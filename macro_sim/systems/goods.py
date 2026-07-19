"""Consumption-goods market phase orchestration."""

from __future__ import annotations

from typing import Any, Dict, List

from macro_sim.behavior import planning as B
from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import (
    EPS,
    BuyOrder,
    MarketTrace,
    SellOffer,
    execute_market,
)
from macro_sim.systems.banking import loan_rate_for


def household_goods_cash_budget(econ: Any, household: Any) -> float:
    """Return the live cash available for this household's goods order.

    Direct monetary transmission reserves contractual service only after all
    pre-goods cash flows have settled.  This preserves desired demand while
    preventing the goods market from spending cash used by the immediately
    following household debt-service phase.
    """
    desired = max(0.0, float(household.consumption_budget))
    deposits = max(0.0, float(econ.ledger.balance(household.id)))
    # This phase owns a typed config view.  Reading the legacy top-level Config
    # here made even the government-off fast path depend on unrelated config
    # internals and broke isolated system use.
    goods_cfg = econ.cfg.goods
    carry_arrears = getattr(goods_cfg, "household_interest_arrears", False)
    if not (
        getattr(goods_cfg, "monetary_direct_transmission", False)
        or carry_arrears
    ):
        return min(desired, deposits)
    return B.reserve_household_debt_service(
        desired,
        deposits=deposits,
        debt=econ.ledger.debt(household.id),
        margin_debt=household.margin_debt,
        loan_rate=loan_rate_for(econ, household.id),
        amort=econ.cfg.credit.hh_amort,
        interest_arrears=(
            household.credit_interest_arrears if carry_arrears else 0.0
        ),
    )


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


def _vat_rates(econ: Any, tc: float):
    """v18.3 per-sector VAT rates. None (default) ⇒ fall back to the uniform τ_c ⇒
    bit-identical to the pre-18.3 path."""
    pol = getattr(econ, "policy", None)
    tn = getattr(pol, "tax_necessity_rate", None)
    tl = getattr(pol, "tax_luxury_rate", None)
    return (tn if tn is not None else tc), (tl if tl is not None else tc)


def _run_split_sessions(econ: Any, tc: float, cash_budgets: Dict[str, float]):
    """v18.1: the two-session household goods market. NECESSITY first (quantity-targeted
    at the household's necessity need, over n_firms), then LUXURY (the residual budget,
    demand=inf, over l_firms). Returns (trades, hh_budget_total). Necessity SHARE falls
    with income because the necessity quantity is fixed — Engel's law emerges here.
    v18.3: each session reserves its own VAT (τ_N on necessities, τ_L on luxuries); with
    both = τ_c this is bit-identical to the uniform path."""
    led = econ.ledger
    tc_N, tc_L = _vat_rates(econ, tc)
    deposits: Dict[str, float] = {}           # h.id -> A4-capped deposits available for goods
    nec_orders: List[BuyOrder] = []
    for h in econ.households:
        dep = cash_budgets[h.id]
        if dep <= EPS:
            continue
        deposits[h.id] = dep
        need = _necessity_need_for(econ, h)
        if need > EPS:
            nec_orders.append(BuyOrder(account=h.id, demand=need, budget=dep / (1.0 + tc_N), ref=h))
    hh_budget_total = sum(dep / (1.0 + tc) for dep in deposits.values())   # unsat gauge (uniform ref)

    n_offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.n_firms]
    foreign_offer = getattr(econ, "_fx_import_offer", None)
    if foreign_offer is not None and foreign_offer.stock > EPS and foreign_offer.price > EPS:
        # A generic imported consumption good may satisfy either stratum.  Offer it
        # first in necessities, then carry the same live residual stock/sales counter
        # into luxuries so settlement sees one unduplicated foreign flow.
        n_offers.append(foreign_offer)
    trace_enabled = bool(econ.cfg.goods.rationed_signal)
    nec_trace = MarketTrace() if trace_enabled else None
    nec_trades = execute_market(
        nec_orders, n_offers, protocol=econ.protocol, rng=econ.rng, ledger=led,
        unmet_trace=nec_trace,
    )
    for off in n_offers:
        if off.ref is None:
            continue
        f: Firm = off.ref
        f.inventory = off.stock
        f.sales = off.sold
        f.revenue = off.sold * off.price
    nec_spent: Dict[str, float] = {}
    for tr in nec_trades:
        nec_spent[tr.buyer] = nec_spent.get(tr.buyer, 0.0) + tr.value

    # LUXURY: the deposits left after the necessity outlay (goods value + its VAT),
    # de-VAT'd at the luxury rate.
    lux_orders: List[BuyOrder] = []
    for h in econ.households:
        dep = deposits.get(h.id, 0.0)
        nec_outlay = nec_spent.get(h.id, 0.0) * (1.0 + tc_N)
        resid = (dep - nec_outlay) / (1.0 + tc_L)
        if resid > EPS:
            lux_orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=resid, ref=h))
    l_offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.l_firms]
    if foreign_offer is not None and foreign_offer.stock > EPS:
        l_offers.append(foreign_offer)
    lux_trace = MarketTrace() if trace_enabled else None
    lux_trades = execute_market(
        lux_orders, l_offers, protocol=econ.protocol, rng=econ.rng, ledger=led,
        unmet_trace=lux_trace,
    )
    if nec_trace is not None and lux_trace is not None and nec_trace.visits:
        # The sessions are sequential claims on one household budget.  If a
        # protocol has already identified unmet necessity demand for a buyer,
        # treating that buyer's same residual cash as additional next-period
        # luxury demand double-counts a conditional budget.  Preserve current
        # trades, but give the higher-priority necessity signal first claim on
        # the counterfactual planning observation.
        necessity_unmet_buyers = {visit.buyer for visit in nec_trace.visits}
        lux_trace.visits = [
            visit for visit in lux_trace.visits
            if visit.buyer not in necessity_unmet_buyers
        ]
    for off in l_offers:
        if off.ref is None:
            continue
        f = off.ref
        f.inventory = off.stock
        f.sales = off.sold
        f.revenue = off.sold * off.price

    for h in econ.households:                     # record the necessity split for the Engel gauge
        h.necessity_spent = nec_spent.get(h.id, 0.0)

    traces = [trace for trace in (nec_trace, lux_trace) if trace is not None]
    return nec_trades + lux_trades, hh_budget_total, traces


