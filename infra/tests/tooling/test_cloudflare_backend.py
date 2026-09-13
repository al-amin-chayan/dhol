"""Meaningful backend failure, scope, encryption and retention contracts."""
import base64
import importlib.util
import json
from pathlib import Path
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "tofu/cloudflare"
spec = importlib.util.spec_from_file_location("dholbeat_r2_backend", PACKAGE / "backend.py")
backend = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backend
spec.loader.exec_module(backend)


def test_session_has_exact_bucket_prefix_and_one_hour_lifetime():
    credentials = backend.session("account", "parent-id", "parent-secret", "state-bucket", ["cloudflare/"], now=100)
    jwt = base64.b64decode(credentials["AWS_SESSION_TOKEN"])[4:]
    payload = json.loads(base64.urlsafe_b64decode(jwt.split(b".")[1] + b"=="))
    assert payload["bucket"] == "state-bucket"
    assert payload["paths"] == {"prefixPaths": ["cloudflare/"], "objectPaths": []}
    assert payload["exp"] - payload["iat"] == 3600
    assert payload["aud"] == "account.r2.cloudflarestorage.com"
    assert credentials["AWS_SECRET_ACCESS_KEY"] == backend.digest(jwt)
    assert "parent-secret" not in str(credentials)


@pytest.mark.parametrize("data", [b"", b"invalid", b'{"resources": []}',
                                  b'{"encryption_version":"v0","encrypted_data":"x","resources":[]}',
                                  b"x" * (backend.MAX_STATE_BYTES + 1)])
def test_plaintext_and_oversized_state_is_rejected(data):
    with pytest.raises(backend.BackendError):
        backend.require_ciphertext(data)


class Store:
    def __init__(self, data=None, corrupt=False):
        self.objects = data or {}
        self.deleted = []
        self.corrupt = corrupt

    def request(self, method, key, body=b"", **kwargs):
        if method == "PUT":
            assert kwargs["headers"] == {"if-none-match": "*"}
            self.objects[key] = body
            return b""
        if method == "DELETE":
            self.deleted.append(key)
            del self.objects[key]
            return b""
        return b"corrupt" if self.corrupt else self.objects[key]

    def list(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]


CIPHER = b'{"encryption_version":"v0","encrypted_data":"cipher"}'


def test_native_state_coordination_metadata_is_allowed():
    backend.require_ciphertext(b'{"encryption_version":"v0","encrypted_data":"cipher","serial":1,"lineage":"public-id","meta":{}}')


def test_verified_copy_prunes_only_old_snapshots_and_preserves_credential_root():
    existing = {f"snapshots/20260101T000000{i:06d}Z-{'a'*64}.tfstate": CIPHER for i in range(20)}
    existing["recovery/cloudflare.sops.yml"] = b"ciphertext"
    recovery = Store(existing)
    receipt = backend.snapshot(Store({"state": CIPHER}), recovery, "state")
    assert len(recovery.list("snapshots/")) == 20
    assert len(recovery.deleted) == 1
    assert receipt["sha256"] == backend.digest(CIPHER)
    assert "recovery/cloudflare.sops.yml" in recovery.objects


def test_bad_readback_never_deletes_a_snapshot():
    recovery = Store(corrupt=True)
    with pytest.raises(backend.BackendError, match="read-back"):
        backend.snapshot(Store({"state": CIPHER}), recovery, "state")
    assert len(recovery.deleted) == 1
    assert recovery.deleted[0].startswith("snapshots/")
    assert "snapshots/do-not-delete" not in recovery.deleted


def test_unrecognized_object_prevents_pruning():
    recovery = Store({"snapshots/do-not-delete": b"other"})
    with pytest.raises(backend.BackendError, match="unrecognized"):
        backend.snapshot(Store({"state": CIPHER}), recovery, "state")
    assert len(recovery.deleted) == 1
    assert recovery.deleted[0].startswith("snapshots/")
    assert "snapshots/do-not-delete" not in recovery.deleted
