#include "macro_sim/core/population.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace macro_sim::core {

namespace {

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

} // namespace

Result<PersonId> PersonStore::create(PersonRecord person) {
    if (next_id_ == std::numeric_limits<std::uint64_t>::max()) {
        return Status(ErrorCode::out_of_range, "person ID space exhausted");
    }
    if (person.id.valid() || !finite(person.efficiency) || person.efficiency <= 0.0 ||
        person.death_day >= 0 || !person.alive) {
        return Status(ErrorCode::invalid_argument, "person genesis record is invalid");
    }
    const auto id = PersonId(next_id_++);
    person.id = id;
    records_.push_back(std::move(person));
    alive_dense_by_id_.push_back(alive_ids_.size());
    alive_ids_.push_back(id);
    return id;
}

Status PersonStore::mark_dead(PersonId id, std::int32_t day) {
    auto *person = get(id);
    if (person == nullptr) {
        return Status(ErrorCode::not_found, "person is absent");
    }
    if (!person->alive) {
        return Status(ErrorCode::contract_violation,
                      "person death was already recorded");
    }
    const auto index = static_cast<std::size_t>(id.value());
    const auto dense = alive_dense_by_id_[index];
    if (dense == kNoDense || dense >= alive_ids_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "person alive index is inconsistent");
    }
    const auto moved = alive_ids_.back();
    alive_ids_[dense] = moved;
    alive_ids_.pop_back();
    alive_dense_by_id_[static_cast<std::size_t>(moved.value())] = dense;
    alive_dense_by_id_[index] = kNoDense;
    person->alive = false;
    person->death_day = day;
    archive_ids_.push_back(id);
    return Status::success();
}

PersonRecord *PersonStore::get(PersonId id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= records_.size()) {
        return nullptr;
    }
    return &records_[static_cast<std::size_t>(id.value())];
}

const PersonRecord *PersonStore::get(PersonId id) const noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= records_.size()) {
        return nullptr;
    }
    return &records_[static_cast<std::size_t>(id.value())];
}

bool PersonStore::contains(PersonId id) const noexcept { return get(id) != nullptr; }

bool PersonStore::alive(PersonId id) const noexcept {
    const auto *person = get(id);
    return person != nullptr && person->alive;
}

std::size_t PersonStore::alive_count() const noexcept { return alive_ids_.size(); }

std::size_t PersonStore::archived_count() const noexcept { return archive_ids_.size(); }

std::size_t PersonStore::total_count() const noexcept { return records_.size() - 1; }

std::uint64_t PersonStore::next_id() const noexcept { return next_id_; }

std::span<const PersonId> PersonStore::alive_ids() const noexcept { return alive_ids_; }

std::span<const PersonId> PersonStore::archive_ids() const noexcept {
    return archive_ids_;
}

const std::vector<PersonRecord> &PersonStore::records() const noexcept {
    return records_;
}

Status PersonStore::replace_records(std::vector<PersonRecord> records) {
    if (records.empty()) {
        return Status(ErrorCode::corrupt_input, "person checkpoint records are empty");
    }
    records_ = std::move(records);
    alive_ids_.clear();
    archive_ids_.clear();
    alive_dense_by_id_.assign(records_.size(), kNoDense);
    for (std::size_t index = 1; index < records_.size(); ++index) {
        const auto id = PersonId(index);
        if (records_[index].id != id) {
            return Status(ErrorCode::corrupt_input,
                          "person checkpoint identity is invalid");
        }
        if (records_[index].alive) {
            alive_dense_by_id_[index] = alive_ids_.size();
            alive_ids_.push_back(id);
        } else {
            archive_ids_.push_back(id);
        }
    }
    next_id_ = records_.size();
    return validate();
}

Status PersonStore::validate() const noexcept {
    if (records_.empty() || alive_dense_by_id_.size() != records_.size() ||
        next_id_ != records_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "person store dimensions are inconsistent");
    }
    std::vector<std::uint8_t> seen(records_.size(), 0U);
    for (std::size_t dense = 0; dense < alive_ids_.size(); ++dense) {
        const auto id = alive_ids_[dense];
        const auto *person = get(id);
        if (person == nullptr || !person->alive ||
            alive_dense_by_id_[static_cast<std::size_t>(id.value())] != dense ||
            seen[static_cast<std::size_t>(id.value())] != 0U) {
            return Status(ErrorCode::invariant_violation,
                          "person alive view is inconsistent");
        }
        seen[static_cast<std::size_t>(id.value())] = 1U;
    }
    for (const auto id : archive_ids_) {
        const auto *person = get(id);
        if (person == nullptr || person->alive || person->death_day < 0 ||
            alive_dense_by_id_[static_cast<std::size_t>(id.value())] != kNoDense ||
            seen[static_cast<std::size_t>(id.value())] != 0U) {
            return Status(ErrorCode::invariant_violation,
                          "person archive is inconsistent");
        }
        seen[static_cast<std::size_t>(id.value())] = 1U;
    }
    for (std::size_t index = 1; index < records_.size(); ++index) {
        const auto &person = records_[index];
        if (person.id.value() != index || !finite(person.efficiency) ||
            person.efficiency <= 0.0 || seen[index] != 1U ||
            (person.alive && person.death_day >= 0) ||
            (!person.alive && person.death_day < 0)) {
            return Status(ErrorCode::invariant_violation,
                          "person record is inconsistent");
        }
    }
    return Status::success();
}

