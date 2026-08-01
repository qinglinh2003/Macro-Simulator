from __future__ import annotations

import pytest

from macro_sim import native_backend
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    apply_config_treatment,
    derive_analysis_metrics,
    effect_scales,
    native_world_treatment_spec,
    paired_effect,
    population_scaled_new_game,
    population_scaled_configs,
    summarize_metric_series,
    summarize_paired_runs,
    summarize_time_responses,
)


def test_population_scaling_preserves_representative_entity_densities() -> None:
    config = population_scaled_configs(
        population=100_000, days=365, seed=17
    )[0]
    assert config.demographics_population == 100_000
    assert config.n_firms_c == 1_500
    assert config.n_firms_k == 500
    assert config.n_firms_e == 250
    assert config.n_builders == 625
    assert config.n_banks == 8
    assert config.n_ticks == 365
    assert config.seed == 17


def test_config_treatment_changes_only_the_target_economy() -> None:
    baseline = population_scaled_configs(
        population=100_000, days=90, seed=19, countries=2
    )
    treated = apply_config_treatment(
        baseline,
        field="lambda_d",
        value=0.012,
        target_economy=1,
    )
    assert treated[0] == baseline[0]
    assert treated[1].lambda_d == pytest.approx(0.012)
    assert treated[1].lambda_y == baseline[1].lambda_y


def test_metric_reduction_and_paired_effect_preserve_pairing() -> None:
    summary = summarize_metric_series(
        [
            {"metric.a": 1.0, "metric.b": 5.0, "_tick": 1},
            {"metric.a": 2.0, "metric.b": 5.0, "_tick": 2},
            {"metric.a": 3.0, "metric.b": 5.0, "_tick": 3},
        ],
        window_days=2,
        burn_in_days=1,
    )
    assert summary["metric.a"].mean == pytest.approx(2.0)
    assert summary["metric.a"].first_window_mean == pytest.approx(1.5)
    assert summary["metric.a"].last_window_mean == pytest.approx(2.5)
    assert summary["metric.a"].cumulative == pytest.approx(6.0)
    assert summary["metric.a"].post_burnin_mean == pytest.approx(2.5)

    effect = paired_effect([1.0, 10.0], [2.0, 11.0])
    assert effect.mean_difference == pytest.approx(1.0)
    assert effect.paired_standard_deviation == pytest.approx(0.0)


def test_analysis_metric_derives_the_goods_transaction_price_proxy() -> None:
    row = derive_analysis_metrics(
        {
            "metric.economy.na.household_consumption_goods_nominal": 80.0,
            "metric.economy.sector_consumption_sales": 100.0,
        }
    )
    assert row["metric.analysis.goods_transaction_price_proxy"] == pytest.approx(
        0.8
    )
    missing = derive_analysis_metrics(
        {
            "metric.economy.na.household_consumption_goods_nominal": 80.0,
            "metric.economy.sector_consumption_sales": 0.0,
        }
    )
    assert "metric.analysis.goods_transaction_price_proxy" not in missing


def test_paired_run_summary_uses_common_metrics_only() -> None:
    def run(value: float, *, extra: bool = False) -> dict:
        metrics = {
            "metric.a": {
                "mean": value,
                "final": value,
                "volatility": 0.0,
                "first_window_mean": value,
                "last_window_mean": value,
                "cumulative": value,
                "post_burnin_mean": value,
                "post_burnin_volatility": 0.0,
            }
        }
        if extra:
            metrics["metric.extra"] = dict(metrics["metric.a"])
        return {"metric_summaries": metrics}

    effects = summarize_paired_runs(
        [run(1.0, extra=True), run(2.0)],
        [run(1.5, extra=True), run(2.5)],
    )
    assert list(effects) == ["metric.a"]
    assert effects["metric.a"]["mean"]["mean_difference"] == pytest.approx(
        0.5
    )
    scales = effect_scales(
        effects, control_value=1.0, treatment_value=1.1
    )
    assert scales["metric.a"]["mean"]["semi_elasticity"] == pytest.approx(
        5.0
    )
    assert scales["metric.a"]["mean"]["local_elasticity"] == pytest.approx(3.75)


def test_time_response_preserves_paired_seed_paths() -> None:
    def run(values: list[float]) -> dict:
        return {
            "metric_series": {
                "metric.a": {"ticks": [1, 2, 3, 4], "values": values}
            }
        }

    response = summarize_time_responses(
        [run([1.0, 1.0, 1.0, 1.0]), run([2.0, 2.0, 2.0, 2.0])],
        [run([1.0, 3.0, 2.0, 1.5]), run([2.0, 4.0, 3.0, 2.5])],
    )["metric.a"]
    assert response["first_difference_tick"] == 2
    assert response["peak_tick"] == 2
    assert response["peak_effect"] == pytest.approx(2.0)
    assert response["terminal_effect"] == pytest.approx(0.5)
    assert response["half_decay_tick"] == 3
    assert response["sign_reversals"] == 0


def test_small_paired_interval_uses_student_t() -> None:
    effect = paired_effect([0.0, 0.0], [0.0, 2.0])
    # df=1: 1 +/- 12.706 * (sqrt(2) / sqrt(2)).
    assert effect.confidence_low == pytest.approx(-11.706)
    assert effect.confidence_high == pytest.approx(13.706)


