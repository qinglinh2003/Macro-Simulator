from __future__ import annotations

import json
import pickle
import zipfile

import pytest

from macro_sim.checkpoint import load_checkpoint, save_checkpoint, session_digest, state_digest
from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.occupants import HumanQueueOccupant, NullOccupant, RandomFuzzOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.scheduler import (
    CalendarSpec,
    DecisionScheduler,
    TriggerSpec,
)
from macro_sim.controllers.session import AWAITING_HUMAN, ControlledSimulationSession
from macro_sim.controllers.transaction import policy_state
from macro_sim.world import World


def _config(seed: int = 12) -> Config:
    return Config.v13(
        seed=seed,
        n_households=10,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=1,
        demographics_population=40,
        n_ticks=40,
        government=True,
    )


def _world(seed: int = 12) -> World:
    return World([_config(seed)])


def _treasury_scheduler() -> DecisionScheduler:
    # Only fiscal_stance meets at genesis.  The other Treasury calendars have a
    # far-away offset, keeping each acceptance test focused on one context.
    return DecisionScheduler(calendars={
        "fiscal_stance": CalendarSpec(100, offset_ticks=0, admin_capacity=20.0),
        "tax_and_transfers": CalendarSpec(100, offset_ticks=50, admin_capacity=20.0),
        "debt_management": CalendarSpec(100, offset_ticks=50, admin_capacity=20.0),
    })


def _human_treasury_session(seed: int = 12) -> tuple[ControlledSimulationSession, HumanQueueOccupant]:
    session = ControlledSimulationSession(
        _world(seed), scheduler=_treasury_scheduler(), run_mode="interactive",
    )
    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human, actor="admin")
    return session, human


def _proposal(
    context,
    *,
    proposal_id: str = "human:fiscal:0",
    value: float | None = None,
    versions: dict[str, int] | None = None,
) -> PolicyProposal:
    if value is None:
        current = next(
            item.current_value
            for item in context.permitted_actions
            if item.lever == "gov_deficit_target"
        )
        value = float(current) + 0.005
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(PolicyAction("gov_deficit_target", value),),
        reason="fiscal_test",
        based_on_policy_versions=(
            dict(context.policy_versions) if versions is None else dict(versions)
        ),
    )


def _open_human_context(session: ControlledSimulationSession):
    result = session.advance()
    assert result.status == AWAITING_HUMAN
    assert len(result.contexts) == 1
    assert result.contexts[0].decision_group == "fiscal_stance"
    return result.contexts[0]


def _accept_pending(session: ControlledSimulationSession) -> tuple[PolicyProposal, object]:
    context = _open_human_context(session)
    proposal = _proposal(context)
    session.submit_human_proposal(proposal)
    result = session.advance()
    assert result.status == "advanced"
    accepted = [item for item in result.decisions if item.proposal_id == proposal.proposal_id]
    assert len(accepted) == 1
    assert accepted[0].status == "accepted_pending"
    return proposal, accepted[0]


def test_null_session_preserves_uncontrolled_engine_record_digest():
    baseline = _world()
    baseline.run(5)

    controlled_world = _world()
    session = ControlledSimulationSession(controlled_world)
    for seat in SEATS:
        session.assign_seat(0, seat, NullOccupant(), actor="test")
    session.run(5)

    # Controller audit events are intentionally different; the actual engine
    # trajectory and its historical digest must remain byte-identical.
    assert state_digest(session.world) == state_digest(baseline)
    assert session.world.economies[0].records == baseline.economies[0].records
    assert session.world.world_records == baseline.world_records


def test_repeated_human_pause_poll_does_not_advance_engine_or_occupant_state():
    session, human = _human_treasury_session()
    automated = RandomFuzzOccupant(seed=991, action_probability=0.0)
    session.assign_seat(0, "central_bank", automated, actor="admin")
    first = session.advance()
    assert first.status == AWAITING_HUMAN

    tick = session.world.t
    engine_blob = pickle.dumps(session.world, protocol=5)
    occupant_blob = pickle.dumps(human, protocol=5)
    automated_rng = automated._rng.getstate()
    event_count = len(session.events.events)
    head_hash = session.events.head_hash

    for _ in range(3):
        again = session.advance()
        assert again.status == AWAITING_HUMAN
        assert again.missing_context_ids == first.missing_context_ids

    assert session.world.t == tick == 0
    assert session.world.economies[0].t == 0
    assert pickle.dumps(session.world, protocol=5) == engine_blob
    assert pickle.dumps(human, protocol=5) == occupant_blob
    assert automated._rng.getstate() == automated_rng
    assert len(session.events.events) == event_count
    assert session.events.head_hash == head_hash


