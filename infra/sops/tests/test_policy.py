from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml


SOPS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SOPS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from infra.sops.rotation_plan import build_rotation_plan
from infra.sops.validate import (
    SOPS_PATH_REGEX,
    decrypt_in_memory_findings,
    structural_findings,
)

RECIPIENT_ONE = "age1" + "q" * 58
RECIPIENT_TWO = "age1" + "p" * 58
WRONG_RECIPIENT = "age1" + "z" * 58
ENC = "ENC[AES256_GCM,data:dGVzdA==,iv:dGVzdA==,tag:dGVzdA==,type:str]"


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def write_policy(root: Path, recipients: list[str]) -> None:
    write_yaml(
        root / ".sops.yaml",
        {
            "creation_rules": [
                {
                    "path_regex": SOPS_PATH_REGEX,
                    "key_groups": [{"age": recipients}],
                }
            ]
        },
    )


def fake_ciphertext(value_keys: list[str], recipients: list[str]) -> dict:
    return {
        "schema_version": ENC,
        "secret_set_id": ENC,
        "owner_project_id": ENC,
        "values": {key: ENC for key in value_keys},
        "sops": {
            "age": [{"recipient": recipient, "enc": "fixture stanza"} for recipient in recipients],
            "lastmodified": "2026-08-17T00:00:00Z",
            "mac": ENC,
            "version": "3.13.3",
        },
    }


def repo_copy(tmp_path: Path, *, with_ciphertext: bool = True) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "infra/inventories", root / "infra/inventories")
    shutil.copytree(REPO_ROOT / "infra/schemas", root / "infra/schemas")
    (root / "infra/secrets").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "infra/secrets/README.md", root / "infra/secrets/README.md")
    shutil.copy2(REPO_ROOT / "infra/secrets/catalog.yml", root / "infra/secrets/catalog.yml")
    write_policy(root, [RECIPIENT_ONE, RECIPIENT_TWO])
    if with_ciphertext:
        catalog = load_yaml(root / "infra/secrets/catalog.yml")
        by_file: dict[str, list[str]] = {}
        for secret in catalog["secrets"]:
            by_file.setdefault(secret["sops_file"], []).append(secret["value_key"])
        for relative, keys in by_file.items():
            write_yaml(root / relative, fake_ciphertext(keys, [RECIPIENT_ONE, RECIPIENT_TWO]))
    return root


def test_structural_policy_is_valid_and_idempotent(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    first = structural_findings(root)
    second = structural_findings(root)
    assert first == []
    assert second == first


def test_wrong_recipient_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/secrets/core.sops.yml"
    document = load_yaml(path)
    document["sops"]["age"][1]["recipient"] = WRONG_RECIPIENT
    write_yaml(path, document)
    assert any("recipients do not exactly match policy" in item for item in structural_findings(root))


def test_plaintext_value_fails_without_echoing_value(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/secrets/core.sops.yml"
    document = load_yaml(path)
    secret_value = "sensitive-fixture-value"
    first_key = next(iter(document["values"]))
    document["values"][first_key] = secret_value
    write_yaml(path, document)
    findings = structural_findings(root)
    assert any("plaintext value is forbidden" in item for item in findings)
    assert all(secret_value not in item for item in findings)


def test_misplaced_sops_file_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    write_yaml(root / "config/misplaced.sops.yml", fake_ciphertext(["fixture-key"], [RECIPIENT_ONE, RECIPIENT_TWO]))
    assert "config/misplaced.sops.yml: SOPS ciphertext is outside infra/secrets" in structural_findings(root)


def test_unknown_catalog_principal_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/secrets/catalog.yml"
    catalog = load_yaml(path)
    catalog["secrets"][0]["allowed_principal_ids"] = ["unknown-principal"]
    write_yaml(path, catalog)
    assert any("unknown allowed principal unknown-principal" in item for item in structural_findings(root))


def test_cross_project_reused_secret_id_fails(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    path = root / "infra/secrets/catalog.yml"
    catalog = load_yaml(path)
    reused = copy.deepcopy(catalog["secrets"][0])
    reused["owner_project_id"] = "another-project"
    reused["allowed_project_ids"] = ["another-project"]
    catalog["secrets"].append(reused)
    write_yaml(path, catalog)
    assert any("duplicate secret ID" in item for item in structural_findings(root))


def test_leaked_recipient_rotates_every_affected_value_without_plaintext(tmp_path: Path) -> None:
    root = repo_copy(tmp_path)
    catalog = load_yaml(root / "infra/secrets/catalog.yml")
    expected_ids = sorted(secret["id"] for secret in catalog["secrets"])
    plan, findings = build_rotation_plan(root, RECIPIENT_ONE)
    assert findings == []
    assert plan["affected_sops_files"] == [
        "infra/secrets/core.sops.yml",
        "infra/secrets/publisher.sops.yml",
    ]
    assert plan["underlying_secret_ids_to_rotate"] == expected_ids
    assert plan["reencryption_alone_is_sufficient"] is False
    assert plan["contains_plaintext"] is False


def age_keypair() -> tuple[str, str]:
    completed = subprocess.run(
        ["age-keygen"],
        check=True,
        capture_output=True,
        text=True,
    )
    combined = f"{completed.stdout}\n{completed.stderr}"
    private = next(line for line in combined.splitlines() if line.startswith("AGE-SECRET-KEY-"))
    public_match = re.search(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}", combined)
    assert public_match is not None
    return private, public_match.group(0)


@pytest.mark.skipif(shutil.which("sops") is None or shutil.which("age-keygen") is None, reason="pinned controller tools required")
def test_in_memory_decrypt_mac_and_schema_validation(tmp_path: Path) -> None:
    root = repo_copy(tmp_path, with_ciphertext=False)
    catalog_path = root / "infra/secrets/catalog.yml"
    catalog = load_yaml(catalog_path)
    catalog["secrets"] = [catalog["secrets"][0]]
    write_yaml(catalog_path, catalog)

    private_one, public_one = age_keypair()
    _, public_two = age_keypair()
    write_policy(root, [public_one, public_two])
    plaintext = yaml.safe_dump(
        {
            "schema_version": 1,
            "secret_set_id": "core",
            "owner_project_id": "platform",
            "values": {catalog["secrets"][0]["value_key"]: "ephemeral-test-value"},
        },
        sort_keys=False,
    )
    completed = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--age",
            f"{public_one},{public_two}",
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "--filename-override",
            "infra/secrets/core.sops.yml",
            "/dev/stdin",
        ],
        input=plaintext,
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    ciphertext_path = root / "infra/secrets/core.sops.yml"
    ciphertext_path.write_text(completed.stdout, encoding="utf-8")
    assert structural_findings(root) == []
    environment = dict(os.environ)
    environment["SOPS_AGE_KEY"] = private_one
    assert decrypt_in_memory_findings(root, ciphertext_path, environment) == []
    assert "ephemeral-test-value" not in ciphertext_path.read_text(encoding="utf-8")
