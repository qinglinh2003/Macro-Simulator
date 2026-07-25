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

Status PersonStore::replace_records(
    std::vector<PersonRecord> records
) {
    if (records.empty()) {
        return Status(ErrorCode::corrupt_input,
                      "person checkpoint records are empty");
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
    auto &members =
        members_by_household_[
            static_cast<std::size_t>(household.value())];
    members.insert(
        std::lower_bound(members.begin(), members.end(), person),
        person
    );
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
            return Status(
                ErrorCode::invariant_violation,
                "household member order is not canonical"
            );
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

Status HouseholdMembershipBook::rebuild(
    const PersonStore &persons
) {
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

void BeneficialOwnershipBook::ensure_person(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1;
    if (lots_by_person_.size() < size) {
        lots_by_person_.resize(size);
    }
}

Result<BeneficialLotId> BeneficialOwnershipBook::create_lot(BeneficialAssetKey asset,
                                                            PersonId owner,
                                                            double share) {
    if (!asset.household.valid() || asset.household.value() == 0 || !owner.valid() ||
        owner.value() == 0 || !finite(share) || share <= 0.0 || share > 1.0) {
        return Status(ErrorCode::invalid_argument,
                      "beneficial ownership lot is invalid");
    }
    const auto id = BeneficialLotId(lots_.size() + 1);
    lots_.push_back({id, asset, owner, share, true});
    ensure_person(owner);
    lots_by_person_[static_cast<std::size_t>(owner.value())].push_back(id);
    lots_by_asset_[asset].push_back(id);
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
    const double remaining = source->share - share;
    if (remaining <= 1.0e-15) {
        auto &old_index =
            lots_by_person_[static_cast<std::size_t>(source->owner.value())];
        const auto found = std::find(old_index.begin(), old_index.end(), lot);
        if (found == old_index.end()) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial owner index is inconsistent");
        }
        old_index.erase(found);
        source->owner = destination;
        ensure_person(destination);
        lots_by_person_[static_cast<std::size_t>(destination.value())].push_back(lot);
        return Status::success();
    }
    source->share = remaining;
    const auto created = create_lot(source->asset, destination, share);
    return created.ok() ? Status::success() : created.status();
}

Status BeneficialOwnershipBook::retire(BeneficialLotId lot) {
    auto *record = get(lot);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "beneficial ownership lot is absent");
    }
    auto &index = lots_by_person_[static_cast<std::size_t>(record->owner.value())];
    const auto found = std::find(index.begin(), index.end(), lot);
    if (found == index.end()) {
        return Status(ErrorCode::invariant_violation,
                      "beneficial owner index is inconsistent");
    }
    index.erase(found);
    record->active = false;
    record->share = 0.0;
    return Status::success();
}

Status BeneficialOwnershipBook::retire_asset(
    BeneficialAssetKey asset
) {
    const auto found = lots_by_asset_.find(asset);
    if (found == lots_by_asset_.end()) {
        return Status::success();
    }
    const auto lots = found->second;
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
    lots_by_asset_.erase(asset);
    return Status::success();
}

