#!/usr/bin/env python3
"""Verify the WireGuard interface against its declared contract, on the host.

Security note, verified against real `wg` output on Ubuntu 24.04: the first
field of the first line of `wg show <interface> dump` is the **server private
key**, and `wg showconf` prints it too. This script therefore runs on the host
and discards that field before anything else, so the key never reaches the
controller, an Ansible transcript, or `.artifacts/` evidence. It prints only
non-secret facts.

Captured interface line:  <private-key> <public-key> <listen-port> <fwmark>
Captured peer line:       <public-key> <preshared-key> <endpoint> <allowed-ips>
                          <latest-handshake> <rx> <tx> <persistent-keepalive>
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys


WG_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42}[A-Za-z0-9+/=]{2}$")
REDACTED = "<redacted>"


def parse_dump(text: str) -> tuple[dict, list[dict], list[str]]:
    """Parse `wg show <interface> dump`, discarding the private key immediately."""

    findings: list[str] = []
    interface: dict = {}
    peers: list[dict] = []
    rows = [line for line in (text or "").splitlines() if line.strip()]
    if not rows:
        return interface, peers, ["the WireGuard interface reported no state"]

    header = rows[0].split("\t")
    if len(header) < 4:
        return interface, peers, ["the WireGuard interface line could not be parsed"]
    # header[0] is the private key. It is never read, stored, or printed.
    interface = {"public_key": header[1], "listen_port": header[2], "fwmark": header[3]}

    for index, row in enumerate(rows[1:], start=1):
        fields = row.split("\t")
        if len(fields) < 4:
            findings.append(f"WireGuard peer row {index} could not be parsed")
            continue
        peers.append(
            {
                "public_key": fields[0],
                "allowed_ips": [item for item in fields[3].split(",") if item and item != "(none)"],
                "keepalive": fields[7] if len(fields) > 7 else "off",
            }
        )
    return interface, peers, findings


def parse_declared_peers(values: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    declared: dict[str, list[str]] = {}
    findings: list[str] = []
    for value in values:
        # A WireGuard key itself ends in '=', so the separator is '|'.
        public_key, separator, allowed = value.partition("|")
        if not separator:
            findings.append(f"declared peer is not <public-key>|<allowed-ips>: {value}")
            continue
        if WG_KEY_RE.match(public_key) is None:
            findings.append("a declared peer public key is not a valid WireGuard key")
            continue
        declared[public_key] = sorted(item for item in allowed.split(",") if item)
    return declared, findings


def validate(
    interface: dict,
    peers: list[dict],
    declared_peers: dict[str, list[str]],
    listen_port: int,
    subnet: str,
    host_address: str,
    interface_addresses: list[str],
) -> list[str]:
    findings: list[str] = []

    if str(interface.get("listen_port")) != str(listen_port):
        findings.append(
            f"WireGuard listen port is {interface.get('listen_port')}, declared {listen_port}"
        )
    if WG_KEY_RE.match(interface.get("public_key", "")) is None:
        findings.append("the WireGuard interface has no valid public key")

    try:
        network = ipaddress.ip_network(subnet, strict=True)
    except ValueError:
        return [*findings, f"the declared VPN subnet is invalid: {subnet}"]

    if host_address not in interface_addresses:
        findings.append("the WireGuard interface does not carry the declared host address")
    for address in interface_addresses:
        try:
            parsed = ipaddress.ip_interface(address)
        except ValueError:
            findings.append(f"the WireGuard interface carries an unparseable address: {address}")
            continue
        if parsed.ip not in network:
            findings.append("the WireGuard interface carries an address outside the declared subnet")

    actual = {peer["public_key"]: sorted(peer["allowed_ips"]) for peer in peers}
    for undeclared in sorted(set(actual) - set(declared_peers)):
        findings.append(f"an undeclared WireGuard peer is configured: {undeclared[:8]}…")
    for missing in sorted(set(declared_peers) - set(actual)):
        findings.append(f"a declared WireGuard peer is absent: {missing[:8]}…")
    for public_key in sorted(set(actual) & set(declared_peers)):
        if actual[public_key] != declared_peers[public_key]:
            findings.append(
                f"WireGuard peer {public_key[:8]}… has allowed IPs outside its declaration"
            )
        for allowed in actual[public_key]:
            try:
                parsed = ipaddress.ip_network(allowed, strict=False)
            except ValueError:
                findings.append(f"WireGuard peer {public_key[:8]}… has an unparseable allowed IP")
                continue
            if parsed.prefixlen not in {32, 128}:
                findings.append(
                    f"WireGuard peer {public_key[:8]}… is allowed a range, not a single address"
                )
            if parsed.network_address not in network:
                findings.append(
                    f"WireGuard peer {public_key[:8]}… is allowed an IP outside the VPN subnet"
                )
    return sorted(set(findings))


def read_command(argv: list[str]) -> str:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return ""
    return completed.stdout


def interface_addresses(interface_name: str) -> list[str]:
    output = read_command(["ip", "-o", "-4", "address", "show", "dev", interface_name])
    addresses: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if "inet" in fields:
            addresses.append(fields[fields.index("inet") + 1])
    return addresses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--subnet", required=True)
    parser.add_argument("--host-address", required=True)
    parser.add_argument("--peer", action="append", default=[])
    arguments = parser.parse_args()

    dump = read_command(["wg", "show", arguments.interface, "dump"])
    if not dump:
        print(
            f"wireguard failure: interface {arguments.interface} reported no state",
            file=sys.stderr,
        )
        raise SystemExit(1)

    interface, peers, findings = parse_dump(dump)
    declared, declaration_findings = parse_declared_peers(arguments.peer)
    findings.extend(declaration_findings)
    findings.extend(
        validate(
            interface,
            peers,
            declared,
            arguments.listen_port,
            arguments.subnet,
            arguments.host_address,
            interface_addresses(arguments.interface),
        )
    )

    if findings:
        for finding in sorted(set(findings)):
            print(f"wireguard failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"wireguard_interface={arguments.interface} "
        f"listen_port={arguments.listen_port} peers={len(peers)} private_key={REDACTED}"
    )


if __name__ == "__main__":
    main()
