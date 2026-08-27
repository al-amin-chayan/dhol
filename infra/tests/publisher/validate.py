#!/usr/bin/env python3
"""Validate the selected publisher's offline deployment contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
import yaml


EXPECTED_SERVICES = {
    "postiz",
    "postiz-postgres",
    "postiz-redis",
    "temporal",
    "temporal-postgres",
    "temporal-elasticsearch",
}
EXPECTED_IMAGES = {
    "postiz": "ghcr.io/gitroomhq/postiz-app:v2.23.0@sha256:785f97312f66a347fb96cdccc4ded5a33ced69a672c89a9adc8054e7d6a21dc5",
    "postiz-postgres": "postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73",
    "postiz-redis": "redis:7.2@sha256:0ba67a00a5ad74574c046711778742c6247f5053b0dca3fdb6ddacd7a82bdc39",
    "temporal-postgres": "postgres:16@sha256:e17e86066e5ef83e0952a9347f5c792b7ece00972e2aa787a6986f471b3dd3d5",
    "temporal-elasticsearch": "elasticsearch:7.17.27@sha256:9a6443f55243f6acbfeb4a112d15eb3b9aac74bf25e0e39fa19b3ddd3a6879d0",
    "temporal": "temporalio/auto-setup:1.28.1@sha256:607d68caa111338d754771efb876c92dfcdae06d056e4530bb31cd0f37406e6a",
}
COMPOSE_TO_REGISTRY = {
    "postiz": "publisher",
    "postiz-postgres": "publisher-postgres",
    "postiz-redis": "publisher-redis",
    "temporal": "publisher-temporal",
    "temporal-postgres": "publisher-temporal-postgres",
    "temporal-elasticsearch": "publisher-temporal-visibility",
}
EXPECTED_REGISTRY_VOLUMES = {
    "publisher": [],
    "publisher-postgres": ["publisher-postgres-data"],
    "publisher-redis": ["publisher-redis-data"],
    "publisher-temporal": [],
    "publisher-temporal-postgres": ["publisher-temporal-postgres-data"],
    "publisher-temporal-visibility": [
        "publisher-temporal-visibility-data",
        "publisher-backup-staging",
    ],
}
STATE_SERVICES = EXPECTED_SERVICES - {"postiz"}
RETAINED_VOLUME_NAMES = {
    "postiz-postgres-data",
    "postiz-redis-data",
    "temporal-postgres-data",
    "temporal-elasticsearch-data",
}
IMAGE_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
REQUIRED_RUNTIME_VARIABLE_RE = re.compile(r"^\$\{[A-Z][A-Z0-9_]+:\?.+\}$")


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return document


def memory_mebibytes(value: Any) -> int:
    text = str(value).strip().lower()
    match = re.fullmatch(r"([0-9]+)([mg])", text)
    if match is None:
        raise ValueError(f"memory limit must use integral m or g units: {value}")
    number = int(match.group(1))
    unit = match.group(2)
    return number * {"m": 1, "g": 1024}[unit]


def validate_compose(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    services = document.get("services")
    if not isinstance(services, dict):
        return ["compose: services must be a mapping"]
    if set(services) != EXPECTED_SERVICES:
        findings.append("compose: deploy exactly the selected six-container topology")

    total_memory = 0
    for service_id in sorted(EXPECTED_SERVICES & set(services)):
        service = services[service_id]
        image = service.get("image")
        if image != EXPECTED_IMAGES[service_id]:
            findings.append(f"{service_id}: image differs from the selected digest pin")
        if not isinstance(image, str) or IMAGE_DIGEST_RE.search(image) is None:
            findings.append(f"{service_id}: image is not digest-pinned")
        logging = service.get("logging", {})
        options = logging.get("options", {}) if isinstance(logging, dict) else {}
        if logging.get("driver") != "json-file" or not options.get("max-size") or not options.get("max-file"):
            findings.append(f"{service_id}: Docker logs are not bounded")
        if "mem_limit" not in service or "pids_limit" not in service:
            findings.append(f"{service_id}: memory and PID limits are required")
        else:
            try:
                total_memory += memory_mebibytes(service["mem_limit"])
            except ValueError as error:
                findings.append(f"{service_id}: {error}")
        if service_id in STATE_SERVICES and service.get("ports"):
            findings.append(f"{service_id}: state service publishes a host port")
        if service_id in STATE_SERVICES and service.get("networks") != ["publisher-state"]:
            findings.append(f"{service_id}: state service must join only publisher-state")

    if total_memory > 4608:
        findings.append(f"compose: aggregate memory limit {total_memory} MiB exceeds 4608 MiB")

    postiz = services.get("postiz", {})
    ports = postiz.get("ports", [])
    if len(ports) != 1 or not str(ports[0]).startswith("127.0.0.1:"):
        findings.append("postiz: the only published port must bind to loopback")
    environment = postiz.get("environment", {})
    if environment.get("STORAGE_PROVIDER") != "cloudflare":
        findings.append("postiz: media storage must use the dedicated Cloudflare R2 provider")
    if environment.get("UPLOAD_DIRECTORY") or environment.get("NEXT_PUBLIC_UPLOAD_DIRECTORY"):
        findings.append("postiz: local upload persistence is forbidden")
    tmpfs = postiz.get("tmpfs", [])
    if tmpfs != ["/tmp:size=268435456,mode=1777"]:
        findings.append("postiz: /tmp tmpfs must be exactly 256 MiB")
    registration = environment.get("DISABLE_REGISTRATION")
    if not isinstance(registration, str) or REQUIRED_RUNTIME_VARIABLE_RE.fullmatch(registration) is None:
        findings.append("postiz: registration state must be a required runtime variable")

    networks = document.get("networks", {})
    state_network = networks.get("publisher-state", {}) if isinstance(networks, dict) else {}
    if state_network.get("internal") is not True:
        findings.append("compose: publisher-state must be an internal network")
    if any(isinstance(spec, dict) and "name" in spec for spec in networks.values()):
        findings.append("compose: explicit network names would break disposable restore isolation")

    volumes = document.get("volumes", {})
    if any(isinstance(spec, dict) and "name" in spec for spec in volumes.values()):
        findings.append("compose: explicit volume names would reuse production state during restore")
    retained = {
        volume_id
        for volume_id, spec in volumes.items()
        if isinstance(spec, dict)
        and spec.get("labels", {}).get("com.dholbeat.retention") == "retained"
    }
    if retained != RETAINED_VOLUME_NAMES:
        findings.append("compose: retained Postiz, Temporal, and Visibility volumes are incomplete")

    elasticsearch = services.get("temporal-elasticsearch", {})
    es_environment = elasticsearch.get("environment", {})
    es_volumes = elasticsearch.get("volumes", [])
    has_snapshot_bind = any(
        isinstance(volume, dict)
        and volume.get("type") == "bind"
        and volume.get("target") == "/snapshots"
        for volume in es_volumes
    )
    if es_environment.get("path.repo") != "/snapshots" or not has_snapshot_bind:
        findings.append("temporal-elasticsearch: filesystem snapshot repository is required")
    temporal = services.get("temporal", {})
    if temporal.get("environment", {}).get("ENABLE_ES") != "true":
        findings.append("temporal: Elasticsearch Visibility must remain enabled")
    redis = services.get("postiz-redis", {})
    redis_command = redis.get("command", [])
    if not all(
        value in redis_command
        for value in ("--appendonly", "yes", "--maxmemory-policy", "noeviction")
    ):
        findings.append("postiz-redis: retained state requires AOF and noeviction")
    if redis.get("volumes") != ["postiz-redis-data:/data"]:
        findings.append("postiz-redis: retained data volume is required")
    return sorted(set(findings))


def validate_restore_override(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    postiz = document.get("services", {}).get("postiz", {})
    if postiz.get("environment", {}).get("RUN_CRON") != "false":
        findings.append("restore override: Postiz cron must be disabled")
    elasticsearch = document.get("services", {}).get("temporal-elasticsearch", {})
    snapshot_mounts = [
        volume
        for volume in elasticsearch.get("volumes", [])
        if isinstance(volume, dict) and volume.get("target") == "/snapshots"
    ]
    if len(snapshot_mounts) != 1 or snapshot_mounts[0].get("read_only") is not True:
        findings.append("restore override: backup evidence must be mounted read-only")
    edge = document.get("networks", {}).get("publisher-edge", {})
    if edge.get("internal") is not True:
        findings.append("restore override: provider egress must be blocked")
    return findings


def validate_mapping_fixtures(root: Path) -> list[str]:
    schema = json.loads((root / "stack/publisher/mapping.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    fixture_dir = root / "infra/schemas/fixtures/positive/publisher-mappings"
    findings: list[str] = []
    mappings = [load_yaml(path) for path in sorted(fixture_dir.glob("*.yml"))]
    for path, mapping in zip(sorted(fixture_dir.glob("*.yml")), mappings, strict=True):
        for error in validator.iter_errors(mapping):
            findings.append(f"{path.name}: {error.message}")
    if len(mappings) != 3:
        findings.append("mappings: exactly three generic fixtures are required")
    account_counts = sorted(
        sum(len(brand["accounts"]) for brand in mapping.get("brands", []))
        for mapping in mappings
    )
    if account_counts != [0, 1, 1]:
        findings.append("mappings: require two account-owning projects and one no-account project")
    for mapping in mappings:
        for brand in mapping.get("brands", []):
            for account in brand.get("accounts", []):
                if account.get("state") != "fixture":
                    findings.append("mappings: offline fixtures may not declare canary or active accounts")
    return sorted(set(findings))


def validate_desired_state_registries(root: Path, compose: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    registry = load_yaml(root / "infra/services/registry.yml")
    images = load_yaml(root / "infra/services/images.lock.yml")
    volumes = load_yaml(root / "infra/services/volumes.yml")
    backups = load_yaml(root / "infra/services/backup-adapters.yml")
    secrets = load_yaml(root / "infra/secrets/catalog.yml")
    inventory = load_yaml(root / "infra/inventories/production/hosts.yml")
    publisher_vars = load_yaml(
        root / "infra/inventories/production/group_vars/publisher.yml"
    )

    service_records = {item["id"]: item for item in registry["services"]}
    image_records = {item["id"]: item for item in images["images"]}
    volume_records = {item["id"]: item for item in volumes["volumes"]}
    backup_ids = {item["id"] for item in backups["backup_adapters"]}
    secret_ids = {item["id"] for item in secrets["secrets"]}
    publisher_host = next(host for host in inventory["hosts"] if host["id"] == "publish-1")

    expected_registry_ids = set(COMPOSE_TO_REGISTRY.values())
    if not expected_registry_ids <= set(publisher_host["service_ids"]):
        findings.append("registries: publish-1 inventory omits a selected publisher service")
    for compose_id, registry_id in COMPOSE_TO_REGISTRY.items():
        service = service_records.get(registry_id)
        if service is None:
            findings.append(f"registries: missing service {registry_id}")
            continue
        image = image_records.get(service["image_id"])
        expected_image = EXPECTED_IMAGES[compose_id]
        if image is None or f"{image['repository']}:{image['tag']}@{image['digest']}" != expected_image:
            findings.append(f"registries: {registry_id} image does not match Compose")
        compose_memory = memory_mebibytes(compose["services"][compose_id]["mem_limit"])
        if service["resources"]["memory_mb"] != compose_memory:
            findings.append(f"registries: {registry_id} memory differs from Compose")
        if service["volume_ids"] != EXPECTED_REGISTRY_VOLUMES[registry_id]:
            findings.append(f"registries: {registry_id} volume ownership differs from Compose")
        if service["backup_adapter_id"] not in backup_ids:
            findings.append(f"registries: {registry_id} has no backup/rebuild adapter")
        for secret_id in service["secret_ids"]:
            if secret_id not in secret_ids:
                findings.append(f"registries: {registry_id} references unknown secret {secret_id}")

    retained = {
        record["id"]
        for record in volume_records.values()
        if record["classification"] == "retained"
    }
    if retained != {
        "publisher-postgres-data",
        "publisher-redis-data",
        "publisher-temporal-postgres-data",
        "publisher-temporal-visibility-data",
    }:
        findings.append("registries: retained publisher state classification is incomplete")
    staging = volume_records.get("publisher-backup-staging", {})
    if staging.get("classification") != "ephemeral" or staging.get("size_limit_mb") != 4096:
        findings.append("registries: publisher backup staging must be ephemeral and 4096 MiB")

    enabled = publisher_vars.get("publisher_enabled")
    blockers = set(publisher_vars.get("publisher_activation_blockers", []))
    if enabled is False and blockers != {"wp05d-publish1", "wp06b-publish1", "wp07-publish1"}:
        findings.append("activation: disabled publisher must name every unmet live gate")
    if enabled is True:
        if blockers:
            findings.append("activation: enabled publisher may not retain dependency blockers")
        for field in (
            "publisher_media_account_id",
            "publisher_media_bucket",
            "publisher_media_public_url",
        ):
            if not publisher_vars.get(field):
                findings.append(f"activation: enabled publisher requires {field}")
    return sorted(set(findings))


def validate_root(root: Path) -> list[str]:
    compose = load_yaml(root / "stack/publisher/postiz/compose.yml")
    return sorted(
        set(
            validate_compose(compose)
            + validate_restore_override(
                load_yaml(root / "stack/publisher/postiz/compose.restore.yml")
            )
            + validate_mapping_fixtures(root)
            + validate_desired_state_registries(root, compose)
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    findings = validate_root(args.root.resolve())
    if findings:
        for finding in findings:
            print(f"publisher contract failure: {finding}")
        raise SystemExit(1)
    print("publisher offline contract passed")


if __name__ == "__main__":
    main()
