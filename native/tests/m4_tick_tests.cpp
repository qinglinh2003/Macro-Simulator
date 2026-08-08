#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <utility>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/invariants.hpp"
#include "macro_sim/engine_session.hpp"
#include "macro_sim/simulation/m4.hpp"
#include "macro_sim/simulation/m4_checkpoint.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::simulation;

[[nodiscard]] M4SimulationSpec v0_spec(std::uint64_t seed = 206) {
    M4SimulationSpec spec;
    spec.vertical = M4Vertical::cash_loop;
    spec.households = 20;
    spec.consumption_firms = 4;
    spec.seed = seed;
    spec.market_protocol = algorithms::MatchingProtocol::price_sorted;
    return spec;
}

[[nodiscard]] M4SimulationSpec v1_spec(std::uint64_t seed = 206) {
    auto spec = v0_spec(seed);
    spec.vertical = M4Vertical::capital_fiscal;
    spec.capital_firms = 2;
    spec.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    return spec;
}

void assert_close(double left, double right, double tolerance = 1.0e-8) {
    if (std::abs(left - right) > tolerance) {
        std::fprintf(stderr, "assert_close failed: left=%.17g right=%.17g tolerance=%.17g\n",
                     left, right, tolerance);
    }
    assert(std::abs(left - right) <= tolerance);
}

void test_capability_boundary() {
    auto spec = v0_spec();
    spec.requested_capabilities = capability_bit(M4Capability::housing);
    const auto invalid = build_m4_genesis(spec);
    assert(!invalid.ok());
    assert(invalid.status().code() == ErrorCode::unsupported);

    spec = v1_spec();
    spec.requested_capabilities |= capability_bit(M4Capability::commercial_banks);
    const auto future = build_m4_genesis(spec);
    assert(!future.ok());
    assert(future.status().code() == ErrorCode::unsupported);
}

void test_v0_genesis_and_tick() {
    EngineSession session(1);
    const auto status = session.initialize_simulation(v0_spec());
    assert(status.ok());
    assert(session.tick() == Tick(0));
    assert(session.root() != nullptr);
    assert(session.simulation_runtime() != nullptr);
    assert(session.root()->households.alive_count() == 20);
    assert(session.root()->firms.alive_count() == 4);
    assert(session.root()->institutions.clearing_account.valid());
    assert_close(session.root()->genesis_money.value(), 2800.0);
    session.root()->households.for_each_alive(
        [](HouseholdId, const core::HouseholdComponent &household) {
            assert_close(household.income_expected, 1.0);
            assert_close(household.income_realized, 1.0);
        });
    const core::SettlementBatch direct_batch;
    const auto direct_apply = session.apply(direct_batch);
    assert(!direct_apply.ok());
    assert(direct_apply.status().code() == ErrorCode::unsupported);

    auto result = session.advance_tick();
    assert(result.ok());
    assert(result.get_if()->advanced_ticks == 1);
    assert(result.get_if()->first_tick == Tick(0));
    assert(result.get_if()->next_tick == Tick(1));
    assert(result.get_if()->metrics.real_output > 0.0);
    assert(result.get_if()->metrics.wages_paid > 0.0);
    assert(result.get_if()->metrics.household_consumption > 0.0);
    assert_close(result.get_if()->metrics.total_money, 2800.0);
    assert_close(result.get_if()->metrics.conservation_drift, 0.0);
    assert(core::run_invariants(*session.root()).ok());
}

void test_v1_fiscal_and_capital_tick() {
    EngineSession session(2);
    const auto status = session.initialize_simulation(v1_spec());
    assert(status.ok());
    assert(session.root()->institutions.treasury_account.valid());
    assert_close(session.root()->genesis_money.value(), 3200.0);
    assert_close(session.simulation_runtime()->last_metrics.total_money, 3200.0);

    auto result = session.advance_ticks(3);
    if (!result.ok()) {
        std::fprintf(stderr, "V1 advance failed: %.*s\n",
                     static_cast<int>(result.status().message().size()),
                     result.status().message().data());
    }
    assert(result.ok());
    const auto &metrics = result.get_if()->metrics;
    assert(result.get_if()->advanced_ticks == 3);
    assert(result.get_if()->next_tick == Tick(3));
    assert(metrics.tax_total > 0.0);
    assert(metrics.tax_profit >= 0.0);
    assert(metrics.tax_income >= 0.0);
    assert(metrics.tax_consumption >= 0.0);
    assert(metrics.tax_profit + metrics.tax_income + metrics.tax_consumption <=
           metrics.tax_total + 1.0e-9);
    assert(metrics.government_spending > 0.0);
    assert(metrics.aggregate_capital > 0.0);
    assert(metrics.public_capital > 0.0);
    assert_close(metrics.total_money, 3200.0);
    assert(core::run_invariants(*session.root()).ok());
}

