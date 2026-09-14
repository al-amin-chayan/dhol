"""Missing identities never count as positive route evidence."""

from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'infra/tofu/cloudflare'))
import probes  # noqa: E402
import routing_verify as verifier  # noqa: E402
from control_plane import ContractError  # noqa: E402

MANIFEST = yaml.safe_load((ROOT / 'infra/tofu/cloudflare/routes.yml').read_text())


def test_missing_scoped_sessions_media_and_ip_remain_incomplete(monkeypatch):
    def request(host, path='/', headers=None):
        return probes.Response(403)

    monkeypatch.setattr(probes, 'request', request)
    monkeypatch.setattr(verifier, 'request', request)
    outcomes = verifier.probes(MANIFEST, {})
    assert outcomes['founder'] == 'scoped-session-required'
    assert outcomes['service-token'] == 'scoped-service-and-application-credentials-required'
    assert outcomes['direct-ip'] == 'explicit-public-host-ip-required'
    assert verifier.media_probe({}) == 'reviewed-media-fixture-required'


def test_service_token_cannot_escape_to_ui(monkeypatch):
    monkeypatch.setattr(verifier, 'run_live', lambda *args: {'publisher-admin-api': {}})
    monkeypatch.setattr(verifier, 'request', lambda *args: probes.Response(200))
    with pytest.raises(ContractError, match='escapes'):
        verifier.probes(MANIFEST, {'N8N_ACCESS_CLIENT_ID': 'fixture-id', 'N8N_ACCESS_CLIENT_SECRET': 'fixture-secret'})


def test_media_fixture_requires_safe_coordinates_before_network():
    with pytest.raises(ContractError):
        verifier.media_probe({'MEDIA_PROBE_PATH': '/private/config', 'MEDIA_PROBE_SHA256': 'a' * 64})
