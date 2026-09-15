#!/usr/bin/env python3
"""Bounded clean-main Git bundle creation and GitHub-independent recovery.

Git is used only locally on the operator/controller machine. No Git credentials
or clone are installed on a production host. Store roots are loaded directly
from the password manager export, independently of SOPS inside the bundle.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

MAX_BUNDLE = 256 * 1024**2
TAG = re.compile(r"^infra-prod-[0-9]{8}-[1-9][0-9]*$")
SNAPSHOT = re.compile(r"^[a-f0-9]{64}$")
# Standalone-kit imports need no repository hierarchy for recovery.
_PARENTS = Path(__file__).resolve().parents
ROOT = _PARENTS[2] if len(_PARENTS) > 2 else _PARENTS[0]


class BundleError(RuntimeError):
    pass


def command(argv, cwd=None, env=None, data=None):
    result = subprocess.run(argv, cwd=cwd, env=env, input=data, capture_output=True, timeout=600)
    if result.returncode:
        raise BundleError("source escrow command failed; private output suppressed")
    return result.stdout


def git(root, *args):
    return command(["git", "-C", str(root), *args]).decode().strip()


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024**2):
            hasher.update(chunk)
    return hasher.hexdigest()


def create(root, tag, directory):
    if not TAG.fullmatch(tag) or git(root, "status", "--porcelain"):
        raise BundleError("bundle requires a clean checkout and production release tag")
    if git(root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise BundleError("release must be annotated")
    head = git(root, "rev-parse", "HEAD")
    if head != git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}"):
        raise BundleError("checkout must be the recorded release commit")
    git(root, "merge-base", "--is-ancestor", head, "refs/heads/main")
    tags = git(root, "tag", "--list", "infra-prod-*").splitlines()
    if not tags or len(tags) > 1000:
        raise BundleError("production tag catalog missing or exceeds bound")
    for value in tags:
        if not TAG.fullmatch(value) or git(root, "cat-file", "-t", f"refs/tags/{value}") != "tag":
            raise BundleError("production tag is malformed or lightweight")
        git(root, "merge-base", "--is-ancestor", f"refs/tags/{value}^{{commit}}", "refs/heads/main")
    directory = Path(directory)
    path = directory / "repository.bundle"
    # RLIMIT_FSIZE bounds the file while Git is producing it, not only afterward.
    import resource

    def quota():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BUNDLE, MAX_BUNDLE))

    result = subprocess.run(["git", "-C", str(root), "bundle", "create", str(path),
        "refs/heads/main", *[f"refs/tags/{value}" for value in tags]],
        capture_output=True, timeout=600, preexec_fn=quota)
    if result.returncode or path.stat().st_size > MAX_BUNDLE:
        raise BundleError("bundle failed or exceeds quota")
    git(root, "bundle", "verify", str(path))
    manifest = {"schema_version": 1, "release": tag, "release_commit": head,
        "main_commit": git(root, "rev-parse", "refs/heads/main"), "production_tags": tags,
        "bundle_sha256": digest(path), "bundle_bytes": path.stat().st_size,
        "created_at": datetime.now(timezone.utc).isoformat()}
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return manifest


def recover(bundle, manifest, destination):
    bundle, destination = Path(bundle), Path(destination)
    if (manifest.get("schema_version") != 1 or not TAG.fullmatch(manifest.get("release", ""))
            or bundle.stat().st_size > MAX_BUNDLE or digest(bundle) != manifest.get("bundle_sha256")
            or bundle.stat().st_size != manifest.get("bundle_bytes")):
        raise BundleError("bundle digest/identity/quota mismatch")
    if destination.exists() or destination.is_symlink():
        raise BundleError("recovery destination must be a new disposable clone")
    destination.mkdir(mode=0o700)
    try:
        git(destination, "init", "--quiet", "--initial-branch=source-recovery")
        git(destination, "bundle", "verify", str(bundle.resolve()))
        # Only the restored file is a remote; no provider or old clone is consulted.
        git(destination, "fetch", str(bundle.resolve()), "refs/heads/main:refs/heads/main",
            "refs/tags/*:refs/tags/*")
        tag = manifest["release"]
        if git(destination, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
            raise BundleError("restored release is unannotated")
        git(destination, "checkout", "--detach", tag)
        if git(destination, "rev-parse", "HEAD") != manifest["release_commit"]:
            raise BundleError("restored release commit differs")
        if git(destination, "rev-parse", "refs/heads/main") != manifest["main_commit"]:
            raise BundleError("restored main differs")
        return {"release": tag, "release_commit": manifest["release_commit"],
            "bundle_sha256": manifest["bundle_sha256"], "github_required": False, "verified": True}
    except BaseException:
        shutil.rmtree(destination)
        raise


def private_input(path):
    path = Path(path).expanduser()
    if any(part in {'github-agent-apps', 'github-app'} for part in path.resolve().parts):
        raise BundleError('GitHub App identities cannot be used as source-escrow roots')
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
        raise BundleError("source-escrow root requires a regular mode-0600 file")
    try:
        git(path.parent, "rev-parse", "--show-toplevel")
    except BundleError:
        return path.resolve()
    raise BundleError("source-escrow root must be outside every Git checkout")


def controller(root_file, work, action, snapshot=None, retention=None):
    image = command([str(ROOT / "scripts/controller"), "digest"]).decode()
    image_id = next(v.split("=", 1)[1] for v in image.splitlines() if v.startswith("image_id="))
    args = ["docker", "run", "--rm", "--read-only", "--memory", "512m", "--cpus", "1",
        "--network", "bridge", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--env", "DHOLBEAT_IN_CONTROLLER=1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=536870912",
        "--volume", f"{ROOT}:/workspace:ro", "--volume", f"{root_file}:/run/escrow.env:ro",
        "--volume", f"{work}:/escrow:rw", "--workdir", "/workspace", image_id,
        "python", "scripts/lib/source_escrow.py", action]
    if snapshot:
        args.extend(["--snapshot", snapshot])
    if retention:
        args.extend(["--retention", json.dumps(retention, sort_keys=True)])
    return json.loads(command(args))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "create", "recover"])
    parser.add_argument("--root-file", required=True)
    parser.add_argument("--release")
    parser.add_argument("--review-pr")
    parser.add_argument("--snapshot")
    parser.add_argument("--deployed-releases", help="JSON catalog of both hosts' deployed release tags")
    parser.add_argument("--destination", help="new disposable recovery checkout, under .artifacts/")
    args = parser.parse_args()
    try:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            raise BundleError("source escrow is operator-only")
        root_file = private_input(args.root_file)
        artifacts = ROOT / ".artifacts"
        if artifacts.is_symlink():
            raise BundleError("symlinked artifacts directory")
        artifacts.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="source-escrow-", dir=artifacts) as temporary:
            work = Path(temporary)
            if args.command == "init":
                from operator_release import verify

                if not sys.stdin.isatty() or not args.release or not args.review_pr:
                    raise BundleError('source initialization requires an interactive reviewed production release')
                verify(args.release, args.review_pr)
                if input('Initialize the dedicated encrypted source prefix? Type initialize-source-escrow: ') != 'initialize-source-escrow':
                    raise BundleError('founder confirmation missing')
                result = controller(root_file, work, 'init')
                lines = root_file.read_text().splitlines()
                if 'SOURCE_ESCROW_REPOSITORY_ID=new' not in lines:
                    raise BundleError('initialization root must declare a new repository')
                content = '\n'.join('SOURCE_ESCROW_REPOSITORY_ID=' + result['repository_id']
                    if line == 'SOURCE_ESCROW_REPOSITORY_ID=new' else line for line in lines) + '\n'
                descriptor, replacement = tempfile.mkstemp(prefix='.source-root-', dir=root_file.parent)
                try:
                    with os.fdopen(descriptor, 'w') as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(replacement, root_file)
                finally:
                    Path(replacement).unlink(missing_ok=True)
                result['password_manager_root_update_required'] = True
            elif args.command == "create":
                from operator_release import verify

                if not args.release or not args.review_pr or not args.deployed_releases:
                    raise BundleError("create requires reviewed release and explicit deployed-release catalog")
                verify(args.release, args.review_pr)
                manifest = create(ROOT, args.release, work)
                retention = json.loads(Path(args.deployed_releases).read_text())
                result = controller(root_file, work, "upload", retention=retention)
                result["release_commit"] = manifest["release_commit"]
            else:
                if not args.snapshot or not SNAPSHOT.fullmatch(args.snapshot) or not args.destination:
                    raise BundleError("recover requires full snapshot ID and new disposable destination")
                destination = Path(args.destination).resolve()
                if not destination.is_relative_to(artifacts.resolve()) or destination == artifacts.resolve():
                    raise BundleError("recovery checkout must be a child of .artifacts/")
                controller(root_file, work, "download", snapshot=args.snapshot)
                result = recover(work / "repository.bundle", json.loads((work / "manifest.json").read_text()), destination)
            result["temporary_bundle_removed"] = True
        print(json.dumps(result, sort_keys=True))
    except (BundleError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("source escrow failed; private subprocess output suppressed", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
