"""Aggregate and per-firm equity-market phase orchestration."""

from __future__ import annotations

import random
from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.demographics.economic_bridge import AGGREGATE_EQUITY_CLAIM_ID
from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import (
    bank_for,
    grant_loan,
    record_bank_credit_loss,
    refresh_loan_books,
    unified_bank_rwa_enabled,
)
from macro_sim.systems.firm_accounting import firm_earnings
from macro_sim.systems.firm_balance_sheet import firm_equity_book_value
from macro_sim.systems.valuation import residual_income_fundamental, valuation_discount_rate


def planned_share_issue(
    firm: Any,
    book_value: float,
    cfg: Any,
    *,
    issue_price: float | None = None,
) -> float:
    """Share units a q>1 firm offers at an explicit issuance quote.

    The v23 path omits ``issue_price`` and therefore uses the issuer's own
    quote.  A caller may supply the historical loop-carried quote solely for
    certified-preset compatibility while that migration is disabled.
    """
    if not cfg.equity_finance or firm.tobin_q <= 1.0:
        return 0.0
    issue_cash = min(
        cfg.lambda_issue * (firm.tobin_q - 1.0) * book_value,
        0.5 * book_value,
    )
    price = max(
        EPS,
        float(firm.share_price if issue_price is None else issue_price),
    )
    return min(issue_cash / price, 0.2 * firm.shares_outstanding)


def setup_per_firm_equity(econ: Any) -> None:
    cfg = econ.cfg.equity_market
    rng = random.Random(cfg.seed + 12345)
    ledger, c_firms = econ.ledger, econ.c_firms
    for firm in c_firms:
        firm.shares_outstanding = cfg.shares_per_firm
        book = firm_equity_book_value(econ, firm)
        firm.share_price = firm.share_last_price = max(EPS, book / cfg.shares_per_firm)
        firm.equity_fundamental = firm.share_price
        firm.residual_income_ema = 0.0
    firm_ids = [firm.id for firm in c_firms]
    watchlist_size = min(cfg.watchlist_size, len(firm_ids))
    watchers = {firm_id: [] for firm_id in firm_ids}
    for household in econ.households:
        household.watchlist = rng.sample(firm_ids, watchlist_size)
        for firm_id in household.watchlist:
            watchers[firm_id].append(household)
    by_id = {firm.id: firm for firm in c_firms}
    if cfg.founder_owned_genesis:
        n_founders = max(1, int(cfg.genesis_founder_pool * len(econ.households)))
        founders = rng.sample(econ.households, n_founders)
        for firm in c_firms:
            founder = founders[rng.randrange(n_founders)]
            founder.holdings[firm.id] = founder.holdings.get(firm.id, 0.0) + firm.shares_outstanding
            if firm.id not in founder.watchlist:
                founder.watchlist.append(firm.id)
    else:
        for firm_id, firm_watchers in watchers.items():
            if not firm_watchers:
                household = econ.households[rng.randrange(len(econ.households))]
                household.watchlist.append(firm_id)
                firm_watchers = [household]
            share = by_id[firm_id].shares_outstanding / len(firm_watchers)
            for household in firm_watchers:
                household.holdings[firm_id] = household.holdings.get(firm_id, 0.0) + share


