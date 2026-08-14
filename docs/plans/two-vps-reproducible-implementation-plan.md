# Two-VPS reproducible implementation plan

**Status:** Draft for cross-review and later GitHub issue breakdown

**Prepared:** 2026-08-15

**Architecture source of truth:**
[Two-VPS infrastructure-as-code plan](two-vps-infrastructure-as-code.md)

**Scope:** Repository foundation, infrastructure, shared services, Dholbeat
pipelines, production rollout, operations and clean-room recovery

## 1. Outcome and authority

This is the implementation companion to the approved architecture. It turns
that architecture into an ordered set of repository deliverables and gates. An
agent should be able to take one work package at a time, implement the named
files, run the named checks and know exactly when it is safe to proceed.

The target outcome is not merely “the services are running.” The target is:

> A reviewed Git commit plus approved SOPS ciphertext, password-manager root
> credentials and encrypted off-site backups can converge replacement hosts,
> restore retained state, reconcile every registered project from immutable
> source commits and prove the same security, approval, capacity and recovery
> properties without consulting laptop files, shell history or dashboard-only
> configuration.

This plan does **not** authorize a production apply, a VPS purchase, a DNS
cutover, a destructive cleanup, a provider connection or a social post. Each
such action remains behind the explicit gates below. If this document conflicts
with the architecture plan, the architecture wins until both are amended and
cross-reviewed.

Work-package IDs (`WP-00`, `WP-01`, and so on) are stable handles for the
GitHub issues that will be created later. They are dependency units, not a
requirement to place unrelated changes in one giant pull request.

## 2. Reproducibility contract

### 2.1 What Git must own

The repository is the desired-state authority for every reproducible part of
the platform:

- the pinned controller environment and every third-party tool/action version;
- inventory, public hostnames, service topology and non-secret configuration;
- Ansible playbooks, roles, handlers, templates and verification tasks;
- Docker Compose definitions, image digests, health checks, limits and
  persistent-volume classifications;
- Cloudflare/R2 declarations for every resource supported by a reviewed
  OpenTofu provider, including imported pre-existing resources;
- SOPS policy plus values-only encrypted secret files;
- database schemas and migrations owned by Dholbeat;
- brand, n8n-consumer, Hermes-project, publisher-mapping and route manifests;
- normalized credential-free n8n exports, prompts, media templates and all
  deterministic render/build code;
- backup, restore, migration, rollback, drift and clean-room rebuild scripts;
- schemas, fixtures, negative tests, canary tests and acceptance probes;
- systemd units/timers, monitoring probes, alert rules and retention policies;
- redacted evidence schemas, deployment receipt schemas and operator runbooks.

An implementation is incomplete if a necessary setting exists only in a web
dashboard, an interactive setup wizard, a server-side editor, an unexported n8n
workflow, a local `.env`, a developer's global Python installation or shell
history.

### 2.2 The unavoidable external roots

"Reproducible from this repository" cannot safely mean "put every byte in
Git." Exactly five classes of external input are permitted:

| External root | Why it cannot live as plaintext code | Repository obligation |
| --- | --- | --- |
| VPS/provider account actions | Ordering, reinstalling, billing and emergency console access have no supported VPSDime provider | Commit the exact bootstrap runbook, stable host role/inventory, expected OS, public-key fingerprint and postcondition checks. No manual **host** configuration is allowed after first SSH; separately catalogued provider/OAuth grants follow their own runbooks. |
| Private root credentials | Age private keys, bootstrap SSH private keys and provider recovery logins would defeat encryption if committed | Commit public recipients/fingerprints, secret names, owners, rotation triggers and test procedures. Store private material only in the password manager. |
| Mutable production state | Database rows, provider OAuth grants and retained application state change after every deployment | Commit migrations, dump/restore adapters, retention policy and verification. Store allowed mutable bytes only in encrypted, restore-tested backups or the provider account. |
| External project source | A registered consumer/profile remains owned by its product repository | Commit repository coordinates, exact reviewed commit, source path, content hashes and the import contract. Never follow a moving branch and never give the host a personal GitHub token. |
| Pinned upstream artifacts | Ubuntu packages, container images, fonts, actions and controller tools are too large or externally licensed to vendor blindly into Git | Commit the exact source, version, digest/checksum, license and verification/build procedure. A production-critical artifact needs a tested upstream-or-mirror recovery path and may never depend only on a laptop cache. |

Every unavoidable manual action must have all of the following:

1. a versioned runbook or wrapper command in this repository;
2. stated preconditions and an explicit founder confirmation point;
3. a machine-verifiable postcondition;
4. a redacted receipt or immutable source pin;
5. a rollback or recovery path.

If any of those five is missing, the action is undocumented mutable state and
must not become production-critical.

### 2.3 Reproducibility is functional, not bit-for-bit

Application images, controller dependencies, fonts and CI actions are pinned by
digest or checksum. Ubuntu security packages intentionally converge to the
approved repository state rather than an eternally frozen vulnerable image.
The deployment receipt records resolved package versions so a later rebuild can
explain differences. Idempotence, effective configuration, data contracts and
acceptance behavior are the invariants; identical filesystem block layout is
not.

### 2.4 Prohibited hidden state

The following fail review or CI:

- mutable `latest` image references, floating Git branches or unpinned CI
  actions;
- plaintext `.env`, tokens, private keys, credentials exports or decrypted
  SOPS output;
- Compose overrides or host files that are not rendered by committed code;
- manual Cloudflare Access, DNS, tunnel or R2 changes left unreconciled;
- live edits to n8n workflows without an exported, normalized reviewed source;
- live Hermes prompt/skill/schedule edits without a reviewed source pin;
- publisher connections without a project/brand mapping and restore record;
- databases or generated media copied into Git;
- unbounded logs, execution history, temporary media, caches or backups;
- a production process whose only recovery instruction is “copy the old
  server.”

### 2.5 Source-of-truth matrix

| Concern | Desired state | Secret/value source | Mutable state | Recovery proof |
| --- | --- | --- | --- | --- |
| Host baseline | `infra/` Ansible roles and inventory | Password-manager SSH key | Current OS packages | Clean Ubuntu convergence + second-run idempotence |
| Cloudflare/R2 control plane | `infra/tofu/cloudflare/` plus committed imports/locks | SOPS/provider recovery login | Remote encrypted/locked OpenTofu state | No-change plan + state recovery drill |
| Paperclip | `stack/paperclip/` and parity manifest | `infra/secrets/core.sops.yml` | App DB and declared volumes | Before/after parity + application restore |
| Central n8n | `stack/n8n/`, migrations and Dholbeat exports | Core plus per-consumer SOPS files | n8n DB and execution data within retention | Inactive reconcile + receipt verification |
| External n8n consumer | Manifest and immutable source commit | Its own SOPS file | Only declared retained execution state | Clean checkout, hash check, inactive import and smoke test |
| Hermes project | Manifest, pinned image and immutable source commit | Its own SOPS file | Declared per-project state only | Separate inactive render, mount/backend checks and smoke test |
| Publisher | Selected adapter, Compose and mapping manifests | Publisher/project SOPS values and provider account grants | Publisher DB/cache/workflow state | App-aware dump/restore + authorization canary |
| Brand behavior | `brands/<slug>.yaml`, prompt templates and workflow inputs | Secret references resolve from SOPS | Content/metrics state within declared retention | Schema validation + fixture replay |
| Generated media | Versioned render code/templates, never output files | Provider API keys from SOPS | Ephemeral working files or selected external archive | Deterministic overlay test + purge/archive verification |
| Deployment identity | Git tag/commit, image lock and release schema | None | Host receipt and backup snapshot IDs | `infra-verify` matches host to reviewed release |

## 3. Agent execution rules

1. Read `AGENTS.md`, `README.md`, the architecture plan and this document
   before starting a work package.
2. Use one Codex/Claude worktree and one branch per issue. Claim only the paths
   named by the work package; split a package if another live lane owns them.
3. Implement prerequisites first. A dependent package may prepare fixtures but
   may not bypass an unmet gate with placeholders that look production-ready.
4. Keep generic runtime code project-neutral. A real project or brand appears
   only in its declarative manifest/profile and SOPS file. Generic tests use
   `project-alpha`, `project-beta`, `brand-alpha` and `brand-beta` fixtures.
5. Every PR includes tests for its failure modes, documentation for operator
   actions and a cost note. “No monthly-cost change” is a valid explicit note.
6. Production-changing scripts default to plan/check mode, require an explicit
   host limit and refuse a dirty checkout, moving source ref, unreviewed commit
   or missing release tag.
7. CI never applies production. The founder invokes production apply after
   cross-review and after reading a redacted plan.
8. Never weaken the human-approval gate to make an end-to-end test pass. Use
   synthetic accounts and fixtures until founder approval/provider connection
   gates are met.
9. Record adjudication and cross-model review using the repository's label
   convention. Two contested rounds stop at the founder.
10. Update this plan only when implementation discovers a real contract or
    dependency change. GitHub issues will track progress; this file remains the
    durable sequence and definition of done.

## 4. Target repository shape

