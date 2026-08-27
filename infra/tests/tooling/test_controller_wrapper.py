"""Regression coverage for the host-side locked-controller wrapper."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "scripts/controller"


def test_offline_controller_attaches_standard_input() -> None:
    """Piped plan transcripts and private-key inputs must reach the container."""

    script = CONTROLLER.read_text(encoding="utf-8")
    run_controller = script.split("run_controller() {", 1)[1].split(
        "\n}\n\nrun_ssh_controller() {", 1
    )[0]

    assert re.search(r"docker run --rm \\\n\s+--interactive \\", run_controller)
