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
  logs/resources, R2-only media, retained Temporal PostgreSQL and Elasticsearch
  Visibility, and an outbound-blocked disposable-restore override.
- Added a dependency-gated Ansible role, production-disabled inventory, scoped
  runtime-secret catalog, service/image/volume/backup registries, and offline
  Compose/registry validation.
- Versioned the publisher mapping contract for one Postiz organization/logical
  workspace per project, per-brand account ownership, and unique API credential,
  integration, and provider-grant identities. Two account-owning generic
  fixtures and a no-account third fixture pass; cross-project reuse mutations
  fail.
- Added a durable global freeze marker, exact Temporal workflow termination and
  recheck, application-aware Postiz/Temporal/Visibility backup, digest checking,
  isolated restore, and operational/update/rollback/rotation runbooks.

## Verification

- `scripts/publisher-check` — passed, including base and outbound-blocked
  restore Compose renders with synthetic values and no network calls.
- `scripts/check` — passed: repository/branch policy, lint, secret scan, all
  schema/inventory/SOPS/baseline/tooling suites, 90 publisher-evaluation tests,
  22 selected-publisher tests, the offline publisher contract, and Ansible lint
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

Because live evidence will change the implementation head, the founder should
trigger the required Claude Code baseline review only after the PR becomes
implementation-complete and ready.

## Cost and rollback boundary

WP-13 adds `$0/month`: it uses the already approved `$7/month` `publish-1` and
the shared expected `$0–1/month` R2 boundary. A host upgrade requires a new
founder decision. Until activation, rollback is deleting/reverting inactive
desired state; after activation, the runbook requires a frozen publisher, a
fresh disposable-restore-tested backup, and the previous exact release.
