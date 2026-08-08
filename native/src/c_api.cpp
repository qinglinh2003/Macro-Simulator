#include "macro_sim/c_api.h"

#include <algorithm>
#include <cstring>
#include <memory>
#include <new>
#include <string_view>
#include <vector>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/simulation/m9.hpp"
#include "macro_sim/version.hpp"

struct macro_sim_session {
    explicit macro_sim_session(std::uint64_t session_id)
        : engine(macro_sim::EngineSessionOptions{macro_sim::SessionId(session_id)}) {}

    macro_sim::EngineSession engine;
};

struct macro_sim_m9_world {
    explicit macro_sim_m9_world(macro_sim::simulation::M9World value)
        : engine(std::move(value)) {}

    macro_sim::simulation::M9World engine;
};

namespace {

macro_sim_status status(macro_sim_error_code code, const char *message) noexcept {
    return {code, message};
}

macro_sim_error_code normalize_error(macro_sim::ErrorCode code) noexcept {
    switch (code) {
    case macro_sim::ErrorCode::ok:
    case macro_sim::ErrorCode::invalid_argument:
    case macro_sim::ErrorCode::out_of_range:
    case macro_sim::ErrorCode::allocation_failure:
    case macro_sim::ErrorCode::invalid_handle:
    case macro_sim::ErrorCode::incompatible_abi:
    case macro_sim::ErrorCode::contract_violation:
    case macro_sim::ErrorCode::corrupt_input:
    case macro_sim::ErrorCode::unsupported:
    case macro_sim::ErrorCode::internal_error:
        return static_cast<macro_sim_error_code>(code);
    case macro_sim::ErrorCode::not_found:
    case macro_sim::ErrorCode::invalid_transaction_state:
    case macro_sim::ErrorCode::stale_handle:
        return MACRO_SIM_INVALID_HANDLE;
    case macro_sim::ErrorCode::already_exists:
    case macro_sim::ErrorCode::insufficient_funds:
    case macro_sim::ErrorCode::unbalanced_transaction:
    case macro_sim::ErrorCode::invariant_violation:
        return MACRO_SIM_CONTRACT_VIOLATION;
    }
    return MACRO_SIM_INTERNAL_ERROR;
}

macro_sim_status status(const macro_sim::Status &source) noexcept {
    return {
        normalize_error(source.code()),
        source.message().empty() ? "" : source.message().data(),
    };
}

void fill_m4_metrics(macro_sim_m4_metrics &output,
                     const macro_sim::simulation::M4Metrics &metrics) noexcept {
    output.reserved = 0;
    output.tick = metrics.tick.value();
    output.real_output = metrics.real_output;
    output.nominal_output = metrics.nominal_output;
    output.price_index = metrics.price_index;
    output.unemployment_rate = metrics.unemployment_rate;
    output.total_money = metrics.total_money;
    output.conservation_drift = metrics.conservation_drift;
    output.aggregate_capital = metrics.aggregate_capital;
    output.household_consumption = metrics.household_consumption;
    output.wages_paid = metrics.wages_paid;
    output.firm_profit = metrics.firm_profit;
    output.tax_total = metrics.tax_total;
    output.government_spending = metrics.government_spending;
    output.government_deficit = metrics.government_deficit;
    output.public_capital = metrics.public_capital;
    output.dividends_paid = metrics.dividends_paid;
}

void fill_m5_metrics(macro_sim_m5_metrics &output,
                     const macro_sim::simulation::M5Metrics &metrics) noexcept {
    output.reserved = 0;
    fill_m4_metrics(output.economy, metrics.economy);
    output.policy_rate = metrics.policy_rate;
    output.inflation_sensor = metrics.inflation_sensor;
    output.new_credit = metrics.new_credit;
    output.principal_repaid = metrics.principal_repaid;
    output.loan_interest_paid = metrics.loan_interest_paid;
    output.household_interest_paid = metrics.household_interest_paid;
    output.deposit_interest_paid = metrics.deposit_interest_paid;
    output.deposit_interest_arrears = metrics.deposit_interest_arrears;
    output.total_loan_principal = metrics.total_loan_principal;
    output.total_bank_capital = metrics.total_bank_capital;
    output.total_reserves = metrics.total_reserves;
    output.reserve_stock = metrics.reserve_stock;
    output.omo_flow = metrics.omo_flow;
    output.lolr_advances = metrics.lolr_advances;
    output.lolr_outstanding = metrics.lolr_outstanding;
    output.interbank_volume = metrics.interbank_volume;
    output.interbank_rate = metrics.interbank_rate;
    output.run_flight_volume = metrics.run_flight_volume;
    output.resolution_cost = metrics.resolution_cost;
    output.realized_credit_losses = metrics.realized_credit_losses;
    output.realized_interbank_losses = metrics.realized_interbank_losses;
    output.alive_banks = metrics.alive_banks;
    output.bank_failures = metrics.bank_failures;
}

void fill_m6_metrics(macro_sim_m6_metrics &output,
                     const macro_sim::simulation::M6Metrics &metrics) noexcept {
    output.reserved = 0;
    fill_m5_metrics(output.economy, metrics.economy);
#define MACRO_SIM_FILL_M6(field) output.field = metrics.field
    MACRO_SIM_FILL_M6(bond_outstanding_face);
    MACRO_SIM_FILL_M6(bond_market_value);
    MACRO_SIM_FILL_M6(bond_issuance);
    MACRO_SIM_FILL_M6(bond_redemption);
    MACRO_SIM_FILL_M6(bond_coupon_paid);
    MACRO_SIM_FILL_M6(household_bond_market_value);
    MACRO_SIM_FILL_M6(bank_bond_market_value);
    MACRO_SIM_FILL_M6(firm_equity_market_cap);
    MACRO_SIM_FILL_M6(bank_equity_market_cap);
    MACRO_SIM_FILL_M6(household_firm_equity_market_value);
    MACRO_SIM_FILL_M6(household_bank_equity_market_value);
    MACRO_SIM_FILL_M6(equity_turnover);
    MACRO_SIM_FILL_M6(firm_equity_turnover);
    MACRO_SIM_FILL_M6(bank_equity_turnover);
    MACRO_SIM_FILL_M6(firm_equity_fundamental_value);
    MACRO_SIM_FILL_M6(bank_equity_fundamental_value);
    MACRO_SIM_FILL_M6(primary_equity_raised);
    MACRO_SIM_FILL_M6(margin_principal);
    MACRO_SIM_FILL_M6(margin_originated);
    MACRO_SIM_FILL_M6(margin_repaid);
    MACRO_SIM_FILL_M6(margin_writeoffs);
    MACRO_SIM_FILL_M6(total_firm_book_equity);
    MACRO_SIM_FILL_M6(clearing_residual);
    MACRO_SIM_FILL_M6(sector_retool_capital);
    MACRO_SIM_FILL_M6(active_security_lots);
    MACRO_SIM_FILL_M6(household_bankruptcies);
    MACRO_SIM_FILL_M6(firm_births);
    MACRO_SIM_FILL_M6(firm_exits);
    MACRO_SIM_FILL_M6(firm_defaults);
    MACRO_SIM_FILL_M6(sector_switches);
    MACRO_SIM_FILL_M6(bank_births);
    MACRO_SIM_FILL_M6(bank_equity_resolutions);
#undef MACRO_SIM_FILL_M6
}

void fill_m7_metrics(macro_sim_m7_metrics &output,
                     const macro_sim::simulation::M7Metrics &metrics) noexcept {
    output.reserved = 0;
    fill_m6_metrics(output.economy, metrics.economy);
#define MACRO_SIM_FILL_M7(field) output.field = metrics.field
    MACRO_SIM_FILL_M7(population);
    MACRO_SIM_FILL_M7(births);
    MACRO_SIM_FILL_M7(deaths);
    MACRO_SIM_FILL_M7(households_with_members);
    MACRO_SIM_FILL_M7(mean_household_size);
    MACRO_SIM_FILL_M7(working_age_share);
    MACRO_SIM_FILL_M7(dependency_ratio);
    MACRO_SIM_FILL_M7(mean_person_efficiency);
    MACRO_SIM_FILL_M7(person_efficiency_stddev);
    MACRO_SIM_FILL_M7(active_unions);
    MACRO_SIM_FILL_M7(mean_partner_age_gap);
    MACRO_SIM_FILL_M7(mean_partner_log_efficiency_gap);
    MACRO_SIM_FILL_M7(participation_rate);
    MACRO_SIM_FILL_M7(estates_settled);
    MACRO_SIM_FILL_M7(beneficial_lots_transferred);
    MACRO_SIM_FILL_M7(inheritance_tax_share);
    MACRO_SIM_FILL_M7(inheritance_tax_paid);
    MACRO_SIM_FILL_M7(beneficial_projection_error);
    MACRO_SIM_FILL_M7(employed_fte);
    MACRO_SIM_FILL_M7(employed_heads);
    MACRO_SIM_FILL_M7(unemployment);
    MACRO_SIM_FILL_M7(unemployment_rate);
    MACRO_SIM_FILL_M7(suspended);
    MACRO_SIM_FILL_M7(job_guarantee);
    MACRO_SIM_FILL_M7(out_of_labor_force);
    MACRO_SIM_FILL_M7(labor_supply);
    MACRO_SIM_FILL_M7(vacancies);
    MACRO_SIM_FILL_M7(underemployed_heads);
    MACRO_SIM_FILL_M7(underemployment_hours);
    MACRO_SIM_FILL_M7(suspended_memo);
    MACRO_SIM_FILL_M7(second_job_heads);
    MACRO_SIM_FILL_M7(second_job_hours);
    MACRO_SIM_FILL_M7(nonsearching);
    MACRO_SIM_FILL_M7(job_to_job_moves);
    MACRO_SIM_FILL_M7(mean_hourly_wage);
    MACRO_SIM_FILL_M7(family_transfer_total);
    MACRO_SIM_FILL_M7(family_transfer_recipients);
    MACRO_SIM_FILL_M7(family_exposed_households);
    MACRO_SIM_FILL_M7(hires);
    MACRO_SIM_FILL_M7(separations);
    MACRO_SIM_FILL_M7(marriages);
    MACRO_SIM_FILL_M7(divorces);
    MACRO_SIM_FILL_M7(widowhoods);
    MACRO_SIM_FILL_M7(leaving_home_events);
#undef MACRO_SIM_FILL_M7
}

bool valid_flag(std::uint32_t value) noexcept { return value <= 1; }

bool valid_m7_genesis_options(const macro_sim_m7_genesis_options &options) noexcept {
    const auto &financial = options.financial;
    return options.struct_size == sizeof(macro_sim_m7_genesis_options) &&
           financial.struct_size == sizeof(macro_sim_m6_genesis_options) &&
           financial.matching_protocol <= MACRO_SIM_M4_MATCH_PRICE_SORTED &&
           valid_flag(financial.stochastic) && valid_flag(financial.bonds) &&
           valid_flag(financial.firm_equity) && valid_flag(financial.margin_credit) &&
           valid_flag(financial.firm_dynamics) && valid_flag(financial.bank_dynamics) &&
           financial.reserved == 0 &&
           financial.portfolio_review_interval_days <= 3'650U;
}

macro_sim::simulation::M7SimulationSpec
make_m7_spec(const macro_sim_m7_genesis_options &options) {
    macro_sim::simulation::M7SimulationSpec spec;
    const auto &source = options.financial;
    auto &financial = spec.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    real.economy = macro_sim::EconomyId(source.economy_id);
    real.currency = macro_sim::CurrencyId(source.currency_id);
    real.market_protocol =
        static_cast<macro_sim::algorithms::MatchingProtocol>(source.matching_protocol);
    real.stochastic = source.stochastic != 0;
    real.consumption_firms = source.consumption_firms;
    real.capital_firms = source.capital_firms;
    real.seed = source.seed;
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    monetary.rules.bank_count = source.banks;
    monetary.rules.opening_capital_per_bank = source.opening_capital_per_bank;
    monetary.initial_policy_rate = source.initial_policy_rate;
    financial.rules.bonds = source.bonds != 0;
    financial.rules.firm_equity = source.firm_equity != 0;
    financial.rules.margin_credit = source.margin_credit != 0;
    financial.rules.firm_dynamics = source.firm_dynamics != 0;
    financial.rules.bank_dynamics = source.bank_dynamics != 0;
    financial.rules.watchlist_size = source.watchlist_size;
    if (source.portfolio_review_interval_days != 0U) {
        financial.rules.portfolio_review_interval_days =
            source.portfolio_review_interval_days;
    }
    spec.population.initial_persons = options.initial_persons;
    spec.population.start_calendar_day = options.start_calendar_day;
    spec.population.target_household_size = options.target_household_size;
    return spec;
}

void fill_energy_policy(
    macro_sim_m8_energy_policy &output,
    const macro_sim::simulation::EnergyPolicyState &value) noexcept {
    output.struct_size = sizeof(output);
    output.price_cap_compensation = value.price_cap_compensation ? 1U : 0U;
    output.state_owned_price_at_cost = value.state_owned_price_at_cost ? 1U : 0U;
    output.rationing = static_cast<std::uint32_t>(value.rationing);
    output.excise_rate = value.excise_rate;
    output.household_subsidy_rate = value.household_subsidy_rate;
    output.subsidy_deposit_threshold = value.subsidy_deposit_threshold;
    output.price_cap = value.price_cap;
    output.strategic_reserve_target = value.strategic_reserve_target;
    output.strategic_reserve_flow_cap = value.strategic_reserve_flow_cap;
}

macro_sim::simulation::EnergyPolicyState
energy_policy_from_c(const macro_sim_m8_energy_policy &value) noexcept {
    macro_sim::simulation::EnergyPolicyState output;
    output.price_cap_compensation = value.price_cap_compensation != 0;
    output.state_owned_price_at_cost = value.state_owned_price_at_cost != 0;
    output.rationing =
        static_cast<macro_sim::simulation::EnergyRationing>(value.rationing);
    output.excise_rate = value.excise_rate;
    output.household_subsidy_rate = value.household_subsidy_rate;
    output.subsidy_deposit_threshold = value.subsidy_deposit_threshold;
    output.price_cap = value.price_cap;
    output.strategic_reserve_target = value.strategic_reserve_target;
    output.strategic_reserve_flow_cap = value.strategic_reserve_flow_cap;
    return output;
}

void fill_energy_rules(macro_sim_m8_energy_rules &output,
                       const macro_sim::simulation::EnergyRules &value) noexcept {
    std::memset(&output, 0, sizeof(output));
    output.struct_size = sizeof(output);
#define MACRO_SIM_FILL_ENERGY_FLAG(field) output.field = value.field ? 1U : 0U
    MACRO_SIM_FILL_ENERGY_FLAG(enabled);
    MACRO_SIM_FILL_ENERGY_FLAG(household_energy);
    MACRO_SIM_FILL_ENERGY_FLAG(deprivation);
    MACRO_SIM_FILL_ENERGY_FLAG(state_owned_first_producer);
#undef MACRO_SIM_FILL_ENERGY_FLAG
#define MACRO_SIM_FILL_ENERGY(field) output.field = value.field
    MACRO_SIM_FILL_ENERGY(deprivation_burnin_years);
    MACRO_SIM_FILL_ENERGY(deprivation_acute_days);
    MACRO_SIM_FILL_ENERGY(deprivation_chronic_days);
    MACRO_SIM_FILL_ENERGY(producer_count);
    MACRO_SIM_FILL_ENERGY(initial_producer_cash);
    MACRO_SIM_FILL_ENERGY(initial_price);
    MACRO_SIM_FILL_ENERGY(initial_wage);
    MACRO_SIM_FILL_ENERGY(initial_markup);
    MACRO_SIM_FILL_ENERGY(producer_productivity);
    MACRO_SIM_FILL_ENERGY(capacity_per_capital);
    MACRO_SIM_FILL_ENERGY(initial_utilization);
    MACRO_SIM_FILL_ENERGY(producer_inventory_ratio);
    MACRO_SIM_FILL_ENERGY(demand_adjustment);
    MACRO_SIM_FILL_ENERGY(markup_adjustment);
    MACRO_SIM_FILL_ENERGY(markup_minimum);
    MACRO_SIM_FILL_ENERGY(markup_maximum);
    MACRO_SIM_FILL_ENERGY(household_need);
    MACRO_SIM_FILL_ENERGY(downstream_intensity);
    MACRO_SIM_FILL_ENERGY(downstream_coverage_days);
    MACRO_SIM_FILL_ENERGY(downstream_gap_close);
    MACRO_SIM_FILL_ENERGY(hoarding_beta);
    MACRO_SIM_FILL_ENERGY(slow_price_days);
    MACRO_SIM_FILL_ENERGY(deprivation_subsistence_share);
    MACRO_SIM_FILL_ENERGY(fuel_poverty_threshold);
    MACRO_SIM_FILL_ENERGY(fuel_poverty_mortality_gamma);
    MACRO_SIM_FILL_ENERGY(fuel_poverty_mortality_cap);
#undef MACRO_SIM_FILL_ENERGY
}

macro_sim::simulation::EnergyRules
energy_rules_from_c(const macro_sim_m8_energy_rules &value) noexcept {
    macro_sim::simulation::EnergyRules output;
#define MACRO_SIM_COPY_ENERGY_FLAG(field) output.field = value.field != 0
    MACRO_SIM_COPY_ENERGY_FLAG(enabled);
    MACRO_SIM_COPY_ENERGY_FLAG(household_energy);
    MACRO_SIM_COPY_ENERGY_FLAG(deprivation);
    MACRO_SIM_COPY_ENERGY_FLAG(state_owned_first_producer);
#undef MACRO_SIM_COPY_ENERGY_FLAG
#define MACRO_SIM_COPY_ENERGY(field) output.field = value.field
    MACRO_SIM_COPY_ENERGY(deprivation_burnin_years);
    MACRO_SIM_COPY_ENERGY(deprivation_acute_days);
    MACRO_SIM_COPY_ENERGY(deprivation_chronic_days);
    MACRO_SIM_COPY_ENERGY(producer_count);
    MACRO_SIM_COPY_ENERGY(initial_producer_cash);
    MACRO_SIM_COPY_ENERGY(initial_price);
    MACRO_SIM_COPY_ENERGY(initial_wage);
    MACRO_SIM_COPY_ENERGY(initial_markup);
    MACRO_SIM_COPY_ENERGY(producer_productivity);
    MACRO_SIM_COPY_ENERGY(capacity_per_capital);
    MACRO_SIM_COPY_ENERGY(initial_utilization);
    MACRO_SIM_COPY_ENERGY(producer_inventory_ratio);
    MACRO_SIM_COPY_ENERGY(demand_adjustment);
    MACRO_SIM_COPY_ENERGY(markup_adjustment);
    MACRO_SIM_COPY_ENERGY(markup_minimum);
    MACRO_SIM_COPY_ENERGY(markup_maximum);
    MACRO_SIM_COPY_ENERGY(household_need);
    MACRO_SIM_COPY_ENERGY(downstream_intensity);
    MACRO_SIM_COPY_ENERGY(downstream_coverage_days);
    MACRO_SIM_COPY_ENERGY(downstream_gap_close);
    MACRO_SIM_COPY_ENERGY(hoarding_beta);
    MACRO_SIM_COPY_ENERGY(slow_price_days);
    MACRO_SIM_COPY_ENERGY(deprivation_subsistence_share);
    MACRO_SIM_COPY_ENERGY(fuel_poverty_threshold);
    MACRO_SIM_COPY_ENERGY(fuel_poverty_mortality_gamma);
    MACRO_SIM_COPY_ENERGY(fuel_poverty_mortality_cap);
#undef MACRO_SIM_COPY_ENERGY
    return output;
}

void fill_energy_input(
    macro_sim_m8_energy_input &output,
    const macro_sim::simulation::EnergyExogenousInput &value) noexcept {
    std::memset(&output, 0, sizeof(output));
    output.struct_size = sizeof(output);
#define MACRO_SIM_FILL_ENERGY_INPUT(field) output.field = value.field
    MACRO_SIM_FILL_ENERGY_INPUT(capacity_multiplier);
    MACRO_SIM_FILL_ENERGY_INPUT(labor_availability_multiplier);
    MACRO_SIM_FILL_ENERGY_INPUT(supply_multiplier);
    MACRO_SIM_FILL_ENERGY_INPUT(household_demand_multiplier);
    MACRO_SIM_FILL_ENERGY_INPUT(industry_demand_multiplier);
    MACRO_SIM_FILL_ENERGY_INPUT(reference_price_multiplier);
#undef MACRO_SIM_FILL_ENERGY_INPUT
}

macro_sim::simulation::EnergyExogenousInput
energy_input_from_c(const macro_sim_m8_energy_input &value) noexcept {
    return {
        value.capacity_multiplier,        value.labor_availability_multiplier,
        value.supply_multiplier,          value.household_demand_multiplier,
        value.industry_demand_multiplier, value.reference_price_multiplier,
    };
}

void fill_housing_policy(
    macro_sim_m8_housing_policy &output,
    const macro_sim::simulation::HousingPolicyState &value) noexcept {
    std::memset(&output, 0, sizeof(output));
    output.struct_size = sizeof(output);
    output.mortgage_underwriting = value.mortgage_underwriting ? 1U : 0U;
#define MACRO_SIM_FILL_HOUSING_POLICY(field) output.field = value.field
    MACRO_SIM_FILL_HOUSING_POLICY(rental_eviction_arrears);
    MACRO_SIM_FILL_HOUSING_POLICY(annual_housing_permits);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_ltv_cap);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_dsti_cap);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_stress_rate_addon);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_risk_weight);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_minimum_capital_ratio);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_foreclosure_ltv);
    MACRO_SIM_FILL_HOUSING_POLICY(mortgage_arrears_floor);
    MACRO_SIM_FILL_HOUSING_POLICY(land_fee_share);
    MACRO_SIM_FILL_HOUSING_POLICY(land_fee_stock_elasticity);
    MACRO_SIM_FILL_HOUSING_POLICY(transfer_tax_rate);
    MACRO_SIM_FILL_HOUSING_POLICY(property_tax_rate);
