"""Released-information observations and institutional objective evaluation.

This module deliberately has no dependency on the controller coordinator or on
the simulation scheduler.  It reads only already-committed ``Economy.records``
and ``World.world_records`` rows.  In particular, it never calls a reporting
collector and never inspects live agent state, so constructing an observation
cannot advance a behavioral sensor or leak an unfinished tick.

The release clock uses simulation boundaries.  A record for tick ``r`` is first
eligible at boundary ``r + 1``; ``publication_lag_ticks`` is added after that.
For example, a three-tick period covering ticks 0..2 with lag zero is released
at boundary 3.  This convention matches ``world.t``: the next tick not yet run.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableSequence
from dataclasses import dataclass, field
import json
import math
from numbers import Integral, Real
from typing import Any, ClassVar, Mapping, Sequence, overload

from .chunk_store import ChunkChainIndex, get_chunk, put_chunk
from .protocol import immutable_json_value


ACCESS_CLASSES = frozenset({"public", "confidential", "operational", "oracle"})
AGGREGATIONS = frozenset({"last", "mean", "sum", "min", "max", "change"})
OBJECTIVE_KINDS = frozenset({"target", "bounds", "maximize", "minimize"})


def _strict_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _canonical_value(value: Any) -> Any:
    """Return a recursively JSON-safe value with deterministic set ordering."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("observation values must be finite JSON numbers")
        return result
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=lambda item: _stable_json(item))
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"value of type {type(value).__name__} is not JSON-safe")


def _stable_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


@dataclass(frozen=True)
class Release:
    """One immutable published vintage of an observation series."""

    series_id: str
    value: Any
    reference_start_tick: int
    reference_end_tick: int
    released_at_tick: int
    vintage: int = 1
    revision: int = 0
    access_class: str = "public"
    missing_reason: str | None = None
    unit: str = ""
    economy_id: int = 0

    def __post_init__(self) -> None:
        if not self.series_id:
            raise ValueError("series_id must not be empty")
        _strict_int("released_at_tick", self.released_at_tick)
        _strict_int("vintage", self.vintage, minimum=1)
        _strict_int("revision", self.revision)
        _strict_int("economy_id", self.economy_id)
        if self.access_class not in ACCESS_CLASSES:
            raise ValueError(f"unknown access_class {self.access_class!r}")
        if self.reference_start_tick == -1 or self.reference_end_tick == -1:
            if (self.reference_start_tick, self.reference_end_tick) != (-1, -1):
                raise ValueError("synthetic releases must use reference range -1..-1")
        else:
            _strict_int("reference_start_tick", self.reference_start_tick)
            _strict_int("reference_end_tick", self.reference_end_tick)
            if self.reference_end_tick < self.reference_start_tick:
                raise ValueError("reference_end_tick precedes reference_start_tick")
        if self.missing_reason is not None:
            if not self.missing_reason:
                raise ValueError("missing_reason must be non-empty or None")
            if self.value is not None:
                raise ValueError("a missing release cannot carry a value")
        else:
            object.__setattr__(self, "value", immutable_json_value(self.value))

    @property
    def identity(self) -> tuple[Any, ...]:
        return (
            self.economy_id, self.series_id, self.released_at_tick,
            self.vintage, self.revision,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_class": self.access_class,
            "economy_id": self.economy_id,
            "missing_reason": self.missing_reason,
            "reference_end_tick": self.reference_end_tick,
            "reference_start_tick": self.reference_start_tick,
            "released_at_tick": self.released_at_tick,
            "revision": self.revision,
            "series_id": self.series_id,
            "unit": self.unit,
            "value": _canonical_value(self.value),
            "vintage": self.vintage,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())


RELEASE_CHUNK_FORMAT = "macro-sim-controller-release-chunk-v1"
DEFAULT_RELEASE_CHUNK_SIZE = 32
DEFAULT_RELEASE_TAIL_LIMIT = 64


def _release_from_dict(value: Any) -> Release:
    if not isinstance(value, dict) or set(value) != {
        "access_class", "economy_id", "missing_reason",
        "reference_end_tick", "reference_start_tick", "released_at_tick",
        "revision", "series_id", "unit", "value", "vintage",
    }:
        raise ValueError("release chunk item fields are invalid")
    return Release(**value)


