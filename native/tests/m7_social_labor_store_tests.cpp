#include <cassert>
#include <cmath>
#include <cstdint>
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
    assert(!employment.primary_job(PersonId(1)).valid());
    assert(employment.secondary_job(PersonId(1)).valid());
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
    accounts.unemployed = 2.0;
    accounts.suspended = 1.0;
    accounts.job_guarantee = 1.0;
    accounts.labor_supply = 9.0;
    assert(
        macro_sim::core::validate_labor_accounts(accounts, 1.0e-9).ok()
    );
    accounts.unemployed = 3.0;
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

} // namespace

int main() {
    test_primary_second_and_roster_indexes();
    test_swap_erase_suspension_and_stable_ids();
    test_labor_partition_gate();
    test_relationship_symmetry_and_lineage();
    test_exact_marriage_order();
    return 0;
}
