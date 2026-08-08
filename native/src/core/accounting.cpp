#include "macro_sim/core/accounting.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace macro_sim::core {
namespace {

constexpr std::size_t kMissingAccountRow = std::numeric_limits<std::size_t>::max();
constexpr std::size_t kDeletedAccountSlot =
    std::numeric_limits<std::size_t>::max();

[[nodiscard]] constexpr bool valid_loan_purpose(LoanPurpose purpose) noexcept {
    switch (purpose) {
    case LoanPurpose::general:
    case LoanPurpose::mortgage:
    case LoanPurpose::margin:
        return true;
    }
    return false;
}

struct RoundedAdd final {
    double value{0.0};
    double error{0.0};
};

class NeumaierAccumulator final {
  public:
    void add(double value) noexcept {
        const double next = sum_ + value;
        if (std::abs(sum_) >= std::abs(value)) {
            correction_ += (sum_ - next) + value;
        } else {
            correction_ += (value - next) + sum_;
        }
        sum_ = next;
    }

    [[nodiscard]] double value() const noexcept { return sum_ + correction_; }

  private:
    double sum_{0.0};
    double correction_{0.0};
};

[[nodiscard]] RoundedAdd add_with_roundoff(double old, double delta) noexcept {
    const double value = old + delta;
    if (!std::isfinite(value)) {
        return {value, 0.0};
    }
    const double correction = std::fma(-1.0, value, old) + delta;
    return {value, -correction};
}

template <typename Record, typename Id>
[[nodiscard]] Record *sequential_get(std::vector<Record> &records, Id id) noexcept {
    if (!id.valid() || id.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(id.value() - 1);
    if (index >= records.size()) {
        return nullptr;
    }
    return &records[index];
}

template <typename Record, typename Id>
[[nodiscard]] const Record *sequential_get(const std::vector<Record> &records,
                                           Id id) noexcept {
    if (!id.valid() || id.value() == 0) {
        return nullptr;
    }
    const auto index = static_cast<std::size_t>(id.value() - 1);
    if (index >= records.size()) {
        return nullptr;
    }
    return &records[index];
}

template <typename Value>
void compact_excess(std::vector<Value> &values) {
    constexpr std::size_t kMaximumSlack = 4096U;
    const auto size = values.size();
    const auto proportional =
        size > std::numeric_limits<std::size_t>::max() / 4U
            ? std::numeric_limits<std::size_t>::max()
            : size * 4U;
    const auto additive =
        size > std::numeric_limits<std::size_t>::max() - kMaximumSlack
            ? std::numeric_limits<std::size_t>::max()
            : size + kMaximumSlack;
    if (values.capacity() <= std::max(proportional, additive)) {
        return;
    }
    auto tight = values;
    values.swap(tight);
}

} // namespace

double neumaier_sum(std::span<const double> values) noexcept {
    NeumaierAccumulator accumulator;
    for (const double value : values) {
        accumulator.add(value);
    }
    return accumulator.value();
}

Result<AccountId> PostingBook::create_account(AccountKey key, Money opening_balance,
                                              bool allow_negative) {
    const double opening = opening_balance.value();
    if (!key.economy.valid() || !key.currency.valid() || !key.owner.valid() ||
        !key.settlement_node.valid()) {
        return Status(ErrorCode::invalid_argument, "invalid account key");
    }
    if (!std::isfinite(opening) || (!allow_negative && opening < 0.0)) {
        return Status(ErrorCode::invalid_argument,
                      "opening balance must be finite and permitted");
    }
    if (find_account_row(key) != kMissingAccountRow) {
        return Status(ErrorCode::already_exists, "account key already exists");
    }
    if (accounts_.size() >=
        static_cast<std::size_t>(AccountId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "account ID space exhausted");
    }
    const auto id =
        AccountId(static_cast<AccountId::rep_type>(accounts_.size() + 1U));
    ensure_account_slot_capacity(accounts_.size() + 1);
    accounts_.push_back(
        AccountRecord{id, key, opening_balance, 0.0, allow_negative, true});
    insert_account_row(accounts_.size() - 1);
    return id;
}

Status PostingBook::close_account(AccountId id) {
    auto *account = get(id);
    if (account == nullptr || !account->open) {
        return Status(ErrorCode::not_found, "account is not open");
    }
    if (account->balance.value() != 0.0) {
        return Status(ErrorCode::contract_violation,
                      "nonzero account cannot be closed");
    }
    erase_account_row(account->key);
    account->open = false;
    return Status::success();
}

Result<AccountId> PostingBook::find(AccountKey key) const noexcept {
    const auto row = find_account_row(key);
    if (row == kMissingAccountRow) {
        return Status(ErrorCode::not_found, "account key is absent");
    }
    return accounts_[row].id;
}

Result<SettlementNodeId> PostingBook::settlement_node(AccountId id) const noexcept {
    const auto *account = get(id);
    if (account == nullptr || !account->open) {
        return Status(ErrorCode::not_found, "account is not open");
    }
    return account->key.settlement_node;
}

bool PostingBook::contains(AccountId id) const noexcept {
    const auto *account = get(id);
    return account != nullptr && account->open;
}

AccountRecord *PostingBook::get(AccountId id) noexcept {
    return sequential_get(accounts_, id);
}

const AccountRecord *PostingBook::get(AccountId id) const noexcept {
    return sequential_get(accounts_, id);
}

Result<Money> PostingBook::balance(AccountId id) const noexcept {
    const auto *account = get(id);
    if (account == nullptr || !account->open) {
        return Status(ErrorCode::not_found, "account is not open");
    }
    return account->balance;
}

Money PostingBook::total_deposits() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &account : accounts_) {
        if (account.open) {
            accumulator.add(account.balance.value());
        }
    }
    return Money(accumulator.value());
}

