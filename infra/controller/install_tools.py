#!/usr/bin/env python3
"""Install checksum-locked controller binaries and Ansible collections."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

import yaml


MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
ALLOWED_INSTALL_ROOT = Path("/usr/local/bin")
COLLECTIONS_ROOT = Path("/usr/share/ansible/collections")


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"controller install error: {message}")


def load_lock(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        fail("toolchain lock must use schema_version 1")
    return data


def download(url: str, expected_sha256: str, destination: Path) -> None:
    if not url.startswith("https://"):
        fail(f"artifact URL is not HTTPS: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "dholbeat-controller/1"})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) > MAX_ARTIFACT_BYTES:
            fail(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {url}")
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                fail(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {url}")
            digest.update(chunk)
            output.write(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        fail(f"checksum mismatch for {url}: expected {expected_sha256}, got {actual_sha256}")


def checked_install_path(value: str) -> Path:
    target = Path(value)
    try:
        target.relative_to(ALLOWED_INSTALL_ROOT)
    except ValueError:
        fail(f"binary install path escapes {ALLOWED_INSTALL_ROOT}: {target}")
    if target.parent != ALLOWED_INSTALL_ROOT:
        fail(f"binary install path must be directly under {ALLOWED_INSTALL_ROOT}: {target}")
    return target


def checked_member(value: str) -> str:
    member = PurePosixPath(value)
    if member.is_absolute() or ".." in member.parts:
        fail(f"unsafe archive member: {value}")
    return str(member)


def write_executable(source, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
    target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


def install_binary_artifact(spec: dict, artifact_path: Path) -> None:
    archive_format = spec["format"]
    installs = spec["install"]
    if archive_format == "binary":
        if len(installs) != 1 or installs[0].get("archive_path") is not None:
            fail("raw binary artifacts must declare one null archive_path")
        with artifact_path.open("rb") as source:
            write_executable(source, checked_install_path(installs[0]["install_path"]))
        return

    if archive_format in {"tar.gz", "tar.xz"}:
        mode = "r:gz" if archive_format == "tar.gz" else "r:xz"
        with tarfile.open(artifact_path, mode) as archive:
            for install in installs:
                member_name = checked_member(install["archive_path"])
                member = archive.getmember(member_name)
                if not member.isfile():
                    fail(f"archive member is not a regular file: {member_name}")
                source = archive.extractfile(member)
                if source is None:
                    fail(f"could not read archive member: {member_name}")
                with source:
                    write_executable(source, checked_install_path(install["install_path"]))
        return

    if archive_format == "zip":
        with zipfile.ZipFile(artifact_path) as archive:
            for install in installs:
                member_name = checked_member(install["archive_path"])
                with archive.open(member_name) as source:
                    write_executable(source, checked_install_path(install["install_path"]))
        return

    fail(f"unsupported artifact format: {archive_format}")


def install_tools(lock: dict, arch: str, temporary: Path) -> None:
    if arch not in {"amd64", "arm64"}:
        fail(f"unsupported controller architecture: {arch}")
    for name, spec in lock["tools"].items():
        artifact = spec["artifacts"].get(arch)
        if artifact is None:
            fail(f"{name} has no artifact for {arch}")
        artifact_path = temporary / f"tool-{name}"
        download(artifact["url"], artifact["sha256"], artifact_path)
        install_binary_artifact(spec, artifact_path)


def install_collections(lock: dict, temporary: Path) -> None:
    COLLECTIONS_ROOT.mkdir(parents=True, exist_ok=True)
    for name, spec in lock["ansible_collections"].items():
        artifact_path = temporary / f"collection-{name.replace('.', '-')}.tar.gz"
        download(spec["url"], spec["sha256"], artifact_path)
        subprocess.run(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "--force",
                "--no-deps",
                "--collections-path",
                str(COLLECTIONS_ROOT),
                str(artifact_path),
            ],
            check=True,
            env={**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(COLLECTIONS_ROOT)},
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--arch", required=True)
    args = parser.parse_args()
    lock = load_lock(args.lock)
    with tempfile.TemporaryDirectory(prefix="dholbeat-controller-install-") as temporary:
        temporary_path = Path(temporary)
        install_tools(lock, args.arch, temporary_path)
        install_collections(lock, temporary_path)


if __name__ == "__main__":
    main()

