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

[[nodiscard]] Status validate_nonnegative_amount(
    double amount,
    const char* message
) noexcept {
    if (!std::isfinite(amount) || amount < 0.0) {
        return Status(ErrorCode::invalid_argument, message);
    }
    return Status::success();
}

[[nodiscard]] bool owner_exists(
    const RootState& state,
    OwnerId owner
) noexcept {
    switch (owner.kind()) {
        case OwnerKind::household:
            return state.households.get(HouseholdId(owner.value())) != nullptr;
        case OwnerKind::firm:
            return state.firms.get(FirmId(owner.value())) != nullptr;
        case OwnerKind::bank:
            return state.banks.get(BankId(owner.value())) != nullptr;
        case OwnerKind::treasury:
        case OwnerKind::central_bank:
        case OwnerKind::dealer:
        case OwnerKind::rounding_residual:
        case OwnerKind::institution:
            return owner.valid();
    }
    return false;
}

[[nodiscard]] double accumulation_roundoff_bound(
    double absolute_sum,
    std::size_t operation_count,
    double accounting_tolerance
) noexcept {
    // Commands are economically balanced by construction, but their deltas are
    // first accumulated by account. A large fan-out payment therefore performs
    // many same-sign additions on the source account before the compensated
    // cross-account sum below. Bound that first-stage forward error as well as
    // the final reduction. This remains a relative floating-point tolerance;
    // any material economic imbalance is still rejected.
    constexpr double kReductionGuardOperations = 64.0;
    const double operations =
        kReductionGuardOperations + static_cast<double>(operation_count);
    const double relative_error =
        operations * std::numeric_limits<double>::epsilon();
    if (relative_error >= 0.5) {
        return std::numeric_limits<double>::infinity();
    }
    const double gamma = relative_error / (1.0 - relative_error);
    return std::max(
        accounting_tolerance,
        gamma * std::max(1.0, absolute_sum)
    );
}

}  // namespace

void TransactionWorkspace::reserve(const RootState& state) {
    posting_totals_.resize(state.postings.size());
    reserve_totals_.resize(state.reserves.size());
    loan_totals_.resize(state.loans.size());
}

SettlementTransaction::SettlementTransaction(
    RootState& state,
    std::optional<std::uint64_t> fault_ordinal
) noexcept
    : fault_ordinal_(fault_ordinal) {
    acquire_root(state);
}

SettlementTransaction::SettlementTransaction(
    RootState& state,
    TransactionWorkspace& workspace,
    std::optional<std::uint64_t> fault_ordinal
) noexcept
    : workspace_(&workspace), fault_ordinal_(fault_ordinal) {
    acquire_root(state);
}

