#!/usr/bin/env python3
"""Fail closed on repository hygiene and supply-chain pinning policy."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
from typing import Iterable

import yaml


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACTION_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EXACT_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9A-Za-z]+)+(?:[-+][0-9A-Za-z.-]+)?$")
IMAGE_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
SKIP_DIRECTORIES = {
    ".artifacts",
    ".controller-cache",
    ".git",
    ".pytest_cache",
    ".terraform",
    ".venv",
    ".worktrees",
    "__pycache__",
    "node_modules",
}
MEDIA_SUFFIXES = {".jpeg", ".jpg", ".mov", ".mp4", ".png", ".webm"}
DATABASE_SUFFIXES = {".db", ".dump", ".sqlite", ".sqlite3"}
STATE_SUFFIXES = {".plan", ".tfplan", ".tfstate"}
EXPECTED_SOURCE_INPUTS = [
    "toolchain.lock.yml",
    "infra/controller/Containerfile",
    "infra/controller/entrypoint.sh",
    "infra/controller/install_tools.py",
    "infra/controller/requirements.in",
    "infra/controller/requirements.txt",
    "infra/controller/requirements.yml",
    "infra/controller/runtime_versions.py",
]
REQUIRED_GITIGNORE_PATTERNS = {
    ".artifacts/",
    ".controller-cache/",
    ".env",
    ".env.*",
    "*.db",
    "*.dump",
    "*.sqlite",
    "*.sqlite3",
    "*.plan",
    "*.tfplan",
    "*.tfstate",
    "*.tfstate.*",
    "**/.terraform/",
    "media/",
    "out/",
}


def repository_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, names, filenames in os.walk(root):
        base = Path(directory)
        retained_directories: list[str] = []
        for name in sorted(names):
            if name in SKIP_DIRECTORIES:
                continue
            candidate = base / name
            if candidate.is_symlink():
                files.append(candidate)
            else:
                retained_directories.append(name)
        names[:] = retained_directories
        for filename in sorted(filenames):
            path = base / filename
            relative = path.relative_to(root)
            if any(part in SKIP_DIRECTORIES for part in relative.parts):
                continue
            files.append(path)
    return files


def check_symlink_boundaries(root: Path, files: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        if not path.is_symlink():
            continue
        rel = relative(path, root)
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            findings.append(f"{rel}: broken symlink is forbidden: {error}")
            continue
        if resolved == root or root not in resolved.parents:
            findings.append(f"{rel}: symlink escapes the repository")
        elif resolved.is_dir():
            findings.append(f"{rel}: symlinked directories are forbidden")
    return findings


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def check_prohibited_paths(root: Path, files: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        rel = relative(path, root)
        name = path.name
        suffix = path.suffix.lower()
        if (name == ".env" or name.startswith(".env.")) and not name.endswith(".example"):
            findings.append(f"{rel}: plaintext .env files are forbidden")
        if suffix in {".key", ".pem"}:
            findings.append(f"{rel}: private key material is forbidden")
        if name.startswith("credentials") and suffix == ".json":
            findings.append(f"{rel}: credential exports are forbidden")
        if suffix in MEDIA_SUFFIXES and not rel.startswith("docs/"):
            findings.append(f"{rel}: generated media is forbidden")
        if suffix in DATABASE_SUFFIXES:
            findings.append(f"{rel}: database or restored dump is forbidden")
        if suffix in STATE_SUFFIXES or ".tfstate." in name:
            findings.append(f"{rel}: OpenTofu state or plan output is forbidden")
        if rel.startswith("infra/secrets/"):
            allowed_metadata = rel in {"infra/secrets/README.md", "infra/secrets/catalog.yml"}
            if not allowed_metadata and not rel.endswith(".sops.yml"):
                findings.append(f"{rel}: only metadata or *.sops.yml ciphertext is allowed under infra/secrets")
    return findings


def walk_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)


def check_container_pins(root: Path, files: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        rel = relative(path, root)
        if path.name in {"Containerfile", "Dockerfile"}:
            text = read_text(path) or ""
            for number, line in enumerate(text.splitlines(), start=1):
                match = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", line, re.IGNORECASE)
                if match and match.group(1) != "scratch" and IMAGE_DIGEST_RE.search(match.group(1)) is None:
                    findings.append(f"{rel}:{number}: base image must be pinned by sha256 digest")
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        if not (rel.startswith("stack/") or rel.startswith("infra/") or rel.startswith(".github/")):
            continue
        text = read_text(path)
        if text is None:
            continue
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        for key, value in walk_values(document):
            if key == "image" and isinstance(value, str) and IMAGE_DIGEST_RE.search(value) is None:
                findings.append(f"{rel}: container image is not pinned by sha256 digest: {value}")
    return findings


def requirement_records(text: str) -> list[str]:
    records: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = f"{current} {stripped}".strip()
        if stripped.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        records.append(current)
        current = ""
    if current:
        records.append(current)
    return records


def check_requirement_hashes(root: Path, files: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        if not (path.name.startswith("requirements") and path.suffix == ".txt"):
            continue
        rel = relative(path, root)
        for record in requirement_records(read_text(path) or ""):
            if record.startswith("-"):
                continue
            package = record.split()[0]
            if "==" not in package:
                findings.append(f"{rel}: dependency is not exactly pinned: {package}")
            if "--hash=sha256:" not in record:
                findings.append(f"{rel}: dependency has no sha256 hash: {package}")
    return findings


def workflow_files(root: Path, files: Iterable[Path]) -> list[Path]:
    return [
        path
        for path in files
        if relative(path, root).startswith(".github/workflows/") and path.suffix in {".yaml", ".yml"}
    ]


def check_action_pins(root: Path, files: Iterable[Path], lock: dict | None = None) -> list[str]:
    findings: list[str] = []
    for path in workflow_files(root, files):
        rel = relative(path, root)
        try:
            document = yaml.safe_load(read_text(path) or "")
        except yaml.YAMLError as error:
            findings.append(f"{rel}: invalid workflow YAML: {error}")
            continue
        for key, value in walk_values(document):
            if key != "uses" or not isinstance(value, str) or value.startswith("./"):
                continue
            if value.startswith("docker://"):
                if IMAGE_DIGEST_RE.search(value) is None:
                    findings.append(f"{rel}: Docker action is not digest-pinned: {value}")
                continue
            action, separator, commit = value.partition("@")
            if not separator or ACTION_COMMIT_RE.fullmatch(commit) is None:
                findings.append(f"{rel}: action must use a full commit SHA: {value}")
                continue
            if lock is not None and action in lock.get("actions", {}):
                expected = str(lock["actions"][action]["commit"])
                if commit != expected:
                    findings.append(f"{rel}: {action} does not match toolchain.lock.yml")
    return findings


def permissions_are_read_only(value: object) -> bool:
    if value == "read-all":
        return True
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(permission, str) and permission in {"read", "none"}
        for permission in value.values()
    )


def check_workflow_permissions(root: Path, files: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in workflow_files(root, files):
        rel = relative(path, root)
        try:
            document = yaml.safe_load(read_text(path) or "")
        except yaml.YAMLError:
            continue
        if not isinstance(document, dict):
            findings.append(f"{rel}: workflow must be a YAML mapping")
            continue
        if "permissions" not in document:
            findings.append(f"{rel}: workflow must declare explicit read-only top-level permissions")
        elif not permissions_are_read_only(document["permissions"]):
            findings.append(f"{rel}: top-level permissions must be read-only")

        jobs = document.get("jobs", {})
        if not isinstance(jobs, dict):
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or "permissions" not in job:
                continue
            if not permissions_are_read_only(job["permissions"]):
                findings.append(f"{rel}: job {job_name} permissions must be read-only")
    return findings


def check_ci_entrypoint(root: Path) -> list[str]:
    path = root / ".github/workflows/validate.yml"
    if not path.is_file():
        return [".github/workflows/validate.yml: canonical read-only CI workflow is missing"]
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        return [f".github/workflows/validate.yml: invalid YAML: {error}"]
    run_commands = [value.strip() for key, value in walk_values(document) if key == "run" and isinstance(value, str)]
    if run_commands != ["scripts/check"]:
        return [".github/workflows/validate.yml: CI run steps must invoke only scripts/check"]
    return []


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError("expected a YAML mapping")
    return value


def check_toolchain_lock(root: Path) -> tuple[list[str], dict | None]:
    path = root / "toolchain.lock.yml"
    if not path.is_file():
        return ["toolchain.lock.yml: lockfile is missing"], None
    try:
        lock = load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return [f"toolchain.lock.yml: cannot load lockfile: {error}"], None

    findings: list[str] = []
    if lock.get("schema_version") != 1:
        findings.append("toolchain.lock.yml: schema_version must be 1")
    controller = lock.get("controller", {})
    for field in ("base_image", "buildkit_image"):
        value = str(controller.get(field, ""))
        if IMAGE_DIGEST_RE.search(value) is None:
            findings.append(f"toolchain.lock.yml: controller.{field} must be digest-pinned")
    if controller.get("supported_platforms") != ["linux/amd64", "linux/arm64"]:
        findings.append("toolchain.lock.yml: supported platforms must be linux/amd64 and linux/arm64")
    if controller.get("source_inputs") != EXPECTED_SOURCE_INPUTS:
        findings.append("toolchain.lock.yml: controller.source_inputs does not match the controller source contract")
    for source_input in EXPECTED_SOURCE_INPUTS:
        if not (root / source_input).is_file():
            findings.append(f"toolchain.lock.yml: missing controller source input: {source_input}")

    python_spec = lock.get("python", {})
    requirement_versions: dict[str, str] = {}
    requirements_path = root / "infra/controller/requirements.txt"
    if requirements_path.is_file():
        for record in requirement_records(requirements_path.read_text(encoding="utf-8")):
            package = record.split()[0]
            if "==" in package:
                name, version = package.split("==", 1)
                requirement_versions[name.lower().replace("_", "-")] = version
    for package, version in python_spec.get("direct_packages", {}).items():
        if EXACT_VERSION_RE.fullmatch(str(version)) is None:
            findings.append(f"toolchain.lock.yml: Python package {package} is not exactly pinned")
        if requirement_versions.get(package.lower().replace("_", "-")) != str(version):
            findings.append(f"infra/controller/requirements.txt: {package} does not match toolchain.lock.yml")

    for name, spec in lock.get("ansible_collections", {}).items():
        if EXACT_VERSION_RE.fullmatch(str(spec.get("version", ""))) is None:
            findings.append(f"toolchain.lock.yml: Ansible collection {name} is not exactly pinned")
        if not str(spec.get("url", "")).startswith("https://"):
            findings.append(f"toolchain.lock.yml: Ansible collection {name} has no HTTPS source")
        if SHA256_RE.fullmatch(str(spec.get("sha256", ""))) is None:
            findings.append(f"toolchain.lock.yml: Ansible collection {name} has no sha256 checksum")

    for name, spec in lock.get("tools", {}).items():
        version = str(spec.get("version", ""))
        if EXACT_VERSION_RE.fullmatch(version) is None:
            findings.append(f"toolchain.lock.yml: tool {name} is not exactly pinned")
        if not spec.get("license"):
            findings.append(f"toolchain.lock.yml: tool {name} has no recorded license")
        artifacts = spec.get("artifacts", {})
        if set(artifacts) != {"amd64", "arm64"}:
            findings.append(f"toolchain.lock.yml: tool {name} must lock amd64 and arm64 artifacts")
        for arch, artifact in artifacts.items():
            url = str(artifact.get("url", ""))
            if not url.startswith("https://") or "latest" in url.lower():
                findings.append(f"toolchain.lock.yml: tool {name}/{arch} has a floating or non-HTTPS URL")
            if SHA256_RE.fullmatch(str(artifact.get("sha256", ""))) is None:
                findings.append(f"toolchain.lock.yml: tool {name}/{arch} has no sha256 checksum")

    for name, spec in lock.get("actions", {}).items():
        if ACTION_COMMIT_RE.fullmatch(str(spec.get("commit", ""))) is None:
            findings.append(f"toolchain.lock.yml: action {name} is not pinned to a full commit")
        if not spec.get("license"):
            findings.append(f"toolchain.lock.yml: action {name} has no recorded license")

    containerfile = root / "infra/controller/Containerfile"
    if containerfile.is_file():
        first_from = next(
            (
                line.split()[1]
                for line in containerfile.read_text(encoding="utf-8").splitlines()
                if line.startswith("FROM ")
            ),
            "",
        )
        if first_from != controller.get("base_image"):
            findings.append("infra/controller/Containerfile: FROM does not match controller.base_image")

    collection_path = root / "infra/controller/requirements.yml"
    if collection_path.is_file():
        try:
            collection_requirements = load_yaml(collection_path).get("collections", [])
            required_versions = {item["name"]: str(item["version"]) for item in collection_requirements}
            locked_versions = {
                name: str(spec["version"]) for name, spec in lock.get("ansible_collections", {}).items()
            }
            if required_versions != locked_versions:
                findings.append("infra/controller/requirements.yml: collection versions do not match toolchain.lock.yml")
        except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as error:
            findings.append(f"infra/controller/requirements.yml: cannot load collection requirements: {error}")
    return findings, lock


def check_gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return [".gitignore: required file is missing"]
    patterns = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(REQUIRED_GITIGNORE_PATTERNS - patterns)
    return [f".gitignore: required pattern is missing: {pattern}" for pattern in missing]


def check_markdown_fences(root: Path, files: Iterable[Path]) -> list[str]:
    """Reject an unbalanced code fence.

    A stray closing fence renders every following section as code, which silently
    hides operational instructions in a runbook.
    """

    findings: list[str] = []
    for path in files:
        rel = relative(path, root)
        if path.suffix.lower() != ".md":
            continue
        text = read_text(path)
        if text is None:
            continue
        fences = [
            number
            for number, line in enumerate(text.splitlines(), start=1)
            if line.lstrip().startswith("```")
        ]
        if len(fences) % 2 != 0:
            findings.append(f"{rel}: unbalanced code fence, last at line {fences[-1]}")
    return findings


def check_executable_entrypoints(root: Path) -> list[str]:
    findings: list[str] = []
    for rel in (
        "scripts/check",
        "scripts/configure-github-rulesets.py",
        "scripts/controller",
        "scripts/eof-marker.sh",
        "scripts/github-app-gh",
        "scripts/github-app-git",
        "scripts/github-app-token.sh",
        "scripts/infra-apply",
        "scripts/infra-plan",
        "scripts/infra-verify",
        "scripts/publisher-check",
        "scripts/wireguard-peer-config",
        "scripts/wireguard-server-key",
        "infra/controller/entrypoint.sh",
        "infra/inventories/host_baseline.py",
        "infra/playbooks/files/verify_public_listeners.py",
    ):
        path = root / rel
        if not path.is_file():
            findings.append(f"{rel}: entry point is missing")
            continue
        mode = path.stat().st_mode
        if mode & stat.S_IXUSR == 0:
            findings.append(f"{rel}: entry point is not executable")
    return findings


def run_policy(root: Path) -> list[str]:
    files = repository_files(root)
    findings: list[str] = []
    findings.extend(check_symlink_boundaries(root, files))
    findings.extend(check_prohibited_paths(root, files))
    findings.extend(check_container_pins(root, files))
    findings.extend(check_requirement_hashes(root, files))
    lock_findings, lock = check_toolchain_lock(root)
    findings.extend(lock_findings)
    findings.extend(check_action_pins(root, files, lock))
    findings.extend(check_workflow_permissions(root, files))
    findings.extend(check_ci_entrypoint(root))
    findings.extend(check_gitignore(root))
    findings.extend(check_executable_entrypoints(root))
    findings.extend(check_markdown_fences(root, files))
    return sorted(set(findings))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    findings = run_policy(root)
    if findings:
        for finding in findings:
            print(f"policy failure: {finding}")
        raise SystemExit(1)
    print("repository policy passed")


if __name__ == "__main__":
    main()
