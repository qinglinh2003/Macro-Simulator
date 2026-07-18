"""C3/C4 context metadata, observation isolation, and reserve ownership gates."""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pytest

from macro_sim.config import Config
from macro_sim.controllers import OracleObservation, PublicObservation
from macro_sim.controllers.coordinator import policy_key
from macro_sim.controllers.observation import (
    DEFAULT_OBSERVATION_SPEC,
    InstitutionObservation,
    ObservationFieldSpec,
    ObservationSpec,
    Release,
    ReleaseService,
)
from macro_sim.controllers.protocol import DecisionContext
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


def _session() -> ControlledSimulationSession:
    cfg = Config.v13(
        seed=991,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
    )
    return ControlledSimulationSession(World([cfg]))


def test_context_snapshots_observation_and_governance_metadata_deeply():
    session = _session()
    lever = "gov_consumption_share"
    session.coordinator.last_effective_tick[policy_key(0, lever)] = -10
    raw_observation = {"nested": {"values": [1, 2]}}

    context = session.coordinator.open_context(
        session,
        0,
        "treasury",
        "fiscal_stance",
        raw_observation,
        expires_at_tick=2,
    )
    raw_observation["nested"]["values"].append(99)

    assert context.to_dict()["observation"] == {"nested": {"values": [1, 2]}}
    assert context.last_effective_ticks[lever] == -10
    assert context.next_eligibility_ticks[lever] == 35
    assert context.admin_capacity == 18.0
    assert context.admin_remaining == 18.0
    assert context.admin_reserved == 0.0
    estimate = context.visible_cost_estimates[lever]
    assert estimate["cost_class"] == "ordinary"
    assert estimate["admin_if_changed"] == pytest.approx(1.25)
    assert estimate["adjustment_for_one_control_step"] == pytest.approx(0.27)
    assert context.emergency_bulletin is None

    owned = {
        name for name, spec in REGISTRY.items()
        if spec.owner_role == "treasury"
    }
    expected_versions = owned | {
        prerequisite
        for name in owned
        for prerequisite in REGISTRY[name].enabled_if
    }
    assert set(context.current_policy) == owned
    assert set(context.last_effective_ticks) == owned
    assert set(context.next_eligibility_ticks) == owned
    assert set(context.policy_versions) == expected_versions
    snapshotted_value = context.current_policy[lever]
    session.world.economies[0].policy.gov_consumption_share = (
        float(snapshotted_value) + 0.01
    )
    assert context.current_policy[lever] == snapshotted_value

    with pytest.raises(TypeError):
        context.observation["nested"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        context.current_policy[lever] = 999  # type: ignore[index]
    with pytest.raises(TypeError):
        context.pending_effective_ticks[lever] = 999  # type: ignore[index]
    with pytest.raises(TypeError):
        context.visible_cost_estimates[lever]["cost_class"] = "major"  # type: ignore[index]

    restored = pickle.loads(pickle.dumps(context, protocol=5))
    assert restored.to_json() == context.to_json()


def test_emergency_context_contains_server_generated_structured_bulletin():
    session = _session()
    context = session.coordinator.open_context(
        session,
        0,
        "treasury",
        "emergency",
        {},
        expires_at_tick=3,
        emergency=True,
        emergency_trigger="energy_shortage",
    )

    assert dict(context.emergency_bulletin) == {
        "decision_group": "emergency",
        "expires_at_tick": 3,
        "generated_at_tick": 0,
        "trigger_id": "energy_shortage",
    }
    assert context.to_dict()["emergency_bulletin"]["trigger_id"] == "energy_shortage"


def test_release_values_and_typed_observations_are_deeply_immutable_and_labelled():
    raw = {"path": [1, {"x": 2}]}
    release = Release("x", raw, 0, 0, released_at_tick=1)
    raw["path"].append(3)
    observation = InstitutionObservation(1, 0, "treasury", (release,))

    assert observation.to_dict()["releases"][0]["value"] == {
        "path": [1, {"x": 2}],
    }
    with pytest.raises(TypeError):
        release.value["path"] = ()  # type: ignore[index]
    restored = pickle.loads(pickle.dumps(observation, protocol=5))
    assert restored.to_json() == observation.to_json()

    engine = SimpleNamespace(records=[{"t": 0, "x": 1.0, "truth": 2.0}])
    service = ReleaseService(ObservationSpec((
        ObservationFieldSpec("x", "x"),
        ObservationFieldSpec("truth", "truth", access_class="oracle"),
    )))
    public = service.observe(engine, 1, role="public")
    oracle = service.observe_oracle(engine, 1)
    assert isinstance(public, PublicObservation)
    assert public.observation_kind == "public"
    assert isinstance(oracle, OracleObservation)
    assert oracle.observation_kind == "oracle"
    assert oracle.release("truth").value == 2.0


def test_oracle_observation_is_rejected_from_ordinary_decision_context():
    session = _session()
    engine = SimpleNamespace(records=[{"t": 0, "truth": 2.0}])
    service = ReleaseService(ObservationSpec((
        ObservationFieldSpec("truth", "truth", access_class="oracle"),
    )))
    oracle = service.observe_oracle(engine, 1)

    with pytest.raises(ValueError, match="cannot enter"):
        session.coordinator.open_context(
            session,
            0,
            "treasury",
            "fiscal_stance",
            oracle,
            expires_at_tick=1,
        )


def test_fx_reserves_are_visible_only_to_the_owning_pegger_central_bank():
    economies = [
        SimpleNamespace(external_policy=SimpleNamespace(fx_regime="float"), records=[]),
        SimpleNamespace(external_policy=SimpleNamespace(fx_regime="peg"), records=[]),
        SimpleNamespace(external_policy=SimpleNamespace(fx_regime="float"), records=[]),
    ]
    world = SimpleNamespace(
        economies=economies,
        world_records=[{
            "t": 0,
            "reserves_by_economy": {0: 0.0, 1: 125.0, 2: 0.0},
        }],
    )
    spec = ObservationSpec((ObservationFieldSpec(
        "fx_reserves",
        "reserves_by_economy",
        source="world",
        economy_indexed=True,
        access_class="operational",
        roles=frozenset({"central_bank"}),
    ),))
    service = ReleaseService(spec)

    assert service.observe(
        world, 1, economy_id=0, role="central_bank",
    ).release("fx_reserves").value == 0.0
    assert service.observe(
        world, 1, economy_id=1, role="central_bank",
    ).release("fx_reserves").value == 125.0
    assert service.observe(
        world, 1, economy_id=2, role="central_bank",
    ).release("fx_reserves").value == 0.0
    assert service.observe(
        world, 1, economy_id=1, role="treasury",
    ).release("fx_reserves").missing_reason == "access_denied"


def test_legacy_scalar_fx_reserve_record_is_explicitly_missing_not_live_inferred():
    economies = [
        SimpleNamespace(external_policy=SimpleNamespace(fx_regime="float"), records=[]),
        SimpleNamespace(external_policy=SimpleNamespace(fx_regime="peg"), records=[]),
    ]
    world = SimpleNamespace(
        economies=economies,
        world_records=[{"t": 0, "reserves": 125.0}],
    )
    spec = ObservationSpec((ObservationFieldSpec(
        "fx_reserves",
        "reserves_by_economy",
        source="world",
        economy_indexed=True,
        access_class="operational",
        roles=frozenset({"central_bank"}),
    ),))

    for economy_id in range(2):
        release = ReleaseService(spec).observe(
            world, 1, economy_id=economy_id, role="central_bank",
        ).release("fx_reserves")
        assert release.value is None
        assert release.missing_reason == "source_missing"


def _reserve_world() -> World:
    cfg = Config.v3(
        seed=0,
        n_households=4,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        n_ticks=4,
        government=True,
        central_bank=False,
        r_interest=0.0,
    )
    return World(
        [cfg, cfg, cfg],
        base_seed=31,
        couple=True,
        capital=True,
        capital_mobility=0.0,
        fx_lambda=0.0,
        peg=True,
        peg_economy=0,
        peg_anchor=2,
        peg_reserves0=100.0,
    )


def test_session_created_after_world_run_backfills_recorded_reserve_owner():
    world = _reserve_world()
    world.step()
    session = ControlledSimulationSession(world)

    owner = session.release_service.observe(
        world, world.t, economy_id=0, role="central_bank",
    ).release("fx_reserves")
    never_owner = session.release_service.observe(
        world, world.t, economy_id=1, role="central_bank",
    ).release("fx_reserves")

    assert owner.value == pytest.approx(100.0)
    assert never_owner.value == 0.0


def test_new_release_service_backfills_peg_handoff_from_recorded_ownership():
    world = _reserve_world()
    world.step()
    world.economies[0].external_policy.fx_regime = "float"
    world.economies[1].external_policy.peg_anchor = 2
    world.economies[1].external_policy.fx_regime = "peg"
    world.step()
    service = ReleaseService(DEFAULT_OBSERVATION_SPEC)

    service.observe(world, world.t, economy_id=0, role="central_bank")
    service.observe(world, world.t, economy_id=1, role="central_bank")
    owner_zero = service.history(0, "fx_reserves")
    owner_one = service.history(1, "fx_reserves")

    assert [item.value for item in owner_zero] == pytest.approx([100.0, 100.0])
    assert [item.value for item in owner_one] == pytest.approx([0.0, 100.0])
    assert world.world_records[0]["reserves_by_economy"] == pytest.approx(
        {0: 100.0, 1: 0.0, 2: 0.0}
    )
    assert world.world_records[1]["reserves_by_economy"] == pytest.approx(
        {0: 100.0, 1: 100.0, 2: 0.0}
    )


def test_context_rejects_mutable_wire_observation_by_snapshotting_it():
    raw = {"x": [{"y": 1}]}
    context = DecisionContext(
        "context:freeze",
        "window:freeze",
        0,
        "treasury",
        "fiscal_stance",
        0,
        0,
        {},
        raw,
    )
    raw["x"][0]["y"] = 9
    assert context.to_dict()["observation"] == {"x": [{"y": 1}]}
