#!/usr/bin/env python3
"""Judge a restore-after-rebuild drill from its rebuild counters and app probe.

Issue #16 asks for an application-aware restore, not a row count. A dump that
reloads every row into a database the application can no longer authenticate
against is a failed restore that a count-only check would call a pass, so the
verdict here requires four things together: the database really was rebuilt
from empty, the rows came back, the application still serves the restored
state, and the tenant boundary survived.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# What the restored instance must still do for n8n to be able to use it.
REQUIRED_BEHAVIOUR = {
    "postiz": (
        "session_restored",
        "api_credential_restored",
        "own_channel_restored",
        "tenant_boundary_restored",
    ),
    # Mixpost Lite has no tenant boundary and no machine credential to restore,
    # so requiring either would be requiring a capability the edition lacks.
    "mixpost-lite": ("login_restored", "label_restored"),
}


def judge(
    results: dict | None,
    rebuilt_tables: str,
    before: str,
    after: str,
    candidate: str = "postiz",
) -> tuple[str, str]:
    required = REQUIRED_BEHAVIOUR[candidate]
    if results is None:
        return "fail", (
            f"the restore probe produced no result; the database rebuilt to "
            f"{rebuilt_tables} table(s) and holds {after} organization(s)"
        )
    missing = [name for name in required if not results.get(name)]
    leaked = bool(results.get("foreign_channel_visible"))
    behaviour = ", ".join(f"{name}={bool(results.get(name))}" for name in required)
    detail = (
        f"database volume destroyed and rebuilt to {rebuilt_tables} table(s), dump reloaded, "
        f"rows {before} -> {after}; restored instance: {behaviour}"
    )
    if rebuilt_tables != "0":
        return "fail", f"the rebuilt database was not empty before the reload — {detail}"
    if after == "0" or before != after:
        return "fail", f"the reload did not return the rows — {detail}"
    if leaked:
        return "fail", f"the restored instance exposed another project's channel — {detail}"
    if missing:
        return "fail", f"the restored instance cannot {', '.join(missing)} — {detail}"
    return "pass", detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--rebuilt-tables", required=True)
    parser.add_argument("--organizations-before", required=True)
    parser.add_argument("--organizations-after", required=True)
    parser.add_argument("--candidate", default="postiz", choices=sorted(REQUIRED_BEHAVIOUR))
    args = parser.parse_args()

    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = None
    result, detail = judge(
        results,
        args.rebuilt_tables,
        args.organizations_before,
        args.organizations_after,
        args.candidate,
    )
    print(f"{result}|{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
