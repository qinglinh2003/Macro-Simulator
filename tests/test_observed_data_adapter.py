from __future__ import annotations

import json
from datetime import date, timedelta
from io import StringIO

import pytest

from macro_sim.diagnostics.empirical import (
    CalendarCadenceError,
    AlignedPoint,
    DailyValue,
    aggregate_daily_series,
    align_observed_simulated,
    classify_empirical_symptoms,
    diagnose_empirical_fit,
    prepare_simulation_timeline,
    select_observed_series,
    simulation_daily_values,
    transform_simulated_aggregates,
)
from macro_sim.diagnostics.observed import (
    ObservedDataError,
    load_observed_csv,
    observation_values_in_simulator_units,
)
from macro_sim.diagnostics.empirical_cli import main as empirical_main
from macro_sim.diagnostics.registry import (
    Aggregation,
    Annualization,
    ComparisonMode,
    DEFAULT_REGISTRY,
    ExternalSeriesCrosswalk,
    Frequency,
    MetricRegistry,
    MetricSpec,
    TemporalType,
    TrustStatus,
    ValueTransform,
)


HEADER = (
    "metric_id,geography,period,frequency,value,unit,source,series_id,vintage,"
    "seasonal_adjustment\n"
)


def _csv(rows: str):
    return load_observed_csv(StringIO(HEADER + rows))


def test_registry_exposes_semantics_trust_and_crosswalks():
    real_gdp = DEFAULT_REGISTRY.get("real_gdp")
    assert real_gdp.temporal_type == TemporalType.FLOW
    assert real_gdp.aggregation == Aggregation.SUM
    assert real_gdp.annualization == Annualization.SUM_DAILY_FLOWS
    assert real_gdp.trust_status == TrustStatus.PROXY
    assert real_gdp.caveats
    assert real_gdp.crosswalks[0].series_id == "GDPC1"
    assert real_gdp.crosswalks[0].target_annualization == Annualization.SUM_DAILY_FLOWS

    assert DEFAULT_REGISTRY.get("nominal_gdp").crosswalks[0].series_id == "GDP"
    assert DEFAULT_REGISTRY.get("nominal_gdp").trust_status == TrustStatus.PROXY
    assert DEFAULT_REGISTRY.get("cpi_fixed_basket").crosswalks[0].series_id == "CPIAUCSL"
    cpi_yoy = DEFAULT_REGISTRY.get("cpi_fixed_basket_inflation_yoy").crosswalks[0]
    assert cpi_yoy.series_id == "CPIAUCSL"
    assert cpi_yoy.transform == ValueTransform.MONTHLY_INDEX_TO_YOY
    assert not DEFAULT_REGISTRY.get("person_unemployment_rate").crosswalks
    assert DEFAULT_REGISTRY.get("labor_u_rate").crosswalks[0].series_id == "UNRATE"

    policy = DEFAULT_REGISTRY.get("policy_rate")
    assert policy.annualization == Annualization.SIMPLE_DAILY_RATE
    assert (
        policy.crosswalks[0].transform
        == ValueTransform.ANNUAL_PERCENT_TO_DAILY_SIMPLE
    )
    assert policy.crosswalks[0].apply(5.25) == pytest.approx(0.0525 / 365.0)

    # Compatibility fields remain available with explicit measurement caveats,
    # but real-data series resolve only to the preferred v23 accounts.
    assert DEFAULT_REGISTRY.get("real_output").trust_status == TrustStatus.PROXY
    for metric_id in ("real_output", "nominal_output", "price_index", "inflation_yoy"):
        legacy = DEFAULT_REGISTRY.get(metric_id)
        assert legacy.caveats
        assert not legacy.crosswalks


@pytest.mark.parametrize(
    ("row", "metric_id"),
    (
        (
            "real_gdp,USA,2024-Q1,quarterly,22500,billions_chained_2017_usd_saar,"
            "FRED,GDPC1,2024-04-25,seasonally_adjusted\n",
            "real_gdp",
        ),
        (
            "nominal_gdp,USA,2024-Q1,quarterly,28600,billions_usd_saar,FRED,GDP,"
            "2024-04-25,seasonally_adjusted\n",
            "nominal_gdp",
        ),
        (
            "cpi_fixed_basket,USA,2024-01,monthly,308.4,index_1982_1984_100,FRED,"
            "CPIAUCSL,2024-02-13,seasonally_adjusted\n",
            "cpi_fixed_basket",
        ),
        (
            "cpi_fixed_basket_inflation_yoy,USA,2024-01,monthly,308.4,"
            "index_1982_1984_100,FRED,CPIAUCSL,2024-02-13,seasonally_adjusted\n",
            "cpi_fixed_basket_inflation_yoy",
        ),
    ),
)
def test_observed_loader_accepts_preferred_v23_macro_crosswalks(row, metric_id):
    dataset = _csv(row)
    assert dataset.records[0].metric_id == metric_id


def test_metric_spec_rejects_economically_invalid_aggregation():
    with pytest.raises(ValueError, match="flow.*cannot use"):
        MetricSpec(
            "bad", "bad flow", "units", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.MEAN, Annualization.NONE, TrustStatus.VALIDATED,
        )