class ReleaseSequence(MutableSequence[Release]):
    """List-compatible publication series with a bounded resident tail."""

    def __init__(
        self,
        values: Sequence[Release] = (),
        *,
        chunk_size: int = DEFAULT_RELEASE_CHUNK_SIZE,
        tail_limit: int = DEFAULT_RELEASE_TAIL_LIMIT,
        chunks: Sequence[Mapping[str, Any]] | Mapping[str, Any] = (),
        tail: Sequence[Release] | None = None,
        total_count: int | None = None,
    ) -> None:
        self.chunk_size = _strict_int(
            "release chunk_size", chunk_size, minimum=1,
        )
        self.tail_limit = _strict_int(
            "release tail_limit", tail_limit, minimum=self.chunk_size,
        )
        if self.chunk_size > 4096 or self.tail_limit > 8192:
            raise ValueError("release sequence bounds are too large")
        if isinstance(chunks, Mapping):
            self._chunks = ChunkChainIndex.from_state(chunks)
        else:
            self._chunks = ChunkChainIndex()
            for descriptor in chunks:
                self._chunks.append(descriptor)
        self._tail = list(values if tail is None else tail)
        if any(not isinstance(item, Release) for item in self._tail):
            raise TypeError("release sequence tail must contain Release values")
        archived = sum(int(item["release_count"]) for item in self._chunks)
        self._total_count = (
            archived + len(self._tail)
            if total_count is None else int(total_count)
        )
        if self._total_count != archived + len(self._tail):
            raise ValueError("release sequence total_count is inconsistent")
        self._validate_descriptors()
        self._compact_tail()

    @property
    def archived_count(self) -> int:
        return self._total_count - len(self._tail)

    @property
    def retained_count(self) -> int:
        return len(self._tail)

    @property
    def chunk_digests(self) -> tuple[str, ...]:
        return tuple(
            str(item["sha256"]) for item in self._chunks
        ) + self._chunks.node_digests

    @staticmethod
    def _chunk_payload(
        first_index: int, releases: Sequence[Release],
    ) -> bytes:
        return (
            json.dumps(
                {
                    "first_index": first_index,
                    "format": RELEASE_CHUNK_FORMAT,
                    "releases": [item.to_dict() for item in releases],
                },
                ensure_ascii=False, allow_nan=False,
                separators=(",", ":"), sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def _decode_chunk(
        cls, payload: bytes, descriptor: Mapping[str, Any],
    ) -> list[Release]:
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("release chunk is not valid JSON") from exc
        if (
            not isinstance(document, dict)
            or set(document) != {"first_index", "format", "releases"}
            or document["format"] != RELEASE_CHUNK_FORMAT
            or document["first_index"] != int(descriptor["first_index"])
        ):
            raise ValueError("release chunk document is invalid")
        releases = [_release_from_dict(item) for item in document["releases"]]
        if cls._chunk_payload(document["first_index"], releases) != payload:
            raise ValueError("release chunk is not canonical")
        return releases

    def _validate_descriptors(self) -> None:
        expected = 0
        previous_release_tick = -1
        for descriptor in self._chunks:
            if set(descriptor) != {
                "byte_count", "first_index", "max_reference_end",
                "max_released_at", "min_reference_start",
                "min_released_at", "release_count", "sha256",
            }:
                raise ValueError("release chunk descriptor fields are invalid")
            count = int(descriptor["release_count"])
            if (
                int(descriptor["first_index"]) != expected
                or count <= 0
                or int(descriptor["byte_count"]) <= 0
            ):
                raise ValueError("release chunk descriptor range is invalid")
            payload = get_chunk(str(descriptor["sha256"]))
            if len(payload) != int(descriptor["byte_count"]):
                raise ValueError("release chunk byte count does not match")
            releases = self._decode_chunk(payload, descriptor)
            if len(releases) != count:
                raise ValueError("release chunk count does not match")
            ticks = [item.released_at_tick for item in releases]
            references = [
                (
                    item.reference_start_tick,
                    item.reference_end_tick,
                )
                for item in releases
            ]
            if (
                ticks != sorted(ticks)
                or ticks[0] < previous_release_tick
                or int(descriptor["min_released_at"]) != ticks[0]
                or int(descriptor["max_released_at"]) != ticks[-1]
                or int(descriptor["min_reference_start"])
                != min(item[0] for item in references)
                or int(descriptor["max_reference_end"])
                != max(item[1] for item in references)
            ):
                raise ValueError("release chunk metadata does not match")
            previous_release_tick = ticks[-1]
            expected += count
        if expected != self.archived_count:
            raise ValueError("release chunk descriptors are not contiguous")
        if self._tail:
            ticks = [item.released_at_tick for item in self._tail]
            if ticks != sorted(ticks) or ticks[0] < previous_release_tick:
                raise ValueError("release sequence tail order is invalid")

    def _write_chunk(self, releases: Sequence[Release]) -> None:
        first = self.archived_count
        payload = self._chunk_payload(first, releases)
        digest = put_chunk(payload)
        self._chunks.append({
            "byte_count": len(payload),
            "first_index": first,
            "max_reference_end": max(
                item.reference_end_tick for item in releases
            ),
            "max_released_at": max(
                item.released_at_tick for item in releases
            ),
            "min_reference_start": min(
                item.reference_start_tick for item in releases
            ),
            "min_released_at": min(
                item.released_at_tick for item in releases
            ),
            "release_count": len(releases),
            "sha256": digest,
        })

    def _compact_tail(self) -> None:
        while len(self._tail) > self.tail_limit:
            chunk = self._tail[:self.chunk_size]
            self._write_chunk(chunk)
            del self._tail[:self.chunk_size]

    def _load_descriptor(
        self, descriptor: Mapping[str, Any],
    ) -> list[Release]:
        return self._decode_chunk(
            get_chunk(str(descriptor["sha256"])), descriptor,
        )

    def _release_at(self, index: int) -> Release:
        if index < 0:
            index += self._total_count
        if not 0 <= index < self._total_count:
            raise IndexError("release index out of range")
        archived = self.archived_count
        if index >= archived:
            return self._tail[index - archived]
        for descriptor in self._chunks:
            first = int(descriptor["first_index"])
            count = int(descriptor["release_count"])
            if first <= index < first + count:
                return self._load_descriptor(descriptor)[index - first]
        raise RuntimeError("release chunk index is unreachable")

    @overload
    def __getitem__(self, index: int) -> Release: ...

    @overload
    def __getitem__(self, index: slice) -> list[Release]: ...

    def __getitem__(self, index: int | slice) -> Release | list[Release]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self._total_count)
            return [
                self._release_at(position)
                for position in range(start, stop, step)
            ]
        return self._release_at(index)

    def __setitem__(self, index: int | slice, value: Any) -> None:
        if isinstance(index, int):
            if not isinstance(value, Release):
                raise TypeError(
                    "release sequence accepts only Release values"
                )
            values = list(self)
            values[index] = value
            self.replace_all(values)
            return
        if index != slice(None, None, None):
            raise TypeError(
                "release sequence supports only complete replacement"
            )
        self.replace_all(value)

    def __delitem__(self, index: int | slice) -> None:
        if isinstance(index, int):
            normalized = index if index >= 0 else self._total_count + index
            if normalized != self._total_count - 1:
                raise TypeError(
                    "release sequence supports only suffix deletion"
                )
            self.truncate(normalized)
            return
        start, stop, step = index.indices(self._total_count)
        if step != 1 or stop != self._total_count:
            raise TypeError("release sequence supports only suffix deletion")
        self.truncate(start)

    def insert(self, index: int, value: Release) -> None:
        if index not in (self._total_count, -1):
            raise TypeError("release sequence is append-only")
        self.append(value)

    def append(self, value: Release) -> None:
        if not isinstance(value, Release):
            raise TypeError("release sequence accepts only Release values")
        if self._total_count and value.released_at_tick < self[-1].released_at_tick:
            raise ValueError("release sequence cannot move backwards")
        self._tail.append(value)
        self._total_count += 1
        self._compact_tail()

    def truncate(self, count: int) -> None:
        count = _strict_int("release truncate count", count)
        if count > self._total_count:
            raise ValueError("release truncate count is outside the sequence")
        if count >= self.archived_count:
            del self._tail[count - self.archived_count:]
            self._total_count = count
            return
        retained = [self._release_at(index) for index in range(count)]
        self._chunks.clear()
        self._tail = retained
        self._total_count = count
        self._compact_tail()

    def replace_all(self, values: Sequence[Release]) -> None:
        self._chunks.clear()
        self._tail.clear()
        self._total_count = 0
        for value in values:
            self.append(value)

    def latest(self, *, as_of_tick: int | None = None) -> Release | None:
        for release in reversed(self._tail):
            if as_of_tick is None or release.released_at_tick <= as_of_tick:
                return release
        for descriptor in reversed(self._chunks):
            if (
                as_of_tick is not None
                and int(descriptor["min_released_at"]) > as_of_tick
            ):
                continue
            for release in reversed(self._load_descriptor(descriptor)):
                if as_of_tick is None \
                        or release.released_at_tick <= as_of_tick:
                    return release
        return None

    def recent(
        self, *, as_of_tick: int | None = None, limit: int,
    ) -> tuple[Release, ...]:
        maximum = _strict_int("release recent limit", limit, minimum=1)
        selected: list[Release] = []
        for release in reversed(self._tail):
            if as_of_tick is None or release.released_at_tick <= as_of_tick:
                selected.append(release)
                if len(selected) == maximum:
                    return tuple(reversed(selected))
        for descriptor in reversed(self._chunks):
            if (
                as_of_tick is not None
                and int(descriptor["min_released_at"]) > as_of_tick
            ):
                continue
            for release in reversed(self._load_descriptor(descriptor)):
                if as_of_tick is None \
                        or release.released_at_tick <= as_of_tick:
                    selected.append(release)
                    if len(selected) == maximum:
                        return tuple(reversed(selected))
        return tuple(reversed(selected))

    def iter_dependency_window(
        self, reference_start: int, reference_end: int, released_at: int,
    ) -> Iterator[Release]:
        for descriptor in self._chunks:
            if (
                int(descriptor["min_released_at"]) > released_at
                or int(descriptor["max_reference_end"]) < reference_start
                or int(descriptor["min_reference_start"]) > reference_end
            ):
                continue
            for release in self._load_descriptor(descriptor):
                if (
                    release.released_at_tick <= released_at
                    and release.reference_start_tick >= reference_start
                    and release.reference_end_tick <= reference_end
                ):
                    yield release
        for release in self._tail:
            if (
                release.released_at_tick <= released_at
                and release.reference_start_tick >= reference_start
                and release.reference_end_tick <= reference_end
            ):
                yield release

    def __len__(self) -> int:
        return self._total_count

    def __iter__(self) -> Iterator[Release]:
        for descriptor in self._chunks:
            yield from self._load_descriptor(descriptor)
        yield from self._tail

    def to_state(self) -> dict[str, Any]:
        return {
            "chunk_size": self.chunk_size,
            "chunks": self._chunks.to_state(),
            "tail": list(self._tail),
            "tail_limit": self.tail_limit,
            "total_count": self._total_count,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ReleaseSequence":
        if not isinstance(state, Mapping) or set(state) != {
            "chunk_size", "chunks", "tail", "tail_limit", "total_count",
        }:
            raise ValueError("release sequence state fields are invalid")
        return cls(
            chunk_size=state["chunk_size"],
            chunks=state["chunks"],
            tail=state["tail"],
            tail_limit=state["tail_limit"],
            total_count=state["total_count"],
        )


@dataclass(frozen=True)
class ObservationFieldSpec:
    """Declarative mapping from a committed record field to a release series.

    ``frequency_ticks`` controls period endpoints, while ``window_ticks``
    controls the aggregation reference window ending at each endpoint.  They
    are independent so, for example, a 30-tick moving average may be published
    every 7 ticks.
    """

    series_id: str
    source_key: str
    source: str = "economy"              # economy | world | release
    unit: str = ""
    aggregation: str = "last"
    window_ticks: int = 1
    frequency_ticks: int = 1
    publication_lag_ticks: int = 0
    phase_offset_ticks: int = 0
    access_class: str = "public"
    roles: frozenset[str] = frozenset()
    require_full_window: bool = True
    economy_indexed: bool = False
    normalization_scale: float | None = None

    def __post_init__(self) -> None:
        if not self.series_id or not self.source_key:
            raise ValueError("series_id and source_key must not be empty")
        if self.source not in {"economy", "world", "release", "shock"}:
            raise ValueError("source must be 'economy', 'world', 'release', or 'shock'")
        if self.source == "release" and self.economy_indexed:
            raise ValueError("a released dependency is already economy-specific")
        if self.source == "shock" and (
            self.aggregation != "last" or self.window_ticks != 1
            or self.economy_indexed or self.phase_offset_ticks != 0
            or self.publication_lag_ticks != 0
        ):
            raise ValueError(
                "shock observables require aggregation='last', window_ticks=1, "
                "economy_indexed=False, phase_offset_ticks=0 and publication_lag_ticks=0"
            )
        if self.aggregation not in AGGREGATIONS:
            raise ValueError(f"unknown aggregation {self.aggregation!r}")
        _strict_int("window_ticks", self.window_ticks, minimum=1)
        _strict_int("frequency_ticks", self.frequency_ticks, minimum=1)
        _strict_int("publication_lag_ticks", self.publication_lag_ticks)
        _strict_int("phase_offset_ticks", self.phase_offset_ticks)
        if self.access_class not in ACCESS_CLASSES:
            raise ValueError(f"unknown access_class {self.access_class!r}")
        object.__setattr__(self, "roles", frozenset(self.roles))
        if self.access_class in {"confidential", "operational"} and not self.roles:
            raise ValueError(f"{self.access_class} field requires at least one authorized role")
        if self.normalization_scale is not None:
            scale = _finite("normalization_scale", self.normalization_scale)
            if scale <= 0.0:
                raise ValueError("normalization_scale must be > 0")

    def permits(self, role: str) -> bool:
        if self.access_class == "public":
            return True
        if self.access_class == "oracle":
            return role == "oracle"
        return role in self.roles

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_class": self.access_class,
            "aggregation": self.aggregation,
            "economy_indexed": self.economy_indexed,
            "frequency_ticks": self.frequency_ticks,
            "normalization_scale": self.normalization_scale,
            "phase_offset_ticks": self.phase_offset_ticks,
            "publication_lag_ticks": self.publication_lag_ticks,
            "require_full_window": self.require_full_window,
            "roles": sorted(self.roles),
            "series_id": self.series_id,
            "source": self.source,
            "source_key": self.source_key,
            "unit": self.unit,
            "window_ticks": self.window_ticks,
        }


@dataclass(frozen=True)
class ObservationSpec:
    fields: tuple[ObservationFieldSpec, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))
        _strict_int("schema_version", self.schema_version, minimum=1)
        names = [field.series_id for field in self.fields]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate observation series: {duplicates}")
        by_name = {item.series_id: item for item in self.fields}
        for item in self.fields:
            if item.source != "release":
                continue
            if item.source_key not in by_name:
                raise ValueError(
                    f"derived series {item.series_id!r} references unknown release "
                    f"{item.source_key!r}"
                )
            source = by_name[item.source_key]
            if item.access_class != source.access_class:
                raise ValueError(
                    f"derived series {item.series_id!r} cannot change dependency access_class"
                )
            if item.access_class in {"confidential", "operational"} \
                    and not item.roles.issubset(source.roles):
                raise ValueError(
                    f"derived series {item.series_id!r} broadens dependency role access"
                )
        # Validate the dependency graph now; publication later uses the same
        # topological order so a same-boundary base vintage exists before its
        # rolling/derived release is evaluated.
        self.ordered_fields()

    def field(self, series_id: str) -> ObservationFieldSpec:
        for item in self.fields:
            if item.series_id == series_id:
                return item
        raise KeyError(series_id)

    def ordered_fields(self) -> tuple[ObservationFieldSpec, ...]:
        by_name = {item.series_id: item for item in self.fields}
        visiting: set[str] = set()
        visited: set[str] = set()
        ordered: list[ObservationFieldSpec] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"observation release dependency cycle at {name!r}")
            visiting.add(name)
            item = by_name[name]
            if item.source == "release":
                dependency = item.source_key
                if dependency not in by_name:
                    # __post_init__ gives the more descriptive public error.
                    raise ValueError(f"unknown release dependency {dependency!r}")
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(item)

        for name in sorted(by_name):
            visit(name)
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": [
                item.to_dict() for item in sorted(self.fields, key=lambda f: f.series_id)
            ],
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())


