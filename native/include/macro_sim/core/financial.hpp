#ifndef MACRO_SIM_CORE_FINANCIAL_HPP
#define MACRO_SIM_CORE_FINANCIAL_HPP

#include <cstddef>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

struct InterbankRecord final {
    InterbankContractId id{};
    BankId lender{};
    BankId borrower{};
    Money principal{};
    Rate rate{};
    Money accrued_interest{};
    Tick originated_tick{};
    Tick maturity_tick{};
    bool active{true};

    bool operator==(const InterbankRecord&) const = default;
};

class InterbankBook final {
public:
    [[nodiscard]] InterbankRecord* get(InterbankContractId id) noexcept;
    [[nodiscard]] const InterbankRecord* get(
        InterbankContractId id
    ) const noexcept;
    [[nodiscard]] const std::vector<InterbankRecord>& records() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] Money total_principal() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void replace_records(std::vector<InterbankRecord>& projection) noexcept;

private:
    std::vector<InterbankRecord> records_;
};

enum class CentralBankOperationKind : std::uint8_t {
    reserve_absorption = 0,
    lender_of_last_resort = 1,
};

struct CentralBankOperationRecord final {
    CentralBankOperationId id{};
    CentralBankOperationKind kind{
        CentralBankOperationKind::reserve_absorption
    };
    BankId counterparty{};
    Money principal{};
    Rate rate{};
    Tick opened_tick{};
    Tick maturity_tick{};
    bool active{true};

    bool operator==(const CentralBankOperationRecord&) const = default;
};

class CentralBankOperationBook final {
public:
    [[nodiscard]] CentralBankOperationRecord* get(
        CentralBankOperationId id
    ) noexcept;
    [[nodiscard]] const CentralBankOperationRecord* get(
        CentralBankOperationId id
    ) const noexcept;
    [[nodiscard]] const std::vector<CentralBankOperationRecord>& records()
        const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] Money total_principal(
        CentralBankOperationKind kind
    ) const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void replace_records(
        std::vector<CentralBankOperationRecord>& projection
    ) noexcept;

private:
    std::vector<CentralBankOperationRecord> records_;
};

struct BankPnlRecord final {
    BankId bank{};
    Tick tick{};
    double loan_interest{0.0};
    double interbank_interest_income{0.0};
    double interbank_interest_expense{0.0};
    double deposit_funding_cost{0.0};
    double realized_loan_losses{0.0};
    double realized_interbank_losses{0.0};
    double resolution_flow{0.0};
    double distributions{0.0};
    double net_income{0.0};

    bool operator==(const BankPnlRecord&) const = default;
};

class BankPnlJournal final {
public:
    [[nodiscard]] BankPnlRecord* get(BankId bank) noexcept;
    [[nodiscard]] const BankPnlRecord* get(BankId bank) const noexcept;
    [[nodiscard]] const std::vector<BankPnlRecord>& records() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void replace_records(std::vector<BankPnlRecord>& projection) noexcept;

private:
    std::vector<BankPnlRecord> records_;
};

struct BankCapitalRecord final {
    BankId bank{};
    double opening_capital{0.0};
    double closing_capital{0.0};
    double deposit_interest_arrears{0.0};
    Tick last_closed_tick{};
    bool alive{true};
    bool resolved{false};

    bool operator==(const BankCapitalRecord&) const = default;
};

class BankCapitalState final {
public:
    [[nodiscard]] BankCapitalRecord* get(BankId bank) noexcept;
    [[nodiscard]] const BankCapitalRecord* get(BankId bank) const noexcept;
    [[nodiscard]] const std::vector<BankCapitalRecord>& records() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void replace_records(std::vector<BankCapitalRecord>& projection) noexcept;

private:
    std::vector<BankCapitalRecord> records_;
};

}  // namespace macro_sim::core

#endif