Status BeneficialOwnershipBook::retire_household(
    HouseholdId household
) {
    if (!household.valid()) {
        return Status(
            ErrorCode::invalid_argument,
            "beneficial household retirement is invalid"
        );
    }
    std::vector<BeneficialAssetKey> assets;
    for (const auto &[asset, lots] : lots_by_asset_) {
        if (asset.household == household && !lots.empty()) {
            assets.push_back(asset);
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

Status BeneficialOwnershipBook::rekey_household(
    HouseholdId source, HouseholdId destination
) {
    if (!source.valid() || !destination.valid() ||
        source == destination) {
        return Status(
            ErrorCode::invalid_argument,
            "beneficial household rekey is invalid"
        );
    }
    std::vector<BeneficialAssetKey> source_assets;
    for (const auto &[asset, lots] : lots_by_asset_) {
        if (asset.household == source && !lots.empty()) {
            source_assets.push_back(asset);
        }
    }
    for (const auto source_asset : source_assets) {
        auto destination_asset = source_asset;
        destination_asset.household = destination;
        if (contains_asset(destination_asset)) {
            return Status(
                ErrorCode::already_exists,
                "beneficial destination asset already exists"
            );
        }
        auto node = lots_by_asset_.extract(source_asset);
        node.key() = destination_asset;
        for (const auto lot : node.mapped()) {
            auto *record = get(lot);
            if (record != nullptr && record->active) {
                record->asset = destination_asset;
            }
        }
        lots_by_asset_.insert(std::move(node));
    }
    return Status::success();
}

bool BeneficialOwnershipBook::contains_asset(
    BeneficialAssetKey asset
) const noexcept {
    const auto found = lots_by_asset_.find(asset);
    if (found == lots_by_asset_.end()) {
        return false;
    }
    return std::any_of(
        found->second.begin(), found->second.end(),
        [this](BeneficialLotId lot) {
            const auto *record = get(lot);
            return record != nullptr && record->active;
        }
    );
}

std::span<const BeneficialLotId>
BeneficialOwnershipBook::lots_for_asset(
    BeneficialAssetKey asset
) const noexcept {
    const auto found = lots_by_asset_.find(asset);
    return found == lots_by_asset_.end()
               ? std::span<const BeneficialLotId>{}
               : std::span<const BeneficialLotId>(found->second);
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
BeneficialOwnershipBook::lots_for_person(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= lots_by_person_.size()) {
        return {};
    }
    return lots_by_person_[static_cast<std::size_t>(person.value())];
}

const std::vector<BeneficialLot> &BeneficialOwnershipBook::records() const noexcept {
    return lots_;
}

std::size_t BeneficialOwnershipBook::size() const noexcept { return lots_.size(); }

Status BeneficialOwnershipBook::replace_records(
    std::vector<BeneficialLot> records
) {
    lots_ = std::move(records);
    lots_by_person_.assign(1, std::vector<BeneficialLotId>{});
    lots_by_asset_.clear();
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        auto &lot = lots_[index];
        if (lot.id != BeneficialLotId(index + 1U)) {
            return Status(ErrorCode::corrupt_input,
                          "beneficial checkpoint identity is invalid");
        }
        if (!lot.active) {
            continue;
        }
        ensure_person(lot.owner);
        lots_by_person_[
            static_cast<std::size_t>(lot.owner.value())]
            .push_back(lot.id);
        lots_by_asset_[lot.asset].push_back(lot.id);
    }
    return Status::success();
}

Status BeneficialOwnershipBook::validate(const PersonStore &persons,
                                         double tolerance) const {
    std::vector<std::uint8_t> indexed(lots_.size() + 1, 0U);
    for (std::size_t person_index = 1; person_index < lots_by_person_.size();
         ++person_index) {
        for (const auto lot_id : lots_by_person_[person_index]) {
            const auto *lot = get(lot_id);
            if (lot == nullptr || !lot->active || lot->owner.value() != person_index ||
                indexed[static_cast<std::size_t>(lot_id.value())] != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "beneficial owner index is inconsistent");
            }
            indexed[static_cast<std::size_t>(lot_id.value())] = 1U;
        }
    }
    std::vector<std::size_t> order;
    order.reserve(lots_.size());
    for (std::size_t index = 0; index < lots_.size(); ++index) {
        const auto &lot = lots_[index];
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
        order.push_back(index);
    }
    std::sort(order.begin(), order.end(), [this](std::size_t left, std::size_t right) {
        return lots_[left].asset < lots_[right].asset;
    });
    std::size_t cursor = 0;
    while (cursor < order.size()) {
        const auto asset = lots_[order[cursor]].asset;
        double total = 0.0;
        while (cursor < order.size() && lots_[order[cursor]].asset == asset) {
            total += lots_[order[cursor]].share;
            ++cursor;
        }
        if (std::abs(total - 1.0) > tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "beneficial ownership projection does not sum to one");
        }
    }
    return Status::success();
}

} // namespace macro_sim::core
