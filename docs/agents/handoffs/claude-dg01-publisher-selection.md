# DG-01 publisher selection evidence

Original agent: Claude Code

Final evidence-integrity fixes: Codex

Head: recorded in PR #49's final review-request comment

Issue: #16 — `[10/27][DG-01] Select the self-hosted publisher and record the
founder decision`.

## Current gate state

`DG-01` is closed by the recorded founder selection of Postiz `v2.23.0` on
2026-08-25. On 2026-08-27 the founder clarified that issue #16 and PR #49 own
the complete decision/evidence packet while issue #17 (`WP-13`) owns the
implementation. Later cancellation and Elasticsearch-recovery findings are
mandatory `WP-13` conditions, not a reason to erase the selected product or
reduce issue #16's evidence scope.

## What changed

- `infra/tests/publisher-eval/` provides digest-pinned candidate topologies, a
  seventeen-check fixture matrix, capacity evidence, registration and restore
  drills, scheduler-state checks, and a fail-closed exact Temporal Visibility
  check.
- `docs/decisions/publisher-selection.md` records the evidence, recommendation,
  original founder instruction, material later findings, and implementation
  conditions.
- `docs/runbooks/publisher-evaluation.md` reproduces the disposable evaluation.
- `README.md` keeps the Postiz decision closed and appends the later evidence
  as `WP-13` conditions without rewriting the original history.
- `scripts/check` shellchecks the harness and runs its unit tests.

## Evidence state

- **Postiz `v2.23.0` — `viable-with-findings`.** All 17 matrix checks pass.
  `registration.lock` passes. The untouched cancellation check fails because
  HTTP 200 and row deletion left that workflow `RUNNING`; a second cancellation
  in the same run ended at raw status `2`, proving only that HTTP success is not
  a reliable termination signal. The restored databases return the queued post
  and its `RUNNING` workflow. The exact List Workflow Executions predicate
  `postId="<id>" AND ExecutionStatus="Running"` returns the exact `post_<id>`
  workflow before Elasticsearch destruction (`1`) and none after rebuild (`0`).
  `WP-13` must therefore retain Visibility state or implement and rehearse a
  reindex path, and must verify its kill switch at scheduler level.
- **Mixpost Lite `v2.6.0` — `disqualified`.** It has no workspace routes or
  machine API, and one login's label is visible to another. Its two drills pass.
- Channels are database fixtures. No social account, OAuth grant, provider
  call, production inventory, SOPS key, or purchase is involved.
- Fixture credentials are generated per run outside the repository, evidence
  contains only bounded redacted values, and successful runs remove their
  disposable containers, volumes, and network. The final live run left zero
  labelled resources.

## Remaining action

No product or scope decision is pending from the founder. Restore `Closes #16`
on PR #49 and request exact-head Claude Code review because the final fixes are
Codex-authored. After that opposite-model review is resolved, the normal
exact-head Codex review of the Claude-authored PR head can satisfy the merge
gate. Issue #17 owns the production stack, recovery/reindex implementation,
scheduler-verified kill switch, update rollback, real-provider checks, and
seven-day canary.
