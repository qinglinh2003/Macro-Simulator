#include "macro_sim/simulation/m8_checkpoint.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/simulation/m7_checkpoint.hpp"

namespace macro_sim::simulation {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '8', 'C', 'P', '0', '1',
};
constexpr std::size_t kDigestBytes = 32;
constexpr std::size_t kMaximumCheckpointBytes = 512U * 1024U * 1024U;

#define M8_ENERGY_POLICY_FIELDS(X)                                                     \
    X(excise_rate)                                                                     \
    X(windfall_tax_rate)                                                               \
    X(household_subsidy_rate)                                                          \
    X(subsidy_deposit_threshold)                                                       \
    X(price_cap)                                                                       \
    X(price_cap_compensation)                                                          \
    X(strategic_reserve_target)                                                        \
    X(strategic_reserve_flow_cap)                                                      \
    X(state_owned_price_at_cost)                                                       \
    X(state_owned_first_producer)

#define M8_ENERGY_RULE_FIELDS(X)                                                       \
    X(enabled)                                                                         \
    X(household_energy)                                                                \
    X(deprivation)                                                                     \
    X(state_owned_first_producer)                                                      \
    X(producer_count)                                                                  \
    X(initial_producer_cash)                                                           \
    X(initial_price)                                                                   \
    X(initial_wage)                                                                    \
    X(initial_markup)                                                                  \
    X(producer_productivity)                                                           \
    X(capacity_per_capital)                                                            \
    X(initial_utilization)                                                             \
    X(producer_inventory_ratio)                                                        \
    X(demand_adjustment)                                                               \
    X(markup_adjustment)                                                               \
    X(markup_minimum)                                                                  \
    X(markup_maximum)                                                                  \
    X(household_need)                                                                  \
    X(downstream_intensity)                                                            \
    X(downstream_coverage_days)                                                        \
    X(downstream_gap_close)                                                            \
    X(hoarding_beta)                                                                   \
    X(slow_price_days)                                                                 \
    X(deprivation_burnin_years)                                                        \
    X(deprivation_subsistence_share)                                                   \
    X(deprivation_acute_days)                                                          \
    X(deprivation_chronic_days)                                                        \
    X(fuel_poverty_threshold)                                                          \
    X(fuel_poverty_mortality_gamma)                                                    \
    X(fuel_poverty_mortality_cap)

#define M8_ENERGY_INPUT_FIELDS(X)                                                      \
    X(capacity_multiplier)                                                             \
    X(labor_availability_multiplier)                                                   \
    X(supply_multiplier)                                                               \
    X(household_demand_multiplier)                                                     \
    X(industry_demand_multiplier)                                                      \
    X(reference_price_multiplier)

#define M8_HOUSING_POLICY_FIELDS(X)                                                    \
    X(mortgage_ltv_cap)                                                                \
    X(mortgage_underwriting)                                                           \
    X(mortgage_dsti_cap)                                                               \
    X(mortgage_stress_rate_addon)                                                      \
    X(mortgage_risk_weight)                                                            \
    X(mortgage_minimum_capital_ratio)                                                  \
    X(mortgage_foreclosure_ltv)                                                        \
    X(mortgage_arrears_floor)                                                          \
    X(rental_eviction_arrears)                                                         \
    X(annual_housing_permits)                                                          \
    X(land_fee_share)                                                                  \
    X(land_fee_stock_elasticity)                                                       \
    X(transfer_tax_rate)                                                               \
    X(property_tax_rate)                                                               \
    X(include_housing_in_wealth_tax)                                                   \
    X(wealth_tax_rate)

