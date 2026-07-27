#ifndef MACRO_SIM_DESKTOP_M11_NEW_GAME_HPP
#define MACRO_SIM_DESKTOP_M11_NEW_GAME_HPP

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/control/m11_session.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::desktop {

inline constexpr std::uint32_t kM11NewGameSchemaVersion = 1U;
inline constexpr std::string_view kM11PlayableModelId = "current_playable_native_v1";
inline constexpr std::size_t kM11MaximumNewGameCountries = 8U;

struct M11CountryMetadata final {
    std::string name;
    std::string code;
    std::string profile;

    bool operator==(const M11CountryMetadata &) const = default;
};

struct M11NativeNewGame final {
    std::uint32_t schema_version{kM11NewGameSchemaVersion};
    std::string model_id{std::string(kM11PlayableModelId)};
    std::uint64_t seed{7U};
    std::string start_date{"2000-01-01"};
    std::optional<std::uint64_t> duration_ticks{1827U};
    std::uint64_t player_economy{0U};
    std::string run_mode{"interactive"};
    std::vector<M11CountryMetadata> countries;
    simulation::M9WorldSpec world;
    control::M11ControllerRunSpec controller;
    std::vector<control::NativePolicyAction> initial_policy_actions;
};

[[nodiscard]] Result<M11NativeNewGame>
parse_m11_native_new_game(std::string_view json_document);

[[nodiscard]] Result<M11NativeNewGame>
default_m11_native_new_game(std::uint64_t seed = 7U);

} // namespace macro_sim::desktop

#endif
