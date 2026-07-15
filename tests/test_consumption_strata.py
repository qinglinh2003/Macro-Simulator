"""v18.1 acceptance tests (PLAN_v18) — the necessity/luxury sector split & the budget
hierarchy.

"Done" for v18.1:
  * flag off (with non-default knobs) ⇒ bit-identical, no sector columns leak;
  * the household goods phase splits into two sequenced sessions — necessity first
    (quantity-targeted at a fixed per-need-unit basket), luxury the residual;
  * ENGEL'S LAW EMERGES: necessity share falls with expenditure PER NEED-UNIT (the
    per-capita affluence axis — total household spend is confounded by size), a >1.5x
    bottom/top gradient that was never seeded;
  * the necessity sector's inelastic demand does NOT pin markups at the ceiling (the
    v17.0 markup watch, transplanted);
  * entry routes to the higher-profit sector; sector firm counts stay bounded (no
    oscillation to 0 or an explosion).

Run: ``uv run python tests/test_consumption_strata.py`` or via pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                       # noqa: E402

from macro_sim.config import Config                      # noqa: E402
from macro_sim.economy import Economy                    # noqa: E402
from macro_sim.reporting.metrics import compute_tick_metrics  # noqa: E402


def _world(**extra) -> Config:
    base = dict(seed=0, n_households=30, n_firms_c=30, n_firms_k=15, n_banks=2,
                demographics_population=300, n_ticks=1825,
                housing_enabled=True, housing_market_enabled=True,
                energy_enabled=True, energy_household=True)
    base.update(extra)
    return Config.v13(**base)


def test_split_off_bit_identical():
    """Flag off with non-default knobs ⇒ not one series value moves, no sector columns."""
    a = Economy(_world(n_ticks=730)).run()
    b = Economy(_world(n_ticks=730, necessity_share0=0.7, n_firm_share=0.4)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"]
        assert x["price_index"] == y["price_index"]
        assert x["conservation_drift"] == y["conservation_drift"]
        assert "necessity_share" not in y, "sector gauges must not appear with the split off"


def _mature(recs, key):
    vals = [r[key] for r in recs[-730:] if r.get(key) is not None]
    return float(np.mean(vals)) if vals else 0.0


def test_engel_law_emerges():
    """Necessity share falls with per-need-unit expenditure — a >1.5x bottom/top gradient
    that emerges from the fixed necessity quantity, not seeded. Also: the aggregate
    necessity share is a plausible modern essentials level (not degenerate 0 or 1)."""
    recs = Economy(_world(consumption_strata=True)).run()
    bq = _mature(recs, "necessity_share_bottomq")
    tq = _mature(recs, "necessity_share_topq")
    assert tq > 0.0 and bq > 0.0, "gradient gauges never populated"
    assert bq / tq >= 1.5, f"Engel gradient too weak: bottomq {bq:.3f} / topq {tq:.3f} = {bq/tq:.2f}x"
    ns = _mature(recs, "necessity_share")
    assert 0.1 < ns < 0.7, f"aggregate necessity share implausible: {ns:.3f}"


def test_necessity_markup_not_pinned():
    """The markup watch: inelastic necessity demand must NOT pin the sector at mu_max
    (if it did, that would be a finding to diagnose, not hide). Time-at-ceiling small."""
    recs = Economy(_world(consumption_strata=True)).run()
    at_cap = _mature(recs, "necessity_markup_at_cap")
    assert at_cap < 0.5, f"necessity markups pinned at the ceiling {at_cap:.2f} of the time"


def test_sector_entry_bounded():
    """Entry routes to sectors and neither sub-sector collapses to zero or explodes over
    the run (the entry-oscillation watch)."""
    recs = Economy(_world(consumption_strata=True)).run()
    active = [r for r in recs if r.get("n_firms_necessity") is not None]
    n_counts = [r["n_firms_necessity"] for r in active]
    l_counts = [r["n_firms_luxury"] for r in active]
    assert min(n_counts) >= 1 and min(l_counts) >= 1, "a sub-sector collapsed to zero"
    assert max(n_counts) < 200 and max(l_counts) < 200, "a sub-sector exploded"


def test_sector_extinction_keeps_a_stable_reporting_schema():
    """A real zero-firm sector remains observable instead of deleting its columns."""
    econ = Economy(_world(consumption_strata=True, n_ticks=1))
    first = econ.step()
    sector_keys = {
        key for key in first
        if key.startswith(("necessity_", "luxury_", "cpi_bottomq", "cpi_topq"))
    }

    econ.n_firms = []
    econ.c_firms = list(econ.l_firms)
    after_extinction = compute_tick_metrics(econ)

    assert sector_keys <= set(after_extinction)
    assert after_extinction["n_firms_necessity"] == 0.0
    assert after_extinction["necessity_price_index"] == first["necessity_price_index"]
    assert all(np.isfinite(after_extinction[key]) for key in sector_keys)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all consumption-strata tests passed")