void test_dividend_payout_is_reported_directly() {
    const auto run = [](double payout) {
        auto spec = v1_spec(4821);
        spec.rules.dividend_payout = payout;
        EngineSession session(31);
        assert(session.initialize_simulation(spec).ok());
        double total = 0.0;
        for (int day = 0; day < 5; ++day) {
            const auto result = session.advance_tick();
            assert(result.ok());
            total += result.get_if()->metrics.dividends_paid;
        }
        return total;
    };

    const double retained = run(0.0);
    const double distributed = run(1.0);
    assert_close(retained, 0.0);
    assert(distributed > 0.0);
}

void test_capital_clock_demand_smoothing_scales_the_source_ema() {
    const auto run = [](double smoothing) {
        auto spec = v0_spec(4822);
        spec.rules.demand_adjustment = 0.5;
        spec.rules.capital_clock_demand_smoothing = smoothing;
        auto initialization = build_m4_genesis(spec);
        assert(initialization.ok());
        auto value = std::move(initialization).take();
        value.root.firms.for_each_alive(
            [](FirmId, core::FirmComponent &firm) {
                firm.demand_expected = 10.0;
                firm.sales_previous = 20.0;
                firm.rationed_previous = 0.0;
                firm.demand_adjustment = 0.5;
            });
        M4TickScratch scratch;
        Tick tick(0);
        const auto advanced =
            advance_tick(value.root, value.runtime, scratch, tick);
        assert(advanced.ok());
        const auto *firm = value.root.firms.get(FirmId(1));
        assert(firm != nullptr);
        return firm->demand_expected;
    };

    assert_close(run(1.0), 15.0);
    assert_close(run(0.5), 12.5);
}

void test_wage_indexation_uses_committed_expected_inflation() {
    const auto run = [](double indexation) {
        auto spec = v0_spec(4823);
        spec.stochastic = true;
        spec.rules.wage_calvo_probability = 1.0;
        spec.rules.wage_downward_drift = 0.0;
        spec.rules.wage_indexation = indexation;
        spec.rules.wage_expected_inflation = 0.01;
        auto initialization = build_m4_genesis(spec);
        assert(initialization.ok());
        auto value = std::move(initialization).take();
        value.root.firms.for_each_alive(
            [](FirmId, core::FirmComponent &firm) {
                firm.hired_previous = 1.0;
                firm.labor_demand_previous = 1.0;
                firm.shortage_adjustment = 0.0;
            });
        M4TickScratch scratch;
        Tick tick(0);
        const auto advanced =
            advance_tick(value.root, value.runtime, scratch, tick);
        assert(advanced.ok());
        const auto *firm = value.root.firms.get(FirmId(1));
        assert(firm != nullptr);
        return firm->posted_wage.value();
    };

    assert_close(run(0.0), 1.0);
    assert_close(run(1.0), 1.01);
}

void test_diseconomy_slope_raises_large_firm_unit_cost() {
    const auto run = [](double slope) {
        auto spec = v0_spec(4824);
        spec.stochastic = true;
        spec.rules.price_calvo_probability = 1.0;
        spec.rules.diseconomy_slope = slope;
        auto initialization = build_m4_genesis(spec);
        assert(initialization.ok());
        auto value = std::move(initialization).take();
        M4TickScratch scratch;
        Tick tick(0);
        const auto advanced =
            advance_tick(value.root, value.runtime, scratch, tick);
        assert(advanced.ok());
        const auto *firm = value.root.firms.get(FirmId(1));
        assert(firm != nullptr);
        return firm->posted_price.value();
    };

    const double constant_returns = run(0.0);
    const double coordination_costs = run(0.05);
    assert(coordination_costs > constant_returns);
}

