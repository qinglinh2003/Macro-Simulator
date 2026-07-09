"""Government bill maturity and issuance orchestration."""

from __future__ import annotations

from typing import Any, Dict

from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_economic_capital, bank_for


def bond_price(face: float, n: int, rate: float, coupon: float) -> float:
    if n <= 0 or rate <= -1.0 + EPS:
        return face
    disc = 1.0 / (1.0 + rate)
    pv_principal = face * disc ** n
    if coupon <= 0.0:
        pv_coupons = 0.0
    elif abs(rate) < 1e-12:
        pv_coupons = coupon * face * n
    else:
        pv_coupons = coupon * face * (1.0 - disc ** n) / rate
    return pv_coupons + pv_principal


def bond_market_value(econ: Any, lot: dict) -> float:
    cfg = econ.cfg.securities
    n = lot["matures_at"] - econ.t
    if n <= 0:
        return lot["face"]
    if cfg.bond_maturity <= 1 and cfg.bond_coupon <= 0.0:
        return lot["face"]
    return bond_price(lot["face"], n, econ._rate, cfg.bond_coupon)


def reindex_bonds(econ: Any) -> None:
    idx: Dict = {}
    for lot in econ._bonds:
        idx[lot["holder"]] = idx.get(lot["holder"], 0.0) + lot["face"]
    econ._bond_holdings = idx


def bump_bonds_version(econ: Any) -> None:
    """Stamp every bond-lot mutation (append/remove/holder/face/cost) so per-tick valuation
    caches know to rebuild. Missing a stamp would desync planning wealth from the lots; the
    per-tick claim/securities identity gates would trip loudly."""
    econ._bonds_version = getattr(econ, "_bonds_version", 0) + 1


def _bond_valuations(econ: Any):
    """One pass over the lots per (tick, lots-version): per-holder market-value lists and
    per-holder (market - cost) delta lists, in lot order.

    Replaces the former per-call full-lot scans (planning's per-household bond wealth and
    per-loan bank economic capital were O(N_agents x N_lots) per tick -- 5.3k households x
    30k lots at the 10k-person scale). Sums stay the same builtin over the same sequence
    (compensated sum() per holder); bank deltas are replayed as the same += sequence.
    """
    # rate is in the key for out-of-loop callers (tests hike econ._rate mid-tick to probe the
    # SVB channel); inside step() it is set once at the top of the tick, so it never churns.
    key = (econ.t, getattr(econ, "_bonds_version", 0), econ._rate)
    cached = getattr(econ, "_bond_valuation_cache", None)
    if cached is not None and cached[0] == key:
        return cached
    mv_lists: Dict = {}
    delta_lists: Dict = {}
    for lot in econ._bonds:
        mv = bond_market_value(econ, lot)
        holder = lot["holder"]
        mv_lists.setdefault(holder, []).append(mv)
        delta_lists.setdefault(holder, []).append(mv - lot["cost"])
    mv_sums = {holder: sum(values) for holder, values in mv_lists.items()}
    cached = (key, mv_sums, delta_lists)
    econ._bond_valuation_cache = cached
    return cached


def household_bond_value(econ: Any, household_id) -> float:
    cfg = econ.cfg.securities
    if not cfg.bonds:
        return 0.0
    return _bond_valuations(econ)[1].get(household_id, 0)


def bank_bond_capital_deltas(econ: Any, bank_id) -> list:
    """Per-lot (market - cost) for `bank_id`'s book, in lot order (bank_economic_capital
    replays these with the same += sequence as its former full-lot scan)."""
    return _bond_valuations(econ)[2].get(bank_id, ())


def redeem_household_bonds(econ: Any, household_id, amount: float) -> None:
    kept, raised = [], 0.0
    bridge = getattr(econ, "demographic_bridge", None)
    for lot in econ._bonds:
        if lot["holder"] == household_id and raised < amount - EPS:
            econ.ledger.transfer(econ._fiscal, household_id, lot["face"])
            if bridge is not None and household_id in getattr(bridge, "account_to_household", {}):
                bridge.post_household_bond_trade(
                    household_id,
                    cash_delta=lot["face"],
                    face_delta=-lot["face"],
                )
            econ._bonds_outstanding -= lot["face"]
            raised += lot["face"]
        else:
            kept.append(lot)
    econ._bonds = kept
    bump_bonds_version(econ)
    reindex_bonds(econ)


def assert_securities_identities(econ: Any) -> None:
    cfg = econ.cfg.securities
    if not cfg.bonds:
        return
    held = sum(econ._bond_holdings.values())
    assert abs(held - econ._bonds_outstanding) <= 1e-6 * max(1.0, abs(econ._bonds_outstanding)), \
        f"v12 bond identity broke: Σheld@face={held} vs outstanding={econ._bonds_outstanding}"
    gov_debt = econ._bonds_outstanding - econ.ledger.balance(econ._fiscal)
    private_nfa = (
        (econ.ledger.total_money - econ.ledger.balance(econ._fiscal))
        - econ.ledger.total_credit
        + held
        - econ.ledger.bank_securities
    )
    target = econ.ledger.genesis_money + gov_debt
    assert abs(private_nfa - target) <= 1e-6 * max(1.0, abs(target)), \
        f"v12 master NFA broke: private NFA {private_nfa} vs M₀+gov_debt {target}"