@dataclass(frozen=True)
class InstitutionObservation:
    """The role-filtered, boundary-versioned observation sent to an occupant."""

    boundary_tick: int
    economy_id: int
    role: str
    releases: tuple[Release, ...]
    observation_schema_version: int = 1
    elapsed_ticks: int = 0
    shock_bulletins: tuple[Mapping[str, Any], ...] = ()
    observation_kind: ClassVar[str] = "institution"
    _controller_observation_deeply_immutable: ClassVar[bool] = True

    def __post_init__(self) -> None:
        _strict_int("boundary_tick", self.boundary_tick)
        _strict_int("economy_id", self.economy_id)
        _strict_int("observation_schema_version", self.observation_schema_version, minimum=1)
        _strict_int("elapsed_ticks", self.elapsed_ticks)
        ordered = tuple(sorted(self.releases, key=lambda item: item.series_id))
        names = [item.series_id for item in ordered]
        if len(names) != len(set(names)):
            raise ValueError("InstitutionObservation must contain one release per series")
        for item in ordered:
            if not isinstance(item, Release):
                raise TypeError("InstitutionObservation.releases must contain Release values")
            if item.economy_id != self.economy_id:
                raise ValueError("release economy_id does not match observation")
            if item.released_at_tick > self.boundary_tick:
                raise ValueError("observation contains an unreleased future vintage")
        object.__setattr__(self, "releases", ordered)
        bulletins = tuple(
            immutable_json_value(item) for item in self.shock_bulletins
        )
        if not all(isinstance(item, Mapping) for item in bulletins):
            raise TypeError("shock_bulletins must contain JSON mappings")
        bulletins = tuple(sorted(
            bulletins, key=lambda item: (item.get("start_tick", 0), item.get("shock_id", "")),
        ))
        object.__setattr__(self, "shock_bulletins", bulletins)

    def release(self, series_id: str) -> Release:
        for item in self.releases:
            if item.series_id == series_id:
                return item
        raise KeyError(series_id)

    def values(self) -> dict[str, Any]:
        return {
            item.series_id: item.value
            for item in self.releases if item.missing_reason is None
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_tick": self.boundary_tick,
            "economy_id": self.economy_id,
            "elapsed_ticks": self.elapsed_ticks,
            "observation_schema_version": self.observation_schema_version,
            "observation_kind": self.observation_kind,
            "releases": [item.to_dict() for item in self.releases],
            "role": self.role,
            "shock_bulletins": list(self.shock_bulletins),
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    def to_json_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")


@dataclass(frozen=True)
class PublicObservation(InstitutionObservation):
    """The stable public subset of the institution observation contract."""

    observation_kind: ClassVar[str] = "public"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.role != "public":
            raise ValueError("PublicObservation role must be 'public'")
        if any(
            release.access_class != "public"
            and release.missing_reason != "access_denied"
            for release in self.releases
        ):
            raise ValueError("PublicObservation cannot expose non-public release values")


@dataclass(frozen=True)
class OracleObservation(InstitutionObservation):
    """Explicitly isolated research/debug observation; never a policy context."""

    observation_kind: ClassVar[str] = "oracle"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.role != "oracle":
            raise ValueError("OracleObservation role must be 'oracle'")


class ReleaseService:
    """Stateful, checkpoint-friendly publication ledger.

    Calling :meth:`observe` repeatedly at the same boundary is idempotent.  A
    boundary may never move backwards for a given economy, which prevents a
    loaded frontend from accidentally manufacturing a historical revision.
    """

    def __init__(self, spec: ObservationSpec):
        self.spec = spec
        self._history: dict[
            tuple[int, str], ReleaseSequence | list[Release]
        ] = {}
        self._next_period_index: dict[tuple[int, str], int] = {}
        self._last_boundary: dict[int, int] = {}

    def _series(self, key: tuple[int, str]) -> ReleaseSequence:
        current = self._history.get(key)
        if isinstance(current, ReleaseSequence):
            return current
        sequence = ReleaseSequence(() if current is None else current)
        self._history[key] = sequence
        return sequence

    @staticmethod
    def _shock_observable(
        engine: Any, key: str, economy_id: int, boundary_tick: int,
        *, role: str,
    ) -> float:
        """Read a disclosed shock scalar from either engine implementation.

        The native engine exposes a narrow, role-aware observation provider
        instead of materializing a second Python ``ShockEngine`` beside the
        authoritative C++ shock tape.  The legacy Python engine continues to use
        its typed ``ShockEngine`` unchanged.
        """
        native_provider = getattr(engine, "native_shock_observable", None)
        if callable(native_provider):
            value = native_provider(
                key, economy_id, boundary_tick, role=role,
            )
            return _finite(f"shock observable {key!r}", value)
        from macro_sim.shocks import get_shock_engine

        shock_engine = get_shock_engine(engine)
        return 0.0 if shock_engine is None else shock_engine.observable(
            key, economy_id, boundary_tick, role=role,
        )

    @staticmethod
    def _shock_bulletins(
        engine: Any, economy_id: int, boundary_tick: int, *, role: str,
    ) -> tuple[Any, ...]:
        native_provider = getattr(engine, "native_shock_bulletins", None)
        if callable(native_provider):
            return tuple(native_provider(
                economy_id, boundary_tick, role=role,
            ))
        from macro_sim.shocks import get_shock_engine

        shock_engine = get_shock_engine(engine)
        return () if shock_engine is None else shock_engine.bulletins(
            economy_id, boundary_tick, role=role,
        )

    @staticmethod
    def _records(engine: Any, source: str, economy_id: int) -> Sequence[Mapping[str, Any]] | None:
        economies = getattr(engine, "economies", None)
        if source == "economy":
            if economies is not None:
                if not 0 <= economy_id < len(economies):
                    raise IndexError(f"economy_id {economy_id} out of range")
                return getattr(economies[economy_id], "records", None)
            if economy_id != 0:
                raise IndexError("a bare Economy has only economy_id 0")
            return getattr(engine, "records", None)
        if economies is None:
            return None
        return getattr(engine, "world_records", None)

    @staticmethod
    def _path(record: Mapping[str, Any], path: str) -> tuple[bool, Any]:
        value: Any = record
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                return False, None
            value = value[part]
        return True, value

    @staticmethod
    def _select_economy(value: Any, economy_id: int) -> tuple[bool, Any]:
        if isinstance(value, Mapping):
            if economy_id in value:
                return True, value[economy_id]
            if str(economy_id) in value:
                return True, value[str(economy_id)]
            return False, None
        if isinstance(value, (list, tuple)) and 0 <= economy_id < len(value):
            return True, value[economy_id]
        return False, None

    @staticmethod
    def _aggregate(kind: str, values: Sequence[Any]) -> tuple[Any, str | None]:
        if not values:
            return None, "no_completed_data"
        if kind == "last":
            try:
                return _canonical_value(values[-1]), None
            except (TypeError, ValueError):
                return None, "invalid_value"
        numeric: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, Real):
                return None, "non_numeric"
            number = float(value)
            if not math.isfinite(number):
                return None, "non_finite"
            numeric.append(number)
        if kind == "mean":
            return sum(numeric) / len(numeric), None
        if kind == "sum":
            return sum(numeric), None
        if kind == "min":
            return min(numeric), None
        if kind == "max":
            return max(numeric), None
        if kind == "change":
            return numeric[-1] - numeric[0], None
        raise AssertionError(f"unhandled aggregation {kind}")

    def _make_release(
        self, engine: Any, item: ObservationFieldSpec, economy_id: int,
        reference_end: int, released_at: int,
    ) -> Release:
        requested_start = reference_end - item.window_ticks + 1
        if requested_start < 0 and item.require_full_window:
            return Release(
                item.series_id, None, max(0, requested_start), reference_end,
                released_at, access_class=item.access_class,
                missing_reason="warmup", unit=item.unit, economy_id=economy_id,
            )
        reference_start = max(0, requested_start)
        if item.source == "shock":
            values = [
                self._shock_observable(
                    engine, item.source_key, economy_id, released_at,
                    role="public",
                )
            ]
            reason = None
        elif item.source == "release":
            values, reason = self._released_dependency_values(
                item, economy_id, reference_start, reference_end, released_at,
            )
        else:
            records = self._records(engine, item.source, economy_id)
            if records is None:
                reason = "source_unavailable"
                values = []
            else:
                by_tick: dict[int, Mapping[str, Any]] = {}
                for index, record in enumerate(records):
                    if not isinstance(record, Mapping):
                        continue
                    raw_tick = record.get("t", index)
                    if isinstance(raw_tick, bool) or not isinstance(raw_tick, Integral):
                        continue
                    tick = int(raw_tick)
                    # The explicit range is the anti-lookahead gate even if the
                    # supplied engine has already simulated far beyond this boundary.
                    if reference_start <= tick <= reference_end:
                        by_tick[tick] = record
                expected = list(range(reference_start, reference_end + 1))
                if any(tick not in by_tick for tick in expected):
                    reason = "no_completed_data"
                    values = []
                else:
                    reason = None
                    values = []
                    for tick in expected:
                        found, value = self._path(by_tick[tick], item.source_key)
                        if found and item.economy_indexed:
                            found, value = self._select_economy(value, economy_id)
                        if not found:
                            reason = "source_missing"
                            values = []
                            break
                        values.append(value)
        value = None
        if reason is None:
            value, reason = self._aggregate(item.aggregation, values)
        return Release(
            item.series_id, value, reference_start, reference_end, released_at,
            access_class=item.access_class, missing_reason=reason, unit=item.unit,
            economy_id=economy_id,
        )

    def _released_dependency_values(
        self, item: ObservationFieldSpec, economy_id: int,
        reference_start: int, reference_end: int, released_at: int,
    ) -> tuple[list[Any], str | None]:
        """Read only dependency vintages that existed by this release boundary.

        Revisions of one reference period replace, rather than supplement, their
        older vintage.  Full-window derived fields require the dependency ranges
        to cover the requested ticks, preventing an unfinished quarterly series
        from leaking through a nominally daily rolling indicator.
        """
        history = self._history.get((economy_id, item.source_key), ())
        latest_by_period: dict[tuple[int, int], Release] = {}
        candidates = (
            history.iter_dependency_window(
                reference_start, reference_end, released_at,
            )
            if isinstance(history, ReleaseSequence)
            else (
                release for release in history
                if release.released_at_tick <= released_at
                and release.reference_start_tick >= reference_start
                and release.reference_end_tick <= reference_end
            )
        )
        for release in candidates:
            if release.released_at_tick > released_at:
                continue
            if release.reference_start_tick < reference_start \
                    or release.reference_end_tick > reference_end:
                continue
            period = (release.reference_start_tick, release.reference_end_tick)
            previous = latest_by_period.get(period)
            if previous is None or (
                release.released_at_tick, release.vintage, release.revision
            ) > (
                previous.released_at_tick, previous.vintage, previous.revision
            ):
                latest_by_period[period] = release
        releases = sorted(
            latest_by_period.values(),
            key=lambda release: (
                release.reference_start_tick, release.reference_end_tick,
                release.released_at_tick,
            ),
        )
        if not releases:
            return [], "dependency_not_released"
        if any(release.missing_reason is not None for release in releases):
            return [], "dependency_missing"
        if item.require_full_window:
            covered_through = reference_start - 1
            for release in releases:
                start = max(reference_start, release.reference_start_tick)
                end = min(reference_end, release.reference_end_tick)
                if start > covered_through + 1:
                    return [], "dependency_not_released"
                covered_through = max(covered_through, end)
            if covered_through < reference_end:
                return [], "dependency_not_released"
        return [release.value for release in releases], None

    def publish_due(
        self, engine: Any, boundary_tick: int, *, economy_id: int = 0,
    ) -> tuple[Release, ...]:
        boundary_tick = _strict_int("boundary_tick", boundary_tick)
        economy_id = _strict_int("economy_id", economy_id)
        previous = self._last_boundary.get(economy_id, -1)
        if boundary_tick < previous:
            raise ValueError("release boundary cannot move backwards")
        published: list[Release] = []
        for item in self.spec.ordered_fields():
            key = (economy_id, item.series_id)
            if item.source == "shock":
                # Shock announcements are boundary information, not a statistic
                # over a completed economic tick.  Publish a synthetic vintage at
                # boundary zero as well, so an announced tick-0 crisis is visible
                # before the first Controller action/RL step.
                period_index = self._next_period_index.get(key, 0)
                while True:
                    released_at = (
                        item.phase_offset_ticks
                        + period_index * item.frequency_ticks
                        + item.publication_lag_ticks
                    )
                    if released_at > boundary_tick:
                        break
                    value = self._shock_observable(
                        engine, item.source_key, economy_id, released_at,
                        role="public",
                    )
                    release = Release(
                        item.series_id, value, -1, -1, released_at,
                        access_class=item.access_class, unit=item.unit,
                        economy_id=economy_id,
                    )
                    self._series(key).append(release)
                    published.append(release)
                    period_index += 1
                self._next_period_index[key] = period_index
                continue
            period_index = self._next_period_index.get(key, 1)
            while True:
                reference_end = (
                    item.phase_offset_ticks
                    + period_index * item.frequency_ticks
                    - 1
                )
                released_at = reference_end + 1 + item.publication_lag_ticks
                if released_at > boundary_tick:
                    break
                release = self._make_release(
                    engine, item, economy_id, reference_end, released_at,
                )
                self._series(key).append(release)
                published.append(release)
                period_index += 1
            self._next_period_index[key] = period_index
        self._last_boundary[economy_id] = boundary_tick
        return tuple(published)

    @staticmethod
    def _missing_release(
        item: ObservationFieldSpec, economy_id: int, boundary_tick: int, reason: str,
    ) -> Release:
        return Release(
            item.series_id, None, -1, -1, boundary_tick,
            access_class=item.access_class, missing_reason=reason,
            unit=item.unit, economy_id=economy_id,
        )

    def observe(
        self, engine: Any, boundary_tick: int, *, economy_id: int = 0,
        role: str = "public", elapsed_ticks: int = 0,
    ) -> InstitutionObservation:
        if role == "oracle":
            raise ValueError(
                "oracle observations require the explicit observe_oracle() research API"
            )
        self.publish_due(engine, boundary_tick, economy_id=economy_id)
        visible: list[Release] = []
        for item in sorted(self.spec.fields, key=lambda field: field.series_id):
            if not item.permits(role):
                visible.append(self._missing_release(
                    item, economy_id, boundary_tick, "access_denied",
                ))
                continue
            history = self._history.get((economy_id, item.series_id), ())
            latest = (
                history.latest(as_of_tick=boundary_tick)
                if isinstance(history, ReleaseSequence)
                else next(
                    (
                        release for release in reversed(history)
                        if release.released_at_tick <= boundary_tick
                    ),
                    None,
                )
            )
            visible.append(
                latest if latest is not None else self._missing_release(
                    item, economy_id, boundary_tick, "not_released",
                )
            )
        observation_type = PublicObservation if role == "public" else InstitutionObservation
        bulletins = self._shock_bulletins(
            engine, economy_id, boundary_tick, role=role,
        )
        return observation_type(
            boundary_tick=boundary_tick,
            economy_id=economy_id,
            role=role,
            releases=tuple(visible),
            observation_schema_version=self.spec.schema_version,
            elapsed_ticks=elapsed_ticks,
            shock_bulletins=bulletins,
        )

    def observe_oracle(
        self, engine: Any, boundary_tick: int, *, economy_id: int = 0,
        elapsed_ticks: int = 0,
    ) -> OracleObservation:
        """Build an explicitly labelled omniscient research/debug observation.

        Oracle access bypasses institutional role filtering, not publication time.
        Every returned value must still have been released by ``boundary_tick``.
        Keeping this on a separate method prevents a client from obtaining it by
        merely claiming ``role="oracle"`` through the normal observation API.
        """
        self.publish_due(engine, boundary_tick, economy_id=economy_id)
        visible: list[Release] = []
        for item in sorted(self.spec.fields, key=lambda field: field.series_id):
            history = self._history.get((economy_id, item.series_id), ())
            latest = (
                history.latest(as_of_tick=boundary_tick)
                if isinstance(history, ReleaseSequence)
                else next(
                    (
                        release for release in reversed(history)
                        if release.released_at_tick <= boundary_tick
                    ),
                    None,
                )
            )
            visible.append(
                latest if latest is not None else self._missing_release(
                    item, economy_id, boundary_tick, "not_released",
                )
            )
        bulletins = self._shock_bulletins(
            engine, economy_id, boundary_tick, role="oracle",
        )
        return OracleObservation(
            boundary_tick=boundary_tick,
            economy_id=economy_id,
            role="oracle",
            releases=tuple(visible),
            observation_schema_version=self.spec.schema_version,
            elapsed_ticks=elapsed_ticks,
            shock_bulletins=bulletins,
        )

    def history(
        self, economy_id: int, series_id: str, *, as_of_tick: int | None = None,
        limit: int | None = None,
    ) -> tuple[Release, ...]:
        history = self._history.get((economy_id, series_id), ())
        if limit is not None:
            limit = _strict_int("history limit", limit, minimum=1)
        if isinstance(history, ReleaseSequence):
            if limit is not None:
                return history.recent(
                    as_of_tick=as_of_tick, limit=limit,
                )
            if as_of_tick is None:
                return tuple(history)
        result = tuple(
            item for item in history
            if as_of_tick is None or item.released_at_tick <= as_of_tick
        )
        if limit is not None:
            result = result[-limit:]
        return result


