from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

import pytest
import yaml


SCHEMA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCHEMA_DIR.parents[1]
POSITIVE = SCHEMA_DIR / "fixtures/positive"
INVALID = SCHEMA_DIR / "fixtures/invalid"
sys.path.insert(0, str(SCHEMA_DIR))

from validate import (  # noqa: E402
    SCHEMA_CONTRACTS,
    _is_forbidden_workflow_key,
    normalize_workflow_source,
    schema_errors,
    normalized_bundle,
    validate_bundle,
    validate_registries,
)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    assert isinstance(document, dict)
    return document


def apply_mutation(bundle: Path, fixture: Path) -> str:
    mutation = load_yaml(fixture / "mutation.yml")
    operations = mutation.get("mutations", [mutation])
    for operation in operations:
        target = bundle / operation["target"]
        document = load_yaml(target)
        cursor = document
        path = operation["path"]
        for part in path[:-1]:
            cursor = cursor[part]
        if operation["operation"] == "set":
            cursor[path[-1]] = operation.get("value")
        elif operation["operation"] == "delete":
            del cursor[path[-1]]
        else:
            raise AssertionError(
                f"unknown fixture mutation operation: {operation['operation']}"
            )
        target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return mutation["expected_error"]


def repository_schema_paths(root: Path) -> set[Path]:
    skipped = {".artifacts", ".controller-cache", ".git", ".worktrees"}
    schemas: set[Path] = set()
    for directory, names, filenames in os.walk(root):
        names[:] = sorted(name for name in names if name not in skipped)
        base = Path(directory)
        schemas.update(base / name for name in filenames if name.endswith(".schema.json"))
    return schemas


def test_schema_inventory_is_versioned_and_complete() -> None:
    expected = {REPO_ROOT / path for path in SCHEMA_CONTRACTS.values()}
    actual = repository_schema_paths(REPO_ROOT)
    assert actual == expected
    for schema_path in sorted(actual):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        version = schema["properties"]["schema_version"]["const"]
        assert f"/v{version}/" in schema["$id"]
        assert isinstance(version, int) and version >= 1


def test_schema_inventory_ignores_other_worktrees(tmp_path: Path) -> None:
    local = tmp_path / "infra/schemas/local.schema.json"
    foreign = tmp_path / ".worktrees/other/foreign.schema.json"
    local.parent.mkdir(parents=True)
    foreign.parent.mkdir(parents=True)
    local.write_text("{}\n", encoding="utf-8")
    foreign.write_text("{}\n", encoding="utf-8")
    assert repository_schema_paths(tmp_path) == {local}


def test_empty_desired_state_registries_are_valid_and_idempotent() -> None:
    first = validate_registries(REPO_ROOT)
    second = validate_registries(REPO_ROOT)
    assert first == []
    assert second == first


def test_data_only_third_brand_bundle_is_valid_and_deterministic() -> None:
    first_bundle, first_findings = validate_bundle(REPO_ROOT, POSITIVE)
    second_bundle, second_findings = validate_bundle(REPO_ROOT, POSITIVE)
    assert first_findings == []
    assert second_findings == first_findings
    assert first_bundle is not None
    assert second_bundle is not None
    first_normalized = normalized_bundle(first_bundle)
    second_normalized = normalized_bundle(second_bundle)
    assert first_normalized == second_normalized
    assert json.dumps(json.loads(first_normalized), separators=(",", ":"), sort_keys=True) == first_normalized

    brands = {manifest["brand"] for _, manifest in first_bundle.many("brands")}
    assert brands == {"brand-alpha", "brand-beta", "brand-gamma"}
    prompts = {manifest["prompt_id"] for _, manifest in first_bundle.many("prompts")}
    workflows = {manifest["workflow_id"] for _, manifest in first_bundle.many("workflows")}
    mappings = {
        manifest["mapping_id"]: manifest
        for _, manifest in first_bundle.many("publisher-mappings")
    }
    assert prompts == {"prompt-alpha", "prompt-beta"}
    assert workflows == {"workflow-alpha", "workflow-beta"}
    assert set(mappings) == {"publisher-alpha", "publisher-beta", "publisher-gamma"}
    assert mappings["publisher-gamma"]["brands"] == [
        {"brand_id": "brand-gamma", "accounts": []}
    ]
    consumer_projects = {
        manifest["project_id"] for _, manifest in first_bundle.many("n8n-consumers")
    }
    assert consumer_projects == {"project-alpha", "project-beta"}
    assert all(
        manifest["credential_ids"] == []
        for directory in ("n8n-consumers", "hermes-projects")
        for _, manifest in first_bundle.many(directory)
    )


def test_brand_profiles_validate_against_schema() -> None:
    schema = REPO_ROOT / SCHEMA_CONTRACTS["brand"]
    for brand_path in sorted((REPO_ROOT / "brands").glob("*.yaml")):
        brand = load_yaml(brand_path)
        findings = schema_errors(
            brand, schema, brand_path.relative_to(REPO_ROOT).as_posix()
        )
        assert not findings, f"{brand_path.name}: {findings}"


