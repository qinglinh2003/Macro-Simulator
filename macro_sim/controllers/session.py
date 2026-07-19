"""Checkpointable orchestration root for controller-enabled simulations."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import types
from typing import Any, Callable, Mapping

from macro_sim.core.policy_registry import REGISTRY

from .coordinator import SEATS, PolicyCoordinator, policy_key
from .costs import AdjustmentCostSpec
from .events import EventStream
from .occupants import (
    HumanQueueOccupant,
    RLOccupant,
    occupant_is_canonical_fresh,
    occupant_spec,
)
from .protocol import DecisionContext, PolicyDecision, PolicyProposal
from .scheduler import DecisionScheduler
from .transaction import world_policy_fingerprint


BOUNDARY_START = "boundary_start"
AWAITING_HUMAN = "awaiting_human"
READY_TO_COMMIT = "ready_to_commit"


def _restore_object_state(target: Any, snapshot: Any) -> None:
    """Restore a deep-copied object's state without changing its identity."""
    if type(target) is not type(snapshot):
        raise TypeError("cannot restore state from a different object type")
    memo = {id(snapshot): target}
    if hasattr(target, "__dict__"):
        restored = copy.deepcopy(snapshot.__dict__, memo)
        target.__dict__.clear()
        target.__dict__.update(restored)
    for cls in type(target).__mro__:
        for name, descriptor in cls.__dict__.items():
            if not isinstance(descriptor, types.MemberDescriptorType):
                continue
            if hasattr(snapshot, name):
                setattr(target, name, copy.deepcopy(getattr(snapshot, name), memo))
            elif hasattr(target, name):
                delattr(target, name)


@dataclass(frozen=True)
class _ReleaseServiceSnapshot:
    service: Any
    history_lengths: dict[Any, int] | None = None
    next_period_index: dict[Any, int] | None = None
    last_boundary: dict[Any, int] | None = None
    full_copy: Any = None


@dataclass(frozen=True)
class _BoundarySnapshot:
    phase: str
    current_context_ids: tuple[str, ...]
    missing_context_ids: tuple[str, ...]
    collected: dict[str, tuple[PolicyProposal, str, str]]
    opened_contexts: dict[str, DecisionContext]
    recorded_human_context_ids: set[str]
    release_service: _ReleaseServiceSnapshot
    trigger_states: dict[Any, Any]
    last_context_tick: dict[tuple[int, str, str], int]
    coordinator_context_count: int
    admin_remaining: dict[tuple[int, str, str], float]
    admin_reserved: dict[tuple[int, str, str], float]
    admin_replenished_at: dict[tuple[int, str, str], int]
    event_count: int
    event_head_hash: str


@dataclass(frozen=True)
class BoundaryResult:
    status: str
    boundary_tick: int
    contexts: tuple[DecisionContext, ...] = ()
    missing_context_ids: tuple[str, ...] = ()
    decisions: tuple[PolicyDecision, ...] = ()
    records: Any = None


def _final_decisions(
    decisions: list[PolicyDecision],
    lifecycle: Mapping[str, PolicyDecision] | None = None,
) -> tuple[PolicyDecision, ...]:
    """Keep one result per decision, using its latest lifecycle state.

    A zero-lag proposal is both accepted and made effective at the same boundary.
    Returning both snapshots makes adapters charge its adjustment cost twice.  The
    first-seen order is stable, while a later snapshot replaces the earlier one.
    The Coordinator's lifecycle table is the final authority when a later proposal
    superseded an earlier decision without returning a second snapshot here.
    """
    order: list[str] = []
    latest: dict[str, PolicyDecision] = {}
    for decision in decisions:
        if decision.decision_id not in latest:
            order.append(decision.decision_id)
        latest[decision.decision_id] = decision
    lifecycle = lifecycle or {}
    return tuple(
        lifecycle.get(decision_id, latest[decision_id])
        for decision_id in order
    )


def _economies(world: Any) -> list[Any]:
    return list(getattr(world, "economies", [world]))


def _is_queued_occupant(occupant: Any) -> bool:
    return isinstance(occupant, HumanQueueOccupant) or (
        isinstance(occupant, RLOccupant) and occupant.policy is None
    )