@dataclass(frozen=True)
class ObjectiveTerm:
    series_id: str
    objective_kind: str
    target_or_bounds: Any = None
    weight: float = 1.0
    normalization_scale: float = 1.0
    evaluation_window: int = 1
    reward_release_rule: str = "latest"       # latest | on_release

    def __post_init__(self) -> None:
        if not self.series_id:
            raise ValueError("objective series_id must not be empty")
        if self.objective_kind not in OBJECTIVE_KINDS:
            raise ValueError(f"unknown objective_kind {self.objective_kind!r}")
        weight = _finite("weight", self.weight)
        scale = _finite("normalization_scale", self.normalization_scale)
        if weight < 0.0:
            raise ValueError("weight must be >= 0")
        if scale <= 0.0:
            raise ValueError("normalization_scale must be > 0")
        _strict_int("evaluation_window", self.evaluation_window, minimum=1)
        if self.reward_release_rule not in {"latest", "on_release"}:
            raise ValueError("reward_release_rule must be 'latest' or 'on_release'")
        if self.objective_kind == "target":
            _finite("target", self.target_or_bounds)
        elif self.objective_kind == "bounds":
            if not isinstance(self.target_or_bounds, (list, tuple)) \
                    or len(self.target_or_bounds) != 2:
                raise ValueError("bounds objective requires (lower, upper)")
            lower = _finite("lower bound", self.target_or_bounds[0])
            upper = _finite("upper bound", self.target_or_bounds[1])
            if lower > upper:
                raise ValueError("objective lower bound exceeds upper bound")
            object.__setattr__(self, "target_or_bounds", (lower, upper))
        elif self.target_or_bounds is not None:
            raise ValueError("maximize/minimize objectives do not take target_or_bounds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_window": self.evaluation_window,
            "normalization_scale": self.normalization_scale,
            "objective_kind": self.objective_kind,
            "reward_release_rule": self.reward_release_rule,
            "series_id": self.series_id,
            "target_or_bounds": self.target_or_bounds,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class ObjectiveSpec:
    terms: tuple[ObjectiveTerm, ...]
    schema_version: int = 1
    human_comparable: bool = True
    control_cost_weight: float = 0.0
    time_normalization: str = "per_tick"       # per_tick | sum

    def __post_init__(self) -> None:
        object.__setattr__(self, "terms", tuple(self.terms))
        _strict_int("schema_version", self.schema_version, minimum=1)
        cost_weight = _finite("control_cost_weight", self.control_cost_weight)
        if cost_weight < 0.0:
            raise ValueError("control_cost_weight must be >= 0")
        if self.time_normalization not in {"per_tick", "sum"}:
            raise ValueError("time_normalization must be 'per_tick' or 'sum'")
        names = [term.series_id for term in self.terms]
        if len(names) != len(set(names)):
            raise ValueError("ObjectiveSpec contains duplicate series")

    def validate_against(self, observation_spec: ObservationSpec) -> None:
        fields = {item.series_id: item for item in observation_spec.fields}
        for term in self.terms:
            if term.series_id not in fields:
                raise ValueError(f"objective series {term.series_id!r} is not observable")
            if self.human_comparable and fields[term.series_id].access_class == "oracle":
                raise ValueError(
                    f"human_comparable objective cannot use oracle series {term.series_id!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_cost_weight": self.control_cost_weight,
            "human_comparable": self.human_comparable,
            "schema_version": self.schema_version,
            "terms": [term.to_dict() for term in sorted(self.terms, key=lambda t: t.series_id)],
            "time_normalization": self.time_normalization,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())


@dataclass(frozen=True)
class ObjectiveEvaluation:
    total_reward: float
    macro_reward: float
    control_cost_penalty: float
    components: Mapping[str, float]
    missing: Mapping[str, str]
    elapsed_ticks: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "components": dict(sorted(self.components.items())),
            "control_cost_penalty": self.control_cost_penalty,
            "elapsed_ticks": self.elapsed_ticks,
            "macro_reward": self.macro_reward,
            "missing": dict(sorted(self.missing.items())),
            "total_reward": self.total_reward,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())


