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

} // namespace

int main() {
    test_null_occupants_advance_complete_boundary();
    test_human_pause_consumes_no_tick();
    test_scheduled_policy_reaches_effective_world();
    test_native_rl_occupant_runs_without_python();
    return 0;
}
