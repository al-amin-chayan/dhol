#!/usr/bin/env python3
"""Run the committed release-identity gate with host-supplied Git facts.

``infra/release/validate.py`` owns the release contract. The pinned controller
deliberately carries no Git binary, so this wrapper takes the Git facts the
operator's checkout already proved — annotated tag object type, the commit that
tag resolves to, and reachability from protected ``main`` — and feeds them to the
same validator. Nothing here relaxes a rule: a missing or mismatched fact fails
exactly as an absent tag would.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from typing import Any

import yaml


def load_validator(root: Path):
    path = root / "infra/release/validate.py"
    spec = importlib.util.spec_from_file_location("dholbeat_release_validate", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def build_git_runner(tag_object_type: str, tag_commit: str, reachable_from_main: bool):
    def git_runner(_root: Path, *args: str) -> tuple[int, str]:
        if args[:2] == ("cat-file", "-t"):
            if not tag_object_type:
                return 1, ""
            return 0, tag_object_type
        if args[0] == "rev-parse":
            if not tag_commit:
                return 1, ""
            return 0, tag_commit
        if args[:2] == ("merge-base", "--is-ancestor"):
            return (0, "") if reachable_from_main else (1, "")
        return 1, ""

    return git_runner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tag-object-type", default="")
    parser.add_argument("--tag-commit", default="")
    parser.add_argument("--reachable-from-main", type=lambda value: value == "true", required=True)
    parser.add_argument("--runtime-receipt", type=Path)
    arguments = parser.parse_args()

    root = arguments.root.resolve()
    validator = load_validator(root)
    release = load_yaml(arguments.release)
    if not isinstance(release, dict):
        raise SystemExit("release identity failure: release document is not a mapping")

    findings = validator.validate_release(
        root,
        release,
        arguments.plan,
        root,
        git_runner=build_git_runner(
            arguments.tag_object_type,
            arguments.tag_commit,
            arguments.reachable_from_main,
        ),
    )
    if arguments.runtime_receipt is not None:
        receipt = load_yaml(arguments.runtime_receipt)
        if not isinstance(receipt, dict):
            findings.append("/etc/dholbeat-release: receipt is not a mapping")
        else:
            findings.extend(validator.validate_runtime_receipt(root, release, receipt))

    findings = sorted(set(findings))
    if findings:
        for finding in findings:
            print(f"release identity failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print("release identity passed")


if __name__ == "__main__":
    main()
