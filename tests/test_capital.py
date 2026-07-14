"""v21.1 — the international capital account: yield-driven persistent positions (PLAN_v21).

Gates: (1) capital off ⇒ the trade layer is byte-identical to v20; (2) conservation holds
with capital on; (3) a rate differential drives capital to the high-rate economy — its
currency appreciates, it runs a persistent NFA deficit, and it pays factor income abroad
(GNP < GDP); (4) capital creates a LARGER persistent NFA than the mean-reverting v20 layer.
"""

from __future__ import annotations

import hashlib

from macro_sim.config import Config
from macro_sim.world import World


def _digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def _cfg(seed=0, r=0.04):
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=200, seed=seed, r_interest=r)


def test_capital_off_is_v20_trade_identical():
    """capital=False ⇒ economies evolve exactly as the v20 trade layer (the grope
    adjustment and factor income are no-ops)."""
    a = World([_cfg(), _cfg()], base_seed=7, trade=True)                     # no capital
    a.run()
    b = World([_cfg(), _cfg()], base_seed=7, trade=True, capital=False, capital_mobility=5.0)
    b.run()  # capital flag off ⇒ mobility ignored
    for i in range(2):
        assert _digest(a.economies[i].records) == _digest(b.economies[i].records)


def test_capital_conserves():
    hi, lo = _cfg(r=0.06), _cfg(r=0.02)
    world = World([hi, lo], base_seed=9, trade=True, capital=True,
                  capital_mobility=2.0, periods_per_year=12)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()


def _mean(recs, key, i, n=60):
    return sum(r[key][i] for r in recs[-n:]) / n


def test_high_rate_economy_runs_deficit_and_pays_factor_income():
    """Interest differential ⇒ capital flows to the high-rate economy: it runs a persistent
    NFA DEFICIT (foreigners accumulate claims on it) and pays factor income abroad (GNP <
    GDP) — the emerging-market carry pattern. Assessed on the settled average (the position
    is a stock the flows converge to; a single tick is noisy)."""
    hi, lo = _cfg(r=0.06), _cfg(r=0.02)
    world = World([hi, lo], base_seed=9, trade=True, capital=True,
                  capital_mobility=3.0, capital_adjust=0.2, periods_per_year=12)
    world.run()
    wr = world.world_records
    assert _mean(wr, "nfa", 0) < 0.0         # high-rate economy is a net foreign DEBTOR
    assert _mean(wr, "nfa", 1) > 0.0         # low-rate economy is a net foreign CREDITOR
    assert _mean(wr, "factor_income", 0) < 0.0   # debtor pays interest abroad (GNP < GDP)


def test_capital_deepens_nfa_vs_mean_reverting_v20():
    """Capital ON accumulates a larger persistent NFA than the mean-reverting (v20) layer."""
    hi, lo = _cfg(r=0.06), _cfg(r=0.02)
    on = World([hi, lo], base_seed=9, trade=True, capital=True, capital_mobility=3.0, capital_adjust=0.2)
    on.run()
    off = World([_cfg(r=0.06), _cfg(r=0.02)], base_seed=9, trade=True)  # v20 mean-revert
    off.run()
    assert abs(_mean(on.world_records, "nfa", 0)) > abs(_mean(off.world_records, "nfa", 0))
