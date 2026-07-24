#ifndef MACRO_SIM_PYTHON_M3_BINDINGS_HPP
#define MACRO_SIM_PYTHON_M3_BINDINGS_HPP

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include "macro_sim/algorithms/behavior.hpp"
#include "macro_sim/algorithms/market.hpp"
#include "macro_sim/algorithms/valuation.hpp"
#include "macro_sim/algorithms/vital_rates.hpp"

namespace macro_sim::python_m3 {

namespace nb = nanobind;
using namespace macro_sim::algorithms;

inline void require_size(
    std::string_view kind,
    const std::vector<double>& values,
    std::size_t size
) {
    if (values.size() != size) {
        throw std::runtime_error(
            std::string(kind)
            + " requires "
            + std::to_string(size)
            + " values"
        );
    }
}

template <typename T>
T take(Result<T> result) {
    if (!result.ok()) {
        throw std::runtime_error(
            std::string(error_code_name(result.status().code()))
            + ": "
            + std::string(result.status().message())
        );
    }
    return std::move(result).take();
}

inline bool truth(double value) noexcept {
    return value != 0.0;
}

inline ProductionTechnology technology(double value) {
    if (value == 0.0) {
        return ProductionTechnology::linear;
    }
    if (value == 1.0) {
        return ProductionTechnology::cobb_douglas;
    }
    throw std::runtime_error("technology must be 0 or 1");
}

inline std::vector<double> evaluate_case(
    const std::string& kind,
    const std::vector<double>& v
) {
    if (kind == "adaptive_expectation") {
        require_size(kind, v, 3);
        return {take(adaptive_expectation(v[0], v[1], v[2]))};
    }
    if (kind == "demand_expectation") {
        require_size(kind, v, 4);
        return {take(demand_expectation(v[0], v[1], v[2], v[3]))};
    }
    if (kind == "production" || kind == "labor_demand") {
        require_size(kind, v, 7);
        if (kind == "production") {
            return {take(production({
                technology(v[0]),
                v[1],
                v[2],
                v[3],
                v[4],
                v[5],
                v[6],
            }))};
        }
        return {take(labor_demand({
            technology(v[0]),
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
        }))};
    }
    if (kind == "capital_service_cost") {
        require_size(kind, v, 4);
        return {take(capital_service_cost({v[0], v[1], v[2], v[3]}))};
    }
    if (kind == "capital_service_unit_cost") {
        require_size(kind, v, 6);
        return {take(capital_service_unit_cost({
            {v[0], v[1], v[2], v[3]},
            v[4],
            v[5],
        }))};
    }
    if (kind == "unit_cost") {
        require_size(kind, v, 13);
        return {take(unit_cost({
            technology(v[0]),
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
            v[8],
            v[9],
            v[10],
            v[11],
            truth(v[12]),
        }))};
    }
    if (kind == "production_plan") {
        require_size(kind, v, 4);
        const auto output = take(production_plan({v[0], v[1], v[2], v[3]}));
        return {output.target_inventory, output.production_target};
    }
    if (kind == "wage_plan") {
        require_size(kind, v, 10);
        const auto output = take(wage_plan({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
            v[8],
            v[9],
        }));
        return {
            output.target,
            output.posted,
            output.rationed ? 1.0 : 0.0,
            output.repriced ? 1.0 : 0.0,
            output.minimum_bound ? 1.0 : 0.0,
        };
    }
    if (kind == "price_plan") {
        require_size(kind, v, 10);
        const auto output = take(price_plan({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
            v[8],
            v[9],
        }));
        return {
            output.markup,
            output.target,
            output.posted,
            output.repriced ? 1.0 : 0.0,
        };
    }
    if (kind == "investment_user_cost") {
        require_size(kind, v, 9);
        return {take(investment_user_cost_multiplier({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
            v[8],
        }))};
    }
    if (kind == "investment_plan") {
        require_size(kind, v, 20);
        InvestmentPlanInput input{
            truth(v[0]),
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
            v[8],
            v[9],
            std::nullopt,
        };
        if (truth(v[10])) {
            input.user_cost = InvestmentUserCostInput{
                v[11],
                v[12],
                v[13],
                v[14],
                v[15],
                v[16],
                v[17],
                v[18],
                v[19],
            };
        }
        return {take(investment_plan(input))};
    }
    if (kind == "firm_credit_request") {
        require_size(kind, v, 5);
        return {take(firm_credit_request({v[0], v[1], v[2], v[3], v[4]}))};
    }
    if (kind == "firm_debt_service_headroom") {
        require_size(kind, v, 5);
        return {take(firm_debt_service_headroom({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
        }))};
    }
    if (kind == "credit_grant") {
        require_size(kind, v, 14);
        CreditGrantInput input{
            v[0],
            v[1],
            v[2],
            v[3],
            truth(v[4]) ? std::optional<double>(v[5]) : std::nullopt,
            truth(v[6]) ? std::optional<double>(v[7]) : std::nullopt,
            std::nullopt,
        };
        if (truth(v[8])) {
            input.debt_service = DebtServiceHeadroomInput{
                v[9],
                v[10],
                v[11],
                v[12],
                v[13],
            };
        }
        return {take(credit_grant(input))};
    }
    if (kind == "debt_service") {
        require_size(kind, v, 4);
        const auto output = take(debt_service({v[0], v[1], v[2], v[3]}));
        return {output.principal, output.interest};
    }
    if (kind == "consumption_plan") {
        require_size(kind, v, 7);
        return {take(consumption_plan({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
        }))};
    }
    if (kind == "household_contractual_debt_service") {
        require_size(kind, v, 5);
        return {take(household_contractual_debt_service({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
        }))};
    }
    if (kind == "household_debt_service_reservation") {
        require_size(kind, v, 7);
        return {take(reserve_household_debt_service(
            v[0],
            v[1],
            {v[2], v[3], v[4], v[5], v[6]}
        ))};
    }
    if (kind == "equity_demand") {
        require_size(kind, v, 8);
        return {take(equity_demand({
            v[0],
            v[1],
            v[2],
            v[3],
            v[4],
            v[5],
            v[6],
            v[7],
        }))};
    }
    if (kind == "household_credit_request") {
        require_size(kind, v, 4);
        const auto output = take(household_credit_request(
            v[0],
            v[1],
            v[2],
            v[3]
        ));
        return {output.target, output.request};
    }
    if (kind == "floor_safe_price_return") {
        require_size(kind, v, 2);
        return {take(floor_safe_price_return(v[0], v[1]))};
    }
    if (kind == "valuation_discount_rate") {
        require_size(kind, v, 3);
        return {take(valuation_discount_rate({v[0], v[1], v[2]}))};
    }
    if (kind == "residual_income_fundamental") {
        require_size(kind, v, 4);
        return {take(residual_income_fundamental({v[0], v[1], v[2], v[3]}))};
    }
    if (kind == "bond_price") {
        require_size(kind, v, 4);
        return {take(bond_price({
            v[0],
            static_cast<std::int64_t>(v[1]),
            v[2],
            v[3],
        }))};
    }
    if (kind == "female_birth_share") {
        require_size(kind, v, 0);
        return {take(female_birth_share(VitalRates{}))};
    }
    if (kind == "male_birth_share") {
        require_size(kind, v, 0);
        return {take(male_birth_share(VitalRates{}))};
    }
    if (kind == "mortality_integral") {
        require_size(kind, v, 2);
        return {take(mortality_integral(VitalRates{}, v[0], v[1]))};
    }
    if (kind == "survival_probability") {
        require_size(kind, v, 2);
        return {take(survival_probability(VitalRates{}, v[0], v[1]))};
    }
    if (kind == "fertility_shape_rate") {
        require_size(kind, v, 1);
        return {take(fertility_shape_rate(VitalRates{}, v[0]))};
    }
    if (kind == "fertility_rate") {
        require_size(kind, v, 1);
        return {take(fertility_rate(VitalRates{}, v[0]))};
    }
    if (kind == "expected_life_at_birth") {
        require_size(kind, v, 0);
        return {take(expected_life_at_birth(VitalRates{}))};
    }
    throw std::runtime_error("unknown M3 equation kind: " + kind);
}

inline nb::list equation_batch(const nb::list& cases) {
    nb::list output;
    for (const nb::handle item : cases) {
        const auto row = nb::cast<nb::dict>(item);
        const auto kind = nb::cast<std::string>(row["kind"]);
        const auto values = nb::cast<std::vector<double>>(row["values"]);
        output.append(evaluate_case(kind, values));
    }
    return output;
}

inline MatchingProtocol parse_protocol(const std::string& value) {
    if (value == "sampled") {
        return MatchingProtocol::sampled;
    }
    if (value == "preferential") {
        return MatchingProtocol::preferential;
    }
    if (value == "price_sorted") {
        return MatchingProtocol::price_sorted;
    }
    throw std::runtime_error("unknown M3 matching protocol");
}

inline nb::dict market_batch(
    const nb::list& order_rows,
    const nb::list& offer_rows,
    const std::string& protocol,
    std::uint32_t sample_size,
    double beta,
    double price_elasticity,
    PhiloxKey key,
    PhiloxCounter counter,
    std::uint32_t worker_count
) {
    std::vector<BuyOrder> orders;
    std::vector<SellOffer> offers;
    orders.reserve(order_rows.size());
    offers.reserve(offer_rows.size());
    for (const nb::handle item : order_rows) {
        const auto row = nb::cast<nb::dict>(item);
        orders.push_back({
            nb::cast<std::uint64_t>(row["order_id"]),
            AccountId(nb::cast<std::uint64_t>(row["buyer"])),
            Goods(nb::cast<double>(row["demand"])),
            Money(nb::cast<double>(row["budget"])),
        });
    }
    for (const nb::handle item : offer_rows) {
        const auto row = nb::cast<nb::dict>(item);
        offers.push_back({
            nb::cast<std::uint64_t>(row["offer_id"]),
            AccountId(nb::cast<std::uint64_t>(row["seller"])),
            Goods(nb::cast<double>(row["stock"])),
            Price(nb::cast<double>(row["price"])),
            nb::cast<double>(row["attractiveness"]),
        });
    }
    const auto clearing = take(clear_market(
        orders,
        offers,
        {
            parse_protocol(protocol),
            sample_size,
            beta,
            price_elasticity,
            key,
            counter,
            worker_count,
        }
    ));
    nb::list trades;
    for (const auto& trade : clearing.trades) {
        nb::dict row;
        row["ordinal"] = trade.ordinal;
        row["order_id"] = trade.order_id;
        row["offer_id"] = trade.offer_id;
        row["buyer"] = trade.buyer.value();
        row["seller"] = trade.seller.value();
        row["quantity"] = trade.quantity.value();
        row["price"] = trade.price.value();
        row["value"] = trade.value.value();
        trades.append(std::move(row));
    }
    nb::list allocations;
    for (const auto& allocation : clearing.allocations) {
        nb::dict row;
        row["order_id"] = allocation.order_id;
        row["buyer"] = allocation.buyer.value();
        row["allocated"] = allocation.allocated.value();
        row["spent"] = allocation.spent.value();
        row["remaining_demand"] = allocation.remaining_demand.value();
        row["remaining_budget"] = allocation.remaining_budget.value();
        allocations.append(std::move(row));
    }
    nb::list stock_commands;
    for (const auto& command : clearing.stock_commands) {
        nb::dict row;
        row["offer_id"] = command.offer_id;
        row["seller"] = command.seller.value();
        row["opening"] = command.opening.value();
        row["sold"] = command.sold.value();
        row["closing"] = command.closing.value();
        stock_commands.append(std::move(row));
    }
    nb::dict diagnostics;
    diagnostics["random_draws"] = clearing.diagnostics.random_draws;
    diagnostics["seller_candidates"] =
        clearing.diagnostics.seller_candidates;
    diagnostics["seller_updates"] = clearing.diagnostics.seller_updates;
    diagnostics["preferential_weight_builds"] =
        clearing.diagnostics.preferential_weight_builds;
    diagnostics["price_sorts"] = clearing.diagnostics.price_sorts;
    diagnostics["worker_count"] = clearing.diagnostics.worker_count;

    nb::dict output;
    output["trades"] = std::move(trades);
    output["allocations"] = std::move(allocations);
    output["stock_commands"] = std::move(stock_commands);
    output["diagnostics"] = std::move(diagnostics);
    output["next_counter"] = clearing.next_counter;
    return output;
}

inline void bind(nb::module_& module) {
    module.def(
        "m3_equation_batch",
        &equation_batch,
        nb::arg("cases")
    );
    module.def(
        "m3_clear_market",
        &market_batch,
        nb::arg("orders"),
        nb::arg("offers"),
        nb::arg("protocol"),
        nb::arg("sample_size") = 1,
        nb::arg("beta") = 1.0,
        nb::arg("price_elasticity") = 0.0,
        nb::arg("key") = PhiloxKey{},
        nb::arg("counter") = PhiloxCounter{},
        nb::arg("worker_count") = 1
    );
}

}  // namespace macro_sim::python_m3

#endif
