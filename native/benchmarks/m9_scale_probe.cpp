#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>
#include <string>
#include <string_view>
#include <vector>

#if defined(__APPLE__) || defined(__linux__)
#include <sys/resource.h>
#endif

#include "macro_sim/core/digest.hpp"
#include "macro_sim/engine_session.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace {

using Clock = std::chrono::steady_clock;
using namespace macro_sim;
using namespace macro_sim::simulation;

std::atomic<bool> measure_allocations{false};
std::atomic<std::uint64_t> allocation_count{0};

enum class ProbeMode : std::uint8_t {
    m8 = 0,
    m9 = 1,
};

struct Options final {
    ProbeMode mode{ProbeMode::m8};
    std::uint64_t persons{10'000U};
    std::uint64_t warmup_days{2U};
    std::uint64_t measured_days{7U};
    bool beneficial_ownership{true};
};

struct Measurement final {
    std::string mode;
    std::string digest;
    std::uint64_t persons{0};
    std::uint64_t households{0};
    std::uint64_t firms{0};
    std::uint64_t banks{0};
    std::uint64_t warmup_days{0};
    std::uint64_t measured_days{0};
    std::uint64_t genesis_ns{0};
    std::uint64_t genesis_allocations{0};
    std::uint64_t genesis_peak_rss_bytes{0};
    std::uint64_t median_day_ns{0};
    std::uint64_t p95_day_ns{0};
    std::uint64_t maximum_day_ns{0};
    std::uint64_t total_measured_ns{0};
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t peak_rss_bytes{0};
    bool beneficial_ownership{true};
    std::vector<std::uint64_t> day_allocations;
    std::vector<std::uint64_t> day_ns;
};

[[nodiscard]] std::uint64_t peak_rss_bytes() noexcept {
#if defined(__APPLE__) || defined(__linux__)
    rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) {
        return 0U;
    }
#if defined(__APPLE__)
    return static_cast<std::uint64_t>(usage.ru_maxrss);
#else
    return static_cast<std::uint64_t>(usage.ru_maxrss) * 1024U;
#endif
#else
    return 0U;
#endif
}

[[nodiscard]] bool parse_u64(std::string_view text, std::uint64_t &value) {
    if (text.empty()) {
        return false;
    }
    char *end = nullptr;
    const auto parsed = std::strtoull(text.data(), &end, 10);
    if (end != text.data() + text.size()) {
        return false;
    }
    value = parsed;
    return true;
}

[[nodiscard]] bool parse_options(int argc, char **argv, Options &options) {
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc) {
            return false;
        }
        const std::string_view flag(argv[index]);
        const std::string_view value(argv[index + 1]);
        if (flag == "--mode") {
            if (value == "m8") {
                options.mode = ProbeMode::m8;
            } else if (value == "m9") {
                options.mode = ProbeMode::m9;
            } else {
                return false;
            }
        } else if (flag == "--persons") {
            if (!parse_u64(value, options.persons)) {
                return false;
            }
        } else if (flag == "--warmup-days") {
            if (!parse_u64(value, options.warmup_days)) {
                return false;
            }
        } else if (flag == "--days") {
            if (!parse_u64(value, options.measured_days)) {
                return false;
            }
        } else if (flag == "--beneficial-ownership") {
            if (value == "enabled") {
                options.beneficial_ownership = true;
            } else if (value == "disabled") {
                options.beneficial_ownership = false;
            } else {
                return false;
            }
        } else {
            return false;
        }
    }
    return options.persons >= 100U && options.measured_days >= 3U &&
           options.persons <=
               static_cast<std::uint64_t>(std::numeric_limits<std::uint32_t>::max());
}

