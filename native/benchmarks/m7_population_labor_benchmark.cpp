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

struct DailyMeasurement final {
    std::uint64_t persons{0};
    std::uint64_t households{0};
    std::uint64_t firms{0};
    std::uint64_t days{0};
    std::uint64_t median_ns{0};
    std::uint64_t p95_ns{0};
    std::uint64_t maximum_allocations_per_day{0};
    std::uint64_t scratch_before{0};
    std::uint64_t scratch_after{0};
    double labor_sink{0.0};
};

[[nodiscard]] macro_sim::simulation::M7SimulationSpec
daily_spec(std::uint64_t persons) {
    macro_sim::simulation::M7SimulationSpec spec;
    auto &financial = spec.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical =
        macro_sim::simulation::M4Vertical::capital_fiscal;
    real.consumption_firms =
        std::max<std::uint64_t>(1, persons * 21U / 500U);
    real.capital_firms =
        std::max<std::uint64_t>(1, persons * 9U / 500U);
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital
        ) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government
        );
    real.seed = 707;
    real.rules.initial_household_money = 30.0;
    real.rules.initial_firm_money = 10.0;
    real.rules.initial_consumption_inventory = 4.0;
    real.rules.initial_capital_inventory = 3.0;
    real.rules.initial_consumption_capital = 5.0;
    real.rules.initial_expected_demand = 12.0;
    real.rules.initial_wage = 2.0;
    real.rules.initial_price = 1.5;
    real.rules.initial_capital_price = 1.5;
    monetary.rules.bank_count =
        std::max<std::uint64_t>(2, persons / 250U);
    monetary.rules.opening_capital_per_bank = 30.0;
    monetary.rules.interbank = true;
    monetary.rules.household_credit = true;
    monetary.policy.bank_capital_constraint = true;
    monetary.policy.bank_leverage_cap = 20.0;
    monetary.initial_policy_rate = 0.002;
    financial.rules.watchlist_size = 12;
    financial.rules.firm_dynamics = false;
    financial.rules.bank_dynamics = false;
    financial.policy.bond_maturity_days = 90;
    spec.population.initial_persons = persons;
    spec.population.target_household_size = 2.5;
    spec.rules.fertility = false;
    spec.rules.mortality = false;
    spec.rules.relationships = false;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.household_lifecycle = false;
    spec.rules.annual_churn = 0.0;
    return spec;
}

[[nodiscard]] DailyMeasurement
run_daily(std::uint64_t persons, std::uint64_t days) {
    const auto spec = daily_spec(persons);
    macro_sim::EngineSession session(persons);
    const auto initialized = session.initialize_m7(spec);
    if (!initialized.ok()) {
        std::cerr << "M7 benchmark initialization failed: "
                  << initialized.message() << '\n';
        std::abort();
    }
    const auto warmup = session.advance_m7_ticks(5);
    assert(warmup.ok());
    const auto warm = session.advance_m7_ticks(1);
    assert(warm.ok());
    const auto scratch_before =
        warm.get_if()->scratch_capacity_signature;
    std::vector<std::uint64_t> samples;
    samples.reserve(static_cast<std::size_t>(days));
    std::uint64_t maximum_allocations = 0;
    std::uint64_t scratch_after = scratch_before;
    double labor_sink = 0.0;
    for (std::uint64_t day = 0; day < days; ++day) {
        allocation_count.store(0, std::memory_order_relaxed);
        measure_allocations.store(true, std::memory_order_relaxed);
        const auto start = Clock::now();
        const auto result = session.advance_m7_ticks(1);
        const auto stop = Clock::now();
        measure_allocations.store(false, std::memory_order_relaxed);
        if (!result.ok()) {
            std::cerr << "M7 benchmark advance failed: "
                      << result.status().message()
                      << " at measured day " << day << '\n';
            std::abort();
        }
        maximum_allocations = std::max(
            maximum_allocations,
            allocation_count.load(std::memory_order_relaxed)
        );
        samples.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                stop - start
            ).count()
        ));
        scratch_after =
            result.get_if()->scratch_capacity_signature;
        labor_sink +=
            result.get_if()->metrics.employed_fte +
            result.get_if()->metrics.labor_supply;
    }
    std::sort(samples.begin(), samples.end());
    const auto p95 = ((samples.size() - 1U) * 95U + 99U) / 100U;
    return {
        persons,
        static_cast<std::uint64_t>(std::ceil(
            static_cast<double>(persons) /
            spec.population.target_household_size
        )),
        spec.financial_economy.monetary_economy.real_economy
            .consumption_firms +
            spec.financial_economy.monetary_economy.real_economy
                .capital_firms,
        days,
        samples[samples.size() / 2U],
        samples[p95],
        maximum_allocations,
        scratch_before,
        scratch_after,
        labor_sink,
    };
}

