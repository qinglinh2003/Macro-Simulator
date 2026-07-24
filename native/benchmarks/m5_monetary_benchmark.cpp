#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
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

struct Measurement final {
    std::uint64_t households{0};
    std::uint64_t firms{0};
    std::uint64_t banks{0};
    std::uint64_t days{0};
    std::uint64_t median_ns{0};
    std::uint64_t p95_ns{0};
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t scratch_before{0};
    std::uint64_t scratch_after{0};
    std::uint64_t transfer_sink{0};
    double loan_sink{0.0};
};

[[nodiscard]] Measurement run(
    std::uint64_t households,
    std::uint64_t banks,
    std::uint64_t days
) {
    macro_sim::simulation::M5SimulationSpec spec;
    spec.real_economy.vertical =
        macro_sim::simulation::M4Vertical::capital_fiscal;
    spec.real_economy.households = households;
    spec.real_economy.consumption_firms =
        std::max<std::uint64_t>(1, households * 21 / 200);
    spec.real_economy.capital_firms =
        std::max<std::uint64_t>(1, households * 9 / 200);
    spec.real_economy.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital
        )
        | macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government
        );
    spec.real_economy.seed = 505;
    spec.real_economy.rules.initial_household_money = 20.0;
    spec.real_economy.rules.initial_firm_money = 0.0;
    spec.real_economy.rules.initial_consumption_inventory = 0.0;
    spec.real_economy.rules.initial_capital_inventory = 0.0;
    spec.real_economy.rules.initial_consumption_capital = 4.0;
    spec.real_economy.rules.initial_expected_demand = 30.0;
    spec.real_economy.rules.initial_wage = 2.0;
    spec.real_economy.rules.initial_price = 1.5;
    spec.real_economy.rules.initial_capital_price = 1.5;
    spec.rules.bank_count = banks;
    spec.rules.opening_capital_per_bank = 1.0;
    spec.rules.bank_leverage_mean = 50.0;
    spec.rules.interbank = true;
    spec.rules.household_credit = true;
    spec.rules.direct_monetary_transmission = false;
    spec.rules.firm_amortization = 0.0;
    spec.rules.household_amortization = 0.0;
    spec.policy.bank_capital_constraint = true;
    spec.policy.bank_leverage_cap = 50.0;
    macro_sim::EngineSession session(households);
    assert(session.initialize_m5(spec).ok());
    assert(session.advance_m5_ticks(5).ok());
    const auto warm = session.advance_m5_ticks(1);
    assert(warm.ok());
    assert(session.root()->loans.size() > 0);
    assert(
        session.root()->loans.total_principal().value()
        > 1.0e-12
    );
    const auto scratch_before =
        warm.get_if()->scratch_capacity_signature;
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(days));
    std::uint64_t maximum_allocations = 0;
    std::uint64_t transfer_sink = 0;
    double loan_sink = 0.0;
    std::uint64_t scratch_after = scratch_before;
    for (std::uint64_t day = 0; day < days; ++day) {
        allocation_count.store(0, std::memory_order_relaxed);
        measure_allocations.store(true, std::memory_order_relaxed);
        const auto start = Clock::now();
        auto result = session.advance_m5_ticks(1);
        const auto stop = Clock::now();
        measure_allocations.store(false, std::memory_order_relaxed);
        assert(result.ok());
        const double root_principal =
            session.root()->loans.total_principal().value();
        assert(
            std::abs(
                result.get_if()->metrics.total_loan_principal
                    - root_principal
            ) <= 1.0e-9 * std::max(1.0, root_principal)
        );
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
        transfer_sink += result.get_if()->transfer_count;
        loan_sink += root_principal;
        scratch_after = result.get_if()->scratch_capacity_signature;
    }
    std::sort(samples.begin(), samples.end());
    const auto p95 = ((samples.size() - 1) * 95 + 99) / 100;
    return {
        households,
        spec.real_economy.consumption_firms
            + spec.real_economy.capital_firms,
        banks,
        days,
        samples[samples.size() / 2],
        samples[p95],
        maximum_allocations,
        scratch_before,
        scratch_after,
        transfer_sink,
        loan_sink,
    };
}

void print(std::string_view name, const Measurement& value) {
    std::cout
        << '"' << name << "\":{"
        << "\"banks\":" << value.banks << ','
        << "\"days\":" << value.days << ','
        << "\"firms\":" << value.firms << ','
        << "\"households\":" << value.households << ','
        << "\"loan_sink\":" << value.loan_sink << ','
        << "\"maximum_allocations_per_day\":"
        << value.maximum_allocations_per_day << ','
        << "\"median_ns\":" << value.median_ns << ','
        << "\"p95_ns\":" << value.p95_ns << ','
        << "\"scratch_after\":" << value.scratch_after << ','
        << "\"scratch_before\":" << value.scratch_before << ','
        << "\"transfer_sink\":" << value.transfer_sink
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
    std::uint64_t days = 120;
    if (argc == 3 && std::string_view(argv[1]) == "--days") {
        days = std::strtoull(argv[2], nullptr, 10);
    }
    if (days < 20) {
        return 2;
    }
    const auto half = run(1000, 8, days);
    const auto p0 = run(2000, 16, days);
    const double scaling =
        static_cast<double>(p0.median_ns)
        / static_cast<double>(half.median_ns);
    std::cout << '{';
    print("half", half);
    std::cout << ',';
    print("p0", p0);
    std::cout
        << ",\"scaling_ratio\":" << scaling
        << ",\"schema_version\":\"m5-monetary-benchmark-v1\"}\n";
    return 0;
}
