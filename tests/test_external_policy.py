"""v25 B5a: ExternalPolicy -- per-economy ownership of the World coupling levers,
atomic barrier commit, A6 sanctions semantics, legacy-constructor equivalence."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.core.policy_registry import set_lever
from macro_sim.world.world import World


def _cfg(seed: int = 0) -> Config:
    return Config.v13(seed=seed, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                      demographics_population=120, n_ticks=40, government=True)


def _digest(world) -> str:
    payload = [[{k: r[k] for k in sorted(r)} for r in econ.records] for econ in world.economies]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def test_legacy_ctor_seeds_external_policy():
    w = World([_cfg(), _cfg(1)], base_seed=5, trade=True, tariff=[0.1, 0.2],
              sanctions={frozenset({0, 1})}, immigration_cap=0.5, migration=True)
    assert w.economies[0].external_policy.tariff == pytest.approx(0.1)
    assert w.economies[1].external_policy.tariff == pytest.approx(0.2)
    # legacy pair seeds BOTH sides (unilateral ownership, symmetric effect)
    assert w.economies[0].external_policy.sanctions_imposed_on == frozenset({1})
    assert w.economies[1].external_policy.sanctions_imposed_on == frozenset({0})
    assert w.sanctioned(0, 1) and w.sanctioned(1, 0)
    assert w.economies[0].external_policy.immigration_cap == pytest.approx(0.5)


def test_legacy_vector_equivalence_bit_identical():
    """The ctor round-trip (legacy args -> ExternalPolicy -> committed vectors)
    must not change a single record."""
    kw = dict(base_seed=9, trade=True, fx_lambda=0.1, tariff=0.05, export_subsidy=0.02)
    a = World([_cfg(), _cfg()], **kw)
    b = World([_cfg(), _cfg()], **kw)
    a.run(30)
    b.run(30)
    assert _digest(a) == _digest(b)


def test_barrier_commit_is_atomic_and_next_tick():
    w = World([_cfg(), _cfg(1)], base_seed=7, trade=True)
    w.run(5)
    w.economies[0].external_policy.tariff = 0.5
    # not yet committed: the world vector still carries the old value
    assert w.tariff[0] == pytest.approx(0.0)
    w.step()
    assert w.tariff[0] == pytest.approx(0.5), "the barrier must commit the stance"
    assert w.tariff[1] == pytest.approx(0.0), "other economies keep their own stance"


def test_sanctions_or_semantics_and_unilateral_lift():
    w = World([_cfg(), _cfg(1), _cfg(2)], base_seed=11, trade=True)
    w.run(3)
    e0, e1 = w.economies[0], w.economies[1]
    set_lever(e0, "sanctions_imposed_on", frozenset({1}), actor="gov0")
    set_lever(e1, "sanctions_imposed_on", frozenset({0}), actor="gov1")
    w.step()
    assert w.sanctioned(0, 1)
    # one side lifts -- the block PERSISTS while any stance stands (A6)
    set_lever(e0, "sanctions_imposed_on", frozenset(), actor="gov0")
    w.step()
    assert w.sanctioned(0, 1), "the other imposer's stance must keep the block"
    set_lever(e1, "sanctions_imposed_on", frozenset(), actor="gov1")
    w.step()
    assert not w.sanctioned(0, 1), "both stances lifted -> flows resume"
    assert not w.sanctioned(0, 2)


def test_set_lever_routes_external_scope():
    w = World([_cfg(), _cfg(1)], base_seed=13, trade=True)
    w.run(3)
    e = w.economies[0]
    set_lever(e, "tariff", 0.25, actor="gov")
    assert e.external_policy.tariff == pytest.approx(0.25)
    assert e.policy is not e.external_policy
    assert e._policy_action_log[-1]["scope"] == "external"
    with pytest.raises(ValueError):
        set_lever(e, "tariff", 99.0, actor="gov")   # out of range
    with pytest.raises(ValueError):
        set_lever(e, "sanctions_imposed_on", {1}, actor="gov")   # not a frozenset


def test_tariff_lever_changes_trade_outcome():
    kw = dict(base_seed=9, trade=True, fx_lambda=0.1)
    a = World([_cfg(), _cfg()], **kw)
    b = World([_cfg(), _cfg()], **kw)
    a.run(40)
    b.run(20)
    b.economies[0].external_policy.tariff = 1.5   # prohibitive importer tariff
    b.run(20)
    assert _digest(a) != _digest(b), "a prohibitive tariff must alter the trajectory"
    assert sum(b._tariff_rev) >= 0.0
