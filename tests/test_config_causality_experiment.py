from __future__ import annotations

import pytest

from macro_sim import native_backend
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    apply_config_treatment,
    derive_analysis_metrics,
    effect_scales,
    native_nested_treatment_spec,
    native_treatment_spec,
    native_world_treatment_spec,
    paired_effect,
    population_scaled_new_game,
    population_scaled_configs,
    summarize_metric_series,
    summarize_paired_runs,
    summarize_time_responses,
)


def test_nested_relationship_and_social_treatments_reach_m7_rules() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=30, seed=189, countries=2
    )
    relationship = native_nested_treatment_spec(
        baseline,
        scope="relationship",
        field="parent_min_age_gap",
        value=21,
        target_economy=1,
    )
    assert (
        relationship.economies[0]
        .domestic_economy.rules.genesis_parent_minimum_age_gap
        != 21
    )
    assert (
        relationship.economies[1]
        .domestic_economy.rules.genesis_parent_minimum_age_gap
        == 21
    )

    social = native_nested_treatment_spec(
        baseline,
        scope="social",
        field="marriage_age_gap_mean",
        value=4.0,
    )
    assert (
        social.economies[0]
        .domestic_economy.rules.marriage_rules.preferred_age_gap
        == pytest.approx(4.0)
    )


def test_nested_union_profiles_preserve_six_band_contract() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=30, seed=188
    )
    bands = {
        "bands": [
            {"target_share": value}
            for value in (0.05, 0.20, 0.40, 0.60, 0.50, 0.25)
        ]
    }
    treated = native_nested_treatment_spec(
        baseline,
        scope="relationship",
        field="union_target_profile",
        value=bands,
    )
    profile = (
        treated.economies[0]
        .domestic_economy.rules.genesis_union_target_profile
    )
    assert profile.enabled is True
    assert list(profile.shares) == pytest.approx(
        [0.05, 0.20, 0.40, 0.60, 0.50, 0.25]
    )

    disabled = native_nested_treatment_spec(
        baseline,
        scope="social",
        field="union_target_profile",
        value=None,
    )
    assert (
        disabled.economies[0]
        .domestic_economy.rules.social_union_target_profile.enabled
        is False
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


def test_native_tfp_treatments_reach_the_sector_state_machine() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=30, seed=190, countries=1
    )
    sector = native_treatment_spec(
        baseline, field="tfp_drift_e", value=0.024
    )
    rules = (
        sector.economies[0].domestic_economy.financial_economy
        .monetary_economy.real_economy.rules
    )
    assert rules.annual_tfp_growth_energy == pytest.approx(0.024)

    learning = native_treatment_spec(
        baseline, field="tfp_law", value="learning"
    )
    learning_rules = (
        learning.economies[0].domestic_economy.financial_economy
        .monetary_economy.real_economy.rules
    )
    assert str(learning_rules.tfp_law).endswith("LEARNING")


def test_household_energy_capability_closes_dependent_mortality_channel() -> None:
    baseline = population_scaled_configs(
        population=100_000, days=90, seed=20
    )
    treated = apply_config_treatment(
        baseline, field="energy_household", value=False
    )
    assert treated[0].energy_household is False
    assert treated[0].energy_mortality_gamma == pytest.approx(0.0)


def test_bank_disable_treatment_retains_native_fiscal_settlement_vertical() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=30, seed=21, countries=1
    )
    treated = native_treatment_spec(
        baseline, field="bank_enabled", value=False
    )
    economy = treated.economies[0].domestic_economy
    monetary = economy.financial_economy.monetary_economy
    assert monetary.rules.banking_enabled is False
    assert monetary.rules.household_credit is False
    assert monetary.real_economy.requested_capabilities == (1 << 0) | (1 << 1)


def test_government_disable_treatment_runs_without_fiscal_flows() -> None:
    baseline = population_scaled_new_game(
        population=1_000, days=5, seed=22, countries=1
    )
    treated = native_treatment_spec(
        baseline, field="government", value=False
    )
    real = (
        treated.economies[0].domestic_economy.financial_economy
        .monetary_economy.real_economy
    )
    assert real.requested_capabilities == 1 << 0
    session = native_backend.NativeSimulationSession.create_from_native_spec(
        treated, worker_count=8
    )
    session.advance(5)
    metrics = session.maintained_metrics()["economies"][0]
    assert metrics["metric.source.m4.tax_total"] == pytest.approx(0.0)
    assert metrics["metric.source.m4.government_spending"] == pytest.approx(0.0)
    assert metrics["metric.source.m4.transfer_payments"] == pytest.approx(0.0)
    assert metrics["metric.source.m7.pension_paid"] == pytest.approx(0.0)
    assert metrics["metric.economy.gov_debt"] == pytest.approx(0.0)


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


