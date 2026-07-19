"""Save/resume checkpoints: an engine-neutral container around an engine-specific blob.

Design: docs/checkpoint_design.md. Container layout (a zip, extension ``.msim``):

    header.json    -- engine-NEUTRAL metadata: container/blob format tags, tick, engine
                      class, git commit, config digest. Any future engine (or a game
                      frontend's save-slot UI) reads this without touching the blob.
    state.pkl.gz   -- engine-SPECIFIC state blob. For the Python engine: a gzip'd
                      pickle of the full object graph (World or Economy) plus sidecar
                      state (e.g. probe-collector records). Pickle covers every piece
                      of live state BY CONSTRUCTION -- RNG streams, ledgers, lot books,
                      EMAs, caches, estate suspense -- so there is no "forgot to
                      serialize a field" failure mode while the model is still evolving.

The hand-written, language-neutral state schema is deliberately deferred to the
model-freeze / compiled-engine port; it will slot into this same container as a new
``blob_format``. What survives that engine swap is everything around the blob:
container layout, header schema, ruleset serialization, event-log schema.

SECURITY: loading a pickle executes arbitrary code. This is a local dev tool --
NEVER load a third-party ``.msim``. The game-era structured blob removes this hazard.

Acceptance contract (tests/test_checkpoint.py): a resumed run is bit-identical to an
uninterrupted one, across a process boundary:

    digest(run 2N ticks straight) == digest(run N -> save -> load in a FRESH process -> run N)
"""
from __future__ import annotations

import gzip
import functools
import hashlib
import json
import os
import pickle
import random
import subprocess
import sys
import zipfile
from collections import deque
from collections.abc import Mapping
from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from fractions import Fraction
import math
from pathlib import Path
from typing import Any

CONTAINER_FORMAT = "msim-container-v1"
BLOB_FORMAT = "python-pickle-v0"


