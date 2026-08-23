#!/usr/bin/env python3
"""Normalize and redact a production infrastructure plan into a stable document.

``scripts/infra-plan`` produces evidence a human must be able to read and a
release must be able to pin. Raw Ansible output contains timings, addresses, and
key material, so it can be neither reviewed safely nor hashed reproducibly. This
module turns that output into a deterministic, redacted document whose SHA-256
is the approved plan digest recorded in the release contract.

Nothing here contacts a host. It reads committed manifests plus the captured
transcript on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


TASK_HEADER_RE = re.compile(r"^(?:TASK|RESCUE|HANDLER)\s+\[(?P<name>.+?)\]\s*\*+\s*$")
STATUS_LINE_RE = re.compile(r"^(?P<status>ok|changed|failed|fatal|skipping|unreachable):\s")
RECAP_RE = re.compile(
    r"^(?P<host>\S+)\s*:\s*"
    r"ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+unreachable=(?P<unreachable>\d+)\s+"
    r"failed=(?P<failed>\d+)\s+skipped=(?P<skipped>\d+)\s+rescued=(?P<rescued>\d+)\s+"
    r"ignored=(?P<ignored>\d+)"
)
IPV4_RE = re.compile(r"(?<![\w.])((?:\d{1,3}\.){3}\d{1,3})(?![\w.]|/\d)")
IPV6_RE = re.compile(r"(?<![\w:])((?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4})(?![\w:]|/\d)")
PUBLIC_KEY_BODY_RE = re.compile(
    r"\b(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|sk-ssh-ed25519@openssh\.com)\s+[A-Za-z0-9+/=]{20,}"
)
HIGH_ENTROPY_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{48,}={0,2}(?![A-Za-z0-9+/=])")
HOME_PATH_RE = re.compile(r"(?:/Users|/home)/[^\s\"',:]+")
REDACTED = "<redacted>"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def canonical_digest(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def redact(text: str, literals: list[str]) -> str:
    """Remove operator-local and secret-shaped material from reviewable evidence."""

    redacted = text
    for literal in sorted({item for item in literals if item}, key=len, reverse=True):
        redacted = redacted.replace(literal, REDACTED)
    redacted = PUBLIC_KEY_BODY_RE.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = HOME_PATH_RE.sub(REDACTED, redacted)

    def _mask_v4(match: re.Match[str]) -> str:
        try:
            ipaddress.ip_address(match.group(1))
        except ValueError:
            return match.group(0)
        return "<redacted-address>"

    redacted = IPV4_RE.sub(_mask_v4, redacted)

    def _mask_v6(match: re.Match[str]) -> str:
        try:
            ipaddress.ip_address(match.group(1))
        except ValueError:
            return match.group(0)
        return "<redacted-address>"

    redacted = IPV6_RE.sub(_mask_v6, redacted)
    redacted = HIGH_ENTROPY_RE.sub(REDACTED, redacted)
    return redacted


DIFF_START_RE = re.compile(r"^(?:--- before|\+\+\+ after|@@ )")
DIFF_BODY_RE = re.compile(r"^[-+ @\\]")


def summarize_transcript(text: str) -> dict[str, Any]:
    """Reduce an Ansible transcript to the outcomes and diffs that must be reviewed.

    Task names and counts alone are not an authorization: two different file,
    package, or firewall deltas can hide under the same changed task. Every
    ``--diff`` hunk is therefore captured verbatim (already redacted by the
    caller) and bound to its task, so a changed host cannot reproduce an earlier
    plan digest.
    """

    current_task = ""
    changed_tasks: list[str] = []
    failed_tasks: list[str] = []
    unreachable_tasks: list[str] = []
    diffs: list[dict[str, Any]] = []
    diff_lines: list[str] = []
    in_diff = False

    def flush_diff() -> None:
        nonlocal diff_lines, in_diff
        if diff_lines:
            diffs.append({"task": current_task, "hunk": list(diff_lines)})
        diff_lines = []
        in_diff = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        header = TASK_HEADER_RE.match(stripped)
        if header is not None:
            flush_diff()
            current_task = header.group("name")
            continue

        if DIFF_START_RE.match(line):
            if not in_diff:
                flush_diff()
            in_diff = True
            diff_lines.append(line)
            continue
        if in_diff:
            if stripped and DIFF_BODY_RE.match(line):
                diff_lines.append(line)
                continue
            flush_diff()

        status = STATUS_LINE_RE.match(stripped)
        if status is None or not current_task:
            continue
        outcome = status.group("status")
        if outcome == "changed" and current_task not in changed_tasks:
            changed_tasks.append(current_task)
        elif outcome in {"failed", "fatal"} and current_task not in failed_tasks:
            failed_tasks.append(current_task)
        elif outcome == "unreachable" and current_task not in unreachable_tasks:
            unreachable_tasks.append(current_task)
    flush_diff()

    recap: dict[str, int] = {}
    saw_recap = False
    for raw_line in text.splitlines():
        match = RECAP_RE.match(raw_line.strip())
        if match is None:
            continue
        saw_recap = True
        for field in ("ok", "changed", "unreachable", "failed", "skipped", "rescued", "ignored"):
            recap[field] = recap.get(field, 0) + int(match.group(field))
    return {
        "recap": recap,
        "recap_present": saw_recap,
        "changed_tasks": changed_tasks,
        "failed_tasks": failed_tasks,
        "unreachable_tasks": unreachable_tasks,
        "diffs": sorted(diffs, key=lambda entry: (entry["task"], "\n".join(entry["hunk"]))),
    }


def check_findings(summary: dict[str, Any], exit_status: int, plan_kind: str) -> list[str]:
    """Reject a plan that cannot authorize anything.

    A nonzero run, an unreachable host, a failed task, or a missing recap all
    mean the reviewed delta is unknown. Approving such a plan would let a
    repeatable failure reach founder confirmation.
    """

    findings: list[str] = []
    if exit_status != 0:
        findings.append(f"the {plan_kind} run exited {exit_status}; a failed plan authorizes nothing")
    if not summary["recap_present"]:
        findings.append("the transcript carries no play recap; the run did not complete")
    if summary["unreachable_tasks"] or summary["recap"].get("unreachable", 0):
        findings.append("the host was unreachable during the run")
    if summary["failed_tasks"] or summary["recap"].get("failed", 0):
        findings.append(f"tasks failed during the run: {summary['failed_tasks']}")
    return findings


def host_secret_scope(root: Path, host_id: str) -> list[dict[str, Any]]:
    catalog = load_yaml(root / "infra/secrets/catalog.yml")
    scope: list[dict[str, Any]] = []
    for secret in (catalog or {}).get("secrets", []):
        target = secret.get("target", {})
        if target.get("kind") != "host-file" or target.get("host_id") != host_id:
            continue
        sops_file = secret["sops_file"]
        scope.append(
            {
                "id": secret["id"],
                "sops_file": sops_file,
                "state": "committed" if (root / sops_file).is_file() else "not-provisioned",
            }
        )
    return sorted(scope, key=lambda item: item["id"])


def host_service_ids(root: Path, host_id: str) -> list[str]:
    manifest = load_yaml(root / "infra/inventories/production/hosts.yml")
    for host in (manifest or {}).get("hosts", []):
        if host.get("id") == host_id:
            return sorted(host.get("service_ids", []))
    return []


def compose_scope(root: Path, host_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Map committed Compose stacks to the limited host through the service registry."""

    registry = load_yaml(root / "infra/services/registry.yml") or {}
    services = {service["id"]: service for service in registry.get("services", [])}
    findings: list[str] = []
    stacks: list[dict[str, Any]] = []
    for compose_path in sorted(root.glob("stack/*/compose.y*ml")):
        stack_id = compose_path.parent.name
        owners = [
            service_id
            for service_id, service in services.items()
            if service.get("stack_id") == stack_id or service_id == stack_id
        ]
        if not owners:
            findings.append(
                f"stack/{stack_id}: Compose stack has no owning entry in infra/services/registry.yml"
            )
            continue
        host_ids = {services[service_id].get("host_id") for service_id in owners}
        if host_ids == {host_id}:
            stacks.append({"stack_id": stack_id, "service_ids": sorted(owners)})
    return stacks, findings