The implementation may add lower-level files, but it must preserve these
ownership boundaries and entry points. A naming change requires updating this
tree and every calling script in the same PR.

```text
.github/
  workflows/
    validate.yml                    # read-only, actions pinned to commit SHAs
.sops.yaml                          # production path policy + public recipients
toolchain.lock.yml                  # CLIs, controller image and checksums/digests

infra/
  README.md                         # bootstrap/apply/recovery entry points
  ansible.cfg
  controller/
    Containerfile                   # reproducible Ansible/check environment
    requirements.txt                # Python packages pinned with hashes
    requirements.yml                # Ansible collections pinned exactly
  schemas/
    inventory.schema.json
    service.schema.json
    secret-catalog.schema.json
    route.schema.json
    volume.schema.json
    release.schema.json
  inventories/
    production/
      hosts.yml
      group_vars/{all,core,publisher}.yml
    fixtures/
      hosts.yml                     # disposable-host/Molecule values only
  services/
    registry.yml                    # every service, host, data and health owner
    images.lock.yml                 # tag, digest, source and verified date
    routes.yml                      # hostname/path/Access/machine-route contract
    volumes.yml                     # persistence, backup, retention and owner
  secrets/
    README.md                       # edit/encrypt/rotate/recover, no values
    catalog.yml                     # names/owners/consumers/rotation only
    core.sops.yml
    publisher.sops.yml
    n8n-consumers/<consumer>.sops.yml
    hermes-projects/<project>.sops.yml
  evidence/
    README.md                       # only redacted schemas/approved baselines
    core-1/paperclip-baseline.yml
  playbooks/
    {bootstrap,core,publisher,site,backup,restore-core,restore-publisher,verify}.yml
  roles/
    base/ docker/ firewall/ cloudflared/ monitoring/ restic/
    paperclip_guard/ n8n/ hermes/ publisher/
  systemd/                          # source templates for timers/services
  tofu/
    cloudflare/                     # DNS, Tunnel, Access and R2 only
      versions.tf providers.tf variables.tf outputs.tf
      dns.tf tunnels.tf access.tf r2.tf imports.tf
      backend.example.hcl
      .terraform.lock.hcl

stack/
  common/
    service-contract.schema.json
  paperclip/
    compose.yml env.schema.yml README.md
  n8n/
    compose.yml env.schema.yml config/ ingress/ db/migrations/ README.md
  hermes/
    compose.yml.j2 env.schema.yml README.md
    projects/{README.md,project.schema.json,<project>.yml}
  publisher/
    README.md mapping.schema.json
    <selected-adapter>/              # created only after founder decision
  monitoring/
    probes.yml alert-rules.yml retention.yml

brands/
  README.md
  brand.schema.json
  _template.yaml
  fixtures/{brand-alpha,brand-beta}.yaml
  <brand>.yaml

n8n/
  README.md
  workflow.schema.json
  workflows/
    research/ ideation/ drafting/ approval/ publishing/ metrics/
  consumers/
    README.md consumer.schema.json <consumer>.yml
  fixtures/
    consumers/{project-alpha,project-beta}/
    workflows/

prompts/
  README.md prompt.schema.json
  research/ ideation/ caption/ visual/ metrics/
  fixtures/

scripts/
  lib/                             # shared strict-shell/Python helpers
  check controller
  infra-capture infra-check infra-plan infra-apply infra-verify
  infra-backup infra-restore-drill release-record
  n8n-export-normalize n8n-consumer-check n8n-consumer-import
  n8n-consumer-verify n8n-consumer-drift
  hermes-project-check hermes-project-import hermes-project-verify
  publisher-check publisher-smoke
  approval-ingress-check telegram-webhook-reconcile
  media-render media-purge

docs/
  decisions/                       # founder decision packets and outcomes
  runbooks/                        # bootstrap, deploy, rollback, restore, rotate
  operations/                      # redacted drill/deployment summaries
  plans/                           # architecture + this implementation plan
```

Generated plans, decrypted values, test media, temporary checkouts, OpenTofu
state and runtime receipts go under a gitignored `.artifacts/` directory or a
fresh `mktemp` directory. A generated file is committed only when it is a
portable runtime input whose generator and normalized-diff check are also
committed.

The first implementation PR must append `.github/` ownership to the root
`AGENTS.md` table and reconcile the outdated `stack/README.md`, `n8n/README.md`
and `.gitignore` comments with the merged two-host/SOPS design. It must not
restructure unrelated founder content in `README.md`.

## 5. Standard command contract

Every operator-facing command runs from any current directory by resolving the
repository root, supports `--help`, uses nonzero exit codes for failed gates and
redacts secrets. Commands that mutate production also support `--plan` or have
a separate plan command, require `--limit <exact-host-or-role>` and print the
Git commit they intend to apply.

| Command | Required behavior |
| --- | --- |
| `scripts/controller` | Build/run the exact controller image/toolchain from `toolchain.lock.yml`, including `versions` and guarded cache-cleanup subcommands; never fall back silently to global Ansible, OpenTofu, SOPS or Python. |
| `scripts/check` | Run every read-only repository check in the same order locally and in CI. |
| `scripts/infra-capture --limit core-1` | Read live state only; normalize/redact it; refuse to write secrets; produce `.artifacts/` evidence for explicit review. |
| `scripts/infra-plan --limit …` | Validate clean reviewed input, decrypt only in memory, run Ansible check/diff where safe, render Compose/OpenTofu plans and emit a redacted plan digest. |
| `scripts/infra-apply --limit … --release <tag>` | Require the exact annotated release tag, matching plan digest and interactive founder confirmation; serialize host changes and stop on failed verification. |
| `scripts/infra-verify --limit …` | Run host, route, service, capacity, secret-boundary and backup-age probes without changing desired state. |
| `scripts/infra-backup --limit …` | Create application-consistent dumps, run restic, enforce retention and remove all but the permitted local latest dump. |
| `scripts/infra-restore-drill --role …` | Restore into a disposable target, verify the application and destroy only the explicitly named disposable resources after evidence capture. |
| `scripts/n8n-consumer-*` | Validate/pin/import inactive/verify/drift-check one manifest and exact clean source checkout; never clone with a token on the host. |
| `scripts/hermes-project-*` | Validate/render/import inactive/verify one project and prove unique mounts/state/credentials before activation. |
| `scripts/publisher-*` | Validate project/workspace/account ownership, test authorization boundaries and exercise publish lifecycle only with fixture or founder-approved accounts. |
| `scripts/media-*` | Render Bangla-safe overlays from committed templates, enforce quotas/TTL and prove purge or selected archive behavior. |
| `scripts/release-record` | Compare the deployed commit/digests/receipts with the release tag and write only a redacted operational summary. |

All shell entry points use strict mode, quote variables, avoid unresolved
destructive targets and share common validation helpers. Machine-readable
results use versioned JSON/YAML schemas; human summaries are derived from the
same result, not maintained independently.

## 6. Shared contracts that must exist before services

### 6.1 Toolchain and supply-chain lock

`toolchain.lock.yml` records each executable, version, source URL, checksum or
container digest and update owner. The controller `Containerfile` uses a base
image pinned by digest. Python dependencies use hashes; Ansible collections use
exact versions; GitHub Actions use full commit SHAs; OpenTofu commits its
provider lock file for every supported architecture. Application images live in
`infra/services/images.lock.yml` and Compose refers to digests from that lock.

An update PR changes the lock, renders all Compose projects, runs disposable
tests and records the upstream release notes reviewed. Production never resolves
an image tag or package version during an application deploy.

### 6.2 Service registry

Every service entry declares:

- stable ID, host role, Compose project and source directory;
- image lock key/version, health probe and expected dependency ordering;
- loopback/private-network/public-route exposure;
- CPU/memory/PID/log limits and start priority;
- persistent volumes and their data classifications;
- backup adapter, RPO/RTO, retention and restore probe;
- secret catalog references, never values;
- monitoring/alert owner and rollback command.

CI fails when a Compose service or persistent volume has no registry entry.

### 6.3 Public-route manifest

Each hostname/path declares its host, tunnel, origin, human or machine caller,
Access policy, exact allowed methods/paths, application authentication, WAF/rate
limit, data class, negative probes and owner. The default is no route. A
machine-route exception cannot share an administration hostname and cannot use
`Bypass` without an explicit reviewed manifest. OpenTofu and host tunnel config
are generated or validated against the same manifest so the edge and origin
cannot drift independently.

### 6.4 Secret catalog and SOPS boundaries

The catalog declares secret ID, owner, allowed service/project, purpose,
rotation trigger, recovery location and target host file. CI checks structure,
encrypted values, required public recipients and the presence of a SOPS MAC;
`infra-plan`, which has an age key in memory, additionally decrypts to a sink to
verify the MAC and schema. CI does not receive a production age private key.

Ansible renders only selected values into root-owned `0600` files with
`no_log: true` and `diff: false`. No full decrypted secret file is copied to a
host or workspace. The n8n drift-watchdog owner key is a platform secret in
`core.sops.yml`, host-only, and is rejected by every workflow/Hermes credential
allowlist.

### 6.5 Persistence and retention catalog

