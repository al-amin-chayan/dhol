"""Contract tests for the DG-01 publisher evaluation harness.

The live harness needs Docker and two large images, so CI proves the parts a
wrong answer would silently corrupt: the pins, the capacity arithmetic, the
verdict rules, and the guarantee that fixture credentials never reach evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))

import probe  # noqa: E402
import resources  # noqa: E402
import restore_verdict  # noqa: E402
import verdict  # noqa: E402

IMAGE_DIGEST = "@sha256:"


@pytest.fixture(scope="module")
def candidates() -> dict:
    return yaml.safe_load((HARNESS / "candidates.yml").read_text(encoding="utf-8"))


def test_every_pinned_image_carries_a_digest(candidates: dict) -> None:
    for candidate in candidates["candidates"]:
        image = candidate.get("image")
        if image is None:
            assert not candidate["evaluable"], f"{candidate['id']} is evaluable but pins no image"
            continue
        assert IMAGE_DIGEST in image, f"{candidate['id']} image is not digest-pinned"


def test_a_paid_edition_is_never_marked_evaluable(candidates: dict) -> None:
    for candidate in candidates["candidates"]:
        if candidate.get("purchase_required"):
            assert candidate["evaluable"] is False
            assert candidate.get("not_evaluable_reason")


def test_every_evaluable_candidate_has_a_compose_file(candidates: dict) -> None:
    for candidate in candidates["candidates"]:
        if not candidate["evaluable"]:
            continue
        assert (HARNESS / candidate["compose"]).is_file()


def test_pins_refuses_an_unknown_candidate() -> None:
    completed = subprocess.run(
        [sys.executable, str(HARNESS / "pins.py"), "--root", str(HARNESS), "--candidate", "nope", "--field", "image"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "unknown candidate" in completed.stderr


def test_pins_reports_a_paid_edition_as_not_evaluable() -> None:
    completed = subprocess.run(
        [sys.executable, str(HARNESS / "pins.py"), "--root", str(HARNESS), "--candidate", "mixpost-pro", "--field", "evaluable"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "false"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("512MiB", 512.0), ("1.5GiB", 1536.0), ("128KiB", 0.125), ("0B", 0.0)],
)
def test_size_parsing(value: str, expected: float) -> None:
    assert resources.to_mib(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", ["", "512", "512 parsecs", "MiB"])
def test_size_parsing_refuses_nonsense(value: str) -> None:
    with pytest.raises(ValueError):
        resources.to_mib(value)


def test_blank_lines_separate_sampling_rounds() -> None:
    lines = [
        "app|100MiB / 6GiB",
        "db|200MiB / 6GiB",
        "",
        "app|300MiB / 6GiB",
        "db|400MiB / 6GiB",
        "",
    ]
    samples = resources.parse_samples(lines)
    assert [sample["total_mib"] for sample in samples] == [300.0, 700.0]
    assert [sample["containers"] for sample in samples] == [2, 2]


def test_capacity_summary_flags_a_ram_breach() -> None:
    samples = resources.parse_samples(["app|5GiB / 6GiB", ""])
    summary = resources.summarise(samples, disk_mib=100.0, image_mib=100.0)
    assert summary["peak_ram_within_budget"] is False
    assert summary["topology_within_steady_budget"] is True


def test_the_lowest_sample_is_reported_as_a_minimum_not_an_idle_figure() -> None:
    samples = resources.parse_samples(["app|100MiB / 6GiB", "", "app|900MiB / 6GiB", ""])
    summary = resources.summarise(samples, disk_mib=0.0, image_mib=0.0)
    assert summary["min_ram_mib"] == pytest.approx(100.0)
    assert summary["peak_ram_mib"] == pytest.approx(900.0)
    assert "idle_ram_mib" not in summary


def test_capacity_summary_flags_a_disk_breach() -> None:
    samples = resources.parse_samples(["app|1GiB / 6GiB", ""])
    summary = resources.summarise(samples, disk_mib=24 * 1024.0, image_mib=1024.0)
    assert summary["topology_within_steady_budget"] is False


def test_update_headroom_is_reported_unmeasured_not_passing() -> None:
    # WP-13's 8 GB update headroom is a property of a real 30 GB host while two
    # image sets coexist. Subtracting this topology's footprint from 30 GiB is
    # arithmetic, not a measurement, and must never read as a passing gate.
    summary = resources.summarise(resources.parse_samples(["app|1GiB / 6GiB", ""]), 100.0, 100.0)
    assert isinstance(summary["update_headroom"], str)
    assert summary["update_headroom"].startswith("unmeasured")
    assert "update_headroom_within_budget" not in summary
    assert "update_headroom_mib" not in summary


def test_the_verdict_never_gates_on_an_unmeasured_budget() -> None:
    document = verdict.build(
        _checks(_all_passing()), {"drills": []}, _healthy_resources(), "v1.0.0"
    )
    assert "update_headroom_within_budget" not in document["capacity_breaches"]
    assert document["unmeasured_capacity"]["update_headroom"].startswith("unmeasured")
    assert document["verdict"] == "viable"


def _checks(results: dict[str, str]) -> dict:
    return {
        "candidate": "fixture",
        "image": "example/fixture@sha256:" + "0" * 64,
        "variant": "default",
        "platform": "linux/arm64",
        "capabilities": {},
        "checks": [
            {"id": check_id, "requirement": "fixture", "result": result, "detail": "", "evidence": {}}
            for check_id, result in results.items()
        ],
    }


def _all_passing() -> dict[str, str]:
    return {check_id: "pass" for check_id, _ in probe.MATRIX}


def test_a_measured_cold_start_is_carried_into_the_summary() -> None:
    samples = resources.parse_samples(["app|1GiB / 6GiB", ""])
    assert resources.summarise(samples, 0.0, 0.0, 137.4)["startup_seconds"] == pytest.approx(137.4)
    assert resources.summarise(samples, 0.0, 0.0)["startup_seconds"] is None


def _healthy_resources() -> dict:
    return resources.summarise(resources.parse_samples(["app|1GiB / 6GiB", ""]), 1024.0, 1024.0)


def test_a_missing_isolation_check_disqualifies() -> None:
    results = _all_passing()
    del results["authz.cross-tenant-write-rejected"]
    document = verdict.build(_checks(results), {"drills": []}, _healthy_resources(), "v1.0.0")
    assert document["verdict"] == "disqualified"
    assert "authz.cross-tenant-write-rejected" in document["disqualifying_checks"]


def test_an_unsupported_machine_api_disqualifies() -> None:
    results = _all_passing()
    results["api.machine-credential"] = "unsupported"
    document = verdict.build(_checks(results), {"drills": []}, _healthy_resources(), "v1.0.0")
    assert document["verdict"] == "disqualified"


def test_a_failed_drill_is_a_finding_not_a_disqualification() -> None:
    drills = {"drills": [{"id": "backup.dump-restore", "result": "fail", "detail": ""}]}
    document = verdict.build(_checks(_all_passing()), drills, _healthy_resources(), "v1.0.0")
    assert document["verdict"] == "viable-with-findings"
    assert document["failed_drills"] == ["backup.dump-restore"]


def test_a_capacity_breach_is_reported_separately() -> None:
    over_budget = resources.summarise(resources.parse_samples(["app|5GiB / 6GiB", ""]), 1024.0, 1024.0)
    document = verdict.build(_checks(_all_passing()), {"drills": []}, over_budget, "v1.0.0")
    assert document["verdict"] == "viable-over-budget"
    assert document["capacity_breaches"] == ["peak_ram_within_budget"]


def test_a_clean_candidate_is_never_marked_selected() -> None:
    document = verdict.build(_checks(_all_passing()), {"drills": []}, _healthy_resources(), "v1.0.0")
    assert document["verdict"] == "viable"


def test_the_recorder_rejects_a_check_outside_the_matrix() -> None:
    recorder = probe.Recorder()
    with pytest.raises(KeyError):
        recorder.record("authz.invented", probe.PASS, "")


def test_the_recorder_rejects_an_unknown_result() -> None:
    recorder = probe.Recorder()
    with pytest.raises(ValueError):
        recorder.record("posts.list", "probably", "")


def test_the_recorder_reports_an_incomplete_matrix() -> None:
    recorder = probe.Recorder()
    recorder.record("posts.list", probe.PASS, "")
    unrecorded = recorder.unrecorded()
    assert "posts.list" not in unrecorded
    assert len(unrecorded) == len(probe.MATRIX) - 1


def test_a_credential_is_only_ever_recorded_as_a_digest() -> None:
    secret = "dg01-fixture-super-secret-value"
    rendered = probe.digest(secret)
    assert secret not in rendered
    assert rendered.startswith("sha256:")
    assert len(rendered) == len("sha256:") + 16


def test_evidence_carries_no_fixture_credential(tmp_path: Path) -> None:
    secret = "dg01-fixture-super-secret-value"
    recorder = probe.Recorder()
    recorder.record("api.machine-credential", probe.PASS, "issued", credential=probe.digest(secret))
    document = json.dumps({"checks": recorder.as_list()})
    assert secret not in document


def _compose_documents() -> list[tuple[str, dict]]:
    documents = []
    for path in sorted((HARNESS / "compose").glob("*.compose.yml")):
        documents.append((path.name, yaml.safe_load(path.read_text(encoding="utf-8"))))
    assert documents, "no evaluation Compose files were found"
    return documents


def test_every_published_port_is_bound_to_loopback() -> None:
    for name, document in _compose_documents():
        for service, definition in document["services"].items():
            for published in definition.get("ports", []):
                assert str(published).startswith("127.0.0.1:"), (
                    f"{name}: {service} publishes {published} beyond loopback"
                )


def test_no_state_service_publishes_a_port() -> None:
    for name, document in _compose_documents():
        for service, definition in document["services"].items():
            if not any(token in service for token in ("postgres", "redis", "mysql", "elasticsearch")):
                continue
            assert not definition.get("ports"), f"{name}: {service} must not publish a port"


def test_no_evaluation_service_restarts_itself() -> None:
    # A disposable evaluation must die when it fails; a restarting container
    # hides a crash loop behind a healthy-looking stack.
    for name, document in _compose_documents():
        for service, definition in document["services"].items():
            assert definition.get("restart", "no") == "no", f"{name}: {service} sets a restart policy"


def test_every_compose_image_is_digest_pinned() -> None:
    for name, document in _compose_documents():
        for service, definition in document["services"].items():
            image = definition["image"]
            assert IMAGE_DIGEST in image, f"{name}: {service} image is not digest-pinned"


# --- DG01-01: the harness must work on the operator's default shell ----------


def test_the_runner_parses_under_bash_3_2() -> None:
    """macOS ships Bash 3.2 as /bin/bash, and the runbook documents a plain
    `run.sh` invocation. Empty-array expansion under `set -u` aborts there, so a
    variant with no Compose profile would die before Compose ran."""
    bash = Path("/bin/bash")
    if not bash.exists():  # pragma: no cover - non-macOS CI
        pytest.skip("no /bin/bash on this platform")
    completed = subprocess.run(
        [str(bash), "-n", str(HARNESS / "run.sh")], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_an_empty_profile_list_survives_nounset() -> None:
    bash = Path("/bin/bash")
    if not bash.exists():  # pragma: no cover - non-macOS CI
        pytest.skip("no /bin/bash on this platform")
    script = (
        'set -euo pipefail\n'
        'PROFILES=""\n'
        'PROFILE_ARGS=""\n'
        'for p in $PROFILES; do PROFILE_ARGS="$PROFILE_ARGS --profile $p"; done\n'
        'printf "[%s]" "$PROFILE_ARGS"\n'
    )
    completed = subprocess.run([str(bash), "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "[]"


# --- DG01-03: the restore drill must judge behaviour, not row counts ---------

RESTORED_OK = {
    "session_restored": True,
    "api_credential_restored": True,
    "own_channel_restored": True,
    "tenant_boundary_restored": True,
    # A restore that returns every row but loses the pending scheduled job has
    # not restored the publisher: at v2.23.0 the recovery workflow only sweeps
    # queued posts whose publish time is already past, so a future job can be
    # dropped or re-timed rather than reconstructed.
    "pending_post_restored": True,
    "pending_post_tenant_correct": True,
    "pending_post_time_preserved": True,
    # The row must still be queued for sending, and the scheduler must still
    # hold the workflow that sends it. A restored DRAFT, or a QUEUE row with no
    # workflow behind it, is a post that never fires at its time.
    "pending_post_state": "QUEUE",
    "workflow_execution_restored": True,
    # Holding the workflow is not the same as being able to manage it: Postiz
    # finds a scheduled post's workflow through a Temporal list query, and list
    # queries are served by the Visibility store the rebuild empties.
    "pending_post_manageable": True,
    # Postiz reports a successful cancel whether or not it found and terminated
    # the workflow, and Temporal keeps closed executions — so the scheduler is
    # asked directly, and the lookup the publisher depends on must return it.
    "workflow_terminated_after_cancel": True,
    "visibility_lists_workflow": True,
}


def test_a_clean_rebuild_and_restore_passes() -> None:
    result, _ = restore_verdict.judge(RESTORED_OK, "0", "3", "3", "postiz")
    assert result == "pass"


def test_a_database_that_was_not_rebuilt_empty_fails() -> None:
    result, detail = restore_verdict.judge(RESTORED_OK, "42", "3", "3", "postiz")
    assert result == "fail"
    assert "not empty" in detail


# `pending_post_state` is a string, not a behaviour flag — the verdict derives
# `pending_post_still_queued` from it, and its own tests below cover that.
@pytest.mark.parametrize(
    "missing", sorted(k for k, v in RESTORED_OK.items() if isinstance(v, bool))
)
def test_rows_returning_without_working_behaviour_fails(missing: str) -> None:
    # The exact false pass a count-only drill would report: every row is back,
    # but the application cannot use the restored state.
    results = dict(RESTORED_OK, **{missing: False})
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert missing in detail


def test_a_restore_that_exposes_another_project_fails() -> None:
    results = dict(RESTORED_OK, foreign_channel_visible=True)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "another project" in detail


def test_a_missing_restore_probe_result_fails_closed() -> None:
    result, _ = restore_verdict.judge(None, "0", "3", "3", "postiz")
    assert result == "fail"


def test_mixpost_is_not_required_to_restore_a_boundary_it_lacks() -> None:
    result, _ = restore_verdict.judge(
        {"login_restored": True, "label_restored": True}, "0", "3", "3", "mixpost-lite"
    )
    assert result == "pass"


# --- DG01-01: an interrupted run must never report success -------------------

BASH_3_2 = Path("/bin/bash")


def _extract_shell_function(name: str) -> str:
    """Lift one function out of run.sh so the real code is what gets tested."""
    source = (HARNESS / "run.sh").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(source) if line.startswith(f"{name}() {{"))
    depth = 0
    for index in range(start, len(source)):
        depth += source[index].count("{") - source[index].count("}")
        if depth == 0:
            return "\n".join(source[start : index + 1])
    raise AssertionError(f"unterminated function {name}")


def _run_bash(script: str) -> subprocess.CompletedProcess:
    if not BASH_3_2.exists():  # pragma: no cover - non-macOS CI
        pytest.skip("no /bin/bash on this platform")
    return subprocess.run([str(BASH_3_2), "-c", script], capture_output=True, text=True, check=False)


TRAP_HARNESS = """
set -euo pipefail
SIGNAL_STATUS=""
on_signal() { SIGNAL_STATUS="$1"; trap - INT TERM HUP; exit "$SIGNAL_STATUS"; }
cleanup() {
  status=$?
  trap - EXIT INT TERM HUP
  [ -z "$SIGNAL_STATUS" ] || status="$SIGNAL_STATUS"
  echo "cleanup:$status"
  exit "$status"
}
trap cleanup EXIT
trap 'on_signal 130' INT
trap 'on_signal 143' TERM
trap 'on_signal 129' HUP
true
kill -%(signal)s $$
sleep 5
"""


@pytest.mark.parametrize(("signal", "status"), [("INT", 130), ("TERM", 143), ("HUP", 129)])
def test_a_signal_makes_an_interrupted_run_exit_nonzero(signal: str, status: int) -> None:
    # `true` runs first so $? is 0 when the signal lands — the exact shape that
    # previously let an interrupted run destroy its stack and report success.
    completed = _run_bash(TRAP_HARNESS % {"signal": signal})
    assert completed.returncode == status
    assert f"cleanup:{status}" in completed.stdout
    assert completed.stdout.count("cleanup:") == 1, "cleanup must not be re-entered"


def test_the_runner_installs_a_distinct_handler_for_every_signal() -> None:
    source = (HARNESS / "run.sh").read_text(encoding="utf-8")
    for signal, status in (("INT", 130), ("TERM", 143), ("HUP", 129)):
        assert f"trap 'on_signal {status}' {signal}" in source
    assert "trap cleanup EXIT\n" in source, "cleanup must remain the single EXIT path"


# --- DG01-01: teardown failure and survivors must fail the run ---------------


def test_a_failed_teardown_fails_the_run() -> None:
    teardown = _extract_shell_function("teardown")
    script = f"""
