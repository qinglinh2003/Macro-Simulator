#ifndef MACRO_SIM_GENERATED_INVALID_CASES_HPP
#define MACRO_SIM_GENERATED_INVALID_CASES_HPP

#include <array>
#include <cstdint>
#include <string_view>

#include "macro_sim/generated/contracts.hpp"

namespace macro_sim::generated {

enum class InvalidInputKind : std::uint8_t { null_value, boolean, integer, number, string, nonfinite };
struct InvalidContractCase final {
    std::string_view id;
    std::string_view contract_id;
    InvalidInputKind input_kind;
    double number;
    std::string_view text;
    ValidationCode expected;
};

inline constexpr std::array<InvalidContractCase, 10> kInvalidContractCases{{
    {"invalid.unknown-contract", "policy.not_a_real_lever", InvalidInputKind::number, 0, "", ValidationCode::unknown_contract},
    {"invalid.number-type", "config.a", InvalidInputKind::string, 0, "not-a-number", ValidationCode::type_mismatch},
    {"invalid.boolean-type", "config.bank_capital_constraint", InvalidInputKind::integer, 1, "", ValidationCode::type_mismatch},
    {"invalid.integer-type", "config.bank_entry_max", InvalidInputKind::number, 1.5, "", ValidationCode::type_mismatch},
    {"invalid.choice", "policy.energy_rationing", InvalidInputKind::string, 0, "not-a-choice", ValidationCode::invalid_choice},
    {"invalid.nonfinite", "config.a", InvalidInputKind::nonfinite, 0, "", ValidationCode::nonfinite},
    {"invalid.null", "config.a", InvalidInputKind::null_value, 0, "", ValidationCode::type_mismatch},
    {"invalid.below-minimum", "policy.bank_bond_duration_limit", InvalidInputKind::number, -1, "", ValidationCode::below_minimum},
    {"invalid.above-maximum", "policy.bank_bond_duration_limit", InvalidInputKind::number, 21, "", ValidationCode::above_maximum},
    {"invalid.nullable-number-type", "config.world.immigration_cap", InvalidInputKind::string, 0, "none", ValidationCode::type_mismatch},
}};

}  // namespace macro_sim::generated

#endif
