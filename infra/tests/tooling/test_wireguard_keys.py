"""Curve25519 coverage, anchored to RFC 7748's own test vectors.

The controller carries no `wg` binary and no cryptography package, so key
generation is implemented in-repo. That is only defensible if it is checked
against the specification rather than against itself, which is what these
vectors do.
"""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/wireguard-peer-config"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "dholbeat_wireguard_keys", ROOT / "scripts/lib/wireguard_keys.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEYS = load_module()

# RFC 7748 §6.1.
ALICE_PRIVATE = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
ALICE_PUBLIC = bytes.fromhex("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
BOB_PRIVATE = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
BOB_PUBLIC = bytes.fromhex("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
SHARED = bytes.fromhex("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")


@pytest.mark.parametrize(
    ("private_key", "expected"), [(ALICE_PRIVATE, ALICE_PUBLIC), (BOB_PRIVATE, BOB_PUBLIC)]
)
def test_public_keys_match_rfc_7748(private_key: bytes, expected: bytes) -> None:
    assert KEYS.public_key(private_key) == expected


def test_the_shared_secret_matches_rfc_7748_in_both_directions() -> None:
    assert KEYS.x25519(ALICE_PRIVATE, BOB_PUBLIC) == SHARED
    assert KEYS.x25519(BOB_PRIVATE, ALICE_PUBLIC) == SHARED


def test_clamping_follows_the_specification() -> None:
    clamped = KEYS.clamp(b"\xff" * 32)
    assert clamped[0] & 0b111 == 0
    assert clamped[31] & 0b1000_0000 == 0
    assert clamped[31] & 0b0100_0000 == 0b0100_0000


def test_a_generated_key_is_clamped_and_encodes_to_a_wireguard_key() -> None:
    private_key = KEYS.generate_private_key()
    assert private_key == KEYS.clamp(private_key)
    encoded = KEYS.encode(KEYS.public_key(private_key))
    assert len(encoded) == 44 and encoded.endswith("=")
    assert KEYS.decode(encoded) == KEYS.public_key(private_key)


def test_generated_keys_differ_between_invocations() -> None:
    assert KEYS.generate_private_key() != KEYS.generate_private_key()


@pytest.mark.parametrize("value", ["", "not-base64!", base64.b64encode(b"short").decode()])
def test_a_value_that_is_not_a_wireguard_key_is_rejected(value: str) -> None:
    with pytest.raises(Exception):
        KEYS.decode(value)


# --- the peer configuration helper ---

SERVER_PUBLIC = "e7/ZaJLicDvGUR0fIh2niBTF5DbEXIxBp9IydY5vCF4="


def run_helper(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *arguments], capture_output=True, text=True
    )


def base_arguments(output: Path) -> list[str]:
    return [
        "--peer-id", "founder-laptop",
        "--address", "10.99.0.2/32",
        "--subnet", "10.99.0.0/24",
        "--server-public-key", SERVER_PUBLIC,
        "--endpoint", "203.0.113.20:51820",
        "--output", str(output),
    ]


def test_the_helper_writes_a_peer_file_and_prints_only_the_public_key(tmp_path: Path) -> None:
    output = tmp_path / "peer.conf"
    completed = run_helper(*base_arguments(output))
    assert completed.returncode == 0, completed.stderr

    body = output.read_text(encoding="utf-8")
    private_line = next(line for line in body.splitlines() if line.startswith("PrivateKey = "))
    private_value = private_line.split(" = ", 1)[1]

    assert private_value not in completed.stdout, "the private key must never be printed"
    assert "public_key:" in completed.stdout
    printed = next(
        line.split("public_key:")[1].strip()
        for line in completed.stdout.splitlines()
        if "public_key:" in line
    )
    assert printed == KEYS.encode(KEYS.public_key(KEYS.decode(private_value)))
    assert oct(output.stat().st_mode)[-3:] == "600"


def test_the_helper_refuses_to_write_inside_the_repository() -> None:
    completed = run_helper(*base_arguments(ROOT / ".artifacts/peer.conf"))
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr + completed.stdout


def test_the_helper_refuses_to_overwrite_an_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "peer.conf"
    output.write_text("existing\n", encoding="utf-8")
    completed = run_helper(*base_arguments(output))
    assert completed.returncode != 0
    assert "refusing to overwrite" in completed.stderr + completed.stdout


def test_the_helper_omits_the_peer_block_before_the_host_has_a_key(tmp_path: Path) -> None:
    """The server key does not exist until the first convergence."""

    output = tmp_path / "peer.conf"
    completed = run_helper(
        "--peer-id", "founder-laptop", "--address", "10.99.0.2/32",
        "--subnet", "10.99.0.0/24", "--output", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    body = output.read_text(encoding="utf-8")
    assert "[Interface]" in body
    assert "[Peer]" not in body
    assert "public_key:" in completed.stdout
    assert "<server-public-key>" in completed.stdout


def test_the_helper_requires_the_endpoint_and_server_key_together(tmp_path: Path) -> None:
    completed = run_helper(
        "--peer-id", "founder-laptop", "--address", "10.99.0.2/32",
        "--subnet", "10.99.0.0/24", "--server-public-key", SERVER_PUBLIC,
        "--output", str(tmp_path / "peer.conf"),
    )
    assert completed.returncode != 0
    assert "must be supplied together" in completed.stderr


@pytest.mark.parametrize(
    ("flag", "value", "expected"),
    [
        ("--address", "10.99.0.0/24", "single address"),
        ("--address", "10.50.0.2/32", "outside --subnet"),
        ("--server-public-key", "not-a-key", "not a valid WireGuard key"),
        ("--endpoint", "203.0.113.20", "<host>:<port>"),
        ("--subnet", "not-a-network", "not a valid network"),
    ],
)
def test_the_helper_validates_its_inputs(
    flag: str, value: str, expected: str, tmp_path: Path
) -> None:
    arguments = base_arguments(tmp_path / "peer.conf")
    arguments[arguments.index(flag) + 1] = value
    completed = run_helper(*arguments)
    assert completed.returncode != 0
    assert expected in completed.stderr
    assert not (tmp_path / "peer.conf").exists()


# --- Escrow confirmation by derivation (PR44-R04) ---

MODULE = ROOT / "scripts/lib/wireguard_keys.py"


def derive(material: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODULE), "--public-of", "-"],
        input=material, capture_output=True, text=True,
    )