set -uo pipefail
PROJECT=dg01-test
TEMP_ROOT=$(mktemp -d)
compose() {{ return 1; }}
docker() {{ :; }}
{teardown}
if teardown >/dev/null 2>&1; then echo "returned-zero"; else echo "returned-nonzero"; fi
rm -rf "$TEMP_ROOT"
"""
    completed = _run_bash(script)
    assert "returned-nonzero" in completed.stdout, completed.stderr


def test_surviving_resources_fail_the_run() -> None:
    teardown = _extract_shell_function("teardown")
    # compose down succeeds, but a labelled container is still there afterwards.
    script = f"""
set -uo pipefail
PROJECT=dg01-test
TEMP_ROOT=$(mktemp -d)
compose() {{ return 0; }}
docker() {{
  case "$*" in
    *"ps --all"*) echo deadbeef ;;
    *) ;;
  esac
}}
{teardown}
if teardown >/dev/null 2>&1; then echo "returned-zero"; else echo "returned-nonzero"; fi
rm -rf "$TEMP_ROOT"
"""
    completed = _run_bash(script)
    assert "returned-nonzero" in completed.stdout, completed.stderr


# --- DG01-02: only the pinned registration-disabled outcome counts -----------


def _lock_verdict(status: str, body: str) -> str:
    function = _extract_shell_function("registration_lock_verdict")
    script = f"""
