#include "macro_sim/core/root_state.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>
#include <utility>

namespace macro_sim::core {
namespace {

[[nodiscard]] Status validate_spec(const GenesisSpec& spec) noexcept {
    if (!spec.economy.valid() || !spec.currency.valid()) {
        return Status(ErrorCode::invalid_argument, "invalid genesis IDs");
    }
    if (spec.households == 0 || spec.settlement_banks == 0) {
        return Status(
            ErrorCode::invalid_argument,
            "genesis requires households and settlement banks"
        );
    }
    if (!std::isfinite(spec.aggregate_opening_money.value())
        || spec.aggregate_opening_money.value() < 0.0
        || !std::isfinite(spec.aggregate_opening_capital.value())
        || spec.aggregate_opening_capital.value() < 0.0
        || !std::isfinite(spec.household_opening_money.value())
        || spec.household_opening_money.value() < 0.0
        || !std::isfinite(spec.firm_opening_money.value())
        || spec.firm_opening_money.value() < 0.0
        || (spec.capital_firm_opening_money.has_value()
            && (!std::isfinite(spec.capital_firm_opening_money->value())
                || spec.capital_firm_opening_money->value() < 0.0))
        || !std::isfinite(spec.bank_opening_money.value())
        || spec.bank_opening_money.value() < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "genesis stocks must be finite and nonnegative"
        );
    }
    const auto firm_count =
        spec.consumption_firms + spec.capital_firms;
    if (firm_count < spec.consumption_firms) {
        return Status(ErrorCode::out_of_range, "firm count overflows");
    }
    if (spec.use_per_agent_endowments) {
        const double capital_firm_opening =
            spec.capital_firm_opening_money.value_or(spec.firm_opening_money).value();
        const double expected =
            static_cast<double>(spec.households)
                * spec.household_opening_money.value()
            + static_cast<double>(spec.consumption_firms)
                * spec.firm_opening_money.value()
            + static_cast<double>(spec.capital_firms)
                * capital_firm_opening
            + static_cast<double>(spec.settlement_banks)
                * spec.bank_opening_money.value();
        const double scale = std::max(
            1.0,
            std::max(
                std::abs(expected),
                std::abs(spec.aggregate_opening_money.value())
            )
        );
        if (!std::isfinite(expected)
            || std::abs(expected - spec.aggregate_opening_money.value())
                > 1.0e-12 * scale) {
            return Status(
                ErrorCode::invalid_argument,
                "per-agent endowments do not match aggregate opening money"
            );
        }
    }
    const bool is_v1 =
        spec.vertical == GenesisVertical::m4_v1_capital_fiscal;
    if (is_v1 != spec.government) {
        return Status(
            ErrorCode::unsupported,
            "government capability must match the selected vertical"
        );
    }
    if (!is_v1
        && (spec.capital_firms != 0
            || spec.aggregate_opening_capital.value() != 0.0)) {
        return Status(
            ErrorCode::unsupported,
            "M4 V0 does not contain capital firms or physical capital"
        );
    }
    const auto capital_recipients =
        spec.opening_capital_to_consumption_firms
        ? spec.consumption_firms
        : spec.capital_firms;
    if (spec.aggregate_opening_capital.value() > 0.0
        && capital_recipients == 0) {
        return Status(
            ErrorCode::invalid_argument,
            "opening capital requires a recipient firm"
        );
    }
    std::set<std::uint64_t> counter_streams;
    for (const auto stream : spec.named_counter_streams) {
        if (stream == 0 || !counter_streams.insert(stream).second) {
            return Status(
                ErrorCode::invalid_argument,
                "counter stream declarations must be unique and nonzero"
            );
        }
    }
    return Status::success();
}

[[nodiscard]] Result<AccountId> create_institution_account(
    RootState& state,
    AccountKind kind,
    OwnerKind owner_kind,
    SettlementNodeId node,
    bool allow_negative = false
) {
    return state.postings.create_account(
        AccountKey{
            kind,
            state.economy,
            OwnerId::institutional(owner_kind),
            state.currency,
            node,
        },
        Money(0.0),
        allow_negative
    );
}

}  // namespace