Every writable path/volume is one of:

- **rebuildable:** regenerate from Git and exclude from backup;
- **ephemeral:** quota-bound and purged on a defined event/TTL;
- **retained:** application-consistent backup with an RPO/RTO and restore test;
- **provider-owned:** external grant/object with a versioned reconciliation
  probe.

Unknown writable paths fail the Compose/Ansible checks. Docker and journald logs
are bounded. n8n executions, publisher histories, Hermes sessions and media each
have explicit project-aware retention; no service may use “keep forever.”

### 6.6 Release and deployment receipts

A release identifies the exact Git tag/commit, toolchain lock digest, service
image digests, target role, approved plan digest and schema versions. Each host
stores its applied release under `/etc/dholbeat-release`; n8n/Hermes registrations
store separate root-owned receipts with source commits and content hashes.
Receipts are included in the appropriate encrypted backup and exposed to
verification only in redacted form.

An emergency host edit is allowed only to restore safety. The incident runbook
records it immediately, and the next PR either codifies or reverses it. Drift
remains a visible failure until reconciliation; the dashboard is never promoted
to source of truth.

## 7. Founder decision gates

Agents prepare evidence and alternatives; they do not silently close these
gates.

| Gate | Required decision/evidence | What may proceed before it | What is blocked |
| --- | --- | --- | --- |
| `DG-01 publisher` | Exact self-hosted Postiz versus Mixpost edition test, multi-project authorization results, measured 6-GB footprint and monthly-cost table; founder selects one | Publisher-neutral schema, fixtures, host baseline, backup/tunnel modules | Selected publisher Compose/role, provider connections and production publish tests |
| `DG-02 approval interface` | Custom Telegram bot versus a project-scoped Hermes gateway; founder selects caller and recovery behavior | Approval ledger/state machine, generic verified-ingress contract and synthetic tests | Production Telegram bot registration and live approval callback |
| `DG-03 media archival` | Purge-only versus the open B2 archival option, with retention/cost; short-lived provider-fetchable R2 delivery objects remain a separate publisher concern | Ephemeral workspace, quota, purge and test renderer | Production archive lifecycle and restore expectation |
| `DG-04 per-brand X` | Value/cost choice per brand | Generic optional channel support | Real X credential/provider connection for that brand |
| `DG-05 public product identity` | Domain registration/repository naming decisions already listed in `README.md` | All `chayan.me` operational infrastructure | Marketing-domain publication only |

If a gate changes monthly cash, its decision packet includes the complete
founder wallet, not merely the incremental software line. This plan adds no new
paid tooling: Ansible, Docker Compose, SOPS/age, restic, OpenTofu and the test
toolchain are $0 software. GitHub CI must stay within the repository's existing
allowance or the same controller runs locally; it must not introduce a paid CI
tier without founder approval.

## 8. Work-package dependency map

| ID | Deliverable | Depends on | Production mutation |
| --- | --- | --- | --- |
| `WP-00` | Repository hygiene, pinned controller and common CI entry point | None | None |
| `WP-01` | Schemas, registries and generic negative fixtures | `WP-00` | None |
| `WP-02` | Brand/prompt/workflow contracts | `WP-00`, `WP-01` | None |
| `WP-03` | Inventory, SOPS policy, secret catalog and release contract | `WP-00`, `WP-01` | None |
| `WP-04` | Read-only `core-1` discovery and approved Paperclip baseline | `WP-00`, `WP-03` | Read-only only |
| `WP-05` | Shared Ubuntu/Docker/firewall baseline roles | `WP-00`, `WP-01`, `WP-03`, `WP-04` | Disposable host first; production only after review |
| `WP-06` | Cloudflare/R2 OpenTofu imports and host tunnel config | `WP-01`, `WP-03`, `WP-04` | Import/read first; apply only after reviewed no-change plan |
| `WP-07` | Application-aware backup and disposable restore foundation | `WP-03`, `WP-05`, `WP-06` | Backup installation; no app replacement |
| `WP-08` | Paperclip parity adoption | `WP-04`–`WP-07` | Planned restart window only |
| `WP-09` | w3exam migration evidence, safe cleanup and `B_core` admission gate | `WP-08` plus separately approved w3exam migration | Explicit destructive approval required |
| `WP-10` | Central n8n runtime and durable control database | `WP-05`–`WP-07`, `WP-09` | `core-1`, inactive workflows first |
| `WP-11` | Generic n8n consumer registration and PoriPati canary | `WP-01`, `WP-10` | Inactive canary; business flows remain off |
| `WP-12` | Per-project Hermes runtime/registration | `WP-01`, `WP-05`, `WP-07`, `WP-09` | Inactive profiles first |
| `WP-13` | `publish-1` and selected publisher adapter | `DG-01`, `WP-05`–`WP-07` | New host; fixture accounts first |
| `WP-14` | Approval ledger, verified ingress and approval adapter | `WP-02`, `WP-10`, then `DG-02` for live bot | Synthetic until founder chooses interface |
| `WP-15` | Research and ideation workflows | `WP-02`, `WP-10` | Per-brand schedule stays disabled until acceptance |
| `WP-16` | Drafting, deterministic Bangla overlay and media lifecycle | `WP-02`, `WP-10`, `DG-03` for archive mode | Synthetic media/provider credentials first |
| `WP-17` | Approval-bound publisher workflows and workspace mappings | `WP-11`, `WP-13`, `WP-14`, `WP-16` | Fixture accounts, then founder-approved real accounts |
| `WP-18` | Metrics ingestion and feedback loop | `WP-02`, `WP-13`, `WP-17` | Read-only provider scopes first |
| `WP-19` | Monitoring, capacity attribution and seven-day canaries | Runtime package being measured | Alerts/probes only |
| `WP-20` | Release, rollback and clean-room replacement-host drill | All production-bound packages | Disposable rebuild, then scheduled drill |

`WP-02`, `WP-05`, `WP-06` and the generic portions of `WP-14` may run in
parallel after their prerequisites because they own disjoint paths. Production
work remains strictly gated even when code preparation is parallel.

## 9. Detailed work packages

Every package below must satisfy the global definition of done in §12 in
addition to its own exit criteria.

### WP-00 — Repository and controller foundation

**Owns:** `.github/`, `toolchain.lock.yml`, `infra/controller/`, common script
helpers, `.gitignore`, and small ownership/documentation corrections.

**Implement:**

1. Add `.github/` to the `AGENTS.md` ownership table as a tooling lane.
2. Correct the old single-host/password-manager-only statements in
   `stack/README.md`, `n8n/README.md` and `.gitignore`; keep `.env` forbidden and
   explicitly document that only `infra/secrets/**/*.sops.yml` ciphertext is
   trackable.
3. Add `toolchain.lock.yml`, a digest-pinned controller `Containerfile`, hashed
   Python dependencies and exact Ansible collection versions. Include SOPS,
   age, OpenTofu, JSON/YAML schema validation, ShellCheck, secret scanning,
   Compose and Ansible lint tools.
4. Implement `scripts/controller` and `scripts/check`. The controller image is
   reproducible from source and may also be published by CI for convenience;
   GHCR availability or a laptop cache is never the only recovery path. Use a
   task-specific bounded cache, report its size and provide a guarded cleanup
   command so the founder's laptop does not retain dependency trees or build
   layers indefinitely.
5. Add a read-only CI workflow pinned to action commit SHAs. It invokes only
   `scripts/check`; no second CI-only implementation is allowed.
6. Gitignore `.artifacts/`, OpenTofu state/plan output, controller caches,
   restored databases and all generated media.

**Verify:** a clean clone can build/pull the locked controller, print identical
tool versions and run the foundation `scripts/check` on both `amd64` CI and the
founder's supported controller architecture. Cleanup removes only labelled
task caches and leaves no project virtualenv, `node_modules` or generated media.
A deliberately floating image, unhashed dependency, unpinned action and
plaintext `.env` fixture each fail.

**Exit evidence:** CI link, controller lock digest, local/CI command parity and
an explicit `$0/month` tooling note. No host connection occurs.

### WP-01 — Schemas, registries and adversarial fixtures

**Owns:** `infra/schemas/`, `infra/services/`, component schemas and fixture
directories.

**Implement:**

1. Add versioned JSON Schemas for inventory, services, routes, volumes, secret
   catalog entries, releases, brands, prompts, workflows, n8n consumers, Hermes
   projects and publisher mappings.
2. Add generic positive fixtures plus one invalid fixture per security or
   durability rule: duplicate ID, cross-project credential, public origin port,
   missing Access policy, unbounded log/volume, floating source ref, shared
   Hermes mount/state, unknown writable path, missing retention, and unapproved
   publish transition.
3. Validate cross-file uniqueness and references, not just individual YAML
   shape. A service's image, route, volume, secrets and backup adapter must all
   resolve to declared IDs.
4. Make fixtures generic. Validation code cannot contain a PoriPati, w3exam or
   Dholbeat special case; real registrations are data-only instances of the
   same schemas.
5. Version schema changes and provide a migration note when a deployed manifest
   would stop validating.

