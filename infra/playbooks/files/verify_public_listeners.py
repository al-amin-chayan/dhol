#!/usr/bin/env python3
"""Fail closed when a host listener is reachable outside loopback or private networks.

The script is read-only. It reads the kernel socket table through ``ss`` and
compares every listening socket against the exact protocol/port pairs the
reviewed baseline allows to answer on a public interface.

Parsing fails closed. A nonempty row that cannot be understood is reported
rather than skipped, because an unparsed row is indistinguishable from an
undeclared service.

An explicitly enabled exception recognizes ephemeral UDP sockets belonging to
the root-owned systemd Cloudflare Tunnel daemon. This is not a port allowlist:
the executable, process identity, descriptor and kernel UDP inode must agree.
TCP and fixed-port UDP listeners remain subject to the public allowlist.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import NamedTuple


LISTEN_RE = re.compile(
    r"^(?P<protocol>tcp|udp)\s+(?P<state>\S+)\s+\S+\s+\S+\s+"
    r"(?P<local>\S+)\s+(?P<peer>\S+)(?:\s+(?P<owners>.*))?$"
)
ALLOW_RE = re.compile(r"^(?P<protocol>tcp|udp)/(?P<port>[1-9][0-9]{0,4})$")
OWNER_RE = re.compile(r'users:\(\("[^"]+",pid=([1-9][0-9]*),fd=([0-9]+)\)\)')
PROC_ROOT = Path("/proc")
CLOUDFLARED_BINARY = Path("/usr/bin/cloudflared")
PORT_RANGE = Path("/proc/sys/net/ipv4/ip_local_port_range")
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


class SocketRow(NamedTuple):
    protocol: str
    address: str
    port: str
    state: str
    peer: str
    owners: str


class TunnelIdentity(NamedTuple):
    pid: int
    start_time: str
    executable_device: int
    executable_inode: int
    ephemeral_ports: tuple[int, int]


def bounded_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        text = handle.read(1024 * 1024 + 1)
    if len(text) > 1024 * 1024:
        raise ValueError("kernel metadata exceeds the inspection bound")
    return text


def root_protected(path: Path) -> bool:
    """Do not trust an executable/unit that an unprivileged user can replace."""
    resolved = path.resolve(strict=True)
    for entry in (resolved, *resolved.parents):
        metadata = entry.stat()
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            return False
    return stat.S_ISREG(resolved.stat().st_mode)


def process_start_time(pid: int) -> str:
    # comm may contain spaces and parentheses; the fields after its final ')'
    # begin at field 3. Field 22 prevents a recycled PID from inheriting trust.
    fields = bounded_text(PROC_ROOT / str(pid) / "stat").rpartition(")")[2].split()
    value = fields[19]
    if not value.isdecimal():
        raise ValueError("invalid process start time")
    return value


def tunnel_run_command(pid: int) -> bool:
    # Never log command-line contents: a remotely managed tunnel may carry its
    # token here. Only inspect the command shape, and reject DNS-server mode.
    with (PROC_ROOT / str(pid) / "cmdline").open("rb") as handle:
        command = handle.read(65537)
    if len(command) > 65536 or not command.endswith(b"\0"):
        return False
    arguments = command.rstrip(b"\0").split(b"\0")[1:]
    if any(argument.startswith(b"--proxy-dns") for argument in arguments):
        return False
    # The installed service uses 'tunnel --no-autoupdate run'; the documented
    # 'tunnel run' spelling is equivalent. Other subcommands receive no trust.
    for index, argument in enumerate(arguments):
        if argument == b"tunnel":
            remaining = arguments[index + 1:]
            if remaining[:1] == [b"--no-autoupdate"]:
                remaining = remaining[1:]
            return remaining[:1] == [b"run"]
    return False


def process_matches(identity: TunnelIdentity) -> bool:
    pid_path = PROC_ROOT / str(identity.pid)
    if process_start_time(identity.pid) != identity.start_time:
        return False
    executable = pid_path / "exe"
    if executable.resolve(strict=True) != CLOUDFLARED_BINARY.resolve(strict=True):
        return False
    metadata = executable.stat()
    if (metadata.st_dev, metadata.st_ino) != (
        identity.executable_device, identity.executable_inode,
    ):
        return False
    uid_lines = [line for line in bounded_text(pid_path / "status").splitlines() if line.startswith("Uid:")]
    return len(uid_lines) == 1 and uid_lines[0].split()[1:] == ["0"] * 4


def cloudflared_identity() -> TunnelIdentity | None:
    """Missing, inactive, unreadable or untrusted daemons confer no exception."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "cloudflared.service", "--property=ActiveState,MainPID,FragmentPath"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        properties = dict(line.split("=", 1) for line in result.stdout.splitlines())
        if properties.get("ActiveState") != "active":
            return None
        pid = int(properties["MainPID"])
        if pid <= 1 or not root_protected(Path(properties["FragmentPath"])):
            return None
        if not root_protected(CLOUDFLARED_BINARY) or not tunnel_run_command(pid):
            return None
        ports = tuple(int(value) for value in bounded_text(PORT_RANGE).split())
        if len(ports) != 2 or not 32768 <= ports[0] <= ports[1] <= 65535:
            return None
        metadata = CLOUDFLARED_BINARY.stat()
        identity = TunnelIdentity(pid, process_start_time(pid), metadata.st_dev, metadata.st_ino, ports)
        return identity if process_matches(identity) else None
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        return None


