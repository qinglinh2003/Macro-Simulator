from __future__ import annotations

import pytest

from macro_sim.checkpoint import state_digest
from macro_sim.config import Config
from macro_sim.controllers.coordinator import policy_key
from macro_sim.controllers.occupants import HumanQueueOccupant, RLOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    BOUNDARY_START,
    ControlledSimulationSession,
)
from macro_sim.controllers.transaction import policy_state
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.economy import Economy
from macro_sim.world import World


def _config(seed: int) -> Config:
    return Config.v13(
        seed=seed,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        demographics_population=30,
        n_ticks=20,
        government=True,
    )


def _world(seed: int = 940) -> World:
    return World([_config(seed), _config(seed + 1)])


def _treasury_scheduler() -> DecisionScheduler:
    groups = {
        lever.decision_group
        for lever in REGISTRY.values()
        if lever.owner_role == "treasury"
    }
    calendars = {
        group: CalendarSpec(100, offset_ticks=50, admin_capacity=20.0)
        for group in groups
    }
    calendars["fiscal_stance"] = CalendarSpec(
        100, offset_ticks=0, admin_capacity=20.0,
    )
    return DecisionScheduler(calendars=calendars)


def _rl_hold(_context):
    return ()


def test_rl_assignment_has_canonical_recorded_proposal_replay():
    source = ControlledSimulationSession(
        World([_config(950)]), scheduler=_treasury_scheduler(),
    )
    source.assign_seat(
        0, "treasury", RLOccupant(policy=_rl_hold), actor="trainer",
    )
    result = source.advance()
    assert result.status == "advanced"

    assignment = source.events.events[0]
    assert assignment["event_type"] == "seat_assignment"
    assert assignment["payload"]["new_occupant"] == "RLOccupant"
    assert assignment["payload"]["occupant_spec"] == {
        "type": "rl",
        "replay_mode": "recorded_proposals",
    }

    replay = ControlledSimulationSession(
        World([_config(950)]),
        scheduler=_treasury_scheduler(),
        run_mode="replay",
    )
    replay_input_events(
        replay,
        source.events.input_events(),
        until_tick=source.boundary_tick,
        expected_events=source.events.events,
    )
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert state_digest(replay.world) == state_digest(source.world)
    replay_occupant = replay.seat_assignments[(0, "treasury")]
    assert isinstance(replay_occupant, RLOccupant)
    assert replay_occupant.policy is None


def test_world_child_tick_divergence_is_rejected_before_open_or_advance():
    session = ControlledSimulationSession(_world())
    session.world.economies[1].step()
    externally_advanced = state_digest(session.world)
    original_fingerprint = session.policy_fingerprint

    with pytest.raises(RuntimeError, match=r"economy 1 tick 1, expected 0"):
        session.coordinator.open_context(
            session,
            0,
            "treasury",
            "fiscal_stance",
            {},
            expires_at_tick=0,
        )
    with pytest.raises(RuntimeError, match=r"economy 1 tick 1, expected 0"):
        session.advance()

    assert state_digest(session.world) == externally_advanced
    assert session.world.t == session.world.economies[0].t == 0
    assert session.world.economies[1].t == 1
    assert session.boundary_tick == 0
    assert session.phase == BOUNDARY_START
    assert not session.coordinator.contexts
    assert not session.events.events
    assert session.policy_fingerprint == original_fingerprint


def test_child_tick_divergence_rejects_decisions_in_an_open_window_without_mutation():
    session = ControlledSimulationSession(
        _world(960), scheduler=_treasury_scheduler(), run_mode="interactive",
    )
    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human)
    opened = session.advance()
    assert opened.status == AWAITING_HUMAN
    context_id = opened.missing_context_ids[0]

    session.world.economies[1].step()
    externally_advanced = state_digest(session.world)
    event_count = len(session.events.events)
    missing = session.missing_context_ids

    with pytest.raises(RuntimeError, match=r"economy 1 tick 1, expected 0"):
        session.timeout_context(context_id)
    with pytest.raises(RuntimeError, match=r"economy 1 tick 1, expected 0"):
        session.advance()

    assert state_digest(session.world) == externally_advanced
    assert len(session.events.events) == event_count
    assert session.missing_context_ids == missing
    assert session.phase == AWAITING_HUMAN
    assert not human.pending


def test_bare_economy_uses_session_id_zero_and_executes_domestic_policy():
    economy = Economy(_config(970))
    # Reproduce a legacy/reused object carrying a World-local id.  A bare session
    # must ignore it because its sole canonical address is zero.
    economy.economy_id = 7
    session = ControlledSimulationSession(economy)

    assert session.policy_versions
    assert all(key.startswith("0:") for key in session.policy_versions)
    assert all(key.startswith("0:") for key in policy_state(economy))
    assert not any(key.startswith("7:") for key in session.policy_versions)

    context = session.coordinator.open_context(
        session,
        0,
        "treasury",
        "fiscal_stance",
        {},
        expires_at_tick=0,
    )
    current = next(
        item.current_value
        for item in context.permitted_actions
        if item.lever == "gov_deficit_target"
    )
    proposal = PolicyProposal(
        proposal_id="bare:fiscal",
        idempotency_key="bare:fiscal",
        context_id=context.context_id,
        actions=(PolicyAction("gov_deficit_target", float(current) + 0.005),),
        reason="bare economy regression",
        based_on_policy_versions=dict(context.policy_versions),
    )
    decision = session.coordinator.submit(session, proposal, actor="test")
    assert decision.status == "accepted_pending"

    session.run(8)
    assert economy.t == session.boundary_tick == 8
    assert economy.policy.gov_deficit_target == pytest.approx(float(current) + 0.005)
    assert session.policy_versions[policy_key(0, "gov_deficit_target")] == 1
    assert not any(key.startswith("7:") for key in session.policy_versions)
