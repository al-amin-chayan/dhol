#!/usr/bin/env python3
"""Application-aware Postiz and Temporal backup/restore adapter."""

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
import tempfile
from typing import Any, BinaryIO, Iterator, Sequence


DEFAULT_PROJECT_DIR = Path("/opt/dholbeat/publisher")
DEFAULT_COMPOSE_FILE = DEFAULT_PROJECT_DIR / "compose.yml"
DEFAULT_RESTORE_FILE = DEFAULT_PROJECT_DIR / "compose.restore.yml"
DEFAULT_STAGING_ROOT = Path("/var/lib/dholbeat/publisher/backup-staging")
DEFAULT_DOCKER_DATA_ROOT = Path("/var/lib/docker")
DEFAULT_KILL_SWITCH = Path("/var/lib/dholbeat/publisher/kill-switch.json")
DEFAULT_LOCK = Path("/run/lock/dholbeat-publisher.lock")
BACKUP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RESTORE_PROJECT_RE = re.compile(r"^dholbeat-publisher-restore-[a-z0-9][a-z0-9-]{0,31}$")
POST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MANIFEST_NAME = "manifest.json"
POSTIZ_DUMP = "postiz.sql"
TEMPORAL_DUMP = "temporal.sql"
REDIS_STATE_DIRECTORY = "redis"
SNAPSHOT_REPOSITORY = "dholbeat_backup"
SNAPSHOT_NAME = "temporal_visibility"
MINIMUM_RESTORE_HEADROOM_BYTES = 8 * 1024 * 1024 * 1024


class StateError(RuntimeError):
    """A backup/restore safety or state operation failed."""


def state_error_message(error: StateError) -> str:
    details = [str(error), *getattr(error, "__notes__", [])]
    return "; ".join(detail for detail in details if detail)


