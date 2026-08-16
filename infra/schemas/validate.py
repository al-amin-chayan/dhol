#!/usr/bin/env python3
"""Validate versioned manifests and their cross-file security contracts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
import yaml


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PRIVATE_ORIGIN_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)

SCHEMA_CONTRACTS = {
    "backup_adapter": "infra/schemas/backup-adapter.schema.json",
    "brand": "brands/brand.schema.json",
    "domain": "infra/schemas/domain.schema.json",
    "hermes_project": "stack/hermes/projects/project.schema.json",
    "image": "infra/schemas/image.schema.json",
    "inventory": "infra/schemas/inventory.schema.json",
    "n8n_consumer": "n8n/consumers/consumer.schema.json",
    "prompt": "prompts/prompt.schema.json",
    "publisher_mapping": "stack/publisher/mapping.schema.json",
    "release": "infra/schemas/release.schema.json",
    "route": "infra/schemas/route.schema.json",
    "secret_catalog": "infra/schemas/secret-catalog.schema.json",
    "service": "infra/schemas/service.schema.json",
    "volume": "infra/schemas/volume.schema.json",
    "workflow": "n8n/workflow.schema.json",
}

FILE_SCHEMAS = {
    "inventory.yml": SCHEMA_CONTRACTS["inventory"],
    "registry.yml": SCHEMA_CONTRACTS["service"],
    "images.lock.yml": SCHEMA_CONTRACTS["image"],
    "domains.yml": SCHEMA_CONTRACTS["domain"],
    "routes.yml": SCHEMA_CONTRACTS["route"],
    "volumes.yml": SCHEMA_CONTRACTS["volume"],
    "backup-adapters.yml": SCHEMA_CONTRACTS["backup_adapter"],
    "secrets.yml": SCHEMA_CONTRACTS["secret_catalog"],
    "release.yml": SCHEMA_CONTRACTS["release"],
}

DIRECTORY_SCHEMAS = {
    "brands": SCHEMA_CONTRACTS["brand"],
    "prompts": SCHEMA_CONTRACTS["prompt"],
    "workflows": SCHEMA_CONTRACTS["workflow"],
    "n8n-consumers": SCHEMA_CONTRACTS["n8n_consumer"],
    "hermes-projects": SCHEMA_CONTRACTS["hermes_project"],
    "publisher-mappings": SCHEMA_CONTRACTS["publisher_mapping"],
}

REGISTRY_SCHEMAS = {
    "infra/services/registry.yml": SCHEMA_CONTRACTS["service"],
    "infra/services/images.lock.yml": SCHEMA_CONTRACTS["image"],
    "infra/services/domains.yml": SCHEMA_CONTRACTS["domain"],
    "infra/services/routes.yml": SCHEMA_CONTRACTS["route"],
    "infra/services/volumes.yml": SCHEMA_CONTRACTS["volume"],
    "infra/services/backup-adapters.yml": SCHEMA_CONTRACTS["backup_adapter"],
}


@dataclass(frozen=True)
class Bundle:
    documents: dict[str, dict[str, Any]]
    schema_versions: dict[str, int]

    def one(self, name: str) -> dict[str, Any]:
        return self.documents[name]

    def many(self, directory: str) -> list[tuple[str, dict[str, Any]]]:
        prefix = f"{directory}/"
        return sorted(
            (
                (name, document)
                for name, document in self.documents.items()
                if name.startswith(prefix)
            ),
            key=lambda item: item[0],
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("expected a YAML mapping")
    return document


def schema_errors(
    document: dict[str, Any], schema_path: Path, document_name: str
) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[str] = []
    for error in sorted(
        validator.iter_errors(document),
        key=lambda item: [str(part) for part in item.absolute_path],
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(f"{document_name}: schema at {location}: {error.message}")
    return findings


def declared_schema_versions(root: Path) -> dict[str, int]:
    versions: dict[str, int] = {}
    for contract, relative_path in SCHEMA_CONTRACTS.items():
        schema = json.loads((root / relative_path).read_text(encoding="utf-8"))
        versions[contract] = int(schema["properties"]["schema_version"]["const"])
    return versions


def load_bundle(root: Path, bundle_path: Path) -> tuple[Bundle | None, list[str]]:
    documents: dict[str, dict[str, Any]] = {}
    findings: list[str] = []
    for name, schema_name in FILE_SCHEMAS.items():
        path = bundle_path / name
        if not path.is_file():
            findings.append(f"{name}: required bundle document is missing")
            continue
        try:
            document = load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            findings.append(f"{name}: cannot load YAML: {error}")
            continue
        documents[name] = document
        findings.extend(schema_errors(document, root / schema_name, name))

    for directory, schema_name in DIRECTORY_SCHEMAS.items():
        path = bundle_path / directory
        files = sorted([*path.glob("*.yml"), *path.glob("*.yaml")]) if path.is_dir() else []
        if not files:
            findings.append(f"{directory}: bundle must contain at least one manifest")
            continue
        for manifest in files:
            name = manifest.relative_to(bundle_path).as_posix()
            try:
                document = load_yaml(manifest)
            except (OSError, ValueError, yaml.YAMLError) as error:
                findings.append(f"{name}: cannot load YAML: {error}")
                continue
            documents[name] = document
            findings.extend(schema_errors(document, root / schema_name, name))

    if findings:
        return None, sorted(findings)
    return Bundle(documents, declared_schema_versions(root)), []


def index_records(
    records: Iterable[dict[str, Any]], key: str, label: str, findings: list[str]
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = str(record[key])
        if identifier in index:
            findings.append(
                f"{label}: duplicate ID {identifier}; subsequent definition skipped from reference checks"
            )
        else:
            index[identifier] = record
    return index


def component_index(
    bundle: Bundle, directory: str, key: str, label: str, findings: list[str]
) -> dict[str, dict[str, Any]]:
    return index_records(
        (document for _, document in bundle.many(directory)), key, label, findings
    )


def require_reference(
    owner: str,
    field: str,
    identifier: str,
    index: dict[str, dict[str, Any]],
    target: str,
    findings: list[str],
) -> dict[str, Any] | None:
    referenced = index.get(identifier)
    if referenced is None:
        findings.append(f"{owner}: {field} references unknown {target} {identifier}")
    return referenced


def credential_scope_errors(
    principal_id: str,
    project_id: str,
    service_id: str | None,
    credential_ids: Iterable[str],
    secrets: dict[str, dict[str, Any]],
    findings: list[str],
) -> None:
    for secret_id in credential_ids:
        secret = require_reference(
            principal_id, "credential_ids", secret_id, secrets, "secret", findings
        )
        if secret is None:
            continue
        if project_id not in secret["allowed_project_ids"]:
            findings.append(
                f"{principal_id}: cross-project credential {secret_id} is not allowed for {project_id}"
            )
        if secret["owner_project_id"] not in {"platform", project_id}:
            findings.append(
                f"{principal_id}: cross-project credential {secret_id} is owned by {secret['owner_project_id']}"
            )
        if principal_id not in secret["allowed_principal_ids"]:
            findings.append(
                f"{principal_id}: credential {secret_id} is not allowed for principal {principal_id}"
            )
        if service_id is not None and service_id not in secret["allowed_service_ids"]:
            findings.append(
                f"{principal_id}: credential {secret_id} is not allowed for service {service_id}"
            )


def private_origin_address(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in PRIVATE_ORIGIN_NETWORKS)


def origin_policy_errors(
    route_id: str,
    origin: dict[str, Any],
    service_id: str,
    allowed_private_addresses: set[str],
) -> list[str]:
    host = origin["host"]
    kind = origin["kind"]
    if kind == "service":
        if host != service_id:
            return [f"{route_id}: origin service {host} must match {service_id}"]
        return []
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if kind == "loopback" and host == "localhost":
            return []
        return [f"{route_id}: unknown {kind} origin host {host}"]
    if kind == "loopback":
        if address.is_loopback:
            return []
        return [f"{route_id}: loopback origin {host} is forbidden"]
    if kind == "private-address":
        if not private_origin_address(host):
            return [
                f"{route_id}: private-address origin {host} is outside declared private networks"
            ]
        if host not in allowed_private_addresses:
            return [f"{route_id}: private-address origin {host} is not declared by {service_id}"]
        return []
    return [f"{route_id}: unsupported origin kind {kind}"]


def validate_cross_file(bundle: Bundle) -> list[str]:
    findings: list[str] = []
    hosts = index_records(bundle.one("inventory.yml")["hosts"], "id", "inventory", findings)
    services = index_records(bundle.one("registry.yml")["services"], "id", "services", findings)
    images = index_records(bundle.one("images.lock.yml")["images"], "id", "images", findings)
    domains = index_records(bundle.one("domains.yml")["domains"], "id", "domains", findings)
    routes = index_records(bundle.one("routes.yml")["routes"], "id", "routes", findings)
    volumes = index_records(bundle.one("volumes.yml")["volumes"], "id", "volumes", findings)
    backups = index_records(
        bundle.one("backup-adapters.yml")["backup_adapters"],
        "id",
        "backup adapters",
        findings,
    )
    secrets = index_records(bundle.one("secrets.yml")["secrets"], "id", "secrets", findings)
    brands = component_index(bundle, "brands", "brand", "brands", findings)
    component_index(bundle, "prompts", "prompt_id", "prompts", findings)
    workflows = component_index(bundle, "workflows", "workflow_id", "workflows", findings)
    consumers = component_index(
        bundle, "n8n-consumers", "consumer_id", "n8n consumers", findings
    )
    hermes_projects = component_index(
        bundle, "hermes-projects", "hermes_project_id", "Hermes projects", findings
    )
    publisher_mappings = component_index(
        bundle, "publisher-mappings", "mapping_id", "publisher mappings", findings
    )
    principal_projects: dict[str, str] = {}
    for label, principal_index in (
        ("service", services),
        ("brand", brands),
        ("workflow", workflows),
        ("n8n consumer", consumers),
        ("Hermes project", hermes_projects),
        ("publisher mapping", publisher_mappings),
    ):
        for principal_id, principal in principal_index.items():
            if principal_id in principal_projects:
                findings.append(f"principals: duplicate principal ID {principal_id} at {label}")
            else:
                principal_projects[principal_id] = principal["project_id"]
    for host_id, host in hosts.items():
        for service_id in host["service_ids"]:
            service = require_reference(host_id, "service_ids", service_id, services, "service", findings)
            if service is not None and service["host_id"] != host_id:
                findings.append(f"{host_id}: service {service_id} belongs to host {service['host_id']}")

    for service_id, service in services.items():
        host = require_reference(service_id, "host_id", service["host_id"], hosts, "host", findings)
        if host is not None and service_id not in host["service_ids"]:
            findings.append(f"{service_id}: host {service['host_id']} does not list this service")
        require_reference(service_id, "image_id", service["image_id"], images, "image", findings)
        backup = require_reference(
            service_id,
            "backup_adapter_id",
            service["backup_adapter_id"],
            backups,
            "backup adapter",
            findings,
        )
        if backup is not None and backup["owner"] not in {"platform", service["project_id"]}:
            findings.append(
                f"{service_id}: backup adapter {backup['id']} is owned by {backup['owner']}"
            )
        for address in service["private_origin_addresses"]:
            if not private_origin_address(address):
                findings.append(
                    f"{service_id}: private origin address {address} is outside declared private networks"
                )

        service_routes: list[dict[str, Any]] = []
        for route_id in service["route_ids"]:
            route = require_reference(service_id, "route_ids", route_id, routes, "route", findings)
            if route is not None:
                service_routes.append(route)
                if route["service_id"] != service_id:
                    findings.append(f"{service_id}: route {route_id} belongs to {route['service_id']}")
        if service["exposure"] == "route" and not service_routes:
            findings.append(f"{service_id}: route exposure requires a declared route")
        if service["exposure"] != "route" and service_routes:
            findings.append(f"{service_id}: non-route exposure cannot declare public routes")

        service_volumes: list[dict[str, Any]] = []
        for volume_id in service["volume_ids"]:
            volume = require_reference(service_id, "volume_ids", volume_id, volumes, "volume", findings)
            if volume is not None:
                service_volumes.append(volume)
                if volume["service_id"] != service_id:
                    findings.append(f"{service_id}: volume {volume_id} belongs to {volume['service_id']}")
                if volume["owner_project_id"] != service["project_id"]:
                    findings.append(
                        f"{service_id}: wrong owner for volume {volume_id}; expected {service['project_id']}"
                    )
        mounted_paths = {volume["mount_path"] for volume in service_volumes}
        declared_paths = set(service["writable_paths"])
        for path in sorted(declared_paths - mounted_paths):
            findings.append(f"{service_id}: unknown writable path {path}")
        for path in sorted(mounted_paths - declared_paths):
            findings.append(f"{service_id}: undeclared writable path {path}")

        credential_scope_errors(
            service_id,
            service["project_id"],
            service_id,
            service["secret_ids"],
            secrets,
            findings,
        )

    human_domains: set[str] = set()
    exception_domains: set[str] = set()
    for route_id, route in routes.items():
        service = require_reference(route_id, "service_id", route["service_id"], services, "service_id", findings)
        require_reference(route_id, "domain_id", route["domain_id"], domains, "domain", findings)
        require_reference(route_id, "host_id", route["host_id"], hosts, "host", findings)
        if service is not None and route_id not in service["route_ids"]:
            findings.append(f"{route_id}: owning service does not reference this route")
        if service is not None and route["host_id"] != service["host_id"]:
            findings.append(f"{route_id}: route host does not match service host")
        if service is not None and route["owner"] != service["project_id"]:
            findings.append(f"{route_id}: route and service have different owners")
        if service is not None and route["retention_owner"] != service["project_id"]:
            findings.append(f"{route_id}: route retention and service have different owners")
        allowed_private_addresses = (
            set(service["private_origin_addresses"]) if service is not None else set()
        )
        findings.extend(
            origin_policy_errors(
                route_id,
                route["origin"],
                route["service_id"],
                allowed_private_addresses,
            )
        )
        if route["caller"] == "human":
            human_domains.add(route["domain_id"])
            if route["access"]["mode"] != "enforced":
                findings.append(f"{route_id}: human route requires enforced Access")
        elif route["access"]["mode"] == "machine-exception":
            exception_domains.add(route["domain_id"])
    for domain_id in sorted(human_domains & exception_domains):
        findings.append(f"routes: machine exception shares human administration domain {domain_id}")

    for volume_id, volume in volumes.items():
        service = require_reference(volume_id, "service_id", volume["service_id"], services, "service", findings)
        if service is not None and volume_id not in service["volume_ids"]:
            findings.append(f"{volume_id}: owning service does not reference this volume")
        if volume["classification"] == "retained":
            backup = require_reference(
                volume_id,
                "backup_adapter_id",
                volume["backup_adapter_id"],
                backups,
                "backup adapter",
                findings,
            )
            if backup is not None and backup["owner"] not in {
                "platform",
                volume["owner_project_id"],
            }:
                findings.append(
                    f"{volume_id}: backup adapter {backup['id']} has the wrong owner"
                )

    for secret_id, secret in secrets.items():
        for principal_id in secret["allowed_principal_ids"]:
            principal_project = principal_projects.get(principal_id)
            if principal_project is None:
                findings.append(
                    f"{secret_id}: allowed_principal_ids references unknown principal {principal_id}"
                )
            elif principal_project not in secret["allowed_project_ids"]:
                findings.append(
                    f"{secret_id}: allowed principal {principal_id} has no allowed project scope"
                )
        for service_id in secret["allowed_service_ids"]:
            allowed_service = require_reference(
                secret_id,
                "allowed_service_ids",
                service_id,
                services,
                "service",
                findings,
            )
            if (
                allowed_service is not None
                and allowed_service["project_id"] not in secret["allowed_project_ids"]
            ):
                findings.append(
                    f"{secret_id}: allowed service {service_id} has no allowed project scope"
                )
            if service_id not in secret["allowed_principal_ids"]:
                findings.append(
                    f"{secret_id}: allowed service {service_id} is missing from allowed principals"
                )

    for brand_id, brand in brands.items():
        credential_scope_errors(
            brand_id,
            brand["project_id"],
            None,
            brand["secret_ids"],
            secrets,
            findings,
        )

    for workflow_id, workflow in workflows.items():
        if not COMMIT_RE.fullmatch(workflow["source_commit"]):
            findings.append(f"{workflow_id}: floating source ref {workflow['source_commit']} is forbidden")
        brand = require_reference(workflow_id, "brand_id", workflow["brand_id"], brands, "brand", findings)
        if brand is not None and brand["project_id"] != workflow["project_id"]:
            findings.append(f"{workflow_id}: workflow and brand have different owners")
        credential_scope_errors(
            workflow_id,
            workflow["project_id"],
            None,
            workflow["credential_ids"],
            secrets,
            findings,
        )
        states = set(workflow["states"])
        for transition in workflow["transitions"]:
            if transition["from"] not in states or transition["to"] not in states:
                findings.append(f"{workflow_id}: transition references an undeclared state")
            if transition["to"] in {"scheduled", "published"}:
                approval = transition["approval"]
                if not (
                    isinstance(approval, dict)
                    and approval.get("type") == "human-final"
                    and approval.get("binds_content_hash") is True
                ):
                    findings.append(
                        f"{workflow_id}: unapproved publish transition to {transition['to']}"
                    )

    for consumer_id, consumer in consumers.items():
        if not COMMIT_RE.fullmatch(consumer["source_commit"]):
            findings.append(f"{consumer_id}: floating source ref {consumer['source_commit']} is forbidden")
        credential_scope_errors(
            consumer_id,
            consumer["project_id"],
            None,
            consumer["credential_ids"],
            secrets,
            findings,
        )
        for route_id in consumer["route_ids"]:
            route = require_reference(consumer_id, "route_ids", route_id, routes, "route", findings)
            route_service = services.get(route["service_id"]) if route is not None else None
            if route_service is not None and route_service["project_id"] != consumer["project_id"]:
                findings.append(f"{consumer_id}: route {route_id} belongs to another project")

    seen_data_mounts: dict[str, str] = {}
    seen_hermes_workspaces: dict[str, str] = {}
    seen_states: dict[str, str] = {}
    for hermes_id, project in hermes_projects.items():
        if not COMMIT_RE.fullmatch(project["source_commit"]):
            findings.append(f"{hermes_id}: floating source ref {project['source_commit']} is forbidden")
        credential_scope_errors(
            hermes_id,
            project["project_id"],
            None,
            project["credential_ids"],
            secrets,
            findings,
        )
        for field, seen, label in (
            ("data_mount", seen_data_mounts, "data mount"),
            ("workspace_mount", seen_hermes_workspaces, "workspace mount"),
        ):
            value = project[field]
            if value in seen:
                findings.append(f"{hermes_id}: shared Hermes {label} {value} with {seen[value]}")
            else:
                seen[value] = hermes_id
        state_path = project["state_backend"]["path"]
        if state_path in seen_states:
            findings.append(
                f"{hermes_id}: shared Hermes state {state_path} with {seen_states[state_path]}"
            )
        else:
            seen_states[state_path] = hermes_id
        adapter_id = project["backup"]["adapter_id"]
        if adapter_id is not None:
            adapter = require_reference(
                hermes_id,
                "backup.adapter_id",
                adapter_id,
                backups,
                "backup adapter",
                findings,
            )
            if adapter is not None and adapter["owner"] not in {"platform", project["project_id"]}:
                findings.append(f"{hermes_id}: backup adapter {adapter_id} belongs to another project")

    seen_organizations: dict[str, str] = {}
    seen_publisher_workspaces: dict[str, str] = {}
    seen_accounts: dict[str, str] = {}
    for mapping_id, mapping in publisher_mappings.items():
        credential_scope_errors(
            mapping_id,
            mapping["project_id"],
            None,
            [mapping["api_credential_id"]],
            secrets,
            findings,
        )
        for field, seen in (
            ("organization_id", seen_organizations),
            ("workspace_id", seen_publisher_workspaces),
        ):
            value = mapping[field]
            if value in seen:
                findings.append(f"{mapping_id}: duplicate publisher {field} {value}")
            else:
                seen[value] = mapping_id
        for brand_mapping in mapping["brands"]:
            brand_id = brand_mapping["brand_id"]
            brand = require_reference(mapping_id, "brand_id", brand_id, brands, "brand", findings)
            if brand is not None and brand["project_id"] != mapping["project_id"]:
                findings.append(f"{mapping_id}: publisher mapping and brand have different owners")
            for account_id in brand_mapping["account_ids"]:
                if account_id in seen_accounts:
                    findings.append(f"{mapping_id}: publisher account {account_id} has duplicate ownership")
                else:
                    seen_accounts[account_id] = mapping_id

    release = bundle.one("release.yml")
    release_versions = release["schema_versions"]
    expected_versions = bundle.schema_versions
    missing_versions = set(expected_versions) - set(release_versions)
    unknown_versions = set(release_versions) - set(expected_versions)
    for schema_name in sorted(missing_versions):
        findings.append(f"{release['release_id']}: missing schema version {schema_name}")
    for schema_name in sorted(unknown_versions):
        findings.append(f"{release['release_id']}: unknown schema version {schema_name}")
    for schema_name, version in release_versions.items():
        if schema_name in expected_versions and version != expected_versions[schema_name]:
            findings.append(
                f"{release['release_id']}: unsupported {schema_name} schema version {version}"
            )
    for image_receipt in release["images"]:
        image = require_reference(
            release["release_id"],
            "images.image_id",
            image_receipt["image_id"],
            images,
            "image",
            findings,
        )
        if image is not None and image["digest"] != image_receipt["digest"]:
            findings.append(
                f"{release['release_id']}: image receipt digest does not match {image_receipt['image_id']}"
            )

    return sorted(set(findings))


def validate_registries(root: Path) -> list[str]:
    findings: list[str] = []
    for document_name, schema_name in REGISTRY_SCHEMAS.items():
        path = root / document_name
        try:
            document = load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            findings.append(f"{document_name}: cannot load YAML: {error}")
            continue
        findings.extend(schema_errors(document, root / schema_name, document_name))
    return sorted(findings)


def validate_bundle(root: Path, bundle_path: Path) -> tuple[Bundle | None, list[str]]:
    bundle, findings = load_bundle(root, bundle_path)
    if bundle is None:
        return None, findings
    return bundle, validate_cross_file(bundle)


def normalized_bundle(bundle: Bundle) -> str:
    return json.dumps(bundle.documents, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    bundle_path = args.bundle if args.bundle.is_absolute() else root / args.bundle
    findings = validate_registries(root)
    _, bundle_findings = validate_bundle(root, bundle_path.resolve())
    findings.extend(bundle_findings)
    if findings:
        for finding in sorted(set(findings)):
            print(f"contract failure: {finding}")
        raise SystemExit(1)
    print("versioned schemas and cross-file contracts passed")


if __name__ == "__main__":
    main()
