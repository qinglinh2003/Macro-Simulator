"""Typed configuration views used during the gradual config split."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BankingConfig:
    bank_enabled: bool
    n_banks: int
    seed: int
    bank_leverage_mean: float
    bank_leverage_disp: float
    bank_assignment: str
    bank_capital_constraint: bool
    bank_migrate_on_failure: bool
    bank_target_capital_ratio: float
    bank_exposure_limit: float
    bank_rate_competition: bool
    bank_spread_disp: float
    bank_search_m: int
    interbank: bool
    interbank_rate_base: float
    interbank_tightness: float
    reserve_floor_frac: float
    deposit_rate_disp: float
    deposit_search_m: int
    bank_equity: bool
    bank_equity_lambda: float
    bank_equity_trading: bool
    bank_theta_equity: float
    bank_dynamics: bool
    bank_min_capital: float
    bank_entry_beta: float
    bank_entry_max: int
    bank_runs: bool
    run_sensitivity: float
    run_health_ref: float
    run_market_weight: float
    run_fear_persistence: float
    lolr: bool
    bank_resolution_fund: bool
    bonds: bool
    rho: float
    genesis_founder_pool: float
    w_fundamental: float
    w_chartist: float
    portfolio_adjust: float
    lambda_p: float
    trend_lambda: float


@dataclass(frozen=True)
class CentralBankConfig:
    central_bank: bool
    r_interest: float
    infl_ema_lambda: float
    u_natural: float
    r_neutral: float
    r_max: float
    omo: bool
    bonds: bool
    interbank: bool
    omo_reserve_target: float
    omo_drain_frac: float
    omo_index_deposits: bool
    cb_log_inflation: bool
    reserve_floor_frac: float


@dataclass(frozen=True)
class CapitalGoodsConfig:
    capital_enabled: bool
    government: bool
    gov_investment_share: float


@dataclass(frozen=True)
class GoodsConfig:
    government: bool
    a: float


@dataclass(frozen=True)
class SettlementConfig:
    government: bool
    pro_rata_dividends: bool
    per_firm_equity: bool
    gov_investment_share: float
    public_capital_depreciation: float
    jg_productivity: float


@dataclass(frozen=True)
class PlanningConfig:
    theta_wage: float
    inventory_gap_close: float
    delta: float
    theta_price: float
    lambda_q: float
    q_invest_floor: float
    q_invest_cap: float
    k_replacement_floor: bool
    wealth_effect: float
    mpc_wealth_curvature: float
    d_household0: float
    demographic_lifecycle_consumption: bool
    lifecycle_alpha_income: float
    lifecycle_alpha_wealth_draw: float
    housing_wealth_effect: float
    alpha2: float


@dataclass(frozen=True)
class DemographicsConfig:
    demographics_enabled: bool
    demographics_population: int
    demographic_lifecycle_consumption: bool
    lifecycle_alpha_income: float
    lifecycle_alpha_wealth_draw: float
    demographic_marriage_enabled: bool
    demographic_divorce_enabled: bool
    demographic_marriage_market_interval_days: int
    demographic_annual_marriage_rate_peak: float
    demographic_annual_divorce_rate_base: float
    demographic_adult_leaving_home_enabled: bool
    demographic_leave_home_min_age: int
    demographic_leave_home_peak_end_age: int
    demographic_annual_leave_rate_peak: float
    demographic_annual_leave_rate_late: float
    demo_feedback_burnin_years: int
    demo_signal_halflife_years: float
    fertility_income_elasticity: float
    fertility_mult_lo: float
    fertility_mult_hi: float
    mortality_income_elasticity: float
    mortality_mult_lo: float
    mortality_mult_hi: float


@dataclass(frozen=True)
class SecuritiesConfig:
    bonds: bool
    government: bool
    bond_maturity: int
    bond_coupon: float
    bond_finance_frac: float
    p_firm0: float
    d_household0: float
    bond_theta: float
    bank_bond_appetite: float
    interbank: bool
    reserve_floor_frac: float
    bank_bond_duration_limit: float


@dataclass(frozen=True)
class FirmDemographicsConfig:
    firm_dynamics: bool
    bankrupt_persist: int
    entry_hurdle: float
    shell_exit_ticks: int
    real_entry_signal: bool
    entry_beta: float
    entry_max: int
    index_startup: bool
    startup_deposits: float
    p_firm0: float
    startup_capital: float
    gibrat_growth: bool
    gibrat_sigma: float
    gibrat_entry_a0: float
    per_firm_equity: bool
    shares_per_firm: float


@dataclass(frozen=True)
class CreditConfig:
    bank_enabled: bool
    household_credit: bool
    hh_subsistence: float
    amort: float
    margin_credit: bool
    hh_amort: float
    bank_target_capital_ratio: float
    interbank: bool
    deposit_rate_disp: float
    bank_equity: bool
    interest_by_deposits: bool


@dataclass(frozen=True)
class EquityConfig:
    seed: int
    per_firm_equity: bool
    shares_per_firm: float
    watchlist_size: int
    founder_owned_genesis: bool
    genesis_founder_pool: float
    lambda_d: float
    lambda_p: float
    trend_lambda: float
    equity_ema_lambda: float
    resid_income_lambda: float
    q_invest_smooth: float
    w_fundamental: float
    w_chartist: float
    margin_credit: bool
    theta_equity: float
    portfolio_adjust: float
    equity_finance: bool
    lambda_issue: float
    household_bankruptcy: bool
