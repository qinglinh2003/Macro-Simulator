#include <algorithm>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <string>
#include <utility>
#include <vector>

#include "macro_sim/control/m11_session.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec economy_spec(std::uint64_t seed) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &financial = population.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 8U;
    real.consumption_firms = 2U;
    real.capital_firms = 1U;
    real.seed = seed;
    real.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
        capability_bit(M4Capability::government);
    monetary.rules.bank_count = 2U;
    monetary.rules.opening_capital_per_bank = 100.0;
    financial.rules.entry_beta = 0.0;
    financial.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 16U;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    value.energy_rules.enabled = true;
    value.energy_rules.household_energy = true;
    value.energy_rules.producer_count = 1U;
    value.housing_rules.enabled = true;
    value.housing_rules.resale_market = true;
    value.housing_rules.mortgages = true;
    value.housing_rules.rentals = true;
    value.housing_rules.construction = true;
    return value;
}

[[nodiscard]] EngineSession engine() {
    M9WorldSpec spec;
    spec.rules.trade = true;
    spec.rules.capital = true;
    spec.rules.migration = true;
    spec.economies.push_back(economy_spec(3301U));
    spec.economies.push_back(economy_spec(3302U));
    spec.external_policies.resize(2U);
    auto world = M9World::create(spec);
    assert(world.ok());
    auto result =
        EngineSession::create(std::move(*world.get_if()), 4096U);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] M11PolicyProposal no_action(
    const M11DecisionContext &context, std::string id) {
    M11PolicyProposal proposal;
    proposal.proposal_id = id;
    proposal.idempotency_key = id;
    proposal.context_id = context.context_id;
    proposal.reason = "human hold";
    for (const auto &version : context.policy_versions) {
        proposal.based_on_policy_versions.push_back(
            {version.lever, version.version});
    }
    return proposal;
}

[[nodiscard]] M11ShockAuthority scenario_authority() {
    M11ShockAuthority authority;
    authority.principal = "scenario-authority";
    authority.granted_seats = {"energy", "treasury"};
    authority.allowed_kinds = {
        ShockKind::productivity,
        ShockKind::energy_capacity,
    };
    authority.allow_all_economies = true;
    authority.allow_global = true;
    authority.maximum_absolute_magnitude = 0.75;
    return authority;
}

void test_null_occupants_advance_complete_boundary() {
    auto session =
        M11ControlledSession::create(engine());
    assert(session.ok());
    auto advanced = session.get_if()->advance_until_decision({1U, true});
    assert(advanced.ok());
    assert(session.get_if()->tick() == Tick(1U));
    assert(advanced.get_if()->opened_context_ids.size() ==
           kM11DecisionGroupCount * 2U);
    assert(advanced.get_if()->decisions.size() ==
           kM11DecisionGroupCount * 2U);
    assert(session.get_if()->phase() ==
           M11BoundaryPhase::boundary_start);
    assert(session.get_if()->events().events().size() >
           advanced.get_if()->decisions.size());
}

void test_human_pause_consumes_no_tick() {
    M11ControllerRunSpec spec;
    M11OccupantSpec human;
    human.kind = M11OccupantKind::human_queue;
    human.occupant_id = "human";
    spec.assignments.push_back({
        EconomyId(0U),
        "treasury",
        std::move(human),
    });
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    const auto opening_digest =
        session.get_if()->engine().world().digest();
    auto paused = session.get_if()->advance_until_decision({1U, true});
    assert(paused.ok());
    assert(paused.get_if()->awaiting_human);
    assert(session.get_if()->tick() == Tick(0U));
    assert(session.get_if()->engine().world().digest() ==
           opening_digest);

    std::vector<std::string> unanswered;
    for (const auto &context_id :
         session.get_if()->state().opened_context_ids) {
        const auto *context =
            session.get_if()->coordinator().find_context(context_id);
        assert(context != nullptr);
        if (context->seat == "treasury" &&
            !context->answered_by_proposal.has_value()) {
            unanswered.push_back(context_id);
        }
    }
    assert(!unanswered.empty());
    for (std::size_t index = 0U; index < unanswered.size(); ++index) {
        const auto *context =
            session.get_if()->coordinator().find_context(
                unanswered[index]);
        assert(context != nullptr);
        auto decision = session.get_if()->submit_human_proposal(
            no_action(
                *context,
                "human-hold-" + std::to_string(index)),
            "player");
        assert(decision.ok());
    }
    assert(session.get_if()->phase() ==
           M11BoundaryPhase::ready_to_commit);
    auto committed =
        session.get_if()->advance_until_decision({1U, true});
    assert(committed.ok());
    assert(session.get_if()->tick() == Tick(1U));
}