def run_equity_phase(econ: Any) -> None:
    cfg = econ.cfg.equity_market
    if cfg.per_firm_equity:
        run_per_firm_equity_phase(econ)
        return
    if econ.equity is None:
        return
    mkt, led = econ.equity, econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)

    mkt.book_value = sum(firm_equity_book_value(econ, f) for f in econ.c_firms)
    mkt.dividend_ema += cfg.lambda_d * (econ._dividends_paid - mkt.dividend_ema)
    mkt.fundamental = mkt.book_value / mkt.float_shares

    p = mkt.price
    desired = [B.plan_equity_demand(h, mkt, led.balance(h.id), cfg) for h in econ.households]
    buy = sum(d for d in desired if d > 0.0)
    sell = -sum(d for d in desired if d < 0.0)
    executed = min(buy, sell)

    if executed > EPS:
        buy_scale, sell_scale = executed / buy, executed / sell
        sellers = []
        for h, d in zip(econ.households, desired):
            if d > 0.0:
                q = d * buy_scale
                led.transfer(h.id, "CLEARING", q * p)
                h.shares += q
                if bridge is not None:
                    bridge.post_household_equity_trade(
                        h.id,
                        AGGREGATE_EQUITY_CLAIM_ID,
                        cash_delta=-(q * p),
                        share_delta=q,
                    )
            elif d < 0.0:
                sellers.append((h, -d * sell_scale))
        for h, q in sellers[:-1]:
            led.transfer("CLEARING", h.id, q * p)
            h.shares -= q
            if bridge is not None:
                bridge.post_household_equity_trade(
                    h.id,
                    AGGREGATE_EQUITY_CLAIM_ID,
                    cash_delta=q * p,
                    share_delta=-q,
                )
        if sellers:
            h, q = sellers[-1]
            rem = led.balance("CLEARING")
            if rem > EPS:
                led.transfer("CLEARING", h.id, rem)
            h.shares -= q
            if bridge is not None:
                bridge.post_household_equity_trade(
                    h.id,
                    AGGREGATE_EQUITY_CLAIM_ID,
                    cash_delta=rem,
                    share_delta=-q,
                )
    mkt.executed_volume = executed
    econ._equity_turnover = executed / mkt.float_shares

    mkt.excess_demand = (buy - sell) / mkt.float_shares
    new_p = max(EPS, p * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, mkt.excess_demand))))
    ret = (new_p - p) / p
    mkt.trend += cfg.trend_lambda * (ret - mkt.trend)
    mkt.last_price, mkt.price = p, new_p

    for h in econ.households:
        h.equity_value_ema += cfg.equity_ema_lambda * (h.shares * new_p - h.equity_value_ema)


