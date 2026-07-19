"""JSON-safe protocol objects shared by frontend, humans, heuristics and RL."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
import json
import math
from typing import Any


CONTROLLER_SCHEMA_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 1


def canonical_value(value: Any) -> Any:
    """Return a strict, deterministically ordered JSON value.

    Python sets are wire arrays, dictionary keys are strings, and non-finite numbers
    are rejected.  The protocol never falls back to ``repr`` because that would make
    event hashes runtime-dependent.
    """
    if is_dataclass(value):
        value = asdict(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("controller protocol forbids NaN and Infinity")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value, key=str):
            if not isinstance(key, str):
                raise TypeError(f"controller protocol dictionary key is not a string: {key!r}")
            result[key] = canonical_value(value[key])
        return result
    if isinstance(value, (set, frozenset)):
        return sorted((canonical_value(item) for item in value), key=_json_sort_key)
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    raise TypeError(f"value is not JSON-safe: {value!r} ({type(value).__name__})")


def _json_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class FrozenMapping(Mapping[str, Any]):
    """A small, deeply immutable and pickle-safe JSON mapping.

    ``MappingProxyType`` is not pickleable and a frozen dataclass containing a
    regular dict is still mutable through that dict.  Protocol snapshots need both
    properties: a proposal may wait many ticks before execution and the complete
    session is checkpointed with pickle.
    """

    __slots__ = ("_items",)

    def __init__(self, value: Mapping[str, Any] | None = None) -> None:
        source = {} if value is None else value
        items: list[tuple[str, Any]] = []
        for key in sorted(source, key=str):
            if not isinstance(key, str):
                raise TypeError(
                    f"controller protocol dictionary key is not a string: {key!r}"
                )
            items.append((key, _freeze_canonical(canonical_value(source[key]))))
        object.__setattr__(self, "_items", tuple(items))

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __getitem__(self, key: str) -> Any:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenMapping({dict(self._items)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self.items()) == dict(other.items())

    def __hash__(self) -> int:
        return hash(self._items)

    def __reduce__(self):
        # Re-enter the validating constructor on load instead of exposing mutable
        # reconstruction state to pickle.
        return (type(self), (dict(self._items),))


def _freeze_canonical(value: Any) -> Any:
    """Freeze a value already normalized by :func:`canonical_value`."""
    if isinstance(value, dict):
        return FrozenMapping(value)
    if isinstance(value, list):
        return tuple(_freeze_canonical(item) for item in value)
    return value


def immutable_json_value(value: Any) -> Any:
    """Return a detached immutable snapshot with canonical JSON semantics."""
    return _freeze_canonical(canonical_value(value))


def immutable_json_mapping(value: Mapping[str, Any]) -> FrozenMapping:
    frozen = immutable_json_value(value)
    if not isinstance(frozen, FrozenMapping):  # defensive; the annotation is runtime-free
        raise TypeError("expected a controller protocol mapping")
    return frozen


@dataclass(frozen=True)
class PolicyAction:
    lever: str
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.lever, str) or not self.lever:
            raise ValueError("PolicyAction.lever must be a non-empty string")
        value = canonical_value(self.value)
        if self.lever == "sanctions_imposed_on" and isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            # EconomySet is a mathematical set on the wire as well as in the
            # engine.  Normalize before proposal hashing/idempotency so client
            # ordering and duplicates cannot create distinct payloads.  Element
            # domain checks deliberately remain Coordinator authority checks.
            by_json = {_json_sort_key(item): item for item in value}
            deduplicated = list(by_json.values())
            if all(type(item) is int for item in deduplicated):
                # Valid economy IDs have an integer ordering, not JSON's lexical
                # ordering (which would put 10 before 2).
                value = sorted(deduplicated)
            else:
                value = [by_json[key] for key in sorted(by_json)]
        object.__setattr__(self, "value", _freeze_canonical(value))

    def engine_value(self) -> Any:
        # EconomySet has an immutable engine representation but a sorted JSON array
        # on the wire.  This conversion happens before Registry validation.
        if self.lever == "sanctions_imposed_on" and isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            return frozenset(self.value)
        return self.value

    def to_dict(self) -> dict[str, Any]:
        return {"lever": self.lever, "value": canonical_value(self.value)}


@dataclass(frozen=True)
class PermittedAction:
    lever: str
    current_value: Any
    allowed: bool
    reason_code: str | None = None
    value_kind: str = "unknown"
    minimum: float | int | None = None
    maximum: float | int | None = None
    choices: tuple[Any, ...] = ()
    nullable: bool = False
    control_scale: float | None = None
    max_step: float | None = None
    earliest_effective_tick: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.lever, str) or not self.lever:
            raise ValueError("PermittedAction.lever must be a non-empty string")
        object.__setattr__(self, "current_value", immutable_json_value(self.current_value))
        object.__setattr__(
            self,
            "choices",
            tuple(immutable_json_value(choice) for choice in self.choices),
        )


def _immutable_observation(value: Any) -> Any:
    """Detach and freeze a context observation without erasing its public type.

    Controller observations are frozen dataclasses whose nested release values are
    themselves immutable.  Keeping that type is important to the Gym and heuristic
    adapters.  Ad-hoc dictionary observations, and any other object exposing only a
    wire representation, are snapshotted into the generic immutable JSON form.
    """
    params = getattr(type(value), "__dataclass_params__", None)
    trusted_immutable = bool(getattr(
        type(value), "_controller_observation_deeply_immutable", False,
    ))
    if params is not None and params.frozen and trusted_immutable \
            and callable(getattr(value, "to_dict", None)):
        # Validate now so a malformed custom observation cannot poison a later event
        # hash or checkpoint.  Known Institution/Public/Oracle observations are
        # deeply immutable at construction time.
        canonical_value(value.to_dict())
        return value
    if callable(getattr(value, "to_dict", None)):
        value = value.to_dict()
    return immutable_json_value(value)


@dataclass(frozen=True)
class DecisionContext:
    context_id: str
    decision_window_id: str
    economy_id: int
    seat: str
    decision_group: str
    boundary_tick: int
    expires_at_tick: int
    policy_versions: Mapping[str, int]
    observation: Any
    permitted_actions: tuple[PermittedAction, ...] = ()
    pending_policy: Mapping[str, Any] = field(default_factory=dict)
    current_policy: Mapping[str, Any] = field(default_factory=dict)
    pending_effective_ticks: Mapping[str, int] = field(default_factory=dict)
    emergency: bool = False
    emergency_trigger: str | None = None
    elapsed_ticks: int = 0
    last_effective_ticks: Mapping[str, int | None] = field(default_factory=dict)
    next_eligibility_ticks: Mapping[str, int] = field(default_factory=dict)
    admin_remaining: float = 0.0
    admin_reserved: float = 0.0
    admin_capacity: float = 0.0
    visible_cost_estimates: Mapping[str, Any] = field(default_factory=dict)
    emergency_bulletin: Mapping[str, Any] | None = None
    schema_version: int = CONTROLLER_SCHEMA_VERSION
    observation_schema_version: int = OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "policy_versions", immutable_json_mapping(self.policy_versions)
        )
        object.__setattr__(self, "observation", _immutable_observation(self.observation))
        object.__setattr__(self, "permitted_actions", tuple(self.permitted_actions))
        if not all(isinstance(item, PermittedAction) for item in self.permitted_actions):
            raise TypeError("permitted_actions must contain PermittedAction values")
        object.__setattr__(
            self, "pending_policy", immutable_json_mapping(self.pending_policy)
        )
        object.__setattr__(
            self, "current_policy", immutable_json_mapping(self.current_policy)
        )
        object.__setattr__(
            self,
            "pending_effective_ticks",
            immutable_json_mapping(self.pending_effective_ticks),
        )
        object.__setattr__(
            self, "last_effective_ticks", immutable_json_mapping(self.last_effective_ticks)
        )
        object.__setattr__(
            self, "next_eligibility_ticks", immutable_json_mapping(self.next_eligibility_ticks)
        )
        object.__setattr__(
            self, "visible_cost_estimates", immutable_json_mapping(self.visible_cost_estimates)
        )
        for name in ("admin_remaining", "admin_reserved", "admin_capacity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.admin_remaining + self.admin_reserved > self.admin_capacity + 1e-9:
            raise ValueError("admin remaining plus reserved exceeds capacity")
        bulletin = self.emergency_bulletin
        if bulletin is None and self.emergency and self.emergency_trigger is not None:
            bulletin = {
                "trigger_id": self.emergency_trigger,
                "generated_at_tick": self.boundary_tick,
                "expires_at_tick": self.expires_at_tick,
                "decision_group": self.decision_group,
            }
        if bulletin is not None:
            if not self.emergency:
                raise ValueError("a non-emergency context cannot carry an emergency bulletin")
            bulletin = immutable_json_mapping(bulletin)
            if bulletin.get("trigger_id") != self.emergency_trigger:
                raise ValueError("emergency bulletin trigger does not match context trigger")
        object.__setattr__(self, "emergency_bulletin", bulletin)

    def to_dict(self) -> dict[str, Any]:
        observation = self.observation
        if hasattr(observation, "to_dict"):
            observation = observation.to_dict()
        return canonical_value({
            "schema_version": self.schema_version,
            "observation_schema_version": self.observation_schema_version,
            "context_id": self.context_id,
            "decision_window_id": self.decision_window_id,
            "economy_id": self.economy_id,
            "seat": self.seat,
            "decision_group": self.decision_group,
            "boundary_tick": self.boundary_tick,
            "expires_at_tick": self.expires_at_tick,
            "policy_versions": dict(self.policy_versions),
            "observation": observation,
            "permitted_actions": self.permitted_actions,
            "pending_policy": dict(self.pending_policy),
            "current_policy": dict(self.current_policy),
            "pending_effective_ticks": dict(self.pending_effective_ticks),
            "emergency": self.emergency,
            "emergency_trigger": self.emergency_trigger,
            "emergency_bulletin": self.emergency_bulletin,
            "elapsed_ticks": self.elapsed_ticks,
            "last_effective_ticks": dict(self.last_effective_ticks),
            "next_eligibility_ticks": dict(self.next_eligibility_ticks),
            "admin_remaining": self.admin_remaining,
            "admin_reserved": self.admin_reserved,
            "admin_capacity": self.admin_capacity,
            "visible_cost_estimates": dict(self.visible_cost_estimates),
        })

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True)
class PolicyProposal:
    proposal_id: str
    idempotency_key: str
    context_id: str
    actions: tuple[PolicyAction, ...] = ()
    reason: str = ""
    based_on_policy_versions: Mapping[str, int] = field(default_factory=dict)
    supersedes_proposal_id: str | None = None
    schema_version: int = CONTROLLER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("proposal_id", "idempotency_key", "context_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.reason, str):
            raise TypeError("PolicyProposal.reason must be a string")
        if self.supersedes_proposal_id is not None and (
            not isinstance(self.supersedes_proposal_id, str)
            or not self.supersedes_proposal_id
        ):
            raise ValueError("supersedes_proposal_id must be a non-empty string or None")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("PolicyProposal.schema_version must be an integer")
        if self.schema_version != CONTROLLER_SCHEMA_VERSION:
            raise ValueError(f"unsupported controller schema version {self.schema_version}")
        actions = tuple(self.actions)
        if not all(isinstance(action, PolicyAction) for action in actions):
            raise TypeError("PolicyProposal.actions must contain PolicyAction values")
        # The protocol is absolute and canonical: semantic action order must not
        # change an idempotency hash or replay event.  UI display order belongs in
        # presentation metadata, not in the executable proposal payload.
        actions = tuple(sorted(
            actions,
            key=lambda action: (action.lever, canonical_json(action.value)),
        ))
        object.__setattr__(self, "actions", actions)
        if not isinstance(self.based_on_policy_versions, Mapping):
            raise TypeError("based_on_policy_versions must be a mapping")
        for key, value in self.based_on_policy_versions.items():
            if not isinstance(key, str) or not key:
                raise ValueError("policy version keys must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("policy versions must be non-negative integers")
        object.__setattr__(
            self,
            "based_on_policy_versions",
            immutable_json_mapping(self.based_on_policy_versions),
        )
        canonical_value(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "idempotency_key": self.idempotency_key,
            "context_id": self.context_id,
            "actions": [action.to_dict() for action in self.actions],
            "reason": self.reason,
            "based_on_policy_versions": dict(self.based_on_policy_versions),
            "supersedes_proposal_id": self.supersedes_proposal_id,
        }


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    proposal_id: str
    status: str
    reason_code: str
    accepted_tick: int | None = None
    effective_tick: int | None = None
    accepted_sequence: int | None = None
    reserved_admin_cost: float = 0.0
    adjustment_cost: float = 0.0


@dataclass
class PendingDecision:
    decision: PolicyDecision
    proposal: PolicyProposal
    context: DecisionContext
    status: str = "accepted_pending"
    reserved_admin_cost: float = 0.0
    adjustment_cost: float = 0.0

    @property
    def effective_tick(self) -> int:
        assert self.decision.effective_tick is not None
        return self.decision.effective_tick

    @property
    def touched_levers(self) -> tuple[str, ...]:
        return tuple(action.lever for action in self.proposal.actions)
