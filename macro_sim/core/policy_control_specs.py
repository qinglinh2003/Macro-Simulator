"""Controller-facing authority, timing, and adjustment metadata.

``policy_registry.REGISTRY`` remains the validation and runtime-effectiveness
source of truth.  This module is the reviewed C1 control-plane companion: it
assigns exactly one institutional owner and one decision cadence to every
canonical lever, and gives controllers explicit implementation, hold, scale,
step, administrative-cost, and emergency rulings.

The values here are deliberately expressed in simulation ticks.  Calendar
objects may choose when a decision group meets, but may not reinterpret these
per-lever lags or minimum holds.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

@dataclass(frozen=True)
class LeverControlSpec:
    """Procedural metadata for one canonical policy lever."""

    owner_role: str
    decision_group: str
    implementation_lag: int
    emergency_implementation_lag: int | None
    min_hold_ticks: int
    emergency: bool
    control_scale: float | None
    max_step: float | None
    admin_weight: float
    cost_class: str


def _S(
    owner_role: str,
    decision_group: str,
    implementation_lag: int,
    min_hold_ticks: int,
    *,
    emergency: bool = False,
    emergency_implementation_lag: int | None = None,
    control_scale: float | None = None,
    max_step: float | None = None,
    admin_weight: float = 1.0,
    cost_class: str = "ordinary",
) -> LeverControlSpec:
    """Compact constructor; every economic ruling remains visible per row."""

    return LeverControlSpec(
        owner_role=owner_role,
        decision_group=decision_group,
        implementation_lag=implementation_lag,
        emergency_implementation_lag=emergency_implementation_lag,
        min_hold_ticks=min_hold_ticks,
        emergency=emergency,
        control_scale=control_scale,
        max_step=max_step,
        admin_weight=admin_weight,
        cost_class=cost_class,
    )


# The order mirrors REGISTRY so this is also a practical 102-row review table.
CONTROL_SPECS: dict[str, LeverControlSpec] = {
    # -- Treasury: fiscal stance and social protection -------------------
    "gov_consumption_share": _S(
        "treasury", "fiscal_stance", 7, 45, emergency=True,
        emergency_implementation_lag=1, control_scale=0.01, max_step=0.05,
    ),
    "gov_deficit_target": _S(
        "treasury", "fiscal_stance", 7, 45, emergency=True,
        emergency_implementation_lag=1, control_scale=0.005, max_step=0.02,
    ),
    "deficit_u_ref": _S(
        "treasury", "fiscal_stance", 7, 91,
        control_scale=0.05, max_step=0.20,
    ),
    "benefit_replacement": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
    ),
    "benefit_income_floor": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
    ),
    "pension_replacement": _S(
        "treasury", "fiscal_stance", 30, 365,
        control_scale=0.05, max_step=0.20, admin_weight=2.0,
        cost_class="major",
    ),

    # -- Treasury: structural taxes -------------------------------------
    "tax_profit_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "tax_income_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "income_allowance": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.10, max_step=0.50, admin_weight=2.0,
        cost_class="major",
    ),
    "tax_consumption_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "tax_necessity_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "tax_luxury_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "tax_wealth_rate": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.001, max_step=0.005, admin_weight=2.0,
        cost_class="major",
    ),
    "wealth_allowance": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.25, max_step=1.0, admin_weight=2.0,
        cost_class="major",
    ),

    # Energy levies and fiscal support stay with Treasury, not the operator.
    "tax_energy_rate": _S(
        "treasury", "tax_and_transfers", 14, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
        admin_weight=2.0, cost_class="major",
    ),
    "tax_energy_windfall": _S(
        "treasury", "tax_and_transfers", 30, 91, emergency=True,
        emergency_implementation_lag=7, control_scale=0.025, max_step=0.10,
        admin_weight=2.0, cost_class="major",
    ),

    # -- Energy authority: reserve and market operations -----------------
    "spr_target_units": _S(
        "energy", "energy_operations", 7, 30, emergency=True,
        emergency_implementation_lag=0, control_scale=10_000.0,
        max_step=100_000.0, admin_weight=0.5, cost_class="operational",
    ),
    "spr_flow_cap": _S(
        "energy", "energy_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, control_scale=100.0,
        max_step=1_000.0, admin_weight=0.5, cost_class="operational",
    ),
    "soe_price_at_cost": _S(
        "energy", "energy_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, admin_weight=0.5,
        cost_class="operational",
    ),
    "energy_price_cap": _S(
        "energy", "energy_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, control_scale=0.10, max_step=1.0,
        admin_weight=0.5, cost_class="operational",
    ),
    "energy_rationing": _S(
        "energy", "energy_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, admin_weight=0.5,
        cost_class="operational",
    ),

    # Compensation and subsidies spend Treasury resources.
    "energy_cap_compensation": _S(
        "treasury", "tax_and_transfers", 7, 30, emergency=True,
        emergency_implementation_lag=1, admin_weight=2.0, cost_class="major",
    ),
    "energy_subsidy_rate": _S(
        "treasury", "tax_and_transfers", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
        admin_weight=2.0, cost_class="major",
    ),
    "energy_subsidy_threshold": _S(
        "treasury", "tax_and_transfers", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.25, max_step=1.0,
        admin_weight=2.0, cost_class="major",
    ),

    # -- Treasury: labour and automatic stabilizers ----------------------
    "min_wage": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.05, max_step=0.25, admin_weight=2.0,
        cost_class="major",
    ),
    "job_guarantee": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, admin_weight=2.0, cost_class="major",
    ),
    "jg_wage_ratio": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
    ),

    # -- Central bank: monetary decisions -------------------------------
    "inflation_target": _S(
        "central_bank", "monetary_stance", 1, 365,
        control_scale=0.00025, max_step=0.001, admin_weight=2.0,
        cost_class="major",
    ),
    "taylor_phi_pi": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.10, max_step=0.50,
    ),
    "taylor_phi_u": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.10, max_step=0.50,
    ),
    "rate_inertia": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.025, max_step=0.10,
    ),
    "manual_policy_rate": _S(
        "central_bank", "monetary_stance", 0, 5, emergency=True,
        emergency_implementation_lag=0, control_scale=0.0001,
        max_step=0.001, admin_weight=0.5, cost_class="operational",
    ),
    "monetary_regime": _S(
        "central_bank", "monetary_stance", 1, 45, emergency=True,
        emergency_implementation_lag=0, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "r_neutral": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.0005, max_step=0.0025,
    ),
    "u_natural": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.005, max_step=0.02,
    ),
    "r_max": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.005, max_step=0.025,
    ),
    "infl_ema_lambda": _S(
        "central_bank", "monetary_stance", 1, 91,
        control_scale=0.01, max_step=0.05,
    ),
    "cb_core_inflation": _S(
        "central_bank", "monetary_stance", 7, 365, admin_weight=2.0,
        cost_class="major",
    ),
    "cb_uses_fixed_basket_cpi": _S(
        "central_bank", "monetary_stance", 7, 365, admin_weight=2.0,
        cost_class="major",
    ),
    "cb_log_inflation": _S(
        "central_bank", "monetary_stance", 7, 365, admin_weight=2.0,
        cost_class="major",
    ),

    # Fiscal measurement is an accounting-rule choice made by Treasury.
    "fiscal_uses_national_accounts_gdp": _S(
        "treasury", "fiscal_stance", 30, 365, admin_weight=2.0,
        cost_class="major",
    ),

    # -- Treasury: debt management --------------------------------------
    "bond_finance_frac": _S(
        "treasury", "debt_management", 7, 45, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
    ),
    "bond_coupon": _S(
        "treasury", "debt_management", 1, 45,
        control_scale=0.0001, max_step=0.001,
    ),
    "bond_maturity": _S(
        "treasury", "debt_management", 1, 91,
        control_scale=365.0, max_step=3_650.0,
    ),

    # -- Central bank: standing liquidity facilities --------------------
    "omo": _S(
        "central_bank", "liquidity_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, admin_weight=0.5,
        cost_class="operational",
    ),
    "omo_reserve_target": _S(
        "central_bank", "liquidity_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, control_scale=0.05, max_step=0.25,
        admin_weight=0.5, cost_class="operational",
    ),
    "omo_drain_frac": _S(
        "central_bank", "liquidity_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, control_scale=0.05, max_step=0.25,
        admin_weight=0.5, cost_class="operational",
    ),
    "lolr": _S(
        "central_bank", "liquidity_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, admin_weight=0.5,
        cost_class="operational",
    ),

    # -- Regulator: banks and credit ------------------------------------
    "bank_capital_constraint": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "bank_leverage_cap": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.50, max_step=2.0,
    ),
    "bank_target_capital_ratio": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.01, max_step=0.05,
    ),
    "bank_exposure_limit": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "bank_min_capital": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=1_000.0,
        max_step=10_000.0,
    ),
    "bank_bond_duration_limit": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.50, max_step=2.0,
    ),
    "bank_resolution_fund": _S(
        "regulator", "structural_law", 30, 365, emergency=True,
        emergency_implementation_lag=0, admin_weight=3.0,
        cost_class="regime_switch",
    ),

    # Reserve requirements are monetary/liquidity tools in the P0 seat map.
    "reserve_floor_frac": _S(
        "central_bank", "liquidity_operations", 1, 30, emergency=True,
        emergency_implementation_lag=0, control_scale=0.025, max_step=0.10,
        admin_weight=0.5, cost_class="operational",
    ),

    "margin_ltv": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "margin_max": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.25, max_step=1.0,
    ),
    "kappa": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.25, max_step=1.0,
    ),
    "hh_credit_limit": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.25, max_step=1.0,
    ),
    "mortgage_ltv_cap": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "mortgage_underwriting": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, admin_weight=2.0, cost_class="major",
    ),
    "mortgage_dsti_cap": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "mortgage_stress_rate_addon": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.0001,
        max_step=0.0005,
    ),
    "mortgage_risk_weight": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "mortgage_min_capital_ratio": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.01, max_step=0.05,
    ),
    "mortgage_foreclosure_ltv": _S(
        "regulator", "structural_law", 30, 365,
        control_scale=0.05, max_step=0.20, admin_weight=2.0,
        cost_class="major",
    ),
    "mortgage_arrears_floor": _S(
        "regulator", "structural_law", 30, 365,
        control_scale=0.50, max_step=2.0, admin_weight=2.0,
        cost_class="major",
    ),

    # -- Treasury: housing supply and property taxes ---------------------
    "housing_permits": _S(
        "treasury", "fiscal_stance", 30, 91,
        control_scale=10.0, max_step=100.0, admin_weight=2.0,
        cost_class="major",
    ),
    "housing_transfer_tax": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.01, max_step=0.05, admin_weight=2.0,
        cost_class="major",
    ),
    "housing_property_tax": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.0025, max_step=0.01, admin_weight=2.0,
        cost_class="major",
    ),
    "housing_in_wealth_tax": _S(
        "treasury", "tax_and_transfers", 30, 365, admin_weight=2.0,
        cost_class="major",
    ),

    "jg_public_works_share": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
    ),
    "deposit_rate_floor": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.0001,
        max_step=0.0005,
    ),
    "deficit_u_cap": _S(
        "treasury", "fiscal_stance", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.10, max_step=0.50,
    ),
    "gov_investment_share": _S(
        "treasury", "fiscal_stance", 30, 91,
        control_scale=0.005, max_step=0.02, admin_weight=2.0,
        cost_class="major",
    ),
    "omo_index_deposits": _S(
        "central_bank", "liquidity_operations", 7, 91, emergency=True,
        emergency_implementation_lag=0, admin_weight=2.0,
        cost_class="major",
    ),

    # -- Regulator: insolvency and resolution law -----------------------
    "bankrupt_persist": _S(
        "regulator", "structural_law", 30, 365,
        control_scale=30.0, max_step=180.0, admin_weight=2.0,
        cost_class="major",
    ),
    "household_bankruptcy": _S(
        "regulator", "structural_law", 30, 365, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "rental_eviction_arrears": _S(
        "regulator", "structural_law", 30, 365,
        control_scale=30.0, max_step=180.0, admin_weight=2.0,
        cost_class="major",
    ),
    "bank_migrate_on_failure": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=0, admin_weight=2.0, cost_class="major",
    ),
    "unified_bank_rwa": _S(
        "regulator", "structural_law", 30, 365, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "firm_credit_min_dscr": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.10, max_step=0.50,
    ),
    "regulatory_firm_capital_haircut": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),
    "regulatory_firm_inventory_haircut": _S(
        "regulator", "macroprudential", 7, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
    ),

    # Land fees are public-revenue/supply choices owned by Treasury.
    "land_fee_share": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.025, max_step=0.10, admin_weight=2.0,
        cost_class="major",
    ),
    "land_fee_stock_elasticity": _S(
        "treasury", "tax_and_transfers", 30, 365,
        control_scale=0.10, max_step=0.50, admin_weight=2.0,
        cost_class="major",
    ),

    # SOE ownership is an energy-sector structural decision, not a tax tool.
    "soe_efirm": _S(
        "energy", "energy_structure", 30, 365, admin_weight=3.0,
        cost_class="regime_switch",
    ),

    # -- External affairs: trade, sanctions, and migration ---------------
    "tariff": _S(
        "external_affairs", "trade_and_migration", 14, 91,
        control_scale=0.05, max_step=0.25,
    ),
    "import_quota": _S(
        "external_affairs", "trade_and_migration", 14, 91,
        control_scale=1.0, max_step=10.0,
    ),
    "export_subsidy": _S(
        "external_affairs", "trade_and_migration", 14, 91,
        control_scale=0.025, max_step=0.10,
    ),

    # Capital-account plumbing belongs to the central bank in the P0 map.
    "capital_control": _S(
        "central_bank", "fx_operations", 7, 30, emergency=True,
        emergency_implementation_lag=0, control_scale=0.05, max_step=0.20,
        admin_weight=1.0, cost_class="operational",
    ),
    "external_interest_settlement_fraction": _S(
        "central_bank", "fx_operations", 7, 30, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.20,
        admin_weight=1.0, cost_class="operational",
    ),

    "sanctions_imposed_on": _S(
        "external_affairs", "trade_and_migration", 1, 30, emergency=True,
        emergency_implementation_lag=0, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "immigration_cap": _S(
        "external_affairs", "trade_and_migration", 30, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.05, max_step=0.25,
        admin_weight=2.0, cost_class="major",
    ),
    "emigration_cap": _S(
        "external_affairs", "trade_and_migration", 30, 91, emergency=True,
        emergency_implementation_lag=1, control_scale=0.025, max_step=0.10,
        admin_weight=2.0, cost_class="major",
    ),
    "remittance_tax": _S(
        "external_affairs", "trade_and_migration", 14, 91,
        control_scale=0.025, max_step=0.10,
    ),
    "outward_remittance_tax": _S(
        "external_affairs", "trade_and_migration", 14, 91,
        control_scale=0.025, max_step=0.10,
    ),
    "guest_worker_return": _S(
        "external_affairs", "trade_and_migration", 30, 91,
        control_scale=0.025, max_step=0.10,
    ),

    # -- Central bank: FX regime and peg operations ----------------------
    "fx_regime": _S(
        "central_bank", "fx_operations", 7, 91, emergency=True,
        emergency_implementation_lag=0, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "peg_anchor": _S(
        "central_bank", "fx_operations", 7, 91, emergency=True,
        emergency_implementation_lag=0, admin_weight=3.0,
        cost_class="regime_switch",
    ),
    "peg_reserve_scale": _S(
        "central_bank", "fx_operations", 1, 7, emergency=True,
        emergency_implementation_lag=0, control_scale=10_000.0,
        max_step=100_000.0, admin_weight=0.5, cost_class="operational",
    ),
}


_OWNER_ROLES = frozenset({
    "central_bank", "treasury", "regulator", "external_affairs", "energy",
})
_COST_CLASSES = frozenset({"ordinary", "major", "regime_switch", "operational"})


def _validate_control_specs() -> None:
    """Fail at import time if Registry and the reviewed table drift apart."""

    # Delayed until after CONTROL_SPECS exists so policy_registry may safely
    # import this table at the end of its own initialization to enrich Lever
    # objects.  This keeps either direct import order deterministic.
    from macro_sim.core.policy_registry import REGISTRY, Range

    registry_names = set(REGISTRY)
    spec_names = set(CONTROL_SPECS)
    if spec_names != registry_names:
        missing = sorted(registry_names - spec_names)
        extra = sorted(spec_names - registry_names)
        raise RuntimeError(
            f"CONTROL_SPECS must exactly cover REGISTRY; missing={missing}, extra={extra}"
        )

    for name, lever in REGISTRY.items():
        spec = CONTROL_SPECS[name]
        if spec.owner_role not in _OWNER_ROLES:
            raise RuntimeError(f"{name}: unknown owner_role {spec.owner_role!r}")
        if not spec.decision_group:
            raise RuntimeError(f"{name}: decision_group must be non-empty")
        if (
            isinstance(spec.implementation_lag, bool)
            or not isinstance(spec.implementation_lag, int)
            or spec.implementation_lag < 0
        ):
            raise RuntimeError(f"{name}: implementation_lag must be a non-negative int")
        if (
            isinstance(spec.min_hold_ticks, bool)
            or not isinstance(spec.min_hold_ticks, int)
            or spec.min_hold_ticks < 0
        ):
            raise RuntimeError(f"{name}: min_hold_ticks must be a non-negative int")
        if spec.emergency:
            lag = spec.emergency_implementation_lag
            if isinstance(lag, bool) or not isinstance(lag, int) or lag < 0:
                raise RuntimeError(
                    f"{name}: an emergency lever needs a non-negative emergency lag"
                )
            if lag > spec.implementation_lag:
                raise RuntimeError(
                    f"{name}: emergency lag cannot exceed regular implementation lag"
                )
        elif spec.emergency_implementation_lag is not None:
            raise RuntimeError(f"{name}: non-emergency lever declares an emergency lag")

        numeric = isinstance(lever.validation, Range)
        if numeric:
            for field_name, value in (
                ("control_scale", spec.control_scale),
                ("max_step", spec.max_step),
            ):
                if value is None or not math.isfinite(value) or value <= 0.0:
                    raise RuntimeError(
                        f"{name}: numeric lever needs finite positive {field_name}"
                    )
            if spec.control_scale > spec.max_step:
                raise RuntimeError(f"{name}: control_scale cannot exceed max_step")
        elif spec.control_scale is not None or spec.max_step is not None:
            raise RuntimeError(f"{name}: non-numeric lever must not declare numeric controls")

        if not math.isfinite(spec.admin_weight) or spec.admin_weight <= 0.0:
            raise RuntimeError(f"{name}: admin_weight must be finite and positive")
        if spec.cost_class not in _COST_CLASSES:
            raise RuntimeError(f"{name}: unknown cost_class {spec.cost_class!r}")


_validate_control_specs()


__all__ = ["LeverControlSpec", "CONTROL_SPECS"]