def run_goods_phase(econ: Any) -> None:
    # Buyers: households with a budget = min(desired budget, LIVE deposits) (A4).
    # The desired budget may exceed this tick's wage income (alpha2 wealth
    # channel) -- do NOT clamp to income; clamp only to live deposits.
    cfg = econ.cfg.goods
    econ._tax_consumption = econ._gov_consumption = 0.0
    gov = cfg.government
    tc = econ.policy.tax_consumption_rate if gov else 0.0
    cash_budgets = {
        h.id: household_goods_cash_budget(econ, h)
        for h in econ.households
    }
    reserve_service = (
        getattr(cfg, "monetary_direct_transmission", False)
        or getattr(cfg, "household_interest_arrears", False)
    )
    if reserve_service:
        # Isolate the service reservation from the ordinary A4 cash cap: a lack
        # of deposits is not itself a monetary-policy transmission effect.
        econ._hh_debt_service_reserved = sum(
            max(
                0.0,
                min(
                    max(0.0, float(h.consumption_budget)),
                    max(0.0, float(econ.ledger.balance(h.id))),
                ) - cash_budgets[h.id],
            )
            for h in econ.households
        )
        econ._hh_contractual_debt_service_due = sum(
            B.household_contractual_debt_service(
                debt=econ.ledger.debt(h.id),
                margin_debt=h.margin_debt,
                loan_rate=loan_rate_for(econ, h.id),
                amort=econ.cfg.credit.hh_amort,
                interest_arrears=(
                    h.credit_interest_arrears
                    if getattr(cfg, "household_interest_arrears", False)
                    else 0.0
                ),
            )
            for h in econ.households
        )
        econ._hh_interest_arrears_in_goods_reservation = (
            sum(max(0.0, float(h.credit_interest_arrears)) for h in econ.households)
            if getattr(cfg, "household_interest_arrears", False)
            else 0.0
        )
    # v18.1: two-session split when consumption strata are on; otherwise the single
    # session below, verbatim (off ⇒ bit-identical). Read via the grouped goods view.
    strata = getattr(cfg, "consumption_strata", False) and econ.n_firms and econ.l_firms
    if strata:
        trades, hh_budget_total, traces = _run_split_sessions(econ, tc, cash_budgets)
        _finalize_goods(econ, cfg, gov, tc, trades, hh_budget_total, traces)
        return

    orders: List[BuyOrder] = []
    for h in econ.households:
        budget = cash_budgets[h.id]
        if budget <= EPS:
            continue
        # v9 VAT: the outlay budget buys goods worth budget/(1+tax); the rest is reserved for tax.
        orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=budget / (1.0 + tc), ref=h))
    hh_budget_total = sum(o.budget for o in orders)     # notional household spend (for unsat ratio)

    # Sellers are the consumption sector only (K-firms sell in Phase 3.5).
    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.c_firms]
    _inject_foreign_trade(econ, orders, offers)   # v20.2 open economy; no-op off ⇒ bit-identical
    unmet_trace = MarketTrace() if getattr(cfg, "rationed_signal", False) else None
    trades = execute_market(
        orders, offers, protocol=econ.protocol, rng=econ.rng, ledger=econ.ledger,
        unmet_trace=unmet_trace,
    )
    for off in offers:
        f: Firm = off.ref
        if f is None:                        # v20.2: the foreign import offer (seller=dealer), not a domestic firm
            continue
        f.inventory = off.stock              # decremented live during trading
        f.sales = off.sold                   # household purchases (government buys separately below)
        f.revenue = off.sold * off.price     # price fixed within the tick
    traces = [unmet_trace] if unmet_trace is not None else []
    _finalize_goods(econ, cfg, gov, tc, trades, hh_budget_total, traces)


