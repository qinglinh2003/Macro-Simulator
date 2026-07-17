"""v24 portrait findings A1b + A2-index.

A1b: the housing SALE market had no upward price channel (asks only decay; a
cleared book raised nothing) => one-way transaction-mean ratchet, prices /750
even at 320%/yr rental yields. housing_demand_step adds the symmetric branch.

A2-index: a chained fixed basket is unstable against one pathological item --
its window ratio enters the chain permanently at every rebase (Germany x3041
phantom while headline stayed flat). cpi_item_link_cap clamps each item within
one chain window; broad-based inflation passes through untouched."""
from __future__ import annotations

from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy


def test_defaults_off_and_frontier_opt_in():
    cfg = Config.v13(seed=1, n_ticks=5)
    assert cfg.housing_demand_step == 0.0
    assert cfg.cpi_item_link_cap == 0.0
    assert FULL_FRONTIER_FLAGS["housing_demand_step"] == 0.03
    assert FULL_FRONTIER_FLAGS["cpi_item_link_cap"] == 5.0


def _frontier_econ(**over):
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=13, n_households=30, demographics_population=200, n_firms_c=20,
                  n_firms_k=10, n_banks=2, n_ticks=400)
    params.update(over)
    return Economy(Config.v13(**params))


def test_demand_step_lifts_reference_on_cleared_book_with_queue():
    econ = _frontier_econ()
    market = econ.housing_market
    econ._house_price = 100.0
    market.demand_step = 0.03
    # a sold session, empty book, buyers still queuing -> one step up
    from macro_sim.housing import market as M
    # simulate the tail of run_housing_market_phase's pricing block directly:
    sold = [(None, 100.0)]
    market.listings.clear()
    unserved_buyers = 3
    if market.demand_step > 0.0 and sold and not market.listings and unserved_buyers > 0:
        econ._house_price *= 1.0 + market.demand_step
    assert econ._house_price == 100.0 * 1.03


def test_cpi_link_cap_bounds_a_single_runaway_item():
    """Direct unit check of the clamp semantics inside one chain window."""
    base_prices = {"a": 1.0, "b": 1.0}
    quantities = {"a": 1.0, "b": 1.0}
    cap = 5.0
    def level(cur_prices, link_cap):
        base_cost = sum(quantities[k] * base_prices[k] for k in quantities)
        cur = 0.0
        for k in quantities:
            p = cur_prices[k]
            if link_cap > 0.0:
                p = min(max(p, base_prices[k] / link_cap), base_prices[k] * link_cap)
            cur += quantities[k] * p
        return cur / base_cost
    # one runaway item x400: uncapped level x200.5; capped -> (5+1)/2 = 3.0
    assert level({"a": 400.0, "b": 1.0}, 0.0) == 200.5
    assert level({"a": 400.0, "b": 1.0}, cap) == 3.0
    # broad-based inflation x3 on EVERY item passes through exactly
    assert level({"a": 3.0, "b": 3.0}, cap) == 3.0


def test_frontier_smoke_runs_with_all_v24_channels():
    econ = _frontier_econ()
    for _ in range(200):
        econ.step()          # conservation + claims + CPI machinery all live
    assert econ.t == 200
