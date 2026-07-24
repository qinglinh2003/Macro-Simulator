#ifndef MACRO_SIM_ALGORITHMS_SHOCK_OVERLAY_HPP
#define MACRO_SIM_ALGORITHMS_SHOCK_OVERLAY_HPP

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"

namespace macro_sim::algorithms {

enum class ShockChannel : std::uint8_t {
    productivity = 0,
    labor_availability = 1,
    energy_capacity = 2,
    household_demand = 3,
    import_capacity = 4,
    export_capacity = 5,
    credit_supply = 6,
};

enum class SectorScope : std::uint8_t {
    all = 0,
    consumption = 1,
    necessity = 2,
    luxury = 3,
    capital = 4,
    energy = 5,
    housing = 6,
    public_sector = 7,
};

struct ShockOverlayEntry final {
    std::string shock_id{};
    ShockChannel channel{ShockChannel::productivity};
    std::optional<EconomyId> economy{};
    SectorScope sector{SectorScope::all};
    std::uint64_t start_tick{0};
    std::optional<std::uint64_t> duration_ticks{};
    std::uint64_t ramp_in_ticks{0};
    std::uint64_t ramp_out_ticks{0};
    double magnitude{0.0};
};

class ShockOverlay final {
public:
    [[nodiscard]] static Result<ShockOverlay> create(
        std::vector<ShockOverlayEntry> entries
    ) noexcept;

    [[nodiscard]] static Result<double> intensity_at(
        const ShockOverlayEntry& entry,
        std::uint64_t tick
    ) noexcept;

    [[nodiscard]] Result<double> factor(
        ShockChannel channel,
        EconomyId economy,
        SectorScope sector,
        std::uint64_t tick
    ) const noexcept;

    [[nodiscard]] const std::vector<ShockOverlayEntry>& entries() const noexcept;

private:
    explicit ShockOverlay(std::vector<ShockOverlayEntry> entries) noexcept;

    std::vector<ShockOverlayEntry> entries_{};
};

}  // namespace macro_sim::algorithms

#endif
