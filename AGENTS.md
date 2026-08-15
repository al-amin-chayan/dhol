# Agent Instructions — Dholbeat repo root

Dholbeat is the brand-agnostic social growth platform described in
`README.md` (read it first — it is the founding plan and the source of truth
for scope, hosting, costs, and phases).

This repo is **LLM-driven and dual-agent**: **Claude Code** and **Codex** both
work here, often *at the same time*. The human is the decision-maker for
ambiguous calls, not the dispatcher.

> This file auto-loads into every Codex session and (via the `CLAUDE.md`
> symlink) every Claude Code session. Keep it lean — summary here, procedural
> detail in `docs/agents/parallel-work.md`.

## Founder constraints (read first)

1. **Solo, self-funded founder.** Every paid line item is personal cash. This
   platform's own marginal cost ceiling is **$10–25/mo**, inside a ≤$75/mo
   total growth budget. Default to free/self-hosted; never propose a $99/mo
   SaaS tier. Show a monthly-cost table whenever you add a paid component.
2. **Office laptop only, chronically full SSD.** Nothing load-bearing may live
   only on the laptop. Everything must be reproducible from git: compose files,
   n8n flow exports (JSON), brand profiles, prompts. No plaintext secret may be
   committed. SOPS+age ciphertext is allowed only under the committed
   `.sops.yaml` policy; age private keys and provider recovery logins live in a
   password manager, and `.env` files are **never** committed. Generated media
   is ephemeral — purge after publish.
3. **Disk is the binding constraint** on the VPSDime host (§5 of `README.md`).
   Anything that grows unboundedly on disk is a bug.

## Parallel work — lane discipline (the core rule here)

Both agents may be running right now. Assume the other one is editing files you
cannot see.

- **One agent, one worktree, one branch.** Never work in the primary checkout
  (`~/Projects/dholbeat`) for anything beyond reading and merging. Create your
  workspace with:

  ```
  scripts/new-worktree.sh --name <slug> --agent claude|codex
  ```

  It creates `.worktrees/<slug>/` on branch `<agent>/<slug>` and writes
  `.dholbeat-agent` so any session opened there knows who it is.
  Remove it with `scripts/rm-worktree.sh <slug>` once merged.
- **Check who else is working before you start.** `git worktree list` and
  `git branch --list 'claude/*' 'codex/*'` show the other agent's active lanes.
  If your task overlaps a live lane, say so and pick different work or narrow
  your scope — do not race.
- **Own directories, not lines.** Claim the smallest set of top-level paths
  your task needs and stay inside them (see the layout table below). Two agents
  editing the same file in the same hour is a process failure, not a merge
  problem to solve later.
- **`README.md` and `AGENTS.md` are shared, high-contention files.** Append to
  the change log / open decisions; do not restructure them while another lane
  is open. Announce restructures before starting.
- **Develop-first branch flow.** Routine lanes branch from local `develop` and
  PR into `develop`. `main` is promotion-only: the only valid PR source for
  `main` is `develop`. Never push directly to either protected branch.
- **Rebase before merging, never force-push a branch the other agent may have
  based work on.** Fetch with the acting agent's App identity and rebase
  routine work on local `develop`.
- **Small, complete commits.** Conventional Commits. Merge into a protected
  branch only when the lane is complete and cross-reviewed.

Detail — worktree lifecycle, conflict recovery, handoff notes:
`docs/agents/parallel-work.md`. Protected-branch topology and reproducible
GitHub rulesets: `docs/agents/branch-workflow.md`.

## Cross-review rule

- Work authored by **Claude Code** is reviewed by **Codex**, and work authored
  by **Codex** is reviewed by **Claude Code**, before it merges into `develop`
  or `main`.
  A fresh session of the *same* model does not count — correlated failure
  modes are the whole reason the rule exists.
- **Cross-review is human-triggered only.** The author stops after publishing
  the exact head SHA and handoff. It must not invoke the other model, spawn a
  reviewer, enqueue an automated review, or otherwise trigger its own review.
  The founder starts every review round in a separate session of the other
  model. Any author fix changes the head and needs a new founder-triggered
  cross-review before merge.
- Cheap-tier subagents inherit their parent's brain: a Sonnet subagent under
  Claude is still Claude and does not satisfy cross-review.
