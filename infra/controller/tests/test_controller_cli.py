from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = REPO_ROOT / "scripts/controller"


def fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    binary_dir = Path(__file__).resolve().parent / "fixtures/bin"
    log = tmp_path / "docker.log"
    return binary_dir, log


def test_help_resolves_root_from_any_directory(tmp_path: Path) -> None:
    result = subprocess.run([CONTROLLER, "--help"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0
    assert "scripts/controller" in result.stdout


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