void test_fiscal_quantity_and_deficit_regimes_are_distinct() {
    auto quantity = v1_spec(207);
    quantity.rules.government_investment_share = 0.0;
    quantity.rules.government_consumption_share = 0.20;
    quantity.rules.government_deficit_target = 0.0;
    EngineSession quantity_session(21);
    assert(quantity_session.initialize_simulation(quantity).ok());
    const auto quantity_result = quantity_session.advance_tick();
    assert(quantity_result.ok());
    assert(quantity_result.get_if()->metrics.government_consumption > 0.0);

    auto funded = quantity;
    funded.rules.government_deficit_target = 1.0;
    EngineSession funded_session(22);
    assert(funded_session.initialize_simulation(funded).ok());
    const auto funded_result = funded_session.advance_tick();
    assert(funded_result.ok());
    assert(funded_result.get_if()->metrics.government_consumption > 0.0);

    auto zero_share = funded;
    zero_share.rules.government_consumption_share = 0.0;
    EngineSession zero_share_session(23);
    assert(zero_share_session.initialize_simulation(zero_share).ok());
    const auto zero_share_result = zero_share_session.advance_tick();
    assert(zero_share_result.ok());
    assert_close(zero_share_result.get_if()->metrics.government_consumption,
                 funded_result.get_if()->metrics.government_consumption);
}

void test_fiscal_deficit_responds_to_unemployment() {
    auto spec = v1_spec(208);
    spec.rules.government_investment_share = 0.0;
    spec.rules.government_consumption_share = 0.10;
    spec.rules.government_deficit_target = 0.05;
    spec.rules.deficit_unemployment_reference = 0.05;
    spec.rules.deficit_unemployment_cap = 4.0;

    const auto run_with_unemployment = [&spec](double unemployment) {
        auto initialization = build_m4_genesis(spec);
        assert(initialization.ok());
        auto state = std::move(initialization).take();
        state.runtime.previous_nominal_output = 100.0;
        state.runtime.last_metrics.nominal_output = 100.0;
        state.runtime.last_metrics.unemployment_rate = unemployment;
        M4TickScratch scratch;
        Tick tick{};
        auto result = advance_ticks(state.root, state.runtime, scratch, tick, 1);
        assert(result.ok());
        return result.get_if()->metrics.government_consumption;
    };

    const double full_employment = run_with_unemployment(0.0);
    const double slack_economy = run_with_unemployment(0.20);
    assert(slack_economy > full_employment);
}

void test_deficit_envelope_includes_transfer_spending() {
    auto spec = v1_spec(209);
    spec.rules.government_investment_share = 0.0;
    spec.rules.government_consumption_share = 1.0;
    spec.rules.government_deficit_target = 0.25;

    const auto run_with_prior_transfers = [&spec](double transfers) {
        auto initialization = build_m4_genesis(spec);
        assert(initialization.ok());
        auto state = std::move(initialization).take();
        state.runtime.previous_nominal_output = 20.0;
        state.runtime.last_metrics.nominal_output = 20.0;
        state.runtime.last_metrics.tax_total = 10.0;
        state.runtime.last_metrics.transfer_payments = transfers;
        M4TickScratch scratch;
        Tick tick{};
        auto result = advance_ticks(state.root, state.runtime, scratch, tick, 1);
        assert(result.ok());
        return result.get_if()->metrics.government_consumption;
    };

    const double without_transfers = run_with_prior_transfers(0.0);
    const double transfer_committed = run_with_prior_transfers(15.0);
    assert(without_transfers > 0.0);
    assert(transfer_committed < without_transfers);
}

void test_consumption_price_index_excludes_capital_goods() {
    auto spec = v1_spec();
    spec.rules.initial_capital_price = 2.4;
    EngineSession session(20);
    assert(session.initialize_simulation(spec).ok());
    const auto result = session.advance_ticks(1);
    assert(result.ok());
    assert_close(result.get_if()->metrics.price_index, 1.2);
}

