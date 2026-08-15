#!/usr/bin/env python3
"""Enforce Dholbeat's develop-first pull request route in canonical CI."""

from __future__ import annotations

import os


def validate_pull_request_route(
    event_name: str,
    base_ref: str,
    head_ref: str,
    github_actions: bool = False,
) -> list[str]:
    if github_actions and not event_name:
        return ["GitHub Actions did not propagate GITHUB_EVENT_NAME into the controller"]
    if event_name not in {"pull_request", "pull_request_target"}:
        return []
    if not base_ref or not head_ref:
        return ["pull request event is missing GITHUB_BASE_REF or GITHUB_HEAD_REF"]
    if base_ref == "develop":
        return []
    if base_ref == "main":
        if head_ref == "develop":
            return []
        return [f"pull requests into main must come from develop, not {head_ref}"]
    return [f"pull request base must be develop or main, not {base_ref}"]


def main() -> None:
    findings = validate_pull_request_route(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("GITHUB_BASE_REF", ""),
        os.environ.get("GITHUB_HEAD_REF", ""),
        os.environ.get("GITHUB_ACTIONS", "").lower() == "true",
    )
    if findings:
        for finding in findings:
            print(f"branch policy failure: {finding}")
        raise SystemExit(1)
    print("branch route policy passed")


if __name__ == "__main__":
    main()
