"""v11 acceptance tests (DESIGNDOC §35).

v11 partitions the loan book among n_banks "loan-book banks", each a capital buffer (its own deposit balance)
with a heterogeneous leverage cap κ_bank. Deposits stay a single global pool (no interbank settlement). Banks
retain ρ of interest → build adequate capital → are STABLE under normal conditions (like real banks); the
failure machinery is LATENT -- a bank fails only if a loss WAVE overruns its capital. "Done":
  * n_banks=1 ⇒ bit-identical to v10.2 (regression -- the whole chain is the one-bank special case);
  * money (A5) + shares conserve at n_banks>1 AND through bank failures (a dead bank's negative balance is
    part of ΣD -- no money created/destroyed);
  * the failure machinery is CORRECT -- under extreme stress a bank CAN fail and it's resolved conservingly;
  * the constraint OFF (or n=1) is a no-op (bit-identical).
The realistic default is a stable, well-capitalized banking system; failures await a genuine (future) shock.

Run: ``uv run python tests/test_v11_banks.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000

# a stressed config that reliably produces bank failures: many thin, aggressive, concentrated banks
STRESS = dict(n_banks=40, bank_capital_constraint=True, bank_capital_frac=0.005,
              bank_leverage_mean=15.0, bank_leverage_disp=1.0)


def test_regression_bit_identical_off():
    """n_banks=1 reproduces v10.2 exactly (single BANK, no partition, no constraint)."""
    a = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v11(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                           n_banks=1)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_conservation_multibank():
    """Multi-bank (constraint on) still conserves money (A5) and per-firm shares -- N bank accounts are just
    part of ΣD; write-offs use the existing conserving primitive."""
    recs = Economy(Config.v11(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_failure_machinery_and_conservation():
    """The failure machinery is CORRECT: under EXTREME stress (many very thin aggressive banks on a volatile
    base) write-offs DO overrun some banks' capital and they fail -- AND A5 holds THROUGH the failures: a
    resolved bank's account stays in the ledger with its negative balance (= the realized loss), so no money is
    created or destroyed. (Normal-condition banks are stable; this deliberately stresses the failure path.)"""
    recs = Economy(Config.v85(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=1, **STRESS)).run()
    fails = recs[-1].get("n_bank_failures", 0.0)
    alive = recs[-1].get("banks_alive", 40.0)
    assert fails >= 1.0, f"stressed banking system should produce failures: fails={fails}"
    assert alive < 40.0, f"some banks should be dead: alive={alive}/40"
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m, "A5 broke through a bank failure"


def test_default_is_stable():
    """The realistic default `Config.v11()` is a STABLE, well-capitalized banking system -- banks retain ρ of
    interest and do NOT fail under normal conditions (like real banks). Failures await a genuine shock."""
    recs = Economy(Config.v11(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    assert recs[-1].get("n_bank_failures", 0.0) == 0.0, "realistic banks should not fail under normal conditions"
    assert recs[-1].get("banks_alive", 0.0) == float(Config.v11().n_banks), "all banks should survive"


def test_v112_realistic_capital():
    """v11.2: with a Basel capital ratio + large-exposure limit, banks are realistically THIN and BOUNDED --
    they hold capital as a SMALL fraction of broad money (a real ~10% leverage ratio) instead of the ρ-hoard,
    and run realistic leverage (loans ≫ capital). (The emergent failure rate is REPORTED in §35, not asserted
    here -- we do not tune the exposure limit to a failure target.)"""
    recs = Economy(Config.v112(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1000, seed=0)).run()
    bc, bm = recs[-1].get("bank_capital", 0.0), recs[-1].get("broad_money", 1.0)
    lev = np.mean([r.get("bank_leverage", 0.0) for r in recs[-300:]])
    assert bc / bm < 0.5, f"v11.2 bank capital should be bounded/thin, not a hoard: bankcap/BM={bc/bm:.2f}"
    assert lev > 3.0, f"v11.2 banks should run realistic leverage (thin capital): {lev:.1f}"
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * bm, "A5 broke"


def test_v112_off_bit_identical():
    """v11.2's levers OFF (ratio=0, exposure=0) reproduce v11 exactly."""
    a = Economy(Config.v11(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v112(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                            bank_target_capital_ratio=0.0, bank_exposure_limit=0.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]


def test_constraint_off_is_noop():
    """With the capital constraint OFF, multi-bank is pure partitioning -- no crunch, no failure (crises are
    opt-in via bank_capital_constraint)."""
    recs = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=500, seed=0,
                               n_banks=5, bank_capital_constraint=False)).run()
    assert recs[-1].get("n_bank_failures", 0.0) == 0.0, "no failures without the constraint"


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
