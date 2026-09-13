"""Pure, deterministic binding of the finite operator's live no-change receipt."""
import hashlib
import json
from pathlib import Path
import re
import time


def input_digest(root: Path) -> str:
    package = root / "infra/tofu/cloudflare"
    digestor = hashlib.sha256()
    paths = sorted(path for path in package.iterdir() if path.is_file() and path.suffix in {".tf", ".yml", ".json", ".py", ".hcl"})
    paths += [root / "infra/services/domains.yml", root / "infra/inventories/production/hosts.yml", root / "toolchain.lock.yml"]
    paths += [root / "infra/secrets/cloudflare.sops.yml", root / "infra/secrets/catalog.yml"]
    for path in paths:
        digestor.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digestor.hexdigest()


def normalize(root: Path, receipt: dict, now: float | None = None) -> dict:
    expected = json.loads((root / "infra/tofu/cloudflare/adoption.json").read_text())
    packages = {p.name for p in (root / "infra/tofu").iterdir() if p.is_dir() and p.name != "__pycache__"}
    unknown_files = [p for p in (root / "infra/tofu").iterdir() if p.is_file() and p.suffix in {".tf", ".tfvars", ".json", ".hcl"}]
    if packages != {"cloudflare"} or unknown_files:
        raise ValueError("unadapted OpenTofu package")
    if (receipt.get("schema_version") != 1 or receipt.get("package") != "cloudflare"
            or receipt.get("provider_mutations") != 0 or receipt.get("imported") is not False
            or receipt.get("resource_count") != len(expected) or not expected
            or receipt.get("opentofu_version") != "1.12.5" or receipt.get("provider_version") != "5.24.0"
            or receipt.get("inputs_sha256") != input_digest(root)):
        raise ValueError("receipt does not bind this complete no-change package")
    observed = receipt.get("observed_epoch")
    age = (time.time() if now is None else now) - observed if isinstance(observed, (int, float)) else -1
    if not 0 <= age <= 300:
        raise ValueError("live no-change receipt is stale or future-dated")
    for key in ("encrypted_plan_sha256", "encrypted_state_sha256"):
        if not isinstance(receipt.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", receipt[key]):
            raise ValueError("encrypted plan/state digest is missing")
    if receipt.get("backend_bucket") != "dholbeat-tfstate" or receipt.get("backend_key") != "cloudflare/production.tfstate":
        raise ValueError("backend authority differs")
    # Encryption randomness and plan timestamps are evidence, not an external resource delta.
    # The exact captured binary is guarded by the operator; stable source + unchanged state
    # are re-proven by a fresh real provider plan each time infra-apply replans.
    keys = ("package", "provider_mutations", "resource_count", "provider_version", "opentofu_version",
            "inputs_sha256", "encrypted_state_sha256", "backend_bucket", "backend_key")
    return {"state": "verified-no-change", **{key: receipt[key] for key in keys}}
