#include "macro_sim/core/transaction.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>

#include "macro_sim/core/checkpoint.hpp"
#include "macro_sim/core/invariants.hpp"

namespace macro_sim::core {
namespace {

template <typename Id>
struct Delta final {
    Id id{};
    double amount{0.0};
};

[[nodiscard]] Status validate_nonnegative_amount(
    double amount,
    const char* message
) noexcept {
    if (!std::isfinite(amount) || amount < 0.0) {
        return Status(ErrorCode::invalid_argument, message);
    }
    return Status::success();
}

[[nodiscard]] double residual_bound(double absolute_sum) noexcept {
    return 8.0 * std::numeric_limits<double>::epsilon()
        * std::max(1.0, absolute_sum);
}

}  // namespace

SettlementTransaction::SettlementTransaction(
    RootState& state,
    std::optional<std::uint64_t> fault_ordinal
) noexcept
    : root_(&state), fault_ordinal_(fault_ordinal) {
    if (state.transaction_active) {
        construction_status_ = Status(
            ErrorCode::invalid_transaction_state,
            "root already has an active transaction"
        );
        state_ = TransactionState::rejected;
        root_ = nullptr;
        return;
    }
    state.transaction_active = true;
}

SettlementTransaction::~SettlementTransaction() {
    release_root();
}

Status SettlementTransaction::require_collecting() const noexcept {
    if (!construction_status_.ok()) {
        return construction_status_;
    }
    if (state_ != TransactionState::collecting || root_ == nullptr) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "transaction is not collecting"
        );
    }
    return Status::success();
}

Status SettlementTransaction::transfer(
    AccountId source,
    AccountId destination,
    Money amount
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    const auto valid = validate_nonnegative_amount(
        amount.value(),
        "transfer amount must be finite and nonnegative"
    );
    if (!valid.ok()) {
        return valid;
    }
    transfers_.push_back({source, destination, amount.value()});
    return Status::success();
}

Status SettlementTransaction::move_reserves(
    SettlementNodeId source,
    SettlementNodeId destination,
    Money amount
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    const auto valid = validate_nonnegative_amount(
        amount.value(),
        "reserve transfer amount must be finite and nonnegative"
    );
    if (!valid.ok()) {
        return valid;
    }
    reserve_transfers_.push_back({source, destination, amount.value()});
    return Status::success();
}

Status SettlementTransaction::issue_reserves(
    SettlementNodeId destination,
    Money amount
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (!std::isfinite(amount.value())) {
        return Status(
            ErrorCode::invalid_argument,
            "reserve issue amount must be finite"
        );
    }
    reserve_issues_.push_back({destination, amount.value()});
    return Status::success();
}

Status SettlementTransaction::originate_loan(
    BankId lender,
    OwnerId borrower,
    AccountId borrower_account,
    Money amount,
    LoanTerms terms
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    const auto valid = validate_nonnegative_amount(
        amount.value(),
        "loan amount must be finite and nonnegative"
    );
    if (!valid.ok()) {
        return valid;
    }
    if (!std::isfinite(terms.annual_rate.value())) {
        return Status(ErrorCode::invalid_argument, "loan rate must be finite");
    }
    originations_.push_back(
        {lender, borrower, borrower_account, amount.value(), terms}
    );
    return Status::success();
}

Status SettlementTransaction::repay_loan(
    LoanId loan,
    AccountId payer_account,
    Money amount
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    const auto valid = validate_nonnegative_amount(
        amount.value(),
        "repayment amount must be finite and nonnegative"
    );
    if (!valid.ok()) {
        return valid;
    }
    repayments_.push_back({loan, payer_account, amount.value()});
    return Status::success();
}

Status SettlementTransaction::mutate_ownership(
    OwnershipLotId lot,
    OwnerId owner,
    double share
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (!owner.valid() || !std::isfinite(share) || share < 0.0
        || share > 1.0) {
        return Status(
            ErrorCode::invalid_argument,
            "ownership mutation is invalid"
        );
    }
    ownership_mutations_.push_back({lot, owner, share});
    return Status::success();
}

