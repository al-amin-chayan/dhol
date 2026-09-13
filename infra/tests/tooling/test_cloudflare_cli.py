"""Operator boundary: no CI, no secret exports, private external inputs, readonly source."""

from pathlib import Path
import os
import json
import shutil
import shlex
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def cli(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    (scripts / "lib").mkdir(parents=True)
    for path in ["scripts/cloudflare", "scripts/lib/common.sh"]:
        shutil.copyfile(ROOT / path, repo / path)
    (scripts / "controller").write_text(
        '#!/bin/sh\nprintf "image_id=sha256:test-only-locked-image\\n"\n'
    )
    (scripts / "controller").chmod(0o755)
    binary = tmp_path / "bin"
    binary.mkdir()
    capture = tmp_path / "args.json"
    docker = binary / "docker"
    docker.write_text(
        '#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ["TEST_DOCKER_ARGS"],"w").write(json.dumps(sys.argv[1:]))\n'
    )
    docker.chmod(0o755)
    inputs = []
    for filename in ["credentials.env", "founder.age", "break-glass.age"]:
        path = tmp_path / filename
        path.write_text("test-only-private-input")
        path.chmod(0o600)
        inputs.append(path)
    env = {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "TEST_DOCKER_ARGS": str(capture),
        "CI": "",
        "GITHUB_ACTIONS": "",
    }

    def invoke(operation="plan", paths=None, extra=None, environment=None):
        paths = paths or inputs
        shell = (
            "function "
            + shlex.quote(str(scripts / "controller"))
            + "() { printf 'image_id=sha256:test-only-locked-image\\n'; }; "
        )
        shell += 'docker() { python3 -c \'import json,os,sys; open(os.environ["TEST_DOCKER_ARGS"],"w").write(json.dumps(sys.argv[1:]))\' "$@"; }; '
        shell += "source " + shlex.quote(str(scripts / "cloudflare")) + ' "$@"'
        args = [
            "bash",
            "-c",
            shell,
            "test-only",
            operation,
            "--credentials",
            str(paths[0]),
            "--founder-key",
            str(paths[1]),
            "--break-glass-key",
            str(paths[2]),
            "--confirm",
            "cloudflare-control-plane",
        ] + (extra or [])
        return subprocess.run(
            args, env={**env, **(environment or {})}, capture_output=True, text=True
        )

    return invoke, inputs, capture, repo


def test_finite_readonly_controller_keeps_secrets_out_of_arguments(cli):
    invoke, _, capture, repo = cli
    result = invoke()
    assert result.returncode == 0, result.stderr
    args = json.loads(capture.read_text())
    assert "--read-only" in args and "--rm" in args
    assert "ALL" in args and "no-new-privileges" in args
    assert any(str(repo) + ":/workspace:ro" == item for item in args)
    assert any("/run/bootstrap.env:ro" in item for item in args)
    assert any("/providers:rw,nosuid,nodev,exec,size=" in item for item in args)
    assert "test-only-private-input" not in str(args) + result.stdout + result.stderr


@pytest.mark.parametrize("name", ["CI", "GITHUB_ACTIONS"])
def test_ci_cannot_operate_cloudflare(cli, name):
    invoke, _, capture, _ = cli
    assert invoke(environment={name: "true"}).returncode != 0 and not capture.exists()


@pytest.mark.parametrize(
    "kind", ["public-mode", "symlink", "repo-input", "github-profile"]
)
def test_unsafe_inputs_fail_before_controller(cli, kind):
    invoke, inputs, capture, repo = cli
    paths = list(inputs)
    if kind == "public-mode":
        paths[0].chmod(0o644)
    elif kind == "symlink":
        path = inputs[0].parent / "alias"
        path.symlink_to(inputs[0])
        paths[0] = path
    elif kind == "repo-input":
        path = repo / "secret"
        path.write_text("test-only")
        path.chmod(0o600)
        paths[0] = path
    else:
        path = inputs[0].parent / "github-agent-apps" / "claude.env"
        path.parent.mkdir()
        path.write_text("test-only-not-an-identity")
        path.chmod(0o600)
        paths[0] = path
    assert invoke(paths=paths).returncode != 0 and not capture.exists()


def test_unknown_operation_and_symlink_output_rejected(cli):
    invoke, _, capture, repo = cli
    assert invoke(operation="destroy").returncode != 0
    (repo / ".artifacts").symlink_to(repo / "scripts", target_is_directory=True)
    assert invoke().returncode != 0 and not capture.exists()
    assert not (repo / "scripts/cloudflare.json").exists()


@pytest.mark.parametrize("alias", [False, True])
def test_duplicate_canonical_operator_inputs_rejected(cli, alias):
    invoke, inputs, capture, _ = cli
    paths = list(inputs)
    paths[2] = inputs[1].parent / "." / inputs[1].name if alias else inputs[1]
    assert invoke(paths=paths).returncode != 0
    assert not capture.exists()