def test_an_escrowed_key_derives_to_its_committed_public_half() -> None:
    """This equality is the escrow postcondition, not a nicety."""

    private_key = KEYS.generate_private_key()
    completed = derive(KEYS.encode(private_key))
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == KEYS.encode(KEYS.public_key(private_key))


def test_the_private_key_is_never_echoed_back() -> None:
    private_key = KEYS.encode(KEYS.generate_private_key())
    completed = derive(private_key)
    assert private_key not in completed.stdout
    assert private_key not in completed.stderr


def test_trailing_whitespace_in_an_export_is_tolerated() -> None:
    private_key = KEYS.generate_private_key()
    assert derive(KEYS.encode(private_key) + "\n\n").stdout.strip() == KEYS.encode(
        KEYS.public_key(private_key)
    )


@pytest.mark.parametrize("material", ["not-a-key", "", "AAAA"])
def test_a_bad_export_fails_without_echoing_it(material: str) -> None:
    completed = derive(material)
    assert completed.returncode != 0
    if material:
        assert material not in completed.stderr


# --- Guarded rotation wrapper (PR44-R04) ---

SERVER_KEY_TOOL = ROOT / "scripts/wireguard-server-key"


def printed_server_key(stdout: str) -> str:
    """Read the emitted value, not the prose line that also names the field."""

    return next(
        line.split(":", 1)[1].strip()
        for line in stdout.splitlines()
        if line.strip().startswith("server_public_key:")
    )


def server_key(output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SERVER_KEY_TOOL), "--output", str(output)],
        capture_output=True, text=True,
    )


def test_a_rotated_key_is_written_0600_and_never_printed(tmp_path: Path) -> None:
    output = tmp_path / "wg0.key"
    completed = server_key(output)
    assert completed.returncode == 0, completed.stderr
    material = output.read_text(encoding="utf-8").strip()
    assert material not in completed.stdout
    assert oct(output.stat().st_mode)[-3:] == "600"


def test_the_printed_public_half_matches_the_written_key(tmp_path: Path) -> None:
    output = tmp_path / "wg0.key"
    completed = server_key(output)
    printed = printed_server_key(completed.stdout)
    private_key = KEYS.decode(output.read_text(encoding="utf-8").strip())
    assert printed == KEYS.encode(KEYS.public_key(private_key))


def test_rotation_refuses_to_clobber_an_existing_key(tmp_path: Path) -> None:
    """Shell redirection would have silently destroyed the live identity."""

    output = tmp_path / "wg0.key"
    assert server_key(output).returncode == 0
    original = output.read_text(encoding="utf-8")
    repeated = server_key(output)
    assert repeated.returncode != 0
    assert "refusing to overwrite" in repeated.stderr
    assert output.read_text(encoding="utf-8") == original


def test_rotation_refuses_a_path_inside_the_repository() -> None:
    completed = server_key(ROOT / ".artifacts/wg0.key")
    assert completed.returncode != 0
    assert "outside the repository" in completed.stderr


def test_a_rotated_key_round_trips_through_the_derivation_check(tmp_path: Path) -> None:
    """Rotation and escrow confirmation must agree on the same value."""

    output = tmp_path / "wg0.key"
    completed = server_key(output)
    printed = printed_server_key(completed.stdout)
    assert derive(output.read_text(encoding="utf-8")).stdout.strip() == printed
