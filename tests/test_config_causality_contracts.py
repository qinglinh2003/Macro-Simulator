from __future__ import annotations

from macro_sim.diagnostics.config_contracts import (
    activation_contracts,
    build_contract_registry,
    invariance_contracts,
    screening_contracts,
)


def test_contract_registry_covers_every_inventory_field() -> None:
    payload = build_contract_registry()
    assert payload["field_count"] == 453
    assert len(payload["contracts"]) == 453
    assert len({item["field_id"] for item in payload["contracts"]}) == 453
    assert payload["status_counts"].get("blocked_native_route", 0) == 0


def test_executable_contracts_do_not_repeat_the_control_value() -> None:
    contracts = (
        *screening_contracts(),
        *activation_contracts(),
        *invariance_contracts(),
    )
    assert all(
        value != contract.baseline_value
        for contract in contracts
        for value in contract.treatment_values
    )


def test_securities_contracts_cover_each_executable_market_mechanism() -> None:
    contracts = screening_contracts(module="securities_and_capital_markets")
    assert len(contracts) == 21
    assert {contract.field_name for contract in contracts} == {
        "bank_bond_appetite",
        "bank_equity",
        "bank_equity_lambda",
        "bank_equity_trading",
        "bank_theta_equity",
        "bond_theta",
        "bonds",
        "equity_finance",
        "founder_owned_genesis",
        "lambda_p",
        "margin_credit",
        "per_firm_equity",
        "portfolio_adjust",
        "resid_income_lambda",
        "theta_equity",
        "valuation_discount_floor",
        "valuation_risk_premium",
        "w_chartist",
        "w_fundamental",
        "watchlist_size",
        "wealth_effect",
    }
    chartist = next(
        contract for contract in contracts if contract.field_name == "w_chartist"
    )
    assert chartist.treatment_values == (0.0, 20.0)
    activated = activation_contracts(
        module="securities_and_capital_markets"
    )
    assert {
        contract.field_name: contract.activation_scenario for contract in activated
    } == {
        "equity_ema_lambda": "active_equity_wealth_signal",
        "lambda_q": "active_q_investment_gap",
        "q_invest_cap": "q_investment_cap_pressure",
        "q_invest_floor": "q_investment_floor_pressure",
        "q_invest_smooth": "active_q_investment_gap",
        "trend_lambda": "active_chartist_demand",
    }
    invariance = invariance_contracts(
        module="securities_and_capital_markets"
    )
    assert {contract.field_name for contract in invariance} == {
        "shares_per_firm"
    }


def test_production_screening_contracts_are_curated_and_routed() -> None:
    contracts = screening_contracts(module="production_and_technology")
    assert len(contracts) == 15
    assert {contract.field_name for contract in contracts} == {
        "alpha",
        "capital_firm_entry",
        "capital_market",
        "capital_clock_demand_smoothing",
        "lambda_issue",
        "A",
        "a_K",
        "delta_K",
        "K_firm0",
        "tfp_drift_rate",
        "tfp_drift_c",
        "tfp_drift_k",
        "tfp_drift_e",
        "tfp_drift_sigma",
        "v",
    }
    assert all(contract.route_status == "mapped_native" for contract in contracts)
    assert all(contract.treatment_values for contract in contracts)
    assert all(contract.primary_metrics for contract in contracts)
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in contracts
    )


def test_activation_only_contracts_do_not_enter_neutral_screen() -> None:
    payload = build_contract_registry()
    contracts = {item["field_name"]: item for item in payload["contracts"]}
    assert contracts["capital_rationed_signal"]["status"] == (
        "activation_scenario_required"
    )
    assert contracts["capital_rationed_signal"]["activation_scenario"] == (
        "positive_capital_gap"
    )
    assert contracts["lambda_issue"]["activation_scenario"] == (
        "neutral_baseline_q_above_one"
    )
    assert contracts["lambda_issue"]["direction_statistics"] == {
        "metric.source.m6.primary_equity_raised": "first_window_mean"
    }
    assert contracts["lambda_I"]["activation_scenario"] == (
        "positive_capital_gap"
    )
    assert contracts["lambda_I"]["direction_statistics"] == {
        "metric.source.m4.fixed_capital_formation_real": "cumulative"
    }
    assert contracts["capital_rationed_signal"]["direction_statistics"] == {
        "metric.source.m4.fixed_capital_formation_real": "cumulative"
    }
    assert contracts["a"]["status"] == "excluded_non_treatment"


