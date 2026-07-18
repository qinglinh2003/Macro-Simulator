from __future__ import annotations

import copy
import pickle

import pytest

from macro_sim.config import Config
from macro_sim.controllers.occupants import HumanQueueOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal, canonical_json
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    READY_TO_COMMIT,
    ControlledSimulationSession,
)
from macro_sim.world import World


def _world(seed: int = 1411) -> World:
    return World([Config.v13(
        seed=seed,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        demographics_population=30,
        n_ticks=20,
        government=True,
    )])


def _treasury_scheduler(*, all_due: bool = False) -> DecisionScheduler:
    return DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, offset_ticks=0),
            "tax_and_transfers": CalendarSpec(
                100, offset_ticks=0 if all_due else 50,
            ),
            "debt_management": CalendarSpec(
                100, offset_ticks=0 if all_due else 50,
            ),
        },
        triggers=(),
    )


def _human_session(seed: int = 1411, *, all_due: bool = False):
    session = ControlledSimulationSession(
        _world(seed),
        scheduler=_treasury_scheduler(all_due=all_due),
        run_mode="interactive",
    )
    occupant = HumanQueueOccupant()
    session.assign_seat(0, "treasury", occupant)
    opened = session.advance()
    assert opened.status == AWAITING_HUMAN
    return session, occupant, opened


def _noop(context, proposal_id: str) -> PolicyProposal:
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(),
        based_on_policy_versions=dict(context.policy_versions),
    )


def _human_state(session, occupant) -> tuple[object, ...]:
    return (
        pickle.dumps(occupant, protocol=5),
        session.phase,
        session.current_context_ids,
        session.missing_context_ids,
        dict(session._collected),
        session.events.canonical_bytes(),
        session.events.head_hash,
        dict(session.coordinator.idempotency),
        dict(session.coordinator.idempotency_payload),
    )


@pytest.mark.parametrize("actor", (None, "", "   ", 7))
def test_human_submit_rejects_poison_actor_before_queue_mutation(actor):
    session, occupant, opened = _human_session()
    proposal = _noop(opened.contexts[0], "human-poison")
    before = _human_state(session, occupant)

    with pytest.raises(ValueError, match="actor must be a non-empty string"):
        session.submit_human_proposal(proposal, actor=actor)

    assert _human_state(session, occupant) == before
    session.submit_human_proposal(proposal, actor="alice")
    assert occupant.pending[proposal.context_id] == proposal


@pytest.mark.parametrize("actor", (None, "", "\t  ", 7))
def test_timeout_rejects_poison_actor_before_collection_or_phase_mutation(actor):
    session, occupant, opened = _human_session(seed=1412)
    context_id = opened.contexts[0].context_id
    before = _human_state(session, occupant)

    with pytest.raises(ValueError, match="actor must be a non-empty string"):
        session.timeout_context(context_id, actor=actor)

    assert _human_state(session, occupant) == before
    session.timeout_context(context_id, actor="deadline")
    assert session.phase == READY_TO_COMMIT
    assert session._collected[context_id][1:] == ("deadline", "timeout")


def _coordinator_state(session: ControlledSimulationSession) -> tuple[object, ...]:
    coordinator = session.coordinator
    return (
        session.events.canonical_bytes(),
        session.events.head_hash,
        coordinator.next_decision_sequence,
        copy.deepcopy(coordinator.idempotency),
        copy.deepcopy(coordinator.idempotency_payload),
        pickle.dumps(coordinator.decisions, protocol=5),
        pickle.dumps(coordinator.pending, protocol=5),
        copy.deepcopy(coordinator.proposal_for_context),
        copy.deepcopy(coordinator.admin_remaining),
        copy.deepcopy(coordinator.admin_reserved),
    )


def _fiscal_action_proposal(context, proposal_id: str) -> PolicyProposal:
    current = next(
        item.current_value
        for item in context.permitted_actions
        if item.lever == "gov_deficit_target"
    )
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(PolicyAction("gov_deficit_target", float(current) + 0.005),),
        based_on_policy_versions=dict(context.policy_versions),
    )


def test_coordinator_public_ingress_validation_and_append_failure_are_atomic(
    monkeypatch,
):
    session = ControlledSimulationSession(_world(1413))
    context = session.coordinator.open_context(
        session,
        0,
        "treasury",
        "fiscal_stance",
        {},
        expires_at_tick=0,
    )
    proposal = _fiscal_action_proposal(context, "coordinator-ingress")
    pristine = _coordinator_state(session)

    with pytest.raises(TypeError, match="proposal must be a PolicyProposal"):
        session.coordinator.submit(session, object(), actor="alice")
    assert _coordinator_state(session) == pristine

    for actor in (None, "", "   ", 3):
        with pytest.raises(ValueError, match="actor must be a non-empty string"):
            session.coordinator.submit(session, proposal, actor=actor)
        assert _coordinator_state(session) == pristine

    for event_type in (None, "", "proposal", " timeout ", []):
        with pytest.raises(ValueError, match="input_event_type must be"):
            session.coordinator.submit(
                session,
                proposal,
                actor="alice",
                input_event_type=event_type,
            )
        assert _coordinator_state(session) == pristine

    original_append = session.events.append

    def fail_append(*args, **kwargs):
        raise ValueError("synthetic event append failure")

    monkeypatch.setattr(session.events, "append", fail_append)
    with pytest.raises(ValueError, match="synthetic event append failure"):
        session.coordinator.submit(session, proposal, actor="alice")
    assert _coordinator_state(session) == pristine
    monkeypatch.setattr(session.events, "append", original_append)

    decision = session.coordinator.submit(session, proposal, actor="alice")
    assert decision.status == "accepted_pending"
    assert session.coordinator.idempotency_payload[proposal.idempotency_key] == (
        canonical_json(proposal.to_dict())
    )
    event_count = len(session.events.events)
    assert session.coordinator.submit(
        session, proposal, actor="alice",
    ) == decision
    assert len(session.events.events) == event_count
    before_cancel = _coordinator_state(session)
    with pytest.raises(ValueError, match="actor must be a non-empty string"):
        session.cancel_pending(decision.decision_id, actor="   ")
    assert _coordinator_state(session) == before_cancel


def test_alias_normalization_preserves_original_wire_payload_for_retry():
    session = ControlledSimulationSession(_world(1414))
    context = session.coordinator.open_context(
        session,
        0,
        "regulator",
        "macroprudential",
        {},
        expires_at_tick=0,
    )
    canonical = "regulatory_firm_capital_haircut"
    current = next(
        item.current_value
        for item in context.permitted_actions
        if item.lever == canonical
    )
    proposal = PolicyProposal(
        proposal_id="alias-idempotency",
        idempotency_key="alias-idempotency",
        context_id=context.context_id,
        actions=(PolicyAction("firm_capital_haircut", float(current) + 0.01),),
        based_on_policy_versions=dict(context.policy_versions),
    )

    decision = session.coordinator.submit(session, proposal, actor="alice")
    assert decision.status == "accepted_pending"
    assert session.coordinator.idempotency_payload[proposal.idempotency_key] == (
        canonical_json(proposal.to_dict())
    )
    event_count = len(session.events.events)
    assert session.coordinator.submit(
        session, proposal, actor="alice",
    ) == decision
    assert len(session.events.events) == event_count