class ComposeRunner:
    def __init__(
        self,
        compose_files: Sequence[Path],
        project_directory: Path,
        *,
        project_name: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.prefix = ["docker", "compose"]
        for compose_file in compose_files:
            self.prefix.extend(["--file", str(compose_file)])
        self.prefix.extend(["--project-directory", str(project_directory)])
        if project_name is not None:
            self.prefix.extend(["--project-name", project_name])
        self.environment = os.environ.copy()
        self.environment.update(environment or {})

    def run(
        self,
        arguments: Sequence[str],
        *,
        capture_output: bool = False,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | None = None,
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [*self.prefix, *arguments],
                check=True,
                stdin=stdin,
                stdout=stdout if stdout is not None else (subprocess.PIPE if capture_output else None),
                stderr=subprocess.PIPE,
                text=False,
                env=self.environment,
            )
        except subprocess.CalledProcessError as error:
            raise StateError("publisher state command failed") from error


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def safe_child(root: Path, identifier: str) -> Path:
    if BACKUP_ID_RE.fullmatch(identifier) is None:
        raise StateError("backup ID must contain only lowercase letters, digits, and hyphens")
    if not root.is_dir() or root.is_symlink():
        raise StateError("backup staging root must be an existing real directory")
    resolved_root = root.resolve()
    candidate = (resolved_root / identifier).resolve()
    if candidate.parent != resolved_root:
        raise StateError("backup path escapes the staging root")
    return candidate


def validate_restore_project(project_name: str) -> None:
    if RESTORE_PROJECT_RE.fullmatch(project_name) is None:
        raise StateError("restore project must use dholbeat-publisher-restore-<id>")


def decode_stdout(result: subprocess.CompletedProcess) -> str:
    value = result.stdout or b""
    return value.decode("utf-8", errors="strict").strip()


def effective_restore_contract(
    runner: ComposeRunner,
    project_name: str,
) -> str:
    result = runner.run(["config", "--format", "json"], capture_output=True)
    try:
        document = json.loads(decode_stdout(result))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateError("effective restore Compose config is invalid") from error
    return validate_effective_restore_document(document, project_name)


def validate_effective_restore_document(
    document: Any,
    project_name: str,
) -> str:
    if not isinstance(document, dict) or document.get("name") != project_name:
        raise StateError("effective restore Compose project is not the disposable project")
    services = document.get("services")
    networks = document.get("networks")
    if not isinstance(services, dict) or not isinstance(networks, dict):
        raise StateError("effective restore Compose config is incomplete")
    attached_networks: set[str] = set()
    for service in services.values():
        if not isinstance(service, dict):
            raise StateError("effective restore service config is invalid")
        if service.get("network_mode"):
            raise StateError("effective restore service bypasses isolated networks")
        service_networks = service.get("networks", {})
        if isinstance(service_networks, list):
            attached_networks.update(str(value) for value in service_networks)
        elif isinstance(service_networks, dict):
            attached_networks.update(str(value) for value in service_networks)
        else:
            raise StateError("effective restore service networks are invalid")
    if not attached_networks or any(
        not isinstance(networks.get(network_id), dict)
        or networks[network_id].get("internal") is not True
        for network_id in attached_networks
    ):
        raise StateError("effective restore Compose permits outbound network access")
    postiz = services.get("postiz", {})
    if postiz.get("environment", {}).get("RUN_CRON") != "false":
        raise StateError("effective restore Postiz cron is not disabled")
    postiz_networks = postiz.get("networks", {})
    if set(postiz_networks) != {"publisher-edge", "publisher-state"}:
        raise StateError("effective restore Postiz networks are incomplete")
    elasticsearch = services.get("temporal-elasticsearch", {})
    snapshot_mounts = [
        volume
        for volume in elasticsearch.get("volumes", [])
        if isinstance(volume, dict) and volume.get("target") == "/snapshots"
    ]
    if len(snapshot_mounts) != 1 or snapshot_mounts[0].get("read_only") is not True:
        raise StateError("effective restore backup mount is not read-only")
    contract = {
        "project_name": project_name,
        "internal_networks": sorted(attached_networks),
        "postiz_cron": "disabled",
        "snapshots": "read-only",
    }
    return hashlib.sha256(
        json.dumps(contract, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def require_restore_capacity(source: Path, docker_data_root: Path) -> dict[str, int]:
    if not docker_data_root.is_dir() or docker_data_root.is_symlink():
        raise StateError("Docker data root must be an existing real directory")
    backup_bytes = directory_bytes(source)
    required_bytes = MINIMUM_RESTORE_HEADROOM_BYTES + (backup_bytes * 2)
    free_bytes = shutil.disk_usage(docker_data_root).free
    if free_bytes < required_bytes:
        raise StateError("insufficient disk for disposable restore and 8 GiB headroom")
    return {
        "backup_bytes": backup_bytes,
        "required_free_bytes": required_bytes,
        "free_bytes_before": free_bytes,
    }


def sql_scalar(runner: ComposeRunner, service: str, user: str, database: str, query: str) -> int:
    result = runner.run(
        ["exec", "-T", service, "psql", "-U", user, "-d", database, "-tAc", query],
        capture_output=True,
    )
    value = decode_stdout(result).replace(" ", "")
    if not value.isdigit():
        raise StateError("database count probe did not return a non-negative integer")
    return int(value)


def redis_key_count(runner: ComposeRunner) -> int:
    result = runner.run(
        ["exec", "-T", "postiz-redis", "redis-cli", "--raw", "DBSIZE"],
        capture_output=True,
    )
    value = decode_stdout(result)
    if not value.isdigit():
        raise StateError("Redis key-count probe did not return a non-negative integer")
    return int(value)


def running_services(runner: ComposeRunner) -> set[str]:
    result = runner.run(["ps", "--status", "running", "--services"], capture_output=True)
    return {line.strip() for line in decode_stdout(result).splitlines() if line.strip()}


def es_request(
    runner: ComposeRunner,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arguments = [
        "exec",
        "-T",
        "temporal-elasticsearch",
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--request",
        method,
        "--header",
        "Content-Type: application/json",
    ]
    if body is not None:
        arguments.extend(["--data-binary", json.dumps(body, separators=(",", ":"), sort_keys=True)])
    arguments.append(f"http://127.0.0.1:9200{path}")
    result = runner.run(arguments, capture_output=True)
    try:
        response = json.loads(decode_stdout(result))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateError("Elasticsearch returned invalid JSON") from error
    if not isinstance(response, dict):
        raise StateError("Elasticsearch response must be an object")
    return response


def visibility_hits(runner: ComposeRunner, post_id: str) -> int:
    if POST_ID_RE.fullmatch(post_id) is None:
        raise StateError("visibility control post ID contains forbidden characters")
    workflow_id = f"post_{post_id}"
    result = runner.run(
        [
            "exec",
            "-T",
            "temporal",
            "temporal",
            "workflow",
            "list",
            "--address",
            "temporal:7233",
            "--namespace",
            "default",
            "--query",
            f'postId="{post_id}" AND ExecutionStatus="Running"',
            "--limit",
            "10",
            "--command-timeout",
            "30s",
            "--output",
            "json",
        ],
        capture_output=True,
    )
    try:
        rows = json.loads(decode_stdout(result))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateError("Temporal Visibility returned invalid JSON") from error
    if not isinstance(rows, list):
        raise StateError("Temporal Visibility response must be a list")
    return sum(
        1
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("execution"), dict)
        and row["execution"].get("workflowId") == workflow_id
    )


def dump_database(
    runner: ComposeRunner,
    service: str,
    user: str,
    database: str,
    destination: Path,
) -> None:
    with destination.open("wb") as handle:
        runner.run(
            ["exec", "-T", service, "pg_dump", "-U", user, "-d", database, "--clean", "--if-exists"],
            stdout=handle,
        )
        handle.flush()
        os.fsync(handle.fileno())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_receipts(root: Path) -> dict[str, str]:
    receipts: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != MANIFEST_NAME:
            receipts[path.relative_to(root).as_posix()] = sha256(path)
    return receipts


def verify_manifest(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or any(path.is_symlink() for path in directory.rglob("*")):
        raise StateError("backup directory may not contain symbolic links")
    manifest_path = directory / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateError("backup manifest is missing or invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise StateError("backup manifest schema is unsupported")
    if manifest.get("adapter") != "postiz-v2.23.0":
        raise StateError("backup manifest belongs to another publisher adapter")
    backup_id = manifest.get("backup_id")
    if (
        not isinstance(backup_id, str)
        or BACKUP_ID_RE.fullmatch(backup_id) is None
        or backup_id != directory.name
    ):
        raise StateError("backup manifest ID does not match its safe directory")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or expected != file_receipts(directory):
        raise StateError("backup file digest verification failed")
    required_files = {POSTIZ_DUMP, TEMPORAL_DUMP}
    if not required_files <= set(expected):
        raise StateError("backup manifest omits a retained database dump")
    if not any(name.startswith(f"{REDIS_STATE_DIRECTORY}/") for name in expected):
        raise StateError("backup manifest omits retained Redis state")
    if not any(name.startswith("visibility/") for name in expected):
        raise StateError("backup manifest omits retained Visibility state")
    for field in (
        "postiz_organization_count",
        "postiz_redis_key_count",
        "temporal_running_workflow_count",
    ):
        value = manifest.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise StateError(f"backup manifest has invalid {field}")
    return manifest


def copy_service_state(
    runner: ComposeRunner,
    service: str,
    container_directory: str,
    destination: Path,
) -> None:
    destination.mkdir(mode=0o700)
    runner.run(
        ["cp", "--archive", f"{service}:{container_directory}/.", str(destination)]
    )


def restore_service_state(
    runner: ComposeRunner,
    service: str,
    source: Path,
    container_directory: str,
) -> None:
    if not source.is_dir() or source.is_symlink():
        raise StateError(f"retained {service} state is missing or unsafe")
    runner.run(["create", service])
    runner.run(
        ["cp", "--archive", f"{source}/.", f"{service}:{container_directory}"]
    )


def create_visibility_snapshot(runner: ComposeRunner, backup_id: str, output: Path) -> None:
    visibility = output / "visibility"
    visibility.mkdir(mode=0o770)
    try:
        os.chown(visibility, 1000, 0)
    except PermissionError as error:
        raise StateError("backup adapter must run as root to stage Visibility state") from error
    location = f"/snapshots/{backup_id}/visibility"
    repository = es_request(
        runner,
        "PUT",
        f"/_snapshot/{SNAPSHOT_REPOSITORY}",
        {"type": "fs", "settings": {"location": location, "compress": True}},
    )
    if repository.get("acknowledged") is not True:
        raise StateError("Elasticsearch snapshot repository was not acknowledged")
    response = es_request(
        runner,
        "PUT",
        f"/_snapshot/{SNAPSHOT_REPOSITORY}/{SNAPSHOT_NAME}?wait_for_completion=true",
        {"include_global_state": True},
    )
    shards = response.get("snapshot", {}).get("shards", {})
    if shards.get("failed") != 0:
        raise StateError("Elasticsearch Visibility snapshot has failed shards")


def backup(
    runner: ComposeRunner,
    staging_root: Path,
    backup_id: str,
    kill_switch: Path,
    visibility_control_post_id: str | None,
) -> Path:
    output = safe_child(staging_root, backup_id)
    if output.exists():
        raise StateError("backup output already exists")
    running = running_services(runner)
    senders = {"postiz", "temporal"}
    state_services = {
        "postiz-postgres",
        "postiz-redis",
        "temporal-postgres",
        "temporal-elasticsearch",
    }
    expected = state_services if kill_switch.exists() else state_services | senders
    if running != expected:
        raise StateError("publisher service state does not match its kill-switch boundary")
    should_restart_senders = not kill_switch.exists()
    operation_error: Exception | None = None
    output.mkdir(parents=True, mode=0o750)
    try:
        control_hits = None
        if visibility_control_post_id is not None:
            control_hits = visibility_hits(runner, visibility_control_post_id)
            if control_hits != 1:
                raise StateError("Visibility control was not established before backup")
        runner.run(["stop", "postiz", "temporal"])
        retained_redis_key_count = redis_key_count(runner)
        runner.run(["stop", "postiz-redis"])
        organization_count = sql_scalar(
            runner, "postiz-postgres", "postiz", "postiz", 'select count(*) from "Organization";'
        )
        running_workflow_count = sql_scalar(
            runner,
            "temporal-postgres",
            "temporal",
            "temporal",
            "select count(*) from current_executions where status = 1;",
        )
        dump_database(runner, "postiz-postgres", "postiz", "postiz", output / POSTIZ_DUMP)
        dump_database(
            runner, "temporal-postgres", "temporal", "temporal", output / TEMPORAL_DUMP
        )
        copy_service_state(
            runner,
            "postiz-redis",
            "/data",
            output / REDIS_STATE_DIRECTORY,
        )
        create_visibility_snapshot(runner, backup_id, output)
        manifest = {
            "schema_version": 1,
            "adapter": "postiz-v2.23.0",
            "backup_id": backup_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "postiz_organization_count": organization_count,
            "postiz_redis_key_count": retained_redis_key_count,
            "temporal_running_workflow_count": running_workflow_count,
            "visibility_control": (
                None
                if visibility_control_post_id is None
                else {
                    "post_id": visibility_control_post_id,
                    "workflow_id": f"post_{visibility_control_post_id}",
                    "hits_before": control_hits,
                }
            ),
            "files": file_receipts(output),
        }
        manifest_path = output / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(manifest_path, 0o600)
        verify_manifest(output)
    except Exception as error:
        operation_error = error
        shutil.rmtree(output, ignore_errors=True)
        raise
    finally:
        restart_services = ["postiz-redis"]
        if should_restart_senders:
            restart_services.extend(["temporal", "postiz"])
        try:
            runner.run(
                [
                    "up",
                    "--detach",
                    "--wait",
                    "--wait-timeout",
                    "900",
                    *restart_services,
                ]
            )
        except Exception as restart_error:
            if operation_error is None:
                raise
            operation_error.add_note(
                f"publisher restart also failed: {restart_error}"
            )
    return output


def restore_database(
    runner: ComposeRunner,
    service: str,
    user: str,
    database: str,
    source: Path,
) -> None:
    with source.open("rb") as handle:
        runner.run(
            [
                "exec",
                "-T",
                service,
                "psql",
                "-U",
                user,
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
            ],
            stdin=handle,
        )


def restore_visibility_snapshot(runner: ComposeRunner, backup_id: str) -> None:
    location = f"/snapshots/{backup_id}/visibility"
    response = es_request(
        runner,
        "PUT",
        f"/_snapshot/{SNAPSHOT_REPOSITORY}",
        {"type": "fs", "settings": {"location": location, "readonly": True}},
    )
    if response.get("acknowledged") is not True:
        raise StateError("restore snapshot repository was not acknowledged")
    response = es_request(
        runner,
        "POST",
        f"/_snapshot/{SNAPSHOT_REPOSITORY}/{SNAPSHOT_NAME}/_restore?wait_for_completion=true",
        {"include_global_state": True},
    )
    if response.get("snapshot", {}).get("shards", {}).get("failed") != 0:
        raise StateError("Elasticsearch Visibility restore has failed shards")


def restore(
    runner: ComposeRunner,
    source: Path,
    project_name: str,
    docker_data_root: Path,
) -> dict[str, Any]:
    validate_restore_project(project_name)
    manifest = verify_manifest(source)
    contract_digest = effective_restore_contract(runner, project_name)
    capacity = require_restore_capacity(source, docker_data_root)
    existing = decode_stdout(runner.run(["ps", "--all", "--services"], capture_output=True))
    if existing:
        raise StateError("restore project already exists; use a fresh project name")
    runner.run(
        [
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            "600",
            "postiz-postgres",
            "temporal-postgres",
            "temporal-elasticsearch",
        ]
    )
    restore_service_state(
        runner,
        "postiz-redis",
        source / REDIS_STATE_DIRECTORY,
        "/data",
    )
    runner.run(
        ["up", "--detach", "--wait", "--wait-timeout", "120", "postiz-redis"]
    )
    restored_redis_key_count = redis_key_count(runner)
    if restored_redis_key_count != manifest["postiz_redis_key_count"]:
        raise StateError("restored Redis key count differs from backup")
    restore_database(runner, "postiz-postgres", "postiz", "postiz", source / POSTIZ_DUMP)
    restore_database(
        runner, "temporal-postgres", "temporal", "temporal", source / TEMPORAL_DUMP
    )
    restore_visibility_snapshot(runner, manifest["backup_id"])
    runner.run(["up", "--detach", "--wait", "--wait-timeout", "900", "temporal", "postiz"])
    organization_count = sql_scalar(
        runner, "postiz-postgres", "postiz", "postiz", 'select count(*) from "Organization";'
    )
    running_workflow_count = sql_scalar(
        runner,
        "temporal-postgres",
        "temporal",
        "temporal",
        "select count(*) from current_executions where status = 1;",
    )
    if organization_count != manifest["postiz_organization_count"]:
        raise StateError("restored Postiz organization count differs from backup")
    if running_workflow_count != manifest["temporal_running_workflow_count"]:
        raise StateError("restored Temporal running-workflow count differs from backup")
    visibility = manifest.get("visibility_control")
    hits_after = None
    if isinstance(visibility, dict):
        hits_after = visibility_hits(runner, visibility["post_id"])
        if hits_after != visibility["hits_before"]:
            raise StateError("restored Temporal Visibility control differs from backup")
    return {
        "schema_version": 1,
        "adapter": "postiz-v2.23.0",
        "backup_id": manifest["backup_id"],
        "restore_project": project_name,
        "outbound_provider_access": "verified-blocked",
        "effective_restore_contract_sha256": contract_digest,
        "capacity": capacity,
        "postiz_organization_count": organization_count,
        "postiz_redis_key_count": restored_redis_key_count,
        "temporal_running_workflow_count": running_workflow_count,
        "visibility_hits_after": hits_after,
        "verified": True,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE_FILE)
    root.add_argument("--restore-file", type=Path, default=DEFAULT_RESTORE_FILE)
    root.add_argument("--project-directory", type=Path, default=DEFAULT_PROJECT_DIR)
    root.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    root.add_argument("--docker-data-root", type=Path, default=DEFAULT_DOCKER_DATA_ROOT)
    root.add_argument("--kill-switch", type=Path, default=DEFAULT_KILL_SWITCH)
    root.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    commands = root.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--backup-id", required=True)
    backup_parser.add_argument("--visibility-control-post-id")

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--backup-id", required=True)

    contract_parser = commands.add_parser("validate-effective-restore")
    contract_parser.add_argument("--project-name", required=True)
    contract_parser.add_argument(
        "--config-stdin",
        action="store_true",
        help="validate an already rendered Compose JSON document from standard input",
    )

    restore_parser = commands.add_parser("restore-disposable")
    restore_parser.add_argument("--backup-id", required=True)
    restore_parser.add_argument("--project-name", required=True)
    restore_parser.add_argument("--loopback-port", required=True, type=int)
    restore_parser.add_argument(
        "--keep",
        action="store_true",
        help="retain the exact disposable project temporarily for evidence or diagnosis",
    )
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        with exclusive_lock(args.lock):
            if args.command == "backup":
                runner = ComposeRunner([args.compose_file], args.project_directory)
                output = backup(
                    runner,
                    args.staging_root,
                    args.backup_id,
                    args.kill_switch,
                    args.visibility_control_post_id,
                )
                result = {
                    "schema_version": 1,
                    "backup_id": args.backup_id,
                    "path": str(output),
                    "verified": True,
                }
            elif args.command == "verify":
                directory = safe_child(args.staging_root, args.backup_id)
                manifest = verify_manifest(directory)
                result = {
                    "schema_version": 1,
                    "backup_id": manifest["backup_id"],
                    "verified": True,
                }
            elif args.command == "validate-effective-restore":
                validate_restore_project(args.project_name)
                if args.config_stdin:
                    try:
                        contract_document = json.load(sys.stdin)
                    except json.JSONDecodeError as error:
                        raise StateError(
                            "effective restore Compose config is invalid"
                        ) from error
                    contract_digest = validate_effective_restore_document(
                        contract_document, args.project_name
                    )
                else:
                    runner = ComposeRunner(
                        [args.compose_file, args.restore_file],
                        args.project_directory,
                        project_name=args.project_name,
                    )
                    contract_digest = effective_restore_contract(
                        runner, args.project_name
                    )
                result = {
                    "schema_version": 1,
                    "restore_project": args.project_name,
                    "effective_restore_contract_sha256": contract_digest,
                    "outbound_provider_access": "verified-blocked",
                    "verified": True,
                }
            else:
                validate_restore_project(args.project_name)
                if not 1024 <= args.loopback_port <= 65535:
                    raise StateError("restore loopback port must be between 1024 and 65535")
                directory = safe_child(args.staging_root, args.backup_id)
                runner = ComposeRunner(
                    [args.compose_file, args.restore_file],
                    args.project_directory,
                    project_name=args.project_name,
                    environment={
                        "PUBLISHER_LOOPBACK_PORT": str(args.loopback_port),
                        "PUBLISHER_MAIN_URL": f"http://127.0.0.1:{args.loopback_port}",
                    },
                )
                restore_error: Exception | None = None
                try:
                    result = restore(
                        runner,
                        directory,
                        args.project_name,
                        args.docker_data_root,
                    )
                except Exception as error:
                    restore_error = error
                    raise
                finally:
                    if not args.keep:
                        try:
                            runner.run(["down", "--volumes", "--remove-orphans"])
                        except Exception as cleanup_error:
                            if restore_error is None:
                                raise
                            restore_error.add_note(
                                f"disposable restore cleanup also failed: {cleanup_error}"
                            )
                result["disposable_project"] = "retained" if args.keep else "removed"
    except StateError as error:
        print(f"publisher state failure: {state_error_message(error)}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
