#ifndef MACRO_SIM_CORE_POPULATION_HPP
#define MACRO_SIM_CORE_POPULATION_HPP

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <vector>

#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

enum class PersonSex : std::uint8_t {
    female = 0,
    male = 1,
};

struct PersonRecord final {
    PersonId id{};
    PersonSex sex{PersonSex::female};
    std::int32_t birth_day{0};
    std::int32_t death_day{-1};
    PersonId mother{};
    PersonId father{};
    PersonId partner{};
    PersonId guardian{};
    HouseholdId household{};
    std::int32_t marriage_start_day{-1};
    std::int32_t last_divorce_day{-1};
    std::int32_t last_widowed_day{-1};
    std::uint32_t marriage_count{0};
    double efficiency{1.0};
    bool participating{false};
    bool searching{true};
    bool alive{true};

    bool operator==(const PersonRecord &) const = default;
};

class PersonStore final {
  public:
    [[nodiscard]] Result<PersonId> create(PersonRecord person);
    [[nodiscard]] Status mark_dead(PersonId id, std::int32_t day);
    [[nodiscard]] PersonRecord *get(PersonId id) noexcept;
    [[nodiscard]] const PersonRecord *get(PersonId id) const noexcept;
    [[nodiscard]] bool contains(PersonId id) const noexcept;
    [[nodiscard]] bool alive(PersonId id) const noexcept;
    [[nodiscard]] std::size_t alive_count() const noexcept;
    [[nodiscard]] std::size_t archived_count() const noexcept;
    [[nodiscard]] std::size_t total_count() const noexcept;
    [[nodiscard]] std::uint64_t next_id() const noexcept;
    [[nodiscard]] std::span<const PersonId> alive_ids() const noexcept;
    [[nodiscard]] std::span<const PersonId> archive_ids() const noexcept;
    [[nodiscard]] const std::vector<PersonRecord> &records() const noexcept;
    [[nodiscard]] Status replace_records(std::vector<PersonRecord> records);
    [[nodiscard]] Status validate() const noexcept;

  private:
    static constexpr std::size_t kNoDense = std::numeric_limits<std::size_t>::max();

    std::vector<PersonRecord> records_{PersonRecord{}};
    std::vector<PersonId> alive_ids_;
    std::vector<PersonId> archive_ids_;
    std::vector<std::size_t> alive_dense_by_id_{kNoDense};
    std::uint64_t next_id_{1};
};

class HouseholdMembershipBook final {
  public:
    [[nodiscard]] Status add(PersonId person, HouseholdId household);
    [[nodiscard]] Status move(PersonId person, HouseholdId household);
    [[nodiscard]] Status remove(PersonId person);
    [[nodiscard]] HouseholdId household_of(PersonId person) const noexcept;
    [[nodiscard]] std::span<const PersonId>
    members(HouseholdId household) const noexcept;
    [[nodiscard]] std::size_t household_capacity() const noexcept;
    [[nodiscard]] Status validate(const PersonStore &persons,
                                  const RootState &state) const;
    [[nodiscard]] Status rebuild(const PersonStore &persons);

  private:
    void ensure_person(PersonId person);
    void ensure_household(HouseholdId household);

    std::vector<HouseholdId> household_by_person_{HouseholdId{}};
    std::vector<std::vector<PersonId>> members_by_household_{std::vector<PersonId>{}};
};

enum class BeneficialAssetKind : std::uint8_t {
    household_cash = 0,
    household_debt = 1,
    security_position = 2,
    generic_position = 3,
};

struct BeneficialAssetKey final {
    BeneficialAssetKind kind{BeneficialAssetKind::generic_position};
    HouseholdId household{};
    std::uint64_t value{0};

    constexpr auto operator<=>(const BeneficialAssetKey &) const noexcept = default;
};

struct BeneficialLot final {
    BeneficialLotId id{};
    BeneficialAssetKey asset{};
    PersonId owner{};
    double share{0.0};
    bool active{true};

    bool operator==(const BeneficialLot &) const = default;
};

