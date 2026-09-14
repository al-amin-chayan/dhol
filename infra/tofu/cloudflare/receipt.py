"""Pure, deterministic binding of the finite operator's live no-change receipt."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time

import yaml


def input_digest(root: Path) -> str:
    package = root / "infra/tofu/cloudflare"
    digestor = hashlib.sha256()
    paths = sorted(
        path
        for path in package.iterdir()
        if path.is_file() and path.suffix in {".tf", ".yml", ".json", ".py", ".hcl"}
    )
    paths += [
        root / "infra/services/domains.yml",
        root / "infra/inventories/production/hosts.yml",
        root / "toolchain.lock.yml",
    ]
    paths += [
        root / "infra/secrets/cloudflare.sops.yml",
        root / "infra/secrets/catalog.yml",
        root / ".sops.yaml",
    ]
    for path in paths:
        digestor.update(
            path.relative_to(root).as_posix().encode()
            + b"\0"
            + path.read_bytes()
            + b"\0"
        )
    return digestor.hexdigest()


def normalize(root: Path, receipt: dict, now: float | None = None, *, max_age: float | None = 300) -> dict:
    expected = json.loads((root / "infra/tofu/cloudflare/adoption.json").read_text())
    packages = {
        p.name
        for p in (root / "infra/tofu").iterdir()
        if p.is_dir() and p.name != "__pycache__"
    }
    unknown_files = [
        p
        for p in (root / "infra/tofu").iterdir()
        if p.is_file() and p.suffix in {".tf", ".tfvars", ".json", ".hcl"}
    ]
    if packages != {"cloudflare"} or unknown_files:
        raise ValueError("unadapted OpenTofu package")
    routing_enabled = receipt.get("routing_enabled", False)
    from routing import footprint

    count = len(expected)
    if routing_enabled:
        manifest = yaml.safe_load((root / "infra/tofu/cloudflare/routes.yml").read_text())
        bootstrap = yaml.safe_load((root / "infra/tofu/cloudflare/bootstrap.yml").read_text())
        count += len(footprint(manifest, bootstrap, ""))
    if (
        receipt.get("schema_version") != 1
        or receipt.get("package") != "cloudflare"
        or receipt.get("provider_mutations") != 0
        or receipt.get("imported") is not False
        or type(routing_enabled) is not bool
        or receipt.get("resource_count") != count
        or not expected
        or receipt.get("opentofu_version") != "1.12.5"
        or receipt.get("provider_version") != "5.24.0"
        or receipt.get("inputs_sha256") != input_digest(root)
    ):
        raise ValueError("receipt does not bind this complete no-change package")
    observed = receipt.get("observed_epoch")
    age = (
        (time.time() if now is None else now) - observed
        if type(observed) in (int, float) and observed > 0 and math.isfinite(observed)
        else -1
    )
    if age < 0 or (max_age is not None and age > max_age):
        raise ValueError("live no-change receipt is stale or future-dated")
    for key in ("encrypted_plan_sha256", "encrypted_state_sha256"):
        if not isinstance(receipt.get(key), str) or not re.fullmatch(
            r"[a-f0-9]{64}", receipt[key]
        ):
            raise ValueError("encrypted plan/state digest is missing")
    backend = yaml.safe_load(
        (root / "infra/tofu/cloudflare/bootstrap.yml").read_text()
    )["backend"]
    if (
        receipt.get("backend_bucket") != backend["bucket"]
        or receipt.get("backend_key") != backend["key"]
    ):
        raise ValueError("backend authority differs")
    # Encryption randomness and plan timestamps are evidence, not an external resource delta.
    # The exact captured binary is guarded by the operator; stable source + unchanged state
    # are re-proven by a fresh real provider plan each time infra-apply replans.
    keys = (
        "package",
        "provider_mutations",
        "resource_count",
        "provider_version",
        "opentofu_version",
        "inputs_sha256",
        "encrypted_state_sha256",
        "backend_bucket",
        "backend_key",
    )
    result = {"state": "verified-no-change", "routing_enabled": routing_enabled, **{key: receipt[key] for key in keys}}
    if routing_enabled:
        audiences = receipt.get('publisher_access_audiences')
        team = receipt.get('access_team_name')
        if (not isinstance(audiences, list) or len(audiences) != 2
                or any(not isinstance(v, str) or not re.fullmatch('[a-f0-9]{64}', v) for v in audiences)
                or len(set(audiences)) != 2 or not isinstance(team, str) or not re.fullmatch('[a-z0-9-]+', team)):
            raise ValueError('live publisher Access authority is missing')
        result.update(publisher_access_audiences=sorted(audiences), access_team_name=team)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize(args.root, json.loads(args.receipt.read_text())), sort_keys=True))