#undef MACRO_SIM_FILL_HOUSING_POLICY
}

macro_sim::simulation::HousingPolicyState
housing_policy_from_c(const macro_sim_m8_housing_policy &value) noexcept {
    macro_sim::simulation::HousingPolicyState output;
    output.mortgage_underwriting = value.mortgage_underwriting != 0;
#define MACRO_SIM_COPY_HOUSING_POLICY(field) output.field = value.field
    MACRO_SIM_COPY_HOUSING_POLICY(rental_eviction_arrears);
    MACRO_SIM_COPY_HOUSING_POLICY(annual_housing_permits);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_ltv_cap);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_dsti_cap);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_stress_rate_addon);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_risk_weight);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_minimum_capital_ratio);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_foreclosure_ltv);
    MACRO_SIM_COPY_HOUSING_POLICY(mortgage_arrears_floor);
    MACRO_SIM_COPY_HOUSING_POLICY(land_fee_share);
    MACRO_SIM_COPY_HOUSING_POLICY(land_fee_stock_elasticity);
    MACRO_SIM_COPY_HOUSING_POLICY(transfer_tax_rate);
    MACRO_SIM_COPY_HOUSING_POLICY(property_tax_rate);
#undef MACRO_SIM_COPY_HOUSING_POLICY
    return output;
}

void fill_housing_rules(macro_sim_m8_housing_rules &output,
                        const macro_sim::simulation::HousingRules &value) noexcept {
    std::memset(&output, 0, sizeof(output));
    output.struct_size = sizeof(output);
#define MACRO_SIM_FILL_HOUSING_FLAG(field) output.field = value.field ? 1U : 0U
    MACRO_SIM_FILL_HOUSING_FLAG(enabled);
    MACRO_SIM_FILL_HOUSING_FLAG(resale_market);
    MACRO_SIM_FILL_HOUSING_FLAG(mortgages);
    MACRO_SIM_FILL_HOUSING_FLAG(rentals);
    MACRO_SIM_FILL_HOUSING_FLAG(construction);
    MACRO_SIM_FILL_HOUSING_FLAG(builder_land_fee_credit);
#undef MACRO_SIM_FILL_HOUSING_FLAG
#define MACRO_SIM_FILL_HOUSING_RULE(field) output.field = value.field
    MACRO_SIM_FILL_HOUSING_RULE(location_count);
    MACRO_SIM_FILL_HOUSING_RULE(market_interval_days);
    MACRO_SIM_FILL_HOUSING_RULE(buyer_search_count);
    MACRO_SIM_FILL_HOUSING_RULE(affordability_burnin_years);
    MACRO_SIM_FILL_HOUSING_RULE(builder_count);
    MACRO_SIM_FILL_HOUSING_RULE(house_price_income_years);
    MACRO_SIM_FILL_HOUSING_RULE(initial_dwellings_per_household);
    MACRO_SIM_FILL_HOUSING_RULE(initial_homeownership_share);
    MACRO_SIM_FILL_HOUSING_RULE(initial_floor_area);
    MACRO_SIM_FILL_HOUSING_RULE(initial_quality);
    MACRO_SIM_FILL_HOUSING_RULE(voluntary_ask_markup);
    MACRO_SIM_FILL_HOUSING_RULE(forced_sale_discount);
    MACRO_SIM_FILL_HOUSING_RULE(ask_decay);
    MACRO_SIM_FILL_HOUSING_RULE(demand_price_step);
    MACRO_SIM_FILL_HOUSING_RULE(ask_floor_annual_wage_share);
    MACRO_SIM_FILL_HOUSING_RULE(buyer_liquidity_buffer);
    MACRO_SIM_FILL_HOUSING_RULE(distress_deposit_floor);
    MACRO_SIM_FILL_HOUSING_RULE(initial_rent_yield);
    MACRO_SIM_FILL_HOUSING_RULE(rent_adjustment);
    MACRO_SIM_FILL_HOUSING_RULE(rent_burden_cap);
    MACRO_SIM_FILL_HOUSING_RULE(rental_investor_premium);
    MACRO_SIM_FILL_HOUSING_RULE(rental_vacancy_deadband);
    MACRO_SIM_FILL_HOUSING_RULE(rent_floor_wage_share);
    MACRO_SIM_FILL_HOUSING_RULE(initial_builder_cash_buffer);
    MACRO_SIM_FILL_HOUSING_RULE(builder_productivity);
    MACRO_SIM_FILL_HOUSING_RULE(builder_demand_seed);
    MACRO_SIM_FILL_HOUSING_RULE(builder_demand_price_gain);
    MACRO_SIM_FILL_HOUSING_RULE(builder_finished_inventory_buffer);
    MACRO_SIM_FILL_HOUSING_RULE(leave_home_elasticity);
    MACRO_SIM_FILL_HOUSING_RULE(leave_home_multiplier_minimum);
    MACRO_SIM_FILL_HOUSING_RULE(leave_home_multiplier_maximum);
    MACRO_SIM_FILL_HOUSING_RULE(fertility_elasticity);
    MACRO_SIM_FILL_HOUSING_RULE(fertility_multiplier_minimum);
    MACRO_SIM_FILL_HOUSING_RULE(fertility_multiplier_maximum);
#undef MACRO_SIM_FILL_HOUSING_RULE
}

