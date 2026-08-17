#!/usr/bin/env python3
"""Fail-closed validation for the shared host baseline inputs and facts."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import PurePosixPath
import re
import sys
from typing import Any


SUPPORTED_ARCHITECTURES = {"aarch64", "x86_64"}
SUPPORTED_CLASSIFICATIONS = {"ephemeral", "rebuildable", "retained"}
SUPPORTED_DATA_CLASSES = {"internal", "confidential"}
ADMIN_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
LOG_SIZE_RE = re.compile(r"^[1-9][0-9]{0,3}[kKmMgG]$")
PUBLIC_KEY_RE = re.compile(
    r"^(?:ecdsa-sha2-nistp256|sk-ssh-ed25519@openssh\.com|ssh-ed25519|ssh-rsa) "
    r"[A-Za-z0-9+/]+={0,3}(?: [^\r\n]+)?$"
)
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def require_mapping(value: Any, label: str, findings: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        findings.append(f"{label} must be a mapping")
        return {}
    return value


def require_list(value: Any, label: str, findings: list[str]) -> list[Any]:
    if not isinstance(value, list):
        findings.append(f"{label} must be a list")
        return []
    return value


def positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def parse_address(value: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def is_allowed_binding(value: Any) -> bool:
    address = parse_address(value)
    if address is None or address.is_unspecified:
        return False
    return address.is_loopback or any(address in network for network in PRIVATE_NETWORKS)


def validate_facts(document: dict[str, Any], findings: list[str]) -> None:
    facts = require_mapping(document.get("facts"), "facts", findings)
    if facts.get("distribution") != "Ubuntu":
        findings.append("host operating system must be Ubuntu")
    if facts.get("distribution_version") != "24.04":
        findings.append("host operating system version must be exactly 24.04")
    if facts.get("architecture") not in SUPPORTED_ARCHITECTURES:
        findings.append("host architecture must be x86_64 or aarch64")

    limits = require_mapping(document.get("resource_minimums"), "resource_minimums", findings)
    for name in ("memory_mb", "disk_total_mb", "disk_free_mb"):
        if not positive_integer(limits.get(name)):
            findings.append(f"resource_minimums.{name} must be a positive integer")
    comparisons = (
        ("memory_mb", "memory_mb", "host RAM is below the declared minimum"),
        ("disk_total_mb", "disk_total_mb", "host root disk is below the declared minimum"),
        ("disk_free_mb", "disk_free_mb", "host free root disk is below the declared minimum"),
    )
    for fact_name, limit_name, message in comparisons:
        actual = facts.get(fact_name)
        minimum = limits.get(limit_name)
        if positive_integer(actual) and positive_integer(minimum) and actual < minimum:
            findings.append(message)


def validate_access(document: dict[str, Any], findings: list[str]) -> None:
    environment = document.get("target_environment")
    if environment not in {"fixture", "production"}:
        findings.append("target_environment must be fixture or production")

    admin = require_mapping(document.get("admin"), "admin", findings)
    username = admin.get("user")
    if not isinstance(username, str) or ADMIN_USER_RE.fullmatch(username) is None:
        findings.append("admin.user must be a valid named Unix account")
    if username in {"root", "ubuntu"}:
        findings.append("admin.user must not reuse a bootstrap or root account")
    if not positive_integer(admin.get("uid")) or admin.get("uid", 0) < 1000:
        findings.append("admin.uid must be an explicit unprivileged UID of at least 1000")
    keys = require_list(admin.get("authorized_keys"), "admin.authorized_keys", findings)
    if not keys:
        findings.append("admin.authorized_keys must contain at least one public key")
    for key in keys:
        if not isinstance(key, str) or PUBLIC_KEY_RE.fullmatch(key) is None:
            findings.append("admin.authorized_keys contains an unsupported public-key format")

    break_glass = require_mapping(document.get("break_glass"), "break_glass", findings)
    allowed_methods = {"provider-console", "vm-console"}
    if environment == "fixture":
        allowed_methods.add("container-console")
    if break_glass.get("method") not in allowed_methods:
        findings.append("break_glass.method is not permitted for this target environment")
    for field in ("owner", "recovery_identity", "verification"):
        if not isinstance(break_glass.get(field), str) or not break_glass[field].strip():
            findings.append(f"break_glass.{field} must be a non-empty string")

    ssh = require_mapping(document.get("ssh"), "ssh", findings)
    allowlist = require_list(ssh.get("allow_cidrs"), "ssh.allow_cidrs", findings)
    if not allowlist:
        findings.append("ssh.allow_cidrs must contain at least one explicit network")
    for network in allowlist:
        try:
            parsed = ipaddress.ip_network(str(network), strict=True)
        except ValueError:
            findings.append(f"ssh.allow_cidrs contains an invalid network: {network}")
            continue
        if parsed.prefixlen == 0:
            findings.append("ssh.allow_cidrs must not expose SSH to the whole internet")
    if ssh.get("password_authentication") is not False:
        findings.append("SSH password authentication must be disabled")
    if ssh.get("root_login") != "no":
        findings.append("SSH root login must be disabled after the safety probe")
    if ssh.get("second_connection_required") is not True:
        findings.append("a second authenticated SSH connection must be required")


def validate_network_and_docker(document: dict[str, Any], findings: list[str]) -> None:
    bindings = require_list(document.get("application_bindings"), "application_bindings", findings)
    for index, binding_value in enumerate(bindings):
        binding = require_mapping(binding_value, f"application_bindings[{index}]", findings)
        if not is_allowed_binding(binding.get("address")):
            findings.append(f"application_bindings[{index}] exposes a public or unspecified address")
        if not isinstance(binding.get("port"), int) or not 1 <= binding["port"] <= 65535:
            findings.append(f"application_bindings[{index}].port must be between 1 and 65535")
        if binding.get("protocol") not in {"tcp", "udp"}:
            findings.append(f"application_bindings[{index}].protocol must be tcp or udp")

    docker = require_mapping(document.get("docker"), "docker", findings)
    if docker.get("daemon_hosts") != ["unix:///var/run/docker.sock"]:
        findings.append("Docker daemon must expose only its local Unix socket")
    logging = require_mapping(docker.get("logging"), "docker.logging", findings)
    if logging.get("driver") != "json-file":
        findings.append("Docker logging driver must be json-file")
    max_size = logging.get("max_size")
    if not isinstance(max_size, str) or LOG_SIZE_RE.fullmatch(max_size) is None:
        findings.append("Docker log max_size must be a finite size such as 10m")
    max_files = logging.get("max_files")
    if not positive_integer(max_files) or max_files > 10:
        findings.append("Docker log max_files must be between 1 and 10")
    if docker.get("live_restore") is not True:
        findings.append("Docker live-restore must remain enabled")
    packages = require_mapping(docker.get("packages"), "docker.packages", findings)
    required_packages = {
        "containerd.io",
        "docker-buildx-plugin",
        "docker-ce",
        "docker-ce-cli",
        "docker-compose-plugin",
    }
    if set(packages) != required_packages:
        findings.append("Docker package manifest must declare the complete required package set")
    for package, version in packages.items():
        if not isinstance(version, str) or not version or "latest" in version.lower():
            findings.append(f"Docker package {package} must have an exact non-floating version")
    signing_checksum = docker.get("apt_signing_checksum")
    if not isinstance(signing_checksum, str) or re.fullmatch(r"[0-9a-f]{64}", signing_checksum) is None:
        findings.append("Docker repository key must have a lowercase SHA-256 pin")


def validate_directories(document: dict[str, Any], findings: list[str]) -> None:
    directories = require_list(document.get("managed_directories"), "managed_directories", findings)
    catalogued_paths: set[str] = set()
    catalogued_entries: dict[str, dict[str, Any]] = {}
    for index, item_value in enumerate(directories):
        label = f"managed_directories[{index}]"
        item = require_mapping(item_value, label, findings)
        path_text = item.get("path")
        if not isinstance(path_text, str):
            findings.append(f"{label}.path must be absolute")
            continue
        path = PurePosixPath(path_text)
        if not path.is_absolute() or ".." in path.parts or path == PurePosixPath("/"):
            findings.append(f"{label}.path must be a specific absolute path")
        if path_text in catalogued_paths:
            findings.append(f"managed directory is declared more than once: {path_text}")
        catalogued_paths.add(path_text)
        catalogued_entries[path_text] = item
        if not isinstance(item.get("owner"), str) or not item["owner"]:
            findings.append(f"{label}.owner must be explicit")
        if not isinstance(item.get("group"), str) or not item["group"]:
            findings.append(f"{label}.group must be explicit")
        if not isinstance(item.get("mode"), str) or re.fullmatch(r"0[0-7]{3}", item["mode"]) is None:
            findings.append(f"{label}.mode must be a four-digit octal string")
        if item.get("classification") not in SUPPORTED_CLASSIFICATIONS:
            findings.append(f"{label}.classification is unsupported")
        if item.get("data_classification") not in SUPPORTED_DATA_CLASSES:
            findings.append(f"{label}.data_classification is unsupported")
        if not positive_integer(item.get("size_limit_mb")):
            findings.append(f"{label}.size_limit_mb must be bounded")
        retention = require_mapping(item.get("retention"), f"{label}.retention", findings)
        if not positive_integer(retention.get("max_age_days")):
            findings.append(f"{label}.retention.max_age_days must be bounded")
        if not isinstance(retention.get("owner"), str) or not retention["owner"]:
            findings.append(f"{label}.retention.owner must be explicit")
        events = require_list(retention.get("purge_events"), f"{label}.retention.purge_events", findings)
        if not events or not all(isinstance(event, str) and event for event in events):
            findings.append(f"{label}.retention.purge_events must be explicit")
        backup = require_mapping(item.get("backup"), f"{label}.backup", findings)
        if not isinstance(backup.get("required"), bool):
            findings.append(f"{label}.backup.required must be boolean")
        if not isinstance(backup.get("owner"), str) or not backup["owner"]:
            findings.append(f"{label}.backup.owner must be explicit")

    admin = require_mapping(document.get("admin"), "admin", findings)
    username = admin.get("user")
    required_entries = {
        "/etc/dholbeat": {"owner": "root", "group": "root", "mode": "0755"},
        "/var/log/dholbeat": {"owner": "root", "group": "adm", "mode": "0750"},
        "/var/lib/docker": {"owner": "root", "group": "root", "mode": "0710"},
    }
    if isinstance(username, str) and ADMIN_USER_RE.fullmatch(username) is not None:
        required_entries[f"/home/{username}"] = {
            "owner": username,
            "group": username,
            "mode": "0750",
        }
        required_entries[f"/home/{username}/.ssh"] = {
            "owner": username,
            "group": username,
            "mode": "0700",
        }
    for path, expected_fields in required_entries.items():
        entry = catalogued_entries.get(path)
        if entry is None:
            findings.append(f"required baseline directory is absent from the catalog: {path}")
            continue
        for field, expected in expected_fields.items():
            if entry.get(field) != expected:
                findings.append(f"required baseline directory {path} must set {field}={expected}")

    writable_paths = require_list(document.get("role_writable_paths"), "role_writable_paths", findings)
    if len(writable_paths) != len(set(writable_paths)):
        findings.append("role_writable_paths must not contain duplicates")
    undeclared = sorted(set(writable_paths) - catalogued_paths)
    if undeclared:
        findings.append(f"role writable paths are absent from the directory catalog: {undeclared}")
    unused = sorted(catalogued_paths - set(writable_paths))
    if unused:
        findings.append(f"directory catalog contains paths not owned by the baseline roles: {unused}")


def validate_contract(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if document.get("schema_version") != 1:
        findings.append("schema_version must be 1")
    validate_facts(document, findings)
    validate_access(document, findings)
    validate_network_and_docker(document, findings)
    validate_directories(document, findings)
    if document.get("host_timezone") != "UTC":
        findings.append("host_timezone must be UTC")
    return sorted(set(findings))


def load_document(path: str) -> dict[str, Any]:
    if path == "-":
        value = json.load(sys.stdin)
    else:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("contract input must be a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON input path or - for stdin")
    args = parser.parse_args()
    try:
        document = load_document(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"baseline contract failure: invalid input: {error}") from error
    findings = validate_contract(document)
    if findings:
        for finding in findings:
            print(f"baseline contract failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print("baseline contract passed")


if __name__ == "__main__":
    main()