def cloudflared_client_socket(row: SocketRow, identity: TunnelIdentity | None) -> bool:
    if identity is None or row.protocol != "udp" or row.state != "UNCONN":
        return False
    if row.address not in {"*", "0.0.0.0", "::"} or not row.port.isdecimal():
        return False
    if row.peer not in {"*:*", "0.0.0.0:*", "[::]:*"}:
        return False
    if not identity.ephemeral_ports[0] <= int(row.port) <= identity.ephemeral_ports[1]:
        return False
    owner = OWNER_RE.fullmatch(row.owners)
    if owner is None or int(owner[1]) != identity.pid:
        return False
    try:
        if not process_matches(identity):
            return False
        target = os.readlink(PROC_ROOT / str(identity.pid) / "fd" / owner[2])
        inode_match = re.fullmatch(r"socket:\[([1-9][0-9]*)\]", target)
        if inode_match is None:
            return False
        for table in ("udp", "udp6"):
            for line in bounded_text(PROC_ROOT / str(identity.pid) / "net" / table).splitlines()[1:]:
                fields = line.split()
                if len(fields) < 10 or fields[9] != inode_match[1]:
                    continue
                address, port = fields[1].split(":")
                remote_address, remote_port = fields[2].split(":")
                if (
                    set(address) == {"0"} and int(port, 16) == int(row.port)
                    and fields[3] == "07" and fields[7] == "0"
                    and set(remote_address) == {"0"} and int(remote_port, 16) == 0
                ):
                    return process_matches(identity)
        return False
    except (OSError, ValueError, IndexError):
        return False


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


def parse_socket_table(output: str) -> tuple[list[SocketRow], list[str]]:
    """Return every listening socket plus every row that could not be parsed."""

    sockets: list[SocketRow] = []
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
        sockets.append(SocketRow(
            match.group("protocol"), local[0], local[1], match.group("state"),
            match.group("peer"), match.group("owners") or "",
        ))
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


def evaluate(
    output: str, allow_values: list[str], tunnel: TunnelIdentity | None = None,
) -> list[str]:
    allowed, invalid = parse_allowlist(allow_values)
    findings = [f"allowlist entry is not protocol/port: {value}" for value in invalid]
    if not allowed and not invalid:
        findings.append("no public protocol/port pair was declared")

    sockets, unparsed = parse_socket_table(output)
    findings.extend(f"socket table row could not be parsed: {row}" for row in unparsed)
    for row in sockets:
        protocol, address, port = row.protocol, row.address, row.port
        if not is_public_binding(address):
            continue
        if (protocol, port) not in allowed and not cloudflared_client_socket(row, tunnel):
            findings.append(f"{protocol}/{port} listens on a public address {address or '*'}")
    return sorted(set(findings))


def listening_socket_table() -> str:
    completed = subprocess.run(
        ["ss", "--no-header", "--listening", "--numeric", "--tcp", "--udp", "--processes"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-cloudflared-quic",
        action="store_true",
        help="recognize ephemeral UDP client sockets of the trusted systemd tunnel daemon",
    )
    parser.add_argument(
        "--allow-public",
        action="append",
        default=[],
        help="protocol/port pair permitted on a public address, such as tcp/22; repeatable",
    )
    arguments = parser.parse_args()

    output = listening_socket_table()
    tunnel = cloudflared_identity() if arguments.allow_cloudflared_quic else None
    findings = evaluate(output, arguments.allow_public, tunnel)
    if findings:
        for finding in findings:
            print(f"public listener failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print(f"public_listeners_allowed={','.join(sorted(arguments.allow_public))}")


if __name__ == "__main__":
    main()
