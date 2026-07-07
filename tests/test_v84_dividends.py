"""v8.4 acceptance tests (DESIGNDOC §26).

v8.4 (step 1) pays dividends PRO-RATA to shareholders instead of equally per capita. In the
per-firm regime we already track who owns what (h.holdings[f.id]); paying dividends per capita was
an accounting inconsistency inherited from the v6 aggregate-index era. Pro-rata makes the cash-flow
return to equity differential (like the capital-gains channel already is): a non-owner earns zero
dividend income. "Done":
  * pro_rata_dividends=False is bit-identical to v8.3 (regression -- all prior configs untouched);
  * money + shares still conserve exactly under pro-rata;
  * pro-rata RAISES cross-household income inequality vs equal split (the mechanism -- capital income
    becomes concentrated). This is a §26 finding, pre-registered, not a brittle threshold.

Pre-registered caveat (§26): genesis firms are still diffusely held (founder-owned genesis is step 2),
so this alone is a correctness fix that barely moves the T8 wealth tail -- the income-gini lift is
modest and directional, which is what we assert.

Run: ``uv run python tests/test_v84_dividends.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_flag_off():
    """pro_rata_dividends=False reproduces v8.3 exactly (equal-split path untouched)."""
    a = Economy(Config.v83(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           pro_rata_dividends=False)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"] and x["real_output"] == y["real_output"]


def test_conservation():
    """Pro-rata payout keeps A5 (money) and per-firm share floats exact -- CLEARING drains to 0."""
    recs = Economy(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_pro_rata_raises_income_inequality():
    """The mechanism: routing each firm's dividend to ITS holders (vs an equal per-capita split)
    makes capital income differential, so cross-household income inequality is HIGHER. Compared on
    the same seed over a late window to average out tick noise; directional, not a tuned threshold."""
    W = 120
    eq = Economy(Config.v83(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=700, seed=1)).run()
    pr = Economy(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=700, seed=1)).run()
    gini_eq = np.mean([r["income_gini"] for r in eq[-W:]])
    gini_pr = np.mean([r["income_gini"] for r in pr[-W:]])
    assert gini_pr > gini_eq, f"pro-rata should raise income inequality: pro={gini_pr:.4f} eq={gini_eq:.4f}"


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
