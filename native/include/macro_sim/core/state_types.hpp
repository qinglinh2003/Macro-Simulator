#ifndef MACRO_SIM_CORE_STATE_TYPES_HPP
#define MACRO_SIM_CORE_STATE_TYPES_HPP

#include <cstdint>

#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

enum class OwnerKind : std::uint8_t {
    household = 0,
    firm = 1,
    bank = 2,
    treasury = 3,
    central_bank = 4,
    dealer = 5,
    rounding_residual = 6,
    institution = 7,
};

struct OwnerId final {
    OwnerKind kind{OwnerKind::institution};
    std::uint64_t value{0};

    [[nodiscard]] static constexpr OwnerId household(HouseholdId id) noexcept {
        return {OwnerKind::household, id.value()};
    }

    [[nodiscard]] static constexpr OwnerId firm(FirmId id) noexcept {
        return {OwnerKind::firm, id.value()};
    }

    [[nodiscard]] static constexpr OwnerId bank(BankId id) noexcept {
        return {OwnerKind::bank, id.value()};
    }

    [[nodiscard]] static constexpr OwnerId institutional(
        OwnerKind kind,
        std::uint64_t value = 1
    ) noexcept {
        return {kind, value};
    }

    [[nodiscard]] constexpr bool valid() const noexcept {
        return value != 0;
    }

    constexpr auto operator<=>(const OwnerId&) const noexcept = default;
};

enum class AccountKind : std::uint8_t {
    deposit = 0,
    bank_cash = 1,
    treasury = 2,
    central_bank = 3,
    dealer = 4,
    rounding_residual = 5,
};

struct AccountKey final {
    AccountKind kind{AccountKind::deposit};
    EconomyId economy{};
    OwnerId owner{};
    CurrencyId currency{};
    SettlementNodeId settlement_node{};

    constexpr auto operator<=>(const AccountKey&) const noexcept = default;
};

enum class FirmSector : std::uint8_t {
    consumption = 0,
    capital = 1,
};

enum class AssetKind : std::uint8_t {
    firm_equity = 0,
    bank_equity = 1,
    generic_contract = 2,
};

struct AssetKey final {
    AssetKind kind{AssetKind::generic_contract};
    EconomyId economy{};
    std::uint64_t value{0};

    constexpr auto operator<=>(const AssetKey&) const noexcept = default;
};

struct HouseholdComponent final {
    AccountId primary_account{};
};

struct FirmComponent final {
    FirmSector sector{FirmSector::consumption};
    AccountId primary_account{};
    Goods goods_inventory{};
    Capital physical_capital{};
    double productivity{1.0};
};

struct BankComponent final {
    AccountId cash_account{};
    SettlementNodeId settlement_node{};
};

}  // namespace macro_sim::core

#endif
