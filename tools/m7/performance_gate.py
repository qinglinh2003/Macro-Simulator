#!/usr/bin/env python3
"""Run and enforce the M7 population and labor performance budget."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument(
        "--budget",
        type=Path,
        default=ROOT / "schemas/m7/performance_budget.json",
    )
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--platform", default=sys.platform)
    arguments = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = (
        arguments.build_dir.resolve()
        / "native"
        / f"macro_sim_m7_benchmarks{suffix}"
    )
    completed = subprocess.run(
        [str(executable), "--days", str(arguments.days)],
        check=True,
        capture_output=True,
        text=True,
    )
    measured = json.loads(completed.stdout)
    budget = json.loads(arguments.budget.read_text(encoding="utf-8"))
    p0 = measured["p0"]
    stable = measured["stable_scratch"]
    failures: list[str] = []
    absolute_p95_ns = budget.get(
        "absolute_p95_ns_by_platform",
        {},
    ).get(arguments.platform, budget["absolute_p95_ns"])
    if p0["p95_ns"] > absolute_p95_ns:
        failures.append("p0 p95 latency exceeds the absolute budget")
    if (
        p0["maximum_allocations_per_day"]
        > budget["maximum_allocations_per_day"]
    ):
        failures.append("allocation count exceeds the M7 budget")
    if (
        measured["daily_scaling_ratio"]
        > budget["maximum_daily_scaling_ratio"]
    ):
        failures.append("daily entity scaling exceeds the M7 budget")
    if (
        measured["matching_normalized_scaling_ratio"]
        > budget["maximum_matching_normalized_scaling_ratio"]
    ):
        failures.append("exact matching scaling exceeds the M7 budget")
    if (
        measured["roster_normalized_scaling_ratio"]
        > budget["maximum_roster_normalized_scaling_ratio"]
    ):
        failures.append("roster mutation scaling exceeds the M7 budget")
    if (
        budget["require_stable_no_topology_scratch"]
        and stable["scratch_before"] != stable["scratch_after"]
    ):
        failures.append("no-topology scratch capacity changed")
    if p0["labor_sink"] <= 0.0:
        failures.append("benchmark did not exercise persistent labor")
    if not all(row["match_sink"] > 0 for row in measured["matching"]):
        failures.append("benchmark did not exercise exact matching")
    report = {
        "failures": failures,
        "measurement": measured,
        "platform": arguments.platform,
        "platform_absolute_p95_ns": absolute_p95_ns,
        "schema_version": "m7-performance-gate-result-v1",
        "status": "failed" if failures else "passed",
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
