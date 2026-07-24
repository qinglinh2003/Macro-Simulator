#!/usr/bin/env python3
"""Run the frozen M4 stochastic replay and aggregate panel."""

from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def run_seed(native, seed: int) -> tuple[str, dict[str, float]]:
    spec = native.M4SimulationSpec()
    spec.vertical = native.M4Vertical.CAPITAL_FISCAL
    spec.households = 80
    spec.consumption_firms = 12
    spec.capital_firms = 4
    spec.requested_capabilities = 3
    spec.market_protocol = native.MatchingProtocol.SAMPLED
    spec.stochastic = True
    spec.seed = seed
    first = native.EngineSession(seed * 2)
    second = native.EngineSession(seed * 2 + 1)
    first.initialize_simulation(spec)
    second.initialize_simulation(spec)
    first.advance_ticks(60)
    second.advance_ticks(60)
    if first.digest() != second.digest():
        raise AssertionError(f"seed {seed} did not replay exactly")
    metrics = first.simulation_snapshot()["metrics"]
    return first.digest(), {
        "nominal_output": float(metrics["nominal_output"]),
        "price_index": float(metrics["price_index"]),
        "tax_total": float(metrics["tax_total"]),
        "unemployment_rate": float(metrics["unemployment_rate"]),
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for key in rows[0]:
        values = [row[key] for row in rows]
        output[key] = {
            "maximum": max(values),
            "mean": statistics.fmean(values),
            "minimum": min(values),
        }
    return output


def validate(
    actual: dict[str, dict[str, float]],
    contract: dict[str, Any],
) -> None:
    for metric, bounds in contract["metrics"].items():
        for statistic_name, interval in bounds.items():
            value = actual[metric][statistic_name]
            if not math.isfinite(value) or not (
                float(interval[0]) <= value <= float(interval[1])
            ):
                raise AssertionError(
                    f"{metric}.{statistic_name}={value!r} is outside "
                    f"{interval!r}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    parser.add_argument("--envelopes", type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())
    rows: list[dict[str, float]] = []
    digests: set[str] = set()
    for seed in range(1000, 1032):
        digest, metrics = run_seed(native, seed)
        digests.add(digest)
        rows.append(metrics)
    if len(digests) < 24:
        raise AssertionError("stochastic panel has insufficient seed diversity")
    actual = aggregate(rows)
    if arguments.envelopes is not None:
        contract = json.loads(
            arguments.envelopes.read_text(encoding="utf-8")
        )
        validate(actual, contract)
    print(json.dumps({
        "distinct_digests": len(digests),
        "metrics": actual,
        "schema_version": "m4-stochastic-panel-result-v1",
        "seeds": 32,
        "status": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
