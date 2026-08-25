"""Coverage for the disposable harness's host network evidence filter.

WP05A-18: the attached real-host evidence never named an interface, so the
`-i <interface> -j DROP` ingress rule was never shown to match a real NIC. The
filter records the link list, the default route and the ingress chain together
and derives the verdict from what it recorded, while keeping every address and
hardware address out of `.artifacts/`. Fixtures below are shaped like real
Ubuntu 24.04 `ip -o link`, `ip route show default` and `iptables -S` output.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/tests/disposable/redact_network_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_network_evidence", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The module defines a dataclass, which resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EVIDENCE = load_module()

LINKS = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT \
group default qlen 1000\\    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0@if42: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT \
group default \\    link/ether 02:42:ac:1c:0b:02 brd ff:ff:ff:ff:ff:ff link-netnsid 0"""

ROUTE = """default via 172.28.11.1 dev eth0 proto kernel scope global metric 100
default via fe80::1 dev eth0 proto ra metric 1024 pref medium"""

CHAIN = """-N DHOLBEAT-DOCKER-INGRESS
-A DHOLBEAT-DOCKER-INGRESS -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A DHOLBEAT-DOCKER-INGRESS -s 10.99.0.0/24 -i eth0 -j ACCEPT
-A DHOLBEAT-DOCKER-INGRESS -i eth0 -j DROP
-A DHOLBEAT-DOCKER-INGRESS -j RETURN"""

HOST_LITERALS = (
    "172.28.11.1",
    "fe80::1",
    "10.99.0.0",
    "02:42:ac:1c:0b:02",
    "ff:ff:ff:ff:ff:ff",
    "00:00:00:00:00:00",
)


def transcript(links: str = LINKS, route: str = ROUTE, chain: str = CHAIN) -> str:
    return (
        f"## links status=ok\n{links}\n"
        f"## default-route status=ok\n{route}\n"
        f"## docker-ingress-chain status=ok\n{chain}\n"
    )


