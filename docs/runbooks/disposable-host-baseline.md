# Disposable shared-host baseline proof

This runbook proves the generic Ubuntu 24.04 baseline without contacting
`core-1`, `publish-1`, a cloud provider, or any production endpoint. It is a
pre-production gate, not permission to bootstrap either VPS.

## Local systemd fixture

Prerequisites are Docker Engine with buildx, `jq`, and `ssh-keygen`. From a
clean checkout, run:

```sh
infra/tests/disposable/run.sh
```

The harness builds the digest-pinned Ubuntu fixture, generates an ephemeral SSH
key, and runs Ansible from the checksum-locked controller. It records:

- first and second convergence transcripts, with zero changes on run two;
- a zero-change check-mode transcript;
- exact resolved Docker package versions and bounded daemon facts;
- default-deny firewall state; and
- container egress, container-to-container connectivity, blocked unlisted
  published ingress, and policy survival across a Docker restart; and
- a negative run proving a failed second administrator connection stops before
  SSH handlers or firewall convergence and leaves bootstrap access usable.

The controller receives the local Docker socket only for the duration of each
fixture command so Ansible can address the exact generated container. Treat
that socket mount as host-root-equivalent: run this harness only on the local
disposable fixture path, never on a shared runner or against a remote daemon.

Evidence goes below ignored `.artifacts/wp05a-disposable-*`. It contains no
private key, secret value, decrypted SOPS data, database, state file, or media.
The harness refuses to overwrite an existing evidence directory and stops when
prior WP-05A evidence exceeds 64 MiB. After attaching the redacted result to
the issue, inspect and remove that run's exact directory; do not retain these
transcripts as a laptop archive.
The temporary key directory is removed on every exit. The fixture containers,
network, and target image carry `io.dholbeat.fixture=wp05a`; cleanup addresses
their exact generated names and never performs a global prune. `--keep-failed`
keeps a failed target for local inspection and prints its exact names.
Every evidence file is capped at 8 MiB and total retained WP-05A evidence is
capped at 64 MiB. The target is built with a dedicated, digest-pinned BuildKit
builder; normal cleanup removes that exact builder and its private cache rather
than pruning shared cache.

The committed inventory pair makes the connection transition explicit:
`inventories/fixtures/hosts.bootstrap.yml` is used only for the first run, and
`inventories/fixtures/hosts.yml` reconnects as the named administrator for the
second run and check mode. Every direct `ansible-playbook` invocation must pass
one of these inventories with `--inventory`; `ansible.cfg` intentionally has no
default target.

The systemd fixture exercises role behavior cheaply, including Docker-in-
Docker with the fixture-only `vfs` storage driver and an isolated firewall
namespace. Production keeps Docker's default storage driver. Before production
use, repeat the same `infra/playbooks/baseline.yml` convergence against an
approved disposable Ubuntu 24.04 VM/VPS with at least 6 GB RAM and 30 GB disk.
Supply its inventory values locally, retain provider-console access, run twice
through the guarded `scripts/controller exec-ssh` command, and attach the same
redacted evidence fields. Store the private identity, strict known-hosts file,
and target-specific inventory only under ignored `.artifacts/`; never pass a
password. The controller requires `--confirm disposable-host`, keeps the
repository read-only, and copies only the declared known-hosts file into its
ephemeral home.
Never use a production hostname or IP for this test.

## Rollback and recovery

For a disposable target, rollback means deleting only that named fixture after
capturing redacted evidence. If access validation fails, do not reload SSH or
enable UFW: use the still-open bootstrap session or declared console, correct
the inventory, and rerun the preflight. The Docker ingress policy has an exact
local rollback command:

```sh
sudo systemctl disable --now dholbeat-docker-firewall.service
sudo /usr/local/sbin/dholbeat-docker-firewall remove
```

The first command prevents reapplication without opening a policy gap during a
normal Docker restart. The second removes only `DHOLBEAT-DOCKER-INGRESS`; it
does not flush UFW, Docker, or unrelated iptables rules. Host baseline rollback
on production belongs to the separately reviewed production-bootstrap issue
and founder-confirmed window.

## Cost

| Component | Monthly cost | Boundary |
| --- | ---: | --- |
| Ansible roles and local fixture | $0 | Open-source software on existing hardware |
| WP-05A disposable VPSDime Linux6GB | $7 for one month | Founder-approved on 2026-08-22; cancel after accepted evidence |
