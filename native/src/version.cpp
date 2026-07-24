#include "macro_sim/version.hpp"

namespace macro_sim {

std::string_view engine_version() noexcept {
    return kEngineVersion;
}

std::uint32_t abi_version() noexcept {
    return kAbiVersion;
}

}  // namespace macro_sim