def test_sparse_transaction_proxy_uses_price_index_then_carries_last_trade() -> None:
    from macro_sim.diagnostics.config_experiment import _fill_sparse_analysis_metrics

    rows = [
        {"metric.economy.price_index": 1.2},
        {
            "metric.economy.price_index": 1.3,
            "metric.analysis.goods_transaction_price_proxy": 0.8,
        },
        {"metric.economy.price_index": 1.4},
    ]
    _fill_sparse_analysis_metrics(rows)
    assert [
        row["metric.analysis.goods_transaction_price_proxy"] for row in rows
    ] == pytest.approx([1.2, 0.8, 0.8])


@pytest.mark.parametrize(
    ("field", "value", "attribute"),
    [
        ("pref_attach_beta", 2.0, "preferential_attachment_beta"),
        ("pref_price_elasticity", 2.0, "preferential_price_elasticity"),
    ],
)
def test_consumer_choice_activation_preserves_the_audited_preference(
    field: str, value: float, attribute: str
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=27
    )
    native_spec = native_treatment_spec(baseline, field=field, value=value)
    before = native_spec.economies[0].domestic_economy.financial_economy.monetary_economy.real_economy
    opening_inventory = before.rules.initial_consumption_inventory
    apply_native_activation_scenario(
        native_spec, scenario="consumer_choice_market"
    )
    real = native_spec.economies[0].domestic_economy.financial_economy.monetary_economy.real_economy
    assert getattr(real.rules, attribute) == pytest.approx(value)
    assert real.rules.initial_consumption_inventory == pytest.approx(
        20.0 * opening_inventory
    )
    assert real.rules.price_calvo_probability == pytest.approx(1.0)
    assert real.rules.income_propensity == pytest.approx(0.10)
    assert real.rules.wealth_propensity == pytest.approx(0.001)


def test_gibrat_capability_selects_the_matching_protocol() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=28
    )
    disabled = native_treatment_spec(
        baseline, field="gibrat_growth", value=False
    )
    real = disabled.economies[0].domestic_economy.financial_economy.monetary_economy.real_economy
    assert not real.rules.gibrat_growth
    assert real.market_protocol == native_backend._load_native().MatchingProtocol.SAMPLED


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
    assert effect.mean_absolute_difference == pytest.approx(1.0)
    assert effect.mean_absolute_relative_difference is None
    assert effect.pathwise_material_share is None


def test_paired_effect_preserves_pathwise_materiality_when_signs_cancel() -> None:
    effect = paired_effect([100.0, 100.0], [98.0, 102.0])
    assert effect.mean_difference == pytest.approx(0.0)
    assert effect.mean_absolute_difference == pytest.approx(2.0)
    assert effect.mean_absolute_relative_difference == pytest.approx(0.02)
    assert effect.pathwise_material_share == pytest.approx(1.0)


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

    autarky = native_world_treatment_spec(
        baseline, field="trade", value=False
    )
    assert autarky.rules.trade is False
    assert autarky.rules.capital is False
    assert autarky.rules.migration is False


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("world_trade_integration", "trade"),
        ("world_trade_friction", "trade_friction"),
        ("world_capital_rate_gap", "capital"),
        ("world_migration_wage_gap", "migration"),
        ("world_migration_cap_pressure", "migration_cap"),
        ("world_peg_pressure", "peg"),
        ("world_dealer_loss", "dealer"),
    ],
)
def test_world_activation_scenarios_create_the_shared_identification_state(
    scenario: str, expected: str
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=730, seed=24, countries=3
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)

    apply_native_activation_scenario(native_spec, scenario=scenario)

    if expected in {"trade", "peg", "dealer"}:
        real0 = (
            native_spec.economies[0]
            .domestic_economy.financial_economy.monetary_economy.real_economy
        )
        real1 = (
            native_spec.economies[1]
            .domestic_economy.financial_economy.monetary_economy.real_economy
        )
        assert real0.rules.initial_consumption_inventory == pytest.approx(0.0)
        assert real1.rules.initial_consumption_inventory > 0.0
    if expected == "trade_friction":
        real0 = (
            native_spec.economies[0]
            .domestic_economy.financial_economy.monetary_economy.real_economy
        )
        real1 = (
            native_spec.economies[1]
            .domestic_economy.financial_economy.monetary_economy.real_economy
        )
        assert real0.rules.initial_consumption_inventory > 0.0
        assert real1.rules.initial_consumption_inventory == pytest.approx(0.0)
    if expected == "capital":
        rates = [
            economy.domestic_economy.financial_economy.monetary_economy.initial_policy_rate
            for economy in native_spec.economies
        ]
        assert rates == pytest.approx([0.00030, 0.00005, 0.000134])
    if expected in {"migration", "migration_cap"}:
        wages = [
            economy.domestic_economy.financial_economy.monetary_economy.real_economy.rules.initial_wage
            for economy in native_spec.economies
        ]
        assert wages == pytest.approx([2.0, 0.70, 0.70])
    if expected == "migration_cap":
        assert native_spec.rules.migration_rate == pytest.approx(0.05)
        assert native_spec.rules.wage_smoothing == pytest.approx(0.20)
    if expected == "peg":
        assert native_spec.external_policies[0].peg_anchor == 1
        assert str(native_spec.external_policies[0].fx_regime).endswith("PEG")
    if expected in {"peg", "dealer"}:
        assert native_spec.rules.fx_adjustment == pytest.approx(0.25)


