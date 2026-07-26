#include "macro_sim/core/securities.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <tuple>
#include <type_traits>
#include <utility>

namespace macro_sim::core {
namespace {

constexpr double kMinimumUnits = 1.0e-12;
constexpr std::size_t kMissingPairSlot = std::numeric_limits<std::size_t>::max();
constexpr std::size_t kPairLoadNumerator = 3U;
constexpr std::size_t kPairLoadDenominator = 4U;

[[nodiscard]] bool finite_nonnegative(double value) noexcept {
    return std::isfinite(value) && value >= 0.0;
}

template <typename Record, typename Id>
[[nodiscard]] Record *sequential_get(std::vector<Record> &records, Id id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > records.size()) {
        return nullptr;
    }
    auto &record = records[static_cast<std::size_t>(id.value() - 1)];
    return record.id == id ? &record : nullptr;
}

template <typename Record, typename Id>
[[nodiscard]] const Record *sequential_get(const std::vector<Record> &records,
                                           Id id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > records.size()) {
        return nullptr;
    }
    const auto &record = records[static_cast<std::size_t>(id.value() - 1)];
    return record.id == id ? &record : nullptr;
}

template <typename Entry, typename Key, typename Values, typename Projection>
[[nodiscard]] std::span<const typename Values::value_type>
indexed_values(const std::vector<Entry> &entries, const Values &values, const Key &key,
               Projection projection) noexcept {
    const auto found =
        std::lower_bound(entries.begin(), entries.end(), key,
                         [&projection](const Entry &entry, const Key &candidate) {
                             return projection(entry) < candidate;
                         });
    if (found == entries.end() || projection(*found) != key) {
        return {};
    }
    return std::span<const typename Values::value_type>(values.data() + found->offset,
                                                        found->count);
}

