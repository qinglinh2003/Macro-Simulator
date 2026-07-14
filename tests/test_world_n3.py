"""v20.4 — generalize to N=3 (PLAN_v20 §11). The FX/trade machinery is general-N; the
new N≥3 phenomena are triangular cross-rate consistency and vehicle-currency emergence.
"""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.world import World


def _cfg() -> Config:
    return Config.v124(n_firms_c=30, n_firms_k=15, n_households=150, n_ticks=200, seed=0)


def test_n3_conserves_and_trades():
    world = World([_cfg(), _cfg(), _cfg()], base_seed=5, trade=True, fx_lambda=0.1)
    world.run()
    assert world.n == 3
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    gross = sum(sum(r["import_value"]) for r in world.world_records)
    assert gross > 0.0                               # trade happens among the three


def test_n3_triangular_consistency_exact():
    """Cross-rates derived from the single numéraire vector are arbitrage-free BY
    CONSTRUCTION: any round-trip i→j→k→i multiplies to exactly 1 (§2)."""
    world = World([_cfg(), _cfg(), _cfg()], base_seed=5, trade=True, fx_lambda=0.1)
    world.run()
    r = world.rates
    round_trip = r.bilateral(0, 1) * r.bilateral(1, 2) * r.bilateral(2, 0)
    assert abs(round_trip - 1.0) < 1e-12


def test_n3_rates_stay_bounded():
    """The coupled 3-economy system is stable — no rate runs away to 0 or ∞."""
    world = World([_cfg(), _cfg(), _cfg()], base_seed=5, trade=True, fx_lambda=0.1)
    world.run()
    for e in world.world_records[-1]["e"]:
        assert 0.2 < e < 5.0                          # bounded (mean-reverting, not divergent)


def test_n3_vehicle_currency_emerges():
    """With N≥3, sourcing concentrates: some currency becomes the dominant source (the
    emergent vehicle/hub currency) — an N≥3-only phenomenon (§2.2, §12)."""
    world = World([_cfg(), _cfg(), _cfg()], base_seed=5, trade=True, fx_lambda=0.1)
    world.run()
    from collections import Counter
    counts = Counter(s for s in world._import_source if s >= 0)
    # the most-used source is chosen by more than its equal share (a hub emerges)
    assert counts and counts.most_common(1)[0][1] >= 2