def test_zero_baseline_builder_seed_uses_the_product_density_scale() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=24
    )
    assert baseline.configs()[0].builder_demand_seed == pytest.approx(0.0)
    treated = native_treatment_spec(
        baseline, field="builder_demand_seed", value=0.01
    )
    rules = treated.economies[0].housing_rules
    assert rules.builder_count == 625
    assert rules.builder_demand_seed == pytest.approx(0.04)


def test_housing_search_activation_preserves_the_audited_search_count() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=180, seed=25
    )
    native_spec = native_treatment_spec(
        baseline, field="housing_search_k", value=1
    )
    apply_native_activation_scenario(
        native_spec, scenario="housing_search_friction"
    )
    economy = native_spec.economies[0]
    assert economy.housing_rules.buyer_search_count == 1
    assert economy.housing_rules.initial_dwellings_per_household == pytest.approx(
        1.20
    )


def test_housing_liquid_activation_preserves_the_audited_wealth_effect() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=26
    )
    native_spec = native_treatment_spec(
        baseline, field="housing_wealth_effect", value=0.25
    )
    apply_native_activation_scenario(native_spec, scenario="housing_liquid_market")
    economy = native_spec.economies[0]
    assert economy.housing_rules.wealth_effect == pytest.approx(0.25)
    assert economy.housing_rules.initial_homeownership_share == pytest.approx(0.40)


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


def test_native_population_rules_receive_suspension_quit_discount() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=411
    )
    native_spec = native_treatment_spec(
        baseline, field="suspension_quit_discount", value=1.2
    )
    rules = native_spec.economies[0].domestic_economy.rules
    assert rules.suspension_quit_discount == pytest.approx(1.2)


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


def test_job_guarantee_public_works_activation_preserves_productivity() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=421
    )
    native_spec = native_treatment_spec(
        baseline, field="jg_productivity", value=0.75
    )
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    assert rules.job_guarantee_productivity == pytest.approx(0.75)
    apply_native_activation_scenario(
        native_spec, scenario="active_job_guarantee_public_works"
    )
    monetary = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy
    )
    assert monetary.policy.job_guarantee is True
    assert monetary.policy.job_guarantee_wage_ratio == pytest.approx(0.5)
    assert monetary.policy.job_guarantee_public_works_share == pytest.approx(1.0)
    assert monetary.real_economy.rules.job_guarantee_productivity == pytest.approx(
        0.75
    )


def test_unpartnered_marriage_activation_preserves_assortativity() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=43
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.economies[0].domestic_economy.rules
    expected_assortativity = rules.marriage_rules.assortativity
    apply_native_activation_scenario(
        native_spec, scenario="unpartnered_marriage_market"
    )
    population = native_spec.economies[0].domestic_economy
    rules = population.rules
    assert rules.genesis_union_target_profile.enabled is False
    assert rules.genesis_target_partnered_adult_share == pytest.approx(0.0)
    assert rules.marriage_interval_days == 14
    assert rules.annual_marriage_rate == pytest.approx(1.0)
    assert rules.annual_divorce_rate == pytest.approx(0.0)
    assert rules.marriage_rules.assortativity == pytest.approx(
        expected_assortativity
    )


