"""v4 acceptance tests (DESIGNDOC §13; PLAN_v4 §6).

Firm entry/exit is diagnostic, not a monopoly cure. v4 "done" is:
  * A5 holds every tick INCLUDING through births, deaths, and bad-debt writeoffs;
  * zombies are cleared (no firms sit persistently insolvent -> credit unfreezes);
  * firm count is dynamically stable (bounded away from 0 and from explosion);
  * writeoffs are absorbed by bank equity (and A5-safe).

Run: ``uv run python tests/test_v4_demographics.py``.
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config          # noqa: E402
from macro_sim.economy import Economy        # noqa: E402

TOL = 1e-6


def _run(ticks=1200, **kw):
    econ = Economy(Config.v4(n_firms_c=40, n_firms_k=20, n_households=400, n_ticks=ticks, seed=0, **kw))
    recs = econ.run()
    return econ, recs


def test_a5_holds_through_demographics():
    """Net worth = M every tick despite births (household-funded), deaths (repay), and
    bad-debt writeoffs (bank equity absorbs)."""
    econ, recs = _run()
    worst = max(r["conservation_drift"] for r in recs)
    assert worst < TOL, f"A5 violated during demographics; worst drift {worst:.3e}"
    assert abs(econ.ledger.net_worth - econ.ledger.genesis_money) < TOL


def test_demographics_actually_happen():
    """Births and deaths both occur (the mechanism is live, not inert)."""
    econ, recs = _run()
    assert sum(r["births"] for r in recs) > 0, "no firms ever entered"
    assert sum(r["deaths"] for r in recs) > 0, "no firms ever went bankrupt"
    assert sum(r["writeoffs"] for r in recs) > 0, "no bad debt was ever written off"


def test_zombies_cleared():
    """The v3 zombie-freeze is gone: persistently-insolvent firms get liquidated, so the
    standing zombie count is ~0 (vs v3 where nearly every C-firm froze insolvent)."""
    econ, recs = _run()
    tail_zombies = statistics.fmean(r["n_zombies"] for r in recs[len(recs) // 2:])
    assert tail_zombies < 0.1 * len(econ.c_firms), (
        f"zombies not cleared: tail avg {tail_zombies:.1f} of {len(econ.c_firms)} firms"
    )


def test_firm_count_bounded():
    """Count stays dynamically stable -- never collapses to 0, never explodes."""
    econ, recs = _run()
    counts = [r["firm_count_c"] for r in recs]
    assert min(counts) >= 1, "C-firm sector went extinct"
    assert max(counts) < 100 * 40, "firm count exploded"
    # and it is genuinely dynamic (entry+exit move it), not frozen
    assert max(counts) > min(counts), "firm count never changed (demographics inert?)"


def test_writeoffs_absorbed_by_bank_equity_a5_safe():
    """Bad debt reduces bank equity (not lost); if it exceeds the buffer the bank goes
    insolvent (allowed), but A5 still holds regardless."""
    econ, recs = _run()
    assert sum(r["writeoffs"] for r in recs) > 0
    # A5 must hold even if the bank went insolvent at some point
    assert max(r["conservation_drift"] for r in recs) < TOL
    # bank equity is tracked and finite
    assert all(r["bank_equity"] == r["bank_equity"] for r in recs)  # not NaN


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
