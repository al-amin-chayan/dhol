#!/usr/bin/env python3
"""Prove the Docker daemon is reachable only over its declared Unix socket.

Checking two conventional TCP ports is not the contract. Drift can put
``"hosts": ["tcp://127.0.0.1:4243"]`` in daemon configuration, or add a
``-H tcp://...`` argument on a nonstandard port, and a loopback binding is
deliberately ignored by the public-listener probe. A local TCP Docker API is
still an unnecessary privilege boundary and is not the declared Unix socket.

This validator therefore rejects every non-Unix host declaration wherever it
appears, and every TCP socket the daemon itself is listening on.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


# ``fd://`` is systemd socket activation of the Unix socket, not a network host.
ALLOWED_SCHEMES = ("unix://", "fd://")
HOST_ARGUMENT_RE = re.compile(r"(?:^|\s)(?:-H|--host(?:=|\s+))\s*(?P<value>\S+)")
DOCKER_PROCESS_RE = re.compile(r"\bdockerd\b")
PROTOCOL_TOKENS = {"tcp", "tcp6", "udp", "udp6"}
# systemd serializes the Listen property endpoint-first, as "<endpoint> (<Kind>)".
# Captured from `systemctl show docker.socket --property=Listen --value` on
# Ubuntu 24.04: "/run/docker.sock (Stream)".
LISTEN_ENTRY_RE = re.compile(r"^(?P<endpoint>\S.*?)\s+\((?P<kind>[A-Za-z]+)\)$")
EXPECTED_SOCKET_KIND = "Stream"


def non_unix(hosts: Any) -> list[str]:
    if not isinstance(hosts, list):
        return [] if hosts is None else [str(hosts)]
    return [str(host) for host in hosts if not str(host).startswith(ALLOWED_SCHEMES)]


def exec_start_hosts(exec_start: str) -> list[str]:
    return [match.group("value") for match in HOST_ARGUMENT_RE.finditer(exec_start or "")]


def is_network_endpoint(value: str) -> bool:
    """A network endpoint is host:port; a Unix socket never appears in ss -t/-u."""

    address, separator, port = value.rpartition(":")
    return bool(separator) and port.isdigit()


def daemon_socket_findings(socket_table: str) -> list[str]:
    """Report every network socket the daemon owns, in either ss output shape.

    ``ss`` omits the Netid column when a single protocol is selected, so
    ``--tcp`` alone yields ``LISTEN 0 128 127.0.0.1:4243 ...`` while
    ``--tcp --udp`` yields ``tcp LISTEN 0 128 ...``. Both are parsed. A row
    attributed to the daemon that cannot be parsed is a finding, never a skip:
    an unparsed row is indistinguishable from an exposed daemon.
    """

    findings: list[str] = []
    for raw_line in (socket_table or "").splitlines():
        line = raw_line.strip()
        if not line or not DOCKER_PROCESS_RE.search(line):
            continue
        fields = line.split()
        if fields and fields[0].lower() in PROTOCOL_TOKENS:
            protocol = fields[0].lower()
            columns = fields[1:]
        else:
            protocol = "network"
            columns = fields
        if len(columns) < 4 or not is_network_endpoint(columns[3]):
            findings.append(f"a Docker-attributed socket row could not be parsed: {line}")
            continue
        findings.append(f"the Docker daemon is listening on a {protocol} socket: {columns[3]}")
    return findings


def socket_activation_findings(listen_text: str, uses_socket_activation: bool) -> list[str]:
    """Validate what systemd actually hands the daemon.

    ``fd://`` is only Unix-only if the activating socket unit is. A drifted
    ``docker.socket`` can carry ``ListenStream=127.0.0.1:2375`` while ExecStart
    still reads ``-H fd://``.

    The parsed form is systemd's own serialization, endpoint first. A missing
    unit yields empty output, which is itself a finding when ExecStart claims
    socket activation.
    """

    findings: list[str] = []
    endpoints = 0
    for raw_line in (listen_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LISTEN_ENTRY_RE.match(line)
        if match is None:
            findings.append(f"docker.socket Listen entry could not be parsed: {line}")
            continue
        endpoints += 1
        endpoint = match.group("endpoint")
        kind = match.group("kind")
        if kind != EXPECTED_SOCKET_KIND:
            findings.append(
                f"docker.socket declares an unexpected socket kind: {endpoint} ({kind})"
            )
        if not endpoint.startswith("/"):
            findings.append(
                f"docker.socket activates a non-filesystem endpoint: {endpoint} ({kind})"
            )
    if uses_socket_activation and endpoints == 0:
        findings.append(
            "the daemon uses fd:// socket activation but docker.socket declares no endpoint"
        )
    return findings


def validate(document: dict[str, Any]) -> list[str]:
    findings: list[str] = []

    declared = document.get("declared_hosts")
    for host in non_unix(declared):
        findings.append(f"declared docker_daemon_hosts entry is not a Unix socket: {host}")

    configured = (document.get("daemon_config") or {}).get("hosts")
    if configured is not None:
        for host in non_unix(configured):
            findings.append(f"daemon.json declares a non-Unix Docker host: {host}")
        if isinstance(configured, list) and isinstance(declared, list):
            if [str(item) for item in configured] != [str(item) for item in declared]:
                findings.append(
                    "daemon.json hosts do not match the declared docker_daemon_hosts contract"
                )

    uses_socket_activation = False
    for host in exec_start_hosts(document.get("exec_start", "")):
        if host.startswith("fd://"):
            uses_socket_activation = True
            continue
        if not host.startswith(ALLOWED_SCHEMES):
            findings.append(f"the Docker systemd command line declares a non-Unix host: {host}")

    findings.extend(daemon_socket_findings(document.get("socket_table", "")))
    findings.extend(
        socket_activation_findings(document.get("socket_activation", ""), uses_socket_activation)
    )
    return sorted(set(findings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    arguments = parser.parse_args()
    raw = sys.stdin.read() if arguments.input == "-" else open(arguments.input, encoding="utf-8").read()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit(f"docker listener failure: invalid input: {error}") from error
    if not isinstance(document, dict):
        raise SystemExit("docker listener failure: input must be a JSON object")

    findings = validate(document)
    if findings:
        for finding in findings:
            print(f"docker listener failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print("docker daemon is Unix-socket-only")


if __name__ == "__main__":
    main()
