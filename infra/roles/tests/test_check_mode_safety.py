"""Every live-state assertion in the planned roles must be check-mode guarded.

Three separate review rounds reported the same defect: a plan run asserting
postconditions against state that check mode deliberately did not create, so no
approvable digest could be produced. Fixing the reported task each time did not
establish the rule. This enforces it, so a newly added unguarded assertion fails
here rather than in a review.

Contract assertions — those reading only inventory-declared variables — are
exempt and listed explicitly, because they must fail fast during planning too.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
ROLE_TASK_FILES = sorted(
    path
    for role in ("base", "docker", "firewall", "wireguard", "release_receipt", "publisher", "restic", "cloudflared")
    for path in (ROOT / f"infra/roles/{role}/tasks").glob("*.yml")
)

# Assertions that read only declared inventory values, never live host state.
# They must run during planning, which is why they are not guarded.
CONTRACT_ASSERTIONS = {
    # Inventory-declared values only.
    "Require all inventory-owned baseline inputs",
    "Require a complete VPN declaration before configuring administration",
    "Require the complete reviewed release identity before writing a receipt",
    "Refuse to record a receipt outside the reviewed authorization",
    "Require selected publisher activation inputs",
    # Controller-side inputs, which exist whether or not the host is mutated.
    "Require readable controller-side connection inputs",
    # A precondition on state that already exists, not a postcondition of this
    # run: it must still refuse during planning.
    "Refuse to remove or replace an undeclared container runtime",
    "Require verified publisher dependency receipts",
    "Require the reviewed publish-1 backup boundary and scoped values",
    "Require the independent publisher tunnel and live Access audiences",
    "Refuse a modified or linked existing dump image",
    # Independently installed admission receipt, never created by this play.
    # An unauthorized timer plan must fail even in check mode.
    "Require exact-host recovery verification before starting timers",
}


# A guard must actually negate. `ansible_check_mode` and
# `ansible_check_mode is defined` both evaluate true during a check run, so a
# substring match would accept conditions that guard nothing.
GUARD_RE = re.compile(r"^not\s+(ansible_check_mode|[a-z_]*plan_only)$")


def guard_conditions(task: dict) -> list[str]:
    when = task.get("when", [])
    conditions = when if isinstance(when, list) else [when]
    return [str(condition).strip() for condition in conditions]


def guarded(task: dict) -> bool:
    """True only when a condition negates check mode outright."""

    return any(GUARD_RE.match(condition) for condition in guard_conditions(task))


def assertion_tasks() -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    for path in ROLE_TASK_FILES:
        for task in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if isinstance(task, dict) and "ansible.builtin.assert" in task:
                found.append((path, task))
    return found


def test_role_task_files_are_discovered() -> None:
    """A shrinking scan silently stops enforcing anything."""

    assert len({path.parent.parent.name for path in ROLE_TASK_FILES}) >= 8
    assert {"restic", "cloudflared"} <= {path.parent.parent.name for path in ROLE_TASK_FILES}
    assert assertion_tasks()


@pytest.mark.parametrize(
    ("path", "task"),
    [(path, task) for path, task in assertion_tasks()],
    ids=lambda value: value.get("name", "") if isinstance(value, dict) else value.name,
)
def test_every_live_state_assertion_is_check_mode_guarded(path: Path, task: dict) -> None:
    name = task.get("name", "")
    if name in CONTRACT_ASSERTIONS:
        return
    assert guarded(task), (
        f"{path.relative_to(ROOT)}: '{name}' asserts against live state without a check-mode "
        "guard. Either guard it with `when: not ansible_check_mode`, or add it to "
        "CONTRACT_ASSERTIONS if it reads only declared inventory values."
    )


def test_the_exemption_list_has_no_stale_entries() -> None:
    """An exemption for a task that no longer exists hides the next one."""

    present = {task.get("name", "") for _, task in assertion_tasks()}
    assert CONTRACT_ASSERTIONS <= present, CONTRACT_ASSERTIONS - present


@pytest.mark.parametrize(
    "condition",
    [
        "ansible_check_mode",
        "ansible_check_mode is defined",
        "ansible_check_mode | default(false)",
        "not ansible_check_mode or true",
        "notansible_check_mode",
        "",
    ],
)
def test_a_condition_that_does_not_negate_check_mode_is_not_a_guard(condition: str) -> None:
    """The gate must reject guards that mention check mode without disabling on it."""

    assert not guarded({"when": condition})


@pytest.mark.parametrize(
    "condition",
    ["not ansible_check_mode", "not wireguard_plan_only", "  not ansible_check_mode  "],
)
def test_a_negating_condition_is_a_guard(condition: str) -> None:
    assert guarded({"when": condition})


def test_a_guard_inside_a_condition_list_is_accepted() -> None:
    assert guarded({"when": ["not ansible_check_mode", "some_other_condition"]})


def test_a_list_without_a_negating_condition_is_not_a_guard() -> None:
    assert not guarded({"when": ["ansible_check_mode", "some_other_condition"]})


@pytest.mark.parametrize("role", ["restic", "cloudflared"])
def test_newly_planned_service_state_tasks_require_existing_units_or_apply(role: str) -> None:
    """Reject missing-unit service operations, which assert coverage cannot see."""
    for path in (ROOT / f"infra/roles/{role}/tasks").glob("*.yml"):
        tasks = yaml.safe_load(path.read_text())
        for task in tasks:
            service = task.get("ansible.builtin.systemd_service", {})
            if ("state" not in service and "enabled" not in service) or guarded(task):
                continue
            conditions = guard_conditions(task)
            if role == "cloudflared":
                assert "not ansible_check_mode or cloudflared_installed_unit.stat.exists" in conditions
                inspect = next(t for t in tasks if t.get("register") == "cloudflared_installed_unit")
                assert inspect["ansible.builtin.stat"]["path"] == "/etc/systemd/system/" + service["name"]
            else:
                assert "not ansible_check_mode or item.stat.exists" in conditions
                assert task["loop"] == "{{ restic_installed_timer_units.results }}"
                assert service["name"] == "{{ item.item }}"
                inspect = next(t for t in tasks if t.get("register") == "restic_installed_timer_units")
                assert inspect["ansible.builtin.stat"]["path"] == "/etc/systemd/system/{{ item }}"


def run_readonly_tasks(tmp_path: Path, tasks: list, variables: dict) -> subprocess.CompletedProcess:
    playbook = tmp_path / "readonly.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Verify first installation admission without mutation", "hosts": "all",
        "gather_facts": False,
        "vars": {"ansible_remote_tmp": str(tmp_path / "remote"), **variables},
        "tasks": tasks,
    }]))
    return subprocess.run([
        "ansible-playbook", "--check", "--diff", "--inventory", "localhost,",
        "--connection", "local", str(playbook),
    ], capture_output=True, text=True, timeout=60)


def test_connector_first_install_plan_handles_an_absent_unit(tmp_path: Path) -> None:
    tasks = yaml.safe_load((ROOT / "infra/roles/cloudflared/tasks/main.yml").read_text())
    template = next(t for t in tasks if t["name"] == "Install the bounded publisher connector service")
    inspect = next(t for t in tasks if t.get("register") == "cloudflared_installed_unit")
    service = next(t for t in tasks if t["name"] == "Keep the isolated publisher connector enabled")
    absent_unit = tmp_path / "cloudflared.service"
    template["ansible.builtin.template"].update(
        src=str(ROOT / "infra/roles/cloudflared/templates/cloudflared.service.j2"),
        dest=str(absent_unit), owner=None, group=None,
    )
    template.pop("notify")
    inspect["ansible.builtin.stat"]["path"] = str(absent_unit)
    result = run_readonly_tasks(tmp_path, [template, inspect, service], {})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "failed=0" in result.stdout
    assert not absent_unit.exists()


@pytest.mark.parametrize("receipt", [None, "wrong-host", "unverified", "wrong-gate", "bad-head", "valid"])
def test_timer_plan_requires_independent_exact_host_recovery_receipt(tmp_path: Path, receipt) -> None:
    tasks = yaml.safe_load((ROOT / "infra/roles/restic/tasks/main.yml").read_text())
    read = next(t for t in tasks if t.get("register") == "restic_gate_receipt")
    require = next(t for t in tasks if t["name"] == "Require exact-host recovery verification before starting timers")
    receipt_path = tmp_path / "wp07.yml"
    if receipt is not None:
        document = {"gate": "wp07-publish1", "host_id": "publish-1", "verified": True,
                    "reviewed_head": "a" * 40}
        if receipt == "wrong-host":
            document["host_id"] = "core-1"
        elif receipt == "unverified":
            document["verified"] = False
        elif receipt == "wrong-gate":
            document["gate"] = "wp06b-publish1"
        elif receipt == "bad-head":
            document["reviewed_head"] = "invalid"
        receipt_path.write_text(yaml.safe_dump(document))
    read["ansible.builtin.slurp"]["src"] = str(receipt_path)
    result = run_readonly_tasks(tmp_path, [read, require], {"restic_timer_enabled": True})
    assert (result.returncode == 0) == (receipt == "valid"), result.stdout + result.stderr
