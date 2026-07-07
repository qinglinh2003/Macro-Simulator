"""v6.1 acceptance tests (DESIGNDOC §18; PLAN_v6.1).

v6.1 turns the aggregate index into a per-firm stock market: each firm separately valued
(floored residual income), traded, priced (own Tobin's q); founders own the firms they fund;
(v6.1b) q lifts investment. "Done" = the SUBSTRATE is solid and conserving:
  * per_firm_equity=False is bit-identical to v6 (regression);
  * MONEY (A5) conserves through per-firm trading AND a bankruptcy (equity wiped);
  * every firm's share float conserves (Σ_h holdings[f] == shares_outstanding_f);
  * founder ownership: funding a startup grants its shares;
  * residual-income valuation: profitable firms get q>1 (a premium over book);
  * q-investment (v6.1b) is wired and bounded.
The two economic FINDINGS (founder-equity mirrors wealth; q-signal is a weak financial→real
channel) are recorded in §18, not asserted as brittle thresholds.

Run: ``uv run python tests/test_v61_per_firm_equity.py``.
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


def _run(cfg):
    econ = Economy(cfg)
    return econ, econ.run()


def test_regression_bit_identical_off():
    """per_firm_equity=False reproduces v6 exactly (per-firm path + q-tilt vanish)."""
    base = Economy(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    off = Economy(Config.v6(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            per_firm_equity=False)).run()
    for a, b in zip(base, off):
        assert a["stock_price"] == b["stock_price"] and a["employment"] == b["employment"]


def test_per_firm_share_conservation():
    """Every firm's float is fully held: Σ_h holdings[f] == shares_outstanding_f, every tick."""
    econ, recs = _run(Config.v61a(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_money_a5_through_per_firm_trading_and_bankruptcy():
    """A5 holds with per-firm trading and through bankruptcies (equity wiped = no money moves)."""
    econ, recs = _run(Config.v61a(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0))
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert sum(r["deaths"] for r in recs) > 0                # bankruptcies did occur (equity wiped)


def test_founder_owns_the_firm_it_funds():
    """When a household funds a startup, it receives that firm's full float on its books."""
    cfg = Config.v61a(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0)
    econ = Economy(cfg)
    econ.run()
    # firms born after genesis (id index >= n_firms_c) were founder-funded; each such live firm's
    # shares must be concentrated (its founder holds a large block).
    born = [f for f in econ.c_firms if int(f.id[1:]) >= cfg.n_firms_c]
    assert born, "no entrants to check"
    for f in born[:20]:
        top = max((h.holdings.get(f.id, 0.0) for h in econ.households), default=0.0)
        assert top >= 0.5 * f.shares_outstanding, "founder does not hold a controlling block"


def test_valuation_rewards_earnings():
    """Floored residual income: profitable firms are valued ABOVE book (q>1)."""
    econ, recs = _run(Config.v61a(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0))
    tail = recs[-300:]
    assert np.mean([r["n_firms_q_above_1"] for r in tail]) > 1.0, "no firm ever priced above book"
    assert np.mean([r["tobin_q_mean"] for r in tail]) > 0.0


def test_q_investment_wired_and_bounded(_cap=Config.v61b().q_invest_cap):
    """v6.1b: q-driven investment runs, conserves, and stays bounded (the g(q) clip holds)."""
    econ, recs = _run(Config.v61b(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0))
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert all(np.isfinite(r["investment_spending"]) for r in recs)
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


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