void HouseholdMembershipBook::ensure_person(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1;
    if (household_by_person_.size() < size) {
        household_by_person_.resize(size);
    }
}

void HouseholdMembershipBook::ensure_household(HouseholdId household) {
    const auto size = static_cast<std::size_t>(household.value()) + 1;
    if (members_by_household_.size() < size) {
        members_by_household_.resize(size);
    }
}

Status HouseholdMembershipBook::add(PersonId person, HouseholdId household) {
    if (!person.valid() || person.value() == 0 || !household.valid() ||
        household.value() == 0) {
        return Status(ErrorCode::invalid_argument, "membership identity is invalid");
    }
    ensure_person(person);
    ensure_household(household);
    if (household_by_person_[static_cast<std::size_t>(person.value())].valid()) {
        return Status(ErrorCode::contract_violation, "person already has a household");
    }
    household_by_person_[static_cast<std::size_t>(person.value())] = household;
    auto &members = members_by_household_[static_cast<std::size_t>(household.value())];
    members.insert(std::lower_bound(members.begin(), members.end(), person), person);
    return Status::success();
}

Status HouseholdMembershipBook::move(PersonId person, HouseholdId household) {
    if (!person.valid() || person.value() == 0 || !household.valid() ||
        household.value() == 0) {
        return Status(ErrorCode::invalid_argument, "membership identity is invalid");
    }
    const auto current = household_of(person);
    if (!current.valid()) {
        return add(person, household);
    }
    if (current == household) {
        return Status::success();
    }
    auto status = remove(person);
    if (!status.ok()) {
        return status;
    }
    return add(person, household);
}

Status HouseholdMembershipBook::remove(PersonId person) {
    const auto household = household_of(person);
    if (!household.valid()) {
        return Status(ErrorCode::not_found, "person membership is absent");
    }
    auto &members = members_by_household_[static_cast<std::size_t>(household.value())];
    const auto found = std::find(members.begin(), members.end(), person);
    if (found == members.end()) {
        return Status(ErrorCode::invariant_violation,
                      "household member index is inconsistent");
    }
    members.erase(found);
    household_by_person_[static_cast<std::size_t>(person.value())] = HouseholdId{};
    return Status::success();
}

HouseholdId HouseholdMembershipBook::household_of(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= household_by_person_.size()) {
        return HouseholdId{};
    }
    return household_by_person_[static_cast<std::size_t>(person.value())];
}

std::span<const PersonId>
HouseholdMembershipBook::members(HouseholdId household) const noexcept {
    if (!household.valid() || household.value() == 0 ||
        household.value() >= members_by_household_.size()) {
        return {};
    }
    return members_by_household_[static_cast<std::size_t>(household.value())];
}

std::size_t HouseholdMembershipBook::household_capacity() const noexcept {
    return members_by_household_.size();
}

Status HouseholdMembershipBook::validate(const PersonStore &persons,
                                         const RootState &state) const {
    std::vector<std::uint8_t> seen(persons.next_id(), 0U);
    for (std::size_t household_index = 1;
         household_index < members_by_household_.size(); ++household_index) {
        const auto household = HouseholdId(household_index);
        const auto &members = members_by_household_[household_index];
        if (!members.empty() && state.households.get(household) == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "membership references an absent household");
        }
        if (!std::is_sorted(members.begin(), members.end())) {
            return Status(ErrorCode::invariant_violation,
                          "household member order is not canonical");
        }
        for (const auto person : members) {
            if (!persons.alive(person) || person.value() >= seen.size() ||
                seen[static_cast<std::size_t>(person.value())] != 0U ||
                household_of(person) != household) {
                return Status(ErrorCode::invariant_violation,
                              "membership projection is inconsistent");
            }
            seen[static_cast<std::size_t>(person.value())] = 1U;
        }
    }
    for (const auto person : persons.alive_ids()) {
        const auto record = persons.get(person);
        const auto household = household_of(person);
        if (record == nullptr || !household.valid() || record->household != household ||
            seen[static_cast<std::size_t>(person.value())] != 1U) {
            return Status(ErrorCode::invariant_violation,
                          "alive person is not projected exactly once");
        }
    }
    return Status::success();
}

