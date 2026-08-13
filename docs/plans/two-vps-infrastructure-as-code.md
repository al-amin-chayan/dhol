# Two-VPS infrastructure-as-code plan

**Decision date:** 2026-08-13

**Status:** Proposed for cross-review; implementation is a separate lane

**Hosting budget:** two VPSDime Linux6GB services under the existing customer account, $7/month each ($14/month total), before tax or optional add-ons

## Decision

Use two independent VPSDime servers, managed from this single Git repository:

| Host | Workloads | Resources | Reason for boundary |
| --- | --- | ---: | --- |
| `core-1` | Paperclip unchanged, n8n, bounded Hermes worker, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Protect the existing application and keep approval/research automation together. |
| `publish-1` | Complete official Postiz stack, its databases/caches/workflow engine, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Isolate the newer publisher and its update/resource risks from Paperclip. |

Buy the second service through the **existing VPSDime account**, preferably in a different available datacenter from `core-1`. Do not create a second customer identity. VPSDime supports adding another VPS to one account, while a related account does not create another refund entitlement. [VPSDime deployment](https://vpsdime.com/knowledgebase/client-area/deploy/deploying-a-new-vps), [VPSDime terms](https://vpsdime.com/tos)

The two hosts are not a cluster and do not form one 8-vCPU/12-GB computer. Each process remains constrained by its host's 6 GB RAM and 30 GB disk, and VPSDime's Linux CPU is shared. The gain is two scheduling envelopes and two failure domains, not eight dedicated cores. [VPSDime Linux plans](https://vpsdime.com/linux-vps)

## Why Ansible is the primary tool

Choose **Ansible Core plus pinned Docker Compose** for host and service configuration. Keep **OpenTofu optional and narrowly scoped to supported external APIs**, initially Cloudflare DNS/Tunnel/Access and R2 bucket metadata if those resources are brought under code.

| Tool | Decision | What it owns | Why |
| --- | --- | --- | --- |
| Ansible Core | **Primary** | OS baseline, users/SSH, firewall, Docker repository/engine/plugin, directories, systemd units/timers, Compose deployment, backup jobs, monitoring, health verification and migration orchestration | It works over ordinary SSH against both current and replacement hosts, is idempotent, supports check/diff modes, and does not require an agent on the VPS. |
| Docker Compose v2 | **Runtime contract** | The complete service definitions, networks, volumes, health checks, resource limits, image digests and logging limits on each single host | It matches the upstream Postiz deployment model and keeps each application portable to any Docker-capable Ubuntu host. Ansible's `community.docker.docker_compose_v2` module manages it directly. [Ansible Compose module](https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_compose_v2_module.html) |
| OpenTofu | **Optional phase 2** | Only providers with supported APIs: Cloudflare DNS, tunnels, Access and R2 bucket declarations | VPSDime's documented deployment flow is a customer-panel workflow; no supported public VPSDime provider/API was found. OpenTofu cannot safely declare the VPS lifecycle without a provider. Cloudflare does publish supported IaC interfaces. [Cloudflare Tunnel IaC](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/deployment-guides/terraform/), [R2 bucket resource](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket) |
| Docker Swarm/Kubernetes | **Reject for two hosts** | Nothing | Two nodes do not provide a sound quorum, do not pool RAM, and make stateful Postiz recovery harder. Docker recommends more than two and an odd manager count for fault tolerance. [Docker Swarm quorum](https://docs.docker.com/engine/swarm/admin_guide/) |
| A web control panel (Coolify, Portainer, etc.) | **Reject as authority** | Optional read-only convenience only | It would create a second mutable configuration surface. Git plus Ansible must remain authoritative. |

The intentionally manual boundary is small: order/reinstall/resize a VPS in the VPSDime panel, choose Ubuntu 24.04 LTS, attach the bootstrap SSH public key, and record the resulting IP in the local inventory. Everything after first SSH must be reproducible from code. If VPSDime later publishes a supported API/provider, add a reviewed OpenTofu module rather than browser automation.

## What “reproducible” means

Rebuilding is a three-source operation, not “Git contains the whole server”:

1. **Git stores desired state:** playbooks, roles, Compose files, version/image locks, public configuration templates, n8n workflow exports, systemd definitions, verification scripts and runbooks.
2. **The password manager stores secrets:** host bootstrap key, application secrets, database passwords, OAuth client credentials, Cloudflare/R2 credentials and restic repository password. Only `.env.example` files and variable names enter Git.
3. **Encrypted off-site backups store mutable state:** fresh database dumps and the small set of non-database application data that cannot be regenerated. Restic is the only backup-retention authority.

A replacement host is complete only after Ansible converges, encrypted state is restored, external OAuth/tunnel callbacks are verified and the service passes its acceptance test. Git alone cannot reproduce PostgreSQL rows, OAuth grants or media objects; pretending otherwise would be either incomplete or unsafe.

## Target repository layout

Implement the following without creating a second infrastructure repository:

```text
infra/
  README.md
  ansible.cfg
  requirements.yml                 # exact tested collection versions
  inventories/
    production/
      hosts.yml                    # committed stable hostnames/roles; no secrets
      group_vars/
        all.yml
        core.yml
        publisher.yml
  playbooks/
    bootstrap.yml
    core.yml
    publisher.yml
    site.yml
    backup.yml
    restore-core.yml
    restore-publisher.yml
    verify.yml
  roles/
    base/
    docker/
    firewall/
    cloudflared/
    monitoring/
    restic/
    paperclip_guard/
    n8n/
    hermes/
    postiz/
  tofu/                             # optional supported-provider phase
    cloudflare/
stack/
  paperclip/                        # imported desired config; app remains unchanged
  n8n/
  hermes/
  postiz/
n8n/
  workflows/                        # credential-free JSON exports
scripts/
  infra-check
  infra-plan
  infra-apply
  infra-verify
  infra-restore-drill
```

Commit the production inventory, host roles and stable public DNS names so a lost laptop is not the only map of the system. Public IP addresses may also be committed when a hostname is unavailable; they are endpoints, not credentials. Keep only secret values and machine-local overrides in ignored files or injected environment variables. Never commit private keys, tunnel tokens, `.env`, Ansible Vault password files, OpenTofu state, plan files, generated media or application data.

## Configuration model

### Shared baseline role

Both hosts receive the same deterministic baseline:

- Ubuntu 24.04 LTS assertion; fail rather than silently applying to an unknown OS.
- A named administration user with `sudo`, key-only SSH, disabled password authentication and a separately tested break-glass path through the VPSDime console.
- Time synchronization, unattended security updates with a declared reboot policy, persistent journald limits, logrotate and a fixed timezone policy (UTC on hosts; business timezone passed to applications).
- Host firewall with default-deny inbound. Expose SSH only through an explicit allowlist or a documented access path; applications bind to loopback unless an inbound webhook truly requires public access.
- Docker Engine and Compose plugin from a declared repository, with tested version ranges and bounded Docker JSON logs. Pin application images by digest; Renovate or a scheduled dependency PR may propose digest updates, but production never follows `latest` implicitly.
- Disk, RAM, OOM, container-health, certificate/tunnel and backup-age monitoring. Alerts go to a dedicated operational channel, not a publishing-approval callback.
- Restic client and one locked systemd timer per host. Backup jobs must not overlap Hermes browser work, Postiz upgrades or each other.

Run baseline changes serially (`serial: 1`) and retain out-of-band console access. Firewall and SSH handlers must verify a second connection before ending the existing session.

### `core-1`: preserve Paperclip, add automation safely

Paperclip remains functionally unchanged, but its host-side desired configuration must stop being an undocumented snowflake:

1. Inventory the current Compose file, environment-variable names, mount paths, systemd/cron jobs, tunnel routing and backup inputs. Generate a redacted drift report before adopting anything.
2. Import only the desired Compose/config templates into `stack/paperclip/`; put values in the password manager and the host's root-readable environment file.
3. Add a `paperclip_guard` role that asserts the expected existing container, mount and database path before any change. The first Ansible run is **adopt-only**: no Paperclip recreate, volume move, image change or automatic pruning.
4. Replace the conflicting tar/cleanup jobs only after a restic snapshot and disposable restore pass. Back up a fresh database dump, Compose/config and required non-database state directly to a private encrypted R2 repository. Keep at most one local latest dump; use `forget --keep-daily 7 --keep-weekly 4 --prune`, followed by `check`. Do not apply an R2 object-expiry lifecycle to the restic bucket.
5. Deploy n8n in its own Compose project, network, volume/database credentials and directory. Start production concurrency at one; cap execution and binary retention; export credential-free workflow JSON to Git.
6. Deploy Hermes as a separate, planned worker with a narrow workspace, approximately 2 GB memory ceiling and one concurrent job. No Docker socket, host root, Paperclip mounts, host network or approval/publishing credentials. n8n remains the deterministic authority.

Live baseline recorded 2026-08-13 before this plan: 4 vCPU, 6 GiB RAM, approximately 1.0 GiB used/5.0 GiB available, no swap, root disk 17/30 GB used, Paperclip approximately 698 MiB RAM, and all w3exam containers approximately 225 MiB. Re-measure after w3exam migration and backup cleanup; these are point-in-time values, not capacity guarantees.

### `publish-1`: keep the complete Postiz stack together

Deploy the maintained official Postiz Compose topology as one host-local unit: Postiz application, PostgreSQL, Redis, Temporal and its required state services. Do not stretch its database, Redis or Temporal across `core-1`, and do not expose their ports publicly. Postiz documents a 2-vCPU/2-GB/20-GB supported floor for light all-in-one use, with 4 vCPU/8 GB/50 GB recommended; therefore Linux6GB is a measured canary, not guaranteed headroom. [Postiz requirements](https://docs.postiz.com/installation/system-requirements)

Required controls:

- Use prebuilt upstream images pinned by digest; do not build Postiz on the 6 GB server.
- Store provider-fetchable media in a dedicated public R2 media bucket. Apply expiry only to this media bucket, never to the private restic repository.
- Persist databases and required workflow state on local named/bind volumes with explicit ownership. Back them up through application-consistent dumps plus restic, not by copying live database directories.
- Bind Postiz UI/API to loopback and publish it through its own Cloudflare tunnel/hostname. Keep Temporal UI disabled or private.
- Add health checks and startup ordering, but do not confuse Compose `depends_on` with disaster recovery.
- Bound container logs, PostgreSQL logs, Temporal history/visibility retention and temporary uploads. Disk growth without a declared retention owner fails CI/review.
- Give n8n only the Postiz HTTPS API URL and scoped API credential. Do not join Docker networks across servers and do not expose a private control port merely to imitate a LAN.
- Enforce the repository's human-approval rule at the integration boundary: n8n may create or schedule a Postiz job only when the current content hash has a recorded founder approval in the correct brand channel. Editing invalidates approval. Hermes never receives the Postiz credential, and neither Postiz nor a retry worker may turn an unapproved draft into a scheduled post.

## Network and failure model

The services integrate at application boundaries:

```text
Founder -> Cloudflare Access -> n8n / Postiz UIs
Telegram -> HTTPS webhook -> n8n -> approval state/database
n8n -> HTTPS + scoped token -> Postiz API
Postiz -> social-provider APIs
Postiz -> public media R2 bucket
core-1 and publish-1 -> separate encrypted restic repositories in private R2
external monitor -> public health endpoints
```

No cross-host NFS, shared Docker volume, overlay network, database connection or two-node scheduler is permitted. This makes a server loss local: `publish-1` failure pauses scheduling but Paperclip/research/approval remain available; `core-1` failure does not corrupt the Postiz state, although new approvals pause. Already scheduled Postiz jobs must behave according to a documented approval-state contract.

Use distinct Cloudflare tunnels, service tokens and R2 credentials per host/purpose. A compromise of the public publisher must not reveal Paperclip secrets or the backup credential for `core-1`.

## Secrets and access workflow

The Git repository describes every secret by name, owner, consumer, rotation trigger and recovery location. It contains no value.

Recommended flow:

1. Store authoritative values in the founder's password manager.
2. A local `scripts/infra-materialize-secrets` command reads explicitly exported environment variables or an approved password-manager CLI session and writes temporary `0600` files outside Git.
3. Ansible templates host environment files with `no_log: true`, `diff: false`, owner `root` and mode `0600`.
4. Delete local materialized files after the run. Rotate any value ever printed to logs.

Ansible Vault may encrypt a small bootstrap file in Git only if its decryption key lives elsewhere and recovery is documented. It must not become an excuse to store every OAuth token in repository history. OpenTofu state, if phase 2 is used, goes to an encrypted remote backend with locking; backend credentials are supplied through environment variables because plans/state may contain sensitive data. [OpenTofu backend security](https://opentofu.org/docs/language/settings/backends/configuration/)

## CI and change workflow

Every infrastructure pull request should run read-only checks:

- YAML lint and `ansible-lint`.
- `ansible-playbook --syntax-check` for every playbook.
- Secret scanning and assertions that `.env`, private keys, state and plan files are absent.
- `docker compose config --quiet` for every project using generated non-secret test values.
- Schema tests for inventory/group variables and assertions that every image is digest-pinned, every persistent volume has a backup classification, and every growth path has retention.
- Molecule/container tests for roles that can be tested locally; a disposable Ubuntu VM test for Docker/firewall roles before production use.
- `tofu fmt -check`, `tofu validate`, provider lockfile verification and a saved, reviewed plan only when the optional Cloudflare layer exists.

Production apply is never automatic on merge. The founder runs:

```text
scripts/infra-plan --limit publish-1
scripts/infra-apply --limit publish-1
scripts/infra-verify --limit publish-1
```

`infra-plan` uses Ansible check/diff mode where supported, while suppressing secret diffs. Check mode is a preview, not proof, so a disposable-host convergence test and post-apply verification remain mandatory. [Ansible check/diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

Require a manual Git tag such as `infra-prod-YYYYMMDD-N` after a verified deployment. Store the deployed commit SHA in `/etc/dholbeat-release` on each host and export it to monitoring. Emergency host edits require a follow-up Git commit and convergence run; otherwise the nightly/weekly drift check reports them.

## Migration and disaster-recovery procedure

The design passes the portability goal only if this runbook succeeds on a blank compatible host:

1. Order/reinstall an Ubuntu 24.04 VPS and attach the bootstrap public key.
2. Add its stable hostname/role to the committed production inventory and use a temporary local override only while both old and replacement hosts coexist; keep the old host live.
3. Run `bootstrap.yml`, then the appropriate `core.yml` or `publisher.yml` against only the new host.
4. Restore the latest checked database/config snapshot into newly created volumes. For Paperclip, use its explicit application-aware restore procedure; never copy a running database directory.
5. Run offline verification, then use a temporary hostname or hosts-file entry for an end-to-end test.
6. Quiesce writes/scheduling on the old host, take a final dump/snapshot, restore the delta, and rerun verification.
7. Change Cloudflare tunnel/DNS routing. Keep OAuth callback hostnames stable so provider registrations do not change merely because the IP changed.
8. Observe the old host for late traffic, retain it through the rollback window, and cancel it only after a second off-site snapshot and documented sign-off.

Recovery objectives for the initial plan:

| Workload | Target RPO | Target hands-on rebuild objective | Notes |
| --- | ---: | ---: | --- |
| Paperclip | 24 hours initially | 2 hours | Tighten only if business data changes justify more frequent dumps. |
| n8n/Hermes configuration | Git commit | 1 hour | n8n runtime/approval database follows the core backup schedule. |
| Postiz database/config | 24 hours initially | 2 hours | Increase dump frequency after observing scheduled-post risk. |
| Public media | Lifecycle-dependent | Re-upload/regenerate or restore selected source | Published assets should not make the root disk authoritative. |

Perform a disposable restore drill quarterly and after any database/topology upgrade. A successful `restic check` alone is not a restore test.

## Rollout plan

### Phase 0 — repository and evidence

- Merge this decision after cross-review.
- Capture a redacted current-state manifest from `core-1`: packages, Compose config, mounts, systemd/cron, firewall, tunnel routes, backup inputs and expected health endpoints.
- Define inventory/group-variable schemas, secret catalog and data classification before writing mutating playbooks.
- Pin the Ansible execution environment/collection versions so the controller is reproducible and does not depend on the founder laptop's global Python installation.

**Exit:** CI validates an empty skeleton, and the Paperclip adoption guard can identify drift without changing the host.

### Phase 1 — make `core-1` declarative without restarting Paperclip

- Apply the shared baseline in small tags with `serial: 1`.
- Adopt Paperclip configuration in guard/read-only mode.
- Install restic and complete a disposable restore before retiring legacy backup jobs.
- Remove w3exam only through its separately approved migration/change window.
- Deploy n8n, measure 24–72-hour peaks, then deploy bounded Hermes and measure again.

**Exit:** a second Ansible run reports no unexpected changes; Paperclip remains healthy; backup restore passes; root disk remains below 70%; seven-day peak RAM remains below 4.5 GB with no OOM.

### Phase 2 — provision and configure `publish-1`

- Manually add a second monthly Linux6GB service to the existing account, ideally in a different available datacenter, using key-only bootstrap access.
- Run the full Ansible bootstrap; configure a distinct tunnel and R2 credentials.
- Deploy the complete Postiz stack with R2 media, automatic registration disabled after founder creation and no public state-service ports.
- Connect both brand workspaces and n8n through the public HTTPS API only.

**Exit:** immediate/scheduled/cancel/delete/token-refresh tests pass for both brands; duplicate-post kill switch works; backup/restore passes; seven-day peak RAM is below 4.5 GB; steady disk is below 18 GB and an image update leaves at least 8 GB free.

### Phase 3 — optional supported-provider OpenTofu

- Import existing Cloudflare DNS/tunnel/Access/R2 declarations rather than recreate them.
- Bootstrap remote encrypted/locked state separately; never have OpenTofu manage the VPSDime services until a supported provider exists.
- Require reviewed plans and manual applies.

**Exit:** a no-change plan is clean, imports match production, state recovery is documented and no secret is committed or exposed in CI artifacts.

### Phase 4 — prove portability

- Rebuild each role in a disposable compatible VPS/VM from Git plus password-manager values and restic data.
- Time the exercise, close all undocumented steps and record the tested Git tag and snapshot IDs.

**Exit:** both host roles can be rebuilt without copying an old root filesystem or consulting shell history.

## Capacity and escalation

Two Linux6GB hosts remain the $14 target only while each host independently meets its guardrails. Aggregate free memory on the other machine cannot rescue a constrained process.

Upgrade **only `publish-1` to Linux12GB** if any of these persist after log/media pruning and scheduling adjustments:

- seven-day peak RAM exceeds 4.5 GB, any OOM occurs, or Postiz cannot update inside its 6 GB limit;
- steady disk exceeds 18 GB, warning reaches 21 GB, or an update cannot preserve 8 GB free;
- Postiz latency/retries correlate with its host's cgroup CPU saturation rather than provider latency.

That yields a $21/month topology (`core-1` $7 + `publish-1` $14), 18 GB aggregate RAM, 90 GB aggregate disk and two four-vCPU scheduling envelopes. Upgrade `core-1` independently only if its own measurements cross the same class of thresholds. Do not buy an extra CPU merely because host-level LXC load average looks high; use cgroup CPU/pressure evidence.

## Cost

| Item | Initial monthly cash | Notes |
| --- | ---: | --- |
| Existing Linux6GB `core-1` | $7 | Already committed. |
| New Linux6GB `publish-1` | $7 | Same existing customer account; start monthly. |
| Ansible Core, Docker Compose, OpenTofu | $0 | Open-source software; maintenance time is real but not a license fee. |
| R2 media and encrypted backups | $0–1 expected initially | Separate public media and private backup buckets; set usage alerts. |
| Optional VPSDime nightly backup add-ons | $0 initially | Two add-ons would add $10/month and provide only three-night retention; restic remains authoritative. |
| **Infrastructure total** | **$14–15/month initially** | Before tax/card conversion and the AI/content costs in the broader plan. |

The two-host design costs the same as one Linux12GB host but adds one OS, tunnel, backup job and monitoring target. IaC contains that management cost; it does not eliminate it. The founder should prefer one $14 host if maintaining the second OS repeatedly consumes more value than isolation and the extra scheduling envelope provide.

## Risks and explicit non-goals

- **Postiz may outgrow 6 GB/30 GB.** Its official recommendation is higher. The canary and one-host upgrade path are mandatory, not optional polish.
- **This is isolation, not provider HA.** Two VPSDime services still share one vendor/account and may share regional infrastructure. Different datacenters reduce correlated host/location failure but not account, billing or provider failure.
- **Paperclip adoption is the riskiest IaC step.** Do not let first-run automation recreate the existing application. Observe, assert, back up, restore-test, then converge small pieces.
- **No automatic production apply.** A malicious or mistaken Git change must not immediately reconfigure both hosts.
- **No secret completeness claim.** Recovery depends on password-manager and restic access, tested separately from GitHub access.
- **No two-node orchestration or distributed database.** Cross-host integration remains HTTPS/R2 only.
- **No routine manual configuration.** Emergency changes are temporary drift and must be reconciled into Git.

## Acceptance criteria for the implementation PR

The subsequent implementation is ready for production review only when:

1. A clean Ubuntu 24.04 test host can reach converged state from the pinned controller environment and documented secret inputs.
2. Running `site.yml` twice produces no second-run changes except explicitly documented probes.
3. Paperclip is neither recreated nor upgraded during adoption, and its backup restores in a disposable environment.
4. Each service has a version/digest, health check, restart policy, log bound, data classification and backup/retention owner.
5. No secret, private key, `.env`, state file, plan file, database or generated media is tracked.
6. Both hosts remain independently operable when the other is unreachable.
7. Postiz passes the two-brand seven-day canary within the 6 GB/30 GB thresholds or the plan records a measured upgrade to `publish-1`.
8. A full replacement-host drill succeeds from Git + password manager + restic, and the exact manual VPSDime bootstrap boundary is documented.