set -uo pipefail
BODY=$(mktemp)
printf '%s' {json.dumps(body)} > "$BODY"
{function}
registration_lock_verdict {json.dumps(status)} "$BODY" 'Registration is disabled' 401
rm -f "$BODY"
"""
    completed = _run_bash(script)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.split("|", 1)[0].strip()


def test_the_pinned_disabled_registration_response_passes() -> None:
    assert _lock_verdict("400", "Registration is disabled") == "pass"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        ("200", "ok"),                              # registration still open
        ("400", "email must be an email"),          # ordinary DTO validation
        ("400", ""),                                # bare 400, no marker
        ("401", "Unauthorized"),                    # auth surface refusing
        ("403", "Forbidden"),
        ("404", "Cannot POST /auth/register"),      # route absent, not closed
        ("429", "Too Many Requests"),               # rate limited
        ("502", "Bad Gateway"),                     # outage
    ],
)
def test_anything_but_the_pinned_outcome_fails(status: str, body: str) -> None:
    assert _lock_verdict(status, body) == "fail"


def test_a_restore_that_loses_the_pending_post_fails() -> None:
    results = dict(RESTORED_OK, pending_post_restored=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "pending_post_restored" in detail


def test_a_restore_that_re_times_the_pending_post_fails() -> None:
    # The row came back and the tenant is right, but the scheduled instant
    # moved. Publishing at the wrong time is not a successful restore.
    results = dict(RESTORED_OK, pending_post_time_preserved=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "pending_post_time_preserved" in detail


def test_a_restore_that_reassigns_the_pending_post_fails() -> None:
    results = dict(RESTORED_OK, pending_post_tenant_correct=False)
    assert restore_verdict.judge(results, "0", "3", "3", "postiz")[0] == "fail"


# --- DG01-02: an unproven control must not yield `viable` --------------------


def _machine_api_checks(results: dict[str, str]) -> dict:
    document = _checks(results)
    document["capabilities"] = {"machine_api": "/public/v1"}
    return document


@pytest.mark.parametrize(
    "check_id",
    ["posts.cancel", "posts.list", "authz.rotated-credential-rejected", "authz.cross-tenant-read-rejected"],
)
def test_an_unsupported_control_on_a_capable_edition_blocks_viable(check_id: str) -> None:
    # probe.py records UNSUPPORTED when a positive control fails, which is
    # right — but an edition that has the surface must not then be called
    # viable just because nothing was marked fail.
    results = dict(_all_passing(), **{check_id: "unsupported"})
    document = verdict.build(_machine_api_checks(results), {"drills": []}, _healthy_resources(), "v1.0.0")
    assert document["verdict"] != "viable"
    assert check_id in document["unproven_checks"]


def test_a_capable_edition_with_every_control_proven_is_viable() -> None:
    document = verdict.build(
        _machine_api_checks(_all_passing()), {"drills": []}, _healthy_resources(), "v1.0.0"
    )
    assert document["verdict"] == "viable"
    assert document["unproven_checks"] == []


def test_an_edition_without_the_surface_is_not_penalised_for_lacking_it() -> None:
    # Mixpost Lite's checks are legitimately unsupported; it is disqualified on
    # capability, and must not additionally be reported as having unproven
    # controls it never had.
    results = {check_id: "unsupported" for check_id, _ in probe.MATRIX}
    results["bootstrap.first-project"] = "pass"
    document = _checks(results)
    document["capabilities"] = {"machine_api": None}
    built = verdict.build(document, {"drills": []}, _healthy_resources(), "v1.0.0")
    assert built["verdict"] == "disqualified"
    assert built["unproven_checks"] == []


def test_a_restored_draft_is_not_a_restored_schedule() -> None:
    # The reviewer's reproduction: every boolean true, but the row came back as
    # a DRAFT, so nothing will send it.
    results = dict(RESTORED_OK, pending_post_state="DRAFT")
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "pending_post_still_queued" in detail


def test_a_queued_row_without_its_workflow_fails() -> None:
    # At v2.23.0 the recovery scan only re-queues posts already past due, so a
    # future job whose workflow was destroyed never fires on time.
    results = dict(RESTORED_OK, workflow_execution_restored=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "workflow_execution_restored" in detail


def test_a_missing_post_state_cannot_pass() -> None:
    results = dict(RESTORED_OK)
    del results["pending_post_state"]
    assert restore_verdict.judge(results, "0", "3", "3", "postiz")[0] == "fail"


def test_mixpost_is_not_asked_for_a_scheduler_it_lacks() -> None:
    result, _ = restore_verdict.judge(
        {"login_restored": True, "label_restored": True}, "0", "3", "3", "mixpost-lite"
    )
    assert result == "pass"


def test_a_post_the_publisher_can_no_longer_manage_fails() -> None:
    results = dict(RESTORED_OK, pending_post_manageable=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "pending_post_manageable" in detail


def test_a_closed_workflow_is_not_a_restored_schedule() -> None:
    # Temporal retains closed executions, so a completed or terminated
    # `post_<id>` is present without being a schedule that will ever fire.
    results = dict(RESTORED_OK, workflow_execution_restored=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "workflow_execution_restored" in detail


def test_a_cancel_that_left_the_workflow_running_fails() -> None:
    # deletePost removes the row first and terminates inside catch-and-ignore,
    # so an orphaned live workflow produces the same HTTP success.
    results = dict(RESTORED_OK, workflow_terminated_after_cancel=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "workflow_terminated_after_cancel" in detail


def test_a_workflow_absent_from_visibility_fails() -> None:
    results = dict(RESTORED_OK, visibility_lists_workflow=False)
    result, detail = restore_verdict.judge(results, "0", "3", "3", "postiz")
    assert result == "fail"
    assert "visibility_lists_workflow" in detail
