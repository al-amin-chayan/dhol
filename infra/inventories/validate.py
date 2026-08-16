#!/usr/bin/env python3
"""Validate committed production inventory and non-secret group variables."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml


SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:api_?key|credential|password|private_?key|secret|token)(?:$|_)",
    re.IGNORECASE,
)
CANONICAL_ROLES = {"core": "core-1", "publisher": "publish-1"}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("expected a YAML mapping")
    return document


def schema_findings(document: dict[str, Any], schema_path: Path, label: str) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[str] = []
    for error in sorted(
        validator.iter_errors(document),
        key=lambda item: [str(part) for part in item.absolute_path],
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(f"{label}: schema at {location}: {error.message}")
    return findings


def sensitive_key_findings(value: Any, label: str, path: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = (*path, key_text)
            if SENSITIVE_KEY_RE.search(key_text):
                findings.append(f"{label}: secret-shaped key is forbidden at {'.'.join(child_path)}")
            findings.extend(sensitive_key_findings(child, label, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(sensitive_key_findings(child, label, (*path, str(index))))
    return findings


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def validate_inventory(root: Path) -> list[str]:
    inventory_dir = root / "infra/inventories/production"
    inventory_path = inventory_dir / "hosts.yml"
    group_dir = inventory_dir / "group_vars"
    findings: list[str] = []
    try:
        inventory = load_yaml(inventory_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return [f"infra/inventories/production/hosts.yml: cannot load YAML: {error}"]

    findings.extend(
        schema_findings(
            inventory,
            root / "infra/schemas/inventory.schema.json",
            "infra/inventories/production/hosts.yml",
        )
    )
    findings.extend(sensitive_key_findings(inventory, "infra/inventories/production/hosts.yml"))
    if findings:
        return sorted(set(findings))

    hosts: dict[str, dict[str, Any]] = {}
    roles: dict[str, str] = {}
    services: dict[str, str] = {}
    for host in inventory["hosts"]:
        host_id = host["id"]
        if host_id in hosts:
            findings.append(f"inventory: duplicate host ID {host_id}")
        hosts[host_id] = host
        if host["role"] in roles:
            findings.append(f"inventory: duplicate host role {host['role']}")
        roles[host["role"]] = host_id
        if _is_ip_address(host["hostname"]):
            findings.append(f"{host_id}: committed stable hostname cannot be an IP address")
        for service_id in host["service_ids"]:
            if service_id in services:
                findings.append(
                    f"{host_id}: service ID {service_id} is already owned by {services[service_id]}"
                )
            services[service_id] = host_id

    if inventory["environment"] != "production":
        findings.append("inventory: production inventory must declare environment production")
    for role, expected_host in CANONICAL_ROLES.items():
        actual_host = roles.get(role)
        if actual_host != expected_host:
            findings.append(f"inventory: canonical role {role} must be owned by {expected_host}")
    unexpected_roles = set(roles) - set(CANONICAL_ROLES)
    if unexpected_roles:
        findings.append(f"inventory: unexpected production roles {sorted(unexpected_roles)}")

    endpoints: dict[str, dict[str, Any]] = {}
    hostnames: dict[str, str] = {}
    for endpoint in inventory["public_endpoints"]:
        endpoint_id = endpoint["id"]
        if endpoint_id in endpoints:
            findings.append(f"inventory: duplicate public endpoint ID {endpoint_id}")
        endpoints[endpoint_id] = endpoint
        if endpoint["host_id"] not in hosts:
            findings.append(f"{endpoint_id}: unknown endpoint host {endpoint['host_id']}")
        prior = hostnames.get(endpoint["hostname"])
        if prior is not None:
            findings.append(
                f"{endpoint_id}: public hostname {endpoint['hostname']} is already owned by {prior}"
            )
        hostnames[endpoint["hostname"]] = endpoint_id

    group_documents: dict[str, dict[str, Any]] = {}
    for scope in ("all", "core", "publisher"):
        relative = f"infra/inventories/production/group_vars/{scope}.yml"
        try:
            document = load_yaml(root / relative)
        except (OSError, ValueError, yaml.YAMLError) as error:
            findings.append(f"{relative}: cannot load YAML: {error}")
            continue
        group_documents[scope] = document
        findings.extend(
            schema_findings(
                document,
                root / "infra/schemas/inventory-vars.schema.json",
                relative,
            )
        )
        findings.extend(sensitive_key_findings(document, relative))
        if document.get("scope") != scope:
            findings.append(f"{relative}: scope must be {scope}")

    for role in ("core", "publisher"):
        document = group_documents.get(role)
        if not document:
            continue
        expected_host = CANONICAL_ROLES[role]
        if document.get("host_ids") != [expected_host]:
            findings.append(f"group_vars/{role}.yml: host_ids must be [{expected_host}]")
        for endpoint_id in document.get("public_endpoint_ids", []):
            endpoint = endpoints.get(endpoint_id)
            if endpoint is None:
                findings.append(f"group_vars/{role}.yml: unknown public endpoint {endpoint_id}")
            elif endpoint["host_id"] != expected_host:
                findings.append(
                    f"group_vars/{role}.yml: endpoint {endpoint_id} belongs to {endpoint['host_id']}"
                )

    assigned_endpoints = {
        endpoint_id
        for role in ("core", "publisher")
        for endpoint_id in group_documents.get(role, {}).get("public_endpoint_ids", [])
    }
    missing_endpoint_assignments = set(endpoints) - assigned_endpoints
    if missing_endpoint_assignments:
        findings.append(
            f"inventory: public endpoints missing role assignment {sorted(missing_endpoint_assignments)}"
        )
    return sorted(set(findings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    findings = validate_inventory(args.root.resolve())
    if findings:
        for finding in findings:
            print(f"inventory failure: {finding}")
        raise SystemExit(1)
    print("production inventory passed")


if __name__ == "__main__":
    main()
