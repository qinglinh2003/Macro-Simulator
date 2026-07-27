#include <cassert>
#include <cstdint>
#include <type_traits>
#include <vector>

#include "macro_sim/core/housing.hpp"

namespace {

using macro_sim::DwellingId;
using macro_sim::HouseholdId;
using macro_sim::LoanId;
using macro_sim::Tick;
using macro_sim::core::DwellingMintSpec;
using macro_sim::core::OwnerId;
using macro_sim::core::PropertyRegistry;
using macro_sim::core::TitleEventKind;

[[nodiscard]] DwellingMintSpec home(std::uint64_t owner, std::uint64_t occupant,
                                    std::uint64_t tick = 0) {
    return {
        OwnerId::household(HouseholdId(owner)),
        HouseholdId(occupant),
        Tick(tick),
        80.0,
        0.9,
        7,
        365,
    };
}

void test_mint_transfer_and_indexes() {
    PropertyRegistry registry;
    const auto first = registry.mint(home(1, 1));
    const auto second = registry.mint(home(1, 2));
    assert(first.ok());
    assert(second.ok());
    assert(registry.minted_count() == 2);
    assert(registry.active_count() == 2);
    assert(registry.destroyed_count() == 0);
    assert(registry.occupied_count() == 2);
    assert(registry.owner_occupied_count() == 1);
    assert(registry.dwellings_for_owner(OwnerId::household(HouseholdId(1))).size() ==
           2);
    assert(registry.dwelling_for_occupant(HouseholdId(2)) == *second.get_if());

    assert(registry
               .transfer_title(*first.get_if(), OwnerId::household(HouseholdId(1)),
                               OwnerId::bank(macro_sim::BankId(1)), Tick(3))
               .ok());
    assert(registry.get(*first.get_if())->owner == OwnerId::bank(macro_sim::BankId(1)));
    assert(registry.dwellings_for_owner(OwnerId::household(HouseholdId(1))).size() ==
           1);
    assert(registry.dwellings_for_owner(OwnerId::bank(macro_sim::BankId(1))).size() ==
           1);
    assert(registry.title_events().size() == 3);
    assert(registry.title_events().back().kind == TitleEventKind::transfer);
    assert(registry.owner_occupied_count() == 0);
    assert(registry.validate_fast().ok());
    assert(registry.validate().ok());
}

void test_occupancy_and_collateral() {
    PropertyRegistry registry;
    const auto first = registry.mint(home(1, 1));
    const auto second = registry.mint(home(2, 2));
    assert(first.ok());
    assert(second.ok());

    assert(
        !registry.set_occupant(*first.get_if(), HouseholdId(1), HouseholdId(2)).ok());
    assert(registry.set_occupant(*first.get_if(), HouseholdId(1), HouseholdId{}).ok());
    assert(registry.occupied_count() == 1);
    assert(registry.set_occupant(*first.get_if(), HouseholdId{}, HouseholdId(3)).ok());
    assert(registry.occupied_count() == 2);
    assert(registry.dwelling_for_occupant(HouseholdId(3)) == *first.get_if());

    assert(registry.attach_collateral(*first.get_if(), LoanId(11)).ok());
    assert(registry.dwelling_for_collateral(LoanId(11)) == *first.get_if());
    assert(!registry.attach_collateral(*second.get_if(), LoanId(11)).ok());
    assert(!registry.attach_collateral(*first.get_if(), LoanId(12)).ok());
    assert(registry.clear_collateral(*first.get_if(), LoanId(11)).ok());
    assert(!registry.dwelling_for_collateral(LoanId(11)).valid());
    assert(registry.validate().ok());
}

void test_mint_only_stock_and_stale_titles() {
    PropertyRegistry registry;
    const auto dwelling = registry.mint(home(1, 1));
    assert(dwelling.ok());
    const auto stock = registry.minted_count();

    assert(!registry
                .transfer_title(*dwelling.get_if(), OwnerId::household(HouseholdId(2)),
                                OwnerId::household(HouseholdId(3)), Tick(1))
                .ok());
    assert(registry.minted_count() == stock);
    assert(
        !registry
             .destroy(*dwelling.get_if(), OwnerId::household(HouseholdId(1)), Tick(1))
             .ok());
    assert(
        registry.set_occupant(*dwelling.get_if(), HouseholdId(1), HouseholdId{}).ok());
    assert(registry
               .destroy(*dwelling.get_if(), OwnerId::household(HouseholdId(1)), Tick(2))
               .ok());
    assert(registry.minted_count() == stock);
    assert(registry.active_count() == 0);
    assert(registry.destroyed_count() == 1);
    assert(registry.occupied_count() == 0);
    assert(registry.title_events().back().kind == TitleEventKind::destroy);
    assert(registry.validate().ok());
}

void test_restore_rejects_corrupt_lineage() {
    PropertyRegistry source;
    const auto dwelling = source.mint(home(1, 1));
    assert(dwelling.ok());
    assert(source
               .transfer_title(*dwelling.get_if(), OwnerId::household(HouseholdId(1)),
                               OwnerId::household(HouseholdId(2)), Tick(4))
               .ok());

    PropertyRegistry restored;
    assert(restored.replace_state(source.records(), source.title_events()).ok());
    assert(restored.validate().ok());

    auto corrupt_events = source.title_events();
    corrupt_events.back().previous_owner = OwnerId::household(HouseholdId(9));
    assert(!restored.replace_state(source.records(), std::move(corrupt_events)).ok());
    assert(restored.validate().ok());
}

void test_randomized_title_journal() {
    PropertyRegistry registry;
    std::vector<OwnerId> owners;
    for (std::uint64_t id = 1; id <= 32; ++id) {
        owners.push_back(OwnerId::household(HouseholdId(id)));
        const auto created = registry.mint(home(id, id));
        assert(created.ok());
    }
    std::uint64_t random = 0x4d3850524f504552ULL;
    const auto next = [&random]() {
        random ^= random << 13U;
        random ^= random >> 7U;
        random ^= random << 17U;
        return random;
    };
    for (std::uint64_t step = 1; step <= 4'000; ++step) {
        const auto dwelling = DwellingId((next() % registry.minted_count()) + 1);
        auto *record = registry.get(dwelling);
        assert(record != nullptr);
        const auto expected = record->owner;
        auto next_owner = owners[next() % owners.size()];
        if (next_owner == expected) {
            next_owner = owners[(next_owner.value() + 1) % owners.size()];
        }
        assert(
            registry.transfer_title(dwelling, expected, next_owner, Tick(step)).ok());
        if (step % 37 == 0) {
            assert(registry.validate().ok());
        }
    }
    assert(registry.minted_count() == 32);
    assert(registry.active_count() == 32);
    assert(registry.validate().ok());
}

} // namespace

int main() {
    static_assert(!std::is_convertible_v<DwellingId, macro_sim::TenancyId>);
    test_mint_transfer_and_indexes();
    test_occupancy_and_collateral();
    test_mint_only_stock_and_stale_titles();
    test_restore_rejects_corrupt_lineage();
    test_randomized_title_journal();
    return 0;
}
