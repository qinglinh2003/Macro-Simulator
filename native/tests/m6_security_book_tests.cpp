#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <type_traits>
#include <vector>

#include "macro_sim/core/securities.hpp"

namespace {

using macro_sim::AccountId;
using macro_sim::BankId;
using macro_sim::BondId;
using macro_sim::CurrencyId;
using macro_sim::EconomyId;
using macro_sim::EquityId;
using macro_sim::HouseholdId;
using macro_sim::Money;
using macro_sim::Price;
using macro_sim::Rate;
using macro_sim::SecurityLotId;
using macro_sim::Tick;
using macro_sim::core::BondContract;
using macro_sim::core::EquityContract;
using macro_sim::core::EquityIssuerKind;
using macro_sim::core::InitialSecurityHolding;
using macro_sim::core::OwnerId;
using macro_sim::core::SecurityBook;
using macro_sim::core::SecurityId;

[[nodiscard]] BondContract bond_contract(std::uint64_t issuer, std::uint64_t account,
                                         std::uint64_t issue, std::uint64_t maturity,
                                         double face) {
    return {
        {},
        OwnerId::institutional(macro_sim::core::OwnerKind::treasury, issuer),
        AccountId(account),
        CurrencyId(1),
        Tick(issue),
        Tick(maturity),
        Rate(0.01),
        Money(face),
        {},
        true,
        false,
    };
}

[[nodiscard]] EquityContract equity_contract(std::uint64_t firm, std::uint64_t account,
                                             double shares) {
    return {
        {},
        EquityIssuerKind::firm,
        OwnerId::firm(macro_sim::FirmId(firm)),
        AccountId(account),
        CurrencyId(1),
        shares,
        Price(2.0),
        Price(2.0),
        Price(2.0),
        Price(2.1),
        0.0,
        0.0,
        true,
        false,
    };
}

void test_contracts_and_indexes() {
    SecurityBook book;
    const auto bond = book.issue_bond(bond_contract(1, 1, 0, 8, 100.0),
                                      OwnerId::household(HouseholdId(1)), Money(98.0));
    assert(bond.ok());
    assert(book.total_bond_face().value() == 100.0);
    assert(book.bonds_maturing_at(Tick(8)).size() == 1);
    assert(book.units_held(SecurityId::bond(*bond.get_if()),
                           OwnerId::household(HouseholdId(1))) == 100.0);
    assert(book.begin_batch().ok());
    assert(book.issue_bond_units(*bond.get_if(), OwnerId::household(HouseholdId(2)),
                                 20.0, Money(20.0))
               .ok());
    assert(book.finish_batch().ok());
    assert(book.get(*bond.get_if())->original_face.value() == 120.0);
    assert(book.get(*bond.get_if())->outstanding_face.value() == 120.0);

    const std::vector holdings{
        InitialSecurityHolding{
            OwnerId::household(HouseholdId(1)),
            60.0,
            Money(120.0),
        },
        InitialSecurityHolding{
            OwnerId::household(HouseholdId(2)),
            40.0,
            Money(80.0),
        },
    };
    const auto equity = book.create_equity(equity_contract(1, 2, 100.0), holdings);
    assert(equity.ok());
    assert(book.validate(1.0e-9).ok());
    assert(book.securities_for_issuer(OwnerId::firm(macro_sim::FirmId(1))).size() == 1);
    book.clear_household_position_changes();
    assert(book.household_position_changes().empty());

    auto status = book.transfer_units(
        SecurityId::equity(*equity.get_if()), OwnerId::household(HouseholdId(1)),
        OwnerId::household(HouseholdId(3)), 15.0, Money(31.5));
    assert(status.ok());
    const auto changes = book.household_position_changes();
    assert(changes.size() == 2U);
    assert(std::find(changes.begin(), changes.end(),
                     macro_sim::core::HouseholdSecurityPositionChange{
                         SecurityId::equity(*equity.get_if()),
                         OwnerId::household(HouseholdId(1))}) != changes.end());
    assert(std::find(changes.begin(), changes.end(),
                     macro_sim::core::HouseholdSecurityPositionChange{
                         SecurityId::equity(*equity.get_if()),
                         OwnerId::household(HouseholdId(3))}) != changes.end());
    assert(book.units_held(SecurityId::equity(*equity.get_if()),
                           OwnerId::household(HouseholdId(1))) == 45.0);
    assert(book.units_held(SecurityId::equity(*equity.get_if()),
                           OwnerId::household(HouseholdId(3))) == 15.0);

    status = book.issue_equity_units(
        *equity.get_if(), OwnerId::household(HouseholdId(3)), 10.0, Money(22.0));
    assert(status.ok());
    assert(book.get(*equity.get_if())->outstanding_shares == 110.0);

    status = book.retire_units(SecurityId::equity(*equity.get_if()),
                               OwnerId::household(HouseholdId(2)), 5.0);
    assert(status.ok());
    assert(book.get(*equity.get_if())->outstanding_shares == 105.0);
    assert(book.consolidate().ok());
    assert(book.validate(1.0e-9).ok());

    assert(book.settle_bond(*bond.get_if()).ok());
    assert(book.total_bond_face().value() == 0.0);
    assert(book.bonds_maturing_at(Tick(8)).empty());
    assert(book.resolve_equity(*equity.get_if()).ok());
    assert(book.validate(1.0e-9).ok());
}

void test_bank_index() {
    SecurityBook book;
    const auto bond = book.issue_bond(bond_contract(1, 1, 0, 2, 25.0),
                                      OwnerId::bank(BankId(3)), Money(25.0));
    assert(bond.ok());
    assert(book.bank_lots(BankId(3)).size() == 1);
    assert(book.bank_lots(BankId(2)).empty());
    assert(book.validate_indexes().ok());
}

void test_transfer_roundoff_clamp_preserves_units() {
    SecurityBook book;
    const auto source = OwnerId::household(HouseholdId(1));
    const auto destination = OwnerId::household(HouseholdId(2));
    const auto bond =
        book.issue_bond(bond_contract(1, 1, 0, 2, 1.0), source, Money(1.0));
    assert(bond.ok());
    const auto security = SecurityId::bond(*bond.get_if());

    assert(book.begin_batch().ok());
    assert(book.transfer_units(security, source, destination, 1.0 + 5.0e-10,
                               Money(1.0 + 5.0e-10))
               .ok());
    assert(book.finish_batch().ok());

    assert(book.units_held(security, source) == 0.0);
    assert(std::abs(book.units_held(security, destination) - 1.0) < 1.0e-15);
    assert(std::abs(book.total_units(security) - 1.0) < 1.0e-15);
    assert(book.validate(1.0e-9).ok());
}

void test_duplicate_pair_lots_in_batch() {
    SecurityBook book;
    const auto holder = OwnerId::household(HouseholdId(1));
    const std::vector holdings{
        InitialSecurityHolding{holder, 40.0, Money(80.0)},
        InitialSecurityHolding{holder, 10.0, Money(20.0)},
        InitialSecurityHolding{
            OwnerId::household(HouseholdId(2)),
            50.0,
            Money(100.0),
        },
    };

    assert(book.begin_batch().ok());
    const auto equity = book.create_equity(equity_contract(1, 2, 100.0), holdings);
    assert(equity.ok());
    const auto security = SecurityId::equity(*equity.get_if());
    assert(book.units_held(security, holder) == 50.0);
    assert(book.issue_equity_units(*equity.get_if(), holder, 5.0, Money(10.0)).ok());
    assert(book.units_held(security, holder) == 55.0);
    assert(book.finish_batch().ok());

    assert(book.units_held(security, holder) == 55.0);
    assert(book.total_units(security) == 105.0);
    assert(book.validate(1.0e-9).ok());
}

void test_fuzzed_mutations() {
    SecurityBook book;
    std::vector<EquityId> equities;
    std::vector<BondId> bonds;
    for (std::uint64_t index = 1; index <= 8; ++index) {
        std::vector<InitialSecurityHolding> holdings;
        for (std::uint64_t holder = 1; holder <= 4; ++holder) {
            holdings.push_back({
                OwnerId::household(HouseholdId(holder)),
                25.0,
                Money(25.0),
            });
        }
        const auto created =
            book.create_equity(equity_contract(index, 100 + index, 100.0), holdings);
        assert(created.ok());
        equities.push_back(*created.get_if());
    }
    for (std::uint64_t index = 1; index <= 16; ++index) {
        const auto created = book.issue_bond(
            bond_contract(1, 1, index, index + 30, 10.0 + static_cast<double>(index)),
            OwnerId::household(HouseholdId((index % 8) + 1)),
            Money(10.0 + static_cast<double>(index)));
        assert(created.ok());
        bonds.push_back(*created.get_if());
    }

    std::uint64_t state = 0x4d36534543555249ULL;
    auto next = [&state]() {
        state ^= state << 13U;
        state ^= state >> 7U;
        state ^= state << 17U;
        return state;
    };
    for (std::size_t step = 0; step < 2'000; ++step) {
        const auto equity = equities[next() % equities.size()];
        const auto security = SecurityId::equity(equity);
        const auto source_id = (next() % 32) + 1;
        auto destination_id = (next() % 32) + 1;
        if (destination_id == source_id) {
            destination_id = (destination_id % 32) + 1;
        }
        const auto source = OwnerId::household(HouseholdId(source_id));
        const auto destination = OwnerId::household(HouseholdId(destination_id));
        const double held = book.units_held(security, source);
        if (held > 1.0e-8) {
            const double units = std::min(held, std::max(1.0e-8, held * 0.25));
            assert(book.transfer_units(security, source, destination, units,
                                       Money(units * 2.0))
                       .ok());
        } else {
            const double issued = 0.01 * static_cast<double>((next() % 10) + 1);
            assert(book.issue_equity_units(equity, destination, issued,
                                           Money(issued * 2.0))
                       .ok());
        }
        if (step % 31 == 0) {
            assert(book.consolidate().ok());
        }
        assert(book.validate(1.0e-8).ok());
        assert(book.validate_indexes().ok());
    }

    for (const auto bond : bonds) {
        assert(book.settle_bond(bond).ok());
    }
    for (const auto equity : equities) {
        assert(book.resolve_equity(equity).ok());
    }
    assert(book.validate(1.0e-8).ok());
}

void test_inactive_lot_compaction_preserves_positions() {
    SecurityBook book;
    const std::array holdings{
        InitialSecurityHolding{
            OwnerId::household(HouseholdId(1)), 60.0, Money(120.0)},
        InitialSecurityHolding{
            OwnerId::household(HouseholdId(2)), 40.0, Money(80.0)},
    };
    const auto equity =
        book.create_equity(equity_contract(1, 2, 100.0), holdings);
    assert(equity.ok());
    const auto security = SecurityId::equity(*equity.get_if());
    assert(book.transfer_units(
                   security, OwnerId::household(HouseholdId(2)),
                   OwnerId::household(HouseholdId(3)), 40.0, Money(80.0))
               .ok());
    assert(book.lots().size() == 3U);
    const auto changes_before = book.household_position_changes().size();
    assert(book.compact_inactive_lots().ok());
    assert(book.lots().size() == 2U);
    assert(book.lots()[0].id == SecurityLotId(1));
    assert(book.lots()[1].id == SecurityLotId(2));
    assert(book.units_held(security, OwnerId::household(HouseholdId(1))) ==
           60.0);
    assert(book.units_held(security, OwnerId::household(HouseholdId(2))) ==
           0.0);
    assert(book.units_held(security, OwnerId::household(HouseholdId(3))) ==
           40.0);
    assert(book.household_position_changes().size() == changes_before);
    assert(book.validate(1.0e-9).ok());
}

void test_rejections() {
    SecurityBook book;
    auto invalid = bond_contract(1, 1, 4, 3, 10.0);
    assert(!book.issue_bond(invalid, OwnerId::household(HouseholdId(1)), Money(10.0))
                .ok());

    const auto bond = book.issue_bond(bond_contract(1, 1, 0, 1, 10.0),
                                      OwnerId::household(HouseholdId(1)), Money(10.0));
    assert(bond.ok());
    assert(!book.transfer_units(SecurityId::bond(*bond.get_if()),
                                OwnerId::household(HouseholdId(1)),
                                OwnerId::household(HouseholdId(2)), 11.0, Money(11.0))
                .ok());
    assert(book.validate(1.0e-9).ok());
}

} // namespace

int main() {
    static_assert(!std::is_convertible_v<BondId, EquityId>);
    static_assert(!std::is_convertible_v<EquityId, BondId>);
    static_cast<void>(EconomyId(1));
    test_contracts_and_indexes();
    test_bank_index();
    test_transfer_roundoff_clamp_preserves_units();
    test_duplicate_pair_lots_in_batch();
    test_fuzzed_mutations();
    test_inactive_lot_compaction_preserves_positions();
    test_rejections();
    return 0;
}
