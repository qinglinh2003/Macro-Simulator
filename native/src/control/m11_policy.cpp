#include "macro_sim/control/m11_policy.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace macro_sim::control {

namespace {

[[nodiscard]] bool choice_contains(std::string_view choices,
                                   std::string_view value) noexcept {
    std::size_t start = 0U;
    while (start <= choices.size()) {
        const auto ending = choices.find('|', start);
        const auto item = choices.substr(
            start,
            ending == std::string_view::npos
                ? choices.size() - start
                : ending - start);
        if (item == value) {
            return true;
        }
        if (ending == std::string_view::npos) {
            break;
        }
        start = ending + 1U;
    }
    return false;
}

[[nodiscard]] std::optional<double>
number_value(const PolicyValue &value) noexcept {
    if (const auto *number = std::get_if<double>(&value)) {
        return *number;
    }
    if (const auto *integer = std::get_if<std::int64_t>(&value)) {
        return static_cast<double>(*integer);
    }
    return std::nullopt;
}

[[nodiscard]] Result<PolicyValue>
read_policy_value(const simulation::DomesticPolicyState &domestic,
                  const simulation::ExternalPolicyState &external,
                  std::string_view name) {
#define MACRO_SIM_M11_DOMESTIC_NUMBER(label, section, field) \
    if (name == label) {                                      \
        return PolicyValue{domestic.section.field};           \
    }
#define MACRO_SIM_M11_DOMESTIC_NULLABLE_NUMBER(label, section, field) \
    if (name == label) {                                               \
        const auto &item = domestic.section.field;                     \
        return item.has_value() ? PolicyValue{*item}                   \
                                : PolicyValue{std::monostate{}};       \
    }
#define MACRO_SIM_M11_DOMESTIC_INTEGER(label, section, field) \
    if (name == label) {                                       \
        return PolicyValue{                                    \
            static_cast<std::int64_t>(domestic.section.field)}; \
    }
#define MACRO_SIM_M11_DOMESTIC_BOOLEAN(label, section, field) \
    if (name == label) {                                      \
        return PolicyValue{domestic.section.field};           \
    }
#define MACRO_SIM_M11_DOMESTIC_CHOICE(label, section, field)
#define MACRO_SIM_M11_DOMESTIC_ECONOMY_ID(label, section, field)
#define MACRO_SIM_M11_DOMESTIC_ECONOMY_SET(label, section, field)
#define MACRO_SIM_M11_EXTERNAL_NUMBER(label, field) \
    if (name == label) {                            \
        return PolicyValue{external.field};         \
    }
#define MACRO_SIM_M11_EXTERNAL_NULLABLE_NUMBER(label, field) \
    if (name == label) {                                     \
        const auto &item = external.field;                   \
        return item.has_value() ? PolicyValue{*item}         \
                                : PolicyValue{std::monostate{}}; \
    }
#define MACRO_SIM_M11_EXTERNAL_INTEGER(label, field) \
    if (name == label) {                              \
        return PolicyValue{                           \
            static_cast<std::int64_t>(external.field)}; \
    }
#define MACRO_SIM_M11_EXTERNAL_BOOLEAN(label, field) \
    if (name == label) {                             \
        return PolicyValue{external.field};          \
    }
#define MACRO_SIM_M11_EXTERNAL_CHOICE(label, field)
#define MACRO_SIM_M11_EXTERNAL_ECONOMY_ID(label, field) \
    if (name == label) {                               \
        return external.field.has_value()              \
                   ? PolicyValue{static_cast<std::int64_t>( \
                         external.field->value())}      \
                   : PolicyValue{std::monostate{}};    \
    }
#define MACRO_SIM_M11_EXTERNAL_ECONOMY_SET(label, field) \
    if (name == label) {                                 \
        return PolicyValue{external.field};              \
    }
#define MACRO_SIM_M11_SPECIAL(label)
#include "generated_m11_policy_routes.inc"
#undef MACRO_SIM_M11_DOMESTIC_NUMBER
#undef MACRO_SIM_M11_DOMESTIC_NULLABLE_NUMBER
#undef MACRO_SIM_M11_DOMESTIC_INTEGER
#undef MACRO_SIM_M11_DOMESTIC_BOOLEAN
#undef MACRO_SIM_M11_DOMESTIC_CHOICE
#undef MACRO_SIM_M11_DOMESTIC_ECONOMY_ID
#undef MACRO_SIM_M11_DOMESTIC_ECONOMY_SET
#undef MACRO_SIM_M11_EXTERNAL_NUMBER
#undef MACRO_SIM_M11_EXTERNAL_NULLABLE_NUMBER
#undef MACRO_SIM_M11_EXTERNAL_INTEGER
#undef MACRO_SIM_M11_EXTERNAL_BOOLEAN
#undef MACRO_SIM_M11_EXTERNAL_CHOICE
#undef MACRO_SIM_M11_EXTERNAL_ECONOMY_ID
#undef MACRO_SIM_M11_EXTERNAL_ECONOMY_SET
#undef MACRO_SIM_M11_SPECIAL

    if (name == "bank_resolution_fund") {
        return PolicyValue{
            domestic.financial.bank_resolution_fund};
    }
    if (name == "monetary_regime") {
        switch (domestic.fiscal_monetary.monetary_regime) {
            case simulation::MonetaryRegime::exogenous:
                return PolicyValue{std::string("exogenous")};
            case simulation::MonetaryRegime::taylor:
                return PolicyValue{std::string("taylor")};
            case simulation::MonetaryRegime::manual:
                return PolicyValue{std::string("manual")};
        }
    }
    if (name == "energy_rationing") {
        switch (domestic.energy.rationing) {
            case simulation::EnergyRationing::market:
                return PolicyValue{std::string("market")};
            case simulation::EnergyRationing::proportional:
                return PolicyValue{std::string("proportional")};
            case simulation::EnergyRationing::household_first:
                return PolicyValue{std::string("household_first")};
            case simulation::EnergyRationing::industry_first:
                return PolicyValue{std::string("industry_first")};
        }
    }
    if (name == "fx_regime") {
        return PolicyValue{std::string(
            external.fx_regime == simulation::FxRegime::peg
                ? "peg"
                : "float")};
    }
    return Status(ErrorCode::not_found,
                  "M11 policy lever is not mapped");
}

[[nodiscard]] Status
write_policy_value(simulation::DomesticPolicyState &domestic,
                   simulation::ExternalPolicyState &external,
                   std::string_view name,
                   const PolicyValue &value) {
    const auto numeric = number_value(value);
#define MACRO_SIM_M11_DOMESTIC_NUMBER(label, section, field) \
    if (name == label) {                                      \
        domestic.section.field = *numeric;                    \
        return Status::success();                             \
    }
#define MACRO_SIM_M11_DOMESTIC_NULLABLE_NUMBER(label, section, field) \
    if (name == label) {                                               \
        if (std::holds_alternative<std::monostate>(value)) {           \
            domestic.section.field.reset();                            \
        } else {                                                       \
            domestic.section.field = *numeric;                         \
        }                                                              \
        return Status::success();                                      \
    }
#define MACRO_SIM_M11_DOMESTIC_INTEGER(label, section, field) \
    if (name == label) {                                       \
        domestic.section.field = static_cast<                  \
            decltype(domestic.section.field)>(                 \
            std::get<std::int64_t>(value));                    \
        return Status::success();                              \
    }
#define MACRO_SIM_M11_DOMESTIC_BOOLEAN(label, section, field) \
    if (name == label) {                                      \
        domestic.section.field = std::get<bool>(value);       \
        return Status::success();                             \
    }
#define MACRO_SIM_M11_DOMESTIC_CHOICE(label, section, field)
#define MACRO_SIM_M11_DOMESTIC_ECONOMY_ID(label, section, field)
#define MACRO_SIM_M11_DOMESTIC_ECONOMY_SET(label, section, field)
#define MACRO_SIM_M11_EXTERNAL_NUMBER(label, field) \
    if (name == label) {                            \
        external.field = *numeric;                  \
        return Status::success();                   \
    }
#define MACRO_SIM_M11_EXTERNAL_NULLABLE_NUMBER(label, field) \
    if (name == label) {                                     \
        if (std::holds_alternative<std::monostate>(value)) { \
            external.field.reset();                          \
        } else {                                             \
            external.field = *numeric;                       \
        }                                                    \
        return Status::success();                            \
    }
#define MACRO_SIM_M11_EXTERNAL_INTEGER(label, field) \
    if (name == label) {                              \
        external.field = static_cast<decltype(external.field)>( \
            std::get<std::int64_t>(value));           \
        return Status::success();                     \
    }
#define MACRO_SIM_M11_EXTERNAL_BOOLEAN(label, field) \
    if (name == label) {                             \
        external.field = std::get<bool>(value);      \
        return Status::success();                    \
    }
#define MACRO_SIM_M11_EXTERNAL_CHOICE(label, field)
#define MACRO_SIM_M11_EXTERNAL_ECONOMY_ID(label, field) \
    if (name == label) {                               \
        if (std::holds_alternative<std::monostate>(value)) { \
            external.field.reset();                    \
        } else {                                       \
            external.field = EconomyId(                \
                static_cast<std::uint64_t>(             \
                    std::get<std::int64_t>(value)));    \
        }                                              \
        return Status::success();                      \
    }
#define MACRO_SIM_M11_EXTERNAL_ECONOMY_SET(label, field) \
    if (name == label) {                                 \
        external.field = std::get<PolicyEconomySet>(value); \
        return Status::success();                        \
    }
#define MACRO_SIM_M11_SPECIAL(label)
#include "generated_m11_policy_routes.inc"
#undef MACRO_SIM_M11_DOMESTIC_NUMBER
#undef MACRO_SIM_M11_DOMESTIC_NULLABLE_NUMBER
#undef MACRO_SIM_M11_DOMESTIC_INTEGER
#undef MACRO_SIM_M11_DOMESTIC_BOOLEAN
#undef MACRO_SIM_M11_DOMESTIC_CHOICE
#undef MACRO_SIM_M11_DOMESTIC_ECONOMY_ID
#undef MACRO_SIM_M11_DOMESTIC_ECONOMY_SET
#undef MACRO_SIM_M11_EXTERNAL_NUMBER
#undef MACRO_SIM_M11_EXTERNAL_NULLABLE_NUMBER
#undef MACRO_SIM_M11_EXTERNAL_INTEGER
#undef MACRO_SIM_M11_EXTERNAL_BOOLEAN
#undef MACRO_SIM_M11_EXTERNAL_CHOICE
#undef MACRO_SIM_M11_EXTERNAL_ECONOMY_ID
#undef MACRO_SIM_M11_EXTERNAL_ECONOMY_SET
#undef MACRO_SIM_M11_SPECIAL

    if (name == "bank_resolution_fund") {
        const auto enabled = std::get<bool>(value);
        domestic.fiscal_monetary.state_resolution_backstop = enabled;
        domestic.financial.bank_resolution_fund = enabled;
        return Status::success();
    }
    if (name == "monetary_regime") {
        const auto &regime = std::get<std::string>(value);
        if (regime == "exogenous") {
            domestic.fiscal_monetary.monetary_regime =
                simulation::MonetaryRegime::exogenous;
            domestic.fiscal_monetary.manual_policy_rate.reset();
        } else if (regime == "taylor") {
            domestic.fiscal_monetary.monetary_regime =
                simulation::MonetaryRegime::taylor;
            domestic.fiscal_monetary.manual_policy_rate.reset();
        } else {
            domestic.fiscal_monetary.monetary_regime =
                simulation::MonetaryRegime::manual;
        }
        return Status::success();
    }
    if (name == "energy_rationing") {
        const auto &rationing = std::get<std::string>(value);
        if (rationing == "market") {
            domestic.energy.rationing =
                simulation::EnergyRationing::market;
        } else if (rationing == "proportional") {
            domestic.energy.rationing =
                simulation::EnergyRationing::proportional;
        } else if (rationing == "household_first") {
            domestic.energy.rationing =
                simulation::EnergyRationing::household_first;
        } else {
            domestic.energy.rationing =
                simulation::EnergyRationing::industry_first;
        }
        return Status::success();
    }
    if (name == "fx_regime") {
        const auto &regime = std::get<std::string>(value);
        external.fx_regime =
            regime == "peg" ? simulation::FxRegime::peg
                            : simulation::FxRegime::floating;
        if (external.fx_regime == simulation::FxRegime::floating) {
            external.peg_anchor.reset();
        }
        return Status::success();
    }
    return Status(ErrorCode::not_found,
                  "M11 policy lever is not mapped");
}

} // namespace

