"""Open-economy governance policy levers (PLAN_v20 §12 Layer C): tariff (trade), capital
controls (capital), sanctions (strategic). Each is a run-time government lever on a
dealer-routed flow; off ⇒ the prior version's behavior; all conserving.
"""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.world import World


def _cfg(a=1.0, r=0.04):
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=250, seed=0, a=a, r_interest=r)


def _mean(recs, fn, n=40):
    return sum(fn(r) for r in recs[-n:]) / n


# -- trade policy: tariff -----------------------------------------------------

def test_tariff_is_protective_and_raises_revenue():
    base = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    base.run()
    tar = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True, tariff=0.01)
    tar.run()
    for econ in tar.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    imp_base = _mean(base.world_records, lambda r: sum(r["import_value"]))
    imp_tar = _mean(tar.world_records, lambda r: sum(r["import_value"]))
    assert imp_tar < imp_base                                   # protective (fewer imports)
    assert _mean(tar.world_records, lambda r: sum(r["tariff_rev"])) > 0.0   # fiscal revenue


# -- capital policy: capital controls (the trilemma's third corner) -----------

def _peg(control):
    lo = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=0.02)
    an = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=0.05)
    return World([lo, an], base_seed=9, trade=True, capital=True, capital_mobility=3.0,
                 capital_adjust=0.2, peg=True, peg_reserves0=5000.0, peg_reserve_scale=0.02,
                 capital_control=control)


def test_capital_controls_save_the_peg():
    """Peg + an independent rate breaks WITHOUT controls (reserves drain) but SURVIVES with
    controls — closing the capital account is the trilemma's third corner (peg + autonomy)."""
    free = _peg(0.0)
    free.run()
    closed = _peg(0.95)
    closed.run()
    assert any(not r["peg_intact"] for r in free.world_records)     # free capital ⇒ crisis
    assert all(r["peg_intact"] for r in closed.world_records)       # controls ⇒ peg survives


# -- strategic: sanctions -----------------------------------------------------

def test_sanctions_sever_bilateral_trade():
    """A sanction zeroes the pair's bilateral flow; for N=2 that is autarky (no trade)."""
    world = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True, sanctions={frozenset({0, 1})})
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
    assert sum(sum(r["import_value"]) for r in world.world_records) == 0.0
