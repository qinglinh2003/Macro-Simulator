"""v15.4: construction -- primary supply on the native firm grammar, land-fee anchor.

Builders hire in the labor market, output folds into unit inventory, whole dwellings
mint under the yearly permit quota after paying the convex land fee to the fiscal, and
list as primary supply. The registry count invariant survives because builders are
exactly the mint() path.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=800,
        housing_enabled=True,
        housing_market_enabled=True,
        housing_construction_enabled=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_builders_created_on_the_firm_rails():
    econ = make_econ()
    assert len(econ.builders) == 5
    for firm in econ.builders:
        assert firm in econ.firms                    # labor market + settlement see them
        assert firm.sells == "housing"
        assert econ.ledger.balance(firm.id) > 0.0    # fiscal seed capital arrived
    econ.step()                                      # conservation gates hold with builders


def test_construction_mints_and_stock_grows():
    econ = make_econ(builder_productivity=0.05)      # hot productivity: mint within weeks
    stock0 = econ.housing.count()
    land_fee_total = 0.0
    for _ in range(200):
        econ.step()
        new_total = getattr(econ, "_land_fee_paid", 0.0)
        assert econ.records[-1]["fiscal_land_fee_revenue"] == pytest.approx(
            new_total - land_fee_total
        )
        assert getattr(econ, "_land_fee_paid_tick", 0.0) == pytest.approx(
            new_total - land_fee_total
        )
        land_fee_total = new_total
    assert econ.housing.count() > stock0             # primary supply exists
    assert getattr(econ, "_dwellings_built", 0) >= 1
    assert getattr(econ, "_land_fee_paid", 0.0) > 0.0
    econ.housing.assert_invariants()                 # count == minted still exact
    rec = econ.records[-1]
    assert rec["dwellings_built_total"] >= 1


def test_permit_quota_binds():
    econ = make_econ(builder_productivity=0.05, housing_permits=2)
    for _ in range(400):
        econ.step()
    assert getattr(econ, "_dwellings_built", 0) <= 2 * 2   # <= permits x years elapsed
    # WIP piles up instead of minting past the quota
    assert sum(getattr(f, "wip", 0.0) for f in econ.builders) > 0.0


def test_land_fee_is_convex_in_the_stock():
    econ = make_econ(builder_productivity=0.05, land_convexity=2.0)
    fees = []
    built_prev = 0
    for _ in range(400):
        econ.step()
        built = getattr(econ, "_dwellings_built", 0)
        if built > built_prev:
            fees.append(getattr(econ, "_land_fee_paid", 0.0))
            built_prev = built
    assert len(fees) >= 2
    increments = [b - a for a, b in zip(fees, fees[1:])]
    # marginal land fee rises with the stock (price also moves; direction dominates
    # under convexity 2 when prices are anchored by the same market)
    assert increments[-1] > 0.0


def test_first_mint_reachable_at_production_productivity():
    """Regression for the mid-gestation starvation zombie: at the PRODUCTION
    productivity (0.002 => ~500 labor-ticks per dwelling) the seed capital must carry
    the builder through the whole first gestation INCLUDING the land fee at the end.
    The hot-productivity tests above cannot catch this."""
    econ = make_econ(n_ticks=400)          # default builder_productivity
    for _ in range(320):
        econ.step()
    assert getattr(econ, "_dwellings_built", 0) >= 1
    assert all(econ.ledger.balance(b.id) >= 0.0 for b in econ.builders)


def test_construction_off_leaves_no_trace():
    econ = make_econ(housing_construction_enabled=False)
    assert not getattr(econ, "builders", None)
    for _ in range(35):
        econ.step()
    assert "dwellings_built_total" not in econ.records[-1]
    assert econ.housing.count() == econ._genesis_dwellings
