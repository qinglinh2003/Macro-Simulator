"""Phase 3.1/3.2: rank-gradient strata -- individual position -> individual hazard.

Covers the strata construction invariants (exposure-weighted mean one, monotonicity,
clip, off-state emptiness), the kernel's per-person application, and the end-to-end
integration through a small economy.
"""

from __future__ import annotations

import math

import pytest

from macro_sim.config import Config
from macro_sim.demographics.kernel import MicroDemographicKernel, create_genesis_population
from macro_sim.demographics.rates import Phase0VitalRates
from macro_sim.demographics.stratification import WealthStratification
from macro_sim.economy import Economy


# ---------------------------------------------------------------------------
# strata construction (pure)
# ---------------------------------------------------------------------------

def build_strata(gradient: float, exposure=None, buckets: int = 5):
    strat = WealthStratification(buckets=buckets, mortality_gradient=gradient)
    # synthetic snapshot: 10 households spread over the buckets
    for household_id in range(10):
        bucket = household_id % buckets
        strat.household_bucket[household_id] = bucket
        strat.household_rank[household_id] = (bucket + 0.5) / buckets
    exposure = exposure if exposure is not None else [1.0] * buckets
    strat._build_strata(gradient, exposure, strat.bucket_mortality_mult, strat.mortality_strata)
    return strat


def test_off_gradient_builds_no_strata():
    strat = build_strata(0.0)
    assert strat.mortality_strata == {}
    assert strat.bucket_mortality_mult == [1.0] * 5


def test_strata_monotone_and_exposure_weighted_mean_one():
    exposure = [5.0, 3.0, 2.0, 1.0, 0.5]      # poor buckets carry more baseline hazard
    strat = build_strata(0.8, exposure=exposure)
    mults = strat.bucket_mortality_mult
    assert mults == sorted(mults, reverse=True)             # poor bucket dies faster
    weighted_mean = sum(w * m for w, m in zip(exposure, mults)) / sum(exposure)
    assert weighted_mean == pytest.approx(1.0, abs=1e-12)   # exact: expected deaths invariant
    assert mults[0] / mults[-1] == pytest.approx(math.exp(0.8 * 0.8))


def test_strata_clip_binds_on_extreme_gradient():
    strat = build_strata(6.0)
    assert max(strat.bucket_mortality_mult) == 2.0
    assert min(strat.bucket_mortality_mult) == 0.5


def test_negative_gradient_reverses_direction():
    strat = build_strata(-0.8)
    mults = strat.bucket_mortality_mult
    assert mults == sorted(mults)             # historical regime: rich bucket higher


def test_every_bucketed_household_gets_a_multiplier():
    strat = build_strata(0.8)
    assert set(strat.mortality_strata) == set(strat.household_bucket)
    # mid-year household absent from the snapshot -> neutral via dict default
    assert strat.mortality_strata.get(9999, 1.0) == 1.0


# ---------------------------------------------------------------------------
# kernel application
# ---------------------------------------------------------------------------

class _StrataStub:
    fertility_macro_multiplier = 1.0

    def __init__(self, mort=None, fert=None):
        self.mortality_strata = mort
        self.fertility_strata = fert


def run_kernel(stub, ticks: int = 120, seed: int = 31):
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=600, seed=seed)
    kernel = MicroDemographicKernel(rates, rng_seed=seed + 1)
    for _ in range(ticks):
        kernel.tick(state, economic_state=stub)
    return state


def test_kernel_mortality_strata_concentrate_deaths():
    # every household pinned to an extreme multiplier by parity: even households 25x hazard
    state_ref = run_kernel(_StrataStub())
    heavy = {h: (25.0 if h % 2 == 0 else 1.0) for h in range(100000)}
    state_heavy = run_kernel(_StrataStub(mort=heavy))
    assert len(state_heavy.death_events) > 2 * len(state_ref.death_events)


def test_kernel_none_strata_is_bit_identical_to_missing_attr():
    state_a = run_kernel(_StrataStub())
    state_b = run_kernel(None)
    assert [(e.tick, e.person_id) for e in state_a.death_events] == [
        (e.tick, e.person_id) for e in state_b.death_events
    ]
    assert [(e.tick, e.person_id) for e in state_a.birth_events] == [
        (e.tick, e.person_id) for e in state_b.birth_events
    ]


def test_kernel_fertility_strata_scale_births():
    boosted = {h: 8.0 for h in range(100000)}
    state_ref = run_kernel(_StrataStub())
    state_boost = run_kernel(_StrataStub(fert=boosted))
    assert len(state_boost.birth_events) > 3 * len(state_ref.birth_events)


# ---------------------------------------------------------------------------
# economy integration
# ---------------------------------------------------------------------------

def test_economy_builds_strata_after_first_snapshot():
    cfg = Config.v13(
        seed=11,
        n_households=40,
        n_firms_c=40,
        n_firms_k=20,
        n_banks=2,
        demographics_population=400,
        n_ticks=3,
        mortality_rank_gradient=0.8,
        fertility_rank_gradient=0.5,
    )
    econ = Economy(cfg)
    for _ in range(3):
        econ.step()
    strat = econ.demographic_bridge.stratification
    assert strat.mortality_strata and strat.fertility_strata
    assert strat.bucket_mortality_mult[0] > 1.0 > strat.bucket_mortality_mult[-1]
    assert strat.bucket_fertility_mult[0] > 1.0 > strat.bucket_fertility_mult[-1]
    rec = econ.records[-1]
    assert rec["bucket0_mortality_mult"] == pytest.approx(strat.bucket_mortality_mult[0])
    # bridge exposes the tables to the kernel
    assert econ.demographic_bridge.mortality_strata is strat.mortality_strata
    assert econ.demographic_bridge.fertility_strata is strat.fertility_strata


def test_economy_gradients_off_exposes_none():
    cfg = Config.v13(
        seed=11,
        n_households=30,
        n_firms_c=30,
        n_firms_k=15,
        n_banks=2,
        demographics_population=300,
        n_ticks=2,
    )
    econ = Economy(cfg)
    for _ in range(2):
        econ.step()
    assert econ.demographic_bridge.mortality_strata is None
    assert econ.demographic_bridge.fertility_strata is None
