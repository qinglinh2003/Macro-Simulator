#include "macro_sim/core/population.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace macro_sim::core {

namespace {

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

template <typename Value>
[[nodiscard]] std::uint64_t capacity_bytes(const std::vector<Value> &values) noexcept {
    return static_cast<std::uint64_t>(values.capacity()) * sizeof(Value);
}

} // namespace

Result<PersonId> PersonStore::create(PersonRecord person) {
    if (next_id_ > static_cast<std::uint64_t>(PersonId::max_valid_value())) {
        return Status(ErrorCode::out_of_range, "person ID space exhausted");
    }
    if (person.id.valid() || !finite(person.efficiency) || person.efficiency <= 0.0 ||
        person.death_day >= 0 || !person.alive) {
        return Status(ErrorCode::invalid_argument, "person genesis record is invalid");
    }
    const auto id =
        PersonId(static_cast<PersonId::rep_type>(next_id_++));
    person.id = id;
    records_.push_back(std::move(person));
    alive_dense_by_id_.push_back(
        static_cast<std::uint32_t>(alive_ids_.size()));
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
    const auto dense = static_cast<std::size_t>(alive_dense_by_id_[index]);
    if (dense == kNoDense || dense >= alive_ids_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "person alive index is inconsistent");
    }
    const auto moved = alive_ids_.back();
    alive_ids_[dense] = moved;
    alive_ids_.pop_back();
    alive_dense_by_id_[static_cast<std::size_t>(moved.value())] =
        static_cast<std::uint32_t>(dense);
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

std::uint64_t PersonStore::retained_bytes() const noexcept {
    return capacity_bytes(records_) + capacity_bytes(alive_ids_) +
           capacity_bytes(archive_ids_) + capacity_bytes(alive_dense_by_id_);
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
            alive_dense_by_id_[index] =
                static_cast<std::uint32_t>(alive_ids_.size());
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

std::uint64_t HouseholdMembershipBook::retained_bytes() const noexcept {
    std::uint64_t bytes =
        capacity_bytes(household_by_person_) + capacity_bytes(members_by_household_);
    for (const auto &members : members_by_household_) {
        bytes += capacity_bytes(members);
    }
    return bytes;
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
    }
}

void BeneficialOwnershipBook::append_person_lot(BeneficialLotId lot,
                                                PersonId person) {
    ensure_person_links(person);
    const auto person_index = static_cast<std::size_t>(person.value());
    const auto lot_index = static_cast<std::size_t>(lot.value() - 1U);
    const auto encoded_lot = static_cast<std::uint32_t>(lot.value());
    indexes_->person_next[lot_index] = 0U;
    auto tail = indexes_->person_heads[person_index];
    if (tail == 0U) {
        indexes_->person_heads[person_index] = encoded_lot;
        return;
    }
    std::size_t traversed = 0U;
    while (indexes_->person_next[static_cast<std::size_t>(tail - 1U)] != 0U) {
        tail = indexes_->person_next[static_cast<std::size_t>(tail - 1U)];
        if (++traversed > lots_.size()) {
            return;
        }
    }
    indexes_->person_next[static_cast<std::size_t>(tail - 1U)] =
        encoded_lot;
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
    std::uint32_t previous = 0U;
    auto current = indexes_->person_heads[person_index];
    std::size_t traversed = 0U;
    while (current != 0U && current != lot.value()) {
        previous = current;
        current = indexes_->person_next[static_cast<std::size_t>(current - 1U)];
        if (++traversed > lots_.size()) {
            break;
        }
    }
    if (current != lot.value()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial owner index is inconsistent");
    }
    const auto next = indexes_->person_next[lot_index];
    if (previous == 0U) {
        indexes_->person_heads[person_index] = next;
    } else {
        indexes_->person_next[static_cast<std::size_t>(previous - 1U)] = next;
    }
    indexes_->person_next[lot_index] = 0U;
    return Status::success();
}

