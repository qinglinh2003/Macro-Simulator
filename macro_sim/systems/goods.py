"""Consumption-goods market phase orchestration."""

from __future__ import annotations

from typing import Any, Dict, List

from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS, BuyOrder, SellOffer, execute_market


def _necessity_need_for(econ: Any, h: Any) -> float:
    """v18.1 household necessity need in REAL units = need_units x the frozen per-need-unit
    anchor. need_units (household size/composition) comes from the demographic profile;
    1.0 in the bare kernel (no demographics). Empty households ⇒ need_units 0 ⇒ no
    necessity demand (all budget is luxury)."""
    per_unit = getattr(econ, "_necessity_need_per_unit", 0.0)
    if per_unit <= 0.0:
        return 0.0
    bridge = getattr(econ, "demographic_bridge", None)
    if bridge is None:
        return per_unit
    return per_unit * bridge.household_profile(h.id).need_units


def _run_split_sessions(econ: Any, tc: float):
    """v18.1: the two-session household goods market. NECESSITY first (quantity-targeted
    at the household's necessity need, over n_firms), then LUXURY (the residual budget,
    demand=inf, over l_firms). Returns (trades, hh_budget_total). Necessity SHARE falls
    with income because the necessity quantity is fixed — Engel's law emerges here."""
    led = econ.ledger
    budget_goods: Dict[str, float] = {}       # h.id -> A4-capped goods budget (÷(1+tc))
    nec_orders: List[BuyOrder] = []
    for h in econ.households:
        budget = min(h.consumption_budget, led.balance(h.id))
        if budget <= EPS:
            continue
        bg = budget / (1.0 + tc)
        budget_goods[h.id] = bg
        need = _necessity_need_for(econ, h)
        if need > EPS:
            nec_orders.append(BuyOrder(account=h.id, demand=need, budget=bg, ref=h))
    hh_budget_total = sum(budget_goods.values())

    n_offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.n_firms]
    nec_trades = execute_market(nec_orders, n_offers, protocol=econ.protocol, rng=econ.rng, ledger=led)
    for off in n_offers:
        f: Firm = off.ref
        f.inventory = off.stock
        f.sales = off.sold
        f.revenue = off.sold * off.price
    nec_spent: Dict[str, float] = {}
    for tr in nec_trades:
        nec_spent[tr.buyer] = nec_spent.get(tr.buyer, 0.0) + tr.value

    # LUXURY: whatever budget the necessity session did not absorb (either the household
    # capped its necessity at `need` and has money left, OR necessities stocked out and
    # the unspent budget carries over here).
    lux_orders: List[BuyOrder] = []
    for h in econ.households:
        resid = budget_goods.get(h.id, 0.0) - nec_spent.get(h.id, 0.0)
        if resid > EPS:
            lux_orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=resid, ref=h))
    l_offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.l_firms]
    lux_trades = execute_market(lux_orders, l_offers, protocol=econ.protocol, rng=econ.rng, ledger=led)
    for off in l_offers:
        f = off.ref
        f.inventory = off.stock
        f.sales = off.sold
        f.revenue = off.sold * off.price

    for h in econ.households:                     # record the necessity split for the Engel gauge
        h.necessity_spent = nec_spent.get(h.id, 0.0)

    return nec_trades + lux_trades, hh_budget_total


def run_goods_phase(econ: Any) -> None:
    # Buyers: households with a budget = min(desired budget, LIVE deposits) (A4).
    # The desired budget may exceed this tick's wage income (alpha2 wealth
    # channel) -- do NOT clamp to income; clamp only to live deposits.
    cfg = econ.cfg.goods
    econ._tax_consumption = econ._gov_consumption = 0.0
    gov = cfg.government
    tc = econ.policy.tax_consumption_rate if gov else 0.0
    # v18.1: two-session split when consumption strata are on; otherwise the single
    # session below, verbatim (off ⇒ bit-identical).
    strata = getattr(econ.cfg, "consumption_strata", False) and econ.n_firms and econ.l_firms
    if strata:
        trades, hh_budget_total = _run_split_sessions(econ, tc)
        _finalize_goods(econ, cfg, gov, tc, trades, hh_budget_total)
        return

    orders: List[BuyOrder] = []
    for h in econ.households:
        budget = min(h.consumption_budget, econ.ledger.balance(h.id))
        if budget <= EPS:
            continue
        # v9 VAT: the outlay budget buys goods worth budget/(1+tax); the rest is reserved for tax.
        orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=budget / (1.0 + tc), ref=h))
    hh_budget_total = sum(o.budget for o in orders)     # notional household spend (for unsat ratio)

    # Sellers are the consumption sector only (K-firms sell in Phase 3.5).
    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.c_firms]
    trades = execute_market(orders, offers, protocol=econ.protocol, rng=econ.rng, ledger=econ.ledger)
    for off in offers:
        f: Firm = off.ref
        f.inventory = off.stock              # decremented live during trading
        f.sales = off.sold                   # household purchases (government buys separately below)
        f.revenue = off.sold * off.price     # price fixed within the tick
    _finalize_goods(econ, cfg, gov, tc, trades, hh_budget_total)


def _finalize_goods(econ: Any, cfg: Any, gov: bool, tc: float, trades: List, hh_budget_total: float) -> None:
    """Shared goods-phase tail: realized spend -> households + person-claim bridge, VAT
    remit, government competitive tender, and the unsatisfied-demand gauge. Both the
    single-session and the v18.1 two-session paths converge here; firm-level results
    (inventory/sales/revenue) are pushed by each path BEFORE this runs (the tender reads
    live inventory)."""
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

    # v9 VAT: households remit consumption tax on realised goods spending to GOV (reserved above, cash-capped).
    if tc > 0.0:
        for h in econ.households:
            vat = min(h.spent * tc, econ.ledger.balance(h.id))
            if vat > EPS:
                econ.ledger.transfer(h.id, econ._fiscal, vat)
                if bridge is not None:
                    bridge.post_household_tax_payment(h.id, vat)
                econ._tax_consumption += vat

    # v9 government procurement budget/units (a competitive tender, not the household preferential
    # market). Two modes: deficit-targeting (spend last-tick revenue + target*GDP - last-tick
    # benefit, so the deficit is near target*GDP), or quantity (g*potential_output real units).
    gov_budget, gov_units = 0.0, float("inf")
    if gov:
        pol = econ.policy
        if pol.gov_deficit_target > 0.0:
            target = pol.gov_deficit_target
            if pol.deficit_u_ref > 0.0:      # state-dependent: taper toward balance at full employment
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

    # v9 competitive procurement: government buys from the cheapest c-firms first (a tender,
    # lowest-bid-wins). It spans BOTH sub-sectors (n+l = c_firms) -- the default "buy from both"
    # ruling; a sector-targeted tender is a later handle.
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
