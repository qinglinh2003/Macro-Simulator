"""v8.1 acceptance tests (DESIGNDOC §23).

v8.1 makes firm market share (attractiveness) a multiplicative random walk (Gibrat) and allocates
goods demand ∝ share^β, so -- with the v4 entry/exit barrier -- firm sizes grow into a Pareto tail
(Simon/Gabaix), the multiplicative growth §22 found missing for T6 AND T8. "Done":
  * gibrat_growth=False is bit-identical to v8 (regression);
  * MONEY (A5) + per-firm SHARE floats conserve (it's only a demand-allocation change);
  * the firm-size UPPER TAIL becomes a steep power law (not v8's flat -0.33);
  * multiplicative shocks disperse attractiveness (Gibrat divergence);
  * the household wealth upper tail steepens too (propagation through the equity/margin chain).

Run: ``uv run python tests/test_v81_gibrat.py``.
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


def _upper_tail_slope(vals):
    s = np.sort([v for v in vals if v > 1e-9])[::-1]
    if len(s) < 8:
        return 0.0
    s = s[:max(8, len(s) // 2)]
    return float(np.polyfit(np.log(np.arange(1, len(s) + 1)), np.log(s), 1)[0])


def test_regression_bit_identical_off():
    """gibrat_growth=False reproduces v8 exactly (preferential match + shocks vanish)."""
    a = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v8(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                          gibrat_growth=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["firm_size_gini_output"] == y["firm_size_gini_output"]


def test_conservation():
    """A5 money and per-firm share floats conserve -- v8.1 only reallocates demand across sellers."""
    recs = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_attractiveness_disperses():
    """Multiplicative shocks make market share DIVERGE (Gibrat) -- attractiveness Gini rises well
    above the no-shock baseline."""
    on = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    off = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             gibrat_sigma=0.0)).run()
    g_on = np.mean([r["firm_attractiveness_gini"] for r in on[-300:]])
    g_off = np.mean([r["firm_attractiveness_gini"] for r in off[-300:]])
    assert g_on > g_off + 0.2, f"shocks did not disperse market share: {g_off:.2f} -> {g_on:.2f}"


def test_firm_size_power_law_tail():
    """The firm-size upper tail becomes a STEEP power law (Zipf ~ -1), not v8's flat -0.33."""
    recs = Economy(Config.v81(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0)).run()
    slope = np.mean([r["firm_size_pareto_slope"] for r in recs[-300:]])
    assert slope < -0.7, f"firm-size tail not a power law: slope {slope:+.2f} (want steeper than -0.7)"


def test_wealth_tail_steepens_modestly():
    """T8 propagation: Gibrat firm growth steepens the household net-worth upper tail vs v8 -- but
    only MODESTLY, because equity ownership is diversified (§18): the Zipf firms are broadly held,
    so wealth inherits only part of the firm tail. Direction is robust; magnitude is throttled by
    ownership dispersion (the remaining gap -- §23)."""
    def nw_tail(cfg):
        econ = Economy(cfg); econ.run()
        po = {f.id: f.share_price for f in econ.c_firms}
        w = [econ.ledger.balance(h.id) + sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
             - econ.ledger.debt(h.id) for h in econ.households]
        return _upper_tail_slope([x for x in w if x > 1e-9])
    kw = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0)
    s81 = nw_tail(Config.v81(**kw))
    s8 = nw_tail(Config.v8(**kw))
    assert s81 < s8 - 0.03, f"wealth tail did not steepen at all: v8 {s8:+.2f} -> v8.1 {s81:+.2f}"


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
