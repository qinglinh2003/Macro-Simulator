#!/usr/bin/env python3
"""Run deterministic public-interface semantic checks for M6."""

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
    real.households = 56
    real.consumption_firms = 8
    real.capital_firms = 3
    real.requested_capabilities = 3
    real.market_protocol = native.MatchingProtocol.PRICE_SORTED
    real.seed = seed
    monetary_policy = native.M5Policy()
    monetary_policy.government_consumption_share = 0.0
    monetary_policy.government_deficit_target = 0.10
    monetary_rules = native.M5Rules()
    monetary_rules.bank_count = 4
    monetary_rules.opening_capital_per_bank = 30.0
    monetary = native.M5SimulationSpec()
    monetary.real_economy = real
    monetary.policy = monetary_policy
    monetary.rules = monetary_rules
    monetary.initial_policy_rate = 0.002
    rules = native.M6Rules()
    rules.watchlist_size = 5
    rules.entry_beta = 0.0
    rules.bank_entry_beta = 0.0
    value = native.M6SimulationSpec()
    value.monetary_economy = monetary
    value.rules = rules
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    arguments = parser.parse_args()
    native = load_native(arguments.native_dir.resolve())

    low_rate = native.m6_bond_price(100.0, 365, 0.001, 0.0001)
    high_rate = native.m6_bond_price(100.0, 365, 0.01, 0.0001)
    if high_rate >= low_rate:
        raise AssertionError("rate increase did not lower bond value")

    session = native.M6Session(6601)
    session.initialize_m6(make_spec(native, 6601))
    result = session.advance_m6_ticks(12)
    metrics = result["metrics"]
    snapshot = session.m6_snapshot()
    if metrics["bond_issuance"] < 0.0:
        raise AssertionError("bond issuance has an invalid sign")
    if abs(metrics["clearing_residual"]) > 1.0e-7:
        raise AssertionError("equity clearing account did not close")
    if len(snapshot["equities"]) != 12:
        raise AssertionError("firm or bank equity genesis is incomplete")
    if not snapshot["firm_statements"]:
        raise AssertionError("priced firm statements are absent")
    if any(item["fundamental"] < 0.0 for item in snapshot["equities"]):
        raise AssertionError("equity fundamental is negative")
    if any(
        item["outstanding_shares"] <= 0.0
        for item in snapshot["equities"]
        if item["active"]
    ):
        raise AssertionError("active equity has no outstanding shares")

    policy = native.M6Policy()
    policy.margin_ltv = 0.40
    policy.bond_maturity_days = 20
    session.update_m6_policy(policy)
    resumed = session.advance_m6_ticks(1)
    if resumed["next_tick"] != 13:
        raise AssertionError("M6 policy update interrupted advancement")

    print(json.dumps({
        "schema_version": "m6-semantic-panel-v1",
        "status": "passed",
        "checks": 8,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
