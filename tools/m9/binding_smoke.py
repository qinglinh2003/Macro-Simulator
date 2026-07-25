from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    import _native as native  # type: ignore[import-not-found]

    return native


def _domestic(native, seed: int):
    spec = native.M8SimulationSpec()
    population = spec.domestic_economy
    monetary = population.financial_economy.monetary_economy
    real = monetary.real_economy
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.households = 12
    real.consumption_firms = 3
    real.capital_firms = 1
    real.seed = seed
    real.requested_capabilities = (1 << 0) | (1 << 1)
    population.population.initial_persons = 24
    population.population.target_household_size = 2.0
    population.rules.fertility = False
    population.rules.mortality = False
    population.rules.marriage = False
    population.rules.divorce = False
    population.rules.annual_churn = 0.0
    spec.energy_rules.producer_count = 1
    return spec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    args = parser.parse_args()
    native = _native(args.native_dir)

    spec = native.M9WorldSpec()
    spec.economies = [_domestic(native, 71), _domestic(native, 72)]
    spec.external_policies = [
        native.ExternalPolicy(),
        native.ExternalPolicy(),
    ]
    spec.rules.trade = True
    spec.rules.fx_trade_cap = 0.5

    world = native.WorldSession.create(spec)
    result = world.advance(2)
    assert world.tick == 2
    assert result["metrics"]["trade_routes"] > 0
    snapshot = world.snapshot()
    assert len(snapshot["rates"]) == 2
    assert len(snapshot["metrics"]["external"]) == 2

    shock = native.ShockSpec()
    shock.id = 71
    shock.kind = native.ShockKind.HOUSEHOLD_DEMAND
    shock.economy_id = 0
    shock.start_tick = 2
    shock.duration = 1
    shock.magnitude = 0.25
    world.schedule_shock(shock)
    event_result = world.advance(1)
    assert event_result["metrics"]["shock_events"] == 2
    events = world.shock_events()
    assert [item["type"] for item in events] == [
        native.ShockEventType.ANNOUNCED,
        native.ShockEventType.STARTED,
    ]

    crisis_options = native.CrisisScenarioOptions()
    crisis_options.start_tick = 20
    crisis_options.first_shock_id = 100
    crisis_options.economies = [0]
    crisis = native.make_crisis_scenario(
        native.CrisisScenario.GLOBAL_FINANCIAL_CRISIS,
        crisis_options,
        2,
    )
    assert len(crisis) == 3
    assert crisis[0].kind == native.ShockKind.CREDIT_SUPPLY
    assert crisis[0].ramp_out_ticks == 90

    checkpoint = world.checkpoint()
    digest = world.digest()
    world.advance(1)
    world.restore_checkpoint(checkpoint)
    assert world.tick == 3
    assert world.digest() == digest
    assert world.checkpoint() == checkpoint
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
