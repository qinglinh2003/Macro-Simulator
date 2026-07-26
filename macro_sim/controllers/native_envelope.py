"""Canonical, pickle-free M10 controller envelope codec.

The native World owns these bytes inside ``HybridControlledBridge``.  Python
objects are reconstructable caches: only explicitly registered controller
types can enter the envelope, and decoding never imports a type named by input.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import hashlib
import json
import math
import random
from typing import Any

from .chunk_store import export_chunk_package, import_chunk_package
from .coordinator import PolicyCoordinator
from .costs import AdjustmentCostSpec, CostWeights
from .events import EventStream
from .observation import (
    InstitutionObservation,
    ObservationFieldSpec,
    ObservationSpec,
    OracleObservation,
    PublicObservation,
    Release,
    ReleaseSequence,
    ReleaseService,
)
from .occupants import (
    HeuristicOccupant,
    HumanQueueOccupant,
    NullOccupant,
    RLOccupant,
    RandomFuzzOccupant,
    ScheduledOccupant,
)
from .protocol import (
    DecisionContext,
    PendingDecision,
    PermittedAction,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
    canonical_json,
)
from .scheduler import CalendarSpec, DecisionScheduler, TriggerSpec, TriggerState


CONTROLLER_ENVELOPE_FORMAT = "macro-sim-controller-envelope-v2"
MAX_CONTROLLER_ENVELOPE_BYTES = 16 * 1024 * 1024

_TYPES = (
    AdjustmentCostSpec,
    CalendarSpec,
    CostWeights,
    DecisionContext,
    DecisionScheduler,
    EventStream,
    HeuristicOccupant,
    HumanQueueOccupant,
    InstitutionObservation,
    NullOccupant,
    ObservationFieldSpec,
    ObservationSpec,
    OracleObservation,
    PendingDecision,
    PermittedAction,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
    PublicObservation,
    RLOccupant,
    RandomFuzzOccupant,
    Release,
    ScheduledOccupant,
    TriggerSpec,
    TriggerState,
)
_TYPE_TO_ID = {
    cls: f"{cls.__module__.removeprefix('macro_sim.controllers.')}:{cls.__name__}"
    for cls in _TYPES
}
_ID_TO_TYPE = {type_id: cls for cls, type_id in _TYPE_TO_ID.items()}
CONTROLLER_ENVELOPE_CONTRACT_HASH = hashlib.sha256(
    canonical_json({
        "format": CONTROLLER_ENVELOPE_FORMAT,
        "root_fields": (
            "assignment_archive",
            "coordinator",
            "cost_spec",
            "events",
            "release_service",
            "scheduler",
            "seat_assignments",
            "session",
        ),
        "types": sorted(_ID_TO_TYPE),
    }).encode("utf-8")
).hexdigest()


def _sort_key(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("controller envelope forbids non-finite numbers")
        return value
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, random.Random):
        return {"$random": _encode(value.getstate())}
    if isinstance(value, EventStream):
        return {"$event_stream": _encode(value.to_state())}
    if isinstance(value, ReleaseSequence):
        return {"$release_sequence": _encode(value.to_state())}
    if isinstance(value, Mapping):
        pairs = [
            [_encode(key), _encode(item)]
            for key, item in value.items()
        ]
        pairs.sort(key=lambda pair: _sort_key(pair[0]))
        return {"$map": pairs}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return {"$list": [_encode(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        items = [_encode(item) for item in value]
        items.sort(key=_sort_key)
        return {"$set": items}
    if isinstance(value, ReleaseService):
        return {
            "$release_service": {
                "history": _encode(value._history),
                "last_boundary": _encode(value._last_boundary),
                "next_period_index": _encode(value._next_period_index),
                "spec": _encode(value.spec),
            },
        }
    if is_dataclass(value):
        type_id = _TYPE_TO_ID.get(type(value))
        if type_id is None:
            raise TypeError(
                f"unsupported controller envelope type {type(value).__name__}"
            )
        if isinstance(value, HeuristicOccupant) and value.rule is not None:
            raise TypeError(
                "custom heuristic callables require an external occupant codec"
            )
        if isinstance(value, RLOccupant) and value.policy is not None:
            raise TypeError(
                "live RL callables require a portable artifact occupant codec"
            )
        return {
            "$type": type_id,
            "fields": {
                item.name: _encode(getattr(value, item.name))
                for item in fields(value)
            },
        }
    raise TypeError(
        f"unsupported controller envelope value {type(value).__name__}"
    )


def _decode(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("controller envelope contains a non-finite number")
        return value
    if not isinstance(value, dict) or len(value) == 0:
        raise TypeError("controller envelope tagged value is malformed")
    if "$bytes" in value and set(value) == {"$bytes"}:
        raw = value["$bytes"]
        if not isinstance(raw, str):
            raise TypeError("controller envelope byte value is malformed")
        return base64.b64decode(raw, validate=True)
    if "$random" in value and set(value) == {"$random"}:
        generator = random.Random()
        generator.setstate(_decode(value["$random"]))
        return generator
    if "$event_stream" in value and set(value) == {"$event_stream"}:
        state = _decode(value["$event_stream"])
        return EventStream.from_state(state)
    if "$release_sequence" in value and set(value) == {
        "$release_sequence",
    }:
        state = _decode(value["$release_sequence"])
        return ReleaseSequence.from_state(state)
    if "$tuple" in value and set(value) == {"$tuple"}:
        return tuple(_decode(item) for item in value["$tuple"])
    if "$list" in value and set(value) == {"$list"}:
        return [_decode(item) for item in value["$list"]]
    if "$set" in value and set(value) == {"$set"}:
        return set(_decode(item) for item in value["$set"])
    if "$map" in value and set(value) == {"$map"}:
        output: dict[Any, Any] = {}
        for pair in value["$map"]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise TypeError("controller envelope mapping pair is malformed")
            key = _decode(pair[0])
            if key in output:
                raise ValueError("controller envelope mapping has a duplicate key")
            output[key] = _decode(pair[1])
        return output
    if "$release_service" in value and set(value) == {"$release_service"}:
        raw = value["$release_service"]
        if not isinstance(raw, dict) or set(raw) != {
            "history", "last_boundary", "next_period_index", "spec",
        }:
            raise TypeError("controller release-service envelope is malformed")
        service = ReleaseService(_decode(raw["spec"]))
        service._history = _decode(raw["history"])
        service._last_boundary = _decode(raw["last_boundary"])
        service._next_period_index = _decode(raw["next_period_index"])
        return service
    if set(value) == {"$type", "fields"}:
        type_id = value["$type"]
        cls = _ID_TO_TYPE.get(type_id)
        if cls is None:
            raise ValueError(f"unknown controller envelope type {type_id!r}")
        raw_fields = value["fields"]
        if not isinstance(raw_fields, dict):
            raise TypeError("controller envelope dataclass fields are malformed")
        declared = {item.name: item for item in fields(cls)}
        if set(raw_fields) != set(declared):
            raise ValueError(
                f"controller envelope fields do not match {type_id}"
            )
        decoded = {
            name: _decode(item)
            for name, item in raw_fields.items()
        }
        kwargs = {
            name: decoded[name]
            for name, item in declared.items()
            if item.init
        }
        instance = cls(**kwargs)
        for name, item in declared.items():
            if not item.init:
                object.__setattr__(instance, name, decoded[name])
        return instance
    raise ValueError("controller envelope uses an unknown tag")


def _coordinator_state(coordinator: PolicyCoordinator) -> dict[str, Any]:
    return {
        item.name: getattr(coordinator, item.name)
        for item in fields(PolicyCoordinator)
        if item.name not in {"scheduler", "events", "cost_spec"}
    }


def encode_controller_state(session: Any) -> bytes:
    """Encode the complete neutral controller state at a committed boundary."""
    session.validate_checkpoint_phase()
    document = {
        "contract_hash": CONTROLLER_ENVELOPE_CONTRACT_HASH,
        "format": CONTROLLER_ENVELOPE_FORMAT,
        "scheduler": _encode(session.scheduler),
        "events": _encode(session.events),
        "cost_spec": _encode(session.cost_spec),
        "release_service": _encode(session.release_service),
        "seat_assignments": _encode(session.seat_assignments),
        "assignment_archive": _encode(session.assignment_archive),
        "coordinator": _encode(_coordinator_state(session.coordinator)),
        "session": _encode({
            "run_mode": session.run_mode,
            "phase": session.phase,
            "boundary_tick": session.boundary_tick,
            "policy_fingerprint": session.policy_fingerprint,
            "next_transaction_sequence": session.next_transaction_sequence,
            "engine_log_cursors": session.engine_log_cursors,
            "shock_event_cursor": session.shock_event_cursor,
            "current_context_ids": session.current_context_ids,
            "missing_context_ids": session.missing_context_ids,
            "collected": session._collected,
            "opened_contexts": session._opened_contexts,
            "recorded_human_context_ids":
                session._recorded_human_context_ids,
            "next_assignment_sequence": session.next_assignment_sequence,
        }),
    }
    payload = canonical_json(document).encode("utf-8")
    if len(payload) > MAX_CONTROLLER_ENVELOPE_BYTES:
        raise ValueError(
            "controller envelope exceeds the native 16 MiB bound; "
            "event chunking is required"
        )
    return payload


def controller_archive_package(session: Any) -> bytes:
    """Export every immutable chunk referenced by the controller state."""
    events = getattr(session, "events", None)
    digests = set(
        () if not isinstance(events, EventStream) else events.chunk_digests
    )
    release_service = getattr(session, "release_service", None)
    if isinstance(release_service, ReleaseService):
        for history in release_service._history.values():
            if isinstance(history, ReleaseSequence):
                digests.update(history.chunk_digests)
    return export_chunk_package(digests)


def decode_controller_state(
    payload: bytes, *, archive_package: bytes | None = None,
) -> dict[str, Any]:
    """Decode and validate a neutral controller envelope without dynamic imports."""
    if not isinstance(payload, bytes):
        raise TypeError("controller envelope payload must be bytes")
    imported = (
        None if archive_package is None
        else set(import_chunk_package(archive_package))
    )
    if len(payload) > MAX_CONTROLLER_ENVELOPE_BYTES:
        raise ValueError("controller envelope exceeds the native size bound")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("controller envelope is not canonical JSON") from exc
    if not isinstance(document, dict) or set(document) != {
        "assignment_archive",
        "contract_hash",
        "coordinator",
        "cost_spec",
        "events",
        "format",
        "release_service",
        "scheduler",
        "seat_assignments",
        "session",
    }:
        raise ValueError("controller envelope root fields are malformed")
    if document["format"] != CONTROLLER_ENVELOPE_FORMAT:
        raise ValueError("unsupported controller envelope format")
    if document["contract_hash"] != CONTROLLER_ENVELOPE_CONTRACT_HASH:
        raise ValueError("controller envelope contract hash does not match")
    if canonical_json(document).encode("utf-8") != payload:
        raise ValueError("controller envelope JSON is not canonical")
    decoded = {
        name: _decode(document[name])
        for name in (
            "scheduler",
            "events",
            "cost_spec",
            "release_service",
            "seat_assignments",
            "assignment_archive",
            "coordinator",
            "session",
        )
    }
    if not isinstance(decoded["scheduler"], DecisionScheduler):
        raise TypeError("controller envelope scheduler type is invalid")
    if not isinstance(decoded["events"], EventStream):
        raise TypeError("controller envelope event stream type is invalid")
    if not isinstance(decoded["cost_spec"], AdjustmentCostSpec):
        raise TypeError("controller envelope cost spec type is invalid")
    if not isinstance(decoded["release_service"], ReleaseService):
        raise TypeError("controller envelope release service type is invalid")
    decoded["events"].verify()
    if imported is not None:
        referenced = set(decoded["events"].chunk_digests)
        for history in decoded["release_service"]._history.values():
            if isinstance(history, ReleaseSequence):
                referenced.update(history.chunk_digests)
        if imported != referenced:
            raise ValueError(
                "controller archive package does not exactly match its manifest"
            )
    return decoded


def install_controller_state(session: Any, decoded: Mapping[str, Any]) -> None:
    """Install decoded state on a fresh session while restoring shared roots."""
    session.scheduler = decoded["scheduler"]
    session.events = decoded["events"]
    session.cost_spec = decoded["cost_spec"]
    session.release_service = decoded["release_service"]
    session.seat_assignments = decoded["seat_assignments"]
    session.assignment_archive = decoded["assignment_archive"]
    coordinator_fields = dict(decoded["coordinator"])
    session.coordinator = PolicyCoordinator(
        scheduler=session.scheduler,
        events=session.events,
        cost_spec=session.cost_spec,
        **coordinator_fields,
    )
    state = dict(decoded["session"])
    session.run_mode = state["run_mode"]
    session.phase = state["phase"]
    session.boundary_tick = state["boundary_tick"]
    session.policy_fingerprint = state["policy_fingerprint"]
    session.next_transaction_sequence = state["next_transaction_sequence"]
    session.engine_log_cursors = state["engine_log_cursors"]
    session.shock_event_cursor = state["shock_event_cursor"]
    session.current_context_ids = state["current_context_ids"]
    session.missing_context_ids = state["missing_context_ids"]
    session._collected = state["collected"]
    session._opened_contexts = state["opened_contexts"]
    session._recorded_human_context_ids = state[
        "recorded_human_context_ids"
    ]
    session.next_assignment_sequence = state["next_assignment_sequence"]
