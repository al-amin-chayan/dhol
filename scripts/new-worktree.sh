#!/usr/bin/env bash
# Create an agent-isolated git worktree so Claude Code and Codex can work in
# parallel without colliding in the same working tree.
#
# Usage:
#   scripts/new-worktree.sh --name <slug> --agent claude|codex [--base <ref>]
#   scripts/new-worktree.sh --name <slug> --agent codex --branch codex/custom-name
#
# What it does
#   1. Resolves the primary checkout (safe to run from inside a worktree) and
#      creates the new worktree under <primary>/.worktrees/<slug>/ — never a
#      sibling directory, never nested inside another worktree.
#   2. Creates branch <agent>/<slug> from --base (default: main).
#   3. Writes .dholbeat-agent inside the worktree so any session opened there
#      knows which agent owns the lane, and appends an "Agent: <agent>" commit
#      trailer template via .git config commit.template.
#   4. Refuses to create a lane whose branch already exists, so two agents
#      cannot silently share one.
#
# After it finishes: cd .worktrees/<slug> and start the session there.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/new-worktree.sh --name <slug> --agent claude|codex [--base <ref>] [--branch <branch>]

examples:
  scripts/new-worktree.sh --name compose-stack --agent claude
  scripts/new-worktree.sh --name brand-profile-schema --agent codex
  scripts/new-worktree.sh --name hotfix-disk-alert --agent codex --base main
EOF
  exit "${1:-2}"
}

REPO_ROOT="$(git worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print; exit }')"
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

NAME=""
AGENT=""
BRANCH=""
BASE_REF="main"

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --name)   [ "$#" -ge 2 ] || usage; NAME="$2"; shift 2 ;;
    --agent)  [ "$#" -ge 2 ] || usage; AGENT="$2"; shift 2 ;;
    --branch) [ "$#" -ge 2 ] || usage; BRANCH="$2"; shift 2 ;;
    --base)   [ "$#" -ge 2 ] || usage; BASE_REF="$2"; shift 2 ;;
    *) echo "error: unexpected argument: $1" >&2; usage ;;
  esac
done

[ -n "$NAME" ] || { echo "error: --name is required" >&2; usage; }
case "$AGENT" in
  claude|codex) ;;
  "") echo "error: --agent is required (claude|codex)" >&2; usage ;;
  *)  echo "error: --agent must be 'claude' or 'codex' (got '$AGENT')" >&2; usage ;;
esac

# Slugify: lowercase, non-alphanumerics to '-', collapse and trim.
SLUG="$(printf '%s' "$NAME" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
[ -n "$SLUG" ] || { echo "error: --name '$NAME' slugified to nothing" >&2; exit 1; }

[ -n "$BRANCH" ] || BRANCH="${AGENT}/${SLUG}"
WT_PATH="$REPO_ROOT/.worktrees/$SLUG"

if [ -e "$WT_PATH" ]; then
  echo "error: worktree path already exists: $WT_PATH" >&2
  echo "       remove it first: scripts/rm-worktree.sh $SLUG" >&2
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "error: branch '$BRANCH' already exists — another lane may own it." >&2
  echo "       active lanes:" >&2
  git worktree list >&2
  exit 1
fi

if ! git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null; then
  echo "error: base ref '$BASE_REF' not found" >&2
  exit 1
fi

# Warn (do not block) when the other agent already has lanes open.
OTHER="claude"; [ "$AGENT" = "claude" ] && OTHER="codex"
OTHER_LANES="$(git branch --list "${OTHER}/*" --format='%(refname:short)' || true)"
if [ -n "$OTHER_LANES" ]; then
  echo "note: $OTHER currently has these lanes open — avoid overlapping paths:" >&2
  printf '  %s\n' $OTHER_LANES >&2
fi

mkdir -p "$REPO_ROOT/.worktrees"
git worktree add -b "$BRANCH" "$WT_PATH" "$BASE_REF"

printf '%s\n' "$AGENT" > "$WT_PATH/.dholbeat-agent"

# Commit template so every commit from this lane is attributable without
# faking git identities.
TEMPLATE="$WT_PATH/.git-commit-template"
cat > "$TEMPLATE" <<EOF

# Lane: $BRANCH (agent: $AGENT)
# Keep the subject in Conventional Commits form, then leave this trailer:
Agent: $AGENT
EOF
git -C "$WT_PATH" config commit.template "$TEMPLATE"

cat <<EOF

created lane
  agent   : $AGENT
  branch  : $BRANCH
  base    : $BASE_REF
  path    : $WT_PATH

next:
  cd .worktrees/$SLUG
  # start the $AGENT session here; when merged:
  #   scripts/rm-worktree.sh $SLUG
EOF
