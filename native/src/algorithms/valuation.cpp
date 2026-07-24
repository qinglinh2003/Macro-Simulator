#include "macro_sim/algorithms/valuation.hpp"

#include <algorithm>
#include <array>
#include <cmath>

#include "macro_sim/algorithms/behavior.hpp"

namespace macro_sim::algorithms {
namespace {

template <std::size_t Size>
[[nodiscard]] bool all_finite(const std::array<double, Size>& values) noexcept {
    for (const auto value : values) {
        if (!std::isfinite(value)) {
            return false;
        }
    }
    return true;
}

[[nodiscard]] Status invalid(std::string_view message) noexcept {
    return Status(ErrorCode::invalid_argument, message);
}

}  // namespace

Result<double> floor_safe_price_return(
    double old_price,
    double new_price
) noexcept {
    if (!all_finite(std::array{old_price, new_price})) {
        return invalid("price return inputs must be finite");
    }
    if (old_price <= kEconomicEpsilon) {
        return 0.0;
    }
    return (new_price - old_price) / old_price;
}

Result<double> valuation_discount_rate(
    const ValuationDiscountInput& input
) noexcept {
    if (!all_finite(
            std::array{input.floor, input.policy_rate, input.risk_premium}
        )) {
        return invalid("valuation discount inputs must be finite");
    }
    return std::max(
        input.floor,
        std::max(0.0, input.policy_rate) + input.risk_premium
    );
}

Result<double> residual_income_fundamental(
    const ResidualIncomeInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.book_value,
                input.residual_income,
                input.shares_outstanding,
                input.discount_rate,
            }
        )) {
        return invalid("residual income inputs must be finite");
    }
    if (input.shares_outstanding <= kEconomicEpsilon) {
        return 0.0;
    }
    const double discount =
        std::max(kEconomicEpsilon, input.discount_rate);
    const double premium =
        std::max(0.0, input.residual_income) / discount;
    return std::max(
        0.0,
        (input.book_value + premium) / input.shares_outstanding
    );
}

Result<double> bond_price(const BondPriceInput& input) noexcept {
    if (!all_finite(
            std::array{input.face, input.rate, input.coupon}
        )) {
        return invalid("bond price inputs must be finite");
    }
    if (
        input.periods <= 0
        || input.rate <= -1.0 + kEconomicEpsilon
    ) {
        return input.face;
    }
    const double discount = 1.0 / (1.0 + input.rate);
    const double principal =
        input.face * std::pow(discount, static_cast<double>(input.periods));
    double coupons = 0.0;
    if (input.coupon > 0.0) {
        if (std::abs(input.rate) < 1.0e-12) {
            coupons =
                input.coupon
                * input.face
                * static_cast<double>(input.periods);
        } else {
            coupons =
                input.coupon
                * input.face
                * (
                    1.0
                    - std::pow(
                        discount,
                        static_cast<double>(input.periods)
                    )
                )
                / input.rate;
        }
    }
    return coupons + principal;
}

}  // namespace macro_sim::algorithms
