#include "macro_sim/algorithms/behavior.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

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

[[nodiscard]] double dead_zone_sign(double value) noexcept {
    if (value > kEconomicEpsilon) {
        return 1.0;
    }
    if (value < -kEconomicEpsilon) {
        return -1.0;
    }
    return 0.0;
}

[[nodiscard]] bool valid_probability(double value) noexcept {
    return std::isfinite(value) && value >= 0.0 && value <= 1.0;
}

}  // namespace

Result<double> adaptive_expectation(
    double previous,
    double observed,
    double adjustment
) noexcept {
    if (!all_finite(std::array{previous, observed, adjustment})) {
        return invalid("expectation inputs must be finite");
    }
    return std::max(0.0, previous + adjustment * (observed - previous));
}

Result<double> demand_expectation(
    double previous,
    double sales_previous,
    double rationed_previous,
    double adjustment
) noexcept {
    if (!all_finite(
            std::array{
                previous,
                sales_previous,
                rationed_previous,
                adjustment,
            }
        )) {
        return invalid("demand expectation inputs must be finite");
    }
    const double signal = sales_previous + rationed_previous;
    return std::max(0.0, previous + adjustment * (signal - previous));
}

Result<double> production(const ProductionInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.labor,
                input.linear_productivity,
                input.total_factor_productivity,
                input.capital,
                input.capital_share,
                input.public_capital_factor,
            }
        )) {
        return invalid("production inputs must be finite");
    }
    if (input.labor <= 0.0) {
        return 0.0;
    }
    if (input.public_capital_factor <= 0.0) {
        return invalid("public capital factor must be positive");
    }
    if (input.technology == ProductionTechnology::linear) {
        if (input.linear_productivity <= 0.0) {
            return invalid("linear productivity must be positive");
        }
        return input.linear_productivity * input.labor
            * input.public_capital_factor;
    }
    if (
        input.total_factor_productivity <= 0.0
        || input.capital <= 0.0
        || input.capital_share < 0.0
        || input.capital_share >= 1.0
    ) {
        return invalid("invalid Cobb-Douglas production inputs");
    }
    return input.total_factor_productivity
        * std::pow(input.capital, input.capital_share)
        * std::pow(input.labor, 1.0 - input.capital_share)
        * input.public_capital_factor;
}

Result<double> labor_demand(const LaborDemandInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.output_target,
                input.linear_productivity,
                input.total_factor_productivity,
                input.capital,
                input.capital_share,
                input.public_capital_factor,
            }
        )) {
        return invalid("labor demand inputs must be finite");
    }
    if (input.output_target <= kEconomicEpsilon) {
        return 0.0;
    }
    if (input.public_capital_factor <= 0.0) {
        return invalid("public capital factor must be positive");
    }
    const double adjusted_target =
        input.output_target / input.public_capital_factor;
    if (input.technology == ProductionTechnology::linear) {
        if (input.linear_productivity <= 0.0) {
            return invalid("linear productivity must be positive");
        }
        return adjusted_target / input.linear_productivity;
    }
    if (
        input.total_factor_productivity <= 0.0
        || input.capital <= 0.0
        || input.capital_share < 0.0
        || input.capital_share >= 1.0
    ) {
        return invalid("invalid Cobb-Douglas labor demand inputs");
    }
    return std::pow(
        adjusted_target
            / (
                input.total_factor_productivity
                * std::pow(input.capital, input.capital_share)
            ),
        1.0 / (1.0 - input.capital_share)
    );
}

Result<double> capital_service_cost(
    const CapitalServiceInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.replacement_price,
                input.opportunity_rate,
                input.capital,
                input.depreciation,
            }
        )) {
        return invalid("capital service inputs must be finite");
    }
    const double capital_value =
        std::max(0.0, input.replacement_price)
        * std::max(0.0, input.capital);
    const double service_rate =
        std::max(0.0, input.depreciation)
        + std::max(0.0, input.opportunity_rate);
    return capital_value * service_rate;
}

Result<double> capital_service_unit_cost(
    const CapitalServiceUnitCostInput& input
) noexcept {
    if (!all_finite(
            std::array{input.production_target, input.minimum_output}
        )) {
        return invalid("capital unit cost output inputs must be finite");
    }
    const double output =
        std::max(input.production_target, input.minimum_output);
    if (output <= kEconomicEpsilon) {
        return 0.0;
    }
    auto cost = capital_service_cost(input.service);
    if (!cost.ok()) {
        return cost.status();
    }
    return std::move(cost).take() / output;
}

