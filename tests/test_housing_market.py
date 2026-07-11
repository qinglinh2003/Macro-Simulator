"""v15.1: resale market -- listings, sessions, atomic sales, price index.

The certified regime for v15.1 is CASH-CONSTRAINED (prices at 3-4x annual income, no
mortgages): volume is thin and rides the involuntary probate flow. These tests verify
the mechanics -- listing inflows, cheapest-first matching, atomicity (ledger + claims +
title move together under the per-tick hard gates), ask decay, index hold-last --
plus an affordable-price integration run where transactions actually happen.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.housing.market import run_housing_market_phase


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=100,
        housing_enabled=True,
        housing_market_enabled=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_market_off_leaves_no_market():
    econ = make_econ(housing_market_enabled=False)
    assert econ.housing_market is None
    econ.step()
    assert "housing_listings" not in econ.records[-1]


def empty_household_by_pinned_mortality(econ, target, max_ticks: int = 120) -> None:
    """Kill every member of `target` through the REAL death machinery (v14 Phase 3
    mortality strata pinned to an extreme multiplier), so estate settlement keeps the
    claim identities consistent -- unlike any surgical membership hack."""
    bridge = econ.demographic_bridge
    hh_id = bridge.household_id_for_account(target.id)
    bridge.stratification.mortality_strata[int(hh_id)] = 1e5
    for _ in range(max_ticks):
        econ.step()
        if not bridge.claims.members_of_household(int(hh_id)):
            return
    raise AssertionError("pinned mortality failed to empty the household in time")


def test_probate_listing_and_sale_cycle_affordable():
    """Affordable anchor (0.2y income ~ 73) so cash buyers exist: the emptied household's
    dwelling must get listed (not escheated in kind), then sell -- title to a houseless
    buyer, proceeds escheated -- under the per-tick registry/claim hard gates."""
    econ = make_econ(house_price_income_years=0.2)
    market = econ.housing_market
    for _ in range(3):
        econ.step()
    target = econ.households[0]
    dwelling_ids = [d.id for d in econ.housing.dwellings_of(target.id)]
    assert dwelling_ids
    empty_household_by_pinned_mortality(econ, target)

    for _ in range(150):
        econ.step()
        if market.sales_total > 0:
            break
    assert market.sales_total >= 1
    assert all(econ.housing.owner_of(d) != target.id for d in dwelling_ids)
    econ.housing.assert_invariants()


def test_cash_constrained_regime_at_production_anchor():
    """At the production anchor (3.5y income) nobody can buy without credit: listings
    accumulate, asks decay, sales stay ~zero -- the documented v15.1 reference regime."""
    econ = make_econ(seed=31)
    market = econ.housing_market
    for _ in range(3):
        econ.step()
    target = econ.households[0]
    empty_household_by_pinned_mortality(econ, target)
    for _ in range(31):                      # ensure a sweep + a session pass
        econ.step()
    asks_before = {l.dwelling_id: l.ask for l in market.listings.values()}
    assert asks_before                       # the probate listing exists
    for _ in range(65):
        econ.step()
    assert market.sales_total == 0
    for listing in market.listings.values():
        if listing.dwelling_id in asks_before:
            assert listing.ask < asks_before[listing.dwelling_id]   # inventory pressure decays asks


def test_distress_listing_from_liquidity_floor():
    econ = make_econ(housing_distress_floor=10_000.0)   # everyone is 'distressed'
    market = econ.housing_market
    for _ in range(31):                                  # one session boundary passes
        econ.step()
    assert len(market.listings) > 0
    assert any(not l.forced for l in market.listings.values())


def test_price_index_holds_last_without_sales():
    econ = make_econ(seed=31)
    p0 = econ._house_price
    for _ in range(65):
        econ.step()
    assert econ._house_price == pytest.approx(p0)        # no sales -> hold-last
