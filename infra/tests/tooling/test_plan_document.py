"""Redaction, normalization, and determinism coverage for the plan document."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import types

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/lib/plan_document.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_plan_document", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = load_module()

def transcript(journald_max: str = "256M", failed: bool = True) -> str:
    """A realistic check-mode transcript, parameterised by one diff value."""

    body = f"""
PLAY [Converge the project-neutral shared host baseline] ***

TASK [base : Install baseline operating-system packages] ***
changed: [publish-1]

TASK [base : Install bounded persistent and runtime journal settings] ***
--- before: /etc/systemd/journald.conf.d/60-dholbeat-bounds.conf
+++ after: /etc/systemd/journald.conf.d/60-dholbeat-bounds.conf
@@ -1,3 +1,3 @@
 [Journal]
-SystemMaxUse=1G
+SystemMaxUse={journald_max}
 RuntimeMaxUse=64M

changed: [publish-1]

TASK [docker : Install exact Docker Engine and Compose packages] ***
ok: [publish-1] => (item=docker-ce=5:29.7.2-1~ubuntu.24.04~noble)
changed: [publish-1] => (item=containerd.io=2.3.3-1~ubuntu.24.04~noble)
"""
    if failed:
        body += """
TASK [firewall : Verify default deny and the explicit SSH allowlist] ***
fatal: [publish-1]: FAILED! => {"msg": "assertion failed"}

PLAY RECAP ***
publish-1                  : ok=12   changed=3    unreachable=0    failed=1    skipped=3    rescued=0    ignored=0
"""
    else:
        body += """
PLAY RECAP ***
publish-1                  : ok=13   changed=3    unreachable=0    failed=0    skipped=3    rescued=0    ignored=0
"""
    return body


TRANSCRIPT = transcript()


@pytest.mark.parametrize(
    "secret",
    [
        "203.0.113.44",
        "2001:db8:1234:5678:9abc:def0:1234:5678",
        "/Users/founder/.ssh/publish1_bootstrap",
        "/home/founder/.ssh/known_hosts",
    ],
)
def test_redaction_removes_operator_local_material(secret: str) -> None:
    assert secret not in PLAN.redact(f"connecting to {secret} now", [])


def test_redaction_removes_public_key_bodies_but_keeps_the_algorithm() -> None:
    line = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRealLookingKeyMaterial0000000 founder@laptop"
    redacted = PLAN.redact(line, [])
    assert "AAAAC3NzaC1lZDI1NTE5AAAAIRealLookingKeyMaterial0000000" not in redacted
    assert "ssh-ed25519" in redacted


def test_redaction_removes_high_entropy_blobs() -> None:
    blob = "QmxvYlRoYXRMb29rc0xpa2VBU2VjcmV0VmFsdWVXaXRoTG90c09mQ2hhcnM="
    assert blob not in PLAN.redact(f"value: {blob}", [])


def test_explicit_literals_are_redacted_even_when_they_look_ordinary() -> None:
    assert "publish-1.internal" not in PLAN.redact("host publish-1.internal", ["publish-1.internal"])


def test_declared_allowlist_networks_survive_redaction() -> None:
    assert "203.0.113.0/24" in PLAN.redact("allow from 203.0.113.0/24", [])


def test_summary_extracts_ordered_task_outcomes_and_the_recap() -> None:
    summary = PLAN.summarize_transcript(TRANSCRIPT)
    assert summary["changed_tasks"] == [
        "base : Install baseline operating-system packages",
        "base : Install bounded persistent and runtime journal settings",
        "docker : Install exact Docker Engine and Compose packages",
    ]
    assert summary["failed_tasks"] == [
        "firewall : Verify default deny and the explicit SSH allowlist"
    ]
    assert summary["recap"]["changed"] == 3
    assert summary["recap"]["failed"] == 1


def test_summary_is_stable_across_repeated_reads() -> None:
    assert PLAN.summarize_transcript(TRANSCRIPT) == PLAN.summarize_transcript(TRANSCRIPT)


def test_summary_ignores_status_lines_outside_a_task() -> None:
    assert PLAN.summarize_transcript("changed: [publish-1]\n")["changed_tasks"] == []


def test_a_changed_diff_value_changes_the_summary() -> None:
    """Task names alone must not be able to hide a different delta."""

    first = PLAN.summarize_transcript(transcript(journald_max="256M"))
    second = PLAN.summarize_transcript(transcript(journald_max="512M"))
    assert first["changed_tasks"] == second["changed_tasks"]
    assert first["recap"] == second["recap"]
    assert first["diffs"] != second["diffs"]


def test_every_diff_hunk_is_bound_to_its_task() -> None:
    diffs = PLAN.summarize_transcript(TRANSCRIPT)["diffs"]
    assert len(diffs) == 1
    assert diffs[0]["task"] == "base : Install bounded persistent and runtime journal settings"
    assert any("SystemMaxUse=256M" in line for line in diffs[0]["hunk"])


def test_diff_ordering_is_stable_regardless_of_capture_order() -> None:
    assert PLAN.summarize_transcript(TRANSCRIPT)["diffs"] == sorted(
        PLAN.summarize_transcript(TRANSCRIPT)["diffs"],
        key=lambda entry: (entry["task"], "\n".join(entry["hunk"])),
    )


def test_a_failed_run_authorizes_nothing() -> None:
    summary = PLAN.summarize_transcript(TRANSCRIPT)
    findings = PLAN.check_findings(summary, 2, "check-diff")
    assert any("exited 2" in finding for finding in findings)
    assert any("tasks failed" in finding for finding in findings)


def test_a_clean_run_produces_no_findings() -> None:
    summary = PLAN.summarize_transcript(transcript(failed=False))
    assert PLAN.check_findings(summary, 0, "check-diff") == []


def test_a_transcript_without_a_recap_authorizes_nothing() -> None:
    summary = PLAN.summarize_transcript("TASK [base : something] ***\nchanged: [publish-1]\n")
    findings = PLAN.check_findings(summary, 0, "check-diff")
    assert any("no play recap" in finding for finding in findings)


def test_an_unreachable_host_authorizes_nothing() -> None:
    unreachable = """
