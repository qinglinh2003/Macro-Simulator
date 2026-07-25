#!/usr/bin/env python3
"""Run deterministic public-interface semantic checks for M8."""

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
    monetary_rules.opening_capital_per_bank = 1000.0
    monetary_rules.household_credit = True
    monetary_rules.household_amortization = 0.0
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
    population_rules = native.M7Rules()
    population_rules.fertility = False
    population_rules.mortality = False
    population_rules.annual_churn = 0.0
    population_rules.marriage = False
    population_rules.divorce = False
    domestic = native.M7SimulationSpec()
    domestic.financial_economy = financial
    domestic.population = population
    domestic.rules = population_rules
    energy_rules = native.EnergyRules()
    energy_rules.producer_count = 3
    energy_rules.deprivation = False
    housing_rules = native.HousingRules()
    housing_rules.enabled = True
    housing_rules.resale_market = True
    housing_rules.rentals = True
    housing_rules.initial_homeownership_share = 0.75
    housing_rules.market_interval_days = 1
    housing_policy = native.HousingPolicy()
    housing_policy.property_tax_rate = 0.001
    value = native.M8SimulationSpec()
    value.domestic_economy = domestic
    value.energy_rules = energy_rules
    value.housing_rules = housing_rules
    value.housing_policy = housing_policy
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())

    session = native.M8Session(8801)
    session.initialize_m8(make_spec(native, 8801))
    result = session.advance_m8_ticks(12)
    metrics = result["metrics"]
    snapshot = session.m8_snapshot()
    if metrics["economy"]["population"] != 128:
        raise AssertionError("population identity changed unexpectedly")
    if metrics["energy"]["capacity"] <= 0.0:
        raise AssertionError("energy capacity is absent")
    if metrics["housing"]["housing_stock"] <= 0.0:
        raise AssertionError("housing stock is absent")
    if (
        len(snapshot["dwellings"])
        != int(metrics["housing"]["housing_stock"])
    ):
        raise AssertionError("dwelling view and housing stock diverged")
    if not snapshot["energy_producers"]:
        raise AssertionError("energy producer view is empty")
    if len(snapshot["persons"]) != 128:
        raise AssertionError("population view is incomplete")

    energy_policy = native.EnergyPolicy()
    energy_policy.excise_rate = 0.05
    energy_policy.strategic_reserve_target = 10.0
    energy_policy.strategic_reserve_flow_cap = 1.0
    session.update_m8_energy_policy(energy_policy)
    housing_policy = native.HousingPolicy()
    housing_policy.property_tax_rate = 0.002
    session.update_m8_housing_policy(housing_policy)
    energy_input = native.EnergyInput()
    energy_input.supply_multiplier = 0.9
    session.update_m8_energy_input(energy_input)
    housing_input = native.HousingInput()
    housing_input.buyer_demand_multiplier = 1.1
    session.update_m8_housing_input(housing_input)
    resumed = session.advance_m8_ticks(1)
    if resumed["next_tick"] != 13:
        raise AssertionError("M8 live updates interrupted advancement")

    clone = native.M8Session(8802)
    clone.restore_checkpoint(session.checkpoint())
    if clone.digest() != session.digest():
        raise AssertionError("M8 checkpoint changed canonical state")
    clone.advance_m8_ticks(2)
    session.advance_m8_ticks(2)
    if clone.digest() != session.digest():
        raise AssertionError("M8 checkpoint continuation diverged")

    print(
        json.dumps(
            {
                "schema_version": "m8-semantic-panel-v1",
                "status": "passed",
                "checks": 10,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
