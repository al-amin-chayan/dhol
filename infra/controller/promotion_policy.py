#!/usr/bin/env python3
"""Read-only promotion ancestry and synchronization policy."""

from __future__ import annotations

import re
from typing import Any, Callable

SYNC_REF = re.compile(r"^(codex|claude)/sync-main-develop-[a-z0-9-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def snapshot(get: Callable[[str], Any]) -> dict[str, Any]:
    main = get("git/ref/heads/main")["object"]["sha"]
    develop = get("git/ref/heads/develop")["object"]["sha"]
    if not SHA.fullmatch(main) or not SHA.fullmatch(develop):
        raise ValueError("invalid protected branch SHA")
    comparison = get(f"compare/{main}...{develop}?per_page=1")
    return {
        "main": main,
        "develop": develop,
        "synchronized": comparison["merge_base_commit"]["sha"] == main,
    }


def findings(
    pull: dict[str, Any],
    state: dict[str, Any],
    get: Callable[[str], Any],
    *,
    require_merge_method: bool = True,
) -> list[str]:
    base = pull["base"]["ref"]
    head = pull["head"]["ref"]
    head_sha = pull["head"]["sha"]
    is_sync = SYNC_REF.fullmatch(head) is not None
    head_repository = (pull["head"].get("repo") or {}).get("full_name")
    base_repository = (pull["base"].get("repo") or {}).get("full_name")
    same_repository = bool(head_repository) and head_repository == base_repository
    if base not in {"main", "develop"}:
        return ["unsupported promotion policy base"]
    if base == "main":
        errors = []
        if not same_repository:
            errors.append("promotion must use this repository's develop branch")
        if head != "develop" or head_sha != state["develop"]:
            errors.append("promotion must use the exact current develop head")
        if not state["synchronized"]:
            errors.append("promotion blocked: synchronize main into develop before opening/reviewing it")
        return errors
    if not is_sync:
        if state["synchronized"]:
            return []
        return ["integration paused: merge a reviewed sync-main-develop-* PR immediately after promotion"]

    errors = []
    if state["synchronized"]:
        errors.append("synchronization is unnecessary: main is already an ancestor of develop")
    if not same_repository:
        errors.append("synchronization must use an agent-owned branch in this repository")
    commit = get(f"git/commits/{head_sha}")
    develop_commit = get(f"git/commits/{state['develop']}")
    parents = [parent["sha"] for parent in commit["parents"]]
    if parents != [state["develop"], state["main"]]:
        errors.append("sync head must have exactly current develop and current main as its ordered parents")
    if commit["tree"]["sha"] != develop_commit["tree"]["sha"]:
        errors.append("sync must change ancestry only; reconcile content in a separate reviewed lane")
    if require_merge_method and (pull.get("auto_merge") or {}).get("merge_method") != "merge":
        errors.append("sync requires native auto-merge with merge method merge; squash/rebase/missing method is blocked")
    return errors
