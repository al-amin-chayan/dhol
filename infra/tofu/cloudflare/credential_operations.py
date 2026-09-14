"""Credential issuance outside OpenTofu, immediately escrowed as SOPS ciphertext."""

import json
import os
import secrets

import yaml

import operations as op
from backend import digest
from receipt import input_digest
from routing import SERVICE_NAME


def blueprint(stage):
    if stage == "access":
        requests = [{"method": "POST", "path": f"/accounts/{op.ACCOUNT}/access/service_tokens",
                     "body": {"name": SERVICE_NAME, "duration": "forever"}}]
    elif stage == "storage":
        requests = [{"method": "POST", "path": f"/accounts/{op.ACCOUNT}/tokens", "name": name,
            "permission_group": "Workers R2 Storage Bucket Item Write",
            "resources": {f"com.cloudflare.edge.r2.bucket.{op.ACCOUNT}_default_{bucket}": "*"}}
            for name, bucket in (("dholbeat-restic-core", "dholbeat-core-backups"),
                ("dholbeat-restic-publisher", "dholbeat-publisher-backups"),
                ("dholbeat-publisher-media", "dholbeat-publisher-media"),
                ("dholbeat-source-escrow", "dholbeat-source-escrow"))]
    else:
        raise op.OperationError("unknown credential stage")
    return {"schema_version": 1, "document_type": "cloudflare-credential-plan", "stage": stage,
            "inputs_sha256": input_digest(op.ROOT), "requests": requests,
            "secrets_in_opentofu": False, "recovery_root_location": "password-manager",
            "software_monthly_usd": 0}


def load_set(name):
    # Preserve recoverable partial issuance; same-name live tokens still require
    # explicit recovery/rotation instead of silently issuing replacements.
    path = op.EVIDENCE / (name + ".sops.yml")
    if not path.exists():
        path = op.ROOT / "infra/secrets" / (name + ".sops.yml")
    if not path.exists():
        return {"schema_version": 1, "secret_set_id": name, "owner_project_id": "platform", "values": {}}
    documents = [yaml.safe_load(op.run(["sops", "--decrypt", str(path)],
        env={**os.environ, "SOPS_AGE_KEY_FILE": f"/run/{role}.age"}).stdout)
        for role in ("founder", "break-glass")]
    if documents[0] != documents[1] or documents[0].get("secret_set_id") != name:
        raise op.OperationError("existing scoped credential ciphertext failed independent recovery")
    validate_set(name, documents[0])
    return documents[0]


def validate_set(name, document):
    catalog = yaml.safe_load((op.ROOT / 'infra/secrets/catalog.yml').read_text())
    expected = {item['value_key'] for item in catalog['secrets']
                if item['sops_file'] == 'infra/secrets/' + name + '.sops.yml'}
    if (set(document) != {'schema_version', 'secret_set_id', 'owner_project_id', 'values'}
            or document['schema_version'] != 1 or document['secret_set_id'] != name
            or document['owner_project_id'] != 'platform' or not expected
            or not isinstance(document['values'], dict) or set(document['values']) != expected
            or any(not isinstance(v, str) or not v for v in document['values'].values())):
        raise op.OperationError('credential set differs from its complete scoped catalog')


def store(name, document):
    validate_set(name, document)
    plaintext = yaml.safe_dump(document).encode()
    encrypted = op.run(["sops", "--encrypt", "--config", str(op.ROOT / ".sops.yaml"),
        "--filename-override", "infra/secrets/" + name + ".sops.yml", "--input-type", "yaml",
        "--output-type", "yaml", "/dev/stdin"], data=plaintext).stdout
    path = op.EVIDENCE / (name + ".sops.yml")
    path.write_bytes(encrypted)
    path.chmod(0o600)
    for role in ("founder", "break-glass"):
        recovered = yaml.safe_load(op.run(["sops", "--decrypt", str(path)],
            env={**os.environ, "SOPS_AGE_KEY_FILE": f"/run/{role}.age"}).stdout)
        if recovered != document:
            raise op.OperationError("issued credential ciphertext failed SOPS MAC recovery")


