"""Offline WP-06A guards; this module performs no provider or state writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[3]


class ContractError(ValueError):
    """A safe, value-free diagnostic suitable for redacted evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def no_change_plan(plan: dict, expected: dict[str, dict[str, str]]) -> None:
    """Require a complete managed-resource plan with exact adoption identities.

    Import blocks may add state, but may never change a provider resource.
    Callers supply a reviewed address-to-identity map, not a map extracted
    from the candidate plan. Output/state values are never logged here.
    """
    require(isinstance(plan, dict), "plan must be an object")
    require(plan.get("format_version") == "1.2", "unsupported plan format")
    # Locked OpenTofu 1.12.5 omits `complete`; exact inventory coverage,
    # errored=false, known values and no deferred changes are mandatory.
    # Reject an explicit incomplete marker if one is supplied.
    require("complete" not in plan or plan["complete"] is True, "incomplete plan")
    lock = yaml.safe_load((ROOT / "toolchain.lock.yml").read_text())
    require(
        plan.get("terraform_version") == str(lock["tools"]["tofu"]["version"]),
        "plan must come from the locked OpenTofu version",
    )
    require(plan.get("errored") is False, "errored or unverified plan")
    require(isinstance(expected, dict) and bool(expected), "empty adoption inventory")
    require(
        all(
            isinstance(k, str)
            and isinstance(v, dict)
            and set(v) == {"resource_id", "import_id"}
            and all(isinstance(s, str) and s for s in v.values())
            for k, v in expected.items()
        ),
        "invalid adoption inventory",
    )
    require(not plan.get("deferred_changes"), "deferred changes are forbidden")
    require(
        not plan.get("action_invocations"), "provider action invocations are forbidden"
    )
    changes = plan.get("resource_changes")
    require(isinstance(changes, list), "resource changes missing")
    seen = set()
    for item in changes:
        require(isinstance(item, dict), "invalid resource change")
        address = item.get("address")
        require(
            isinstance(address, str) and address in expected,
            "unreviewed resource address",
        )
        require(address not in seen, "duplicate resource address")
        seen.add(address)
        require(
            item.get("mode") == "managed",
            "only managed adoption resources are supported",
        )
        require(
            item.get("provider_name")
            in {
                "registry.opentofu.org/cloudflare/cloudflare",
                "registry.terraform.io/cloudflare/cloudflare",
            },
            "unexpected adoption provider",
        )
        change = item.get("change")
        require(isinstance(change, dict), "resource change body missing")
        require(change.get("actions") == ["no-op"], "provider mutation is forbidden")
        require(
            not change.get("after_unknown"), "unknown post-plan values are forbidden"
        )
        after = change.get("after")
        require(
            isinstance(after, dict)
            and after.get("id") == expected[address]["resource_id"],
            "resource identity differs from adoption inventory",
        )
        importing = change.get("importing")
        if importing is not None:
            require(
                isinstance(importing, dict)
                and importing.get("id") == expected[address]["import_id"],
                "import identity differs from adoption inventory",
            )
    require(seen == set(expected), "adoption inventory is not fully planned")
    # Drift can otherwise be absorbed into state while the main diff is no-op.
    require(not plan.get("resource_drift"), "resource drift requires separate review")
    outputs = plan.get("output_changes", {})
    require(isinstance(outputs, dict), "invalid output changes")
    require(
        all(
            isinstance(c, dict) and c.get("actions") == ["no-op"]
            for c in outputs.values()
        ),
        "output changes require separate review",
    )
    checks = plan.get("checks", [])
    require(
        isinstance(checks, list)
        and all(isinstance(c, dict) and c.get("status") == "pass" for c in checks),
        "unverified plan checks",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    guard = sub.add_parser("no-change-plan")
    guard.add_argument("--plan", type=Path, required=True)
    guard.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    try:
        no_change_plan(
            json.loads(args.plan.read_text()), json.loads(args.expected.read_text())
        )
        print("PASS: exact adoption inventory; no provider, drift, or output changes")
    except ContractError as error:
        print(f"control-plane error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        # Parser exceptions may echo source lines containing secrets.
        print("control-plane error: unreadable or malformed input", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
