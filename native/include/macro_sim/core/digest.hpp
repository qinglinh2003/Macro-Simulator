#ifndef MACRO_SIM_CORE_DIGEST_HPP
#define MACRO_SIM_CORE_DIGEST_HPP

#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace macro_sim::core {

struct RootState;

struct StateDigest final {
    std::array<std::uint8_t, 32> bytes{};

    [[nodiscard]] std::string hex() const;
    constexpr auto operator<=>(const StateDigest&) const noexcept = default;
};

[[nodiscard]] StateDigest sha256_digest(
    std::span<const std::uint8_t> bytes
) noexcept;
[[nodiscard]] StateDigest state_digest(const RootState& state);
[[nodiscard]] StateDigest state_digest(
    const RootState& state,
    std::vector<std::uint8_t>& scratch
);

}  // namespace macro_sim::core

#endif
