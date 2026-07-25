#!/usr/bin/env python3
"""Run the local M8 contract and acceptance checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_contracts() -> None:
    budget = json.loads(
        (ROOT / "schemas/m8/performance_budget.json").read_text(
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
        "maximum_active_allocations_per_day": 5000,
        "maximum_normalized_entity_scaling_ratio": 2.5,
        "maximum_quiet_allocations_per_day": 2500,
        "maximum_quiet_housing_over_energy_ratio": 1.2,
        "p0": {
            "measured_days": 60,
            "persons": 2000,
            "seed": 808,
            "warmup_days": 11,
        },
        "require_stable_quiet_scratch": True,
        "schema_version": "m8-performance-budget-v1",
    }
    if budget != expected:
        raise AssertionError("M8 performance contract changed")

    required = (
        "native/benchmarks/m8_energy_housing_benchmark.cpp",
        "native/include/macro_sim/core/housing.hpp",
        "native/include/macro_sim/simulation/m8.hpp",
        "native/include/macro_sim/simulation/m8_checkpoint.hpp",
        "native/src/core/housing.cpp",
        "native/src/simulation/m8.cpp",
        "native/src/simulation/m8_checkpoint.cpp",
        "native/tests/m8_c_smoke.c",
        "tools/m8/fresh_process_checkpoint.py",
        "tools/m8/performance_gate.py",
        "tools/m8/semantic_panel.py",
        "tools/m8/source_artifact_smoke.py",
        "tools/m8/wheel_smoke.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M8 input is absent: {relative}")

    m7_header = (
        ROOT / "native/include/macro_sim/simulation/m7.hpp"
    ).read_text(encoding="utf-8")
    if "m8.hpp" in m7_header or "housing.hpp" in m7_header:
        raise AssertionError("M7 public header depends on an M8 domain")

    version = (
        ROOT / "native/include/macro_sim/version.hpp"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'kEngineVersion\s*=\s*"(\d+)\.(\d+)\.(\d+)-m(\d+)"',
        version,
    )
    if match is None or tuple(map(int, match.groups())) < (0, 8, 0, 8):
        raise AssertionError("native engine predates the M8 frontier")

    forbidden_target = "v" + "124"
    for relative in (
        "native/include/macro_sim/simulation/m8.hpp",
        "native/src/simulation/m8.cpp",
        "native/src/simulation/m8_checkpoint.cpp",
        "docs/cpp_engine_m8_execution_plan_v33.md",
        "tools/m8",
    ):
        path = ROOT / relative
        candidates = [path] if path.is_file() else sorted(path.glob("*.py"))
        for candidate in candidates:
            if forbidden_target in candidate.read_text(
                encoding="utf-8"
            ).lower():
                raise AssertionError(
                    f"M8 targets a historical engine: {candidate}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m8-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m7/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset, "-j", "8"])
        run(["ctest", "--preset", arguments.preset, "-j", "8"])
    print("M8 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
