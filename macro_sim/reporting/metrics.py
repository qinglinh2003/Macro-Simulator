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

import math
from typing import Dict, List, Sequence

import numpy as np

from macro_sim.reporting.collectors import EconomyMetricCollector, collect_metric_groups
from macro_sim.demographics.economic_state import build_household_economic_profiles, need_weight_for_person
from macro_sim.systems.banking import bank_equity_value, bank_for, bank_rwa_exposure
from macro_sim.systems.firm_balance_sheet import firm_balance_sheet, firm_return_asset_base
from macro_sim.systems.planning import CAPITAL_SERVICE_PRICED_SECTORS
from macro_sim.systems.securities import bond_market_value


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


def _quantile(x: Sequence[float], q: float) -> float:
    a = np.asarray(x, dtype=float)
    return float(np.quantile(a, q)) if a.size else 0.0


def _safe_ratio(num: float, den: float) -> float:
    return float(num / den) if abs(den) > 1e-12 else 0.0


def _sector_infl(econ, attr: str, price: float) -> float:
    """Tick-over-tick sector inflation against the last committed price.

    The corresponding hold-last value is advanced by :func:`commit_tick_metrics`,
    never by a reporting query.
    """
    prev = getattr(econ, attr, None)
    return (price / prev - 1.0) if (prev and prev > 1e-12) else 0.0


def _deprivation_person_observations(econ) -> tuple[int, list]:
    """Build the raw deprivation observation shared by preview and commit."""
    bridge = getattr(econ, "demographic_bridge", None)
    state = getattr(econ, "demographic_state", None)
    if bridge is None or state is None:
        return 0, []
    alive_people = [
        person for person in getattr(state, "people", []) if getattr(person, "alive", True)
    ]
    persons = [
        (
            int(person.id),
            int(person.household_id),
            need_weight_for_person(person),
            bridge.claims.balance_sheet(int(person.id)).consumption_allocated_tick,
            int(getattr(person, "age", 0)),
            bridge.claims.balance_sheet(int(person.id)).net_worth,
            bridge.claims.balance_sheet(int(person.id)).cash_claim,
        )
        for person in alive_people
        if bridge.claims.has_person(int(person.id))
    ]
    return int(state.current_date.year), persons


def _bank_economic_capital_snapshot(econ, bank, bond_deltas_by_holder=None) -> float:
    """Read bank economic capital WITHOUT populating the behavioral bond cache (metrics must
    leave econ untouched -- test_metrics_purity).

    ``bond_deltas_by_holder`` is an optional pre-computed {holder: [market-cost per lot in lot
    order]} map, built ONCE by a pure local pass in _compute_tick_metrics (no econ mutation). When
    supplied it replaces the former per-bank full-lot re-scan (O(n_banks x n_lots) per call). The
    ``+=`` accumulation from the ledger balance over the same lot-ordered deltas is byte-for-byte
    the old sequence, so the snapshot stays bit-identical."""
    capital = econ.ledger.balance(bank.id)
    if econ.cfg.bonds:
        if bond_deltas_by_holder is not None:
            for delta in bond_deltas_by_holder.get(bank.id, ()):  # lot order preserved
                capital += delta
        else:
            for lot in getattr(econ, "_bonds", ()):
                if lot["holder"] == bank.id:
                    capital += bond_market_value(econ, lot) - lot["cost"]
    return capital


def _bond_deltas_by_holder(econ) -> dict:
    """Pure local {holder: [market-cost per lot in lot order]} for the bank-capital snapshots.

    ONE pass over the lots, mirroring the per-holder ``+=`` order the snapshot used to rebuild
    per bank -- so it is bit-identical -- but shared across every bank and every snapshot call
    site instead of re-scanning all lots per bank (was O(n_call_sites x n_banks x n_lots)). This
    does NOT touch econ._bond_valuation_cache, so metrics stay pure (test_metrics_purity)."""
    deltas: dict = {}
    for lot in getattr(econ, "_bonds", ()):
        deltas.setdefault(lot["holder"], []).append(bond_market_value(econ, lot) - lot["cost"])
    return deltas


def _hhi(values: Sequence[float]) -> float:
    a = np.asarray([max(0.0, float(v)) for v in values], dtype=float)
    total = float(a.sum())
    if total <= 1e-12:
        return 0.0
    shares = a / total
    return float(np.sum(shares * shares))


def _skew(values: Sequence[float]) -> float:
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return 0.0
    m = float(a.mean())
    s = float(a.std())
    return float(np.mean(((a - m) / s) ** 3)) if s > 1e-12 else 0.0


def _excess_kurtosis(values: Sequence[float]) -> float:
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return 0.0
    m = float(a.mean())
    s = float(a.std())
    return float(np.mean(((a - m) / s) ** 4) - 3.0) if s > 1e-12 else 0.0


# ---------------------------------------------------------------------------
# Per-tick snapshot
# ---------------------------------------------------------------------------
def compute_tick_metrics(econ) -> Dict[str, float]:
    return collect_metric_groups(econ, [EconomyMetricCollector(_compute_tick_metrics)])


