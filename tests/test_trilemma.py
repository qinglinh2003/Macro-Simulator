"""v21.2 — the impossible trinity + currency crisis (PLAN_v21 §3).

Under a peg the CB fixes the rate and absorbs the imbalance onto FX reserves. With open
capital: an INDEPENDENT policy rate ⇒ a one-way flow ⇒ reserves drain ⇒ the peg breaks and
the currency devalues (a crisis). A MATCHED rate ⇒ reserves stable ⇒ the peg holds — but the
CB has surrendered monetary autonomy. You cannot have all three.
"""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.world import World


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