def test_workflow_source_normalization_is_stable_and_removes_volatiles() -> None:
    source = json.loads(
        (POSITIVE / "n8n/exports/workflows/workflow-alpha.normalized.json").read_text(
            encoding="utf-8"
        )
    )
    source["updatedAt"] = "2026-01-01T00:00:00Z"
    source["nodes"][0]["position"] = [100, 200]
    source["nodes"][0]["webhookId"] = "uuid-placeholder"
    source["nodes"][0]["notes"] = "caption note"
    source["nodes"][0]["parameters"] = {"options": {"disabled": True}}

    normalized, removed = normalize_workflow_source(source)
    assert "$.updatedAt" in removed
    assert "$.nodes[0].position" in removed
    assert "$.nodes[0].webhookId" in removed
    assert "$.nodes[0].notes" in removed
    assert "$.nodes[0].parameters.disabled" not in removed
    assert "$.nodes[0].parameters.options.disabled" not in removed
    assert "$.updatedAt" not in normalized
    assert "position" not in normalized["nodes"][0]
    assert "webhookId" not in normalized["nodes"][0]
    assert "disabled" in normalized["nodes"][0]["parameters"]["options"]

    repeated, _ = normalize_workflow_source(normalized)
    assert normalized == repeated


@pytest.mark.parametrize(
    "field",
    [
        "credentials",
        "apiKey",
        "APIKey",
        "api_key",
        "apikey",
        "accessToken",
        "bearerToken",
        "password",
        "auth",
        "authorization",
        "privateKey",
        "private_key",
        "privatekey",
        "client_secret",
    ],
)
def test_workflow_source_scan_flags_credential_field_names(field: str) -> None:
    assert _is_forbidden_workflow_key(field)


@pytest.mark.parametrize(
    "field",
    [
        "author",
        "authorName",
        "authors",
        "capital",
        "capitalize",
        "rapid",
        "apiVersion",
        "tokenize",
        "secretary",
    ],
)
def test_workflow_source_scan_allows_safe_field_names(field: str) -> None:
    assert not _is_forbidden_workflow_key(field)


def test_workflow_source_scan_does_not_flag_safe_parameter_names(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    source_path = (
        bundle_path / "n8n/exports/workflows/workflow-alpha.normalized.json"
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["nodes"][0]["parameters"]["authorName"] = "fixture-author"
    source["nodes"][0]["parameters"]["apiVersion"] = "v1"
    source_path.write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings == []


def test_explicit_rfc1918_route_origin_is_valid(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    routes = load_yaml(bundle_path / "routes.yml")
    routes["routes"][0]["origin"] = {
        "kind": "private-address",
        "scheme": "http",
        "host": "172.18.0.2",
        "port": 18081,
    }
    (bundle_path / "routes.yml").write_text(
        yaml.safe_dump(routes, sort_keys=False), encoding="utf-8"
    )
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings == []


def test_equivalent_ipv6_private_origin_spellings_are_valid(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    registry = load_yaml(bundle_path / "registry.yml")
    registry["services"][0]["private_origin_addresses"] = ["fc00::1"]
    (bundle_path / "registry.yml").write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    routes = load_yaml(bundle_path / "routes.yml")
    routes["routes"][0]["origin"] = {
        "kind": "private-address",
        "scheme": "http",
        "host": "fc00:0:0:0:0:0:0:1",
        "port": 18081,
    }
    (bundle_path / "routes.yml").write_text(
        yaml.safe_dump(routes, sort_keys=False), encoding="utf-8"
    )
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings == []


def test_private_origin_address_ownership_is_scoped_per_host(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    inventory = load_yaml(bundle_path / "inventory.yml")
    inventory["hosts"][0]["service_ids"] = ["service-alpha"]
    inventory["hosts"][1]["service_ids"] = ["service-beta"]
    (bundle_path / "inventory.yml").write_text(
        yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8"
    )
    registry = load_yaml(bundle_path / "registry.yml")
    registry["services"][1]["host_id"] = "fixture-publisher"
    registry["services"][1]["private_origin_addresses"] = ["172.18.0.2"]
    (bundle_path / "registry.yml").write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    routes = load_yaml(bundle_path / "routes.yml")
    routes["routes"][1]["host_id"] = "fixture-publisher"
    (bundle_path / "routes.yml").write_text(
        yaml.safe_dump(routes, sort_keys=False), encoding="utf-8"
    )
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings == []


INVALID_CASES = sorted(path for path in INVALID.iterdir() if path.is_dir())


@pytest.mark.parametrize("fixture", INVALID_CASES, ids=lambda path: path.name)
def test_invalid_fixture_fails_for_its_intended_reason(tmp_path: Path, fixture: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    expected_error = apply_mutation(bundle_path, fixture)
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings, f"{fixture.name} unexpectedly validated"
    assert expected_error in findings, findings
    assert all("cannot load YAML" not in finding for finding in findings)


def test_validator_contains_no_real_project_special_case() -> None:
    source = (SCHEMA_DIR / "validate.py").read_text(encoding="utf-8").lower()
    assert "dholbeat" not in source
    assert "poripati" not in source
    assert "w3exam" not in source
