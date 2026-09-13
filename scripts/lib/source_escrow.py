#!/usr/bin/env python3
"""Pinned-restic source escrow worker; roots never depend on the stored bundle."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT_KEYS = {"RESTIC_REPOSITORY", "RESTIC_PASSWORD", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
             "SOURCE_ESCROW_REPOSITORY_ID"}
MAX_BYTES = 256 * 1024**2


def roots(path, initializing=False):
    result = {}
    for line in Path(path).read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key in ROOT_KEYS:
            result[key] = value.strip().strip("\"'")
    if set(result) != ROOT_KEYS or not all(result.values()):
        raise ValueError("independent escrow roots incomplete")
    if result['RESTIC_REPOSITORY'] != 's3:https://7512591000a1e57593bc784dad59bfc0.r2.cloudflarestorage.com/dholbeat-publisher-backups/source':
        raise ValueError("source escrow must use the private publisher source prefix")
    if not re.fullmatch(r"[a-f0-9]{64}", result["SOURCE_ESCROW_REPOSITORY_ID"]) and not (
            initializing and result["SOURCE_ESCROW_REPOSITORY_ID"] == "new"):
        raise ValueError("source-escrow root must pin the initialized repository identity")
    return result


def retained_snapshots(snapshots, catalog):
    if set(catalog) != {"core-1", "publish-1"}:
        raise ValueError("both hosts' deployed releases must be accounted for")
    deployed = {v for v in catalog.values() if v is not None}
    if not all(re.fullmatch(r"infra-prod-[0-9]{8}-[1-9][0-9]*", str(v)) for v in deployed):
        raise ValueError("invalid deployed release")
    ordered = sorted(snapshots, key=lambda v: v["time"], reverse=True)
    if len(ordered) > 200:
        raise ValueError("source snapshot catalog exceeds bound; inspect before pruning")
    releases = {}
    coverage = {}
    for item in ordered:
        tags = item.get("tags", [])
        release_tags = [t[8:] for t in tags if t.startswith("release:")]
        if (item.get("hostname") != "dholbeat-source-escrow" or "source-escrow" not in tags
                or len(release_tags) != 1 or not re.fullmatch(r"[a-f0-9]{64}", item.get("id", ""))):
            raise ValueError("unexpected source snapshot identity")
        releases.setdefault(release_tags[0], item["id"])
        contents = {t[len('contains-release:'):] for t in tags if t.startswith('contains-release:')}
        contents.add(release_tags[0])
        if not all(re.fullmatch(r'infra-prod-[0-9]{8}-[1-9][0-9]*', value) for value in contents):
            raise ValueError('malformed source release coverage')
        for value in contents:
            coverage.setdefault(value, item['id'])
    if not deployed <= coverage.keys():
        raise ValueError("a deployed release lacks source escrow; no pruning permitted")
    superseded = [v for k, v in releases.items() if k not in deployed][:2]
    keep = {coverage[value] for value in deployed} | set(superseded)
    # The newest bundle survives even with an empty deployed catalog.
    if ordered:
        keep.add(ordered[0]["id"])
    return keep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "upload", "download"])
    parser.add_argument("--snapshot")
    parser.add_argument("--retention")
    args = parser.parse_args()
    try:
        values = roots("/run/escrow.env", initializing=args.command == "init")
        env = {**os.environ, **{k: v for k, v in values.items() if k != "SOURCE_ESCROW_REPOSITORY_ID"},
               'GOMEMLIMIT': '320MiB', 'GOMAXPROCS': '1'}

        def restic(*argv):
            result = subprocess.run(["restic", "--no-cache", *argv], env=env, cwd="/escrow",
                capture_output=True, timeout=3600)
            if result.returncode:
                raise ValueError("source restic operation failed")
            return result.stdout

        if args.command == "init":
            if values['SOURCE_ESCROW_REPOSITORY_ID'] != 'new':
                raise ValueError('source root initialization is only permitted for a new repository')
            probe = subprocess.run(['restic', '--no-cache', 'cat', 'config'], env=env,
                capture_output=True, timeout=60)
            if probe.returncode != 10:
                raise ValueError('existing/unreachable source repository cannot be silently adopted')
            restic('init')
            repository_id = json.loads(restic('cat', 'config'))['id']
            print(json.dumps({'repository_id': repository_id, 'initialized': True}))
            return
        if json.loads(restic("cat", "config"))["id"] != values["SOURCE_ESCROW_REPOSITORY_ID"]:
            raise ValueError("source root identity mismatch")
        if args.command == "upload":
            manifest = json.loads(Path("/escrow/manifest.json").read_text())
            bundle = Path("/escrow/repository.bundle")
            hasher = hashlib.sha256()
            with bundle.open('rb') as handle:
                while chunk := handle.read(1024**2):
                    hasher.update(chunk)
            if bundle.stat().st_size > MAX_BYTES or hasher.hexdigest() != manifest["bundle_sha256"]:
                raise ValueError("bundle quota/digest failed")
            catalog = json.loads(args.retention)
            if any(v and v not in manifest["production_tags"] for v in catalog.values()):
                raise ValueError("current deployed release missing from bundle")
            tag_args = [arg for tag in manifest['production_tags'] for arg in ('--tag', 'contains-release:' + tag)]
            output = restic("backup", "--json", "--host", "dholbeat-source-escrow", "--tag", "source-escrow",
                "--tag", "release:" + manifest["release"], *tag_args, "repository.bundle", "manifest.json")
            summary = next(v for v in reversed([json.loads(line) for line in output.splitlines()]) if v.get("message_type") == "summary")
            snapshot = summary["snapshot_id"]
            snapshots = json.loads(restic("snapshots", "--json", "--host", "dholbeat-source-escrow", "--tag", "source-escrow"))
            keep = retained_snapshots(snapshots, catalog)
            remove = [v["id"] for v in snapshots if v["id"] not in keep]
            if remove:
                restic("forget", *remove)
                restic("prune")
            restic("check")
            result = {"snapshot_id": snapshot, "bundle_sha256": manifest["bundle_sha256"], "retained_snapshots": len(keep)}
        else:
            if not re.fullmatch(r"[a-f0-9]{64}", args.snapshot or ""):
                raise ValueError("full source snapshot required")
            snapshots = json.loads(restic("snapshots", "--json", "--host", "dholbeat-source-escrow", "--tag", "source-escrow"))
            if not any(v.get("id") == args.snapshot for v in snapshots):
                raise ValueError("source snapshot absent or wrong purpose")
            for name, quota in (("repository.bundle", MAX_BYTES), ("manifest.json", 1024**2)):
                with Path("/escrow", name).open("xb") as output, open(os.devnull, "wb") as errors:
                    process = subprocess.Popen(["restic", "--no-cache", "dump", args.snapshot, "/escrow/" + name],
                        env=env, stdout=subprocess.PIPE, stderr=errors)
                    try:
                        size = 0
                        while chunk := process.stdout.read(1024**2):
                            size += len(chunk)
                            if size > quota:
                                raise ValueError("restored source exceeds quota")
                            output.write(chunk)
                        if process.wait(timeout=600):
                            raise ValueError("source recovery failed")
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait()
            result = {"snapshot_id": args.snapshot, "downloaded": True}
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
        print("source escrow failed; root/output values suppressed", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
