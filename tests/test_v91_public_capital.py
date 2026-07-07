"""v9.1 acceptance tests (DESIGNDOC §29).

v9.1 adds the SUPPLY SIDE: government investment buys real capital goods (from K-firms), accumulating an
economy-wide PUBLIC capital stock K_pub that raises every firm's productivity (Barro 1990),
``Y_f = A·K_f^α·N_f^{1-α}·(1 + K_pub/K_ref)^γ``. This gives the deficit a productive outlet and flips the
government from net-negative (v9) to net-positive (real output/consumption up, u down). "Done":
  * gov_investment_share=0 & γ=0 ⇒ bit-identical to v9 (regression -- prior configs untouched);
  * money (A5) + shares still conserve (public capital is a REAL stock, not money);
  * K_pub accumulates from 0, stays FINITE (bounded steady state, not explosive);
  * with the same government investment, γ>0 raises real output vs γ=0 (the productivity channel works).
The welfare flip (v9.1 > v9 and > v8.5 on real output/consumption) is the §29 finding from the multi-seed
battery, not a brittle unit threshold.

Run: ``uv run python tests/test_v91_public_capital.py``.
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
    """gov_investment_share=0 & γ=0 reproduces v9 exactly (public-capital factor ≡ 1)."""
    a = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v91(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                           gov_investment_share=0.0, public_capital_gamma=0.0)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"] and x["real_output"] == y["real_output"]


def test_conservation():
    """Public capital is a REAL stock (like firm capital), not money -- A5 and per-firm shares still hold."""
    recs = Economy(Config.v91(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_public_capital_accumulates_and_is_finite():
    """K_pub builds from 0 (government investment) and converges to a BOUNDED steady state (I=δK), never
    explodes -- the growth is a productivity LEVEL boost, not a runaway."""
    econ = Economy(Config.v91(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1500, seed=0))
    recs = econ.run()
    kpub = np.array([r.get("public_capital", 0.0) for r in recs])
    assert kpub[100:300].mean() > 0.0, "public capital never accumulated"
    assert kpub[-1] > kpub[200], "public capital did not grow"
    assert np.isfinite(kpub).all() and kpub.max() < 1e9, "public capital exploded"
    assert np.isfinite([r["real_output"] for r in recs]).all(), "output exploded"


def test_productivity_channel_raises_output():
    """With the SAME government investment, γ>0 (public capital raises productivity) yields higher real
    output than γ=0 (investment happens but has no productivity effect)."""
    W = 400
    on = Economy(Config.v91(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=2000, seed=0)).run()
    off = Economy(Config.v91(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=2000, seed=0,
                             public_capital_gamma=0.0)).run()
    y_on = np.mean([r["real_output"] for r in on[-W:]])
    y_off = np.mean([r["real_output"] for r in off[-W:]])
    assert y_on > y_off, f"productivity channel should raise output: γ>0={y_on:.0f} vs γ=0={y_off:.0f}"


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
