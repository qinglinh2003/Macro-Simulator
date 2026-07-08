"""Shared visualization specifications for static PNGs and future Streamlit views."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PanelSpec:
    id: str
    title: str
    metrics: tuple[str, ...]
    question: str
    zero: bool = False
    one: bool = False


@dataclass(frozen=True)
class CategorySpec:
    id: str
    title: str
    panels: tuple[PanelSpec, ...]


@dataclass(frozen=True)
class RunArtifact:
    label: str
    version: str
    records: list[dict]
    series_path: Path
    metadata_path: Path


def _panel(
    id: str,
    title: str,
    metrics: Sequence[str],
    question: str,
    *,
    zero: bool = False,
    one: bool = False,
) -> PanelSpec:
    return PanelSpec(id=id, title=title, metrics=tuple(metrics), question=question, zero=zero, one=one)


DEFAULT_CATEGORIES: Mapping[str, CategorySpec] = {
    "overview": CategorySpec(
        id="overview",
        title="Overview",
        panels=(
            _panel("real_activity", "Real Activity", ("real_output", "real_consumption"),
                   "Are production and realized consumption moving together?"),
            _panel("labor_slack", "Labor Slack", ("unemployment_rate", "effective_unemployment"),
                   "Is unemployment private, policy-buffered, or both?"),
            _panel("prices", "Prices And Inflation", ("price_index", "inflation"),
                   "Is nominal instability building?"),
            _panel("fiscal_impulse", "Fiscal Impulse",
                   ("cash_deficit_to_gdp", "augmented_gov_spending_share_of_gdp"),
                   "How large is the broad fiscal impulse?", zero=True),
            _panel("bank_survival", "Bank Survival", ("banks_alive", "bank_economic_capital_min"),
                   "Is the banking sector surviving with enough economic capital?"),
            _panel("securities", "Securities Stock", ("bond_market_total", "bond_mtm_pnl"),
                   "Are security values large or producing duration losses?", zero=True),
            _panel("welfare", "Household Welfare", ("bottom10_consumption", "poverty_rate"),
                   "Are lower-tail living standards improving?"),
            _panel("stability", "Accounting And Risk", ("conservation_drift", "reserve_conservation_drift"),
                   "Are accounting invariants quiet?"),
        ),
    ),
    "real_macro": CategorySpec(
        id="real_macro",
        title="Real Macro Activity",
        panels=(
            _panel("level", "Real Activity Level", ("real_output", "real_consumption"),
                   "Are production and realized consumption moving together?"),
            _panel("growth", "Growth Momentum", ("real_output_growth", "real_consumption_growth"),
                   "Is the real economy expanding, slowing, or contracting?", zero=True),
            _panel("demand_conversion", "Household Demand Conversion",
                   ("desired_consumption", "effective_consumption"),
                   "Do planned household purchases become realized purchases?"),
            _panel("demand_friction", "Demand Friction", ("unsatisfied_demand_ratio",),
                   "Is unmet demand becoming a structural constraint?"),
            _panel("production_fulfillment", "Production Plan Fulfillment",
                   ("production_target_total", "real_output", "production_realization_rate"),
                   "Are firms producing what they planned?", one=True),
            _panel("investment_fulfillment", "Investment Plan Fulfillment",
                   ("investment_target_units", "investment_units", "investment_realization_rate"),
                   "Is desired investment becoming installed capital?", one=True),
            _panel("capital_accumulation", "Capital Accumulation",
                   ("aggregate_capital", "net_private_capital_formation"),
                   "Is productive capacity growing or being eaten away?", zero=True),
            _panel("productivity", "Productivity", ("capital_productivity", "labor_productivity"),
                   "Is efficiency improving on capital and labor margins?"),
            _panel("activity_breadth", "Activity Breadth", ("active_producer_share",),
                   "Is aggregate output broad-based or carried by fewer firms?"),
            _panel("inventory_pressure", "Inventory Pressure",
                   ("inventory", "inventory_investment", "inventory_to_sales"),
                   "Are goods piling up, being depleted, or balanced against sales?", zero=True),
        ),
    ),
    "demographics": CategorySpec(
        id="demographics",
        title="Demographics",
        panels=(
            _panel("population_stock", "Population Stock",
                   ("population_alive", "demographic_households"),
                   "Is the person base growing, shrinking, or reorganizing into households?"),
            _panel("vital_flows", "Births And Deaths",
                   ("births_tick", "deaths_tick"),
                   "Are daily vital events quiet or becoming macro-relevant?", zero=True),
            _panel("social_flows", "Household Formation Events",
                   ("marriages_tick", "divorces_tick", "leaving_home_tick"),
                   "Are marriage, divorce, and leaving-home dynamics reshaping households?", zero=True),
            _panel("age_shares", "Age Composition",
                   ("child_share", "working_age_share", "elder_share"),
                   "Is the population young, working-age heavy, or ageing?", zero=True),
            _panel("dependency", "Dependency Ratios",
                   ("dependency_ratio", "youth_dependency_ratio", "old_age_dependency_ratio"),
                   "How much non-working-age population is carried by working-age adults?", zero=True),
            _panel("household_structure", "Household Structure",
                   ("avg_household_size", "married_share"),
                   "Are households becoming larger, smaller, or more partnered?"),
            _panel("minor_safety", "Minor Safety Net",
                   ("orphan_count", "public_guardian_children", "minor_household_missing"),
                   "Are minors assigned to parents, guardians, or public care?", zero=True),
            _panel("annualized_rates", "Annualized Vital Rates",
                   ("birth_rate_per_1000_annualized", "death_rate_per_1000_annualized"),
                   "What do daily events imply at annual population scale?", zero=True),
        ),
    ),
    "per_capita_macro": CategorySpec(
        id="per_capita_macro",
        title="Per-Capita Macro",
        panels=(
            _panel("real_activity_per_capita", "Real Activity Per Capita",
                   ("real_output_per_capita", "real_consumption_per_capita"),
                   "Is total activity translating into higher living standards per person?"),
            _panel("real_activity_per_adult", "Real Activity Per Adult",
                   ("real_output_per_adult", "real_consumption_per_adult"),
                   "Does working-age scale change the interpretation of real activity?"),
            _panel("income_saving_per_capita", "Income And Saving Per Capita",
                   ("household_income_per_capita", "household_saving_per_capita"),
                   "Are households gaining income per person or leaking demand through saving?"),
            _panel("balance_sheet_per_capita", "Balance Sheet Per Capita",
                   ("money_per_capita", "household_net_worth_per_capita", "gross_household_assets_per_capita"),
                   "Is financial capacity rising per person?"),
            _panel("debt_per_capita", "Debt Per Capita",
                   ("household_debt_per_capita", "private_nfa_per_capita"),
                   "Are liabilities or net financial assets scaling with population?", zero=True),
            _panel("labor_per_adult", "Labor Per Adult",
                   ("employment_per_adult", "labor_supply_per_adult"),
                   "Is adult labor capacity being absorbed by firms and policy?"),
            _panel("public_flows_per_capita", "Public Flows Per Capita",
                   ("gov_spending_per_capita", "taxes_per_capita"),
                   "How large is the public sector per person?", zero=True),
            _panel("person_welfare", "Person Welfare",
                   ("mean_real_consumption_per_person", "person_wealth_gini"),
                   "Are average consumption and person-level inequality moving together?"),
        ),
    ),
    "fiscal_monetary": CategorySpec(
        id="fiscal_monetary",
        title="Fiscal And Monetary Policy",
        panels=(
            _panel("fiscal_flow", "Fiscal Flow Balance",
                   ("augmented_gov_spending", "tax_total", "cash_deficit"),
                   "Is fiscal policy injecting or draining demand?", zero=True),
            _panel("debt", "Debt And Deficit", ("gov_debt_to_gdp", "cash_deficit_to_gdp"),
                   "Is debt stabilizing or compounding?", zero=True),
            _panel("public_capital", "Public Capital",
                   ("public_investment", "public_capital", "pubcap_factor"),
                   "Is public investment raising productive capacity?"),
            _panel("rate_stance", "Policy Rate Stance", ("policy_rate", "real_rate", "rate_change"),
                   "Is policy tightening or easing?", zero=True),
            _panel("inflation_mandate", "Inflation Mandate",
                   ("inflation_ema", "inflation_target", "inflation_gap_to_target"),
                   "Is inflation on target?", zero=True),
            _panel("employment_mandate", "Employment Mandate",
                   ("unemployment_rate", "u_natural", "unemployment_gap"),
                   "Is slack above or below target?", zero=True),
            _panel("taylor_rule", "Taylor Rule Mechanics",
                   ("taylor_rate_target", "policy_rate", "policy_rate_gap"),
                   "Is inertia or a cap binding policy?", zero=True),
            _panel("reserve_tool", "Reserve Quantity Tool",
                   ("reserve_M", "bank_reserves_total", "cb_absorbed", "omo_flow"),
                   "Is OMO draining or injecting reserves?", zero=True),
        ),
    ),
    "banking": CategorySpec(
        id="banking",
        title="Banking System",
        panels=(
            _panel("population", "Bank Population", ("banks_alive", "bank_births", "bank_deaths", "n_bank_failures"),
                   "Is the banking sector stable or churning?"),
            _panel("capital", "Capital And Solvency",
                   ("bank_capital", "bank_economic_capital_min", "bank_leverage"),
                   "Are banks solvent after market-value losses?"),
            _panel("concentration", "Concentration",
                   ("bank_size_gini", "bank_loanbook_hhi", "bank_deposit_hhi"),
                   "Is banking becoming too concentrated?"),
            _panel("reserves", "Reserve Liquidity",
                   ("bank_reserves_total", "peak_intraday_overdraft", "payments_gridlocked"),
                   "Are banks liquid enough to settle payments?", zero=True),
            _panel("interbank", "Interbank Market",
                   ("interbank_rate", "interbank_volume", "interbank_contagion_loss"),
                   "Is interbank funding stabilizing or spreading losses?", zero=True),
            _panel("runs", "Run Dynamics",
                   ("bank_deposit_flight", "bank_fear", "bank_min_price_peak"),
                   "Are runs driven by fear and market distress?"),
            _panel("bond_exposure", "Bond Exposure",
                   ("bank_bond_face", "bond_mtm_pnl", "bank_economic_capital_min"),
                   "Are bond books threatening solvency?", zero=True),
        ),
    ),
    "securities": CategorySpec(
        id="securities",
        title="Securities And Asset Markets",
        panels=(
            _panel("equity_valuation", "Equity Valuation",
                   ("stock_price", "market_cap", "book_value", "tobin_q"),
                   "Are stocks priced near fundamentals?"),
            _panel("bubble_yield", "Bubble And Yield",
                   ("bubble_gap", "dividend_yield", "equity_trend"),
                   "Is return coming from cash flow or bubble momentum?", zero=True),
            _panel("trading_issuance", "Trading And Issuance",
                   ("equity_turnover", "equity_raised"),
                   "Is the market trading and funding firms?"),
            _panel("ownership", "Equity Ownership",
                   ("equity_wealth_share", "equity_ownership_gini", "hh_wealth_gini_incl_equity"),
                   "Is equity concentrating household wealth?"),
            _panel("bond_values", "Bond Stock Values",
                   ("bonds_outstanding", "bond_book_total", "bond_market_total"),
                   "Do face, book, and market values diverge?"),
            _panel("duration_losses", "Duration Losses",
                   ("policy_rate", "bond_mtm_pnl", "bank_bond_face"),
                   "Are rate moves creating bond losses?", zero=True),
            _panel("bond_ownership", "Bond Income And Ownership",
                   ("gov_interest_bill", "hh_bond_market_value", "bank_bond_face"),
                   "Who receives and bears government security exposure?"),
        ),
    ),
}
