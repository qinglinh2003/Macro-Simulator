#!/usr/bin/env python3
"""Run and validate the M3 matching complexity benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUDGET = ROOT / "schemas/m3/performance_budget.json"


def executable(build_dir: Path) -> Path:
    suffix = ".exe" if __import__("os").name == "nt" else ""
    return build_dir / "native" / f"macro_sim_m3_benchmarks{suffix}"


def run(build_dir: Path, repetitions: int) -> dict[str, Any]:
    completed = subprocess.run(
        [str(executable(build_dir)), "--repetitions", str(repetitions)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def validate(result: dict[str, Any], budget: dict[str, Any]) -> None:
    if result.get("schema_version") != "m3-market-benchmark-v1":
        raise SystemExit("unexpected M3 benchmark schema")
    rows = result["rows"]
    expected_sizes = budget["sizes"]
    by_protocol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_protocol.setdefault(row["protocol"], []).append(row)
        if row["protocol"] == "preferential":
            if row["preferential_weight_builds"] > budget["instrumentation"]["preferential_weight_builds_max"]:
                raise SystemExit("preferential matching rebuilt seller weights")
        elif row["preferential_weight_builds"] != 0:
            raise SystemExit("non-preferential matching reported a weight build")
        if row["protocol"] == "price_sorted":
            if row["price_sorts"] > budget["instrumentation"]["price_sorted_sorts_max"]:
                raise SystemExit("price-sorted matching sorted more than once")
        elif row["price_sorts"] != 0:
            raise SystemExit("non-price matching reported a price sort")
    for protocol, protocol_rows in by_protocol.items():
        protocol_rows.sort(key=lambda row: row["size"])
        if [row["size"] for row in protocol_rows] != expected_sizes:
            raise SystemExit(f"{protocol} benchmark sizes are incomplete")
        limit = budget["complexity_ratios"][f"{protocol}_double_sellers_max"]
        for previous, current in zip(protocol_rows, protocol_rows[1:], strict=False):
            ratio = current["median_ns"] / previous["median_ns"]
            if ratio > limit:
                raise SystemExit(
                    f"{protocol} doubling ratio {ratio:.3f} exceeds {limit:.3f}"
                )
            candidate_ratio = current["seller_candidates"] / max(
                1, previous["seller_candidates"],
            )
            if candidate_ratio > 2.25:
                raise SystemExit(
                    f"{protocol} candidate-work ratio {candidate_ratio:.3f} is superlinear"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=9)
    arguments = parser.parse_args()
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    result = run(arguments.build_dir.resolve(), arguments.repetitions)
    validate(result, budget)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
