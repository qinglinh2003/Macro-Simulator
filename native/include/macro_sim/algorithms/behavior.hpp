#ifndef MACRO_SIM_ALGORITHMS_BEHAVIOR_HPP
#define MACRO_SIM_ALGORITHMS_BEHAVIOR_HPP

#include <optional>

#include "macro_sim/error.hpp"

namespace macro_sim::algorithms {

inline constexpr double kEconomicEpsilon = 1.0e-9;

enum class ProductionTechnology {
    linear = 0,
    cobb_douglas = 1,
};

struct ProductionInput final {
    ProductionTechnology technology{ProductionTechnology::linear};
    double labor{0.0};
    double linear_productivity{1.0};
    double total_factor_productivity{1.0};
    double capital{0.0};
    double capital_share{0.3};
    double public_capital_factor{1.0};
};

struct LaborDemandInput final {
    ProductionTechnology technology{ProductionTechnology::linear};
    double output_target{0.0};
    double linear_productivity{1.0};
    double total_factor_productivity{1.0};
    double capital{0.0};
    double capital_share{0.3};
    double public_capital_factor{1.0};
};

struct CapitalServiceInput final {
    double replacement_price{0.0};
    double opportunity_rate{0.0};
    double capital{0.0};
    double depreciation{0.0};
};

struct CapitalServiceUnitCostInput final {
    CapitalServiceInput service{};
    double production_target{0.0};
    double minimum_output{0.0};
};

struct UnitCostInput final {
    ProductionTechnology technology{ProductionTechnology::linear};
    double wage{0.0};
    double linear_productivity{1.0};
    double total_factor_productivity{1.0};
    double capital{0.0};
    double capital_share{0.3};
    double production_target{0.0};
    double labor_demand{0.0};
    double energy_intensity{0.0};
    double energy_average_cost{0.0};
    double diseconomy_slope{0.0};
    double capital_unit_cost{0.0};
    bool productivity_adjusted{true};
};

struct ProductionPlanInput final {
    double demand_expected{0.0};
    double inventory_ratio{0.0};
    double inventory{0.0};
    double gap_close{1.0};
};

struct ProductionPlanResult final {
    double target_inventory{0.0};
    double production_target{0.0};
};

struct WagePlanInput final {
    double wage{0.0};
    double hired_previous{0.0};
    double labor_demand_previous{0.0};
    double shortage_adjustment{0.0};
    double calvo_probability{0.0};
    double calvo_draw{0.0};
    double minimum_wage{0.0};
    double downward_drift{0.0};
    double expected_inflation{0.0};
    double wage_indexation{0.0};
};

struct WagePlanResult final {
    double target{0.0};
    double posted{0.0};
    bool rationed{false};
    bool repriced{false};
    bool minimum_bound{false};
};

struct PricePlanInput final {
    double posted_price{0.0};
    double markup{0.0};
    double markup_min{0.0};
    double markup_max{0.0};
    double markup_adjustment{0.0};
    double target_inventory_previous{0.0};
    double inventory{0.0};
    double unit_cost{0.0};
    double calvo_probability{0.0};
    double calvo_draw{0.0};
};

struct PricePlanResult final {
    double markup{0.0};
    double target{0.0};
    double posted{0.0};
    bool repriced{false};
};

struct InvestmentUserCostInput final {
    double nominal_loan_rate{0.0};
    double expected_inflation{0.0};
    double neutral_nominal_rate{0.0};
    double inflation_target{0.0};
    double depreciation{0.0};
    double elasticity{0.0};
    double multiplier_min{0.5};
    double multiplier_max{1.5};
    double user_cost_floor{1.0e-9};
};

struct InvestmentPlanInput final {
    bool invests{false};
    double capital_output_ratio{0.0};
    double demand_expected{0.0};
    double adjustment_speed{0.0};
    double capital{0.0};
    double depreciation{0.0};
    double tobin_q{1.0};
    double q_response{0.0};
    double q_floor{0.5};
    double q_cap{2.0};
    std::optional<InvestmentUserCostInput> user_cost{};
};

struct FirmCreditRequestInput final {
    double wage{0.0};
    double labor_demand{0.0};
    double investment_target{0.0};
    double capital_goods_price{0.0};
    double deposits{0.0};
};

struct DebtServiceHeadroomInput final {
    double expected_operating_cash_flow{0.0};
    double debt{0.0};
    double loan_rate{0.0};
    double amortization{0.0};
    double minimum_dscr{1.0};
};

struct CreditGrantInput final {
    double requested{0.0};
    double deposits{0.0};
    double debt{0.0};
    double leverage_limit{0.0};
    std::optional<double> book_equity{};
    std::optional<double> borrowing_base{};
    std::optional<DebtServiceHeadroomInput> debt_service{};
};

struct DebtServiceInput final {
    double debt{0.0};
    double deposits{0.0};
    double loan_rate{0.0};
    double amortization{0.0};
};

struct DebtServiceResult final {
    double principal{0.0};
    double interest{0.0};
};

struct ConsumptionPlanInput final {
    double income_propensity{0.0};
    double wealth_propensity{0.0};
    double expected_income{0.0};
    double deposits_previous{0.0};
    double equity_wealth{0.0};
    double curvature{1.0};
    double wealth_reference{1.0};
};

struct HouseholdDebtServiceInput final {
    double debt{0.0};
    double margin_debt{0.0};
    double loan_rate{0.0};
    double amortization{0.0};
    double interest_arrears{0.0};
};

struct EquityDemandInput final {
    double price{0.0};
    double fundamental{0.0};
    double trend{0.0};
    double deposits{0.0};
    double shares{0.0};
    double fundamental_weight{0.0};
    double chartist_weight{0.0};
    double target_equity_share{0.0};
};

struct HouseholdCreditResult final {
    double target{0.0};
    double request{0.0};
};

[[nodiscard]] Result<double> adaptive_expectation(
    double previous,
    double observed,
    double adjustment
) noexcept;

[[nodiscard]] Result<double> demand_expectation(
    double previous,
    double sales_previous,
    double rationed_previous,
    double adjustment
) noexcept;

[[nodiscard]] Result<double> production(const ProductionInput& input) noexcept;
[[nodiscard]] Result<double> labor_demand(const LaborDemandInput& input) noexcept;
[[nodiscard]] Result<double> capital_service_cost(
    const CapitalServiceInput& input
) noexcept;
[[nodiscard]] Result<double> capital_service_unit_cost(
    const CapitalServiceUnitCostInput& input
) noexcept;
[[nodiscard]] Result<double> unit_cost(const UnitCostInput& input) noexcept;
[[nodiscard]] Result<ProductionPlanResult> production_plan(
    const ProductionPlanInput& input
) noexcept;
[[nodiscard]] Result<WagePlanResult> wage_plan(
    const WagePlanInput& input
) noexcept;
[[nodiscard]] Result<PricePlanResult> price_plan(
    const PricePlanInput& input
) noexcept;
[[nodiscard]] Result<double> investment_user_cost_multiplier(
    const InvestmentUserCostInput& input
) noexcept;
[[nodiscard]] Result<double> investment_plan(
    const InvestmentPlanInput& input
) noexcept;
[[nodiscard]] Result<double> firm_credit_request(
    const FirmCreditRequestInput& input
) noexcept;
[[nodiscard]] Result<double> firm_debt_service_headroom(
    const DebtServiceHeadroomInput& input
) noexcept;
[[nodiscard]] Result<double> credit_grant(const CreditGrantInput& input) noexcept;
[[nodiscard]] Result<DebtServiceResult> debt_service(
    const DebtServiceInput& input
) noexcept;
[[nodiscard]] Result<double> consumption_plan(
    const ConsumptionPlanInput& input
) noexcept;
[[nodiscard]] Result<double> household_contractual_debt_service(
    const HouseholdDebtServiceInput& input
) noexcept;
[[nodiscard]] Result<double> reserve_household_debt_service(
    double consumption_budget,
    double deposits,
    const HouseholdDebtServiceInput& input
) noexcept;
[[nodiscard]] Result<double> equity_demand(
    const EquityDemandInput& input
) noexcept;
[[nodiscard]] Result<HouseholdCreditResult> household_credit_request(
    double consumption_budget,
    double subsistence,
    double deposits,
    double expected_income
) noexcept;

}  // namespace macro_sim::algorithms

#endif
