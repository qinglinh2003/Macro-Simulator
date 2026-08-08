"""Stable Python facade for the native simulation engine.

The extension module intentionally exposes low-level, typed C++ contracts.  This
module owns the product-facing conversion from :class:`NewGameSpec` and the
current immutable ``Config`` seed into those contracts.  Economic stepping stays
entirely in C++; Python only constructs a run, submits boundary transactions and
projects returned native state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import sys
from typing import Any, Iterable, Mapping

from macro_sim.config import Config
from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import Policy
from macro_sim.core.policy_registry import EconomySet, REGISTRY
from macro_sim.desktop.new_game import NewGameSpec


def _load_native():
    if "_native" in sys.modules:
        return sys.modules["_native"]
    try:
        import _native as native  # type: ignore[import-not-found]
    except ImportError:
        from macro_sim import _native as native
    return native


def _assign(target: Any, source: Any, aliases: Mapping[str, str]) -> None:
    """Copy an audited set of source attributes into a native contract."""
    for target_name, source_name in aliases.items():
        value = getattr(source, source_name)
        # nanobind's optional setter on the in-tree stable-ABI build does not
        # accept ``None`` on every supported Python minor.  Native defaults are
        # already disengaged optionals, so only materialized values need copying.
        if value is not None:
            setattr(target, target_name, value)


M4_RULE_FIELDS = {
    "linear_productivity": "a",
    "capital_productivity": "a_K",
    "total_factor_productivity": "A",
    "capital_share": "alpha",
    "capital_output_ratio": "v",
    "demand_adjustment": "lambda_d",
    "capital_clock_demand_smoothing": "capital_clock_demand_smoothing",
    "income_adjustment": "lambda_y",
    "inventory_ratio": "phi",
    "inventory_gap_close": "inventory_gap_close",
    "markup_adjustment": "eta",
    "markup_minimum": "mu_min",
    "markup_maximum": "mu_max",
    "diseconomy_slope": "dis_slope",
    "gibrat_growth": "gibrat_growth",
    "gibrat_sigma": "gibrat_sigma",
    "preferential_attachment_beta": "pref_attach_beta",
    "preferential_price_elasticity": "pref_price_elasticity",
    "wage_shortage_adjustment": "omega",
    "wage_downward_drift": "delta",
    "wage_calvo_probability": "theta_wage",
    "wage_indexation": "wage_indexation",
    "price_calvo_probability": "theta_price",
    "income_propensity": "alpha1",
    "wealth_propensity": "alpha2",
    "mpc_dispersion": "mpc_dispersion",
    "mpc_wealth_curvature": "mpc_wealth_curvature",
    "consumption_strata": "consumption_strata",
    "dividend_payout": "rho",
    "investment_adjustment": "lambda_I",
    "capital_depreciation": "delta_K",
    "annual_tfp_growth": "tfp_drift_rate",
    "annual_tfp_growth_consumption": "tfp_drift_c",
    "annual_tfp_growth_capital": "tfp_drift_k",
    "annual_tfp_growth_energy": "tfp_drift_e",
    "annual_tfp_volatility": "tfp_drift_sigma",
    "tfp_learning_theta": "tfp_learning_theta",
    "profit_tax_rate": "tax_profit_rate",
    "income_tax_rate": "tax_income_rate",
    "consumption_tax_rate": "tax_consumption_rate",
    "wealth_tax_rate": "tax_wealth_rate",
    "government_consumption_share": "gov_consumption_share",
    "government_deficit_target": "gov_deficit_target",
    "deficit_unemployment_reference": "deficit_u_ref",
    "deficit_unemployment_cap": "deficit_u_cap",
    "government_investment_share": "gov_investment_share",
    "public_capital_gamma": "public_capital_gamma",
    "public_capital_depreciation": "public_capital_depreciation",
    "unemployment_benefit_replacement": "benefit_replacement",
    "income_allowance": "income_allowance",
    "wealth_allowance": "wealth_allowance",
    "benefit_income_floor": "benefit_income_floor",
    "minimum_wage": "min_wage",
    "job_guarantee": "job_guarantee",
    "job_guarantee_wage_ratio": "jg_wage_ratio",
    "job_guarantee_productivity": "jg_productivity",
    "initial_household_money": "d_household0",
    "initial_firm_money": "d_cfirm0",
    "initial_capital_firm_money": "d_kfirm0",
    "initial_bank_capital": "d_bank0",
    "initial_consumption_inventory": "inv_firm0",
    "initial_capital_inventory": "inv_kfirm0",
    "initial_consumption_capital": "K_firm0",
    "initial_price": "p_firm0",
    "initial_capital_price": "p_kfirm0",
    "initial_wage": "w_firm0",
    "initial_markup": "mu_firm0",
    "initial_expected_demand": "demand_e_firm0",
    "capital_rationed_signal": "capital_rationed_signal",
    "consumption_rationed_signal": "consumption_rationed_signal",
    "market_sample_size": "search_m",
}

M5_POLICY_FIELDS = {
    "government_consumption_share": "gov_consumption_share",
    "government_deficit_target": "gov_deficit_target",
    "deficit_unemployment_reference": "deficit_u_ref",
    "deficit_unemployment_cap": "deficit_u_cap",
    "government_investment_share": "gov_investment_share",
    "profit_tax_rate": "tax_profit_rate",
    "income_tax_rate": "tax_income_rate",
    "income_allowance": "income_allowance",
    "consumption_tax_rate": "tax_consumption_rate",
    "necessity_consumption_tax_rate": "tax_necessity_rate",
    "luxury_consumption_tax_rate": "tax_luxury_rate",
    "wealth_tax_rate": "tax_wealth_rate",
    "wealth_allowance": "wealth_allowance",
    "unemployment_benefit_replacement": "benefit_replacement",
    "benefit_income_floor": "benefit_income_floor",
    "minimum_wage": "min_wage",
    "job_guarantee": "job_guarantee",
    "job_guarantee_wage_ratio": "jg_wage_ratio",
    "job_guarantee_public_works_share": "jg_public_works_share",
    "inflation_target": "inflation_target",
    "taylor_inflation": "taylor_phi_pi",
    "taylor_unemployment": "taylor_phi_u",
    "rate_inertia": "rate_inertia",
    "manual_policy_rate": "manual_policy_rate",
    "neutral_rate": "r_neutral",
    "natural_unemployment": "u_natural",
    "maximum_policy_rate": "r_max",
    "inflation_sensor_lambda": "infl_ema_lambda",
    "core_inflation_sensor": "cb_core_inflation",
    "fixed_basket_cpi": "cb_uses_fixed_basket_cpi",
    "logarithmic_inflation": "cb_log_inflation",
    "fiscal_uses_national_accounts_gdp":
        "fiscal_uses_national_accounts_gdp",
    "open_market_operations": "omo",
    "reserve_target": "omo_reserve_target",
    "reserve_gap_close": "omo_drain_frac",
    "reserve_target_indexes_deposits": "omo_index_deposits",
    "lender_of_last_resort": "lolr",
    "reserve_floor_fraction": "reserve_floor_frac",
    "firm_leverage_limit": "kappa",
    "firm_minimum_dscr": "firm_credit_min_dscr",
    "household_credit_limit": "hh_credit_limit",
    "bank_capital_constraint": "bank_capital_constraint",
    "unified_bank_rwa": "unified_bank_rwa",
    "bank_leverage_cap": "bank_leverage_cap",
    "bank_exposure_limit": "bank_exposure_limit",
    "bank_target_capital_ratio": "bank_target_capital_ratio",
    "deposit_rate_floor": "deposit_rate_floor",
    "migrate_relationships_on_failure": "bank_migrate_on_failure",
    "state_resolution_backstop": "bank_resolution_fund",
}

M5_RULE_FIELDS = {
    "bank_count": "n_banks",
    "opening_capital_per_bank": "d_bank0",
    "bank_leverage_mean": "bank_leverage_mean",
    "bank_leverage_dispersion": "bank_leverage_disp",
    "realized_bank_pnl": "bank_realized_pnl",
    "full_firm_pnl": "firm_full_pnl",
    "household_credit": "household_credit",
    "rate_competition": "bank_rate_competition",
    "relationship_lock_in": "bank_relationship_lock_in",
    "loan_spread_dispersion": "bank_spread_disp",
    "bank_search_count": "bank_search_m",
    "interbank": "interbank",
    "interbank_rate_base": "interbank_rate_base",
    "interbank_tightness": "interbank_tightness",
    "deposit_spread_dispersion": "deposit_rate_disp",
    "deposit_search_count": "deposit_search_m",
    "deposit_rate": "deposit_rate",
    "interest_by_deposits": "interest_by_deposits",
    "deposit_interest_arrears": "deposit_interest_arrears",
    "firm_amortization": "amort",
    "household_amortization": "hh_amort",
    "household_subsistence": "hh_subsistence",
    "direct_monetary_transmission": "monetary_direct_transmission",
    "investment_user_cost_elasticity": "investment_user_cost_elasticity",
    "investment_user_cost_multiplier_min": "investment_user_cost_multiplier_min",
    "investment_user_cost_multiplier_max": "investment_user_cost_multiplier_max",
    "investment_user_cost_floor": "investment_user_cost_floor",
    "bank_runs": "bank_runs",
    "run_sensitivity": "run_sensitivity",
    "run_health_reference": "run_health_ref",
    "run_fear_persistence": "run_fear_persistence",
}

M6_POLICY_FIELDS = {
    "bond_finance_fraction": "bond_finance_frac",
    "bond_coupon_rate": "bond_coupon",
    "bond_maturity_days": "bond_maturity",
    "bank_bond_duration_limit": "bank_bond_duration_limit",
    "margin_ltv": "margin_ltv",
    "margin_max": "margin_max",
    "household_bankruptcy": "household_bankruptcy",
    "bank_resolution_fund": "bank_resolution_fund",
    "bank_minimum_capital": "bank_min_capital",
    "bankrupt_persistence": "bankrupt_persist",
    "regulatory_capital_haircut":
        "regulatory_firm_capital_haircut",
    "regulatory_inventory_haircut":
        "regulatory_firm_inventory_haircut",
}

M7_POLICY_FIELDS = {
    "pension_replacement": "pension_replacement",
}

M6_RULE_FIELDS = {
    "bonds": "bonds",
    "bond_maturity_bucket": "bond_maturity_bucket",
    "firm_equity": "per_firm_equity",
    "shares_per_firm": "shares_per_firm",
    "watchlist_size": "watchlist_size",
    "founder_owned_genesis": "founder_owned_genesis",
    "genesis_founder_pool": "genesis_founder_pool",
    "equity_price_adjustment": "lambda_p",
    "equity_trend_lambda": "trend_lambda",
    "residual_income_lambda": "resid_income_lambda",
    "q_smoothing": "q_invest_smooth",
    "q_investment_sensitivity": "lambda_q",
    "q_investment_floor": "q_invest_floor",
    "q_investment_cap": "q_invest_cap",
    "household_equity_wealth_smoothing": "equity_ema_lambda",
    "household_equity_wealth_effect": "wealth_effect",
    "fundamental_weight": "w_fundamental",
    "chartist_weight": "w_chartist",
    "household_equity_target": "theta_equity",
    "portfolio_adjustment": "portfolio_adjust",
    "equity_finance": "equity_finance",
    "equity_issue_lambda": "lambda_issue",
    "margin_credit": "margin_credit",
    "valuation_discount_floor": "valuation_discount_floor",
    "valuation_risk_premium": "valuation_risk_premium",
    "capital_haircut": "firm_capital_haircut",
    "inventory_haircut": "firm_inventory_haircut",
    "firm_dynamics": "firm_dynamics",
    "bankrupt_persistence": "bankrupt_persist",
    "shell_exit_days": "shell_exit_ticks",
    "entry_hurdle": "entry_hurdle",
    "entry_beta": "entry_beta",
    "entry_max": "entry_max",
    "startup_deposits": "startup_deposits",
    "startup_capital": "startup_capital",
    "entrant_attractiveness": "gibrat_entry_a0",
    "firm_subscale_exit": "firm_subscale_exit",
    "capital_firm_entry": "capital_firm_entry",
    "subscale_viability_workers": "subscale_viability_workers",
    "subscale_grace_days": "subscale_grace_days",
    "subscale_exit_hazard": "subscale_exit_hazard",
    "k_entry_demand": "k_entry_demand",
    "k_entry_hazard": "k_entry_hazard",
    "consumption_strata": "consumption_strata",
    "necessity_firm_share": "n_firm_share",
    "sector_switching": "sector_switching",
    "switch_return_gap": "switch_return_gap",
    "switch_pressure_days": "switch_pressure_days",
    "switch_hazard": "switch_hazard",
    "switch_retool_loss": "switch_retool_loss",
    "bank_equity": "bank_equity",
    "bank_equity_trading": "bank_equity_trading",
    "bank_equity_lambda": "bank_equity_lambda",
    "bank_equity_target": "bank_theta_equity",
    "bank_dynamics": "bank_dynamics",
    "bank_entry_beta": "bank_entry_beta",
    "bank_entry_max": "bank_entry_max",
}

M7_RULE_FIELDS = {
    "fertility": "demographics_enabled",
    "mortality": "demographics_enabled",
    "persistent_labor": "labor_accounting",
    "fractional_hours": "labor_fractional_hours",
    "second_jobs": "labor_second_job",
    "suspensions": "labor_suspension",
    "annual_churn": "churn_annual",
    "firing_adjustment": "lambda_fire",
    "layoff_band": "layoff_band",
    "target_smoothing": "layoff_target_smooth",
    "suspension_timeout_days": "suspension_timer",
    "suspension_quit_discount": "suspension_quit_discount",
    "frictional_search": "labor_matching_friction",
    "search_intensity": "job_search_intensity",
    "relationship_wages": "labor_relationship_wages",
    "job_ladder": "labor_job_ladder",
    "ladder_search_intensity": "ladder_search_intensity",
    "ladder_premium": "ladder_premium",
    "person_efficiency": "labor_person_efficiency",
    "efficiency_sigma": "efficiency_sigma",
    "participation_margin": "labor_participation",
    "reservation_markup": "reservation_markup",
    "welfare_quit_hazard": "welfare_quit_hazard",
    "family_transfers": "family_transfers",
    "family_transfer_buffer": "family_transfer_buffer",
    "marriage": "demographic_marriage_enabled",
    "divorce": "demographic_divorce_enabled",
    "household_lifecycle": "demographic_lifecycle_consumption",
    "leaving_home": "demographic_adult_leaving_home_enabled",
    "leave_home_min_age": "demographic_leave_home_min_age",
    "leave_home_peak_end_age": "demographic_leave_home_peak_end_age",
    "annual_leave_rate_peak": "demographic_annual_leave_rate_peak",
    "annual_leave_rate_late": "demographic_annual_leave_rate_late",
    "marriage_interval_days": "demographic_marriage_market_interval_days",
    "annual_marriage_rate": "demographic_annual_marriage_rate_peak",
    "annual_divorce_rate": "demographic_annual_divorce_rate_base",
    "mortality_rank_gradient": "mortality_rank_gradient",
    "fertility_rank_gradient": "fertility_rank_gradient",
    "stratification_multiplier_minimum": "strat_mult_lo",
    "stratification_multiplier_maximum": "strat_mult_hi",
}

ENERGY_POLICY_FIELDS = {
    "excise_rate": "tax_energy_rate",
    "windfall_tax_rate": "tax_energy_windfall",
    "household_subsidy_rate": "energy_subsidy_rate",
    "subsidy_deposit_threshold": "energy_subsidy_threshold",
    "price_cap": "energy_price_cap",
    "price_cap_compensation": "energy_cap_compensation",
    "strategic_reserve_target": "spr_target_units",
    "strategic_reserve_flow_cap": "spr_flow_cap",
    "state_owned_price_at_cost": "soe_price_at_cost",
    "state_owned_first_producer": "soe_efirm",
}

ENERGY_RULE_FIELDS = {
    "enabled": "energy_enabled",
    "household_energy": "energy_household",
    "deprivation": "deprivation_gauges",
    "state_owned_first_producer": "soe_efirm",
    "producer_count": "n_firms_e",
    "initial_producer_cash": "d_efirm0",
    "initial_price": "p_efirm0",
    "initial_wage": "w_firm0",
    "initial_markup": "mu_firm0",
    "producer_productivity": "a_E",
    "capacity_per_capital": "kappa_E",
    "initial_utilization": "energy_util0",
    "producer_inventory_ratio": "phi",
    "demand_adjustment": "lambda_d",
    "markup_adjustment": "eta",
    "markup_minimum": "mu_min",
    "markup_maximum": "mu_max",
    "household_need": "energy_hh_share",
    "downstream_intensity": "energy_intensity",
    "downstream_coverage_days": "energy_coverage_ticks",
    "downstream_gap_close": "energy_gap_close",
    "hoarding_beta": "energy_hoarding_beta",
    "deprivation_burnin_years": "deprivation_burnin_years",
    "deprivation_subsistence_share": "subsistence_share",
    "deprivation_acute_days": "deprivation_acute_days",
    "deprivation_chronic_days": "deprivation_chronic_days",
    "fuel_poverty_mortality_gamma": "energy_mortality_gamma",
    "fuel_poverty_mortality_cap": "energy_mortality_mult_hi",
}

HOUSING_POLICY_FIELDS = {
    "annual_housing_permits": "housing_permits",
    "land_fee_share": "land_fee_share",
    "land_fee_stock_elasticity": "land_fee_stock_elasticity",
    "mortgage_arrears_floor": "mortgage_arrears_floor",
    "mortgage_dsti_cap": "mortgage_dsti_cap",
    "mortgage_foreclosure_ltv": "mortgage_foreclosure_ltv",
    "mortgage_ltv_cap": "mortgage_ltv_cap",
    "mortgage_minimum_capital_ratio": "mortgage_min_capital_ratio",
    "mortgage_risk_weight": "mortgage_risk_weight",
    "mortgage_stress_rate_addon": "mortgage_stress_rate_addon",
    "mortgage_underwriting": "mortgage_underwriting",
    "property_tax_rate": "housing_property_tax",
    "rental_eviction_arrears": "rental_eviction_arrears",
    "transfer_tax_rate": "housing_transfer_tax",
    "include_housing_in_wealth_tax": "housing_in_wealth_tax",
}

HOUSING_RULE_FIELDS = {
    "enabled": "housing_enabled",
    "resale_market": "housing_market_enabled",
    "mortgages": "mortgage_enabled",
    "rentals": "housing_rental_enabled",
    "construction": "housing_construction_enabled",
    "house_price_income_years": "house_price_income_years",
    "market_interval_days": "housing_session_interval",
    "voluntary_ask_markup": "housing_ask_markup",
    "forced_sale_discount": "housing_forced_discount",
    "ask_decay": "housing_ask_decay",
    "buyer_search_count": "housing_search_k",
    "buyer_liquidity_buffer": "housing_buyer_buffer",
    "distress_deposit_floor": "housing_distress_floor",
    "initial_rent_yield": "rent_yield0",
    "rent_adjustment": "rent_adjust",
    "rent_burden_cap": "rent_burden_cap",
    "rental_investor_premium": "rental_investor_premium",
    "rental_vacancy_deadband": "rental_vacancy_deadband",
    "rent_floor_wage_share": "rental_rent_floor_wage_share",
    "wealth_effect": "housing_wealth_effect",
    "demand_price_step": "housing_demand_step",
    "ask_floor_annual_wage_share": "housing_ask_floor_wage_share",
    "affordability_burnin_years": "housing_signal_burnin_years",
    "leave_home_elasticity": "housing_leave_elasticity",
    "leave_home_multiplier_minimum": "housing_leave_mult_lo",
    "leave_home_multiplier_maximum": "housing_leave_mult_hi",
    "fertility_elasticity": "housing_fertility_elasticity",
    "fertility_multiplier_minimum": "housing_fertility_mult_lo",
    "fertility_multiplier_maximum": "housing_fertility_mult_hi",
    "builder_count": "n_builders",
    "builder_productivity": "builder_productivity",
    "builder_demand_seed": "builder_demand_seed",
    "builder_demand_price_gain": "builder_demand_price_gain",
    "builder_finished_inventory_buffer": "builder_inventory_buffer",
    "builder_land_fee_credit": "builder_land_fee_credit",
}

DOMESTIC_POLICY_BINDINGS: dict[str, tuple[str, str]] = {
    source: ("fiscal_monetary", target)
    for target, source in M5_POLICY_FIELDS.items()
}
DOMESTIC_POLICY_BINDINGS.update({
    source: ("financial", target)
    for target, source in M6_POLICY_FIELDS.items()
})
DOMESTIC_POLICY_BINDINGS.update({
    source: ("population", target)
    for target, source in M7_POLICY_FIELDS.items()
})
DOMESTIC_POLICY_BINDINGS.update({
    source: ("energy", target)
    for target, source in ENERGY_POLICY_FIELDS.items()
})
DOMESTIC_POLICY_BINDINGS.update({
    source: ("housing", target)
    for target, source in HOUSING_POLICY_FIELDS.items()
})
EXTERNAL_POLICY_LEVERS = frozenset({
    "tariff", "import_quota", "export_subsidy", "capital_control",
    "external_interest_settlement_fraction", "sanctions_imposed_on",
    "immigration_cap", "emigration_cap", "remittance_tax",
    "outward_remittance_tax", "guest_worker_return", "fx_regime",
    "peg_anchor", "peg_reserve_scale",
})
SPECIAL_POLICY_LEVERS = frozenset({
    "monetary_regime", "energy_rationing", "bank_resolution_fund",
})
NATIVE_POLICY_LEVERS = (
    frozenset(DOMESTIC_POLICY_BINDINGS)
    | EXTERNAL_POLICY_LEVERS
    | SPECIAL_POLICY_LEVERS
)

# The original calibration counts establishments per household, while the
# current new-game manifest counts people and lets demographic genesis form
# households.  Convert the historical densities through the genesis household
# size before scaling representative firms.  Omitting this conversion makes
# every large economy 2.5x overcapitalized and overstocked at birth.
_REFERENCE_PERSONS_PER_HOUSEHOLD = 2.5
_REFERENCE_BASE_FIRMS_PER_PERSON = 0.20 / _REFERENCE_PERSONS_PER_HOUSEHOLD
_REFERENCE_ENERGY_FIRMS_PER_PERSON = 0.025 / _REFERENCE_PERSONS_PER_HOUSEHOLD
_REFERENCE_BUILDERS_PER_PERSON = 0.0625 / _REFERENCE_PERSONS_PER_HOUSEHOLD


def _representative_entity_scale(
    cfg: Any, count: int, reference_density: float,
) -> float:
    population = int(cfg.demographics_population)
    if population <= 0:
        return 1.0
    return max(
        1.0e-6,
        reference_density * float(population) / float(max(1, count)),
    )


def _policy_from_spec(
    spec: NewGameSpec, economy_id: int, cfg: Any
) -> tuple[Policy, ExternalPolicy]:
    domestic = Policy.from_config(cfg)
    external = ExternalPolicy()
    for key, value in spec.initial_policy_overrides.items():
        raw_economy, _seat, lever_name = key.split(".", 2)
        if int(raw_economy) != economy_id:
            continue
        lever = REGISTRY[lever_name]
        if isinstance(lever.validation, EconomySet):
            value = frozenset(value)
        target = external if lever.scope == "external" else domestic
        setattr(target, lever_name, value)
    return domestic, external


def _m4_spec(native: Any, cfg: Any, economy_id: int) -> Any:
    output = native.M4SimulationSpec()
    output.vertical = native.M4Vertical.CAPITAL_FISCAL
    output.economy_id = economy_id
    output.currency_id = economy_id
    output.households = max(1, int(cfg.n_households))
    output.consumption_firms = max(1, int(cfg.n_firms_c))
    output.capital_firms = max(1, int(cfg.n_firms_k))
    output.settlement_banks = max(1, int(cfg.n_banks))
    output.seed = int(cfg.seed)
    # M4 V1 owns only the physical-capital and government capability bits.
    output.requested_capabilities = (1 << 0) | (1 << 1)
    output.stochastic = bool(
        cfg.tfp_drift_sigma or (cfg.gibrat_growth and cfg.gibrat_sigma)
    )
    output.market_protocol = (
        native.MatchingProtocol.PREFERENTIAL
        if cfg.gibrat_growth
        else native.MatchingProtocol.SAMPLED
    )
    _assign(output.rules, cfg, M4_RULE_FIELDS)
    output.rules.necessity_need_per_unit = (
        float(cfg.necessity_share0) * float(cfg.w_firm0) / float(cfg.p_firm0)
        if cfg.consumption_strata
        else 0.0
    )
    output.rules.tfp_law = (
        native.M4TfpLaw.LEARNING
        if cfg.tfp_law == "learning"
        else native.M4TfpLaw.EXOGENOUS
    )
    firm_scale = _representative_entity_scale(
        cfg,
        output.consumption_firms + output.capital_firms,
        _REFERENCE_BASE_FIRMS_PER_PERSON,
    )
    for field_name in (
        "initial_firm_money",
        "initial_capital_firm_money",
        "initial_consumption_inventory",
        "initial_capital_inventory",
        "initial_consumption_capital",
    ):
        setattr(
            output.rules,
            field_name,
            float(getattr(output.rules, field_name)) * firm_scale,
        )
    demand_scale = _representative_entity_scale(
        cfg,
        output.consumption_firms + output.capital_firms,
        _REFERENCE_BASE_FIRMS_PER_PERSON,
    )
    output.rules.initial_expected_demand *= demand_scale
    return output


def _m8_spec(
    native: Any, spec: NewGameSpec, cfg: Any, economy_id: int
) -> tuple[Any, Any]:
    policy, external = _policy_from_spec(spec, economy_id, cfg)

    monetary = native.M5SimulationSpec()
    monetary.real_economy = _m4_spec(native, cfg, economy_id)
    monetary.initial_policy_rate = float(cfg.r_interest)
    _assign(monetary.policy, policy, M5_POLICY_FIELDS)
    monetary.policy.monetary_regime = {
        "exogenous": native.MonetaryRegime.EXOGENOUS,
        "taylor": native.MonetaryRegime.TAYLOR,
        "manual": native.MonetaryRegime.MANUAL,
    }[policy.monetary_regime]
    _assign(monetary.rules, cfg, M5_RULE_FIELDS)
    monetary.rules.assign_banks_by_size = cfg.bank_assignment == "by_size"

    financial = native.M6SimulationSpec()
    financial.monetary_economy = monetary
    _assign(financial.policy, policy, M6_POLICY_FIELDS)
    financial.policy.household_bond_target = float(cfg.bond_theta)
    financial.policy.bank_bond_appetite = float(cfg.bank_bond_appetite)
    _assign(financial.rules, cfg, M6_RULE_FIELDS)
    if not cfg.capital_market:
        financial.rules.firm_equity = False
        financial.rules.bank_equity = False
        financial.rules.bank_equity_trading = False
        financial.rules.equity_finance = False
        financial.rules.margin_credit = False
    if not cfg.bank_enabled:
        monetary.rules.household_credit = False
        monetary.rules.interbank = False
        monetary.rules.rate_competition = False
        monetary.rules.relationship_lock_in = False
        financial.rules.bank_equity = False
        financial.rules.bank_equity_trading = False
        financial.rules.bank_dynamics = False
        financial.monetary_economy = monetary

    population = native.M7SimulationSpec()
    population.financial_economy = financial
    population.policy.inheritance_tax_rate = float(cfg.tax_wealth_rate)
    _assign(population.policy, policy, M7_POLICY_FIELDS)
    _assign(population.rules, cfg, M7_RULE_FIELDS)
    population.rules.age_participation = bool(cfg.labor_participation)
    population.rules.genesis_employment_rate = (
        0.95 if cfg.labor_matching == "persistent" else 0.0
    )
    vital = population.rules.vital_rates
    vital.total_fertility_rate = float(cfg.demographics_tfr)
    vital.makeham_a *= float(cfg.demographics_mortality_scale)
    vital.gompertz_b *= float(cfg.demographics_mortality_scale)
    population.rules.vital_rates = vital
    population.population.fixed_genesis_vital_rates = True
    population.population.genesis_vital_rates = vital
    marriage = population.rules.marriage_rules
    marriage.assortativity = float(cfg.marriage_assortativity)
    population.rules.marriage_rules = marriage
    initial_persons = int(cfg.demographics_population or cfg.n_households)
    population.population.initial_persons = max(1, initial_persons)
    population.population.start_calendar_day = date.fromisoformat(
        cfg.simulation_start_date
    ).toordinal()
    # The Config field is the requested person count in the current start menu.
    # A demographic genesis then forms households around this target size.
    population.population.target_household_size = 2.5

    output = native.M8SimulationSpec()
    output.domestic_economy = population
    _assign(output.energy_policy, policy, ENERGY_POLICY_FIELDS)
    output.energy_policy.rationing = {
        "market": native.EnergyRationing.MARKET,
        "proportional": native.EnergyRationing.PROPORTIONAL,
        "household_first": native.EnergyRationing.HOUSEHOLD_FIRST,
        "industry_first": native.EnergyRationing.INDUSTRY_FIRST,
    }[policy.energy_rationing]
    _assign(output.energy_rules, cfg, ENERGY_RULE_FIELDS)
    # ``energy_coverage_ticks`` is the downstream firms' input buffer in the
    # Config contract.  Energy producers use the ordinary finished-goods
    # inventory ratio (``phi``), exactly like the original energy grammar.
    output.energy_rules.household_need = (
        float(cfg.energy_hh_share)
        * float(cfg.w_firm0)
        / max(1.0e-12, float(cfg.p_efirm0))
    )
    energy_scale = _representative_entity_scale(
        cfg,
        int(output.energy_rules.producer_count),
        _REFERENCE_ENERGY_FIRMS_PER_PERSON,
    )
    output.energy_rules.initial_producer_cash *= energy_scale
    _assign(output.housing_policy, policy, HOUSING_POLICY_FIELDS)
    output.housing_policy.wealth_tax_rate = float(policy.tax_wealth_rate)
    _assign(output.housing_rules, cfg, HOUSING_RULE_FIELDS)
    builder_scale = _representative_entity_scale(
        cfg,
        int(output.housing_rules.builder_count),
        _REFERENCE_BUILDERS_PER_PERSON,
    )
    output.housing_rules.initial_builder_cash_buffer *= builder_scale
    output.housing_rules.builder_demand_seed *= builder_scale
    if cfg.bank_enabled:
        person_count = int(cfg.demographics_population)
        household_count = (
            math.ceil(person_count / population.population.target_household_size)
            if person_count > 0
            else int(monetary.real_economy.households)
        )
        real_rules = monetary.real_economy.rules
        private_opening_money = (
            household_count * float(real_rules.initial_household_money)
            + int(monetary.real_economy.consumption_firms)
            * float(real_rules.initial_firm_money)
            + int(monetary.real_economy.capital_firms)
            * float(real_rules.initial_capital_firm_money)
            + int(output.energy_rules.producer_count)
            * float(output.energy_rules.initial_producer_cash)
            + int(output.housing_rules.builder_count)
            * float(output.housing_rules.initial_builder_cash_buffer)
        )
        total_bank_capital = (
            float(cfg.d_bank0)
            + float(cfg.bank_capital_frac) * private_opening_money
        )
        monetary.rules.opening_capital_per_bank = (
            total_bank_capital / max(1, int(monetary.rules.bank_count))
        )
        financial.monetary_economy = monetary
        population.financial_economy = financial
        output.domestic_economy = population
    return output, external


def _external_policy(native: Any, value: ExternalPolicy) -> Any:
    output = native.ExternalPolicy()
    for name in (
        "tariff", "import_quota", "export_subsidy", "capital_control",
        "external_interest_settlement_fraction", "immigration_cap",
        "emigration_cap", "remittance_tax", "outward_remittance_tax",
        "guest_worker_return", "peg_anchor", "peg_reserve_scale",
    ):
        field_value = getattr(value, name)
        if field_value is not None:
            setattr(output, name, field_value)
    output.sanctions_imposed_on = sorted(value.sanctions_imposed_on)
    output.fx_regime = (
        native.FxRegime.PEG if value.fx_regime == "peg" else native.FxRegime.FLOAT
    )
    return output


def _shock_id(label: str, ordinal: int) -> int:
    digest = hashlib.sha256(f"{label}:{ordinal}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") or 1


def _native_shocks(
    native: Any, spec: NewGameSpec, economy_count: int
) -> list[Any]:
    tape = spec.shock_tape()
    if tape is None:
        return []
    output: list[Any] = []
    sector_values = {
        "consumption": native.ShockSector.CONSUMPTION,
        "necessity": native.ShockSector.CONSUMPTION,
        "luxury": native.ShockSector.CONSUMPTION,
        "capital": native.ShockSector.CAPITAL,
        "energy": native.ShockSector.ENERGY,
        "housing": native.ShockSector.HOUSING,
        "public": native.ShockSector.PUBLIC,
    }
    kind_values = {
        "productivity": native.ShockKind.PRODUCTIVITY,
        "labor_availability": native.ShockKind.LABOR_AVAILABILITY,
        "energy_capacity": native.ShockKind.ENERGY_CAPACITY,
        "household_demand": native.ShockKind.HOUSEHOLD_DEMAND,
        "import_capacity": native.ShockKind.IMPORT_CAPACITY,
        "export_capacity": native.ShockKind.EXPORT_CAPACITY,
        "credit_supply": native.ShockKind.CREDIT_SUPPLY,
        "capital_destruction": native.ShockKind.CAPITAL_DESTRUCTION,
    }
    ordinal = 0
    for shock in tape.specs:
        economies: Iterable[int | None] = (
            range(economy_count)
            if shock.target.economy_ids is None
            else shock.target.economy_ids
        )
        sectors: Iterable[str | None] = shock.target.sectors or (None,)
        for economy_id in economies:
            for sector in sectors:
                row = native.ShockSpec()
                row.id = _shock_id(shock.shock_id, ordinal)
                row.kind = kind_values[shock.kind]
                row.economy_id = economy_id
                row.start_tick = shock.start_tick
                row.announcement_tick = shock.announcement_tick
                row.duration = (
                    shock.duration_ticks
                    if shock.duration_ticks is not None
                    else max(1, (spec.duration_ticks or 100_000) - shock.start_tick)
                )
                row.magnitude = shock.magnitude
                row.shape = native.ShockShape.STEP
                row.ramp_in_ticks = shock.ramp_in_ticks
                row.ramp_out_ticks = shock.ramp_out_ticks
                if sector is not None:
                    row.sector = sector_values[sector]
                output.append(row)
                ordinal += 1
    return output


def build_world_spec(spec: NewGameSpec | Mapping[str, Any]) -> Any:
    """Build the complete native world contract for one desktop new game."""
    if not isinstance(spec, NewGameSpec):
        spec = NewGameSpec.from_mapping(spec)
    native = _load_native()
    world = native.M9WorldSpec()
    economies = []
    external = []
    for economy_id, cfg in enumerate(spec.configs()):
        economy, policy = _m8_spec(native, spec, cfg, economy_id)
        economies.append(economy)
        external.append(_external_policy(native, policy))
    world.economies = economies
    world.external_policies = external
    rules = world.rules
    rules.trade = bool(spec.world["trade"])
    rules.capital = bool(spec.world["capital"])
    rules.migration = bool(spec.world["migration"])
    rules.fx_adjustment = float(spec.world["fx_lambda"])
    rules.fx_friction = float(spec.world["fx_friction"])
    rules.fx_spread = float(spec.world.get("fx_spread", 0.0))
    rules.fx_loss_mutualization = bool(
        spec.world.get("fx_loss_mutualization", False)
    )
    rules.fx_trade_cap = float(spec.world["fx_trade_cap"])
    rules.capital_mobility = float(spec.world["capital_mobility"])
    rules.capital_adjustment = float(spec.world["capital_adjust"])
    rules.migration_rate = float(spec.world["migration_rate"])
    rules.migration_max_share = float(spec.world["migration_max_share"])
    rules.remittance_share = float(spec.world["remittance_share"])
    rules.wage_smoothing = float(spec.world["wage_smoothing"])
    rules.initial_peg_reserves = float(spec.world["peg_reserves0"])
    rules.periods_per_year = 365.0
    world.rules = rules
    world.shocks = _native_shocks(native, spec, len(economies))
    return world


def build_native_new_game_spec(
    spec: NewGameSpec | Mapping[str, Any],
) -> Any:
    """Parse the product new-game contract without constructing live state."""
    if not isinstance(spec, NewGameSpec):
        spec = NewGameSpec.from_mapping(spec)
    native = _load_native()
    return native.native_spec_from_new_game(
        json.dumps(spec.to_dict(), sort_keys=True, separators=(",", ":"))
    )


@dataclass(frozen=True, slots=True)
class NativeConfigRunSpec:
    """Minimal facade metadata for non-desktop native sessions."""

    player_country: int = 0

    @property
    def initial_policy_overrides(self) -> Mapping[str, Any]:
        return {}


def build_world_spec_from_configs(
    configs: Iterable[Config],
    *,
    world_overrides: Mapping[str, Any] | None = None,
) -> Any:
    """Translate explicit immutable Config seeds into one native World.

    This is the controller/RL construction path.  It deliberately bypasses
    desktop profiles while still using the same audited M4-M8 contract mapping.
    The resulting native World is the sole economic state owner.
    """
    checked = tuple(configs)
    if not checked or not all(isinstance(item, Config) for item in checked):
        raise TypeError("configs must contain one or more Config values")
    native = _load_native()
    facade_spec = NativeConfigRunSpec()
    world = native.M9WorldSpec()
    economies = []
    external = []
    for economy_id, cfg in enumerate(checked):
        economy, policy = _m8_spec(
            native, facade_spec, cfg, economy_id  # type: ignore[arg-type]
        )
        economies.append(economy)
        external.append(_external_policy(native, policy))
    world.economies = economies
    world.external_policies = external
    rules = world.rules
    rules.periods_per_year = 365.0
    if world_overrides is not None:
        allowed = {
            "trade",
            "capital",
            "migration",
            "fx_lambda",
            "fx_friction",
            "fx_spread",
            "fx_loss_mutualization",
            "fx_trade_cap",
            "capital_mobility",
            "capital_adjust",
            "migration_rate",
            "migration_max_share",
            "remittance_share",
            "wage_smoothing",
            "peg_reserves0",
        }
        unknown = set(world_overrides) - allowed
        if unknown:
            raise ValueError(
                "unknown native World Config fields: "
                + ", ".join(sorted(unknown))
            )
        world_rule_fields = {
            "trade": "trade",
            "capital": "capital",
            "migration": "migration",
            "fx_lambda": "fx_adjustment",
            "fx_friction": "fx_friction",
            "fx_spread": "fx_spread",
            "fx_loss_mutualization": "fx_loss_mutualization",
            "fx_trade_cap": "fx_trade_cap",
            "capital_mobility": "capital_mobility",
            "capital_adjust": "capital_adjustment",
            "migration_rate": "migration_rate",
            "migration_max_share": "migration_max_share",
            "remittance_share": "remittance_share",
            "wage_smoothing": "wage_smoothing",
            "peg_reserves0": "initial_peg_reserves",
        }
        for source, target in world_rule_fields.items():
            if source in world_overrides:
                setattr(rules, target, world_overrides[source])
    world.rules = rules
    return world


def _controller_envelope(native: Any, world: Any) -> Any:
    payload = json.dumps(
        {
            "phase": "boundary_start",
            "schema_version": 1,
            "tick": world.tick,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope = native.CanonicalControllerEnvelope()
    envelope.boundary = world.tick
    envelope.policy_generation = world.policy_generation
    envelope.canonical_payload = payload
    envelope.seal()
    return envelope


@dataclass
class NativePreparedBoundary:
    """Exclusive native boundary lease plus its immutable controller predecessor."""

    lease: Any
    previous_envelope: Any
    operation_id: str
    canonical_actions: tuple[dict[str, Any], ...]


@dataclass
class NativeSimulationSession:
    """Product-level owner of a native M9 world and M10 control bridge."""

    spec: Any
    bridge: Any
    worker_count: int = 8
    restored_controller_archive: bytes = b""

    @classmethod
    def create(
        cls,
        spec: NewGameSpec | Mapping[str, Any],
        *,
        worker_count: int = 8,
        history_capacity_frames: int = 2048,
    ) -> "NativeSimulationSession":
        if not isinstance(spec, NewGameSpec):
            spec = NewGameSpec.from_mapping(spec)
        if worker_count < 1:
            raise ValueError("worker_count must be positive")
        native = _load_native()
        # Product NewGameSpec construction is owned by the same native parser
        # used by the Godot desktop worker.  Keeping a second Python mapping
        # here allowed omitted defaults (notably the exogenous/stochastic TFP
        # regime) to diverge silently from the actual game.
        document = json.dumps(
            spec.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        world = native.native_world_from_new_game(document)
        engine = native.NativeWorldEngineSession.create(
            world, history_capacity_frames
        )
        bridge = native.HybridControlledBridge.create(
            engine, _controller_envelope(native, world)
        )
        return cls(spec=spec, bridge=bridge, worker_count=worker_count)

    @classmethod
    def create_from_configs(
        cls,
        configs: Iterable[Config],
        *,
        player_country: int = 0,
        worker_count: int = 8,
        history_capacity_frames: int = 2048,
        world_overrides: Mapping[str, Any] | None = None,
    ) -> "NativeSimulationSession":
        checked = tuple(configs)
        if not 0 <= player_country < len(checked):
            raise ValueError("player_country is outside the Config sequence")
        if worker_count < 1:
            raise ValueError("worker_count must be positive")
        native = _load_native()
        world = native.WorldSession.create(
            build_world_spec_from_configs(
                checked, world_overrides=world_overrides
            )
        )
        engine = native.NativeWorldEngineSession.create(
            world, history_capacity_frames
        )
        bridge = native.HybridControlledBridge.create(
            engine, _controller_envelope(native, world)
        )
        return cls(
            spec=NativeConfigRunSpec(player_country),
            bridge=bridge,
            worker_count=worker_count,
        )

    @classmethod
    def create_from_native_spec(
        cls,
        native_spec: Any,
        *,
        player_country: int = 0,
        worker_count: int = 8,
        history_capacity_frames: int = 2048,
    ) -> "NativeSimulationSession":
        """Create a session from an already-audited native experiment spec."""
        if worker_count < 1:
            raise ValueError("worker_count must be positive")
        native = _load_native()
        world = native.WorldSession.create(native_spec)
        engine = native.NativeWorldEngineSession.create(
            world, history_capacity_frames
        )
        bridge = native.HybridControlledBridge.create(
            engine, _controller_envelope(native, world)
        )
        return cls(
            spec=NativeConfigRunSpec(player_country),
            bridge=bridge,
            worker_count=worker_count,
        )

    @property
    def tick(self) -> int:
        return int(self.bridge.tick)

    def public_metrics(self) -> dict[str, Any]:
        return dict(self.bridge.public_metrics())

    def maintained_metrics(self) -> dict[str, Any]:
        """Return every committed M4-M9 source plus public derived series."""
        return dict(self.bridge.maintained_metrics())

    def native_snapshot(self) -> dict[str, Any]:
        return dict(self.bridge.native_snapshot())

    def history_page(
        self, first_sequence: int, maximum_frames: int = 256
    ) -> dict[str, Any]:
        return dict(self.bridge.history_page(first_sequence, maximum_frames))

    def maintained_history_page(
        self, first_sequence: int, maximum_frames: int = 256
    ) -> dict[str, Any]:
        return dict(self.bridge.maintained_history_page(
            first_sequence, maximum_frames,
        ))

    def history_bounds(self) -> dict[str, int]:
        return {
            key: int(value)
            for key, value in dict(self.bridge.history_bounds()).items()
        }

    def memory_usage(self) -> dict[str, int]:
        """Return capacity-accounted native World memory by subsystem."""
        return {
            key: int(value)
            for key, value in dict(self.bridge.memory_usage()).items()
        }

    def storage_counts(self) -> dict[str, int]:
        """Return logical row counts for long-lived native stores."""
        return {
            key: int(value)
            for key, value in dict(self.bridge.storage_counts()).items()
        }

    def clone(self) -> "NativeSimulationSession":
        """Clone the committed native composite without Python world state."""
        return type(self)(
            spec=self.spec,
            bridge=self.bridge.clone(),
            worker_count=self.worker_count,
        )

    def probe_page(
        self, kind: str, *, economy_id: int = 0, after_id: int = 0,
        maximum_rows: int = 256,
    ) -> dict[str, Any]:
        methods = {
            "households": self.bridge.probe_households,
            "firms": self.bridge.probe_firms,
            "banks": self.bridge.probe_banks,
            "persons": self.bridge.probe_persons,
            "jobs": self.bridge.probe_jobs,
            "dwellings": self.bridge.probe_dwellings,
            "equities": self.bridge.probe_equities,
            "security_positions":
                self.bridge.probe_security_positions,
        }
        try:
            method = methods[kind]
        except KeyError as exc:
            raise ValueError(f"unknown native probe kind {kind!r}") from exc
        return dict(method(economy_id, after_id, maximum_rows))

    def probe_economy_diagnostics(
        self, economy_id: int = 0,
    ) -> dict[str, Any]:
        return dict(self.bridge.probe_economy_diagnostics(economy_id))

    def shock_bulletins(
        self, economy_id: int, as_of_boundary: int,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            dict(row) for row in self.bridge.probe_shock_bulletins(
                economy_id, as_of_boundary,
            )
        )

    def policy_values(self, economy_id: int = 0) -> dict[str, Any]:
        """Return all 102 current policy values through the generated bridge."""
        if not 0 <= economy_id < int(self.bridge.economy_count):
            raise IndexError(f"economy_id {economy_id} out of range")
        native = _load_native()
        domestic = self.bridge.domestic_policy(economy_id)
        external = self.bridge.external_policies()[economy_id]
        return self._policy_values_from_bundle(native, domestic, external)

    @staticmethod
    def _policy_values_from_bundle(
        native: Any, domestic: Any, external: Any,
    ) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for name, lever in REGISTRY.items():
            if lever.scope == "external":
                if name == "fx_regime":
                    output[name] = (
                        "peg"
                        if external.fx_regime == native.FxRegime.PEG
                        else "float"
                    )
                elif name == "sanctions_imposed_on":
                    output[name] = sorted(external.sanctions_imposed_on)
                else:
                    output[name] = getattr(external, name)
                continue
            if name == "monetary_regime":
                regime = domestic.fiscal_monetary.monetary_regime
                output[name] = {
                    native.MonetaryRegime.EXOGENOUS: "exogenous",
                    native.MonetaryRegime.TAYLOR: "taylor",
                    native.MonetaryRegime.MANUAL: "manual",
                }[regime]
            elif name == "energy_rationing":
                output[name] = {
                    native.EnergyRationing.MARKET: "market",
                    native.EnergyRationing.PROPORTIONAL: "proportional",
                    native.EnergyRationing.HOUSEHOLD_FIRST: "household_first",
                    native.EnergyRationing.INDUSTRY_FIRST: "industry_first",
                }[domestic.energy.rationing]
            elif name == "bank_resolution_fund":
                output[name] = domestic.financial.bank_resolution_fund
            else:
                section_name, field_name = DOMESTIC_POLICY_BINDINGS[name]
                output[name] = getattr(
                    getattr(domestic, section_name), field_name,
                )
        return output

    def projected_policy_values(
        self, actions: Iterable[Mapping[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        """Return the complete policy view after a validated, non-mutating batch."""
        native = _load_native()
        batch, _canonical = self._policy_batch(actions)
        self.bridge.validate_policy_batch(batch)
        return tuple(
            self._policy_values_from_bundle(
                native, batch.domestic[economy_id],
                batch.external[economy_id],
            )
            for economy_id in range(int(self.bridge.economy_count))
        )

    @staticmethod
    def _set_domestic_lever(
        native: Any, policy: Any, lever_name: str, value: Any
    ) -> None:
        if lever_name == "monetary_regime":
            section = policy.fiscal_monetary
            section.monetary_regime = {
                "exogenous": native.MonetaryRegime.EXOGENOUS,
                "taylor": native.MonetaryRegime.TAYLOR,
                "manual": native.MonetaryRegime.MANUAL,
            }[value]
            if value != "manual":
                section.manual_policy_rate = None
            policy.fiscal_monetary = section
            return
        if lever_name == "energy_rationing":
            section = policy.energy
            section.rationing = {
                "market": native.EnergyRationing.MARKET,
                "proportional": native.EnergyRationing.PROPORTIONAL,
                "household_first": native.EnergyRationing.HOUSEHOLD_FIRST,
                "industry_first": native.EnergyRationing.INDUSTRY_FIRST,
            }[value]
            policy.energy = section
            return
        if lever_name == "bank_resolution_fund":
            monetary = policy.fiscal_monetary
            monetary.state_resolution_backstop = bool(value)
            policy.fiscal_monetary = monetary
            financial = policy.financial
            financial.bank_resolution_fund = bool(value)
            policy.financial = financial
            return
        try:
            section_name, field_name = DOMESTIC_POLICY_BINDINGS[lever_name]
        except KeyError as exc:
            raise ValueError(
                f"native policy bridge does not implement {lever_name!r}"
            ) from exc
        section = getattr(policy, section_name)
        setattr(section, field_name, value)
        setattr(policy, section_name, section)

    @staticmethod
    def _set_external_lever(
        native: Any, policy: Any, lever_name: str, value: Any
    ) -> None:
        if lever_name == "fx_regime":
            policy.fx_regime = (
                native.FxRegime.PEG if value == "peg" else native.FxRegime.FLOAT
            )
            if value != "peg":
                policy.peg_anchor = None
            return
        if lever_name == "sanctions_imposed_on":
            policy.sanctions_imposed_on = sorted(value)
            return
        setattr(policy, lever_name, value)

    def _policy_batch(
        self, actions: Iterable[Mapping[str, Any]]
    ) -> tuple[Any, list[dict[str, Any]]]:
        native = _load_native()
        domestic = [
            self.bridge.domestic_policy(index)
            for index in range(self.bridge.economy_count)
        ]
        external = list(self.bridge.external_policies())
        canonical_actions: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise TypeError(f"actions[{index}] must be an object")
            if set(action) not in ({"lever", "value"}, {"economy_id", "lever", "value"}):
                raise ValueError(
                    f"actions[{index}] must contain lever/value and optional economy_id"
                )
            economy_id = action.get("economy_id", self.spec.player_country)
            if isinstance(economy_id, bool) or not isinstance(economy_id, int):
                raise TypeError(f"actions[{index}].economy_id must be an integer")
            if not 0 <= economy_id < len(domestic):
                raise ValueError(f"actions[{index}] targets an unknown economy")
            lever_name = action["lever"]
            if not isinstance(lever_name, str) or lever_name not in REGISTRY:
                raise ValueError(f"actions[{index}] names an unknown policy lever")
            key = (economy_id, lever_name)
            if key in seen:
                raise ValueError(f"actions contain duplicate policy lever {key!r}")
            seen.add(key)
            if lever_name not in NATIVE_POLICY_LEVERS:
                raise ValueError(
                    f"native policy bridge does not implement {lever_name!r}"
                )
            lever = REGISTRY[lever_name]
            value = action["value"]
            engine_value = (
                frozenset(value)
                if isinstance(lever.validation, EconomySet)
                and isinstance(value, (list, tuple))
                else value
            )
            error = lever.validation.check(None, engine_value)
            if error is not None:
                raise ValueError(f"{lever_name}: {error}")
            if lever.scope == "external":
                self._set_external_lever(
                    native, external[economy_id], lever_name, engine_value
                )
            else:
                self._set_domestic_lever(
                    native, domestic[economy_id], lever_name, engine_value
                )
            canonical_actions.append({
                "economy_id": economy_id,
                "lever": lever_name,
                "value": (
                    sorted(engine_value)
                    if isinstance(engine_value, frozenset)
                    else engine_value
                ),
            })
        batch = native.WorldPolicyBatch()
        batch.expected_tick = self.tick
        batch.expected_generation = int(self.bridge.policy_generation)
        batch.domestic = domestic
        batch.external = external
        return batch, canonical_actions

    def validate_actions(
        self, actions: Iterable[Mapping[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        """Validate and canonicalize an atomic policy batch without mutation."""
        _batch, canonical = self._policy_batch(actions)
        return tuple(canonical)

    def sync_controller_envelope(
        self,
        payload: bytes,
        *,
        event_sequence: int,
        release_cursor: int,
        decision_versions: Iterable[int],
        effective_versions: Iterable[int],
        operation_id: str,
    ) -> str:
        """Atomically publish a complete neutral controller cache root."""
        if not isinstance(payload, bytes):
            raise TypeError("controller payload must be bytes")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("controller operation_id must be non-empty")
        for name, value in (
            ("event_sequence", event_sequence),
            ("release_cursor", release_cursor),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        decisions = list(decision_versions)
        effective = list(effective_versions)
        if len(decisions) != len(effective):
            raise ValueError("controller policy version vectors differ in length")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (*decisions, *effective)
        ):
            raise ValueError("controller policy versions must be non-negative integers")

        previous = self.bridge.controller_envelope
        if (
            bytes(previous.canonical_payload) == payload
            and int(previous.event_sequence) == event_sequence
            and int(previous.release_cursor) == release_cursor
            and list(previous.decision_versions) == decisions
            and list(previous.effective_versions) == effective
        ):
            return str(previous.hash)

        native = _load_native()
        envelope = native.CanonicalControllerEnvelope()
        envelope.schema_version = previous.schema_version
        envelope.boundary = self.tick
        envelope.policy_generation = int(self.bridge.policy_generation)
        envelope.event_sequence = event_sequence
        envelope.release_cursor = release_cursor
        envelope.decision_versions = decisions
        envelope.effective_versions = effective
        envelope.canonical_payload = payload
        envelope.seal()
        transition = native.ControllerEnvelopeTransition()
        transition.operation_id = operation_id
        transition.expected_prior_hash = previous.hash
        transition.next = envelope
        receipt = dict(self.bridge.update_controller(transition))
        self.bridge.acknowledge_receipt(operation_id)
        return str(receipt["result_hash"])

    def prepare_boundary(
        self,
        *,
        actions: Iterable[Mapping[str, Any]] = (),
        advance_ticks: int = 1,
        fault_point: str = "none",
    ) -> NativePreparedBoundary:
        """Prepare one atomic native batch while keeping the public state unchanged."""
        if (
            isinstance(advance_ticks, bool)
            or not isinstance(advance_ticks, int)
            or advance_ticks < 1
        ):
            raise ValueError("advance_ticks must be a positive integer")
        native = _load_native()
        fault_points = {
            "none": native.M10FaultPoint.NONE,
            "prepare_after_policy":
                native.M10FaultPoint.PREPARE_AFTER_POLICY,
            "prepare_after_advance":
                native.M10FaultPoint.PREPARE_AFTER_ADVANCE,
            "prepare_after_metrics":
                native.M10FaultPoint.PREPARE_AFTER_METRICS,
            "commit_before_swap":
                native.M10FaultPoint.COMMIT_BEFORE_SWAP,
        }
        try:
            native_fault = fault_points[fault_point]
        except KeyError as exc:
            raise ValueError(
                f"unknown native M10 fault point {fault_point!r}"
            ) from exc
        policies, canonical_actions = self._policy_batch(actions)
        previous = self.bridge.controller_envelope
        operation_id = (
            f"native-boundary:{self.tick}:"
            f"{int(previous.event_sequence) + 1}"
        )
        sealed = native.SealedControlBatch()
        sealed.operation_id = operation_id
        sealed.expected_controller_hash = previous.hash
        sealed.policies = policies
        sealed.advance_ticks = advance_ticks
        sealed.worker_count = self.worker_count
        sealed.fault_point = native_fault
        lease = self.bridge.prepare_boundary(sealed)
        return NativePreparedBoundary(
            lease=lease,
            previous_envelope=previous,
            operation_id=operation_id,
            canonical_actions=tuple(canonical_actions),
        )

    def commit_prepared_boundary(
        self,
        prepared: NativePreparedBoundary,
        *,
        payload: bytes,
        event_sequence: int,
        release_cursor: int,
        decision_versions: Iterable[int],
        effective_versions: Iterable[int],
    ) -> dict[str, Any]:
        """Commit a prepared economy together with the complete controller root."""
        if not prepared.lease.active:
            raise RuntimeError("native prepared boundary lease is inactive")
        native = _load_native()
        decisions = list(decision_versions)
        effective = list(effective_versions)
        if len(decisions) != len(effective):
            raise ValueError("controller policy version vectors differ in length")
        envelope = native.CanonicalControllerEnvelope()
        envelope.schema_version = prepared.previous_envelope.schema_version
        envelope.boundary = int(prepared.lease.preview["next_tick"])
        envelope.policy_generation = int(
            prepared.lease.preview["policy_generation"]
        )
        envelope.event_sequence = int(event_sequence)
        envelope.release_cursor = int(release_cursor)
        envelope.decision_versions = decisions
        envelope.effective_versions = effective
        envelope.canonical_payload = payload
        envelope.seal()
        return dict(self.bridge.commit_boundary(prepared.lease, envelope))

    def abort_prepared_boundary(
        self, prepared: NativePreparedBoundary,
    ) -> None:
        if prepared.lease.active:
            self.bridge.abort_boundary(prepared.lease)

    def advance(
        self,
        ticks: int = 1,
        *,
        actions: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Commit one or more native day boundaries atomically, action first."""
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1:
            raise ValueError("ticks must be a positive integer")
        prepared = self.prepare_boundary(
            actions=tuple(actions), advance_ticks=ticks,
        )
        try:
            previous = prepared.previous_envelope
            # The authoritative Python controller envelope is republished
            # after the completed boundary.  The economic commit must not
            # invent controller/release sequence positions that the final
            # neutral state could then be unable to decrease.
            payload = json.dumps(
                {
                    "actions": prepared.canonical_actions,
                    "operation_id": prepared.operation_id,
                    "phase": "boundary_start",
                    "schema_version": 1,
                    "tick": int(prepared.lease.preview["next_tick"]),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            return self.commit_prepared_boundary(
                prepared,
                payload=payload,
                event_sequence=int(previous.event_sequence),
                release_cursor=int(previous.release_cursor),
                decision_versions=list(previous.decision_versions),
                effective_versions=list(previous.effective_versions),
            )
        except Exception:
            self.abort_prepared_boundary(prepared)
            raise

    def checkpoint(
        self, objective_envelope: bytes = b"{}", *,
        controller_archive: bytes = b"",
    ) -> bytes:
        return bytes(self.bridge.checkpoint(
            objective_envelope, controller_archive,
        ))

    @classmethod
    def restore(
        cls,
        spec: NewGameSpec | NativeConfigRunSpec | Mapping[str, Any],
        checkpoint: bytes,
        *,
        worker_count: int = 8,
    ) -> tuple["NativeSimulationSession", bytes]:
        if isinstance(spec, Mapping):
            spec = NewGameSpec.from_mapping(spec)
        if not isinstance(spec, (NewGameSpec, NativeConfigRunSpec)):
            raise TypeError("spec must be a NewGameSpec or NativeConfigRunSpec")
        native = _load_native()
        restored = native.HybridControlledBridge.restore_checkpoint(checkpoint)
        session = cls(
            spec=spec,
            bridge=restored["bridge"],
            worker_count=worker_count,
            restored_controller_archive=bytes(
                restored["controller_archive"],
            ),
        )
        return session, bytes(restored["objective_envelope"])
