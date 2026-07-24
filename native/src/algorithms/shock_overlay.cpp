#include "macro_sim/algorithms/shock_overlay.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <new>
#include <string_view>
#include <utility>

namespace macro_sim::algorithms {
namespace {

[[nodiscard]] Status invalid(std::string_view message) noexcept {
    return Status(ErrorCode::invalid_argument, message);
}

[[nodiscard]] bool matches_sector(
    SectorScope target,
    SectorScope query
) noexcept {
    if (target == SectorScope::all) {
        return true;
    }
    if (target == query) {
        return true;
    }
    return target == SectorScope::consumption
        && (
            query == SectorScope::necessity
            || query == SectorScope::luxury
        );
}

[[nodiscard]] bool valid_entry(const ShockOverlayEntry& entry) noexcept {
    if (
        entry.shock_id.empty()
        || !std::isfinite(entry.magnitude)
        || entry.magnitude < -3.0
        || entry.magnitude > 0.99
    ) {
        return false;
    }
    if (
        entry.duration_ticks.has_value()
        && *entry.duration_ticks == 0
    ) {
        return false;
    }
    if (
        !entry.duration_ticks.has_value()
        && entry.ramp_out_ticks != 0
    ) {
        return false;
    }
    if (
        entry.duration_ticks.has_value()
        && (
            entry.ramp_in_ticks
            > std::numeric_limits<std::uint64_t>::max()
                - entry.ramp_out_ticks
            || entry.ramp_in_ticks + entry.ramp_out_ticks
                > *entry.duration_ticks
        )
    ) {
        return false;
    }
    return !entry.economy.has_value() || entry.economy->valid();
}

}  // namespace

ShockOverlay::ShockOverlay(
    std::vector<ShockOverlayEntry> entries
) noexcept
    : entries_(std::move(entries)) {}

Result<ShockOverlay> ShockOverlay::create(
    std::vector<ShockOverlayEntry> entries
) noexcept {
    try {
        for (const auto& entry : entries) {
            if (!valid_entry(entry)) {
                return invalid("invalid shock overlay entry");
            }
        }
        std::stable_sort(
            entries.begin(),
            entries.end(),
            [](const auto& left, const auto& right) {
                return left.shock_id < right.shock_id;
            }
        );
        for (std::size_t index = 1; index < entries.size(); ++index) {
            if (entries[index - 1].shock_id == entries[index].shock_id) {
                return Status(
                    ErrorCode::already_exists,
                    "duplicate shock overlay ID"
                );
            }
        }
        return ShockOverlay(std::move(entries));
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "shock overlay allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "shock overlay construction failed"
        );
    }
}

Result<double> ShockOverlay::intensity_at(
    const ShockOverlayEntry& entry,
    std::uint64_t tick
) noexcept {
    if (!valid_entry(entry)) {
        return invalid("invalid shock overlay entry");
    }
    if (tick < entry.start_tick) {
        return 0.0;
    }
    std::optional<std::uint64_t> end_tick;
    if (entry.duration_ticks.has_value()) {
        if (
            entry.start_tick
            > std::numeric_limits<std::uint64_t>::max()
                - *entry.duration_ticks
        ) {
            return Status(
                ErrorCode::out_of_range,
                "shock end tick overflow"
            );
        }
        end_tick = entry.start_tick + *entry.duration_ticks;
        if (tick >= *end_tick) {
            return 0.0;
        }
    }
    const std::uint64_t elapsed = tick - entry.start_tick;
    double intensity = 1.0;
    if (entry.ramp_in_ticks != 0) {
        intensity = std::min(
            intensity,
            (static_cast<double>(elapsed) + 1.0)
                / static_cast<double>(entry.ramp_in_ticks)
        );
    }
    if (entry.ramp_out_ticks != 0 && end_tick.has_value()) {
        intensity = std::min(
            intensity,
            static_cast<double>(*end_tick - tick)
                / static_cast<double>(entry.ramp_out_ticks)
        );
    }
    return std::clamp(intensity, 0.0, 1.0);
}

Result<double> ShockOverlay::factor(
    ShockChannel channel,
    EconomyId economy,
    SectorScope sector,
    std::uint64_t tick
) const noexcept {
    if (!economy.valid()) {
        return invalid("shock read economy ID is invalid");
    }
    double result = 1.0;
    for (const auto& entry : entries_) {
        if (
            entry.channel != channel
            || (
                entry.economy.has_value()
                && *entry.economy != economy
            )
            || !matches_sector(entry.sector, sector)
        ) {
            continue;
        }
        auto intensity = intensity_at(entry, tick);
        if (!intensity.ok()) {
            return intensity.status();
        }
        result *= 1.0 - entry.magnitude * std::move(intensity).take();
    }
    if (!std::isfinite(result) || result <= 0.0 || result > 64.0) {
        return Status(
            ErrorCode::contract_violation,
            "shock overlay composition is outside valid bounds"
        );
    }
    return result;
}

const std::vector<ShockOverlayEntry>& ShockOverlay::entries() const noexcept {
    return entries_;
}

}  // namespace macro_sim::algorithms
