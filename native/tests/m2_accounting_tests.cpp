#include <cassert>
#include <cmath>
#include <cstdint>
#include <utility>

#include "macro_sim/core/root_state.hpp"

namespace {

using macro_sim::Capital;
using macro_sim::EconomyId;
using macro_sim::Money;
using macro_sim::core::FirmSector;
using macro_sim::core::GenesisSpec;
using macro_sim::core::GenesisVertical;
using macro_sim::core::RootState;

[[nodiscard]] RootState take_state(macro_sim::Result<RootState> result) {
    assert(result.ok());
    return std::move(result).take();
}

void test_v0_genesis_is_deterministic_and_balanced() {
    const GenesisSpec spec{
        GenesisVertical::m4_v0_cash_loop,
        EconomyId(7),
        macro_sim::CurrencyId(2),
        3,
        2,
        0,
        2,
        false,
        Money(100.0),
        Capital(0.0),
        91,
        {3, 7},
    };
    auto first = take_state(macro_sim::core::build_genesis(spec));
    auto second = take_state(macro_sim::core::build_genesis(spec));

    assert(first.households.alive_count() == 3);
    assert(first.firms.alive_count() == 2);
    assert(first.banks.alive_count() == 2);
    assert(first.postings.size() == 10);
    assert(first.reserves.size() == 2);
    assert(first.ownership.size() == 2);
    assert(first.institutions.treasury_account.valid() == false);
    assert(first.seed == 91);
    assert(first.named_counters.contains(3));
    assert(first.named_counters.contains(7));
    assert(first.postings.total_deposits() == Money(100.0));
    assert(first.reserves.total_reserves() == Money(100.0));
    assert(first.reserves.reserve_stock() == Money(100.0));
    assert(first.ownership.validate_shares(1.0e-12).ok());
    assert(first.postings.validate_finite().ok());
    assert(first.postings.validate_nonnegative(1.0e-8).ok());
    const auto household_account =
        first.households.get(macro_sim::HouseholdId(1))->primary_account;
    const auto* account = first.postings.get(household_account);
    assert(account != nullptr);
    const auto found = first.postings.find(account->key);
    const auto node = first.postings.settlement_node(household_account);
    assert(found.ok() && *found.get_if() == household_account);
    assert(node.ok() && *node.get_if() == account->key.settlement_node);

    assert(first.postings.records() == second.postings.records());
    assert(first.reserves.records() == second.reserves.records());
    assert(first.ownership.records() == second.ownership.records());
}

void test_v1_genesis_has_capital_and_treasury() {
    const GenesisSpec spec{
        GenesisVertical::m4_v1_capital_fiscal,
        EconomyId(1),
        macro_sim::CurrencyId(1),
        4,
        3,
        2,
        1,
        true,
        Money(12.0),
        Capital(9.0),
        3,
        {},
    };
    auto state = take_state(macro_sim::core::build_genesis(spec));

    assert(state.institutions.treasury_account.valid());
    std::uint64_t consumption = 0;
    std::uint64_t capital = 0;
    double physical_capital = 0.0;
    state.firms.for_each_alive(
        [&consumption, &capital, &physical_capital](
            macro_sim::FirmId,
            const macro_sim::core::FirmComponent& firm
        ) {
            if (firm.sector == FirmSector::consumption) {
                ++consumption;
            } else {
                ++capital;
            }
            physical_capital += firm.physical_capital.value();
        }
    );
    assert(consumption == 3);
    assert(capital == 2);
    assert(std::abs(physical_capital - 9.0) < 1.0e-12);
    assert(state.postings.total_deposits() == Money(12.0));
}

void test_invalid_vertical_capabilities_publish_no_state() {
    GenesisSpec spec;
    spec.vertical = GenesisVertical::m4_v0_cash_loop;
    spec.government = true;
    const auto result = macro_sim::core::build_genesis(spec);
    assert(!result.ok());
    assert(result.status().code() == macro_sim::ErrorCode::unsupported);
}

void test_ownership_owner_rekey_merges_assets() {
    macro_sim::core::OwnershipBook ownership;
    const macro_sim::core::AssetKey asset{
        macro_sim::core::AssetKind::firm_equity,
        EconomyId(1),
        7,
    };
    const auto source =
        macro_sim::core::OwnerId::household(
            macro_sim::HouseholdId(1)
        );
    const auto destination =
        macro_sim::core::OwnerId::household(
            macro_sim::HouseholdId(2)
        );
    assert(ownership.create_lot(asset, source, 0.4).ok());
    assert(
        ownership.create_lot(asset, destination, 0.6).ok()
    );
    assert(
        ownership.rekey_owner(source, destination).ok()
    );
    assert(ownership.validate_shares(1.0e-12).ok());
    std::size_t active = 0;
    for (const auto &lot : ownership.records()) {
        if (!lot.active) {
            continue;
        }
        ++active;
        assert(lot.owner == destination);
        assert(std::abs(lot.share - 1.0) < 1.0e-12);
    }
    assert(active == 1);
}

}  // namespace

int main() {
    test_v0_genesis_is_deterministic_and_balanced();
    test_v1_genesis_has_capital_and_treasury();
    test_invalid_vertical_capabilities_publish_no_state();
    test_ownership_owner_rekey_merges_assets();
    return 0;
}
