"""Positive, negative, and idempotence coverage for the production host baseline."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/inventories/host_baseline.py"
FIXTURE_ROOT = ROOT / "infra/inventories/fixtures/host-baseline"
BASELINE_ROOT = ROOT / "infra/inventories/production/baseline"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_host_baseline", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_BASELINE = load_module()


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def deep_merge(base: dict, overlay: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def positive_document() -> dict:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    return document


def test_positive_fixture_satisfies_the_shared_baseline_contract() -> None:
    assert HOST_BASELINE.validate_document(ROOT, positive_document(), "fixture") == []


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("wrong-os.yml", "expected_host.os_image must be ubuntu-24.04"),
        ("low-memory.yml", "RAM is below"),
        ("low-disk.yml", "free root disk is below"),
        ("committed-address.yml", "committed host address is forbidden"),
        ("world-open-ssh.yml", "must not expose SSH to the whole internet"),
        ("public-application-binding.yml", "public or unspecified address"),
        ("root-administrator.yml", "must not reuse a bootstrap or root account"),
        ("bootstrap-identity-is-admin.yml", "bootstrap.identity must be a provider bootstrap login"),
        ("committed-address-source.yml", "bootstrap.address_source must be operator-extra-vars"),
        ("fixture-environment.yml", "target_environment must be production"),
    ],
)
def test_negative_fixtures_fail_closed(fixture: str, expected: str) -> None:
    overlay = load_yaml(FIXTURE_ROOT / "negative" / fixture)
    assert isinstance(overlay, dict)
    document = deep_merge(positive_document(), overlay)
    findings = HOST_BASELINE.validate_document(ROOT, document, "fixture")
    assert any(expected in finding for finding in findings), findings


def test_missing_catalogued_directory_blocks_convergence() -> None:
    document = positive_document()
    document["managed_directories"] = [
        entry for entry in document["managed_directories"] if entry["path"] != "/var/lib/docker"
    ]
    findings = HOST_BASELINE.validate_document(ROOT, document, "fixture")
    assert any("required baseline directory is absent" in finding for finding in findings), findings


def test_role_writable_paths_are_derived_and_cannot_drift() -> None:
    payload = HOST_BASELINE.contract_payload(ROOT, positive_document())
    assert payload["role_writable_paths"] == [
        entry["path"] for entry in payload["managed_directories"]
    ]


def test_committed_production_baselines_pass_offline() -> None:
    """Whatever is committed must already satisfy the contract.

    An empty directory is a valid state: a host gains a contract only when its
    own work package provisions it, so core-1 has none here yet.
    """

    for path in sorted(BASELINE_ROOT.glob("*.yml")):
        assert HOST_BASELINE.validate_host_baseline(ROOT, path.stem) == []


def test_committed_production_baselines_match_the_inventory_manifest() -> None:
    manifest = HOST_BASELINE.manifest_hosts(ROOT)
    for path in sorted(BASELINE_ROOT.glob("*.yml")):
        document = load_yaml(path)
        assert document["host_id"] in manifest
        assert manifest[document["host_id"]]["role"] == document["host_role"]


def test_an_empty_baseline_directory_is_valid_but_a_missing_one_is_not(tmp_path: Path) -> None:
    assert HOST_BASELINE.validate_all(tmp_path) == [
        "infra/inventories/production/baseline: production baseline directory is missing"
    ]
    (tmp_path / "infra/inventories/production/baseline").mkdir(parents=True)
    assert HOST_BASELINE.validate_all(tmp_path) == []


@pytest.fixture()
def rendering_root(tmp_path: Path) -> Path:
    """A minimal repository root carrying one synthetic host contract."""

    baseline_dir = tmp_path / "infra/inventories/production/baseline"
    baseline_dir.mkdir(parents=True)
    document = positive_document()
    (baseline_dir / f"{document['host_id']}.yml").write_text(
        yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
    )
    group_vars = tmp_path / "infra/inventories/production/group_vars"
    group_vars.mkdir(parents=True)
    (group_vars / "all.yml").write_bytes(
        (ROOT / "infra/inventories/production/group_vars/all.yml").read_bytes()
    )
    return tmp_path


def rendered(
    root: Path,
    stage: str,
    address: str = "203.0.113.20",
    admin_identity: str | None = None,
) -> dict:
    return HOST_BASELINE.render_inventory(
        root,
        positive_document()["host_id"],
        address,
        stage,
        "/tmp/controller-home/.ssh/id_target",
        "/tmp/controller-home/.ssh/known_hosts",
        admin_identity,
    )


def host_vars(inventory: dict) -> dict:
    hosts = inventory["all"]["children"]["baseline_targets"]["hosts"]
    assert len(hosts) == 1
    return next(iter(hosts.values()))


def test_render_uses_the_bootstrap_identity_only_for_first_contact(rendering_root: Path) -> None:
    document = positive_document()
    bootstrap = host_vars(rendered(rendering_root, "bootstrap"))
    converged = host_vars(rendered(rendering_root, "converged"))
    assert bootstrap["ansible_user"] == document["bootstrap"]["identity"]
    assert converged["ansible_user"] == document["admin"]["user"]
    assert bootstrap["dholbeat_stage"] == "bootstrap"


def test_render_places_the_address_only_in_the_operator_artifact(rendering_root: Path) -> None:
    variables = host_vars(rendered(rendering_root, "bootstrap"))
    assert variables["ansible_host"] == "203.0.113.20"
    assert variables["baseline_second_connection_host"] == "203.0.113.20"
    committed = (FIXTURE_ROOT / "positive.yml").read_text(encoding="utf-8")
    assert "203.0.113.20" not in committed


def test_render_derives_writable_paths_from_the_catalog(rendering_root: Path) -> None:
    variables = host_vars(rendered(rendering_root, "converged"))
    assert variables["baseline_role_writable_paths"] == [
        entry["path"] for entry in variables["baseline_managed_directories"]
    ]


def test_render_targets_exactly_one_host(rendering_root: Path) -> None:
    inventory = rendered(rendering_root, "converged")
    document = positive_document()
    children = inventory["all"]["children"]
    assert set(children) == {"baseline_targets", document["host_role"]}
    assert list(children["baseline_targets"]["hosts"]) == [document["host_id"]]


def test_render_is_deterministic_for_identical_inputs(rendering_root: Path) -> None:
    assert rendered(rendering_root, "converged") == rendered(rendering_root, "converged")


@pytest.mark.parametrize("address", ["publish-1.example", "203.0.113.0/24", "", "not-an-address"])
def test_render_refuses_anything_but_a_literal_address(
    rendering_root: Path, address: str
) -> None:
    with pytest.raises(ValueError):
        rendered(rendering_root, "converged", address)


def test_render_refuses_an_unknown_stage(rendering_root: Path) -> None:
    with pytest.raises(ValueError):
        rendered(rendering_root, "production")


# --- Bootstrap-to-administrator lifecycle ---

BOOTSTRAP_KEY = "/tmp/controller-home/.ssh/id_target"
ADMIN_KEY = "/tmp/controller-home/.ssh/id_admin"


def test_first_contact_uses_the_bootstrap_key_and_login(rendering_root: Path) -> None:
    document = positive_document()
    variables = host_vars(rendered(rendering_root, "bootstrap", admin_identity=ADMIN_KEY))
    assert variables["ansible_user"] == document["bootstrap"]["identity"]
    assert variables["ansible_private_key_file"] == BOOTSTRAP_KEY


def test_every_later_connection_uses_the_administrator_key_and_login(
    rendering_root: Path,
) -> None:
    document = positive_document()
    variables = host_vars(rendered(rendering_root, "converged", admin_identity=ADMIN_KEY))
    assert variables["ansible_user"] == document["admin"]["user"]
    assert variables["ansible_private_key_file"] == ADMIN_KEY


def test_the_second_connection_probe_always_authenticates_as_the_administrator(
    rendering_root: Path,
) -> None:
    """The probe proves the path that survives SSH hardening, not the bootstrap one."""

    for stage in ("bootstrap", "converged"):
        variables = host_vars(rendered(rendering_root, stage, admin_identity=ADMIN_KEY))
        assert variables["baseline_second_connection_identity_file"] == ADMIN_KEY


def test_the_administrator_key_defaults_to_the_bootstrap_key(rendering_root: Path) -> None:
    variables = host_vars(rendered(rendering_root, "converged"))
    assert variables["ansible_private_key_file"] == BOOTSTRAP_KEY
    assert variables["baseline_second_connection_identity_file"] == BOOTSTRAP_KEY


def test_a_bootstrap_inventory_cannot_be_reused_after_hardening(rendering_root: Path) -> None:
    """Convergence disables root login and restricts AllowUsers to the administrator.

    A second Ansible process therefore needs a distinct converged inventory; the
    in-play identity switch cannot cross a process boundary.
    """

    bootstrap = host_vars(rendered(rendering_root, "bootstrap", admin_identity=ADMIN_KEY))
    converged = host_vars(rendered(rendering_root, "converged", admin_identity=ADMIN_KEY))
    assert bootstrap["ansible_user"] != converged["ansible_user"]
    assert bootstrap["ansible_private_key_file"] != converged["ansible_private_key_file"]
