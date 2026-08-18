#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
REPO_ROOT="$(CDPATH='' cd -- "$SCRIPT_DIR/../../.." && pwd -P)"
RUN_ID="wp05a-$$"
NETWORK_NAME="dholbeat-${RUN_ID}"
BUILDER_NAME="dholbeat-${RUN_ID}-builder"
POSITIVE_CONTAINER="dholbeat-${RUN_ID}-positive"
NEGATIVE_CONTAINER="dholbeat-${RUN_ID}-negative"
TARGET_IMAGE="dholbeat/wp05a-target:${RUN_ID}"
TARGET_ALIAS="wp05a-baseline-target"
NEGATIVE_ALIAS="wp05a-baseline-negative"
BOOTSTRAP_INVENTORY="inventories/fixtures/hosts.bootstrap.yml"
CONVERGED_INVENTORY="inventories/fixtures/hosts.yml"
CONNECTIVITY_IMAGE="busybox:1.37.0@sha256:9db7b59979c38555a39def84a31fb98b5296952f9e3afd4f6f11f05b07adfab0"
TEMP_ROOT=""
ARTIFACT_ROOT=""
CONTROLLER_IMAGE_ID=""
BUILDKIT_IMAGE=""
BUILDER_CREATED=0
BUILDKIT_IMAGE_PREEXISTED=0
DOCKER_SOCKET_PATH=""
KEEP_FAILED=0
ARTIFACT_LIMIT_KB=65536
ARTIFACT_FILE_LIMIT_BYTES=8388608

usage() {
  printf '%s\n' \
    'Usage: infra/tests/disposable/run.sh [--artifacts PATH] [--keep-failed]' \
    '' \
    'Build a labelled Ubuntu 24.04 systemd fixture, converge the baseline twice' \
    'through the locked controller, run check mode, and prove a failed second SSH' \
    'connection leaves bootstrap access and the unapplied firewall intact.' \
    '' \
    'The harness never contacts production. It removes only its named containers,' \
    'network, target image, builder/cache, and temporary key material. Evidence is' \
    'redacted and bounded.'
}

die() {
  printf 'disposable baseline failure: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ] && [ "$KEEP_FAILED" -eq 1 ]; then
    printf 'kept failed fixtures for inspection: %s %s\n' "$POSITIVE_CONTAINER" "$NEGATIVE_CONTAINER" >&2
  else
    docker container rm --force "$POSITIVE_CONTAINER" >/dev/null 2>&1 || true
    docker container rm --force "$NEGATIVE_CONTAINER" >/dev/null 2>&1 || true
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
    docker image rm "$TARGET_IMAGE" >/dev/null 2>&1 || true
  fi
  if [ "$BUILDER_CREATED" -eq 1 ]; then
    docker buildx rm --force "$BUILDER_NAME" >/dev/null 2>&1 || true
  fi
  if [ "$BUILDKIT_IMAGE_PREEXISTED" -eq 0 ] && [ -n "$BUILDKIT_IMAGE" ]; then
    docker image rm "$BUILDKIT_IMAGE" >/dev/null 2>&1 || true
  fi
  if [ -n "$TEMP_ROOT" ] && [ -d "$TEMP_ROOT" ]; then
    rm -rf -- "$TEMP_ROOT"
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --artifacts)
      [ "$#" -ge 2 ] || die "--artifacts requires a path"
      ARTIFACT_ROOT="$2"
      shift 2
      ;;
    --keep-failed)
      KEEP_FAILED=1
      shift
      ;;
    *) die "unexpected argument: $1" ;;
  esac
done

for command_name in awk docker du find grep jq python3 sed ssh-keygen tail; do
  require_command "$command_name"
done
DOCKER_HOST_URI="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
case "$DOCKER_HOST_URI" in
  unix://*) DOCKER_SOCKET_PATH="${DOCKER_HOST_URI#unix://}" ;;
  *) die "the disposable harness requires a local Unix Docker socket" ;;
esac
[ -S "$DOCKER_SOCKET_PATH" ] || die "Docker socket is unavailable: $DOCKER_SOCKET_PATH"

