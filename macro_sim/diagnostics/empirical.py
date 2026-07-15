"""Calendar aggregation, empirical alignment, and distance diagnostics."""

from __future__ import annotations

import calendar
import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

import numpy as np

from macro_sim.diagnostics.observed import ObservedDataset, ObservedRecord
from macro_sim.diagnostics.registry import (
    Aggregation,
    Annualization,
    ComparisonMode,
    DEFAULT_REGISTRY,
    ExternalSeriesCrosswalk,
    Frequency,
    MetricRegistry,
    MetricSpec,
    TrustStatus,
    ValueTransform,
)


@dataclass(frozen=True)
class DailyValue:
    day: date
    value: float


@dataclass(frozen=True)
class SimulationTimelineRow:
    """One validated simulator row with its post-burn empirical calendar day."""

    tick: int
    day: date
    record: dict[str, Any]


@dataclass(frozen=True)
class SimulationTimeline:
    """A once-validated, contiguous simulator timeline shared by every series."""

    rows: tuple[SimulationTimelineRow, ...]
    tick_field: str
    tick_origin: int
    burn_in_ticks: int
    cutoff_tick: int
    raw_tick_start: int
    raw_tick_end: int
    retained_tick_start: int
    retained_tick_end: int
    discarded_row_count: int
    calendar_start_date: date
    calendar_end_date: date

    def metadata(self) -> dict[str, Any]:
        return {
            "tick_field": self.tick_field,
            "tick_origin": self.tick_origin,
            "burn_in_ticks": self.burn_in_ticks,
            "cutoff_tick": self.cutoff_tick,
            "raw_tick_range": [self.raw_tick_start, self.raw_tick_end],
            "raw_row_count": self.raw_tick_end - self.raw_tick_start + 1,
            "retained_tick_range": [
                self.retained_tick_start, self.retained_tick_end,
            ],
            "retained_row_count": len(self.rows),
            "discarded_row_count": self.discarded_row_count,
            "calendar_start_date": self.calendar_start_date,
            "calendar_end_date": self.calendar_end_date,
            "calendar_mapping": "cutoff_tick_maps_to_simulation_start_date",
        }


@dataclass(frozen=True)
class AggregatedValue:
    metric_id: str
    period: str
    frequency: Frequency
    value: float
    n_observations: int
    expected_observations: int
    complete: bool


@dataclass(frozen=True)
class AlignedPoint:
    period: str
    simulated: float
    observed: float
    observed_vintage: date
    source: str
    series_id: str
    comparison_mode: ComparisonMode
    crosswalk_caveats: tuple[str, ...] = ()
    simulated_complete: bool = True
    simulated_n_observations: int | None = None
    simulated_expected_observations: int | None = None
    frequency: Frequency | None = None


@dataclass(frozen=True)
class SeriesMoments:
    mean: float
    standard_deviation: float
    coefficient_of_variation: float
    lag1_autocorrelation: float
    linear_trend_per_period: float
    mean_log_growth: float
    volatility_log_growth: float


@dataclass(frozen=True)
class EmpiricalDiagnostic:
    metric_id: str
    comparison_mode: ComparisonMode
    n_aligned: int
    observed_moments: SeriesMoments
    simulated_moments: SeriesMoments
    mean_bias: float
    mean_absolute_error: float
    root_mean_squared_error: float
    normalized_rmse: float
    standardized_rmse: float
    correlation: float
    first_difference_correlation: float
    trust_status: str
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmpiricalSymptomFinding:
    """A descriptive model/data mismatch and the next diagnostic routes.

    These findings deliberately stop at symptoms.  ``root_cause_ids`` are existing
    dynamic issue/ablation identifiers worth testing next, not causes inferred from
    an observational fit statistic.
    """

    issue_id: str
    severity: str
    confidence: str
    category: str
    claim: str
    metric_id: str
    comparison_mode: ComparisonMode
    evidence: dict[str, float | int | str | None]
    thresholds: dict[str, float | int]
    measurement_status: str
    caveats: tuple[str, ...]
    probe_ids: tuple[str, ...]
    root_cause_ids: tuple[str, ...]
    ablation_ids: tuple[str, ...]
    inference_scope: str = "descriptive_non_causal"


@dataclass(frozen=True)
class EmpiricalSymptomClassification:
    """Result of applying conservative, comparison-mode-aware screening gates."""

    status: str
    metric_id: str
    comparison_mode: ComparisonMode
    n_aligned: int
    n_comparison_observations: int
    minimum_comparison_observations: int
    minimum_comparison_observations_basis: str
    comparison_frequency: Frequency | None
    level_calibration_allowed: bool
    measurement_status: str
    caveats: tuple[str, ...]
    probe_ids: tuple[str, ...]
    root_cause_ids: tuple[str, ...]
    ablation_ids: tuple[str, ...]
    findings: tuple[EmpiricalSymptomFinding, ...]
    inference_scope: str = "descriptive_non_causal"


