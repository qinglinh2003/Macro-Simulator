"""Final regressions for wire sets, cancellation atomicity, and replay boundaries."""
from __future__ import annotations

import copy
import hashlib

import pytest

from macro_sim.checkpoint import session_digest
from macro_sim.config import Config
from macro_sim.controllers.events import EventStream
from macro_sim.controllers.occupants import HumanQueueOccupant, NullOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal, canonical_json
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    BOUNDARY_START,
    READY_TO_COMMIT,
    ControlledSimulationSession,
)
from macro_sim.world import World


def _config(seed: int) -> Config:
    return Config.v13(
        seed=seed,
        n_households=10,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=1,
        demographics_population=40,
        n_ticks=20,
        government=True,
    )


def _treasury_scheduler() -> DecisionScheduler:
    return DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, offset_ticks=0, admin_capacity=20),
            "tax_and_transfers": CalendarSpec(100, offset_ticks=50),
            "debt_management": CalendarSpec(100, offset_ticks=50),
        },
        triggers=(),
    )


def _treasury_session(seed: int) -> ControlledSimulationSession:
    return ControlledSimulationSession(
        World([_config(seed)]), scheduler=_treasury_scheduler(), run_mode="replay",
    )


def _proposal(context, proposal_id: str) -> PolicyProposal:
    current = next(
        item.current_value for item in context.permitted_actions
        if item.lever == "gov_deficit_target"
    )
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(PolicyAction("gov_deficit_target", float(current) + 0.005),),
        based_on_policy_versions=dict(context.policy_versions),
    )


def test_sanctions_wire_values_are_sorted_deduplicated_set_semantics():
    proposals = []
    for raw in ([1, 2], [2, 1], [1, 1, 2], (2, 1), {1, 2}):
        action = PolicyAction("sanctions_imposed_on", raw)
        proposals.append(PolicyProposal(
            "proposal:sanctions:set",
            "proposal:sanctions:set",
            "context:sanctions:set",
            (action,),
            based_on_policy_versions={"sanctions_imposed_on": 0},
        ))
        assert action.value == (1, 2)
        assert action.engine_value() == frozenset({1, 2})

    payloads = [canonical_json(proposal.to_dict()) for proposal in proposals]
    hashes = [hashlib.sha256(payload.encode()).hexdigest() for payload in payloads]
    assert len(set(payloads)) == 1
    assert len(set(hashes)) == 1
    assert PolicyAction("sanctions_imposed_on", [10, 2]).value == (2, 10)

    idempotent_world = World(
        [_config(891), _config(892), _config(893)], couple=True, trade=True,
    )
    idempotent_session = ControlledSimulationSession(idempotent_world)
    idempotent_context = idempotent_session.coordinator.open_context(
        idempotent_session,
        0,
        "external_affairs",
        "trade_and_migration",
        {},
        expires_at_tick=0,
    )

    def sanctions_proposal(raw) -> PolicyProposal:
        return PolicyProposal(
            "proposal:sanctions:idempotent",
            "proposal:sanctions:idempotent",
            idempotent_context.context_id,
            (PolicyAction("sanctions_imposed_on", raw),),
            based_on_policy_versions=dict(idempotent_context.policy_versions),
        )

    first = idempotent_session.coordinator.submit(
        idempotent_session, sanctions_proposal([1, 2]), actor="client",
    )
    event_count = len(idempotent_session.events.events)
    retry = idempotent_session.coordinator.submit(
        idempotent_session, sanctions_proposal([2, 1, 1]), actor="client",
    )
    assert retry == first
    assert len(idempotent_session.events.events) == event_count

    # JSON-safe but invalid domain elements remain wire-constructible; authority
    # belongs to the Coordinator's runtime-sized reference validation.
    invalid = PolicyAction("sanctions_imposed_on", [True, "1", -1])
    assert invalid.to_dict()["value"] == ["1", -1, True]
    world = World([_config(901), _config(902)], couple=True, trade=True)
    session = ControlledSimulationSession(world)
    context = session.coordinator.open_context(
        session,
        0,
        "external_affairs",
        "trade_and_migration",
        {},
        expires_at_tick=0,
    )
    proposal = PolicyProposal(
        "proposal:sanctions:invalid",
        "proposal:sanctions:invalid",
        context.context_id,
        (invalid,),
        based_on_policy_versions=dict(context.policy_versions),
    )
    decision = session.coordinator.submit(session, proposal, actor="test")
    assert decision.status == "rejected"
    assert decision.reason_code == "dynamic_reference:invalid_sanctions_target"

    for suffix, raw in (("bool", [1, True]), ("float", [1, 1.0])):
        mixed = PolicyProposal(
            f"proposal:sanctions:mixed:{suffix}",
            f"proposal:sanctions:mixed:{suffix}",
            context.context_id,
            (PolicyAction("sanctions_imposed_on", raw),),
            based_on_policy_versions=dict(context.policy_versions),
        )
        rejected = session.coordinator.submit(session, mixed, actor="test")
        assert rejected.status == "rejected"
        assert rejected.reason_code == "dynamic_reference:invalid_sanctions_target"