macro_sim::simulation::HousingRules
housing_rules_from_c(const macro_sim_m8_housing_rules &value) noexcept {
    macro_sim::simulation::HousingRules output;
#define MACRO_SIM_COPY_HOUSING_FLAG(field) output.field = value.field != 0
    MACRO_SIM_COPY_HOUSING_FLAG(enabled);
    MACRO_SIM_COPY_HOUSING_FLAG(resale_market);
    MACRO_SIM_COPY_HOUSING_FLAG(mortgages);
    MACRO_SIM_COPY_HOUSING_FLAG(rentals);
    MACRO_SIM_COPY_HOUSING_FLAG(construction);
    MACRO_SIM_COPY_HOUSING_FLAG(builder_land_fee_credit);
#undef MACRO_SIM_COPY_HOUSING_FLAG
#define MACRO_SIM_COPY_HOUSING_RULE(field) output.field = value.field
    MACRO_SIM_COPY_HOUSING_RULE(location_count);
    MACRO_SIM_COPY_HOUSING_RULE(market_interval_days);
    MACRO_SIM_COPY_HOUSING_RULE(buyer_search_count);
    MACRO_SIM_COPY_HOUSING_RULE(affordability_burnin_years);
    MACRO_SIM_COPY_HOUSING_RULE(builder_count);
    MACRO_SIM_COPY_HOUSING_RULE(house_price_income_years);
    MACRO_SIM_COPY_HOUSING_RULE(initial_dwellings_per_household);
    MACRO_SIM_COPY_HOUSING_RULE(initial_homeownership_share);
    MACRO_SIM_COPY_HOUSING_RULE(initial_floor_area);
    MACRO_SIM_COPY_HOUSING_RULE(initial_quality);
    MACRO_SIM_COPY_HOUSING_RULE(voluntary_ask_markup);
    MACRO_SIM_COPY_HOUSING_RULE(forced_sale_discount);
    MACRO_SIM_COPY_HOUSING_RULE(ask_decay);
    MACRO_SIM_COPY_HOUSING_RULE(demand_price_step);
    MACRO_SIM_COPY_HOUSING_RULE(ask_floor_annual_wage_share);
    MACRO_SIM_COPY_HOUSING_RULE(buyer_liquidity_buffer);
    MACRO_SIM_COPY_HOUSING_RULE(distress_deposit_floor);
    MACRO_SIM_COPY_HOUSING_RULE(initial_rent_yield);
    MACRO_SIM_COPY_HOUSING_RULE(rent_adjustment);
    MACRO_SIM_COPY_HOUSING_RULE(rent_burden_cap);
    MACRO_SIM_COPY_HOUSING_RULE(rental_investor_premium);
    MACRO_SIM_COPY_HOUSING_RULE(rental_vacancy_deadband);
    MACRO_SIM_COPY_HOUSING_RULE(rent_floor_wage_share);
    MACRO_SIM_COPY_HOUSING_RULE(initial_builder_cash_buffer);
    MACRO_SIM_COPY_HOUSING_RULE(builder_productivity);
    MACRO_SIM_COPY_HOUSING_RULE(builder_demand_seed);
    MACRO_SIM_COPY_HOUSING_RULE(builder_demand_price_gain);
    MACRO_SIM_COPY_HOUSING_RULE(builder_finished_inventory_buffer);
    MACRO_SIM_COPY_HOUSING_RULE(leave_home_elasticity);
    MACRO_SIM_COPY_HOUSING_RULE(leave_home_multiplier_minimum);
    MACRO_SIM_COPY_HOUSING_RULE(leave_home_multiplier_maximum);
    MACRO_SIM_COPY_HOUSING_RULE(fertility_elasticity);
    MACRO_SIM_COPY_HOUSING_RULE(fertility_multiplier_minimum);
    MACRO_SIM_COPY_HOUSING_RULE(fertility_multiplier_maximum);
#undef MACRO_SIM_COPY_HOUSING_RULE
    return output;
}

void fill_housing_input(
    macro_sim_m8_housing_input &output,
    const macro_sim::simulation::HousingExogenousInput &value) noexcept {
    std::memset(&output, 0, sizeof(output));
    output.struct_size = sizeof(output);
#define MACRO_SIM_FILL_HOUSING_INPUT(field) output.field = value.field
    MACRO_SIM_FILL_HOUSING_INPUT(house_price_reference_multiplier);
    MACRO_SIM_FILL_HOUSING_INPUT(buyer_demand_multiplier);
    MACRO_SIM_FILL_HOUSING_INPUT(rental_demand_multiplier);
    MACRO_SIM_FILL_HOUSING_INPUT(construction_productivity_multiplier);
    MACRO_SIM_FILL_HOUSING_INPUT(land_cost_multiplier);
#undef MACRO_SIM_FILL_HOUSING_INPUT
}

macro_sim::simulation::HousingExogenousInput
housing_input_from_c(const macro_sim_m8_housing_input &value) noexcept {
    return {
        value.house_price_reference_multiplier,
        value.buyer_demand_multiplier,
        value.rental_demand_multiplier,
        value.construction_productivity_multiplier,
        value.land_cost_multiplier,
    };
}

bool valid_m8_genesis_options(const macro_sim_m8_genesis_options &options) noexcept {
    return options.struct_size == sizeof(options) && options.reserved == 0 &&
           valid_m7_genesis_options(options.domestic_economy) &&
           options.energy_policy.struct_size == sizeof(options.energy_policy) &&
           options.energy_rules.struct_size == sizeof(options.energy_rules) &&
           options.energy_input.struct_size == sizeof(options.energy_input) &&
           options.housing_policy.struct_size == sizeof(options.housing_policy) &&
           options.housing_rules.struct_size == sizeof(options.housing_rules) &&
           options.housing_input.struct_size == sizeof(options.housing_input) &&
           valid_flag(options.energy_policy.price_cap_compensation) &&
           valid_flag(options.energy_policy.state_owned_price_at_cost) &&
           options.energy_policy.rationing <=
               MACRO_SIM_M8_ENERGY_RATION_INDUSTRY_FIRST &&
           valid_flag(options.energy_rules.enabled) &&
           valid_flag(options.energy_rules.household_energy) &&
           valid_flag(options.energy_rules.deprivation) &&
           valid_flag(options.energy_rules.state_owned_first_producer) &&
           options.energy_rules.reserved == 0 && options.energy_input.reserved == 0 &&
           valid_flag(options.housing_policy.mortgage_underwriting) &&
           options.housing_policy.reserved == 0 &&
           valid_flag(options.housing_rules.enabled) &&
           valid_flag(options.housing_rules.resale_market) &&
           valid_flag(options.housing_rules.mortgages) &&
           valid_flag(options.housing_rules.rentals) &&
           valid_flag(options.housing_rules.construction) &&
           valid_flag(options.housing_rules.builder_land_fee_credit) &&
           options.housing_rules.reserved == 0 && options.housing_input.reserved == 0;
}

macro_sim::simulation::M8SimulationSpec
make_m8_spec(const macro_sim_m8_genesis_options &options) {
    macro_sim::simulation::M8SimulationSpec spec;
    spec.domestic_economy = make_m7_spec(options.domestic_economy);
    spec.energy_policy = energy_policy_from_c(options.energy_policy);
    spec.energy_rules = energy_rules_from_c(options.energy_rules);
    spec.energy_input = energy_input_from_c(options.energy_input);
    spec.housing_policy = housing_policy_from_c(options.housing_policy);
    spec.housing_rules = housing_rules_from_c(options.housing_rules);
    spec.housing_input = housing_input_from_c(options.housing_input);
    return spec;
}

macro_sim::simulation::WorldRules
world_rules_from_c(const macro_sim_m9_world_rules &value) noexcept {
    macro_sim::simulation::WorldRules output;
    output.trade = value.trade != 0U;
    output.capital = value.capital != 0U;
    output.migration = value.migration != 0U;
    output.fx_loss_mutualization = value.fx_loss_mutualization != 0U;
    output.dense_edge_threshold = static_cast<std::size_t>(value.dense_edge_threshold);
    output.fx_adjustment = value.fx_adjustment;
    output.fx_friction = value.fx_friction;
    output.fx_spread = value.fx_spread;
    output.fx_trade_cap = value.fx_trade_cap;
    output.capital_mobility = value.capital_mobility;
    output.capital_adjustment = value.capital_adjustment;
    output.periods_per_year = value.periods_per_year;
    output.migration_rate = value.migration_rate;
    output.migration_max_share = value.migration_max_share;
    output.remittance_share = value.remittance_share;
    output.wage_smoothing = value.wage_smoothing;
    output.initial_peg_reserves = value.initial_peg_reserves;
    return output;
}

bool valid_m9_world_rules(const macro_sim_m9_world_rules &value) noexcept {
    return value.struct_size == sizeof(value) && valid_flag(value.trade) &&
           valid_flag(value.capital) && valid_flag(value.migration) &&
           valid_flag(value.fx_loss_mutualization) && value.reserved == 0U &&
           value.dense_edge_threshold != 0U;
}

bool valid_m9_external_policy(const macro_sim_m9_external_policy &value) noexcept {
    return value.struct_size == sizeof(value) && valid_flag(value.has_import_quota) &&
           valid_flag(value.has_immigration_cap) &&
           valid_flag(value.has_emigration_cap) &&
           value.fx_regime <= MACRO_SIM_M9_FX_PEG && valid_flag(value.has_peg_anchor) &&
           value.reserved == 0U && value.reserved_2 == 0U &&
           (value.sanction_count == 0U || value.sanctions != nullptr);
}

macro_sim::simulation::ExternalPolicyState
external_policy_from_c(const macro_sim_m9_external_policy &value) {
    macro_sim::simulation::ExternalPolicyState output;
    output.tariff = value.tariff;
    if (value.has_import_quota != 0U) {
        output.import_quota = value.import_quota;
    }
    output.export_subsidy = value.export_subsidy;
    output.capital_control = value.capital_control;
    output.external_interest_settlement_fraction =
        value.external_interest_settlement_fraction;
    output.sanctions_imposed_on.reserve(value.sanction_count);
    for (std::size_t index = 0; index < value.sanction_count; ++index) {
        output.sanctions_imposed_on.emplace_back(value.sanctions[index]);
    }
    if (value.has_immigration_cap != 0U) {
        output.immigration_cap = value.immigration_cap;
    }
    if (value.has_emigration_cap != 0U) {
        output.emigration_cap = value.emigration_cap;
    }
    output.remittance_tax = value.remittance_tax;
    output.outward_remittance_tax = value.outward_remittance_tax;
    output.guest_worker_return = value.guest_worker_return;
    output.fx_regime = static_cast<macro_sim::simulation::FxRegime>(value.fx_regime);
    if (value.has_peg_anchor != 0U) {
        output.peg_anchor = macro_sim::EconomyId(value.peg_anchor);
    }
    output.peg_reserve_scale = value.peg_reserve_scale;
    return output;
}

bool valid_m9_shock(const macro_sim_m9_shock &value) noexcept {
    return value.struct_size == sizeof(value) &&
           value.kind <= MACRO_SIM_M9_SHOCK_CAPITAL_DESTRUCTION &&
           value.shape <= MACRO_SIM_M9_SHOCK_TRIANGULAR &&
           valid_flag(value.has_economy) && valid_flag(value.has_announcement) &&
           valid_flag(value.has_sector) &&
           (value.has_sector == 0U ||
            value.sector <= MACRO_SIM_M9_SHOCK_SECTOR_PUBLIC) &&
           value.reserved == 0U;
}

macro_sim::simulation::ShockSpec
shock_from_c(const macro_sim_m9_shock &value) noexcept {
    macro_sim::simulation::ShockSpec output;
    output.id = value.id;
    output.kind = static_cast<macro_sim::simulation::ShockKind>(value.kind);
    if (value.has_economy != 0U) {
        output.economy = macro_sim::EconomyId(value.economy_id);
    }
    output.start = macro_sim::Tick(value.start_tick);
    if (value.has_announcement != 0U) {
        output.announcement = macro_sim::Tick(value.announcement_tick);
    }
    output.duration = value.duration;
    output.magnitude = value.magnitude;
    output.ramp_in_ticks = value.ramp_in_ticks;
    output.ramp_out_ticks = value.ramp_out_ticks;
    output.shape = static_cast<macro_sim::simulation::ShockShape>(value.shape);
    if (value.has_sector != 0U) {
        output.sector = static_cast<macro_sim::simulation::ShockSector>(value.sector);
    }
    return output;
}

void fill_m8_metrics(macro_sim_m8_metrics &output,
                     const macro_sim::simulation::M8Metrics &value) noexcept {
    output.reserved = 0;
    fill_m7_metrics(output.economy, value.economy);
    output.energy.deprivation_boundary = value.energy.deprivation_boundary ? 1U : 0U;
#define MACRO_SIM_FILL_M8_ENERGY(field) output.energy.field = value.energy.field
    MACRO_SIM_FILL_M8_ENERGY(production);
    MACRO_SIM_FILL_M8_ENERGY(capacity);
    MACRO_SIM_FILL_M8_ENERGY(utilization);
    MACRO_SIM_FILL_M8_ENERGY(opening_supply);
    MACRO_SIM_FILL_M8_ENERGY(requested_total);
    MACRO_SIM_FILL_M8_ENERGY(requested_households);
    MACRO_SIM_FILL_M8_ENERGY(requested_industry);
    MACRO_SIM_FILL_M8_ENERGY(requested_public);
    MACRO_SIM_FILL_M8_ENERGY(sold);
    MACRO_SIM_FILL_M8_ENERGY(unfilled);
    MACRO_SIM_FILL_M8_ENERGY(transaction_price);
    MACRO_SIM_FILL_M8_ENERGY(household_units);
    MACRO_SIM_FILL_M8_ENERGY(household_spending);
    MACRO_SIM_FILL_M8_ENERGY(industry_units);
    MACRO_SIM_FILL_M8_ENERGY(industry_spending);
    MACRO_SIM_FILL_M8_ENERGY(excise_paid);
    MACRO_SIM_FILL_M8_ENERGY(subsidy_paid);
    MACRO_SIM_FILL_M8_ENERGY(cap_compensation);
    MACRO_SIM_FILL_M8_ENERGY(strategic_reserve_stock);
    MACRO_SIM_FILL_M8_ENERGY(strategic_reserve_flow);
    MACRO_SIM_FILL_M8_ENERGY(strategic_reserve_purchase_paid);
    MACRO_SIM_FILL_M8_ENERGY(strategic_reserve_sale_revenue);
    MACRO_SIM_FILL_M8_ENERGY(fuel_poverty_share);
    MACRO_SIM_FILL_M8_ENERGY(fuel_poverty_mortality_multiplier);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_below_100_share);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_below_60_share);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_below_30_share);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_destitute_share);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_acute_stock);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_chronic_stock);
    MACRO_SIM_FILL_M8_ENERGY(deprivation_max_spell_days);
    MACRO_SIM_FILL_M8_ENERGY(producer_capital);
