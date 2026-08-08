#!/usr/bin/env python3
"""Compare the M4 native tick with an independent Python reference."""

from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
import sys
from typing import Any


CAPITAL_AND_GOVERNMENT = 3
DAILY_GROWTH = 1.0 + 0.02 / 365.0


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10)


def assert_close(name: str, actual: float, expected: float) -> None:
    if not close(float(actual), float(expected)):
        raise AssertionError(f"{name}: native={actual!r} python={expected!r}")


def demand_after_open() -> float:
    return 10.0 + 0.0076 * (0.0 - 10.0)


def production_target(inventory: float) -> float:
    demand = demand_after_open()
    target_inventory = 14.0 * demand
    return demand + 0.05 * (target_inventory - inventory)


def reference_v0() -> dict[str, Any]:
    budget = 0.8 * 1.0 + 100.0 * 5.5e-5
    quantity = budget / 1.2
    produced = DAILY_GROWTH
    balances = [0.0, 0.0, 0.0, 0.0, 0.0, 101.0 - budget, 199.0 + budget]
    firm_profit = budget - 1.0
    return {
        "balances": balances,
        "household": {
            "income_expected": 1.0,
            "income_realized": 1.0,
            "consumption_budget": budget,
            "spent": budget,
            "labor_sold": 1.0,
        },
        "firm": {
            "inventory": 10.0 + produced - quantity,
            "capital": 0.0,
            "price": 1.2,
            "wage": 1.0,
            "expected_demand": demand_after_open(),
            "previous_sales": quantity,
        },
        "technology_index": DAILY_GROWTH,
        "public_capital": 0.0,
        "rng_counter": [1, 0, 0, 0],
        "phase_ids": [0, 1, 2, 3, 4, 5, 7, 8, 9],
        "metrics": {
            "tick": 0,
            "real_output": produced,
            "nominal_output": budget,
            "price_index": 1.2,
            "unemployment_rate": 0.0,
            "total_money": 300.0,
            "conservation_drift": 0.0,
            "aggregate_capital": 0.0,
            "household_consumption": budget,
            "wages_paid": 1.0,
            "firm_profit": firm_profit,
            "tax_total": 0.0,
            "government_spending": 0.0,
            "government_deficit": 0.0,
            "public_capital": 0.0,
        },
    }


def reference_v1() -> dict[str, Any]:
    gross_budget = 0.8 * 1.0 + 100.0 * 5.5e-5
    household_spend = gross_budget / 1.15
    consumption_tax = household_spend * 0.15
    household_quantity = household_spend / 1.2
    government_quantity = 0.2
    government_consumption = government_quantity * 1.2

    consumption_produced = math.pow(20.0, 0.3) * DAILY_GROWTH
    desired_capital = 2.5 * demand_after_open()
    investment_quantity = max(
        0.0,
        0.0019 * (desired_capital - 20.0) + 0.000228 * 20.0,
    )
    investment_value = investment_quantity * 1.2
    public_quantity = 0.04
    public_investment = public_quantity * 1.2

    consumption_revenue = household_spend + government_consumption
    capital_revenue = investment_value + public_investment
    consumption_profit = consumption_revenue - 1.0
    capital_profit = capital_revenue
    profit_tax = capital_profit * 0.25
    dividend = (capital_profit - profit_tax) * 0.5
    income_before_tax = 1.0 + dividend
    income_tax = income_before_tax * 0.2

    household_balance_before_wealth_tax = (
        100.0
        + 1.0
        - household_spend
        - consumption_tax
        + dividend
        - income_tax
    )
    wealth_tax = household_balance_before_wealth_tax * 5.479452054794521e-6
    household_balance = household_balance_before_wealth_tax - wealth_tax
    consumption_balance = (
        200.0 - 1.0 + consumption_revenue - investment_value
    )
    capital_balance = (
        200.0 + capital_revenue - profit_tax - dividend
    )
    treasury_balance = (
        consumption_tax
        - government_consumption
        - public_investment
        + profit_tax
        + income_tax
        + wealth_tax
    )
    tax_total = consumption_tax + profit_tax + income_tax + wealth_tax
    closing_capital = 20.0 * (1.0 - 0.000228) + investment_quantity
    return {
        "balances": [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            treasury_balance,
            household_balance,
            consumption_balance,
            capital_balance,
        ],
        "household": {
            "income_expected": 1.0,
            "income_realized": income_before_tax - income_tax,
            "consumption_budget": gross_budget,
            "spent": household_spend,
            "labor_sold": 1.0,
        },
        "firms": [
            {
                "inventory": (
                    10.0
                    + consumption_produced
                    - household_quantity
                    - government_quantity
                ),
                "capital": closing_capital,
                "price": 1.2,
                "wage": 1.0,
                "expected_demand": demand_after_open(),
                "previous_sales": household_quantity + government_quantity,
            },
            {
                "inventory": 5.0 - investment_quantity - public_quantity,
                "capital": 0.0,
                "price": 1.2,
                "wage": 1.0,
                "expected_demand": demand_after_open(),
                "previous_sales": investment_quantity + public_quantity,
            },
        ],
        "technology_index": DAILY_GROWTH,
        "public_capital": public_quantity,
        "rng_counter": [2, 0, 0, 0],
        "phase_ids": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "metrics": {
            "tick": 0,
            "real_output": consumption_produced,
            "nominal_output": consumption_revenue + capital_revenue,
            "price_index": 1.2,
            "unemployment_rate": 0.0,
            "total_money": 500.0,
            "conservation_drift": 0.0,
            "aggregate_capital": closing_capital,
            "household_consumption": household_spend,
            "wages_paid": 1.0,
            "firm_profit": consumption_profit + capital_profit,
            "tax_total": tax_total,
            "government_spending": government_consumption + public_investment,
            "government_deficit": (
                government_consumption + public_investment - tax_total
            ),
            "public_capital": public_quantity,
        },
    }


