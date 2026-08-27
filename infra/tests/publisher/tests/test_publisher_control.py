from __future__ import annotations

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
        if "select status from current_executions" in command[-1]:
            value = self.status_values.pop(0) if self.status_values else "absent"
            return subprocess.CompletedProcess(command, 0, f"{value}\n" if value != "absent" else "", "")
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
    runner = FakeRunner(["1", "1", "2"])
    assert terminate_workflow(runner, "fixture-post", 5) == "2"
    terminate = next(command for command in runner.commands if "terminate" in command)
    assert "post_fixture-post" in terminate


def test_already_stopped_workflow_is_idempotent() -> None:
    runner = FakeRunner(["2"])
    assert terminate_workflow(runner, "fixture-post", 1) == "2"
    assert not any("terminate" in command for command in runner.commands)