#undef MACRO_SIM_FILL_M8_ENERGY
    output.housing.reserved = 0;
#define MACRO_SIM_FILL_M8_HOUSING(field) output.housing.field = value.housing.field
    MACRO_SIM_FILL_M8_HOUSING(house_price);
    MACRO_SIM_FILL_M8_HOUSING(rent_level);
    MACRO_SIM_FILL_M8_HOUSING(housing_stock);
    MACRO_SIM_FILL_M8_HOUSING(homeownership_share);
    MACRO_SIM_FILL_M8_HOUSING(vacancy_share);
    MACRO_SIM_FILL_M8_HOUSING(active_listings);
    MACRO_SIM_FILL_M8_HOUSING(forced_listing_share);
    MACRO_SIM_FILL_M8_HOUSING(session_sales);
    MACRO_SIM_FILL_M8_HOUSING(session_volume);
    MACRO_SIM_FILL_M8_HOUSING(mean_time_on_market_days);
    MACRO_SIM_FILL_M8_HOUSING(mortgage_originations);
    MACRO_SIM_FILL_M8_HOUSING(mortgage_principal_originated);
    MACRO_SIM_FILL_M8_HOUSING(mortgage_principal_outstanding);
    MACRO_SIM_FILL_M8_HOUSING(foreclosures);
    MACRO_SIM_FILL_M8_HOUSING(rent_paid);
    MACRO_SIM_FILL_M8_HOUSING(rent_unpaid);
    MACRO_SIM_FILL_M8_HOUSING(evictions);
    MACRO_SIM_FILL_M8_HOUSING(property_tax_paid);
    MACRO_SIM_FILL_M8_HOUSING(transfer_tax_paid);
    MACRO_SIM_FILL_M8_HOUSING(land_fee_paid);
    MACRO_SIM_FILL_M8_HOUSING(construction_output);
    MACRO_SIM_FILL_M8_HOUSING(dwellings_completed);
    MACRO_SIM_FILL_M8_HOUSING(permits_used);
    MACRO_SIM_FILL_M8_HOUSING(price_to_income_ratio);
    MACRO_SIM_FILL_M8_HOUSING(rent_burden_ratio);
    MACRO_SIM_FILL_M8_HOUSING(leave_home_multiplier);
    MACRO_SIM_FILL_M8_HOUSING(fertility_multiplier);
#undef MACRO_SIM_FILL_M8_HOUSING
}

} // namespace

uint32_t macro_sim_abi_version(void) { return macro_sim::abi_version(); }

uint64_t macro_sim_capabilities(void) {
    return MACRO_SIM_CAPABILITY_M2_ACCOUNTING | MACRO_SIM_CAPABILITY_M3_ALGORITHMS |
           MACRO_SIM_CAPABILITY_M4_TICK | MACRO_SIM_CAPABILITY_M5_MONETARY |
           MACRO_SIM_CAPABILITY_M6_SECURITIES | MACRO_SIM_CAPABILITY_M7_POPULATION |
           MACRO_SIM_CAPABILITY_M8_ENERGY_HOUSING | MACRO_SIM_CAPABILITY_M9_WORLD;
}

const char *macro_sim_engine_version(void) { return macro_sim::kEngineVersion.data(); }

const char *macro_sim_error_code_name(macro_sim_error_code code) {
    return macro_sim::error_code_name(static_cast<macro_sim::ErrorCode>(code)).data();
}

macro_sim_status macro_sim_session_create(const macro_sim_create_options *options,
                                          macro_sim_session **output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "output must not be null");
    }
    *output = nullptr;
    std::uint64_t session_id = 1;
    if (options != nullptr) {
        if (options->struct_size != sizeof(macro_sim_create_options)) {
            return status(MACRO_SIM_INVALID_ARGUMENT, "create options size mismatch");
        }
        if (options->abi_version != MACRO_SIM_ABI_VERSION) {
            return status(MACRO_SIM_INCOMPATIBLE_ABI, "ABI version mismatch");
        }
        if (options->session_id == UINT64_MAX) {
            return status(MACRO_SIM_INVALID_ARGUMENT, "session ID is invalid");
        }
        session_id = options->session_id;
    }
    try {
        *output = new macro_sim_session(session_id);
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "session allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "session creation failed");
    }
}

macro_sim_status macro_sim_session_destroy(macro_sim_session **session) {
    if (session == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session pointer must not be null");
    }
    if (*session == nullptr) {
        return status(MACRO_SIM_INVALID_HANDLE, "session is already null");
    }
    delete *session;
    *session = nullptr;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_session_id(const macro_sim_session *session,
                                      uint64_t *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.id().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_session_tick(const macro_sim_session *session,
                                        uint64_t *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.tick().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_validate_scalar(const char *contract_id,
                                           size_t contract_id_size,
                                           const macro_sim_scalar *value,
                                           macro_sim_validation_code *output) {
    if (contract_id == nullptr || value == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "contract ID, scalar, and output are required");
    }
    macro_sim::generated::ScalarValue native_value{};
    switch (value->kind) {
    case MACRO_SIM_SCALAR_NULL:
        native_value.kind = macro_sim::generated::InputKind::null_value;
        break;
    case MACRO_SIM_SCALAR_BOOLEAN:
        native_value.kind = macro_sim::generated::InputKind::boolean;
        native_value.number = value->integer_value == 0 ? 0.0 : 1.0;
        break;
    case MACRO_SIM_SCALAR_INTEGER:
        native_value.kind = macro_sim::generated::InputKind::integer;
        native_value.number = static_cast<double>(value->integer_value);
        break;
    case MACRO_SIM_SCALAR_NUMBER:
        native_value.kind = macro_sim::generated::InputKind::number;
        native_value.number = value->number_value;
        break;
    case MACRO_SIM_SCALAR_STRING:
        if (value->string_value == nullptr && value->string_size != 0) {
            return status(MACRO_SIM_INVALID_ARGUMENT,
                          "nonempty string scalar has a null pointer");
        }
        native_value.kind = macro_sim::generated::InputKind::string;
        native_value.text =
            std::string_view(value->string_value == nullptr ? "" : value->string_value,
                             value->string_size);
        break;
    case MACRO_SIM_SCALAR_ID_SET:
        native_value.kind = macro_sim::generated::InputKind::id_set;
        break;
    default:
        return status(MACRO_SIM_INVALID_ARGUMENT, "unknown scalar kind");
    }
    const auto code = macro_sim::generated::validate_scalar(
        std::string_view(contract_id, contract_id_size), native_value);
    *output = static_cast<macro_sim_validation_code>(code);
    return status(MACRO_SIM_OK, "");
}

const char *macro_sim_validation_code_name(macro_sim_validation_code code) {
    return macro_sim::generated::validation_code_name(
               static_cast<macro_sim::generated::ValidationCode>(code))
        .data();
}

macro_sim_status macro_sim_m2_genesis(macro_sim_session *session,
                                      const macro_sim_m2_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m2_genesis_options) ||
        options->vertical > MACRO_SIM_M2_M4_V1_CAPITAL_FISCAL ||
        options->government > 1) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "genesis options are invalid");
    }
    macro_sim::core::GenesisSpec spec;
    spec.vertical = static_cast<macro_sim::core::GenesisVertical>(options->vertical);
    spec.economy = macro_sim::EconomyId(options->economy_id);
    spec.currency = macro_sim::CurrencyId(options->currency_id);
    spec.households = options->households;
    spec.consumption_firms = options->consumption_firms;
    spec.capital_firms = options->capital_firms;
    spec.settlement_banks = options->settlement_banks;
    spec.government = options->government != 0;
    spec.aggregate_opening_money = macro_sim::Money(options->aggregate_opening_money);
    spec.aggregate_opening_capital =
        macro_sim::Capital(options->aggregate_opening_capital);
    spec.seed = options->seed;
    return status(session->engine.initialize(spec));
}