if [ -z "$ARTIFACT_ROOT" ]; then
  ARTIFACT_ROOT="$REPO_ROOT/.artifacts/wp05a-disposable-$RUN_ID"
elif [[ "$ARTIFACT_ROOT" != /* ]]; then
  ARTIFACT_ROOT="$REPO_ROOT/$ARTIFACT_ROOT"
fi
ARTIFACT_NAME="${ARTIFACT_ROOT##*/}"
[ "$ARTIFACT_ROOT" = "$REPO_ROOT/.artifacts/$ARTIFACT_NAME" ] \
  || die "artifact path must be directly below $REPO_ROOT/.artifacts/"
case "$ARTIFACT_NAME" in
  wp05a-disposable-*) ;;
  *) die "artifact directory must start with wp05a-disposable-" ;;
esac
[ ! -L "$REPO_ROOT/.artifacts" ] || die ".artifacts must not be a symbolic link"
[ ! -e "$REPO_ROOT/.artifacts" ] || [ -d "$REPO_ROOT/.artifacts" ] \
  || die ".artifacts exists but is not a directory"
mkdir -p "$REPO_ROOT/.artifacts"
[ ! -e "$ARTIFACT_ROOT" ] || die "artifact path already exists: $ARTIFACT_ROOT"
EXISTING_ARTIFACT_KB="$(find "$REPO_ROOT/.artifacts" -mindepth 1 -maxdepth 1 \
  -type d -name 'wp05a-disposable-*' -exec du -sk {} + \
  | awk '{total += $1} END {print total + 0}')"
[ "$EXISTING_ARTIFACT_KB" -le "$ARTIFACT_LIMIT_KB" ] \
  || die "existing WP-05A evidence exceeds 64 MiB; inspect and remove exact old run directories"
mkdir -p "$ARTIFACT_ROOT"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dholbeat-wp05a.XXXXXX")"
BUILDKIT_IMAGE="$(awk '$1 == "buildkit_image:" {print $2; exit}' "$REPO_ROOT/toolchain.lock.yml")"
[ -n "$BUILDKIT_IMAGE" ] || die "could not resolve the digest-pinned BuildKit image"

artifact_usage_kb() {
  find "$REPO_ROOT/.artifacts" -mindepth 1 -maxdepth 1 \
    -type d -name 'wp05a-disposable-*' -exec du -sk {} + \
    | awk '{total += $1} END {print total + 0}'
}

assert_artifact_budget() {
  current_artifact_kb="$(artifact_usage_kb)"
  [ "$current_artifact_kb" -le "$ARTIFACT_LIMIT_KB" ] \
    || die "WP-05A evidence exceeds 64 MiB; inspect and remove exact run directories"
}

run_logged() {
  local output_path="$1"
  local errexit_enabled=0
  local statuses
  shift
  case "$-" in
    *e*) errexit_enabled=1 ;;
  esac
  set +e
  "$@" 2>&1 | python3 "$SCRIPT_DIR/bounded_tee.py" \
    --output "$output_path" \
    --limit-bytes "$ARTIFACT_FILE_LIMIT_BYTES"
  statuses=("${PIPESTATUS[@]}")
  if [ "$errexit_enabled" -eq 1 ]; then
    set -e
  fi
  assert_artifact_budget
  [ "${statuses[0]}" -eq 0 ] || return "${statuses[0]}"
  [ "${statuses[1]}" -eq 0 ] || return "${statuses[1]}"
}

"$REPO_ROOT/scripts/controller" digest >"$ARTIFACT_ROOT/controller-digest.txt"
assert_artifact_budget
CONTROLLER_IMAGE_ID="$(awk -F= '$1 == "image_id" {print $2}' "$ARTIFACT_ROOT/controller-digest.txt")"
[ -n "$CONTROLLER_IMAGE_ID" ] || die "could not resolve the locked controller image"

ssh-keygen -q -t ed25519 -N '' -C "${RUN_ID}@fixture" -f "$TEMP_ROOT/id_ed25519"
PUBLIC_KEY="$(sed -n '1p' "$TEMP_ROOT/id_ed25519.pub")"

