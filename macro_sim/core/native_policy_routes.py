"""Audited native storage routes and first economic read points for Policy.

The control contract proves that a value can be written into native policy state.
This catalog goes one layer further: it names the first C++ simulation source that
reads the value, or records an explicit engine-route defect.  It intentionally lives
outside the generated M11 contract because read-point evidence is an audit artifact,
not an ABI field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


ROUTED = "routed"
ENGINE_ROUTE_DEFECT = "engine_route_defect"


@dataclass(frozen=True, slots=True)
class NativePolicyRoute:
    route_section: str
    route_field: str
    source_path: str
    source_anchor: str
    read_phase: str
    disposition: str = ROUTED
    defect_reason: str = ""

    @property
    def read_point(self) -> str:
        if self.disposition == ROUTED:
            return f"{self.source_path}::{self.source_anchor}"
        return f"{self.disposition}::{self.defect_reason}"


def _section_routes(
    *,
    section: str,
    fields: Mapping[str, str],
    source_path: str,
    source_prefix: str,
    read_phase: str,
) -> dict[str, NativePolicyRoute]:
    return {
        lever: NativePolicyRoute(
            route_section=section,
            route_field=field,
            source_path=source_path,
            source_anchor=f"{source_prefix}{field}",
            read_phase=read_phase,
        )
        for lever, field in fields.items()
    }


_FISCAL_MONETARY_FIELDS = {
    "bank_capital_constraint": "bank_capital_constraint",
    "bank_exposure_limit": "bank_exposure_limit",
    "bank_leverage_cap": "bank_leverage_cap",
    "bank_migrate_on_failure": "migrate_relationships_on_failure",
    "bank_target_capital_ratio": "bank_target_capital_ratio",
    "benefit_income_floor": "benefit_income_floor",
    "benefit_replacement": "unemployment_benefit_replacement",
    "cb_core_inflation": "core_inflation_sensor",
    "cb_log_inflation": "logarithmic_inflation",
    "deficit_u_cap": "deficit_unemployment_cap",
    "deficit_u_ref": "deficit_unemployment_reference",
    "deposit_rate_floor": "deposit_rate_floor",
    "firm_credit_min_dscr": "firm_minimum_dscr",
    "fiscal_uses_national_accounts_gdp": "fiscal_uses_national_accounts_gdp",
    "gov_consumption_share": "government_consumption_share",
    "gov_deficit_target": "government_deficit_target",
    "gov_investment_share": "government_investment_share",
    "hh_credit_limit": "household_credit_limit",
    "income_allowance": "income_allowance",
    "infl_ema_lambda": "inflation_sensor_lambda",
    "inflation_target": "inflation_target",
    "jg_public_works_share": "job_guarantee_public_works_share",
    "jg_wage_ratio": "job_guarantee_wage_ratio",
    "job_guarantee": "job_guarantee",
    "kappa": "firm_leverage_limit",
    "lolr": "lender_of_last_resort",
    "manual_policy_rate": "manual_policy_rate",
    "min_wage": "minimum_wage",
    "omo": "open_market_operations",
    "omo_drain_frac": "reserve_gap_close",
    "omo_index_deposits": "reserve_target_indexes_deposits",
    "omo_reserve_target": "reserve_target",
    "r_max": "maximum_policy_rate",
    "r_neutral": "neutral_rate",
    "rate_inertia": "rate_inertia",
    "reserve_floor_frac": "reserve_floor_fraction",
    "tax_consumption_rate": "consumption_tax_rate",
    "tax_income_rate": "income_tax_rate",
    "tax_luxury_rate": "luxury_consumption_tax_rate",
    "tax_necessity_rate": "necessity_consumption_tax_rate",
    "tax_profit_rate": "profit_tax_rate",
    "tax_wealth_rate": "wealth_tax_rate",
    "taylor_phi_pi": "taylor_inflation",
    "taylor_phi_u": "taylor_unemployment",
    "u_natural": "natural_unemployment",
    "unified_bank_rwa": "unified_bank_rwa",
    "wealth_allowance": "wealth_allowance",
}

_FINANCIAL_FIELDS = {
    "bank_bond_duration_limit": "bank_bond_duration_limit",
    "bank_min_capital": "bank_minimum_capital",
    "bankrupt_persist": "bankrupt_persistence",
    "bond_coupon": "bond_coupon_rate",
    "bond_finance_frac": "bond_finance_fraction",
    "bond_maturity": "bond_maturity_days",
    "household_bankruptcy": "household_bankruptcy",
    "margin_ltv": "margin_ltv",
    "margin_max": "margin_max",
    "regulatory_firm_capital_haircut": "regulatory_capital_haircut",
    "regulatory_firm_inventory_haircut": "regulatory_inventory_haircut",
}

_ENERGY_FIELDS = {
    "energy_cap_compensation": "price_cap_compensation",
    "energy_price_cap": "price_cap",
    "energy_subsidy_rate": "household_subsidy_rate",
    "energy_subsidy_threshold": "subsidy_deposit_threshold",
    "soe_efirm": "state_owned_first_producer",
    "soe_price_at_cost": "state_owned_price_at_cost",
    "spr_flow_cap": "strategic_reserve_flow_cap",
    "spr_target_units": "strategic_reserve_target",
    "tax_energy_rate": "excise_rate",
    "tax_energy_windfall": "windfall_tax_rate",
}

_HOUSING_FIELDS = {
    "housing_in_wealth_tax": "include_housing_in_wealth_tax",
    "housing_permits": "annual_housing_permits",
    "housing_property_tax": "property_tax_rate",
    "housing_transfer_tax": "transfer_tax_rate",
    "land_fee_share": "land_fee_share",
    "land_fee_stock_elasticity": "land_fee_stock_elasticity",
    "mortgage_arrears_floor": "mortgage_arrears_floor",
    "mortgage_dsti_cap": "mortgage_dsti_cap",
    "mortgage_foreclosure_ltv": "mortgage_foreclosure_ltv",
    "mortgage_ltv_cap": "mortgage_ltv_cap",
    "mortgage_min_capital_ratio": "mortgage_minimum_capital_ratio",
    "mortgage_risk_weight": "mortgage_risk_weight",
    "mortgage_stress_rate_addon": "mortgage_stress_rate_addon",
    "mortgage_underwriting": "mortgage_underwriting",
    "rental_eviction_arrears": "rental_eviction_arrears",
}

_EXTERNAL_FIELDS = {
    "capital_control": "capital_control",
    "emigration_cap": "emigration_cap",
    "export_subsidy": "export_subsidy",
    "external_interest_settlement_fraction": "external_interest_settlement_fraction",
    "fx_regime": "fx_regime",
    "guest_worker_return": "guest_worker_return",
    "immigration_cap": "immigration_cap",
    "import_quota": "import_quota",
    "outward_remittance_tax": "outward_remittance_tax",
    "peg_anchor": "peg_anchor",
    "peg_reserve_scale": "peg_reserve_scale",
    "remittance_tax": "remittance_tax",
    "sanctions_imposed_on": "sanctions_imposed_on",
    "tariff": "tariff",
}


NATIVE_POLICY_ROUTES: dict[str, NativePolicyRoute] = {}
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="fiscal_monetary",
    fields=_FISCAL_MONETARY_FIELDS,
    source_path="native/src/simulation/m5.cpp",
    source_prefix="runtime.policy.",
    read_phase="domestic_monetary_and_fiscal",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="financial",
    fields=_FINANCIAL_FIELDS,
    source_path="native/src/simulation/m6.cpp",
    source_prefix="runtime.policy.",
    read_phase="domestic_financial_and_securities",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="population",
    fields={"pension_replacement": "pension_replacement"},
    source_path="native/src/simulation/m7.cpp",
    source_prefix="runtime_.policy.",
    read_phase="population_and_labor",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="energy",
    fields=_ENERGY_FIELDS,
    source_path="native/src/simulation/m8.cpp",
    source_prefix="runtime_.energy_policy.",
    read_phase="energy_and_housing",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="housing",
    fields=_HOUSING_FIELDS,
    source_path="native/src/simulation/m8.cpp",
    source_prefix="runtime_.housing_policy.",
    read_phase="energy_and_housing",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="external",
    fields=_EXTERNAL_FIELDS,
    source_path="native/src/simulation/m9.cpp",
    source_prefix="policy.",
    read_phase="world_coupling",
))

# R2 contract-observability routes name the economic decision boundary rather
# than the policy-state member expression.  This makes cohort and gate evidence
# auditable at the point where the term is stamped or applied.
_R2_MECHANISM_ANCHORS = {
    "bond_coupon": "run_bond_issuance",
    "bond_maturity": "run_bond_issuance",
    "omo": "run_omo",
    "firm_credit_min_dscr": "stage_m5_firm_plan_credit",
    "regulatory_firm_capital_haircut": "build_firm_statements",
    "regulatory_firm_inventory_haircut": "build_firm_statements",
    "mortgage_underwriting": "buy_listing",
    "mortgage_dsti_cap": "buy_listing",
    "mortgage_stress_rate_addon": "buy_listing",
    "housing_in_wealth_tax": "prepare_household_net_wealth",
    "land_fee_share": "complete_construction",
    "land_fee_stock_elasticity": "complete_construction",
}
for _lever, _anchor in _R2_MECHANISM_ANCHORS.items():
    _route = NATIVE_POLICY_ROUTES[_lever]
    NATIVE_POLICY_ROUTES[_lever] = NativePolicyRoute(
        route_section=_route.route_section,
        route_field=_route.route_field,
        source_path=_route.source_path,
        source_anchor=_anchor,
        read_phase=_route.read_phase,
    )

# R3 closes the remaining native route gaps and names the repaired decision
# boundary for policies whose earlier read point was only storage or validation.
_R3_MECHANISM_ANCHORS = {
    "fiscal_uses_national_accounts_gdp": (
        "native/src/simulation/m4.cpp",
        "fiscal_output_reference",
        "domestic_fiscal_budgeting",
    ),
    "bank_capital_constraint": (
        "native/src/simulation/m5.cpp",
        "bank_capacity",
        "domestic_credit_allocation",
    ),
    "mortgage_risk_weight": (
        "native/src/simulation/m8.cpp",
        "m5_bank_rwa_principal_capacity",
        "housing_mortgage_underwriting",
    ),
    "mortgage_min_capital_ratio": (
        "native/src/simulation/m8.cpp",
        "m5_bank_rwa_principal_capacity",
        "housing_mortgage_underwriting",
    ),
    "mortgage_arrears_floor": (
        "native/src/simulation/m8.cpp",
        "synchronize_mortgages",
        "housing_mortgage_resolution",
    ),
    "deficit_u_cap": (
        "native/src/simulation/m4.cpp",
        "run_government_procurement",
        "domestic_fiscal_budgeting",
    ),
}
for _lever, (_source, _anchor, _phase) in _R3_MECHANISM_ANCHORS.items():
    _route = NATIVE_POLICY_ROUTES[_lever]
    NATIVE_POLICY_ROUTES[_lever] = NativePolicyRoute(
        route_section=_route.route_section,
        route_field=_route.route_field,
        source_path=_source,
        source_anchor=_anchor,
        read_phase=_phase,
    )

# External policies are validated through a local ``policy`` reference, so use
# the concrete world-coupling expression rather than allowing validation to
# masquerade as an economic read point.
_EXTERNAL_MECHANISM_ANCHORS = {
    "capital_control": "staged.external_policies_[investor].capital_control",
    "emigration_cap": "staged.external_policies_[origin].emigration_cap",
    "export_subsidy": "staged.external_policies_[source].export_subsidy",
    "external_interest_settlement_fraction": (
        "staged.external_policies_[debtor]\n"
        "                                            .external_interest_settlement_fraction"
    ),
    "fx_regime": "if (policy.fx_regime == FxRegime::peg)",
    "guest_worker_return": "staged.external_policies_[origin].guest_worker_return",
    "immigration_cap": "staged.external_policies_[host].immigration_cap",
    "import_quota": "staged.external_policies_[importer].import_quota",
    "outward_remittance_tax": (
        "staged.external_policies_[host].outward_remittance_tax"
    ),
    "peg_anchor": "*policy.peg_anchor",
    "peg_reserve_scale": "staged.external_policies_[pegger].peg_reserve_scale",
    "remittance_tax": "staged.external_policies_[origin].remittance_tax",
    "sanctions_imposed_on": "external_policies_[first].sanctions_imposed_on",
    "tariff": "staged.external_policies_[importer].tariff",
}
for _lever, _anchor in _EXTERNAL_MECHANISM_ANCHORS.items():
    _route = NATIVE_POLICY_ROUTES[_lever]
    NATIVE_POLICY_ROUTES[_lever] = NativePolicyRoute(
        route_section=_route.route_section,
        route_field=_route.route_field,
        source_path=_route.source_path,
        source_anchor=_anchor,
        read_phase=_route.read_phase,
    )

# These consumers bind a local policy reference rather than reading through the
# runtime member expression used by the rest of their section.
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="fiscal_monetary",
    fields={
        "cb_core_inflation": "core_inflation_sensor",
        "cb_log_inflation": "logarithmic_inflation",
        "infl_ema_lambda": "inflation_sensor_lambda",
        "manual_policy_rate": "manual_policy_rate",
        "r_max": "maximum_policy_rate",
        "rate_inertia": "rate_inertia",
        "taylor_phi_pi": "taylor_inflation",
        "taylor_phi_u": "taylor_unemployment",
        "u_natural": "natural_unemployment",
    },
    source_path="native/src/simulation/m5.cpp",
    source_prefix="policy.",
    read_phase="domestic_monetary_and_fiscal",
))
NATIVE_POLICY_ROUTES.update(_section_routes(
    section="energy",
    fields={
        "spr_flow_cap": "strategic_reserve_flow_cap",
        "spr_target_units": "strategic_reserve_target",
    },
    source_path="native/src/simulation/m8.cpp",
    source_prefix="policy.",
    read_phase="energy_and_housing",
))

# These generated-contract special routes map to concrete native policy fields.
NATIVE_POLICY_ROUTES.update({
    "bank_resolution_fund": NativePolicyRoute(
        "special", "bank_resolution_fund", "native/src/simulation/m6.cpp",
        "runtime.policy.bank_resolution_fund", "domestic_financial_and_securities",
    ),
    "energy_rationing": NativePolicyRoute(
        "special", "energy_rationing", "native/src/simulation/m8.cpp",
        "runtime_.energy_policy.rationing", "energy_and_housing",
    ),
    "monetary_regime": NativePolicyRoute(
        "special", "monetary_regime", "native/src/simulation/m5.cpp",
        "policy.monetary_regime", "domestic_monetary_and_fiscal",
    ),
    "cb_uses_fixed_basket_cpi": NativePolicyRoute(
        "fiscal_monetary", "fixed_basket_cpi", "native/src/simulation/m8.cpp",
        "monetary.policy.fixed_basket_cpi", "energy_and_housing",
    ),
})

NATIVE_ROUTE_DEFECTS = frozenset(
    name
    for name, route in NATIVE_POLICY_ROUTES.items()
    if route.disposition == ENGINE_ROUTE_DEFECT
)
