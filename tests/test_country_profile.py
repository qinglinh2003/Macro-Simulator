"""v20.3 — the CountryProfile character overlay (PLAN_v20 §0.6) + the divergence world
conserves and trades balanced (pure-trade layer, no persistent imbalance)."""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.country import ADVANCED, DEVELOPING, SYMMETRIC, CountryProfile


def _base() -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=150, seed=0)


def test_profile_applies_axes():
    base = _base()
    p = CountryProfile("x", productivity=1.5, scale=2.0, necessity_tilt=0.7)
    cfg = p.apply(base)
    assert cfg.a == base.a * 1.5
    assert cfg.n_households == base.n_households * 2
    assert cfg.necessity_share0 == 0.7


def test_symmetric_profile_is_identity_on_key_axes():
    base = _base()
    cfg = SYMMETRIC.apply(base)
    assert cfg.a == base.a and cfg.n_households == base.n_households


def test_divergence_world_conserves_and_balances():
    """Advanced vs developing: both conserve, and at the pure-trade layer trade stays
    balanced (dealer inventory bounded — persistent imbalance awaits the capital account)."""
    base = _base()
    world = World([ADVANCED.apply(base), DEVELOPING.apply(base)],
                  base_seed=11, trade=True, fx_lambda=0.1)
    world.run()
    M = min(e.ledger.total_money for e in world.economies)
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    inv = world.world_records[-1]["dealer_inventory"]
    assert max(abs(x) for x in inv) < 0.05 * M      # balanced trade (no capital account)
    # the two economies genuinely differ (different productivity ⇒ different config)
    assert world.economies[0].cfg.a != world.economies[1].cfg.a