if docker image inspect "$BUILDKIT_IMAGE" >/dev/null 2>&1; then
  BUILDKIT_IMAGE_PREEXISTED=1
fi
docker buildx create \
  --name "$BUILDER_NAME" \
  --driver docker-container \
  --driver-opt "image=$BUILDKIT_IMAGE" >/dev/null
BUILDER_CREATED=1
run_logged "$ARTIFACT_ROOT/target-build.log" docker buildx build \
  --builder "$BUILDER_NAME" \
  --file "$SCRIPT_DIR/Containerfile" \
  --label io.dholbeat.fixture=wp05a \
  --load \
  --pull \
  --tag "$TARGET_IMAGE" \
  "$SCRIPT_DIR"
docker network create \
  --label io.dholbeat.fixture=wp05a \
  --subnet 172.28.11.0/24 \
  "$NETWORK_NAME" >"$ARTIFACT_ROOT/network-id.txt"

start_target() {
  target_name="$1"
  target_alias="$2"
  docker run --detach \
    --cgroupns=host \
    --hostname "$target_alias" \
    --label io.dholbeat.fixture=wp05a \
    --memory 6g \
    --name "$target_name" \
    --network "$NETWORK_NAME" \
    --network-alias "$target_alias" \
    --privileged \
    --tmpfs /run:rw,nosuid,nodev \
    --tmpfs /run/lock:rw,nosuid,nodev \
    "$TARGET_IMAGE" >/dev/null

  attempts=0
  until docker exec "$target_name" systemctl is-active --quiet ssh.socket \
    >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    [ "$attempts" -lt 60 ] || die "SSH did not start in $target_name"
    sleep 1
  done
  docker exec -i "$target_name" /bin/sh -eu -c \
    'umask 077; mkdir -p /root/.ssh; cat > /root/.ssh/authorized_keys' \
    <"$TEMP_ROOT/id_ed25519.pub"
}

write_known_hosts() {
  target_name="$1"
  target_alias="$2"
  destination="$3"
  docker exec "$target_name" awk -v host="$target_alias" \
    '{print host " " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub >"$destination"
}

write_vars() {
  destination="$1"
  jq -n \
    --arg identity /run/dholbeat-fixture/id_ed25519 \
    --arg key "$PUBLIC_KEY" \
    --arg known /tmp/controller-home/.ssh/known_hosts \
    '{fixture_identity_file:$identity,fixture_admin_authorized_keys:[$key],fixture_known_hosts_file:$known}' \
    >"$destination"
}

run_controller() {
  known_hosts_path="$1"
  shift
  docker run --rm \
    --cap-drop ALL \
    --env ANSIBLE_CONFIG=/workspace/infra/ansible.cfg \
    --env ANSIBLE_FORCE_COLOR=0 \
    --env DOCKER_HOST=unix:///var/run/docker.sock \
    --env HOME=/tmp/controller-home \
    --network "$NETWORK_NAME" \
    --read-only \
    --security-opt no-new-privileges \
    --tmpfs /tmp:rw,nosuid,nodev,size=536870912 \
    --user 0:0 \
    --volume "$DOCKER_SOCKET_PATH:/var/run/docker.sock" \
    --volume "$REPO_ROOT:/workspace:ro" \
    --volume "$TEMP_ROOT/id_ed25519:/run/dholbeat-fixture/id_ed25519:ro" \
    --volume "$TEMP_ROOT/vars.json:/run/dholbeat-fixture/vars.json:ro" \
    --volume "$known_hosts_path:/tmp/controller-home/.ssh/known_hosts:ro" \
    --workdir /workspace/infra \
    "$CONTROLLER_IMAGE_ID" "$@"
}

changed_count() {
  sed -n 's/.*changed=\([0-9][0-9]*\).*/\1/p' "$1" | tail -n 1
}

start_target "$POSITIVE_CONTAINER" "$TARGET_ALIAS"
write_known_hosts "$POSITIVE_CONTAINER" "$TARGET_ALIAS" "$TEMP_ROOT/known_hosts-positive"
write_vars "$TEMP_ROOT/vars.json"

