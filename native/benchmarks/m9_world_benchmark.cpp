#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>
#include <string_view>
#include <vector>

#include "macro_sim/simulation/m9.hpp"

namespace {

std::atomic<bool> measure_allocations{false};
std::atomic<std::uint64_t> allocation_count{0};
using Clock = std::chrono::steady_clock;
using namespace macro_sim;
using namespace macro_sim::simulation;

struct Measurement final {
    std::size_t economies{0};
    std::uint64_t days{0};
    std::uint64_t median_ns{0};
    std::uint64_t p95_ns{0};
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t digest{0};
    std::uint64_t trade_routes{0};
    std::uint64_t migration_routes{0};
};

[[nodiscard]] M8SimulationSpec domestic_spec(std::uint64_t seed, double wage) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 4;
    real.consumption_firms = 2;
    real.capital_firms = 1;
    real.seed = seed;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_household_money = 100.0;
    real.rules.initial_firm_money = 40.0;
    real.rules.initial_consumption_inventory = 20.0;
    real.rules.initial_capital_inventory = 5.0;
    real.rules.initial_consumption_capital = 8.0;
    real.rules.initial_wage = wage;
    real.rules.initial_price = 1.2;
    monetary.rules.bank_count = 1;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 8;
    population.population.target_household_size = 2.0;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.relationships = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.household_lifecycle = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.producer_count = 1;
    value.energy_rules.deprivation = false;
    value.energy_rules.initial_wage = wage;
    value.housing_rules.enabled = false;
    return value;
}

[[nodiscard]] M9WorldSpec world_spec(std::size_t economies) {
    M9WorldSpec spec;
    spec.rules.trade = true;
    spec.rules.capital = true;
    spec.rules.migration = true;
    spec.rules.fx_trade_cap = 0.25;
    spec.rules.capital_mobility = 0.1;
    spec.rules.capital_adjustment = 0.1;
    spec.rules.migration_rate = 0.01;
    spec.rules.wage_smoothing = 1.0;
    spec.economies.reserve(economies);
    spec.external_policies.resize(economies);
    for (std::size_t index = 0; index < economies; ++index) {
        spec.economies.push_back(
            domestic_spec(9100U + static_cast<std::uint64_t>(index),
                          1.0 + 0.01 * static_cast<double>(index % 11U)));
    }
    return spec;
}

[[nodiscard]] Measurement run(std::size_t economies, std::uint64_t days) {
    auto created = M9World::create(world_spec(economies));
    if (!created.ok()) {
        std::cerr << "M9 benchmark genesis failed: " << created.status().message()
                  << '\n';
        std::abort();
    }
    auto world = std::move(*created.get_if());
    if (!world.advance(2).ok()) {
        std::abort();
    }
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(days));
    std::uint64_t maximum_allocations = 0U;
    std::uint64_t trade_routes = 0U;
    std::uint64_t migration_routes = 0U;
    for (std::uint64_t day = 0; day < days; ++day) {
        allocation_count.store(0U, std::memory_order_relaxed);
        measure_allocations.store(true, std::memory_order_relaxed);
        const auto start = Clock::now();
        auto result = world.advance(1);
        const auto stop = Clock::now();
        measure_allocations.store(false, std::memory_order_relaxed);
        if (!result.ok()) {
            std::cerr << "M9 benchmark advance failed: " << result.status().message()
                      << '\n';
            std::abort();
        }
        maximum_allocations = std::max(
            maximum_allocations, allocation_count.load(std::memory_order_relaxed));
        samples.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start)
                .count()));
        trade_routes += result.get_if()->metrics.trade_routes;
        migration_routes += result.get_if()->metrics.migration_routes;
    }
    std::sort(samples.begin(), samples.end());
    const auto p95_index = ((samples.size() - 1U) * 95U + 99U) / 100U;
    return {
        economies,
        days,
        samples[samples.size() / 2U],
        samples[p95_index],
        maximum_allocations,
        world.digest(),
        trade_routes,
        migration_routes,
    };
}

void print(std::string_view name, const Measurement &value) {
    std::cout << '"' << name << "\":{"
              << "\"days\":" << value.days << ',' << "\"digest\":" << value.digest
              << ',' << "\"economies\":" << value.economies << ','
              << "\"maximum_allocations_per_day\":" << value.maximum_allocations_per_day
              << ',' << "\"median_ns\":" << value.median_ns << ','
              << "\"migration_routes\":" << value.migration_routes << ','
              << "\"p95_ns\":" << value.p95_ns << ','
              << "\"trade_routes\":" << value.trade_routes << '}';
}

} // namespace

void *operator new(std::size_t size) {
    if (measure_allocations.load(std::memory_order_relaxed)) {
        allocation_count.fetch_add(1U, std::memory_order_relaxed);
    }
    if (void *pointer = std::malloc(size); pointer != nullptr) {
        return pointer;
    }
    throw std::bad_alloc();
}

void operator delete(void *pointer) noexcept { std::free(pointer); }

void operator delete(void *pointer, std::size_t) noexcept { std::free(pointer); }

int main(int argc, char **argv) {
    std::uint64_t days = 7U;
    if (argc == 3 && std::string_view(argv[1]) == "--days") {
        days = std::strtoull(argv[2], nullptr, 10);
    }
    if (days < 3U) {
        return 2;
    }
    const auto n2 = run(2U, days);
    const auto n4 = run(4U, days);
    const auto n8 = run(8U, days);
    const auto n16 = run(16U, days);
    const auto n64 = run(64U, days);
    const auto n256 = run(256U, days);
    std::cout << '{';
    print("n2", n2);
    std::cout << ',';
    print("n4", n4);
    std::cout << ',';
    print("n8", n8);
    std::cout << ',';
    print("n16", n16);
    std::cout << ',';
    print("n64", n64);
    std::cout << ',';
    print("n256", n256);
    std::cout << ",\"dense_edge_threshold\":" << kM9DenseEdgeThreshold
              << ",\"schema_version\":\"m9-world-benchmark-v1\"}\n";
    return 0;
}