#define M8_HOUSING_RULE_FIELDS(X)                                                      \
    X(enabled)                                                                         \
    X(resale_market)                                                                   \
    X(mortgages)                                                                       \
    X(rentals)                                                                         \
    X(construction)                                                                    \
    X(house_price_income_years)                                                        \
    X(initial_dwellings_per_household)                                                 \
    X(initial_homeownership_share)                                                     \
    X(initial_floor_area)                                                              \
    X(initial_quality)                                                                 \
    X(location_count)                                                                  \
    X(market_interval_days)                                                            \
    X(voluntary_ask_markup)                                                            \
    X(forced_sale_discount)                                                            \
    X(ask_decay)                                                                       \
    X(demand_price_step)                                                               \
    X(ask_floor_annual_wage_share)                                                     \
    X(buyer_search_count)                                                              \
    X(buyer_liquidity_buffer)                                                          \
    X(distress_deposit_floor)                                                          \
    X(initial_rent_yield)                                                              \
    X(rent_adjustment)                                                                 \
    X(rent_burden_cap)                                                                 \
    X(rental_investor_premium)                                                         \
    X(rental_vacancy_deadband)                                                         \
    X(rent_floor_wage_share)                                                           \
    X(wealth_effect)                                                                   \
    X(builder_count)                                                                   \
    X(initial_builder_cash_buffer)                                                     \
    X(builder_productivity)                                                            \
    X(builder_demand_seed)                                                             \
    X(builder_demand_price_gain)                                                       \
    X(builder_finished_inventory_buffer)                                               \
    X(builder_land_fee_credit)                                                         \
    X(affordability_burnin_years)                                                      \
    X(leave_home_elasticity)                                                           \
    X(leave_home_multiplier_minimum)                                                   \
    X(leave_home_multiplier_maximum)                                                   \
    X(fertility_elasticity)                                                            \
    X(fertility_multiplier_minimum)                                                    \
    X(fertility_multiplier_maximum)

#define M8_HOUSING_INPUT_FIELDS(X)                                                     \
    X(house_price_reference_multiplier)                                                \
    X(buyer_demand_multiplier)                                                         \
    X(rental_demand_multiplier)                                                        \
    X(construction_productivity_multiplier)                                            \
    X(land_cost_multiplier)

#define M8_AFFORDABILITY_FIELDS(X)                                                     \
    X(current_year)                                                                    \
    X(years_completed)                                                                 \
    X(price_sum)                                                                       \
    X(rent_sum)                                                                        \
    X(wage_sum)                                                                        \
    X(labor_sum)                                                                       \
    X(observed_days)                                                                   \
    X(price_to_income_baseline)                                                        \
    X(rent_burden_baseline)                                                            \
    X(price_to_income_ratio)                                                           \
    X(rent_burden_ratio)                                                               \
    X(leave_home_multiplier)                                                           \
    X(fertility_multiplier)

#define M8_ENERGY_METRIC_FIELDS(X)                                                     \
    X(production)                                                                      \
    X(capacity)                                                                        \
    X(producer_capital)                                                                \
    X(utilization)                                                                     \
    X(opening_supply)                                                                  \
    X(requested_total)                                                                 \
    X(requested_households)                                                            \
    X(requested_industry)                                                              \
    X(requested_public)                                                                \
    X(sold)                                                                            \
    X(unfilled)                                                                        \
    X(transaction_price)                                                               \
    X(household_units)                                                                 \
    X(household_spending)                                                              \
    X(industry_units)                                                                  \
    X(industry_spending)                                                               \
    X(excise_paid)                                                                     \
    X(windfall_tax_paid)                                                               \
    X(subsidy_paid)                                                                    \
    X(cap_compensation)                                                                \
    X(strategic_reserve_stock)                                                         \
    X(strategic_reserve_flow)                                                          \
    X(strategic_reserve_purchase_paid)                                                 \
    X(strategic_reserve_sale_revenue)                                                  \
    X(fuel_poverty_share)                                                              \
    X(fuel_poverty_mortality_multiplier)                                               \
    X(deprivation_below_100_share)                                                     \
    X(deprivation_below_60_share)                                                      \
    X(deprivation_below_30_share)                                                      \
    X(deprivation_destitute_share)                                                     \
    X(deprivation_acute_stock)                                                         \
    X(deprivation_chronic_stock)                                                       \
    X(deprivation_max_spell_days)                                                      \
    X(deprivation_boundary)