**Verify:** mutation tests demonstrate that every invalid fixture fails for the
intended reason, while two credential-free project/brand fixtures validate and
round-trip deterministically.

**Exit evidence:** schema inventory, positive/negative fixture matrix and
`scripts/check` integration. No host connection occurs.

### WP-02 — Brand, prompt and workflow source contracts

**Owns:** `brands/`, `prompts/`, credential-free Dholbeat workflow source
conventions under `n8n/`, and their tests.

**Implement:**

1. Replace the prose-only brand shape with `brand.schema.json`. Private chat
   IDs and tokens become logical secret references; only public handles and
   non-secret editorial configuration live in a profile.
2. Preserve the extension invariant: adding a brand is one profile plus secret
   and publisher mapping data, never a workflow/script change.
3. Define prompt front matter: stable ID/version, required variables, output
   JSON schema, model capability class, token/cost ceiling, retry policy and
   safety/disclosure rules. Prompts remain brand-neutral and load voice/context
   from the profile.
4. Define a normalized n8n export format and index. Remove volatile UI fields,
   reject embedded credentials/secrets and give every workflow a stable logical
   ID, input/output schema, timeout, trigger class, retention and owner.
5. Add workflow/prompt compiler tests with both brand fixtures. Fail any prompt
   or workflow containing a real brand name, autonomous publish path, AI-avatar
   testimonial path or image-model Bangla-text instruction outside declarative
   test data.
6. Define content revision and idempotency keys used by every later pipeline:
   `project/brand/content/revision` and
   `project/brand/content/revision/channel/scheduled_at`.

**Verify:** both fixture brands compile through every prompt/workflow interface
without code changes; invalid secret references, missing approval stages and
unbounded cost/retry policies fail.

**Exit evidence:** schema/examples, normalized-export golden tests and a written
workflow change/export procedure. No live n8n edit is needed.

### WP-03 — Inventory, SOPS and release identity

**Owns:** `.sops.yaml`, `infra/inventories/`, `infra/secrets/`, release schema
and non-secret variable files.

**Implement:**

1. Commit stable `core-1`/`publish-1` roles and public endpoints; temporary IP
   overrides stay local and are never an implicit recovery input.
2. Define all non-secret variables and JSON Schema validation. Production
   inventory contains no passwords, tokens or private keys.
3. Commit `.sops.yaml` with the exact nested-secret path expression and founder
   plus break-glass public age recipients. Add values-only encrypted files only
   after the real recipients are confirmed; never commit example ciphertext
   encrypted to a throwaway production path.
4. Add a non-secret secret catalog with owner, allowed consumers, target file,
   rotation trigger and recovery account. Render one service/project subset at
   a time rather than decrypting the whole catalog to a host.
5. Define release and runtime receipt schemas, `/etc/dholbeat-release`, plan
   digest handling and manual annotated-tag convention.
6. Add CI structural SOPS checks and apply-time in-memory decrypt/MAC/schema
   verification. Logs and artifacts are scanned again after plan/apply.

**Verify:** wrong recipients, plaintext YAML values, misplaced secret files,
unknown secret references, reused cross-project secret IDs and a simulated
leaked-key rotation all fail or follow the documented full-secret rotation
path.

**Exit evidence:** recipient fingerprints confirmed by the founder, catalog
review, recovery-account checklist and secret-rotation dry run. No plaintext is
committed or emitted.

### WP-04 — Read-only `core-1` discovery and parity baseline

**Owns:** `scripts/infra-capture`, capture normalization/redaction code,
`infra/evidence/core-1/` and the Paperclip baseline schema.

**Implement:**

1. Capture OS/kernel, installed package versions, users/SSH settings, firewall,
   listening ports, Docker/Compose versions, images/digests, projects,
   containers, networks, volumes/mounts, resource use, systemd units, timers,
   cron, tunnel routes, backup jobs and disk ownership without changing them.
2. Capture Paperclip's normalized effective Compose config, environment **key
   names plus value hashes**, image digest, volume map, health contract and
   current public-route behavior. Never capture a plaintext value.
3. Discover all w3exam resources but classify them as externally owned. This
   package neither migrates nor deletes them.
4. Produce a human-reviewed diff between observed state and the intended
   architecture. Unknown listeners, mounts, cron jobs, backup jobs or disk
   consumers block mutation until classified.
5. Commit only the approved redacted baseline and stable facts. Raw capture
   remains in `.artifacts/` and is deleted after review.

**Verify:** run the capture twice with no live changes and obtain identical
normalized output. Seed a secret-shaped fixture and prove redaction/scanning
prevents it entering the baseline.

**Exit evidence:** founder-approved baseline commit, disk ownership report,
Paperclip parity hash and a list of separately owned/migration-blocked assets.
Production access is read-only.

### WP-05 — Shared host baseline

**Owns:** Ansible configuration, fixture inventory, base/Docker/firewall/
cloudflared prerequisites, common systemd templates and Molecule/disposable-host
tests.

**Implement:**

1. Assert Ubuntu 24.04, architecture and minimum resources before mutation.
2. Configure the named admin user, key-only SSH, sudo, time sync, security
   updates/reboot policy, UTC host timezone, bounded journald/logrotate and the
   tested break-glass path.
3. Install a declared Docker Engine/Compose range from a pinned repository/key;
   configure log rotation, live-restore policy if verified, and no public daemon
   socket.
4. Apply default-deny firewall rules. Application ports bind only to loopback or
   private Compose networks; SSH uses the declared allowlist/access method.
5. Create service directories with explicit owner/mode. No role may create a
   writable directory missing from the persistence catalog.
6. Use handlers, tags, `serial: 1`, check-mode support and a second-connection
   safety probe before an SSH/firewall handler closes the current path.

**Verify:** converge a disposable Ubuntu host twice; the second run has no
unexpected changes. Negative tests cover wrong OS, public application port,
unbounded Docker logs, missing disk space and failed second SSH connection.

**Exit evidence:** disposable-host transcript, resolved package manifest and
idempotence report. Production bootstrap is a separate founder-confirmed run.

### WP-06 — Supported external control plane as code

**Owns:** `infra/tofu/cloudflare/`, route generation/verification and host
`cloudflared` config. It does not own VPSDime lifecycle.

**Implement:**

1. Select and document an encrypted, locked remote OpenTofu state backend that
   stays within budget. Implement a two-stage bootstrap because the backend
   cannot own the bucket or locking mechanism that stores its own state: create
   that root only through the committed controller command/runbook, record its
   immutable identifiers and postconditions, then manage every supported child
   resource from remote state. Do not proceed with local-only production state.
2. Import existing `team.chayan.me`, its tunnel/DNS/Access objects and private
   R2 resources before any create/update. Record provider/resource IDs as
   non-secret variables and commit the provider lock.
3. Declare one tunnel/credential boundary per host, `team.chayan.me`,
   `n8n.chayan.me`, `hooks.chayan.me`, `publish.chayan.me`, default-deny human
   Access applications, the scoped publisher service-token policy, machine
   route rules and separate private-backup/public-media buckets.
4. Render/validate host ingress config from the same route manifest. No route
   may cross host boundaries or expose an origin port.
5. Implement route probes for unauthenticated, founder identity, valid/invalid
   service token, allowed/forbidden method/path, direct IP and alternate DNS.
6. Keep production application secrets out of OpenTofu. Backend/provider
   credentials enter only through the controller environment and SOPS/password
   manager workflow.

**Verify:** imported state yields a reviewed no-change plan before convergence;
fixture plans reject whole-host bypass, missing Access, shared tunnel tokens,
public private-bucket access and origin exposure. Starting from a clean clone,
prove backend discovery/recovery and lock contention on a disposable state
object without copying a local state file or shell history.

**Exit evidence:** no-change import plan, state-recovery drill and route-test
matrix. Any live change requires a separately reviewed plan and founder apply.

### WP-07 — Backup and restore foundation

**Owns:** restic role, per-application dump adapters, timers, retention, backup
monitoring and disposable restore harness.

**Implement:**

1. Create distinct private R2 repositories and credentials per host. The public
   media bucket is never a restic repository and has different credentials.
2. Build application-aware dump adapters. PostgreSQL/MySQL/other databases dump
   to a uniquely named temporary file, restic captures it, and a trap removes
   it; raw live database directories are excluded.
3. Back up Compose/config, runtime receipts and only catalogued retained state.
   Exclude images, caches, logs, ephemeral media and rebuildable exports.
4. Enforce `keep-daily 7`, `keep-weekly 4`, prune/check sequencing and no
   overlapping host backups, Hermes browser work or publisher upgrades. Keep at
   most one local latest dump.
5. Add backup-age/size alerts and a quarterly plus post-upgrade restore timer or
   runbook. A repository check alone is not a restore test.
6. Implement disposable restore targets with explicit names and guarded
   cleanup; never restore over production during a drill.

**Verify:** corrupt/missing snapshot, wrong host credential, overlapping lock,
failed dump and full disk all fail safely and alert. Restore a fixture database
and retained file, then prove excluded data is regenerated rather than restored.

**Exit evidence:** first successful encrypted snapshot, disposable restore
report, measured duration and RPO/RTO comparison. No existing legacy backup is
removed yet.

