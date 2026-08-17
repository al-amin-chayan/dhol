#!/usr/bin/env python3
"""Produce a redacted full-value rotation plan for a leaked age recipient."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .validate import (
        catalog_findings,
        ciphertext_recipients,
        load_yaml,
        repository_sops_files,
    )
except ImportError:  # pragma: no cover - direct script execution
    from validate import (
        catalog_findings,
        ciphertext_recipients,
        load_yaml,
        repository_sops_files,
    )


def build_rotation_plan(root: Path, leaked_recipient: str) -> tuple[dict, list[str]]:
    catalog, findings = catalog_findings(root)
    sops_files, path_findings = repository_sops_files(root)
    findings.extend(path_findings)
    if catalog is None or findings:
        return {}, sorted(set(findings))
    affected_files: list[str] = []
    metadata_findings: list[str] = []
    for path in sops_files:
        relative = path.relative_to(root).as_posix()
        try:
            document = load_yaml(path)
        except Exception:
            metadata_findings.append(f"{relative}: cannot inspect SOPS recipient metadata")
            continue
        recipients, recipient_findings = ciphertext_recipients(document, relative)
        metadata_findings.extend(recipient_findings)
        if leaked_recipient in recipients:
            affected_files.append(relative)
    if metadata_findings:
        return {}, sorted(set(metadata_findings))
    affected_file_set = set(affected_files)
    secret_ids = sorted(
        secret["id"]
        for secret in catalog["secrets"]
        if secret["sops_file"] in affected_file_set
    )
    plan = {
        "schema_version": 1,
        "mode": "dry-run",
        "scope": "current-working-tree",
        "historical_ciphertext_review_required": True,
        "leaked_recipient": leaked_recipient,
        "replace_recipient": True,
        "reencryption_alone_is_sufficient": False,
        "affected_sops_files": sorted(affected_files),
        "underlying_secret_ids_to_rotate": secret_ids,
        "contains_plaintext": False,
    }
    return plan, []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--leaked-recipient", required=True)
    args = parser.parse_args()
    plan, findings = build_rotation_plan(args.root.resolve(), args.leaked_recipient)
    if findings:
        for finding in findings:
            print(f"rotation planning failure: {finding}")
        raise SystemExit(1)
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