#define M8_HOUSING_METRIC_FIELDS(X)                                                    \
    X(house_price)                                                                     \
    X(rent_level)                                                                      \
    X(housing_stock)                                                                   \
    X(homeownership_share)                                                             \
    X(vacancy_share)                                                                   \
    X(active_listings)                                                                 \
    X(forced_listing_share)                                                            \
    X(session_sales)                                                                   \
    X(session_volume)                                                                  \
    X(mean_time_on_market_days)                                                        \
    X(mortgage_originations)                                                           \
    X(mortgage_principal_originated)                                                   \
    X(mortgage_principal_outstanding)                                                  \
    X(mortgage_applications)                                                           \
    X(mortgage_underwriting_applications)                                              \
    X(mortgage_dsti_rejections)                                                        \
    X(mortgage_dsti_cap_applied)                                                       \
    X(mortgage_stress_rate_addon_applied)                                              \
    X(mortgage_risk_weight_applied)                                                    \
    X(mortgage_minimum_capital_ratio_applied)                                          \
    X(mortgage_unified_bank_rwa_applied)                                               \
    X(mortgage_bank_risk_weighted_assets)                                              \
    X(mortgage_rwa_principal_capacity)                                                 \
    X(mortgage_rwa_rejections)                                                         \
    X(mortgage_underwritten_principal_share)                                           \
    X(mortgage_cohort_weighted_dsti_cap)                                               \
    X(mortgage_cohort_weighted_stress_rate_addon)                                      \
    X(foreclosures)                                                                    \
    X(mortgage_foreclosure_candidates)                                                 \
    X(mortgage_foreclosures_prevented_by_liquidity)                                    \
    X(mortgage_arrears_floor_applied)                                                  \
    X(rent_paid)                                                                       \
    X(rent_unpaid)                                                                     \
    X(evictions)                                                                       \
    X(property_tax_paid)                                                               \
    X(housing_wealth_tax_paid)                                                         \
    X(housing_wealth_tax_base_included)                                                \
    X(transfer_tax_paid)                                                               \
    X(land_fee_paid)                                                                   \
    X(land_fee_assessments)                                                            \
    X(land_fee_share_applied)                                                          \
    X(land_fee_stock_elasticity_applied)                                               \
    X(land_fee_stock_pressure_applied)                                                 \
    X(construction_output)                                                             \
    X(dwellings_completed)                                                             \
    X(housing_permit_cap_applied)                                                      \
    X(housing_units_ready_for_permits)                                                 \
    X(housing_units_blocked_by_permits)                                                \
    X(permits_used)                                                                    \
    X(price_to_income_ratio)                                                           \
    X(rent_burden_ratio)                                                               \
    X(leave_home_multiplier)                                                           \
    X(fertility_multiplier)

#define M8_WRITE_FIELD(name) output[#name] = value.name;
#define M8_READ_FIELD(name)                                                            \
    value.name = input.at(#name).get<std::remove_cvref_t<decltype(value.name)>>();

void append_u32(std::vector<std::uint8_t> &bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

[[nodiscard]] bool read_u32(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint32_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 4U) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 4; ++index) {
        value = static_cast<std::uint32_t>((value << 8U) | bytes[position++]);
    }
    return true;
}

[[nodiscard]] bool read_u64(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint64_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 8U) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 8; ++index) {
        value = (value << 8U) | bytes[position++];
    }
    return true;
}

[[nodiscard]] Status corrupt(const char *message) noexcept {
    return Status(ErrorCode::corrupt_input, message);
}

[[nodiscard]] Json owner_json(core::OwnerId owner) {
    return Json::array({
        static_cast<std::uint8_t>(owner.kind()),
        owner.value(),
    });
}

[[nodiscard]] core::OwnerId owner_from_json(const Json &row) {
    if (!row.is_array() || row.size() != 2U) {
        throw std::runtime_error("invalid M8 owner");
    }
    return {
        static_cast<core::OwnerKind>(row[0].get<std::uint8_t>()),
        row[1].get<std::uint32_t>(),
    };
}

[[nodiscard]] Json encode_energy_policy(const EnergyPolicyState &value) {
    Json output;
    M8_ENERGY_POLICY_FIELDS(M8_WRITE_FIELD)
    output["rationing"] = static_cast<std::uint8_t>(value.rationing);
    return output;
}