def test_positive_wage_inflation_activation_preserves_indexation_treatment() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=30, seed=431
    )
    native_spec = native_treatment_spec(
        baseline, field="wage_indexation", value=0.25
    )
    apply_native_activation_scenario(
        native_spec, scenario="positive_wage_inflation_pulse"
    )
    rules = (
        native_spec.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy.rules
    )
    assert rules.wage_indexation == pytest.approx(0.25)
    assert rules.price_calvo_probability == pytest.approx(1.0)
    assert rules.wage_calvo_probability == pytest.approx(1.0)
    assert rules.wage_shortage_adjustment == pytest.approx(0.0)
    assert rules.wage_downward_drift == pytest.approx(0.0)


def test_mortality_treatment_preserves_genesis_age_profile() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=44
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    population = native_spec.economies[0].domestic_economy
    genesis_makeham = population.population.genesis_vital_rates.makeham_a
    runtime_makeham = population.rules.vital_rates.makeham_a
    assert population.population.fixed_genesis_vital_rates is True
    assert genesis_makeham == pytest.approx(runtime_makeham)

    native_spec = native_treatment_spec(
        baseline,
        field="demographics_mortality_scale",
        value=0.5,
    )
    population = native_spec.economies[0].domestic_economy
    assert population.population.genesis_vital_rates.makeham_a == pytest.approx(
        genesis_makeham
    )
    assert population.rules.vital_rates.makeham_a < genesis_makeham


@pytest.mark.parametrize(
    ("field", "native_field", "value"),
    (
        ("demographic_lifecycle_consumption", "lifecycle_consumption", False),
        ("lifecycle_alpha_income", "lifecycle_income_propensity", 0.45),
        (
            "lifecycle_alpha_wealth_draw",
            "lifecycle_wealth_draw_propensity",
            2.5,
        ),
        (
            "demo_feedback_burnin_years",
            "demographic_feedback_burnin_years",
            2,
        ),
        (
            "demo_signal_halflife_years",
            "demographic_signal_halflife_years",
            2.5,
        ),
        ("fertility_income_elasticity", "fertility_income_elasticity", 0.4),
        ("fertility_mult_lo", "fertility_multiplier_minimum", 0.6),
        ("fertility_mult_hi", "fertility_multiplier_maximum", 1.8),
        ("mortality_income_elasticity", "mortality_income_elasticity", 0.3),
        ("mortality_mult_lo", "mortality_multiplier_minimum", 0.7),
        ("mortality_mult_hi", "mortality_multiplier_maximum", 1.7),
    ),
)
def test_lifecycle_and_development_treatments_reach_population_rules(
    field: str,
    native_field: str,
    value: bool | float | int,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=3650, seed=441
    )
    native_spec = native_treatment_spec(
        baseline,
        field=field,
        value=value,
    )
    actual = getattr(
        native_spec.economies[0].domestic_economy.rules,
        native_field,
    )
    if isinstance(value, bool):
        assert actual is value
    elif isinstance(value, int):
        assert actual == value
    else:
        assert actual == pytest.approx(value)


