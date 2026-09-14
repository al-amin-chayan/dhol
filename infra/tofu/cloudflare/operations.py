#!/usr/bin/env python3
"""Finite, value-redacted Cloudflare adoption operations in the locked controller."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml

from backend import (
    MAX_SNAPSHOTS,
    BackendError,
    NoRedirect,
    S3,
    digest,
    require_ciphertext,
    session,
    snapshot,
)
from control_plane import ContractError, no_change_plan
from edge import documents, render, validate
from receipt import input_digest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "infra/tofu/cloudflare"
CONFIG = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())
ACCOUNT = CONFIG["account_id"]
ZONE = CONFIG["zone_id"]
RECIPIENT_FINGERPRINTS = {}
EVIDENCE = Path("/evidence")
SECRET_PATH = ROOT / "infra/secrets/cloudflare.sops.yml"


def run(command, directory=None, env=None, data=None, codes=(0,)):
    result = subprocess.run(
        command, cwd=directory, env=env, input=data, capture_output=True, timeout=180
    )
    if result.returncode not in codes:
        raise OperationError(
            f"{command[0]} {command[1] if len(command) > 1 else ''} failed (exit {result.returncode}); output suppressed"
        )
    return result


def evidence(name, value):
    value = {**value, "recipient_fingerprints": RECIPIENT_FINGERPRINTS}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / (name + ".json")
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"operation": name, "status": "passed", **value}))


def recipient_checks():
    """Prove distinct private-key identities against the committed public policy."""
    policy = yaml.safe_load((ROOT / ".sops.yaml").read_text())
    declared = policy["creation_rules"][0]["key_groups"][0]["age"]
    recipients = {}
    for role in ("founder", "break-glass"):
        public = run(["age-keygen", "-y", f"/run/{role}.age"]).stdout.decode().strip()
        if not re.fullmatch(r"age1[0-9a-z]{58}", public):
            raise OperationError("operator key must contain exactly one age identity")
        recipients[role] = public
    if (
        len(declared) != 2
        or len(set(recipients.values())) != 2
        or set(recipients.values()) != set(declared)
    ):
        raise OperationError(
            "operator age identities must be distinct and match the committed policy"
        )
    return {role: digest(public.encode()) for role, public in recipients.items()}


def secret_set():
    recipient_checks()
    path = SECRET_PATH if SECRET_PATH.is_file() else EVIDENCE / "cloudflare.sops.yml"
    recovered = []
    for key in ("/run/founder.age", "/run/break-glass.age"):
        recovered.append(
            yaml.safe_load(
                run(
                    ["sops", "--decrypt", str(path)],
                    env={**os.environ, "SOPS_AGE_KEY_FILE": key},
                ).stdout
            )
        )
    if recovered[0] != recovered[1]:
        raise OperationError("independent recipient secret recovery differs")
    document = recovered[0]
    if (
        set(document)
        != {"schema_version", "secret_set_id", "owner_project_id", "values"}
        or document.get("secret_set_id") != "cloudflare"
        or document.get("schema_version") != 1
        or document.get("owner_project_id") != "platform"
        or set(document.get("values", {})) != {"platform-opentofu-state-passphrase"}
        or not isinstance(document["values"]["platform-opentofu-state-passphrase"], str)
        or len(document["values"]["platform-opentofu-state-passphrase"]) < 48
    ):
        raise OperationError("invalid controller secret-set identity")
    return document["values"]


def ensure_secret_set():
    recipient_checks()
    if SECRET_PATH.is_file() or (EVIDENCE / "cloudflare.sops.yml").is_file():
        return secret_set()
    document = {
        "schema_version": 1,
        "secret_set_id": "cloudflare",
        "owner_project_id": "platform",
        "values": {"platform-opentofu-state-passphrase": secrets.token_urlsafe(48)},
    }
    cipher = run(
        [
            "sops",
            "--encrypt",
            "--filename-override",
            "infra/secrets/cloudflare.sops.yml",
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "/dev/stdin",
        ],
        directory=ROOT,
        data=yaml.safe_dump(document).encode(),
    ).stdout
    for key in ("/run/founder.age", "/run/break-glass.age"):
        recovered = run(
            [
                "sops",
                "--decrypt",
                "--input-type",
                "yaml",
                "--output-type",
                "yaml",
                "/dev/stdin",
            ],
            env={**os.environ, "SOPS_AGE_KEY_FILE": key},
            data=cipher,
        ).stdout
        if yaml.safe_load(recovered) != document:
            raise OperationError("independent recipient recovery mismatch")
    (EVIDENCE / "cloudflare.sops.yml").write_bytes(cipher)
    return document["values"]


def root_api(inputs):
    token = inputs.get("CLOUDFLARE_R2_BOOTSTRAP_TOKEN")
    if not token:
        raise OperationError("R2 bootstrap credential is unavailable")
    return Cloudflare(token)


def bucket_session(inputs, bucket, prefixes, now=None):
    # R2's bootstrap token ID and SHA256(token) are its S3 parent pair.
    api = root_api(inputs)
    verified = api.request("GET", f"/accounts/{ACCOUNT}/tokens/verify")
    if verified.get("status") != "active":
        raise OperationError("R2 bootstrap root is not active")
    return session(
        ACCOUNT,
        verified["id"],
        digest(inputs["CLOUDFLARE_R2_BOOTSTRAP_TOKEN"].encode()),
        bucket,
        prefixes,
        now=now,
    )


def backend_config(key):
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    return {
        "bucket": config["bucket"],
        "key": key,
        "region": "auto",
        "use_lockfile": True,
        "endpoints": {"s3": f"https://{ACCOUNT}.r2.cloudflarestorage.com"},
        "skip_credentials_validation": True,
        "skip_region_validation": True,
        "skip_metadata_api_check": True,
        "skip_requesting_account_id": True,
        "skip_s3_checksum": True,
        "use_path_style": True,
    }


def environment(inputs, values, bucket, prefixes):
    return {
        **os.environ,
        **bucket_session(inputs, bucket, prefixes),
        "TF_VAR_state_passphrase": values["platform-opentofu-state-passphrase"],
        "CLOUDFLARE_API_TOKEN": inputs["CLOUDFLARE_API_TOKEN"],
        "TF_IN_AUTOMATION": "1",
        "TF_INPUT": "0",
        "CHECKPOINT_DISABLE": "1",
    }


def initialize(directory, env, key):
    config = directory / "backend.json"
    # This file contains only non-secret backend coordinates; credentials stay in environment.
    config.write_text(json.dumps(backend_config(key)))
    run(
        [
            "tofu",
            "init",
            "-input=false",
            "-backend-config=" + str(config),
            "-lockfile=readonly",
        ],
        directory,
        env,
    )
    executable_provider(directory)


def executable_provider(directory):
    architecture = "arm64" if platform.machine() in {"aarch64", "arm64"} else "amd64"
    path = (
        directory
        / f".terraform/providers/registry.opentofu.org/cloudflare/cloudflare/5.24.0/linux_{architecture}/terraform-provider-cloudflare_v5.24.0"
    )
    if path.is_file():
        # init has already authenticated the package against the committed dependency lock.
        # Normalize the verified package's executable permission before launching it.
        path.chmod(0o755)


def prepare(directory):
    docs = documents()
    validate(*docs)
    for pattern in ("*.tf", "*.yml", ".terraform.lock.hcl"):
        for path in PACKAGE.glob(pattern):
            shutil.copyfile(path, directory / path.name)
    (directory / "core-ingress.json").write_text(
        json.dumps(render(*docs, "core-1")["ingress"])
    )
    return json.loads((PACKAGE / "adoption.json").read_text())


def provider_validate(inputs):
    with tempfile.TemporaryDirectory(
        prefix="dholbeat-provider-validation-"
    ) as temporary:
        directory = Path(temporary)
        prepare(directory)
        env = {
            **os.environ,
            "TF_VAR_state_passphrase": secrets.token_urlsafe(48),
            "TF_INPUT": "0",
            "CHECKPOINT_DISABLE": "1",
        }
        run(
            ["tofu", "init", "-backend=false", "-lockfile=readonly", "-input=false"],
            directory,
            env,
        )
        executable_provider(directory)
        result = json.loads(
            run(["tofu", "validate", "-json"], directory, env, codes=(0, 1)).stdout
        )
        if not result.get("valid"):
            for diagnostic in result.get("diagnostics", []):
                # Summaries identify provider schema errors without displaying source snippets.
                print(
                    json.dumps(
                        {
                            "severity": diagnostic.get("severity"),
                            "summary": diagnostic.get("summary"),
                        }
                    )
                )
            raise OperationError("locked provider validation failed")
        evidence(
            "validate",
            {
                "provider_version": "5.24.0",
                "opentofu_version": "1.12.5",
                "provider_lock_sha256": digest(
                    (PACKAGE / ".terraform.lock.hcl").read_bytes()
                ),
            },
        )


def plan(inputs, adopt=False):
    values = secret_set()
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    env = environment(inputs, values, config["bucket"], ["cloudflare/"])
    source_digest = input_digest(ROOT)
    storage = S3(
        ACCOUNT,
        config["bucket"],
        {
            k: env[k]
            for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
        },
    )
    previous_state = storage.request("GET", config["key"], missing_ok=adopt)
    if previous_state is not None:
        require_ciphertext(previous_state)
    with tempfile.TemporaryDirectory(prefix="dholbeat-cloudflare-plan-") as temporary:
        directory = Path(temporary)
        expected = prepare(directory)
        initialize(directory, env, config["key"])
        from routing_operations import active, enable
        from routing import guard

        desired = enable(inputs, env) if active(directory, env) else {}
        if adopt and desired:
            raise OperationError("adoption is unavailable after publisher routing activation")
        run(["tofu", "validate"], directory, env)
        if adopt:
            imports = "\n".join(
                "import {\n  to = "
                + address
                + "\n  id = "
                + json.dumps(identity["import_id"])
                + "\n}"
                for address, identity in sorted(expected.items())
            )
            (directory / "imports.tf").write_text(imports + "\n")
        binary = directory / "plan.encrypted"
        result = run(
            [
                "tofu",
                "plan",
                "-json",
                "-input=false",
                "-detailed-exitcode",
                "-out=" + str(binary),
            ],
            directory,
            env,
            codes=(0, 1, 2),
        )
        if result.returncode == 1:
            for line in result.stdout.splitlines():
                event = json.loads(line)
                if event.get("type") == "diagnostic":
                    diagnostic = event.get("diagnostic", {})
                    print(
                        json.dumps(
                            {
                                "severity": diagnostic.get("severity"),
                                "summary": diagnostic.get("summary"),
                            }
                        )
                    )
            raise OperationError(
                "native provider plan failed; no resource changes applied"
            )
        document = json.loads(
            run(["tofu", "show", "-json", str(binary)], directory, env).stdout
        )
        try:
            if desired:
                guard(document, expected, desired)
            else:
                no_change_plan(document, expected)
        except ValueError as error:
            print(json.dumps({"guard_rejection": str(error)}))
            for change in document.get("resource_changes", []):
                delta = change["change"]
                if delta["actions"] != ["no-op"]:
                    before, after = delta.get("before") or {}, delta.get("after") or {}
                    print(
                        json.dumps(
                            {
                                "resource": change["address"],
                                "actions": delta["actions"],
                                "changed_attributes": sorted(
                                    k
                                    for k in set(before) | set(after)
                                    if before.get(k) != after.get(k)
                                ),
                            }
                        )
                    )
            raise OperationError(
                "provider plan is not no-change; nothing was applied"
            ) from None
        if input_digest(ROOT) != source_digest:
            raise OperationError("package inputs changed during the provider plan")
        if storage.request("GET", config["key"], missing_ok=adopt) != previous_state:
            raise OperationError("remote state changed during the provider plan")
        if adopt:
            # The only apply entry point accepts this exact guarded import-only encrypted binary.
            run(["tofu", "apply", "-input=false", str(binary)], directory, env)
            (directory / "imports.tf").unlink()
            run(
                [
                    "tofu",
                    "plan",
                    "-input=false",
                    "-detailed-exitcode",
                    "-out=" + str(binary),
                ],
                directory,
                env,
            )
            document = json.loads(
                run(["tofu", "show", "-json", str(binary)], directory, env).stdout
            )
            no_change_plan(document, expected)
        receipt = {
            "schema_version": 1,
            "package": "cloudflare",
            "provider_mutations": 0,
            "resource_count": len(expected) + len(desired),
            "routing_enabled": bool(desired),
            "provider_version": "5.24.0",
            "opentofu_version": "1.12.5",
            "encrypted_plan_sha256": digest(binary.read_bytes()),
            "inputs_sha256": source_digest,
            "imported": adopt,
            "observed_epoch": time.time(),
            "backend_bucket": config["bucket"],
            "backend_key": config["key"],
        }
        if desired:
            organization = Cloudflare(inputs['CLOUDFLARE_API_TOKEN']).request(
                'GET', f'/accounts/{ACCOUNT}/access/organizations'
            )
            auth_domain = organization.get('auth_domain', '')
            if not re.fullmatch(r'[a-z0-9-]+\.cloudflareaccess\.com', auth_domain):
                raise OperationError('Access organization auth domain is invalid')
            receipt['access_team_name'] = auth_domain.split('.')[0]
            receipt["publisher_access_audiences"] = [
                item["change"]["after"]["aud"]
                for item in document["resource_changes"]
                if item["address"] in {
                    "cloudflare_zero_trust_access_application.publisher_ui[0]",
                    "cloudflare_zero_trust_access_application.publisher_api[0]",
                }
            ]
        raw_state = storage.request("GET", config["key"])
        require_ciphertext(raw_state)
        if not adopt and raw_state != previous_state:
            raise OperationError("remote state changed before the no-change receipt")
        if input_digest(ROOT) != source_digest:
            raise OperationError("package inputs changed before the no-change receipt")
        receipt["encrypted_state_sha256"] = digest(raw_state)
        if adopt:
            receipt["recovery_snapshot"] = take_snapshot(inputs, emit=False)
        evidence("adopt" if adopt else "plan", receipt)


def take_snapshot(inputs, emit=True):
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    source = S3(
        ACCOUNT,
        config["bucket"],
        bucket_session(inputs, config["bucket"], ["cloudflare/"]),
    )
    recovery = S3(
        ACCOUNT,
        config["recovery_bucket"],
        bucket_session(inputs, config["recovery_bucket"], ["snapshots/"]),
    )
    receipt = snapshot(source, recovery, config["key"])
    if emit:
        evidence("snapshot", receipt)
    return receipt


def bootstrap(inputs):
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    initial = config["authority"] == "initial-bootstrap"
    if config["authority"] not in {"immutable-bootstrap", "initial-bootstrap"}:
        raise OperationError("unknown bootstrap authority")
    if initial and (
        config.get("bucket_id") is not None
        or config.get("recovery_bucket_id") is not None
    ):
        raise OperationError("initial bootstrap must not replace pinned roots")
    roots = (config["bucket"], config["recovery_bucket"])
    if len(set(roots)) != 2 or any(
        not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", name) for name in roots
    ):
        raise OperationError(
            "bootstrap requires two distinct valid reviewed root names"
        )
    approved = json.loads((PACKAGE / "bootstrap-roots.json").read_text())
    if (
        set(approved) != {"schema_version", "bucket", "recovery_bucket"}
        or approved["schema_version"] != 1
        or roots != (approved["bucket"], approved["recovery_bucket"])
    ):
        raise OperationError(
            "bootstrap root names differ from the committed authority pair"
        )
    api = root_api(inputs)
    existing = api.request("GET", f"/accounts/{ACCOUNT}/r2/buckets")["buckets"]
    names = {bucket["name"] for bucket in existing}
    bindings = {}
    for name in (config["bucket"], config["recovery_bucket"]):
        if name not in names:
            if not initial:
                raise OperationError(
                    "immutable backend root is missing; restore it through the documented bootstrap gate"
                )
            api.request(
                "POST",
                f"/accounts/{ACCOUNT}/r2/buckets",
                {"name": name, "locationHint": "apac", "storageClass": "Standard"},
            )
        public = api.request(
            "GET", f"/accounts/{ACCOUNT}/r2/buckets/{name}/domains/managed"
        )
        expected_id = (
            config["bucket_id"]
            if name == config["bucket"]
            else config["recovery_bucket_id"]
        )
        bindings[name] = public.get("bucketId")
        if not bindings[name] or (not initial and bindings[name] != expected_id):
            raise OperationError(
                "immutable backend bucket identity differs; refusing adoption"
            )
        custom = api.request(
            "GET", f"/accounts/{ACCOUNT}/r2/buckets/{name}/domains/custom"
        )
        lifecycle = api.request(
            "GET", f"/accounts/{ACCOUNT}/r2/buckets/{name}/lifecycle"
        )
        rules = lifecycle.get("rules", [])
        safe_multipart = all(
            set(rule)
            <= {"id", "enabled", "conditions", "abortMultipartUploadsTransition"}
            and "abortMultipartUploadsTransition" in rule
            for rule in rules
        )
        if public.get("enabled") or custom.get("domains") or not safe_multipart:
            raise OperationError(
                "immutable backend root is public or expires state objects; refusing adoption"
            )
    if initial:
        evidence(
            "bootstrap-provision",
            {
                "account_id": ACCOUNT,
                "immutable_root_candidates": bindings,
                "public": False,
                "state_initialized": False,
            },
        )
        return
    ensure_secret_set()
    recovery = S3(
        ACCOUNT,
        config["recovery_bucket"],
        bucket_session(
            inputs, config["recovery_bucket"], ["recovery/", "snapshots/", "drills/"]
        ),
    )
    cipher = (
        SECRET_PATH.read_bytes()
        if SECRET_PATH.is_file()
        else (EVIDENCE / "cloudflare.sops.yml").read_bytes()
    )
    stored = recovery.request("GET", "recovery/cloudflare.sops.yml", missing_ok=True)
    if stored is None:
        recovery.request(
            "PUT",
            "recovery/cloudflare.sops.yml",
            cipher,
            headers={"if-none-match": "*"},
        )
    elif stored != cipher:
        raise OperationError(
            "independent credential root differs or is absent; use the explicit recovery/rotation gate"
        )
    if digest(recovery.request("GET", "recovery/cloudflare.sops.yml")) != digest(
        cipher
    ):
        raise OperationError(
            "independent encrypted credential recovery read-back failed"
        )
    evidence(
        "bootstrap",
        {
            "account_id": ACCOUNT,
            "bucket": config["bucket"],
            "recovery_bucket": config["recovery_bucket"],
            "public": False,
            "credential_ciphertext_sha256": digest(cipher),
            "local_state_authority": False,
        },
    )


def delegation_drill(inputs):
    """Live scope/expiry enforcement, with existing-object positive controls."""
    config = CONFIG["backend"]
    primary = S3(
        ACCOUNT,
        config["bucket"],
        bucket_session(inputs, config["bucket"], ["cloudflare/"]),
    )
    recovery = S3(
        ACCOUNT,
        config["recovery_bucket"],
        bucket_session(inputs, config["recovery_bucket"], ["recovery/"]),
    )
    primary.request("HEAD", config["key"], status_only=True)
    recovery.request("HEAD", "recovery/cloudflare.sops.yml", status_only=True)
    scoped = bucket_session(inputs, config["bucket"], ["drills/"])
    storage = S3(ACCOUNT, config["bucket"], scoped)
    # One fixed, tiny, non-secret marker bounds leftovers even if the process dies.
    key = "drills/delegation-enforcement.probe"
    marker = secrets.token_hex(16).encode()
    storage.request("PUT", key, marker, headers={"if-none-match": "*"})
    try:
        if storage.request("GET", key) != marker:
            raise OperationError("delegation in-scope positive control differs")
        prefix_status = storage.request(
            "GET", config["key"], expected=(403,), status_only=True
        )
        bucket_status = S3(ACCOUNT, config["recovery_bucket"], scoped).request(
            "GET", "recovery/cloudflare.sops.yml", expected=(403,), status_only=True
        )
        expired = S3(
            ACCOUNT,
            config["bucket"],
            bucket_session(
                inputs, config["bucket"], ["drills/"], now=int(time.time()) - 7200
            ),
        )
        expiry_status = expired.request("GET", key, expected=(403,), status_only=True)
    finally:
        # Only a successful conditional create grants cleanup ownership.
        storage.request("DELETE", key, expected=(204,))
    evidence(
        "delegation-drill",
        {
            "in_scope_read_write": True,
            "target_objects_exist": True,
            "outside_prefix_http": prefix_status,
            "other_bucket_http": bucket_status,
            "expired_session_http": expiry_status,
            "probe_removed": True,
            "production_state_modified": False,
        },
    )


def recovery_drill(inputs):
    values = ensure_secret_set()
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    key = "drills/" + secrets.token_hex(16) + ".tfstate"
    env = environment(inputs, values, config["bucket"], ["drills/"])
    storage = S3(
        ACCOUNT,
        config["bucket"],
        {
            k: env[k]
            for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
        },
    )
    recovery = S3(
        ACCOUNT,
        config["recovery_bucket"],
        bucket_session(inputs, config["recovery_bucket"], ["drills/"]),
    )
    if len(storage.list("drills/")) >= MAX_SNAPSHOTS:
        raise OperationError(
            "disposable drill inventory reached its bound; recover locks and clean known drills first"
        )
    owned = {}
    try:
        _recovery_drill(inputs, values, config, key, env, storage, recovery, owned)
    finally:
        # Only this invocation's random keys are eligible for cleanup. Never remove another lock.
        for store, object_key in (
            (storage, key),
            (recovery, owned.get("snapshot_key", "")),
        ):
            if object_key:
                store.request("DELETE", object_key, expected=(204,))

    evidence(
        "recovery-drill",
        {
            "native_lock_contention": True,
            "wrong_unlock_rejected": True,
            "clean_clone_no_change": True,
            "wrong_encryption_key_rejected": True,
            "independent_ciphertext_recovered": True,
            "disposable_objects_removed": True,
        },
    )


def _recovery_drill(inputs, values, config, key, env, storage, recovery, owned):
    with tempfile.TemporaryDirectory(prefix="dholbeat-lock-drill-") as temporary:
        directory = Path(temporary)
        versions = (PACKAGE / "versions.tf").read_text()
        # Exact production encryption/backend code; the drill uses only OpenTofu's built-in provider.
        start = versions.index("  required_providers {")
        end = versions.index('  backend "s3" {}')
        versions = versions[:start] + versions[end:]
        versions = versions.replace('provider "cloudflare" {}', "")
        (directory / "versions.tf").write_text(versions)
        (directory / "drill.tf").write_text(
            'resource "terraform_data" "proof" { input = "disposable-lock-recovery-proof" }\n'
        )
        initialize(directory, env, key)
        run(["tofu", "apply", "-auto-approve", "-input=false"], directory, env)
        raw = storage.request("GET", key)
        print(json.dumps({"encrypted_state_envelope_fields": sorted(json.loads(raw))}))
        require_ciphertext(raw)
        copied = snapshot(storage, recovery, key, "drills/")
        owned["snapshot_key"] = copied["snapshot_key"]
        # Empty clone: no .terraform, local state, provider cache, or copied working directory.
        clone = directory / "clean-clone"
        clone.mkdir()
        for name in ("versions.tf", "drill.tf"):
            shutil.copyfile(directory / name, clone / name)
        initialize(clone, env, key)
        run(["tofu", "plan", "-detailed-exitcode", "-input=false"], clone, env)
        state = json.loads(run(["tofu", "state", "pull"], clone, env).stdout)
        if len(state.get("resources", [])) != 1:
            raise OperationError("clean-clone resource recovery mismatch")
        # Exercise native OpenTofu contention against the documented native lock format.
        lock_id = secrets.token_hex(16)
        lock = {
            "ID": lock_id,
            "Operation": "OperationTypeApply",
            "Info": "Dholbeat disposable contention drill",
            "Who": "controller@disposable",
            "Version": "1.12.5",
            "Created": datetime.now(timezone.utc).isoformat(),
            "Path": config["bucket"] + "/" + key,
        }
        storage.request(
            "PUT",
            key + ".tflock",
            json.dumps(lock).encode(),
            headers={"if-none-match": "*"},
        )
        try:
            contender = run(
                ["tofu", "apply", "-auto-approve", "-input=false", "-lock-timeout=0s"],
                clone,
                env,
                codes=(1,),
            )
            if (
                b"Error acquiring the state lock"
                not in contender.stderr + contender.stdout
            ):
                raise OperationError(
                    "native lock contention did not reject the second writer"
                )
            run(
                ["tofu", "force-unlock", "-force", "wrong-lock-id"],
                clone,
                env,
                codes=(1,),
            )
            if json.loads(storage.request("GET", key + ".tflock"))["ID"] != lock_id:
                raise OperationError("wrong unlock identity removed the lock")
        finally:
            run(["tofu", "force-unlock", "-force", lock_id], clone, env)
        run(["tofu", "apply", "-auto-approve", "-input=false"], clone, env)
        wrong = {**env, "TF_VAR_state_passphrase": secrets.token_urlsafe(48)}
        run(["tofu", "state", "pull"], clone, wrong, codes=(1,))
        # Recover from independent ciphertext, not from the primary state object.
        if digest(recovery.request("GET", copied["snapshot_key"])) != digest(raw):
            raise OperationError("independent state ciphertext recovery mismatch")
        storage.request("DELETE", key, expected=(204,))
        storage.request(
            "PUT",
            key,
            recovery.request("GET", copied["snapshot_key"]),
            headers={"if-none-match": "*"},
        )
        restored = json.loads(run(["tofu", "state", "pull"], clone, env).stdout)
        if (
            restored["lineage"] != state["lineage"]
            or restored["resources"] != state["resources"]
        ):
            raise OperationError("independent decrypted state restoration mismatch")
        run(["tofu", "plan", "-detailed-exitcode", "-input=false"], clone, env)
        storage.request("DELETE", key, expected=(204,))
        recovery.request("DELETE", copied["snapshot_key"], expected=(204,))


class OperationError(Exception):
    """Safe, value-free operator diagnostic."""


def credentials(path: Path) -> dict[str, str]:
    allowed = {
        "CLOUDFLARE_API_TOKEN",
        "CF_ACCOUNT_ID",
        "CLOUDFLARE_R2_BOOTSTRAP_TOKEN",
        "CLOUDFLARE_R2_PARENT_TOKEN",
        "R2_PARENT_ACCESS_KEY_ID",
        "R2_PARENT_SECRET_ACCESS_KEY",
    }
    allowed |= {
        "N8N_ACCESS_CLIENT_ID",
        "N8N_ACCESS_CLIENT_SECRET",
        "PUBLISHER_API_KEY",
        "PROBE_CORE_1_IP",
        "PROBE_PUBLISH_1_IP",
        "MEDIA_PROBE_PATH",
        "MEDIA_PROBE_SHA256",
    }
    allowed |= {
        "FOUNDER_ACCESS_JWT_" + identifier.replace("-", "_").upper()
        for identifier in ("paperclip-admin", "n8n-admin", "publisher-admin-api")
    }
    result = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.removeprefix("export ").partition("=")
        if separator and key in allowed:
            result[key] = value.strip().strip("\"'")
    if result.get("CF_ACCOUNT_ID") != ACCOUNT or not result.get("CLOUDFLARE_API_TOKEN"):
        raise OperationError("bootstrap account identity or API credential is missing")
    return result


class Cloudflare:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, body=None):
        request = urllib.request.Request(
            "https://api.cloudflare.com/client/v4" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=30
            ) as response:
                document = json.load(response)
        except urllib.error.HTTPError as error:
            raise OperationError(
                f"Cloudflare operation rejected (HTTP {error.code})"
            ) from None
        if not document.get("success"):
            raise OperationError("Cloudflare operation returned an unsuccessful result")
        return document.get("result")


def discover(inputs):
    for key in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_R2_BOOTSTRAP_TOKEN",
        "CLOUDFLARE_R2_PARENT_TOKEN",
    ):
        if not inputs.get(key):
            continue
        api = Cloudflare(inputs[key])
        for path in (
            f"/accounts/{ACCOUNT}/r2/buckets",
            f"/accounts/{ACCOUNT}/cfd_tunnel",
            f"/zones/{ZONE}",
        ):
            try:
                api.request("GET", path)
                print(
                    json.dumps(
                        {
                            "credential_reference": key,
                            "endpoint": path,
                            "status": "read permitted",
                        }
                    )
                )
            except OperationError as error:
                print(
                    json.dumps(
                        {
                            "credential_reference": key,
                            "endpoint": path,
                            "status": str(error),
                        }
                    )
                )
        for path in (
            f"/accounts/{ACCOUNT}/tokens/permission_groups",
            "/user/tokens/permission_groups",
        ):
            try:
                groups = api.request("GET", path)
                print(
                    json.dumps(
                        {
                            "credential_reference": key,
                            "endpoint": path,
                            "permission_groups": [
                                {"id": g["id"], "name": g["name"]} for g in groups
                            ],
                        }
                    )
                )
            except OperationError as error:
                print(
                    json.dumps(
                        {
                            "credential_reference": key,
                            "endpoint": path,
                            "status": str(error),
                        }
                    )
                )


def verify(inputs):
    from probes import check, matrix, request, verify_founder_policy

    docs = documents()
    validate(*docs)
    api = Cloudflare(inputs["CLOUDFLARE_API_TOKEN"])
    expected = json.loads((PACKAGE / "adoption.json").read_text())
    application_id = expected["cloudflare_zero_trust_access_application.team"][
        "resource_id"
    ]
    policy_id = expected["cloudflare_zero_trust_access_policy.founder"]["resource_id"]
    application = api.request(
        "GET", f"/accounts/{ACCOUNT}/access/apps/{application_id}"
    )
    policy = api.request("GET", f"/accounts/{ACCOUNT}/access/policies/{policy_id}")
    route = next(
        route
        for route in docs[0]["routes"]
        if route["id"] == CONFIG["adopted_human_route_id"]
    )
    verify_founder_policy(
        application, policy, route["hostname"], CONFIG["founder_email"]
    )
    domain = next(
        domain for domain in docs[2]["domains"] if domain["id"] == docs[3]["domain_id"]
    )
    zone = api.request("GET", f"/zones/{ZONE}")
    registrar = api.request(
        "GET", f"/accounts/{ACCOUNT}/registrar/domains/{domain['name']}"
    )
    if set(zone["name_servers"]) != set(domain["expected_nameservers"]):
        raise OperationError("provider nameservers differ")
    if (
        registrar.get("auto_renew") is not True
        or registrar.get("expires_at") != docs[3]["renewal_evidence"]["expires_on"]
    ):
        raise OperationError("registrar renewal evidence differs")
    # Query the parent delegation independently of the zone API and recursive resolver cache.
    expected_ns = set(docs[3]["delegation_evidence"]["expected_nameservers"])
    for parent in docs[3]["delegation_evidence"]["independent_parent_servers"]:
        from delegation import nameservers

        if nameservers(parent, domain["name"]) != expected_ns:
            raise OperationError("independent parent delegation differs")
    check("unauthenticated", request(route["hostname"]))
    # This child imports existing resources only. It must report future security gates honestly.
    deferred = {
        route["id"]: route["status"]
        for route in docs[0]["routes"]
        if route["status"] != "adopted"
    }
    evidence(
        "verify",
        {
            "existing_founder_access": True,
            "unauthenticated_denied": True,
            "independent_parent_delegation": True,
            "registrar_renewal": True,
            "promotion_probe_contracts": matrix(docs[0]),
            "deferred_routes": deferred,
            "core_host_contacted": False,
            "provider_mutations": 0,
        },
    )


def validate_recovery_request(request, config):
    if (
        set(request)
        != {
            "schema_version",
            "snapshot_key",
            "sha256",
            "backend_bucket",
            "backend_key",
            "expected_primary_absent",
        }
        or request["schema_version"] != 1
        or request["expected_primary_absent"] is not True
        or request["backend_bucket"] != config["bucket"]
        or request["backend_key"] != config["key"]
        or not re.fullmatch(
            r"snapshots/[0-9]{8}T[0-9]{12}Z-[a-f0-9]{64}\.tfstate",
            request["snapshot_key"],
        )
        or not re.fullmatch(r"[a-f0-9]{64}", request["sha256"])
    ):
        raise OperationError(
            "recovery request does not bind the absent primary and reviewed snapshot"
        )


def restore(inputs):
    request = json.loads(Path("/run/recovery-request.json").read_text())
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    validate_recovery_request(request, config)
    values = secret_set()
    primary = S3(
        ACCOUNT,
        config["bucket"],
        bucket_session(inputs, config["bucket"], ["cloudflare/"]),
    )
    recovery_env = environment(
        inputs, values, config["recovery_bucket"], ["snapshots/"]
    )
    recovery = S3(
        ACCOUNT,
        config["recovery_bucket"],
        {
            k: recovery_env[k]
            for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
        },
    )
    if primary.request("GET", config["key"], missing_ok=True) is not None:
        raise OperationError("primary state exists; never overwrite it during recovery")
    cipher = recovery.request("GET", request["snapshot_key"])
    require_ciphertext(cipher)
    if digest(cipher) != request["sha256"]:
        raise OperationError("reviewed recovery digest differs")
    # Decrypt and validate from the independent backend BEFORE touching the primary.
    with tempfile.TemporaryDirectory(
        prefix="dholbeat-independent-recovery-"
    ) as temporary:
        directory = Path(temporary)
        expected = prepare(directory)
        coordinates = {
            **backend_config(request["snapshot_key"]),
            "bucket": config["recovery_bucket"],
        }
        (directory / "backend.json").write_text(json.dumps(coordinates))
        run(
            [
                "tofu",
                "init",
                "-input=false",
                "-backend-config=" + str(directory / "backend.json"),
                "-lockfile=readonly",
            ],
            directory,
            recovery_env,
        )
        executable_provider(directory)
        state = json.loads(
            run(["tofu", "state", "pull"], directory, recovery_env).stdout
        )
        identities = {}
        for resource in state.get("resources", []):
            address = resource["type"] + "." + resource["name"]
            instances = resource.get("instances", [])
            if address in identities or resource.get("module") or len(instances) != 1:
                raise OperationError("recovered state inventory is unexpected")
            identities[address] = instances[0]["attributes"]["id"]
        if identities != {
            address: identity["resource_id"] for address, identity in expected.items()
        }:
            raise OperationError("recovered provider identities differ")
    # Conditional create protects against a concurrent restore or a newly initialized primary.
    primary.request("PUT", config["key"], cipher, headers={"if-none-match": "*"})
    if primary.request("GET", config["key"]) != cipher:
        raise OperationError("restored ciphertext read-back differs")
    evidence(
        "restore",
        {
            "provider_mutations": 0,
            "encrypted_state_sha256": digest(cipher),
            "resource_count": len(expected),
            "independent_decryption_verified": True,
        },
    )


def clean_drills(inputs):
    """Remove only unlocked, cryptographically verified, disposable built-in-provider state."""
    config = yaml.safe_load((PACKAGE / "bootstrap.yml").read_text())["backend"]
    env = environment(inputs, secret_set(), config["bucket"], ["drills/"])
    storage = S3(
        ACCOUNT,
        config["bucket"],
        {
            k: env[k]
            for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
        },
    )
    keys = storage.list("drills/")
    if any(not re.fullmatch(r"drills/[a-f0-9]{32}\.tfstate", key) for key in keys):
        raise OperationError(
            "drill inventory includes a lock or unknown object; nothing removed"
        )
    eligible = []
    with tempfile.TemporaryDirectory(
        prefix="dholbeat-disposable-cleanup-"
    ) as temporary:
        versions = (PACKAGE / "versions.tf").read_text()
        versions = (
            versions[: versions.index("  required_providers {")]
            + versions[versions.index('  backend "s3" {}') :]
        )
        for key in keys:
            directory = Path(temporary) / key.split("/")[-1]
            directory.mkdir()
            (directory / "versions.tf").write_text(
                versions.replace('provider "cloudflare" {}', "")
            )
            raw = storage.request("GET", key)
            require_ciphertext(raw)
            initialize(directory, env, key)
            state = json.loads(run(["tofu", "state", "pull"], directory, env).stdout)
            resources = state.get("resources", [])
            if (
                len(resources) != 1
                or resources[0].get("type") != "terraform_data"
                or resources[0].get("name") != "proof"
                or resources[0]["instances"][0]["attributes"].get("input")
                != {"type": "string", "value": "disposable-lock-recovery-proof"}
            ):
                raise OperationError(
                    "state is not the disposable drill; nothing removed"
                )
            eligible.append((key, raw))
    for key, raw in eligible:
        if (
            storage.request("GET", key + ".tflock", missing_ok=True) is not None
            or storage.request("GET", key) != raw
        ):
            raise OperationError("drill is locked or changed; refusing cleanup")
        storage.request("DELETE", key, expected=(204,))
    evidence(
        "clean-drills",
        {
            "disposable_objects_removed": len(eligible),
            "production_state_untouched": True,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=[
            "discover",
            "validate",
            "bootstrap",
            "adopt",
            "plan",
            "routing-plan",
            "routing-apply",
            "routing-verify",
            "credential-plan-access",
            "credential-plan-storage",
            "credential-issue-access",
            "credential-issue-storage",
            "verify",
            "recovery-drill",
            "delegation-drill",
            "snapshot",
            "probe",
            "restore",
            "clean-drills",
        ],
    )
    args = parser.parse_args()
    if os.environ.get("DHOLBEAT_IN_CONTROLLER") != "1":
        raise OperationError("run through scripts/cloudflare and the locked controller")
    global RECIPIENT_FINGERPRINTS
    RECIPIENT_FINGERPRINTS = recipient_checks()
    inputs = credentials(Path("/run/bootstrap.env"))
    if args.operation == "discover":
        discover(inputs)
    elif args.operation == "bootstrap":
        bootstrap(inputs)
    elif args.operation == "delegation-drill":
        delegation_drill(inputs)
    elif args.operation == "recovery-drill":
        recovery_drill(inputs)
    elif args.operation == "validate":
        provider_validate(inputs)
    elif args.operation == "adopt":
        plan(inputs, adopt=True)
    elif args.operation == "plan":
        plan(inputs)
    elif args.operation in {"routing-plan", "routing-apply"}:
        import routing_operations

        routing_operations.plan(inputs, apply=args.operation == "routing-apply")
    elif args.operation == 'routing-verify':
        import routing_verify

        routing_verify.verify(inputs)
    elif args.operation.startswith("credential-"):
        import credential_operations

        stage = args.operation.rsplit("-", 1)[1]
        if args.operation.startswith("credential-plan-"):
            credential_operations.plan(stage)
        else:
            credential_operations.issue(inputs, stage)
    elif args.operation == "snapshot":
        take_snapshot(inputs)
    elif args.operation == "verify":
        verify(inputs)
    elif args.operation == "restore":
        restore(inputs)
    elif args.operation == "clean-drills":
        clean_drills(inputs)
    elif args.operation == "probe":
        from probes import run_live

        docs = documents()
        validate(*docs)
        results = run_live(docs[0], inputs)
        complete = all(
            all(value in {"accepted", "denied"} for value in result.values())
            for result in results.values()
        )
        evidence(
            "probe", {"provider_mutations": 0, "complete": complete, "results": results}
        )


if __name__ == "__main__":
    try:
        main()
    except (
        OperationError,
        BackendError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
        subprocess.TimeoutExpired,
    ) as error:
        # Never include provider response bodies, subprocess output or values.
        print(
            str(error)
            if isinstance(error, (OperationError, BackendError, ContractError))
            else "control-plane operation failed safely"
        )
        raise SystemExit(1) from None
