"""v3 acceptance tests (DESIGNDOC §12.8; PLAN_v3 §6).

The four things that make v3 trustworthy:
  * net-worth conservation A5 (ΣD − ΣL = M) to machine precision every tick;
  * broad money ΣD is *endogenous* — a live series, not the flat M0 line;
  * credit does work — it is created (loans grow ΣD) and funds wage bills (A4's
    credit term is live), logged by purpose;
  * the leverage rule (B7) caps new borrowing, and the run stays bounded.

Run: ``uv run python tests/test_v3_credit.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from behavior import credit_grant           # noqa: E402
from config import Config                    # noqa: E402
from economy import Economy                  # noqa: E402

TOL = 1e-6


def _run(**kw):
    econ = Economy(Config.v3(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=2000, seed=0, **kw))
    return econ, econ.run()


def test_a5_conservation_every_tick():
    econ, recs = _run()
    M = econ.ledger.genesis_money
    worst = max(r["conservation_drift"] for r in recs)   # = |net_worth − M|
    assert worst < TOL, f"A5 (ΣD−ΣL=M) violated; worst drift {worst:.3e}"
    assert abs(econ.ledger.net_worth - M) < TOL


def test_broad_money_is_endogenous():
    """ΣD must MOVE (credit expands/contracts) while net worth stays pinned to M —
    the flat line coming alive is the signature of a credit economy (§12.8)."""
    econ, recs = _run()
    bm = [r["broad_money"] for r in recs]
    nw = [r["net_worth"] for r in recs]
    assert max(bm) - min(bm) > 1.0, "broad money should vary (credit is inert?)"
    assert max(bm) > econ.ledger.genesis_money + 1.0, "broad money should exceed M (credit creates deposits)"
    assert max(nw) - min(nw) < TOL, "net worth must stay flat at M"


def test_credit_is_created_and_funds_wages():
    """Loans are actually made (ΣL>0), and credit funds wage bills — A4's credit term
    is doing work (the working-capital relief §11.5 predicted)."""
    econ, recs = _run()
    total_new_loans = sum(r["new_loans"] for r in recs)
    total_wage_credit = sum(r["credit_wage"] for r in recs)
    assert total_new_loans > 0.0, "no loans were ever made"
    assert econ.ledger.total_credit > 0.0, "no outstanding credit at end"
    assert total_wage_credit > 0.0, "credit never funded wages (working-capital channel dead)"


def test_credit_grant_respects_leverage_cap():
    """B7 (pure): granted credit never pushes debt above kappa·NW; insolvent => 0."""
    kappa = 3.0
    # request more than allowed; NW = D − L = 100
    g = credit_grant(requested=999.0, deposits=100.0, debt=0.0, kappa=kappa)
    assert abs(g - 300.0) < TOL, f"cap should be kappa*NW=300, got {g}"
    # existing debt eats into headroom: room = kappa*NW − L = 3*(100−40) − 40 = 140
    g2 = credit_grant(requested=999.0, deposits=100.0, debt=40.0, kappa=kappa)
    assert abs(g2 - 140.0) < TOL, f"headroom should be 140, got {g2}"
    # insolvent (NW<=0) => no credit
    assert credit_grant(999.0, deposits=30.0, debt=30.0, kappa=kappa) == 0.0
    assert credit_grant(999.0, deposits=10.0, debt=50.0, kappa=kappa) == 0.0
    # request below cap is honored in full
    assert abs(credit_grant(25.0, deposits=100.0, debt=0.0, kappa=kappa) - 25.0) < TOL


def test_bounded_not_diverging():
    """Credit is positive feedback; at the default kappa the run must stay bounded
    (broad money not exploding, output finite)."""
    econ, recs = _run()
    M = econ.ledger.genesis_money
    bm = [r["broad_money"] for r in recs]
    out = [r["real_output"] for r in recs]
    assert max(bm) < 100 * M, f"broad money exploded: max {max(bm):.0f} vs M {M:.0f}"
    assert all(o == o and o < 1e6 for o in out), "output diverged / non-finite"


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
