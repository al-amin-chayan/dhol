#!/usr/bin/env python3
"""Validate SOPS policy, ciphertext structure, catalog scope, and decrypted shape."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml


SOPS_PATH_REGEX = (
    r"^infra/secrets/(?:[a-z0-9][a-z0-9-]*/)*"
    r"[a-z0-9][a-z0-9-]*\.sops\.yml$"
)
AGE_RECIPIENT_RE = re.compile(r"^age1[023456789acdefghjklmnpqrstuvwxyz]{58}$")
ENCRYPTED_VALUE_RE = re.compile(r"^ENC\[AES256_GCM,")
ALLOWED_SECRET_METADATA = {"README.md", "catalog.yml"}
SKIPPED_DIRECTORIES = {".artifacts", ".controller-cache", ".git", ".worktrees"}


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


def policy_recipients(policy: dict[str, Any]) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    rules = policy.get("creation_rules")
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        return [], [".sops.yaml: exactly one creation rule is required"]
    rule = rules[0]
    if rule.get("path_regex") != SOPS_PATH_REGEX:
        findings.append(".sops.yaml: creation rule path_regex does not match the exact nested secret path")
    unknown_fields = set(rule) - {"path_regex", "key_groups"}
    if unknown_fields:
        findings.append(f".sops.yaml: creation rule has unsupported fields {sorted(unknown_fields)}")
    key_groups = rule.get("key_groups")
    if not isinstance(key_groups, list) or len(key_groups) != 1 or not isinstance(key_groups[0], dict):
        return [], findings + [".sops.yaml: exactly one age key group is required"]
    if set(key_groups[0]) != {"age"}:
        findings.append(".sops.yaml: key group may contain only age recipients")
    recipients = key_groups[0].get("age")
    if not isinstance(recipients, list) or len(recipients) != 2:
        return [], findings + [".sops.yaml: founder and break-glass age recipients are required"]
    if not all(isinstance(recipient, str) and AGE_RECIPIENT_RE.fullmatch(recipient) for recipient in recipients):
        findings.append(".sops.yaml: every recipient must be a valid public age recipient")
    if len(set(recipients)) != len(recipients):
        findings.append(".sops.yaml: founder and break-glass recipients must be distinct")
    return list(recipients), findings


def load_policy(root: Path) -> tuple[list[str], list[str]]:
    path = root / ".sops.yaml"
    try:
        policy = load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return [], [f".sops.yaml: cannot load policy: {error}"]
    return policy_recipients(policy)


def repository_sops_files(root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    findings: list[str] = []
    secret_root = root / "infra/secrets"
    for directory, names, filenames in os.walk(root):
        names[:] = sorted(name for name in names if name not in SKIPPED_DIRECTORIES)
        base = Path(directory)
        for filename in sorted(filenames):
            path = base / filename
            relative = path.relative_to(root).as_posix()
            if filename.endswith(".sops.yml"):
                if not relative.startswith("infra/secrets/"):
                    findings.append(f"{relative}: SOPS ciphertext is outside infra/secrets")
                else:
                    files.append(path)
            elif secret_root in path.parents and filename not in ALLOWED_SECRET_METADATA:
                findings.append(f"{relative}: only catalog/docs or *.sops.yml may be tracked")
    return sorted(files), findings


def encrypted_leaf_findings(value: Any, label: str, path: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(encrypted_leaf_findings(child, label, (*path, str(key))))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(encrypted_leaf_findings(child, label, (*path, str(index))))
    elif not isinstance(value, str) or ENCRYPTED_VALUE_RE.match(value) is None:
        location = ".".join(path) or "$"
        findings.append(f"{label}: plaintext value is forbidden at {location}")
    return findings


def ciphertext_recipients(document: dict[str, Any], label: str) -> tuple[list[str], list[str]]:
    sops = document.get("sops")
    if not isinstance(sops, dict):
        return [], [f"{label}: SOPS metadata is missing"]
    age_entries = sops.get("age")
    recipients: list[str] = []
    if not isinstance(age_entries, list):
        return [], [f"{label}: SOPS age metadata is missing"]
    for entry in age_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("recipient"), str):
            return [], [f"{label}: invalid SOPS age recipient metadata"]
        recipients.append(entry["recipient"])
    mac = sops.get("mac")
    findings: list[str] = []
    if not isinstance(mac, str) or ENCRYPTED_VALUE_RE.match(mac) is None:
        findings.append(f"{label}: encrypted SOPS MAC is missing")
    return recipients, findings


def ciphertext_findings(
    root: Path,
    path: Path,
    required_recipients: set[str],
    expected_value_keys: set[str] | None = None,
) -> list[str]:
    label = path.relative_to(root).as_posix()
    findings: list[str] = []
    if re.fullmatch(SOPS_PATH_REGEX, label) is None:
        findings.append(f"{label}: path does not match the SOPS creation rule")
    try:
        document = load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return findings + [f"{label}: cannot load ciphertext YAML: {error}"]
    recipients, metadata_findings = ciphertext_recipients(document, label)
    findings.extend(metadata_findings)
    if set(recipients) != required_recipients:
        findings.append(f"{label}: ciphertext recipients do not exactly match policy")
    encrypted_document = {key: value for key, value in document.items() if key != "sops"}
    findings.extend(encrypted_leaf_findings(encrypted_document, label))
    values = document.get("values")
    if not isinstance(values, dict):
        findings.append(f"{label}: encrypted values mapping is missing")
    elif expected_value_keys is not None:
        actual_keys = set(values)
        if actual_keys != expected_value_keys:
            findings.append(
                f"{label}: encrypted value keys differ from catalog; "
                f"missing={sorted(expected_value_keys - actual_keys)} "
                f"unknown={sorted(actual_keys - expected_value_keys)}"
            )
    return findings


def _catalog_principals(inventory: dict[str, Any], all_vars: dict[str, Any]) -> tuple[set[str], set[str]]:
    hosts = {host["id"] for host in inventory.get("hosts", []) if isinstance(host, dict) and "id" in host}
    services = {
        service_id
        for host in inventory.get("hosts", [])
        if isinstance(host, dict)
        for service_id in host.get("service_ids", [])
    }
    controller = all_vars.get("infra_controller_principal_id")
    principals = hosts | services
    if isinstance(controller, str):
        principals.add(controller)
    return principals, services


def catalog_findings(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    label = "infra/secrets/catalog.yml"
    try:
        catalog = load_yaml(root / label)
        inventory = load_yaml(root / "infra/inventories/production/hosts.yml")
        all_vars = load_yaml(root / "infra/inventories/production/group_vars/all.yml")
    except (OSError, ValueError, yaml.YAMLError) as error:
        return None, [f"{label}: cannot load catalog dependencies: {error}"]
    findings = schema_findings(catalog, root / "infra/schemas/secret-catalog.schema.json", label)
    if findings:
        return catalog, findings
    principals, services = _catalog_principals(inventory, all_vars)
    hosts = {host["id"] for host in inventory["hosts"]}
    seen_ids: set[str] = set()
    seen_values: dict[tuple[str, str], str] = {}
    seen_targets: dict[tuple[str, str, str], str] = {}
    for secret in catalog["secrets"]:
        secret_id = secret["id"]
        if secret_id in seen_ids:
            findings.append(f"{label}: duplicate secret ID {secret_id}")
        seen_ids.add(secret_id)
        if secret["value_key"] != secret_id:
            findings.append(f"{secret_id}: value_key must equal the secret ID")
        value_identity = (secret["sops_file"], secret["value_key"])
        prior_value = seen_values.get(value_identity)
        if prior_value is not None:
            findings.append(f"{secret_id}: reuses encrypted value owned by {prior_value}")
        seen_values[value_identity] = secret_id
        for principal_id in secret["allowed_principal_ids"]:
            if principal_id not in principals:
                findings.append(f"{secret_id}: unknown allowed principal {principal_id}")
        for service_id in secret["allowed_service_ids"]:
            if service_id not in services:
                findings.append(f"{secret_id}: unknown allowed service {service_id}")
            if service_id not in secret["allowed_principal_ids"]:
                findings.append(f"{secret_id}: allowed service is absent from allowed principals")
        target = secret["target"]
        if target["kind"] == "host-file":
            if target["host_id"] not in hosts:
                findings.append(f"{secret_id}: target names unknown host {target['host_id']}")
            target_identity = (target["host_id"], target["path"], target["variable"])
            prior_target = seen_targets.get(target_identity)
            if prior_target is not None:
                findings.append(f"{secret_id}: reuses target variable owned by {prior_target}")
            seen_targets[target_identity] = secret_id
        procedure_path = secret["rotation"]["procedure"].split("#", 1)[0]
        if not (root / procedure_path).is_file():
            findings.append(f"{secret_id}: rotation procedure does not exist: {procedure_path}")
    return catalog, sorted(set(findings))


def structural_findings(root: Path) -> list[str]:
    required_recipients, findings = load_policy(root)
    catalog, catalog_errors = catalog_findings(root)
    findings.extend(catalog_errors)
    sops_files, path_findings = repository_sops_files(root)
    findings.extend(path_findings)
    expected_by_file: dict[str, set[str]] = {}
    if catalog is not None and not catalog_errors:
        for secret in catalog["secrets"]:
            expected_by_file.setdefault(secret["sops_file"], set()).add(secret["value_key"])
    for path in sops_files:
        relative = path.relative_to(root).as_posix()
        expected = expected_by_file.get(relative, set())
        if not expected:
            findings.append(f"{relative}: ciphertext file is absent from the secret catalog")
        findings.extend(ciphertext_findings(root, path, set(required_recipients), expected))
    return sorted(set(findings))


def decrypt_in_memory_findings(root: Path, path: Path, environment: dict[str, str]) -> list[str]:
    label = path.relative_to(root).as_posix()
    try:
        completed = subprocess.run(
            ["sops", "--decrypt", "--output-type", "json", str(path)],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return [f"{label}: SOPS executable is unavailable in the pinned controller"]
    if completed.returncode != 0:
        return [f"{label}: in-memory SOPS decrypt/MAC verification failed"]
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [f"{label}: decrypted content is not valid JSON/YAML"]
    if not isinstance(document, dict):
        return [f"{label}: decrypted content must be a mapping"]
    findings = schema_findings(document, root / "infra/schemas/secret-values.schema.json", label)
    catalog, catalog_errors = catalog_findings(root)
    findings.extend(catalog_errors)
    if catalog is not None and not catalog_errors:
        expected = {
            secret["value_key"]
            for secret in catalog["secrets"]
            if secret["sops_file"] == label
        }
        actual = set(document.get("values", {})) if isinstance(document.get("values"), dict) else set()
        if actual != expected:
            findings.append(f"{label}: decrypted value keys do not exactly match catalog")
    return sorted(set(findings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--decrypt", type=Path, action="append", default=[])
    args = parser.parse_args()
    root = args.root.resolve()
    findings = structural_findings(root)
    for requested in args.decrypt:
        path = requested if requested.is_absolute() else root / requested
        findings.extend(decrypt_in_memory_findings(root, path, dict(os.environ)))
    findings = sorted(set(findings))
    if findings:
        for finding in findings:
            print(f"SOPS policy failure: {finding}")
        raise SystemExit(1)
    print("SOPS policy and catalog passed")


if __name__ == "__main__":
    main()
