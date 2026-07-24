#ifndef MACRO_SIM_CORE_INVARIANTS_HPP
#define MACRO_SIM_CORE_INVARIANTS_HPP

#include <cstdint>
#include <string_view>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"

namespace macro_sim::core {

enum class InvariantId : std::uint8_t {
    finite_state = 0,
    nonnegative_balances = 1,
    deposit_conservation = 2,
    reserve_conservation = 3,
    loan_ownership = 4,
    ownership_lots = 5,
};

[[nodiscard]] constexpr std::string_view invariant_id_name(
    InvariantId id
) noexcept {
    switch (id) {
        case InvariantId::finite_state:
            return "invariant.m2.finite-state";
        case InvariantId::nonnegative_balances:
            return "invariant.ledger.nonnegative-balances";
        case InvariantId::deposit_conservation:
            return "invariant.ledger.deposit-conservation";
        case InvariantId::reserve_conservation:
            return "invariant.ledger.reserve-conservation";
        case InvariantId::loan_ownership:
            return "invariant.m2.loan-ownership";
        case InvariantId::ownership_lots:
            return "invariant.m2.ownership-lots";
    }
    return "invariant.m2.unknown";
}

struct InvariantReport final {
    Status status{};
    InvariantId failed{InvariantId::finite_state};
    double observed{0.0};
    double expected{0.0};
    double tolerance{0.0};

    [[nodiscard]] bool ok() const noexcept {
        return status.ok();
    }
};

[[nodiscard]] InvariantReport run_invariants(
    const RootState& state
) noexcept;

}  // namespace macro_sim::core

#endif
