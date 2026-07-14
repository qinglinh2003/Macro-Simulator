"""Planning phase orchestration for the closed-economy simulator."""

from __future__ import annotations

from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.systems.banking import loan_rate_for
from macro_sim.systems.securities import household_bond_value
from macro_sim.systems.firm_accounting import (
    committed_replacement_capital_price,
    reset_firm_pnl_flows,
)


# Every production sector that can carry productive capital belongs in the
# long-run replacement-cost quote.  Keep this set authoritative for planning,
# reporting and diagnostics: duplicating the old C/K-only tuple is what left the
# capital-using energy sector priced as if its capacity were free.
CAPITAL_SERVICE_PRICED_SECTORS = frozenset({"consumption", "capital", "energy"})


def run_planning_phase(econ: Any) -> None:
    cfg = econ.cfg.planning
    full_pnl = getattr(cfg, "firm_full_pnl", False)
    direct_monetary = getattr(cfg, "monetary_direct_transmission", False)
    if full_pnl:
        econ._firm_pnl_closed = False
    if direct_monetary:
        econ._hh_debt_service_reserved = 0.0

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
        h.energy_spent = h.energy_units = 0.0   # v17.1: reset per-tick household energy
    for f in econ.firms:
        f.hired = f.produced = f.sales = 0.0
        f.revenue = f.wagebill = f.profit = 0.0
        f.investment = f.investment_target = f.dividend_shortfall = 0.0
        if full_pnl:
            reset_firm_pnl_flows(f)

    # (c) firm plans. Order (PLAN_v2 §1.5): production target -> NOTIONAL labor
    #     demand (needed by Cobb-Douglas unit cost) -> wage -> price (wage BEFORE
    #     price) -> cash-capped labor demand -> investment (C-firms, B5).
    capital_price = (
        committed_replacement_capital_price(econ)
        if getattr(cfg, "capital_service_pricing", False)
        else 0.0
    )
    for f in econ.firms:
        B.plan_production(f, cfg.inventory_gap_close)
        if f.capacity_kappa > 0.0:
            # v17.0 capacity edge (E-firms): never plan past kappa*K, so labor demand is
            # capped at the capacity-implied headcount (short-run supply inelasticity).
            f.production_target = min(f.production_target, f.capacity_kappa * f.capital)
        f.labor_demand_notional = B.labor_demand_notional(f, f.production_target, econ._output_factor(f))
        # v23: wage setting now reads COMMITTED inflation expectations -- the same lag/EMA the
        # monetary transmission uses, never this tick's price -- so the labour-tightness terms
        # apply to the REAL wage. wage_indexation=0 collapses this to the original rule exactly.
        B.plan_wage(
            f, econ.rng, cfg.theta_wage, econ.policy.min_wage, cfg.delta,
            expected_inflation=float(
                econ._infl_ema if econ.cfg.central_bank else econ._prev_inflation
            ),
            wage_indexation=float(getattr(cfg, "wage_indexation", 0.0)),
        )
        if (
            getattr(cfg, "capital_service_pricing", False)
            and f.sells in CAPITAL_SERVICE_PRICED_SECTORS
        ):
            opportunity_rate = max(0.0, float(loan_rate_for(econ, f.id)))
            f.pricing_capital_price = capital_price
            f.pricing_capital_service_rate = max(0.0, float(f.delta_K)) + opportunity_rate
            f.pricing_capital_service_cost = B.capital_service_cost(
                f,
                replacement_price=capital_price,
                opportunity_rate=opportunity_rate,
            )
            f.pricing_capital_unit_cost = B.capital_service_unit_cost(
                f,
                replacement_price=capital_price,
                opportunity_rate=opportunity_rate,
            )
            B.plan_price(
                f,
                econ.rng,
                cfg.theta_price,
                f.pricing_capital_unit_cost,
                productivity_adjusted=True,
            )
        else:
            # Historical presets priced linear technology at ``w / a`` even when
            # public capital raised output.  The v23 long-run pricing frontier
            # intentionally migrates to planned wage bill / planned output, while
            # an omitted migration flag remains bit-compatible with certified
            # version presets.
            B.plan_price(
                f,
                econ.rng,
                cfg.theta_price,
                productivity_adjusted=False,
            )
        # Continuous cash cap (§8.1: floor(D/w) is a cap, not integer employment).
        cash_cap = econ.ledger.balance(f.id) / f.wage
        f.labor_demand_eff = max(0.0, min(f.labor_demand_notional, cash_cap))
        if f.invests:
            if direct_monetary:
                # The inflation expectation is committed observation state only.  With
                # a live CB, set_policy_rate has just updated the EMA from t-1's committed
                # sensor; without it, use the committed one-period lag directly.
                expected_inflation = float(
                    econ._infl_ema if econ.cfg.central_bank else econ._prev_inflation
                )
                current_loan_rate = float(loan_rate_for(econ, f.id))
                current_policy_rate = max(0.0, float(econ._rate))
                pass_through_spread = current_loan_rate - current_policy_rate
                neutral_loan_rate = max(
                    0.0,
                    float(econ.cfg.central_banking.r_neutral) + pass_through_spread,
                )
                B.plan_investment(
                    f,
                    cfg.lambda_q,
                    cfg.q_invest_floor,
                    cfg.q_invest_cap,
                    nominal_loan_rate=current_loan_rate,
                    expected_inflation=expected_inflation,
                    neutral_nominal_rate=neutral_loan_rate,
                    inflation_target=float(econ.policy.inflation_target),
                    user_cost_elasticity=cfg.investment_user_cost_elasticity,
                    user_cost_multiplier_min=cfg.investment_user_cost_multiplier_min,
                    user_cost_multiplier_max=cfg.investment_user_cost_multiplier_max,
                    user_cost_floor=cfg.investment_user_cost_floor,
                )
            else:
                B.plan_investment(f, cfg.lambda_q, cfg.q_invest_floor, cfg.q_invest_cap)  # B5 (+q, v6.1b)
            # v2.5 diagnostic (PLAN_v2 §1.1 disambiguation): force K-firms to at
            # least replace depreciation, removing the "never invests" failure so
            # any remaining collapse must be the structural absorbing state.
            if cfg.k_replacement_floor and f.sells == "capital":
                f.investment_target = max(f.investment_target, f.delta_K * f.capital)
            # v17.0: E-firms carry the same floor UNCONDITIONALLY -- it is an existence
            # condition, not a diagnostic: a demand slump zeroes the accelerator, K
            # depreciates away, and a dead E-sector is ABSORBING (recovery demand cannot
            # be produced, sales stay 0, d^e stays 0 -- found in the v124+energy probe).
            if f.sells == "energy":
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

    # v15.5: housing wealth effect (default 0 = off). Deliberately a separate, WEAK dial:
    # the honest default is the emergent down-payment effect (buying drains deposits and
    # the alpha2 term contracts consumption); this flag adds the "feeling richer" channel
    # on top for policy experiments, on BOTH consumption paths.
    hwe = float(getattr(cfg, "housing_wealth_effect", 0.0))
    housing = getattr(econ, "housing", None)
    if hwe > 0.0 and housing is not None:
        alpha2 = cfg.alpha2
        price = float(getattr(econ, "_house_price", 0.0))
        for h in econ.households:
            units = housing.units_of(h.id)
            if units > 0.0:
                h.consumption_budget += hwe * alpha2 * units * price

    # Keep ``consumption_budget`` as the household's desired nominal demand.  The
    # cash needed for debt service is reserved at the goods-order boundary, after
    # current wages, household credit and family transfers have arrived.  Capping
    # here against opening deposits used to suppress otherwise affordable demand
    # permanently for households paid later in the same tick.
