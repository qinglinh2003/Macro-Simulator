from __future__ import annotations

import pickle

import pytest

from macro_sim.checkpoint import load_checkpoint, save_checkpoint, state_digest
from macro_sim.config import Config
from macro_sim.controllers.occupants import HumanQueueOccupant
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.economy import Economy
from macro_sim.shocks import (
    ShockEngine,
    ShockSpec,
    ShockTape,
    ShockTarget,
    generate_poisson_tape,
    natural_disaster_scenario,
)
from macro_sim.world import World


def _linear_config(**overrides):
    values = dict(n_households=24, n_firms=4, n_ticks=20, seed=17)
    values.update(overrides)
    return Config(**values)


def _capital_config(**overrides):
    values = dict(
        n_households=30, n_firms_c=6, n_firms_k=3, n_ticks=20, seed=19,
        firm_full_pnl=True, priced_firm_balance_sheet=True,
        national_accounts_metrics=True,
    )
    values.update(overrides)
    return Config.v124(**values)


def test_tape_is_canonical_roundtrippable_and_order_independent():
    left = ShockSpec("z", "productivity", 3, 0.20, duration_ticks=4)
    right = ShockSpec("a", "productivity", 3, 0.25, duration_ticks=4)
    one = ShockTape((left, right), name="pair")
    two = ShockTape((right, left), name="pair")

    assert one.to_json() == two.to_json()
    assert one.contract_hash == two.contract_hash
    assert ShockTape.from_json(one.to_json()) == one

    engine = ShockEngine(one)
    econ = Economy(_linear_config())
    engine.bind([econ])
    engine.begin_tick(0, [econ])
    engine.begin_tick(1, [econ])
    engine.begin_tick(2, [econ])
    engine.begin_tick(3, [econ])
    assert engine.factor("productivity", 0) == pytest.approx(0.8 * 0.75)


def test_contract_rejects_untyped_targets_unknown_channels_and_capability_mismatch():
    with pytest.raises(TypeError, match="string sequence"):
        ShockTarget(sectors="energy")
    with pytest.raises(ValueError, match="finite"):
        ShockSpec("nan", "productivity", 0, float("nan"))
    with pytest.raises(ValueError, match="unknown shock kind"):
        ShockTape((ShockSpec("unknown", "set_gdp", 0, 0.1),))

    engine = ShockEngine()
    with pytest.raises(ValueError, match="unknown shock channel"):
        engine.factor("unemployment")
    with pytest.raises(ValueError, match="energy_enabled"):
        Economy(_linear_config(), shocks=(ShockSpec(
            "energy", "energy_capacity", 0, 0.2,
            target=ShockTarget(sectors=("energy",)), duration_ticks=1,
        ),))

    running = ShockEngine((ShockSpec(
        "running", "productivity", 0, 0.1, duration_ticks=1,
    ),))
    probe = Economy(_linear_config())
    running.bind([probe])
    running.begin_tick(0, [probe])
    with pytest.raises(ValueError, match="running ShockEngine"):
        Economy(_linear_config(), shocks=running)


def test_no_shock_path_is_exact_and_productivity_prefix_only_diverges_at_start():
    cfg = _linear_config()
    baseline = Economy(cfg)
    shocked = Economy(cfg, shocks=(
        ShockSpec("tfp", "productivity", 3, 0.5, duration_ticks=2),
    ))
    base_records = [baseline.step() for _ in range(6)]
    shock_records = [shocked.step() for _ in range(6)]

    for left, right in zip(base_records[:3], shock_records[:3]):
        # Shock-only observability fields are deliberately additive; the economic
        # record remains exact before the event.
        for key, value in left.items():
            assert right[key] == value
    assert shock_records[3]["real_output"] < base_records[3]["real_output"]
    assert shock_records[3]["shock_productivity_factor"] == pytest.approx(0.5)
    assert shock_records[5]["shock_productivity_factor"] == pytest.approx(1.0)


