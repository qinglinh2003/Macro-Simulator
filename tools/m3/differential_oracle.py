#!/usr/bin/env python3
"""Compare M3 native pure algorithms with independent Python semantics."""

from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any

from equation_fixtures import FIXTURE, expected


ROOT = Path(__file__).resolve().parents[2]


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def close(actual: float, expected_value: float) -> bool:
    return math.isclose(actual, expected_value, rel_tol=1e-10, abs_tol=1e-10)


def fixture_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def randomized_cases(seed: int, count: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for _ in range(count):
        previous = rng.uniform(0.0, 100.0)
        observed = rng.uniform(0.0, 100.0)
        adjustment = rng.uniform(0.0, 1.0)
        rows.append({
            "kind": "adaptive_expectation",
            "values": [previous, observed, adjustment],
        })
        rows.append({
            "kind": "production_plan",
            "values": [
                rng.uniform(0.0, 100.0),
                rng.uniform(0.0, 3.0),
                rng.uniform(0.0, 100.0),
                rng.uniform(0.0, 1.0),
            ],
        })
        rows.append({
            "kind": "investment_user_cost",
            "values": [
                rng.uniform(0.0, 0.2),
                rng.uniform(-0.05, 0.1),
                rng.uniform(0.0, 0.2),
                rng.uniform(-0.02, 0.08),
                rng.uniform(0.0, 0.05),
                rng.uniform(0.1, 2.0),
                0.25,
                2.0,
                1e-9,
            ],
        })
        rows.append({
            "kind": "residual_income_fundamental",
            "values": [
                rng.uniform(-100.0, 500.0),
                rng.uniform(-20.0, 100.0),
                rng.uniform(0.1, 100.0),
                rng.uniform(-0.01, 0.2),
            ],
        })
        rows.append({
            "kind": "bond_price",
            "values": [
                rng.uniform(1.0, 1000.0),
                rng.randint(1, 50),
                rng.uniform(-0.005, 0.2),
                rng.uniform(0.0, 0.1),
            ],
        })
    return rows


def validate_equations(native, rows: list[dict[str, Any]]) -> None:
    actual = native.m3_equation_batch(
        [{"kind": row["kind"], "values": row["values"]} for row in rows]
    )
    for index, (case, received) in enumerate(zip(rows, actual, strict=True)):
        wanted = case.get("expected")
        if wanted is None:
            wanted = expected(case)
        if len(received) != len(wanted) or not all(
            close(float(left), float(right))
            for left, right in zip(received, wanted, strict=True)
        ):
            raise AssertionError(
                f"equation mismatch at {index} {case['kind']}: "
                f"native={received!r} python={wanted!r}"
            )


def validate_market_adapter(native) -> None:
    orders = [{"order_id": 1, "buyer": 10, "demand": 4.0, "budget": 20.0}]
    offers = [
        {"offer_id": 1, "seller": 20, "stock": 2.0, "price": 4.0, "attractiveness": 1.0},
        {"offer_id": 2, "seller": 30, "stock": 5.0, "price": 2.0, "attractiveness": 1.0},
    ]
    reference = native.m3_clear_market(
        orders, offers, "price_sorted", key=[7, 11], worker_count=1,
    )
    assert reference["trades"] == [{
        "ordinal": 0,
        "order_id": 1,
        "offer_id": 2,
        "buyer": 10,
        "seller": 30,
        "quantity": 4.0,
        "price": 2.0,
        "value": 8.0,
    }]
    assert reference["diagnostics"]["price_sorts"] == 1
    for workers in (2, 4, 8):
        candidate = native.m3_clear_market(
            orders, offers, "price_sorted", key=[7, 11], worker_count=workers,
        )
        assert candidate["trades"] == reference["trades"]
        assert candidate["allocations"] == reference["allocations"]
        assert candidate["stock_commands"] == reference["stock_commands"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--random-cases", type=int, default=200)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())
    validate_equations(native, fixture_cases())
    validate_equations(
        native,
        randomized_cases(arguments.seed, arguments.random_cases),
    )
    validate_market_adapter(native)
    print(
        json.dumps(
            {
                "exact_cases": len(fixture_cases()),
                "random_cases": arguments.random_cases * 5,
                "schema_version": "m3-differential-result-v1",
                "status": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