Status HouseholdMembershipBook::rebuild(const PersonStore &persons) {
    household_by_person_.assign(1, HouseholdId{});
    members_by_household_.assign(1, std::vector<PersonId>{});
    for (const auto person : persons.alive_ids()) {
        const auto *record = persons.get(person);
        const auto status = add(person, record->household);
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

void BeneficialOwnershipBook::ensure_unique_indexes() {
    if (indexes_.use_count() != 1) {
        indexes_ = std::make_shared<Indexes>(*indexes_);
    }
}

void BeneficialOwnershipBook::ensure_person_links(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1U;
    if (indexes_->person_heads.size() < size) {
        indexes_->person_heads.resize(size, 0U);
        indexes_->person_tails.resize(size, 0U);
    }
}

void BeneficialOwnershipBook::append_person_lot(BeneficialLotId lot,
                                                PersonId person) {
    ensure_person_links(person);
    const auto person_index = static_cast<std::size_t>(person.value());
    const auto lot_index = static_cast<std::size_t>(lot.value() - 1U);
    const auto encoded_lot = static_cast<std::uint32_t>(lot.value());
    const auto tail = indexes_->person_tails[person_index];
    indexes_->person_previous[lot_index] = tail;
    indexes_->person_next[lot_index] = 0U;
    if (tail == 0U) {
        indexes_->person_heads[person_index] = encoded_lot;
    } else {
        indexes_->person_next[static_cast<std::size_t>(tail - 1U)] =
            encoded_lot;
    }
    indexes_->person_tails[person_index] = encoded_lot;
    indexes_->person_index_dirty = true;
}

Status BeneficialOwnershipBook::unlink_person_lot(BeneficialLotId lot,
                                                  PersonId person) {
    const auto person_index = static_cast<std::size_t>(person.value());
    const auto lot_index = static_cast<std::size_t>(lot.value() - 1U);
    if (person_index >= indexes_->person_heads.size() ||
        lot_index >= indexes_->person_next.size()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial owner index is inconsistent");
    }
    const auto previous = indexes_->person_previous[lot_index];
    const auto next = indexes_->person_next[lot_index];
    if (previous == 0U) {
        if (indexes_->person_heads[person_index] != lot.value()) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial owner index is inconsistent");
        }
        indexes_->person_heads[person_index] = next;
    } else {
        indexes_->person_next[static_cast<std::size_t>(previous - 1U)] = next;
    }
    if (next == 0U) {
        if (indexes_->person_tails[person_index] != lot.value()) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial owner index is inconsistent");
        }
        indexes_->person_tails[person_index] = previous;
    } else {
        indexes_->person_previous[static_cast<std::size_t>(next - 1U)] =
            previous;
    }
    indexes_->person_previous[lot_index] = 0U;
    indexes_->person_next[lot_index] = 0U;
    indexes_->person_index_dirty = true;
    return Status::success();
}

void BeneficialOwnershipBook::rebuild_person_index() const {
    if (!indexes_->person_index_dirty) {
        return;
    }
    auto &offsets = indexes_->person_offsets;
    offsets.assign(indexes_->person_heads.size() + 1U, 0U);
    auto &flat = indexes_->lots_by_person;
    flat.clear();
    flat.reserve(lots_.size());
    for (std::size_t person = 0U;
         person < indexes_->person_heads.size(); ++person) {
        offsets[person] = flat.size();
        auto lot = indexes_->person_heads[person];
        std::size_t traversed = 0U;
        while (lot != 0U) {
            flat.push_back(BeneficialLotId(lot));
            lot = indexes_->person_next[static_cast<std::size_t>(lot - 1U)];
            if (++traversed > lots_.size()) {
                break;
            }
        }
    }
    offsets.back() = flat.size();
    indexes_->person_index_dirty = false;
}

void BeneficialOwnershipBook::rebuild_asset_lot_index() const {
    if (!indexes_->asset_lot_index_dirty) {
        return;
    }
    auto &offsets = indexes_->asset_offsets;
    offsets.assign(indexes_->lots_by_asset.size() + 1U, 0U);
    std::size_t indexed_lots = 0U;
    for (std::size_t index = 0U;
         index < indexes_->asset_row_by_lot.size(); ++index) {
        if (indexes_->asset_lot_indexed[index] == 0U) {
            continue;
        }
        const auto row = indexes_->asset_row_by_lot[index];
        ++offsets[static_cast<std::size_t>(row) + 1U];
        ++indexed_lots;
    }
    for (std::size_t index = 1U; index < offsets.size(); ++index) {
        offsets[index] += offsets[index - 1U];
    }
    auto cursor = offsets;
    auto &flat = indexes_->lots_by_asset_flat;
    flat.resize(indexed_lots);
    for (std::size_t index = 0U; index < lots_.size(); ++index) {
        if (indexes_->asset_lot_indexed[index] == 0U) {
            continue;
        }
        const auto row =
            static_cast<std::size_t>(indexes_->asset_row_by_lot[index]);
        flat[cursor[row]++] = lots_[index].id;
    }
    indexes_->asset_lot_index_dirty = false;
}

std::size_t BeneficialOwnershipBook::asset_hash(BeneficialAssetKey asset) noexcept {
    const auto mix = [](std::uint64_t value) {
        value += 0x9e3779b97f4a7c15ULL;
        value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31U);
    };
    std::uint64_t hash =
        mix(static_cast<std::uint64_t>(static_cast<std::uint8_t>(asset.kind)));
    hash ^= mix(asset.household.value() + 0x517cc1b727220a95ULL);
    hash ^= mix(asset.value + 0x6eed0e9da4d94a4fULL);
    return static_cast<std::size_t>(hash);
}

std::size_t
BeneficialOwnershipBook::find_asset_row(BeneficialAssetKey asset) const noexcept {
    if (asset.kind == BeneficialAssetKind::household_cash &&
        asset.value == asset.household.value() &&
        asset.household.value() < indexes_->canonical_cash_rows.size()) {
        const auto encoded = indexes_->canonical_cash_rows[
            static_cast<std::size_t>(asset.household.value())];
        if (encoded != 0U) {
            return static_cast<std::size_t>(encoded - 1U);
        }
    }
    if (indexes_->asset_slots.empty()) {
        return kMissingAssetRow;
    }
    const auto mask = indexes_->asset_slots.size() - 1U;
    auto slot = asset_hash(asset) & mask;
    while (indexes_->asset_slots[slot] != 0U) {
        const auto row = indexes_->asset_slots[slot] - 1U;
        if (indexes_->lots_by_asset[row].asset == asset) {
            return row;
        }
        slot = (slot + 1U) & mask;
    }
    return kMissingAssetRow;
}

void BeneficialOwnershipBook::rebuild_asset_slots(std::size_t minimum_rows) {
    const auto required_rows =
        std::max(minimum_rows, indexes_->lots_by_asset.size());
    std::size_t capacity = 8U;
    while (capacity < required_rows * 2U) {
        capacity *= 2U;
    }
    indexes_->asset_slots.assign(capacity, 0U);
    const auto mask = capacity - 1U;
    for (std::size_t row = 0; row < indexes_->lots_by_asset.size(); ++row) {
        auto slot = asset_hash(indexes_->lots_by_asset[row].asset) & mask;
        while (indexes_->asset_slots[slot] != 0U) {
            slot = (slot + 1U) & mask;
        }
        indexes_->asset_slots[slot] = row + 1U;
    }
}

std::size_t BeneficialOwnershipBook::ensure_asset_row(BeneficialAssetKey asset) {
    const auto existing = find_asset_row(asset);
    if (existing != kMissingAssetRow) {
        return existing;
    }
    if (indexes_->asset_slots.empty() ||
        (indexes_->lots_by_asset.size() + 1U) * 10U >=
            indexes_->asset_slots.size() * 7U) {
        rebuild_asset_slots(indexes_->lots_by_asset.size() + 1U);
    }
    const auto row = indexes_->lots_by_asset.size();
    indexes_->lots_by_asset.push_back({asset, 0U});
    const auto mask = indexes_->asset_slots.size() - 1U;
    auto slot = asset_hash(asset) & mask;
    while (indexes_->asset_slots[slot] != 0U) {
        slot = (slot + 1U) & mask;
    }
    indexes_->asset_slots[slot] = row + 1U;
    if (asset.kind == BeneficialAssetKind::household_cash &&
        asset.value == asset.household.value() &&
        row < std::numeric_limits<std::uint32_t>::max() &&
        asset.household.value() <=
            static_cast<std::uint64_t>(
                std::numeric_limits<std::uint32_t>::max())) {
        const auto household =
            static_cast<std::size_t>(asset.household.value());
        if (indexes_->canonical_cash_rows.size() <= household) {
            indexes_->canonical_cash_rows.resize(household + 1U, 0U);
        }
        indexes_->canonical_cash_rows[household] =
            static_cast<std::uint32_t>(row + 1U);
    }
    return row;
}