def test_labor_demand_energy_and_credit_channels_hit_decisions_not_outcomes():
    # Labor availability reduces effective work at the production seam while the
    # contractual employment state remains endogenous.
    base = Economy(_linear_config())
    labor = Economy(_linear_config(), shocks=(
        ShockSpec("labor", "labor_availability", 0, 0.5, duration_ticks=1),
    ))
    assert labor.step()["real_output"] < base.step()["real_output"]

    # Household demand changes desired budgets before the credit phase; it does
    # not set realized consumption.
    from macro_sim.systems.planning import run_planning_phase

    planned_base = Economy(_linear_config())
    planned_shock = Economy(_linear_config(), shocks=(
        ShockSpec("demand", "household_demand", 0, 0.4, duration_ticks=1),
    ))
    planned_shock.shock_engine.begin_tick(0, [planned_shock])
    run_planning_phase(planned_base)
    run_planning_phase(planned_shock)
    assert sum(h.consumption_budget for h in planned_shock.households) == pytest.approx(
        0.6 * sum(h.consumption_budget for h in planned_base.households)
    )

    # Credit supply scales origination, never borrower debt directly.
    from macro_sim.systems.banking import grant_loan

    credit_cfg = Config.v124(
        n_households=20, n_firms_c=4, n_firms_k=2, n_banks=1,
        n_ticks=2, seed=23,
    )
    credit = Economy(credit_cfg, shocks=(
        ShockSpec("credit", "credit_supply", 0, 0.5, duration_ticks=1),
    ))
    credit.shock_engine.begin_tick(0, [credit])
    borrower = credit.c_firms[0]
    before = credit.ledger.debt(borrower.id)
    assert grant_loan(credit, borrower.id, 10.0) == pytest.approx(5.0)
    assert credit.ledger.debt(borrower.id) - before == pytest.approx(5.0)

    # Energy capacity is an overlay: recovery never divides/mutates the anchor.
    energy_cfg = Config.v124(
        n_households=30, n_firms_c=6, n_firms_k=3, n_ticks=3, seed=29,
        energy_enabled=True,
    )
    energy = Economy(energy_cfg, shocks=(
        ShockSpec(
            "energy", "energy_capacity", 0, 0.5,
            target=ShockTarget(sectors=("energy",)), duration_ticks=1,
        ),
    ))
    anchors = [firm.capacity_kappa for firm in energy.e_firms]
    record = energy.step()
    assert record["shock_energy_capacity_factor"] == pytest.approx(0.5)
    assert [firm.capacity_kappa for firm in energy.e_firms] == anchors
    energy.step()
    assert [firm.capacity_kappa for firm in energy.e_firms] == anchors


def test_dynamic_schedule_at_a_live_boundary_and_rejection_are_atomic():
    econ = Economy(_linear_config())
    econ.step()
    econ.step()
    econ.schedule_shock(ShockSpec("now", "productivity", 2, 0.4, duration_ticks=1))
    assert econ.step()["shock_active_count"] == 1.0

    before_hash = econ.shock_engine.contract_hash
    before_tick = econ.t
    with pytest.raises(ValueError, match="past"):
        econ.schedule_shock(ShockSpec("past", "productivity", 1, 0.1, duration_ticks=1))
    assert econ.shock_engine.contract_hash == before_hash
    assert econ.t == before_tick


def test_rejected_first_schedule_does_not_attach_an_empty_runtime_engine():
    econ = Economy(_linear_config())
    econ.step()
    assert econ.shock_engine is None
    with pytest.raises(ValueError, match="past"):
        econ.schedule_shock(ShockSpec(
            "past", "productivity", 0, 0.1, duration_ticks=1,
        ))
    assert econ.shock_engine is None

    world = World([_linear_config()])
    with pytest.raises(ValueError, match="trade layer"):
        world.schedule_shock(ShockSpec(
            "invalid_trade", "import_capacity", 0, 0.1, duration_ticks=1,
        ))
    assert world.shock_engine is None
    assert all(item.shock_engine is None for item in world.economies)


def test_capital_destruction_is_one_shot_conserving_and_checkpoint_exact(tmp_path):
    tape = ShockTape((
        ShockSpec(
            "disaster", "capital_destruction", 2, 0.2,
            target=ShockTarget(sectors=("consumption",)), duration_ticks=1,
        ),
    ))
    econ = Economy(_capital_config(), shocks=tape)
    econ.step()
    econ.step()
    opening_money = econ.ledger.total_money
    opening_capital = sum(f.capital for f in econ.c_firms)
    econ.shock_engine.begin_tick(econ.t, [econ])
    assert econ.ledger.total_money == opening_money
    event_record = econ.step()
    assert event_record["shock_capital_destroyed"] == pytest.approx(opening_capital * 0.2)
    assert event_record["conservation_drift"] < 1e-9

    path = tmp_path / "shock.msim"
    save_checkpoint(str(path), econ, tick=econ.t)
    resumed, _sidecar, _header = load_checkpoint(str(path))
    uninterrupted = [econ.step() for _ in range(4)]
    continued = [resumed.step() for _ in range(4)]
    assert pickle.dumps(uninterrupted, protocol=5) == pickle.dumps(continued, protocol=5)
    assert state_digest(econ) == state_digest(resumed)
    assert [e["event_type"] for e in resumed.shock_engine.events.events].count("realized") == 1
    resumed.shock_engine.events.verify()


