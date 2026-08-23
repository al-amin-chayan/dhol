#!/usr/bin/env python3
"""Fail closed when a host listener is reachable outside loopback or private networks.

The script is read-only. It reads the kernel socket table through ``ss`` and
compares every listening socket against the exact ports the reviewed baseline
allows to answer on a public interface.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys


LISTEN_RE = re.compile(r"^(?P<protocol>tcp|udp)\s+\S+\s+\S+\s+\S+\s+(?P<local>\S+)\s")
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def split_local(value: str) -> tuple[str, str] | None:
    address, separator, port = value.rpartition(":")
    if not separator or not port:
        return None
    return address.strip("[]"), port


def is_public_binding(address: str) -> bool:
    if address in {"*", ""}:
        return True
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return True
    if parsed.is_loopback or parsed.is_link_local:
        return False
    if parsed.is_unspecified:
        return True
    return not any(parsed in network for network in PRIVATE_NETWORKS)


def listening_sockets() -> list[tuple[str, str, str]]:
    completed = subprocess.run(
        ["ss", "-H", "--listening", "--numeric", "--tcp", "--udp"],
        check=True,
        capture_output=True,
        text=True,
    )
    sockets: list[tuple[str, str, str]] = []
    for line in completed.stdout.splitlines():
        match = LISTEN_RE.match(line.strip())
        if match is None:
            continue
        local = split_local(match.group("local"))
        if local is None:
            continue
        sockets.append((match.group("protocol"), local[0], local[1]))
    return sockets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-public-port",
        action="append",
        default=[],
        help="port permitted to listen on a public address, repeatable",
    )
    arguments = parser.parse_args()
    allowed = {str(port) for port in arguments.allow_public_port}

    findings: list[str] = []
    inspected = 0
    for protocol, address, port in listening_sockets():
        inspected += 1
        if not is_public_binding(address):
            continue
        if port not in allowed:
            findings.append(f"{protocol}/{port} listens on a public address {address or '*'}")

    if findings:
        for finding in sorted(set(findings)):
            print(f"public listener failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print(f"public_listeners_allowed={','.join(sorted(allowed))} inspected={inspected}")


if __name__ == "__main__":
    main()
