#!/usr/bin/env python3
"""Verify a real exact-head cross-review and protected annotated release."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/controller"))
from review_gate import evaluate_pull_request  # noqa: E402


def run(argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError("release identity command failed; output suppressed")
    return result.stdout.strip()


def verify(tag, number):
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise ValueError("production operations cannot run in CI")
    if not re.fullmatch(r"infra-prod-[0-9]{8}-[1-9][0-9]*", tag) or not str(number).isdigit():
        raise ValueError("invalid production release/review PR")
    head = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if run(["git", "-C", str(ROOT), "status", "--porcelain"]):
        raise ValueError("production operation requires a clean worktree")
    if run(["git", "-C", str(ROOT), "cat-file", "-t", f"refs/tags/{tag}"]) != "tag":
        raise ValueError("release must be annotated")
    if run(["git", "-C", str(ROOT), "rev-parse", f"refs/tags/{tag}^{{commit}}"] ) != head:
        raise ValueError("release must point at checkout HEAD")
    url = "https://github.com/al-amin-chayan/dhol.git"
    run([str(ROOT / "scripts/github-app-git"), "fetch", '--no-prune', url, "main:refs/remotes/origin/main"])
    run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, "refs/remotes/origin/main"])
    base = f"repos/al-amin-chayan/dhol/pulls/{number}"
    pull = json.loads(run([str(ROOT / "scripts/github-app-gh"), "api", base]))
    reviews = json.loads(run([str(ROOT / "scripts/github-app-gh"), "api", "--paginate", "--slurp", base + "/reviews"]))
    reviews = [review for page in reviews for review in page]
    reviewed = pull.get("head", {}).get("sha")
    if (not pull.get("merged_at") or pull.get('base', {}).get('ref') != 'main'
            or pull.get('head', {}).get('ref') != 'develop'
            or pull.get('merge_commit_sha') != head):
        raise ValueError("release must be the recorded merge of a reviewed develop-to-main promotion")
    if run(['git', '-C', str(ROOT), 'rev-parse', head + '^{tree}']) != run(
            ['git', '-C', str(ROOT), 'rev-parse', str(reviewed) + '^{tree}']):
        raise ValueError('promotion merge tree differs from its exact reviewed source head')
    verdict = evaluate_pull_request(pull, reviews)
    if not verdict.allowed:
        raise ValueError("release cross-review gate rejected: " + "; ".join(verdict.findings))
    return head


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--review-pr", required=True)
    args = parser.parse_args()
    try:
        print(verify(args.release, args.review_pr))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
