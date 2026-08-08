#ifndef MACRO_SIM_SIMULATION_M4_CHECKPOINT_HPP
#define MACRO_SIM_SIMULATION_M4_CHECKPOINT_HPP

#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m4.hpp"

namespace macro_sim::simulation {

inline constexpr std::uint32_t kM4CheckpointSchemaVersion = 7;

struct M4Checkpoint final {
    core::RootState root;
    M4Runtime runtime;
    Tick tick{};
};

[[nodiscard]] bool is_m4_checkpoint(
    std::span<const std::uint8_t> bytes
) noexcept;
[[nodiscard]] Result<std::vector<std::uint8_t>> save_m4_checkpoint(
    const core::RootState& root,
    const M4Runtime& runtime,
    Tick tick
);
[[nodiscard]] Result<M4Checkpoint> load_m4_checkpoint(
    std::span<const std::uint8_t> bytes
);

}  // namespace macro_sim::simulation

#endif
