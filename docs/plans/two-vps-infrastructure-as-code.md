# Two-VPS infrastructure-as-code plan

**Decision date:** 2026-08-13

**Status:** Founder-approved topology; round-one feedback applied; final cross-review pending; implementation is a separate lane

**Hosting budget:** two VPSDime Linux6GB services under the existing customer account, $7/month each ($14/month total), before tax or optional add-ons

## Decision

Use two independent VPSDime servers, managed from this single Git repository:

| Host | Workloads | Resources | Reason for boundary |
| --- | --- | ---: | --- |
| `core-1` | Paperclip under configuration-parity IaC, n8n, bounded Hermes worker, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Protect the existing application and keep approval/research automation together. |
| `publish-1` | Selected publisher stack, its databases/caches/workflow engine, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Isolate the newer publisher and its update/resource risks from Paperclip. |

Buy the second service through the **existing VPSDime account**, preferably in a different available datacenter from `core-1`. Do not create a second customer identity. VPSDime supports adding another VPS to one account, while a related account does not create another refund entitlement. [VPSDime deployment](https://vpsdime.com/knowledgebase/client-area/deploy/deploying-a-new-vps), [VPSDime terms](https://vpsdime.com/tos)

The two hosts are not a cluster and do not form one 8-vCPU/12-GB computer. Each process remains constrained by its host's 6 GB RAM and 30 GB disk, and VPSDime's Linux CPU is shared. The gain is two scheduling envelopes and two failure domains, not eight dedicated cores. [VPSDime Linux plans](https://vpsdime.com/linux-vps)

### Supersedes the earlier single-host recommendation

The [2026-08-12 social-media plan review](../reviews/ai-social-media-plan-review-2026-08-12.md) recommended upgrading the existing server to one Linux12GB host because that was the simplest $14 topology and met Postiz's recommended 8 GB/50 GB sizing. On 2026-08-13, the founder instead approved two Linux6GB services at the same initial $14 total: one preserves a scheduling and failure boundary around Paperclip, n8n and Hermes, while the other makes the newer publisher independently replaceable and upgradeable. The trade-off is a second OS to manage and a 6 GB/30 GB publisher canary below Postiz's recommendation.

This plan supersedes only that review's hosting topology, Paperclip-adoption workflow and directly conflicting budget statements. Its two-brand launch, publisher alternatives, research constraints and generation-cost findings remain inputs. `README.md` §5 and §9 record this topology as the current repository source of truth. The second $7 service purchase is founder-approved; there is no additional pre-purchase decision gate.

## Why Ansible is the primary tool

Choose **Ansible Core plus pinned Docker Compose** for host and service configuration. Keep **OpenTofu optional and narrowly scoped to supported external APIs**, initially Cloudflare DNS/Tunnel/Access and R2 bucket metadata if those resources are brought under code.

| Tool | Decision | What it owns | Why |
| --- | --- | --- | --- |
| Ansible Core | **Primary** | OS baseline, users/SSH, firewall, Docker repository/engine/plugin, directories, systemd units/timers, Compose deployment, backup jobs, monitoring, health verification and migration orchestration | It works over ordinary SSH against both current and replacement hosts, is idempotent, supports check/diff modes, and does not require an agent on the VPS. |
| Docker Compose v2 | **Runtime contract** | The complete service definitions, networks, volumes, health checks, resource limits, image digests and logging limits on each single host | It matches the upstream Postiz deployment model and keeps each application portable to any Docker-capable Ubuntu host. Ansible's `community.docker.docker_compose_v2` module manages it directly. [Ansible Compose module](https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_compose_v2_module.html) |
| OpenTofu | **Optional phase 2** | Only providers with supported APIs: Cloudflare DNS, tunnels, Access and R2 bucket declarations | VPSDime's documented deployment flow is a customer-panel workflow; no supported public VPSDime provider/API was found. OpenTofu cannot safely declare the VPS lifecycle without a provider. Cloudflare does publish supported IaC interfaces. [Cloudflare Tunnel IaC](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/deployment-guides/terraform/), [R2 bucket resource](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket) |
| Docker Swarm/Kubernetes | **Reject for two hosts** | Nothing | Two nodes do not provide a sound quorum, do not pool RAM, and make stateful publisher recovery harder. Docker recommends more than two and an odd manager count for fault tolerance. [Docker Swarm quorum](https://docs.docker.com/engine/swarm/admin_guide/) |
| A web control panel (Coolify, Portainer, etc.) | **Reject as authority** | Optional read-only convenience only | It would create a second mutable configuration surface. Git plus Ansible must remain authoritative. |

The intentionally manual boundary is small: order/reinstall/resize a VPS in the VPSDime panel, choose Ubuntu 24.04 LTS, attach the bootstrap SSH public key, and record its stable hostname and role in the committed inventory. A temporary IP override may remain local only while old and replacement hosts coexist. Everything after first SSH must be reproducible from code. If VPSDime later publishes a supported API/provider, add a reviewed OpenTofu module rather than browser automation.

## What “reproducible” means

Rebuilding is a three-source operation, not “Git contains the whole server”:

1. **Git stores desired state and approved ciphertext:** playbooks, roles, Compose files, version/image locks, public configuration templates, n8n workflow exports, systemd definitions, verification scripts, runbooks, the `.sops.yaml` policy and values-only SOPS+age-encrypted `*.sops.yml` files.
2. **The password manager is the root-access authority:** it stores the founder and break-glass age private keys, host bootstrap key and provider recovery logins. The `SOPS_AGE_KEY` environment variable supplies an age private key at apply time; no private key or plaintext `.env` enters Git.
3. **Encrypted off-site backups store mutable state:** fresh database dumps and the small set of non-database application data that cannot be regenerated. Restic is the only backup-retention authority.

A replacement host is complete only after Ansible converges, encrypted state is restored, external OAuth/tunnel callbacks are verified and the service passes its acceptance test. Git alone cannot reproduce PostgreSQL rows, OAuth grants or media objects; pretending otherwise would be either incomplete or unsafe.

## Target repository layout

Implement the following without creating a second infrastructure repository:

```text
infra/
  README.md
  ansible.cfg
  requirements.yml                 # exact tested collection versions
  secrets/
    core.sops.yml                  # values encrypted by SOPS; metadata required
    publisher.sops.yml
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
    publisher/                      # selected Postiz or Mixpost implementation
  tofu/                             # optional supported-provider phase
    cloudflare/
stack/
  paperclip/                        # imported desired config; parity is invariant
  n8n/
  hermes/
  publisher/                        # only the selected publisher stack is enabled
n8n/
  workflows/                        # credential-free JSON exports
scripts/
  infra-check
  infra-plan
  infra-apply
  infra-verify
  infra-restore-drill
.sops.yaml                          # path policy + founder/break-glass recipients
```

Commit the production inventory, host roles and stable public DNS names so a lost laptop is not the only map of the system. Public IP addresses may also be committed when a hostname is unavailable; they are endpoints, not credentials. Secret values may be committed only as SOPS+age ciphertext in `infra/secrets/*.sops.yml` under the committed `.sops.yaml` policy. Never commit plaintext secrets, private age/SSH keys, tunnel tokens in plaintext, `.env`, Ansible Vault files/passwords, OpenTofu state, plan files, generated media or application data.

## Configuration model

### Shared baseline role

Both hosts receive the same deterministic baseline:

- Ubuntu 24.04 LTS assertion; fail rather than silently applying to an unknown OS.
- A named administration user with `sudo`, key-only SSH, disabled password authentication and a separately tested break-glass path through the VPSDime console.
- Time synchronization, unattended security updates with a declared reboot policy, persistent journald limits, logrotate and a fixed timezone policy (UTC on hosts; business timezone passed to applications).
- Host firewall with default-deny inbound. Expose SSH only through an explicit allowlist or a documented access path; applications bind to loopback unless an inbound webhook truly requires public access.
- Docker Engine and Compose plugin from a declared repository, with tested version ranges and bounded Docker JSON logs. Pin application images by digest; Renovate or a scheduled dependency PR may propose digest updates, but production never follows `latest` implicitly.
- Disk, RAM, OOM, container-health, certificate/tunnel and backup-age monitoring. Alerts go to a dedicated operational channel, not a publishing-approval callback.
- Restic client and one locked systemd timer per host. Backup jobs must not overlap Hermes browser work, publisher upgrades or each other.

Run baseline changes serially (`serial: 1`) and retain out-of-band console access. Firewall and SSH handlers must verify a second connection before ending the existing session.

### `core-1`: adopt Paperclip by parity, then add automation

Paperclip need not be an untouchable snowflake. The invariant is that its effective configuration and image digest remain unchanged during IaC adoption and that it returns healthy after convergence. Container recreation is permitted in a planned restart window:

1. Capture a redacted effective manifest: `docker compose config`, environment-variable names plus value hashes, bind mounts/volumes, resolved image digest, restart policy, systemd/cron jobs, tunnel routes, backup inputs and expected health response.
2. Take a fresh application-consistent database dump, snapshot required state with restic and prove a disposable restore **before** the first mutating convergence.
3. Express the captured desired state in `stack/paperclip/` and SOPS-encrypted variables. The `paperclip_guard` role compares the rendered candidate with the captured manifest and fails on any unexplained difference before applying it.
4. Converge in a planned restart window. Ansible may recreate the container, but may not move its data, alter the effective config or change/upgrade the captured image digest during adoption.
5. Recapture the same manifest after convergence, compare it with the before snapshot and verify application health. Store only redacted manifests and hashes in CI artifacts; rotate a secret if its value is ever exposed.
6. Replace the conflicting tar/cleanup jobs only after the restore test. Back up a fresh database dump, Compose/config and required non-database state directly to a private encrypted R2 restic repository. Keep at most one local latest dump; use `forget --keep-daily 7 --keep-weekly 4 --prune`, followed by `check`. Do not apply an R2 object-expiry lifecycle to the restic bucket.
7. Deploy n8n in its own Compose project, network, volume/database credentials and directory. Start production concurrency at one; cap execution and binary retention; export credential-free workflow JSON to Git.
8. Deploy Hermes as a separate, planned noncritical worker with a narrow workspace, approximately 2 GB memory ceiling and one concurrent job. No Docker socket, host root, Paperclip mounts, host network or approval/publishing credentials. n8n remains the deterministic authority, and no deadline, approval or publish path depends on Hermes.

Live baseline recorded 2026-08-13 before this plan: 4 vCPU, 6 GiB RAM, approximately 1.0 GiB used/5.0 GiB available, no swap, root disk 17/30 GB used, Paperclip approximately 698 MiB RAM, and all w3exam containers approximately 225 MiB. Re-measure after w3exam migration and backup cleanup; these are point-in-time values, not capacity guarantees.

### `publish-1`: keep the selected publisher stack together

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

Postiz remains a default, not a closed decision. If the founder selects Mixpost, the host boundary, inventory, baseline, tunnel, R2/restic, monitoring, approval contract and replacement-host workflow remain unchanged; only the publisher role, Compose project and application-aware dump/restore adapter change. Mixpost's documented stack uses PHP, MySQL, Redis, queue workers and FFmpeg and does not list Temporal, so it must be re-benchmarked rather than assumed to share Postiz's resource profile. Do not deploy both publishers simultaneously. [Mixpost server requirements](https://docs.mixpost.app/server/)

## Network and failure model

The services integrate at application boundaries:

```text
Founder -> Cloudflare Access -> team.chayan.me -> Paperclip
Founder -> Cloudflare Access -> n8n / selected publisher UIs
Telegram -> HTTPS webhook -> n8n -> approval state/database
n8n -> Cloudflare Access service token + scoped app token -> selected publisher API
selected publisher -> social-provider APIs
selected publisher -> public media R2 bucket
core-1 and publish-1 -> separate encrypted restic repositories in private R2
external monitor -> public health endpoints
```

### Public namespace and Zero Trust policy

`chayan.me` is the only public application namespace for workloads on these
two hosts. Paperclip already uses `team.chayan.me`; preserve that hostname and
capture its current DNS/origin route and any existing Access policy during the
parity adoption. Import compliant resources; if the route or policy does not
yet meet this section, converge it without renaming Paperclip. A Paperclip
hostname change is out of scope unless the founder approves it separately.

The initial human-facing hostname map is:

| Host | Interface | Hostname | Edge access |
| --- | --- | --- | --- |
| `core-1` | Paperclip | `team.chayan.me` (existing) | Cloudflare Access identity policy |
| `core-1` | n8n administration | `n8n.chayan.me` | Cloudflare Access identity policy |
| `publish-1` | Selected publisher administration and API | `publish.chayan.me` | Cloudflare Access identity policy for people; a separately scoped Access service token for n8n API calls |

Cloudflare documents service tokens specifically for automated callers of an
Access-protected self-hosted application; each token is independently
renewable and revocable. [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)

Every current or future human-facing interface follows the same contract:

- Declare its stable `chayan.me` hostname, owning host, Cloudflare Tunnel route
  and Access application in committed desired state before first deployment.
- Default-deny at Cloudflare Access and allow only the founder or explicitly
  approved identities. Machine callers receive distinct service tokens where
  the protocol supports them; Cloudflare authentication supplements rather
  than replaces application authentication and authorization.
- Bind the origin to loopback or a private container network. The host firewall
  must not expose application HTTP(S) ports, and neither a public IP nor an
  alternate DNS record may bypass the tunnel and Access policy. This follows
  Cloudflare's outbound-only Tunnel firewall model. [Cloudflare Tunnel with a firewall](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)
- Keep one tunnel and tunnel credential per host. A route may not silently
  cross the `core-1`/`publish-1` failure and credential boundary.

Some third-party protocols cannot present a Cloudflare Access credential. A
provider-initiated webhook or OAuth callback, a provider-fetchable R2 media
object, or a minimal external health probe is a machine endpoint, not a public
administration interface. Such an endpoint must still use an explicit
`chayan.me` hostname through Cloudflare, and it must be either a separate
hostname or the narrowest exact path the application supports. Before exposure,
its committed route manifest must name the caller, purpose, allowed methods,
application-level verification (for example webhook signature, OAuth `state`,
signed object URL or monitor secret), Cloudflare WAF/rate limit, data class and
retention owner. Never create an Access bypass for an entire administration
hostname. If the provider cannot support a safely scoped route, stop and ask
the founder rather than exposing it. Cloudflare supports policies scoped to
specific application paths, but its `Bypass` action disables Access controls
and Access logging; any required bypass is therefore an explicit machine-route
exception, not Zero Trust protection. [Cloudflare Access application paths](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/), [Cloudflare Access policy actions](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)

No cross-host NFS, shared Docker volume, overlay network, database connection or two-node scheduler is permitted. This makes a server loss local: `publish-1` failure pauses scheduling but Paperclip/research/approval remain available; `core-1` failure does not corrupt publisher state, although new approvals pause. Already scheduled publisher jobs must behave according to a documented approval-state contract.

Use distinct Cloudflare tunnels, service tokens and R2 credentials per host/purpose. A compromise of the public publisher must not reveal Paperclip secrets or the backup credential for `core-1`.

## Secrets and access workflow

The hard rule is **no plaintext secrets in Git**. Values-only SOPS+age ciphertext may be committed as `infra/secrets/*.sops.yml` only under a reviewed `.sops.yaml` policy and CI metadata checks. This replaces password-manager-to-temporary-file materialization as the primary application-secret path; Ansible Vault is not used.

Required flow:

1. Commit `.sops.yaml` with a `creation_rules` path expression limited to `infra/secrets/.*\.sops\.yml` and both the founder and break-glass **public** age recipients. Keep the corresponding private keys only in the password manager.
2. Encrypt only YAML values with SOPS. Each encrypted file must retain SOPS metadata, its integrity MAC and both approved recipients; adding a plain file under `infra/secrets/` is a CI failure. The repository secret catalog records each name, owner, consumer and rotation trigger without duplicating its value.
3. At apply time, export the selected private key from the password manager to `SOPS_AGE_KEY` in controller memory. Pinned `community.sops` integration decrypts variables for Ansible; tasks render root-owned `0600` host environment files with `no_log: true` and `diff: false`. Do not write a decrypted workspace copy. [SOPS age configuration](https://github.com/getsops/sops#encrypting-using-age), [Ansible `community.sops`](https://docs.ansible.com/projects/ansible/latest/collections/community/sops/)
4. Unset `SOPS_AGE_KEY` after the run and verify logs/artifacts contain neither plaintext nor decrypted diffs. Rotate any value ever printed. The password manager remains authoritative for private age keys, bootstrap SSH keys and provider recovery logins.
5. If an age private key leaks, remove its recipient and add a replacement, but also rotate **every underlying secret it could decrypt**. Re-encryption alone is insufficient because old ciphertext remains recoverable from Git history with the leaked key.

OpenTofu state, if phase 2 is used, goes to an encrypted remote backend with locking; backend credentials are supplied through environment variables because plans/state may contain sensitive data. Production application secrets should not pass through OpenTofu. [OpenTofu backend security](https://opentofu.org/docs/language/settings/backends/configuration/)

## CI and change workflow

Every infrastructure pull request should run read-only checks:

- YAML lint and `ansible-lint`.
- `ansible-playbook --syntax-check` for every playbook.
- Secret scanning plus policy checks that `.env`, private keys, Ansible Vault data, state and plan files are absent; every file under `infra/secrets/` is named `*.sops.yml`, carries valid SOPS metadata/MAC and lists the policy's required age recipients.
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
| Publisher database/config | 24 hours initially | 2 hours | Use the selected application's dump adapter; increase frequency after observing scheduled-post risk. |
| Public media | Lifecycle-dependent | Re-upload/regenerate or restore selected source | Published assets should not make the root disk authoritative. |

Perform a disposable restore drill quarterly and after any database/topology upgrade. A successful `restic check` alone is not a restore test.

## Rollout plan

### Phase 0 — repository and evidence

- Merge this founder-approved topology after final cross-review.
- Capture a redacted current-state manifest from `core-1`: packages, Compose config, mounts, systemd/cron, firewall, tunnel routes, backup inputs and expected health endpoints.
- Capture `team.chayan.me` as Paperclip's current stable hostname, audit its
  current DNS/origin route and Access state, and record the complete desired
  public-hostname/Access-policy map without changing live DNS.
- Define inventory/group-variable schemas, the `.sops.yaml` policy, required age recipients, secret catalog and data classification before writing mutating playbooks.
- Pin the Ansible execution environment/collection versions so the controller is reproducible and does not depend on the founder laptop's global Python installation.

**Exit:** CI validates an empty skeleton and rejects a non-SOPS file in the secrets path; the Paperclip guard can capture and compare redacted effective manifests without changing the host.

### Phase 1 — make `core-1` declarative with Paperclip parity

- Apply the shared baseline in small tags with `serial: 1`.
- Capture Paperclip's redacted effective manifest, image digest and health baseline; express that state in Git and compare before convergence.
- Install restic and complete a disposable restore before the first mutating Paperclip converge or retirement of legacy backup jobs.
- Converge Paperclip in a planned restart window; recreation is permitted, but a config/digest mismatch fails the run. Recapture, rediff and health-check afterward.
- Verify that unauthenticated requests to `team.chayan.me` stop at Cloudflare
  Access, authenticated requests reach Paperclip, and no origin address or
  alternate hostname bypasses the policy.
- Remove w3exam only through its separately approved migration/change window.
- Deploy n8n at `n8n.chayan.me` behind its own Access application, measure
  24–72-hour peaks, then deploy bounded Hermes and measure again.

**Exit:** a second Ansible run reports no unexpected changes; Paperclip's before/after effective-config diff is empty, its image digest is unchanged and it is healthy; backup restore passes; root disk remains below 70%; seven-day peak RAM remains below 4.5 GB with no OOM.

### Phase 2 — provision and configure `publish-1`

- Exercise the founder's approved purchase by manually adding a second monthly Linux6GB service to the existing account, ideally in a different available datacenter, using key-only bootstrap access.
- Run the full Ansible bootstrap; configure a distinct tunnel and R2 credentials.
- Close the existing Postiz-vs-Mixpost decision, then deploy only the selected complete publisher stack with R2 media, automatic registration disabled after founder creation and no public state-service ports.
- Expose the publisher at `publish.chayan.me` behind Access, then connect both
  brand workspaces and n8n through its public HTTPS API using both a scoped
  Cloudflare Access service token and a scoped application credential.

**Exit:** immediate/scheduled/cancel/delete/token-refresh tests pass for both brands; duplicate-post kill switch works; backup/restore passes; seven-day peak RAM is below 4.5 GB; steady disk is below 18 GB and an image update leaves at least 8 GB free.

### Phase 3 — optional supported-provider OpenTofu

- Import existing Cloudflare DNS/tunnel/Access/R2 declarations rather than recreate them.
- Bootstrap remote encrypted/locked state separately; never have OpenTofu manage the VPSDime services until a supported provider exists.
- Require reviewed plans and manual applies.

**Exit:** a no-change plan is clean, imports match production, state recovery is documented and no secret is committed or exposed in CI artifacts.

### Phase 4 — prove portability

- Rebuild each role in a disposable compatible VPS/VM from Git/SOPS ciphertext plus a password-manager age key and restic data.
- Time the exercise, close all undocumented steps and record the tested Git tag and snapshot IDs.

**Exit:** both host roles can be rebuilt without copying an old root filesystem or consulting shell history.

## Capacity and escalation

Two Linux6GB hosts remain the $14 target only while each host independently meets its guardrails. Aggregate free memory on the other machine cannot rescue a constrained process.

Upgrade **only `publish-1` to Linux12GB** if any of these persist after log/media pruning and scheduling adjustments:

- seven-day peak RAM exceeds 4.5 GB, any OOM occurs, or the selected publisher cannot update inside its 6 GB limit;
- steady disk exceeds 18 GB, warning reaches 21 GB, or an update cannot preserve 8 GB free;
- publisher latency/retries correlate with its host's cgroup CPU saturation rather than provider latency.

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

The two-host design costs the same as one Linux12GB host but adds one OS, tunnel, backup job and monitoring target. IaC contains that management cost; it does not eliminate it. The founder selected that trade-off for isolation and independent upgrade/replacement boundaries.

The broader review estimates $7–17/month for two-brand AI, generation and storage without paid voice or X. Cost reconciliation is therefore:

| Scenario | VPS cash (R2 is in the baseline) | Additional cash from today's already-paid $7 host | Complete monthly cash |
| --- | ---: | ---: | ---: |
| Initial `core-1` $7 + new `publish-1` $7 | $14 | $7 new host + $7–17 baseline = **$14–24** | **$21–31** |
| Escalated `core-1` $7 + `publish-1` $14 | $21 | $14 infra increase + $7–17 baseline = **$21–31** | **$28–38** |

The initial additional $14–24 remains inside the repository's $10–25 marginal target. A publisher upgrade can exceed it by up to $6/month and therefore requires a fresh founder cost decision, a documented offset elsewhere, or comparison with the one-host/managed alternatives. The original one-Linux12GB topology would remain $14 infrastructure and cheaper than an escalated $21 two-host topology, but it gives up the selected failure and scheduling boundary.

## Risks and explicit non-goals

- **The publisher may outgrow 6 GB/30 GB.** Postiz's official recommendation is higher, and Mixpost needs its own measured baseline. The canary and publisher-only upgrade path are mandatory, not optional polish.
- **This is isolation, not provider HA.** Two VPSDime services still share one vendor/account and may share regional infrastructure. Different datacenters reduce correlated host/location failure but not account, billing or provider failure.
- **Paperclip parity adoption is the riskiest IaC step.** Capture, back up, restore-test and diff before convergence; recreate only in a planned window; then prove the effective config and image digest are unchanged and health has returned.
- **No automatic production apply.** A malicious or mistaken Git change must not immediately reconfigure both hosts.
- **No secret completeness claim.** Recovery depends on Git/SOPS ciphertext, a password-manager age key and restic access, tested separately from GitHub access.
- **No two-node orchestration or distributed database.** Cross-host integration remains HTTPS/R2 only.
- **No routine manual configuration.** Emergency changes are temporary drift and must be reconciled into Git.

## Acceptance criteria for the implementation PR

The subsequent implementation is ready for production review only when:

1. A clean Ubuntu 24.04 test host can reach converged state from the pinned controller environment and documented secret inputs.
2. Running `site.yml` twice produces no second-run changes except explicitly documented probes.
3. Paperclip's effective configuration is unchanged by a before/after parity diff, its image digest is unchanged, it is healthy after convergence, and its backup restores in a disposable environment; container recreation is permitted in the planned restart window.
4. Each service has a version/digest, health check, restart policy, log bound, data classification and backup/retention owner.
5. No plaintext secret, private key, `.env`, state file, plan file, database or generated media is tracked; every tracked file under the secrets path is values-only SOPS+age ciphertext with policy-required metadata and recipients.
6. Both hosts remain independently operable when the other is unreachable.
7. The selected publisher passes the two-brand seven-day canary within the 6 GB/30 GB thresholds, including its application-specific publish/restore tests, or the plan records a measured upgrade to `publish-1`.
8. A full replacement-host drill succeeds from Git/SOPS ciphertext + a password-manager age key + restic, and the exact manual VPSDime bootstrap boundary is documented.
9. Paperclip remains at `team.chayan.me`; every human-facing interface is a
   declared `chayan.me` hostname behind the correct host's Cloudflare Tunnel
   and default-deny Access policy, and no application origin is reachable by
   public IP or alternate DNS.
10. Every non-human public route has a committed least-privilege manifest and
    verification test; no whole administration hostname has an Access bypass.
