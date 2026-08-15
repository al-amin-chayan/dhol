from __future__ import annotations

from pathlib import Path
import sys


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTROLLER_DIR.parents[1]
sys.path.insert(0, str(CONTROLLER_DIR))

from repo_policy import (  # noqa: E402
    check_action_pins,
    check_container_pins,
    check_prohibited_paths,
    check_requirement_hashes,
    check_symlink_boundaries,
    repository_files,
    run_policy,
)


def write(root: Path, relative: str, content: str = "fixture") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_repository_policy_is_positive_and_idempotent() -> None:
    first = run_policy(REPO_ROOT)
    second = run_policy(REPO_ROOT)
    assert first == []
    assert second == first


def test_floating_image_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "stack/compose.yml", "services:\n  cache:\n    image: redis:7\n")
    findings = check_container_pins(tmp_path, repository_files(tmp_path))
    assert any("not pinned" in finding for finding in findings)


def test_digest_pinned_image_is_accepted(tmp_path: Path) -> None:
    digest = "a" * 64
    write(tmp_path, "stack/compose.yml", f"services:\n  cache:\n    image: redis:7@sha256:{digest}\n")
    assert check_container_pins(tmp_path, repository_files(tmp_path)) == []


def test_unhashed_requirement_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "example==1.0.0\n")
    findings = check_requirement_hashes(tmp_path, repository_files(tmp_path))
    assert any("no sha256 hash" in finding for finding in findings)


def test_hashed_requirement_is_accepted(tmp_path: Path) -> None:
    digest = "b" * 64
    write(tmp_path, "requirements.txt", f"example==1.0.0 --hash=sha256:{digest}\n")
    assert check_requirement_hashes(tmp_path, repository_files(tmp_path)) == []


def test_unpinned_action_is_rejected(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/workflows/test.yml",
        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v7\n",
    )
    findings = check_action_pins(tmp_path, repository_files(tmp_path))
    assert any("full commit SHA" in finding for finding in findings)


def test_plaintext_env_generated_media_and_state_are_rejected(tmp_path: Path) -> None:
    write(tmp_path, ".env.production", "TOKEN=not-a-real-token\n")
    write(tmp_path, "out/generated.png")
    write(tmp_path, "infra/tofu/terraform.tfstate")
    findings = check_prohibited_paths(tmp_path, repository_files(tmp_path))
    assert any("plaintext .env" in finding for finding in findings)
    assert any("generated media" in finding for finding in findings)
    assert any("state or plan" in finding for finding in findings)


def test_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (root / "escape").symlink_to(outside)
    findings = check_symlink_boundaries(root, repository_files(root))
    assert any("escapes the repository" in finding for finding in findings)
