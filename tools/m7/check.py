#!/usr/bin/env python3
"""Run the local M7 contract and acceptance checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_contracts() -> None:
    budget = json.loads(
        (ROOT / "schemas/m7/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "absolute_p95_ns": 120_000_000,
        "absolute_p95_ns_by_platform": {
            "darwin": 120_000_000,
            "linux": 120_000_000,
            "win32": 120_000_000,
        },
        "maximum_allocations_per_day": 2200,
        "maximum_daily_scaling_ratio": 3.2,
        "maximum_matching_normalized_scaling_ratio": 2.6,
        "maximum_roster_normalized_scaling_ratio": 1.5,
        "p0": {
            "banks": 8,
            "firms": 120,
            "households": 800,
            "measured_days": 60,
            "persons": 2000,
            "seed": 707,
            "warmup_days": 6,
            "watchlist_size": 12,
        },
        "require_stable_no_topology_scratch": True,
        "schema_version": "m7-performance-budget-v1",
    }
    if budget != expected:
        raise AssertionError("M7 performance contract changed")

    required = (
        "native/include/macro_sim/core/population.hpp",
        "native/include/macro_sim/core/social_labor.hpp",
        "native/include/macro_sim/simulation/m7.hpp",
        "native/include/macro_sim/simulation/m7_checkpoint.hpp",
        "native/src/core/population.cpp",
        "native/src/core/social_labor.cpp",
        "native/src/simulation/m7.cpp",
        "native/src/simulation/m7_checkpoint.cpp",
        "tools/m7/fresh_process_checkpoint.py",
        "tools/m7/performance_gate.py",
        "tools/m7/semantic_panel.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M7 input is absent: {relative}")

    m6_header = (
        ROOT / "native/include/macro_sim/simulation/m6.hpp"
    ).read_text(encoding="utf-8")
    if "m7.hpp" in m6_header or "population.hpp" in m6_header:
        raise AssertionError("M6 public header depends on an M7 domain")

    version = (
        ROOT / "native/include/macro_sim/version.hpp"
    ).read_text(encoding="utf-8")
    if '"0.7.0-m7"' not in version:
        raise AssertionError("M7 is not the current native engine version")

    forbidden_target = "v" + "124"
    for relative in (
        "native/include/macro_sim/simulation/m7.hpp",
        "native/src/simulation/m7.cpp",
        "native/src/simulation/m7_checkpoint.cpp",
        "docs/cpp_engine_m7_execution_plan_v33.md",
        "tools/m7",
    ):
        path = ROOT / relative
        candidates = [path] if path.is_file() else sorted(path.glob("*.py"))
        for candidate in candidates:
            if forbidden_target in candidate.read_text(
                encoding="utf-8"
            ).lower():
                raise AssertionError(
                    f"M7 targets a historical engine: {candidate}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m7-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m6/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M7 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