def test_invalid_and_duplicate_cancel_are_zero_event_zero_mutation():
    session = _treasury_session(911)
    context = session.coordinator.open_context(
        session, 0, "treasury", "fiscal_stance", {}, expires_at_tick=0,
    )
    decision = session.coordinator.submit(
        session, _proposal(context, "proposal:cancel:atomic"), actor="alice",
    )
    assert decision.status == "accepted_pending"
    key = (0, "treasury", "fiscal_stance")

    def snapshot():
        return (
            session.events.canonical_bytes(),
            session.events.head_hash,
            session.coordinator.pending[decision.decision_id].status,
            session.coordinator.decisions[decision.decision_id],
            session.coordinator.admin_remaining[key],
            session.coordinator.admin_reserved[key],
        )

    pristine = snapshot()
    with pytest.raises(ValueError, match="not active pending"):
        session.cancel_pending("decision:does:not:exist", actor="alice")
    assert snapshot() == pristine

    for actor in ("", None, 7):
        with pytest.raises(ValueError, match="actor must be a non-empty string"):
            session.cancel_pending(decision.decision_id, actor=actor)  # type: ignore[arg-type]
        assert snapshot() == pristine

    cancelled = session.cancel_pending(decision.decision_id, actor="alice")
    assert cancelled.status == "cancelled"
    after_cancel = snapshot()
    assert len(session.events.events) == 4  # submit+accept, cancel request+result
    with pytest.raises(ValueError, match="not active pending"):
        session.cancel_pending(decision.decision_id, actor="alice")
    assert snapshot() == after_cancel


def test_replay_includes_tick_zero_boundary_start_assignment_without_advancing():
    source = _treasury_session(921)
    source.assign_seat(0, "treasury", HumanQueueOccupant(), actor="admin")
    assert source.boundary_tick == source.world.t == 0
    assert source.phase == BOUNDARY_START

    replay = _treasury_session(921)
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=0,
        expected_events=copy.deepcopy(source.events.events),
    )

    assert replay.boundary_tick == replay.world.t == 0
    assert replay.phase == BOUNDARY_START
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert session_digest(replay) == session_digest(source)


def test_replay_recreates_terminal_open_human_pause_without_engine_tick():
    source = _treasury_session(931)
    source.assign_seat(0, "treasury", HumanQueueOccupant(), actor="admin")
    opened = source.advance()
    assert opened.status == AWAITING_HUMAN
    assert source.boundary_tick == source.world.t == 0
    unknown = PolicyProposal(
        "proposal:terminal:unknown",
        "proposal:terminal:unknown",
        "ctx:terminal:not-open",
        (),
        based_on_policy_versions={},
    )
    source.submit_human_proposal(unknown, actor="intruder")
    assert source.phase == AWAITING_HUMAN

    replay = _treasury_session(931)
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=0,
        expected_events=copy.deepcopy(source.events.events),
    )

    assert replay.boundary_tick == replay.world.t == 0
    assert replay.phase == AWAITING_HUMAN
    assert replay.current_context_ids == source.current_context_ids
    assert replay.missing_context_ids == source.missing_context_ids
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert session_digest(replay) == session_digest(source)


def test_replay_rejects_unsupported_terminal_boundary_input_explicitly():
    tape = EventStream()
    unsupported = tape.append(
        "timeout",
        "input",
        0,
        READY_TO_COMMIT,
        actor="deadline",
        context_id="ctx:not-open",
    )
    replay = _treasury_session(941)

    with pytest.raises(ValueError, match="unsupported input at terminal boundary"):
        replay_input_events(replay, [unsupported], until_tick=0)
    assert replay.events.events == []
    assert replay.boundary_tick == replay.world.t == 0


def test_terminal_replay_never_advances_automatic_occupant_tick():
    source = _treasury_session(951)
    source.assign_seat(0, "treasury", NullOccupant(), actor="admin")
    assert source.advance().status == "advanced"
    assert source.boundary_tick == source.world.t == 1

    replay = _treasury_session(951)
    with pytest.raises(ValueError, match="not an open human pause"):
        replay_input_events(
            replay,
            copy.deepcopy(source.events.input_events()),
            until_tick=0,
            expected_events=copy.deepcopy(source.events.events),
        )

    # The boundary-start seat assignment is a legal terminal input, but tick zero
    # itself remains exclusive and must not run even on a rejected tape.
    assert replay.boundary_tick == replay.world.t == 0

    # Even a truncated tape that hides all READY_TO_COMMIT evidence cannot trick the
    # terminal path: the isolated probe observes that NullOccupant would run a tick.
    truncated = [
        copy.deepcopy(event) for event in source.events.events
        if event["phase"] != READY_TO_COMMIT
    ]
    replay_from_truncated = _treasury_session(951)
    with pytest.raises(ValueError, match="do not prove an open human pause"):
        replay_input_events(
            replay_from_truncated,
            copy.deepcopy(source.events.input_events()),
            until_tick=0,
            expected_events=truncated,
        )
    assert replay_from_truncated.boundary_tick == replay_from_truncated.world.t == 0
