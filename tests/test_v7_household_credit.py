"""v7 acceptance tests (DESIGNDOC §20; PLAN_v7).

v7 adds household credit: households borrow to defend a subsistence consumption floor, financed
by the bank (loans create deposits), recycling savers' deposits into spenders' demand. "Done"
(v7a) = the machinery works and conserves:
  * household_credit=False is bit-identical to v4 (regression);
  * MONEY (A5) conserves through household borrowing AND debt service;
  * a binding subsistence floor makes households borrow, and the credit funds consumption;
  * the debt-to-income limit keeps borrowing bounded (deposits stay non-negative, A4);
  * balance-sheet inequality appears (some households go net-debtor / underwater).
The prosperity result (credit dissolving the thrift paradox) is a §20 finding, shown in the
acceptance experiment, not a brittle per-tick threshold.

Run: ``uv run python tests/test_v7_household_credit.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 60, 30, 600
CMIN = 1.6                               # subsistence floor above typical income -> credit binds


def test_regression_bit_identical_off():
    """household_credit=False reproduces v4 exactly (no borrowing path taken)."""
    a = Economy(Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                          household_credit=False, hh_subsistence=1.5)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["hh_money"] == y["hh_money"]


def test_a5_through_household_credit():
    """A5 (money) conserves through household borrowing and debt service."""
    recs = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             hh_subsistence=CMIN)).run()
    assert max(r["conservation_drift"] for r in recs) < TOL


def test_credit_funds_consumption():
    """A binding subsistence floor makes households borrow, and the new credit funds consumption."""
    recs = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             hh_subsistence=CMIN)).run()
    assert sum(r["household_credit_new"] for r in recs) > 0.0, "no household ever borrowed"
    # credit funded consumption at some point (over the run; a binding floor may later max out at
    # the debt limit -- see §20's debt-trap finding, so we do not require tail-sustained borrowing).
    assert max(r["consumption_credit_share"] for r in recs) > 0.0


def test_debt_bounded_and_deposits_nonnegative():
    """The debt-to-income limit keeps debt finite; A4 (non-negative deposits) still holds
    (borrowing raises cash first, so nobody spends money they don't have)."""
    econ = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             hh_subsistence=CMIN))
    recs = econ.run()                    # would raise on an A4/A5 violation mid-run
    assert all(np.isfinite(r["household_debt_total"]) for r in recs)
    assert all(econ.ledger.balance(h.id) >= -TOL for h in econ.households)


def test_net_debtors_in_stressed_regime():
    """Balance-sheet inequality is REGIME-DEPENDENT (§20): in a healthy economy credit is mild
    and even lifts the bottom (demand boost), but in a STRESSED regime (endogenous MPC drains
    households) it produces net-debtor households (negative net worth) -- and, pushed further, the
    debt trap. Force the stressed regime via an experimental override (base config untouched)."""
    recs = Economy(Config.v7(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             d_household0=1.0, hh_subsistence=1.5)).run()   # cash-poor + binding floor
    assert np.mean([r["share_underwater"] for r in recs[-300:]]) > 0.05, "no net-debtors even when cash-short"


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