TASK [base : Gathering Facts] ***
unreachable: [publish-1]

PLAY RECAP ***
publish-1                  : ok=0    changed=0    unreachable=1    failed=0    skipped=0    rescued=0    ignored=0
"""
    findings = PLAN.check_findings(PLAN.summarize_transcript(unreachable), 4, "check-diff")
    assert any("unreachable" in finding for finding in findings)


def test_opentofu_scope_is_explicitly_absent_until_its_own_work_package() -> None:
    scope = PLAN.opentofu_scope(ROOT)
    assert scope["state"] == "absent"
    assert "WP-06" in scope["reason"]


def test_compose_stack_without_a_registry_owner_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "infra/services").mkdir(parents=True)
    (tmp_path / "infra/services/registry.yml").write_text(
        "schema_version: 1\nservices: []\n", encoding="utf-8"
    )
    (tmp_path / "stack/publisher").mkdir(parents=True)
    (tmp_path / "stack/publisher/compose.yml").write_text("services: {}\n", encoding="utf-8")
    stacks, findings = PLAN.compose_scope(tmp_path, "publish-1")
    assert stacks == []
    assert any("no owning entry" in finding for finding in findings)


def owned_compose_root(tmp_path: Path) -> Path:
    (tmp_path / "infra/services").mkdir(parents=True)
    (tmp_path / "infra/services/registry.yml").write_text(
        "schema_version: 1\n"
        "services:\n"
        "  - id: publisher\n"
        "    stack_id: publisher\n"
        "    host_id: publish-1\n",
        encoding="utf-8",
    )
    (tmp_path / "stack/publisher").mkdir(parents=True)
    (tmp_path / "stack/publisher/compose.yml").write_text("services: {}\n", encoding="utf-8")
    return tmp_path


def test_an_owned_compose_stack_is_in_scope_for_its_host(tmp_path: Path) -> None:
    stacks, findings = PLAN.compose_scope(owned_compose_root(tmp_path), "publish-1")
    assert findings == []
    assert [stack["stack_id"] for stack in stacks] == ["publisher"]


def test_a_stack_owned_by_another_host_is_out_of_scope(tmp_path: Path) -> None:
    stacks, findings = PLAN.compose_scope(owned_compose_root(tmp_path), "core-1")
    assert stacks == []
    assert findings == []


def test_an_owned_stack_without_a_rendered_config_fails_closed(tmp_path: Path) -> None:
    import json

    root = owned_compose_root(tmp_path / "repo")
    (root / "infra/inventories/production/baseline").mkdir(parents=True)
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_bytes(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_bytes()
    )
    (root / "infra/secrets").mkdir(parents=True)
    (root / "infra/secrets/catalog.yml").write_text(
        "schema_version: 1\nsecrets: []\n", encoding="utf-8"
    )
    (root / "infra/inventories/production/hosts.yml").write_text(
        "schema_version: 1\nenvironment: production\nhosts: []\npublic_endpoints: []\n",
        encoding="utf-8",
    )
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    log = tmp_path / "check.log"
    log.write_text(transcript(failed=False), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    arguments = build_arguments(root, log, contract)
    arguments.limit = "publish-1"
    (root / "infra/inventories/production/baseline/publish-1.yml").write_bytes(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_bytes()
    )
    _, findings = PLAN.build_plan(arguments)
    assert any("was not rendered for this plan" in finding for finding in findings)


def test_committed_opentofu_always_fails_closed_until_an_adapter_exists(
    tmp_path: Path,
) -> None:
    """No operator-supplied file can satisfy the external-state gate."""

    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    (root / "infra/tofu").mkdir(parents=True)
    (root / "infra/tofu/main.tf").write_text("# committed declarations\n", encoding="utf-8")
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_text(encoding="utf-8")
    )
    source["host_id"] = "fixture-plan-host"
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_text(
        yaml.safe_dump(source, sort_keys=True), encoding="utf-8"
    )
    log = tmp_path / "check.log"
    log.write_text(transcript(failed=False), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    _, findings = PLAN.build_plan(build_arguments(root, log, contract))
    assert any("no plan adapter is implemented" in finding for finding in findings)


def test_the_plan_document_carries_no_opentofu_digest_field() -> None:
    """A digest field would invite an operator-supplied file to satisfy the gate."""

    assert "opentofu_plan_sha256" not in (ROOT / "scripts/lib/plan_document.py").read_text(
        encoding="utf-8"
    )


def test_host_secret_scope_marks_uncommitted_ciphertext() -> None:
    scope = PLAN.host_secret_scope(ROOT, "publish-1")
    assert scope, "publish-1 owns catalogued secrets"
    assert all(entry["state"] in {"committed", "not-provisioned"} for entry in scope)


def build_arguments(root: Path, log: Path, contract: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        root=root,
        limit="fixture-plan-host",
        playbook="playbooks/bootstrap.yml",
        stage="bootstrap",
        git_commit="a" * 40,
        worktree_clean=True,
        reachable_from_main=True,
        rehearsal=False,
        controller_image_id="sha256:" + "b" * 64,
        controller_source_lock="c" * 64,
        contract=contract,
        ansible_log=log,
        ansible_status=0,
        sops_canary="verified",
        compose_render=[],
        redact=[],
        applied_playbook="playbooks/site.yml",
        plan_kind="check-diff",
        transport="auto",
        wireguard_restore_public_key="",
    )


def test_plan_document_is_byte_stable_for_identical_inputs(tmp_path: Path) -> None:
    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())

    baseline = root / "infra/inventories/production/baseline/fixture-plan-host.yml"
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_text(encoding="utf-8")
    )
    source["host_id"] = "fixture-plan-host"
    baseline.write_text(yaml.safe_dump(source, sort_keys=True), encoding="utf-8")

    log = tmp_path / "check.log"
    log.write_text(transcript(failed=False), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    first, findings = PLAN.build_plan(build_arguments(root, log, contract))
    second, _ = PLAN.build_plan(build_arguments(root, log, contract))
    assert findings == []
    assert yaml.safe_dump(first, sort_keys=True) == yaml.safe_dump(second, sort_keys=True)
    assert first["reviewed_input"]["rehearsal"] is False
    assert first["secrets"]["decrypted_to_disk"] is False
    assert first["planned_playbook"] == "playbooks/bootstrap.yml"
    assert first["applied_playbook"] == "playbooks/site.yml"
    assert first["ansible_run"]["diffs"], "the reviewed diff must be bound into the plan"
    assert first["ansible_run"]["transcript_sha256"]
    # Both are safety-critical and must be reproduced by apply.
    assert first["transport"] == "auto"
    assert first["wireguard_restore_public_key"] == ""


def test_the_transport_is_bound_into_the_plan_digest(tmp_path: Path) -> None:
    """A different transport is a different authorization."""

    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive-wireguard.yml").read_text(
            encoding="utf-8"
        )
    )
    source["host_id"] = "fixture-plan-host"
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_text(
        yaml.safe_dump(source, sort_keys=True), encoding="utf-8"
    )
    log = tmp_path / "check.log"
    log.write_text(transcript(failed=False), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    digests = []
    for transport in ("auto", "tunnel"):
        arguments = build_arguments(root, log, contract)
        arguments.transport = transport
        plan, findings = PLAN.build_plan(arguments)
        assert findings == []
        digests.append(PLAN.sha256_text(yaml.safe_dump(plan, sort_keys=True)))
    assert digests[0] != digests[1]


def test_a_restored_identity_changes_the_plan_digest(tmp_path: Path) -> None:
    """Replacing the server identity must not ride in on an unchanged plan."""

    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive-wireguard.yml").read_text(
            encoding="utf-8"
        )
    )
    source["host_id"] = "fixture-plan-host"
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_text(
        yaml.safe_dump(source, sort_keys=True), encoding="utf-8"
    )
    log = tmp_path / "check.log"
    log.write_text(transcript(failed=False), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    baseline, _ = PLAN.build_plan(build_arguments(root, log, contract))
    restoring = build_arguments(root, log, contract)
    restoring.wireguard_restore_public_key = "RklYVFVSRS1TRVJWRVItUFVCLS0tLS0tLS0tLS0tLS0="
    replaced, _ = PLAN.build_plan(restoring)
    assert PLAN.sha256_text(yaml.safe_dump(baseline, sort_keys=True)) != PLAN.sha256_text(
        yaml.safe_dump(replaced, sort_keys=True)
    )


def test_a_changed_host_cannot_reproduce_an_earlier_plan_digest(tmp_path: Path) -> None:
    """Only a diff value differs; the plan document must still change."""

    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_text(encoding="utf-8")
    )
    source["host_id"] = "fixture-plan-host"
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_text(
        yaml.safe_dump(source, sort_keys=True), encoding="utf-8"
    )
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    digests = []
    for value in ("256M", "512M"):
        log = tmp_path / f"check-{value}.log"
        log.write_text(transcript(journald_max=value, failed=False), encoding="utf-8")
        plan, findings = PLAN.build_plan(build_arguments(root, log, contract))
        assert findings == []
        digests.append(PLAN.sha256_text(yaml.safe_dump(plan, sort_keys=True)))
    assert digests[0] != digests[1]


def test_a_failed_check_never_yields_an_approvable_plan(tmp_path: Path) -> None:
    import json
    import shutil

    import yaml

    root = tmp_path / "repo"
    shutil.copytree(ROOT / "infra/inventories/production", root / "infra/inventories/production")
    shutil.copytree(ROOT / "infra/services", root / "infra/services")
    shutil.copytree(ROOT / "infra/secrets", root / "infra/secrets")
    (root / "toolchain.lock.yml").write_bytes((ROOT / "toolchain.lock.yml").read_bytes())
    source = yaml.safe_load(
        (ROOT / "infra/inventories/fixtures/host-baseline/positive.yml").read_text(encoding="utf-8")
    )
    source["host_id"] = "fixture-plan-host"
    (root / "infra/inventories/production/baseline/fixture-plan-host.yml").write_text(
        yaml.safe_dump(source, sort_keys=True), encoding="utf-8"
    )
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    log = tmp_path / "check.log"
    log.write_text(transcript(failed=True), encoding="utf-8")

    arguments = build_arguments(root, log, contract)
    arguments.ansible_status = 2
    _, findings = PLAN.build_plan(arguments)
    assert any("authorizes nothing" in finding for finding in findings)