void BeneficialOwnershipBook::append_asset_lot(BeneficialLotId lot,
                                               std::size_t asset_row) {
    const auto lot_index = static_cast<std::size_t>(lot.value() - 1U);
    const auto encoded_lot = static_cast<std::uint32_t>(lot.value());
    const auto previous_head = indexes_->asset_heads[asset_row];
    indexes_->asset_previous[lot_index] = 0U;
    indexes_->asset_next[lot_index] = previous_head;
    if (previous_head != 0U) {
        indexes_->asset_previous[
            static_cast<std::size_t>(previous_head - 1U)] = encoded_lot;
    }
    indexes_->asset_heads[asset_row] = encoded_lot;
    indexes_->asset_lot_indexed[lot_index] = 1U;
}

Status BeneficialOwnershipBook::unlink_asset_lot(BeneficialLotId lot,
                                                 std::size_t asset_row) {
    const auto lot_index = static_cast<std::size_t>(lot.value() - 1U);
    if (asset_row >= indexes_->asset_heads.size() ||
        lot_index >= indexes_->asset_next.size() ||
        lot_index >= indexes_->asset_previous.size() ||
        lot_index >= indexes_->asset_lot_indexed.size() ||
        indexes_->asset_lot_indexed[lot_index] == 0U) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset lot index is inconsistent");
    }
    const auto encoded_lot = static_cast<std::uint32_t>(lot.value());
    const auto previous = indexes_->asset_previous[lot_index];
    const auto next = indexes_->asset_next[lot_index];
    if (previous == 0U) {
        if (indexes_->asset_heads[asset_row] != encoded_lot) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lot index is inconsistent");
        }
        indexes_->asset_heads[asset_row] = next;
    } else {
        const auto previous_index =
            static_cast<std::size_t>(previous - 1U);
        if (previous_index >= indexes_->asset_next.size() ||
            indexes_->asset_next[previous_index] != encoded_lot) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lot index is inconsistent");
        }
        indexes_->asset_next[previous_index] = next;
    }
    if (next != 0U) {
        const auto next_index = static_cast<std::size_t>(next - 1U);
        if (next_index >= indexes_->asset_previous.size() ||
            indexes_->asset_previous[next_index] != encoded_lot) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial asset lot index is inconsistent");
        }
        indexes_->asset_previous[next_index] = previous;
    }
    indexes_->asset_next[lot_index] = 0U;
    indexes_->asset_previous[lot_index] = 0U;
    indexes_->asset_lot_indexed[lot_index] = 0U;
    return Status::success();
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

