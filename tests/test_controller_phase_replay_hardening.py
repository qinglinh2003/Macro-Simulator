from __future__ import annotations

import copy

import pytest

from macro_sim.checkpoint import session_digest, state_digest
from macro_sim.config import Config
from macro_sim.controllers.observation import (
    ObservationFieldSpec,
    ObservationSpec,
    ReleaseService,
)
from macro_sim.controllers.occupants import HumanQueueOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    READY_TO_COMMIT,
    ControlledSimulationSession,
)
from macro_sim.core.policy_registry import apply_action_batch
from macro_sim.world import World


def _world(seed: int = 803) -> World:
    return World([Config.v13(
        seed=seed,
        n_households=10,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=1,
        demographics_population=40,
        n_ticks=30,
        government=True,
    )])


def _treasury_scheduler(*, period: int = 100) -> DecisionScheduler:
    return DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(period, offset_ticks=0, admin_capacity=20),
            "tax_and_transfers": CalendarSpec(100, offset_ticks=50),
            "debt_management": CalendarSpec(100, offset_ticks=50),
        },
        triggers=(),
    )


def _human_treasury(seed: int = 803, *, period: int = 100):
    session = ControlledSimulationSession(
        _world(seed), scheduler=_treasury_scheduler(period=period), run_mode="interactive",
    )
    occupant = HumanQueueOccupant()
    session.assign_seat(0, "treasury", occupant, actor="admin")
    return session, occupant


def _proposal(context, proposal_id: str, *, increment: float = 0.005):
    current = next(
        action.current_value
        for action in context.permitted_actions
        if action.lever == "gov_deficit_target"
    )
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(PolicyAction("gov_deficit_target", float(current) + increment),),
        reason="phase_replay_test",
        based_on_policy_versions=dict(context.policy_versions),
    )


def _unknown_proposal(proposal_id: str = "unknown:first") -> PolicyProposal:
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id="ctx:does:not:exist",
        actions=(),
        reason="must_reject",
        based_on_policy_versions={},
    )


def test_human_queue_retries_are_payload_and_actor_idempotent():
    session, human = _human_treasury()
    opened = session.advance()
    assert opened.status == AWAITING_HUMAN
    context = opened.contexts[0]
    proposal = _proposal(context, "human:idempotent")

    session.submit_human_proposal(proposal, actor="alice")
    first_hash = human.payload_hashes[context.context_id]
    session.submit_human_proposal(proposal, actor="alice")
    assert human.pending[context.context_id] == proposal
    assert human.payload_hashes[context.context_id] == first_hash
    assert human.actors[context.context_id] == "alice"

    altered = PolicyProposal(
        proposal_id=proposal.proposal_id,
        idempotency_key=proposal.idempotency_key,
        context_id=proposal.context_id,
        actions=(PolicyAction(
            "gov_deficit_target", float(proposal.actions[0].value) + 0.001,
        ),),
        reason=proposal.reason,
        based_on_policy_versions=proposal.based_on_policy_versions,
    )
    with pytest.raises(ValueError, match="different proposal payload"):
        session.submit_human_proposal(altered, actor="alice")
    with pytest.raises(ValueError, match="different actor"):
        session.submit_human_proposal(proposal, actor="bob")
    with pytest.raises(ValueError, match="queued human proposal"):
        session.timeout_context(context.context_id)

    result = session.advance()
    event = next(
        item for item in session.events.events
        if item["event_type"] == "human_proposal_queued"
        and item["proposal_id"] == proposal.proposal_id
    )
    assert result.status == "advanced"
    assert event["actor"] == "alice"


