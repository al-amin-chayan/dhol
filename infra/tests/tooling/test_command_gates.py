"""Argument and authorization gates that must fail before any host is contacted.

Every case here stops well before the command builds the controller or opens a
connection, so the suite runs inside the pinned controller with no Docker socket,
no network, and no production input. Nothing here depends on a committed host
contract: these gates must hold for any argument, including a host that owns no
contract at all.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "scripts/infra-plan"
APPLY = ROOT / "scripts/infra-apply"
VERIFY = ROOT / "scripts/infra-verify"

ANY_HOST = "publish-1"
ANY_TAG = "infra-prod-20260823-1"


def local_inputs(tmp_path: Path) -> tuple[str, str]:
    """Create connection inputs that are structurally valid but reach nothing."""

    identity = tmp_path / "id_target"
    identity.write_text("fixture private key material\n", encoding="utf-8")
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("fixture-host ssh-ed25519 AAAAC3NzaC1lZDI1NTE5\n", encoding="utf-8")
    return str(identity), str(known_hosts)


def run(command: list, **kwargs) -> subprocess.CompletedProcess:
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/controller-home"}
    environment.update(kwargs.pop("env", {}))
    return subprocess.run(
        [str(part) for part in command],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=environment,
        **kwargs,
    )


@pytest.mark.parametrize("command", [PLAN, APPLY, VERIFY])
def test_help_is_available_from_any_directory(command: Path, tmp_path: Path) -> None:
    completed = run([command, "--help"], cwd=tmp_path)
    assert completed.returncode == 0
    assert "Usage:" in completed.stdout


@pytest.mark.parametrize("command", [PLAN, APPLY, VERIFY])
def test_unknown_arguments_are_refused(command: Path) -> None:
    completed = run([command, "--limit", ANY_HOST, "--danger"])
    assert completed.returncode != 0
    assert "unexpected argument" in completed.stderr


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (PLAN, "--address is required"),
        (VERIFY, "--address is required"),
        (APPLY, "--release is required"),
    ],
)
def test_incomplete_invocations_stop_before_any_connection(command: Path, expected: str) -> None:
    completed = run([command, "--limit", ANY_HOST])
    assert completed.returncode != 0
    assert expected in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
@pytest.mark.parametrize("limit", ["publisher", "core", "baseline_targets", "all", "unknown-host"])
def test_a_group_or_unknown_name_is_never_accepted_as_a_host_limit(
    command: Path, limit: str, tmp_path: Path
) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            command,
            "--limit",
            limit,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "no committed baseline contract" in completed.stderr


@pytest.mark.parametrize("variable", ["GITHUB_ACTIONS", "CI"])
def test_production_commands_never_run_in_ci(variable: str, tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    arguments = [
        "--limit",
        ANY_HOST,
        "--address",
        "203.0.113.9",
        "--identity-file",
        identity,
        "--known-hosts-file",
        known_hosts,
    ]
    plan = run([PLAN, *arguments], env={variable: "true"})
    assert plan.returncode != 0
    assert "never permitted in CI" in plan.stderr

    verify = run([VERIFY, *arguments], env={variable: "true"})
    assert verify.returncode != 0
    assert "never permitted in CI" in verify.stderr

    applied = run(
        [APPLY, *arguments, "--release", ANY_TAG, "--approved-plan", "/tmp/plan.yml"],
        env={variable: "true"},
    )
    assert applied.returncode != 0
    assert "never permitted in CI" in applied.stderr


def test_apply_refuses_a_non_interactive_session(tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            APPLY,
            "--limit",
            ANY_HOST,
            "--release",
            ANY_TAG,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            known_hosts,
            "--approved-plan",
            "/tmp/plan.yml",
        ]
    )
    assert completed.returncode != 0
    assert "interactive terminal" in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
def test_identity_material_inside_the_repository_is_refused(
    command: Path, tmp_path: Path
) -> None:
    _, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            str(ROOT / "infra/id_target"),
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
def test_an_empty_known_hosts_file_is_refused(command: Path, tmp_path: Path) -> None:
    identity, _ = local_inputs(tmp_path)
    known_hosts = tmp_path / "empty_known_hosts"
    known_hosts.write_text("", encoding="utf-8")
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            str(known_hosts),
        ]
    )
    assert completed.returncode != 0
    assert "empty" in completed.stderr


def test_a_missing_identity_file_is_refused(tmp_path: Path) -> None:
    _, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            PLAN,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            str(tmp_path / "absent"),
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "identity file is unavailable" in completed.stderr


def test_plan_refuses_an_unsupported_stage(tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            PLAN,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            known_hosts,
            "--stage",
            "production",
        ]
    )
    assert completed.returncode != 0
    assert "--stage must be bootstrap or converged" in completed.stderr


@pytest.mark.parametrize("suffix", ["../escape", "Upper", "with space", "semi;colon"])
def test_verify_refuses_an_unsafe_artifact_suffix(suffix: str, tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            VERIFY,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            known_hosts,
            "--artifact-suffix",
            suffix,
        ]
    )
    assert completed.returncode != 0
    assert "lowercase letters" in completed.stderr


# --- Repository-contained private key material, resolved rather than compared ---

@pytest.mark.parametrize("command", [PLAN, VERIFY])
@pytest.mark.parametrize(
    "identity",
    [
        ".artifacts/id_target",
        "infra/../.artifacts/id_target",
        "./scripts/../.artifacts/nested/id_target",
        "infra/inventories/id_target",
    ],
)
def test_a_relative_or_traversing_repository_identity_is_refused(
    command: Path, identity: str, tmp_path: Path
) -> None:
    """A lexical prefix check would pass every one of these."""

    _, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            identity,
            "--known-hosts-file",
            known_hosts,
        ],
        cwd=ROOT,
    )
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
def test_an_identity_reached_through_a_symlinked_parent_is_refused(
    command: Path, tmp_path: Path
) -> None:
    _, known_hosts = local_inputs(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(ROOT)
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            str(link / ".artifacts" / "id_target"),
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
def test_a_symlinked_identity_file_is_refused(command: Path, tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    link = tmp_path / "linked_id"
    link.symlink_to(identity)
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            str(link),
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "must not be a symbolic link" in completed.stderr


@pytest.mark.parametrize("command", [PLAN, VERIFY])
def test_a_directory_is_not_accepted_as_an_identity(command: Path, tmp_path: Path) -> None:
    _, known_hosts = local_inputs(tmp_path)
    directory = tmp_path / "keydir"
    directory.mkdir()
    completed = run(
        [
            command,
            "--limit",
            ANY_HOST,
            "--address",
            "203.0.113.9",
            "--identity-file",
            str(directory),
            "--known-hosts-file",
            known_hosts,
        ]
    )
    assert completed.returncode != 0
    assert "must be a regular file" in completed.stderr


def test_controller_exec_ssh_refuses_a_repository_relative_identity() -> None:
    controller = ROOT / "scripts/controller"
    completed = run(
        [
            controller,
            "exec-ssh",
            "--known-hosts",
            ".artifacts/known_hosts",
            "--identity",
            ".artifacts/id_target",
            "--confirm",
            "production-host",
            "true",
        ],
        cwd=ROOT,
    )
    assert completed.returncode != 0
    assert "identity file inside the repository" in completed.stderr


def test_controller_exec_ssh_refuses_an_identity_behind_a_symlinked_parent(
    tmp_path: Path,
) -> None:
    controller = ROOT / "scripts/controller"
    link = tmp_path / "link"
    link.symlink_to(ROOT)
    completed = run(
        [
            controller,
            "exec-ssh",
            "--known-hosts",
            ".artifacts/known_hosts",
            "--identity",
            str(link / ".artifacts" / "id_target"),
            "--confirm",
            "production-host",
            "true",
        ]
    )
    assert completed.returncode != 0
    assert "identity file inside the repository" in completed.stderr


# --- Stage lifecycle ---

@pytest.mark.parametrize("command", [PLAN, APPLY])
def test_an_unsupported_stage_is_refused(command: Path, tmp_path: Path) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    arguments = [
        command,
        "--limit",
        ANY_HOST,
        "--address",
        "203.0.113.9",
        "--identity-file",
        identity,
        "--known-hosts-file",
        known_hosts,
        "--stage",
        "first-contact",
    ]
    if command == APPLY:
        arguments += ["--release", ANY_TAG, "--approved-plan", "/tmp/plan.yml"]
    completed = run(arguments)
    assert completed.returncode != 0
    assert "--stage must be bootstrap or converged" in completed.stderr


# --- The renderer CLI every command actually invokes (PR44-B01) ---

RENDER = ROOT / "infra/inventories/host_baseline.py"


def render_cli(*extra: str) -> subprocess.CompletedProcess:
    """Exercise the command line the wrappers use, not the Python function.

    This runs under the interpreter the suite runs under, because the renderer
    needs the controller's PyYAML rather than a bare system Python.
    """

    return subprocess.run(
        [
            sys.executable, str(RENDER), "--root", str(ROOT), "render",
            "--limit", ANY_HOST,
            "--address", "203.0.113.20",
            "--stage", "converged",
            "--identity-file", "/tmp/id",
            "--known-hosts-file", "/tmp/kh",
            "--output", "-",
            *extra,
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.parametrize("transport", ["auto", "public", "tunnel"])
def test_the_render_cli_accepts_every_transport(transport: str) -> None:
    """Regression: --transport was wired into the wrappers but never registered.

    A missing option makes argparse exit 2 before any rendering, so every
    production command stopped. Asserting on the parser, not on the function,
    is what catches that.
    """

    completed = render_cli("--transport", transport)
    assert "unrecognized arguments" not in completed.stderr
    assert "--transport" not in completed.stderr


def test_the_render_cli_refuses_an_unknown_transport() -> None:
    completed = render_cli("--transport", "sideways")
    assert completed.returncode != 0
    assert "invalid choice" in completed.stderr


def test_the_render_cli_still_works_without_a_transport() -> None:
    completed = render_cli()
    assert "unrecognized arguments" not in completed.stderr


@pytest.mark.parametrize("subcommand", [["check"], ["contract", "--limit", ANY_HOST]])
def test_other_render_subcommands_remain_invocable(subcommand: list) -> None:
    completed = subprocess.run(
        [sys.executable, str(RENDER), "--root", str(ROOT), *subcommand],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert "unrecognized arguments" not in completed.stderr


@pytest.mark.parametrize("command", [PLAN, APPLY, VERIFY])
def test_an_unknown_transport_is_refused_by_every_wrapper(
    command: Path, tmp_path: Path
) -> None:
    identity, known_hosts = local_inputs(tmp_path)
    arguments = [
        command, "--limit", ANY_HOST, "--address", "203.0.113.9",
        "--identity-file", identity, "--known-hosts-file", known_hosts,
        "--transport", "sideways",
    ]
    if command == APPLY:
        arguments += ["--release", ANY_TAG, "--approved-plan", "/tmp/plan.yml"]
    completed = run(arguments)
    assert completed.returncode != 0
    assert "--transport must be auto, public, or tunnel" in completed.stderr


def test_a_wireguard_key_export_inside_the_repository_is_refused(tmp_path: Path) -> None:
    """A key export under .artifacts/ would leave private material in the checkout.

    Only infra-plan is exercised: infra-apply refuses a non-interactive session
    before it reaches input validation, which its own test already covers.
    """

    identity, known_hosts = local_inputs(tmp_path)
    completed = run(
        [
            PLAN, "--limit", ANY_HOST, "--address", "203.0.113.9",
            "--identity-file", identity, "--known-hosts-file", known_hosts,
            "--wireguard-key-file", str(ROOT / ".artifacts/wg.key"),
        ]
    )
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr
