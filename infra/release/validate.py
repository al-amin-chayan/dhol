#!/usr/bin/env python3
"""Validate reviewed release identity, plan digest, annotated tag, and host receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(git_root: Path, *args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=git_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout.strip()


def validate_release(
    root: Path,
    release: dict[str, Any],
    plan_path: Path,
    git_root: Path,
) -> list[str]:
    findings = schema_findings(
        release,
        root / "infra/schemas/release.schema.json",
        "release",
    )
    if findings:
        return sorted(set(findings))
    if release["review"]["reviewed_commit"] != release["git_commit"]:
        findings.append("release: cross-review does not cover the release commit")
    try:
        actual_plan_digest = sha256_file(plan_path)
    except OSError:
        findings.append("release: approved plan artifact is unavailable")
    else:
        if actual_plan_digest != release["approved_plan_sha256"]:
            findings.append("release: approved plan digest does not match the reviewed plan")

    tag_ref = f"refs/tags/{release['tag']}"
    status, object_type = git_output(git_root, "cat-file", "-t", tag_ref)
    if status != 0 or object_type != "tag":
        findings.append("release: annotated production tag is missing")
    else:
        status, tagged_commit = git_output(git_root, "rev-parse", f"{tag_ref}^{{commit}}")
        if status != 0 or tagged_commit != release["git_commit"]:
            findings.append("release: annotated tag does not identify the release commit")

    status, _ = git_output(
        git_root,
        "merge-base",
        "--is-ancestor",
        release["git_commit"],
        "refs/heads/main",
    )
    if status != 0:
        findings.append("release: commit is not reachable from protected main")
    return sorted(set(findings))


def validate_runtime_receipt(
    root: Path,
    release: dict[str, Any],
    receipt: dict[str, Any],
) -> list[str]:
    findings = schema_findings(
        receipt,
        root / "infra/schemas/runtime-receipt.schema.json",
        "/etc/dholbeat-release",
    )
    if findings:
        return sorted(set(findings))
    matching_fields = (
        "release_id",
        "git_commit",
        "tag",
        "toolchain_lock_sha256",
        "approved_plan_sha256",
        "required_backup_snapshot_id",
        "schema_versions",
        "images",
    )
    for field in matching_fields:
        if receipt[field] != release[field]:
            findings.append(f"/etc/dholbeat-release: {field} differs from reviewed release")
    if receipt["applied_plan_sha256"] != release["approved_plan_sha256"]:
        findings.append("/etc/dholbeat-release: applied plan digest differs from approval")
    if receipt["host_role"] not in release["target_roles"]:
        findings.append("/etc/dholbeat-release: host role is absent from release targets")
    return sorted(set(findings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--git-root", type=Path)
    parser.add_argument("--runtime-receipt", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    release = load_yaml(args.release)
    findings = validate_release(root, release, args.plan, (args.git_root or root).resolve())
    if args.runtime_receipt is not None:
        findings.extend(validate_runtime_receipt(root, release, load_yaml(args.runtime_receipt)))
    findings = sorted(set(findings))
    if findings:
        for finding in findings:
            print(f"release identity failure: {finding}")
        raise SystemExit(1)
    print("release identity passed")


if __name__ == "__main__":
    main()