std::uint32_t
BeneficialOwnershipBook::asset_fingerprint(std::size_t hash) noexcept {
    auto fingerprint = static_cast<std::uint32_t>(
        static_cast<std::uint64_t>(hash) >> 32U);
    if (fingerprint == 0U) {
        fingerprint = 1U;
    }
    return fingerprint;
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
    const auto hash = asset_hash(asset);
    const auto fingerprint = asset_fingerprint(hash);
    auto slot = hash & mask;
    while (indexes_->asset_slots[slot].row != 0U) {
        const auto &candidate = indexes_->asset_slots[slot];
        const auto row = static_cast<std::size_t>(candidate.row - 1U);
        if (candidate.fingerprint == fingerprint &&
            indexes_->lots_by_asset[row].asset == asset) {
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
    indexes_->asset_slots.assign(capacity, AssetSlot{});
    const auto mask = capacity - 1U;
    for (std::size_t row = 0; row < indexes_->lots_by_asset.size(); ++row) {
        const auto hash = asset_hash(indexes_->lots_by_asset[row].asset);
        auto slot = hash & mask;
        while (indexes_->asset_slots[slot].row != 0U) {
            slot = (slot + 1U) & mask;
        }
        indexes_->asset_slots[slot] = {
            asset_fingerprint(hash),
            static_cast<std::uint32_t>(row + 1U),
        };
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
    if (row >= std::numeric_limits<std::uint32_t>::max()) {
        return kMissingAssetRow;
    }
    indexes_->lots_by_asset.push_back({asset, 0U, 0.0});
    indexes_->asset_heads.push_back(0U);
    indexes_->asset_presence_epochs.push_back(0U);
    const auto mask = indexes_->asset_slots.size() - 1U;
    const auto hash = asset_hash(asset);
    auto slot = hash & mask;
    while (indexes_->asset_slots[slot].row != 0U) {
        slot = (slot + 1U) & mask;
    }
    indexes_->asset_slots[slot] = {
        asset_fingerprint(hash),
        static_cast<std::uint32_t>(row + 1U),
    };
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
    indexes_->asset_lot_indexed.push_back(0U);
    indexes_->asset_next.push_back(0U);
    indexes_->asset_previous.push_back(0U);
    indexes_->person_next.push_back(0U);
    append_asset_lot(id, asset_row);
    append_person_lot(id, owner);
    ++indexes_->lots_by_asset[asset_row].active_lots;
    indexes_->lots_by_asset[asset_row].active_share += share;
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
    indexes_->lots_by_asset[asset_row].active_share -= share;
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
    auto &asset_index = indexes_->lots_by_asset[asset_row];
    --asset_index.active_lots;
    asset_index.active_share -= record->share;
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
        const auto unlinked = unlink_asset_lot(lot, row);
        if (!unlinked.ok()) {
            return unlinked;
        }
    }
    indexes_->lots_by_asset[row].active_lots = 0U;
    indexes_->lots_by_asset[row].active_share = 0.0;
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
        const auto active_share = indexes_->lots_by_asset[source_row].active_share;
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
            const auto unlinked = unlink_asset_lot(lot, source_row);
            if (!unlinked.ok()) {
                return unlinked;
            }
            record->asset = destination_asset;
            indexes_->asset_row_by_lot[
                static_cast<std::size_t>(lot.value() - 1U)] =
                static_cast<std::uint32_t>(destination_row);
            append_asset_lot(lot, destination_row);
            ++moved_lots;
            indexes_->validation_dirty_lots.push_back(lot);
        }
        if (moved_lots != active_lots) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial source asset index is inconsistent");
        }
        indexes_->lots_by_asset[source_row].active_lots = 0U;
        indexes_->lots_by_asset[source_row].active_share = 0.0;
        indexes_->lots_by_asset[destination_row].active_lots = active_lots;
        indexes_->lots_by_asset[destination_row].active_share = active_share;
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
    auto &query = indexes_->asset_query;
    query.clear();
    auto encoded_lot = indexes_->asset_heads[row];
    std::size_t traversed = 0U;
    while (encoded_lot != 0U) {
        const auto lot_index =
            static_cast<std::size_t>(encoded_lot - 1U);
        if (lot_index >= indexes_->asset_next.size() ||
            lot_index >= indexes_->asset_row_by_lot.size() ||
            indexes_->asset_lot_indexed[lot_index] == 0U ||
            indexes_->asset_row_by_lot[lot_index] != row) {
            query.clear();
            break;
        }
        query.push_back(BeneficialLotId(encoded_lot));
        encoded_lot = indexes_->asset_next[lot_index];
        if (++traversed > lots_.size()) {
            query.clear();
            break;
        }
    }
    return query;
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
    const auto index = static_cast<std::size_t>(person.value());
    if (index >= indexes_->person_heads.size()) {
        return {};
    }
    auto &query = indexes_->person_query;
    query.clear();
    auto lot = indexes_->person_heads[index];
    std::size_t traversed = 0U;
    while (lot != 0U) {
        query.push_back(BeneficialLotId(lot));
        lot = indexes_->person_next[static_cast<std::size_t>(lot - 1U)];
        if (++traversed > lots_.size()) {
            query.clear();
            break;
        }
    }
    return query;
}

const std::vector<BeneficialLot> &BeneficialOwnershipBook::records() const noexcept {
    return lots_;
}

std::size_t BeneficialOwnershipBook::size() const noexcept { return lots_.size(); }

BeneficialOwnershipMemoryUsage BeneficialOwnershipBook::memory_usage() const noexcept {
    BeneficialOwnershipMemoryUsage usage;
    usage.lots = capacity_bytes(lots_);
    if (indexes_ == nullptr) {
        return usage;
    }
    usage.asset_indexes = capacity_bytes(indexes_->lots_by_asset) +
                          capacity_bytes(indexes_->asset_slots) +
                          capacity_bytes(indexes_->canonical_cash_rows) +
                          capacity_bytes(indexes_->asset_row_by_lot) +
                          capacity_bytes(indexes_->asset_lot_indexed) +
                          capacity_bytes(indexes_->asset_heads) +
                          capacity_bytes(indexes_->asset_next) +
                          capacity_bytes(indexes_->asset_previous) +
                          capacity_bytes(indexes_->asset_presence_epochs);
    usage.person_indexes =
        capacity_bytes(indexes_->person_heads) + capacity_bytes(indexes_->person_next);
    usage.query_indexes = capacity_bytes(indexes_->person_query) +
                          capacity_bytes(indexes_->asset_query);
    usage.validation_scratch = capacity_bytes(indexes_->validation_dirty_lots) +
                               capacity_bytes(indexes_->validation_dirty_asset_rows);
    return usage;
}

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