double PostingBook::total_roundoff_drift() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &account : accounts_) {
        accumulator.add(account.roundoff_drift);
    }
    return accumulator.value();
}

std::size_t PostingBook::size() const noexcept { return accounts_.size(); }

std::vector<AccountRecord> &PostingBook::records() noexcept { return accounts_; }

const std::vector<AccountRecord> &PostingBook::records() const noexcept {
    return accounts_;
}

void PostingBook::compact_excess_capacity() {
    compact_excess(accounts_);
    compact_excess(account_slots_);
}

std::size_t PostingBook::account_hash(AccountKey key) noexcept {
    auto mix = [](std::uint64_t value) {
        value += 0x9e3779b97f4a7c15ULL;
        value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31U);
    };
    std::uint64_t hash = mix(static_cast<std::uint64_t>(key.kind));
    const auto combine = [&hash, &mix](std::uint64_t value) {
        hash ^= mix(value + hash + 0x9e3779b97f4a7c15ULL);
    };
    combine(key.economy.value());
    combine(static_cast<std::uint64_t>(key.owner.kind()));
    combine(key.owner.value());
    combine(key.currency.value());
    combine(key.settlement_node.value());
    return static_cast<std::size_t>(hash);
}

std::size_t PostingBook::find_account_row(AccountKey key) const noexcept {
    if (account_slots_.empty()) {
        return kMissingAccountRow;
    }
    const auto mask = account_slots_.size() - 1;
    auto slot = account_hash(key) & mask;
    while (account_slots_[slot] != 0) {
        if (account_slots_[slot] != kDeletedAccountSlot) {
            const auto row = account_slots_[slot] - 1;
            const auto &account = accounts_[row];
            if (account.open && account.key == key) {
                return row;
            }
        }
        slot = (slot + 1) & mask;
    }
    return kMissingAccountRow;
}

void PostingBook::ensure_account_slot_capacity(std::size_t required_rows) {
    std::size_t capacity = account_slots_.empty() ? 8 : account_slots_.size();
    while (required_rows > capacity / 2) {
        capacity *= 2;
    }
    if (capacity != account_slots_.size()) {
        account_slots_.assign(capacity, 0);
        for (std::size_t row = 0; row < accounts_.size(); ++row) {
            if (accounts_[row].open) {
                insert_account_row(row);
            }
        }
    }
}

void PostingBook::rebuild_account_slots() {
    account_slots_.clear();
    ensure_account_slot_capacity(accounts_.size());
}

