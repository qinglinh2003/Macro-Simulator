#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <utility>

#include "macro_sim/control/m10.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::simulation;

[[nodiscard]] M9World build_world() {
    M8SimulationSpec economy;
    auto &population = economy.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 8;
    real.consumption_firms = 2;
    real.capital_firms = 1;
    real.seed = 808U;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 16;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    economy.energy_rules.producer_count = 1;
    economy.housing_rules.enabled = false;

    M9WorldSpec spec;
    spec.economies.push_back(std::move(economy));
    spec.external_policies.resize(1);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] CanonicalControllerEnvelope
envelope(const EngineSession &engine, std::string payload = "{}") {
    CanonicalControllerEnvelope value;
    value.boundary = engine.tick();
    value.policy_generation = engine.policy_generation();
    value.decision_versions = {0U, 0U};
    value.effective_versions = {0U, 0U};
    value.canonical_payload.assign(payload.begin(), payload.end());
    assert(seal_controller_envelope(value).ok());
    return value;
}

[[nodiscard]] WorldPolicyBatch policy_batch(const EngineSession &engine) {
    WorldPolicyBatch batch;
    batch.expected_tick = engine.tick();
    batch.expected_generation = engine.policy_generation();
    batch.external = engine.world().external_policies();
    for (std::size_t index = 0; index < engine.world().economy_count(); ++index) {
        auto policy = engine.world().domestic_policy(
            EconomyId(static_cast<std::uint64_t>(index)));
        assert(policy.ok());
        batch.domestic.push_back(*policy.get_if());
    }
    return batch;
}

[[nodiscard]] HybridControlledBridge bridge() {
    auto engine = EngineSession::create(build_world(), 8U);
    assert(engine.ok());
    auto initial = envelope(*engine.get_if());
    auto result = HybridControlledBridge::create(
        std::move(*engine.get_if()), std::move(initial));
    assert(result.ok());
    return std::move(*result.get_if());
}

void test_controller_updates_are_idempotent_and_monotonic() {
    auto session = bridge();
    auto next = session.controller_envelope();
    next.event_sequence = 1U;
    next.canonical_payload = {'n', 'e', 'x', 't'};
    assert(seal_controller_envelope(next).ok());
    ControllerEnvelopeTransition transition{
        "controller-update-1",
        session.controller_envelope().hash,
        next,
    };
    const auto first = session.update_controller(transition);
    const auto repeated = session.update_controller(transition);
    assert(first.ok());
    assert(repeated.ok());
    assert(*first.get_if() == *repeated.get_if());

    transition.next.canonical_payload.push_back('x');
    assert(seal_controller_envelope(transition.next).ok());
    assert(session.update_controller(transition).status().code() ==
           ErrorCode::already_exists);
    assert(session.acknowledge_receipt("controller-update-1").ok());
    assert(session.acknowledge_receipt("controller-update-1").code() ==
           ErrorCode::not_found);
}