void SettlementTransaction::acquire_root(RootState& state) noexcept {
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
    root_ = &state;
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
    if (!valid.ok() || amount.value() == 0.0) {
        return valid.ok()
            ? Status(
                ErrorCode::invalid_argument,
                "loan amount must be positive"
            )
            : valid;
    }
    if (terms.maturity_tick < terms.originated_tick) {
        return Status(
            ErrorCode::invalid_argument,
            "loan maturity precedes origination"
        );
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

void SettlementTransaction::reserve_capacity() {
    if (root_ == nullptr) {
        return;
    }
    posting_undo_.reserve(workspace_->posting_deltas_.size());
    reserve_undo_.reserve(workspace_->reserve_deltas_.size());
    loan_undo_.reserve(workspace_->loan_deltas_.size());
    created_loans_.reserve(originations_.size());
    ownership_undo_.reserve(ownership_mutations_.size());
    counter_undo_.reserve(counter_increments_.size());
    root_->loans.loans_.reserve(
        root_->loans.loans_.size() + originations_.size()
    );
    root_->named_counters.counters_.reserve(
        root_->named_counters.counters_.size() + counter_increments_.size()
    );
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
    return commit_impl(true);
}

Status SettlementTransaction::commit_locally_validated() {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (!originations_.empty() || !repayments_.empty() ||
        !ownership_mutations_.empty() || !counter_increments_.empty()) {
        auto rejected = reject(Status(
            ErrorCode::invalid_transaction_state,
            "local validation only supports posting and reserve commands"
        ));
        return rejected.status();
    }
    auto result = commit_impl(false);
    return result.ok() ? Status::success() : result.status();
}

Result<TransactionReceipt> SettlementTransaction::commit_impl(
    bool audit_root
) {
    const auto collecting = require_collecting();
    if (!collecting.ok()) {
        return collecting;
    }
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    workspace_->reserve(*root_);
    const auto before = audit_root
        ? state_digest(*root_, workspace_->digest_bytes_)
        : StateDigest{};
    auto& posting_totals = workspace_->posting_totals_;
    auto& reserve_totals = workspace_->reserve_totals_;
    auto& loan_totals = workspace_->loan_totals_;
    std::fill(posting_totals.begin(), posting_totals.end(), 0.0);
    std::fill(reserve_totals.begin(), reserve_totals.end(), 0.0);
    std::fill(loan_totals.begin(), loan_totals.end(), 0.0);
    double reserve_stock_delta = 0.0;
    double new_loan_total = 0.0;
    double absolute_economic_sum = 0.0;
    double absolute_reserve_sum = 0.0;

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
            absolute_reserve_sum += 2.0 * intent.amount;
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
        absolute_reserve_sum += 2.0 * intent.amount;
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
        absolute_reserve_sum += intent.amount;
    }

    for (const auto& intent : originations_) {
        const auto* account = root_->postings.get(intent.borrower_account);
        const auto* bank = root_->banks.get(intent.lender);
        if (bank == nullptr || account == nullptr
            || !account->open || account->key.owner != intent.borrower) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "loan parties do not match canonical state"
                )
            );
        }
        if (bank->settlement_node != account->key.settlement_node) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "loan deposit is not held at the lender bank"
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
        if (loan == nullptr || !loan->active || account == nullptr
            || !account->open
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

    for (std::size_t index = 0; index < ownership_mutations_.size(); ++index) {
        const auto& intent = ownership_mutations_[index];
        const auto* lot = root_->ownership.get(intent.lot);
        if (lot == nullptr || !lot->active
            || !owner_exists(*root_, intent.owner)) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "ownership mutation references an absent party"
                )
            );
        }
        bool first_for_asset = true;
        for (std::size_t previous = 0; previous < index; ++previous) {
            const auto* previous_lot = root_->ownership.get(
                ownership_mutations_[previous].lot
            );
            if (previous_lot != nullptr
                && previous_lot->asset == lot->asset) {
                first_for_asset = false;
                break;
            }
        }
        if (!first_for_asset) {
            continue;
        }
        double share_sum = 0.0;
        double correction = 0.0;
        bool active_after = false;
        for (const auto& existing : root_->ownership.records()) {
            if (!existing.active || existing.asset != lot->asset) {
                continue;
            }
            double final_share = existing.share;
            for (
                auto mutation = ownership_mutations_.rbegin();
                mutation != ownership_mutations_.rend();
                ++mutation
            ) {
                if (mutation->lot == existing.id) {
                    final_share = mutation->share;
                    break;
                }
            }
            active_after = active_after || final_share > 0.0;
            const double next = share_sum + final_share;
            correction +=
                std::abs(share_sum) >= std::abs(final_share)
                ? (share_sum - next) + final_share
                : (final_share - next) + share_sum;
            share_sum = next;
        }
        if (active_after
            && std::abs((share_sum + correction) - 1.0)
            > root_->accounting_tolerance) {
            return reject(
                Status(
                    ErrorCode::contract_violation,
                    "ownership shares would not sum to one"
                )
            );
        }
    }

    for (std::size_t index = 0; index < counter_increments_.size(); ++index) {
        const auto& intent = counter_increments_[index];
        bool first_for_stream = true;
        for (std::size_t previous = 0; previous < index; ++previous) {
            if (counter_increments_[previous].stream_id == intent.stream_id) {
                first_for_stream = false;
                break;
            }
        }
        if (!first_for_stream) {
            continue;
        }
        auto final_value = root_->named_counters.value(intent.stream_id);
        for (const auto& candidate : counter_increments_) {
            if (candidate.stream_id != intent.stream_id) {
                continue;
            }
            if (candidate.amount
                > std::numeric_limits<std::uint64_t>::max() - final_value) {
                return reject(
                    Status(
                        ErrorCode::out_of_range,
                        "named counter overflow"
                    )
                );
            }
            final_value += candidate.amount;
        }
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
    const double allowed_residual = accumulation_roundoff_bound(
        absolute_economic_sum,
        transfers_.size() * 2U + originations_.size() + repayments_.size(),
        root_->accounting_tolerance
    );
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

    const double reserve_residual_bound = accumulation_roundoff_bound(
        absolute_reserve_sum + std::abs(reserve_stock_delta),
        transfers_.size() * 2U + reserve_transfers_.size() * 2U +
            reserve_issues_.size(),
        root_->accounting_tolerance
    );
    if (std::abs(neumaier_sum(reserve_totals) - reserve_stock_delta)
        > reserve_residual_bound) {
        return reject(
            Status(
                ErrorCode::unbalanced_transaction,
                "reserve transaction is not balanced"
            )
        );
    }
    if (!std::isfinite(
            root_->reserves.reserve_stock().value() + reserve_stock_delta
        )) {
        return reject(
            Status(ErrorCode::out_of_range, "reserve stock overflow")
        );
    }

    auto& posting_deltas = workspace_->posting_deltas_;
    auto& reserve_deltas = workspace_->reserve_deltas_;
    auto& loan_deltas = workspace_->loan_deltas_;
    posting_deltas.clear();
    reserve_deltas.clear();
    loan_deltas.clear();
    posting_deltas.reserve(
        transfers_.size() * 2U + originations_.size() + repayments_.size() + 1U
    );
    reserve_deltas.reserve(
        transfers_.size() * 2U + reserve_transfers_.size() * 2U +
        reserve_issues_.size()
    );
    loan_deltas.reserve(repayments_.size());
    for (std::size_t index = 0; index < posting_totals.size(); ++index) {
        if (posting_totals[index] != 0.0) {
            posting_deltas.push_back(
                {
                    AccountId(static_cast<std::uint64_t>(index) + 1),
                    posting_totals[index]
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
                    reserve_totals[index]
                }
            );
        }
    }
    for (std::size_t index = 0; index < loan_totals.size(); ++index) {
        if (loan_totals[index] != 0.0) {
            loan_deltas.push_back(
                {
                    LoanId(static_cast<std::uint64_t>(index) + 1),
                    loan_totals[index]
                }
            );
        }
    }

    reserve_capacity();
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    std::uint64_t mutations = 0;
    for (const auto& delta : posting_deltas) {
        posting_undo_.push_back(
            {
                delta.first,
                root_->postings.apply_delta_unchecked(
                    delta.first,
                    delta.second
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
                delta.first,
                root_->reserves.apply_delta_unchecked(
                    delta.first,
                    delta.second
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
                delta.first,
                root_->loans.apply_principal_delta_unchecked(
                    delta.first,
                    delta.second
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
    if (audit_root) {
        const auto invariants = run_invariants(*root_);
        if (!invariants.ok()) {
            return reject(invariants.status);
        }
    }
    if (inject_fault()) {
        return reject(
            Status(ErrorCode::internal_error, "injected transaction fault")
        );
    }

    TransactionReceipt receipt{
        before,
        audit_root
            ? state_digest(*root_, workspace_->digest_bytes_)
            : StateDigest{},
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