### WP-08 — Paperclip parity adoption

**Owns:** `stack/paperclip/`, `paperclip_guard` role, Paperclip backup/restore
adapter and its runbook.

**Implement:**

1. Express the approved `WP-04` baseline as Compose/config/SOPS desired state
   without changing image digest, effective environment, mounts or hostname.
2. Normalize rendered candidate and captured baseline using the same code.
   Unexplained differences fail before Compose is invoked.
3. Require a fresh `WP-07` dump, successful disposable restore, healthy current
   instance, founder-approved restart window and rollback snapshot.
4. Converge with exact image digest and data paths. Container recreation is
   allowed; data migration or image upgrade is not part of adoption.
5. Recapture and diff after convergence, verify `team.chayan.me` through Access,
   verify direct-origin failure and observe through the rollback window.
6. Disable an old backup/cleanup job only after its replacement and restore
   evidence pass, one job at a time.

**Verify:** candidate drift in a secret hash, mount, image, route, restart policy
or health contract blocks apply. A disposable clone restores and reaches the
expected health endpoint.

**Exit evidence:** zero unexplained before/after diff, unchanged image digest,
health/Access probes, restore report and rollback sign-off.

### WP-09 — Capacity prerequisite and safe cleanup

**Owns:** disk attribution/cleanup scripts, capacity gate and evidence; it does
not own the w3exam migration implementation.

**Implement:**

1. Require evidence that the separately approved w3exam migration completed and
   its rollback window closed. Do not infer this from stopped containers.
2. Re-run inventory and map every candidate image, volume, dump and backup file
   to an owner and recovery source. Unknown ownership means “do not delete.”
3. Produce a reviewed deletion plan with exact IDs/paths, sizes, last-use
   evidence and recovery method. Avoid globs and broad Docker prune commands.
4. After explicit founder approval, remove only listed assets, then rerun
   Paperclip health/restore and disk inventory.
5. Record `B_core`. It must be at most 14 GB before n8n or Hermes admission; an
   update must preserve at least 8 GB free. Otherwise stop with measured
   cleanup/resize/move options and a monthly-cost table.

**Verify:** dry run is default; unknown/mounted/in-use resources cannot enter
the apply set; interrupted cleanup remains resumable and does not remove the
last valid backup.

**Exit evidence:** separately approved migration reference, deletion receipt,
post-cleanup health/backup checks and measured `B_core`. This is the only work
package authorized to remove the specifically reviewed legacy assets.

### WP-10 — Central n8n runtime and control database foundation

**Owns:** `stack/n8n/`, the n8n Ansible role, platform database migration
harness, n8n health/backup adapter and admin-route configuration.

**Implement:**

1. Deploy one digest-pinned n8n Community Compose project with its own
   PostgreSQL database, private network, named persistent volumes, health checks,
   restart policy, resource/log limits and explicit execution/binary retention.
   No host port is public.
2. Configure `N8N_EDITOR_BASE_URL`, `N8N_WEBHOOK_URL`, proxy hops, timezone,
   encryption key, concurrency one and execution-data pruning entirely from
   committed configuration plus SOPS values.
3. Place `n8n.chayan.me` behind founder-only Access and reserve
   `hooks.chayan.me` for the narrow verified ingress in `WP-14`. The editor,
   public API and test/waiting webhook paths never use the machine route.
4. Add a versioned migration harness under `stack/n8n/db/migrations/` for
   Dholbeat-owned control data. Platform migrations use a separate database or
   schema/role from n8n internals; no migration edits n8n's private tables.
5. Provision Registered Community activation from the founder operations email,
   catalogue the recovery account/license in the password-manager/SOPS model and
   restore-test activation. If unavailable, names/tags remain the only namespace
   and tests must not assume folders.
6. Create the drift-watchdog API key through a supported pinned-version API/CLI
   bootstrap path. Render it only to root-owned mode `0600`
   `/etc/dholbeat/n8n-consumer-drift.env`; do not put it in n8n or Hermes
   environments or in the n8n credential store.
7. Add application-aware PostgreSQL dump/restore and inactive workflow
   reconciliation. An empty fresh database plus Git/SOPS must reach the same
   configuration without using the editor.

**Verify:** Compose render, migration up/down or forward-restore test, second
Ansible run, backup/restore, Access/direct-origin probes, bounded execution
retention and an empty-instance reconcile all pass on a disposable host. A
workflow cannot access the owner watchdog key.

**Exit evidence:** pinned versions/digests, rendered-config hash, inactive fresh
restore, Registered Community recovery result and 24–72-hour idle/fixture
resource baseline. No business workflow is active.

### WP-11 — Generic n8n consumer lifecycle and first external canary

**Owns:** `n8n/consumers/`, consumer fixtures, and
`scripts/n8n-consumer-{check,import,verify,drift}`.

**Implement:**

1. Validate one consumer manifest against `WP-01`, including immutable source
   commit, clean source checkout, workflow namespace, credential names/purposes,
   outbound hosts, trigger classes, timeout/rate, route declarations, retention,
   rollback and restore behavior.
2. Normalize and hash credential-free workflow JSON. Reject secret literals,
   embedded credential values, duplicate/cross-consumer IDs, Execute Command,
   SSH, local filesystem, unreviewed nodes, undeclared network targets and any
   credential reference not allowed by the manifest.
3. Generate a redacted import plan, require founder confirmation, import
   inactive using only supported pinned-version API/CLI surfaces, run offline
   smoke tests and write a root-owned receipt containing repository, exact
   commit, workflow hashes and resolved allowed credential IDs.
4. Bootstrap only the selected consumer's credentials from its SOPS file. A
   platform or another consumer credential can never be selected by name,
   purpose or resolved ID.
5. Implement rollback as an explicit receipt-backed reconcile to the preceding
   reviewed source; rollback does not resurrect credentials or workflows absent
   from that receipt.
6. Run a locked five-minute drift timer. Re-export/hash live workflows and
   resolved credential IDs; deactivate only a new, changed or cross-credential
   workflow, alert and require a clean reviewed import before reactivation.
7. Prove project neutrality with `project-alpha` and `project-beta`. Mutate one
   with the other's dummy credential and prove only the violating workflow is
   deactivated within five minutes.
8. Register the real PoriPati Track-1 canary only as declarative data pinned to
   an exact cross-reviewed commit in its repository. It imports inactive,
   reaches only its typed HTTPS test API, stores no successful PII execution and
   retains minimized failures for at most 14 days. Unfinished business flows
   remain inactive.
9. If a private source must be fetched, mint a fresh actor-specific GitHub App
   token on the controller for that command, verify the bot identity and discard
   the token with the ephemeral checkout. Never use or persist the founder's
   personal token and never forward a Git credential to either host.

**Verify:** clean import, repeated idempotent import, source-hash mismatch,
moving ref, missing repository, forbidden node, undeclared host/credential,
cross-project dummy credential, rollback and restored-instance reconciliation.
The host never receives a personal GitHub token.

**Exit evidence:** two generic fixture receipts, drift-timer alert/deactivation
evidence, PoriPati inactive-canary receipt and proof that no duplicate n8n/admin
hostname exists.

### WP-12 — Reusable Hermes project lifecycle

**Owns:** `stack/hermes/`, Hermes role/project manifests and
`scripts/hermes-project-{check,import,verify}`.

**Implement:**

1. Pin one Hermes image/version, but render one container/service per enabled
   project as the documented resource-isolation/blast-radius exception. Do not
   use the default in-container multi-profile deployment.
2. Give every project a unique resolved host directory mounted at `/opt/data`,
   workspace, local state-backend path, credential file, log path, network and
   cgroup limits. Never share a local database or remote memory workspace.
3. Run non-root without Docker socket, host root, Paperclip/product mounts,
   publisher credentials or another project's files. Default outbound, tool,
   command, filesystem and caller permissions to deny and render only manifest
   allowlists.
4. Import prompt/skill/schedule configuration from the exact clean source commit
   into an inactive container, hash it and write a root-owned project receipt.
   Dholbeat-owned configuration remains canonical here; external configuration
   remains in its owner repository.
5. Enforce an approximately 2-GB aggregate envelope and one active agent job
   across all Hermes containers using per-container limits plus a host-global
   systemd lock/scheduler. A per-profile 2-GB allocation is invalid.
6. Keep every profile noncritical and non-public. A later selected Telegram
   gateway receives only its own bot token and forwards verified input to the
   `WP-14` ledger path; it cannot approve, mutate durable state or publish.
7. Back up only manifest-declared retained state. Rebuildable prompts/skills and
   caches restore from Git; unknown or shared state leaves that profile inactive.

**Verify:** two generic fixtures have distinct rendered mounts, state paths,
secrets and networks; cross-read, shared-backend, duplicate bot token, forbidden
tool/network and simultaneous-job tests fail safely. Destroy and recreate one
fixture without affecting the other.

**Exit evidence:** fixture receipts, rendered-boundary diff, one-job lock test,
aggregate resource measurements and inactive restore test. No approval or
publishing deadline depends on Hermes.

