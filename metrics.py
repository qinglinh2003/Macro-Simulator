"""Rich per-tick metrics for the kernel (observation only).

This module computes a comprehensive snapshot of the economy each tick. It is
PURE OBSERVATION: measuring a statistic never drives behavior, so logging §4
test-set quantities (Gini, top-shares, firm-size dispersion, fat-tail inputs) is
fine and does not violate §0-ii / §8.2 -- these are exactly the series we will
later validate against, so we want them recorded from day one.

Metric groups:
  * money & shares   -- who holds the (conserved) money stock
  * circular flows   -- wages, consumption, profit, dividends, saving (the leak)
  * real activity    -- output, consumption, inventory, inventory investment
  * prices           -- index, dispersion, inflation, markup, wage
  * labor            -- demand, supply, employment, unfilled, fill rate
  * demand residuals -- desired vs effective consumption, unsatisfied ratio
  * distributions    -- household wealth & firm size Gini / top-shares (for §4)
  * diagnostics      -- conservation drift, active-firm counts
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Distribution helpers (used for §4 wealth / Zipf diagnostics later)
# ---------------------------------------------------------------------------
def gini(values: Sequence[float]) -> float:
    """Gini coefficient in [0,1]. 0 = perfectly equal. Returns 0 for empty / all-
    non-positive inputs (no meaningful inequality to report)."""
    x = np.sort(np.asarray(values, dtype=float))
    n = x.size
    if n == 0:
        return 0.0
    total = x.sum()
    if total <= 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * x)) / (n * total) - (n + 1.0) / n)


def top_share(values: Sequence[float], frac: float = 0.1) -> float:
    """Share of the total held by the top ``frac`` of holders (by value)."""
    x = np.sort(np.asarray(values, dtype=float))[::-1]
    n = x.size
    if n == 0:
        return 0.0
    total = x.sum()
    if total <= 0:
        return 0.0
    k = max(1, int(np.ceil(frac * n)))
    return float(x[:k].sum() / total)


def cv(values: Sequence[float]) -> float:
    """Coefficient of variation (std/mean); 0 if mean ~ 0."""
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return 0.0
    m = x.mean()
    return float(x.std() / abs(m)) if abs(m) > 1e-12 else 0.0


def _mean(x: Sequence[float]) -> float:
    a = np.asarray(x, dtype=float)
    return float(a.mean()) if a.size else 0.0


def _std(x: Sequence[float]) -> float:
    a = np.asarray(x, dtype=float)
    return float(a.std()) if a.size else 0.0


# ---------------------------------------------------------------------------
# Per-tick snapshot
# ---------------------------------------------------------------------------
def compute_tick_metrics(econ) -> Dict[str, float]:
    """Build one tick's metric record from live economy state. Read-only.

    Sector-aware: consumption-side quantities (price index, real output, inventory)
    are computed from the consumption firms only; money/labor/wages span all firms.
    In v1 (capital off) ``econ.c_firms == econ.firms``, so every legacy key keeps its
    exact v1 value. When capital is on, a v2 block is appended (§10 metrics).
    """
    firms = econ.firms
    cfirms = econ.c_firms
    kfirms = getattr(econ, "k_firms", [])
    households = econ.households
    led = econ.ledger
    n_h = len(households)

    hh_dep = [led.balance(h.id) for h in households]
    firm_dep = [led.balance(f.id) for f in firms]
    hh_money = float(np.sum(hh_dep))
    firm_money = float(np.sum(firm_dep))
    total_money = float(led.total_money)   # broad money ΣD (incl. bank; endogenous in v3)

    # consumption sector (the "output/price" side; == all firms in v1)
    prices = [f.price for f in cfirms]
    markups = [f.markup for f in cfirms]
    produced_c = [f.produced for f in cfirms]
    sales_c = [f.sales for f in cfirms]
    revenue_c = [f.revenue for f in cfirms]
    inventory_c = [f.inventory for f in cfirms]

    # all firms (labor/money/wages span both sectors)
    wages = [f.wage for f in firms]
    wagebill = [f.wagebill for f in firms]
    profit = [f.profit for f in firms]
    labor_demand = [f.labor_demand_eff for f in firms]
    hired = [f.hired for f in firms]
    produced_all = [f.produced for f in firms]
    sales_all = [f.sales for f in firms]

    total_produced = float(np.sum(produced_c))          # consumption output
    total_sales_u = float(np.sum(sales_c))
    total_revenue = float(np.sum(revenue_c))            # R_C
    total_wagebill = float(np.sum(wagebill))
    total_profit = float(np.sum(profit))
    total_hired = float(np.sum(hired))
    total_labor_demand = float(np.sum(labor_demand))
    labor_supply = float(n_h)

    desired_cons = float(np.sum([h.consumption_budget for h in households]))
    effective_cons = float(np.sum([h.spent for h in households]))
    income_realized = float(np.sum([h.income_realized for h in households]))

    # Price index: consumption sales-weighted when there were sales, else mean posted.
    price_index = (total_revenue / total_sales_u) if total_sales_u > 1e-12 else _mean(prices)

    # Inflation vs last tick's price index (0 on the first tick).
    prev_p = getattr(econ, "_prev_price_index", None)
    inflation = (price_index / prev_p - 1.0) if (prev_p and prev_p > 1e-12) else 0.0
    econ._prev_price_index = price_index

    dividends_paid = float(getattr(econ, "_dividends_paid", 0.0))
    retained = max(0.0, total_profit) - dividends_paid  # positive profit not paid out

    rec: Dict[str, float] = {
        "t": econ.t,

        # -- money & shares --------------------------------------------------
        "total_money": total_money,
        "hh_money": hh_money,
        "firm_money": firm_money,
        "hh_money_share": hh_money / total_money if total_money > 0 else 0.0,
        "conservation_drift": abs(led.net_worth - led.genesis_money),   # A5 drift (=M0 drift in v1/v2)

        # -- circular flows (this tick) --------------------------------------
        "wages_paid": total_wagebill,
        "consumption_spending": total_revenue,       # = goods-market money hh->firm
        "dividends_paid": dividends_paid,
        "profit_total": total_profit,
        "retained_total": retained,
        "hh_income": income_realized,                # wages + dividends received
        "hh_saving": income_realized - effective_cons,

        # -- real activity ---------------------------------------------------
        "real_output": total_produced,               # consumption units produced
        "real_consumption": total_sales_u,           # consumption units sold
        "inventory": float(np.sum(inventory_c)),
        "inventory_investment": total_produced - total_sales_u,

        # -- prices ----------------------------------------------------------
        "price_index": price_index,
        "mean_price": _mean(prices),
        "price_std": _std(prices),
        "price_cv": cv(prices),
        "inflation": inflation,
        "avg_markup": _mean(markups),
        "markup_std": _std(markups),
        "avg_wage": _mean(wages),
        "wage_std": _std(wages),

        # -- labor -----------------------------------------------------------
        "labor_demand": total_labor_demand,
        "labor_supply": labor_supply,
        "employment": total_hired,
        "unemployment_rate": max(0.0, 1.0 - total_hired / labor_supply),
        "vacancies_unfilled": max(0.0, total_labor_demand - total_hired),
        "labor_fill_rate": (total_hired / total_labor_demand) if total_labor_demand > 1e-12 else 1.0,

        # -- demand residuals ------------------------------------------------
        "desired_consumption": desired_cons,
        "effective_consumption": effective_cons,
        "unsatisfied_demand_ratio": float(getattr(econ, "_unsat_ratio", 0.0)),

        # -- distributions (for §4: wealth shape, Zipf firm size) ------------
        "hh_wealth_gini": gini(hh_dep),
        "hh_wealth_top10_share": top_share(hh_dep, 0.10),
        "hh_wealth_cv": cv(hh_dep),
        "hh_wealth_min": float(np.min(hh_dep)) if hh_dep else 0.0,
        "hh_wealth_max": float(np.max(hh_dep)) if hh_dep else 0.0,
        "firm_deposits_gini": gini(firm_dep),
        "firm_size_gini_output": gini(produced_all),
        "firm_size_top_share_output": top_share(produced_all, 0.20),
        "firm_deposits_max": float(np.max(firm_dep)) if firm_dep else 0.0,

        # -- diagnostics -----------------------------------------------------
        "n_firms_producing": float(np.sum(np.asarray(produced_all) > 1e-9)),
        "n_firms_selling": float(np.sum(np.asarray(sales_all) > 1e-9)),
    }

    # ----------------------------------------------------------------------
    # v2 block (DESIGNDOC §10). Appended only when a capital sector exists, so
    # every legacy key above keeps its exact v1 value.
    # ----------------------------------------------------------------------
    if kfirms:
        c_money = float(np.sum([led.balance(f.id) for f in cfirms]))
        k_money = float(np.sum([led.balance(f.id) for f in kfirms]))
        B_C = float(np.sum([f.wagebill for f in cfirms]))
        B_K = float(np.sum([f.wagebill for f in kfirms]))     # capital-sector wages: the cure channel
        R_K = float(np.sum([f.revenue for f in kfirms]))      # investment spending (money F_C->F_K)
        inv_units = float(np.sum([f.investment for f in firms]))     # C + K (v2.5)
        agg_K = float(np.sum([f.capital for f in firms]))            # total capital (K-firms 0 in v2)
        c_capital = float(np.sum([f.capital for f in cfirms]))
        k_capital = float(np.sum([f.capital for f in kfirms]))       # >0 only in v2.5
        cap_produced = float(np.sum([f.produced for f in kfirms]))
        cap_inventory = float(np.sum([f.inventory for f in kfirms]))
        cap_prices = [f.price for f in kfirms]
        Pi_C = float(np.sum([f.profit for f in cfirms]))
        Pi_K = float(np.sum([f.profit for f in kfirms]))

        def _div_paid(f):   # dividends actually transferred = intended minus A4 cap shortfall
            return f.rho * max(0.0, f.profit) - f.dividend_shortfall

        V_C = float(np.sum([_div_paid(f) for f in cfirms]))
        V_K = float(np.sum([_div_paid(f) for f in kfirms]))   # K payout to households
        retained_intended = float(np.sum([(1.0 - f.rho) * max(0.0, f.profit) for f in firms]))
        shortfall = float(np.sum([f.dividend_shortfall for f in firms]))
        n_capped = float(np.sum([1 for f in firms if f.dividend_shortfall > 1e-9]))

        rec.update({
            # sector money
            "c_firm_money": c_money,
            "k_firm_money": k_money,
            # circular flows split by sector (the §10.3 money-return channel)
            "wages_C": B_C,
            "wages_K": B_K,                        # B_K -- watch this: the cure
            "dividends_C": V_C,
            "dividends_K": V_K,
            "investment_spending": R_K,            # R_K (money)
            "investment_units": inv_units,         # I_t (real capital bought)
            "profit_C": Pi_C,
            "profit_K": Pi_K,
            # capital
            "aggregate_capital": agg_K,            # ΣK_f -- the endogenous output ceiling
            "c_capital": c_capital,
            "k_capital": k_capital,                # K-sector own capital (>0 only in v2.5)
            "capital_output": cap_produced,
            "capital_inventory": cap_inventory,
            "capital_price_index": _mean(cap_prices),
            # drain decomposition (boom form ΔH = R_K − (1−ρ)Π_total):
            "retained_intended_total": retained_intended,
            "net_drain": retained_intended - R_K,  # >0 drains hh, <0 refills (boom)
            # dividend/investment cash conflict (PLAN_v2 §1.1)
            "dividend_shortfall": shortfall,
            "dividend_cash_capped": n_capped,
        })

    # ----------------------------------------------------------------------
    # v3 block (DESIGNDOC §12). Appended only when a bank exists.
    # ----------------------------------------------------------------------
    if getattr(econ, "bank", None) is not None:
        total_credit = float(led.total_credit)
        firm_debt = [led.debt(f.id) for f in firms]
        firm_nw = [max(0.0, led.balance(f.id) - led.debt(f.id)) for f in firms]
        total_firm_nw = float(np.sum(firm_nw))
        rec.update({
            "broad_money": total_money,                 # ΣD -- the headline: must be ALIVE
            "total_credit": total_credit,               # ΣL
            "net_worth": float(led.net_worth),          # ΣD − ΣL, must = M (A5 check)
            "bank_money": float(led.balance(econ.bank.id)),   # retained interest (small new sink)
            "credit_to_M": total_credit / led.genesis_money,
            "aggregate_leverage": (total_credit / total_firm_nw) if total_firm_nw > 1e-9 else 0.0,
            "n_firms_borrowing": float(np.sum(np.asarray(firm_debt) > 1e-9)),
            "new_loans": float(getattr(econ, "_new_loans", 0.0)),
            "credit_wage": float(getattr(econ, "_credit_wage", 0.0)),
            "credit_investment": float(getattr(econ, "_credit_investment", 0.0)),
            "interest_paid": float(getattr(econ, "_interest_paid", 0.0)),
            "principal_repaid": float(getattr(econ, "_principal_repaid", 0.0)),
        })

    # ----------------------------------------------------------------------
    # v4 block (DESIGNDOC §13). Firm demographics. Appended when firm_dynamics on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "firm_dynamics", False):
        bank_eq = float(led.balance(econ.bank.id))
        n_zombie = float(np.sum([1 for f in cfirms
                                 if led.balance(f.id) - led.debt(f.id) < -1e-9]))
        rec.update({
            "firm_count_c": float(len(cfirms)),        # emergent (entry↔exit balance)
            "births": float(getattr(econ, "_births", 0)),
            "deaths": float(getattr(econ, "_deaths", 0)),
            "writeoffs": float(getattr(econ, "_writeoffs", 0.0)),   # bad debt this tick
            "bank_equity": bank_eq,                    # < 0 => bank insolvent (systemic crisis)
            "bank_insolvent": 1.0 if bank_eq < -1e-9 else 0.0,
            "n_zombies": n_zombie,                     # persistently-insolvent C-firms (should ~0)
        })

    # ----------------------------------------------------------------------
    # v6 block (DESIGNDOC §16). Equity market. Appended when capital_market on.
    # ----------------------------------------------------------------------
    if getattr(econ, "equity", None) is not None:
        mkt = econ.equity
        market_cap = mkt.price * mkt.float_shares
        # household wealth NOW includes equity (choice 乙): D_h + shares_h·p.
        hh_wealth = [hh_dep[i] + households[i].shares * mkt.price for i in range(n_h)]
        rec.update({
            "stock_price": float(mkt.price),
            "market_cap": float(market_cap),
            "book_value": float(mkt.book_value),
            "fundamental_ps": float(mkt.fundamental),
            "bubble_gap": float(market_cap - mkt.book_value),      # valuation phantom (not money)
            "tobin_q": float(market_cap / mkt.book_value) if abs(mkt.book_value) > 1e-9 else 0.0,
            "equity_trend": float(mkt.trend),
            "equity_turnover": float(getattr(econ, "_equity_turnover", 0.0)),
            "hh_wealth_gini_incl_equity": gini(hh_wealth),         # 乙: the T8-relevant measure
            "equity_wealth_share": float(mkt.price * mkt.float_shares
                                         / max(1e-9, np.sum(hh_wealth))),
            "dividend_yield": float(dividends_paid / market_cap) if market_cap > 1e-9 else 0.0,
            "shares_outstanding": float(np.sum([h.shares for h in households])),  # == float (gate)
        })

    # ----------------------------------------------------------------------
    # v6.1 block (DESIGNDOC §18). Per-firm stock market. Appended when per_firm_equity on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "per_firm_equity", False):
        qs = [f.tobin_q for f in cfirms]
        share_prices = [f.share_price for f in cfirms]
        mkt_cap = float(np.sum([f.share_price * f.shares_outstanding for f in cfirms]))
        price_of = {f.id: f.share_price for f in cfirms}
        eq_val = [float(np.sum([sh * price_of.get(fid, 0.0) for fid, sh in h.holdings.items()]))
                  for h in households]
        hh_wealth = [hh_dep[i] + eq_val[i] for i in range(n_h)]
        held: Dict[str, float] = {}
        for h in households:
            for fid, sh in h.holdings.items():
                held[fid] = held.get(fid, 0.0) + sh
        drift = max((abs(held.get(f.id, 0.0) - f.shares_outstanding) for f in cfirms), default=0.0)
        inv = [f.investment for f in cfirms]
        iq = (float(np.corrcoef(inv, qs)[0, 1])
              if len(cfirms) > 2 and np.std(inv) > 1e-12 and np.std(qs) > 1e-12 else 0.0)
        rec.update({
            "equity_market_cap": mkt_cap,
            "tobin_q_mean": float(np.mean(qs)) if qs else 0.0,
            "tobin_q_dispersion": float(np.std(qs)) if qs else 0.0,
            "n_firms_q_above_1": float(np.sum(np.asarray(qs) > 1.0)) if qs else 0.0,
            "share_price_dispersion": cv(share_prices),
            "equity_ownership_gini": gini(eq_val),           # who owns equity (founder concentration)
            "hh_wealth_gini_incl_equity": gini(hh_wealth),   # T8 with per-firm equity (choice 乙)
            "equity_wealth_share": mkt_cap / max(1e-9, float(np.sum(hh_wealth))),
            "investment_q_corr": iq,                          # v6.1b: does investment track q?
            "shares_conservation_drift": float(drift),        # per-firm float gate (== 0)
            "equity_turnover": float(getattr(econ, "_equity_turnover", 0.0)),
            "equity_raised": float(getattr(econ, "_equity_raised", 0.0)),   # v6.2: capex funded by issuance
            "shares_outstanding_total": float(np.sum([f.shares_outstanding for f in cfirms])),
        })

    # ----------------------------------------------------------------------
    # v7 block (DESIGNDOC §20). Household credit. Appended when household_credit on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "household_credit", False):
        debts = [led.debt(h.id) for h in households]
        nw = np.asarray([hh_dep[i] - debts[i] for i in range(n_h)])   # net worth = D - L (can be <0)
        hh_debt_total = float(np.sum(debts))
        cons = total_revenue                                          # consumption this tick
        rec.update({
            "household_debt_total": hh_debt_total,
            "household_credit_new": float(getattr(econ, "_hh_credit_new", 0.0)),
            "hh_interest_paid": float(getattr(econ, "_hh_interest", 0.0)),
            "household_leverage": hh_debt_total / max(1e-9, income_realized),  # debt / income
            "share_underwater": float(np.mean(nw < 0.0)),                     # fraction with D<L (net debtor)
            # net worth has negatives (borrowers) -> Gini on the min-shifted series (valid [0,1]).
            "hh_networth_gini": gini(list(nw - nw.min())),
            "hh_networth_min": float(nw.min()),
            "hh_networth_median": float(np.median(nw)),
            "consumption_credit_share": float(getattr(econ, "_hh_credit_new", 0.0)) / max(1e-9, cons),
        })

    # ----------------------------------------------------------------------
    # v8 block (DESIGNDOC §21). Household margin credit. Appended when margin_credit on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "margin_credit", False):
        price_of = {f.id: f.share_price for f in cfirms}
        eqv = np.asarray([float(np.sum([sh * price_of.get(fid, 0.0) for fid, sh in h.holdings.items()]))
                          for h in households])
        debt_arr = np.asarray([led.debt(h.id) for h in households])
        margin = np.asarray([h.margin_debt for h in households])
        bankeq = np.asarray([econ._bank_equity_value(h.id) for h in households]) \
            if getattr(econ.cfg, "bank_equity", False) else 0.0        # v11.5: bank-equity wealth
        nw_full = np.asarray(hh_dep) + eqv + bankeq - debt_arr  # TRUE net worth: cash + equity (firm+bank) − debt
        rec.update({
            "household_margin_debt": float(np.sum(margin)),
            "avg_household_leverage": float(np.sum(eqv) / max(1e-9, np.sum(nw_full))),  # equity / net worth
            "margin_deleveraged": float(getattr(econ, "_hh_margin_repaid", 0.0)),       # fire-sale repay
            "margin_credit_new": float(getattr(econ, "_hh_margin_new", 0.0)),
            # T8 with leverage: is wealth (cash+equity−debt) concentrating in a few?
            "hh_full_networth_gini": gini(list(nw_full - nw_full.min())),
            "hh_full_networth_top10": top_share(list(nw_full - nw_full.min()), 0.10),
            "share_margin_underwater": float(np.mean(nw_full < 0.0)),
        })

    # ----------------------------------------------------------------------
    # v8.1 block (DESIGNDOC §23). Gibrat growth. Appended when gibrat_growth on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "gibrat_growth", False):
        sizes = np.sort([v for v in produced_c if v > 1e-9])[::-1]
        pslope = 0.0
        if len(sizes) >= 8:
            s = sizes[:max(8, len(sizes) // 2)]          # upper-tail rank-size (Zipf = -1)
            pslope = float(np.polyfit(np.log(np.arange(1, len(s) + 1)), np.log(s), 1)[0])
        rec.update({
            "firm_attractiveness_gini": gini([f.attractiveness for f in cfirms]),
            "firm_size_pareto_slope": pslope,
        })

    # ----------------------------------------------------------------------
    # Derived macro indicators (§17) -- OBSERVATION ONLY: standard headline
    # rates/ratios computed from the series above (no mechanism, no conservation
    # impact), so a macro dashboard need not re-derive them post-hoc.
    # ----------------------------------------------------------------------
    avg_wage = _mean(wages)
    nominal_output = total_produced * price_index
    prev_y = getattr(econ, "_prev_real_output", None)
    prev_w = getattr(econ, "_prev_avg_wage", None)
    va = total_wagebill + max(0.0, total_profit)          # value added = wages + operating surplus
    rec.update({
        "nominal_output": nominal_output,                 # = real output × price index
        "real_output_growth": (total_produced / prev_y - 1.0) if (prev_y and prev_y > 1e-12) else 0.0,
        "wage_inflation": (avg_wage / prev_w - 1.0) if (prev_w and prev_w > 1e-12) else 0.0,
        "real_wage": (avg_wage / price_index) if price_index > 1e-12 else 0.0,
        "labor_productivity": (total_produced / total_hired) if total_hired > 1e-9 else 0.0,
        "labor_share": (total_wagebill / va) if va > 1e-9 else 0.0,   # functional distribution
        "savings_rate": ((income_realized - effective_cons) / income_realized) if income_realized > 1e-9 else 0.0,
        "money_velocity": (nominal_output / total_money) if total_money > 1e-9 else 0.0,
        "credit_to_gdp": (rec.get("total_credit", 0.0) / nominal_output) if nominal_output > 1e-9 else 0.0,
        "debt_service_ratio": ((rec.get("interest_paid", 0.0) + rec.get("principal_repaid", 0.0))
                               / nominal_output) if nominal_output > 1e-9 else 0.0,
        "income_gini": gini([h.income_realized for h in households]),          # income inequality
        "consumption_gini": gini([h.spent for h in households]),               # consumption inequality
    })
    # -- distributional / bottom-tail WELFARE (§8.3): what aggregates & Gini miss -- pure observation.
    #    Consumption is the welfare basis; LEVEL measures are REAL (÷ price_index), ratios stay nominal
    #    (scale-invariant). Relative poverty line = 50% of median consumption (adapts to inflation/growth).
    cons = np.asarray([h.spent for h in households], float)
    inc = np.asarray([h.income_realized for h in households], float)
    defl = price_index if price_index > 1e-12 else 1.0
    real_c = cons / defl
    med_c, med_i = float(np.median(cons)), float(np.median(inc))
    line = 0.5 * med_c
    poor = cons < line
    nbot = max(1, len(real_c) // 10)
    subsist = float(getattr(econ.cfg, "hh_subsistence", 0.0))
    rec.update({
        "poverty_rate": float(poor.mean()) if line > 1e-12 else 0.0,                       # FGT0 headcount
        "poverty_gap": float(((line - cons[poor]) / line).mean()) if (line > 1e-12 and poor.any()) else 0.0,  # FGT1 depth
        "bottom10_consumption": float(np.sort(real_c)[:nbot].mean()),                       # Rawlsian floor (real)
        "welfare_log": float(np.log(np.maximum(real_c, 1e-6)).mean()),                      # concave (utilitarian) SWF
        "sen_welfare": float(real_c.mean() * (1.0 - gini(list(cons)))),                     # level × equality
        "income_poverty_rate": float((inc < 0.5 * med_i).mean()) if med_i > 1e-12 else 0.0, # income-based robustness
        "consumption_floor_share": float((cons <= subsist).mean()) if subsist > 0.0 else 0.0,  # policy reach
    })
    # v9 government (§28): fiscal flows + NORMALISED balances (raw stocks are unreadable). deficit>0 =
    # net injection (spend>tax); expressed as a share of revenue AND of GDP. gov_debt = −GOV balance.
    if getattr(econ.cfg, "government", False):
        tax_profit = float(getattr(econ, "_tax_profit", 0.0))
        tax_income = float(getattr(econ, "_tax_income", 0.0))
        tax_consumption = float(getattr(econ, "_tax_consumption", 0.0))
        tax_wealth = float(getattr(econ, "_tax_wealth", 0.0))
        tax_total = tax_profit + tax_income + tax_consumption + tax_wealth
        benefit_paid = float(getattr(econ, "_benefit_paid", 0.0))
        gov_consumption = float(getattr(econ, "_gov_consumption", 0.0))
        jg_spending = float(getattr(econ, "_jg_spending", 0.0))    # v9.3 job-guarantee wage bill
        spend_total = benefit_paid + gov_consumption + jg_spending
        deficit = spend_total - tax_total                          # >0 = deficit (net outside-money injection)
        # v12: gov_debt = the government's total net liability. With bonds OFF this is exactly −TSY deposit balance
        # (bit-identical). With bonds ON: |TSY deposit-debt| + bonds outstanding + CB claim on TSY − TGA (the TSY's
        # cash; ⚠ D_TSY and TGA are the same cash from two sides, so TGA is SUBTRACTED, never double-added).
        gov_debt = -econ.ledger.balance(econ._fiscal) \
            + float(getattr(econ, "_bonds_outstanding", 0.0)) \
            + float(getattr(econ, "_cb_claim_on_tsy", 0.0)) - float(getattr(econ, "_tga", 0.0))
        # v9.3 job guarantee: the buffer stock absorbs the residual, so EFFECTIVE (no-income) unemployment ~0
        # while the PRIVATE unemployment_rate metric (firm-side, above) is left untouched -- T4 stays clean.
        jg_emp = float(getattr(econ, "_jg_employment", 0.0))
        jg_emp_rate = jg_emp / labor_supply if labor_supply > 1e-12 else 0.0
        rec.update({
            "tax_profit": tax_profit, "tax_income": tax_income,
            "tax_consumption": tax_consumption, "tax_wealth": tax_wealth,
            "tax_total": tax_total, "benefit_paid": benefit_paid, "gov_consumption": gov_consumption,
            "jg_spending": jg_spending, "jg_employment": jg_emp, "jg_employment_rate": jg_emp_rate,
            "effective_unemployment": max(0.0, rec["unemployment_rate"] - jg_emp_rate),
            "gov_spending": spend_total, "gov_deficit": deficit, "gov_debt": gov_debt,
            "gov_deficit_to_revenue": (deficit / tax_total) if tax_total > 1e-9 else 0.0,
            "gov_deficit_to_gdp": (deficit / nominal_output) if nominal_output > 1e-9 else 0.0,
            "gov_debt_to_gdp": (gov_debt / nominal_output) if nominal_output > 1e-9 else 0.0,
            "gov_spending_share_of_gdp": (spend_total / nominal_output) if nominal_output > 1e-9 else 0.0,
            "hh_bankruptcies": float(getattr(econ, "_hh_bankruptcies", 0.0)),
        })
        econ._prev_tax_total = tax_total          # fed to next tick's deficit-targeting rule
        econ._prev_benefit = benefit_paid
        econ._prev_nominal_output = nominal_output
        econ._prev_u = rec.get("unemployment_rate", 0.0)   # for the state-dependent (countercyclical) deficit
    # v9.1/v9.3 public capital: government investment AND job-guarantee public works build the stock.
    if getattr(econ.cfg, "gov_investment_share", 0.0) > 0.0 or getattr(econ.policy, "job_guarantee", False):
        priv_k = sum(f.capital for f in econ.c_firms)
        rec.update({
            "public_capital": float(econ.public_capital),
            "public_investment": float(getattr(econ, "_public_investment", 0.0)),
            "pubcap_factor": float(getattr(econ, "_pubcap_factor", 1.0)),
            "public_to_private_capital": float(econ.public_capital / max(1e-9, priv_k)),
        })
    # v10 central bank: expose the policy rate + smoothed inflation; feed _prev_inflation to next tick's rule.
    if getattr(econ.cfg, "central_bank", False):
        rate = float(getattr(econ, "_rate", econ.cfg.r_interest))
        infl_ema = float(getattr(econ, "_infl_ema", 0.0))
        rec.update({
            "policy_rate": rate,
            "inflation_ema": infl_ema,
            "real_rate": rate - infl_ema,        # ex-ante real policy rate (Taylor principle => rises with π)
        })
    # v11 multi-bank: capital, leverage, failures, bank-size concentration (only with >1 bank)
    if getattr(econ, "banks", None) and len(econ.banks) > 1:
        caps = [econ.ledger.balance(b.id) for b in econ.banks]
        lb = {b.id: 0.0 for b in econ.banks}
        for a in list(econ.firms) + list(econ.households):
            lb[econ._bank_for(a.id).id] += econ.ledger.debt(a.id)
        tot_cap = sum(c for c in caps if c > 0.0)
        # v11.3: loan-book concentration (HHI of loan-book shares; 1/n_banks = even, 1 = monopoly) and the
        # realized cross-borrower loan-rate dispersion (loan-book-weighted SD of bank spreads; 0 without competition).
        tot_lb = sum(max(0.0, v) for v in lb.values())
        hhi = float(sum((max(0.0, v) / tot_lb) ** 2 for v in lb.values())) if tot_lb > 1e-9 else 0.0
        spr = getattr(econ, "_bank_spread", {}) or {}
        if tot_lb > 1e-9 and spr:
            wmean = sum(max(0.0, lb.get(bid, 0.0)) * s for bid, s in spr.items()) / tot_lb
            wvar = sum(max(0.0, lb.get(bid, 0.0)) * (s - wmean) ** 2 for bid, s in spr.items()) / tot_lb
        else:
            wvar = 0.0
        rec.update({
            "n_bank_failures": float(getattr(econ, "_bank_failures_total", 0)),
            "banks_alive": float(sum(1 for b in econ.banks if b.alive)),
            "bank_capital": float(sum(caps)),
            "bank_leverage": float(sum(lb.values()) / tot_cap) if tot_cap > 1e-9 else 0.0,
            "bank_size_gini": float(gini([max(0.0, v) for v in lb.values()])),
            "bank_loanbook_hhi": hhi,
            "bank_rate_spread_sd": float(wvar ** 0.5),
        })
        # v11.4: the reserve tier + interbank market + deposit-side competition. Reserves conserve as a second
        # layer; the interbank market is LATENT under ample reserves (peak overdraft ≈ 0) but reported honestly.
        if getattr(econ.cfg, "interbank", False):
            dep = {b.id: 0.0 for b in econ.banks}                 # per-bank DEPOSIT base (partitioned)
            for h in econ.households:
                dep[econ._bank_for(h.id).id] += max(0.0, econ.ledger.balance(h.id))
            tot_dep = sum(dep.values())
            dep_hhi = float(sum((v / tot_dep) ** 2 for v in dep.values())) if tot_dep > 1e-9 else 0.0
            peak_od = -min([econ.ledger.reserve_min(b.id) for b in econ.banks] + [0.0])
            rec.update({
                "bank_reserves_total": float(sum(econ.ledger.reserves(b.id) for b in econ.banks)),  # BANK-side only
                "cb_reserves": float(econ.ledger.reserves("CB")),      # govt-debt-driven reserve injection
                "interbank_rate": float(getattr(econ, "_interbank_rate", 0.0)),
                "interbank_volume": float(getattr(econ, "_interbank_volume", 0.0)),
                "interbank_contagion_loss": float(getattr(econ, "_interbank_contagion_loss", 0.0)),
                "peak_intraday_overdraft": float(max(0.0, peak_od)),   # ≈0 (latent gridlock) under ample reserves
                "payments_gridlocked": float(getattr(econ, "_payments_blocked", 0.0)),
                "bank_deposit_hhi": dep_hhi,                           # deposit-market concentration (competition)
            })
        # v11.5: bank demographics & ownership (entry/exit, bank-equity concentration, runs)
        if getattr(econ.cfg, "bank_equity", False):
            bankeq_h = [econ._bank_equity_value(h.id) for h in econ.households]
            alive_bk = [b for b in econ.banks if b.alive]
            pp = [b.share_price / b.share_peak for b in alive_bk if b.share_peak > 1e-9]
            rec.update({
                "bank_births": float(getattr(econ, "_bank_births", 0)),
                "bank_deaths": float(getattr(econ, "_bank_deaths", 0)),
                "bank_equity_total": float(sum(bankeq_h)),
                "bank_equity_gini": float(gini([max(0.0, v) for v in bankeq_h])),   # bank-OWNERSHIP concentration
                "bank_deposit_flight": float(getattr(econ, "_run_flight_volume", 0.0)),   # run flight volume
                "bank_fear": float(getattr(econ, "_bank_fear", 0.0)),
                "bank_min_price_peak": float(min(pp)) if pp else 1.0,   # worst price/peak = deepest distress signal
                "bank_stock_turnover": float(getattr(econ, "_bank_equity_turnover", 0.0)),
            })
    # v12: the securities layer (bonds sterilise reserves). 0 when bonds off.
    if getattr(econ.cfg, "bonds", False):
        held = getattr(econ, "_bond_holdings", {}) or {}
        hh_ids = {h.id for h in econ.households}
        bank_ids = getattr(econ, "_bank_ids", set())
        lots = getattr(econ, "_bonds", []) or []
        # v12.3 THREE VALUES: face (bond identity) / book (cost, bank-money invariant) / market (MTM, wealth).
        market_total = float(sum(econ._bond_market_value(l) for l in lots)) if lots else 0.0
        book_total = float(sum(l["cost"] for l in lots)) if lots else 0.0
        bank_bond_face = float(sum(l["face"] for l in lots if l["holder"] in bank_ids)) if lots else 0.0
        alive_banks = [b for b in econ.banks if b.alive]
        econ_caps = [econ._bank_economic_capital(b) for b in alive_banks]
        rec.update({
            "bonds_outstanding": float(getattr(econ, "_bonds_outstanding", 0.0)),   # = Σ face
            "bond_book_total": book_total,
            "bond_market_total": market_total,
            "bond_mtm_pnl": market_total - book_total,          # <0 on a rate hike above coupon (duration/SVB)
            "hh_bond_wealth": float(sum(v for k, v in held.items() if k in hh_ids)),
            "bank_bond_face": bank_bond_face,
            "bank_economic_capital_min": float(min(econ_caps)) if econ_caps else 0.0,
            "gov_interest_bill": float(getattr(econ, "_gov_interest_bill", 0.0)),
            "cb_claim_on_tsy": float(getattr(econ, "_cb_claim_on_tsy", 0.0)),
            "tga": float(getattr(econ, "_tga", 0.0)),
            # v12.4: the CB's quantity tools (0 when omo/lolr off).
            "cb_absorbed": float(getattr(econ, "_cb_absorbed", 0.0)),      # reserves drained via OMO (reverse repo)
            "omo_flow": float(getattr(econ, "_omo_flow", 0.0)),           # this tick's drain(+)/inject(−)
            "lolr_advances": float(getattr(econ, "_lolr_advances", 0.0)),  # cumulative emergency reserves lent
            "reserve_M": float(getattr(econ.ledger, "_reserve_M", 0.0)),   # base money (now VARIABLE under OMO/QE)
        })
    econ._prev_inflation = inflation          # v10: last tick's realised inflation feeds the Taylor EMA
    econ._prev_real_output = total_produced
    econ._prev_avg_wage = avg_wage
    econ._price_level = price_index          # v9.2: fed to the price-indexed startup endowment
    return rec


# ---------------------------------------------------------------------------
# Post-run derived series & field ordering for stable CSV export
# ---------------------------------------------------------------------------
def _finite(x: float) -> bool:
    return x == x and abs(x) != float("inf")


def classify_series(values: List[float], *, tail_frac: float = 0.5) -> str:
    """Label a series 'frozen' | 'exploding' | 'alive' from its tail behavior.
    A rough, honest heuristic for the v1 'alive and bounded' bar (§7.5), not a proof."""
    if not values:
        return "empty"
    n = len(values)
    tail = values[max(1, int(n * (1 - tail_frac))):]
    lo, hi = min(tail), max(tail)
    mean = float(np.mean(tail))
    scale = max(abs(mean), 1e-9)
    last = values[-1]
    if not _finite(last) or abs(last) > 1e6 * scale:
        return "exploding"
    if (hi - lo) / scale < 1e-6:
        return "frozen"
    return "alive"


def field_order(records: List[dict]) -> List[str]:
    """Stable column order for CSV: 't' first, then remaining keys in first-seen
    order across all records (robust if some rows carry extra keys)."""
    cols: List[str] = ["t"]
    for r in records:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols
