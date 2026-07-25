#ifndef MACRO_SIM_CORE_POPULATION_HPP
#define MACRO_SIM_CORE_POPULATION_HPP

#include <cstddef>
#include <cstdint>
#include <limits>
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
    [[nodiscard]] BeneficialLot *get(BeneficialLotId id) noexcept;
    [[nodiscard]] const BeneficialLot *get(BeneficialLotId id) const noexcept;
    [[nodiscard]] std::span<const BeneficialLotId>
    lots_for_person(PersonId person) const noexcept;
    [[nodiscard]] const std::vector<BeneficialLot> &records() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    [[nodiscard]] Status validate(const PersonStore &persons, double tolerance) const;

  private:
    void ensure_person(PersonId person);

    std::vector<BeneficialLot> lots_;
    std::vector<std::vector<BeneficialLotId>> lots_by_person_{
        std::vector<BeneficialLotId>{}};
};

} // namespace macro_sim::core

#endif