def _inject_foreign_trade(econ: Any, orders: List, offers: List) -> None:
    """v20.2 open economy: add the FX dealer's cross-border offer/order into the domestic
    goods session (PLAN_v20 §4). The World sets these on the economy in the coupling
    barrier (last-tick foreign price × rate × (1+friction)); absent ⇒ closed economy ⇒
    bit-identical. Money routes through the dealer via the real matching engine, so each
    economy's ledger conserves by construction:
      * import offer  — seller = DEALER: households buy foreign goods, paying the dealer
        in domestic currency (dealer's inventory rises; import competition vs domestic firms);
      * export order  — buyer = DEALER: the dealer buys domestic goods for foreign buyers,
        paying domestic firms in domestic currency (dealer's inventory falls; goods ship out).
    """
    off = getattr(econ, "_fx_import_offer", None)
    if off is not None and off.stock > EPS and off.price > EPS:
        offers.append(off)
    order = getattr(econ, "_fx_export_order", None)
    if order is not None and order.budget > EPS:
        orders.append(order)


def _finalize_goods(econ: Any, cfg: Any, gov: bool, tc: float, trades: List,
                    hh_budget_total: float,
                    unmet_traces: List[MarketTrace] | None = None) -> None:
    """Shared goods-phase tail: realized spend -> households + person-claim bridge, VAT
    remit, government competitive tender, and the unsatisfied-demand gauge. Both the
    single-session and the v18.1 two-session paths converge here; firm-level results
    (inventory/sales/revenue) are pushed by each path BEFORE this runs (the tender reads
    live inventory)."""
    national_accounts = getattr(econ, "_national_accounts", None)
    # Aggregate only records tied to explicit protocol-defined diagnostic visits.  A
    # foreign offer can legitimately receive such a visit, but it is not a
    # domestic C-firm planning signal and therefore remains outside this map.
    footfall_by_firm: Dict[str, float] = {}
    trace_attributable_total = 0.0
    trace_unattributed_budget = 0.0
    if getattr(cfg, "rationed_signal", False):
        domestic_ids = {firm.id for firm in econ.c_firms}
        for trace in unmet_traces or []:
            trace_attributable_total += trace.attributable_qty
            trace_unattributed_budget += trace.unattributed_budget
            for seller_id, qty in trace.by_seller.items():
                if seller_id in domestic_ids:
                    footfall_by_firm[seller_id] = footfall_by_firm.get(seller_id, 0.0) + qty
    if national_accounts is not None:
        national_accounts.observe_goods_trades(econ, trades)
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
    # v18.3: with the split on, necessities and luxuries carry their own rates (τ_N, τ_L);
    # with both = τ_c this reduces to the uniform remit (bit-identical).
    strata = getattr(cfg, "consumption_strata", False) and econ.n_firms and econ.l_firms
    tc_N, tc_L = _vat_rates(econ, tc) if strata else (tc, tc)
    if tc > 0.0 or (strata and (tc_N > 0.0 or tc_L > 0.0)):
        for h in econ.households:
            if strata:
                due = h.necessity_spent * tc_N + max(0.0, h.spent - h.necessity_spent) * tc_L
            else:
                due = h.spent * tc
            vat = min(due, econ.ledger.balance(h.id))
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
                cap = float(econ.policy.deficit_u_cap)
                target *= min(cap, getattr(econ, "_prev_u", pol.deficit_u_ref) / pol.deficit_u_ref)
            gov_budget = max(
                0.0,
                getattr(econ, "_prev_tax_total", 0.0)
                + target * getattr(
                    econ,
                    "_prev_fiscal_output",
                    getattr(econ, "_prev_nominal_output", 0.0),
                )
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
        last_contractor = None
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
            if national_accounts is not None:
                national_accounts.observe_government_goods(f.id, q, val)
            b -= val
            u -= q
            last_contractor = f

        # The tender has an observable final accepted bid.  If that contractor
        # exhausts its shelf while the tender remains open, the affordable
        # residual is attributable to that firm.  A tender with no accepted bid
        # remains aggregate: assigning it across unseen firms would recreate the
        # equal-share coupling this patch removes.
        if getattr(cfg, "rationed_signal", False) and last_contractor is not None \
                and last_contractor.inventory <= EPS and b > EPS and u > EPS:
            qty = min(u, b / last_contractor.price)
            if qty > EPS:
                footfall_by_firm[last_contractor.id] = (
                    footfall_by_firm.get(last_contractor.id, 0.0) + qty
                )
                trace_attributable_total += qty

    if getattr(cfg, "rationed_signal", False):
        for firm in econ.c_firms:
            firm.rationed_demand = footfall_by_firm.get(firm.id, 0.0)
        # Runtime audit hooks: total protocol-attributable quantity includes a
        # possible foreign visit; the firm total contains only domestic signals.
        econ._c_attributable_footfall = trace_attributable_total
        econ._c_firm_footfall = sum(footfall_by_firm.values())
        econ._c_unattributed_footfall_budget = trace_unattributed_budget

    hh_spent = sum(h.spent for h in econ.households)
    # Unsatisfied-demand ratio: fraction of intended budget that could not be spent (stockouts).
    econ._unsat_ratio = (1.0 - hh_spent / hh_budget_total) if hh_budget_total > EPS else 0.0