def test_observed_loader_requires_provenance_and_canonical_periods():
    dataset = _csv(
        "labor_u_rate,USA,2024-01,monthly,3.7,percent,FRED,UNRATE,"
        "2024-02-02,seasonally_adjusted\n"
    )
    row = dataset.records[0]
    assert row.geography == "USA"
    assert row.vintage == date(2024, 2, 2)

    missing_vintage = HEADER.replace("vintage,", "")
    with pytest.raises(ObservedDataError, match="missing required columns.*vintage"):
        load_observed_csv(StringIO(missing_vintage))
    with pytest.raises(ObservedDataError, match="invalid for frequency"):
        _csv(
            "labor_u_rate,USA,2024-13,monthly,3.7,percent,FRED,UNRATE,"
            "2024-02-02,seasonally_adjusted\n"
        )


@pytest.mark.parametrize("bad_value", ["nan", "inf", "not-a-number"])
def test_observed_loader_rejects_nonfinite_or_nonnumeric_values(bad_value):
    with pytest.raises(ObservedDataError, match="value"):
        _csv(
            f"labor_u_rate,USA,2024-01,monthly,{bad_value},percent,FRED,"
            "UNRATE,2024-02-02,seasonally_adjusted\n"
        )


def test_observed_loader_rejects_unregistered_crosswalk_and_duplicates():
    with pytest.raises(ObservedDataError, match="expected one registered crosswalk"):
        _csv(
            "labor_u_rate,USA,2024-01,monthly,3.7,ratio,UNKNOWN,U,"
            "2024-02-02,seasonally_adjusted\n"
        )
    row = (
        "labor_u_rate,USA,2024-01,monthly,3.7,percent,FRED,UNRATE,"
        "2024-02-02,seasonally_adjusted\n"
    )
    with pytest.raises(ObservedDataError, match="duplicate observation"):
        _csv(row + row)


def test_calendar_aggregation_uses_flow_stock_mean_and_compound_rules():
    days = tuple(
        DailyValue(date(2024, 2, 1) + timedelta(days=i), float(i + 1))
        for i in range(29)
    )
    flow = DEFAULT_REGISTRY.get("real_gdp")
    flow_month = aggregate_daily_series(days, flow, Frequency.MONTHLY)[0]
    assert flow_month.value == pytest.approx(sum(range(1, 30)))
    assert flow_month.complete
    assert flow_month.expected_observations == 29

    stock = DEFAULT_REGISTRY.get("total_money")
    assert aggregate_daily_series(days, stock, Frequency.MONTHLY)[0].value == 29.0

    price = DEFAULT_REGISTRY.get("price_index")
    assert aggregate_daily_series(days, price, Frequency.MONTHLY)[0].value == 15.0

    rate = DEFAULT_REGISTRY.get("labor_u_rate")
    assert aggregate_daily_series(days, rate, Frequency.MONTHLY)[0].value == 15.0

    compound_spec = MetricSpec(
        "return", "daily return", "ratio", Frequency.DAILY, TemporalType.RATE,
        Aggregation.COMPOUND, Annualization.COMPOUND_DAILY_RATE,
        TrustStatus.VALIDATED,
    )
    compounded = aggregate_daily_series(
        (DailyValue(date(2024, 1, 1), 0.1), DailyValue(date(2024, 1, 2), 0.1)),
        compound_spec, Frequency.MONTHLY,
    )[0]
    assert compounded.value == pytest.approx(0.21)
    assert not compounded.complete

    quarter_days = tuple(
        DailyValue(date(2024, 1, 1) + timedelta(days=i), 1.0) for i in range(91)
    )
    saar = aggregate_daily_series(
        quarter_days, flow, Frequency.QUARTERLY, crosswalk=flow.crosswalks[0],
    )[0]
    assert saar.value == pytest.approx(365.0)


def test_simulation_timeline_discards_burn_in_and_rebases_tick_origin():
    records = [
        {"tick": str(tick), "labor_u_rate": str(tick / 100.0)}
        for tick in range(10, 15)
    ]
    timeline = prepare_simulation_timeline(
        reversed(records),
        start_date=date(2024, 2, 28),
        tick_field="tick",
        tick_origin=10,
        burn_in_ticks=2,
    )
    daily = simulation_daily_values(timeline, "labor_u_rate")

    assert [(item.day, item.value) for item in daily] == [
        (date(2024, 2, 28), 0.12),
        (date(2024, 2, 29), 0.13),
        (date(2024, 3, 1), 0.14),
    ]
    assert timeline.metadata() == {
        "tick_field": "tick",
        "tick_origin": 10,
        "burn_in_ticks": 2,
        "cutoff_tick": 12,
        "raw_tick_range": [10, 14],
        "raw_row_count": 5,
        "retained_tick_range": [12, 14],
        "retained_row_count": 3,
        "discarded_row_count": 2,
        "calendar_start_date": date(2024, 2, 28),
        "calendar_end_date": date(2024, 3, 1),
        "calendar_mapping": "cutoff_tick_maps_to_simulation_start_date",
    }


@pytest.mark.parametrize(
    ("records", "kwargs", "message"),
    (
        ([{"t": "0"}, {"t": "2"}], {}, "missing tick 1"),
        ([{"t": "0"}, {"t": "0"}], {}, "duplicate tick 0"),
        ([{"t": "0.0"}], {}, "must be an integer"),
        ([{"t": "1"}], {}, "must start at tick_origin 0"),
        ([{"t": "0"}], {"burn_in_ticks": 1}, "smaller than"),
        ([{"t": "0"}], {"burn_in_ticks": -1}, "non-negative"),
    ),
)
def test_simulation_timeline_fails_closed_on_invalid_ticks(records, kwargs, message):
    with pytest.raises(ValueError, match=message):
        prepare_simulation_timeline(
            records, start_date=date(2024, 1, 1), **kwargs,
        )


