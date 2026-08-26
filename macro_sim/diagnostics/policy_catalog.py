"""Frozen P0 catalogs for the Policy causality and crisis audit.

This module contains reviewable economic rulings, not experiment results.  The
runtime Registry remains authoritative for validation and execution.  P0 maps
that surface to activation fixtures, maintained metrics, horizons, and a
policy-independent scenario library so later stages cannot choose a crisis
after seeing a treatment result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Mapping


CRISIS_ROLES = frozenset({"primary", "secondary", "safety", "not_applicable"})
SCENARIO_READINESS = frozenset({"ready_to_calibrate", "conditional", "blocked"})


@dataclass(frozen=True, slots=True)
class ActivationFixtureSpec:
    fixture_id: str
    description: str
    preconditions: tuple[str, ...]
    activation_metrics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    scenario_id: str
    description: str
    readiness: str
    construction: tuple[str, ...]
    entry_metrics: tuple[str, ...]
    damage_metrics: tuple[str, ...]
    caveat: str = ""

    def __post_init__(self) -> None:
        if self.readiness not in SCENARIO_READINESS:
            raise ValueError(
                f"{self.scenario_id}: unknown readiness {self.readiness!r}"
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MaterialitySpec:
    metric_id: str
    absolute_floor: float
    relative_floor: float
    standardized_floor: float
    default_statistic: str
    basis: str = "model_design_prior"

    def __post_init__(self) -> None:
        if self.absolute_floor < 0.0:
            raise ValueError(f"{self.metric_id}: absolute floor must be non-negative")
        if self.relative_floor < 0.0 or self.standardized_floor < 0.0:
            raise ValueError(f"{self.metric_id}: normalized floors must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FailureClass:
    code: str
    layer: str
    description: str
    default_disposition: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GroupAuditSpec:
    owner_role: str
    decision_group: str
    activation_fixture: str
    ordinary_scenarios: tuple[str, ...]
    structural_scenarios: tuple[str, ...]
    crisis_roles: Mapping[str, str]
    primary_metrics: tuple[str, ...]
    tradeoff_metrics: tuple[str, ...]
    causal_chain: tuple[str, ...]
    horizon_days: int


def _fixture(
    fixture_id: str,
    description: str,
    preconditions: tuple[str, ...],
    metrics: tuple[str, ...],
) -> ActivationFixtureSpec:
    return ActivationFixtureSpec(fixture_id, description, preconditions, metrics)


ACTIVATION_FIXTURES: Mapping[str, ActivationFixtureSpec] = MappingProxyType({
    item.fixture_id: item
    for item in (
        _fixture(
            "ACT_FISCAL_RESOURCE_SLACK",
            "Idle labor and productive capacity make discretionary demand and employment support bind.",
            ("positive unemployment", "idle firm capacity", "government enabled"),
            (
                "metric.source.m4.government_spending",
                "metric.economy.unemployment_rate",
                "metric.economy.real_output",
            ),
        ),
        _fixture(
            "ACT_TAX_BASES",
            "All maintained tax bases are positive before a tax or allowance is changed.",
            ("positive wages", "positive profits", "positive consumption", "positive household wealth"),
            ("metric.source.m4.tax_total", "metric.source.m4.transfer_payments"),
        ),
        _fixture(
            "ACT_PENSION_ELIGIBILITY",
            "Retirement-age people receive a nonzero wage reference and remain in populated households.",
            ("positive elder population", "positive reference wage", "government enabled"),
            ("metric.source.m7.pension_paid", "metric.economy.elder_median_consumption"),
        ),
        _fixture(
            "ACT_DEBT_ISSUANCE",
            "A funded deficit creates new bond cohorts and active household or bank demand.",
            ("positive government deficit", "bonds enabled", "positive eligible cash demand"),
            (
                "metric.source.m6.bond_issuance",
                "metric.source.m6.bond_outstanding_face",
                "metric.source.m6.bond_coupon_paid",
            ),
        ),
        _fixture(
            "ACT_TAYLOR_INTERIOR",
            "Inflation and unemployment gaps move an active Taylor rule away from both rate clamps.",
            ("monetary regime is taylor", "rate above zero", "rate below r_max", "nonzero policy gaps"),
            ("metric.economy.policy_rate", "metric.source.m5.inflation_sensor"),
        ),
        _fixture(
            "ACT_BANK_LIQUIDITY",
            "Heterogeneous banks approach reserve or funding constraints while remaining solvent.",
            ("banking enabled", "positive deposits", "positive reserve dispersion", "solvent banks"),
            (
                "metric.source.m5.total_reserves",
                "metric.source.m5.omo_flow",
                "metric.source.m5.lolr_advances",
            ),
        ),
        _fixture(
            "ACT_DEPOSIT_PRICING",
            "Realized bank PnL pays positive deposit interest so a regulatory floor can bind.",
            ("bank realized PnL enabled", "positive deposits", "baseline deposit rate below treatment floor"),
            ("metric.source.m5.deposit_interest_paid", "metric.source.m5.deposit_interest_arrears"),
        ),
        _fixture(
            "ACT_BANK_SOLVENCY",
            "Leveraged banks hold loss-bearing and concentrated assets near capital constraints.",
            ("banking enabled", "positive credit", "heterogeneous capital ratios", "positive borrower exposure"),
            (
                "metric.source.m5.total_bank_capital",
                "metric.source.m5.new_credit",
                "metric.source.m5.bank_failures",
            ),
        ),
        _fixture(
            "ACT_BANK_ENTRY",
            "Bank dynamics produce eligible entrants around the charter-capital threshold.",
            ("bank dynamics enabled", "positive entry signal", "candidate bank capital near threshold"),
            ("metric.source.m6.bank_births", "metric.source.m5.alive_banks"),
        ),
        _fixture(
            "ACT_HOUSEHOLD_CREDIT",
            "Eligible households demand credit near debt-service and bankruptcy constraints.",
            ("household credit enabled", "positive household credit demand", "heterogeneous income and debt"),
            (
                "metric.source.m5.household_debt_service_reserved",
                "metric.economy.household_debt_total",
                "metric.source.m6.household_bankruptcies",
            ),
        ),
        _fixture(
            "ACT_FIRM_CREDIT",
            "Credit-hungry firms sit near leverage, DSCR, collateral, and exposure constraints.",
            ("positive investment demand", "positive firm credit demand", "heterogeneous firm balance sheets"),
            (
                "metric.source.m5.new_credit",
                "metric.source.m5.firm_dscr_credit_shortfall",
                "metric.economy.firm_debt_total",
            ),
        ),
        _fixture(
            "ACT_MORTGAGE_CREDIT",
            "Active housing turnover produces eligible mortgage applications and arrears risk.",
            ("housing and mortgage modules enabled", "positive session sales", "heterogeneous borrower affordability"),
            (
                "metric.source.m8.housing.mortgage_originations",
                "metric.source.m8.housing.mortgage_principal_originated",
                "metric.source.m8.housing.foreclosures",
            ),
        ),
        _fixture(
            "ACT_HOUSING_TRANSACTIONS",
            "Sales, assessed property values, construction, and rental arrears are all nonzero.",
            ("housing market enabled", "positive sales", "positive construction", "positive rental activity"),
            (
                "metric.source.m8.housing.session_sales",
                "metric.source.m8.housing.transfer_tax_paid",
                "metric.source.m8.housing.property_tax_paid",
            ),
        ),
        _fixture(
            "ACT_MARKET_MARGIN",
            "Households hold tradable equity and request margin credit near leverage limits.",
            ("capital market enabled", "margin credit enabled", "positive equity holdings", "positive margin demand"),
            ("metric.source.m6.margin_originated", "metric.source.m6.margin_principal"),
        ),
        _fixture(
            "ACT_TRADE_FLOWS",
            "At least two economies have positive bilateral trade with finite route capacity.",
            ("world trade enabled", "positive imports", "positive exports", "at least two economies"),
            (
                "metric.source.m9.country.imports_volume",
                "metric.source.m9.country.exports_volume",
                "metric.source.m9.world.trade_routes",
            ),
        ),
        _fixture(
            "ACT_MIGRATION_FLOWS",
            "At least two economies produce migration and remittance flows in both directions.",
            ("world migration enabled", "positive wage gap", "positive migrant stock", "positive remittances"),
            (
                "metric.source.m9.country.migrant_stock_hosted",
                "metric.source.m9.country.remittances_sent",
                "metric.source.m9.world.migration_routes",
            ),
        ),
        _fixture(
            "ACT_PEG_PRESSURE",
            "A valid peg owns reserves and faces live interest-rate or external-flow pressure.",
            ("world coupling enabled", "valid anchor", "positive peg reserves", "nonzero pressure differential"),
            (
                "metric.source.m9.country.peg_reserves",
                "metric.source.m9.country.exchange_rate",
                "metric.source.m9.country.capital_flow",
            ),
        ),
        _fixture(
            "ACT_ENERGY_SHORTAGE",
            "Energy demand exceeds deliverable supply while reserve and allocation paths are active.",
            ("energy enabled", "positive household and industry demand", "positive unfilled demand"),
            (
                "metric.source.m8.energy.unfilled",
                "metric.source.m8.energy.transaction_price",
                "metric.source.m8.energy.strategic_reserve_flow",
            ),
        ),
        _fixture(
            "ACT_INSOLVENCY_ARREARS",
            "Firms, indebted households, and tenants approach legal persistence boundaries.",
            ("positive firm insolvency", "positive household debt", "positive mortgage or rent arrears"),
            (
                "metric.source.m6.firm_defaults",
                "metric.source.m6.household_bankruptcies",
                "metric.source.m8.housing.evictions",
            ),
        ),
        _fixture(
            "ACT_OWNERSHIP_TRANSITION",
            "A live energy firm and all affected pricing, ownership, and ledger state are present.",
            ("energy enabled", "at least one live energy firm", "government enabled"),
            ("metric.source.m8.energy.production", "metric.source.m8.energy.transaction_price"),
        ),
        _fixture(
            "ACT_FISCAL_ACCOUNTING_DIVERGENCE",
            "Legacy and national-accounts GDP denominators differ enough to alter a fiscal rule.",
            ("government enabled", "national accounts enabled", "nonzero denominator difference"),
            ("metric.source.m4.government_spending", "metric.economy.na.nominal_gdp"),
        ),
    )
})


def _scenario(
    scenario_id: str,
    description: str,
    readiness: str,
    construction: tuple[str, ...],
    entry: tuple[str, ...],
    damage: tuple[str, ...],
    caveat: str = "",
) -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id, description, readiness, construction, entry, damage, caveat
    )


SCENARIOS: Mapping[str, ScenarioSpec] = MappingProxyType({
    item.scenario_id: item
    for item in (
        _scenario(
            "CR_DEMAND_RECESSION",
            "A household-demand contraction propagates into output and employment.",
            "ready_to_calibrate",
            ("stable burn-in", "household_demand shock"),
            ("metric.economy.real_output", "metric.economy.unemployment_rate"),
            ("metric.economy.real_output", "metric.economy.unemployment_rate", "metric.economy.poverty_rate"),
        ),
        _scenario(
            "CR_SUPPLY_STAGFLATION",
            "Productivity and energy capacity fall while price pressure rises.",
            "ready_to_calibrate",
            ("stable burn-in", "productivity shock", "energy_capacity shock"),
            ("metric.economy.real_output", "metric.economy.inflation"),
            ("metric.economy.real_output", "metric.economy.inflation", "metric.economy.energy_unfilled"),
        ),
        _scenario(
            "CR_ENERGY_EMBARGO",
            "Energy and import capacity losses create a physical shortage.",
            "ready_to_calibrate",
            ("energy-dependent burn-in", "energy_capacity shock", "import_capacity shock"),
            ("metric.source.m8.energy.unfilled", "metric.source.m8.energy.transaction_price"),
            ("metric.economy.real_output", "metric.source.m8.energy.fuel_poverty_share", "metric.economy.inflation"),
        ),
        _scenario(
            "CR_CREDIT_CRUNCH",
            "Credit, demand, and productivity disturbances produce a balance-sheet recession.",
            "ready_to_calibrate",
            ("positive credit burn-in", "credit_supply shock", "household_demand shock", "productivity shock"),
            ("metric.source.m5.new_credit", "metric.economy.real_output"),
            ("metric.economy.real_output", "metric.economy.unemployment_rate", "metric.source.m5.bank_failures"),
        ),
        _scenario(
            "CR_PANDEMIC",
            "Labor, productivity, demand, credit, and optional trade capacity are interrupted.",
            "ready_to_calibrate",
            ("stable burn-in", "labor_availability shock", "productivity shock", "household_demand shock", "credit_supply shock"),
            ("metric.economy.employment", "metric.economy.real_output"),
            ("metric.economy.real_output", "metric.economy.unemployment_rate", "metric.economy.poverty_rate"),
        ),
        _scenario(
            "CR_NATURAL_DISASTER",
            "One-shot capital destruction and sector disruption reduce productive capacity.",
            "ready_to_calibrate",
            ("stable burn-in", "capital_destruction shock", "sector productivity shock"),
            ("metric.source.m9.country.capital_destroyed", "metric.source.m4.aggregate_capital"),
            ("metric.economy.real_output", "metric.economy.unemployment_rate", "metric.source.m4.aggregate_capital"),
        ),
        _scenario(
            "CR_TRADE_INTERRUPTION",
            "Bilateral import and export capacity losses fragment active trade routes.",
            "ready_to_calibrate",
            ("positive bilateral trade burn-in", "import_capacity shock", "export_capacity shock"),
            ("metric.source.m9.country.imports_volume", "metric.source.m9.country.exports_volume"),
            ("metric.economy.real_output", "metric.world.current_account", "metric.economy.price_index"),
        ),
        _scenario(
            "CR_PEG_PRESSURE",
            "A peg loses reserves under trade and live interest-rate pressure.",
            "conditional",
            ("valid peg burn-in", "external-flow pressure", "live rate differential"),
            ("metric.source.m9.country.peg_reserves", "metric.source.m9.country.exchange_rate"),
            ("metric.source.m9.country.peg_reserves", "metric.world.current_account", "metric.economy.real_output"),
            "Requires a repeatable endogenous reserve-drain path before use for efficacy.",
        ),
        _scenario(
            "CR_BANK_RUN",
            "Deposit flight creates bank liquidity stress and possible contagion.",
            "conditional",
            ("vulnerable bank burn-in", "endogenous withdrawal trigger"),
            ("metric.source.m5.run_flight_volume", "metric.source.m5.lolr_advances"),
            ("metric.source.m5.bank_failures", "metric.source.m5.new_credit", "metric.economy.real_output"),
            "No direct withdrawal shock channel exists; the endogenous run trigger must be validated.",
        ),
        _scenario(
            "CR_HOUSING_BUST",
            "A leveraged housing expansion reverses into arrears, foreclosures, and construction decline.",
            "conditional",
            ("endogenous housing-credit boom", "common macro trigger"),
            ("metric.source.m8.housing.house_price", "metric.source.m8.housing.foreclosures"),
            ("metric.source.m8.housing.house_price", "metric.source.m8.housing.foreclosures", "metric.economy.real_output"),
            "Requires reproducible endogenous boom-bust formation; there is no direct house-price override.",
        ),
        _scenario(
            "CR_SOVEREIGN_STRESS",
            "Government refinancing stress feeds back through bond holders and the real economy.",
            "blocked",
            ("high debt and refinancing need", "funding stress trigger"),
            ("metric.source.m6.bond_issuance", "metric.economy.gov_debt_to_gdp"),
            ("metric.source.m6.bond_market_value", "metric.source.m5.total_bank_capital", "metric.economy.real_output"),
            "Blocked unless sovereign risk-premium or default transmission is implemented and observed.",
        ),
    )
})


ORDINARY_SCENARIOS = (
    "BASE_NORMAL",
    "BASE_SLACK",
    "BASE_TIGHT",
)

STRUCTURAL_SCENARIOS = (
    "STRUCT_HIGH_POVERTY",
    "STRUCT_HIGH_INEQUALITY",
    "STRUCT_LOW_PARTICIPATION",
    "STRUCT_HOUSING_SHORTAGE",
    "STRUCT_LOW_PRODUCTIVITY",
    "STRUCT_ENERGY_DEPENDENCE",
    "STRUCT_POPULATION_AGING",
    "STRUCT_EXTERNAL_IMBALANCE",
)


def _roles(
    *,
    primary: tuple[str, ...] = (),
    secondary: tuple[str, ...] = (),
    safety: tuple[str, ...] = (),
) -> Mapping[str, str]:
    output = {scenario_id: "not_applicable" for scenario_id in SCENARIOS}
    for role, ids in (("primary", primary), ("secondary", secondary), ("safety", safety)):
        for scenario_id in ids:
            if scenario_id not in output:
                raise ValueError(f"unknown scenario {scenario_id!r}")
            if output[scenario_id] != "not_applicable":
                raise ValueError(f"scenario {scenario_id!r} assigned more than once")
            output[scenario_id] = role
    return MappingProxyType(output)


GROUP_SPECS: Mapping[tuple[str, str], GroupAuditSpec] = MappingProxyType({
    ("treasury", "fiscal_stance"): GroupAuditSpec(
        "treasury", "fiscal_stance", "ACT_FISCAL_RESOURCE_SLACK",
        ORDINARY_SCENARIOS, ("STRUCT_HIGH_POVERTY", "STRUCT_LOW_PRODUCTIVITY", "STRUCT_HOUSING_SHORTAGE"),
        _roles(
            primary=("CR_DEMAND_RECESSION",),
            secondary=("CR_CREDIT_CRUNCH", "CR_PANDEMIC", "CR_NATURAL_DISASTER"),
            safety=("CR_SUPPLY_STAGFLATION", "CR_ENERGY_EMBARGO"),
        ),
        ("metric.source.m4.government_spending", "metric.economy.real_output", "metric.economy.unemployment_rate"),
        ("metric.economy.gov_deficit_to_gdp", "metric.economy.inflation", "metric.economy.gov_debt_to_gdp"),
        ("policy", "public demand or investment", "output", "employment", "fiscal balance"),
        365,
    ),
    ("treasury", "tax_and_transfers"): GroupAuditSpec(
        "treasury", "tax_and_transfers", "ACT_TAX_BASES",
        ORDINARY_SCENARIOS, ("STRUCT_HIGH_POVERTY", "STRUCT_HIGH_INEQUALITY", "STRUCT_ENERGY_DEPENDENCE", "STRUCT_HOUSING_SHORTAGE"),
        _roles(
            secondary=("CR_DEMAND_RECESSION", "CR_SUPPLY_STAGFLATION", "CR_ENERGY_EMBARGO"),
            safety=("CR_CREDIT_CRUNCH", "CR_HOUSING_BUST"),
        ),
        ("metric.source.m4.tax_total", "metric.source.m4.transfer_payments", "metric.economy.poverty_rate"),
        ("metric.economy.real_output", "metric.economy.income_gini", "metric.economy.gov_deficit_to_gdp"),
        ("policy", "tax base or transfer eligibility", "disposable income", "demand and distribution", "fiscal balance"),
        1825,
    ),
    ("treasury", "debt_management"): GroupAuditSpec(
        "treasury", "debt_management", "ACT_DEBT_ISSUANCE",
        ORDINARY_SCENARIOS, ("STRUCT_EXTERNAL_IMBALANCE",),
        _roles(
            primary=("CR_SOVEREIGN_STRESS",),
            secondary=("CR_CREDIT_CRUNCH", "CR_PEG_PRESSURE"),
            safety=("CR_DEMAND_RECESSION",),
        ),
        ("metric.source.m6.bond_issuance", "metric.source.m6.bond_outstanding_face", "metric.source.m6.bond_coupon_paid"),
        ("metric.economy.gov_debt_to_gdp", "metric.source.m5.total_bank_capital", "metric.economy.real_output"),
        ("policy", "new debt cohort", "cash funding and duration", "holder balance sheets", "fiscal resilience"),
        3650,
    ),
    ("central_bank", "monetary_stance"): GroupAuditSpec(
        "central_bank", "monetary_stance", "ACT_TAYLOR_INTERIOR",
        ORDINARY_SCENARIOS, ("STRUCT_EXTERNAL_IMBALANCE",),
        _roles(
            primary=("CR_DEMAND_RECESSION", "CR_SUPPLY_STAGFLATION"),
            secondary=("CR_CREDIT_CRUNCH", "CR_PEG_PRESSURE"),
            safety=("CR_ENERGY_EMBARGO",),
        ),
        ("metric.economy.policy_rate", "metric.economy.inflation", "metric.economy.unemployment_rate"),
        ("metric.economy.real_output", "metric.source.m5.new_credit", "metric.source.m9.country.peg_reserves"),
        ("policy", "policy-rate path", "credit and demand", "prices and employment", "financial and external balance"),
        365,
    ),
    ("central_bank", "liquidity_operations"): GroupAuditSpec(
        "central_bank", "liquidity_operations", "ACT_BANK_LIQUIDITY",
        ORDINARY_SCENARIOS, (),
        _roles(
            primary=("CR_CREDIT_CRUNCH", "CR_BANK_RUN"),
            secondary=("CR_PEG_PRESSURE",),
            safety=("CR_DEMAND_RECESSION",),
        ),
        ("metric.source.m5.total_reserves", "metric.source.m5.omo_flow", "metric.source.m5.lolr_advances"),
        ("metric.source.m5.bank_failures", "metric.source.m5.new_credit", "metric.economy.inflation"),
        ("policy", "bank reserves and emergency funding", "payment and credit capacity", "failures", "real activity"),
        90,
    ),
    ("central_bank", "fx_operations"): GroupAuditSpec(
        "central_bank", "fx_operations", "ACT_PEG_PRESSURE",
        ORDINARY_SCENARIOS, ("STRUCT_EXTERNAL_IMBALANCE",),
        _roles(
            primary=("CR_PEG_PRESSURE",),
            secondary=("CR_TRADE_INTERRUPTION", "CR_CREDIT_CRUNCH"),
            safety=("CR_DEMAND_RECESSION",),
        ),
        ("metric.source.m9.country.peg_reserves", "metric.source.m9.country.capital_flow", "metric.source.m9.country.exchange_rate"),
        ("metric.world.current_account", "metric.economy.real_output", "metric.economy.inflation"),
        ("policy", "cross-border settlement or peg defense", "capital and reserve flows", "exchange rate", "domestic balance sheets"),
        365,
    ),
    ("regulator", "macroprudential"): GroupAuditSpec(
        "regulator", "macroprudential", "ACT_BANK_SOLVENCY",
        ORDINARY_SCENARIOS, ("STRUCT_HOUSING_SHORTAGE", "STRUCT_HIGH_INEQUALITY"),
        _roles(
            primary=("CR_CREDIT_CRUNCH", "CR_BANK_RUN", "CR_HOUSING_BUST"),
            secondary=("CR_DEMAND_RECESSION", "CR_PEG_PRESSURE"),
            safety=("CR_SUPPLY_STAGFLATION",),
        ),
        ("metric.source.m5.new_credit", "metric.source.m5.total_bank_capital", "metric.source.m5.bank_failures"),
        ("metric.economy.real_output", "metric.economy.unemployment_rate", "metric.economy.household_debt_total"),
        ("policy", "credit eligibility or capital constraint", "origination and leverage", "loss absorption", "real activity"),
        1825,
    ),
    ("regulator", "structural_law"): GroupAuditSpec(
        "regulator", "structural_law", "ACT_INSOLVENCY_ARREARS",
        ORDINARY_SCENARIOS, ("STRUCT_HOUSING_SHORTAGE", "STRUCT_HIGH_POVERTY"),
        _roles(
            primary=("CR_CREDIT_CRUNCH", "CR_BANK_RUN", "CR_HOUSING_BUST"),
            secondary=("CR_NATURAL_DISASTER", "CR_DEMAND_RECESSION"),
        ),
        ("metric.source.m6.firm_defaults", "metric.source.m6.household_bankruptcies", "metric.source.m8.housing.foreclosures"),
        ("metric.source.m5.realized_credit_losses", "metric.source.m8.housing.evictions", "metric.economy.real_output"),
        ("policy", "legal threshold or resolution", "default and recovery", "creditor and debtor balance sheets", "entry and activity"),
        1825,
    ),
    ("external_affairs", "trade_and_migration"): GroupAuditSpec(
        "external_affairs", "trade_and_migration", "ACT_TRADE_FLOWS",
        ORDINARY_SCENARIOS, ("STRUCT_EXTERNAL_IMBALANCE", "STRUCT_LOW_PARTICIPATION"),
        _roles(
            primary=("CR_TRADE_INTERRUPTION",),
            secondary=("CR_PANDEMIC", "CR_ENERGY_EMBARGO", "CR_PEG_PRESSURE"),
            safety=("CR_DEMAND_RECESSION",),
        ),
        ("metric.source.m9.country.imports_volume", "metric.source.m9.country.exports_volume", "metric.source.m9.country.migrant_stock_hosted"),
        ("metric.world.current_account", "metric.economy.real_output", "metric.economy.avg_wage"),
        ("policy", "bilateral route or price wedge", "trade migration or remittance flow", "domestic allocation", "external balance"),
        1825,
    ),
    ("energy", "energy_operations"): GroupAuditSpec(
        "energy", "energy_operations", "ACT_ENERGY_SHORTAGE",
        ORDINARY_SCENARIOS, ("STRUCT_ENERGY_DEPENDENCE", "STRUCT_HIGH_POVERTY"),
        _roles(
            primary=("CR_ENERGY_EMBARGO", "CR_SUPPLY_STAGFLATION"),
            secondary=("CR_NATURAL_DISASTER", "CR_PANDEMIC"),
            safety=("CR_DEMAND_RECESSION",),
        ),
        ("metric.source.m8.energy.unfilled", "metric.source.m8.energy.transaction_price", "metric.source.m8.energy.strategic_reserve_stock"),
        ("metric.source.m8.energy.fuel_poverty_share", "metric.economy.real_output", "metric.economy.gov_deficit_to_gdp"),
        ("policy", "reserve price or allocation operation", "energy quantity and price", "household and firm coverage", "fiscal and real effects"),
        365,
    ),
    ("energy", "energy_structure"): GroupAuditSpec(
        "energy", "energy_structure", "ACT_OWNERSHIP_TRANSITION",
        ORDINARY_SCENARIOS, ("STRUCT_ENERGY_DEPENDENCE",),
        _roles(secondary=("CR_ENERGY_EMBARGO",), safety=("CR_SUPPLY_STAGFLATION",)),
        ("metric.source.m8.energy.production", "metric.source.m8.energy.transaction_price"),
        ("metric.source.m8.energy.unfilled", "metric.source.m4.government_deficit", "metric.economy.real_output"),
        ("policy", "ownership transition", "pricing and investment behavior", "energy supply", "fiscal and real effects"),
        3650,
    ),
    ("labor_social", "labor_and_welfare"): GroupAuditSpec(
        "labor_social", "labor_and_welfare", "ACT_FISCAL_RESOURCE_SLACK",
        ORDINARY_SCENARIOS, ("STRUCT_HIGH_POVERTY", "STRUCT_HIGH_INEQUALITY", "STRUCT_LOW_PARTICIPATION", "STRUCT_POPULATION_AGING"),
        _roles(
            primary=("CR_DEMAND_RECESSION", "CR_PANDEMIC"),
            secondary=("CR_CREDIT_CRUNCH",),
            safety=("CR_SUPPLY_STAGFLATION",),
        ),
        ("metric.economy.unemployment_rate", "metric.source.m7.mean_hourly_wage", "metric.economy.poverty_rate"),
        ("metric.economy.real_output", "metric.economy.income_gini", "metric.economy.gov_deficit_to_gdp"),
        ("policy", "wage or eligibility rule", "employment and transfers", "household income and demand", "output and fiscal balance"),
        1825,
    ),
})


LEVER_ACTIVATION_OVERRIDES: Mapping[str, str] = MappingProxyType({
    "pension_replacement": "ACT_PENSION_ELIGIBILITY",
    "fiscal_uses_national_accounts_gdp": "ACT_FISCAL_ACCOUNTING_DIVERGENCE",
    "deposit_rate_floor": "ACT_DEPOSIT_PRICING",
    "bank_min_capital": "ACT_BANK_ENTRY",
    "margin_ltv": "ACT_MARKET_MARGIN",
    "margin_max": "ACT_MARKET_MARGIN",
    "kappa": "ACT_FIRM_CREDIT",
    "firm_credit_min_dscr": "ACT_FIRM_CREDIT",
    "regulatory_firm_capital_haircut": "ACT_FIRM_CREDIT",
    "regulatory_firm_inventory_haircut": "ACT_FIRM_CREDIT",
    "hh_credit_limit": "ACT_HOUSEHOLD_CREDIT",
    "mortgage_ltv_cap": "ACT_MORTGAGE_CREDIT",
    "mortgage_underwriting": "ACT_MORTGAGE_CREDIT",
    "mortgage_dsti_cap": "ACT_MORTGAGE_CREDIT",
    "mortgage_stress_rate_addon": "ACT_MORTGAGE_CREDIT",
    "mortgage_risk_weight": "ACT_MORTGAGE_CREDIT",
    "mortgage_min_capital_ratio": "ACT_MORTGAGE_CREDIT",
    "mortgage_foreclosure_ltv": "ACT_MORTGAGE_CREDIT",
    "mortgage_arrears_floor": "ACT_MORTGAGE_CREDIT",
    "housing_permits": "ACT_HOUSING_TRANSACTIONS",
    "housing_transfer_tax": "ACT_HOUSING_TRANSACTIONS",
    "housing_property_tax": "ACT_HOUSING_TRANSACTIONS",
    "housing_in_wealth_tax": "ACT_HOUSING_TRANSACTIONS",
    "rental_eviction_arrears": "ACT_HOUSING_TRANSACTIONS",
    "land_fee_share": "ACT_HOUSING_TRANSACTIONS",
    "land_fee_stock_elasticity": "ACT_HOUSING_TRANSACTIONS",
    "tariff": "ACT_TRADE_FLOWS",
    "import_quota": "ACT_TRADE_FLOWS",
    "export_subsidy": "ACT_TRADE_FLOWS",
    "sanctions_imposed_on": "ACT_TRADE_FLOWS",
    "immigration_cap": "ACT_MIGRATION_FLOWS",
    "emigration_cap": "ACT_MIGRATION_FLOWS",
    "remittance_tax": "ACT_MIGRATION_FLOWS",
    "outward_remittance_tax": "ACT_MIGRATION_FLOWS",
    "guest_worker_return": "ACT_MIGRATION_FLOWS",
})


# The first metric is the mechanism-proximal P1 activation target.  Later
# metrics capture an adjacent quantity or balance-sheet response.  Every
# canonical Registry lever must appear exactly once; P0 verification enforces
# this invariant.
LEVER_PROXIMAL_METRICS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "gov_consumption_share": ("metric.source.m4.government_consumption",),
    "gov_deficit_target": ("metric.source.m4.government_deficit", "metric.source.m4.government_consumption"),
    "deficit_u_ref": ("metric.source.m4.government_consumption",),
    "benefit_replacement": ("metric.source.m4.transfer_payments", "metric.economy.poverty_rate"),
    "benefit_income_floor": ("metric.source.m4.transfer_payments", "metric.economy.poverty_rate"),
    "pension_replacement": ("metric.source.m7.pension_paid", "metric.economy.elder_median_consumption"),
    "tax_profit_rate": ("metric.source.m4.tax_profit",),
    "tax_income_rate": ("metric.source.m4.tax_income",),
    "income_allowance": ("metric.source.m4.tax_income",),
    "tax_consumption_rate": ("metric.source.m4.tax_consumption",),
    "tax_necessity_rate": ("metric.source.m4.tax_consumption", "metric.source.m4.necessity_consumption"),
    "tax_luxury_rate": ("metric.source.m4.tax_consumption", "metric.source.m4.luxury_consumption"),
    "tax_wealth_rate": ("metric.source.m4.tax_total", "metric.economy.hh_wealth_gini"),
    "wealth_allowance": ("metric.source.m4.tax_total", "metric.economy.hh_wealth_gini"),
    "tax_energy_rate": ("metric.source.m8.energy.excise_paid", "metric.source.m8.energy.household_units"),
    "tax_energy_windfall": ("metric.source.m8.energy.windfall_tax_paid",),
    "spr_target_units": ("metric.source.m8.energy.strategic_reserve_stock",),
    "spr_flow_cap": ("metric.source.m8.energy.strategic_reserve_flow",),
    "soe_price_at_cost": ("metric.source.m8.energy.transaction_price",),
    "energy_price_cap": ("metric.source.m8.energy.transaction_price", "metric.source.m8.energy.unfilled"),
    "energy_rationing": ("metric.source.m8.energy.household_units", "metric.source.m8.energy.industry_units"),
    "energy_cap_compensation": ("metric.source.m8.energy.cap_compensation",),
    "energy_subsidy_rate": ("metric.source.m8.energy.subsidy_paid", "metric.source.m8.energy.fuel_poverty_share"),
    "energy_subsidy_threshold": ("metric.source.m8.energy.subsidy_paid", "metric.source.m8.energy.fuel_poverty_share"),
    "min_wage": ("metric.source.m7.mean_hourly_wage", "metric.economy.unemployment_rate"),
    "job_guarantee": ("metric.source.m7.job_guarantee", "metric.source.m4.job_guarantee_spending"),
    "jg_wage_ratio": ("metric.source.m4.job_guarantee_spending", "metric.source.m7.job_guarantee"),
    "inflation_target": ("metric.economy.policy_rate",),
    "taylor_phi_pi": ("metric.economy.policy_rate",),
    "taylor_phi_u": ("metric.economy.policy_rate",),
    "rate_inertia": ("metric.economy.policy_rate",),
    "manual_policy_rate": ("metric.economy.policy_rate",),
    "monetary_regime": ("metric.economy.policy_rate", "metric.source.m5.inflation_sensor"),
    "r_neutral": ("metric.economy.policy_rate",),
    "u_natural": ("metric.economy.policy_rate",),
    "r_max": ("metric.economy.policy_rate",),
    "infl_ema_lambda": ("metric.source.m5.inflation_sensor", "metric.economy.policy_rate"),
    "cb_core_inflation": ("metric.source.m5.inflation_sensor", "metric.economy.policy_rate"),
    "cb_uses_fixed_basket_cpi": ("metric.source.m5.inflation_sensor", "metric.economy.policy_rate"),
    "cb_log_inflation": ("metric.source.m5.inflation_sensor", "metric.economy.policy_rate"),
    "fiscal_uses_national_accounts_gdp": ("metric.source.m4.fiscal_output_reference_applied", "metric.economy.na.nominal_gdp"),
    "bond_finance_frac": ("metric.source.m6.bond_issuance",),
    "bond_coupon": ("metric.source.m6.bond_issued_coupon_rate", "metric.source.m6.bond_weighted_coupon_rate"),
    "bond_maturity": ("metric.source.m6.bond_issued_maturity_days", "metric.source.m6.bond_weighted_remaining_maturity_days"),
    "omo": ("metric.source.m6.bond_duration_adjusted_omo_flow", "metric.source.m5.omo_flow", "metric.source.m5.total_reserves"),
    "omo_reserve_target": ("metric.source.m5.total_reserves", "metric.source.m5.omo_flow"),
    "omo_drain_frac": ("metric.source.m5.omo_flow", "metric.source.m5.total_reserves"),
    "lolr": ("metric.source.m5.lolr_liquidity_shortfall", "metric.source.m5.lolr_advances", "metric.source.m5.bank_failures"),
    "bank_capital_constraint": ("metric.source.m5.bank_capital_constraint_applied", "metric.source.m5.bank_gross_capital_headroom", "metric.source.m5.bank_gross_capital_credit_shortfall", "metric.source.m5.new_credit"),
    "bank_leverage_cap": ("metric.source.m5.new_credit", "metric.source.m5.total_bank_capital"),
    "bank_target_capital_ratio": ("metric.source.m5.total_bank_capital", "metric.source.m4.dividends_paid"),
    "bank_exposure_limit": ("metric.source.m5.new_credit", "metric.source.m5.firm_dscr_credit_shortfall"),
    "bank_min_capital": ("metric.source.m6.bank_births", "metric.source.m5.alive_banks"),
    "bank_bond_duration_limit": ("metric.source.m6.bank_bond_market_value", "metric.source.m5.total_bank_capital"),
    "bank_resolution_fund": ("metric.source.m5.resolution_funding_need", "metric.source.m5.resolution_cost", "metric.source.m5.resolution_mutualized_cost", "metric.source.m5.bank_failures"),
    "reserve_floor_frac": ("metric.economy.reserve_floor_breach_share", "metric.source.m5.total_reserves"),
    "margin_ltv": ("metric.source.m6.margin_originated", "metric.source.m6.margin_principal"),
    "margin_max": ("metric.source.m6.margin_max_applied", "metric.source.m6.margin_target_equity", "metric.source.m6.margin_max_binding_shortfall", "metric.source.m6.margin_originated"),
    "kappa": ("metric.source.m5.new_credit", "metric.economy.firm_debt_total"),
    "hh_credit_limit": ("metric.source.m5.household_debt_service_reserved", "metric.economy.household_debt_total"),
    "mortgage_ltv_cap": ("metric.source.m8.housing.mortgage_principal_originated", "metric.source.m8.housing.mortgage_originations"),
    "mortgage_underwriting": ("metric.source.m8.housing.mortgage_underwriting_applications", "metric.source.m8.housing.mortgage_dsti_rejections"),
    "mortgage_dsti_cap": ("metric.source.m8.housing.mortgage_dsti_cap_applied", "metric.source.m8.housing.mortgage_cohort_weighted_dsti_cap", "metric.source.m8.housing.mortgage_dsti_rejections"),
    "mortgage_stress_rate_addon": ("metric.source.m8.housing.mortgage_stress_rate_addon_applied", "metric.source.m8.housing.mortgage_cohort_weighted_stress_rate_addon", "metric.source.m8.housing.mortgage_dsti_rejections"),
    "mortgage_risk_weight": ("metric.source.m8.housing.mortgage_risk_weight_applied", "metric.source.m8.housing.mortgage_rwa_principal_capacity", "metric.source.m8.housing.mortgage_rwa_rejections"),
    "mortgage_min_capital_ratio": ("metric.source.m8.housing.mortgage_minimum_capital_ratio_applied", "metric.source.m8.housing.mortgage_rwa_principal_capacity", "metric.source.m8.housing.mortgage_rwa_rejections"),
    "mortgage_foreclosure_ltv": ("metric.source.m8.housing.foreclosures",),
    "mortgage_arrears_floor": ("metric.source.m8.housing.mortgage_arrears_floor_applied", "metric.source.m8.housing.mortgage_foreclosure_candidates", "metric.source.m8.housing.mortgage_foreclosures_prevented_by_liquidity", "metric.source.m8.housing.foreclosures"),
    "housing_permits": ("metric.source.m8.housing.housing_permit_cap_applied", "metric.source.m8.housing.housing_units_ready_for_permits", "metric.source.m8.housing.housing_units_blocked_by_permits", "metric.source.m8.housing.permits_used", "metric.source.m8.housing.dwellings_completed"),
    "housing_transfer_tax": ("metric.source.m8.housing.transfer_tax_paid", "metric.source.m8.housing.session_sales"),
    "housing_property_tax": ("metric.source.m8.housing.property_tax_paid",),
    "housing_in_wealth_tax": ("metric.source.m8.housing.housing_wealth_tax_base_included", "metric.source.m8.housing.housing_wealth_tax_paid"),
    "jg_public_works_share": ("metric.source.m4.job_guarantee_public_capital_formation",),
    "deposit_rate_floor": ("metric.source.m5.deposit_interest_paid",),
    "deficit_u_cap": ("metric.source.m4.fiscal_unemployment_multiplier_applied", "metric.source.m4.fiscal_deficit_target_applied", "metric.source.m4.government_procurement_budget", "metric.source.m4.government_deficit"),
    "gov_investment_share": ("metric.source.m4.public_fixed_capital_formation", "metric.source.m4.public_capital"),
    "omo_index_deposits": ("metric.source.m5.omo_flow", "metric.source.m5.total_reserves"),
    "bankrupt_persist": ("metric.source.m6.firm_defaults", "metric.source.m6.firm_exits"),
    "household_bankruptcy": ("metric.source.m6.household_bankruptcy_candidates", "metric.source.m6.household_bankruptcies_blocked_by_policy", "metric.source.m6.household_bankruptcies", "metric.source.m6.margin_writeoffs"),
    "rental_eviction_arrears": ("metric.source.m8.housing.evictions", "metric.source.m8.housing.rent_unpaid"),
    "bank_migrate_on_failure": ("metric.source.m5.failed_account_migration_candidates", "metric.source.m5.failed_accounts_migrated", "metric.source.m5.failed_loan_migration_candidates", "metric.source.m5.failed_loans_migrated"),
    "unified_bank_rwa": ("metric.source.m5.unified_bank_rwa_applied", "metric.source.m5.bank_rwa_headroom", "metric.source.m5.bank_rwa_credit_shortfall", "metric.source.m8.housing.mortgage_bank_risk_weighted_assets", "metric.source.m8.housing.mortgage_rwa_rejections"),
    "firm_credit_min_dscr": ("metric.source.m5.firm_credit_min_dscr_applied", "metric.source.m5.firm_credit_applications", "metric.source.m5.firm_dscr_credit_shortfall", "metric.source.m5.firm_credit_originated"),
    "regulatory_firm_capital_haircut": ("metric.source.m6.firm_capital_haircut_applied", "metric.source.m6.firm_eligible_collateral_value"),
    "regulatory_firm_inventory_haircut": ("metric.source.m6.firm_inventory_haircut_applied", "metric.source.m6.firm_eligible_collateral_value"),
    "land_fee_share": ("metric.source.m8.housing.land_fee_share_applied", "metric.source.m8.housing.land_fee_assessments", "metric.source.m8.housing.land_fee_paid"),
    "land_fee_stock_elasticity": ("metric.source.m8.housing.land_fee_stock_elasticity_applied", "metric.source.m8.housing.land_fee_stock_pressure_applied", "metric.source.m8.housing.land_fee_assessments"),
    "soe_efirm": ("metric.source.m8.energy.transaction_price", "metric.source.m8.energy.production"),
    "tariff": ("metric.source.m9.country.tariff_revenue", "metric.source.m9.country.imports_volume"),
    "import_quota": ("metric.source.m9.country.imports_volume",),
    "export_subsidy": ("metric.source.m9.country.export_subsidy_cost", "metric.source.m9.country.exports_volume"),
    "capital_control": ("metric.source.m9.country.capital_flow",),
    "external_interest_settlement_fraction": ("metric.source.m9.country.factor_income_cash", "metric.source.m9.country.factor_income_arrears"),
    "sanctions_imposed_on": ("metric.source.m9.country.imports_volume", "metric.source.m9.country.exports_volume"),
    "immigration_cap": ("metric.source.m9.country.migrant_stock_hosted",),
    "emigration_cap": ("metric.source.m9.country.migrant_stock_abroad",),
    "remittance_tax": ("metric.source.m9.country.remittance_tax_revenue", "metric.source.m9.country.remittances_received"),
    "outward_remittance_tax": ("metric.source.m9.country.remittance_tax_revenue", "metric.source.m9.country.remittances_sent"),
    "guest_worker_return": ("metric.source.m9.country.migrant_stock_hosted", "metric.source.m9.country.migrant_stock_abroad"),
    "fx_regime": ("metric.source.m9.country.exchange_rate", "metric.source.m9.country.peg_reserves"),
    "peg_anchor": ("metric.source.m9.country.exchange_rate", "metric.source.m9.country.peg_reserves"),
    "peg_reserve_scale": ("metric.source.m9.country.peg_reserves",),
})


LEVER_HORIZON_OVERRIDES: Mapping[str, int] = MappingProxyType({
    "manual_policy_rate": 90,
    "monetary_regime": 365,
    "omo": 30,
    "omo_reserve_target": 30,
    "omo_drain_frac": 30,
    "lolr": 30,
    "reserve_floor_frac": 90,
    "spr_target_units": 365,
    "spr_flow_cap": 90,
    "energy_price_cap": 90,
    "energy_rationing": 90,
    "bond_coupon": 3650,
    "bond_maturity": 3650,
    "pension_replacement": 7300,
    "housing_permits": 1825,
    "land_fee_share": 1825,
    "land_fee_stock_elasticity": 1825,
    "soe_efirm": 3650,
    "immigration_cap": 7300,
    "emigration_cap": 7300,
    "guest_worker_return": 7300,
})


FAILURE_TAXONOMY: Mapping[str, FailureClass] = MappingProxyType({
    item.code: item
    for item in (
        FailureClass("registry_missing", "p0", "A live policy field is absent from the canonical Registry.", "engine_route_defect"),
        FailureClass("owner_or_group_missing", "p0", "A lever has no unique institutional owner or decision group.", "engine_route_defect"),
        FailureClass("contract_unmapped", "p0", "A lever lacks an activation, metric, horizon, or scenario ruling.", "unsupported_by_current_engine"),
        FailureClass("metric_unmaintained", "p0", "A declared causal observable is not maintained by the native engine.", "observable_defect"),
        FailureClass("route_missing", "p1", "The action cannot reach its declared native read point.", "engine_route_defect"),
        FailureClass("capability_guard_failure", "p1", "An unsupported action commits or a supported action is rejected incorrectly.", "engine_route_defect"),
        FailureClass("linked_atomicity_failure", "p1", "A linked or world action partially mutates on rejection.", "engine_route_defect"),
        FailureClass("boundary_timing_failure", "p1", "A staged action affects the completed day or misses the declared next-day read.", "engine_route_defect"),
        FailureClass("noop_mutation", "p1", "An exact no-op changes a version, event, cost, or economic path.", "engine_route_defect"),
        FailureClass("checkpoint_replay_failure", "p1", "Checkpoint continuation does not reproduce policy state, events, or outcomes.", "engine_route_defect"),
        FailureClass("activation_fixture_invalid", "p2", "The fixture does not make the intended base or constraint bind.", "unsupported_by_current_engine"),
        FailureClass("mechanism_silent", "p2", "The read point changes but no mechanism-proximal observable responds.", "mechanism_defect"),
        FailureClass("wrong_sign", "p2", "The declared directional effect reverses without a documented regime transition.", "mechanism_defect"),
        FailureClass("wrong_clock", "p2", "The effect arrives before eligibility or outside the declared operating horizon.", "mechanism_defect"),
        FailureClass("implausibly_weak", "p2", "The valid mechanism remains below its preregistered materiality floor.", "remove_from_player_surface"),
        FailureClass("explosive_response", "p2", "A meaningful dose creates an unbounded or implausibly large response.", "mechanism_defect"),
        FailureClass("genesis_artifact", "p2", "The apparent effect is only an opening-state overwrite and has no runtime channel.", "mechanism_defect"),
        FailureClass("accounting_violation", "p2", "The treatment violates a stock-flow, money, or real-stock identity.", "mechanism_defect"),
        FailureClass("crisis_entry_failure", "p3", "The frozen no-response path does not meet its crisis entry rule.", "unsupported_by_current_engine"),
        FailureClass("crisis_propagation_failure", "p3", "The injected input changes without the declared endogenous propagation chain.", "unsupported_by_current_engine"),
        FailureClass("crisis_severity_failure", "p3", "Mild, moderate, and severe variants are not ordered by control damage.", "unsupported_by_current_engine"),
        FailureClass("crisis_recovery_failure", "p3", "A finite shock produces unexplained permanent collapse or instant costless recovery.", "mechanism_defect"),
        FailureClass("treatment_dependent_selection", "p3", "Treatment outcomes alter crisis entry or seed inclusion.", "unsupported_by_current_engine"),
        FailureClass("efficacy_failure", "p4", "A primary crisis policy activates but does not improve its preregistered loss estimand.", "remove_from_player_surface"),
        FailureClass("guardrail_breach", "p4", "A treatment improves its headline target by violating a hard safety or accounting guardrail.", "mechanism_defect"),
        FailureClass("future_information_leakage", "p8", "A human-comparable occupant observes unreleased or unauthorized state.", "engine_route_defect"),
        FailureClass("finite_size_instability", "p6", "A material sign or activation conclusion fails the matched scale comparison.", "accepted_expert_only"),
        FailureClass("dominant_strategy", "p7", "One setting dominates all declared states without a visible cost or trade-off.", "remove_from_player_surface"),
    )
})


_SHARE_METRICS = frozenset({
    "metric.economy.unemployment_rate",
    "metric.economy.poverty_rate",
    "metric.economy.income_gini",
    "metric.economy.hh_wealth_gini",
    "metric.economy.gov_deficit_to_gdp",
    "metric.economy.gov_debt_to_gdp",
    "metric.economy.reserve_floor_breach_share",
    "metric.source.m8.energy.fuel_poverty_share",
})
_RATE_METRICS = frozenset({
    "metric.economy.inflation",
    "metric.economy.policy_rate",
    "metric.source.m5.inflation_sensor",
})
_COUNT_METRICS = frozenset({
    "metric.source.m5.bank_failures",
    "metric.source.m5.alive_banks",
    "metric.source.m6.bank_births",
    "metric.source.m6.firm_defaults",
    "metric.source.m6.firm_exits",
    "metric.source.m6.household_bankruptcies",
    "metric.source.m8.housing.foreclosures",
    "metric.source.m8.housing.evictions",
    "metric.source.m8.housing.session_sales",
    "metric.source.m8.housing.mortgage_originations",
    "metric.source.m8.housing.dwellings_completed",
    "metric.source.m8.housing.permits_used",
    "metric.source.m9.world.trade_routes",
    "metric.source.m9.world.migration_routes",
})


def _all_declared_metrics() -> set[str]:
    metrics: set[str] = set()
    for fixture in ACTIVATION_FIXTURES.values():
        metrics.update(fixture.activation_metrics)
    for scenario in SCENARIOS.values():
        metrics.update(scenario.entry_metrics)
        metrics.update(scenario.damage_metrics)
    for group in GROUP_SPECS.values():
        metrics.update(group.primary_metrics)
        metrics.update(group.tradeoff_metrics)
    for lever_metrics in LEVER_PROXIMAL_METRICS.values():
        metrics.update(lever_metrics)
    return metrics


def _materiality(metric_id: str) -> MaterialitySpec:
    if metric_id in _SHARE_METRICS:
        return MaterialitySpec(metric_id, 1.0e-3, 1.0e-3, 0.2, "post_burnin_mean")
    if metric_id in _RATE_METRICS:
        return MaterialitySpec(metric_id, 1.0e-6, 1.0e-3, 0.2, "post_burnin_mean")
    if metric_id in _COUNT_METRICS:
        return MaterialitySpec(metric_id, 1.0, 0.0, 0.2, "cumulative")
    if "exchange_rate" in metric_id or "price" in metric_id or "gini" in metric_id:
        return MaterialitySpec(metric_id, 1.0e-4, 1.0e-3, 0.2, "post_burnin_mean")
    return MaterialitySpec(metric_id, 1.0e-9, 1.0e-3, 0.2, "cumulative")


METRIC_MATERIALITY: Mapping[str, MaterialitySpec] = MappingProxyType({
    metric_id: _materiality(metric_id)
    for metric_id in sorted(_all_declared_metrics())
})


__all__ = [
    "ACTIVATION_FIXTURES",
    "CRISIS_ROLES",
    "FAILURE_TAXONOMY",
    "GROUP_SPECS",
    "LEVER_ACTIVATION_OVERRIDES",
    "LEVER_HORIZON_OVERRIDES",
    "LEVER_PROXIMAL_METRICS",
    "METRIC_MATERIALITY",
    "ORDINARY_SCENARIOS",
    "SCENARIOS",
    "STRUCTURAL_SCENARIOS",
    "ActivationFixtureSpec",
    "FailureClass",
    "GroupAuditSpec",
    "MaterialitySpec",
    "ScenarioSpec",
]