[[nodiscard]] M8SimulationSpec make_spec(std::uint64_t persons,
                                         bool beneficial_ownership) {
    M8SimulationSpec spec;
    auto &population = spec.domestic_economy;
    auto &financial = population.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = std::max<std::uint64_t>(1U, persons * 21U / 500U);
    real.capital_firms = std::max<std::uint64_t>(1U, persons * 9U / 500U);
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.seed = 33'909U;
    real.rules.initial_household_money = 100.0;
    real.rules.initial_firm_money = 50.0;
    real.rules.initial_consumption_inventory = 4.0;
    real.rules.initial_capital_inventory = 3.0;
    real.rules.initial_consumption_capital = 5.0;
    real.rules.initial_expected_demand = 12.0;
    real.rules.initial_wage = 2.0;
    real.rules.initial_price = 1.5;
    real.rules.initial_capital_price = 1.5;

    monetary.rules.bank_count = 8U;
    monetary.rules.opening_capital_per_bank = 1'000.0;
    monetary.rules.interbank = true;
    monetary.rules.household_credit = true;
    monetary.rules.household_amortization = 0.0;
    monetary.policy.household_credit_limit = 1'000.0;
    monetary.policy.bank_leverage_cap = 20.0;
    monetary.initial_policy_rate = 0.002;

    financial.rules.watchlist_size = 12U;
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
    population.rules.beneficial_ownership = beneficial_ownership;
    population.rules.estates = beneficial_ownership;

    spec.energy_rules.producer_count = std::max<std::uint64_t>(2U, persons / 500U);
    spec.energy_rules.deprivation = false;
    spec.energy_rules.hoarding_beta = 0.0;

    spec.housing_rules.enabled = true;
    spec.housing_rules.resale_market = false;
    spec.housing_rules.rentals = false;
    spec.housing_rules.mortgages = false;
    spec.housing_rules.construction = false;
    spec.housing_rules.market_interval_days = 7U;
    spec.housing_rules.initial_homeownership_share = 0.75;
    spec.housing_rules.builder_count = 2U;
    spec.housing_rules.initial_builder_cash_buffer = 1'000.0;
    spec.housing_rules.builder_productivity = 0.01;
    spec.housing_rules.builder_demand_seed = 0.01;
    spec.housing_policy.mortgage_underwriting = false;
    spec.housing_policy.annual_housing_permits = persons;
    return spec;
}

void begin_allocation_measurement() noexcept {
    allocation_count.store(0U, std::memory_order_relaxed);
    measure_allocations.store(true, std::memory_order_relaxed);
}

[[nodiscard]] std::uint64_t end_allocation_measurement() noexcept {
    measure_allocations.store(false, std::memory_order_relaxed);
    return allocation_count.load(std::memory_order_relaxed);
}

template <typename Advance>
[[nodiscard]] bool measure_days(const Options &options, Advance &&advance,
                                Measurement &measurement) {
    for (std::uint64_t day = 0; day < options.warmup_days; ++day) {
        if (!advance()) {
            return false;
        }
        std::cerr << "Scale probe warmup day complete: " << day + 1U << '\n';
    }
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(options.measured_days));
    for (std::uint64_t day = 0; day < options.measured_days; ++day) {
        begin_allocation_measurement();
        const auto start = Clock::now();
        const bool advanced = advance();
        const auto stop = Clock::now();
        const auto allocations = end_allocation_measurement();
        if (!advanced) {
            return false;
        }
        const auto elapsed = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count());
        samples.push_back(elapsed);
        measurement.day_allocations.push_back(allocations);
        measurement.day_ns.push_back(elapsed);
        measurement.total_measured_ns += elapsed;
        measurement.maximum_allocations_per_day =
            std::max(measurement.maximum_allocations_per_day, allocations);
        std::cerr << "Scale probe measured day complete: " << day + 1U << ' ' << elapsed
                  << " ns\n";
    }
    std::sort(samples.begin(), samples.end());
    const auto p95_index = ((samples.size() - 1U) * 95U + 99U) / 100U;
    measurement.median_day_ns = samples[samples.size() / 2U];
    measurement.p95_day_ns = samples[p95_index];
    measurement.maximum_day_ns = samples.back();
    measurement.peak_rss_bytes = peak_rss_bytes();
    return true;
}

[[nodiscard]] Measurement run_m8(const Options &options) {
    Measurement measurement;
    measurement.mode = "m8";
    measurement.persons = options.persons;
    measurement.warmup_days = options.warmup_days;
    measurement.measured_days = options.measured_days;
    measurement.beneficial_ownership = options.beneficial_ownership;
    measurement.day_allocations.reserve(
        static_cast<std::size_t>(options.measured_days));
    measurement.day_ns.reserve(static_cast<std::size_t>(options.measured_days));

    EngineSession session(33909U);
    begin_allocation_measurement();
    const auto start = Clock::now();
    const auto initialized =
        session.initialize_m8(make_spec(options.persons, options.beneficial_ownership));
    const auto stop = Clock::now();
    measurement.genesis_allocations = end_allocation_measurement();
    if (!initialized.ok()) {
        std::cerr << "M8 scale probe genesis failed: " << initialized.message() << '\n';
        std::abort();
    }
    measurement.genesis_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count());
    measurement.genesis_peak_rss_bytes = peak_rss_bytes();
    measurement.households = session.root()->households.alive_count();
    measurement.firms = session.root()->firms.alive_count();
    measurement.banks = session.root()->banks.alive_count();
    std::cerr << "M8 scale probe genesis complete: " << measurement.genesis_ns
              << " ns\n";

    Status advance_status;
    const auto advanced = measure_days(
        options,
        [&session, &advance_status]() {
            const auto result = session.advance_m8_ticks(1U);
            if (!result.ok()) {
                advance_status = result.status();
            }
            return result.ok();
        },
        measurement);
    if (!advanced) {
        std::cerr << "M8 scale probe advance failed: "
                  << static_cast<std::uint32_t>(advance_status.code()) << ' '
                  << advance_status.message() << '\n';
        std::abort();
    }
    measurement.digest = core::state_digest(*session.root()).hex();
    return measurement;
}

