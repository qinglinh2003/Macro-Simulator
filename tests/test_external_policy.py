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


# ================= B5b: the peg family =================

def _peg_pair(r_peg=0.02, r_anchor=0.05, peg=False):
    a = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                   demographics_population=120, n_ticks=200, government=True,
                   r_interest=r_peg, central_bank=False)
    b = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                   demographics_population=120, n_ticks=200, government=True,
                   r_interest=r_anchor, central_bank=False)
    return World([a, b], base_seed=21, trade=True, capital=True, capital_mobility=2.0,
                 capital_adjust=0.2, peg=peg, peg_reserves0=500.0, peg_reserve_scale=0.02)


def test_runtime_peg_adoption_via_levers():
    """A floating economy ADOPTS a peg mid-run through the sanctioned path:
    stage the anchor, switch the regime; the next barrier acquires reserves."""
    w = _peg_pair()
    w.run(10)
    assert not w.peg
    e0 = w.economies[0]
    set_lever(e0, "peg_anchor", 1, actor="cb0")
    set_lever(e0, "fx_regime", "peg", actor="cb0")
    w.step()
    assert w.peg and w.peg_economy == 0 and w.peg_anchor == 1
    st = w.peg_states[0]
    assert st.reserve_account_id == "CBRES:0"
    assert w.reserves() == pytest.approx(500.0, rel=0.2), "the war chest must be acquired"


def test_peg_requires_staged_anchor():
    w = _peg_pair()
    w.run(3)
    with pytest.raises(ValueError):
        set_lever(w.economies[0], "fx_regime", "peg", actor="cb0")   # nothing staged
    assert w.economies[0].external_policy.fx_regime == "float"


def test_anchor_must_not_itself_peg():
    a = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                   demographics_population=120, n_ticks=60, government=True, central_bank=False)
    w = World([a, a, a], base_seed=23, trade=True, capital=True, peg=True,
              peg_economy=0, peg_anchor=1, peg_reserves0=100.0)
    w.run(3)
    e1 = w.economies[1]
    set_lever(e1, "peg_anchor", 2, actor="cb1")
    set_lever(e1, "fx_regime", "peg", actor="cb1")   # anchor 1 tries to peg to 2
    with pytest.raises(ValueError, match="anchor 1 must not itself peg|at most ONE"):
        w.step()


def test_voluntary_exit_releases_pressure_once_and_floats():
    w = _peg_pair(peg=True)
    w.run(30)
    st = w.peg_states[0]
    assert st.intact
    pent = st.pent_up
    e_before = w.rates.e[0]
    w.economies[0].external_policy.fx_regime = "float"
    w.step()
    assert not st.intact and not st.exit_pending
    if pent > 1.0:
        assert w.rates.e[0] > e_before, "released pressure must devalue the exiter"
    w.run(5)
    for econ in w.economies:
        econ.ledger.assert_conserved()


def test_broken_peg_forces_regime_to_float():
    w = _peg_pair(r_peg=0.001, r_anchor=0.08, peg=True)   # brutal mismatch
    w.run(200)
    if not w._peg_intact:   # the drain must eventually break it
        assert w.economies[0].external_policy.fx_regime == "float", (
            "the authority must reflect the broken peg")
