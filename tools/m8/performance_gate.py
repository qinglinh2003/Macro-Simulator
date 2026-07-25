#!/usr/bin/env python3
"""Run and enforce the M8 energy and housing performance budget."""

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
        default=ROOT / "schemas/m8/performance_budget.json",
    )
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--platform", default=sys.platform)
    arguments = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = (
        arguments.build_dir.resolve()
        / "native"
        / f"macro_sim_m8_benchmarks{suffix}"
    )
    completed = subprocess.run(
        [str(executable), "--days", str(arguments.days)],
        check=True,
        capture_output=True,
        text=True,
    )
    measured = json.loads(completed.stdout)
    budget = json.loads(arguments.budget.read_text(encoding="utf-8"))
    quiet = measured["quiet_p0"]
    active = measured["active_market"]
    failures: list[str] = []
    absolute_p95_ns = budget.get(
        "absolute_p95_ns_by_platform",
        {},
    ).get(arguments.platform, budget["absolute_p95_ns"])
    if quiet["p95_ns"] > absolute_p95_ns:
        failures.append("quiet p0 latency exceeds the absolute budget")
    if (
        quiet["maximum_allocations_per_day"]
        > budget["maximum_quiet_allocations_per_day"]
    ):
        failures.append("quiet allocation count exceeds the M8 budget")
    if (
        active["maximum_allocations_per_day"]
        > budget["maximum_active_allocations_per_day"]
    ):
        failures.append("active allocation count exceeds the M8 budget")
    if (
        measured["normalized_entity_scaling_ratio"]
        > budget["maximum_normalized_entity_scaling_ratio"]
    ):
        failures.append("entity scaling exceeds the M8 budget")
    if (
        measured["quiet_housing_over_energy_ratio"]
        > budget["maximum_quiet_housing_over_energy_ratio"]
    ):
        failures.append("quiet housing adds excessive daily overhead")
    if (
        budget["require_stable_quiet_scratch"]
        and quiet["scratch_before"] != quiet["scratch_after"]
    ):
        failures.append("quiet scratch capacity changed")
    if quiet["energy_sink"] <= 0.0 or quiet["housing_sink"] <= 0.0:
        failures.append("quiet benchmark omitted an M8 domain")
    if active["energy_sink"] <= 0.0 or active["housing_sink"] <= 0.0:
        failures.append("active benchmark omitted an M8 domain")
    report = {
        "failures": failures,
        "measurement": measured,
        "platform": arguments.platform,
        "platform_absolute_p95_ns": absolute_p95_ns,
        "schema_version": "m8-performance-gate-result-v1",
        "status": "failed" if failures else "passed",
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
