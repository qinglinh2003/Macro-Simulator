from __future__ import annotations

import copy
import pickle

import pytest

from macro_sim.config import Config
from macro_sim.controllers.occupants import (
    HeuristicOccupant,
    HumanQueueOccupant,
    NullOccupant,
)
from macro_sim.controllers.observation import ObservationSpec, ReleaseService
from macro_sim.controllers.protocol import PolicyProposal
from macro_sim.controllers.scheduler import (
    CalendarSpec,
    DecisionScheduler,
    TriggerSpec,
)
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    BOUNDARY_START,
    ControlledSimulationSession,
)
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


def _world(seed: int = 1301) -> World:
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


def _seat_scheduler(
    seat: str,
    *,
    due_groups: tuple[str, ...] = (),
    triggers: tuple[TriggerSpec, ...] = (),
) -> DecisionScheduler:
    groups = {
        lever.decision_group
        for lever in REGISTRY.values()
        if lever.owner_role == seat
    }
    calendars = {
        group: CalendarSpec(
            100,
            offset_ticks=0 if group in due_groups else 50,
            admin_capacity=11.0,
        )
        for group in groups
    }
    for trigger in triggers:
        calendars.setdefault(
            trigger.decision_group,
            CalendarSpec(100, offset_ticks=50, admin_capacity=7.0),
        )
    return DecisionScheduler(calendars=calendars, triggers=triggers)


def _noop_proposal(context, proposal_id: str) -> PolicyProposal:
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(),
        reason="atomicity_test",
        based_on_policy_versions=dict(context.policy_versions),
    )


def _assignment_state(session: ControlledSimulationSession) -> tuple[object, ...]:
    return (
        dict(session.seat_assignments),
        dict(session.assignment_archive),
        session.next_assignment_sequence,
        session.events.canonical_bytes(),
        session.events.head_hash,
    )


def test_assign_seat_rejects_before_assignment_archive_or_sequence_mutation():
    session = ControlledSimulationSession(_world())
    original = NullOccupant()
    session.assign_seat(0, "treasury", original)
    before = _assignment_state(session)

    with pytest.raises(ValueError, match="finite numbers"):
        session.assign_seat(
            0,
            "treasury",
            HeuristicOccupant(parameters={"gain": float("nan")}),
        )

    assert _assignment_state(session) == before
    assert session.seat_assignments[(0, "treasury")] is original


@pytest.mark.parametrize(
    ("economy_id", "seat", "actor", "initialization", "occupant", "error"),
    (
        (False, "treasury", "admin", "fresh", NullOccupant(), TypeError),
        (0, "not-a-seat", "admin", "fresh", NullOccupant(), ValueError),
        (0, "treasury", "", "fresh", NullOccupant(), ValueError),
        (0, "treasury", "admin", "warm", NullOccupant(), ValueError),
        (0, "treasury", "admin", "fresh", object(), TypeError),
    ),
)
def test_assign_seat_strict_ingress_is_non_mutating(
    economy_id, seat, actor, initialization, occupant, error,
):
    session = ControlledSimulationSession(_world(1302))
    before = _assignment_state(session)
    with pytest.raises(error):
        session.assign_seat(
            economy_id,
            seat,
            occupant,
            actor=actor,
            initialization=initialization,
        )
    assert _assignment_state(session) == before


def test_restore_initialization_requires_existing_exact_archive_object():
    session = ControlledSimulationSession(_world(1303))
    first = NullOccupant()
    second = HumanQueueOccupant()
    session.assign_seat(0, "treasury", first)
    session.assign_seat(0, "treasury", second)
    archive_id = session.events.events[-1]["payload"]["archived_outgoing_id"]
    before = _assignment_state(session)

    with pytest.raises(ValueError, match="referenced archive object"):
        session.assign_seat(
            0,
            "treasury",
            NullOccupant(),
            initialization=f"restore:{archive_id}",
        )
    assert _assignment_state(session) == before

    with pytest.raises(ValueError, match="reference an archived occupant"):
        session.assign_seat(
            0,
            "treasury",
            first,
            initialization="restore:not-present",
        )
    assert _assignment_state(session) == before

    session.restore_seat(0, "treasury", archive_id)
    assert session.seat_assignments[(0, "treasury")] is first


