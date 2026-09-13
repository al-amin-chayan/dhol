# Codex issue #12 implementation handoff

Lane: `codex/wp06a-control-plane-import`, worktree `.worktrees/wp06a-control-plane-import`.
PR: https://github.com/al-amin-chayan/dhol/pull/67, target `develop`.
The author publishes the full final SHA in the PR description and founder handoff;
verify `git rev-parse HEAD` against that SHA before the founder-triggered Claude
Code Follow-up review. No author-triggered reviewer or review automation is used.

## Outcome and scope

Seven existing DNS/tunnel/Access resources are imported into client-encrypted,
natively locked R2 state, with a clean follow-up plan and verified independent
snapshot. Root bucket IDs are immutable and outside their own state ownership.
All declarations, finite bootstrap/adoption/recovery commands, provider checksums,
route/probe contracts and recovery ciphertext are reproducible from git.

Owned paths expanded after repeated live-lane discovery to:
`infra/tofu/cloudflare/`, `infra/services/domains.yml`, the secret catalog/runbook
and new controller-only ciphertext, their policy regression, Cloudflare tooling
tests, the existing plan-document regression, `scripts/cloudflare`, `scripts/check`,
`infra-plan`/its document adapter, and this handoff. The adapter expansion is
necessary because the previous gate rejected every host plan merely on the
presence of an OpenTofu directory. No active lane owned these files; inventory
baselines/playbooks, promotion governance, brand setup and shared README remained
outside this lane. No core/publisher host configuration was mutated.

## Evidence

See `infra/tofu/cloudflare/evidence-2026-09-13.md` and the package recovery runbook.
Author verification includes the exact locked provider, all offline checks, real
provider imports/no-change plans, both recipient MAC recovery, clean-workspace
native locking/encryption recovery, independent parent DNS delegation, live
founder-policy validation and unauthenticated/wrong-founder/alternate-Host/path
Access denial. The Cloudflare package has 197 tests, including mutation/source/state
race refusal, two-stage bootstrap, bounded snapshot failures, route-negative
fixtures and real loopback HTTP proxy behavior.

Provider plan errors/differences were diagnosed and corrected in source; no
resource-changing plan was applied and no `ignore_changes` hides policy drift.
The publisher's locally managed connector remains local. Two earlier failed
*disposable* drill objects were decrypted, verified and removed; production state
and its separate verified snapshot were preserved.

## Production and founder gates

Only two new private R2 roots and state/ciphertext writes occurred under the
founder's full-implementation authorization. Existing Cloudflare resources are
unchanged. The setup provider token is private, outside git and expires September
14; it is excluded from committed SOPS and all evidence. The R2 delegator uses the
existing founder-controlled administrative root from the local reference; do not
revoke that existing root when retiring the temporary setup token. Operator
recovery can issue a new account R2 root without changing pinned bucket IDs.

`n8n`/`hooks` are planned and `publish` remains explicitly `existing-unprotected`;
WP-06C must configure their Access/path/service-token overlays and private/public
storage before later promotion. The currently down core connector also needs its
later host lane. The live full founder/service-token/direct-IP positive matrix is
not claimed: scoped sessions/IPs, deployed future services and disposable POST
fixtures remain promotion requirements. Complete fixtures cover their contracts.
The founder removed the second-device validation requirement on 2026-09-13
because no second device is available, after the shared-recipient recovery risk
was explained. README §9/§10 records the waiver and authorization to retain the
generated state key. Password-manager escrow and both distinct-recipient/MAC
checks remain required. Both existing local age recipients were successfully
verified; no successful second-device drill is claimed.

## Cost and rollback

Software $0; two private state/recovery roots and bounded snapshots remain inside
the approved R2 $0–1/month baseline. Future bucket declarations add no provisioned
cost. No paid subscription was added.