# Every identifier below already exists in the runtime analysis or root-cause
# matrix.  The mapping is a route for follow-up probes, never a causal conclusion.
_EMPIRICAL_DIAGNOSTIC_ROUTES: dict[
    str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]
] = {
    "real_gdp": (
        (
            "growth_accounting", "sector_output_decomposition", "three_way_gdp",
            "sector_flow_of_funds", "production_constraint_decomposition",
            "investment_order_remainders", "K_sector_footfall",
        ),
        (
            "macro.implausible_per_capita_growth",
            "growth.public_capital_scale_explosion",
            "production.plan_realization_failure",
            "investment.plan_realization_failure",
        ),
        (
            "no_exogenous_tfp", "no_public_capital_system", "no_gov_investment",
            "no_public_productivity", "no_jg_capital", "spot_labor",
            "no_bank_capital_cap",
        ),
    ),
    "nominal_gdp": (
        (
            "three_way_gdp", "sector_flow_of_funds", "growth_accounting",
            "sector_output_decomposition", "price_decomposition",
            "production_constraint_decomposition",
        ),
        (
            "accounting.national_accounts_reconciliation_drift",
            "macro.implausible_per_capita_growth",
            "macro.persistent_price_instability",
            "production.plan_realization_failure",
        ),
        (
            "no_exogenous_tfp", "no_public_capital_system", "no_gov_investment",
            "spot_labor", "no_bank_capital_cap",
        ),
    ),
    "cpi_fixed_basket": (
        (
            "fixed_basket_cpi", "price_mix_counterfactual", "price_decomposition",
            "nominal_anchor_ablation", "energy_order_book", "coverage_distribution",
        ),
        (
            "macro.persistent_price_instability", "measurement.price_composition",
            "energy.structural_rationing",
        ),
        (),
    ),
    "cpi_fixed_basket_inflation_yoy": (
        (
            "fixed_basket_cpi", "price_mix_counterfactual", "price_decomposition",
            "nominal_anchor_ablation", "energy_order_book", "coverage_distribution",
        ),
        (
            "macro.persistent_price_instability", "measurement.price_composition",
            "energy.structural_rationing",
        ),
        (),
    ),
    "person_unemployment_rate": (
        (
            "labor_constraint_decomposition", "demand_stimulus_twin", "jg_off_twin",
            "private_vacancy_and_cash_constraint_decomposition",
            "spot_vs_persistent_twin", "K_firm_count_scale_sweep",
        ),
        (
            "labor.chronic_slack", "labor.large_job_guarantee_buffer",
            "labor.whole_person_k_sector_deadlock",
        ),
        ("no_job_guarantee", "spot_labor", "no_bank_capital_cap"),
    ),
    "labor_u_rate": (
        (
            "labor_constraint_decomposition", "demand_stimulus_twin", "jg_off_twin",
            "private_vacancy_and_cash_constraint_decomposition",
            "spot_vs_persistent_twin", "K_firm_count_scale_sweep",
        ),
        (
            "labor.chronic_slack", "labor.large_job_guarantee_buffer",
            "labor.whole_person_k_sector_deadlock",
        ),
        ("no_job_guarantee", "spot_labor", "no_bank_capital_cap"),
    ),
    "policy_rate": (
        (
            "price_decomposition", "nominal_anchor_ablation", "firm_headroom_distribution",
            "binding_constraint_share", "bank_capital_bridge",
        ),
        (
            "macro.persistent_price_instability", "credit.productive_assets_excluded",
            "banking.rwa_capital_breach",
        ),
        ("no_bank_capital_cap",),
    ),
}


_SYMPTOM_THRESHOLDS: dict[str, float | int] = {
    "minimum_comparison_observations": 8,
    "normalized_rmse_warning": 0.75,
    "normalized_rmse_high": 1.50,
    "correlation_warning_below": 0.40,
    "correlation_high_below": 0.0,
    "normalized_mean_gap_warning": 0.50,
    "normalized_mean_gap_high": 1.00,
    "absolute_log_std_ratio_warning": math.log(2.0),
    "absolute_log_std_ratio_high": math.log(4.0),
}


class CalendarCadenceError(ValueError):
    """Aligned observations skip a calendar period needed by lag/difference statistics."""


def _period_for_day(day: date, frequency: Frequency) -> str:
    if frequency == Frequency.DAILY:
        return day.isoformat()
    if frequency == Frequency.MONTHLY:
        return f"{day.year:04d}-{day.month:02d}"
    if frequency == Frequency.QUARTERLY:
        return f"{day.year:04d}-Q{(day.month - 1) // 3 + 1}"
    if frequency == Frequency.ANNUAL:
        return f"{day.year:04d}"
    raise AssertionError(f"unhandled frequency {frequency!r}")


def _expected_days(period: str, frequency: Frequency) -> int:
    if frequency == Frequency.DAILY:
        return 1
    if frequency == Frequency.MONTHLY:
        year, month = map(int, period.split("-"))
        return calendar.monthrange(year, month)[1]
    if frequency == Frequency.QUARTERLY:
        year_text, quarter_text = period.split("-Q")
        year, quarter = int(year_text), int(quarter_text)
        return sum(calendar.monthrange(year, month)[1] for month in range(3 * quarter - 2, 3 * quarter + 1))
    if frequency == Frequency.ANNUAL:
        return 366 if calendar.isleap(int(period)) else 365
    raise AssertionError(f"unhandled frequency {frequency!r}")


def _strict_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.lstrip("+-").isdigit():
            raise ValueError(f"{label} must be an integer")
    elif value != converted:
        raise ValueError(f"{label} must be an integer")
    return converted