def _semantic_state(
    value: Any,
    _memo: dict[int, tuple[int, Any]] | None = None,
) -> Any:
    """Canonicalize a Python object graph with deterministic reference markers.

    Pickle is the checkpoint *transport*, but its bytes are not a stable state
    digest: an unpickle/re-pickle cycle may choose different memo opcodes even when
    continuation semantics are identical.  This walker sorts unordered containers,
    captures RNG/array state, and assigns traversal-order references so cycles and
    shared live objects are represented without embedding process object ids.
    """
    if _memo is None:
        _memo = {}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"__float__": repr(value)}
    if isinstance(value, Enum):
        return {
            "__enum__": f"{type(value).__module__}.{type(value).__qualname__}",
            "name": value.name,
        }
    if isinstance(value, (Decimal, Fraction)):
        return {
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": str(value),
        }
    if isinstance(value, (date, datetime, time)):
        return {
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": value.isoformat(),
        }
    if isinstance(value, Path):
        return {"__path__": str(value)}
    if isinstance(value, bytes):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest()}
    if isinstance(value, bytearray):
        return {"__bytearray_sha256__": hashlib.sha256(bytes(value)).hexdigest()}

    # NumPy is an engine dependency, but keep checkpoint import failure-friendly.
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - the simulator itself imports NumPy
        np = None
    if np is not None and isinstance(value, np.generic):
        return _semantic_state(value.item(), _memo)

    object_id = id(value)
    existing = _memo.get(object_id)
    if existing is not None and existing[1] is value:
        return {"__ref__": existing[0]}
    reference = len(_memo)
    # Keep a strong reference for the duration of the walk.  RNG ``getstate`` and
    # similar APIs create temporary tuples; without keepalive, CPython may reuse a
    # released tuple's id and turn an unrelated later state into a false __ref__.
    _memo[object_id] = (reference, value)

    def nested(item: Any) -> Any:
        return _semantic_state(item, _memo)

    def sort_probe(item: Any) -> str:
        # Sorting gets an isolated memo so unordered-container insertion order
        # cannot influence reference numbering in the real traversal.
        probe = _semantic_state(item, {})
        return json.dumps(probe, sort_keys=True, separators=(",", ":"), default=str)

    if isinstance(value, random.Random):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "state": nested(value.getstate()),
        }
    if np is not None and isinstance(value, np.ndarray):
        return {
            "__id__": reference,
            "__ndarray__": str(value.dtype),
            "shape": list(value.shape),
            "bytes_sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest(),
        }
    if np is not None and isinstance(value, np.random.Generator):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "state": nested(value.bit_generator.state),
        }
    if is_dataclass(value):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "fields": {
                item.name: nested(getattr(value, item.name))
                for item in dataclass_fields(value)
            },
        }
    if isinstance(value, Mapping):
        pairs = sorted(value.items(), key=lambda pair: sort_probe(pair[0]))
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "items": [[nested(key), nested(item)] for key, item in pairs],
        }
    if isinstance(value, (list, tuple)):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "items": [nested(item) for item in value],
        }
    if isinstance(value, deque):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "maxlen": value.maxlen,
            "items": [nested(item) for item in value],
        }
    if isinstance(value, (set, frozenset)):
        ordered = sorted(value, key=sort_probe)
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "items": [nested(item) for item in ordered],
        }
    if isinstance(value, range):
        return {
            "__id__": reference,
            "__range__": [value.start, value.stop, value.step],
        }
    if isinstance(value, type):
        return {"__id__": reference, "__class__": f"{value.__module__}.{value.__qualname__}"}
    if callable(value):
        callable_state: dict[str, Any] = {}
        if isinstance(value, functools.partial):
            # ``partial`` exposes no function defaults/closure of its own.  Its
            # continuation semantics live in these three public attributes.
            callable_state["func"] = nested(value.func)
            callable_state["args"] = nested(value.args)
            callable_state["keywords"] = nested(value.keywords or {})
        bound_self = getattr(value, "__self__", None)
        if bound_self is not None:
            callable_state["bound_self"] = nested(bound_self)
        defaults = getattr(value, "__defaults__", None)
        if defaults is not None:
            callable_state["defaults"] = nested(defaults)
        kwdefaults = getattr(value, "__kwdefaults__", None)
        if kwdefaults is not None:
            callable_state["kwdefaults"] = nested(kwdefaults)
        closure = getattr(value, "__closure__", None)
        if closure is not None:
            captured = []
            for cell in closure:
                try:
                    captured.append(nested(cell.cell_contents))
                except ValueError:  # empty closure cell
                    captured.append({"__empty_cell__": True})
            callable_state["closure"] = captured
        if hasattr(value, "__dict__"):
            callable_state["attributes"] = nested(vars(value))
        return {
            "__id__": reference,
            "__callable__": f"{getattr(value, '__module__', '')}."
            f"{getattr(value, '__qualname__', type(value).__qualname__)}",
            "state": callable_state,
        }
    if hasattr(value, "__dict__"):
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "state": nested(vars(value)),
        }
    slots: dict[str, Any] = {}
    for cls in type(value).__mro__:
        declared = getattr(cls, "__slots__", ())
        if isinstance(declared, str):
            declared = (declared,)
        for name in declared:
            if name not in {"__dict__", "__weakref__"} and hasattr(value, name):
                slots[name] = nested(getattr(value, name))
    if slots:
        return {
            "__id__": reference,
            "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
            "slots": {name: slots[name] for name in sorted(slots)},
        }
    # Stateless extension/builtin leaf.  Its qualified type is the only portable
    # semantic information available; stateful engine types are covered above.
    return {
        "__id__": reference,
        "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
    }