def test_simultaneous_emergency_triggers_open_distinct_shared_budget_contexts():
    triggers = (
        TriggerSpec(
            "crisis_a",
            "stress_a",
            enter_threshold=1.0,
            exit_threshold=0.0,
            authorized_seats=("central_bank",),
            decision_group="shared_crisis",
        ),
        TriggerSpec(
            "crisis_b",
            "stress_b",
            enter_threshold=1.0,
            exit_threshold=0.0,
            authorized_seats=("central_bank",),
            decision_group="shared_crisis",
        ),
    )
    scheduler = _seat_scheduler("central_bank", triggers=triggers)
    scheduler.last_context_tick[(0, "central_bank", "shared_crisis")] = -5
    session = ControlledSimulationSession(_world(1304), scheduler=scheduler)
    session.assign_seat(0, "central_bank", HumanQueueOccupant())
    session.world.economies[0].records.append({
        "stress_a": 2.0,
        "stress_b": 3.0,
    })

    opened = session.advance()

    assert opened.status == AWAITING_HUMAN
    contexts = [
        context
        for context in opened.contexts
        if context.decision_group == "shared_crisis"
    ]
    assert len(contexts) == 2
    assert {context.emergency_trigger for context in contexts} == {
        "crisis_a",
        "crisis_b",
    }
    assert len({context.context_id for context in contexts}) == 2
    assert {context.elapsed_ticks for context in contexts} == {5}
    assert {context.admin_capacity for context in contexts} == {7.0}
    budget_key = (0, "central_bank", "shared_crisis")
    assert session.coordinator.admin_remaining == {budget_key: 7.0}
    trigger_events = [
        event
        for event in session.events.events
        if event["event_type"] == "emergency_trigger"
        and event["reason"] in {"crisis_a", "crisis_b"}
    ]
    assert len(trigger_events) == 2
    assert len({event["context_id"] for event in trigger_events}) == 2


class _BoundaryFailureOccupant:
    failure_mode = "raise"

    def __init__(self) -> None:
        self.calls = 0
        self.private_history: list[str] = []

    def propose(self, context):
        self.calls += 1
        self.private_history.append(context.context_id)
        if type(self).failure_mode == "raise":
            raise RuntimeError("occupant failure")
        if type(self).failure_mode == "bad_return":
            return {"not": "a PolicyProposal"}
        return _noop_proposal(context, f"retry:{context.context_id}")


@pytest.mark.parametrize("failure_mode", ("raise", "bad_return"))
def test_boundary_callback_failure_rolls_back_all_boundary_state_and_retries(
    failure_mode,
):
    trigger = TriggerSpec(
        "atomic_crisis",
        "atomic_stress",
        enter_threshold=1.0,
        exit_threshold=0.0,
        authorized_seats=("treasury",),
        decision_group="atomic_group",
    )
    scheduler = _seat_scheduler("treasury", triggers=(trigger,))
    session = ControlledSimulationSession(_world(1305), scheduler=scheduler)
    occupant = _BoundaryFailureOccupant()
    session.assign_seat(0, "treasury", occupant, log_event=False)
    session.world.economies[0].records.append({"atomic_stress": 2.0})
    _BoundaryFailureOccupant.failure_mode = failure_mode

    release_before = pickle.dumps(session.release_service, protocol=5)
    trigger_before = copy.deepcopy(session.scheduler.trigger_states)
    last_context_before = dict(session.scheduler.last_context_tick)
    coordinator_contexts_before = dict(session.coordinator.contexts)
    admin_before = (
        dict(session.coordinator.admin_remaining),
        dict(session.coordinator.admin_reserved),
        dict(session.coordinator.admin_replenished_at),
    )
    events_before = session.events.canonical_bytes()
    head_before = session.events.head_hash

    expected_error = RuntimeError if failure_mode == "raise" else TypeError
    with pytest.raises(expected_error):
        session.advance()

    assert session.phase == BOUNDARY_START
    assert session.current_context_ids == session.missing_context_ids == ()
    assert not session._opened_contexts
    assert not session._collected
    assert pickle.dumps(session.release_service, protocol=5) == release_before
    assert session.scheduler.trigger_states == trigger_before
    assert session.scheduler.last_context_tick == last_context_before
    assert session.coordinator.contexts == coordinator_contexts_before
    assert (
        session.coordinator.admin_remaining,
        session.coordinator.admin_reserved,
        session.coordinator.admin_replenished_at,
    ) == admin_before
    assert session.events.canonical_bytes() == events_before
    assert session.events.head_hash == head_before
    assert occupant.calls == 0
    assert occupant.private_history == []

    _BoundaryFailureOccupant.failure_mode = "ok"
    assert session.advance().status == "advanced"
    assert occupant.calls == 1


class _StatefulReleaseService(ReleaseService):
    """A custom service whose non-base state must participate in rollback."""

    def __init__(self) -> None:
        super().__init__(ObservationSpec(()))
        self.custom_counter = 0
        self.custom_cache: dict[int, list[int]] = {}

    def publish_due(self, engine, boundary_tick, *, economy_id=0):
        self.custom_counter += 1
        self.custom_cache.setdefault(economy_id, []).append(boundary_tick)
        return super().publish_due(
            engine, boundary_tick, economy_id=economy_id,
        )


