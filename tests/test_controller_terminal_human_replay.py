from __future__ import annotations

import copy
import pickle

import pytest

from macro_sim.checkpoint import load_checkpoint, save_checkpoint, session_digest
from macro_sim.config import Config
from macro_sim.controllers.occupants import HumanQueueOccupant, RLOccupant
from macro_sim.controllers.protocol import PolicyProposal, canonical_json
from macro_sim.controllers.replay import replay_input_events
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import AWAITING_HUMAN, ControlledSimulationSession
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


def _world(seed: int) -> World:
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


def _scheduler(*, three: bool) -> DecisionScheduler:
    return DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, offset_ticks=0),
            "tax_and_transfers": CalendarSpec(
                100, offset_ticks=0 if three else 50,
            ),
            "debt_management": CalendarSpec(
                100, offset_ticks=0 if three else 50,
            ),
        },
        triggers=(),
    )


def _mixed_rl_human_scheduler() -> DecisionScheduler:
    due = {"monetary_stance", "fiscal_stance"}
    groups = {lever.decision_group for lever in REGISTRY.values()}
    return DecisionScheduler(
        calendars={
            group: CalendarSpec(
                100, offset_ticks=0 if group in due else 50,
            )
            for group in groups
        },
        triggers=(),
    )


def _source(seed: int, *, three: bool = True):
    scheduler = _scheduler(three=three)
    session = ControlledSimulationSession(
        _world(seed), scheduler=scheduler, run_mode="interactive",
    )
    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human, actor="admin")
    opened = session.advance()
    assert opened.status == AWAITING_HUMAN
    return session, human, opened


def _proposal(context, proposal_id: str) -> PolicyProposal:
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(),
        based_on_policy_versions=dict(context.policy_versions),
    )


def _rl_hold(_context):
    return ()


def _replay(source, seed: int, *, three: bool = True):
    replay = ControlledSimulationSession(
        _world(seed), scheduler=_scheduler(three=three), run_mode="replay",
    )
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=source.boundary_tick,
        expected_events=copy.deepcopy(source.events.events),
    )
    return replay


def _assert_terminal_equal(source, replay):
    assert replay.boundary_tick == replay.world.t == source.boundary_tick
    assert replay.phase == source.phase
    assert replay.current_context_ids == source.current_context_ids
    assert replay.missing_context_ids == source.missing_context_ids
    assert replay._collected == source._collected
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    assert session_digest(replay) == session_digest(source)


def test_terminal_partial_collection_replays_without_crossing_until_tick():
    source, _human, opened = _source(1501)
    proposal = _proposal(opened.contexts[0], "terminal-partial")
    source.submit_human_proposal(proposal, actor="alice")
    polled = source.advance()
    assert polled.status == AWAITING_HUMAN
    assert len(source.missing_context_ids) == 2
    assert set(source._collected) == {proposal.context_id}

    replay = _replay(source, 1501)
    _assert_terminal_equal(source, replay)
    assert [
        event["event_type"] for event in source.events.events[-2:]
    ] == ["human_proposal_queued", "human_proposal_collected"]


def test_terminal_queued_but_unpolled_mailbox_replays_exactly():
    source, human, opened = _source(1502)
    proposal = _proposal(opened.contexts[0], "terminal-queued")
    source.submit_human_proposal(proposal, actor="alice")
    assert proposal.context_id in human.pending
    assert not source._collected

    replay = _replay(source, 1502)
    _assert_terminal_equal(source, replay)
    replay_human = replay.seat_assignments[(0, "treasury")]
    assert replay_human.pending == human.pending


def test_direct_mailbox_preload_before_context_open_is_rejected_atomically():
    session = ControlledSimulationSession(
        _world(1510), scheduler=_scheduler(three=True), run_mode="interactive",
    )
    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human, actor="admin")

    # Context IDs are deterministic, so an integration could try to predict one
    # and bypass the session ingress before the decision window is exposed.
    probe = pickle.loads(pickle.dumps(session, protocol=5))
    predicted = probe.advance().contexts[0]
    proposal = _proposal(predicted, "pre-open-direct-mailbox")
    assert human.submit(proposal, actor="alice") is True
    digest_before = session_digest(session)
    events_before = session.events.canonical_bytes()

    with pytest.raises(ValueError, match="before its context opened"):
        session.advance()

    assert session.phase == "boundary_start"
    assert session.current_context_ids == ()
    assert session.missing_context_ids == ()
    assert session._opened_contexts == {}
    assert human.pending[predicted.context_id] == proposal
    assert session.events.canonical_bytes() == events_before
    assert session_digest(session) == digest_before