class BeneficialOwnershipBook final {
  public:
    [[nodiscard]] Result<BeneficialLotId> create_lot(BeneficialAssetKey asset,
                                                     PersonId owner, double share);
    [[nodiscard]] Status transfer(BeneficialLotId lot, PersonId destination,
                                  double share);
    [[nodiscard]] Status retire(BeneficialLotId lot);
    [[nodiscard]] Status retire_asset(BeneficialAssetKey asset);
    [[nodiscard]] Status retire_household(HouseholdId household);
    [[nodiscard]] Status rekey_household(HouseholdId source, HouseholdId destination);
    [[nodiscard]] BeneficialLot *get(BeneficialLotId id) noexcept;
    [[nodiscard]] const BeneficialLot *get(BeneficialLotId id) const noexcept;
    [[nodiscard]] bool contains_asset(BeneficialAssetKey asset) const noexcept;
    [[nodiscard]] std::span<const BeneficialLotId>
    lots_for_person(PersonId person) const;
    [[nodiscard]] std::span<const BeneficialLotId>
    lots_for_asset(BeneficialAssetKey asset) const;
    [[nodiscard]] const std::vector<BeneficialLot> &records() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    void active_assets(std::vector<BeneficialAssetKey> &output) const;
    void active_assets_except(BeneficialAssetKind excluded,
                              std::vector<BeneficialAssetKey> &output) const;
    [[nodiscard]] Status begin_asset_presence_refresh(BeneficialAssetKind kind);
    [[nodiscard]] bool touch_asset_presence(BeneficialAssetKey asset) noexcept;
    [[nodiscard]] Status finish_asset_presence_refresh();
    [[nodiscard]] double maximum_projection_error() const;
    [[nodiscard]] Status replace_records(std::vector<BeneficialLot> records);
    [[nodiscard]] Status validate_fast(const PersonStore &persons,
                                       double tolerance) const;
    [[nodiscard]] Status validate(const PersonStore &persons, double tolerance) const;

  private:
    static constexpr std::size_t kMissingAssetRow =
        std::numeric_limits<std::size_t>::max();

    struct AssetIndexRow final {
        BeneficialAssetKey asset{};
        std::uint32_t active_lots{0};
    };

    struct AssetSlot final {
        std::uint32_t fingerprint{0U};
        std::uint32_t row{0U};
    };

    struct Indexes final {
        std::vector<AssetIndexRow> lots_by_asset;
        std::vector<AssetSlot> asset_slots;
        std::vector<std::uint32_t> canonical_cash_rows;
        std::vector<std::uint32_t> asset_row_by_lot;
        std::vector<std::uint8_t> asset_lot_indexed;
        std::vector<std::uint32_t> asset_presence_epochs;
        std::vector<std::uint32_t> person_heads{0U};
        std::vector<std::uint32_t> person_tails{0U};
        std::vector<std::uint32_t> person_next;
        std::vector<std::uint32_t> person_previous;
        mutable std::vector<std::size_t> person_offsets;
        mutable std::vector<BeneficialLotId> lots_by_person;
        mutable std::vector<std::size_t> asset_offsets;
        mutable std::vector<BeneficialLotId> lots_by_asset_flat;
        mutable bool person_index_dirty{true};
        mutable bool asset_lot_index_dirty{true};
        std::uint32_t asset_presence_epoch{0U};
        BeneficialAssetKind refreshed_asset_kind{
            BeneficialAssetKind::generic_position};
        bool asset_presence_refresh_active{false};
        mutable std::vector<BeneficialLotId> validation_dirty_lots;
        mutable std::vector<std::size_t> validation_dirty_asset_rows;
        mutable bool full_validation_required{true};
    };

    void ensure_unique_indexes();
    void ensure_person_links(PersonId person);
    void append_person_lot(BeneficialLotId lot, PersonId person);
    [[nodiscard]] Status unlink_person_lot(BeneficialLotId lot, PersonId person);
    void rebuild_person_index() const;
    void rebuild_asset_lot_index() const;
    [[nodiscard]] static std::size_t asset_hash(BeneficialAssetKey asset) noexcept;
    [[nodiscard]] static std::uint32_t
    asset_fingerprint(std::size_t hash) noexcept;
    [[nodiscard]] std::size_t find_asset_row(BeneficialAssetKey asset) const noexcept;
    [[nodiscard]] std::size_t ensure_asset_row(BeneficialAssetKey asset);
    void rebuild_asset_slots(std::size_t minimum_rows);

    std::vector<BeneficialLot> lots_;
    std::shared_ptr<Indexes> indexes_{std::make_shared<Indexes>()};
};

} // namespace macro_sim::core

#endif
