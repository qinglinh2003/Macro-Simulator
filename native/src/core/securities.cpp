#include "macro_sim/core/securities.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <tuple>
#include <utility>

namespace macro_sim::core {
namespace {

constexpr double kMinimumUnits = 1.0e-12;

[[nodiscard]] bool finite_nonnegative(double value) noexcept {
    return std::isfinite(value) && value >= 0.0;
}

template <typename Record, typename Id>
[[nodiscard]] Record* sequential_get(
    std::vector<Record>& records,
    Id id
) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > records.size()) {
        return nullptr;
    }
    auto& record = records[static_cast<std::size_t>(id.value() - 1)];
    return record.id == id ? &record : nullptr;
}

template <typename Record, typename Id>
[[nodiscard]] const Record* sequential_get(
    const std::vector<Record>& records,
    Id id
) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > records.size()) {
        return nullptr;
    }
    const auto& record = records[static_cast<std::size_t>(id.value() - 1)];
    return record.id == id ? &record : nullptr;
}

template <typename Entry, typename Key, typename Values, typename Projection>
[[nodiscard]] std::span<const typename Values::value_type> indexed_values(
    const std::vector<Entry>& entries,
    const Values& values,
    const Key& key,
    Projection projection
) noexcept {
    const auto found = std::lower_bound(
        entries.begin(),
        entries.end(),
        key,
        [&projection](const Entry& entry, const Key& candidate) {
            return projection(entry) < candidate;
        }
    );
    if (found == entries.end() || projection(*found) != key) {
        return {};
    }
    return std::span<const typename Values::value_type>(
        values.data() + found->offset,
        found->count
    );
}

