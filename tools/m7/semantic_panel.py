#!/usr/bin/env python3
"""Run deterministic public-interface semantic checks for M7."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def make_spec(native, seed: int):
    real = native.M4SimulationSpec()
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.consumption_firms = 8
    real.capital_firms = 3
    real.requested_capabilities = 3
    real.market_protocol = native.MatchingProtocol.PRICE_SORTED
    real.seed = seed
    monetary_rules = native.M5Rules()
    monetary_rules.bank_count = 4
    monetary_rules.opening_capital_per_bank = 30.0
    monetary = native.M5SimulationSpec()
    monetary.real_economy = real
    monetary.rules = monetary_rules
    monetary.initial_policy_rate = 0.002
    financial_rules = native.M6Rules()
    financial_rules.watchlist_size = 5
    financial_rules.entry_beta = 0.0
    financial_rules.bank_entry_beta = 0.0
    financial = native.M6SimulationSpec()
    financial.monetary_economy = monetary
    financial.rules = financial_rules
    population = native.M7PopulationSpec()
    population.initial_persons = 128
    population.target_household_size = 2.5
    population.start_calendar_day = 29
    rules = native.M7Rules()
    rules.fertility = False
    rules.mortality = False
    rules.annual_churn = 0.0
    rules.marriage_interval_days = 30
    rules.annual_marriage_rate = 1.0
    value = native.M7SimulationSpec()
    value.financial_economy = financial
    value.population = population
    value.rules = rules
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())

    session = native.M7Session(7701)
    session.initialize_m7(make_spec(native, 7701))
    result = session.advance_m7_ticks(12)
    metrics = result["metrics"]
    snapshot = session.m7_snapshot()
    if metrics["population"] != 128:
        raise AssertionError("population identity changed unexpectedly")
    if metrics["employed_heads"] <= 0.0:
        raise AssertionError("persistent employment is absent")
    if metrics["labor_supply"] <= 0.0:
        raise AssertionError("labor supply is absent")
    if not snapshot["jobs"]:
        raise AssertionError("job view is empty")
    if not snapshot["persons"]:
        raise AssertionError("person view is empty")
    if len(snapshot["persons"]) != 128:
        raise AssertionError("person view is incomplete")
    if abs(metrics["beneficial_projection_error"]) > 1.0e-8:
        raise AssertionError("beneficial ownership projection drifted")

    policy = native.M7Policy()
    policy.inheritance_tax_rate = 0.20
    session.update_m7_policy(policy)
    resumed = session.advance_m7_ticks(1)
    if resumed["next_tick"] != 13:
        raise AssertionError("M7 policy update interrupted advancement")

    print(json.dumps({
        "schema_version": "m7-semantic-panel-v1",
        "status": "passed",
        "checks": 8,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
