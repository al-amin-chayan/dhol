#!/usr/bin/env bash
# Remove an agent lane created by scripts/new-worktree.sh.
#
# Usage:
#   scripts/rm-worktree.sh <slug> [--delete-branch] [--force]
#
# Refuses to remove a worktree with uncommitted changes or with commits not
# reachable from develop or main, unless --force is given. Losing another agent's
# unmerged work is the failure mode this guards against.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: scripts/rm-worktree.sh <slug> [--delete-branch] [--force]
EOF
  exit "${1:-2}"
}

REPO_ROOT="$(git worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print; exit }')"
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SLUG=""
DELETE_BRANCH=0
FORCE=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --delete-branch) DELETE_BRANCH=1; shift ;;
    --force) FORCE=1; shift ;;
    -*) echo "error: unknown option: $1" >&2; usage ;;
    *) [ -z "$SLUG" ] || usage; SLUG="$1"; shift ;;
  esac
done
[ -n "$SLUG" ] || usage

WT_PATH="$REPO_ROOT/.worktrees/$SLUG"
[ -d "$WT_PATH" ] || { echo "error: no worktree at $WT_PATH" >&2; exit 1; }

BRANCH="$(git -C "$WT_PATH" rev-parse --abbrev-ref HEAD)"

if [ "$FORCE" -eq 0 ]; then
  if [ -n "$(git -C "$WT_PATH" status --porcelain)" ]; then
    echo "error: $WT_PATH has uncommitted changes — commit them or pass --force" >&2
    git -C "$WT_PATH" status --short >&2
    exit 1
  fi
  MERGED_BASE=""
  for base_ref in develop main; do
    if git -C "$WT_PATH" show-ref --verify --quiet "refs/heads/$base_ref" &&
      git -C "$WT_PATH" merge-base --is-ancestor "$BRANCH" "$base_ref"; then
      MERGED_BASE="$base_ref"
      break
    fi
  done
  if [ -z "$MERGED_BASE" ]; then
    echo "error: '$BRANCH' is not merged into develop or main — merge first or pass --force" >&2
    git -C "$WT_PATH" log --oneline "develop..$BRANCH" >&2
    exit 1
  fi
fi

if [ "$FORCE" -eq 1 ]; then
  git worktree remove --force "$WT_PATH"
else
  git worktree remove "$WT_PATH"
fi
git worktree prune

if [ "$DELETE_BRANCH" -eq 1 ]; then
  if [ "$FORCE" -eq 1 ]; then
    git branch -D "$BRANCH"
  else
    git branch -d "$BRANCH"
  fi
fi

echo "removed lane: $SLUG (branch $BRANCH$([ "$DELETE_BRANCH" -eq 1 ] && echo ', deleted' || echo ', kept'))"
