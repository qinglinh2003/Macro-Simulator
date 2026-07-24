#ifndef MACRO_SIM_CORE_TRANSACTION_HPP
#define MACRO_SIM_CORE_TRANSACTION_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"

namespace macro_sim::core {

enum class TransactionState : std::uint8_t {
    collecting = 0,
    committed = 1,
    rejected = 2,
};

struct TransactionReceipt final {
    StateDigest before{};
    StateDigest after{};
    std::uint64_t applied_mutations{0};
    std::vector<LoanId> created_loans;
};

struct TransferCommand final {
    AccountId source{};
    AccountId destination{};
    Money amount{};
};

struct ReserveTransferCommand final {
    SettlementNodeId source{};
    SettlementNodeId destination{};
    Money amount{};
};

struct ReserveIssueCommand final {
    SettlementNodeId destination{};
    Money amount{};
};

struct LoanOriginationCommand final {
    BankId lender{};
    OwnerId borrower{};
    AccountId borrower_account{};
    Money amount{};
    LoanTerms terms{};
};

struct LoanRepaymentCommand final {
    LoanId loan{};
    AccountId payer_account{};
    Money amount{};
};

struct OwnershipCommand final {
    OwnershipLotId lot{};
    OwnerId owner{};
    double share{0.0};
};

struct CounterCommand final {
    std::uint64_t stream_id{0};
    std::uint64_t amount{0};
};

struct SettlementBatch final {
    std::vector<TransferCommand> transfers;
    std::vector<ReserveTransferCommand> reserve_transfers;
    std::vector<ReserveIssueCommand> reserve_issues;
    std::vector<LoanOriginationCommand> originations;
    std::vector<LoanRepaymentCommand> repayments;
    std::vector<OwnershipCommand> ownership_mutations;
    std::vector<CounterCommand> counter_increments;
};

class SettlementTransaction final {
public:
    explicit SettlementTransaction(
        RootState& state,
        std::optional<std::uint64_t> fault_ordinal = std::nullopt
    ) noexcept;
    SettlementTransaction(const SettlementTransaction&) = delete;
    SettlementTransaction& operator=(const SettlementTransaction&) = delete;
    SettlementTransaction(SettlementTransaction&&) = delete;
    SettlementTransaction& operator=(SettlementTransaction&&) = delete;
    ~SettlementTransaction();

    [[nodiscard]] Status transfer(
        AccountId source,
        AccountId destination,
        Money amount
    );
    [[nodiscard]] Status move_reserves(
        SettlementNodeId source,
        SettlementNodeId destination,
        Money amount
    );
    [[nodiscard]] Status issue_reserves(
        SettlementNodeId destination,
        Money amount
    );
    [[nodiscard]] Status originate_loan(
        BankId lender,
        OwnerId borrower,
        AccountId borrower_account,
        Money amount,
        LoanTerms terms
    );
    [[nodiscard]] Status repay_loan(
        LoanId loan,
        AccountId payer_account,
        Money amount
    );
    [[nodiscard]] Status mutate_ownership(
        OwnershipLotId lot,
        OwnerId owner,
        double share
    );
    [[nodiscard]] Status increment_counter(
        std::uint64_t stream_id,
        std::uint64_t amount = 1
    );
    [[nodiscard]] Status append(const SettlementBatch& batch);
    [[nodiscard]] Result<TransactionReceipt> commit();
    [[nodiscard]] TransactionState transaction_state() const noexcept;
    [[nodiscard]] std::uint64_t next_fault_ordinal() const noexcept;

private:
    struct TransferIntent final {
        AccountId source{};
        AccountId destination{};
        double amount{0.0};
    };

    struct ReserveTransferIntent final {
        SettlementNodeId source{};
        SettlementNodeId destination{};
        double amount{0.0};
    };

    struct ReserveIssueIntent final {
        SettlementNodeId destination{};
        double amount{0.0};
    };

    struct LoanOriginationIntent final {
        BankId lender{};
        OwnerId borrower{};
        AccountId borrower_account{};
        double amount{0.0};
        LoanTerms terms{};
    };

    struct LoanRepaymentIntent final {
        LoanId loan{};
        AccountId payer_account{};
        double amount{0.0};
    };

    struct OwnershipIntent final {
        OwnershipLotId lot{};
        OwnerId owner{};
        double share{0.0};
    };

    struct CounterIntent final {
        std::uint64_t stream_id{0};
        std::uint64_t amount{0};
    };

    struct PostingUndo final {
        AccountId id{};
        PostingBook::MutationResult previous{};
    };

    struct ReserveUndo final {
        SettlementNodeId node{};
        ReserveBook::MutationResult previous{};
    };

    struct LoanUndo final {
        LoanId id{};
        LoanBook::MutationResult previous{};
    };

    struct OwnershipUndo final {
        OwnershipLotId id{};
        OwnershipBook::MutationResult previous{};
    };

    struct CounterUndo final {
        std::uint64_t stream_id{0};
        std::uint64_t previous{0};
        bool existed{false};
    };

    [[nodiscard]] Status require_collecting() const noexcept;
    [[nodiscard]] bool inject_fault() noexcept;
    [[nodiscard]] Result<TransactionReceipt> reject(Status status) noexcept;
    void rollback() noexcept;
    void release_root() noexcept;

    RootState* root_{nullptr};
    TransactionState state_{TransactionState::collecting};
    Status construction_status_{};
    std::optional<std::uint64_t> fault_ordinal_;
    std::uint64_t current_fault_ordinal_{0};

    std::vector<TransferIntent> transfers_;
    std::vector<ReserveTransferIntent> reserve_transfers_;
    std::vector<ReserveIssueIntent> reserve_issues_;
    std::vector<LoanOriginationIntent> originations_;
    std::vector<LoanRepaymentIntent> repayments_;
    std::vector<OwnershipIntent> ownership_mutations_;
    std::vector<CounterIntent> counter_increments_;

    std::vector<PostingUndo> posting_undo_;
    std::vector<ReserveUndo> reserve_undo_;
    std::optional<ReserveBook::MutationResult> reserve_stock_undo_;
    std::vector<LoanUndo> loan_undo_;
    std::vector<LoanId> created_loans_;
    std::vector<OwnershipUndo> ownership_undo_;
    std::vector<CounterUndo> counter_undo_;
};

using TickTransaction = SettlementTransaction;

struct WorldTransactionReceipt final {
    std::vector<TransactionReceipt> roots;
};

class WorldTransaction final {
public:
    [[nodiscard]] Status add(
        RootState& root,
        SettlementBatch batch,
        std::optional<std::uint64_t> fault_ordinal = std::nullopt
    );
    [[nodiscard]] Result<WorldTransactionReceipt> commit();

private:
    struct Entry final {
        RootState* root{nullptr};
        SettlementBatch batch;
        std::optional<std::uint64_t> fault_ordinal;
    };

    bool committed_{false};
    std::vector<Entry> entries_;
};

}  // namespace macro_sim::core

#endif
