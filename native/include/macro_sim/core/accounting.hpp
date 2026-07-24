#ifndef MACRO_SIM_CORE_ACCOUNTING_HPP
#define MACRO_SIM_CORE_ACCOUNTING_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <utility>
#include <vector>

#include "macro_sim/core/state_types.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

class CheckpointCodec;
class AccountingBenchmarkAccess;
class SettlementTransaction;

struct AccountRecord final {
    AccountId id{};
    AccountKey key{};
    Money balance{};
    double roundoff_drift{0.0};
    bool allow_negative{false};
    bool open{true};

    bool operator==(const AccountRecord&) const = default;
};

class PostingBook final {
public:
    [[nodiscard]] Result<AccountId> create_account(
        AccountKey key,
        Money opening_balance,
        bool allow_negative = false
    );
    [[nodiscard]] Status close_account(AccountId id);
    [[nodiscard]] Result<AccountId> find(AccountKey key) const noexcept;
    [[nodiscard]] Result<SettlementNodeId> settlement_node(
        AccountId id
    ) const noexcept;
    [[nodiscard]] bool contains(AccountId id) const noexcept;
    [[nodiscard]] AccountRecord* get(AccountId id) noexcept;
    [[nodiscard]] const AccountRecord* get(AccountId id) const noexcept;
    [[nodiscard]] Result<Money> balance(AccountId id) const noexcept;
    [[nodiscard]] Money total_deposits() const noexcept;
    [[nodiscard]] double total_roundoff_drift() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] std::vector<AccountRecord>& records() noexcept;
    [[nodiscard]] const std::vector<AccountRecord>& records() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    [[nodiscard]] Status validate_nonnegative(double tolerance) const noexcept;

private:
    friend class AccountingBenchmarkAccess;
    friend class CheckpointCodec;
    friend class SettlementTransaction;

    struct MutationResult final {
        double old_balance{0.0};
        double old_roundoff_drift{0.0};
    };

    [[nodiscard]] MutationResult apply_delta_unchecked(
        AccountId id,
        double delta
    ) noexcept;
    void restore_unchecked(
        AccountId id,
        const MutationResult& previous
    ) noexcept;

    std::vector<AccountRecord> accounts_;
};

struct ReserveRecord final {
    SettlementNodeId node{};
    BankId bank{};
    Money balance{};
    double roundoff_drift{0.0};

    bool operator==(const ReserveRecord&) const = default;
};

class ReserveBook final {
public:
    [[nodiscard]] Result<SettlementNodeId> create_position(
        BankId bank,
        Money opening_balance
    );
    [[nodiscard]] bool contains(SettlementNodeId node) const noexcept;
    [[nodiscard]] ReserveRecord* get(SettlementNodeId node) noexcept;
    [[nodiscard]] const ReserveRecord* get(SettlementNodeId node) const noexcept;
    [[nodiscard]] Result<Money> balance(SettlementNodeId node) const noexcept;
    [[nodiscard]] Money total_reserves() const noexcept;
    [[nodiscard]] Money reserve_stock() const noexcept;
    [[nodiscard]] double reserve_stock_roundoff_drift() const noexcept;
    [[nodiscard]] double total_roundoff_drift() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] std::vector<ReserveRecord>& records() noexcept;
    [[nodiscard]] const std::vector<ReserveRecord>& records() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void commit_projected_stock(Money stock) noexcept;

private:
    friend class CheckpointCodec;
    friend class SettlementTransaction;

    struct MutationResult final {
        double old_balance{0.0};
        double old_roundoff_drift{0.0};
    };

    [[nodiscard]] MutationResult apply_delta_unchecked(
        SettlementNodeId node,
        double delta
    ) noexcept;
    [[nodiscard]] MutationResult apply_stock_delta_unchecked(
        double delta
    ) noexcept;
    void restore_stock_unchecked(const MutationResult& previous) noexcept;
    void restore_unchecked(
        SettlementNodeId node,
        const MutationResult& previous
    ) noexcept;

    std::vector<ReserveRecord> positions_;
    Money reserve_stock_{};
    double reserve_stock_roundoff_drift_{0.0};
};

