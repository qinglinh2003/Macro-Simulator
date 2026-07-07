"""v5 acceptance tests (DESIGNDOC §14; PLAN_v5).

v5 adds an output-scaled diseconomy of scale, uc = uc_labor * (1 + dis_slope * y*).
The phase diagram falsified the pre-registered hypothesis; "done" is the SURPRISE, in
data (robust, low-variance claims only):
  * dis_slope=0 is bit-identical to v4 (pricing change vanishes) -- regression;
  * at LOW transparency (m=1) raising dis_slope de-concentrates (Gini AND markup fall)
    -- the profit-squeeze->death channel;
  * at HIGH transparency (m>=2) it does NOT de-concentrate (winner-take-all rotates the
    leader instead of thinning it) -- transparency is antagonistic;
  * entry/exit is independently necessary: firm_dynamics OFF at the competition cell
    restores concentration (3-D conjunction);
  * A5 / conservation untouched (v5 is a pricing-only change).

Run: ``uv run python tests/test_v5_diseconomies.py``.
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config          # noqa: E402
from macro_sim.economy import Economy        # noqa: E402

TOL = 1e-6
TICKS, TAIL = 800, 150
NC, NK, NH = 40, 20, 400


def _cell(m, slope, seeds=(0, 1), fd=True):
    """Tail-mean Gini, markup, and worst A5 drift over ``seeds``, at (m, slope)."""
    ginis, markups, drifts = [], [], []
    for sd in seeds:
        cfg = Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                        n_ticks=TICKS, search_m=m, dis_slope=slope, seed=sd)
        cfg.firm_dynamics = fd
        recs = Economy(cfg).run()
        t = recs[-TAIL:]
        ginis.append(statistics.fmean(r["firm_size_gini_output"] for r in t))
        markups.append(statistics.fmean(r["avg_markup"] for r in t))
        drifts.append(max(r["conservation_drift"] for r in recs))
    return (statistics.fmean(ginis), statistics.fmean(markups), max(drifts))


def test_regression_bit_identical_at_zero_slope():
    """dis_slope=0 reproduces v4 exactly (the pricing multiplier is 1.0)."""
    base = Economy(Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                             n_ticks=300, seed=0)).run()
    v5 = Economy(Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                           n_ticks=300, seed=0, dis_slope=0.0)).run()
    for a, b in zip(base, v5):
        assert a["price_index"] == b["price_index"], "dis_slope=0 perturbed prices"
        assert a["firm_size_gini_output"] == b["firm_size_gini_output"]


def test_deconcentrates_at_low_transparency():
    """m=1: raising dis_slope de-concentrates the market (profit-squeeze->death) -- the
    robust, scale-stable claim. It also lowers markups, but that effect grows with scale
    (~0.08 at the §14.2 scale of 80/40/800; only ~0.005 here), so at test scale we assert
    only that the diseconomy does NOT raise monopoly markups."""
    g0, mk0, _ = _cell(m=1, slope=0.0)
    g1, mk1, _ = _cell(m=1, slope=0.005)
    assert g1 < g0 - 0.05, f"diseconomy did not de-concentrate at m=1: {g0:.3f} -> {g1:.3f}"
    assert mk1 <= mk0 + 0.01, f"diseconomy raised markup at m=1: {mk0:.3f} -> {mk1:.3f}"


def test_transparency_blocks_deconcentration():
    """m>=2: the same diseconomy does NOT materially de-concentrate -- winner-take-all
    (§11.6) rotates the leader rather than thinning it. Concentration stays high."""
    g0, _, _ = _cell(m=5, slope=0.0)
    g1, _, _ = _cell(m=5, slope=0.005)
    assert g1 > 0.80, f"m=5 unexpectedly de-concentrated to {g1:.3f} (antagonism claim fails)"
    # and the drop is far smaller than the m=1 drop (that comparison is the real content)
    assert g1 > g0 - 0.05, f"m=5 de-concentrated as much as m=1 ({g0:.3f} -> {g1:.3f})"


def test_entry_exit_is_necessary_3d():
    """At the competition cell (m=1, slope=0.005), removing firm_dynamics restores
    concentration: the diseconomy makes losses, but exit is the executioner."""
    g_on, _, _ = _cell(m=1, slope=0.005, fd=True)
    g_off, _, _ = _cell(m=1, slope=0.005, fd=False)
    assert g_off > g_on + 0.08, (
        f"competition survived without entry/exit ({g_on:.3f} on vs {g_off:.3f} off) "
        "-- 3-D conjunction claim fails"
    )


def test_a5_holds_under_diseconomy():
    """v5 is a pricing-only change; conservation (A5) is untouched."""
    _, _, worst = _cell(m=1, slope=0.005, seeds=(0,))
    assert worst < TOL, f"A5 violated under diseconomy; worst drift {worst:.3e}"


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
