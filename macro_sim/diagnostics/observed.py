"""Strict ingestion for versioned observed macroeconomic time series."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, TextIO

from macro_sim.diagnostics.registry import (
    DEFAULT_REGISTRY,
    ExternalSeriesCrosswalk,
    Frequency,
    MetricRegistry,
)


REQUIRED_COLUMNS = frozenset({
    "metric_id", "geography", "period", "frequency", "value", "unit",
    "source", "series_id", "vintage", "seasonal_adjustment",
})
OPTIONAL_COLUMNS = frozenset({"notes"})
SEASONAL_ADJUSTMENTS = frozenset({
    "seasonally_adjusted", "not_seasonally_adjusted", "trend_cycle", "not_applicable",
})
_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$")
_YEAR_RE = re.compile(r"^\d{4}$")


class ObservedDataError(ValueError):
    """A schema or row error that makes an observed dataset unsafe to use."""


@dataclass(frozen=True)
class ObservedRecord:
    metric_id: str
    geography: str
    period: str
    frequency: Frequency
    value: float
    unit: str
    source: str
    series_id: str
    vintage: date
    seasonal_adjustment: str
    notes: str = ""

    @property
    def identity(self) -> tuple[str, str, str, Frequency, str, str, date, str]:
        return (
            self.metric_id, self.geography, self.period, self.frequency,
            self.source, self.series_id, self.vintage, self.seasonal_adjustment,
        )


@dataclass(frozen=True)
class ObservedDataset:
    records: tuple[ObservedRecord, ...]
    registry: MetricRegistry

    def series(self, metric_id: str) -> tuple[ObservedRecord, ...]:
        return tuple(row for row in self.records if row.metric_id == metric_id)


def validate_period(period: str, frequency: Frequency) -> None:
    try:
        if frequency == Frequency.DAILY:
            parsed = date.fromisoformat(period)
            if parsed.isoformat() != period:
                raise ValueError
        elif frequency == Frequency.MONTHLY:
            if not _MONTH_RE.fullmatch(period):
                raise ValueError
        elif frequency == Frequency.QUARTERLY:
            if not _QUARTER_RE.fullmatch(period):
                raise ValueError
        elif frequency == Frequency.ANNUAL:
            if not _YEAR_RE.fullmatch(period):
                raise ValueError
            year = int(period)
            if not 1 <= year <= 9999:
                raise ValueError
        else:  # pragma: no cover - exhaustive guard for future enum additions
            raise ValueError
    except ValueError as exc:
        raise ObservedDataError(
            f"period {period!r} is invalid for frequency {frequency.value!r}"
        ) from exc


def _required_text(row: dict[str, str | None], name: str, row_number: int) -> str:
    value = row.get(name)
    if value is None or not value.strip():
        raise ObservedDataError(f"row {row_number}: {name} must be non-empty")
    if value != value.strip():
        raise ObservedDataError(f"row {row_number}: {name} has leading/trailing whitespace")
    return value


def _parse_row(
    row: dict[str, str | None], row_number: int, registry: MetricRegistry,
) -> tuple[ObservedRecord, ExternalSeriesCrosswalk]:
    metric_id = _required_text(row, "metric_id", row_number)
    geography = _required_text(row, "geography", row_number)
    period = _required_text(row, "period", row_number)
    frequency_text = _required_text(row, "frequency", row_number)
    unit = _required_text(row, "unit", row_number)
    source = _required_text(row, "source", row_number)
    series_id = _required_text(row, "series_id", row_number)
    vintage_text = _required_text(row, "vintage", row_number)
    seasonal = _required_text(row, "seasonal_adjustment", row_number)
    value_text = _required_text(row, "value", row_number)

    try:
        frequency = Frequency(frequency_text)
    except ValueError as exc:
        raise ObservedDataError(
            f"row {row_number}: unsupported frequency {frequency_text!r}"
        ) from exc
    validate_period(period, frequency)
    try:
        value = float(value_text)
    except ValueError as exc:
        raise ObservedDataError(f"row {row_number}: value is not numeric") from exc
    if not math.isfinite(value):
        raise ObservedDataError(f"row {row_number}: value must be finite")
    try:
        vintage = date.fromisoformat(vintage_text)
    except ValueError as exc:
        raise ObservedDataError(
            f"row {row_number}: vintage must be an ISO date (YYYY-MM-DD)"
        ) from exc
    if vintage.isoformat() != vintage_text:
        raise ObservedDataError(f"row {row_number}: vintage must use canonical ISO format")
    if seasonal not in SEASONAL_ADJUSTMENTS:
        raise ObservedDataError(
            f"row {row_number}: seasonal_adjustment {seasonal!r} is not recognized"
        )
    try:
        crosswalk = registry.resolve_crosswalk(
            metric_id, source=source, series_id=series_id, frequency=frequency,
            unit=unit, geography=geography, seasonal_adjustment=seasonal,
        )
    except (KeyError, ValueError) as exc:
        raise ObservedDataError(f"row {row_number}: {exc}") from exc

    return ObservedRecord(
        metric_id=metric_id, geography=geography, period=period,
        frequency=frequency, value=value, unit=unit, source=source,
        series_id=series_id, vintage=vintage, seasonal_adjustment=seasonal,
        notes=(row.get("notes") or "").strip(),
    ), crosswalk


def load_observed_csv(
    source: str | Path | TextIO,
    *,
    registry: MetricRegistry = DEFAULT_REGISTRY,
) -> ObservedDataset:
    """Load a provenance-complete CSV or fail before returning any records.

    Multiple vintages are allowed and intentionally preserved.  Exact duplicate
    identities are rejected; callers select a vintage during alignment.
    """

    close = False
    if isinstance(source, (str, Path)):
        stream: TextIO = Path(source).open("r", encoding="utf-8", newline="")
        close = True
    else:
        stream = source
    try:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ObservedDataError("CSV is missing a header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ObservedDataError("CSV contains duplicate column names")
        actual = set(reader.fieldnames)
        missing = REQUIRED_COLUMNS - actual
        unknown = actual - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
        if missing:
            raise ObservedDataError(f"CSV is missing required columns: {sorted(missing)}")
        if unknown:
            raise ObservedDataError(f"CSV contains unknown columns: {sorted(unknown)}")

        records: list[ObservedRecord] = []
        seen: set[tuple[str, str, str, Frequency, str, str, date, str]] = set()
        series_units: dict[tuple[str, str, str, str], str] = {}
        for row_number, row in enumerate(reader, start=2):
            record, _crosswalk = _parse_row(row, row_number, registry)
            if record.identity in seen:
                raise ObservedDataError(f"row {row_number}: duplicate observation identity")
            seen.add(record.identity)
            series_key = (
                record.metric_id, record.geography, record.source.casefold(),
                record.series_id.casefold(),
            )
            old_unit = series_units.setdefault(series_key, record.unit)
            if old_unit != record.unit:
                raise ObservedDataError(
                    f"row {row_number}: a source series changes units from {old_unit!r} "
                    f"to {record.unit!r}"
                )
            records.append(record)
    finally:
        if close:
            stream.close()

    if not records:
        raise ObservedDataError("CSV contains no observations")
    records.sort(key=lambda item: (
        item.metric_id, item.geography, item.source.casefold(),
        item.series_id.casefold(), item.period, item.vintage,
    ))
    return ObservedDataset(tuple(records), registry)


def observation_values_in_simulator_units(
    records: Iterable[ObservedRecord], registry: MetricRegistry = DEFAULT_REGISTRY,
) -> tuple[tuple[ObservedRecord, float], ...]:
    """Convert selected observed series, including lagged/derived transforms.

    Records are grouped by their complete provenance.  Sequence transforms require
    one selected vintage per period in each group and may omit warm-up periods for
    which the registered lag is unavailable.
    """

    grouped: dict[
        tuple[str, str, str, Frequency, str, str, str],
        list[tuple[ObservedRecord, ExternalSeriesCrosswalk]],
    ] = {}
    for row in records:
        crosswalk = registry.resolve_crosswalk(
            row.metric_id, source=row.source, series_id=row.series_id,
            frequency=row.frequency, unit=row.unit, geography=row.geography,
            seasonal_adjustment=row.seasonal_adjustment,
        )
        key = (
            row.metric_id, row.geography.casefold(), row.source.casefold(),
            row.frequency, row.unit, row.series_id.casefold(),
            row.seasonal_adjustment,
        )
        grouped.setdefault(key, []).append((row, crosswalk))

    converted: list[tuple[ObservedRecord, float]] = []
    for group in grouped.values():
        group.sort(key=lambda item: item[0].period)
        crosswalk = group[0][1]
        values = dict(crosswalk.apply_series(
            (row.period, row.value) for row, _item in group
        ))
        converted.extend(
            (row, values[row.period])
            for row, _item in group
            if row.period in values
        )
    converted.sort(key=lambda item: (
        item[0].metric_id, item[0].geography.casefold(),
        item[0].source.casefold(), item[0].series_id.casefold(), item[0].period,
    ))
    return tuple(converted)