template <typename Key, typename Value, typename Entry>
void build_flat_index(
    std::vector<std::pair<Key, Value>> rows,
    std::vector<Entry>& entries,
    std::vector<Value>& values
) {
    std::stable_sort(
        rows.begin(),
        rows.end(),
        [](const auto& left, const auto& right) {
            return left.first < right.first;
        }
    );
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto& [key, value] : rows) {
        if (entries.empty()
            || !(entries.back().holder == key)) {
            entries.push_back(
                {
                    key,
                    static_cast<std::uint32_t>(values.size()),
                    0,
                }
            );
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

void build_contract_index(
    std::vector<std::pair<SecurityId, SecurityLotId>> rows,
    std::vector<ContractLotIndexEntry>& entries,
    std::vector<SecurityLotId>& values
) {
    std::stable_sort(
        rows.begin(),
        rows.end(),
        [](const auto& left, const auto& right) {
            return left.first < right.first;
        }
    );
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto& [key, value] : rows) {
        if (entries.empty() || entries.back().security != key) {
            entries.push_back(
                {
                    key,
                    static_cast<std::uint32_t>(values.size()),
                    0,
                }
            );
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

void build_issuer_index(
    std::vector<std::pair<OwnerId, SecurityId>> rows,
    std::vector<IssuerSecurityIndexEntry>& entries,
    std::vector<SecurityId>& values
) {
    std::stable_sort(
        rows.begin(),
        rows.end(),
        [](const auto& left, const auto& right) {
            return left.first < right.first;
        }
    );
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto& [key, value] : rows) {
        if (entries.empty() || entries.back().issuer != key) {
            entries.push_back(
                {
                    key,
                    static_cast<std::uint32_t>(values.size()),
                    0,
                }
            );
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

void build_maturity_index(
    std::vector<std::pair<Tick, BondId>> rows,
    std::vector<MaturityIndexEntry>& entries,
    std::vector<BondId>& values
) {
    std::stable_sort(
        rows.begin(),
        rows.end(),
        [](const auto& left, const auto& right) {
            return left.first < right.first;
        }
    );
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto& [key, value] : rows) {
        if (entries.empty() || entries.back().maturity != key) {
            entries.push_back(
                {
                    key,
                    static_cast<std::uint32_t>(values.size()),
                    0,
                }
            );
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

[[nodiscard]] double scaled_tolerance(
    double tolerance,
    double expected
) noexcept {
    return std::max(tolerance, tolerance * std::max(1.0, std::abs(expected)));
}

}  // namespace

Result<SecurityLotId> SecurityBook::create_lot(
    SecurityId security,
    OwnerId holder,
    double units,
    Money cost_basis
) {
    if (!validate_security(security).ok() || !holder.valid()
        || !finite_nonnegative(units) || units <= kMinimumUnits
        || !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid security lot");
    }
    const auto id = SecurityLotId(
        static_cast<std::uint64_t>(lots_.size()) + 1
    );
    lots_.push_back(
        SecurityLot{id, security, holder, units, cost_basis, true}
    );
    return id;
}

Result<BondId> SecurityBook::issue_bond(
    BondContract contract,
    OwnerId holder,
    Money cost_basis
) {
    if (!contract.issuer.valid() || !contract.issuer_account.valid()
        || !contract.currency.valid()
        || contract.maturity_tick < contract.issued_tick
        || !finite_nonnegative(contract.coupon_rate.value())
        || !finite_nonnegative(contract.original_face.value())
        || contract.original_face.value() <= kMinimumUnits
        || contract.settled
        || !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid bond contract");
    }
    contract.id = BondId(static_cast<std::uint64_t>(bonds_.size()) + 1);
    contract.outstanding_face = contract.original_face;
    contract.active = true;
    bonds_.push_back(contract);
    auto lot = create_lot(
        SecurityId::bond(contract.id),
        holder,
        contract.original_face.value(),
        cost_basis
    );
    if (!lot.ok()) {
        bonds_.pop_back();
        return lot.status();
    }
    const auto indexes = mutation_complete();
    if (!indexes.ok()) {
        lots_.pop_back();
        bonds_.pop_back();
        static_cast<void>(rebuild_indexes());
        return indexes;
    }
    return contract.id;
}

Result<EquityId> SecurityBook::create_equity(
    EquityContract contract,
    std::span<const InitialSecurityHolding> holdings
) {
    if (!contract.issuer.valid() || !contract.issuer_account.valid()
        || !contract.currency.valid()
        || !finite_nonnegative(contract.outstanding_shares)
        || contract.outstanding_shares <= kMinimumUnits
        || !finite_nonnegative(contract.price.value())
        || !finite_nonnegative(contract.last_price.value())
        || !finite_nonnegative(contract.peak_price.value())
        || !finite_nonnegative(contract.fundamental.value())
        || !std::isfinite(contract.trend)
        || !std::isfinite(contract.income_signal)
        || contract.resolved || holdings.empty()) {
        return Status(ErrorCode::invalid_argument, "invalid equity contract");
    }
    double total = 0.0;
    for (const auto& holding : holdings) {
        if (!holding.holder.valid()
            || !finite_nonnegative(holding.units)
            || holding.units <= kMinimumUnits
            || !finite_nonnegative(holding.cost_basis.value())) {
            return Status(
                ErrorCode::invalid_argument,
                "invalid equity holding"
            );
        }
        total += holding.units;
    }
    if (!std::isfinite(total)
        || std::abs(total - contract.outstanding_shares)
            > scaled_tolerance(1.0e-10, contract.outstanding_shares)) {
        return Status(
            ErrorCode::contract_violation,
            "equity holdings do not equal outstanding shares"
        );
    }
    contract.id = EquityId(
        static_cast<std::uint64_t>(equities_.size()) + 1
    );
    contract.active = true;
    equities_.push_back(contract);
    const auto first_lot = lots_.size();
    for (const auto& holding : holdings) {
        auto lot = create_lot(
            SecurityId::equity(contract.id),
            holding.holder,
            holding.units,
            holding.cost_basis
        );
        if (!lot.ok()) {
            lots_.resize(first_lot);
            equities_.pop_back();
            return lot.status();
        }
    }
    const auto indexes = mutation_complete();
    if (!indexes.ok()) {
        lots_.resize(first_lot);
        equities_.pop_back();
        static_cast<void>(rebuild_indexes());
        return indexes;
    }
    return contract.id;
}

Status SecurityBook::transfer_units(
    SecurityId security,
    OwnerId source,
    OwnerId destination,
    double units,
    Money destination_cost_basis
) {
    if (!validate_security(security).ok() || !source.valid()
        || !destination.valid() || source == destination
        || !std::isfinite(units) || units <= kMinimumUnits
        || !finite_nonnegative(destination_cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid security transfer");
    }
    const double held = units_held(security, source);
    if (units > held + scaled_tolerance(1.0e-10, held)) {
        return Status(
            ErrorCode::insufficient_funds,
            "security transfer exceeds holdings"
        );
    }

    double remaining = std::min(units, held);
    double removed_cost = 0.0;
    for (auto& lot : lots_) {
        if (!lot.active || lot.security != security || lot.holder != source
            || remaining <= kMinimumUnits) {
            continue;
        }
        const double take = std::min(remaining, lot.units);
        const double fraction = take / lot.units;
        removed_cost += lot.cost_basis.value() * fraction;
        lot.units -= take;
        lot.cost_basis = Money(
            std::max(0.0, lot.cost_basis.value() * (1.0 - fraction))
        );
        remaining -= take;
        if (lot.units <= kMinimumUnits) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    }
    if (remaining > scaled_tolerance(1.0e-10, units)) {
        return Status(
            ErrorCode::invariant_violation,
            "security source index is inconsistent"
        );
    }

    SecurityLot* destination_lot = nullptr;
    for (auto& lot : lots_) {
        if (lot.active && lot.security == security
            && lot.holder == destination) {
            destination_lot = &lot;
            break;
        }
    }
    const double assigned_cost =
        destination_cost_basis.value() > 0.0
        ? destination_cost_basis.value()
        : removed_cost;
    if (destination_lot == nullptr) {
        auto created = create_lot(
            security,
            destination,
            units,
            Money(assigned_cost)
        );
        if (!created.ok()) {
            return created.status();
        }
    } else {
        destination_lot->units += units;
        destination_lot->cost_basis = Money(
            destination_lot->cost_basis.value() + assigned_cost
        );
    }
    return mutation_complete();
}

Status SecurityBook::issue_equity_units(
    EquityId equity,
    OwnerId destination,
    double units,
    Money cost_basis
) {
    auto* contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved
        || !destination.valid() || !std::isfinite(units)
        || units <= kMinimumUnits
        || !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid equity issuance");
    }
    auto created = create_lot(
        SecurityId::equity(equity),
        destination,
        units,
        cost_basis
    );
    if (!created.ok()) {
        return created.status();
    }
    contract->outstanding_shares += units;
    return mutation_complete();
}

Status SecurityBook::retire_units(
    SecurityId security,
    OwnerId holder,
    double units
) {
    if (!validate_security(security).ok() || !holder.valid()
        || !std::isfinite(units) || units <= kMinimumUnits) {
        return Status(ErrorCode::invalid_argument, "invalid security retirement");
    }
    const double held = units_held(security, holder);
    if (units > held + scaled_tolerance(1.0e-10, held)) {
        return Status(
            ErrorCode::insufficient_funds,
            "security retirement exceeds holdings"
        );
    }
    double remaining = std::min(units, held);
    for (auto& lot : lots_) {
        if (!lot.active || lot.security != security || lot.holder != holder
            || remaining <= kMinimumUnits) {
            continue;
        }
        const double take = std::min(remaining, lot.units);
        const double fraction = take / lot.units;
        lot.units -= take;
        lot.cost_basis = Money(
            std::max(0.0, lot.cost_basis.value() * (1.0 - fraction))
        );
        remaining -= take;
        if (lot.units <= kMinimumUnits) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    }
    if (security.kind == SecurityKind::bond) {
        auto* contract = get(BondId(security.value));
        contract->outstanding_face = Money(
            std::max(0.0, contract->outstanding_face.value() - units)
        );
    } else {
        auto* contract = get(EquityId(security.value));
        contract->outstanding_shares =
            std::max(0.0, contract->outstanding_shares - units);
    }
    return mutation_complete();
}

Status SecurityBook::settle_bond(BondId bond) {
    auto* contract = get(bond);
    if (contract == nullptr || !contract->active || contract->settled) {
        return Status(ErrorCode::invalid_argument, "invalid bond settlement");
    }
    const auto security = SecurityId::bond(bond);
    for (auto& lot : lots_) {
        if (lot.active && lot.security == security) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    }
    contract->outstanding_face = Money(0.0);
    contract->active = false;
    contract->settled = true;
    return mutation_complete();
}

Status SecurityBook::resolve_equity(EquityId equity) {
    auto* contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved) {
        return Status(ErrorCode::invalid_argument, "invalid equity resolution");
    }
    const auto security = SecurityId::equity(equity);
    for (auto& lot : lots_) {
        if (lot.active && lot.security == security) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    }
    contract->outstanding_shares = 0.0;
    contract->price = Price(0.0);
    contract->last_price = Price(0.0);
    contract->fundamental = Price(0.0);
    contract->active = false;
    contract->resolved = true;
    return mutation_complete();
}

Status SecurityBook::update_equity_valuation(
    EquityId equity,
    Price price,
    Price last_price,
    Price peak_price,
    Price fundamental,
    double trend,
    double income_signal
) {
    auto* contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved
        || !finite_nonnegative(price.value())
        || !finite_nonnegative(last_price.value())
        || !finite_nonnegative(peak_price.value())
        || !finite_nonnegative(fundamental.value())
        || !std::isfinite(trend) || !std::isfinite(income_signal)) {
        return Status(
            ErrorCode::invalid_argument,
            "invalid equity valuation update"
        );
    }
    contract->price = price;
    contract->last_price = last_price;
    contract->peak_price = peak_price;
    contract->fundamental = fundamental;
    contract->trend = trend;
    contract->income_signal = income_signal;
    return mutation_complete();
}

Status SecurityBook::consolidate() {
    bool changed = false;
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        auto& target = lots_[index];
        if (!target.active) {
            continue;
        }
        for (std::size_t next = index + 1; next < lots_.size(); ++next) {
            auto& candidate = lots_[next];
            if (!candidate.active || candidate.security != target.security
                || candidate.holder != target.holder) {
                continue;
            }
            target.units += candidate.units;
            target.cost_basis = Money(
                target.cost_basis.value() + candidate.cost_basis.value()
            );
            candidate.units = 0.0;
            candidate.cost_basis = Money(0.0);
            candidate.active = false;
            changed = true;
        }
    }
    if (!changed) {
        return Status::success();
    }
    return mutation_complete();
}

Status SecurityBook::begin_batch() noexcept {
    if (batch_active_) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "security mutation batch is already active"
        );
    }
    batch_active_ = true;
    batch_dirty_ = false;
    return Status::success();
}

Status SecurityBook::finish_batch() {
    if (!batch_active_) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "security mutation batch is not active"
        );
    }
    batch_active_ = false;
    if (!batch_dirty_) {
        return Status::success();
    }
    batch_dirty_ = false;
    bump_version();
    return rebuild_indexes();
}

