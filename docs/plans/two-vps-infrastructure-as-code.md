# Two-VPS infrastructure-as-code plan

**Decision date:** 2026-08-13

**Amended:** 2026-08-14 — shared services are multi-project-ready; PoriPati Track-1 is the first external n8n consumer

**Amended:** 2026-08-15 — supported Cloudflare/R2 control-plane resources must
be reproducible from this repository before their production cutover

**Amended:** 2026-08-15 — cross-review hardening adds keyed Paperclip parity,
Git source escrow, registrar delegation verification and a runbooked n8n key
bootstrap fallback

**Status:** Founder-approved topology and multi-project shared-service direction
(confirmed 2026-08-14); base plan merged 2026-08-15; implementation companion
and reproducibility hardening cross-reviewed and awaiting merge; implementation
has not started

**Implementation companion:**
[Two-VPS reproducible implementation plan](two-vps-reproducible-implementation-plan.md)

**Hosting budget:** two VPSDime Linux6GB services under the existing customer account, $7/month each ($14/month total), before tax or optional add-ons

## Decision

Use two independent VPSDime servers whose host/runtime desired state is managed
from this Git repository. Shared tools accept only explicitly registered
founder-owned projects, whose implementations remain at exact reviewed commits
in their owning repositories:

| Host | Workloads | Resources | Reason for boundary |
| --- | --- | ---: | --- |
| `core-1` | Paperclip under configuration-parity IaC, central multi-project n8n, separately managed per-project Hermes profiles under one global resource envelope, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Protect the existing application and keep trusted founder-owned approval/research/growth automation together without sharing product databases or container networks. |
| `publish-1` | Selected multi-project publisher stack, its databases/caches/workflow engine, host monitoring, restic | 4 shared vCPU, 6 GB RAM, 30 GB SSD | Isolate the newer publisher and its update/resource risks from Paperclip while separating each project by organization/workspace and brand connection mapping. |

