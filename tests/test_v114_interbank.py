"""v11.4 acceptance tests (DESIGNDOC §37).

v11.4 partitions deposits (each becomes a specific bank's liability) and adds a RESERVE tier with full intra-tick
RTGS settlement: every payment settles reserves between the payer's and payee's banks (a reserve OVERLAY hooked in
Ledger.transfer -- the deposit ledger + A5 are untouched). On top sit an interbank money market (reserve-short
banks borrow at an endogenous, tightness-driven rate; failures cascade through interbank claims) and deposit-side
competition (banks post deposit-rate spreads, depositors migrate toward higher rates). "Done":
  * interbank=False ⇒ v11.3 bit-identical; n_banks=1 ⇒ v10.2 bit-identical;
  * deposit-A5 conserves with the overlay on AND through interbank failures/cascades (the overlay is a 2nd layer);
  * the reserve overlay conserves separately (Σ reserves = M₀) AND the RTGS-settled reserves match the balance-
    sheet identity R_k = capital+deposits−loans each tick (the settlement is exact);
  * KEY FINDING -- the interbank market / gridlock are LATENT: reserves are hyper-abundant vs payment flows (thin
    credit, money multiplier ≈1, unsterilised deficit), so peak intraday overdraft ≈ 0 and no payment gridlocks;
  * deposit-side competition also lacks a genuine driver here and DEGENERATES (monopoly/collapse), so it ships OFF
    -- the whole funding-side complex awaits a scarce-reserves regime (a bond layer). The correct, conserving
    reserve/RTGS/interbank INFRASTRUCTURE is the deliverable.

Run: ``uv run python tests/test_v114_interbank.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """interbank=False reproduces v11.3 exactly (no reserve overlay, no settlement)."""
    a = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            interbank=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_single_bank_bit_identical():
    """n_banks=1 ⇒ the reserve overlay never activates (gated on >1 bank) ⇒ v10.2 exactly."""
    a = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0, n_banks=1)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]


def test_deposit_A5_conserves():
    """The deposit ledger (A5) conserves with the overlay on -- the reserve layer never touches deposit
    accounting; interbank interest + contagion are plain conserving transfers."""
    recs = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


def test_reserves_conserve_and_settle_exactly():
    """The reserve overlay conserves (Σ reserves = M₀) AND the RTGS-settled reserves reproduce the balance-sheet
    identity R_k = capital+deposits−loans each tick (the settlement is exact, not an approximation)."""
    econ = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=500, seed=1))
    max_ident = 0.0
    for _ in range(500):
        econ.step()
        econ._refresh_loan_books()
        for bk in econ.banks:
            max_ident = max(max_ident, abs(econ._reserve_position(bk.id) - econ.ledger.reserves(bk.id)))
    assert abs(econ.ledger.total_reserves - econ.ledger._reserve_M) < 1e-6 * abs(econ.ledger._reserve_M)
    assert max_ident < 1e-4, f"RTGS-settled reserves should match the identity R_k=cap+dep−loans: {max_ident:.2e}"


def test_interbank_market_is_latent():
    """KEY FINDING (reported, not tuned): reserves are hyper-abundant vs payment flows in this economy (thin
    credit, unsterilised deficit), so NO bank ever runs reserve-short -- peak intraday overdraft ≈ 0, interbank
    volume ≈ 0, and no payment gridlocks. The machinery is correct but LATENT (awaits a scarce-reserves regime)."""
    recs = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    assert max(r.get("peak_intraday_overdraft", 0.0) for r in recs) < 1e-3, "banks should never be reserve-short here"
    assert sum(r.get("payments_gridlocked", 0.0) for r in recs) == 0.0, "no gridlock under ample reserves"


def test_deposit_competition_degenerates_so_off_by_default():
    """FINDING (§37): deposit-side competition has NO genuine driver in this ample-reserves economy (banks don't
    need deposits to fund loans), so imposed exogenous deposit spreads DEGENERATE -- depositors all pile into the
    top-rate bank (HHI → ~1, monopoly + sector collapse) rather than equilibrate. Hence it ships OFF
    (deposit_rate_disp=0): the DEFAULT stays near the even-split floor. (The machinery is opt-in; the real unlock
    is a scarce-reserves regime / a bond layer.)"""
    default = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    forced = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                                 deposit_rate_disp=0.002)).run()
    hhi_default = np.mean([r.get("bank_deposit_hhi", 0.0) for r in default[-300:]])
    hhi_forced = np.mean([r.get("bank_deposit_hhi", 0.0) for r in forced[-300:]])
    assert hhi_default < 0.3, f"the shipped default must NOT concentrate deposits: {hhi_default:.3f}"
    assert hhi_forced > hhi_default, "forcing deposit competition on concentrates (degenerately) -- why it's off"


def test_conservation_through_contagion():
    """A5 holds THROUGH interbank failures/cascades -- the loss reassignment onto interbank creditors is a
    conserving transfer. Stress it with thin, aggressive banks so failures actually occur."""
    recs = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=1,
                               bank_leverage_mean=14.0, bank_leverage_disp=1.0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m, "A5 broke through interbank contagion"
    assert abs(recs[-1].get("bank_reserves_total", 0.0)) > 0.0  # overlay active


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
