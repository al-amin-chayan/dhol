"""Fail-closed coverage for the production release-identity gate."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = ROOT / "scripts/lib/release_gate.py"
VARS_PATH = ROOT / "scripts/lib/release_vars.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load_module("dholbeat_release_gate", GATE_PATH)
VALIDATOR = GATE.load_validator(ROOT)


@pytest.fixture()
def release() -> dict:
    document = yaml.safe_load(
        (ROOT / "infra/release/examples/release.yml").read_text(encoding="utf-8")
    )
    document["target_roles"] = ["publisher"]
    return document


@pytest.fixture()
def approved_plan(tmp_path: Path, release: dict) -> Path:
    plan = tmp_path / "plan.yml"
    plan.write_text("document_type: infra-plan\n", encoding="utf-8")
    release["approved_plan_sha256"] = VALIDATOR.sha256_file(plan)
    return plan


def run_gate(release: dict, plan: Path, **overrides) -> list[str]:
    settings = {
        "tag_object_type": "tag",
        "tag_commit": release["git_commit"],
        "reachable_from_main": True,
    }
    settings.update(overrides)
    return VALIDATOR.validate_release(
        ROOT,
        release,
        plan,
        ROOT,
        git_runner=GATE.build_git_runner(
            settings["tag_object_type"],
            settings["tag_commit"],
            settings["reachable_from_main"],
        ),
    )


def test_complete_authorization_passes(release: dict, approved_plan: Path) -> None:
    assert run_gate(release, approved_plan) == []


def test_unreviewed_commit_blocks_apply(release: dict, approved_plan: Path) -> None:
    findings = run_gate(release, approved_plan, reachable_from_main=False)
    assert any("not reachable from protected main" in finding for finding in findings)


def test_lightweight_or_missing_tag_blocks_apply(release: dict, approved_plan: Path) -> None:
    findings = run_gate(release, approved_plan, tag_object_type="commit")
    assert any("annotated production tag is missing" in finding for finding in findings)


def test_tag_pointing_elsewhere_blocks_apply(release: dict, approved_plan: Path) -> None:
    findings = run_gate(release, approved_plan, tag_commit="d" * 40)
    assert any("does not identify the release commit" in finding for finding in findings)


def test_missing_plan_digest_blocks_apply(release: dict, approved_plan: Path) -> None:
    release["approved_plan_sha256"] = "e" * 64
    findings = run_gate(release, approved_plan)
    assert any("plan digest does not match" in finding for finding in findings)


def test_same_family_review_blocks_apply(release: dict, approved_plan: Path) -> None:
    release["review"]["reviewer"] = release["author"]
    findings = run_gate(release, approved_plan)
    assert any("different model families" in finding for finding in findings)


def test_review_of_another_commit_blocks_apply(release: dict, approved_plan: Path) -> None:
    release["review"]["reviewed_commit"] = "f" * 40
    findings = run_gate(release, approved_plan)
    assert any("does not cover the release commit" in finding for finding in findings)


def test_receipt_from_a_different_plan_is_rejected(release: dict, approved_plan: Path) -> None:
    receipt = {
        "schema_version": 1,
        "receipt_type": "host-runtime",
        "release_id": release["release_id"],
        "git_commit": release["git_commit"],
        "tag": release["tag"],
        "host_id": "publish-1",
        "host_role": "publisher",
        "applied_at": release["created_at"],
        "toolchain_lock_sha256": release["toolchain_lock_sha256"],
        "approved_plan_sha256": release["approved_plan_sha256"],
        "applied_plan_sha256": "0" * 64,
        "required_backup_snapshot_id": release["required_backup_snapshot_id"],
        "schema_versions": release["schema_versions"],
        "images": release["images"],
    }
    findings = VALIDATOR.validate_runtime_receipt(ROOT, release, receipt)
    assert any("applied plan digest differs from approval" in finding for finding in findings)


def test_receipt_for_an_untargeted_role_is_rejected(release: dict) -> None:
    receipt = {
        "schema_version": 1,
        "receipt_type": "host-runtime",
        "release_id": release["release_id"],
        "git_commit": release["git_commit"],
        "tag": release["tag"],
        "host_id": "core-1",
        "host_role": "core",
        "applied_at": release["created_at"],
        "toolchain_lock_sha256": release["toolchain_lock_sha256"],
        "approved_plan_sha256": release["approved_plan_sha256"],
        "applied_plan_sha256": release["approved_plan_sha256"],
        "required_backup_snapshot_id": release["required_backup_snapshot_id"],
        "schema_versions": release["schema_versions"],
        "images": release["images"],
    }
    findings = VALIDATOR.validate_runtime_receipt(ROOT, release, receipt)
    assert any("host role is absent from release targets" in finding for finding in findings)


def test_release_vars_never_emit_a_plan_body_or_address(release: dict) -> None:
    completed = subprocess.run(
        [sys.executable, str(VARS_PATH)],
        input=yaml.safe_dump(release),
        text=True,
        capture_output=True,
        check=True,
    )
    document = yaml.safe_load(completed.stdout)
    assert document["dholbeat_applied_plan_sha256"] == release["approved_plan_sha256"]
    assert set(document) == {
        "dholbeat_release",
        "dholbeat_applied_plan_sha256",
        "dholbeat_applied_at",
    }


def test_release_vars_reject_an_incomplete_release(release: dict) -> None:
    incomplete = copy.deepcopy(release)
    del incomplete["approved_plan_sha256"]
    completed = subprocess.run(
        [sys.executable, str(VARS_PATH)],
        input=yaml.safe_dump(incomplete),
        text=True,
        capture_output=True,
    )
    assert completed.returncode != 0
    assert "missing required fields" in completed.stderr