Result<BeneficialLotId> BeneficialOwnershipBook::create_lot(BeneficialAssetKey asset,
                                                            PersonId owner,
                                                            double share) {
    if (!asset.household.valid() || asset.household.value() == 0 || !owner.valid() ||
        owner.value() == 0 || !finite(share) || share <= 0.0 || share > 1.0) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership lot is invalid");
    }
    if (lots_.size() >= std::numeric_limits<std::uint32_t>::max()) {
        return Status(ErrorCode::out_of_range,
                      "beneficial ownership lot index exceeds storage range");
    }
    ensure_unique_indexes();
    const auto asset_row = ensure_asset_row(asset);
    if (asset_row >= std::numeric_limits<std::uint32_t>::max()) {
        return Status(ErrorCode::out_of_range,
                      "beneficial asset index exceeds storage range");
    }
    const auto id = BeneficialLotId(lots_.size() + 1);
    lots_.push_back({id, asset, owner, share, true});
    indexes_->asset_row_by_lot.push_back(
        static_cast<std::uint32_t>(asset_row));
    indexes_->asset_lot_indexed.push_back(1U);
    indexes_->person_next.push_back(0U);
    indexes_->person_previous.push_back(0U);
    append_person_lot(id, owner);
    ++indexes_->lots_by_asset[asset_row].active_lots;
    indexes_->asset_lot_index_dirty = true;
    indexes_->validation_dirty_lots.push_back(id);
    indexes_->validation_dirty_asset_rows.push_back(asset_row);
    return id;
}

Status BeneficialOwnershipBook::transfer(BeneficialLotId lot, PersonId destination,
                                         double share) {
    auto *source = get(lot);
    if (source == nullptr || !source->active) {
        return Status(ErrorCode::not_found, "beneficial ownership lot is absent");
    }
    if (!destination.valid() || destination.value() == 0 || !finite(share) ||
        share <= 0.0 || share > source->share) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership transfer is invalid");
    }
    ensure_unique_indexes();
    const auto asset_row = find_asset_row(source->asset);
    if (asset_row == kMissingAssetRow) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset index is inconsistent");
    }
    const double remaining = source->share - share;
    if (remaining <= 1.0e-15) {
        const auto unlinked = unlink_person_lot(lot, source->owner);
        if (!unlinked.ok()) {
            return unlinked;
        }
        source->owner = destination;
        append_person_lot(lot, destination);
        indexes_->validation_dirty_lots.push_back(lot);
        indexes_->validation_dirty_asset_rows.push_back(asset_row);
        return Status::success();
    }
    source->share = remaining;
    indexes_->validation_dirty_lots.push_back(lot);
    indexes_->validation_dirty_asset_rows.push_back(asset_row);
    const auto created = create_lot(source->asset, destination, share);
    return created.ok() ? Status::success() : created.status();
}

Status BeneficialOwnershipBook::retire(BeneficialLotId lot) {
    auto *record = get(lot);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "beneficial ownership lot is absent");
    }
    ensure_unique_indexes();
    const auto asset_row = find_asset_row(record->asset);
    if (asset_row == kMissingAssetRow ||
        indexes_->lots_by_asset[asset_row].active_lots == 0U) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset index is inconsistent");
    }
    const auto unlinked = unlink_person_lot(lot, record->owner);
    if (!unlinked.ok()) {
        return unlinked;
    }
    --indexes_->lots_by_asset[asset_row].active_lots;
    record->active = false;
    record->share = 0.0;
    indexes_->validation_dirty_lots.push_back(lot);
    indexes_->validation_dirty_asset_rows.push_back(asset_row);
    return Status::success();
}

Status BeneficialOwnershipBook::retire_asset(BeneficialAssetKey asset) {
    const auto row = find_asset_row(asset);
    if (row == kMissingAssetRow) {
        return Status::success();
    }
    ensure_unique_indexes();
    const auto indexed_lots = lots_for_asset(asset);
    const std::vector<BeneficialLotId> lots(indexed_lots.begin(),
                                            indexed_lots.end());
    for (const auto lot : lots) {
        const auto *record = get(lot);
        if (record == nullptr || !record->active) {
            continue;
        }
        const auto status = retire(lot);
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto lot : lots) {
        indexes_->asset_lot_indexed[
            static_cast<std::size_t>(lot.value() - 1U)] = 0U;
    }
    indexes_->asset_lot_index_dirty = true;
    indexes_->lots_by_asset[row].active_lots = 0U;
    return Status::success();
}

