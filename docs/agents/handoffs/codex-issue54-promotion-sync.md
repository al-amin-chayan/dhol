# Issue #54 — repeatable promotion ancestry synchronization

## Outcome and ownership

This lane owns promotion governance only: `scripts/promotion`, its Git regression,
`infra/controller/promotion_policy.py`, review-gate integration and tests, the
read-only ancestry notice workflow, and agent workflow documentation. It chooses
issue #54 policy 1: reviewed, merge-commit-only synchronization after every
promotion. No ruleset, production host, credential or paid component changes.
Monthly change: `$0`.

## Behavior

- `scripts/promotion check` reads live exact protected heads through the acting
  App and checks pinned-SHA ancestry before a promotion is opened/reviewed.
- `prepare` uses the acting App Git wrapper to fetch, creates a fresh isolated
  lane from live develop, performs a normal merge of live main, and verifies
  exact ordered parents and equal trees. It never pushes or requests review.
- `arm NUMBER` validates a same-repository graph-only sync, pins its exact head,
  selects native merge-commit auto-merge, and checks the recorded method and
  expected author/enabling App identity. Routine PRs retain squash.
- The trusted review gate pauses routine integration while synchronization is
  pending, rejects premature/stale/fork promotions, and validates reserved sync
  branches, exact parents, tree equality and recorded auto-merge method. Existing
  formal opposite-model review checks remain mandatory.
- Protected-branch pushes run a read-only ancestry notice immediately. It neither
  writes nor invokes a reviewer. Its expected post-promotion failure names the
  repair command; a develop push after successful sync clears the condition.

## Author verification

Full pinned-controller `scripts/check`: passed (952 tests, no secret leaks,
zero Ansible lint failures/warnings). Focused governance tests: 66 passed.
Host `python3 scripts/tests/promotion_graph.py`: passed. This independent real
Git test reproduces promotion divergence, proves squash loses the repair,
proves a normal merge preserves it, and completes the next promotion. Git is
intentionally absent from the offline controller; the host test uses standard
Python and temporary repositories and removes them at exit.

Live `scripts/promotion check` correctly reported NOT READY for main
`8d6462f46a5a569e942611bfcd6a5fad2148d279` and develop
`945ced9d9378c292d1fc9fb09c08d8e4d423e993`. `prepare` created a separate graph-only
sync lane for those heads. The exact current implementation and sync SHAs are
published in their PR bodies and the founder handoff, avoiding a self-referential
SHA in this committed note.

## Review and remaining closure evidence

The founder must start Claude Code Baseline review; the author never invokes,
queues or delegates that review. Review and merge the current graph-only sync
PR first, then this implementation PR. Source-tree content in this lane is
independent of that zero-tree repair, so no rebase is needed merely for its
merge. Any author fix changes the head and needs a founder-triggered Follow-up.

Before closing #54, record both reviewed merges, a live READY preflight and
successful next develop-to-main promotion with its own exact-head review.
After that promotion, use the newly documented mandatory sync again. Existing
protected-branch rulesets and the three required checks remain unchanged; the
read-only live configuration comparison must confirm every explicit desired
field still matches. No production deployment is part of this issue.

Gate results are GitHub check runs at an exact head. If an existing ordinary
PR has a failed gate from the pending-sync interval, rerun its workflow after
repair; do not replace its formal review. Changing protected heads makes a
prepared sync stale; prepare a fresh lane and publish a new reviewed SHA.
