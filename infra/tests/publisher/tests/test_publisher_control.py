from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "infra/roles/publisher/files"))

from publisher_control import (  # noqa: E402
    CONFIRM_UNFREEZE,
    ControlError,
    freeze,
    terminate_workflow,
    unfreeze,
    workflow_status,
)
from publisher_docker import is_compose_up, run_docker  # noqa: E402


class FakeRunner:
    def __init__(self, status_values: list[str] | None = None) -> None:
        self.commands: list[list[str]] = []
        self.status_values = status_values or []
        self.running = {"postiz", "temporal"}

    def run(self, arguments, *, capture_output=False):
        command = list(arguments)
        self.commands.append(command)
        if command[:2] == ["stop", "postiz"]:
            self.running -= {"postiz", "temporal"}
        elif command[:2] == ["up", "--detach"]:
            self.running |= {"postiz", "temporal"}
        if command[:3] == ["ps", "--status", "running"]:
            return subprocess.CompletedProcess(command, 0, "\n".join(sorted(self.running)), "")
        if "describe" in command:
            value = self.status_values.pop(0) if self.status_values else "absent"
            if value == "absent":
                raise ControlError("publisher Compose control command failed")
            payload = {"workflowExecutionInfo": {"status": value}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_freeze_is_idempotent_and_stops_both_senders(tmp_path: Path) -> None:
    runner = FakeRunner()
    marker = tmp_path / "kill-switch.json"
    freeze(runner, marker, "fixture incident")
    freeze(runner, marker, "fixture incident")
    assert marker.is_file()
    assert runner.running.isdisjoint({"postiz", "temporal"})


def test_freeze_rejects_an_empty_reason(tmp_path: Path) -> None:
    with pytest.raises(ControlError, match="freeze reason"):
        freeze(FakeRunner(), tmp_path / "marker", "  ")


def test_unfreeze_requires_exact_confirmation(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    marker.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ControlError, match=CONFIRM_UNFREEZE):
        unfreeze(FakeRunner(), marker, "yes", "http://fixture.invalid", 1)


def test_invalid_post_id_never_reaches_sql() -> None:
    runner = FakeRunner()
    with pytest.raises(ControlError, match="forbidden"):
        workflow_status(runner, "x'; drop table executions; --")
    assert runner.commands == []


def test_running_workflow_is_terminated_and_rechecked() -> None:
    runner = FakeRunner(
        [
            "WORKFLOW_EXECUTION_STATUS_RUNNING",
            "WORKFLOW_EXECUTION_STATUS_RUNNING",
            "WORKFLOW_EXECUTION_STATUS_TERMINATED",
        ]
    )
    assert terminate_workflow(runner, "fixture-post", 5) == "TERMINATED"
    terminate = next(command for command in runner.commands if "terminate" in command)
    assert "post_fixture-post" in terminate


def test_already_stopped_workflow_is_idempotent() -> None:
    runner = FakeRunner(["WORKFLOW_EXECUTION_STATUS_TERMINATED"])
    assert terminate_workflow(runner, "fixture-post", 1) == "TERMINATED"
    assert not any("terminate" in command for command in runner.commands)


def test_missing_workflow_fails_closed() -> None:
    with pytest.raises(ControlError):
        workflow_status(FakeRunner(["absent"]), "fixture-post")


def test_docker_guard_recognizes_only_compose_up() -> None:
    assert is_compose_up(["compose", "--file", "compose.yml", "up", "--detach"])
    assert not is_compose_up(["compose", "config", "--quiet"])
    assert not is_compose_up(["ps"])


def test_docker_guard_refuses_up_while_frozen(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    marker.write_text("{}\n", encoding="utf-8")
    called = False

    def execute(*_args, **_kwargs):
        nonlocal called
        called = True
        return subprocess.CompletedProcess([], 0)

    result = run_docker(
        ["compose", "up", "--detach"],
        docker=tmp_path / "docker",
        marker=marker,
        lock=tmp_path / "publisher.lock",
        execute=execute,
    )
    assert result == 75
    assert called is False


def test_docker_guard_runs_compose_up_when_unfrozen(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def execute(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    docker = tmp_path / "docker"
    result = run_docker(
        ["compose", "up", "--detach"],
        docker=docker,
        marker=tmp_path / "marker",
        lock=tmp_path / "publisher.lock",
        execute=execute,
    )
    assert result == 0
    assert commands == [[str(docker), "compose", "up", "--detach"]]
