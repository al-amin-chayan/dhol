from __future__ import annotations

from pathlib import Path
import sys


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROLLER_DIR))

from review_gate import evaluate_pull_request, parse_review_markers  # noqa: E402


HEAD_ONE = "1" * 40
HEAD_TWO = "2" * 40


def pull(
    *,
    head: str = HEAD_ONE,
    author: str = "app/chayan-codex",
    labels: tuple[str, ...] = ("review:ready-for-ci",),
    draft: bool = False,
) -> dict:
    return {
        "draft": draft,
        "user": {"login": author},
        "base": {"ref": "develop"},
        "head": {"ref": "codex/governance", "sha": head},
        "labels": [{"name": name} for name in (*labels, "area:tooling")],
    }


def review(
    *,
    head: str = HEAD_ONE,
    state: str = "APPROVED",
    review_type: str = "Baseline",
    reviewer: str = "Claude Code",
    login: str = "chayan-claude",
    review_id: int = 1,
) -> dict:
    return {
        "id": review_id,
        "state": state,
        "commit_id": head,
        "submitted_at": f"2026-08-16T00:00:{review_id:02d}Z",
        "user": {"login": login},
        "body": (
            f"Review type: {review_type}\n"
            f"Reviewer: {reviewer}\n"
            f"Reviewed head: {head}\n"
        ),
    }


def test_baseline_approval_from_opposite_agent_passes() -> None:
    result = evaluate_pull_request(pull(), [review()])
    assert result.allowed is True
    assert result.findings == ()


def test_markdown_review_markers_are_accepted() -> None:
    markers = parse_review_markers(
        f"- Review type: **Follow-up**\n- Reviewer: `Claude Code`\n- Reviewed head: `{HEAD_ONE}`\n"
    )
    assert markers is not None
    assert markers.review_type == "Follow-up"
    assert markers.reviewer == "Claude Code"
    assert markers.reviewed_head == HEAD_ONE


def test_follow_up_must_approve_the_new_exact_head() -> None:
    reviews = [
        review(head=HEAD_ONE, state="CHANGES_REQUESTED", review_id=1),
        review(head=HEAD_TWO, review_type="Follow-up", review_id=2),
    ]
    result = evaluate_pull_request(pull(head=HEAD_TWO), reviews)
    assert result.allowed is True


def test_first_formal_review_cannot_be_follow_up() -> None:
    result = evaluate_pull_request(pull(), [review(review_type="Follow-up")])
    assert result.allowed is False
    assert "the first formal cross-review must be Review type: Baseline" in result.findings


def test_second_baseline_is_rejected() -> None:
    reviews = [
        review(head=HEAD_ONE, state="CHANGES_REQUESTED", review_id=1),
        review(head=HEAD_TWO, review_type="Baseline", review_id=2),
    ]
    result = evaluate_pull_request(pull(head=HEAD_TWO), reviews)
    assert result.allowed is False
    assert any("exactly one formal Baseline" in finding for finding in result.findings)
    assert any("every formal review after the baseline" in finding for finding in result.findings)


def test_same_model_review_does_not_satisfy_cross_review() -> None:
    result = evaluate_pull_request(
        pull(),
        [review(reviewer="Codex", login="chayan-codex")],
    )
    assert result.allowed is False
    assert result.findings[-1] == "no formal Claude Code cross-review has been submitted"


def test_latest_exact_head_changes_requested_blocks() -> None:
    reviews = [
        review(review_id=1),
        review(state="CHANGES_REQUESTED", review_type="Follow-up", review_id=2),
    ]
    result = evaluate_pull_request(pull(), reviews)
    assert result.allowed is False
    assert any("CHANGES_REQUESTED, not APPROVED" in finding for finding in result.findings)


def test_reviewed_head_marker_must_match_github_commit() -> None:
    mismatched = review()
    mismatched["body"] = mismatched["body"].replace(HEAD_ONE, HEAD_TWO)
    result = evaluate_pull_request(pull(), [mismatched])
    assert result.allowed is False
    assert any("Reviewed head marker does not equal" in finding for finding in result.findings)


def test_only_ready_for_ci_review_label_is_allowed() -> None:
    result = evaluate_pull_request(
        pull(labels=("review:requested", "review:ready-for-ci")),
        [review()],
    )
    assert result.allowed is False
    assert any("must have only review:ready-for-ci" in finding for finding in result.findings)


def test_area_label_is_required() -> None:
    candidate = pull()
    candidate["labels"] = [{"name": "review:ready-for-ci"}]
    result = evaluate_pull_request(candidate, [review()])
    assert result.allowed is False
    assert "the pull request must have at least one area:* label" in result.findings


def test_blocked_or_decision_labels_cannot_pass() -> None:
    candidate = pull()
    candidate["labels"].append({"name": "decision"})
    result = evaluate_pull_request(candidate, [review()])
    assert result.allowed is False
    assert any("blocked or decision PRs cannot pass" in finding for finding in result.findings)


def test_invalid_earlier_formal_review_cannot_be_skipped() -> None:
    invalid = review(state="CHANGES_REQUESTED", review_id=1)
    invalid["body"] = "No governance markers"
    corrected = review(review_type="Baseline", review_id=2)
    result = evaluate_pull_request(pull(), [invalid, corrected])
    assert result.allowed is False
    assert any("formal review 1 is missing valid" in finding for finding in result.findings)


def test_unknown_pr_author_fails_closed() -> None:
    result = evaluate_pull_request(pull(author="al-amin-chayan"), [review()])
    assert result.allowed is False
    assert any("not a recognized Dholbeat agent App" in finding for finding in result.findings)


def test_main_promotion_must_come_from_develop() -> None:
    candidate = pull()
    candidate["base"]["ref"] = "main"
    result = evaluate_pull_request(candidate, [review()])
    assert result.allowed is False
    assert any("main promotions must come from develop" in finding for finding in result.findings)