Status SettlementTransaction::increment_counter(
    std::uint64_t stream_id,
    std::uint64_t amount
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (stream_id == 0 || amount == 0) {
        return Status(
            ErrorCode::invalid_argument,
            "counter increment requires nonzero IDs and amounts"
        );
    }
    counter_increments_.push_back({stream_id, amount});
    return Status::success();
}

Status SettlementTransaction::append(const SettlementBatch& batch) {
    for (const auto& command : batch.transfers) {
        const auto status =
            transfer(command.source, command.destination, command.amount);
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.reserve_transfers) {
        const auto status =
            move_reserves(
                command.source,
                command.destination,
                command.amount
            );
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.reserve_issues) {
        const auto status =
            issue_reserves(command.destination, command.amount);
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.originations) {
        const auto status =
            originate_loan(
                command.lender,
                command.borrower,
                command.borrower_account,
                command.amount,
                command.terms
            );
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.repayments) {
        const auto status =
            repay_loan(
                command.loan,
                command.payer_account,
                command.amount
            );
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.ownership_mutations) {
        const auto status =
            mutate_ownership(command.lot, command.owner, command.share);
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto& command : batch.counter_increments) {
        const auto status =
            increment_counter(command.stream_id, command.amount);
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

bool SettlementTransaction::inject_fault() noexcept {
    const bool inject =
        fault_ordinal_.has_value()
        && *fault_ordinal_ == current_fault_ordinal_;
    ++current_fault_ordinal_;
    return inject;
}

Result<TransactionReceipt> SettlementTransaction::reject(
    Status status
) noexcept {
    rollback();
    state_ = TransactionState::rejected;
    release_root();
    return status;
}

Result<TransactionReceipt> SettlementTransaction::commit() {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    const auto before = state_digest(*root_);
    std::vector<double> posting_totals(root_->postings.size(), 0.0);
    std::vector<double> reserve_totals(root_->reserves.size(), 0.0);
    std::vector<double> loan_totals(root_->loans.size(), 0.0);
    double reserve_stock_delta = 0.0;
    double new_loan_total = 0.0;
    double absolute_economic_sum = 0.0;

    for (const auto& intent : transfers_) {
        const auto* source = root_->postings.get(intent.source);
        const auto* destination = root_->postings.get(intent.destination);
        if (source == nullptr || destination == nullptr || !source->open
            || !destination->open) {
            return reject(
                Status(ErrorCode::not_found, "transfer account is absent")
            );
        }
        if (intent.source == intent.destination || intent.amount == 0.0) {
            continue;
        }
        posting_totals[
            static_cast<std::size_t>(intent.source.value() - 1)
        ] -= intent.amount;
        posting_totals[
            static_cast<std::size_t>(intent.destination.value() - 1)
        ] += intent.amount;
        absolute_economic_sum += 2.0 * intent.amount;
        const auto source_node = source->key.settlement_node;
        const auto destination_node = destination->key.settlement_node;
        if (source_node != destination_node) {
            if (!root_->reserves.contains(source_node)
                || !root_->reserves.contains(destination_node)) {
                return reject(
                    Status(
                        ErrorCode::not_found,
                        "settlement node is absent"
                    )
                );
            }
            reserve_totals[
                static_cast<std::size_t>(source_node.value() - 1)
            ] -= intent.amount;
            reserve_totals[
                static_cast<std::size_t>(destination_node.value() - 1)
            ] += intent.amount;
        }
    }

    for (const auto& intent : reserve_transfers_) {
        if (!root_->reserves.contains(intent.source)
            || !root_->reserves.contains(intent.destination)) {
            return reject(
                Status(ErrorCode::not_found, "reserve position is absent")
            );
        }
        if (intent.source == intent.destination || intent.amount == 0.0) {
            continue;
        }
        reserve_totals[
            static_cast<std::size_t>(intent.source.value() - 1)
        ] -= intent.amount;
        reserve_totals[
            static_cast<std::size_t>(intent.destination.value() - 1)
        ] += intent.amount;
    }

    for (const auto& intent : reserve_issues_) {
        if (!root_->reserves.contains(intent.destination)) {
            return reject(
                Status(ErrorCode::not_found, "reserve position is absent")
            );
        }
        reserve_totals[
            static_cast<std::size_t>(intent.destination.value() - 1)
        ] += intent.amount;
        reserve_stock_delta += intent.amount;
    }

    for (const auto& intent : originations_) {
        const auto* account = root_->postings.get(intent.borrower_account);
        if (root_->banks.get(intent.lender) == nullptr || account == nullptr
            || !account->open || account->key.owner != intent.borrower) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "loan parties do not match canonical state"
                )
            );
        }
        posting_totals[
            static_cast<std::size_t>(intent.borrower_account.value() - 1)
        ] += intent.amount;
        new_loan_total += intent.amount;
        absolute_economic_sum += 2.0 * intent.amount;
    }

    for (const auto& intent : repayments_) {
        const auto* loan = root_->loans.get(intent.loan);
        const auto* account = root_->postings.get(intent.payer_account);
        if (loan == nullptr || account == nullptr || !account->open
            || loan->borrower_account != intent.payer_account) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "repayment parties do not match the loan"
                )
            );
        }
        posting_totals[
            static_cast<std::size_t>(intent.payer_account.value() - 1)
        ] -= intent.amount;
        loan_totals[static_cast<std::size_t>(intent.loan.value() - 1)] -=
            intent.amount;
        absolute_economic_sum += 2.0 * intent.amount;
    }

    for (std::size_t index = 0; index < posting_totals.size(); ++index) {
        const auto* account = root_->postings.get(
            AccountId(static_cast<std::uint64_t>(index) + 1)
        );
        const double final_balance =
            account->balance.value() + posting_totals[index];
        if (!std::isfinite(final_balance)) {
            return reject(
                Status(ErrorCode::out_of_range, "account overflow")
            );
        }
        if (!account->allow_negative
            && final_balance < -root_->accounting_tolerance) {
            return reject(
                Status(ErrorCode::insufficient_funds, "account overdraft")
            );
        }
    }

    for (std::size_t index = 0; index < reserve_totals.size(); ++index) {
        const auto* reserve = root_->reserves.get(
            SettlementNodeId(static_cast<std::uint64_t>(index) + 1)
        );
        if (!std::isfinite(reserve->balance.value() + reserve_totals[index])) {
            return reject(
                Status(ErrorCode::out_of_range, "reserve overflow")
            );
        }
    }

    for (std::size_t index = 0; index < loan_totals.size(); ++index) {
        const auto* loan = root_->loans.get(
            LoanId(static_cast<std::uint64_t>(index) + 1)
        );
        const double final_principal =
            loan->principal.value() + loan_totals[index];
        if (!std::isfinite(final_principal)
            || final_principal < -root_->accounting_tolerance) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "repayment exceeds loan principal"
                )
            );
        }
    }

    const double posting_sum = neumaier_sum(posting_totals);
    const double existing_loan_sum = neumaier_sum(loan_totals);
    const double economic_residual =
        posting_sum - existing_loan_sum - new_loan_total;
    const double allowed_residual = residual_bound(absolute_economic_sum);
    if (std::abs(economic_residual) > allowed_residual) {
        return reject(
            Status(
                ErrorCode::unbalanced_transaction,
                "economic transaction is not balanced"
            )
        );
    }
    if (economic_residual != 0.0) {
        const auto residual = root_->institutions.rounding_residual_account;
        if (!root_->postings.contains(residual)) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "rounding residual account is absent"
                )
            );
        }
        posting_totals[
            static_cast<std::size_t>(residual.value() - 1)
        ] -= economic_residual;
    }

    if (std::abs(neumaier_sum(reserve_totals) - reserve_stock_delta)
        > residual_bound(std::abs(reserve_stock_delta))) {
        return reject(
            Status(
                ErrorCode::unbalanced_transaction,
                "reserve transaction is not balanced"
            )
        );
    }

    std::vector<Delta<AccountId>> posting_deltas;
    std::vector<Delta<SettlementNodeId>> reserve_deltas;
    std::vector<Delta<LoanId>> loan_deltas;
    posting_deltas.reserve(posting_totals.size());
    reserve_deltas.reserve(reserve_totals.size());
    loan_deltas.reserve(loan_totals.size());
    for (std::size_t index = 0; index < posting_totals.size(); ++index) {
        if (posting_totals[index] != 0.0) {
            posting_deltas.push_back(
                {
                    AccountId(static_cast<std::uint64_t>(index) + 1),
                    posting_totals[index],
                }
            );
        }
    }
    for (std::size_t index = 0; index < reserve_totals.size(); ++index) {
        if (reserve_totals[index] != 0.0) {
            reserve_deltas.push_back(
                {
                    SettlementNodeId(
                        static_cast<std::uint64_t>(index) + 1
                    ),
                    reserve_totals[index],
                }
            );
        }
    }
    for (std::size_t index = 0; index < loan_totals.size(); ++index) {
        if (loan_totals[index] != 0.0) {
            loan_deltas.push_back(
                {
                    LoanId(static_cast<std::uint64_t>(index) + 1),
                    loan_totals[index],
                }
            );
        }
    }

    posting_undo_.reserve(posting_deltas.size());
    reserve_undo_.reserve(reserve_deltas.size());
    loan_undo_.reserve(loan_deltas.size());
    created_loans_.reserve(originations_.size());
    ownership_undo_.reserve(ownership_mutations_.size());
    counter_undo_.reserve(counter_increments_.size());
    root_->loans.loans_.reserve(
        root_->loans.loans_.size() + originations_.size()
    );
    root_->named_counters.counters_.reserve(
        root_->named_counters.counters_.size() + counter_increments_.size()
    );
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    std::uint64_t mutations = 0;
    for (const auto& delta : posting_deltas) {
        posting_undo_.push_back(
            {
                delta.id,
                root_->postings.apply_delta_unchecked(
                    delta.id,
                    delta.amount
                ),
            }
        );
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    for (const auto& delta : reserve_deltas) {
        reserve_undo_.push_back(
            {
                delta.id,
                root_->reserves.apply_delta_unchecked(
                    delta.id,
                    delta.amount
                ),
            }
        );
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    if (reserve_stock_delta != 0.0) {
        reserve_stock_undo_ =
            root_->reserves.apply_stock_delta_unchecked(reserve_stock_delta);
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    for (const auto& delta : loan_deltas) {
        loan_undo_.push_back(
            {
                delta.id,
                root_->loans.apply_principal_delta_unchecked(
                    delta.id,
                    delta.amount
                ),
            }
        );
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    for (const auto& intent : originations_) {
        const auto created = root_->loans.create_unchecked(
            intent.lender,
            intent.borrower,
            intent.borrower_account,
            Money(intent.amount),
            intent.terms
        );
        created_loans_.push_back(created.id);
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    for (const auto& intent : ownership_mutations_) {
        if (!root_->ownership.contains(intent.lot)) {
            return reject(
                Status(ErrorCode::not_found, "ownership lot is absent")
            );
        }
        ownership_undo_.push_back(
            {
                intent.lot,
                root_->ownership.mutate_unchecked(
                    intent.lot,
                    intent.owner,
                    intent.share
                ),
            }
        );
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }
    for (const auto& intent : counter_increments_) {
        const auto previous = root_->named_counters.value(intent.stream_id);
        if (intent.amount
            > std::numeric_limits<std::uint64_t>::max() - previous) {
            return reject(
                Status(ErrorCode::out_of_range, "named counter overflow")
            );
        }
        counter_undo_.push_back(
            {
                intent.stream_id,
                previous,
                root_->named_counters.contains(intent.stream_id),
            }
        );
        root_->named_counters.set_unchecked(
            intent.stream_id,
            previous + intent.amount
        );
        ++mutations;
        if (inject_fault()) {
            return reject(
                Status(ErrorCode::internal_error, "injected transaction fault")
            );
        }
    }

    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }
    const auto invariants = run_invariants(*root_);
    if (!invariants.ok()) {
        return reject(invariants.status);
    }
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    TransactionReceipt receipt{
        before,
        state_digest(*root_),
        mutations,
        created_loans_,
    };
    posting_undo_.clear();
    reserve_undo_.clear();
    reserve_stock_undo_.reset();
    loan_undo_.clear();
    created_loans_.clear();
    ownership_undo_.clear();
    counter_undo_.clear();
    state_ = TransactionState::committed;
    release_root();
    return receipt;
}

void SettlementTransaction::rollback() noexcept {
    if (root_ == nullptr) {
        return;
    }
    for (auto item = counter_undo_.rbegin(); item != counter_undo_.rend(); ++item) {
        if (item->existed) {
            root_->named_counters.set_unchecked(
                item->stream_id,
                item->previous
            );
        } else {
            root_->named_counters.erase_unchecked(item->stream_id);
        }
    }
    for (
        auto item = ownership_undo_.rbegin();
        item != ownership_undo_.rend();
        ++item
    ) {
        root_->ownership.restore_unchecked(item->id, item->previous);
    }
    for (
        auto item = created_loans_.rbegin();
        item != created_loans_.rend();
        ++item
    ) {
        root_->loans.rollback_create_unchecked(*item);
    }
    for (auto item = loan_undo_.rbegin(); item != loan_undo_.rend(); ++item) {
        root_->loans.restore_unchecked(item->id, item->previous);
    }
    if (reserve_stock_undo_.has_value()) {
        root_->reserves.restore_stock_unchecked(*reserve_stock_undo_);
    }
    for (
        auto item = reserve_undo_.rbegin();
        item != reserve_undo_.rend();
        ++item
    ) {
        root_->reserves.restore_unchecked(item->node, item->previous);
    }
    for (
        auto item = posting_undo_.rbegin();
        item != posting_undo_.rend();
        ++item
    ) {
        root_->postings.restore_unchecked(item->id, item->previous);
    }
    posting_undo_.clear();
    reserve_undo_.clear();
    reserve_stock_undo_.reset();
    loan_undo_.clear();
    created_loans_.clear();
    ownership_undo_.clear();
    counter_undo_.clear();
}

void SettlementTransaction::release_root() noexcept {
    if (root_ != nullptr) {
        root_->transaction_active = false;
        root_ = nullptr;
    }
}

TransactionState SettlementTransaction::transaction_state() const noexcept {
    return state_;
}

std::uint64_t SettlementTransaction::next_fault_ordinal() const noexcept {
    return current_fault_ordinal_;
}

Status WorldTransaction::add(
    RootState& root,
    SettlementBatch batch,
    std::optional<std::uint64_t> fault_ordinal
) {
    if (committed_) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "world transaction is already committed"
        );
    }
    if (root.transaction_active) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "root already has an active transaction"
        );
    }
    const auto duplicate = std::find_if(
        entries_.begin(),
        entries_.end(),
        [&root](const Entry& entry) { return entry.root == &root; }
    );
    if (duplicate != entries_.end()) {
        return Status(
            ErrorCode::already_exists,
            "root is already present in the world transaction"
        );
    }
    entries_.push_back({&root, std::move(batch), fault_ordinal});
    return Status::success();
}

