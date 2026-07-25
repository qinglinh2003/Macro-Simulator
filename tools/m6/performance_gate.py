#!/usr/bin/env python3
"""Run and enforce the M6 native securities performance budget."""

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
        default=ROOT / "schemas/m6/performance_budget.json",
    )
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--platform", default=sys.platform)
    arguments = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = (
        arguments.build_dir.resolve()
        / "native"
        / f"macro_sim_m6_benchmarks{suffix}"
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
        failures.append("allocation count exceeds the M6 budget")
    if measured["scaling_ratio"] > budget["maximum_scaling_ratio"]:
        failures.append("entity scaling ratio exceeds the M6 budget")
    if (
        budget["require_stable_scratch_capacity"]
        and p0["scratch_before"] != p0["scratch_after"]
    ):
        failures.append("M6 scratch capacity changed during measurement")
    if p0["market_sink"] <= 0.0 or p0["transfer_sink"] <= 0:
        failures.append("benchmark did not exercise markets and settlement")
    report = {
        "failures": failures,
        "measurement": measured,
        "platform": arguments.platform,
        "platform_absolute_p95_ns": absolute_p95_ns,
        "schema_version": "m6-performance-gate-result-v1",
        "status": "failed" if failures else "passed",
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
