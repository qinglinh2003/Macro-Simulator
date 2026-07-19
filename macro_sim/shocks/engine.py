"""Deterministic realization engine for semantic exogenous shocks."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Iterable, Mapping, Sequence

from .registry import DEFAULT_SHOCK_REGISTRY, ShockRegistry
from .spec import ShockSpec, ShockTape, ShockTarget, canonical_json, normalize_sector


EMPTY_SHOCK_EVENT_HEAD = hashlib.sha256(b"").hexdigest()


def sector_for_firm(firm: Any) -> str:
    detailed = getattr(firm, "consumption_sector", "")
    if detailed:
        return normalize_sector(detailed)
    return normalize_sector(getattr(firm, "sells", "consumption"))


def read_shock_factor(
    econ: Any,
    channel: str,
    *,
    firm: Any | None = None,
    sector: str | None = None,
) -> float:
    """Read an economic shock overlay, defaulting to the exact identity.

    System functions are deliberately usable with small economy-shaped test and
    downstream objects, not only with :class:`macro_sim.economy.Economy`. Those
    objects predate the v27 convenience method and represent an economy with no
    attached shock engine. Keep that historical contract explicit here instead
    of scattering ``getattr`` fallbacks across every economic coupling seam.
    """
    reader = getattr(econ, "shock_factor", None)
    if callable(reader):
        if firm is not None:
            return float(reader(channel, firm=firm))
        if sector is not None:
            return float(reader(channel, sector=sector))
        return float(reader(channel))

    engine = getattr(econ, "shock_engine", None)
    if engine is None:
        return 1.0
    if firm is not None:
        sector = sector_for_firm(firm)
    return float(engine.factor(channel, int(getattr(econ, "economy_id", 0)), sector))


@dataclass
class ShockEventStream:
    events: list[dict[str, Any]] = field(default_factory=list)
    _head_hash: str = EMPTY_SHOCK_EVENT_HEAD

    @property
    def head_hash(self) -> str:
        return self._head_hash

    def append(
        self, event_type: str, tick: int, spec: ShockSpec, *, payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        sequence = len(self.events)
        event = {
            "schema_version": 1,
            "sequence": sequence,
            "event_id": f"shock-event:{sequence:012d}",
            "event_type": event_type,
            "tick": int(tick),
            "shock_id": spec.shock_id,
            "kind": spec.kind,
            "economy_ids": (
                None if spec.target.economy_ids is None else list(spec.target.economy_ids)
            ),
            "payload": dict(payload or {}),
        }
        # Round-trip through canonical JSON rejects accidental non-JSON state now,
        # before it can poison a checkpoint or replay tape.
        encoded = canonical_json(event)
        self._head_hash = hashlib.sha256(
            bytes.fromhex(self._head_hash) + encoded.encode("utf-8")
        ).hexdigest()
        self.events.append(event)
        return event

    def verify(self) -> None:
        head = EMPTY_SHOCK_EVENT_HEAD
        for sequence, event in enumerate(self.events):
            if event.get("sequence") != sequence \
                    or event.get("event_id") != f"shock-event:{sequence:012d}":
                raise ValueError(f"shock event sequence mismatch at {sequence}")
            head = hashlib.sha256(
                bytes.fromhex(head) + canonical_json(event).encode("utf-8")
            ).hexdigest()
        if head != self._head_hash:
            raise ValueError("shock event head hash does not match its event prefix")


class ShockEngine:
    """Checkpoint-safe state machine over a concrete :class:`ShockTape`.

    The engine owns no references to the simulated world.  ``bind`` records only
    immutable structural facts, while ``begin_tick`` receives the live economies.
    This keeps policy transaction projections and ordinary pickle checkpoints safe.
    """

    def __init__(
        self,
        tape: ShockTape | Iterable[ShockSpec] | None = None,
        *,
        registry: ShockRegistry = DEFAULT_SHOCK_REGISTRY,
    ) -> None:
        if not isinstance(registry, ShockRegistry):
            raise TypeError("registry must be a ShockRegistry")
        self.registry = registry
        initial = ShockTape.coerce(tape)
        self._specs: dict[str, ShockSpec] = {item.shock_id: item for item in initial.specs}
        self.initial_tape_hash = initial.contract_hash
        self.current_tick = -1
        self._bound_signature: tuple[tuple[int, ...], bool] | None = None
        self._announced: set[str] = set()
        self._active: set[str] = set()
        self._realized: set[str] = set()
        self.events = ShockEventStream()

    @property
    def specs(self) -> tuple[ShockSpec, ...]:
        return tuple(sorted(
            self._specs.values(), key=lambda item: (item.start_tick, item.shock_id),
        ))

    @property
    def tape(self) -> ShockTape:
        return ShockTape(self.specs, name="runtime_shock_tape")

    @property
    def contract_hash(self) -> str:
        return self.tape.contract_hash

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    def is_active(self, kind: str, economy_id: int) -> bool:
        self.registry[kind]
        return any(
            self._specs[shock_id].kind == kind
            and self._specs[shock_id].target.matches_economy(int(economy_id))
            for shock_id in self._active
        )

    @staticmethod
    def _economy_pairs(economies: Sequence[Any]) -> tuple[tuple[int, Any], ...]:
        pairs = tuple(
            (int(getattr(economy, "economy_id", index)), economy)
            for index, economy in enumerate(economies)
        )
        ids = [item[0] for item in pairs]
        if len(ids) != len(set(ids)):
            raise ValueError("shock engine economy ids must be unique")
        return tuple(sorted(pairs, key=lambda item: item[0]))

    def bind(self, economies: Sequence[Any], *, world: Any | None = None) -> None:
        pairs = self._economy_pairs(economies)
        signature = (tuple(item[0] for item in pairs), bool(getattr(world, "trade", False)))
        if self._bound_signature is not None and self._bound_signature != signature:
            raise ValueError("a ShockEngine cannot be rebound to a different engine topology")
        for spec in self.specs:
            self._validate_bound_spec(spec, pairs, world=world)
        self._bound_signature = signature

    def _validate_bound_spec(
        self, spec: ShockSpec, pairs: tuple[tuple[int, Any], ...], *, world: Any | None,
    ) -> None:
        self.registry.validate_spec(spec)
        by_id = dict(pairs)
        targets = tuple(by_id) if spec.target.economy_ids is None else spec.target.economy_ids
        unknown = sorted(set(targets) - set(by_id))
        if unknown:
            raise ValueError(f"shock {spec.shock_id!r} targets unknown economies {unknown}")
        definition = self.registry[spec.kind]
        for economy_id in targets:
            econ = by_id[economy_id]
            if definition.required_capability == "world_trade" \
                    and not bool(getattr(world, "trade", False)):
                raise ValueError(f"shock {spec.shock_id!r} requires an enabled World trade layer")
            if definition.required_capability == "energy_enabled" \
                    and not bool(getattr(econ.cfg, "energy_enabled", False)):
                raise ValueError(
                    f"shock {spec.shock_id!r} requires energy_enabled in economy {economy_id}"
                )
            if definition.required_capability == "bank_enabled" \
                    and not bool(getattr(econ.cfg, "bank_enabled", False)):
                raise ValueError(
                    f"shock {spec.shock_id!r} requires bank_enabled in economy {economy_id}"
                )
            if "energy" in spec.target.sectors \
                    and not bool(getattr(econ.cfg, "energy_enabled", False)):
                raise ValueError(
                    f"shock {spec.shock_id!r} targets a missing energy sector in economy {economy_id}"
                )

    def schedule(
        self,
        spec: ShockSpec,
        *,
        economies: Sequence[Any],
        world: Any | None = None,
        boundary_tick: int | None = None,
    ) -> None:
        """Atomically append a concrete future event to a live tape."""
        if not isinstance(spec, ShockSpec):
            raise TypeError("scheduled shock must be a ShockSpec")
        if spec.shock_id in self._specs:
            raise ValueError(f"duplicate shock id {spec.shock_id!r}")
        boundary = self.current_tick + 1 if boundary_tick is None else int(boundary_tick)
        if spec.start_tick < boundary:
            raise ValueError("a live shock cannot be scheduled in the past")
        if spec.announcement_tick < boundary:
            raise ValueError("a live shock announcement cannot be backdated")
        pairs = self._economy_pairs(economies)
        signature = (tuple(item[0] for item in pairs), bool(getattr(world, "trade", False)))
        if self._bound_signature is not None and self._bound_signature != signature:
            raise ValueError("scheduled shock topology differs from the bound engine")
        self._validate_bound_spec(spec, pairs, world=world)
        # All raisable work is complete.  The single mapping write is the commit.
        self._specs[spec.shock_id] = spec

    def _continuous_factor(
        self, channel: str, economy_id: int, sector: str | None, tick: int,
    ) -> float:
        result = 1.0
        for spec in sorted(self._specs.values(), key=lambda item: item.shock_id):
            definition = self.registry[spec.kind]
            if definition.one_shot or definition.channel != channel:
                continue
            if not spec.target.matches_economy(economy_id) \
                    or not spec.target.matches_sector(sector):
                continue
            intensity = spec.intensity_at(tick)
            if intensity <= 0.0:
                continue
            result *= 1.0 - spec.magnitude * intensity
        return result

    def factor(self, channel: str, economy_id: int = 0, sector: str | None = None) -> float:
        channels = {definition.channel for _kind, definition in self.registry.items()}
        if channel not in channels:
            raise ValueError(f"unknown shock channel {channel!r}")
        if self.current_tick < 0:
            return 1.0
        return self._continuous_factor(channel, int(economy_id), sector, self.current_tick)

    def _prepare_capital_losses(
        self, tick: int, pairs: tuple[tuple[int, Any], ...], specs: tuple[ShockSpec, ...],
    ) -> tuple[list[tuple[Any, float]], list[tuple[Any, float]], dict[int, float]]:
        private_changes: list[tuple[Any, float]] = []
        public_changes: list[tuple[Any, float]] = []
        destroyed: dict[int, float] = {economy_id: 0.0 for economy_id, _ in pairs}
        for economy_id, econ in pairs:
            applicable = tuple(
                item for item in specs if item.target.matches_economy(economy_id)
            )
            if not applicable:
                continue
            for firm in sorted(getattr(econ, "firms", ()), key=lambda item: item.id):
                sector = sector_for_firm(firm)
                survival = 1.0
                for spec in applicable:
                    if spec.target.matches_sector(sector):
                        survival *= 1.0 - spec.magnitude
                if survival != 1.0 and float(getattr(firm, "capital", 0.0)) > 0.0:
                    opening = float(firm.capital)
                    closing = max(0.0, opening * survival)
                    private_changes.append((firm, closing))
                    destroyed[economy_id] += opening - closing
            public_survival = 1.0
            for spec in applicable:
                if not spec.target.sectors or "public" in spec.target.sectors:
                    public_survival *= 1.0 - spec.magnitude
            opening_public = float(getattr(econ, "public_capital", 0.0))
            if public_survival != 1.0 and opening_public > 0.0:
                closing_public = max(0.0, opening_public * public_survival)
                public_changes.append((econ, closing_public))
                destroyed[economy_id] += opening_public - closing_public
        return private_changes, public_changes, destroyed

    def begin_tick(
        self, tick: int, economies: Sequence[Any], *, world: Any | None = None,
    ) -> None:
        """Prepare and commit all exogenous transitions for one engine tick.

        Every validation and composition-bound check precedes the first mutation of
        either the economic state or this state machine.
        """
        tick = int(tick)
        pairs = self._economy_pairs(economies)
        if self._bound_signature is None:
            self.bind(economies, world=world)
        expected_signature = (
            tuple(item[0] for item in pairs), bool(getattr(world, "trade", False)),
        )
        if self._bound_signature != expected_signature:
            raise ValueError("ShockEngine tick topology differs from its bound topology")
        if tick == self.current_tick:
            return
        if tick != self.current_tick + 1:
            raise ValueError(
                f"shock ticks must be consecutive: got {tick}, expected {self.current_tick + 1}"
            )

        new_active = {
            spec.shock_id for spec in self.specs
            if not self.registry[spec.kind].one_shot and spec.intensity_at(tick) > 0.0
        }
        one_shots = tuple(
            spec for spec in self.specs
            if self.registry[spec.kind].one_shot
            and spec.start_tick == tick and spec.shock_id not in self._realized
        )
        announcements = tuple(
            spec for spec in self.specs
            if spec.announcement_tick <= tick and spec.shock_id not in self._announced
        )

        # Check every composed continuous factor.  The generous upper bound protects
        # against accidental explosive stacking while allowing favorable scenarios.
        for economy_id, _econ in pairs:
            for _kind, definition in self.registry.items():
                if definition.one_shot:
                    continue
                sectors: tuple[str | None, ...] = (None,) + tuple(sorted(definition.allowed_sectors))
                for sector in sectors:
                    factor = self._continuous_factor(definition.channel, economy_id, sector, tick)
                    if not math.isfinite(factor) or not 0.0 < factor <= 64.0:
                        raise ValueError(
                            f"shock composition produced invalid {definition.channel} factor "
                            f"{factor} for economy {economy_id}, sector {sector}"
                        )

        capital_specs = tuple(item for item in one_shots if item.kind == "capital_destruction")
        private_changes, public_changes, destroyed = self._prepare_capital_losses(
            tick, pairs, capital_specs,
        )

        # COMMIT -- everything below is infallible assignment/canonical event append.
        for firm, closing in private_changes:
            firm.capital = closing
        for econ, closing in public_changes:
            econ.public_capital = closing

        old_active = set(self._active)
        self.current_tick = tick
        self._active = new_active
        self._realized.update(item.shock_id for item in one_shots)
        self._announced.update(item.shock_id for item in announcements)

        for spec in sorted(announcements, key=lambda item: (item.announcement_tick, item.shock_id)):
            self.events.append(
                "announced", int(spec.announcement_tick), spec,
                payload={"spec": spec.to_dict(), "contract_hash": self.contract_hash},
            )
        for shock_id in sorted(old_active - new_active):
            spec = self._specs[shock_id]
            self.events.append("ended", tick, spec)
        for shock_id in sorted(new_active - old_active):
            spec = self._specs[shock_id]
            self.events.append(
                "started", tick, spec,
                payload={"intensity": spec.intensity_at(tick)},
            )
        for spec in sorted(one_shots, key=lambda item: item.shock_id):
            self.events.append("realized", tick, spec)

        for economy_id, econ in pairs:
            active_here = [
                self._specs[item] for item in sorted(new_active)
                if self._specs[item].target.matches_economy(economy_id)
            ]
            realized_here = [
                item for item in one_shots
                if item.target.matches_economy(economy_id)
            ]
            econ._shock_active_count = float(len(active_here) + len(realized_here))
            econ._shock_max_intensity = max(
                [item.intensity_at(tick) for item in active_here]
                + [1.0 for _item in realized_here], default=0.0,
            )
            econ._shock_capital_destroyed_tick = float(destroyed.get(economy_id, 0.0))
            econ._energy_shock_active = float(any(
                item.kind == "energy_capacity" for item in active_here
            ))
            channel_factors = {}
            for _kind, definition in self.registry.items():
                if definition.one_shot:
                    continue
                candidates = [self.factor(definition.channel, economy_id)]
                candidates.extend(
                    self.factor(definition.channel, economy_id, sector)
                    for sector in sorted(definition.allowed_sectors)
                )
                channel_factors[definition.channel] = max(
                    candidates, key=lambda value: abs(value - 1.0),
                )
            econ._shock_channel_factors = channel_factors

    def _relevant_disclosed(
        self, economy_id: int, as_of_tick: int, role: str,
    ) -> tuple[ShockSpec, ...]:
        relevant = []
        for spec in self.specs:
            if not spec.target.matches_economy(economy_id):
                continue
            if spec.announcement_tick > as_of_tick or not spec.permits(role):
                continue
            definition = self.registry[spec.kind]
            if definition.one_shot:
                if spec.start_tick < as_of_tick:
                    continue
            elif spec.end_tick is not None and spec.end_tick <= as_of_tick:
                continue
            relevant.append(spec)
        return tuple(relevant)

    def bulletins(
        self, economy_id: int, as_of_tick: int, *, role: str = "public",
    ) -> tuple[dict[str, Any], ...]:
        """Return only information disclosed by this simulation boundary."""
        rows: list[dict[str, Any]] = []
        for spec in self._relevant_disclosed(int(economy_id), int(as_of_tick), role):
            definition = self.registry[spec.kind]
            if as_of_tick < spec.start_tick:
                status = "upcoming"
                intensity = 0.0
            elif definition.one_shot:
                status = "realizing"
                intensity = 1.0
            else:
                status = "active"
                intensity = spec.intensity_at(as_of_tick)
            rows.append({
                "announcement_tick": spec.announcement_tick,
                "calibration_note": spec.calibration_note,
                "correlation_group": spec.correlation_group,
                "duration_ticks": spec.duration_ticks,
                "expected_end_tick": spec.end_tick,
                "intensity": intensity,
                "kind": spec.kind,
                "magnitude": spec.magnitude,
                "shock_id": spec.shock_id,
                "source": spec.source,
                "start_tick": spec.start_tick,
                "status": status,
                "tags": list(spec.tags),
                "target": spec.target.to_dict(),
                "visibility": spec.visibility,
            })
        return tuple(sorted(rows, key=lambda item: (item["start_tick"], item["shock_id"])))

    def observable(
        self, key: str, economy_id: int, as_of_tick: int, *, role: str = "public",
    ) -> float:
        relevant = self._relevant_disclosed(int(economy_id), int(as_of_tick), role)
        active = [
            item for item in relevant
            if item.start_tick <= as_of_tick and (
                self.registry[item.kind].one_shot or item.intensity_at(as_of_tick) > 0.0
            )
        ]
        if key == "announced_count":
            return float(len(relevant))
        if key == "active_count":
            return float(len(active))
        if key == "max_severity":
            return max((max(0.0, item.magnitude) * (
                1.0 if self.registry[item.kind].one_shot else item.intensity_at(as_of_tick)
            ) for item in active), default=0.0)
        if key == "time_to_next":
            return float(min((max(0, item.start_tick - as_of_tick) for item in relevant), default=0))
        if key.startswith("severity."):
            kind = key.split(".", 1)[1]
            self.registry[kind]
            candidates = [item for item in relevant if item.kind == kind]
            return max((
                max(0.0, item.magnitude) * (
                    1.0 if item.start_tick > as_of_tick else (
                        1.0 if self.registry[item.kind].one_shot
                        else item.intensity_at(as_of_tick)
                    )
                )
                for item in candidates
            ), default=0.0)
        raise KeyError(f"unknown shock observable {key!r}")

    def trigger_metrics(
        self, economy_id: int, as_of_tick: int, *, role: str = "public",
    ) -> dict[str, float]:
        def active_severity(kind: str) -> float:
            values = []
            for item in self._relevant_disclosed(economy_id, as_of_tick, role):
                if item.kind != kind or item.start_tick > as_of_tick:
                    continue
                intensity = 1.0 if self.registry[kind].one_shot else item.intensity_at(as_of_tick)
                values.append(max(0.0, item.magnitude) * intensity)
            return max(values, default=0.0)

        productivity = active_severity("productivity")
        labor = active_severity("labor_availability")
        capital = active_severity("capital_destruction")
        return {
            "shock_supply_severity": max(productivity, labor, capital),
            "shock_energy_severity": active_severity("energy_capacity"),
            "shock_financial_severity": active_severity("credit_supply"),
            "shock_trade_severity": max(
                active_severity("import_capacity"), active_severity("export_capacity"),
            ),
            "shock_demand_severity": active_severity("household_demand"),
        }


def legacy_energy_spec(cfg: Any, *, economy_id: int | None = None) -> ShockSpec | None:
    """Translate the v17 Config scenario into the v27 semantic contract."""
    start = int(getattr(cfg, "energy_shock_at", 0))
    if start <= 0:
        return None
    target = ShockTarget(
        None if economy_id is None else (int(economy_id),),
        sectors=("energy",),
    )
    duration = int(getattr(cfg, "energy_shock_duration", 0))
    suffix = "all" if economy_id is None else str(economy_id)
    return ShockSpec(
        shock_id=f"legacy.energy_capacity.{suffix}",
        kind="energy_capacity",
        start_tick=start,
        magnitude=float(getattr(cfg, "energy_shock_magnitude", 0.0)),
        target=target,
        duration_ticks=None if duration == 0 else duration,
        announcement_tick=start,
        source="legacy_config",
        calibration_note="Compatibility translation of Config.energy_shock_*.",
        tags=("legacy",),
    )


def get_shock_engine(engine: Any) -> ShockEngine | None:
    direct = getattr(engine, "shock_engine", None)
    if isinstance(direct, ShockEngine):
        return direct
    economies = getattr(engine, "economies", None)
    if economies:
        candidate = getattr(economies[0], "shock_engine", None)
        if isinstance(candidate, ShockEngine):
            return candidate
    return None