def test_terminal_partial_timeout_replays_exactly():
    source, _human, opened = _source(1503)
    timed_out = opened.contexts[0].context_id
    source.timeout_context(timed_out, actor="deadline")
    assert source.phase == AWAITING_HUMAN
    assert timed_out in source._collected

    replay = _replay(source, 1503)
    _assert_terminal_equal(source, replay)


def test_terminal_live_rl_collection_with_human_pause_replays_exactly(tmp_path):
    source = ControlledSimulationSession(
        _world(1511),
        scheduler=_mixed_rl_human_scheduler(),
        run_mode="interactive",
    )
    source.assign_seat(0, "central_bank", RLOccupant(policy=_rl_hold))
    source.assign_seat(0, "treasury", HumanQueueOccupant())

    opened = source.advance()
    assert opened.status == AWAITING_HUMAN
    assert {source._opened_contexts[key].seat for key in source._collected} == {
        "central_bank",
    }
    assert {source._opened_contexts[key].seat for key in source.missing_context_ids} == {
        "treasury",
    }
    rl_input = next(
        event for event in source.events.events
        if event["event_type"] == "proposal_submitted"
        and event.get("payload", {}).get("input_origin") == "automatic"
    )
    assert rl_input["phase"] == "boundary_start"

    checkpoint_path = tmp_path / "mixed-rl-human-awaiting.msim"
    save_checkpoint(
        str(checkpoint_path), source, tick=source.boundary_tick,
    )
    loaded, _, _ = load_checkpoint(str(checkpoint_path))
    assert loaded.phase == source.phase
    assert loaded._collected == source._collected

    replay = ControlledSimulationSession(
        _world(1511),
        scheduler=_mixed_rl_human_scheduler(),
        run_mode="replay",
    )
    replay_input_events(
        replay,
        copy.deepcopy(source.events.input_events()),
        until_tick=source.boundary_tick,
        expected_events=copy.deepcopy(source.events.events),
    )

    assert replay.phase == source.phase == AWAITING_HUMAN
    assert replay.current_context_ids == source.current_context_ids
    assert replay.missing_context_ids == source.missing_context_ids
    assert replay._collected == source._collected
    assert replay.events.canonical_bytes() == source.events.canonical_bytes()
    replay_rl = replay.seat_assignments[(0, "central_bank")]
    assert isinstance(replay_rl, RLOccupant)
    assert replay_rl.policy is None


def test_complete_human_boundary_records_ingress_once_and_replays():
    source, _human, opened = _source(1504, three=False)
    proposal = _proposal(opened.contexts[0], "complete-human")
    source.submit_human_proposal(proposal, actor="alice")
    assert source.advance().status == "advanced"

    replay = _replay(source, 1504, three=False)
    _assert_terminal_equal(source, replay)
    assert sum(
        event["event_type"] == "human_proposal_queued"
        for event in source.events.events
    ) == 1
    assert not any(
        event["event_type"] == "proposal_submitted"
        and event["proposal_id"] == proposal.proposal_id
        for event in source.events.events
    )


def test_queue_retry_and_event_append_failure_are_atomic(monkeypatch):
    source, human, opened = _source(1505)
    proposal = _proposal(opened.contexts[0], "atomic-queue-event")
    before = (
        pickle.dumps(human, protocol=5),
        source.events.canonical_bytes(),
        source.events.head_hash,
        set(source._recorded_human_context_ids),
    )
    original_append = source.events.append

    def fail_append(*args, **kwargs):
        if args and args[0] == "human_proposal_queued":
            raise ValueError("synthetic queue event failure")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(source.events, "append", fail_append)
    with pytest.raises(ValueError, match="synthetic queue event failure"):
        source.submit_human_proposal(proposal, actor="alice")
    assert (
        pickle.dumps(human, protocol=5),
        source.events.canonical_bytes(),
        source.events.head_hash,
        set(source._recorded_human_context_ids),
    ) == before

    monkeypatch.setattr(source.events, "append", original_append)
    source.submit_human_proposal(proposal, actor="alice")
    event_count = len(source.events.events)
    source.submit_human_proposal(proposal, actor="alice")
    assert len(source.events.events) == event_count


