"""Aggregate and per-firm equity-market phase orchestration."""

from __future__ import annotations

import random
from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.demographics.economic_bridge import AGGREGATE_EQUITY_CLAIM_ID
from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_for


def setup_per_firm_equity(econ: Any) -> None:
    cfg = econ.cfg.equity_market
    rng = random.Random(cfg.seed + 12345)
    ledger, c_firms = econ.ledger, econ.c_firms
    for firm in c_firms:
        firm.shares_outstanding = cfg.shares_per_firm
        book = ledger.balance(firm.id) - ledger.debt(firm.id) + firm.capital
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

    mkt.book_value = sum(led.balance(f.id) - led.debt(f.id) + f.capital for f in econ.c_firms)
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
    cfirms = econ.c_firms
    bridge = getattr(econ, "demographic_bridge", None)

    book_of = {}
    for f in cfirms:
        book = led.balance(f.id) - led.debt(f.id) + f.capital
        book_of[f.id] = book
        f.residual_income_ema += cfg.resid_income_lambda * ((f.profit - r * book) - f.residual_income_ema)
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
    for h in econ.households:
        watch = [by_id[fid] for fid in h.watchlist if fid in by_id]
        if not watch:
            continue
        deposits = led.balance(h.id)
        eq_val = sum(h.holdings.get(f.id, 0.0) * f.share_price for f in watch)
        attr = []
        for f in watch:
            p = f.share_price
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
                led.create_loan(h.id, margin_used)
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
        buy = sum(d for _, d in od if d > 0.0)
        hsell = -sum(d for _, d in od if d < 0.0)
        issue = 0.0
        if cfg.equity_finance and f.tobin_q > 1.0:
            issue_cash = min(cfg.lambda_issue * (f.tobin_q - 1.0) * book_of[f.id], 0.5 * book_of[f.id])
            issue = min(issue_cash / p, 0.2 * f.shares_outstanding)
        sell_total = hsell + issue
        executed = min(buy, sell_total)
        p = f.share_price
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
    if cfg.household_bankruptcy and cfg.margin_credit:
        for h in econ.households:
            if h.margin_debt <= EPS:
                continue
            eq = sum(h.holdings.get(fid, 0.0) * by_id[fid].share_price for fid in h.watchlist if fid in by_id)
            if led.balance(h.id) + eq - h.margin_debt <= 0.0:
                pay = min(led.balance(h.id), h.margin_debt)
                if pay > EPS:
                    led.repay(h.id, pay)
                    if bridge is not None:
                        bridge.post_household_debt_repayment(h.id, pay)
                    h.margin_debt -= pay
                if h.margin_debt > EPS:
                    bad = h.margin_debt
                    led.write_off(h.id, bank_for(econ, h.id).id, h.margin_debt)
                    if bridge is not None:
                        bridge.post_household_debt_writeoff(h.id, bad)
                    h.margin_debt = 0.0
                econ._hh_bankruptcies += 1