def prepare_simulation_timeline(
    records: Iterable[dict[str, Any]],
    *,
    start_date: date,
    tick_field: str = "t",
    tick_origin: int = 0,
    burn_in_ticks: int = 0,
) -> SimulationTimeline:
    """Validate ticks once, discard genesis, and attach the empirical calendar.

    ``start_date`` is the date of the first retained (post-burn) observation.  Raw
    simulator tick labels remain in every row for provenance; only their calendar
    origin is rebased.
    """

    origin = _strict_integer(tick_origin, label="tick_origin")
    burn = _strict_integer(burn_in_ticks, label="burn_in_ticks")
    if origin < 0:
        raise ValueError("tick_origin must be non-negative")
    if burn < 0:
        raise ValueError("burn_in_ticks must be non-negative")
    if not tick_field:
        raise ValueError("tick_field must be non-empty")

    indexed: list[tuple[int, dict[str, Any]]] = []
    seen_ticks: set[int] = set()
    for row_number, record in enumerate(records, start=1):
        if tick_field not in record:
            raise ValueError(f"simulation row {row_number} lacks {tick_field!r}")
        tick = _strict_integer(
            record[tick_field], label=f"simulation row {row_number} tick",
        )
        if tick < 0:
            raise ValueError(f"simulation row {row_number} has negative tick {tick}")
        if tick in seen_ticks:
            raise ValueError(f"simulation row {row_number} has duplicate tick {tick}")
        seen_ticks.add(tick)
        indexed.append((tick, record))
    if not indexed:
        raise ValueError("simulation timeline contains no records")

    indexed.sort(key=lambda item: item[0])
    ticks = [tick for tick, _record in indexed]
    if ticks[0] != origin:
        raise ValueError(
            f"simulation ticks must start at tick_origin {origin}; found {ticks[0]}"
        )
    for previous, current in zip(ticks, ticks[1:]):
        if current != previous + 1:
            raise ValueError(
                "simulation ticks must form a complete contiguous range from "
                f"tick_origin {origin}; missing tick {previous + 1} before {current}"
            )
    if burn >= len(indexed):
        raise ValueError(
            f"burn_in_ticks ({burn}) must be smaller than the simulation row count "
            f"({len(indexed)})"
        )

    cutoff = origin + burn
    retained = indexed[burn:]
    try:
        timeline_rows = tuple(
            SimulationTimelineRow(
                tick=tick,
                day=start_date + timedelta(days=tick - cutoff),
                record=record,
            )
            for tick, record in retained
        )
    except OverflowError as exc:
        raise ValueError("simulation calendar range exceeds supported dates") from exc
    return SimulationTimeline(
        rows=timeline_rows,
        tick_field=tick_field,
        tick_origin=origin,
        burn_in_ticks=burn,
        cutoff_tick=cutoff,
        raw_tick_start=ticks[0],
        raw_tick_end=ticks[-1],
        retained_tick_start=timeline_rows[0].tick,
        retained_tick_end=timeline_rows[-1].tick,
        discarded_row_count=burn,
        calendar_start_date=timeline_rows[0].day,
        calendar_end_date=timeline_rows[-1].day,
    )


def simulation_daily_values(
    records: Iterable[dict[str, Any]] | SimulationTimeline,
    metric_id: str,
    *,
    start_date: date | None = None,
    tick_field: str = "t",
    tick_origin: int = 0,
    burn_in_ticks: int = 0,
) -> tuple[DailyValue, ...]:
    """Extract one metric from a validated timeline.

    Passing raw records remains supported for callers outside the CLI, but the CLI
    prepares one :class:`SimulationTimeline` and reuses it for every metric.
    """

    if isinstance(records, SimulationTimeline):
        timeline = records
    else:
        if start_date is None:
            raise ValueError("start_date is required for raw simulation records")
        timeline = prepare_simulation_timeline(
            records,
            start_date=start_date,
            tick_field=tick_field,
            tick_origin=tick_origin,
            burn_in_ticks=burn_in_ticks,
        )

    values: list[DailyValue] = []
    for row in timeline.rows:
        if metric_id not in row.record:
            raise ValueError(
                f"simulation tick {row.tick} lacks metric {metric_id!r}"
            )
        try:
            value = float(row.record[metric_id])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"simulation tick {row.tick} has a non-numeric {metric_id!r} value"
            ) from exc
        if not math.isfinite(value):
            raise ValueError(
                f"simulation tick {row.tick} has a non-finite {metric_id!r} value"
            )
        values.append(DailyValue(row.day, value))
    return tuple(values)


