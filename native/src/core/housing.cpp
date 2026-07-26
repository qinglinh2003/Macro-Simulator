#include "macro_sim/core/housing.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace macro_sim::core {
namespace {

constexpr double kMinimumFloorArea = 1.0e-9;

template <typename Value>
[[nodiscard]] std::uint64_t capacity_bytes(const std::vector<Value> &values) noexcept {
    return static_cast<std::uint64_t>(values.capacity()) * sizeof(Value);
}

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
    if (spec.occupant.valid() &&
        dwelling_for_occupant(spec.occupant).valid()) {
        return Status(ErrorCode::already_exists,
                      "household already occupies a dwelling");
    }
    if (records_.size() >=
            static_cast<std::size_t>(DwellingId::max_valid_value()) ||
        title_events_.size() >=
            static_cast<std::size_t>(TitleEventId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "dwelling id space exhausted");
    }

    const auto id =
        DwellingId(static_cast<DwellingId::rep_type>(records_.size() + 1U));
    const auto event_id = TitleEventId(
        static_cast<TitleEventId::rep_type>(title_events_.size() + 1U));
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
    insert_owner_index(spec.owner, id);
    if (spec.occupant.valid()) {
        const auto occupant = static_cast<std::size_t>(spec.occupant.value());
        if (occupant_index_.size() <= occupant) {
            occupant_index_.resize(occupant + 1U, DwellingId{});
        }
        occupant_index_[occupant] = id;
        ++occupied_count_;
        if (spec.owner == OwnerId::household(spec.occupant)) {
            ++owner_occupied_count_;
        }
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
    if (!expected_owner.valid()) {
        return Status(ErrorCode::invalid_argument,
                      "title transfer source is invalid");
    }
    if (!next_owner.valid()) {
        return Status(ErrorCode::invalid_argument,
                      "title transfer destination is invalid");
    }
    if (expected_owner == next_owner) {
        return Status(ErrorCode::invalid_argument,
                      "title transfer source equals destination");
    }
    if (record->owner != expected_owner) {
        return Status(ErrorCode::stale_handle, "stale dwelling title");
    }
    if (tick < record->last_title_tick) {
        return Status(ErrorCode::invalid_argument,
                      "title transfer precedes prior event");
    }
    if (title_events_.size() >=
        static_cast<std::size_t>(TitleEventId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "title event id space exhausted");
    }

    if (record->occupant.valid()) {
        if (record->owner == OwnerId::household(record->occupant)) {
            --owner_occupied_count_;
        }
        if (next_owner == OwnerId::household(record->occupant)) {
            ++owner_occupied_count_;
        }
    }
    insert_owner_index(next_owner, dwelling);
    remove_owner_index(expected_owner, dwelling);
    record->owner = next_owner;
    record->last_title_tick = tick;
    return append_title_event({
        TitleEventId(
            static_cast<TitleEventId::rep_type>(title_events_.size() + 1U)),
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
    if (title_events_.size() >=
        static_cast<std::size_t>(TitleEventId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "title event id space exhausted");
    }

    remove_owner_index(expected_owner, dwelling);
    record->active = false;
    record->last_title_tick = tick;
    --active_count_;
    ++destroyed_count_;
    return append_title_event({
        TitleEventId(
            static_cast<TitleEventId::rep_type>(title_events_.size() + 1U)),
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
        dwelling_for_occupant(next_occupant).valid()) {
        return Status(ErrorCode::already_exists,
                      "household already occupies a dwelling");
    }
    if (expected_occupant.valid()) {
        --occupied_count_;
        if (record->owner == OwnerId::household(expected_occupant)) {
            --owner_occupied_count_;
        }
        occupant_index_[static_cast<std::size_t>(expected_occupant.value())] =
            DwellingId{};
    }
    if (next_occupant.valid()) {
        const auto occupant = static_cast<std::size_t>(next_occupant.value());
        if (occupant_index_.size() <= occupant) {
            occupant_index_.resize(occupant + 1U, DwellingId{});
        }
        occupant_index_[occupant] = dwelling;
        ++occupied_count_;
        if (record->owner == OwnerId::household(next_occupant)) {
            ++owner_occupied_count_;
        }
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
    if (dwelling_for_collateral(loan).valid()) {
        return Status(ErrorCode::already_exists, "loan already has collateral");
    }
    const auto loan_index = static_cast<std::size_t>(loan.value());
    if (collateral_index_.size() <= loan_index) {
        collateral_index_.resize(loan_index + 1U, DwellingId{});
    }
    collateral_index_[loan_index] = dwelling;
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
    collateral_index_[static_cast<std::size_t>(expected_loan.value())] =
        DwellingId{};
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
    if (!owner.valid()) {
        return {};
    }
    if (owner.kind == OwnerKind::household) {
        const auto household = HouseholdId(owner.value);
        const auto overflow = household_owner_overflow_.find(household);
        if (overflow != household_owner_overflow_.end()) {
            return overflow->second;
        }
        const auto index = static_cast<std::size_t>(owner.value);
        if (index >= household_owner_primary_.size() ||
            !household_owner_primary_[index].valid()) {
            return {};
        }
        return std::span<const DwellingId>(&household_owner_primary_[index], 1U);
    }
    const auto found = non_household_owner_index_.find(owner);
    return found == non_household_owner_index_.end()
               ? std::span<const DwellingId>{}
               : std::span<const DwellingId>(found->second);
}

DwellingId
PropertyRegistry::dwelling_for_occupant(HouseholdId household) const noexcept {
    if (!household.valid()) {
        return {};
    }
    const auto index = static_cast<std::size_t>(household.value());
    return index < occupant_index_.size() ? occupant_index_[index] : DwellingId{};
}

DwellingId PropertyRegistry::dwelling_for_collateral(LoanId loan) const noexcept {
    if (!loan.valid()) {
        return {};
    }
    const auto index = static_cast<std::size_t>(loan.value());
    return index < collateral_index_.size() ? collateral_index_[index]
                                            : DwellingId{};
}

std::size_t PropertyRegistry::active_count() const noexcept { return active_count_; }

std::size_t PropertyRegistry::minted_count() const noexcept { return records_.size(); }

std::size_t PropertyRegistry::destroyed_count() const noexcept {
    return destroyed_count_;
}

std::size_t PropertyRegistry::occupied_count() const noexcept {
    return occupied_count_;
}

std::size_t PropertyRegistry::owner_occupied_count() const noexcept {
    return owner_occupied_count_;
}

std::uint64_t PropertyRegistry::retained_bytes() const noexcept {
    std::uint64_t bytes = capacity_bytes(records_) + capacity_bytes(title_events_) +
                          capacity_bytes(household_owner_primary_) +
                          capacity_bytes(occupant_index_) +
                          capacity_bytes(collateral_index_);
    for (const auto &[owner, dwellings] : household_owner_overflow_) {
        static_cast<void>(owner);
        bytes += sizeof(decltype(household_owner_overflow_)::value_type) +
                 3U * sizeof(void *) + capacity_bytes(dwellings);
    }
    for (const auto &[owner, dwellings] : non_household_owner_index_) {
        static_cast<void>(owner);
        bytes += sizeof(decltype(non_household_owner_index_)::value_type) +
                 3U * sizeof(void *) + capacity_bytes(dwellings);
    }
    return bytes;
}

Status PropertyRegistry::validate_fast() const noexcept {
    if (active_count_ + destroyed_count_ != records_.size() ||
        title_events_.size() < records_.size() ||
        owner_occupied_count_ > occupied_count_ || occupied_count_ > active_count_) {
        return Status(ErrorCode::invariant_violation,
                      "invalid dwelling stock counters");
    }
    return Status::success();
}

Status PropertyRegistry::validate() const noexcept {
    auto status = validate_fast();
    if (!status.ok()) {
        return status;
    }

    std::size_t active = 0;
    std::size_t destroyed = 0;
    std::size_t occupied = 0;
    std::size_t owner_occupied = 0;
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
            const auto owner_dwellings = dwellings_for_owner(record.owner);
            if (std::count(owner_dwellings.begin(), owner_dwellings.end(),
                           record.id) != 1) {
                return Status(ErrorCode::invariant_violation,
                              "invalid dwelling owner index");
            }
            if (record.occupant.valid()) {
                ++occupied;
                owner_occupied +=
                    record.owner == OwnerId::household(record.occupant) ? 1U : 0U;
                if (dwelling_for_occupant(record.occupant) != record.id) {
                    return Status(ErrorCode::invariant_violation,
                                  "invalid dwelling occupant index");
                }
            }
            if (record.collateral.valid()) {
                if (dwelling_for_collateral(record.collateral) != record.id) {
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
            const auto owner_dwellings = dwellings_for_owner(record.owner);
            if (std::find(owner_dwellings.begin(), owner_dwellings.end(),
                          record.id) != owner_dwellings.end()) {
                return Status(ErrorCode::invariant_violation,
                              "inactive dwelling remains indexed");
            }
        }
    }
    if (active != active_count_ || destroyed != destroyed_count_ ||
        occupied != occupied_count_ || owner_occupied != owner_occupied_count_) {
        return Status(ErrorCode::invariant_violation,
                      "dwelling stock counter mismatch");
    }

    for (std::size_t index = 1U; index < household_owner_primary_.size(); ++index) {
        const auto dwelling = household_owner_primary_[index];
        if (!dwelling.valid()) {
            continue;
        }
        const auto household = HouseholdId(index);
        if (household_owner_overflow_.contains(household)) {
            return Status(ErrorCode::invariant_violation,
                          "household owner index has two representations");
        }
        const auto *record = get(dwelling);
        if (record == nullptr || !record->active ||
            record->owner != OwnerId::household(household)) {
            return Status(ErrorCode::invariant_violation,
                          "household owner index does not resolve");
        }
    }
    const auto validate_owner_rows = [this](
                                         OwnerId owner,
                                         const std::vector<DwellingId> &dwellings) {
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
        return Status::success();
    };
    for (const auto &[household, dwellings] : household_owner_overflow_) {
        if (!household.valid() ||
            static_cast<std::size_t>(household.value()) >=
                household_owner_primary_.size() ||
            household_owner_primary_[static_cast<std::size_t>(household.value())]
                .valid()) {
            return Status(ErrorCode::invariant_violation,
                          "invalid household owner overflow");
        }
        status = validate_owner_rows(OwnerId::household(household), dwellings);
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto &[owner, dwellings] : non_household_owner_index_) {
        if (owner.kind == OwnerKind::household) {
            return Status(ErrorCode::invariant_violation,
                          "household owner is in the sparse index");
        }
        status = validate_owner_rows(owner, dwellings);
        if (!status.ok()) {
            return status;
        }
    }
    for (std::size_t index = 1U; index < occupant_index_.size(); ++index) {
        const auto dwelling = occupant_index_[index];
        if (!dwelling.valid()) {
            continue;
        }
        const auto occupant = HouseholdId(index);
        const auto *record = get(dwelling);
        if (record == nullptr || !record->active ||
            record->occupant != occupant) {
            return Status(ErrorCode::invariant_violation,
                          "occupant index does not resolve");
        }
    }
    for (std::size_t index = 1U; index < collateral_index_.size(); ++index) {
        const auto dwelling = collateral_index_[index];
        if (!dwelling.valid()) {
            continue;
        }
        const auto loan = LoanId(index);
        const auto *record = get(dwelling);
        if (record == nullptr || !record->active ||
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
    household_owner_primary_.assign(1U, DwellingId{});
    household_owner_overflow_.clear();
    non_household_owner_index_.clear();
    occupant_index_.assign(1U, DwellingId{});
    collateral_index_.assign(1U, DwellingId{});
    active_count_ = 0;
    destroyed_count_ = 0;
    occupied_count_ = 0;
    owner_occupied_count_ = 0;
    for (const auto &record : records_) {
        if (record.active) {
            if (record.occupant.valid()) {
                const auto occupant =
                    static_cast<std::size_t>(record.occupant.value());
                if (occupant_index_.size() <= occupant) {
                    occupant_index_.resize(occupant + 1U, DwellingId{});
                }
                if (occupant_index_[occupant].valid()) {
                    return Status(ErrorCode::invariant_violation,
                                  "duplicate dwelling occupant");
                }
                occupant_index_[occupant] = record.id;
                ++occupied_count_;
                owner_occupied_count_ +=
                    record.owner == OwnerId::household(record.occupant) ? 1U : 0U;
            }
            if (record.collateral.valid()) {
                const auto loan =
                    static_cast<std::size_t>(record.collateral.value());
                if (collateral_index_.size() <= loan) {
                    collateral_index_.resize(loan + 1U, DwellingId{});
                }
                if (collateral_index_[loan].valid()) {
                    return Status(ErrorCode::invariant_violation,
                                  "duplicate dwelling collateral");
                }
                collateral_index_[loan] = record.id;
            }
            insert_owner_index(record.owner, record.id);
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

void PropertyRegistry::insert_owner_index(OwnerId owner, DwellingId dwelling) {
    if (owner.kind != OwnerKind::household) {
        auto &dwellings = non_household_owner_index_[owner];
        dwellings.insert(
            std::lower_bound(dwellings.begin(), dwellings.end(), dwelling),
            dwelling);
        return;
    }
    const auto household = HouseholdId(owner.value);
    const auto index = static_cast<std::size_t>(owner.value);
    if (household_owner_primary_.size() <= index) {
        household_owner_primary_.resize(index + 1U, DwellingId{});
    }
    const auto overflow = household_owner_overflow_.find(household);
    if (overflow != household_owner_overflow_.end()) {
        auto &dwellings = overflow->second;
        dwellings.insert(
            std::lower_bound(dwellings.begin(), dwellings.end(), dwelling),
            dwelling);
        return;
    }
    if (!household_owner_primary_[index].valid()) {
        household_owner_primary_[index] = dwelling;
        return;
    }
    std::vector<DwellingId> dwellings{
        household_owner_primary_[index],
        dwelling,
    };
    std::sort(dwellings.begin(), dwellings.end());
    household_owner_primary_[index] = DwellingId{};
    household_owner_overflow_.emplace(household, std::move(dwellings));
}

void PropertyRegistry::remove_owner_index(OwnerId owner, DwellingId dwelling) noexcept {
    if (owner.kind == OwnerKind::household) {
        const auto household = HouseholdId(owner.value);
        const auto index = static_cast<std::size_t>(owner.value);
        const auto overflow = household_owner_overflow_.find(household);
        if (overflow == household_owner_overflow_.end()) {
            if (index < household_owner_primary_.size() &&
                household_owner_primary_[index] == dwelling) {
                household_owner_primary_[index] = DwellingId{};
            }
            return;
        }
        auto &dwellings = overflow->second;
        const auto position =
            std::lower_bound(dwellings.begin(), dwellings.end(), dwelling);
        if (position != dwellings.end() && *position == dwelling) {
            dwellings.erase(position);
        }
        if (dwellings.size() == 1U) {
            household_owner_primary_[index] = dwellings.front();
            household_owner_overflow_.erase(overflow);
        } else if (dwellings.empty()) {
            household_owner_overflow_.erase(overflow);
        }
        return;
    }
    const auto found = non_household_owner_index_.find(owner);
    if (found == non_household_owner_index_.end()) {
        return;
    }
    auto &dwellings = found->second;
    const auto position =
        std::lower_bound(dwellings.begin(), dwellings.end(), dwelling);
    if (position != dwellings.end() && *position == dwelling) {
        dwellings.erase(position);
    }
    if (dwellings.empty()) {
        non_household_owner_index_.erase(found);
    }
}

} // namespace macro_sim::core
