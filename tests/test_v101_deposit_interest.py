"""v10.1 acceptance tests (DESIGNDOC §33).

v10.1 fixes the v3 bank's equal-split of collected loan interest: instead of paying every household the same
"dividend" (which paid interest even to zero-deposit hand-to-mouth households, over-strengthening the demand
channel and making low rates perversely contractionary -- the v10 hump), it pays interest to DEPOSITORS in
proportion to their deposit balance. "Done":
  * interest_by_deposits=False ⇒ bit-identical to v10 (regression -- prior configs untouched);
  * money (A5) + shares still conserve (still a single bank→household transfer, no new money);
  * the bank's interest goes to DEPOSITORS ∝ deposits (high-deposit households receive it, zero-deposit
    households receive ~nothing) -- the correctness claim (H1);
  * the flag materially changes outcomes (it is consequential, not cosmetic).
The transmission verdict (deposit-proportional restores conventional monotone-contractionary rates -- H2) is
the §33 multi-seed finding, not a brittle unit threshold.

Run: ``uv run python tests/test_v101_deposit_interest.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000
EPS = 1e-9


def test_regression_bit_identical_off():
    """interest_by_deposits=False reproduces v10 exactly (the equal-split path is untouched)."""
    a = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                            interest_by_deposits=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["hh_wealth_gini_incl_equity"] == y["hh_wealth_gini_incl_equity"]


def test_conservation():
    """Deposit-proportional interest is still a single bank→household transfer (no new money, no new stock):
    A5 (money) and per-firm shares still conserve."""
    recs = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_interest_goes_to_depositors():
    """The correctness claim (H1): the bank's interest payout accrues to depositors ∝ deposits. After a
    burn-in, exercising the debt-service phase raises household income ONLY via the bank redistribution, so the
    income delta IS each household's interest receipt. High-deposit households get the bulk; zero-deposit
    households get ~0."""
    econ = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1, seed=0))
    for _ in range(80):                          # build up firm debt (interest to pay) + a deposit spread
        econ.step()
    depo = {h.id: econ.ledger.balance(h.id) for h in econ.households}
    before = {h.id: h.income_realized for h in econ.households}
    econ._phase4_5_debt_service()                # only the bank redistribution adds to income_realized here
    recv = {h.id: h.income_realized - before[h.id] for h in econ.households}
    total_recv = sum(recv.values())
    assert total_recv > EPS, "no interest was distributed (burn-in produced no debt?)"
    med = float(np.median(list(depo.values())))
    hi = sum(recv[i] for i in depo if depo[i] > med)      # above-median depositors
    lo = sum(recv[i] for i in depo if depo[i] <= med)     # at/below-median depositors
    assert hi > lo, f"interest should favour high-deposit households: hi={hi:.3f} vs lo={lo:.3f}"
    zero_recv = [recv[i] for i in depo if depo[i] <= EPS]
    assert all(x < 1e-6 for x in zero_recv), "zero-deposit households should receive ~no interest"


def test_flag_materially_changes_outcomes():
    """The fix is consequential, not cosmetic: at the same seed, deposit-proportional interest changes the
    macro path relative to equal-split (the two differ materially in steady-state real output)."""
    W = 300
    eq = Economy(Config.v10(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0)).run()
    dp = Economy(Config.v101(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0)).run()
    y_eq = np.mean([r["real_output"] for r in eq[-W:]])
    y_dp = np.mean([r["real_output"] for r in dp[-W:]])
    assert abs(y_dp - y_eq) / max(y_eq, 1.0) > 0.005, f"flag should matter: equal={y_eq:.0f} vs deposit={y_dp:.0f}"


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
