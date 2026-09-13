"""Host approval binds current external sources and unchanged encrypted state, fail-closed."""

from pathlib import Path
import json
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/tofu/cloudflare"))
from receipt import input_digest, normalize


@pytest.fixture
def receipt_tree(tmp_path):
    for path in [
        "infra/tofu/cloudflare",
        "infra/services",
        "infra/inventories/production",
        "infra/secrets",
    ]:
        shutil.copytree(
            ROOT / path, tmp_path / path, ignore=shutil.ignore_patterns("__pycache__")
        )
    for filename in ["toolchain.lock.yml", ".sops.yaml"]:
        shutil.copyfile(ROOT / filename, tmp_path / filename)
    receipt = {
        "schema_version": 1,
        "package": "cloudflare",
        "provider_mutations": 0,
        "imported": False,
        "resource_count": 7,
        "provider_version": "5.24.0",
        "opentofu_version": "1.12.5",
        "inputs_sha256": input_digest(tmp_path),
        "observed_epoch": 1000,
        "encrypted_plan_sha256": "a" * 64,
        "encrypted_state_sha256": "b" * 64,
        "backend_bucket": "dholbeat-tfstate",
        "backend_key": "cloudflare/production.tfstate",
    }
    return tmp_path, receipt


def test_valid_receipt_has_stable_external_delta(receipt_tree):
    root, receipt = receipt_tree
    first = normalize(root, receipt, now=1100)
    second = normalize(
        root,
        {**receipt, "observed_epoch": 1100, "encrypted_plan_sha256": "c" * 64},
        now=1200,
    )
    assert first == second and first["state"] == "verified-no-change"


@pytest.mark.parametrize(
    "key,value",
    [
        ("provider_mutations", 1),
        ("imported", True),
        ("resource_count", 0),
        ("provider_version", "5.23.0"),
        ("backend_bucket", "foreign-bucket"),
        ("backend_key", "foreign/key"),
        ("encrypted_state_sha256", ""),
        ("encrypted_plan_sha256", "invalid"),
        ("observed_epoch", 2000),
        ("observed_epoch", 0),
    ],
)
def test_invalid_receipt_never_authorizes_host_plan(receipt_tree, key, value):
    root, receipt = receipt_tree
    with pytest.raises(ValueError):
        normalize(root, {**receipt, key: value}, now=1100)


@pytest.mark.parametrize(
    "path",
    [
        "infra/tofu/cloudflare/resources.tf",
        "infra/tofu/cloudflare/bootstrap-roots.json",
        "infra/secrets/catalog.yml",
        "infra/secrets/cloudflare.sops.yml",
        "infra/services/domains.yml",
        "infra/inventories/production/hosts.yml",
    ],
)
def test_changed_inputs_require_real_replan(receipt_tree, path):
    root, receipt = receipt_tree
    with (root / path).open("a") as output:
        output.write("\n# changed\n")
    with pytest.raises(ValueError):
        normalize(root, receipt, now=1100)


@pytest.mark.parametrize("path", ["infra/tofu/foreign", "infra/tofu/main.tf"])
def test_unadapted_package_fails_closed(receipt_tree, path):
    root, receipt = receipt_tree
    if path.endswith(".tf"):
        (root / path).write_text('resource "terraform_data" "bad" {}')
    else:
        (root / path).mkdir()
    with pytest.raises(ValueError):
        normalize(root, receipt, now=1100)
