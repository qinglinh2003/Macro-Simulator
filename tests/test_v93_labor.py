"""v9.3 acceptance tests (DESIGNDOC §32).

v9.3 adds LABOR welfare, targeting the employment channel §31 identified as the driver of bottom-tail
welfare. Two levers:
  * min_wage -- a statutory wage floor, now WIRED in plan_wage (it binds immediately, bypassing Calvo);
  * a JOB GUARANTEE -- the government hires every household's residual (unemployed) labour at a
    transitional JG wage, UNCAPPED (a buffer stock), paid as outside money (like the benefit); the
    public-works labour builds public capital (reusing the v9.1 K_pub channel).
"Done":
  * job_guarantee=False & min_wage=0 ⇒ bit-identical to v9.2 (regression -- prior configs untouched);
  * money (A5) + shares still conserve (JG pays outside money like the dole; K_pub is a REAL stock);
  * the buffer stock absorbs the residual -- EFFECTIVE (no-income) unemployment ≈ 0 even where PRIVATE
    unemployment stays high (the T4 metric is left untouched -- firm-side);
  * the public-works channel builds extra K_pub (jg_productivity>0 vs =0);
  * the min_wage floor actually binds (raises the average wage vs min_wage=0).
The welfare verdict (v9.3 vs v9.2 on poverty / bottom-decile consumption) is the §32 multi-seed finding,
not a brittle unit threshold.

Run: ``uv run python tests/test_v93_labor.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """job_guarantee=False & min_wage=0 reproduces v9.2 exactly (both levers inert)."""
    a = Economy(Config.v92(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           job_guarantee=False, min_wage=0.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["price_index"] == y["price_index"]
        assert x["unemployment_rate"] == y["unemployment_rate"]


def test_conservation():
    """The JG pays OUTSIDE money (GOV -> household, like the benefit) and its output is a REAL stock
    (public capital) -- so A5 (money) and per-firm shares still conserve."""
    recs = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_buffer_stock_absorbs_unemployment():
    """On the v9 stack (persistent private slack, u~0.3), the uncapped JG absorbs the residual: EFFECTIVE
    (no-income) unemployment falls to ≈ 0. (A ~1e-4 floor remains from the firm-side/household-side labor
    accounting -- the buffer stock is a household-side program, the private u metric is firm-side.)"""
    W = 200
    recs = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             job_guarantee=True, jg_wage_ratio=0.5, jg_productivity=0.5)).run()
    eff_u = np.mean([r["effective_unemployment"] for r in recs[-W:]])
    jg_emp = np.sum([r.get("jg_employment", 0.0) for r in recs])
    assert jg_emp > 0.0, "job guarantee never hired anyone"
    assert eff_u < 5e-3, f"buffer stock should clear no-income unemployment: eff_u={eff_u:.4f}"


def test_public_works_build_capital():
    """The public-works channel: with the JG active (the slack v9 stack), jg_productivity>0 builds public
    capital while jg_productivity=0 (a pure income floor, no gov investment on v9) leaves K_pub at 0. We take
    the PEAK over the run: on v9 the JG's wage injection reflates demand to full employment, after which the
    buffer empties and the early-built K_pub depreciates away -- so the accumulation shows in the peak, not
    the tail. (On v9, γ=0, so this K_pub is inert -- the mechanism, not a productivity effect, is the point.)"""
    build = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0,
                              job_guarantee=True, jg_wage_ratio=0.5, jg_productivity=0.5)).run()
    floor = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0,
                              job_guarantee=True, jg_wage_ratio=0.5, jg_productivity=0.0)).run()
    k_build = max(r.get("public_capital", 0.0) for r in build)
    k_floor = max(r.get("public_capital", 0.0) for r in floor)
    assert k_build > k_floor + 1.0, f"public works should build K_pub: peak prod>0={k_build:.0f} vs prod=0={k_floor:.0f}"


def test_min_wage_floor_binds():
    """The wired min_wage is a real floor: a high statutory minimum raises the average wage relative to
    min_wage=0 at the same seed (the lever was a no-op before v9.3, §31.4)."""
    W = 200
    w0 = Config.v92().w_firm0
    high = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0,
                              job_guarantee=False, min_wage=3.0 * w0)).run()
    zero = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0,
                              job_guarantee=False, min_wage=0.0)).run()
    w_high = np.mean([r["avg_wage"] for r in high[-W:]])
    w_zero = np.mean([r["avg_wage"] for r in zero[-W:]])
    assert w_high >= 3.0 * w0 * 0.95, f"floor should lift wages to ~min_wage: avg={w_high:.2f}, floor={3.0*w0:.2f}"
    assert w_high > w_zero, f"min_wage floor should raise the average wage: {w_high:.2f} vs {w_zero:.2f}"


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
