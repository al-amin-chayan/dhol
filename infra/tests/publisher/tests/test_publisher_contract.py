from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[4]
VALIDATOR_PATH = ROOT / "infra/tests/publisher/validate.py"
SPEC = importlib.util.spec_from_file_location("publisher_contract_validate", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
load_yaml = VALIDATOR.load_yaml
memory_mebibytes = VALIDATOR.memory_mebibytes
validate_compose = VALIDATOR.validate_compose
validate_root = VALIDATOR.validate_root


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


@pytest.mark.parametrize("value", ["1024", "512k", "1.5g"])
def test_memory_limit_rejects_ambiguous_or_fractional_units(value: str) -> None:
    with pytest.raises(ValueError, match="integral m or g"):
        memory_mebibytes(value)


def test_redis_cannot_be_reclassified_as_rebuildable(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz-redis"]["command"][-1] = "allkeys-lru"
    changed["services"]["postiz-redis"].pop("volumes")
    findings = validate_compose(changed)
    assert "postiz-redis: retained state requires AOF and noeviction" in findings
    assert "postiz-redis: retained data volume is required" in findings


def test_postiz_tmpfs_must_stay_within_256_mib(compose: dict) -> None:
    changed = deepcopy(compose)
    changed["services"]["postiz"]["tmpfs"] = ["/tmp:size=536870912,mode=1777"]
    assert "postiz: /tmp tmpfs must be exactly 256 MiB" in validate_compose(changed)


def test_decommission_is_explicit_and_preserves_retained_volumes() -> None:
    runbook = (ROOT / "docs/runbooks/publisher-operations.md").read_text(
        encoding="utf-8"
    )
    section = runbook.split("## Explicit decommission after activation", 1)[1].split(
        "## Seven-day canary", 1
    )[0]
    assert "dholbeat-publisher-control freeze" in section
    assert "docker compose down --remove-orphans" in section
    assert "Never\nadd `--volumes`" in section


def test_yaml_round_trip_preserves_the_contract(compose: dict) -> None:
    rendered = yaml.safe_load(yaml.safe_dump(compose, sort_keys=True))
    assert validate_compose(rendered) == []
