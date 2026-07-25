#ifndef MACRO_SIM_VERSION_HPP
#define MACRO_SIM_VERSION_HPP

#include <cstdint>
#include <string_view>

namespace macro_sim {

inline constexpr std::uint32_t kAbiVersion = 1;
inline constexpr std::string_view kEngineVersion = "0.7.0-m7";

[[nodiscard]] std::string_view engine_version() noexcept;
[[nodiscard]] std::uint32_t abi_version() noexcept;

} // namespace macro_sim

#endif