Status BeneficialOwnershipBook::retire_household(HouseholdId household) {
    if (!household.valid()) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial household retirement is invalid");
    }
    std::vector<BeneficialAssetKey> assets;
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.asset.household == household && row.active_lots != 0U) {
            assets.push_back(row.asset);
        }
    }
    for (const auto asset : assets) {
        const auto status = retire_asset(asset);
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

Status BeneficialOwnershipBook::rekey_household(HouseholdId source,
                                                HouseholdId destination) {
    if (!source.valid() || !destination.valid() || source == destination) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial household rekey is invalid");
    }
    std::vector<BeneficialAssetKey> source_assets;
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.asset.household == source && row.active_lots != 0U) {
            source_assets.push_back(row.asset);
        }
    }
    for (const auto source_asset : source_assets) {
        auto destination_asset = source_asset;
        destination_asset.household = destination;
        if (contains_asset(destination_asset)) {
            return Status(ErrorCode::already_exists,
                          "beneficial destination asset already exists");
        }
        const auto source_row = find_asset_row(source_asset);
        if (source_row == kMissingAssetRow) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial source asset is absent");
        }
        ensure_unique_indexes();
        const auto active_lots = indexes_->lots_by_asset[source_row].active_lots;
        const auto indexed_lots = lots_for_asset(source_asset);
        std::vector<BeneficialLotId> source_lots(indexed_lots.begin(),
                                                 indexed_lots.end());
        const auto destination_row = ensure_asset_row(destination_asset);
        if (destination_row >= std::numeric_limits<std::uint32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "beneficial asset index exceeds storage range");
        }
        std::uint32_t moved_lots = 0U;
        for (const auto lot : source_lots) {
            auto *record = get(lot);
            if (record == nullptr || !record->active) {
                continue;
            }
            record->asset = destination_asset;
            indexes_->asset_row_by_lot[
                static_cast<std::size_t>(lot.value() - 1U)] =
                static_cast<std::uint32_t>(destination_row);
            ++moved_lots;
            indexes_->validation_dirty_lots.push_back(lot);
        }
        if (moved_lots != active_lots) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial source asset index is inconsistent");
        }
        indexes_->lots_by_asset[source_row].active_lots = 0U;
        indexes_->lots_by_asset[destination_row].active_lots = active_lots;
        indexes_->asset_lot_index_dirty = true;
        indexes_->validation_dirty_asset_rows.push_back(source_row);
        indexes_->validation_dirty_asset_rows.push_back(destination_row);
    }
    return Status::success();
}

bool BeneficialOwnershipBook::contains_asset(BeneficialAssetKey asset) const noexcept {
    const auto row = find_asset_row(asset);
    if (row == kMissingAssetRow) {
        return false;
    }
    return indexes_->lots_by_asset[row].active_lots != 0U;
}

std::span<const BeneficialLotId>
BeneficialOwnershipBook::lots_for_asset(BeneficialAssetKey asset) const {
    const auto row = find_asset_row(asset);
    if (row == kMissingAssetRow) {
        return {};
    }
    rebuild_asset_lot_index();
    const auto begin = indexes_->asset_offsets[row];
    const auto end = indexes_->asset_offsets[row + 1U];
    if (begin == end) {
        return {};
    }
    return std::span<const BeneficialLotId>(
        indexes_->lots_by_asset_flat.data() + begin, end - begin);
}

BeneficialLot *BeneficialOwnershipBook::get(BeneficialLotId id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > lots_.size()) {
        return nullptr;
    }
    return &lots_[static_cast<std::size_t>(id.value() - 1)];
}

const BeneficialLot *BeneficialOwnershipBook::get(BeneficialLotId id) const noexcept {
    if (!id.valid() || id.value() == 0 || id.value() > lots_.size()) {
        return nullptr;
    }
    return &lots_[static_cast<std::size_t>(id.value() - 1)];
}

std::span<const BeneficialLotId>
BeneficialOwnershipBook::lots_for_person(PersonId person) const {
    if (!person.valid() || person.value() == 0) {
        return {};
    }
    rebuild_person_index();
    const auto index = static_cast<std::size_t>(person.value());
    if (index + 1U >= indexes_->person_offsets.size()) {
        return {};
    }
    const auto begin = indexes_->person_offsets[index];
    const auto end = indexes_->person_offsets[index + 1U];
    if (begin == end) {
        return {};
    }
    return std::span<const BeneficialLotId>(
        indexes_->lots_by_person.data() + begin, end - begin);
}

const std::vector<BeneficialLot> &BeneficialOwnershipBook::records() const noexcept {
    return lots_;
}

std::size_t BeneficialOwnershipBook::size() const noexcept { return lots_.size(); }

void BeneficialOwnershipBook::active_assets(
    std::vector<BeneficialAssetKey> &output) const {
    output.clear();
    output.reserve(indexes_->lots_by_asset.size());
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.active_lots != 0U) {
            output.push_back(row.asset);
        }
    }
}

double BeneficialOwnershipBook::maximum_projection_error() const {
    double maximum_error = 0.0;
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.active_lots == 0U) {
            continue;
        }
        double total = 0.0;
        for (const auto lot_id : lots_for_asset(row.asset)) {
            const auto *lot = get(lot_id);
            if (lot != nullptr && lot->active) {
                total += lot->share;
            }
        }
        maximum_error = std::max(maximum_error, std::abs(total - 1.0));
    }
    return maximum_error;
}