Result<RootState> build_genesis(const GenesisSpec& spec) {
    const auto validation = validate_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    const auto firm_count =
        spec.consumption_firms + spec.capital_firms;

    RootState state;
    state.economy = spec.economy;
    state.currency = spec.currency;
    state.seed = spec.seed;
    state.genesis_money = spec.aggregate_opening_money;
    for (const auto stream : spec.named_counter_streams) {
        const auto declared = state.named_counters.declare(stream);
        if (!declared.ok()) {
            return declared;
        }
    }

    std::vector<BankId> bank_ids;
    bank_ids.reserve(static_cast<std::size_t>(spec.settlement_banks));
    const double reserve_base =
        spec.aggregate_opening_money.value()
        / static_cast<double>(spec.settlement_banks);
    double assigned_reserves = 0.0;
    for (std::uint64_t index = 0; index < spec.settlement_banks; ++index) {
        auto bank_result = state.banks.create(BankComponent{});
        if (!bank_result.ok()) {
            return bank_result.status();
        }
        const auto bank_receipt = *bank_result.get_if();
        const double reserve =
            index + 1 == spec.settlement_banks
            ? spec.aggregate_opening_money.value() - assigned_reserves
            : reserve_base;
        assigned_reserves += reserve;
        auto node_result = state.reserves.create_position(
            bank_receipt.id,
            Money(reserve)
        );
        if (!node_result.ok()) {
            return node_result.status();
        }
        const auto node = *node_result.get_if();
        auto cash_result = state.postings.create_account(
            AccountKey{
                AccountKind::bank_cash,
                state.economy,
                OwnerId::bank(bank_receipt.id),
                state.currency,
                node,
            },
            Money(0.0),
            true
        );
        if (!cash_result.ok()) {
            return cash_result.status();
        }
        state.postings.get(*cash_result.get_if())->balance =
            spec.bank_opening_money;
        auto* bank = state.banks.get(bank_receipt.id);
        bank->cash_account = *cash_result.get_if();
        bank->settlement_node = node;
        bank_ids.push_back(bank_receipt.id);
    }

    const auto institutional_node =
        state.banks.get(bank_ids.front())->settlement_node;
    auto residual_result = create_institution_account(
        state,
        AccountKind::rounding_residual,
        OwnerKind::rounding_residual,
        institutional_node,
        true
    );
    if (!residual_result.ok()) {
        return residual_result.status();
    }
    state.institutions.rounding_residual_account = *residual_result.get_if();

    auto central_bank_result = create_institution_account(
        state,
        AccountKind::central_bank,
        OwnerKind::central_bank,
        institutional_node,
        true
    );
    if (!central_bank_result.ok()) {
        return central_bank_result.status();
    }
    state.institutions.central_bank_account = *central_bank_result.get_if();

    auto dealer_result = create_institution_account(
        state,
        AccountKind::dealer,
        OwnerKind::dealer,
        institutional_node,
        true
    );
    if (!dealer_result.ok()) {
        return dealer_result.status();
    }
    state.institutions.dealer_account = *dealer_result.get_if();

    if (spec.use_per_agent_endowments) {
        auto clearing_result = create_institution_account(
            state,
            AccountKind::clearing,
            OwnerKind::institution,
            institutional_node
        );
        if (!clearing_result.ok()) {
            return clearing_result.status();
        }
        state.institutions.clearing_account = *clearing_result.get_if();
    }

    if (spec.government) {
        auto treasury_result = create_institution_account(
            state,
            AccountKind::treasury,
            OwnerKind::treasury,
            institutional_node,
            true
        );
        if (!treasury_result.ok()) {
            return treasury_result.status();
        }
        state.institutions.treasury_account = *treasury_result.get_if();
    }

    const double bank_total =
        static_cast<double>(spec.settlement_banks)
        * spec.bank_opening_money.value();
    const double non_bank_total =
        spec.aggregate_opening_money.value() - bank_total;
    const double household_total = spec.use_per_agent_endowments
        ? static_cast<double>(spec.households)
            * spec.household_opening_money.value()
        : non_bank_total;
    const double household_base = spec.use_per_agent_endowments
        ? spec.household_opening_money.value()
        : household_total / static_cast<double>(spec.households);
    double assigned_money = 0.0;
    std::vector<HouseholdId> household_ids;
    household_ids.reserve(static_cast<std::size_t>(spec.households));
    for (std::uint64_t index = 0; index < spec.households; ++index) {
        auto household_result = state.households.create(HouseholdComponent{});
        if (!household_result.ok()) {
            return household_result.status();
        }
        const auto household_receipt = *household_result.get_if();
        const auto bank_index = static_cast<std::size_t>(
            index % spec.settlement_banks
        );
        const auto* bank = state.banks.get(bank_ids[bank_index]);
        const double opening =
            index + 1 == spec.households
            ? household_total - assigned_money
            : household_base;
        assigned_money += opening;
        auto account_result = state.postings.create_account(
            AccountKey{
                AccountKind::deposit,
                state.economy,
                OwnerId::household(household_receipt.id),
                state.currency,
                bank->settlement_node,
            },
            Money(opening)
        );
        if (!account_result.ok()) {
            return account_result.status();
        }
        state.households.get(household_receipt.id)->primary_account =
            *account_result.get_if();
        household_ids.push_back(household_receipt.id);
    }

    const auto capital_count = spec.opening_capital_to_consumption_firms
        ? spec.consumption_firms
        : spec.capital_firms;
    const double capital_base =
        capital_count == 0
        ? 0.0
        : spec.aggregate_opening_capital.value()
            / static_cast<double>(capital_count);
    double assigned_capital = 0.0;
    double assigned_firm_money = 0.0;
    for (std::uint64_t index = 0; index < firm_count; ++index) {
        const bool is_capital = index >= spec.consumption_firms;
        const bool receives_capital =
            spec.opening_capital_to_consumption_firms
            ? !is_capital
            : is_capital;
        double opening_capital = 0.0;
        if (receives_capital) {
            const auto capital_index = spec.opening_capital_to_consumption_firms
                ? index
                : index - spec.consumption_firms;
            opening_capital =
                capital_index + 1 == capital_count
                ? spec.aggregate_opening_capital.value() - assigned_capital
                : capital_base;
            assigned_capital += opening_capital;
        }
        auto firm_result = state.firms.create(
            FirmComponent{
                is_capital ? FirmSector::capital : FirmSector::consumption,
                AccountId{},
                Goods(0.0),
                Capital(opening_capital),
                1.0,
            }
        );
        if (!firm_result.ok()) {
            return firm_result.status();
        }
        const auto firm_receipt = *firm_result.get_if();
        const auto bank_index = static_cast<std::size_t>(
            index % spec.settlement_banks
        );
        const auto* bank = state.banks.get(bank_ids[bank_index]);
        double opening_money = 0.0;
        if (spec.use_per_agent_endowments) {
            const double sector_opening =
                is_capital && spec.capital_firm_opening_money.has_value()
                    ? spec.capital_firm_opening_money->value()
                    : spec.firm_opening_money.value();
            opening_money =
                index + 1 == firm_count
                ? non_bank_total
                    - household_total - assigned_firm_money
                : sector_opening;
            assigned_firm_money += opening_money;
        }
        auto account_result = state.postings.create_account(
            AccountKey{
                AccountKind::deposit,
                state.economy,
                OwnerId::firm(firm_receipt.id),
                state.currency,
                bank->settlement_node,
            },
            Money(opening_money)
        );
        if (!account_result.ok()) {
            return account_result.status();
        }
        state.firms.get(firm_receipt.id)->primary_account =
            *account_result.get_if();
        const auto owner = household_ids[
            static_cast<std::size_t>(index % spec.households)
        ];
        auto lot_result = state.ownership.create_lot(
            AssetKey{
                AssetKind::firm_equity,
                state.economy,
                firm_receipt.id.value(),
            },
            OwnerId::household(owner),
            1.0
        );
        if (!lot_result.ok()) {
            return lot_result.status();
        }
    }

    return Result<RootState>(std::move(state));
}

}  // namespace macro_sim::core
