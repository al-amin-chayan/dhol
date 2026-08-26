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
        # A restore that reloads settled state but loses pending scheduled work
        # is not a usable restore, and Postiz cannot repair it: at v2.23.0 the
        # orchestrator only re-queues posts whose publish time is already past,
        # so a future job must come back with its own instant or the drill fails.
        "pending_post_restored",
        "pending_post_tenant_correct",
        "pending_post_time_preserved",
        # A row is not a schedule. The post must still be queued for sending,
        # and the workflow that will send it must exist, or the restore has
        # produced a post that never fires at its time.
        "pending_post_still_queued",
        "workflow_execution_restored",
        # The publisher must still be able to manage that workflow, not merely
        # hold it: lifecycle operations go through Temporal's Visibility store,
        # which the rebuild empties.
        "pending_post_manageable",
    ),
    # Mixpost Lite has no tenant boundary and no machine credential to restore,
    # so requiring either would be requiring a capability the edition lacks.
    "mixpost-lite": ("login_restored", "label_restored"),
}


# Postiz post states that still represent work waiting to be sent. A restored
# DRAFT is a row that came back without its schedule, which is exactly the
# false pass this drill exists to catch.
QUEUED_STATES = {"QUEUE", "PENDING"}


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
    results = dict(results)
    if candidate == "postiz":
        state = results.get("pending_post_state")
        results["pending_post_still_queued"] = (
            isinstance(state, str) and state.upper() in QUEUED_STATES
        )
    missing = [name for name in required if not results.get(name)]
    leaked = bool(results.get("foreign_channel_visible"))
    behaviour = ", ".join(f"{name}={bool(results.get(name))}" for name in required)
    # A failed restore has to say enough to be diagnosed from the evidence
    # alone: which call answered what, not merely which booleans came out false.
    observed = ", ".join(
        f"{name}={results[name]!r}"
        for name in (
            "pending_post_window_status",
            "pending_post_state",
            "pending_post_restored_at",
            "pending_post_cancel_status",
            "pending_post_recheck_status",
            "pending_post_manage_detail",
            "foreign_window_status",
            "workflow_executions_before",
            "workflow_executions_after",
        )
        if name in results
    )
    if observed:
        behaviour = f"{behaviour}; observed: {observed}"
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
    parser.add_argument("--workflow-executions-before", default="")
    parser.add_argument("--workflow-executions-after", default="")
    parser.add_argument(
        "--workflow-execution-restored",
        default="",
        help="whether the scheduler still holds an open workflow execution after the restore",
    )
    args = parser.parse_args()

    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = None
    if results is not None and args.workflow_execution_restored:
        # Measured against the scheduler's own store by the caller, because the
        # publisher's HTTP API cannot see whether the workflow exists.
        results["workflow_execution_restored"] = args.workflow_execution_restored == "true"
        results["workflow_executions_before"] = args.workflow_executions_before
        results["workflow_executions_after"] = args.workflow_executions_after
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
