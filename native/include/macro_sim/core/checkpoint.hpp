#ifndef MACRO_SIM_CORE_CHECKPOINT_HPP
#define MACRO_SIM_CORE_CHECKPOINT_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"

namespace macro_sim::core {

inline constexpr std::uint32_t kM2CheckpointSchemaVersion = 2;
inline constexpr std::uint32_t kCanonicalEncodingVersion = 1;

struct CheckpointLimits final {
    std::size_t maximum_archive_bytes{64U * 1024U * 1024U};
    std::size_t maximum_entry_bytes{64U * 1024U * 1024U};
    std::size_t maximum_entries{16};
    std::size_t maximum_records{1'000'000};
};

[[nodiscard]] Result<std::vector<std::uint8_t>> save_checkpoint(
    const RootState& state
);

[[nodiscard]] Result<RootState> load_checkpoint(
    std::span<const std::uint8_t> archive,
    CheckpointLimits limits = {}
);

[[nodiscard]] Status validate_canonical_json(
    std::span<const std::uint8_t> encoded
) noexcept;

}  // namespace macro_sim::core

#endif
