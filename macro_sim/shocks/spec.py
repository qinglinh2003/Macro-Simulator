"""Immutable shock contracts and canonical shock tapes.

The shock surface is deliberately semantic.  A tape names a registered economic
channel; it never carries an attribute path or executable callback.  This makes a
tape safe to hash, checkpoint, replay and exchange with a frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from numbers import Integral, Real
from typing import Any, Iterable, Mapping


SHOCK_SCHEMA_VERSION = 1
VISIBILITY_CLASSES = frozenset({"public", "operational", "confidential", "oracle"})
SECTOR_ALIASES = {
    "c": "consumption",
    "k": "capital",
    "e": "energy",
}
SECTORS = frozenset({
    "consumption", "necessity", "luxury", "capital", "energy", "public",
    # CAMPAIGN BUG FIX: builders sell "housing" -- any world with construction
    # crashed at the first planning tick of any productivity/labor shock because
    # sector_for_firm could not normalize the builder sector.
    "housing",
})


def _strict_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def normalize_sector(value: str) -> str:
    text = _text("sector", value)
    result = SECTOR_ALIASES.get(text, text)
    if result not in SECTORS:
        raise ValueError(f"unknown shock sector {value!r}")
    return result


@dataclass(frozen=True)
class ShockTarget:
    """Economies and optional real sectors affected by one shock.

    ``economy_ids=None`` broadcasts to every economy in the engine.  An empty
    tuple is rejected because it nearly always means a silently dead scenario.
    """

    economy_ids: tuple[int, ...] | None = None
    sectors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.economy_ids is not None:
            if isinstance(self.economy_ids, (str, bytes)):
                raise TypeError("ShockTarget.economy_ids must be an integer sequence")
            ids = tuple(sorted(_strict_int("economy_id", item) for item in self.economy_ids))
            if not ids:
                raise ValueError("ShockTarget.economy_ids must be None or non-empty")
            if len(ids) != len(set(ids)):
                raise ValueError("ShockTarget.economy_ids contains duplicates")
            object.__setattr__(self, "economy_ids", ids)
        if isinstance(self.sectors, (str, bytes)):
            raise TypeError("ShockTarget.sectors must be a string sequence")
        sectors = tuple(sorted(normalize_sector(item) for item in self.sectors))
        if len(sectors) != len(set(sectors)):
            raise ValueError("ShockTarget.sectors contains duplicates")
        object.__setattr__(self, "sectors", sectors)

    def matches_economy(self, economy_id: int) -> bool:
        return self.economy_ids is None or economy_id in self.economy_ids

    def matches_sector(self, sector: str | None) -> bool:
        if not self.sectors:
            return True
        if sector is None:
            return False
        normalized = normalize_sector(sector)
        if normalized in self.sectors:
            return True
        return normalized in {"necessity", "luxury"} and "consumption" in self.sectors

    def to_dict(self) -> dict[str, Any]:
        return {
            "economy_ids": None if self.economy_ids is None else list(self.economy_ids),
            "sectors": list(self.sectors),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ShockTarget":
        if not isinstance(value, Mapping) or set(value) != {"economy_ids", "sectors"}:
            raise ValueError("shock target must contain exactly economy_ids and sectors")
        ids = value["economy_ids"]
        sectors = value["sectors"]
        if ids is not None and not isinstance(ids, list):
            raise TypeError("shock target economy_ids must be null or an array")
        if not isinstance(sectors, list):
            raise TypeError("shock target sectors must be an array")
        return cls(None if ids is None else tuple(ids), tuple(sectors))


@dataclass(frozen=True)
class ShockSpec:
    """One fully realized exogenous disturbance.

    Positive magnitude is adverse: a continuous channel contributes
    ``1 - magnitude * intensity``.  Negative magnitude is a favorable shock.
    ``duration_ticks=None`` is a permanent step; a finite duration is an
    inclusive-start/exclusive-end pulse.  Ramps live inside that duration.
    """

    shock_id: str
    kind: str
    start_tick: int
    magnitude: float
    target: ShockTarget = field(default_factory=ShockTarget)
    duration_ticks: int | None = None
    ramp_in_ticks: int = 0
    ramp_out_ticks: int = 0
    announcement_tick: int | None = None
    visibility: str = "public"
    roles: tuple[str, ...] = ()
    source: str = "scenario"
    calibration_note: str = ""
    correlation_group: str | None = None
    tags: tuple[str, ...] = ()
    schema_version: int = SHOCK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "shock_id", _text("shock_id", self.shock_id))
        object.__setattr__(self, "kind", _text("kind", self.kind))
        object.__setattr__(self, "start_tick", _strict_int("start_tick", self.start_tick))
        object.__setattr__(self, "magnitude", _finite("magnitude", self.magnitude))
        if not isinstance(self.target, ShockTarget):
            raise TypeError("target must be a ShockTarget")
        if self.duration_ticks is not None:
            object.__setattr__(
                self, "duration_ticks", _strict_int("duration_ticks", self.duration_ticks, minimum=1),
            )
        object.__setattr__(self, "ramp_in_ticks", _strict_int("ramp_in_ticks", self.ramp_in_ticks))
        object.__setattr__(self, "ramp_out_ticks", _strict_int("ramp_out_ticks", self.ramp_out_ticks))
        if self.duration_ticks is None and self.ramp_out_ticks:
            raise ValueError("a permanent shock cannot have ramp_out_ticks")
        if self.duration_ticks is not None \
                and self.ramp_in_ticks + self.ramp_out_ticks > self.duration_ticks:
            raise ValueError("shock ramps cannot exceed duration_ticks")
        announcement = self.start_tick if self.announcement_tick is None else self.announcement_tick
        object.__setattr__(self, "announcement_tick", _strict_int("announcement_tick", announcement))
        if self.visibility not in VISIBILITY_CLASSES:
            raise ValueError(f"unknown shock visibility {self.visibility!r}")
        if isinstance(self.roles, (str, bytes)):
            raise TypeError("shock roles must be a string sequence")
        roles = tuple(sorted(_text("role", item) for item in self.roles))
        if len(roles) != len(set(roles)):
            raise ValueError("shock roles contain duplicates")
        if self.visibility in {"operational", "confidential"} and not roles:
            raise ValueError(f"{self.visibility} shocks require at least one role")
        if self.visibility in {"public", "oracle"} and roles:
            raise ValueError(f"{self.visibility} shocks cannot carry role grants")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "source", _text("source", self.source))
        if not isinstance(self.calibration_note, str):
            raise TypeError("calibration_note must be a string")
        if self.correlation_group is not None:
            object.__setattr__(
                self, "correlation_group", _text("correlation_group", self.correlation_group),
            )
        if isinstance(self.tags, (str, bytes)):
            raise TypeError("shock tags must be a string sequence")
        tags = tuple(sorted(_text("tag", item) for item in self.tags))
        if len(tags) != len(set(tags)):
            raise ValueError("shock tags contain duplicates")
        object.__setattr__(self, "tags", tags)
        if self.schema_version != SHOCK_SCHEMA_VERSION:
            raise ValueError(f"unsupported ShockSpec schema {self.schema_version}")

    @property
    def end_tick(self) -> int | None:
        return None if self.duration_ticks is None else self.start_tick + self.duration_ticks

    def intensity_at(self, tick: int) -> float:
        tick = int(tick)
        if tick < self.start_tick or (self.end_tick is not None and tick >= self.end_tick):
            return 0.0
        elapsed = tick - self.start_tick
        intensity = 1.0
        if self.ramp_in_ticks:
            intensity = min(intensity, (elapsed + 1) / self.ramp_in_ticks)
        if self.ramp_out_ticks and self.end_tick is not None:
            intensity = min(intensity, (self.end_tick - tick) / self.ramp_out_ticks)
        return max(0.0, min(1.0, float(intensity)))

    def permits(self, role: str) -> bool:
        if role == "oracle":
            return True
        if self.visibility == "public":
            return True
        if self.visibility == "oracle":
            return False
        return role in self.roles

    def to_dict(self) -> dict[str, Any]:
        return {
            "announcement_tick": self.announcement_tick,
            "calibration_note": self.calibration_note,
            "correlation_group": self.correlation_group,
            "duration_ticks": self.duration_ticks,
            "kind": self.kind,
            "magnitude": self.magnitude,
            "ramp_in_ticks": self.ramp_in_ticks,
            "ramp_out_ticks": self.ramp_out_ticks,
            "roles": list(self.roles),
            "schema_version": self.schema_version,
            "shock_id": self.shock_id,
            "source": self.source,
            "start_tick": self.start_tick,
            "tags": list(self.tags),
            "target": self.target.to_dict(),
            "visibility": self.visibility,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ShockSpec":
        expected = {
            "announcement_tick", "calibration_note", "correlation_group",
            "duration_ticks", "kind", "magnitude", "ramp_in_ticks",
            "ramp_out_ticks", "roles", "schema_version", "shock_id", "source",
            "start_tick", "tags", "target", "visibility",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            actual = set(value) if isinstance(value, Mapping) else set()
            raise ValueError(
                f"ShockSpec fields differ; missing={sorted(expected-actual)}, "
                f"extra={sorted(actual-expected)}"
            )
        if not isinstance(value["roles"], list) or not isinstance(value["tags"], list):
            raise TypeError("ShockSpec roles and tags must be arrays")
        return cls(
            shock_id=value["shock_id"], kind=value["kind"],
            start_tick=value["start_tick"], magnitude=value["magnitude"],
            target=ShockTarget.from_dict(value["target"]),
            duration_ticks=value["duration_ticks"], ramp_in_ticks=value["ramp_in_ticks"],
            ramp_out_ticks=value["ramp_out_ticks"],
            announcement_tick=value["announcement_tick"], visibility=value["visibility"],
            roles=tuple(value["roles"]), source=value["source"],
            calibration_note=value["calibration_note"],
            correlation_group=value["correlation_group"], tags=tuple(value["tags"]),
            schema_version=value["schema_version"],
        )


@dataclass(frozen=True)
class ShockTape:
    """Canonical immutable input tape."""

    specs: tuple[ShockSpec, ...] = ()
    name: str = "shock_tape"
    schema_version: int = SHOCK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        specs = tuple(self.specs)
        if not all(isinstance(item, ShockSpec) for item in specs):
            raise TypeError("ShockTape.specs must contain ShockSpec values")
        ids = [item.shock_id for item in specs]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise ValueError(f"duplicate shock ids: {duplicates}")
        object.__setattr__(
            self, "specs", tuple(sorted(specs, key=lambda item: (item.start_tick, item.shock_id))),
        )
        object.__setattr__(self, "name", _text("ShockTape.name", self.name))
        if self.schema_version != SHOCK_SCHEMA_VERSION:
            raise ValueError(f"unsupported ShockTape schema {self.schema_version}")
        # Import lazily to avoid the registry importing this module during setup.
        from .registry import DEFAULT_SHOCK_REGISTRY
        for item in self.specs:
            DEFAULT_SHOCK_REGISTRY.validate_spec(item)

    @property
    def contract_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "specs": [item.to_dict() for item in self.specs],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ShockTape":
        if not isinstance(value, Mapping) or set(value) != {"name", "schema_version", "specs"}:
            raise ValueError("ShockTape must contain exactly name, schema_version and specs")
        if not isinstance(value["specs"], list):
            raise TypeError("ShockTape.specs must be an array")
        return cls(
            tuple(ShockSpec.from_dict(item) for item in value["specs"]),
            name=value["name"], schema_version=value["schema_version"],
        )

    @classmethod
    def from_json(cls, value: str) -> "ShockTape":
        if not isinstance(value, str):
            raise TypeError("ShockTape JSON must be text")
        return cls.from_dict(json.loads(value))

    @classmethod
    def merge(cls, *tapes: "ShockTape", name: str = "merged_shock_tape") -> "ShockTape":
        return cls(
            tuple(spec for tape in tapes for spec in tape.specs),
            name=name,
        )

    @classmethod
    def coerce(cls, value: "ShockTape | Iterable[ShockSpec] | None") -> "ShockTape":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        return cls(tuple(value))
