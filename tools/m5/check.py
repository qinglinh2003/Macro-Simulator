#!/usr/bin/env python3
"""Run the local M5 contract and acceptance checks."""

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
        (ROOT / "schemas/m5/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    if budget["maximum_allocations_per_day"] > 2:
        raise AssertionError("M5 allocation budget is too permissive")
    header = (
        ROOT / "native/include/macro_sim/simulation/m5.hpp"
    ).read_text(encoding="utf-8")
    if "securities" in header or "equity" in header:
        raise AssertionError("M5 public header depends on an M6 domain")
    source = (
        ROOT / "native/src/simulation/m5.cpp"
    ).read_text(encoding="utf-8")
    if "v124" in source.lower():
        raise AssertionError("M5 contains a historical-engine target")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m5-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m4/current_target.py", "--check"])
    run([sys.executable, "tools/m5/locks.py"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M5 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