macro_sim_status macro_sim_m2_apply_batch(macro_sim_session *session,
                                          const macro_sim_m2_command *commands,
                                          size_t command_count,
                                          macro_sim_m2_receipt *output) {
    if (session == nullptr || output == nullptr ||
        (commands == nullptr && command_count != 0)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session, commands, and receipt are invalid");
    }
    if (output->struct_size != sizeof(macro_sim_m2_receipt)) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "receipt structure size mismatch");
    }
    if (command_count > 1'000'000) {
        return status(MACRO_SIM_OUT_OF_RANGE, "command count limit is exceeded");
    }
    macro_sim::core::SettlementBatch batch;
    try {
        for (std::size_t index = 0; index < command_count; ++index) {
            const auto &command = commands[index];
            if (command.struct_size != sizeof(macro_sim_m2_command) ||
                command.reserved != 0) {
                return status(MACRO_SIM_INVALID_ARGUMENT,
                              "command structure is invalid");
            }
            if (command.owner_kind > MACRO_SIM_M2_OWNER_INSTITUTION ||
                command.tertiary_id > macro_sim::core::OwnerId::max_packed_value()) {
                return status(MACRO_SIM_INVALID_ARGUMENT, "command owner is invalid");
            }
            const macro_sim::core::OwnerId owner{
                static_cast<macro_sim::core::OwnerKind>(command.owner_kind),
                static_cast<std::uint32_t>(command.tertiary_id),
            };
            switch (command.kind) {
            case MACRO_SIM_M2_TRANSFER:
                batch.transfers.push_back({
                    macro_sim::AccountId(command.primary_id),
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_RESERVE_TRANSFER:
                batch.reserve_transfers.push_back({
                    macro_sim::SettlementNodeId(command.primary_id),
                    macro_sim::SettlementNodeId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_RESERVE_ISSUE:
                batch.reserve_issues.push_back({
                    macro_sim::SettlementNodeId(command.primary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_LOAN_ORIGINATION:
                batch.originations.push_back({
                    macro_sim::BankId(command.primary_id),
                    owner,
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                    {
                        macro_sim::Rate(command.rate),
                        macro_sim::Tick(command.tick_a),
                        macro_sim::Tick(command.tick_b),
                    },
                });
                break;
            case MACRO_SIM_M2_LOAN_REPAYMENT:
                batch.repayments.push_back({
                    macro_sim::LoanId(command.primary_id),
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_OWNERSHIP_MUTATION:
                batch.ownership_mutations.push_back({
                    macro_sim::OwnershipLotId(command.primary_id),
                    owner,
                    command.amount,
                });
                break;
            case MACRO_SIM_M2_COUNTER_INCREMENT:
                batch.counter_increments.push_back(
                    {command.primary_id, command.secondary_id});
                break;
            default:
                return status(MACRO_SIM_INVALID_ARGUMENT, "command kind is invalid");
            }
        }
        auto receipt = session->engine.apply(batch);
        if (!receipt.ok()) {
            return status(receipt.status());
        }
        output->reserved = 0;
        output->applied_mutations = receipt.get_if()->applied_mutations;
        output->created_loan_count = receipt.get_if()->created_loans.size();
        std::copy(receipt.get_if()->before.bytes.begin(),
                  receipt.get_if()->before.bytes.end(), output->before_digest);
        std::copy(receipt.get_if()->after.bytes.begin(),
                  receipt.get_if()->after.bytes.end(), output->after_digest);
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "batch allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "batch conversion failed");
    }
}

macro_sim_status macro_sim_m2_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    if (session == nullptr || output == nullptr || output_size != 32) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and 32-byte digest output are required");
    }
    const auto digest = session->engine.digest();
    if (!digest.ok()) {
        return status(digest.status());
    }
    std::copy(digest.get_if()->bytes.begin(), digest.get_if()->bytes.end(), output);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and checkpoint output are required");
    }
    output->data = nullptr;
    output->size = 0;
    const auto checkpoint = session->engine.checkpoint();
    if (!checkpoint.ok()) {
        return status(checkpoint.status());
    }
    const auto size = checkpoint.get_if()->size();
    auto *bytes = new (std::nothrow) std::uint8_t[size];
    if (bytes == nullptr && size != 0) {
        return status(MACRO_SIM_ALLOCATION_FAILURE,
                      "checkpoint output allocation failed");
    }
    std::memcpy(bytes, checkpoint.get_if()->data(), size);
    output->data = bytes;
    output->size = size;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    if (session == nullptr || (checkpoint == nullptr && checkpoint_size != 0)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and checkpoint input are invalid");
    }
    return status(session->engine.restore_checkpoint(
        std::span<const std::uint8_t>(checkpoint, checkpoint_size)));
}

macro_sim_status macro_sim_m4_genesis(macro_sim_session *session,
                                      const macro_sim_m4_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M4 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m4_genesis_options) ||
        options->vertical > MACRO_SIM_M4_CAPITAL_FISCAL ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        options->stochastic > 1 || options->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M4 genesis options are invalid");
    }
    macro_sim::simulation::M4SimulationSpec spec;
    spec.vertical = static_cast<macro_sim::simulation::M4Vertical>(options->vertical);
    spec.economy = macro_sim::EconomyId(options->economy_id);
    spec.currency = macro_sim::CurrencyId(options->currency_id);
    spec.market_protocol = static_cast<macro_sim::algorithms::MatchingProtocol>(
        options->matching_protocol);
    spec.stochastic = options->stochastic != 0;
    spec.households = options->households;
    spec.consumption_firms = options->consumption_firms;
    spec.capital_firms = options->capital_firms;
    spec.seed = options->seed;
    spec.requested_capabilities = options->requested_capabilities;
    return status(session->engine.initialize_simulation(spec));
}

macro_sim_status macro_sim_m4_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m4_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m4_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M4 result are required");
    }
    const auto result = session->engine.advance_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m4_metrics(output->metrics, metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m4_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m4_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m4_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m5_genesis(macro_sim_session *session,
                                      const macro_sim_m5_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M5 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m5_genesis_options) ||
        options->monetary_regime > MACRO_SIM_M5_MANUAL ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        !valid_flag(options->stochastic) ||
        !valid_flag(options->has_manual_policy_rate) ||
        !valid_flag(options->interbank) || !valid_flag(options->household_credit) ||
        !valid_flag(options->bank_runs) || options->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 genesis options are invalid");
    }
    macro_sim::simulation::M5SimulationSpec spec;
    spec.real_economy.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    spec.real_economy.economy = macro_sim::EconomyId(options->economy_id);
    spec.real_economy.currency = macro_sim::CurrencyId(options->currency_id);
    spec.real_economy.market_protocol =
        static_cast<macro_sim::algorithms::MatchingProtocol>(
            options->matching_protocol);
    spec.real_economy.stochastic = options->stochastic != 0;
    spec.real_economy.households = options->households;
    spec.real_economy.consumption_firms = options->consumption_firms;
    spec.real_economy.capital_firms = options->capital_firms;
    spec.real_economy.seed = options->seed;
    spec.real_economy.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    spec.rules.bank_count = options->banks;
    spec.rules.opening_capital_per_bank = options->opening_capital_per_bank;
    spec.rules.interbank = options->interbank != 0;
    spec.rules.household_credit = options->household_credit != 0;
    spec.rules.bank_runs = options->bank_runs != 0;
    spec.policy.monetary_regime =
        static_cast<macro_sim::simulation::MonetaryRegime>(options->monetary_regime);
    if (options->has_manual_policy_rate != 0) {
        spec.policy.manual_policy_rate = options->manual_policy_rate;
    }
    spec.initial_policy_rate = options->initial_policy_rate;
    return status(session->engine.initialize_m5(spec));
}

macro_sim_status macro_sim_m5_update_policy(macro_sim_session *session,
                                            const macro_sim_m5_policy *policy) {
    if (session == nullptr || policy == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and M5 policy are required");
    }
    if (policy->struct_size != sizeof(macro_sim_m5_policy) ||
        policy->monetary_regime > MACRO_SIM_M5_MANUAL ||
        !valid_flag(policy->has_manual_policy_rate) ||
        !valid_flag(policy->open_market_operations) ||
        !valid_flag(policy->reserve_target_indexes_deposits) ||
        !valid_flag(policy->lender_of_last_resort) ||
        !valid_flag(policy->bank_capital_constraint) ||
        !valid_flag(policy->unified_bank_rwa) ||
        !valid_flag(policy->migrate_relationships_on_failure) ||
        !valid_flag(policy->state_resolution_backstop) ||
        !valid_flag(policy->job_guarantee) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 policy structure is invalid");
    }
    macro_sim::simulation::M5PolicyState value;
    value.government_consumption_share = policy->government_consumption_share;
    value.government_deficit_target = policy->government_deficit_target;
    value.deficit_unemployment_reference = policy->deficit_unemployment_reference;
    value.deficit_unemployment_cap = policy->deficit_unemployment_cap;
    value.government_investment_share = policy->government_investment_share;
    value.profit_tax_rate = policy->profit_tax_rate;
    value.income_tax_rate = policy->income_tax_rate;
    value.income_allowance = policy->income_allowance;
    value.consumption_tax_rate = policy->consumption_tax_rate;
    value.wealth_tax_rate = policy->wealth_tax_rate;
    value.wealth_allowance = policy->wealth_allowance;
    value.unemployment_benefit_replacement = policy->unemployment_benefit_replacement;
    value.benefit_income_floor = policy->benefit_income_floor;
    value.minimum_wage = policy->minimum_wage;
    value.job_guarantee = policy->job_guarantee != 0;
    value.job_guarantee_wage_ratio = policy->job_guarantee_wage_ratio;
    value.job_guarantee_public_works_share = policy->job_guarantee_public_works_share;
    value.monetary_regime =
        static_cast<macro_sim::simulation::MonetaryRegime>(policy->monetary_regime);
    value.inflation_target = policy->inflation_target;
    value.taylor_inflation = policy->taylor_inflation;
    value.taylor_unemployment = policy->taylor_unemployment;
    value.rate_inertia = policy->rate_inertia;
    if (policy->has_manual_policy_rate != 0) {
        value.manual_policy_rate = policy->manual_policy_rate;
    }
    value.neutral_rate = policy->neutral_rate;
    value.natural_unemployment = policy->natural_unemployment;
    value.maximum_policy_rate = policy->maximum_policy_rate;
    value.inflation_sensor_lambda = policy->inflation_sensor_lambda;
    value.open_market_operations = policy->open_market_operations != 0;
    value.reserve_target = policy->reserve_target;
    value.reserve_gap_close = policy->reserve_gap_close;
    value.reserve_target_indexes_deposits =
        policy->reserve_target_indexes_deposits != 0;
    value.lender_of_last_resort = policy->lender_of_last_resort != 0;
    value.reserve_floor_fraction = policy->reserve_floor_fraction;
    value.firm_leverage_limit = policy->firm_leverage_limit;
    value.firm_minimum_dscr = policy->firm_minimum_dscr;
    value.household_credit_limit = policy->household_credit_limit;
    value.bank_capital_constraint = policy->bank_capital_constraint != 0;
    value.unified_bank_rwa = policy->unified_bank_rwa != 0;
    value.bank_leverage_cap = policy->bank_leverage_cap;
    value.bank_exposure_limit = policy->bank_exposure_limit;
    value.bank_target_capital_ratio = policy->bank_target_capital_ratio;
    value.deposit_rate_floor = policy->deposit_rate_floor;
    value.migrate_relationships_on_failure =
        policy->migrate_relationships_on_failure != 0;
    value.state_resolution_backstop = policy->state_resolution_backstop != 0;
    return status(session->engine.update_m5_policy(value));
}

macro_sim_status macro_sim_m5_policy_defaults(macro_sim_m5_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 policy output is required");
    }
    const macro_sim::simulation::M5PolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->monetary_regime = static_cast<std::uint32_t>(value.monetary_regime);
    output->open_market_operations = value.open_market_operations ? 1U : 0U;
    output->reserve_target_indexes_deposits =
        value.reserve_target_indexes_deposits ? 1U : 0U;
    output->lender_of_last_resort = value.lender_of_last_resort ? 1U : 0U;
    output->bank_capital_constraint = value.bank_capital_constraint ? 1U : 0U;
    output->unified_bank_rwa = value.unified_bank_rwa ? 1U : 0U;
    output->migrate_relationships_on_failure =
        value.migrate_relationships_on_failure ? 1U : 0U;
    output->state_resolution_backstop = value.state_resolution_backstop ? 1U : 0U;
    output->job_guarantee = value.job_guarantee ? 1U : 0U;
    output->government_consumption_share = value.government_consumption_share;
    output->government_deficit_target = value.government_deficit_target;
    output->deficit_unemployment_reference = value.deficit_unemployment_reference;
    output->deficit_unemployment_cap = value.deficit_unemployment_cap;
    output->government_investment_share = value.government_investment_share;
    output->profit_tax_rate = value.profit_tax_rate;
    output->income_tax_rate = value.income_tax_rate;
    output->income_allowance = value.income_allowance;
    output->consumption_tax_rate = value.consumption_tax_rate;
    output->wealth_tax_rate = value.wealth_tax_rate;
    output->wealth_allowance = value.wealth_allowance;
    output->unemployment_benefit_replacement = value.unemployment_benefit_replacement;
    output->benefit_income_floor = value.benefit_income_floor;
    output->minimum_wage = value.minimum_wage;
    output->job_guarantee_wage_ratio = value.job_guarantee_wage_ratio;
    output->job_guarantee_public_works_share = value.job_guarantee_public_works_share;
    output->inflation_target = value.inflation_target;
    output->taylor_inflation = value.taylor_inflation;
    output->taylor_unemployment = value.taylor_unemployment;
    output->rate_inertia = value.rate_inertia;
    output->neutral_rate = value.neutral_rate;
    output->natural_unemployment = value.natural_unemployment;
    output->maximum_policy_rate = value.maximum_policy_rate;
    output->inflation_sensor_lambda = value.inflation_sensor_lambda;
    output->reserve_target = value.reserve_target;
    output->reserve_gap_close = value.reserve_gap_close;
    output->reserve_floor_fraction = value.reserve_floor_fraction;
    output->firm_leverage_limit = value.firm_leverage_limit;
    output->firm_minimum_dscr = value.firm_minimum_dscr;
    output->household_credit_limit = value.household_credit_limit;
    output->bank_leverage_cap = value.bank_leverage_cap;
    output->bank_exposure_limit = value.bank_exposure_limit;
    output->bank_target_capital_ratio = value.bank_target_capital_ratio;
    output->deposit_rate_floor = value.deposit_rate_floor;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m5_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m5_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m5_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m5_metrics) ||
        output->metrics.economy.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M5 result are required");
    }
    const auto result = session->engine.advance_m5_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m5_metrics(output->metrics, metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m5_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m5_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m5_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m6_genesis(macro_sim_session *session,
                                      const macro_sim_m6_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M6 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m6_genesis_options) ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        !valid_flag(options->stochastic) || !valid_flag(options->bonds) ||
        !valid_flag(options->firm_equity) || !valid_flag(options->margin_credit) ||
        !valid_flag(options->firm_dynamics) || !valid_flag(options->bank_dynamics) ||
        options->reserved != 0 || options->portfolio_review_interval_days > 3'650U) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M6 genesis options are invalid");
    }
    macro_sim::simulation::M6SimulationSpec spec;
    auto &monetary = spec.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    real.economy = macro_sim::EconomyId(options->economy_id);
    real.currency = macro_sim::CurrencyId(options->currency_id);
    real.market_protocol = static_cast<macro_sim::algorithms::MatchingProtocol>(
        options->matching_protocol);
    real.stochastic = options->stochastic != 0;
    real.households = options->households;
    real.consumption_firms = options->consumption_firms;
    real.capital_firms = options->capital_firms;
    real.seed = options->seed;
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    monetary.rules.bank_count = options->banks;
    monetary.rules.opening_capital_per_bank = options->opening_capital_per_bank;
    monetary.initial_policy_rate = options->initial_policy_rate;
    spec.rules.bonds = options->bonds != 0;
    spec.rules.firm_equity = options->firm_equity != 0;
    spec.rules.margin_credit = options->margin_credit != 0;
    spec.rules.firm_dynamics = options->firm_dynamics != 0;
    spec.rules.bank_dynamics = options->bank_dynamics != 0;
    spec.rules.watchlist_size = options->watchlist_size;
    if (options->portfolio_review_interval_days != 0U) {
        spec.rules.portfolio_review_interval_days =
            options->portfolio_review_interval_days;
    }
    return status(session->engine.initialize_m6(spec));
}

macro_sim_status macro_sim_m6_update_policy(macro_sim_session *session,
                                            const macro_sim_m6_policy *policy) {
    if (session == nullptr || policy == nullptr ||
        policy->struct_size != sizeof(macro_sim_m6_policy) ||
        !valid_flag(policy->household_bankruptcy) ||
        !valid_flag(policy->bank_resolution_fund) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M6 policy are required");
    }
    macro_sim::simulation::M6PolicyState value;
    value.bond_finance_fraction = policy->bond_finance_fraction;
    value.bond_coupon_rate = policy->bond_coupon_rate;
    value.bond_maturity_days = policy->bond_maturity_days;
    value.household_bond_target = policy->household_bond_target;
    value.bank_bond_appetite = policy->bank_bond_appetite;
    value.bank_bond_duration_limit = policy->bank_bond_duration_limit;
    value.margin_ltv = policy->margin_ltv;
    value.margin_max = policy->margin_max;
    value.household_bankruptcy = policy->household_bankruptcy != 0;
    value.bank_resolution_fund = policy->bank_resolution_fund != 0;
    value.bank_minimum_capital = policy->bank_minimum_capital;
    return status(session->engine.update_m6_policy(value));
}

