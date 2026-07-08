"""Layered Phase 0 demographic validation harness."""

from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

import numpy as np

from macro_sim.demographics.kernel import MicroDemographicKernel, count_alive_by_age, create_genesis_population
from macro_sim.demographics.leslie import build_leslie_matrix, spectral_diagnostics, stable_age_distribution
from macro_sim.demographics.multistate import (
    MaritalState,
    MultiStateIndex,
    Sex,
    build_multistate_leslie_matrix,
    calibrate_marital_fertility_curve,
    stable_multistate_distribution,
)
from macro_sim.demographics.rates import Phase0VitalRates, expected_life_at_birth
from macro_sim.demographics.social import SocialDynamicsConfig, social_health_snapshot


DEFAULT_OUTPUT_DIR = Path("outputs/demographics/phase0_validation")


def _same_month_day_in_year(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _completed_age_on(birth_date: date, current_date: date) -> int:
    birthday_this_year = _same_month_day_in_year(birth_date, current_date.year)
    years = current_date.year - birth_date.year
    if birthday_this_year > current_date:
        years -= 1
    return years


def _age_years_on(birth_date: date, current_date: date) -> float:
    completed = _completed_age_on(birth_date, current_date)
    last_birthday = _same_month_day_in_year(birth_date, current_date.year)
    if last_birthday > current_date:
        last_birthday = _same_month_day_in_year(birth_date, current_date.year - 1)
    next_birthday = _same_month_day_in_year(birth_date, last_birthday.year + 1)
    age_year_days = max(1, (next_birthday - last_birthday).days)
    elapsed_days = (current_date - last_birthday).days
    return float(completed + elapsed_days / age_year_days)


def _days_in_calendar_year(day: date) -> int:
    return (date(day.year + 1, 1, 1) - date(day.year, 1, 1)).days


class _CalendarExpectedOracle:
    """Deterministic expected Config B projection under real birthdays and daily ticks."""

    def __init__(self, rates: Phase0VitalRates, people, current_date: date) -> None:
        self.rates = rates
        self.current_date = current_date
        self.cohorts: dict[date, list[float]] = {}
        for person in people:
            if not person.alive:
                continue
            weights = self.cohorts.setdefault(person.birth_date, [0.0, 0.0])
            weights[0 if person.sex == "F" else 1] += 1.0

    def tick(self) -> dict[str, np.ndarray]:
        self.current_date = self.current_date + timedelta(days=1)
        dt_years = 1.0 / _days_in_calendar_year(self.current_date)
        next_cohorts: dict[date, list[float]] = {}
        expected_deaths_by_age = np.zeros(self.rates.omega + 1, dtype=float)
        expected_births_by_mother_age = np.zeros(self.rates.omega + 1, dtype=float)
        expected_births = 0.0
        for birth_date, weights in self.cohorts.items():
            completed_age = _completed_age_on(birth_date, self.current_date)
            age_bucket = min(max(0, completed_age), self.rates.omega)
            age_years = _age_years_on(birth_date, self.current_date)
            survival = 0.0 if completed_age >= self.rates.omega else self.rates.survival_probability(age_years, dt=dt_years)
            expected_deaths_by_age[age_bucket] += (weights[0] + weights[1]) * (1.0 - survival)
            female = weights[0] * survival
            male = weights[1] * survival
            if female > 1e-12 or male > 1e-12:
                next_cohorts[birth_date] = [female, male]
            if female > 0.0:
                cohort_births = female * self.rates.fertility_rate(age_years) * dt_years
                expected_births += cohort_births
                expected_births_by_mother_age[age_bucket] += cohort_births
        if expected_births > 0.0:
            next_cohorts[self.current_date] = [
                expected_births * self.rates.female_birth_share,
                expected_births * self.rates.male_birth_share,
            ]
        self.cohorts = next_cohorts
        return {
            "deaths_by_age": expected_deaths_by_age,
            "births_by_mother_age": expected_births_by_mother_age,
        }

    def counts_by_age(self) -> np.ndarray:
        counts = np.zeros(self.rates.omega + 1, dtype=float)
        for birth_date, weights in self.cohorts.items():
            age = min(max(0, _completed_age_on(birth_date, self.current_date)), self.rates.omega)
            counts[age] += weights[0] + weights[1]
        return counts


def total_variation(a: np.ndarray, b: np.ndarray) -> float:
    """Return total-variation distance after normalizing two non-negative vectors."""

    left = np.asarray(a, dtype=float)
    right = np.asarray(b, dtype=float)
    left_sum = float(left.sum())
    right_sum = float(right.sum())
    if left_sum <= 0.0 and right_sum <= 0.0:
        return 0.0
    if left_sum > 0.0:
        left = left / left_sum
    if right_sum > 0.0:
        right = right / right_sum
    return float(0.5 * np.abs(left - right).sum())


def partner_integrity(state) -> dict[str, int]:
    """Scan live partner pointers for missing, dead, self, or asymmetric links."""

    people_by_id = {person.id: person for person in state.people}
    report = {
        "partner_refs": 0,
        "bad_partner_links": 0,
        "missing_partner_refs": 0,
        "dead_partner_refs": 0,
        "self_partner_refs": 0,
        "asymmetric_partner_links": 0,
    }
    for person in state.people:
        if not person.alive or person.partner_id is None:
            continue
        report["partner_refs"] += 1
        partner = people_by_id.get(person.partner_id)
        if person.partner_id == person.id:
            report["self_partner_refs"] += 1
            report["bad_partner_links"] += 1
        elif partner is None:
            report["missing_partner_refs"] += 1
            report["bad_partner_links"] += 1
        elif not partner.alive:
            report["dead_partner_refs"] += 1
            report["bad_partner_links"] += 1
        elif partner.partner_id != person.id:
            report["asymmetric_partner_links"] += 1
            report["bad_partner_links"] += 1
    return report


def _survivorship_curve(rates: Phase0VitalRates) -> np.ndarray:
    survivorship = np.ones(rates.omega + 1, dtype=float)
    for age in range(rates.omega):
        survivorship[age + 1] = survivorship[age] * rates.survival_probability(age, dt=1.0)
    return survivorship


def _nrr_and_generation_length(rates: Phase0VitalRates) -> tuple[float, float]:
    survivorship = _survivorship_curve(rates)
    female_fertility = rates.female_birth_share * rates.fertility_curve()
    weighted_births = survivorship * female_fertility * rates.dt
    nrr = float(np.sum(weighted_births))
    generation_length = float(np.sum(np.arange(rates.omega + 1) * weighted_births) / nrr) if nrr > 0.0 else 0.0
    return nrr, generation_length


def _mean_age(vector: np.ndarray) -> float:
    total = float(vector.sum())
    if total <= 0.0:
        return 0.0
    return float(np.sum(np.arange(vector.size) * vector) / total)


def _linear_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    y = np.asarray(values, dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def _project_normalized_distances(matrix: np.ndarray, initial: np.ndarray, stable: np.ndarray, steps: int) -> list[float]:
    vector = np.asarray(initial, dtype=float)
    distances: list[float] = []
    for _ in range(steps):
        total = float(vector.sum())
        normalized = vector / total if total > 0.0 else vector
        distances.append(total_variation(normalized, stable))
        vector = matrix @ vector
    return distances


def _genesis_zero_transient_metrics(rates: Phase0VitalRates, *, n: int, seeds: list[int]) -> dict[str, float]:
    matrix = build_leslie_matrix(rates)
    stable = stable_age_distribution(matrix)
    rng = np.random.default_rng(97_531)
    null_tvs = []
    for _ in range(200):
        sample = rng.multinomial(n, stable)
        null_tvs.append(total_variation(sample, stable))
    null_mean = float(np.mean(null_tvs))
    null_sd = float(np.std(null_tvs, ddof=1))

    tvs = []
    mean_age_slopes = []
    for seed in seeds:
        sample_rng = np.random.default_rng(seed)
        sample = sample_rng.multinomial(n, stable)
        tvs.append(total_variation(sample, stable))
        ages = []
        vector = sample.astype(float)
        for _ in range(20):
            ages.append(_mean_age(vector))
            vector = matrix @ vector
        mean_age_slopes.append(_linear_slope(ages))

    uniform = np.ones(rates.omega + 1, dtype=float)
    uniform = uniform / uniform.sum()
    uniform_distances = _project_normalized_distances(matrix, uniform, stable, 80)
    stable_distances = _project_normalized_distances(matrix, stable, stable, 80)
    return {
        "genesis_tv_mean": float(np.mean(tvs)) if tvs else 0.0,
        "genesis_tv_null_mean": null_mean,
        "genesis_tv_null_sd": null_sd,
        "genesis_tv_null_upper_3sd": null_mean + 3.0 * null_sd,
        "stable_mean_age_abs_slope": float(max(abs(slope) for slope in mean_age_slopes)) if mean_age_slopes else 0.0,
        "stable_projection_distance_max": float(max(stable_distances)) if stable_distances else 0.0,
        "uniform_projection_distance_ratio": (
            float(uniform_distances[-1] / uniform_distances[0]) if uniform_distances and uniform_distances[0] > 0.0 else 0.0
        ),
    }


def _ensemble_alignment_metrics(
    deviations_by_year: dict[int, list[np.ndarray]],
    growth_rates: list[float],
    matrix: np.ndarray,
    r_oracle: float | None = None,
) -> dict[str, float | int]:
    over_2se = 0
    max_z = 0.0
    active_cell_tests = 0
    for deviations in deviations_by_year.values():
        if len(deviations) < 3:
            continue
        arr = np.asarray(deviations, dtype=float)
        means = arr.mean(axis=0)
        ses = arr.std(axis=0, ddof=1) / np.sqrt(arr.shape[0])
        active = ses > 1e-9
        if not np.any(active):
            continue
        active_cell_tests += int(np.sum(active))
        z = np.abs(means[active]) / ses[active]
        over_2se += int(np.sum(z > 2.0))
        max_z = max(max_z, float(np.max(z)))

    diag = spectral_diagnostics(matrix)
    oracle_growth_rate = diag.growth_rate if r_oracle is None else r_oracle
    if len(growth_rates) >= 3:
        r_mean = float(np.mean(growth_rates))
        r_se = float(np.std(growth_rates, ddof=1) / np.sqrt(len(growth_rates)))
        r_z = abs(r_mean - oracle_growth_rate) / r_se if r_se > 1e-12 else 0.0
    elif growth_rates:
        r_mean = float(np.mean(growth_rates))
        r_se = 0.0
        r_z = 0.0
    else:
        r_mean = 0.0
        r_se = 0.0
        r_z = 0.0
    return {
        "ensemble_active_cells": active_cell_tests,
        "ensemble_cells_over_2se": over_2se,
        "ensemble_expected_over_2se_5pct": float(0.05 * active_cell_tests),
        "ensemble_max_mean_z": max_z,
        "r_empirical_mean": r_mean,
        "r_empirical_se": r_se,
        "r_oracle": oracle_growth_rate,
        "r_empirical_z_abs": float(r_z),
    }


def _ensemble_deviation_rows(deviations_by_year: dict[int, list[np.ndarray]]) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for year_index in sorted(deviations_by_year):
        deviations = deviations_by_year[year_index]
        if len(deviations) < 3:
            continue
        arr = np.asarray(deviations, dtype=float)
        means = arr.mean(axis=0)
        ses = arr.std(axis=0, ddof=1) / np.sqrt(arr.shape[0])
        for age, (mean, se) in enumerate(zip(means, ses, strict=True)):
            z_abs = abs(mean) / se if se > 1e-9 else 0.0
            rows.append({
                "year_index": year_index + 1,
                "age": age,
                "mean_deviation": float(mean),
                "standard_error": float(se),
                "z_abs": float(z_abs),
                "over_2se": int(z_abs > 2.0),
            })
    return rows


def _poisson_cdf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    if lam <= 0.0:
        return 1.0
    if lam > 700.0:
        z = (k + 0.5 - lam) / math.sqrt(lam)
        return float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    term = math.exp(-lam)
    total = term
    for value in range(1, k + 1):
        term *= lam / value
        total += term
    return float(min(1.0, total))


def _poisson_two_sided_p_value(observed: int, expected: float) -> float:
    if expected <= 0.0:
        return 1.0 if observed == 0 else 0.0
    lower = _poisson_cdf(observed, expected)
    upper = 1.0 - _poisson_cdf(observed - 1, expected)
    return float(min(1.0, 2.0 * min(lower, upper)))


def _apply_benjamini_hochberg(rows: list[dict], *, alpha: float = 0.05) -> None:
    active = [row for row in rows if row["expected_events"] > 1e-12 or row["observed_events"] > 0]
    ordered = sorted(active, key=lambda row: row["p_value"])
    m = len(ordered)
    running_q = 1.0
    for rank_from_end, row in enumerate(reversed(ordered), start=1):
        rank = m - rank_from_end + 1
        running_q = min(running_q, float(row["p_value"]) * m / rank)
        row["q_value"] = min(1.0, running_q)
    for rank, row in enumerate(ordered, start=1):
        row["bh_rejected"] = int(float(row["p_value"]) <= alpha * rank / m) if m else 0
    inactive = [row for row in rows if row not in active]
    for row in inactive:
        row["q_value"] = 1.0
        row["bh_rejected"] = 0


def _event_count_test_rows(seed_results: list[dict], config_key: str, kinds: Sequence[str]) -> list[dict]:
    buckets: dict[tuple[str, int, int], dict[str, float | int | str]] = {}
    for result in seed_results:
        event_counts = result[config_key].get("event_counts_by_year", {})
        for year_index, counts in event_counts.items():
            for kind in kinds:
                expected = np.asarray(counts[f"{kind}_expected"], dtype=float)
                observed = np.asarray(counts[f"{kind}_observed"], dtype=float)
                for age, (expected_value, observed_value) in enumerate(zip(expected, observed, strict=True)):
                    if expected_value <= 1e-12 and observed_value <= 0.0:
                        continue
                    key = (kind, int(year_index) + 1, age)
                    bucket = buckets.setdefault(
                        key,
                        {
                            "kind": kind,
                            "year_index": int(year_index) + 1,
                            "age": age,
                            "expected_events": 0.0,
                            "observed_events": 0,
                        },
                    )
                    bucket["expected_events"] = float(bucket["expected_events"]) + float(expected_value)
                    bucket["observed_events"] = int(bucket["observed_events"]) + int(round(float(observed_value)))
    rows = list(buckets.values())
    for row in rows:
        observed = int(row["observed_events"])
        expected = float(row["expected_events"])
        row["p_value"] = _poisson_two_sided_p_value(observed, expected)
        row["q_value"] = 1.0
        row["bh_rejected"] = 0
    _apply_benjamini_hochberg(rows)
    rows.sort(key=lambda row: (str(row["kind"]), int(row["year_index"]), int(row["age"])))
    return rows


def _aggregated_event_rows(event_rows: list[dict], *, min_expected: float = 10.0) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    ordered = sorted(event_rows, key=lambda row: (str(row["kind"]), int(row["year_index"]), int(row["age"])))
    current: dict[str, float | int | str] | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        expected = float(current["expected_events"])
        observed = int(current["observed_events"])
        z = 0.0 if expected <= 1e-12 else (observed - expected) / math.sqrt(expected)
        current["z_score"] = float(z)
        current["z_abs"] = abs(float(z))
        current["p_value"] = _poisson_two_sided_p_value(observed, expected)
        rows.append(current)
        current = None

    for row in ordered:
        kind = str(row["kind"])
        year_index = int(row["year_index"])
        age = int(row["age"])
        if (
            current is None
            or current["kind"] != kind
            or current["year_index"] != year_index
            or float(current["expected_events"]) >= min_expected
        ):
            flush()
            current = {
                "kind": kind,
                "year_index": year_index,
                "age_start": age,
                "age_end": age,
                "expected_events": 0.0,
                "observed_events": 0,
            }
        current["age_end"] = age
        current["expected_events"] = float(current["expected_events"]) + float(row["expected_events"])
        current["observed_events"] = int(current["observed_events"]) + int(row["observed_events"])
    flush()
    _apply_benjamini_hochberg(rows)
    return rows


def _event_count_summary(event_rows: list[dict], aggregated_rows: list[dict]) -> dict[str, float | int]:
    active_rows = [row for row in event_rows if float(row["expected_events"]) > 1e-12 or int(row["observed_events"]) > 0]
    active_aggregated_rows = [
        row for row in aggregated_rows if float(row["expected_events"]) > 1e-12 or int(row["observed_events"]) > 0
    ]
    q_values = [float(row["q_value"]) for row in active_rows]
    aggregated_q_values = [float(row["q_value"]) for row in active_aggregated_rows]
    return {
        "event_count_active_cells": len(active_rows),
        "event_count_bh_rejections": sum(int(row["bh_rejected"]) for row in active_rows),
        "event_count_min_q_value": min(q_values) if q_values else 1.0,
        "aggregated_event_cells": len(aggregated_rows),
        "aggregated_event_z_max": max((float(row["z_abs"]) for row in aggregated_rows), default=0.0),
        "aggregated_event_bh_rejections": sum(int(row["bh_rejected"]) for row in active_aggregated_rows),
        "aggregated_event_min_q_value": min(aggregated_q_values) if aggregated_q_values else 1.0,
    }


def _relaxation_metrics(matrix: np.ndarray) -> dict[str, float]:
    stable = stable_age_distribution(matrix)
    perturbed = stable.copy()
    perturbed[:10] *= 1.6
    perturbed[55:] *= 0.55
    perturbed = perturbed / perturbed.sum()
    distances = _project_normalized_distances(matrix, perturbed, stable, 80)

    values, vectors = np.linalg.eig(matrix)
    primary = int(np.argmax(values.real))
    lambda1 = values[primary]
    secondary = max(
        (idx for idx in range(values.size) if idx != primary),
        key=lambda idx: abs(values[idx] / lambda1),
    )
    lambda2 = values[secondary]
    mode = vectors[:, secondary].real
    if np.max(np.abs(mode)) < 1e-12:
        mode = vectors[:, secondary].imag
    mode = mode - mode.sum() * stable
    epsilon = 0.01
    negative = mode < 0.0
    if np.any(negative):
        epsilon = min(epsilon, 0.5 * float(np.min(stable[negative] / (-mode[negative]))))
    spectral_initial = stable + epsilon * mode
    spectral_initial = spectral_initial / spectral_initial.sum()
    spectral_distances = _project_normalized_distances(matrix, spectral_initial, stable, 80)
    spectral_usable = np.asarray(
        [distance for distance in spectral_distances[5:50] if distance > 1e-14],
        dtype=float,
    )
    slope = _linear_slope(np.log(spectral_usable)) if spectral_usable.size >= 2 else 0.0
    actual_decay = -slope
    diag = spectral_diagnostics(matrix)
    expected_decay = -float(np.log(abs(lambda2 / lambda1))) if abs(lambda2) > 0.0 else 0.0
    relative_error = (
        abs(actual_decay - expected_decay) / expected_decay
        if expected_decay > 1e-12
        else 0.0
    )
    return {
        "relaxation_decay_rate": actual_decay,
        "relaxation_expected_decay_rate": expected_decay,
        "relaxation_decay_relative_error": relative_error,
        "relaxation_initial_tv": float(distances[0]) if distances else 0.0,
        "relaxation_final_tv": float(distances[-1]) if distances else 0.0,
        "relaxation_distance_ratio": (
            float(distances[-1] / distances[0]) if distances and distances[0] > 0.0 else 0.0
        ),
        "relaxation_spectral_initial_tv": float(spectral_distances[0]) if spectral_distances else 0.0,
        "relaxation_spectral_final_tv": float(spectral_distances[-1]) if spectral_distances else 0.0,
        "relaxation_damping_ratio": diag.damping_ratio,
    }


def _max_tv_slope(tv_by_seed: dict[int, list[float]]) -> float:
    if not tv_by_seed:
        return 0.0
    slopes = [abs(_linear_slope(values)) for values in tv_by_seed.values() if len(values) >= 2]
    return float(max(slopes)) if slopes else 0.0


def run_phase0_validation(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    n: int = 5_000,
    years: int = 80,
    seeds: int | Sequence[int] = 20,
    workers: int = 1,
    start_date: date = date(2001, 1, 1),
) -> dict:
    """Run a layered, lightweight Phase 0 validation and write artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    seed_values = _seed_values(seeds)
    rates = Phase0VitalRates()
    worker_count = max(1, min(int(workers), len(seed_values)))

    constants = _spectral_constants(rates)
    _write_csv(output_path / "spectral_constants.csv", constants)

    seed_results = _run_seed_bundles(rates, n=n, years=years, seeds=seed_values, start_date=start_date, workers=worker_count)
    config_a = _aggregate_config_a(rates, seed_results, output_path=output_path)
    config_b = _aggregate_config_b(rates, seed_results, n=n, seeds=seed_values, output_path=output_path)
    config_c_oracle = _config_c_multistate_oracle(rates)
    config_c_matching = _aggregate_config_c_matching(seed_results, output_path=output_path)
    config_c_matching["married_share_oracle_gap_abs"] = abs(
        config_c_matching["mean_married_adult_share"] - config_c_oracle["adult_married_share"]
    )

    configs = {
        "config_a_mortality_only": config_a,
        "config_b_ungated_fertility": config_b,
        "config_c_multistate_oracle": config_c_oracle,
        "config_c_two_sided_matching": config_c_matching,
    }
    passed = (
        config_a["headcount_identity_failures"] == 0
        and config_a["event_count_bh_rejections"] == 0
        and config_a["aggregated_event_bh_rejections"] == 0
        and config_b["headcount_identity_failures"] == 0
        and config_b["max_tv_distance"] < 0.35
        and config_b["genesis_tv_mean"] <= config_b["genesis_tv_null_upper_3sd"]
        and config_b["r_empirical_z_abs"] < 2.5
        and config_b["event_count_bh_rejections"] == 0
        and config_b["aggregated_event_bh_rejections"] == 0
        and config_b["relaxation_decay_relative_error"] < 0.35
        and config_b["noop_economic_state_identical"] == 1
        and config_c_matching["headcount_identity_failures"] == 0
        and config_c_matching["bad_partner_links"] == 0
        and config_c_matching["minor_household_missing"] == 0
        and config_c_oracle["married_profile_max_abs_error"] < 0.12
        and config_c_matching["married_share_oracle_gap_abs"] < 0.20
    )
    summary = {
        "passed": bool(passed),
        "n": n,
        "years": years,
        "seeds": seed_values,
        "workers": worker_count,
        "start_date": start_date.isoformat(),
        "configs": configs,
        "artifacts": {
            "spectral_constants": str(output_path / "spectral_constants.csv"),
            "config_a_mortality": str(output_path / "config_a_mortality.csv"),
            "config_a_ensemble_deviation": str(output_path / "config_a_ensemble_deviation.csv"),
            "config_a_event_count_tests": str(output_path / "config_a_event_count_tests.csv"),
            "config_a_aggregated_event_tests": str(output_path / "config_a_aggregated_event_tests.csv"),
            "config_b_oracle_alignment": str(output_path / "config_b_oracle_alignment.csv"),
            "config_b_ensemble_deviation": str(output_path / "config_b_ensemble_deviation.csv"),
            "config_b_event_count_tests": str(output_path / "config_b_event_count_tests.csv"),
            "config_b_aggregated_event_tests": str(output_path / "config_b_aggregated_event_tests.csv"),
            "config_c_two_sided_matching": str(output_path / "config_c_two_sided_matching.csv"),
            "partner_integrity": str(output_path / "partner_integrity.csv"),
        },
    }
    (output_path / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def _seed_values(seeds: int | Sequence[int]) -> list[int]:
    if isinstance(seeds, int):
        if seeds <= 0:
            raise ValueError("seeds must be positive")
        return list(range(seeds))
    values = [int(seed) for seed in seeds]
    if not values:
        raise ValueError("seeds must not be empty")
    return values


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _spectral_constants(rates: Phase0VitalRates) -> list[dict[str, float | str]]:
    one_dimensional = build_leslie_matrix(rates)
    one_diag = spectral_diagnostics(one_dimensional, dt=rates.dt)
    nrr, generation_length = _nrr_and_generation_length(rates)

    index = MultiStateIndex(rates.omega)
    base_multistate = build_multistate_leslie_matrix(rates, SocialDynamicsConfig(), index=index)
    stable = stable_multistate_distribution(base_multistate)
    marital_curve = calibrate_marital_fertility_curve(rates, stable, index)
    multistate = build_multistate_leslie_matrix(
        rates,
        SocialDynamicsConfig(),
        index=index,
        marital_fertility_curve=marital_curve,
    )
    multi_diag = spectral_diagnostics(multistate, dt=rates.dt)
    adult_mass = 0.0
    adult_married = 0.0
    for age in range(18, rates.omega + 1):
        for sex in (Sex.FEMALE, Sex.MALE):
            single = stable[index.position(age, sex, MaritalState.SINGLE)]
            married = stable[index.position(age, sex, MaritalState.MARRIED)]
            adult_mass += single + married
            adult_married += married

    return [
        {
            "oracle": "one_dimensional",
            "lambda1": one_diag.lambda1,
            "growth_rate": one_diag.growth_rate,
            "annualized_growth_rate": one_diag.growth_rate,
            "damping_ratio": one_diag.damping_ratio,
            "cycle_period": "" if one_diag.cycle_period is None else one_diag.cycle_period,
            "e0": expected_life_at_birth(rates),
            "tfr": rates.tfr,
            "nrr": nrr,
            "generation_length": generation_length,
            "sign_consistency": int((one_diag.growth_rate >= 0.0) == (nrr >= 1.0)),
            "adult_married_share": "",
        },
        {
            "oracle": "multistate",
            "lambda1": multi_diag.lambda1,
            "growth_rate": multi_diag.growth_rate,
            "annualized_growth_rate": multi_diag.growth_rate,
            "damping_ratio": multi_diag.damping_ratio,
            "cycle_period": "" if multi_diag.cycle_period is None else multi_diag.cycle_period,
            "e0": expected_life_at_birth(rates),
            "tfr": rates.tfr,
            "nrr": nrr,
            "generation_length": generation_length,
            "sign_consistency": int((multi_diag.growth_rate >= 0.0) == (nrr >= 1.0)),
            "adult_married_share": adult_married / adult_mass if adult_mass > 0.0 else 0.0,
        },
    ]


def _run_seed_bundles(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seeds: list[int],
    start_date: date,
    workers: int,
) -> list[dict]:
    tasks = [(rates, n, years, seed, start_date) for seed in seeds]
    if workers <= 1 or len(tasks) <= 1:
        results = [_run_seed_bundle(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_run_seed_bundle, tasks))
    return sorted(results, key=lambda result: result["seed"])


def _run_seed_bundle(task: tuple[Phase0VitalRates, int, int, int, date]) -> dict:
    rates, n, years, seed, start_date = task
    return {
        "seed": seed,
        "config_a": _run_config_a_seed(rates, n=n, years=years, seed=seed, start_date=start_date),
        "config_b": _run_config_b_seed(rates, n=n, years=years, seed=seed, start_date=start_date),
        "config_c": _run_config_c_seed(rates, n=n, years=years, seed=seed, start_date=start_date),
    }


def _mortality_only_rates(rates: Phase0VitalRates) -> Phase0VitalRates:
    return Phase0VitalRates(
        makeham_a=rates.makeham_a,
        gompertz_b=rates.gompertz_b,
        gompertz_theta=rates.gompertz_theta,
        infant_extra=rates.infant_extra,
        tfr=0.0,
        fertility_peak_age=rates.fertility_peak_age,
        fertility_width=rates.fertility_width,
        sex_ratio_at_birth=rates.sex_ratio_at_birth,
        omega=rates.omega,
        dt=rates.dt,
    )


def _run_config_a_seed(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seed: int,
    start_date: date,
) -> dict:
    mortality_rates = _mortality_only_rates(rates)
    state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date, build_relationships=False)
    calendar_oracle = _CalendarExpectedOracle(mortality_rates, state.people, state.current_date)
    kernel = MicroDemographicKernel(
        mortality_rates,
        rng_seed=seed + 100_000,
        social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False, guardianship_enabled=False),
        fertility_mode="all_women",
    )
    initial_death_count = len(state.death_events)
    failures = 0
    tick_count = 0
    deviations_by_year: dict[int, list[float]] = {}
    event_counts_by_year: dict[int, dict[str, list[float]]] = {}
    tvs: list[float] = []
    for year_index in range(years):
        target_year = start_date.year + year_index + 1
        expected_deaths = np.zeros(rates.omega + 1, dtype=float)
        observed_deaths = np.zeros(rates.omega + 1, dtype=float)
        while state.current_date < date(target_year, 1, 1):
            before_deaths = len(state.death_events)
            result = kernel.tick(state)
            expected = calendar_oracle.tick()
            expected_deaths += expected["deaths_by_age"]
            for event in state.death_events[before_deaths:]:
                observed_deaths[min(max(0, event.age), rates.omega)] += 1.0
            tick_count += 1
            if result.new_headcount != result.old_headcount + result.births - result.deaths:
                failures += 1
        calendar_counts = calendar_oracle.counts_by_age()
        live_counts = count_alive_by_age(state.people, rates.omega)
        deviations_by_year[year_index] = (live_counts.astype(float) - calendar_counts).tolist()
        event_counts_by_year[year_index] = {
            "death_expected": expected_deaths.tolist(),
            "death_observed": observed_deaths.tolist(),
        }
        tvs.append(total_variation(live_counts, calendar_counts))
    deaths = len(state.death_events) - initial_death_count
    return {
        "row": {
            "seed": seed,
            "ticks": tick_count,
            "alive": state.alive_count,
            "deaths": deaths,
            "headcount_identity_failures": failures,
        },
        "failures": failures,
        "deaths": deaths,
        "deviations_by_year": deviations_by_year,
        "event_counts_by_year": event_counts_by_year,
        "tvs": tvs,
    }


def _run_config_b_seed(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seed: int,
    start_date: date,
) -> dict:
    birth_hook_count = 0
    death_hook_count = 0

    def birth_hook(_event, _person) -> None:
        nonlocal birth_hook_count
        birth_hook_count += 1

    def death_hook(_event, _person) -> None:
        nonlocal death_hook_count
        death_hook_count += 1

    state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date, build_relationships=False)
    annual_oracle = state.oracle()
    calendar_oracle = _CalendarExpectedOracle(rates, state.people, state.current_date)
    initial_alive = state.alive_count
    kernel = MicroDemographicKernel(
        rates,
        rng_seed=seed + 200_000,
        on_birth=birth_hook,
        on_death=death_hook,
        social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False, guardianship_enabled=False),
        fertility_mode="all_women",
    )
    rows: list[dict] = []
    deviations_by_year: dict[int, list[float]] = {}
    event_counts_by_year: dict[int, dict[str, list[float]]] = {}
    tvs: list[float] = []
    annual_tvs: list[float] = []
    failures = 0
    max_tv = 0.0
    max_annual_tv = 0.0
    for year_index in range(years):
        target_year = start_date.year + year_index + 1
        tick_count = 0
        year_failures = 0
        expected_deaths = np.zeros(rates.omega + 1, dtype=float)
        observed_deaths = np.zeros(rates.omega + 1, dtype=float)
        expected_births = np.zeros(rates.omega + 1, dtype=float)
        observed_births = np.zeros(rates.omega + 1, dtype=float)
        while state.current_date < date(target_year, 1, 1):
            before_deaths = len(state.death_events)
            before_births = len(state.birth_events)
            result = kernel.tick(state)
            expected = calendar_oracle.tick()
            expected_deaths += expected["deaths_by_age"]
            expected_births += expected["births_by_mother_age"]
            for event in state.death_events[before_deaths:]:
                observed_deaths[min(max(0, event.age), rates.omega)] += 1.0
            people_by_id = {person.id: person for person in state.people}
            for event in state.birth_events[before_births:]:
                mother = people_by_id.get(event.mother_id)
                if mother is not None:
                    observed_births[min(max(0, mother.completed_age_on(event.date)), rates.omega)] += 1.0
            tick_count += 1
            if result.new_headcount != result.old_headcount + result.births - result.deaths:
                year_failures += 1
        failures += year_failures
        annual_counts = annual_oracle.step()
        calendar_counts = calendar_oracle.counts_by_age()
        live_counts = count_alive_by_age(state.people, rates.omega)
        deviation = live_counts.astype(float) - calendar_counts
        deviations_by_year[year_index] = deviation.tolist()
        event_counts_by_year[year_index] = {
            "death_expected": expected_deaths.tolist(),
            "death_observed": observed_deaths.tolist(),
            "birth_expected": expected_births.tolist(),
            "birth_observed": observed_births.tolist(),
        }
        tv = total_variation(live_counts, calendar_counts)
        annual_tv = total_variation(live_counts, annual_counts)
        tvs.append(tv)
        annual_tvs.append(annual_tv)
        max_tv = max(max_tv, tv)
        max_annual_tv = max(max_annual_tv, annual_tv)
        rows.append({
            "seed": seed,
            "year": state.current_date.year - 1,
            "ticks": tick_count,
            "alive": int(live_counts.sum()),
            "oracle_alive": float(calendar_counts.sum()),
            "annual_leslie_alive": float(annual_counts.sum()),
            "tv_distance": tv,
            "annual_leslie_tv_distance": annual_tv,
            "headcount_identity_failures": year_failures,
        })
    growth_rate = float(np.log(state.alive_count / initial_alive) / years) if initial_alive > 0 and state.alive_count > 0 and years > 0 else 0.0
    oracle_initial_alive = float(n)
    oracle_final_alive = float(calendar_oracle.counts_by_age().sum())
    oracle_growth_rate = float(np.log(oracle_final_alive / oracle_initial_alive) / years) if oracle_initial_alive > 0.0 and oracle_final_alive > 0.0 and years > 0 else 0.0
    birth_events = len(state.birth_events)
    death_events = len(state.death_events)
    return {
        "rows": rows,
        "deviations_by_year": deviations_by_year,
        "event_counts_by_year": event_counts_by_year,
        "growth_rate": growth_rate,
        "oracle_growth_rate": oracle_growth_rate,
        "tvs": tvs,
        "annual_tvs": annual_tvs,
        "failures": failures,
        "max_tv": max_tv,
        "max_annual_tv": max_annual_tv,
        "birth_hook_count": birth_hook_count,
        "death_hook_count": death_hook_count,
        "birth_events": birth_events,
        "death_events": death_events,
        "dead_retained_count": sum(1 for person in state.people if not person.alive and person.death_tick is not None),
        "newborns_with_parent_id": sum(
            1
            for person in state.people
            if person.id >= n and (person.mother_id is not None or person.father_id is not None)
        ),
    }


def _run_config_c_seed(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seed: int,
    start_date: date,
) -> dict:
    state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date)
    kernel = MicroDemographicKernel(rates, rng_seed=seed + 300_000)
    failures, tick_count = _run_daily_years(state, kernel, years)
    health = social_health_snapshot(state)
    integrity = partner_integrity(state)
    return {
        "row": {
            "seed": seed,
            "ticks": tick_count,
            "alive": health.alive,
            "adults": health.adults,
            "minors": health.minors,
            "married_adult_share": health.married_adult_share,
            "minor_household_missing": health.minor_household_missing,
            "public_guardian_minors": health.public_guardian_minors,
            "marriages": health.marriages,
            "divorces": health.divorces,
            "headcount_identity_failures": failures,
        },
        "partner_row": {"seed": seed, **integrity},
        "failures": failures,
        "bad_partner_links": integrity["bad_partner_links"],
        "minor_household_missing": health.minor_household_missing,
    }


def _aggregate_config_a(
    rates: Phase0VitalRates,
    seed_results: list[dict],
    *,
    output_path: Path,
) -> dict[str, float | int]:
    rows = [result["config_a"]["row"] for result in seed_results]
    deviations_by_year: dict[int, list[np.ndarray]] = {}
    max_tv = 0.0
    for result in seed_results:
        config = result["config_a"]
        for year_index, deviation in config["deviations_by_year"].items():
            deviations_by_year.setdefault(int(year_index), []).append(np.asarray(deviation, dtype=float))
        if config["tvs"]:
            max_tv = max(max_tv, max(float(value) for value in config["tvs"]))
    _write_csv(output_path / "config_a_mortality.csv", rows)
    _write_csv(output_path / "config_a_ensemble_deviation.csv", _ensemble_deviation_rows(deviations_by_year))
    ensemble = _ensemble_alignment_metrics(deviations_by_year, [], build_leslie_matrix(rates), r_oracle=0.0)
    event_rows = _event_count_test_rows(seed_results, "config_a", ("death",))
    aggregated_event_rows = _aggregated_event_rows(event_rows)
    _write_csv(output_path / "config_a_event_count_tests.csv", event_rows)
    _write_csv(output_path / "config_a_aggregated_event_tests.csv", aggregated_event_rows)
    return {
        "headcount_identity_failures": sum(int(result["config_a"]["failures"]) for result in seed_results),
        "mean_final_alive": float(np.mean([row["alive"] for row in rows])) if rows else 0.0,
        "total_deaths": sum(int(result["config_a"]["deaths"]) for result in seed_results),
        "max_tv_distance": max_tv,
        **ensemble,
        **_event_count_summary(event_rows, aggregated_event_rows),
        "max_daily_survival_error": _max_daily_survival_error(rates),
        "cohort_survival_max_abs_error": _cohort_survival_max_abs_error(rates),
    }


def _aggregate_config_b(
    rates: Phase0VitalRates,
    seed_results: list[dict],
    *,
    n: int,
    seeds: list[int],
    output_path: Path,
) -> dict[str, float | int]:
    rows: list[dict] = []
    deviations_by_year: dict[int, list[np.ndarray]] = {}
    growth_rates: list[float] = []
    oracle_growth_rates: list[float] = []
    tv_by_seed: dict[int, list[float]] = {}
    failures = 0
    max_tv = 0.0
    max_annual_tv = 0.0
    birth_hook_count = 0
    death_hook_count = 0
    birth_events = 0
    death_events = 0
    dead_retained_count = 0
    newborns_with_parent_id = 0

    for result in seed_results:
        seed = int(result["seed"])
        config = result["config_b"]
        rows.extend(config["rows"])
        for year_index, deviation in config["deviations_by_year"].items():
            deviations_by_year.setdefault(int(year_index), []).append(np.asarray(deviation, dtype=float))
        growth_rates.append(float(config["growth_rate"]))
        oracle_growth_rates.append(float(config["oracle_growth_rate"]))
        tv_by_seed[seed] = [float(value) for value in config["tvs"]]
        failures += int(config["failures"])
        max_tv = max(max_tv, float(config["max_tv"]))
        max_annual_tv = max(max_annual_tv, float(config["max_annual_tv"]))
        birth_hook_count += int(config["birth_hook_count"])
        death_hook_count += int(config["death_hook_count"])
        birth_events += int(config["birth_events"])
        death_events += int(config["death_events"])
        dead_retained_count += int(config["dead_retained_count"])
        newborns_with_parent_id += int(config["newborns_with_parent_id"])

    rows.sort(key=lambda row: (row["seed"], row["year"]))
    _write_csv(output_path / "config_b_oracle_alignment.csv", rows)
    _write_csv(output_path / "config_b_ensemble_deviation.csv", _ensemble_deviation_rows(deviations_by_year))
    event_rows = _event_count_test_rows(seed_results, "config_b", ("death", "birth"))
    aggregated_event_rows = _aggregated_event_rows(event_rows)
    _write_csv(output_path / "config_b_event_count_tests.csv", event_rows)
    _write_csv(output_path / "config_b_aggregated_event_tests.csv", aggregated_event_rows)
    return {
        "headcount_identity_failures": failures,
        "max_tv_distance": max_tv,
        "annual_leslie_max_tv_distance": max_annual_tv,
        **_genesis_zero_transient_metrics(rates, n=n, seeds=seeds),
        **_ensemble_alignment_metrics(
            deviations_by_year,
            growth_rates,
            build_leslie_matrix(rates),
            r_oracle=float(np.mean(oracle_growth_rates)) if oracle_growth_rates else None,
        ),
        **_event_count_summary(event_rows, aggregated_event_rows),
        **_relaxation_metrics(build_leslie_matrix(rates)),
        "max_tv_slope": _max_tv_slope(tv_by_seed),
        "noop_economic_state_identical": _noop_economic_state_identical(rates),
        "birth_hook_count": birth_hook_count,
        "death_hook_count": death_hook_count,
        "birth_events": birth_events,
        "death_events": death_events,
        "dead_retained_count": dead_retained_count,
        "newborns_with_parent_id": newborns_with_parent_id,
        "hook_count_matches_events": int(birth_hook_count == birth_events and death_hook_count == death_events),
    }


def _noop_economic_state_identical(rates: Phase0VitalRates) -> int:
    left = create_genesis_population(rates, n=500, seed=91_007, start_date=date(2001, 1, 1), build_relationships=False)
    right = create_genesis_population(rates, n=500, seed=91_007, start_date=date(2001, 1, 1), build_relationships=False)
    kernel_left = MicroDemographicKernel(rates, rng_seed=91_008, fertility_mode="all_women")
    kernel_right = MicroDemographicKernel(rates, rng_seed=91_008, fertility_mode="all_women")
    result_left = kernel_left.tick(left)
    result_right = kernel_right.tick(right, economic_state={})
    if result_left != result_right:
        return 0
    left_projection = [(person.id, person.alive, person.age, person.death_tick) for person in left.people]
    right_projection = [(person.id, person.alive, person.age, person.death_tick) for person in right.people]
    return int(left_projection == right_projection)


def _aggregate_config_c_matching(
    seed_results: list[dict],
    *,
    output_path: Path,
) -> dict[str, float | int]:
    rows = [result["config_c"]["row"] for result in seed_results]
    partner_rows = [result["config_c"]["partner_row"] for result in seed_results]
    rows.sort(key=lambda row: row["seed"])
    partner_rows.sort(key=lambda row: row["seed"])
    _write_csv(output_path / "config_c_two_sided_matching.csv", rows)
    _write_csv(output_path / "partner_integrity.csv", partner_rows)
    return {
        "headcount_identity_failures": sum(int(result["config_c"]["failures"]) for result in seed_results),
        "bad_partner_links": max((int(result["config_c"]["bad_partner_links"]) for result in seed_results), default=0),
        "minor_household_missing": max((int(result["config_c"]["minor_household_missing"]) for result in seed_results), default=0),
        "mean_married_adult_share": float(np.mean([row["married_adult_share"] for row in rows])) if rows else 0.0,
    }


def _run_config_a_mortality_only(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seeds: list[int],
    start_date: date,
    output_path: Path,
) -> dict[str, float | int]:
    rows: list[dict] = []
    failures = 0
    total_deaths = 0
    mortality_rates = Phase0VitalRates(
        makeham_a=rates.makeham_a,
        gompertz_b=rates.gompertz_b,
        gompertz_theta=rates.gompertz_theta,
        infant_extra=rates.infant_extra,
        tfr=0.0,
        fertility_peak_age=rates.fertility_peak_age,
        fertility_width=rates.fertility_width,
        sex_ratio_at_birth=rates.sex_ratio_at_birth,
        omega=rates.omega,
        dt=rates.dt,
    )
    for seed in seeds:
        state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date, build_relationships=False)
        kernel = MicroDemographicKernel(
            mortality_rates,
            rng_seed=seed + 100_000,
            social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False, guardianship_enabled=False),
            fertility_mode="all_women",
        )
        before_deaths = len(state.death_events)
        seed_failures, tick_count = _run_daily_years(state, kernel, years)
        deaths = len(state.death_events) - before_deaths
        failures += seed_failures
        total_deaths += deaths
        rows.append({
            "seed": seed,
            "ticks": tick_count,
            "alive": state.alive_count,
            "deaths": deaths,
            "headcount_identity_failures": seed_failures,
        })
    _write_csv(output_path / "config_a_mortality.csv", rows)
    return {
        "headcount_identity_failures": failures,
        "mean_final_alive": float(np.mean([row["alive"] for row in rows])) if rows else 0.0,
        "total_deaths": total_deaths,
        "max_daily_survival_error": _max_daily_survival_error(rates),
        "cohort_survival_max_abs_error": _cohort_survival_max_abs_error(rates),
    }


def _run_config_b_ungated_fertility(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seeds: list[int],
    start_date: date,
    output_path: Path,
) -> dict[str, float | int]:
    rows: list[dict] = []
    deviations_by_year: dict[int, list[np.ndarray]] = {}
    growth_rates: list[float] = []
    tv_by_seed: dict[int, list[float]] = {}
    failures = 0
    max_tv = 0.0
    birth_hook_count = 0
    death_hook_count = 0
    birth_events = 0
    death_events = 0
    dead_retained_count = 0
    newborns_with_parent_id = 0

    def birth_hook(_event, _person) -> None:
        nonlocal birth_hook_count
        birth_hook_count += 1

    def death_hook(_event, _person) -> None:
        nonlocal death_hook_count
        death_hook_count += 1

    for seed in seeds:
        state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date, build_relationships=False)
        oracle = state.oracle()
        initial_alive = state.alive_count
        seed_tvs: list[float] = []
        kernel = MicroDemographicKernel(
            rates,
            rng_seed=seed + 200_000,
            on_birth=birth_hook,
            on_death=death_hook,
            social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False, guardianship_enabled=False),
            fertility_mode="all_women",
        )
        for year_index in range(years):
            target_year = start_date.year + year_index + 1
            seed_failures, tick_count = _run_until_year(state, kernel, target_year)
            failures += seed_failures
            oracle_counts = oracle.step()
            live_counts = count_alive_by_age(state.people, rates.omega)
            deviations_by_year.setdefault(year_index, []).append(live_counts.astype(float) - oracle_counts)
            tv = total_variation(live_counts, oracle_counts)
            seed_tvs.append(tv)
            max_tv = max(max_tv, tv)
            rows.append({
                "seed": seed,
                "year": state.current_date.year - 1,
                "ticks": tick_count,
                "alive": int(live_counts.sum()),
                "oracle_alive": float(oracle_counts.sum()),
                "tv_distance": tv,
                "headcount_identity_failures": seed_failures,
            })
        if initial_alive > 0 and state.alive_count > 0 and years > 0:
            growth_rates.append(float(np.log(state.alive_count / initial_alive) / years))
        tv_by_seed[seed] = seed_tvs
        birth_events += len(state.birth_events)
        death_events += len(state.death_events)
        dead_retained_count += sum(1 for person in state.people if not person.alive and person.death_tick is not None)
        newborns_with_parent_id += sum(
            1
            for person in state.people
            if person.id >= n and (person.mother_id is not None or person.father_id is not None)
        )
    _write_csv(output_path / "config_b_oracle_alignment.csv", rows)
    return {
        "headcount_identity_failures": failures,
        "max_tv_distance": max_tv,
        **_genesis_zero_transient_metrics(rates, n=n, seeds=seeds),
        **_ensemble_alignment_metrics(deviations_by_year, growth_rates, build_leslie_matrix(rates)),
        **_relaxation_metrics(build_leslie_matrix(rates)),
        "max_tv_slope": _max_tv_slope(tv_by_seed),
        "birth_hook_count": birth_hook_count,
        "death_hook_count": death_hook_count,
        "birth_events": birth_events,
        "death_events": death_events,
        "dead_retained_count": dead_retained_count,
        "newborns_with_parent_id": newborns_with_parent_id,
        "hook_count_matches_events": int(birth_hook_count == birth_events and death_hook_count == death_events),
    }


def _config_c_multistate_oracle(rates: Phase0VitalRates) -> dict[str, float]:
    index = MultiStateIndex(rates.omega)
    matrix = build_multistate_leslie_matrix(rates, SocialDynamicsConfig(), index=index)
    stable = stable_multistate_distribution(matrix)
    adult_mass = 0.0
    adult_married = 0.0
    fertile_female_mass = 0.0
    fertile_female_married = 0.0
    band_mass: dict[str, float] = {}
    band_married: dict[str, float] = {}
    band_targets: dict[str, float] = {}
    profile = SocialDynamicsConfig().union_target_profile
    for age in range(rates.omega + 1):
        age_mass = 0.0
        age_married = 0.0
        for sex in (Sex.FEMALE, Sex.MALE):
            single = stable[index.position(age, sex, MaritalState.SINGLE)]
            married = stable[index.position(age, sex, MaritalState.MARRIED)]
            age_mass += single + married
            age_married += married
            if age >= 18:
                adult_mass += single + married
                adult_married += married
            if sex == Sex.FEMALE and 15 <= age <= 49:
                fertile_female_mass += single + married
                fertile_female_married += married
        band = profile.band_for_age(age) if profile is not None else None
        if band is not None and age_mass > 0.0:
            label = band.label
            band_mass[label] = band_mass.get(label, 0.0) + age_mass
            band_married[label] = band_married.get(label, 0.0) + age_married
            band_targets[label] = band.target_share
    band_errors = [
        abs(band_married[label] / band_mass[label] - band_targets[label])
        for label in band_mass
        if band_mass[label] > 0.0
    ]
    return {
        "adult_married_share": float(adult_married / adult_mass) if adult_mass > 0.0 else 0.0,
        "fertile_female_married_share": float(
            fertile_female_married / fertile_female_mass
        ) if fertile_female_mass > 0.0 else 0.0,
        "married_profile_max_abs_error": float(max(band_errors)) if band_errors else 0.0,
    }


def _run_config_c_two_sided_matching(
    rates: Phase0VitalRates,
    *,
    n: int,
    years: int,
    seeds: list[int],
    start_date: date,
    output_path: Path,
) -> dict[str, float | int]:
    rows: list[dict] = []
    partner_rows: list[dict] = []
    failures = 0
    max_bad_links = 0
    max_minor_missing = 0
    for seed in seeds:
        state = create_genesis_population(rates, n=n, seed=seed, start_date=start_date)
        kernel = MicroDemographicKernel(rates, rng_seed=seed + 300_000)
        seed_failures, tick_count = _run_daily_years(state, kernel, years)
        failures += seed_failures
        health = social_health_snapshot(state)
        integrity = partner_integrity(state)
        max_bad_links = max(max_bad_links, integrity["bad_partner_links"])
        max_minor_missing = max(max_minor_missing, health.minor_household_missing)
        rows.append({
            "seed": seed,
            "ticks": tick_count,
            "alive": health.alive,
            "adults": health.adults,
            "minors": health.minors,
            "married_adult_share": health.married_adult_share,
            "minor_household_missing": health.minor_household_missing,
            "public_guardian_minors": health.public_guardian_minors,
            "marriages": health.marriages,
            "divorces": health.divorces,
            "headcount_identity_failures": seed_failures,
        })
        partner_rows.append({"seed": seed, **integrity})
    _write_csv(output_path / "config_c_two_sided_matching.csv", rows)
    _write_csv(output_path / "partner_integrity.csv", partner_rows)
    return {
        "headcount_identity_failures": failures,
        "bad_partner_links": max_bad_links,
        "minor_household_missing": max_minor_missing,
        "mean_married_adult_share": float(np.mean([row["married_adult_share"] for row in rows])) if rows else 0.0,
    }


def _run_daily_years(state, kernel: MicroDemographicKernel, years: int) -> tuple[int, int]:
    start_year = state.current_date.year
    return _run_until_year(state, kernel, start_year + years)


def _max_daily_survival_error(rates: Phase0VitalRates, *, days: int = 365) -> float:
    errors = []
    dt = 1.0 / days
    for age in range(rates.omega):
        daily = 1.0
        for day in range(days):
            daily *= rates.survival_probability(age + day * dt, dt=dt)
        annual = rates.survival_probability(age, dt=1.0)
        errors.append(abs(daily - annual))
    return float(max(errors)) if errors else 0.0


def _cohort_survival_max_abs_error(rates: Phase0VitalRates, *, days: int = 365) -> float:
    dt = 1.0 / days
    annual = _survivorship_curve(rates)
    daily_values = [1.0]
    daily = 1.0
    for age in range(rates.omega):
        for day in range(days):
            daily *= rates.survival_probability(age + day * dt, dt=dt)
        daily_values.append(daily)
    daily_curve = np.asarray(daily_values, dtype=float)
    return float(np.max(np.abs(daily_curve - annual)))


def _run_until_year(state, kernel: MicroDemographicKernel, target_year: int) -> tuple[int, int]:
    failures = 0
    ticks = 0
    while state.current_date < date(target_year, 1, 1):
        result = kernel.tick(state)
        ticks += 1
        if result.new_headcount != result.old_headcount + result.births - result.deaths:
            failures += 1
    return failures, ticks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run layered Phase 0 demographic validation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--n", type=int, default=5_000)
    parser.add_argument("--years", type=int, default=80)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2001, 1, 1))
    args = parser.parse_args(argv)
    summary = run_phase0_validation(
        output_dir=args.output_dir,
        n=args.n,
        years=args.years,
        seeds=args.seeds,
        workers=args.workers,
        start_date=args.start_date,
    )
    print(f"output_dir: {args.output_dir}")
    print(f"passed: {summary['passed']}")
    for name, config in summary["configs"].items():
        print(f"{name}: {config}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