- Reviewer mindset is adversarial: verify claims against files and against
  `README.md`'s constraints (cost, disk, disclosure rules), not against the
  author's summary.
- Record the review verdict in the merge commit body or in the lane's handoff
  note: `Reviewer: <Codex|Claude Code>` + `Reviewed head: <sha>`.
- Findings are `blocker` / `required` / `suggestion`. The implementer
  adjudicates each (`accept` / `already-done` / `reject` with evidence) before
  fixing. Two rounds max; still contested → stop and ask the founder.

## GitHub identity

- Every GitHub command must use `scripts/github-app-gh ...`; authenticated Git
  must use `scripts/github-app-git ...` with an explicit HTTPS GitHub URL.
  Both wrappers mint a fresh, short-lived token and fail closed before invoking
  `gh` or `git`; never fall back to ambient authentication, a personal token,
  SSH credentials, or a connected personal account.
- The helper infers the running agent and loads only its personal profile from
  `~/.config/github-agent-apps/`: Codex uses `codex.env` and Claude Code uses
  `claude.env`. An agent must never request, read, copy, or use the other
  agent's profile or private key.
- The personal Apps are repository-agnostic. To authorize another personal
  repository, enable that repository on each App installation; do not create
  repository-specific Apps or copy private keys into a repository.
- After any GitHub write, verify that GitHub recorded the expected App bot
  identity reported by `scripts/github-app-token.sh --expected-login`.

## Repo layout & ownership

| Path | Contents | Typical lane |
|---|---|---|
| `.github/` | Read-only CI workflows and repository automation | tooling lane |
| `README.md` | Founding plan, decisions, change log | shared — append only |
| `brands/` | Per-brand profile YAML (the extension point, §4) | brand lane |
| `infra/` | Ansible/OpenTofu desired state, inventory, SOPS policy/ciphertext | infra lane |
| `stack/` | Docker compose, env templates, host bootstrap | infra lane |
| `n8n/` | Exported n8n flow JSON (researcher, drafting, publish) | pipeline lane |
| `prompts/` | LLM prompt templates, brand-agnostic | content lane |
| `scripts/` | Repo tooling (worktrees, checks) | tooling lane |
| `docs/` | Runbooks, agent docs, research notes | any |

Adding a brand must mean **adding a file under `brands/`** — never a code
change. If a task tempts you to hard-code `poripati` or `w3exam` anywhere
outside `brands/`, that is the bug; fix the abstraction instead.

## Working efficiently (token budget)

- **Use RTK for noisy shell commands**: `rtk git status`, `rtk grep`, `rtk ls`,
  `rtk find`, `rtk read`. Prefer the native Read/Grep/Glob tools first.
- **Choose the model per delegated task — never silently inherit the session
  model.** Mechanical work (locating files, grep sweeps, collating) → cheapest
  tier (Claude: Haiku; Codex: low reasoning). Well-specified implementation →
  mid tier (Sonnet / medium). Design, cross-component reasoning, security or
  cost review, adversarial review → top tier (Opus / high). When torn, pick
  cheaper and escalate on failure.
- **Delegate only genuinely large, independent, parallel work.** Subagents
  protect main-thread context and enable parallelism; they do **not** reduce
  total tokens. A handful of files you can name → read them yourself.
- Never commit generated media, `node_modules`, exports of secrets, or n8n
  credentials blobs.

## Hard rules (project-specific)

- **Nothing publishes without human approval** in the brand's Telegram channel.
  Any flow that can post autonomously is a defect.
- **No AI-avatar testimonials, ever.** Honour platform AI-disclosure rules
  (Meta, TikTok, YouTube) — see `README.md` §8.
- **Bangla text is never rendered by an image model.** Always a separate
  overlay step.
- **No plaintext secrets in git.** SOPS+age-encrypted values may be committed
  only as `*.sops.yml` under the `.sops.yaml` policy with CI verification. Age
  private keys and provider recovery logins stay in the password manager;
  `.env` files are never committed.
- **No unbounded disk growth.** Media is purge-after-publish.

## Open items needing the founder

Tracked in `README.md` §9. Do not silently decide these — surface them:
domain registration, GitHub repo creation, Postiz vs Mixpost, approval-bot
choice, per-brand X usage, media archival.