def test_release_service_subclass_uses_full_state_rollback():
    scheduler = _seat_scheduler(
        "treasury", due_groups=("fiscal_stance",),
    )
    releases = _StatefulReleaseService()
    session = ControlledSimulationSession(
        _world(1312), scheduler=scheduler, release_service=releases,
    )
    occupant = _BoundaryFailureOccupant()
    session.assign_seat(0, "treasury", occupant, log_event=False)
    _BoundaryFailureOccupant.failure_mode = "raise"
    before = pickle.dumps(releases, protocol=5)

    with pytest.raises(RuntimeError, match="occupant failure"):
        session.advance()

    assert session.release_service is releases
    assert pickle.dumps(releases, protocol=5) == before
    assert releases.custom_counter == 0
    assert releases.custom_cache == {}

    _BoundaryFailureOccupant.failure_mode = "ok"
    assert session.advance().status == "advanced"
    assert releases.custom_counter > 0
    assert releases.custom_cache


class _ActorFailureQueue(HumanQueueOccupant):
    fail_actor = True

    def __init__(self) -> None:
        super().__init__()
        self.actor_calls = 0

    def take_actor(self, context_id: str) -> str:
        actor = super().take_actor(context_id)
        self.actor_calls += 1
        if type(self).fail_actor:
            raise RuntimeError("actor lookup failed")
        return actor


def test_take_actor_failure_restores_delivered_queue_and_collection_state():
    scheduler = _seat_scheduler("treasury", due_groups=("fiscal_stance",))
    session = ControlledSimulationSession(_world(1306), scheduler=scheduler)
    occupant = _ActorFailureQueue()
    session.assign_seat(0, "treasury", occupant, log_event=False)
    opened = session.advance()
    assert opened.status == AWAITING_HUMAN
    context = opened.contexts[0]
    proposal = _noop_proposal(context, "actor-retry")
    session.submit_human_proposal(proposal, actor="alice")
    occupant_before = pickle.dumps(occupant, protocol=5)
    collected_before = dict(session._collected)
    missing_before = session.missing_context_ids
    events_before = session.events.canonical_bytes()

    _ActorFailureQueue.fail_actor = True
    with pytest.raises(RuntimeError, match="actor lookup failed"):
        session.advance()

    assert session.phase == AWAITING_HUMAN
    assert session._collected == collected_before
    assert session.missing_context_ids == missing_before
    assert pickle.dumps(occupant, protocol=5) == occupant_before
    assert session.events.canonical_bytes() == events_before

    _ActorFailureQueue.fail_actor = False
    assert session.advance().status == "advanced"
    submitted = next(
        event
        for event in session.events.events
        if event["event_type"] == "human_proposal_queued"
    )
    assert submitted["actor"] == "alice"


class _MustNotCopyOccupant:
    def __deepcopy__(self, memo):
        raise AssertionError("occupant without a due context was copied")

    def propose(self, context):
        raise AssertionError("occupant without a due context was called")


def test_occupant_snapshot_is_skipped_when_no_context_is_due():
    session = ControlledSimulationSession(
        _world(1307), scheduler=_seat_scheduler("treasury"),
    )
    session.assign_seat(0, "treasury", _MustNotCopyOccupant(), log_event=False)
    assert session.advance().status == "advanced"


def test_identical_transport_retry_after_partial_collection_is_idempotent():
    due = ("debt_management", "fiscal_stance", "tax_and_transfers")
    scheduler = _seat_scheduler("treasury", due_groups=due)
    session = ControlledSimulationSession(_world(1308), scheduler=scheduler)
    occupant = HumanQueueOccupant()
    session.assign_seat(0, "treasury", occupant)
    opened = session.advance()
    assert len(opened.missing_context_ids) == 3
    context = opened.contexts[0]
    proposal = _noop_proposal(context, "partial-retry")
    session.submit_human_proposal(proposal, actor="alice")

    waiting = session.advance()
    assert waiting.status == AWAITING_HUMAN
    assert context.context_id not in waiting.missing_context_ids
    collected_before = dict(session._collected)
    occupant_before = pickle.dumps(occupant, protocol=5)
    events_before = session.events.canonical_bytes()

    session.submit_human_proposal(proposal, actor="alice")

    assert session._collected == collected_before
    assert pickle.dumps(occupant, protocol=5) == occupant_before
    assert session.events.canonical_bytes() == events_before