def verdict(document: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in document.splitlines():
        if line.startswith("## verdict"):
            fields["__reached__"] = "true"
        if ": " in line and not line.startswith("## "):
            key, _, value = line.partition(": ")
            fields[key] = value
    return fields


def render(**parts: str) -> str:
    return EVIDENCE.render(transcript(**parts))


def test_a_converged_host_proves_the_drop_rule_names_the_default_route_nic() -> None:
    fields = verdict(render())
    assert fields["host_interfaces"] == "lo,eth0"
    assert fields["default_route_interfaces"] == "eth0"
    assert fields["docker_ingress_drop_interfaces"] == "eth0"
    assert fields["drop_interfaces_exist_on_host"] == "true"
    assert fields["default_route_interfaces_dropped"] == "true"
    assert fields["redaction_residue"] == "0"
    assert fields["evidence_complete"] == "true"


@pytest.mark.parametrize("literal", HOST_LITERALS)
def test_no_host_address_survives_into_the_evidence(literal: str) -> None:
    assert literal not in render()


def test_interface_names_route_structure_and_rule_shape_survive() -> None:
    document = render()
    assert "eth0@if42" in document
    assert "mtu 1500" in document
    assert "default via <IP> dev eth0 proto kernel scope global metric 100" in document
    assert "-A DHOLBEAT-DOCKER-INGRESS -i eth0 -j DROP" in document
    assert "-A DHOLBEAT-DOCKER-INGRESS -s <IP>/24 -i eth0 -j ACCEPT" in document
    assert "link/ether <MAC> brd <MAC>" in document


def test_a_drop_rule_naming_an_absent_nic_is_rejected() -> None:
    fields = verdict(render(chain=CHAIN.replace("-i eth0 -j DROP", "-i ens3 -j DROP")))
    assert fields["docker_ingress_drop_interfaces"] == "ens3"
    assert fields["drop_interfaces_exist_on_host"] == "false"
    assert fields["default_route_interfaces_dropped"] == "false"
    assert fields["evidence_complete"] == "false"


def test_a_drop_rule_on_the_wrong_present_nic_is_rejected() -> None:
    links = LINKS + "\n3: ens3: <BROADCAST,MULTICAST,UP> mtu 1500 qdisc fq_codel state UP"
    fields = verdict(
        render(links=links, chain=CHAIN.replace("-i eth0 -j DROP", "-i ens3 -j DROP"))
    )
    assert fields["host_interfaces"] == "lo,eth0,ens3"
    assert fields["drop_interfaces_exist_on_host"] == "true"
    assert fields["default_route_interfaces_dropped"] == "false"
    assert fields["evidence_complete"] == "false"


def test_an_interface_agnostic_drop_rule_covers_the_default_route() -> None:
    fields = verdict(render(chain=CHAIN.replace(" -i eth0 -j DROP", " -j DROP")))
    assert fields["docker_ingress_drop_interfaces"] == "any"
    assert fields["drop_interfaces_exist_on_host"] == "true"
    assert fields["default_route_interfaces_dropped"] == "true"
    assert fields["evidence_complete"] == "true"


def test_a_negated_interface_match_never_counts_as_covering_it() -> None:
    fields = verdict(render(chain=CHAIN.replace("-i eth0 -j DROP", "! -i eth0 -j DROP")))
    assert fields["docker_ingress_drop_interfaces"] == "not:eth0"
    # The rule does name a real NIC; it just drops everything except that NIC.
    assert fields["drop_interfaces_exist_on_host"] == "true"
    assert fields["default_route_interfaces_dropped"] == "false"
    assert fields["evidence_complete"] == "false"


def test_a_host_with_no_default_route_cannot_prove_the_match() -> None:
    fields = verdict(render(route=""))
    assert fields["default_route_interfaces"] == "unavailable"
    assert fields["default_route_interfaces_dropped"] == "false"
    assert fields["evidence_complete"] == "false"


def test_a_missing_command_is_recorded_rather_than_left_empty() -> None:
    document = EVIDENCE.render(
        "## links status=unavailable reason=command-not-found:ip\n"
        "## default-route status=unavailable reason=command-not-found:ip\n"
        f"## docker-ingress-chain status=ok\n{CHAIN}\n"
    )
    fields = verdict(document)
    assert "## links status=unavailable reason=command-not-found:ip" in document
    assert fields["host_interfaces"] == "unavailable"
    assert fields["default_route_interfaces"] == "unavailable"
    assert fields["evidence_complete"] == "false"


def test_an_absent_ingress_chain_is_recorded_rather_than_left_empty() -> None:
    document = EVIDENCE.render(
        f"## links status=ok\n{LINKS}\n"
        f"## default-route status=ok\n{ROUTE}\n"
        "## docker-ingress-chain status=absent reason=command-failed:iptables\n"
    )
    fields = verdict(document)
    assert "## docker-ingress-chain status=absent reason=command-failed:iptables" in document
    assert fields["docker_ingress_drop_interfaces"] == "unavailable"
    assert fields["evidence_complete"] == "false"


def test_a_section_the_collector_never_emitted_is_reported_missing() -> None:
    document = EVIDENCE.render(f"## links status=ok\n{LINKS}\n")
    assert "## default-route status=missing" in document
    assert "finding: missing-section:default-route" in document
    assert "finding: missing-section:docker-ingress-chain" in document
    assert verdict(document)["evidence_complete"] == "false"


def test_a_duplicated_or_unknown_section_is_reported() -> None:
    document = EVIDENCE.render(transcript() + "## links status=ok\n## nftables status=ok\n")
    assert "finding: duplicate-section:links" in document
    assert "finding: unexpected-section:nftables" in document
    assert verdict(document)["evidence_complete"] == "false"


def test_an_address_shape_the_redactors_miss_is_withheld_not_emitted() -> None:
    document = EVIDENCE.render(
        transcript(route="default via 1.2.3.4.5 dev eth0 metric 100")
    )
    assert "1.2.3.4" not in document
    assert EVIDENCE.WITHHELD in document
    fields = verdict(document)
    assert fields["redaction_residue"] == "1"
    assert fields["evidence_complete"] == "false"


def test_output_before_any_section_is_reported_rather_than_kept() -> None:
    document = EVIDENCE.render("sh: unexpected preamble\n" + transcript())
    assert "unexpected preamble" not in document
    assert "finding: output-before-first-section" in document


@pytest.mark.parametrize(
    ("captured", "expected"),
    [
        ("inet 203.0.113.7/24 brd 203.0.113.255", "inet <IP>/24 brd <IP>"),
        ("inet6 2001:db8::5/64 scope global", "inet6 <IP>/64 scope global"),
        ("inet6 ::1/128 scope host", "inet6 <IP>/128 scope host"),
        ("link/ether 02:42:ac:1c:0b:02 brd ff:ff:ff:ff:ff:ff", "link/ether <MAC> brd <MAC>"),
        ("mtu 1500 qdisc noqueue state UP qlen 1000", "mtu 1500 qdisc noqueue state UP qlen 1000"),
        (
            "-A DHOLBEAT-DOCKER-INGRESS -i eth0.100 -j DROP",
            "-A DHOLBEAT-DOCKER-INGRESS -i eth0.100 -j DROP",
        ),
    ],
)
def test_redaction_removes_addresses_and_keeps_structure(captured: str, expected: str) -> None:
    assert EVIDENCE.redact(captured) == expected