void PostingBook::insert_account_row(std::size_t row) noexcept {
    const auto mask = account_slots_.size() - 1;
    auto slot = account_hash(accounts_[row].key) & mask;
    auto deleted = kMissingAccountRow;
    while (account_slots_[slot] != 0) {
        if (account_slots_[slot] == kDeletedAccountSlot &&
            deleted == kMissingAccountRow) {
            deleted = slot;
        }
        slot = (slot + 1) & mask;
    }
    account_slots_[deleted == kMissingAccountRow ? slot : deleted] = row + 1;
}

void PostingBook::erase_account_row(AccountKey key) noexcept {
    if (account_slots_.empty()) {
        return;
    }
    const auto mask = account_slots_.size() - 1;
    auto slot = account_hash(key) & mask;
    while (account_slots_[slot] != 0) {
        if (account_slots_[slot] != kDeletedAccountSlot) {
            const auto row = account_slots_[slot] - 1;
            if (accounts_[row].open && accounts_[row].key == key) {
                account_slots_[slot] = kDeletedAccountSlot;
                return;
            }
        }
        slot = (slot + 1) & mask;
    }
}

Status PostingBook::validate_finite() const noexcept {
    for (const auto &account : accounts_) {
        if (!std::isfinite(account.balance.value()) ||
            !std::isfinite(account.roundoff_drift)) {
            return Status(ErrorCode::invariant_violation, "non-finite account");
        }
    }
    return Status::success();
}

Status PostingBook::validate_nonnegative(double tolerance) const noexcept {
    for (const auto &account : accounts_) {
        if (account.open && !account.allow_negative &&
            account.balance.value() < -tolerance) {
            return Status(ErrorCode::insufficient_funds,
                          "account balance is below the allowed tolerance");
        }
    }
    return Status::success();
}

PostingBook::MutationResult PostingBook::apply_delta_unchecked(AccountId id,
                                                               double delta) noexcept {
    auto &account = accounts_[static_cast<std::size_t>(id.value() - 1)];
    const MutationResult previous{
        account.balance.value(),
        account.roundoff_drift,
    };
    const auto addition = add_with_roundoff(previous.old_balance, delta);
    account.balance = Money(addition.value);
    account.roundoff_drift += addition.error;
    return previous;
}

void PostingBook::restore_unchecked(AccountId id,
                                    const MutationResult &previous) noexcept {
    auto &account = accounts_[static_cast<std::size_t>(id.value() - 1)];
    account.balance = Money(previous.old_balance);
    account.roundoff_drift = previous.old_roundoff_drift;
}

Result<SettlementNodeId> ReserveBook::create_position(BankId bank,
                                                      Money opening_balance) {
    if (!bank.valid() || !std::isfinite(opening_balance.value())) {
        return Status(ErrorCode::invalid_argument,
                      "reserve position requires a valid bank and finite balance");
    }
    if (positions_.size() >=
        static_cast<std::size_t>(SettlementNodeId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "settlement node ID space exhausted");
    }
    const auto node = SettlementNodeId(
        static_cast<SettlementNodeId::rep_type>(positions_.size() + 1U));
    positions_.push_back(ReserveRecord{node, bank, opening_balance, 0.0});
    static_cast<void>(apply_stock_delta_unchecked(opening_balance.value()));
    return node;
}

bool ReserveBook::contains(SettlementNodeId node) const noexcept {
    return get(node) != nullptr;
}

ReserveRecord *ReserveBook::get(SettlementNodeId node) noexcept {
    return sequential_get(positions_, node);
}

const ReserveRecord *ReserveBook::get(SettlementNodeId node) const noexcept {
    return sequential_get(positions_, node);
}

Result<Money> ReserveBook::balance(SettlementNodeId node) const noexcept {
    const auto *position = get(node);
    if (position == nullptr) {
        return Status(ErrorCode::not_found, "reserve position is absent");
    }
    return position->balance;
}

Money ReserveBook::total_reserves() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &position : positions_) {
        accumulator.add(position.balance.value());
    }
    return Money(accumulator.value());
}

Money ReserveBook::reserve_stock() const noexcept { return reserve_stock_; }

