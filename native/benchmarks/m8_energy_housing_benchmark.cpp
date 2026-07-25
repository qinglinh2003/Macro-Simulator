#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>
#include <string_view>
#include <vector>

#include "macro_sim/engine_session.hpp"

namespace {

std::atomic<bool> measure_allocations{false};
std::atomic<std::uint64_t> allocation_count{0};
using Clock = std::chrono::steady_clock;

enum class HousingMode : std::uint8_t {
    disabled = 0,
    quiet = 1,
    active = 2,
};

struct Measurement final {
    std::uint64_t persons{0};
    std::uint64_t days{0};
    std::uint64_t median_ns{0};
    std::uint64_t p95_ns{0};
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t scratch_before{0};
    std::uint64_t scratch_after{0};
    double energy_sink{0.0};
    double housing_sink{0.0};
};

[[nodiscard]] macro_sim::simulation::M8SimulationSpec
make_spec(std::uint64_t persons, HousingMode housing_mode) {
    macro_sim::simulation::M8SimulationSpec spec;
    auto &population = spec.domestic_economy;
    auto &financial = population.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    real.consumption_firms = std::max<std::uint64_t>(1, persons * 21U / 500U);
    real.capital_firms = std::max<std::uint64_t>(1, persons * 9U / 500U);
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    real.seed = 808;
    real.rules.initial_household_money = 100.0;
    real.rules.initial_firm_money = 50.0;
    real.rules.initial_consumption_inventory = 4.0;
    real.rules.initial_capital_inventory = 3.0;
    real.rules.initial_consumption_capital = 5.0;
    real.rules.initial_expected_demand = 12.0;
    real.rules.initial_wage = 2.0;
    real.rules.initial_price = 1.5;
    real.rules.initial_capital_price = 1.5;
    monetary.rules.bank_count = std::max<std::uint64_t>(2, persons / 250U);
    monetary.rules.opening_capital_per_bank = 1'000.0;
    monetary.rules.interbank = true;
    monetary.rules.household_credit = true;
    monetary.rules.household_amortization = 0.0;
    monetary.policy.household_credit_limit = 1'000.0;
    monetary.policy.bank_leverage_cap = 20.0;
    monetary.initial_policy_rate = 0.002;
    financial.rules.watchlist_size = 12;
    financial.rules.firm_dynamics = false;
    financial.rules.bank_dynamics = false;
    population.population.initial_persons = persons;
    population.population.target_household_size = 2.5;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.relationships = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.household_lifecycle = false;
    population.rules.annual_churn = 0.0;
    spec.energy_rules.producer_count = std::max<std::uint64_t>(2, persons / 500U);
    spec.energy_rules.deprivation = false;
    spec.energy_rules.hoarding_beta = 0.0;
    spec.housing_rules.enabled = housing_mode != HousingMode::disabled;
    spec.housing_rules.resale_market = housing_mode == HousingMode::active;
    spec.housing_rules.rentals = housing_mode == HousingMode::active;
    spec.housing_rules.mortgages = housing_mode == HousingMode::active;
    spec.housing_rules.construction = housing_mode == HousingMode::active;
    spec.housing_rules.market_interval_days = 7;
    spec.housing_rules.initial_homeownership_share = 0.75;
    spec.housing_rules.builder_count = 2;
    spec.housing_rules.initial_builder_cash_buffer = 1'000.0;
    spec.housing_rules.builder_productivity = 0.01;
    spec.housing_rules.builder_demand_seed = 0.01;
    spec.housing_policy.mortgage_underwriting = false;
    spec.housing_policy.annual_housing_permits = persons;
    return spec;
}

[[nodiscard]] Measurement run(std::uint64_t persons, std::uint64_t days,
                              HousingMode housing_mode) {
    macro_sim::EngineSession session(persons ^
                                     static_cast<std::uint64_t>(housing_mode));
    const auto initialized = session.initialize_m8(make_spec(persons, housing_mode));
    if (!initialized.ok()) {
        std::cerr << "M8 benchmark initialization failed: " << initialized.message()
                  << '\n';
        std::abort();
    }
    const auto warmup = session.advance_m8_ticks(10);
    if (!warmup.ok()) {
        std::cerr << "M8 benchmark warmup failed: " << warmup.status().message()
                  << '\n';
        std::abort();
    }
    const auto opening = session.advance_m8_ticks(1);
    assert(opening.ok());
    const auto scratch_before = opening.get_if()->scratch_capacity_signature;
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(days));
    std::uint64_t maximum_allocations = 0;
    std::uint64_t scratch_after = scratch_before;
    double energy_sink = 0.0;
    double housing_sink = 0.0;
    for (std::uint64_t day = 0; day < days; ++day) {
        allocation_count.store(0, std::memory_order_relaxed);
        measure_allocations.store(true, std::memory_order_relaxed);
        const auto start = Clock::now();
        const auto result = session.advance_m8_ticks(1);
        const auto stop = Clock::now();
        measure_allocations.store(false, std::memory_order_relaxed);
        if (!result.ok()) {
            std::cerr << "M8 benchmark advance failed: " << result.status().message()
                      << '\n';
            std::abort();
        }
        maximum_allocations = std::max(
            maximum_allocations, allocation_count.load(std::memory_order_relaxed));
        samples.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start)
                .count()));
        scratch_after = result.get_if()->scratch_capacity_signature;
        energy_sink += result.get_if()->metrics.energy.capacity +
                       result.get_if()->metrics.energy.requested_total;
        housing_sink += result.get_if()->metrics.housing.housing_stock +
                        result.get_if()->metrics.housing.active_listings +
                        result.get_if()->metrics.housing.construction_output;
    }
    std::sort(samples.begin(), samples.end());
    const auto p95_index = ((samples.size() - 1U) * 95U + 99U) / 100U;
    return {
        persons,
        days,
        samples[samples.size() / 2U],
        samples[p95_index],
        maximum_allocations,
        scratch_before,
        scratch_after,
        energy_sink,
        housing_sink,
    };
}

