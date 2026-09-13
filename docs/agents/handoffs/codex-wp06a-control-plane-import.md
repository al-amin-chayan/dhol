# Codex issue #12 implementation handoff

Lane: `codex/wp06a-control-plane-import`, worktree `.worktrees/wp06a-control-plane-import`.
PR: https://github.com/al-amin-chayan/dhol/pull/67, target `develop`.
The author publishes the full final SHA in the PR description and founder handoff;
verify `git rev-parse HEAD` against that SHA before the founder-triggered Claude
Code Baseline review. No author-triggered reviewer or review automation is used.

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
Access denial. The Cloudflare package has 192 tests, including mutation/source/state
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

Reviewer: pending founder-triggered Claude Code Baseline review.
Reviewed head: pending formal exact-head opposite-model verdict.
