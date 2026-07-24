#!/usr/bin/env python3
"""Validate an M4 tick benchmark result against its frozen budget."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--result", type=Path)
    source.add_argument("--build-dir", type=Path)
    arguments = parser.parse_args()
    budget = read_json(arguments.budget)
    if arguments.result is not None:
        result = read_json(arguments.result)
    else:
        assert arguments.build_dir is not None
        suffix = ".exe" if os.name == "nt" else ""
        executable = (
            arguments.build_dir
            / "native"
            / f"macro_sim_m4_benchmarks{suffix}"
        )
        completed = subprocess.run(
            [
                str(executable),
                "--days",
                str(budget["p0"]["measured_days"]),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
    p0 = result["p0"]
    expected = budget["p0"]
    for key in ("households", "consumption_firms", "capital_firms"):
        if int(p0[key]) != int(expected[key]):
            raise AssertionError(
                f"P0 {key} mismatch: {p0[key]!r} != {expected[key]!r}"
            )
    if int(p0["days"]) != int(expected["measured_days"]):
        raise AssertionError("P0 measured-day count does not match")
    native_to_python = (
        float(p0["median_ns"]) / float(budget["matched_python_median_ns"])
    )
    if native_to_python > float(budget["maximum_native_to_python_ratio"]):
        raise AssertionError(
            f"native/Python ratio {native_to_python:.6f} exceeds budget"
        )
    if int(p0["p95_ns"]) > int(budget["absolute_p95_ns"]):
        raise AssertionError("P0 p95 exceeds the absolute daily budget")
    if float(result["scaling_ratio"]) > float(budget["maximum_scaling_ratio"]):
        raise AssertionError("2x entity scaling ratio exceeds the budget")
    if int(p0["maximum_allocations_per_day"]) > int(
        budget["maximum_allocations_per_day"]
    ):
        raise AssertionError("steady tick allocation count exceeds the budget")
    if budget["require_stable_scratch_capacity"] and (
        int(p0["scratch_before"]) != int(p0["scratch_after"])
        or int(result["half"]["scratch_before"])
        != int(result["half"]["scratch_after"])
    ):
        raise AssertionError("scratch capacity changed after warm-up")
    print(json.dumps({
        "native_to_python_ratio": native_to_python,
        "p0_median_ns": int(p0["median_ns"]),
        "p0_p95_ns": int(p0["p95_ns"]),
        "scaling_ratio": float(result["scaling_ratio"]),
        "schema_version": "m4-performance-gate-result-v1",
        "status": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
