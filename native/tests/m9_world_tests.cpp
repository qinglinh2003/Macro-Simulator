#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m9.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec domestic_spec(std::uint64_t seed = 9001U,
                                             double wage = 1.5,
                                             double rate = 0.01) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 20;
    real.consumption_firms = 4;
    real.capital_firms = 1;
    real.seed = seed;
    real.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
        capability_bit(M4Capability::government);
    real.rules.initial_household_money = 100.0;
    real.rules.initial_firm_money = 40.0;
    real.rules.initial_consumption_inventory = 20.0;
    real.rules.initial_capital_inventory = 5.0;
    real.rules.initial_consumption_capital = 8.0;
    real.rules.initial_wage = wage;
    real.rules.initial_price = 1.2;
    real.rules.government_deficit_target = 0.0;
    monetary.initial_policy_rate = rate;
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 40;
    population.population.target_household_size = 2.0;
    population.population.start_calendar_day = 20'000;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.producer_count = 1;
    value.energy_rules.initial_producer_cash = 50.0;
    value.energy_rules.initial_wage = wage;
    value.housing_rules.enabled = false;
    return value;
}

[[nodiscard]] M9World build_world(std::size_t count,
                                  WorldRules rules = {}) {
    M9WorldSpec spec;
    spec.rules = rules;
    for (std::size_t index = 0; index < count; ++index) {
        spec.economies.push_back(
            domestic_spec(9001U + static_cast<std::uint64_t>(index),
                          1.0 + static_cast<double>(index), 0.01));
    }
    spec.external_policies.resize(count);
    auto result = M9World::create(spec);
    if (!result.ok()) {
        std::cerr << "M9 World genesis failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    return std::move(*result.get_if());
}

void test_single_country_is_an_inert_m8_container() {
    auto world = build_world(1);
    const auto result = world.advance(3);
    if (!result.ok()) {
        std::cerr << "M9 single-country advance failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(world.tick() == Tick(3));
    assert(result.get_if()->metrics.domestic.size() == 1U);
    assert(result.get_if()->metrics.external.size() == 1U);
    assert(result.get_if()->metrics.trade_routes == 0U);
    assert(result.get_if()->metrics.migration_routes == 0U);
    assert(std::abs(world.rates().rate(EconomyId(0)) - 1.0) < 1.0e-12);
    assert(world.validate().ok());
}

void test_trade_fx_and_tariff_clear_deterministically() {
    WorldRules rules;
    rules.trade = true;
    rules.fx_trade_cap = 0.5;
    rules.fx_adjustment = 0.1;
    auto world = build_world(2, rules);
    auto policies = world.external_policies();
    policies[0].tariff = 0.2;
    assert(world.update_external_policies(policies).ok());
    const auto first = world.advance(1);
    assert(first.ok());
    assert(first.get_if()->metrics.trade_routes > 0U);
    const auto &external = first.get_if()->metrics.external;
    assert(external[0].imports_value > 0.0);
    assert(external[0].tariff_revenue > 0.0);
    assert(external[1].exports_value > 0.0);
    assert(external[1].exports_volume >= external[1].iceberg_loss);
    assert(std::abs(world.rates().log_rates[0] +
                    world.rates().log_rates[1]) < 1.0e-12);
    const auto digest = world.digest();

    auto replay = build_world(2, rules);
    assert(replay.update_external_policies(policies).ok());
    assert(replay.advance(1).ok());
    assert(replay.digest() == digest);
}

void test_unilateral_sanction_has_symmetric_effect() {
    WorldRules rules;
    rules.trade = true;
    rules.fx_trade_cap = 0.5;
    auto world = build_world(2, rules);
    auto policies = world.external_policies();
    policies[0].sanctions_imposed_on = {EconomyId(1)};
    assert(world.update_external_policies(policies).ok());
    const auto result = world.advance(1);
    assert(result.ok());
    assert(result.get_if()->metrics.trade_routes == 0U);
    assert(result.get_if()->metrics.external[0].imports_value == 0.0);
    assert(result.get_if()->metrics.external[1].imports_value == 0.0);
}

void test_faults_leave_the_complete_old_world() {
    WorldRules rules;
    rules.trade = true;
    auto world = build_world(2, rules);
    const auto opening_digest = world.digest();
    M9AdvanceOptions options;
    options.fault_point = M9FaultPoint::after_trade_reservation;
    const auto failed = world.advance(1, options);
    assert(!failed.ok());
    assert(world.tick() == Tick(0));
    assert(world.digest() == opening_digest);

    options.fault_point = M9FaultPoint::before_world_commit;
    const auto failed_late = world.advance(1, options);
    assert(!failed_late.ok());
    assert(world.tick() == Tick(0));
    assert(world.digest() == opening_digest);
}

void test_policy_peg_and_shock_contracts() {
    WorldRules rules;
    rules.trade = true;
    auto world = build_world(2, rules);
    auto policies = world.external_policies();
    policies[0].fx_regime = FxRegime::peg;
    policies[0].peg_anchor = EconomyId(1);
    assert(world.update_external_policies(policies).ok());
    assert(world.pegs().size() == 1U);
    assert(world.pegs()[0].pegger == EconomyId(0));

    auto invalid = policies;
    invalid[1].fx_regime = FxRegime::peg;
    invalid[1].peg_anchor = EconomyId(0);
    assert(!world.update_external_policies(invalid).ok());

    ShockSpec shock;
    shock.id = 91U;
    shock.kind = ShockKind::energy_capacity;
    shock.economy = EconomyId(0);
    shock.start = Tick(0);
    shock.duration = 2U;
    shock.magnitude = -0.5;
    assert(world.schedule_shock(shock).ok());
    assert(!world.schedule_shock(shock).ok());
    const auto result = world.advance(1);
    assert(result.ok());
    assert(result.get_if()->metrics.external[0].active_shocks > 0U);
}

void test_capital_and_migration_paths_are_live() {
    WorldRules rules;
    rules.trade = true;
    rules.capital = true;
    rules.migration = true;
    rules.capital_mobility = 0.8;
    rules.capital_adjustment = 0.5;
    rules.migration_rate = 0.1;
    rules.wage_smoothing = 1.0;
    auto world = build_world(2, rules);
    const auto result = world.advance(3);
    assert(result.ok());
    const auto &external = result.get_if()->metrics.external;
    assert(external[0].migrant_stock_abroad > 0.0 ||
           external[1].migrant_stock_abroad > 0.0);
    assert(result.get_if()->metrics.migration_routes > 0U);
    assert(world.validate().ok());
}

void test_checkpoint_round_trip_and_continuation_are_exact() {
    WorldRules rules;
    rules.trade = true;
    rules.capital = true;
    rules.migration = true;
    rules.capital_mobility = 0.4;
    rules.migration_rate = 0.05;
    rules.wage_smoothing = 1.0;
    auto world = build_world(2, rules);
    assert(world.advance(4).ok());
    auto bytes = world.checkpoint();
    assert(bytes.ok());
    auto restored = M9World::restore(*bytes.get_if());
    if (!restored.ok()) {
        std::cerr << "M9 checkpoint restore failed: "
                  << restored.status().message() << "\n";
    }
    assert(restored.ok());
    auto round_trip = restored.get_if()->checkpoint();
    assert(round_trip.ok());
    assert(*round_trip.get_if() == *bytes.get_if());
    assert(restored.get_if()->digest() == world.digest());

    assert(world.advance(5).ok());
    assert(restored.get_if()->advance(5).ok());
    auto original_end = world.checkpoint();
    auto restored_end = restored.get_if()->checkpoint();
    assert(original_end.ok());
    assert(restored_end.ok());
    assert(*original_end.get_if() == *restored_end.get_if());

    auto corrupted = *bytes.get_if();
    corrupted[corrupted.size() / 2U] ^= 0x5aU;
    assert(!M9World::restore(corrupted).ok());
}

} // namespace

int main() {
    test_single_country_is_an_inert_m8_container();
    test_trade_fx_and_tariff_clear_deterministically();
    test_unilateral_sanction_has_symmetric_effect();
    test_faults_leave_the_complete_old_world();
    test_policy_peg_and_shock_contracts();
    test_capital_and_migration_paths_are_live();
    test_checkpoint_round_trip_and_continuation_are_exact();
    std::cout << "M9 World tests passed\n";
    return 0;
}
