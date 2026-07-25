#!/usr/bin/env python3
"""Run the local M6 contract and acceptance checks."""

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
        (ROOT / "schemas/m6/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "absolute_p95_ns": 85_000_000,
        "absolute_p95_ns_by_platform": {
            "darwin": 65_000_000,
            "linux": 85_000_000,
            "win32": 80_000_000,
        },
        "maximum_allocations_per_day": 64,
        "maximum_scaling_ratio": 3.2,
        "p0": {
            "banks": 16,
            "firms": 300,
            "households": 2000,
            "measured_days": 60,
            "seed": 606,
            "warmup_days": 6,
            "watchlist_size": 15,
        },
        "require_stable_scratch_capacity": True,
        "schema_version": "m6-performance-budget-v1",
    }
    if budget != expected:
        raise AssertionError("M6 performance contract changed")

    required = (
        "native/include/macro_sim/core/securities.hpp",
        "native/include/macro_sim/simulation/m6.hpp",
        "native/include/macro_sim/simulation/m6_checkpoint.hpp",
        "native/src/core/securities.cpp",
        "native/src/simulation/m6.cpp",
        "native/src/simulation/m6_checkpoint.cpp",
        "tools/m6/fresh_process_checkpoint.py",
        "tools/m6/performance_gate.py",
        "tools/m6/semantic_panel.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M6 input is absent: {relative}")

    m5_header = (
        ROOT / "native/include/macro_sim/simulation/m5.hpp"
    ).read_text(encoding="utf-8")
    if "m6.hpp" in m5_header or "securities.hpp" in m5_header:
        raise AssertionError("M5 public header depends on an M6 domain")

    version = (
        ROOT / "native/include/macro_sim/version.hpp"
    ).read_text(encoding="utf-8")
    if '"0.6.0-m6"' not in version:
        raise AssertionError("M6 is not the current native engine version")

    for relative in (
        "native/include/macro_sim/simulation/m6.hpp",
        "native/src/simulation/m6.cpp",
        "native/src/simulation/m6_checkpoint.cpp",
        "docs/cpp_engine_m6_execution_plan_v33.md",
        "tools/m6",
    ):
        path = ROOT / relative
        candidates = [path] if path.is_file() else sorted(path.glob("*.py"))
        forbidden_target = "v" + "124"
        for candidate in candidates:
            if forbidden_target in candidate.read_text(
                encoding="utf-8"
            ).lower():
                raise AssertionError(
                    f"M6 targets a historical engine: {candidate}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m6-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m5/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M6 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
