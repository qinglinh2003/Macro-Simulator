"""v10.2 acceptance tests (DESIGNDOC §34).

v10.2 makes the wealth tax PROGRESSIVE: a threshold (exemption = wealth_allowance · mean net worth) so only
above-average wealth is taxed. The flat tax taxed even zero/low-net-worth hand-to-mouth households, destroying
their demand; the threshold spares them. "Done":
  * wealth_allowance=0 ⇒ bit-identical to v10.1 (regression -- prior configs untouched);
  * money (A5) + shares still conserve (still household→GOV transfers);
  * the threshold REDUCES the tax burden (it exempts sub-threshold households) at the same rate;
  * it is PRO-POOR: at the same rate, progressive lifts bottom-decile consumption vs the flat tax.
The full distributional verdict (u down, income poverty halved, concentration cut MORE) is the §34 multi-seed
finding, not a brittle unit threshold.

Run: ``uv run python tests/test_v102_progressive_wealth.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """wealth_allowance=0 reproduces v10.1 exactly (the flat-tax path is untouched)."""
    a = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                            wealth_allowance=0.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["tax_wealth"] == y["tax_wealth"]
        assert x["hh_wealth_gini_incl_equity"] == y["hh_wealth_gini_incl_equity"]


def test_conservation():
    """Progressive wealth tax is still household→GOV transfers (no new money): A5 + shares conserve."""
    recs = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_threshold_reduces_burden():
    """The exemption spares sub-threshold households, so at the SAME rate a progressive wealth tax collects
    strictly LESS revenue than the flat tax (only above-average wealth pays)."""
    W = 400
    flat = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0,
                               tax_wealth_rate=0.01, wealth_allowance=0.0)).run()
    prog = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0,
                               tax_wealth_rate=0.01, wealth_allowance=1.0)).run()
    tw_flat = np.mean([r["tax_wealth"] for r in flat[-W:]])
    tw_prog = np.mean([r["tax_wealth"] for r in prog[-W:]])
    assert tw_prog < tw_flat, f"threshold should exempt sub-mean households: prog={tw_prog:.1f} vs flat={tw_flat:.1f}"


def test_progressive_is_pro_poor():
    """At the same wealth-tax rate, the threshold lifts bottom-decile consumption vs the flat tax -- because
    the flat tax was taxing (and demand-destroying) cash-poor small savers. 2 seeds for a stable read."""
    W = 400
    def bot10(allow, seed):
        recs = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1500, seed=seed,
                                   tax_wealth_rate=0.02, wealth_allowance=allow)).run()
        return np.mean([r["bottom10_consumption"] for r in recs[-W:]])
    flat = np.mean([bot10(0.0, s) for s in (0, 1)])
    prog = np.mean([bot10(1.0, s) for s in (0, 1)])
    assert prog > flat, f"progressive should protect the poor: bottom-decile prog={prog:.3f} vs flat={flat:.3f}"


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
