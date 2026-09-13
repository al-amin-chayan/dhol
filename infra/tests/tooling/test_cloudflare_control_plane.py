from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "infra/tofu/cloudflare"
sys.path.insert(0, str(PACKAGE))
from control_plane import ContractError, no_change_plan, render_ingress  # noqa: E402


ADDRESS = 'cloudflare_zero_trust_tunnel_cloudflared.host["fixture-core"]'
EXPECTED = {ADDRESS: {"resource_id": "fixture-tunnel", "import_id": "fixture-account/fixture-tunnel"}}


def plan():
    return {"format_version": "1.2", "terraform_version": "1.12.5", "errored": False,
            "resource_changes": [{"address": ADDRESS, "mode": "managed",
                                  "provider_name": "registry.opentofu.org/cloudflare/cloudflare",
                                  "change": {"actions": ["no-op"], "after_unknown": {},
                                             "after": {"id": "fixture-tunnel"}}}]}


def test_import_and_post_import_plans_are_no_change_and_repeatable():
    candidate = plan()
    no_change_plan(candidate, EXPECTED)
    candidate["resource_changes"][0]["change"]["importing"] = {"id": EXPECTED[ADDRESS]["import_id"]}
    before = deepcopy(candidate)
    no_change_plan(candidate, EXPECTED)
    no_change_plan(candidate, EXPECTED)
    assert candidate == before


@pytest.mark.parametrize("actions", [["create"], ["update"], ["delete"], ["delete", "create"],
                                     ["create", "delete"], ["read"], [], ["unknown"]])
def test_provider_mutations_and_unknown_actions_are_rejected(actions):
    candidate = plan()
    candidate["resource_changes"][0]["change"]["actions"] = actions
    with pytest.raises(ContractError, match="mutation"):
        no_change_plan(candidate, EXPECTED)


@pytest.mark.parametrize("key,value,reason", [
    ("complete", False, "incomplete"), ("errored", True, "errored"),
    ("format_version", "2.0", "format"), ("resource_changes", [], "fully planned"),
    ("terraform_version", "1.0.0", "locked OpenTofu"),
    ("resource_drift", [{"change": {"actions": ["update"]}}], "drift"),
    ("deferred_changes", [{}], "deferred"),
    ("action_invocations", [{}], "action invocations"),
    ("output_changes", {"secret": {"actions": ["update"]}}, "output"),
    ("checks", [{"status": "unknown"}], "checks"),
])
def test_incomplete_drift_and_output_plans_fail(key, value, reason):
    candidate = plan()
    candidate[key] = value
    with pytest.raises(ContractError, match=reason):
        no_change_plan(candidate, EXPECTED)


@pytest.mark.parametrize("mutation,reason", [
    (lambda c: c.update(address="unreviewed"), "unreviewed"),
    (lambda c: c["change"]["after"].update(id="wrong"), "resource identity"),
    (lambda c: c["change"].update(importing={"id": "wrong"}), "import identity"),
    (lambda c: c["change"].update(after_unknown={"id": True}), "unknown"),
    (lambda c: c.update(provider_name="unreviewed-provider"), "provider"),
])
def test_adoption_identity_is_independently_pinned(mutation, reason):
    candidate = plan()
    mutation(candidate["resource_changes"][0])
    with pytest.raises(ContractError, match=reason):
        no_change_plan(candidate, EXPECTED)


def test_duplicate_plan_and_empty_adoption_inventory_fail():
    candidate = plan()
    candidate["resource_changes"] *= 2
    with pytest.raises(ContractError, match="duplicate"):
        no_change_plan(candidate, EXPECTED)
    with pytest.raises(ContractError, match="empty"):
        no_change_plan(plan(), {})


def registries():
    fixture = ROOT / "infra/schemas/fixtures/positive"
    documents = [yaml.safe_load((fixture / name).read_text())
                 for name in ("routes.yml", "domains.yml", "registry.yml")]
    documents.append({"schema_version": 1, "tunnels": [
        {"id": "00000000-0000-0000-0000-000000000001", "host_id": "fixture-core",
         "credential_ref": "fixture-core-tunnel"},
        {"id": "00000000-0000-0000-0000-000000000002", "host_id": "fixture-publisher",
         "credential_ref": "fixture-publisher-tunnel"}]})
    return documents


def test_human_loopback_ingress_is_deterministic_with_terminal_deny():
    inputs = registries()
    before = deepcopy(inputs)
    first = render_ingress(*inputs, "fixture-core")
    assert first == render_ingress(*inputs, "fixture-core")
    assert inputs == before
    assert first["ingress"] == [
        {"hostname": "alpha.example.test", "service": "http://127.0.0.1:18081"},
        {"hostname": "beta.example.test", "service": "http://127.0.0.1:18082"},
        {"service": "http_status:404"}]