std::span<const PolicyLeverDescriptor> m11_policy_levers() noexcept {
    return kM11PolicyLevers;
}

const PolicyLeverDescriptor *
find_m11_policy_lever(std::string_view name) noexcept {
    const auto iterator = std::lower_bound(
        kM11PolicyLevers.begin(), kM11PolicyLevers.end(), name,
        [](const PolicyLeverDescriptor &lever, std::string_view target) {
            return lever.name < target;
        });
    if (iterator == kM11PolicyLevers.end() || iterator->name != name) {
        return nullptr;
    }
    return &*iterator;
}

Status validate_m11_policy_value(
    const PolicyLeverDescriptor &lever, const PolicyValue &value,
    EconomyId owner, std::size_t economy_count) noexcept {
    const auto numeric = number_value(value);
    switch (lever.kind) {
        case PolicyValueKind::number:
            if (!numeric.has_value()) {
                return Status(ErrorCode::invalid_argument,
                              "M11 numeric policy value has the wrong type");
            }
            break;
        case PolicyValueKind::nullable_number:
            if (!std::holds_alternative<std::monostate>(value) &&
                !numeric.has_value()) {
                return Status(
                    ErrorCode::invalid_argument,
                    "M11 nullable policy value has the wrong type");
            }
            break;
        case PolicyValueKind::integer:
            if (!std::holds_alternative<std::int64_t>(value)) {
                return Status(ErrorCode::invalid_argument,
                              "M11 integer policy value has the wrong type");
            }
            break;
        case PolicyValueKind::boolean:
            if (!std::holds_alternative<bool>(value)) {
                return Status(ErrorCode::invalid_argument,
                              "M11 boolean policy value has the wrong type");
            }
            break;
        case PolicyValueKind::choice: {
            const auto *choice = std::get_if<std::string>(&value);
            if (choice == nullptr ||
                !choice_contains(lever.choices, *choice)) {
                return Status(ErrorCode::invalid_argument,
                              "M11 policy choice is outside its contract");
            }
            break;
        }
        case PolicyValueKind::economy_id: {
            if (std::holds_alternative<std::monostate>(value)) {
                break;
            }
            const auto *target = std::get_if<std::int64_t>(&value);
            if (target == nullptr || *target < 0 ||
                static_cast<std::uint64_t>(*target) >= economy_count ||
                static_cast<std::uint64_t>(*target) == owner.value()) {
                return Status(ErrorCode::out_of_range,
                              "M11 policy economy reference is invalid");
            }
            break;
        }
        case PolicyValueKind::economy_set: {
            const auto *targets = std::get_if<PolicyEconomySet>(&value);
            if (targets == nullptr ||
                !std::is_sorted(targets->begin(), targets->end()) ||
                std::adjacent_find(
                    targets->begin(), targets->end()) != targets->end()) {
                return Status(ErrorCode::invalid_argument,
                              "M11 policy economy set is not canonical");
            }
            for (const auto target : *targets) {
                if (target.value() >= economy_count ||
                    target == owner) {
                    return Status(ErrorCode::out_of_range,
                                  "M11 policy economy set target is invalid");
                }
            }
            break;
        }
    }
    if (numeric.has_value()) {
        if (!std::isfinite(*numeric)) {
            return Status(ErrorCode::invalid_argument,
                          "M11 numeric policy value is not finite");
        }
        if ((lever.minimum.has_value() &&
             *numeric < *lever.minimum) ||
            (lever.maximum.has_value() &&
             *numeric > *lever.maximum)) {
            return Status(ErrorCode::out_of_range,
                          "M11 numeric policy value is outside its contract");
        }
        if (lever.kind == PolicyValueKind::integer) {
            const auto integer = std::get<std::int64_t>(value);
            if (static_cast<double>(integer) != *numeric) {
                return Status(ErrorCode::out_of_range,
                              "M11 integer policy value loses precision");
            }
        }
    }
    return Status::success();
}

