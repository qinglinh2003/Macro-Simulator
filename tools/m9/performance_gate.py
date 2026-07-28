#!/usr/bin/env python3
"""Run and enforce the M9 multi-country performance budget."""

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
        default=ROOT / "schemas/m9/performance_budget.json",
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--platform", default=sys.platform)
    arguments = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = (
        arguments.build_dir.resolve()
        / "native"
        / f"macro_sim_m9_benchmarks{suffix}"
    )
    completed = subprocess.run(
        [str(executable), "--days", str(arguments.days)],
        check=True,
        capture_output=True,
        text=True,
    )
    measured = json.loads(completed.stdout)
    budget = json.loads(arguments.budget.read_text(encoding="utf-8"))
    n64 = measured["n64"]
    n256 = measured["n256"]
    failures: list[str] = []
    absolute_p95 = budget["absolute_n256_p95_ns_by_platform"].get(
        arguments.platform,
        budget["absolute_n256_p95_ns"],
    )
    if n256["p95_ns"] > absolute_p95:
        failures.append("N=256 latency exceeds the M9 absolute budget")
    allocations_per_economy = (
        n256["maximum_allocations_per_day"] / n256["economies"]
    )
    if (
        allocations_per_economy
        > budget["maximum_allocations_per_economy_day"]
    ):
        failures.append("M9 allocation density exceeds the budget")
    normalized_scaling = (
        n256["median_ns"] / n64["median_ns"]
    ) / (n256["economies"] / n64["economies"])
    maximum_normalized_scaling = budget["maximum_normalized_64_to_256_scaling"]
    if normalized_scaling > maximum_normalized_scaling:
        failures.append("M9 N=64 to N=256 scaling exceeds the budget")
    if measured["dense_edge_threshold"] != budget["dense_edge_threshold"]:
        failures.append("M9 dense edge threshold differs from the contract")
    minimum_routes = budget["minimum_active_routes_per_day"] * arguments.days
    for name in ("n2", "n4", "n8", "n16", "n64", "n256"):
        if measured[name]["trade_routes"] < minimum_routes:
            failures.append(f"{name} trade path is not active")
        if measured[name]["migration_routes"] < minimum_routes:
            failures.append(f"{name} migration path is not active")
    report = {
        "allocations_per_economy_day": allocations_per_economy,
        "failures": failures,
        "measurement": measured,
        "normalized_64_to_256_scaling": normalized_scaling,
        "maximum_normalized_64_to_256_scaling": maximum_normalized_scaling,
        "platform": arguments.platform,
        "platform_absolute_n256_p95_ns": absolute_p95,
        "schema_version": "m9-performance-gate-result-v1",
        "status": "failed" if failures else "passed",
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