Buy the second service through the **existing VPSDime account**, preferably in a different available datacenter from `core-1`. Do not create a second customer identity. VPSDime supports adding another VPS to one account, while a related account does not create another refund entitlement. [VPSDime deployment](https://vpsdime.com/knowledgebase/client-area/deploy/deploying-a-new-vps), [VPSDime terms](https://vpsdime.com/tos)

The two hosts are not a cluster and do not form one 8-vCPU/12-GB computer. Each process remains constrained by its host's 6 GB RAM and 30 GB disk, and VPSDime's Linux CPU is shared. The gain is two scheduling envelopes and two failure domains, not eight dedicated cores. [VPSDime Linux plans](https://vpsdime.com/linux-vps)

### Shared services are multi-project-ready from day one

The two hosts provide a reusable platform for trusted founder-owned projects;
they do not turn every resident application into a tenant service. Adding a
project should be a reviewed manifest, scoped secret set, exact source pin and
capacity admission—not a new VPS or a hard-coded branch in shared runtime
code—when the selected tool provides an adequate separation primitive.

| Service | Day-one project contract | Deliberate boundary |
| --- | --- | --- |
| Central n8n | One Community instance; registered consumer manifests, workflow namespaces, separate credentials, source pins and deployment receipts | Logical organization only: consumers share a process, database, encryption key, queue, backup and upgrade window. |
| Hermes Agent | One pinned image/version; one container/service per registered project profile with a distinct `/opt/data` mount, workspace, approved tool set, schedule and credential set | Verified process/filesystem/state-store separation on one host, not a hostile-tenant boundary; one global job and memory envelope protects `core-1`. |
| Selected publisher | One selected stack; separate project organizations/workspaces, brand provider connections, approval state and credential mappings | Application separation must be verified during the Postiz-vs-Mixpost decision; a tool that cannot prevent cross-project writes requires a founder decision to split or replace it. |
| Monitoring, tunnel and backup automation | Shared code with per-host/per-purpose routes, credentials, repositories, labels and retention | Operational automation is shared, but credentials and backup repositories do not cross host or purpose boundaries. |
| Paperclip and project applications/databases | Not shared through this contract | They remain separately owned applications. Shared tools reach only declared, authenticated HTTPS APIs—never product databases or container networks. |

This is a capability contract, not an unlimited capacity promise. Every new
project is admitted only after its resource, data, access and failure impact
fits the thresholds below. A hard isolation requirement, another operator or
untrusted workflow/agent code stops onboarding and triggers a founder decision
about a separate instance or host.

#### n8n: one central runtime with registered consumers

Deploy exactly one production n8n instance on `core-1`. It is the central
workflow runtime for Dholbeat and explicitly registered, founder-owned external
workloads. **PoriPati Track-1 is the first external consumer.** A later w3exam
automation uses the same generic registration path; it does not require an n8n
fork or second administration surface. Do not deploy a PoriPati-specific n8n
container, PostgreSQL database, Caddy proxy or public origin. PoriPati uses the
same `n8n.chayan.me` administration interface and the same bounded execution
service described by this plan.

This shares the runtime, not application ownership:

- Dholbeat owns the n8n image/version, Compose project, database, encryption
  key, host resources, Cloudflare Tunnel/Access policy, monitoring, backups,
  restore procedure and generic consumer tooling.
- Each consumer repository owns its workflow implementation, application API
  contract, business rules, tests and credential-free JSON exports. PoriPati
  Track-1 flows remain canonical in the PoriPati repository and reach the
  product only through its narrow authenticated HTTPS APIs, never its database
  or container network.
- The PoriPati social-media brand remains a normal `brands/` profile. Its
  Track-1 lead/care automation is a separate external product workload and must
  not be hidden inside the brand profile or Dholbeat's social pipeline.

Track-1 therefore depends on the Dholbeat-managed **automation substrate**, but
not on Dholbeat's content, approval or publishing workflows. Free n8n Community
Edition does not provide Projects, workflow/credential sharing, external
secrets or built-in Git environments, so the initial one-instance model is
logical organization for trusted workflows, not a tenant security or resource
boundary. If another operator, untrusted workflow code or a hard isolation
requirement appears, stop and obtain a founder decision to split the consumer
into another instance or host; do not silently buy a paid n8n tier. [n8n
Community edition features](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/community-edition-features.md)

### Supersedes the earlier single-host recommendation

The [2026-08-12 social-media plan review](../reviews/ai-social-media-plan-review-2026-08-12.md) recommended upgrading the existing server to one Linux12GB host because that was the simplest $14 topology and met Postiz's recommended 8 GB/50 GB sizing. On 2026-08-13, the founder instead approved two Linux6GB services at the same initial $14 total: one preserves a scheduling and failure boundary around Paperclip, n8n and Hermes, while the other makes the newer publisher independently replaceable and upgradeable. The trade-off is a second OS to manage and a 6 GB/30 GB publisher canary below Postiz's recommendation.

This plan supersedes only that review's hosting topology, Paperclip-adoption workflow and directly conflicting budget statements. Its two-brand launch, publisher alternatives, research constraints and generation-cost findings remain inputs. `README.md` §5 and §9 record this topology as the current repository source of truth. The second $7 service purchase is founder-approved; there is no additional pre-purchase decision gate.

## Why Ansible is the primary tool

Choose **Ansible Core plus pinned Docker Compose** for host and service
configuration. Use **OpenTofu narrowly for supported external APIs**, initially
Cloudflare DNS/Tunnel/Access and R2 bucket metadata. Those resources must be
imported and code-owned before their production cutover; OpenTofu still does not
manage unsupported VPSDime lifecycle operations.

| Tool | Decision | What it owns | Why |
| --- | --- | --- | --- |
| Ansible Core | **Primary** | OS baseline, users/SSH, firewall, Docker repository/engine/plugin, directories, systemd units/timers, Compose deployment, backup jobs, monitoring, health verification and migration orchestration | It works over ordinary SSH against both current and replacement hosts, is idempotent, supports check/diff modes, and does not require an agent on the VPS. |
| Docker Compose v2 | **Runtime contract** | The complete service definitions, networks, volumes, health checks, resource limits, image digests and logging limits on each single host | It matches the upstream Postiz deployment model and keeps each application portable to any Docker-capable Ubuntu host. Ansible's `community.docker.docker_compose_v2` module manages it directly. [Ansible Compose module](https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_compose_v2_module.html) |
| OpenTofu | **Required for the supported control plane** | Only providers with supported APIs: Cloudflare DNS, tunnels, Access and R2 bucket declarations | Reproducibility forbids dashboard-only production state where a supported provider exists. VPSDime's documented deployment flow remains a customer-panel workflow; no supported public VPSDime provider/API was found, so OpenTofu cannot safely declare that lifecycle. [Cloudflare Tunnel IaC](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/deployment-guides/terraform/), [R2 bucket resource](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket) |
| Docker Swarm/Kubernetes | **Reject for two hosts** | Nothing | Two nodes do not provide a sound quorum, do not pool RAM, and make stateful publisher recovery harder. Docker recommends more than two and an odd manager count for fault tolerance. [Docker Swarm quorum](https://docs.docker.com/engine/swarm/admin_guide/) |
| A web control panel (Coolify, Portainer, etc.) | **Reject as authority** | Optional read-only convenience only | It would create a second mutable configuration surface. Git plus Ansible must remain authoritative. |

The intentionally manual boundary is small: order/reinstall/resize a VPS in the
VPSDime panel, choose Ubuntu 24.04 LTS, attach the bootstrap SSH public key, and
record its stable hostname and role in the committed inventory. A temporary IP
override may remain local only while old and replacement hosts coexist. Every
host and supported control-plane configuration after first SSH must be
reproducible from code; unavoidable provider/OAuth grants follow committed
runbooks and verification receipts. If VPSDime later publishes a supported
API/provider, add a reviewed OpenTofu module rather than browser automation.

## What “reproducible” means

Rebuilding is a three-source operation, not “one Git checkout contains the
whole server”:

1. **Reviewed Git repositories store desired state and approved ciphertext:** Dholbeat stores playbooks, roles, Compose files, version/image locks, public configuration templates, Dholbeat-owned n8n workflow exports, n8n-consumer and Hermes-project manifests, systemd definitions, verification scripts, runbooks, the `.sops.yaml` policy and values-only SOPS+age-encrypted `*.sops.yml` files. An external project's repository stores its own credential-free workflow exports, Hermes prompt/skill/schedule configuration and tests where it uses those tools. Every production import records the exact reviewed source commit and content hashes; a moving branch is never a recovery input. GitHub is not the sole recovery copy: every annotated production release creates a verified bundle of Dholbeat `main` plus production tags in encrypted restic source escrow, then deletes the local temporary bundle.
2. **The password manager is the root-access authority:** it stores the founder and break-glass age private keys, host bootstrap key and provider recovery logins. The `SOPS_AGE_KEY` environment variable supplies an age private key at apply time; no private key or plaintext `.env` enters Git.
3. **Encrypted off-site backups store mutable state and source escrow:** fresh
   database dumps, the small set of non-database application data that cannot be
   regenerated and the verified Dholbeat release bundle. Restic is the only
   backup-retention authority; its source-escrow recovery root also lives in the
   password manager so bundle retrieval does not depend on GitHub or ciphertext
   inside the missing checkout.

A replacement host is complete only after Ansible converges, encrypted state is restored, external OAuth/tunnel callbacks are verified and the service passes its acceptance test. Git alone cannot reproduce PostgreSQL rows, OAuth grants or media objects; pretending otherwise would be either incomplete or unsafe.

## Target repository layout

Implement the following without creating a second infrastructure repository:

```text
infra/
  README.md
  ansible.cfg
  requirements.yml                 # exact tested collection versions
  secrets/
    core.sops.yml                  # platform secrets: n8n drift key, parity HMAC key
    publisher.sops.yml
    n8n-consumers/
      poripati-track1.sops.yml     # runtime values only; no secret in consumer repo
    hermes-projects/
      dholbeat.sops.yml            # one values-only secret set per enabled profile
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
  tofu/                             # supported external control-plane state
    cloudflare/
  services/
    domains.yml                     # registrar delegation/zone expectations
stack/
  paperclip/                        # imported desired config; parity is invariant
  n8n/
  hermes/
    projects/
      README.md                     # profile ownership/import/restore contract
      project.schema.json           # validates every Hermes project registration
      dholbeat.yml                  # non-secret profile/source/limits contract
  publisher/                        # only the selected publisher stack is enabled
n8n/
  workflows/                        # Dholbeat-owned credential-free JSON exports
  consumers/
    README.md                       # ownership/import/restore contract
    consumer.schema.json            # validates all consumer registrations
    poripati-track1.yml             # non-secret source, limits and data contract
scripts/
  infra-plan
  infra-apply
  infra-verify
  infra-restore-drill
  repository-bundle
  n8n-consumer-check
  n8n-consumer-import
  n8n-consumer-verify
  n8n-consumer-drift
  hermes-project-check
  hermes-project-import
  hermes-project-verify
.sops.yaml                          # path policy + founder/break-glass recipients
```

Commit the production inventory, host roles and stable public DNS names so a
lost laptop is not the only map of the system. Public IP addresses may also be
committed when a hostname is unavailable; they are endpoints, not credentials.
Secret values may be committed only as SOPS+age `*.sops.yml` ciphertext beneath
`infra/secrets/` under the committed `.sops.yaml` policy. Never commit plaintext
secrets, private age/SSH keys, tunnel tokens in plaintext, `.env`, Ansible Vault
files/passwords, OpenTofu state, plan files, generated media or application
data.

## Configuration model

### Shared baseline role

Both hosts receive the same deterministic baseline:

- Ubuntu 24.04 LTS assertion; fail rather than silently applying to an unknown OS.
- A named administration user with `sudo`, key-only SSH, disabled password authentication and a separately tested break-glass path through the VPSDime console.
- Time synchronization, unattended security updates with a declared reboot policy, persistent journald limits, logrotate and a fixed timezone policy (UTC on hosts; business timezone passed to applications).
- Host firewall with default-deny inbound. Expose SSH only through an explicit
  allowlist or a documented access path; applications bind to loopback or a
  private container network. Inbound webhooks use declared Cloudflare Tunnel
  routes and never require a publicly exposed origin application port.
- Docker Engine and Compose plugin from a declared repository, with tested version ranges and bounded Docker JSON logs. Pin application images by digest; Renovate or a scheduled dependency PR may propose digest updates, but production never follows `latest` implicitly.
- Disk, RAM, OOM, container-health, certificate/tunnel and backup-age monitoring. Alerts go to a dedicated operational channel, not a publishing-approval callback.
- Restic client and one locked systemd timer per host. Backup jobs must not overlap Hermes browser work, publisher upgrades or each other.

Run baseline changes serially (`serial: 1`) and retain out-of-band console access. Firewall and SSH handlers must verify a second connection before ending the existing session.

### `core-1`: adopt Paperclip by parity, then add automation

Paperclip need not be an untouchable snowflake. The invariant is that its effective configuration and image digest remain unchanged during IaC adoption and that it returns healthy after convergence. Container recreation is permitted in a planned restart window:

1. Capture a redacted effective manifest: `docker compose config`, environment-
   variable names plus domain-separated HMACs, bind mounts/volumes, resolved
   image digest, restart policy, systemd/cron jobs, tunnel routes, backup inputs
   and expected health response. Compute live and candidate HMAC-SHA-256 values
   over `paperclip-env-v1\0<key>\0<value>` with the same dedicated high-entropy
   parity key decrypted from SOPS only in controller memory; never emit a value,
   an unkeyed digest or the parity key.
2. Take a fresh application-consistent database dump, snapshot required state with restic and prove a disposable restore **before** the first mutating convergence.
3. Express the captured desired state in `stack/paperclip/` and SOPS-encrypted variables. The `paperclip_guard` role compares the rendered candidate with the captured manifest and fails on any unexplained difference before applying it.
4. Converge in a planned restart window. Ansible may recreate the container, but may not move its data, alter the effective config or change/upgrade the captured image digest during adoption.
5. Recapture the same manifest after convergence, compare it with the before
   snapshot and verify application health. Store only redacted manifests and
   keyed parity HMACs in CI artifacts. If the parity key leaks, rotate it and
   every represented service secret before reviewing a new baseline because Git
   history retains the old HMACs; rotate a service secret immediately if its
   value is ever exposed.
6. Replace the conflicting tar/cleanup jobs only after the restore test. Back up a fresh database dump, Compose/config and required non-database state directly to a private encrypted R2 restic repository. Keep at most one local latest dump; use `forget --keep-daily 7 --keep-weekly 4 --prune`, followed by `check`. Do not apply an R2 object-expiry lifecycle to the restic bucket.
7. Deploy one central n8n Community instance in its own Compose project,
   network, volume/database credentials and directory. Start production
   concurrency at one; cap execution and binary retention; export Dholbeat
   workflow JSON to this repository and import registered external workflows
   from their owning repositories through the consumer contract below.
8. Reuse one pinned Hermes image/version, but deliberately take upstream's
   documented separate-container exception for resource isolation and blast-
   radius control: one container/service per enabled project profile, each with
   a unique host directory mounted at `/opt/data`, its own project workspace,
   approved skills, schedules and credentials. Do not use the default in-
   container profile multiplexer or mount one data directory into two gateways.
   Enforce an aggregate
   approximately 2 GB Hermes memory ceiling and one active agent job globally,
   not 2 GB per profile. No profile receives the Docker socket, host root,
   Paperclip or another project's mounts, host network, publishing credentials
   or authority to mutate durable approval state. A designated profile may
   receive only its own Telegram gateway token if that open decision selects
   Hermes for founder input; it forwards verified input to n8n and cannot
   approve or publish by itself. n8n remains the deterministic authority, and
   no deadline, approval or publish path depends on Hermes.

Live baseline recorded 2026-08-13 before this plan: 4 vCPU, 6 GiB RAM,
approximately 1.0 GiB used/5.0 GiB available, no swap, root disk 17/30 GB
used, Paperclip approximately 698 MiB RAM, and all w3exam containers
approximately 225 MiB. After the separately approved w3exam migration and
legacy-backup cleanup, record `B_core`, the used root-disk baseline before n8n
or Hermes is admitted. The expected admission target is **`B_core ≤ 14 GB`**:
that leaves 4 GB for initial shared-service steady state, a further 3 GB before
the pause gate and at least 9 GB free. This is a required target to measure, not
a claim that cleanup has already achieved it. If `B_core` remains above 14 GB,
stop before deploying n8n/Hermes and present measured cleanup, resize or move
options to the founder. The existing figures are point-in-time evidence, not
capacity guarantees.

### Central n8n consumer contract

The implementation must support external workloads without making Dholbeat a
copy of their product repositories. Every consumer is registered by a
non-secret manifest under `n8n/consumers/`. The schema requires:

- stable consumer and workflow namespace; owning repository, export path,
  allowed source-ref policy and an immutable desired `source_commit` pin;
- workflow owner, operational alert destination and incident contact;
- exact credential **names and purposes**, never values; outbound hostname/API
  allowlist and an explicit prohibition on direct product-database access;
- permitted trigger types, schedule windows, maximum execution time and
  expected execution rate;
- allowed/denied node classes, data classification, execution/binary retention
  and backup/deletion handling;
- any public machine route, including caller, exact method/path, signature or
  secret verification, rate limit and negative tests; an empty route list is
  the default;
- import, smoke-test, rollback and restore commands plus the conditions under
  which the workload may be activated.

PoriPati Track-1 begins with these concrete constraints:

1. Its canonical JSON exports stay in
   `infra/growth/n8n/flows/` in the PoriPati repository. The first workloads are
   the Scout scheduler, post-conversation summary sync, founder digest and
   opt-in-checked WhatsApp template sender. Dholbeat does not vendor copies.
2. A small reviewed Dholbeat change pins the exact cross-reviewed PoriPati
   commit in `poripati-track1.yml` before production import. Imports must match
   that pin, validate the consumer manifest and JSON, reject
   duplicate/cross-consumer workflow identifiers, secret literals and every
   credential reference not declared for that consumer, then record repository,
   commit, content hashes and the resolved allowed credential IDs in a
   root-owned deployment receipt under `/etc/dholbeat-n8n-consumers/`. The
   committed pin is desired state; the receipt proves what was applied. A
   PoriPati merge never applies itself to production.
3. PoriPati receives distinct credentials for its revocable product service
   principal, official WhatsApp Cloud API, Anthropic API and operational
   Telegram destination. Names are declared in PoriPati; values are rendered
   only from `infra/secrets/n8n-consumers/poripati-track1.sops.yml`. Never reuse
   Dholbeat publisher, approval-bot or brand credentials.
4. PoriPati flows use typed authenticated HTTPS endpoints and keep product
   business rules in the product API. Reject Execute Command, SSH, local
   filesystem, unreviewed community/custom nodes and arbitrary network targets
   for this consumer unless a later security review explicitly amends its
   manifest.
5. Current Track-1 workflows are scheduled or outbound and receive no public
   n8n ingress. A future provider callback requires a separately reviewed
   `hooks.chayan.me` path manifest and application-level signature/secret
   verification before n8n; it may not expose or bypass `n8n.chayan.me`.
6. Do not save successful PII-bearing executions. Retain minimized failure data
   for at most 14 days, never persist message bodies or generated media, and
   keep phone numbers out of general logs. After a restore, rerun time-based
   pruning and PoriPati deletion/suppression reconciliation before activating
   the consumer.
7. At global concurrency one, split Scout work into short checkpointed batches,
   avoid holding an active execution slot while waiting, schedule those batches
   away from planned publishing activity and give every workflow a hard
   timeout. Measure per-consumer counts, duration, errors, RAM and disk.
   Persistent head-of-line blocking, an OOM or a host threshold breach pauses
   the offending workload and triggers a founder capacity/isolation decision;
   it does not silently increase concurrency or purchase capacity.

Names, tags and folders make operations legible but are not security controls.
All workflows share one process, encryption key, database, backup set, upgrade
window and outage boundary. Only trusted, reviewed founder-owned consumers may
use this central instance.

Folders require the **Registered Community** edition: still $0, but unlocked by
registering a founder-controlled operations email and activating the resulting
license key. Record the registration/recovery account in the password manager,
catalogue the license key as a SOPS-managed runtime secret and restore-test its
activation. If registration is unavailable, retain the same namespace through
names/tags and do not represent folders as an isolation control. [n8n registered
Community features](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/community-edition-features.md#registered-community-edition)

The PoriPati rules above are the first concrete registration, not a special
case in the runtime. A future w3exam or other founder-owned consumer gets a new
manifest, its own SOPS file, namespace, credential references, allowlists,
source-commit pin and deployment receipt. Its product-specific workflows stay
in that product repository. Onboarding must not require a change to the n8n
Compose project, Ansible role or generic import code. The implementation first
proves this by validating and round-tripping a second credential-free fixture;
that test does not activate unfinished w3exam business automation.

### Central Hermes project contract

Maintain one pinned Hermes Agent image/version on `core-1`, but do not run all
projects inside one Docker profile multiplexer. Upstream documents two distinct
facts: native profiles have per-profile configuration and credentials while
their gateway session keys can be namespaced inside a **shared** session store;
its Docker default is one s6-supervised container hosting multiple profiles,
while separate containers are documented for needs such as resource isolation
and blast-radius control. This plan deliberately takes that documented
exception. Each project gets its own container/service and a distinct host
directory mounted at `/opt/data`; the upstream warning against pointing two
containers at the same data directory still applies. Each project also gets a
resolved state backend, SOUL/prompt configuration,
approved skills, intended local memory/session state, cron definitions, bot
tokens and other credentials, project workspace and bounded logs. [Hermes
multi-profile gateways](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/user-guide/multi-profile-gateways.md), [Hermes profiles](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md), [Hermes Docker profiles](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/docker.md#multi-profile-support)

Every project is registered by a non-secret manifest under
`stack/hermes/projects/`. The schema requires:

- a stable project/profile ID, owner, owning repository, configuration path and
  immutable desired `source_commit` pin;
- exact credential names and purposes, unique `/opt/data` and workspace mounts,
  the intended state-backend type/path, and explicit tool, filesystem, command
  and outbound-network allowlists;
- allowed trigger types and caller/chat identities, schedules, maximum runtime,
  expected job rate, operational alert destination and incident contact;
- memory/CPU limits, global scheduling priority, data classification,
  session/memory/log retention and explicit backup/deletion handling; and
- import, inactive smoke-test, rollback and restore commands plus activation
  conditions.

Dholbeat's own profile is canonical in this repository. An external project's
Hermes prompts, skills and cron definitions remain canonical at an exact
cross-reviewed commit in its owning repository, with hashes recorded in a
root-owned deployment receipt. Runtime values come only from that project's
`infra/secrets/hermes-projects/<project>.sops.yml`; no container may mount
another profile's data directory, credential file or workspace. Separate
memory/session storage is an activation requirement, not an assumption: the
verifier must inspect the rendered mounts and resolved state-backend paths and
prove that each container writes its own local state database. A shared remote
memory/session backend, including a shared Honcho workspace, fails activation
unless a later security review supplies real project isolation; namespaced keys
alone do not pass. Adding w3exam later is therefore a manifest,
project-specific SOPS file, reviewed source pin, inactive smoke test and
capacity check—not another Hermes code installation or a branch in shared
runtime code.

The initial host-wide Hermes envelope is approximately 2 GB and one active
agent job across all profiles. Enforce per-profile cgroup limits plus a global
scheduler/lock; leave profiles inactive or schedule them apart when necessary.
Measure duration, errors, RAM, disk and queue delay by project. A noisy profile
is paused before it can delay Paperclip or deterministic n8n work. This shared
image becomes a process/filesystem/state-store boundary for trusted
founder-owned projects only after the mount/backend verifier passes; it is not
hostile-tenant isolation or independent capacity.

Hermes is noncritical and has no public API or gateway by default. Any later
founder interface must be separately declared under the Zero Trust policy;
bot/gateway callers are allowlisted per profile. Use a sandbox/container,
non-root execution, resource limits and narrow credentials, and do not forward
secrets into an agent sandbox unless the declared task requires them. No
profile receives the Docker socket, host root, Paperclip/product mounts,
another project's state or Postiz/Mixpost credentials. If the founder selects
Hermes as a Telegram gateway, only the designated profile receives its own bot
token and forwards verified founder input to n8n; it cannot mutate durable
approval state or publish by itself. n8n owns deterministic triggers, retries,
approval state and publishing, and a metered API fallback remains available
when Hermes is unavailable. [Hermes
security guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md), [Hermes security policy](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)

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
- Require a stable project organization/workspace and brand-account mapping
  before connecting a social account. Provider connections, media, approval
  records and API credentials must not be silently reused across projects.
  Adding a project/brand is a workspace plus configuration/secret change, not
  shared integration code.
  Verify the selected tool's workspace and API authorization behavior during
  the canary; if it cannot prevent an integration from writing to another
  project's workspace, stop for a founder decision to split the instance or
  select a different publisher.
- Enforce the repository's human-approval rule at the integration boundary: n8n may create or schedule a Postiz job only when the current content hash has a recorded founder approval in the correct brand channel. Editing invalidates approval. Hermes never receives the Postiz credential, and neither Postiz nor a retry worker may turn an unapproved draft into a scheduled post.

For Postiz, use one organization and its own API/OAuth credential per project;
map each brand only to integration IDs owned by that organization. Postiz's
public API documents organization-scoped resources and rejects access to a
resource owned by another organization, but the canary must still verify this
on the pinned self-hosted version. [Postiz API authorization](https://docs.postiz.com/public-api/introduction)

Postiz remains a default, not a closed decision. If the founder selects Mixpost,
the host boundary, inventory, baseline, tunnel, R2/restic, monitoring, approval
contract and replacement-host workflow remain unchanged; only the publisher
role, Compose project and application-aware dump/restore adapter change.
Mixpost documents configurable multiple workspaces under its Enterprise edition
and says a user otherwise owns one workspace, so the comparison may not treat
multi-workspace support as a free-edition guarantee. This finding is recorded
in `README.md` §9 and **does not choose the publisher**. The decision packet must
compare the exact $0 Postiz and Mixpost editions against the same isolation/API
tests. If only a paid edition meets the founder-approved multi-project
requirement, return with a monthly-cost table and explicit founder choice; do
not silently retain Postiz or buy Mixpost. Mixpost's documented stack uses PHP,
MySQL, Redis, queue workers and FFmpeg and does not list Temporal, so it must be
re-benchmarked rather than assumed to share Postiz's resource profile. Do not
deploy both publishers simultaneously. [Mixpost multiple workspaces](https://docs.mixpost.app/enterprise/configuration/multiple-workspaces/), [Mixpost server requirements](https://docs.mixpost.app/server/)

## Network and failure model

The services integrate at application boundaries:

```text
Founder -> Cloudflare Access -> team.chayan.me -> Paperclip
Founder -> Cloudflare Access -> n8n.chayan.me / publish.chayan.me UIs
Telegram -> hooks.chayan.me/webhook/* -> verified ingress -> n8n approval state
n8n -> per-project scoped service principal over HTTPS -> registered product APIs
n8n -> official provider APIs -> project-scoped consented actions and ops alerts
Hermes project profile -> declared project workspace/APIs only
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

The registrar-side delegation of `chayan.me` is an external root, not a
Cloudflare/OpenTofu resource. Commit the expected parent-zone nameserver set,
registrar owner and renewal expectation as non-secret data; keep the registrar
recovery identity in the password manager. Any delegation change follows a
founder-confirmed runbook with rollback and a direct parent-zone NS probe, not a
cached recursive answer or dashboard screenshot.

The initial public hostname and route map is:

| Host | Interface | Hostname | Edge access |
| --- | --- | --- | --- |
| `core-1` | Paperclip | `team.chayan.me` (existing) | Cloudflare Access identity policy |
| `core-1` | n8n administration | `n8n.chayan.me` | Cloudflare Access identity policy |
| `core-1` | Telegram approval webhook ingress | `hooks.chayan.me` | Machine-only `POST /webhook/*`; path-scoped exception with secret-header verification; no editor or REST UI |
| `publish-1` | Selected publisher administration and API | `publish.chayan.me` | Cloudflare Access identity policy for people; a separately scoped Access service token for n8n API calls |

PoriPati does not receive another n8n administration hostname: the founder uses
`n8n.chayan.me` for the central instance. Its initial Track-1 flows are
scheduled/outbound and add no public route. If a later provider callback is
required, add the narrowest consumer-specific path below `hooks.chayan.me` only
after its route manifest, application-level verification and negative tests are
reviewed. Never make an Access exception on `n8n.chayan.me` for a consumer.
Future w3exam or other project registrations follow the same rule. Hermes has
no public interface by default; a project profile does not receive a hostname
merely because it exists.

Cloudflare documents service tokens specifically for automated callers of an
Access-protected self-hosted application; each token is independently
renewable and revocable. A service-token-authenticated route remains
Access-enforced and is not a machine-route exception under acceptance criterion
10. [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)

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
hostname or the narrowest exact path/prefix the application supports. Before
exposure, its committed route manifest must name the caller, purpose, allowed
methods, application-level verification (for example webhook secret, OAuth
`state`, signed object URL or monitor secret), Cloudflare WAF/rate limit, data
class and retention owner. Never create an Access bypass for an entire
administration hostname. If the provider cannot support a safely scoped route,
stop and ask the founder rather than exposing it. Cloudflare supports policies
scoped to specific application paths, but its `Bypass` action disables Access
controls and Access logging; any required bypass is therefore an explicit
machine-route exception, not Zero Trust protection. [Cloudflare Access application paths](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/), [Cloudflare Access policy actions](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)

The Telegram approval webhook is the first declared machine-route exception:

- Route only `POST https://hooks.chayan.me/webhook/*` through the `core-1`
  tunnel to a narrow verifying ingress in front of n8n. Deny every other method
  and path at that hostname; never expose the n8n editor, REST API,
  `/webhook-test/*` or `/webhook-waiting/*` there without a separate reviewed
  manifest.
- Set `N8N_EDITOR_BASE_URL=https://n8n.chayan.me/` and
  `N8N_WEBHOOK_URL=https://hooks.chayan.me/`; `WEBHOOK_URL` is now only a
  deprecated alias. Declare the exact `N8N_PROXY_HOPS` value for the implemented
  proxy chain and forward only the documented proxy headers. [n8n endpoint variables](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md), [n8n reverse-proxy webhook configuration](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/configure-webhook-urls-with-reverse-proxy.md)
- Register a distinct SOPS-managed Telegram `secret_token` for each approval
  bot and reject any request whose `X-Telegram-Bot-Api-Secret-Token` header is
  absent or wrong before n8n processes it. Keep n8n's random webhook path as a
  second control, not as the only authentication mechanism. If the selected n8n
  trigger cannot preserve and verify the header, the narrow ingress must do so.
  [Telegram Bot API `setWebhook`](https://core.telegram.org/bots/api#setwebhook)
- Use a separate non-production Telegram bot for manual trigger testing; one
  bot can register only one webhook at a time, so a test activation must not
  replace the production approval webhook. [n8n Telegram Trigger guidance](https://github.com/n8n-io/n8n-docs/blob/main/docs/integrations/builtin/trigger-nodes/n8n-nodes-base.telegramtrigger/common-issues.md)

No cross-host NFS, shared Docker volume, overlay network, database connection or two-node scheduler is permitted. This makes a server loss local: `publish-1` failure pauses scheduling but Paperclip/research/approval remain available; `core-1` failure does not corrupt publisher state, although new approvals pause. Already scheduled publisher jobs must behave according to a documented approval-state contract.

Use distinct Cloudflare tunnels, service tokens and R2 credentials per host/purpose. A compromise of the public publisher must not reveal Paperclip secrets or the backup credential for `core-1`.

## Secrets and access workflow

The hard rule is **no plaintext secrets in Git**. Values-only SOPS+age ciphertext may be committed as `infra/secrets/*.sops.yml` only under a reviewed `.sops.yaml` policy and CI metadata checks. This replaces password-manager-to-temporary-file materialization as the primary application-secret path; Ansible Vault is not used.

Required flow:

1. Commit `.sops.yaml` with a `creation_rules` path expression limited to `infra/secrets/.*\.sops\.yml` and both the founder and break-glass **public** age recipients. Keep the corresponding private keys only in the password manager.
2. Encrypt only YAML values with SOPS. Each encrypted file must retain SOPS metadata, its integrity MAC and both approved recipients; adding a plain file under `infra/secrets/` is a CI failure. The repository secret catalog records each name, owner, consumer and rotation trigger without duplicating its value.
3. Keep each external n8n consumer and each Hermes project profile in its own
   SOPS file. Render only the selected consumer/profile values into its
   credential bootstrap or root-owned service file; owning repositories contain
   credential names, schemas and setup instructions only. Publisher provider
   connections and application tokens are likewise catalogued by project/brand
   even if the selected application stores them in one database. Removing a
   project must revoke its provider/API credentials, deactivate its workflows
   and profile, and remove its workspace access without rotating or exposing
   unrelated projects.
4. At apply time, export the selected private key from the password manager to `SOPS_AGE_KEY` in controller memory. Pinned `community.sops` integration decrypts variables for Ansible; tasks render root-owned `0600` host environment files with `no_log: true` and `diff: false`. Do not write a decrypted workspace copy. [SOPS age configuration](https://github.com/getsops/sops#encrypting-using-age), [Ansible `community.sops`](https://docs.ansible.com/projects/ansible/latest/collections/community/sops/)
5. Unset `SOPS_AGE_KEY` after the run and verify logs/artifacts contain neither plaintext nor decrypted diffs. Rotate any value ever printed. The password manager remains authoritative for private age keys, bootstrap SSH keys and provider recovery logins.
6. If an age private key leaks, remove its recipient and add a replacement, but also rotate **every underlying secret it could decrypt**. Re-encryption alone is insufficient because old ciphertext remains recoverable from Git history with the leaked key.

OpenTofu state goes to an encrypted remote backend with locking; backend
credentials are supplied through environment variables because plans/state may
contain sensitive data. Production application secrets should not pass through
OpenTofu. [OpenTofu backend security](https://opentofu.org/docs/language/settings/backends/configuration/)

## CI and change workflow

Every infrastructure pull request should run read-only checks:

- YAML lint and `ansible-lint`.
- `ansible-playbook --syntax-check` for every playbook.
- Secret scanning plus policy checks that `.env`, private keys, Ansible Vault data, state and plan files are absent; every file under `infra/secrets/` is named `*.sops.yml`, carries valid SOPS metadata/MAC and lists the policy's required age recipients.
- `docker compose config --quiet` for every project using generated non-secret test values.
- Schema tests for inventory/group variables and assertions that every image is digest-pinned, every persistent volume has a backup classification, and every growth path has retention.
- Consumer-schema tests for stable namespaces, source ownership, credential
  names, outbound allowlists, schedules/timeouts, data retention and route
  declarations. Inspect imported workflow JSON for secret literals,
  cross-consumer/duplicate IDs, forbidden nodes, undeclared network targets and
  credential references absent from that consumer's manifest.
- Hermes-project schema tests for stable profile IDs, immutable source pins,
  unique `/opt/data` and workspace mounts, distinct credential sets and
  state-backend paths, declared tools/network targets, caller allowlists,
  schedules/timeouts, global concurrency, resource limits and retention. Reject
  a shared data directory, local state database or remote memory/session
  workspace. A two-project fixture must prove that generic tooling creates no
  cross-profile path, state backend or secret reference.
- Publisher configuration tests require a unique project-to-
  organization/workspace and brand-to-social-account mapping, and reject
  duplicate account ownership or cross-project credential references.
- Molecule/container tests for roles that can be tested locally; a disposable Ubuntu VM test for Docker/firewall roles before production use.
- `tofu fmt -check`, `tofu validate`, provider lockfile verification and a
  saved, reviewed plan for the supported Cloudflare/R2 control plane.

Production apply is never automatic on merge. The founder runs:

```text
scripts/infra-plan --limit publish-1
scripts/infra-apply --limit publish-1
scripts/infra-verify --limit publish-1
```

`infra-plan` uses Ansible check/diff mode where supported, while suppressing secret diffs. Check mode is a preview, not proof, so a disposable-host convergence test and post-apply verification remain mandatory. [Ansible check/diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

Require a manual Git tag such as `infra-prod-YYYYMMDD-N` after a verified deployment. Store the deployed commit SHA in `/etc/dholbeat-release` on each host and export it to monitoring. Emergency host edits require a follow-up Git commit and convergence run; otherwise the nightly/weekly drift check reports them.

After tagging, `scripts/repository-bundle create --release <tag>` must refuse a
dirty checkout or non-annotated tag, bundle `main` plus production tags, run
`git bundle verify`, record the digest into encrypted restic source escrow and
remove its quota-bound local temporary file. Source-escrow retention preserves
every release named by a deployed host receipt plus the last two superseded
releases independently of normal daily/weekly pruning. Its restore mode must
reconstruct and verify the exact tag while GitHub is deliberately unavailable.

External-consumer deployment is also manual. `n8n-consumer-import` accepts a
clean local checkout at the exact `source_commit` already pinned by the merged
Dholbeat consumer manifest, produces a redacted plan of workflow
creates/updates/deactivations and requires founder confirmation before applying
it. `n8n-consumer-verify` writes the source commit, workflow hashes and resolved
allowed credential IDs to the consumer deployment receipt only after smoke
tests pass. A locked drift timer must re-export every live external-consumer
workflow at least every five minutes and revalidate its content hash and
resolved credential references against that receipt and the Git pin. Its
dedicated owner-generated n8n API key is instance-wide because non-Enterprise
keys cannot be scope-limited. Store it as SOPS ciphertext in
`infra/secrets/core.sops.yml` and render it only to the host as root-owned mode
`0600` `/etc/dholbeat/n8n-consumer-drift.env`. Never inject it into the n8n
service, import it as a workflow credential or mount it into a Hermes container;
both manifest validators and credential allowlists must reject any reference to
it. Prefer a supported bootstrap surface for the pinned version. If none exists,
use a committed one-time founder-only editor runbook whose no-echo controller
prompt encrypts the value directly into SOPS without logging or a persistent
plaintext file, verifies a read-only owner API probe, writes a redacted receipt
and defines create-new/verify/revoke-old rotation. That interactive external-
root action must never make the editor the desired-state authority.
[n8n API
authentication](https://github.com/n8n-io/n8n-docs/blob/main/docs/connect/n8n-api/authentication.md)
A new,
undeclared or cross-consumer credential reference is a critical fail-closed
event: deactivate only the affected workflow through the owner API, alert the
operational channel and require a clean reviewed re-import before reactivation.
The host never receives a personal GitHub token or follows a moving consumer
branch. This watchdog reduces the in-UI edit window; it does not turn Community
edition into tenant isolation, so editor Access remains founder-only.

Hermes project deployment follows the same reviewed-source rule.
`hermes-project-import` renders one profile from the exact commit pinned by its
merged manifest, leaves it inactive, and shows a redacted create/update plan.
Only after resolved mount/state-backend, isolation, resource, tool/network and
smoke checks pass may `hermes-project-verify` record hashes and activate its
declared schedules. A shared/unknown state backend or other failed profile stays
inactive without changing another profile.

## Migration and disaster-recovery procedure

The design passes the portability goal only if this runbook succeeds on a blank
compatible host. Start from the exact annotated release tag. In the GitHub-
outage drill, restore and verify that tag from encrypted source escrow using
only its password-manager recovery root, not an existing laptop clone.

1. Order/reinstall an Ubuntu 24.04 VPS and attach the bootstrap public key.
2. Add its stable hostname/role to the committed production inventory and use a temporary local override only while both old and replacement hosts coexist; keep the old host live.
3. Run `bootstrap.yml`, then the appropriate `core.yml` or `publisher.yml` against only the new host.
4. Restore the latest checked database/config snapshot into newly created volumes. For Paperclip, use its explicit application-aware restore procedure; never copy a running database directory.
5. Keep n8n workflows inactive while reconciling Dholbeat exports from the
   deployed Dholbeat commit and each external consumer from the exact commit in
   its deployment receipt. Recreate credential references from SOPS-managed
   values, run retention pruning and consumer-specific deletion reconciliation,
   revalidate the resolved allowed credential IDs, then run offline consumer
   smoke tests. Reconcile each Hermes profile from its recorded source commit
   into unique resolved `/opt/data`, state-backend and workspace boundaries;
   restore mutable memory/session state only when its manifest classifies and
   retains it, then keep every profile inactive until mount/backend isolation
   and smoke checks pass.
6. Run offline host verification, then use a temporary hostname or hosts-file entry for an end-to-end test.
7. Quiesce writes/scheduling on the old host, take a final dump/snapshot, restore the delta, and rerun verification.
8. Change Cloudflare tunnel/DNS routing. Keep OAuth callback hostnames stable so provider registrations do not change merely because the IP changed.
9. Observe the old host for late traffic, retain it through the rollback window, and cancel it only after a second off-site snapshot and documented sign-off.

Recovery objectives for the initial plan:

| Workload | Target RPO | Target hands-on rebuild objective | Notes |
| --- | ---: | ---: | --- |
| Dholbeat desired state | Every annotated production release | 30 minutes | Restore and verify `main` plus production tags from the encrypted Git bundle without GitHub. |
| Paperclip | 24 hours initially | 2 hours | Tighten only if business data changes justify more frequent dumps. |
| n8n configuration/state | Recorded Dholbeat + consumer Git commits; mutable DB follows backup schedule | 1 hour | External workflows reconcile from deployment receipts before activation. |
| Hermes profiles | Recorded project Git commits; only explicitly retained mutable state follows backup schedule | 1 hour aggregate initial target | Recreate separate profiles inactive, restore scoped state where declared, then verify isolation before activation. |
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
- Bootstrap encrypted/locked OpenTofu state, import the existing Cloudflare/R2
  resources and require a reviewed no-change plan before any public cutover.
- Commit the `hooks.chayan.me` Telegram route manifest, including its exact
  method/path boundary, secret owner, verification point, WAF/rate limit, data
  class, execution retention and negative tests.
- Define inventory/group-variable schemas, the `.sops.yaml` policy, required age recipients, secret catalog and data classification before writing mutating playbooks.
- Implement release-time repository bundling into encrypted source escrow and
  prove an exact-tag restore with GitHub unavailable before relying on GitHub as
  the normal checkout path.
- Define and test the generic n8n consumer schema, import/verification receipt
  format (including resolved allowed credential IDs), five-minute fail-closed
  drift timer and per-consumer SOPS layout. Register PoriPati Track-1 with no
  public route, its owning repository/export path and immutable source-commit
  pin, credential names, outbound hosts, execution bounds, 14-day maximum
  failure retention and restore checks.
- Define and test the generic Hermes project schema, profile
  import/verification receipt, per-project SOPS layout, separate data/workspace
  mounts and local state backends, global scheduler/resource contract and
  inactive-by-default lifecycle. Include a second credential-free fixture so
  the tooling cannot hard-code Dholbeat, PoriPati or w3exam.
- Define the selected publisher's project organization/workspace and
  brand-mapping schema and acceptance test before provisioning it; do not
  assume a UI folder is an authorization boundary.
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
  That product-host migration does not prevent w3exam from later consuming the
  central tools through its registered HTTPS/API contracts.
- After that migration, remove only inventory-proven unused images/volumes and
  superseded local backup artifacts under the separately reviewed cleanup
  procedure. Record `B_core`; require `B_core ≤ 14 GB` before admitting n8n or
  Hermes, or stop for a founder capacity decision.
- Apply the reviewed OpenTofu route/Access plan, then deploy n8n's editor at
  `n8n.chayan.me` behind its own Access application and its production webhook
  base at `hooks.chayan.me` through the restricted machine route above. Verify
  that non-`POST` methods, non-`/webhook/*` paths,
  and requests with a missing or wrong Telegram secret are rejected before
  n8n. A valid canary plus a replay must reach the correct brand/channel
  workflow while producing one durable approval transition. Then measure
  24–72-hour peaks. Prove the external-consumer path using a harmless
  credential-free PoriPati canary from an exact reviewed commit: validation,
  redacted import plan, isolated workflow identifiers, inactive-by-default
  import, smoke test, deployment receipt, rollback and restore. Do not activate
  unfinished PoriPati business flows. Round-trip a second credential-free n8n
  fixture to prove the importer is project-neutral. With dummy non-production
  credentials, mutate that fixture to reference the other fixture's credential
  and prove the drift timer deactivates only the violating workflow and alerts.
  Deploy the Dholbeat Hermes profile plus a harmless second project fixture as
  separate managed processes/data/workspace boundaries; verify that neither
  can read the other's state or credentials, then measure the aggregate one-job
  envelope.

**Exit:** a second Ansible run reports no unexpected changes; Paperclip's before/after effective-config diff is empty, its image digest is unchanged and it is healthy; backup restore passes; the Telegram route's positive, negative and replay tests pass without exposing an n8n UI/API; the PoriPati canary and second generic fixture round-trip without another public route or cross-project credential access; the dummy cross-credential mutation is detected within five minutes and only its workflow is deactivated; separate Hermes fixtures have unique resolved state/data/workspace mounts, cannot read each other's paths or credentials and obey one global active-job limit; measured `B_core` is at most 14 GB and root usage stays within its derived gates; seven-day peak RAM remains below 4.5 GB with no OOM.

### Phase 2 — provision and configure `publish-1`

- Exercise the founder's approved purchase by manually adding a second monthly Linux6GB service to the existing account, ideally in a different available datacenter, using key-only bootstrap access.
- Run the full Ansible bootstrap; configure a distinct tunnel and R2 credentials.
- Close the existing Postiz-vs-Mixpost decision, then deploy only the selected complete publisher stack with R2 media, automatic registration disabled after founder creation and no public state-service ports.
- Apply the reviewed OpenTofu route/Access plan and expose the publisher at
  `publish.chayan.me`, then connect both
  project spaces/brand mappings and n8n through its public HTTPS API using both
  a scoped Cloudflare Access service token and a scoped application credential.
- Prove the generic organization/workspace mapper can add another project/brand
  through configuration and scoped secrets without code changes or access to
  existing provider connections. Do not connect a real account merely for this
  fixture.

**Exit:** immediate/scheduled/cancel/delete/token-refresh tests pass for both brands; cross-workspace negative tests and the generic workspace fixture pass; duplicate-post kill switch works; backup/restore passes; seven-day peak RAM is below 4.5 GB; steady disk is below 18 GB and an image update leaves at least 8 GB free.

### Phase 3 — complete supported-provider OpenTofu coverage

- Cloudflare/R2 resources needed by Phases 1 and 2 must already be imported and
  code-owned before their respective public cutovers. Import any remaining
  supported declarations rather than recreate them.
- Recover and verify the remote encrypted/locked state independently; never
  have OpenTofu manage the VPSDime services until a supported provider exists.
- Require reviewed plans and manual applies.

**Exit:** a no-change plan is clean, imports match production, state recovery is documented and no secret is committed or exposed in CI artifacts.

### Phase 4 — prove portability

- Rebuild each role in a disposable compatible VPS/VM twice: once from the
  normal Git checkout and once from the verified source-escrow bundle, plus
  SOPS ciphertext, password-manager roots and restic data.
- For `core-1`, reconcile every n8n consumer and Hermes profile from recorded
  source commits. Prove that a missing repository, content-hash mismatch or
  missing credential leaves only that consumer/profile inactive and fails the
  drill visibly without breaking Dholbeat or another registered project.
- Time the exercise, close all undocumented steps and record the tested Git tag and snapshot IDs.

**Exit:** both host roles can be rebuilt without copying an old root filesystem or consulting shell history.

## Capacity and escalation

Two Linux6GB hosts remain the $14 target only while each host independently meets its guardrails. Aggregate free memory on the other machine cannot rescue a constrained process.

For `core-1`, attribute n8n execution counts, duration, errors and retained data
to the declared consumer namespace, and attribute Hermes jobs, queue delay,
memory/session/log growth, RAM and errors to the declared project profile.
Start n8n at global concurrency one and Hermes at one active agent job globally;
admit PoriPati and any later w3exam workload only within those shared envelopes.
Do not pretend free n8n provides per-project queues/quotas or that separate
Hermes profiles create independent host capacity.

Derive `core-1` disk gates from the measured post-migration `B_core`, rather
than copying publisher thresholds:

- expected n8n/Hermes steady state is at most `B_core + 4 GB`;
- alert at `B_core + 5 GB`, pause the workload responsible and block another
  project admission at `B_core + 7 GB`; and
- independently fail any update or admission that cannot preserve at least
  8 GB free.

At the required `B_core ≤ 14 GB` admission target, those are at most 18 GB
steady, a 19 GB warning and a 21 GB pause gate. They are not applied to the
pre-migration 17 GB snapshot. Before changing capacity, prune retained data,
bound/stagger long work and pause the project responsible for pressure.

The seven-day shared-service canary must also keep verified founder-approval
ingress → publisher-job creation at **p95 ≤ 60 seconds**, with no wait over
5 minutes attributable to another project. If that SLO fails, seven-day peak
RAM exceeds 4.5 GB, any OOM occurs, a derived disk gate trips or update
headroom is lost, stop and present measured options to the founder: workflow or
agent correction, a stricter same-host container/profile envelope, or a
`core-1` upgrade/move. No option is automatic.

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
| Registered projects on central n8n, Hermes and the selected publisher | $0 incremental initially | Reuse the bounded shared services; PoriPati is the first external n8n consumer and w3exam can register later. Provider/API usage remains in each project's budget, and measured capacity or isolation can still require a founder-approved split/upgrade. |
| Ansible Core, Docker Compose, OpenTofu | $0 | Open-source software; maintenance time is real but not a license fee. |
| R2 media and encrypted backups | $0–1 expected initially | Separate public media and private backup buckets; set usage alerts. |
| Optional VPSDime nightly backup add-ons | $0 initially | Two add-ons would add $10/month and provide only three-night retention; restic remains authoritative. |
| **Infrastructure total** | **$14–15/month initially** | Before tax/card conversion and the AI/content costs in the broader plan. |

Per-project attribution is operational accounting, not another wallet: n8n
consumers' Anthropic, WhatsApp and other provider spend still draws from the
same founder-funded **≤$75/month total growth envelope**. Every project
admission must update the complete forecast and surface any ceiling breach,
even when its incremental VPS/software line is $0.

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
- **No Git-hosting or secret completeness claim.** Recovery depends on the
  reviewed Git/SOPS content, password-manager roots and restic access, but the
  release bundle is restored and verified separately so GitHub and an existing
  laptop clone are not recovery prerequisites.
- **No two-node orchestration or distributed database.** Cross-host integration remains HTTPS/R2 only.
- **No routine manual configuration.** Emergency changes are temporary drift and must be reconciled into Git.
- **Central n8n is a shared-fate boundary.** Dholbeat, PoriPati and any later
  registered project share one process, database, encryption key, execution
  queue, backup set and upgrade window. Namespaces and separate credentials
  reduce mistakes but do not create tenant isolation. Community edition has no
  per-workflow credential ACL: the owner UI can attach any instance credential,
  so founder-only editor Access plus import and five-minute live drift
  validation are safety controls, not a hard authorization boundary.
- **External workflows are privileged code.** A workflow can consume CPU/disk,
  call networks and expose data. Only reviewed, schema-compliant workflows from
  a recorded commit may be imported; risky nodes and undeclared targets fail
  closed.
- **Cross-repository drift can make recovery false.** The deployment receipt,
  exact source commit, workflow hashes and restore drill are mandatory. Neither
  a moving PoriPati branch nor a copied JSON file in Dholbeat is authoritative.
- **Hermes profiles are not hostile-tenant isolation.** This plan deliberately
  uses one container per project plus unique `/opt/data`, workspace, credential
  set and verified local state backend per project; upstream's shared-store
  namespace alone would not qualify. Those boundaries contain ordinary mistakes
  and independent restarts, but profiles still share one host, image/version,
  upgrade window and global resource envelope. Agent tools are privileged code;
  only trusted reviewed profiles with narrow allowlists may run.
- **Publisher workspaces may be an application boundary, not a hard security
  boundary.** Verify API authorization and cross-workspace negative tests for
  the selected tool. If it cannot prevent cross-project writes, do not describe
  the deployment as separated; split or replace it only after a founder
  decision.
- **PoriPati execution data may contain personal data.** Minimize it before n8n,
  disable successful-execution storage, prune failures within 14 days and run
  deletion/retention reconciliation after restore. Backups are not permission
  to retain a replayable lead registry in n8n.
- **No per-project duplicate shared stack by default.** PoriPati, w3exam or a
  later trusted project should use the generic n8n/Hermes/publisher contracts
  while they meet the access, isolation and capacity gates. A split requires a
  documented founder decision; it is not an implementation shortcut.

## Acceptance criteria for the implementation PR

The subsequent implementation is ready for production review only when:

1. A clean Ubuntu 24.04 test host can reach converged state from the pinned controller environment and documented secret inputs.
2. Running `site.yml` twice produces no second-run changes except explicitly documented probes.
3. Paperclip's effective configuration is unchanged by a before/after parity diff, its image digest is unchanged, it is healthy after convergence, and its backup restores in a disposable environment; container recreation is permitted in the planned restart window.
4. Each service has a version/digest, health check, restart policy, log bound, data classification and backup/retention owner.
5. No plaintext secret, private key, `.env`, state file, plan file, database or generated media is tracked; every tracked file under the secrets path is values-only SOPS+age ciphertext with policy-required metadata and recipients.
6. Both hosts remain independently operable when the other is unreachable.
7. The selected publisher passes the two-brand seven-day canary within the 6 GB/30 GB thresholds, including its application-specific publish/restore tests, or the plan records a measured upgrade to `publish-1`.
8. A full replacement-host drill succeeds from both the normal Git checkout and
   a GitHub-independent verified release bundle, plus SOPS ciphertext,
   password-manager roots and restic; the exact manual VPSDime/registrar
   bootstrap boundary is documented.
9. Paperclip remains at `team.chayan.me`; every human-facing interface is a
   declared `chayan.me` hostname behind the correct host's Cloudflare Tunnel
   and default-deny Access policy, and no application origin is reachable by
   public IP or alternate DNS.
10. Every machine route that cannot enforce Access has a committed
    least-privilege exception manifest and positive/negative verification
    tests; no whole administration hostname has an Access bypass. Routes using
    a valid Access service token remain normal Access-enforced routes.
11. One central n8n instance serves Dholbeat and the registered PoriPati
    Track-1 consumer; no PoriPati-specific n8n/PostgreSQL/Caddy stack or second
    administration hostname exists. A second credential-free project fixture
    round-trips through the same tooling without hard-coded project logic,
    proving that w3exam can later register without changing the runtime.
12. The generic consumer schema and tooling reject secret literals, duplicate
    or cross-consumer workflow identifiers, forbidden nodes, undeclared network
    targets, undeclared/cross-consumer credential references, missing
    execution/retention bounds and unreviewed source commits. The five-minute
    live drift check revalidates credential IDs and content hashes against the
    deployment receipt; any violation deactivates only the affected workflow
    and requires a clean reviewed import before reactivation.
13. A PoriPati canary imports inactive from its owning repository, receives only
    its declared credential references, reaches only its typed HTTPS test API,
    passes smoke/rollback tests and produces a deployment receipt containing
    source commit, workflow hashes and resolved allowed credential IDs.
14. PoriPati workflows have no direct product-database or container-network
    access, no public route by default, no successful PII-bearing execution
    storage, at most 14 days of minimized failure data and no persistent
    binary/generated-media data.
15. One pinned Hermes image/version runs each enabled project as a separate
    container/service—not the Docker profile multiplexer—with a unique resolved
    `/opt/data` mount, workspace, local memory/session state backend, approved
    skills/schedules and credential set. Shared/unknown state backends fail
    activation; cross-profile path, state and secret negative tests pass. No
    profile exposes a public API or receives Docker, host, Paperclip, publisher
    or another project's credentials. A selected Telegram gateway profile has
    only its own bot token and cannot mutate durable approval state or publish.
16. Hermes tooling validates a second credential-free project fixture without
    runtime-code changes, keeps imports inactive until verified, enforces the
    aggregate approximately 2 GB/one-active-job envelope and records an exact
    source commit plus content hashes for every activated profile.
17. The selected publisher maintains unique project organization/workspace and
    brand social-account mappings. Both initial brands plus a no-account
    generic fixture pass cross-project authorization tests; no integration can
    schedule into another project's space or reuse its provider credentials.
18. The `core-1` restore drill reconciles Dholbeat and every registered n8n
    consumer/Hermes profile from recorded commits, restores only its SOPS-
    scoped credentials and declared retained state, performs retention/deletion
    reconciliation and leaves an unverifiable unit inactive without breaking
    another project.
19. Monitoring distinguishes n8n and Hermes pressure by consumer/project. The
    measured pre-admission `B_core` is at most 14 GB; the seven-day canary stays
    within the derived `B_core + 4 GB` steady, `B_core + 5 GB` warning and
    `B_core + 7 GB` pause gates, has no OOM and preserves 8 GB update headroom.
    Verified founder-approval ingress → publisher-job creation remains p95 at
    most 60 seconds with no wait over 5 minutes attributable to another
    project, or the plan records the founder-approved remediation.
