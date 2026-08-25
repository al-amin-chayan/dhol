#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
REPO_ROOT="$(CDPATH='' cd -- "$SCRIPT_DIR/../../.." && pwd -P)"
# shellcheck source=scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

CANDIDATE=""
VARIANT=""
ARTIFACT_ROOT="$REPO_ROOT/.artifacts/publisher-eval"
KEEP_FAILED=0
SAMPLE_INTERVAL=2
# The sampler is stopped when the matrix and drills finish; the cap only keeps
# a hung run from sampling forever.
SAMPLE_ROUNDS=1800
PROJECT=""
TEMP_ROOT=""
SAMPLER_PID=""
READY_CODE=""
STARTUP_SECONDS=""
CONVERGE_EPOCH=""
ARTIFACT_FILE_LIMIT_BYTES=1048576

usage() {
  cat <<'EOF'
Usage: infra/tests/publisher-eval/run.sh --candidate ID [--variant ID]
                                         [--artifacts PATH] [--keep-failed]

Run the DG-01 fixture matrix against one disposable publisher candidate:
converge the pinned topology, register the generic project fixtures, run the
positive and negative authorization matrix, exercise the registration lock and
an application-consistent dump/restore drill, sample resources, then destroy
the stack and its volumes.

The harness never contacts a social provider, never reads production
inventory, and writes only redacted, bounded evidence.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --candidate) [ "$#" -ge 2 ] || dholbeat_die "--candidate needs a value"; CANDIDATE="$2"; shift 2 ;;
    --variant) [ "$#" -ge 2 ] || dholbeat_die "--variant needs a value"; VARIANT="$2"; shift 2 ;;
    --artifacts) [ "$#" -ge 2 ] || dholbeat_die "--artifacts needs a value"; ARTIFACT_ROOT="$2"; shift 2 ;;
    --keep-failed) KEEP_FAILED=1; shift ;;
    *) dholbeat_die "unexpected argument: $1" ;;
  esac
done

[ -n "$CANDIDATE" ] || dholbeat_die "--candidate is required"
dholbeat_require_command docker
dholbeat_require_command python3
dholbeat_require_command openssl

case "$CANDIDATE" in
  postiz) [ -n "$VARIANT" ] || VARIANT="temporal-es" ;;
  mixpost-lite) [ -n "$VARIANT" ] || VARIANT="default" ;;
  *) dholbeat_die "unknown candidate: $CANDIDATE" ;;
esac

pin() {
  python3 "$SCRIPT_DIR/pins.py" --root "$SCRIPT_DIR" --candidate "$CANDIDATE" "$@"
}

[ "$(pin --field evaluable)" = "true" ] || dholbeat_die "$CANDIDATE is not evaluable without an unapproved purchase"

IMAGE="$(pin --field image)"
VERSION="$(pin --field version)"
COMPOSE_FILE="$SCRIPT_DIR/$(pin --field compose)"
PROFILES="$(pin --variant "$VARIANT" --field profiles)"
PROFILE_ARGS=""
for profile in $PROFILES; do
  case "$profile" in
    *[!a-z0-9-]*) dholbeat_die "profile id is not a bare slug: $profile" ;;
  esac
  PROFILE_ARGS="$PROFILE_ARGS --profile $profile"
done
PLATFORM="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
PROJECT="dg01-${CANDIDATE}-$$"
RUN_ROOT="$ARTIFACT_ROOT/$CANDIDATE/$VARIANT"

# Bash 3.2 is the default shell on the operator's macOS, and there
# `"${empty[@]}"` under `set -u` is an unbound-variable error rather than an
# empty expansion. Every variant with no Compose profile would abort before
# Compose ran, so the profile flags are built as a plain string instead of an
# array. PROFILES holds validated profile ids from candidates.yml, never
# operator input.
compose() {
  # shellcheck disable=SC2086
  docker compose --env-file "$TEMP_ROOT/stack.env" -p "$PROJECT" \
    $PROFILE_ARGS -f "$COMPOSE_FILE" "$@"
}

container() {
  compose ps -q "$1"
}