void test_consumption_tax_follows_each_household_purchase_basket() {
    auto spec = v1_spec(9127);
    spec.market_protocol = algorithms::MatchingProtocol::sampled;
    spec.rules.market_sample_size = 1;
    spec.rules.government_consumption_share = 0.0;
    spec.rules.government_investment_share = 0.0;
    spec.rules.profit_tax_rate = 0.0;
    spec.rules.income_tax_rate = 0.0;
    spec.rules.consumption_tax_rate = 0.0;
    spec.rules.necessity_consumption_tax_rate = 0.05;
    spec.rules.luxury_consumption_tax_rate = 0.50;
    spec.rules.wealth_tax_rate = 0.0;
    spec.rules.unemployment_benefit_replacement = 0.0;
    auto initialization = build_m4_genesis(spec);
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    value.root.firms.for_each_alive([&](FirmId id, const core::FirmComponent &) {
        value.root.firms.get(id)->dividend_payout = 0.0;
    });
    std::vector<double> opening(
        static_cast<std::size_t>(value.root.households.allocator_state().next_id), 0.0);
    value.root.households.for_each_alive(
        [&](HouseholdId id, const core::HouseholdComponent &household) {
            opening[static_cast<std::size_t>(id.value())] =
                value.root.postings.get(household.primary_account)->balance.value();
        });
    M4TickScratch scratch;
    scratch.reserve(value.root);
    Tick tick{};
    const auto result = advance_ticks(value.root, value.runtime, scratch, tick, 1);
    assert(result.ok());
    double necessity_spent = 0.0;
    double luxury_spent = 0.0;
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto id = scratch.household_ids_[index];
        const auto *household = value.root.households.get(id);
        const auto &work = scratch.household_work_[index];
        const double closing =
            value.root.postings.get(household->primary_account)->balance.value();
        const double paid = opening[static_cast<std::size_t>(id.value())] +
                            work.income_realized - work.spent - closing;
        const double expected = 0.05 * work.necessity_spent + 0.50 * work.luxury_spent;
        assert_close(paid, expected, 1.0e-7);
        necessity_spent += work.necessity_spent;
        luxury_spent += work.luxury_spent;
    }
    assert(necessity_spent > 0.0);
    assert(luxury_spent > 0.0);
    assert_close(result.get_if()->metrics.tax_consumption,
                 0.05 * necessity_spent + 0.50 * luxury_spent, 1.0e-7);
}

void test_public_capital_stock_and_productivity() {
    auto spec = v1_spec(778);
    spec.rules.government_consumption_share = 0.0;
    spec.rules.government_investment_share = 0.0;
    spec.rules.public_capital_gamma = 0.15;
    spec.rules.public_capital_depreciation = 0.01;

    auto baseline = build_m4_genesis(spec);
    auto supported = build_m4_genesis(spec);
    assert(baseline.ok());
    assert(supported.ok());
    auto baseline_state = std::move(baseline).take();
    auto supported_state = std::move(supported).take();
    supported_state.runtime.public_capital =
        supported_state.runtime.public_capital_reference;

    M4TickScratch baseline_scratch;
    M4TickScratch supported_scratch;
    Tick baseline_tick{};
    Tick supported_tick{};
    const auto baseline_result =
        advance_ticks(baseline_state.root, baseline_state.runtime, baseline_scratch,
                      baseline_tick, 1);
    const auto supported_result =
        advance_ticks(supported_state.root, supported_state.runtime, supported_scratch,
                      supported_tick, 1);
    assert(baseline_result.ok());
    assert(supported_result.ok());
    assert_close(supported_state.runtime.public_capital,
                 0.99 * supported_state.runtime.public_capital_reference);
    assert(supported_result.get_if()->metrics.real_output >
           baseline_result.get_if()->metrics.real_output);
}

void test_faults_are_atomic() {
    constexpr std::array phases{
        M4Phase::open_books,           M4Phase::open_real_economy,
        M4Phase::plan_and_finance,     M4Phase::labor,
        M4Phase::production,           M4Phase::goods_market,
        M4Phase::capital_market,       M4Phase::settle_domestic,
        M4Phase::validate_and_measure, M4Phase::stage_local_commit,
    };
    for (const auto phase : phases) {
        EngineSession session(3);
        assert(session.initialize_simulation(v1_spec()).ok());
        const auto before = core::state_digest(*session.root());
        const auto runtime_before = *session.simulation_runtime();
        M4AdvanceOptions options;
        options.fault_before_phase = phase;
        const auto result = session.advance_ticks(1, options);
        assert(!result.ok());
        assert(session.tick() == Tick(0));
        assert(core::state_digest(*session.root()) == before);
        const auto *runtime = session.simulation_runtime();
        assert(runtime->rng_counter == runtime_before.rng_counter);
        assert(runtime->technology_index == runtime_before.technology_index);
        assert(runtime->public_capital == runtime_before.public_capital);
        assert(runtime->previous_nominal_output ==
               runtime_before.previous_nominal_output);
        assert(runtime->last_metrics == runtime_before.last_metrics);
    }
}