void test_scheduled_policy_reaches_effective_world() {
    M11OccupantSpec scheduled;
    scheduled.kind = M11OccupantKind::scheduled;
    scheduled.occupant_id = "fiscal-script";
    scheduled.schedule.push_back({
        Tick(0U),
        "fiscal_stance",
        {{EconomyId(0U), "gov_deficit_target", 0.02}},
    });
    M11ControllerRunSpec spec;
    spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(scheduled)});
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    auto first =
        session.get_if()->advance_until_decision({1U, true});
    assert(first.ok());
    const auto accepted = std::find_if(
        first.get_if()->decisions.begin(),
        first.get_if()->decisions.end(),
        [](const M11PolicyDecision &decision) {
            return decision.status ==
                       M11DecisionStatus::accepted_pending &&
                   decision.effective_at == Tick(7U);
        });
    assert(accepted != first.get_if()->decisions.end());

    auto through_effective =
        session.get_if()->advance_until_decision({7U, false});
    assert(through_effective.ok());
    assert(session.get_if()->tick() == Tick(8U));
    auto policy = session.get_if()->engine().world().domestic_policy(
        EconomyId(0U));
    assert(policy.ok());
    assert(policy.get_if()->fiscal_monetary.government_deficit_target ==
           0.02);
    const auto *decision =
        session.get_if()->coordinator().find_decision(
            accepted->decision_id);
    assert(decision != nullptr);
    assert(decision->status == M11DecisionStatus::effective);
}

void test_native_rl_occupant_runs_without_python() {
    M11OccupantSpec rl;
    rl.kind = M11OccupantKind::reinforcement_learning;
    rl.occupant_id = "native-rl";
    rl.artifact_path =
        std::filesystem::path(MACRO_SIM_SOURCE_DIR) /
        "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl";
    M11ControllerRunSpec spec;
    spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(rl)});
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    const auto *runtime =
        session.get_if()->seat(EconomyId(0U), "treasury");
    assert(runtime != nullptr);
    assert(runtime->artifact.has_value());
    assert(runtime->assignment.occupant.action_dimensions ==
           std::vector<std::string>{"gov_deficit_target"});
    auto advanced =
        session.get_if()->advance_until_decision({1U, true});
    assert(advanced.ok());
    assert(session.get_if()->tick() == Tick(1U));
    assert(std::any_of(
        advanced.get_if()->decisions.begin(),
        advanced.get_if()->decisions.end(),
        [](const M11PolicyDecision &decision) {
            return decision.status ==
                       M11DecisionStatus::accepted_noop ||
                   decision.status ==
                       M11DecisionStatus::accepted_pending;
        }));
}

