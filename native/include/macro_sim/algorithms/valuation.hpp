#ifndef MACRO_SIM_ALGORITHMS_VALUATION_HPP
#define MACRO_SIM_ALGORITHMS_VALUATION_HPP

#include <cstdint>

#include "macro_sim/error.hpp"

namespace macro_sim::algorithms {

struct ValuationDiscountInput final {
    double floor{0.0};
    double policy_rate{0.0};
    double risk_premium{0.0};
};

struct ResidualIncomeInput final {
    double book_value{0.0};
    double residual_income{0.0};
    double shares_outstanding{0.0};
    double discount_rate{0.0};
};

struct BondPriceInput final {
    double face{0.0};
    std::int64_t periods{0};
    double rate{0.0};
    double coupon{0.0};
};

[[nodiscard]] Result<double> floor_safe_price_return(
    double old_price,
    double new_price
) noexcept;
[[nodiscard]] Result<double> valuation_discount_rate(
    const ValuationDiscountInput& input
) noexcept;
[[nodiscard]] Result<double> residual_income_fundamental(
    const ResidualIncomeInput& input
) noexcept;
[[nodiscard]] Result<double> bond_price(const BondPriceInput& input) noexcept;

}  // namespace macro_sim::algorithms

#endif
