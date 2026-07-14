"""v20.2 — the first real L2: dealer-routed cross-border trade (PLAN_v20 §4, §11 v20.2).

Gates: (1) trade off ≡ closed (the goods-phase hook is a no-op); (2) the identical-economy
quiet baseline holds — symmetric economies trade but net to zero, rates flat; (3) all
economies conserve with trade on; (4) the BoP identity holds by construction.
"""

from __future__ import annotations

import hashlib

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world import World


def _digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def _cfg(seed: int = 0) -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=200, seed=seed)


def test_trade_off_is_closed_economy_identical():
    """trade=False ⇒ the goods-phase foreign-trade hook is never fed ⇒ bit-identical to a
    bare Economy (the off ≡ v20.1/closed gate)."""
    bare = Economy(_cfg())
    bare.run()
    world = World([_cfg(), _cfg()], base_seed=None, trade=False)  # trade off
    world.run()
    # economy 0 (seed 0, same as bare) must match byte-for-byte
    assert _digest(world.economies[0].records) == _digest(bare.records)


def test_clone_quiet_baseline_balanced():
    """Identical economies (clones): trade FLOWS but nets to zero — dealer inventory ~0,
    rates flat. The symmetric quiet baseline (§8)."""
    world = World([_cfg(), _cfg()], trade=True, fx_lambda=0.1)   # clones (same seed)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    last = world.world_records[-1]
    assert all(abs(x) < 1.0 for x in last["dealer_inventory"])   # ~0 (balanced)
    assert all(abs(e - 1.0) < 1e-6 for e in last["e"])           # rates flat
    gross = sum(sum(r["import_value"]) for r in world.world_records)
    assert gross > 0.0                                           # trade actually happened


def test_diverse_economies_trade_bounded_and_conserving():
    """Different draws: trade flows, the imbalance stays small and bounded (export-financed,
    groping-cleared), and every economy conserves."""
    M = None
    world = World([_cfg(), _cfg()], base_seed=9, trade=True, fx_lambda=0.1)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
        M = econ.ledger.total_money
    inv0 = [r["dealer_inventory"][0] for r in world.world_records]
    assert max(abs(x) for x in inv0) < 0.05 * M                  # imbalance < 5% of money
    assert sum(r["import_value"][0] for r in world.world_records) > 0.0


def test_bop_identity_holds():
    """The reported BoP in the numéraire equals the dealer's net worth (Σ inventory_i / e_i)
    — the multilateral balance-of-payments identity, true by construction (gate #2)."""
    world = World([_cfg(), _cfg()], base_seed=3, trade=True)
    world.run()
    rec = world.world_records[-1]
    inv, e = rec["dealer_inventory"], rec["e"]
    recomputed = sum(inv[i] / e[i] for i in range(len(inv)))
    assert abs(rec["bop_numeraire"] - recomputed) < 1e-6