def plan(stage):
    document = blueprint(stage)
    approval = digest(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    op.evidence("credential-plan-" + stage, {"approval_document": document, "approval_digest": approval})


def issue(inputs, stage):
    op.recipient_checks()
    document = blueprint(stage)
    approval = digest(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    if (os.environ.get("DHOLBEAT_APPROVED_ROUTING_DIGEST") != approval
            or not os.environ.get("DHOLBEAT_REVIEWED_HEAD")):
        raise op.OperationError("credential issuance requires founder-approved reviewed release plan")
    api = op.Cloudflare(inputs["CLOUDFLARE_API_TOKEN"])
    if stage == "access":
        value = load_set("publisher-access")
        existing = api.request("GET", f"/accounts/{op.ACCOUNT}/access/service_tokens")
        if any(t.get("name") == SERVICE_NAME for t in existing):
            raise op.OperationError("dedicated service token already exists; recover or rotate it explicitly")
        request = document["requests"][0]
        token = api.request(request["method"], request["path"], request["body"])
        try:
            if token.get("duration") != request["body"]["duration"] or token.get("enabled", True) is not True:
                raise op.OperationError("issued service token does not match the approved non-expiring lifetime")
            value["values"].update({"platform-n8n-publisher-access-client-id": token["client_id"],
                                    "platform-n8n-publisher-access-client-secret": token["client_secret"]})
            store("publisher-access", value)
        except BaseException:
            api.request("DELETE", f"/accounts/{op.ACCOUNT}/access/service_tokens/{token['id']}")
            raise
        identifiers = {SERVICE_NAME: token["id"]}
    else:
        groups = api.request("GET", f"/accounts/{op.ACCOUNT}/tokens/permission_groups")
        matching = [g for g in groups if g.get("name") == "Workers R2 Storage Bucket Item Write"]
        if len(matching) != 1:
            raise op.OperationError("bucket-only object-write permission could not be verified")
        group = matching[0]
        sets = {name: load_set(name) for name in ('core-backups', 'publisher-backups', 'publisher-media', 'source-escrow')}
        existing = api.request("GET", f"/accounts/{op.ACCOUNT}/tokens")
        if any(t.get("name") in {r["name"] for r in document["requests"]} for t in existing):
            raise op.OperationError("a scoped bucket credential already exists; recover rather than overwrite it")
        identifiers = {}
        owners = [("core-backups", "platform-core-backup"), ("publisher-backups", "platform-publisher-backup"),
                  ("publisher-media", "platform-publisher-media"), ("source-escrow", "platform-source-escrow")]
        for request, (owner, prefix) in zip(document["requests"], owners, strict=True):
            bucket = next(iter(request["resources"])).split("_default_", 1)[1]
            api.request("GET", f"/accounts/{op.ACCOUNT}/r2/buckets/{bucket}")
            token = api.request("POST", request["path"], {"name": request["name"], "policies": [{
                "effect": "allow", "permission_groups": [{"id": group["id"]}], "resources": request["resources"]}]})
            try:
                sets[owner]["values"].update({prefix + "-access-key": token["id"],
                    prefix + "-secret-access-key": digest(token["value"].encode())})
                password = {"core-backups": "platform-core-restic-password", "publisher-backups": "platform-publisher-restic-password",
                            "source-escrow": "platform-source-escrow-restic-password"}.get(owner)
                if password:
                    sets[owner]["values"].setdefault(password, secrets.token_urlsafe(48))
                store(owner, sets[owner])
            except BaseException:
                api.request("DELETE", f"/accounts/{op.ACCOUNT}/tokens/{token['id']}")
                raise
            identifiers[request["name"]] = token["id"]
        tunnel = load_set('publisher-tunnel')
        tunnel["values"]["platform-publisher-tunnel-token"] = api.request("GET",
            f"/accounts/{op.ACCOUNT}/cfd_tunnel/55d6ce3a-7abb-452b-b819-f2feb2fa2a58/token")
        store("publisher-tunnel", tunnel)
    op.evidence("credential-issue-" + stage, {"approved_digest": approval,
        "reviewed_head": os.environ["DHOLBEAT_REVIEWED_HEAD"], "credential_ids": identifiers,
        "ciphertext_mac_recovery": True, "password_manager_escrow": "founder-action-required",
        "opentofu_state_contains_credentials": False,
        **({"service_token_duration": token["duration"]} if stage == "access" else {})})
