"""v8 acceptance tests (DESIGNDOC §21).

v8 adds household MARGIN credit: households borrow AGAINST their equity (LTV) to lever into
stocks, so borrowing brings an ASSET (not naked debt like v7 consumption credit). Leverage
concentrates capital gains (T8); a price drop triggers margin calls (fire sales). "Done":
  * margin_credit=False is bit-identical to v7 (regression);
  * MONEY (A5) and per-firm SHARE floats conserve through margin borrowing and calls;
  * borrowing brings assets -- margin debt is collateralised, so borrowers are NOT underwater
    (unlike v7 consumption debt);
  * leverage concentrates net worth in a bubble (top-share rises);
  * margin calls actually deleverage.

Run: ``uv run python tests/test_v8_margin_credit.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 60, 30, 600


def test_regression_bit_identical_off():
    """margin_credit=False reproduces v7 exactly (leverage path + calls vanish)."""
    a = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                          margin_credit=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["tobin_q_mean"] == y["tobin_q_mean"]


def test_conservation_through_margin():
    """Money A5 and per-firm share floats conserve through margin borrowing and margin calls."""
    recs = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0,
                             w_chartist=20)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_borrowing_brings_assets():
    """The margin debt is equity-collateralised, so borrowers hold an ASSET against it and are NOT
    systematically underwater -- the fix for v7's 'debt only, no asset'."""
    recs = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    tail = recs[-300:]
    assert np.mean([r["household_margin_debt"] for r in tail]) > 0.0, "no margin borrowing happened"
    # unlike v7 consumption debt (which drove households underwater), most stay solvent on full NW
    assert np.mean([r["share_margin_underwater"] for r in tail]) < 0.5


def test_leverage_concentrates_in_bubble():
    """Leverage amplifies capital gains: in a bubble the top decile's share of (cash+equity−debt)
    net worth is materially higher than in the calm regime -- the T8 mechanism."""
    calm = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             w_chartist=0.2)).run()
    bubble = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                               w_chartist=20)).run()
    top_calm = np.mean([r["hh_full_networth_top10"] for r in calm[-300:]])
    top_bubble = np.mean([r["hh_full_networth_top10"] for r in bubble[-300:]])
    # direction is robust (magnitude grows with scale: ~+0.20 at 800 households, §21)
    assert top_bubble > top_calm + 0.01, f"leverage did not concentrate: {top_calm:.2f} -> {top_bubble:.2f}"


def test_margin_calls_deleverage():
    """A leveraged bubble produces margin calls -- forced repayment (fire sales)."""
    recs = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             w_chartist=20)).run()
    assert sum(r["margin_deleveraged"] for r in recs) > 0.0, "no margin calls ever fired"


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
