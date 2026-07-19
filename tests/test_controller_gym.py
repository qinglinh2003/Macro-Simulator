"""C5 acceptance gates for the semi-Markov controller adapter.

These tests intentionally exercise the same server-issued ``DecisionContext`` and
Coordinator path used by the frontend.  The Gym mask is advisory: malformed,
unauthorized, and stale actions must still be rejected by the Coordinator without
touching engine state.
"""
from __future__ import annotations

import numpy as np
import pytest

from macro_sim.checkpoint import state_digest
from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.gym_adapter import ControllerEnv
from macro_sim.controllers.observation import (
    ObjectiveEvaluator,
    ObjectiveSpec,
    ObservationSpec,
    ReleaseService,
)
from macro_sim.controllers.occupants import HumanQueueOccupant, RandomFuzzOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
)
from macro_sim.controllers.session import AWAITING_HUMAN, ControlledSimulationSession
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


PRIMARY_GROUP = "monetary_stance"
PRIMARY_SEAT = "central_bank"
MEETING_PERIOD = 4


def _config(seed: int = 19) -> Config:
    return Config.v13(
        seed=seed,
        n_households=20,
        n_firms_c=15,
        n_firms_k=8,
        n_banks=2,
        n_ticks=80,
        government=True,
    )


def _one_group_scheduler(
    group: str = PRIMARY_GROUP,
    period: int = MEETING_PERIOD,
) -> DecisionScheduler:
    # Keep every other institutional calendar beyond this test's horizon.  This
    # gives the adapter exactly one outstanding human context at a time.
    calendars = {
        name: CalendarSpec(
            period_ticks=1_000,
            offset_ticks=999,
            admin_capacity=100.0,
        )
        for name in DEFAULT_CALENDARS
    }
    calendars[group] = CalendarSpec(period_ticks=period, admin_capacity=100.0)
    # Default emergency triggers are intentionally disabled: this fixture tests
    # the regular semi-Markov clock, not stochastic crisis timing.
    return DecisionScheduler(calendars=calendars, triggers=())


def _session(
    *,
    seed: int = 19,
    release_service: ReleaseService | None = None,
) -> ControlledSimulationSession:
    return ControlledSimulationSession(
        World([_config(seed)]),
        scheduler=_one_group_scheduler(),
        release_service=release_service,
    )


def _open_frontend_context(
    session: ControlledSimulationSession,
    *,
    seat: str = PRIMARY_SEAT,
):
    session.assign_seat(
        0, seat, HumanQueueOccupant(), actor="frontend", log_event=False,
    )
    result = session.advance()
    assert result.status == AWAITING_HUMAN
    assert len(result.missing_context_ids) == len(result.contexts) == 1
    return result.contexts[0]


def _directional_action(env: ControllerEnv, lever: str, code: int) -> np.ndarray:
    action = np.ones(len(env.action_levers), dtype=np.int64)
    action[env.action_levers.index(lever)] = code
    return action


def _advance_to_next_human_context(
    session: ControlledSimulationSession,
    *,
    max_calls: int = 16,
):
    for _ in range(max_calls):
        result = session.advance()
        if result.status == AWAITING_HUMAN:
            assert len(result.missing_context_ids) == len(result.contexts) == 1
            return result.contexts[0]
    raise AssertionError("the next human decision context did not open")


def test_reset_context_json_is_byte_equivalent_to_frontend_decision_context():
    env = ControllerEnv(_session(), economy_id=0, seat=PRIMARY_SEAT)
    observation, info = env.reset()

    frontend_context = _open_frontend_context(_session())
    frontend_bytes = frontend_context.to_json().encode("utf-8")

    assert env.context is not None
    assert info["context_json"].encode("utf-8") == frontend_bytes
    assert env.context.to_json().encode("utf-8") == frontend_bytes
    assert info["context"] == frontend_context.to_dict()
    assert observation.dtype == np.float64