# A harness that promises to destroy its stack must prove it did. Swallowing the
# teardown error leaves publisher containers and volumes running on the
# operator's machine while the run reports success.
# A harness that promises to destroy its stack must prove it did, and must not
# report success when it could not. A surviving publisher stack keeps
# containers, volumes and a network on the operator's machine.
teardown() {
  local failed=0
  if ! compose down --volumes --remove-orphans >"$TEMP_ROOT/teardown.log" 2>&1; then
    printf 'teardown command failed for project %s:\n' "$PROJECT" >&2
    tail -20 "$TEMP_ROOT/teardown.log" >&2 || true
    failed=1
  fi
  local containers volumes networks
  containers="$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=$PROJECT" | grep -c . || true)"
  volumes="$(docker volume ls --quiet \
    --filter "label=com.docker.compose.project=$PROJECT" | grep -c . || true)"
  networks="$(docker network ls --quiet \
    --filter "label=com.docker.compose.project=$PROJECT" | grep -c . || true)"
  if [ "$containers" != "0" ] || [ "$volumes" != "0" ] || [ "$networks" != "0" ]; then
    printf 'teardown left %s container(s), %s volume(s), %s network(s) for project %s; remove them with:\n  docker compose -p %s down --volumes --remove-orphans\n' \
      "$containers" "$volumes" "$networks" "$PROJECT" "$PROJECT" >&2
    failed=1
  fi
  return "$failed"
}

# An interrupted evaluation must never report success. `cleanup` preserves
# whatever `$?` preceded it, and on bash 3.2 a signal delivered right after a
# successful command reaches the handler with `$?` still 0 — so running cleanup
# straight off INT/TERM/HUP let a run that destroyed its stack mid-flight exit
# 0. The signal handlers now record the conventional 128+n status explicitly and
# exit with it; cleanup stays the single, non-reentrant teardown path and runs
# only from EXIT, where it honours that recorded status.
SIGNAL_STATUS=""

on_signal() {
  SIGNAL_STATUS="$1"
  trap - INT TERM HUP
  exit "$SIGNAL_STATUS"
}