void test_prepare_blocks_queries_and_abort_exposes_old_composite() {
    auto session = bridge();
    const auto opening_tick = session.engine().tick();
    const auto opening_digest = session.engine().world().digest();
    auto policies = policy_batch(session.engine());
    policies.domestic[0].fiscal_monetary.income_tax_rate = 0.40;
    SealedControlBatch batch{
        "boundary-abort",
        session.controller_envelope().hash,
        std::move(policies),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    assert(lease.get_if()->preview().first_tick == opening_tick);
    assert(lease.get_if()->preview().next_tick == Tick(opening_tick.value() + 1U));
    assert(!session.query_status().ok());
    assert(!session.clone().ok());
    assert(!session.probe_households(EconomyId(0U), 0U, 4U).ok());
    assert(!session.probe_economy_diagnostics(EconomyId(0U)).ok());
    assert(session.abort_boundary(std::move(*lease.get_if())).ok());
    assert(session.engine().tick() == opening_tick);
    assert(session.engine().world().digest() == opening_digest);
    assert(session.query_status().ok());
    assert(session.probe_households(EconomyId(0U), 0U, 4U).ok());
}

void test_policy_validation_is_non_mutating_and_respects_query_lock() {
    auto session = bridge();
    const auto opening_digest = session.engine().world().digest();
    const auto opening_generation = session.engine().policy_generation();

    auto valid = policy_batch(session.engine());
    valid.domestic[0].fiscal_monetary.income_tax_rate = 0.33;
    assert(session.validate_policy_batch(valid).ok());
    assert(session.engine().world().digest() == opening_digest);
    assert(session.engine().policy_generation() == opening_generation);

    auto invalid = policy_batch(session.engine());
    invalid.domestic[0].fiscal_monetary.income_tax_rate = 2.0;
    assert(!session.validate_policy_batch(invalid).ok());
    assert(session.engine().world().digest() == opening_digest);

    SealedControlBatch boundary{
        "validation-query-lock",
        session.controller_envelope().hash,
        policy_batch(session.engine()),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(boundary);
    assert(lease.ok());
    assert(!session.validate_policy_batch(valid).ok());
    assert(session.abort_boundary(std::move(*lease.get_if())).ok());
}

void test_commit_swaps_complete_engine_and_envelope() {
    auto session = bridge();
    auto policies = policy_batch(session.engine());
    policies.domestic[0].fiscal_monetary.income_tax_rate = 0.33;
    SealedControlBatch batch{
        "boundary-commit",
        session.controller_envelope().hash,
        std::move(policies),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    auto next = session.controller_envelope();
    next.boundary = lease.get_if()->preview().next_tick;
    next.policy_generation = lease.get_if()->preview().policy_generation;
    next.event_sequence = 1U;
    next.decision_versions[0] = 1U;
    next.effective_versions[0] = 1U;
    next.canonical_payload = {'c', 'o', 'm', 'm', 'i', 't'};
    assert(seal_controller_envelope(next).ok());
    const auto committed =
        session.commit_boundary(std::move(*lease.get_if()), next);
    assert(committed.ok());
    assert(session.engine().tick() == Tick(1U));
    assert(session.engine().policy_generation() == 1U);
    assert(session.controller_envelope().boundary == Tick(1U));
    const auto policy = session.engine().world().domestic_policy(EconomyId(0));
    assert(policy.ok());
    assert(policy.get_if()->fiscal_monetary.income_tax_rate == 0.33);
    assert(session.engine().metrics().history().size() == 2U);
}

void test_invalid_next_envelope_keeps_prepared_lease_abortable() {
    auto session = bridge();
    SealedControlBatch batch{
        "boundary-invalid-envelope",
        session.controller_envelope().hash,
        policy_batch(session.engine()),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    auto invalid = session.controller_envelope();
    invalid.boundary = Tick(999U);
    assert(seal_controller_envelope(invalid).ok());
    assert(!session.commit_boundary(std::move(*lease.get_if()), invalid).ok());
    assert(lease.get_if()->active());
    assert(session.abort_boundary(std::move(*lease.get_if())).ok());
    assert(session.engine().tick() == Tick(0U));
}

void commit_one(HybridControlledBridge &session, std::string operation_id,
                double income_tax_rate) {
    auto policies = policy_batch(session.engine());
    policies.domestic[0].fiscal_monetary.income_tax_rate = income_tax_rate;
    SealedControlBatch batch{
        std::move(operation_id),
        session.controller_envelope().hash,
        std::move(policies),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    auto next = session.controller_envelope();
    next.boundary = lease.get_if()->preview().next_tick;
    next.policy_generation = lease.get_if()->preview().policy_generation;
    ++next.event_sequence;
    ++next.decision_versions[0];
    ++next.effective_versions[0];
    next.canonical_payload.push_back(
        static_cast<std::uint8_t>(next.event_sequence));
    assert(seal_controller_envelope(next).ok());
    assert(session.commit_boundary(std::move(*lease.get_if()), next).ok());
}

void test_hybrid_checkpoint_split_run_is_exact() {
    auto uninterrupted = bridge();
    commit_one(uninterrupted, "split-first", 0.31);
    const std::vector<std::uint8_t> objective{1U, 3U, 5U, 7U};
    auto checkpoint = save_hybrid_checkpoint(uninterrupted, objective);
    assert(checkpoint.ok());
    auto loaded = load_hybrid_checkpoint(*checkpoint.get_if());
    assert(loaded.ok());
    assert(loaded.get_if()->objective_envelope == objective);
    assert(loaded.get_if()->bridge.engine().tick() ==
           uninterrupted.engine().tick());
    assert(loaded.get_if()->bridge.engine().world().digest() ==
           uninterrupted.engine().world().digest());
    assert(loaded.get_if()->bridge.controller_envelope() ==
           uninterrupted.controller_envelope());
    assert(loaded.get_if()->bridge.engine().metrics().history().next_sequence() ==
           uninterrupted.engine().metrics().history().next_sequence());

    commit_one(uninterrupted, "split-second", 0.32);
    commit_one(loaded.get_if()->bridge, "split-second", 0.32);
    assert(loaded.get_if()->bridge.engine().world().digest() ==
           uninterrupted.engine().world().digest());
    assert(loaded.get_if()->bridge.controller_envelope() ==
           uninterrupted.controller_envelope());
}

void test_checkpoint_rejects_prepared_and_corrupt_state() {
    auto session = bridge();
    SealedControlBatch batch{
        "checkpoint-lock",
        session.controller_envelope().hash,
        policy_batch(session.engine()),
        1U,
        {},
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    assert(!save_hybrid_checkpoint(session).ok());
    assert(session.abort_boundary(std::move(*lease.get_if())).ok());
    auto checkpoint = save_hybrid_checkpoint(session);
    assert(checkpoint.ok());
    checkpoint.get_if()->back() ^= 0xffU;
    assert(load_hybrid_checkpoint(*checkpoint.get_if()).status().code() ==
           ErrorCode::corrupt_input);
}

void test_every_hybrid_fault_exposes_only_old_or_new_composite() {
    for (const auto fault : {
             M10FaultPoint::prepare_after_policy,
             M10FaultPoint::prepare_after_advance,
             M10FaultPoint::prepare_after_metrics,
         }) {
        auto session = bridge();
        const auto opening_tick = session.engine().tick();
        const auto opening_digest = session.engine().world().digest();
        const auto opening_envelope = session.controller_envelope();
        SealedControlBatch batch{
            "prepare-fault-" +
                std::to_string(static_cast<std::uint8_t>(fault)),
            opening_envelope.hash,
            policy_batch(session.engine()),
            1U,
            {},
            fault,
        };
        assert(!session.prepare_boundary(batch).ok());
        assert(session.query_status().ok());
        assert(session.engine().tick() == opening_tick);
        assert(session.engine().world().digest() == opening_digest);
        assert(session.controller_envelope() == opening_envelope);
    }

    auto session = bridge();
    const auto opening_digest = session.engine().world().digest();
    const auto opening_envelope = session.controller_envelope();
    SealedControlBatch batch{
        "commit-fault",
        opening_envelope.hash,
        policy_batch(session.engine()),
        1U,
        {},
        M10FaultPoint::commit_before_swap,
    };
    auto lease = session.prepare_boundary(batch);
    assert(lease.ok());
    auto next = opening_envelope;
    next.boundary = lease.get_if()->preview().next_tick;
    next.policy_generation = lease.get_if()->preview().policy_generation;
    ++next.event_sequence;
    assert(seal_controller_envelope(next).ok());
    assert(!session.commit_boundary(std::move(*lease.get_if()), next).ok());
    assert(lease.get_if()->active());
    assert(!session.query_status().ok());
    assert(session.abort_boundary(std::move(*lease.get_if())).ok());
    assert(session.engine().tick() == Tick(0U));
    assert(session.engine().world().digest() == opening_digest);
    assert(session.controller_envelope() == opening_envelope);
}

} // namespace

int main() {
    test_controller_updates_are_idempotent_and_monotonic();
    test_prepare_blocks_queries_and_abort_exposes_old_composite();
    test_policy_validation_is_non_mutating_and_respects_query_lock();
    test_commit_swaps_complete_engine_and_envelope();
    test_invalid_next_envelope_keeps_prepared_lease_abortable();
    test_hybrid_checkpoint_split_run_is_exact();
    test_checkpoint_rejects_prepared_and_corrupt_state();
    test_every_hybrid_fault_exposes_only_old_or_new_composite();
    std::cout << "M10 control tests passed\n";
    return 0;
}
