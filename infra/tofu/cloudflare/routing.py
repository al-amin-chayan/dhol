"""Finite WP-06B profile and complete create-only/no-change plan guard."""

import copy
import json
import re

from control_plane import no_change_plan, require

SERVICE_NAME = "dholbeat-n8n-publisher-api"


def token_identity(api, account):
    tokens = api.request("GET", f"/accounts/{account}/access/service_tokens")
    found = [token for token in tokens if token.get("name") == SERVICE_NAME]
    require(len(found) == 1, "exactly one dedicated publisher service token is required")
    token = found[0]
    require(token.get("enabled", True) is True, "publisher service token is disabled")
    require(re.fullmatch(r"[0-9a-f-]{36}", token.get("id", "")), "invalid publisher service-token identity")
    return token["id"]


def footprint(manifest, bootstrap, token_id):
    account = bootstrap["account_id"]
    route = next(v for v in manifest["routes"] if v["id"] == "publisher-admin-api")
    items = {
        "cloudflare_zero_trust_access_application.publisher_ui[0]": {"account_id": account,
            "name": "Dholbeat publisher administration", "domain": route["hostname"], "type": "self_hosted",
            "options_preflight_bypass": False, "http_only_cookie_attribute": True,
            "enable_binding_cookie": True, "allowed_idps": [bootstrap['founder_identity_provider_id']]},
        "cloudflare_zero_trust_access_application.publisher_api[0]": {"account_id": account,
            "name": "Dholbeat publisher API", "domain": route["hostname"] + "/api/public/*", "type": "self_hosted",
            "options_preflight_bypass": False, "http_only_cookie_attribute": True,
            "allowed_idps": [bootstrap['founder_identity_provider_id']]},
        "cloudflare_zero_trust_access_policy.publisher_machine[0]": {"account_id": account,
            "name": "Dholbeat n8n publisher API only", "decision": "non_identity",
            "include": [{"service_token": {"token_id": token_id}}], 'exclude': [], 'require': []},
        "cloudflare_r2_bucket_lifecycle.publisher_media[0]": {"account_id": account,
            "bucket_name": "dholbeat-publisher-media", "jurisdiction": "default", 'rules': [{
                'id': 'publisher-media-seven-day-expiry', 'enabled': True, 'conditions': {'prefix': ''},
                'delete_objects_transition': {'condition': {'type': 'Age', 'max_age': 604800}},
                'abort_multipart_uploads_transition': {'condition': {'type': 'Age', 'max_age': 86400}}}]},
        "cloudflare_r2_custom_domain.publisher_media[0]": {"account_id": account,
            "bucket_name": "dholbeat-publisher-media", "domain": "media.chayan.me",
            "zone_id": bootstrap["zone_id"], "enabled": True, "min_tls": "1.2"},
    }
    for bucket in manifest["buckets"]:
        key = json.dumps(bucket["id"])
        items[f"cloudflare_r2_bucket.runtime[{key}]"] = {"account_id": account, "name": bucket["name"],
            "jurisdiction": "default", "storage_class": "Standard"}
        items[f"cloudflare_r2_managed_domain.runtime[{key}]"] = {"account_id": account,
            "bucket_name": bucket["name"], "enabled": False}
        if not bucket['public']:
            items[f'cloudflare_r2_bucket_lifecycle.private_backups[{key}]'] = {
                'account_id': account, 'bucket_name': bucket['name'], 'jurisdiction': 'default', 'rules': []}
    return items


def guard(plan, adoption, desired, *, allow_create=False):
    """Protect all adopted identities and permit only the reviewed new footprint.

    New objects may have computed IDs, but their caller-supplied, source-derived
    account/domain/bucket/policy selectors must be known. Existing/new resources
    cannot be updated, deleted, imported again, moved, or replaced in this lane.
    """
    require(isinstance(plan, dict), "missing routing plan")
    changes = plan.get("resource_changes")
    require(isinstance(changes, list), "missing routing changes")
    adopted = copy.deepcopy(plan)
    adopted["resource_changes"] = [v for v in changes if v.get("address") in adoption]
    no_change_plan(adopted, adoption)
    seen = set()
    for item in changes:
        address = item.get("address")
        require(address not in seen, "duplicate routing address")
        seen.add(address)
        if address in adoption:
            continue
        require(address in desired, "unreviewed routing resource")
        require(item.get("mode") == "managed" and item.get("provider_name") in {
            "registry.opentofu.org/cloudflare/cloudflare", "registry.terraform.io/cloudflare/cloudflare"},
            "unexpected routing provider")
        require(not item.get("previous_address"), "moved routing resource")
        change = item.get("change", {})
        allowed = [["no-op"], ["create"]] if allow_create else [["no-op"]]
        require(change.get("actions") in allowed, "routing update/delete/replacement is forbidden")
        require(not change.get("importing"), "new routing profile cannot import unrelated resources")
        before, after = change.get("before"), change.get("after")
        require(isinstance(after, dict), "routing result missing")
        if change["actions"] == ["no-op"]:
            require(before == after and not change.get("after_unknown"), "routing drift or unknown result")
        else:
            require(before is None, "create resource unexpectedly has prior state")
        for key, expected in desired[address].items():
            require(prune_nulls(after.get(key)) == expected, "routing selector differs from reviewed source")
        if address.startswith('cloudflare_zero_trust_access_application.publisher_'):
            attached = prune_nulls(after.get('policies', []))
            founder = adoption['cloudflare_zero_trust_access_policy.founder']['resource_id']
            if '.publisher_ui[' in address:
                require(attached == [{'id': founder, 'precedence': 1}], 'UI must attach only the founder policy')
            else:
                require(len(attached) == 2 and attached[1] == {'id': founder, 'precedence': 2}
                        and attached[0].get('precedence') == 1, 'API policy attachment differs')
                machine = next(v['change'] for v in changes
                               if v['address'] == 'cloudflare_zero_trust_access_policy.publisher_machine[0]')
                machine_id = machine.get('after', {}).get('id')
                if machine_id:
                    require(attached[0] == {'id': machine_id, 'precedence': 1}, 'API attaches a different machine policy')
                else:
                    unknown = change.get('after_unknown', {}).get('policies', [])
                    require(change['actions'] == ['create'] and attached[0] == {'precedence': 1}
                            and isinstance(unknown, list) and unknown and unknown[0].get('id') is True,
                            'computed machine policy reference was not proven')
        # A service-token secret or provider root never belongs in OpenTofu state.
        require(not any(k in after for k in ("client_secret", "secret_access_key", "api_token")),
                "credential-producing resource is forbidden")
    require(seen == set(adoption) | set(desired), "routing inventory is incomplete")
    return {address: next(v["change"]["actions"] for v in changes if v["address"] == address)
            for address in sorted(seen)}


def prune_nulls(value):
    if isinstance(value, dict):
        return {k: prune_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_nulls(v) for v in value]
    return value
