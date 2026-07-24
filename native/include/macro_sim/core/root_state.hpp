#ifndef MACRO_SIM_CORE_ROOT_STATE_HPP
#define MACRO_SIM_CORE_ROOT_STATE_HPP

#include <vector>

#include "macro_sim/core/accounting.hpp"
#include "macro_sim/core/financial.hpp"
#include "macro_sim/core/slot_store.hpp"
#include "macro_sim/core/state_types.hpp"

namespace macro_sim::core {

struct InstitutionRegistry final {
    AccountId central_bank_account{};
    AccountId dealer_account{};
    AccountId rounding_residual_account{};
    AccountId treasury_account{};
    AccountId clearing_account{};
};

struct RootState final {
    EconomyId economy{};
    CurrencyId currency{};
    std::uint64_t seed{0};
    Money genesis_money{};
    double accounting_tolerance{1.0e-8};
    bool transaction_active{false};

    SlotStore<HouseholdId, HouseholdComponent> households;
    SlotStore<FirmId, FirmComponent> firms;
    SlotStore<BankId, BankComponent> banks;
    PostingBook postings;
    ReserveBook reserves;
    LoanBook loans;
    InterbankBook interbank;
    CentralBankOperationBook central_bank_operations;
    BankPnlJournal bank_pnl;
    BankCapitalState bank_capital;
    OwnershipBook ownership;
    NamedCounterBook named_counters;
    InstitutionRegistry institutions;
};

enum class GenesisVertical : std::uint8_t {
    m4_v0_cash_loop = 0,
    m4_v1_capital_fiscal = 1,
};

struct GenesisSpec final {
    GenesisVertical vertical{GenesisVertical::m4_v0_cash_loop};
    EconomyId economy{EconomyId(1)};
    CurrencyId currency{CurrencyId(1)};
    std::uint64_t households{1};
    std::uint64_t consumption_firms{1};
    std::uint64_t capital_firms{0};
    std::uint64_t settlement_banks{1};
    bool government{false};
    Money aggregate_opening_money{Money(100.0)};
    Capital aggregate_opening_capital{};
    std::uint64_t seed{0};
    std::vector<std::uint64_t> named_counter_streams;
    bool use_per_agent_endowments{false};
    Money household_opening_money{};
    Money firm_opening_money{};
    Money bank_opening_money{};
    bool opening_capital_to_consumption_firms{false};
};

[[nodiscard]] Result<RootState> build_genesis(const GenesisSpec& spec);

}  // namespace macro_sim::core

#endif
