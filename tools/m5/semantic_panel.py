#!/usr/bin/env python3
"""Run deterministic public-interface semantic checks for M5."""

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
    real.households = 48
    real.consumption_firms = 8
    real.capital_firms = 3
    real.requested_capabilities = 3
    real.market_protocol = native.MatchingProtocol.PRICE_SORTED
    real.seed = seed
    rules = native.M5Rules()
    rules.bank_count = 3
    rules.opening_capital_per_bank = 30.0
    value = native.M5SimulationSpec()
    value.real_economy = real
    value.rules = rules
    return value


def run_fiscal(native, share: float) -> dict[str, object]:
    spec = make_spec(native, 5501)
    policy = native.M5Policy()
    policy.government_consumption_share = share
    spec.policy = policy
    session = native.EngineSession(5501)
    session.initialize_m5(spec)
    return session.advance_m5_ticks(1)["metrics"]

def run_policy(native, policy, ticks: int = 1, households: int = 48):
    spec = make_spec(native, 5503)
    spec.real_economy.households = households
    spec.policy = policy
    session = native.EngineSession(5503)
    session.initialize_m5(spec)
    result = session.advance_m5_ticks(ticks)
    return result["metrics"], session.m5_snapshot()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())

    low = run_fiscal(native, 0.05)
    high = run_fiscal(native, 0.35)
    if high["economy"]["government_spending"] <= low["economy"]["government_spending"]:
        raise AssertionError("fiscal expansion did not raise government spending")
    if high["economy"]["nominal_output"] <= low["economy"]["nominal_output"]:
        raise AssertionError("fiscal expansion did not raise nominal demand")

    flat = native.M5Policy()
    progressive = native.M5Policy()
    progressive.income_allowance = 1.0
    flat_metrics, _ = run_policy(native, flat)
    progressive_metrics, _ = run_policy(native, progressive)
    if progressive_metrics["economy"]["tax_total"] >= flat_metrics["economy"]["tax_total"]:
        raise AssertionError("income allowance did not reduce household tax")

    wage_floor = native.M5Policy()
    wage_floor.minimum_wage = 3.0
    _, wage_snapshot = run_policy(native, wage_floor)
    if min(firm["wage"] for firm in wage_snapshot["firms"]) < 3.0:
        raise AssertionError("minimum wage did not bind posted wages")

    deficit = native.M5Policy()
    deficit.government_consumption_share = 0.0
    deficit.government_deficit_target = 0.10
    deficit_metrics, _ = run_policy(native, deficit, ticks=2)
    if deficit_metrics["economy"]["government_spending"] <= 0.0:
        raise AssertionError("deficit target did not fund procurement")

    guarantee = native.M5Policy()
    guarantee.job_guarantee = True
    guarantee.job_guarantee_wage_ratio = 1.0
    guarantee.job_guarantee_public_works_share = 1.0
    oversupply_metrics, _ = run_policy(native, flat, households=480)
    guarantee_metrics, _ = run_policy(
        native,
        guarantee,
        households=480,
    )
    if guarantee_metrics["economy"]["government_spending"] <= oversupply_metrics["economy"]["government_spending"]:
        raise AssertionError("job guarantee did not raise public outlays")
    if guarantee_metrics["economy"]["public_capital"] <= oversupply_metrics["economy"]["public_capital"]:
        raise AssertionError("job guarantee did not create public works")

    session = native.EngineSession(5502)
    session.initialize_m5(make_spec(native, 5502))
    policy = native.M5Policy()
    policy.monetary_regime = native.MonetaryRegime.MANUAL
    policy.manual_policy_rate = 0.04
    session.update_m5_policy(policy)
    result = session.advance_m5_ticks(1)
    if result["metrics"]["policy_rate"] != 0.04:
        raise AssertionError("manual monetary regime did not pin the rate")
    snapshot = session.m5_snapshot()
    if len(snapshot["banks"]) != 3 or snapshot["tick"] != 1:
        raise AssertionError("M5 public snapshot is incomplete")

    print(json.dumps({
        "schema_version": "m5-semantic-panel-v1",
        "status": "passed",
        "checks": 10,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
