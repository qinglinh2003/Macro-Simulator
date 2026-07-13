"""v20.0 — the `World` container is INERT: N economies run as N independent closed
economies, and an N=1 World reproduces `Economy(cfg)` byte-for-byte (the keystone
bit-identity gate, PLAN_v20 §6 gate #3 / §11).
"""

from __future__ import annotations

import hashlib

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world import ECONOMY_SEED_STRIDE, World


def _digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def _macro_cfg(seed: int = 0, **extra) -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=120, seed=seed, **extra)


def test_n1_world_is_byte_identical_to_bare_economy():
    """World([cfg]) must reproduce Economy(cfg) exactly — the N=1 ≡ closed dev gate."""
    cfg = _macro_cfg()
    bare = Economy(cfg)
    bare.run()

    world = World([_macro_cfg()])
    world.run()

    assert world.n == 1
    assert _digest(world.economies[0].records) == _digest(bare.records)


def test_n2_world_economies_are_independent():
    """Adding economy B must not perturb economy A: each economy in an N=2 World with
    distinct seeds equals a bare Economy run at that same seed (no cross-contamination)."""
    base = 42
    world = World([_macro_cfg(), _macro_cfg()], base_seed=base)
    world.run()

    for i in range(2):
        solo = Economy(_macro_cfg(seed=base + i * ECONOMY_SEED_STRIDE))
        solo.run()
        assert _digest(world.economies[i].records) == _digest(solo.records)


def test_two_identical_configs_with_distinct_seeds_diverge():
    """The identical-economy quiet baseline (§8): same structure, different seed ⇒
    genuinely independent draws (not clones)."""
    world = World([_macro_cfg(), _macro_cfg()], base_seed=7)
    world.run()
    d0 = _digest(world.economies[0].records)
    d1 = _digest(world.economies[1].records)
    assert d0 != d1  # independent draws, not identical


def test_residency_and_currency_tags():
    world = World([_macro_cfg(), _macro_cfg()], base_seed=1)
    assert [e.economy_id for e in world.economies] == [0, 1]
    assert [e.currency for e in world.economies] == ["CUR0", "CUR1"]