BondContract* SecurityBook::get(BondId id) noexcept {
    return sequential_get(bonds_, id);
}

const BondContract* SecurityBook::get(BondId id) const noexcept {
    return sequential_get(bonds_, id);
}

EquityContract* SecurityBook::get(EquityId id) noexcept {
    return sequential_get(equities_, id);
}

const EquityContract* SecurityBook::get(EquityId id) const noexcept {
    return sequential_get(equities_, id);
}

SecurityLot* SecurityBook::get(SecurityLotId id) noexcept {
    return sequential_get(lots_, id);
}

const SecurityLot* SecurityBook::get(SecurityLotId id) const noexcept {
    return sequential_get(lots_, id);
}

const std::vector<BondContract>& SecurityBook::bonds() const noexcept {
    return bonds_;
}

const std::vector<EquityContract>& SecurityBook::equities() const noexcept {
    return equities_;
}

const std::vector<SecurityLot>& SecurityBook::lots() const noexcept {
    return lots_;
}

std::span<const SecurityLotId> SecurityBook::lots_for_holder(
    OwnerId holder
) const noexcept {
    return indexed_values(
        holder_index_,
        holder_lots_,
        holder,
        [](const HolderSecurityIndexEntry& entry) {
            return entry.holder;
        }
    );
}

