from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "infra/roles/publisher/files"))

import publisher_state  # noqa: E402
from publisher_state import (  # noqa: E402
    MANIFEST_NAME,
    StateError,
    backup,
    effective_restore_contract,
    file_receipts,
    parser,
    require_restore_capacity,
    safe_child,
    running_services,
    state_error_message,
    validate_restore_project,
    verify_manifest,
)


class FakeRunner:
    def __init__(self, output: bytes) -> None:
        self.output = output

    def run(self, arguments, *, capture_output=False):
        assert arguments == ["ps", "--status", "running", "--services"]
        from subprocess import CompletedProcess

        return CompletedProcess(arguments, 0, self.output, b"")


def write_valid_backup(root: Path, name: str = "fixture") -> Path:
    backup_directory = root / name
    backup_directory.mkdir()
    (backup_directory / "postiz.sql").write_text("postiz\n", encoding="utf-8")
    (backup_directory / "temporal.sql").write_text("temporal\n", encoding="utf-8")
    redis = backup_directory / "redis"
    redis.mkdir()
    (redis / "appendonly.aof").write_text("redis\n", encoding="utf-8")
    visibility = backup_directory / "visibility"
    visibility.mkdir()
    (visibility / "snapshot").write_text("visibility\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "adapter": "postiz-v2.23.0",
        "backup_id": name,
        "postiz_organization_count": 1,
        "postiz_redis_key_count": 1,
        "temporal_running_workflow_count": 1,
        "files": file_receipts(backup_directory),
    }
    (backup_directory / MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return backup_directory


def test_backup_id_cannot_escape_staging_root(tmp_path: Path) -> None:
    for value in ("../escape", "/absolute", "UPPERCASE", "two/slugs"):
        with pytest.raises(StateError, match="backup ID"):
            safe_child(tmp_path, value)


def test_restore_project_can_never_name_production() -> None:
    for value in ("dholbeat-publisher", "publisher", "dholbeat-publisher-restore-"):
        with pytest.raises(StateError, match="restore project"):
            validate_restore_project(value)
    validate_restore_project("dholbeat-publisher-restore-fixture-1")


def test_running_service_probe_returns_an_exact_set() -> None:
    assert running_services(FakeRunner(b"postiz\ntemporal\n")) == {"postiz", "temporal"}


def test_manifest_detects_changed_backup_bytes(tmp_path: Path) -> None:
    backup = write_valid_backup(tmp_path)
    assert verify_manifest(backup)["backup_id"] == "fixture"
    (backup / "postiz.sql").write_text("changed\n", encoding="utf-8")
    with pytest.raises(StateError, match="digest"):
        verify_manifest(backup)


def test_manifest_rejects_another_adapter(tmp_path: Path) -> None:
    backup = tmp_path / "fixture"
    backup.mkdir()
    (backup / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "adapter": "another-publisher",
                "backup_id": "fixture",
                "files": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(StateError, match="another publisher"):
        verify_manifest(backup)


def test_manifest_id_must_match_safe_directory(tmp_path: Path) -> None:
    backup = write_valid_backup(tmp_path)
    manifest_path = backup / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["backup_id"] = "different"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StateError, match="does not match"):
        verify_manifest(backup)


def test_manifest_rejects_symbolic_links(tmp_path: Path) -> None:
    backup = write_valid_backup(tmp_path)
    (backup / "redis" / "escape").symlink_to(tmp_path / "outside")
    with pytest.raises(StateError, match="symbolic links"):
        verify_manifest(backup)


class ConfigRunner:
    def __init__(self, document: dict) -> None:
        self.document = document

    def run(self, arguments, *, capture_output=False):
        from subprocess import CompletedProcess

        assert arguments == ["config", "--format", "json"]
        assert capture_output is True
        return CompletedProcess(arguments, 0, json.dumps(self.document).encode(), b"")


def restore_config() -> dict:
    return {
        "name": "dholbeat-publisher-restore-fixture",
        "networks": {
            "publisher-edge": {"internal": True},
            "publisher-state": {"internal": True},
        },
        "services": {
            "postiz": {
                "environment": {"RUN_CRON": "false"},
                "networks": {"publisher-edge": {}, "publisher-state": {}},
            },
            "temporal-elasticsearch": {
                "networks": {"publisher-state": {}},
                "volumes": [
                    {"target": "/snapshots", "read_only": True},
                ],
            },
        },
    }


def test_effective_restore_contract_is_verified_before_use() -> None:
    digest = effective_restore_contract(
        ConfigRunner(restore_config()), "dholbeat-publisher-restore-fixture"
    )
    assert len(digest) == 64


@pytest.mark.parametrize(
    "mutation", ["egress", "cron", "snapshot", "project", "host-network"]
)
def test_effective_restore_contract_fails_closed(mutation: str) -> None:
    document = restore_config()
    if mutation == "egress":
        document["networks"]["publisher-edge"]["internal"] = False
    elif mutation == "cron":
        document["services"]["postiz"]["environment"]["RUN_CRON"] = "true"
    elif mutation == "snapshot":
        document["services"]["temporal-elasticsearch"]["volumes"][0][
            "read_only"
        ] = False
    elif mutation == "project":
        document["name"] = "dholbeat-publisher"
    else:
        document["services"]["postiz"]["network_mode"] = "host"
    with pytest.raises(StateError, match="effective restore"):
        effective_restore_contract(
            ConfigRunner(document), "dholbeat-publisher-restore-fixture"
        )


def test_restore_capacity_preserves_eight_gib_headroom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_valid_backup(tmp_path)
    docker_root = tmp_path / "docker"
    docker_root.mkdir()
    monkeypatch.setattr(
        publisher_state.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=8 * 1024 * 1024 * 1024),
    )
    with pytest.raises(StateError, match="insufficient disk"):
        require_restore_capacity(source, docker_root)


