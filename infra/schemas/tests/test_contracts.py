from __future__ import annotations

import json
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
    DIRECTORY_SCHEMAS,
    FILE_SCHEMAS,
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
    target = bundle / mutation["target"]
    document = load_yaml(target)
    cursor = document
    path = mutation["path"]
    for part in path[:-1]:
        cursor = cursor[part]
    if mutation["operation"] == "set":
        cursor[path[-1]] = mutation.get("value")
    elif mutation["operation"] == "delete":
        del cursor[path[-1]]
    else:
        raise AssertionError(f"unknown fixture mutation operation: {mutation['operation']}")
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return mutation["expected_error"]


def test_schema_inventory_is_versioned_and_complete() -> None:
    expected = {Path(path).name for path in [*FILE_SCHEMAS.values(), *DIRECTORY_SCHEMAS.values()]}
    actual = {path.name for path in REPO_ROOT.rglob("*.schema.json")}
    assert actual == expected
    for schema_path in REPO_ROOT.rglob("*.schema.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "/v1/" in schema["$id"]
        assert schema["properties"]["schema_version"]["const"] == 1


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


INVALID_CASES = sorted(path for path in INVALID.iterdir() if path.is_dir())


@pytest.mark.parametrize("fixture", INVALID_CASES, ids=lambda path: path.name)
def test_invalid_fixture_fails_for_its_intended_reason(tmp_path: Path, fixture: Path) -> None:
    bundle_path = tmp_path / "bundle"
    shutil.copytree(POSITIVE, bundle_path)
    expected_error = apply_mutation(bundle_path, fixture)
    _, findings = validate_bundle(REPO_ROOT, bundle_path)
    assert findings, f"{fixture.name} unexpectedly validated"
    assert any(expected_error in finding for finding in findings), findings
    assert all("cannot load YAML" not in finding for finding in findings)


def test_validator_contains_no_real_project_special_case() -> None:
    source = (SCHEMA_DIR / "validate.py").read_text(encoding="utf-8").lower()
    assert "dholbeat" not in source
    assert "poripati" not in source
    assert "w3exam" not in source
