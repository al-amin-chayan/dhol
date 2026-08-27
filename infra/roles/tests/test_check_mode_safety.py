"""Every live-state assertion in the baseline roles must be check-mode guarded.

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

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
ROLE_TASK_FILES = sorted(
    path
    for role in ("base", "docker", "firewall", "wireguard", "release_receipt", "publisher")
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

    assert len(ROLE_TASK_FILES) >= 8
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
