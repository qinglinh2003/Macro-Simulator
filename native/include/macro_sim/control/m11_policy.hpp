#ifndef MACRO_SIM_CONTROL_M11_POLICY_HPP
#define MACRO_SIM_CONTROL_M11_POLICY_HPP

#include <array>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::control {

enum class PolicyScope : std::uint8_t {
    economy = 0,
    external = 1,
};

enum class PolicyValueKind : std::uint8_t {
    number = 0,
    nullable_number = 1,
    integer = 2,
    boolean = 3,
    choice = 4,
    economy_id = 5,
    economy_set = 6,
};

using PolicyEconomySet = std::vector<EconomyId>;
using PolicyValue = std::variant<
    std::monostate, bool, std::int64_t, double, std::string,
    PolicyEconomySet>;

struct PolicyLeverDescriptor final {
    std::string_view name;
    PolicyScope scope{PolicyScope::economy};
    PolicyValueKind kind{PolicyValueKind::number};
    std::optional<double> minimum{};
    std::optional<double> maximum{};
    std::string_view choices;
    std::string_view owner_role;
    std::string_view decision_group;
    std::uint32_t implementation_lag{0};
    std::optional<std::uint32_t> emergency_implementation_lag{};
    std::uint32_t minimum_hold_ticks{0};
    bool emergency{false};
    std::optional<double> control_scale{};
    std::optional<double> maximum_step{};
    double administrative_weight{1.0};
    std::string_view cost_class;
    std::string_view semantics;
    std::string_view handler_id;
    std::string_view enabled_if;
    std::string_view required_capabilities;
    std::string_view route_section;
    std::string_view route_field;

    bool operator==(const PolicyLeverDescriptor &) const = default;
};

#include "macro_sim/control/generated_m11_policy_contract.inc"

struct NativePolicyAction final {
    EconomyId economy{};
    std::string lever;
    PolicyValue value{};

    bool operator==(const NativePolicyAction &) const = default;
};

[[nodiscard]] std::span<const PolicyLeverDescriptor>
m11_policy_levers() noexcept;
[[nodiscard]] const PolicyLeverDescriptor *
find_m11_policy_lever(std::string_view name) noexcept;
[[nodiscard]] Status
validate_m11_policy_value(const PolicyLeverDescriptor &lever,
                          const PolicyValue &value,
                          EconomyId owner,
                          std::size_t economy_count) noexcept;
[[nodiscard]] Result<PolicyValue>
m11_policy_value(const simulation::DomesticPolicyState &domestic,
                 const simulation::ExternalPolicyState &external,
                 std::string_view name);
[[nodiscard]] Result<simulation::WorldPolicyBatch>
project_m11_policy_actions(
    const simulation::M9World &world,
    std::span<const NativePolicyAction> actions);

[[nodiscard]] bool m11_policy_values_equal(
    const PolicyValue &left, const PolicyValue &right) noexcept;
[[nodiscard]] Result<double>
m11_policy_numeric_distance(const PolicyLeverDescriptor &lever,
                            const PolicyValue &left,
                            const PolicyValue &right) noexcept;

} // namespace macro_sim::control

#endif
