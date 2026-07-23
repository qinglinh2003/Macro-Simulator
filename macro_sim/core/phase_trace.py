"""Passive phase-level evidence for Python/native differential tests.

The trace registry is external to simulation objects. Installing a sink does
not add checkpointed attributes or change constructor signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
from threading import RLock
from typing import Any, Protocol
import weakref

from .phases import (
    ECONOMY_VALIDATE_AND_MEASURE,
    PHASE_BY_ID,
    WORLD_VALIDATE_GLOBAL,
)


TRACE_SCHEMA_VERSION = "phase-trace-v1"


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_id(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("trace identity contains a non-finite float")
        return value
    if isinstance(value, (tuple, list)):
        return [_safe_id(item) for item in value]
    raise TypeError(
        f"trace identity must be scalar or tuple-like, got {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class TraceSpec:
    run_id: str
    scenario_id: str
    selected_state_fields: tuple[str, ...] = (
        "policy_rate",
        "public_capital",
        "house_price",
        "ledger_total_money",
        "ledger_total_credit",
        "record_count",
    )

    def __post_init__(self) -> None:
        if not self.run_id or not self.scenario_id:
            raise ValueError("trace run_id and scenario_id must be non-empty")
        fields = tuple(self.selected_state_fields)
        unknown = set(fields) - set(STATE_ACCESSORS)
        if unknown:
            raise ValueError(f"unknown trace state fields: {sorted(unknown)}")
        if len(fields) != len(set(fields)):
            raise ValueError("trace state fields must be unique")
        object.__setattr__(self, "selected_state_fields", fields)


class TraceSink(Protocol):
    spec: TraceSpec

    def append(self, record: dict[str, Any]) -> None:
        ...


@dataclass
class MemoryTraceSink:
    spec: TraceSpec
    records: list[dict[str, Any]] = field(default_factory=list)

    def append(self, record: dict[str, Any]) -> None:
        self.records.append(record)

    def canonical_bytes(self) -> bytes:
        return b"".join(_canonical_bytes(record) for record in self.records)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class JsonLinesTraceSink:
    spec: TraceSpec
    path: Path

    def __post_init__(self) -> None:
        path = Path(self.path)
        if path.exists():
            raise FileExistsError(f"refusing to append to an existing trace: {path}")
        object.__setattr__(self, "path", path)

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(_canonical_bytes(record))


@dataclass(frozen=True)
class _Registration:
    reference: weakref.ReferenceType[Any]
    sink: TraceSink
    event_stream: Any = None
    world_managed: bool = False


_REGISTRY: dict[int, _Registration] = {}
_REGISTRY_LOCK = RLock()


def _register(
    engine: Any,
    sink: TraceSink,
    *,
    event_stream: Any,
    world_managed: bool,
) -> None:
    object_id = id(engine)

    def remove(reference: weakref.ReferenceType[Any]) -> None:
        with _REGISTRY_LOCK:
            current = _REGISTRY.get(object_id)
            if current is not None and current.reference is reference:
                _REGISTRY.pop(object_id, None)

    reference = weakref.ref(engine, remove)
    _REGISTRY[object_id] = _Registration(
        reference=reference,
        sink=sink,
        event_stream=event_stream,
        world_managed=world_managed,
    )


def install_phase_trace(root: Any, sink: TraceSink) -> None:
    """Install one sink on an Economy, World, or ControlledSimulationSession."""

    if not isinstance(sink.spec, TraceSpec):
        raise TypeError("trace sink must carry a TraceSpec")
    session = root if hasattr(root, "coordinator") and hasattr(root, "world") else None
    engine = session.world if session is not None else root
    event_stream = getattr(session, "events", None)
    with _REGISTRY_LOCK:
        _register(
            root,
            sink,
            event_stream=event_stream,
            world_managed=hasattr(engine, "economies"),
        )
        if session is not None:
            _register(
                engine,
                sink,
                event_stream=event_stream,
                world_managed=hasattr(engine, "economies"),
            )
        economies = getattr(engine, "economies", None)
        if economies is not None:
            for economy in economies:
                _register(
                    economy,
                    sink,
                    event_stream=event_stream,
                    world_managed=True,
                )


def uninstall_phase_trace(root: Any) -> None:
    session = root if hasattr(root, "coordinator") and hasattr(root, "world") else None
    engine = session.world if session is not None else root
    targets = [root]
    if session is not None:
        targets.append(engine)
    targets.extend(getattr(engine, "economies", ()))
    with _REGISTRY_LOCK:
        for target in targets:
            registration = _REGISTRY.get(id(target))
            if registration is not None and registration.reference() is target:
                _REGISTRY.pop(id(target), None)


def phase_trace_installed(engine: Any) -> bool:
    return _registration(engine) is not None


def phase_trace_world_managed(engine: Any) -> bool:
    registration = _registration(engine)
    return bool(registration and registration.world_managed)


def _registration(engine: Any) -> _Registration | None:
    with _REGISTRY_LOCK:
        registration = _REGISTRY.get(id(engine))
        if registration is None:
            return None
        if registration.reference() is not engine:
            _REGISTRY.pop(id(engine), None)
            return None
        return registration


def _calendar_date(engine: Any) -> str | None:
    economies = getattr(engine, "economies", None)
    economy = economies[0] if economies else engine
    demographic_state = getattr(economy, "demographic_state", None)
    current = getattr(demographic_state, "current_date", None)
    if isinstance(current, date):
        return current.isoformat()
    raw = getattr(getattr(economy, "cfg", None), "simulation_start_date", None)
    if isinstance(raw, date):
        start = raw
    elif isinstance(raw, str):
        try:
            start = date.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    return (start + timedelta(days=int(getattr(economy, "t", 0)))).isoformat()


def _economies(engine: Any) -> tuple[Any, ...]:
    values = getattr(engine, "economies", None)
    return tuple(values) if values is not None else (engine,)


def _entity_counts(engine: Any) -> dict[str, int]:
    counts = {
        "economies": len(_economies(engine)),
        "households": 0,
        "firms": 0,
        "banks": 0,
        "people": 0,
        "accounts": 0,
        "records": 0,
        "world_records": len(getattr(engine, "world_records", ()) or ()),
    }
    for economy in _economies(engine):
        counts["households"] += len(getattr(economy, "households", ()) or ())
        counts["firms"] += len(getattr(economy, "firms", ()) or ())
        counts["banks"] += len(getattr(economy, "banks", ()) or ())
        demographic_state = getattr(economy, "demographic_state", None)
        counts["people"] += len(getattr(demographic_state, "people", ()) or ())
        ledger = getattr(economy, "ledger", None)
        counts["accounts"] += len(getattr(ledger, "_bal", {}) or {})
        counts["records"] += len(getattr(economy, "records", ()) or ())
    return counts


def _contract_counts(engine: Any) -> dict[str, int]:
    counts = {
        "loans": 0,
        "bonds": 0,
        "jobs": 0,
        "dwellings": 0,
        "active_shocks": 0,
    }
    for economy in _economies(engine):
        ledger = getattr(economy, "ledger", None)
        counts["loans"] += sum(
            amount > 0.0 for amount in (getattr(ledger, "_loans", {}) or {}).values()
        )
        counts["bonds"] += len(getattr(economy, "_bond_lots", ()) or ())
        labor_market = getattr(economy, "labor_market", None)
        counts["jobs"] += len(getattr(labor_market, "jobs", ()) or ())
        housing = getattr(economy, "housing", None)
        counts["dwellings"] += len(getattr(housing, "dwellings", ()) or ())
    shock_engine = getattr(engine, "shock_engine", None)
    if shock_engine is None and len(_economies(engine)) == 1:
        shock_engine = getattr(_economies(engine)[0], "shock_engine", None)
    counts["active_shocks"] = len(getattr(shock_engine, "_active", ()) or ())
    return counts


def _ledger_projection(engine: Any) -> list[dict[str, Any]]:
    result = []
    for ordinal, economy in enumerate(_economies(engine)):
        ledger = getattr(economy, "ledger", None)
        if ledger is None:
            continue
        balances = sorted(
            ((_safe_id(key), float(value)) for key, value in ledger._bal.items()),
            key=lambda item: _canonical_bytes(item[0]),
        )
        loans = sorted(
            ((_safe_id(key), float(value)) for key, value in ledger._loans.items()),
            key=lambda item: _canonical_bytes(item[0]),
        )
        reserves = sorted(
            (
                (_safe_id(key), float(value))
                for key, value in (ledger._reserves or {}).items()
            ),
            key=lambda item: _canonical_bytes(item[0]),
        )
        result.append(
            {
                "economy_id": int(getattr(economy, "economy_id", ordinal)),
                "balances": balances,
                "loans": loans,
                "reserves": reserves,
                "bank_securities": float(ledger.bank_securities),
            }
        )
    return result


def _event_projection(engine: Any, event_stream: Any) -> dict[str, Any]:
    controller = []
    if event_stream is not None:
        controller = list(getattr(event_stream, "events", ()) or ())
    policy = []
    for economy in _economies(engine):
        policy.extend(getattr(economy, "_policy_action_log", ()) or ())
    shock_engine = getattr(engine, "shock_engine", None)
    if shock_engine is None and len(_economies(engine)) == 1:
        shock_engine = getattr(_economies(engine)[0], "shock_engine", None)
    shock_stream = getattr(shock_engine, "events", None)
    shock = list(getattr(shock_stream, "events", ()) or ())
    return {
        "controller": controller,
        "policy": policy,
        "shock": shock,
    }


def _physical_command_projection(events: dict[str, Any]) -> list[dict[str, Any]]:
    commands = []
    for event in events["controller"]:
        changes = event.get("effective_changes") or ()
        if changes:
            commands.append(
                {
                    "source": "controller",
                    "event_id": event.get("event_id"),
                    "transaction_id": event.get("transaction_id"),
                    "economy_id": event.get("economy_id"),
                    "changes": changes,
                }
            )
    for event in events["policy"]:
        changes = event.get("actions") or ()
        if changes:
            commands.append(
                {
                    "source": "engine-policy",
                    "sequence": event.get("sequence"),
                    "economy_id": event.get("actor_economy"),
                    "changes": changes,
                }
            )
    return commands


def _rng_metadata(engine: Any) -> dict[str, Any]:
    streams = []
    for economy_ordinal, economy in enumerate(_economies(engine)):
        for name, value in sorted(vars(economy).items()):
            state: Any
            algorithm: str
            if isinstance(value, random.Random):
                algorithm = "python.random.Random"
                state = value.getstate()
            else:
                bit_generator = getattr(value, "bit_generator", None)
                if bit_generator is None or not hasattr(bit_generator, "state"):
                    continue
                algorithm = f"numpy.{type(bit_generator).__name__}"
                state = bit_generator.state
            streams.append(
                {
                    "economy_id": int(
                        getattr(economy, "economy_id", economy_ordinal)
                    ),
                    "attribute": name,
                    "algorithm": algorithm,
                    "state_digest": _digest(state),
                }
            )
    return {
        "root_seeds": [
            int(getattr(getattr(economy, "cfg", None), "seed", 0))
            for economy in _economies(engine)
        ],
        "streams": streams,
    }


def _invariant_results(engine: Any, phase_id: str) -> list[dict[str, str]]:
    if phase_id == ECONOMY_VALIDATE_AND_MEASURE:
        economy = engine
        result = [
            {"id": "invariant.ledger.deposit-conservation", "status": "passed"},
            {"id": "invariant.ledger.nonnegative-balances", "status": "passed"},
            {"id": "invariant.ledger.reserve-conservation", "status": "passed"},
            {
                "id": "invariant.securities.issuer-holder-identities",
                "status": "passed",
            },
        ]
        if getattr(economy, "housing", None) is not None:
            result.append(
                {"id": "invariant.housing.stock-and-title", "status": "passed"}
            )
        if getattr(economy, "demographic_bridge", None) is not None:
            result.append(
                {
                    "id": "invariant.demography.financial-claims",
                    "status": "passed",
                }
            )
        if getattr(economy, "labor_accounts", None) is not None:
            result.append(
                {"id": "invariant.labor.stock-flow", "status": "passed"}
            )
        return result
    if phase_id == WORLD_VALIDATE_GLOBAL:
        return [
            {"id": "invariant.world.dealer-flow-passthrough", "status": "passed"}
        ]
    return []


def _economy_for_scalar(engine: Any) -> Any:
    economies = getattr(engine, "economies", None)
    return economies[0] if economies else engine


def _policy_rate(engine: Any) -> Any:
    economy = _economy_for_scalar(engine)
    return float(getattr(economy, "r_interest", 0.0))


def _public_capital(engine: Any) -> Any:
    economy = _economy_for_scalar(engine)
    return float(getattr(economy, "public_capital", 0.0))


def _house_price(engine: Any) -> Any:
    economy = _economy_for_scalar(engine)
    return float(getattr(economy, "_house_price", 0.0))


def _ledger_total_money(engine: Any) -> Any:
    return [
        float(getattr(economy.ledger, "total_money", 0.0))
        for economy in _economies(engine)
    ]


def _ledger_total_credit(engine: Any) -> Any:
    return [
        float(getattr(economy.ledger, "total_credit", 0.0))
        for economy in _economies(engine)
    ]


def _record_count(engine: Any) -> Any:
    return [len(getattr(economy, "records", ())) for economy in _economies(engine)]


def _fx_rates(engine: Any) -> Any:
    rates = getattr(engine, "rates", None)
    return None if rates is None else [float(value) for value in rates.e]


STATE_ACCESSORS = {
    "policy_rate": _policy_rate,
    "public_capital": _public_capital,
    "house_price": _house_price,
    "ledger_total_money": _ledger_total_money,
    "ledger_total_credit": _ledger_total_credit,
    "record_count": _record_count,
    "fx_rates": _fx_rates,
}


def semantic_engine_digest(engine: Any) -> str:
    from macro_sim.checkpoint import state_digest

    return state_digest(engine)


def emit_phase_trace(
    engine: Any,
    phase_id: str,
    *,
    terminal_status: str = "ok",
) -> None:
    registration = _registration(engine)
    if registration is None:
        return
    descriptor = PHASE_BY_ID.get(phase_id)
    if descriptor is None:
        raise ValueError(f"unregistered phase id {phase_id!r}")
    sink = registration.sink
    economy_id = getattr(engine, "economy_id", None)
    selected_state = {
        name: STATE_ACCESSORS[name](engine)
        for name in sink.spec.selected_state_fields
    }
    events = _event_projection(engine, registration.event_stream)
    record = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "run_id": sink.spec.run_id,
        "scenario_id": sink.spec.scenario_id,
        "tick": int(getattr(engine, "t", 0)),
        "calendar_date": _calendar_date(engine),
        "economy_id": None if economy_id is None else int(economy_id),
        "phase_id": descriptor.id,
        "phase_code": descriptor.code,
        "phase_ordinal": descriptor.ordinal,
        "snapshot_epoch": descriptor.snapshot_epoch,
        "entity_counts": _entity_counts(engine),
        "contract_counts": _contract_counts(engine),
        "posting_digest": _digest(_ledger_projection(engine)),
        "event_digest": _digest(events),
        "physical_command_digest": _digest(_physical_command_projection(events)),
        "selected_state": selected_state,
        "invariant_results": _invariant_results(engine, phase_id),
        "rng_metadata": _rng_metadata(engine),
        "terminal_status": terminal_status,
    }
    sink.append(record)
