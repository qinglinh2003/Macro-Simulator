#include <array>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdint>
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
    spec.requested_capabilities =
        capability_bit(M4Capability::physical_capital)
        | capability_bit(M4Capability::government);
    return spec;
}

void assert_close(double left, double right, double tolerance = 1.0e-8) {
    assert(std::abs(left - right) <= tolerance);
}

void test_capability_boundary() {
    auto spec = v0_spec();
    spec.requested_capabilities =
        capability_bit(M4Capability::housing);
    const auto invalid = build_m4_genesis(spec);
    assert(!invalid.ok());
    assert(invalid.status().code() == ErrorCode::unsupported);

    spec = v1_spec();
    spec.requested_capabilities |=
        capability_bit(M4Capability::commercial_banks);
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
    assert_close(
        session.simulation_runtime()->last_metrics.total_money,
        3200.0
    );

    auto result = session.advance_ticks(3);
    if (!result.ok()) {
        std::fprintf(
            stderr,
            "V1 advance failed: %.*s\n",
            static_cast<int>(result.status().message().size()),
            result.status().message().data()
        );
    }
    assert(result.ok());
    const auto& metrics = result.get_if()->metrics;
    assert(result.get_if()->advanced_ticks == 3);
    assert(result.get_if()->next_tick == Tick(3));
    assert(metrics.tax_total > 0.0);
    assert(metrics.government_spending > 0.0);
    assert(metrics.aggregate_capital > 0.0);
    assert(metrics.public_capital > 0.0);
    assert_close(metrics.total_money, 3200.0);
    assert(core::run_invariants(*session.root()).ok());
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

void test_faults_are_atomic() {
    constexpr std::array phases{
        M4Phase::open_books,
        M4Phase::open_real_economy,
        M4Phase::plan_and_finance,
        M4Phase::labor,
        M4Phase::production,
        M4Phase::goods_market,
        M4Phase::capital_market,
        M4Phase::settle_domestic,
        M4Phase::validate_and_measure,
        M4Phase::stage_local_commit,
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
        const auto* runtime = session.simulation_runtime();
        assert(runtime->rng_counter == runtime_before.rng_counter);
        assert(runtime->technology_index == runtime_before.technology_index);
        assert(runtime->public_capital == runtime_before.public_capital);
        assert(runtime->previous_nominal_output
            == runtime_before.previous_nominal_output);
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
    assert(core::state_digest(*direct.root())
        == core::state_digest(*chunked.root()));
    assert(direct.simulation_runtime()->rng_counter
        == chunked.simulation_runtime()->rng_counter);
    assert(direct.simulation_runtime()->last_metrics
        == chunked.simulation_runtime()->last_metrics);
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
    const auto checkpoint = save_m4_checkpoint(
        value.root,
        value.runtime,
        Tick(0)
    );
    assert(!checkpoint.ok());
    assert(checkpoint.status().code() == ErrorCode::invariant_violation);
}

}  // namespace

int main() {
    test_capability_boundary();
    test_v0_genesis_and_tick();
    test_v1_fiscal_and_capital_tick();
    test_consumption_price_index_excludes_capital_goods();
    test_faults_are_atomic();
    test_chunking_and_stochastic_replay();
    test_scratch_capacity_stabilizes();
    test_checkpoint_round_trip_and_corruption();
    test_checkpoint_rejects_invalid_m4_columns();
    return 0;
}