struct MatchingMeasurement final {
    std::uint64_t candidates{0};
    std::uint64_t median_ns{0};
    std::uint64_t match_sink{0};
};

[[nodiscard]] MatchingMeasurement
run_matching(std::uint64_t candidates) {
    macro_sim::core::PersonStore persons;
    macro_sim::core::HouseholdMembershipBook membership;
    const auto half = candidates / 2U;
    for (std::uint64_t index = 0; index < candidates; ++index) {
        macro_sim::core::PersonRecord person;
        person.sex =
            index < half
                ? macro_sim::core::PersonSex::female
                : macro_sim::core::PersonSex::male;
        const auto age = 18U + (index * 17U) % 63U;
        const auto day_offset =
            static_cast<std::int32_t>((index * 97U) % 365U);
        person.birth_day =
            -static_cast<std::int32_t>(age * 365U) - day_offset;
        person.efficiency =
            0.55 + static_cast<double>((index * 37U) % 145U) /
                       100.0;
        person.household = macro_sim::HouseholdId(index + 1U);
        const auto created = persons.create(person);
        assert(created.ok());
        assert(
            membership
                .add(*created.get_if(), person.household)
                .ok()
        );
    }
    macro_sim::core::MarriageRules rules;
    std::vector<std::uint64_t> samples;
    samples.reserve(5);
    std::uint64_t match_sink = 0;
    for (std::uint32_t iteration = 0; iteration < 5U;
         ++iteration) {
        const auto start = Clock::now();
        const auto matches =
            macro_sim::core::exact_marriage_matches(
                persons, membership, rules, 0
            );
        const auto stop = Clock::now();
        assert(matches.ok());
        match_sink += matches.get_if()->size();
        samples.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                stop - start
            ).count()
        ));
    }
    std::sort(samples.begin(), samples.end());
    return {
        candidates,
        samples[samples.size() / 2U],
        match_sink,
    };
}

struct RosterMeasurement final {
    std::uint64_t jobs{0};
    std::uint64_t median_ns{0};
    std::uint64_t mutation_sink{0};
};

[[nodiscard]] RosterMeasurement
run_roster(std::uint64_t jobs) {
    std::vector<std::uint64_t> samples;
    samples.reserve(5);
    std::uint64_t mutation_sink = 0;
    for (std::uint32_t iteration = 0; iteration < 5U;
         ++iteration) {
        macro_sim::core::EmploymentBook employment;
        std::vector<macro_sim::JobId> identifiers;
        identifiers.reserve(static_cast<std::size_t>(jobs));
        for (std::uint64_t person = 1; person <= jobs; ++person) {
            const auto created = employment.hire(
                macro_sim::PersonId(person), macro_sim::FirmId(1),
                0, 1.0, 1.0
            );
            assert(created.ok());
            identifiers.push_back(*created.get_if());
        }
        const auto start = Clock::now();
        for (const auto job : identifiers) {
            assert(
                employment
                    .separate(
                        job, 1,
                        macro_sim::core::SeparationKind::firm_exit
                    )
                    .ok()
            );
        }
        const auto stop = Clock::now();
        mutation_sink += employment.active_count();
        samples.push_back(static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                stop - start
            ).count()
        ));
    }
    std::sort(samples.begin(), samples.end());
    return {
        jobs,
        samples[samples.size() / 2U],
        mutation_sink,
    };
}