def _compute_tick_metrics(econ) -> Dict[str, float]:
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

    # Shell hygiene, HOUSEHOLD edition (mirror of the firm-seller rule below):
    # demographically dissolved households keep their agent + ledger account for
    # accounting continuity (escheat drains them to zero) but accumulate
    # monotonically, so COUNT-based distributional statistics -- gini, quantiles,
    # top shares, poverty -- scan households with LIVING members only. Aggregate
    # SUMS keep scanning everyone: residual shell stocks must stay visible in totals.
    _bridge = getattr(econ, "demographic_bridge", None)
    if _bridge is not None:
        live_mask = np.asarray(
            [_bridge.household_has_living_members(h.id) for h in households], dtype=bool
        )
        live_households = [h for h, alive in zip(households, live_mask) if alive]
        live_dep = [d for d, alive in zip(hh_dep, live_mask) if alive]
    else:
        live_mask = np.ones(n_h, dtype=bool)
        live_households = households
        live_dep = hh_dep
    n_live = len(live_households)

    # consumption sector (the "output/price" side; == all firms in v1)
    # v13 shell hygiene: posted-price/markup stats read ACTIVE SELLERS -- never-trading shells
    # carried stale exploding posted prices that blew mean_price to 1e20 and buried tobin_q /
    # wage medians in the 10k x 3650t audit. Falls back to all firms when nothing sold (t0).
    _selling_c = [f for f in cfirms if f.sales > 1e-9]
    _stat_c = _selling_c if _selling_c else cfirms
    prices = [f.price for f in _stat_c]
    markups = [f.markup for f in _stat_c]
    produced_c = [f.produced for f in cfirms]
    sales_c = [f.sales for f in cfirms]
    revenue_c = [f.revenue for f in cfirms]
    inventory_c = [f.inventory for f in cfirms]

    # all firms (labor/money/wages span both sectors)
    _hiring = [f for f in firms if f.hired > 1e-9]
    wages = [f.wage for f in (_hiring if _hiring else firms)]
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
    bridge = getattr(econ, "demographic_bridge", None)
    demographic_profiles = {}
    if bridge is not None and getattr(econ, "demographic_state", None) is not None:
        demographic_profiles = build_household_economic_profiles(econ.demographic_state, bridge.claims)
    labor_supply = (
        float(sum(profile.labor_supply for profile in demographic_profiles.values()))
        if demographic_profiles
        else float(n_h)
    )

    desired_cons = float(np.sum([h.consumption_budget for h in households]))
    effective_cons = float(np.sum([h.spent for h in households]))
    income_realized = float(np.sum([h.income_realized for h in households]))

    # Price index: consumption sales-weighted when there were sales, else mean posted.
    price_index = (total_revenue / total_sales_u) if total_sales_u > 1e-12 else _mean(prices)

    # Inflation vs last COMMITTED tick's price index (0 on the first tick).
    prev_p = getattr(econ, "_prev_price_index", None)
    inflation = (price_index / prev_p - 1.0) if (prev_p and prev_p > 1e-12) else 0.0
    hist = getattr(econ, "_price_index_history", None)
    yoy_base = hist[0] if hist and len(hist) == 365 else (hist[0] if hist else price_index)
    inflation_yoy = (price_index / yoy_base - 1.0) if yoy_base > 1e-12 else 0.0

    dividends_paid = float(getattr(econ, "_dividends_paid", 0.0))
    # ``retained_total`` is a distributable-income measure, so losses at one firm
    # must not erase another firm's positive earnings before the latter's dividend
    # is deducted.  The old aggregate truncation could report a negative retained
    # amount whenever loss-making firms pulled aggregate profit below dividends.
    distributable_profit = float(np.sum([max(0.0, f.profit) for f in firms]))
    retained = max(0.0, distributable_profit - dividends_paid)

    rec: Dict[str, float] = {
        "t": econ.t,

        # -- money & shares --------------------------------------------------
        "total_money": total_money,
        "hh_money": hh_money,
        "firm_money": firm_money,
        "hh_money_share": hh_money / (hh_money + firm_money) if (hh_money + firm_money) > 0 else 0.0,
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
        "inflation_yoy": inflation_yoy,   # v13: trailing-365-tick price change (annual inflation on a day tick)
        "avg_markup": _mean(markups),
        "markup_std": _std(markups),
        "avg_wage": _mean(wages),
        "avg_wage_paid": (total_wagebill / total_hired) if total_hired > 1e-9 else _mean(wages),
        "wage_std": _std(wages),

        # -- labor -----------------------------------------------------------
        "labor_demand": total_labor_demand,
        "labor_supply": labor_supply,
        "employment": total_hired,
        "unemployment_rate": max(0.0, 1.0 - total_hired / labor_supply),
        "vacancies_unfilled": max(0.0, total_labor_demand - total_hired),
        "labor_fill_rate": (total_hired / total_labor_demand) if total_labor_demand > 1e-12 else 1.0,
        "demographic_alive": float(getattr(getattr(econ, "demographic_state", None), "alive_count", 0)),
        "demographic_households": float(len(demographic_profiles)),
        "demographic_children": float(sum(profile.child_count for profile in demographic_profiles.values())),
        "demographic_adults": float(sum(profile.adult_count for profile in demographic_profiles.values())),
        "demographic_elders": float(sum(profile.elder_count for profile in demographic_profiles.values())),
        "dependency_ratio": _safe_ratio(
            sum(profile.child_count + profile.elder_count for profile in demographic_profiles.values()),
            sum(profile.adult_count for profile in demographic_profiles.values()),
        ),

        # -- demand residuals ------------------------------------------------
        "desired_consumption": desired_cons,
        "effective_consumption": effective_cons,
        "unsatisfied_demand_ratio": float(getattr(econ, "_unsat_ratio", 0.0)),

        # -- distributions (for §4: wealth shape, Zipf firm size) ------------
        "hh_wealth_gini": gini(live_dep),
        "hh_wealth_top10_share": top_share(live_dep, 0.10),
        "hh_wealth_cv": cv(live_dep),
        "hh_wealth_min": float(np.min(live_dep)) if live_dep else 0.0,
        "hh_wealth_max": float(np.max(live_dep)) if live_dep else 0.0,
        "firm_deposits_gini": gini(firm_dep),
        "firm_size_gini_output": gini(produced_all),
        "firm_size_top_share_output": top_share(produced_all, 0.20),
        "firm_deposits_max": float(np.max(firm_dep)) if firm_dep else 0.0,

        # -- diagnostics -----------------------------------------------------
        "n_firms_producing": float(np.sum(np.asarray(produced_all) > 1e-9)),
        "n_firms_selling": float(np.sum(np.asarray(sales_all) > 1e-9)),
    }

    # Opt-in full firm income statement.  Named aggregates are exported only
    # when the mechanism is active, so legacy record schemas and values remain
    # bit-identical.  ``profit_total`` above is already net income in this mode;
    # these fields expose every bridge layer and its hard diagnostic residuals.
    if getattr(econ.cfg, "firm_full_pnl", False):
        pnl_firms = list(firms) + list(getattr(econ, "_exited_firms_tick", ()))
        pnl_reported_profit = float(np.sum([f.profit for f in pnl_firms]))
        pnl_revenue = float(np.sum([f.pnl_revenue for f in pnl_firms]))
        pnl_intermediate = float(np.sum([f.pnl_intermediate_inputs for f in pnl_firms]))
        pnl_compensation = float(np.sum([f.pnl_compensation for f in pnl_firms]))
        pnl_ebitda = float(np.sum([f.pnl_ebitda for f in pnl_firms]))
        pnl_depreciation = float(np.sum([f.pnl_depreciation for f in pnl_firms]))
        pnl_ebit = float(np.sum([f.pnl_ebit for f in pnl_firms]))
        pnl_interest_accrued = float(np.sum([f.pnl_interest_accrued for f in pnl_firms]))
        pnl_interest_due = float(np.sum([f.pnl_interest_due for f in pnl_firms]))
        pnl_cash_interest = float(np.sum([f.pnl_interest_expense for f in pnl_firms]))
        pnl_pre_tax = float(np.sum([f.pnl_pre_tax_income for f in pnl_firms]))
        pnl_profit_tax = float(np.sum([f.pnl_profit_tax for f in pnl_firms]))
        pnl_windfall_tax = float(np.sum([f.pnl_windfall_tax for f in pnl_firms]))
        pnl_net_income = float(np.sum([f.pnl_net_income for f in pnl_firms]))
        pnl_dividends = float(np.sum([f.pnl_dividends_paid for f in pnl_firms]))
        pnl_retained = float(np.sum([f.pnl_retained_earnings for f in pnl_firms]))
        pnl_arrears = float(np.sum([f.pnl_interest_arrears for f in pnl_firms]))
        pnl_revenue_carry = float(np.sum([f.pnl_revenue_carry for f in pnl_firms]))
        bridge_residuals = (
            pnl_ebitda - (pnl_revenue - pnl_intermediate - pnl_compensation),
            pnl_ebit - (pnl_ebitda - pnl_depreciation),
            pnl_pre_tax - (pnl_ebit - pnl_cash_interest),
            pnl_net_income - (pnl_pre_tax - pnl_profit_tax - pnl_windfall_tax),
            pnl_retained - (pnl_net_income - pnl_dividends),
            pnl_reported_profit - pnl_net_income,
        )
        rec.update({
            "firm_full_pnl_enabled": 1.0,
            "firm_pnl_revenue": pnl_revenue,
            "firm_pnl_intermediate_inputs": pnl_intermediate,
            "firm_pnl_compensation": pnl_compensation,
            "firm_pnl_ebitda": pnl_ebitda,
            "firm_pnl_capital_price": float(getattr(econ, "_firm_pnl_capital_price", 0.0)),
            "firm_pnl_depreciation": pnl_depreciation,
            "firm_pnl_ebit": pnl_ebit,
            "firm_pnl_interest_accrued": pnl_interest_accrued,
            "firm_pnl_interest_due": pnl_interest_due,
            "firm_pnl_cash_interest": pnl_cash_interest,
            "firm_pnl_pre_tax_income": pnl_pre_tax,
            "firm_pnl_profit_tax": pnl_profit_tax,
            "firm_pnl_windfall_tax": pnl_windfall_tax,
            "firm_pnl_tax_total": pnl_profit_tax + pnl_windfall_tax,
            "firm_pnl_net_income": pnl_net_income,
            "firm_pnl_dividends_paid": pnl_dividends,
            "firm_pnl_retained_earnings": pnl_retained,
            "firm_pnl_interest_arrears": pnl_arrears,
            "firm_pnl_post_close_revenue_carry": pnl_revenue_carry,
            "firm_pnl_profit_compatibility_residual": pnl_reported_profit - pnl_net_income,
            "firm_pnl_bridge_max_abs_residual": max(abs(value) for value in bridge_residuals),
            "firm_pnl_interest_cash_counter_residual": (
                pnl_cash_interest - float(getattr(econ, "_interest_paid", 0.0))
            ),
            "firm_bank_interest_counterparty_residual": (
                float(np.sum([bank.loan_interest for bank in econ.banks]))
                - pnl_cash_interest
                - float(getattr(econ, "_hh_interest", 0.0))
            ),
        })

    if getattr(econ.cfg, "capital_service_pricing", False):
        priced_firms = [
            firm for firm in firms
            if firm.sells in CAPITAL_SERVICE_PRICED_SECTORS
        ]
        energy_priced_firms = [firm for firm in priced_firms if firm.sells == "energy"]
        planned_output = float(np.sum([max(0.0, f.production_target) for f in priced_firms]))
        allocated_cost = float(np.sum([
            max(0.0, f.pricing_capital_unit_cost) * max(0.0, f.production_target)
            for f in priced_firms
        ]))
        energy_allocated_cost = float(np.sum([
            max(0.0, f.pricing_capital_unit_cost) * max(0.0, f.production_target)
            for f in energy_priced_firms
        ]))
        rec.update({
            "capital_service_pricing_enabled": 1.0,
            "capital_service_replacement_price": float(
                _mean([f.pricing_capital_price for f in priced_firms])
            ),
            "capital_service_replacement_price_closing": float(
                getattr(econ, "_firm_pnl_capital_price", 0.0)
            ),
            "capital_service_cost_planned": float(np.sum([
                max(0.0, f.pricing_capital_service_cost) for f in priced_firms
            ])),
            "capital_service_cost_allocated": allocated_cost,
            "capital_service_unit_cost_output_weighted": (
                allocated_cost / planned_output if planned_output > 1.0e-12 else 0.0
            ),
        })
        if energy_priced_firms:
            rec.update({
                "energy_capital_service_cost_planned": float(np.sum([
                    max(0.0, f.pricing_capital_service_cost) for f in energy_priced_firms
                ])),
                "energy_capital_service_cost_allocated": energy_allocated_cost,
            })

    # v18.1 consumption sector split gauges: sector prices (feed the group CPIs in 18.2),
    # the aggregate necessity share (Engel level) + a rank gradient (Engel EMERGENCE),
    # sector markups + time-at-ceiling + HHI (the markup watch), and sector firm counts
    # (the entry-oscillation watch). Only present when the split is on.
    if getattr(econ.cfg, "consumption_strata", False):
        def _sector(firms, previous_price_attr):
            rev = float(sum(f.revenue for f in firms))
            units = float(sum(f.sales for f in firms))
            out = float(sum(f.produced for f in firms))
            cap = float(sum(f.capital for f in firms))          # v18.5: sector capital (reallocation watch)
            sell = [f for f in firms if f.sales > 1e-9] or list(firms)
            # A sector can genuinely lose its last firm.  That is an economic state,
            # not permission for the reporting schema to disappear.  Hold the last
            # observed sector price when no seller remains, just as the aggregate
            # transaction-price indexes do, while the flow/count fields fall to zero.
            fallback_price = float(getattr(
                econ, previous_price_attr, getattr(econ.cfg, "p_firm0", 1.0),
            ))
            price = (
                rev / units if units > 1e-12
                else _mean([f.price for f in sell]) if sell
                else fallback_price
            )
            mk = _mean([f.markup for f in sell])
            at_cap = _mean([1.0 if f.markup >= f.mu_max - 1e-9 else 0.0 for f in firms])
            hhi = float(sum((f.revenue / rev) ** 2 for f in firms)) if rev > 1e-12 else 0.0
            return dict(rev=rev, units=units, out=out, cap=cap, price=price, mk=mk, at_cap=at_cap,
                        hhi=hhi, n=len(firms))
        N = _sector(getattr(econ, "n_firms", ()), "_cpi_prev_nec")
        L = _sector(getattr(econ, "l_firms", ()), "_cpi_prev_lux")
        tot_cons = N["rev"] + L["rev"]
        # Engel EMERGENCE: necessity share for the bottom vs top quintile of households
        # ranked by expenditure PER NEED-UNIT (affluence per person). The Engel axis must
        # be per-capita: the fixed necessity need scales with household size, so total
        # household expenditure is confounded by size and its gradient washes out; per
        # need-unit, necessity share ≈ const / (expenditure-per-unit) — a clean 1/E
        # decline. §4-style structural judge; the gradient is not seeded.
        bridge_ref = getattr(econ, "demographic_bridge", None)

        def _per_unit(h):
            if bridge_ref is not None:
                household_id = bridge_ref.household_id_for_account(h.id)
                profile = demographic_profiles.get(household_id)
                if profile is not None and profile.need_units > 1e-9:
                    return h.spent / profile.need_units
            return h.spent
        spenders = [(_per_unit(h), h) for h in households if h.spent > 1e-9]
        nec_share_bottomq = nec_share_topq = 0.0
        # v18.2 group-specific price LEVEL index ("whose inflation is whose"): each group's
        # own N / L / energy expenditure weights x the sector price RELATIVES to genesis
        # base. A LEVEL index (weighted price relatives), NOT compounded per-tick inflation
        # -- the sales-weighted sector price has large compositional jumps, and compounding
        # them amplifies measurement noise. The index is base-1 at genesis; its year-over-
        # year ratio is the group inflation (computed downstream from the level).
        base_c = max(1e-12, float(getattr(econ.cfg, "p_firm0", 1.0)))
        base_e = max(1e-12, float(getattr(econ.cfg, "p_efirm0", 1.0)))
        r_N = N["price"] / base_c
        r_L = L["price"] / base_c
        p_energy = float(getattr(econ, "_energy_price", 0.0))
        r_E = (p_energy / base_e) if p_energy > 0 else 1.0
        infl_N = _sector_infl(econ, "_cpi_prev_nec", N["price"])   # informational per-tick only
        infl_L = _sector_infl(econ, "_cpi_prev_lux", L["price"])
        cpi_bottomq_index = cpi_topq_index = 1.0
        if len(spenders) >= 5:
            spenders.sort(key=lambda t: t[0])
            q = max(1, len(spenders) // 5)
            bot = [h for _e, h in spenders[:q]]
            top = [h for _e, h in spenders[-q:]]

            def _grp(hs):
                nec = sum(h.necessity_spent for h in hs)
                lux = sum(max(0.0, h.spent - h.necessity_spent) for h in hs)
                ene = sum(getattr(h, "energy_spent", 0.0) for h in hs)
                tot = nec + lux + ene
                if tot <= 1e-12:
                    return 0.0, 1.0
                nshare = nec / tot
                idx = (nec * r_N + lux * r_L + ene * r_E) / tot   # weighted price relatives
                return nshare, idx
            nec_share_bottomq, cpi_bottomq_index = _grp(bot)
            nec_share_topq, cpi_topq_index = _grp(top)
        rec.update({
            "necessity_price_index": N["price"],
            "luxury_price_index": L["price"],
            "necessity_revenue": N["rev"],
            "luxury_revenue": L["rev"],
            "necessity_output": N["out"],
            "luxury_output": L["out"],
            "necessity_infl": infl_N,
            "luxury_infl": infl_L,
            "cpi_bottomq_index": cpi_bottomq_index,   # v18.2 group price level (democratic), base 1
            "cpi_topq_index": cpi_topq_index,         # v18.2 group price level (plutocratic), base 1
            "necessity_share": (N["rev"] / tot_cons) if tot_cons > 1e-12 else 0.0,
            "necessity_share_bottomq": nec_share_bottomq,
            "necessity_share_topq": nec_share_topq,
            "necessity_markup": N["mk"],
            "luxury_markup": L["mk"],
            "necessity_markup_at_cap": N["at_cap"],
            "luxury_markup_at_cap": L["at_cap"],
            "necessity_hhi": N["hhi"],
            "luxury_hhi": L["hhi"],
            "n_firms_necessity": float(N["n"]),
            "n_firms_luxury": float(L["n"]),
            "necessity_capital": N["cap"],                       # v18.5 sector capital + share
            "luxury_capital": L["cap"],
            "necessity_capital_share": (N["cap"] / (N["cap"] + L["cap"]))
                                       if (N["cap"] + L["cap"]) > 1e-12 else 0.0,
        })
        if getattr(econ.cfg, "sector_switching", False):
            rec.update({
                "sector_switches": float(getattr(econ, "_sector_switches", 0.0)),
                "sector_switch_capital": float(getattr(econ, "_sector_switch_capital", 0.0)),
            })

    # v18.4 family transfers (the first-line private safety net)
    if getattr(econ.cfg, "family_transfers", False):
        rec.update({
            "family_transfer_total": float(getattr(econ, "_family_transfer_total", 0.0)),
            "family_transfer_recipients": float(getattr(econ, "_family_transfer_recipients", 0.0)),
            "family_exposed": float(getattr(econ, "_family_exposed", 0.0)),   # in need, no kin donor
        })

    if bridge is not None:
        state = getattr(econ, "demographic_state", None)
        alive_people = [person for person in getattr(state, "people", []) if getattr(person, "alive", True)]
        claim_sheets = [
            bridge.claims.balance_sheet(int(person.id))
            for person in alive_people
            if bridge.claims.has_person(int(person.id))
        ]
        person_income = [
            sheet.labor_income_tick + sheet.capital_income_tick + sheet.transfer_income_tick
            for sheet in claim_sheets
        ]
        person_consumption = [sheet.consumption_allocated_tick for sheet in claim_sheets]
        person_wealth = [sheet.net_worth for sheet in claim_sheets]
        adult_consumption = [
            bridge.claims.balance_sheet(int(person.id)).consumption_allocated_tick
            for person in alive_people
            if int(person.age) >= 18 and int(person.age) < 65 and bridge.claims.has_person(int(person.id))
        ]
        child_consumption = [
            bridge.claims.balance_sheet(int(person.id)).consumption_allocated_tick
            for person in alive_people
            if int(person.age) < 18 and bridge.claims.has_person(int(person.id))
        ]
        elder_consumption = [
            bridge.claims.balance_sheet(int(person.id)).consumption_allocated_tick
            for person in alive_people
            if int(person.age) >= 65 and bridge.claims.has_person(int(person.id))
        ]
        adults = sum(profile.adult_count for profile in demographic_profiles.values())
        children = sum(profile.child_count for profile in demographic_profiles.values())
        elders = sum(profile.elder_count for profile in demographic_profiles.values())
        public_guardian_children = sum(
            1
            for person in alive_people
            if int(person.age) < 18 and person.household_id == getattr(state, "public_guardian_household_id", None)
        )
        rec.update(
            {
                "demographics_enabled": 1.0,
                "person_population_alive": float(len(alive_people)),
                "person_labor_supply": labor_supply,
                "person_employment_rate": _safe_ratio(total_hired, labor_supply),
                "person_unemployment_rate": max(0.0, 1.0 - _safe_ratio(total_hired, labor_supply)),
                "child_dependency_ratio": _safe_ratio(children, adults),
                "elder_dependency_ratio": _safe_ratio(elders, adults),
                "person_income_gini": gini(person_income),
                "person_consumption_gini": gini(person_consumption),
                "person_wealth_gini": gini(person_wealth),
                "adult_median_consumption": _quantile(adult_consumption, 0.5),
                "child_median_consumption": _quantile(child_consumption, 0.5),
                "elder_median_consumption": _quantile(elder_consumption, 0.5),
                "estate_suspense_total": bridge.estates.total_net_worth(),
                "inheritance_flow": float(getattr(econ, "_inheritance_flow", 0.0)),
                "escheat_flow": float(getattr(econ, "_escheat_flow", 0.0)),
                "pension_paid": float(getattr(econ, "_pension_paid", 0.0)),
                "claim_reconciled_flow": float(getattr(econ, "_claim_reconciled_flow", 0.0)),
                "public_guardian_children": float(public_guardian_children),
                "orphan_support_spending": float(
                    getattr(bridge, "orphan_support_spending", getattr(econ, "_orphan_support_spending", 0.0))
                ),
                # v14 Phase 2: macro->demography signal (annual; constant within the year). The
                # values are the ones the kernel saw THIS tick (observe_macro runs after metrics).
                "demo_signal_x": float(getattr(getattr(bridge, "macro_signal", None), "signal_x", 1.0)),
                "demo_signal_z": float(getattr(getattr(bridge, "macro_signal", None), "signal_z", 1.0)),
                "fertility_mult": float(getattr(getattr(bridge, "macro_signal", None), "fertility_mult", 1.0)),
                "mortality_mult": float(getattr(getattr(bridge, "macro_signal", None), "mortality_mult", 1.0)),
                "e0_effective": float(getattr(bridge, "e0_effective", 0.0)),
            }
        )
        # v18.0 deprivation gauges (observation only). Coverage is measured at the
        # HOUSEHOLD unit (the model charges dependents' needs to supporting adults, so a
        # child's own allocation is ~0), then inherited by members. The signal owns the
        # cumulative->flow differencing (consumption_allocated_tick is a lifetime stock)
        # and all aggregation; metrics just hands it the raw per-person snapshot.
        dep = getattr(econ, "deprivation_signal", None)
        if dep is not None and state is not None:
            dep_year, dep_persons = _deprivation_person_observations(econ)
            rec.update(dep.preview(year=dep_year, price_index=price_index, persons=dep_persons))

        strat = getattr(bridge, "stratification", None)
        if strat is not None:
            # v14 Phase 3.0: per-quintile vital gauges + the age-wealth confound gauge
            rec.update(
                {
                    **{f"bucket{k}_deaths": float(strat.bucket_deaths[k]) for k in range(strat.buckets)},
                    **{f"bucket{k}_births": float(strat.bucket_births[k]) for k in range(strat.buckets)},
                    **{f"bucket{k}_wealth_share": float(strat.bucket_wealth_share[k]) for k in range(strat.buckets)},
                    **{f"bucket{k}_pop_share": float(strat.bucket_pop_share[k]) for k in range(strat.buckets)},
                    "age_rank_corr": float(strat.age_rank_corr),
                    **{f"median_rank_band{i}": float(strat.median_rank_by_band[i]) for i in range(4)},
                    **{f"bucket{k}_mortality_mult": float(strat.bucket_mortality_mult[k]) for k in range(strat.buckets)},
                    **{f"bucket{k}_fertility_mult": float(strat.bucket_fertility_mult[k]) for k in range(strat.buckets)},
                    "spousal_rank_corr": float(strat.spousal_rank_corr),
                }
            )
    else:
        rec["demographics_enabled"] = 0.0

    accounts = getattr(econ, "labor_accounts", None)
    if accounts is not None:
        # v16-L0: the five-state labor taxonomy + the Beveridge pair. Flow counters are
        # zero under the spot market; L1 populates them.
        rec.update(
            {
                "labor_E": float(accounts.employed),
                "labor_employed_heads": float(accounts.employed_heads),
                "labor_average_private_job_hours": _safe_ratio(
                    accounts.employed, accounts.employed_heads,
                ),
                "labor_underemployed_heads": float(accounts.underemployed_heads),
                "labor_underemployment_hours": float(accounts.underemployment_hours),
                # v23 second contract: heads holding a live extra job + the FTE-hours it sells
                "labor_second_job_heads": float(getattr(accounts, "second_job_heads", 0.0)),
                "labor_second_job_hours": float(getattr(accounts, "second_job_hours", 0.0)),
                "labor_U": float(accounts.unemployed),
                "labor_S": float(accounts.suspended_memo),
                "labor_JG": float(accounts.job_guarantee),
                "labor_OLF": float(accounts.out_of_labor_force),
                "labor_u_rate": float(accounts.unemployment_rate),
                "labor_vacancies": float(accounts.vacancies),
                "labor_v_rate": float(accounts.vacancy_rate),
                "labor_hires_total": float(accounts.hires_total),
                "labor_churn_seps_total": float(accounts.churn_seps_total),
                "labor_layoff_seps_total": float(accounts.layoff_seps_total),
                "labor_bankruptcy_seps_total": float(accounts.bankruptcy_seps_total),
                "labor_death_seps_total": float(accounts.death_seps_total),
                "labor_recalls_total": float(accounts.recalls_total),
                "labor_suspensions_total": float(accounts.suspensions_total),
                "labor_susp_timeouts_total": float(accounts.suspension_timeouts_total),
                "labor_susp_poached_total": float(accounts.suspension_poached_total),
                "labor_ladder_moves_total": float(accounts.ladder_moves_total),
                "labor_welfare_quits_total": float(accounts.welfare_quits_total),
                "labor_nonsearching_memo": float(accounts.nonsearching_memo),
                "labor_incumbent_wage_mean": (
                    (lambda jobs: sum(j.wage for j in jobs) / len(jobs) if jobs else 0.0)(
                        [j for j in getattr(getattr(econ, "labor_market", None), "jobs", {}).values()
                         if j.wage > 0.0]
                    ) if getattr(econ, "labor_market", None) is not None else 0.0
                ),
                "labor_vacancy_age_mean": (
                    float(sum(getattr(econ.labor_market, "vacancy_age", {}).values()))
                    / max(1, len(getattr(econ.labor_market, "vacancy_age", {}) or {1: 0}))
                    if getattr(econ, "labor_market", None) is not None else 0.0
                ),
            }
        )
        lm = getattr(econ, "labor_market", None)
        if lm is not None and getattr(lm, "person_efficiency", False):
            # v16-L4 decomposition gauges: earnings dispersion splits into the FIRM
            # component (log base wage) and the PERSON component (log e_i) -- under
            # independence var(log earn) ~ var(log w) + var(log e)
            active = [(j, lm.efficiency.get(pid, 1.0))
                      for pid, j in lm.jobs.items() if pid not in lm.suspended]
            es = np.array([e for _, e in active]) if active else np.array([1.0])
            ws = np.array([max(j.wage, 1e-12) for j, _ in active]) if active else np.array([1.0])
            rec.update(
                {
                    "labor_eff_employed_mean": float(np.mean(es)),
                    "labor_earn_var_logw": float(np.var(np.log(ws))),
                    "labor_earn_var_loge": float(np.var(np.log(es))),
                }
            )

    housing = getattr(econ, "housing", None)
    if housing is not None:
        # v15.0: registry stock gauges (frozen price until the v15.1 market)
        fiscal = getattr(econ, "_fiscal", None)
        owner_households = sum(1 for h in live_households if housing.dwellings_of(h.id))
        rec.update(
            {
                "dwellings_total": float(housing.count()),
                "dwellings_fiscal": float(len(housing.dwellings_of(fiscal)) if fiscal else 0.0),
                "homeowner_share": owner_households / max(1, n_live),
                "house_price": float(getattr(econ, "_house_price", 0.0)),
            }
        )
        market = getattr(econ, "housing_market", None)
        if market is not None:
            rec.update(
                {
                    "housing_listings": float(len(market.listings)),
                    "housing_sales_session": float(market.last_session_sales),
                    "housing_sales_total": float(market.sales_total),
                    "housing_tom": float(market.last_session_tom),
                    "housing_forced_share": float(market.forced_share),
                    "transfer_tax_paid": float(getattr(econ, "_transfer_tax_paid", 0.0)),
                    "property_tax_paid": float(getattr(econ, "_property_tax_paid", 0.0)),
                }
            )
        mortgage_book = getattr(econ, "mortgage_book", None)
        if mortgage_book is not None:
            rec.update(
                {
                    "mortgage_count": float(len(mortgage_book.loans)),
                    "mortgage_balance_total": float(mortgage_book.balance_total()),
                    "mortgage_originated_tick": float(mortgage_book.originated_tick),
                    "mortgage_originated_total": float(mortgage_book.originated_total),
                    "foreclosures_total": float(mortgage_book.foreclosures_total),
                }
            )
        afford = getattr(econ, "housing_affordability", None)
        if afford is not None:
            rec.update(
                {
                    "housing_pti_ratio": float(afford.pti_ratio),
                    "rent_burden_ratio": float(afford.rent_burden_ratio),
                    "leave_home_mult": float(afford.leave_mult),
                    "housing_fertility_mult": float(afford.fertility_mult),
                }
            )
        builders = getattr(econ, "builders", None)
        if builders:
            rec.update(
                {
                    "dwellings_built_total": float(getattr(econ, "_dwellings_built", 0)),
                    "land_fee_paid_total": float(getattr(econ, "_land_fee_paid", 0.0)),
                    "builder_employment": float(sum(f.hired for f in builders)),
                    "builder_inventory_units": float(sum(f.inventory for f in builders)),
                    "builder_wip_units": float(sum(getattr(f, "wip", 0.0) for f in builders)),
                    "permits_used_year": float(getattr(econ, "_permits_used", 0)),
                }
            )
        rental = getattr(econ, "rental_market", None)
        if rental is not None:
            price = max(1e-9, float(getattr(econ, "_house_price", 0.0)))
            rec.update(
                {
                    "tenancy_count": float(len(rental.tenancies)),
                    "rental_vacancies": float(len(rental.vacancies(econ))),
                    "rent_level": float(rental.rent_level),
                    "rental_yield": float(rental.rent_level * 365.0 / price),
                    **({
                        "housing_safe_asset_return_annual": float(
                            getattr(econ, "_housing_safe_asset_return_annual", 0.0)
                        ),
                    } if getattr(econ.cfg, "monetary_direct_transmission", False) else {}),
                    "rent_paid_total": float(rental.rent_paid_total),
                    "evictions_total": float(rental.evictions_total),
                    "tenant_share": float(len(rental.tenancies)) / max(1, n_live),
                    "landlord_count": float(sum(
                        1 for h in live_households if len(housing.dwellings_of(h.id)) > 1
                    )),
                }
            )

    # -- observable-but-not-yet-mechanistic metrics -----------------------
    # These are read-only aggregates over fields the model already maintains.
    # They support the visualization refactor without adding any behavioral
    # channel.
    production_target_c = float(np.sum([f.production_target for f in cfirms]))
    target_inventory_c = float(np.sum([f.target_inventory for f in cfirms]))
    demand_expected_c = float(np.sum([f.demand_expected for f in cfirms]))
    inventory_gap = float(np.sum([f.inventory - f.target_inventory for f in cfirms]))
    active_producers = float(np.sum(np.asarray(produced_all) > 1e-9))
    active_sellers = float(np.sum(np.asarray(sales_all) > 1e-9))
    labor_notional = float(np.sum([f.labor_demand_notional for f in firms]))
    labor_gap = max(0.0, labor_notional - total_labor_demand)
    labor_rationed = [f for f in firms if f.labor_demand_eff - f.hired > 1e-9]
    cash_constrained = [f for f in firms if f.labor_demand_notional - f.labor_demand_eff > 1e-9]
    c_hired = float(np.sum([f.hired for f in cfirms]))
    k_hired = float(np.sum([f.hired for f in kfirms]))
    c_labor_demand = float(np.sum([f.labor_demand_eff for f in cfirms]))
    k_labor_demand = float(np.sum([f.labor_demand_eff for f in kfirms]))
    c_capital_stock = float(np.sum([f.capital for f in cfirms]))
    investing = list(getattr(econ, "investing_firms", []))
    investment_target = float(np.sum([f.investment_target for f in investing]))
    private_depreciation = float(np.sum([f.delta_K * f.capital for f in investing]))
    unit_labor_costs = [f.wagebill / f.produced for f in firms if f.produced > 1e-9]
    min_wage = float(getattr(econ.policy, "min_wage", 0.0))
    jg_wage_ratio = float(getattr(econ.policy, "jg_wage_ratio", 0.0))
    real_c_active = float(np.sum([f.produced for f in cfirms if f.produced > 1e-9]))
    sales_c_active = float(np.sum([f.sales for f in cfirms if f.sales > 1e-9]))
    active_c_producers = float(np.sum([1 for f in cfirms if f.produced > 1e-9]))
    active_c_sellers = float(np.sum([1 for f in cfirms if f.sales > 1e-9]))

    rec.update({
        "genesis_money": float(led.genesis_money),
        "total_reserves": float(getattr(led, "total_reserves", 0.0)),
        "reserve_conservation_drift": abs(float(getattr(led, "total_reserves", 0.0))
                                          - float(getattr(led, "_reserve_M", 0.0))),
        "price_p10": _quantile(prices, 0.10),
        "price_p50": _quantile(prices, 0.50),
        "price_p90": _quantile(prices, 0.90),
        "price_p90_p10_ratio": _safe_ratio(_quantile(prices, 0.90), _quantile(prices, 0.10)),
        "markup_cv": cv(markups),
        "markup_p10": _quantile(markups, 0.10),
        "markup_p50": _quantile(markups, 0.50),
        "markup_p90": _quantile(markups, 0.90),
        "wage_cv": cv(wages),
        "wage_p10": _quantile(wages, 0.10),
        "wage_p50": _quantile(wages, 0.50),
        "wage_p90": _quantile(wages, 0.90),
        "wage_p90_p10_ratio": _safe_ratio(_quantile(wages, 0.90), _quantile(wages, 0.10)),
        "sector_avg_wage_C": _mean([f.wage for f in cfirms if f.hired > 1e-9] or [f.wage for f in cfirms]),
        "sector_avg_wage_K": _mean([f.wage for f in kfirms if f.hired > 1e-9] or [f.wage for f in kfirms]),
        "sector_wage_gap_C_vs_K": (_mean([f.wage for f in cfirms if f.hired > 1e-9] or [f.wage for f in cfirms])
                                   - _mean([f.wage for f in kfirms if f.hired > 1e-9] or [f.wage for f in kfirms])),
        "unit_labor_cost_mean": _mean(unit_labor_costs),
        "unit_labor_cost_cv": cv(unit_labor_costs),
        "production_target_total": production_target_c,
        "production_realization_rate": _safe_ratio(total_produced, production_target_c),
        "demand_expected_total": demand_expected_c,
        "target_inventory_total": target_inventory_c,
        "inventory_gap_total": inventory_gap,
        "inventory_gap_ratio": _safe_ratio(inventory_gap, target_inventory_c),
        "inventory_to_sales": _safe_ratio(float(np.sum(inventory_c)), total_sales_u),
        "capital_productivity": _safe_ratio(total_produced, c_capital_stock),
        "active_producer_share": _safe_ratio(active_producers, float(len(firms))),
        "active_seller_share": _safe_ratio(active_sellers, float(len(firms))),
        "real_output_per_active_firm": _safe_ratio(real_c_active, active_c_producers),
        "real_sales_per_active_firm": _safe_ratio(sales_c_active, active_c_sellers),
        "capital_deepening": _safe_ratio(c_capital_stock, total_hired),
        "firm_revenue_gini": gini(revenue_c),
        "firm_profit_gini": gini([max(0.0, f.profit) for f in cfirms]),
        "market_share_hhi_sales": _hhi(revenue_c),
        "market_share_hhi_output": _hhi(produced_c),
        "top_firm_sales_share": top_share(revenue_c, 1.0 / max(1, len(cfirms))),
        "top_firm_output_share": top_share(produced_c, 1.0 / max(1, len(cfirms))),
        "sector_count_C": float(len(cfirms)),
        "sector_count_K": float(len(kfirms)),
        "profit_rate_mean": _mean([
            f.profit / max(1e-9, firm_return_asset_base(econ, f))
            for f in cfirms
        ]),
        "profit_rate_dispersion": _std([
            f.profit / max(1e-9, firm_return_asset_base(econ, f))
            for f in cfirms
        ]),
        "investment_target_units": investment_target,
        "investment_realization_rate": _safe_ratio(float(np.sum([f.investment for f in investing])), investment_target),
        "private_capital_depreciation": private_depreciation,
        "net_private_capital_formation": float(np.sum([f.investment for f in investing])) - private_depreciation,
        "labor_demand_notional": labor_notional,
        "cash_labor_demand_gap": labor_gap,
        "cash_labor_constraint_rate": _safe_ratio(labor_gap, labor_notional),
        "cash_constrained_firm_share": _safe_ratio(float(len(cash_constrained)), float(len(firms))),
        "labor_rationed_firm_share": _safe_ratio(float(len(labor_rationed)), float(len(firms))),
        "labor_sold_gini": gini([h.labor_sold for h in live_households]),
        "full_unemployed_share": float(np.mean([(h.labor_sold + h.jg_labor) <= 1e-9 for h in live_households]))
        if live_households else 0.0,
        "underemployed_share": float(np.mean([(h.labor_sold + h.jg_labor) < 1.0 - 1e-9 for h in live_households]))
        if live_households else 0.0,
        "employment_C": c_hired,
        "employment_K": k_hired,
        "labor_demand_C": c_labor_demand,
        "labor_demand_K": k_labor_demand,
        "min_wage": min_wage,
        "job_guarantee_wage": jg_wage_ratio * _mean(wages),
        "min_wage_binding_firm_share": (
            float(np.mean([f.wage <= min_wage + 1e-9 for f in firms])) if min_wage > 0.0 and firms else 0.0
        ),
    })

    if getattr(econ.cfg, "priced_firm_balance_sheet", False):
        firm_sheets = [firm_balance_sheet(econ, firm) for firm in firms]
        rec.update({
            "priced_firm_balance_sheet_enabled": 1.0,
            "firm_replacement_cost_capital_value": float(np.sum([
                sheet.capital_value for sheet in firm_sheets
            ])),
            "firm_priced_inventory_value": float(np.sum([
                sheet.inventory_value for sheet in firm_sheets
            ])),
            "firm_gross_assets_priced": float(np.sum([
                sheet.gross_assets for sheet in firm_sheets
            ])),
            "firm_book_equity_priced": float(np.sum([
                sheet.book_equity for sheet in firm_sheets
            ])),
            "firm_eligible_collateral_value": float(np.sum([
                sheet.eligible_collateral_value for sheet in firm_sheets
            ])),
            "firm_borrowing_base_proxy": float(np.sum([
                sheet.borrowing_base_proxy for sheet in firm_sheets
            ])),
            "firm_borrowing_base_headroom": float(np.sum([
                sheet.borrowing_base_headroom for sheet in firm_sheets
            ])),
        })

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
        household_debt = [led.debt(h.id) for h in households]
        total_household_debt = float(np.sum(household_debt))
        new_firm_loans = float(getattr(econ, "_new_loans", 0.0))
        mortgage_originated = float(
            getattr(getattr(econ, "mortgage_book", None), "originated_tick", 0.0)
        )
        new_household_loans = (
            float(getattr(econ, "_hh_credit_new", 0.0))
            + float(getattr(econ, "_hh_margin_new", 0.0))
            + mortgage_originated
        )
        total_interest = float(getattr(econ, "_interest_paid", 0.0)) + float(getattr(econ, "_hh_interest", 0.0))
        total_principal = (
            float(getattr(econ, "_principal_repaid", 0.0))
            + float(getattr(econ, "_hh_principal", 0.0))
            + float(getattr(econ, "_hh_margin_repaid", 0.0))
        )
        rec.update({
            "broad_money": total_money,                 # ΣD -- the headline: must be ALIVE
            "total_credit": total_credit,               # ΣL
            "net_worth": float(led.net_worth),          # ΣD − ΣL, must = M (A5 check)
            "bank_money": float(led.balance(econ.bank.id)),   # retained interest (small new sink)
            "credit_to_M": total_credit / led.genesis_money,
            "aggregate_leverage": (total_credit / total_firm_nw) if total_firm_nw > 1e-9 else 0.0,
            "n_firms_borrowing": float(np.sum(np.asarray(firm_debt) > 1e-9)),
            "new_loans": new_firm_loans,
            "new_loans_total": new_firm_loans + new_household_loans,
            "credit_wage": float(getattr(econ, "_credit_wage", 0.0)),
            "credit_investment": float(getattr(econ, "_credit_investment", 0.0)),
            "interest_paid": float(getattr(econ, "_interest_paid", 0.0)),
            "principal_repaid": float(getattr(econ, "_principal_repaid", 0.0)),
            "firm_debt_total": float(np.sum(firm_debt)),
            "firm_debt_gini": gini(firm_debt),
            "firm_debt_top10_share": top_share(firm_debt, 0.10),
            "household_debt_total_observed": total_household_debt,
            "firm_credit_share": _safe_ratio(float(np.sum(firm_debt)), total_credit),
            "household_credit_share": _safe_ratio(total_household_debt, total_credit),
            "credit_wage_share": _safe_ratio(float(getattr(econ, "_credit_wage", 0.0)), new_firm_loans),
            "credit_investment_share": _safe_ratio(float(getattr(econ, "_credit_investment", 0.0)), new_firm_loans),
            "total_interest_paid": total_interest,
            "total_principal_repaid": total_principal,
            "bank_loan_interest_income": float(np.sum([b.loan_interest for b in econ.banks])),
            "bank_bond_coupon_income": float(np.sum([b.bond_coupon for b in econ.banks])),
            "bank_interbank_interest_income": float(
                np.sum([b.interbank_interest_income for b in econ.banks])
            ),
            "bank_interbank_interest_expense": float(
                np.sum([b.interbank_interest_expense for b in econ.banks])
            ),
            "bank_external_interest_expense": float(
                np.sum([b.external_interest_expense for b in econ.banks])
            ),
            # v23: the bank's cost of funds on DEPOSITS (the missing P&L leg the deposit-rate fix
            # added). Reduces realized profit before dividends; surfaced so the spread is visible.
            "bank_deposit_funding_cost": float(
                np.sum([getattr(b, "deposit_funding_cost", 0.0) for b in econ.banks])
            ),
            "bank_realized_credit_losses": float(
                np.sum([b.realized_credit_losses for b in econ.banks])
            ),
            "bank_realized_profit": float(np.sum([b.profit for b in econ.banks])),
            "bank_dividends_paid": float(np.sum([b.dividends_paid for b in econ.banks])),
        })
        if getattr(econ.cfg, "monetary_direct_transmission", False):
            rec.update({
                "household_debt_service_reserved": float(
                    getattr(econ, "_hh_debt_service_reserved", 0.0)
                ),
                "firm_credit_dscr_allowed": float(
                    getattr(econ, "_firm_credit_dscr_allowed", 0.0)
                ),
                "firm_credit_dscr_shortfall": float(
                    getattr(econ, "_firm_credit_dscr_shortfall", 0.0)
                ),
                "firm_credit_dscr_constrained": float(
                    getattr(econ, "_firm_credit_dscr_constrained", 0.0)
                ),
            })
        if getattr(econ.cfg, "household_interest_arrears", False):
            opening = accrued = due = cash = extinguished = 0.0
            closing = float(np.sum([
                max(0.0, float(h.credit_interest_arrears)) for h in households
            ]))
            for household in households:
                if household.credit_interest_journal_tick == econ.t:
                    opening += max(0.0, float(household.credit_interest_arrears_opening))
                    accrued += max(0.0, float(household.credit_interest_accrued))
                    due += max(0.0, float(household.credit_interest_due))
                    cash += max(0.0, float(household.credit_interest_cash_paid))
                    extinguished += max(
                        0.0,
                        float(household.credit_interest_arrears_extinguished),
                    )
                else:
                    # A mid-phase diagnostic snapshot still has a valid bridge:
                    # no current flows means the persistent stock opens unchanged.
                    opening += max(0.0, float(household.credit_interest_arrears))
            rec.update({
                "household_interest_arrears_opening": opening,
                "household_interest_accrued": accrued,
                "household_interest_due": due,
                "household_interest_cash_paid": cash,
                "household_interest_arrears_closing": closing,
                "household_interest_arrears_extinguished": extinguished,
                "household_interest_arrears_stock_flow_residual": (
                    opening + accrued - cash - extinguished - closing
                ),
                "household_interest_cash_counter_residual": (
                    cash - float(getattr(econ, "_hh_interest", 0.0))
                ),
                "household_contractual_debt_service_due": float(
                    getattr(econ, "_hh_contractual_debt_service_due", 0.0)
                ),
                "household_interest_arrears_in_goods_reservation": float(
                    getattr(econ, "_hh_interest_arrears_in_goods_reservation", 0.0)
                ),
                "household_debt_service_reserved": float(
                    getattr(econ, "_hh_debt_service_reserved", 0.0)
                ),
            })
        if getattr(econ.cfg, "priced_firm_balance_sheet", False):
            rec.update({
                "firm_credit_borrowing_base_proxy": float(
                    getattr(econ, "_firm_credit_borrowing_base_proxy", 0.0)
                ),
                "firm_credit_borrowing_base_headroom": float(
                    getattr(econ, "_firm_credit_borrowing_base_headroom", 0.0)
                ),
                "firm_credit_borrowing_base_shortfall": float(
                    getattr(econ, "_firm_credit_borrowing_base_shortfall", 0.0)
                ),
                "firm_credit_borrowing_base_constrained": float(
                    getattr(econ, "_firm_credit_borrowing_base_constrained", 0.0)
                ),
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
        live_wealth = [w for w, alive in zip(hh_wealth, live_mask) if alive]
        rec.update({
            "stock_price": float(mkt.price),
            "market_cap": float(market_cap),
            "book_value": float(mkt.book_value),
            "fundamental_ps": float(mkt.fundamental),
            "bubble_gap": float(market_cap - mkt.book_value),      # valuation phantom (not money)
            "tobin_q": float(market_cap / mkt.book_value) if abs(mkt.book_value) > 1e-9 else 0.0,
            "equity_trend": float(mkt.trend),
            "equity_turnover": float(getattr(econ, "_equity_turnover", 0.0)),
            "hh_wealth_gini_incl_equity": gini(live_wealth),       # 乙: the T8-relevant measure
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
        live_eq_val = [v for v, alive in zip(eq_val, live_mask) if alive]
        live_wealth = [w for w, alive in zip(hh_wealth, live_mask) if alive]
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
            "equity_ownership_gini": gini(live_eq_val),      # who owns equity (founder concentration)
            "hh_wealth_gini_incl_equity": gini(live_wealth), # T8 with per-firm equity (choice 乙)
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
        live_nw = nw[live_mask]                                       # shape stats over living households only
        hh_debt_total = float(np.sum(debts))
        cons = total_revenue                                          # consumption this tick
        rec.update({
            "household_debt_total": hh_debt_total,
            "household_credit_new": float(getattr(econ, "_hh_credit_new", 0.0)),
            "hh_interest_paid": float(getattr(econ, "_hh_interest", 0.0)),
            "household_leverage": hh_debt_total / max(1e-9, income_realized),  # debt / income
            "share_underwater": float(np.mean(live_nw < 0.0)) if live_nw.size else 0.0,  # fraction with D<L (net debtor)
            # net worth has negatives (borrowers) -> Gini on the min-shifted series (valid [0,1]).
            "hh_networth_gini": gini(list(np.maximum(live_nw, 0.0))),   # clip, not min-shift: one deep debtor made the shifted gini gyrate
            "hh_networth_min": float(live_nw.min()) if live_nw.size else 0.0,
            "hh_networth_median": float(np.median(live_nw)) if live_nw.size else 0.0,
            "consumption_credit_share": float(getattr(econ, "_hh_credit_new", 0.0)) / max(1e-9, cons),
        })

    # Shared per-household bank-equity values (read-only state; identical for every block below).
    bankeq_list = (
        [bank_equity_value(econ, h.id) for h in households]
        if getattr(econ.cfg, "bank_equity", False) else None
    )

    # ----------------------------------------------------------------------
    # v8 block (DESIGNDOC §21). Household margin credit. Appended when margin_credit on.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "margin_credit", False):
        price_of = {f.id: f.share_price for f in cfirms}
        eqv = np.asarray([float(np.sum([sh * price_of.get(fid, 0.0) for fid, sh in h.holdings.items()]))
                          for h in households])
        debt_arr = np.asarray([led.debt(h.id) for h in households])
        margin = np.asarray([h.margin_debt for h in households])
        bankeq = np.asarray(bankeq_list) if bankeq_list is not None else 0.0   # v11.5: bank-equity wealth
        nw_full = np.asarray(hh_dep) + eqv + bankeq - debt_arr  # TRUE net worth: cash + equity (firm+bank) − debt
        live_nw_full = nw_full[live_mask]                      # T8 concentration over living households only
        _nw_shift = list(live_nw_full - live_nw_full.min()) if live_nw_full.size else []
        rec.update({
            "household_margin_debt": float(np.sum(margin)),
            "avg_household_leverage": float(np.sum(eqv) / max(1e-9, np.sum(nw_full))),  # equity / net worth
            "margin_deleveraged": float(getattr(econ, "_hh_margin_repaid", 0.0)),       # fire-sale repay
            "margin_credit_new": float(getattr(econ, "_hh_margin_new", 0.0)),
            # T8 with leverage: is wealth (cash+equity−debt) concentrating in a few?
            "hh_full_networth_gini": gini(_nw_shift),
            "hh_full_networth_top10": top_share(_nw_shift, 0.10),
            "share_margin_underwater": float(np.mean(live_nw_full < 0.0)) if live_nw_full.size else 0.0,
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
        # v19: the technology index Z(t) per sector (1.0 while inert) + its annualised growth.
        "tfp_index_c": float(econ.technology.factor("c")) if hasattr(econ, "technology") else 1.0,
        "tfp_index_k": float(econ.technology.factor("k")) if hasattr(econ, "technology") else 1.0,
        "tfp_index_e": float(econ.technology.factor("e")) if hasattr(econ, "technology") else 1.0,
        "savings_rate": ((income_realized - effective_cons) / income_realized) if income_realized > 1e-9 else 0.0,
        "money_velocity": (nominal_output / total_money) if total_money > 1e-9 else 0.0,
        "credit_to_gdp": (rec.get("total_credit", 0.0) / nominal_output) if nominal_output > 1e-9 else 0.0,
        "debt_service_ratio": ((rec.get("interest_paid", 0.0) + rec.get("principal_repaid", 0.0))
                               / nominal_output) if nominal_output > 1e-9 else 0.0,
        "total_debt_service_ratio": ((rec.get("total_interest_paid", rec.get("interest_paid", 0.0))
                                      + rec.get("total_principal_repaid", rec.get("principal_repaid", 0.0)))
                                     / nominal_output) if nominal_output > 1e-9 else 0.0,
        "income_gini": gini([h.income_realized for h in live_households]),     # income inequality
        "consumption_gini": gini([h.spent for h in live_households]),          # consumption inequality
    })
    # -- distributional / bottom-tail WELFARE (§8.3): what aggregates & Gini miss -- pure observation.
    #    Consumption is the welfare basis; LEVEL measures are REAL (÷ price_index), ratios stay nominal
    #    (scale-invariant). Relative poverty line = 50% of median consumption (adapts to inflation/growth).
    #    Welfare is a per-LIVING-household statistic: a demographically dissolved shell consumes a
    #    permanent zero, which would masquerade as destitution (poverty_gap pinned at 1.0, bottom
    #    deciles at 0) and swamp every headcount. Sums are shell-invariant (shells spend 0) so the
    #    aggregate real_household_consumption is unchanged whether it scans live or all.
    cons = np.asarray([h.spent for h in live_households], float)
    inc = np.asarray([h.income_realized for h in live_households], float)
    defl = price_index if price_index > 1e-12 else 1.0
    real_c = cons / defl
    med_c, med_i = float(np.median(cons)) if cons.size else 0.0, float(np.median(inc)) if inc.size else 0.0
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
    bottom25_n = max(1, int(np.ceil(0.25 * len(real_c)))) if len(real_c) else 1
    subsistence_gap = np.maximum(0.0, subsist - cons) if subsist > 0.0 else np.zeros_like(cons)

    # Household balance-sheet observables. These reuse live deposits, ledger debt,
    # equity holdings, bank-equity ownership, and bond lots; no portfolio behavior
    # is changed by reporting them.
    hh_debt = np.asarray([led.debt(h.id) for h in households], dtype=float)
    firm_equity_values = np.zeros(n_h, dtype=float)
    if getattr(econ, "equity", None) is not None:
        firm_equity_values = np.asarray([h.shares * econ.equity.price for h in households], dtype=float)
    elif getattr(econ.cfg, "per_firm_equity", False):
        share_price_of = {f.id: f.share_price for f in cfirms}
        firm_equity_values = np.asarray([
            float(sum(sh * share_price_of.get(fid, 0.0) for fid, sh in h.holdings.items()))
            for h in households
        ], dtype=float)
    bank_equity_values = (
        np.asarray(bankeq_list, dtype=float) if bankeq_list is not None else np.zeros(n_h, dtype=float)
    )
    # One pass over the lots, grouped by holder, then sum() per holder over its own values in lot
    # order -- the SAME builtin over the SAME sequence as the per-account scan it replaces
    # (formerly O(N_h x N_lots)). Do NOT fold into a running scalar: float sum() is compensated
    # (Neumaier) since Python 3.12, so naive accumulation differs in the last bit.
    bond_mv_by_holder: Dict = {}
    for lot in getattr(econ, "_bonds", []) or []:
        bond_mv_by_holder.setdefault(lot.get("holder"), []).append(bond_market_value(econ, lot))
    bond_market_values = np.asarray(
        [float(sum(bond_mv_by_holder.get(h.id, ()))) for h in households], dtype=float
    )
    full_networth = np.asarray(hh_dep, dtype=float) + firm_equity_values + bank_equity_values + bond_market_values - hh_debt
    gross_assets = np.asarray(hh_dep, dtype=float) + firm_equity_values + bank_equity_values + bond_market_values
    # live-only views for the count / quantile / gini / share statistics (shells contribute a
    # frozen zero that distorts every distributional shape); the explicit *_total / gross_* SUMS
    # below stay on the full arrays so residual shell stocks remain visible in aggregates.
    live_dep_arr = np.asarray(hh_dep, dtype=float)[live_mask]
    live_debt = hh_debt[live_mask]
    live_firm_eq = firm_equity_values[live_mask]
    live_bank_eq = bank_equity_values[live_mask]
    live_bond_mv = bond_market_values[live_mask]
    live_networth = full_networth[live_mask]
    live_networth_shifted = live_networth - float(live_networth.min()) if live_networth.size else live_networth
    rec.update({
        "mean_real_consumption_per_household": float(real_c.mean()) if real_c.size else 0.0,
        "median_real_consumption": float(np.median(real_c)) if real_c.size else 0.0,
        "bottom25_consumption": float(np.sort(real_c)[:bottom25_n].mean()) if real_c.size else 0.0,
        "subsistence_gap_ratio": _safe_ratio(float(subsistence_gap.sum()), subsist * n_live),
        "median_real_household_income": float(np.median(inc / defl)) if inc.size else 0.0,
        "consumption_realization_rate": _safe_ratio(effective_cons, desired_cons),
        "real_household_consumption": float(real_c.sum()),
        "hh_deposit_p10": _quantile(list(live_dep_arr), 0.10),
        "hh_deposit_median": _quantile(list(live_dep_arr), 0.50),
        "hh_deposit_p90": _quantile(list(live_dep_arr), 0.90),
        "household_debt_gini": gini(live_debt),
        "household_debt_top10_share": top_share(live_debt, 0.10),
        "equity_wealth_top10_share": top_share(live_firm_eq, 0.10),
        "bank_equity_top10_share": top_share(live_bank_eq, 0.10),
        "bond_wealth_gini": gini(live_bond_mv),
        "bond_wealth_top10_share": top_share(live_bond_mv, 0.10),
        "bond_wealth_share": _safe_ratio(float(bond_market_values.sum()), float(gross_assets.sum())),
        "hh_full_networth_total": float(full_networth.sum()) if full_networth.size else 0.0,
        "hh_full_networth_skew": _skew(live_networth),
        "hh_full_networth_excess_kurtosis": _excess_kurtosis(live_networth),
        "gross_household_assets_total": float(gross_assets.sum()) if gross_assets.size else 0.0,
        "household_underwater_share": float(np.mean(live_networth < 0.0)) if live_networth.size else 0.0,
        "full_networth_p10": _quantile(list(live_networth), 0.10),
        "full_networth_p50": _quantile(list(live_networth), 0.50),
        "full_networth_p90": _quantile(list(live_networth), 0.90),
        "hh_full_networth_gini_observed": gini(live_networth_shifted),
    })
    # v9 government (§28): fiscal flows + NORMALISED balances (raw stocks are unreadable). deficit>0 =
    # net injection (spend>tax); expressed as a share of revenue AND of GDP. gov_debt = −GOV balance.
    if getattr(econ.cfg, "government", False):
        tax_profit = float(getattr(econ, "_tax_profit", 0.0))
        tax_income = float(getattr(econ, "_tax_income", 0.0))
        tax_consumption = float(getattr(econ, "_tax_consumption", 0.0))
        tax_wealth = float(getattr(econ, "_tax_wealth", 0.0))
        tax_energy = float(getattr(econ, "_tax_energy", 0.0))
        tax_energy_windfall = float(getattr(econ, "_tax_energy_windfall", 0.0))
        tax_property = float(getattr(econ, "_property_tax_paid", 0.0))
        tax_transfer = float(getattr(econ, "_transfer_tax_paid", 0.0))
        tax_tariff = float(getattr(econ, "_tariff_revenue_external", 0.0))
        tax_remittance = float(
            getattr(econ, "_remittance_tax_revenue_external", 0.0)
        )
        tax_outward_remittance = float(
            getattr(econ, "_outward_remittance_tax_revenue", 0.0)
        )
        export_policy_flow = float(
            getattr(econ, "_export_subsidy_cost_external", 0.0)
        )
        tax_export = max(0.0, -export_policy_flow)
        tax_total = (
            tax_profit
            + tax_income
            + tax_consumption
            + tax_wealth
            + tax_energy
            + tax_energy_windfall
            + tax_property
            + tax_transfer
            + tax_tariff
            + tax_remittance
            + tax_outward_remittance
            + tax_export
        )
        soe_dividends = float(getattr(econ, "_soe_dividends", 0.0))
        fiscal_land_fee_revenue = float(
            getattr(econ, "_land_fee_paid_tick", 0.0)
        )
        fiscal_escheat_revenue = float(getattr(econ, "_escheat_flow", 0.0))
        fiscal_spr_sale_revenue = float(
            getattr(econ, "_spr_sale_revenue", 0.0)
        )
        fiscal_non_tax_revenue = (
            soe_dividends
            + fiscal_land_fee_revenue
            + fiscal_escheat_revenue
            + fiscal_spr_sale_revenue
        )
        fiscal_revenue_total = tax_total + fiscal_non_tax_revenue
        benefit_paid = float(getattr(econ, "_benefit_paid", 0.0))
        gov_consumption = float(getattr(econ, "_gov_consumption", 0.0))
        jg_spending = float(getattr(econ, "_jg_spending", 0.0))    # v9.3 job-guarantee wage bill
        public_investment = float(getattr(econ, "_public_investment", 0.0))
        gov_interest_bill = float(getattr(econ, "_gov_interest_bill", 0.0))
        energy_subsidy = float(getattr(econ, "_energy_subsidy_paid", 0.0))
        energy_cap_compensation = float(getattr(econ, "_energy_cap_comp", 0.0))
        export_subsidy = max(0.0, export_policy_flow)
        external_interest = float(getattr(econ, "_external_interest_fiscal", 0.0))
        bank_resolution_fund_paid = float(
            getattr(econ, "_bank_resolution_fund_paid", 0.0)
        )
        fiscal_spr_purchase_paid = float(
            getattr(econ, "_spr_purchase_paid", 0.0)
        )
        spend_total = benefit_paid + gov_consumption + jg_spending
        augmented_spending = (
            spend_total
            + public_investment
            + gov_interest_bill
            + energy_subsidy
            + energy_cap_compensation
            + export_subsidy
            + external_interest
            + bank_resolution_fund_paid
            + fiscal_spr_purchase_paid
        )
        deficit = spend_total - fiscal_revenue_total               # >0 = deficit (net outside-money injection)
        cash_deficit = augmented_spending - fiscal_revenue_total
        fiscal_opening = float(getattr(
            econ,
            "_fiscal_opening_balance",
            econ.ledger.balance(econ._fiscal),
        ))
        treasury_account_net_outflow = fiscal_opening - econ.ledger.balance(econ._fiscal)
        treasury_implied_financing_and_unclassified_inflow = (
            cash_deficit - treasury_account_net_outflow
        )
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
            "tax_energy": tax_energy,
            "tax_energy_windfall": tax_energy_windfall,
            "tax_property": tax_property,
            "tax_transfer": tax_transfer,
            "tax_tariff": tax_tariff,
            "tax_remittance": tax_remittance,
            "tax_outward_remittance": tax_outward_remittance,
            "tax_export": tax_export,
            "tax_total": tax_total,
            "fiscal_soe_dividends": soe_dividends,
            "fiscal_land_fee_revenue": fiscal_land_fee_revenue,
            "fiscal_escheat_revenue": fiscal_escheat_revenue,
            "fiscal_spr_sale_revenue": fiscal_spr_sale_revenue,
            "fiscal_non_tax_revenue": fiscal_non_tax_revenue,
            "fiscal_revenue_total": fiscal_revenue_total,
            "benefit_paid": benefit_paid, "gov_consumption": gov_consumption,
            "jg_spending": jg_spending, "jg_employment": jg_emp, "jg_employment_rate": jg_emp_rate,
            "effective_unemployment": max(0.0, rec["unemployment_rate"] - jg_emp_rate),
            "gov_spending": spend_total, "gov_deficit": deficit, "gov_debt": gov_debt,
            "fiscal_uses_national_accounts_gdp": float(
                bool(getattr(econ.cfg, "fiscal_uses_national_accounts_gdp", False))
            ),
            "fiscal_output_lag": float(getattr(
                econ,
                "_prev_fiscal_output",
                getattr(econ, "_prev_nominal_output", 0.0),
            )),
            "augmented_gov_spending": augmented_spending,
            "bank_resolution_fund_paid": bank_resolution_fund_paid,
            "fiscal_spr_purchase_paid": fiscal_spr_purchase_paid,
            "cash_deficit": cash_deficit,
            "fiscal_external_interest_paid": external_interest,
            "fiscal_export_subsidy_paid": export_subsidy,
            "treasury_account_net_outflow": treasury_account_net_outflow,
            "treasury_implied_financing_and_unclassified_inflow": (
                treasury_implied_financing_and_unclassified_inflow
            ),
            "gov_deficit_to_revenue": (
                deficit / fiscal_revenue_total
            ) if fiscal_revenue_total > 1e-9 else 0.0,
            "gov_deficit_to_gdp": (deficit / nominal_output) if nominal_output > 1e-9 else 0.0,
            "cash_deficit_to_gdp": (cash_deficit / nominal_output) if nominal_output > 1e-9 else 0.0,
            "gov_debt_to_gdp": (gov_debt / (365.0 * nominal_output)) if nominal_output > 1e-9 else 0.0,  # vs ANNUAL GDP
            "gov_spending_share_of_gdp": (spend_total / nominal_output) if nominal_output > 1e-9 else 0.0,
            "augmented_gov_spending_share_of_gdp": (
                augmented_spending / nominal_output
            ) if nominal_output > 1e-9 else 0.0,
            "hh_bankruptcies": float(getattr(econ, "_hh_bankruptcies", 0.0)),
            "benefit_recipient_share": float(np.mean([
                (h.labor_sold + h.jg_labor) <= 1e-9 for h in live_households
            ])) if live_households and benefit_paid > 0.0 else 0.0,
        })
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
        cb_cfg = econ.cfg.central_banking
        pol = econ.policy
        inflation_gap = infl_ema - pol.inflation_target
        unemployment_gap = rec.get("unemployment_rate", 0.0) - cb_cfg.u_natural
        taylor_target = (
            cb_cfg.r_neutral
            + pol.taylor_phi_pi * inflation_gap
            - pol.taylor_phi_u * unemployment_gap
        )
        # v25 B2(b): the OMO STANCE (on/off + target) is POLICY; the metrics gate must
        # read the same source as behaviour or a runtime policy change desynchronises
        # observation from action (the split-brain defect). bonds/interbank stay cfg:
        # they are structural capabilities, not stances.
        omo_target = (
            float(getattr(econ, "_omo_target_value",
                          pol.omo_reserve_target * float(getattr(econ, "_reserve_M0", 0.0))))
            if pol.omo and cb_cfg.bonds and cb_cfg.interbank else 0.0
        )
        bank_reserves_total = rec.get("bank_reserves_total", 0.0)
        cb_bond_market = float(sum(bond_mv_by_holder.get("CB", ())))
        rec.update({
            "policy_rate": rate,
            "cb_uses_fixed_basket_cpi": float(
                bool(getattr(econ.cfg, "cb_uses_fixed_basket_cpi", False))
            ),
            "cb_inflation_lag_input": float(getattr(econ, "_prev_inflation", 0.0)),
            "inflation_ema": infl_ema,
            "real_rate": rate - infl_ema,        # ex-ante real policy rate (Taylor principle => rises with π)
            "inflation_target": float(pol.inflation_target),
            "inflation_gap_to_target": inflation_gap,
            "u_natural": float(cb_cfg.u_natural),
            "unemployment_gap": unemployment_gap,
            "taylor_rate_target": taylor_target,
            "policy_rate_gap": rate - taylor_target,
            "omo_reserve_target_value": omo_target,
            "reserve_gap": bank_reserves_total - omo_target,
            "cb_balance_sheet_assets": float(getattr(econ, "_cb_claim_on_tsy", 0.0)) + cb_bond_market,
            "cb_balance_sheet_liabilities": rec.get("cb_reserves", 0.0) + float(getattr(econ, "_tga", 0.0)),
        })
        rec["cb_net_position"] = rec["cb_balance_sheet_assets"] - rec["cb_balance_sheet_liabilities"]
    # One pure local pass over the bond lots, shared by every bank-capital snapshot below
    # (else each snapshot re-scanned all lots per bank). None when bonds are off.
    bond_deltas = _bond_deltas_by_holder(econ) if getattr(econ.cfg, "bonds", False) else None
    # Optional common bank-capital envelope.  Report live ledger exposure rather
    # than the intra-credit cache so principal service and write-offs later in the
    # tick are reflected without mutating model state during observation.
    if getattr(econ.cfg, "unified_bank_rwa", False) and getattr(econ, "banks", None):
        alive_banks = [bank for bank in econ.banks if bank.alive]
        exposures = [bank_rwa_exposure(econ, bank, use_cache=False) for bank in alive_banks]
        capitals = [max(0.0, _bank_economic_capital_snapshot(econ, bank, bond_deltas)) for bank in alive_banks]
        ratio = max(1e-12, float(econ.cfg.mortgage_min_capital_ratio))
        limits = [capital / ratio for capital in capitals]
        headrooms = [limit - exposure for limit, exposure in zip(limits, exposures)]
        capital_ratios = [
            capital / exposure if exposure > 1e-12 else float("inf")
            for capital, exposure in zip(capitals, exposures)
        ]
        finite_ratios = [value for value in capital_ratios if math.isfinite(value)]
        rec.update({
            "bank_rwa_total": float(sum(exposures)),
            "bank_rwa_limit_total": float(sum(limits)),
            "bank_rwa_headroom_min": float(min(headrooms)) if headrooms else 0.0,
            "bank_rwa_capital_ratio_min": float(min(finite_ratios)) if finite_ratios else 0.0,
        })
    # v11 multi-bank: capital, leverage, failures, bank-size concentration (only with >1 bank)
    if getattr(econ, "banks", None) and len(econ.banks) > 1:
        caps = [econ.ledger.balance(b.id) for b in econ.banks]
        lb = {b.id: 0.0 for b in econ.banks}
        for a in list(econ.firms) + list(econ.households):
            lb[bank_for(econ, a.id).id] += econ.ledger.debt(a.id)
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
            "bank_capital_min": float(min(caps)) if caps else 0.0,
            "bank_capital_median": float(np.median(caps)) if caps else 0.0,
            "bank_money_total": float(sum(caps)),
            "bank_leverage": float(sum(lb.values()) / tot_cap) if tot_cap > 1e-9 else 0.0,
            "bank_size_gini": float(gini([max(0.0, v) for v in lb.values()])),
            "bank_loanbook_hhi": hhi,
            "bank_rate_spread_sd": float(wvar ** 0.5),
        })
        econ_caps = [_bank_economic_capital_snapshot(econ, b, bond_deltas) for b in econ.banks if b.alive]
        rec.update({
            "bank_economic_capital_total": float(sum(econ_caps)) if econ_caps else 0.0,
            "bank_economic_capital_median": float(np.median(econ_caps)) if econ_caps else 0.0,
            "negative_capital_bank_count": float(sum(1 for c in caps if c < -1e-9)),
            "near_failure_bank_count": float(sum(1 for c in caps if 0.0 <= c < econ.cfg.bank_min_capital)),
        })
        if getattr(econ.cfg, "bank_exposure_limit", 0.0) > 0.0:
            usage = []
            for a in list(econ.firms) + list(econ.households):
                bid = bank_for(econ, a.id).id
                cap = max(1e-9, float(getattr(econ.cfg, "bank_min_capital", 0.0)), led.balance(bid))
                usage.append(led.debt(a.id) / (econ.cfg.bank_exposure_limit * cap))
            rec["large_exposure_usage_max"] = float(max(usage)) if usage else 0.0
        else:
            rec["large_exposure_usage_max"] = 0.0
        # v11.4: the reserve tier + interbank market + deposit-side competition. Reserves conserve as a second
        # layer; the interbank market is LATENT under ample reserves (peak overdraft ≈ 0) but reported honestly.
        if getattr(econ.cfg, "interbank", False):
            dep = {b.id: 0.0 for b in econ.banks}                 # per-bank DEPOSIT base (partitioned)
            for h in econ.households:
                dep[bank_for(econ, h.id).id] += max(0.0, econ.ledger.balance(h.id))
            tot_dep = sum(dep.values())
            dep_hhi = float(sum((v / tot_dep) ** 2 for v in dep.values())) if tot_dep > 1e-9 else 0.0
            peak_od = -min([econ.ledger.reserve_min(b.id) for b in econ.banks] + [0.0])
            bank_reserves = [econ.ledger.reserves(b.id) for b in econ.banks]
            reserve_floor = {
                b.id: econ.cfg.reserve_floor_frac * dep.get(b.id, 0.0)
                for b in econ.banks
            }
            reserve_breaches = [
                econ.ledger.reserves(b.id) < reserve_floor.get(b.id, 0.0) - 1e-9
                for b in econ.banks
            ]
            rec.update({
                "bank_reserves_total": float(sum(econ.ledger.reserves(b.id) for b in econ.banks)),  # BANK-side only
                "bank_reserve_min": float(min(bank_reserves)) if bank_reserves else 0.0,
                "bank_reserve_median": float(np.median(bank_reserves)) if bank_reserves else 0.0,
                "cb_reserves": float(econ.ledger.reserves("CB")),      # govt-debt-driven reserve injection
                "interbank_rate": float(getattr(econ, "_interbank_rate", 0.0)),
                "interbank_volume": float(getattr(econ, "_interbank_volume", 0.0)),
                "interbank_contagion_loss": float(getattr(econ, "_interbank_contagion_loss", 0.0)),
                "peak_intraday_overdraft": float(max(0.0, peak_od)),   # ≈0 (latent gridlock) under ample reserves
                "payments_gridlocked": float(getattr(econ, "_payments_blocked", 0.0)),
                "bank_deposit_hhi": dep_hhi,                           # deposit-market concentration (competition)
                "bank_deposit_total": float(tot_dep),
                "bank_deposit_p90_p10": _quantile(list(dep.values()), 0.90) - _quantile(list(dep.values()), 0.10),
                "reserve_floor_breach_share": float(np.mean(reserve_breaches)) if reserve_breaches else 0.0,
            })
        # v11.5: bank demographics & ownership (entry/exit, bank-equity concentration, runs)
        if getattr(econ.cfg, "bank_equity", False):
            bankeq_h = bankeq_list if bankeq_list is not None \
                else [bank_equity_value(econ, h.id) for h in econ.households]
            live_bankeq_h = [v for v, alive in zip(bankeq_h, live_mask) if alive]
            alive_bk = [b for b in econ.banks if b.alive]
            pp = [b.share_price / b.share_peak for b in alive_bk if b.share_peak > 1e-9]
            rec.update({
                "bank_births": float(getattr(econ, "_bank_births", 0)),
                "bank_deaths": float(getattr(econ, "_bank_deaths", 0)),
                "bank_equity_total": float(sum(bankeq_h)),
                "bank_equity_gini": float(gini([max(0.0, v) for v in live_bankeq_h])),   # bank-OWNERSHIP concentration
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
        # ONE pass computes each lot's market value once (was ~6 full-lot scans per tick, each
        # recomputing bond_market_value). Every list is built in lot order, so each sum below is
        # byte-for-byte the former generator sum over the same order -- bit-identical.
        coupon_bearing = getattr(econ.cfg, "bond_coupon", 0.0) > 0.0
        all_mv: list = []
        hh_mv: list = []
        bank_mv: list = []
        cb_mv: list = []
        dur_mv_num: list = []
        for l in lots:
            mv = bond_market_value(econ, l)
            holder = l["holder"]
            all_mv.append(mv)
            if holder in hh_ids:
                hh_mv.append(mv)
            if holder in bank_ids:
                bank_mv.append(mv)
            if holder == "CB":
                cb_mv.append(mv)
            if coupon_bearing:
                dur_mv_num.append(mv * max(0.0, l["matures_at"] - econ.t))
        market_total = float(sum(all_mv)) if lots else 0.0
        book_total = float(sum(l["cost"] for l in lots)) if lots else 0.0
        bank_bond_face = float(sum(l["face"] for l in lots if l["holder"] in bank_ids)) if lots else 0.0
        hh_bond_face = float(sum(l["face"] for l in lots if l["holder"] in hh_ids)) if lots else 0.0
        cb_bond_face = float(sum(l["face"] for l in lots if l["holder"] == "CB")) if lots else 0.0
        hh_bond_market = float(sum(hh_mv)) if lots else 0.0
        bank_bond_market = float(sum(bank_mv)) if lots else 0.0
        cb_bond_market = float(sum(cb_mv)) if lots else 0.0
        bond_face_total = float(sum(l["face"] for l in lots)) if lots else 0.0
        maturity_weighted = _safe_ratio(
            float(sum(l["face"] * max(0.0, l["matures_at"] - econ.t) for l in lots)),
            bond_face_total,
        )
        duration_weighted = maturity_weighted if not coupon_bearing else _safe_ratio(
            float(sum(dur_mv_num)),
            market_total,
        )
        alive_banks = [b for b in econ.banks if b.alive]
        econ_caps = [_bank_economic_capital_snapshot(econ, b, bond_deltas) for b in alive_banks]
        rec.update({
            "bonds_outstanding": float(getattr(econ, "_bonds_outstanding", 0.0)),   # = Σ face
            # FINDING 4: the LOT COUNT (not face). Daily issuance fragments the book; bounded by
            # bond_maturity_bucket. Watch it stay flat over long horizons instead of O(ticks).
            "n_bond_lots": float(len(lots)),
            "bond_book_total": book_total,
            "bond_market_total": market_total,
            "bond_mtm_pnl": market_total - book_total,          # <0 on a rate hike above coupon (duration/SVB)
            "hh_bond_wealth": float(sum(v for k, v in held.items() if k in hh_ids)),
            "hh_bond_face": hh_bond_face,
            "hh_bond_market_value": hh_bond_market,
            "bank_bond_face": bank_bond_face,
            "bank_bond_market_value": bank_bond_market,
            "cb_bond_face": cb_bond_face,
            "cb_bond_market_value": cb_bond_market,
            "bond_owner_share_households": _safe_ratio(hh_bond_market, market_total),
            "bond_owner_share_banks": _safe_ratio(bank_bond_market, market_total),
            "bond_owner_share_cb": _safe_ratio(cb_bond_market, market_total),
            "bond_duration_weighted": duration_weighted,
            "bond_maturity_weighted": maturity_weighted,
            "bond_market_to_face": _safe_ratio(market_total, bond_face_total),
            "bond_discount": 1.0 - _safe_ratio(market_total, bond_face_total),
            "bond_share_of_gov_debt": _safe_ratio(float(getattr(econ, "_bonds_outstanding", 0.0)),
                                                  rec.get("gov_debt", 0.0)),
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

    # ------------------------------------------------------------------
    # v13 demographic denominators and per-capita observables.
    # Observation only: these normalize already-recorded stocks/flows by
    # population, adults, or working-age people. They do not feed behavior.
    # ------------------------------------------------------------------
    state = getattr(econ, "demographic_state", None)
    if state is not None:
        alive_people = [person for person in getattr(state, "people", []) if getattr(person, "alive", True)]
        population_alive = float(len(alive_people))
        child_population = float(sum(1 for person in alive_people if int(person.age) < 18))
        working_age_population = float(sum(1 for person in alive_people if 18 <= int(person.age) < 65))
        elder_population = float(sum(1 for person in alive_people if int(person.age) >= 65))
        adult_population = working_age_population
        current_demo_tick = int(getattr(state, "tick_index", econ.t))
        births_tick = float(sum(1 for event in getattr(state, "birth_events", []) if event.tick == current_demo_tick))
        deaths_tick = float(sum(1 for event in getattr(state, "death_events", []) if event.tick == current_demo_tick))
        marriages_tick = float(sum(1 for event in getattr(state, "marriage_events", []) if event.tick == current_demo_tick))
        divorces_tick = float(sum(1 for event in getattr(state, "divorce_events", []) if event.tick == current_demo_tick))
        leaving_home_tick = float(sum(
            1 for event in getattr(state, "leaving_home_events", []) if event.tick == current_demo_tick
        ))
        married_share = _safe_ratio(
            float(sum(1 for person in alive_people if getattr(person, "partner_id", None) is not None)),
            population_alive,
        )
        orphan_count = float(sum(
            1
            for person in alive_people
            if int(person.age) < 18
            and person.household_id == getattr(state, "public_guardian_household_id", None)
        ))
        minor_household_missing = float(sum(
            1
            for person in alive_people
            if int(person.age) < 18 and getattr(person, "household_id", None) is None
        ))
    else:
        population_alive = float(n_h)
        child_population = 0.0
        working_age_population = float(n_h)
        elder_population = 0.0
        adult_population = float(n_h)
        births_tick = deaths_tick = marriages_tick = divorces_tick = leaving_home_tick = 0.0
        married_share = orphan_count = minor_household_missing = 0.0

    household_count = rec.get("demographic_households", float(n_h))
    total_dependency = _safe_ratio(child_population + elder_population, adult_population)
    rec.update({
        "population_alive": population_alive,
        # v19: per-capita real output -- the object whose long-run growth rate the exogenous
        # TFP drift is pre-registered against (BGP: -> g/(1-alpha) for the Cobb-Douglas sector).
        "per_capita_real_output": _safe_ratio(rec.get("real_output", 0.0), population_alive),
        "child_population": child_population,
        "adult_population": adult_population,
        "working_age_population": working_age_population,
        "elder_population": elder_population,
        "child_share": _safe_ratio(child_population, population_alive),
        "adult_share": _safe_ratio(adult_population, population_alive),
        "working_age_share": _safe_ratio(working_age_population, population_alive),
        "elder_share": _safe_ratio(elder_population, population_alive),
        "dependency_ratio": total_dependency,
        "youth_dependency_ratio": _safe_ratio(child_population, adult_population),
        "old_age_dependency_ratio": _safe_ratio(elder_population, adult_population),
        "avg_household_size": _safe_ratio(population_alive, household_count),
        "married_share": married_share,
        "orphan_count": orphan_count,
        "minor_household_missing": minor_household_missing,
        "births_tick": births_tick,
        "deaths_tick": deaths_tick,
        "marriages_tick": marriages_tick,
        "divorces_tick": divorces_tick,
        "leaving_home_tick": leaving_home_tick,
        "birth_rate_per_1000_annualized": _safe_ratio(births_tick * 365_000.0, population_alive),
        "death_rate_per_1000_annualized": _safe_ratio(deaths_tick * 365_000.0, population_alive),
        "net_population_growth_rate_annualized": _safe_ratio((births_tick - deaths_tick) * 365.0, population_alive),
        "real_output_per_capita": _safe_ratio(rec.get("real_output", 0.0), population_alive),
        "real_consumption_per_capita": _safe_ratio(rec.get("real_consumption", 0.0), population_alive),
        "nominal_output_per_capita": _safe_ratio(rec.get("nominal_output", 0.0), population_alive),
        "household_income_per_capita": _safe_ratio(rec.get("hh_income", 0.0), population_alive),
        "household_saving_per_capita": _safe_ratio(rec.get("hh_saving", 0.0), population_alive),
        "money_per_capita": _safe_ratio(rec.get("total_money", 0.0), population_alive),
        "private_nfa_per_capita": _safe_ratio(rec.get("net_worth", float(getattr(led, "net_worth", 0.0))), population_alive),
        "household_net_worth_per_capita": _safe_ratio(rec.get("hh_full_networth_total", 0.0), population_alive),
        "gross_household_assets_per_capita": _safe_ratio(rec.get("gross_household_assets_total", 0.0), population_alive),
        "household_debt_per_capita": _safe_ratio(
            rec.get("household_debt_total", rec.get("household_debt_total_observed", 0.0)),
            population_alive,
        ),
        "real_output_per_adult": _safe_ratio(rec.get("real_output", 0.0), adult_population),
        "real_consumption_per_adult": _safe_ratio(rec.get("real_consumption", 0.0), adult_population),
        "employment_per_adult": _safe_ratio(rec.get("employment", 0.0), adult_population),
        "labor_supply_per_adult": _safe_ratio(rec.get("labor_supply", 0.0), adult_population),
        "gov_spending_per_capita": _safe_ratio(rec.get("augmented_gov_spending", rec.get("gov_spending", 0.0)), population_alive),
        "taxes_per_capita": _safe_ratio(rec.get("tax_total", 0.0), population_alive),
        "mean_real_consumption_per_person": _safe_ratio(rec.get("real_household_consumption", 0.0), population_alive),
        "orphan_support_per_child": _safe_ratio(rec.get("orphan_support_spending", 0.0), child_population),
    })
    # ----------------------------------------------------------------------
    # v17.0 energy gauges (PLAN_v17) -- pure observation. The three standing watches:
    # FLOW (produced == used + Δstocks, the soft conservation gauge), BULLWHIP
    # (coverage stationarity + restock share), MARKUP DISCIPLINE (E-markup mean,
    # time-at-ceiling share, sector HHI). Energy revenue is intermediate: none of the
    # consumption-GDP series above read E-firms, by construction of the sector split.
    # ----------------------------------------------------------------------
    if getattr(econ.cfg, "energy_enabled", False):
        e_firms = econ.e_firms
        users = [f for f in list(cfirms) + list(kfirms) if f.energy_intensity > 0.0]
        e_produced = float(np.sum([f.produced for f in e_firms]))
        e_used = float(np.sum([f.energy_used for f in users]))
        e_bought = float(np.sum([f.energy_bought for f in users]))
        hh_units = float(getattr(econ, "_energy_hh_units", 0.0))   # v17.1: consumed on purchase
        stock_total = (float(np.sum([f.energy_stock for f in users]))
                       + float(np.sum([f.inventory for f in e_firms]))
                       + float(getattr(econ, "_spr_stock", 0.0)))   # v17.3: the SPR is a stock too
        prev_stock = getattr(econ, "_energy_prev_stock_total", None)
        flow_gap = (e_produced - e_used - hh_units - (stock_total - prev_stock)) if prev_stock is not None else 0.0
        # AGGREGATE coverage (stock over sector expected use): per-firm ratios explode
        # when a shell's d^e -> 0 while it still holds stock (the v13 active-seller
        # hygiene lesson); the aggregate is the stable gauge, the min reads ACTIVE firms.
        _use_expected = float(np.sum([f.energy_intensity * f.demand_expected for f in users]))
        _stock_down = float(np.sum([f.energy_stock for f in users]))
        _active_u = [f for f in users if f.energy_intensity * f.demand_expected > 1e-6]
        coverage = ([_stock_down / _use_expected] if _use_expected > 1e-9 else [])
        coverage_min = ([f.energy_stock / (f.energy_intensity * f.demand_expected) for f in _active_u]
                        or [0.0])
        e_sales = [f.sales for f in e_firms]
        e_sales_tot = float(np.sum(e_sales))
        e_cost_used_tot = float(np.sum([f.energy_cost_used for f in users]))
        _e_active = [f for f in e_firms if f.sales > 1e-9] or list(e_firms)
        rec.update({
            "energy_price": float(getattr(econ, "_energy_price", 0.0)),   # transaction-weighted, hold-last
            "energy_produced": e_produced,
            "energy_sold": float(getattr(econ, "_energy_sold", 0.0)),
            "energy_used": e_used,
            "energy_bought": e_bought,
            "energy_stock_total": stock_total,                       # downstream input + E output stocks
            "energy_flow_gap": flow_gap,                             # soft gauge: ≈0 every tick
            "energy_coverage_mean": _mean(coverage),                 # AGGREGATE ticks of expected use held
            "energy_coverage_min": float(min(coverage_min)),         # worst ACTIVE firm
            "energy_unfilled": float(getattr(econ, "_energy_unfilled", 0.0)),
            "energy_restock_share": (max(0.0, e_bought - e_used) / e_bought) if e_bought > 1e-9 else 0.0,
            "energy_cost_share": (e_cost_used_tot / (total_wagebill + e_cost_used_tot))
                                 if (total_wagebill + e_cost_used_tot) > 1e-9 else 0.0,
            "e_markup_mean": _mean([f.markup for f in _e_active]),
            "e_markup_at_cap_share": _mean([1.0 if f.markup >= f.mu_max - 1e-9 else 0.0 for f in e_firms]),
            "e_hhi": (float(np.sum([(s / e_sales_tot) ** 2 for s in e_sales])) if e_sales_tot > 1e-9 else 0.0),
            "e_capacity_utilization": (e_produced / max(1e-9, float(np.sum([f.capacity_kappa * f.capital
                                                                            for f in e_firms])))),
            "tax_energy": float(getattr(econ, "_tax_energy", 0.0)),
            "tax_energy_windfall": float(getattr(econ, "_tax_energy_windfall", 0.0)),  # v17.2
            "energy_shock_active": float(getattr(econ, "_energy_shock_active", 0.0)),  # v17.2 bookkeeping
            "spr_stock": float(getattr(econ, "_spr_stock", 0.0)),                      # v17.3
            "spr_flow": float(getattr(econ, "_spr_flow", 0.0)),                        # v17.3 (+build/-release)
            "soe_dividends": float(getattr(econ, "_soe_dividends", 0.0)),              # v17.3
            "energy_cap_binding": float(getattr(econ, "_energy_cap_binding", 0.0)),    # v17.4
            "energy_cap_compensation": float(getattr(econ, "_energy_cap_comp", 0.0)),  # v17.4
            "energy_subsidy_paid": float(getattr(econ, "_energy_subsidy_paid", 0.0)),  # v17.5
            "energy_mortality_mult": float(getattr(getattr(econ, "energy_poverty_signal", None),
                                                   "mortality_mult", 1.0)),            # v17.5
        })
        # -- v17.1 household energy: consumption GDP component, headline CPI, poverty --
        if getattr(econ.cfg, "energy_household", False):
            hh_spend = float(getattr(econ, "_energy_hh_spend", 0.0))
            # Headline index in the native transaction-weighted grammar: household
            # consumption basket = c-goods + energy, quantities aggregated at the (equal)
            # genesis base prices. Core == the existing c-goods `price_index`.
            headline = ((total_revenue + hh_spend) / (total_sales_u + hh_units)
                        if (total_sales_u + hh_units) > 1e-12 else price_index)
            prev_h = getattr(econ, "_prev_headline_index", None)
            headline_infl = (headline / prev_h - 1.0) if (prev_h and prev_h > 1e-12) else 0.0
            shares = [h.energy_spent / (h.energy_spent + h.spent)
                      for h in households if (h.energy_spent + h.spent) > 1e-12]
            n_q = max(1, len(households) // 5)
            by_dep = sorted(households, key=lambda h: led.balance(h.id))
            def _qshare(hs):
                vals = [h.energy_spent / (h.energy_spent + h.spent)
                        for h in hs if (h.energy_spent + h.spent) > 1e-12]
                return _mean(vals)
            q1, q5 = _qshare(by_dep[:n_q]), _qshare(by_dep[-n_q:])
            rec.update({
                "energy_hh_spend": hh_spend,                     # consumption GDP component
                "energy_hh_units": hh_units,
                "cpi_headline": headline,
                "headline_inflation": headline_infl,
                "energy_hh_share_mean": _mean(shares),
                "fuel_poverty_share": _mean([1.0 if s > 0.10 else 0.0 for s in shares]),
                "energy_share_q1": q1,                           # poorest deposit quintile
                "energy_share_q5": q5,                           # richest deposit quintile
            })
    if getattr(econ.cfg, "national_accounts_metrics", False):
        from macro_sim.reporting.national_accounts import preview as preview_national_accounts

        rec.update(preview_national_accounts(econ))

        # Canonical stock/flow ratios for empirical diagnostics.  The historical
        # ``*_to_gdp`` fields above intentionally remain untouched: the optional
        # national-accounts layer is observation-only and promises not to replace
        # legacy dashboard sensors.  Those old fields divide by the C-sector
        # ``nominal_output`` compatibility proxy; in particular, ``credit_to_gdp``
        # divides a stock by one model-day of output and therefore has units of
        # days.  These explicitly named fields instead use economy-wide value added
        # and annualise the denominator whenever the numerator is a stock.
        nominal_gdp = float(rec.get("nominal_gdp", 0.0))
        annual_nominal_gdp = 365.0 * nominal_gdp
        prior_nominal_gdp = list(getattr(econ, "_nominal_gdp_history", ()))
        trailing_nominal_gdp = sum(prior_nominal_gdp[-364:]) + nominal_gdp
        trailing_gdp_observed = len(prior_nominal_gdp) >= 364
        best_annual_gdp = (
            trailing_nominal_gdp if trailing_gdp_observed else annual_nominal_gdp
        )
        rec.update({
            # Explicitly label the short-run run-rate proxy retained for backward
            # compatibility.  A stock/annual-flow ratio becomes genuinely trailing
            # only after 365 accepted daily observations.
            "nominal_gdp_annualized_daily_run_rate": annual_nominal_gdp,
            "nominal_gdp_trailing_365d": trailing_nominal_gdp,
            "nominal_gdp_trailing_365d_observed": float(trailing_gdp_observed),
            "credit_to_annualized_daily_gdp": _safe_ratio(
                float(rec.get("total_credit", 0.0)), annual_nominal_gdp
            ),
            "credit_to_annual_gdp": _safe_ratio(
                float(rec.get("total_credit", 0.0)), annual_nominal_gdp
            ),
            "credit_to_trailing_365d_gdp": (
                _safe_ratio(float(rec.get("total_credit", 0.0)), trailing_nominal_gdp)
                if trailing_gdp_observed else 0.0
            ),
            "credit_to_best_available_annual_gdp": _safe_ratio(
                float(rec.get("total_credit", 0.0)), best_annual_gdp
            ),
            "annual_gdp_ratio_uses_trailing_observations": float(
                trailing_gdp_observed
            ),
            "debt_service_to_nominal_gdp": _safe_ratio(
                float(rec.get("interest_paid", 0.0))
                + float(rec.get("principal_repaid", 0.0)),
                nominal_gdp,
            ),
            "total_debt_service_to_nominal_gdp": _safe_ratio(
                float(rec.get("total_interest_paid", rec.get("interest_paid", 0.0)))
                + float(rec.get("total_principal_repaid", rec.get("principal_repaid", 0.0))),
                nominal_gdp,
            ),
        })
        if getattr(econ.cfg, "government", False):
            rec.update({
                "gov_deficit_to_nominal_gdp": _safe_ratio(
                    float(rec.get("gov_deficit", 0.0)), nominal_gdp
                ),
                "cash_deficit_to_nominal_gdp": _safe_ratio(
                    float(rec.get("cash_deficit", 0.0)), nominal_gdp
                ),
                "gov_debt_to_annual_gdp": _safe_ratio(
                    float(rec.get("gov_debt", 0.0)), annual_nominal_gdp
                ),
                "gov_debt_to_trailing_365d_gdp": (
                    _safe_ratio(float(rec.get("gov_debt", 0.0)), trailing_nominal_gdp)
                    if trailing_gdp_observed else 0.0
                ),
                "gov_debt_to_best_available_annual_gdp": _safe_ratio(
                    float(rec.get("gov_debt", 0.0)), best_annual_gdp
                ),
                "gov_spending_share_of_nominal_gdp": _safe_ratio(
                    float(rec.get("gov_spending", 0.0)), nominal_gdp
                ),
                "augmented_gov_spending_share_of_nominal_gdp": _safe_ratio(
                    float(rec.get("augmented_gov_spending", 0.0)), nominal_gdp
                ),
            })
    return rec


def commit_tick_metrics(econ, rec: Dict[str, float]) -> None:
    """Advance metric-derived cross-tick state exactly once.

    ``compute_tick_metrics`` is intentionally safe for dashboards, diagnostics, and
    tests to call repeatedly.  The simulation kernel calls this function only after it
    has accepted the tick snapshot, preserving the historical one-transition-per-tick
    behavior without hiding behavioral state changes inside reporting.
    """
    from collections import deque

    price_index = float(rec.get("price_index", 0.0))
    econ._prev_price_index = price_index
    hist = getattr(econ, "_price_index_history", None)
    if hist is None:
        hist = deque(maxlen=365)
        econ._price_index_history = hist
    hist.append(price_index)

    if (
        getattr(econ.cfg, "national_accounts_metrics", False)
        and "nominal_gdp" in rec
    ):
        gdp_hist = getattr(econ, "_nominal_gdp_history", None)
        if gdp_hist is None:
            gdp_hist = deque(maxlen=365)
            econ._nominal_gdp_history = gdp_hist
        gdp_hist.append(float(rec["nominal_gdp"]))

    if getattr(econ.cfg, "consumption_strata", False):
        if "necessity_price_index" in rec:
            econ._cpi_prev_nec = float(rec["necessity_price_index"])
        if "luxury_price_index" in rec:
            econ._cpi_prev_lux = float(rec["luxury_price_index"])

    dep = getattr(econ, "deprivation_signal", None)
    if dep is not None and getattr(econ, "demographic_state", None) is not None:
        dep_year, dep_persons = _deprivation_person_observations(econ)
        dep.observe(year=dep_year, price_index=price_index, persons=dep_persons)

    if getattr(econ.cfg, "government", False):
        econ._prev_tax_total = float(rec.get(
            "fiscal_revenue_total", rec.get("tax_total", 0.0)
        ))
        econ._prev_benefit = float(rec.get("benefit_paid", 0.0))
        econ._prev_nominal_output = float(rec.get("nominal_output", 0.0))
        econ._prev_fiscal_output = float(rec.get(
            "nominal_gdp" if getattr(econ.cfg, "fiscal_uses_national_accounts_gdp", False)
            else "nominal_output",
            0.0,
        ))
        econ._prev_u = float(rec.get("unemployment_rate", 0.0))

    if getattr(econ.cfg, "energy_enabled", False) and "energy_stock_total" in rec:
        econ._energy_prev_stock_total = float(rec["energy_stock_total"])
    if getattr(econ.cfg, "energy_household", False) and "cpi_headline" in rec:
        econ._prev_headline_index = float(rec["cpi_headline"])

    if getattr(econ.cfg, "cb_uses_fixed_basket_cpi", False):
        cb_inflation = float(rec.get("cpi_fixed_basket_inflation", 0.0))
    else:
        cb_inflation = float(rec.get("inflation", 0.0))
    if (not getattr(econ.cfg, "cb_uses_fixed_basket_cpi", False)
            and getattr(econ.cfg, "energy_household", False)
            and not getattr(econ.cfg, "cb_core_inflation", False)):
        cb_inflation = float(rec.get("headline_inflation", cb_inflation))
    if getattr(econ.cfg, "cb_log_inflation", False):
        # Feed Taylor's EMA the log price change; the exported inflation field remains
        # the arithmetic change, exactly as before this state transition was separated.
        econ._prev_inflation = math.log1p(cb_inflation) if cb_inflation > -1.0 else 0.0
    else:
        econ._prev_inflation = cb_inflation
    econ._prev_real_output = float(rec.get("real_output", 0.0))
    econ._prev_avg_wage = float(rec.get("avg_wage", 0.0))
    econ._price_level = price_index
    if getattr(econ.cfg, "national_accounts_metrics", False):
        from macro_sim.reporting.national_accounts import commit as commit_national_accounts

        commit_national_accounts(econ, rec)


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
