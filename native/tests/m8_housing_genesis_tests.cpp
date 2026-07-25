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

} // namespace

int main() {
    test_genesis_mints_real_assets_without_money();
    test_partial_homeownership_seeds_valid_tenancies();
    test_disabled_housing_has_no_state();
    test_quiet_days_preserve_title_exactly();
    test_capability_dependencies_are_rejected();
    return 0;
}
