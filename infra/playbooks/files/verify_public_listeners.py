#!/usr/bin/env python3
"""Fail closed when a host listener is reachable outside loopback or private networks.

The script is read-only. It reads the kernel socket table through ``ss`` and
compares every listening socket against the exact protocol/port pairs the
reviewed baseline allows to answer on a public interface.

Parsing fails closed. A nonempty row that cannot be understood is reported
rather than skipped, because an unparsed row is indistinguishable from an
undeclared service.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys


LISTEN_RE = re.compile(r"^(?P<protocol>tcp|udp)\s+\S+\s+\S+\s+\S+\s+(?P<local>\S+)(?:\s|$)")
ALLOW_RE = re.compile(r"^(?P<protocol>tcp|udp)/(?P<port>[1-9][0-9]{0,4})$")
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
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return True
    if parsed.is_loopback or parsed.is_link_local:
        return False
    if parsed.is_unspecified:
        return True
    return not any(parsed in network for network in PRIVATE_NETWORKS)


def parse_socket_table(output: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Return every listening socket plus every row that could not be parsed."""

    sockets: list[tuple[str, str, str]] = []
    unparsed: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LISTEN_RE.match(line)
        if match is None:
            unparsed.append(line)
            continue
        local = split_local(match.group("local"))
        if local is None:
            unparsed.append(line)
            continue
        sockets.append((match.group("protocol"), local[0], local[1]))
    return sockets, unparsed


def parse_allowlist(values: list[str]) -> tuple[set[tuple[str, str]], list[str]]:
    allowed: set[tuple[str, str]] = set()
    invalid: list[str] = []
    for value in values:
        match = ALLOW_RE.match(value.strip())
        if match is None:
            invalid.append(value)
            continue
        allowed.add((match.group("protocol"), match.group("port")))
    return allowed, invalid


def evaluate(output: str, allow_values: list[str]) -> list[str]:
    allowed, invalid = parse_allowlist(allow_values)
    findings = [f"allowlist entry is not protocol/port: {value}" for value in invalid]
    if not allowed and not invalid:
        findings.append("no public protocol/port pair was declared")

    sockets, unparsed = parse_socket_table(output)
    findings.extend(f"socket table row could not be parsed: {row}" for row in unparsed)
    for protocol, address, port in sockets:
        if not is_public_binding(address):
            continue
        if (protocol, port) not in allowed:
            findings.append(f"{protocol}/{port} listens on a public address {address or '*'}")
    return sorted(set(findings))


def listening_socket_table() -> str:
    completed = subprocess.run(
        ["ss", "--no-header", "--listening", "--numeric", "--tcp", "--udp"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-public",
        action="append",
        default=[],
        help="protocol/port pair permitted on a public address, such as tcp/22; repeatable",
    )
    arguments = parser.parse_args()

    findings = evaluate(listening_socket_table(), arguments.allow_public)
    if findings:
        for finding in findings:
            print(f"public listener failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print(f"public_listeners_allowed={','.join(sorted(arguments.allow_public))}")


if __name__ == "__main__":
    main()