### WP-13 — `publish-1` and the selected publisher

**Owns:** publisher-neutral mapping contract, then the founder-selected adapter,
publisher role/Compose, dump/restore adapter and publisher runbooks.

**Precondition:** `DG-01` is closed in a committed decision record. No agent may
infer the choice from the current default language in `README.md`.

**Implement:**

1. The decision packet runs the same fixture tests against the exact available
   Postiz and Mixpost editions that can be evaluated without an unapproved
   purchase: project/workspace authorization, API ownership,
   immediate/scheduled/cancel/delete/token-refresh behavior, backup/restore,
   6-GB/30-GB footprint, update headroom and full monthly cost.
2. After selection, the founder manually orders `publish-1` in the existing
   VPSDime account and attaches the approved bootstrap public key. Everything
   after first SSH uses `WP-05`–`WP-07` code.
3. Commit only the selected complete stack. Pin all images; keep database,
   cache, queue/workflow-engine and internal ports private; disable public
   registration after founder bootstrap; bound every log/history/upload path.
4. Expose `publish.chayan.me` through its own tunnel. Human UI uses founder-only
   Access; n8n uses a distinct renewable Access service token plus a scoped
   application credential. Direct origin and state services remain unreachable.
5. Define project organization/workspace and brand account mapping as data.
   Provider connections and OAuth grants are catalogued per project/brand and
   never silently reused.
6. Use public media objects only through the selected lifecycle policy and a
   dedicated credential. Private restic objects/bucket credentials never enter
   the publisher.
7. Implement application-aware backup/restore, update rollback and a duplicate-
   post kill switch before connecting real accounts.

**Verify:** two generic project/workspace fixtures plus a no-account third
fixture pass create/read/write negative authorization tests. An integration
cannot schedule into, read or reuse credentials from another project. A seven-
day fixture canary stays below 4.5-GB peak RAM, 18-GB steady disk and preserves
8 GB update headroom, or the founder reviews measured alternatives.

**Exit evidence:** founder decision record, exact edition/version, new-host
convergence/idempotence, authorization matrix, restore/update drill and measured
canary. Real social accounts are a later explicit gate.

### WP-14 — Durable approval ledger and verified ingress

**Owns:** Dholbeat control migrations, approval-state contract, generic ingress
source/config, Telegram/selected-interface adapter and approval tests.

**Implement:**

1. Add a durable, migration-managed control database/schema outside n8n private
   tables. Store project ID, brand ID, content ID, revision, content SHA-256,
   state, minimal actor reference, event/update ID and timestamps—never message
   bodies, phone numbers, generated media or provider credentials.
2. Enforce `idea_pending` → `idea_approved` → `draft_pending` →
   `final_approved` → `scheduled` → `published`, plus rejected, cancelled and
   failed outcomes. Only approved functions/API transitions may write state;
   audit events are append-only.
3. Editing content creates a new revision/hash and makes every earlier approval
   ineligible. Scheduling requires the current revision's `final_approved`
   record; a retry cannot manufacture or inherit approval.
4. Scope database/API access by project. Generic two-project tests prove a
   caller cannot read or mutate another project's records. Dholbeat publishing
   code receives only the minimum transition/read capability.
5. Implement the narrow verifying ingress in front of n8n from committed code.
   On `hooks.chayan.me`, accept only declared `POST /webhook/*` paths, enforce
   body-size/rate limits and validate each bot's SOPS-managed Telegram secret
   before forwarding. Deny editor/API/test/waiting paths and every other method.
6. Deduplicate/reject replayed Telegram update IDs and bind every callback to
   project, brand, content revision and intended action. Positive, wrong-secret,
   missing-secret, replay, wrong-brand, stale-hash and oversized-body tests are
   required.
7. Keep the ingress adapter independent of `DG-02`. After the founder chooses
   custom bot or Hermes gateway, add only that adapter and secret/caller
   manifest; the ledger and publish gate do not change.
8. Reconcile Telegram webhook registration from code using the Bot API, its
   declared URL and SOPS secret; verify the resulting webhook state. Interactive
   `setWebhook` calls or dashboard-only bot configuration are drift.

**Verify:** migration restore, transition/property tests, concurrent duplicate
approval, edit-after-approval, forged callback, replay and cross-project tests.
The approval-ingress-to-publisher-job SLO instrumentation starts here even
before the publisher is live.

**Exit evidence:** schema/state diagram, test matrix, restored audit ledger,
route negative probes and founder-selected live-interface record. No synthetic
test can schedule without an explicit matching final approval.

### WP-15 — Research and ideation pipelines

**Owns:** research/ideation workflow exports, prompts, result schemas and
brand-profile inputs.

**Implement:**

1. A schedule enumerates enabled brand profiles; it never contains a hard-coded
   brand branch. Each run records project/brand, workflow and prompt versions.
2. Collect only declared sources/APIs with timeouts, rate limits, provenance and
   failure isolation. Store normalized evidence references and compact summaries,
   not unbounded copied pages or media.
3. Produce structured audience-interest findings and a small content-calendar
   proposal that validates against a committed schema. Enforce per-brand token,
   request and estimated-cost ceilings before calling an LLM.
4. Send ideas to the `WP-14` `idea_pending` state/approval interface. Nothing in
   research can create a draft approval, publisher job or provider post.
5. Support deterministic fixture replay with captured non-sensitive API
   responses so CI does not call paid providers or the live internet.
6. Fail one brand independently. Global concurrency and schedule staggering
   protect approvals/publishing from a long research job.

**Verify:** both fixture brands and two real brand profiles follow the same
workflow code; cost cap, invalid output, source timeout, duplicate schedule and
partial-brand failure tests pass. No workflow path bypasses idea approval.

**Exit evidence:** normalized exports, prompt/schema versions, fixture replay,
cost estimate and inactive production schedule ready for founder activation.

### WP-16 — Drafting, Bangla-safe rendering and media lifecycle

**Owns:** drafting/visual workflows, prompt templates, deterministic overlay
engine/templates, media commands and retention tests.

**Implement:**

1. Start only from a current `idea_approved` revision. Generate structured
   captions/creative instructions under brand tone, language, no-go and platform
   disclosure rules.
2. Image generation produces backgrounds/visual elements only. Bangla and other
   final text are rendered in a separate deterministic Pango/Cairo or equivalent
   shaping-capable step whose container, fonts and font checksums are pinned.
3. Commit templates, layout tokens, font license/source/checksum and golden test
   inputs. Generated images/videos remain under a quota-bound project/brand/
   content/revision work directory and are never committed.
4. Enforce no AI-avatar testimonials, no unsupported medical claims and
   platform-specific AI disclosure metadata. A content policy failure stops the
   revision rather than silently editing around the rule.
5. Hash captions, media and scheduling metadata into the revision presented for
   final approval. Any subsequent edit creates a new revision and invalidates
   the old final approval.
6. Purge working media after publish/cancel/failure TTL. If `DG-03` selects an
   archive, upload only the approved class with lifecycle/cost limits and prove
   retrieval; purge remains the local-disk rule.
7. Keep video generation optional and bounded. Large model/assets and provider
   downloads may not become permanent VPS caches.

**Verify:** Bangla shaping golden tests, missing-font failure, deterministic
overlay repeat, media quota/full-disk behavior, purge/archive lifecycle,
disclosure/no-go tests and edit-invalidates-approval tests.

**Exit evidence:** pinned renderer/font manifest, golden results, maximum disk
footprint, purge proof and two-brand drafts awaiting final approval. No output
publishes from this package.

### WP-17 — Approval-bound publishing

**Owns:** publishing workflow exports, publisher mapper, idempotency/kill-switch
logic and lifecycle tests.

**Implement:**

1. Resolve the project workspace and brand integration IDs only from validated
   mappings. Refuse an unknown, duplicate or cross-project mapping.
2. Immediately before job creation, query `WP-14` for the current revision/hash
   and `final_approved` state. Record the approval event ID in the publisher job
   receipt. A stale or edited revision fails closed.
3. Use the full idempotency key to prevent duplicate immediate/scheduled posts.
   Retries reconcile existing jobs before creating another.
4. Support create, schedule, cancel, delete, token refresh and provider failure.
   Cancelling/revoking approval prevents unsent jobs; already-published content
   is never represented as automatically reversible.
5. Hermes receives no publisher credential. n8n holds a project-scoped
   application credential and Cloudflare service token; workflows cannot select
   another project's credential.
6. Make channels profile-driven. A disabled or undecided X channel causes no
   code branch and no cost. Provider-specific limits/disclosures validate before
   job creation.
7. Add a host/project/brand kill switch that blocks new jobs without deleting
   audit/approval state. Its activation and recovery are tested and alerted.

**Verify:** immediate/scheduled/cancel/delete, duplicate retry, stale approval,
edited asset, wrong workspace, revoked credential, provider timeout and kill-
switch tests. First real-account posts require founder approval in a designated
test brand/channel and are manually observed.

**Exit evidence:** two-project negative authorization matrix, lifecycle receipts,
idempotency proof, approval-hash linkage and founder sign-off for any live canary.

### WP-18 — Metrics and feedback loop

