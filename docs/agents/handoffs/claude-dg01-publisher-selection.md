# DG-01 publisher selection evidence

Original agent: Claude Code

Final evidence-integrity fixes: Codex

Head: recorded in PR #49's final review-request comment

Issue: #16 — `[10/27][DG-01] Select the self-hosted publisher and record the
founder decision`.

## Current gate state

`DG-01` is open and `WP-13` remains blocked. The founder selected Postiz
`v2.23.0` on 2026-08-25, but a material cancellation defect was measured after
that instruction: deleting a scheduled post removes its Postiz row while its
Temporal workflow remains `RUNNING`. The founder must explicitly reaffirm
Postiz with the scheduler-verified kill-switch condition or reopen the choice.
No agent may infer that answer from the earlier selection.

## What changed

- `infra/tests/publisher-eval/` provides digest-pinned candidate topologies, a
  seventeen-check fixture matrix, capacity evidence, registration and restore
  drills, scheduler-state checks, and a fail-closed exact Temporal Visibility
  check.
- `docs/decisions/publisher-selection.md` records the evidence, recommendation,
  original founder instruction, material later finding, and pending founder
  action.
- `docs/runbooks/publisher-evaluation.md` reproduces the disposable evaluation.
- `README.md` keeps the current decision open and appends the later evidence to
  the change log without rewriting the original history.
- `scripts/check` shellchecks the harness and runs its unit tests.

## Evidence state

- **Postiz `v2.23.0` — `viable-with-findings`.** All 17 matrix checks pass.
  `registration.lock` passes; `cancel.terminates-workflow` and the composite
  `backup.dump-restore` drill fail because cancellation leaves the exact
  `post_<id>` workflow running. The restored databases return the queued post
  and its `RUNNING` workflow. The corrected harness now asks Temporal's exact
  `postId="<id>" AND ExecutionStatus="Running"` predicate through List Workflow
  Executions and requires that exact workflow id, but its post-rebuild live
  result remains unproven: the final rerun passed all 17 matrix checks, then the
  local Docker daemon failed to stop the Postiz container before the restore
  phase. The disposable stack was removed manually and zero labelled resources
  remained. Do not substitute the earlier raw-Elasticsearch count for this
  outstanding proof.
- **Mixpost Lite `v2.6.0` — `disqualified`.** It has no workspace routes or
  machine API, and one login's label is visible to another. Its two drills pass.
- Channels are database fixtures. No social account, OAuth grant, provider
  call, production inventory, SOPS key, or purchase is involved.
- Fixture credentials are generated per run outside the repository, evidence
  contains only bounded redacted values, and successful runs remove their
  disposable containers and volumes.

## Remaining founder action

Read finding 3 and the pending-reconfirmation section in
`docs/decisions/publisher-selection.md`, then state one of:

1. reaffirm Postiz `v2.23.0` with the scheduler-verified cancellation condition;
2. reopen the publisher choice.

After that instruction, transcribe it with its date, update `README.md` §9 and
the change log, restore the appropriate closing keyword on PR #49 if the gate is
closed, and request exact-head Claude Code review because the final fixes are
Codex-authored.
