#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <utility>
#include <vector>

#include "macro_sim/core/transaction.hpp"
#include "macro_sim/simulation/m7_checkpoint.hpp"
#include "macro_sim/simulation/m8.hpp"

namespace {

using macro_sim::Tick;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec spec() {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &real = population.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 5;
    real.capital_firms = 2;
    real.seed = 8080;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
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
        std::cerr << "M8 genesis failed: " << initialization.status().message() << "\n";
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
    result.financial_scratch.reserve(result.root, result.financial_runtime);
    result.population_scratch.reserve(result.population_runtime);
    result.scratch.reserve(result.root, result.runtime);
    return result;
}

[[nodiscard]] macro_sim::Result<M8AdvanceResult>
advance(Harness &harness, std::uint64_t count, const M8AdvanceOptions &options = {}) {
    return advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                            harness.monetary_runtime, harness.monetary_scratch,
                            harness.financial_runtime, harness.financial_scratch,
                            harness.population_runtime, harness.population_scratch,
                            harness.runtime, harness.scratch, harness.tick, count,
                            options);
}

[[nodiscard]] std::vector<std::uint8_t> base_checkpoint(const Harness &harness) {
    auto bytes = save_m7_checkpoint(harness.root, harness.real_runtime,
                                    harness.monetary_runtime, harness.financial_runtime,
                                    harness.population_runtime, harness.tick);
    assert(bytes.ok());
    return *bytes.get_if();
}

