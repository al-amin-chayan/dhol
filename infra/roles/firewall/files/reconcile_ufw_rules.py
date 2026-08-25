#!/usr/bin/env python3
"""Reconcile the firewall rules this repository owns, rather than only adding them.

`ufw allow` is additive. Converging a narrower contract therefore leaves the
previous rule in place, so a host moving from a public SSH allowlist to a VPN
subnet would keep both paths open. This computes which owned rules are obsolete
so they can be removed, and reports any desired rule that is missing.

Parsed from real `ufw status numbered` output on Ubuntu 24.04:

    [ 1] 22/tcp            ALLOW IN    203.0.113.0/24    # dholbeat-admin-ssh
    [ 3] 51820/udp         ALLOW IN    Anywhere          # dholbeat-wireguard
    [ 5] 51820/udp (v6)    ALLOW IN    Anywhere (v6)     # dholbeat-wireguard

ufw creates the (v6) twin of an "Anywhere" rule by itself, so both normalize to
the same desired tuple and neither is treated as obsolete.
"""

from __future__ import annotations

import argparse
import re
import sys


RULE_RE = re.compile(
    r"^\[\s*(?P<index>\d+)\]\s+(?P<to>.+?)\s+ALLOW IN\s+(?P<source>.+?)"
    r"(?:\s+#\s*(?P<comment>.*))?$"
)


def normalize(value: str) -> str:
    return re.sub(r"\s*\(v6\)\s*$", "", value.strip())


def parse_rules(text: str) -> tuple[list[dict], list[str]]:
    rules: list[dict] = []
    findings: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        if not line.lstrip().startswith("["):
            continue
        match = RULE_RE.match(line.strip())
        if match is None:
            findings.append(f"a numbered firewall rule could not be parsed: {line.strip()}")
            continue
        rules.append(
            {
                "index": int(match.group("index")),
                "to": normalize(match.group("to")),
                "source": normalize(match.group("source")),
                "comment": (match.group("comment") or "").strip(),
            }
        )
    return rules, findings


def desired_tuples(values: list[str]) -> tuple[set[tuple[str, str, str]], list[str]]:
    desired: set[tuple[str, str, str]] = set()
    findings: list[str] = []
    for value in values:
        parts = value.split("|")
        if len(parts) != 3:
            findings.append(f"desired rule is not <to>|<source>|<comment>: {value}")
            continue
        desired.add((normalize(parts[0]), normalize(parts[1]), parts[2].strip()))
    return desired, findings


def reconcile(
    text: str, owned_comments: set[str], desired: set[tuple[str, str, str]]
) -> tuple[list[int], list[str], list[str]]:
    rules, findings = parse_rules(text)
    obsolete: list[int] = []
    present: set[tuple[str, str, str]] = set()
    for rule in rules:
        if rule["comment"] not in owned_comments:
            continue
        key = (rule["to"], rule["source"], rule["comment"])
        if key in desired:
            present.add(key)
        else:
            obsolete.append(rule["index"])
    missing = [
        f"a desired firewall rule is absent: {to} from {source} ({comment})"
        for to, source, comment in sorted(desired - present)
    ]
    # Descending, so removing one rule cannot renumber the next.
    return sorted(obsolete, reverse=True), missing, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owned-comment", action="append", default=[])
    parser.add_argument("--desired", action="append", default=[])
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail when a desired rule is absent, used for the closure assertion",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help=(
            "print the planned add and delete set without asserting closure. Check mode "
            "deliberately does not apply the rules, so the plan describes the delta instead "
            "of failing on state it did not create."
        ),
    )
    arguments = parser.parse_args()

    desired, desired_findings = desired_tuples(arguments.desired)
    obsolete, missing, findings = reconcile(
        sys.stdin.read(), set(arguments.owned_comment), desired
    )
    if arguments.report:
        for problem in sorted(set(desired_findings + findings)):
            print(f"firewall reconciliation failure: {problem}", file=sys.stderr)
        if desired_findings or findings:
            raise SystemExit(1)
        for entry in missing:
            print(f"planned add: {entry.split(': ', 1)[1]}")
        for index in obsolete:
            print(f"planned delete: rule {index}")
        if not missing and not obsolete:
            print("planned change: none")
        return
    problems = desired_findings + findings + (missing if arguments.require_complete else [])
    if problems:
        for problem in sorted(set(problems)):
            print(f"firewall reconciliation failure: {problem}", file=sys.stderr)
        raise SystemExit(1)
    for index in obsolete:
        print(index)


if __name__ == "__main__":
    main()
