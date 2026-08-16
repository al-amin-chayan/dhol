from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER_DIR = REPO_ROOT / "infra/controller"
sys.path.insert(0, str(CONTROLLER_DIR))

from review_gate import AREA_LABEL_PREFIX, REVIEW_LABELS, WORKFLOW_BLOCKER_LABELS  # noqa: E402


SCRIPT = REPO_ROOT / "scripts/configure-github-rulesets.py"
SPEC = importlib.util.spec_from_file_location("configure_github_rulesets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def rule(ruleset: dict, kind: str) -> dict:
    return next(item for item in ruleset["rules"] if item["type"] == kind)


def test_develop_first_configuration_is_complete() -> None:
    configuration = MODULE.desired_configuration()
    assert configuration["repository_settings"] == {
        "default_branch": "develop",
        "allow_merge_commit": True,
        "allow_squash_merge": True,
        "allow_rebase_merge": False,
        "allow_auto_merge": True,
        "delete_branch_on_merge": True,
    }
    assert configuration["actions_permissions"] == {
        "enabled": True,
        "allowed_actions": "all",
        "sha_pinning_required": True,
    }
    managed_labels = {label["name"] for label in configuration["labels"]["labels"]}
    assert managed_labels == {
        "review:requested",
        "review:changes-requested",
        "review:ready-for-ci",
        "area:content",
        "area:infra",
        "area:operations",
        "area:pipeline",
        "area:tooling",
        "blocked",
        "decision",
        "production-risk",
    }
    assert REVIEW_LABELS | WORKFLOW_BLOCKER_LABELS <= managed_labels
    assert any(name.startswith(AREA_LABEL_PREFIX) for name in managed_labels)
    review_labels = {
        label["name"]: label for label in configuration["labels"]["labels"]
        if label["name"].startswith("review:")
    }
    assert review_labels["review:requested"]["color"] == "FBCA04"
    assert review_labels["review:changes-requested"]["color"] == "D93F0B"
    assert configuration["labels"]["renames"] == {
        "review:approved": "review:ready-for-ci"
    }
    rulesets = {item["conditions"]["ref_name"]["include"][0]: item for item in configuration["rulesets"]}
    assert set(rulesets) == {"refs/heads/develop", "refs/heads/main"}


def test_both_rulesets_require_cross_review_and_controller_checks() -> None:
    for ruleset in MODULE.desired_configuration()["rulesets"]:
        assert ruleset["enforcement"] == "active"
        assert ruleset["bypass_actors"] == [
            {"actor_id": 6504305, "actor_type": "User", "bypass_mode": "pull_request"}
        ]
        assert {item["type"] for item in ruleset["rules"]} >= {
            "deletion",
            "non_fast_forward",
            "pull_request",
            "required_status_checks",
        }
        pull_request = rule(ruleset, "pull_request")["parameters"]
        assert pull_request["required_approving_review_count"] == 1
        assert pull_request["dismiss_stale_reviews_on_push"] is True
        assert pull_request["require_last_push_approval"] is True
        assert pull_request["required_review_thread_resolution"] is True
        checks = rule(ruleset, "required_status_checks")["parameters"]["required_status_checks"]
        assert checks == [
            {"context": "Cross-review gate", "integration_id": 15368},
            {"context": "Controller check (linux/amd64)", "integration_id": 15368},
            {"context": "Controller check (linux/arm64)", "integration_id": 15368},
        ]


def test_only_main_requires_an_up_to_date_base() -> None:
    rulesets = {
        item["conditions"]["ref_name"]["include"][0]: item
        for item in MODULE.desired_configuration()["rulesets"]
    }
    assert rule(rulesets["refs/heads/develop"], "required_status_checks")["parameters"][
        "strict_required_status_checks_policy"
    ] is False
    assert rule(rulesets["refs/heads/main"], "required_status_checks")["parameters"][
        "strict_required_status_checks_policy"
    ] is True


def test_merge_methods_preserve_develop_to_main_ancestry() -> None:
    rulesets = {item["conditions"]["ref_name"]["include"][0]: item for item in MODULE.desired_configuration()["rulesets"]}
    develop_methods = rule(rulesets["refs/heads/develop"], "pull_request")["parameters"][
        "allowed_merge_methods"
    ]
    main_methods = rule(rulesets["refs/heads/main"], "pull_request")["parameters"][
        "allowed_merge_methods"
    ]
    assert develop_methods == ["squash", "merge"]
    assert main_methods == ["merge"]


def test_live_empty_required_reviewers_normalizes_to_desired() -> None:
    desired = MODULE.desired_configuration()["rulesets"][0]
    live = copy.deepcopy(desired)
    rule(live, "pull_request")["parameters"]["required_reviewers"] = []
    live["id"] = 123
    assert MODULE.normalized_ruleset(live) == MODULE.normalized_ruleset(desired)


def test_unchanged_ruleset_does_not_issue_a_write(monkeypatch, capsys) -> None:
    desired = MODULE.desired_configuration()["rulesets"][0]
    live = copy.deepcopy(desired)
    rule(live, "pull_request")["parameters"]["required_reviewers"] = []
    calls: list[tuple[str, str]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path))
        if path == "rulesets":
            return [{"name": desired["name"], "id": 123}]
        if path == "rulesets/123":
            return live
        raise AssertionError(f"unexpected request: {method} {path} {payload}")

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.upsert_rulesets("token", "owner/repository", [desired])
    assert calls == [("GET", "rulesets"), ("GET", "rulesets/123")]
    assert capsys.readouterr().out == f"unchanged: {desired['name']}\n"