**Owns:** metrics workflow exports, normalized metrics schema, retention and
research feedback inputs.

**Implement:**

1. Use read-only provider/application scopes where supported and resolve account
   ownership from the same publisher mapping as `WP-17`.
2. Normalize post ID, project, brand, channel, content revision, publish time,
   metric window and supported engagement fields. Keep raw provider payloads
   only for a short declared debugging window.
3. Make collection idempotent by provider post/window. Rate limits pause only
   that provider/brand and never block approval or publishing.
4. Produce compact, provenance-bearing aggregates for the next research run.
   Do not let metrics directly change cadence, spend or publish content without
   a reviewed profile change or founder approval.
5. Exclude audience PII and comments/messages unless a later data review adds a
   narrowly justified schema/retention policy.

**Verify:** fixture payloads for every enabled channel, duplicate windows,
missing/deleted posts, rate limit, revoked read scope, wrong-account mapping and
retention pruning. Two brands cannot see each other's metrics.

**Exit evidence:** normalized schema, fixture replay, provider-scope inventory,
retention proof and a research input generated without live provider calls.

### WP-19 — Monitoring, attribution and canaries

**Owns:** lightweight probes, systemd timers, bounded observation storage,
alerts, dashboards/reports and failure-injection tests.

**Implement:**

1. Prefer bounded code-owned probes over a disk-heavy resident time-series stack.
   Collect host/disk/RAM/OOM, Compose health, tunnel/route, backup age, release
   drift, n8n execution/retention/drift, Hermes job/queue/state growth, publisher
   queue/storage and approval-to-job latency into an eight-day rotating store or
   equally bounded sink.
2. Label n8n metrics by consumer and Hermes by project. Shared-host totals alone
   cannot identify the workload to pause.
3. Alert to a dedicated operations destination, not an approval callback. Alert
   credentials are scoped and catalogued.
4. Encode the `B_core +4/+5/+7 GB` steady/warn/pause gates, 8-GB update headroom,
   4.5-GB seven-day peak RAM threshold, any-OOM stop, publisher 18-GB steady
   threshold, backup age and five-minute drift deadline.
5. Measure verified approval ingress to publisher-job creation at p95 at most 60
   seconds with no wait over five minutes attributable to another project.
6. Add external least-privilege health probes and direct-origin negative probes.
   Health endpoints reveal no version, secret, project data or admin surface.
7. Failure-inject stopped containers, stale backup, full fixture disk, bad route,
   cross-credential workflow and Hermes lock contention; prove targeted pause and
   actionable alert behavior.

**Verify:** alert unit tests, eight-day retention bound, attribution, failure
matrix and seven-day canaries on each host. A threshold breach stops admission
or the offending workload; it does not silently buy capacity or raise limits.

**Exit evidence:** seven-day reports, SLO/threshold results, alert screenshots or
redacted payloads and founder-approved remediation for every breach.

### WP-20 — Release, rollback and clean-room recovery

**Owns:** release/rollback/rotation/replacement runbooks, release tooling,
quarterly drill schedule and final evidence mapping.

**Implement:**

1. Require an annotated release tag on a cross-reviewed commit. Record target
   roles, toolchain/image locks, plan digest and required backup snapshot before
   apply.
2. `infra-apply` writes `/etc/dholbeat-release`; `infra-verify` compares every
   host/service/consumer/profile receipt with the tag and reports drift.
3. Define rollback separately for stateless config, database migration, image
   update, route cutover and provider connection. Never treat a Git revert as a
   database rollback.
4. On clean disposable Ubuntu hosts, execute the complete sequence in §11 using
   only the reviewed Git tag, SOPS ciphertext plus password-manager age key,
   bootstrap access, exact external source commits and restic data.
5. Reconcile all n8n workflows and Hermes profiles inactive; an unavailable or
   mismatched external source leaves only that unit inactive. Restore retained
   state, run retention/deletion reconciliation and activate only after its
   verifier passes.
6. Test a temporary route, quiesce/final-dump/restore delta, stable-hostname
   cutover and rollback window. Do not cancel the old host until late-traffic
   observation and a second off-site snapshot complete.
7. Time and document RPO/RTO results. Schedule quarterly and post-upgrade drills;
   close every step that required shell history or undocumented knowledge.

**Verify:** destroy disposable hosts and rebuild both roles again from the same
inputs; second convergence is clean, both hosts operate independently, direct
origins remain closed, application restores pass and the exact deployed release
is observable.

**Exit evidence:** clean-room transcript, redacted receipts, RPO/RTO results,
rollback/cutover report and a list of remaining provider-owned grants. This is
the final portability gate, not optional documentation polish.

## 10. Rollout gates

No issue label, deadline or partially working service overrides these gates.

| Gate | Pass condition | Mandatory stop condition |
| --- | --- | --- |
| `G0 repository` | `WP-00`–`WP-03` checks pass from a clean clone; fixtures prove policy failures; no production secret enters CI | Tool/version depends on laptop globals, schema gaps, plaintext/unscoped secret or CI/apply coupling |
| `G1 discovery` | `WP-04` baseline is stable, redacted and founder-reviewed; every live listener/job/volume has an owner | Unknown state, suspected secret leak, or Paperclip baseline cannot be normalized |
| `G2 disposable baseline` | `WP-05` converges twice on disposable Ubuntu and firewall/SSH recovery tests pass | Wrong OS/resources, non-idempotence, public app port or loss of second access path |
| `G3 recoverability` | `WP-07` completes an application-aware disposable restore before replacing any live backup/adopting Paperclip | Missing/failed dump, untested restore, shared credentials, unbounded staging or no rollback snapshot |
| `G4 Paperclip parity` | `WP-08` has zero unexplained before/after diff, unchanged digest, health, Access and rollback evidence | Any config/data/image mismatch or failed restore/health/Access probe |
| `G5 core capacity` | Separately approved w3exam migration is evidenced; reviewed cleanup yields `B_core ≤ 14 GB` and ≥8 GB update headroom | Unknown deletion target, migration rollback still open, baseline too high or capacity option lacks founder decision |
| `G6 shared-runtime fixtures` | n8n and Hermes generic two-project fixtures pass isolation, drift, restore, inactivity and global-capacity tests | Cross-project access, moving source, shared state, watchdog >5 minutes, OOM or hidden second runtime |
| `G7 publisher` | `DG-01` is closed; selected exact edition passes authorization, backup/update and seven-day host thresholds | Decision still open, paid tier not approved, cross-project write, restore failure or 6-GB canary breach |
| `G8 approval/pipeline` | Current-hash idea and final approvals gate fixture publishing; Bangla overlay, disclosure, purge and idempotency tests pass | Any autonomous publish path, stale approval, AI-avatar testimonial, image-model Bangla text or unbounded media |
| `G9 live canary` | Founder-approved accounts run seven days within resource/SLO/retention gates with alerts and kill switch verified | OOM, capacity/disk gate, p95 >60 seconds, >5-minute cross-project wait, duplicate/unapproved post or missing backup |
| `G10 portability` | `WP-20` rebuilds both roles from declared inputs with no shell-history/old-root copy and meets recorded RPO/RTO | Undocumented manual config, unrecoverable grant/state, source mismatch activating a unit, or host interdependence |

Production activation is incremental. A service that passes its own gate may
remain active while a later independent package is blocked, but no blocked
package may be disguised as “done.”

## 11. Required end-to-end operator sequence

When all work packages are implemented, the primary runbook must reduce to the
following sequence. Exact flags may grow, but these safety boundaries and
operator confirmations must remain.

### 11.1 Prepare a reviewed release

1. Start from a clean clone; checkout the cross-reviewed release commit.
2. Run `scripts/controller versions` and `scripts/check`.
3. Review changed images, migrations, routes, secrets catalog references,
   retention and cost impact.
4. Create the annotated release tag only after cross-model approval.
5. Load the age private key into `SOPS_AGE_KEY` from the password manager without
   writing it to disk.
6. Run `scripts/infra-plan --limit <exact-role-or-host>`, inspect the redacted
   plan and record its digest. A different commit or plan invalidates approval.

### 11.2 Converge `core-1` safely

1. Before mutation, run `scripts/infra-capture`, compare to the approved baseline
   and run `scripts/infra-backup` plus the relevant disposable restore drill.
2. Apply/verify the shared baseline alone.
3. Adopt Paperclip alone during its restart window; recapture, diff and observe
   rollback health.
4. Complete only the separately approved w3exam migration/cleanup path; record
   `B_core` and stop if the admission threshold fails.
5. Apply/verify the n8n stack inactive. Restore/reconcile Dholbeat control state,
   then run the two generic consumer fixtures and drift attack test.
6. From an ephemeral clean checkout of an external consumer's exact commit, run
   consumer check/import/verify. Remove the checkout after the receipt is
   written. Business schedules remain inactive until their own PR/gate.
7. Render/import/verify Hermes fixtures and projects inactive; enable only
   approved schedules under the one-job global lock.
8. Apply route state only from the reviewed Cloudflare plan; run human, machine
   and direct-origin positive/negative probes.

### 11.3 Converge `publish-1`

