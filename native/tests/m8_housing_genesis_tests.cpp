#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "macro_sim/simulation/m8.hpp"

namespace {

using macro_sim::Tick;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec housing_spec() {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &real = population.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 3;
    real.capital_firms = 1;
    real.seed = 8100;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_household_money = 40.0;
    real.rules.initial_firm_money = 20.0;
    real.rules.initial_consumption_inventory = 5.0;
    real.rules.initial_capital_inventory = 5.0;
    real.rules.initial_wage = 2.0;
    auto &monetary = population.financial_economy.monetary_economy;
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 50.0;
    population.population.initial_persons = 40;
    population.population.target_household_size = 2.0;
    population.population.start_calendar_day = 18'000;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.enabled = false;
    value.housing_rules.enabled = true;
    value.housing_rules.house_price_income_years = 4.0;
    value.housing_rules.initial_dwellings_per_household = 1.0;
    value.housing_rules.initial_homeownership_share = 1.0;
    value.housing_rules.initial_floor_area = 75.0;
    value.housing_rules.location_count = 4;
    return value;
}

struct Harness final {
    macro_sim::core::RootState root;
    M4Runtime real_runtime;
    M4TickScratch real_scratch;
    M5Runtime monetary_runtime;
    M5TickScratch monetary_scratch;
    M6Runtime financial_runtime;
    M6TickScratch financial_scratch;
    M7Runtime population_runtime;
    M7TickScratch population_scratch;
    M8Runtime runtime;
    M8TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build(M8SimulationSpec value = housing_spec()) {
    auto initialized = build_m8_genesis(value);
    if (!initialized.ok()) {
        std::cerr << "housing genesis failed: " << initialized.status().message()
                  << "\n";
    }
    assert(initialized.ok());
    auto state = std::move(*initialized.get_if());
    Harness result{
        std::move(state.root),
        std::move(state.real_economy_runtime),
        {},
        std::move(state.monetary_runtime),
        {},
        std::move(state.financial_runtime),
        {},
        std::move(state.population_runtime),
        {},
        std::move(state.runtime),
        {},
        Tick{},
    };
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(result.root, result.financial_runtime);
    result.population_scratch.reserve(result.population_runtime);
    result.scratch.reserve(result.root, result.runtime);
    return result;
}

[[nodiscard]] macro_sim::Result<M8AdvanceResult> advance(Harness &harness,
                                                         std::uint64_t count) {
    return advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                            harness.monetary_runtime, harness.monetary_scratch,
                            harness.financial_runtime, harness.financial_scratch,
                            harness.population_runtime, harness.population_scratch,
                            harness.runtime, harness.scratch, harness.tick, count);
}

void test_genesis_mints_real_assets_without_money() {
    auto enabled = build();
    auto disabled_spec = housing_spec();
    disabled_spec.housing_rules.enabled = false;
    auto disabled = build(disabled_spec);

    const auto households = enabled.root.households.alive_count();
    assert(enabled.runtime.properties.active_count() == households);
    assert(enabled.runtime.properties.minted_count() == households);
    assert(enabled.runtime.genesis_dwelling_count == households);
    assert(enabled.root.genesis_money == disabled.root.genesis_money);
    assert(enabled.runtime.house_price == 4.0 * 365.0 * 2.0);
    assert(enabled.runtime.properties.validate().ok());

    enabled.root.households.for_each_alive(
        [&enabled](macro_sim::HouseholdId household,
                   const macro_sim::core::HouseholdComponent &) {
            const auto owned = enabled.runtime.properties.dwellings_for_owner(
                macro_sim::core::OwnerId::household(household));
            assert(owned.size() == 1);
            const auto *dwelling = enabled.runtime.properties.get(owned.front());
            assert(dwelling != nullptr);
            assert(dwelling->occupant == household);
            assert(dwelling->floor_area == 75.0);
            assert(dwelling->location < 4);
        });
    assert(validate_m8_state(enabled.root, enabled.real_runtime,
                             enabled.monetary_runtime, enabled.financial_runtime,
                             enabled.population_runtime, enabled.runtime, enabled.tick)
               .ok());
}

void test_partial_homeownership_seeds_valid_tenancies() {
    auto value = housing_spec();
    value.housing_rules.resale_market = true;
    value.housing_rules.rentals = true;
    value.housing_rules.initial_homeownership_share = 0.5;
    auto harness = build(value);
    const auto households = harness.root.households.alive_count();
    const auto owners =
        static_cast<std::uint64_t>(std::llround(0.5 * static_cast<double>(households)));
    assert(harness.runtime.tenancies.size() == households - owners);
    assert(std::abs(harness.runtime.last_metrics.housing.homeownership_share -
                    static_cast<double>(owners) / static_cast<double>(households)) <
           1.0e-12);
    for (const auto &tenancy : harness.runtime.tenancies) {
        assert(tenancy.active);
        const auto *dwelling = harness.runtime.properties.get(tenancy.dwelling);
        assert(dwelling != nullptr);
        assert(dwelling->occupant == tenancy.tenant);
        assert(dwelling->owner ==
               macro_sim::core::OwnerId::household(tenancy.landlord));
    }
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_disabled_housing_has_no_state() {
    auto value = housing_spec();
    value.housing_rules.enabled = false;
    auto harness = build(value);
    assert(harness.runtime.properties.active_count() == 0);
    assert(harness.runtime.tenancies.empty());
    const auto result = advance(harness, 2);
    assert(result.ok());
    assert(harness.runtime.properties.active_count() == 0);
}

void test_quiet_days_preserve_title_exactly() {
    auto harness = build();
    const auto registry = harness.runtime.properties;
    const auto result = advance(harness, 10);
    assert(result.ok());
    assert(harness.tick == Tick(10));
    assert(harness.runtime.properties == registry);
    assert(result.get_if()->metrics.housing.house_price == harness.runtime.house_price);
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_capability_dependencies_are_rejected() {
    auto value = housing_spec();
    value.housing_rules.mortgages = true;
    assert(!validate_m8_spec(value).ok());

    value = housing_spec();
    value.housing_rules.resale_market = true;
    value.housing_rules.construction = true;
    value.domestic_economy.financial_economy.monetary_economy.real_economy
        .requested_capabilities = 0;
    assert(!validate_m8_spec(value).ok());

    value = housing_spec();
    value.housing_input.land_cost_multiplier = -1.0;
    assert(!validate_m8_spec(value).ok());

    value = housing_spec();
    value.housing_policy.mortgage_ltv_cap = 1.1;
    assert(!validate_m8_spec(value).ok());
}

void test_builders_create_permitted_real_stock() {
    auto value = housing_spec();
    value.housing_rules.resale_market = true;
    value.housing_rules.construction = true;
    value.housing_rules.builder_count = 1;
    value.housing_rules.builder_productivity = 1.0;
    value.housing_rules.builder_demand_seed = 5.0;
    value.housing_rules.initial_builder_cash_buffer = 1'000.0;
    value.housing_rules.market_interval_days = 30;
    value.housing_policy.land_fee_share = 0.0;
    value.housing_policy.annual_housing_permits = 2;
    auto harness = build(value);
    assert(harness.runtime.builders.size() == 1);
    const auto builder = harness.runtime.builders.front().firm;
    const auto *firm = harness.root.firms.get(builder);
    assert(firm != nullptr);
    assert(firm->sector == macro_sim::core::FirmSector::construction);
    const auto stock_before = harness.runtime.properties.active_count();
    const auto money_before = harness.root.genesis_money;
    const auto result = advance(harness, 200);
    if (!result.ok()) {
        std::cerr << "builder advance failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    if (harness.runtime.properties.active_count() != stock_before + 2) {
        std::cerr << "builder stock=" << harness.runtime.properties.active_count()
                  << " before=" << stock_before
                  << " wip=" << harness.runtime.builders.front().work_in_progress
                  << " minted=" << harness.runtime.builders.front().dwellings_minted
                  << " permits=" << harness.runtime.permits_used << "\n";
    }
    assert(harness.runtime.properties.active_count() == stock_before + 2);
    assert(harness.runtime.permits_used == 2);
    assert(harness.runtime.builders.front().dwellings_minted == 2);
    assert(harness.runtime.properties
               .dwellings_for_owner(macro_sim::core::OwnerId::firm(builder))
               .size() == 2);
    assert(harness.root.genesis_money == money_before);
}

void test_builder_energy_input_is_canonical() {
    auto value = housing_spec();
    value.energy_rules.enabled = true;
    value.energy_rules.producer_count = 1;
    value.energy_rules.initial_producer_cash = 100.0;
    value.housing_rules.resale_market = true;
    value.housing_rules.construction = true;
    value.housing_rules.builder_count = 1;
    value.housing_rules.initial_builder_cash_buffer = 100.0;
    value.housing_policy.land_fee_share = 0.0;
    auto harness = build(value);
    const auto builder = harness.runtime.builders.front().firm;
    const auto index = static_cast<std::size_t>(builder.value());
    assert(index < harness.runtime.energy_inputs.size());
    assert(harness.runtime.energy_inputs[index].active);
    assert(harness.runtime.energy_inputs[index].firm == builder);
    const auto result = advance(harness, 2);
    assert(result.ok());
}

void test_affordability_feedback_reaches_demographic_port() {
    auto value = housing_spec();
    value.domestic_economy.population.start_calendar_day = 0;
    value.housing_rules.affordability_burnin_years = 0;
    value.housing_rules.leave_home_elasticity = 1.0;
    value.housing_rules.fertility_elasticity = 1.0;
    value.housing_rules.leave_home_multiplier_minimum = 0.1;
    value.housing_rules.fertility_multiplier_minimum = 0.1;
    auto harness = build(value);
    auto result = advance(harness, 366);
    assert(result.ok());
    assert(harness.runtime.housing_affordability.years_completed >= 1);
    assert(harness.runtime.housing_affordability.price_to_income_baseline > 0.0);
    harness.runtime.house_price *= 10.0;
    harness.runtime.rent_level *= 10.0;
    result = advance(harness, 366);
    assert(result.ok());
    assert(harness.runtime.housing_affordability.years_completed >= 2);
    assert(harness.runtime.housing_affordability.leave_home_multiplier < 1.0);
    assert(harness.runtime.housing_affordability.fertility_multiplier < 1.0);
    result = advance(harness, 1);
    assert(result.ok());
    assert(std::abs(harness.population_scratch.external_leave_home_multiplier_ -
                    harness.runtime.housing_affordability.leave_home_multiplier) <
           1.0e-12);
    assert(std::abs(harness.population_scratch.external_fertility_multiplier_ -
                    harness.runtime.housing_affordability.fertility_multiplier) <
           1.0e-12);
}

void test_last_death_transfers_title_to_public_estate() {
    auto value = housing_spec();
    value.domestic_economy.population.initial_persons = 1;
    value.domestic_economy.population.target_household_size = 1.0;
    auto harness = build(value);
    const auto dwelling =
        harness.runtime.properties.dwelling_for_occupant(macro_sim::HouseholdId(1));
    assert(dwelling.valid());
    M8AdvanceOptions options;
    options.base.force_death = macro_sim::PersonId(1);
    const auto result =
        advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                         harness.monetary_runtime, harness.monetary_scratch,
                         harness.financial_runtime, harness.financial_scratch,
                         harness.population_runtime, harness.population_scratch,
                         harness.runtime, harness.scratch, harness.tick, 1, options);
    if (!result.ok()) {
        std::cerr << "housing estate failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.root.households.get(macro_sim::HouseholdId(1)) == nullptr);
    const auto *record = harness.runtime.properties.get(dwelling);
    assert(record != nullptr);
    assert(record->owner == macro_sim::core::OwnerId::institutional(
                                macro_sim::core::OwnerKind::treasury));
    assert(!record->occupant.valid());
    assert(harness.runtime.properties.validate().ok());
}

} // namespace

int main() {
    test_genesis_mints_real_assets_without_money();
    test_partial_homeownership_seeds_valid_tenancies();
    test_disabled_housing_has_no_state();
    test_quiet_days_preserve_title_exactly();
    test_capability_dependencies_are_rejected();
    test_builders_create_permitted_real_stock();
    test_builder_energy_input_is_canonical();
    test_affordability_feedback_reaches_demographic_port();
    test_last_death_transfers_title_to_public_estate();
    return 0;
}