std::span<const SecurityLotId> SecurityBook::lots_for_security(
    SecurityId security
) const noexcept {
    return indexed_values(
        contract_index_,
        contract_lots_,
        security,
        [](const ContractLotIndexEntry& entry) {
            return entry.security;
        }
    );
}

std::span<const SecurityId> SecurityBook::securities_for_issuer(
    OwnerId issuer
) const noexcept {
    return indexed_values(
        issuer_index_,
        issuer_securities_,
        issuer,
        [](const IssuerSecurityIndexEntry& entry) {
            return entry.issuer;
        }
    );
}

std::span<const BondId> SecurityBook::bonds_maturing_at(
    Tick maturity
) const noexcept {
    return indexed_values(
        maturity_index_,
        maturity_bonds_,
        maturity,
        [](const MaturityIndexEntry& entry) {
            return entry.maturity;
        }
    );
}

std::span<const SecurityLotId> SecurityBook::bank_lots(
    BankId bank
) const noexcept {
    return indexed_values(
        bank_index_,
        bank_lots_,
        OwnerId::bank(bank),
        [](const HolderSecurityIndexEntry& entry) {
            return entry.holder;
        }
    );
}

double SecurityBook::units_held(
    SecurityId security,
    OwnerId holder
) const noexcept {
    double total = 0.0;
    double correction = 0.0;
    if (batch_active_) {
        for (const auto& lot : lots_) {
            if (!lot.active || lot.security != security
                || lot.holder != holder) {
                continue;
            }
            const double next = total + lot.units;
            correction +=
                std::abs(total) >= std::abs(lot.units)
                ? (total - next) + lot.units
                : (lot.units - next) + total;
            total = next;
        }
        return total + correction;
    }
    for (const auto lot_id : lots_for_holder(holder)) {
        const auto* lot = get(lot_id);
        if (lot == nullptr || !lot->active || lot->security != security) {
            continue;
        }
        const double next = total + lot->units;
        correction +=
            std::abs(total) >= std::abs(lot->units)
            ? (total - next) + lot->units
            : (lot->units - next) + total;
        total = next;
    }
    return total + correction;
}