class FailedBackupRunner:
    def run(self, arguments, *, capture_output=False):
        from subprocess import CompletedProcess

        if arguments == ["ps", "--status", "running", "--services"]:
            services = (
                "postiz\npostiz-postgres\npostiz-redis\ntemporal\n"
                "temporal-elasticsearch\ntemporal-postgres\n"
            )
            return CompletedProcess(arguments, 0, services.encode(), b"")
        if arguments[0] == "stop":
            raise StateError("primary backup failure")
        if arguments[0] == "up":
            raise StateError("restart failure")
        raise AssertionError(arguments)


def test_restart_failure_augments_primary_backup_failure(tmp_path: Path) -> None:
    with pytest.raises(StateError, match="primary backup failure") as caught:
        backup(
            FailedBackupRunner(),
            tmp_path,
            "fixture",
            tmp_path / "kill-switch",
            None,
        )
    assert any("restart also failed" in note for note in caught.value.__notes__)
    assert "primary backup failure; publisher restart also failed" in state_error_message(
        caught.value
    )


def test_restore_override_blocks_provider_egress() -> None:
    override = (ROOT / "stack/publisher/postiz/compose.restore.yml").read_text(
        encoding="utf-8"
    )
    assert 'RUN_CRON: "false"' in override
    assert "internal: true" in override
    assert "read_only: true" in override


def test_disposable_restore_cleans_up_unless_explicitly_kept() -> None:
    arguments = [
        "restore-disposable",
        "--backup-id",
        "fixture",
        "--project-name",
        "dholbeat-publisher-restore-fixture",
        "--loopback-port",
        "15001",
    ]
    assert parser().parse_args(arguments).keep is False
    assert parser().parse_args([*arguments, "--keep"]).keep is True
    source = (ROOT / "infra/roles/publisher/files/publisher_state.py").read_text(
        encoding="utf-8"
    )
    assert 'runner.run(["down", "--volumes", "--remove-orphans"])' in source