1. Close `DG-01`, manually order the approved VPS and attach the bootstrap
   public key.
2. Apply/verify baseline, tunnel and backup roles using a distinct host limit.
3. Apply only the selected publisher stack and restore adapter.
4. Create generic fixture workspaces/mappings; pass cross-project negative,
   lifecycle, update and restore tests.
5. Connect real provider accounts only after a separate founder confirmation;
   record each grant against its project/brand mapping.

### 11.4 Activate application pipelines

1. Deploy validated brand profiles, prompts, normalized Dholbeat workflows and
   control migrations from the release commit.
2. Run research/ideation with synthetic inputs; then activate founder-approved
   schedules one brand at a time.
3. Verify idea approval, draft generation, deterministic Bangla overlay, final
   approval and content-hash binding using non-production destinations.
4. Run one founder-approved live canary through the selected publisher. Verify
   idempotency, kill switch, metrics collection, media purge/archive and audit
   receipts before enabling another channel/brand.
5. Start the seven-day canary and block expansion until `G9` passes.

### 11.5 Close the release

1. Run `scripts/infra-verify` independently for both hosts and all active
   registrations.
2. Run `scripts/release-record`; compare deployed commits/image digests/receipts to the
   tag and commit only the redacted operational summary if policy permits.
3. Take a second off-site snapshot, verify backup age and perform any required
   post-migration restore drill.
4. Unset `SOPS_AGE_KEY`, remove temporary checkouts/plans/media and scan the
   workspace/logs for secret leakage.
5. Leave drift, monitoring and scheduled restore reminders active. Any failed
   acceptance item keeps the release open or rolls back the affected unit.

### 11.6 Replacement-host sequence

1. Order/reinstall a compatible Ubuntu 24.04 host and attach the recorded public
   key; keep the old host live.
2. Checkout the exact deployed tag and recover only the age/SSH/provider roots
   from the password manager.
3. Bootstrap and converge the replacement role; restore the latest valid
   application dumps and catalogued retained state.
4. Reconcile n8n consumers and Hermes projects inactive from receipts/exact
   source commits. A missing source or hash mismatch leaves only that unit off.
5. Run offline verification and a temporary-hostname test.
6. Quiesce old writes, final-dump, restore delta and rerun verification.
7. Apply the reviewed tunnel/DNS cutover; preserve stable OAuth callback
   hostnames. Observe late traffic through the rollback window.
8. Take a second snapshot and cancel the old VPS only after founder sign-off.

## 12. Definition of done

### 12.1 Every implementation pull request

A work-package PR is complete only when:

- it stays within declared paths and has a conventional, reviewable commit
  history;
- new tools, images, actions and dependencies are pinned and licensed/owned;
- `scripts/check` passes locally and in CI from the locked controller;
- positive, negative and idempotence tests cover the package's failure modes;
- no secret, decrypted artifact, database, state, plan or generated media is
  tracked or printed;
- every new writable path has persistence/retention/backup classification;
- every public/machine route has a route manifest and negative origin test;
- plan/apply/rollback behavior and production authorization are explicit;
- user/operator documentation starts from a clean checkout, not prior setup;
- monthly cost impact is stated and any paid change is founder-approved;
- a Claude-authored change is reviewed by Codex or a Codex-authored change is
  reviewed by Claude Code at the exact head;
- evidence is redacted, reproducible and linked in the PR without making CI
  artifacts the sole record.

### 12.2 Architecture acceptance traceability

| Architecture acceptance area | Implemented/proved by |
| --- | --- |
| Clean Ubuntu convergence and pinned controller | `WP-00`, `WP-05`, `WP-20` |
| Second-run idempotence | `WP-05`, each service role, `WP-20` |
| Paperclip parity/health/restore | `WP-04`, `WP-07`, `WP-08` |
| Service image/health/log/data ownership | `WP-01`, `WP-03`, all service packages |
| No plaintext secrets/state/media | `WP-00`, `WP-03`, CI and every PR |
| Independent host operation | `WP-05`, `WP-13`, `WP-20` |
| Publisher sizing/canary | `DG-01`, `WP-13`, `WP-19` |
| Full replacement-host drill | `WP-20` |
| `chayan.me`, Tunnel, Access and closed origin | `WP-06`, service packages, `WP-20` |
| Machine-route least privilege | `WP-01`, `WP-06`, `WP-14` |
| One central n8n plus generic second fixture | `WP-10`, `WP-11` |
| Consumer schema/import/drift rejection | `WP-01`, `WP-11` |
| PoriPati exact-source inactive canary | `WP-11` |
| PoriPati PII/network/retention constraints | `WP-11`, `WP-19` |
| Separate Hermes containers/state/credentials | `WP-12` |
| Generic Hermes fixture/global envelope | `WP-12`, `WP-19` |
| Publisher project/workspace/account boundaries | `WP-13`, `WP-17` |
| Core restore reconciliation by unit | `WP-07`, `WP-11`, `WP-12`, `WP-20` |
| `B_core`, RAM/OOM and approval-latency gates | `WP-09`, `WP-19` |

### 12.3 Additional end-to-end application criteria

The implementation is not end-to-end complete until all of these also hold:

1. Adding a third fixture brand requires only a profile, secret references and
   publisher mapping—no prompt, workflow or script change.
2. Research cannot draft/publish; drafting requires current idea approval;
   publishing requires current final approval bound to exact content/media hash.
3. Editing after approval invalidates approval and prevents/cancels an unsent
   stale publisher job.
4. Bangla text is rendered only by the deterministic overlay step with pinned
   fonts; image prompts contain no final Bangla text.
5. AI-avatar testimonials are impossible through validated prompts/workflows,
   and platform disclosure metadata is present where required.
6. Generated media is absent from Git and local disk after its declared
   publish/cancel/failure TTL; selected archives respect lifecycle/cost policy.
7. Publishing retries are idempotent, scoped to the correct project/workspace
   and controlled by a tested kill switch.
8. Metrics are read-only, project/brand scoped, retention-bound and influence
   the next research cycle only through reviewed structured inputs.
9. No required approval/publish deadline depends on Hermes availability.
10. The complete two-brand forecast remains inside the founder's approved
    wallet or a fresh cost decision is recorded.

## 13. GitHub issue breakdown rules

Later issue creation should use one issue per work package by default. Split a
package when it would own more than two top-level paths, cross more than one
production gate or require independently reviewable security/application work.
Keep the parent `WP-XX` ID in every child title.

Each issue body should contain:

```text
Outcome
Architecture/plan references
Dependencies and founder gates
Owned paths
Implementation checklist
Positive and negative tests
Production mutation/approval boundary
Rollback and recovery evidence
Cost impact
Definition of done
Cross-review requirement
```

Suggested issue waves:

1. **Foundation:** `WP-00`, `WP-01`, `WP-02`, `WP-03`.
2. **Safe discovery:** `WP-04`, disposable portion of `WP-05`, import-only
   portion of `WP-06`.
3. **Recoverability/adoption:** production `WP-05`, then `WP-07`, `WP-08`,
   `WP-09`.
4. **Shared runtimes:** `WP-10`, `WP-11`, `WP-12`, generic `WP-14`.
5. **Founder decisions and publisher:** decision issues `DG-01`–`DG-03`, then
   `WP-13` and live-interface part of `WP-14`.
6. **Application:** `WP-15`, `WP-16`, `WP-17`, `WP-18`.
7. **Production proof:** `WP-19`, `WP-20`.

Use decision labels for `DG-*`, area labels for tooling/infra/pipeline/content/
operations, and a production-risk label on any issue that can mutate a host or
provider. “Blocked” names the exact unmet issue/gate; it is not a substitute for
doing safe prerequisite work.

Closing an implementation issue requires its tests and evidence, not merely a
merged code skeleton. Conversely, do not keep a code issue open for a seven-day
canary when a small follow-up production-proof issue gives clearer ownership.

## 14. Known prerequisites and non-assumptions

- The repository is currently a planning/skeleton repository; none of the
  target scripts, IaC, stacks, schemas or CI described here should be assumed to
  exist until its work package lands.
- Live `core-1` facts must come from `WP-04`; the 2026-08-13 figures are a
  baseline hint, not current truth.
- w3exam migration is separately owned and must be evidenced before cleanup.
  This plan does not authorize or implement that product migration.
- PoriPati workflow source and business API contracts remain in the PoriPati
  repository. Dholbeat pins/imports them; it does not copy or redesign them.
- Exact tool, image, action and provider versions are selected and locked in
  implementation PRs after verifying current official releases. This draft does
  not create floating “use latest” permission.
- Open founder decisions in `README.md` remain open unless the founder records a
  choice. Fixture code should make later choices cheap without pretending a
  choice was made.
- A future third-party/untrusted operator, untrusted workflow/agent code or hard
  tenant-isolation requirement stops shared-service admission and returns to the
  founder. Namespaces and manifests are not a hostile-tenant boundary.
- No implementation may expand the existing $14 two-VPS baseline or broader
  ≤$75/month wallet merely to make a test pass. Capacity changes require measured
  evidence and an explicit cost decision.
