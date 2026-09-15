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


def guard(plan, adoption, desired, *, allow_create=False, allow_observations=False):
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
    # Attachments, R2 TLS, and publisher connector startup change computed
    # observations. Validate their narrow shape before the WP-06A guard;
    # its general rejection of drift remains unchanged for every other field.
    if allow_observations:
        validate_creation_observations(plan, adoption, desired)
        adopted["resource_drift"] = []
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


def validate_creation_observations(plan, adoption, desired):
    drifts = plan.get("resource_drift", [])
    require(isinstance(drifts, list), "invalid routing drift inventory")
    if not drifts:
        return
    changes = plan["resource_changes"]
    require(all(isinstance(item, dict) and item.get("change", {}).get("actions") == ["no-op"]
                for item in changes), "creation observations require an entirely no-change plan")
    resources = {item.get("address"): item for item in changes}
    founder = "cloudflare_zero_trust_access_policy.founder"
    machine = "cloudflare_zero_trust_access_policy.publisher_machine[0]"
    media = "cloudflare_r2_custom_domain.publisher_media[0]"
    tunnel = "cloudflare_zero_trust_tunnel_cloudflared.publisher"
    counts = {founder: (1, 3), machine: (0, 1)}
    require(founder in adoption and machine in desired and media in desired,
            "creation observations require the reviewed publisher profile")
    seen = set()
    for item in drifts:
        require(isinstance(item, dict), "invalid routing drift record")
        address = item.get("address")
        require(address in {*counts, media, tunnel} and address not in seen,
                "resource drift requires separate review")
        seen.add(address)
        resource = resources.get(address, {})
        require(item.get("mode") == resource.get("mode") == "managed"
                and item.get("provider_name") == resource.get("provider_name")
                and item.get("provider_name") in {
                    "registry.opentofu.org/cloudflare/cloudflare",
                    "registry.terraform.io/cloudflare/cloudflare"}
                and not item.get("previous_address"), "invalid creation observation identity")
        change = item.get("change", {})
        require(isinstance(change, dict) and change.get("actions") == ["update"]
                and not change.get("after_unknown") and not change.get("importing"),
                "invalid creation observation action")
        before, after = change.get("before"), change.get("after")
        current = resource.get("change", {})
        require(isinstance(before, dict) and isinstance(after, dict)
                and set(before) == set(after)
                and after == current.get("before") == current.get("after"),
                "creation observation differs from current no-change resource")
        changed = {key for key in before if before[key] != after[key]}
        if address in counts:
            old, new = counts[address]
            require(changed == {"app_count"}
                    and type(before.get("app_count")) is int and type(after.get("app_count")) is int
                    and (before["app_count"], after["app_count"]) == (old, new),
                    "policy attachment count differs from reviewed creation")
        elif address == tunnel:
            import ipaddress
            from datetime import datetime
            from uuid import UUID

            require(tunnel in adoption and before.get("id") == after.get("id") == adoption[tunnel]["resource_id"],
                    "publisher tunnel observation identity differs")
            require(changed and changed <= {"connections", "conns_active_at"},
                    "publisher tunnel configuration drift is forbidden")
            connections = after.get("connections")
            require(isinstance(connections, list) and len(connections) == 4,
                    "publisher tunnel must have four active connections")
            keys = {"client_id", "client_version", "colo_name", "id", "uuid",
                    "opened_at", "origin_ip"}
            try:
                # The pinned provider omits the API's false reconnect flag.
                require(all(isinstance(c, dict) and set(c) in (keys, keys | {"is_pending_reconnect"})
                            and c.get("is_pending_reconnect", False) is False
                            and ipaddress.ip_address(c["origin_ip"]).is_global
                            and bool(c["client_version"]) and bool(c["colo_name"])
                            and datetime.fromisoformat(c["opened_at"].replace("Z", "+00:00")).utcoffset() is not None
                            for c in connections), "publisher tunnel connection metadata is invalid")
                require(len({str(UUID(c["id"])) for c in connections}) == 4
                        and len({str(UUID(c["client_id"])) for c in connections}) == 1
                        and len({c["origin_ip"] for c in connections}) == 1
                        and datetime.fromisoformat(after["conns_active_at"].replace("Z", "+00:00")).utcoffset() is not None,
                        "publisher tunnel connection identities differ")
            except (ValueError, TypeError, KeyError, AttributeError):
                require(False, "publisher tunnel connection metadata is invalid")
        else:
            prior = before.get("status")
            require(changed == {"status"} and isinstance(prior, dict)
                    and set(prior) == {"ownership", "ssl"}
                    and prior["ownership"] in {"pending", "active"}
                    and prior["ssl"] in {"initializing", "pending", "active"}
                    and after.get("status") == {"ownership": "active", "ssl": "active"},
                    "media domain activation differs from reviewed creation")


def prune_nulls(value):
    if isinstance(value, dict):
        return {k: prune_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_nulls(v) for v in value]
    return value
