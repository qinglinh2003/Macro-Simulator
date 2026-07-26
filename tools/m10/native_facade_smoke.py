from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.desktop.new_game import NewGameSpec
    from macro_sim.controllers.native_observation import NativeObservationSource
    from macro_sim.diagnostics import (
        NativeDeepProbeCollector,
        NativeWorldProbeCollector,
    )
    from macro_sim.core.external_policy import ExternalPolicy
    from macro_sim.core.policy import Policy
    from macro_sim.core.policy_registry import REGISTRY
    from macro_sim.native_backend import (
        NATIVE_POLICY_LEVERS,
        NativeSimulationSession,
        build_world_spec,
    )

    for scenario in ("sandbox", "oil", "gfc", "pandemic", "disaster"):
        spec = replace(NewGameSpec.default(seed=941), scenario=scenario)
        world_spec = build_world_spec(spec)
        assert len(world_spec.economies) == len(spec.countries)
        assert len(world_spec.external_policies) == len(spec.countries)
        if scenario != "sandbox":
            assert world_spec.shocks

    spec = NewGameSpec.default(seed=942)
    session = NativeSimulationSession.create(spec)
    assert session.tick == 0
    assert session.history_bounds()["capacity"] == 2048
    assert (
        session.history_bounds()["retained_bytes"]
        <= 8 * 1024 * 1024 * int(session.maintained_metrics()["economy_count"])
    )
    assert set(NATIVE_POLICY_LEVERS) == set(REGISTRY)
    opening_policy = Policy.from_config(spec.configs()[0])
    opening_external = ExternalPolicy()
    for lever_name, lever in REGISTRY.items():
        source = opening_external if lever.scope == "external" else opening_policy
        session._policy_batch((
            {"lever": lever_name, "value": getattr(source, lever_name)},
        ))
    session.advance(actions=(
        {"lever": "tax_income_rate", "value": 0.31},
        {"lever": "tariff", "value": 0.08},
    ))
    assert session.tick == 1
    assert (
        session.bridge.domestic_policy(0).fiscal_monetary.income_tax_rate
        == 0.31
    )
    assert session.bridge.external_policies()[0].tariff == 0.08
    generation = session.bridge.policy_generation
    session.advance()
    assert session.tick == 2
    assert session.bridge.policy_generation == generation
    maintained = session.maintained_metrics()
    assert maintained["tick"] == session.tick
    assert all(len(row) == 300 for row in maintained["economies"])
    assert (
        maintained["economies"][0]["metric.source.m4.real_output"]
        == maintained["economies"][0]["metric.economy.real_output"]
    )
    assert "metric.source.m8.housing.house_price" in (
        maintained["economies"][0]
    )
    assert (
        maintained["economies"][0][
            "metric.economy.na.expenditure_reconciled_nominal"
        ]
        == maintained["economies"][0]["metric.economy.na.nominal_gdp"]
    )
    household_page = session.probe_page(
        "households", economy_id=0, maximum_rows=3,
    )
    assert household_page["boundary"] == session.tick
    assert 0 < len(household_page["rows"]) <= 3
    assert household_page["rows"][0]["id"] > 0
    person_page = session.probe_page(
        "persons", economy_id=0, maximum_rows=3,
    )
    assert person_page["rows"][0]["gross_assets"] >= 0.0
    equity_page = session.probe_page(
        "equities", economy_id=0, maximum_rows=3,
    )
    assert equity_page["rows"]
    assert equity_page["rows"][0]["price"] >= 0.0
    position_page = session.probe_page(
        "security_positions", economy_id=0, maximum_rows=3,
    )
    assert position_page["rows"]
    assert position_page["rows"][0]["market_value"] >= 0.0
    economy_diagnostic = session.probe_economy_diagnostics(0)
    assert economy_diagnostic["households"] > 0
    assert economy_diagnostic["peg_count"] == 0
    assert economy_diagnostic["pegs_intact"]
    diagnostic = NativeDeepProbeCollector().collect(session)
    assert diagnostic.boundary == session.tick
    assert diagnostic.aggregates["households"] > 0
    world_probe = NativeWorldProbeCollector(session)
    decomposition = world_probe.step()
    assert decomposition["next_tick"] == decomposition["first_tick"] + 1

    cloned = session.clone()
    cloned.advance()
    session.advance()
    assert cloned.native_snapshot()["digest"] == session.native_snapshot()["digest"]
    assert cloned.history_bounds() == session.history_bounds()

    sequential = NativeSimulationSession.create(
        spec, history_capacity_frames=32,
    )
    batched = NativeSimulationSession.create(
        spec, history_capacity_frames=32,
    )
    for _ in range(15):
        sequential.advance()
    batch_result = batched.advance(15)
    assert batch_result["advanced_ticks"] == 15
    assert batched.native_snapshot()["digest"] == (
        sequential.native_snapshot()["digest"]
    )
    assert batched.history_bounds() == sequential.history_bounds()
    assert batched.history_page(0, 32)["frames"] == (
        sequential.history_page(0, 32)["frames"]
    )

    checkpoint = session.checkpoint(b'{"objective":"native"}')
    restored, objective = NativeSimulationSession.restore(spec, checkpoint)
    assert restored.tick == session.tick
    assert objective == b'{"objective":"native"}'
    assert restored.native_snapshot()["digest"] == session.native_snapshot()["digest"]

    wrapped = NativeSimulationSession.create(
        spec, history_capacity_frames=2,
    )
    wrapped.advance(3)
    assert wrapped.history_bounds()["oldest_sequence"] > 0
    wrapped_source = NativeObservationSource(wrapped)
    assert wrapped_source.boundary_tick == wrapped.tick
    assert wrapped_source.economies[0].records
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
