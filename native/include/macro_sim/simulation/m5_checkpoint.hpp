#ifndef MACRO_SIM_SIMULATION_M5_CHECKPOINT_HPP
#define MACRO_SIM_SIMULATION_M5_CHECKPOINT_HPP

#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/simulation/m5.hpp"

namespace macro_sim::simulation {

inline constexpr std::uint32_t kM5CheckpointSchemaVersion = 3;

struct M5Checkpoint final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime runtime;
    Tick tick{};
};

[[nodiscard]] bool is_m5_checkpoint(std::span<const std::uint8_t> bytes) noexcept;
[[nodiscard]] Result<std::vector<std::uint8_t>>
save_m5_checkpoint(const core::RootState &root, const M4Runtime &real_economy_runtime,
                   const M5Runtime &runtime, Tick tick);
[[nodiscard]] Result<M5Checkpoint>
load_m5_checkpoint(std::span<const std::uint8_t> bytes);

} // namespace macro_sim::simulation

#endif
