from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import subprocess

import yaml

from infra.release.validate import validate_release, validate_runtime_receipt


RELEASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = RELEASE_DIR.parents[1]


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "git"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Fixture Reviewer")
    git(root, "config", "user.email", "fixture@example.test")
    (root / "desired-state.txt").write_text("reviewed\n", encoding="utf-8")
    git(root, "add", "desired-state.txt")
    git(root, "commit", "-m", "feat: reviewed fixture")
    return root, git(root, "rev-parse", "HEAD")


def release_document(commit: str, plan_digest: str, tag: str) -> dict:
    document = yaml.safe_load(
        (REPO_ROOT / "infra/release/examples/release.yml").read_text(encoding="utf-8")
    )
    assert isinstance(document, dict)
    document["git_commit"] = commit
    document["review"]["reviewed_commit"] = commit
    document["approved_plan_sha256"] = plan_digest
    document["tag"] = tag
    return document


def test_reviewed_annotated_release_is_valid_and_idempotent(tmp_path: Path) -> None:
    git_root, commit = test_repository(tmp_path)
    tag = "infra-prod-20260817-1"
    git(git_root, "tag", "-a", tag, "-m", "fixture production release")
    plan = tmp_path / "redacted-plan.json"
    plan.write_text('{"changes":[]}\n', encoding="utf-8")
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    release = release_document(commit, digest, tag)
    first = validate_release(REPO_ROOT, release, plan, git_root)
    second = validate_release(REPO_ROOT, release, plan, git_root)
    assert first == []
    assert second == first


def test_wrong_plan_digest_fails(tmp_path: Path) -> None:
    git_root, commit = test_repository(tmp_path)
    tag = "infra-prod-20260817-2"
    git(git_root, "tag", "-a", tag, "-m", "fixture production release")
    plan = tmp_path / "redacted-plan.json"
    plan.write_text('{"changes":["safe"]}\n', encoding="utf-8")
    release = release_document(commit, "e" * 64, tag)
    assert "release: approved plan digest does not match the reviewed plan" in validate_release(
        REPO_ROOT, release, plan, git_root
    )


def test_lightweight_tag_fails(tmp_path: Path) -> None:
    git_root, commit = test_repository(tmp_path)
    tag = "infra-prod-20260817-3"
    git(git_root, "tag", tag)
    plan = tmp_path / "redacted-plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    release = release_document(commit, hashlib.sha256(plan.read_bytes()).hexdigest(), tag)
    assert "release: annotated production tag is missing" in validate_release(
        REPO_ROOT, release, plan, git_root
    )


def test_unreviewed_branch_commit_fails(tmp_path: Path) -> None:
    git_root, _ = test_repository(tmp_path)
    git(git_root, "checkout", "-b", "unreviewed")
    (git_root / "desired-state.txt").write_text("unreviewed\n", encoding="utf-8")
    git(git_root, "commit", "-am", "feat: unreviewed fixture")
    commit = git(git_root, "rev-parse", "HEAD")
    tag = "infra-prod-20260817-4"
    git(git_root, "tag", "-a", tag, "-m", "unreviewed release")
    plan = tmp_path / "redacted-plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    release = release_document(commit, hashlib.sha256(plan.read_bytes()).hexdigest(), tag)
    assert "release: commit is not reachable from protected main" in validate_release(
        REPO_ROOT, release, plan, git_root
    )


def test_review_record_for_other_commit_fails(tmp_path: Path) -> None:
    git_root, commit = test_repository(tmp_path)
    tag = "infra-prod-20260817-5"
    git(git_root, "tag", "-a", tag, "-m", "fixture production release")
    plan = tmp_path / "redacted-plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    release = release_document(commit, hashlib.sha256(plan.read_bytes()).hexdigest(), tag)
    release["review"]["reviewed_commit"] = "a" * 40
    assert "release: cross-review does not cover the release commit" in validate_release(
        REPO_ROOT, release, plan, git_root
    )


def test_runtime_receipt_matches_release_and_rejects_plan_drift() -> None:
    release = yaml.safe_load(
        (REPO_ROOT / "infra/release/examples/release.yml").read_text(encoding="utf-8")
    )
    receipt = yaml.safe_load(
        (REPO_ROOT / "infra/release/examples/runtime-receipt.yml").read_text(encoding="utf-8")
    )
    assert isinstance(release, dict)
    assert isinstance(receipt, dict)
    assert validate_runtime_receipt(REPO_ROOT, release, receipt) == []
    drifted = copy.deepcopy(receipt)
    drifted["applied_plan_sha256"] = "f" * 64
    assert "applied plan digest differs from approval" in "\n".join(
        validate_runtime_receipt(REPO_ROOT, release, drifted)
    )