class ObjectiveEvaluator:
    """Evaluate a mandate exclusively from role-filtered released observations."""

    def __init__(self, spec: ObjectiveSpec, observation_spec: ObservationSpec):
        spec.validate_against(observation_spec)
        self.spec = spec
        self.observation_spec = observation_spec
        self._history: dict[tuple[int, str, str], list[Release]] = {}
        self._seen: set[tuple[Any, ...]] = set()

    def _ingest(
        self, observation: InstitutionObservation,
        release_history: Mapping[str, Sequence[Release]] | None,
    ) -> set[tuple[Any, ...]]:
        oracle_observation = isinstance(observation, OracleObservation)
        if self.spec.human_comparable and oracle_observation:
            raise ValueError(
                "an OracleObservation cannot enter a human_comparable objective"
            )
        candidates: list[Release] = list(observation.releases)
        if release_history is not None:
            candidates = [
                release
                for series in sorted(release_history)
                for release in release_history[series]
                if release.released_at_tick <= observation.boundary_tick
            ]
        newly_seen: set[tuple[Any, ...]] = set()
        fields = {item.series_id: item for item in self.observation_spec.fields}
        for release in sorted(
            candidates,
            key=lambda item: (item.released_at_tick, item.series_id, item.vintage, item.revision),
        ):
            if release.economy_id != observation.economy_id:
                continue
            field_spec = fields.get(release.series_id)
            if field_spec is None or (
                not oracle_observation and not field_spec.permits(observation.role)
            ):
                continue
            if release.missing_reason is not None or release.value is None:
                continue
            if self.spec.human_comparable and release.access_class == "oracle":
                raise ValueError("oracle release entered a human_comparable objective")
            seen_key = (observation.role,) + release.identity
            if seen_key in self._seen:
                continue
            self._seen.add(seen_key)
            newly_seen.add(release.identity)
            key = (observation.economy_id, observation.role, release.series_id)
            self._history.setdefault(key, []).append(release)
        windows = {
            term.series_id: term.evaluation_window
            for term in self.spec.terms
        }
        for key, releases in self._history.items():
            maximum = windows.get(key[2], 1)
            if len(releases) > maximum:
                del releases[:-maximum]
        self._seen = {
            (role,) + release.identity
            for (_economy_id, role, _series_id), releases
            in self._history.items()
            for release in releases
        }
        return newly_seen

    @staticmethod
    def _score(term: ObjectiveTerm, value: float) -> float:
        scale = float(term.normalization_scale)
        if term.objective_kind == "target":
            distance = (value - float(term.target_or_bounds)) / scale
            return -float(term.weight) * distance * distance
        if term.objective_kind == "bounds":
            lower, upper = term.target_or_bounds
            if value < lower:
                distance = (value - lower) / scale
            elif value > upper:
                distance = (value - upper) / scale
            else:
                distance = 0.0
            return -float(term.weight) * distance * distance
        if term.objective_kind == "maximize":
            return float(term.weight) * value / scale
        if term.objective_kind == "minimize":
            return -float(term.weight) * value / scale
        raise AssertionError(term.objective_kind)

    def evaluate(
        self, observation: InstitutionObservation, *, adjustment_cost: float = 0.0,
        elapsed_ticks: int | None = None,
        release_history: Mapping[str, Sequence[Release]] | None = None,
    ) -> ObjectiveEvaluation:
        if observation.observation_schema_version != self.observation_spec.schema_version:
            raise ValueError("observation schema version does not match ObjectiveEvaluator")
        adjustment_cost = _finite("adjustment_cost", adjustment_cost)
        if adjustment_cost < 0.0:
            raise ValueError("adjustment_cost must be >= 0")
        elapsed = observation.elapsed_ticks if elapsed_ticks is None else elapsed_ticks
        elapsed = _strict_int("elapsed_ticks", elapsed)
        elapsed = max(1, elapsed)
        newly_seen = self._ingest(observation, release_history)

        components: dict[str, float] = {}
        missing: dict[str, str] = {}
        for term in self.spec.terms:
            releases = self._history.get(
                (observation.economy_id, observation.role, term.series_id), ()
            )
            if len(releases) < term.evaluation_window:
                missing[term.series_id] = "objective_warmup"
                continue
            latest = releases[-1]
            if term.reward_release_rule == "on_release" and latest.identity not in newly_seen:
                components[term.series_id] = 0.0
                continue
            window = releases[-term.evaluation_window:]
            values: list[float] = []
            bad = False
            for release in window:
                if isinstance(release.value, bool) or not isinstance(release.value, Real):
                    bad = True
                    break
                value = float(release.value)
                if not math.isfinite(value):
                    bad = True
                    break
                values.append(value)
            if bad:
                missing[term.series_id] = "objective_non_numeric"
                continue
            components[term.series_id] = self._score(term, sum(values) / len(values))

        raw_macro = sum(components.values())
        raw_cost = float(self.spec.control_cost_weight) * adjustment_cost
        if self.spec.time_normalization == "sum":
            macro_reward = raw_macro * elapsed
            cost_penalty = raw_cost
        else:
            macro_reward = raw_macro
            cost_penalty = raw_cost / elapsed
        return ObjectiveEvaluation(
            total_reward=macro_reward - cost_penalty,
            macro_reward=macro_reward,
            control_cost_penalty=cost_penalty,
            components=components,
            missing=missing,
            elapsed_ticks=elapsed,
        )


