"""v21.2 — the impossible trinity + currency crisis (PLAN_v21 §3).

Under a peg the CB fixes the rate and absorbs the imbalance onto FX reserves. With open
capital: an INDEPENDENT policy rate ⇒ a one-way flow ⇒ reserves drain ⇒ the peg breaks and
the currency devalues (a crisis). A MATCHED rate ⇒ reserves stable ⇒ the peg holds — but the
CB has surrendered monetary autonomy. You cannot have all three.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.capital import capital_financing
from macro_sim.world.fx import DEALER_ID


def _pair(r_peg, r_anchor=0.05, peg=True):
    # B5b: peg pressure reads the LIVE rates (the filed static-rate defect is fixed).
    # The trilemma premise -- a DELIBERATELY independent rate -- therefore needs the
    # rate PINNED: central_bank=False => monetary_regime='exogenous' => _rate ==
    # r_interest exactly. (The old test smuggled independence through the static
    # config read while the live Taylor rates actually converged.)
    peg0 = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0,
                       r_interest=r_peg, central_bank=False)
    anc = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0,
                      r_interest=r_anchor, central_bank=False)
    return World([peg0, anc], base_seed=9, trade=True, capital=True, capital_mobility=3.0,
                 capital_adjust=0.2, peg=peg, peg_reserves0=5000.0, peg_reserve_scale=0.02)


def test_independent_rate_drains_reserves_to_crisis():
    """Independent (low) policy rate under the peg ⇒ reserves drain to zero ⇒ the peg breaks
    ⇒ the currency devalues — a currency crisis."""
    world = _pair(r_peg=0.02)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
    wr = world.world_records
    broke = next((r["t"] for r in wr if not r["peg_intact"]), None)
    assert broke is not None                       # the peg BROKE
    assert wr[broke]["reserves"] == 0.0            # reserves were exhausted
    pre = wr[broke - 1]["e"][0]
    post = wr[min(broke + 5, len(wr) - 1)]["e"][0]
    assert post > pre * 1.02                       # the currency DEVALUED (>2%)


def test_matched_rate_sustains_peg_but_no_autonomy():
    """Matching the anchor rate ⇒ no mismatch ⇒ reserves stable ⇒ the peg holds — the price
    of the peg is zero monetary autonomy."""
    world = _pair(r_peg=0.05)                       # matches the anchor
    world.run()
    wr = world.world_records
    assert all(r["peg_intact"] for r in wr)        # never broke
    assert abs(wr[-1]["reserves"] - wr[0]["reserves"]) < 1e-6   # reserves untouched


def test_peg_off_economies_still_conserve():
    world = _pair(r_peg=0.02, peg=False)   # B5b: the regime is set at construction
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()


def test_reserve_asset_survives_depeg_and_does_not_create_a_capital_gap():
    """Changing the exchange-rate regime cannot delete a live CB reserve asset.

    The reserve-acquisition dealer legs and the official asset offset at genesis,
    so portfolio adjustment must also see a zero market position rather than try
    to unwind the accounting plumbing through trade.
    """
    world = _pair(r_peg=0.05)

    assert world.reserves() == pytest.approx(5000.0)
    assert world.market_external_positions() == pytest.approx([0.0, 0.0])
    assert capital_financing(world, 0, best_price=1.0) == pytest.approx(0.0)
    assert capital_financing(world, 1, best_price=1.0) == pytest.approx(0.0)

    # B5b sanctioned de-peg: flip the pegger's OWN regime; the barrier commit
    # stages a voluntary exit. The reserve ASSET must survive the regime change.
    world.economies[0].external_policy.fx_regime = "float"
    world._commit_external_policies()

    assert world.reserves() == pytest.approx(5000.0)
    assert world.market_external_positions() == pytest.approx([0.0, 0.0])


def test_factor_income_cash_does_not_recursively_become_new_principal():
    """The factor-income layer promises simple service on contract principal.

    Cash settlement still changes NFA/dealer inventory, but paying one period's
    income must not silently capitalize it and charge interest-on-interest in the
    next period without a new capital-flow contract.
    """
    cfg = Config.v3(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_ticks=2,
        r_interest=0.1,
    )
    world = World([cfg, cfg], base_seed=17, couple=True, capital=True)
    debtor, creditor = world.economies
    principal = 10.0
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, principal)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, principal)
    world._factor_interest_principal = [principal, -principal]

    world.step()
    first = list(world._factor_income)
    world.step()
    second = list(world._factor_income)

    assert first == pytest.approx([1.0, -1.0])
    # Debtor-currency service remains exactly simple interest.  The creditor's
    # local-currency receipt can differ after FX moves, while the reported common-
    # numeraire counterflows must still cancel.
    assert second[0] == pytest.approx(1.0)
    assert sum(world.world_records[-1]["factor_income"]) == pytest.approx(0.0)
    assert world._factor_interest_principal == pytest.approx([principal, -principal])
    assert world.dealer.inventory()[0] == pytest.approx(12.0)


def test_peg_freezes_only_the_cross_rate_v24():
    """v24 portrait finding A4: a bilateral peg fixes e_pegger/e_anchor -- the REST of the
    world must keep floating. (The v21 implementation returned [0.0]*n while the peg held,
    silently freezing every currency: one intact peg turned the whole simulation into a
    fixed-exchange-rate regime.)"""
    cfgs = [
        # ledger_rel_tol 1e-8: three coupled economies at 300 ticks accumulate reserve-overlay
        # float rounding just past the 1e-9 default (the A8/A5 micro-drift class) -- the knob
        # exists precisely for high-volume multi-economy horizons.
        Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=i,
                    r_interest=r, ledger_rel_tol=1e-8)
        for i, r in enumerate((0.02, 0.05, 0.08))
    ]
    world = World(cfgs, base_seed=9, trade=True, capital=True, capital_mobility=1.0,
                  capital_adjust=0.2, peg=True, peg_economy=0, peg_anchor=1,
                  peg_reserves0=1.0e9, peg_reserve_scale=0.02)   # reserves >> drain: peg survives
    world.run(300)
    wr = world.world_records
    assert all(r["peg_intact"] for r in wr), "peg must survive this test"
    cross = [r["e"][0] / r["e"][1] for r in wr]
    assert max(cross) == pytest.approx(min(cross), rel=1e-9), \
        "the pegged CROSS rate must stay exactly fixed"
    third = [r["e"][2] for r in wr]
    assert max(third) / min(third) > 1.0 + 1e-6, \
        "the third currency must keep floating while the peg holds"
