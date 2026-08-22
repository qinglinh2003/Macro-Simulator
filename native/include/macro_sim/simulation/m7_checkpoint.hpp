#ifndef MACRO_SIM_SIMULATION_M7_CHECKPOINT_HPP
#define MACRO_SIM_SIMULATION_M7_CHECKPOINT_HPP

#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m7.hpp"

namespace macro_sim::simulation {

inline constexpr std::uint32_t kM7CheckpointSchemaVersion = 4;

struct M7Checkpoint final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime financial_runtime;
    M7Runtime runtime;
    Tick tick{};
};

[[nodiscard]] bool
is_m7_checkpoint(std::span<const std::uint8_t> bytes) noexcept;
[[nodiscard]] Result<std::vector<std::uint8_t>>
save_m7_checkpoint(const core::RootState &root,
                   const M4Runtime &real_economy_runtime,
                   const M5Runtime &monetary_runtime,
                   const M6Runtime &financial_runtime,
                   const M7Runtime &runtime, Tick tick);
[[nodiscard]] Result<M7Checkpoint>
load_m7_checkpoint(std::span<const std::uint8_t> bytes);
[[nodiscard]] Result<core::StateDigest>
m7_state_digest(const core::RootState &root,
                const M4Runtime &real_economy_runtime,
                const M5Runtime &monetary_runtime,
                const M6Runtime &financial_runtime,
                const M7Runtime &runtime, Tick tick);

} // namespace macro_sim::simulation

#endif