def test_timeout_event_append_failure_is_atomic(monkeypatch):
    source, human, opened = _source(1506)
    context_id = opened.contexts[0].context_id
    before = (
        pickle.dumps(human, protocol=5),
        source.phase,
        source.missing_context_ids,
        dict(source._collected),
        source.events.canonical_bytes(),
        source.events.head_hash,
    )
    original_append = source.events.append

    def fail_append(*args, **kwargs):
        if args and args[0] == "timeout":
            raise ValueError("synthetic timeout event failure")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(source.events, "append", fail_append)
    with pytest.raises(ValueError, match="synthetic timeout event failure"):
        source.timeout_context(context_id, actor="deadline")
    assert (
        pickle.dumps(human, protocol=5),
        source.phase,
        source.missing_context_ids,
        dict(source._collected),
        source.events.canonical_bytes(),
        source.events.head_hash,
    ) == before


def test_direct_mailbox_submit_is_backfilled_at_poll_and_replays():
    source, human, opened = _source(1507)
    proposal = _proposal(opened.contexts[0], "direct-mailbox")
    assert human.submit(proposal, actor="alice") is True
    assert not any(
        event["event_type"] == "human_proposal_queued"
        for event in source.events.events
    )
    assert source.advance().status == AWAITING_HUMAN
    assert [
        event["event_type"] for event in source.events.events[-2:]
    ] == ["human_proposal_queued", "human_proposal_collected"]

    replay = _replay(source, 1507)
    _assert_terminal_equal(source, replay)


class _SecretReleaseService:
    def publish_due(self, world, boundary_tick, *, economy_id=0):
        return ()

    def observe(
        self, world, boundary_tick, *, economy_id=0, role="public",
        elapsed_ticks=0,
    ):
        return {"confidential_release": "DO_NOT_LOG_SENTINEL"}


def test_human_ingress_and_collection_events_do_not_embed_context_observation():
    session = ControlledSimulationSession(
        _world(1508),
        scheduler=_scheduler(three=True),
        release_service=_SecretReleaseService(),
    )
    human = HumanQueueOccupant()
    session.assign_seat(0, "treasury", human)
    opened = session.advance()
    proposal = _proposal(opened.contexts[0], "secret-safe")
    session.submit_human_proposal(proposal, actor="alice")
    session.advance()
    session.timeout_context(session.missing_context_ids[0], actor="deadline")

    relevant = [
        event for event in session.events.events
        if event["event_type"] in {
            "human_proposal_queued", "human_proposal_collected", "timeout",
        }
    ]
    assert relevant
    assert "DO_NOT_LOG_SENTINEL" not in canonical_json(relevant)


def test_checkpoint_rejects_tampered_recorded_human_marker(tmp_path):
    source, _human, opened = _source(1509)
    proposal = _proposal(opened.contexts[0], "marker-tamper")
    source.submit_human_proposal(proposal, actor="alice")

    missing_marker = pickle.loads(pickle.dumps(source, protocol=5))
    missing_marker._recorded_human_context_ids.clear()
    with pytest.raises(ValueError, match="disagrees with event log"):
        save_checkpoint(
            str(tmp_path / "missing-marker.msim"),
            missing_marker,
            tick=missing_marker.boundary_tick,
        )

    extra_marker = pickle.loads(pickle.dumps(source, protocol=5))
    extra_marker._recorded_human_context_ids.add("ctx:not-current")
    with pytest.raises(ValueError, match="non-current contexts"):
        save_checkpoint(
            str(tmp_path / "extra-marker.msim"),
            extra_marker,
            tick=extra_marker.boundary_tick,
        )

    polled = source.advance()
    assert polled.status == AWAITING_HUMAN
    wrong_metadata = pickle.loads(pickle.dumps(source, protocol=5))
    context_id = proposal.context_id
    queued, actor, _kind = wrong_metadata._collected[context_id]
    wrong_metadata._collected[context_id] = (
        queued, actor, "automatic_recorded",
    )
    with pytest.raises(ValueError, match="marker/collection metadata disagree"):
        save_checkpoint(
            str(tmp_path / "wrong-marker-kind.msim"),
            wrong_metadata,
            tick=wrong_metadata.boundary_tick,
        )
