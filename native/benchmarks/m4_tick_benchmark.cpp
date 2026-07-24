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
#include "macro_sim/simulation/m4.hpp"

namespace {

std::atomic<bool> measure_allocations{false};
std::atomic<std::uint64_t> allocation_count{0};
using Clock = std::chrono::steady_clock;

struct Statistics final {
    std::uint64_t median_ns{0};
    std::uint64_t p95_ns{0};
};

struct Measurement final {
    std::uint64_t households{0};
    std::uint64_t consumption_firms{0};
    std::uint64_t capital_firms{0};
    std::uint64_t days{0};
    Statistics latency;
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t scratch_before{0};
    std::uint64_t scratch_after{0};
    std::uint64_t trade_sink{0};
    double money_sink{0.0};
};

[[nodiscard]] Statistics statistics(
    std::vector<std::uint64_t> samples
) {
    std::sort(samples.begin(), samples.end());
    const auto p95_index = ((samples.size() - 1) * 95 + 99) / 100;
    return {
        samples[samples.size() / 2],
        samples[p95_index],
    };
}

[[nodiscard]] Measurement run(
    std::uint64_t households,
    std::uint64_t consumption_firms,
    std::uint64_t capital_firms,
    std::uint64_t days
) {
    macro_sim::simulation::M4SimulationSpec spec;
    spec.vertical =
        macro_sim::simulation::M4Vertical::capital_fiscal;
    spec.households = households;
    spec.consumption_firms = consumption_firms;
    spec.capital_firms = capital_firms;
    spec.seed = 206;
    spec.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital
        )
        | macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government
        );
    spec.market_protocol =
        macro_sim::algorithms::MatchingProtocol::sampled;
    macro_sim::EngineSession session(households);
    assert(session.initialize_simulation(spec).ok());
    assert(session.advance_ticks(5).ok());
    const auto scratch_before =
        session.tick_scratch()->capacity_signature();
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(days));
    std::uint64_t maximum_allocations = 0;
    std::uint64_t trade_sink = 0;
    double money_sink = 0.0;
    for (std::uint64_t day = 0; day < days; ++day) {
        allocation_count.store(0, std::memory_order_relaxed);
        measure_allocations.store(true, std::memory_order_relaxed);
        const auto start = Clock::now();
        auto result = session.advance_ticks(1);
        const auto stop = Clock::now();
        measure_allocations.store(false, std::memory_order_relaxed);
        if (!result.ok()) {
            std::cerr
                << "advance failed at measured day " << day
                << ": " << result.status().message() << '\n';
            std::abort();
        }
        maximum_allocations = std::max(
            maximum_allocations,
            allocation_count.load(std::memory_order_relaxed)
        );
        samples.push_back(
            static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    stop - start
                ).count()
            )
        );
        trade_sink += result.get_if()->trade_count;
        money_sink += result.get_if()->metrics.total_money;
    }
    return {
        households,
        consumption_firms,
        capital_firms,
        days,
        statistics(std::move(samples)),
        maximum_allocations,
        scratch_before,
        session.tick_scratch()->capacity_signature(),
        trade_sink,
        money_sink,
    };
}

void print_measurement(std::string_view name, const Measurement& value) {
    std::cout
        << '"' << name << "\":{"
        << "\"capital_firms\":" << value.capital_firms << ','
        << "\"consumption_firms\":" << value.consumption_firms << ','
        << "\"days\":" << value.days << ','
        << "\"households\":" << value.households << ','
        << "\"maximum_allocations_per_day\":"
        << value.maximum_allocations_per_day << ','
        << "\"median_ns\":" << value.latency.median_ns << ','
        << "\"money_sink\":" << value.money_sink << ','
        << "\"p95_ns\":" << value.latency.p95_ns << ','
        << "\"scratch_after\":" << value.scratch_after << ','
        << "\"scratch_before\":" << value.scratch_before << ','
        << "\"trade_sink\":" << value.trade_sink
        << '}';
}

}  // namespace

void* operator new(std::size_t size) {
    if (measure_allocations.load(std::memory_order_relaxed)) {
        allocation_count.fetch_add(1, std::memory_order_relaxed);
    }
    if (void* pointer = std::malloc(size); pointer != nullptr) {
        return pointer;
    }
    throw std::bad_alloc();
}

void operator delete(void* pointer) noexcept {
    std::free(pointer);
}

void operator delete(void* pointer, std::size_t) noexcept {
    std::free(pointer);
}

int main(int argc, char** argv) {
    std::uint64_t days = 365;
    if (argc == 3 && std::string_view(argv[1]) == "--days") {
        days = std::strtoull(argv[2], nullptr, 10);
    }
    if (days < 20) {
        std::cerr << "days must be at least 20\n";
        return 2;
    }
    const auto half = run(2500, 263, 112, days);
    const auto p0 = run(5000, 525, 225, days);
    if (half.money_sink <= 0.0 || p0.money_sink <= 0.0) {
        return 3;
    }
    const double scaling_ratio =
        static_cast<double>(p0.latency.median_ns)
        / static_cast<double>(half.latency.median_ns);
    std::cout << '{';
    print_measurement("half", half);
    std::cout << ',';
    print_measurement("p0", p0);
    std::cout
        << ",\"scaling_ratio\":" << scaling_ratio
        << ",\"schema_version\":\"m4-tick-benchmark-v1\"}\n";
    return 0;
}