Status BeneficialOwnershipBook::replace_records(std::vector<BeneficialLot> records) {
    lots_ = std::move(records);
    if (lots_.size() > std::numeric_limits<std::uint32_t>::max()) {
        return Status(ErrorCode::out_of_range,
                      "beneficial ownership lot index exceeds storage range");
    }
    indexes_ = std::make_shared<Indexes>();
    indexes_->lots_by_asset.reserve(lots_.size());
    indexes_->asset_row_by_lot.reserve(lots_.size());
    indexes_->asset_lot_indexed.reserve(lots_.size());
    indexes_->person_next.reserve(lots_.size());
    indexes_->person_previous.reserve(lots_.size());
    rebuild_asset_slots(lots_.size());
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        auto &lot = lots_[index];
        if (lot.id != BeneficialLotId(index + 1U)) {
            return Status(ErrorCode::corrupt_input,
                          "beneficial checkpoint identity is invalid");
        }
        indexes_->person_next.push_back(0U);
        indexes_->person_previous.push_back(0U);
        if (!lot.active) {
            indexes_->asset_row_by_lot.push_back(
                std::numeric_limits<std::uint32_t>::max());
            indexes_->asset_lot_indexed.push_back(0U);
            continue;
        }
        const auto asset_row = ensure_asset_row(lot.asset);
        if (asset_row >= std::numeric_limits<std::uint32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "beneficial asset index exceeds storage range");
        }
        indexes_->asset_row_by_lot.push_back(
            static_cast<std::uint32_t>(asset_row));
        indexes_->asset_lot_indexed.push_back(1U);
        append_person_lot(lot.id, lot.owner);
        ++indexes_->lots_by_asset[asset_row].active_lots;
    }
    return Status::success();
}

Status BeneficialOwnershipBook::validate_fast(const PersonStore &persons,
                                              double tolerance) const {
    if (!finite(tolerance) || tolerance < 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership tolerance is invalid");
    }
    auto &dirty_lots = indexes_->validation_dirty_lots;
    auto &dirty_rows = indexes_->validation_dirty_asset_rows;
    const auto validate_lot = [&](BeneficialLotId lot_id) {
        const auto *lot = get(lot_id);
        if (lot == nullptr || lot->id != lot_id ||
            (!lot->active && lot->share != 0.0) ||
            (lot->active &&
             (!persons.alive(lot->owner) || !finite(lot->share) ||
              lot->share <= 0.0))) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership lot is inconsistent");
        }
        return Status::success();
    };
    const auto validate_row = [&](std::size_t row_index) {
        if (row_index >= indexes_->lots_by_asset.size()) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset index is inconsistent");
        }
        const auto &row = indexes_->lots_by_asset[row_index];
        if (find_asset_row(row.asset) != row_index) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lookup index is inconsistent");
        }
        double total = 0.0;
        std::uint32_t active_lots = 0U;
        for (const auto lot_id : lots_for_asset(row.asset)) {
            const auto *lot = get(lot_id);
            if (lot == nullptr || lot->asset != row.asset) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial asset index is inconsistent");
            }
            if (lot->active) {
                total += lot->share;
                ++active_lots;
            }
        }
        if (active_lots != row.active_lots ||
            (active_lots != 0U && std::abs(total - 1.0) > tolerance)) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership projection is inconsistent");
        }
        return Status::success();
    };

    if (indexes_->full_validation_required) {
        for (std::size_t index = 0; index < lots_.size(); ++index) {
            const auto status = validate_lot(BeneficialLotId(index + 1U));
            if (!status.ok()) {
                return status;
            }
        }
        for (std::size_t row_index = 0;
             row_index < indexes_->lots_by_asset.size(); ++row_index) {
            const auto status = validate_row(row_index);
            if (!status.ok()) {
                return status;
            }
        }
    } else {
        std::sort(dirty_lots.begin(), dirty_lots.end());
        dirty_lots.erase(std::unique(dirty_lots.begin(), dirty_lots.end()),
                         dirty_lots.end());
        for (const auto lot_id : dirty_lots) {
            const auto status = validate_lot(lot_id);
            if (!status.ok()) {
                return status;
            }
        }
        std::sort(dirty_rows.begin(), dirty_rows.end());
        dirty_rows.erase(std::unique(dirty_rows.begin(), dirty_rows.end()),
                         dirty_rows.end());
        for (const auto row_index : dirty_rows) {
            const auto status = validate_row(row_index);
            if (!status.ok()) {
                return status;
            }
        }
    }
    dirty_lots.clear();
    dirty_rows.clear();
    indexes_->full_validation_required = false;
    return Status::success();
}

