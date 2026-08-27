from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "infra/roles/publisher/files"))

from publisher_state import (  # noqa: E402
    MANIFEST_NAME,
    StateError,
    file_receipts,
    safe_child,
    running_services,
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
    backup = tmp_path / "fixture"
    backup.mkdir()
    dump = backup / "postiz.sql"
    dump.write_text("fixture\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "adapter": "postiz-v2.23.0",
        "backup_id": "fixture",
        "files": file_receipts(backup),
    }
    (backup / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(backup)["backup_id"] == "fixture"
    dump.write_text("changed\n", encoding="utf-8")
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


def test_restore_override_blocks_provider_egress() -> None:
    override = (ROOT / "stack/publisher/postiz/compose.restore.yml").read_text(
        encoding="utf-8"
    )
    assert 'RUN_CRON: "false"' in override
    assert "internal: true" in override
    assert "read_only: true" in override
