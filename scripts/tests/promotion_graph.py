#!/usr/bin/env python3
"""Host-Git integration regression; the offline controller intentionally has no Git.

Run: python3 scripts/tests/promotion_graph.py
"""

from pathlib import Path
import subprocess
import tempfile


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True).stdout.strip()


def test_real_merge_repair_preserves_ancestry_and_squash_does_not(tmp_path):
    git(tmp_path, "init", "-b", "develop")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "file").write_text("base")
    git(tmp_path, "add", "file")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "branch", "main")
    (tmp_path / "file").write_text("feature")
    git(tmp_path, "commit", "-am", "feature")
    develop = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "main")
    git(tmp_path, "merge", "--no-ff", "develop", "-m", "promotion")
    main = git(tmp_path, "rev-parse", "HEAD")
    assert subprocess.run(["git", "merge-base", "--is-ancestor", main, develop], cwd=tmp_path).returncode == 1
    git(tmp_path, "checkout", "-b", "sync", "develop")
    git(tmp_path, "merge", "--no-ff", "main", "-m", "sync")
    sync = git(tmp_path, "rev-parse", "HEAD")
    assert git(tmp_path, "show", "-s", "--format=%P", sync).split() == [develop, main]
    assert git(tmp_path, "rev-parse", f"{sync}^{{tree}}") == git(tmp_path, "rev-parse", f"{develop}^{{tree}}")
    git(tmp_path, "checkout", "develop")
    git(tmp_path, "merge", "--squash", "sync")
    git(tmp_path, "commit", "--allow-empty", "-m", "squashed sync")
    squashed = git(tmp_path, "rev-parse", "HEAD")
    assert squashed != develop
    assert git(tmp_path, "show", "-s", "--format=%P", squashed).split() == [develop]
    assert git(tmp_path, "rev-parse", f"{squashed}^{{tree}}") == git(tmp_path, "rev-parse", f"{develop}^{{tree}}")
    assert subprocess.run(["git", "merge-base", "--is-ancestor", main, "HEAD"], cwd=tmp_path).returncode == 1
    git(tmp_path, "merge", "--no-ff", "sync", "-m", "reviewed sync merge")
    git(tmp_path, "merge-base", "--is-ancestor", main, "develop")
    git(tmp_path, "checkout", "main")
    git(tmp_path, "merge", "--no-ff", "develop", "-m", "next promotion")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="dholbeat-promotion-graph-") as temporary:
        test_real_merge_repair_preserves_ancestry_and_squash_does_not(Path(temporary))
    print("real Git promotion/sync/squash/next-promotion regression passed")
