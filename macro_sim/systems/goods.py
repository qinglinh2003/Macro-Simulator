"""Consumption-goods market phase orchestration."""

from __future__ import annotations

from typing import Any, Dict, List

from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS, BuyOrder, SellOffer, execute_market


def run_goods_phase(econ: Any) -> None:
    # Buyers: households with a budget = min(desired budget, LIVE deposits) (A4).
    # The desired budget may exceed this tick's wage income (alpha2 wealth
    # channel) -- do NOT clamp to income; clamp only to live deposits.
    cfg = econ.cfg.goods
    econ._tax_consumption = econ._gov_consumption = 0.0
    gov = cfg.government
    tc = econ.policy.tax_consumption_rate if gov else 0.0
    orders: List[BuyOrder] = []
    for h in econ.households:
        budget = min(h.consumption_budget, econ.ledger.balance(h.id))
        if budget <= EPS:
            continue
        # v9 VAT: the outlay budget buys goods worth budget/(1+tax); the rest is reserved for tax.
        orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=budget / (1.0 + tc), ref=h))
    hh_budget_total = sum(o.budget for o in orders)     # notional household spend (for unsat ratio)

    # v9 government procurement budget/units (spent below via a competitive tender, not the household
    # preferential market). Two modes: deficit-targeting (spend last-tick revenue + target*GDP -
    # last-tick benefit, so the deficit is near target*GDP), or quantity (g*potential_output real units).
    gov_budget, gov_units = 0.0, float("inf")
    if gov:
        pol = econ.policy
        if pol.gov_deficit_target > 0.0:
            target = pol.gov_deficit_target
            if pol.deficit_u_ref > 0.0:      # state-dependent: taper toward balance at full employment
                # v13: the multiplier used to be capped at 1.0, so fiscal policy pushed no harder
                # at 30% unemployment than at 5% -- the ZLB slump had no fiscal counterweight.
                # deficit_u_cap > 1 lets the deficit target scale with slack (still tapering to
                # balance at full employment); cap 1.0 reproduces v12 exactly.
                cap = float(getattr(econ.cfg, "deficit_u_cap", 1.0))
                target *= min(cap, getattr(econ, "_prev_u", pol.deficit_u_ref) / pol.deficit_u_ref)
            gov_budget = max(
                0.0,
                getattr(econ, "_prev_tax_total", 0.0)
                + target * getattr(econ, "_prev_nominal_output", 0.0)
                - getattr(econ, "_prev_benefit", 0.0),
            )
        elif pol.gov_consumption_share > 0.0:
            gov_units = pol.gov_consumption_share * len(econ.households) * cfg.a
            gov_budget = float("inf")

    # Sellers are the consumption sector only (K-firms sell in Phase 3.5).
    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.c_firms]
    trades = execute_market(orders, offers, protocol=econ.protocol, rng=econ.rng, ledger=econ.ledger)

    # Push realized results back onto agents.
    spent_by: Dict[str, float] = {}
    for tr in trades:
        spent_by[tr.buyer] = spent_by.get(tr.buyer, 0.0) + tr.value
    for h in econ.households:
        h.spent = spent_by.get(h.id, 0.0)
    bridge = getattr(econ, "demographic_bridge", None)
    if bridge is not None:
        for h in econ.households:
            if h.spent > EPS:
                bridge.post_household_consumption(h.id, h.spent)
    econ._gov_consumption = spent_by.get(econ._fiscal, 0.0)      # government's realised real purchases
    for off in offers:
        f: Firm = off.ref
        f.inventory = off.stock              # decremented live during trading
        f.sales = off.sold                   # household purchases (government buys separately below)
        f.revenue = off.sold * off.price     # price fixed within the tick

    # v9 VAT: households remit consumption tax on realised goods spending to GOV (reserved above, cash-capped).
    if tc > 0.0:
        for h in econ.households:
            vat = min(h.spent * tc, econ.ledger.balance(h.id))
            if vat > EPS:
                econ.ledger.transfer(h.id, econ._fiscal, vat)
                if bridge is not None:
                    bridge.post_household_tax_payment(h.id, vat)
                econ._tax_consumption += vat

    # v9 competitive procurement: government buys from the cheapest c-firms first (a tender,
    # lowest-bid-wins), not through the household preferential market.
    if gov and gov_budget > EPS and gov_units > EPS:
        led = econ.ledger
        ranked = sorted((f for f in econ.c_firms if f.inventory > EPS and f.price > EPS),
                        key=lambda f: f.price)
        b, u = gov_budget, gov_units
        for f in ranked:
            if b <= EPS or u <= EPS:
                break
            q = min(f.inventory, b / f.price, u)
            if q <= EPS:
                continue
            val = q * f.price
            led.transfer(econ._fiscal, f.id, val)
            f.inventory -= q
            f.sales += q
            f.revenue += val
            econ._gov_consumption += val
            b -= val
            u -= q

    hh_spent = sum(h.spent for h in econ.households)
    # Unsatisfied-demand ratio: fraction of intended budget that could not be spent (stockouts).
    econ._unsat_ratio = (1.0 - hh_spent / hh_budget_total) if hh_budget_total > EPS else 0.0
