#!/usr/bin/env python3
"""Redact captured host network evidence and judge the Docker ingress DROP rule.

The Docker ingress policy drops public ingress with `-i <interface> -j DROP`.
Evidence that never names an interface cannot tell a correct convergence from
one whose DROP rule points at a NIC the host does not have, so this filter
records the link list, the default route and the ingress chain together and
derives the verdict from what it recorded.

Interface names, route structure and iptables rule shape are evidence and are
kept. IPv4/IPv6 addresses and hardware addresses identify the host and are
replaced before the text reaches `.artifacts/`. A line that still looks
address-shaped after redaction is withheld rather than emitted.

Input is the collector transcript on stdin: one `## <key> status=<status>
[reason=<reason>]` header per section, followed by that command's output.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import re
import sys

SCHEMA_VERSION = 1
LINKS = "links"
DEFAULT_ROUTE = "default-route"
INGRESS_CHAIN = "docker-ingress-chain"
REQUIRED_SECTIONS = (LINKS, DEFAULT_ROUTE, INGRESS_CHAIN)
WITHHELD = "<withheld: redaction residue>"
ANY_INTERFACE = "any"

HEADER = re.compile(r"^##\s+(\S+)\s+status=(\S+)(?:\s+reason=(\S+))?\s*$")
# link/ether, link/infiniband and friends: six or more colon-separated octets.
MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5,}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
# Any hextet run holding at least two colons, which covers `::1` and `fe80::a`.
IPV6 = re.compile(r"(?<![0-9A-Za-z:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z.:])")
IPV4 = re.compile(r"(?<![0-9A-Za-z.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Za-z.])")
# Deliberately looser than the redactors, so a shape they miss is still caught.
RESIDUE = re.compile(r"\d+\.\d+\.\d+|[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:")

LINK_NAME = re.compile(r"^\d+:\s+([^\s:@]+)(?:@[^\s:]+)?:")
ROUTE_DEVICE = re.compile(r"(?:^|\s)dev\s+(\S+)")


@dataclass
class Section:
    """One collected command: its outcome and its already-redacted output."""

    status: str
    reason: str = ""
    lines: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def redact(text: str) -> str:
    """Replace hardware and network addresses, keeping every other token."""
    text = MAC.sub("<MAC>", text)
    text = IPV6.sub("<IP>", text)
    return IPV4.sub("<IP>", text)


def has_residue(line: str) -> bool:
    """Report whether a redacted line still carries an address-shaped token."""
    return bool(RESIDUE.search(line))


def sanitize(line: str) -> str:
    """Redact one line, withholding it entirely if anything address-shaped survives."""
    redacted = redact(line)
    return WITHHELD if has_residue(redacted) else redacted


def parse(text: str) -> tuple[dict[str, Section], list[str]]:
    """Split the collector transcript into redacted sections plus any findings."""
    sections: dict[str, Section] = {}
    findings: list[str] = []
    current: Section | None = None
    for raw in text.splitlines():
        header = HEADER.match(raw)
        if header:
            key, status, reason = header.group(1), header.group(2), header.group(3) or ""
            if key in sections:
                findings.append(f"duplicate-section:{key}")
            if key not in REQUIRED_SECTIONS:
                findings.append(f"unexpected-section:{key}")
            current = Section(status=status, reason=reason)
            sections[key] = current
            continue
        if current is None:
            if raw.strip():
                findings.append("output-before-first-section")
            continue
        current.lines.append(sanitize(raw))
    for key in REQUIRED_SECTIONS:
        if key not in sections:
            findings.append(f"missing-section:{key}")
    return sections, findings


def link_names(section: Section) -> list[str]:
    """Interface names from `ip -o link`, in the order the kernel listed them."""
    names: list[str] = []
    for line in section.lines:
        match = LINK_NAME.match(line.strip())
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def default_route_interfaces(section: Section) -> list[str]:
    """Interfaces carrying a default route, in the order the kernel listed them."""
    names: list[str] = []
    for line in section.lines:
        stripped = line.strip()
        if not stripped.startswith("default"):
            continue
        match = ROUTE_DEVICE.search(stripped)
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def drop_interfaces(section: Section) -> list[str]:
    """Inbound interfaces the chain drops.

    A `-j DROP` rule with no `-i` drops on every interface and is reported as
    `any`. A negated `! -i X` rule drops everything except X, so it is reported
    as `not:X` and never counts as covering an interface.
    """
    names: list[str] = []
    for line in section.lines:
        tokens = line.split()
        if len(tokens) < 2 or tokens[0] != "-A":
            continue
        if "-j" not in tokens:
            continue
        target_index = tokens.index("-j") + 1
        if target_index >= len(tokens) or tokens[target_index] != "DROP":
            continue
        name = ANY_INTERFACE
        for index, token in enumerate(tokens):
            if token in ("-i", "--in-interface") and index + 1 < len(tokens):
                name = tokens[index + 1]
                if index > 0 and tokens[index - 1] == "!":
                    name = f"not:{name}"
                break
        if name not in names:
            names.append(name)
    return names


def join(names: list[str], empty: str) -> str:
    return ",".join(names) if names else empty


def render(text: str) -> str:
    """Return the complete redacted evidence document, verdict included."""
    sections, findings = parse(text)
    residue = sum(line == WITHHELD for section in sections.values() for line in section.lines)

    links = sections.get(LINKS)
    routes = sections.get(DEFAULT_ROUTE)
    chain = sections.get(INGRESS_CHAIN)
    hosts = link_names(links) if links and links.ok else []
    defaults = default_route_interfaces(routes) if routes and routes.ok else []
    drops = drop_interfaces(chain) if chain and chain.ok else []

    covering = {name for name in drops if not name.startswith("not:")}
    # Existence asks only whether every interface a DROP rule names is real, so a
    # negated match is checked too; whether it covers anything is the next field.
    exist = bool(drops) and all(
        name == ANY_INTERFACE or name.removeprefix("not:") in hosts for name in drops
    )
    covered = bool(defaults) and all(
        name in covering or ANY_INTERFACE in covering for name in defaults
    )
    complete = (
        not findings
        and residue == 0
        and all(section.ok for section in sections.values())
        and bool(hosts)
        and exist
        and covered
    )

    body: list[str] = [f"schema_version: {SCHEMA_VERSION}"]
    for key in REQUIRED_SECTIONS:
        section = sections.get(key)
        body.append("")
        if section is None:
            body.append(f"## {key} status=missing")
            continue
        header = f"## {key} status={section.status}"
        if section.reason:
            header = f"{header} reason={redact(section.reason)}"
        body.append(header)
        body.extend(section.lines)
    body.append("")
    body.append("## verdict")
    body.append(f"host_interfaces: {join(hosts, 'unavailable')}")
    body.append(f"default_route_interfaces: {join(defaults, 'unavailable')}")
    body.append(f"docker_ingress_drop_interfaces: {join(drops, 'unavailable')}")
    body.append(f"drop_interfaces_exist_on_host: {str(exist).lower()}")
    body.append(f"default_route_interfaces_dropped: {str(covered).lower()}")
    body.append(f"redaction_residue: {residue}")
    for finding in findings:
        body.append(f"finding: {finding}")
    body.append(f"evidence_complete: {str(complete).lower()}")
    return "\n".join(body) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    captured = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    sys.stdout.write(render(captured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
