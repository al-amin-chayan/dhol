from __future__ import annotations

from pathlib import Path
import sys

import pytest


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROLLER_DIR))

from secret_scan import prepare_scan_tree  # noqa: E402


def test_symlinked_directory_is_rejected_before_copy(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "target"
    target.mkdir()
    (target / "value.txt").write_text("safe fixture\n", encoding="utf-8")
    (root / "linked-directory").symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked directories are forbidden"):
        prepare_scan_tree(root, tmp_path / "scan")
