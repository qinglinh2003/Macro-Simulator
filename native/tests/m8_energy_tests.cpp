#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m7_checkpoint.hpp"
#include "macro_sim/simulation/m8.hpp"

namespace {

using macro_sim::Tick;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec spec() {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &real =
        population.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 5;
    real.capital_firms = 2;
    real.seed = 8080;
    real.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
        capability_bit(M4Capability::government);
    real.rules.initial_household_money = 50.0;
    real.rules.initial_firm_money = 12.0;
    real.rules.initial_consumption_inventory = 5.0;
    real.rules.initial_capital_inventory = 4.0;
    real.rules.initial_consumption_capital = 8.0;
    real.rules.initial_expected_demand = 10.0;
    real.rules.initial_wage = 1.5;
    real.rules.initial_price = 1.4;
    real.rules.initial_capital_price = 1.6;
    real.rules.government_deficit_target = 0.0;
    auto &monetary = population.financial_economy.monetary_economy;
    monetary.rules.bank_count = 3;
    monetary.rules.opening_capital_per_bank = 40.0;
    monetary.rules.bank_leverage_mean = 8.0;
    monetary.rules.interbank = true;
    monetary.rules.full_firm_pnl = true;
    monetary.rules.realized_bank_pnl = true;
    monetary.policy.bank_capital_constraint = true;
    monetary.policy.bank_leverage_cap = 8.0;
    population.financial_economy.policy.bank_minimum_capital = 20.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.financial_economy.rules.sector_switching = false;
    population.population.initial_persons = 100;
    population.population.target_household_size = 2.5;
    population.population.start_calendar_day = 20'000;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.producer_count = 2;
    value.energy_rules.initial_producer_cash = 30.0;
    value.energy_rules.initial_price = 1.2;
    value.energy_rules.initial_wage = 1.5;
    value.energy_rules.household_need = 0.2;
    value.energy_rules.downstream_intensity = 0.08;
    value.energy_rules.deprivation_burnin_years = 0;
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

[[nodiscard]] Harness build(M8SimulationSpec value = spec()) {
    auto initialization = build_m8_genesis(value);
    if (!initialization.ok()) {
        std::cerr << "M8 genesis failed: "
                  << initialization.status().message() << "\n";
    }
    assert(initialization.ok());
    auto state = std::move(*initialization.get_if());
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
        Tick(0),
    };
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(
        result.root, result.financial_runtime
    );
    result.population_scratch.reserve(
        result.population_runtime
    );
    result.scratch.reserve(result.root, result.runtime);
    return result;
}

[[nodiscard]] macro_sim::Result<M8AdvanceResult>
advance(Harness &harness, std::uint64_t count,
        const M8AdvanceOptions &options = {}) {
    return advance_m8_ticks(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch,
        harness.financial_runtime, harness.financial_scratch,
        harness.population_runtime, harness.population_scratch,
        harness.runtime, harness.scratch, harness.tick, count, options
    );
}

[[nodiscard]] std::vector<std::uint8_t>
base_checkpoint(const Harness &harness) {
    auto bytes = save_m7_checkpoint(
        harness.root, harness.real_runtime,
        harness.monetary_runtime, harness.financial_runtime,
        harness.population_runtime, harness.tick
    );
    assert(bytes.ok());
    return *bytes.get_if();
}

void test_genesis_owns_energy_components() {
    auto harness = build();
    std::uint64_t producers = 0;
    harness.root.firms.for_each_alive(
        [&producers](macro_sim::FirmId,
                     const macro_sim::core::FirmComponent &firm) {
            producers +=
                firm.sector == macro_sim::core::FirmSector::energy
                    ? 1U
                    : 0U;
        }
    );
    assert(producers == 2);
    assert(harness.real_runtime.capability_mask ==
           (capability_bit(M4Capability::physical_capital) |
            capability_bit(M4Capability::government)));
    assert(
        std::count_if(
            harness.runtime.energy_producers.begin(),
            harness.runtime.energy_producers.end(),
            [](const EnergyProducerComponent &producer) {
                return producer.active;
            }
        ) == 2
    );
    assert(
        std::count_if(
            harness.runtime.energy_inputs.begin(),
            harness.runtime.energy_inputs.end(),
            [](const EnergyInputComponent &input) {
                return input.active;
            }
        ) == 7
    );
    assert(
        validate_m8_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime, harness.financial_runtime,
            harness.population_runtime, harness.runtime, harness.tick
        )
            .ok()
    );
}

