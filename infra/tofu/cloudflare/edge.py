"""One host-owned edge manifest for adopted and explicitly planned routes."""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

from control_plane import ContractError, require

ROOT = Path(__file__).resolve().parents[3]


def validate(manifest: dict, inventory: dict, domains: dict, registrar: dict):
    require(isinstance(manifest, dict) and set(manifest) == {"schema_version", "tunnels", "routes", "buckets"}
            and manifest["schema_version"] == 1, "invalid edge manifest")
    hosts = {host["id"]: host for host in inventory["hosts"]}
    endpoints = {entry["id"]: entry for entry in inventory["public_endpoints"]}
    domain = next((d for d in domains["domains"] if d["id"] == registrar.get("domain_id")), None)
    require(domain is not None, "registered parent domain is missing")
    require(registrar.get("registrar") == "cloudflare" and registrar.get("registrar_owner") == "founder"
            and registrar.get("renewal_owner") == "founder" and registrar.get("recovery_location") == "password-manager"
            and bool(registrar.get("recovery_account_id")), "unknown registrar or recovery ownership")
    require(set(domain["expected_nameservers"]) == set(registrar["delegation_evidence"]["expected_nameservers"])
            and registrar["delegation_evidence"].get("recursion") is False
            and registrar["delegation_evidence"].get("result") == "exact-match", "wrong parent delegation")
    require(registrar["renewal_evidence"].get("auto_renew") is True
            and bool(registrar["renewal_evidence"].get("expires_on")), "renewal evidence missing")
    tunnels = {}
    refs = set()
    ids = set()
    for tunnel in manifest["tunnels"]:
        require(set(tunnel) == {"id", "name", "host_id", "config_source", "credential_ref"}, "unknown tunnel field")
        host = tunnel["host_id"]
        require(host in hosts and host not in tunnels, "one tunnel per declared host is required")
        require(tunnel["id"] not in ids and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", tunnel["id"]), "shared or invalid tunnel identity")
        require(tunnel["credential_ref"] not in refs, "shared tunnel token reference")
        require(tunnel["config_source"] in {"local", "cloudflare"}, "unknown tunnel configuration source")
        tunnels[host] = tunnel
        refs.add(tunnel["credential_ref"])
        ids.add(tunnel["id"])
    require(set(tunnels) == set(hosts), "host tunnel coverage is incomplete")
    seen = set()
    names = set()
    required = {"id", "hostname", "service_id", "host_id", "status", "origin", "path", "caller", "access",
                "methods", "application_auth", "data_classification", "retention_owner"}
    optional = {"rate_limit", "machine_path", "machine_access", "machine_policy", "webhook_secret_ref"}
    for route in manifest["routes"]:
        require(required <= set(route) <= required | optional, "invalid route fields")
        require(route["id"] in endpoints and route["id"] not in seen, "unknown or duplicate route")
        seen.add(route["id"])
        endpoint = endpoints[route["id"]]
        require(route["host_id"] == endpoint["host_id"] and route["hostname"] == endpoint["hostname"], "cross-host or alternate-DNS route")
        require(route["service_id"] in hosts[route["host_id"]]["service_ids"], "cross-host origin service")
        require(route["hostname"] not in names and route["hostname"].endswith("." + domain["name"]), "invalid route parent domain")
        names.add(route["hostname"])
        origin = urlsplit(route["origin"])
        try:
            loopback = origin.hostname == "localhost" or ipaddress.ip_address(origin.hostname).is_loopback
        except ValueError:
            loopback = False
        require(loopback and origin.scheme == "http" and origin.port is not None and origin.path == ""
                and not origin.query and not origin.fragment and not origin.username, "public or malformed origin")
        require(route["status"] in {"adopted", "planned", "existing-unprotected"}, "unknown route admission status")
        require(route["caller"] in endpoint["audiences"], "undeclared route caller")
        require(route["methods"] and len(set(route["methods"])) == len(route["methods"])
                and set(route["methods"]) <= {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}, "invalid route methods")
        if route["caller"] == "machine":
            require(route["access"] == "path-only-machine-exception" and route["path"] == "/webhook/*"
                    and route["methods"] == ["POST"]
                    and route["application_auth"] == "telegram-secret-token-verifying-proxy"
                    and route.get("webhook_secret_ref") == "platform-telegram-webhook-secret"
                    and route.get("rate_limit") == {"requests": 60, "period_seconds": 60}, "whole-host bypass or unverified machine ingress")
        else:
            require(route["access"] == "founder-only" and route["path"] == "/", "missing human Access")
        if "machine_path" in route:
            require(route["machine_path"] == "/api/public/*" and route.get("machine_access") == "n8n-service-auth"
                    and endpoint["audiences"] == ["human", "machine"], "unscoped service-token route")
            require(route.get("machine_policy") == {
                "decision": "non_identity", "principal_id": "n8n", "application_hostname": route["hostname"],
                "application_path": route["machine_path"], "allow_any_service_token": False,
                "client_id_ref": "platform-n8n-publisher-access-client-id",
                "client_secret_ref": "platform-n8n-publisher-access-client-secret",
                "application_key_ref": "platform-n8n-publisher-api-key"}, "unscoped machine credential policy")
    require(seen == set(endpoints), "edge route coverage is incomplete")
    catalog = {item["id"]: item for item in yaml.safe_load((ROOT / "infra/secrets/catalog.yml").read_text())["secrets"]}
    for host_id, tunnel in tunnels.items():
        secret = catalog.get(tunnel["credential_ref"], {})
        require(secret.get("target", {}).get("host_id") == host_id, "cross-host or unknown tunnel credential")
    bucket_names = set()
    bucket_credentials = set()
    backup_hosts = set()
    media_hosts = set()
    bucket_ids = set()
    principals = set()
    for bucket in manifest["buckets"]:
        required_bucket = {"id", "name", "host_id", "principal_id", "credential_refs", "status", "public", "retention_authority", "object_expiry_days"}
        require(required_bucket <= set(bucket) <= required_bucket | {"public_hostname"}, "unknown or missing bucket fields")
        require(bucket["id"] not in bucket_ids, "duplicate bucket ID")
        bucket_ids.add(bucket["id"])
        require(bucket["name"] not in bucket_names and bucket["principal_id"] not in principals, "shared bucket credential boundary")
        require(len(bucket.get("credential_refs", [])) == 2 and len(set(bucket["credential_refs"])) == 2
                and not bucket_credentials.intersection(bucket["credential_refs"]), "shared or absent bucket credentials")
        for reference in bucket["credential_refs"]:
            secret = catalog.get(reference, {})
            require(secret.get("allowed_principal_ids") == [bucket["principal_id"]]
                    and secret.get("target", {}).get("host_id") == bucket["host_id"], "cross-principal bucket credential")
        bucket_credentials.update(bucket["credential_refs"])
        bucket_names.add(bucket["name"])
        principals.add(bucket["principal_id"])
        require(bucket["principal_id"] in hosts[bucket["host_id"]]["service_ids"], "cross-host bucket owner")
        require(bucket["status"] in {"planned", "adopted"}, "unknown bucket admission status")
        if bucket["retention_authority"] == "restic-forget-prune":
            require(bucket["host_id"] not in backup_hosts, "duplicate private backup boundary")
            backup_hosts.add(bucket["host_id"])
            require(bucket["public"] is False and bucket["object_expiry_days"] is None
                    and "public_hostname" not in bucket, "public or lifecycle-expiring backup bucket")
        else:
            require(bucket["host_id"] not in media_hosts, "duplicate public media boundary")
            media_hosts.add(bucket["host_id"])
            require(bucket["retention_authority"] == "r2-lifecycle" and bucket["public"] is True
                    and bucket["object_expiry_days"] == 7 and bucket.get("public_hostname", "").endswith("." + domain["name"]), "unbounded public media retention")
    require(backup_hosts == set(hosts) and media_hosts == {host_id for host_id, host in hosts.items() if host["role"] == "publisher"}, "backup or public media coverage is incomplete")
    return tunnels


def documents(root=ROOT):
    return [yaml.safe_load((root / path).read_text()) for path in (
        "infra/tofu/cloudflare/routes.yml", "infra/inventories/production/hosts.yml",
        "infra/services/domains.yml", "infra/tofu/cloudflare/registrar.yml")]


def render(manifest, inventory, domains, registrar, host, include_planned=False):
    tunnels = validate(manifest, inventory, domains, registrar)
    require(host in tunnels, "undeclared ingress host")
    ingress = []
    for route in manifest["routes"]:
        if route["host_id"] != host or (route["status"] == "planned" and not include_planned):
            continue
        entry = {"hostname": route["hostname"], "service": route["origin"]}
        if route["caller"] == "machine":
            entry["path"] = r"^/webhook/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$"
        ingress.append(entry)
    return {"tunnel": tunnels[host]["id"], "ingress": ingress + [{"service": "http_status:404"}]}


if __name__ == '__main__':
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--include-planned',action='store_true')
    args=parser.parse_args()
    try:
        print(json.dumps(render(*documents(),args.host,args.include_planned),sort_keys=True,indent=2))
    except (ValueError,KeyError,TypeError):
        parser.exit(1,'invalid edge declaration; no ingress rendered\n')