void test_checkpoint_restores_pending_execution_exactly() {
    M11OccupantSpec scheduled;
    scheduled.kind = M11OccupantKind::scheduled;
    scheduled.occupant_id = "checkpoint-script";
    scheduled.schedule.push_back({
        Tick(0U),
        "fiscal_stance",
        {{EconomyId(0U), "gov_deficit_target", 0.015}},
    });
    M11ControllerRunSpec spec;
    spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(scheduled)});
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    assert(session.get_if()
               ->advance_until_decision({1U, true})
               .ok());
    auto checkpoint = save_m11_checkpoint(*session.get_if());
    assert(checkpoint.ok());
    auto restored = load_m11_checkpoint(*checkpoint.get_if());
    assert(restored.ok());
    assert(restored.get_if()->tick() == session.get_if()->tick());
    assert(restored.get_if()->engine().world().digest() ==
           session.get_if()->engine().world().digest());
    assert(restored.get_if()->events().head_hash() ==
           session.get_if()->events().head_hash());
    assert(restored.get_if()->releases().next_sequence() ==
           session.get_if()->releases().next_sequence());

    auto original_advance =
        session.get_if()->advance_until_decision({12U, false});
    auto restored_advance =
        restored.get_if()->advance_until_decision({12U, false});
    assert(original_advance.ok());
    assert(restored_advance.ok());
    assert(restored.get_if()->engine().world().digest() ==
           session.get_if()->engine().world().digest());
    assert(restored.get_if()->events().head_hash() ==
           session.get_if()->events().head_hash());
    const auto restored_releases =
        restored.get_if()->releases().releases();
    const auto original_releases =
        session.get_if()->releases().releases();
    assert(restored_releases.size() == original_releases.size());
    assert(std::equal(
        restored_releases.begin(), restored_releases.end(),
        original_releases.begin()));

    auto corrupt = *checkpoint.get_if();
    corrupt[corrupt.size() / 2U] ^= 0x5aU;
    assert(!load_m11_checkpoint(corrupt).ok());
}

void test_checkpoint_preserves_human_pause_and_embedded_rl() {
    M11ControllerRunSpec human_spec;
    M11OccupantSpec human;
    human.kind = M11OccupantKind::human_queue;
    human.occupant_id = "checkpoint-human";
    human_spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(human)});
    auto human_session = M11ControlledSession::create(
        engine(), std::move(human_spec));
    assert(human_session.ok());
    auto paused = human_session.get_if()->advance_until_decision(
        {1U, true});
    assert(paused.ok() && paused.get_if()->awaiting_human);
    auto human_checkpoint =
        save_m11_checkpoint(*human_session.get_if());
    assert(human_checkpoint.ok());
    auto restored_human =
        load_m11_checkpoint(*human_checkpoint.get_if());
    assert(restored_human.ok());
    assert(restored_human.get_if()->phase() ==
           M11BoundaryPhase::awaiting_human);
    assert(restored_human.get_if()->tick() == Tick(0U));
    assert(restored_human.get_if()->state().opened_context_ids ==
           human_session.get_if()->state().opened_context_ids);

    M11ControllerRunSpec rl_spec;
    M11OccupantSpec rl;
    rl.kind = M11OccupantKind::reinforcement_learning;
    rl.occupant_id = "checkpoint-rl";
    rl.artifact_path =
        std::filesystem::path(MACRO_SIM_SOURCE_DIR) /
        "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl";
    rl_spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(rl)});
    auto rl_session =
        M11ControlledSession::create(engine(), std::move(rl_spec));
    assert(rl_session.ok());
    auto rl_checkpoint = save_m11_checkpoint(*rl_session.get_if());
    assert(rl_checkpoint.ok());
    auto restored_rl =
        load_m11_checkpoint(*rl_checkpoint.get_if());
    assert(restored_rl.ok());
    const auto *runtime =
        restored_rl.get_if()->seat(EconomyId(0U), "treasury");
    assert(runtime != nullptr && runtime->artifact.has_value());
    assert(!runtime->artifact->source_bytes().empty());
    assert(restored_rl.get_if()
               ->advance_until_decision({1U, true})
               .ok());
}

