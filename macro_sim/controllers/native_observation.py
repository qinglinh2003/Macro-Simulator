"""Release-safe observation source backed by committed native metric frames.

This adapter intentionally contains no economic calculations.  C++ owns every
source value and the bounded history ring; Python retains the M10 publication
calendar, institutional visibility, vintage, and revision contracts.  That
division is the planned M10 bridge before M11 moves publication state into the
standalone native controlled session.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any, Mapping


_ECONOMY_PREFIX = "metric.economy."
_WORLD_PREFIX = "metric.world."
_SHOCK_PREFIX = "metric.shock."


@dataclass(slots=True)
class _EconomyRecordView:
    records: list[dict[str, Any]]


class NativeObservationSource:
    """Project C++ metric history into the read-only ReleaseService protocol."""

    def __init__(self, session: Any) -> None:
        if not callable(getattr(session, "history_page", None)):
            raise TypeError("native observation source requires history_page()")
        economy_count = int(getattr(session.bridge, "economy_count"))
        if economy_count <= 0:
            raise ValueError("native observation source requires an economy")
        self._session = session
        self.economies = tuple(
            _EconomyRecordView([]) for _ in range(economy_count)
        )
        self.world_records: list[dict[str, Any]] = []
        self._shock_frames: dict[int, tuple[dict[str, float], ...]] = {}
        self._next_sequence = 0
        self._last_frame_tick = -1
        self.refresh()

    @property
    def boundary_tick(self) -> int:
        return int(self._session.tick)

    @staticmethod
    def _finite_scalar(name: str, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a numeric native metric")
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            raise ValueError(f"{name} must be finite")
        return result

    def _ingest_frame(self, frame: Mapping[str, Any]) -> None:
        raw_tick = frame.get("tick")
        if isinstance(raw_tick, bool) or not isinstance(raw_tick, Integral):
            raise TypeError("native metric frame tick must be an integer")
        boundary_tick = int(raw_tick)
        if boundary_tick <= self._last_frame_tick:
            raise ValueError("native metric history is not strictly ordered")
        rows = frame.get("economies")
        if not isinstance(rows, (list, tuple)) or len(rows) != len(self.economies):
            raise ValueError("native metric frame economy shape drifted")

        shock_rows: list[dict[str, float]] = []
        economy_rows: list[dict[str, Any]] = []
        world_values: dict[str, list[float | None]] = {}
        for economy_id, raw_values in enumerate(rows):
            if not isinstance(raw_values, Mapping):
                raise TypeError("native metric economy row must be a mapping")
            economy_record: dict[str, Any] = {"t": boundary_tick - 1}
            shocks: dict[str, float] = {}
            for stable_id, raw_value in raw_values.items():
                if not isinstance(stable_id, str):
                    raise TypeError("native metric stable ID must be a string")
                if raw_value is None:
                    value = None
                else:
                    value = self._finite_scalar(stable_id, raw_value)
                if stable_id.startswith(_ECONOMY_PREFIX):
                    if boundary_tick > 0 and value is not None:
                        economy_record[
                            stable_id[len(_ECONOMY_PREFIX):]
                        ] = value
                elif stable_id.startswith(_WORLD_PREFIX):
                    source_key = stable_id[len(_WORLD_PREFIX):]
                    target = world_values.setdefault(
                        source_key, [None] * len(self.economies)
                    )
                    target[economy_id] = value
                elif stable_id.startswith(_SHOCK_PREFIX):
                    if value is not None:
                        shocks[stable_id[len(_SHOCK_PREFIX):]] = value
                else:
                    raise ValueError(
                        f"unknown native metric namespace {stable_id!r}"
                    )
            economy_rows.append(economy_record)
            shock_rows.append(shocks)

        # The tick-zero frame is a boundary snapshot, not a completed economic
        # record.  It is still retained for announcement-time shock disclosure.
        if boundary_tick > 0:
            for view, row in zip(self.economies, economy_rows, strict=True):
                view.records.append(row)
            world_row: dict[str, Any] = {"t": boundary_tick - 1}
            world_row.update(world_values)
            self.world_records.append(world_row)
        self._shock_frames[boundary_tick] = tuple(shock_rows)
        self._last_frame_tick = boundary_tick

    def refresh(self) -> None:
        """Consume every newly committed native frame exactly once."""
        while True:
            page = self._session.history_page(self._next_sequence, 256)
            frames = page.get("frames")
            if not isinstance(frames, (list, tuple)):
                raise TypeError("native metric history page has no frame list")
            for frame in frames:
                if not isinstance(frame, Mapping):
                    raise TypeError("native metric history frame must be a mapping")
                self._ingest_frame(frame)
            next_sequence = page.get("next_sequence")
            if isinstance(next_sequence, bool) or not isinstance(
                next_sequence, Integral
            ):
                raise TypeError("native metric history cursor must be an integer")
            checked_next = int(next_sequence)
            if checked_next < self._next_sequence:
                raise ValueError("native metric history cursor moved backward")
            progressed = checked_next > self._next_sequence
            self._next_sequence = checked_next
            if not progressed or len(frames) < 256:
                break

    def native_shock_observable(
        self, key: str, economy_id: int, as_of_tick: int,
        *, role: str = "public",
    ) -> float:
        """Return only the native disclosure scalar available at this boundary."""
        del role  # Native frame already enforces announcement-time disclosure.
        self.refresh()
        if not 0 <= economy_id < len(self.economies):
            raise IndexError(f"economy_id {economy_id} out of range")
        eligible = [
            boundary for boundary in self._shock_frames
            if boundary <= int(as_of_tick)
        ]
        if not eligible:
            return 0.0
        frame = self._shock_frames[max(eligible)][economy_id]
        try:
            return float(frame[key])
        except KeyError as exc:
            raise KeyError(f"unknown native shock observable {key!r}") from exc

    def native_shock_bulletins(
        self, economy_id: int, as_of_tick: int, *, role: str = "public",
    ) -> tuple[dict[str, Any], ...]:
        """Return typed bulletins once the C++ probe surface supplies them.

        Numeric context features are already authoritative and release-safe.
        The empty tuple avoids fabricating prose or future tape details while the
        typed M10 shock bulletin probe is implemented.
        """
        del as_of_tick, role
        if not 0 <= economy_id < len(self.economies):
            raise IndexError(f"economy_id {economy_id} out of range")
        return ()