macro_sim_status macro_sim_m6_policy_defaults(macro_sim_m6_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M6 policy output is required");
    }
    const macro_sim::simulation::M6PolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->household_bankruptcy = value.household_bankruptcy ? 1U : 0U;
    output->bank_resolution_fund = value.bank_resolution_fund ? 1U : 0U;
    output->bond_maturity_days = value.bond_maturity_days;
    output->bond_finance_fraction = value.bond_finance_fraction;
    output->bond_coupon_rate = value.bond_coupon_rate;
    output->household_bond_target = value.household_bond_target;
    output->bank_bond_appetite = value.bank_bond_appetite;
    output->bank_bond_duration_limit = value.bank_bond_duration_limit;
    output->margin_ltv = value.margin_ltv;
    output->margin_max = value.margin_max;
    output->bank_minimum_capital = value.bank_minimum_capital;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m6_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m6_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m6_metrics) ||
        output->metrics.economy.struct_size != sizeof(macro_sim_m5_metrics) ||
        output->metrics.economy.economy.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M6 result are required");
    }
    const auto result = session->engine.advance_m6_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m6_metrics(output->metrics, metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m6_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m6_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m6_bond_count(const macro_sim_session *session,
                                         size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    *output = session->engine.securities_runtime()->securities.bonds().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_bonds(const macro_sim_session *session, size_t offset,
                                    macro_sim_m6_bond *output, size_t capacity,
                                    size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and bond output are required");
    }
    const auto &rows = session->engine.securities_runtime()->securities.bonds();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.issuer_kind = static_cast<std::uint32_t>(source.issuer.kind());
        target.id = source.id.value();
        target.issuer_id = source.issuer.value();
        target.issuer_account = source.issuer_account.value();
        target.currency_id = source.currency.value();
        target.active = source.active ? 1U : 0U;
        target.issued_tick = source.issued_tick.value();
        target.maturity_tick = source.maturity_tick.value();
        target.coupon_rate = source.coupon_rate.value();
        target.original_face = source.original_face.value();
        target.outstanding_face = source.outstanding_face.value();
        target.settled = source.settled ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_equity_count(const macro_sim_session *session,
                                           size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    *output = session->engine.securities_runtime()->securities.equities().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_equities(const macro_sim_session *session, size_t offset,
                                       macro_sim_m6_equity *output, size_t capacity,
                                       size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and equity output are required");
    }
    const auto &rows = session->engine.securities_runtime()->securities.equities();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.issuer_kind = static_cast<std::uint32_t>(source.issuer_kind);
        target.id = source.id.value();
        target.owner_kind = static_cast<std::uint32_t>(source.issuer.kind());
        target.currency_id = source.currency.value();
        target.issuer_id = source.issuer.value();
        target.issuer_account = source.issuer_account.value();
        target.outstanding_shares = source.outstanding_shares;
        target.price = source.price.value();
        target.last_price = source.last_price.value();
        target.peak_price = source.peak_price.value();
        target.fundamental = source.fundamental.value();
        target.trend = source.trend;
        target.income_signal = source.income_signal;
        target.active = source.active ? 1U : 0U;
        target.resolved = source.resolved ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_firm_statement_count(const macro_sim_session *session,
                                                   size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    const auto &rows = session->engine.securities_runtime()->firms;
    *output = rows.empty() ? 0 : rows.size() - 1;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_firm_statements(const macro_sim_session *session,
                                              size_t offset,
                                              macro_sim_m6_firm_statement *output,
                                              size_t capacity, size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and statement output are required");
    }
    const auto &rows = session->engine.securities_runtime()->firms;
    *written = 0;
    const auto logical_size = rows.empty() ? 0 : rows.size() - 1;
    if (offset >= logical_size) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, logical_size - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index + 1];
        const auto &statement = source.statement;
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.firm_id = source.firm.value();
        target.stratum = static_cast<std::uint32_t>(source.stratum);
        target.defaulted = source.defaulted ? 1U : 0U;
        target.cash = statement.cash;
        target.debt = statement.debt;
        target.interest_arrears = statement.interest_arrears;
        target.capital_units = statement.capital_units;
        target.capital_unit_price = statement.capital_unit_price;
        target.capital_value = statement.capital_value;
        target.output_inventory_units = statement.output_inventory_units;
        target.output_inventory_unit_price = statement.output_inventory_unit_price;
        target.output_inventory_value = statement.output_inventory_value;
        target.inventory_value = statement.inventory_value;
        target.gross_assets = statement.gross_assets;
        target.book_equity = statement.book_equity;
        target.eligible_collateral_value = statement.eligible_collateral_value;
        target.borrowing_base_proxy = statement.borrowing_base_proxy;
        target.borrowing_base_headroom = statement.borrowing_base_headroom;
        target.earnings = statement.earnings;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_genesis(macro_sim_session *session,
                                      const macro_sim_m7_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M7 genesis options are required");
    }
    const auto &financial_options = options->financial;
    if (options->struct_size != sizeof(macro_sim_m7_genesis_options) ||
        financial_options.struct_size != sizeof(macro_sim_m6_genesis_options) ||
        financial_options.matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        !valid_flag(financial_options.stochastic) ||
        !valid_flag(financial_options.bonds) ||
        !valid_flag(financial_options.firm_equity) ||
        !valid_flag(financial_options.margin_credit) ||
        !valid_flag(financial_options.firm_dynamics) ||
        !valid_flag(financial_options.bank_dynamics) ||
        financial_options.reserved != 0 ||
        financial_options.portfolio_review_interval_days > 3'650U) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M7 genesis options are invalid");
    }

    macro_sim::simulation::M7SimulationSpec spec;
    auto &financial = spec.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    real.economy = macro_sim::EconomyId(financial_options.economy_id);
    real.currency = macro_sim::CurrencyId(financial_options.currency_id);
    real.market_protocol = static_cast<macro_sim::algorithms::MatchingProtocol>(
        financial_options.matching_protocol);
    real.stochastic = financial_options.stochastic != 0;
    real.consumption_firms = financial_options.consumption_firms;
    real.capital_firms = financial_options.capital_firms;
    real.seed = financial_options.seed;
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    monetary.rules.bank_count = financial_options.banks;
    monetary.rules.opening_capital_per_bank =
        financial_options.opening_capital_per_bank;
    monetary.initial_policy_rate = financial_options.initial_policy_rate;
    financial.rules.bonds = financial_options.bonds != 0;
    financial.rules.firm_equity = financial_options.firm_equity != 0;
    financial.rules.margin_credit = financial_options.margin_credit != 0;
    financial.rules.firm_dynamics = financial_options.firm_dynamics != 0;
    financial.rules.bank_dynamics = financial_options.bank_dynamics != 0;
    financial.rules.watchlist_size = financial_options.watchlist_size;
    if (financial_options.portfolio_review_interval_days != 0U) {
        financial.rules.portfolio_review_interval_days =
            financial_options.portfolio_review_interval_days;
    }
    spec.population.initial_persons = options->initial_persons;
    spec.population.start_calendar_day = options->start_calendar_day;
    spec.population.target_household_size = options->target_household_size;
    return status(session->engine.initialize_m7(spec));
}

macro_sim_status macro_sim_m7_update_policy(macro_sim_session *session,
                                            const macro_sim_m7_policy *policy) {
    if (session == nullptr || policy == nullptr ||
        policy->struct_size != sizeof(macro_sim_m7_policy) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M7 policy are required");
    }
    macro_sim::simulation::M7PolicyState value;
    value.inheritance_tax_rate = policy->inheritance_tax_rate;
    return status(session->engine.update_m7_policy(value));
}

macro_sim_status macro_sim_m7_policy_defaults(macro_sim_m7_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M7 policy output is required");
    }
    const macro_sim::simulation::M7PolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->inheritance_tax_rate = value.inheritance_tax_rate;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_rules_defaults(macro_sim_m7_rules *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M7 rules output is required");
    }
    const macro_sim::simulation::M7Rules value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->working_age = value.working_age;
    output->retirement_age = value.retirement_age;
    output->maximum_age = value.vital_rates.maximum_age;
#define MACRO_SIM_M7_RULE_FLAG(field) output->field = value.field ? 1U : 0U
    MACRO_SIM_M7_RULE_FLAG(beneficial_ownership);
    MACRO_SIM_M7_RULE_FLAG(estates);
    MACRO_SIM_M7_RULE_FLAG(fertility);
    MACRO_SIM_M7_RULE_FLAG(mortality);
    MACRO_SIM_M7_RULE_FLAG(persistent_labor);
    MACRO_SIM_M7_RULE_FLAG(fractional_hours);
    MACRO_SIM_M7_RULE_FLAG(second_jobs);
    MACRO_SIM_M7_RULE_FLAG(suspensions);
    MACRO_SIM_M7_RULE_FLAG(frictional_search);
    MACRO_SIM_M7_RULE_FLAG(relationship_wages);
    MACRO_SIM_M7_RULE_FLAG(job_ladder);
    MACRO_SIM_M7_RULE_FLAG(person_efficiency);
    MACRO_SIM_M7_RULE_FLAG(participation_margin);
    MACRO_SIM_M7_RULE_FLAG(age_participation);
    MACRO_SIM_M7_RULE_FLAG(family_transfers);
    MACRO_SIM_M7_RULE_FLAG(relationships);
    MACRO_SIM_M7_RULE_FLAG(marriage);
    MACRO_SIM_M7_RULE_FLAG(divorce);
    MACRO_SIM_M7_RULE_FLAG(household_lifecycle);
    MACRO_SIM_M7_RULE_FLAG(leaving_home);
#undef MACRO_SIM_M7_RULE_FLAG
    output->forbid_same_household =
        value.marriage_rules.forbid_same_household ? 1U : 0U;
    output->forbid_close_kin = value.marriage_rules.forbid_close_kin ? 1U : 0U;
    output->suspension_timeout_days = value.suspension_timeout_days;
    output->marriage_interval_days = value.marriage_interval_days;
    output->marriage_minimum_age = value.marriage_rules.minimum_age;
    output->marriage_maximum_age = value.marriage_rules.maximum_age;
    output->marriage_maximum_age_gap = value.marriage_rules.maximum_age_gap;
    output->leave_home_min_age = value.leave_home_min_age;
    output->leave_home_peak_end_age = value.leave_home_peak_end_age;
    output->makeham_a = value.vital_rates.makeham_a;
    output->gompertz_b = value.vital_rates.gompertz_b;
    output->gompertz_theta = value.vital_rates.gompertz_theta;
    output->infant_extra = value.vital_rates.infant_extra;
    output->total_fertility_rate = value.vital_rates.total_fertility_rate;
    output->fertility_peak_age = value.vital_rates.fertility_peak_age;
    output->fertility_width = value.vital_rates.fertility_width;
    output->sex_ratio_at_birth = value.vital_rates.sex_ratio_at_birth;
    output->vital_interval = value.vital_rates.interval;
    output->annual_churn = value.annual_churn;
    output->firing_adjustment = value.firing_adjustment;
    output->layoff_band = value.layoff_band;
    output->target_smoothing = value.target_smoothing;
    output->search_intensity = value.search_intensity;
    output->ladder_search_intensity = value.ladder_search_intensity;
    output->ladder_premium = value.ladder_premium;
    output->efficiency_sigma = value.efficiency_sigma;
    output->genesis_employment_rate = value.genesis_employment_rate;
    output->young_participation_rate = value.young_participation_rate;
    output->prime_participation_rate = value.prime_participation_rate;
    output->older_participation_rate = value.older_participation_rate;
    output->reservation_markup = value.reservation_markup;
    output->welfare_quit_hazard = value.welfare_quit_hazard;
    output->family_transfer_buffer = value.family_transfer_buffer;
    output->annual_leave_rate_peak = value.annual_leave_rate_peak;
    output->annual_leave_rate_late = value.annual_leave_rate_late;
    output->annual_marriage_rate = value.annual_marriage_rate;
    output->annual_divorce_rate = value.annual_divorce_rate;
    output->marriage_preferred_age_gap = value.marriage_rules.preferred_age_gap;
    output->marriage_age_gap_penalty = value.marriage_rules.age_gap_penalty;
    output->marriage_assortativity = value.marriage_rules.assortativity;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_update_rules(macro_sim_session *session,
                                           const macro_sim_m7_rules *rules) {
    if (session == nullptr || rules == nullptr ||
        rules->struct_size != sizeof(macro_sim_m7_rules) ||
        !valid_flag(rules->beneficial_ownership) || !valid_flag(rules->estates) ||
        !valid_flag(rules->fertility) || !valid_flag(rules->mortality) ||
        !valid_flag(rules->persistent_labor) || !valid_flag(rules->fractional_hours) ||
        !valid_flag(rules->second_jobs) || !valid_flag(rules->suspensions) ||
        !valid_flag(rules->frictional_search) ||
        !valid_flag(rules->relationship_wages) || !valid_flag(rules->job_ladder) ||
        !valid_flag(rules->person_efficiency) ||
        !valid_flag(rules->participation_margin) ||
        !valid_flag(rules->age_participation) || !valid_flag(rules->family_transfers) ||
        !valid_flag(rules->relationships) || !valid_flag(rules->marriage) ||
        !valid_flag(rules->divorce) || !valid_flag(rules->household_lifecycle) ||
        !valid_flag(rules->leaving_home) || !valid_flag(rules->forbid_same_household) ||
        !valid_flag(rules->forbid_close_kin)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M7 rules are required");
    }
    macro_sim::simulation::M7Rules value;
    value.working_age = rules->working_age;
    value.retirement_age = rules->retirement_age;
    value.vital_rates.maximum_age = rules->maximum_age;
#define MACRO_SIM_COPY_M7_FLAG(field) value.field = rules->field != 0
    MACRO_SIM_COPY_M7_FLAG(beneficial_ownership);
    MACRO_SIM_COPY_M7_FLAG(estates);
    MACRO_SIM_COPY_M7_FLAG(fertility);
    MACRO_SIM_COPY_M7_FLAG(mortality);
    MACRO_SIM_COPY_M7_FLAG(persistent_labor);
    MACRO_SIM_COPY_M7_FLAG(fractional_hours);
    MACRO_SIM_COPY_M7_FLAG(second_jobs);
    MACRO_SIM_COPY_M7_FLAG(suspensions);
    MACRO_SIM_COPY_M7_FLAG(frictional_search);
    MACRO_SIM_COPY_M7_FLAG(relationship_wages);
    MACRO_SIM_COPY_M7_FLAG(job_ladder);
    MACRO_SIM_COPY_M7_FLAG(person_efficiency);
    MACRO_SIM_COPY_M7_FLAG(participation_margin);
    MACRO_SIM_COPY_M7_FLAG(age_participation);
    MACRO_SIM_COPY_M7_FLAG(family_transfers);
    MACRO_SIM_COPY_M7_FLAG(relationships);
    MACRO_SIM_COPY_M7_FLAG(marriage);
    MACRO_SIM_COPY_M7_FLAG(divorce);
    MACRO_SIM_COPY_M7_FLAG(household_lifecycle);
    MACRO_SIM_COPY_M7_FLAG(leaving_home);
#undef MACRO_SIM_COPY_M7_FLAG
    value.marriage_rules.forbid_same_household = rules->forbid_same_household != 0;
    value.marriage_rules.forbid_close_kin = rules->forbid_close_kin != 0;
    value.suspension_timeout_days = rules->suspension_timeout_days;
    value.marriage_interval_days = rules->marriage_interval_days;
    value.marriage_rules.minimum_age = rules->marriage_minimum_age;
    value.marriage_rules.maximum_age = rules->marriage_maximum_age;
    value.marriage_rules.maximum_age_gap = rules->marriage_maximum_age_gap;
    value.leave_home_min_age = rules->leave_home_min_age;
    value.leave_home_peak_end_age = rules->leave_home_peak_end_age;
    value.vital_rates.makeham_a = rules->makeham_a;
    value.vital_rates.gompertz_b = rules->gompertz_b;
    value.vital_rates.gompertz_theta = rules->gompertz_theta;
    value.vital_rates.infant_extra = rules->infant_extra;
    value.vital_rates.total_fertility_rate = rules->total_fertility_rate;
    value.vital_rates.fertility_peak_age = rules->fertility_peak_age;
    value.vital_rates.fertility_width = rules->fertility_width;
    value.vital_rates.sex_ratio_at_birth = rules->sex_ratio_at_birth;
    value.vital_rates.interval = rules->vital_interval;
    value.annual_churn = rules->annual_churn;
    value.firing_adjustment = rules->firing_adjustment;
    value.layoff_band = rules->layoff_band;
    value.target_smoothing = rules->target_smoothing;
    value.search_intensity = rules->search_intensity;
    value.ladder_search_intensity = rules->ladder_search_intensity;
    value.ladder_premium = rules->ladder_premium;
    value.efficiency_sigma = rules->efficiency_sigma;
    value.genesis_employment_rate = rules->genesis_employment_rate;
    value.young_participation_rate = rules->young_participation_rate;
    value.prime_participation_rate = rules->prime_participation_rate;
    value.older_participation_rate = rules->older_participation_rate;
    value.reservation_markup = rules->reservation_markup;
    value.welfare_quit_hazard = rules->welfare_quit_hazard;
    value.family_transfer_buffer = rules->family_transfer_buffer;
    value.annual_leave_rate_peak = rules->annual_leave_rate_peak;
    value.annual_leave_rate_late = rules->annual_leave_rate_late;
    value.annual_marriage_rate = rules->annual_marriage_rate;
    value.annual_divorce_rate = rules->annual_divorce_rate;
    value.marriage_rules.preferred_age_gap = rules->marriage_preferred_age_gap;
    value.marriage_rules.age_gap_penalty = rules->marriage_age_gap_penalty;
    value.marriage_rules.assortativity = rules->marriage_assortativity;
    return status(session->engine.update_m7_rules(value));
}

macro_sim_status macro_sim_m7_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m7_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m7_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m7_metrics) ||
        output->metrics.economy.struct_size != sizeof(macro_sim_m6_metrics) ||
        output->metrics.economy.economy.struct_size != sizeof(macro_sim_m5_metrics) ||
        output->metrics.economy.economy.economy.struct_size !=
            sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M7 result are required");
    }
    const auto result = session->engine.advance_m7_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m7_metrics(output->metrics, value.metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m7_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m7_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m7_person_count(const macro_sim_session *session,
                                           size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and output are required");
    }
    *output = session->engine.population_runtime()->persons.total_count();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_persons(const macro_sim_session *session, size_t offset,
                                      macro_sim_m7_person *output, size_t capacity,
                                      size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and person output are required");
    }
    const auto &rows = session->engine.population_runtime()->persons.records();
    const auto logical_size = rows.empty() ? 0 : rows.size() - 1;
    *written = 0;
    if (offset >= logical_size) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, logical_size - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index + 1];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.sex = static_cast<std::uint32_t>(source.sex);
        target.id = source.id.value();
        target.birth_day = source.birth_day;
        target.death_day = source.death_day;
        target.mother_id = source.mother.value();
        target.father_id = source.father.value();
        target.partner_id = source.partner.value();
        target.guardian_id = source.guardian.value();
        target.household_id = source.household.value();
        target.marriage_start_day = source.marriage_start_day;
        target.last_divorce_day = source.last_divorce_day;
        target.last_widowed_day = source.last_widowed_day;
        target.marriage_count = source.marriage_count;
        target.efficiency = source.efficiency;
        target.participating = source.participating ? 1U : 0U;
        target.searching = source.searching ? 1U : 0U;
        target.alive = source.alive ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_membership_count(const macro_sim_session *session,
                                               size_t *output) {
    return macro_sim_m7_person_count(session, output);
}

