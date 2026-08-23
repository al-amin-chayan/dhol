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


def document(**overrides):
    base = {
        "declared_hosts": DECLARED,
        "daemon_config": {"live-restore": True, "log-driver": "json-file"},
        "exec_start": "/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock",
        "socket_table": "tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:((\"sshd\",pid=700,fd=3))",
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


@pytest.mark.parametrize(
    "port", ["2375", "2376", "4243", "9999"]
)
def test_any_tcp_socket_owned_by_the_daemon_is_rejected(port: str) -> None:
    table = f'tcp LISTEN 0 4096 127.0.0.1:{port} 0.0.0.0:* users:(("dockerd",pid=901,fd=9))'
    findings = DOCKER.validate(document(socket_table=table))
    assert any("listening on a TCP socket" in finding for finding in findings), findings


def test_a_non_docker_tcp_listener_is_not_the_daemon_contract() -> None:
    table = 'tcp LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:(("nginx",pid=12,fd=6))'
    assert DOCKER.validate(document(socket_table=table)) == []


def test_daemon_json_hosts_that_differ_from_the_contract_are_rejected() -> None:
    findings = DOCKER.validate(
        document(daemon_config={"hosts": ["unix:///var/run/docker-alt.sock"]})
    )
    assert any("do not match the declared" in finding for finding in findings), findings


def test_a_declared_contract_that_is_itself_non_unix_is_rejected() -> None:
    findings = DOCKER.validate(document(declared_hosts=["tcp://127.0.0.1:2375"]))
    assert any("declared docker_daemon_hosts" in finding for finding in findings), findings


def test_an_absent_hosts_key_is_acceptable() -> None:
    assert DOCKER.validate(document(daemon_config={})) == []
