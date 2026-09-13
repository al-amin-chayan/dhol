from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
from pathlib import Path
import sys

import pytest

CONTROLLER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROLLER))
import promotion_policy as policy  # noqa: E402

MAIN = "1" * 40
DEVELOP = "2" * 40
HEAD = "3" * 40
TREE = "4" * 40
STATE = {"main": MAIN, "develop": DEVELOP, "synchronized": False}


def pull(ref="codex/sync-main-develop-test", base="develop"):
    return {
        "base": {"ref": base, "repo": {"full_name": "owner/repo"}},
        "head": {"ref": ref, "sha": HEAD, "repo": {"full_name": "owner/repo"}},
        "auto_merge": {"merge_method": "merge"},
    }


def commits():
    return {
        f"git/commits/{HEAD}": {"parents": [{"sha": DEVELOP}, {"sha": MAIN}], "tree": {"sha": TREE}},
        f"git/commits/{DEVELOP}": {"tree": {"sha": TREE}},
    }


def test_graph_only_sync_with_merge_method_passes():
    assert policy.findings(pull(), STATE, commits().__getitem__) == []


@pytest.mark.parametrize("method", [None, "squash", "rebase"])
def test_sync_never_accepts_squash_rebase_or_missing_method(method):
    candidate = pull()
    candidate["auto_merge"] = None if method is None else {"merge_method": method}
    assert any("merge method merge" in error for error in policy.findings(candidate, STATE, commits().__getitem__))


@pytest.mark.parametrize("parents", [[DEVELOP], [MAIN, DEVELOP], ["5" * 40, MAIN], [DEVELOP, "5" * 40]])
def test_squashed_reversed_or_stale_parents_fail(parents):
    data = commits()
    data[f"git/commits/{HEAD}"]["parents"] = [{"sha": sha} for sha in parents]
    assert any("ordered parents" in error for error in policy.findings(pull(), STATE, data.__getitem__))


def test_sync_cannot_hide_content_changes():
    data = commits()
    data[f"git/commits/{HEAD}"]["tree"]["sha"] = "5" * 40
    assert any("ancestry only" in error for error in policy.findings(pull(), STATE, data.__getitem__))


def test_fork_cannot_impersonate_sync_branch():
    candidate = pull()
    candidate["head"]["repo"]["full_name"] = "fork/repo"
    assert any("agent-owned branch" in error for error in policy.findings(candidate, STATE, commits().__getitem__))


def test_pending_sync_pauses_ordinary_integration():
    assert any("integration paused" in error for error in policy.findings(pull("codex/feature"), STATE, commits().__getitem__))
    ready = {**STATE, "synchronized": True}
    assert policy.findings(pull("codex/feature"), ready, commits().__getitem__) == []


def test_sync_is_rejected_when_already_synchronized():
    assert any("unnecessary" in error for error in policy.findings(pull(), {**STATE, "synchronized": True}, commits().__getitem__))


def test_promotion_preflight_blocks_missing_main_and_stale_head():
    candidate = pull("develop", "main")
    candidate["head"]["sha"] = DEVELOP
    assert any("promotion blocked" in error for error in policy.findings(candidate, STATE, commits().__getitem__))
    ready = {**STATE, "synchronized": True}
    assert policy.findings(candidate, ready, commits().__getitem__) == []
    candidate["head"]["sha"] = HEAD
    assert any("exact current" in error for error in policy.findings(candidate, ready, commits().__getitem__))


def test_snapshot_uses_pinned_sha_ancestry_not_commit_count():
    data = {
        "git/ref/heads/main": {"object": {"sha": MAIN}},
        "git/ref/heads/develop": {"object": {"sha": DEVELOP}},
        f"compare/{MAIN}...{DEVELOP}?per_page=1": {"merge_base_commit": {"sha": DEVELOP}, "behind_by": 0},
    }
    assert policy.snapshot(data.__getitem__) == STATE
    data[f"compare/{MAIN}...{DEVELOP}?per_page=1"]["merge_base_commit"]["sha"] = MAIN
    assert policy.snapshot(data.__getitem__)["synchronized"] is True




