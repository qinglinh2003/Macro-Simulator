import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.phase0 import generate_phase0_artifacts
from macro_sim.demographics.relationships import RelationshipConfig
from macro_sim.demographics.union import MEDIUM_FAMILY_FORMATION_PROFILE, partnered_share_by_band


def test_genesis_relationships_derive_households_from_population():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=5_000, seed=101)
    stats = state.relationship_stats

    assert stats is not None
    assert stats.population == 5_000
    assert stats.households > 0
    assert stats.households < stats.population
    assert stats.adults + stats.minors == stats.population
    assert stats.minor_placement_rate == 1.0
    assert stats.max_household_size >= 1

    household_ids = {person.household_id for person in state.people}
    assert None not in household_ids
    assert len(household_ids) == stats.households


def test_strict_parent_links_respect_sex_and_age_gap_constraints():
    rates = Phase0VitalRates()
    config = RelationshipConfig(parent_min_age_gap=15, parent_max_age_gap=50)
    state = create_genesis_population(rates, n=8_000, seed=202, relationship_config=config)
    people = {person.id: person for person in state.people}

    minors = [person for person in state.people if person.age < config.adult_age]
    assert minors

    for child in minors:
        assert child.household_id is not None
        if child.mother_id is not None:
            mother = people[child.mother_id]
            assert mother.sex == "F"
            assert config.parent_min_age_gap <= mother.age - child.age <= config.parent_max_age_gap
            assert mother.household_id == child.household_id
        if child.father_id is not None:
            father = people[child.father_id]
            assert father.sex == "M"
            assert config.parent_min_age_gap <= father.age - child.age <= config.parent_max_age_gap
            assert father.household_id == child.household_id

    covered = [child for child in minors if child.mother_id is not None or child.father_id is not None]
    assert len(covered) / len(minors) > 0.85


def test_relationship_stats_reconcile_minor_parent_categories():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=6_000, seed=303)
    stats = state.relationship_stats

    assert stats is not None
    shares = (
        stats.dual_parent_minor_share
        + stats.mother_only_minor_share
        + stats.father_only_minor_share
        + stats.guardian_only_minor_share
    )
    assert math.isclose(shares, 1.0, abs_tol=1e-12)
    assert 0.0 <= stats.partnered_adult_share <= 1.0
    assert 0.0 <= stats.households_with_minors_share <= 1.0
    assert stats.avg_household_size >= 1.0


def test_relationship_matching_uses_soft_age_targets_not_single_point():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=12_000, seed=505)
    stats = state.relationship_stats

    assert stats is not None
    assert stats.mother_age_gap_p10 < stats.mother_age_gap_p90
    assert stats.father_age_gap_p10 < stats.father_age_gap_p90
    assert stats.spouse_age_gap_p90 > 0.0
    assert stats.dual_parent_minor_share < 0.98


def test_genesis_partner_matching_follows_age_specific_union_profile():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=20_000, seed=606)

    shares = partnered_share_by_band(state.people, MEDIUM_FAMILY_FORMATION_PROFILE)

    assert abs(shares["18-24"] - 0.10) < 0.07
    assert abs(shares["25-34"] - 0.58) < 0.08
    assert abs(shares["35-49"] - 0.74) < 0.08
    assert abs(shares["50-64"] - 0.68) < 0.10
    assert abs(shares["65-74"] - 0.55) < 0.12
    assert abs(shares["75-100"] - 0.32) < 0.14


def test_phase0_artifacts_include_relationship_stats(tmp_path):
    metrics = generate_phase0_artifacts(output_dir=tmp_path, n=2_000, seed=404)

    assert "relationship_stats" in metrics
    assert metrics["relationship_stats"]["population"] == 2_000
    assert metrics["relationship_stats"]["minor_placement_rate"] == 1.0

    written = json.loads((tmp_path / "metrics.json").read_text())
    assert written["relationship_stats"]["households"] == metrics["relationship_stats"]["households"]
