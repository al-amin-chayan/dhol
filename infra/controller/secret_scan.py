#!/usr/bin/env python3
"""Create a bounded temporary tree for secret scanning the current lane only."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from repo_policy import check_symlink_boundaries, repository_files


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


def prepare_scan_tree(root: Path, destination: Path) -> tuple[int, int]:
    files = repository_files(root)
    boundary_findings = check_symlink_boundaries(root, files)
    if boundary_findings:
        raise ValueError(f"secret-scan input violates repository boundary: {boundary_findings[0]}")

    total = 0
    count = 0
    for source in files:
        size = source.stat().st_size
        relative = source.relative_to(root)
        if size > MAX_FILE_BYTES:
            raise ValueError(f"secret-scan input exceeds {MAX_FILE_BYTES} bytes: {relative}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"secret-scan inputs exceed {MAX_TOTAL_BYTES} bytes")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=True)
        count += 1
    return count, total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit(f"secret-scan destination already exists: {destination}")
    if destination == root or root in destination.parents:
        raise SystemExit("secret-scan destination must be outside the repository")

    try:
        count, total = prepare_scan_tree(root, destination)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"prepared {count} files ({total} bytes) for bounded secret scan")


if __name__ == "__main__":
    main()
