"""Picklable seat occupants; none can mutate an engine directly."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import hashlib
import math
import random
from typing import Any, Callable, Mapping, Protocol

from .protocol import (
    DecisionContext,
    PolicyAction,
    PolicyProposal,
    canonical_json,
    immutable_json_mapping,
)


class Occupant(Protocol):
    def propose(self, context: DecisionContext) -> PolicyProposal | None: ...


def _proposal(context: DecisionContext, suffix: str, actions=(), reason="") -> PolicyProposal:
    proposal_id = f"proposal:{context.context_id}:{suffix}"
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=tuple(actions),
        reason=reason,
        based_on_policy_versions=dict(context.policy_versions),
    )


@dataclass
class NullOccupant:
    """Explicit no-action baseline."""

    def propose(self, context: DecisionContext) -> PolicyProposal:
        return _proposal(context, "noop", reason="no_action")


@dataclass(frozen=True)
class _FrozenSchedule(Mapping[int, tuple[PolicyAction, ...]]):
    _items: tuple[tuple[int, tuple[PolicyAction, ...]], ...]

    def __init__(self, schedule: Mapping[int, tuple[PolicyAction, ...]]):
        if not isinstance(schedule, Mapping):
            raise TypeError("ScheduledOccupant.schedule must be a mapping")
        normalized: list[tuple[int, tuple[PolicyAction, ...]]] = []
        for tick, raw_actions in schedule.items():
            if isinstance(tick, bool) or not isinstance(tick, int):
                raise TypeError("scheduled ticks must be strict integers")
            if tick < 0:
                raise ValueError("scheduled ticks must be non-negative")
            actions = tuple(raw_actions)
            if not all(isinstance(action, PolicyAction) for action in actions):
                raise TypeError("scheduled actions must contain PolicyAction values")
            normalized.append((tick, actions))
        normalized.sort(key=lambda item: item[0])
        object.__setattr__(self, "_items", tuple(normalized))

    def __getitem__(self, key: int) -> tuple[PolicyAction, ...]:
        for tick, actions in self._items:
            if tick == key:
                return actions
        raise KeyError(key)

    def __iter__(self) -> Iterator[int]:
        return (tick for tick, _actions in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __reduce__(self):
        return (type(self), (dict(self._items),))


@dataclass(frozen=True)
class ScheduledOccupant:
    schedule: Mapping[int, tuple[PolicyAction, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schedule", _FrozenSchedule(self.schedule))

    def propose(self, context: DecisionContext) -> PolicyProposal:
        actions = tuple(self.schedule.get(context.boundary_tick, ()))
        return _proposal(context, f"scheduled:{context.boundary_tick}", actions, "scheduled")


_HEURISTIC_RULES = frozenset({"hold", "inflation_targeting"})


@dataclass(frozen=True)
class HeuristicOccupant:
    """A serializable named-rule occupant.

    Built-ins deliberately stay small.  A checkpoint may preserve a pickle-safe
    custom top-level ``rule`` callable, but P0 canonical seat-assignment events and
    input replay support only the built-in named-rule specification.
    """

    rule_name: str = "hold"
    parameters: Mapping[str, float] = field(default_factory=dict)
    rule: Callable[[DecisionContext], tuple[PolicyAction, ...]] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rule_name, str) or self.rule_name not in _HEURISTIC_RULES:
            raise ValueError(f"unknown heuristic rule: {self.rule_name!r}")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("heuristic parameters must be a mapping")
        normalized: dict[str, float] = {}
        for name, value in self.parameters.items():
            if not isinstance(name, str) or not name:
                raise ValueError("heuristic parameter names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError("heuristic parameters must be finite numbers")
            normalized[name] = float(value)
        if self.rule is not None and not callable(self.rule):
            raise TypeError("custom heuristic rule must be callable")
        object.__setattr__(
            self, "parameters", immutable_json_mapping(normalized)
        )

    def propose(self, context: DecisionContext) -> PolicyProposal:
        if self.rule is not None:
            actions = tuple(self.rule(context))
        elif self.rule_name == "hold":
            actions = ()
        elif self.rule_name == "inflation_targeting":
            if hasattr(context.observation, "values") and not isinstance(context.observation, dict):
                values = context.observation.values()
            else:
                obs = context.observation.to_dict() if hasattr(context.observation, "to_dict") \
                    else context.observation
                values = obs.get("values", obs) if isinstance(obs, dict) else {}
            inflation = values.get("inflation")
            target = self.parameters.get("target", 0.0)
            gain = self.parameters.get("gain", 0.0001)
            permitted = {item.lever: item for item in context.permitted_actions}
            rate = permitted.get("manual_policy_rate")
            if inflation is None or rate is None or not rate.allowed or rate.current_value is None:
                actions = ()
            else:
                value = float(rate.current_value) + gain * (float(inflation) - target)
                if rate.minimum is not None:
                    value = max(float(rate.minimum), value)
                if rate.maximum is not None:
                    value = min(float(rate.maximum), value)
                actions = (PolicyAction("manual_policy_rate", value),)
        else:
            raise ValueError(f"unknown heuristic rule: {self.rule_name}")
        return _proposal(context, f"heuristic:{self.rule_name}", actions, self.rule_name)


@dataclass(frozen=True)
class RandomFuzzOccupant:
    seed: int
    action_probability: float = 0.25
    max_actions: int = 2
    _rng: random.Random = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("random fuzz seed must be a strict integer")
        probability = self.action_probability
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) \
                or not math.isfinite(float(probability)):
            raise ValueError("action_probability must be a finite number")
        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError("action_probability must be between zero and one")
        if isinstance(self.max_actions, bool) or not isinstance(self.max_actions, int):
            raise TypeError("max_actions must be a strict integer")
        if self.max_actions < 0:
            raise ValueError("max_actions must be non-negative")
        object.__setattr__(self, "action_probability", float(probability))
        object.__setattr__(self, "_rng", random.Random(self.seed))

    def propose(self, context: DecisionContext) -> PolicyProposal:
        candidates = [item for item in context.permitted_actions if item.allowed]
        candidates.sort(key=lambda item: item.lever)
        self._rng.shuffle(candidates)
        actions: list[PolicyAction] = []
        for item in candidates:
            if len(actions) >= self.max_actions or self._rng.random() > self.action_probability:
                continue
            value = self._draw(item)
            if value != item.current_value:
                actions.append(PolicyAction(item.lever, value))
        return _proposal(context, f"fuzz:{context.boundary_tick}", actions, "random_fuzz")

    def _draw(self, item):
        if item.value_kind == "bool":
            return not bool(item.current_value)
        if item.value_kind == "economy_set":
            current = set(item.current_value or ())
            available = [value for value in item.choices if value not in current]
            if current and (not available or self._rng.random() < 0.5):
                current.remove(self._rng.choice(sorted(current)))
            elif available:
                current.add(self._rng.choice(available))
            return sorted(current)
        if item.choices:
            choices = [choice for choice in item.choices if choice != item.current_value]
            return self._rng.choice(choices or list(item.choices))
        if item.nullable and self._rng.random() < 0.10:
            return None
        if item.value_kind in {"number", "integer"}:
            step = item.control_scale or item.max_step or 1.0
            direction = self._rng.choice((-1.0, 1.0))
            value = float(item.current_value or 0.0) + direction * step
            if item.minimum is not None:
                value = max(float(item.minimum), value)
            if item.maximum is not None:
                value = min(float(item.maximum), value)
            return int(round(value)) if item.value_kind == "integer" else value
        return item.current_value


@dataclass
class HumanQueueOccupant:
    """A checkpoint-safe mailbox.  Transport concurrency remains outside the model."""

    pending: dict[str, PolicyProposal] = field(default_factory=dict)
    actors: dict[str, str] = field(default_factory=dict)
    payload_hashes: dict[str, str] = field(default_factory=dict)
    idempotency_payload_hashes: dict[str, str] = field(default_factory=dict)
    idempotency_actors: dict[str, str] = field(default_factory=dict)
    _delivered_actors: dict[str, str] = field(default_factory=dict)

    def submit(self, proposal: PolicyProposal, *, actor: str = "human") -> bool:
        """Queue a new proposal, returning ``False`` for an exact retry."""
        payload_hash = hashlib.sha256(
            canonical_json(proposal.to_dict()).encode("utf-8")
        ).hexdigest()
        known_hash = self.idempotency_payload_hashes.get(proposal.idempotency_key)
        if known_hash is not None:
            if known_hash != payload_hash:
                raise ValueError(
                    "idempotency key was reused with a different proposal payload"
                )
            if self.idempotency_actors.get(proposal.idempotency_key) != actor:
                raise ValueError("idempotency key was reused by a different actor")
            return False
        existing = self.pending.get(proposal.context_id)
        if existing is not None:
            raise ValueError("a human context already has a different queued proposal")
        self.pending[proposal.context_id] = proposal
        self.actors[proposal.context_id] = actor
        self.payload_hashes[proposal.context_id] = payload_hash
        self.idempotency_payload_hashes[proposal.idempotency_key] = payload_hash
        self.idempotency_actors[proposal.idempotency_key] = actor
        return True

    def accept_idempotent_retry(
        self, proposal: PolicyProposal, *, actor: str = "human",
    ) -> bool:
        """Validate an already-seen transport retry without re-queuing it."""
        if proposal.idempotency_key not in self.idempotency_payload_hashes:
            return False
        self.submit(proposal, actor=actor)
        return True

    def propose(self, context: DecisionContext) -> PolicyProposal | None:
        proposal = self.pending.get(context.context_id)
        if proposal is not None:
            expected_hash = self.payload_hashes.get(context.context_id)
            actual_hash = hashlib.sha256(
                canonical_json(proposal.to_dict()).encode("utf-8")
            ).hexdigest()
            if expected_hash != actual_hash:
                raise RuntimeError("queued human proposal payload changed after submission")
            self.pending.pop(context.context_id)
            self._delivered_actors[context.context_id] = self.actors.pop(
                context.context_id, "human"
            )
            self.payload_hashes.pop(context.context_id, None)
        return proposal

    def take_actor(self, context_id: str) -> str:
        return self._delivered_actors.pop(context_id, "human")


@dataclass
class RLOccupant:
    """An application-supplied RL policy.

    The policy object itself belongs to the live/checkpointed session and is not
    embedded in the canonical event stream.  Input replay reconstructs an inert
    ``RLOccupant`` and feeds it the source run's recorded proposals.  This keeps
    seat-assignment events JSON-safe without deserializing arbitrary model bytes.
    """

    policy: Any | None = None
    _replay_queue: HumanQueueOccupant = field(
        default_factory=HumanQueueOccupant, init=False, repr=False,
    )
    _recorded_seed_context_ids: set[str] = field(
        default_factory=set, init=False, repr=False,
    )

    def propose(self, context: DecisionContext) -> PolicyProposal | None:
        if self.policy is None:
            # Replay placeholder: replay_input_events supplies the canonical
            # proposal recorded by the source occupant for this context.
            return self._replay_queue.propose(context)
        actions = tuple(self.policy(context))
        return _proposal(context, f"rl:{context.boundary_tick}", actions, "rl")

    def submit(self, proposal: PolicyProposal, *, actor: str) -> bool:
        if self.policy is not None:
            raise ValueError("live RL occupants do not accept queued proposals")
        return self._replay_queue.submit(proposal, actor=actor)

    def seed_recorded_proposal(
        self, proposal: PolicyProposal, *, actor: str,
    ) -> bool:
        """Seed an event-replay proposal and authorize pre-open consumption.

        This is deliberately distinct from :meth:`submit`: arbitrary direct
        mailbox preloads remain unsupported because they have no canonical event
        position inside boundary opening.
        """
        if self.policy is not None:
            raise ValueError("live RL occupants do not accept recorded replay seeds")
        inserted = self._replay_queue.submit(proposal, actor=actor)
        if inserted:
            self._recorded_seed_context_ids.add(proposal.context_id)
        elif proposal.context_id not in self._recorded_seed_context_ids:
            raise ValueError("recorded RL retry has no seed authorization")
        return inserted

    def consume_recorded_seed(self, context_id: str) -> bool:
        if context_id not in self._recorded_seed_context_ids:
            return False
        self._recorded_seed_context_ids.remove(context_id)
        return True

    def accept_idempotent_retry(
        self, proposal: PolicyProposal, *, actor: str,
    ) -> bool:
        if self.policy is not None:
            return False
        return self._replay_queue.accept_idempotent_retry(
            proposal, actor=actor,
        )

    def take_actor(self, context_id: str) -> str:
        return self._replay_queue.take_actor(context_id)

    @property
    def pending(self) -> Mapping[str, PolicyProposal]:
        return self._replay_queue.pending


def occupant_spec(occupant: Any) -> dict[str, Any]:
    """Canonical construction spec for built-in, replayable occupants."""
    # Subclasses may carry additional constructor or continuation state that the
    # built-in specs cannot represent.  Treat only the exact built-in classes as
    # canonical; applications can still install custom occupants with event
    # logging disabled and provide their own trusted replay genesis.
    if type(occupant) is NullOccupant:
        return {"type": "null"}
    if type(occupant) is HumanQueueOccupant:
        return {"type": "human_queue"}
    if type(occupant) is RandomFuzzOccupant:
        return {
            "type": "random_fuzz",
            "seed": occupant.seed,
            "action_probability": occupant.action_probability,
            "max_actions": occupant.max_actions,
        }
    if type(occupant) is HeuristicOccupant and occupant.rule is None:
        return {
            "type": "heuristic",
            "rule_name": occupant.rule_name,
            "parameters": dict(occupant.parameters),
        }
    if type(occupant) is ScheduledOccupant:
        return {
            "type": "scheduled",
            "schedule": {
                str(tick): [action.to_dict() for action in actions]
                for tick, actions in sorted(occupant.schedule.items())
            },
        }
    if type(occupant) is RLOccupant:
        return {"type": "rl", "replay_mode": "recorded_proposals"}
    raise TypeError(
        f"occupant {type(occupant).__name__} needs an application-level replay factory"
    )


def _queue_is_pristine(queue: HumanQueueOccupant) -> bool:
    return not any((
        queue.pending,
        queue.actors,
        queue.payload_hashes,
        queue.idempotency_payload_hashes,
        queue.idempotency_actors,
        queue._delivered_actors,
    ))


def occupant_is_canonical_fresh(occupant: Any) -> bool:
    """Whether a replayable occupant matches its canonical construction state."""
    spec = occupant_spec(occupant)
    reconstructed = occupant_from_spec(spec)
    if canonical_json(occupant_spec(reconstructed)) != canonical_json(spec):
        return False
    if isinstance(occupant, RandomFuzzOccupant):
        return occupant._rng.getstate() == reconstructed._rng.getstate()
    if isinstance(occupant, HumanQueueOccupant):
        return _queue_is_pristine(occupant)
    if isinstance(occupant, RLOccupant):
        return (
            _queue_is_pristine(occupant._replay_queue)
            and not occupant._recorded_seed_context_ids
        )
    return True


def _spec_tick(raw_tick: Any) -> int:
    if not isinstance(raw_tick, str):
        raise TypeError("scheduled spec ticks must be canonical strings")
    try:
        tick = int(raw_tick)
    except ValueError as exc:
        raise ValueError("scheduled spec tick is not an integer") from exc
    if raw_tick != str(tick):
        raise ValueError("scheduled spec tick is not canonical")
    if tick < 0:
        raise ValueError("scheduled spec ticks must be non-negative")
    return tick


def _require_spec_keys(
    spec: Mapping[str, Any], expected: set[str],
) -> None:
    if not isinstance(spec, Mapping):
        raise TypeError("occupant spec must be a mapping")
    actual = set(spec)
    if actual != expected:
        raise ValueError(
            f"occupant spec keys must be exactly {sorted(expected)}"
        )


def occupant_from_spec(spec: Mapping[str, Any]) -> Any:
    if not isinstance(spec, Mapping):
        raise TypeError("occupant spec must be a mapping")
    kind = spec.get("type")
    if kind == "null":
        _require_spec_keys(spec, {"type"})
        return NullOccupant()
    if kind == "human_queue":
        _require_spec_keys(spec, {"type"})
        return HumanQueueOccupant()
    if kind == "random_fuzz":
        _require_spec_keys(
            spec,
            {"type", "seed", "action_probability", "max_actions"},
        )
        return RandomFuzzOccupant(
            seed=spec["seed"],
            action_probability=spec["action_probability"],
            max_actions=spec["max_actions"],
        )
    if kind == "heuristic":
        _require_spec_keys(spec, {"type", "rule_name", "parameters"})
        return HeuristicOccupant(
            rule_name=spec["rule_name"],
            parameters=spec["parameters"],
        )
    if kind == "scheduled":
        _require_spec_keys(spec, {"type", "schedule"})
        raw_schedule = spec["schedule"]
        if not isinstance(raw_schedule, Mapping):
            raise TypeError("scheduled occupant spec schedule must be a mapping")
        schedule: dict[int, tuple[PolicyAction, ...]] = {}
        for raw_tick, raw_actions in raw_schedule.items():
            tick = _spec_tick(raw_tick)
            if tick in schedule:
                raise ValueError("scheduled spec contains canonical tick collision")
            if not isinstance(raw_actions, list):
                raise TypeError("scheduled spec actions must be an array")
            actions: list[PolicyAction] = []
            for action in raw_actions:
                if not isinstance(action, Mapping):
                    raise TypeError("scheduled spec action must be a mapping")
                _require_spec_keys(action, {"lever", "value"})
                lever = action["lever"]
                if not isinstance(lever, str) or not lever:
                    raise ValueError("scheduled spec action lever must be non-empty")
                actions.append(PolicyAction(lever, action["value"]))
            schedule[tick] = tuple(actions)
        return ScheduledOccupant(schedule)
    if kind == "rl":
        _require_spec_keys(spec, {"type", "replay_mode"})
        if spec["replay_mode"] != "recorded_proposals":
            raise ValueError("unknown RL occupant replay mode")
        return RLOccupant()
    raise ValueError(f"unknown occupant spec type: {kind!r}")