def run_bill_maturity_phase(econ: Any) -> None:
    cfg = econ.cfg.securities
    econ._gov_interest_bill = 0.0
    if not (cfg.bonds and cfg.government) or not econ._bonds:
        return
    bridge = getattr(econ, "demographic_bridge", None)
    if cfg.bond_coupon > 0.0:
        for lot in econ._bonds:
            c = cfg.bond_coupon * lot["face"]
            if c > EPS:
                econ.ledger.transfer(econ._fiscal, lot["holder"], c)
                if bridge is not None and lot["holder"] in getattr(bridge, "account_to_household", {}):
                    bridge.post_household_cash_delta(lot["holder"], c, reason="capital_income")
                econ._gov_interest_bill += c
    matured = [lot for lot in econ._bonds if lot["matures_at"] <= econ.t]
    if matured:
        for lot in matured:
            f = lot["face"]
            if f > EPS:
                if lot["holder"] in econ._bank_ids:
                    econ.ledger.bank_redeem_bond(lot["holder"], econ._fiscal, f)
                else:
                    econ.ledger.transfer(econ._fiscal, lot["holder"], f)
                    if bridge is not None and lot["holder"] in getattr(bridge, "account_to_household", {}):
                        bridge.post_household_bond_trade(lot["holder"], cash_delta=f, face_delta=-f)
                econ._bonds_outstanding -= f
        econ._bonds = [lot for lot in econ._bonds if lot["matures_at"] > econ.t]
        bump_bonds_version(econ)
        reindex_bonds(econ)


def run_bill_issuance_phase(econ: Any) -> None:
    cfg = econ.cfg.securities
    if not (cfg.bonds and cfg.bond_finance_frac > 0.0 and cfg.government):
        return
    gov_debt = econ._bonds_outstanding - econ.ledger.balance(econ._fiscal)
    if gov_debt <= EPS:
        return
    gap = cfg.bond_finance_frac * gov_debt - econ._bonds_outstanding
    if gap <= EPS:
        return
    hh = econ.households
    pfac = econ._price_level / cfg.p_firm0
    if cfg.bond_theta > 0.0:
        idle = {}
        for h in hh:
            d = econ.ledger.balance(h.id)
            bm = household_bond_value(econ, h.id)
            thin_buffer = max(h.y_expected, cfg.d_household0 * pfac)
            room = max(0.0, cfg.bond_theta * (d + bm) - bm)
            idle[h.id] = min(max(0.0, d - thin_buffer), room)
    else:
        idle = {
            h.id: max(0.0, econ.ledger.balance(h.id) - max(2.0 * h.y_expected, cfg.d_household0 * pfac))
            for h in hh
        }
    remaining = gap
    total = sum(idle.values())
    issued = False
    bridge = getattr(econ, "demographic_bridge", None)
    if total > EPS:
        for h in hh:
            buy = min(remaining * idle[h.id] / total, idle[h.id])
            if buy > EPS:
                econ.ledger.transfer(h.id, econ._fiscal, buy)
                if bridge is not None:
                    bridge.post_household_bond_trade(h.id, cash_delta=-buy, face_delta=buy)
                econ._bonds.append({
                    "holder": h.id,
                    "face": buy,
                    "cost": buy,
                    "matures_at": econ.t + cfg.bond_maturity,
                })
                bump_bonds_version(econ)
                econ._bonds_outstanding += buy
                remaining -= buy
                issued = True
    if cfg.bank_bond_appetite > 0.0 and remaining > EPS and cfg.interbank:
        dep_by_bank: Dict = {}
        for a in list(econ.firms) + list(econ.households):
            bid = bank_for(econ, a.id).id
            dep_by_bank[bid] = dep_by_bank.get(bid, 0.0) + econ.ledger.balance(a.id)
        for bk in [b for b in econ.banks if b.alive]:
            if remaining <= EPS:
                break
            required = cfg.reserve_floor_frac * dep_by_bank.get(bk.id, 0.0)
            excess = max(0.0, econ.ledger.reserves(bk.id) - required)
            want = min(cfg.bank_bond_appetite * excess, remaining)
            if cfg.bank_bond_duration_limit > 0.0:
                cur = sum(l["face"] for l in econ._bonds if l["holder"] == bk.id)
                room = cfg.bank_bond_duration_limit * max(0.0, bank_economic_capital(econ, bk)) - cur
                want = min(want, max(0.0, room))
            if want > EPS:
                econ.ledger.bank_buy_bond_with_reserves(bk.id, econ._fiscal, want)
                econ._bonds.append({
                    "holder": bk.id,
                    "face": want,
                    "cost": want,
                    "matures_at": econ.t + cfg.bond_maturity,
                })
                bump_bonds_version(econ)
                econ._bonds_outstanding += want
                remaining -= want
                issued = True
    if issued:
        reindex_bonds(econ)
