#!/usr/bin/env python3
"""Run M10 contract checks and the local native acceptance preset."""

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
        (ROOT / "schemas/m10/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    if budget["schema_version"] != "m10-performance-budget-v1":
        raise AssertionError("M10 performance contract changed")
    if budget["history_capacity_frames"] <= 0:
        raise AssertionError("M10 history must be bounded")

    required = (
        "docs/cpp_engine_m10_execution_plan_v34.md",
        "schemas/m10/performance_budget.json",
        "schemas/m10/public_metrics.json",
        "macro_sim/native_backend.py",
        "tools/m10/check.py",
        "tools/m10/native_facade_smoke.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M10 input is absent: {relative}")

    forbidden = ("PyObject_Call", "PyObject_CallObject", "nb::call", "py::call")
    for path in sorted((ROOT / "native/src").rglob("*.cpp")):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            raise AssertionError(f"native callback hook found in {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m10-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m9/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset, "-j", "8"])
        run(["ctest", "--preset", arguments.preset, "-j", "8"])
    print("M10 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