def test_latest_vintage_alignment_converts_percent_to_ratio():
    dataset = _csv(
        "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
        "2024-02-02,seasonally_adjusted\n"
        "labor_u_rate,USA,2024-01,monthly,3.8,percent,FRED,UNRATE,"
        "2024-03-01,seasonally_adjusted\n"
        "labor_u_rate,USA,2024-02,monthly,3.9,percent,FRED,UNRATE,"
        "2024-03-08,seasonally_adjusted\n"
    )
    observed = select_observed_series(
        dataset, "labor_u_rate", geography="USA", source="FRED",
        series_id="UNRATE", seasonal_adjustment="seasonally_adjusted",
    )
    assert [row.value for row in observed] == [3.8, 3.9]

    spec = DEFAULT_REGISTRY.get("labor_u_rate")
    jan = tuple(DailyValue(date(2024, 1, 1) + timedelta(days=i), 0.04) for i in range(31))
    feb = tuple(DailyValue(date(2024, 2, 1) + timedelta(days=i), 0.041) for i in range(29))
    simulated = aggregate_daily_series(jan + feb, spec, Frequency.MONTHLY)
    aligned = align_observed_simulated(simulated, observed)
    assert [point.observed for point in aligned] == pytest.approx([0.038, 0.039])
    assert [point.simulated for point in aligned] == pytest.approx([0.04, 0.041])
    assert {(point.source, point.series_id, point.comparison_mode) for point in aligned} == {
        ("FRED", "UNRATE", ComparisonMode.LEVELS)
    }


def test_raw_cpi_crosswalk_derives_exact_calendar_yoy_and_preserves_provenance():
    dataset = _csv(
        "cpi_fixed_basket_inflation_yoy,USA,2023-01,monthly,100.0,"
        "index_1982_1984_100,FRED,CPIAUCSL,2023-02-14,seasonally_adjusted\n"
        "cpi_fixed_basket_inflation_yoy,USA,2024-01,monthly,103.0,"
        "index_1982_1984_100,FRED,CPIAUCSL,2024-02-13,seasonally_adjusted\n"
        "cpi_fixed_basket_inflation_yoy,USA,2024-02,monthly,104.0,"
        "index_1982_1984_100,FRED,CPIAUCSL,2024-03-12,seasonally_adjusted\n"
    )
    observed = select_observed_series(
        dataset, "cpi_fixed_basket_inflation_yoy", geography="USA",
        source="FRED", series_id="CPIAUCSL",
    )
    converted = observation_values_in_simulator_units(observed)
    assert [row.period for row, _value in converted] == ["2024-01"]
    assert [value for _row, value in converted] == pytest.approx([0.03])

    spec = DEFAULT_REGISTRY.get("cpi_fixed_basket_inflation_yoy")
    crosswalk = spec.crosswalks[0]
    assert crosswalk.simulation_source_metric_id == "cpi_fixed_basket"
    assert crosswalk.simulation_transform == ValueTransform.MONTHLY_INDEX_TO_YOY

    # Strong within-month movement makes this materially different from averaging
    # daily trailing-365 inflation.  The registered empirical path first constructs
    # monthly CPI levels, then takes the exact same-month t-12 ratio.
    level_spec = DEFAULT_REGISTRY.get("cpi_fixed_basket")
    january_2023 = tuple(
        DailyValue(
            date(2023, 1, 1) + timedelta(days=index),
            100.0 + (index - 15) * 0.2,
        )
        for index in range(31)
    )
    january_2024 = tuple(
        DailyValue(
            date(2024, 1, 1) + timedelta(days=index),
            103.0 + (index - 15) * 0.4,
        )
        for index in range(31)
    )
    monthly_levels = aggregate_daily_series(
        january_2023 + january_2024, level_spec, Frequency.MONTHLY,
    )
    simulated = transform_simulated_aggregates(
        monthly_levels,
        target_metric_id="cpi_fixed_basket_inflation_yoy",
        crosswalk=crosswalk,
    )
    aligned = align_observed_simulated(
        simulated, observed,
    )
    assert len(aligned) == 1
    assert aligned[0].period == "2024-01"
    assert aligned[0].observed == pytest.approx(0.03)
    assert aligned[0].series_id == "CPIAUCSL"
    assert aligned[0].simulated == pytest.approx(0.03)
    assert any("Both model" in item for item in aligned[0].crosswalk_caveats)

    with pytest.raises(ValueError, match="requires apply_series"):
        spec.crosswalks[0].apply(103.0)


def test_model_cpi_yoy_uses_exact_month_lag_across_leap_year_and_omits_missing_lag():
    level_spec = DEFAULT_REGISTRY.get("cpi_fixed_basket")
    crosswalk = DEFAULT_REGISTRY.get(
        "cpi_fixed_basket_inflation_yoy"
    ).crosswalks[0]

    def centered_month(start: date, days: int, mean: float, slope: float):
        center = (days - 1) / 2.0
        return tuple(
            DailyValue(
                start + timedelta(days=index),
                mean + (index - center) * slope,
            )
            for index in range(days)
        )

    daily = (
        centered_month(date(2023, 2, 1), 28, 100.0, 0.3)
        + centered_month(date(2024, 2, 1), 29, 104.0, 0.6)
        + centered_month(date(2024, 3, 1), 31, 106.0, 0.2)
    )
    derived = transform_simulated_aggregates(
        aggregate_daily_series(daily, level_spec, Frequency.MONTHLY),
        target_metric_id="cpi_fixed_basket_inflation_yoy",
        crosswalk=crosswalk,
    )

    assert [item.period for item in derived] == ["2024-02"]
    assert derived[0].value == pytest.approx(0.04)
    assert derived[0].complete
    assert derived[0].n_observations == 57
    assert derived[0].expected_observations == 57


