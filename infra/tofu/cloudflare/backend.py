"""R2 signing, bounded encrypted snapshots and ephemeral bucket-scoped sessions."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re

import yaml
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BOUNDS = yaml.safe_load(Path(__file__).with_name("bootstrap.yml").read_text())[
    "backend"
]
MAX_STATE_BYTES = BOUNDS["max_state_bytes"]
MAX_SNAPSHOTS = BOUNDS["snapshot_count"]
# Declarative bounds may be reduced, but never exceed the founding disk ceiling.
if (
    type(MAX_STATE_BYTES) is not int
    or not 0 < MAX_STATE_BYTES <= 4 * 1024 * 1024
    or type(MAX_SNAPSHOTS) is not int
    or not 0 < MAX_SNAPSHOTS <= 20
):
    raise ValueError("backend retention bounds exceed the absolute disk ceiling")


class BackendError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def session(
    account: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    prefixes: list[str],
    now: int | None = None,
) -> dict[str, str]:
    """Cloudflare's documented HS256 delegation; parent never reaches OpenTofu."""
    issued = int(time.time()) if now is None else now
    endpoint = f"{account}.r2.cloudflarestorage.com"
    payload = {
        "bucket": bucket,
        "scope": "object-read-write",
        "sub": account,
        "iss": access_key,
        "aud": endpoint,
        "iat": issued,
        "exp": issued + 3600,
        "paths": {"prefixPaths": prefixes, "objectPaths": []},
    }

    def encode(value):
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode()
        ).rstrip(b"=")

    content = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(payload)
    signature = base64.urlsafe_b64encode(
        hmac.digest(secret_key.encode(), content, "sha256")
    ).rstrip(b"=")
    jwt = content + b"." + signature
    return {
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": digest(jwt),
        "AWS_SESSION_TOKEN": base64.b64encode(b"jwt/" + jwt).decode(),
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class S3:
    def __init__(self, account: str, bucket: str, credentials: dict[str, str]):
        self.host = f"{account}.r2.cloudflarestorage.com"
        self.bucket = bucket
        self.credentials = credentials

    def request(
        self,
        method: str,
        key: str = "",
        body: bytes = b"",
        query=None,
        headers=None,
        expected=(200,),
        now: datetime | None = None,
        missing_ok=False,
        status_only=False,
    ) -> bytes:
        timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        day = timestamp[:8]
        path = "/" + urllib.parse.quote(self.bucket + "/" + key, safe="/~")
        pairs = sorted(
            (urllib.parse.quote(str(k), safe="~"), urllib.parse.quote(str(v), safe="~"))
            for k, v in (query or {}).items()
        )
        query_string = "&".join(k + "=" + v for k, v in pairs)
        signed = {
            "host": self.host,
            "x-amz-date": timestamp,
            "x-amz-content-sha256": digest(body),
            "x-amz-security-token": self.credentials["AWS_SESSION_TOKEN"],
            **(headers or {}),
        }
        signed = {k.lower(): " ".join(v.split()) for k, v in signed.items()}
        names = ";".join(sorted(signed))
        canonical_headers = "".join(f"{k}:{signed[k]}\n" for k in sorted(signed))
        canonical = "\n".join(
            (method, path, query_string, canonical_headers, names, digest(body))
        )
        scope = f"{day}/auto/s3/aws4_request"
        string_to_sign = "\n".join(
            ("AWS4-HMAC-SHA256", timestamp, scope, digest(canonical.encode()))
        )
        signing_key = ("AWS4" + self.credentials["AWS_SECRET_ACCESS_KEY"]).encode()
        for component in (day, "auto", "s3", "aws4_request"):
            signing_key = hmac.digest(signing_key, component.encode(), "sha256")
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        signed["authorization"] = (
            "AWS4-HMAC-SHA256 Credential="
            + self.credentials["AWS_ACCESS_KEY_ID"]
            + "/"
            + scope
            + ", SignedHeaders="
            + names
            + ", Signature="
            + signature
        )
        request = urllib.request.Request(
            "https://"
            + self.host
            + path
            + ("?" + query_string if query_string else ""),
            data=body if method in {"PUT", "POST"} else None,
            headers=signed,
            method=method,
        )
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            if missing_ok and response.status == 404:
                return None
            if response.status not in expected:
                raise BackendError(f"R2 operation rejected (HTTP {response.status})")
            if status_only:
                return response.status
            data = response.read(MAX_STATE_BYTES + 1)
            if len(data) > MAX_STATE_BYTES:
                raise BackendError("R2 object exceeds the bounded state size")
            return data

    def list(self, prefix: str) -> list[str]:
        document = ET.fromstring(
            self.request(
                "GET", query={"list-type": 2, "prefix": prefix, "max-keys": 1000}
            )
        )
        namespace = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        if document.findtext("s:IsTruncated", namespaces=namespace) != "false":
            raise BackendError("snapshot inventory exceeds the bounded listing")
        return [item.text for item in document.findall("s:Contents/s:Key", namespace)]


def require_ciphertext(data: bytes) -> None:
    if not data or len(data) > MAX_STATE_BYTES:
        raise BackendError("encrypted state is empty or exceeds its bound")
    try:
        envelope = json.loads(data)
    except ValueError:
        raise BackendError(
            "state is not a client-encrypted OpenTofu envelope"
        ) from None
    if (
        not isinstance(envelope, dict)
        or "encrypted_data" not in envelope
        or "encryption_version" not in envelope
    ):
        raise BackendError("plaintext state is forbidden")
    # Native OpenTofu leaves serial/lineage outside its encrypted payload for backend coordination.
    if any(key in envelope for key in ("resources", "outputs")):
        raise BackendError("plaintext state is forbidden")


def snapshot(
    source: S3, recovery: S3, key: str, prefix: str = "snapshots/"
) -> dict[str, str | int]:
    data = source.request("GET", key)
    require_ciphertext(data)
    sha = digest(data)
    target = (
        prefix
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + sha
        + ".tfstate"
    )
    recovery.request(
        "PUT", target, data, headers={"if-none-match": "*"}, expected=(200,)
    )
    try:
        if digest(recovery.request("GET", target)) != sha:
            raise BackendError("recovery read-back mismatch; no snapshots were pruned")
        objects = sorted(recovery.list(prefix))
        # Never delete credential roots or objects outside this exact generated format.
        if any(
            not re.fullmatch(
                re.escape(prefix) + r"[0-9]{8}T[0-9]{12}Z-[a-f0-9]{64}\.tfstate", k
            )
            for k in objects
        ):
            raise BackendError("unrecognized recovery object; no snapshots were pruned")
        for old in objects[:-MAX_SNAPSHOTS]:
            recovery.request("DELETE", old, expected=(204,))
    except Exception:
        # Remove only this candidate. Earlier successful old-snapshot deletions
        # are permanent; a later prune failure does not restore those objects.
        recovery.request("DELETE", target, expected=(204,))
        raise
    return {
        "snapshot_key": target,
        "sha256": sha,
        "bytes": len(data),
        "retention_count": MAX_SNAPSHOTS,
    }