void print_daily(
    std::string_view name, const DailyMeasurement &value
) {
    std::cout << '"' << name << "\":{"
              << "\"days\":" << value.days << ','
              << "\"firms\":" << value.firms << ','
              << "\"households\":" << value.households << ','
              << "\"labor_sink\":" << value.labor_sink << ','
              << "\"maximum_allocations_per_day\":"
              << value.maximum_allocations_per_day << ','
              << "\"median_ns\":" << value.median_ns << ','
              << "\"p95_ns\":" << value.p95_ns << ','
              << "\"persons\":" << value.persons << ','
              << "\"scratch_after\":" << value.scratch_after << ','
              << "\"scratch_before\":" << value.scratch_before
              << '}';
}

void print_matching(const MatchingMeasurement &value) {
    std::cout << "{\"candidates\":" << value.candidates << ','
              << "\"match_sink\":" << value.match_sink << ','
              << "\"median_ns\":" << value.median_ns << '}';
}

void print_roster(
    std::string_view name, const RosterMeasurement &value
) {
    std::cout << '"' << name << "\":{"
              << "\"jobs\":" << value.jobs << ','
              << "\"median_ns\":" << value.median_ns << ','
              << "\"mutation_sink\":" << value.mutation_sink
              << '}';
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

void operator delete(void *pointer) noexcept {
    std::free(pointer);
}

void operator delete(void *pointer, std::size_t) noexcept {
    std::free(pointer);
}

int main(int argc, char **argv) {
    std::uint64_t days = 40;
    if (argc == 3 && std::string_view(argv[1]) == "--days") {
        days = std::strtoull(argv[2], nullptr, 10);
    }
    if (days < 20) {
        return 2;
    }
    const auto half = run_daily(1'000, days);
    const auto p0 = run_daily(2'000, days);
    const double daily_scaling =
        static_cast<double>(p0.median_ns) /
        static_cast<double>(half.median_ns);

    std::vector<MatchingMeasurement> matching;
    for (const auto candidates :
         {400U, 800U, 1'600U, 3'200U}) {
        matching.push_back(run_matching(candidates));
    }
    const double matching_normalized_scaling =
        (static_cast<double>(matching.back().median_ns) /
         static_cast<double>(matching.back().candidates)) /
        (static_cast<double>(matching.front().median_ns) /
         static_cast<double>(matching.front().candidates));

    const auto roster_small = run_roster(400);
    const auto roster_large = run_roster(3'200);
    const double roster_normalized_scaling =
        (static_cast<double>(roster_large.median_ns) /
         static_cast<double>(roster_large.jobs)) /
        (static_cast<double>(roster_small.median_ns) /
         static_cast<double>(roster_small.jobs));

    std::cout << '{';
    print_daily("half", half);
    std::cout << ',';
    print_daily("p0", p0);
    std::cout << ",\"daily_scaling_ratio\":"
              << daily_scaling;
    std::cout << ",\"matching\":[";
    for (std::size_t index = 0; index < matching.size(); ++index) {
        if (index != 0) {
            std::cout << ',';
        }
        print_matching(matching[index]);
    }
    std::cout << "],\"matching_normalized_scaling_ratio\":"
              << matching_normalized_scaling << ',';
    print_roster("roster_small", roster_small);
    std::cout << ',';
    print_roster("roster_large", roster_large);
    std::cout << ",\"roster_normalized_scaling_ratio\":"
              << roster_normalized_scaling
              << ",\"schema_version\":"
                 "\"m7-population-labor-benchmark-v1\"}\n";
    return 0;
}
