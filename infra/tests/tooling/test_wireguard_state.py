"""Coverage for the host-side WireGuard verifier.

Every fixture is captured from real `wg` output on Ubuntu 24.04, not written
from memory. The interface line's first field is the server private key, which
is why this probe runs on the host and why these tests assert it never survives
parsing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/roles/wireguard/files/verify_wireguard_state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_wireguard_state", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WG = load_module()

# Captured verbatim from `wg show wg0 dump`. The keys are throwaway values from
# an ephemeral container that was removed; the shape is what matters.
SERVER_PRIVATE = "qKVseOxyFNQpMuaMIom3hTDxGwQmrGN/yf36mGSPxHk="
SERVER_PUBLIC = "e7/ZaJLicDvGUR0fIh2niBTF5DbEXIxBp9IydY5vCF4="
PEER_ONE = "HBUM1KiVWeNe5vNANfq6gv8cqxUn60efcsLXMPjZdRk="
PEER_TWO = "6wv6jnLo7bP3mV32NlgHfMD0pYcKdp2W4+SS8h2xj2c="

REAL_DUMP = (
    f"{SERVER_PRIVATE}\t{SERVER_PUBLIC}\t51820\toff\n"
    f"{PEER_ONE}\t(none)\t(none)\t10.99.0.2/32\t0\t0\t0\toff\n"
    f"{PEER_TWO}\t(none)\t(none)\t10.99.0.3/32\t0\t0\t0\t25\n"
)
DECLARED = {PEER_ONE: ["10.99.0.2/32"], PEER_TWO: ["10.99.0.3/32"]}
SUBNET = "10.99.0.0/24"
HOST_ADDRESS = "10.99.0.1/24"


def parsed():
    interface, peers, findings = WG.parse_dump(REAL_DUMP)
    assert findings == []
    return interface, peers


def check(**overrides):
    interface, peers = parsed()
    settings = {
        "interface": interface,
        "peers": peers,
        "declared_peers": DECLARED,
        "listen_port": 51820,
        "subnet": SUBNET,
        "host_address": HOST_ADDRESS,
        "interface_addresses": [HOST_ADDRESS],
    }
    settings.update(overrides)
    return WG.validate(**settings)


def test_the_server_private_key_never_survives_parsing() -> None:
    """The dump's first field is the private key; it must be dropped at once."""

    interface, peers = parsed()
    serialized = repr(interface) + repr(peers)
    assert SERVER_PRIVATE not in serialized
    assert SERVER_PUBLIC in serialized


def test_the_real_dump_parses_into_interface_and_peers() -> None:
    interface, peers = parsed()
    assert interface["listen_port"] == "51820"
    assert interface["public_key"] == SERVER_PUBLIC
    assert [peer["public_key"] for peer in peers] == [PEER_ONE, PEER_TWO]
    assert peers[0]["allowed_ips"] == ["10.99.0.2/32"]
    assert peers[1]["keepalive"] == "25"


def test_a_conforming_interface_passes() -> None:
    assert check() == []


def test_a_drifted_listen_port_is_reported() -> None:
    assert any("listen port" in finding for finding in check(listen_port=51821))


def test_an_undeclared_peer_is_reported() -> None:
    findings = check(declared_peers={PEER_ONE: ["10.99.0.2/32"]})
    assert any("undeclared WireGuard peer" in finding for finding in findings), findings


def test_a_missing_declared_peer_is_reported() -> None:
    declared = dict(DECLARED)
    declared["RklYVFVSRS1QRUVSLU9ORS0tLS0tLS0tLS0tLS0tLS0="] = ["10.99.0.9/32"]
    findings = check(declared_peers=declared)
    assert any("declared WireGuard peer is absent" in finding for finding in findings), findings


def test_a_peer_allowed_more_than_its_declaration_is_reported() -> None:
    findings = check(declared_peers={PEER_ONE: ["10.99.0.5/32"], PEER_TWO: ["10.99.0.3/32"]})
    assert any("allowed IPs outside its declaration" in finding for finding in findings), findings


def test_a_reported_peer_never_echoes_a_full_key() -> None:
    findings = check(declared_peers={PEER_ONE: ["10.99.0.2/32"]})
    assert findings
    assert all(PEER_TWO not in finding for finding in findings)


def test_the_reviewed_identity_is_asserted_when_declared() -> None:
    """A replaced host key must not pass verification silently."""

    interface, peers = parsed()
    assert check(expected_public_key=SERVER_PUBLIC) == []
    findings = check(expected_public_key=PEER_ONE)
    assert any("differs from the reviewed public key" in f for f in findings), findings


def test_no_expected_key_means_no_identity_assertion() -> None:
    assert check(expected_public_key="") == []


def test_a_missing_tunnel_address_is_reported() -> None:
    findings = check(interface_addresses=[])
    assert any("does not carry the declared host address" in f for f in findings), findings


def test_an_address_outside_the_subnet_is_reported() -> None:
    findings = check(interface_addresses=[HOST_ADDRESS, "192.168.50.1/24"])
    assert any("outside the declared subnet" in finding for finding in findings), findings


def test_an_empty_dump_fails_closed() -> None:
    _, _, findings = WG.parse_dump("")
    assert findings


def test_a_truncated_interface_line_fails_closed() -> None:
    _, _, findings = WG.parse_dump("only\ttwo\n")
    assert any("interface line could not be parsed" in finding for finding in findings), findings


def test_a_truncated_peer_row_fails_closed() -> None:
    _, _, findings = WG.parse_dump(f"{SERVER_PRIVATE}\t{SERVER_PUBLIC}\t51820\toff\nbroken\n")
    assert any("peer row" in finding for finding in findings), findings


@pytest.mark.parametrize(
    "value", ["missing-separator", "not-a-key|10.99.0.2/32", "|10.99.0.2/32"]
)
def test_a_malformed_declared_peer_is_rejected(value: str) -> None:
    _, findings = WG.parse_declared_peers([value])
    assert findings


def test_a_declared_peer_parses_despite_the_trailing_equals_in_keys() -> None:
    declared, findings = WG.parse_declared_peers([f"{PEER_ONE}|10.99.0.2/32"])
    assert findings == []
    assert declared == {PEER_ONE: ["10.99.0.2/32"]}