@dataclass
class ControlledSimulationSession:
    """The only orchestration root that may advance a controlled engine.

    ``world`` may be a World or a legacy bare Economy, although new controlled
    runs should use ``World([cfg])`` even for one economy.  The object contains no
    locks, async queues, wall clocks, or callbacks and is therefore pickle-safe.
    """

    world: Any
    scheduler: DecisionScheduler = field(default_factory=DecisionScheduler)
    events: EventStream = field(default_factory=EventStream)
    cost_spec: AdjustmentCostSpec = field(default_factory=AdjustmentCostSpec)
    release_service: Any = None
    seat_assignments: dict[tuple[int, str], Any] = field(default_factory=dict)
    run_mode: str = "batch"  # interactive | realtime | batch | replay
    phase: str = BOUNDARY_START
    boundary_tick: int = field(init=False)
    coordinator: PolicyCoordinator = field(init=False)
    policy_fingerprint: str = field(init=False)
    next_transaction_sequence: int = 0
    engine_log_cursors: dict[int, int] = field(default_factory=dict)
    shock_event_cursor: int = 0
    current_context_ids: tuple[str, ...] = ()
    missing_context_ids: tuple[str, ...] = ()
    _collected: dict[str, tuple[PolicyProposal, str, str]] = field(default_factory=dict)
    _opened_contexts: dict[str, DecisionContext] = field(default_factory=dict)
    _recorded_human_context_ids: set[str] = field(default_factory=set)
    assignment_archive: dict[str, Any] = field(default_factory=dict)
    next_assignment_sequence: int = 0

    def __post_init__(self) -> None:
        if self.run_mode not in {"interactive", "realtime", "batch", "replay"}:
            raise ValueError(f"unknown controller run mode: {self.run_mode}")
        if self.release_service is None:
            from .observation import DEFAULT_OBSERVATION_SPEC, ReleaseService
            self.release_service = ReleaseService(DEFAULT_OBSERVATION_SPEC)
        self.boundary_tick = int(getattr(self.world, "t", 0))
        economies = _economies(self.world)
        for index, econ in enumerate(economies):
            if int(getattr(econ, "t", self.boundary_tick)) != self.boundary_tick:
                raise ValueError(f"world/economy tick mismatch for economy {index}")
            self.engine_log_cursors.setdefault(
                index, len(getattr(econ, "_policy_action_log", ()))
            )
        from macro_sim.shocks import get_shock_engine

        shock_engine = get_shock_engine(self.world)
        if shock_engine is not None and self.shock_event_cursor == 0:
            self.shock_event_cursor = len(shock_engine.events.events)
        self.coordinator = PolicyCoordinator.create(
            self.world, self.scheduler, self.events, self.cost_spec
        )
        self.policy_fingerprint = world_policy_fingerprint(self.world)

    def assert_boundary_integrity(self, *, expected_tick: int | None = None) -> None:
        """Reject engine advancement that bypassed this orchestration root.

        ``World.t`` alone is insufficient: a caller can retain a child Economy
        reference and step it independently.  Every public decision/advance path
        calls this guard before changing controller state.
        """
        expected = self.boundary_tick if expected_tick is None else int(expected_tick)
        world_tick = int(getattr(self.world, "t", -1))
        if world_tick != expected:
            raise RuntimeError(
                "engine advanced outside ControlledSimulationSession "
                f"(world tick {world_tick}, expected {expected})"
            )
        for economy_id, econ in enumerate(_economies(self.world)):
            economy_tick = int(getattr(econ, "t", world_tick))
            if economy_tick != expected:
                raise RuntimeError(
                    "engine advanced outside ControlledSimulationSession "
                    f"(economy {economy_id} tick {economy_tick}, expected {expected})"
                )

    @property
    def policy_versions(self) -> dict[str, int]:
        return self.coordinator.policy_versions

    @property
    def last_effective_tick(self) -> dict[str, int]:
        return self.coordinator.last_effective_tick

    @property
    def pending(self):
        return self.coordinator.pending

    def assign_seat(
        self,
        economy_id: int,
        seat: str,
        occupant: Any,
        *,
        actor: str = "system",
        initialization: str = "fresh",
        log_event: bool = True,
    ) -> None:
        self.assert_boundary_integrity()
        if self.phase != BOUNDARY_START:
            raise RuntimeError(
                "seat assignments are accepted only at a clean boundary; "
                "an already-open decision window keeps its original occupant"
            )
        if isinstance(economy_id, bool) or not isinstance(economy_id, int):
            raise TypeError("seat assignment economy_id must be an integer")
        if not 0 <= economy_id < len(_economies(self.world)):
            raise ValueError("seat assignment economy is out of range")
        if not isinstance(seat, str) or seat not in SEATS:
            raise ValueError(f"unknown policy seat: {seat!r}")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("seat assignment actor must be a non-empty string")
        if not isinstance(initialization, str) or not initialization.strip():
            raise ValueError(
                "seat assignment initialization must be a non-empty string"
            )
        if initialization != "fresh" and not initialization.startswith("restore:"):
            raise ValueError(
                "seat assignment initialization must be 'fresh' or 'restore:<id>'"
            )
        if isinstance(occupant, type) or not callable(getattr(occupant, "propose", None)):
            raise TypeError("seat occupant must implement callable propose(context)")
        if not isinstance(log_event, bool):
            raise TypeError("log_event must be a boolean")

        if initialization.startswith("restore:"):
            archived_id = initialization.split(":", 1)[1]
            if not archived_id or archived_id not in self.assignment_archive:
                raise ValueError(
                    "restore initialization must reference an archived occupant"
                )
            if occupant is not self.assignment_archive[archived_id]:
                raise ValueError(
                    "restored occupant must be the referenced archive object"
                )

        active_elsewhere = any(
            assigned is occupant for assigned in self.seat_assignments.values()
        )
        archived_anywhere = any(
            archived is occupant for archived in self.assignment_archive.values()
        )
        if initialization == "fresh":
            if active_elsewhere or archived_anywhere:
                raise ValueError(
                    "fresh occupant must not already be active or archived; "
                    "use restore or an application genesis factory"
                )
            try:
                canonical_fresh = occupant_is_canonical_fresh(occupant)
            except TypeError:
                canonical_fresh = None
            if canonical_fresh is False:
                raise ValueError(
                    "fresh occupant is not in its canonical initial state; "
                    "use restore or an application genesis factory"
                )
        elif active_elsewhere:
            raise ValueError(
                "restored occupant cannot already be active in another seat"
            )

        # Everything above, occupant_spec(), and EventStream.append() may reject
        # application input.  Complete all of them before changing assignment,
        # archive, or sequence state.
        replay_spec = occupant_spec(occupant) if log_event else None
        key = (economy_id, seat)
        old = self.seat_assignments.get(key)
        assignment_id = f"assignment:{self.next_assignment_sequence:012d}"
        archived_outgoing_id = (
            f"occupant:{assignment_id}" if old is not None else None
        )
        if log_event:
            self.events.append(
                "seat_assignment", "input", self.boundary_tick, self.phase,
                economy_id=economy_id, seat=seat, actor=actor,
                payload={
                    "assignment_id": assignment_id,
                    "archived_outgoing_id": archived_outgoing_id,
                    "old_occupant": type(old).__name__ if old is not None else None,
                    "new_occupant": type(occupant).__name__,
                    "occupant_spec": replay_spec,
                    "initialization": initialization,
                },
            )
        if archived_outgoing_id is not None:
            self.assignment_archive[archived_outgoing_id] = old
        self.seat_assignments[key] = occupant
        self.next_assignment_sequence += 1

    def restore_seat(
        self,
        economy_id: int,
        seat: str,
        archived_occupant_id: str,
        *,
        actor: str = "system",
    ) -> None:
        if archived_occupant_id not in self.assignment_archive:
            raise KeyError(archived_occupant_id)
        self.assign_seat(
            economy_id,
            seat,
            self.assignment_archive[archived_occupant_id],
            actor=actor,
            initialization=f"restore:{archived_occupant_id}",
        )

    def submit_human_proposal(self, proposal: PolicyProposal, *, actor: str = "human") -> None:
        self.assert_boundary_integrity()
        if not isinstance(proposal, PolicyProposal):
            raise TypeError("proposal must be a PolicyProposal")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        context = self._opened_contexts.get(proposal.context_id)
        if context is None:
            # Let the Coordinator produce a canonical unknown-context rejection.
            self.coordinator.submit(self, proposal, actor=actor)
            return
        occupant = self.seat_assignments.get((context.economy_id, context.seat))
        if self.phase != AWAITING_HUMAN \
                or proposal.context_id not in self.missing_context_ids:
            if isinstance(occupant, HumanQueueOccupant) \
                    and occupant.accept_idempotent_retry(
                proposal, actor=actor,
            ):
                return
            raise ValueError("context is not awaiting a human proposal")
        if not isinstance(occupant, HumanQueueOccupant):
            raise ValueError("context is not assigned to a human queue")
        occupant_snapshot = copy.deepcopy(occupant)
        recorded_before = set(self._recorded_human_context_ids)
        event_count = len(self.events.events)
        event_head_hash = self.events.head_hash
        try:
            inserted = occupant.submit(proposal, actor=actor)
            if not inserted:
                return
            self._append_human_queue_event(
                context, proposal, actor,
            )
            self._recorded_human_context_ids.add(context.context_id)
        except Exception:
            _restore_object_state(occupant, occupant_snapshot)
            self._recorded_human_context_ids = recorded_before
            del self.events.events[event_count:]
            self.events._head_hash = event_head_hash
            raise

    def timeout_context(self, context_id: str, *, actor: str = "server_timeout") -> None:
        self.assert_boundary_integrity()
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        context = self._opened_contexts.get(context_id)
        if context is None:
            raise KeyError(context_id)
        if self.phase != AWAITING_HUMAN or context_id not in self.missing_context_ids:
            raise ValueError("context is not awaiting a timeout decision")
        occupant = self.seat_assignments.get((context.economy_id, context.seat))
        if _is_queued_occupant(occupant) and context_id in occupant.pending:
            raise ValueError("context already has a queued human proposal")
        proposal_id = f"proposal:{context_id}:timeout"
        proposal = PolicyProposal(
            proposal_id=proposal_id,
            idempotency_key=proposal_id,
            context_id=context_id,
            actions=(),
            reason="timeout_no_action",
            based_on_policy_versions=dict(context.policy_versions),
        )
        before_collected = dict(self._collected)
        before_missing = self.missing_context_ids
        before_phase = self.phase
        event_count = len(self.events.events)
        event_head_hash = self.events.head_hash
        try:
            proposal_dict = proposal.to_dict()
            self.events.append(
                "timeout", "input", self.boundary_tick, self.phase,
                economy_id=context.economy_id, seat=context.seat, actor=actor,
                context_id=context_id, proposal_id=proposal.proposal_id,
                requested_actions=proposal_dict["actions"],
                payload={
                    "proposal": proposal_dict,
                    "actor": actor,
                    "context_id": context.context_id,
                },
            )
            self._collected[context_id] = (proposal, actor, "timeout")
            self.missing_context_ids = tuple(
                item for item in self.missing_context_ids if item != context_id
            )
            if not self.missing_context_ids:
                self.phase = READY_TO_COMMIT
        except Exception:
            self._collected = before_collected
            self.missing_context_ids = before_missing
            self.phase = before_phase
            del self.events.events[event_count:]
            self.events._head_hash = event_head_hash
            raise

    def cancel_pending(self, decision_id: str, *, actor: str = "human") -> PolicyDecision:
        self.assert_boundary_integrity()
        return self.coordinator.cancel(self, decision_id, actor=actor)

    def advance(
        self,
        *,
        engine_step: Callable[[Any], Any] | None = None,
    ) -> BoundaryResult:
        """Advance exactly one engine tick, or return an interactive pause."""
        self.assert_boundary_integrity()
        if self.phase == BOUNDARY_START:
            self._begin_boundary()
        if self.phase == AWAITING_HUMAN:
            self._collect_waiting_humans()
            if self.missing_context_ids:
                return BoundaryResult(
                    status=AWAITING_HUMAN,
                    boundary_tick=self.boundary_tick,
                    contexts=tuple(self._opened_contexts[key] for key in self.current_context_ids),
                    missing_context_ids=self.missing_context_ids,
                )
            self.phase = READY_TO_COMMIT

        decisions: list[PolicyDecision] = []
        for context_id in self.current_context_ids:
            proposal, actor, input_type = self._collected[context_id]
            input_already_recorded = input_type in {
                "automatic_recorded", "human_recorded", "timeout",
            }
            decisions.append(self.coordinator.submit(
                self,
                proposal,
                actor=actor,
                input_event_type=("timeout" if input_type == "timeout" else "proposal_submitted"),
                input_already_recorded=input_already_recorded,
                input_origin=(
                    "automatic"
                    if input_type == "automatic_recorded"
                    else "external"
                ),
            ))
        decisions.extend(self.coordinator.execute_due(self))

        completed_tick = self.boundary_tick
        if engine_step is None:
            records = self.world.step()
        else:
            records = engine_step(self.world)
        self.assert_boundary_integrity(expected_tick=completed_tick + 1)
        self._drain_engine_policy_events()
        self._drain_engine_shock_events()
        self.boundary_tick = int(getattr(self.world, "t", completed_tick + 1))
        self._publish_due_releases()
        self.policy_fingerprint = world_policy_fingerprint(self.world)
        self.phase = BOUNDARY_START
        contexts = tuple(self._opened_contexts[key] for key in self.current_context_ids)
        self.current_context_ids = ()
        self.missing_context_ids = ()
        self._collected.clear()
        self._opened_contexts.clear()
        self._recorded_human_context_ids.clear()
        return BoundaryResult(
            status="advanced",
            boundary_tick=completed_tick,
            contexts=contexts,
            decisions=_final_decisions(decisions, self.coordinator.decisions),
            records=records,
        )

    def run(self, n_ticks: int) -> list[Any]:
        if n_ticks < 0:
            raise ValueError("n_ticks must be non-negative")
        results: list[Any] = []
        target = self.boundary_tick + n_ticks
        while self.boundary_tick < target:
            result = self.advance()
            if result.status == AWAITING_HUMAN:
                raise RuntimeError(
                    f"run paused for human contexts {result.missing_context_ids}; "
                    "submit or timeout them before continuing"
                )
            results.append(result.records)
        return results

    def _begin_boundary(self) -> None:
        self.assert_boundary_integrity()
        if world_policy_fingerprint(self.world) != self.policy_fingerprint:
            raise RuntimeError("policy changed outside ControlledSimulationSession")
        boundary_snapshot = self._capture_boundary_snapshot()
        occupant_snapshots: list[tuple[Any, Any]] = []
        try:
            self._opened_contexts = {}
            self._collected = {}
            self._recorded_human_context_ids = set()

            # Releases are a property of the simulation boundary, not of whether a
            # controller happens to hold a seat or a meeting happens to be due.
            self._publish_due_releases()

            notices_by_economy: dict[int, list[Any]] = {}
            for economy_id, econ in enumerate(_economies(self.world)):
                metrics = (
                    dict(econ.records[-1]) if getattr(econ, "records", None) else {}
                )
                world_records = getattr(self.world, "world_records", None)
                if world_records:
                    for name, value in world_records[-1].items():
                        if isinstance(value, (list, tuple)) \
                                and economy_id < len(value):
                            metrics.setdefault(name, value[economy_id])
                        else:
                            metrics.setdefault(name, value)
                from macro_sim.shocks import get_shock_engine

                shock_engine = get_shock_engine(self.world)
                if shock_engine is not None:
                    metrics.update(shock_engine.trigger_metrics(
                        economy_id, self.boundary_tick, role="public",
                    ))
                notices_by_economy[economy_id] = self.scheduler.evaluate_triggers(
                    self.boundary_tick, economy_id, metrics
                )

            context_specs: list[tuple[int, str, str, bool, Any]] = []
            for (economy_id, seat), _occupant in sorted(
                self.seat_assignments.items()
            ):
                groups = sorted({
                    lever.decision_group for lever in REGISTRY.values()
                    if lever.owner_role == seat
                })
                for group in groups:
                    if self.scheduler.due(
                        group, self.boundary_tick, economy_id=economy_id,
                    ):
                        context_specs.append(
                            (economy_id, seat, group, False, None)
                        )
                for notice in notices_by_economy.get(economy_id, ()):
                    if seat in notice.seats:
                        context_specs.append((
                            economy_id, seat, notice.decision_group, True, notice,
                        ))

            # Regular windows deduplicate by group.  Emergency windows additionally
            # key on their server trigger so simultaneous crises remain auditable.
            seen: set[tuple[int, str, str, bool, str | None]] = set()
            elapsed_by_key: dict[tuple[int, str, str], int] = {}
            contexts: list[DecisionContext] = []
            for economy_id, seat, group, emergency, notice in sorted(
                context_specs,
                key=lambda item: (
                    item[0], item[1], item[2], item[3],
                    item[4].trigger_id if item[4] is not None else "",
                ),
            ):
                trigger_id = notice.trigger_id if emergency else None
                spec_key = (economy_id, seat, group, emergency, trigger_id)
                if spec_key in seen:
                    continue
                seen.add(spec_key)
                last_key = (economy_id, seat, group)
                if last_key not in elapsed_by_key:
                    previous = self.scheduler.last_context_tick.get(last_key)
                    elapsed_by_key[last_key] = (
                        0 if previous is None else self.boundary_tick - previous
                    )
                elapsed = elapsed_by_key[last_key]
                observation = self._observation(economy_id, seat, elapsed)
                expiry = (
                    notice.expires_at_tick if emergency
                    else self.boundary_tick
                    + self.scheduler.calendar_for(group).window_ticks - 1
                )
                context = self.coordinator.open_context(
                    self, economy_id, seat, group, observation,
                    expires_at_tick=expiry,
                    emergency=emergency,
                    emergency_trigger=trigger_id,
                    elapsed_ticks=elapsed,
                )
                self.scheduler.last_context_tick[last_key] = self.boundary_tick
                self._opened_contexts[context.context_id] = context
                contexts.append(context)
                self.events.append(
                    "decision_context_opened", "derived", self.boundary_tick,
                    self.phase, economy_id=economy_id, seat=seat,
                    actor="scheduler", context_id=context.context_id,
                    payload={
                        "decision_group": group,
                        "emergency": emergency,
                        "expires_at_tick": expiry,
                    },
                )
                if emergency:
                    self.events.append(
                        "emergency_trigger", "derived", self.boundary_tick,
                        self.phase, economy_id=economy_id, seat=seat,
                        actor="scheduler", context_id=context.context_id,
                        reason=trigger_id, payload={"value": notice.value},
                    )

            contexts.sort(key=lambda item: item.context_id)
            self.current_context_ids = tuple(
                item.context_id for item in contexts
            )
            # Occupants can contain large models.  Snapshot only occupants that
            # will actually be called at this boundary, and only once by identity.
            if contexts:
                occupant_snapshots = self._snapshot_context_occupants(contexts)
            missing: list[str] = []
            for context in contexts:
                occupant = self.seat_assignments[
                    (context.economy_id, context.seat)
                ]
                proposal = self._occupant_proposal(occupant, context)
                if proposal is None:
                    missing.append(context.context_id)
                else:
                    recorded_rl_seed = (
                        isinstance(occupant, RLOccupant)
                        and occupant.policy is None
                        and occupant.consume_recorded_seed(context.context_id)
                    )
                    if _is_queued_occupant(occupant) and not recorded_rl_seed:
                        # A mailbox filled before its context was opened cannot be
                        # represented at the same event position during input-only
                        # replay: the recorded input would sit halfway through this
                        # atomic boundary-opening operation. Public ingress is only
                        # accepted after ``advance()`` exposes an awaiting context.
                        raise ValueError(
                            "queued occupant proposal was submitted before its "
                            "context opened; submit it while the session is "
                            "awaiting_human"
                        )
                    proposal_actor = self._occupant_actor(occupant, context)
                    self._append_automatic_proposal_event(
                        context, proposal, proposal_actor,
                    )
                    input_type = "automatic_recorded"
                    self._collected[context.context_id] = (
                        proposal, proposal_actor, input_type
                    )
            self.missing_context_ids = tuple(missing)
            self.phase = AWAITING_HUMAN if missing else READY_TO_COMMIT
        except Exception:
            for occupant, occupant_snapshot in reversed(occupant_snapshots):
                _restore_object_state(occupant, occupant_snapshot)
            self._restore_boundary_snapshot(boundary_snapshot)
            raise

    def _collect_waiting_humans(self) -> None:
        before_collected = dict(self._collected)
        before_missing = self.missing_context_ids
        before_phase = self.phase
        recorded_before = set(self._recorded_human_context_ids)
        event_count = len(self.events.events)
        event_head_hash = self.events.head_hash
        contexts = [
            self._opened_contexts[context_id]
            for context_id in self.missing_context_ids
        ]
        occupant_snapshots = self._snapshot_context_occupants(contexts)
        try:
            still_missing: list[str] = []
            for context in contexts:
                context_id = context.context_id
                occupant = self.seat_assignments[
                    (context.economy_id, context.seat)
                ]
                proposal = self._occupant_proposal(occupant, context)
                if proposal is None:
                    still_missing.append(context_id)
                else:
                    actor = self._occupant_actor(occupant, context)
                    input_type = "automatic_recorded"
                    if isinstance(occupant, HumanQueueOccupant):
                        if context_id not in self._recorded_human_context_ids:
                            self._append_human_queue_event(
                                context, proposal, actor,
                            )
                            self._recorded_human_context_ids.add(context_id)
                        self._append_human_collection_event(
                            context, proposal, actor,
                        )
                        input_type = "human_recorded"
                    else:
                        if isinstance(occupant, RLOccupant) \
                                and occupant.policy is None \
                                and not occupant.consume_recorded_seed(
                                    context_id
                                ):
                            raise ValueError(
                                "inert RL proposals must be seeded by canonical "
                                "recorded-proposal replay"
                            )
                        self._append_automatic_proposal_event(
                            context, proposal, actor,
                        )
                    self._collected[context_id] = (
                        proposal, actor, input_type
                    )
            self.missing_context_ids = tuple(still_missing)
        except Exception:
            for occupant, occupant_snapshot in reversed(occupant_snapshots):
                _restore_object_state(occupant, occupant_snapshot)
            self._collected = before_collected
            self.missing_context_ids = before_missing
            self.phase = before_phase
            self._recorded_human_context_ids = recorded_before
            del self.events.events[event_count:]
            self.events._head_hash = event_head_hash
            raise

    def _append_human_queue_event(
        self,
        context: DecisionContext,
        proposal: PolicyProposal,
        actor: str,
    ) -> None:
        proposal_dict = proposal.to_dict()
        self.events.append(
            "human_proposal_queued", "input", self.boundary_tick,
            self.phase, economy_id=context.economy_id, seat=context.seat,
            actor=actor, context_id=context.context_id,
            proposal_id=proposal.proposal_id,
            requested_actions=proposal_dict["actions"],
            payload={
                "proposal": proposal_dict,
                "actor": actor,
                "context_id": context.context_id,
            },
        )

    def _append_automatic_proposal_event(
        self,
        context: DecisionContext,
        proposal: PolicyProposal,
        actor: str,
    ) -> None:
        proposal_dict = proposal.to_dict()
        self.events.append(
            "proposal_submitted", "input", self.boundary_tick,
            self.phase, economy_id=context.economy_id, seat=context.seat,
            actor=actor, context_id=context.context_id,
            proposal_id=proposal.proposal_id,
            requested_actions=proposal_dict["actions"],
            payload={
                "proposal": proposal_dict,
                "input_origin": "automatic",
            },
        )

    def _append_human_collection_event(
        self,
        context: DecisionContext,
        proposal: PolicyProposal,
        actor: str,
    ) -> None:
        proposal_dict = proposal.to_dict()
        self.events.append(
            "human_proposal_collected", "derived", self.boundary_tick,
            self.phase, economy_id=context.economy_id, seat=context.seat,
            actor=actor, context_id=context.context_id,
            proposal_id=proposal.proposal_id,
            requested_actions=proposal_dict["actions"],
            payload={
                "proposal_id": proposal.proposal_id,
                "context_id": context.context_id,
            },
        )

    def _capture_boundary_snapshot(self) -> _BoundarySnapshot:
        return _BoundarySnapshot(
            phase=self.phase,
            current_context_ids=self.current_context_ids,
            missing_context_ids=self.missing_context_ids,
            collected=dict(self._collected),
            opened_contexts=dict(self._opened_contexts),
            recorded_human_context_ids=set(self._recorded_human_context_ids),
            release_service=self._snapshot_release_service(),
            trigger_states=copy.deepcopy(self.scheduler.trigger_states),
            last_context_tick=dict(self.scheduler.last_context_tick),
            coordinator_context_count=len(self.coordinator.contexts),
            admin_remaining=dict(self.coordinator.admin_remaining),
            admin_reserved=dict(self.coordinator.admin_reserved),
            admin_replenished_at=dict(self.coordinator.admin_replenished_at),
            event_count=len(self.events.events),
            event_head_hash=self.events.head_hash,
        )

    def _restore_boundary_snapshot(self, snapshot: _BoundarySnapshot) -> None:
        self.phase = snapshot.phase
        self.current_context_ids = snapshot.current_context_ids
        self.missing_context_ids = snapshot.missing_context_ids
        self._collected = dict(snapshot.collected)
        self._opened_contexts = dict(snapshot.opened_contexts)
        self._recorded_human_context_ids = set(
            snapshot.recorded_human_context_ids
        )
        self._restore_release_service(snapshot.release_service)
        self.scheduler.trigger_states.clear()
        self.scheduler.trigger_states.update(copy.deepcopy(snapshot.trigger_states))
        self.scheduler.last_context_tick.clear()
        self.scheduler.last_context_tick.update(snapshot.last_context_tick)
        while len(self.coordinator.contexts) > snapshot.coordinator_context_count:
            self.coordinator.contexts.popitem()
        if len(self.coordinator.contexts) != snapshot.coordinator_context_count:
            raise RuntimeError("coordinator context state changed non-append-only")
        self.coordinator.admin_remaining.clear()
        self.coordinator.admin_remaining.update(snapshot.admin_remaining)
        self.coordinator.admin_reserved.clear()
        self.coordinator.admin_reserved.update(snapshot.admin_reserved)
        self.coordinator.admin_replenished_at.clear()
        self.coordinator.admin_replenished_at.update(
            snapshot.admin_replenished_at
        )
        del self.events.events[snapshot.event_count:]
        self.events._head_hash = snapshot.event_head_hash

    def _snapshot_release_service(self) -> _ReleaseServiceSnapshot:
        from .observation import ReleaseService

        service = self.release_service
        history = getattr(service, "_history", None)
        next_period = getattr(service, "_next_period_index", None)
        last_boundary = getattr(service, "_last_boundary", None)
        if type(service) is ReleaseService \
                and isinstance(history, dict) \
                and all(isinstance(value, list) for value in history.values()) \
                and isinstance(next_period, dict) \
                and isinstance(last_boundary, dict):
            # ReleaseService is append-only.  Length markers avoid copying its
            # complete, ever-growing publication history at every engine tick.
            return _ReleaseServiceSnapshot(
                service=service,
                history_lengths={key: len(value) for key, value in history.items()},
                next_period_index=dict(next_period),
                last_boundary=dict(last_boundary),
            )
        return _ReleaseServiceSnapshot(
            service=service,
            full_copy=copy.deepcopy(service),
        )

    def _restore_release_service(
        self, snapshot: _ReleaseServiceSnapshot,
    ) -> None:
        if snapshot.history_lengths is not None:
            self.release_service = snapshot.service
            history = self.release_service._history
            for key in tuple(history):
                if key not in snapshot.history_lengths:
                    del history[key]
                else:
                    del history[key][snapshot.history_lengths[key]:]
            self.release_service._next_period_index.clear()
            self.release_service._next_period_index.update(
                snapshot.next_period_index or {}
            )
            self.release_service._last_boundary.clear()
            self.release_service._last_boundary.update(
                snapshot.last_boundary or {}
            )
            return
        if self.release_service is None or type(self.release_service) is not type(
            snapshot.full_copy
        ):
            self.release_service = copy.deepcopy(snapshot.full_copy)
        else:
            _restore_object_state(self.release_service, snapshot.full_copy)

    def _snapshot_context_occupants(
        self, contexts: list[DecisionContext],
    ) -> list[tuple[Any, Any]]:
        snapshots: list[tuple[Any, Any]] = []
        seen: set[int] = set()
        for context in contexts:
            occupant = self.seat_assignments[(context.economy_id, context.seat)]
            identity = id(occupant)
            if identity in seen:
                continue
            seen.add(identity)
            snapshots.append((occupant, copy.deepcopy(occupant)))
        return snapshots

    @staticmethod
    def _occupant_proposal(
        occupant: Any, context: DecisionContext,
    ) -> PolicyProposal | None:
        proposal = occupant.propose(context)
        if proposal is None:
            return None
        if not isinstance(proposal, PolicyProposal):
            raise TypeError(
                "occupant.propose() must return PolicyProposal or None"
            )
        if proposal.context_id != context.context_id:
            raise ValueError(
                "occupant proposal context_id does not match its DecisionContext"
            )
        return proposal

    @staticmethod
    def _occupant_actor(occupant: Any, context: DecisionContext) -> str:
        actor = (
            occupant.take_actor(context.context_id)
            if _is_queued_occupant(occupant)
            else type(occupant).__name__
        )
        if not isinstance(actor, str) or not actor.strip():
            raise TypeError("occupant actor must be a non-empty string")
        return actor

    def _observation(self, economy_id: int, seat: str, elapsed_ticks: int) -> Any:
        if self.release_service is not None:
            return self.release_service.observe(
                self.world,
                self.boundary_tick,
                economy_id=economy_id,
                role=seat,
                elapsed_ticks=elapsed_ticks,
            )
        econ = _economies(self.world)[economy_id]
        return {
            "boundary_tick": self.boundary_tick,
            "values": dict(econ.records[-1]) if getattr(econ, "records", None) else {},
            "missing": {} if getattr(econ, "records", None) else {"records": "warmup"},
        }

    def _publish_due_releases(self) -> None:
        publish_due = getattr(self.release_service, "publish_due", None)
        if callable(publish_due):
            for economy_id in range(len(_economies(self.world))):
                publish_due(
                    self.world, self.boundary_tick, economy_id=economy_id,
                )

    def _drain_engine_policy_events(self) -> None:
        for economy_id, econ in enumerate(_economies(self.world)):
            log = getattr(econ, "_policy_action_log", ())
            cursor = self.engine_log_cursors.get(economy_id, 0)
            for legacy in log[cursor:]:
                actor = legacy.get("actor", "engine")
                if not str(actor).startswith("world:"):
                    raise RuntimeError(
                        "uncoordinated discretionary policy event appeared during engine tick"
                    )
                versions_before: dict[str, int] = {}
                versions_after: dict[str, int] = {}
                for change in legacy.get("actions", ()):
                    key = policy_key(economy_id, change["lever"])
                    old_version = self.policy_versions.get(key, 0)
                    versions_before[key] = old_version
                    versions_after[key] = old_version + 1
                    self.policy_versions[key] = old_version + 1
                    self.last_effective_tick[key] = self.boundary_tick
                self.events.append(
                    "forced_system_transition", "derived", self.boundary_tick,
                    "engine_tick", economy_id=economy_id, actor=actor,
                    effective_changes=legacy.get("actions", ()),
                    policy_versions_before=versions_before,
                    policy_versions_after=versions_after,
                    payload={"legacy_sequence": legacy.get("sequence")},
                )
            self.engine_log_cursors[economy_id] = len(log)

    def _drain_engine_shock_events(self) -> None:
        """Mirror deterministic shock transitions into the controller replay stream."""
        from macro_sim.shocks import get_shock_engine

        shock_engine = get_shock_engine(self.world)
        if shock_engine is None:
            return
        log = shock_engine.events.events
        specs = {item.shock_id: item for item in shock_engine.specs}
        for item in log[self.shock_event_cursor:]:
            # The global Controller stream is consumed by generic frontend/Gym
            # plumbing and has no seat-scoped authorization.  Role-restricted
            # details travel only through role-filtered observations/bulletins;
            # the internal ShockEngine chain still records every transition.
            if specs[item["shock_id"]].visibility != "public":
                continue
            ids = item.get("economy_ids")
            economy_id = ids[0] if isinstance(ids, list) and len(ids) == 1 else None
            self.events.append(
                f"shock_{item['event_type']}", "derived", int(item["tick"]),
                "engine_tick", economy_id=economy_id, actor="shock_engine",
                payload={"shock_event": item},
            )
        self.shock_event_cursor = len(log)

    def validate_checkpoint_phase(self) -> None:
        if self.phase not in {BOUNDARY_START, AWAITING_HUMAN, READY_TO_COMMIT}:
            raise ValueError(f"session cannot be checkpointed in transient phase {self.phase}")
        self.events.verify()
