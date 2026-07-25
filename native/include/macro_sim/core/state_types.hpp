#ifndef MACRO_SIM_CORE_STATE_TYPES_HPP
#define MACRO_SIM_CORE_STATE_TYPES_HPP

#include <cstdint>
#include <type_traits>
#include <utility>

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
    std::uint32_t value{0};

    [[nodiscard]] static constexpr OwnerId household(HouseholdId id) noexcept {
        return {OwnerKind::household, id.value()};
    }

    [[nodiscard]] static constexpr OwnerId firm(FirmId id) noexcept {
        return {OwnerKind::firm, id.value()};
    }

    [[nodiscard]] static constexpr OwnerId bank(BankId id) noexcept {
        return {OwnerKind::bank, id.value()};
    }

    template <typename Source = std::uint32_t>
        requires std::is_integral_v<Source>
    [[nodiscard]] static constexpr OwnerId institutional(
        OwnerKind kind,
        Source value = Source{1}
    ) noexcept {
        return {
            kind,
            std::in_range<std::uint32_t>(value)
                ? static_cast<std::uint32_t>(value)
                : std::uint32_t{0},
        };
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
    clearing = 6,
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
    energy = 2,
    construction = 3,
};

enum class FirmTechnology : std::uint8_t {
    linear = 0,
    cobb_douglas = 1,
};

enum class AssetKind : std::uint8_t {
    firm_equity = 0,
    bank_equity = 1,
    generic_contract = 2,
};

struct AssetKey final {
    AssetKind kind{AssetKind::generic_contract};
    EconomyId economy{};
    std::uint32_t value{0};

    constexpr auto operator<=>(const AssetKey&) const noexcept = default;
};

struct HouseholdComponent final {
    AccountId primary_account{};
    double income_propensity{0.8};
    double wealth_propensity{0.05};
    double income_adjustment{0.3};
    double income_expected{0.0};
    double income_realized{0.0};
    double consumption_budget{0.0};
    double spent{0.0};
    double labor_sold{0.0};
};

struct FirmComponent final {
    FirmSector sector{FirmSector::consumption};
    AccountId primary_account{};
    Goods goods_inventory{};
    Capital physical_capital{};
    double productivity{1.0};
    FirmTechnology technology{FirmTechnology::linear};
    double total_factor_productivity{1.0};
    double capital_share{0.3};
    double capital_output_ratio{0.0};
    double investment_adjustment{0.0};
    double capital_depreciation{0.0};
    double demand_adjustment{0.3};
    double inventory_ratio{0.75};
    double markup_adjustment{0.05};
    double markup_minimum{0.0};
    double markup_maximum{1.0};
    double shortage_adjustment{0.02};
    double dividend_payout{0.5};
    Price posted_price{Price(1.2)};
    Money posted_wage{Money(1.0)};
    double markup{0.2};
    double demand_expected{10.0};
    double target_inventory_previous{0.0};
    double labor_demand_previous{0.0};
    double hired_previous{0.0};
    double sales_previous{0.0};
    double rationed_previous{0.0};
};

struct BankComponent final {
    AccountId cash_account{};
    SettlementNodeId settlement_node{};
    double leverage_appetite{10.0};
    double loan_spread{0.0};
    double deposit_spread{0.0};
    bool alive{true};
};

}  // namespace macro_sim::core

#endif
