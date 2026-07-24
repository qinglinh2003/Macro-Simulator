#include "macro_sim/core/financial.hpp"

#include <algorithm>
#include <array>
#include <cmath>

namespace macro_sim::core {
namespace {

template <typename Id, typename Record>
[[nodiscard]] Record* indexed_get(
    std::vector<Record>& records,
    Id id
) noexcept {
    if (!id.valid() || id.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(id.value() - 1);
    return index < records.size() && records[index].id == id
        ? &records[index]
        : nullptr;
}

template <typename Id, typename Record>
[[nodiscard]] const Record* indexed_get(
    const std::vector<Record>& records,
    Id id
) noexcept {
    if (!id.valid() || id.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(id.value() - 1);
    return index < records.size() && records[index].id == id
        ? &records[index]
        : nullptr;
}

template <typename Record>
[[nodiscard]] Record* bank_get(
    std::vector<Record>& records,
    BankId bank
) noexcept {
    if (!bank.valid() || bank.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(bank.value() - 1);
    return index < records.size() && records[index].bank == bank
        ? &records[index]
        : nullptr;
}

template <typename Record>
[[nodiscard]] const Record* bank_get(
    const std::vector<Record>& records,
    BankId bank
) noexcept {
    if (!bank.valid() || bank.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(bank.value() - 1);
    return index < records.size() && records[index].bank == bank
        ? &records[index]
        : nullptr;
}

}  // namespace

InterbankRecord* InterbankBook::get(InterbankContractId id) noexcept {
    return indexed_get(records_, id);
}

const InterbankRecord* InterbankBook::get(
    InterbankContractId id
) const noexcept {
    return indexed_get(records_, id);
}

const std::vector<InterbankRecord>& InterbankBook::records() const noexcept {
    return records_;
}

std::size_t InterbankBook::size() const noexcept {
    return records_.size();
}

Money InterbankBook::total_principal() const noexcept {
    double total = 0.0;
    for (const auto& record : records_) {
        if (record.active) {
            total += record.principal.value();
        }
    }
    return Money(total);
}

Status InterbankBook::validate_finite() const noexcept {
    for (std::size_t index = 0; index < records_.size(); ++index) {
        const auto& record = records_[index];
        if (record.id.value() != index + 1 || !record.lender.valid()
            || !record.borrower.valid()
            || record.lender == record.borrower
            || !std::isfinite(record.principal.value())
            || record.principal.value() < 0.0
            || !std::isfinite(record.rate.value())
            || record.rate.value() < 0.0
            || !std::isfinite(record.accrued_interest.value())
            || record.accrued_interest.value() < 0.0
            || record.maturity_tick < record.originated_tick) {
            return Status(
                ErrorCode::invariant_violation,
                "interbank book contains an invalid record"
            );
        }
    }
    return Status::success();
}

void InterbankBook::replace_records(
    std::vector<InterbankRecord>& projection
) noexcept {
    records_.swap(projection);
}

CentralBankOperationRecord* CentralBankOperationBook::get(
    CentralBankOperationId id
) noexcept {
    return indexed_get(records_, id);
}

const CentralBankOperationRecord* CentralBankOperationBook::get(
    CentralBankOperationId id
) const noexcept {
    return indexed_get(records_, id);
}

const std::vector<CentralBankOperationRecord>&
CentralBankOperationBook::records() const noexcept {
    return records_;
}

std::size_t CentralBankOperationBook::size() const noexcept {
    return records_.size();
}

Money CentralBankOperationBook::total_principal(
    CentralBankOperationKind kind
) const noexcept {
    double total = 0.0;
    for (const auto& record : records_) {
        if (record.active && record.kind == kind) {
            total += record.principal.value();
        }
    }
    return Money(total);
}

Status CentralBankOperationBook::validate_finite() const noexcept {
    for (std::size_t index = 0; index < records_.size(); ++index) {
        const auto& record = records_[index];
        const auto kind = static_cast<std::uint8_t>(record.kind);
        if (record.id.value() != index + 1 || kind > 1U
            || !record.counterparty.valid()
            || !std::isfinite(record.principal.value())
            || record.principal.value() < 0.0
            || !std::isfinite(record.rate.value())
            || record.rate.value() < 0.0
            || record.maturity_tick < record.opened_tick) {
            return Status(
                ErrorCode::invariant_violation,
                "central-bank operation book contains an invalid record"
            );
        }
    }
    return Status::success();
}

void CentralBankOperationBook::replace_records(
    std::vector<CentralBankOperationRecord>& projection
) noexcept {
    records_.swap(projection);
}

BankPnlRecord* BankPnlJournal::get(BankId bank) noexcept {
    return bank_get(records_, bank);
}

const BankPnlRecord* BankPnlJournal::get(BankId bank) const noexcept {
    return bank_get(records_, bank);
}

const std::vector<BankPnlRecord>& BankPnlJournal::records() const noexcept {
    return records_;
}

std::size_t BankPnlJournal::size() const noexcept {
    return records_.size();
}

Status BankPnlJournal::validate_finite() const noexcept {
    for (std::size_t index = 0; index < records_.size(); ++index) {
        const auto& record = records_[index];
        const std::array values{
            record.loan_interest,
            record.interbank_interest_income,
            record.interbank_interest_expense,
            record.deposit_funding_cost,
            record.realized_loan_losses,
            record.realized_interbank_losses,
            record.resolution_flow,
            record.distributions,
            record.net_income,
        };
        if (record.bank.value() != index + 1
            || !std::all_of(
                values.begin(),
                values.end(),
                [](double value) { return std::isfinite(value); }
            )) {
            return Status(
                ErrorCode::invariant_violation,
                "bank P&L journal contains an invalid record"
            );
        }
    }
    return Status::success();
}

void BankPnlJournal::replace_records(
    std::vector<BankPnlRecord>& projection
) noexcept {
    records_.swap(projection);
}

BankCapitalRecord* BankCapitalState::get(BankId bank) noexcept {
    return bank_get(records_, bank);
}

const BankCapitalRecord* BankCapitalState::get(BankId bank) const noexcept {
    return bank_get(records_, bank);
}

const std::vector<BankCapitalRecord>&
BankCapitalState::records() const noexcept {
    return records_;
}

std::size_t BankCapitalState::size() const noexcept {
    return records_.size();
}

Status BankCapitalState::validate_finite() const noexcept {
    for (std::size_t index = 0; index < records_.size(); ++index) {
        const auto& record = records_[index];
        if (record.bank.value() != index + 1
            || !std::isfinite(record.opening_capital)
            || !std::isfinite(record.closing_capital)
            || !std::isfinite(record.deposit_interest_arrears)
            || record.deposit_interest_arrears < 0.0) {
            return Status(
                ErrorCode::invariant_violation,
                "bank capital state contains an invalid record"
            );
        }
    }
    return Status::success();
}

void BankCapitalState::replace_records(
    std::vector<BankCapitalRecord>& projection
) noexcept {
    records_.swap(projection);
}

}  // namespace macro_sim::core