@pytest.mark.parametrize("mutation,reason", [
    (lambda r,d,s,t: r["routes"][0].update(host_id="fixture-publisher"), "cross-host"),
    (lambda r,d,s,t: r["routes"][0].update(owner="project-beta"), "cross-project"),
    (lambda r,d,s,t: r["routes"][0]["origin"].update(host="203.0.113.1"), "public origin"),
    (lambda r,d,s,t: r["routes"][0]["access"].clear(), "route registry schema"),
    (lambda r,d,s,t: r["routes"][0]["access"].update(mode="machine-exception"), "machine ingress"),
    (lambda r,d,s,t: r["routes"][0].update(path="/webhook/*"), "path-scoped"),
    (lambda r,d,s,t: s["services"][0].update(route_ids=[]), "backreference"),
    (lambda r,d,s,t: t["tunnels"][1].update(credential_ref="fixture-core-tunnel"), "shared tunnel"),
    (lambda r,d,s,t: t["tunnels"][1].update(host_id="fixture-core"), "one tunnel per host"),
    (lambda r,d,s,t: t["tunnels"][0].update(token="DO_NOT_RENDER_SECRET"), "non-secret references"),
    (lambda r,d,s,t: d["domains"][1].update(name="alpha.example.test"), "duplicate route hostname"),
])
def test_ingress_security_boundaries_fail_for_intended_reasons(mutation, reason):
    inputs = registries()
    mutation(*inputs)
    with pytest.raises(ContractError, match=reason):
        render_ingress(*inputs, "fixture-core")


def test_renderer_does_not_silently_ignore_bad_routes_on_another_host():
    inputs = registries()
    inputs[0]["routes"][0].update(host_id="unknown-host")
    with pytest.raises(ContractError, match="route tunnel"):
        render_ingress(*inputs, "fixture-core")


def test_cli_never_echoes_plan_values_or_parser_source_lines(tmp_path):
    candidate = tmp_path / "candidate.json"
    expected = tmp_path / "expected.json"
    candidate.write_text('{"DO_NOT_ECHO_SECRET": broken input}')
    expected.write_text(json.dumps(EXPECTED))
    result = subprocess.run([sys.executable, str(PACKAGE / "control_plane.py"), "no-change-plan",
                             "--plan", str(candidate), "--expected", str(expected)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "malformed input" in result.stderr
    assert "DO_NOT_ECHO_SECRET" not in result.stdout + result.stderr


def test_plan_format_matches_locked_tofu_without_network_or_external_provider(tmp_path):
    # Built-in terraform_data exercises the actual locked plan JSON interface.
    # The disposable local state/plan live only in the controller's tmpfs.
    # This is not a Cloudflare import or remote-backend integration test.
    (tmp_path / "main.tf").write_text('resource "terraform_data" "fixture" { input = "fixture" }\n')
    commands = [["tofu", "init", "-input=false", "-no-color"],
                ["tofu", "apply", "-input=false", "-auto-approve", "-no-color"],
                ["tofu", "plan", "-input=false", "-detailed-exitcode", "-out=fixture.plan", "-no-color"]]
    for command in commands:
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True,
                                check=False, timeout=30)
        assert result.returncode == 0, "locked OpenTofu disposable plan command failed"
    result = subprocess.run(["tofu", "show", "-json", "fixture.plan"], cwd=tmp_path,
                            capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode == 0
    actual = json.loads(result.stdout)
    assert actual["format_version"] == "1.2"
    assert actual.get("complete", True) is True and actual["errored"] is False
    assert actual["resource_changes"][0]["change"]["actions"] == ["no-op"]
    address = actual["resource_changes"][0]["address"]
    identifier = actual["resource_changes"][0]["change"]["after"]["id"]
    with pytest.raises(ContractError, match="unexpected adoption provider"):
        no_change_plan(actual, {address: {"resource_id": identifier, "import_id": identifier}})


def test_yaml_parser_diagnostics_never_echo_source_values(tmp_path):
    source = tmp_path / "malformed.yml"
    source.write_text('routes: [DO_NOT_ECHO_YAML_SECRET\n')
    command = [sys.executable, str(PACKAGE / "control_plane.py"), "render-ingress", "--host", "fixture-core"]
    for name in ("routes", "domains", "services", "tunnels"):
        command.extend([f"--{name}", str(source)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "malformed input" in result.stderr
    assert "DO_NOT_ECHO_YAML_SECRET" not in result.stdout + result.stderr