Status BeneficialOwnershipBook::validate(const PersonStore &persons,
                                         double tolerance) const {
    if (!finite(tolerance) || tolerance < 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership tolerance is invalid");
    }
    if (indexes_->asset_row_by_lot.size() != lots_.size() ||
        indexes_->asset_lot_indexed.size() != lots_.size() ||
        indexes_->person_next.size() != lots_.size() ||
        indexes_->person_previous.size() != lots_.size() ||
        indexes_->person_heads.size() != indexes_->person_tails.size()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset lot index is inconsistent");
    }
    rebuild_person_index();
    rebuild_asset_lot_index();
    std::vector<std::uint8_t> indexed(lots_.size() + 1, 0U);
    for (std::size_t person_index = 1U;
        person_index + 1U < indexes_->person_offsets.size(); ++person_index) {
        const auto begin = indexes_->person_offsets[person_index];
        const auto end = indexes_->person_offsets[person_index + 1U];
        const auto expected_head =
            begin == end ? 0U
                         : static_cast<std::uint32_t>(
                               indexes_->lots_by_person[begin].value());
        const auto expected_tail =
            begin == end ? 0U
                         : static_cast<std::uint32_t>(
                               indexes_->lots_by_person[end - 1U].value());
        if (indexes_->person_heads[person_index] != expected_head ||
            indexes_->person_tails[person_index] != expected_tail) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial owner index is inconsistent");
        }
        for (std::size_t offset = begin; offset < end; ++offset) {
            const auto lot_id = indexes_->lots_by_person[offset];
            const auto *lot = get(lot_id);
            if (lot == nullptr) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index is inconsistent");
            }
            const auto lot_index =
                static_cast<std::size_t>(lot_id.value() - 1U);
            const auto expected_previous =
                offset == begin
                    ? 0U
                    : static_cast<std::uint32_t>(
                          indexes_->lots_by_person[offset - 1U].value());
            const auto expected_next =
                offset + 1U == end
                    ? 0U
                    : static_cast<std::uint32_t>(
                          indexes_->lots_by_person[offset + 1U].value());
            if (!lot->active || lot->owner.value() != person_index ||
                indexes_->person_previous[lot_index] != expected_previous ||
                indexes_->person_next[lot_index] != expected_next ||
                indexed[static_cast<std::size_t>(lot_id.value())] != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index is inconsistent");
            }
            indexed[static_cast<std::size_t>(lot_id.value())] = 1U;
        }
    }
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        const auto &lot = lots_[index];
        if (lot.id != BeneficialLotId(index + 1U) ||
            (!lot.active && lot.share != 0.0)) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership lot is inconsistent");
        }
        const auto asset_row =
            static_cast<std::size_t>(indexes_->asset_row_by_lot[index]);
        const bool asset_indexed =
            indexes_->asset_lot_indexed[index] != 0U;
        if ((lot.active && !asset_indexed) ||
            (asset_indexed &&
             (asset_row >= indexes_->lots_by_asset.size() ||
              indexes_->lots_by_asset[asset_row].asset != lot.asset))) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lot index is inconsistent");
        }
        if (!lot.active) {
            if (lot.share != 0.0) {
                return Status(ErrorCode::invariant_violation,
                              "retired beneficial lot has a share");
            }
            continue;
        }
        if (!persons.alive(lot.owner) || !finite(lot.share) || lot.share <= 0.0 ||
            indexed[static_cast<std::size_t>(lot.id.value())] != 1U) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership lot is inconsistent");
        }
    }

    for (std::size_t row_index = 0;
         row_index < indexes_->lots_by_asset.size();
         ++row_index) {
        const auto &row = indexes_->lots_by_asset[row_index];
        if (find_asset_row(row.asset) != row_index) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lookup index is inconsistent");
        }
        double total = 0.0;
        std::uint32_t active_lots = 0U;
        for (const auto lot_id : lots_for_asset(row.asset)) {
            const auto *lot = get(lot_id);
            if (lot == nullptr || lot->asset != row.asset) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial asset index is inconsistent");
            }
            if (!lot->active) {
                continue;
            }
            auto &flags = indexed[static_cast<std::size_t>(lot_id.value())];
            if ((flags & 2U) != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial asset index contains a duplicate lot");
            }
            flags |= 2U;
            total += lot->share;
            ++active_lots;
        }
        if (active_lots != row.active_lots ||
            (active_lots != 0U && std::abs(total - 1.0) > tolerance)) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership projection does not sum to one");
        }
    }

    for (const auto &lot : lots_) {
        if (lot.active &&
            indexed[static_cast<std::size_t>(lot.id.value())] != 3U) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership lot is not fully indexed");
        }
    }
    indexes_->validation_dirty_lots.clear();
    indexes_->validation_dirty_asset_rows.clear();
    indexes_->full_validation_required = false;
    return Status::success();
}

} // namespace macro_sim::core
