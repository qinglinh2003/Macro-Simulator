#include <cassert>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

#include "macro_sim/core/social_labor.hpp"

namespace {

using macro_sim::FirmId;
using macro_sim::HouseholdId;
using macro_sim::JobId;
using macro_sim::Money;
using macro_sim::PersonId;
using macro_sim::core::EmploymentBook;
using macro_sim::core::GenesisSpec;
using macro_sim::core::LaborAccounts;
using macro_sim::core::MarriageRules;
using macro_sim::core::PersonRecord;
using macro_sim::core::PersonStore;
using macro_sim::core::RelationshipBook;
using macro_sim::core::SeparationKind;

struct Fixture final {
    macro_sim::core::RootState root;
    PersonStore persons;
};

[[nodiscard]] Fixture fixture() {
    GenesisSpec spec;
    spec.households = 3;
    spec.consumption_firms = 2;
    spec.aggregate_opening_money = Money(100.0);
    auto genesis = macro_sim::core::build_genesis(spec);
    assert(genesis.ok());
    Fixture value{std::move(*genesis.get_if()), {}};
    for (std::uint64_t index = 0; index < 6; ++index) {
        PersonRecord person;
        person.birth_day = -10'000;
        person.household = HouseholdId(1 + index / 2);
        assert(value.persons.create(person).ok());
    }
    return value;
}

void test_primary_second_and_roster_indexes() {
    auto value = fixture();
    EmploymentBook employment;
    const auto first =
        employment.hire(PersonId(1), FirmId(1), 10, 2.0, 0.6);
    const auto second =
        employment.hire(PersonId(1), FirmId(2), 11, 2.5, 0.4, true);
    assert(first.ok());
    assert(second.ok());
    assert(employment.primary_job(PersonId(1)) == *first.get_if());
    assert(employment.secondary_job(PersonId(1)) == *second.get_if());
    assert(std::abs(employment.active_hours(PersonId(1)) - 1.0) <
           1.0e-12);
    assert(employment.roster(FirmId(1)).size() == 1);
    assert(employment.roster(FirmId(2)).size() == 1);
    assert(employment.validate(value.persons, value.root, 1.0e-12).ok());
    assert(
        !employment
             .hire(PersonId(1), FirmId(1), 12, 2.0, 0.1, true)
             .ok()
    );
    assert(
        employment.separate(*first.get_if(), 20, SeparationKind::churn)
            .ok()
    );
    assert(employment.primary_job(PersonId(1)) == *second.get_if());
    assert(!employment.secondary_job(PersonId(1)).valid());
    assert(!employment.get(*second.get_if())->secondary);
    assert(employment.validate(value.persons, value.root, 1.0e-12).ok());
}

void test_swap_erase_suspension_and_stable_ids() {
    auto value = fixture();
    EmploymentBook employment;
    std::vector<JobId> jobs;
    for (std::uint64_t person = 1; person <= 6; ++person) {
        const auto hired = employment.hire(
            PersonId(person), FirmId(1), static_cast<std::int32_t>(person),
            1.0, 1.0
        );
        assert(hired.ok());
        jobs.push_back(*hired.get_if());
    }
    assert(employment.suspend(jobs[2], 20).ok());
    assert(employment.suspended_count() == 1);
    assert(employment.active_hours(PersonId(3)) == 0.0);
    assert(employment.recall(jobs[2]).ok());
    assert(employment.suspended_count() == 0);
    assert(
        employment
            .separate(jobs[1], 22, SeparationKind::demand_layoff)
            .ok()
    );
    assert(employment.roster(FirmId(1)).size() == 5);
    assert(employment.validate(value.persons, value.root, 1.0e-12).ok());
    const auto replacement =
        employment.hire(PersonId(2), FirmId(2), 23, 1.5, 1.0);
    assert(replacement.ok());
    assert(replacement.get_if()->value() == 7);
    assert(employment.validate(value.persons, value.root, 1.0e-12).ok());
}

void test_labor_partition_gate() {
    LaborAccounts accounts;
    accounts.employed_fte = 4.5;
    accounts.employed_heads = 5.0;
    accounts.unemployed = 2.5;
    accounts.suspended = 1.0;
    accounts.job_guarantee = 1.0;
    accounts.labor_supply = 9.0;
    assert(
        macro_sim::core::validate_labor_accounts(accounts, 1.0e-9).ok()
    );
    accounts.unemployed = 3.5;
    assert(
        !macro_sim::core::validate_labor_accounts(accounts, 1.0e-9).ok()
    );
}

void test_relationship_symmetry_and_lineage() {
    auto value = fixture();
    RelationshipBook relationships;
    auto *first = value.persons.get(PersonId(1));
    auto *second = value.persons.get(PersonId(2));
    first->sex = macro_sim::core::PersonSex::female;
    second->sex = macro_sim::core::PersonSex::male;
    assert(
        relationships
            .marry(
                value.persons, macro_sim::EventId(1),
                PersonId(1), PersonId(2), 10
            )
            .ok()
    );
    assert(first->partner == PersonId(2));
    assert(second->partner == PersonId(1));
    assert(relationships.validate(value.persons).ok());
    assert(
        relationships.divorce(value.persons, PersonId(1), 20).ok()
    );
    assert(!first->partner.valid());
    assert(!second->partner.valid());
    assert(relationships.validate(value.persons).ok());
    assert(
        relationships
            .marry(
                value.persons, macro_sim::EventId(2),
                PersonId(1), PersonId(2), 30
            )
            .ok()
    );
    assert(relationships.widow(value.persons, PersonId(2), 40).ok());
    assert(relationships.validate(value.persons).ok());

    auto *child = value.persons.get(PersonId(3));
    child->mother = PersonId(1);
    child->father = PersonId(2);
    assert(relationships.register_birth(value.persons, PersonId(3)).ok());
    assert(relationships.children(PersonId(1)).size() == 1);
    assert(relationships.children(PersonId(2)).size() == 1);
    assert(relationships.validate(value.persons).ok());
}

void test_exact_marriage_order() {
    auto value = fixture();
    macro_sim::core::HouseholdMembershipBook membership;
    for (std::uint64_t index = 1; index <= 6; ++index) {
        auto *person = value.persons.get(PersonId(index));
        person->sex =
            index <= 3 ? macro_sim::core::PersonSex::female
                       : macro_sim::core::PersonSex::male;
        person->birth_day =
            -static_cast<std::int32_t>(20 + index) * 365;
        person->household = HouseholdId(index <= 3 ? index : index - 3);
        assert(membership.add(PersonId(index), person->household).ok());
    }
    MarriageRules rules;
    rules.forbid_same_household = false;
    const auto first = macro_sim::core::exact_marriage_matches(
        value.persons, membership, rules, 0
    );
    const auto second = macro_sim::core::exact_marriage_matches(
        value.persons, membership, rules, 0
    );
    assert(first.ok());
    assert(second.ok());
    assert(*first.get_if() == *second.get_if());
    assert(first.get_if()->size() == 3);
    assert((*first.get_if())[0].first == PersonId(1));
}

void test_indexed_marriage_matches_brute_force() {
    auto value = fixture();
    value.persons = PersonStore{};
    macro_sim::core::HouseholdMembershipBook membership;
    constexpr std::uint64_t count = 160;
    for (std::uint64_t index = 0; index < count; ++index) {
        PersonRecord person;
        person.sex =
            index % 2U == 0U
                ? macro_sim::core::PersonSex::female
                : macro_sim::core::PersonSex::male;
        person.birth_day =
            -static_cast<std::int32_t>(
                (18U + (index * 19U) % 63U) * 365U +
                (index * 101U) % 365U
            );
        person.efficiency =
            0.5 + static_cast<double>((index * 43U) % 175U) /
                      100.0;
        person.household = HouseholdId(1U + index / 3U);
        const auto created = value.persons.create(person);
        assert(created.ok());
        assert(
            membership
                .add(*created.get_if(), person.household)
                .ok()
        );
    }
    MarriageRules rules;
    rules.maximum_age_gap = 17;
    rules.preferred_age_gap = 2.5;
    rules.age_gap_penalty = 0.7;
    rules.assortativity = 0.9;
    rules.forbid_same_household = true;
    rules.forbid_close_kin = true;

    std::vector<PersonId> first_pool;
    std::vector<PersonId> second_pool;
    for (const auto id : value.persons.alive_ids()) {
        const auto *person = value.persons.get(id);
        const double age =
            static_cast<double>(-person->birth_day) / 365.2425;
        if (age < static_cast<double>(rules.minimum_age) ||
            age > static_cast<double>(rules.maximum_age)) {
            continue;
        }
        (person->sex == macro_sim::core::PersonSex::female
             ? first_pool
             : second_pool)
            .push_back(id);
    }
    std::sort(first_pool.begin(), first_pool.end());
    std::sort(second_pool.begin(), second_pool.end());
    std::vector<std::uint8_t> matched(
        value.persons.next_id(), 0U
    );
    std::vector<macro_sim::core::MarriageMatch> expected;
    for (const auto first_id : first_pool) {
        const auto *first = value.persons.get(first_id);
        const double first_age =
            static_cast<double>(-first->birth_day) / 365.2425;
        macro_sim::core::MarriageMatch best;
        best.score = std::numeric_limits<double>::infinity();
        for (const auto second_id : second_pool) {
            if (matched[static_cast<std::size_t>(
                    second_id.value()
                )] != 0U) {
                continue;
            }
            const auto *second = value.persons.get(second_id);
            const double second_age =
                static_cast<double>(-second->birth_day) / 365.2425;
            const double gap = second_age - first_age;
            if (std::abs(gap) >
                    static_cast<double>(rules.maximum_age_gap) ||
                membership.household_of(first_id) ==
                    membership.household_of(second_id)) {
                continue;
            }
            const double score =
                rules.age_gap_penalty *
                    std::abs(gap - rules.preferred_age_gap) +
                rules.assortativity *
                    std::abs(
                        std::log(first->efficiency) -
                        std::log(second->efficiency)
                    );
            if (score < best.score ||
                (score == best.score &&
                 second_id < best.second)) {
                best = {first_id, second_id, score};
            }
        }
        if (best.second.valid()) {
            matched[static_cast<std::size_t>(
                best.second.value()
            )] = 1U;
            expected.push_back(best);
        }
    }
    const auto actual =
        macro_sim::core::exact_marriage_matches(
            value.persons, membership, rules, 0
    );
    assert(actual.ok());
    assert(actual.get_if()->size() == expected.size());
    for (std::size_t index = 0; index < expected.size(); ++index) {
        assert((*actual.get_if())[index].first ==
               expected[index].first);
        assert((*actual.get_if())[index].second ==
               expected[index].second);
        assert(
            std::abs(
                (*actual.get_if())[index].score -
                expected[index].score
            ) < 1.0e-12
        );
    }
}

} // namespace

int main() {
    test_primary_second_and_roster_indexes();
    test_swap_erase_suspension_and_stable_ids();
    test_labor_partition_gate();
    test_relationship_symmetry_and_lineage();
    test_exact_marriage_order();
    test_indexed_marriage_matches_brute_force();
    return 0;
}