def test_activation_contracts_are_reviewed_and_separate() -> None:
    contracts = activation_contracts(module="production_and_technology")
    assert {contract.field_name for contract in contracts} == {
        "capital_rationed_signal",
        "lambda_I",
        "tfp_law",
        "tfp_learning_theta",
    }
    assert all(
        contract.status == "activation_scenario_required"
        for contract in contracts
    )


def test_firm_contracts_cover_every_mapped_causal_or_genesis_field() -> None:
    neutral = screening_contracts(module="firms_and_industrial_dynamics")
    activated = activation_contracts(module="firms_and_industrial_dynamics")
    assert len(neutral) == 12
    assert len(activated) == 13
    assert len({contract.field_name for contract in (*neutral, *activated)}) == 25
    assert "rho" in {contract.field_name for contract in neutral}
    assert "sector_switching" in {
        contract.field_name for contract in activated
    }
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )


def test_consumption_contracts_cover_every_mapped_causal_field() -> None:
    neutral = screening_contracts(
        module="consumption_prices_and_expectations"
    )
    activated = activation_contracts(
        module="consumption_prices_and_expectations"
    )
    assert len(neutral) == 9
    assert {contract.field_name for contract in activated} == {
        "consumption_rationed_signal",
        "mu_max",
        "mu_min",
        "pref_attach_beta",
        "pref_price_elasticity",
    }
    assert {contract.field_name for contract in (*neutral, *activated)} == {
        "alpha1",
        "alpha2",
        "consumption_rationed_signal",
        "eta",
        "inventory_gap_close",
        "lambda_d",
        "lambda_y",
        "mu_max",
        "mu_min",
        "phi",
        "pref_attach_beta",
        "pref_price_elasticity",
        "search_m",
        "theta_price",
    }
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )
def test_labor_contracts_cover_every_mapped_causal_field() -> None:
    neutral = screening_contracts(module="labor_market")
    activated = activation_contracts(module="labor_market")
    assert {contract.field_name for contract in activated} == {
        "labor_job_ladder",
        "labor_participation",
        "labor_relationship_wages",
        "ladder_search_intensity",
        "layoff_band",
        "wage_indexation",
        "welfare_quit_hazard",
    }
    assert {contract.field_name for contract in (*neutral, *activated)} == {
        "churn_annual",
        "delta",
        "efficiency_sigma",
        "job_search_intensity",
        "labor_fractional_hours",
        "labor_job_ladder",
        "labor_matching_friction",
        "labor_participation",
        "labor_relationship_wages",
        "labor_second_job",
        "labor_suspension",
        "ladder_premium",
        "ladder_search_intensity",
        "lambda_fire",
        "layoff_band",
        "layoff_target_smooth",
        "omega",
        "reservation_markup",
        "suspension_timer",
        "suspension_quit_discount",
        "theta_wage",
        "wage_indexation",
        "welfare_quit_hazard",
    }
    assert len(neutral) == 16
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )
    accounting = next(
        row
        for row in build_contract_registry()["contracts"]
        if row["field_id"] == "config.labor_accounting"
    )
    assert accounting["route_status"] == "native_fixed"
    assert accounting["status"] == "invariance_review_required"