macro_sim_status macro_sim_m7_memberships(const macro_sim_session *session,
                                          size_t offset,
                                          macro_sim_m7_membership *output,
                                          size_t capacity, size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and membership output are required");
    }
    const auto *runtime = session->engine.population_runtime();
    const auto &rows = runtime->persons.records();
    const auto logical_size = rows.empty() ? 0 : rows.size() - 1;
    *written = 0;
    if (offset >= logical_size) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, logical_size - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &person = rows[offset + index + 1];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.person_id = person.id.value();
        target.household_id = runtime->membership.household_of(person.id).value();
        target.alive = person.alive ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_job_count(const macro_sim_session *session,
                                        size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and output are required");
    }
    const auto &rows = session->engine.population_runtime()->employment.records();
    *output = rows.empty() ? 0 : rows.size() - 1;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_jobs(const macro_sim_session *session, size_t offset,
                                   macro_sim_m7_job *output, size_t capacity,
                                   size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and job output are required");
    }
    const auto &rows = session->engine.population_runtime()->employment.records();
    const auto logical_size = rows.empty() ? 0 : rows.size() - 1;
    *written = 0;
    if (offset >= logical_size) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, logical_size - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index + 1];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.id = source.id.value();
        target.person_id = source.person.value();
        target.firm_id = source.firm.value();
        target.hire_day = source.hire_day;
        target.separation_day = source.separation_day;
        target.suspension_day = source.suspension_day;
        target.separation_kind = static_cast<std::uint32_t>(source.separation_kind);
        target.wage = source.wage;
        target.hours = source.hours;
        target.secondary = source.secondary ? 1U : 0U;
        target.suspended = source.suspended ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_union_count(const macro_sim_session *session,
                                          size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and output are required");
    }
    *output = session->engine.population_runtime()->relationships.unions().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_unions(const macro_sim_session *session, size_t offset,
                                     macro_sim_m7_union *output, size_t capacity,
                                     size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and union output are required");
    }
    const auto &rows = session->engine.population_runtime()->relationships.unions();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.event_id = source.event.value();
        target.first_id = source.first.value();
        target.second_id = source.second.value();
        target.first_origin_household_id = source.first_origin_household.value();
        target.second_origin_household_id = source.second_origin_household.value();
        target.start_day = source.start_day;
        target.end_day = source.end_day;
        target.end_kind = static_cast<std::uint32_t>(source.end_kind);
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_estate_count(const macro_sim_session *session,
                                           size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and output are required");
    }
    *output = session->engine.population_runtime()->estates.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m7_estates(const macro_sim_session *session, size_t offset,
                                      macro_sim_m7_estate *output, size_t capacity,
                                      size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.population_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M7 session and estate output are required");
    }
    const auto &rows = session->engine.population_runtime()->estates;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.settled = source.settled ? 1U : 0U;
        target.event_id = source.event.value();
        target.deceased_id = source.deceased.value();
        target.heir_id = source.heir.value();
        target.household_id = source.household.value();
        target.destination_household_id = source.destination_household.value();
        target.opened_day = source.opened_day;
        target.settled_day = source.settled_day;
        target.transferred_lots = source.transferred_lots;
        target.gross_share = source.gross_share;
        target.tax_share = source.tax_share;
        target.gross_value = source.gross_value;
        target.liabilities = source.liabilities;
        target.tax_paid = source.tax_paid;
        target.public_residual = source.public_residual ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_defaults(macro_sim_m8_genesis_options *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M8 genesis output is required");
    }
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    auto &domestic = output->domestic_economy;
    domestic.struct_size = sizeof(domestic);
    domestic.start_calendar_day = 0;
    domestic.initial_persons = 100;
    domestic.target_household_size = 2.5;
    auto &financial = domestic.financial;
    financial.struct_size = sizeof(financial);
    financial.matching_protocol = MACRO_SIM_M4_MATCH_PRICE_SORTED;
    financial.economy_id = 1;
    financial.currency_id = 1;
    financial.bonds = 1;
    financial.firm_equity = 1;
    financial.margin_credit = 1;
    financial.consumption_firms = 6;
    financial.capital_firms = 2;
    financial.banks = 2;
    financial.seed = 8;
    financial.watchlist_size = 3;
    financial.portfolio_review_interval_days = 30;
    financial.opening_capital_per_bank = 1'000.0;
    financial.initial_policy_rate = 0.002;
    fill_energy_policy(output->energy_policy, {});
    fill_energy_rules(output->energy_rules, {});
    fill_energy_input(output->energy_input, {});
    fill_housing_policy(output->housing_policy, {});
    fill_housing_rules(output->housing_rules, {});
    fill_housing_input(output->housing_input, {});
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_genesis(macro_sim_session *session,
                                      const macro_sim_m8_genesis_options *options) {
    if (session == nullptr || options == nullptr ||
        !valid_m8_genesis_options(*options)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M8 genesis options are required");
    }
    return status(session->engine.initialize_m8(make_m8_spec(*options)));
}

macro_sim_status
macro_sim_m8_update_energy_policy(macro_sim_session *session,
                                  const macro_sim_m8_energy_policy *policy) {
    if (session == nullptr || policy == nullptr ||
        policy->struct_size != sizeof(*policy) ||
        !valid_flag(policy->price_cap_compensation) ||
        !valid_flag(policy->state_owned_price_at_cost) ||
        policy->rationing > MACRO_SIM_M8_ENERGY_RATION_INDUSTRY_FIRST) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M8 energy policy are required");
    }
    return status(
        session->engine.update_m8_energy_policy(energy_policy_from_c(*policy)));
}

macro_sim_status
macro_sim_m8_update_housing_policy(macro_sim_session *session,
                                   const macro_sim_m8_housing_policy *policy) {
    if (session == nullptr || policy == nullptr ||
        policy->struct_size != sizeof(*policy) ||
        !valid_flag(policy->mortgage_underwriting) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M8 housing policy are required");
    }
    return status(
        session->engine.update_m8_housing_policy(housing_policy_from_c(*policy)));
}

macro_sim_status
macro_sim_m8_update_energy_input(macro_sim_session *session,
                                 const macro_sim_m8_energy_input *input) {
    if (session == nullptr || input == nullptr ||
        input->struct_size != sizeof(*input) || input->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M8 energy input are required");
    }
    return status(session->engine.update_m8_energy_input(energy_input_from_c(*input)));
}

macro_sim_status
macro_sim_m8_update_housing_input(macro_sim_session *session,
                                  const macro_sim_m8_housing_input *input) {
    if (session == nullptr || input == nullptr ||
        input->struct_size != sizeof(*input) || input->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M8 housing input are required");
    }
    return status(
        session->engine.update_m8_housing_input(housing_input_from_c(*input)));
}

