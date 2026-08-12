#!/usr/bin/env bash
# Show who is working on what right now. Run this BEFORE starting a task so
# you don't pick work that overlaps the other agent's open lane.
#
# Usage: scripts/lanes.sh
set -euo pipefail

REPO_ROOT="$(git worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print; exit }')"
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

printf '\n== active lanes (worktrees) ==\n'
found=0
while IFS= read -r wt; do
  [ "$wt" = "$REPO_ROOT" ] && continue
  found=1
  slug="$(basename "$wt")"
  agent="unknown"
  [ -f "$wt/.dholbeat-agent" ] && agent="$(tr -d '[:space:]' < "$wt/.dholbeat-agent")"
  branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  ahead="$(git -C "$wt" rev-list --count "main..$branch" 2>/dev/null || echo '?')"
  dirty="clean"
  [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ] && dirty="DIRTY"
  printf '  %-24s agent=%-7s branch=%-32s +%s commits  %s\n' \
    "$slug" "$agent" "$branch" "$ahead" "$dirty"
  # Touched top-level paths — the overlap signal that matters.
  paths="$(git -C "$wt" diff --name-only "main...$branch" 2>/dev/null \
    | cut -d/ -f1 | sort -u | tr '\n' ' ')"
  uncommitted="$(git -C "$wt" status --porcelain 2>/dev/null \
    | awk '{print $NF}' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
  [ -n "$paths$uncommitted" ] && printf '      owns: %s%s\n' "$paths" "$uncommitted"
done < <(git worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print }')
[ "$found" -eq 0 ] && printf '  (none — primary checkout only)\n'

printf '\n== lane branches ==\n'
git branch --list 'claude/*' 'codex/*' --format='  %(refname:short)  (%(committerdate:relative))' || true

printf '\n== primary checkout ==\n'
git -C "$REPO_ROOT" status --short --branch | sed 's/^/  /'
printf '\n'
