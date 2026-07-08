"""Genesis-time kinship and household construction for the demographic kernel."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median

import numpy as np

from macro_sim.demographics.agents import Person
from macro_sim.demographics.union import MEDIUM_FAMILY_FORMATION_PROFILE, UnionTargetProfile


@dataclass(frozen=True)
class RelationshipConfig:
    adult_age: int = 18
    parent_min_age_gap: int = 15
    parent_max_age_gap: int = 50
    ideal_parent_age_gap: int = 28
    parent_age_gap_sd: float = 6.0
    spouse_max_age_gap: int = 18
    spouse_age_gap_sd: float = 4.5
    union_target_profile: UnionTargetProfile | None = field(default_factory=lambda: MEDIUM_FAMILY_FORMATION_PROFILE)
    target_partnered_adult_share: float = 0.55
    two_parent_assignment_share: float = 0.82
    max_children_per_parent: int = 6
    max_children_per_household: int = 8


@dataclass(frozen=True)
class RelationshipStats:
    population: int
    adults: int
    minors: int
    households: int
    avg_household_size: float
    median_household_size: float
    max_household_size: int
    partnered_adult_share: float
    couple_household_share: float
    households_with_minors_share: float
    single_parent_household_share: float
    minor_placement_rate: float
    minor_parent_coverage_rate: float
    dual_parent_minor_share: float
    mother_only_minor_share: float
    father_only_minor_share: float
    guardian_only_minor_share: float
    guardian_only_minors: int
    mother_age_gap_mean: float
    mother_age_gap_p10: float
    mother_age_gap_p50: float
    mother_age_gap_p90: float
    father_age_gap_mean: float
    father_age_gap_p10: float
    father_age_gap_p50: float
    father_age_gap_p90: float
    spouse_age_gap_mean: float
    spouse_age_gap_p50: float
    spouse_age_gap_p90: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def build_genesis_relationships(
    people: list[Person],
    *,
    config: RelationshipConfig | None = None,
    seed: int = 0,
) -> RelationshipStats:
    """Fill partner, parent, and household IDs for a genesis population.

    Household count is an output of matching. Parent IDs are strict biological
    links: if no legal sex/age-gap parent exists, the child is placed in an
    adult guardian household without fabricating a mother or father.
    """

    config = config or RelationshipConfig()
    rng = np.random.default_rng(seed)
    for person in people:
        person.mother_id = None
        person.father_id = None
        person.household_id = None
        person.partner_id = None

    adults = [person for person in people if person.alive and person.age >= config.adult_age]
    minors = [person for person in people if person.alive and person.age < config.adult_age]
    if minors and not adults:
        raise ValueError("cannot place minors without at least one adult")

    _match_partners(adults, config=config, rng=rng)
    household_members = _create_adult_households(adults)

    adult_by_id = {person.id: person for person in adults}
    household_children = {household_id: 0 for household_id in household_members}
    parent_capacity = {person.id: config.max_children_per_parent for person in adults}
    by_sex_age = _index_adults_by_sex_age(adults, rng=rng)

    guardian_only = 0
    for child in sorted(minors, key=lambda person: person.age, reverse=True):
        ideal_gap = float(
            np.clip(
                rng.normal(config.ideal_parent_age_gap, config.parent_age_gap_sd),
                config.parent_min_age_gap,
                config.parent_max_age_gap,
            )
        )
        prefer_two_parent = rng.random() < config.two_parent_assignment_share
        if prefer_two_parent:
            assigned = (
                _assign_to_two_parent_household(child, adult_by_id, by_sex_age, household_children, parent_capacity, config, ideal_gap)
                or _assign_to_single_parent(child, "F", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=True)
                or _assign_to_single_parent(child, "M", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=True)
                or _assign_to_single_parent(child, "F", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=False)
                or _assign_to_single_parent(child, "M", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=False)
            )
        else:
            assigned = (
                _assign_to_single_parent(child, "F", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=True)
                or _assign_to_single_parent(child, "M", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=True)
                or _assign_to_two_parent_household(child, adult_by_id, by_sex_age, household_children, parent_capacity, config, ideal_gap)
                or _assign_to_single_parent(child, "F", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=False)
                or _assign_to_single_parent(child, "M", by_sex_age, household_children, parent_capacity, config, ideal_gap, unpartnered_only=False)
            )
        if not assigned:
            guardian_household = min(household_members, key=lambda household_id: (len(household_members[household_id]), household_id))
            child.household_id = guardian_household
            household_children[guardian_household] += 1
            guardian_only += 1
        household_members[child.household_id].append(child.id)

    return _relationship_stats(people, adults, minors, household_members, guardian_only)


def _match_partners(adults: list[Person], *, config: RelationshipConfig, rng: np.random.Generator) -> None:
    if config.union_target_profile is not None:
        _match_partners_by_union_profile(adults, config=config, rng=rng)
        return
    _match_partners_flat(adults, config=config, rng=rng)


def _match_partners_by_union_profile(adults: list[Person], *, config: RelationshipConfig, rng: np.random.Generator) -> None:
    males_by_age: dict[int, list[Person]] = {}
    males = [person for person in adults if person.sex == "M"]
    rng.shuffle(males)
    for male in males:
        males_by_age.setdefault(male.age, []).append(male)

    assert config.union_target_profile is not None
    for band in config.union_target_profile.bands:
        females = [
            person
            for person in adults
            if person.sex == "F"
            and person.partner_id is None
            and band.contains(person.age)
        ]
        rng.shuffle(females)
        target_females = min(len(females), int(round(band.target_share * len(females))))
        couples = 0
        for female in females:
            if couples >= target_females:
                break
            target_age = female.age + rng.normal(0.0, config.spouse_age_gap_sd)
            partner = _pop_male_near_target(female.age, target_age, males_by_age, config.spouse_max_age_gap)
            if partner is None:
                continue
            female.partner_id = partner.id
            partner.partner_id = female.id
            couples += 1


def _match_partners_flat(adults: list[Person], *, config: RelationshipConfig, rng: np.random.Generator) -> None:
    females = [person for person in adults if person.sex == "F"]
    males_by_age: dict[int, list[Person]] = {}
    males = [person for person in adults if person.sex == "M"]
    rng.shuffle(females)
    rng.shuffle(males)
    for male in males:
        males_by_age.setdefault(male.age, []).append(male)

    target_couples = min(
        len(females),
        len(males),
        int(round(config.target_partnered_adult_share * len(adults) / 2.0)),
    )
    couples = 0
    for female in females:
        if couples >= target_couples:
            break
        target_age = female.age + rng.normal(0.0, config.spouse_age_gap_sd)
        partner = _pop_male_near_target(female.age, target_age, males_by_age, config.spouse_max_age_gap)
        if partner is None:
            continue
        female.partner_id = partner.id
        partner.partner_id = female.id
        couples += 1


def _pop_male_near_target(
    female_age: int,
    target_age: float,
    males_by_age: dict[int, list[Person]],
    max_gap: int,
) -> Person | None:
    candidate_ages = range(female_age - max_gap, female_age + max_gap + 1)
    for candidate_age in sorted(candidate_ages, key=lambda age: (abs(age - target_age), abs(age - female_age), age)):
        bucket = males_by_age.get(candidate_age)
        while bucket:
            candidate = bucket.pop()
            if candidate.partner_id is None:
                return candidate
    return None


def _candidate_ages(age: int, gap: int) -> tuple[int, ...]:
    if gap == 0:
        return (age,)
    return (age - gap, age + gap)


def _create_adult_households(adults: list[Person]) -> dict[int, list[int]]:
    household_members: dict[int, list[int]] = {}
    seen: set[int] = set()
    household_id = 0
    adult_by_id = {person.id: person for person in adults}
    for adult in sorted(adults, key=lambda person: person.id):
        if adult.id in seen:
            continue
        partner = adult_by_id.get(adult.partner_id) if adult.partner_id is not None else None
        members = [adult]
        if partner is not None and partner.id not in seen:
            members.append(partner)
        for member in members:
            member.household_id = household_id
            seen.add(member.id)
        household_members[household_id] = [member.id for member in members]
        household_id += 1
    return household_members


def _index_adults_by_sex_age(adults: list[Person], *, rng: np.random.Generator) -> dict[str, dict[int, list[Person]]]:
    by_sex_age: dict[str, dict[int, list[Person]]] = {"F": {}, "M": {}}
    for adult in adults:
        by_sex_age.setdefault(adult.sex, {}).setdefault(adult.age, []).append(adult)
    for age_map in by_sex_age.values():
        for bucket in age_map.values():
            rng.shuffle(bucket)
    return by_sex_age


def _assign_to_two_parent_household(
    child: Person,
    adult_by_id: dict[int, Person],
    by_sex_age: dict[str, dict[int, list[Person]]],
    household_children: dict[int, int],
    parent_capacity: dict[int, int],
    config: RelationshipConfig,
    ideal_gap: float,
) -> bool:
    for mother in _strict_parent_candidates(child, "F", by_sex_age, config, ideal_gap):
        father = adult_by_id.get(mother.partner_id) if mother.partner_id is not None else None
        if father is None or father.sex != "M":
            continue
        if not _valid_parent_age_gap(father, child, config):
            continue
        if parent_capacity[mother.id] <= 0 or parent_capacity[father.id] <= 0:
            continue
        household_id = mother.household_id
        if household_id is None or household_children[household_id] >= config.max_children_per_household:
            continue
        child.mother_id = mother.id
        child.father_id = father.id
        child.household_id = household_id
        parent_capacity[mother.id] -= 1
        parent_capacity[father.id] -= 1
        household_children[household_id] += 1
        return True
    return False


def _assign_to_single_parent(
    child: Person,
    sex: str,
    by_sex_age: dict[str, dict[int, list[Person]]],
    household_children: dict[int, int],
    parent_capacity: dict[int, int],
    config: RelationshipConfig,
    ideal_gap: float,
    *,
    unpartnered_only: bool,
) -> bool:
    for parent in _strict_parent_candidates(child, sex, by_sex_age, config, ideal_gap):
        if unpartnered_only and parent.partner_id is not None:
            continue
        if parent_capacity[parent.id] <= 0:
            continue
        household_id = parent.household_id
        if household_id is None or household_children[household_id] >= config.max_children_per_household:
            continue
        if sex == "F":
            child.mother_id = parent.id
        else:
            child.father_id = parent.id
        child.household_id = household_id
        parent_capacity[parent.id] -= 1
        household_children[household_id] += 1
        return True
    return False


def _strict_parent_candidates(
    child: Person,
    sex: str,
    by_sex_age: dict[str, dict[int, list[Person]]],
    config: RelationshipConfig,
    ideal_gap: float,
):
    for gap in _ordered_gaps(config.parent_min_age_gap, config.parent_max_age_gap, ideal_gap):
        parent_age = child.age + gap
        for parent in by_sex_age.get(sex, {}).get(parent_age, []):
            if _valid_parent_age_gap(parent, child, config):
                yield parent


def _ordered_gaps(min_gap: int, max_gap: int, ideal_gap: int) -> list[int]:
    return sorted(range(min_gap, max_gap + 1), key=lambda gap: (abs(gap - ideal_gap), gap))


def _valid_parent_age_gap(parent: Person, child: Person, config: RelationshipConfig) -> bool:
    gap = parent.age - child.age
    return config.parent_min_age_gap <= gap <= config.parent_max_age_gap


def _relationship_stats(
    people: list[Person],
    adults: list[Person],
    minors: list[Person],
    household_members: dict[int, list[int]],
    guardian_only: int,
) -> RelationshipStats:
    people_by_id = {person.id: person for person in people}
    household_sizes = [len(members) for members in household_members.values()]
    household_adult_counts = {
        household_id: sum(1 for person_id in members if people_by_id[person_id].age >= 18)
        for household_id, members in household_members.items()
    }
    household_minor_counts = {
        household_id: sum(1 for person_id in members if people_by_id[person_id].age < 18)
        for household_id, members in household_members.items()
    }
    mother_gaps = [people_by_id[child.mother_id].age - child.age for child in minors if child.mother_id is not None]
    father_gaps = [people_by_id[child.father_id].age - child.age for child in minors if child.father_id is not None]
    spouse_gaps = [
        abs(person.age - people_by_id[person.partner_id].age)
        for person in adults
        if person.partner_id is not None and person.id < person.partner_id
    ]
    dual = sum(1 for child in minors if child.mother_id is not None and child.father_id is not None)
    mother_only = sum(1 for child in minors if child.mother_id is not None and child.father_id is None)
    father_only = sum(1 for child in minors if child.mother_id is None and child.father_id is not None)
    parented = dual + mother_only + father_only
    placed = sum(1 for child in minors if child.household_id is not None)
    households = len(household_members)
    households_with_minors = sum(1 for count in household_minor_counts.values() if count > 0)
    single_parent_households = sum(
        1
        for household_id, minor_count in household_minor_counts.items()
        if minor_count > 0 and household_adult_counts[household_id] == 1
    )
    couple_households = sum(1 for count in household_adult_counts.values() if count == 2)

    return RelationshipStats(
        population=len(people),
        adults=len(adults),
        minors=len(minors),
        households=households,
        avg_household_size=float(np.mean(household_sizes)) if household_sizes else 0.0,
        median_household_size=float(median(household_sizes)) if household_sizes else 0.0,
        max_household_size=max(household_sizes) if household_sizes else 0,
        partnered_adult_share=_safe_share(sum(1 for adult in adults if adult.partner_id is not None), len(adults)),
        couple_household_share=_safe_share(couple_households, households),
        households_with_minors_share=_safe_share(households_with_minors, households),
        single_parent_household_share=_safe_share(single_parent_households, households),
        minor_placement_rate=_safe_share(placed, len(minors), empty_value=1.0),
        minor_parent_coverage_rate=_safe_share(parented, len(minors), empty_value=1.0),
        dual_parent_minor_share=_safe_share(dual, len(minors), empty_value=0.0),
        mother_only_minor_share=_safe_share(mother_only, len(minors), empty_value=0.0),
        father_only_minor_share=_safe_share(father_only, len(minors), empty_value=0.0),
        guardian_only_minor_share=_safe_share(guardian_only, len(minors), empty_value=0.0),
        guardian_only_minors=guardian_only,
        mother_age_gap_mean=_mean(mother_gaps),
        mother_age_gap_p10=_percentile(mother_gaps, 10),
        mother_age_gap_p50=_percentile(mother_gaps, 50),
        mother_age_gap_p90=_percentile(mother_gaps, 90),
        father_age_gap_mean=_mean(father_gaps),
        father_age_gap_p10=_percentile(father_gaps, 10),
        father_age_gap_p50=_percentile(father_gaps, 50),
        father_age_gap_p90=_percentile(father_gaps, 90),
        spouse_age_gap_mean=_mean(spouse_gaps),
        spouse_age_gap_p50=_percentile(spouse_gaps, 50),
        spouse_age_gap_p90=_percentile(spouse_gaps, 90),
    )


def _safe_share(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    if denominator <= 0:
        return empty_value
    return float(numerator / denominator)


def _mean(values: list[int]) -> float:
    return float(np.mean(values)) if values else 0.0


def _percentile(values: list[int], q: int) -> float:
    return float(np.percentile(values, q)) if values else 0.0
