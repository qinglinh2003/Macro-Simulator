"""Treatment contracts for the immutable Config causality audit.

The registry deliberately covers the entire immutable surface.  A generated
suggestion is not an approved experiment: only ``screening_ready`` contracts
may enter the expensive native batch.  This prevents a generic percentage
change from being mistaken for an economically reviewed intervention.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Mapping

from macro_sim.diagnostics.config_causality import build_audit_inventory


DIRECTION_VALUES = frozenset(
    {
        "increase",
        "decrease",
        "nonzero",
        "ambiguous",
        "invariance",
        "washout",
    }
)


MODULE_PRIMARY_METRICS: Mapping[str, tuple[str, ...]] = {
    "production_and_technology": (
        "metric.economy.na.real_gdp_per_capita",
        "metric.economy.real_output",
        "metric.source.m4.aggregate_capital",
        "metric.source.m4.fixed_capital_formation_real",
        "metric.source.m4.capital_output_real",
        "metric.economy.labor_sector_capital_fte",
        "metric.economy.avg_wage",
        "metric.economy.price_index",
        "metric.economy.unemployment_rate",
        "metric.source.m6.primary_equity_raised",
        "metric.source.m4.tfp_index_consumption",
        "metric.source.m4.tfp_index_capital",
        "metric.source.m4.tfp_index_energy",
        "metric.source.m4.tfp_growth_consumption",
        "metric.source.m4.tfp_growth_capital",
        "metric.source.m4.tfp_growth_energy",
    ),
    "firms_and_industrial_dynamics": (
        "metric.economy.firm_count_c",
        "metric.economy.firm_count_k",
        "metric.source.m6.firm_births",
        "metric.source.m6.firm_exits",
        "metric.source.m6.firm_defaults",
        "metric.source.m6.sector_switches",
        "metric.source.m6.sector_retool_capital",
        "metric.source.m4.firm_profit",
        "metric.source.m4.dividends_paid",
        "metric.economy.avg_markup",
        "metric.economy.firm_size_gini_output",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "consumption_prices_and_expectations": (
        "metric.economy.na.household_consumption_real",
        "metric.analysis.goods_transaction_price_proxy",
        "metric.economy.inventory_to_sales",
        "metric.economy.avg_markup",
        "metric.economy.price_index",
        "metric.economy.inflation",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
        "metric.economy.poverty_rate",
    ),
    "labor_market": (
        "metric.source.m7.mean_person_efficiency",
        "metric.source.m7.person_efficiency_stddev",
        "metric.source.m7.participation_rate",
        "metric.source.m7.employed_fte",
        "metric.source.m7.out_of_labor_force",
        "metric.source.m7.hires",
        "metric.source.m7.separations",
        "metric.source.m7.churn_separations",
        "metric.source.m7.demand_layoff_separations",
        "metric.source.m7.cash_layoff_separations",
        "metric.source.m7.welfare_quits",
        "metric.source.m7.suspensions_flow",
        "metric.source.m7.recalls",
        "metric.source.m7.suspended",
        "metric.source.m7.second_job_hours",
        "metric.source.m7.job_to_job_moves",
        "metric.source.m7.nonsearching",
        "metric.source.m7.mean_hourly_wage",
        "metric.source.m7.underemployment_hours",
        "metric.source.m7.vacancies",
        "metric.economy.unemployment_rate",
        "metric.economy.underemployed_share",
        "metric.economy.avg_wage",
        "metric.economy.real_output",
    ),
    "demography_and_households": (
        "metric.source.m7.population",
        "metric.source.m7.mean_person_efficiency",
        "metric.source.m7.person_efficiency_stddev",
        "metric.source.m7.births",
        "metric.source.m7.deaths",
        "metric.source.m7.households_with_members",
        "metric.source.m7.mean_household_size",
        "metric.source.m7.working_age_share",
        "metric.source.m7.dependency_ratio",
        "metric.source.m7.active_unions",
        "metric.source.m7.mean_partner_age_gap",
        "metric.source.m7.mean_partner_log_efficiency_gap",
        "metric.source.m7.marriages",
        "metric.source.m7.divorces",
        "metric.source.m7.widowhoods",
        "metric.source.m7.leaving_home_events",
        "metric.economy.na.household_consumption_real",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "distribution_and_welfare": (
        "metric.source.m4.household_consumption_budget",
        "metric.source.m4.household_wealth_consumption_budget",
        "metric.source.m4.household_income_propensity_stddev",
        "metric.source.m4.household_wealth_propensity_stddev",
        "metric.source.m4.necessity_requested_quantity",
        "metric.source.m4.necessity_consumption",
        "metric.source.m4.luxury_consumption",
        "metric.source.m4.necessity_consumption_share",
        "metric.source.m4.necessity_firm_count",
        "metric.source.m4.luxury_firm_count",
        "metric.source.m7.family_transfer_total",
        "metric.source.m7.family_transfer_recipients",
        "metric.source.m7.family_exposed_households",
        "metric.source.m8.energy.deprivation_below_100_share",
        "metric.source.m8.energy.deprivation_below_60_share",
        "metric.source.m8.energy.deprivation_below_30_share",
        "metric.source.m8.energy.deprivation_destitute_share",
        "metric.source.m8.energy.deprivation_acute_stock",
        "metric.source.m8.energy.deprivation_chronic_stock",
        "metric.economy.poverty_rate",
        "metric.economy.income_gini",
        "metric.economy.hh_wealth_gini_incl_equity",
        "metric.economy.wage_p90_p10_ratio",
        "metric.economy.savings_rate",
        "metric.economy.welfare_log",
        "metric.economy.na.household_consumption_real",
    ),
    "banking_and_credit": (
        "metric.source.m5.new_credit",
        "metric.source.m5.firm_investment_target",
        "metric.source.m5.investment_user_cost_multiplier_mean",
        "metric.source.m5.household_debt_service_reserved",
        "metric.source.m5.firm_dscr_credit_shortfall",
        "metric.source.m5.principal_repaid",
        "metric.source.m5.loan_interest_paid",
        "metric.source.m5.household_interest_paid",
        "metric.source.m5.deposit_interest_paid",
        "metric.source.m5.deposit_interest_arrears",
        "metric.source.m5.total_loan_principal",
        "metric.source.m5.total_bank_capital",
        "metric.source.m5.total_reserves",
        "metric.source.m5.interbank_volume",
        "metric.source.m5.interbank_rate",
        "metric.source.m5.run_flight_volume",
        "metric.source.m5.realized_credit_losses",
        "metric.source.m5.realized_interbank_losses",
        "metric.source.m5.alive_banks",
        "metric.source.m5.bank_failures",
        "metric.source.m6.bank_births",
        "metric.economy.household_debt_total",
        "metric.economy.firm_debt_total",
        "metric.economy.credit_to_gdp",
        "metric.economy.income_gini",
        "metric.economy.na.household_consumption_real",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "government_and_public_sector": (
        "metric.source.m4.public_capital",
        "metric.source.m4.public_fixed_capital_formation",
        "metric.source.m4.job_guarantee_spending",
        "metric.source.m4.job_guarantee_labor",
        "metric.source.m4.job_guarantee_public_capital_formation",
        "metric.source.m4.job_guarantee_realized_productivity",
        "metric.source.m4.government_spending",
        "metric.source.m4.government_deficit",
        "metric.economy.na.real_gdp_per_capita",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
        "metric.economy.avg_wage",
        "metric.economy.price_index",
        "metric.economy.na.public_fixed_capital_formation_nominal",
        "metric.economy.na.government_consumption_real",
    ),
    "securities_and_capital_markets": (
        "metric.source.m6.bond_outstanding_face",
        "metric.source.m6.bond_market_value",
        "metric.source.m6.bond_issuance",
        "metric.source.m6.household_bond_market_value",
        "metric.source.m6.bank_bond_market_value",
        "metric.source.m6.firm_equity_market_cap",
        "metric.source.m6.bank_equity_market_cap",
        "metric.source.m6.household_firm_equity_market_value",
        "metric.source.m6.household_bank_equity_market_value",
        "metric.source.m6.firm_equity_turnover",
        "metric.source.m6.bank_equity_turnover",
        "metric.source.m6.firm_equity_fundamental_value",
        "metric.source.m6.bank_equity_fundamental_value",
        "metric.source.m6.primary_equity_raised",
        "metric.source.m6.margin_principal",
        "metric.source.m6.margin_originated",
        "metric.source.m6.margin_repaid",
        "metric.source.m6.mean_tobin_q_ema",
        "metric.source.m6.mean_q_investment_multiplier",
        "metric.source.m6.q_adjusted_investment_target",
        "metric.source.m6.household_equity_wealth_ema",
        "metric.source.m6.household_equity_consumption_addition",
        "metric.economy.tobin_q_mean",
        "metric.economy.equity_ownership_gini",
        "metric.economy.hh_wealth_gini_incl_equity",
        "metric.source.m4.fixed_capital_formation_real",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "housing": (
        "metric.source.m8.housing.house_price",
        "metric.source.m8.housing.rent_level",
        "metric.source.m8.housing.housing_stock",
        "metric.source.m8.housing.homeownership_share",
        "metric.source.m8.housing.vacancy_share",
        "metric.source.m8.housing.active_listings",
        "metric.source.m8.housing.forced_listing_share",
        "metric.source.m8.housing.session_sales",
        "metric.source.m8.housing.session_volume",
        "metric.source.m8.housing.mean_time_on_market_days",
        "metric.source.m8.housing.mortgage_originations",
        "metric.source.m8.housing.mortgage_principal_originated",
        "metric.source.m8.housing.mortgage_principal_outstanding",
        "metric.source.m8.housing.foreclosures",
        "metric.source.m8.housing.rent_paid",
        "metric.source.m8.housing.rent_unpaid",
        "metric.source.m8.housing.evictions",
        "metric.source.m8.housing.land_fee_paid",
        "metric.source.m8.housing.construction_output",
        "metric.source.m8.housing.dwellings_completed",
        "metric.source.m8.housing.price_to_income_ratio",
        "metric.source.m8.housing.rent_burden_ratio",
        "metric.source.m8.housing.leave_home_multiplier",
        "metric.source.m8.housing.fertility_multiplier",
        "metric.source.m7.births",
        "metric.source.m7.leaving_home_events",
        "metric.economy.na.household_consumption_real",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "energy": (
        "metric.source.m8.energy.production",
        "metric.source.m8.energy.capacity",
        "metric.source.m8.energy.producer_capital",
        "metric.source.m8.energy.utilization",
        "metric.source.m8.energy.opening_supply",
        "metric.source.m8.energy.requested_total",
        "metric.source.m8.energy.requested_households",
        "metric.source.m8.energy.requested_industry",
        "metric.source.m8.energy.sold",
        "metric.source.m8.energy.unfilled",
        "metric.source.m8.energy.transaction_price",
        "metric.source.m8.energy.household_units",
        "metric.source.m8.energy.household_spending",
        "metric.source.m8.energy.industry_units",
        "metric.source.m8.energy.industry_spending",
        "metric.source.m8.energy.fuel_poverty_share",
        "metric.source.m8.energy.fuel_poverty_mortality_multiplier",
        "metric.source.m8.energy.deprivation_below_100_share",
        "metric.source.m8.energy.deprivation_below_60_share",
        "metric.source.m8.energy.deprivation_below_30_share",
        "metric.source.m8.energy.deprivation_acute_stock",
        "metric.source.m8.energy.deprivation_chronic_stock",
        "metric.economy.energy_coverage_mean",
        "metric.economy.energy_stock_total",
        "metric.economy.labor_sector_energy_fte",
        "metric.economy.sector_energy_sales",
        "metric.source.m4.fixed_capital_formation_real",
        "metric.source.m4.aggregate_capital",
        "metric.source.m7.deaths",
        "metric.economy.na.household_consumption_real",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
        "metric.economy.price_index",
    ),
    "open_economy": (
        "metric.source.m9.country.exchange_rate",
        "metric.source.m9.country.imports_value",
        "metric.source.m9.country.imports_volume",
        "metric.source.m9.country.exports_value",
        "metric.source.m9.country.exports_volume",
        "metric.source.m9.country.iceberg_loss",
        "metric.source.m9.country.current_account",
        "metric.source.m9.country.capital_flow",
        "metric.source.m9.country.net_foreign_assets",
        "metric.source.m9.country.factor_income_accrued",
        "metric.source.m9.country.factor_income_cash",
        "metric.source.m9.country.factor_income_arrears",
        "metric.source.m9.country.peg_reserves",
        "metric.source.m9.country.migrant_stock_abroad",
        "metric.source.m9.country.migrant_stock_hosted",
        "metric.source.m9.country.remittances_received",
        "metric.source.m9.country.remittances_sent",
        "metric.source.m9.country.fx_mutualization_paid",
        "metric.source.m9.world.dealer_flow",
        "metric.source.m9.world.dealer_spread_revenue",
        "metric.source.m9.world.dealer_valuation",
        "metric.source.m9.world.world_nfa",
        "metric.source.m9.world.trade_routes",
        "metric.source.m9.world.migration_routes",
        "metric.economy.real_output",
        "metric.economy.avg_wage",
        "metric.economy.price_index",
        "metric.economy.unemployment_rate",
    ),
}


@dataclass(frozen=True, slots=True)
class TreatmentContract:
    field_id: str
    field_name: str
    scope: str
    module: str
    experiment_role: str
    route_status: str
    baseline_value: Any
    status: str
    treatment_kind: str
    treatment_values: tuple[Any, ...]
    primary_metrics: tuple[str, ...]
    expected_directions: Mapping[str, str]
    direction_statistics: Mapping[str, str]
    horizon_days: int
    countries: int
    activation_scenario: str
    rationale: str


def _suggested_numeric_levels(value: int | float) -> tuple[int | float, ...]:
    """Return non-authoritative, type-preserving review suggestions."""
    if isinstance(value, int):
        if value <= 0:
            return (1,)
        low = max(0, round(value * 0.75))
        high = max(low + 1, round(value * 1.25))
        return tuple(candidate for candidate in (low, high) if candidate != value)
    number = float(value)
    if number > 0.0:
        return (number * 0.75, number * 1.25)
    if number < 0.0:
        return (number * 1.25, number * 0.75)
    return (-0.01, 0.01)


def _draft_treatment(row: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    baseline = row["playable_baseline"]
    annotation = str(row["annotation"])
    if annotation == "bool" and isinstance(baseline, bool):
        return "boolean_toggle", (not baseline,)
    if annotation in {"float", "int"} and isinstance(baseline, (int, float)):
        return "numeric_levels", _suggested_numeric_levels(baseline)
    if row["field_name"] == "bank_assignment":
        return "categorical_alternative", (
            "by_size" if baseline == "random" else "random",
        )
    if row["field_name"] == "simulation_start_date":
        start = date.fromisoformat(str(baseline))
        return "calendar_shift", (start.replace(year=start.year + 10).isoformat(),)
    return "manual_review", ()


def _default_status(row: Mapping[str, Any]) -> str:
    role = str(row["experiment_role"])
    if role == "repair_before_experiment":
        return "blocked_native_route"
    if role in {"excluded_policy", "excluded_shock", "excluded_non_treatment"}:
        return role
    if role == "invariance_only":
        return "invariance_review_required"
    if role == "scale_invariance":
        return "scale_contract_required"
    if role == "genesis_transient":
        return "washout_contract_required"
    return "economic_review_required"


def _production_contracts() -> Mapping[str, Mapping[str, Any]]:
    output = "metric.economy.na.real_gdp_per_capita"
    capital = "metric.source.m4.aggregate_capital"
    investment = "metric.source.m4.fixed_capital_formation_real"
    return {
        "config.a": {
            "status": "excluded_non_treatment",
            "values": (),
            "directions": {},
            "rationale": "The product uses Cobb-Douglas consumption firms, where Hicks-neutral A replaces the linear-productivity compatibility input.",
        },
        "config.alpha": {
            "status": "screening_ready",
            "values": (0.25, 0.35),
            "directions": {capital: "nonzero", output: "ambiguous"},
            "rationale": "Capital income share changes factor substitution and distribution; the equilibrium output sign is not imposed.",
        },
        "config.capital_firm_entry": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.source.m6.firm_births": "decrease",
                "metric.economy.firm_count_k": "decrease",
            },
            "rationale": "A capability ablation should remove endogenous capital-firm births without disabling incumbent production.",
        },
        "config.capital_market": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.economy.equity_market_cap": "decrease",
                "metric.source.m6.primary_equity_raised": "decrease",
            },
            "rationale": "Capability ablation identifies the equity-finance channel and its real-economy spillovers.",
        },
        "config.capital_rationed_signal": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {investment: "nonzero"},
            "statistics": {investment: "cumulative"},
            "activation": "positive_capital_gap",
            "rationale": "Halving opening consumption-firm capital creates positive investment orders and unmet capital demand, allowing the expectations signal to affect subsequent capital-goods production.",
        },
        "config.case-a": {
            "status": "screening_ready",
            "values": (0.1362705873, 0.2044058809),
            "directions": {
                output: "increase",
                "metric.economy.price_index": "decrease",
            },
            "rationale": "Hicks-neutral consumption-sector productivity should raise real capacity and lower marginal cost, holding other structural inputs fixed.",
        },
        "config.case-a_k": {
            "status": "screening_ready",
            "values": (2.304, 3.456),
            "directions": {
                "metric.source.m4.capital_output_real": "increase",
                investment: "increase",
            },
            "rationale": "Capital-goods labor productivity should expand machinery supply and relax investment bottlenecks.",
        },
        "config.case-delta_k": {
            "status": "screening_ready",
            "values": (0.0001824, 0.0002736),
            "directions": {capital: "decrease", investment: "increase"},
            "rationale": "Faster depreciation destroys the installed stock while raising replacement demand; both legs must be visible.",
        },
        "config.case-k_firm0": {
            "status": "screening_ready",
            "values": (5840.0, 8760.0),
            "directions": {capital: "washout"},
            "rationale": "Opening capital is a genesis condition: the initial stock must move proportionally and its normalized effect should decay.",
        },
        "config.case-lambda_i": {
            "status": "activation_scenario_required",
            "values": (0.00152, 0.00228),
            "directions": {investment: "nonzero"},
            "statistics": {investment: "cumulative"},
            "activation": "positive_capital_gap",
            "rationale": "Investment adjustment speed only binds when desired capital exceeds the installed stock; the baseline initially sits on its replacement-only branch.",
        },
        "config.lambda_issue": {
            "status": "screening_ready",
            "values": (0.1, 0.3),
            "directions": {
                "metric.source.m6.primary_equity_raised": "increase"
            },
            "statistics": {
                "metric.source.m6.primary_equity_raised": "first_window_mean"
            },
            "activation": "neutral_baseline_q_above_one",
            "rationale": "The audited product baseline has Tobin's q above one and positive daily issuance, so the issuance-intensity channel is identified without a synthetic stress scenario.",
        },
        "config.tfp_drift_rate": {
            "status": "screening_ready",
            "values": (0.006, 0.024),
            "directions": {output: "increase"},
            "horizon_days": 1825,
            "rationale": "A higher annual TFP trend must steepen medium-run real output growth rather than create a one-day level jump.",
        },
        "config.tfp_drift_c": {
            "status": "screening_ready",
            "values": (0.024,),
            "directions": {
                "metric.source.m4.tfp_index_consumption": "increase",
            },
            "horizon_days": 365,
            "rationale": "The consumption-sector override must steepen only its own technology index while leaving the common trend as the fallback for other sectors.",
        },
        "config.tfp_drift_k": {
            "status": "screening_ready",
            "values": (0.024,),
            "directions": {
                "metric.source.m4.tfp_index_capital": "increase",
            },
            "horizon_days": 365,
            "rationale": "The capital-goods override must independently move machinery-sector productivity and its direct index.",
        },
        "config.tfp_drift_e": {
            "status": "screening_ready",
            "values": (0.024,),
            "directions": {
                "metric.source.m4.tfp_index_energy": "increase",
            },
            "horizon_days": 365,
            "rationale": "The energy override must reach energy producers rather than aliasing the consumption-sector technology path.",
        },
        "config.tfp_drift_sigma": {
            "status": "screening_ready",
            "values": (0.08,),
            "directions": {
                "metric.source.m4.tfp_growth_consumption": "nonzero",
            },
            "horizon_days": 365,
            "rationale": "A positive innovation scale must create a reproducible nonzero TFP-growth path on its dedicated RNG stream.",
        },
        "config.tfp_law": {
            "status": "activation_scenario_required",
            "values": ("learning",),
            "directions": {
                "metric.source.m4.tfp_index_consumption": "nonzero",
            },
            "horizon_days": 730,
            "activation": "positive_learning_elasticity",
            "rationale": "Selecting learning must replace calendar drift with cumulative sector experience once theta is positive.",
        },
        "config.tfp_learning_theta": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.20),
            "directions": {
                "metric.source.m4.tfp_index_consumption": "increase",
            },
            "horizon_days": 730,
            "activation": "tfp_learning_law",
            "rationale": "Under the learning law, a larger elasticity must translate the same accumulated output into a larger productivity gain.",
        },
        "config.v": {
            "status": "screening_ready",
            "values": (730.0, 1095.0),
            "directions": {capital: "increase", investment: "increase"},
            "rationale": "The desired capital-output ratio raises desired installed capital and the investment needed to approach it.",
        },
    }


def _firm_contracts() -> Mapping[str, Mapping[str, Any]]:
    births = "metric.source.m6.firm_births"
    exits = "metric.source.m6.firm_exits"
    capital_firms = "metric.economy.firm_count_k"
    switches = "metric.source.m6.sector_switches"
    retool = "metric.source.m6.sector_retool_capital"
    return {
        "config.demand_e_firm0": {
            "status": "screening_ready",
            "values": (5.0, 7.5),
            "directions": {
                "metric.source.m8.energy.production": "washout",
            },
            "horizon_days": 1825,
            "rationale": "Opening expected energy demand is a genesis seed; it must move early production and then lose influence.",
        },
        "config.entry_beta": {
            "status": "screening_ready",
            "values": (0.2, 0.6),
            "directions": {births: "increase"},
            "statistics": {births: "cumulative"},
            "rationale": "Entry sensitivity scales the number of consumption-firm entrants generated by a positive median excess return.",
        },
        "config.entry_hurdle": {
            "status": "screening_ready",
            "values": (0.0, 0.000268),
            "directions": {births: "decrease"},
            "statistics": {births: "cumulative"},
            "rationale": "A higher required return should suppress consumption-firm entry, holding profitability and the policy rate fixed.",
        },
        "config.entry_max": {
            "status": "activation_scenario_required",
            "values": (1, 6),
            "directions": {births: "increase"},
            "statistics": {births: "cumulative"},
            "activation": "high_consumption_entry_pressure",
            "rationale": "The per-day cap is exactly silent in the neutral one-year screen; a shared high entry sensitivity and zero hurdle force desired entry above the cap while preserving the audited limit.",
        },
        "config.firm_dynamics": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {births: "decrease", exits: "decrease"},
            "statistics": {births: "cumulative", exits: "cumulative"},
            "rationale": "The master capability ablation must remove endogenous firm births and exits; Config validity also closes the dependent founder-equity capability, so broad spillovers are interpreted as a package rather than a pure dynamics effect.",
        },
        "config.firm_full_pnl": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.source.m5.loan_interest_paid": "nonzero",
                "metric.source.m4.firm_profit": "nonzero",
            },
            "statistics": {
                "metric.source.m5.loan_interest_paid": "cumulative",
                "metric.source.m4.firm_profit": "cumulative",
            },
            "rationale": "The full cash-basis income statement services debt before settlement; disabling it tests whether that phase ordering changes realized interest and firm profit flows.",
        },
        "config.firm_subscale_exit": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "rationale": "Disabling viability exits should reduce total firm exits after the grace period.",
        },
        "config.k_entry_demand": {
            "status": "screening_ready",
            "values": (1.0, 5.0),
            "directions": {capital_firms: "decrease"},
            "rationale": "A higher sector-wide labor-demand threshold should make capital-firm spin-offs less frequent.",
        },
        "config.k_entry_hazard": {
            "status": "screening_ready",
            "values": (1.0 / 120.0, 1.0 / 30.0),
            "directions": {capital_firms: "increase"},
            "rationale": "Conditional on sector capacity pressure, a higher daily spin-off hazard should raise the capital-firm stock.",
        },
        "config.mu_firm0": {
            "status": "screening_ready",
            "values": (0.15, 0.25),
            "directions": {"metric.economy.avg_markup": "washout"},
            "horizon_days": 1825,
            "rationale": "Opening markup is a quote seed; it should affect early prices and margins but converge under endogenous price adjustment.",
        },
        "config.rho": {
            "status": "screening_ready",
            "values": (0.1, 0.9),
            "directions": {
                "metric.source.m4.dividends_paid": "increase",
            },
            "statistics": {
                "metric.source.m4.dividends_paid": "cumulative",
            },
            "rationale": "The profit-distribution ratio allocates after-tax positive firm earnings between shareholder dividends and retained earnings. A higher ratio must increase the directly reported dividend flow, holding operating profitability and all other rules fixed.",
        },
        "config.sector_switching": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {
                switches: "decrease",
                retool: "decrease",
            },
            "statistics": {
                switches: "cumulative",
                retool: "cumulative",
            },
            "activation": "sector_returns_retool",
            "rationale": "This is the master capability gate for endogenous firm movement between sectors. Disabling it under a shared return-gap activation must eliminate both switch events and the physical capital destroyed during retooling.",
        },
        "config.shell_exit_ticks": {
            "status": "activation_scenario_required",
            "values": (180, 548),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "activation": "idle_consumption_firms",
            "horizon_days": 730,
            "rationale": "A shared zero-capital, zero-inventory, no-investment setup creates idle shells while disabling the competing subscale-exit rule.",
        },
        "config.subscale_exit_hazard": {
            "status": "screening_ready",
            "values": (1.0 / 180.0, 1.0 / 45.0),
            "directions": {exits: "increase"},
            "statistics": {exits: "cumulative"},
            "rationale": "After the viability grace period, a higher daily hazard should increase subscale exits.",
        },
        "config.subscale_grace_days": {
            "status": "screening_ready",
            "values": (90, 365),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "rationale": "A longer continuous-below-viability grace period should delay and reduce exits over a fixed horizon.",
        },
        "config.subscale_viability_workers": {
            "status": "screening_ready",
            "values": (0.05, 2.0),
            "directions": {exits: "increase"},
            "statistics": {exits: "cumulative"},
            "rationale": "A higher minimum viable labor demand classifies more firms as subscale and should increase exits.",
        },
        "config.switch_hazard": {
            "status": "activation_scenario_required",
            "values": (0.005, 0.02),
            "directions": {switches: "increase"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_hazard",
            "rationale": "A shared low return gap and short pressure window create eligible firms while preserving the audited switch hazard.",
        },
        "config.switch_pressure_days": {
            "status": "activation_scenario_required",
            "values": (2, 10),
            "directions": {switches: "decrease"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_pressure",
            "rationale": "A shared low return gap and higher hazard preserve the audited pressure duration; 2 and 10 days identify the mechanism after 30 and 120 days proved silent because return leadership resets too often.",
        },
        "config.switch_retool_loss": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.15),
            "directions": {retool: "increase"},
            "statistics": {retool: "cumulative"},
            "activation": "sector_returns_retool",
            "rationale": "A common switching regime identifies the physical capital destroyed per retool event.",
        },
        "config.switch_return_gap": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.10),
            "directions": {switches: "decrease"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_gap",
            "rationale": "A short pressure window and higher hazard expose how the required relative-return gap governs eligibility.",
        },
        "config.w_firm0": {
            "status": "screening_ready",
            "values": (0.8, 1.2),
            "directions": {"metric.economy.avg_wage": "washout"},
            "horizon_days": 1825,
            "rationale": "Opening posted wage should move initial labor-market quotes and then converge under endogenous wage adjustment.",
        },
    }


def _consumption_contracts() -> Mapping[str, Mapping[str, Any]]:
    consumption = "metric.economy.na.household_consumption_real"
    inventory = "metric.economy.inventory_to_sales"
    markup = "metric.economy.avg_markup"
    inflation = "metric.economy.inflation"
    return {
        "config.alpha1": {
            "status": "screening_ready",
            "values": (0.90, 0.99),
            "directions": {consumption: "increase"},
            "rationale": "A higher marginal propensity out of expected income should raise household consumption demand, holding income, wealth, taxes, and credit rules fixed.",
        },
        "config.alpha2": {
            "status": "screening_ready",
            "values": (1.0e-6, 5.0e-4),
            "directions": {consumption: "increase"},
            "rationale": "A higher propensity out of liquid wealth should raise consumption for a given expected income and opening balance sheet.",
        },
        "config.consumption_rationed_signal": {
            "status": "activation_scenario_required",
            "values": (True,),
            "directions": {inventory: "increase"},
            "activation": "opening_consumption_stockout",
            "rationale": "A shared opening stockout exposes whether unfilled consumer and government orders enter seller demand expectations and raise the subsequent inventory response; output, employment, prices, and realized consumption remain unconstrained trade-offs.",
        },
        "config.eta": {
            "status": "screening_ready",
            "values": (3.35e-4, 1.34e-3),
            "directions": {markup: "nonzero"},
            "rationale": "Markup adjustment speed must change the response of price-cost margins to inventory imbalance; the equilibrium sign depends on whether shortages or excess stocks dominate.",
        },
        "config.inventory_gap_close": {
            "status": "screening_ready",
            "values": (0.025, 0.10),
            "directions": {inventory: "nonzero"},
            "rationale": "The fraction of the target inventory gap closed each day should alter realized inventory coverage and production volatility without changing the long-run inventory target itself.",
        },
        "config.lambda_d": {
            "status": "screening_ready",
            "values": (0.0019, 0.0076),
            "directions": {inventory: "nonzero"},
            "rationale": "Faster seller demand learning should change the inventory and sales path after daily demand surprises; its long-run level sign is not imposed.",
        },
        "config.lambda_y": {
            "status": "screening_ready",
            "values": (0.0038, 0.0152),
            "directions": {consumption: "nonzero"},
            "rationale": "Faster permanent-income updating should change consumption when realized labor and transfer income differs from prior expectations.",
        },
        "config.mu_max": {
            "status": "activation_scenario_required",
            "values": (0.20, 0.22),
            "directions": {markup: "increase"},
            "activation": "markup_ceiling_pressure",
            "rationale": "A higher markup ceiling should permit higher price-cost margins when shortage pressure would otherwise bind the cap.",
        },
        "config.mu_min": {
            "status": "activation_scenario_required",
            "values": (0.18, 0.20),
            "directions": {markup: "increase"},
            "activation": "markup_floor_pressure",
            "rationale": "A higher markup floor should prevent competitive or excess-inventory pressure from compressing margins below the configured bound.",
        },
        "config.phi": {
            "status": "screening_ready",
            "values": (10.5, 17.5),
            "directions": {inventory: "increase"},
            "rationale": "A higher target number of inventory days should raise inventory coverage and create a larger working-stock buffer against demand surprises.",
        },
        "config.search_m": {
            "status": "screening_ready",
            "values": (2, 8),
            "directions": {
                "metric.analysis.goods_transaction_price_proxy": "nonzero"
            },
            "rationale": "Comparing more sampled sellers increases consumer price transparency. The partial-equilibrium selection effect favors cheaper offers, but inventory depletion, seller learning, and the current mixed household/sector price proxy leave the long-run equilibrium sign unconstrained. The ordinary range stops at eight because larger samples add little measured benefit while increasing matching cost materially.",
        },
        "config.theta_price": {
            "status": "screening_ready",
            "values": (0.00185, 0.00740),
            "directions": {inflation: "nonzero"},
            "statistics": {inflation: "post_burnin_volatility"},
            "rationale": "The daily Calvo repricing probability should alter inflation dynamics and the speed at which desired markups pass into posted prices; the volatility sign is an empirical model result.",
        },
    }


def _labor_contracts() -> Mapping[str, Mapping[str, Any]]:
    efficiency_dispersion = "metric.source.m7.person_efficiency_stddev"
    participation = "metric.source.m7.participation_rate"
    hires = "metric.source.m7.hires"
    churn = "metric.source.m7.churn_separations"
    layoffs = "metric.source.m7.demand_layoff_separations"
    suspensions = "metric.source.m7.suspensions_flow"
    suspension_poaches = "metric.source.m7.suspension_poaches"
    suspended = "metric.source.m7.suspended"
    second_jobs = "metric.source.m7.second_job_hours"
    moves = "metric.source.m7.job_to_job_moves"
    welfare_quits = "metric.source.m7.welfare_quits"
    wage = "metric.source.m7.mean_hourly_wage"
    return {
        "config.churn_annual": {
            "status": "screening_ready",
            "values": (0.14, 0.42),
            "directions": {churn: "increase"},
            "statistics": {churn: "cumulative"},
            "rationale": "The annual exogenous separation probability should change cumulative churn separations while preserving demand layoffs as a distinct channel.",
        },
        "config.delta": {
            "status": "screening_ready",
            "values": (0.0, 0.0099),
            "directions": {wage: "decrease"},
            "rationale": "Faster downward wage adjustment should reduce posted and relationship wages when firms face labor surplus; employment and output are equilibrium trade-offs.",
        },
        "config.efficiency_sigma": {
            "status": "screening_ready",
            "values": (0.0, 0.70),
            "directions": {efficiency_dispersion: "increase"},
            "rationale": "The standard deviation of permanent lognormal person efficiency should increase with its genesis dispersion parameter while mean efficiency remains normalized near one. Output, wages, sorting, and employment are equilibrium spillovers.",
        },
        "config.job_search_intensity": {
            "status": "screening_ready",
            "values": (0.075, 0.30),
            "directions": {hires: "increase"},
            "statistics": {hires: "cumulative"},
            "rationale": "With frictional matching enabled, a higher daily contact probability should raise successful hires over a fixed horizon.",
        },
        "config.labor_fractional_hours": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {second_jobs: "decrease"},
            "statistics": {second_jobs: "cumulative"},
            "rationale": "Disabling the intensive margin also closes dependent second jobs; the package should remove secondary hours and change underemployment and vacancies.",
        },
        "config.labor_job_ladder": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {moves: "decrease"},
            "statistics": {moves: "cumulative"},
            "activation": "active_job_ladder",
            "rationale": "A shared zero wage-premium threshold creates qualifying on-the-job offers; disabling the ladder should then remove job-to-job moves while leaving ordinary unemployment matching enabled.",
        },
        "config.labor_matching_friction": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {hires: "increase"},
            "statistics": {hires: "cumulative"},
            "rationale": "Removing the daily contact gate should accelerate vacancy filling and raise cumulative hires, with unemployment as the main spillover.",
        },
        "config.labor_participation": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {participation: "increase"},
            "activation": "binding_labor_reservation",
            "rationale": "A shared binding reservation markup causes eligible workers to withdraw under the endogenous margin; disabling it should keep them in the labor force.",
        },
        "config.labor_relationship_wages": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {moves: "decrease"},
            "statistics": {moves: "cumulative"},
            "activation": "active_job_ladder",
            "rationale": "Relationship wages are required by the job ladder, so this capability ablation closes the ladder under a shared active-ladder setup and is interpreted as a wage-contract package.",
        },
        "config.labor_second_job": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {second_jobs: "decrease"},
            "statistics": {second_jobs: "cumulative"},
            "rationale": "Disabling secondary contracts should remove hours sold by workers whose primary job does not use their full daily labor capacity.",
        },
        "config.labor_suspension": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {suspensions: "decrease"},
            "statistics": {suspensions: "cumulative"},
            "rationale": "Without employment-preserving suspensions, payroll shortfalls should become cash layoffs rather than retained recall options.",
        },
        "config.ladder_premium": {
            "status": "screening_ready",
            "values": (0.0, 0.10),
            "directions": {moves: "decrease"},
            "statistics": {moves: "cumulative"},
            "rationale": "A larger required wage gain should reject more on-the-job offers and reduce job-to-job transitions.",
        },
        "config.ladder_search_intensity": {
            "status": "activation_scenario_required",
            "values": (0.015, 0.06),
            "directions": {moves: "increase"},
            "statistics": {moves: "cumulative"},
            "activation": "active_job_ladder",
            "rationale": "A shared zero wage-premium threshold supplies qualifying offers, so a higher daily on-the-job search probability should raise cumulative job-to-job transitions.",
        },
        "config.lambda_fire": {
            "status": "screening_ready",
            "values": (0.015, 0.06),
            "directions": {layoffs: "increase"},
            "statistics": {layoffs: "cumulative"},
            "rationale": "Faster closure of a firm's excess-labor gap should raise demand layoffs over a fixed adjustment window and reduce labor hoarding.",
        },
        "config.layoff_band": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.50),
            "directions": {layoffs: "decrease"},
            "statistics": {layoffs: "cumulative"},
            "activation": "labor_demand_contraction",
            "rationale": "A shared high opening demand estimate with fast demand learning creates a common hiring boom and correction; a wider employment hysteresis band should absorb more of that contraction before layoffs begin.",
        },
        "config.layoff_target_smooth": {
            "status": "screening_ready",
            "values": (0.01, 0.08),
            "directions": {layoffs: "increase"},
            "statistics": {layoffs: "cumulative"},
            "rationale": "During a demand contraction, faster target smoothing lets the protected firing target fall sooner and should increase layoffs over a fixed horizon.",
        },
        "config.omega": {
            "status": "screening_ready",
            "values": (0.00375, 0.015),
            "directions": {wage: "increase"},
            "rationale": "Faster shortage-driven wage adjustment should raise wages when desired labor exceeds available hires.",
        },
        "config.reservation_markup": {
            "status": "screening_ready",
            "values": (0.5, 2.5),
            "directions": {participation: "decrease"},
            "rationale": "A higher reservation markup raises the wage required relative to the welfare outside option and should reduce labor-force participation.",
        },
        "config.suspension_timer": {
            "status": "screening_ready",
            "values": (1, 90),
            "directions": {suspended: "increase"},
            "rationale": "A longer recall window should retain more suspended matches; automatic cash layoffs and successful outside matches are reported as competing transition flows rather than assigned a permanent sign.",
        },
        "config.suspension_quit_discount": {
            "status": "screening_ready",
            "values": (1.05,),
            "directions": {suspension_poaches: "decrease"},
            "statistics": {suspension_poaches: "cumulative"},
            "rationale": "A higher outside-offer threshold preserves more recall options by requiring a suspended worker to receive a larger wage relative to the suspended contract before accepting another employer's offer. The playable wage grid saturates below the 0.9 baseline—all observed outside offers already qualify—so the reviewed treatment probes the economically active upper side rather than crediting a deliberately flat lower arm.",
        },
        "config.theta_wage": {
            "status": "screening_ready",
            "values": (0.0055, 0.022),
            "directions": {wage: "nonzero"},
            "statistics": {wage: "post_burnin_volatility"},
            "rationale": "The Calvo wage-reset probability should change wage dynamics and the pass-through speed of labor shortages or surpluses.",
        },
        "config.welfare_quit_hazard": {
            "status": "activation_scenario_required",
            "values": (0.01, 0.08),
            "directions": {welfare_quits: "increase"},
            "statistics": {welfare_quits: "cumulative"},
            "activation": "binding_labor_reservation",
            "rationale": "A shared binding reservation threshold creates underpaid incumbents, so a higher daily quit hazard should raise welfare-motivated separations.",
        },
    }


def _demography_contracts() -> Mapping[str, Mapping[str, Any]]:
    births = "metric.source.m7.births"
    deaths = "metric.source.m7.deaths"
    marriages = "metric.source.m7.marriages"
    divorces = "metric.source.m7.divorces"
    leaving = "metric.source.m7.leaving_home_events"
    partner_efficiency_gap = (
        "metric.source.m7.mean_partner_log_efficiency_gap"
    )
    return {
        "config.demographic_adult_leaving_home_enabled": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {leaving: "decrease"},
            "statistics": {leaving: "cumulative"},
            "activation": "eligible_peak_leaving_home",
            "rationale": "A shared minimum eligibility age of 18 exposes the oldest genesis children within one year. Disabling adult household formation should then remove departures and reduce the creation of one-person households.",
        },
        "config.demographic_annual_divorce_rate_base": {
            "status": "screening_ready",
            "values": (0.006, 0.024),
            "directions": {divorces: "increase"},
            "statistics": {divorces: "cumulative"},
            "rationale": "A higher annual union-dissolution hazard should raise cumulative divorces while exposing household-size, housing, consumption, and labor spillovers.",
        },
        "config.demographic_annual_leave_rate_late": {
            "status": "activation_scenario_required",
            "values": (0.025, 0.10),
            "directions": {leaving: "increase"},
            "statistics": {leaving: "cumulative"},
            "activation": "eligible_late_leaving_home",
            "rationale": "A shared eligibility and peak-end age of 18 exposes the oldest genesis children directly to the late departure hazard. A higher rate should raise cumulative household formation.",
        },
        "config.demographic_annual_leave_rate_peak": {
            "status": "activation_scenario_required",
            "values": (0.125, 0.50),
            "directions": {leaving: "increase"},
            "statistics": {leaving: "cumulative"},
            "activation": "eligible_peak_leaving_home",
            "rationale": "A shared minimum eligibility age of 18 places the oldest genesis children in the peak band within one year. A higher departure hazard should raise cumulative household formation.",
        },
        "config.demographic_annual_marriage_rate_peak": {
            "status": "screening_ready",
            "values": (0.15, 0.60),
            "directions": {marriages: "increase"},
            "statistics": {marriages: "cumulative"},
            "rationale": "A higher annual acceptance hazard in the marriage market should raise cumulative new unions over a fixed year.",
        },
        "config.demographic_divorce_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {divorces: "decrease"},
            "statistics": {divorces: "cumulative"},
            "rationale": "Disabling divorce should remove union-dissolution events while retaining mortality-driven widowhood as a separate mechanism.",
        },
        "config.demographic_leave_home_min_age": {
            "status": "screening_ready",
            "values": (18, 26),
            "directions": {leaving: "decrease"},
            "statistics": {leaving: "cumulative"},
            "horizon_days": 3650,
            "rationale": "A higher eligibility age should reduce the stock of co-resident adult children able to establish a new household.",
        },
        "config.demographic_leave_home_peak_end_age": {
            "status": "activation_scenario_required",
            "values": (26, 35),
            "directions": {leaving: "increase"},
            "statistics": {leaving: "cumulative"},
            "activation": "long_horizon_peak_leaving_home",
            "horizon_days": 7300,
            "rationale": "A shared minimum age of 18 and lower common departure hazards preserve enough co-resident children to cross the alternative peak-band endpoints over twenty years. Because the peak rate exceeds the late rate, extending the band should raise cumulative departures.",
        },
        "config.demographic_marriage_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {marriages: "decrease"},
            "statistics": {marriages: "cumulative"},
            "rationale": "Disabling marriage should remove newly formed unions without suppressing the dissolution of unions created at genesis.",
        },
        "config.demographic_marriage_market_interval_days": {
            "status": "screening_ready",
            "values": (14, 90),
            "directions": {marriages: "invariance"},
            "statistics": {marriages: "cumulative"},
            "rationale": "This is a numerical market-clearing cadence rather than an economic intensity: the annual acceptance hazard is interval-adjusted, so cumulative marriage incidence should remain equivalent apart from finite-sample timing noise. It is not a gameplay lever.",
        },
        "config.demographics_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {births: "decrease", deaths: "decrease"},
            "statistics": {births: "cumulative", deaths: "cumulative"},
            "rationale": "The legacy master switch closes vital events and dependent person-level capabilities. Its broad effects are interpreted as a capability package, not as pure fertility or mortality coefficients.",
        },
        "config.demographics_mortality_scale": {
            "status": "screening_ready",
            "values": (0.50, 1.50),
            "directions": {deaths: "increase"},
            "statistics": {deaths: "cumulative"},
            "rationale": "Scaling the Makeham and Gompertz hazards upward should raise cumulative deaths and change dependency, estates, labor supply, and consumption.",
        },
        "config.demographics_tfr": {
            "status": "screening_ready",
            "values": (1.0, 2.2),
            "directions": {births: "increase"},
            "statistics": {births: "cumulative"},
            "rationale": "A higher total fertility rate should raise cumulative births, with population and dependency effects emerging over longer horizons.",
        },
        "config.marriage_assortativity": {
            "status": "activation_scenario_required",
            "values": (0.0, 4.0),
            "directions": {partner_efficiency_gap: "decrease"},
            "activation": "unpartnered_marriage_market",
            "rationale": "A shared one-person-household genesis removes pre-existing unions and activates a common marriage market. A higher efficiency-similarity weight should reduce the mean absolute log-efficiency gap within active couples, potentially trading off against age similarity.",
        },
    }


def _distribution_contracts() -> Mapping[str, Mapping[str, Any]]:
    budget = "metric.source.m4.household_consumption_budget"
    wealth_budget = "metric.source.m4.household_wealth_consumption_budget"
    income_mpc_stddev = "metric.source.m4.household_income_propensity_stddev"
    wealth_mpc_stddev = "metric.source.m4.household_wealth_propensity_stddev"
    necessity_requested = "metric.source.m4.necessity_requested_quantity"
    necessity_spending = "metric.source.m4.necessity_consumption"
    luxury_spending = "metric.source.m4.luxury_consumption"
    necessity_share = "metric.source.m4.necessity_consumption_share"
    necessity_firms = "metric.source.m4.necessity_firm_count"
    luxury_firms = "metric.source.m4.luxury_firm_count"
    transfer_total = "metric.source.m7.family_transfer_total"
    transfer_recipients = "metric.source.m7.family_transfer_recipients"
    deprivation = "metric.source.m8.energy.deprivation_below_100_share"
    output = "metric.economy.real_output"
    unemployment = "metric.economy.unemployment_rate"
    consumption = "metric.economy.na.household_consumption_real"
    return {
        "config.consumption_strata": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {
                necessity_requested: "nonzero",
                necessity_share: "nonzero",
                necessity_spending: "nonzero",
                luxury_spending: "nonzero",
            },
            "activation": "consumption_strata_isolation",
            "rationale": "Disabling the structural split must replace the ordered fixed-quantity necessity session followed by residual luxury demand with one combined goods market. The direct spending composition must change while sector switching and family transfers are held inactive in both arms.",
        },
        "config.deprivation_gauges": {
            "status": "invariance_activation_required",
            "values": (False,),
            "directions": {
                deprivation: "decrease",
                output: "invariance",
                unemployment: "invariance",
                consumption: "invariance",
            },
            "activation": "deprivation_measurement_active",
            "rationale": "The deprivation switch controls a measurement state only. Turning it off should remove the published deprivation gauge while leaving production, employment, and household consumption exactly unchanged.",
        },
        "config.family_transfer_buffer": {
            "status": "screening_ready",
            "values": (1.0, 3.0),
            "directions": {transfer_total: "decrease"},
            "statistics": {transfer_total: "cumulative"},
            "rationale": "A larger donor reserve buffer protects more of each kin household's own consumption need and should reduce the amount privately transferred to liquidity-constrained relatives.",
        },
        "config.family_transfers": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                transfer_total: "decrease",
                transfer_recipients: "decrease",
            },
            "statistics": {
                transfer_total: "cumulative",
                transfer_recipients: "cumulative",
            },
            "rationale": "Disabling the private kin safety net should remove conserving household-to-household transfers and their recipients; poverty, consumption, and public support are equilibrium spillovers.",
        },
        "config.mpc_dispersion": {
            "status": "screening_ready",
            "values": (0.0, 0.80),
            "directions": {
                income_mpc_stddev: "increase",
                wealth_mpc_stddev: "increase",
                budget: "ambiguous",
            },
            "rationale": "A wider mean-corrected lognormal preference distribution must increase cross-household dispersion in both income and wealth propensities. Aggregate consumption is an equilibrium result because truncation, liquidity constraints, and income heterogeneity make the macro response nonlinear.",
        },
        "config.mpc_wealth_curvature": {
            "status": "activation_scenario_required",
            "values": (0.50,),
            "directions": {
                wealth_budget: "increase",
                budget: "ambiguous",
            },
            "activation": "wealth_dispersion",
            "rationale": "With positive dispersed household wealth, moving from a concave buffer-stock rule toward the linear rule must increase the wealth-financed consumption budget for above-reference wealth. Total planned consumption remains an equilibrium outcome because some households can remain below the reference and liquidity constraints bind.",
        },
        "config.n_firm_share": {
            "status": "screening_ready",
            "values": (0.25, 0.75),
            "directions": {
                necessity_firms: "increase",
                luxury_firms: "decrease",
            },
            "rationale": "The firm-share parameter changes only the genesis allocation of consumption producers across necessity and luxury sectors. Raising it must increase necessity producers and reduce luxury producers without redefining household necessity quantity.",
        },
        "config.necessity_share0": {
            "status": "screening_ready",
            "values": (0.25, 0.75),
            "directions": {
                necessity_requested: "increase",
                necessity_spending: "ambiguous",
                necessity_share: "ambiguous",
                luxury_spending: "ambiguous",
            },
            "rationale": "A larger fixed per-need-unit necessity basket must increase requested necessity quantity before residual luxury demand is admitted. Realized spending and its share remain equilibrium outcomes because sector capacity, prices, income, and stock-outs can move endogenously. It must not change the number of firms assigned to either sector.",
        },
        "config.subsistence_share": {
            "status": "invariance_activation_required",
            "values": (0.25, 0.75),
            "directions": {
                deprivation: "increase",
                output: "invariance",
                unemployment: "invariance",
                consumption: "invariance",
            },
            "activation": "deprivation_measurement_active",
            "rationale": "The subsistence share defines the external consumption standard used by the deprivation gauge. A higher line should classify more people as deprived, but it must not feed back into behavior or alter the economy being measured.",
        },
    }


def _banking_contracts() -> Mapping[str, Mapping[str, Any]]:
    new_credit = "metric.source.m5.new_credit"
    principal_repaid = "metric.source.m5.principal_repaid"
    loan_interest = "metric.source.m5.loan_interest_paid"
    deposit_paid = "metric.source.m5.deposit_interest_paid"
    deposit_arrears = "metric.source.m5.deposit_interest_arrears"
    loan_stock = "metric.source.m5.total_loan_principal"
    bank_capital = "metric.source.m5.total_bank_capital"
    interbank_volume = "metric.source.m5.interbank_volume"
    interbank_rate = "metric.source.m5.interbank_rate"
    run_flight = "metric.source.m5.run_flight_volume"
    bank_births = "metric.source.m6.bank_births"
    household_debt = "metric.economy.household_debt_total"
    investment_target = "metric.source.m5.firm_investment_target"
    user_cost_multiplier = (
        "metric.source.m5.investment_user_cost_multiplier_mean"
    )
    service_reserved = "metric.source.m5.household_debt_service_reserved"
    dscr_shortfall = "metric.source.m5.firm_dscr_credit_shortfall"
    return {
        "config.amort": {
            "status": "screening_ready",
            "values": (1.0 / (365.0 * 5.0), 1.0 / (365.0 * 1.25)),
            "directions": {principal_repaid: "increase", loan_stock: "decrease"},
            "statistics": {principal_repaid: "cumulative"},
            "rationale": "Faster contractual firm-loan amortization should raise principal repayments and shorten the outstanding loan stock, subject to borrower cash constraints.",
        },
        "config.bank_dynamics": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {bank_births: "decrease"},
            "statistics": {bank_births: "cumulative"},
            "activation": "bank_entry_eligible_founders",
            "rationale": "Disabling bank demographics should remove de-novo bank births when profitable incumbents and eligible founders are present.",
        },
        "config.bank_entry_beta": {
            "status": "activation_scenario_required",
            "values": (0.005, 0.08),
            "directions": {bank_births: "increase"},
            "statistics": {bank_births: "cumulative"},
            "activation": "bank_entry_eligible_founders",
            "rationale": "Entry sensitivity should scale the probability that excess bank ROE produces a de-novo bank, holding founder eligibility fixed.",
        },
        "config.bank_entry_max": {
            "status": "activation_scenario_required",
            "values": (0, 4),
            "directions": {bank_births: "increase"},
            "statistics": {bank_births: "first_window_mean"},
            "activation": "bank_entry_cap_pressure",
            "rationale": "The per-day bank-entry cap is identified only when shared entry pressure requests more than one entrant. It changes the speed of entry in the first response window, while the long-run number of banks can converge to the same market-saturation level.",
        },
        "config.bank_leverage_disp": {
            "status": "activation_scenario_required",
            "values": (0.0, 1.0),
            "directions": {loan_stock: "nonzero"},
            "activation": "binding_bank_capital",
            "rationale": "Cross-bank risk-appetite dispersion should change the allocation and aggregate quantity of credit under a shared binding capital constraint; the equilibrium aggregate sign is not imposed.",
        },
        "config.bank_leverage_mean": {
            "status": "activation_scenario_required",
            "values": (5.0, 15.0),
            "directions": {new_credit: "increase", loan_stock: "increase"},
            "statistics": {
                new_credit: "first_window_mean",
                loan_stock: "first_window_mean",
            },
            "activation": "binding_bank_capital",
            "rationale": "A larger bank leverage appetite relaxes the capital-based lending ceiling and should expand credit in the first response window when capacity binds. Longer-run credit stocks are equilibrium outcomes because easier initial finance changes output, employment, and subsequent liquidity demand.",
        },
        "config.bank_rate_competition": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {loan_interest: "nonzero", new_credit: "nonzero"},
            "statistics": {loan_interest: "cumulative", new_credit: "cumulative"},
            "rationale": "Borrower shopping across heterogeneous loan spreads should alter realized funding cost and credit allocation without assigning an equilibrium output sign.",
        },
        "config.bank_realized_pnl": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {bank_capital: "nonzero", deposit_paid: "decrease"},
            "statistics": {deposit_paid: "cumulative"},
            "activation": "positive_deposit_carry",
            "rationale": "The realized income statement books funding expense and losses before payout; the legacy gross-interest path should therefore change bank capital and omit contractual deposit expense.",
        },
        "config.bank_relationship_lock_in": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {new_credit: "nonzero", loan_interest: "nonzero"},
            "statistics": {new_credit: "cumulative", loan_interest: "cumulative"},
            "rationale": "Keeping an active loan with its creditor prevents costless relationship reassignment and should alter refinancing, origination, and interest flows.",
        },
        "config.bank_runs": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {run_flight: "decrease"},
            "statistics": {run_flight: "cumulative"},
            "activation": "bank_run_pressure",
            "rationale": "A shared weak-bank health state creates depositor flight; disabling runs must remove that flow while retaining ordinary interbank settlement.",
        },
        "config.bank_search_m": {
            "status": "screening_ready",
            "values": (1, 8),
            "directions": {loan_interest: "decrease"},
            "statistics": {loan_interest: "cumulative"},
            "rationale": "Sampling more rival lenders should weakly lower the rate selected by borrowers when bank spreads differ.",
        },
        "config.bank_spread_disp": {
            "status": "screening_ready",
            "values": (0.0, 1.0e-4),
            "directions": {loan_interest: "decrease"},
            "statistics": {loan_interest: "cumulative"},
            "rationale": "With rate competition active, greater mean-zero loan-spread dispersion gives searching borrowers access to cheaper lenders, while concentration and credit spillovers remain empirical.",
        },
        "config.deposit_interest_arrears": {
            "status": "activation_scenario_required",
            "values": (True,),
            "directions": {deposit_arrears: "increase"},
            "activation": "deposit_arrears_pressure",
            "rationale": "When contractual deposit interest exceeds current bank cash, enabling the memo account must preserve the unpaid obligation instead of silently discarding it.",
        },
        "config.deposit_rate": {
            "status": "screening_ready",
            "values": (1.34e-4,),
            "directions": {deposit_paid: "increase", bank_capital: "decrease"},
            "statistics": {deposit_paid: "cumulative"},
            "rationale": "A positive contractual deposit rate raises bank funding expense and depositor income, reducing bank capital before general-equilibrium feedbacks.",
        },
        "config.deposit_rate_disp": {
            "status": "screening_ready",
            "values": (1.0e-4,),
            "directions": {interbank_volume: "nonzero"},
            "statistics": {interbank_volume: "cumulative"},
            "rationale": "Heterogeneous deposit offers cause households to migrate across banks and therefore alter reserve settlement and interbank funding needs.",
        },
        "config.deposit_search_m": {
            "status": "activation_scenario_required",
            "values": (1, 8),
            "directions": {interbank_volume: "nonzero"},
            "statistics": {interbank_volume: "cumulative"},
            "activation": "deposit_spread_competition",
            "rationale": "Deposit search breadth is silent when all banks offer the same spread; shared dispersion identifies its effect on account migration and reserve flows.",
        },
        "config.hh_amort": {
            "status": "screening_ready",
            "values": (1.0 / (365.0 * 10.0), 1.0 / (365.0 * 2.5)),
            "directions": {principal_repaid: "increase", household_debt: "decrease"},
            "statistics": {principal_repaid: "cumulative"},
            "rationale": "Faster unsecured household-loan amortization should raise principal repayment and reduce the household debt stock, conditional on available cash.",
        },
        "config.hh_subsistence": {
            "status": "screening_ready",
            "values": (0.0, 1.0),
            "directions": {household_debt: "increase", new_credit: "increase"},
            "statistics": {new_credit: "cumulative"},
            "rationale": "A higher underwriting income floor gives liquidity-constrained households more room to borrow toward their planned consumption budget.",
        },
        "config.household_credit": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {household_debt: "decrease", new_credit: "decrease"},
            "statistics": {new_credit: "cumulative"},
            "rationale": "Disabling unsecured household credit should remove household loan balances and reduce aggregate originations while leaving firm credit active.",
        },
        "config.interbank": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {interbank_volume: "decrease"},
            "statistics": {interbank_volume: "cumulative"},
            "activation": "deposit_spread_competition",
            "rationale": "Disabling reserve settlement and interbank funding should remove interbank loan volume; dependent runs and central-bank liquidity facilities close as a documented capability package.",
        },
        "config.interbank_rate_base": {
            "status": "activation_scenario_required",
            "values": (1.34e-4,),
            "directions": {interbank_rate: "increase"},
            "activation": "deposit_spread_competition",
            "rationale": "A larger exogenous money-market spread should raise the realized interbank rate whenever reserve deficits are funded.",
        },
        "config.interbank_tightness": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.005),
            "directions": {interbank_rate: "increase"},
            "activation": "deposit_spread_competition",
            "rationale": "A stronger tightness coefficient should raise the interbank rate in sessions with aggregate reserve demand relative to available surplus.",
        },
        "config.interest_by_deposits": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {"metric.economy.income_gini": "nonzero"},
            "rationale": "Allocating bank payout equally rather than in proportion to deposits changes who receives financial income; distribution, consumption, and output are equilibrium consequences.",
        },
        "config.monetary_direct_transmission": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {
                investment_target: "nonzero",
                service_reserved: "decrease",
                dscr_shortfall: "decrease",
                new_credit: "nonzero",
            },
            "statistics": {
                investment_target: "cumulative",
                service_reserved: "cumulative",
                dscr_shortfall: "cumulative",
                new_credit: "cumulative",
            },
            "activation": "monetary_tightening_pressure",
            "rationale": "At a shared above-neutral loan rate, disabling direct transmission removes the investment user-cost multiplier, household contractual-service cash reservation, and firm DSCR screen. All three demand and credit flows should therefore weakly increase relative to the enabled control.",
        },
        "config.investment_user_cost_elasticity": {
            "status": "activation_scenario_required",
            "values": (0.10, 1.0),
            "directions": {user_cost_multiplier: "decrease"},
            "statistics": {user_cost_multiplier: "post_burnin_mean"},
            "activation": "monetary_tightening_elasticity",
            "rationale": "With the expected real financing cost above its neutral benchmark, a larger absolute elasticity should reduce desired and realized investment more strongly.",
        },
        "config.investment_user_cost_multiplier_min": {
            "status": "activation_scenario_required",
            "values": (0.25, 0.75),
            "directions": {user_cost_multiplier: "increase"},
            "statistics": {user_cost_multiplier: "post_burnin_mean"},
            "activation": "monetary_tightening_pressure",
            "rationale": "Under a sufficiently tight monetary state, a higher lower bound truncates the contractionary user-cost response and therefore supports more investment.",
        },
        "config.investment_user_cost_multiplier_max": {
            "status": "activation_scenario_required",
            "values": (1.10, 2.0),
            "directions": {user_cost_multiplier: "increase"},
            "statistics": {user_cost_multiplier: "post_burnin_mean"},
            "activation": "monetary_easing_pressure",
            "rationale": "Under a below-neutral financing cost, a higher upper bound permits a larger expansionary investment response instead of clipping it at the ordinary cap.",
        },
        "config.investment_user_cost_floor": {
            "status": "activation_scenario_required",
            "values": (1.0e-4,),
            "directions": {user_cost_multiplier: "decrease"},
            "statistics": {user_cost_multiplier: "post_burnin_mean"},
            "activation": "monetary_zlb_pressure",
            "rationale": "At the zero lower bound with zero depreciation, raising the positive real-user-cost floor narrows the apparent easing gap and should reduce the expansionary investment multiplier while preserving finite values.",
        },
        "config.run_fear_persistence": {
            "status": "activation_scenario_required",
            "values": (0.50, 0.99),
            "directions": {run_flight: "increase"},
            "statistics": {run_flight: "cumulative"},
            "activation": "bank_run_fear_pressure",
            "rationale": "More persistent system-wide fear should sustain depositor flight after weak-bank withdrawals begin.",
        },
        "config.run_health_ref": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.30),
            "directions": {run_flight: "increase"},
            "statistics": {run_flight: "cumulative"},
            "activation": "bank_run_health_screen",
            "rationale": "A higher reference capital ratio makes the same bank balance sheet appear less healthy and should increase run pressure.",
        },
        "config.run_sensitivity": {
            "status": "activation_scenario_required",
            "values": (0.5, 16.0),
            "directions": {run_flight: "increase"},
            "statistics": {run_flight: "cumulative"},
            "activation": "bank_run_pressure",
            "rationale": "Conditional on weak bank health, a steeper depositor response should raise cumulative flight volume.",
        },
    }


def _government_contracts() -> Mapping[str, Mapping[str, Any]]:
    public_capital = "metric.source.m4.public_capital"
    jg_capital = (
        "metric.source.m4.job_guarantee_public_capital_formation"
    )
    jg_productivity = "metric.source.m4.job_guarantee_realized_productivity"
    output = "metric.economy.na.real_gdp_per_capita"
    unemployment = "metric.economy.unemployment_rate"
    return {
        "config.jg_productivity": {
            "status": "activation_scenario_required",
            "values": (0.25, 0.75),
            "horizon_days": 365,
            "directions": {
                jg_productivity: "increase",
                jg_capital: "ambiguous",
                public_capital: "ambiguous",
                output: "ambiguous",
            },
            "statistics": {
                jg_productivity: "post_burnin_mean",
                jg_capital: "cumulative",
            },
            "activation": "active_job_guarantee_public_works",
            "rationale": "With a common active employer-of-last-resort programme and a full public-works allocation, the direct causal contract is capital formed per unit of assigned residual labor. Gross formation, public capital, and GDP remain reported but are not assigned a universal sign because employment and labor-market feedback can offset the engineering coefficient. Productive construction is valued at wage cost in national accounts and augments the public-capital stock.",
        },
        "config.public_capital_depreciation": {
            "status": "screening_ready",
            "values": (5.7e-5, 9.12e-4),
            "horizon_days": 1095,
            "directions": {
                public_capital: "decrease",
                output: "ambiguous",
                unemployment: "ambiguous",
            },
            "rationale": "Faster physical decay should reduce the public-capital stock accumulated from the same investment rule. Output and employment remain general-equilibrium outcomes because public capital raises productivity while demand determines planned production.",
        },
        "config.public_capital_gamma": {
            "status": "screening_ready",
            "values": (0.0, 0.20),
            "horizon_days": 1095,
            "directions": {
                output: "nonzero",
                unemployment: "nonzero",
            },
            "rationale": "The public-capital elasticity scales the economy-wide productivity service produced by a given infrastructure stock. It should alter real activity without directly changing the law of motion for the stock itself.",
        },
    }


def _housing_contracts() -> Mapping[str, Mapping[str, Any]]:
    price = "metric.source.m8.housing.house_price"
    rent = "metric.source.m8.housing.rent_level"
    stock = "metric.source.m8.housing.housing_stock"
    listings = "metric.source.m8.housing.active_listings"
    forced = "metric.source.m8.housing.forced_listing_share"
    sales = "metric.source.m8.housing.session_sales"
    volume = "metric.source.m8.housing.session_volume"
    mortgages = "metric.source.m8.housing.mortgage_originations"
    mortgage_principal = (
        "metric.source.m8.housing.mortgage_principal_outstanding"
    )
    rent_paid = "metric.source.m8.housing.rent_paid"
    evictions = "metric.source.m8.housing.evictions"
    construction = "metric.source.m8.housing.construction_output"
    completions = "metric.source.m8.housing.dwellings_completed"
    leave_multiplier = "metric.source.m8.housing.leave_home_multiplier"
    fertility_multiplier = "metric.source.m8.housing.fertility_multiplier"
    common_construction = {
        "status": "activation_scenario_required",
        "activation": "housing_shortage",
    }
    return {
        "config.builder_demand_price_gain": {
            **common_construction,
            "values": (0.5, 2.0),
            "directions": {construction: "nonzero"},
            "rationale": "When households face an uncovered dwelling shortage, a larger price-to-income demand gain should raise developers' expected sales and construction rather than leave supply disconnected from scarcity.",
        },
        "config.builder_demand_seed": {
            **common_construction,
            "values": (0.02,),
            "directions": {construction: "nonzero"},
            "statistics": {construction: "cumulative"},
            "rationale": "The cold-start demand seed should move early developer production under the same housing shortage. It is screened as an initialization channel, not interpreted as permanent autonomous demand.",
        },
        "config.builder_inventory_buffer": {
            **common_construction,
            "values": (0.25, 1.0),
            "directions": {construction: "nonzero"},
            "rationale": "Allowing developers to carry a larger finished-unit buffer should support more construction before sales arrive, at the cost of a larger vacant inventory exposure.",
        },
        "config.builder_land_fee_credit": {
            **common_construction,
            "values": (False,),
            "directions": {completions: "decrease"},
            "statistics": {completions: "cumulative"},
            "rationale": "Disabling development credit for the land fee should reduce completed dwellings when otherwise viable builders cannot fund the fee from cash alone.",
        },
        "config.builder_productivity": {
            **common_construction,
            "values": (0.001, 0.008),
            "directions": {construction: "increase"},
            "rationale": "Higher construction labor productivity should turn the same builder workforce into more work in progress and completed dwellings.",
        },
        "config.house_price_income_years": {
            "status": "screening_ready",
            "values": (2.0, 6.0),
            "directions": {price: "increase"},
            "statistics": {price: "first_window_mean"},
            "rationale": "The opening price-to-income multiple anchors the initial dwelling valuation. A higher multiple must raise the opening house-price path; persistence is measured separately rather than assumed to wash out.",
        },
        "config.housing_ask_decay": {
            "status": "activation_scenario_required",
            "values": (0.001, 0.05),
            "activation": "housing_liquid_market",
            "directions": {price: "decrease"},
            "rationale": "Faster markdown of stale listings should lower transaction prices and shorten the distance between sellers and constrained buyers.",
        },
        "config.housing_ask_markup": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.20),
            "activation": "housing_liquid_market",
            "directions": {price: "increase"},
            "rationale": "A larger voluntary asking markup should raise the transaction-price path conditional on sales, while turnover remains an equilibrium response.",
        },
        "config.housing_buyer_buffer": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.50),
            "activation": "housing_liquid_market",
            "directions": {sales: "decrease", mortgages: "decrease"},
            "statistics": {sales: "cumulative", mortgages: "cumulative"},
            "rationale": "A larger post-purchase liquidity reserve makes fewer households able to bid and borrow, so transactions and mortgage originations should fall.",
        },
        "config.housing_construction_enabled": {
            **common_construction,
            "values": (False,),
            "directions": {construction: "decrease", completions: "decrease"},
            "statistics": {construction: "cumulative", completions: "cumulative"},
            "rationale": "Disabling residential construction must eliminate construction output and new completions even when a common dwelling shortage creates demand.",
        },
        "config.housing_distress_floor": {
            "status": "screening_ready",
            "values": (0.0,),
            "directions": {forced: "increase", listings: "increase"},
            "rationale": "A higher deposit distress threshold should force more owner-occupiers to list and therefore expand the distressed share of active supply.",
        },
        "config.housing_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {stock: "decrease", rent_paid: "decrease"},
            "statistics": {rent_paid: "cumulative"},
            "rationale": "The parent housing capability should remove the dwelling registry and every dependent resale, mortgage, rental, and construction flow through the validated closure.",
        },
        "config.housing_fertility_elasticity": {
            "status": "activation_scenario_required",
            "values": (0.0, 2.0),
            "horizon_days": 1095,
            "activation": "housing_affordability_pressure",
            "directions": {fertility_multiplier: "decrease"},
            "statistics": {fertility_multiplier: "last_window_mean"},
            "rationale": "After a common affordability baseline is established, a larger fertility elasticity should translate worsening housing costs into a lower fertility multiplier.",
        },
        "config.housing_fertility_mult_hi": {
            "status": "activation_scenario_required",
            "values": (1.0,),
            "horizon_days": 1095,
            "activation": "housing_affordability_relief",
            "directions": {fertility_multiplier: "increase"},
            "statistics": {fertility_multiplier: "last_window_mean"},
            "rationale": "Under improving affordability, lowering the upper clamp to one should prevent the fertility multiplier from rising above neutrality.",
        },
        "config.housing_fertility_mult_lo": {
            "status": "activation_scenario_required",
            "values": (0.99,),
            "horizon_days": 1095,
            "activation": "housing_affordability_pressure",
            "directions": {fertility_multiplier: "increase"},
            "statistics": {fertility_multiplier: "last_window_mean"},
            "rationale": "Under worsening affordability, raising the lower clamp should bound the maximum fertility penalty and lift the resulting multiplier.",
        },
        "config.housing_forced_discount": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.30),
            "activation": "housing_distressed_market",
            "directions": {volume: "nonzero"},
            "statistics": {volume: "cumulative"},
            "rationale": "The forced-sale discount must change distressed transaction value. Its aggregate-volume sign is not fixed because a lower price also lets more constrained buyers clear; forced trades deliberately do not rebase the representative house-price index.",
        },
        "config.housing_leave_elasticity": {
            "status": "activation_scenario_required",
            "values": (0.0, 3.0),
            "horizon_days": 1095,
            "activation": "housing_affordability_pressure",
            "directions": {leave_multiplier: "decrease"},
            "statistics": {leave_multiplier: "last_window_mean"},
            "rationale": "A larger leaving-home elasticity should translate worsening rent and price affordability into a lower rate multiplier for household formation.",
        },
        "config.housing_leave_mult_hi": {
            "status": "activation_scenario_required",
            "values": (1.0,),
            "horizon_days": 1095,
            "activation": "housing_affordability_relief",
            "directions": {leave_multiplier: "increase"},
            "statistics": {leave_multiplier: "last_window_mean"},
            "rationale": "Under improving affordability, lowering the upper clamp to one should remove the positive leaving-home response above neutrality.",
        },
        "config.housing_leave_mult_lo": {
            "status": "activation_scenario_required",
            "values": (0.99,),
            "horizon_days": 1095,
            "activation": "housing_affordability_pressure",
            "directions": {leave_multiplier: "increase"},
            "statistics": {leave_multiplier: "last_window_mean"},
            "rationale": "Under worsening affordability, raising the lower clamp should bound the reduction in household formation.",
        },
        "config.housing_market_enabled": {
            "status": "activation_scenario_required",
            "values": (False,),
            "activation": "housing_liquid_market",
            "directions": {sales: "decrease", volume: "decrease", mortgages: "decrease"},
            "statistics": {sales: "cumulative", volume: "cumulative", mortgages: "cumulative"},
            "rationale": "Disabling resale clearing should eliminate sales, transfer value, and purchase-mortgage originations while leaving the housing stock itself intact.",
        },
        "config.housing_rental_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {rent_paid: "decrease"},
            "statistics": {rent_paid: "cumulative"},
            "rationale": "Disabling the rental institution should eliminate rent settlements and rental evictions without deleting dwellings.",
        },
        "config.housing_search_k": {
            "status": "activation_scenario_required",
            "values": (1,),
            "activation": "housing_search_friction",
            "directions": {sales: "increase"},
            "statistics": {sales: "cumulative"},
            "rationale": "A broader buyer search set should weakly increase successful matches by exposing each buyer to more active listings.",
        },
        "config.housing_session_interval": {
            "status": "activation_scenario_required",
            "values": (7, 90),
            "activation": "housing_liquid_market",
            "directions": {sales: "decrease"},
            "statistics": {sales: "cumulative"},
            "rationale": "Less frequent market sessions should reduce the number of opportunities to transact within a fixed calendar horizon.",
        },
        "config.mortgage_enabled": {
            "status": "activation_scenario_required",
            "values": (False,),
            "activation": "housing_liquid_market",
            "directions": {mortgages: "decrease", mortgage_principal: "decrease"},
            "statistics": {mortgages: "cumulative"},
            "rationale": "Disabling mortgage finance should eliminate originations and mortgage principal while retaining cash purchases.",
        },
        "config.rent_adjust": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.20),
            "activation": "housing_rental_pressure",
            "directions": {rent: "nonzero"},
            "statistics": {rent: "post_burnin_volatility"},
            "rationale": "The partial rent-adjustment coefficient should change rent dynamics when vacancies or unmet tenant demand create pressure; the level sign depends on that pressure.",
        },
        "config.rent_burden_cap": {
            "status": "screening_ready",
            "values": (0.10,),
            "directions": {rent: "increase"},
            "rationale": "A higher wage-relative rent ceiling relaxes the affordability cap and should permit a higher rent path when the ceiling binds.",
        },
        "config.rent_yield0": {
            "status": "screening_ready",
            "values": (0.02, 0.10),
            "directions": {rent: "increase"},
            "statistics": {rent: "first_window_mean"},
            "rationale": "The opening rental yield maps the house-price anchor into initial daily rent, so a higher yield must raise the first rent window.",
        },
        "config.rental_investor_premium": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.10),
            "activation": "housing_investor_choice",
            "directions": {listings: "increase"},
            "rationale": "A larger return premium makes holding a vacant rental less attractive relative to deposits, causing more investor-owned vacancies to be offered for sale.",
        },
    }


def _energy_contracts() -> Mapping[str, Mapping[str, Any]]:
    production = "metric.source.m8.energy.production"
    capacity = "metric.source.m8.energy.capacity"
    producer_capital = "metric.source.m8.energy.producer_capital"
    utilization = "metric.source.m8.energy.utilization"
    requested_households = "metric.source.m8.energy.requested_households"
    requested_industry = "metric.source.m8.energy.requested_industry"
    household_spending = "metric.source.m8.energy.household_spending"
    industry_spending = "metric.source.m8.energy.industry_spending"
    unfilled = "metric.source.m8.energy.unfilled"
    mortality_multiplier = (
        "metric.source.m8.energy.fuel_poverty_mortality_multiplier"
    )
    coverage = "metric.economy.energy_coverage_mean"
    energy_labor = "metric.economy.labor_sector_energy_fte"
    investment = "metric.source.m4.fixed_capital_formation_real"
    deaths = "metric.source.m7.deaths"
    return {
        "config.case-a_e": {
            "status": "screening_ready",
            "values": (0.70, 1.40),
            "directions": {energy_labor: "decrease", production: "nonzero"},
            "rationale": "Energy-sector labor productivity determines how much output each effective worker can produce. Higher productivity should reduce the labor required for a given production plan and relax labor-side supply constraints; the realized production response remains a market-clearing outcome.",
        },
        "config.case-kappa_e": {
            "status": "screening_ready",
            "values": (0.60, 1.60),
            "directions": {
                producer_capital: "decrease",
                investment: "nonzero",
            },
            "horizon_days": 365,
            "rationale": "Energy capital productivity maps installed physical capital into capacity. A higher coefficient should require less physical investment to support a given capacity path, while demand and producer adjustment determine the equilibrium capacity response.",
        },
        "config.energy_coverage_ticks": {
            "status": "screening_ready",
            "values": (3, 30),
            "directions": {coverage: "increase", requested_industry: "increase"},
            "statistics": {requested_industry: "first_window_mean"},
            "rationale": "The downstream coverage target is the number of production days that firms aim to hold as energy inputs. A larger buffer should raise desired industry purchases and eventually increase observed input coverage, especially while stocks are being accumulated.",
        },
        "config.energy_enabled": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {production: "decrease", requested_industry: "decrease"},
            "rationale": "The parent capability removes the explicit energy-producing sector, energy input orders, household energy purchases, and deprivation accounting. It is a structural model switch rather than an ordinary policy lever.",
        },
        "config.energy_gap_close": {
            "status": "activation_scenario_required",
            "values": (0.001, 0.20),
            "activation": "energy_inventory_gap",
            "directions": {requested_industry: "nonzero", production: "nonzero"},
            "statistics": {
                requested_industry: "first_window_mean",
                production: "first_window_mean",
            },
            "rationale": "The gap-closing speed determines how aggressively downstream firms and producers rebuild energy stocks toward their targets. Under a shared inventory disturbance it must change both input orders and replenishment production, but a larger coefficient can either close shortages faster or create overshoot and financing pressure, so the equilibrium level sign is not imposed.",
        },
        "config.energy_hh_share": {
            "status": "screening_ready",
            "values": (0.03, 0.14),
            "directions": {
                requested_households: "increase",
                household_spending: "increase",
            },
            "statistics": {
                requested_households: "first_window_mean",
                household_spending: "cumulative",
            },
            "rationale": "This Config value is the representative household energy budget share. The native bridge converts it into physical need at the opening wage and energy price, so a larger share should raise household energy orders and spending before affordability and rationing feedbacks.",
        },
        "config.energy_hoarding_beta": {
            "status": "activation_scenario_required",
            "values": (0.0, 5.0),
            "activation": "energy_rising_price",
            "directions": {requested_industry: "increase", unfilled: "nonzero"},
            "statistics": {
                requested_industry: "first_window_mean",
                unfilled: "first_window_mean",
            },
            "rationale": "The hoarding coefficient amplifies firms' desired coverage only when the current energy price exceeds its slow reference. Under a shared rising-price episode, a larger coefficient should raise precautionary industry orders and can intensify unmet demand.",
        },
        "config.energy_household": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                requested_households: "decrease",
                household_spending: "decrease",
            },
            "statistics": {household_spending: "cumulative"},
            "rationale": "This capability decides whether households directly purchase the explicit energy good. Disabling it should eliminate household energy orders and payments while leaving industrial energy use active.",
        },
        "config.energy_intensity": {
            "status": "screening_ready",
            "values": (0.01, 0.12),
            "directions": {
                requested_industry: "increase",
                industry_spending: "increase",
            },
            "statistics": {
                requested_industry: "first_window_mean",
                industry_spending: "cumulative",
            },
            "rationale": "Energy intensity is the physical energy input required per unit of planned downstream production. Raising it should increase firms' energy orders and input expenditure, with output and employment effects determined by supply availability and financing.",
        },
        "config.energy_mortality_gamma": {
            "status": "activation_scenario_required",
            "values": (0.0, 4.0),
            "activation": "energy_mortality_pressure",
            "horizon_days": 730,
            "directions": {mortality_multiplier: "increase", deaths: "increase"},
            "statistics": {
                mortality_multiplier: "last_window_mean",
                deaths: "cumulative",
            },
            "rationale": "This elasticity translates the share of people receiving less than the fuel-poverty energy threshold into an excess mortality hazard. Under a common persistent energy-access shortfall, a larger elasticity should raise both the published hazard multiplier and realized deaths, subject to the safety cap.",
        },
        "config.energy_mortality_mult_hi": {
            "status": "activation_scenario_required",
            "values": (1.0, 2.0),
            "activation": "energy_mortality_cap_binding",
            "horizon_days": 730,
            "directions": {mortality_multiplier: "increase", deaths: "increase"},
            "statistics": {
                mortality_multiplier: "last_window_mean",
                deaths: "cumulative",
            },
            "rationale": "The mortality ceiling limits how strongly fuel poverty can amplify ordinary age-specific death hazards. When a shared energy crisis makes the unconstrained multiplier exceed the baseline cap, relaxing the ceiling should raise the effective hazard and cumulative deaths.",
        },
        "config.energy_util0": {
            "status": "screening_ready",
            "values": (0.55, 1.0),
            "directions": {utilization: "increase", capacity: "decrease"},
            "statistics": {
                utilization: "first_window_mean",
                capacity: "first_window_mean",
            },
            "rationale": "Despite its legacy name, this value is reused as the producer's desired capacity-utilization target, not merely as an opening seed. A higher target should support the same planned supply with less reserve capacity and therefore raise realized utilization while lowering required capacity in the initial adjustment window.",
        },
    }


def _open_economy_contracts() -> Mapping[str, Mapping[str, Any]]:
    imports = "metric.source.m9.country.imports_volume"
    iceberg = "metric.source.m9.country.iceberg_loss"
    exchange_rate = "metric.source.m9.country.exchange_rate"
    capital_flow = "metric.source.m9.country.capital_flow"
    hosted = "metric.source.m9.country.migrant_stock_hosted"
    remittances_sent = "metric.source.m9.country.remittances_sent"
    peg_reserves = "metric.source.m9.country.peg_reserves"
    mutualization = "metric.source.m9.country.fx_mutualization_paid"
    spread_revenue = "metric.source.m9.world.dealer_spread_revenue"
    trade_routes = "metric.source.m9.world.trade_routes"
    return {
        "config.world.capital": {
            "status": "activation_scenario_required",
            "values": (False,),
            "activation": "world_capital_rate_gap",
            "directions": {capital_flow: "decrease"},
            "statistics": {capital_flow: "cumulative"},
            "rationale": "The capital-account capability allows funds to move from lower-yield economies toward higher-yield borrowers. With a shared cross-country policy-rate gap, disabling it should eliminate the resulting gross external lending flow and the associated foreign-asset positions.",
        },
        "config.world.capital_adjust": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.50),
            "activation": "world_capital_rate_gap",
            "directions": {capital_flow: "increase"},
            "statistics": {capital_flow: "cumulative"},
            "rationale": "Capital adjustment is the speed at which investors close the gap between the current and desired cross-border position. A larger value should produce a larger cumulative inflow into the common high-rate economy over a fixed horizon.",
        },
        "config.world.capital_mobility": {
            "status": "activation_scenario_required",
            "values": (0.20, 0.80),
            "activation": "world_capital_rate_gap",
            "directions": {capital_flow: "increase"},
            "statistics": {capital_flow: "cumulative"},
            "rationale": "Capital mobility is the structural openness of the international financial account. Conditional on the same interest-rate differential and capital controls, greater mobility should scale up cross-border lending and borrowing.",
        },
        "config.world.fx_friction": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.15),
            "activation": "world_trade_friction",
            "directions": {iceberg: "increase"},
            "statistics": {iceberg: "cumulative"},
            "rationale": "The FX/trade friction is an iceberg transport cost: exporters must ship more physical goods than importers receive. Raising it should destroy more goods in transit and reduce delivered import volume, all else equal.",
        },
        "config.world.fx_lambda": {
            "status": "activation_scenario_required",
            "values": (0.01, 0.20),
            "activation": "world_trade_integration",
            "directions": {exchange_rate: "nonzero"},
            "statistics": {exchange_rate: "post_burnin_volatility"},
            "rationale": "The exchange-rate adjustment coefficient controls how quickly currencies respond to the FX dealer's accumulated inventory imbalance. It should change exchange-rate dynamics under active trade, although the level sign depends on whether a country is initially a net importer or exporter.",
        },
        "config.world.fx_loss_mutualization": {
            "status": "activation_scenario_required",
            "values": (True,),
            "activation": "world_dealer_loss",
            "horizon_days": 730,
            "directions": {mutualization: "increase"},
            "statistics": {mutualization: "cumulative"},
            "rationale": "Dealer-loss mutualization makes member treasuries explicitly recapitalize a loss-making common FX clearing facility at the annual boundary. Enabling it should create observable fiscal levies when dealer valuation is negative instead of leaving that loss indefinitely unowned.",
        },
        "config.world.fx_spread": {
            "status": "activation_scenario_required",
            "values": (0.01,),
            "activation": "world_trade_integration",
            "directions": {spread_revenue: "increase"},
            "statistics": {spread_revenue: "cumulative"},
            "rationale": "The FX spread is the dealer's conversion wedge on imports and remittances. A positive spread should generate dealer revenue whenever cross-border conversions occur, while also making foreign transactions more expensive for residents.",
        },
        "config.world.fx_trade_cap": {
            "status": "activation_scenario_required",
            "values": (0.03, 0.30),
            "activation": "world_trade_integration",
            "directions": {imports: "increase", trade_routes: "increase"},
            "statistics": {
                imports: "cumulative",
                trade_routes: "cumulative",
            },
            "rationale": "The trade cap limits each economy's daily import reservation relative to domestic output. Relaxing it should allow more foreign goods to be delivered and more bilateral lots to clear while demand and export inventories remain available.",
        },
        "config.world.migration": {
            "status": "activation_scenario_required",
            "values": (False,),
            "activation": "world_migration_wage_gap",
            "directions": {hosted: "decrease", remittances_sent: "decrease"},
            "statistics": {
                hosted: "last_window_mean",
                remittances_sent: "cumulative",
            },
            "rationale": "The migration capability permits workers to relocate toward economies offering higher real wages. Disabling it should eliminate migrant stocks and the remittance payments generated by those workers under a shared wage gradient.",
        },
        "config.world.migration_max_share": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.40),
            "activation": "world_migration_cap_pressure",
            "directions": {hosted: "increase"},
            "statistics": {hosted: "last_window_mean"},
            "rationale": "This ceiling limits the fraction of an origin population that can remain abroad. Under a persistent wage gap and fast common migration response, a higher ceiling should permit a larger hosted migrant stock.",
        },
        "config.world.migration_rate": {
            "status": "activation_scenario_required",
            "values": (0.0001, 0.005),
            "activation": "world_migration_wage_gap",
            "directions": {hosted: "increase", remittances_sent: "increase"},
            "statistics": {
                hosted: "last_window_mean",
                remittances_sent: "cumulative",
            },
            "rationale": "The migration rate is the daily speed at which a real-wage advantage becomes an actual migrant stock. A faster response should raise both migrant employment hosted by the destination and the associated remittance outflow over a fixed horizon.",
        },
        "config.world.peg_reserves0": {
            "status": "activation_scenario_required",
            "values": (1_000.0, 20_000.0),
            "activation": "world_peg_pressure",
            "horizon_days": 180,
            "directions": {peg_reserves: "increase"},
            "statistics": {peg_reserves: "first_window_mean"},
            "rationale": "Initial peg reserves are the anchor-currency buffer available to defend a fixed exchange rate. Under identical external pressure, a larger opening reserve stock should leave more reserves after intervention and allow the peg to absorb a larger cumulative imbalance before breaking.",
        },
        "config.world.periods_per_year": {
            "status": "excluded_non_treatment",
            "values": (),
            "directions": {},
            "rationale": "The current product has an invariant civil calendar of 365 one-day ticks per year. The legacy twelve-period seed is deliberately replaced by 365 at the native bridge and is not a playable structural treatment.",
        },
        "config.world.remittance_share": {
            "status": "activation_scenario_required",
            "values": (0.05, 0.50),
            "activation": "world_migration_wage_gap",
            "directions": {remittances_sent: "increase"},
            "statistics": {remittances_sent: "cumulative"},
            "rationale": "The remittance share is the fraction of migrant labor income workers attempt to send back to their origin economy. Raising it should increase gross remittance outflows from the host, subject to available household cash and conversion taxes.",
        },
        "config.world.trade": {
            "status": "activation_scenario_required",
            "values": (False,),
            "activation": "world_trade_integration",
            "directions": {
                imports: "decrease",
                trade_routes: "decrease",
            },
            "statistics": {
                imports: "cumulative",
                trade_routes: "cumulative",
            },
            "rationale": "The trade capability connects domestic goods markets through cross-border reservation and settlement. Disabling it should eliminate imports, exports, iceberg losses, and trade routes while leaving each domestic economy operational.",
        },
        "config.world.wage_smoothing": {
            "status": "activation_scenario_required",
            "values": (0.005, 0.20),
            "activation": "world_migration_wage_gap",
            "directions": {hosted: "increase"},
            "statistics": {hosted: "first_window_mean"},
            "rationale": "Migration responds to a smoothed cross-country real-wage signal. A larger smoothing gain incorporates a newly present wage gap faster and should therefore accelerate early migration toward the common high-wage destination.",
        },
    }


def _securities_contracts() -> Mapping[str, Mapping[str, Any]]:
    household_bonds = "metric.source.m6.household_bond_market_value"
    bank_bonds = "metric.source.m6.bank_bond_market_value"
    firm_cap = "metric.source.m6.firm_equity_market_cap"
    bank_cap = "metric.source.m6.bank_equity_market_cap"
    firm_turnover = "metric.source.m6.firm_equity_turnover"
    bank_turnover = "metric.source.m6.bank_equity_turnover"
    firm_fundamental = "metric.source.m6.firm_equity_fundamental_value"
    bank_fundamental = "metric.source.m6.bank_equity_fundamental_value"
    issuance = "metric.source.m6.primary_equity_raised"
    margin = "metric.source.m6.margin_principal"
    margin_flow = "metric.source.m6.margin_originated"
    equity_gini = "metric.economy.equity_ownership_gini"
    q_ema = "metric.source.m6.mean_tobin_q_ema"
    q_multiplier = "metric.source.m6.mean_q_investment_multiplier"
    q_target = "metric.source.m6.q_adjusted_investment_target"
    equity_wealth_ema = "metric.source.m6.household_equity_wealth_ema"
    equity_consumption = (
        "metric.source.m6.household_equity_consumption_addition"
    )
    return {
        "config.bank_bond_appetite": {
            "status": "screening_ready",
            "values": (0.0, 0.15),
            "directions": {bank_bonds: "increase"},
            "rationale": "A larger bank appetite should shift more of the active government-bond book onto bank balance sheets. Household holdings and aggregate issuance remain equilibrium outcomes because investors compete for the same supply.",
        },
        "config.bank_equity": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                bank_cap: "decrease",
                bank_turnover: "decrease",
                "metric.source.m6.household_bank_equity_market_value": "decrease",
            },
            "rationale": "Removing bank ownership should eliminate bank-stock contracts, their household claims, and their secondary-market turnover. The valid capability closure also disables bank-equity trading and de-novo bank entry.",
        },
        "config.bank_equity_lambda": {
            "status": "screening_ready",
            "values": (0.0005, 0.01),
            "directions": {bank_fundamental: "nonzero"},
            "statistics": {bank_fundamental: "post_burnin_volatility"},
            "rationale": "The bank earnings-signal gain controls how quickly stock fundamentals absorb realized bank income. A faster gain should change the variability of aggregate fundamental value; its level sign depends on the income path.",
        },
        "config.bank_equity_trading": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {bank_turnover: "decrease"},
            "rationale": "Disabling the secondary bank-stock market should remove household bank-equity turnover while retaining bank ownership and mark-to-model fundamentals.",
        },
        "config.bank_theta_equity": {
            "status": "screening_ready",
            "values": (0.02, 0.25),
            "directions": {bank_turnover: "nonzero", bank_cap: "increase"},
            "statistics": {bank_turnover: "first_window_mean"},
            "rationale": "A larger desired bank-equity wealth share should create additional net demand, turnover, and upward price pressure during portfolio adjustment.",
        },
        "config.bond_theta": {
            "status": "screening_ready",
            "values": (0.02, 0.40),
            "directions": {household_bonds: "increase"},
            "rationale": "A larger household bond target should increase household government-bond holdings when deficit-financed supply is active.",
        },
        "config.bonds": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.source.m6.bond_outstanding_face": "decrease",
                household_bonds: "decrease",
                bank_bonds: "decrease",
            },
            "rationale": "Removing the bond capability should eliminate issuance and both household and bank government-bond positions. Dependent central-bank quantity facilities close with the capability.",
        },
        "config.equity_finance": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {issuance: "decrease"},
            "statistics": {issuance: "cumulative"},
            "rationale": "Disabling primary equity finance should remove firms' sale of new shares while preserving the secondary stock market.",
        },
        "config.equity_ema_lambda": {
            "status": "activation_scenario_required",
            "values": (0.001, 0.10),
            "directions": {equity_wealth_ema: "nonzero"},
            "statistics": {equity_wealth_ema: "post_burnin_volatility"},
            "activation": "active_equity_wealth_signal",
            "horizon_days": 180,
            "rationale": "The household equity-wealth EMA must react more quickly to a moving marked-to-market portfolio when its gain is raised. The level sign is path-dependent, so the direct dynamic statistic is volatility rather than an imposed macro sign.",
        },
        "config.founder_owned_genesis": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {equity_gini: "decrease"},
            "rationale": "Diffuse genesis ownership should reduce concentration relative to vesting each initial firm in a small founder class. This is a persistent ownership institution, not a shock expected to wash out mechanically.",
        },
        "config.lambda_p": {
            "status": "screening_ready",
            "values": (0.03, 0.25),
            "directions": {firm_cap: "nonzero"},
            "statistics": {firm_cap: "post_burnin_volatility"},
            "rationale": "The market-impact gain controls how strongly a given order imbalance moves prices. A larger gain should alter market-cap volatility, while the equilibrium price level is not assigned a sign.",
        },
        "config.lambda_q": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.25),
            "directions": {
                q_multiplier: "increase",
                q_target: "increase",
            },
            "statistics": {
                q_multiplier: "first_window_mean",
                q_target: "first_window_mean",
            },
            "activation": "active_q_investment_gap",
            "horizon_days": 90,
            "rationale": "With positive accelerator demand and q above one, a larger Tobin-q sensitivity must raise the pre-credit physical investment target and the multiplier visible to the financing stage.",
        },
        "config.margin_credit": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {margin: "decrease", margin_flow: "decrease"},
            "statistics": {margin_flow: "cumulative"},
            "rationale": "Removing margin lending should eliminate equity-backed household credit balances and originations. The dependent bankruptcy rule closes because there is no margin debt to discharge.",
        },
        "config.per_firm_equity": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {firm_cap: "decrease", firm_turnover: "decrease"},
            "rationale": "Removing per-firm stock contracts should eliminate firm market capitalization and trading. Equity finance, margin lending, founder vesting, and pro-rata dividends close as a documented capability package.",
        },
        "config.portfolio_adjust": {
            "status": "screening_ready",
            "values": (0.01, 0.20),
            "directions": {firm_turnover: "increase"},
            "statistics": {firm_turnover: "first_window_mean"},
            "rationale": "A faster partial-adjustment coefficient should move a larger fraction of each household's portfolio gap during the initial rebalancing window.",
        },
        "config.q_invest_cap": {
            "status": "activation_scenario_required",
            "values": (1.01,),
            "directions": {q_multiplier: "increase", q_target: "increase"},
            "statistics": {
                q_multiplier: "first_window_mean",
                q_target: "first_window_mean",
            },
            "activation": "q_investment_cap_pressure",
            "horizon_days": 90,
            "rationale": "Under a deliberately strong positive-q signal, the upper bound must visibly cap the valuation multiplier. Raising the cap should transmit more of the same q signal into planned real investment.",
        },
        "config.q_invest_floor": {
            "status": "activation_scenario_required",
            "values": (0.95,),
            "directions": {q_multiplier: "increase"},
            "statistics": {q_multiplier: "post_burnin_mean"},
            "activation": "q_investment_floor_pressure",
            "horizon_days": 180,
            "rationale": "A high-volatility equity path produces a cross-section of firms below q=1. A higher crash floor must prevent their investment multiplier from falling as far and thereby preserve more planned investment.",
        },
        "config.q_invest_smooth": {
            "status": "activation_scenario_required",
            "values": (0.01, 0.25),
            "directions": {q_ema: "nonzero"},
            "statistics": {q_ema: "first_window_mean"},
            "activation": "active_q_investment_gap",
            "horizon_days": 90,
            "rationale": "The q EMA gain controls the response lag between market valuation and the signal used by next-day investment. A slow and an instantaneous signal must produce distinct direct q paths under the same moving market.",
        },
        "config.resid_income_lambda": {
            "status": "screening_ready",
            "values": (0.0005, 0.01),
            "directions": {firm_fundamental: "nonzero"},
            "statistics": {firm_fundamental: "post_burnin_volatility"},
            "rationale": "The residual-income gain controls how quickly firm fundamentals incorporate earnings surprises. Its effect on the fundamental level is state-dependent, but its dynamic effect must be observable.",
        },
        "config.shares_per_firm": {
            "status": "invariance_activation_required",
            "values": (50.0, 200.0),
            "directions": {
                firm_cap: "invariance",
                firm_fundamental: "invariance",
                "metric.economy.real_output": "invariance",
            },
            "rationale": "Shares per firm is a denomination choice. Splitting the same corporate claim into more units should rescale price per share but leave aggregate market value, fundamentals, and the real economy unchanged.",
        },
        "config.theta_equity": {
            "status": "screening_ready",
            "values": (0.10, 0.60),
            "directions": {firm_cap: "increase", firm_turnover: "nonzero"},
            "statistics": {
                firm_cap: "first_window_mean",
                firm_turnover: "first_window_mean",
            },
            "rationale": "A larger desired household equity share should create additional demand and upward price pressure while portfolios move toward the new allocation.",
        },
        "config.trend_lambda": {
            "status": "activation_scenario_required",
            "values": (0.005, 0.10),
            "directions": {firm_cap: "nonzero"},
            "statistics": {firm_cap: "post_burnin_volatility"},
            "activation": "active_chartist_demand",
            "rationale": "Faster trend learning changes the momentum signal seen by chartist demand. The stable product baseline deliberately keeps chartist demand weak, so the learning-speed mechanism is identified under a shared high-chartist activation rather than expected to manufacture a bubble on its own.",
        },
        "config.valuation_discount_floor": {
            "status": "screening_ready",
            "values": (0.001,),
            "directions": {firm_fundamental: "decrease", bank_fundamental: "decrease"},
            "rationale": "A binding higher required-return floor reduces the present value of residual firm income and bank earnings, holding book values fixed.",
        },
        "config.valuation_risk_premium": {
            "status": "screening_ready",
            "values": (0.00005, 0.00050),
            "directions": {firm_fundamental: "decrease", bank_fundamental: "decrease"},
            "rationale": "A larger valuation risk premium raises the required return and should lower capitalized firm residual income and bank earnings.",
        },
        "config.w_chartist": {
            "status": "screening_ready",
            "values": (0.0, 20.0),
            "directions": {firm_cap: "nonzero"},
            "statistics": {firm_cap: "post_burnin_volatility"},
            "rationale": "Chartist weight scales momentum-following demand. The upper treatment uses the repository's established bubble-regime dose so the experiment compares a stable market with an economically material momentum-feedback regime.",
        },
        "config.w_fundamental": {
            "status": "screening_ready",
            "values": (0.25, 2.0),
            "directions": {firm_cap: "nonzero"},
            "statistics": {firm_cap: "post_burnin_volatility"},
            "rationale": "Fundamentalist weight scales the demand response to value-price gaps. It should change price correction dynamics without imposing a one-sided market-cap level effect.",
        },
        "config.watchlist_size": {
            "status": "screening_ready",
            "values": (1, 16),
            "directions": {equity_gini: "decrease", firm_turnover: "nonzero"},
            "statistics": {firm_turnover: "first_window_mean"},
            "rationale": "A broader permanent investment opportunity set should diversify household firm ownership and alter secondary-market turnover. It is a persistent market-structure treatment, not a transient opening shock.",
        },
        "config.wealth_effect": {
            "status": "screening_ready",
            "values": (0.10, 0.50),
            "directions": {equity_consumption: "increase"},
            "statistics": {equity_consumption: "cumulative"},
            "horizon_days": 90,
            "rationale": "The wealth-effect coefficient weights committed smoothed household equity wealth in the next-day consumption budget. A positive treatment must create a positive direct budget addition; realized output and employment remain equilibrium outcomes because the extra desired spending can accelerate deposit drawdown.",
        },
    }


CURATED_CONTRACTS = {
    **_production_contracts(),
    **_firm_contracts(),
    **_consumption_contracts(),
    **_labor_contracts(),
    **_demography_contracts(),
    **_distribution_contracts(),
    **_banking_contracts(),
    **_government_contracts(),
    **_housing_contracts(),
    **_energy_contracts(),
    **_open_economy_contracts(),
    **_securities_contracts(),
}


def build_contract_registry() -> dict[str, Any]:
    inventory = build_audit_inventory()
    contracts: list[TreatmentContract] = []
    for row in inventory["rows"]:
        treatment_kind, suggested_values = _draft_treatment(row)
        override = CURATED_CONTRACTS.get(str(row["id"]), {})
        directions = dict(override.get("directions", {}))
        invalid = set(directions.values()) - DIRECTION_VALUES
        if invalid:
            raise ValueError(f"invalid expected directions for {row['id']}: {invalid}")
        module_metrics = tuple(
            override.get(
                "metrics", MODULE_PRIMARY_METRICS.get(str(row["module"]), ())
            )
        )
        primary_metrics = tuple(
            dict.fromkeys((*module_metrics, *directions.keys()))
        )
        contract = TreatmentContract(
            field_id=str(row["id"]),
            field_name=str(row["field_name"]),
            scope=("world" if row["declaring_type"] == "World" else "root"),
            module=str(row["module"]),
            experiment_role=str(row["experiment_role"]),
            route_status=str(row["route_status"]),
            baseline_value=row["playable_baseline"],
            status=str(override.get("status", _default_status(row))),
            treatment_kind=treatment_kind,
            treatment_values=tuple(override.get("values", suggested_values)),
            primary_metrics=primary_metrics,
            expected_directions=directions,
            direction_statistics=dict(override.get("statistics", {})),
            horizon_days=int(override.get("horizon_days", 365)),
            countries=(3 if row["declaring_type"] == "World" else 1),
            activation_scenario=str(override.get("activation", "neutral_baseline")),
            rationale=str(
                override.get(
                    "rationale",
                    "Automatically generated treatment suggestion; economic review is required before execution.",
                )
            ),
        )
        if contract.status in {
            "screening_ready",
            "activation_scenario_required",
            "invariance_activation_required",
        }:
            allowed_routes = (
                {"infrastructure_invariance", "mapped_native"}
                if contract.status == "invariance_activation_required"
                else {"mapped_native"}
            )
            if contract.route_status not in allowed_routes:
                raise ValueError(f"ready contract lacks a native route: {contract.field_id}")
            if not contract.treatment_values or not contract.primary_metrics:
                raise ValueError(f"ready contract is incomplete: {contract.field_id}")
            if set(contract.direction_statistics) - set(contract.expected_directions):
                raise ValueError(
                    f"direction statistic lacks an expectation: {contract.field_id}"
                )
        contracts.append(contract)

    status_counts: dict[str, int] = {}
    for contract in contracts:
        status_counts[contract.status] = status_counts.get(contract.status, 0) + 1
    return {
        "schema_version": "config-treatment-contracts-v1",
        "field_count": len(contracts),
        "status_counts": dict(sorted(status_counts.items())),
        "contracts": [asdict(contract) for contract in contracts],
    }


def screening_contracts(*, module: str | None = None) -> tuple[TreatmentContract, ...]:
    payload = build_contract_registry()
    output = []
    for raw in payload["contracts"]:
        if raw["status"] != "screening_ready":
            continue
        if module is not None and raw["module"] != module:
            continue
        output.append(TreatmentContract(**raw))
    return tuple(output)


def activation_contracts(*, module: str | None = None) -> tuple[TreatmentContract, ...]:
    """Return reviewed contracts that require a shared activation scenario."""
    payload = build_contract_registry()
    output = []
    for raw in payload["contracts"]:
        if raw["status"] != "activation_scenario_required":
            continue
        if module is not None and raw["module"] != module:
            continue
        output.append(TreatmentContract(**raw))
    return tuple(output)


def invariance_contracts(*, module: str | None = None) -> tuple[TreatmentContract, ...]:
    """Return reviewed measurement contracts with no economic feedback."""
    payload = build_contract_registry()
    output = []
    for raw in payload["contracts"]:
        if raw["status"] != "invariance_activation_required":
            continue
        if module is not None and raw["module"] != module:
            continue
        output.append(TreatmentContract(**raw))
    return tuple(output)