run_logged "$ARTIFACT_ROOT/first-converge.log" \
  run_controller "$TEMP_ROOT/known_hosts-positive" \
  ansible-playbook --inventory "$BOOTSTRAP_INVENTORY" playbooks/baseline.yml \
  --extra-vars @/run/dholbeat-fixture/vars.json \
  --extra-vars "ansible_host=$POSITIVE_CONTAINER"

run_logged "$ARTIFACT_ROOT/second-converge.log" \
  run_controller "$TEMP_ROOT/known_hosts-positive" \
  ansible-playbook --inventory "$CONVERGED_INVENTORY" playbooks/baseline.yml \
  --extra-vars @/run/dholbeat-fixture/vars.json \
  --extra-vars "ansible_host=$POSITIVE_CONTAINER"

SECOND_CHANGED="$(changed_count "$ARTIFACT_ROOT/second-converge.log")"
[ "$SECOND_CHANGED" = "0" ] || die "second convergence changed $SECOND_CHANGED task(s)"

run_logged "$ARTIFACT_ROOT/check-mode.log" \
  run_controller "$TEMP_ROOT/known_hosts-positive" \
  ansible-playbook --inventory "$CONVERGED_INVENTORY" playbooks/baseline.yml \
  --check \
  --diff \
  --extra-vars @/run/dholbeat-fixture/vars.json \
  --extra-vars "ansible_host=$POSITIVE_CONTAINER"

CHECK_CHANGED="$(changed_count "$ARTIFACT_ROOT/check-mode.log")"
[ "$CHECK_CHANGED" = "0" ] || die "converged check mode reported $CHECK_CHANGED change(s)"

docker exec "$POSITIVE_CONTAINER" dpkg-query --show \
  --showformat='${binary:Package}\t${Version}\n' \
  containerd.io docker-buildx-plugin docker-ce docker-ce-cli docker-compose-plugin \
  >"$ARTIFACT_ROOT/resolved-packages.tsv"
docker exec "$POSITIVE_CONTAINER" /usr/sbin/ufw status verbose >"$ARTIFACT_ROOT/firewall-status.txt"
docker exec "$POSITIVE_CONTAINER" /usr/bin/docker info --format json \
  | jq '{ServerVersion,Driver,LoggingDriver,LiveRestoreEnabled}' \
  >"$ARTIFACT_ROOT/docker-info.json"

docker exec "$POSITIVE_CONTAINER" systemctl restart docker.service
docker exec "$POSITIVE_CONTAINER" systemctl is-active dholbeat-docker-firewall.service \
  >"$ARTIFACT_ROOT/docker-firewall-restart.txt"
docker exec "$POSITIVE_CONTAINER" iptables -w -C DOCKER-USER \
  -j DHOLBEAT-DOCKER-INGRESS

# The single-quoted script expands only inside the disposable target.
# shellcheck disable=SC2016
run_logged "$ARTIFACT_ROOT/container-connectivity.txt" \
  docker exec "$POSITIVE_CONTAINER" /bin/sh -eu -c '
    image=$1
    network=wp05a-connectivity
    server=wp05a-connectivity-server
    ingress=wp05a-connectivity-ingress
    docker pull --quiet "$image"
    docker network create "$network" >/dev/null
    docker run --detach --name "$server" --network "$network" "$image" \
      sh -c "mkdir -p /www; printf passed >/www/index.html; exec httpd -f -p 8080 -h /www" \
      >/dev/null
    attempts=0
    until docker run --rm --network "$network" "$image" \
      wget -q -T 3 -O - "http://$server:8080" | grep -q passed; do
      attempts=$((attempts + 1))
      [ "$attempts" -lt 10 ] || exit 1
      sleep 1
    done
    printf "container_to_container=passed\n"
    docker run --rm "$image" nc -z -w 10 1.1.1.1 443
    printf "container_egress=passed\n"
    docker run --detach --name "$ingress" --publish 18080:8080 "$image" \
      httpd -f -p 8080 >/dev/null
  ' fixture-connectivity "$CONNECTIVITY_IMAGE"