void test_genesis_owns_energy_components() {
    auto harness = build();
    std::uint64_t producers = 0;
    harness.root.firms.for_each_alive(
        [&producers](macro_sim::FirmId, const macro_sim::core::FirmComponent &firm) {
            producers += firm.sector == macro_sim::core::FirmSector::energy ? 1U : 0U;
        });
    assert(producers == 2);
    assert(harness.real_runtime.capability_mask ==
           (capability_bit(M4Capability::physical_capital) |
            capability_bit(M4Capability::government)));
    assert(std::count_if(harness.runtime.energy_producers.begin(),
                         harness.runtime.energy_producers.end(),
                         [](const EnergyProducerComponent &producer) {
                             return producer.active;
                         }) == 2);
    assert(std::count_if(
               harness.runtime.energy_inputs.begin(),
               harness.runtime.energy_inputs.end(),
               [](const EnergyInputComponent &input) { return input.active; }) == 7);
    for (const auto &producer : harness.runtime.energy_producers) {
        if (!producer.active) {
            continue;
        }
        const auto *firm = harness.root.firms.get(producer.firm);
        assert(firm != nullptr);
        assert(firm->capital_depreciation ==
               harness.real_runtime.rules.capital_depreciation);
    }
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_energy_day_conserves_and_constrains() {
    auto harness = build();
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M8 energy day failed: " << result.status().message() << "\n";
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
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_firm_exit_transfers_physical_energy_stocks() {
    auto producer_control = build();
    auto producer_exit = build();
    macro_sim::FirmId exiting_producer{};
    for (const auto &producer : producer_exit.runtime.energy_producers) {
        if (producer.active) {
            exiting_producer = producer.firm;
            break;
        }
    }
    assert(exiting_producer.valid());
    M8AdvanceOptions producer_exit_options;
    producer_exit_options.base.base.force_firm_exit = exiting_producer;
    const auto producer_control_result = advance(producer_control, 1);
    const auto producer_exit_result = advance(producer_exit, 1, producer_exit_options);
    assert(producer_control_result.ok());
    assert(producer_exit_result.ok());
    const auto producer_totals = [](const M8Runtime &runtime) {
        double inventory = 0.0;
        double inventory_cost = 0.0;
        for (const auto &producer : runtime.energy_producers) {
            if (producer.active) {
                inventory += producer.inventory;
                inventory_cost += producer.inventory_cost;
            }
        }
        return std::pair{inventory, inventory_cost};
    };
    const auto control_producer_totals = producer_totals(producer_control.runtime);
    const auto exit_producer_totals = producer_totals(producer_exit.runtime);
    assert(std::abs(control_producer_totals.first - exit_producer_totals.first) <
           1.0e-8);
    assert(std::abs(control_producer_totals.second - exit_producer_totals.second) <
           1.0e-8);
    const auto producer_slot = static_cast<std::size_t>(exiting_producer.value());
    assert(!producer_exit.runtime.energy_producers[producer_slot].active);
    assert(producer_exit.runtime.energy_producers[producer_slot].inventory == 0.0);

    auto input_control = build();
    auto input_exit = build();
    macro_sim::FirmId exiting_downstream{};
    for (const auto &input : input_exit.runtime.energy_inputs) {
        if (input.active) {
            exiting_downstream = input.firm;
            break;
        }
    }
    assert(exiting_downstream.valid());
    M8AdvanceOptions input_exit_options;
    input_exit_options.base.base.force_firm_exit = exiting_downstream;
    const auto input_control_result = advance(input_control, 1);
    const auto input_exit_result = advance(input_exit, 1, input_exit_options);
    assert(input_control_result.ok());
    assert(input_exit_result.ok());
    const auto input_totals = [](const M8Runtime &runtime) {
        double stock = 0.0;
        double stock_cost = 0.0;
        for (const auto &input : runtime.energy_inputs) {
            if (input.active) {
                stock += input.stock;
                stock_cost += input.stock_cost;
            }
        }
        return std::pair{stock, stock_cost};
    };
    const auto control_input_totals = input_totals(input_control.runtime);
    const auto exit_input_totals = input_totals(input_exit.runtime);
    assert(std::abs(control_input_totals.first - exit_input_totals.first) < 1.0e-8);
    assert(std::abs(control_input_totals.second - exit_input_totals.second) < 1.0e-8);
    const auto input_slot = static_cast<std::size_t>(exiting_downstream.value());
    assert(!input_exit.runtime.energy_inputs[input_slot].active);
    assert(input_exit.runtime.energy_inputs[input_slot].stock == 0.0);
}

void test_energy_profits_enter_common_income_settlement() {
    auto value = spec();
    value.energy_rules.initial_price = 3.0;
    value.energy_rules.initial_wage = 1.0;
    auto harness = build(value);
    const auto result = advance(harness, 1);
    assert(result.ok());

    double profit = 0.0;
    double profit_tax = 0.0;
    double dividends = 0.0;
    for (std::size_t index = 0; index < harness.real_scratch.firm_ids_.size();
         ++index) {
        const auto *firm =
            harness.root.firms.get(harness.real_scratch.firm_ids_[index]);
        if (firm == nullptr || firm->sector != macro_sim::core::FirmSector::energy) {
            continue;
        }
        const auto &work = harness.real_scratch.firm_work_[index];
        profit += std::max(0.0, work.profit);
        profit_tax += work.profit_tax;
        dividends += work.dividends;
    }
    assert(profit > 0.0);
    assert(profit_tax > 0.0);
    assert(dividends > 0.0);
}

void test_energy_capacity_expands_through_capital_market() {
    auto value = spec();
    auto &real = value.domestic_economy.financial_economy.monetary_economy.real_economy;
    real.rules.initial_capital_inventory = 1'000.0;
    value.energy_rules.initial_producer_cash = 10'000.0;
    auto harness = build(value);
    const auto energy_capital = [&harness]() {
        double total = 0.0;
        harness.root.firms.for_each_alive(
            [&total](macro_sim::FirmId, const macro_sim::core::FirmComponent &firm) {
                if (firm.sector == macro_sim::core::FirmSector::energy) {
                    total += firm.physical_capital.value();
                }
            });
        return total;
    };
    const double opening_capital = energy_capital();
    M8AdvanceOptions demand_growth;
    demand_growth.energy_input = EnergyExogenousInput{
        1.0, 1.0, 1.0, 5.0, 1.0, 1.0,
    };
    const auto result = advance(harness, 30, demand_growth);
    assert(result.ok());
    assert(energy_capital() > opening_capital);
}

void test_affordability_gap_does_not_create_phantom_energy_demand() {
    auto value = spec();
    value.energy_rules.initial_producer_cash = 10'000.0;
    value.energy_rules.initial_price = 1'000'000.0;
    value.energy_rules.demand_adjustment = 0.20;
    auto harness = build(value);
    double opening_expected = 0.0;
    double opening_capital = 0.0;
    for (auto &producer : harness.runtime.energy_producers) {
        if (!producer.active) {
            continue;
        }
        producer.inventory += 1'000.0;
        opening_expected += producer.demand_expected;
        const auto *firm = harness.root.firms.get(producer.firm);
        assert(firm != nullptr);
        opening_capital += firm->physical_capital.value();
    }
    const auto opening_result = advance(harness, 1);
    assert(opening_result.ok());
    assert(opening_result.get_if()->metrics.energy.unfilled > 0.0);
    const auto result = advance(harness, 19);
    assert(result.ok());
    double closing_expected = 0.0;
    double closing_capital = 0.0;
    for (const auto &producer : harness.runtime.energy_producers) {
        if (!producer.active) {
            continue;
        }
        closing_expected += producer.demand_expected;
        const auto *firm = harness.root.firms.get(producer.firm);
        assert(firm != nullptr);
        closing_capital += firm->physical_capital.value();
    }
    assert(closing_expected < opening_expected);
    assert(closing_capital <= opening_capital + 1.0e-8);
}

void test_energy_plan_can_receive_working_capital_credit() {
    auto value = spec();
    value.energy_rules.initial_producer_cash = 0.01;
    value.energy_rules.initial_wage = 0.5;
    auto harness = build(value);
    const auto result = advance(harness, 1);
    assert(result.ok());
    bool energy_borrower = false;
    for (const auto &loan : harness.root.loans.records()) {
        if (!loan.active || loan.borrower.kind() != macro_sim::core::OwnerKind::firm) {
            continue;
        }
        const auto *firm =
            harness.root.firms.get(macro_sim::FirmId(loan.borrower.value()));
        energy_borrower =
            energy_borrower ||
            (firm != nullptr && firm->sector == macro_sim::core::FirmSector::energy &&
             loan.principal.value() > 0.0);
    }
    assert(energy_borrower);
    assert(result.get_if()->metrics.energy.production > 0.0);
}

void test_settlement_dust_cannot_buy_energy() {
    auto value = spec();
    auto &real = value.domestic_economy.financial_economy.monetary_economy.real_economy;
    real.rules.government_consumption_share = 0.0;
    real.rules.government_investment_share = 0.0;
    real.rules.income_propensity = 0.0;
    real.rules.wealth_propensity = 0.0;
    real.rules.investment_adjustment = 0.0;
    value.energy_rules.household_energy = false;
    value.energy_policy.rationing = EnergyRationing::industry_first;
    auto harness = build(value);

    const auto target = std::min_element(
        harness.runtime.energy_inputs.begin(), harness.runtime.energy_inputs.end(),
        [](const EnergyInputComponent &left, const EnergyInputComponent &right) {
            if (left.active != right.active) {
                return left.active;
            }
            return left.firm < right.firm;
        });
    assert(target != harness.runtime.energy_inputs.end());
    assert(target->active);
    const auto *firm = harness.root.firms.get(target->firm);
    assert(firm != nullptr);
    auto *account = harness.root.postings.get(firm->primary_account);
    assert(account != nullptr);
    constexpr double dust = 2.0e-12;
    const double transfer_amount = account->balance.value() - dust;
    assert(transfer_amount > 0.0);
    {
        macro_sim::core::SettlementTransaction transaction(harness.root);
        assert(transaction
                   .transfer(firm->primary_account,
                             harness.root.institutions.treasury_account,
                             macro_sim::Money(transfer_amount))
                   .ok());
        assert(transaction.commit().ok());
    }

    M8AdvanceOptions options;
    options.base.base.base.credit_supply_multiplier = 0.0;
    const auto result = advance(harness, 1, options);
    assert(result.ok());
    const auto closing = std::find_if(
        harness.runtime.energy_inputs.begin(), harness.runtime.energy_inputs.end(),
        [firm_id = target->firm](const EnergyInputComponent &input) {
            return input.firm == firm_id;
        });
    assert(closing != harness.runtime.energy_inputs.end());
    assert(closing->bought == 0.0);
}

void test_labor_search_order_does_not_starve_late_sectors() {
    std::uint32_t producing_seeds = 0;
    for (std::uint64_t seed = 1; seed <= 12; ++seed) {
        auto value = spec();
        auto &population = value.domestic_economy;
        auto &real = population.financial_economy.monetary_economy.real_economy;
        real.seed = seed;
        real.consumption_firms = 1;
        real.capital_firms = 1;
        real.rules.initial_firm_money = 10'000.0;
        real.rules.initial_expected_demand = 1'000.0;
        population.population.initial_persons = 100;
        value.energy_rules.producer_count = 1;
        value.energy_rules.initial_producer_cash = 10'000.0;
        auto harness = build(value);
        const auto result = advance(harness, 1);
        assert(result.ok());
        producing_seeds += result.get_if()->metrics.energy.production > 0.0 ? 1U : 0U;
    }
    assert(producing_seeds > 0U);
}

void test_priority_rationing_changes_allocation() {
    auto household_first_spec = spec();
    household_first_spec.energy_rules.producer_inventory_ratio = 0.0;
    household_first_spec.energy_policy.rationing = EnergyRationing::household_first;
    auto industry_first_spec = household_first_spec;
    industry_first_spec.energy_policy.rationing = EnergyRationing::industry_first;
    auto households = build(household_first_spec);
    auto industry = build(industry_first_spec);
    M8AdvanceOptions constrained;
    constrained.energy_input = EnergyExogenousInput{
        0.05, 1.0, 1.0, 1.0, 1.0, 1.0,
    };
    const auto household_result = advance(households, 1, constrained);
    const auto industry_result = advance(industry, 1, constrained);
    assert(household_result.ok());
    assert(industry_result.ok());
    assert(household_result.get_if()->metrics.energy.household_units >
           industry_result.get_if()->metrics.energy.household_units);
    assert(std::accumulate(households.runtime.energy_inputs.begin(),
                           households.runtime.energy_inputs.end(), 0.0,
                           [](double total, const EnergyInputComponent &input) {
                               return total + (input.active ? input.bought : 0.0);
                           }) <
           std::accumulate(industry.runtime.energy_inputs.begin(),
                           industry.runtime.energy_inputs.end(), 0.0,
                           [](double total, const EnergyInputComponent &input) {
                               return total + (input.active ? input.bought : 0.0);
                           }));
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
    const auto &fiscal = result.get_if()->metrics.economy.economy.economy.economy;
    assert(energy.excise_paid > 0.0);
    assert(energy.subsidy_paid > 0.0);
    assert(energy.cap_compensation > 0.0);
    assert(energy.strategic_reserve_flow > 0.0);
    assert(energy.strategic_reserve_stock > 0.0);
    assert(fiscal.tax_total + 1.0e-8 >= energy.excise_paid);
    assert(fiscal.transfer_payments + 1.0e-8 >=
           energy.subsidy_paid + energy.cap_compensation);
    assert(fiscal.government_consumption + 1.0e-8 >=
           energy.strategic_reserve_purchase_paid);

    harness.runtime.energy_policy.strategic_reserve_target = 0.0;
    result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.energy.strategic_reserve_flow < 0.0);
    assert(result.get_if()->metrics.energy.strategic_reserve_sale_revenue > 0.0);
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
    test_firm_exit_transfers_physical_energy_stocks();
    test_energy_profits_enter_common_income_settlement();
    test_energy_capacity_expands_through_capital_market();
    test_affordability_gap_does_not_create_phantom_energy_demand();
    test_energy_plan_can_receive_working_capital_credit();
    test_settlement_dust_cannot_buy_energy();
    test_labor_search_order_does_not_starve_late_sectors();
    test_priority_rationing_changes_allocation();
    test_fiscal_energy_flows_and_reserve();
    test_all_fallible_boundaries_are_atomic();
    test_batch_and_split_are_exact();
    test_validation_rejects_invalid_contracts();
    return 0;
}
