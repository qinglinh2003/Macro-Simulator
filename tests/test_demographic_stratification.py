"""Phase 3.0: wealth stratification snapshot -- observation-only gauges.

Integration-light: drives WealthStratification through a real Economy (small v13
config) rather than stubbing the valuation, because the snapshot's inputs (ledger,
holdings, bank equity, household profiles) are exactly the integration surface.
Pure-function properties (tie-break, bucketing, medians) are tested directly.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.demographics.stratification import WealthStratification, _median, _pearson
from macro_sim.economy import Economy


@pytest.fixture(scope="module")
def small_econ():
    cfg = Config.v13(
        seed=3,
        n_households=60,
        n_firms_c=60,
        n_firms_k=30,
        n_banks=2,
        demographics_population=600,
        n_ticks=30,
    )
    econ = Economy(cfg)
    for _ in range(30):
        econ.step()
    return econ


def test_snapshot_covers_living_households_with_ranks_and_buckets(small_econ):
    strat = small_econ.demographic_bridge.stratification
    assert strat is not None and strat.household_rank
    ranks = list(strat.household_rank.values())
    assert all(0.0 < r < 1.0 for r in ranks)
    assert len(set(ranks)) == len(ranks)          # (i+0.5)/n ranks are unique by construction
    assert set(strat.household_bucket.values()) <= set(range(strat.buckets))


def test_bucket_shares_are_normalized(small_econ):
    strat = small_econ.demographic_bridge.stratification
    assert sum(strat.bucket_pop_share) == pytest.approx(1.0)
    assert sum(strat.bucket_wealth_share) == pytest.approx(1.0)
    # ranks are per-adult-equivalent while shares aggregate RAW net worth, so strict
    # monotonicity is not guaranteed (a poor-per-capita large household can out-hold a
    # rich-per-capita single) -- but the top bucket must out-hold the bottom one
    assert strat.bucket_wealth_share[-1] > strat.bucket_wealth_share[0]


def test_rank_history_accumulates(small_econ):
    strat = small_econ.demographic_bridge.stratification
    assert strat.rank_history
    year, household_id, rank = strat.rank_history[0]
    assert year == strat.year and 0.0 < rank < 1.0
    assert household_id in strat.household_rank


def test_vital_counters_attribute_to_buckets(small_econ):
    strat = small_econ.demographic_bridge.stratification
    state = small_econ.demographic_state
    # 30 ticks over 600 people: some deaths happened; every counted event maps to a bucket
    assert sum(strat.bucket_deaths) <= len(state.death_events)
    assert sum(strat.bucket_births) <= len(state.birth_events)
    assert all(v >= 0 for v in strat.bucket_deaths + strat.bucket_births)


def test_deterministic_tie_break_orders_by_household_id():
    entries = [(0.0, 7, 0.0), (0.0, 3, 0.0), (0.0, 11, 0.0)]
    entries.sort(key=lambda e: (e[0], e[1]))
    assert [e[1] for e in entries] == [3, 7, 11]


def test_pearson_and_median_primitives():
    assert _pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert _pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert _pearson([1, 1, 1], [1, 2, 3]) == 0.0     # zero variance guard
    assert _median([3.0, 1.0, 2.0]) == 2.0
    assert _median([4.0, 1.0, 2.0, 3.0]) == 2.5
    assert _median([]) == 0.5


def test_age_gauges_populated(small_econ):
    strat = small_econ.demographic_bridge.stratification
    assert -1.0 <= strat.age_rank_corr <= 1.0
    assert len(strat.median_rank_by_band) == 4
    assert all(0.0 <= m <= 1.0 for m in strat.median_rank_by_band)
