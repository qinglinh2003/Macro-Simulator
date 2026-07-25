#include "macro_sim/core/housing.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace macro_sim::core {
namespace {

constexpr double kMinimumFloorArea = 1.0e-9;

[[nodiscard]] bool finite_positive(double value) noexcept {
    return std::isfinite(value) && value > kMinimumFloorArea;
}

[[nodiscard]] bool finite_nonnegative(double value) noexcept {
    return std::isfinite(value) && value >= 0.0;
}

[[nodiscard]] bool valid_title_kind(TitleEventKind kind) noexcept {
    return static_cast<std::uint8_t>(kind) <=
           static_cast<std::uint8_t>(TitleEventKind::destroy);
}

} // namespace

Result<DwellingId> PropertyRegistry::mint(const DwellingMintSpec &spec) {
    if (!spec.owner.valid() || !finite_positive(spec.floor_area) ||
        !finite_nonnegative(spec.quality)) {
        return Status(ErrorCode::invalid_argument, "invalid dwelling mint");
    }
    if (spec.occupant.valid() && occupant_index_.contains(spec.occupant)) {
        return Status(ErrorCode::already_exists,
                      "household already occupies a dwelling");
    }
    if (records_.size() ==
            static_cast<std::size_t>(std::numeric_limits<std::uint64_t>::max()) ||
        title_events_.size() ==
            static_cast<std::size_t>(std::numeric_limits<std::uint64_t>::max())) {
        return Status(ErrorCode::out_of_range, "dwelling id space exhausted");
    }

    const auto id = DwellingId(static_cast<std::uint64_t>(records_.size()) + 1);
    const auto event_id =
        TitleEventId(static_cast<std::uint64_t>(title_events_.size()) + 1);
    DwellingRecord record{
        id,
        spec.owner,
        spec.occupant,
        {},
        spec.tick,
        spec.tick,
        spec.floor_area,
        spec.quality,
        spec.location,
        spec.age_days,
        true,
    };

    records_.push_back(record);
    owner_index_[spec.owner].push_back(id);
    if (spec.occupant.valid()) {
        occupant_index_.emplace(spec.occupant, id);
    }
    title_events_.push_back({
        event_id,
        id,
        TitleEventKind::mint,
        {},
        spec.owner,
        spec.tick,
    });
    ++active_count_;
    return id;
}

Status PropertyRegistry::transfer_title(DwellingId dwelling, OwnerId expected_owner,
                                        OwnerId next_owner, Tick tick) {
    auto *record = get(dwelling);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "dwelling is not active");
    }
    if (!expected_owner.valid() || !next_owner.valid() ||
        expected_owner == next_owner) {
        return Status(ErrorCode::invalid_argument, "invalid title transfer");
    }
    if (record->owner != expected_owner) {
        return Status(ErrorCode::stale_handle, "stale dwelling title");
    }
    if (tick < record->last_title_tick) {
        return Status(ErrorCode::invalid_argument,
                      "title transfer precedes prior event");
    }
    if (title_events_.size() ==
        static_cast<std::size_t>(std::numeric_limits<std::uint64_t>::max())) {
        return Status(ErrorCode::out_of_range, "title event id space exhausted");
    }

    auto &next_holdings = owner_index_[next_owner];
    next_holdings.insert(
        std::lower_bound(next_holdings.begin(), next_holdings.end(), dwelling),
        dwelling);
    remove_owner_index(expected_owner, dwelling);
    record->owner = next_owner;
    record->last_title_tick = tick;
    return append_title_event({
        TitleEventId(static_cast<std::uint64_t>(title_events_.size()) + 1),
        dwelling,
        TitleEventKind::transfer,
        expected_owner,
        next_owner,
        tick,
    });
}

