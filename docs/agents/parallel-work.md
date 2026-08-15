# Parallel work protocol — Claude Code + Codex

Detail behind the "Parallel work" section of the root `AGENTS.md`. Read this
when starting, merging, or recovering a lane.

## Why worktrees and not just branches

Both agents run on the same laptop against the same clone. A shared working
tree means one agent's `git checkout` silently changes the files under the
other's feet, and one agent's half-finished edit lands in the other's commit.
Git worktrees give each agent its own directory and its own checked-out
branch, backed by one object store — isolation without a second clone.

## Lane lifecycle

```bash
# 1. See what the other agent is doing. Always. Before anything.
scripts/lanes.sh

# 2. Create your lane (from the primary checkout)
scripts/new-worktree.sh --name brand-profile-schema --agent codex
cd .worktrees/brand-profile-schema

# 3. Work. Commit small and complete. Conventional Commits.
git add brands/ && git commit        # commit.template adds the Agent: trailer

# 4. Rebase on develop before asking for review
git rebase develop

# 5. Cross-review: the OTHER model reviews this branch (see below)

# 6. Merge the approved PR into develop with GitHub's squash method.
#    Do not merge or push directly from the primary checkout.

# 7. Remove the lane
scripts/rm-worktree.sh brand-profile-schema --delete-branch
```

`new-worktree.sh` refuses to reuse an existing branch or path, and warns when
the other agent has open lanes. `rm-worktree.sh` refuses to delete a lane with
uncommitted changes or with commits not yet in `develop` or `main` unless you
pass `--force` — that guard exists specifically so one agent cannot delete the
other's unmerged work.

## Avoiding collisions

Ranked, cheapest first:

1. **Disjoint top-level paths.** Pick a lane whose work lives in one or two of
   `brands/ stack/ n8n/ prompts/ scripts/ docs/`. `scripts/lanes.sh` prints
   the paths each open lane already touches — treat them as taken.
2. **Shared files get append-only edits.** `README.md` (change log, open
   decisions) and `AGENTS.md` are edited by both agents. Append a row; do not
   reflow, renumber, or restructure while another lane is open. If a
   restructure is genuinely needed, close the other lanes first.
3. **Announce, then act.** If your task cannot avoid a live lane's paths, say
   so in your response to the founder and either wait or take the task over
   entirely — never two lanes editing one file in the same session.
4. **Long-running edits are a smell.** A lane that stays open for days
   accumulates conflicts. Split it.

## Conflict recovery

- Conflict during `git rebase develop`: resolve in your lane, never in the
  primary checkout, and never `git checkout --ours/--theirs` wholesale on a
  shared doc — read both sides and merge the intent.
- If the other agent has already merged an equivalent change, drop your commit
  (`git rebase --skip`) rather than re-landing a near-duplicate.
- Never force-push or rewrite a branch the other agent may have based work on.
  With no remote configured, the risk is local: check `scripts/lanes.sh` for
  a lane branched off yours before any history rewrite.

## Cross-review in practice

Every tracked implementation task requires review by the other model at the
exact head that may merge. Review is never author-triggered or automated:

1. The author finishes the lane, rebases on `develop`, runs the required checks,
   and publishes a PR or local handoff containing the exact head SHA, what
   changed, what to check, and what was deliberately left out. Then it stops
   and returns control to the founder. The author must not invoke the other
   model, spawn a reviewer, or enqueue review automation.
2. The founder explicitly starts a separate session of the **other** model and
   asks it to review that SHA. For a local lane, point it at
   `.worktrees/<slug>`; for a PR, provide the PR number and head SHA.
3. The reviewer first verifies that the checked-out or remote head equals the
   founder-requested SHA, then posts findings as `blocker` / `required` /
   `suggestion`, each
   with a citation (a rule in `AGENTS.md` / `README.md`, or a concrete failure
   scenario). No citation → it is a `suggestion` and does not gate the merge.
4. The author adjudicates every finding (`accept` / `already-done` / `reject`
   with evidence / `out-of-scope`), fixes the whole class, and re-checks its
   own diff before replying. A fix changes the head, so the author hands the
   new SHA back to the founder; only the founder may trigger the next review.
5. Merge commit body records:
   ```
   Reviewer: Codex
   Reviewed head: <sha>
   ```
6. Two rounds max. Still contested → both stop, write a
   `Needs founder decision` block, and ask.

The reviewer uses its own personal GitHub App identity for any GitHub read or
write. Codex never uses Claude Code's App profile, and Claude Code never uses
Codex's.

## Handoff notes

`docs/agents/handoffs/` holds one markdown file per lane, deleted when the
lane merges. It is the only channel the two agents have to each other — they
never share a session. Keep it factual: what changed, what is verified, what
is assumed, what is left.
