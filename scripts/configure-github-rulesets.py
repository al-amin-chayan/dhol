#!/usr/bin/env python3
"""Idempotently apply Dholbeat's develop-first GitHub repository policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_HELPER = REPO_ROOT / "scripts/github-app-token.sh"
DEFAULT_REPOSITORY = "al-amin-chayan/dhol"
SETTINGS_FILE = REPO_ROOT / ".github/repository-settings.json"
RULESET_FILES = (
    REPO_ROOT / ".github/rulesets/develop.json",
    REPO_ROOT / ".github/rulesets/main.json",
)


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"GitHub API failed: HTTP {status}: {detail}")
        self.status = status


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def desired_configuration() -> dict[str, Any]:
    return {
        "repository_settings": load_json(SETTINGS_FILE),
        "rulesets": [load_json(path) for path in RULESET_FILES],
    }


def mint_token() -> str:
    result = subprocess.run(
        [TOKEN_HELPER],
        check=True,
        text=True,
        capture_output=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("GitHub App token helper returned an empty token")
    return token


def github_request(
    token: str,
    repository: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    url = f"https://api.github.com/repos/{repository}"
    if path:
        url = f"{url}/{path.lstrip('/')}"
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise GitHubApiError(error.code, detail) from error
    if not response_body:
        return None
    return json.loads(response_body)


def ensure_develop(token: str, repository: str) -> None:
    try:
        github_request(token, repository, "GET", "git/ref/heads/develop")
        print("unchanged: refs/heads/develop")
        return
    except GitHubApiError as error:
        if error.status != 404:
            raise
    main_ref = github_request(token, repository, "GET", "git/ref/heads/main")
    github_request(
        token,
        repository,
        "POST",
        "git/refs",
        {"ref": "refs/heads/develop", "sha": main_ref["object"]["sha"]},
    )
    print("created: refs/heads/develop from main")


def normalized_ruleset(value: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        key: value.get(key)
        for key in ("name", "target", "enforcement", "bypass_actors", "conditions")
    }
    normalized_rules: list[dict[str, Any]] = []
    for rule in value.get("rules", []):
        normalized_rule = {"type": rule.get("type")}
        if "parameters" in rule:
            parameters = dict(rule["parameters"])
            if parameters.get("required_reviewers") == []:
                parameters.pop("required_reviewers")
            normalized_rule["parameters"] = parameters
        normalized_rules.append(normalized_rule)
    normalized["rules"] = normalized_rules
    return normalized


def upsert_rulesets(token: str, repository: str, rulesets: list[dict[str, Any]]) -> None:
    existing_payload = github_request(token, repository, "GET", "rulesets")
    existing: dict[str, list[int]] = {}
    for ruleset in existing_payload:
        existing.setdefault(ruleset["name"], []).append(ruleset["id"])
    for desired in rulesets:
        matches = existing.get(desired["name"], [])
        if len(matches) > 1:
            raise RuntimeError(f"multiple live rulesets named {desired['name']!r}")
        if matches:
            live = github_request(token, repository, "GET", f"rulesets/{matches[0]}")
            if normalized_ruleset(live) == normalized_ruleset(desired):
                print(f"unchanged: {desired['name']}")
                continue
            github_request(token, repository, "PUT", f"rulesets/{matches[0]}", desired)
            print(f"updated: {desired['name']}")
        else:
            github_request(token, repository, "POST", "rulesets", desired)
            print(f"created: {desired['name']}")


def apply(repository: str, configuration: dict[str, Any]) -> None:
    token = mint_token()
    ensure_develop(token, repository)
    repository_settings = configuration["repository_settings"]
    live_repository = github_request(token, repository, "GET", "")
    if all(live_repository.get(key) == value for key, value in repository_settings.items()):
        print("unchanged: repository settings")
    else:
        github_request(token, repository, "PATCH", "", repository_settings)
        print("updated: repository settings")
    upsert_rulesets(token, repository, configuration["rulesets"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    configuration = desired_configuration()
    if not args.apply:
        print(json.dumps(configuration, indent=2, sort_keys=True))
        return
    apply(args.repo, configuration)


if __name__ == "__main__":
    main()