Status PropertyRegistry::destroy(DwellingId dwelling, OwnerId expected_owner,
                                 Tick tick) {
    auto *record = get(dwelling);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "dwelling is not active");
    }
    if (!expected_owner.valid() || record->owner != expected_owner) {
        return Status(ErrorCode::stale_handle, "stale dwelling title");
    }
    if (record->occupant.valid() || record->collateral.valid()) {
        return Status(ErrorCode::contract_violation,
                      "encumbered dwelling cannot be destroyed");
    }
    if (tick < record->last_title_tick) {
        return Status(ErrorCode::invalid_argument,
                      "destruction precedes prior title event");
    }
    if (title_events_.size() ==
        static_cast<std::size_t>(std::numeric_limits<std::uint64_t>::max())) {
        return Status(ErrorCode::out_of_range, "title event id space exhausted");
    }

    remove_owner_index(expected_owner, dwelling);
    record->active = false;
    record->last_title_tick = tick;
    --active_count_;
    ++destroyed_count_;
    return append_title_event({
        TitleEventId(static_cast<std::uint64_t>(title_events_.size()) + 1),
        dwelling,
        TitleEventKind::destroy,
        expected_owner,
        {},
        tick,
    });
}

Status PropertyRegistry::set_occupant(DwellingId dwelling,
                                      HouseholdId expected_occupant,
                                      HouseholdId next_occupant) {
    auto *record = get(dwelling);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "dwelling is not active");
    }
    if (record->occupant != expected_occupant) {
        return Status(ErrorCode::stale_handle, "stale dwelling occupant");
    }
    if (next_occupant.valid() && next_occupant != expected_occupant &&
        occupant_index_.contains(next_occupant)) {
        return Status(ErrorCode::already_exists,
                      "household already occupies a dwelling");
    }
    if (expected_occupant.valid()) {
        occupant_index_.erase(expected_occupant);
    }
    if (next_occupant.valid()) {
        occupant_index_.emplace(next_occupant, dwelling);
    }
    record->occupant = next_occupant;
    return Status::success();
}

Status PropertyRegistry::attach_collateral(DwellingId dwelling, LoanId loan) {
    auto *record = get(dwelling);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "dwelling is not active");
    }
    if (!loan.valid()) {
        return Status(ErrorCode::invalid_argument, "invalid collateral loan");
    }
    if (record->collateral.valid()) {
        return Status(ErrorCode::already_exists, "dwelling already has collateral");
    }
    if (collateral_index_.contains(loan)) {
        return Status(ErrorCode::already_exists, "loan already has collateral");
    }
    collateral_index_.emplace(loan, dwelling);
    record->collateral = loan;
    return Status::success();
}

Status PropertyRegistry::clear_collateral(DwellingId dwelling, LoanId expected_loan) {
    auto *record = get(dwelling);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "dwelling is not active");
    }
    if (!expected_loan.valid() || record->collateral != expected_loan) {
        return Status(ErrorCode::stale_handle, "stale dwelling collateral");
    }
    collateral_index_.erase(expected_loan);
    record->collateral = {};
    return Status::success();
}

DwellingRecord *PropertyRegistry::get(DwellingId id) noexcept {
    if (!id.valid() || id.value() > records_.size()) {
        return nullptr;
    }
    return &records_[static_cast<std::size_t>(id.value() - 1)];
}

const DwellingRecord *PropertyRegistry::get(DwellingId id) const noexcept {
    return const_cast<PropertyRegistry *>(this)->get(id);
}

const std::vector<DwellingRecord> &PropertyRegistry::records() const noexcept {
    return records_;
}

const std::vector<TitleEvent> &PropertyRegistry::title_events() const noexcept {
    return title_events_;
}

std::span<const DwellingId>
PropertyRegistry::dwellings_for_owner(OwnerId owner) const noexcept {
    const auto found = owner_index_.find(owner);
    if (found == owner_index_.end()) {
        return {};
    }
    return found->second;
}

DwellingId
PropertyRegistry::dwelling_for_occupant(HouseholdId household) const noexcept {
    const auto found = occupant_index_.find(household);
    return found == occupant_index_.end() ? DwellingId{} : found->second;
}

DwellingId PropertyRegistry::dwelling_for_collateral(LoanId loan) const noexcept {
    const auto found = collateral_index_.find(loan);
    return found == collateral_index_.end() ? DwellingId{} : found->second;
}