double ReserveBook::reserve_stock_roundoff_drift() const noexcept {
    return reserve_stock_roundoff_drift_;
}

double ReserveBook::total_roundoff_drift() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &position : positions_) {
        accumulator.add(position.roundoff_drift);
    }
    return accumulator.value();
}

std::size_t ReserveBook::size() const noexcept { return positions_.size(); }

std::vector<ReserveRecord> &ReserveBook::records() noexcept { return positions_; }

const std::vector<ReserveRecord> &ReserveBook::records() const noexcept {
    return positions_;
}

void ReserveBook::compact_excess_capacity() { compact_excess(positions_); }

Status ReserveBook::validate_finite() const noexcept {
    for (const auto &position : positions_) {
        if (!std::isfinite(position.balance.value()) ||
            !std::isfinite(position.roundoff_drift)) {
            return Status(ErrorCode::invariant_violation,
                          "non-finite reserve position");
        }
    }
    return Status::success();
}

void ReserveBook::commit_projected_stock(Money stock) noexcept {
    reserve_stock_ = stock;
}

ReserveBook::MutationResult ReserveBook::apply_delta_unchecked(SettlementNodeId node,
                                                               double delta) noexcept {
    auto &position = positions_[static_cast<std::size_t>(node.value() - 1)];
    const MutationResult previous{
        position.balance.value(),
        position.roundoff_drift,
    };
    const auto addition = add_with_roundoff(previous.old_balance, delta);
    position.balance = Money(addition.value);
    position.roundoff_drift += addition.error;
    return previous;
}

void ReserveBook::restore_unchecked(SettlementNodeId node,
                                    const MutationResult &previous) noexcept {
    auto &position = positions_[static_cast<std::size_t>(node.value() - 1)];
    position.balance = Money(previous.old_balance);
    position.roundoff_drift = previous.old_roundoff_drift;
}

ReserveBook::MutationResult
ReserveBook::apply_stock_delta_unchecked(double delta) noexcept {
    const MutationResult previous{
        reserve_stock_.value(),
        reserve_stock_roundoff_drift_,
    };
    const auto addition = add_with_roundoff(previous.old_balance, delta);
    reserve_stock_ = Money(addition.value);
    reserve_stock_roundoff_drift_ += addition.error;
    return previous;
}

void ReserveBook::restore_stock_unchecked(const MutationResult &previous) noexcept {
    reserve_stock_ = Money(previous.old_balance);
    reserve_stock_roundoff_drift_ = previous.old_roundoff_drift;
}

bool LoanBook::contains(LoanId id) const noexcept { return get(id) != nullptr; }

LoanRecord *LoanBook::get(LoanId id) noexcept { return sequential_get(loans_, id); }

const LoanRecord *LoanBook::get(LoanId id) const noexcept {
    return sequential_get(loans_, id);
}

Money LoanBook::total_principal() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &loan : loans_) {
        if (loan.active) {
            accumulator.add(loan.principal.value());
        }
    }
    return Money(accumulator.value());
}

double LoanBook::total_roundoff_drift() const noexcept {
    NeumaierAccumulator accumulator;
    for (const auto &loan : loans_) {
        accumulator.add(loan.roundoff_drift);
    }
    return accumulator.value();
}

std::size_t LoanBook::size() const noexcept { return loans_.size(); }

const std::vector<LoanRecord> &LoanBook::records() const noexcept { return loans_; }

Status LoanBook::validate_finite() const noexcept {
    for (const auto &loan : loans_) {
        if (!std::isfinite(loan.principal.value()) ||
            !std::isfinite(loan.roundoff_drift) ||
            !std::isfinite(loan.interest_arrears) ||
            loan.principal.value() < 0.0 || loan.interest_arrears < 0.0 ||
            !valid_loan_purpose(loan.purpose)) {
            return Status(ErrorCode::invariant_violation, "invalid loan");
        }
    }
    return Status::success();
}

void LoanBook::replace_records(std::vector<LoanRecord> &projection) noexcept {
    loans_.swap(projection);
}

void LoanBook::compact_excess_capacity() { compact_excess(loans_); }