def test_demography_contracts_cover_every_mapped_causal_field() -> None:
    neutral = screening_contracts(module="demography_and_households")
    activated = activation_contracts(module="demography_and_households")
    slow_development_fields = {
        "demo_signal_halflife_years",
        "fertility_income_elasticity",
        "fertility_mult_hi",
        "fertility_mult_lo",
        "mortality_income_elasticity",
        "mortality_mult_hi",
        "mortality_mult_lo",
    }
    assert all(
        contract.horizon_days >= 1460
        for contract in activated
        if contract.field_name in slow_development_fields
    )
    assert {contract.field_name for contract in activated} == {
        "demo_feedback_burnin_years",
        "demo_signal_halflife_years",
        "demographic_adult_leaving_home_enabled",
        "demographic_annual_leave_rate_late",
        "demographic_annual_leave_rate_peak",
        "demographic_leave_home_peak_end_age",
        "fertility_income_elasticity",
        "fertility_mult_hi",
        "fertility_mult_lo",
        "guardian_max_household_size",
        "guardian_search_adult_siblings",
        "guardian_search_grandparents",
        "guardian_search_same_household_adults",
        "marriage_acceptance_base",
        "marriage_age_gap_mean",
        "marriage_age_gap_penalty",
        "marriage_age_gap_sd",
        "marriage_age_width",
        "marriage_assortativity",
        "marriage_max_age",
        "marriage_max_age_gap",
        "marriage_peak_age",
        "max_children_per_parent",
        "mortality_income_elasticity",
        "mortality_mult_hi",
        "mortality_mult_lo",
        "remarriage_rate_multiplier",
        "target_partnered_adult_share",
        "union_target_profile",
        "widowed_remarriage_multiplier",
    }
    assert {contract.field_name for contract in (*neutral, *activated)} == {
        "demo_feedback_burnin_years",
        "demo_signal_halflife_years",
        "demographic_adult_leaving_home_enabled",
        "demographic_annual_divorce_rate_base",
        "demographic_annual_leave_rate_late",
        "demographic_annual_leave_rate_peak",
        "demographic_annual_marriage_rate_peak",
        "demographic_divorce_enabled",
        "demographic_leave_home_min_age",
        "demographic_leave_home_peak_end_age",
        "demographic_lifecycle_consumption",
        "demographic_marriage_enabled",
        "demographic_marriage_market_interval_days",
        "demographics_enabled",
        "demographics_mortality_scale",
        "demographics_tfr",
        "divorce_age_gap_multiplier_per_10y",
        "divorce_child_multiplier",
        "divorce_duration_width",
        "divorce_peak_duration_years",
        "divorce_peak_multiplier",
        "fertility_income_elasticity",
        "fertility_mult_hi",
        "fertility_mult_lo",
        "fertility_rank_gradient",
        "guardian_max_household_size",
        "guardian_search_adult_siblings",
        "guardian_search_grandparents",
        "guardian_search_same_household_adults",
        "ideal_parent_age_gap",
        "lifecycle_alpha_income",
        "lifecycle_alpha_wealth_draw",
        "marriage_acceptance_base",
        "marriage_age_gap_mean",
        "marriage_age_gap_penalty",
        "marriage_age_gap_sd",
        "marriage_age_width",
        "marriage_assortativity",
        "marriage_max_age",
        "marriage_max_age_gap",
        "marriage_peak_age",
        "max_children_per_household",
        "max_children_per_parent",
        "mortality_income_elasticity",
        "mortality_mult_hi",
        "mortality_mult_lo",
        "mortality_rank_gradient",
        "parent_age_gap_sd",
        "parent_max_age_gap",
        "parent_min_age_gap",
        "remarriage_rate_multiplier",
        "spouse_age_gap_sd",
        "spouse_max_age_gap",
        "target_partnered_adult_share",
        "two_parent_assignment_share",
        "union_target_profile",
        "widowed_remarriage_multiplier",
    }
    assert len(neutral) == 28
    assert len(activated) == 30
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )
    child_capacity = next(
        contract
        for contract in activated
        if contract.field_name == "max_children_per_parent"
    )
    assert child_capacity.expected_directions == {
        "metric.source.m7.dual_parent_minor_share": "increase",
        "metric.source.m7.maximum_household_size": "increase",
    }
    lifecycle = next(
        row
        for row in build_contract_registry()["contracts"]
        if row["field_id"] == "config.demographic_lifecycle_consumption"
    )
    assert lifecycle["status"] == "screening_ready"