[[nodiscard]] Measurement run_m9(const Options &options) {
    Measurement measurement;
    measurement.mode = "m9";
    measurement.persons = options.persons;
    measurement.warmup_days = options.warmup_days;
    measurement.measured_days = options.measured_days;
    measurement.beneficial_ownership = options.beneficial_ownership;
    measurement.day_allocations.reserve(
        static_cast<std::size_t>(options.measured_days));
    measurement.day_ns.reserve(static_cast<std::size_t>(options.measured_days));

    M9WorldSpec spec;
    spec.economies.push_back(make_spec(options.persons, options.beneficial_ownership));
    begin_allocation_measurement();
    const auto start = Clock::now();
    auto created = M9World::create(spec);
    const auto stop = Clock::now();
    measurement.genesis_allocations = end_allocation_measurement();
    if (!created.ok()) {
        std::cerr << "M9 scale probe genesis failed: " << created.status().message()
                  << '\n';
        std::abort();
    }
    auto world = std::move(*created.get_if());
    measurement.genesis_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count());
    measurement.genesis_peak_rss_bytes = peak_rss_bytes();
    const auto *root = world.economy_root(EconomyId(0U));
    if (root == nullptr) {
        std::cerr << "M9 scale probe economy root is missing\n";
        std::abort();
    }
    measurement.households = root->households.alive_count();
    measurement.firms = root->firms.alive_count();
    measurement.banks = root->banks.alive_count();
    std::cerr << "M9 scale probe genesis complete: " << measurement.genesis_ns
              << " ns\n";

    Status advance_status;
    const auto advanced = measure_days(
        options,
        [&world, &advance_status]() {
            const auto result = world.advance(1U);
            if (!result.ok()) {
                advance_status = result.status();
            }
            return result.ok();
        },
        measurement);
    if (!advanced) {
        std::cerr << "M9 scale probe advance failed: "
                  << static_cast<std::uint32_t>(advance_status.code()) << ' '
                  << advance_status.message() << '\n';
        std::abort();
    }
    measurement.digest = std::to_string(world.digest());
    return measurement;
}

void print(const Measurement &value) {
    std::cout << '{' << "\"banks\":" << value.banks << ','
              << "\"beneficial_ownership\":"
              << (value.beneficial_ownership ? "true" : "false") << ','
              << "\"day_allocations\":[";
    for (std::size_t index = 0; index < value.day_allocations.size(); ++index) {
        if (index != 0U) {
            std::cout << ',';
        }
        std::cout << value.day_allocations[index];
    }
    std::cout << "],"
              << "\"day_ns\":[";
    for (std::size_t index = 0; index < value.day_ns.size(); ++index) {
        if (index != 0U) {
            std::cout << ',';
        }
        std::cout << value.day_ns[index];
    }
    std::cout << "],"
              << "\"digest\":\"" << value.digest << "\","
              << "\"firms\":" << value.firms << ','
              << "\"genesis_allocations\":" << value.genesis_allocations << ','
              << "\"genesis_ns\":" << value.genesis_ns << ','
              << "\"genesis_peak_rss_bytes\":" << value.genesis_peak_rss_bytes << ','
              << "\"households\":" << value.households << ','
              << "\"maximum_allocations_per_day\":" << value.maximum_allocations_per_day
              << ',' << "\"maximum_day_ns\":" << value.maximum_day_ns << ','
              << "\"measured_days\":" << value.measured_days << ','
              << "\"median_day_ns\":" << value.median_day_ns << ',' << "\"mode\":\""
              << value.mode << "\","
              << "\"p95_day_ns\":" << value.p95_day_ns << ','
              << "\"peak_rss_bytes\":" << value.peak_rss_bytes << ','
              << "\"persons\":" << value.persons << ','
              << "\"scenario\":\"static-population-quiet-housing-v1\","
              << "\"schema_version\":\"m9-scale-probe-v2\","
              << "\"total_measured_ns\":" << value.total_measured_ns << ','
              << "\"warmup_days\":" << value.warmup_days << "}\n";
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
    Options options;
    if (!parse_options(argc, argv, options)) {
        std::cerr << "usage: macro_sim_m9_scale_probe --mode m8|m9 --persons N "
                     "--warmup-days N --days N "
                     "--beneficial-ownership enabled|disabled\n";
        return 2;
    }
    print(options.mode == ProbeMode::m8 ? run_m8(options) : run_m9(options));
    return 0;
}
