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
        assert "/v1/" in schema["$id"]
        assert schema["properties"]["schema_version"]["const"] == 1


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


def test_two_project_positive_bundle_is_valid_and_round_trips_deterministically() -> None:
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
    assert brands == {"brand-alpha", "brand-beta"}
    projects = {manifest["project_id"] for _, manifest in first_bundle.many("n8n-consumers")}
    assert projects == {"project-alpha", "project-beta"}
    assert all(
        manifest["credential_ids"] == []
        for directory in ("n8n-consumers", "hermes-projects")
        for _, manifest in first_bundle.many(directory)
    )


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