double SecurityBook::total_units(SecurityId security) const noexcept {
    double total = 0.0;
    double correction = 0.0;
    for (const auto lot_id : lots_for_security(security)) {
        const auto* lot = get(lot_id);
        if (lot == nullptr || !lot->active) {
            continue;
        }
        const double next = total + lot->units;
        correction +=
            std::abs(total) >= std::abs(lot->units)
            ? (total - next) + lot->units
            : (lot->units - next) + total;
        total = next;
    }
    return total + correction;
}

Money SecurityBook::total_bond_face() const noexcept {
    double total = 0.0;
    double correction = 0.0;
    for (const auto& bond : bonds_) {
        if (!bond.active) {
            continue;
        }
        const double value = bond.outstanding_face.value();
        const double next = total + value;
        correction +=
            std::abs(total) >= std::abs(value)
            ? (total - next) + value
            : (value - next) + total;
        total = next;
    }
    return Money(total + correction);
}

std::uint64_t SecurityBook::version() const noexcept {
    return version_;
}

Status SecurityBook::validate(double tolerance) const {
    if (!std::isfinite(tolerance) || tolerance < 0.0) {
        return Status(ErrorCode::invalid_argument, "invalid security tolerance");
    }
    for (std::size_t index = 0; index < bonds_.size(); ++index) {
        const auto& bond = bonds_[index];
        if (bond.id.value() != index + 1 || !bond.issuer.valid()
            || !bond.issuer_account.valid() || !bond.currency.valid()
            || bond.maturity_tick < bond.issued_tick
            || !finite_nonnegative(bond.coupon_rate.value())
            || !finite_nonnegative(bond.original_face.value())
            || !finite_nonnegative(bond.outstanding_face.value())
            || (bond.active == bond.settled)
            || (bond.settled && bond.outstanding_face.value() != 0.0)
            || (bond.active
                && bond.outstanding_face.value()
                    > bond.original_face.value()
                        + scaled_tolerance(
                            tolerance,
                            bond.original_face.value()
                        ))) {
            return Status(
                ErrorCode::invariant_violation,
                "invalid bond contract"
            );
        }
    }
    for (std::size_t index = 0; index < equities_.size(); ++index) {
        const auto& equity = equities_[index];
        if (equity.id.value() != index + 1 || !equity.issuer.valid()
            || !equity.issuer_account.valid() || !equity.currency.valid()
            || !finite_nonnegative(equity.outstanding_shares)
            || !finite_nonnegative(equity.price.value())
            || !finite_nonnegative(equity.last_price.value())
            || !finite_nonnegative(equity.peak_price.value())
            || !finite_nonnegative(equity.fundamental.value())
            || !std::isfinite(equity.trend)
            || !std::isfinite(equity.income_signal)
            || (equity.active == equity.resolved)
            || (equity.resolved
                && (equity.outstanding_shares != 0.0
                    || equity.price.value() != 0.0))) {
            return Status(
                ErrorCode::invariant_violation,
                "invalid equity contract"
            );
        }
    }
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        const auto& lot = lots_[index];
        if (lot.id.value() != index + 1 || !lot.security.valid()
            || !lot.holder.valid() || !finite_nonnegative(lot.units)
            || !finite_nonnegative(lot.cost_basis.value())
            || (lot.active && lot.units <= kMinimumUnits)
            || (!lot.active
                && (lot.units != 0.0 || lot.cost_basis.value() != 0.0))
            || (lot.active && !validate_security(lot.security).ok())) {
            return Status(
                ErrorCode::invariant_violation,
                "invalid security lot"
            );
        }
    }
    for (const auto& bond : bonds_) {
        const double held = total_units(SecurityId::bond(bond.id));
        if (std::abs(held - bond.outstanding_face.value())
            > scaled_tolerance(tolerance, bond.outstanding_face.value())) {
            return Status(
                ErrorCode::invariant_violation,
                "bond face and lots differ"
            );
        }
    }
    for (const auto& equity : equities_) {
        const double held = total_units(SecurityId::equity(equity.id));
        if (std::abs(held - equity.outstanding_shares)
            > scaled_tolerance(tolerance, equity.outstanding_shares)) {
            return Status(
                ErrorCode::invariant_violation,
                "equity shares and lots differ"
            );
        }
    }
    return validate_indexes();
}

