from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "infra/tests/publisher"))

from validate import load_yaml, validate_compose, validate_root  # noqa: E402


@pytest.fixture
def compose() -> dict:
    return load_yaml(ROOT / "stack/publisher/postiz/compose.yml")


def test_selected_publisher_contract_passes() -> None:
    assert validate_root(ROOT) == []


def test_internal_state_port_is_rejected(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz-postgres"]["ports"] = ["5432:5432"]
    assert "postiz-postgres: state service publishes a host port" in validate_compose(changed)


def test_public_application_binding_is_rejected(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["ports"] = ["5000:5000"]
    assert "postiz: the only published port must bind to loopback" in validate_compose(changed)


def test_mutable_or_changed_image_is_rejected(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["image"] = "ghcr.io/gitroomhq/postiz-app:latest"
    findings = validate_compose(changed)
    assert "postiz: image differs from the selected digest pin" in findings
    assert "postiz: image is not digest-pinned" in findings


def test_visibility_cannot_be_removed(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["temporal"]["environment"]["ENABLE_ES"] = "false"
    assert "temporal: Elasticsearch Visibility must remain enabled" in validate_compose(changed)


def test_snapshot_path_is_required(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["temporal-elasticsearch"]["volumes"] = [
        "temporal-elasticsearch-data:/usr/share/elasticsearch/data"
    ]
    assert (
        "temporal-elasticsearch: filesystem snapshot repository is required"
        in validate_compose(changed)
    )


def test_local_media_storage_is_rejected(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["environment"]["STORAGE_PROVIDER"] = "local"
    assert (
        "postiz: media storage must use the dedicated Cloudflare R2 provider"
        in validate_compose(changed)
    )


def test_registration_may_not_default_open(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["environment"]["DISABLE_REGISTRATION"] = "false"
    assert (
        "postiz: registration state must be a required runtime variable"
        in validate_compose(changed)
    )


def test_aggregate_memory_ceiling_is_enforced(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["mem_limit"] = "2g"
    assert any("aggregate memory limit" in finding for finding in validate_compose(changed))


def test_yaml_round_trip_preserves_the_contract(compose: dict) -> None:
    rendered = yaml.safe_load(yaml.safe_dump(compose, sort_keys=True))
    assert validate_compose(rendered) == []