Reverting code preserves Cloudflare objects/state. Never `destroy`, overwrite an
existing primary or remove an unidentified lock. The finite restore command
checks a reviewed independent ciphertext digest, decrypts/checks provider IDs in
memory and conditionally creates only an absent primary. Follow restoration with
a fresh real no-change plan. See the runbook for bootstrap and key rotation.

Reviewer: Claude Code Baseline completed; founder-triggered Follow-up pending.
Reviewed head: pending formal exact-head opposite-model verdict.

## Historical Baseline adjudication — 2026-09-13, before implementation fixes

Reviewer: Claude Code
Reviewed head: 897ef192ee43e588715625366807ec3b9719e74f

- R1: accept. Only operations.prepare calls the real edge renderer; the legacy
  renderer has no production consumer and the old route registry is empty. Remove
  the legacy renderer and state explicitly that the edge manifest supersedes it.
  A reference sweep also proves index/validate_schema have no remaining consumer
  after that removal, so those unused helpers are removed with it.
- R2: accept. JWT payload tests prove requested scope, not provider enforcement.
  Add a finite live drill with an in-scope positive control and explicit denied
  reads outside the prefix, across buckets, and after expiration.
- R3: accept. Two successful decryptions can currently use the same key. Reject
  duplicate canonical inputs and require two distinct public recipients matching
  the committed policy before decryption or any provider operation; record hashes.
- R4: needs-founder. The generated key reading is literally within the existing
  gate, but the founder must explicitly acknowledge proceeding before the second-
  device drill. No acknowledgment is inferred from general implementation approval.
  Clarify that the recovery ciphertext copy protects against git loss only; total
  age-key loss requires re-import from adoption.json, which contains all seven IDs.
- S1: accept. Account, zone, identity and backend bounds are duplicated in runtime
  code. Use the reviewed declarative sources and retain explicit absolute bounds.
- S2: accept. Production renderer YAML/OSError exceptions can leak source lines;
  catch them with a value-free diagnostic and exercise malformed/missing inputs.
- S3: accept. Successful old-object deletions cannot be rolled back after a later
  prune failure. Correct the comment and test partial pruning and candidate cleanup.
- S4: accept. Resolve the registrar domain by ID, as edge.validate already does.
- S5: accept. Expand compressed security parser/probe code and use normal imports.

The separately noted webhook runtime packaging/concurrency remains WP-06C's
planned-route promotion gate; no runtime is activated by this child package.

## Historical Baseline fix result

R1–R3 and S1–S5 are implemented. The finite live delegation drill returned HTTP
403 for all three scope/expiry negatives after successful positive controls and
removed its sole marker. Both actual recipient fingerprints match the existing
policy. A fresh locked-provider plan proves seven resources, zero mutations and
unchanged encrypted state; its source digest is recorded in the refreshed evidence.
Live policy/registrar/parent delegation verification passed with the domain-by-ID
lookup. Full scripts/check: 1,174 tests passed (193 Cloudflare), all lint/policy/
format/secret checks passed. Style changes in delegation/proxy preserve semantics.

R4 is still needs-founder: explicitly acknowledge that the generated OpenTofu state
key may precede the second-device drill. Its copied ciphertext cannot recover loss
of both age keys. All seven provider IDs remain committed, permitting a reviewed
re-import into an empty replacement backend without application-data loss. The
secret runbook and package recovery instructions now state this precisely. The PR
returns to draft with decision pending and native auto-merge cancelled, per the
review workflow. After acknowledgment is recorded, publish the resulting exact
head for a founder-triggered Claude Code Follow-up; the author does not start it.

## Historical Follow-up adjudication — before second fix edits

Reviewer: Claude Code
Reviewed head: 6b10410fe1dbb858a7da98df94113a956ec51ef8

- R1–R3 and S1–S5: already-done; the Follow-up independently verified every fix,
  193 controller tests, full scripts/check, source/receipt binding and parser ASTs.
- R4: needs-founder, unchanged. The latest request to fix feedback is not an
  explicit acknowledgment of the generated-key recovery risk. Keep draft/decision
  and auto-merge disabled; do not manufacture founder acknowledgment.