LoanBook::CreateResult LoanBook::create_unchecked(BankId lender, OwnerId borrower,
                                                  AccountId borrower_account,
                                                  Money principal, LoanTerms terms) {
    const auto id =
        LoanId(static_cast<LoanId::rep_type>(loans_.size() + 1U));
    loans_.push_back(LoanRecord{
        id,
        lender,
        borrower,
        borrower_account,
        principal,
        0.0,
        0.0,
        terms,
        principal.value() != 0.0,
    });
    return CreateResult{id};
}

void LoanBook::rollback_create_unchecked(LoanId id) noexcept {
    if (!loans_.empty() && loans_.back().id == id) {
        loans_.pop_back();
    }
}

LoanBook::MutationResult
LoanBook::apply_principal_delta_unchecked(LoanId id, double delta) noexcept {
    auto &loan = loans_[static_cast<std::size_t>(id.value() - 1)];
    const MutationResult previous{
        loan.principal.value(),
        loan.roundoff_drift,
        loan.active,
    };
    const auto addition = add_with_roundoff(previous.old_principal, delta);
    loan.principal = Money(addition.value);
    loan.roundoff_drift += addition.error;
    loan.active = addition.value != 0.0;
    return previous;
}

void LoanBook::restore_unchecked(LoanId id, const MutationResult &previous) noexcept {
    auto &loan = loans_[static_cast<std::size_t>(id.value() - 1)];
    loan.principal = Money(previous.old_principal);
    loan.roundoff_drift = previous.old_roundoff_drift;
    loan.active = previous.old_active;
}

Result<OwnershipLotId> OwnershipBook::create_lot(AssetKey asset, OwnerId owner,
                                                 double share) {
    if (!asset.economy.valid() || asset.value == 0 || !owner.valid() ||
        !std::isfinite(share) || share <= 0.0 || share > 1.0) {
        return Status(ErrorCode::invalid_argument, "invalid ownership lot");
    }
    if (lots_.size() >=
        static_cast<std::size_t>(OwnershipLotId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "ownership lot ID space exhausted");
    }
    const auto id = OwnershipLotId(
        static_cast<OwnershipLotId::rep_type>(lots_.size() + 1U));
    lots_.push_back(OwnershipLot{id, asset, owner, share, true});
    return id;
}

bool OwnershipBook::contains(OwnershipLotId id) const noexcept {
    const auto *lot = get(id);
    return lot != nullptr && lot->active;
}

OwnershipLot *OwnershipBook::get(OwnershipLotId id) noexcept {
    return sequential_get(lots_, id);
}

const OwnershipLot *OwnershipBook::get(OwnershipLotId id) const noexcept {
    return sequential_get(lots_, id);
}

std::size_t OwnershipBook::size() const noexcept { return lots_.size(); }

const std::vector<OwnershipLot> &OwnershipBook::records() const noexcept {
    return lots_;
}

std::size_t OwnershipBook::retire_asset(AssetKey asset) noexcept {
    std::size_t retired = 0;
    for (auto &lot : lots_) {
        if (!lot.active || lot.asset != asset) {
            continue;
        }
        lot.share = 0.0;
        lot.active = false;
        ++retired;
    }
    return retired;
}

Status OwnershipBook::rekey_owner(OwnerId source, OwnerId destination) noexcept {
    if (!source.valid() || !destination.valid() || source == destination) {
        return Status(ErrorCode::invalid_argument,
                      "ownership rekey subjects are invalid");
    }
    for (auto &lot : lots_) {
        if (!lot.active || lot.owner != source) {
            continue;
        }
        const auto existing = std::find_if(
            lots_.begin(), lots_.end(), [&](const OwnershipLot &candidate) {
                return candidate.active && candidate.owner == destination &&
                       candidate.asset == lot.asset;
            });
        if (existing == lots_.end()) {
            lot.owner = destination;
            continue;
        }
        existing->share += lot.share;
        lot.share = 0.0;
        lot.active = false;
    }
    return Status::success();
}

