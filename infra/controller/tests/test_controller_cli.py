from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = REPO_ROOT / "scripts/controller"
GITHUB_APP_TOKEN = REPO_ROOT / "scripts/github-app-token.sh"
GITHUB_APP_GIT = REPO_ROOT / "scripts/github-app-git"
COMMON = REPO_ROOT / "scripts/lib/common.sh"


def fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    binary_dir = Path(__file__).resolve().parent / "fixtures/bin"
    log = tmp_path / "docker.log"
    return binary_dir, log


def test_help_resolves_root_from_any_directory(tmp_path: Path) -> None:
    result = subprocess.run([CONTROLLER, "--help"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0
    assert "scripts/controller" in result.stdout


def test_controller_propagates_complete_github_event_context() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    for variable in ("GITHUB_ACTIONS", "GITHUB_EVENT_NAME", "GITHUB_BASE_REF", "GITHUB_HEAD_REF"):
        assert f"--env {variable}" in source


def yaml_scalar(path: Path, key: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; dholbeat_yaml_scalar "$2" "$3"',
            "bash",
            str(COMMON),
            str(path),
            key,
        ],
        text=True,
        capture_output=True,
    )


def test_yaml_scalar_reads_only_the_exact_section_and_key(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.yml"
    fixture.write_text(
        "nested:\n  local_image: wrong\ncontroller:\n  local_image: right\n",
        encoding="utf-8",
    )
    result = yaml_scalar(fixture, "controller.local_image")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "right\n"


def test_yaml_scalar_rejects_missing_or_empty_qualified_key(tmp_path: Path) -> None:
    for content in ("nested:\n  local_image: wrong\n", "controller:\n  local_image:\n"):
        fixture = tmp_path / "fixture.yml"
        fixture.write_text(content, encoding="utf-8")
        result = yaml_scalar(fixture, "controller.local_image")
        assert result.returncode != 0
        assert "missing or empty YAML scalar" in result.stderr


def test_cache_cleanup_requires_exact_confirmation(tmp_path: Path) -> None:
    binary_dir, log = fake_docker(tmp_path)
    environment = {
        **os.environ,
        "PATH": f"{binary_dir}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(log),
    }
    result = subprocess.run(
        [CONTROLLER, "cache", "cleanup"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert not log.exists()


def test_cache_cleanup_targets_only_labelled_image(tmp_path: Path) -> None:
    binary_dir, log = fake_docker(tmp_path)
    environment = {
        **os.environ,
        "PATH": f"{binary_dir}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(log),
    }
    result = subprocess.run(
        [CONTROLLER, "cache", "cleanup", "--confirm", "dholbeat-controller"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert log.exists(), f"fake Docker was not called\nstdout={result.stdout}\nstderr={result.stderr}"
    calls = log.read_text(encoding="utf-8")
    assert "image ls --filter label=io.dholbeat.controller.cache=wp00-v1" in calls
    assert "image rm project-controller-image" in calls
    assert "unrelated" not in calls


def agent_environment(**updates: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "CLAUDECODE",
            "CLAUDE_CODE_ENTRYPOINT",
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "GITHUB_AGENT_IDENTITY",
        }
    }
    environment.update(updates)
    return environment


def test_github_app_helper_infers_codex_runtime(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_TOKEN, "--whoami"],
        cwd=tmp_path,
        env=agent_environment(CODEX_THREAD_ID="test-thread"),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "codex\n"


def test_github_app_helper_uses_reviewer_runtime_not_lane_owner(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_TOKEN, "--whoami"],
        cwd=tmp_path,
        env=agent_environment(CLAUDECODE="1"),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "claude\n"


def test_github_app_helper_rejects_ambiguous_runtime(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_TOKEN, "--whoami"],
        cwd=tmp_path,
        env=agent_environment(CODEX_THREAD_ID="test-thread", CLAUDECODE="1"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "both Codex and Claude runtime markers are set" in result.stderr


def test_github_app_helper_does_not_accept_an_agent_argument(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_TOKEN, "claude"],
        cwd=tmp_path,
        env=agent_environment(CODEX_THREAD_ID="test-thread"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr


def test_github_app_git_rejects_ssh_before_authentication(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_GIT, "push", "git@github.com:owner/repository.git", "branch"],
        cwd=tmp_path,
        env=agent_environment(CODEX_THREAD_ID="test-thread"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "SSH GitHub remotes" in result.stderr


def test_github_app_git_requires_explicit_https_remote(tmp_path: Path) -> None:
    result = subprocess.run(
        [GITHUB_APP_GIT, "push", "origin", "branch"],
        cwd=tmp_path,
        env=agent_environment(CODEX_THREAD_ID="test-thread"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "explicit https://github.com" in result.stderr
