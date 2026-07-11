"""Phase 3.3: wealth homophily in the marriage market.

The assortativity term prices rank distance in years of age mismatch inside the
deterministic candidate score. lambda=0 or a missing rank map MUST take the original
code path (bit-identity by code path, not by weight equality).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from macro_sim.demographics.kernel import MicroDemographicKernel, create_genesis_population
from macro_sim.demographics.rates import Phase0VitalRates
from macro_sim.demographics.social import SocialDynamicsConfig, _best_marriage_candidate


@dataclass
class _P:
    id: int
    age: int
    sex: str
    household_id: int
    partner_id: int | None = None
    mother_id: int | None = None
    father_id: int | None = None


def config(assortativity: float = 0.0) -> SocialDynamicsConfig:
    return SocialDynamicsConfig(marriage_assortativity=assortativity)


def test_no_ranks_is_the_original_selection():
    female = _P(0, 28, "F", 100)
    males = [_P(1, 30, "M", 200), _P(2, 33, "M", 201)]
    # age target 28+2=30: male 1 wins on age alone
    assert _best_marriage_candidate(female, males, config(5.0), None).id == 1
    assert _best_marriage_candidate(female, males, config(0.0), None).id == 1


def test_assortativity_overrides_small_age_mismatch():
    female = _P(0, 28, "F", 100)
    close_age_poor = _P(1, 30, "M", 200)     # perfect age, far rank
    older_rich = _P(2, 33, "M", 201)         # 3y age miss, same rank
    ranks = {100: 0.9, 200: 0.1, 201: 0.85}
    # lambda=0: age wins
    assert _best_marriage_candidate(female, [close_age_poor, older_rich], config(0.0), None).id == 1
    # lambda=10: 0.8 rank distance costs 8 'years' > 3y age miss -- the rich candidate wins
    assert _best_marriage_candidate(
        female, [close_age_poor, older_rich], config(10.0), ranks
    ).id == 2


def test_unknown_households_default_to_middle_rank():
    female = _P(0, 28, "F", 999)             # not in the rank map
    males = [_P(1, 30, "M", 200), _P(2, 30, "M", 998)]
    ranks = {200: 0.5}
    # female defaults to 0.5; male 200 has rank 0.5 (distance 0), male 998 defaults 0.5 too
    # -> tie on rank, falls back to age/id ordering: id 1 wins
    assert _best_marriage_candidate(female, males, config(10.0), ranks).id == 1


def test_kernel_marriage_stream_identical_when_assortativity_off():
    def run(economic_state):
        rates = Phase0VitalRates()
        state = create_genesis_population(rates, n=500, seed=17)
        kernel = MicroDemographicKernel(rates, rng_seed=18, social_config=config(0.0))
        for _ in range(90):
            kernel.tick(state, economic_state=economic_state)
        return [(e.tick, tuple(sorted((e.spouse_a_id, e.spouse_b_id)))) for e in state.marriage_events]

    class _WithRanks:
        household_ranks = {h: (h % 10) / 10.0 for h in range(10000)}

    # assortativity 0 in the social config: the rank map must be inert
    assert run(None) == run(_WithRanks())


def test_kernel_assortativity_shifts_matches():
    def run(assortativity, ranks):
        rates = Phase0VitalRates()
        state = create_genesis_population(rates, n=1200, seed=17)
        kernel = MicroDemographicKernel(rates, rng_seed=18, social_config=config(assortativity))
        stub = type("S", (), {"household_ranks": ranks})() if ranks else None
        for _ in range(365):
            kernel.tick(state, economic_state=stub)
        return [(e.tick, tuple(sorted((e.spouse_a_id, e.spouse_b_id)))) for e in state.marriage_events]

    ranks = {h: (h % 10) / 10.0 for h in range(10000)}
    baseline = run(0.0, None)
    homophilous = run(50.0, ranks)
    assert baseline != homophilous            # strong homophily reorders at least one match
    assert len(homophilous) > 0
