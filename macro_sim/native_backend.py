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
import sys
from typing import Any, Iterable, Mapping

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
    "demand_adjustment": "lambda_d",
    "income_adjustment": "lambda_y",
    "inventory_ratio": "phi",
    "inventory_gap_close": "inventory_gap_close",
    "markup_adjustment": "eta",
    "markup_minimum": "mu_min",
    "markup_maximum": "mu_max",
    "wage_shortage_adjustment": "omega",
    "wage_downward_drift": "delta",
    "wage_calvo_probability": "theta_wage",
    "price_calvo_probability": "theta_price",
    "income_propensity": "alpha1",
    "wealth_propensity": "alpha2",
    "investment_adjustment": "lambda_I",
    "capital_depreciation": "delta_K",
    "annual_tfp_growth": "tfp_drift_rate",
    "profit_tax_rate": "tax_profit_rate",
    "income_tax_rate": "tax_income_rate",
    "consumption_tax_rate": "tax_consumption_rate",
    "wealth_tax_rate": "tax_wealth_rate",
    "government_consumption_share": "gov_consumption_share",
    "government_deficit_target": "gov_deficit_target",
    "deficit_unemployment_reference": "deficit_u_ref",
    "deficit_unemployment_cap": "deficit_u_cap",
    "government_investment_share": "gov_investment_share",
    "unemployment_benefit_replacement": "benefit_replacement",
    "income_allowance": "income_allowance",
    "wealth_allowance": "wealth_allowance",
    "benefit_income_floor": "benefit_income_floor",
    "minimum_wage": "min_wage",
    "job_guarantee": "job_guarantee",
    "job_guarantee_wage_ratio": "jg_wage_ratio",
    "initial_household_money": "d_household0",
    "initial_firm_money": "d_cfirm0",
    "initial_bank_capital": "d_bank0",
    "initial_consumption_inventory": "inv_firm0",
    "initial_capital_inventory": "inv_kfirm0",
    "initial_consumption_capital": "K_firm0",
    "initial_price": "p_firm0",
    "initial_capital_price": "p_kfirm0",
    "initial_wage": "w_firm0",
    "initial_markup": "mu_firm0",
    "initial_expected_demand": "demand_e_firm0",
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
    "shares_per_firm": "shares_per_firm",
    "watchlist_size": "watchlist_size",
    "founder_owned_genesis": "founder_owned_genesis",
    "genesis_founder_pool": "genesis_founder_pool",
    "equity_price_adjustment": "lambda_p",
    "equity_trend_lambda": "trend_lambda",
    "residual_income_lambda": "resid_income_lambda",
    "q_smoothing": "lambda_q",
    "fundamental_weight": "w_fundamental",
    "chartist_weight": "w_chartist",
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
    "consumption_strata": "consumption_strata",
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
    "frictional_search": "labor_matching_friction",
    "search_intensity": "job_search_intensity",
    "relationship_wages": "labor_relationship_wages",
    "job_ladder": "labor_job_ladder",
    "ladder_search_intensity": "ladder_search_intensity",
    "ladder_premium": "ladder_premium",
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
    "producer_inventory_ratio": "energy_coverage_ticks",
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
    output.stochastic = bool(cfg.tfp_drift_sigma or cfg.gibrat_sigma)
    _assign(output.rules, cfg, M4_RULE_FIELDS)
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
    monetary.rules.assign_banks_by_size = cfg.bank_assignment == "size"

    financial = native.M6SimulationSpec()
    financial.monetary_economy = monetary
    _assign(financial.policy, policy, M6_POLICY_FIELDS)
    financial.policy.bank_bond_appetite = float(cfg.bank_bond_appetite)
    _assign(financial.rules, cfg, M6_RULE_FIELDS)

    population = native.M7SimulationSpec()
    population.financial_economy = financial
    population.policy.inheritance_tax_rate = float(cfg.tax_wealth_rate)
    _assign(population.policy, policy, M7_POLICY_FIELDS)
    _assign(population.rules, cfg, M7_RULE_FIELDS)
    vital = population.rules.vital_rates
    vital.total_fertility_rate = float(cfg.demographics_tfr)
    vital.makeham_a *= float(cfg.demographics_mortality_scale)
    vital.gompertz_b *= float(cfg.demographics_mortality_scale)
    population.rules.vital_rates = vital
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
    _assign(output.housing_policy, policy, HOUSING_POLICY_FIELDS)
    output.housing_policy.wealth_tax_rate = float(policy.tax_wealth_rate)
    _assign(output.housing_rules, cfg, HOUSING_RULE_FIELDS)
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
class NativeSimulationSession:
    """Product-level owner of a native M9 world and M10 control bridge."""

    spec: NewGameSpec
    bridge: Any
    worker_count: int = 8

    @classmethod
    def create(
        cls,
        spec: NewGameSpec | Mapping[str, Any],
        *,
        worker_count: int = 8,
        history_capacity_frames: int = 4096,
    ) -> "NativeSimulationSession":
        if not isinstance(spec, NewGameSpec):
            spec = NewGameSpec.from_mapping(spec)
        if worker_count < 1:
            raise ValueError("worker_count must be positive")
        native = _load_native()
        world = native.WorldSession.create(build_world_spec(spec))
        engine = native.NativeWorldEngineSession.create(
            world, history_capacity_frames
        )
        bridge = native.HybridControlledBridge.create(
            engine, _controller_envelope(native, world)
        )
        return cls(spec=spec, bridge=bridge, worker_count=worker_count)

    @property
    def tick(self) -> int:
        return int(self.bridge.tick)

    def public_metrics(self) -> dict[str, Any]:
        return dict(self.bridge.public_metrics())

    def native_snapshot(self) -> dict[str, Any]:
        return dict(self.bridge.native_snapshot())

    def history_page(
        self, first_sequence: int, maximum_frames: int = 256
    ) -> dict[str, Any]:
        return dict(self.bridge.history_page(first_sequence, maximum_frames))

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

    def advance(
        self,
        ticks: int = 1,
        *,
        actions: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Commit one or more native day boundaries atomically, action first."""
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1:
            raise ValueError("ticks must be a positive integer")
        native = _load_native()
        result: dict[str, Any] = {}
        pending_actions = tuple(actions)
        for offset in range(ticks):
            policies, canonical_actions = self._policy_batch(
                pending_actions if offset == 0 else ()
            )
            operation_id = (
                f"native-boundary:{self.tick}:"
                f"{int(self.bridge.controller_envelope.event_sequence) + 1}"
            )
            sealed = native.SealedControlBatch()
            sealed.operation_id = operation_id
            sealed.expected_controller_hash = self.bridge.controller_envelope.hash
            sealed.policies = policies
            sealed.advance_ticks = 1
            sealed.worker_count = self.worker_count
            lease = self.bridge.prepare_boundary(sealed)
            try:
                previous = self.bridge.controller_envelope
                envelope = native.CanonicalControllerEnvelope()
                envelope.schema_version = previous.schema_version
                envelope.boundary = int(lease.preview["next_tick"])
                envelope.policy_generation = int(
                    lease.preview["policy_generation"]
                )
                envelope.event_sequence = (
                    int(previous.event_sequence) + len(canonical_actions)
                )
                envelope.release_cursor = int(previous.release_cursor) + 1
                envelope.decision_versions = list(previous.decision_versions)
                envelope.effective_versions = list(previous.effective_versions)
                envelope.canonical_payload = json.dumps(
                    {
                        "actions": canonical_actions,
                        "operation_id": operation_id,
                        "phase": "boundary_start",
                        "schema_version": 1,
                        "tick": envelope.boundary,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                envelope.seal()
                result = dict(self.bridge.commit_boundary(lease, envelope))
            except Exception:
                if lease.active:
                    self.bridge.abort_boundary(lease)
                raise
        return result

    def checkpoint(self, objective_envelope: bytes = b"{}") -> bytes:
        return bytes(self.bridge.checkpoint(objective_envelope))

    @classmethod
    def restore(
        cls,
        spec: NewGameSpec | Mapping[str, Any],
        checkpoint: bytes,
        *,
        worker_count: int = 8,
    ) -> tuple["NativeSimulationSession", bytes]:
        if not isinstance(spec, NewGameSpec):
            spec = NewGameSpec.from_mapping(spec)
        native = _load_native()
        restored = native.HybridControlledBridge.restore_checkpoint(checkpoint)
        return (
            cls(spec=spec, bridge=restored["bridge"], worker_count=worker_count),
            bytes(restored["objective_envelope"]),
        )
