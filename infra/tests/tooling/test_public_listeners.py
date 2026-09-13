"""Coverage for the read-only public-listener probe used by infra/playbooks/verify.yml."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/playbooks/files/verify_public_listeners.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_public_listeners", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LISTENERS = load_module()


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "10.4.0.7", "172.18.0.1", "192.168.1.5"])
def test_loopback_and_private_bindings_are_not_public(address: str) -> None:
    assert LISTENERS.is_public_binding(address) is False


@pytest.mark.parametrize("address", ["0.0.0.0", "*", "203.0.113.9", "2001:db8::1", ""])
def test_unspecified_and_routable_bindings_are_public(address: str) -> None:
    assert LISTENERS.is_public_binding(address) is True


def test_an_unparseable_address_is_treated_as_public() -> None:
    assert LISTENERS.is_public_binding("%eth0") is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.0.0.0:22", ("0.0.0.0", "22")),
        ("[::]:22", ("::", "22")),
        ("[2001:db8::1]:5432", ("2001:db8::1", "5432")),
        ("*:5432", ("*", "5432")),
    ],
)
def test_local_socket_addresses_split_correctly(value: str, expected: tuple[str, str]) -> None:
    assert LISTENERS.split_local(value) == expected


def test_a_malformed_socket_address_is_skipped() -> None:
    assert LISTENERS.split_local("nonsense") is None


SS_SAMPLE = """
tcp   LISTEN 0      4096       127.0.0.1:5432      0.0.0.0:*
tcp   LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
udp   UNCONN 0      0          127.0.0.53:53       0.0.0.0:*
"""


def test_a_declared_public_tcp_port_passes() -> None:
    assert LISTENERS.evaluate(SS_SAMPLE, ["tcp/22"]) == []


def test_an_undeclared_public_tcp_port_is_reported() -> None:
    sample = SS_SAMPLE + "tcp   LISTEN 0 4096 0.0.0.0:8080 0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("tcp/8080 listens on a public address" in finding for finding in findings)


def test_the_same_port_on_another_protocol_is_not_covered() -> None:
    sample = SS_SAMPLE + "udp   UNCONN 0 0 0.0.0.0:22 0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("udp/22 listens on a public address" in finding for finding in findings)


def test_an_unparseable_row_fails_closed_instead_of_being_skipped() -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE + "wat is this row\n", ["tcp/22"])
    assert any("could not be parsed" in finding for finding in findings)


def test_a_malformed_local_address_fails_closed() -> None:
    sample = "tcp   LISTEN 0      4096       nonsense      0.0.0.0:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("could not be parsed" in finding for finding in findings)


def test_blank_rows_are_not_treated_as_unparseable() -> None:
    assert LISTENERS.evaluate("\n\n" + SS_SAMPLE + "\n   \n", ["tcp/22"]) == []


@pytest.mark.parametrize("entry", ["22", "tcp:22", "tcp/", "sctp/22", "tcp/0"])
def test_an_allowlist_entry_that_is_not_protocol_slash_port_is_rejected(entry: str) -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE, [entry])
    assert any("not protocol/port" in finding for finding in findings)


def test_an_empty_allowlist_is_rejected() -> None:
    findings = LISTENERS.evaluate(SS_SAMPLE, [])
    assert any("no public protocol/port pair was declared" in finding for finding in findings)


def test_private_and_loopback_listeners_never_need_declaring() -> None:
    sample = (
        "tcp   LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:*\n"
        "tcp   LISTEN 0 4096 10.4.0.7:6379 0.0.0.0:*\n"
        "tcp   LISTEN 0 4096 [::1]:9090 [::]:*\n"
        "tcp   LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n"
    )
    assert LISTENERS.evaluate(sample, ["tcp/22"]) == []


def test_a_public_ipv6_listener_is_reported() -> None:
    sample = "tcp   LISTEN 0 4096 [2001:db8::1]:8443 [::]:*\n"
    findings = LISTENERS.evaluate(sample, ["tcp/22"])
    assert any("tcp/8443 listens on a public address" in finding for finding in findings)


CLIENT = 'udp UNCONN 0 0 *:44858 *:* users:(("cloudflared",pid=468,fd=7))\n'


@pytest.fixture
def tunnel(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    pid = proc / "468"
    (pid / "fd").mkdir(parents=True)
    (pid / "net").mkdir()
    binary = tmp_path / "cloudflared"
    binary.write_text("fixture executable")
    (pid / "exe").symlink_to(binary)
    (pid / "status").write_text("Name:\tcloudflared\nUid:\t0\t0\t0\t0\n")
    (pid / "stat").write_text("468 (cloudflared) " + " ".join(["S"] + ["0"] * 18 + ["12345"]))
    (pid / "cmdline").write_bytes(b"cloudflared\0tunnel\0--no-autoupdate\0run\0--token\0sensitive-value\0")
    (pid / "fd" / "7").symlink_to("socket:[9001]")
    header = "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
    (pid / "net" / "udp").write_text(header)
    (pid / "net" / "udp6").write_text(
        header + "0: " + "0" * 32 + ":AF3A " + "0" * 32 + ":0000 07 0:0 0:0 0 0 0 9001\n"
    )
    ports = tmp_path / "port-range"
    ports.write_text("32768 60999\n")
    unit = tmp_path / "cloudflared.service"
    unit.write_text("fixture unit")
    monkeypatch.setattr(LISTENERS, "PROC_ROOT", proc)
    monkeypatch.setattr(LISTENERS, "CLOUDFLARED_BINARY", binary)
    monkeypatch.setattr(LISTENERS, "PORT_RANGE", ports)
    # Fixtures run as the laptop user. Root-path checks are separately tested.
    monkeypatch.setattr(LISTENERS, "root_protected", lambda path: True)
    monkeypatch.setattr(
        LISTENERS.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"ActiveState=active\nMainPID=468\nFragmentPath={unit}\n"
        ),
    )
    identity = LISTENERS.cloudflared_identity()
    assert identity is not None
    return SimpleNamespace(identity=identity, proc=proc, pid=pid, ports=ports, binary=binary, unit=unit)


def test_trusted_systemd_tunnel_ephemeral_udp_client_passes(tunnel) -> None:
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"], tunnel.identity) == []


def test_exception_is_opt_in_even_for_real_tunnel_socket(tunnel) -> None:
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"])


@pytest.mark.parametrize("address", ["*", "0.0.0.0", "[::]"])
def test_wildcard_client_spellings_pass(tunnel, address) -> None:
    assert LISTENERS.evaluate(CLIENT.replace("*:44858", f"{address}:44858"), ["tcp/22"], tunnel.identity) == []


@pytest.mark.parametrize("port", ["53", "7844", "1023", "32767", "61000", "65536", "nonsense"])
def test_fixed_or_non_ephemeral_udp_ports_never_receive_exception(tunnel, port) -> None:
    assert LISTENERS.evaluate(CLIENT.replace("44858", port), ["tcp/22"], tunnel.identity)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.replace("pid=468", "pid=469"),
        lambda value: value.replace("fd=7", "fd=8"),
        lambda value: value.replace(' users:(("cloudflared",pid=468,fd=7))', ""),
        lambda value: value.replace('pid=468,fd=7))', 'pid=468,fd=7),("other",pid=469,fd=8))'),
        lambda value: value.replace("udp UNCONN", "tcp LISTEN"),
        lambda value: value.replace("udp UNCONN", "udp ESTAB"),
        lambda value: value.replace("*:44858", "203.0.113.9:44858"),
        lambda value: value.replace("*:* users:", "198.51.100.1:7844 users:"),
        lambda value: value.replace("users:", "garbage-users:"),
        lambda value: value.rstrip() + " trailing-garbage\n",
    ],
)
def test_untrusted_or_non_client_socket_never_receives_exception(tunnel, change) -> None:
    assert LISTENERS.evaluate(change(CLIENT), ["tcp/22"], tunnel.identity)


def test_same_port_untrusted_socket_does_not_inherit_exception(tunnel) -> None:
    other = CLIENT.replace("pid=468", "pid=469")
    assert LISTENERS.evaluate(CLIENT + other, ["tcp/22"], tunnel.identity)


@pytest.mark.parametrize("table_change", ["inode", "port", "uid", "state", "address"])
def test_descriptor_must_match_a_root_owned_unconnected_wildcard_udp_inode(tunnel, table_change) -> None:
    table = tunnel.pid / "net" / "udp6"
    text = table.read_text()
    replacements = {
        "inode": ("9001", "9002"), "port": ("AF3A", "AF3B"),
        "uid": ("0 0 0 9001", "0 501 0 9001"), "state": (" 07 ", " 01 "),
        "address": ("0" * 32 + ":AF3A", "0" * 31 + "1:AF3A"),
    }
    before, after = replacements[table_change]
    table.write_text(text.replace(before, after))
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"], tunnel.identity)


@pytest.mark.parametrize("change", ["recycled-pid", "non-root", "other-executable", "deleted-fd", "not-a-socket"])
def test_process_or_descriptor_drift_fails_closed(tunnel, change) -> None:
    if change == "recycled-pid":
        path = tunnel.pid / "stat"
        path.write_text(path.read_text().replace("12345", "12346"))
    elif change == "non-root":
        (tunnel.pid / "status").write_text("Uid:\t501\t501\t501\t501\n")
    elif change == "other-executable":
        (tunnel.pid / "exe").unlink()
        (tunnel.pid / "exe").symlink_to(tunnel.unit)
    else:
        (tunnel.pid / "fd" / "7").unlink()
        if change == "not-a-socket":
            (tunnel.pid / "fd" / "7").symlink_to(tunnel.binary)
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"], tunnel.identity)


def test_executable_replacement_invalidates_inode_identity(tunnel) -> None:
    replacement = tunnel.binary.with_name("replacement")
    replacement.write_text("replacement executable")
    os.replace(replacement, tunnel.binary)
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"], tunnel.identity)


@pytest.mark.parametrize("ports", ["", "32768", "32768 60999 65535", "0 65535", "1024 65535", "60999 32768", "1 65536", "invalid"])
def test_invalid_kernel_ephemeral_range_confers_no_exception(tunnel, ports) -> None:
    tunnel.ports.write_text(ports)
    assert LISTENERS.cloudflared_identity() is None


@pytest.mark.parametrize("command", [
    b"cloudflared\0proxy-dns\0", b"cloudflared\0tunnel\0list\0",
    b"cloudflared\0tunnel\0run\0--proxy-dns\0",
    b"cloudflared\0tunnel\0run\0--proxy-dns-port=44858\0",
])
def test_non_tunnel_or_dns_server_command_confers_no_exception(tunnel, command) -> None:
    (tunnel.pid / "cmdline").write_bytes(command)
    assert LISTENERS.cloudflared_identity() is None


def test_documented_tunnel_run_command_is_supported(tunnel) -> None:
    (tunnel.pid / "cmdline").write_bytes(b"cloudflared\0--no-autoupdate\0tunnel\0run\0")
    assert LISTENERS.cloudflared_identity() is not None


@pytest.mark.parametrize("properties", [
    "ActiveState=inactive\nMainPID=468\nFragmentPath=/unit\n",
    "ActiveState=active\nMainPID=0\nFragmentPath=/unit\n",
    "ActiveState=active\nMainPID=1\nFragmentPath=/unit\n",
    "ActiveState=active\nMainPID=nonsense\nFragmentPath=/unit\n",
    "ActiveState=active\nMainPID=468\n", "malformed\n",
])
def test_inactive_missing_or_invalid_systemd_identity_confers_no_exception(tunnel, monkeypatch, properties) -> None:
    monkeypatch.setattr(LISTENERS.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=properties))
    assert LISTENERS.cloudflared_identity() is None


def test_untrusted_binary_or_unit_confers_no_exception(tunnel, monkeypatch) -> None:
    for rejected in (tunnel.binary, tunnel.unit):
        monkeypatch.setattr(LISTENERS, "root_protected", lambda path: path != rejected)
        assert LISTENERS.cloudflared_identity() is None


def test_inspection_failure_confers_no_exception(tunnel, monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("systemctl", 10)
    monkeypatch.setattr(LISTENERS.subprocess, "run", fail)
    assert LISTENERS.cloudflared_identity() is None
    assert "sensitive-value" not in capsys.readouterr().out


@pytest.mark.parametrize("uid,mode,expected", [(0, 0o100755, True), (501, 0o100755, False), (0, 0o100775, False), (0, 0o100757, False)])
def test_root_protected_path_rejects_unprivileged_replacement(monkeypatch, uid, mode, expected) -> None:
    class FakePath:
        parents = ()
        def resolve(self, strict):
            return self
        def stat(self):
            return SimpleNamespace(st_uid=uid, st_mode=mode)
    assert LISTENERS.root_protected(FakePath()) is expected


def test_socket_table_requests_kernel_process_metadata(monkeypatch) -> None:
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=SS_SAMPLE)
    monkeypatch.setattr(LISTENERS.subprocess, "run", run)
    assert LISTENERS.listening_socket_table() == SS_SAMPLE
    assert "--processes" in calls[0]


def test_identity_is_rechecked_after_reading_the_descriptor(tunnel, monkeypatch) -> None:
    matches = iter([True, False])
    monkeypatch.setattr(LISTENERS, "process_matches", lambda identity: next(matches))
    assert LISTENERS.evaluate(CLIENT, ["tcp/22"], tunnel.identity)


def test_ipv4_kernel_socket_table_is_supported(tunnel) -> None:
    table = tunnel.pid / "net" / "udp6"
    text = table.read_text().replace("0" * 32, "0" * 8)
    table.write_text(text.splitlines()[0] + "\n")
    (tunnel.pid / "net" / "udp").write_text(text)
    assert LISTENERS.evaluate(CLIENT.replace("*:44858", "0.0.0.0:44858"), ["tcp/22"], tunnel.identity) == []


def test_writable_parent_directory_prevents_executable_trust() -> None:
    class FakePath:
        def __init__(self, mode, parents=()):
            self.mode, self.parents = mode, parents
        def resolve(self, strict):
            return self
        def stat(self):
            return SimpleNamespace(st_uid=0, st_mode=self.mode)
    parent = FakePath(0o40777)
    assert LISTENERS.root_protected(FakePath(0o100755, (parent,))) is False