def state_digest(engine: Any) -> str:
    """Canonical digest of an engine's simulated history, for bit-identity gates.

    sha256 over the json-serialized record rows -- the same discipline as the
    frontier digest. For a World: world_records + every economy's records; for a
    single Economy: its records. A resumed run must reproduce this EXACTLY.
    """
    if hasattr(engine, "coordinator") and hasattr(engine, "world"):
        return session_digest(engine)
    h = hashlib.sha256()
    economies = getattr(engine, "economies", None)
    if economies is not None:  # World
        for row in getattr(engine, "world_records", []) or []:
            h.update(json.dumps(row, sort_keys=True, default=str).encode())
        for econ in economies:
            for row in econ.records:
                h.update(json.dumps(row, sort_keys=True, default=str).encode())
    else:  # Economy
        for row in engine.records:
            h.update(json.dumps(row, sort_keys=True, default=str).encode())
    return h.hexdigest()


def session_digest(session: Any) -> str:
    """Canonical full-state digest for a controlled session.

    This intentionally hashes the complete checkpointable object graph rather
    than maintaining a second, hand-written list of fields.  Therefore new live
    engine ledgers/RNGs/caches and new controller cursors/cost clocks enter the
    identity gate automatically.  ``_semantic_state`` makes the hash stable across
    an unpickle/re-pickle cycle while retaining cycles and alias topology.
    """
    payload = _semantic_state(session)
    # ``run_mode`` is currently an execution-surface label only.  Replay sets it
    # to ``replay`` while reproducing an interactive source byte-for-byte; treating
    # that label as continuation state would make equivalent runs hash differently.
    if isinstance(payload, dict):
        payload.get("fields", {}).pop("run_mode", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_release_service_snapshot(
    root: Any,
    *,
    economy_count: int,
) -> None:
    """Validate the publication clock embedded in a controlled session.

    A ReleaseService is continuation state: allowing it to run ahead of the engine
    boundary leaks future vintages after resume even when World and policy state are
    otherwise bit-identical.  Custom release-service implementations are opaque to
    this checkpoint layer and retain their own validation responsibility.
    """
    from macro_sim.controllers.observation import Release, ReleaseService

    service = getattr(root, "release_service", None)
    if type(service) is not ReleaseService:
        return
    clock = getattr(service, "_last_boundary", None)
    if not isinstance(clock, Mapping):
        raise ValueError("controlled-session release clock is not a mapping")
    for economy_id, release_tick in clock.items():
        if type(economy_id) is not int or not 0 <= economy_id < economy_count:
            raise ValueError(
                "controlled-session release clock contains an invalid economy_id"
            )
        if type(release_tick) is not int or release_tick < 0:
            raise ValueError(
                "controlled-session release clock values must be non-negative strict ints"
            )
        if release_tick > root.boundary_tick:
            raise ValueError(
                "controlled-session release clock is ahead of the session boundary"
            )

    history = getattr(service, "_history", None)
    if not isinstance(history, Mapping):
        raise ValueError("controlled-session release history is not a mapping")
    for key, releases in history.items():
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("controlled-session release history key is malformed")
        economy_id, series_id = key
        if type(economy_id) is not int or not 0 <= economy_id < economy_count:
            raise ValueError(
                "controlled-session release history contains an invalid economy_id"
            )
        if not isinstance(series_id, str) or not series_id:
            raise ValueError("controlled-session release history series_id is malformed")
        release_clock = clock.get(economy_id)
        if release_clock is None:
            raise ValueError(
                "controlled-session release history has no corresponding release clock"
            )
        if not isinstance(releases, (list, tuple)):
            raise ValueError("controlled-session release history series is malformed")
        for release in releases:
            if not isinstance(release, Release):
                raise ValueError("controlled-session release history item is malformed")
            if release.economy_id != economy_id or release.series_id != series_id:
                raise ValueError(
                    "controlled-session release history item does not match its index"
                )
            released_at = release.released_at_tick
            if type(released_at) is not int or released_at < 0:
                raise ValueError(
                    "controlled-session release history tick must be a non-negative strict int"
                )
            if released_at > release_clock or released_at > root.boundary_tick:
                raise ValueError(
                    "controlled-session release history is ahead of its publication clock"
                )

    next_period = getattr(service, "_next_period_index", None)
    if not isinstance(next_period, Mapping):
        raise ValueError("controlled-session next release period index is not a mapping")
    fields_by_series = {
        field.series_id: field for field in service.spec.fields
    }
    for key, period_index in next_period.items():
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("controlled-session next release period key is malformed")
        economy_id, series_id = key
        if type(economy_id) is not int or economy_id not in clock:
            raise ValueError(
                "controlled-session next release period has no valid economy clock"
            )
        if not isinstance(series_id, str) or series_id not in fields_by_series:
            raise ValueError(
                "controlled-session next release period references an unknown series"
            )
        if type(period_index) is not int or period_index < 1:
            raise ValueError(
                "controlled-session next release period must be a positive strict int"
            )

    expected_keys = {
        (economy_id, series_id)
        for economy_id in clock
        for series_id in fields_by_series
    }
    if set(next_period) != expected_keys:
        raise ValueError(
            "controlled-session next release period index is incomplete or has extra keys"
        )
    if not set(history).issubset(expected_keys):
        raise ValueError(
            "controlled-session release history references an unknown clock/spec series"
        )

    for economy_id, series_id in sorted(expected_keys):
        field = fields_by_series[series_id]
        release_clock = clock[economy_id]
        due_numerator = (
            release_clock
            - field.phase_offset_ticks
            - field.publication_lag_ticks
        )
        completed_periods = max(0, due_numerator // field.frequency_ticks)
        expected_next = completed_periods + 1
        if next_period[(economy_id, series_id)] != expected_next:
            raise ValueError(
                "controlled-session next release period is unreachable from its clock/spec"
            )

        releases = history.get((economy_id, series_id), ())
        # v27 shock observables are boundary vintages and include boundary zero;
        # ordinary series cover completed engine periods and begin at boundary one.
        expected_release_count = (
            completed_periods + 1 if field.source == "shock" else completed_periods
        )
        if len(releases) != expected_release_count:
            raise ValueError(
                "controlled-session release history length disagrees with its next period"
            )
        period_start = 0 if field.source == "shock" else 1
        for period_index, release in enumerate(releases, start=period_start):
            if field.source == "shock":
                expected_reference_start = expected_reference_end = -1
                expected_released_at = (
                    field.phase_offset_ticks
                    + period_index * field.frequency_ticks
                    + field.publication_lag_ticks
                )
            else:
                expected_reference_end = (
                    field.phase_offset_ticks
                    + period_index * field.frequency_ticks
                    - 1
                )
                expected_reference_start = max(
                    0,
                    expected_reference_end - field.window_ticks + 1,
                )
                expected_released_at = (
                    expected_reference_end + 1 + field.publication_lag_ticks
                )
            if release.reference_start_tick != expected_reference_start \
                    or release.reference_end_tick != expected_reference_end \
                    or release.released_at_tick != expected_released_at:
                raise ValueError(
                    "controlled-session release history period is unreachable from its spec"
                )
            if release.access_class != field.access_class or release.unit != field.unit:
                raise ValueError(
                    "controlled-session release history metadata disagrees with its spec"
                )


def _validate_controlled_session_snapshot(root: Any) -> None:
    """Reject internally inconsistent snapshots before save and after load."""
    from macro_sim.controllers.transaction import world_policy_fingerprint

    root.events.verify()
    if root.coordinator.events is not root.events:
        raise ValueError("controlled-session coordinator/event stream identity is broken")
    if root.coordinator.scheduler is not root.scheduler:
        raise ValueError("controlled-session coordinator/scheduler identity is broken")
    if root.coordinator.cost_spec is not root.cost_spec:
        raise ValueError("controlled-session coordinator/cost spec identity is broken")
    actual_fingerprint = world_policy_fingerprint(root.world)
    if root.policy_fingerprint != actual_fingerprint:
        raise ValueError("controlled-session policy fingerprint does not match live World")
    if int(getattr(root.world, "t", -1)) != int(root.boundary_tick):
        raise ValueError("controlled-session snapshot world tick does not match boundary")
    economies = list(getattr(root.world, "economies", [root.world]))
    for economy_id, economy in enumerate(economies):
        if int(getattr(economy, "t", -1)) != int(root.boundary_tick):
            raise ValueError(
                f"controlled-session economy {economy_id} tick does not match boundary"
            )
        log = getattr(economy, "_policy_action_log", ())
        cursor = root.engine_log_cursors.get(economy_id)
        if not isinstance(cursor, int) or isinstance(cursor, bool) \
                or not 0 <= cursor <= len(log):
            raise ValueError(
                f"controlled-session engine log cursor {economy_id} is out of bounds"
            )
    extra_cursors = set(root.engine_log_cursors) - set(range(len(economies)))
    if extra_cursors:
        raise ValueError("controlled-session has engine log cursors for unknown economies")
    _validate_release_service_snapshot(root, economy_count=len(economies))
    opened = set(root._opened_contexts)
    current = set(root.current_context_ids)
    missing = set(root.missing_context_ids)
    collected = set(root._collected)
    recorded_human = getattr(root, "_recorded_human_context_ids", None)
    if type(recorded_human) is not set or any(
        not isinstance(context_id, str) or not context_id
        for context_id in recorded_human
    ):
        raise ValueError(
            "controlled-session recorded human input index must be a strict set[str]"
        )
    if not recorded_human.issubset(current):
        raise ValueError(
            "controlled-session recorded human inputs reference non-current contexts"
        )
    logged_human = {
        event.get("context_id")
        for event in root.events.events
        if event.get("event_type") == "human_proposal_queued"
        and event.get("replay_class") == "input"
        and event.get("context_id") in current
    }
    if recorded_human != logged_human:
        raise ValueError(
            "controlled-session recorded human input index disagrees with event log"
        )
    if len(current) != len(root.current_context_ids) \
            or len(missing) != len(root.missing_context_ids):
        raise ValueError("controlled-session current/missing context indexes contain duplicates")
    if opened != current or not missing.issubset(current):
        raise ValueError("controlled-session open/missing context indexes are inconsistent")
    for context_id, context in root._opened_contexts.items():
        if context.context_id != context_id:
            raise ValueError("controlled-session opened context key does not match payload")
        if root.coordinator.contexts.get(context_id) != context:
            raise ValueError("controlled-session opened/coordinator context indexes disagree")

    if root.phase == "boundary_start":
        if current or missing or collected or recorded_human:
            raise ValueError("boundary_start checkpoint must not retain open context state")
    elif root.phase == "awaiting_human":
        if not missing or collected != current - missing:
            raise ValueError("awaiting_human checkpoint context/collection state is inconsistent")
    elif root.phase == "ready_to_commit":
        if missing or collected != current:
            raise ValueError("ready_to_commit checkpoint context/collection state is inconsistent")
    else:
        raise ValueError(f"controlled-session checkpoint has unknown phase {root.phase!r}")
    for context_id, value in root._collected.items():
        if not isinstance(value, tuple) or len(value) != 3:
            raise ValueError("controlled-session collected proposal entry is malformed")
        proposal, actor, input_type = value
        if getattr(proposal, "context_id", None) != context_id:
            raise ValueError("controlled-session collected proposal/context mismatch")
        if not isinstance(actor, str) or not actor.strip() \
                or input_type not in {
                    "automatic_recorded", "human_recorded", "timeout",
                }:
            raise ValueError("controlled-session collected proposal metadata is malformed")
        if (input_type == "human_recorded") != (context_id in recorded_human):
            raise ValueError(
                "controlled-session human input marker/collection metadata disagree"
            )
        if input_type == "automatic_recorded":
            matching_inputs = [
                event for event in root.events.events
                if event.get("event_type") == "proposal_submitted"
                and event.get("replay_class") == "input"
                and event.get("context_id") == context_id
                and event.get("proposal_id") == proposal.proposal_id
                and event.get("payload", {}).get("input_origin") == "automatic"
            ]
            if len(matching_inputs) != 1:
                raise ValueError(
                    "controlled-session automatic collection disagrees with event log"
                )

    for context_id in recorded_human & missing:
        context = root._opened_contexts[context_id]
        occupant = root.seat_assignments.get((context.economy_id, context.seat))
        pending = getattr(occupant, "pending", None)
        if not isinstance(pending, Mapping) or context_id not in pending:
            raise ValueError(
                "controlled-session recorded human input has no queued proposal"
            )

    coordinator = root.coordinator
    for context_id, context in coordinator.contexts.items():
        if getattr(context, "context_id", None) != context_id:
            raise ValueError("controlled-session coordinator context index is inconsistent")
    for decision_id, decision in coordinator.decisions.items():
        if getattr(decision, "decision_id", None) != decision_id:
            raise ValueError("controlled-session decision index is inconsistent")
    for decision_id, pending in coordinator.pending.items():
        if getattr(pending.decision, "decision_id", None) != decision_id \
                or coordinator.decisions.get(decision_id) != pending.decision:
            raise ValueError("controlled-session pending/decision indexes are inconsistent")
        if pending.status != pending.decision.status:
            raise ValueError("controlled-session pending lifecycle status is inconsistent")
        if pending.proposal.proposal_id != pending.decision.proposal_id:
            raise ValueError("controlled-session pending proposal/decision indexes disagree")
        context_id = pending.context.context_id
        if coordinator.contexts.get(context_id) != pending.context \
                or pending.proposal.context_id != context_id:
            raise ValueError("controlled-session pending context index is inconsistent")

    if set(coordinator.idempotency) != set(coordinator.idempotency_payload):
        raise ValueError("controlled-session idempotency payload index is inconsistent")
    if len(coordinator.idempotency) != len(coordinator.decisions) \
            or set(coordinator.idempotency.values()) != set(coordinator.decisions):
        raise ValueError("controlled-session idempotency/decision indexes are inconsistent")
    attempts_by_proposal: dict[str, list[tuple[dict[str, Any], Any]]] = {}
    for idempotency_key, decision_id in coordinator.idempotency.items():
        decision = coordinator.decisions.get(decision_id)
        try:
            payload = json.loads(coordinator.idempotency_payload[idempotency_key])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("controlled-session idempotency payload is malformed") from exc
        if payload.get("idempotency_key") != idempotency_key \
                or payload.get("proposal_id") != decision.proposal_id:
            raise ValueError("controlled-session idempotency payload does not match decision")
        attempts_by_proposal.setdefault(decision.proposal_id, []).append(
            (payload, decision)
        )

    for context_id, proposal_id in coordinator.proposal_for_context.items():
        if context_id not in coordinator.contexts:
            raise ValueError("controlled-session proposal/context index references unknown context")
        canonical_attempts = [
            (payload, decision)
            for payload, decision in attempts_by_proposal.get(proposal_id, ())
            if decision.reason_code != "duplicate_proposal_id"
            and payload.get("context_id") == context_id
        ]
        if len(canonical_attempts) != 1:
            raise ValueError("controlled-session proposal/context index is ambiguous")


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _config_digest(obj: Any) -> str | None:
    """Best-effort stable digest of the run's config(s) for the header."""
    try:
        if hasattr(obj, "coordinator") and hasattr(obj, "world"):
            obj = obj.world
        cfgs = getattr(obj, "configs", None)
        if cfgs is None:
            cfg = getattr(obj, "cfg", None)
            cfgs = [cfg] if cfg is not None else []
        h = hashlib.sha256()
        for cfg in cfgs:
            h.update(repr(cfg).encode())
        return h.hexdigest()[:16]
    except Exception:
        return None


def _validate_shock_snapshot(root: Any, *, tick: int) -> Any | None:
    """Validate the v27 tape/runtime/event prefix before save and after load."""
    from macro_sim.shocks import get_shock_engine

    engine_root = root.world if hasattr(root, "world") and hasattr(root, "coordinator") else root
    engine = get_shock_engine(engine_root)
    if engine is None:
        if hasattr(root, "shock_event_cursor") and root.shock_event_cursor != 0:
            raise ValueError("controlled-session shock cursor exists without a shock engine")
        return None
    engine.events.verify()
    if engine.current_tick != int(tick) - 1:
        raise ValueError(
            "shock engine is not at a completed simulation boundary "
            f"(shock tick {engine.current_tick}, checkpoint tick {tick})"
        )
    ids = {item.shock_id for item in engine.specs}
    for name, values in (
        ("announced", engine._announced),
        ("active", engine._active),
        ("realized", engine._realized),
    ):
        if not set(values).issubset(ids):
            raise ValueError(f"shock engine {name} index references an unknown shock")
    expected_active = {
        item.shock_id for item in engine.specs
        if not engine.registry[item.kind].one_shot
        and item.intensity_at(engine.current_tick) > 0.0
    } if engine.current_tick >= 0 else set()
    if engine._active != expected_active:
        raise ValueError("shock active index disagrees with tape/current tick")
    expected_announced = {
        item.shock_id for item in engine.specs
        if item.announcement_tick <= engine.current_tick
    } if engine.current_tick >= 0 else set()
    if engine._announced != expected_announced:
        raise ValueError("shock announcement index disagrees with tape/current tick")
    expected_realized = {
        item.shock_id for item in engine.specs
        if engine.registry[item.kind].one_shot and item.start_tick <= engine.current_tick
    } if engine.current_tick >= 0 else set()
    if engine._realized != expected_realized:
        raise ValueError("shock realization index disagrees with tape/current tick")
    economies = list(getattr(engine_root, "economies", [engine_root]))
    if any(getattr(economy, "shock_engine", None) is not engine for economy in economies):
        raise ValueError("World/economy shock-engine identity is broken")
    if hasattr(root, "shock_event_cursor"):
        cursor = root.shock_event_cursor
        if isinstance(cursor, bool) or not isinstance(cursor, int) \
                or cursor != len(engine.events.events):
            raise ValueError("controlled-session shock event cursor is not at the event head")
    # Rebuilding the canonical tape is also a schema/registry validation pass.
    if not isinstance(engine.contract_hash, str) or len(engine.contract_hash) != 64:
        raise ValueError("shock tape contract hash is malformed")
    return engine


def save_checkpoint(
    path: str,
    world: Any,
    *,
    tick: int,
    sidecar: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Write an atomic checkpoint container.

    ``world`` is the live engine object (World or Economy). ``sidecar`` carries
    companion state that lives OUTSIDE the engine object and must ride along
    explicitly -- e.g. the probe collector's records list. ``meta`` merges extra
    free-form fields into header.json (seed, out_dir, label, ...).

    Atomicity: the container is written to ``<path>.tmp`` and moved into place
    with ``os.replace`` -- a crash mid-save can never corrupt the previous file.
    """
    is_session = hasattr(world, "coordinator") and hasattr(world, "events") \
        and hasattr(world, "world")
    if is_session:
        world.validate_checkpoint_phase()
        _validate_controlled_session_snapshot(world)
        if int(tick) != int(world.boundary_tick):
            raise ValueError(
                f"session checkpoint tick {tick} != boundary {world.boundary_tick}"
            )
    shock_engine = _validate_shock_snapshot(world, tick=int(tick))
    payload = {"world": world, "sidecar": sidecar or {}}
    # gzip level 1: the blob is float-heavy simulation state; speed beats ratio.
    blob = gzip.compress(pickle.dumps(payload, protocol=5), compresslevel=1)
    header = {
        "container_format": CONTAINER_FORMAT,
        "blob_format": BLOB_FORMAT,
        "tick": int(tick),
        "engine_class": type(world).__name__,
        "git_commit": _git_commit(),
        "config_digest": _config_digest(world),
        "blob_bytes": len(blob),
    }
    if is_session:
        header.update({
            "session_phase": world.phase,
            "world_policy_version": sum(world.coordinator.policy_versions.values()),
            "policy_fingerprint": world.policy_fingerprint,
            "event_count": len(world.events.events),
            "event_head_hash": world.events.head_hash,
            "session_digest": session_digest(world),
        })
    if shock_engine is not None:
        header.update({
            "shock_contract_hash": shock_engine.contract_hash,
            "shock_event_count": len(shock_engine.events.events),
            "shock_event_head_hash": shock_engine.events.head_hash,
        })
    if meta:
        conflicts = set(meta).intersection(header)
        if conflicts:
            raise ValueError(
                "checkpoint meta cannot override reserved header fields: "
                + ", ".join(sorted(conflicts))
            )
        header.update(meta)
    tmp = f"{path}.tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("header.json", json.dumps(header, indent=1, default=str))
        zf.writestr("state.pkl.gz", blob)
    os.replace(tmp, path)
    return path


def read_header(path: str) -> dict[str, Any]:
    """Read the engine-neutral header without touching (or unpickling) the blob."""
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("header.json"))


def load_checkpoint(
    path: str,
    *,
    require_same_commit: bool = False,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Load a checkpoint. Returns ``(world, sidecar, header)``.

    Version guard: the header records the git commit that wrote the state. With
    ``require_same_commit=True`` a mismatch refuses to load -- the class layout may
    have changed, and pickle would either fail loudly or, worse, resume with
    silently stale semantics. The DEFAULT is a warning, not a refusal: day-to-day
    crash forensics is "edit the code, then load the dump", and must be able to.
    """
    with zipfile.ZipFile(path) as zf:
        header = json.loads(zf.read("header.json"))
        if header.get("container_format") != CONTAINER_FORMAT:
            raise ValueError(f"unknown container format: {header.get('container_format')!r}")
        if header.get("blob_format") != BLOB_FORMAT:
            raise ValueError(
                f"blob format {header.get('blob_format')!r} is not readable by this engine "
                f"(expected {BLOB_FORMAT!r})"
            )
        here = _git_commit()
        there = header.get("git_commit")
        if here and there and here != there:
            msg = (f"checkpoint written at commit {there[:12]}, code is at {here[:12]}")
            if require_same_commit:
                raise ValueError(msg + "; pass require_same_commit=False to force")
            print(f"WARNING: {msg} -- resuming anyway", file=sys.stderr)
        payload = pickle.loads(gzip.decompress(zf.read("state.pkl.gz")))
    root = payload["world"]
    shock_engine = _validate_shock_snapshot(root, tick=int(header["tick"]))
    if shock_engine is not None:
        expected_shock = {
            "shock_contract_hash": shock_engine.contract_hash,
            "shock_event_count": len(shock_engine.events.events),
            "shock_event_head_hash": shock_engine.events.head_hash,
        }
        for key, value in expected_shock.items():
            if header.get(key) != value:
                raise ValueError(f"checkpoint {key} does not match shock state/event prefix")
    if hasattr(root, "coordinator") and hasattr(root, "events") and hasattr(root, "world"):
        _validate_controlled_session_snapshot(root)
        expected = {
            "tick": root.boundary_tick,
            "session_phase": root.phase,
            "world_policy_version": sum(root.coordinator.policy_versions.values()),
            "policy_fingerprint": root.policy_fingerprint,
            "event_count": len(root.events.events),
            "event_head_hash": root.events.head_hash,
            "session_digest": session_digest(root),
        }
        for key, value in expected.items():
            if header.get(key) != value:
                raise ValueError(
                    f"controlled-session checkpoint {key} does not match snapshot/event prefix"
                )
    return root, payload.get("sidecar", {}), header