def test_timeout_and_late_submit_cannot_overwrite_collected_answer():
    session, _human = _human_treasury()
    opened = session.advance()
    context = opened.contexts[0]

    session.timeout_context(context.context_id, actor="deadline")
    assert session.phase == READY_TO_COMMIT
    collected = session._collected[context.context_id]
    with pytest.raises(ValueError, match="not awaiting a human proposal"):
        session.submit_human_proposal(_proposal(context, "too:late"), actor="alice")
    with pytest.raises(ValueError, match="not awaiting a timeout"):
        session.timeout_context(context.context_id)
    assert session._collected[context.context_id] == collected

    result = session.advance()
    assert [decision.status for decision in result.decisions] == ["accepted_noop"]
    timeout_inputs = [
        event for event in session.events.input_events()
        if event["event_type"] == "timeout"
    ]
    assert len(timeout_inputs) == 1
    assert timeout_inputs[0]["actor"] == "deadline"


def test_submit_only_targets_contexts_that_are_still_missing():
    scheduler = DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, offset_ticks=0),
            "tax_and_transfers": CalendarSpec(100, offset_ticks=0),
            "debt_management": CalendarSpec(100, offset_ticks=0),
        },
        triggers=(),
    )
    session = ControlledSimulationSession(_world(807), scheduler=scheduler)
    session.assign_seat(0, "treasury", HumanQueueOccupant(), actor="admin")
    opened = session.advance()
    assert len(opened.missing_context_ids) == 3
    fiscal = next(
        context for context in opened.contexts
        if context.decision_group == "fiscal_stance"
    )
    proposal = _proposal(fiscal, "collected:first")
    session.submit_human_proposal(proposal, actor="alice")

    still_waiting = session.advance()
    assert still_waiting.status == AWAITING_HUMAN
    assert fiscal.context_id not in still_waiting.missing_context_ids
    collected = session._collected[fiscal.context_id]
    # A transport retry of the exact same payload/actor remains idempotent even
    # after this answer was collected while other human contexts are still open.
    session.submit_human_proposal(proposal, actor="alice")
    assert session._collected[fiscal.context_id] == collected

    for context_id in still_waiting.missing_context_ids:
        session.timeout_context(context_id)
    assert session.advance().status == "advanced"


def test_replay_injects_awaiting_cancel_after_context_open():
    source, _human = _human_treasury(seed=811, period=1)
    opened0 = source.advance()
    proposal = _proposal(opened0.contexts[0], "pending:then:cancel")
    source.submit_human_proposal(proposal, actor="alice")
    result0 = source.advance()
    pending = next(decision for decision in result0.decisions if decision.status == "accepted_pending")

    opened1 = source.advance()
    assert opened1.status == AWAITING_HUMAN
    source.cancel_pending(pending.decision_id, actor="alice")
    cancel_event = next(
        event for event in reversed(source.events.events)
        if event["event_type"] == "pending_cancel_requested"
    )
    assert cancel_event["phase"] == AWAITING_HUMAN
    source.timeout_context(opened1.contexts[0].context_id)
    source.advance()

    expected_events = copy.deepcopy(source.events.events)
    replay = ControlledSimulationSession(
        _world(811), scheduler=_treasury_scheduler(period=1), run_mode="replay",
    )
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=source.boundary_tick,
        expected_events=expected_events,
    )
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert state_digest(replay.world) == state_digest(source.world)
    assert replay.coordinator.policy_versions == source.coordinator.policy_versions
    assert replay.coordinator.pending == source.coordinator.pending


def test_replay_preserves_unknown_rejection_before_valid_acceptance():
    source, _human = _human_treasury(seed=821)
    source.submit_human_proposal(_unknown_proposal(), actor="mallory")
    rejected = list(source.coordinator.decisions.values())[-1]
    assert rejected.status == "rejected"
    assert rejected.reason_code == "unknown_context"

    opened = source.advance()
    valid = _proposal(opened.contexts[0], "valid:second")
    source.submit_human_proposal(valid, actor="alice")
    result = source.advance()
    assert any(decision.proposal_id == valid.proposal_id for decision in result.decisions)
    source_statuses = [
        event["status"] for event in source.events.events
        if event["event_type"] in {"decision_rejected", "decision_accepted"}
    ]
    assert source_statuses[:2] == ["rejected", "accepted_pending"]

    expected_events = copy.deepcopy(source.events.events)
    replay = ControlledSimulationSession(
        _world(821), scheduler=_treasury_scheduler(), run_mode="replay",
    )
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=source.boundary_tick,
        expected_events=expected_events,
    )
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert state_digest(replay.world) == state_digest(source.world)
    assert replay.coordinator.policy_versions == source.coordinator.policy_versions
    assert replay.coordinator.pending == source.coordinator.pending