def test_action_mask_and_directional_adapter_emit_absolute_targets():
    env = ControllerEnv(_session(), economy_id=0, seat=PRIMARY_SEAT)
    _observation, info = env.reset()
    assert env.context is not None

    permitted = {item.lever: item for item in env.context.permitted_actions}
    inflation = permitted["inflation_target"]
    inflation_index = env.action_levers.index("inflation_target")
    liquidity_index = env.action_levers.index("omo_reserve_target")
    mask = info["action_mask"]

    assert mask.shape == (len(env.action_levers), 3)
    np.testing.assert_array_equal(mask[inflation_index], (1, 1, 1))
    # A lever belonging to another decision group is hold-only in this context.
    np.testing.assert_array_equal(mask[liquidity_index], (0, 1, 0))

    up = env.action_to_proposal(
        _directional_action(env, "inflation_target", 2)
    )
    down = env.action_to_proposal(
        _directional_action(env, "inflation_target", 0)
    )

    assert len(up.actions) == len(down.actions) == 1
    assert up.actions[0].lever == down.actions[0].lever == "inflation_target"
    assert up.actions[0].value == pytest.approx(
        float(inflation.current_value) + float(inflation.control_scale)
    )
    assert down.actions[0].value == pytest.approx(
        float(inflation.current_value) - float(inflation.control_scale)
    )
    # The wire protocol carries absolute targets; no direction code escapes.
    assert up.actions[0].value not in (0, 1, 2)


def test_same_canonical_proposal_via_gym_and_human_has_identical_digests():
    gym_env = ControllerEnv(_session(), economy_id=0, seat=PRIMARY_SEAT)
    _observation, _info = gym_env.reset()
    action = _directional_action(gym_env, "inflation_target", 2)
    canonical_proposal = gym_env.action_to_proposal(action)

    # Gym builds the same immutable wire proposal internally, then advances to
    # the next decision boundary.
    gym_env.step(action)

    direct = _session()
    direct_context = _open_frontend_context(direct)
    assert canonical_proposal.context_id == direct_context.context_id
    assert canonical_proposal.based_on_policy_versions == direct_context.policy_versions
    direct.submit_human_proposal(canonical_proposal, actor="gym")
    first = direct.advance()
    assert first.status == "advanced"
    direct_next = _advance_to_next_human_context(direct)

    assert gym_env.context is not None
    assert direct_next.to_json() == gym_env.context.to_json()
    assert direct.events.canonical_bytes() == gym_env.session.events.canonical_bytes()
    assert state_digest(direct.world) == state_digest(gym_env.session.world)
    # The session digest additionally covers pending state, calendars, occupants,
    # versions, costs, and the canonical event head.
    assert state_digest(direct) == state_digest(gym_env.session)


def test_semi_markov_elapsed_ticks_normalize_control_cost_reward():
    observation_spec = ObservationSpec(())
    releases = ReleaseService(observation_spec)
    objective = ObjectiveEvaluator(
        ObjectiveSpec(
            (),
            control_cost_weight=2.0,
            time_normalization="per_tick",
        ),
        observation_spec,
    )
    env = ControllerEnv(
        _session(release_service=releases),
        economy_id=0,
        seat=PRIMARY_SEAT,
        objective_evaluator=objective,
    )
    env.reset()

    next_observation, reward, terminated, truncated, info = env.step(
        _directional_action(env, "inflation_target", 2)
    )

    assert info["elapsed_ticks"] == MEETING_PERIOD
    assert env.context is not None
    assert env.context.elapsed_ticks == MEETING_PERIOD
    assert next_observation[0] == pytest.approx(MEETING_PERIOD)
    assert next_observation[1] == pytest.approx(MEETING_PERIOD)
    assert not terminated and not truncated

    accepted = [
        item for item in info["decisions"]
        if item["status"] in {"accepted_pending", "effective"}
    ]
    assert len(accepted) == 1
    adjustment_cost = accepted[0]["adjustment_cost"]
    expected_penalty = 2.0 * adjustment_cost / MEETING_PERIOD
    assert info["objective"]["elapsed_ticks"] == MEETING_PERIOD
    assert info["objective"]["macro_reward"] == 0.0
    assert info["objective"]["control_cost_penalty"] == pytest.approx(expected_penalty)
    assert reward == pytest.approx(-expected_penalty)