def test_trigger_hysteresis_persistence_and_cooldown_prevent_repeat_sessions():
    scheduler = DecisionScheduler(triggers=(TriggerSpec(
        trigger_id="bank_stress",
        series_id="stress",
        enter_threshold=10.0,
        exit_threshold=5.0,
        min_persist_ticks=2,
        cooldown_ticks=3,
        authorized_seats=("central_bank", "regulator"),
        decision_group="liquidity_operations",
    ),))

    assert scheduler.evaluate_triggers(1, 0, {"stress": 11.0}) == []
    first = scheduler.evaluate_triggers(2, 0, {"stress": 12.0})
    assert [notice.trigger_id for notice in first] == ["bank_stress"]
    # Staying above the entry threshold does not fire every tick.
    assert scheduler.evaluate_triggers(3, 0, {"stress": 20.0}) == []
    # Crossing the exit threshold rearms, but persistence is still required.
    assert scheduler.evaluate_triggers(4, 0, {"stress": 4.0}) == []
    assert scheduler.evaluate_triggers(5, 0, {"stress": 11.0}) == []
    second = scheduler.evaluate_triggers(6, 0, {"stress": 12.0})
    assert [notice.trigger_id for notice in second] == ["bank_stress"]
    assert second[0].seats == ("central_bank", "regulator")


def test_idempotent_retry_does_not_double_reserve_cost_or_append_events():
    session, _human = _human_treasury_session()
    proposal, decision = _accept_pending(session)

    remaining = dict(session.coordinator.admin_remaining)
    reserved = dict(session.coordinator.admin_reserved)
    event_count = len(session.events.events)
    head_hash = session.events.head_hash
    retry = session.coordinator.submit(session, proposal, actor="human")

    assert retry == decision
    assert session.coordinator.admin_remaining == remaining
    assert session.coordinator.admin_reserved == reserved
    assert len(session.events.events) == event_count
    assert session.events.head_hash == head_hash
    assert sum(
        event["event_type"] == "human_proposal_queued"
        and event["proposal_id"] == proposal.proposal_id
        for event in session.events.events
    ) == 1

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
        session.coordinator.submit(session, altered, actor="human")
    assert session.coordinator.admin_remaining == remaining
    assert session.coordinator.admin_reserved == reserved
    assert len(session.events.events) == event_count


def test_stale_policy_version_and_forged_emergency_context_are_rejected():
    session, _human = _human_treasury_session()
    context = _open_human_context(session)
    stale_versions = dict(context.policy_versions)
    stale_versions["gov_deficit_target"] += 1
    stale = session.coordinator.submit(
        session,
        _proposal(context, proposal_id="stale", versions=stale_versions),
        actor="human",
    )
    assert stale.status == "rejected"
    assert stale.reason_code == "stale_policy_version"

    forged = PolicyProposal(
        proposal_id="forged-emergency",
        idempotency_key="forged-emergency",
        context_id="ctx:0:treasury:emergency:0:emergency",
        actions=(),
        reason="client_declared_emergency",
        based_on_policy_versions={},
    )
    rejected = session.coordinator.submit(session, forged, actor="human")
    assert rejected.status == "rejected"
    assert rejected.reason_code == "unknown_context"
    assert not any(
        item.context_id == forged.context_id and item.emergency
        for item in session.coordinator.contexts.values()
    )


