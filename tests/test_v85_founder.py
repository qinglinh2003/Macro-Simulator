"""v8.5 acceptance tests (DESIGNDOC §27).

v8.5 vests the genesis share float in a minority founder class instead of splitting it equally among
all watchers, so a few households start with concentrated blocks -- the structural lever for the T8
wealth tail. "Done":
  * founder_owned_genesis=False is bit-identical to v8.4 (regression -- prior configs untouched);
  * money + per-firm share floats still conserve exactly;
  * at genesis, equity ownership is far MORE concentrated than the diffuse (equal-split) baseline.
Whether that concentration PERSISTS (vs erodes via rebalancing) is a §27 finding from the multi-seed
run, not a unit threshold.

Run: ``uv run python tests/test_v85_founder.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402
from macro_sim.reporting.metrics import gini                 # noqa: E402

TOL = 1e-6
NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_flag_off():
    """founder_owned_genesis=False reproduces v8.4 exactly (equal-split genesis untouched)."""
    a = Economy(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v85(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           founder_owned_genesis=False)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"] and x["real_output"] == y["real_output"]


def test_conservation():
    recs = Economy(Config.v85(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_genesis_ownership_more_concentrated():
    """At t=0 the founder-class allocation is far more concentrated than the diffuse equal split."""
    def genesis_owner_gini(cfg):
        econ = Economy(cfg)               # constructed but NOT run: read the t=0 allocation
        eq = []
        for h in econ.households:
            eq.append(sum(sh for sh in h.holdings.values()))
        return gini(eq)
    diffuse = genesis_owner_gini(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, seed=0))
    founder = genesis_owner_gini(Config.v85(n_firms_c=NC, n_firms_k=NK, n_households=NH, seed=0))
    assert founder > diffuse + 0.2, f"founder genesis not more concentrated: founder={founder:.3f} diffuse={diffuse:.3f}"


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