void test_seat_archive_restore_and_checkpoint_idempotency() {
    auto session = M11ControlledSession::create(engine());
    assert(session.ok());
    const auto *opening =
        session.get_if()->seat(EconomyId(0U), "treasury");
    assert(opening != nullptr);
    assert(opening->assignment.occupant.kind ==
           M11OccupantKind::null_occupant);

    M11OccupantSpec human;
    human.kind = M11OccupantKind::human_queue;
    human.occupant_id = "cabinet-player";
    const M11SeatAssignmentRequest assignment{
        "assign-cabinet",
        "operator",
        EconomyId(0U),
        "treasury",
        human,
    };
    auto assigned =
        session.get_if()->assign_seat(assignment);
    assert(assigned.ok());
    assert(!assigned.get_if()->repeated);
    assert(assigned.get_if()
               ->archived_occupant_id.has_value());
    const auto null_archive =
        *assigned.get_if()->archived_occupant_id;
    assert(session.get_if()
               ->seat(EconomyId(0U), "treasury")
               ->assignment.occupant.occupant_id ==
           "cabinet-player");
    assert(session.get_if()
               ->state()
               .archived_seat_occupants.size() == 1U);

    auto repeated =
        session.get_if()->assign_seat(assignment);
    assert(repeated.ok());
    assert(repeated.get_if()->repeated);
    assert(repeated.get_if()->archived_occupant_id ==
           assigned.get_if()->archived_occupant_id);
    assert(session.get_if()
               ->state()
               .archived_seat_occupants.size() == 1U);

    const auto before_invalid =
        save_m11_checkpoint(*session.get_if());
    assert(before_invalid.ok());
    auto invalid = session.get_if()->restore_seat({
        "restore-wrong",
        "operator",
        EconomyId(1U),
        "treasury",
        null_archive,
    });
    assert(!invalid.ok());
    const auto after_invalid =
        save_m11_checkpoint(*session.get_if());
    assert(after_invalid.ok());
    assert(*before_invalid.get_if() ==
           *after_invalid.get_if());

    auto checkpoint =
        save_m11_checkpoint(*session.get_if());
    assert(checkpoint.ok());
    auto restored_session =
        load_m11_checkpoint(*checkpoint.get_if());
    assert(restored_session.ok());
    assert(restored_session.get_if()
               ->state()
               .archived_seat_occupants.size() == 1U);
    assert(restored_session.get_if()
               ->state()
               .seat_operations.size() == 1U);

    const M11SeatRestoreRequest restoration{
        "restore-opening",
        "operator",
        EconomyId(0U),
        "treasury",
        null_archive,
    };
    auto restored =
        restored_session.get_if()->restore_seat(restoration);
    assert(restored.ok());
    assert(!restored.get_if()->repeated);
    assert(restored.get_if()
               ->archived_occupant_id.has_value());
    assert(restored_session.get_if()
               ->seat(EconomyId(0U), "treasury")
               ->assignment.occupant.kind ==
           M11OccupantKind::null_occupant);
    assert(restored_session.get_if()
               ->state()
               .archived_seat_occupants.size() == 1U);

    auto restore_retry =
        restored_session.get_if()->restore_seat(restoration);
    assert(restore_retry.ok());
    assert(restore_retry.get_if()->repeated);
    assert(restore_retry.get_if()->archived_occupant_id ==
           restored.get_if()->archived_occupant_id);
    const auto final_checkpoint =
        save_m11_checkpoint(*restored_session.get_if());
    assert(final_checkpoint.ok());
    auto final_round_trip =
        load_m11_checkpoint(*final_checkpoint.get_if());
    assert(final_round_trip.ok());
    assert(final_round_trip.get_if()
               ->state()
               .seat_operations.size() == 2U);
}