def test_alignment_orders_simulated_periods_before_time_series_diagnostics():
    dataset = _csv(
        "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
        "2024-02-02,seasonally_adjusted\n"
        "labor_u_rate,USA,2024-02,monthly,5.0,percent,FRED,UNRATE,"
        "2024-03-08,seasonally_adjusted\n"
    )
    observed = select_observed_series(
        dataset, "labor_u_rate", geography="USA", source="FRED",
        series_id="UNRATE",
    )
    spec = DEFAULT_REGISTRY.get("labor_u_rate")
    jan = tuple(DailyValue(date(2024, 1, 1) + timedelta(days=i), 0.04) for i in range(31))
    feb = tuple(DailyValue(date(2024, 2, 1) + timedelta(days=i), 0.05) for i in range(29))
    simulated = aggregate_daily_series(jan + feb, spec, Frequency.MONTHLY)
    aligned = align_observed_simulated(reversed(simulated), observed)
    assert [point.period for point in aligned] == ["2024-01", "2024-02"]


@pytest.mark.parametrize(
    ("periods", "frequency", "metric_id", "mode"),
    (
        (
            ("2024-01", "2024-03"), Frequency.MONTHLY,
            "labor_u_rate", ComparisonMode.LEVELS,
        ),
        (
            ("2024-Q1", "2024-Q3"), Frequency.QUARTERLY,
            "real_gdp", ComparisonMode.LOG_CHANGES,
        ),
    ),
)
def test_empirical_diagnostic_rejects_calendar_gaps_before_differencing(
    periods, frequency, metric_id, mode,
):
    aligned = tuple(
        AlignedPoint(
            period, 100.0 + index, 100.0 + index, date(2025, 1, 1),
            "FRED", "SERIES", mode, frequency=frequency,
        )
        for index, period in enumerate(periods)
    )
    with pytest.raises(CalendarCadenceError, match="not contiguous"):
        diagnose_empirical_fit(aligned, metric_id)


def test_empirical_diagnostic_never_bypasses_mixed_provenance_validation():
    aligned = (
        AlignedPoint(
            "2024-01", 1.0, 1.0, date(2024, 2, 1),
            "SOURCE_A", "SERIES", ComparisonMode.LEVELS,
        ),
        AlignedPoint(
            "2024-02", 2.0, 2.0, date(2024, 3, 1),
            "SOURCE_B", "SERIES", ComparisonMode.LEVELS,
        ),
    )
    with pytest.raises(ValueError, match="one source/series/comparison mode"):
        diagnose_empirical_fit(
            aligned, "labor_u_rate", comparison_mode=ComparisonMode.LEVELS,
        )


def test_single_series_selection_strictly_rejects_ambiguous_provenance():
    registry = MetricRegistry.from_specs((MetricSpec(
        "test_rate", "test rate", "ratio", Frequency.DAILY, TemporalType.RATE,
        Aggregation.MEAN, Annualization.NONE, TrustStatus.VALIDATED,
        crosswalks=(
            ExternalSeriesCrosswalk(
                "SOURCE_A", "RATE", Frequency.MONTHLY, "ratio", geography="USA",
            ),
            ExternalSeriesCrosswalk(
                "SOURCE_B", "RATE", Frequency.MONTHLY, "ratio", geography="USA",
            ),
        ),
    ),))
    dataset = load_observed_csv(StringIO(
        HEADER
        + "test_rate,USA,2024-01,monthly,0.1,ratio,SOURCE_A,RATE,2024-02-01,"
          "not_seasonally_adjusted\n"
        + "test_rate,USA,2024-01,monthly,0.2,ratio,SOURCE_B,RATE,2024-02-01,"
          "not_seasonally_adjusted\n"
    ), registry=registry)
    with pytest.raises(ValueError, match="multiple source/series/frequency/unit"):
        select_observed_series(dataset, "test_rate", geography="USA")
    selected = select_observed_series(
        dataset, "test_rate", geography="USA", source="SOURCE_A",
    )
    assert len(selected) == 1
    assert selected[0].source == "SOURCE_A"


def test_empirical_diagnostics_report_distances_moments_and_measurement_caveats():
    dataset = _csv(
        "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
        "2024-02-02,seasonally_adjusted\n"
        "labor_u_rate,USA,2024-02,monthly,5.0,percent,FRED,UNRATE,"
        "2024-03-08,seasonally_adjusted\n"
        "labor_u_rate,USA,2024-03,monthly,4.5,percent,FRED,UNRATE,"
        "2024-04-05,seasonally_adjusted\n"
    )
    observed = select_observed_series(
        dataset, "labor_u_rate", geography="USA",
        source="FRED", series_id="UNRATE",
    )
    spec = DEFAULT_REGISTRY.get("labor_u_rate")
    simulated = []
    for month, value, n_days in ((1, 0.041, 31), (2, 0.048, 29), (3, 0.046, 31)):
        simulated.extend(
            DailyValue(date(2024, month, 1) + timedelta(days=i), value)
            for i in range(n_days)
        )
    aligned = align_observed_simulated(
        aggregate_daily_series(simulated, spec, Frequency.MONTHLY), observed,
    )
    result = diagnose_empirical_fit(aligned, "labor_u_rate")
    assert result.n_aligned == 3
    assert result.comparison_mode == ComparisonMode.LEVELS
    assert result.root_mean_squared_error > 0.0
    assert result.observed_moments.standard_deviation > 0.0
    assert result.trust_status == "proxy"
    assert result.caveats


