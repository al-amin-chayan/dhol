from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/tofu/cloudflare"))
from control_plane import ContractError  # noqa: E402
import credential_operations as credentials  # noqa: E402
from routing import SERVICE_NAME, footprint, guard, token_identity  # noqa: E402

PROVIDER = "registry.opentofu.org/cloudflare/cloudflare"
ADOPTION = json.loads((ROOT / "infra/tofu/cloudflare/adoption.json").read_text())
MANIFEST = yaml.safe_load((ROOT / "infra/tofu/cloudflare/routes.yml").read_text())
BOOTSTRAP = yaml.safe_load((ROOT / "infra/tofu/cloudflare/bootstrap.yml").read_text())
TOKEN = "12345678-1234-1234-1234-123456789abc"
DESIRED = footprint(MANIFEST, BOOTSTRAP, TOKEN)


def plan(create=True):
    resources = [{"address": address, "mode": "managed", "provider_name": PROVIDER,
        "change": {"actions": ["no-op"], "before": {"id": identity["resource_id"]},
                   "after": {"id": identity["resource_id"]}, "after_unknown": {}}}
        for address, identity in ADOPTION.items()]
    resources += [{"address": address, "mode": "managed", "provider_name": PROVIDER,
        "change": {"actions": ["create"] if create else ["no-op"],
            "before": None if create else {"id": "fixture-id", **body},
            "after": deepcopy(body) if create else {"id": "fixture-id", **deepcopy(body)},
            "after_unknown": {"id": True} if create else {}}}
        for address, body in DESIRED.items()]
    founder = ADOPTION['cloudflare_zero_trust_access_policy.founder']['resource_id']
    for item in resources:
        if 'access_application.publisher_' not in item['address']:
            continue
        policies = ([{'id': founder, 'precedence': 1}] if 'publisher_ui' in item['address'] else
                    [{'precedence': 1} if create else {'id': 'fixture-id', 'precedence': 1},
                     {'id': founder, 'precedence': 2}])
        item['change']['after']['policies'] = deepcopy(policies)
        if not create:
            item['change']['before']['policies'] = deepcopy(policies)
        elif 'publisher_api' in item['address']:
            item['change']['after_unknown']['policies'] = [{'id': True}, {}]
    return {"format_version": "1.2", "terraform_version": "1.12.5", "errored": False,
            "resource_changes": resources}


def test_create_profile_and_post_apply_no_change_cover_complete_inventory():
    candidate = plan()
    original = deepcopy(candidate)
    actions = guard(candidate, ADOPTION, DESIRED, allow_create=True)
    assert candidate == original
    assert len(actions) == len(ADOPTION) + len(DESIRED)
    assert all(actions[v] == ["no-op"] for v in ADOPTION)
    guard(plan(False), ADOPTION, DESIRED)
    with pytest.raises(ContractError):
        guard(candidate, ADOPTION, DESIRED)


@pytest.mark.parametrize("actions", [["update"], ["delete"], ["delete", "create"], ["read"]])
def test_updates_deletes_and_replacements_never_touch_imports_or_children(actions):
    for address in (next(iter(ADOPTION)), next(iter(DESIRED))):
        candidate = plan()
        item = next(v for v in candidate["resource_changes"] if v["address"] == address)
        item["change"]["actions"] = actions
        with pytest.raises(ContractError):
            guard(candidate, ADOPTION, DESIRED, allow_create=True)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "duplicate", "wrong-account", "credential", "public-backup", "whole-host-machine"])
def test_invalid_boundary_fails_before_apply(mutation):
    candidate = plan()
    children = candidate["resource_changes"][len(ADOPTION):]
    if mutation == "missing":
        candidate["resource_changes"].pop()
    elif mutation == "unknown":
        children[0]["address"] = "cloudflare_dns_record.unrelated"
    elif mutation == "duplicate":
        candidate["resource_changes"].append(deepcopy(children[0]))
    elif mutation == "wrong-account":
        children[0]["change"]["after"]["account_id"] = "f" * 32
    elif mutation == "credential":
        children[0]["change"]["after"]["client_secret"] = "fixture-secret"
    elif mutation == "public-backup":
        item = next(v for v in children if 'managed_domain.runtime["publisher-backups"]' in v["address"])
        item["change"]["after"]["enabled"] = True
    else:
        item = next(v for v in children if "publisher_api" in v["address"])
        item["change"]["after"]["domain"] = "publish.chayan.me/*"
    with pytest.raises(ContractError):
        guard(candidate, ADOPTION, DESIRED, allow_create=True)