def test_housing_upper_clamps_use_the_structural_monotonic_direction() -> None:
    contracts = {
        contract.field_name: contract
        for contract in activation_contracts(module="housing")
    }
    assert contracts["housing_fertility_mult_hi"].expected_directions == {
        "metric.source.m8.housing.fertility_multiplier": "increase"
    }
    assert contracts["housing_leave_mult_hi"].expected_directions == {
        "metric.source.m8.housing.leave_home_multiplier": "increase"
    }


def test_distribution_contracts_cover_every_mapped_causal_field() -> None:
    neutral = screening_contracts(module="distribution_and_welfare")
    activated = activation_contracts(module="distribution_and_welfare")
    assert {contract.field_name for contract in neutral} == {
        "family_transfer_buffer",
        "family_transfers",
        "mpc_dispersion",
        "n_firm_share",
        "necessity_share0",
        "strat_mult_hi",
        "strat_mult_lo",
    }
    assert {contract.field_name for contract in activated} == {
        "consumption_strata",
        "mpc_wealth_curvature",
    }
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in neutral
    )
    measurement = invariance_contracts(module="distribution_and_welfare")
    assert {contract.field_name for contract in measurement} == {
        "deprivation_gauges",
        "subsistence_share",
    }
    assert all(
        contract.activation_scenario == "deprivation_measurement_active"
        for contract in measurement
    )


def test_banking_contracts_cover_every_mapped_causal_field() -> None:
    neutral = screening_contracts(module="banking_and_credit")
    activated = activation_contracts(module="banking_and_credit")
    assert len(neutral) == 10
    assert len(activated) == 25
    assert {contract.field_name for contract in (*neutral, *activated)} == {
        "amort",
        "bank_assignment",
        "bank_dynamics",
        "bank_entry_beta",
        "bank_entry_max",
        "bank_enabled",
        "bank_leverage_disp",
        "bank_leverage_mean",
        "bank_rate_competition",
        "bank_realized_pnl",
        "bank_relationship_lock_in",
        "bank_runs",
        "bank_search_m",
        "bank_spread_disp",
        "deposit_interest_arrears",
        "deposit_rate",
        "deposit_rate_disp",
        "deposit_search_m",
        "hh_amort",
        "hh_subsistence",
        "household_credit",
        "household_interest_arrears",
        "interbank",
        "interbank_rate_base",
        "interbank_tightness",
        "interest_by_deposits",
        "investment_user_cost_elasticity",
        "investment_user_cost_floor",
        "investment_user_cost_multiplier_max",
        "investment_user_cost_multiplier_min",
        "monetary_direct_transmission",
        "run_fear_persistence",
        "run_health_ref",
        "run_market_weight",
        "run_sensitivity",
    }
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )
    user_cost_metric = (
        "metric.source.m5.investment_user_cost_multiplier_mean"
    )
    user_cost_fields = {
        "investment_user_cost_elasticity",
        "investment_user_cost_floor",
        "investment_user_cost_multiplier_max",
        "investment_user_cost_multiplier_min",
    }
    for contract in activated:
        if contract.field_name in user_cost_fields:
            assert contract.direction_statistics == {
                user_cost_metric: "post_burnin_mean"
            }


def test_bank_assignment_draft_uses_the_canonical_enum_spelling() -> None:
    contract = next(
        row
        for row in build_contract_registry()["contracts"]
        if row["field_id"] == "config.bank_assignment"
    )
    assert contract["treatment_values"] == ("by_size",)


def test_government_contracts_cover_every_executable_causal_field() -> None:
    neutral = screening_contracts(module="government_and_public_sector")
    activated = activation_contracts(module="government_and_public_sector")
    assert {contract.field_name for contract in activated} == {
        "jg_productivity"
    }
    assert {contract.field_name for contract in neutral} == {
        "government",
        "public_capital_depreciation",
        "public_capital_gamma",
    }
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in neutral
    )
    government = next(
        row
        for row in build_contract_registry()["contracts"]
        if row["field_id"] == "config.government"
    )
    assert government["status"] == "screening_ready"
