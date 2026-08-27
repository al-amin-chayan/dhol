#!/usr/bin/env python3
"""Fail-closed Postiz/Temporal kill switch and workflow termination control."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Iterator, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest


DEFAULT_PROJECT_DIR = Path("/opt/dholbeat/publisher")
DEFAULT_COMPOSE_FILE = DEFAULT_PROJECT_DIR / "compose.yml"
DEFAULT_MARKER = Path("/var/lib/dholbeat/publisher/kill-switch.json")
DEFAULT_LOCK = Path("/run/lock/dholbeat-publisher.lock")
POST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CONFIRM_UNFREEZE = "UNFREEZE-PUBLISHER"
CRITICAL_SERVICES = {"postiz", "temporal"}


class ControlError(RuntimeError):
    """A safety or publisher-control operation failed."""


class ComposeRunner:
    def __init__(self, compose_file: Path, project_directory: Path) -> None:
        self.prefix = [
            "docker",
            "compose",
            "--file",
            str(compose_file),
            "--project-directory",
            str(project_directory),
        ]

    def run(
        self,
        arguments: Sequence[str],
        *,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [*self.prefix, *arguments],
                check=True,
                text=True,
                capture_output=capture_output,
            )
        except subprocess.CalledProcessError as error:
            raise ControlError("publisher Compose control command failed") from error


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def running_services(runner: ComposeRunner) -> set[str]:
    result = runner.run(["ps", "--status", "running", "--services"], capture_output=True)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def write_marker(path: Path, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "state": "frozen",
        "reason": reason,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    descriptor, temporary_name = tempfile.mkstemp(prefix=".kill-switch-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def freeze(runner: ComposeRunner, marker: Path, reason: str) -> None:
    normalized = " ".join(reason.split())
    if not normalized or len(normalized) > 240:
        raise ControlError("freeze reason must contain 1-240 printable characters")
    if not marker.exists():
        write_marker(marker, normalized)
    runner.run(["stop", "postiz", "temporal"])
    still_running = running_services(runner) & CRITICAL_SERVICES
    if still_running:
        raise ControlError(f"kill switch failed; still running: {', '.join(sorted(still_running))}")


def health_ready(url: str) -> bool:
    try:
        with urlrequest.urlopen(url, timeout=5) as response:
            return response.status in {200, 401}
    except urlerror.HTTPError as error:
        return error.code == 401
    except (OSError, urlerror.URLError):
        return False


def unfreeze(
    runner: ComposeRunner,
    marker: Path,
    confirmation: str,
    health_url: str,
    timeout_seconds: int,
) -> None:
    if confirmation != CONFIRM_UNFREEZE:
        raise ControlError(f"unfreeze requires --confirm {CONFIRM_UNFREEZE}")
    if not marker.is_file():
        raise ControlError("publisher is not frozen")
    runner.run(["up", "--detach", "temporal", "postiz"])
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if CRITICAL_SERVICES <= running_services(runner) and health_ready(health_url):
            marker.unlink()
            return
        time.sleep(5)
    runner.run(["stop", "postiz", "temporal"])
    raise ControlError("publisher did not become healthy; kill switch remains active")


def workflow_status(runner: ComposeRunner, post_id: str) -> str:
    if POST_ID_RE.fullmatch(post_id) is None:
        raise ControlError("post ID contains forbidden characters")
    workflow_id = f"post_{post_id}"
    result = runner.run(
        [
            "exec",
            "-T",
            "temporal",
            "temporal",
            "workflow",
            "describe",
            "--address",
            "temporal:7233",
            "--namespace",
            "default",
            "--workflow-id",
            workflow_id,
            "--output",
            "json",
        ],
        capture_output=True,
    )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ControlError("Temporal workflow description is invalid") from error
    if not isinstance(document, dict):
        raise ControlError("Temporal workflow description must be an object")
    information = document.get("workflowExecutionInfo")
    if not isinstance(information, dict):
        information = document.get("workflow_execution_info")
    if not isinstance(information, dict):
        raise ControlError("Temporal workflow description omits execution info")
    status = information.get("status")
    if isinstance(status, dict):
        status = status.get("name")
    if status == 1:
        return "RUNNING"
    if not isinstance(status, str) or not status:
        raise ControlError("Temporal workflow description omits status")
    prefix = "WORKFLOW_EXECUTION_STATUS_"
    normalized = status.removeprefix(prefix).upper()
    if normalized == "UNSPECIFIED":
        raise ControlError("Temporal workflow status is unspecified")
    return normalized


def terminate_workflow(
    runner: ComposeRunner,
    post_id: str,
    timeout_seconds: int,
) -> str:
    status = workflow_status(runner, post_id)
    if status != "RUNNING":
        return status
    workflow_id = f"post_{post_id}"
    runner.run(
        [
            "exec",
            "-T",
            "temporal",
            "temporal",
            "workflow",
            "terminate",
            "--address",
            "temporal:7233",
            "--namespace",
            "default",
            "--workflow-id",
            workflow_id,
            "--reason",
            "Dholbeat cancellation safety control",
        ]
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = workflow_status(runner, post_id)
        if status != "RUNNING":
            return status
        time.sleep(2)
    raise ControlError(f"Temporal workflow {workflow_id} remains RUNNING")


def status_document(runner: ComposeRunner, marker: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "frozen": marker.is_file(),
        "running_services": sorted(running_services(runner)),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE_FILE)
    root.add_argument("--project-directory", type=Path, default=DEFAULT_PROJECT_DIR)
    root.add_argument("--marker", type=Path, default=DEFAULT_MARKER)
    root.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    commands = root.add_subparsers(dest="command", required=True)

    freeze_parser = commands.add_parser("freeze")
    freeze_parser.add_argument("--reason", required=True)

    unfreeze_parser = commands.add_parser("unfreeze")
    unfreeze_parser.add_argument("--confirm", required=True)
    unfreeze_parser.add_argument(
        "--health-url", default="http://127.0.0.1:5000/api/user/self"
    )
    unfreeze_parser.add_argument("--timeout-seconds", type=int, default=900)

    terminate_parser = commands.add_parser("terminate-post-workflow")
    terminate_parser.add_argument("--post-id", required=True)
    terminate_parser.add_argument("--timeout-seconds", type=int, default=60)

    verify_parser = commands.add_parser("verify-post-workflow-stopped")
    verify_parser.add_argument("--post-id", required=True)
    commands.add_parser("status")
    return root


def main() -> None:
    args = parser().parse_args()
    runner = ComposeRunner(args.compose_file, args.project_directory)
    try:
        with exclusive_lock(args.lock):
            if args.command == "freeze":
                freeze(runner, args.marker, args.reason)
                result = status_document(runner, args.marker)
            elif args.command == "unfreeze":
                unfreeze(
                    runner,
                    args.marker,
                    args.confirm,
                    args.health_url,
                    args.timeout_seconds,
                )
                result = status_document(runner, args.marker)
            elif args.command == "terminate-post-workflow":
                workflow = terminate_workflow(runner, args.post_id, args.timeout_seconds)
                result = {"schema_version": 1, "post_id": args.post_id, "status": workflow}
            elif args.command == "verify-post-workflow-stopped":
                workflow = workflow_status(runner, args.post_id)
                if workflow == "RUNNING":
                    raise ControlError(f"Temporal workflow post_{args.post_id} remains RUNNING")
                result = {"schema_version": 1, "post_id": args.post_id, "status": workflow}
            else:
                result = status_document(runner, args.marker)
    except ControlError as error:
        print(f"publisher control failure: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