def run_per_firm_equity_phase(econ: Any) -> None:
    cfg, led = econ.cfg.equity_market, econ.ledger
    r = econ._rate
    direct_discount = (
        valuation_discount_rate(econ)
        if econ.cfg.monetary_direct_transmission else None
    )
    cfirms = econ.c_firms
    bridge = getattr(econ, "demographic_bridge", None)
    if cfg.margin_credit and unified_bank_rwa_enabled(econ):
        # Equity trading follows debt service and housing.  Rebase the cache once
        # on live principal, then sequential margin grants update it atomically.
        refresh_loan_books(econ)

    book_of = {}
    for f in cfirms:
        book = firm_equity_book_value(econ, f)
        book_of[f.id] = book
        earnings = firm_earnings(econ, f)
        required_return = direct_discount if direct_discount is not None else r
        f.residual_income_ema += cfg.resid_income_lambda * (
            (earnings - required_return * book) - f.residual_income_ema
        )
        if direct_discount is not None:
            f.equity_fundamental = residual_income_fundamental(
                book_value=book,
                residual_income=f.residual_income_ema,
                shares_outstanding=f.shares_outstanding,
                discount_rate=direct_discount,
            )
        else:
            premium = (max(0.0, f.residual_income_ema) / r) if r > EPS else 0.0
            f.equity_fundamental = (book + premium) / f.shares_outstanding if f.shares_outstanding > EPS else 0.0
        f.tobin_q = (f.share_price * f.shares_outstanding / book) if book > EPS else 1.0
        f.tobin_q_ema = (
            f.tobin_q
            if cfg.q_invest_smooth >= 1.0
            else f.tobin_q_ema + cfg.q_invest_smooth * (f.tobin_q - f.tobin_q_ema)
        )

    by_id = {f.id: f for f in cfirms}
    orders = {f.id: [] for f in cfirms}
    econ._hh_margin_new = 0.0
    legacy_issue_price = None
    for h in econ.households:
        watch = [by_id[fid] for fid in h.watchlist if fid in by_id]
        if not watch:
            continue
        deposits = led.balance(h.id)
        eq_val = sum(h.holdings.get(f.id, 0.0) * f.share_price for f in watch)
        attr = []
        for f in watch:
            p = f.share_price
            legacy_issue_price = p
            pr = (
                cfg.w_fundamental * (f.equity_fundamental - p) / p
                + cfg.w_chartist * f.share_trend
            ) if p > EPS else 0.0
            attr.append(max(0.0, 1.0 + pr))
        tot = sum(attr)
        if cfg.margin_credit:
            nw = deposits + eq_val - h.margin_debt
            avg_pr = sum(a - 1.0 for a in attr) / len(attr)
            target_share = min(econ.policy.margin_max, max(0.0, cfg.theta_equity * (1.0 + avg_pr)))
            target_eq = target_share * nw
            budget = deposits + max(0.0, econ.policy.margin_ltv * eq_val - h.margin_debt)
        else:
            target_eq = cfg.theta_equity * (deposits + eq_val)
            budget = deposits
        adj = cfg.portfolio_adjust
        deltas = []
        for f, a in zip(watch, attr):
            w = (a / tot) if tot > EPS else (1.0 / len(watch))
            desired = (target_eq * w / f.share_price) if f.share_price > EPS else 0.0
            deltas.append((f, (desired - h.holdings.get(f.id, 0.0)) * adj))
        buy_cash = sum(d * f.share_price for f, d in deltas if d > 0.0)
        if cfg.margin_credit and buy_cash > EPS:
            margin_used = max(0.0, min(buy_cash, budget) - deposits)
            if margin_used > EPS:
                if unified_bank_rwa_enabled(econ):
                    margin_used = grant_loan(econ, h.id, margin_used)
                    # A partial bank grant reduces this order's cash budget; do not
                    # leave an equity order sized to credit that was denied.
                    budget = min(budget, deposits + margin_used)
                else:
                    led.create_loan(h.id, margin_used)
                if margin_used > EPS:
                    if bridge is not None:
                        bridge.post_household_debt_creation(h.id, margin_used)
                    h.margin_debt += margin_used
                    econ._hh_margin_new += margin_used
                    deposits = led.balance(h.id)
        scale = min(1.0, budget / buy_cash) if buy_cash > EPS else 1.0
        for f, d in deltas:
            d = d * scale if d > 0.0 else max(d, -h.holdings.get(f.id, 0.0))
            if abs(d) > EPS:
                orders[f.id].append((h, d))

    executed_total = 0.0
    econ._equity_raised = 0.0
    for f in cfirms:
        od = orders[f.id]
        # Capture this firm's own transaction price before clearing.  Issuance
        # itself also reads ``firm.share_price`` in ``planned_share_issue``; the
        # historical ordering accidentally reused ``p`` left by a household
        # watchlist loop (or left it unbound when no household traded).
        p = f.share_price
        buy = sum(d for _, d in od if d > 0.0)
        hsell = -sum(d for _, d in od if d < 0.0)
        issue = planned_share_issue(
            f,
            book_of[f.id],
            cfg,
            issue_price=(
                None
                if getattr(cfg, "priced_firm_balance_sheet", False)
                else legacy_issue_price
            ),
        )
        sell_total = hsell + issue
        executed = min(buy, sell_total)
        if executed > EPS:
            bs, ss = executed / buy, executed / sell_total
            for h, d in od:
                if d > 0.0:
                    q = d * bs
                    led.transfer(h.id, "CLEARING", q * p)
                    h.holdings[f.id] = h.holdings.get(f.id, 0.0) + q
                    if bridge is not None:
                        bridge.post_household_equity_trade(
                            h.id,
                            f.id,
                            cash_delta=-(q * p),
                            share_delta=q,
                        )
            hsellers = [(h, -d * ss) for h, d in od if d < 0.0]
            for h, q in hsellers:
                h.holdings[f.id] = h.holdings.get(f.id, 0.0) - q
                led.transfer("CLEARING", h.id, q * p)
                if bridge is not None:
                    bridge.post_household_equity_trade(
                        h.id,
                        f.id,
                        cash_delta=q * p,
                        share_delta=-q,
                    )
            issued = issue * ss
            if issued > EPS:
                f.shares_outstanding += issued
                rem = led.balance("CLEARING")
                if rem > EPS:
                    econ._equity_raised += rem
                    led.transfer("CLEARING", f.id, rem)
            elif hsellers:
                rem = led.balance("CLEARING")
                if rem > EPS:
                    led.transfer("CLEARING", hsellers[-1][0].id, rem)
                    if bridge is not None:
                        bridge.post_household_cash_delta(hsellers[-1][0].id, rem, reason="asset_trade")
            executed_total += executed
        excess = (buy - sell_total) / f.shares_outstanding if f.shares_outstanding > EPS else 0.0
        new_p = max(EPS, p * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, excess))))
        f.share_trend += cfg.trend_lambda * ((new_p - p) / p - f.share_trend)
        f.share_last_price, f.share_price = p, new_p
        # Mirror the pre-v23 loop-carried quote for the next issuer only while
        # the priced balance-sheet migration is disabled.
        legacy_issue_price = p
    econ._equity_turnover = executed_total / max(EPS, sum(f.shares_outstanding for f in cfirms))

    econ._hh_margin_repaid = 0.0
    if cfg.margin_credit:
        for h in econ.households:
            if h.margin_debt <= EPS:
                continue
            eq = sum(h.holdings.get(fid, 0.0) * by_id[fid].share_price for fid in h.watchlist if fid in by_id)
            excess = h.margin_debt - econ.policy.margin_ltv * eq
            if excess > EPS:
                pay = min(excess, led.balance(h.id))
                if pay > EPS:
                    led.repay(h.id, pay)
                    if bridge is not None:
                        bridge.post_household_debt_repayment(h.id, pay)
                    h.margin_debt -= pay
                    econ._hh_margin_repaid += pay

    econ._hh_bankruptcies = 0
    if econ.policy.household_bankruptcy and cfg.margin_credit:
        for h in econ.households:
            if h.margin_debt <= EPS:
                continue
            eq = sum(h.holdings.get(fid, 0.0) * by_id[fid].share_price for fid in h.watchlist if fid in by_id)
            if led.balance(h.id) + eq - h.margin_debt <= 0.0:
                # the margin_debt SHADOW can run stale-high when ledger debt left the account
                # through channels that do not know about it (e.g. a debt claim inherited into
                # another household moves ledger debt via transfer_debt): repay/write off no
                # more than the LEDGER actually carries, then retire the shadow. Seed-5 of the
                # ten-year sweep died here on write_off(715.03) vs ledger debt 704.74.
                pay = min(led.balance(h.id), h.margin_debt, led.debt(h.id))
                if pay > EPS:
                    led.repay(h.id, pay)
                    if bridge is not None:
                        bridge.post_household_debt_repayment(h.id, pay)
                    h.margin_debt -= pay
                if h.margin_debt > EPS:
                    bad = min(h.margin_debt, led.debt(h.id))
                    if bad > EPS:
                        bank_id = bank_for(econ, h.id).id
                        principal_before = max(0.0, float(led.debt(h.id)))
                        led.write_off(h.id, bank_id, bad)
                        record_bank_credit_loss(econ, bank_id, bad)
                        h.margin_debt = max(0.0, h.margin_debt - bad)
                        from macro_sim.systems.credit import (
                            extinguish_household_interest_arrears_for_writeoff,
                        )
                        extinguish_household_interest_arrears_for_writeoff(
                            econ,
                            h.id,
                            principal_before=principal_before,
                            principal_reduction=bad,
                        )
                        if bridge is not None:
                            bridge.post_household_debt_writeoff(h.id, bad)
                    h.margin_debt = 0.0
                econ._hh_bankruptcies += 1
