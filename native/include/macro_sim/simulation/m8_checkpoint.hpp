#ifndef MACRO_SIM_SIMULATION_M8_CHECKPOINT_HPP
#define MACRO_SIM_SIMULATION_M8_CHECKPOINT_HPP

#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m8.hpp"

namespace macro_sim::simulation {

inline constexpr std::uint32_t kM8CheckpointSchemaVersion = 1;

struct M8Checkpoint final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime financial_runtime;
    M7Runtime population_runtime;
    M8Runtime runtime;
    Tick tick{};
};

[[nodiscard]] bool is_m8_checkpoint(std::span<const std::uint8_t> bytes) noexcept;
[[nodiscard]] Result<std::vector<std::uint8_t>> save_m8_checkpoint(
    const core::RootState &root, const M4Runtime &real_economy_runtime,
    const M5Runtime &monetary_runtime, const M6Runtime &financial_runtime,
    const M7Runtime &population_runtime, const M8Runtime &runtime, Tick tick);
[[nodiscard]] Result<M8Checkpoint>
load_m8_checkpoint(std::span<const std::uint8_t> bytes);
[[nodiscard]] Result<core::StateDigest>
m8_state_digest(const core::RootState &root, const M4Runtime &real_economy_runtime,
                const M5Runtime &monetary_runtime, const M6Runtime &financial_runtime,
                const M7Runtime &population_runtime, const M8Runtime &runtime,
                Tick tick);

} // namespace macro_sim::simulation

#endif