void BeneficialOwnershipBook::active_assets_except(
    BeneficialAssetKind excluded,
    std::vector<BeneficialAssetKey> &output) const {
    output.clear();
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.active_lots != 0U && row.asset.kind != excluded) {
            output.push_back(row.asset);
        }
    }
}

Status BeneficialOwnershipBook::begin_asset_presence_refresh(
    BeneficialAssetKind kind) {
    if (indexes_->asset_presence_refresh_active) {
        return Status(ErrorCode::invalid_transaction_state,
                      "beneficial asset refresh is already active");
    }
    ensure_unique_indexes();
    if (indexes_->asset_presence_epoch ==
        std::numeric_limits<std::uint32_t>::max()) {
        std::fill(indexes_->asset_presence_epochs.begin(),
                  indexes_->asset_presence_epochs.end(), 0U);
        indexes_->asset_presence_epoch = 1U;
    } else {
        ++indexes_->asset_presence_epoch;
    }
    indexes_->refreshed_asset_kind = kind;
    indexes_->asset_presence_refresh_active = true;
    return Status::success();
}

bool BeneficialOwnershipBook::touch_asset_presence(
    BeneficialAssetKey asset) noexcept {
    if (!indexes_->asset_presence_refresh_active ||
        asset.kind != indexes_->refreshed_asset_kind) {
        return false;
    }
    const auto row = find_asset_row(asset);
    if (row == kMissingAssetRow ||
        indexes_->lots_by_asset[row].active_lots == 0U) {
        return false;
    }
    indexes_->asset_presence_epochs[row] = indexes_->asset_presence_epoch;
    return true;
}

Status BeneficialOwnershipBook::finish_asset_presence_refresh() {
    if (!indexes_->asset_presence_refresh_active) {
        return Status(ErrorCode::invalid_transaction_state,
                      "beneficial asset refresh is not active");
    }
    const auto kind = indexes_->refreshed_asset_kind;
    const auto epoch = indexes_->asset_presence_epoch;
    for (std::size_t row = 0U; row < indexes_->lots_by_asset.size(); ++row) {
        const auto &index = indexes_->lots_by_asset[row];
        if (index.asset.kind != kind || index.active_lots == 0U ||
            indexes_->asset_presence_epochs[row] == epoch) {
            continue;
        }
        const auto status = retire_asset(index.asset);
        if (!status.ok()) {
            indexes_->asset_presence_refresh_active = false;
            return status;
        }
    }
    indexes_->asset_presence_refresh_active = false;
    return Status::success();
}

double BeneficialOwnershipBook::maximum_projection_error() const {
    double maximum_error = 0.0;
    for (const auto &row : indexes_->lots_by_asset) {
        if (row.active_lots == 0U) {
            continue;
        }
        maximum_error =
            std::max(maximum_error, std::abs(row.active_share - 1.0));
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
    indexes_->asset_next.reserve(lots_.size());
    indexes_->asset_previous.reserve(lots_.size());
    indexes_->person_next.reserve(lots_.size());
    rebuild_asset_slots(lots_.size());
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        auto &lot = lots_[index];
        if (lot.id != BeneficialLotId(index + 1U)) {
            return Status(ErrorCode::corrupt_input,
                          "beneficial checkpoint identity is invalid");
        }
        indexes_->person_next.push_back(0U);
        indexes_->asset_next.push_back(0U);
        indexes_->asset_previous.push_back(0U);
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
        indexes_->asset_lot_indexed.push_back(0U);
        append_asset_lot(lot.id, asset_row);
        append_person_lot(lot.id, lot.owner);
        ++indexes_->lots_by_asset[asset_row].active_lots;
        indexes_->lots_by_asset[asset_row].active_share += lot.share;
    }
    return Status::success();
}

