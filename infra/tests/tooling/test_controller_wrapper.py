"""Regression coverage for the host-side locked-controller wrapper."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "scripts/controller"
PLAN = ROOT / "scripts/infra-plan"


def function_body(script: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{(.*?)^\}}", script, re.S | re.M)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(1)


def test_offline_controller_attaches_standard_input() -> None:
    """Piped plan transcripts and private-key inputs must reach the container."""

    script = CONTROLLER.read_text(encoding="utf-8")
    run_controller = function_body(script, "run_controller")

    assert "--interactive" in run_controller


def test_ssh_controller_intentionally_does_not_attach_standard_input() -> None:
    """No production exec-ssh caller streams a transcript or secret on stdin."""

    script = CONTROLLER.read_text(encoding="utf-8")
    assert "--interactive" not in function_body(script, "run_ssh_controller")


def test_compose_scope_iteration_survives_a_stdin_consuming_controller() -> None:
    """Every owned stack must contribute one compose-render pair to the plan."""

    plan = PLAN.read_text(encoding="utf-8")
    assert "while IFS= read -r stack_id <&3; do" in plan
    assert "done 3<<EOF" in plan

    completed = subprocess.run(
        [
            "bash",
            "-c",
            """
set -eu
COMPOSE_STACKS='stack-a
stack-b'
COMPOSE_RENDER_ARGS=()
while IFS= read -r stack_id <&3; do
  python3 -c 'import sys; sys.stdin.read()'
  COMPOSE_RENDER_ARGS+=(--compose-render "$stack_id=digest")
done 3<<EOF
$COMPOSE_STACKS
EOF
printf '%s\n' "${COMPOSE_RENDER_ARGS[@]}"
""",
        ],
        input="controller input that may be consumed",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "--compose-render",
        "stack-a=digest",
        "--compose-render",
        "stack-b=digest",
    ]
