#!/usr/bin/env python3
"""Combine one candidate's checks, drills and resources into a DG-01 verdict.

The verdict is deliberately mechanical: a candidate that cannot satisfy the
founder-approved multi-project requirement is `disqualified` regardless of how
well it performs elsewhere, and a candidate is never marked `selected` here —
only the founder records a selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# The checks that encode the founder-approved multi-project requirement from
# README.md §9. Failing or lacking any of these disqualifies a candidate.
REQUIRED_CHECKS = (
    "bootstrap.second-project",
    "api.machine-credential",
    "api.credential-tenant-bound",
    "authz.cross-tenant-read-rejected",
    "authz.cross-tenant-write-rejected",
    "authz.no-credential-rejected",
)

# An `unsupported` result on these means the probe's own positive control
# failed, so the behaviour was never measured — not that the edition lacks the
# surface. The runbook defines `viable` as every measured check and drill
# passing, so an unmeasured lifecycle or authorization check cannot be part of
# one. The gate applies only where `capabilities.machine_api` is non-null: an
# edition without a machine API reports these as `unsupported` legitimately.
UNPROVEN_PREFIXES = ("authz.", "posts.")


def build(checks: dict, drills: dict, resources: dict, version: str) -> dict:
    by_id = {check["id"]: check for check in checks["checks"]}
    blocking = {
        check_id: by_id.get(check_id, {}).get("result", "missing")
        for check_id in REQUIRED_CHECKS
    }
    disqualifiers = sorted(
        check_id for check_id, result in blocking.items() if result != "pass"
    )
    failed = sorted(check["id"] for check in checks["checks"] if check["result"] == "fail")
    unsupported = sorted(check["id"] for check in checks["checks"] if check["result"] == "unsupported")
    has_machine_api = checks["capabilities"].get("machine_api") is not None
    unproven = (
        [check_id for check_id in unsupported if check_id.startswith(UNPROVEN_PREFIXES)]
        if has_machine_api
        else []
    )
    failed_drills = sorted(drill["id"] for drill in drills["drills"] if drill["result"] != "pass")
    # Only budgets this harness actually measured may gate the verdict. Update
    # headroom needs a real 30 GB host mid-upgrade, so it is carried as
    # unmeasured rather than counted as passing.
    capacity = [
        key
        for key in ("peak_ram_within_budget", "topology_within_steady_budget")
        if not resources.get(key, False)
    ]

    if disqualifiers:
        verdict = "disqualified"
    elif failed or failed_drills or unproven:
        verdict = "viable-with-findings"
    elif capacity:
        verdict = "viable-over-budget"
    else:
        verdict = "viable"

    return {
        "schema_version": 1,
        "candidate": checks["candidate"],
        "version": version,
        "image": checks["image"],
        "variant": checks["variant"],
        "platform": checks["platform"],
        "verdict": verdict,
        "disqualifying_checks": disqualifiers,
        "failed_checks": failed,
        "unsupported_checks": unsupported,
        "unproven_checks": unproven,
        "failed_drills": failed_drills,
        "capacity_breaches": capacity,
        "unmeasured_capacity": {"update_headroom": resources.get("update_headroom")},
        "capabilities": checks["capabilities"],
        "checks": checks["checks"],
        "drills": drills["drills"],
        "resources": resources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", required=True, type=Path)
    parser.add_argument("--drills", required=True, type=Path)
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    document = build(
        json.loads(args.checks.read_text(encoding="utf-8")),
        json.loads(args.drills.read_text(encoding="utf-8")),
        json.loads(args.resources.read_text(encoding="utf-8")),
        args.version,
    )
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{document['candidate']} {document['variant']}: {document['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
