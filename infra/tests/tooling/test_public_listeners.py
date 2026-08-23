"""Coverage for the read-only public-listener probe used by infra/playbooks/verify.yml."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/playbooks/files/verify_public_listeners.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_public_listeners", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LISTENERS = load_module()


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "10.4.0.7", "172.18.0.1", "192.168.1.5"])
def test_loopback_and_private_bindings_are_not_public(address: str) -> None:
    assert LISTENERS.is_public_binding(address) is False


@pytest.mark.parametrize("address", ["0.0.0.0", "*", "203.0.113.9", "2001:db8::1", ""])
def test_unspecified_and_routable_bindings_are_public(address: str) -> None:
    assert LISTENERS.is_public_binding(address) is True


def test_an_unparseable_address_is_treated_as_public() -> None:
    assert LISTENERS.is_public_binding("%eth0") is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.0.0.0:22", ("0.0.0.0", "22")),
        ("[::]:22", ("::", "22")),
        ("[2001:db8::1]:5432", ("2001:db8::1", "5432")),
        ("*:5432", ("*", "5432")),
    ],
)
def test_local_socket_addresses_split_correctly(value: str, expected: tuple[str, str]) -> None:
    assert LISTENERS.split_local(value) == expected


def test_a_malformed_socket_address_is_skipped() -> None:
    assert LISTENERS.split_local("nonsense") is None


SS_SAMPLE = """
tcp   LISTEN 0      4096       127.0.0.1:5432      0.0.0.0:*
tcp   LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
udp   UNCONN 0      0          127.0.0.53:53       0.0.0.0:*
"""


def test_a_declared_public_tcp_port_passes() -> None:
    assert LISTENERS.evaluate(SS_SAMPLE, ["tcp/22"]) == []


def test_an_undeclared_public_tcp_port_is_reported() -> None:
    sample = SS_SAMPLE + "tcp   LISTEN 0 4096 0.0.0.0:8080 0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("tcp/8080 listens on a public address" in finding for finding in findings)


def test_the_same_port_on_another_protocol_is_not_covered() -> None:
    sample = SS_SAMPLE + "udp   UNCONN 0 0 0.0.0.0:22 0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("udp/22 listens on a public address" in finding for finding in findings)


def test_an_unparseable_row_fails_closed_instead_of_being_skipped() -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE + "wat is this row\n", ["tcp/22"])
    assert any("could not be parsed" in finding for finding in findings)


def test_a_malformed_local_address_fails_closed() -> None:
    sample = "tcp   LISTEN 0      4096       nonsense      0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("could not be parsed" in finding for finding in findings)


def test_blank_rows_are_not_treated_as_unparseable() -> None:
    assert LISTENERS.evaluate("\n\n" + SS_SAMPLE + "\n   \n", ["tcp/22"]) == []


@pytest.mark.parametrize("entry", ["22", "tcp:22", "tcp/", "sctp/22", "tcp/0"])
def test_an_allowlist_entry_that_is_not_protocol_slash_port_is_rejected(entry: str) -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE, [entry])
    assert any("not protocol/port" in finding for finding in findings)


def test_an_empty_allowlist_is_rejected() -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE, [])
    assert any("no public protocol/port pair was declared" in finding for finding in findings)


def test_private_and_loopback_listeners_never_need_declaring() -> None:
    sample = (
        "tcp   LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:*\n"
        "tcp   LISTEN 0 4096 10.4.0.7:6379 0.0.0.0:*\n"
        "tcp   LISTEN 0 4096 [::1]:9090 [::]:*\n"
        "tcp   LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n"
    )
    assert LISTENERS.evaluate(sample, ["tcp/22"]) == []


def test_a_public_ipv6_listener_is_reported() -> None:
    sample = "tcp   LISTEN 0 4096 [2001:db8::1]:8443 [::]:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("tcp/8443 listens on a public address" in finding for finding in findings)
