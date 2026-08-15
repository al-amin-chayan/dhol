from __future__ import annotations

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
