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
4. The founder starts the other model to review the exact head.
5. After approval and green checks, squash-merge routine work into `develop`.

## Main promotion

Open a PR whose base is `main` and whose head is exactly `develop`. Run the
same founder-triggered cross-review and required checks, then use a merge
commit. The founder starts one agent App to open or update the promotion PR and
the other agent App to review it: the latest pusher/PR author and approving App
must be different identities. This satisfies the last-push approval gate
without a personal-account bypass. Approval is valid only for the exact head;
the author never triggers the reviewer. Main's ruleset allows only merge
commits so `develop` remains an ancestor of `main`. Direct pushes, force
pushes, deletion, feature-to-main PRs, and unresolved review threads are
blocked.

## Reproduce GitHub settings

The desired repository settings and active rulesets are committed in:

- `.github/repository-settings.json`
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
converges repository merge defaults and the two named rulesets, and reports
whether each item changed. It never reads the other agent's profile and never
falls back to personal authentication.