Result<WorldTransactionReceipt> WorldTransaction::commit() {
    if (committed_) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "world transaction is already committed"
        );
    }
    if (entries_.empty()) {
        return Status(
            ErrorCode::invalid_argument,
            "world transaction has no roots"
        );
    }

    std::vector<std::vector<std::uint8_t>> checkpoints;
    checkpoints.reserve(entries_.size());
    for (const auto& entry : entries_) {
        const auto checkpoint = save_checkpoint(*entry.root);
        if (!checkpoint.ok()) {
            return checkpoint.status();
        }
        checkpoints.push_back(*checkpoint.get_if());
    }

    WorldTransactionReceipt world_receipt;
    world_receipt.roots.reserve(entries_.size());
    for (const auto& entry : entries_) {
        SettlementTransaction transaction(
            *entry.root,
            entry.fault_ordinal
        );
        const auto appended = transaction.append(entry.batch);
        Result<TransactionReceipt> receipt =
            appended.ok()
            ? transaction.commit()
            : Result<TransactionReceipt>(appended);
        if (!receipt.ok()) {
            for (std::size_t index = 0; index < entries_.size(); ++index) {
                auto restored = load_checkpoint(checkpoints[index]);
                if (!restored.ok()) {
                    return Status(
                        ErrorCode::internal_error,
                        "world rollback checkpoint could not be restored"
                    );
                }
                *entries_[index].root = std::move(*restored.get_if());
            }
            return receipt.status();
        }
        world_receipt.roots.push_back(*receipt.get_if());
    }
    committed_ = true;
    return world_receipt;
}

}  // namespace macro_sim::core