Result<double> unit_cost(const UnitCostInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.wage,
                input.linear_productivity,
                input.total_factor_productivity,
                input.capital,
                input.capital_share,
                input.production_target,
                input.labor_demand,
                input.energy_intensity,
                input.energy_average_cost,
                input.diseconomy_slope,
                input.capital_unit_cost,
            }
        )) {
        return invalid("unit cost inputs must be finite");
    }
    if (input.wage <= 0.0 || input.linear_productivity <= 0.0) {
        return invalid("wage and linear productivity must be positive");
    }
    double base = 0.0;
    if (
        input.production_target > kEconomicEpsilon
        && (
            input.productivity_adjusted
            || input.technology != ProductionTechnology::linear
        )
    ) {
        base = input.wage * input.labor_demand / input.production_target;
    } else if (input.technology == ProductionTechnology::linear) {
        base = input.wage / input.linear_productivity;
    } else {
        if (
            input.total_factor_productivity <= 0.0
            || input.capital <= 0.0
            || input.capital_share < 0.0
            || input.capital_share >= 1.0
        ) {
            return invalid("invalid Cobb-Douglas unit cost inputs");
        }
        base = input.wage
            / (
                input.total_factor_productivity
                * std::pow(input.capital, input.capital_share)
            );
    }
    base += input.energy_intensity * input.energy_average_cost;
    const double variable =
        base * (1.0 + input.diseconomy_slope * input.production_target);
    return variable + std::max(0.0, input.capital_unit_cost);
}

Result<ProductionPlanResult> production_plan(
    const ProductionPlanInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.demand_expected,
                input.inventory_ratio,
                input.inventory,
                input.gap_close,
            }
        )) {
        return invalid("production plan inputs must be finite");
    }
    const double target_inventory =
        input.inventory_ratio * input.demand_expected;
    const double gap = target_inventory - input.inventory;
    return ProductionPlanResult{
        target_inventory,
        std::max(0.0, input.demand_expected + input.gap_close * gap),
    };
}

Result<WagePlanResult> wage_plan(const WagePlanInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.wage,
                input.hired_previous,
                input.labor_demand_previous,
                input.shortage_adjustment,
                input.calvo_probability,
                input.calvo_draw,
                input.minimum_wage,
                input.downward_drift,
                input.expected_inflation,
                input.wage_indexation,
            }
        )) {
        return invalid("wage plan inputs must be finite");
    }
    if (
        input.wage <= 0.0
        || !valid_probability(input.calvo_probability)
        || !valid_probability(input.calvo_draw)
        || input.shortage_adjustment < 0.0
        || input.downward_drift < 0.0
        || input.downward_drift >= 1.0
    ) {
        return invalid("invalid wage or Calvo inputs");
    }
    const double drift = input.wage_indexation * input.expected_inflation;
    const bool rationed =
        input.hired_previous
        < input.labor_demand_previous - kEconomicEpsilon;
    const double indexed_gross = 1.0 + drift;
    if (!std::isfinite(indexed_gross) || indexed_gross <= 0.0) {
        return invalid("wage indexation produced a nonpositive gross factor");
    }
    double target = input.wage * indexed_gross;
    if (rationed) {
        target = input.wage * (indexed_gross + input.shortage_adjustment);
    } else if (
        input.downward_drift > 0.0
        && input.labor_demand_previous > kEconomicEpsilon
    ) {
        target = input.wage * (indexed_gross - input.downward_drift);
        if (target <= 0.0) {
            // Preserve the established additive rule over its ordinary range.
            // In severe deflation its two individually valid adjustments can
            // sum past -100%; sequential proportional composition supplies a
            // positive limiting rule without changing ordinary trajectories.
            target = input.wage * indexed_gross * (1.0 - input.downward_drift);
        }
    }
    const bool repriced = input.calvo_draw < input.calvo_probability;
    double posted = repriced ? target : input.wage;
    const bool minimum_bound =
        input.minimum_wage > 0.0 && posted < input.minimum_wage;
    if (minimum_bound) {
        posted = input.minimum_wage;
    }
    if (!std::isfinite(posted) || posted <= 0.0) {
        return invalid("wage plan produced a nonpositive wage");
    }
    return WagePlanResult{
        target,
        posted,
        rationed,
        repriced,
        minimum_bound,
    };
}

Result<PricePlanResult> price_plan(const PricePlanInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.posted_price,
                input.markup,
                input.markup_min,
                input.markup_max,
                input.markup_adjustment,
                input.target_inventory_previous,
                input.inventory,
                input.unit_cost,
                input.calvo_probability,
                input.calvo_draw,
            }
        )) {
        return invalid("price plan inputs must be finite");
    }
    if (
        input.posted_price <= 0.0
        || input.unit_cost < 0.0
        || input.markup_min > input.markup_max
        || !valid_probability(input.calvo_probability)
        || !valid_probability(input.calvo_draw)
    ) {
        return invalid("invalid price plan inputs");
    }
    const double signal = dead_zone_sign(
        input.target_inventory_previous - input.inventory
    );
    const double markup = std::clamp(
        input.markup + input.markup_adjustment * signal,
        input.markup_min,
        input.markup_max
    );
    const double target = (1.0 + markup) * input.unit_cost;
    const bool repriced = input.calvo_draw < input.calvo_probability;
    const double posted = repriced ? target : input.posted_price;
    if (!std::isfinite(posted) || posted <= 0.0) {
        return invalid("price plan produced a nonpositive price");
    }
    return PricePlanResult{markup, target, posted, repriced};
}

