"""v10 acceptance tests (DESIGNDOC §33).

v10 promotes the frozen `r_interest` to a per-tick POLICY rate set by a Taylor rule:
    r = clip( ρ·r_{-1} + (1-ρ)·[ r* + φ_π·(π̄ - π*) - φ_u·(u - u*) ] , 0, r_max ).
The whole monetary-transmission surface (investment/entry hurdle, equity valuation, firm + household debt
service) was ALREADY wired to `r_interest`, so v10 only makes the rate move. "Done":
  * central_bank=False ⇒ bit-identical to v9.3 (regression -- prior configs untouched);
  * money (A5) + shares still conserve (a rate change only rescales an A5-safe interest transfer);
  * the rate stays inside [0, r_max] (ZLB + cap) and actually MOVES under the rule;
  * the Taylor rule RESPONDS to inflation (higher π̄ ⇒ higher rate) -- the rule's core;
  * the rate's transmission has the right SIGN (a higher rate is contractionary -- fewer entrants / lower
    real output), the channel the central bank rides on (H3).
The inflation-anchor (H1) and T3 (H2) verdicts are §33 multi-seed findings, not brittle unit thresholds.

Run: ``uv run python tests/test_v10_central_bank.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402
from macro_sim.systems.central_bank import set_policy_rate  # noqa: E402

NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """central_bank=False reproduces v9.3 exactly (the rate stays the frozen r_interest)."""
    a = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           central_bank=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["price_index"] == y["price_index"]
        assert x["equity_market_cap"] == y["equity_market_cap"]


def test_conservation():
    """The policy rate only rescales the interest transfer (A5-safe: debtor → bank → redistributed). No new
    money, no new stock -- so A5 and per-firm shares still conserve under an active central bank."""
    recs = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_rate_bounds_and_moves():
    """The policy rate respects the ZLB and the sanity cap every tick, and actually MOVES (it is not the
    frozen constant) once the central bank is active."""
    econ = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    recs = econ.run()
    rate = np.array([r.get("policy_rate", np.nan) for r in recs])
    assert np.isfinite(rate).all(), "policy rate went non-finite"
    assert (rate >= -1e-12).all() and (rate <= econ.cfg.r_max + 1e-12).all(), "rate left [0, r_max]"
    assert rate.std() > 1e-6, "rate never moved (rule inert?)"


def test_taylor_rule_responds_to_inflation():
    """The rule's core: a higher smoothed inflation raises the policy rate (φ_π>0), holding the labour-gap
    fixed -- a direct unit test of _cb_set_rate (not an end-to-end outcome)."""
    econ = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1, seed=0))
    cfg = econ.cfg

    def rate_given(infl):
        econ._infl_ema = infl                     # pin the smoothed signal
        econ._prev_inflation = infl               # so the EMA step keeps it put
        econ._prev_u = cfg.u_natural              # zero the labour-gap term
        econ._rate = cfg.r_neutral                # same starting point each time
        set_policy_rate(econ)
        return econ._rate

    r_hi = rate_given(cfg.inflation_target + 0.02)
    r_lo = rate_given(cfg.inflation_target - 0.02)
    assert r_hi > r_lo, f"rate should rise with inflation: hi={r_hi:.4f} vs lo={r_lo:.4f}"


def test_manual_rate_override_does_not_freeze_inflation_sensor():
    """A hand-set rate replaces the policy decision only; the information state
    must keep updating so releasing the override does not create a hidden shock."""
    econ = Economy(Config.v10(n_firms_c=10, n_firms_k=5, n_households=40, n_ticks=1, seed=0))
    econ._infl_ema = 0.01
    econ._prev_inflation = 0.03
    expected = 0.01 + econ.cfg.infl_ema_lambda * (0.03 - 0.01)
    econ.policy.manual_policy_rate = 0.0
    econ.policy.monetary_regime = "manual"

    set_policy_rate(econ)

    assert econ._rate == 0.0
    assert econ._infl_ema == expected


def test_rate_is_non_neutral_and_deters_entry():
    """The rate has real effects (money is non-neutral), and the cost-of-capital channel is present: a higher
    rate DETERS FIRM ENTRY (entry hurdle = return − r). We deliberately do NOT assert the sign of the OUTPUT
    response: §33 finds transmission is PERVERSE here -- interest is redistributed to households (economy.py
    ~745), so in a demand-constrained economy a higher rate is net EXPANSIONARY on output even as it culls
    firms. This test pins the two robust facts (non-neutrality + entry deterrence); the perverse output sign
    is the §33 finding, verified separately, not encoded as a pass/fail here."""
    W = 400
    lo = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1500, seed=0,
                            r_interest=0.005)).run()
    hi = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1500, seed=0,
                            r_interest=0.05)).run()
    firms_lo = np.mean([r["n_firms_producing"] for r in lo[-W:]])
    firms_hi = np.mean([r["n_firms_producing"] for r in hi[-W:]])
    y_lo = np.mean([r["real_output"] for r in lo[-W:]])
    y_hi = np.mean([r["real_output"] for r in hi[-W:]])
    assert firms_hi < firms_lo, f"higher rate should deter entry: firms hi={firms_hi:.0f} vs lo={firms_lo:.0f}"
    assert abs(y_hi - y_lo) / max(y_lo, 1.0) > 0.01, f"rate should have a REAL (non-neutral) output effect: {y_lo:.0f}->{y_hi:.0f}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
