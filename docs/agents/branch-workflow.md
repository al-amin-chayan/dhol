# Develop-first branch workflow

Dholbeat follows the same integration shape as Poripati, with fewer release
branches: routine work merges into `develop`; production promotion is a PR from
`develop` to `main`. The canonical controller check rejects every other PR
source for `main`.

## Routine task

1. Update local `develop` using the acting agent's GitHub App identity.
2. Create an isolated lane with `scripts/new-worktree.sh`; its default base is
   `develop`.
3. Push the agent-owned branch and open a ready-for-review PR targeting
   `develop`. Use draft status only if implementation is genuinely incomplete
   or blocked—not merely because CI or cross-review is pending.
4. Apply `review:requested` plus at least one `area:*` label and arm native
   squash auto-merge using the author App.
5. The founder starts the other model to perform the exact-head baseline or
   follow-up review described in `docs/agents/pr-review-workflow.md`.
6. GitHub squash-merges into `develop` only after the opposite-model approval,
   exact-head review gate, controller checks, and resolved threads all pass.
   Develop deliberately does not require a mechanical base update: concurrent
   lanes do not consume a follow-up round merely because another PR merged.

PR bodies use reference-only links such as `Refs #N` unless issue closure is
intended. GitHub's closing-keyword parser ignores negation: never put
`close/closes/closed/fix/fixes/fixed/resolve/resolves/resolved` adjacent to an issue
reference in a disclaimer. Use wording such as "Issue #N remains pending until
the acceptance evidence is recorded." Check the body's issue links before
publishing; an issue's administrative state remains a founder decision.

## Main promotion

Run `scripts/promotion check` against live GitHub before opening or reviewing
a promotion. It must report READY. Open a PR whose base is `main` and whose
head is exactly the printed `develop` SHA. Run the
same founder-triggered cross-review and required checks, then use a merge
commit. The founder starts one agent App to open or update the promotion PR and
the other agent App to review it: the latest pusher/PR author and approving App
must be different identities. This satisfies the last-push approval gate
without using the founder bypass. Approval is valid only for the exact head;
the author never triggers the reviewer. The promotion author arms native
auto-merge with the merge-commit method. Main's ruleset allows only merge
commits so `develop` remains an ancestor of `main`. Direct pushes, force
pushes, deletion, feature-to-main PRs, stale-base merges, and unresolved review
threads are blocked.

## Mandatory synchronization after every promotion

A merge-commit promotion creates a new `main` commit that `develop` does not
contain. Main's strict up-to-date rule then blocks the next promotion as
`BEHIND`. GitHub's Update branch button would write directly to protected
`develop`; it is not a repair. Squashing a repair discards the `main` parent.
Issue #54 selects repeatable, reviewed synchronization; it changes no ruleset.

Immediately after **each** promotion, before further integration:

1. Run `scripts/promotion prepare`. It reads live protected heads with the
   acting App, fetches through the App Git wrapper, and creates a separate
   `<agent>/sync-main-develop-<main-prefix>-<develop-prefix>` lane from that
   exact `develop`.
   A normal `git merge --no-ff` incorporates `main`; no `ours` strategy or
   content-discarding shortcut is allowed. It verifies two ordered parents
   (`develop`, `main`) and an identical first-parent tree. If content differs
   or conflicts, stop the graph-only repair and reconcile the content in a
   separate reviewed lane; never discard main-only content.
2. In the printed lane, run `scripts/check`. Push its owned branch with
   `scripts/github-app-git push https://github.com/al-amin-chayan/dhol.git HEAD`.
   Open a ready PR into `develop` with `review:requested` and `area:tooling`.
   Include the complete head SHA, both parents, zero-tree proof and checks.
   Verify the PR author is the acting App's expected login.
3. Run `scripts/promotion arm NUMBER`. This validates the live graph, pins the
   exact head, selects **merge**, and verifies GitHub recorded that method and
   the acting App. Never use the routine squash command for a sync PR.
4. Publish the exact SHA and handoff, then stop. The founder starts the opposite
   model's review. The author must never invoke, schedule or enqueue it.
5. After the reviewed sync merges, run `scripts/promotion check` again. READY
   confirms the repair retained `main` as an ancestor. Remove the merged lane
   with the normal worktree helper. A later promotion repeats this sequence.

