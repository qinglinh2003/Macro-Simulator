"""Sex-aware two-state marital Leslie oracle for marital fertility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import exp

import numpy as np

from macro_sim.demographics.rates import Phase0VitalRates
from macro_sim.demographics.social import SocialDynamicsConfig


class Sex(IntEnum):
    FEMALE = 0
    MALE = 1


class MaritalState(IntEnum):
    SINGLE = 0
    MARRIED = 1


@dataclass(frozen=True)
class MultiStateIndex:
    omega: int

    @property
    def size(self) -> int:
        return (self.omega + 1) * 2 * 2

    def position(self, age: int, sex: Sex, marital: MaritalState) -> int:
        if age < 0 or age > self.omega:
            raise ValueError("age out of bounds")
        return ((age * 2 + int(sex)) * 2 + int(marital))

    def decode(self, position: int) -> tuple[int, Sex, MaritalState]:
        if position < 0 or position >= self.size:
            raise ValueError("position out of bounds")
        marital = MaritalState(position % 2)
        sex = Sex((position // 2) % 2)
        age = position // 4
        return age, sex, marital


def build_multistate_leslie_matrix(
    rates: Phase0VitalRates,
    social: SocialDynamicsConfig,
    *,
    index: MultiStateIndex | None = None,
    marital_fertility_curve: np.ndarray | None = None,
) -> np.ndarray:
    index = index or MultiStateIndex(rates.omega)
    fertility = rates.fertility_curve() if marital_fertility_curve is None else np.asarray(marital_fertility_curve, dtype=float)
    if fertility.shape != (rates.omega + 1,):
        raise ValueError("fertility curve shape must be omega + 1")

    matrix = np.zeros((index.size, index.size), dtype=float)
    for age in range(rates.omega + 1):
        married_female = index.position(age, Sex.FEMALE, MaritalState.MARRIED)
        matrix[index.position(0, Sex.FEMALE, MaritalState.SINGLE), married_female] += rates.female_birth_share * fertility[age] * rates.dt
        matrix[index.position(0, Sex.MALE, MaritalState.SINGLE), married_female] += rates.male_birth_share * fertility[age] * rates.dt

        if age >= rates.omega:
            continue
        survival = rates.survival_probability(age)
        for sex in (Sex.FEMALE, Sex.MALE):
            p_exit = _annual_marriage_exit_probability(age, sex, rates, social)
            p_marry = _annual_marriage_probability(age, sex, rates, social, p_exit)
            source_single = index.position(age, sex, MaritalState.SINGLE)
            source_married = index.position(age, sex, MaritalState.MARRIED)
            dest_single = index.position(age + 1, sex, MaritalState.SINGLE)
            dest_married = index.position(age + 1, sex, MaritalState.MARRIED)
            matrix[dest_single, source_single] += survival * (1.0 - p_marry)
            matrix[dest_married, source_single] += survival * p_marry
            matrix[dest_married, source_married] += survival * (1.0 - p_exit)
            matrix[dest_single, source_married] += survival * p_exit
    return matrix


def stable_multistate_distribution(matrix: np.ndarray) -> np.ndarray:
    values, vectors = np.linalg.eig(matrix)
    idx = int(np.argmax(values.real))
    vector = vectors[:, idx].real
    if vector.sum() < 0.0:
        vector = -vector
    vector = np.clip(vector, 0.0, None)
    total = float(vector.sum())
    if total <= 0.0:
        raise ValueError("dominant multistate eigenvector has zero non-negative mass")
    return vector / total


def married_female_share_by_age(stable_vector: np.ndarray, index: MultiStateIndex) -> np.ndarray:
    shares = np.zeros(index.omega + 1, dtype=float)
    for age in range(index.omega + 1):
        single = stable_vector[index.position(age, Sex.FEMALE, MaritalState.SINGLE)]
        married = stable_vector[index.position(age, Sex.FEMALE, MaritalState.MARRIED)]
        denom = single + married
        shares[age] = 0.0 if denom <= 0.0 else float(married / denom)
    return shares


def calibrate_marital_fertility_curve(
    rates: Phase0VitalRates,
    stable_vector: np.ndarray,
    index: MultiStateIndex,
) -> np.ndarray:
    shape = rates.fertility_shape_curve()
    married_profile = married_female_share_by_age(stable_vector, index)
    weighted_area = float(np.sum(shape * married_profile * rates.dt))
    if weighted_area <= 0.0:
        raise ValueError("married female profile gives zero fertility support")
    return shape * (rates.tfr / weighted_area)


def _annual_marriage_probability(
    age: int,
    sex: Sex,
    rates: Phase0VitalRates,
    social: SocialDynamicsConfig,
    p_exit: float,
) -> float:
    if not social.marriage_enabled:
        return 0.0
    if social.union_target_profile is not None:
        if age + 1 < social.marriage_min_age or age > social.marriage_max_age:
            return 0.0
        current_share = social.union_target_profile.target_share(age)
        next_share = social.union_target_profile.target_share(min(age + 1, rates.omega))
        single_share = 1.0 - current_share
        if single_share <= 1e-12:
            return 0.0
        probability = (next_share - current_share * (1.0 - p_exit)) / single_share
        return float(np.clip(probability, 0.0, 1.0))
    if age < social.marriage_min_age or age > social.marriage_max_age:
        return 0.0
    rate = social.annual_marriage_rate_peak * exp(
        -0.5 * ((age - social.marriage_peak_age) / social.marriage_age_width) ** 2
    )
    if sex == Sex.MALE:
        # Approximate the male age profile from a female-centered marriage market
        # where husbands are slightly older on average.
        male_equivalent_age = age - social.marriage_age_gap_mean
        rate = social.annual_marriage_rate_peak * exp(
            -0.5 * ((male_equivalent_age - social.marriage_peak_age) / social.marriage_age_width) ** 2
        )
    return float(np.clip(1.0 - exp(-rate), 0.0, 1.0))


def _annual_marriage_exit_probability(
    age: int,
    sex: Sex,
    rates: Phase0VitalRates,
    social: SocialDynamicsConfig,
) -> float:
    if not social.divorce_enabled:
        divorce_rate = 0.0
    else:
        divorce_rate = social.annual_divorce_rate_base
    spouse_age = age + social.marriage_age_gap_mean if sex == Sex.FEMALE else age - social.marriage_age_gap_mean
    spouse_age = float(np.clip(spouse_age, 0.0, rates.omega))
    spouse_death_probability = 1.0 - rates.survival_probability(spouse_age, dt=1.0)
    annual_exit = divorce_rate + spouse_death_probability
    return float(np.clip(1.0 - exp(-annual_exit), 0.0, 1.0))
