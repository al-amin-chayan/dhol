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
redacted evidence fields plus the interface-binding fields required below.
Store the private identity, strict known-hosts file, and target-specific
inventory only under ignored `.artifacts/`; never pass a password. The
controller requires `--confirm disposable-host`, keeps the repository
read-only, and copies only the declared known-hosts file into its ephemeral
home.
The inventory's `ansible_port` and `baseline_second_connection_port` must name
the same active SSH listener; preflight rejects a mismatch, and the firewall
opens that exact port from the declared controller networks.
Never use a production hostname or IP for this test.

Run it with no hand-added `dholbeat-temporary-ssh` rule, and no other
manually added firewall rule. The role's own `dholbeat-admin-ssh` task must be
what opens the SSH port; a port an operator opened beforehand proves nothing
about the role. The attached `ufw status numbered` output must show exactly one
role-owned admin-SSH rule, on the port actually in use.

The evidence must also include the interface-binding fields:

```sh
ip -o link
ip route show default
sudo iptables -S DHOLBEAT-DOCKER-INGRESS
```

These three are required, not optional. The `-i <iface> -j DROP` line inside
`DHOLBEAT-DOCKER-INGRESS` names an interface, and on its own it does not show
that the interface exists or carries any traffic. Read side by side, `ip -o
link` lists the interfaces the host actually has, the default route names the
one real ingress and egress use, and the iptables ruleset names the one the
DROP targets. Only all three together establish that the Docker ingress policy
binds to the interface carrying the default route rather than to an assumed
name. Addresses and MAC addresses stay redacted as usual; interface names do
not, because they identify nothing about the operator and are the fact under
review.

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