run_logged "$ARTIFACT_ROOT/published-port-blocked.txt" \
  run_controller "$TEMP_ROOT/known_hosts-positive" \
    python3 -c 'import socket, sys; sock = socket.socket(); sock.settimeout(3); result = sock.connect_ex((sys.argv[1], int(sys.argv[2]))); sock.close(); print("published_port_blocked=passed" if result else "published_port_blocked=failed"); raise SystemExit(1 if result == 0 else 0)' \
    "$TARGET_ALIAS" 18080

docker exec "$POSITIVE_CONTAINER" docker container rm --force \
  wp05a-connectivity-server wp05a-connectivity-ingress >/dev/null
docker exec "$POSITIVE_CONTAINER" docker network rm wp05a-connectivity >/dev/null
docker exec "$POSITIVE_CONTAINER" docker image rm "$CONNECTIVITY_IMAGE" >/dev/null
assert_artifact_budget

start_target "$NEGATIVE_CONTAINER" "$NEGATIVE_ALIAS"
write_known_hosts "$NEGATIVE_CONTAINER" "$NEGATIVE_ALIAS" "$TEMP_ROOT/known_hosts-negative"

set +e
run_logged "$ARTIFACT_ROOT/failed-second-connection.log" \
  run_controller "$TEMP_ROOT/known_hosts-negative" \
  ansible-playbook --inventory "$BOOTSTRAP_INVENTORY" playbooks/baseline.yml \
  --extra-vars @/run/dholbeat-fixture/vars.json \
  --extra-vars "ansible_host=$NEGATIVE_CONTAINER" \
  --extra-vars "baseline_second_connection_host=$NEGATIVE_ALIAS" \
  --extra-vars baseline_second_connection_port=9
NEGATIVE_STATUS=$?
set -e
[ "$NEGATIVE_STATUS" -ne 0 ] || die "failed second-connection fixture unexpectedly converged"
grep -q 'second connection probe failed' "$ARTIFACT_ROOT/failed-second-connection.log" \
  || die "failed second-connection fixture did not stop at the safety probe"

run_controller "$TEMP_ROOT/known_hosts-negative" \
  python3 /workspace/infra/roles/base/files/second_connection_probe.py \
  --host "$NEGATIVE_ALIAS" \
  --port 22 \
  --user root \
  --identity-file /run/dholbeat-fixture/id_ed25519 \
  --known-hosts-file /tmp/controller-home/.ssh/known_hosts \
  >"$ARTIFACT_ROOT/break-glass-probe.log"
docker exec "$NEGATIVE_CONTAINER" /bin/sh -c \
  'if command -v ufw >/dev/null 2>&1; then ufw status; else printf "Status: not-installed\n"; fi' \
  >"$ARTIFACT_ROOT/failed-probe-firewall-status.txt"
grep -Eq '^Status: (inactive|not-installed)$' "$ARTIFACT_ROOT/failed-probe-firewall-status.txt" \
  || die "firewall changed after the failed connection probe"
assert_artifact_budget

FIRST_CHANGED="$(changed_count "$ARTIFACT_ROOT/first-converge.log")"
TARGET_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$TARGET_IMAGE")"
TARGET_BASE_REFERENCE="$(awk '$1 == "FROM" {print $2; exit}' "$SCRIPT_DIR/Containerfile")"
printf '%s\n' \
  'schema_version: 1' \
  "controller_image_id: $CONTROLLER_IMAGE_ID" \
  "target_image_id: $TARGET_IMAGE_ID" \
  "target_base_reference: $TARGET_BASE_REFERENCE" \
  "first_run_changed: $FIRST_CHANGED" \
  "second_run_changed: $SECOND_CHANGED" \
  "check_mode_changed: $CHECK_CHANGED" \
  'failed_second_connection: rejected' \
  'bootstrap_access_after_failure: passed' \
  'firewall_after_failed_probe: inactive' \
  'docker_firewall_restart: passed' \
  'container_egress: passed' \
  'container_to_container: passed' \
  'unlisted_published_port: blocked' \
  'production_contacted: false' \
  'software_monthly_cost_usd: 0' \
  >"$ARTIFACT_ROOT/summary.yml"
assert_artifact_budget

printf 'disposable baseline evidence: %s\n' "$ARTIFACT_ROOT"