cleanup() {
  status=$?
  trap - EXIT INT TERM HUP
  [ -z "$SIGNAL_STATUS" ] || status="$SIGNAL_STATUS"
  if [ -n "$SAMPLER_PID" ]; then
    kill "$SAMPLER_PID" >/dev/null 2>&1 || true
    wait "$SAMPLER_PID" 2>/dev/null || true
  fi
  if [ "$status" -ne 0 ] && [ "$KEEP_FAILED" -eq 1 ]; then
    printf 'kept the failed %s stack for inspection: project %s\n' "$CANDIDATE" "$PROJECT" >&2
  elif [ -n "$TEMP_ROOT" ] && [ -f "$TEMP_ROOT/stack.env" ]; then
    # A teardown that could not finish is a failure of the run, not a note on
    # it: leaving a publisher stack up is exactly what this harness promises
    # never to do.
    if ! teardown && [ "$status" -eq 0 ]; then
      status=1
    fi
  fi
  # The scratch directory holds this run's fixture credentials, so it goes even
  # when the stack could not be destroyed.
  if [ -n "$TEMP_ROOT" ] && [ -d "$TEMP_ROOT" ]; then
    rm -rf -- "$TEMP_ROOT"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'on_signal 130' INT
trap 'on_signal 143' TERM
trap 'on_signal 129' HUP

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dholbeat-dg01.XXXXXX")"
# Throwaway fixture credentials are generated per run and must never be written
# inside the repository, where an ignored directory or a stray add would keep
# them.
case "$(dholbeat_canonical_path "$TEMP_ROOT")" in
  "$REPO_ROOT"|"$REPO_ROOT"/*) dholbeat_die "the evaluation scratch directory must live outside the repository" ;;
esac
mkdir -p "$RUN_ROOT"

HOST_PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
FIXTURE_PASSWORD_PREFIX="dg01-$(openssl rand -hex 8)"

case "$CANDIDATE" in
  postiz)
    cat >"$TEMP_ROOT/stack.env" <<EOF
POSTIZ_HOST_PORT=$HOST_PORT
POSTIZ_JWT_SECRET=$(openssl rand -hex 32)
POSTIZ_DB_PASSWORD=$(openssl rand -hex 16)
TEMPORAL_DB_PASSWORD=$(openssl rand -hex 16)
TEMPORAL_ENABLE_ES=$([ -n "$PROFILES" ] && printf 'true' || printf 'false')
POSTIZ_DISABLE_REGISTRATION=false
EOF
    ;;
  mixpost-lite)
    cat >"$TEMP_ROOT/stack.env" <<EOF
MIXPOST_HOST_PORT=$HOST_PORT
MIXPOST_APP_KEY=base64:$(openssl rand -base64 32)
MIXPOST_DB_PASSWORD=$(openssl rand -hex 16)
MIXPOST_DB_ROOT_PASSWORD=$(openssl rand -hex 16)
EOF
    ;;
esac
chmod 600 "$TEMP_ROOT/stack.env"

printf '==> pulling %s\n' "$IMAGE"
compose pull --quiet
printf '==> converging %s (%s) on %s\n' "$CANDIDATE" "$VARIANT" "$PLATFORM"
CONVERGE_EPOCH="$(date +%s)"
compose up --detach --wait --wait-timeout 600 || compose up --detach

sample_resources() {
  local names
  names="$(compose ps --format '{{.Name}}' | tr '\n' ' ')"
  local round=0
  : >"$TEMP_ROOT/samples.txt"
  while [ "$round" -lt "$SAMPLE_ROUNDS" ]; do
    # shellcheck disable=SC2086
    docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}' $names >>"$TEMP_ROOT/samples.txt" 2>/dev/null || true
    printf '\n' >>"$TEMP_ROOT/samples.txt"
    round=$((round + 1))
    sleep "$SAMPLE_INTERVAL"
  done
}

# A Compose healthcheck reports the web server, not the first-boot database
# migration behind it, so the harness waits for the application's own entry
# route before it creates fixtures.
#
# Readiness is the one status the route is supposed to answer with, never
# "anything that is not a gateway error". Accepting any other code let a 404
# from a half-registered route, or a reverse-proxy error page the harness had
# not enumerated, count as a serving application — and the registration-lock
# drill then read that outage as a working control.
wait_for_http() {
  local url="$1"
  local attempts="$2"
  local expected="$3"
  local code=""
  local attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [ "$code" = "$expected" ]; then
      printf '%s\n' "$code"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 5
  done
  diagnose_stalled_application >&2
  dholbeat_die "timed out waiting for $url (expected HTTP $expected, last HTTP code: ${code:-none})"
}

# The serving response of each candidate's readiness route at its pinned
# version. Postiz's /api/user/self sits behind AuthMiddleware, which raises
# HttpForbiddenException; the globally registered HttpExceptionFilter rewrites
# that to a bodyless 401, so an unauthenticated request to a healthy v2.23.0
# backend answers exactly 401. Mixpost Lite's login page is a plain 200.
POSTIZ_SERVING_CODE=401
MIXPOST_SERVING_CODE=200

# Decide what a registration attempt proved, as `result|detail`. Kept a
# function so the decision itself is unit-tested rather than only exercised by
# a full live run: the difference between "the toggle closed registration" and
# "something else refused the request" is the whole point of the drill.
registration_lock_verdict() {
  local status="$1"
  local body="$2"
  local marker="$3"
  local ready="$4"
  case "$status" in
    200)
      printf 'fail|DISABLE_REGISTRATION=true still accepted a new registration (HTTP %s).\n' "$status"
      ;;
    400)
      if grep -qF "$marker" "$body" 2>/dev/null; then
        printf 'pass|the backend answered HTTP %s when serving, then refused a new registration with HTTP %s and the pinned "%s" error.\n' \
          "$ready" "$status" "$marker"
      else
        printf 'fail|registration returned HTTP %s without the pinned "%s" error, so the refusal shows some other validation or auth failure rather than the toggle.\n' \
          "$status" "$marker"
      fi
      ;;
    *)
      # 404 would mean the route is absent rather than closed, and 429 is rate
      # limiting. Neither shows the toggle working.
      printf 'fail|registration returned HTTP %s, which shows neither an open nor a deliberately closed registration surface.\n' "$status"
      ;;
  esac
}

# A convergence that never answers is the most likely way this harness fails on
# a small host, so it reports why rather than only that it gave up.
diagnose_stalled_application() {
  printf 'the application never answered; last container state and logs follow\n'
  compose ps || true
  local names=()
  local name
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    names+=("$name")
  done < <(compose ps --format '{{.Name}}')
  if [ "${#names[@]}" -gt 0 ]; then
    docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}' "${names[@]}" || true
  fi
  case "$CANDIDATE" in
    postiz)
      docker exec "$(container postiz)" sh -c 'tail -25 /root/.pm2/logs/backend-error.log' || true
      ;;
    mixpost-lite)
      compose logs --tail 25 mixpost || true
      ;;
  esac
}

sample_resources &
SAMPLER_PID=$!

PROBE_ARGS=(
  --candidate "$CANDIDATE"
  --base-url "http://localhost:$HOST_PORT"
  --output "$TEMP_ROOT/checks.json"
  --image "$IMAGE"
  --variant "$VARIANT"
  --platform "$PLATFORM"
)

case "$CANDIDATE" in
  postiz)
    PROBE_ARGS+=(
      --postgres-container "$(container postiz-postgres)"
      --schedule-at "$(date -u -v+2d '+%Y-%m-%dT12:00:00Z' 2>/dev/null || date -u -d '+2 days' '+%Y-%m-%dT12:00:00Z')"
      --window-start "$(date -u -v-1d '+%Y-%m-%dT00:00:00Z' 2>/dev/null || date -u -d '-1 day' '+%Y-%m-%dT00:00:00Z')"
      --window-end "$(date -u -v+30d '+%Y-%m-%dT00:00:00Z' 2>/dev/null || date -u -d '+30 days' '+%Y-%m-%dT00:00:00Z')"
      --fixture-password-prefix "$FIXTURE_PASSWORD_PREFIX"
    )
    READY_CODE="$(wait_for_http "http://localhost:$HOST_PORT/api/user/self" 240 "$POSTIZ_SERVING_CODE")" ||
      dholbeat_die "the Postiz backend never answered; with --variant temporal-sql this is the expected Temporal search-attribute failure"
    STARTUP_SECONDS="$(( $(date +%s) - CONVERGE_EPOCH ))"
    printf '    backend answered HTTP %s after %ss\n' "$READY_CODE" "$STARTUP_SECONDS"
    ;;
  mixpost-lite)
    MIXPOST_CONTAINER="$(container mixpost)"
    READY_CODE="$(wait_for_http "http://localhost:$HOST_PORT/mixpost/login" 90 "$MIXPOST_SERVING_CODE")" ||
      dholbeat_die "the Mixpost login page never answered"
    STARTUP_SECONDS="$(( $(date +%s) - CONVERGE_EPOCH ))"
    printf '    login page answered HTTP %s after %ss\n' "$READY_CODE" "$STARTUP_SECONDS"
    for slug in project-a project-b; do
      printf '%s\n%s\n%s\n%s\n' \
        "DG01 ${slug}" "${slug}@dg01.invalid" "${FIXTURE_PASSWORD_PREFIX}-${slug}" "${FIXTURE_PASSWORD_PREFIX}-${slug}" |
        docker exec -i "$MIXPOST_CONTAINER" sh -c 'cd /var/www/html && php artisan mixpost-auth:create --no-ansi' \
          >"$TEMP_ROOT/mixpost-auth-${slug}.log" 2>&1 ||
        dholbeat_die "creating the ${slug} login failed: $(tail -3 "$TEMP_ROOT/mixpost-auth-${slug}.log")"
    done
    PROBE_ARGS+=(
      --mixpost-container "$MIXPOST_CONTAINER"
      --mixpost-password-a "${FIXTURE_PASSWORD_PREFIX}-project-a"
      --mixpost-password-b "${FIXTURE_PASSWORD_PREFIX}-project-b"
    )
    ;;
esac

printf '==> running the fixture matrix\n'
python3 "$SCRIPT_DIR/probe.py" "${PROBE_ARGS[@]}"

printf '==> registration lock and restore drills\n'
python3 - "$CANDIDATE" "$TEMP_ROOT/drills.json" <<'PY' || dholbeat_die "drill recording failed"
import json, sys
candidate, output = sys.argv[1], sys.argv[2]
json.dump({"candidate": candidate, "drills": []}, open(output, "w"), indent=2)
PY

drill() {
  python3 - "$TEMP_ROOT/drills.json" "$1" "$2" "$3" <<'PY'
import json, sys
path, drill_id, result, detail = sys.argv[1:5]
document = json.load(open(path))
document["drills"].append({"id": drill_id, "result": result, "detail": detail})
json.dump(document, open(path, "w"), indent=2, sort_keys=True)
PY
}

# Read one scalar out of the matrix run's `capabilities` block. Prints nothing
# when the key is missing, unreadable or not a short, plain scalar, so a caller
# can decide to pass nothing rather than forward junk into a probe argument.
capability() {
  python3 - "$TEMP_ROOT/checks.json" "$1" <<'PY'
import json, re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path) as handle:
        document = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(0)
capabilities = document.get("capabilities")
if not isinstance(capabilities, dict):
    raise SystemExit(0)
value = capabilities.get(key)
if isinstance(value, bool) or not isinstance(value, (str, int)):
    raise SystemExit(0)
value = str(value)
if re.match(r"^[A-Za-z0-9:._+-]{1,128}$", value):
    sys.stdout.write(value)
PY
}

case "$CANDIDATE" in
  postiz)
    # Restore after rebuild, not in place — and the rebuild has to cover every
    # surface the decision packet calls rebuildable, not just the one the backup
    # protects. Temporal, its own PostgreSQL and the Elasticsearch visibility
    # store are excluded from the retained dump on the claim that they can be
    # regenerated; leaving them running through the drill would have proved only
    # that the dump reloads beside state that was never at risk. So the dump is
    # taken, the Postiz database volume *and* every excluded surface are
    # destroyed, the retained dump alone is reloaded, Temporal is re-provisioned
    # from empty and the application is restarted against the result. A row
    # count would only show the rows returned; the probe then proves the
    # restored instance still authenticates a project, mints its credential,
    # serves its own channel and refuses another project's.
    HAS_ES=0
    case " $PROFILES " in *" visibility-es "*) HAS_ES=1 ;; esac

    POSTGRES="$(container postiz-postgres)"
    docker exec "$POSTGRES" pg_dump -U postiz -d postiz --clean --if-exists >"$TEMP_ROOT/postiz.sql"
    BEFORE="$(docker exec "$POSTGRES" psql -U postiz -d postiz -tAc 'select count(*) from "Organization";')"
    RETAINED_POST_ID="$(capability retained_pending_post_id)"
    RETAINED_POST_AT="$(capability retained_pending_post_at)"

    # Temporal's database is RETAINED state, not rebuildable. A post is a row
    # plus the workflow that will send it, and at v2.23.0 the recovery scan only
    # re-queues posts whose publishDate is already past — so rebuilding Temporal
    # empty strands every future job until it is late. It is therefore dumped
    # and restored alongside the Postiz database, and only the Elasticsearch
    # visibility index is treated as rebuildable.
    TEMPORAL_POSTGRES="$(container temporal-postgres)"
    docker exec "$TEMPORAL_POSTGRES" pg_dump -U temporal -d temporal --clean --if-exists \
      >"$TEMP_ROOT/temporal.sql"

    compose stop postiz >/dev/null
    # Temporal is removed rather than merely stopped: its schema and namespace
    # live in the temporal-postgres volume that is about to go, and auto-setup
    # only re-provisions them on a fresh container start.
    compose rm --force --stop --volumes temporal >/dev/null
    compose rm --force --stop --volumes postiz-postgres temporal-postgres >/dev/null
    # `compose rm --volumes` only takes anonymous volumes, so the two named data
    # volumes are removed explicitly.
    docker volume rm "${PROJECT}_postiz-postgres-data" >/dev/null 2>&1 || true
    docker volume rm "${PROJECT}_temporal-postgres-data" >/dev/null 2>&1 || true
    if [ "$HAS_ES" -eq 1 ]; then
      # Elasticsearch declares no named volume in this topology, so its indices
      # live in the container's own writable layer and removing the container is
      # what destroys the visibility store. It is started first because it is
      # the slowest of the rebuilt surfaces to accept connections.
      compose rm --force --stop --volumes temporal-elasticsearch >/dev/null
      compose up --detach --no-deps temporal-elasticsearch >/dev/null
    fi
    compose up --detach --no-deps --wait --wait-timeout 300 postiz-postgres temporal-postgres >/dev/null
    POSTGRES="$(container postiz-postgres)"
    REBUILT="$(docker exec "$POSTGRES" psql -U postiz -d postiz -tAc \
      "select count(*) from information_schema.tables where table_schema='public';")"
    docker exec -i "$POSTGRES" psql -U postiz -d postiz \
      >"$TEMP_ROOT/postiz-restore.log" 2>&1 <"$TEMP_ROOT/postiz.sql" || true
    AFTER="$(docker exec "$POSTGRES" psql -U postiz -d postiz -tAc 'select count(*) from "Organization";')"

    # Restore the retained Temporal database before Temporal starts, so
    # auto-setup finds an existing schema rather than provisioning an empty one.
    TEMPORAL_POSTGRES="$(container temporal-postgres)"
    docker exec -i "$TEMPORAL_POSTGRES" psql -U temporal -d temporal \
      >"$TEMP_ROOT/temporal-restore.log" 2>&1 <"$TEMP_ROOT/temporal.sql" || true
    compose up --detach --no-deps temporal >/dev/null

    # A restored row that has no workflow behind it will not fire at its time.
    # Count Temporal's own open executions rather than trusting the Postiz row.
    OPEN_EXECUTIONS="$(docker exec "$TEMPORAL_POSTGRES" psql -U temporal -d temporal -tAc \
      "select count(*) from executions;" 2>/dev/null | tr -d ' ')"
    case "${OPEN_EXECUTIONS:-}" in
      ''|*[!0-9]*) WORKFLOW_RESTORED=false ;;
      0) WORKFLOW_RESTORED=false ;;
      *) WORKFLOW_RESTORED=true ;;
    esac
    compose start postiz >/dev/null
    # The verification probe must not race the rebuild: a backend still coming
    # back refuses a project's login exactly the way an unrestored database
    # would, which would report a lost restore as a lost restore for the wrong
    # reason.
    wait_for_http "http://localhost:$HOST_PORT/api/user/self" 240 "$POSTIZ_SERVING_CODE" >/dev/null ||
      dholbeat_die "the Postiz backend never came back after the restore rebuild"

    RESTORE_PROBE_ARGS=(
      --candidate postiz --mode restore-verify
      --base-url "http://localhost:$HOST_PORT"
      --image "$IMAGE" --variant "$VARIANT" --platform "$PLATFORM"
      --fixture-password-prefix "$FIXTURE_PASSWORD_PREFIX"
      --output "$TEMP_ROOT/restore-verify.json"
    )
    # The matrix run leaves one pending scheduled post behind and records it
    # under `capabilities`; the probe checks that the restored instance still
    # holds it. Both halves are needed to identify it, so a missing or
    # unusable value forwards nothing and leaves the verdict tool to say so.
    if [ -n "$RETAINED_POST_ID" ] && [ -n "$RETAINED_POST_AT" ]; then
      RESTORE_PROBE_ARGS+=(
        --restored-pending-post-id "$RETAINED_POST_ID"
        --restored-pending-post-at "$RETAINED_POST_AT"
      )
    fi
    python3 "$SCRIPT_DIR/probe.py" "${RESTORE_PROBE_ARGS[@]}" 2>/dev/null || true

    RESTORE_VERDICT="$(python3 "$SCRIPT_DIR/restore_verdict.py" \
      --results "$TEMP_ROOT/restore-verify.json" \
      --workflow-execution-restored "$WORKFLOW_RESTORED" \
      --rebuilt-tables "$REBUILT" --organizations-before "$BEFORE" --organizations-after "$AFTER")"
    drill backup.dump-restore "${RESTORE_VERDICT%%|*}" "${RESTORE_VERDICT#*|}"

    sed -i.bak 's/^POSTIZ_DISABLE_REGISTRATION=.*/POSTIZ_DISABLE_REGISTRATION=true/' "$TEMP_ROOT/stack.env"
    rm -f "$TEMP_ROOT/stack.env.bak"
    compose up --detach --no-deps postiz >/dev/null
    # Wait for the recreated backend to actually be serving before asking it to
    # reject a registration. A restarting or rate-limiting instance refuses
    # everything, and counting that as a locked registration surface would let
    # an outage masquerade as a working control.
    READY_CODE="$(wait_for_http "http://localhost:$HOST_PORT/api/user/self" 240 "$POSTIZ_SERVING_CODE")" ||
      dholbeat_die "the Postiz backend never came back after the registration-lock restart"
    # At the pinned v2.23.0, AuthService.routeAuth throws Error('Registration is
    # disabled') when canRegister() is false and AuthController.register catches
    # it as `response.status(400).send(e.message)` — so the toggle working looks
    # like exactly HTTP 400 carrying that plain-text message, and nothing else.
    # A bare 400 is an ordinary DTO validation failure and a 401/403 is the auth
    # surface refusing for its own reasons; neither shows the lock. The body is
    # captured but never quoted into evidence beyond the marker itself.
    # https://github.com/gitroomhq/postiz-app/blob/v2.23.0/apps/backend/src/services/auth/auth.service.ts#L55-L57
    LOCK_MARKER='Registration is disabled'
    LOCK_BODY="$TEMP_ROOT/registration-lock.body"
    LOCK_STATUS="$(curl -s -o "$LOCK_BODY" -w '%{http_code}' -X POST \
      --max-filesize 65536 \
      -H 'Content-Type: application/json' \
      -d '{"email":"locked@dg01.invalid","password":"dg01-locked-fixture","company":"Locked","provider":"LOCAL"}' \
      "http://localhost:$HOST_PORT/api/auth/register" || true)"
    LOCK_VERDICT="$(registration_lock_verdict "$LOCK_STATUS" "$LOCK_BODY" "$LOCK_MARKER" "$READY_CODE")"
    drill registration.lock "${LOCK_VERDICT%%|*}" "${LOCK_VERDICT#*|}"
    rm -f "$LOCK_BODY"
    ;;
  mixpost-lite)
    # Same shape as the Postiz drill: rebuild the data volume from empty rather
    # than reloading over the live database, then prove the restored instance
    # still authenticates and serves its data.
    MYSQL="$(container mixpost-mysql)"
    docker exec "$MYSQL" sh -c 'exec mysqldump --no-tablespaces -umixpost -p"$MYSQL_PASSWORD" mixpost' >"$TEMP_ROOT/mixpost.sql"
    BEFORE="$(docker exec "$MYSQL" sh -c 'exec mysql -umixpost -p"$MYSQL_PASSWORD" -N -B -e "select count(*) from users" mixpost')"

    compose stop mixpost >/dev/null
    compose rm --force --stop --volumes mixpost-mysql >/dev/null
    docker volume rm "${PROJECT}_mixpost-mysql-data" >/dev/null 2>&1 || true
    compose up --detach --no-deps --wait --wait-timeout 300 mixpost-mysql >/dev/null
    MYSQL="$(container mixpost-mysql)"
    REBUILT="$(docker exec "$MYSQL" sh -c 'exec mysql -umixpost -p"$MYSQL_PASSWORD" -N -B -e "select count(*) from information_schema.tables where table_schema=\"mixpost\"" mixpost')"
    docker exec -i "$MYSQL" sh -c 'exec mysql -umixpost -p"$MYSQL_PASSWORD" mixpost' \
      >"$TEMP_ROOT/mixpost-restore.log" 2>&1 <"$TEMP_ROOT/mixpost.sql" || true
    AFTER="$(docker exec "$MYSQL" sh -c 'exec mysql -umixpost -p"$MYSQL_PASSWORD" -N -B -e "select count(*) from users" mixpost')"
    compose start mixpost >/dev/null

    python3 "$SCRIPT_DIR/probe.py" \
      --candidate mixpost-lite --mode restore-verify \
      --base-url "http://localhost:$HOST_PORT" \
      --image "$IMAGE" --variant "$VARIANT" --platform "$PLATFORM" \
      --mixpost-container "$MIXPOST_CONTAINER" \
      --mixpost-password-a "${FIXTURE_PASSWORD_PREFIX}-project-a" \
      --mixpost-password-b "${FIXTURE_PASSWORD_PREFIX}-project-b" \
      --output "$TEMP_ROOT/restore-verify.json" 2>/dev/null || true

    RESTORE_VERDICT="$(python3 "$SCRIPT_DIR/restore_verdict.py" \
      --results "$TEMP_ROOT/restore-verify.json" --candidate mixpost-lite \
      --rebuilt-tables "$REBUILT" --organizations-before "$BEFORE" --organizations-after "$AFTER")"
    drill backup.dump-restore "${RESTORE_VERDICT%%|*}" "${RESTORE_VERDICT#*|}"
    drill registration.lock pass "Mixpost Lite registers no self-signup route, so there is nothing to lock."
    ;;