Status SecurityBook::validate_indexes() const {
    SecurityBook rebuilt;
    rebuilt.bonds_ = bonds_;
    rebuilt.equities_ = equities_;
    rebuilt.lots_ = lots_;
    rebuilt.version_ = version_;
    const auto status = rebuilt.rebuild_indexes();
    if (!status.ok()) {
        return status;
    }
    if (rebuilt.holder_index_ != holder_index_
        || rebuilt.holder_lots_ != holder_lots_
        || rebuilt.contract_index_ != contract_index_
        || rebuilt.contract_lots_ != contract_lots_
        || rebuilt.issuer_index_ != issuer_index_
        || rebuilt.issuer_securities_ != issuer_securities_
        || rebuilt.maturity_index_ != maturity_index_
        || rebuilt.maturity_bonds_ != maturity_bonds_
        || rebuilt.bank_index_ != bank_index_
        || rebuilt.bank_lots_ != bank_lots_) {
        return Status(
            ErrorCode::invariant_violation,
            "security indexes are inconsistent"
        );
    }
    return Status::success();
}

void SecurityBook::replace_records(
    std::vector<BondContract> bonds,
    std::vector<EquityContract> equities,
    std::vector<SecurityLot> lots,
    std::uint64_t version
) {
    bonds_ = std::move(bonds);
    equities_ = std::move(equities);
    lots_ = std::move(lots);
    version_ = version;
    batch_active_ = false;
    batch_dirty_ = false;
    static_cast<void>(rebuild_indexes());
}