def aggregate_daily_series(
    values: Iterable[DailyValue],
    spec: MetricSpec,
    target_frequency: Frequency,
    *,
    require_complete: bool = False,
    crosswalk: ExternalSeriesCrosswalk | None = None,
) -> tuple[AggregatedValue, ...]:
    """Aggregate daily values according to the registered economic semantics.

    Flows sum, stocks take the calendar-period end, rates use their declared mean
    or compound rule, and indexes use their declared end/mean rule.  Partial periods
    are either retained with ``complete=False`` or dropped when ``require_complete``.
    """

    order = {
        Frequency.DAILY: 0, Frequency.MONTHLY: 1,
        Frequency.QUARTERLY: 2, Frequency.ANNUAL: 3,
    }
    if order[target_frequency] < order[spec.native_frequency]:
        raise ValueError("cannot upsample a metric with this aggregator")
    if crosswalk is not None and crosswalk.frequency != target_frequency:
        raise ValueError("crosswalk frequency does not match the requested aggregation frequency")
    if crosswalk is not None and crosswalk not in spec.crosswalks:
        raise ValueError("crosswalk is not registered for this simulator metric")
    by_period: dict[str, list[DailyValue]] = {}
    seen_days: set[date] = set()
    for item in values:
        if item.day in seen_days:
            raise ValueError(f"duplicate simulation day {item.day.isoformat()}")
        seen_days.add(item.day)
        if not math.isfinite(item.value):
            raise ValueError(f"non-finite simulation value on {item.day.isoformat()}")
        by_period.setdefault(_period_for_day(item.day, target_frequency), []).append(item)

    result: list[AggregatedValue] = []
    for period in sorted(by_period):
        points = sorted(by_period[period], key=lambda item: item.day)
        raw = np.asarray([item.value for item in points], dtype=float)
        if spec.aggregation == Aggregation.SUM:
            value = float(np.sum(raw))
        elif spec.aggregation == Aggregation.END:
            value = float(raw[-1])
        elif spec.aggregation == Aggregation.MEAN:
            value = float(np.mean(raw))
        elif spec.aggregation == Aggregation.COMPOUND:
            if np.any(raw <= -1.0):
                raise ValueError(f"cannot compound a rate <= -100% in {period}")
            value = float(np.prod(1.0 + raw) - 1.0)
        else:  # pragma: no cover
            raise AssertionError(f"unhandled aggregation {spec.aggregation!r}")
        expected = _expected_days(period, target_frequency)
        # National-accounts level series such as GDP are commonly published at a
        # seasonally-adjusted annual rate.  A sum of model-day flows must be put on
        # the same clock; otherwise different month/quarter lengths create mechanical
        # growth.  Daily output remains in its native per-day unit.
        if (
            crosswalk is not None
            and crosswalk.target_annualization == Annualization.SUM_DAILY_FLOWS
            and target_frequency != Frequency.DAILY
            and len(points) > 0
        ):
            value *= 365.0 / len(points)
        complete = len(points) == expected
        if not require_complete or complete:
            result.append(AggregatedValue(
                spec.metric_id, period, target_frequency, value,
                len(points), expected, complete,
            ))
    return tuple(result)


