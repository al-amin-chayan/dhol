"""Drift coverage for the Unix-socket-only Docker daemon contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra/roles/docker/files/verify_daemon_listeners.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dholbeat_docker_listeners", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DOCKER = load_module()
DECLARED = ["unix:///var/run/docker.sock"]

# Captured from Ubuntu 24.04. ss omits the Netid column when a single protocol
# is selected, so the committed invocation's real output is shape-dependent.
SS_TCP_ONLY = 'LISTEN 0      1      127.0.0.1:{port} 0.0.0.0:* users:(("{process}",pid=270,fd=3))'
SS_TCP_AND_UDP = 'tcp LISTEN 0      1      127.0.0.1:{port} 0.0.0.0:* users:(("{process}",pid=270,fd=3))'
SS_SHAPES = (SS_TCP_ONLY, SS_TCP_AND_UDP)

# Captured from `systemctl show <unit> --property=Listen --value` on Ubuntu
# 24.04. systemd serializes the endpoint first, then the kind in parentheses.
HEALTHY_LISTEN = "/run/docker.sock (Stream)"


def document(**overrides):
    base = {
        "declared_hosts": DECLARED,
        "daemon_config": {"live-restore": True, "log-driver": "json-file"},
        "exec_start": "/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock",
        "socket_table": SS_TCP_AND_UDP.format(port="22", process="sshd"),
        "socket_activation": HEALTHY_LISTEN,
    }
    base.update(overrides)
    return base


def test_a_conforming_daemon_passes() -> None:
    assert DOCKER.validate(document()) == []


def test_a_daemon_json_hosts_key_matching_the_contract_passes() -> None:
    assert DOCKER.validate(document(daemon_config={"hosts": DECLARED})) == []


@pytest.mark.parametrize(
    "host",
    [
        "tcp://127.0.0.1:4243",
        "tcp://0.0.0.0:2375",
        "tcp://10.4.0.7:9999",
        "npipe:////./pipe/docker_engine",
    ],
)
def test_a_non_unix_host_in_daemon_json_is_rejected(host: str) -> None:
    findings = DOCKER.validate(document(daemon_config={"hosts": [host]}))
    assert any("non-Unix Docker host" in finding for finding in findings), findings


def test_a_loopback_tcp_host_on_a_nonstandard_port_is_rejected() -> None:
    """The exact drift the public-listener probe deliberately ignores."""

    findings = DOCKER.validate(document(daemon_config={"hosts": ["tcp://127.0.0.1:4243"]}))
    assert findings


@pytest.mark.parametrize(
    "exec_start",
    [
        "/usr/bin/dockerd -H tcp://127.0.0.1:4243",
        "/usr/bin/dockerd --host tcp://0.0.0.0:2376",
        "/usr/bin/dockerd --host=tcp://127.0.0.1:9999 -H fd://",
        "/usr/bin/dockerd -H fd:// -H tcp://127.0.0.1:2375",
    ],
)
def test_a_non_unix_host_on_the_systemd_command_line_is_rejected(exec_start: str) -> None:
    findings = DOCKER.validate(document(exec_start=exec_start))
    assert any("systemd command line" in finding for finding in findings), findings


@pytest.mark.parametrize("shape", SS_SHAPES)
@pytest.mark.parametrize("port", ["2375", "2376", "4243", "9999"])
def test_any_socket_owned_by_the_daemon_is_rejected(shape: str, port: str) -> None:
    """Both real ss output shapes must be parsed, not just the two-column one."""

    table = shape.format(port=port, process="dockerd")
    findings = DOCKER.validate(document(socket_table=table))
    assert any("is listening on a" in finding for finding in findings), findings


def test_the_committed_ss_invocation_shape_is_not_silently_skipped() -> None:
    """Regression: ss omits Netid with a single protocol, and rows were skipped."""

    table = "LISTEN 0      1      127.0.0.1:4243 0.0.0.0:* users:((\"dockerd\",pid=270,fd=3))"
    assert DOCKER.validate(document(socket_table=table)) != []


@pytest.mark.parametrize("shape", SS_SHAPES)
def test_a_non_docker_listener_is_not_attributed_to_the_daemon(shape: str) -> None:
    table = shape.format(port="443", process="nginx")
    assert DOCKER.validate(document(socket_table=table)) == []


@pytest.mark.parametrize(
    "row",
    [
        'LISTEN 0 1 users:(("dockerd",pid=270,fd=3))',
        'tcp dockerd',
        'LISTEN 0 1 not-an-endpoint 0.0.0.0:* users:(("dockerd",pid=1,fd=3))',
    ],
)
def test_an_unparseable_daemon_row_fails_closed(row: str) -> None:
    findings = DOCKER.validate(document(socket_table=row))
    assert any("could not be parsed" in finding for finding in findings), findings


# --- systemd socket activation behind fd:// ---

def test_the_normal_docker_socket_unit_passes() -> None:
    """Regression: the shared verifier must not fail a healthy default install."""

    assert DOCKER.validate(document(socket_activation=HEALTHY_LISTEN)) == []


@pytest.mark.parametrize(
    "listen_value",
    [
        "/run/docker.sock (Stream)",
        "/var/run/docker.sock (Stream)",
        "/run/docker-custom.sock (Stream)",
    ],
)
def test_a_filesystem_socket_activation_endpoint_passes(listen_value: str) -> None:
    assert DOCKER.validate(document(socket_activation=listen_value)) == []


@pytest.mark.parametrize(
    "listen_value",
    [
        "127.0.0.1:2375 (Stream)",
        "0.0.0.0:2376 (Stream)",
        "[::1]:4243 (Stream)",
        "10.4.0.7:9999 (Datagram)",
    ],
)
def test_a_network_socket_activation_endpoint_is_rejected(listen_value: str) -> None:
    """fd:// is only Unix-only if the activating socket unit is."""

    findings = DOCKER.validate(document(socket_activation=listen_value))
    assert any("non-filesystem endpoint" in finding for finding in findings), findings


def test_a_non_stream_socket_kind_is_reported() -> None:
    findings = DOCKER.validate(document(socket_activation="/run/docker.sock (Datagram)"))
    assert any("unexpected socket kind" in finding for finding in findings), findings


def test_a_mixed_unit_is_rejected_for_its_network_endpoint() -> None:
    """Captured from a unit declaring both a filesystem and a network endpoint."""

    listen_value = "/run/probe-multi.sock (Stream)\n10.4.0.7:9999 (Datagram)"
    findings = DOCKER.validate(document(socket_activation=listen_value))
    assert any("non-filesystem endpoint" in finding for finding in findings), findings


def test_fd_activation_without_any_declared_endpoint_is_rejected() -> None:
    """An absent unit yields empty output, which cannot be what fd:// claims."""

    findings = DOCKER.validate(document(socket_activation=""))
    assert any("declares no endpoint" in finding for finding in findings), findings


@pytest.mark.parametrize(
    "listen_value",
    ["StreamOnly", "Stream /run/docker.sock", "(Stream)", "/run/docker.sock Stream"],
)
def test_an_unparseable_socket_activation_entry_fails_closed(listen_value: str) -> None:
    findings = DOCKER.validate(document(socket_activation=listen_value))
    assert any("Listen entry could not be parsed" in finding for finding in findings), findings


def test_a_daemon_without_fd_activation_needs_no_socket_unit() -> None:
    assert (
        DOCKER.validate(
            document(
                exec_start="/usr/bin/dockerd -H unix:///var/run/docker.sock",
                socket_activation="",
            )
        )
        == []
    )
