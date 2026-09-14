"""Execute the shared operator capture/comparison with provider-safe stand-ins."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("failure", [None, "provider", "normalizer", "drift", "missing"])
def test_fresh_capture_and_comparison_fail_before_host_mutation(tmp_path, failure):
    log = tmp_path / "calls"
    approved = tmp_path / "approved.json"
    approved.write_text("stable\n")
    fresh = tmp_path / "fresh.json"
    marker = tmp_path / "host-mutated"
    environment = {**os.environ, "CALL_LOG": str(log), "PROVIDER_STATUS": "1" if failure == "provider" else "0",
                   "NORMALIZER_STATUS": "1" if failure == "normalizer" else "0",
                   "AUTHORITY": "changed" if failure == "drift" else "stable"}
    if failure == "missing":
        approved.unlink()
    # Bash path-named stand-ins avoid executable fixtures on the controller's
    # deliberately noexec tmpfs, while exercising the actual shared functions.
    driver = '''set -eu
source "$1"
SCRIPT_DIR=fixture
function fixture/cloudflare {
  printf 'provider\\n' >>"$CALL_LOG"
  [ "$1" = plan ] || return 2
  return "$PROVIDER_STATUS"
}
function fixture/controller {
  printf 'normalize\\n' >>"$CALL_LOG"
  [ "$1" = exec ] && [ "$3" = infra/tofu/cloudflare/receipt.py ] || return 2
  printf '%s\\n' "$AUTHORITY"
  return "$NORMALIZER_STATUS"
}
dholbeat_refresh_cloudflare "$2"
dholbeat_compare_cloudflare "$3" "$2"
touch "$4"
'''
    result = subprocess.run(["bash", "-c", driver,
                             "boundary-fixture", str(ROOT / "scripts/lib/common.sh"), str(fresh), str(approved), str(marker)],
                            env=environment, capture_output=True, text=True)
    assert marker.exists() is (failure is None), result.stderr
    assert (result.returncode == 0) is (failure is None)
    assert log.read_text().splitlines() == (["provider"] if failure == "provider" else ["provider", "normalize"])
    if failure is None:
        assert fresh.stat().st_mode & 0o777 == 0o600