def test_apply_mints_one_token_for_the_whole_invocation(monkeypatch) -> None:
    configuration = MODULE.desired_configuration()
    tokens: list[str] = []

    def mint():
        tokens.append("token")
        return "token"

    def repository_request(token, repository, method, path, payload=None):
        assert token == "token"
        assert method == "GET"
        assert path == ""
        return configuration["repository_settings"]

    monkeypatch.setattr(MODULE, "mint_token", mint)
    monkeypatch.setattr(MODULE, "ensure_develop", lambda token, repository: None)
    monkeypatch.setattr(MODULE, "github_request", repository_request)
    monkeypatch.setattr(
        MODULE,
        "converge_actions_permissions",
        lambda token, repository, actions_permissions: None,
    )
    monkeypatch.setattr(MODULE, "converge_labels", lambda token, repository, labels: None)
    monkeypatch.setattr(MODULE, "upsert_rulesets", lambda token, repository, rulesets: None)
    MODULE.apply("owner/repository", configuration)
    assert tokens == ["token"]


def test_unchanged_actions_permissions_do_not_issue_a_write(monkeypatch, capsys) -> None:
    desired = MODULE.desired_configuration()["actions_permissions"]
    calls: list[tuple[str, str, dict | None]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path, payload))
        return {**desired, "selected_actions_url": "https://api.github.test/selected-actions"}

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.converge_actions_permissions("token", "owner/repository", desired)
    assert calls == [("GET", "actions/permissions", None)]
    assert capsys.readouterr().out == "unchanged: Actions permissions\n"


def test_drifted_actions_permissions_are_updated(monkeypatch, capsys) -> None:
    desired = MODULE.desired_configuration()["actions_permissions"]
    calls: list[tuple[str, str, dict | None]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {**desired, "sha_pinning_required": False}
        return None

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.converge_actions_permissions("token", "owner/repository", desired)
    assert calls == [
        ("GET", "actions/permissions", None),
        ("PUT", "actions/permissions", desired),
    ]
    assert capsys.readouterr().out == "updated: Actions permissions\n"


def test_labels_are_renamed_and_converged_without_losing_assignments(monkeypatch, capsys) -> None:
    desired = MODULE.desired_configuration()["labels"]
    ready = next(label for label in desired["labels"] if label["name"] == "review:ready-for-ci")
    live = [label for label in desired["labels"] if label["name"] != "review:ready-for-ci"]
    live.append({"name": "review:approved", "color": "123456", "description": "old"})
    calls: list[tuple[str, str, dict | None]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return live
        if method == "PATCH":
            return ready
        return None

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.converge_labels("token", "owner/repository", desired)
    rename_payload = {
        "new_name": ready["name"],
        "color": ready["color"],
        "description": ready["description"],
    }
    assert calls == [
        ("GET", "labels?per_page=100", None),
        ("PATCH", "labels/review%3Aapproved", rename_payload),
    ]
    assert set(rename_payload) == {"new_name", "color", "description"}
    assert "renamed label: review:approved -> review:ready-for-ci" in capsys.readouterr().out


def test_unconfirmed_label_rename_fails_closed(monkeypatch) -> None:
    desired = MODULE.desired_configuration()["labels"]
    ready = next(label for label in desired["labels"] if label["name"] == "review:ready-for-ci")
    old = {"name": "review:approved", "color": "123456", "description": "old"}

    def request(token, repository, method, path, payload=None):
        if method == "GET":
            return [old]
        if method == "PATCH":
            return {**ready, "name": "review:approved"}
        return None

    monkeypatch.setattr(MODULE, "github_request", request)
    with pytest.raises(RuntimeError, match="did not confirm label rename"):
        MODULE.converge_labels("token", "owner/repository", desired)


def test_drifted_label_update_uses_only_the_github_contract_fields(monkeypatch) -> None:
    desired = MODULE.desired_configuration()["labels"]
    requested = next(label for label in desired["labels"] if label["name"] == "review:requested")
    live = [dict(label) for label in desired["labels"]]
    next(label for label in live if label["name"] == "review:requested")["color"] = "000000"
    calls: list[tuple[str, str, dict | None]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return live
        if method == "PATCH":
            return requested
        return None

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.converge_labels("token", "owner/repository", desired)
    assert calls == [
        ("GET", "labels?per_page=100", None),
        (
            "PATCH",
            "labels/review%3Arequested",
            {"color": requested["color"], "description": requested["description"]},
        ),
    ]


def test_superseded_label_assignments_are_migrated_before_removal(
    monkeypatch, capsys
) -> None:
    desired = MODULE.desired_configuration()["labels"]
    live = [*desired["labels"], {"name": "review:approved", "color": "123456"}]
    calls: list[tuple[str, str]] = []

    def request(token, repository, method, path, payload=None):
        calls.append((method, path))
        if path == "labels?per_page=100":
            return live
        if path.startswith("issues?state=all"):
            return [{"number": 17}]
        return None

    monkeypatch.setattr(MODULE, "github_request", request)
    MODULE.converge_labels("token", "owner/repository", desired)
    assert calls == [
        ("GET", "labels?per_page=100"),
        (
            "GET",
            "issues?state=all&labels=review%3Aapproved&per_page=100&page=1",
        ),
        ("POST", "issues/17/labels"),
        ("DELETE", "labels/review%3Aapproved"),
    ]
    assert "removed superseded label: review:approved" in capsys.readouterr().out
