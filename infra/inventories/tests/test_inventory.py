from __future__ import annotations

from pathlib import Path
import shutil

import yaml


INVENTORY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = INVENTORY_DIR.parents[1]

from infra.inventories.validate import validate_inventory


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_yaml(path: Path, value: dict) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def repo_copy(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "infra/inventories", root / "infra/inventories")
    shutil.copytree(REPO_ROOT / "infra/schemas", root / "infra/schemas")
    return root


def test_production_inventory_is_valid_and_idempotent() -> None:
    first = validate_inventory(REPO_ROOT)
    second = validate_inventory(REPO_ROOT)
    assert first == []
    assert second == first


def test_unknown_endpoint_host_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/inventories/production/hosts.yml"
    inventory = load_yaml(path)
    inventory["public_endpoints"][0]["host_id"] = "unknown-host"
    write_yaml(path, inventory)
    assert "paperclip-admin: unknown endpoint host unknown-host" in validate_inventory(root)


def test_committed_ip_override_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/inventories/production/hosts.yml"
    inventory = load_yaml(path)
    inventory["hosts"][0]["hostname"] = "192.0.2.10"
    write_yaml(path, inventory)
    findings = validate_inventory(root)
    assert any("committed stable hostname cannot be an IP address" in item for item in findings)


def test_secret_shaped_inventory_key_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/inventories/production/group_vars/all.yml"
    values = load_yaml(path)
    values["api_token"] = "must-not-live-here"
    write_yaml(path, values)
    findings = validate_inventory(root)
    assert any("secret-shaped key is forbidden" in item for item in findings)


def test_wrong_canonical_role_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/inventories/production/hosts.yml"
    inventory = load_yaml(path)
    inventory["hosts"][0]["id"] = "core-replacement"
    write_yaml(path, inventory)
    assert "inventory: canonical role core must be owned by core-1" in validate_inventory(root)