def test_standardized_mode_computes_errors_on_z_scores():
    aligned = tuple(
        AlignedPoint(
            str(index), simulated, observed, date(2024, 1, 1),
            "TEST", "SERIES", ComparisonMode.STANDARDIZED,
        )
        for index, (simulated, observed) in enumerate(((1.0, 10.0), (2.0, 20.0), (3.0, 30.0)))
    )
    result = diagnose_empirical_fit(aligned, "labor_u_rate")
    assert result.root_mean_squared_error == pytest.approx(0.0)
    assert result.mean_bias == pytest.approx(0.0)


def test_log_change_mode_does_not_difference_growth_rates_twice():
    import math

    simulated_growth = (0.10, 0.30, -0.10, 0.20)
    observed_growth = (0.20, 0.10, 0.00, 0.40)
    simulated = [1.0]
    observed = [1.0]
    for sim_growth, obs_growth in zip(simulated_growth, observed_growth):
        simulated.append(simulated[-1] * math.exp(sim_growth))
        observed.append(observed[-1] * math.exp(obs_growth))
    aligned = tuple(
        AlignedPoint(
            str(index), sim, obs, date(2024, 1, 1),
            "TEST", "SERIES", ComparisonMode.LOG_CHANGES,
        )
        for index, (sim, obs) in enumerate(zip(simulated, observed))
    )
    result = diagnose_empirical_fit(aligned, "real_output")
    assert result.first_difference_correlation == pytest.approx(result.correlation)


def test_empirical_result_preserves_crosswalk_and_partial_period_caveats():
    caveat = "Compare growth dynamics only; simulator levels use abstract units."
    aligned = (
        AlignedPoint(
            "2024-Q1", 100.0, 100.0, date(2024, 4, 1), "FRED", "GDPC1",
            ComparisonMode.LOG_CHANGES, (caveat,), False, 45, 91,
        ),
        AlignedPoint(
            "2024-Q2", 101.0, 102.0, date(2024, 7, 1), "FRED", "GDPC1",
            ComparisonMode.LOG_CHANGES, (caveat,), True, 91, 91,
        ),
    )
    result = diagnose_empirical_fit(aligned, "real_output")
    assert caveat in result.caveats
    assert any("incomplete simulator calendar period" in item for item in result.caveats)


