"""Deterministic institutional calendars and hysteretic emergency triggers."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class CalendarSpec:
    period_ticks: int
    offset_ticks: int = 0
    window_ticks: int = 1
    admin_capacity: float = 20.0

    def __post_init__(self) -> None:
        for name in ("period_ticks", "offset_ticks", "window_ticks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"calendar {name} must be an integer")
        if self.period_ticks <= 0 or self.window_ticks <= 0:
            raise ValueError("calendar period and window must be positive")
        if self.window_ticks > self.period_ticks:
            raise ValueError("calendar window cannot overlap the next period")
        if not 0 <= self.offset_ticks < self.period_ticks:
            raise ValueError("calendar offset must be inside the period")
        if isinstance(self.admin_capacity, bool) or not isinstance(
            self.admin_capacity, (int, float)
        ) or not math.isfinite(float(self.admin_capacity)):
            raise ValueError("admin capacity must be a finite number")
        if self.admin_capacity < 0:
            raise ValueError("admin capacity must be non-negative")

    def due(self, tick: int) -> bool:
        return tick >= self.offset_ticks and (tick - self.offset_ticks) % self.period_ticks == 0


DEFAULT_CALENDARS: dict[str, CalendarSpec] = {
    "monetary_stance": CalendarSpec(45, admin_capacity=12),
    "liquidity_operations": CalendarSpec(45, admin_capacity=10),
    "fiscal_stance": CalendarSpec(91, admin_capacity=18),
    "tax_and_transfers": CalendarSpec(365, admin_capacity=25),
    "debt_management": CalendarSpec(91, admin_capacity=12),
    "macroprudential": CalendarSpec(91, admin_capacity=20),
    "structural_law": CalendarSpec(365, admin_capacity=30),
    "trade_and_migration": CalendarSpec(91, admin_capacity=18),
    "fx_operations": CalendarSpec(45, admin_capacity=12),
    "energy_operations": CalendarSpec(91, admin_capacity=16),
    "energy_structure": CalendarSpec(365, admin_capacity=20),
}


@dataclass(frozen=True)
class TriggerSpec:
    trigger_id: str
    series_id: str
    enter_threshold: float
    exit_threshold: float
    direction: str = "above"
    min_persist_ticks: int = 1
    cooldown_ticks: int = 30
    context_expiry_ticks: int = 1
    authorized_seats: tuple[str, ...] = ()
    decision_group: str = "emergency"

    def __post_init__(self) -> None:
        if not self.trigger_id or not self.series_id or not self.decision_group:
            raise ValueError("trigger id, series id, and decision group are required")
        if self.direction not in {"above", "below"}:
            raise ValueError("trigger direction must be above or below")
        for name in ("min_persist_ticks", "cooldown_ticks", "context_expiry_ticks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"trigger {name} must be an integer")
        if self.min_persist_ticks <= 0 or self.cooldown_ticks < 0 \
                or self.context_expiry_ticks <= 0:
            raise ValueError("invalid trigger persistence/cooldown")
        thresholds = (self.enter_threshold, self.exit_threshold)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(float(value)) for value in thresholds):
            raise ValueError("trigger thresholds must be finite numbers")
        if self.direction == "above" and self.enter_threshold <= self.exit_threshold:
            raise ValueError("above trigger requires enter_threshold > exit_threshold")
        if self.direction == "below" and self.enter_threshold >= self.exit_threshold:
            raise ValueError("below trigger requires enter_threshold < exit_threshold")
        seats = tuple(self.authorized_seats)
        if not seats or any(not isinstance(seat, str) or not seat for seat in seats):
            raise ValueError("trigger requires non-empty authorized seats")
        if len(seats) != len(set(seats)):
            raise ValueError("trigger authorized seats must be unique")
        object.__setattr__(self, "authorized_seats", seats)


@dataclass
class TriggerState:
    active: bool = False
    persist_ticks: int = 0
    cooldown_until: int = -1


@dataclass(frozen=True)
class TriggerNotice:
    trigger_id: str
    economy_id: int
    seats: tuple[str, ...]
    decision_group: str
    expires_at_tick: int
    value: float


DEFAULT_TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(
        "bank_liquidity_stress", "reserve_floor_breach_share",
        enter_threshold=0.10, exit_threshold=0.02,
        min_persist_ticks=2, cooldown_ticks=30,
        authorized_seats=("central_bank", "regulator"),
    ),
    TriggerSpec(
        "bank_capital_stress", "near_failure_bank_count",
        enter_threshold=0.5, exit_threshold=0.0,
        min_persist_ticks=1, cooldown_ticks=30,
        authorized_seats=("central_bank", "regulator"),
    ),
    TriggerSpec(
        "energy_shortage", "energy_unfilled",
        enter_threshold=1.0, exit_threshold=0.1,
        min_persist_ticks=2, cooldown_ticks=14,
        authorized_seats=("energy", "treasury"),
    ),
)


@dataclass
class DecisionScheduler:
    calendars: dict[str, CalendarSpec] = field(default_factory=lambda: dict(DEFAULT_CALENDARS))
    triggers: tuple[TriggerSpec, ...] = DEFAULT_TRIGGERS
    economy_offsets: dict[tuple[int, str], int] = field(default_factory=dict)
    trigger_states: dict[tuple[int, str], TriggerState] = field(default_factory=dict)
    last_context_tick: dict[tuple[int, str, str], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if any(not isinstance(name, str) or not name for name in self.calendars):
            raise ValueError("calendar decision-group names must be non-empty strings")
        if not all(isinstance(spec, CalendarSpec) for spec in self.calendars.values()):
            raise TypeError("calendar values must be CalendarSpec")
        self.triggers = tuple(self.triggers)
        if not all(isinstance(spec, TriggerSpec) for spec in self.triggers):
            raise TypeError("triggers must contain TriggerSpec values")
        ids = [spec.trigger_id for spec in self.triggers]
        if len(ids) != len(set(ids)):
            raise ValueError("trigger ids must be unique")

    def calendar_for(self, decision_group: str) -> CalendarSpec:
        return self.calendars.get(decision_group, CalendarSpec(91))

    def due(self, decision_group: str, tick: int, *, economy_id: int = 0) -> bool:
        calendar = self.calendar_for(decision_group)
        extra = self.economy_offsets.get((economy_id, decision_group), 0)
        offset = (calendar.offset_ticks + extra) % calendar.period_ticks
        return tick >= offset and (tick - offset) % calendar.period_ticks == 0

    def evaluate_triggers(
        self,
        boundary_tick: int,
        economy_id: int,
        metrics: Mapping[str, Any],
    ) -> list[TriggerNotice]:
        notices: list[TriggerNotice] = []
        for spec in sorted(self.triggers, key=lambda item: item.trigger_id):
            raw = metrics.get(spec.series_id)
            key = (economy_id, spec.trigger_id)
            state = self.trigger_states.setdefault(key, TriggerState())
            if raw is None or isinstance(raw, bool):
                if not state.active:
                    state.persist_ticks = 0
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                if not state.active:
                    state.persist_ticks = 0
                continue
            if not math.isfinite(value):
                if not state.active:
                    state.persist_ticks = 0
                continue
            entering = value >= spec.enter_threshold if spec.direction == "above" \
                else value <= spec.enter_threshold
            exiting = value <= spec.exit_threshold if spec.direction == "above" \
                else value >= spec.exit_threshold
            if state.active:
                if exiting:
                    state.active = False
                    state.persist_ticks = 0
                continue
            if entering:
                state.persist_ticks += 1
            else:
                state.persist_ticks = 0
            if state.persist_ticks >= spec.min_persist_ticks and boundary_tick >= state.cooldown_until:
                state.active = True
                state.persist_ticks = 0
                state.cooldown_until = boundary_tick + spec.cooldown_ticks
                notices.append(TriggerNotice(
                    trigger_id=spec.trigger_id,
                    economy_id=economy_id,
                    seats=tuple(sorted(spec.authorized_seats)),
                    decision_group=spec.decision_group,
                    expires_at_tick=boundary_tick + spec.context_expiry_ticks,
                    value=value,
                ))
        return notices