def test_token_identity_is_unique_enabled_and_never_any_token():
    class API:
        def __init__(self, result):
            self.result = result

        def request(self, *args):
            return self.result

    assert token_identity(API([{"id": TOKEN, "name": SERVICE_NAME}]), BOOTSTRAP["account_id"]) == TOKEN
    for result in ([], [{"id": TOKEN, "name": "unrelated"}], [{"id": TOKEN, "name": SERVICE_NAME, "enabled": False}],
                   [{"id": TOKEN, "name": SERVICE_NAME}] * 2):
        with pytest.raises(ContractError):
            token_identity(API(result), BOOTSTRAP["account_id"])


def test_credentials_plan_is_deterministic_and_bucket_only():
    first = credentials.blueprint("storage")
    assert first == credentials.blueprint("storage")
    assert first["secrets_in_opentofu"] is False
    assert len({v["name"] for v in first["requests"]}) == 4
    assert len({tuple(v["resources"]) for v in first["requests"]}) == 4
    assert any("dholbeat-source-escrow" in json.dumps(v["resources"]) for v in first["requests"])
    for request in first["requests"]:
        assert request["permission_group"] == "Workers R2 Storage Bucket Item Write"
        assert len(request["resources"]) == 1
        assert "bucket.*" not in json.dumps(request)
    access = credentials.blueprint("access")
    assert access["requests"][0]["body"] == {"name": SERVICE_NAME, "duration": "forever"}


def test_dedicated_source_bucket_has_private_domain_and_restic_retention():
    assert len(DESIRED) == 16 and len(ADOPTION) + len(DESIRED) == 23
    assert DESIRED['cloudflare_r2_managed_domain.runtime["source-escrow"]']["enabled"] is False
    lifecycle = DESIRED['cloudflare_r2_bucket_lifecycle.private_backups["source-escrow"]']
    assert "delete_objects_transition" not in json.dumps(lifecycle)


def test_credential_issuance_cannot_run_without_exact_release_and_approval(monkeypatch):
    monkeypatch.setattr(credentials.op, "recipient_checks", lambda: {})
    monkeypatch.delenv("DHOLBEAT_APPROVED_ROUTING_DIGEST", raising=False)
    monkeypatch.delenv("DHOLBEAT_REVIEWED_HEAD", raising=False)
    with pytest.raises(credentials.op.OperationError, match="founder-approved"):
        credentials.issue({}, "access")


def test_monthly_plan_approval_does_not_authorize_nonexpiring_issuance(monkeypatch):
    monkeypatch.setattr(credentials.op, "recipient_checks", lambda: {})
    previous = credentials.blueprint("access")
    previous["requests"][0]["body"]["duration"] = "720h"
    approval = credentials.digest(json.dumps(previous, sort_keys=True, separators=(",", ":")).encode())
    monkeypatch.setenv("DHOLBEAT_APPROVED_ROUTING_DIGEST", approval)
    monkeypatch.setenv("DHOLBEAT_REVIEWED_HEAD", "a" * 40)
    with pytest.raises(credentials.op.OperationError, match="founder-approved"):
        credentials.issue({}, "access")