def _monthly_ordinal(period: str) -> int:
    try:
        year_text, month_text = period.split("-")
        year, month = int(year_text), int(month_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid monthly period {period!r}") from exc
    if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12:
        raise ValueError(f"invalid monthly period {period!r}")
    return year * 12 + month - 1


def transform_simulated_aggregates(
    values: Iterable[AggregatedValue],
    *,
    target_metric_id: str,
    crosswalk: ExternalSeriesCrosswalk,
) -> tuple[AggregatedValue, ...]:
    """Apply the crosswalk's registered model-side sequence transform.

    For exact-month YoY, completeness depends on both the current and t-12 level
    months.  The derived observation therefore carries their combined coverage;
    an incomplete lag cannot masquerade as a complete inflation observation.
    """

    source = tuple(sorted(values, key=lambda item: item.period))
    if not source:
        return ()
    if any(item.frequency != crosswalk.frequency for item in source):
        raise ValueError("simulation aggregate frequency does not match crosswalk")
    periods = [item.period for item in source]
    if len(periods) != len(set(periods)):
        raise ValueError("simulation transform requires one aggregate per period")

    converted = dict(crosswalk.apply_simulation_series(
        (item.period, item.value) for item in source
    ))
    by_period = {item.period: item for item in source}
    by_month = (
        {_monthly_ordinal(item.period): item for item in source}
        if crosswalk.simulation_transform == ValueTransform.MONTHLY_INDEX_TO_YOY
        else {}
    )
    result: list[AggregatedValue] = []
    for period in sorted(converted):
        current = by_period[period]
        dependencies = [current]
        if crosswalk.simulation_transform == ValueTransform.MONTHLY_INDEX_TO_YOY:
            lagged = by_month.get(_monthly_ordinal(period) - 12)
            if lagged is None:  # Defensive: the registered transform omits this case.
                continue
            dependencies.append(lagged)
        value = float(converted[period])
        if not math.isfinite(value):
            raise ValueError(f"simulation transform produced non-finite value in {period}")
        result.append(AggregatedValue(
            metric_id=target_metric_id,
            period=period,
            frequency=current.frequency,
            value=value,
            n_observations=sum(item.n_observations for item in dependencies),
            expected_observations=sum(
                item.expected_observations for item in dependencies
            ),
            complete=all(item.complete for item in dependencies),
        ))
    return tuple(result)


def select_observed_series(
    dataset: ObservedDataset,
    metric_id: str,
    *,
    geography: str,
    source: str | None = None,
    series_id: str | None = None,
    frequency: Frequency | None = None,
    unit: str | None = None,
    seasonal_adjustment: str | None = None,
    vintage: date | str = "latest",
) -> tuple[ObservedRecord, ...]:
    """Select one provenance-homogeneous series and one vintage per period."""

    candidates = [
        row for row in dataset.records
        if row.metric_id == metric_id and row.geography.casefold() == geography.casefold()
        and (source is None or row.source.casefold() == source.casefold())
        and (series_id is None or row.series_id.casefold() == series_id.casefold())
        and (frequency is None or row.frequency == frequency)
        and (unit is None or row.unit == unit)
        and (seasonal_adjustment is None or row.seasonal_adjustment == seasonal_adjustment)
    ]
    if not candidates:
        raise ValueError(f"no observed records match {metric_id!r} in {geography!r}")
    provenances = {
        (row.source.casefold(), row.series_id.casefold(), row.frequency,
         row.unit, row.seasonal_adjustment)
        for row in candidates
    }
    if len(provenances) != 1:
        raise ValueError(
            "selection contains multiple source/series/frequency/unit/seasonal-adjustment "
            "combinations; add filters"
        )

    if vintage != "latest" and not isinstance(vintage, date):
        raise ValueError("vintage must be 'latest' or a datetime.date")
    by_period: dict[str, list[ObservedRecord]] = {}
    for row in candidates:
        if vintage == "latest" or row.vintage <= vintage:
            by_period.setdefault(row.period, []).append(row)
    if not by_period:
        raise ValueError("no observations are available at the requested vintage")
    return tuple(
        max(rows, key=lambda row: row.vintage)
        for _period, rows in sorted(by_period.items())
    )


def align_observed_simulated(
    simulated: Iterable[AggregatedValue],
    observed: Sequence[ObservedRecord],
    *,
    registry: MetricRegistry = DEFAULT_REGISTRY,
    require_complete_simulation_periods: bool = True,
) -> tuple[AlignedPoint, ...]:
    if not observed:
        raise ValueError("observed series is empty")
    metric_id = observed[0].metric_id
    frequency = observed[0].frequency
    if any(row.metric_id != metric_id or row.frequency != frequency for row in observed):
        raise ValueError("observed records must contain one metric and frequency")
    provenances = {
        (
            row.source.casefold(), row.series_id.casefold(), row.geography.casefold(),
            row.unit, row.seasonal_adjustment,
        )
        for row in observed
    }
    if len(provenances) != 1:
        raise ValueError(
            "observed records must contain one source/series/geography/unit/"
            "seasonal-adjustment provenance"
        )
    resolved: list[tuple[ObservedRecord, ExternalSeriesCrosswalk]] = []
    seen_observed_periods: set[str] = set()
    for row in observed:
        crosswalk = registry.resolve_crosswalk(
            metric_id, source=row.source, series_id=row.series_id,
            frequency=row.frequency, unit=row.unit, geography=row.geography,
            seasonal_adjustment=row.seasonal_adjustment,
        )
        if row.period in seen_observed_periods:
            raise ValueError("observed records must have one selected vintage per period")
        seen_observed_periods.add(row.period)
        resolved.append((row, crosswalk))
    crosswalk = resolved[0][1]
    if any(item != crosswalk for _row, item in resolved[1:]):
        raise ValueError("observed records must resolve to one registered crosswalk")
    converted = dict(crosswalk.apply_series(
        (row.period, row.value) for row, _item in resolved
    ))
    obs_by_period: dict[str, tuple[ObservedRecord, float, ExternalSeriesCrosswalk]] = {
        row.period: (row, converted[row.period], crosswalk)
        for row, _item in resolved
        if row.period in converted
    }

    aligned: list[AlignedPoint] = []
    seen_sim_periods: set[str] = set()
    for item in sorted(simulated, key=lambda value: value.period):
        if item.metric_id != metric_id or item.frequency != frequency:
            raise ValueError("simulation aggregate metric/frequency does not match observations")
        if item.period in seen_sim_periods:
            raise ValueError(f"duplicate simulated period {item.period!r}")
        seen_sim_periods.add(item.period)
        if require_complete_simulation_periods and not item.complete:
            continue
        pair = obs_by_period.get(item.period)
        if pair is not None:
            row, observed_value, crosswalk = pair
            aligned.append(AlignedPoint(
                item.period, item.value, observed_value, row.vintage,
                row.source, row.series_id, crosswalk.comparison_mode,
                crosswalk.caveats, item.complete, item.n_observations,
                item.expected_observations, frequency,
            ))
    return tuple(aligned)


def _infer_period_frequency(period: str) -> Frequency | None:
    if "-Q" in period:
        return Frequency.QUARTERLY
    if len(period) == 7 and period[4] == "-":
        return Frequency.MONTHLY
    if len(period) == 10 and period[4] == "-" and period[7] == "-":
        return Frequency.DAILY
    if len(period) == 4 and period.isdigit():
        return Frequency.ANNUAL
    return None


def _aligned_frequency(aligned: Sequence[AlignedPoint]) -> Frequency | None:
    declared = {point.frequency for point in aligned if point.frequency is not None}
    if len(declared) > 1:
        raise CalendarCadenceError("aligned points declare multiple frequencies")
    if declared:
        frequency = next(iter(declared))
        if any(
            point.frequency not in (None, frequency) for point in aligned
        ):  # pragma: no cover - guarded by the set above
            raise CalendarCadenceError("aligned points declare multiple frequencies")
        return frequency
    inferred = {_infer_period_frequency(point.period) for point in aligned}
    inferred.discard(None)
    return next(iter(inferred)) if len(inferred) == 1 else None


def _period_ordinal(period: str, frequency: Frequency) -> int:
    if frequency == Frequency.DAILY:
        try:
            return date.fromisoformat(period).toordinal()
        except ValueError as exc:
            raise CalendarCadenceError(f"invalid daily period {period!r}") from exc
    if frequency == Frequency.MONTHLY:
        try:
            return _monthly_ordinal(period)
        except ValueError as exc:
            raise CalendarCadenceError(str(exc)) from exc
    if frequency == Frequency.QUARTERLY:
        try:
            year_text, quarter_text = period.split("-Q")
            year, quarter = int(year_text), int(quarter_text)
        except (TypeError, ValueError) as exc:
            raise CalendarCadenceError(f"invalid quarterly period {period!r}") from exc
        if len(year_text) != 4 or quarter not in (1, 2, 3, 4):
            raise CalendarCadenceError(f"invalid quarterly period {period!r}")
        return year * 4 + quarter - 1
    if frequency == Frequency.ANNUAL:
        if len(period) != 4 or not period.isdigit():
            raise CalendarCadenceError(f"invalid annual period {period!r}")
        return int(period)
    raise AssertionError(f"unhandled frequency {frequency!r}")


def validate_aligned_cadence(
    aligned: Sequence[AlignedPoint],
) -> Frequency | None:
    """Reject calendar gaps before any lag, trend, or difference is computed."""

    if len(aligned) < 2:
        return _aligned_frequency(aligned)
    frequency = _aligned_frequency(aligned)
    if frequency is None:
        # Synthetic API callers may use abstract labels.  Real alignment always
        # carries an explicit observed frequency and is therefore fail-closed.
        return None
    for previous, current in zip(aligned, aligned[1:]):
        if _period_ordinal(current.period, frequency) != (
            _period_ordinal(previous.period, frequency) + 1
        ):
            raise CalendarCadenceError(
                f"aligned {frequency.value} periods are not contiguous: "
                f"{previous.period!r} is followed by {current.period!r}; "
                "lag and difference statistics would bridge a calendar gap"
            )
    return frequency


def _safe_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or np.std(left) <= 1e-15 or np.std(right) <= 1e-15:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def _moments(values: np.ndarray) -> SeriesMoments:
    n = values.size
    mean = float(np.mean(values))
    std = float(np.std(values))
    cv = std / abs(mean) if abs(mean) > 1e-15 else float("nan")
    lag1 = _safe_correlation(values[:-1], values[1:]) if n > 1 else float("nan")
    if n > 1:
        x = np.arange(n, dtype=float)
        trend = float(np.polyfit(x, values, 1)[0])
    else:
        trend = float("nan")
    if n > 1 and np.all(values > 0.0):
        growth = np.diff(np.log(values))
        mean_growth = float(np.mean(growth))
        growth_vol = float(np.std(growth))
    else:
        mean_growth = growth_vol = float("nan")
    return SeriesMoments(mean, std, cv, lag1, trend, mean_growth, growth_vol)


def _comparison_arrays(
    simulated: np.ndarray, observed: np.ndarray, mode: ComparisonMode,
) -> tuple[np.ndarray, np.ndarray]:
    if mode == ComparisonMode.LEVELS:
        return simulated, observed
    if mode == ComparisonMode.STANDARDIZED:
        sim_std = float(np.std(simulated))
        obs_std = float(np.std(observed))
        if sim_std <= 1e-15 or obs_std <= 1e-15:
            raise ValueError("standardized comparison requires variation in both series")
        return (
            (simulated - np.mean(simulated)) / sim_std,
            (observed - np.mean(observed)) / obs_std,
        )
    if mode == ComparisonMode.LOG_CHANGES:
        if np.any(simulated <= 0.0) or np.any(observed <= 0.0):
            raise ValueError("log-change comparison requires strictly positive series")
        if simulated.size < 2:
            raise ValueError("log-change comparison requires at least two aligned periods")
        return np.diff(np.log(simulated)), np.diff(np.log(observed))
    if mode == ComparisonMode.REBASED_INDEX:
        if simulated[0] == 0.0 or observed[0] == 0.0:
            raise ValueError("index rebasing requires non-zero initial values")
        return simulated / simulated[0] * 100.0, observed / observed[0] * 100.0
    raise AssertionError(f"unhandled comparison mode {mode!r}")


def diagnose_empirical_fit(
    aligned: Sequence[AlignedPoint],
    metric_id: str,
    *,
    registry: MetricRegistry = DEFAULT_REGISTRY,
    comparison_mode: ComparisonMode | None = None,
) -> EmpiricalDiagnostic:
    """Compute scale-aware distances and core time-series moment discrepancies."""

    if len(aligned) < 2:
        raise ValueError("at least two aligned periods are required")
    spec = registry.get(metric_id)
    periods = [point.period for point in aligned]
    if len(periods) != len(set(periods)):
        raise ValueError("aligned periods must be unique")
    if periods != sorted(periods):
        raise ValueError("aligned periods must be in chronological order")
    validate_aligned_cadence(aligned)
    provenances = {
        (point.source.casefold(), point.series_id.casefold(), point.comparison_mode)
        for point in aligned
    }
    if len(provenances) != 1:
        raise ValueError("aligned points must retain one source/series/comparison mode")
    simulated_raw = np.asarray([point.simulated for point in aligned], dtype=float)
    observed_raw = np.asarray([point.observed for point in aligned], dtype=float)
    if not np.all(np.isfinite(simulated_raw)) or not np.all(np.isfinite(observed_raw)):
        raise ValueError("aligned values must be finite")

    if comparison_mode is None:
        comparison_mode = aligned[0].comparison_mode
    simulated, observed = _comparison_arrays(simulated_raw, observed_raw, comparison_mode)
    errors = simulated - observed
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    obs_scale = float(np.std(observed))
    if obs_scale <= 1e-15:
        obs_scale = abs(float(np.mean(observed)))
    nrmse = rmse / obs_scale if obs_scale > 1e-15 else float("nan")

    sim_std = float(np.std(simulated))
    obs_std = float(np.std(observed))
    if sim_std > 1e-15 and obs_std > 1e-15:
        sim_z = (simulated - np.mean(simulated)) / sim_std
        obs_z = (observed - np.mean(observed)) / obs_std
        standardized_rmse = float(np.sqrt(np.mean((sim_z - obs_z) ** 2)))
    else:
        standardized_rmse = float("nan")

    caveats = list(spec.caveats)
    for point in aligned:
        for caveat in point.crosswalk_caveats:
            if caveat not in caveats:
                caveats.append(caveat)
    registered_mode = aligned[0].comparison_mode
    if comparison_mode != registered_mode:
        caveats.append(
            f"Comparison mode was explicitly overridden from the registered "
            f"{registered_mode.value!r} mode to {comparison_mode.value!r}."
        )
    if any(not point.simulated_complete for point in aligned):
        caveats.append(
            "At least one observed period is compared with an incomplete simulator "
            "calendar period; level and growth distances may be mechanically biased."
        )

    return EmpiricalDiagnostic(
        metric_id=metric_id,
        comparison_mode=comparison_mode,
        n_aligned=len(aligned),
        observed_moments=_moments(observed_raw),
        simulated_moments=_moments(simulated_raw),
        mean_bias=float(np.mean(errors)),
        mean_absolute_error=float(np.mean(np.abs(errors))),
        root_mean_squared_error=rmse,
        normalized_rmse=nrmse,
        standardized_rmse=standardized_rmse,
        correlation=_safe_correlation(simulated, observed),
        first_difference_correlation=(
            _safe_correlation(simulated, observed)
            if comparison_mode == ComparisonMode.LOG_CHANGES
            else (
                _safe_correlation(np.diff(simulated), np.diff(observed))
                if simulated.size > 2 else float("nan")
            )
        ),
        trust_status=spec.trust_status.value,
        caveats=tuple(caveats),
    )


def _measurement_status(spec: MetricSpec) -> str:
    if spec.trust_status == TrustStatus.VALIDATED:
        return "valid_with_scope_caveats"
    if spec.trust_status == TrustStatus.PROXY:
        return "proxy_not_calibration"
    if spec.trust_status == TrustStatus.EXPERIMENTAL:
        return "experimental_not_calibration"
    return "blocked_by_invalid_measurement"


def _diagnostic_route(
    metric_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    return _EMPIRICAL_DIAGNOSTIC_ROUTES.get(metric_id, ((), (), ()))


def _minimum_comparison_sample(
    frequency: Frequency | None,
    mode: ComparisonMode,
) -> tuple[int, str]:
    if frequency == Frequency.MONTHLY:
        return (
            24,
            "monthly comparisons require at least 24 post-transform observations "
            "to cover two calendar years",
        )
    if frequency == Frequency.QUARTERLY and mode == ComparisonMode.LOG_CHANGES:
        return (
            12,
            "quarterly log-change comparisons require at least 12 growth "
            "observations (13 contiguous levels)",
        )
    minimum = int(_SYMPTOM_THRESHOLDS["minimum_comparison_observations"])
    label = frequency.value if frequency is not None else "unspecified-frequency"
    return (
        minimum,
        f"default {label} {mode.value} screening floor",
    )


def classify_empirical_symptoms(
    aligned: Sequence[AlignedPoint],
    diagnostic: EmpiricalDiagnostic,
    *,
    registry: MetricRegistry = DEFAULT_REGISTRY,
    registered_comparison_mode: ComparisonMode | None = None,
) -> EmpiricalSymptomClassification:
    """Screen an empirical fit for descriptive symptoms without claiming causality.

    The registered comparison mode is an economic measurement constraint.  An
    explicit CLI override remains available for exploratory distance calculations,
    but it cannot produce classified symptoms: in particular, overriding GDP from
    log changes to levels must never turn abstract model units into a calibration
    target.
    """

    if not aligned:
        raise ValueError("aligned series is empty")
    metric_id = diagnostic.metric_id
    spec = registry.get(metric_id)
    mode = diagnostic.comparison_mode
    if registered_comparison_mode is None:
        registered_comparison_mode = aligned[0].comparison_mode
    probes, root_causes, ablations = _diagnostic_route(metric_id)
    measurement_status = _measurement_status(spec)
    common_caveats = list(diagnostic.caveats)
    non_causal_caveat = (
        "Observed/model distances are descriptive symptoms only; they do not identify "
        "a causal mechanism or justify parameter calibration by themselves."
    )
    if non_causal_caveat not in common_caveats:
        common_caveats.append(non_causal_caveat)

    simulated_raw = np.asarray([point.simulated for point in aligned], dtype=float)
    observed_raw = np.asarray([point.observed for point in aligned], dtype=float)
    frequency = validate_aligned_cadence(aligned)
    simulated, observed = _comparison_arrays(simulated_raw, observed_raw, mode)
    n_comparison = int(simulated.size)
    minimum, minimum_basis = _minimum_comparison_sample(frequency, mode)
    level_calibration_allowed = (
        mode == ComparisonMode.LEVELS and spec.trust_status == TrustStatus.VALIDATED
        and registered_comparison_mode == ComparisonMode.LEVELS
    )

    def result(
        status: str, findings: Sequence[EmpiricalSymptomFinding] = (),
    ) -> EmpiricalSymptomClassification:
        return EmpiricalSymptomClassification(
            status=status,
            metric_id=metric_id,
            comparison_mode=mode,
            n_aligned=len(aligned),
            n_comparison_observations=n_comparison,
            minimum_comparison_observations=minimum,
            minimum_comparison_observations_basis=minimum_basis,
            comparison_frequency=frequency,
            level_calibration_allowed=level_calibration_allowed,
            measurement_status=measurement_status,
            caveats=tuple(common_caveats),
            probe_ids=probes,
            root_cause_ids=root_causes,
            ablation_ids=ablations,
            findings=tuple(findings),
        )

    if spec.trust_status == TrustStatus.LEGACY_INVALID:
        common_caveats.append(
            "The registered metric is legacy-invalid, so empirical symptom "
            "classification is blocked."
        )
        return result("blocked_by_invalid_measurement")
    if mode != registered_comparison_mode:
        common_caveats.append(
            "Classification is blocked because the requested comparison mode differs "
            "from the registered crosswalk mode."
        )
        return result("blocked_by_comparison_override")
    if n_comparison < minimum:
        common_caveats.append(
            f"Only {n_comparison} comparison observations are available; at least "
            f"{minimum} are required for symptom classification."
        )
        return result("insufficient_sample")

    obs_mean = float(np.mean(observed))
    sim_mean = float(np.mean(simulated))
    obs_std = float(np.std(observed))
    sim_std = float(np.std(simulated))
    mean_scale = max(abs(obs_mean), obs_std, 1e-12)
    normalized_mean_gap = abs(sim_mean - obs_mean) / mean_scale
    if obs_std <= 1e-15 and sim_std <= 1e-15:
        absolute_log_std_ratio = 0.0
    elif obs_std <= 1e-15 or sim_std <= 1e-15:
        absolute_log_std_ratio = float("inf")
    else:
        absolute_log_std_ratio = abs(math.log(sim_std / obs_std))

    shared_evidence: dict[str, float | int | str | None] = {
        "n_aligned": len(aligned),
        "n_comparison_observations": n_comparison,
        "normalized_rmse": diagnostic.normalized_rmse,
        "correlation": diagnostic.correlation,
        "simulated_comparison_mean": sim_mean,
        "observed_comparison_mean": obs_mean,
        "simulated_comparison_standard_deviation": sim_std,
        "observed_comparison_standard_deviation": obs_std,
        "normalized_mean_gap": normalized_mean_gap,
        "absolute_log_std_ratio": (
            absolute_log_std_ratio
            if math.isfinite(absolute_log_std_ratio)
            else "infinite_one_series_is_constant"
        ),
        "comparison_domain": mode.value,
    }
    if not math.isfinite(diagnostic.normalized_rmse):
        common_caveats.append(
            "Normalized RMSE is unavailable because the observed comparison series "
            "has neither a non-zero mean scale nor variation."
        )
    if not math.isfinite(diagnostic.correlation):
        common_caveats.append(
            "Correlation is unavailable because at least one comparison series is "
            "constant or has too few varying observations."
        )
    findings: list[EmpiricalSymptomFinding] = []

    def add(
        suffix: str,
        *,
        severity: str,
        category: str,
        claim: str,
        threshold_names: Sequence[str],
    ) -> None:
        findings.append(EmpiricalSymptomFinding(
            issue_id=f"empirical.{metric_id}.{suffix}",
            severity=severity,
            confidence="medium",
            category=category,
            claim=claim,
            metric_id=metric_id,
            comparison_mode=mode,
            evidence=dict(shared_evidence),
            thresholds={name: _SYMPTOM_THRESHOLDS[name] for name in threshold_names},
            measurement_status=measurement_status,
            caveats=tuple(common_caveats),
            probe_ids=probes,
            root_cause_ids=root_causes,
            ablation_ids=ablations,
        ))

    nrmse = diagnostic.normalized_rmse
    if math.isfinite(nrmse) and nrmse >= float(_SYMPTOM_THRESHOLDS["normalized_rmse_warning"]):
        add(
            "path_distance",
            severity=(
                "high" if nrmse >= float(_SYMPTOM_THRESHOLDS["normalized_rmse_high"])
                else "medium"
            ),
            category="empirical_path",
            claim=(
                f"The model and observed {metric_id} paths differ materially in the "
                f"registered {mode.value} comparison domain."
            ),
            threshold_names=("normalized_rmse_warning", "normalized_rmse_high"),
        )

    correlation = diagnostic.correlation
    if (
        math.isfinite(correlation)
        and correlation < float(_SYMPTOM_THRESHOLDS["correlation_warning_below"])
    ):
        add(
            "weak_comovement",
            severity=(
                "high"
                if correlation < float(_SYMPTOM_THRESHOLDS["correlation_high_below"])
                else "medium"
            ),
            category="empirical_comovement",
            claim=(
                f"The model and observed {metric_id} series have weak co-movement in "
                f"the registered {mode.value} comparison domain."
            ),
            threshold_names=("correlation_warning_below", "correlation_high_below"),
        )

    mean_warn = normalized_mean_gap >= float(
        _SYMPTOM_THRESHOLDS["normalized_mean_gap_warning"]
    )
    volatility_warn = absolute_log_std_ratio >= float(
        _SYMPTOM_THRESHOLDS["absolute_log_std_ratio_warning"]
    )
    if mean_warn or volatility_warn:
        high = (
            normalized_mean_gap >= float(_SYMPTOM_THRESHOLDS["normalized_mean_gap_high"])
            or absolute_log_std_ratio
            >= float(_SYMPTOM_THRESHOLDS["absolute_log_std_ratio_high"])
        )
        add(
            "moment_gap",
            severity="high" if high else "medium",
            category="empirical_moments",
            claim=(
                f"The model and observed {metric_id} series have a material mean and/or "
                f"volatility gap in the registered {mode.value} comparison domain."
            ),
            threshold_names=(
                "normalized_mean_gap_warning", "normalized_mean_gap_high",
                "absolute_log_std_ratio_warning", "absolute_log_std_ratio_high",
            ),
        )

    return result("screened", findings)
