"""Offline WP-06A guards; this module performs no provider or state writes."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator
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
    require(plan.get("terraform_version") == str(lock["tools"]["tofu"]["version"]),
            "plan must come from the locked OpenTofu version")
    require(plan.get("errored") is False, "errored or unverified plan")
    require(isinstance(expected, dict) and bool(expected), "empty adoption inventory")
    require(all(isinstance(k, str) and isinstance(v, dict)
                and set(v) == {"resource_id", "import_id"}
                and all(isinstance(s, str) and s for s in v.values()) for k, v in expected.items()),
            "invalid adoption inventory")
    require(not plan.get("deferred_changes"), "deferred changes are forbidden")
    require(not plan.get("action_invocations"), "provider action invocations are forbidden")
    changes = plan.get("resource_changes")
    require(isinstance(changes, list), "resource changes missing")
    seen = set()
    for item in changes:
        require(isinstance(item, dict), "invalid resource change")
        address = item.get("address")
        require(isinstance(address, str) and address in expected, "unreviewed resource address")
        require(address not in seen, "duplicate resource address")
        seen.add(address)
        require(item.get("mode") == "managed", "only managed adoption resources are supported")
        require(item.get("provider_name") in {"registry.opentofu.org/cloudflare/cloudflare",
                                             "registry.terraform.io/cloudflare/cloudflare"},
                "unexpected adoption provider")
        change = item.get("change")
        require(isinstance(change, dict), "resource change body missing")
        require(change.get("actions") == ["no-op"], "provider mutation is forbidden")
        require(not change.get("after_unknown"), "unknown post-plan values are forbidden")
        after = change.get("after")
        require(isinstance(after, dict) and after.get("id") == expected[address]["resource_id"],
                "resource identity differs from adoption inventory")
        importing = change.get("importing")
        if importing is not None:
            require(isinstance(importing, dict) and importing.get("id") == expected[address]["import_id"],
                    "import identity differs from adoption inventory")
    require(seen == set(expected), "adoption inventory is not fully planned")
    # Drift can otherwise be absorbed into state while the main diff is no-op.
    require(not plan.get("resource_drift"), "resource drift requires separate review")
    outputs = plan.get("output_changes", {})
    require(isinstance(outputs, dict), "invalid output changes")
    require(all(isinstance(c, dict) and c.get("actions") == ["no-op"] for c in outputs.values()),
            "output changes require separate review")
    checks = plan.get("checks", [])
    require(isinstance(checks, list) and all(isinstance(c, dict) and c.get("status") == "pass"
                                           for c in checks), "unverified plan checks")


def index(document: dict, key: str) -> dict:
    require(isinstance(document, dict) and document.get("schema_version") == 1,
            "unsupported registry version")
    items = document.get(key)
    require(isinstance(items, list), "registry collection missing")
    result = {}
    for item in items:
        require(isinstance(item, dict) and isinstance(item.get("id"), str), "registry ID missing")
        require(item["id"] not in result, "duplicate registry ID")
        result[item["id"]] = item
    return result


def validate_schema(document: dict, name: str) -> None:
    schema = json.loads((ROOT / "infra/schemas" / f"{name}.schema.json").read_text())
    require(Draft202012Validator(schema).is_valid(document), f"invalid {name} registry schema")


def render_ingress(routes: dict, domains: dict, services: dict, tunnels: dict, host_id: str) -> dict:
    """Render human loopback ingress only, with a terminal deny rule.

    Machine ingress needs a verified method/path/authentication proxy, and is
    intentionally rejected until that implementation is reviewed. Tunnel
    credentials are references; no token or credential value is an input.
    """
    validate_schema(routes, "route")
    validate_schema(domains, "domain")
    validate_schema(services, "service")
    route_map = index(routes, "routes")
    domain_map = index(domains, "domains")
    service_map = index(services, "services")
    tunnel_map = index(tunnels, "tunnels")
    host_map = {}
    credentials = set()
    for tid, tunnel in tunnel_map.items():
        require(set(tunnel) == {"id", "host_id", "credential_ref"},
                "tunnel registry accepts only non-secret references")
        require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", tid) is not None,
                "invalid tunnel UUID")
        host = tunnel.get("host_id")
        ref = tunnel.get("credential_ref")
        require(isinstance(host, str) and host not in host_map, "one tunnel per host is required")
        require(isinstance(ref, str) and re.fullmatch(r"[a-z][a-z0-9-]+", ref) is not None,
                "tunnel credential reference required")
        require(ref not in credentials, "shared tunnel credential reference")
        credentials.add(ref)
        host_map[host] = tid
    require(host_id in host_map, "host tunnel not declared")
    hostnames = set()
    ingress = []
    for route in sorted(route_map.values(), key=lambda item: item["id"]):
        service = service_map.get(route["service_id"])
        domain = domain_map.get(route["domain_id"])
        require(service is not None and domain is not None, "orphan route reference")
        require(route["host_id"] in host_map, "route tunnel not declared")
        require(service.get("host_id") == route["host_id"], "cross-host route")
        require(service.get("project_id") == route["owner"], "cross-project route")
        require(route["id"] in service.get("route_ids", []), "service route backreference missing")
        require(service.get("exposure") == "route", "service is not declared for route exposure")
        require(route["caller"] == "human" and route["access"]["mode"] == "enforced",
                "machine ingress requires separately verified proxy")
        require(route["path"] == "/", "path-scoped ingress requires separately verified proxy")
        require(domain["name"] not in hostnames, "duplicate route hostname")
        hostnames.add(domain["name"])
        origin = route["origin"]
        require(origin["kind"] == "loopback", "only loopback adoption origins are supported")
        try:
            loopback = origin["host"] == "localhost" or ipaddress.ip_address(origin["host"]).is_loopback
        except ValueError:
            loopback = False
        require(loopback, "public origin is forbidden")
        if route["host_id"] == host_id:
            address = origin["host"]
            if ":" in address:
                address = f"[{address}]"
            ingress.append({"hostname": domain["name"],
                            "service": f"{origin['scheme']}://{address}:{origin['port']}"})
    require(bool(ingress), "host has no adoptable ingress")
    return {"tunnel": host_map[host_id], "ingress": ingress + [{"service": "http_status:404"}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    guard = sub.add_parser("no-change-plan")
    guard.add_argument("--plan", type=Path, required=True)
    guard.add_argument("--expected", type=Path, required=True)
    render = sub.add_parser("render-ingress")
    for name in ("routes", "domains", "services", "tunnels"):
        render.add_argument(f"--{name}", type=Path, required=True)
    render.add_argument("--host", required=True)
    args = parser.parse_args()
    try:
        if args.command == "no-change-plan":
            no_change_plan(json.loads(args.plan.read_text()), json.loads(args.expected.read_text()))
            print("PASS: exact adoption inventory; no provider, drift, or output changes")
        else:
            documents = [yaml.safe_load(getattr(args, name).read_text())
                         for name in ("routes", "domains", "services", "tunnels")]
            print(yaml.safe_dump(render_ingress(*documents, args.host), sort_keys=False), end="")
    except ContractError as error:
        print(f"control-plane error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        # Parser exceptions may echo source lines containing secrets.
        print("control-plane error: unreadable or malformed input", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
