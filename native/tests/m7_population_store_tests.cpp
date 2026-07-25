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
    assert(ownership.maximum_projection_error() < 1.0e-12);
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(ownership.transfer(*first.get_if(), PersonId(3), 0.2).ok());
    assert(std::abs(ownership.get(*first.get_if())->share - 0.4) < 1.0e-12);
    assert(ownership.lots_for_person(PersonId(3)).size() == 1);
    assert(ownership.maximum_projection_error() < 1.0e-12);
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(ownership.transfer(*second.get_if(), PersonId(3), 0.4).ok());
    assert(ownership.get(*second.get_if())->owner == PersonId(3));
    const auto destination_lots = ownership.lots_for_person(PersonId(3));
    assert(destination_lots.size() == 2);
    assert(destination_lots[0] == BeneficialLotId(3));
    assert(destination_lots[1] == *second.get_if());
    assert(ownership.maximum_projection_error() < 1.0e-12);
    assert(ownership.validate(persons, 1.0e-12).ok());
}

void test_beneficial_index_copy_isolation() {
    PersonStore persons;
    assert(persons.create(person(-9'000, PersonSex::female)).ok());
    assert(persons.create(person(-9'001, PersonSex::male)).ok());

    const BeneficialAssetKey cash{
        BeneficialAssetKind::household_cash,
        HouseholdId(1),
        1,
    };
    BeneficialOwnershipBook original;
    const auto lot = original.create_lot(cash, PersonId(1), 1.0);
    assert(lot.ok());

    auto copy = original;
    assert(copy.transfer(*lot.get_if(), PersonId(2), 1.0).ok());
    assert(original.get(*lot.get_if())->owner == PersonId(1));
    assert(copy.get(*lot.get_if())->owner == PersonId(2));
    assert(original.lots_for_person(PersonId(1)).size() == 1);
    assert(original.lots_for_person(PersonId(2)).empty());
    assert(copy.lots_for_person(PersonId(1)).empty());
    assert(copy.lots_for_person(PersonId(2)).size() == 1);
    assert(original.validate(persons, 1.0e-12).ok());
    assert(copy.validate(persons, 1.0e-12).ok());
}

void test_beneficial_rekey_retains_retired_history() {
    PersonStore persons;
    assert(persons.create(person(-9'000, PersonSex::female)).ok());
    assert(persons.create(person(-9'001, PersonSex::male)).ok());

    const BeneficialAssetKey asset{
        BeneficialAssetKind::generic_position,
        HouseholdId(1),
        7,
    };
    BeneficialOwnershipBook ownership;
    const auto first = ownership.create_lot(asset, PersonId(1), 0.5);
    const auto second = ownership.create_lot(asset, PersonId(2), 0.5);
    assert(first.ok());
    assert(second.ok());
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(ownership.retire(*first.get_if()).ok());
    assert(ownership.create_lot(asset, PersonId(1), 0.5).ok());
    assert(ownership.validate_fast(persons, 1.0e-12).ok());

    assert(ownership.rekey_household(HouseholdId(1), HouseholdId(2)).ok());
    const auto destination = BeneficialAssetKey{
        BeneficialAssetKind::generic_position,
        HouseholdId(2),
        7,
    };
    assert(!ownership.contains_asset(asset));
    assert(ownership.contains_asset(destination));
    assert(ownership.lots_for_asset(asset).size() == 1);
    assert(ownership.lots_for_asset(destination).size() == 2);
    assert(ownership.validate(persons, 1.0e-12).ok());
}

void test_canonical_cash_lookup_preserves_full_asset_identity() {
    PersonStore persons;
    assert(persons.create(person(-9'000, PersonSex::female)).ok());

    const BeneficialAssetKey canonical{
        BeneficialAssetKind::household_cash,
        HouseholdId(1),
        1,
    };
    const BeneficialAssetKey alternate{
        BeneficialAssetKind::household_cash,
        HouseholdId(1),
        77,
    };
    BeneficialOwnershipBook ownership;
    const auto canonical_lot =
        ownership.create_lot(canonical, PersonId(1), 1.0);
    const auto alternate_lot =
        ownership.create_lot(alternate, PersonId(1), 1.0);
    assert(canonical_lot.ok());
    assert(alternate_lot.ok());
    assert(ownership.contains_asset(canonical));
    assert(ownership.contains_asset(alternate));
    assert(ownership.lots_for_asset(canonical).size() == 1);
    assert(ownership.lots_for_asset(alternate).size() == 1);
    assert(ownership.retire(*canonical_lot.get_if()).ok());
    assert(!ownership.contains_asset(canonical));
    assert(ownership.contains_asset(alternate));
    assert(ownership.retire_asset(alternate).ok());
    assert(ownership.lots_for_asset(alternate).empty());
    assert(ownership.validate(persons, 1.0e-12).ok());
}

void test_asset_presence_refresh_retires_only_unseen_kind() {
    PersonStore persons;
    assert(persons.create(person(-9'000, PersonSex::female)).ok());

    const BeneficialAssetKey first_security{
        BeneficialAssetKind::security_position,
        HouseholdId(1),
        2,
    };
    const BeneficialAssetKey second_security{
        BeneficialAssetKind::security_position,
        HouseholdId(1),
        4,
    };
    const BeneficialAssetKey generic{
        BeneficialAssetKind::generic_position,
        HouseholdId(1),
        9,
    };
    BeneficialOwnershipBook ownership;
    assert(ownership.create_lot(first_security, PersonId(1), 1.0).ok());
    assert(ownership.create_lot(second_security, PersonId(1), 1.0).ok());
    assert(ownership.create_lot(generic, PersonId(1), 1.0).ok());
    const auto untouched = ownership;

    assert(ownership
               .begin_asset_presence_refresh(
                   BeneficialAssetKind::security_position)
               .ok());
    assert(!ownership
                .begin_asset_presence_refresh(
                    BeneficialAssetKind::security_position)
                .ok());
    assert(ownership.touch_asset_presence(first_security));
    assert(!ownership.touch_asset_presence(generic));
    assert(ownership.finish_asset_presence_refresh().ok());
    assert(ownership.contains_asset(first_security));
    assert(!ownership.contains_asset(second_security));
    assert(ownership.contains_asset(generic));
    assert(ownership.lots_for_asset(second_security).empty());
    assert(ownership.validate(persons, 1.0e-12).ok());
    assert(untouched.contains_asset(first_security));
    assert(untouched.contains_asset(second_security));
    assert(untouched.contains_asset(generic));
    assert(untouched.validate(persons, 1.0e-12).ok());
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
    test_beneficial_index_copy_isolation();
    test_beneficial_rekey_retains_retired_history();
    test_canonical_cash_lookup_preserves_full_asset_identity();
    test_asset_presence_refresh_retires_only_unseen_kind();
    test_rejections();
    return 0;
}
