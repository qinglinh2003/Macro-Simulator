#!/usr/bin/env python3
"""Run the local M9 contract and acceptance checks."""

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
        (ROOT / "schemas/m9/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "absolute_n256_p95_ns": 30_000_000,
        "absolute_n256_p95_ns_by_platform": {
            "darwin": 30_000_000,
            "linux": 30_000_000,
            "win32": 90_000_000,
        },
        "dense_edge_threshold": 256,
        "maximum_allocations_per_economy_day": 400,
        "maximum_normalized_64_to_256_scaling": 2.0,
        "maximum_normalized_64_to_256_scaling_by_platform": {
            "darwin": 2.25,
        },
        "minimum_active_routes_per_day": 1,
        "p0": {
            "days": 7,
            "economies": [2, 4, 8, 16, 64, 256],
            "persons_per_economy": 8,
        },
        "schema_version": "m9-performance-budget-v1",
    }
    if budget != expected:
        raise AssertionError("M9 performance contract changed")

    required = (
        "docs/cpp_engine_m9_execution_plan_v33.md",
        "native/benchmarks/m9_world_benchmark.cpp",
        "native/include/macro_sim/simulation/m9.hpp",
        "native/src/simulation/m9.cpp",
        "native/src/simulation/m9_checkpoint.cpp",
        "native/tests/m9_c_smoke.c",
        "native/tests/m9_world_tests.cpp",
        "tools/m9/binding_smoke.py",
        "tools/m9/fresh_process_checkpoint.py",
        "tools/m9/performance_gate.py",
        "tools/m9/semantic_panel.py",
        "tools/m9/source_artifact_smoke.py",
        "tools/m9/wheel_smoke.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M9 input is absent: {relative}")

    version = (
        ROOT / "native/include/macro_sim/version.hpp"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'kEngineVersion\s*=\s*"(\d+)\.(\d+)\.(\d+)-m(\d+)"',
        version,
    )
    if match is None or tuple(map(int, match.groups())) < (0, 9, 0, 9):
        raise AssertionError("native engine predates the M9 frontier")

    m8_header = (
        ROOT / "native/include/macro_sim/simulation/m8.hpp"
    ).read_text(encoding="utf-8")
    if "m9.hpp" in m8_header:
        raise AssertionError("M8 public header depends on the M9 World")

    forbidden_target = "v" + "124"
    for relative in (
        "native/include/macro_sim/simulation/m9.hpp",
        "native/src/simulation/m9.cpp",
        "native/src/simulation/m9_checkpoint.cpp",
        "docs/cpp_engine_m9_execution_plan_v33.md",
        "tools/m9",
    ):
        path = ROOT / relative
        candidates = [path] if path.is_file() else sorted(path.glob("*.py"))
        for candidate in candidates:
            if forbidden_target in candidate.read_text(
                encoding="utf-8"
            ).lower():
                raise AssertionError(
                    f"M9 targets a historical engine: {candidate}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m9-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m8/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset, "-j", "8"])
        run(["ctest", "--preset", arguments.preset, "-j", "8"])
    print("M9 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
