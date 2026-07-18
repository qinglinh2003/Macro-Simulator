"""Canonical global event stream and deterministic hash chain."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable

from .protocol import CONTROLLER_SCHEMA_VERSION, canonical_json, canonical_value


EMPTY_EVENT_HEAD = hashlib.sha256(b"").hexdigest()


@dataclass
class EventStream:
    events: list[dict[str, Any]] = field(default_factory=list)
    _head_hash: str = EMPTY_EVENT_HEAD

    @property
    def head_hash(self) -> str:
        return self._head_hash

    def append(
        self,
        event_type: str,
        replay_class: str,
        boundary_tick: int,
        phase: str,
        *,
        transaction_id: str | None = None,
        economy_id: int | None = None,
        seat: str | None = None,
        actor: str = "system",
        context_id: str | None = None,
        proposal_id: str | None = None,
        decision_id: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        requested_actions: Any = (),
        effective_changes: Any = (),
        policy_versions_before: Any = None,
        policy_versions_after: Any = None,
        payload: Any = None,
    ) -> dict[str, Any]:
        if replay_class not in {"input", "derived"}:
            raise ValueError(f"invalid replay_class: {replay_class}")
        seq = len(self.events)
        event = canonical_value({
            "schema_version": CONTROLLER_SCHEMA_VERSION,
            "global_sequence": seq,
            "event_id": f"evt:{seq:012d}",
            "transaction_id": transaction_id,
            "event_type": event_type,
            "replay_class": replay_class,
            "boundary_tick": int(boundary_tick),
            "phase": phase,
            "economy_id": economy_id,
            "seat": seat,
            "actor": actor,
            "context_id": context_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "status": status,
            "reason": reason,
            "requested_actions": requested_actions,
            "effective_changes": effective_changes,
            "policy_versions_before": policy_versions_before or {},
            "policy_versions_after": policy_versions_after or {},
            "payload": payload or {},
        })
        self._head_hash = hashlib.sha256(
            bytes.fromhex(self._head_hash) + canonical_json(event).encode("utf-8")
        ).hexdigest()
        self.events.append(event)
        return event

    def verify(self) -> None:
        expected = EMPTY_EVENT_HEAD
        for seq, event in enumerate(self.events):
            if event.get("global_sequence") != seq or event.get("event_id") != f"evt:{seq:012d}":
                raise ValueError(f"event sequence mismatch at index {seq}")
            expected = hashlib.sha256(
                bytes.fromhex(expected) + canonical_json(event).encode("utf-8")
            ).hexdigest()
        if expected != self._head_hash:
            raise ValueError("event head hash does not match the event prefix")

    def input_events(self) -> list[dict[str, Any]]:
        return [event for event in self.events if event["replay_class"] == "input"]

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.events).encode("utf-8")
