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


def _pair(r_peg, r_anchor=0.05):
    peg0 = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=r_peg)
    anc = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=r_anchor)
    return World([peg0, anc], base_seed=9, trade=True, capital=True, capital_mobility=3.0,
                 capital_adjust=0.2, peg=True, peg_reserves0=5000.0, peg_reserve_scale=0.02)


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
    world = _pair(r_peg=0.02)
    world.peg = False
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

    world.peg = False

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
