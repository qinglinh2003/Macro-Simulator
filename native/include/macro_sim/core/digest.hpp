#ifndef MACRO_SIM_CORE_DIGEST_HPP
#define MACRO_SIM_CORE_DIGEST_HPP

#include <array>
#include <cstdint>
#include <string>

namespace macro_sim::core {

struct RootState;

struct StateDigest final {
    std::array<std::uint8_t, 32> bytes{};

    [[nodiscard]] std::string hex() const;
    constexpr auto operator<=>(const StateDigest&) const noexcept = default;
};

[[nodiscard]] StateDigest state_digest(const RootState& state);

}  // namespace macro_sim::core

#endif
