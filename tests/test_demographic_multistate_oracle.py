import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates
from macro_sim.demographics.multistate import (
    MaritalState,
    MultiStateIndex,
    Sex,
    build_multistate_leslie_matrix,
    calibrate_marital_fertility_curve,
    married_female_share_by_age,
    stable_multistate_distribution,
)
from macro_sim.demographics.social import SocialDynamicsConfig
from macro_sim.demographics.union import MEDIUM_FAMILY_FORMATION_PROFILE


def test_multistate_index_maps_age_sex_marital_state_to_flat_position():
    index = MultiStateIndex(omega=100)

    assert index.size == 404
    assert index.position(0, Sex.FEMALE, MaritalState.SINGLE) == 0
    assert index.position(0, Sex.FEMALE, MaritalState.MARRIED) == 1
    assert index.position(0, Sex.MALE, MaritalState.SINGLE) == 2
    assert index.position(0, Sex.MALE, MaritalState.MARRIED) == 3
    assert index.decode(403) == (100, Sex.MALE, MaritalState.MARRIED)


def test_multistate_matrix_has_stable_joint_distribution_and_married_profile():
    rates = Phase0VitalRates()
    social = SocialDynamicsConfig()
    index = MultiStateIndex(omega=rates.omega)
    matrix = build_multistate_leslie_matrix(rates, social, index=index)
    stable = stable_multistate_distribution(matrix)
    profile = married_female_share_by_age(stable, index)

    assert matrix.shape == (index.size, index.size)
    assert stable.shape == (index.size,)
    assert math.isclose(float(stable.sum()), 1.0)
    assert np.all(stable >= 0.0)
    assert profile.shape == (rates.omega + 1,)
    assert np.all((profile >= 0.0) & (profile <= 1.0))
    assert profile[28] > profile[16]


def test_marital_fertility_calibration_matches_target_tfr_under_married_profile():
    rates = Phase0VitalRates(tfr=2.5)
    social = SocialDynamicsConfig()
    index = MultiStateIndex(omega=rates.omega)
    matrix = build_multistate_leslie_matrix(rates, social, index=index)
    stable = stable_multistate_distribution(matrix)
    marital_curve = calibrate_marital_fertility_curve(rates, stable, index)
    married_profile = married_female_share_by_age(stable, index)
    implied_tfr = float(np.sum(marital_curve * married_profile * rates.dt))

    assert marital_curve.shape == (rates.omega + 1,)
    assert marital_curve[:15].sum() == 0.0
    assert marital_curve[50:].sum() == 0.0
    assert math.isclose(implied_tfr, rates.tfr, rel_tol=1e-10)
    assert marital_curve[28] > rates.fertility_curve()[28]


def test_multistate_oracle_anchors_to_default_union_profile():
    rates = Phase0VitalRates()
    social = SocialDynamicsConfig()
    index = MultiStateIndex(omega=rates.omega)
    matrix = build_multistate_leslie_matrix(rates, social, index=index)
    stable = stable_multistate_distribution(matrix)
    profile = MEDIUM_FAMILY_FORMATION_PROFILE

    adult_mass = 0.0
    adult_married = 0.0
    fertile_female_mass = 0.0
    fertile_female_married = 0.0
    target_adult_mass = 0.0
    target_adult_married = 0.0
    target_fertile_female_mass = 0.0
    target_fertile_female_married = 0.0
    for age in range(rates.omega + 1):
        for sex in (Sex.FEMALE, Sex.MALE):
            single = stable[index.position(age, sex, MaritalState.SINGLE)]
            married = stable[index.position(age, sex, MaritalState.MARRIED)]
            mass = single + married
            if age >= 18:
                adult_mass += mass
                adult_married += married
                target_adult_mass += mass
                target_adult_married += mass * profile.target_share(age)
            if sex == Sex.FEMALE and 15 <= age <= 49:
                fertile_female_mass += mass
                fertile_female_married += married
                target_fertile_female_mass += mass
                target_fertile_female_married += mass * profile.target_share(age)

    adult_share = adult_married / adult_mass
    fertile_female_share = fertile_female_married / fertile_female_mass
    target_adult_share = target_adult_married / target_adult_mass
    target_fertile_female_share = target_fertile_female_married / target_fertile_female_mass

    assert abs(adult_share - target_adult_share) < 0.05
    assert abs(fertile_female_share - target_fertile_female_share) < 0.05