def opentofu_scope(root: Path) -> dict[str, Any]:
    tofu_root = root / "infra/tofu"
    if not tofu_root.is_dir():
        return {
            "state": "absent",
            "reason": "no OpenTofu declarations are committed yet; the external control plane is WP-06",
        }
    return {
        "state": "present",
        "reason": "committed OpenTofu declarations require the WP-06 plan adapter before apply",
    }


def build_plan(arguments: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    root = arguments.root.resolve()
    baseline = load_yaml(root / f"infra/inventories/production/baseline/{arguments.limit}.yml")
    transcript = arguments.ansible_log.read_text(encoding="utf-8", errors="replace")
    redacted_transcript = redact(transcript, arguments.redact)
    summary = summarize_transcript(redacted_transcript)
    stacks, findings = compose_scope(root, arguments.limit)

    compose_renders = {}
    for entry in arguments.compose_render:
        stack_id, _, digest = entry.partition("=")
        compose_renders[stack_id] = digest
    for stack in stacks:
        stack["config_sha256"] = compose_renders.get(stack["stack_id"], "")
        if not stack["config_sha256"]:
            findings.append(
                f"stack/{stack['stack_id']}: Compose configuration was not rendered for this plan"
            )

    contract_payload = json.loads(arguments.contract.read_text(encoding="utf-8"))
    findings.extend(check_findings(summary, arguments.ansible_status, arguments.plan_kind))

    tofu = opentofu_scope(root)
    if tofu["state"] == "present":
        findings.append(
            "infra/tofu: committed OpenTofu declarations exist but no plan adapter is "
            "implemented; the external-state delta cannot be bound, so this plan "
            "authorizes nothing (WP-06)"
        )

    plan = {
        "schema_version": 1,
        "document_type": "infra-plan",
        "target_host_id": arguments.limit,
        "target_host_role": baseline["host_role"],
        "target_environment": baseline["target_environment"],
        "plan_kind": arguments.plan_kind,
        "planned_playbook": arguments.playbook,
        "applied_playbook": arguments.applied_playbook,
        "stage": arguments.stage,
        "reviewed_input": {
            "git_commit": arguments.git_commit,
            "worktree_clean": arguments.worktree_clean,
            "reachable_from_main": arguments.reachable_from_main,
            "rehearsal": arguments.rehearsal,
            "toolchain_lock_sha256": sha256_file(root / "toolchain.lock.yml"),
            "controller_source_lock_sha256": arguments.controller_source_lock,
            "controller_image_id": arguments.controller_image_id,
        },
        "identity": {
            "inventory_manifest_sha256": sha256_file(
                root / "infra/inventories/production/hosts.yml"
            ),
            "host_baseline_sha256": sha256_file(
                root / f"infra/inventories/production/baseline/{arguments.limit}.yml"
            ),
            "baseline_contract_sha256": canonical_digest(contract_payload),
            "declared_service_ids": host_service_ids(root, arguments.limit),
        },
        "secrets": {
            "host_scope": host_secret_scope(root, arguments.limit),
            "sops_canary": arguments.sops_canary,
            "decrypted_to_disk": False,
        },
        "compose_stacks": stacks,
        "opentofu": tofu,
        "ansible_run": {
            "mode": arguments.plan_kind,
            "exit_status": arguments.ansible_status,
            "recap": summary["recap"],
            "changed_tasks": summary["changed_tasks"],
            "failed_tasks": summary["failed_tasks"],
            "unreachable_tasks": summary["unreachable_tasks"],
            "diffs": summary["diffs"],
            "transcript_sha256": sha256_text(
                arguments.ansible_log.read_text(encoding="utf-8", errors="replace")
            ),
        },
        "cost": {
            "monthly_usd": baseline["provider"]["monthly_cost_usd"],
            "provider": baseline["provider"]["vendor"],
            "plan": baseline["provider"]["plan"],
        },
    }
    return plan, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render", help="render the redacted plan document")
    render.add_argument("--root", type=Path, required=True)
    render.add_argument("--limit", required=True)
    render.add_argument("--playbook", required=True)
    render.add_argument("--applied-playbook", required=True)
    render.add_argument("--plan-kind", required=True, choices=["bootstrap-preflight", "check-diff"])
    render.add_argument("--stage", required=True)
    render.add_argument("--git-commit", required=True)
    render.add_argument("--worktree-clean", type=lambda value: value == "true", required=True)
    render.add_argument("--reachable-from-main", type=lambda value: value == "true", required=True)
    render.add_argument("--rehearsal", type=lambda value: value == "true", required=True)
    render.add_argument("--controller-image-id", required=True)
    render.add_argument("--controller-source-lock", required=True)
    render.add_argument("--contract", type=Path, required=True)
    render.add_argument("--ansible-log", type=Path, required=True)
    render.add_argument("--ansible-status", type=int, required=True)
    render.add_argument("--sops-canary", required=True)
    render.add_argument("--compose-render", action="append", default=[])
    render.add_argument("--redact", action="append", default=[])

    scope = subparsers.add_parser(
        "compose-scope", help="list the Compose stacks this host owns, failing on an unowned stack"
    )
    scope.add_argument("--root", type=Path, required=True)
    scope.add_argument("--limit", required=True)

    scrub = subparsers.add_parser("redact", help="redact a captured transcript in place")
    scrub.add_argument("--redact", action="append", default=[])

    arguments = parser.parse_args()

    if arguments.command == "compose-scope":
        stacks, findings = compose_scope(arguments.root.resolve(), arguments.limit)
        if findings:
            for finding in findings:
                print(f"plan failure: {finding}", file=sys.stderr)
            raise SystemExit(1)
        for stack in stacks:
            print(stack["stack_id"])
        return

    if arguments.command == "redact":
        sys.stdout.write(redact(sys.stdin.read(), arguments.redact))
        return

    plan, findings = build_plan(arguments)
    if findings:
        for finding in findings:
            print(f"plan failure: {finding}", file=sys.stderr)
        raise SystemExit(1)
    body = yaml.safe_dump(plan, default_flow_style=False, sort_keys=True)
    sys.stdout.write(body)


if __name__ == "__main__":
    main()
