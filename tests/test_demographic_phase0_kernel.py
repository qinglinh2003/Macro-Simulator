import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import (
    Phase0VitalRates,
    build_leslie_matrix,
    create_genesis_population,
    expected_life_at_birth,
    plot_stable_pyramid,
    spectral_diagnostics,
    stable_age_distribution,
)
from macro_sim.demographics.kernel import MicroDemographicKernel, count_alive_by_age


def test_vital_rates_generate_survival_and_fertility_curves():
    rates = Phase0VitalRates()

    survival = rates.survival_curve()
    fertility = rates.fertility_curve()

    assert survival.shape == (rates.omega,)
    assert fertility.shape == (rates.omega + 1,)
    assert np.all((survival > 0.0) & (survival <= 1.0))
    assert survival[0] < survival[1]
    assert fertility[:15].sum() == 0.0
    assert fertility[50:].sum() == 0.0
    assert math.isclose(float(fertility.sum()), rates.tfr, rel_tol=1e-10)
    assert 70.0 < expected_life_at_birth(rates) < 82.0


def test_leslie_matrix_has_stable_age_distribution():
    rates = Phase0VitalRates()
    leslie = build_leslie_matrix(rates)
    stable = stable_age_distribution(leslie)
    diag = spectral_diagnostics(leslie)

    assert leslie.shape == (rates.omega + 1, rates.omega + 1)
    assert math.isclose(float(stable.sum()), 1.0)
    assert np.all(stable >= 0.0)
    np.testing.assert_allclose(leslie @ stable, diag.lambda1 * stable, rtol=1e-8, atol=1e-10)
    assert diag.lambda1 > 1.0
    assert 0.0 < diag.damping_ratio < 1.0


def test_genesis_samples_agents_from_stable_distribution():
    rates = Phase0VitalRates()
    leslie = build_leslie_matrix(rates)
    stable = stable_age_distribution(leslie)

    state = create_genesis_population(rates, n=40_000, seed=17)
    sampled = count_alive_by_age(state.people, rates.omega) / state.alive_count

    assert state.alive_count == 40_000
    assert all(hasattr(person, "mother_id") and hasattr(person, "father_id") for person in state.people)
    assert all(person.household_id is not None for person in state.people)
    assert state.relationship_stats is not None
    assert state.relationship_stats.population == 40_000
    assert state.relationship_stats.minor_placement_rate == 1.0
    assert max(abs(float(sampled[i] - stable[i])) for i in range(rates.omega + 1)) < 0.01


def test_micro_tick_preserves_headcount_identity_and_tracks_oracle():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=25_000, seed=5, start_date=date(2001, 1, 1))
    kernel = MicroDemographicKernel(rates, rng_seed=99, fertility_mode="all_women")
    oracle = state.oracle()

    result = None
    for _ in range(365):
        result = kernel.tick(state)
        assert result.new_headcount == result.old_headcount + result.births - result.deaths

    oracle_counts = oracle.step()
    live_counts = count_alive_by_age(state.people, rates.omega)
    assert result is not None
    assert state.current_date == date(2002, 1, 1)
    assert live_counts.sum() == result.new_headcount
    assert np.abs(live_counts - oracle_counts).sum() < 12.0 * math.sqrt(result.new_headcount) * math.sqrt(rates.omega + 1)


def test_birth_events_record_mother_and_household():
    rates = Phase0VitalRates(tfr=1000.0, makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    state = create_genesis_population(rates, n=2_500, seed=31)
    kernel = MicroDemographicKernel(rates, rng_seed=7, fertility_mode="all_women")

    births = 0
    for _ in range(10):
        births += kernel.tick(state).births
        if births:
            break

    assert births > 0
    newborns = [person for person in state.people if person.id >= 2_500]
    assert newborns
    assert all(person.mother_id is not None for person in newborns)
    assert all(person.household_id is not None for person in newborns)
    assert all(event.mother_id is not None for event in state.birth_events)
    assert all(hasattr(event, "father_id") for event in state.birth_events)


def test_leslie_oracle_relaxes_perturbed_distribution_toward_stable_shape():
    rates = Phase0VitalRates()
    leslie = build_leslie_matrix(rates)
    stable = stable_age_distribution(leslie)
    perturbed = stable.copy()
    perturbed[:10] *= 1.6
    perturbed[55:] *= 0.55
    perturbed = perturbed / perturbed.sum()

    def normalized_distance(vector: np.ndarray) -> float:
        vector = vector / vector.sum()
        return float(np.abs(vector - stable).sum())

    start = normalized_distance(perturbed)
    vector = perturbed
    for _ in range(80):
        vector = leslie @ vector
    end = normalized_distance(vector)

    assert end < start * 0.35


def test_plot_stable_pyramid_writes_png(tmp_path):
    rates = Phase0VitalRates()
    leslie = build_leslie_matrix(rates)
    stable = stable_age_distribution(leslie)
    path = tmp_path / "stable_pyramid.png"

    written = plot_stable_pyramid(stable, rates, path)

    assert written == path
    assert path.exists()
    assert path.stat().st_size > 0