@pytest.mark.parametrize(
    (
        "scenario",
        "growth",
        "signal_halflife",
        "fertility_elasticity",
        "mortality_elasticity",
    ),
    (
        ("demographic_real_wage_transition", 0.025, None, None, None),
        ("demographic_income_elasticity_transition", 0.025, 1.0, None, None),
        ("demographic_positive_income_transition", 0.08, 0.5, 4.0, 4.0),
        ("demographic_negative_income_transition", -0.05, 0.5, 4.0, 4.0),
    ),
)
def test_demographic_income_activation_builds_a_shared_wage_transition(
    scenario: str,
    growth: float,
    signal_halflife: float | None,
    fertility_elasticity: float | None,
    mortality_elasticity: float | None,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=3650, seed=442
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    population_rules = native_spec.economies[0].domestic_economy.rules
    initial_fertility = population_rules.fertility_income_elasticity
    initial_mortality = population_rules.mortality_income_elasticity

    apply_native_activation_scenario(native_spec, scenario=scenario)

    economy = native_spec.economies[0].domestic_economy
    real_rules = (
        economy.financial_economy.monetary_economy.real_economy.rules
    )
    population_rules = economy.rules
    assert real_rules.annual_tfp_growth == pytest.approx(growth)
    assert real_rules.wage_indexation == pytest.approx(1.0)
    assert population_rules.demographic_feedback_burnin_years == 4
    if signal_halflife is not None:
        assert population_rules.demographic_signal_halflife_years == pytest.approx(
            signal_halflife
        )
    if fertility_elasticity is None:
        assert population_rules.fertility_income_elasticity == pytest.approx(
            initial_fertility
        )
        assert population_rules.mortality_income_elasticity == pytest.approx(
            initial_mortality
        )
    else:
        assert population_rules.fertility_income_elasticity == pytest.approx(
            fertility_elasticity
        )
        assert population_rules.mortality_income_elasticity == pytest.approx(
            mortality_elasticity
        )


@pytest.mark.parametrize(
    ("scenario", "expected_peak_end"),
    (
        ("eligible_peak_leaving_home", 30),
        ("eligible_late_leaving_home", 18),
    ),
)
def test_leaving_home_activation_creates_an_eligible_genesis_cohort(
    scenario: str, expected_peak_end: int
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=45
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(native_spec, scenario=scenario)
    rules = native_spec.economies[0].domestic_economy.rules
    assert rules.leave_home_min_age == 18
    assert rules.leave_home_peak_end_age == expected_peak_end


def test_long_horizon_leaving_home_activation_preserves_survivors() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=7300, seed=45
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(
        native_spec, scenario="long_horizon_peak_leaving_home"
    )
    rules = native_spec.economies[0].domestic_economy.rules
    assert rules.leave_home_min_age == 18
    assert rules.leave_home_peak_end_age == 30
    assert rules.annual_leave_rate_peak == pytest.approx(0.05)
    assert rules.annual_leave_rate_late == pytest.approx(0.01)


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


def test_entrant_attractiveness_activation_creates_an_identifiable_entry_cohort() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=40
    )
    native_spec = native_treatment_spec(
        baseline, field="gibrat_entry_a0", value=0.05
    )
    apply_native_activation_scenario(
        native_spec, scenario="entrant_attractiveness_pressure"
    )
    economy = native_spec.economies[0]
    real = economy.domestic_economy.financial_economy.monetary_economy.real_economy
    financial = economy.domestic_economy.financial_economy
    assert real.consumption_firms == 50
    assert financial.rules.entry_beta == pytest.approx(50.0)
    assert financial.rules.entry_max == 25
    assert financial.rules.entrant_attractiveness == pytest.approx(0.05)
    assert real.rules.income_propensity == pytest.approx(0.10)


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


@pytest.mark.parametrize(
    ("scenario", "ruleset", "audited_field", "shared_field", "shared_value"),
    [
        (
            "bank_entry_eligible_founders",
            "financial",
            "bank_dynamics",
            "bank_minimum_capital",
            0.1,
        ),
        (
            "bank_entry_eligible_founders",
            "financial",
            "bank_entry_beta",
            "bank_minimum_capital",
            0.1,
        ),
        (
            "bank_entry_cap_pressure",
            "financial",
            "bank_entry_max",
            "bank_entry_beta",
            0.50,
        ),
        (
            "bank_run_pressure",
            "monetary",
            "bank_runs",
            "run_health_reference",
            0.22,
        ),
        (
            "bank_run_pressure",
            "monetary",
            "run_sensitivity",
            "run_health_reference",
            0.22,
        ),
        (
            "bank_run_fear_pressure",
            "monetary",
            "run_fear_persistence",
            "run_sensitivity",
            0.50,
        ),
        (
            "bank_run_health_screen",
            "monetary",
            "run_health_reference",
            "bank_runs",
            True,
        ),
        (
            "deposit_arrears_pressure",
            "monetary",
            "deposit_interest_arrears",
            "deposit_rate",
            0.005,
        ),
        (
            "deposit_spread_competition",
            "monetary",
            "deposit_search_count",
            "deposit_spread_dispersion",
            1.0e-4,
        ),
        (
            "deposit_spread_competition",
            "monetary",
            "interbank",
            "deposit_spread_dispersion",
            1.0e-4,
        ),
        (
            "deposit_spread_competition",
            "monetary",
            "interbank_rate_base",
            "deposit_spread_dispersion",
            1.0e-4,
        ),
        (
            "deposit_spread_competition",
            "monetary",
            "interbank_tightness",
            "deposit_spread_dispersion",
            1.0e-4,
        ),
        (
            "positive_deposit_carry",
            "monetary",
            "realized_bank_pnl",
            "deposit_rate",
            1.0e-4,
        ),
    ],
)
def test_banking_activation_preserves_the_audited_field(
    scenario: str,
    ruleset: str,
    audited_field: str,
    shared_field: str,
    shared_value: float | bool,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=47
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    financial = native_spec.economies[0].domestic_economy.financial_economy
    if ruleset == "financial":
        rules = financial.rules
        shared = financial.policy
    else:
        rules = financial.monetary_economy.rules
        shared = rules
    expected = getattr(rules, audited_field)

    apply_native_activation_scenario(native_spec, scenario=scenario)

    financial = native_spec.economies[0].domestic_economy.financial_economy
    if ruleset == "financial":
        rules = financial.rules
        shared = financial.policy if scenario.endswith("founders") else rules
    else:
        rules = financial.monetary_economy.rules
        shared = rules
    actual = getattr(rules, audited_field)
    if isinstance(expected, bool):
        assert actual is expected
    else:
        assert actual == pytest.approx(expected)
    assert getattr(shared, shared_field) == pytest.approx(shared_value)


@pytest.mark.parametrize(
    "audited_field", ["bank_leverage_mean", "bank_leverage_dispersion"]
)
def test_binding_bank_capital_preserves_the_audited_leverage_field(
    audited_field: str,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=365, seed=49
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    financial = native_spec.economies[0].domestic_economy.financial_economy
    expected = getattr(financial.monetary_economy.rules, audited_field)

    apply_native_activation_scenario(
        native_spec, scenario="binding_bank_capital"
    )

    financial = native_spec.economies[0].domestic_economy.financial_economy
    assert financial.monetary_economy.policy.bank_capital_constraint is True
    assert financial.monetary_economy.rules.opening_capital_per_bank == (
        pytest.approx(250.0)
    )
    assert getattr(financial.monetary_economy.rules, audited_field) == (
        pytest.approx(expected)
    )


@pytest.mark.parametrize(
    "audited_field", ["deprivation", "deprivation_subsistence_share"]
)
def test_deprivation_activation_preserves_the_audited_measurement_field(
    audited_field: str,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=53
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.economies[0].energy_rules
    expected = getattr(rules, audited_field)

    apply_native_activation_scenario(
        native_spec, scenario="deprivation_measurement_active"
    )

    rules = native_spec.economies[0].energy_rules
    assert rules.deprivation_burnin_years == 0
    if isinstance(expected, bool):
        assert getattr(rules, audited_field) is expected
    else:
        assert getattr(rules, audited_field) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("scenario", "field", "value", "shared_field", "shared_value"),
    [
        (
            "energy_inventory_gap",
            "energy_gap_close",
            0.20,
            "downstream_coverage_days",
            30.0,
        ),
        (
            "energy_rising_price",
            "energy_hoarding_beta",
            5.0,
            "producer_productivity",
            0.50,
        ),
        (
            "energy_mortality_pressure",
            "energy_mortality_gamma",
            4.0,
            "fuel_poverty_mortality_cap",
            5.0,
        ),
        (
            "energy_mortality_cap_binding",
            "energy_mortality_mult_hi",
            2.0,
            "fuel_poverty_mortality_gamma",
            10.0,
        ),
    ],
)
def test_energy_activation_preserves_the_audited_field(
    scenario: str,
    field: str,
    value: float,
    shared_field: str,
    shared_value: float,
) -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=1095, seed=59
    )
    native_spec = native_treatment_spec(baseline, field=field, value=value)
    rules = native_spec.economies[0].energy_rules
    expected = getattr(
        rules,
        {
            "energy_gap_close": "downstream_gap_close",
            "energy_hoarding_beta": "hoarding_beta",
            "energy_mortality_gamma": "fuel_poverty_mortality_gamma",
            "energy_mortality_mult_hi": "fuel_poverty_mortality_cap",
        }[field],
    )

    apply_native_activation_scenario(native_spec, scenario=scenario)

    rules = native_spec.economies[0].energy_rules
    assert getattr(
        rules,
        {
            "energy_gap_close": "downstream_gap_close",
            "energy_hoarding_beta": "hoarding_beta",
            "energy_mortality_gamma": "fuel_poverty_mortality_gamma",
            "energy_mortality_mult_hi": "fuel_poverty_mortality_cap",
        }[field],
    ) == pytest.approx(expected)
    assert getattr(rules, shared_field) == pytest.approx(shared_value)