def test_hot_swap_is_an_input_event_and_never_changes_effective_policy():
    session = ControlledSimulationSession(_world(), scheduler=_treasury_scheduler())
    session.assign_seat(0, "treasury", NullOccupant(), actor="admin")
    before = policy_state(session.world)
    fingerprint = session.policy_fingerprint
    tick = session.world.t

    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human, actor="admin")

    assert session.seat_assignments[(0, "treasury")] is human
    assert policy_state(session.world) == before
    assert session.policy_fingerprint == fingerprint
    assert session.world.t == tick
    event = session.events.events[-1]
    assert event["event_type"] == "seat_assignment"
    assert event["replay_class"] == "input"
    assert event["payload"]["old_occupant"] == "NullOccupant"
    assert event["payload"]["new_occupant"] == "HumanQueueOccupant"
    assignment_events = [
        item for item in session.events.events if item["event_type"] == "seat_assignment"
    ]
    assert [item["payload"]["assignment_id"] for item in assignment_events] == [
        "assignment:000000000000", "assignment:000000000001",
    ]

    # P0 binds an already-open context to its original occupant.  Rejecting a
    # mid-window swap keeps replay ordering unambiguous.
    assert session.advance().status == AWAITING_HUMAN
    open_policy = policy_state(session.world)
    open_event_count = len(session.events.events)
    with pytest.raises(RuntimeError, match="clean boundary"):
        session.assign_seat(0, "treasury", NullOccupant(), actor="admin")
    assert policy_state(session.world) == open_policy
    assert len(session.events.events) == open_event_count


def test_pending_checkpoint_roundtrip_resumes_bit_identically(tmp_path):
    original, _human = _human_treasury_session()
    _proposal_used, decision = _accept_pending(original)
    assert decision.decision_id in original.pending
    assert original.pending[decision.decision_id].effective_tick == 7

    checkpoint = tmp_path / "pending.msim"
    save_checkpoint(
        str(checkpoint), original, tick=original.boundary_tick,
    )
    resumed, sidecar, header = load_checkpoint(str(checkpoint))
    assert sidecar == {}
    assert header["session_phase"] == original.phase
    assert session_digest(resumed) == session_digest(original)

    original.run(8)  # boundary 1 -> 9; the pending action lands at boundary 7
    resumed.run(8)
    assert session_digest(resumed) == session_digest(original)
    assert resumed.events.canonical_bytes() == original.events.canonical_bytes()
    assert resumed.world.economies[0].policy.gov_deficit_target == pytest.approx(
        original.world.economies[0].policy.gov_deficit_target
    )


def _rewrite_header(src, dst, **updates):
    with zipfile.ZipFile(src) as source:
        header = json.loads(source.read("header.json"))
        blob = source.read("state.pkl.gz")
    header.update(updates)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED) as target:
        target.writestr("header.json", json.dumps(header))
        target.writestr("state.pkl.gz", blob)


def test_open_human_checkpoint_roundtrip_and_header_tamper_guard(tmp_path):
    original, _human = _human_treasury_session()
    context = _open_human_context(original)
    checkpoint = tmp_path / "open-human.msim"
    save_checkpoint(str(checkpoint), original, tick=original.boundary_tick)

    resumed, _sidecar, header = load_checkpoint(str(checkpoint))
    assert resumed.phase == AWAITING_HUMAN
    assert resumed.missing_context_ids == (context.context_id,)
    assert session_digest(resumed) == session_digest(original)

    # Polling the restored open context is still inert.
    before = session_digest(resumed)
    assert resumed.advance().status == AWAITING_HUMAN
    assert session_digest(resumed) == before

    original.timeout_context(context.context_id)
    resumed.timeout_context(context.context_id)
    original.advance()
    resumed.advance()
    assert session_digest(resumed) == session_digest(original)

    tampered = tmp_path / "tampered.msim"
    _rewrite_header(
        checkpoint,
        tampered,
        event_head_hash="0" * 64,
        event_count=header["event_count"] + 1,
    )
    with pytest.raises(ValueError, match="checkpoint (event_count|event_head_hash)"):
        load_checkpoint(str(tampered))

    tick_tampered = tmp_path / "tick-tampered.msim"
    _rewrite_header(
        checkpoint,
        tick_tampered,
        tick=header["tick"] + 99,
    )
    with pytest.raises(ValueError, match="checkpoint tick"):
        load_checkpoint(str(tick_tampered))


def test_input_only_replay_regenerates_identical_full_derived_stream():
    source, _human = _human_treasury_session(seed=77)
    _proposal_used, _decision = _accept_pending(source)
    source.assign_seat(0, "treasury", NullOccupant(), actor="admin")
    source.run(8)

    expected_events = list(source.events.events)
    inputs = list(source.events.input_events())
    replay = ControlledSimulationSession(
        _world(seed=77), scheduler=_treasury_scheduler(), run_mode="replay",
    )
    replay_input_events(
        replay,
        inputs,
        until_tick=source.boundary_tick,
        expected_events=expected_events,
    )

    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert state_digest(replay.world) == state_digest(source.world)
    assert session_digest(replay) == session_digest(source)