void test_chunking_and_stochastic_replay() {
    auto spec = v1_spec(991);
    spec.stochastic = true;
    spec.market_protocol = algorithms::MatchingProtocol::sampled;
    spec.rules.market_sample_size = 2;

    EngineSession direct(4);
    EngineSession chunked(5);
    assert(direct.initialize_simulation(spec).ok());
    assert(chunked.initialize_simulation(spec).ok());
    auto all = direct.advance_ticks(20);
    assert(all.ok());
    for (std::uint64_t index = 0; index < 20; ++index) {
        assert(chunked.advance_ticks(1).ok());
    }
    assert(direct.tick() == chunked.tick());
    assert(core::state_digest(*direct.root()) == core::state_digest(*chunked.root()));
    assert(direct.simulation_runtime()->rng_counter ==
           chunked.simulation_runtime()->rng_counter);
    assert(direct.simulation_runtime()->last_metrics ==
           chunked.simulation_runtime()->last_metrics);
}

void test_scratch_capacity_stabilizes() {
    EngineSession session(6);
    assert(session.initialize_simulation(v1_spec()).ok());
    assert(session.advance_ticks(5).ok());
    const auto capacity = session.tick_scratch()->capacity_signature();
    assert(session.advance_ticks(30).ok());
    assert(session.tick_scratch()->capacity_signature() == capacity);
}

void test_checkpoint_round_trip_and_corruption() {
    auto spec = v1_spec(412);
    spec.stochastic = true;
    spec.rules.capital_clock_demand_smoothing = 0.5;
    spec.rules.diseconomy_slope = 0.01;
    spec.rules.wage_indexation = 0.75;
    spec.rules.wage_expected_inflation = 0.001;
    EngineSession source(7);
    assert(source.initialize_simulation(spec).ok());
    assert(source.advance_ticks(12).ok());
    const auto source_digest = source.digest();
    const auto checkpoint = source.checkpoint();
    assert(source_digest.ok());
    assert(checkpoint.ok());

    EngineSession restored(8);
    assert(restored.restore_checkpoint(*checkpoint.get_if()).ok());
    assert(restored.tick() == Tick(12));
    const auto restored_digest = restored.digest();
    assert(restored_digest.ok());
    assert(*restored_digest.get_if() == *source_digest.get_if());
    assert(source.advance_ticks(15).ok());
    assert(restored.advance_ticks(15).ok());
    assert(*source.digest().get_if() == *restored.digest().get_if());

    auto corrupt = *checkpoint.get_if();
    corrupt[corrupt.size() / 2] ^= 0x1U;
    const auto before = restored.digest();
    const auto before_tick = restored.tick();
    const auto status = restored.restore_checkpoint(corrupt);
    assert(!status.ok());
    assert(status.code() == ErrorCode::corrupt_input);
    assert(restored.tick() == before_tick);
    assert(*restored.digest().get_if() == *before.get_if());
}

void test_checkpoint_rejects_invalid_m4_columns() {
    auto initialization = build_m4_genesis(v1_spec());
    assert(initialization.ok());
    auto value = std::move(initialization).take();
    value.root.households.get(HouseholdId(1))->income_expected =
        std::numeric_limits<double>::quiet_NaN();
    const auto checkpoint = save_m4_checkpoint(value.root, value.runtime, Tick(0));
    assert(!checkpoint.ok());
    assert(checkpoint.status().code() == ErrorCode::invariant_violation);
}

} // namespace

int main() {
    test_capability_boundary();
    test_v0_genesis_and_tick();
    test_v1_fiscal_and_capital_tick();
    test_dividend_payout_is_reported_directly();
    test_capital_clock_demand_smoothing_scales_the_source_ema();
    test_wage_indexation_uses_committed_expected_inflation();
    test_diseconomy_slope_raises_large_firm_unit_cost();
    test_fiscal_quantity_and_deficit_regimes_are_distinct();
    test_fiscal_deficit_responds_to_unemployment();
    test_deficit_envelope_includes_transfer_spending();
    test_consumption_price_index_excludes_capital_goods();
    test_consumption_tax_follows_each_household_purchase_basket();
    test_public_capital_stock_and_productivity();
    test_faults_are_atomic();
    test_chunking_and_stochastic_replay();
    test_scratch_capacity_stabilizes();
    test_checkpoint_round_trip_and_corruption();
    test_checkpoint_rejects_invalid_m4_columns();
    return 0;
}