def test_empirical_cli_reads_real_data_contract_and_writes_reports(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_rows = ["t,labor_u_rate"]
    simulation_rows.extend(
        f"{tick},{0.04 if tick < 31 else 0.05}" for tick in range(60)
    )
    simulation_path.write_text("\n".join(simulation_rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.1,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,4.9,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--source", "FRED",
        "--series-id", "UNRATE",
        "--output-dir", str(output_dir),
    ]) == 0
    payload = json.loads((output_dir / "empirical_diagnostic.json").read_text())
    assert payload["diagnostic"]["n_aligned"] == 2
    assert payload["observed_series"]["series_id"] == "UNRATE"
    assert payload["simulation"]["sha256"]
    assert payload["observed_series"]["sha256"]
    assert payload["observed_series"]["crosswalk"]["transform"] == "percent_to_ratio"
    assert (output_dir / "REPORT.md").exists()


def test_empirical_cli_records_burn_in_timeline_and_maps_cutoff_to_start_date(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    rows = ["tick,labor_u_rate"]
    for tick in range(10, 72):
        value = 0.99 if tick < 12 else (0.04 if tick < 43 else 0.05)
        rows.append(f"{tick},{value}")
    simulation_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,5.0,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--simulation-start-date", "2024-01-01",
        "--tick-field", "tick",
        "--tick-origin", "10",
        "--burn-in-ticks", "2",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 0
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    assert payload["software"]["unchanged_during_run"] is True
    assert payload["software"]["at_start"]["git"]["revision"]
    assert len(
        payload["software"]["at_start"]["metric_registry_sha256"]
    ) == 64
    assert (
        payload["software"]["at_start"]["metric_registry_sha256"]
        == payload["software"]["at_completion"]["metric_registry_sha256"]
    )
    timeline = payload["inputs"]["simulation"]["timeline"]
    assert timeline == {
        "burn_in_ticks": 2,
        "calendar_end_date": "2024-02-29",
        "calendar_mapping": "cutoff_tick_maps_to_simulation_start_date",
        "calendar_start_date": "2024-01-01",
        "cutoff_tick": 12,
        "discarded_row_count": 2,
        "raw_row_count": 62,
        "raw_tick_range": [10, 71],
        "retained_row_count": 60,
        "retained_tick_range": [12, 71],
        "tick_field": "tick",
        "tick_origin": 10,
    }
    assert payload["request"]["simulation_start_date_semantics"] == (
        "first_retained_post_burn_tick"
    )
    assert [point["simulated"] for point in payload["series"][0]["aligned"]] == (
        pytest.approx([0.04, 0.05])
    )


def test_empirical_cli_can_select_preferred_fixed_basket_cpi(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_rows = ["t,cpi_fixed_basket"]
    simulation_rows.extend(
        f"{tick},{1.0 if tick < 31 else 1.01}" for tick in range(60)
    )
    simulation_path.write_text("\n".join(simulation_rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "cpi_fixed_basket,USA,2024-01,monthly,300.0,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-02-13,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-02,monthly,303.0,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-03-12,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "cpi_fixed_basket",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--source", "FRED",
        "--series-id", "CPIAUCSL",
        "--output-dir", str(output_dir),
    ]) == 0
    payload = json.loads((output_dir / "empirical_diagnostic.json").read_text())
    assert payload["diagnostic"]["trust_status"] == "validated"
    assert payload["diagnostic"]["comparison_mode"] == "rebased_index"
    assert payload["metric_id"] == "cpi_fixed_basket"


def test_empirical_cli_cpi_yoy_uses_registered_monthly_level_source(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    rows = ["t,cpi_fixed_basket,cpi_fixed_basket_inflation_yoy"]
    start = date(2023, 1, 1)
    end = date(2024, 2, 29)
    day = start
    tick = 0
    while day <= end:
        level = 1.0
        if (day.year, day.month) == (2024, 1):
            level = 1.03
        elif (day.year, day.month) == (2024, 2):
            level = 1.04
        # Deliberately wrong official daily field: the empirical adapter must not
        # average it when the crosswalk names cpi_fixed_basket as its source.
        rows.append(f"{tick},{level},9.9")
        tick += 1
        day += timedelta(days=1)
    simulation_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    observed_rows = []
    for index in range(14):
        year, month = 2023 + index // 12, index % 12 + 1
        value = 100.0
        if (year, month) == (2024, 1):
            value = 103.0
        elif (year, month) == (2024, 2):
            value = 104.0
        observed_rows.append(
            f"cpi_fixed_basket_inflation_yoy,USA,{year}-{month:02d},monthly,"
            f"{value},index_1982_1984_100,FRED,CPIAUCSL,2025-01-01,"
            "seasonally_adjusted\n"
        )
    observed_path.write_text(
        HEADER + "".join(observed_rows), encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "cpi_fixed_basket_inflation_yoy",
        "--simulation-start-date", "2023-01-01",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 0
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    series = payload["series"][0]
    assert series["observed_series"]["crosswalk"][
        "effective_simulation_metric_id"
    ] == "cpi_fixed_basket"
    assert [point["period"] for point in series["aligned"]] == [
        "2024-01", "2024-02",
    ]
    assert [point["simulated"] for point in series["aligned"]] == pytest.approx(
        [0.03, 0.04]
    )


def test_empirical_cli_repeated_metrics_batch_once_across_frequencies(
    tmp_path, monkeypatch,
):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    rows = ["t,real_gdp,labor_u_rate"]
    for tick in range(182):
        rows.append(
            f"{tick},{10.0 if tick < 91 else 11.0},"
            f"{0.04 + 0.00001 * tick}"
        )
    simulation_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "real_gdp,USA,2024-Q1,quarterly,3650,billions_chained_2017_usd_saar,"
          "FRED,GDPC1,2024-04-25,seasonally_adjusted\n"
        + "real_gdp,USA,2024-Q2,quarterly,3900,billions_chained_2017_usd_saar,"
          "FRED,GDPC1,2024-07-25,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,4.1,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n",
        encoding="utf-8",
    )

    from macro_sim.diagnostics import empirical_cli

    real_reader = empirical_cli._read_simulation_csv
    real_prepare = empirical_cli.prepare_simulation_timeline
    reads = 0
    preparations = 0

    def counted_reader(path):
        nonlocal reads
        reads += 1
        return real_reader(path)

    def counted_prepare(*args, **kwargs):
        nonlocal preparations
        preparations += 1
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(empirical_cli, "_read_simulation_csv", counted_reader)
    monkeypatch.setattr(
        empirical_cli, "prepare_simulation_timeline", counted_prepare,
    )
    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--metric-id", "real_gdp",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 0

    assert reads == 1
    assert preparations == 1
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    assert payload["schema_version"] == 2
    assert payload["request"]["metric_ids"] == [
        "labor_u_rate", "real_gdp",
    ]
    assert payload["summary"]["series_successful"] == 2
    assert [item["metric_id"] for item in payload["series"]] == [
        "labor_u_rate", "real_gdp",
    ]
    by_metric = {item["metric_id"]: item for item in payload["series"]}
    assert by_metric["real_gdp"]["observed_series"]["frequency"] == "quarterly"
    assert by_metric["real_gdp"]["classification"]["status"] == "insufficient_sample"
    assert by_metric["real_gdp"]["classification"]["findings"] == []
    assert (
        by_metric["labor_u_rate"]["observed_series"]["frequency"]
        == "monthly"
    )
    assert not (output_dir / "empirical_diagnostic.json").exists()


def test_empirical_cli_auto_discovers_all_series_and_isolates_group_failure(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_rows = ["t,labor_u_rate"]
    simulation_rows.extend(
        f"{tick},{0.04 if tick < 31 else 0.05}" for tick in range(60)
    )
    simulation_path.write_text("\n".join(simulation_rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.1,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,4.9,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-01,monthly,300,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-02-13,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-02,monthly,303,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-03-12,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 1
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    assert payload["request"]["auto_discover_all_metrics"] is True
    assert payload["summary"] == {
        "finding_count": 0,
        "series_failed": 1,
        "series_skipped": 0,
        "series_successful": 1,
        "series_total": 2,
    }
    by_metric = {item["metric_id"]: item for item in payload["series"]}
    assert by_metric["labor_u_rate"]["status"] == "success"
    assert by_metric["labor_u_rate"]["aligned"]
    assert by_metric["cpi_fixed_basket"]["status"] == "failed"
    assert by_metric["cpi_fixed_basket"]["failure_reason"]["stage"] == "simulation_series"
    report = (output_dir / "REPORT.md").read_text()
    assert "series_processing_failed" in report
    assert "Aligned data" in report


def test_empirical_cli_reports_noncontiguous_alignment_failure_code(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    rows = ["t,labor_u_rate,cpi_fixed_basket"]
    rows.extend(f"{tick},{0.04 + tick / 100000.0},{1.0 + tick / 10000.0}" for tick in range(91))
    simulation_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-04-01,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-03,monthly,4.2,percent,FRED,UNRATE,"
          "2024-04-01,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-01,monthly,300,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-04-01,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-02,monthly,301,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-04-01,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-03,monthly,302,index_1982_1984_100,FRED,"
          "CPIAUCSL,2024-04-01,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 1
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    labor = next(
        item for item in payload["series"] if item["metric_id"] == "labor_u_rate"
    )
    assert labor["status"] == "failed"
    assert labor["failure_reason"]["stage"] == "calendar_cadence"
    assert labor["failure_reason"]["code"] == "non_contiguous_aligned_periods"
    assert "would bridge a calendar gap" in labor["failure_reason"]["message"]


def test_empirical_symptoms_route_unemployment_to_existing_noncausal_probes(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_rows = ["t,labor_u_rate"]
    # 2024 (leap) + 2025 gives 24 complete monthly observations, the declared
    # minimum for screening rather than a fragile eight-month path comparison.
    simulation_rows.extend(f"{tick},0.20" for tick in range(366 + 365))
    simulation_path.write_text("\n".join(simulation_rows) + "\n", encoding="utf-8")
    observed = []
    for index in range(24):
        year, month = 2024 + index // 12, index % 12 + 1
        value = 4.0 + 0.4 * (index % 2) + 0.01 * index
        observed.append(
            f"labor_u_rate,USA,{year}-{month:02d},monthly,{value},percent,"
            f"FRED,UNRATE,2026-01-15,seasonally_adjusted\n"
        )
    observed_path.write_text(HEADER + "".join(observed), encoding="utf-8")

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--source", "FRED",
        "--series-id", "UNRATE",
        "--output-dir", str(output_dir),
    ]) == 0
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    series = payload["series"][0]
    classification = series["classification"]
    assert classification["status"] == "screened"
    assert classification["minimum_comparison_observations"] == 24
    assert "two calendar years" in classification[
        "minimum_comparison_observations_basis"
    ]
    assert classification["measurement_status"] == "proxy_not_calibration"
    assert classification["level_calibration_allowed"] is False
    assert "labor_constraint_decomposition" in classification["probe_ids"]
    assert "labor.chronic_slack" in classification["root_cause_ids"]
    assert "spot_labor" in classification["ablation_ids"]
    assert series["findings"]
    assert all(
        finding["inference_scope"] == "descriptive_non_causal"
        for finding in series["findings"]
    )
    assert all(finding["thresholds"] for finding in series["findings"])
    assert payload["input_integrity"]["verified"] is True


def test_empirical_classifier_never_treats_gdp_abstract_levels_as_calibration():
    aligned = tuple(
        AlignedPoint(
            f"202{index // 4}-Q{index % 4 + 1}",
            100.0 * 1.01 ** index,
            20_000.0 * 1.02 ** index,
            date(2025, 1, 1),
            "FRED", "GDPC1", ComparisonMode.LOG_CHANGES,
        )
        for index in range(13)
    )
    diagnostic = diagnose_empirical_fit(aligned, "real_gdp")
    classification = classify_empirical_symptoms(
        aligned, diagnostic, registered_comparison_mode=ComparisonMode.LOG_CHANGES,
    )
    assert classification.status == "screened"
    assert classification.n_comparison_observations == 12
    assert classification.minimum_comparison_observations == 12
    assert "13 contiguous levels" in (
        classification.minimum_comparison_observations_basis
    )
    assert classification.level_calibration_allowed is False
    assert classification.comparison_mode == ComparisonMode.LOG_CHANGES
    assert "growth_accounting" in classification.probe_ids

    overridden = diagnose_empirical_fit(
        aligned, "real_gdp", comparison_mode=ComparisonMode.LEVELS,
    )
    blocked = classify_empirical_symptoms(
        aligned, overridden, registered_comparison_mode=ComparisonMode.LOG_CHANGES,
    )
    assert blocked.status == "blocked_by_comparison_override"
    assert not blocked.findings
    assert blocked.level_calibration_allowed is False
    assert any("blocked" in caveat.lower() for caveat in blocked.caveats)


def test_monthly_symptom_screen_requires_24_post_transform_observations():
    aligned = tuple(
        AlignedPoint(
            f"{2023 + index // 12}-{index % 12 + 1:02d}",
            0.05 + index / 10000.0,
            0.04 + index / 10000.0,
            date(2026, 1, 1),
            "FRED", "UNRATE", ComparisonMode.LEVELS,
            frequency=Frequency.MONTHLY,
        )
        for index in range(23)
    )
    diagnostic = diagnose_empirical_fit(aligned, "labor_u_rate")
    classification = classify_empirical_symptoms(aligned, diagnostic)

    assert classification.status == "insufficient_sample"
    assert classification.n_comparison_observations == 23
    assert classification.minimum_comparison_observations == 24
    assert "two calendar years" in (
        classification.minimum_comparison_observations_basis
    )


def test_empirical_batch_vintage_skip_does_not_hide_success(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_rows = ["t,labor_u_rate,cpi_fixed_basket"]
    simulation_rows.extend(
        f"{tick},{0.04 if tick < 31 else 0.05},{1.0 if tick < 31 else 1.01}"
        for tick in range(60)
    )
    simulation_path.write_text("\n".join(simulation_rows) + "\n", encoding="utf-8")
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.1,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,4.9,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-01,monthly,300,index_1982_1984_100,FRED,"
          "CPIAUCSL,2025-02-13,seasonally_adjusted\n"
        + "cpi_fixed_basket,USA,2024-02,monthly,303,index_1982_1984_100,FRED,"
          "CPIAUCSL,2025-03-12,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--metric-id", "cpi_fixed_basket",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--vintage", "2024-12-31",
        "--output-dir", str(output_dir),
    ]) == 1
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    assert payload["summary"]["series_successful"] == 1
    assert payload["summary"]["series_skipped"] == 1
    skipped = next(item for item in payload["series"] if item["status"] == "skipped")
    assert skipped["metric_id"] == "cpi_fixed_basket"
    assert skipped["failure_reason"]["code"] == "observations_unavailable_at_vintage"
    assert payload["request_completeness"] == {
        "complete": False,
        "explicitly_requested_skipped_metrics": ["cpi_fixed_basket"],
        "missing_requested_allowed": False,
    }

    allowed_output = tmp_path / "allowed-report"
    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--metric-id", "cpi_fixed_basket",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--vintage", "2024-12-31",
        "--allow-missing-requested",
        "--output-dir", str(allowed_output),
    ]) == 0
    allowed = json.loads(
        (allowed_output / "empirical_diagnostics.json").read_text()
    )
    assert allowed["request_completeness"]["missing_requested_allowed"] is True


def test_explicitly_requested_metric_without_observed_series_fails_batch(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_path.write_text(
        "t,labor_u_rate\n"
        + "\n".join(f"{tick},0.04" for tick in range(60))
        + "\n",
        encoding="utf-8",
    )
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,4.0,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n",
        encoding="utf-8",
    )

    assert empirical_main([
        "--simulation-csv", str(simulation_path),
        "--observed-csv", str(observed_path),
        "--metric-id", "labor_u_rate",
        "--metric-id", "policy_rate",
        "--simulation-start-date", "2024-01-01",
        "--geography", "USA",
        "--output-dir", str(output_dir),
    ]) == 1
    payload = json.loads((output_dir / "empirical_diagnostics.json").read_text())
    assert payload["request_completeness"][
        "explicitly_requested_skipped_metrics"
    ] == ["policy_rate"]
    missing = next(item for item in payload["series"] if item["metric_id"] == "policy_rate")
    assert missing["failure_reason"]["code"] == "no_matching_observed_series"


def test_empirical_cli_rejects_input_hash_change_before_writing(tmp_path, monkeypatch):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n"
        + "labor_u_rate,USA,2024-02,monthly,5.0,percent,FRED,UNRATE,"
          "2024-03-08,seasonally_adjusted\n",
        encoding="utf-8",
    )
    simulation_path.write_text(
        "t,labor_u_rate\n"
        + "\n".join(f"{tick},{0.04 if tick < 31 else 0.05}" for tick in range(60))
        + "\n",
        encoding="utf-8",
    )

    from macro_sim.diagnostics import empirical_cli

    hashes = iter(("simulation-before", "observed-before", "simulation-after", "observed-before"))
    monkeypatch.setattr(empirical_cli, "_file_sha256", lambda _path: next(hashes))
    with pytest.raises(RuntimeError, match="changed while"):
        empirical_main([
            "--simulation-csv", str(simulation_path),
            "--observed-csv", str(observed_path),
            "--metric-id", "labor_u_rate",
            "--simulation-start-date", "2024-01-01",
            "--geography", "USA",
            "--output-dir", str(output_dir),
        ])
    assert not output_dir.exists()


def test_empirical_cli_rejects_duplicate_simulation_header_before_processing(tmp_path):
    simulation_path = tmp_path / "series.csv"
    observed_path = tmp_path / "observed.csv"
    output_dir = tmp_path / "report"
    simulation_path.write_text(
        "t,t,labor_u_rate\n0,0,0.04\n1,1,0.04\n",
        encoding="utf-8",
    )
    observed_path.write_text(
        HEADER
        + "labor_u_rate,USA,2024-01,monthly,4.0,percent,FRED,UNRATE,"
          "2024-02-02,seasonally_adjusted\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate header"):
        empirical_main([
            "--simulation-csv", str(simulation_path),
            "--observed-csv", str(observed_path),
            "--metric-id", "labor_u_rate",
            "--simulation-start-date", "2024-01-01",
            "--geography", "USA",
            "--output-dir", str(output_dir),
        ])
    assert not output_dir.exists()