[[nodiscard]] EnergyPolicyState decode_energy_policy(const Json &input) {
    EnergyPolicyState value;
    M8_ENERGY_POLICY_FIELDS(M8_READ_FIELD)
    value.rationing =
        static_cast<EnergyRationing>(input.at("rationing").get<std::uint8_t>());
    return value;
}

[[nodiscard]] Json encode_energy_rules(const EnergyRules &value) {
    Json output;
    M8_ENERGY_RULE_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] EnergyRules decode_energy_rules(const Json &input) {
    EnergyRules value;
    M8_ENERGY_RULE_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_energy_input(const EnergyExogenousInput &value) {
    Json output;
    M8_ENERGY_INPUT_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] EnergyExogenousInput decode_energy_input(const Json &input) {
    EnergyExogenousInput value;
    M8_ENERGY_INPUT_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_housing_policy(const HousingPolicyState &value) {
    Json output;
    M8_HOUSING_POLICY_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] HousingPolicyState decode_housing_policy(const Json &input) {
    HousingPolicyState value;
    M8_HOUSING_POLICY_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_housing_rules(const HousingRules &value) {
    Json output;
    M8_HOUSING_RULE_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] HousingRules decode_housing_rules(const Json &input) {
    HousingRules value;
    M8_HOUSING_RULE_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_housing_input(const HousingExogenousInput &value) {
    Json output;
    M8_HOUSING_INPUT_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] HousingExogenousInput decode_housing_input(const Json &input) {
    HousingExogenousInput value;
    M8_HOUSING_INPUT_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_affordability(const HousingAffordabilityState &value) {
    Json output;
    M8_AFFORDABILITY_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] HousingAffordabilityState decode_affordability(const Json &input) {
    HousingAffordabilityState value;
    M8_AFFORDABILITY_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_energy_metrics(const EnergyMetrics &value) {
    Json output;
    M8_ENERGY_METRIC_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] EnergyMetrics decode_energy_metrics(const Json &input) {
    EnergyMetrics value;
    M8_ENERGY_METRIC_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_housing_metrics(const HousingMetrics &value) {
    Json output;
    M8_HOUSING_METRIC_FIELDS(M8_WRITE_FIELD)
    return output;
}

[[nodiscard]] HousingMetrics decode_housing_metrics(const Json &input) {
    HousingMetrics value;
    M8_HOUSING_METRIC_FIELDS(M8_READ_FIELD)
    return value;
}

[[nodiscard]] Json encode_runtime(const M8Runtime &runtime) {
    Json output;
    output["energy_policy"] = encode_energy_policy(runtime.energy_policy);
    output["energy_rules"] = encode_energy_rules(runtime.energy_rules);
    output["energy_input"] = encode_energy_input(runtime.energy_input);
    output["energy_producers"] = Json::array();
    for (const auto &row : runtime.energy_producers) {
        output["energy_producers"].push_back(Json::array({
            row.firm.value(),
            row.active,
            row.state_owned,
            row.capacity_per_capital,
            row.inventory,
            row.inventory_cost,
            row.produced,
            row.sales,
            row.revenue,
            row.demand_expected,
        }));
    }
    output["energy_inputs"] = Json::array();
    for (const auto &row : runtime.energy_inputs) {
        output["energy_inputs"].push_back(Json::array({
            row.firm.value(),
            row.active,
            row.intensity,
            row.coverage_days,
            row.stock,
            row.stock_cost,
            row.average_cost,
            row.bought,
            row.used,
            row.unmet,
        }));
    }
    output["household_energy"] = Json::array();
    for (const auto &row : runtime.household_energy) {
        output["household_energy"].push_back(Json::array({
            row.household.value(),
            row.active,
            row.need,
            row.bought,
            row.spent,
            row.subsidy,
            row.coverage,
            row.deprivation_spells,
        }));
    }
    output["deprivation"] = Json::array({
        runtime.deprivation.current_year,
        runtime.deprivation.years_completed,
        runtime.deprivation.per_unit_sum,
        runtime.deprivation.household_days,
        runtime.deprivation.price_sum,
        runtime.deprivation.price_days,
        runtime.deprivation.basket_cost_anchor,
        runtime.deprivation.price_anchor,
        runtime.deprivation.active,
        runtime.deprivation.boundary_breached,
    });
    output["energy_state"] = Json::array({
        runtime.strategic_reserve_stock,
        runtime.strategic_reserve_cost,
        runtime.energy_price,
        runtime.slow_energy_price,
        runtime.energy_event_counter,
    });
    output["housing_policy"] = encode_housing_policy(runtime.housing_policy);
    output["housing_rules"] = encode_housing_rules(runtime.housing_rules);
    output["housing_input"] = encode_housing_input(runtime.housing_input);
    output["dwellings"] = Json::array();
    for (const auto &row : runtime.properties.records()) {
        output["dwellings"].push_back(Json::array({
            row.id.value(),
            owner_json(row.owner),
            row.occupant.value(),
            row.collateral.value(),
            row.minted_tick.value(),
            row.last_title_tick.value(),
            row.floor_area,
            row.quality,
            row.location,
            row.age_days,
            row.active,
        }));
    }
    output["title_events"] = Json::array();
    for (const auto &row : runtime.properties.title_events()) {
        output["title_events"].push_back(Json::array({
            row.id.value(),
            row.dwelling.value(),
            static_cast<std::uint8_t>(row.kind),
            owner_json(row.previous_owner),
            owner_json(row.next_owner),
            row.tick.value(),
        }));
    }
    output["listings"] = Json::array();
    for (const auto &row : runtime.housing_listings) {
        output["listings"].push_back(Json::array({
            row.dwelling.value(),
            owner_json(row.seller),
            row.asking_price,
            row.listed_tick.value(),
            row.forced,
            row.active,
        }));
    }
    output["mortgages"] = Json::array();
    for (const auto &row : runtime.mortgages) {
        output["mortgages"].push_back(Json::array({
            row.loan.value(),
            row.borrower.value(),
            row.lender.value(),
            row.collateral.value(),
            row.original_principal,
            row.purchase_price,
            row.qualifying_income,
            row.stressed_payment,
            row.underwriting_applied,
            row.dsti_cap_at_origination,
            row.stress_rate_addon_at_origination,
            row.originated_tick.value(),
            row.active,
            row.foreclosed,
        }));
    }
    output["tenancies"] = Json::array();
    for (const auto &row : runtime.tenancies) {
        output["tenancies"].push_back(Json::array({
            row.id.value(),
            row.dwelling.value(),
            row.landlord.value(),
            row.tenant.value(),
            row.daily_rent,
            row.missed_days,
            row.started_tick.value(),
            row.ended_tick.value(),
            row.active,
        }));
    }
    output["builders"] = Json::array();
    for (const auto &row : runtime.builders) {
        output["builders"].push_back(Json::array({
            row.firm.value(),
            row.active,
            row.work_in_progress,
            row.finished_inventory,
            row.demand_expected,
            row.produced_today,
            row.dwellings_minted,
        }));
    }
    output["affordability"] = encode_affordability(runtime.housing_affordability);
    output["housing_state"] = Json::array({
        runtime.house_price,
        runtime.rent_level,
        runtime.genesis_dwelling_count,
        runtime.permit_year,
        runtime.permits_used,
        runtime.housing_event_counter,
    });
    output["energy_metrics"] = encode_energy_metrics(runtime.last_metrics.energy);
    output["housing_metrics"] = encode_housing_metrics(runtime.last_metrics.housing);
    return output;
}

void decode_runtime(const Json &input, M8Runtime &runtime) {
    runtime.energy_policy = decode_energy_policy(input.at("energy_policy"));
    runtime.energy_rules = decode_energy_rules(input.at("energy_rules"));
    runtime.energy_input = decode_energy_input(input.at("energy_input"));
    for (const auto &row : input.at("energy_producers")) {
        if (!row.is_array() || row.size() != 10U) {
            throw std::runtime_error("invalid M8 energy producer");
        }
        runtime.energy_producers.push_back({
            FirmId(row[0].get<std::uint64_t>()),
            row[1].get<bool>(),
            row[2].get<bool>(),
            row[3].get<double>(),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<double>(),
            row[9].get<double>(),
        });
    }
    for (const auto &row : input.at("energy_inputs")) {
        if (!row.is_array() || row.size() != 10U) {
            throw std::runtime_error("invalid M8 energy input");
        }
        runtime.energy_inputs.push_back({
            FirmId(row[0].get<std::uint64_t>()),
            row[1].get<bool>(),
            row[2].get<double>(),
            row[3].get<double>(),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<double>(),
            row[9].get<double>(),
        });
    }
    for (const auto &row : input.at("household_energy")) {
        if (!row.is_array() || row.size() != 8U) {
            throw std::runtime_error("invalid M8 household energy");
        }
        runtime.household_energy.push_back({
            HouseholdId(row[0].get<std::uint64_t>()),
            row[1].get<bool>(),
            row[2].get<double>(),
            row[3].get<double>(),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<double>(),
            row[7].get<std::array<std::uint32_t, 3>>(),
        });
    }
    const auto &deprivation = input.at("deprivation");
    if (!deprivation.is_array() || deprivation.size() != 10U) {
        throw std::runtime_error("invalid M8 deprivation state");
    }
    runtime.deprivation = {
        deprivation[0].get<std::int32_t>(), deprivation[1].get<std::uint32_t>(),
        deprivation[2].get<double>(),       deprivation[3].get<double>(),
        deprivation[4].get<double>(),       deprivation[5].get<double>(),
        deprivation[6].get<double>(),       deprivation[7].get<double>(),
        deprivation[8].get<bool>(),         deprivation[9].get<bool>(),
    };
    const auto &energy_state = input.at("energy_state");
    if (!energy_state.is_array() || energy_state.size() != 5U) {
        throw std::runtime_error("invalid M8 energy state");
    }
    runtime.strategic_reserve_stock = energy_state[0].get<double>();
    runtime.strategic_reserve_cost = energy_state[1].get<double>();
    runtime.energy_price = energy_state[2].get<double>();
    runtime.slow_energy_price = energy_state[3].get<double>();
    runtime.energy_event_counter = energy_state[4].get<std::uint64_t>();
    runtime.housing_policy = decode_housing_policy(input.at("housing_policy"));
    runtime.housing_rules = decode_housing_rules(input.at("housing_rules"));
    runtime.housing_input = decode_housing_input(input.at("housing_input"));
    std::vector<core::DwellingRecord> dwellings;
    for (const auto &row : input.at("dwellings")) {
        if (!row.is_array() || row.size() != 11U) {
            throw std::runtime_error("invalid M8 dwelling");
        }
        dwellings.push_back({
            DwellingId(row[0].get<std::uint64_t>()),
            owner_from_json(row[1]),
            HouseholdId(row[2].get<std::uint64_t>()),
            LoanId(row[3].get<std::uint64_t>()),
            Tick(row[4].get<std::uint64_t>()),
            Tick(row[5].get<std::uint64_t>()),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<std::uint32_t>(),
            row[9].get<std::uint32_t>(),
            row[10].get<bool>(),
        });
    }
    std::vector<core::TitleEvent> title_events;
    for (const auto &row : input.at("title_events")) {
        if (!row.is_array() || row.size() != 6U) {
            throw std::runtime_error("invalid M8 title event");
        }
        title_events.push_back({
            TitleEventId(row[0].get<std::uint64_t>()),
            DwellingId(row[1].get<std::uint64_t>()),
            static_cast<core::TitleEventKind>(row[2].get<std::uint8_t>()),
            owner_from_json(row[3]),
            owner_from_json(row[4]),
            Tick(row[5].get<std::uint64_t>()),
        });
    }
    const auto restored =
        runtime.properties.replace_state(std::move(dwellings), std::move(title_events));
    if (!restored.ok()) {
        throw std::runtime_error("invalid M8 property registry");
    }
    for (const auto &row : input.at("listings")) {
        if (!row.is_array() || row.size() != 6U) {
            throw std::runtime_error("invalid M8 listing");
        }
        runtime.housing_listings.push_back({
            DwellingId(row[0].get<std::uint64_t>()),
            owner_from_json(row[1]),
            row[2].get<double>(),
            Tick(row[3].get<std::uint64_t>()),
            row[4].get<bool>(),
            row[5].get<bool>(),
        });
    }
    for (const auto &row : input.at("mortgages")) {
        if (!row.is_array() || row.size() != 14U) {
            throw std::runtime_error("invalid M8 mortgage");
        }
        runtime.mortgages.push_back({
            LoanId(row[0].get<std::uint64_t>()),
            HouseholdId(row[1].get<std::uint64_t>()),
            BankId(row[2].get<std::uint64_t>()),
            DwellingId(row[3].get<std::uint64_t>()),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<bool>(),
            row[9].get<double>(),
            row[10].get<double>(),
            Tick(row[11].get<std::uint64_t>()),
            row[12].get<bool>(),
            row[13].get<bool>(),
        });
    }
    for (const auto &row : input.at("tenancies")) {
        if (!row.is_array() || row.size() != 9U) {
            throw std::runtime_error("invalid M8 tenancy");
        }
        runtime.tenancies.push_back({
            TenancyId(row[0].get<std::uint64_t>()),
            DwellingId(row[1].get<std::uint64_t>()),
            HouseholdId(row[2].get<std::uint64_t>()),
            HouseholdId(row[3].get<std::uint64_t>()),
            row[4].get<double>(),
            row[5].get<std::uint32_t>(),
            Tick(row[6].get<std::uint64_t>()),
            Tick(row[7].get<std::uint64_t>()),
            row[8].get<bool>(),
        });
    }
    for (const auto &row : input.at("builders")) {
        if (!row.is_array() || row.size() != 7U) {
            throw std::runtime_error("invalid M8 builder");
        }
        runtime.builders.push_back({
            FirmId(row[0].get<std::uint64_t>()),
            row[1].get<bool>(),
            row[2].get<double>(),
            row[3].get<double>(),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<std::uint64_t>(),
        });
    }
    runtime.housing_affordability = decode_affordability(input.at("affordability"));
    const auto &housing_state = input.at("housing_state");
    if (!housing_state.is_array() || housing_state.size() != 6U) {
        throw std::runtime_error("invalid M8 housing state");
    }
    runtime.house_price = housing_state[0].get<double>();
    runtime.rent_level = housing_state[1].get<double>();
    runtime.genesis_dwelling_count = housing_state[2].get<std::uint64_t>();
    runtime.permit_year = housing_state[3].get<std::int32_t>();
    runtime.permits_used = housing_state[4].get<std::uint64_t>();
    runtime.housing_event_counter = housing_state[5].get<std::uint64_t>();
    runtime.last_metrics.energy = decode_energy_metrics(input.at("energy_metrics"));
    runtime.last_metrics.housing = decode_housing_metrics(input.at("housing_metrics"));
}

#undef M8_WRITE_FIELD
#undef M8_READ_FIELD
#undef M8_ENERGY_POLICY_FIELDS
#undef M8_ENERGY_RULE_FIELDS
#undef M8_ENERGY_INPUT_FIELDS
#undef M8_HOUSING_POLICY_FIELDS
#undef M8_HOUSING_RULE_FIELDS
#undef M8_HOUSING_INPUT_FIELDS
#undef M8_AFFORDABILITY_FIELDS
#undef M8_ENERGY_METRIC_FIELDS
#undef M8_HOUSING_METRIC_FIELDS

} // namespace

bool is_m8_checkpoint(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= kMagic.size() &&
           std::equal(kMagic.begin(), kMagic.end(), bytes.begin());
}

Result<std::vector<std::uint8_t>> save_m8_checkpoint(
    const core::RootState &root, const M4Runtime &real_economy_runtime,
    const M5Runtime &monetary_runtime, const M6Runtime &financial_runtime,
    const M7Runtime &population_runtime, const M8Runtime &runtime, Tick tick) {
    const auto validation =
        validate_m8_state(root, real_economy_runtime, monetary_runtime,
                          financial_runtime, population_runtime, runtime, tick);
    if (!validation.ok()) {
        return Status(ErrorCode::invariant_violation, "cannot save invalid M8 state");
    }
    auto base = save_m7_checkpoint(root, real_economy_runtime, monetary_runtime,
                                   financial_runtime, population_runtime, tick);
    if (!base.ok()) {
        return base.status();
    }
    const auto encoded = encode_runtime(runtime).dump();
    std::vector<std::uint8_t> bytes;
    bytes.reserve(kMagic.size() + 4U + 8U + base.get_if()->size() + 8U +
                  encoded.size() + kDigestBytes);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kM8CheckpointSchemaVersion);
    append_u64(bytes, base.get_if()->size());
    bytes.insert(bytes.end(), base.get_if()->begin(), base.get_if()->end());
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    if (bytes.size() > kMaximumCheckpointBytes) {
        return Status(ErrorCode::out_of_range,
                      "M8 checkpoint exceeds the supported size");
    }
    return bytes;
}

Result<M8Checkpoint> load_m8_checkpoint(std::span<const std::uint8_t> bytes) {
    if (bytes.size() > kMaximumCheckpointBytes ||
        bytes.size() < kMagic.size() + 4U + 8U + 8U + kDigestBytes ||
        !is_m8_checkpoint(bytes)) {
        return corrupt("M8 checkpoint identity or size is invalid");
    }
    const auto payload = bytes.first(bytes.size() - kDigestBytes);
    const auto digest = core::sha256_digest(payload);
    if (!std::equal(digest.bytes.begin(), digest.bytes.end(),
                    bytes.end() - static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt("M8 checkpoint checksum does not match");
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0;
    std::uint64_t base_size = 0;
    if (!read_u32(payload, position, version) ||
        version != kM8CheckpointSchemaVersion ||
        !read_u64(payload, position, base_size) ||
        base_size > payload.size() - position) {
        return corrupt("M8 checkpoint header is invalid");
    }
    const auto base = payload.subspan(position, static_cast<std::size_t>(base_size));
    position += static_cast<std::size_t>(base_size);
    std::uint64_t json_size = 0;
    if (!read_u64(payload, position, json_size) ||
        json_size > payload.size() - position ||
        position + json_size != payload.size()) {
        return corrupt("M8 checkpoint payload size is invalid");
    }
    auto loaded = load_m7_checkpoint(base);
    if (!loaded.ok()) {
        return loaded.status();
    }
    try {
        const std::string encoded(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(json_size));
        const auto json = Json::parse(encoded);
        auto value = std::move(*loaded.get_if());
        M8Runtime runtime;
        decode_runtime(json, runtime);
        runtime.last_metrics.economy = value.runtime.last_metrics;
        if (!validate_m8_state(value.root, value.real_economy_runtime,
                               value.monetary_runtime, value.financial_runtime,
                               value.runtime, runtime, value.tick)
                 .ok()) {
            return corrupt("M8 checkpoint restored state is invalid");
        }
        return M8Checkpoint{
            std::move(value.root),
            std::move(value.real_economy_runtime),
            std::move(value.monetary_runtime),
            std::move(value.financial_runtime),
            std::move(value.runtime),
            std::move(runtime),
            value.tick,
        };
    } catch (...) {
        return corrupt("M8 checkpoint JSON payload is invalid");
    }
}

Result<core::StateDigest> m8_state_digest(const core::RootState &root,
                                          const M4Runtime &real_economy_runtime,
                                          const M5Runtime &monetary_runtime,
                                          const M6Runtime &financial_runtime,
                                          const M7Runtime &population_runtime,
                                          const M8Runtime &runtime, Tick tick) {
    auto checkpoint =
        save_m8_checkpoint(root, real_economy_runtime, monetary_runtime,
                           financial_runtime, population_runtime, runtime, tick);
    if (!checkpoint.ok()) {
        return checkpoint.status();
    }
    return core::sha256_digest(*checkpoint.get_if());
}

} // namespace macro_sim::simulation