def run_case(native, *, fiscal: bool) -> dict[str, Any]:
    spec = native.M4SimulationSpec()
    spec.vertical = (
        native.M4Vertical.CAPITAL_FISCAL
        if fiscal
        else native.M4Vertical.CASH_LOOP
    )
    spec.households = 1
    spec.consumption_firms = 1
    spec.capital_firms = 1 if fiscal else 0
    spec.requested_capabilities = CAPITAL_AND_GOVERNMENT if fiscal else 0
    spec.market_protocol = native.MatchingProtocol.PRICE_SORTED
    spec.seed = 206
    session = native.EngineSession(610 if fiscal else 600)
    session.initialize_simulation(spec)
    result = session.advance_ticks(1, capture_phase_trace=True)
    snapshot = session.simulation_snapshot()
    if result["next_tick"] != 1 or snapshot["tick"] != 1:
        raise AssertionError("native tick did not advance exactly once")
    return snapshot


def compare_case(name: str, actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if len(actual["balances"]) != len(expected["balances"]):
        raise AssertionError(f"{name}.balances: length mismatch")
    for index, (left, right) in enumerate(
        zip(actual["balances"], expected["balances"], strict=True)
    ):
        assert_close(f"{name}.balances[{index}]", left, right)
    household = actual["households"][0]
    for key, value in expected["household"].items():
        assert_close(f"{name}.household.{key}", household[key], value)
    expected_firms = expected.get("firms", [expected.get("firm")])
    for index, wanted in enumerate(expected_firms):
        firm = actual["firms"][index]
        for key, value in wanted.items():
            assert_close(f"{name}.firms[{index}].{key}", firm[key], value)
    assert_close(
        f"{name}.technology_index",
        actual["technology_index"],
        expected["technology_index"],
    )
    assert_close(
        f"{name}.public_capital",
        actual["public_capital"],
        expected["public_capital"],
    )
    if list(actual["rng_counter"]) != expected["rng_counter"]:
        raise AssertionError(
            f"{name}.rng_counter: native={actual['rng_counter']!r} "
            f"python={expected['rng_counter']!r}"
        )
    phase_ids = [int(row["phase"]) for row in actual["phase_trace"]]
    if phase_ids != expected["phase_ids"]:
        raise AssertionError(
            f"{name}.phase_ids: native={phase_ids!r} "
            f"python={expected['phase_ids']!r}"
        )
    for row in actual["phase_trace"]:
        assert_close(f"{name}.phase.money", row["money_total"], expected["metrics"]["total_money"])
    for key, value in expected["metrics"].items():
        assert_close(f"{name}.metrics.{key}", actual["metrics"][key], value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())
    compare_case("v0", run_case(native, fiscal=False), reference_v0())
    compare_case("v1", run_case(native, fiscal=True), reference_v1())
    print(json.dumps({
        "cases": 2,
        "schema_version": "m4-differential-result-v1",
        "status": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