SCRIPT = CONTROLLER.parents[1] / "scripts/promotion"
LOADER = importlib.machinery.SourceFileLoader("promotion_cli", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
CLI = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(CLI)


def test_arm_pins_head_and_checks_bot_and_merge_method(monkeypatch):
    candidate = pull()
    candidate["user"] = {"login": "chayan-codex[bot]"}
    recorded = copy.deepcopy(candidate)
    recorded["auto_merge"]["enabled_by"] = {"login": "chayan-codex[bot]"}
    pulls = iter([candidate, recorded])
    monkeypatch.setattr(CLI, "get", lambda path: next(pulls) if path == "pulls/54" else commits()[path])
    monkeypatch.setattr(CLI, "run", lambda *args, **kwargs: "chayan-codex[bot]")
    calls = []
    monkeypatch.setattr(CLI, "gh", lambda *args: calls.append(args))
    CLI.arm(54, STATE)
    assert calls == [("pr", "merge", "54", "--repo", CLI.REPOSITORY, "--auto", "--merge", "--match-head-commit", HEAD)]


@pytest.mark.parametrize("login,method", [("other[bot]", "merge"), ("chayan-codex[bot]", "squash")])
def test_arm_detects_wrong_recorded_actor_or_method(monkeypatch, login, method):
    candidate = pull()
    candidate["user"] = {"login": "chayan-codex[bot]"}
    recorded = copy.deepcopy(candidate)
    recorded["auto_merge"] = {"merge_method": method, "enabled_by": {"login": login}}
    pulls = iter([candidate, recorded])
    monkeypatch.setattr(CLI, "get", lambda path: next(pulls) if path == "pulls/54" else commits()[path])
    monkeypatch.setattr(CLI, "run", lambda *args, **kwargs: "chayan-codex[bot]")
    monkeypatch.setattr(CLI, "gh", lambda *args: "")
    with pytest.raises(ValueError, match="expected App"):
        CLI.arm(54, STATE)


def test_arm_refuses_other_authors_before_writing(monkeypatch):
    candidate = pull()
    candidate["user"] = {"login": "chayan-claude[bot]"}
    monkeypatch.setattr(CLI, "get", lambda path: candidate if path == "pulls/54" else commits()[path])
    monkeypatch.setattr(CLI, "run", lambda *args, **kwargs: "chayan-codex[bot]")
    monkeypatch.setattr(CLI, "gh", lambda *args: pytest.fail("must not write"))
    with pytest.raises(ValueError, match="acting App"):
        CLI.arm(54, STATE)


def test_prepare_uses_fresh_lane_and_normal_merge_without_writing_github(monkeypatch, tmp_path):
    monkeypatch.setattr(CLI, "ROOT", tmp_path)
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if args[-1] == "--whoami":
            return "codex"
        if args == ("git", "worktree", "list", "--porcelain"):
            return f"worktree {tmp_path}\nbranch refs/heads/develop"
        if args == ("git", "rev-parse", "HEAD"):
            return HEAD
        if args == ("git", "show", "-s", "--format=%P", "HEAD"):
            return f"{DEVELOP} {MAIN}"
        if args[:2] == ("git", "rev-parse"):
            return TREE
        return ""

    monkeypatch.setattr(CLI, "run", run)
    monkeypatch.setattr(CLI, "gh", lambda *args: pytest.fail("prepare must never write GitHub"))
    CLI.prepare(STATE)
    assert (str(tmp_path / "scripts/github-app-git"), "fetch", f"https://github.com/{CLI.REPOSITORY}.git", "develop", "main") in [args for args, _ in calls]
    assert ("git", "merge", "--no-ff", "-m", "chore(governance): synchronize main promotion ancestry\n\nAgent: codex", MAIN) in [args for args, _ in calls]
    lane = tmp_path / ".worktrees" / f"sync-main-develop-{MAIN[:12]}-{DEVELOP[:12]}"
    assert any(kwargs.get("cwd") == lane for _, kwargs in calls)


def test_prepare_refuses_nonzero_tree_repair(monkeypatch, tmp_path):
    monkeypatch.setattr(CLI, "ROOT", tmp_path)

    def run(*args, **kwargs):
        if args[-1] == "--whoami":
            return "codex"
        if args == ("git", "worktree", "list", "--porcelain"):
            return f"worktree {tmp_path}"
        if args == ("git", "show", "-s", "--format=%P", "HEAD"):
            return f"{DEVELOP} {MAIN}"
        if args == ("git", "rev-parse", "HEAD^{tree}"):
            return "5" * 40
        return TREE

    monkeypatch.setattr(CLI, "run", run)
    with pytest.raises(ValueError, match="not graph-only"):
        CLI.prepare(STATE)


def test_review_gate_enforces_live_policy_even_with_valid_review(monkeypatch, tmp_path, capsys):
    import json
    import review_gate
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"number": 54}))
    monkeypatch.setenv("GH_TOKEN", "workflow-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    candidate = pull("codex/feature")
    candidate.update({"user": {"login": "chayan-codex[bot]"}, "labels": [{"name": "review:ready-for-ci"}, {"name": "area:tooling"}]})
    reviews = [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "chayan-claude[bot]"}, "body": f"Review type: Baseline\nReviewer: Claude Code\nReviewed head: {HEAD}"}]
    data = {
        "pulls/54": candidate,
        "pulls/54/reviews?per_page=100": reviews,
        "git/ref/heads/main": {"object": {"sha": MAIN}},
        "git/ref/heads/develop": {"object": {"sha": DEVELOP}},
        f"compare/{MAIN}...{DEVELOP}?per_page=1": {"merge_base_commit": {"sha": DEVELOP}},
    }
    monkeypatch.setattr(review_gate, "github_get", lambda token, repository, path: data[path])
    with pytest.raises(SystemExit):
        review_gate.main()
    assert "integration paused" in capsys.readouterr().out
