#!/usr/bin/env python3
"""Run and validate the native M2 accounting benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUDGET_PATH = ROOT / "schemas/m2/performance_budget.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def benchmark_path(build_dir: Path) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return build_dir / "native" / f"macro_sim_m2_benchmarks{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=Path("build/native/m2-release"),
    )
    parser.add_argument("--repetitions", type=int, default=1000)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force-timing", action="store_true")
    arguments = parser.parse_args()

    executable = benchmark_path(ROOT / arguments.build_dir)
    if not executable.is_file():
        parser.error(f"benchmark executable is absent: {executable}")
    completed = subprocess.run(
        [
            str(executable),
            "--repetitions",
            str(arguments.repetitions),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    budget = load_json(BUDGET_PATH)
    timing_enforced = arguments.force_timing or (
        platform.system() == budget["timing_enforcement_profile"]["os"]
        and platform.machine().lower()
        == budget["timing_enforcement_profile"]["architecture"]
    )
    failures: list[str] = []
    allocations = budget["allocation_budget"]
    allocation_fields = {
        "no_journal_transfer": "no_journal_measured_allocations",
        "batch_commit": "batch_measured_allocations",
        "rollback": "rollback_measured_allocations",
    }
    for budget_name, result_name in allocation_fields.items():
        if result[result_name] > allocations[budget_name]:
            failures.append(
                f"{result_name}={result[result_name]} exceeds "
                f"{allocations[budget_name]}"
            )
    if result.get("invariant_status") != "passed":
        failures.append("benchmark invariant status did not pass")
    if timing_enforced:
        timing = budget["timing_budget_ns"]
        timing_fields = {
            "no_journal_transfer_median": "no_journal_transfer",
            "batch_commit_per_transfer_median": "batch_commit_per_transfer",
            "rollback_per_transfer_median": "rollback_per_transfer",
        }
        for budget_name, result_name in timing_fields.items():
            observed = result[result_name]["median_ns"]
            if observed > timing[budget_name]:
                failures.append(
                    f"{result_name}.median_ns={observed} exceeds "
                    f"{timing[budget_name]}"
                )

    report = {
        "architecture": platform.machine(),
        "benchmark": result,
        "budget_schema_version": budget["schema_version"],
        "os": platform.system(),
        "schema_version": "m2-performance-gate-report-v1",
        "status": "failed" if failures else "passed",
        "timing_enforced": timing_enforced,
        "violations": failures,
    }
    encoded = (
        json.dumps(report, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    if arguments.report is not None:
        output = ROOT / arguments.report
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
