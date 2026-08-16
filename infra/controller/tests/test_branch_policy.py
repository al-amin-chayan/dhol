from __future__ import annotations

from pathlib import Path
import sys


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROLLER_DIR))

from branch_policy import validate_pull_request_route  # noqa: E402


def test_non_pull_request_event_is_not_routed() -> None:
    assert validate_pull_request_route("push", "", "") == []


def test_github_actions_requires_event_propagation() -> None:
    findings = validate_pull_request_route("", "", "", github_actions=True)
    assert findings == ["GitHub Actions did not propagate GITHUB_EVENT_NAME into the controller"]


def test_feature_pull_request_targets_develop() -> None:
    assert validate_pull_request_route("pull_request", "develop", "codex/wp00") == []


def test_main_back_merge_may_target_develop() -> None:
    assert validate_pull_request_route("pull_request", "develop", "main") == []


def test_develop_is_the_only_main_promotion_source() -> None:
    assert validate_pull_request_route("pull_request", "main", "develop") == []


def test_feature_branch_cannot_bypass_develop() -> None:
    findings = validate_pull_request_route("pull_request", "main", "codex/wp00")
    assert findings == ["pull requests into main must come from develop, not codex/wp00"]


def test_other_pull_request_base_is_rejected() -> None:
    findings = validate_pull_request_route("pull_request", "release/v1", "develop")
    assert findings == ["pull request base must be develop or main, not release/v1"]


def test_pull_request_refs_are_required() -> None:
    findings = validate_pull_request_route("pull_request", "", "")
    assert findings == ["pull request event is missing GITHUB_BASE_REF or GITHUB_HEAD_REF"]