struct LoanTerms final {
    Rate annual_rate{};
    Tick originated_tick{};
    Tick maturity_tick{};

    bool operator==(const LoanTerms&) const = default;
};

struct LoanRecord final {
    LoanId id{};
    BankId lender{};
    OwnerId borrower{};
    AccountId borrower_account{};
    Money principal{};
    double roundoff_drift{0.0};
    LoanTerms terms{};
    bool active{true};

    bool operator==(const LoanRecord&) const = default;
};

class LoanBook final {
public:
    [[nodiscard]] bool contains(LoanId id) const noexcept;
    [[nodiscard]] LoanRecord* get(LoanId id) noexcept;
    [[nodiscard]] const LoanRecord* get(LoanId id) const noexcept;
    [[nodiscard]] Money total_principal() const noexcept;
    [[nodiscard]] double total_roundoff_drift() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] const std::vector<LoanRecord>& records() const noexcept;
    [[nodiscard]] Status validate_finite() const noexcept;
    void replace_records(std::vector<LoanRecord>& projection) noexcept;

private:
    friend class CheckpointCodec;
    friend class SettlementTransaction;

    struct CreateResult final {
        LoanId id{};
    };

    struct MutationResult final {
        double old_principal{0.0};
        double old_roundoff_drift{0.0};
        bool old_active{true};
    };

    [[nodiscard]] CreateResult create_unchecked(
        BankId lender,
        OwnerId borrower,
        AccountId borrower_account,
        Money principal,
        LoanTerms terms
    );
    void rollback_create_unchecked(LoanId id) noexcept;
    [[nodiscard]] MutationResult apply_principal_delta_unchecked(
        LoanId id,
        double delta
    ) noexcept;
    void restore_unchecked(LoanId id, const MutationResult& previous) noexcept;

    std::vector<LoanRecord> loans_;
};

struct OwnershipLot final {
    OwnershipLotId id{};
    AssetKey asset{};
    OwnerId owner{};
    double share{0.0};
    bool active{true};

    bool operator==(const OwnershipLot&) const = default;
};

class OwnershipBook final {
public:
    [[nodiscard]] Result<OwnershipLotId> create_lot(
        AssetKey asset,
        OwnerId owner,
        double share
    );
    [[nodiscard]] bool contains(OwnershipLotId id) const noexcept;
    [[nodiscard]] OwnershipLot* get(OwnershipLotId id) noexcept;
    [[nodiscard]] const OwnershipLot* get(OwnershipLotId id) const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] const std::vector<OwnershipLot>& records() const noexcept;
    [[nodiscard]] Status validate_shares(double tolerance) const;

private:
    friend class CheckpointCodec;
    friend class SettlementTransaction;

    struct MutationResult final {
        OwnerId old_owner{};
        double old_share{0.0};
        bool old_active{true};
    };

    [[nodiscard]] MutationResult mutate_unchecked(
        OwnershipLotId id,
        OwnerId owner,
        double share
    ) noexcept;
    void restore_unchecked(
        OwnershipLotId id,
        const MutationResult& previous
    ) noexcept;

    std::vector<OwnershipLot> lots_;
};

class NamedCounterBook final {
public:
    [[nodiscard]] Status declare(std::uint64_t stream_id);
    [[nodiscard]] std::uint64_t value(std::uint64_t stream_id) const noexcept;
    [[nodiscard]] bool contains(std::uint64_t stream_id) const noexcept;
    [[nodiscard]] Result<std::uint64_t> increment(std::uint64_t stream_id);
    [[nodiscard]] const std::vector<std::pair<std::uint64_t, std::uint64_t>>&
    records() const noexcept;

private:
    friend class CheckpointCodec;
    friend class SettlementTransaction;
    void set_unchecked(std::uint64_t stream_id, std::uint64_t value);
    void erase_unchecked(std::uint64_t stream_id) noexcept;

    std::vector<std::pair<std::uint64_t, std::uint64_t>> counters_;
};

[[nodiscard]] double neumaier_sum(std::span<const double> values) noexcept;

}  // namespace macro_sim::core

#endif
