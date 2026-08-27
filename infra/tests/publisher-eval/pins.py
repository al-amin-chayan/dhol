#!/usr/bin/env python3
"""Read one field out of the pinned DG-01 candidate list.

run.sh must never hardcode an image reference: the pins in candidates.yml are
the reproducibility record, so the harness reads them rather than restating
them.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def load(root: Path) -> dict:
    document = yaml.safe_load((root / "candidates.yml").read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise SystemExit("candidates.yml schema_version must be 1")
    return document


def candidate(document: dict, candidate_id: str) -> dict:
    for entry in document["candidates"]:
        if entry["id"] == candidate_id:
            return entry
    raise SystemExit(f"unknown candidate: {candidate_id}")


def variant(entry: dict, variant_id: str) -> dict:
    for item in entry.get("variants", []):
        if item["id"] == variant_id:
            return item
    raise SystemExit(f"unknown variant for {entry['id']}: {variant_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--variant")
    parser.add_argument("--field", required=True, choices=["image", "compose", "version", "license", "profiles", "evaluable"])
    args = parser.parse_args()

    entry = candidate(load(args.root), args.candidate)
    if args.field == "profiles":
        if not args.variant:
            parser.error("--variant is required with --field profiles")
        print(" ".join(variant(entry, args.variant).get("profiles", [])))
        return 0
    if args.field == "evaluable":
        print("true" if entry.get("evaluable") else "false")
        return 0
    value = entry.get(args.field)
    if not value:
        raise SystemExit(f"{args.candidate} has no {args.field}")
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