@pytest.mark.parametrize("duration,enabled,accepted", [
    ("forever", True, True), ("720h", True, False), (None, True, False), ("forever", False, False),
    ("<missing>", True, False), ("forever", None, False), ("forever", "<missing>", False),
])
def test_issuance_verifies_lifetime_and_revokes_unaccepted_token(monkeypatch, duration, enabled, accepted):
    monkeypatch.setattr(credentials.op, "recipient_checks", lambda: {})
    document = credentials.blueprint("access")
    approval = credentials.digest(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    monkeypatch.setenv("DHOLBEAT_APPROVED_ROUTING_DIGEST", approval)
    monkeypatch.setenv("DHOLBEAT_REVIEWED_HEAD", "a" * 40)
    calls, stored, receipts = [], [], []

    class API:
        def request(self, method, path, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return []
            if method == "POST":
                token = {"id": TOKEN, "client_id": "fixture-client", "client_secret": "fixture-secret"}
                if duration != "<missing>":
                    token["duration"] = duration
                if enabled != "<missing>":
                    token["enabled"] = enabled
                return token
            assert method == "DELETE" and path.endswith("/" + TOKEN)

    monkeypatch.setattr(credentials.op, "Cloudflare", lambda _: API())
    monkeypatch.setattr(credentials, "load_set", lambda _: {"values": {}})
    monkeypatch.setattr(credentials, "store", lambda name, value: stored.append((name, deepcopy(value))))
    monkeypatch.setattr(credentials.op, "evidence", lambda name, value: receipts.append((name, value)))
    if accepted:
        credentials.issue({"CLOUDFLARE_API_TOKEN": "fixture-management"}, "access")
        assert len(stored) == 1 and stored[0][0] == "publisher-access"
        assert receipts[0][1]["service_token_duration"] == "forever"
        assert receipts[0][1]["ciphertext_mac_recovery"] is True
        assert [v[0] for v in calls] == ["GET", "POST"]
    else:
        with pytest.raises(credentials.op.OperationError, match="non-expiring lifetime") as rejection:
            credentials.issue({"CLOUDFLARE_API_TOKEN": "fixture-management"}, "access")
        assert f"observed duration={duration!r} enabled={enabled!r}" in str(rejection.value)
        assert "expected duration='forever' enabled=True" in str(rejection.value)
        assert "fixture-secret" not in str(rejection.value)
        assert not stored and not receipts
        assert [v[0] for v in calls] == ["GET", "POST", "DELETE"]
    assert calls[1][2] == {"name": SERVICE_NAME, "duration": "forever"}


@pytest.mark.parametrize('address,key,value', [
    ('cloudflare_zero_trust_access_application.publisher_ui[0]', 'policies', []),
    ('cloudflare_zero_trust_access_application.publisher_api[0]', 'policies', [{'id': 'any', 'precedence': 1}]),
    ('cloudflare_zero_trust_access_application.publisher_api[0]', 'options_preflight_bypass', True),
    ('cloudflare_zero_trust_access_policy.publisher_machine[0]', 'include', [{'any_valid_service_token': {}}]),
    ('cloudflare_r2_bucket_lifecycle.publisher_media[0]', 'rules', []),
    ('cloudflare_r2_bucket_lifecycle.private_backups["publisher-backups"]', 'rules',
     [{'id': 'unsafe-expiry', 'enabled': True, 'conditions': {'prefix': ''}}]),
])
def test_admission_and_retention_controls_are_guarded(address, key, value):
    candidate = plan()
    next(v for v in candidate['resource_changes'] if v['address'] == address)['change']['after'][key] = value
    with pytest.raises(ContractError):
        guard(candidate, ADOPTION, DESIRED, allow_create=True)


def test_complete_credential_set_cannot_cross_catalog_scopes():
    value = {'schema_version': 1, 'owner_project_id': 'platform', 'secret_set_id': 'publisher-access',
             'values': {'platform-n8n-publisher-access-client-id': 'fixture-id',
                        'platform-n8n-publisher-access-client-secret': 'fixture-secret'}}
    credentials.validate_set('publisher-access', value)
    value['values']['platform-publisher-media-access-key'] = 'fixture-extra'
    with pytest.raises(credentials.op.OperationError):
        credentials.validate_set('publisher-access', value)


def converged_plan():
    candidate = plan(False)
    observations = {
        'cloudflare_zero_trust_access_policy.founder': ('app_count', 1, 3),
        'cloudflare_zero_trust_access_policy.publisher_machine[0]': ('app_count', 0, 1),
        'cloudflare_r2_custom_domain.publisher_media[0]': (
            'status', {'ownership': 'pending', 'ssl': 'initializing'},
            {'ownership': 'active', 'ssl': 'active'}),
    }
    candidate['resource_drift'] = []
    for address, (key, before, after) in observations.items():
        resource = next(item for item in candidate['resource_changes'] if item['address'] == address)
        resource['change']['before'][key] = deepcopy(after)
        resource['change']['after'][key] = deepcopy(after)
        drift = deepcopy(resource)
        drift['change']['actions'] = ['update']
        drift['change']['before'][key] = deepcopy(before)
        candidate['resource_drift'].append(drift)
    return candidate


def test_reviewed_creation_computed_fields_are_accepted_without_mutating_plan():
    candidate = converged_plan()
    original = deepcopy(candidate)
    assert len(guard(candidate, ADOPTION, DESIRED)) == 23
    assert candidate == original
    # The standalone WP-06A rule still rejects drift, including these records.
    from control_plane import no_change_plan
    baseline = deepcopy(candidate)
    baseline['resource_changes'] = baseline['resource_changes'][:len(ADOPTION)]
    with pytest.raises(ContractError, match='drift'):
        no_change_plan(baseline, ADOPTION)


@pytest.mark.parametrize('mutation', [
    'other-adopted-resource', 'other-child-resource', 'duplicate', 'selector',
    'identity', 'additional-key', 'missing-key', 'unknown', 'import', 'move',
    'provider', 'delete', 'missing-change', 'count-before', 'count-after',
    'count-type', 'status-before', 'status-after', 'status-extra', 'current-mismatch',
    'planned-create', 'planned-update', 'malformed-inventory',
])
def test_other_drift_and_unproven_convergence_remain_rejected(mutation):
    candidate = converged_plan()
    founder, machine, media = candidate['resource_drift']
    if mutation == 'other-adopted-resource':
        founder['address'] = 'cloudflare_dns_record.team'
    elif mutation == 'other-child-resource':
        media['address'] = 'cloudflare_r2_bucket.runtime["publisher-media"]'
    elif mutation == 'duplicate':
        candidate['resource_drift'].append(deepcopy(founder))
    elif mutation == 'selector':
        machine['change']['before']['include'] = [{'any_valid_service_token': {}}]
    elif mutation == 'identity':
        founder['change']['before']['id'] = 'different-policy'
    elif mutation == 'additional-key':
        founder['change']['before']['decision'] = 'bypass'
    elif mutation == 'missing-key':
        founder['change']['before'].pop('id')
    elif mutation == 'unknown':
        founder['change']['after_unknown'] = {'app_count': True}
    elif mutation == 'import':
        founder['change']['importing'] = {'id': 'fixture'}
    elif mutation == 'move':
        founder['previous_address'] = 'cloudflare_zero_trust_access_policy.unrelated'
    elif mutation == 'provider':
        founder['provider_name'] = 'registry.opentofu.org/unrelated/provider'
    elif mutation == 'delete':
        founder['change']['actions'] = ['delete']
    elif mutation == 'missing-change':
        founder.pop('change')
    elif mutation == 'count-before':
        founder['change']['before']['app_count'] = 2
    elif mutation == 'count-after':
        founder['change']['after']['app_count'] = 4
    elif mutation == 'count-type':
        machine['change']['before']['app_count'] = False
    elif mutation == 'status-before':
        media['change']['before']['status']['ownership'] = 'blocked'
    elif mutation == 'status-after':
        media['change']['after']['status']['ssl'] = 'pending'
    elif mutation == 'status-extra':
        media['change']['before']['status']['unreviewed'] = 'value'
    elif mutation == 'current-mismatch':
        founder['change']['after']['id'] = 'different-policy'
    elif mutation == 'planned-create':
        candidate['resource_changes'][-1]['change']['actions'] = ['create']
    elif mutation == 'planned-update':
        candidate['resource_changes'][-1]['change']['actions'] = ['update']
    else:
        candidate['resource_drift'] = {}
    with pytest.raises(ContractError):
        guard(candidate, ADOPTION, DESIRED, allow_create=True)
