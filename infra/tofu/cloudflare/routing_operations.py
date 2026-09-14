"""Staged routing changes through the encrypted native OpenTofu backend."""

import json
import os
from pathlib import Path
import tempfile
import time
import re

import operations as op
from backend import S3, digest, require_ciphertext
from edge import documents
from receipt import input_digest
from routing import footprint, guard, token_identity
from control_plane import ContractError


def enable(inputs, env):
    token = token_identity(op.Cloudflare(inputs["CLOUDFLARE_API_TOKEN"]), op.ACCOUNT)
    env.update({"TF_VAR_publisher_routing_enabled": "true", "TF_VAR_publisher_service_token_id": token})
    return footprint(documents()[0], op.CONFIG, token)


def active(directory, env):
    return any(line.startswith(("cloudflare_r2_bucket.runtime[", "cloudflare_zero_trust_access_application.publisher_"))
        for line in op.run(["tofu", "state", "list"], directory, env).stdout.decode().splitlines())


def no_change(document, expected, desired):
    guard(document, expected, desired)


def plan(inputs, *, apply=False):
    values = op.secret_set()
    backend = op.CONFIG["backend"]
    env = op.environment(inputs, values, backend["bucket"], ["cloudflare/"])
    desired = enable(inputs, env)
    source = input_digest(op.ROOT)
    storage = S3(op.ACCOUNT, backend["bucket"], {k: env[k] for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")})
    state = storage.request("GET", backend["key"])
    require_ciphertext(state)
    with tempfile.TemporaryDirectory(prefix="routing-") as temporary:
        directory = Path(temporary)
        expected = op.prepare(directory)
        op.initialize(directory, env, backend["key"])
        op.run(["tofu", "validate"], directory, env)
        binary = directory / "routing.encrypted"
        op.run(["tofu", "plan", "-input=false", "-detailed-exitcode", "-out=" + str(binary)],
               directory, env, codes=(0, 2))
        document = json.loads(op.run(["tofu", "show", "-json", str(binary)], directory, env).stdout)
        actions = guard(document, expected, desired, allow_create=True, allow_observations=True)
        summary = {"schema_version": 1, "document_type": "cloudflare-routing-plan", "host_id": "publish-1",
            "inputs_sha256": source, "encrypted_state_sha256": digest(state), "resources": actions,
            "new_configuration_sha256": digest(json.dumps({v["address"]: v["change"] for v in document["resource_changes"]
                if v["address"] in desired}, sort_keys=True, separators=(",", ":")).encode()),
            "service_token_id": env["TF_VAR_publisher_service_token_id"], "imported_mutations": 0,
            "private_backup_expiry": None, "media_expiry_days": 7, "new_software_monthly_usd": 0}
        approval_digest = digest(json.dumps(summary, sort_keys=True, separators=(",", ":")).encode())
        if input_digest(op.ROOT) != source or storage.request("GET", backend["key"]) != state:
            raise op.OperationError("routing source or remote state changed during plan")
        if apply:
            if os.environ.get("DHOLBEAT_APPROVED_ROUTING_DIGEST") != approval_digest or not os.environ.get("DHOLBEAT_REVIEWED_HEAD"):
                raise op.OperationError("fresh routing plan differs from founder-approved release plan")
            previous_snapshot = op.take_snapshot(inputs, emit=False)
            require_ciphertext(binary.read_bytes())
            apply_completed, guard_passed, final = False, False, None
            try:
                op.run(["tofu", "apply", "-input=false", str(binary)], directory, env)
                apply_completed = True
                op.run(["tofu", "plan", "-input=false", "-detailed-exitcode", "-out=" + str(binary)], directory, env)
                final = json.loads(op.run(["tofu", "show", "-json", str(binary)], directory, env).stdout)
                guard(final, expected, desired, allow_observations=True)
                guard_passed = True
                recovery = op.take_snapshot(inputs, emit=False)
            except Exception as error:
                # Native apply may already have persisted changes. Never turn a
                # rejection into success or lose its record if snapshot fails.
                recovery, snapshot_error = None, None
                try:
                    recovery = op.take_snapshot(inputs, emit=False)
                except Exception as failure:
                    snapshot_error = type(failure).__name__
                metadata = []
                records = final.get("resource_changes", []) if isinstance(final, dict) else []
                if not isinstance(records, list):
                    records = []
                for item in records:
                    if not isinstance(item, dict):
                        continue
                    if not isinstance(item.get("address"), str) or item["address"] not in set(expected) | set(desired):
                        continue
                    change = item.get("change", {})
                    if not isinstance(change, dict):
                        change = {}
                    after = change.get("after")
                    identifier = after.get("id") if isinstance(after, dict) else None
                    # IDs are public provider identities; never serialize other
                    # response values, or a malformed ID that could be a secret.
                    if not isinstance(identifier, str) or not re.fullmatch(
                            r"(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", identifier):
                        identifier = None
                    actions_seen = change.get("actions")
                    if not isinstance(actions_seen, list) or any(not isinstance(action, str) or action not in {
                            "no-op", "create", "update", "delete", "read"} for action in actions_seen):
                        actions_seen = None
                    metadata.append({"address": item["address"], "actions": actions_seen, "id": identifier})
                op.evidence("routing-apply-rejected", {
                    "status": "rejected",
                    "reviewed_head": os.environ["DHOLBEAT_REVIEWED_HEAD"],
                    "approved_digest": approval_digest, "apply_completed": apply_completed,
                    "provider_changes_may_have_occurred": True, "post_apply_no_change": guard_passed,
                    "safe_reason": str(error) if isinstance(error, (ContractError, op.OperationError)) else "post-apply operation failed",
                    "error_class": type(error).__name__, "planned_resource_actions": actions,
                    "post_apply_resources": metadata, "previous_snapshot": previous_snapshot,
                    "recovery_snapshot": recovery, "snapshot_error_class": snapshot_error,
                    "observed_epoch": time.time()})
                raise
            op.evidence("routing-apply", {"reviewed_head": os.environ["DHOLBEAT_REVIEWED_HEAD"],
                "approved_digest": approval_digest, "post_apply_no_change": True, "resource_count": len(actions),
                "resource_ids": {v["address"]: v["change"]["after"].get("id") for v in final["resource_changes"]},
                "recovery_snapshot": recovery, "observed_epoch": time.time()})
        else:
            op.evidence("routing-plan", {"approval_digest": approval_digest, "approval_document": summary,
                "encrypted_plan_sha256": digest(binary.read_bytes()), "observed_epoch": time.time()})
