"""v6.2 acceptance tests (DESIGNDOC §19).

v6.2 adds equity finance: a q>1 firm issues new shares (extra sell-side supply in its own
market) to raise capex funds -- the DIRECT financial→real channel. "Done" = it is built,
conserves, and is bounded:
  * equity_finance=False is bit-identical to v6.1 (regression);
  * MONEY (A5) and per-firm SHARE floats both conserve through issuance;
  * dilution is bounded (no share-count runaway);
  * firms actually raise cash when q>1.
The FINDING (equity finance is a weak, demand-constrained, stabilising channel -- it does NOT
transmit bubbles to real investment) is recorded in §19, not asserted as a threshold.

Run: ``uv run python tests/test_v62_equity_finance.py``.
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


def test_regression_bit_identical_off():
    """equity_finance=False reproduces v6.1b exactly (issuance vanishes)."""
    a = Economy(Config.v61b(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v62(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                           equity_finance=False, lambda_issue=0.0)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"]
        assert x.get("shares_outstanding_total") == y.get("shares_outstanding_total")


def test_conservation_through_issuance():
    """Money A5 and per-firm share floats both conserve while firms issue shares."""
    recs = Economy(Config.v62(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                              w_chartist=20, lambda_issue=0.5)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL
    assert max(r["shares_conservation_drift"] for r in recs) < TOL


def test_dilution_is_bounded():
    """Issuance is tied to book (not share count) and capped per tick -> no float runaway."""
    recs = Economy(Config.v62(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                              w_chartist=20, lambda_issue=2.0)).run()
    tot = [r["shares_outstanding_total"] for r in recs[100:]]
    assert max(tot) / max(1e-9, min(tot)) < 10.0, "share float ran away (dilution spiral)"


def test_firms_raise_capital_when_overvalued():
    """When q>1 (bubble), firms actually raise cash via issuance (the channel is live)."""
    recs = Economy(Config.v62(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                              w_chartist=20, lambda_issue=0.5)).run()
    assert sum(r.get("equity_raised", 0.0) for r in recs) > 0.0


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
