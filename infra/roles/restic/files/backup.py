#!/usr/bin/env python3
"""Host-isolated, bounded application backup and named disposable recovery.

All subprocess output stays private. Credentials are inherited from a root-only
systemd EnvironmentFile; neither provider credentials nor plaintext dumps are
included in operational status. The publisher lock spans dump/upload/retention.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

ID = re.compile(r"^[a-f0-9]{64}$")
NAME = re.compile(r"^dholbeat-restore-[a-z0-9][a-z0-9-]{0,31}$")
MAX_ARCHIVE = 2 * 1024**3
HEADROOM = 8 * 1024**3
STATE_TAG = "application-state"
CANARY_OBSERVER = Path('/usr/local/sbin/dholbeat-publisher-canary')


class BackupError(RuntimeError):
    pass


def run(argv, *, env=None, data=None, timeout=3600):
    result = subprocess.run(argv, env=env, input=data, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise BackupError("subprocess failed; private output suppressed")
    return result.stdout


@contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise BackupError("symlinked lock")
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("another backup, restore, or publisher mutation is running") from None
        yield


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise BackupError("symlinked status")
    temporary = path.with_suffix(".new")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def capacity(path, needed=0):
    if needed > 2 * MAX_ARCHIVE or shutil.disk_usage(path).free < HEADROOM + needed:
        raise BackupError("backup or restore exceeds bounded staging/headroom")


def regular_tree(path):
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise BackupError("retained path is absent or not a regular tree")
    entries = [path]
    if path.is_dir():
        for entry in path.rglob('*'):
            entries.append(entry)
            if len(entries) > 10000:
                raise BackupError('retained tree member count exceeds quota')
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in entries):
        raise BackupError("retained tree contains links or special files")
    size = sum(p.stat().st_size for p in entries if p.is_file())
    if size > MAX_ARCHIVE:
        raise BackupError("retained tree exceeds quota")
    return size


def file_hashes(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != root / "receipt.json":
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1024**2):
                    hasher.update(chunk)
            result[path.relative_to(root).as_posix()] = hasher.hexdigest()
    return result


def config(path):
    document = json.loads(Path(path).read_text())
    host = document.get("host_id")
    bucket = {"publish-1": "dholbeat-publisher-backups", "core-1": "dholbeat-core-backups"}.get(host)
    account = document.get("account_id")
    repository = document.get("repository")
    if not bucket or account != "7512591000a1e57593bc784dad59bfc0":
        raise BackupError("unknown host or account")
    expected = f"s3:https://{account}.r2.cloudflarestorage.com/{bucket}/state"
    if repository != expected or document.get("schema_version") != 1:
        raise BackupError("wrong-host/private repository boundary")
    allowed = {"schema_version", "host_id", "account_id", "repository", "repository_id_file",
               "staging", "restore_root", "status", "lock", "retained_paths", "publisher_enabled", "publisher_staging"}
    if set(document) != allowed:
        raise BackupError("unknown or missing backup configuration")
    if host == "core-1" and document["publisher_enabled"]:
        raise BackupError("publisher adapter cannot run on core-1")
    expected_paths = {'staging': '/var/lib/dholbeat/restic/staging',
        'restore_root': '/var/lib/dholbeat/restic/restores', 'status': '/var/lib/dholbeat/restic/status.json',
        'repository_id_file': '/etc/dholbeat/restic-repository-id',
        'publisher_staging': '/var/lib/dholbeat/restic/application',
        'lock': '/run/lock/dholbeat-publisher.lock' if host == 'publish-1' else '/run/lock/dholbeat-core-backup.lock'}
    if any(document[k] != v for k, v in expected_paths.items()):
        raise BackupError('backup writable paths differ from the reviewed host contract')
    allowed_paths = {"/etc/dholbeat-release", "/etc/dholbeat/receipts"}
    if document["publisher_enabled"]:
        allowed_paths |= {"/opt/dholbeat/publisher/compose.yml", "/opt/dholbeat/publisher/.env"}
    if (not isinstance(document["retained_paths"], list) or not document["retained_paths"]
            or len(document["retained_paths"]) != len(set(document["retained_paths"]))
            or not set(document["retained_paths"]) <= allowed_paths):
        raise BackupError("retained paths must be explicitly catalogued config/receipts, never live DBs")
    # Core installation is intentionally not enabled by the production role.
    if os.environ.get("RESTIC_REPOSITORY") not in (None, repository):
        raise BackupError("credential environment points at another repository")
    return document


class Restic:
    def __init__(self, document):
        self.document = document
        self.env = {**os.environ, "RESTIC_REPOSITORY": document["repository"],
                    'GOMAXPROCS': '1', 'GOMEMLIMIT': '160MiB'}
        self.argv = ["/usr/local/bin/restic", "--no-cache"]

    def command(self, *args):
        return run([*self.argv, *args], env=self.env)

    def identity(self):
        value = json.loads(self.command("cat", "config"))["id"]
        if not isinstance(value, str) or not ID.fullmatch(value):
            raise BackupError("invalid restic repository identity")
        return value

    def verify(self):
        path = Path(self.document["repository_id_file"])
        if path.is_symlink() or not path.is_file() or path.read_text().strip() != self.identity():
            raise BackupError("repository is missing or differs from the pinned host root")

    def initialize(self):
        path = Path(self.document["repository_id_file"])
        if path.exists() or path.is_symlink():
            self.verify()
            return
        # An existing unpinned repository cannot silently become this host's root.
        probe = subprocess.run([*self.argv, "cat", "config"], env=self.env, capture_output=True, timeout=60)
        if probe.returncode != 10:  # restic RepositoryDoesNotExist
            raise BackupError("initialization requires a proven absent repository")
        self.command("init")
        value = self.identity()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(value + "\n")

    def upload(self, directory, additional=None):
        # Stable stdin filename + host/tag grouping avoids one retention group per temp path.
        argv = [*self.argv, "backup", "--json", "--host", self.document["host_id"],
                "--tag", STATE_TAG, "--stdin", "--stdin-filename", "state.tar"]
        with open(os.devnull, 'wb') as errors:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, env=self.env)
            output = bytearray()
            exceeded = []

            def collect():
                while chunk := process.stdout.read(65536):
                    if len(output) + len(chunk) > 1024**2:
                        exceeded.append(True)
                        process.kill()
                        return
                    output.extend(chunk)

            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            try:
                with tarfile.open(fileobj=ArchiveWriter(process.stdin), mode="w|") as archive:
                    for child in sorted(directory.iterdir()):
                        archive.add(child, arcname=child.name, recursive=True)
                    for name, child in (additional or {}).items():
                        archive.add(child, arcname=name, recursive=True)
                process.stdin.close()
                if process.wait(timeout=3600) != 0:
                    raise BackupError("restic backup failed or only partially captured data")
            except BaseException:
                process.kill()
                process.wait()
                raise
            finally:
                reader.join(timeout=5)
                process.stdout.close()
            if exceeded or reader.is_alive():
                raise BackupError("restic summary exceeds quota")
            summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
        summary = next((v for v in reversed(summaries) if v.get("message_type") == "summary"), {})
        identifier = summary.get("snapshot_id", "")
        if not ID.fullmatch(identifier):
            raise BackupError("successful snapshot receipt missing")
        return identifier

    def retain(self):
        self.command("forget", "--host", self.document["host_id"], "--tag", STATE_TAG,
                     "--group-by", "host,tags", "--keep-daily", "7", "--keep-weekly", "4")
        self.command("prune")
        self.command("check")


def canary_maintenance(action):
    observer = CANARY_OBSERVER
    if observer.is_file():
        # A capacity failure must not prevent the recovery backup itself.
        try:
            subprocess.run([str(observer), action], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass


def backup(document, restic, visibility_control=None):
    if visibility_control is not None and (not document['publisher_enabled']
            or not re.fullmatch('[a-zA-Z0-9_-]{1,80}', visibility_control)):
        raise BackupError('Visibility control requires the publisher and a safe fixture post ID')
    restic.verify()
    stage = Path(document["staging"])
    stage.mkdir(parents=True, exist_ok=True, mode=0o700)
    capacity(stage)
    if any(stage.iterdir()):
        raise BackupError("staging is not empty; inspect interrupted run before retry")
    started = time.monotonic()
    application = None
    observed_maintenance = False
    try:
        with tempfile.TemporaryDirectory(prefix="backup-", dir=stage) as temporary:
            work = Path(temporary)
            retained = work / "retained"
            retained.mkdir(mode=0o700)
            paths = []
            retained_bytes = 0
            for index, value in enumerate(document["retained_paths"]):
                source = Path(value)
                retained_bytes += regular_tree(source)
                if retained_bytes > 16 * 1024**2:
                    raise BackupError('retained configuration exceeds its catalogued sixteen-MB quota')
                capacity(stage, retained_bytes)
                target = retained / str(index)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copyfile(source, target)
                paths.append({"source": str(source), "archive": f"retained/{index}"})
            backup_id = "backup-" + str(time.time_ns())
            additional = {}
            if document["publisher_enabled"]:
                adapters = publisher_area(document)
                application = adapters / backup_id
                observed_maintenance = True
                canary_maintenance('maintenance-begin')
                argv = ["/usr/local/sbin/dholbeat-publisher-state", "--staging-root", str(adapters),
                        "--lock", "/run/lock/dholbeat-publisher-adapter.lock", "backup", "--backup-id", backup_id]
                if visibility_control:
                    argv += ['--visibility-control-post-id', visibility_control]
                run(argv)
                additional['publisher/' + backup_id] = application
                regular_tree(application)
            hashes = file_hashes(work)
            for name, child in additional.items():
                hashes.update({name + '/' + key: value for key, value in file_hashes(child).items()})
            (work / "receipt.json").write_text(json.dumps({"schema_version": 1, "host_id": document["host_id"],
                "backup_id": backup_id, "paths": paths, "publisher": document["publisher_enabled"],
                'visibility_control': bool(visibility_control),
                "files": hashes}) + "\n")
            size = regular_tree(work) + sum(regular_tree(child) for child in additional.values())
            if size > MAX_ARCHIVE - 16 * 1024**2:
                raise BackupError('backup exceeds archive quota including tar metadata reserve')
            capacity(stage, size)
            identifier = restic.upload(work, additional)
            restic.retain()
    finally:
        if application is not None and application.exists():
            shutil.rmtree(application)
        if observed_maintenance:
            canary_maintenance('maintenance-end')
    result = {"schema_version": 1, "host_id": document["host_id"], "snapshot_id": identifier,
              "success_epoch": time.time(), "staging_bytes": size,
              "duration_seconds": round(time.monotonic() - started, 3), "last_attempt_failed": False}
    atomic_json(document["status"], result)
    return result


def publisher_area(document):
    root = Path(document['publisher_staging'])
    if root.is_symlink() or not root.is_dir() or not root.is_mount():
        raise BackupError('publisher dumps require the dedicated bounded staging filesystem')
    fs = os.statvfs(root)
    if fs.f_blocks * fs.f_frsize > MAX_ARCHIVE:
        raise BackupError('publisher staging filesystem exceeds its two-GB bound')
    if any(path.name != 'lost+found' for path in root.iterdir()):
        raise BackupError('publisher staging contains an interrupted dump; inspect before retry')
    return root


def extract(archive_path, destination):
    with tarfile.open(archive_path, "r:") as archive:
        members = []
        size = 0
        seen = set()
        for member in archive:
            members.append(member)
            path = Path(member.name)
            if (path.is_absolute() or ".." in path.parts or member.name in seen
                    or not (member.isdir() or member.isfile())):
                raise BackupError("unsafe restored archive")
            seen.add(member.name)
            size += member.size
            if size > MAX_ARCHIVE or len(seen) > 10000:
                raise BackupError("restored archive exceeds quota")
        archive.extractall(destination, members=members, filter="data")


class ArchiveWriter:
    def __init__(self, output):
        self.output = output
        self.bytes = 0

    def write(self, data):
        self.bytes += len(data)
        if self.bytes > MAX_ARCHIVE:
            raise BackupError('streamed tar exceeds the archive quota')
        return self.output.write(data)


def application_restore_permissions(publisher):
    # tar's data filter intentionally ignores directory modes. Under the
    # service's 0077 umask, Elasticsearch could not traverse restored snapshots.
    os.chown(publisher, 1000, 0)
    publisher.chmod(0o770)
    for application in publisher.iterdir():
        if not application.is_dir() or application.is_symlink():
            raise BackupError("invalid restored application directory")
        application.chmod(0o750)
        visibility = application / "visibility"
        if visibility.is_dir():
            for path in [visibility, *visibility.rglob("*")]:
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    raise BackupError("invalid restored Visibility path")
                os.chown(path, 0, 0)
                path.chmod(0o750 if path.is_dir() else 0o640)
        redis = application / "redis"
        if redis.is_dir():
            os.chown(redis, 0, 0)
            redis.chmod(0o700)


def restore(document, restic, identifier, name, port):
    if not ID.fullmatch(identifier) or not NAME.fullmatch(name) or not 5200 <= port <= 5299:
        raise BackupError("restore requires a full snapshot ID, named disposable target, and reserved loopback port")
    restic.verify()
    snapshots = json.loads(restic.command("snapshots", "--json", "--host", document["host_id"], "--tag", STATE_TAG))
    if not any(v.get("id") == identifier for v in snapshots):
        raise BackupError("snapshot missing or belongs to another host/purpose")
    root = Path(document["restore_root"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise BackupError("symlinked restore root")
    target = root / name
    if target.exists() or target.is_symlink():
        raise BackupError("disposable target already exists")
    # Download and extraction coexist until validation; preserve the reserve
    # even at their combined worst case, not just the single archive size.
    capacity(root, 2 * MAX_ARCHIVE)
    target.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        archive_path = target / "snapshot.tar"
        with archive_path.open("xb") as handle, open(os.devnull, 'wb') as errors:
            process = subprocess.Popen([*restic.argv, "dump", identifier, "state.tar"],
                env=restic.env, stdout=subprocess.PIPE, stderr=errors)
            size = 0
            try:
                while chunk := process.stdout.read(1024**2):
                    size += len(chunk)
                    if size > MAX_ARCHIVE:
                        raise BackupError("restored snapshot exceeds quota")
                    handle.write(chunk)
                if process.wait(timeout=3600) != 0:
                    raise BackupError("snapshot download failed")
            finally:
                process.kill() if process.poll() is None else None
                process.wait()
        extract(archive_path, target)
        archive_path.unlink()
        receipt = json.loads((target / "receipt.json").read_text())
        if receipt["host_id"] != document["host_id"] or receipt["schema_version"] != 1:
            raise BackupError("restored receipt is not this host")
        if receipt.get("files") != file_hashes(target):
            raise BackupError("restored retained bytes differ from the backup receipt")
        if receipt["publisher"]:
            project = name.replace("dholbeat-restore-", "dholbeat-publisher-restore-", 1)
            application_restore_permissions(target / 'publisher')
            run(["/usr/local/sbin/dholbeat-publisher-state", "--staging-root", str(target / "publisher"),
                 "--lock", "/run/lock/dholbeat-publisher-adapter.lock", "restore-disposable",
                 "--backup-id", receipt["backup_id"], "--project-name", project, "--loopback-port", str(port)],
                 env={**os.environ, 'PUBLISHER_BACKUP_STAGING': str(target / 'publisher')})
        return {"schema_version": 1, "host_id": document["host_id"], "snapshot_id": identifier,
                "disposable_target": name, "duration_seconds": round(time.monotonic() - started, 3),
                "application_restore_verified": receipt["publisher"],
                'visibility_control_verified': receipt.get('visibility_control', False), "cleanup": True}
    finally:
        shutil.rmtree(target)


def status(document):
    value = json.loads(Path(document["status"]).read_text())
    age = time.time() - value["success_epoch"]
    if (value.get("host_id") != document["host_id"] or value.get("last_attempt_failed")
            or not 0 <= age <= 26 * 3600 or value["staging_bytes"] > MAX_ARCHIVE):
        raise BackupError("backup is stale, failed, oversized, or from another host")
    return {"host_id": document["host_id"], "backup_age_seconds": round(age), "healthy": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/dholbeat/backup.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    snapshot = sub.add_parser("backup")
    snapshot.add_argument('--visibility-control-post-id')
    sub.add_parser("status")
    drill = sub.add_parser("restore-disposable")
    drill.add_argument("--snapshot", required=True)
    drill.add_argument("--name", required=True)
    drill.add_argument("--loopback-port", type=int, default=5200)
    args = parser.parse_args()
    document = None
    try:
        document = config(args.config)
        if args.command == "status":
            result = status(document)
        else:
            with lock(document["lock"]):
                restic = Restic(document)
                if args.command == "init":
                    restic.initialize()
                    result = {"host_id": document["host_id"], "initialized": True}
                elif args.command == "backup":
                    result = backup(document, restic, args.visibility_control_post_id)
                else:
                    result = restore(document, restic, args.snapshot, args.name, args.loopback_port)
        print(json.dumps(result, sort_keys=True))
    except (BackupError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        if document and args.command == "backup":
            path = Path(document["status"])
            try:
                previous = json.loads(path.read_text()) if path.is_file() else {}
                atomic_json(path, {**previous, "last_attempt_failed": True})
            except (OSError, ValueError, BackupError):
                pass
        print("backup operation failed; check the root-only configuration and recovery runbook", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