Status SecurityBook::validate_security(SecurityId security) const noexcept {
    if (!security.valid()) {
        return Status(ErrorCode::invalid_argument, "invalid security ID");
    }
    if (security.kind == SecurityKind::bond) {
        const auto* contract = get(BondId(security.value));
        if (contract == nullptr || !contract->active || contract->settled) {
            return Status(ErrorCode::not_found, "bond is not active");
        }
    } else if (security.kind == SecurityKind::equity) {
        const auto* contract = get(EquityId(security.value));
        if (contract == nullptr || !contract->active || contract->resolved) {
            return Status(ErrorCode::not_found, "equity is not active");
        }
    } else {
        return Status(ErrorCode::invalid_argument, "unknown security kind");
    }
    return Status::success();
}

Status SecurityBook::rebuild_indexes() {
    if (lots_.size() > std::numeric_limits<std::uint32_t>::max()
        || bonds_.size() > std::numeric_limits<std::uint32_t>::max()
        || equities_.size() > std::numeric_limits<std::uint32_t>::max()) {
        return Status(ErrorCode::out_of_range, "security index is too large");
    }
    std::vector<std::pair<OwnerId, SecurityLotId>> holder_rows;
    std::vector<std::pair<OwnerId, SecurityLotId>> bank_rows;
    std::vector<std::pair<SecurityId, SecurityLotId>> contract_rows;
    std::vector<std::pair<OwnerId, SecurityId>> issuer_rows;
    std::vector<std::pair<Tick, BondId>> maturity_rows;
    holder_rows.reserve(lots_.size());
    contract_rows.reserve(lots_.size());
    bank_rows.reserve(lots_.size());
    issuer_rows.reserve(bonds_.size() + equities_.size());
    maturity_rows.reserve(bonds_.size());
    for (const auto& lot : lots_) {
        if (!lot.active) {
            continue;
        }
        holder_rows.emplace_back(lot.holder, lot.id);
        contract_rows.emplace_back(lot.security, lot.id);
        if (lot.holder.kind == OwnerKind::bank) {
            bank_rows.emplace_back(lot.holder, lot.id);
        }
    }
    for (const auto& bond : bonds_) {
        if (!bond.active) {
            continue;
        }
        issuer_rows.emplace_back(
            bond.issuer,
            SecurityId::bond(bond.id)
        );
        maturity_rows.emplace_back(bond.maturity_tick, bond.id);
    }
    for (const auto& equity : equities_) {
        if (!equity.active) {
            continue;
        }
        issuer_rows.emplace_back(
            equity.issuer,
            SecurityId::equity(equity.id)
        );
    }
    build_flat_index(
        std::move(holder_rows),
        holder_index_,
        holder_lots_
    );
    build_flat_index(
        std::move(bank_rows),
        bank_index_,
        bank_lots_
    );
    build_contract_index(
        std::move(contract_rows),
        contract_index_,
        contract_lots_
    );
    build_issuer_index(
        std::move(issuer_rows),
        issuer_index_,
        issuer_securities_
    );
    build_maturity_index(
        std::move(maturity_rows),
        maturity_index_,
        maturity_bonds_
    );
    return Status::success();
}

Status SecurityBook::mutation_complete() {
    if (batch_active_) {
        batch_dirty_ = true;
        return Status::success();
    }
    bump_version();
    return rebuild_indexes();
}

void SecurityBook::bump_version() noexcept {
    if (version_ != std::numeric_limits<std::uint64_t>::max()) {
        ++version_;
    }
}

}  // namespace macro_sim::core