Result<double> investment_user_cost_multiplier(
    const InvestmentUserCostInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.nominal_loan_rate,
                input.expected_inflation,
                input.neutral_nominal_rate,
                input.inflation_target,
                input.depreciation,
                input.elasticity,
                input.multiplier_min,
                input.multiplier_max,
                input.user_cost_floor,
            }
        )) {
        return invalid("user cost inputs must be finite");
    }
    if (
        input.multiplier_min > input.multiplier_max
        || input.user_cost_floor <= 0.0
    ) {
        return invalid("invalid user cost bounds");
    }
    if (input.elasticity <= 0.0) {
        return 1.0;
    }
    const double current = std::max(
        input.user_cost_floor,
        std::max(0.0, input.nominal_loan_rate)
            - input.expected_inflation
            + std::max(0.0, input.depreciation)
    );
    const double neutral = std::max(
        input.user_cost_floor,
        std::max(0.0, input.neutral_nominal_rate)
            - input.inflation_target
            + std::max(0.0, input.depreciation)
    );
    const double response = std::pow(
        current / neutral,
        -input.elasticity
    );
    return std::clamp(
        response,
        input.multiplier_min,
        input.multiplier_max
    );
}

Result<double> investment_plan(const InvestmentPlanInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.capital_output_ratio,
                input.demand_expected,
                input.adjustment_speed,
                input.capital,
                input.depreciation,
                input.tobin_q,
                input.q_response,
                input.q_floor,
                input.q_cap,
            }
        )) {
        return invalid("investment plan inputs must be finite");
    }
    if (!input.invests) {
        return 0.0;
    }
    if (input.q_floor > input.q_cap) {
        return invalid("invalid Tobin q bounds");
    }
    const double desired_capital =
        input.capital_output_ratio * input.demand_expected;
    double target = std::max(
        0.0,
        input.adjustment_speed * (desired_capital - input.capital)
            + input.depreciation * input.capital
    );
    if (input.q_response > 0.0) {
        const double multiplier = std::clamp(
            1.0 + input.q_response * (input.tobin_q - 1.0),
            input.q_floor,
            input.q_cap
        );
        target *= multiplier;
    }
    if (input.user_cost.has_value()) {
        auto multiplier = investment_user_cost_multiplier(*input.user_cost);
        if (!multiplier.ok()) {
            return multiplier.status();
        }
        target *= std::move(multiplier).take();
    }
    return target;
}

Result<double> firm_credit_request(
    const FirmCreditRequestInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.wage,
                input.labor_demand,
                input.investment_target,
                input.capital_goods_price,
                input.deposits,
            }
        )) {
        return invalid("firm credit request inputs must be finite");
    }
    const double wage_need = input.wage * input.labor_demand;
    const double investment_need =
        input.investment_target * std::max(0.0, input.capital_goods_price);
    return std::max(0.0, wage_need + investment_need - input.deposits);
}

Result<double> firm_debt_service_headroom(
    const DebtServiceHeadroomInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.expected_operating_cash_flow,
                input.debt,
                input.loan_rate,
                input.amortization,
                input.minimum_dscr,
            }
        )) {
        return invalid("debt service headroom inputs must be finite");
    }
    const double service_rate =
        std::max(0.0, input.loan_rate)
        + std::max(0.0, input.amortization);
    if (service_rate <= kEconomicEpsilon) {
        return std::numeric_limits<double>::infinity();
    }
    const double supported_total_debt =
        std::max(0.0, input.expected_operating_cash_flow)
        / (std::max(1.0, input.minimum_dscr) * service_rate);
    return std::max(0.0, supported_total_debt - std::max(0.0, input.debt));
}

Result<double> credit_grant(const CreditGrantInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.requested,
                input.deposits,
                input.debt,
                input.leverage_limit,
            }
        )) {
        return invalid("credit grant inputs must be finite");
    }
    if (
        (input.book_equity.has_value()
            && !std::isfinite(*input.book_equity))
        || (
            input.borrowing_base.has_value()
            && !std::isfinite(*input.borrowing_base)
        )
    ) {
        return invalid("optional credit grant inputs must be finite");
    }
    const double net_worth = input.book_equity.value_or(
        input.deposits - input.debt
    );
    if (net_worth <= 0.0) {
        return 0.0;
    }
    double room = input.leverage_limit * net_worth - input.debt;
    if (input.borrowing_base.has_value()) {
        room = std::min(
            room,
            std::max(0.0, *input.borrowing_base) - input.debt
        );
    }
    if (input.debt_service.has_value()) {
        auto headroom = firm_debt_service_headroom(*input.debt_service);
        if (!headroom.ok()) {
            return headroom.status();
        }
        room = std::min(room, std::move(headroom).take());
    }
    return std::max(0.0, std::min(input.requested, room));
}

