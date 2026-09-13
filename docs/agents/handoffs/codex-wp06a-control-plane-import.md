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
Access denial. The Cloudflare package has 193 tests, including mutation/source/state
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
The physical second-device password-manager retrieval gate still precedes future
provider-issued production-secret encryption. Both existing local age recipients
were successfully recovered; that is a separate proof.

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

## Baseline adjudication — 2026-09-13, before implementation fixes

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

## Baseline fix result

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
