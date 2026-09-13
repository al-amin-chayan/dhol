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
    for request in first["requests"]:
        assert request["permission_group"] == "Workers R2 Storage Bucket Item Write"
        assert len(request["resources"]) == 1
        assert "bucket.*" not in json.dumps(request)
    access = credentials.blueprint("access")
    assert access["requests"][0]["body"] == {"name": SERVICE_NAME, "duration": "720h"}


def test_credential_issuance_cannot_run_without_exact_release_and_approval(monkeypatch):
    monkeypatch.setattr(credentials.op, "recipient_checks", lambda: {})
    monkeypatch.delenv("DHOLBEAT_APPROVED_ROUTING_DIGEST", raising=False)
    monkeypatch.delenv("DHOLBEAT_REVIEWED_HEAD", raising=False)
    with pytest.raises(credentials.op.OperationError, match="founder-approved"):
        credentials.issue({}, "access")


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
