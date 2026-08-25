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

## Main promotion

Open a PR whose base is `main` and whose head is exactly `develop`. Run the
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
