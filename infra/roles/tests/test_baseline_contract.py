from __future__ import annotations

import copy
import configparser
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "infra/roles/base/files/validate_contract.py"
PROBE_PATH = ROOT / "infra/roles/base/files/second_connection_probe.py"
BOUNDED_TEE_PATH = ROOT / "infra/tests/disposable/bounded_tee.py"
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
        ("controller-source-not-allowed.yml", "controller source address is absent"),
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


@pytest.mark.parametrize("fact_name", ["memory_mb", "disk_total_mb", "disk_free_mb"])
@pytest.mark.parametrize("invalid_value", [None, "6144", 0])
def test_contract_requires_positive_integer_resource_facts(
    fact_name: str, invalid_value: object
) -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    if invalid_value is None:
        document["facts"].pop(fact_name)
    else:
        document["facts"][fact_name] = invalid_value
    findings = CONTRACT.validate_contract(document)
    assert f"facts.{fact_name} must be a positive integer" in findings


def test_contract_accepts_controller_source_inside_ssh_allowlist() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["ssh"]["connection_transport"] = "ssh"
    document["ssh"]["controller_source"] = "172.16.10.5"
    assert CONTRACT.validate_contract(document) == []


def test_contract_uses_effective_docker_data_root_for_catalog() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["docker"]["data_root"] = "/srv/docker"
    for entry in document["managed_directories"]:
        if entry["path"] == "/var/lib/docker":
            entry["path"] = "/srv/docker"
    document["role_writable_paths"] = [
        "/srv/docker" if path == "/var/lib/docker" else path
        for path in document["role_writable_paths"]
    ]
    assert CONTRACT.validate_contract(document) == []


def test_contract_rejects_loopback_firewall_interface() -> None:
    document = load_yaml(FIXTURE_ROOT / "positive.yml")
    assert isinstance(document, dict)
    document["firewall"]["public_interface"] = "lo"
    findings = CONTRACT.validate_contract(document)
    assert any("specific non-loopback interface" in finding for finding in findings)


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
    switch_user = names.index("Continue through the proven administrator identity")
    reset = names.index("Reset the bootstrap connection after disabling root login")
    verify = names.index("Verify the effective SSH daemon policy")
    final_probe = names.index("Re-prove access after SSH hardening")
    assert (
        first_probe
        < firewall
        < post_firewall_probe
        < ssh_hardening
        < flush
        < switch_user
        < reset
        < verify
        < final_probe
    )


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


def test_firewall_policy_is_directional_and_returns_other_forwarding() -> None:
    template = (
        ROOT / "infra/roles/firewall/templates/dholbeat-docker-firewall.sh.j2"
    ).read_text(encoding="utf-8")
    assert '-i "$public_interface" -j DROP' in template
    assert '-A "$chain" -j RETURN' in template
    assert '-A "$chain" -j DROP' not in template
    assert '-i lo -j ACCEPT' not in template


def test_firewall_verification_covers_ufw_host_cidr_normalization() -> None:
    tasks = load_yaml(ROOT / "infra/roles/firewall/tasks/main.yml")
    assert isinstance(tasks, list)
    verification = next(
        task
        for task in tasks
        if task["name"] == "Verify default deny and the explicit SSH allowlist"
    )
    assertions = verification["ansible.builtin.assert"]["that"]
    assert any("regex_replace('/32$', '')" in item for item in assertions)
    assert any("regex_replace('/128$', '')" in item for item in assertions)

    fixture_vars = load_yaml(
        ROOT / "infra/inventories/fixtures/group_vars/baseline_targets.yml"
    )
    assert any(
        cidr.endswith("/32") for cidr in fixture_vars["baseline_ssh_allow_cidrs"]
    )


def test_docker_firewall_survives_docker_restart_without_teardown_gap() -> None:
    unit = (
        ROOT
        / "infra/roles/firewall/templates/dholbeat-docker-firewall.service.j2"
    ).read_text(encoding="utf-8")
    assert "BindsTo=docker.service" in unit
    assert "PartOf=docker.service" in unit
    assert "ExecStop=" not in unit


def test_exact_docker_packages_can_converge_after_repository_advances() -> None:
    tasks = load_yaml(ROOT / "infra/roles/docker/tasks/main.yml")
    assert isinstance(tasks, list)
    package_task = next(
        task
        for task in tasks
        if task["name"] == "Install exact Docker Engine and Compose packages"
    )
    assert package_task["ansible.builtin.apt"]["allow_downgrade"] is True


def test_ssh_baseline_sorts_before_cloud_init_and_is_effectively_verified() -> None:
    hardening_tasks = load_yaml(ROOT / "infra/roles/base/tasks/ssh_hardening.yml")
    assert isinstance(hardening_tasks, list)
    rendered_destinations = [
        task["ansible.builtin.template"]["dest"]
        for task in hardening_tasks
        if "ansible.builtin.template" in task
    ]
    assert rendered_destinations == [
        "/etc/ssh/sshd_config.d/01-dholbeat-baseline.conf"
    ]
    assert any(
        task.get("ansible.builtin.file", {}).get("path")
        == "/etc/ssh/sshd_config.d/60-dholbeat-baseline.conf"
        and task["ansible.builtin.file"].get("state") == "absent"
        for task in hardening_tasks
    )
    verification = load_yaml(ROOT / "infra/roles/base/tasks/ssh_verify.yml")
    assert isinstance(verification, list)
    verification_text = str(verification).lower()
    for expected in (
        "passwordauthentication no",
        "kbdinteractiveauthentication no",
        "permitrootlogin no",
        "allowusers ",
    ):
        assert expected in verification_text


def test_committed_inventories_encode_bootstrap_and_reconvergence_users() -> None:
    bootstrap = load_yaml(ROOT / "infra/inventories/fixtures/hosts.bootstrap.yml")
    converged = load_yaml(ROOT / "infra/inventories/fixtures/hosts.yml")
    assert isinstance(bootstrap, dict)
    assert isinstance(converged, dict)
    bootstrap_host = bootstrap["all"]["children"]["baseline_targets"]["hosts"]
    converged_host = converged["all"]["children"]["baseline_targets"]["hosts"]
    assert bootstrap_host["disposable-baseline"]["ansible_user"] == "root"
    assert converged_host["disposable-baseline"]["ansible_user"] == "dholbeat-admin"
    harness = (ROOT / "infra/tests/disposable/run.sh").read_text(encoding="utf-8")
    assert "--extra-vars ansible_user=" not in harness


def test_disposable_harness_exercises_container_connectivity() -> None:
    harness = (ROOT / "infra/tests/disposable/run.sh").read_text(encoding="utf-8")
    for evidence in (
        "container_egress: passed",
        "container_to_container: passed",
        "unlisted_published_port: blocked",
        "docker_firewall_restart: passed",
    ):
        assert evidence in harness


def test_ansible_config_requires_explicit_inventory_and_portable_role_path() -> None:
    config = configparser.ConfigParser()
    config.read(ROOT / "infra/ansible.cfg")
    assert not config.has_option("defaults", "inventory")
    assert config.get("defaults", "roles_path") == "roles"


def test_bounded_tee_fails_without_exceeding_limit(tmp_path: Path) -> None:
    output_path = tmp_path / "bounded.log"
    result = subprocess.run(
        [
            sys.executable,
            BOUNDED_TEE_PATH,
            "--output",
            output_path,
            "--limit-bytes",
            "8",
        ],
        input=b"0123456789",
        capture_output=True,
    )
    assert result.returncode != 0
    assert result.stdout == b"0123456789"
    assert output_path.read_bytes() == b"01234567"