template <typename Key, typename Value, typename Entry>
void build_flat_index(std::vector<std::pair<Key, Value>> &rows,
                      std::vector<Entry> &entries, std::vector<Value> &values) {
    std::sort(rows.begin(), rows.end(), [](const auto &left, const auto &right) {
        if (left.first != right.first) {
            return left.first < right.first;
        }
        return left.second < right.second;
    });
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto &[key, value] : rows) {
        if (entries.empty() || !(entries.back().holder == key)) {
            entries.push_back({
                key,
                static_cast<std::uint32_t>(values.size()),
                0,
            });
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

void build_contract_index(std::vector<std::pair<SecurityId, SecurityLotId>> &rows,
                          std::vector<ContractLotIndexEntry> &entries,
                          std::vector<SecurityLotId> &values) {
    std::sort(rows.begin(), rows.end(), [](const auto &left, const auto &right) {
        if (left.first != right.first) {
            return left.first < right.first;
        }
        return left.second < right.second;
    });
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto &[key, value] : rows) {
        if (entries.empty() || entries.back().security != key) {
            entries.push_back({
                key,
                static_cast<std::uint32_t>(values.size()),
                0,
            });
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

[[nodiscard]] bool
build_dense_holder_index(const std::vector<SecurityLot> &lots,
                         std::vector<HolderSecurityIndexEntry> &entries,
                         std::vector<SecurityLotId> &values,
                         std::vector<std::uint32_t> &counts) {
    constexpr std::size_t kind_count =
        static_cast<std::size_t>(OwnerKind::institution) + 1U;
    std::array<std::uint32_t, kind_count> maximum_values{};
    std::size_t active_count = 0U;
    for (const auto &lot : lots) {
        if (lot.active) {
            const auto kind = static_cast<std::size_t>(lot.holder.kind);
            if (kind >= kind_count) {
                return false;
            }
            maximum_values[kind] =
                std::max(maximum_values[kind], lot.holder.value);
            ++active_count;
        }
    }
    std::array<std::size_t, kind_count> kind_offsets{};
    std::size_t slot_count = 0U;
    for (std::size_t kind = 0U; kind < kind_count; ++kind) {
        kind_offsets[kind] = slot_count;
        slot_count += static_cast<std::size_t>(maximum_values[kind]) + 1U;
    }
    const auto dense_limit = std::max<std::size_t>(1024U, active_count * 2U);
    if (slot_count > dense_limit) {
        return false;
    }
    counts.resize(slot_count);
    std::fill(counts.begin(), counts.end(), 0U);
    for (const auto &lot : lots) {
        if (!lot.active) {
            continue;
        }
        const auto kind = static_cast<std::size_t>(lot.holder.kind);
        const auto slot = kind_offsets[kind] +
                          static_cast<std::size_t>(lot.holder.value);
        ++counts[slot];
    }
    entries.clear();
    values.resize(active_count);
    std::uint32_t offset = 0U;
    for (std::size_t kind = 0U; kind < kind_count; ++kind) {
        const auto limit = static_cast<std::size_t>(maximum_values[kind]) + 1U;
        for (std::size_t value = 1U; value < limit; ++value) {
            const auto slot = kind_offsets[kind] + value;
            const auto count = counts[slot];
            counts[slot] = offset;
            if (count == 0U) {
                continue;
            }
            entries.push_back({
                OwnerId{
                    static_cast<OwnerKind>(kind),
                    static_cast<std::uint32_t>(value),
                },
                offset,
                count,
            });
            offset += count;
        }
    }
    for (const auto &lot : lots) {
        if (!lot.active) {
            continue;
        }
        const auto kind = static_cast<std::size_t>(lot.holder.kind);
        const auto slot = kind_offsets[kind] +
                          static_cast<std::size_t>(lot.holder.value);
        values[counts[slot]++] = lot.id;
    }
    return true;
}

[[nodiscard]] bool build_dense_contract_index(
    const std::vector<SecurityLot> &lots, std::vector<ContractLotIndexEntry> &entries,
    std::vector<SecurityLotId> &values, std::vector<std::uint32_t> &counts) {
    constexpr std::size_t kind_count =
        static_cast<std::size_t>(SecurityKind::equity) + 1U;
    std::uint32_t maximum_value = 0U;
    std::size_t active_count = 0U;
    for (const auto &lot : lots) {
        if (lot.active) {
            if (static_cast<std::size_t>(lot.security.kind) >= kind_count) {
                return false;
            }
            maximum_value = std::max(maximum_value, lot.security.value);
            ++active_count;
        }
    }
    const auto stride = static_cast<std::size_t>(maximum_value) + 1U;
    const auto slot_count = stride * kind_count;
    const auto dense_limit = std::max<std::size_t>(1024U, active_count * 2U);
    if (slot_count > dense_limit) {
        return false;
    }
    counts.resize(slot_count);
    std::fill(counts.begin(), counts.end(), 0U);
    for (const auto &lot : lots) {
        if (!lot.active) {
            continue;
        }
        const auto slot = static_cast<std::size_t>(lot.security.kind) * stride +
                          static_cast<std::size_t>(lot.security.value);
        ++counts[slot];
    }
    entries.clear();
    values.resize(active_count);
    std::uint32_t offset = 0U;
    for (std::size_t kind = 0U; kind < kind_count; ++kind) {
        for (std::size_t value = 1U; value < stride; ++value) {
            const auto slot = kind * stride + value;
            const auto count = counts[slot];
            counts[slot] = offset;
            if (count == 0U) {
                continue;
            }
            entries.push_back({
                SecurityId{
                    static_cast<SecurityKind>(kind),
                    static_cast<std::uint32_t>(value),
                },
                offset,
                count,
            });
            offset += count;
        }
    }
    for (const auto &lot : lots) {
        if (!lot.active) {
            continue;
        }
        const auto slot = static_cast<std::size_t>(lot.security.kind) * stride +
                          static_cast<std::size_t>(lot.security.value);
        values[counts[slot]++] = lot.id;
    }
    return true;
}

void build_issuer_index(std::vector<std::pair<OwnerId, SecurityId>> &rows,
                        std::vector<IssuerSecurityIndexEntry> &entries,
                        std::vector<SecurityId> &values) {
    std::sort(rows.begin(), rows.end(), [](const auto &left, const auto &right) {
        if (left.first != right.first) {
            return left.first < right.first;
        }
        return left.second < right.second;
    });
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto &[key, value] : rows) {
        if (entries.empty() || entries.back().issuer != key) {
            entries.push_back({
                key,
                static_cast<std::uint32_t>(values.size()),
                0,
            });
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

void build_maturity_index(std::vector<std::pair<Tick, BondId>> &rows,
                          std::vector<MaturityIndexEntry> &entries,
                          std::vector<BondId> &values) {
    std::sort(rows.begin(), rows.end(), [](const auto &left, const auto &right) {
        if (left.first != right.first) {
            return left.first < right.first;
        }
        return left.second < right.second;
    });
    entries.clear();
    values.clear();
    entries.reserve(rows.size());
    values.reserve(rows.size());
    for (const auto &[key, value] : rows) {
        if (entries.empty() || entries.back().maturity != key) {
            entries.push_back({
                key,
                static_cast<std::uint32_t>(values.size()),
                0,
            });
        }
        values.push_back(value);
        ++entries.back().count;
    }
}

[[nodiscard]] double scaled_tolerance(double tolerance, double expected) noexcept {
    return std::max(tolerance, tolerance * std::max(1.0, std::abs(expected)));
}

} // namespace

std::size_t SecurityBook::pair_hash(SecurityId security, OwnerId holder) noexcept {
    const auto mix = [](std::uint64_t value) {
        value += 0x9e3779b97f4a7c15ULL;
        value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31U);
    };
    std::uint64_t hash =
        mix(static_cast<std::uint64_t>(security.kind) ^ security.value);
    hash ^= mix(static_cast<std::uint64_t>(holder.kind) ^ holder.value ^
                0x517cc1b727220a95ULL);
    return static_cast<std::size_t>(hash);
}

std::size_t
SecurityBook::find_pair_slot(SecurityId security, OwnerId holder) const noexcept {
    if (pair_slots_.empty()) {
        return kMissingPairSlot;
    }
    const auto mask = pair_slots_.size() - 1U;
    auto slot = pair_hash(security, holder) & mask;
    while (pair_slots_[slot] != 0U) {
        const auto *lot = get(SecurityLotId(pair_slots_[slot]));
        if (lot != nullptr && lot->security == security && lot->holder == holder) {
            return slot;
        }
        slot = (slot + 1U) & mask;
    }
    return slot;
}

void SecurityBook::rebuild_pair_index() {
    pair_count_ = 0;
    std::size_t capacity = 8U;
    while (lots_.size() * kPairLoadDenominator > capacity * kPairLoadNumerator) {
        capacity *= 2U;
    }
    pair_slots_.assign(capacity, 0U);
    const auto mask = capacity - 1U;
    for (const auto &lot : lots_) {
        auto slot = pair_hash(lot.security, lot.holder) & mask;
        while (pair_slots_[slot] != 0U) {
            const auto *indexed = get(SecurityLotId(pair_slots_[slot]));
            if (indexed != nullptr && indexed->security == lot.security &&
                indexed->holder == lot.holder) {
                if (!indexed->active || lot.active) {
                    pair_slots_[slot] = static_cast<std::uint32_t>(lot.id.value());
                }
                break;
            }
            slot = (slot + 1U) & mask;
        }
        if (pair_slots_[slot] == 0U) {
            pair_slots_[slot] = static_cast<std::uint32_t>(lot.id.value());
            ++pair_count_;
        }
    }
}

void SecurityBook::append_pair_lot(SecurityLotId lot_id) {
    if (pair_slots_.empty()) {
        rebuild_pair_index();
        return;
    }
    const auto *lot = get(lot_id);
    const auto slot = find_pair_slot(lot->security, lot->holder);
    if (slot != kMissingPairSlot && pair_slots_[slot] != 0U) {
        pair_slots_[slot] = static_cast<std::uint32_t>(lot_id.value());
        return;
    }
    if ((pair_count_ + 1U) * kPairLoadDenominator >
        pair_slots_.size() * kPairLoadNumerator) {
        rebuild_pair_index();
        return;
    }
    pair_slots_[slot] = static_cast<std::uint32_t>(lot_id.value());
    ++pair_count_;
}

void SecurityBook::record_household_position_change(SecurityId security,
                                                    OwnerId holder) {
    if (holder.kind == OwnerKind::household) {
        household_position_changes_.push_back({security, holder});
    }
}

Result<SecurityLotId> SecurityBook::create_lot(SecurityId security, OwnerId holder,
                                               double units, Money cost_basis) {
    if (!validate_security(security).ok() || !holder.valid() ||
        !finite_nonnegative(units) || units <= kMinimumUnits ||
        !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid security lot");
    }
    if (auto *existing = find_active_lot(security, holder); existing != nullptr) {
        existing->units += units;
        existing->cost_basis = Money(existing->cost_basis.value() + cost_basis.value());
        record_household_position_change(security, holder);
        return existing->id;
    }
    if (lots_.size() >= SecurityLotId::max_valid_value()) {
        return Status(ErrorCode::out_of_range, "security lot index is too large");
    }
    const auto id = SecurityLotId(static_cast<std::uint64_t>(lots_.size()) + 1);
    lots_.push_back(SecurityLot{id, security, holder, units, cost_basis, true});
    append_pair_lot(id);
    record_household_position_change(security, holder);
    return id;
}

SecurityLot *SecurityBook::find_active_lot(SecurityId security,
                                           OwnerId holder) noexcept {
    const auto slot = find_pair_slot(security, holder);
    if (slot == kMissingPairSlot || pair_slots_[slot] == 0U) {
        return nullptr;
    }
    auto *lot = get(SecurityLotId(pair_slots_[slot]));
    return lot != nullptr && lot->active && lot->security == security &&
                   lot->holder == holder
               ? lot
               : nullptr;
}

const SecurityLot *SecurityBook::find_active_lot(SecurityId security,
                                                 OwnerId holder) const noexcept {
    return const_cast<SecurityBook *>(this)->find_active_lot(security, holder);
}

Result<BondId> SecurityBook::issue_bond(BondContract contract, OwnerId holder,
                                        Money cost_basis) {
    if (!contract.issuer.valid() || !contract.issuer_account.valid() ||
        !contract.currency.valid() || contract.maturity_tick < contract.issued_tick ||
        !finite_nonnegative(contract.coupon_rate.value()) ||
        !finite_nonnegative(contract.original_face.value()) ||
        contract.original_face.value() <= kMinimumUnits || contract.settled ||
        !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid bond contract");
    }
    if (bonds_.size() >= SecurityId::max_packed_value()) {
        return Status(ErrorCode::out_of_range, "bond index is too large");
    }
    contract.id = BondId(static_cast<std::uint64_t>(bonds_.size()) + 1);
    contract.outstanding_face = contract.original_face;
    contract.active = true;
    bonds_.push_back(contract);
    auto lot = create_lot(SecurityId::bond(contract.id), holder,
                          contract.original_face.value(), cost_basis);
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

Result<EquityId>
SecurityBook::create_equity(EquityContract contract,
                            std::span<const InitialSecurityHolding> holdings) {
    if (!contract.issuer.valid() || !contract.issuer_account.valid() ||
        !contract.currency.valid() ||
        !finite_nonnegative(contract.outstanding_shares) ||
        contract.outstanding_shares <= kMinimumUnits ||
        !finite_nonnegative(contract.price.value()) ||
        !finite_nonnegative(contract.last_price.value()) ||
        !finite_nonnegative(contract.peak_price.value()) ||
        !finite_nonnegative(contract.fundamental.value()) ||
        !std::isfinite(contract.trend) || !std::isfinite(contract.income_signal) ||
        contract.resolved || holdings.empty()) {
        return Status(ErrorCode::invalid_argument, "invalid equity contract");
    }
    if (equities_.size() >= SecurityId::max_packed_value()) {
        return Status(ErrorCode::out_of_range, "equity index is too large");
    }
    double total = 0.0;
    for (const auto &holding : holdings) {
        if (!holding.holder.valid() || !finite_nonnegative(holding.units) ||
            holding.units <= kMinimumUnits ||
            !finite_nonnegative(holding.cost_basis.value())) {
            return Status(ErrorCode::invalid_argument, "invalid equity holding");
        }
        total += holding.units;
    }
    if (!std::isfinite(total) ||
        std::abs(total - contract.outstanding_shares) >
            scaled_tolerance(1.0e-10, contract.outstanding_shares)) {
        return Status(ErrorCode::contract_violation,
                      "equity holdings do not equal outstanding shares");
    }
    contract.id = EquityId(static_cast<std::uint64_t>(equities_.size()) + 1);
    contract.active = true;
    equities_.push_back(contract);
    const auto first_lot = lots_.size();
    for (const auto &holding : holdings) {
        auto lot = create_lot(SecurityId::equity(contract.id), holding.holder,
                              holding.units, holding.cost_basis);
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

Status SecurityBook::transfer_units(SecurityId security, OwnerId source,
                                    OwnerId destination, double units,
                                    Money destination_cost_basis) {
    if (!validate_security(security).ok() || !source.valid() || !destination.valid() ||
        source == destination || !std::isfinite(units) || units <= kMinimumUnits ||
        !finite_nonnegative(destination_cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid security transfer");
    }
    const double held = units_held(security, source);
    constexpr double transfer_tolerance = 1.0e-9;
    if (units > held + scaled_tolerance(transfer_tolerance, held)) {
        return Status(ErrorCode::insufficient_funds,
                      security.kind == SecurityKind::bond
                          ? "bond transfer exceeds holdings"
                          : "equity transfer exceeds holdings");
    }

    const double transferred_units = std::min(units, held);
    double remaining = transferred_units;
    double removed_cost = 0.0;
    const auto remove_from_lot = [&](SecurityLot &lot) {
        if (!lot.active || lot.security != security || lot.holder != source ||
            remaining <= kMinimumUnits) {
            return;
        }
        const double take = std::min(remaining, lot.units);
        const double fraction = take / lot.units;
        removed_cost += lot.cost_basis.value() * fraction;
        lot.units -= take;
        lot.cost_basis =
            Money(std::max(0.0, lot.cost_basis.value() * (1.0 - fraction)));
        remaining -= take;
        if (lot.units <= kMinimumUnits) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    };
    auto *source_lot = find_active_lot(security, source);
    if (source_lot == nullptr) {
        return Status(ErrorCode::invariant_violation,
                      "security source index is inconsistent");
    }
    remove_from_lot(*source_lot);
    if (remaining > scaled_tolerance(transfer_tolerance, transferred_units)) {
        return Status(ErrorCode::invariant_violation,
                      "security source index is inconsistent");
    }

    SecurityLot *destination_lot = find_active_lot(security, destination);
    const double assigned_cost =
        destination_cost_basis.value() > 0.0
            ? destination_cost_basis.value() * transferred_units / units
            : removed_cost;
    if (destination_lot == nullptr) {
        auto created =
            create_lot(security, destination, transferred_units, Money(assigned_cost));
        if (!created.ok()) {
            return created.status();
        }
    } else {
        destination_lot->units += transferred_units;
        destination_lot->cost_basis =
            Money(destination_lot->cost_basis.value() + assigned_cost);
        record_household_position_change(security, destination);
    }
    record_household_position_change(security, source);
    return mutation_complete();
}

Status SecurityBook::issue_equity_units(EquityId equity, OwnerId destination,
                                        double units, Money cost_basis) {
    auto *contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved ||
        !destination.valid() || !std::isfinite(units) || units <= kMinimumUnits ||
        !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid equity issuance");
    }
    const auto security = SecurityId::equity(equity);
    SecurityLot *destination_lot = find_active_lot(security, destination);
    if (destination_lot == nullptr) {
        auto created = create_lot(security, destination, units, cost_basis);
        if (!created.ok()) {
            return created.status();
        }
    } else {
        destination_lot->units += units;
        destination_lot->cost_basis =
            Money(destination_lot->cost_basis.value() + cost_basis.value());
        record_household_position_change(security, destination);
    }
    contract->outstanding_shares += units;
    return mutation_complete();
}

Status SecurityBook::issue_bond_units(BondId bond, OwnerId destination, double units,
                                      Money cost_basis) {
    auto *contract = get(bond);
    if (contract == nullptr || !contract->active || contract->settled ||
        !destination.valid() || !std::isfinite(units) || units <= kMinimumUnits ||
        !finite_nonnegative(cost_basis.value())) {
        return Status(ErrorCode::invalid_argument, "invalid bond issuance");
    }
    const auto security = SecurityId::bond(bond);
    auto *destination_lot = find_active_lot(security, destination);
    if (destination_lot == nullptr) {
        auto created = create_lot(security, destination, units, cost_basis);
        if (!created.ok()) {
            return created.status();
        }
    } else {
        destination_lot->units += units;
        destination_lot->cost_basis =
            Money(destination_lot->cost_basis.value() + cost_basis.value());
        record_household_position_change(security, destination);
    }
    contract->original_face = Money(contract->original_face.value() + units);
    contract->outstanding_face = Money(contract->outstanding_face.value() + units);
    return mutation_complete();
}

Status SecurityBook::retire_units(SecurityId security, OwnerId holder, double units) {
    if (!validate_security(security).ok() || !holder.valid() || !std::isfinite(units) ||
        units <= kMinimumUnits) {
        return Status(ErrorCode::invalid_argument, "invalid security retirement");
    }
    const double held = units_held(security, holder);
    if (units > held + scaled_tolerance(1.0e-10, held)) {
        return Status(ErrorCode::insufficient_funds,
                      "security retirement exceeds holdings");
    }
    double remaining = std::min(units, held);
    const auto retire_from_lot = [&](SecurityLot &lot) {
        if (!lot.active || lot.security != security || lot.holder != holder ||
            remaining <= kMinimumUnits) {
            return;
        }
        const double take = std::min(remaining, lot.units);
        const double fraction = take / lot.units;
        lot.units -= take;
        lot.cost_basis =
            Money(std::max(0.0, lot.cost_basis.value() * (1.0 - fraction)));
        remaining -= take;
        if (lot.units <= kMinimumUnits) {
            lot.units = 0.0;
            lot.cost_basis = Money(0.0);
            lot.active = false;
        }
    };
    auto *lot = find_active_lot(security, holder);
    if (lot == nullptr) {
        return Status(ErrorCode::invariant_violation,
                      "security holder index is inconsistent");
    }
    retire_from_lot(*lot);
    if (security.kind == SecurityKind::bond) {
        auto *contract = get(BondId(security.value));
        contract->outstanding_face =
            Money(std::max(0.0, contract->outstanding_face.value() - units));
    } else {
        auto *contract = get(EquityId(security.value));
        contract->outstanding_shares =
            std::max(0.0, contract->outstanding_shares - units);
    }
    record_household_position_change(security, holder);
    return mutation_complete();
}

Status SecurityBook::settle_bond(BondId bond) {
    auto *contract = get(bond);
    if (contract == nullptr || !contract->active || contract->settled) {
        return Status(ErrorCode::invalid_argument, "invalid bond settlement");
    }
    const auto security = SecurityId::bond(bond);
    for (auto &lot : lots_) {
        if (lot.active && lot.security == security) {
            record_household_position_change(security, lot.holder);
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
    auto *contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved) {
        return Status(ErrorCode::invalid_argument, "invalid equity resolution");
    }
    const auto security = SecurityId::equity(equity);
    for (auto &lot : lots_) {
        if (lot.active && lot.security == security) {
            record_household_position_change(security, lot.holder);
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

Status SecurityBook::update_equity_valuation(EquityId equity, Price price,
                                             Price last_price, Price peak_price,
                                             Price fundamental, double trend,
                                             double income_signal) {
    auto *contract = get(equity);
    if (contract == nullptr || !contract->active || contract->resolved ||
        !finite_nonnegative(price.value()) || !finite_nonnegative(last_price.value()) ||
        !finite_nonnegative(peak_price.value()) ||
        !finite_nonnegative(fundamental.value()) || !std::isfinite(trend) ||
        !std::isfinite(income_signal)) {
        return Status(ErrorCode::invalid_argument, "invalid equity valuation update");
    }
    contract->price = price;
    contract->last_price = last_price;
    contract->peak_price = peak_price;
    contract->fundamental = fundamental;
    contract->trend = trend;
    contract->income_signal = income_signal;
    return mutation_complete(false);
}

Status SecurityBook::consolidate() {
    rebuild_pair_index();
    bool changed = false;
    for (auto &candidate : lots_) {
        if (!candidate.active) {
            continue;
        }
        const auto slot = find_pair_slot(candidate.security, candidate.holder);
        if (slot == kMissingPairSlot || pair_slots_[slot] == 0U) {
            return Status(ErrorCode::invariant_violation,
                          "security pair index is inconsistent");
        }
        auto *target = get(SecurityLotId(pair_slots_[slot]));
        if (target == nullptr || target == &candidate) {
            continue;
        }
        target->units += candidate.units;
        target->cost_basis =
            Money(target->cost_basis.value() + candidate.cost_basis.value());
        candidate.units = 0.0;
        candidate.cost_basis = Money(0.0);
        candidate.active = false;
        changed = true;
    }
    if (!changed) {
        return Status::success();
    }
    return mutation_complete();
}

Status SecurityBook::compact_inactive_lots() {
    if (std::all_of(lots_.begin(), lots_.end(),
                    [](const SecurityLot &lot) { return lot.active; })) {
        return Status::success();
    }
    std::size_t write = 0U;
    for (std::size_t read = 0U; read < lots_.size(); ++read) {
        if (!lots_[read].active) {
            continue;
        }
        if (write != read) {
            lots_[write] = std::move(lots_[read]);
        }
        lots_[write].id = SecurityLotId(static_cast<std::uint64_t>(write) + 1U);
        ++write;
    }
    lots_.resize(write);
    if (batch_active_) {
        rebuild_pair_index();
        batch_dirty_ = true;
        batch_indexes_dirty_ = true;
        return Status::success();
    }
    return rebuild_indexes();
}

Status SecurityBook::reserve_position_capacity(std::size_t expected_lots,
                                               std::size_t expected_active_pairs) {
    const auto limit = static_cast<std::size_t>(SecurityLotId::max_valid_value());
    if (expected_lots > limit || expected_active_pairs > limit) {
        return Status(ErrorCode::out_of_range,
                      "security position capacity exceeds the compact ID range");
    }
    lots_.reserve(expected_lots);
    holder_lots_.reserve(expected_lots);
    contract_lots_.reserve(expected_lots);
    std::size_t pair_capacity = 8U;
    while (expected_active_pairs * kPairLoadDenominator >
           pair_capacity * kPairLoadNumerator) {
        if (pair_capacity > limit / 2U) {
            return Status(ErrorCode::out_of_range,
                          "security pair capacity exceeds the compact ID range");
        }
        pair_capacity *= 2U;
    }
    pair_slots_.reserve(pair_capacity);
    return Status::success();
}

Status SecurityBook::reserve_additional_lots(std::size_t additional) {
    const auto limit = static_cast<std::size_t>(SecurityLotId::max_valid_value());
    if (lots_.size() > limit || additional > limit - lots_.size()) {
        return Status(ErrorCode::out_of_range,
                      "security lot reservation exceeds the compact ID range");
    }
    const auto required = lots_.size() + additional;
    if (required <= lots_.capacity()) {
        return Status::success();
    }
    const auto headroom =
        std::max<std::size_t>(1024U, std::max(additional, lots_.size() / 8U));
    lots_.reserve(std::min(limit, lots_.size() + headroom));
    return Status::success();
}

Status SecurityBook::begin_batch() noexcept {
    if (batch_active_) {
        return Status(ErrorCode::invalid_transaction_state,
                      "security mutation batch is already active");
    }
    batch_active_ = true;
    batch_dirty_ = false;
    batch_indexes_dirty_ = false;
    return Status::success();
}

Status SecurityBook::finish_batch() {
    if (!batch_active_) {
        return Status(ErrorCode::invalid_transaction_state,
                      "security mutation batch is not active");
    }
    batch_active_ = false;
    if (!batch_dirty_) {
        return Status::success();
    }
    batch_dirty_ = false;
    const bool rebuild = batch_indexes_dirty_;
    batch_indexes_dirty_ = false;
    bump_version();
    return rebuild ? rebuild_active_indexes() : Status::success();
}

BondContract *SecurityBook::get(BondId id) noexcept {
    return sequential_get(bonds_, id);
}

const BondContract *SecurityBook::get(BondId id) const noexcept {
    return sequential_get(bonds_, id);
}

EquityContract *SecurityBook::get(EquityId id) noexcept {
    return sequential_get(equities_, id);
}

const EquityContract *SecurityBook::get(EquityId id) const noexcept {
    return sequential_get(equities_, id);
}

SecurityLot *SecurityBook::get(SecurityLotId id) noexcept {
    return sequential_get(lots_, id);
}

const SecurityLot *SecurityBook::get(SecurityLotId id) const noexcept {
    return sequential_get(lots_, id);
}

const std::vector<BondContract> &SecurityBook::bonds() const noexcept { return bonds_; }

const std::vector<EquityContract> &SecurityBook::equities() const noexcept {
    return equities_;
}

const std::vector<SecurityLot> &SecurityBook::lots() const noexcept { return lots_; }

std::span<const HouseholdSecurityPositionChange>
SecurityBook::household_position_changes() const noexcept {
    return household_position_changes_;
}

void SecurityBook::clear_household_position_changes() noexcept {
    household_position_changes_.clear();
}

std::span<const SecurityLotId>
SecurityBook::lots_for_holder(OwnerId holder) const noexcept {
    return indexed_values(
        holder_index_, holder_lots_, holder,
        [](const HolderSecurityIndexEntry &entry) { return entry.holder; });
}

std::span<const SecurityLotId>
SecurityBook::lots_for_security(SecurityId security) const noexcept {
    return indexed_values(
        contract_index_, contract_lots_, security,
        [](const ContractLotIndexEntry &entry) { return entry.security; });
}

std::span<const SecurityId>
SecurityBook::securities_for_issuer(OwnerId issuer) const noexcept {
    return indexed_values(
        issuer_index_, issuer_securities_, issuer,
        [](const IssuerSecurityIndexEntry &entry) { return entry.issuer; });
}

std::span<const BondId> SecurityBook::bonds_maturing_at(Tick maturity) const noexcept {
    return indexed_values(
        maturity_index_, maturity_bonds_, maturity,
        [](const MaturityIndexEntry &entry) { return entry.maturity; });
}

std::span<const SecurityLotId> SecurityBook::bank_lots(BankId bank) const noexcept {
    return indexed_values(
        bank_index_, bank_lots_, OwnerId::bank(bank),
        [](const HolderSecurityIndexEntry &entry) { return entry.holder; });
}

double SecurityBook::units_held(SecurityId security, OwnerId holder) const noexcept {
    const auto *lot = find_active_lot(security, holder);
    return lot == nullptr ? 0.0 : lot->units;
}

double SecurityBook::total_units(SecurityId security) const noexcept {
    double total = 0.0;
    double correction = 0.0;
    for (const auto lot_id : lots_for_security(security)) {
        const auto *lot = get(lot_id);
        if (lot == nullptr || !lot->active) {
            continue;
        }
        const double next = total + lot->units;
        correction += std::abs(total) >= std::abs(lot->units)
                          ? (total - next) + lot->units
                          : (lot->units - next) + total;
        total = next;
    }
    return total + correction;
}

Money SecurityBook::total_bond_face() const noexcept {
    double total = 0.0;
    double correction = 0.0;
    for (const auto &bond : bonds_) {
        if (!bond.active) {
            continue;
        }
        const double value = bond.outstanding_face.value();
        const double next = total + value;
        correction += std::abs(total) >= std::abs(value) ? (total - next) + value
                                                         : (value - next) + total;
        total = next;
    }
    return Money(total + correction);
}

std::uint64_t SecurityBook::version() const noexcept { return version_; }

SecurityBookMemoryUsage SecurityBook::memory_usage() const noexcept {
    const auto bytes = [](const auto &values) {
        return static_cast<std::uint64_t>(values.capacity()) *
               sizeof(typename std::remove_cvref_t<decltype(values)>::value_type);
    };
    SecurityBookMemoryUsage usage;
    usage.contracts = bytes(bonds_) + bytes(equities_);
    usage.lots = bytes(lots_);
    usage.query_indexes = bytes(holder_index_) + bytes(holder_lots_) +
                          bytes(contract_index_) + bytes(contract_lots_) +
                          bytes(issuer_index_) + bytes(issuer_securities_) +
                          bytes(maturity_index_) + bytes(maturity_bonds_) +
                          bytes(bank_index_) + bytes(bank_lots_);
    usage.pair_index = bytes(pair_slots_);
    usage.scratch = bytes(household_position_changes_) + bytes(holder_rows_scratch_) +
                    bytes(contract_rows_scratch_) + bytes(issuer_rows_scratch_) +
                    bytes(maturity_rows_scratch_) + bytes(holder_counts_scratch_) +
                    bytes(contract_counts_scratch_);
    return usage;
}

Status SecurityBook::validate_records(double tolerance) const {
    if (!std::isfinite(tolerance) || tolerance < 0.0) {
        return Status(ErrorCode::invalid_argument, "invalid security tolerance");
    }
    for (std::size_t index = 0; index < bonds_.size(); ++index) {
        const auto &bond = bonds_[index];
        if (bond.id.value() != index + 1 || !bond.issuer.valid() ||
            !bond.issuer_account.valid() || !bond.currency.valid() ||
            bond.maturity_tick < bond.issued_tick ||
            !finite_nonnegative(bond.coupon_rate.value()) ||
            !finite_nonnegative(bond.original_face.value()) ||
            !finite_nonnegative(bond.outstanding_face.value()) ||
            (bond.active == bond.settled) ||
            (bond.settled && bond.outstanding_face.value() != 0.0) ||
            (bond.active &&
             bond.outstanding_face.value() >
                 bond.original_face.value() +
                     scaled_tolerance(tolerance, bond.original_face.value()))) {
            return Status(ErrorCode::invariant_violation, "invalid bond contract");
        }
    }
    for (std::size_t index = 0; index < equities_.size(); ++index) {
        const auto &equity = equities_[index];
        if (equity.id.value() != index + 1 || !equity.issuer.valid() ||
            !equity.issuer_account.valid() || !equity.currency.valid() ||
            !finite_nonnegative(equity.outstanding_shares) ||
            !finite_nonnegative(equity.price.value()) ||
            !finite_nonnegative(equity.last_price.value()) ||
            !finite_nonnegative(equity.peak_price.value()) ||
            !finite_nonnegative(equity.fundamental.value()) ||
            !std::isfinite(equity.trend) || !std::isfinite(equity.income_signal) ||
            (equity.active == equity.resolved) ||
            (equity.resolved &&
             (equity.outstanding_shares != 0.0 || equity.price.value() != 0.0))) {
            return Status(ErrorCode::invariant_violation, "invalid equity contract");
        }
    }
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        const auto &lot = lots_[index];
        if (lot.id.value() != index + 1 || !lot.security.valid() ||
            !lot.holder.valid() || !finite_nonnegative(lot.units) ||
            !finite_nonnegative(lot.cost_basis.value()) ||
            (lot.active && lot.units <= kMinimumUnits) ||
            (!lot.active && (lot.units != 0.0 || lot.cost_basis.value() != 0.0)) ||
            (lot.active && !validate_security(lot.security).ok())) {
            return Status(ErrorCode::invariant_violation, "invalid security lot");
        }
    }
    for (const auto &bond : bonds_) {
        const double held = total_units(SecurityId::bond(bond.id));
        if (std::abs(held - bond.outstanding_face.value()) >
            scaled_tolerance(tolerance, bond.outstanding_face.value())) {
            return Status(ErrorCode::invariant_violation, "bond face and lots differ");
        }
    }
    for (const auto &equity : equities_) {
        const double held = total_units(SecurityId::equity(equity.id));
        if (std::abs(held - equity.outstanding_shares) >
            scaled_tolerance(tolerance, equity.outstanding_shares)) {
            return Status(ErrorCode::invariant_violation,
                          "equity shares and lots differ");
        }
    }
    return Status::success();
}

Status SecurityBook::validate(double tolerance) const {
    const auto records = validate_records(tolerance);
    return records.ok() ? validate_indexes() : records;
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
    if (rebuilt.holder_index_ != holder_index_ ||
        rebuilt.holder_lots_ != holder_lots_ ||
        rebuilt.contract_index_ != contract_index_ ||
        rebuilt.contract_lots_ != contract_lots_ ||
        rebuilt.issuer_index_ != issuer_index_ ||
        rebuilt.issuer_securities_ != issuer_securities_ ||
        rebuilt.maturity_index_ != maturity_index_ ||
        rebuilt.maturity_bonds_ != maturity_bonds_ ||
        rebuilt.bank_index_ != bank_index_ || rebuilt.bank_lots_ != bank_lots_ ||
        rebuilt.pair_slots_ != pair_slots_ || rebuilt.pair_count_ != pair_count_) {
        return Status(ErrorCode::invariant_violation,
                      "security indexes are inconsistent");
    }
    for (const auto &lot : lots_) {
        const auto actual_slot = find_pair_slot(lot.security, lot.holder);
        if (actual_slot == kMissingPairSlot ||
            (lot.active &&
             pair_slots_[actual_slot] != static_cast<std::uint32_t>(lot.id.value()))) {
            return Status(ErrorCode::invariant_violation,
                          "security pair index contains duplicate active lots");
        }
    }
    return Status::success();
}

void SecurityBook::replace_records(std::vector<BondContract> bonds,
                                   std::vector<EquityContract> equities,
                                   std::vector<SecurityLot> lots,
                                   std::uint64_t version) {
    bonds_ = std::move(bonds);
    equities_ = std::move(equities);
    lots_ = std::move(lots);
    version_ = version;
    batch_active_ = false;
    batch_dirty_ = false;
    batch_indexes_dirty_ = false;
    household_position_changes_.clear();
    static_cast<void>(rebuild_indexes());
}

Status SecurityBook::validate_security(SecurityId security) const noexcept {
    if (!security.valid()) {
        return Status(ErrorCode::invalid_argument, "invalid security ID");
    }
    if (security.kind == SecurityKind::bond) {
        const auto *contract = get(BondId(security.value));
        if (contract == nullptr || !contract->active || contract->settled) {
            return Status(ErrorCode::not_found, "bond is not active");
        }
    } else if (security.kind == SecurityKind::equity) {
        const auto *contract = get(EquityId(security.value));
        if (contract == nullptr || !contract->active || contract->resolved) {
            return Status(ErrorCode::not_found, "equity is not active");
        }
    } else {
        return Status(ErrorCode::invalid_argument, "unknown security kind");
    }
    return Status::success();
}

Status SecurityBook::rebuild_indexes() {
    if (lots_.size() > std::numeric_limits<std::uint32_t>::max() ||
        bonds_.size() > SecurityId::max_packed_value() ||
        equities_.size() > SecurityId::max_packed_value()) {
        return Status(ErrorCode::out_of_range, "security index is too large");
    }
    rebuild_pair_index();
    return rebuild_active_indexes();
}

Status SecurityBook::rebuild_active_indexes() {
    if (lots_.size() > std::numeric_limits<std::uint32_t>::max() ||
        bonds_.size() > SecurityId::max_packed_value() ||
        equities_.size() > SecurityId::max_packed_value()) {
        return Status(ErrorCode::out_of_range, "security index is too large");
    }
    auto &holder_rows = holder_rows_scratch_;
    auto &contract_rows = contract_rows_scratch_;
    auto &issuer_rows = issuer_rows_scratch_;
    auto &maturity_rows = maturity_rows_scratch_;
    holder_rows.clear();
    contract_rows.clear();
    issuer_rows.clear();
    maturity_rows.clear();
    issuer_rows.reserve(bonds_.size() + equities_.size());
    maturity_rows.reserve(bonds_.size());
    for (const auto &bond : bonds_) {
        if (!bond.active) {
            continue;
        }
        issuer_rows.emplace_back(bond.issuer, SecurityId::bond(bond.id));
        maturity_rows.emplace_back(bond.maturity_tick, bond.id);
    }
    for (const auto &equity : equities_) {
        if (!equity.active) {
            continue;
        }
        issuer_rows.emplace_back(equity.issuer, SecurityId::equity(equity.id));
    }
    if (!build_dense_holder_index(lots_, holder_index_, holder_lots_,
                                  holder_counts_scratch_)) {
        holder_rows.reserve(lots_.size());
        for (const auto &lot : lots_) {
            if (lot.active) {
                holder_rows.emplace_back(lot.holder, lot.id);
            }
        }
        build_flat_index(holder_rows, holder_index_, holder_lots_);
    }
    bank_index_.clear();
    bank_lots_.clear();
    for (const auto &entry : holder_index_) {
        if (entry.holder.kind != OwnerKind::bank) {
            continue;
        }
        bank_index_.push_back({
            entry.holder,
            static_cast<std::uint32_t>(bank_lots_.size()),
            entry.count,
        });
        const auto begin = holder_lots_.begin() + entry.offset;
        bank_lots_.insert(bank_lots_.end(), begin, begin + entry.count);
    }
    if (!build_dense_contract_index(lots_, contract_index_, contract_lots_,
                                    contract_counts_scratch_)) {
        contract_rows.reserve(lots_.size());
        for (const auto &lot : lots_) {
            if (lot.active) {
                contract_rows.emplace_back(lot.security, lot.id);
            }
        }
        build_contract_index(contract_rows, contract_index_, contract_lots_);
    }
    build_issuer_index(issuer_rows, issuer_index_, issuer_securities_);
    build_maturity_index(maturity_rows, maturity_index_, maturity_bonds_);
    holder_rows.clear();
    contract_rows.clear();
    issuer_rows.clear();
    maturity_rows.clear();
    return Status::success();
}

Status SecurityBook::mutation_complete(bool indexes_dirty) {
    if (batch_active_) {
        batch_dirty_ = true;
        batch_indexes_dirty_ = batch_indexes_dirty_ || indexes_dirty;
        return Status::success();
    }
    bump_version();
    return indexes_dirty ? rebuild_active_indexes() : Status::success();
}

void SecurityBook::bump_version() noexcept {
    if (version_ != std::numeric_limits<std::uint64_t>::max()) {
        ++version_;
    }
}

} // namespace macro_sim::core
