#!/usr/bin/env python3
"""Run deterministic public-interface semantic checks for M9."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    import _native as native  # type: ignore[import-not-found]

    return native


def _domestic(native, seed: int, wage: float):
    spec = native.M8SimulationSpec()
    population = spec.domestic_economy
    monetary = population.financial_economy.monetary_economy
    real = monetary.real_economy
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.households = 16
    real.consumption_firms = 4
    real.capital_firms = 1
    real.seed = seed
    real.requested_capabilities = 3
    real.rules.initial_wage = wage
    population.population.initial_persons = 32
    population.population.target_household_size = 2.0
    population.rules.fertility = False
    population.rules.mortality = False
    population.rules.marriage = False
    population.rules.divorce = False
    population.rules.annual_churn = 0.0
    spec.energy_rules.producer_count = 1
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", type=Path, required=True)
    arguments = parser.parse_args()
    native = _native(arguments.native_dir.resolve())

    policies = [native.ExternalPolicy() for _ in range(3)]
    policies[0].tariff = 0.1
    policies[1].fx_regime = native.FxRegime.PEG
    policies[1].peg_anchor = 2
    spec = native.M9WorldSpec()
    spec.economies = [
        _domestic(native, 9101, 1.0),
        _domestic(native, 9102, 1.5),
        _domestic(native, 9103, 2.0),
    ]
    spec.external_policies = policies
    spec.rules.trade = True
    spec.rules.capital = True
    spec.rules.migration = True
    spec.rules.fx_trade_cap = 0.5
    spec.rules.capital_mobility = 0.25
    spec.rules.migration_rate = 0.04
    spec.rules.wage_smoothing = 1.0
    world = native.WorldSession.create(spec)

    options = native.CrisisScenarioOptions()
    options.start_tick = 3
    options.announcement_lead_ticks = 1
    options.first_shock_id = 500
    for shock in native.make_crisis_scenario(
        native.CrisisScenario.GLOBAL_FINANCIAL_CRISIS,
        options,
        3,
    ):
        world.schedule_shock(shock)

    first = world.advance(8, worker_count=1)
    snapshot = world.snapshot()
    if world.tick != 8 or len(snapshot["rates"]) != 3:
        raise AssertionError("M9 World did not advance all economies")
    if not world.shock_events():
        raise AssertionError("M9 shock lifecycle did not publish events")
    if not any(
        item["migrant_stock_abroad"] > 0.0
        for item in first["metrics"]["external"]
    ):
        raise AssertionError("M9 migration path is not live")

    checkpoint = world.checkpoint()
    parallel = native.WorldSession.create(spec)
    parallel.restore_checkpoint(checkpoint)
    serial = native.WorldSession.create(spec)
    serial.restore_checkpoint(checkpoint)
    parallel.advance(5, worker_count=8)
    serial.advance(5, worker_count=1)
    if parallel.checkpoint() != serial.checkpoint():
        raise AssertionError("M9 worker count changed semantics")
    print(
        json.dumps(
            {
                "digest": parallel.digest(),
                "economies": 3,
                "schema_version": "m9-semantic-panel-v1",
                "status": "passed",
                "tick": parallel.tick,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