Status OwnershipBook::validate_shares(double tolerance) const {
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        const auto &candidate = lots_[index];
        if (!candidate.active) {
            continue;
        }
        bool first_for_asset = true;
        for (std::size_t previous = 0; previous < index; ++previous) {
            if (lots_[previous].active && lots_[previous].asset == candidate.asset) {
                first_for_asset = false;
                break;
            }
        }
        if (!first_for_asset) {
            continue;
        }
        NeumaierAccumulator shares;
        for (const auto &lot : lots_) {
            if (lot.active && lot.asset == candidate.asset) {
                if (!std::isfinite(lot.share) || lot.share <= 0.0) {
                    return Status(ErrorCode::invariant_violation,
                                  "invalid ownership share");
                }
                shares.add(lot.share);
            }
        }
        if (std::abs(shares.value() - 1.0) > tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "ownership shares do not sum to one");
        }
    }
    return Status::success();
}

void OwnershipBook::compact_excess_capacity() { compact_excess(lots_); }

OwnershipBook::MutationResult OwnershipBook::mutate_unchecked(OwnershipLotId id,
                                                              OwnerId owner,
                                                              double share) noexcept {
    auto &lot = lots_[static_cast<std::size_t>(id.value() - 1)];
    const MutationResult previous{lot.owner, lot.share, lot.active};
    lot.owner = owner;
    lot.share = share;
    lot.active = share != 0.0;
    return previous;
}

void OwnershipBook::restore_unchecked(OwnershipLotId id,
                                      const MutationResult &previous) noexcept {
    auto &lot = lots_[static_cast<std::size_t>(id.value() - 1)];
    lot.owner = previous.old_owner;
    lot.share = previous.old_share;
    lot.active = previous.old_active;
}

Status NamedCounterBook::declare(std::uint64_t stream_id) {
    if (stream_id == 0) {
        return Status(ErrorCode::invalid_argument, "counter stream ID must be nonzero");
    }
    const auto found = std::lower_bound(
        counters_.begin(), counters_.end(), stream_id,
        [](const auto &item, std::uint64_t id) { return item.first < id; });
    if (found != counters_.end() && found->first == stream_id) {
        return Status(ErrorCode::already_exists, "counter stream is already declared");
    }
    counters_.insert(found, {stream_id, 0});
    return Status::success();
}

std::uint64_t NamedCounterBook::value(std::uint64_t stream_id) const noexcept {
    const auto found = std::lower_bound(
        counters_.begin(), counters_.end(), stream_id,
        [](const auto &item, std::uint64_t id) { return item.first < id; });
    return found != counters_.end() && found->first == stream_id ? found->second : 0;
}

bool NamedCounterBook::contains(std::uint64_t stream_id) const noexcept {
    const auto found = std::lower_bound(
        counters_.begin(), counters_.end(), stream_id,
        [](const auto &item, std::uint64_t id) { return item.first < id; });
    return found != counters_.end() && found->first == stream_id;
}

Result<std::uint64_t> NamedCounterBook::increment(std::uint64_t stream_id) {
    if (stream_id == 0) {
        return Status(ErrorCode::invalid_argument, "counter stream ID must be nonzero");
    }
    const auto previous = value(stream_id);
    if (previous == std::numeric_limits<std::uint64_t>::max()) {
        return Status(ErrorCode::out_of_range, "named counter overflow");
    }
    set_unchecked(stream_id, previous + 1);
    return previous;
}

const std::vector<std::pair<std::uint64_t, std::uint64_t>> &
NamedCounterBook::records() const noexcept {
    return counters_;
}

void NamedCounterBook::compact_excess_capacity() {
    compact_excess(counters_);
}

void NamedCounterBook::set_unchecked(std::uint64_t stream_id, std::uint64_t value) {
    const auto found = std::lower_bound(
        counters_.begin(), counters_.end(), stream_id,
        [](const auto &item, std::uint64_t id) { return item.first < id; });
    if (found != counters_.end() && found->first == stream_id) {
        found->second = value;
    } else {
        counters_.insert(found, {stream_id, value});
    }
}

void NamedCounterBook::erase_unchecked(std::uint64_t stream_id) noexcept {
    const auto found = std::lower_bound(
        counters_.begin(), counters_.end(), stream_id,
        [](const auto &item, std::uint64_t id) { return item.first < id; });
    if (found != counters_.end() && found->first == stream_id) {
        counters_.erase(found);
    }
}

} // namespace macro_sim::core
