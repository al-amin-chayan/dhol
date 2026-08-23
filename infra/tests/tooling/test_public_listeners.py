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


def parse(sample: str) -> list[tuple[str, str, str]]:
    sockets = []
    for line in sample.splitlines():
        match = LISTENERS.LISTEN_RE.match(line.strip())
        if match is None:
            continue
        local = LISTENERS.split_local(match.group("local"))
        assert local is not None
        sockets.append((match.group("protocol"), local[0], local[1]))
    return sockets


SS_SAMPLE = """
tcp   LISTEN 0      4096       127.0.0.1:5432      0.0.0.0:*
tcp   LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
tcp   LISTEN 0      4096         0.0.0.0:8080      0.0.0.0:*
udp   UNCONN 0      0          127.0.0.53:53       0.0.0.0:*
"""


def test_only_the_declared_ssh_port_may_answer_publicly() -> None:
    public = [
        (protocol, port)
        for protocol, address, port in parse(SS_SAMPLE)
        if LISTENERS.is_public_binding(address)
    ]
    assert ("tcp", "22") in public
    assert ("tcp", "8080") in public, "an undeclared published port must be reported"
    assert ("tcp", "5432") not in public
    assert ("udp", "53") not in public
