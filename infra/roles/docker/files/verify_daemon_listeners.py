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


def non_unix(hosts: Any) -> list[str]:
    if not isinstance(hosts, list):
        return [] if hosts is None else [str(hosts)]
    return [str(host) for host in hosts if not str(host).startswith(ALLOWED_SCHEMES)]


def exec_start_hosts(exec_start: str) -> list[str]:
    return [match.group("value") for match in HOST_ARGUMENT_RE.finditer(exec_start or "")]


def daemon_tcp_listeners(socket_table: str) -> list[str]:
    listeners: list[str] = []
    for raw_line in (socket_table or "").splitlines():
        line = raw_line.strip()
        if not line or not DOCKER_PROCESS_RE.search(line):
            continue
        fields = line.split()
        if not fields or fields[0].lower() not in {"tcp", "tcp6"}:
            continue
        listeners.append(fields[4] if len(fields) > 4 else line)
    return listeners


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

    for host in exec_start_hosts(document.get("exec_start", "")):
        if not host.startswith(ALLOWED_SCHEMES):
            findings.append(f"the Docker systemd command line declares a non-Unix host: {host}")

    for listener in daemon_tcp_listeners(document.get("socket_table", "")):
        findings.append(f"the Docker daemon is listening on a TCP socket: {listener}")

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