esac

printf '==> summarising resources\n'
kill "$SAMPLER_PID" >/dev/null 2>&1 || true
wait "$SAMPLER_PID" 2>/dev/null || true
SAMPLER_PID=""

VOLUME_MIB="$(compose ps --format '{{.Name}}' >/dev/null 2>&1; docker system df -v --format '{{json .Volumes}}' 2>/dev/null |
  python3 -c "
import json,sys
project=sys.argv[1]
raw=sys.stdin.read().strip()
total=0.0
if raw:
    for volume in json.loads(raw):
        if volume.get('Name','').startswith(project):
            size=volume.get('Size','0B').replace('B','').strip()
            for suffix,factor in (('k',1/1024),('M',1.0),('G',1024.0),('T',1024*1024)):
                if size.endswith(suffix):
                    total+=float(size[:-1])*factor
                    break
            else:
                total+=float(size or 0)/(1024*1024)
print(round(total,1))
" "$PROJECT")"
# Steady disk must account for every image the topology pulls, not only the
# publisher image: the supporting database, cache and workflow images live on
# the same 30 GB volume.
IMAGE_MIB="$(compose config --images | sort -u | xargs docker image inspect --format '{{.Size}}' |
  python3 -c '
import sys
total = sum(int(line) for line in sys.stdin if line.strip())
print(round(total / 1024 / 1024, 1))
')"

