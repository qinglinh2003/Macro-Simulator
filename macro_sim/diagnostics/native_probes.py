"""Privileged diagnostics over the stable native M10 probe contract.

These adapters deliberately know nothing about C++ store layout.  They consume
only committed, typed probe pages from :class:`NativeSimulationSession`, so
diagnostic code cannot accidentally mutate the engine or retain raw pointers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_ENTITY_KINDS = frozenset({
    "households", "firms", "banks", "persons", "jobs", "dwellings",
})


@dataclass(frozen=True, slots=True)
class NativeDiagnosticSnapshot:
    boundary: int
    economy_id: int
    aggregates: Mapping[str, int | float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "economy_id": self.economy_id,
            "aggregates": dict(self.aggregates),
        }


class NativeDeepProbeCollector:
    """Collect immutable aggregate and entity probes at a committed boundary."""

    def collect(
        self, session: Any, economy_id: int = 0,
    ) -> NativeDiagnosticSnapshot:
        raw = session.probe_economy_diagnostics(economy_id)
        boundary = int(raw.pop("boundary"))
        returned_economy = int(raw.pop("economy_id"))
        if returned_economy != economy_id:
            raise RuntimeError("native diagnostic probe economy drifted")
        return NativeDiagnosticSnapshot(
            boundary=boundary,
            economy_id=returned_economy,
            aggregates=raw,
        )

    @staticmethod
    def entity_page(
        session: Any, kind: str, *, economy_id: int = 0,
        after_id: int = 0, maximum_rows: int = 256,
    ) -> dict[str, Any]:
        if kind not in _ENTITY_KINDS:
            raise ValueError(f"unknown native diagnostic entity kind {kind!r}")
        return session.probe_page(
            kind,
            economy_id=economy_id,
            after_id=after_id,
            maximum_rows=maximum_rows,
        )


class NativeWorldProbeCollector:
    """Capture typed pre/post decompositions around one native World boundary."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.deep = NativeDeepProbeCollector()
        self.records: list[dict[str, Any]] = []

    def step(self, *, actions=()) -> dict[str, Any]:
        economy_count = int(self.session.bridge.economy_count)
        before = tuple(
            self.deep.collect(self.session, economy_id).to_dict()
            for economy_id in range(economy_count)
        )
        result = self.session.advance(actions=actions)
        after = tuple(
            self.deep.collect(self.session, economy_id).to_dict()
            for economy_id in range(economy_count)
        )
        record = {
            "first_tick": int(result["first_tick"]),
            "next_tick": int(result["next_tick"]),
            "engine_digest": int(result["digest"]),
            "before": before,
            "after": after,
            "public_metrics": self.session.public_metrics(),
        }
        self.records.append(record)
        return record
