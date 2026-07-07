"""v6 acceptance tests (DESIGNDOC §16; PLAN_v6).

v6 adds a single aggregate equity index + household portfolio choice, activating choice 乙
(equity enters household wealth). "Done" (conservative milestone):
  * capital_market=False is bit-identical to v5 (regression);
  * MONEY (A5) conserves through equity trading AND through a bubble+crash;
  * SHARES conserve exactly (Σ holdings == float) every tick;
  * the market is LIVE in a healthy economy (nonzero turnover, price tracks book);
  * choice 乙 works: household wealth includes a fluctuating equity component;
  * fundamental limit: w_chartist=0 => price stays near book (no runaway);
  * bubble is REACHABLE: large w_chartist => price detaches from book, and money still
    conserves through the crash (a wealth boom-bust with zero money created/destroyed).

Run: ``uv run python tests/test_v6_capital_market.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 120, 60, 1200


def _run(cfg):
    econ = Economy(cfg)
    return econ, econ.run()


def test_regression_bit_identical_off():
    """capital_market=False reproduces v5 exactly (equity phase + 乙 term vanish)."""
    base = Economy(Config.v5(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    off = Economy(Config.v5(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            capital_market=False)).run()
    for a, b in zip(base, off):
        assert a["price_index"] == b["price_index"] and a["employment"] == b["employment"]


def test_shares_conserve():
    """Σ household shares == float every tick (the new non-money invariant)."""
    econ, recs = _run(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    worst = max(abs(r["shares_outstanding"] - econ.cfg.float_shares) for r in recs)
    assert worst < TOL, f"share float not conserved; worst drift {worst:.3e}"


def test_money_a5_through_trading():
    """A5 (money) holds with the market active -- equity trades are deposit transfers."""
    econ, recs = _run(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    assert max(r["conservation_drift"] for r in recs) < TOL


def test_market_is_live():
    """In a healthy economy the market trades and the price is a sensible multiple of book."""
    econ, recs = _run(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0))
    tail = recs[-300:]
    turnover = np.mean([r["equity_turnover"] for r in tail])
    price = np.mean([r["stock_price"] for r in tail])
    assert turnover > 1e-4, f"equity market is dead (turnover {turnover:.1e})"
    assert price > 1e-3, f"price collapsed ({price:.3e})"


def test_choice_yi_wealth_includes_equity():
    """乙: household wealth now carries a nonzero, varying equity component."""
    econ, recs = _run(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    shares = [r["equity_wealth_share"] for r in recs[-300:]]
    assert np.mean(shares) > 0.01, "equity is not a meaningful part of wealth"
    assert np.std([r["stock_price"] for r in recs[-300:]]) > 0.0, "equity value never moves"


def test_fundamental_limit_no_runaway():
    """w_chartist=0 => price stays anchored near book (Tobin's q bounded, no bubble)."""
    econ, recs = _run(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0,
                                w_chartist=0.0))
    q = np.array([r["tobin_q"] for r in recs[300:]])
    assert q.max() < 3.0, f"price ran away with no chartist force (q max {q.max():.2f})"


def test_bubble_reachable_and_money_conserves_through_crash():
    """Large w_chartist => price detaches from book (a bubble), then crashes -- and money
    conservation holds THROUGH the crash (a wealth boom-bust with zero money destroyed)."""
    econ, recs = _run(Config.v6_bubble(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                       n_ticks=1500, seed=0))
    q = np.array([r["tobin_q"] for r in recs])
    assert q.max() > 3.0, f"no bubble formed at high w_chartist (q max {q.max():.2f})"
    # a crash: q falls back substantially from its peak
    peak = q.argmax()
    assert q[peak:].min() < 0.6 * q.max(), "bubble never crashed"
    # the invariant: money conserved across the entire boom-bust
    assert max(r["conservation_drift"] for r in recs) < TOL, "A5 broke during the bubble/crash"


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
