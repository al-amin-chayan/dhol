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
    assert summary["steady_disk_within_budget"] is True


def test_the_lowest_sample_is_reported_as_a_minimum_not_an_idle_figure() -> None:
    samples = resources.parse_samples(["app|100MiB / 6GiB", "", "app|900MiB / 6GiB", ""])
    summary = resources.summarise(samples, disk_mib=0.0, image_mib=0.0)
    assert summary["min_ram_mib"] == pytest.approx(100.0)
    assert summary["peak_ram_mib"] == pytest.approx(900.0)
    assert "idle_ram_mib" not in summary


def test_capacity_summary_flags_a_disk_breach() -> None:
    samples = resources.parse_samples(["app|1GiB / 6GiB", ""])
    summary = resources.summarise(samples, disk_mib=24 * 1024.0, image_mib=1024.0)
    assert summary["steady_disk_within_budget"] is False
    assert summary["update_headroom_within_budget"] is False


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
