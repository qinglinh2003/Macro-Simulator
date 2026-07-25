#include <cassert>
#include <cmath>
#include <cstdint>
#include <type_traits>
#include <vector>

#include "macro_sim/core/population.hpp"

namespace {

using macro_sim::BeneficialLotId;
using macro_sim::HouseholdId;
using macro_sim::Money;
using macro_sim::PersonId;
using macro_sim::core::BeneficialAssetKey;
using macro_sim::core::BeneficialAssetKind;
using macro_sim::core::BeneficialOwnershipBook;
using macro_sim::core::GenesisSpec;
using macro_sim::core::HouseholdMembershipBook;
using macro_sim::core::PersonRecord;
using macro_sim::core::PersonSex;
using macro_sim::core::PersonStore;

[[nodiscard]] PersonRecord person(std::int32_t birth_day, PersonSex sex) {
    PersonRecord value;
    value.birth_day = birth_day;
    value.sex = sex;
    return value;
}

void test_person_dense_view_and_archive() {
    PersonStore store;
    std::vector<PersonId> ids;
    for (std::int32_t index = 0; index < 8; ++index) {
        const auto created = store.create(person(
            -10'000 - index, index % 2 == 0 ? PersonSex::female : PersonSex::male));
        assert(created.ok());
        ids.push_back(*created.get_if());
    }
    assert(store.validate().ok());
    assert(store.alive_count() == 8);
    assert(store.mark_dead(ids[2], 30).ok());
    assert(store.mark_dead(ids[5], 31).ok());
    assert(store.alive_count() == 6);
    assert(store.archived_count() == 2);
    assert(store.contains(ids[2]));
    assert(!store.alive(ids[2]));
    assert(!store.mark_dead(ids[2], 32).ok());
    assert(store.validate().ok());
    const auto born = store.create(person(32, PersonSex::female));
    assert(born.ok());
    assert(born.get_if()->value() == 9);
    assert(store.validate().ok());
}

void test_membership_projection() {
    GenesisSpec spec;
    spec.households = 3;
    spec.consumption_firms = 1;
    spec.aggregate_opening_money = Money(100.0);
    const auto genesis = macro_sim::core::build_genesis(spec);
    assert(genesis.ok());

    PersonStore persons;
    HouseholdMembershipBook membership;
    for (std::uint64_t index = 0; index < 6; ++index) {
        auto record = person(-8'000 - static_cast<std::int32_t>(index),
                             index % 2 == 0 ? PersonSex::female : PersonSex::male);
        record.household = HouseholdId(1 + index / 2);
        const auto created = persons.create(record);
        assert(created.ok());
        assert(membership.add(*created.get_if(), record.household).ok());
    }
    assert(membership.validate(persons, *genesis.get_if()).ok());
    assert(membership.members(HouseholdId(2)).size() == 2);
    assert(membership.move(PersonId(2), HouseholdId(2)).ok());
    persons.get(PersonId(2))->household = HouseholdId(2);
    assert(membership.members(HouseholdId(1)).size() == 1);
    assert(membership.members(HouseholdId(2)).size() == 3);
    assert(membership.validate(persons, *genesis.get_if()).ok());
    assert(membership.remove(PersonId(3)).ok());
    assert(persons.mark_dead(PersonId(3), 44).ok());
    assert(membership.validate(persons, *genesis.get_if()).ok());
}

void test_beneficial_ownership_split_and_transfer() {
    PersonStore persons;
    for (std::int32_t index = 0; index < 3; ++index) {
        assert(persons.create(person(-9'000 - index, PersonSex::female)).ok());
    }
    BeneficialOwnershipBook ownership;
    const BeneficialAssetKey cash{
        BeneficialAssetKind::household_cash,
        HouseholdId(1),
        1,
    };
    const auto first = ownership.create_lot(cash, PersonId(1), 0.6);
    const auto second = ownership.create_lot(cash, PersonId(2), 0.4);
    assert(first.ok());
    assert(second.ok());
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(ownership.transfer(*first.get_if(), PersonId(3), 0.2).ok());
    assert(std::abs(ownership.get(*first.get_if())->share - 0.4) < 1.0e-12);
    assert(ownership.lots_for_person(PersonId(3)).size() == 1);
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(ownership.transfer(*second.get_if(), PersonId(3), 0.4).ok());
    assert(ownership.get(*second.get_if())->owner == PersonId(3));
    assert(ownership.validate(persons, 1.0e-12).ok());
}

void test_rejections() {
    PersonStore persons;
    PersonRecord invalid;
    invalid.efficiency = 0.0;
    assert(!persons.create(invalid).ok());
    auto valid = person(-10, PersonSex::male);
    const auto id = persons.create(valid);
    assert(id.ok());

    HouseholdMembershipBook membership;
    assert(membership.add(*id.get_if(), HouseholdId(1)).ok());
    assert(!membership.add(*id.get_if(), HouseholdId(2)).ok());

    BeneficialOwnershipBook ownership;
    const BeneficialAssetKey asset{
        BeneficialAssetKind::generic_position,
        HouseholdId(1),
        1,
    };
    assert(!ownership.create_lot(asset, PersonId(1), 0.0).ok());
    const auto lot = ownership.create_lot(asset, PersonId(1), 1.0);
    assert(lot.ok());
    assert(!ownership.transfer(*lot.get_if(), PersonId(2), 2.0).ok());
}

} // namespace

int main() {
    static_assert(!std::is_convertible_v<PersonId, HouseholdId>);
    static_assert(!std::is_convertible_v<BeneficialLotId, PersonId>);
    test_person_dense_view_and_archive();
    test_membership_projection();
    test_beneficial_ownership_split_and_transfer();
    test_rejections();
    return 0;
}