Result<PolicyValue>
m11_policy_value(const simulation::DomesticPolicyState &domestic,
                 const simulation::ExternalPolicyState &external,
                 std::string_view name) {
    if (find_m11_policy_lever(name) == nullptr) {
        return Status(ErrorCode::not_found,
                      "M11 policy lever is unknown");
    }
    return read_policy_value(domestic, external, name);
}

Result<simulation::WorldPolicyBatch>
project_m11_policy_actions(
    const simulation::M9World &world,
    std::span<const NativePolicyAction> actions) {
    simulation::WorldPolicyBatch batch;
    batch.expected_tick = world.tick();
    batch.expected_generation = world.policy_generation();
    batch.external = world.external_policies();
    batch.domestic.reserve(world.economy_count());
    for (std::size_t index = 0; index < world.economy_count(); ++index) {
        auto policy = world.domestic_policy(
            EconomyId(static_cast<std::uint64_t>(index)));
        if (!policy.ok()) {
            return policy.status();
        }
        batch.domestic.push_back(std::move(*policy.get_if()));
    }
    auto ordered = std::vector<NativePolicyAction>(
        actions.begin(), actions.end());
    std::sort(
        ordered.begin(), ordered.end(),
        [](const NativePolicyAction &left,
           const NativePolicyAction &right) {
            return std::pair(left.economy.value(), left.lever) <
                   std::pair(right.economy.value(), right.lever);
        });
    for (std::size_t index = 1U; index < ordered.size(); ++index) {
        if (ordered[index - 1U].economy == ordered[index].economy &&
            ordered[index - 1U].lever == ordered[index].lever) {
            return Status(ErrorCode::already_exists,
                          "M11 policy batch contains a duplicate lever");
        }
    }
    for (const auto &action : ordered) {
        const auto economy =
            static_cast<std::size_t>(action.economy.value());
        if (economy >= world.economy_count()) {
            return Status(ErrorCode::out_of_range,
                          "M11 policy action economy is unknown");
        }
        const auto *lever = find_m11_policy_lever(action.lever);
        if (lever == nullptr) {
            return Status(ErrorCode::not_found,
                          "M11 policy action lever is unknown");
        }
        auto status = validate_m11_policy_value(
            *lever, action.value, action.economy,
            world.economy_count());
        if (!status.ok()) {
            return status;
        }
        status = write_policy_value(
            batch.domestic[economy], batch.external[economy],
            action.lever, action.value);
        if (!status.ok()) {
            return status;
        }
    }
    for (auto &domestic : batch.domestic) {
        domestic.housing.wealth_tax_rate =
            domestic.fiscal_monetary.wealth_tax_rate;
        auto status = simulation::validate_domestic_policy(domestic);
        if (!status.ok()) {
            return status;
        }
    }
    for (std::size_t index = 0; index < batch.external.size(); ++index) {
        auto status = simulation::validate_external_policy(
            batch.external[index], batch.external.size(),
            EconomyId(static_cast<std::uint64_t>(index)));
        if (!status.ok()) {
            return status;
        }
    }
    std::size_t peg_count = 0U;
    for (std::size_t index = 0; index < batch.external.size(); ++index) {
        const auto &external = batch.external[index];
        if (external.fx_regime != simulation::FxRegime::peg) {
            continue;
        }
        ++peg_count;
        if (!external.peg_anchor.has_value()) {
            return Status(ErrorCode::contract_violation,
                          "M11 peg regime requires an anchor");
        }
        const auto anchor = static_cast<std::size_t>(
            external.peg_anchor->value());
        if (batch.external[anchor].fx_regime !=
            simulation::FxRegime::floating) {
            return Status(ErrorCode::contract_violation,
                          "M11 peg anchor must remain floating");
        }
    }
    if (peg_count > 1U) {
        return Status(ErrorCode::unsupported,
                      "M11 policy contract permits one active pegger");
    }
    return batch;
}

bool m11_policy_values_equal(
    const PolicyValue &left, const PolicyValue &right) noexcept {
    if (left.index() == right.index()) {
        return left == right;
    }
    const auto left_number = number_value(left);
    const auto right_number = number_value(right);
    return left_number.has_value() && right_number.has_value() &&
           *left_number == *right_number;
}

Result<double>
m11_policy_numeric_distance(
    const PolicyLeverDescriptor &lever,
    const PolicyValue &left,
    const PolicyValue &right) noexcept {
    if (m11_policy_values_equal(left, right)) {
        return 0.0;
    }
    const auto before = number_value(left);
    const auto after = number_value(right);
    if (!lever.control_scale.has_value() ||
        !before.has_value() || !after.has_value()) {
        return 1.0;
    }
    const auto distance =
        std::abs(*after - *before) / *lever.control_scale;
    if (!std::isfinite(distance)) {
        return Status(ErrorCode::out_of_range,
                      "M11 policy distance is not finite");
    }
    return distance;
}

} // namespace macro_sim::control