- N1: accept. The fixed delegation marker shares the drill namespace, so one stale
  marker prevents clean_drills from removing otherwise eligible state and counts
  toward recovery_drill's inventory bound. Document this coupling and the existing
  explicit manual removal procedure; keep conservative cleanup ownership.
- N2: accept. S1 removed the name-pair tripwire in initial-bootstrap mode. Restore
  an exact role-bound name check against a separate committed bootstrap-roots.json
  authority manifest, before any API request, preserving project-neutral runtime
  code. A bootstrap.yml edit alone must not create arbitrary bucket names; changing
  the approved authority pair requires a separate reviewed source change. Existing
  immutable bucket-ID checks remain mandatory and the receipt binds both manifests.

## Historical Follow-up suggestion fix result

N1 and N2 are implemented. The runbook documents namespace cleanup coupling. The
restored root-name tripwire uses an independently committed declarative authority
pair, preserving generic runtime code and immutable bucket-ID enforcement. Three
negative tests prove changed/swapped initial names fail before provider contact;
the receipt mutation test binds the added authority manifest.

Verification: full scripts/check passed all 1,178 tests, including 197 Cloudflare,
and all policy/lint/format/secret checks. A fresh locked-provider plan binds the
current sources, reports seven resources and zero mutations, and preserves the
production encrypted-state digest. Its canonical receipt normalization passed.
Refreshed evidence is committed with this fix.

R4 remains the sole required finding: explicit founder recovery-risk acknowledgment
is pending. Keep draft/decision and native auto-merge disabled. Following acknowledgment,
record it and hand the resulting exact head to the founder for a Claude Code Follow-up;
the author does not invoke review or infer acknowledgment from a generic fix request.

## Founder decision adjudication — 2026-09-13, before policy edits

The founder explicitly instructed: "I don't have any second device so drop the
second device validation plan." This follows the explanation that both ciphertext
copies share the age recipients and total key loss requires re-import.

- R4: accept the recovery diagnosis; resolve the founder requirement through this
  explicit policy waiver. Remove the second-device validation gate from current
  README and dependent runbooks, record the informed decision in §9/§10, retain
  the generated state passphrase, and keep password-manager escrow and both
  distinct-recipient/MAC checks mandatory. Do not claim the drill passed.
- G1: already corrected. The accurate label was restored. This policy commit
  creates a real new head, so review:requested is now the prescribed transition;
  remove decision after the founder decision is recorded.
- R1–R3, S1–S5, N1/N2: already-done, unchanged and independently verified.

Historical adjudications/evidence above describe earlier decisions and are
superseded by the new recorded policy for current requirements.

## Current author disposition and review handoff

R4's founder decision is now recorded in README §9/§10 and current recovery
runbooks. The removed requirement is marked waived, not passed. Retaining the
generated state key is explicitly authorized after the shared-key risk explanation;
password-manager escrow, provider recovery logins and both distinct-recipient/MAC
checks remain mandatory. No key, ciphertext, provider object or runtime code changed.

G1's label correction was already applied; this new source commit now invalidates
the old exact-head review and legitimately restores review:requested. Remove the
decision label, keep the completed PR ready, and arm native auto-merge behind the
formal opposite-model exact-head approval and CI. The founder starts Claude Code's
next Follow-up on the published new head. The author does not invoke review.

Policy-commit author verification: full scripts/check passed all 1,178 tests,
including 197 Cloudflare tests, plus repository/branch/YAML/shell/schema/inventory/
SOPS/secret/format/Ansible checks. The Cloudflare input digest remains
6884a26ea43c44445caee230fe3408568c55f827deeeb1c9b2ce8a13dc248b08, matching
the previously verified live receipt: no runtime, provider or secret input changed.
The documentation propagation includes publisher-operations.md after checking the
active brand lane has only brands/onboarding work; no overlapping edits were found.
