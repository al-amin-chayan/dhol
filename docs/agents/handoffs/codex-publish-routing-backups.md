# WP-06B / WP-07 implementation handoff

Author: Codex (`chayan-codex[bot]`)
Branch: `codex/publish-routing-backups`
Base: `develop` at `8ed499a`
Issues: #14, #15, and dependent #17

## Baseline finding adjudication (before implementation)

Claude Code reviewed `81c1d7c1a1d9239009ea47499de740079386a3b4` on
2026-09-14; formal review 5193144310 requested changes.

- R1 — accept. The role's five-minute artifact expires during operator review,
  and `infra-plan` refreshes it after Ansible. `infra-apply` does indirectly
  refresh through its mandatory pre-apply `infra-plan`, contrary to the narrow
  claim that it never refreshes, but that does not solve the ordering or the
  subsequent confirmation delay. Refresh before host planning and immediately
  after apply confirmation, compare stable normalized source/state/Access
  authority, and retain strict freshness at operator capture. Host role
  consumption binds that authority without imposing a five-minute human window.
- R2 — accept. `ROOT.parent.parent` names the founder's home in the production
  checkout. Validate against the actual checkout and exclude other Git/App
  identities while accepting ordinary external home-directory SSH keys.
- R3 — accept. Append the disk/cost/live-gate record to README §10 and the
  required temporary management credential decision to §9; append-only records
  avoid restructuring the shared founding plan.
- S1 — accept. A separate private source bucket costs no bucket-count fee and
  makes the model enforce the actual blast-radius boundary. Model the finite
  controller-only owner explicitly, separate from per-host backup ownership;
  keep the unique credential-pair invariant. Update issuance/recovery paths,
  guards, validation and counts together.
- S2 — accept. Role defaults already contain the non-secret media coordinates;
  update step 6 to inspect those rather than populate group vars.

## Implemented baseline dispositions

- R1: `infra-plan` captures before and after Ansible; `infra-apply` captures
  again after exact confirmation. The common helper executes the native
  provider and strict fresh normalization, then rejects any changed source,
  encrypted-state digest, Access audience or team. Timestamps and randomized
  encrypted-plan hashes are excluded from the stable approved-plan authority.
  Only host-role consumption omits the 300-second expiry; invalid/future
  observations still fail. Regression tests cover an hour-long approval delay,
  fresh recapture, authority drift, provider/normalizer failure and no host
  mutation after a failed comparison.
- R2: identity validation now names the actual checkout and walks resolved
  ancestors to exclude regular Git checkouts, linked worktrees, bare repos and
  App profiles. This avoids ambient Git environment dependence. Nine identity
  cases cover home-directory acceptance from both checkout layouts and unsafe
  paths/modes. Source-root tests also reject the former shared publisher bucket.
- R3: README §9 records the temporary management credential decision; §10
  records scope, permanent 2 GiB disk reservation, preserved 8 GiB headroom,
  subscription change, R2 usage cost and outstanding live acceptance. Only
  append-only shared-file changes were made.
