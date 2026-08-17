from __future__ import annotations

import re
from pathlib import Path
import subprocess
import time


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts/eof-marker.sh"
MARKER_RE = re.compile(
    r"^--- EOF @ [A-Z][a-z]{2} [0-9]{2}, [0-9]{4} \| "
    r"(?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM) \| "
    r"Duration: (?:[0-9]+s|[0-9]+m [0-5][0-9]s|unavailable) \| "
    r"Status: (?:DONE|IN PROGRESS|BLOCKED|NEEDS HUMAN ACTION) ---$"
)


def run_marker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def test_start_returns_measured_epoch() -> None:
    before = int(time.time())
    completed = run_marker("start")
    after = int(time.time())
    assert before <= int(completed.stdout.strip()) <= after


def test_finish_renders_exact_subminute_marker() -> None:
    completed = run_marker("finish", "--start", str(int(time.time())), "--status", "DONE")
    marker = completed.stdout.strip()
    assert MARKER_RE.fullmatch(marker)
    assert re.search(r"Duration: [0-5]s \| Status: DONE", marker)


def test_finish_renders_multiminute_marker() -> None:
    completed = run_marker(
        "finish",
        "--start",
        str(int(time.time()) - 252),
        "--status",
        "IN PROGRESS",
    )
    marker = completed.stdout.strip()
    assert MARKER_RE.fullmatch(marker)
    assert re.search(r"Duration: 4m 1[2-4]s \| Status: IN PROGRESS", marker)


def test_finish_without_start_reports_unavailable_duration() -> None:
    completed = run_marker("finish", "--status", "NEEDS HUMAN ACTION")
    marker = completed.stdout.strip()
    assert MARKER_RE.fullmatch(marker)
    assert "Duration: unavailable | Status: NEEDS HUMAN ACTION" in marker


def test_invalid_status_fails_without_marker() -> None:
    completed = run_marker("finish", "--status", "UNKNOWN", check=False)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "invalid or missing status" in completed.stderr