void test_controlled_shocks_are_authorized_atomic_and_idempotent() {
    M11ControllerRunSpec spec;
    spec.shock_authorities.push_back(scenario_authority());
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    ShockSpec shock;
    shock.id = 5501U;
    shock.kind = ShockKind::energy_capacity;
    shock.economy = EconomyId(0U);
    shock.start = Tick(0U);
    shock.duration = 2U;
    shock.magnitude = 0.4;
    M11ControlledShockScheduleRequest request{
        "shock-request-5501",
        "scenario-authority",
        "player",
        std::optional<std::string>("energy"),
        shock,
    };
    auto accepted = session.get_if()->schedule_shock(request);
    assert(accepted.ok());
    assert(!accepted.get_if()->repeated);
    assert(session.get_if()->engine().world().shocks().size() == 1U);
    const auto digest = session.get_if()->engine().world().digest();
    const auto event_count =
        session.get_if()->events().next_sequence();
    auto repeated = session.get_if()->schedule_shock(request);
    assert(repeated.ok());
    assert(repeated.get_if()->repeated);
    assert(repeated.get_if()->event_sequence ==
           accepted.get_if()->event_sequence);
    assert(session.get_if()->engine().world().digest() == digest);
    assert(session.get_if()->events().next_sequence() == event_count);

    request.shock.magnitude = 0.5;
    assert(session.get_if()
               ->schedule_shock(request)
               .status()
               .code() == ErrorCode::already_exists);
    request.operation_id = "unauthorized-shock";
    request.principal = "ordinary-seat";
    assert(!session.get_if()->schedule_shock(request).ok());
    assert(session.get_if()->engine().world().digest() == digest);
    assert(session.get_if()->events().next_sequence() == event_count);

    assert(session.get_if()
               ->advance_until_decision({1U, true})
               .ok());
    assert(session.get_if()->tick() == Tick(1U));
    assert(session.get_if()
               ->engine()
               .world()
               .last_metrics()
               .external[0U]
               .active_shocks > 0U);
}

void test_shock_scheduled_during_human_pause_starts_next_boundary() {
    M11ControllerRunSpec spec;
    spec.shock_authorities.push_back(scenario_authority());
    M11OccupantSpec human;
    human.kind = M11OccupantKind::human_queue;
    human.occupant_id = "shock-pause-human";
    spec.assignments.push_back(
        {EconomyId(0U), "treasury", std::move(human)});
    auto session =
        M11ControlledSession::create(engine(), std::move(spec));
    assert(session.ok());
    auto paused =
        session.get_if()->advance_until_decision({1U, true});
    assert(paused.ok() && paused.get_if()->awaiting_human);
    ShockSpec shock;
    shock.id = 5502U;
    shock.kind = ShockKind::productivity;
    shock.economy = EconomyId(0U);
    shock.start = Tick(0U);
    shock.duration = 1U;
    shock.magnitude = 0.2;
    M11ControlledShockScheduleRequest request{
        "shock-request-5502",
        "scenario-authority",
        "player",
        std::optional<std::string>("treasury"),
        shock,
    };
    assert(!session.get_if()->schedule_shock(request).ok());
    request.shock.start = Tick(1U);
    assert(session.get_if()->schedule_shock(request).ok());
    assert(session.get_if()->tick() == Tick(0U));
    auto checkpoint = save_m11_checkpoint(*session.get_if());
    assert(checkpoint.ok());
    auto restored = load_m11_checkpoint(*checkpoint.get_if());
    assert(restored.ok());
    assert(restored.get_if()->run_spec().shock_authorities ==
           session.get_if()->run_spec().shock_authorities);
    assert(restored.get_if()->engine().world().shocks() ==
           session.get_if()->engine().world().shocks());
}

} // namespace

int main() {
    test_null_occupants_advance_complete_boundary();
    test_human_pause_consumes_no_tick();
    test_scheduled_policy_reaches_effective_world();
    test_native_rl_occupant_runs_without_python();
    test_checkpoint_restores_pending_execution_exactly();
    test_checkpoint_preserves_human_pause_and_embedded_rl();
    test_seat_archive_restore_and_checkpoint_idempotency();
    test_controlled_shocks_are_authorized_atomic_and_idempotent();
    test_shock_scheduled_during_human_pause_starts_next_boundary();
    return 0;
}
