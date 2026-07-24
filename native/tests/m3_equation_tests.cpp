#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

#include "macro_sim/algorithms/behavior.hpp"
#include "macro_sim/algorithms/shock_overlay.hpp"
#include "macro_sim/algorithms/valuation.hpp"
#include "macro_sim/algorithms/vital_rates.hpp"

namespace {

using namespace macro_sim::algorithms;

template <typename T>
[[nodiscard]] T take(macro_sim::Result<T> result) {
    assert(result.ok());
    return std::move(result).take();
}

void near(double actual, double expected, double tolerance = 1.0e-10) {
    assert(std::isfinite(actual));
    assert(std::abs(actual - expected) <= tolerance);
}

void test_expectations_and_technology() {
    near(take(adaptive_expectation(10.0, 14.0, 0.25)), 11.0);
    near(take(demand_expectation(10.0, 8.0, 4.0, 0.5)), 11.0);
    near(take(adaptive_expectation(2.0, -10.0, 1.0)), 0.0);

    ProductionInput linear;
    linear.labor = 4.0;
    linear.linear_productivity = 2.5;
    linear.public_capital_factor = 1.2;
    near(take(production(linear)), 12.0);

    ProductionInput cobb;
    cobb.technology = ProductionTechnology::cobb_douglas;
    cobb.labor = 9.0;
    cobb.total_factor_productivity = 2.0;
    cobb.capital = 16.0;
    cobb.capital_share = 0.5;
    near(take(production(cobb)), 24.0);

    LaborDemandInput inverse;
    inverse.technology = ProductionTechnology::cobb_douglas;
    inverse.output_target = 24.0;
    inverse.total_factor_productivity = 2.0;
    inverse.capital = 16.0;
    inverse.capital_share = 0.5;
    near(take(labor_demand(inverse)), 9.0);
}

void test_costs_and_plans() {
    const CapitalServiceInput service{3.0, 0.02, 100.0, 0.08};
    near(take(capital_service_cost(service)), 30.0);
    near(
        take(capital_service_unit_cost({service, 12.0, 15.0})),
        2.0
    );

    UnitCostInput cost;
    cost.wage = 6.0;
    cost.linear_productivity = 3.0;
    cost.production_target = 20.0;
    cost.labor_demand = 8.0;
    cost.energy_intensity = 0.2;
    cost.energy_average_cost = 5.0;
    cost.diseconomy_slope = 0.01;
    cost.capital_unit_cost = 0.5;
    near(take(unit_cost(cost)), 4.58);

    const auto output = take(production_plan({10.0, 2.0, 7.0, 0.25}));
    near(output.target_inventory, 20.0);
    near(output.production_target, 13.25);

    WagePlanInput wage;
    wage.wage = 10.0;
    wage.hired_previous = 4.0;
    wage.labor_demand_previous = 5.0;
    wage.shortage_adjustment = 0.1;
    wage.calvo_probability = 0.5;
    wage.calvo_draw = 0.2;
    wage.minimum_wage = 11.5;
    const auto wage_output = take(wage_plan(wage));
    near(wage_output.target, 11.0);
    near(wage_output.posted, 11.5);
    assert(wage_output.rationed);
    assert(wage_output.repriced);
    assert(wage_output.minimum_bound);

    PricePlanInput price;
    price.posted_price = 8.0;
    price.markup = 0.2;
    price.markup_min = 0.1;
    price.markup_max = 0.4;
    price.markup_adjustment = 0.05;
    price.target_inventory_previous = 5.0;
    price.inventory = 3.0;
    price.unit_cost = 10.0;
    price.calvo_probability = 0.8;
    price.calvo_draw = 0.1;
    const auto price_output = take(price_plan(price));
    near(price_output.markup, 0.25);
    near(price_output.target, 12.5);
    near(price_output.posted, 12.5);
}

void test_investment_and_credit() {
    InvestmentUserCostInput user_cost;
    user_cost.nominal_loan_rate = 0.06;
    user_cost.expected_inflation = 0.02;
    user_cost.neutral_nominal_rate = 0.04;
    user_cost.inflation_target = 0.02;
    user_cost.depreciation = 0.01;
    user_cost.elasticity = 1.0;
    near(take(investment_user_cost_multiplier(user_cost)), 0.6);

    InvestmentPlanInput investment;
    investment.invests = true;
    investment.capital_output_ratio = 2.0;
    investment.demand_expected = 10.0;
    investment.adjustment_speed = 0.5;
    investment.capital = 12.0;
    investment.depreciation = 0.1;
    investment.tobin_q = 1.5;
    investment.q_response = 0.5;
    investment.user_cost = user_cost;
    near(take(investment_plan(investment)), 3.9);

    near(
        take(firm_credit_request({4.0, 5.0, 3.0, 2.0, 8.0})),
        18.0
    );
    const DebtServiceHeadroomInput headroom{12.0, 10.0, 0.05, 0.05, 1.2};
    near(take(firm_debt_service_headroom(headroom)), 90.0);

    CreditGrantInput grant;
    grant.requested = 40.0;
    grant.deposits = 100.0;
    grant.debt = 20.0;
    grant.leverage_limit = 1.0;
    grant.borrowing_base = 45.0;
    grant.debt_service = headroom;
    near(take(credit_grant(grant)), 25.0);

    const auto service = take(debt_service({100.0, 15.0, 0.05, 0.1}));
    near(service.principal, 10.0);
    near(service.interest, 5.0);
}

void test_household_and_valuation() {
    ConsumptionPlanInput consumption;
    consumption.income_propensity = 0.8;
    consumption.wealth_propensity = 0.1;
    consumption.expected_income = 10.0;
    consumption.deposits_previous = 16.0;
    consumption.curvature = 0.5;
    consumption.wealth_reference = 4.0;
    near(take(consumption_plan(consumption)), 8.8);

    const HouseholdDebtServiceInput household_service{
        100.0,
        20.0,
        0.02,
        0.1,
        3.0,
    };
    near(take(household_contractual_debt_service(household_service)), 13.0);
    near(
        take(reserve_household_debt_service(
            40.0,
            45.0,
            household_service
        )),
        32.0
    );

    EquityDemandInput equity;
    equity.price = 10.0;
    equity.fundamental = 12.0;
    equity.deposits = 100.0;
    equity.shares = 5.0;
    equity.fundamental_weight = 0.5;
    equity.target_equity_share = 0.4;
    near(take(equity_demand(equity)), 1.6);

    const auto household_credit = take(
        household_credit_request(8.0, 12.0, 2.0, 4.0)
    );
    near(household_credit.target, 12.0);
    near(household_credit.request, 6.0);

    near(take(floor_safe_price_return(0.0, 1.0)), 0.0);
    near(take(floor_safe_price_return(10.0, 12.0)), 0.2);
    near(
        take(valuation_discount_rate({0.01, -0.02, 0.03})),
        0.03
    );
    near(
        take(residual_income_fundamental({100.0, 10.0, 20.0, 0.1})),
        10.0
    );
    near(take(bond_price({100.0, 2, 0.1, 0.05})), 91.32231404958677);
}

void test_vital_rates() {
    const VitalRates rates;
    near(take(female_birth_share(rates)), 1.0 / 2.05);
    near(take(male_birth_share(rates)), 1.05 / 2.05);
    const double integral = take(mortality_integral(rates, 0.0, 1.0));
    assert(integral > 0.0102 && integral < 0.0105);
    near(
        take(survival_probability(rates, 0.0, 1.0)),
        std::exp(-integral)
    );
    near(
        take(fertility_rate(rates, 28.0)),
        rates.total_fertility_rate
            * take(fertility_shape_rate(rates, 28.0))
    );
    const double life = take(expected_life_at_birth(rates));
    assert(life > 70.0 && life < 100.0);
}

void test_shock_overlay() {
    std::vector<ShockOverlayEntry> entries{
        {
            "b-demand",
            ShockChannel::household_demand,
            std::nullopt,
            SectorScope::all,
            5,
            4,
            2,
            2,
            0.2,
        },
        {
            "a-productivity",
            ShockChannel::productivity,
            macro_sim::EconomyId(2),
            SectorScope::consumption,
            3,
            std::nullopt,
            0,
            0,
            0.1,
        },
        {
            "c-productivity",
            ShockChannel::productivity,
            macro_sim::EconomyId(2),
            SectorScope::necessity,
            3,
            std::nullopt,
            0,
            0,
            -0.5,
        },
    };
    const auto overlay = take(ShockOverlay::create(std::move(entries)));
    near(
        take(overlay.factor(
            ShockChannel::productivity,
            macro_sim::EconomyId(2),
            SectorScope::necessity,
            3
        )),
        0.9 * 1.5
    );
    near(
        take(overlay.factor(
            ShockChannel::productivity,
            macro_sim::EconomyId(1),
            SectorScope::necessity,
            3
        )),
        1.0
    );
    near(
        take(overlay.factor(
            ShockChannel::household_demand,
            macro_sim::EconomyId(1),
            SectorScope::all,
            5
        )),
        0.9
    );
    near(
        take(overlay.factor(
            ShockChannel::household_demand,
            macro_sim::EconomyId(1),
            SectorScope::all,
            8
        )),
        0.9
    );
    near(
        take(overlay.factor(
            ShockChannel::household_demand,
            macro_sim::EconomyId(1),
            SectorScope::all,
            9
        )),
        1.0
    );
}

void test_invalid_inputs() {
    assert(!adaptive_expectation(
        1.0,
        std::numeric_limits<double>::quiet_NaN(),
        0.5
    ).ok());
    ProductionInput invalid_production;
    invalid_production.technology = ProductionTechnology::cobb_douglas;
    invalid_production.labor = 1.0;
    invalid_production.capital = 0.0;
    assert(!production(invalid_production).ok());
    assert(!wage_plan(WagePlanInput{}).ok());
    assert(!ShockOverlay::create({
        {
            "",
            ShockChannel::productivity,
            std::nullopt,
            SectorScope::all,
            0,
            std::nullopt,
            0,
            0,
            0.1,
        },
    }).ok());
}

}  // namespace

int main() {
    test_expectations_and_technology();
    test_costs_and_plans();
    test_investment_and_credit();
    test_household_and_valuation();
    test_vital_rates();
    test_shock_overlay();
    test_invalid_inputs();
    return 0;
}
