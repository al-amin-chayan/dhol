"""Post-write failures preserve an audit record without weakening admission."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import runpy
import sys
from types import SimpleNamespace, ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/tofu/cloudflare"))
import routing_operations as routing
from control_plane import ContractError
from backend import digest
from test_cloudflare_routing import ADOPTION, DESIRED, plan


@pytest.mark.parametrize("failure", ["guard", "timeout", "malformed-json", "snapshot", "guard-and-snapshot"])
def test_post_apply_failure_records_truth_and_preserves_nonzero_exit(monkeypatch, failure):
    receipts, snapshots = [], []
    source = b"encrypted-state-fixture"
    initial, final = plan(), plan(False)
    final["resource_changes"][0]["change"]["after"]["id"] = "sensitive-provider-value-not-an-id"
    final["resource_changes"][0]["change"]["after"]["client_secret"] = "sensitive-provider-value"

    class Storage:
        def request(self, *args, **kwargs):
            return source

    calls = []
    def run(command, directory=None, env=None, **kwargs):
        calls.append(command[:2])
        if command[:2] == ["tofu", "plan"]:
            if ["tofu", "apply"] in calls and failure == "timeout":
                raise subprocess.TimeoutExpired(command, 180, output=b"sensitive-provider-output")
            Path(next(arg.removeprefix("-out=") for arg in command if arg.startswith("-out="))).write_bytes(b"encrypted-plan")
        if command[:2] == ["tofu", "show"]:
            if ["tofu", "apply"] in calls and failure == "malformed-json":
                return SimpleNamespace(stdout=b"sensitive-malformed-provider-json")
            return SimpleNamespace(stdout=json.dumps(final if ["tofu", "apply"] in calls else initial).encode())
        return SimpleNamespace(stdout=b"")

    def guard(document, expected, desired, **kwargs):
        if document == final and failure in {"guard", "guard-and-snapshot"}:
            raise ContractError("unreviewed resource drift")
        return {item["address"]: item["change"]["actions"] for item in document["resource_changes"]}

    def snapshot(*args, **kwargs):
        snapshots.append(True)
        if len(snapshots) > 1 and failure in {"snapshot", "guard-and-snapshot"}:
            raise routing.op.OperationError("snapshot storage unavailable")
        return {"snapshot_key": "encrypted-snapshot", "sha256": digest(source)}

    monkeypatch.setattr(routing.op, "secret_set", lambda: {})
    monkeypatch.setattr(routing.op, "environment", lambda *args: {"AWS_ACCESS_KEY_ID": "fixture", "AWS_SECRET_ACCESS_KEY": "fixture", "AWS_SESSION_TOKEN": "fixture", "TF_VAR_publisher_service_token_id": "fixture-id"})
    monkeypatch.setattr(routing, "enable", lambda *args: DESIRED)
    monkeypatch.setattr(routing, "input_digest", lambda *args: "fixture-input-digest")
    monkeypatch.setattr(routing, "S3", lambda *args: Storage())
    monkeypatch.setattr(routing.op, "prepare", lambda *args: ADOPTION)
    monkeypatch.setattr(routing.op, "initialize", lambda *args: None)
    monkeypatch.setattr(routing.op, "run", run)
    monkeypatch.setattr(routing, "guard", guard)
    monkeypatch.setattr(routing, "require_ciphertext", lambda *args: None)
    monkeypatch.setattr(routing, "digest", lambda *args: "approved-fixture-digest")
    monkeypatch.setattr(routing.op, "take_snapshot", snapshot)
    monkeypatch.setattr(routing.op, "evidence", lambda name, value: receipts.append((name, deepcopy(value))))
    monkeypatch.setenv("DHOLBEAT_APPROVED_ROUTING_DIGEST", "approved-fixture-digest")
    monkeypatch.setenv("DHOLBEAT_REVIEWED_HEAD", "a" * 40)
    with pytest.raises(Exception):
        routing.plan({}, apply=True)
    assert [name for name, _ in receipts] == ["routing-apply-rejected"]
    receipt = receipts[0][1]
    assert receipt["status"] == "rejected" and receipt["apply_completed"] is True
    assert receipt["provider_changes_may_have_occurred"] is True
    assert receipt["post_apply_no_change"] is (failure == "snapshot")
    assert receipt["previous_snapshot"]["snapshot_key"] == "encrypted-snapshot"
    assert len(snapshots) >= 2
    assert receipt["recovery_snapshot"] is None if failure in {"snapshot", "guard-and-snapshot"} else receipt["recovery_snapshot"]["snapshot_key"] == "encrypted-snapshot"
    assert "sensitive" not in json.dumps(receipt)
    assert "routing-apply" not in [name for name, _ in receipts]


def test_real_cli_helpers_share_recipient_state_and_caught_safe_exception(monkeypatch, capsys):
    # Exercise the actual __main__ loader, not the normally imported test module.
    policy = yaml.safe_load((ROOT / ".sops.yaml").read_text())
    recipients = policy["creation_rules"][0]["key_groups"][0]["age"]
    original_read = Path.read_text
    def read(path, *args, **kwargs):
        if str(path) == "/run/bootstrap.env":
            return "CF_ACCOUNT_ID=" + routing.op.ACCOUNT + "\nCLOUDFLARE_API_TOKEN=fixture\n"
        return original_read(path, *args, **kwargs)

    def run(command, **kwargs):
        assert command[:2] == ["age-keygen", "-y"]
        index = 0 if command[-1] == "/run/founder.age" else 1
        return SimpleNamespace(returncode=0, stdout=(recipients[index]+"\n").encode(), stderr=b"")

    helper = ModuleType("credential_operations")
    def fail(stage):
        import operations as imported
        assert stage == "storage" and imported.__name__ == "__main__"
        assert len(imported.RECIPIENT_FINGERPRINTS) == 2
        raise imported.OperationError("safe mocked helper failure")
    helper.plan = fail
    monkeypatch.setitem(sys.modules, "operations", routing.op)
    monkeypatch.setitem(sys.modules, "credential_operations", helper)
    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["operations.py", "credential-plan-storage"])
    monkeypatch.setenv("DHOLBEAT_IN_CONTROLLER", "1")
    with pytest.raises(SystemExit) as failure:
        runpy.run_path(str(ROOT / "infra/tofu/cloudflare/operations.py"), run_name="__main__")
    assert failure.value.code == 1
    assert capsys.readouterr().out.strip() == "safe mocked helper failure"