std::size_t PropertyRegistry::active_count() const noexcept { return active_count_; }

std::size_t PropertyRegistry::minted_count() const noexcept { return records_.size(); }

std::size_t PropertyRegistry::destroyed_count() const noexcept {
    return destroyed_count_;
}

Status PropertyRegistry::validate() const noexcept {
    if (active_count_ + destroyed_count_ != records_.size() ||
        title_events_.size() < records_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "invalid dwelling stock counters");
    }

    std::size_t active = 0;
    std::size_t destroyed = 0;
    for (std::size_t index = 0; index < records_.size(); ++index) {
        const auto &record = records_[index];
        if (record.id.value() != index + 1 || !record.owner.valid() ||
            !finite_positive(record.floor_area) ||
            !finite_nonnegative(record.quality) ||
            record.last_title_tick < record.minted_tick) {
            return Status(ErrorCode::invariant_violation, "invalid dwelling record");
        }
        if (record.active) {
            ++active;
            const auto owner = owner_index_.find(record.owner);
            if (owner == owner_index_.end() ||
                std::count(owner->second.begin(), owner->second.end(), record.id) !=
                    1) {
                return Status(ErrorCode::invariant_violation,
                              "invalid dwelling owner index");
            }
            if (record.occupant.valid()) {
                const auto occupant = occupant_index_.find(record.occupant);
                if (occupant == occupant_index_.end() ||
                    occupant->second != record.id) {
                    return Status(ErrorCode::invariant_violation,
                                  "invalid dwelling occupant index");
                }
            }
            if (record.collateral.valid()) {
                const auto collateral = collateral_index_.find(record.collateral);
                if (collateral == collateral_index_.end() ||
                    collateral->second != record.id) {
                    return Status(ErrorCode::invariant_violation,
                                  "invalid dwelling collateral index");
                }
            }
        } else {
            ++destroyed;
            if (record.occupant.valid() || record.collateral.valid()) {
                return Status(ErrorCode::invariant_violation,
                              "inactive dwelling remains encumbered");
            }
            const auto owner = owner_index_.find(record.owner);
            if (owner != owner_index_.end() &&
                std::find(owner->second.begin(), owner->second.end(), record.id) !=
                    owner->second.end()) {
                return Status(ErrorCode::invariant_violation,
                              "inactive dwelling remains indexed");
            }
        }
    }
    if (active != active_count_ || destroyed != destroyed_count_) {
        return Status(ErrorCode::invariant_violation,
                      "dwelling stock counter mismatch");
    }

    for (const auto &[owner, dwellings] : owner_index_) {
        if (!owner.valid() || dwellings.empty()) {
            return Status(ErrorCode::invariant_violation, "invalid owner index entry");
        }
        for (std::size_t index = 0; index < dwellings.size(); ++index) {
            if (index > 0 && dwellings[index - 1] >= dwellings[index]) {
                return Status(ErrorCode::invariant_violation,
                              "owner index is not unique and ordered");
            }
            const auto *record = get(dwellings[index]);
            if (record == nullptr || !record->active || record->owner != owner) {
                return Status(ErrorCode::invariant_violation,
                              "owner index does not resolve");
            }
        }
    }
    for (const auto &[occupant, dwelling] : occupant_index_) {
        const auto *record = get(dwelling);
        if (!occupant.valid() || record == nullptr || !record->active ||
            record->occupant != occupant) {
            return Status(ErrorCode::invariant_violation,
                          "occupant index does not resolve");
        }
    }
    for (const auto &[loan, dwelling] : collateral_index_) {
        const auto *record = get(dwelling);
        if (!loan.valid() || record == nullptr || !record->active ||
            record->collateral != loan) {
            return Status(ErrorCode::invariant_violation,
                          "collateral index does not resolve");
        }
    }

    std::vector<std::size_t> lineage(records_.size(), 0);
    std::vector<OwnerId> lineage_owner(records_.size());
    std::vector<bool> lineage_active(records_.size(), false);
    std::vector<Tick> lineage_tick(records_.size());
    for (std::size_t index = 0; index < title_events_.size(); ++index) {
        const auto &event = title_events_[index];
        if (event.id.value() != index + 1 || !event.dwelling.valid() ||
            event.dwelling.value() > records_.size() || !valid_title_kind(event.kind)) {
            return Status(ErrorCode::invariant_violation, "invalid title event");
        }
        const auto position = static_cast<std::size_t>(event.dwelling.value() - 1);
        if (event.kind == TitleEventKind::mint) {
            if (lineage[position] != 0 || event.previous_owner.valid() ||
                !event.next_owner.valid() ||
                event.tick != records_[position].minted_tick) {
                return Status(ErrorCode::invariant_violation,
                              "invalid dwelling mint lineage");
            }
            lineage_owner[position] = event.next_owner;
            lineage_active[position] = true;
        } else if (event.kind == TitleEventKind::transfer) {
            if (!lineage_active[position] ||
                lineage_owner[position] != event.previous_owner ||
                !event.next_owner.valid() || event.previous_owner == event.next_owner ||
                event.tick < lineage_tick[position]) {
                return Status(ErrorCode::invariant_violation,
                              "invalid title transfer lineage");
            }
            lineage_owner[position] = event.next_owner;
        } else {
            if (!lineage_active[position] ||
                lineage_owner[position] != event.previous_owner ||
                event.next_owner.valid() || event.tick < lineage_tick[position]) {
                return Status(ErrorCode::invariant_violation,
                              "invalid dwelling destruction lineage");
            }
            lineage_active[position] = false;
        }
        lineage_tick[position] = event.tick;
        ++lineage[position];
    }
    for (std::size_t index = 0; index < records_.size(); ++index) {
        if (lineage[index] == 0 || lineage_owner[index] != records_[index].owner ||
            lineage_active[index] != records_[index].active ||
            lineage_tick[index] != records_[index].last_title_tick) {
            return Status(ErrorCode::invariant_violation,
                          "title lineage does not match dwelling");
        }
    }
    return Status::success();
}