python3 "$SCRIPT_DIR/resources.py" \
  --samples "$TEMP_ROOT/samples.txt" \
  --volume-mib "${VOLUME_MIB:-0}" \
  --image-mib "$IMAGE_MIB" \
  --startup-seconds "${STARTUP_SECONDS:-0}" \
  --output "$TEMP_ROOT/resources.json" >/dev/null

python3 "$SCRIPT_DIR/verdict.py" \
  --checks "$TEMP_ROOT/checks.json" \
  --drills "$TEMP_ROOT/drills.json" \
  --resources "$TEMP_ROOT/resources.json" \
  --version "$VERSION" \
  --output "$RUN_ROOT/evidence.json"

EVIDENCE_FILE="$RUN_ROOT/evidence.json"
EVIDENCE_BYTES="$(wc -c <"$EVIDENCE_FILE" | tr -d ' ')"
[ "$EVIDENCE_BYTES" -le "$ARTIFACT_FILE_LIMIT_BYTES" ] ||
  dholbeat_die "evidence exceeded ${ARTIFACT_FILE_LIMIT_BYTES} bytes: $EVIDENCE_FILE"
dholbeat_assert_absent_from_evidence "$RUN_ROOT" "$FIXTURE_PASSWORD_PREFIX"

printf 'evidence: %s\n' "$RUN_ROOT/evidence.json"