void test_energy_day_conserves_and_constrains() {
    auto harness = build();
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M8 energy day failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.tick == Tick(1));
    const auto &energy = result.get_if()->metrics.energy;
    assert(energy.production > 0.0);
    assert(energy.sold > 0.0);
    assert(energy.household_units > 0.0);
    assert(energy.industry_units > 0.0);
    assert(energy.transaction_price > 0.0);
    assert(energy.opening_supply + 1.0e-8 >= energy.sold);
    assert(
        validate_m8_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime, harness.financial_runtime,
            harness.population_runtime, harness.runtime, harness.tick
        )
            .ok()
    );
}

void test_priority_rationing_changes_allocation() {
    auto household_first_spec = spec();
    household_first_spec.energy_rules.producer_inventory_ratio = 0.0;
    household_first_spec.energy_policy.rationing =
        EnergyRationing::household_first;
    auto industry_first_spec = household_first_spec;
    industry_first_spec.energy_policy.rationing =
        EnergyRationing::industry_first;
    auto households = build(household_first_spec);
    auto industry = build(industry_first_spec);
    M8AdvanceOptions constrained;
    constrained.energy_input =
        EnergyExogenousInput{
            0.05, 1.0, 1.0, 1.0, 1.0, 1.0,
        };
    const auto household_result =
        advance(households, 1, constrained);
    const auto industry_result =
        advance(industry, 1, constrained);
    assert(household_result.ok());
    assert(industry_result.ok());
    assert(
        household_result.get_if()->metrics.energy.household_units >
        industry_result.get_if()->metrics.energy.household_units
    );
    assert(
        household_result.get_if()->metrics.energy.industry_units <
        industry_result.get_if()->metrics.energy.industry_units
    );
}

void test_fiscal_energy_flows_and_reserve() {
    auto value = spec();
    value.energy_policy.excise_rate = 0.2;
    value.energy_policy.household_subsidy_rate = 0.25;
    value.energy_policy.price_cap = 0.8;
    value.energy_policy.price_cap_compensation = true;
    value.energy_policy.strategic_reserve_target = 5.0;
    value.energy_policy.strategic_reserve_flow_cap = 1.0;
    value.energy_rules.producer_inventory_ratio = 2.0;
    auto harness = build(value);
    auto result = advance(harness, 1);
    assert(result.ok());
    const auto &energy = result.get_if()->metrics.energy;
    assert(energy.excise_paid > 0.0);
    assert(energy.subsidy_paid > 0.0);
    assert(energy.cap_compensation > 0.0);
    assert(energy.strategic_reserve_flow > 0.0);
    assert(energy.strategic_reserve_stock > 0.0);

    harness.runtime.energy_policy.strategic_reserve_target = 0.0;
    result = advance(harness, 1);
    assert(result.ok());
    assert(
        result.get_if()->metrics.energy.strategic_reserve_flow < 0.0
    );
    assert(
        result.get_if()->metrics.energy
                .strategic_reserve_sale_revenue >
        0.0
    );
}

void test_all_fallible_boundaries_are_atomic() {
    for (const auto point : {
             M8FaultPoint::after_energy_plan,
             M8FaultPoint::after_energy_clearing,
             M8FaultPoint::before_commit,
         }) {
        auto harness = build();
        const auto before_base = base_checkpoint(harness);
        const auto before_energy = harness.runtime;
        M8AdvanceOptions options;
        options.fault_point = point;
        const auto result = advance(harness, 1, options);
        assert(!result.ok());
        assert(harness.tick == Tick(0));
        assert(base_checkpoint(harness) == before_base);
        assert(harness.runtime == before_energy);
    }
}

void test_batch_and_split_are_exact() {
    auto batch = build();
    auto split = build();
    const auto batch_result = advance(batch, 20);
    assert(batch_result.ok());
    for (std::uint64_t day = 0; day < 20; ++day) {
        const auto result = advance(split, 1);
        assert(result.ok());
    }
    assert(batch.tick == split.tick);
    assert(base_checkpoint(batch) == base_checkpoint(split));
    assert(batch.runtime == split.runtime);
}

void test_validation_rejects_invalid_contracts() {
    auto value = spec();
    value.energy_rules.producer_count = 0;
    assert(!validate_m8_spec(value).ok());
    value = spec();
    value.energy_policy.household_subsidy_rate = 1.1;
    assert(!validate_m8_spec(value).ok());
    value = spec();
    value.energy_input.capacity_multiplier = -1.0;
    assert(!validate_m8_spec(value).ok());
}

} // namespace

int main() {
    test_genesis_owns_energy_components();
    test_energy_day_conserves_and_constrains();
    test_priority_rationing_changes_allocation();
    test_fiscal_energy_flows_and_reserve();
    test_all_fallible_boundaries_are_atomic();
    test_batch_and_split_are_exact();
    test_validation_rejects_invalid_contracts();
    return 0;
}