def test_adversarial_and_stale_actions_are_rejected_without_engine_mutation():
    # The adapter deliberately forwards an advisory-mask bypass so authority is
    # enforced by the Coordinator, not trusted client behavior.
    env = ControllerEnv(_session(), economy_id=0, seat=PRIMARY_SEAT)
    env.reset()
    assert env.context is not None
    unauthorized = env.action_to_proposal({"tax_income_rate": 0.20})
    before = state_digest(env.session.world)
    old_tax_rate = env.session.world.economies[0].policy.tax_income_rate
    old_inflation_target = env.session.world.economies[0].policy.inflation_target

    rejected = env.session.coordinator.submit(
        env.session, unauthorized, actor="adversarial_client",
    )

    assert rejected.status == "rejected"
    assert rejected.reason_code == "unauthorized_lever"
    assert state_digest(env.session.world) == before
    assert env.session.world.economies[0].policy.tax_income_rate == old_tax_rate
    assert env.session.world.economies[0].policy.inflation_target == old_inflation_target
    assert not env.session.pending

    # A forged old version is independently rejected before Registry preparation
    # or any pending reservation can touch the engine.
    stale_session = _session(seed=23)
    stale_context = _open_frontend_context(stale_session)
    item = next(
        entry for entry in stale_context.permitted_actions
        if entry.lever == "inflation_target"
    )
    stale_versions = dict(stale_context.policy_versions)
    # Wire versions must themselves be valid non-negative counters.  A future
    # counter is still a legal wire value and is stale relative to Coordinator
    # state, which exercises the intended authority check.
    stale_versions["inflation_target"] += 1
    stale = PolicyProposal(
        proposal_id="proposal:stale-adversary",
        idempotency_key="proposal:stale-adversary",
        context_id=stale_context.context_id,
        actions=(PolicyAction(
            "inflation_target",
            float(item.current_value) + float(item.control_scale),
        ),),
        reason="forged_stale_version",
        based_on_policy_versions=stale_versions,
    )
    stale_before = state_digest(stale_session.world)
    stale_old = stale_session.world.economies[0].policy.inflation_target

    stale_decision = stale_session.coordinator.submit(
        stale_session, stale, actor="adversarial_client",
    )

    assert stale_decision.status == "rejected"
    assert stale_decision.reason_code == "stale_policy_version"
    assert state_digest(stale_session.world) == stale_before
    assert stale_session.world.economies[0].policy.inflation_target == stale_old
    assert not stale_session.pending


def test_random_fuzz_occupants_small_run_smoke():
    calendars = {
        name: CalendarSpec(period_ticks=3, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    session = ControlledSimulationSession(
        World([_config(seed=31)]),
        scheduler=DecisionScheduler(calendars=calendars, triggers=()),
    )
    for index, seat in enumerate(SEATS):
        session.assign_seat(
            0,
            seat,
            RandomFuzzOccupant(
                seed=100 + index,
                action_probability=0.60,
                max_actions=1,
            ),
            actor="fuzz_harness",
            log_event=False,
        )

    session.run(12)

    assert session.boundary_tick == session.world.t == 12
    assert len(session.world.economies[0].records) == 12
    assert session.coordinator.decisions
    assert set(
        decision.status for decision in session.coordinator.decisions.values()
    ) <= {
        "accepted_noop", "accepted_pending", "effective", "rejected",
        "failed_at_execution",
    }
    economy = session.world.economies[0]
    for name, lever in REGISTRY.items():
        holder = economy.external_policy if lever.scope == "external" else economy.policy
        value = getattr(holder, name)
        assert lever.validation.check(value, value) is None, name
    session.events.verify()
    assert len(state_digest(session)) == 64
