#!/usr/bin/env python3
"""Verify the installed toolchain and print architecture-neutral versions."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


LOCK_PATH = Path("/opt/dholbeat/toolchain.lock.yml")
COLLECTIONS_ROOT = Path("/usr/share/ansible/collections/ansible_collections")
TOOL_COMMANDS = {
    "sops": ["sops", "--version"],
    "age": ["age", "--version"],
    "tofu": ["tofu", "version"],
    "shellcheck": ["shellcheck", "--version"],
    "gitleaks": ["gitleaks", "version"],
    "docker-compose": ["docker-compose", "version", "--short"],
}


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"controller version error: {message}")


def load_lock() -> dict:
    with LOCK_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=True, timeout=20)
    return f"{result.stdout}\n{result.stderr}".strip()


def verify_python(lock: dict) -> None:
    actual_python = ".".join(str(part) for part in sys.version_info[:3])
    if actual_python != str(lock["python"]["version"]):
        fail(f"python expected {lock['python']['version']}, got {actual_python}")
    for package, expected in lock["python"]["direct_packages"].items():
        actual = metadata.version(package)
        if actual != str(expected):
            fail(f"{package} expected {expected}, got {actual}")


def verify_tools(lock: dict) -> None:
    for name, spec in lock["tools"].items():
        output = command_output(TOOL_COMMANDS[name])
        expected = str(spec["version"])
        if re.search(rf"(?<![0-9])v?{re.escape(expected)}(?![0-9])", output) is None:
            fail(f"{name} expected {expected}; command returned {output!r}")


def verify_collections(lock: dict) -> None:
    for name, spec in lock["ansible_collections"].items():
        namespace, collection = name.split(".", 1)
        manifest_path = COLLECTIONS_ROOT / namespace / collection / "MANIFEST.json"
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        actual = manifest["collection_info"]["version"]
        if actual != str(spec["version"]):
            fail(f"{name} expected {spec['version']}, got {actual}")


def print_versions(lock: dict) -> None:
    print("controller-platforms=" + ",".join(lock["controller"]["supported_platforms"]))
    print(f"python={lock['python']['version']}")
    for package, version in lock["python"]["direct_packages"].items():
        print(f"python-package.{package}={version}")
    for name, spec in lock["ansible_collections"].items():
        print(f"ansible-collection.{name}={spec['version']}")
    for name, spec in lock["tools"].items():
        print(f"tool.{name}={spec['version']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    lock = load_lock()
    verify_python(lock)
    verify_tools(lock)
    verify_collections(lock)
    if not args.verify_only:
        print_versions(lock)


if __name__ == "__main__":
    main()

