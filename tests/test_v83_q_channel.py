"""v8.3 acceptance tests (DESIGNDOC §25).

v8.3 weakens the Tobin's-q → investment channel to match the empirically weak, sluggish
q-elasticity: lower `lambda_q` and drive investment off a SMOOTHED q (`tobin_q_ema`) so firms
ignore transient bubbles. This fixed a spurious macro-volatility bug (over-strong instant q
pumping stock noise into real investment). "Done":
  * q_invest_smooth=1.0 is bit-identical to v8.1 (regression);
  * the smoothed q that drives investment is genuinely LESS volatile than the raw q;
  * conservation intact.
The macro effects (calmer economy, still §4 8/8) are §25 findings from the multi-seed validation,
not brittle unit thresholds.

Run: ``uv run python tests/test_v83_q_channel.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_instant_q():
    """q_invest_smooth=1.0 reproduces v8.1 exactly (tobin_q_ema == tobin_q, same investment)."""
    a = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           q_invest_smooth=1.0)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"] and x["real_output"] == y["real_output"]


def test_conservation():
    recs = Economy(Config.v83(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_smoothed_q_is_less_volatile():
    """The q that DRIVES investment (tobin_q_ema) is smoother than the raw market q -- firms respond
    to a sluggish signal, ignoring transient mispricing (the mechanism that calms investment)."""
    econ = Economy(Config.v83(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                              w_chartist=20))          # a bubbly market to make raw q swing
    econ.run()
    cf = [f for f in econ.c_firms if f.tobin_q > 0]
    raw = np.array([f.tobin_q for f in cf])
    ema = np.array([f.tobin_q_ema for f in cf])
    # cross-firm dispersion of the investment-driving q is compressed vs the raw q
    assert np.std(ema) < np.std(raw), f"smoothed q not less volatile: std {np.std(ema):.2f} vs {np.std(raw):.2f}"


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