Status BeneficialOwnershipBook::validate_fast(const PersonStore &persons,
                                              double tolerance) const {
    if (!finite(tolerance) || tolerance < 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership tolerance is invalid");
    }
    if (indexes_->asset_presence_refresh_active ||
        indexes_->asset_presence_epochs.size() !=
            indexes_->lots_by_asset.size()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset refresh is inconsistent");
    }
    auto &dirty_lots = indexes_->validation_dirty_lots;
    auto &dirty_rows = indexes_->validation_dirty_asset_rows;
    const bool release_genesis_validation_capacity = indexes_->full_validation_required;
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
        if (!finite(row.active_share) ||
            (row.active_lots == 0U &&
             std::abs(row.active_share) > tolerance) ||
            (row.active_lots != 0U &&
             std::abs(row.active_share - 1.0) > tolerance)) {
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
    if (release_genesis_validation_capacity) {
        std::vector<BeneficialLotId>().swap(dirty_lots);
        std::vector<std::size_t>().swap(dirty_rows);
    }
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
        indexes_->asset_next.size() != lots_.size() ||
        indexes_->asset_previous.size() != lots_.size() ||
        indexes_->asset_heads.size() != indexes_->lots_by_asset.size() ||
        indexes_->person_next.size() != lots_.size() ||
        indexes_->asset_presence_refresh_active ||
        indexes_->asset_presence_epochs.size() !=
            indexes_->lots_by_asset.size()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial asset lot index is inconsistent");
    }
    std::vector<std::uint8_t> indexed(lots_.size() + 1, 0U);
    for (std::size_t person_index = 1U; person_index < indexes_->person_heads.size();
         ++person_index) {
        auto encoded_lot = indexes_->person_heads[person_index];
        std::size_t traversed = 0U;
        while (encoded_lot != 0U) {
            const auto lot_id = BeneficialLotId(encoded_lot);
            const auto *lot = get(lot_id);
            if (lot == nullptr) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index is inconsistent");
            }
            const auto lot_index =
                static_cast<std::size_t>(lot_id.value() - 1U);
            if (!lot->active || lot->owner.value() != person_index ||
                indexed[static_cast<std::size_t>(lot_id.value())] != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index is inconsistent");
            }
            indexed[static_cast<std::size_t>(lot_id.value())] = 1U;
            encoded_lot = indexes_->person_next[lot_index];
            if (++traversed > lots_.size()) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index contains a cycle");
            }
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
        std::uint32_t previous_lot = 0U;
        for (const auto lot_id : lots_for_asset(row.asset)) {
            const auto *lot = get(lot_id);
            const auto lot_index =
                static_cast<std::size_t>(lot_id.value() - 1U);
            if (lot == nullptr || lot->asset != row.asset ||
                lot_index >= indexes_->asset_previous.size() ||
                indexes_->asset_previous[lot_index] != previous_lot) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial asset index is inconsistent");
            }
            auto &flags = indexed[static_cast<std::size_t>(lot_id.value())];
            if ((flags & 2U) != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial asset index contains a duplicate lot");
            }
            flags |= 2U;
            previous_lot = static_cast<std::uint32_t>(lot_id.value());
            if (!lot->active) {
                continue;
            }
            total += lot->share;
            ++active_lots;
        }
        if (active_lots != row.active_lots ||
            std::abs(total - row.active_share) > tolerance ||
            (active_lots != 0U && std::abs(total - 1.0) > tolerance)) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership projection does not sum to one");
        }
    }

    for (const auto &lot : lots_) {
        const auto flags =
            indexed[static_cast<std::size_t>(lot.id.value())];
        const auto lot_index =
            static_cast<std::size_t>(lot.id.value() - 1U);
        const bool asset_indexed =
            indexes_->asset_lot_indexed[lot_index] != 0U;
        if ((lot.active && flags != 3U) ||
            (asset_indexed && (flags & 2U) == 0U) ||
            (!asset_indexed && (flags & 2U) != 0U)) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership lot is not fully indexed");
        }
    }
    indexes_->validation_dirty_lots.clear();
    indexes_->validation_dirty_asset_rows.clear();
    std::vector<BeneficialLotId>().swap(indexes_->validation_dirty_lots);
    std::vector<std::size_t>().swap(indexes_->validation_dirty_asset_rows);
    indexes_->full_validation_required = false;
    return Status::success();
}

} // namespace macro_sim::core
