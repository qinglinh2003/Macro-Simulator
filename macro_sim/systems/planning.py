"""Planning phase orchestration for the closed-economy simulator."""

from __future__ import annotations

from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.systems.securities import household_bond_value


def run_planning_phase(econ: Any) -> None:
    cfg = econ.cfg.planning

    # (a) update expectations from LAST tick's realized outcomes, BEFORE we
    #     reset this tick's accumulators.
    for h in econ.households:
        B.update_income_expectation(h)      # consumes h.income_realized (last tick)
    for f in econ.firms:
        B.update_demand_expectation(f)      # consumes f.sales_prev

    # (b) reset this-tick accumulators.
    for h in econ.households:
        h.income_realized = 0.0
        h.spent = 0.0
        h.consumption_budget = 0.0
        h.labor_sold = 0.0                  # v9: reset per-tick employment (for the benefit)
        h.jg_labor = 0.0                    # v9.3: reset per-tick job-guarantee employment
    for f in econ.firms:
        f.hired = f.produced = f.sales = 0.0
        f.revenue = f.wagebill = f.profit = 0.0
        f.investment = f.investment_target = f.dividend_shortfall = 0.0

    # (c) firm plans. Order (PLAN_v2 §1.5): production target -> NOTIONAL labor
    #     demand (needed by Cobb-Douglas unit cost) -> wage -> price (wage BEFORE
    #     price) -> cash-capped labor demand -> investment (C-firms, B5).
    for f in econ.firms:
        B.plan_production(f)
        f.labor_demand_notional = B.labor_demand_notional(f, f.production_target, econ._pubcap_factor)
        B.plan_wage(f, econ.rng, cfg.theta_wage, econ.policy.min_wage)
        B.plan_price(f, econ.rng, cfg.theta_price)
        # Continuous cash cap (§8.1: floor(D/w) is a cap, not integer employment).
        cash_cap = econ.ledger.balance(f.id) / f.wage
        f.labor_demand_eff = max(0.0, min(f.labor_demand_notional, cash_cap))
        if f.invests:
            B.plan_investment(f, cfg.lambda_q, cfg.q_invest_floor, cfg.q_invest_cap)  # B5 (+q, v6.1b)
            # v2.5 diagnostic (PLAN_v2 §1.1 disambiguation): force K-firms to at
            # least replace depreciation, removing the "never invests" failure so
            # any remaining collapse must be the structural absorbing state.
            if cfg.k_replacement_floor and f.sells == "capital":
                f.investment_target = max(f.investment_target, f.delta_K * f.capital)

    # (d) household consumption budget from expected income + wealth (deposits, plus the weighted equity
    #     wealth effect when v6's wealth_effect>0, plus v12.3 BOND wealth at market). Bonds are near-money
    #     (coupon-paying, sellable, maturing every <=bond_maturity ticks) so they enter the wealth term
    #     UNGATED by wealth_effect; 0 when bonds off => bit-identical. This is the v12.1-fix "no re-freeze"
    #     property made explicit: bond wealth supports consumption instead of being a frozen stone.
    we = cfg.wealth_effect
    for h in econ.households:
        bridge = getattr(econ, "demographic_bridge", None)
        if bridge is not None and getattr(cfg, "demographic_lifecycle_consumption", False):
            rates = getattr(econ, "demographic_rates", None)
            if rates is None:
                rates = getattr(getattr(econ, "demographic_state", None), "rates", None)
            if rates is None:
                raise RuntimeError("demographic lifecycle consumption requires demographic rates")
            h.consumption_budget = bridge.household_lifecycle_consumption_budget(
                h.id,
                rates,
                alpha_income=getattr(cfg, "lifecycle_alpha_income", h.alpha1),
                alpha_wealth_draw=getattr(cfg, "lifecycle_alpha_wealth_draw", 1.0),
            )
            continue
        B.plan_consumption(
            h,
            deposits_prev=econ.ledger.balance(h.id),
            equity_wealth=we * h.equity_value_ema + household_bond_value(econ, h.id),
            curvature=cfg.mpc_wealth_curvature,
            wealth_ref=cfg.d_household0,
        )
