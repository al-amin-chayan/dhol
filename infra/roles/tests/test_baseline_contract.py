from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "infra/roles/base/files/validate_contract.py"
PROBE_PATH = ROOT / "infra/roles/base/files/second_connection_probe.py"
FIXTURE_ROOT = ROOT / "infra/inventories/fixtures/contracts"


def load_module():
    spec = importlib.util.spec_from_file_location("baseline_contract", CONTRACT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = load_module()


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


def test_positive_baseline_contract() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    assert CONTRACT.validate_contract(document) == []


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("wrong-os.yml", "operating system must be Ubuntu"),
        ("wrong-architecture.yml", "architecture must be x86_64 or aarch64"),
        ("low-memory.yml", "RAM is below"),
        ("low-disk.yml", "free root disk is below"),
        ("public-app-port.yml", "public or unspecified address"),
        ("unbounded-docker-log.yml", "Docker log max_size"),
        ("undeclared-writable-path.yml", "absent from the directory catalog"),
    ],
)
def test_negative_contracts_fail_closed(fixture: str, expected: str) -> None:
    positive = load_yaml(FIXTURE_ROOT / "positive.yml")
    overlay = load_yaml(FIXTURE_ROOT / "negative" / fixture)
    assert isinstance(positive, dict)
    assert isinstance(overlay, dict)
    findings = CONTRACT.validate_contract(deep_merge(positive, overlay))
    assert any(expected in finding for finding in findings), findings


def test_contract_cli_never_echoes_authorized_key(tmp_path: Path) -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["facts"]["distribution"] = "Debian"
    input_path = tmp_path / "contract.json"
    import json

    input_path.write_text(json.dumps(document), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, CONTRACT_PATH, "--input", input_path],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "FixtureOnlyPublicKeyMaterial" not in result.stdout + result.stderr


def test_contract_rejects_authorized_key_line_injection() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["admin"]["authorized_keys"][0] += "\nssh-ed25519 InjectedKeyMaterial attacker"
    findings = CONTRACT.validate_contract(document)
    assert any("unsupported public-key format" in finding for finding in findings)


def test_contract_requires_every_baseline_directory_before_mutation() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["managed_directories"] = [
        item for item in document["managed_directories"] if item["path"] != "/var/lib/docker"
    ]
    document["role_writable_paths"].remove("/var/lib/docker")
    findings = CONTRACT.validate_contract(document)
    assert any("required baseline directory is absent" in finding for finding in findings)


def test_connection_probe_fails_closed_without_identity(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            PROBE_PATH,
            "--host",
            "127.0.0.1",
            "--port",
            "22",
            "--user",
            "dholbeat-admin",
            "--identity-file",
            tmp_path / "missing-identity",
            "--known-hosts-file",
            tmp_path / "missing-known-hosts",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "identity file is unavailable" in result.stderr


def test_playbook_orders_safety_probes_before_ssh_and_firewall_changes() -> None:
    playbook = load_yaml(ROOT / "infra/playbooks/baseline.yml")
    assert isinstance(playbook, list)
    play = playbook[0]
    assert play["serial"] == 1
    tasks = play["tasks"]
    names = [task["name"] for task in tasks]
    first_probe = names.index("Prove the named administrator can open a second connection")
    firewall = names.index("Apply the default-deny host and container firewall")
    post_firewall_probe = names.index("Prove access after firewall convergence")
    ssh_hardening = names.index("Stage key-only SSH hardening after the firewall probe")
    flush = names.index("Apply pending SSH handlers only after the safety probes")
    assert first_probe < firewall < post_firewall_probe < ssh_hardening < flush


def test_preflight_tasks_do_not_use_mutating_modules() -> None:
    tasks = load_yaml(ROOT / "infra/roles/base/tasks/preflight.yml")
    assert isinstance(tasks, list)
    forbidden_modules = {
        "ansible.builtin.apt",
        "ansible.builtin.copy",
        "ansible.builtin.file",
        "ansible.builtin.get_url",
        "ansible.builtin.package",
        "ansible.builtin.systemd_service",
        "ansible.builtin.template",
        "ansible.builtin.user",
    }
    for task in tasks:
        assert forbidden_modules.isdisjoint(task), task["name"]