void print_measurement(std::string_view name, const Measurement &value) {
    std::cout << '"' << name << "\":{"
              << "\"days\":" << value.days << ','
              << "\"energy_sink\":" << value.energy_sink << ','
              << "\"housing_sink\":" << value.housing_sink << ','
              << "\"maximum_allocations_per_day\":" << value.maximum_allocations_per_day
              << ',' << "\"median_ns\":" << value.median_ns << ','
              << "\"p95_ns\":" << value.p95_ns << ',' << "\"persons\":" << value.persons
              << ',' << "\"scratch_after\":" << value.scratch_after << ','
              << "\"scratch_before\":" << value.scratch_before << '}';
}

} // namespace

void *operator new(std::size_t size) {
    if (measure_allocations.load(std::memory_order_relaxed)) {
        allocation_count.fetch_add(1, std::memory_order_relaxed);
    }
    if (void *pointer = std::malloc(size); pointer != nullptr) {
        return pointer;
    }
    throw std::bad_alloc();
}

void operator delete(void *pointer) noexcept { std::free(pointer); }

void operator delete(void *pointer, std::size_t) noexcept { std::free(pointer); }

int main(int argc, char **argv) {
    std::uint64_t days = 40;
    if (argc == 3 && std::string_view(argv[1]) == "--days") {
        days = std::strtoull(argv[2], nullptr, 10);
    }
    if (days < 20) {
        return 2;
    }
    const auto quiet_small = run(500, days, HousingMode::quiet);
    const auto quiet_p0 = run(2'000, days, HousingMode::quiet);
    const auto energy_only = run(2'000, days, HousingMode::disabled);
    const auto active_market = run(500, days, HousingMode::active);
    const auto entity_ratio = static_cast<double>(quiet_p0.median_ns) /
                              static_cast<double>(quiet_small.median_ns);
    const auto normalized_entity_ratio = entity_ratio / 4.0;
    const auto quiet_housing_over_energy = static_cast<double>(quiet_p0.median_ns) /
                                           static_cast<double>(energy_only.median_ns);

    std::cout << '{';
    print_measurement("quiet_small", quiet_small);
    std::cout << ',';
    print_measurement("quiet_p0", quiet_p0);
    std::cout << ',';
    print_measurement("energy_only_p0", energy_only);
    std::cout << ',';
    print_measurement("active_market", active_market);
    std::cout << ",\"entity_scaling_ratio\":" << entity_ratio
              << ",\"normalized_entity_scaling_ratio\":" << normalized_entity_ratio
              << ",\"quiet_housing_over_energy_ratio\":" << quiet_housing_over_energy
              << ",\"schema_version\":"
                 "\"m8-energy-housing-benchmark-v1\"}\n";
    return 0;
}
