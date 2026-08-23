#!/usr/bin/env python3
"""Load, validate offline, and render the committed production host baseline.

``infra/inventories/production/hosts.yml`` is the non-secret identity manifest.
It deliberately carries no address. This module turns that manifest plus one
committed per-host baseline contract into the Ansible inventory the shared
baseline roles consume, and proves offline — without contacting any host — that
the committed contract already satisfies
``infra/roles/base/files/validate_contract.py``.

The rendered inventory is an operator artifact. It carries the local address
override supplied on the command line and therefore belongs under gitignored
``.artifacts/`` or a fresh temporary directory, never in Git.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

import yaml


SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:api_?key|credential|password|private_?key|secret|token)(?:$|_)",
    re.IGNORECASE,
)
HOST_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
OVERRIDE_VARIABLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SUPPORTED_ROLES = {"core", "publisher"}
BOOTSTRAP_IDENTITIES = {"root", "ubuntu", "debian"}
REQUIRED_TOP_LEVEL = (
    "schema_version",
    "host_id",
    "host_role",
    "target_environment",
    "provider",
    "expected_host",
    "bootstrap",
    "admin",
    "break_glass",
    "ssh",
    "application_bindings",
    "managed_directories",
)
REQUIRED_PROVIDER = (
    "vendor",
    "plan",
    "account_boundary",
    "datacenter",
    "purchase_receipt_location",
    "monthly_cost_usd",
)
REQUIRED_EXPECTED_HOST = (
    "os_image",
    "distribution",
    "distribution_version",
    "architecture",
    "memory_mb",
    "disk_total_mb",
    "disk_free_mb",
    "public_interface",
)
REQUIRED_BOOTSTRAP = (
    "identity",
    "authentication",
    "address_source",
    "address_variable",
    "known_hosts_source",
)


def repository_root(start: Path) -> Path:
    return start.resolve()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_contract_module(root: Path):
    contract_path = root / "infra/roles/base/files/validate_contract.py"
    spec = importlib.util.spec_from_file_location("dholbeat_baseline_contract", contract_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {contract_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def role_defaults(root: Path, role: str) -> dict[str, Any]:
    document = load_yaml(root / f"infra/roles/{role}/defaults/main.yml")
    return document if isinstance(document, dict) else {}


def baseline_directory(root: Path) -> Path:
    return root / "infra/inventories/production/baseline"


def baseline_path(root: Path, host_id: str) -> Path:
    return baseline_directory(root) / f"{host_id}.yml"


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


ADDRESS_SCAN_EXEMPT_ROOTS = ("application_bindings",)


def bare_address_findings(value: Any, label: str, path: tuple[str, ...] = ()) -> list[str]:
    """Reject committed host addresses.

    ``ssh.allow_cidrs`` holds networks rather than addresses, and
    ``application_bindings`` legitimately declares the loopback or private
    address a future service may bind to. Everything else must stay
    address-free so a replacement host needs no repository change.
    """

    findings: list[str] = []
    if path[:1] in {(root,) for root in ADDRESS_SCAN_EXEMPT_ROOTS}:
        return findings
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(bare_address_findings(child, label, (*path, str(key))))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(bare_address_findings(child, label, (*path, str(index))))
    elif isinstance(value, str):
        location = ".".join(path)
        for token in re.split(r"[\s,]+", value):
            candidate = token.strip("[]()<>\"'")
            if not candidate:
                continue
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            findings.append(
                f"{label}: committed host address is forbidden at {location}; "
                "addresses are operator extra-vars only"
            )
    return findings


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def structural_findings(document: Any, label: str) -> list[str]:
    findings: list[str] = []
    if not isinstance(document, dict):
        return [f"{label}: expected a YAML mapping"]
    if document.get("schema_version") != 1:
        findings.append(f"{label}: schema_version must be 1")
    for field in REQUIRED_TOP_LEVEL:
        if field not in document:
            findings.append(f"{label}: required field is missing: {field}")
    if findings:
        return findings

    host_id = document["host_id"]
    if not isinstance(host_id, str) or HOST_ID_RE.fullmatch(host_id) is None:
        findings.append(f"{label}: host_id must be a lowercase identifier")
    if document["host_role"] not in SUPPORTED_ROLES:
        findings.append(f"{label}: host_role must be one of {sorted(SUPPORTED_ROLES)}")
    if document["target_environment"] != "production":
        findings.append(f"{label}: target_environment must be production")

    provider = document["provider"]
    if not isinstance(provider, dict):
        findings.append(f"{label}: provider must be a mapping")
    else:
        for field in REQUIRED_PROVIDER:
            if field not in provider:
                findings.append(f"{label}: provider.{field} must be recorded")
        if not _positive_int(provider.get("monthly_cost_usd")):
            findings.append(f"{label}: provider.monthly_cost_usd must be a positive integer")

    expected_host = document["expected_host"]
    if not isinstance(expected_host, dict):
        findings.append(f"{label}: expected_host must be a mapping")
    else:
        for field in REQUIRED_EXPECTED_HOST:
            if field not in expected_host:
                findings.append(f"{label}: expected_host.{field} must be recorded")
        if expected_host.get("os_image") != "ubuntu-24.04":
            findings.append(f"{label}: expected_host.os_image must be ubuntu-24.04")

    bootstrap = document["bootstrap"]
    if not isinstance(bootstrap, dict):
        findings.append(f"{label}: bootstrap must be a mapping")
    else:
        for field in REQUIRED_BOOTSTRAP:
            if field not in bootstrap:
                findings.append(f"{label}: bootstrap.{field} must be recorded")
        if bootstrap.get("identity") not in BOOTSTRAP_IDENTITIES:
            findings.append(f"{label}: bootstrap.identity must be a provider bootstrap login")
        if bootstrap.get("authentication") != "public-key-only":
            findings.append(f"{label}: bootstrap.authentication must be public-key-only")
        if bootstrap.get("address_source") != "operator-extra-vars":
            findings.append(f"{label}: bootstrap.address_source must be operator-extra-vars")
        variable = bootstrap.get("address_variable")
        if not isinstance(variable, str) or OVERRIDE_VARIABLE_RE.fullmatch(variable) is None:
            findings.append(f"{label}: bootstrap.address_variable must name one override variable")

    admin = document["admin"]
    if not isinstance(admin, dict) or not admin.get("authorized_keys"):
        findings.append(f"{label}: admin.authorized_keys must list the approved public keys")

    ssh = document["ssh"]
    if not isinstance(ssh, dict):
        findings.append(f"{label}: ssh must be a mapping")
    else:
        if not _positive_int(ssh.get("port")) or ssh.get("port", 0) > 65535:
            findings.append(f"{label}: ssh.port must be a valid port")
        allow_cidrs = ssh.get("allow_cidrs")
        if not isinstance(allow_cidrs, list) or not allow_cidrs:
            findings.append(f"{label}: ssh.allow_cidrs must list at least one network")
        else:
            for network in allow_cidrs:
                try:
                    ipaddress.ip_network(str(network), strict=True)
                except ValueError:
                    findings.append(f"{label}: ssh.allow_cidrs contains an invalid network: {network}")

    directories = document["managed_directories"]
    if not isinstance(directories, list) or not directories:
        findings.append(f"{label}: managed_directories must catalog every baseline writable path")
    else:
        for index, entry in enumerate(directories):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                findings.append(f"{label}: managed_directories[{index}].path must be absolute")
                continue
            path = PurePosixPath(entry["path"])
            if not path.is_absolute() or ".." in path.parts:
                findings.append(f"{label}: managed_directories[{index}].path must be a specific absolute path")
    return findings


def synthetic_controller_source(allow_cidrs: list[Any]) -> str:
    """Pick a declared allowlist member so the offline contract check is exact.

    The real controller address is never committed. The offline check answers the
    question the reviewer actually cares about: if the controller connects from
    inside the declared allowlist, does the committed contract hold?
    """

    for network in allow_cidrs:
        try:
            parsed = ipaddress.ip_network(str(network), strict=True)
        except ValueError:
            continue
        return str(next(parsed.hosts(), parsed.network_address))
    return ""


def contract_payload(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    base = role_defaults(root, "base")
    docker = role_defaults(root, "docker")
    expected_host = document["expected_host"]
    admin = document["admin"]
    ssh = document["ssh"]
    interface = expected_host["public_interface"]
    port = int(ssh["port"])
    directories = document["managed_directories"]
    return {
        "schema_version": 1,
        "target_environment": document["target_environment"],
        "facts": {
            "distribution": expected_host["distribution"],
            "distribution_version": expected_host["distribution_version"],
            "architecture": expected_host["architecture"],
            "memory_mb": int(expected_host["memory_mb"]),
            "disk_total_mb": int(expected_host["disk_total_mb"]),
            "disk_free_mb": int(expected_host["disk_free_mb"]),
        },
        "resource_minimums": {
            "memory_mb": int(base["base_minimum_memory_mb"]),
            "disk_total_mb": int(base["base_minimum_disk_total_mb"]),
            "disk_free_mb": int(base["base_minimum_disk_free_mb"]),
        },
        "admin": {
            "user": admin["user"],
            "uid": int(admin["uid"]),
            "authorized_keys": list(admin["authorized_keys"]),
        },
        "break_glass": document["break_glass"],
        "ssh": {
            "allow_cidrs": list(ssh["allow_cidrs"]),
            "connection_transport": "ssh",
            "controller_source": synthetic_controller_source(list(ssh["allow_cidrs"])),
            "port": port,
            "active_connection_port": port,
            "password_authentication": bool(base["base_ssh_password_authentication"]),
            "root_login": str(base["base_ssh_root_login"]),
            "second_connection_port": port,
            "second_connection_required": bool(base["base_second_connection_required"]),
        },
        "application_bindings": list(document["application_bindings"]),
        "firewall": {
            "public_interface": interface,
            "host_interfaces": ["lo", interface],
            "default_interface": interface,
        },
        "docker": {
            "apt_signing_checksum": docker["docker_apt_signing_checksum"],
            "daemon_hosts": list(docker["docker_daemon_hosts"]),
            "data_root": docker["docker_data_root"],
            "storage_driver": docker["docker_storage_driver"],
            "live_restore": docker["docker_live_restore"],
            "logging": {
                "driver": docker["docker_log_driver"],
                "max_size": docker["docker_log_max_size"],
                "max_files": int(docker["docker_log_max_files"]),
            },
            "packages": dict(docker["docker_packages"]),
        },
        "host_timezone": base["base_host_timezone"],
        "managed_directories": directories,
        "role_writable_paths": [entry["path"] for entry in directories],
    }


def manifest_hosts(root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_yaml(root / "infra/inventories/production/hosts.yml")
    if not isinstance(manifest, dict):
        return {}
    return {host["id"]: host for host in manifest.get("hosts", []) if isinstance(host, dict)}


def validate_document(root: Path, document: Any, label: str) -> list[str]:
    """Validate one host baseline contract without consulting the manifest."""

    findings = structural_findings(document, label)
    findings.extend(sensitive_key_findings(document, label))
    findings.extend(bare_address_findings(document, label))
    if findings:
        return sorted(set(findings))

    try:
        payload = contract_payload(root, document)
    except (KeyError, TypeError, ValueError) as error:
        return sorted(set([*findings, f"{label}: cannot build the baseline contract: {error}"]))

    contract = load_contract_module(root)
    findings.extend(f"{label}: {finding}" for finding in contract.validate_contract(payload))
    return sorted(set(findings))


def validate_host_baseline(root: Path, host_id: str) -> list[str]:
    path = baseline_path(root, host_id)
    label = path.relative_to(root).as_posix()
    try:
        document = load_yaml(path)
    except (OSError, yaml.YAMLError) as error:
        return [f"{label}: cannot load YAML: {error}"]

    findings = validate_document(root, document, label)
    if not isinstance(document, dict) or "host_id" not in document:
        return findings

    if document["host_id"] != host_id:
        findings.append(f"{label}: host_id must match the file name")
    manifest = manifest_hosts(root)
    manifest_host = manifest.get(document["host_id"])
    if manifest_host is None:
        findings.append(f"{label}: host is absent from the production inventory manifest")
    else:
        if manifest_host.get("role") != document.get("host_role"):
            findings.append(f"{label}: host_role differs from the production inventory manifest")
        expected_image = (document.get("expected_host") or {}).get("os_image")
        if manifest_host.get("os") != expected_image:
            findings.append(f"{label}: expected_host.os_image differs from the inventory manifest os")
    return sorted(set(findings))


def validate_all(root: Path) -> list[str]:
    """Validate every committed host baseline contract.

    An empty directory is a valid state, not a failure: a host only gains a
    baseline contract when its own work package provisions it. ``core-1`` is
    adopted by parity under its own package and has no contract here yet.
    """

    directory = baseline_directory(root)
    if not directory.is_dir():
        return [f"{directory.relative_to(root).as_posix()}: production baseline directory is missing"]
    findings: list[str] = []
    for path in sorted(directory.glob("*.yml")):
        findings.extend(validate_host_baseline(root, path.stem))
    return sorted(set(findings))


def render_inventory(
    root: Path,
    host_id: str,
    address: str,
    stage: str,
    identity_file: str,
    known_hosts_file: str,
) -> dict[str, Any]:
    document = load_yaml(baseline_path(root, host_id))
    if not isinstance(document, dict):
        raise ValueError(f"{host_id}: baseline contract is not a mapping")
    try:
        ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError(f"{host_id}: --address must be a literal IP address") from error
    if stage not in {"bootstrap", "converged"}:
        raise ValueError("stage must be bootstrap or converged")

    admin = document["admin"]
    ssh = document["ssh"]
    directories = document["managed_directories"]
    group_all = load_yaml(root / "infra/inventories/production/group_vars/all.yml")
    connection_user = document["bootstrap"]["identity"] if stage == "bootstrap" else admin["user"]
    host_vars: dict[str, Any] = {
        "ansible_host": address,
        "ansible_port": int(ssh["port"]),
        "ansible_user": connection_user,
        "ansible_private_key_file": identity_file,
        "dholbeat_host_id": document["host_id"],
        "dholbeat_host_role": document["host_role"],
        "dholbeat_stage": stage,
        "host_timezone": group_all["host_timezone"],
        "release_receipt_path": group_all["release_receipt_path"],
        "baseline_target_environment": document["target_environment"],
        "baseline_admin_user": admin["user"],
        "baseline_admin_uid": int(admin["uid"]),
        "baseline_admin_authorized_keys": list(admin["authorized_keys"]),
        "baseline_break_glass": document["break_glass"],
        "baseline_ssh_allow_cidrs": list(ssh["allow_cidrs"]),
        "baseline_public_interface": document["expected_host"]["public_interface"],
        "baseline_second_connection_host": address,
        "baseline_second_connection_port": int(ssh["port"]),
        "baseline_second_connection_identity_file": identity_file,
        "baseline_second_connection_known_hosts_file": known_hosts_file,
        "baseline_application_bindings": list(document["application_bindings"]),
        "baseline_managed_directories": directories,
        "baseline_role_writable_paths": [entry["path"] for entry in directories],
    }
    return {
        "all": {
            "children": {
                "baseline_targets": {"hosts": {document["host_id"]: host_vars}},
                document["host_role"]: {"hosts": {document["host_id"]: {}}},
            }
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate every committed host baseline offline")

    render = subparsers.add_parser("render", help="render the operator Ansible inventory")
    render.add_argument("--limit", required=True)
    render.add_argument("--address", required=True)
    render.add_argument("--stage", choices=["bootstrap", "converged"], required=True)
    render.add_argument("--identity-file", required=True)
    render.add_argument("--known-hosts-file", required=True)
    render.add_argument("--output", type=Path, required=True)

    contract = subparsers.add_parser("contract", help="print the offline baseline contract payload")
    contract.add_argument("--limit", required=True)

    arguments = parser.parse_args()
    root = repository_root(arguments.root)

    if arguments.command == "check":
        findings = validate_all(root)
        if findings:
            for finding in findings:
                print(f"host baseline failure: {finding}")
            raise SystemExit(1)
        committed = sorted(path.stem for path in baseline_directory(root).glob("*.yml"))
        print(f"production host baseline passed: {committed or 'no host contract committed yet'}")
        return

    if arguments.command == "contract":
        document = load_yaml(baseline_path(root, arguments.limit))
        json.dump(contract_payload(root, document), sys.stdout, indent=2, sort_keys=True)
        print()
        return

    findings = validate_host_baseline(root, arguments.limit)
    if findings:
        for finding in findings:
            print(f"host baseline failure: {finding}")
        raise SystemExit(1)
    inventory = render_inventory(
        root,
        arguments.limit,
        arguments.address,
        arguments.stage,
        arguments.identity_file,
        arguments.known_hosts_file,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(inventory, handle, default_flow_style=False, sort_keys=True)
    arguments.output.chmod(0o600)
    print(f"rendered operator inventory: {arguments.output}")


if __name__ == "__main__":
    main()