def test_world_treatment_uses_the_product_new_game_contract() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=23, countries=2
    )
    treated = native_world_treatment_spec(
        baseline, field="fx_lambda", value=0.071
    )
    assert treated.rules.fx_adjustment == pytest.approx(0.071)
    assert len(treated.economies) == 2

    spread = native_world_treatment_spec(
        baseline, field="fx_spread", value=0.004
    )
    assert spread.rules.fx_spread == pytest.approx(0.004)


@pytest.mark.parametrize(
    ("scenario", "attribute", "ratio"),
    [
        ("positive_capital_gap", "initial_consumption_capital", 0.5),
    ],
)
def test_native_activation_scenario_changes_only_the_shared_condition(
    scenario: str,
    attribute: str,
    ratio: float,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=29
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    before_rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    before = getattr(before_rules, attribute)
    apply_native_activation_scenario(native_spec, scenario=scenario)
    after_rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    assert getattr(after_rules, attribute) == pytest.approx(before * ratio)


def test_unknown_native_activation_scenario_is_rejected() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=31
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    with pytest.raises(ValueError, match="unknown native activation scenario"):
        apply_native_activation_scenario(native_spec, scenario="unsupported")


def test_idle_firm_activation_isolates_shell_exit() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=730, seed=37
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(
        native_spec, scenario="idle_consumption_firms"
    )
    economy = native_spec.economies[0]
    financial = economy.domestic_economy.financial_economy
    real_rules = financial.monetary_economy.real_economy.rules
    assert real_rules.initial_consumption_capital == pytest.approx(1.0e-12)
    assert real_rules.initial_consumption_inventory == pytest.approx(0.0)
    assert real_rules.investment_adjustment == pytest.approx(0.0)
    assert financial.rules.firm_subscale_exit is False


def test_opening_stockout_activation_preserves_the_rationing_signal() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=38
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    expected_signal = rules.consumption_rationed_signal
    apply_native_activation_scenario(
        native_spec, scenario="opening_consumption_stockout"
    )
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    assert rules.initial_consumption_inventory == pytest.approx(0.0)
    assert rules.consumption_rationed_signal is expected_signal


@pytest.mark.parametrize(
    ("scenario", "bound_name", "inventory_ratio"),
    [
        ("markup_ceiling_pressure", "markup_maximum", 0.0),
        ("markup_floor_pressure", "markup_minimum", 4.0),
    ],
)
def test_markup_bound_activation_preserves_the_audited_bound(
    scenario: str,
    bound_name: str,
    inventory_ratio: float,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=39
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    expected_bound = getattr(rules, bound_name)
    opening_inventory = rules.initial_consumption_inventory
    apply_native_activation_scenario(native_spec, scenario=scenario)
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    assert getattr(rules, bound_name) == pytest.approx(expected_bound)
    assert rules.initial_consumption_inventory == pytest.approx(
        opening_inventory * inventory_ratio
    )


def test_active_job_ladder_activation_preserves_search_intensity() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=40
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.economies[0].domestic_economy.rules
    expected_intensity = rules.ladder_search_intensity
    apply_native_activation_scenario(
        native_spec, scenario="active_job_ladder"
    )
    rules = native_spec.economies[0].domestic_economy.rules
    assert rules.ladder_premium == pytest.approx(0.0)
    assert rules.ladder_search_intensity == pytest.approx(expected_intensity)


def test_binding_labor_reservation_preserves_quit_hazard() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=41
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.economies[0].domestic_economy.rules
    expected_hazard = rules.welfare_quit_hazard
    apply_native_activation_scenario(
        native_spec, scenario="binding_labor_reservation"
    )
    rules = native_spec.economies[0].domestic_economy.rules
    assert rules.reservation_markup == pytest.approx(2.5)
    assert rules.welfare_quit_hazard == pytest.approx(expected_hazard)


def test_labor_demand_contraction_preserves_layoff_band() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=42
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    expected_band = native_spec.economies[0].domestic_economy.rules.layoff_band
    opening_demand = rules.initial_expected_demand
    apply_native_activation_scenario(
        native_spec, scenario="labor_demand_contraction"
    )
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    population_rules = native_spec.economies[0].domestic_economy.rules
    assert population_rules.layoff_band == pytest.approx(expected_band)
    assert rules.initial_expected_demand == pytest.approx(opening_demand * 4.0)
    assert rules.demand_adjustment == pytest.approx(0.10)


def test_entry_pressure_activation_preserves_the_daily_entry_cap() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=39
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    before = native_spec.economies[0].domestic_economy.financial_economy.rules
    expected_cap = before.entry_max
    apply_native_activation_scenario(
        native_spec, scenario="high_consumption_entry_pressure"
    )
    after = native_spec.economies[0].domestic_economy.financial_economy.rules
    assert after.entry_max == expected_cap
    assert after.entry_beta == pytest.approx(5.0)
    assert after.entry_hurdle == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("scenario", "unchanged_field"),
    [
        ("sector_returns_hazard", "switch_hazard"),
        ("sector_returns_pressure", "switch_pressure_days"),
        ("sector_returns_retool", "switch_retool_loss"),
        ("sector_returns_gap", "switch_return_gap"),
    ],
)
def test_sector_activation_preserves_the_audited_field(
    scenario: str,
    unchanged_field: str,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=41
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    before = native_spec.economies[0].domestic_economy.financial_economy.rules
    expected = getattr(before, unchanged_field)
    apply_native_activation_scenario(native_spec, scenario=scenario)
    after = native_spec.economies[0].domestic_economy.financial_economy.rules
    assert getattr(after, unchanged_field) == pytest.approx(expected)