Result<DebtServiceResult> debt_service(
    const DebtServiceInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.debt,
                input.deposits,
                input.loan_rate,
                input.amortization,
            }
        )) {
        return invalid("debt service inputs must be finite");
    }
    if (input.debt <= kEconomicEpsilon) {
        return DebtServiceResult{};
    }
    const double principal =
        std::min(input.amortization * input.debt, input.deposits);
    const double interest = std::min(
        input.loan_rate * input.debt,
        input.deposits - principal
    );
    return DebtServiceResult{principal, interest};
}

Result<double> consumption_plan(
    const ConsumptionPlanInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.income_propensity,
                input.wealth_propensity,
                input.expected_income,
                input.deposits_previous,
                input.equity_wealth,
                input.curvature,
                input.wealth_reference,
            }
        )) {
        return invalid("consumption plan inputs must be finite");
    }
    if (input.curvature < 1.0 && input.wealth_reference <= 0.0) {
        return invalid("wealth reference must be positive for concave wealth");
    }
    const double wealth = input.deposits_previous + input.equity_wealth;
    double wealth_term = input.wealth_propensity * wealth;
    if (input.curvature < 1.0) {
        wealth_term =
            input.wealth_propensity
            * input.wealth_reference
            * std::pow(
                std::max(0.0, wealth) / input.wealth_reference,
                input.curvature
            );
    }
    return std::max(
        0.0,
        input.income_propensity * input.expected_income + wealth_term
    );
}

Result<double> household_contractual_debt_service(
    const HouseholdDebtServiceInput& input
) noexcept {
    if (!all_finite(
            std::array{
                input.debt,
                input.margin_debt,
                input.loan_rate,
                input.amortization,
                input.interest_arrears,
            }
        )) {
        return invalid("household debt service inputs must be finite");
    }
    const double live_debt = std::max(0.0, input.debt);
    const double margin =
        std::min(live_debt, std::max(0.0, input.margin_debt));
    const double amortizing = live_debt - margin;
    return std::max(0.0, input.interest_arrears)
        + std::max(0.0, input.amortization) * amortizing
        + std::max(0.0, input.loan_rate) * live_debt;
}

Result<double> reserve_household_debt_service(
    double consumption_budget,
    double deposits,
    const HouseholdDebtServiceInput& input
) noexcept {
    if (!all_finite(std::array{consumption_budget, deposits})) {
        return invalid("household debt reservation inputs must be finite");
    }
    auto service = household_contractual_debt_service(input);
    if (!service.ok()) {
        return service.status();
    }
    const double spendable_cash =
        std::max(0.0, deposits - std::move(service).take());
    return std::min(std::max(0.0, consumption_budget), spendable_cash);
}

Result<double> equity_demand(const EquityDemandInput& input) noexcept {
    if (!all_finite(
            std::array{
                input.price,
                input.fundamental,
                input.trend,
                input.deposits,
                input.shares,
                input.fundamental_weight,
                input.chartist_weight,
                input.target_equity_share,
            }
        )) {
        return invalid("equity demand inputs must be finite");
    }
    if (input.price <= kEconomicEpsilon) {
        return 0.0;
    }
    const double wealth = input.deposits + input.shares * input.price;
    const double pressure =
        input.fundamental_weight
            * (input.fundamental - input.price) / input.price
        + input.chartist_weight * input.trend;
    const double target_share = std::clamp(
        input.target_equity_share * (1.0 + pressure),
        0.0,
        0.95
    );
    const double desired =
        target_share * wealth / input.price - input.shares;
    if (desired > 0.0) {
        return std::min(desired, input.deposits / input.price);
    }
    return std::max(desired, -input.shares);
}

Result<HouseholdCreditResult> household_credit_request(
    double consumption_budget,
    double subsistence,
    double deposits,
    double expected_income
) noexcept {
    if (!all_finite(
            std::array{
                consumption_budget,
                subsistence,
                deposits,
                expected_income,
            }
        )) {
        return invalid("household credit request inputs must be finite");
    }
    const double target = std::max(consumption_budget, subsistence);
    return HouseholdCreditResult{
        target,
        std::max(0.0, target - deposits - expected_income),
    };
}

}  // namespace macro_sim::algorithms
