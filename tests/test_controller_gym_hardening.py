"""Lifecycle, horizon, reset, and interval-reward gates for ControllerEnv."""
from __future__ import annotations

from dataclasses import replace
from itertools import product
import pickle

import numpy as np
import pytest

from macro_sim.checkpoint import state_digest
from macro_sim.config import Config
from macro_sim.controllers.costs import AdjustmentCostSpec
from macro_sim.controllers.gym_adapter import ControllerEnv
from macro_sim.controllers.occupants import NullOccupant, ScheduledOccupant
from macro_sim.controllers.protocol import (
    PendingDecision,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
)
from macro_sim.controllers.observation import (
    ObjectiveEvaluator,
    ObjectiveSpec,
    ObjectiveTerm,
    ObservationFieldSpec,
    ObservationSpec,
    ReleaseService,
)
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.core.policy_registry import REGISTRY, apply_action_batch
from macro_sim.economy import Economy
from macro_sim.world import World


def _scheduler(period: int = 4, *, admin_capacity: float = 100.0) -> DecisionScheduler:
    calendars = {
        name: CalendarSpec(period_ticks=1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    calendars["monetary_stance"] = CalendarSpec(
        period_ticks=period,
        admin_capacity=admin_capacity,
    )
    return DecisionScheduler(calendars=calendars, triggers=())


def _world(seed: int = 81) -> World:
    return World([Config.v13(
        seed=seed,
        n_households=12,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=1,
        n_ticks=30,
        government=True,
    )])


def _session(*, releases=None) -> ControlledSimulationSession:
    return ControlledSimulationSession(
        _world(), scheduler=_scheduler(), release_service=releases,
    )


def _hold(env: ControllerEnv) -> np.ndarray:
    return np.ones(len(env.action_dimensions), dtype=np.int64)


def _invalid_fractional(size: int):
    result = np.ones(size, dtype=np.float64)
    result[0] = 1.5
    return result


def _invalid_nan(size: int):
    result = np.ones(size, dtype=np.float64)
    result[0] = np.nan
    return result


def _invalid_inf(size: int):
    result = np.ones(size, dtype=np.float64)
    result[0] = np.inf
    return result


def _invalid_bool(size: int):
    return np.ones(size, dtype=np.bool_)


def _invalid_object(size: int):
    return np.asarray([1] * size, dtype=object)


def _invalid_string(size: int):
    return np.asarray(["1"] * size)


def _invalid_matrix(size: int):
    return np.ones((1, size), dtype=np.int64)


def _invalid_mixed_bool(size: int):
    return [True, *([1] * (size - 1))]


def _invalid_complex(size: int):
    return np.ones(size, dtype=np.complex128)


def _invalid_code(size: int):
    result = np.ones(size, dtype=np.int64)
    result[0] = 3
    return result


def _invalid_huge_int(size: int):
    return [10 ** 400, *([1] * (size - 1))]


def _external_session(
    economy_count: int = 3,
    *,
    decision_group: str = "trade_and_migration",
    immigration_cap: float | None = None,
) -> ControlledSimulationSession:
    calendars = {
        name: CalendarSpec(period_ticks=1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    calendars[decision_group] = CalendarSpec(4, admin_capacity=100.0)
    world = World([
        Config.v13(
            seed=800 + economy_id,
            n_households=8,
            n_firms_c=5,
            n_firms_k=3,
            n_banks=1,
            n_ticks=20,
            government=True,
        )
        for economy_id in range(economy_count)
    ], couple=True, trade=True, migration=True, immigration_cap=immigration_cap)
    return ControlledSimulationSession(
        world, scheduler=DecisionScheduler(calendars=calendars, triggers=()),
    )


def test_constructor_rejects_unknown_or_empty_seat_action_spaces():
    with pytest.raises(ValueError, match="unknown controller seat"):
        ControllerEnv(_session(), economy_id=0, seat="not-a-seat")
    with pytest.raises(ValueError, match="max_boundary_tick"):
        ControllerEnv(
            _session(), economy_id=0, seat="central_bank", max_boundary_tick=True,
        )


def test_constructor_failure_on_bare_external_seat_is_session_atomic():
    economy = Economy(Config.v13(
        seed=813,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
    ))
    session = ControlledSimulationSession(economy, scheduler=_scheduler())
    session.assign_seat(
        0, "external_affairs", NullOccupant(), actor="existing",
    )
    assignments = dict(session.seat_assignments)
    archive = dict(session.assignment_archive)
    sequence = session.next_assignment_sequence
    events = session.events.canonical_bytes()
    event_head = session.events.head_hash

    with pytest.raises(ValueError, match="owns no policy levers"):
        ControllerEnv(session, economy_id=0, seat="external_affairs")

    assert session.seat_assignments == assignments
    assert session.assignment_archive == archive
    assert session.next_assignment_sequence == sequence
    assert session.events.canonical_bytes() == events
    assert session.events.head_hash == event_head


def test_constructor_rejects_out_of_range_economy_before_assignment():
    session = _session()
    assignments = dict(session.seat_assignments)
    sequence = session.next_assignment_sequence

    with pytest.raises(ValueError, match="economy is out of range"):
        ControllerEnv(session, economy_id=1, seat="central_bank")

    assert session.seat_assignments == assignments
    assert session.next_assignment_sequence == sequence


@pytest.mark.parametrize(
    "invalid_action",
    (
        _invalid_fractional,
        _invalid_nan,
        _invalid_inf,
        _invalid_bool,
        _invalid_object,
        _invalid_string,
        _invalid_matrix,
        _invalid_mixed_bool,
        _invalid_complex,
        _invalid_code,
        _invalid_huge_int,
    ),
    ids=(
        "fractional", "nan", "inf", "bool", "object", "string", "shape",
        "mixed-bool", "complex", "out-of-range", "huge-int",
    ),
)
def test_invalid_directional_vectors_are_rejected_without_state_change(
    invalid_action,
):
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    before_digest = state_digest(env.session)
    before_context = env.context.to_json()
    before_events = tuple(env.session.events.events)

    with pytest.raises(ValueError, match="directional action"):
        env.action_to_proposal(invalid_action(len(env.action_dimensions)))

    assert state_digest(env.session) == before_digest
    assert env.context.to_json() == before_context
    assert tuple(env.session.events.events) == before_events


def test_policy_vector_keeps_context_values_for_groups_not_open_in_this_context():
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    observation, _info = env.reset()
    assert env.context is not None
    assert env.context.decision_group == "monetary_stance"
    assert "external_interest_settlement_fraction" not in {
        item.lever for item in env.context.permitted_actions
    }
    policy_index = env.observation_features.index(
        "policy:external_interest_settlement_fraction:value"
    )
    live = env.session.world.economies[
        0
    ].external_policy.external_interest_settlement_fraction
    assert live == 1.0
    assert observation[policy_index] == pytest.approx(1.0)
    pending_index = env.observation_features.index(
        "policy:external_interest_settlement_fraction:pending_present"
    )
    assert observation[pending_index] == 0.0
    dimension = env.action_dimensions.index(
        ("external_interest_settlement_fraction", None)
    )
    np.testing.assert_array_equal(_info["action_mask"][dimension], (0, 1, 0))


def test_vector_policy_pending_versions_and_admin_are_context_snapshots(monkeypatch):
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    context = env.context
    lever = "inflation_target"
    boundary = context.boundary_tick
    current_policy = dict(context.current_policy)
    current_policy[lever] = 0.037
    versions = dict(context.policy_versions)
    versions[lever] = 17
    snapshot = replace(
        context,
        current_policy=current_policy,
        policy_versions=versions,
        pending_policy={lever: 0.041},
        pending_effective_ticks={lever: boundary + 7},
        admin_remaining=7.5,
        admin_reserved=2.5,
        admin_capacity=10.0,
    )
    # The mask/cost tail is explicitly server-advisory.  Freeze it here so this
    # test isolates the context-owned base-vector contract.
    mask = np.zeros((len(env.action_dimensions), 3), dtype=np.int8)
    costs = np.zeros((len(env.action_dimensions), 3), dtype=np.float64)
    monkeypatch.setattr(env, "_direction_metadata", lambda _context: (mask, costs))

    economy = env.session.world.economies[0]
    economy.policy.inflation_target = 0.099
    key = (0, "central_bank", context.decision_group)
    env.session.coordinator.policy_versions["0:inflation_target"] = 99
    env.session.coordinator.admin_remaining[key] = 0.0
    env.session.coordinator.admin_reserved[key] = 0.0

    vector = env._vector(snapshot)
    value = lambda name: float(vector[env.observation_features.index(name)])
    item = next(
        item for item in snapshot.permitted_actions if item.lever == lever
    )
    assert value("policy:inflation_target:value") == pytest.approx(
        env._encode_policy_value(lever, 0.037, item)
    )
    assert value("policy:inflation_target:pending_target") == pytest.approx(
        env._encode_policy_value(lever, 0.041, item)
    )
    assert value("policy:inflation_target:pending_present") == 1.0
    assert value("policy:inflation_target:version") == 17.0
    assert value("admin:remaining") == 7.5
    assert value("admin:reserved") == 2.5


def test_markov_vector_distinguishes_last_effective_age_and_never_mask(monkeypatch):
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    context = env.context
    lever = "inflation_target"
    mask = np.zeros((len(env.action_dimensions), 3), dtype=np.int8)
    costs = np.zeros((len(env.action_dimensions), 3), dtype=np.float64)
    monkeypatch.setattr(env, "_direction_metadata", lambda _context: (mask, costs))

    never_ticks = dict(context.last_effective_ticks)
    never_ticks[lever] = None
    seen_ticks = dict(context.last_effective_ticks)
    seen_ticks[lever] = context.boundary_tick - 7
    never = env._vector(replace(context, last_effective_ticks=never_ticks))
    seen = env._vector(replace(context, last_effective_ticks=seen_ticks))

    age = env.observation_features.index(f"policy:{lever}:last_effective_age")
    never_mask = env.observation_features.index(
        f"policy:{lever}:last_effective_never"
    )
    assert (never[age], never[never_mask]) == (0.0, 1.0)
    assert (seen[age], seen[never_mask]) == (7.0, 0.0)


def test_markov_vector_distinguishes_eligibility_and_pending_lag(monkeypatch):
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    context = env.context
    lever = "inflation_target"
    boundary = context.boundary_tick
    mask = np.zeros((len(env.action_dimensions), 3), dtype=np.int8)
    costs = np.zeros((len(env.action_dimensions), 3), dtype=np.float64)
    monkeypatch.setattr(env, "_direction_metadata", lambda _context: (mask, costs))

    near_next = dict(context.next_eligibility_ticks)
    near_next[lever] = boundary + 4
    far_next = dict(context.next_eligibility_ticks)
    far_next[lever] = boundary + 9
    common_pending = {lever: 0.03}
    near = env._vector(replace(
        context,
        next_eligibility_ticks=near_next,
        pending_policy=common_pending,
        pending_effective_ticks={lever: boundary + 2},
    ))
    far = env._vector(replace(
        context,
        next_eligibility_ticks=far_next,
        pending_policy=common_pending,
        pending_effective_ticks={lever: boundary + 6},
    ))

    eligibility = env.observation_features.index(
        f"policy:{lever}:next_eligibility_delta"
    )
    pending_lag = env.observation_features.index(
        f"policy:{lever}:pending_effective_delta"
    )
    pending_mask = env.observation_features.index(f"policy:{lever}:pending_present")
    assert (near[eligibility], near[pending_lag], near[pending_mask]) == (4.0, 2.0, 1.0)
    assert (far[eligibility], far[pending_lag], far[pending_mask]) == (9.0, 6.0, 1.0)


def test_bare_economy_central_bank_reset_excludes_external_levers():
    economy = Economy(Config.v13(
        seed=812,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
    ))
    env = ControllerEnv(
        ControlledSimulationSession(economy, scheduler=_scheduler()),
        economy_id=0,
        seat="central_bank",
    )

    observation, info = env.reset()

    assert all(REGISTRY[name].scope != "external" for name in env.action_levers)
    assert set(env.context.current_policy) == set(env.action_levers)
    assert len(observation) == len(info["observation_features"])


def test_economy_set_has_one_directional_dimension_per_target():
    env = ControllerEnv(
        _external_session(), economy_id=0, seat="external_affairs",
    )
    observation, info = env.reset()
    target_one = env.action_dimensions.index(("sanctions_imposed_on", 1))
    target_two = env.action_dimensions.index(("sanctions_imposed_on", 2))
    np.testing.assert_array_equal(info["action_mask"][target_one], (0, 1, 1))
    np.testing.assert_array_equal(info["action_mask"][target_two], (0, 1, 1))

    action = _hold(env)
    action[target_two] = 2
    proposal = env.action_to_proposal(action)
    sanctions = [item for item in proposal.actions if item.lever == "sanctions_imposed_on"]
    assert len(sanctions) == 1
    assert sanctions[0].value == (2,)

    next_observation, _reward, _terminated, _truncated, next_info = env.step(action)
    assert env.session.world.economies[0].external_policy.sanctions_imposed_on == frozenset({2})
    policy_offset = env.observation_features.index(
        "policy:sanctions_imposed_on:value"
    )
    # Set policy values are encoded as a stable target bit mask: target 2 is bit 1.
    assert observation[policy_offset] == 0.0
    assert next_observation[policy_offset] == 2.0
    # The sanctions min-hold now closes both change directions until the next
    # lawful window; hold remains valid.
    np.testing.assert_array_equal(next_info["action_mask"][target_two], (0, 1, 0))


def test_released_series_vector_uses_declared_normalization_scale():
    spec = ObservationSpec((
        ObservationFieldSpec(
            "scaled_price",
            "price_index",
            frequency_ticks=1,
            window_ticks=1,
            publication_lag_ticks=0,
            require_full_window=False,
            normalization_scale=0.1,
        ),
    ))
    env = ControllerEnv(
        _session(releases=ReleaseService(spec)),
        economy_id=0,
        seat="central_bank",
    )
    env.reset()
    observation, _reward, _terminated, _truncated, _info = env.step(_hold(env))
    assert env.context is not None
    release = env.context.observation.releases[0]
    assert release.missing_reason is None
    assert observation[2] == pytest.approx(float(release.value) / 0.1)


def test_zero_lag_decision_is_reported_and_charged_exactly_once():
    world = _world()
    apply_action_batch(
        world.economies[0],
        [("monetary_regime", "manual"), ("manual_policy_rate", 0.002)],
        actor="test_seed",
    )
    env = ControllerEnv(
        ControlledSimulationSession(world, scheduler=_scheduler()),
        economy_id=0,
        seat="central_bank",
    )
    env.reset()

    _obs, reward, _terminated, _truncated, info = env.step(
        {"manual_policy_rate": 0.0021}
    )

    changed = [
        item for item in info["decisions"]
        if item["proposal_id"].endswith(":gym")
    ]
    assert len(changed) == 1
    assert changed[0]["status"] == "effective"
    assert changed[0]["adjustment_cost"] > 0.0
    assert reward == pytest.approx(-changed[0]["adjustment_cost"])
    assert changed[0]["decision_id"] not in env._charged_adjustment_costs
    assert changed[0]["decision_id"] in env._settled_adjustment_costs


def test_lagged_decision_is_not_charged_again_when_it_becomes_effective_next_step():
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    current = next(
        item.current_value for item in env.context.permitted_actions
        if item.lever == "cb_log_inflation"
    )

    _obs1, reward1, _term1, _trunc1, info1 = env.step(
        {"cb_log_inflation": not current}
    )
    pending = next(
        item for item in info1["decisions"]
        if item["proposal_id"].endswith(":gym")
    )
    assert pending["status"] == "accepted_pending"
    assert reward1 == pytest.approx(-pending["adjustment_cost"])

    _obs2, reward2, _term2, _trunc2, info2 = env.step(_hold(env))
    effective = [
        item for item in info2["decisions"]
        if item["decision_id"] == pending["decision_id"]
    ]
    assert len(effective) == 1 and effective[0]["status"] == "effective"
    assert reward2 == pytest.approx(0.0)
    assert pending["decision_id"] not in env._charged_adjustment_costs
    assert pending["decision_id"] in env._settled_adjustment_costs


def test_agent_reward_excludes_other_seats_adjustment_costs_in_same_interval():
    calendars = {
        name: CalendarSpec(period_ticks=1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    calendars["monetary_stance"] = CalendarSpec(4, admin_capacity=100.0)
    calendars["fiscal_stance"] = CalendarSpec(4, admin_capacity=100.0)
    session = ControlledSimulationSession(
        _world(), scheduler=DecisionScheduler(calendars=calendars, triggers=()),
    )
    current = session.world.economies[0].policy.gov_deficit_target
    session.assign_seat(
        0,
        "treasury",
        ScheduledOccupant({
            0: (PolicyAction("gov_deficit_target", current + 0.005),),
        }),
        actor="test",
        log_event=False,
    )
    env = ControllerEnv(session, economy_id=0, seat="central_bank")
    env.reset()

    _obs, reward, _terminated, _truncated, info = env.step(_hold(env))

    treasury = [
        decision for decision in info["decisions"]
        if decision["adjustment_cost"] > 0.0
    ]
    assert len(treasury) == 1
    assert reward == pytest.approx(0.0)


def test_horizon_returns_a_valid_truncated_transition_before_seeking_context():
    env = ControllerEnv(
        _session(), economy_id=0, seat="central_bank", max_boundary_tick=1,
    )
    initial, _info = env.reset()
    assert env.context is not None
    policy_index = env.observation_features.index("policy:taylor_phi_pi:value")
    initial_policy_value = initial[policy_index]
    assert env.observation_space.contains(initial)

    observation, _reward, terminated, truncated, info = env.step(_hold(env))

    assert not terminated and truncated
    assert env.context is None
    assert observation[0] == pytest.approx(1.0)
    assert observation[policy_index] == pytest.approx(initial_policy_value)
    assert observation[policy_index] != 0.0
    assert env.observation_space.contains(observation)
    assert info["terminal_observation"] is True
    assert info["context"]["context_id"].startswith("terminal:")


def test_terminal_context_refreshes_current_pending_and_markov_snapshots():
    env = ControllerEnv(
        _session(), economy_id=0, seat="central_bank", max_boundary_tick=1,
    )
    env.reset()
    assert env.context is not None
    current = bool(env.context.current_policy["cb_log_inflation"])

    observation, _reward, _terminated, truncated, info = env.step(
        {"cb_log_inflation": not current}
    )

    assert truncated
    terminal = info["context"]
    assert terminal["current_policy"]["cb_log_inflation"] is current
    assert terminal["pending_policy"]["cb_log_inflation"] is (not current)
    assert terminal["pending_effective_ticks"]["cb_log_inflation"] == 7
    assert "cb_log_inflation" in terminal["policy_versions"]
    assert "cb_log_inflation" in terminal["last_effective_ticks"]
    assert terminal["next_eligibility_ticks"]["cb_log_inflation"] >= 372
    pending_delta = env.observation_features.index(
        "policy:cb_log_inflation:pending_effective_delta"
    )
    assert observation[pending_delta] == 6.0


def _released_objective():
    observation_spec = ObservationSpec((
        ObservationFieldSpec(
            "unemployment",
            "unemployment_rate",
            frequency_ticks=1,
            window_ticks=1,
            publication_lag_ticks=0,
            require_full_window=False,
            normalization_scale=1.0,
        ),
    ))
    objective = ObjectiveEvaluator(
        ObjectiveSpec((
            ObjectiveTerm(
                "unemployment",
                "maximize",
                weight=1.0,
                normalization_scale=1.0,
                reward_release_rule="on_release",
            ),
        ), time_normalization="per_tick"),
        observation_spec,
    )
    return ReleaseService(observation_spec), objective


def test_reward_accumulates_each_intervening_release_and_normalizes_per_tick():
    releases, objective = _released_objective()
    env = ControllerEnv(
        _session(releases=releases),
        economy_id=0,
        seat="central_bank",
        objective_evaluator=objective,
    )
    env.reset()

    _obs, reward, _terminated, _truncated, info = env.step(_hold(env))

    released = env.session.release_service.history(
        0, "unemployment", as_of_tick=env.session.boundary_tick,
    )
    values = [float(item.value) for item in released if 1 <= item.released_at_tick <= 4]
    assert len(values) == 4
    expected = sum(values) / 4
    assert len([
        item for item in info["interval_trace"] if item["status"] == "advanced"
    ]) == 4
    assert info["objective"]["macro_reward"] == pytest.approx(expected)
    assert info["objective"]["components"]["unemployment"] == pytest.approx(expected)
    assert reward == pytest.approx(expected)


def _oracle_research_objective(*, frequency_ticks: int = 1):
    observation_spec = ObservationSpec((
        ObservationFieldSpec(
            "public_price",
            "price_index",
            frequency_ticks=frequency_ticks,
            window_ticks=1,
            publication_lag_ticks=0,
            require_full_window=False,
            normalization_scale=1.0,
        ),
        ObservationFieldSpec(
            "oracle_output",
            "real_output",
            access_class="oracle",
            frequency_ticks=frequency_ticks,
            window_ticks=1,
            publication_lag_ticks=0,
            require_full_window=False,
            normalization_scale=1.0,
        ),
    ))
    objective = ObjectiveEvaluator(
        ObjectiveSpec((
            ObjectiveTerm(
                "public_price", "maximize", reward_release_rule="on_release",
            ),
            ObjectiveTerm(
                "oracle_output", "maximize", reward_release_rule="on_release",
            ),
        ), human_comparable=False, time_normalization="per_tick"),
        observation_spec,
    )
    return ReleaseService(observation_spec), objective


def test_oracle_research_reward_is_live_but_policy_context_stays_seat_filtered():
    releases, objective = _oracle_research_objective()
    env = ControllerEnv(
        _session(releases=releases),
        economy_id=0,
        seat="central_bank",
        objective_evaluator=objective,
    )
    observation, reset_info = env.reset()
    assert env.context is not None
    assert reset_info["objective_profile"] == "oracle_research"

    hidden = env.context.observation.release("oracle_output")
    assert hidden.value is None
    assert hidden.missing_reason == "access_denied"
    hidden_value = env.observation_features.index("release:oracle_output:value")
    hidden_missing = env.observation_features.index("release:oracle_output:missing")
    assert observation[hidden_value] == 0.0
    assert observation[hidden_missing] == 1.0

    next_observation, reward, _terminated, _truncated, info = env.step(_hold(env))
    assert reward > 0.0
    assert info["objective_profile"] == "oracle_research"
    assert info["objective"]["profile"] == "oracle_research"
    assert info["objective"]["components"]["oracle_output"] > 0.0

    # Reward-only oracle access must not widen the next policy observation or the
    # stable policy vector delivered to the occupant.
    context_releases = {
        item["series_id"]: item
        for item in info["context"]["observation"]["releases"]
    }
    assert context_releases["oracle_output"]["value"] is None
    assert context_releases["oracle_output"]["missing_reason"] == "access_denied"
    assert next_observation[hidden_value] == 0.0
    assert next_observation[hidden_missing] == 1.0


def test_oracle_reset_prime_marks_pre_episode_vintage_without_rewarding_it():
    world = _world(seed=812)
    world.run(10)
    releases, objective = _oracle_research_objective(frequency_ticks=10)
    calendars = {
        name: CalendarSpec(
            period_ticks=1_000, offset_ticks=999, admin_capacity=100.0,
        )
        for name in DEFAULT_CALENDARS
    }
    calendars["monetary_stance"] = CalendarSpec(
        period_ticks=4, offset_ticks=2, admin_capacity=100.0,
    )
    session = ControlledSimulationSession(
        world,
        scheduler=DecisionScheduler(calendars=calendars, triggers=()),
        release_service=releases,
    )
    env = ControllerEnv(
        session,
        economy_id=0,
        seat="central_bank",
        objective_evaluator=objective,
    )

    _observation, reset_info = env.reset()
    assert env.context is not None and env.context.boundary_tick == 10
    assert reset_info["objective_profile"] == "oracle_research"
    assert env.session.release_service.history(0, "oracle_output")

    # The next decision is boundary 14, before the next ten-tick release at 20.
    # The boundary-10 vintage was primed at reset and must not become a spurious
    # first-step on_release reward.
    _obs, reward, _terminated, _truncated, info = env.step(_hold(env))
    assert info["elapsed_ticks"] == 4
    assert info["objective"]["profile"] == "oracle_research"
    assert info["objective"]["components"]["oracle_output"] == 0.0
    assert info["objective"]["components"]["public_price"] == 0.0
    assert reward == 0.0


def test_reset_restores_objective_history_for_repeatable_episodes():
    releases, objective = _released_objective()
    env = ControllerEnv(
        _session(releases=releases),
        economy_id=0,
        seat="central_bank",
        objective_evaluator=objective,
    )

    env.reset(seed=123)
    first = env.step(_hold(env))
    first_trace = first[4]["interval_trace"]
    first_events = first[4]["interval_events"]

    env.reset(seed=123)
    second = env.step(_hold(env))

    assert second[1] == pytest.approx(first[1])
    assert second[4]["objective"] == first[4]["objective"]
    assert second[4]["interval_trace"] == first_trace
    assert second[4]["interval_events"] == first_events


def test_bool_direction_codes_are_absolute_false_hold_true_not_two_toggles():
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    permitted = {item.lever: item for item in env.context.permitted_actions}
    item = permitted["cb_uses_fixed_basket_cpi"]

    assert env._directional_value(item, 0) is False
    assert env._directional_value(item, 2) is True
    mask = env.action_mask()
    row = mask[env.action_levers.index("cb_uses_fixed_basket_cpi")]
    if item.current_value:
        np.testing.assert_array_equal(row, (1, 1, 0))
    else:
        np.testing.assert_array_equal(row, (0, 1, 1))


def _assert_coordinator_accepts(env: ControllerEnv, proposal) -> None:
    isolated = pickle.loads(pickle.dumps(env.session, protocol=5))
    decision = isolated.coordinator.submit(
        isolated, proposal, actor="gym_acceptance_probe",
    )
    assert decision.status in {"accepted_noop", "accepted_pending"}, (
        decision.status, decision.reason_code, proposal.to_dict()
    )


def test_vector_regime_directions_expand_to_atomic_manual_and_peg_templates():
    monetary = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    monetary.reset()
    regime_index = monetary.action_dimensions.index(("monetary_regime", None))
    regime = next(
        item for item in monetary.context.permitted_actions
        if item.lever == "monetary_regime"
    )
    assert regime.current_value == "taylor"
    action = _hold(monetary)
    action[regime_index] = 2
    assert monetary.action_mask()[regime_index, 2] == 1
    proposal = monetary.action_to_proposal(action)
    targets = {item.lever: item.value for item in proposal.actions}
    assert targets["monetary_regime"] == "manual"
    assert targets["manual_policy_rate"] is not None
    _assert_coordinator_accepts(monetary, proposal)

    fx = ControllerEnv(
        _external_session(decision_group="fx_operations"),
        economy_id=0,
        seat="central_bank",
    )
    fx.reset()
    fx_index = fx.action_dimensions.index(("fx_regime", None))
    action = _hold(fx)
    action[fx_index] = 2
    assert fx.action_mask()[fx_index, 2] == 1
    proposal = fx.action_to_proposal(action)
    targets = {item.lever: item.value for item in proposal.actions}
    assert targets["fx_regime"] == "peg"
    assert targets["peg_anchor"] in {1, 2}
    _assert_coordinator_accepts(fx, proposal)


def test_every_masked_cartesian_combination_yields_a_legal_joint_proposal():
    session = ControlledSimulationSession(
        _world(), scheduler=_scheduler(admin_capacity=4.0),
    )
    env = ControllerEnv(session, economy_id=0, seat="central_bank")
    env.reset()
    mask = env.action_mask()
    dimensions = [
        env.action_dimensions.index((lever, None))
        for lever in ("inflation_target", "manual_policy_rate", "monetary_regime")
    ]
    choices = [tuple(np.flatnonzero(mask[index])) for index in dimensions]

    # The two templates are each affordable but not jointly affordable.  The
    # adapter deterministically keeps a legal subset rather than emitting a
    # proposal that the Coordinator must reject.
    combined = _hold(env)
    combined[dimensions[0]] = 2
    combined[dimensions[2]] = 2
    combined_proposal = env.action_to_proposal(combined)
    combined_levers = {item.lever for item in combined_proposal.actions}
    assert "inflation_target" in combined_levers
    assert "monetary_regime" not in combined_levers

    for selected_codes in product(*choices):
        action = _hold(env)
        for index, code in zip(dimensions, selected_codes, strict=True):
            action[index] = code
        _assert_coordinator_accepts(env, env.action_to_proposal(action))


def test_smdp_vector_exposes_versions_pending_budget_costs_emergency_and_none():
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    observation, info = env.reset()
    assert len(observation) == len(env.observation_features)
    assert len(set(env.observation_features)) == len(env.observation_features)
    assert tuple(info["observation_features"]) == env.observation_features

    def value(name: str) -> float:
        return float(observation[env.observation_features.index(name)])

    assert value("policy:manual_policy_rate:is_none") == 1.0
    assert value("policy:inflation_target:is_none") == 0.0
    assert value("policy:inflation_target:version") == 0.0
    key = (0, "central_bank", env.context.decision_group)
    assert value("admin:remaining") == pytest.approx(
        env.session.coordinator.admin_remaining[key]
    )
    assert value("admin:reserved") == pytest.approx(0.0)
    inflation_dimension = env.action_dimensions.index(("inflation_target", None))
    label = "action:inflation_target"
    assert value(f"{label}:up_eligible") == info["action_mask"][inflation_dimension, 2]
    assert value(f"{label}:up_cost") == pytest.approx(
        info["action_costs"][inflation_dimension, 2]
    )
    assert value(f"{label}:up_cost") > 0.0

    emergency = replace(
        env.context, emergency=True, emergency_trigger="liquidity_crisis",
    )
    emergency_vector = env._vector(emergency)
    assert emergency_vector[
        env.observation_features.index("decision:emergency")
    ] == 1.0
    assert emergency_vector[
        env.observation_features.index("decision:emergency_trigger_present")
    ] == 1.0
    assert env.observation_space.contains(emergency_vector)

    nullable = ControllerEnv(
        _external_session(immigration_cap=0.0),
        economy_id=0,
        seat="external_affairs",
    )
    nullable.reset()
    cap_index = nullable.action_dimensions.index(("immigration_cap", None))
    action = _hold(nullable)
    action[cap_index] = 0
    pending_observation, _reward, _terminated, _truncated, _info = nullable.step(action)
    pending = nullable.observation_features.index(
        "policy:immigration_cap:pending_present"
    )
    pending_none = nullable.observation_features.index(
        "policy:immigration_cap:pending_target_is_none"
    )
    assert pending_observation[pending] == 1.0
    assert pending_observation[pending_none] == 1.0
    assert nullable.observation_space.contains(pending_observation)


def test_external_cancel_refund_is_returned_on_next_step_exactly_once():
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    current = next(
        item.current_value for item in env.context.permitted_actions
        if item.lever == "cb_log_inflation"
    )
    _obs, first_reward, _terminated, _truncated, first_info = env.step(
        {"cb_log_inflation": not current}
    )
    accepted = next(
        item for item in first_info["decisions"]
        if item["status"] == "accepted_pending"
    )
    cost = float(accepted["adjustment_cost"])
    assert first_reward == pytest.approx(-cost)

    env.session.cancel_pending(accepted["decision_id"], actor="frontend")
    _obs, refunded, _terminated, _truncated, refund_info = env.step(_hold(env))
    cancelled = [
        item for item in refund_info["decisions"]
        if item["decision_id"] == accepted["decision_id"]
    ]
    assert len(cancelled) == 1 and cancelled[0]["status"] == "cancelled"
    assert refunded == pytest.approx(cost * env.session.cost_spec.refund_on_cancel)

    _obs, later, _terminated, _truncated, later_info = env.step(_hold(env))
    assert later == pytest.approx(0.0)
    assert accepted["decision_id"] not in {
        item["decision_id"] for item in later_info["decisions"]
    }


@pytest.mark.parametrize(
    ("status", "refund_field"),
    (
        ("cancelled", "refund_on_cancel"),
        ("superseded", "refund_on_supersede"),
        ("failed_at_execution", "refund_on_failed_execution"),
    ),
)
def test_first_seen_terminal_decision_charges_only_non_refunded_cost(
    status, refund_field,
):
    env = ControllerEnv(_session(), economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    refund = 0.25
    cost_spec = AdjustmentCostSpec(**{refund_field: refund})
    env.session.cost_spec = cost_spec
    env.session.coordinator.cost_spec = cost_spec
    proposal = PolicyProposal(
        proposal_id=f"proposal:{status}",
        idempotency_key=f"idempotency:{status}",
        context_id=env.context.context_id,
        actions=(),
        based_on_policy_versions=dict(env.context.policy_versions),
    )
    decision = PolicyDecision(
        decision_id=f"decision:{status}",
        proposal_id=proposal.proposal_id,
        status=status,
        reason_code=status,
        adjustment_cost=8.0,
    )
    env.session.coordinator.pending[decision.decision_id] = PendingDecision(
        decision=decision,
        proposal=proposal,
        context=env.context,
        status=status,
        adjustment_cost=8.0,
    )

    charged = env._account_adjustment_cost((decision,))

    assert charged == pytest.approx(8.0 * (1.0 - refund))
    assert decision.decision_id not in env._charged_adjustment_costs
    assert env._account_adjustment_cost((decision,)) == 0.0


@pytest.mark.parametrize(
    ("session", "seat"),
    (
        (_session(), "central_bank"),
        (_external_session(), "external_affairs"),
    ),
)
def test_controller_env_passes_gymnasium_env_checker(session, seat):
    pytest.importorskip("gymnasium")
    from gymnasium.utils.env_checker import check_env
    env = ControllerEnv(
        session, economy_id=0, seat=seat, max_boundary_tick=5,
    )
    check_env(env, skip_render_check=True)
