from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
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
        "delete_branch_on_merge": True,
    }
    assert configuration["actions_permissions"] == {
        "enabled": True,
        "allowed_actions": "all",
        "sha_pinning_required": True,
    }
    rulesets = {item["conditions"]["ref_name"]["include"][0]: item for item in configuration["rulesets"]}
    assert set(rulesets) == {"refs/heads/develop", "refs/heads/main"}


def test_both_rulesets_require_cross_review_and_controller_checks() -> None:
    for ruleset in MODULE.desired_configuration()["rulesets"]:
        assert ruleset["enforcement"] == "active"
        assert ruleset["bypass_actors"] == []
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
            {"context": "Controller check (linux/amd64)", "integration_id": 15368},
            {"context": "Controller check (linux/arm64)", "integration_id": 15368},
        ]


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
