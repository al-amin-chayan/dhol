"""Closure coverage for owned firewall rules.

`ufw allow` is additive, so a narrower contract would otherwise leave the older,
broader rule in place. Fixtures are captured from real `ufw status numbered`
output on Ubuntu 24.04, including the (v6) twin ufw creates by itself for an
"Anywhere" rule.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/roles/firewall/files/reconcile_ufw_rules.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_ufw_reconcile", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UFW = load_module()
OWNED = {"dholbeat-admin-ssh", "dholbeat-wireguard"}

CAPTURED = """Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    203.0.113.0/24             # dholbeat-admin-ssh
[ 2] 22/tcp                     ALLOW IN    10.99.0.0/24               # dholbeat-admin-ssh
[ 3] 51820/udp                  ALLOW IN    Anywhere                   # dholbeat-wireguard
[ 4] 8080/tcp                   ALLOW IN    Anywhere                   # someone-elses-rule
[ 5] 51820/udp (v6)             ALLOW IN    Anywhere (v6)              # dholbeat-wireguard
[ 6] 8080/tcp (v6)              ALLOW IN    Anywhere (v6)              # someone-elses-rule
"""

OFFICE = ("22/tcp", "203.0.113.0/24", "dholbeat-admin-ssh")
TUNNEL = ("22/tcp", "10.99.0.0/24", "dholbeat-admin-ssh")
LISTENER = ("51820/udp", "Anywhere", "dholbeat-wireguard")


def reconcile(desired, text: str = CAPTURED):
    return UFW.reconcile(text, OWNED, set(desired))


def test_the_public_phase_removes_nothing() -> None:
    obsolete, missing, findings = reconcile({OFFICE, TUNNEL, LISTENER})
    assert obsolete == []
    assert missing == []
    assert findings == []


def test_the_tunnel_phase_removes_exactly_the_public_ssh_rule() -> None:
    obsolete, missing, _ = reconcile({TUNNEL, LISTENER})
    assert obsolete == [1]
    assert missing == []


def test_the_auto_created_ipv6_twin_is_never_treated_as_obsolete() -> None:
    """ufw creates the (v6) rule itself; deleting it would fight the tool."""

    obsolete, _, _ = reconcile({TUNNEL, LISTENER})
    assert 5 not in obsolete


def test_rules_this_repository_does_not_own_are_never_touched() -> None:
    obsolete, _, _ = reconcile({TUNNEL, LISTENER})
    assert 4 not in obsolete and 6 not in obsolete


def test_changing_the_listener_port_removes_both_old_rules() -> None:
    obsolete, _, _ = reconcile({TUNNEL, ("51821/udp", "Anywhere", "dholbeat-wireguard")})
    assert 3 in obsolete and 5 in obsolete


def test_deletions_are_ordered_so_renumbering_cannot_skip_a_rule() -> None:
    obsolete, _, _ = reconcile({TUNNEL})
    assert obsolete == sorted(obsolete, reverse=True)


def test_rolling_back_to_no_vpn_removes_the_listener() -> None:
    obsolete, _, _ = reconcile({OFFICE})
    assert 3 in obsolete and 5 in obsolete and 2 in obsolete


def test_a_stale_rule_left_behind_fails_the_closure_assertion() -> None:
    stale = (
        "[ 1] 22/tcp     ALLOW IN    203.0.113.0/24    # dholbeat-admin-ssh\n"
        "[ 2] 22/tcp     ALLOW IN    10.99.0.0/24      # dholbeat-admin-ssh\n"
    )
    obsolete, _, _ = reconcile({TUNNEL}, stale)
    assert obsolete, "closure must fail while the public path is still open"


def test_a_missing_desired_rule_is_reported() -> None:
    _, missing, _ = reconcile({TUNNEL, LISTENER}, "")
    assert len(missing) == 2


def test_a_host_ssh_rule_rendered_without_its_prefix_still_matches() -> None:
    """ufw renders a /32 source as a bare address."""

    text = "[ 1] 22/tcp   ALLOW IN    198.51.100.7    # dholbeat-admin-ssh\n"
    obsolete, missing, _ = reconcile(
        {("22/tcp", "198.51.100.7", "dholbeat-admin-ssh")}, text
    )
    assert obsolete == [] and missing == []


@pytest.mark.parametrize("row", ["[ 1] nonsense", "[ 2] 22/tcp ALLOW"])
def test_an_unparseable_numbered_row_fails_closed(row: str) -> None:
    _, _, findings = reconcile({TUNNEL}, row + "\n")
    assert any("could not be parsed" in finding for finding in findings), findings


def test_a_malformed_desired_specification_is_rejected() -> None:
    desired, findings = UFW.desired_tuples(["22/tcp|only-two-parts"])
    assert findings and not desired


def test_header_lines_are_not_mistaken_for_rules() -> None:
    _, _, findings = reconcile({TUNNEL, LISTENER, OFFICE})
    assert findings == []