macro_sim_status macro_sim_m8_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m8_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(*output) ||
        output->metrics.struct_size != sizeof(output->metrics) ||
        output->metrics.economy.struct_size != sizeof(output->metrics.economy) ||
        output->metrics.economy.economy.struct_size !=
            sizeof(output->metrics.economy.economy) ||
        output->metrics.economy.economy.economy.struct_size !=
            sizeof(output->metrics.economy.economy.economy) ||
        output->metrics.economy.economy.economy.economy.struct_size !=
            sizeof(output->metrics.economy.economy.economy.economy) ||
        output->metrics.energy.struct_size != sizeof(output->metrics.energy) ||
        output->metrics.housing.struct_size != sizeof(output->metrics.housing)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M8 result are required");
    }
    const auto result = session->engine.advance_m8_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m8_metrics(output->metrics, value.metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m8_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m8_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m8_dwelling_count(const macro_sim_session *session,
                                             size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->properties.minted_count();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_dwellings(const macro_sim_session *session, size_t offset,
                                        macro_sim_m8_dwelling *output, size_t capacity,
                                        size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and dwelling output are required");
    }
    const auto &rows = session->engine.housing_runtime()->properties.records();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.id = source.id.value();
        target.owner_kind = static_cast<std::uint32_t>(source.owner.kind());
        target.location = source.location;
        target.owner_id = source.owner.value();
        target.occupant_household_id = source.occupant.value();
        target.collateral_loan_id = source.collateral.value();
        target.minted_tick = source.minted_tick.value();
        target.last_title_tick = source.last_title_tick.value();
        target.age_days = source.age_days;
        target.floor_area = source.floor_area;
        target.quality = source.quality;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_listing_count(const macro_sim_session *session,
                                            size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->housing_listings.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_listings(const macro_sim_session *session, size_t offset,
                                       macro_sim_m8_listing *output, size_t capacity,
                                       size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and listing output are required");
    }
    const auto &rows = session->engine.housing_runtime()->housing_listings;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.dwelling_id = source.dwelling.value();
        target.seller_kind = static_cast<std::uint32_t>(source.seller.kind());
        target.forced = source.forced ? 1U : 0U;
        target.seller_id = source.seller.value();
        target.listed_tick = source.listed_tick.value();
        target.asking_price = source.asking_price;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_mortgage_count(const macro_sim_session *session,
                                             size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->mortgages.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_mortgages(const macro_sim_session *session, size_t offset,
                                        macro_sim_m8_mortgage *output, size_t capacity,
                                        size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and mortgage output are required");
    }
    const auto &rows = session->engine.housing_runtime()->mortgages;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.loan_id = source.loan.value();
        target.borrower_household_id = source.borrower.value();
        target.lender_bank_id = source.lender.value();
        target.collateral_dwelling_id = source.collateral.value();
        target.originated_tick = source.originated_tick.value();
        target.foreclosed = source.foreclosed ? 1U : 0U;
        target.original_principal = source.original_principal;
        target.purchase_price = source.purchase_price;
        target.qualifying_income = source.qualifying_income;
        target.stressed_payment = source.stressed_payment;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_tenancy_count(const macro_sim_session *session,
                                            size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->tenancies.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_tenancies(const macro_sim_session *session, size_t offset,
                                        macro_sim_m8_tenancy *output, size_t capacity,
                                        size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and tenancy output are required");
    }
    const auto &rows = session->engine.housing_runtime()->tenancies;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.id = source.id.value();
        target.dwelling_id = source.dwelling.value();
        target.landlord_household_id = source.landlord.value();
        target.tenant_household_id = source.tenant.value();
        target.started_tick = source.started_tick.value();
        target.ended_tick = source.ended_tick.value();
        target.missed_days = source.missed_days;
        target.daily_rent = source.daily_rent;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_builder_count(const macro_sim_session *session,
                                            size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->builders.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_builders(const macro_sim_session *session, size_t offset,
                                       macro_sim_m8_builder *output, size_t capacity,
                                       size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and builder output are required");
    }
    const auto &rows = session->engine.housing_runtime()->builders;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.firm_id = source.firm.value();
        target.dwellings_minted = source.dwellings_minted;
        target.work_in_progress = source.work_in_progress;
        target.finished_inventory = source.finished_inventory;
        target.demand_expected = source.demand_expected;
        target.produced_today = source.produced_today;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_energy_producer_count(const macro_sim_session *session,
                                                    size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and output are required");
    }
    *output = session->engine.housing_runtime()->energy_producers.size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m8_energy_producers(const macro_sim_session *session,
                                               size_t offset,
                                               macro_sim_m8_energy_producer *output,
                                               size_t capacity, size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.housing_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M8 session and energy producer output are required");
    }
    const auto &rows = session->engine.housing_runtime()->energy_producers;
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.state_owned = source.state_owned ? 1U : 0U;
        target.firm_id = source.firm.value();
        target.capacity_per_capital = source.capacity_per_capital;
        target.inventory = source.inventory;
        target.inventory_cost = source.inventory_cost;
        target.produced = source.produced;
        target.sales = source.sales;
        target.revenue = source.revenue;
        target.demand_expected = source.demand_expected;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_rules_defaults(macro_sim_m9_world_rules *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M9 World rules output is required");
    }
    const macro_sim::simulation::WorldRules value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->trade = value.trade ? 1U : 0U;
    output->capital = value.capital ? 1U : 0U;
    output->migration = value.migration ? 1U : 0U;
    output->fx_loss_mutualization = value.fx_loss_mutualization ? 1U : 0U;
    output->dense_edge_threshold = value.dense_edge_threshold;
    output->fx_adjustment = value.fx_adjustment;
    output->fx_friction = value.fx_friction;
    output->fx_spread = value.fx_spread;
    output->fx_trade_cap = value.fx_trade_cap;
    output->capital_mobility = value.capital_mobility;
    output->capital_adjustment = value.capital_adjustment;
    output->periods_per_year = value.periods_per_year;
    output->migration_rate = value.migration_rate;
    output->migration_max_share = value.migration_max_share;
    output->remittance_share = value.remittance_share;
    output->wage_smoothing = value.wage_smoothing;
    output->initial_peg_reserves = value.initial_peg_reserves;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status
macro_sim_m9_external_policy_defaults(macro_sim_m9_external_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 external policy output is required");
    }
    const macro_sim::simulation::ExternalPolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->fx_regime = MACRO_SIM_M9_FX_FLOAT;
    output->tariff = value.tariff;
    output->export_subsidy = value.export_subsidy;
    output->capital_control = value.capital_control;
    output->external_interest_settlement_fraction =
        value.external_interest_settlement_fraction;
    output->remittance_tax = value.remittance_tax;
    output->outward_remittance_tax = value.outward_remittance_tax;
    output->guest_worker_return = value.guest_worker_return;
    output->peg_reserve_scale = value.peg_reserve_scale;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_create(const macro_sim_m9_genesis_options *options,
                                           macro_sim_m9_world **output) {
    if (options == nullptr || output == nullptr ||
        options->struct_size != sizeof(*options) || options->reserved != 0U ||
        options->economy_count == 0U || options->economies == nullptr ||
        !valid_m9_world_rules(options->rules) ||
        (options->external_policy_count != 0U &&
         (options->external_policy_count != options->economy_count ||
          options->external_policies == nullptr)) ||
        (options->shock_count != 0U && options->shocks == nullptr)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "valid M9 genesis options and output are required");
    }
    *output = nullptr;
    try {
        macro_sim::simulation::M9WorldSpec spec;
        spec.rules = world_rules_from_c(options->rules);
        spec.economies.reserve(options->economy_count);
        for (std::size_t index = 0; index < options->economy_count; ++index) {
            if (!valid_m8_genesis_options(options->economies[index])) {
                return status(MACRO_SIM_INVALID_ARGUMENT,
                              "invalid M8 economy in M9 genesis");
            }
            spec.economies.push_back(make_m8_spec(options->economies[index]));
        }
        if (options->external_policy_count != 0U) {
            spec.external_policies.reserve(options->external_policy_count);
            for (std::size_t index = 0; index < options->external_policy_count;
                 ++index) {
                if (!valid_m9_external_policy(options->external_policies[index])) {
                    return status(MACRO_SIM_INVALID_ARGUMENT,
                                  "invalid external policy in M9 genesis");
                }
                spec.external_policies.push_back(
                    external_policy_from_c(options->external_policies[index]));
            }
        }
        spec.shocks.reserve(options->shock_count);
        for (std::size_t index = 0; index < options->shock_count; ++index) {
            if (!valid_m9_shock(options->shocks[index])) {
                return status(MACRO_SIM_INVALID_ARGUMENT,
                              "invalid shock in M9 genesis");
            }
            spec.shocks.push_back(shock_from_c(options->shocks[index]));
        }
        auto created = macro_sim::simulation::M9World::create(spec);
        if (!created.ok()) {
            return status(created.status());
        }
        auto *handle =
            new (std::nothrow) macro_sim_m9_world(std::move(*created.get_if()));
        if (handle == nullptr) {
            return status(MACRO_SIM_ALLOCATION_FAILURE, "M9 World allocation failed");
        }
        *output = handle;
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "M9 World allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "M9 World conversion failed");
    }
}

macro_sim_status macro_sim_m9_world_destroy(macro_sim_m9_world **world) {
    if (world == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World handle pointer is required");
    }
    delete *world;
    *world = nullptr;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_tick(const macro_sim_m9_world *world,
                                         uint64_t *output) {
    if (world == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and tick output are required");
    }
    *output = world->engine.tick().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_advance(macro_sim_m9_world *world,
                                            uint64_t tick_count,
                                            macro_sim_m9_advance_result *output) {
    if (world == nullptr || output == nullptr ||
        output->struct_size != sizeof(*output)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and initialized result are required");
    }
    const auto result = world->engine.advance(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    output->reserved = 0U;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->digest = value.digest;
    output->trade_routes = value.metrics.trade_routes;
    output->migration_routes = value.metrics.migration_routes;
    output->shock_events = value.metrics.shock_events;
    output->dealer_flow = value.metrics.dealer_flow;
    output->dealer_spread_revenue = value.metrics.dealer_spread_revenue;
    output->dealer_valuation = value.metrics.dealer_valuation;
    output->world_nfa = value.metrics.world_nfa;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_update_external_policies(
    macro_sim_m9_world *world, const macro_sim_m9_external_policy *policies,
    size_t policy_count) {
    if (world == nullptr || policies == nullptr ||
        policy_count != world->engine.economy_count()) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "complete M9 external policy vector is required");
    }
    try {
        std::vector<macro_sim::simulation::ExternalPolicyState> values;
        values.reserve(policy_count);
        for (std::size_t index = 0; index < policy_count; ++index) {
            if (!valid_m9_external_policy(policies[index])) {
                return status(MACRO_SIM_INVALID_ARGUMENT, "invalid M9 external policy");
            }
            values.push_back(external_policy_from_c(policies[index]));
        }
        return status(world->engine.update_external_policies(values));
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "M9 policy allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "M9 policy conversion failed");
    }
}

macro_sim_status macro_sim_m9_world_schedule_shock(macro_sim_m9_world *world,
                                                   const macro_sim_m9_shock *shock) {
    if (world == nullptr || shock == nullptr || !valid_m9_shock(*shock)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "valid M9 World and shock are required");
    }
    return status(world->engine.schedule_shock(shock_from_c(*shock)));
}

macro_sim_status macro_sim_m9_world_shock_event_count(const macro_sim_m9_world *world,
                                                      size_t *output) {
    if (world == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and event-count output are required");
    }
    *output = world->engine.shock_events().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_shock_events(const macro_sim_m9_world *world,
                                                 size_t offset,
                                                 macro_sim_m9_shock_event *output,
                                                 size_t capacity, size_t *written) {
    if (world == nullptr || written == nullptr ||
        (capacity != 0U && output == nullptr)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and event output are required");
    }
    *written = 0U;
    const auto &events = world->engine.shock_events();
    if (offset >= events.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, events.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = events[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.type = static_cast<std::uint32_t>(source.type);
        target.sequence = source.sequence;
        target.tick = source.tick.value();
        target.shock_id = source.shock_id;
        target.intensity = source.intensity;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_rates(const macro_sim_m9_world *world,
                                          size_t offset, double *output,
                                          size_t capacity, size_t *written) {
    if (world == nullptr || written == nullptr ||
        (capacity != 0U && output == nullptr)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and rate output are required");
    }
    *written = 0U;
    const auto count = world->engine.economy_count();
    if (offset >= count) {
        return status(MACRO_SIM_OK, "");
    }
    const auto rows = std::min(capacity, count - offset);
    for (std::size_t index = 0; index < rows; ++index) {
        output[index] = world->engine.rates().rate(
            macro_sim::EconomyId(static_cast<std::uint64_t>(offset + index)));
    }
    *written = rows;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status
macro_sim_m9_world_country_metrics(const macro_sim_m9_world *world, size_t offset,
                                   macro_sim_m9_country_metrics *output,
                                   size_t capacity, size_t *written) {
    if (world == nullptr || written == nullptr ||
        (capacity != 0U && output == nullptr)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and metrics output are required");
    }
    *written = 0U;
    const auto &metrics = world->engine.last_metrics().external;
    if (offset >= metrics.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, metrics.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = metrics[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.economy_id = offset + index;
        target.active_shocks = source.active_shocks;
#define MACRO_SIM_FILL_M9_COUNTRY(field) target.field = source.field
        MACRO_SIM_FILL_M9_COUNTRY(exchange_rate);
        MACRO_SIM_FILL_M9_COUNTRY(imports_value);
        MACRO_SIM_FILL_M9_COUNTRY(imports_volume);
        MACRO_SIM_FILL_M9_COUNTRY(exports_value);
        MACRO_SIM_FILL_M9_COUNTRY(exports_volume);
        MACRO_SIM_FILL_M9_COUNTRY(iceberg_loss);
        MACRO_SIM_FILL_M9_COUNTRY(tariff_revenue);
        MACRO_SIM_FILL_M9_COUNTRY(export_subsidy_cost);
        MACRO_SIM_FILL_M9_COUNTRY(current_account);
        MACRO_SIM_FILL_M9_COUNTRY(capital_flow);
        MACRO_SIM_FILL_M9_COUNTRY(net_foreign_assets);
        MACRO_SIM_FILL_M9_COUNTRY(factor_income_accrued);
        MACRO_SIM_FILL_M9_COUNTRY(factor_income_cash);
        MACRO_SIM_FILL_M9_COUNTRY(factor_income_arrears);
        MACRO_SIM_FILL_M9_COUNTRY(peg_reserves);
        MACRO_SIM_FILL_M9_COUNTRY(migrant_stock_abroad);
        MACRO_SIM_FILL_M9_COUNTRY(migrant_stock_hosted);
        MACRO_SIM_FILL_M9_COUNTRY(remittances_received);
        MACRO_SIM_FILL_M9_COUNTRY(remittances_sent);
        MACRO_SIM_FILL_M9_COUNTRY(remittance_tax_revenue);
        MACRO_SIM_FILL_M9_COUNTRY(fx_mutualization_paid);
        MACRO_SIM_FILL_M9_COUNTRY(capital_destroyed);
#undef MACRO_SIM_FILL_M9_COUNTRY
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_checkpoint_save(const macro_sim_m9_world *world,
                                                    macro_sim_owned_buffer *output) {
    if (world == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and checkpoint output are required");
    }
    output->data = nullptr;
    output->size = 0U;
    const auto checkpoint = world->engine.checkpoint();
    if (!checkpoint.ok()) {
        return status(checkpoint.status());
    }
    const auto size = checkpoint.get_if()->size();
    auto *bytes = new (std::nothrow) std::uint8_t[size];
    if (bytes == nullptr && size != 0U) {
        return status(MACRO_SIM_ALLOCATION_FAILURE,
                      "M9 checkpoint output allocation failed");
    }
    std::memcpy(bytes, checkpoint.get_if()->data(), size);
    output->data = bytes;
    output->size = size;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m9_world_checkpoint_load(macro_sim_m9_world *world,
                                                    const uint8_t *checkpoint,
                                                    size_t checkpoint_size) {
    if (world == nullptr || (checkpoint_size != 0U && checkpoint == nullptr)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "M9 World and checkpoint are required");
    }
    const auto restored = macro_sim::simulation::M9World::restore(
        std::span<const std::uint8_t>(checkpoint, checkpoint_size));
    if (!restored.ok()) {
        return status(restored.status());
    }
    world->engine = std::move(*restored.get_if());
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_owned_buffer_release(macro_sim_owned_buffer *buffer) {
    if (buffer == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "buffer is required");
    }
    delete[] buffer->data;
    buffer->data = nullptr;
    buffer->size = 0;
    return status(MACRO_SIM_OK, "");
}