def test_world_trade_shocks_target_importer_and_exporter_without_money_drift():
    cfg = Config.v124(
        n_households=30, n_firms_c=6, n_firms_k=3, n_ticks=3, seed=5,
    )
    baseline = World([cfg, cfg], base_seed=100, trade=True)
    shocked = World([cfg, cfg], base_seed=100, trade=True, shocks=(
        ShockSpec(
            "imports", "import_capacity", 0, 0.5,
            target=ShockTarget((0,)), duration_ticks=2,
        ),
        ShockSpec(
            "exports", "export_capacity", 0, 0.5,
            target=ShockTarget((1,)), duration_ticks=2,
        ),
    ))
    baseline.step()
    records = shocked.step()
    assert shocked._prev_import_volume[0] < baseline._prev_import_volume[0]
    assert records[0]["conservation_drift"] < 1e-9
    assert records[1]["conservation_drift"] < 1e-9


def test_announcement_visibility_has_no_future_leak_and_routes_emergency():
    tape = ShockTape((
        ShockSpec(
            "known", "productivity", 2, 0.3, duration_ticks=3,
            announcement_tick=1,
        ),
        ShockSpec(
            "classified", "productivity", 2, 0.2, duration_ticks=3,
            announcement_tick=0, visibility="confidential", roles=("treasury",),
        ),
    ))
    world = World([_linear_config()], shocks=tape)
    from macro_sim.controllers.observation import DEFAULT_OBSERVATION_SPEC, ReleaseService

    releases = ReleaseService(DEFAULT_OBSERVATION_SPEC)
    public0 = releases.observe(world, 0, economy_id=0, role="public")
    treasury0 = releases.observe(world, 0, economy_id=0, role="treasury")
    assert not public0.shock_bulletins
    assert [item["shock_id"] for item in treasury0.shock_bulletins] == ["classified"]
    assert public0.release("shock_announced_count").value == 0.0

    world.step()
    public1 = releases.observe(world, 1, economy_id=0, role="public")
    assert [item["shock_id"] for item in public1.shock_bulletins] == ["known"]
    assert public1.release("shock_productivity").value == pytest.approx(0.3)

    emergency_world = World([_linear_config()], shocks=(
        ShockSpec("crisis", "productivity", 0, 0.3, duration_ticks=2),
    ))
    session = ControlledSimulationSession(emergency_world, run_mode="interactive")
    session.assign_seat(0, "treasury", HumanQueueOccupant(), actor="test")
    result = session.advance()
    emergency = [context for context in result.contexts if context.emergency]
    assert emergency
    assert emergency[0].emergency_trigger == "exogenous_supply_crisis"
    assert emergency[0].emergency_bulletin["shock_bulletins"][0]["shock_id"] == "crisis"

    # The controller-wide replay/info stream has no seat authorization context.
    # Classified transitions therefore remain in the internal ShockEngine chain
    # and never appear in that global stream.
    classified_session = ControlledSimulationSession(World(
        [_linear_config()],
        shocks=(ShockSpec(
            "secret", "productivity", 0, 0.3, duration_ticks=1,
            visibility="confidential", roles=("treasury",),
        ),),
    ))
    classified_session.run(1)
    assert any(
        item["shock_id"] == "secret"
        for item in classified_session.world.shock_engine.events.events
    )
    assert not any(
        item["event_type"].startswith("shock_")
        for item in classified_session.events.events
    )


def test_controller_event_replay_regenerates_shock_transitions():
    tape = ShockTape((
        ShockSpec("pulse", "productivity", 1, 0.3, duration_ticks=2),
    ))
    source = ControlledSimulationSession(World([_linear_config()], shocks=tape))
    source.run(4)
    expected = list(source.events.events)
    assert any(item["event_type"] == "shock_started" for item in expected)
    assert any(item["event_type"] == "shock_ended" for item in expected)

    replay = ControlledSimulationSession(World([_linear_config()], shocks=tape))
    replay_input_events(
        replay, source.events.input_events(), until_tick=4, expected_events=expected,
    )
    assert replay.events.events == expected
    assert state_digest(replay.world) == state_digest(source.world)


def test_seeded_generator_materializes_deterministic_events_and_scenarios_are_generic():
    first = generate_poisson_tape(
        seed=41, kind="productivity", start_tick=0, end_tick=2_000,
        annual_rate=2.0, magnitude_range=(0.1, 0.2), duration_range=(10, 30),
    )
    second = generate_poisson_tape(
        seed=41, kind="productivity", start_tick=0, end_tick=2_000,
        annual_rate=2.0, magnitude_range=(0.1, 0.2), duration_range=(10, 30),
    )
    assert first.contract_hash == second.contract_hash
    assert first.specs
    assert all(item.source == "seeded_poisson_generator" for item in first.specs)

    disaster = natural_disaster_scenario(start_tick=5)
    assert {item.kind for item in disaster.specs} == {
        "capital_destruction", "labor_availability", "productivity",
    }
    assert all("policy" not in item.kind for item in disaster.specs)
