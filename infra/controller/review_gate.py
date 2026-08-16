#!/usr/bin/env python3
"""Validate Dholbeat's human-triggered cross-review for an exact PR head."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any


REVIEW_LABELS = {
    "review:requested",
    "review:changes-requested",
    "review:ready-for-ci",
}
WORKFLOW_BLOCKER_LABELS = {"blocked", "decision"}
AREA_LABEL_PREFIX = "area:"
DECISIVE_STATES = {"APPROVED", "CHANGES_REQUESTED"}
AGENT_LOGINS = {
    "chayan-codex": "Codex",
    "chayan-claude": "Claude Code",
}
OPPOSITE_MODEL = {"Codex": "Claude Code", "Claude Code": "Codex"}
FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(Review type|Reviewer|Reviewed head)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ReviewMarkers:
    review_type: str
    reviewer: str
    reviewed_head: str


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    findings: tuple[str, ...]


def normalize_login(login: str) -> str:
    normalized = login.strip().lower()
    if normalized.startswith("app/"):
        normalized = normalized.removeprefix("app/")
    if normalized.endswith("[bot]"):
        normalized = normalized.removesuffix("[bot]")
    return normalized


def model_for_login(login: str) -> str | None:
    return AGENT_LOGINS.get(normalize_login(login))


def clean_marker_value(value: str) -> str:
    return value.strip().strip("`*_ ")


def parse_review_markers(body: str) -> ReviewMarkers | None:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        match = FIELD_RE.match(line)
        if match:
            fields[match.group(1).lower()] = clean_marker_value(match.group(2))
    review_type = fields.get("review type", "").title()
    reviewer = fields.get("reviewer", "")
    reviewed_head = fields.get("reviewed head", "").lower()
    if review_type not in {"Baseline", "Follow-Up"}:
        return None
    if reviewer not in OPPOSITE_MODEL:
        return None
    if SHA_RE.fullmatch(reviewed_head) is None:
        return None
    return ReviewMarkers(
        review_type="Follow-up" if review_type == "Follow-Up" else review_type,
        reviewer=reviewer,
        reviewed_head=reviewed_head,
    )


def review_sort_key(review: dict[str, Any]) -> tuple[str, int]:
    return str(review.get("submitted_at") or ""), int(review.get("id") or 0)


def evaluate_pull_request(pull: dict[str, Any], reviews: list[dict[str, Any]]) -> GateResult:
    findings: list[str] = []
    if pull.get("draft"):
        findings.append("the pull request is still a draft")

    base = str(pull.get("base", {}).get("ref") or "")
    head_ref = str(pull.get("head", {}).get("ref") or "")
    if base not in {"develop", "main"}:
        findings.append(f"unsupported base branch: {base or '<missing>'}")
    if base == "main" and head_ref != "develop":
        findings.append(f"main promotions must come from develop, not {head_ref or '<missing>'}")

    head_sha = str(pull.get("head", {}).get("sha") or "").lower()
    if SHA_RE.fullmatch(head_sha) is None:
        findings.append("the pull request head SHA is missing or invalid")

    label_names = {
        str(label.get("name"))
        for label in pull.get("labels", [])
        if isinstance(label, dict) and label.get("name")
    }
    active_review_labels = sorted(label_names & REVIEW_LABELS)
    if active_review_labels != ["review:ready-for-ci"]:
        rendered = ", ".join(active_review_labels) if active_review_labels else "none"
        findings.append(
            "the exact head must have only review:ready-for-ci; "
            f"active review labels: {rendered}"
        )
    if not any(name.startswith(AREA_LABEL_PREFIX) for name in label_names):
        findings.append("the pull request must have at least one area:* label")
    workflow_blockers = sorted(label_names & WORKFLOW_BLOCKER_LABELS)
    if workflow_blockers:
        findings.append(
            "blocked or decision PRs cannot pass review; active labels: "
            + ", ".join(workflow_blockers)
        )

    author_login = str(pull.get("user", {}).get("login") or "")
    author_model = model_for_login(author_login)
    if author_model is None:
        findings.append(
            "the PR author is not a recognized Dholbeat agent App: "
            f"{author_login or '<missing>'}"
        )
        return GateResult(False, tuple(findings))
    expected_reviewer = OPPOSITE_MODEL[author_model]

    expected_reviews: list[tuple[dict[str, Any], ReviewMarkers | None]] = []
    for review in sorted(reviews, key=review_sort_key):
        state = str(review.get("state") or "").upper()
        if state not in DECISIVE_STATES:
            continue
        review_login = str(review.get("user", {}).get("login") or "")
        if model_for_login(review_login) != expected_reviewer:
            continue
        expected_reviews.append((review, parse_review_markers(str(review.get("body") or ""))))

    if not expected_reviews:
        findings.append(f"no formal {expected_reviewer} cross-review has been submitted")
        return GateResult(False, tuple(findings))

    valid_reviews = []
    for review, markers in expected_reviews:
        review_commit = str(review.get("commit_id") or "").lower()
        if (
            markers is not None
            and markers.reviewer == expected_reviewer
            and markers.reviewed_head == review_commit
        ):
            valid_reviews.append((review, markers))
    if not valid_reviews:
        findings.append(f"no correctly marked formal {expected_reviewer} cross-review exists")
    else:
        baseline_reviews = [item for item in valid_reviews if item[1].review_type == "Baseline"]
        if len(baseline_reviews) != 1:
            findings.append(
                f"the PR must contain exactly one formal Baseline review by {expected_reviewer}; "
                f"found {len(baseline_reviews)}"
            )
        first_valid_type = valid_reviews[0][1].review_type
        if first_valid_type != "Baseline":
            findings.append("the first formal cross-review must be Review type: Baseline")
        for _, markers in valid_reviews[1:]:
            if markers.review_type != "Follow-up":
                findings.append(
                    "every formal review after the baseline must be Review type: Follow-up"
                )
                break

    current_reviews = [
        item
        for item in expected_reviews
        if str(item[0].get("commit_id") or "").lower() == head_sha
    ]
    if not current_reviews:
        findings.append(f"{expected_reviewer} has not reviewed the exact current head {head_sha}")
        return GateResult(False, tuple(findings))

    latest_review, latest_markers = current_reviews[-1]
    latest_state = str(latest_review.get("state") or "").upper()
    if latest_markers is None:
        findings.append("the latest exact-head formal review has invalid or missing review markers")
    else:
        if latest_markers.reviewer != expected_reviewer:
            findings.append(
                "the Reviewer marker does not match the opposite agent App identity: "
                f"expected {expected_reviewer}, found {latest_markers.reviewer}"
            )
        if latest_markers.reviewed_head != head_sha:
            findings.append(
                "the Reviewed head marker does not equal the current PR head: "
                f"{latest_markers.reviewed_head} != {head_sha}"
            )
    if latest_state != "APPROVED":
        findings.append(
            f"the latest {expected_reviewer} review on the current head is {latest_state}, not APPROVED"
        )

    return GateResult(not findings, tuple(findings))


def github_get(token: str, repository: str, path: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API failed: HTTP {error.code}: {detail}") from error


def event_pull_request_number(event_path: Path) -> int:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    number = event.get("pull_request", {}).get("number") or event.get("number")
    if not isinstance(number, int) or number < 1:
        raise ValueError("GitHub event does not contain a pull request number")
    return number


def main() -> None:
    token = os.environ.get("GH_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    if not token or not repository or not event_path.is_file():
        raise SystemExit("review gate requires GH_TOKEN, GITHUB_REPOSITORY, and GITHUB_EVENT_PATH")

    number = event_pull_request_number(event_path)
    pull = github_get(token, repository, f"pulls/{number}")
    reviews = github_get(token, repository, f"pulls/{number}/reviews?per_page=100")
    result = evaluate_pull_request(pull, reviews)
    if not result.allowed:
        for finding in result.findings:
            print(f"cross-review gate: {finding}")
        raise SystemExit(1)
    print(f"cross-review gate passed for PR #{number} at {pull['head']['sha']}")


if __name__ == "__main__":
    main()
