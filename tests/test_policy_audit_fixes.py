"""User audit round (2026-07-18): six defect classes, each with the reported repro.

1. loose numeric validation (str/bool/fractional accepted)  -> strict typed validators
2. stale-vector validation order + non-atomic barrier commit -> commit-then-validate
3. no atomic multi-lever decision                            -> apply_action_batch
4. action log economy id wrong + unlogged mutations          -> economy_id + single writer
5. capability vs policy-state gating conflated               -> requires / enabled_if
6. PolicySeed incomplete                                     -> full initial_policy + version
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.core.policy import PolicySeed, POLICY_SCHEMA_VERSION
from macro_sim.core.policy_registry import REGISTRY, apply_action_batch, set_lever
from macro_sim.economy import Economy
from macro_sim.world.world import World


def _econ(**over):
    base = dict(seed=41, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                demographics_population=120, n_ticks=40, government=True)
    e = Economy(Config.v13(**{**base, **over}))
    for _ in range(3):
        e.step()
    return e


def _world(n=2, **kw):
    cfg = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                     demographics_population=120, n_ticks=60, government=True)
    return World([cfg] * n, base_seed=5, trade=True, migration=True, **kw)


# ---- 1. strict typed validation (the exact reported repros) ----

def test_string_float_rejected():
    e = _econ()
    with pytest.raises(ValueError, match="not a number"):
        set_lever(e, "tax_income_rate", "0.2")
    assert not isinstance(e.policy.tax_income_rate, str)


def test_fractional_int_rejected():
    e = _econ(bonds=True, bond_finance_frac=0.3)
    with pytest.raises(ValueError, match="not an integer"):
        set_lever(e, "bond_maturity", 1.5)


def test_string_economy_id_rejected():
    w = _world()
    with pytest.raises(ValueError, match="not an economy id"):
        set_lever(w.economies[0], "peg_anchor", "1")


def test_bool_and_nonfinite_rejected():
    e = _econ()
    with pytest.raises(ValueError, match="not a number"):
        set_lever(e, "tax_income_rate", True)
    with pytest.raises(ValueError, match="not finite"):
        set_lever(e, "tax_income_rate", float("nan"))


# ---- 2. commit/validate ordering + legal mixed vectors + aligned bounds ----

def test_mixed_cap_vector_is_legal_and_immediate():
    """The reported repro: emigration_cap on ONE economy only. Must be accepted,
    committed at the next barrier, and never rejected by the domain validator."""
    w = _world()
    w.run(2)
    set_lever(w.economies[1], "emigration_cap", 0.5, actor="gov1")
    w.step()                       # commit happens BEFORE validation now
    w.step()                       # the reported crash was on the SECOND tick
    assert w.emigration_cap[1] == pytest.approx(0.5)
    assert w.emigration_cap[0] is None


def test_registry_bound_matches_world_bound():
    w = _world()
    with pytest.raises(ValueError):
        set_lever(w.economies[1], "emigration_cap", 2.0)   # World allows <= 1.0


def test_bad_value_surfaces_on_its_own_tick():
    w = _world()
    w.run(2)
    w.economies[0].external_policy.remittance_tax = 5.0    # bypass registry on purpose
    with pytest.raises(ValueError):
        w.step()                   # commit-then-validate: caught NOW, not next tick


def test_barrier_commit_is_atomic_on_peg_violation():
    w = _world(n=3, capital=True)
    w.run(2)
    tariff_before = list(w.tariff)
    # two peggers staged directly (bypassing set_lever) -> the barrier must veto
    w.economies[0].external_policy.fx_regime = "peg"
    w.economies[0].external_policy.peg_anchor = 2
    w.economies[1].external_policy.fx_regime = "peg"
    w.economies[1].external_policy.peg_anchor = 2
    w.economies[0].external_policy.tariff = 0.4
    with pytest.raises(ValueError, match="at most ONE pegger"):
        w.step()
    assert w.tariff == tariff_before, "a vetoed commit must not write ANY vector"


# ---- 3. atomic action batch ----

def test_batch_enters_manual_atomically_any_order():
    e = _econ()
    apply_action_batch(e, [("monetary_regime", "manual"),
                           ("manual_policy_rate", 3.0e-4)], actor="gov")
    assert e.policy.monetary_regime == "manual"
    assert e.policy.manual_policy_rate == pytest.approx(3.0e-4)
    ev = e._policy_action_log[-1]
    assert len(ev["actions"]) == 2 and ev["schema_version"] == 1


def test_batch_veto_leaves_everything_untouched():
    e = _econ()
    before = e.policy.tax_income_rate
    with pytest.raises(ValueError):
        apply_action_batch(e, [("tax_income_rate", 0.3),
                               ("monetary_regime", "manual")])   # no rate anywhere
    assert e.policy.tax_income_rate == before, "partial application is forbidden"
    assert not any(a.get("lever") == "tax_income_rate"
                   for ev in getattr(e, "_policy_action_log", []) for a in ev["actions"])


def test_batch_single_log_event():
    e = _econ()
    n0 = len(getattr(e, "_policy_action_log", []))
    apply_action_batch(e, [("tax_income_rate", 0.25), ("min_wage", 0.02)])
    assert len(e._policy_action_log) == n0 + 1, "one decision = one event"


# ---- 4. log economy id + world-forced transitions logged ----

def test_action_log_carries_real_economy_id():
    w = _world()
    w.run(2)
    set_lever(w.economies[1], "tariff", 0.1, actor="gov1")
    assert w.economies[1]._policy_action_log[-1]["actor_economy"] == 1


def test_peg_break_is_logged():
    cfg_p = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                       demographics_population=120, n_ticks=200, government=True,
                       r_interest=0.001, central_bank=False)
    cfg_a = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                       demographics_population=120, n_ticks=200, government=True,
                       r_interest=0.08, central_bank=False)
    w = World([cfg_p, cfg_a], base_seed=21, trade=True, capital=True,
              capital_mobility=2.0, capital_adjust=0.2, peg=True,
              peg_reserves0=50.0, peg_reserve_scale=0.05)
    w.run(200)
    if not w._peg_intact:
        events = [ev for ev in w.economies[0]._policy_action_log
                  if ev["actor"] == "world:peg_break"]
        assert events, "the forced float must appear in the action log"


# ---- 5. requires vs enabled_if ----

def test_enabled_if_reads_live_policy_not_config():
    """The reported repro: cfg.omo=False but the controller turns Policy.omo on --
    omo_index_deposits must become adjustable, in the SAME batch."""
    e = _econ(omo=False, bonds=True, interbank=True)
    assert e.policy.omo is False
    with pytest.raises(ValueError, match="requires policy omo"):
        set_lever(e, "omo_index_deposits", True)
    apply_action_batch(e, [("omo", True), ("omo_index_deposits", True)], actor="cb")
    assert e.policy.omo_index_deposits is True


# ---- 6. PolicySeed completeness ----

def test_policy_seed_full_snapshot_and_version():
    e = _econ()
    assert e.policy_seed.policy_schema_version == POLICY_SCHEMA_VERSION
    assert e.policy_seed.initial_policy is not None
    # the live policy STARTED at the seed but is not the same object
    assert e.policy is not e.policy_seed.initial_policy
    set_lever(e, "tax_income_rate", 0.31)
    assert e.policy_seed.initial_policy.tax_income_rate != 0.31, (
        "mutating the live policy must never touch the seed snapshot")


# ---- audit round 2 (v26 doc S1.2): the two integration blockers ----

def test_vetoed_commit_leaves_sanctions_cache_clean():
    """Out-of-range sanctions target: the step must raise AND the derived cache
    must stay untouched (prepare -> validate -> commit; no partial state)."""
    w = _world()
    w.run(2)
    w.economies[0].external_policy.sanctions_imposed_on = frozenset({7})
    with pytest.raises(ValueError, match="sanctions"):
        w.step()
    assert w.sanctions == set(), "a vetoed commit must not pollute the derived cache"


def test_peg_handover_selects_active_state():
    """0 exits, 1 adopts: the dead state stays for history, but every legacy
    accessor (and therefore peg_defense) must answer for the ACTIVE pegger."""
    cfgp = Config.v13(seed=0, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                      demographics_population=120, n_ticks=200, government=True,
                      central_bank=False)
    w = World([cfgp, cfgp, cfgp], base_seed=7, trade=True, capital=True,
              peg=True, peg_economy=0, peg_anchor=2, peg_reserves0=100.0)
    w.run(3)
    w.economies[0].external_policy.fx_regime = "float"
    w.economies[1].external_policy.peg_anchor = 2
    w.economies[1].external_policy.fx_regime = "peg"
    w.step()
    assert w.peg_states[1].intact and not w.peg_states[0].intact
    assert w.peg_economy == 1, "accessors must select the ACTIVE pegger, not insertion order"
    assert w.peg_anchor == 2
    assert w.peg_states[1].reserve_account_id == "CBRES:1"
    w.run(3)
    for econ in w.economies:
        econ.ledger.assert_conserved()
