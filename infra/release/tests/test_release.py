from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys

import yaml


RELEASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = RELEASE_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from infra.release.validate import validate_release, validate_runtime_receipt


class FakeGit:
    def __init__(self, commit: str, *, annotated: bool = True, on_main: bool = True):
        self.commit = commit
        self.annotated = annotated
        self.on_main = on_main

    def __call__(self, _root: Path, *args: str) -> tuple[int, str]:
        if len(args) == 3 and args[:2] == ("cat-file", "-t"):
            return 0, "tag" if self.annotated else "commit"
        if len(args) == 2 and args[0] == "rev-parse":
            return 0, self.commit
        if args[:2] == ("merge-base", "--is-ancestor"):
            return (0, "") if self.on_main else (1, "")
        raise AssertionError(f"unexpected git invocation: {args}")


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


def release_case(tmp_path: Path, sequence: int = 1) -> tuple[dict, Path, str]:
    commit = "c" * 40
    plan = tmp_path / "redacted-plan.json"
    plan.write_text('{"changes":[]}\n', encoding="utf-8")
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    tag = f"infra-prod-20260817-{sequence}"
    return release_document(commit, digest, tag), plan, commit


def test_reviewed_annotated_release_is_valid_and_idempotent(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path)
    runner = FakeGit(commit)
    first = validate_release(REPO_ROOT, release, plan, tmp_path, runner)
    second = validate_release(REPO_ROOT, release, plan, tmp_path, runner)
    assert first == []
    assert second == first


def test_wrong_plan_digest_fails(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path, 2)
    release["approved_plan_sha256"] = "e" * 64
    assert "release: approved plan digest does not match the reviewed plan" in validate_release(
        REPO_ROOT, release, plan, tmp_path, FakeGit(commit)
    )


def test_lightweight_tag_fails(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path, 3)
    assert "release: annotated production tag is missing" in validate_release(
        REPO_ROOT, release, plan, tmp_path, FakeGit(commit, annotated=False)
    )


def test_unreviewed_branch_commit_fails(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path, 4)
    assert "release: commit is not reachable from protected main" in validate_release(
        REPO_ROOT, release, plan, tmp_path, FakeGit(commit, on_main=False)
    )


def test_review_record_for_other_commit_fails(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path, 5)
    release["review"]["reviewed_commit"] = "a" * 40
    assert "release: cross-review does not cover the release commit" in validate_release(
        REPO_ROOT, release, plan, tmp_path, FakeGit(commit)
    )


def test_same_model_family_review_fails(tmp_path: Path) -> None:
    release, plan, commit = release_case(tmp_path, 6)
    release["review"]["reviewer"] = release["author"]
    assert "release: author and reviewer must be different model families" in validate_release(
        REPO_ROOT, release, plan, tmp_path, FakeGit(commit)
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


def test_schema_invalid_release_fails_receipt_validation_without_key_error() -> None:
    release = yaml.safe_load(
        (REPO_ROOT / "infra/release/examples/release.yml").read_text(encoding="utf-8")
    )
    receipt = yaml.safe_load(
        (REPO_ROOT / "infra/release/examples/runtime-receipt.yml").read_text(encoding="utf-8")
    )
    assert isinstance(release, dict)
    assert isinstance(receipt, dict)
    release.pop("tag")
    findings = validate_runtime_receipt(REPO_ROOT, release, receipt)
    assert any("schema" in finding and "tag" in finding for finding in findings)
