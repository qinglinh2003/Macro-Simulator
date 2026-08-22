#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m8_checkpoint.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec domestic_spec(std::uint64_t seed = 9001U,
                                             double wage = 1.5, double rate = 0.01) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 20;
    real.consumption_firms = 4;
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

[[nodiscard]] M9World build_world(std::size_t count, WorldRules rules = {}) {
    M9WorldSpec spec;
    spec.rules = rules;
    for (std::size_t index = 0; index < count; ++index) {
        auto economy = domestic_spec(9001U + static_cast<std::uint64_t>(index),
                                     1.0 + static_cast<double>(index), 0.01);
        auto &real =
            economy.domestic_economy.financial_economy.monetary_economy.real_economy;
        real.market_protocol = algorithms::MatchingProtocol::price_sorted;
        real.rules.initial_price = index == 0U ? 2.0 : 1.0;
        real.rules.initial_consumption_inventory = 1.0;
        spec.economies.push_back(std::move(economy));
    }
    spec.external_policies.resize(count);
    auto result = M9World::create(spec);
    if (!result.ok()) {
        std::cerr << "M9 World genesis failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    return std::move(*result.get_if());
}

void test_single_country_is_an_inert_m8_container() {
    auto standalone_spec = domestic_spec(9001U, 1.0, 0.01);
    auto &standalone_real = standalone_spec.domestic_economy.financial_economy
                                .monetary_economy.real_economy;
    standalone_real.economy = EconomyId(0);
    standalone_real.currency = CurrencyId(0);
    standalone_real.market_protocol = algorithms::MatchingProtocol::price_sorted;
    standalone_real.rules.initial_price = 2.0;
    standalone_real.rules.initial_consumption_inventory = 1.0;
    auto initialized = build_m8_genesis(standalone_spec);
    assert(initialized.ok());
    auto state = std::move(*initialized.get_if());
    M4TickScratch real_scratch;
    M5TickScratch monetary_scratch;
    M6TickScratch financial_scratch;
    M7TickScratch population_scratch;
    M8TickScratch domestic_scratch;
    Tick standalone_tick{};
    real_scratch.reserve(state.root);
    monetary_scratch.reserve(state.root);
    financial_scratch.reserve(state.root, state.financial_runtime);
    population_scratch.reserve(state.population_runtime);
    domestic_scratch.reserve(state.root, state.runtime);

    auto world = build_world(1);
    assert(world.economy_root(EconomyId(0)) != nullptr);
    assert(world.economy_financial_runtime(EconomyId(0)) != nullptr);
    assert(world.economy_population_runtime(EconomyId(0)) != nullptr);
    assert(world.economy_runtime(EconomyId(0)) != nullptr);
    assert(world.economy_root(EconomyId(1)) == nullptr);
    assert(world.economy_financial_runtime(EconomyId(1)) == nullptr);
    assert(world.economy_population_runtime(EconomyId(1)) == nullptr);
    assert(world.economy_runtime(EconomyId(1)) == nullptr);
    const auto result = world.advance(3);
    if (!result.ok()) {
        std::cerr << "M9 single-country advance failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(world.tick() == Tick(3));
    assert(result.get_if()->metrics.domestic.size() == 1U);
    assert(result.get_if()->metrics.external.size() == 1U);
    assert(result.get_if()->metrics.trade_routes == 0U);
    assert(result.get_if()->metrics.migration_routes == 0U);
    assert(std::abs(world.rates().rate(EconomyId(0)) - 1.0) < 1.0e-12);
    const auto standalone = advance_m8_ticks(
        state.root, state.real_economy_runtime, real_scratch, state.monetary_runtime,
        monetary_scratch, state.financial_runtime, financial_scratch,
        state.population_runtime, population_scratch, state.runtime, domestic_scratch,
        standalone_tick, 3U);
    assert(standalone.ok());
    const auto standalone_checkpoint =
        save_m8_checkpoint(state.root, state.real_economy_runtime,
                           state.monetary_runtime, state.financial_runtime,
                           state.population_runtime, state.runtime, standalone_tick);
    const auto world_checkpoint = world.economy_checkpoint(EconomyId(0));
    assert(standalone_checkpoint.ok());
    assert(world_checkpoint.ok());
    assert(*standalone_checkpoint.get_if() == *world_checkpoint.get_if());
    assert(!world.economy_checkpoint(EconomyId(1)).ok());
    assert(world.validate().ok());
}

void test_closed_single_country_fast_path_matches_staged_world() {
    auto fast = build_world(1);
    auto staged = build_world(1);
    ShockSpec future;
    future.id = 77U;
    future.kind = ShockKind::household_demand;
    future.economy = EconomyId(0U);
    future.start = Tick(100U);
    future.announcement = Tick(100U);
    future.duration = 1U;
    future.magnitude = 0.25;
    assert(staged.schedule_shock(future).ok());

    const auto fast_result = fast.advance(5U);
    const auto staged_result = staged.advance(5U);
    assert(fast_result.ok());
    assert(staged_result.ok());
    assert(fast_result.get_if()->metrics == staged_result.get_if()->metrics);
    assert(fast.digest() == staged.digest());
    const auto fast_economy = fast.economy_checkpoint(EconomyId(0U));
    const auto staged_economy = staged.economy_checkpoint(EconomyId(0U));
    assert(fast_economy.ok());
    assert(staged_economy.ok());
    assert(*fast_economy.get_if() == *staged_economy.get_if());
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
    assert(std::abs(world.rates().log_rates[0] + world.rates().log_rates[1]) < 1.0e-12);
    const auto digest = world.digest();

    auto replay = build_world(2, rules);
    assert(replay.update_external_policies(policies).ok());
    assert(replay.advance(1).ok());
    assert(replay.digest() == digest);
}

void test_no_shock_open_world_fx_remains_bounded() {
    WorldRules rules;
    rules.trade = true;
    rules.capital = true;
    rules.migration = true;
    rules.fx_trade_cap = 0.15;
    rules.fx_adjustment = 0.05;
    rules.capital_mobility = 1.0;
    rules.capital_adjustment = 0.2;
    rules.migration_rate = 0.02;
    rules.migration_max_share = 0.25;
    rules.remittance_share = 0.2;
    rules.wage_smoothing = 0.02;
    auto world = build_world(3, rules);

    const auto result = world.advance(730U);
    assert(result.ok());
    for (std::size_t index = 0; index < 3U; ++index) {
        const auto rate =
            world.rates().rate(EconomyId(static_cast<std::uint64_t>(index)));
        assert(std::isfinite(rate));
        assert(rate > 0.1);
        assert(rate < 10.0);
    }
    assert(std::isfinite(result.get_if()->metrics.dealer_valuation));
    assert(std::isfinite(result.get_if()->metrics.world_nfa));
    assert(world.validate().ok());
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
    const auto opening_checkpoint = world.checkpoint();
    assert(opening_checkpoint.ok());
    M9AdvanceOptions options;
    options.fault_point = M9FaultPoint::after_trade_reservation;
    const auto failed = world.advance(1, options);
    assert(!failed.ok());
    assert(world.tick() == Tick(0));
    assert(world.digest() == opening_digest);
    assert(*world.checkpoint().get_if() == *opening_checkpoint.get_if());

    options.fault_point = M9FaultPoint::after_domestic_advance;
    const auto failed_domestic = world.advance(1, options);
    assert(!failed_domestic.ok());
    assert(world.tick() == Tick(0));
    assert(*world.checkpoint().get_if() == *opening_checkpoint.get_if());

    options.fault_point = M9FaultPoint::before_world_commit;
    const auto failed_late = world.advance(1, options);
    assert(!failed_late.ok());
    assert(world.tick() == Tick(0));
    assert(world.digest() == opening_digest);
    assert(*world.checkpoint().get_if() == *opening_checkpoint.get_if());
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
    shock.magnitude = 0.5;
    assert(world.schedule_shock(shock).ok());
    assert(!world.schedule_shock(shock).ok());
    const auto result = world.advance(1);
    assert(result.ok());
    assert(result.get_if()->metrics.external[0].active_shocks > 0U);
}

[[nodiscard]] ShockSpec adverse_shock(std::uint64_t id, ShockKind kind,
                                      double magnitude = 0.5) {
    ShockSpec shock;
    shock.id = id;
    shock.kind = kind;
    shock.economy = EconomyId(0);
    shock.start = Tick(0);
    shock.duration = 1U;
    shock.magnitude = magnitude;
    return shock;
}

void test_all_eight_shock_channels_reach_their_native_seams() {
    auto baseline = build_world(1);
    const auto baseline_result = baseline.advance(1);
    assert(baseline_result.ok());
    const auto &base = baseline_result.get_if()->metrics.domestic[0];

    auto productivity = build_world(1);
    assert(
        productivity.schedule_shock(adverse_shock(101U, ShockKind::productivity)).ok());
    const auto productivity_result = productivity.advance(1);
    assert(productivity_result.ok());
    assert(productivity_result.get_if()
               ->metrics.domestic[0]
               .economy.economy.economy.economy.real_output <
           base.economy.economy.economy.economy.real_output);

    auto labor = build_world(1);
    assert(
        labor.schedule_shock(adverse_shock(102U, ShockKind::labor_availability)).ok());
    const auto labor_result = labor.advance(1);
    assert(labor_result.ok());
    assert(labor_result.get_if()
               ->metrics.domestic[0]
               .economy.economy.economy.economy.real_output <
           base.economy.economy.economy.economy.real_output);

    auto energy = build_world(1);
    assert(energy.schedule_shock(adverse_shock(103U, ShockKind::energy_capacity)).ok());
    const auto energy_result = energy.advance(1);
    assert(energy_result.ok());
    assert(energy_result.get_if()->metrics.domestic[0].energy.capacity <
           base.energy.capacity);

    auto demand = build_world(1);
    assert(
        demand.schedule_shock(adverse_shock(104U, ShockKind::household_demand)).ok());
    const auto demand_result = demand.advance(1);
    assert(demand_result.ok());
    assert(demand_result.get_if()
               ->metrics.domestic[0]
               .economy.economy.economy.economy.household_consumption <
           base.economy.economy.economy.economy.household_consumption);

    auto credit_spec = domestic_spec();
    auto &credit_real =
        credit_spec.domestic_economy.financial_economy.monetary_economy.real_economy;
    credit_real.rules.initial_firm_money = 1.0;
    credit_real.rules.initial_expected_demand = 10'000.0;
    credit_spec.domestic_economy.financial_economy.monetary_economy.rules
        .opening_capital_per_bank = 5.0;
    const auto build_credit_world = [&]() {
        M9WorldSpec spec;
        spec.economies.push_back(credit_spec);
        spec.external_policies.resize(1);
        auto result = M9World::create(spec);
        assert(result.ok());
        return std::move(*result.get_if());
    };
    auto credit_baseline = build_credit_world();
    const auto credit_baseline_result = credit_baseline.advance(1);
    assert(credit_baseline_result.ok());
    const double baseline_credit = credit_baseline_result.get_if()
                                       ->metrics.domestic[0]
                                       .economy.economy.economy.new_credit;
    assert(baseline_credit > 0.0);
    auto credit = build_credit_world();
    assert(credit.schedule_shock(adverse_shock(105U, ShockKind::credit_supply, 0.99))
               .ok());
    const auto credit_result = credit.advance(1);
    assert(credit_result.ok());
    assert(
        credit_result.get_if()->metrics.domestic[0].economy.economy.economy.new_credit <
        baseline_credit);

    auto destruction = build_world(1);
    auto destruction_shock = adverse_shock(106U, ShockKind::capital_destruction, 0.25);
    assert(destruction.schedule_shock(destruction_shock).ok());
    const auto destruction_result = destruction.advance(1);
    assert(destruction_result.ok());
    assert(destruction_result.get_if()->metrics.external[0].capital_destroyed > 0.0);
    const double first_loss =
        destruction_result.get_if()->metrics.external[0].capital_destroyed;
    const auto after = destruction.advance(1);
    assert(after.ok());
    assert(after.get_if()->metrics.external[0].capital_destroyed == 0.0);
    assert(first_loss > 0.0);

    WorldRules trade_rules;
    trade_rules.trade = true;
    trade_rules.fx_trade_cap = 1.0;
    auto trade_baseline = build_world(2, trade_rules);
    const auto trade_baseline_result = trade_baseline.advance(1);
    assert(trade_baseline_result.ok());
    const double baseline_imports =
        trade_baseline_result.get_if()->metrics.external[0].imports_volume;
    assert(baseline_imports > 0.0);

    auto imports = build_world(2, trade_rules);
    assert(imports.schedule_shock(adverse_shock(107U, ShockKind::import_capacity, 0.99))
               .ok());
    const auto import_result = imports.advance(1);
    assert(import_result.ok());
    assert(import_result.get_if()->metrics.external[0].imports_volume <
           baseline_imports);

    auto exports = build_world(2, trade_rules);
    auto export_shock = adverse_shock(108U, ShockKind::export_capacity, 0.99);
    export_shock.economy = EconomyId(1);
    assert(exports.schedule_shock(export_shock).ok());
    const auto export_result = exports.advance(1);
    assert(export_result.ok());
    assert(export_result.get_if()->metrics.external[0].imports_volume <
           baseline_imports);

    auto invalid_sector = adverse_shock(109U, ShockKind::credit_supply);
    invalid_sector.sector = ShockSector::capital;
    assert(!baseline.schedule_shock(invalid_sector).ok());
    auto invalid_one_shot = adverse_shock(110U, ShockKind::capital_destruction);
    invalid_one_shot.duration = 2U;
    assert(!baseline.schedule_shock(invalid_one_shot).ok());
    auto invalid_end = adverse_shock(111U, ShockKind::productivity);
    invalid_end.start = Tick(std::numeric_limits<std::uint64_t>::max());
    assert(!baseline.schedule_shock(invalid_end).ok());
    auto invalid_ramps = adverse_shock(112U, ShockKind::productivity);
    invalid_ramps.duration = 2U;
    invalid_ramps.ramp_in_ticks = std::numeric_limits<std::uint64_t>::max();
    invalid_ramps.ramp_out_ticks = 2U;
    assert(!baseline.schedule_shock(invalid_ramps).ok());
}

void test_household_demand_shock_survives_lifecycle_budget_projection() {
    const auto build_lifecycle_world = []() {
        auto economy = domestic_spec();
        economy.domestic_economy.rules.lifecycle_consumption = true;
        M9WorldSpec spec;
        spec.economies.push_back(std::move(economy));
        spec.external_policies.resize(1U);
        auto result = M9World::create(spec);
        assert(result.ok());
        return std::move(*result.get_if());
    };

    auto baseline = build_lifecycle_world();
    const auto baseline_result = baseline.advance(1U);
    assert(baseline_result.ok());

    auto treatment = build_lifecycle_world();
    assert(treatment
               .schedule_shock(
                   adverse_shock(109U, ShockKind::household_demand, 0.50))
               .ok());
    const auto treatment_result = treatment.advance(1U);
    assert(treatment_result.ok());
    assert(treatment_result.get_if()
               ->metrics.domestic[0]
               .economy.economy.economy.economy.household_consumption_budget <
           baseline_result.get_if()
               ->metrics.domestic[0]
               .economy.economy.economy.economy.household_consumption_budget);
}

void test_shock_lifecycle_events_are_ordered_and_checkpointed() {
    auto world = build_world(1);
    auto continuous = adverse_shock(201U, ShockKind::household_demand, 0.2);
    continuous.start = Tick(2);
    continuous.announcement = Tick(1);
    continuous.duration = 2U;
    assert(world.schedule_shock(continuous).ok());
    auto one_shot = adverse_shock(202U, ShockKind::capital_destruction, 0.1);
    one_shot.start = Tick(2);
    one_shot.announcement = Tick(1);
    assert(world.schedule_shock(one_shot).ok());

    assert(world.advance(1).ok());
    assert(world.shock_events().empty());
    const auto announced = world.advance(1);
    assert(announced.ok());
    assert(announced.get_if()->metrics.shock_events == 2U);
    assert(world.shock_events().size() == 2U);
    assert(world.shock_events()[0].type == ShockEventType::announced);
    assert(world.shock_events()[0].shock_id == 201U);
    assert(world.shock_events()[1].type == ShockEventType::announced);
    assert(world.shock_events()[1].shock_id == 202U);

    const auto started = world.advance(1);
    assert(started.ok());
    assert(started.get_if()->metrics.shock_events == 2U);
    assert(world.shock_events()[2].type == ShockEventType::started);
    assert(world.shock_events()[2].shock_id == 201U);
    assert(world.shock_events()[3].type == ShockEventType::realized);
    assert(world.shock_events()[3].shock_id == 202U);

    auto checkpoint = world.checkpoint();
    assert(checkpoint.ok());
    auto restored = M9World::restore(*checkpoint.get_if());
    assert(restored.ok());
    assert(restored.get_if()->shock_events() == world.shock_events());

    assert(world.advance(2).ok());
    assert(restored.get_if()->advance(2).ok());
    assert(world.shock_events().back().type == ShockEventType::ended);
    assert(world.shock_events().back().shock_id == 201U);
    assert(restored.get_if()->shock_events() == world.shock_events());
}

void test_packaged_crisis_scenarios_match_the_native_shock_contract() {
    CrisisScenarioOptions options;
    options.start = Tick(50);
    options.announcement_lead_ticks = 5U;
    options.first_shock_id = 1000U;

    const auto oil = make_crisis_scenario(CrisisScenario::oil_embargo, options, 3U);
    assert(oil.ok());
    assert(oil.get_if()->size() == 2U);
    assert((*oil.get_if())[0].kind == ShockKind::energy_capacity);
    assert((*oil.get_if())[0].sector == ShockSector::energy);
    assert((*oil.get_if())[0].duration == 180U);
    assert((*oil.get_if())[0].announcement == Tick(45));
    assert((*oil.get_if())[1].kind == ShockKind::import_capacity);

    const auto gfc =
        make_crisis_scenario(CrisisScenario::global_financial_crisis, options, 3U);
    assert(gfc.ok());
    assert(gfc.get_if()->size() == 3U);
    assert((*gfc.get_if())[0].kind == ShockKind::credit_supply);
    assert((*gfc.get_if())[0].ramp_out_ticks == 90U);

    options.include_trade = false;
    const auto pandemic = make_crisis_scenario(CrisisScenario::pandemic, options, 3U);
    assert(pandemic.ok());
    assert(pandemic.get_if()->size() == 4U);
    assert((*pandemic.get_if())[3].kind == ShockKind::credit_supply);

    options.economies = {EconomyId(0), EconomyId(2)};
    options.duration = 60U;
    const auto disaster =
        make_crisis_scenario(CrisisScenario::natural_disaster, options, 3U);
    assert(disaster.ok());
    assert(disaster.get_if()->size() == 6U);
    assert((*disaster.get_if())[0].kind == ShockKind::capital_destruction);
    assert((*disaster.get_if())[0].duration == 1U);
    assert((*disaster.get_if())[1].economy == EconomyId(2));
    assert((*disaster.get_if())[2].kind == ShockKind::productivity);
    assert((*disaster.get_if())[2].ramp_out_ticks == 30U);

    options.economies = {EconomyId(3)};
    assert(!make_crisis_scenario(CrisisScenario::pandemic, options, 3U).ok());
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

void test_dealer_loss_mutualization_posts_an_explicit_fiscal_levy() {
    WorldRules rules;
    rules.trade = true;
    rules.fx_trade_cap = 0.50;
    rules.fx_adjustment = 0.50;
    rules.fx_loss_mutualization = true;
    rules.periods_per_year = 1.0;
    auto world = build_world(2, rules);

    const auto opening = world.advance(1);
    assert(opening.ok());
    const auto settlement = world.advance(1);
    assert(settlement.ok());
    const auto &external = settlement.get_if()->metrics.external;
    const double paid = external[0].fx_mutualization_paid +
                        external[1].fx_mutualization_paid;
    assert(paid > 0.0);
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
        std::cerr << "M9 checkpoint restore failed: " << restored.status().message()
                  << "\n";
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

void test_worker_count_does_not_change_semantics() {
    WorldRules rules;
    rules.trade = true;
    rules.capital = true;
    rules.migration = true;
    rules.capital_mobility = 0.2;
    rules.migration_rate = 0.02;
    rules.wage_smoothing = 1.0;
    auto serial = build_world(4, rules);
    auto parallel = build_world(4, rules);
    M9AdvanceOptions serial_options;
    serial_options.worker_count = 1U;
    serial_options.require_world_rollback = true;
    M9AdvanceOptions parallel_options;
    parallel_options.worker_count = 8U;
    assert(serial.advance(6, serial_options).ok());
    assert(parallel.advance(6, parallel_options).ok());
    assert(serial.digest() == parallel.digest());
    auto serial_checkpoint = serial.checkpoint();
    auto parallel_checkpoint = parallel.checkpoint();
    assert(serial_checkpoint.ok());
    assert(parallel_checkpoint.ok());
    assert(*serial_checkpoint.get_if() == *parallel_checkpoint.get_if());
}

} // namespace

int main() {
    test_single_country_is_an_inert_m8_container();
    test_closed_single_country_fast_path_matches_staged_world();
    test_trade_fx_and_tariff_clear_deterministically();
    test_no_shock_open_world_fx_remains_bounded();
    test_unilateral_sanction_has_symmetric_effect();
    test_faults_leave_the_complete_old_world();
    test_policy_peg_and_shock_contracts();
    test_all_eight_shock_channels_reach_their_native_seams();
    test_household_demand_shock_survives_lifecycle_budget_projection();
    test_shock_lifecycle_events_are_ordered_and_checkpointed();
    test_packaged_crisis_scenarios_match_the_native_shock_contract();
    test_capital_and_migration_paths_are_live();
    test_dealer_loss_mutualization_posts_an_explicit_fiscal_levy();
    test_checkpoint_round_trip_and_continuation_are_exact();
    test_worker_count_does_not_change_semantics();
    std::cout << "M9 World tests passed\n";
    return 0;
}
