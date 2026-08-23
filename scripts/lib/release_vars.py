#!/usr/bin/env python3
"""Turn a reviewed release document into the extra-vars the receipt role needs.

The output is generated for one plan or apply run and is never a repository
input. It carries release identity and digests only: no address override, no
decrypted value, and no plan body.
"""

from __future__ import annotations

import sys

import yaml


REQUIRED_FIELDS = (
    "release_id",
    "git_commit",
    "tag",
    "target_roles",
    "toolchain_lock_sha256",
    "approved_plan_sha256",
    "required_backup_snapshot_id",
    "schema_versions",
    "images",
    "created_at",
)


def main() -> None:
    release = yaml.safe_load(sys.stdin.read())
    if not isinstance(release, dict):
        raise SystemExit("release document failure: expected a YAML mapping")
    missing = [field for field in REQUIRED_FIELDS if field not in release]
    if missing:
        raise SystemExit(f"release document failure: missing required fields: {sorted(missing)}")

    document = {
        "dholbeat_release": release,
        "dholbeat_applied_plan_sha256": release["approved_plan_sha256"],
        "dholbeat_applied_at": release["created_at"],
    }
    sys.stdout.write("# Generated for one run; never a repository input.\n")
    yaml.safe_dump(document, sys.stdout, default_flow_style=False, sort_keys=True)


if __name__ == "__main__":
    main()
