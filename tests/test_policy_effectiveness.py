"""v25 P0 scaffold: per-lever effectiveness tests.

The pattern the audits demanded: mutate ONLY econ.policy mid-run (never Config)
and assert behaviour responds. A digest gate cannot catch dead fields; this can.

Scaffold contents:
- helper `run_ab(lever_mutation, ticks, observe)` — same-seed twin economies,
  policy mutated on one arm at mid-run
- LIVE levers: proven effective here (first exemplars; grows per migration)
- KNOWN DEFECTS (design doc section 1.7): encoded as xfail — they FLIP to green
  when the defect is fixed, keeping the defect list executable."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.economy import Economy


def _econ():
    return Economy(Config.v13(
        seed=17, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=2,
        demographics_population=260, n_ticks=400,
        government=True, gov_consumption_share=0.10, tax_income_rate=0.10,
        tax_consumption_rate=0.10, central_bank=True, inflation_target=5.4e-5,
        # NOTE: Config.v13 presets gov_deficit_target=0.03 -- the deficit branch is
        # ACTIVE here, which the shadowing tests below rely on.
    ))


def run_ab(mutate, ticks=240, split=120, observe=lambda e: None):
    """Same-seed twin: arm B gets `mutate(policy)` at `split`. Returns (obs_a, obs_b)."""
    a, b = _econ(), _econ()
    for t in range(ticks):
        if t == split:
            mutate(b.policy)
        a.step()
        b.step()
    return observe(a), observe(b)


# ---------------- live levers (exemplars; list grows with each migration) --------------

def test_tax_income_rate_is_runtime_effective():
    tax_a, tax_b = run_ab(lambda p: setattr(p, "tax_income_rate", 0.30),
                          observe=lambda e: sum(r.get("tax_total", 0.0) for r in e.records[-100:]))
    assert tax_b > tax_a * 1.05, "raising income tax mid-run must raise revenue"


def test_gov_consumption_share_is_runtime_effective_when_not_shadowed():
    # PRECEDENCE TRAP (found by this scaffold, first hour of P0): the deficit-target
    # branch shadows the share branch, and Config.v13() presets gov_deficit_target=0.03,
    # so the share lever is silently inert in every v13-family config -- including the
    # 30y portraits (defc>0 archetypes: China/India/USA). The registry gains a
    # `shadowed_by` declaration; this test exercises the UNSHADOWED path.
    def mutate(p):
        p.gov_deficit_target = 0.0        # un-shadow
        p.gov_consumption_share = 0.25
    g_a, g_b = run_ab(mutate,
                      observe=lambda e: sum(r.get("gov_consumption", 0.0) for r in e.records[-100:]))
    assert g_b != pytest.approx(g_a), "un-shadowed share change must alter gov consumption"


def test_gov_consumption_share_is_shadowed_by_deficit_target():
    """Documents the precedence: while gov_deficit_target>0 the share lever is a NO-OP.
    This is the registry's `shadowed_by` semantics made executable."""
    g_a, g_b = run_ab(lambda p: setattr(p, "gov_consumption_share", 0.25),
                      observe=lambda e: sum(r.get("gov_consumption", 0.0) for r in e.records[-100:]))
    assert g_b == pytest.approx(g_a), "share mutation must be inert under an active deficit target"


def test_policy_rate_override_is_runtime_effective():
    r_a, r_b = run_ab(lambda p: setattr(p, "policy_rate_override", 0.0005),
                      observe=lambda e: e.records[-1].get("policy_rate", 0.0))
    assert r_b == pytest.approx(0.0005), "the override must pin the policy rate"
    assert r_b != r_a


# ---------------- KNOWN DEFECTS (design doc 1.7) — xfail until fixed -------------------

@pytest.mark.xfail(reason="1.7: Policy.central_bank is a DEAD FIELD (rate path reads cfg); "
                          "flips green when monetary_regime lands", strict=True)
def test_policy_central_bank_flag_is_runtime_effective():
    # turning the CB OFF mid-run should freeze the rate at r_interest; today it does nothing
    r_a, r_b = run_ab(lambda p: setattr(p, "central_bank", False),
                      observe=lambda e: e.records[-1].get("policy_rate", 0.0))
    assert r_b != r_a