- S1: source escrow has its own controller-only private bucket, exact catalog
  credential pair, disabled managed domain and empty object-expiry lifecycle.
  Issuance and recovery use that bucket; live probes include all three private
  buckets. Tests reject cross-host/principal/name/credential/public/expiry
  mutations and missing coverage, verify four distinct bucket credential
  scopes, and assert the new 16/23 resource arithmetic. R2 charges storage and
  operations rather than a per-bucket subscription; separate scope adds no
  recurring bucket-count fee ([official pricing](https://developers.cloudflare.com/r2/pricing/)).
- S2: publisher operations step 6 points at the actual committed role defaults
  and requires media credentials to be denied access to every private bucket.

Review: founder-triggered Claude Code Follow-up required; no reviewer invoked.
The PR and founder handoff carry the full published head SHA. This document
cannot contain its own commit hash.

## Scope and rationale

The lane owns the Cloudflare publisher profile/credential operator, new
`cloudflared`/`restic` roles and boundary playbook, source-escrow/backup operator
scripts, narrowly required publisher staging/secret integration, toolchain
restic pin, tests and recovery runbooks. It does not edit the concurrent #55
listener-verifier/bootstrap runbook lane or brand lane. README additions only
append the required decision and change-log records.

### Cloudflare boundaries (#14)

The encrypted native controller stages sixteen new managed configurations:
two Access applications, one dedicated machine policy, four R2 buckets, four
disabled managed domains, three empty private-bucket lifecycles, and public media
lifecycle/custom domain. Including seven adopted resources, the active profile
requires a complete twenty-three-resource plan. Every adopted identity stays no-change;
updates, deletes, replacements, moves, imports and unknown resources are rejected.
New-resource guards bind caller-supplied account/domain/bucket/security selectors,
exact policy attachments and lifecycle transitions. Computed machine policy IDs
must be proven references; a broad any-token policy is rejected.

The human UI attaches only the unchanged founder policy. `/api/public/*` has a
separate Access audience and exact n8n token policy plus independent application
authentication. The local connector validates Access JWT audiences and derives
ingress from the manifest, terminating in 404; it does not expose an origin port.
Backup buckets have disabled `r2.dev`, no object-expiry rules and no custom public
domains. Private retention belongs to restic because deleting a referenced pack
independently can corrupt recovery. Public media has 7-day deletion and 1-day
incomplete-upload cleanup; these values are seconds in locked provider 5.24.0.

Credential generation stays outside OpenTofu: token IDs/selectors can enter
state, client secrets/provider roots cannot. Each issuance is immediately
encrypted into a complete catalog-specific set and MAC-recovered under both
distinct age private keys. Unescrowed newly issued tokens are revoked on error;
same-name existing credentials require explicit recovery/rotation. Separate
files avoid committing partial `core`/`publisher` secret sets or mounting backup
credentials into the application. Source escrow uses a dedicated private bucket,
controller-only token and distinct restic identity/password. The bucket model
enforces exactly one credential pair/owner for each bucket, so a compromised
publisher root cannot delete the independently stored source escrow.

Mutation helpers require a clean annotated production release, protected-main
reachability, a merged develop-to-main promotion PR, its formal opposite-model
exact-head approval and identical reviewed/merge trees. The actual merge commit
differs from the reviewed PR source SHA, so comparing those commit hashes alone
would incorrectly reject normal merge-commit promotions. Each mutation then
requires interactive confirmation of its deterministic digest. Source/state
changes invalidate routing approval; apply uses the captured encrypted binary
plan and proves post-apply no-change plus encrypted recovery snapshot.

### Backup and source recovery (#15)

Installation is opt-in, publisher-only, and initially leaves timers disabled.
Core legacy backup/cron jobs and repositories are untouched. State and source
prefixes use separate encrypted restic repositories with pinned identities;
existing unpinned repositories cannot be silently adopted. Publisher dumps use
the adapter's SQL, stopped Redis persistence, and Elasticsearch filesystem
snapshot. Raw PostgreSQL/Elasticsearch volumes, caches/media/logs are excluded.

The shared publisher lock covers dump/upload/retention and disposable restore;
a different child lock avoids deadlocking the adapter. Plaintext application
dumps land directly in a physically reserved 2 GiB ext4 filesystem also mounted
into Elasticsearch. Formatting disables discard; a readonly verifier checks
allocation and mount size. Provisioning requires 10 GiB free before reserving
the image, preserving 8 GiB. Existing allocated images do not require reserving
those 2 GiB again on every no-change run. Retained config/receipts are limited
to 16 MiB, tar/member counts and byte streams are bounded, and upload summary
uses bounded memory rather than an unbounded disk log.

The root job is bounded to 256 MiB/50% CPU/two hours. It streams the tar into
restic, then runs seven-daily/four-weekly `forget`, `prune`, and `check` before
advancing success. Host/tag grouping and stable `state.tar` paths avoid a
separate retention group for every temporary directory. One daily/weekly
policy may retain two same-day snapshots; tests allow that documented behavior.
Hourly freshness/failure checks emit actionable journal errors. The unit does
not claim Telegram alert delivery; that integration is pending the approval bot.

Disposable recovery requires a full host/purpose-scoped snapshot ID, new named
target, loopback-only port, safe bounded archive and byte-digest equality. It
reserves download plus extraction space before starting and calls the existing
outbound-blocked adapter using the restored staging root, not production's
snapshot mount. Cleanup is unconditional. The optional scheduled fixture
Visibility control is passed through backup and restored by the adapter; its
absence is explicitly different from a full Visibility recovery proof.

Source escrow creates a 256 MiB size-limited clean release/main Git bundle with
all annotated production tags, verifies its digest/Git structure, and uploads
encrypted restic data using independently exported password-manager roots.
Root initialization pins the new repository ID atomically and requires updating
the password manager. Deployed releases for both hosts are mandatory before
pruning: protect their newest covering bundles, the last two superseded
releases, and the latest bundle. Coverage tags let a fresh bundle preserve an
older deployed tag even without an earlier source snapshot. Recovery downloads
through R2 and restores an exact tag/main commit from only the bundle; it never
needs the old clone, SOPS within the bundle, GitHub, or a server-side Git token.
Temporary bundle files are always removed; the inspected recovered clone is
explicitly disposable and remains until operator cleanup.

## Author verification and remaining live evidence

Baseline fixes: the final `scripts/check` passes all 1,269 pytest cases,
including 31 new regressions, both real Git suites, schemas, bounded secret
scan, Compose checks, OpenTofu formatting and production-profile Ansible lint.
Native validation under OpenTofu 1.12.5/provider 5.24.0 and both distinct age
MAC recoveries passes. The post-fix read-only provider plan still proves seven
no-change adopted objects with routing disabled and encrypted-state SHA-256
`f54484f3c1e071b2e463bad448dd5eff375276af62b3b12178cd68ef70f27ccf`.

`scripts/check` covers real local Git outage/digest/annotation/dirty/cleanup
regressions; real pinned restic encrypted SQLite dump recovery/retention and
publisher staging/failure integration fixtures; hostile archives, wrong roots,
lock contention, full disk, stale status, source retention, credential catalog
scope, routing guards and exact promotion-review authorization. Native
OpenTofu/provider validation succeeds under both age roots. A read-only live
plan proves all seven adopted resources unchanged, routing still disabled,
and encrypted remote state unchanged. This is WP-06A preservation evidence,
not a claim that the new profile has been applied.

No new provider token/bucket/Access policy has been created, no server role or
timer applied, and no real social account/post connected. Existing operator
credentials can inspect the adopted footprint, but cannot inspect account
token permission groups; scoped issuance needs a temporary approved management
credential. Local fixtures are not x86 production or live R2 acceptance proof.

After cross-review and promotion, use the exact stages in
[publisher boundaries](../../runbooks/publisher-boundaries.md) and
[backup recovery](../../runbooks/backup-recovery.md), separately confirming the
credential, routing and publisher-only host plans. Capture real positive/
negative admission, private/public storage, lock/recovery/delegation, encrypted
snapshot, independent root escrow, GitHub-outage and disposable application
recovery receipts before declaring #14/#15 verified. Missing identities and
missing public media fixture remain explicit incomplete results. Actual
seven-day media expiry is distinct from the configured lifecycle proof.

The staging path change must be part of reviewed #17 desired-state adoption;
an existing Elasticsearch container bound to the old path cannot write into
the new mount until recreated with the reviewed configuration. Do not rewrite
an environment or fake a backup receipt to bypass this. Foundation recovery
can precede application activation, but complete application/Visibility proof
must use the actual adopted mount and a scheduled disposable fixture.

#45/#55 baseline is verified, but #17 is not automatically closed by source
implementation of #14/#15. It still needs desired-state adoption/releases,
idempotence and the actual publisher fixture/auth/registration/scheduler/
kill/recovery/update proofs, investigation of the earlier disposable cold-start
OOM flag, and seven continuous days below its RAM/disk/process/headroom limits.
Keep all three issues open until their real acceptance receipts support closure.
