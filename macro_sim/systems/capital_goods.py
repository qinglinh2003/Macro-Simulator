"""Capital-goods market phase orchestration."""

from __future__ import annotations

from typing import Any, Dict, List

from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS, BuyOrder, SellOffer, execute_market


def run_capital_goods_phase(econ: Any) -> None:
    """C-firms buy capital goods from K-firms after the consumption-goods market."""
    cfg = econ.cfg.capital_goods
    econ._public_investment = econ._gov_capital_units = 0.0
    if not cfg.capital_enabled:
        return
    orders: List[BuyOrder] = []
    for f in econ.investing_firms:          # C-firms, plus K-firms in v2.5
        budget = econ.ledger.balance(f.id)
        if f.investment_target <= EPS or budget <= EPS:
            continue
        orders.append(BuyOrder(account=f.id, demand=f.investment_target, budget=budget, ref=f))

    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in econ.k_firms]
    trades = execute_market(orders, offers, protocol=econ.protocol, rng=econ.rng, ledger=econ.ledger)

    bought: Dict[str, float] = {}
    for tr in trades:
        bought[tr.buyer] = bought.get(tr.buyer, 0.0) + tr.qty
    for f in econ.investing_firms:
        # push results onto the SAME list the orders came from (v17.0: E-firms invest in
        # capacity through this market; == c_firms in every pre-energy preset ⇒ bit-identical)
        f.investment = bought.get(f.id, 0.0)          # realized capital units (I_{f,t})
    for off in offers:                                # K-firms' sales come from THIS market
        kf: Firm = off.ref
        kf.inventory = off.stock
        kf.sales = off.sold
        kf.revenue = off.sold * off.price

    # v16-L6 footfall: unmet order units become an OBSERVABLE demand signal, split
    # equally across K-firms (the zero-stock sellers are exactly who needs to see
    # it). Expectations-only -- no money, no goods, no revenue moves here.
    if cfg.rationed_signal and econ.k_firms:
        unmet = sum(max(0.0, o.demand - bought.get(o.account, 0.0)) for o in orders)
        share = unmet / len(econ.k_firms)
        for kf in econ.k_firms:
            kf.rationed_demand = share
    else:
        for kf in econ.k_firms:
            kf.rationed_demand = 0.0

    # v9.1 government investment: buy remaining K-goods cheapest-first, building public capital.
    if cfg.government and cfg.gov_investment_share > 0.0:
        budget = cfg.gov_investment_share * getattr(econ, "_prev_nominal_output", 0.0)
        led, b = econ.ledger, budget
        for kf in sorted((k for k in econ.k_firms if k.inventory > EPS and k.price > EPS),
                         key=lambda k: k.price):
            if b <= EPS:
                break
            q = min(kf.inventory, b / kf.price)
            if q <= EPS:
                continue
            val = q * kf.price
            led.transfer(econ._fiscal, kf.id, val)
            kf.inventory -= q
            kf.sales += q
            kf.revenue += val
            econ._gov_capital_units += q
            econ._public_investment += val
            b -= val
