# codex/wp13-publisher

Agent: codex

Head: see draft PR metadata; cross-review must use the later implementation-complete head

## Status

WP-13's safe offline implementation is complete, but the issue is not. The
production inventory keeps `publisher_enabled: false`; no host, Cloudflare,
R2, Postiz, or social-provider state was changed. Keep the PR draft until the
dependency receipts and live fixture evidence below exist.

## What changed

- Added only the selected Postiz `v2.23.0` six-container stack with exact image
  digests, loopback-only application exposure, private state services, bounded
  logs/resources, R2-only media, retained Postiz PostgreSQL/Redis and Temporal
  PostgreSQL/Elasticsearch Visibility, and an outbound-blocked disposable-
  restore override.
- Added a dependency-gated Ansible role, production-disabled inventory, scoped
  runtime-secret catalog, service/image/volume/backup registries, and offline
  Compose/registry validation.
- Versioned the publisher mapping contract for one Postiz organization/logical
  workspace per project, per-brand account ownership, and unique API credential,
  integration, and provider-grant identities. Two account-owning generic
  fixtures and a no-account third fixture pass; cross-project reuse mutations
  fail.
- Added a durable global freeze marker, a lock-serialized Ansible activation,
  exact supported-CLI Temporal workflow termination/recheck, application-aware
  Postiz/Redis/Temporal/Visibility backup, effective-Compose restore validation,
  default disposable cleanup, digest checking, and operational/update/rollback/
  rotation/decommission runbooks.

## Verification

- `scripts/publisher-check` — passed, including base and outbound-blocked
  restore Compose renders with synthetic values and no network calls.
- `scripts/check` — passed: repository/branch policy, lint, secret scan, all
  schema/inventory/SOPS/baseline/tooling suites, 90 publisher-evaluation tests,
  43 selected-publisher tests, the offline publisher contract, and Ansible lint
  with zero failures or warnings.
- `git diff --check` — passed.

No image was pulled on the SSD-constrained laptop, and no live provider or host
probe is claimed.

## Blocking dependencies and unfinished evidence

1. #45 / `wp05d-publish1`: create and converge `publish-1`, then produce its
   reviewed exact-host receipt.
2. #14 / `wp06b-publish1`: prove tunnel/Access/service-token, direct-origin
   rejection, and separate public-media versus private-restic R2 boundaries.
3. #15 / `wp07-publish1`: install the backup/source-escrow foundation and prove
   bounded staging plus disposable recovery.
4. The founder confirms the exact reviewed production plan before apply.
5. After those gates, run fixture convergence/idempotence, authorization,
   registration-lock, restore/update, immediate/scheduled/cancel/delete,
   token-refresh, duplicate-provider-write, kill-switch, and seven-day capacity
   probes. A real provider connection remains a separate founder-approved
   canary; no real post is authorized here.

## Baseline review and author fixes

Claude Code performed the founder-triggered Baseline review at
`3eecd5208b4e265bfcce772f702452b44bafa2de` and requested three required fixes
plus eight suggestions. The author recorded an evidence-based `accept`
disposition for all eleven before editing. The fix delta retains Redis rather
than assuming it rebuildable; derives restore isolation from the effective
Compose merge; serializes Compose activation with the kill switch; makes an
absent workflow fail closed; shrinks and monitors the tmpfs; cleans disposable
state by default behind a disk-headroom gate; rejects ambiguous memory units;
binds backup IDs; preserves primary plus restart failures; documents explicit
decommission; and imports `sys` directly.

Any follow-up is founder-triggered and must review the later exact PR head. The
author did not invoke or enqueue it. Live evidence may still change the head
again before the PR becomes implementation-complete.

## Cost and rollback boundary

WP-13 adds `$0/month`: it uses the already approved `$7/month` `publish-1` and
the shared expected `$0–1/month` R2 boundary. A host upgrade requires a new
founder decision. Until activation, rollback is deleting/reverting inactive
desired state; after activation, the runbook requires a frozen publisher, a
fresh disposable-restore-tested backup, and the previous exact release.
