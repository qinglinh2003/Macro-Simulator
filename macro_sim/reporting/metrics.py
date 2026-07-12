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
from macro_sim.demographics.economic_state import build_household_economic_profiles
from macro_sim.systems.banking import bank_economic_capital, bank_equity_value, bank_for
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

    # Inflation vs last tick's price index (0 on the first tick).
    prev_p = getattr(econ, "_prev_price_index", None)
    inflation = (price_index / prev_p - 1.0) if (prev_p and prev_p > 1e-12) else 0.0
    econ._prev_price_index = price_index
    hist = getattr(econ, "_price_index_history", None)
    if hist is None:
        from collections import deque
        hist = econ._price_index_history = deque(maxlen=365)
    yoy_base = hist[0] if len(hist) == 365 else (hist[0] if hist else price_index)
    inflation_yoy = (price_index / yoy_base - 1.0) if yoy_base > 1e-12 else 0.0
    hist.append(price_index)

    dividends_paid = float(getattr(econ, "_dividends_paid", 0.0))
    retained = max(0.0, total_profit) - dividends_paid  # positive profit not paid out

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
        owner_households = sum(1 for h in households if housing.dwellings_of(h.id))
        rec.update(
            {
                "dwellings_total": float(housing.count()),
                "dwellings_fiscal": float(len(housing.dwellings_of(fiscal)) if fiscal else 0.0),
                "homeowner_share": owner_households / max(1, len(households)),
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
                    "rent_paid_total": float(rental.rent_paid_total),
                    "evictions_total": float(rental.evictions_total),
                    "tenant_share": float(len(rental.tenancies)) / max(1, len(households)),
                    "landlord_count": float(sum(
                        1 for h in households if len(housing.dwellings_of(h.id)) > 1
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
            f.profit / max(1e-9, led.balance(f.id) + led.debt(f.id) + f.capital)
            for f in cfirms
        ]),
        "profit_rate_dispersion": _std([
            f.profit / max(1e-9, led.balance(f.id) + led.debt(f.id) + f.capital)
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
        "labor_sold_gini": gini([h.labor_sold for h in households]),
        "full_unemployed_share": float(np.mean([(h.labor_sold + h.jg_labor) <= 1e-9 for h in households]))
        if households else 0.0,
        "underemployed_share": float(np.mean([(h.labor_sold + h.jg_labor) < 1.0 - 1e-9 for h in households]))
        if households else 0.0,
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
        new_household_loans = float(getattr(econ, "_hh_credit_new", 0.0)) + float(getattr(econ, "_hh_margin_new", 0.0))
        total_interest = float(getattr(econ, "_interest_paid", 0.0)) + float(getattr(econ, "_hh_interest", 0.0))
        total_principal = (
            float(getattr(econ, "_principal_repaid", 0.0))
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
            "hh_networth_gini": gini(list(np.maximum(nw, 0.0))),   # clip, not min-shift: one deep debtor made the shifted gini gyrate
            "hh_networth_min": float(nw.min()),
            "hh_networth_median": float(np.median(nw)),
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
        "total_debt_service_ratio": ((rec.get("total_interest_paid", rec.get("interest_paid", 0.0))
                                      + rec.get("total_principal_repaid", rec.get("principal_repaid", 0.0)))
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
    full_networth_shifted = full_networth - float(full_networth.min()) if full_networth.size else full_networth
    gross_assets = np.asarray(hh_dep, dtype=float) + firm_equity_values + bank_equity_values + bond_market_values
    rec.update({
        "mean_real_consumption_per_household": float(real_c.mean()) if real_c.size else 0.0,
        "median_real_consumption": float(np.median(real_c)) if real_c.size else 0.0,
        "bottom25_consumption": float(np.sort(real_c)[:bottom25_n].mean()) if real_c.size else 0.0,
        "subsistence_gap_ratio": _safe_ratio(float(subsistence_gap.sum()), subsist * n_h),
        "median_real_household_income": float(np.median(inc / defl)) if inc.size else 0.0,
        "consumption_realization_rate": _safe_ratio(effective_cons, desired_cons),
        "real_household_consumption": float(real_c.sum()),
        "hh_deposit_p10": _quantile(hh_dep, 0.10),
        "hh_deposit_median": _quantile(hh_dep, 0.50),
        "hh_deposit_p90": _quantile(hh_dep, 0.90),
        "household_debt_gini": gini(hh_debt),
        "household_debt_top10_share": top_share(hh_debt, 0.10),
        "equity_wealth_top10_share": top_share(firm_equity_values, 0.10),
        "bank_equity_top10_share": top_share(bank_equity_values, 0.10),
        "bond_wealth_gini": gini(bond_market_values),
        "bond_wealth_top10_share": top_share(bond_market_values, 0.10),
        "bond_wealth_share": _safe_ratio(float(bond_market_values.sum()), float(gross_assets.sum())),
        "hh_full_networth_total": float(full_networth.sum()) if full_networth.size else 0.0,
        "hh_full_networth_skew": _skew(full_networth),
        "hh_full_networth_excess_kurtosis": _excess_kurtosis(full_networth),
        "gross_household_assets_total": float(gross_assets.sum()) if gross_assets.size else 0.0,
        "household_underwater_share": float(np.mean(full_networth < 0.0)) if full_networth.size else 0.0,
        "full_networth_p10": _quantile(full_networth, 0.10),
        "full_networth_p50": _quantile(full_networth, 0.50),
        "full_networth_p90": _quantile(full_networth, 0.90),
        "hh_full_networth_gini_observed": gini(full_networth_shifted),
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
        public_investment = float(getattr(econ, "_public_investment", 0.0))
        gov_interest_bill = float(getattr(econ, "_gov_interest_bill", 0.0))
        spend_total = benefit_paid + gov_consumption + jg_spending
        augmented_spending = spend_total + public_investment + gov_interest_bill
        deficit = spend_total - tax_total                          # >0 = deficit (net outside-money injection)
        cash_deficit = augmented_spending - tax_total
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
            "augmented_gov_spending": augmented_spending,
            "cash_deficit": cash_deficit,
            "gov_deficit_to_revenue": (deficit / tax_total) if tax_total > 1e-9 else 0.0,
            "gov_deficit_to_gdp": (deficit / nominal_output) if nominal_output > 1e-9 else 0.0,
            "cash_deficit_to_gdp": (cash_deficit / nominal_output) if nominal_output > 1e-9 else 0.0,
            "gov_debt_to_gdp": (gov_debt / (365.0 * nominal_output)) if nominal_output > 1e-9 else 0.0,  # vs ANNUAL GDP
            "gov_spending_share_of_gdp": (spend_total / nominal_output) if nominal_output > 1e-9 else 0.0,
            "augmented_gov_spending_share_of_gdp": (
                augmented_spending / nominal_output
            ) if nominal_output > 1e-9 else 0.0,
            "hh_bankruptcies": float(getattr(econ, "_hh_bankruptcies", 0.0)),
            "benefit_recipient_share": float(np.mean([
                (h.labor_sold + h.jg_labor) <= 1e-9 for h in households
            ])) if households and benefit_paid > 0.0 else 0.0,
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
        cb_cfg = econ.cfg.central_banking
        pol = econ.policy
        inflation_gap = infl_ema - pol.inflation_target
        unemployment_gap = rec.get("unemployment_rate", 0.0) - cb_cfg.u_natural
        taylor_target = (
            cb_cfg.r_neutral
            + pol.taylor_phi_pi * inflation_gap
            - pol.taylor_phi_u * unemployment_gap
        )
        omo_target = (
            float(getattr(econ, "_omo_target_value",
                          cb_cfg.omo_reserve_target * float(getattr(econ, "_reserve_M0", 0.0))))
            if cb_cfg.omo and cb_cfg.bonds and cb_cfg.interbank else 0.0
        )
        bank_reserves_total = rec.get("bank_reserves_total", 0.0)
        cb_bond_market = float(sum(bond_mv_by_holder.get("CB", ())))
        rec.update({
            "policy_rate": rate,
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
        econ_caps = [bank_economic_capital(econ, b) for b in econ.banks if b.alive]
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
        market_total = float(sum(bond_market_value(econ, l) for l in lots)) if lots else 0.0
        book_total = float(sum(l["cost"] for l in lots)) if lots else 0.0
        bank_bond_face = float(sum(l["face"] for l in lots if l["holder"] in bank_ids)) if lots else 0.0
        hh_bond_face = float(sum(l["face"] for l in lots if l["holder"] in hh_ids)) if lots else 0.0
        cb_bond_face = float(sum(l["face"] for l in lots if l["holder"] == "CB")) if lots else 0.0
        hh_bond_market = float(sum(bond_market_value(econ, l) for l in lots if l["holder"] in hh_ids)) if lots else 0.0
        bank_bond_market = float(sum(bond_market_value(econ, l) for l in lots if l["holder"] in bank_ids)) if lots else 0.0
        cb_bond_market = float(sum(bond_market_value(econ, l) for l in lots if l["holder"] == "CB")) if lots else 0.0
        bond_face_total = float(sum(l["face"] for l in lots)) if lots else 0.0
        maturity_weighted = _safe_ratio(
            float(sum(l["face"] * max(0.0, l["matures_at"] - econ.t) for l in lots)),
            bond_face_total,
        )
        duration_weighted = maturity_weighted if getattr(econ.cfg, "bond_coupon", 0.0) <= 0.0 else _safe_ratio(
            float(sum(bond_market_value(econ, l) * max(0.0, l["matures_at"] - econ.t) for l in lots)),
            market_total,
        )
        alive_banks = [b for b in econ.banks if b.alive]
        econ_caps = [bank_economic_capital(econ, b) for b in alive_banks]
        rec.update({
            "bonds_outstanding": float(getattr(econ, "_bonds_outstanding", 0.0)),   # = Σ face
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
    if getattr(econ.cfg, "cb_log_inflation", False):
        # v13: feed the Taylor EMA the LOG price change (ln(P/P_prev) = log1p(inflation)). The
        # arithmetic per-tick change has a Jensen bias under index noise (the sick 10k run's EMA
        # read ~7x the true trend), so the CB chased noise. The `inflation` column is unchanged.
        econ._prev_inflation = math.log1p(inflation) if inflation > -1.0 else 0.0
    else:
        econ._prev_inflation = inflation      # v10: last tick's realised inflation feeds the Taylor EMA
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