Status PropertyRegistry::replace_state(std::vector<DwellingRecord> records,
                                       std::vector<TitleEvent> events) {
    PropertyRegistry candidate;
    candidate.records_ = std::move(records);
    candidate.title_events_ = std::move(events);
    auto status = candidate.rebuild_indexes();
    if (!status.ok()) {
        return status;
    }
    status = candidate.validate();
    if (!status.ok()) {
        return status;
    }
    *this = std::move(candidate);
    return Status::success();
}

Status PropertyRegistry::rebuild_indexes() {
    owner_index_.clear();
    occupant_index_.clear();
    collateral_index_.clear();
    active_count_ = 0;
    destroyed_count_ = 0;
    for (const auto &record : records_) {
        if (record.active) {
            owner_index_[record.owner].push_back(record.id);
            if (record.occupant.valid() &&
                !occupant_index_.emplace(record.occupant, record.id).second) {
                return Status(ErrorCode::invariant_violation,
                              "duplicate dwelling occupant");
            }
            if (record.collateral.valid() &&
                !collateral_index_.emplace(record.collateral, record.id).second) {
                return Status(ErrorCode::invariant_violation,
                              "duplicate dwelling collateral");
            }
            ++active_count_;
        } else {
            ++destroyed_count_;
        }
    }
    return Status::success();
}

Status PropertyRegistry::append_title_event(TitleEvent event) {
    title_events_.push_back(event);
    return Status::success();
}

void PropertyRegistry::remove_owner_index(OwnerId owner, DwellingId dwelling) noexcept {
    const auto found = owner_index_.find(owner);
    if (found == owner_index_.end()) {
        return;
    }
    auto &dwellings = found->second;
    const auto position =
        std::lower_bound(dwellings.begin(), dwellings.end(), dwelling);
    if (position != dwellings.end() && *position == dwelling) {
        dwellings.erase(position);
    }
    if (dwellings.empty()) {
        owner_index_.erase(found);
    }
}

} // namespace macro_sim::core
