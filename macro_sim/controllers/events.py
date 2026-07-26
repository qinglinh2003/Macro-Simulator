"""Canonical bounded-memory event stream and deterministic hash chain."""
from __future__ import annotations

from collections.abc import Iterable, Iterator, MutableSequence, Sequence
import hashlib
import json
from numbers import Integral
from typing import Any, overload

from .chunk_store import get_chunk, put_chunk
from .protocol import CONTROLLER_SCHEMA_VERSION, canonical_json, canonical_value


EMPTY_EVENT_HEAD = hashlib.sha256(b"").hexdigest()
EVENT_CHUNK_FORMAT = "macro-sim-controller-event-chunk-v1"
DEFAULT_EVENT_CHUNK_SIZE = 128
DEFAULT_EVENT_TAIL_LIMIT = 256


def _canonical_chunk(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


class EventSequence(MutableSequence[dict[str, Any]]):
    """List-compatible sequence with a chained immutable historical prefix."""

    def __init__(
        self,
        values: Iterable[dict[str, Any]] = (),
        *,
        chunk_size: int = DEFAULT_EVENT_CHUNK_SIZE,
        tail_limit: int = DEFAULT_EVENT_TAIL_LIMIT,
        chunk_head_sha256: str | None = None,
        chunk_count: int = 0,
        archived_count: int = 0,
        tail: Iterable[dict[str, Any]] | None = None,
        total_count: int | None = None,
    ) -> None:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, Integral):
            raise TypeError("event chunk_size must be an integer")
        if isinstance(tail_limit, bool) or not isinstance(tail_limit, Integral):
            raise TypeError("event tail_limit must be an integer")
        self.chunk_size = int(chunk_size)
        self.tail_limit = int(tail_limit)
        if not 1 <= self.chunk_size <= 4096:
            raise ValueError("event chunk_size must be between 1 and 4096")
        if self.tail_limit < self.chunk_size:
            raise ValueError("event tail_limit must be at least chunk_size")
        self._chunk_head_sha256 = chunk_head_sha256
        self._chunk_count = int(chunk_count)
        self._archived_count = int(archived_count)
        if (
            self._chunk_count < 0
            or self._archived_count < 0
            or (self._chunk_count == 0) != (chunk_head_sha256 is None)
            or (
                chunk_head_sha256 is not None
                and not _valid_digest(chunk_head_sha256)
            )
        ):
            raise ValueError("event chunk-chain state is invalid")
        self._tail = [
            canonical_value(item)
            for item in (values if tail is None else tail)
        ]
        self._total_count = (
            self._archived_count + len(self._tail)
            if total_count is None else int(total_count)
        )
        if self._total_count != self._archived_count + len(self._tail):
            raise ValueError("event sequence total_count is inconsistent")
        self._validate_chain()
        self._compact_tail()

    @property
    def archived_count(self) -> int:
        return self._archived_count

    @property
    def retained_count(self) -> int:
        return len(self._tail)

    @property
    def chunk_count(self) -> int:
        return self._chunk_count

    @property
    def chunk_digests(self) -> tuple[str, ...]:
        return tuple(
            digest for digest, _document in self._chain(newest_first=False)
        )

    @staticmethod
    def _validate_event_position(
        event: dict[str, Any], sequence: int,
    ) -> None:
        if (
            not isinstance(event, dict)
            or event.get("global_sequence") != sequence
            or event.get("event_id") != f"evt:{sequence:012d}"
        ):
            raise ValueError(
                f"event sequence mismatch at global_sequence {sequence}"
            )

    def _decode_chunk(
        self, digest: str,
    ) -> dict[str, Any]:
        payload = get_chunk(digest)
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("event chunk is not valid JSON") from exc
        if (
            not isinstance(document, dict)
            or set(document) != {
                "events", "first_sequence", "format", "previous_sha256",
            }
            or document["format"] != EVENT_CHUNK_FORMAT
            or _canonical_chunk(document) != payload
            or (
                document["previous_sha256"] is not None
                and not _valid_digest(document["previous_sha256"])
            )
        ):
            raise ValueError("event chunk document is invalid")
        events = document["events"]
        first = document["first_sequence"]
        if (
            isinstance(first, bool)
            or not isinstance(first, int)
            or first < 0
            or not isinstance(events, list)
            or not 1 <= len(events) <= self.chunk_size
        ):
            raise ValueError("event chunk range is invalid")
        for offset, event in enumerate(events, start=first):
            self._validate_event_position(event, offset)
        return document

    def _chain(
        self, *, newest_first: bool,
    ) -> list[tuple[str, dict[str, Any]]]:
        output: list[tuple[str, dict[str, Any]]] = []
        digest = self._chunk_head_sha256
        seen: set[str] = set()
        while digest is not None:
            if digest in seen:
                raise ValueError("event chunk chain contains a cycle")
            seen.add(digest)
            document = self._decode_chunk(digest)
            output.append((digest, document))
            digest = document["previous_sha256"]
            if len(output) > self._chunk_count:
                raise ValueError("event chunk chain exceeds its declared count")
        if len(output) != self._chunk_count:
            raise ValueError("event chunk chain count does not match")
        if not newest_first:
            output.reverse()
        return output

    def _validate_chain(self) -> None:
        expected = 0
        for _digest, document in self._chain(newest_first=False):
            if document["first_sequence"] != expected:
                raise ValueError("event chunk chain is not contiguous")
            expected += len(document["events"])
        if expected != self._archived_count:
            raise ValueError("event archived count does not match its chain")
        for offset, event in enumerate(self._tail, start=expected):
            self._validate_event_position(event, offset)

    def _write_chunk(self, events: Sequence[dict[str, Any]]) -> None:
        first = self._archived_count
        for offset, event in enumerate(events, start=first):
            self._validate_event_position(event, offset)
        payload = _canonical_chunk({
            "events": list(events),
            "first_sequence": first,
            "format": EVENT_CHUNK_FORMAT,
            "previous_sha256": self._chunk_head_sha256,
        })
        self._chunk_head_sha256 = put_chunk(payload)
        self._chunk_count += 1
        self._archived_count += len(events)

    def _compact_tail(self) -> None:
        while len(self._tail) > self.tail_limit:
            chunk = self._tail[:self.chunk_size]
            self._write_chunk(chunk)
            del self._tail[:self.chunk_size]

    def _event_at(self, index: int) -> dict[str, Any]:
        if index < 0:
            index += self._total_count
        if not 0 <= index < self._total_count:
            raise IndexError("event index out of range")
        if index >= self._archived_count:
            return self._tail[index - self._archived_count]
        for _digest, document in self._chain(newest_first=True):
            first = int(document["first_sequence"])
            events = document["events"]
            if first <= index < first + len(events):
                return events[index - first]
        raise RuntimeError("event chunk index is unreachable")

    @overload
    def __getitem__(self, index: int) -> dict[str, Any]: ...

    @overload
    def __getitem__(self, index: slice) -> list[dict[str, Any]]: ...

    def __getitem__(
        self, index: int | slice,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self._total_count)
            return [
                self._event_at(position)
                for position in range(start, stop, step)
            ]
        return self._event_at(index)

    def __setitem__(
        self, index: int | slice, value: Any,
    ) -> None:
        if not isinstance(index, slice) or index != slice(None, None, None):
            raise TypeError("event sequence supports only complete replacement")
        self.replace_all(value)

    def __delitem__(self, index: int | slice) -> None:
        if isinstance(index, int):
            normalized = index if index >= 0 else self._total_count + index
            if normalized != self._total_count - 1:
                raise TypeError("event sequence supports only suffix deletion")
            self.truncate(normalized)
            return
        start, stop, step = index.indices(self._total_count)
        if step != 1 or stop != self._total_count:
            raise TypeError("event sequence supports only suffix deletion")
        self.truncate(start)

    def insert(self, index: int, value: dict[str, Any]) -> None:
        if index not in (self._total_count, -1):
            raise TypeError("event sequence is append-only")
        self.append(value)

    def append(self, value: dict[str, Any]) -> None:
        event = canonical_value(value)
        self._validate_event_position(event, self._total_count)
        self._tail.append(event)
        self._total_count += 1
        self._compact_tail()

    def _reset(self) -> None:
        self._chunk_head_sha256 = None
        self._chunk_count = 0
        self._archived_count = 0
        self._tail.clear()
        self._total_count = 0

    def truncate(self, count: int) -> None:
        if isinstance(count, bool) or not isinstance(count, Integral):
            raise TypeError("event truncate count must be an integer")
        count = int(count)
        if not 0 <= count <= self._total_count:
            raise ValueError("event truncate count is outside the sequence")
        if count >= self._archived_count:
            del self._tail[count - self._archived_count:]
            self._total_count = count
            return
        retained = [self._event_at(index) for index in range(count)]
        self._reset()
        for event in retained:
            self.append(event)

    def replace_all(self, values: Iterable[dict[str, Any]]) -> None:
        replacement = list(values)
        self._reset()
        for value in replacement:
            self.append(value)

    def __len__(self) -> int:
        return self._total_count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for _digest, document in self._chain(newest_first=False):
            yield from document["events"]
        yield from self._tail

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EventSequence):
            return list(self) == list(other)
        if isinstance(other, Sequence):
            return list(self) == list(other)
        return NotImplemented

    def to_state(self) -> dict[str, Any]:
        return {
            "archived_count": self._archived_count,
            "chunk_count": self._chunk_count,
            "chunk_head_sha256": self._chunk_head_sha256,
            "chunk_size": self.chunk_size,
            "tail": list(self._tail),
            "tail_limit": self.tail_limit,
            "total_count": self._total_count,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "EventSequence":
        if not isinstance(state, dict) or set(state) != {
            "archived_count", "chunk_count", "chunk_head_sha256",
            "chunk_size", "tail", "tail_limit", "total_count",
        }:
            raise ValueError("event sequence state fields are invalid")
        return cls(
            archived_count=state["archived_count"],
            chunk_count=state["chunk_count"],
            chunk_head_sha256=state["chunk_head_sha256"],
            chunk_size=state["chunk_size"],
            tail=state["tail"],
            tail_limit=state["tail_limit"],
            total_count=state["total_count"],
        )


class EventStream:
    def __init__(
        self,
        events: Iterable[dict[str, Any]] = (),
        _head_hash: str = EMPTY_EVENT_HEAD,
        *,
        chunk_size: int = DEFAULT_EVENT_CHUNK_SIZE,
        tail_limit: int = DEFAULT_EVENT_TAIL_LIMIT,
    ) -> None:
        self.events = EventSequence(
            events, chunk_size=chunk_size, tail_limit=tail_limit,
        )
        self._head_hash = _head_hash

    @property
    def head_hash(self) -> str:
        return self._head_hash

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def retained_event_count(self) -> int:
        return self.events.retained_count

    @property
    def chunk_digests(self) -> tuple[str, ...]:
        return self.events.chunk_digests

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
        seq = self.event_count
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
            if event.get("global_sequence") != seq \
                    or event.get("event_id") != f"evt:{seq:012d}":
                raise ValueError(f"event sequence mismatch at index {seq}")
            expected = hashlib.sha256(
                bytes.fromhex(expected) + canonical_json(event).encode("utf-8")
            ).hexdigest()
        if expected != self._head_hash:
            raise ValueError("event head hash does not match the event prefix")

    def input_events(self) -> list[dict[str, Any]]:
        return [
            event for event in self.events
            if event["replay_class"] == "input"
        ]

    def canonical_bytes(self) -> bytes:
        return canonical_json(list(self.events)).encode("utf-8")

    def to_state(self) -> dict[str, Any]:
        return {
            "events": self.events.to_state(),
            "head_hash": self._head_hash,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "EventStream":
        if not isinstance(state, dict) or set(state) != {
            "events", "head_hash",
        }:
            raise ValueError("event stream state fields are invalid")
        stream = cls(_head_hash=state["head_hash"])
        stream.events = EventSequence.from_state(state["events"])
        stream.verify()
        return stream
