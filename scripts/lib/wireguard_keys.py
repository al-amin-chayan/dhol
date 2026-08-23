#!/usr/bin/env python3
"""Curve25519 key generation for WireGuard peers, with no external dependency.

The pinned controller carries no `wg` binary and no cryptography package, and
adding either to satisfy one helper is not worth the supply-chain surface. X25519
is fully specified in RFC 7748, so it is implemented here and verified against
that document's own test vectors in the test suite. Nothing here is invented.
"""

from __future__ import annotations

import base64
import os


FIELD_PRIME = 2**255 - 19
A24 = 121665
BASE_POINT = (9).to_bytes(32, "little")


def clamp(scalar: bytes) -> bytes:
    material = bytearray(scalar)
    material[0] &= 248
    material[31] &= 127
    material[31] |= 64
    return bytes(material)


def x25519(scalar: bytes, point: bytes) -> bytes:
    """RFC 7748 §5 X25519 scalar multiplication."""

    k = int.from_bytes(clamp(scalar), "little")
    x1 = int.from_bytes(point, "little") % FIELD_PRIME
    x2, z2, x3, z3 = 1, 0, x1, 1
    swap = 0
    for bit in range(254, -1, -1):
        current = (k >> bit) & 1
        swap ^= current
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = current

        a = (x2 + z2) % FIELD_PRIME
        aa = a * a % FIELD_PRIME
        b = (x2 - z2) % FIELD_PRIME
        bb = b * b % FIELD_PRIME
        e = (aa - bb) % FIELD_PRIME
        c = (x3 + z3) % FIELD_PRIME
        d = (x3 - z3) % FIELD_PRIME
        da = d * a % FIELD_PRIME
        cb = c * b % FIELD_PRIME
        x3 = pow((da + cb) % FIELD_PRIME, 2, FIELD_PRIME)
        z3 = x1 * pow((da - cb) % FIELD_PRIME, 2, FIELD_PRIME) % FIELD_PRIME
        x2 = aa * bb % FIELD_PRIME
        z2 = e * ((aa + A24 * e) % FIELD_PRIME) % FIELD_PRIME
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * pow(z2, FIELD_PRIME - 2, FIELD_PRIME) % FIELD_PRIME).to_bytes(32, "little")


def public_key(private_key: bytes) -> bytes:
    return x25519(private_key, BASE_POINT)


def generate_private_key() -> bytes:
    return clamp(os.urandom(32))


def encode(key: bytes) -> str:
    return base64.b64encode(key).decode("ascii")


def decode(value: str) -> bytes:
    material = base64.b64decode(value, validate=True)
    if len(material) != 32:
        raise ValueError("a WireGuard key must be 32 bytes")
    return material


def _main() -> None:
    """Derive the public half of an escrowed key, so a backup can be confirmed.

    The private key is read and never echoed. Only the public half is printed,
    which is the value committed as vpn.server_public_key.
    """

    import argparse
    import sys

    parser = argparse.ArgumentParser(description=_main.__doc__)
    parser.add_argument(
        "--public-of", required=True, help="file holding one base64 private key, or - for stdin"
    )
    arguments = parser.parse_args()
    source = sys.stdin if arguments.public_of == "-" else open(arguments.public_of, encoding="utf-8")
    with source as handle:
        material = handle.read().strip()
    try:
        private_key = decode(material)
    except Exception:  # noqa: BLE001 - any decode failure is fatal and must not echo input
        raise SystemExit("wireguard key failure: input is not a base64 WireGuard key") from None
    print(encode(public_key(private_key)))


if __name__ == "__main__":
    _main()
