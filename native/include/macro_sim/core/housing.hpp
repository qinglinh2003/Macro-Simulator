#ifndef MACRO_SIM_CORE_HOUSING_HPP
#define MACRO_SIM_CORE_HOUSING_HPP

#include <cstddef>
#include <cstdint>
#include <map>
#include <span>
#include <vector>

#include "macro_sim/core/state_types.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

enum class TitleEventKind : std::uint8_t {
    mint = 0,
    transfer = 1,
    destroy = 2,
};

struct DwellingRecord final {
    DwellingId id{};
    OwnerId owner{};
    HouseholdId occupant{};
    LoanId collateral{};
    Tick minted_tick{};
    Tick last_title_tick{};
    double floor_area{0.0};
    double quality{0.0};
    std::uint32_t location{0};
    std::uint32_t age_days{0};
    bool active{true};

    bool operator==(const DwellingRecord &) const = default;
};

struct DwellingMintSpec final {
    OwnerId owner{};
    HouseholdId occupant{};
    Tick tick{};
    double floor_area{0.0};
    double quality{0.0};
    std::uint32_t location{0};
    std::uint32_t age_days{0};

    bool operator==(const DwellingMintSpec &) const = default;
};

struct TitleEvent final {
    TitleEventId id{};
    DwellingId dwelling{};
    TitleEventKind kind{TitleEventKind::mint};
    OwnerId previous_owner{};
    OwnerId next_owner{};
    Tick tick{};

    bool operator==(const TitleEvent &) const = default;
};

class PropertyRegistry final {
  public:
    [[nodiscard]] bool operator==(const PropertyRegistry &other) const noexcept {
        return records_ == other.records_ && title_events_ == other.title_events_;
    }

    [[nodiscard]] Result<DwellingId> mint(const DwellingMintSpec &spec);
    [[nodiscard]] Status transfer_title(DwellingId dwelling, OwnerId expected_owner,
                                        OwnerId next_owner, Tick tick);
    [[nodiscard]] Status destroy(DwellingId dwelling, OwnerId expected_owner,
                                 Tick tick);
    [[nodiscard]] Status set_occupant(DwellingId dwelling,
                                      HouseholdId expected_occupant,
                                      HouseholdId next_occupant);
    [[nodiscard]] Status attach_collateral(DwellingId dwelling, LoanId loan);
    [[nodiscard]] Status clear_collateral(DwellingId dwelling, LoanId expected_loan);

    [[nodiscard]] DwellingRecord *get(DwellingId id) noexcept;
    [[nodiscard]] const DwellingRecord *get(DwellingId id) const noexcept;
    [[nodiscard]] const std::vector<DwellingRecord> &records() const noexcept;
    [[nodiscard]] const std::vector<TitleEvent> &title_events() const noexcept;
    [[nodiscard]] std::span<const DwellingId>
    dwellings_for_owner(OwnerId owner) const noexcept;
    [[nodiscard]] DwellingId
    dwelling_for_occupant(HouseholdId household) const noexcept;
    [[nodiscard]] DwellingId dwelling_for_collateral(LoanId loan) const noexcept;
    [[nodiscard]] std::size_t active_count() const noexcept;
    [[nodiscard]] std::size_t minted_count() const noexcept;
    [[nodiscard]] std::size_t destroyed_count() const noexcept;
    [[nodiscard]] std::size_t occupied_count() const noexcept;
    [[nodiscard]] std::size_t owner_occupied_count() const noexcept;

    [[nodiscard]] Status validate_fast() const noexcept;
    [[nodiscard]] Status validate() const noexcept;
    [[nodiscard]] Status replace_state(std::vector<DwellingRecord> records,
                                       std::vector<TitleEvent> events);

  private:
    [[nodiscard]] Status rebuild_indexes();
    [[nodiscard]] Status append_title_event(TitleEvent event);
    void remove_owner_index(OwnerId owner, DwellingId dwelling) noexcept;

    std::vector<DwellingRecord> records_;
    std::vector<TitleEvent> title_events_;
    std::map<OwnerId, std::vector<DwellingId>> owner_index_;
    std::map<HouseholdId, DwellingId> occupant_index_;
    std::map<LoanId, DwellingId> collateral_index_;
    std::size_t active_count_{0};
    std::size_t destroyed_count_{0};
    std::size_t occupied_count_{0};
    std::size_t owner_occupied_count_{0};
};

} // namespace macro_sim::core

#endif