def test_replay_recreates_unlogged_poll_before_ready_phase_input():
    scheduler = DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, offset_ticks=0),
            "debt_management": CalendarSpec(100, offset_ticks=0),
            "tax_and_transfers": CalendarSpec(100, offset_ticks=50),
        },
        triggers=(),
    )
    source = ControlledSimulationSession(
        _world(823), scheduler=scheduler, run_mode="interactive",
    )
    source.assign_seat(0, "treasury", HumanQueueOccupant(), actor="admin")
    opened = source.advance()
    fiscal = next(
        context for context in opened.contexts
        if context.decision_group == "fiscal_stance"
    )
    debt = next(
        context for context in opened.contexts
        if context.decision_group == "debt_management"
    )
    source.submit_human_proposal(_proposal(fiscal, "fiscal:collected"), actor="alice")
    polled = source.advance()
    assert polled.status == AWAITING_HUMAN
    assert polled.missing_context_ids == (debt.context_id,)
    source.timeout_context(debt.context_id)
    assert source.phase == READY_TO_COMMIT
    source.submit_human_proposal(_unknown_proposal("unknown:while:ready"), actor="mallory")
    unknown_event = next(
        event for event in source.events.events
        if event["proposal_id"] == "unknown:while:ready"
        and event["event_type"] == "proposal_submitted"
    )
    assert unknown_event["phase"] == READY_TO_COMMIT
    source.advance()

    replay = ControlledSimulationSession(
        _world(823),
        scheduler=DecisionScheduler(
            calendars=dict(scheduler.calendars), triggers=(),
        ),
        run_mode="replay",
    )
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=source.boundary_tick,
        expected_events=copy.deepcopy(source.events.events),
    )
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()


def test_zero_lag_boundary_result_contains_only_final_decision_state():
    scheduler = DecisionScheduler(
        calendars={
            "monetary_stance": CalendarSpec(100, offset_ticks=0),
            "liquidity_operations": CalendarSpec(100, offset_ticks=50),
            "fx_operations": CalendarSpec(100, offset_ticks=50),
        },
        triggers=(),
    )
    world = _world(829)
    apply_action_batch(
        world.economies[0],
        (("manual_policy_rate", 0.0002), ("monetary_regime", "manual")),
        actor="test_setup",
    )
    session = ControlledSimulationSession(world, scheduler=scheduler)
    session.assign_seat(0, "central_bank", HumanQueueOccupant(), actor="admin")
    opened = session.advance()
    context = opened.contexts[0]
    proposal = PolicyProposal(
        proposal_id="manual:zero:lag",
        idempotency_key="manual:zero:lag",
        context_id=context.context_id,
        actions=(PolicyAction("manual_policy_rate", 0.0001),),
        based_on_policy_versions=dict(context.policy_versions),
    )
    session.submit_human_proposal(proposal, actor="alice")
    result = session.advance()

    matching = [
        decision for decision in result.decisions
        if decision.proposal_id == proposal.proposal_id
    ]
    assert len(matching) == 1
    assert matching[0].status == "effective"
    assert matching[0].adjustment_cost > 0.0


def test_release_publication_runs_without_any_seat_or_context():
    releases = ReleaseService(ObservationSpec((ObservationFieldSpec(
        "inflation_release",
        "inflation",
        frequency_ticks=1,
        publication_lag_ticks=0,
    ),)))
    session = ControlledSimulationSession(_world(839), release_service=releases)
    assert not session.seat_assignments

    session.advance()  # boundary 1 publishes completed record 0 despite no meeting

    history = releases.history(0, "inflation_release")
    assert len(history) == 1
    assert history[0].reference_end_tick == 0
    assert history[0].released_at_tick == 1
