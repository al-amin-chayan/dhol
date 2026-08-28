#!/usr/bin/env python3
"""Summarise `docker stats` samples into a DG-01 capacity verdict.

The parsing and the verdict are pure functions so the capacity thresholds are
unit-tested rather than asserted only by a live run.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Iterable

# docs/plans/two-vps-reproducible-implementation-plan.md WP-13 verify clause.
PEAK_RAM_BUDGET_MIB = 4.5 * 1024
STEADY_DISK_BUDGET_MIB = 18 * 1024
# WP-13 also asks for >=8 GB of update headroom. That is a property of a real
# 30 GB host mid-upgrade — free filesystem space while two image sets coexist —
# and nothing here measures it. Subtracting this topology's footprint from
# 30 GiB ignores the host OS, container writable layers, Docker metadata and
# logs, monitoring and restic, and the second image set an update pulls. It is
# reported as unmeasured rather than dressed up as a passing gate.
UPDATE_HEADROOM_BUDGET_MIB = 8 * 1024
UPDATE_HEADROOM_STATUS = "unmeasured: needs a bounded 30 GB host mid-upgrade (WP-13)"

UNIT_MIB = {
    "B": 1 / (1024 * 1024),
    "KIB": 1 / 1024,
    "KB": 1000 / (1024 * 1024),
    "MIB": 1.0,
    "MB": 1000 * 1000 / (1024 * 1024),
    "GIB": 1024.0,
    "GB": 1000 * 1000 * 1000 / (1024 * 1024),
    "TIB": 1024.0 * 1024,
}

SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*$")


def to_mib(value: str) -> float:
    match = SIZE_RE.match(value)
    if not match:
        raise ValueError(f"unparsable size: {value!r}")
    amount, unit = match.groups()
    key = unit.upper()
    if key not in UNIT_MIB:
        raise ValueError(f"unknown size unit: {unit!r}")
    return float(amount) * UNIT_MIB[key]


def parse_samples(lines: Iterable[str]) -> list[dict[str, float | str]]:
    """Parse `docker stats --format '{{.Name}}|{{.MemUsage}}'` output.

    A blank line separates one sampling round from the next, so a round with no
    containers is preserved rather than merged into its neighbour.
    """
    rounds: list[list[dict[str, float | str]]] = [[]]
    for raw in lines:
        line = raw.strip()
        if not line:
            rounds.append([])
            continue
        name, _, usage = line.partition("|")
        used, _, _limit = usage.partition("/")
        rounds[-1].append({"name": name.strip(), "mib": to_mib(used)})
    samples = []
    for index, entries in enumerate(rounds):
        if not entries:
            continue
        samples.append(
            {
                "round": index,
                "total_mib": round(sum(float(entry["mib"]) for entry in entries), 1),
                "containers": len(entries),
            }
        )
    return samples


def summarise(
    samples: list[dict[str, float | str]],
    disk_mib: float,
    image_mib: float,
    startup_seconds: float | None = None,
) -> dict:
    totals = [float(sample["total_mib"]) for sample in samples]
    peak = max(totals) if totals else 0.0
    # The lowest sample is normally taken while the stack is still warming up,
    # so it is reported as the observed minimum and never as a steady idle
    # figure the founder could mistake for a seven-day canary result.
    minimum = min(totals) if totals else 0.0
    topology_disk = disk_mib + image_mib
    return {
        "samples": len(samples),
        "startup_seconds": None if startup_seconds is None else round(startup_seconds, 1),
        "min_ram_mib": round(minimum, 1),
        "peak_ram_mib": round(peak, 1),
        "peak_ram_budget_mib": PEAK_RAM_BUDGET_MIB,
        "peak_ram_within_budget": peak <= PEAK_RAM_BUDGET_MIB,
        "volume_disk_mib": round(disk_mib, 1),
        "image_disk_mib": round(image_mib, 1),
        # This topology's own images plus named volumes. It is a lower bound on
        # what the publisher costs a 30 GB host, not the host's steady usage:
        # the host OS, writable layers, Docker metadata and logs, monitoring and
        # restic are all outside it.
        "topology_disk_mib": round(topology_disk, 1),
        "topology_disk_is_lower_bound": True,
        "steady_disk_budget_mib": STEADY_DISK_BUDGET_MIB,
        "topology_within_steady_budget": topology_disk <= STEADY_DISK_BUDGET_MIB,
        "update_headroom_budget_mib": UPDATE_HEADROOM_BUDGET_MIB,
        "update_headroom": UPDATE_HEADROOM_STATUS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", required=True, help="file of Name|MemUsage lines, blank line between rounds")
    parser.add_argument("--volume-mib", type=float, required=True)
    parser.add_argument("--image-mib", type=float, required=True,
                        help="on-disk size of every image in the candidate topology, not only the app image")
    parser.add_argument("--startup-seconds", type=float, default=None,
                        help="seconds from the converge command to the first non-gateway HTTP answer")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.samples, encoding="utf-8") as handle:
        samples = parse_samples(handle)
    summary = summarise(samples, args.volume_mib, args.image_mib, args.startup_seconds)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