def default_observation_spec() -> ObservationSpec:
    """Reviewed P0 institutional release table.

    Frequencies/lags are configurable model defaults, not claims that every
    jurisdiction publishes on this cadence.  Daily operational data are role
    restricted; public macro aggregates arrive in weekly/monthly batches.
    """
    F = ObservationFieldSpec
    cb_reg = frozenset({"central_bank", "regulator"})
    return ObservationSpec(fields=(
        F("price_index", "price_index", unit="index", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=1.0),
        F("inflation", "inflation", unit="per_tick", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=0.01),
        F("real_output", "real_output", unit="goods", aggregation="sum",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=1_000.0),
        F("unemployment_rate", "unemployment_rate", unit="share", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=0.1),
        F("employment", "employment", unit="fte", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=100.0),
        F("avg_wage", "avg_wage", unit="currency_per_tick", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=1.0),
        F("population_alive", "population_alive", unit="persons", aggregation="last",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=1_000.0),
        F("poverty_rate", "poverty_rate", unit="share", aggregation="mean",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=0.1),
        F("income_gini", "income_gini", unit="index", aggregation="last",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=0.5),
        F("gov_deficit_to_gdp", "gov_deficit_to_gdp", unit="share", aggregation="mean",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=0.1),
        F("gov_debt_to_gdp", "gov_debt_to_gdp", unit="share", aggregation="last",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=1.0),
        F("policy_rate", "policy_rate", unit="per_tick", aggregation="last",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.01),
        F("bank_reserves_total", "bank_reserves_total", unit="currency",
          access_class="operational", roles=cb_reg,
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1_000.0),
        F("reserve_floor_breach_share", "reserve_floor_breach_share", unit="share",
          access_class="confidential", roles=cb_reg,
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.1),
        F("near_failure_bank_count", "near_failure_bank_count", unit="banks",
          access_class="confidential", roles=cb_reg,
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1.0),
        F("bank_failures", "n_bank_failures", unit="banks",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=1,
          normalization_scale=1.0),
        F("credit_to_gdp", "credit_to_gdp", unit="share", aggregation="last",
          window_ticks=30, frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=1.0),
        F("energy_price", "energy_price", unit="currency_per_unit", aggregation="mean",
          window_ticks=7, frequency_ticks=7, publication_lag_ticks=2,
          normalization_scale=1.0),
        F("energy_stock", "energy_stock_total", unit="energy_units",
          access_class="operational", roles=frozenset({"energy"}),
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1_000.0),
        F("energy_unfilled", "energy_unfilled", unit="energy_units",
          access_class="operational", roles=frozenset({"energy"}),
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=100.0),
        F("energy_subsidy_paid", "energy_subsidy_paid", unit="currency",
          aggregation="sum", window_ticks=30, frequency_ticks=30,
          publication_lag_ticks=7, normalization_scale=1_000.0),
        F("exchange_rate", "e", source="world", unit="numeraire_per_currency",
          economy_indexed=True, window_ticks=1, frequency_ticks=1,
          publication_lag_ticks=0, normalization_scale=1.0),
        F("current_account", "current_account", source="world", unit="currency",
          economy_indexed=True, aggregation="sum", window_ticks=30,
          frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=1_000.0),
        F("nfa", "nfa", source="world", unit="currency", economy_indexed=True,
          aggregation="last", window_ticks=30, frequency_ticks=30,
          publication_lag_ticks=7, normalization_scale=1_000.0),
        F("fx_reserves", "reserves_by_economy", source="world", unit="anchor_currency",
          access_class="operational", roles=frozenset({"central_bank"}),
          economy_indexed=True,
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1_000.0),
        F("migrant_stock", "migrant_stock", source="world", unit="persons",
          economy_indexed=True, aggregation="last", window_ticks=30,
          frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=100.0),
        F("remittances", "remittances", source="world", unit="currency",
          economy_indexed=True, aggregation="sum", window_ticks=30,
          frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=100.0),
        F("import_volume", "import_volume", source="world", unit="goods",
          economy_indexed=True, aggregation="sum", window_ticks=30,
          frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=100.0),
        F("export_volume", "export_shipped_volume", source="world", unit="goods",
          economy_indexed=True, aggregation="sum", window_ticks=30,
          frequency_ticks=30, publication_lag_ticks=7,
          normalization_scale=100.0),
        # v27: fixed numeric features for RL plus typed detail in
        # InstitutionObservation.shock_bulletins.  These query only shocks whose
        # announcement boundary has arrived; the future tape remains inaccessible.
        F("shock_announced_count", "announced_count", source="shock", unit="events",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1.0),
        F("shock_active_count", "active_count", source="shock", unit="events",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=1.0),
        F("shock_max_severity", "max_severity", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_time_to_next", "time_to_next", source="shock", unit="ticks",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=30.0),
        F("shock_productivity", "severity.productivity", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_labor_availability", "severity.labor_availability", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_energy_capacity", "severity.energy_capacity", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_household_demand", "severity.household_demand", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_import_capacity", "severity.import_capacity", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_export_capacity", "severity.export_capacity", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_credit_supply", "severity.credit_supply", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("shock_capital_destruction", "severity.capital_destruction", source="shock", unit="fraction",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=0.25),
        F("oracle_daily_output", "real_output", access_class="oracle",
          window_ticks=1, frequency_ticks=1, publication_lag_ticks=0,
          normalization_scale=100.0),
    ), schema_version=2)


DEFAULT_OBSERVATION_SPEC = default_observation_spec()
