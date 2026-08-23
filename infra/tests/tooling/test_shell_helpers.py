"""Coverage for the shared shell helpers that guard evidence and key material."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "scripts/lib/common.sh"


def call(function: str, *arguments: str) -> subprocess.CompletedProcess:
    script = f'source "{COMMON}"\n{function} "$@"\n'
    return subprocess.run(
        ["bash", "-c", script, "bash", *arguments],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp"},
    )


@pytest.mark.parametrize(
    "candidate",
    [
        ".artifacts/id_target",
        "infra/../.artifacts/id_target",
        "./scripts/../.artifacts/nested/id_target",
        "absent/deeper/id_target",
    ],
)
def test_relative_and_traversing_paths_resolve_into_the_repository(candidate: str) -> None:
    result = call("dholbeat_canonical_path", candidate)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith(str(ROOT.resolve()))


def test_a_path_outside_the_repository_stays_outside(tmp_path: Path) -> None:
    result = call("dholbeat_canonical_path", str(tmp_path / "id_target"))
    assert result.returncode == 0, result.stderr
    assert not result.stdout.strip().startswith(str(ROOT.resolve()) + "/")


def test_an_empty_path_is_refused() -> None:
    result = call("dholbeat_canonical_path", "")
    assert result.returncode != 0
    assert "cannot resolve an empty path" in result.stderr


def test_evidence_scan_reports_a_leaked_literal(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "plan.yml").write_text("connected to 203.0.113.44\n", encoding="utf-8")
    result = call("dholbeat_assert_absent_from_evidence", str(evidence), "203.0.113.44")
    assert result.returncode != 0
    assert "leaked into evidence" in result.stderr


def test_evidence_scan_passes_when_the_literal_is_absent(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "plan.yml").write_text("connected to <redacted-address>\n", encoding="utf-8")
    result = call("dholbeat_assert_absent_from_evidence", str(evidence), "203.0.113.44")
    assert result.returncode == 0, result.stderr


def test_evidence_scan_finds_a_literal_in_a_nested_file(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    (evidence / "nested").mkdir(parents=True)
    (evidence / "nested" / "known_hosts").write_text(
        "203.0.113.44 ssh-ed25519 AAAA\n", encoding="utf-8"
    )
    result = call("dholbeat_assert_absent_from_evidence", str(evidence), "203.0.113.44")
    assert result.returncode != 0


def test_evidence_scan_ignores_empty_literals(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "plan.yml").write_text("anything\n", encoding="utf-8")
    assert call("dholbeat_assert_absent_from_evidence", str(evidence), "").returncode == 0