The trusted Cross-review gate pauses ordinary `develop` integration while
synchronization is pending and rejects a premature promotion. Reserved sync
branches must be in this repository, have exactly the current protected heads
as ordered parents, preserve the current `develop` tree, and have native
**merge-commit** auto-merge enabled. Missing, squash or rebase methods fail
closed. Changing either protected head requires rebuilding the sync from the
new heads in a fresh lane and obtaining a new founder-triggered review; stale
approval is never reused. The gate reruns when auto-merge is enabled/disabled
or the PR base changes. A failed gate remains required; it cannot silently
select squash.

The read-only Promotion ancestry workflow runs on protected-branch pushes.
Its failure immediately after a promotion is an actionable synchronization
notice, not a deployment failure. It never writes branches, opens PRs, calls a
model, approves or merges. The existing three required checks and both
rulesets remain unchanged. If an old open PR's gate failed while sync was
pending, rerun its Cross-review workflow after the sync; this does not replace
its exact-head review.

Before issue #54 closes, record a reviewed implementation merge, successful
`scripts/check`, a graph-only synchronization merged with the required method,
and a subsequent READY preflight/promotion. Confirm committed settings and
live rulesets still agree. Monthly cost change: `$0`.

## Founder break glass

Both rulesets grant only the founder GitHub user (`actor_id: 6504305`) a
pull-request-only bypass. Direct pushes remain protected, and neither agent App
is a bypass actor. Use it only when a broken required check or ruleset makes
the normal reviewed path impossible:

1. Confirm the failure is in governance rather than the implementation and
   capture the failed check or ruleset response.
2. Open the smallest revert or repair PR and run `scripts/check` locally.
3. The founder, signed into their own GitHub account, uses the ruleset bypass
   on that PR and records the reason in the merge message.
4. Immediately restore the normal gate and run
   `scripts/configure-github-rulesets.py --apply` to confirm convergence.

Agents must never use the founder's token or account for this procedure. The
committed ruleset tests verify that only the founder user has
`bypass_mode: pull_request` on both protected branches.

## Reproduce GitHub settings

The desired repository settings, Actions policy, and active rulesets are
committed in:

- `.github/repository-settings.json`
- `.github/actions-permissions.json`
- `.github/labels.json`
- `.github/rulesets/develop.json`
- `.github/rulesets/main.json`

Preview the exact payload without network access:

```bash
scripts/configure-github-rulesets.py
```

Compare managed settings, Actions permissions, labels and both rulesets against
live GitHub without changing anything:

```bash
scripts/configure-github-rulesets.py --check
```

This mode mints a fresh acting-App token, sends only GET requests and exits 1
on drift (0 on a match). Missing `develop`, missing or duplicate managed
rulesets, and superseded labels are drift; API/authentication failures fail
the command. Unmanaged labels and rulesets are outside the comparison. Ruleset
metadata and an empty `required_reviewers` list are normalized; approval-policy
flags are compared explicitly. Both branches preserve the live
`require_extra_approval_for_unattributed_changes: true` policy. Main's strict
base flag remains `true`, and develop's remains `false`. Use this read-only
comparison for promotion verification. Live convergence is a separate scoped
operation; this check never creates a branch or repairs configuration.

Apply it from a Codex or Claude Code session:

```bash
scripts/configure-github-rulesets.py --apply
```

The installer detects the running agent, mints one fresh token for the
installer invocation, creates `develop` from `main` only when missing,
converges repository merge defaults and native auto-merge, requires full-SHA
action pinning at the GitHub boundary, migrates and converges managed review
labels, converges the two named rulesets, and reports whether each item
changed. It never reads the other agent's profile and never falls back to
personal authentication.

When a PR introduces a new required workflow check, merge that bootstrap PR
under the existing rules first and only then run `--apply`. Required checks
must execute a gate script already present on `develop`; applying the ruleset
early would deadlock the bootstrap.

The PR #35 bootstrap exception was removed after its workflow and gate script
landed on `develop` and `--apply` converged the live rulesets. The workflow now
fails closed for every PR if the trusted gate script is missing from `develop`.
