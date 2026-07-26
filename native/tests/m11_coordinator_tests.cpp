#include <cassert>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "macro_sim/control/m11_coordinator.hpp"

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

[[nodiscard]] M9World build_world() {
    M9WorldSpec spec;
    spec.rules.trade = true;
    spec.rules.capital = true;
    spec.rules.migration = true;
    spec.economies.push_back(economy_spec(3101U));
    spec.economies.push_back(economy_spec(3102U));
    spec.external_policies.resize(2U);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] M11PolicyProposal proposal(
    const M11DecisionContext &context, std::string proposal_id,
    std::string idempotency_key,
    std::vector<NativePolicyAction> actions,
    std::optional<std::string> supersedes = std::nullopt) {
    std::vector<M11ProposalVersion> versions;
    for (const auto &action : actions) {
        const auto permitted =
            std::find_if(
                context.permitted_actions.begin(),
                context.permitted_actions.end(),
                [&](const M11PermittedAction &entry) {
                    return entry.lever == action.lever;
                });
        assert(permitted != context.permitted_actions.end());
        versions.push_back({action.lever, permitted->policy_version});
        const auto *lever = find_m11_policy_lever(action.lever);
        assert(lever != nullptr);
        std::string_view prerequisites = lever->enabled_if;
        while (!prerequisites.empty()) {
            const auto separator = prerequisites.find('|');
            const auto name = prerequisites.substr(0U, separator);
            const auto version =
                std::find_if(
                    context.policy_versions.begin(),
                    context.policy_versions.end(),
                    [&](const M11PolicyVersion &entry) {
                        return entry.lever == name;
                    });
            assert(version != context.policy_versions.end());
            versions.push_back({std::string(name), version->version});
            if (separator == std::string_view::npos) {
                break;
            }
            prerequisites.remove_prefix(separator + 1U);
        }
    }
    return {
        std::move(proposal_id),
        std::move(idempotency_key),
        context.context_id,
        std::move(actions),
        std::move(versions),
        "test proposal",
        std::move(supersedes),
    };
}

[[nodiscard]] M11DecisionContext open_tax_context(
    M11PolicyCoordinator &coordinator,
    const M9World &world,
    const M11DecisionScheduler &scheduler) {
    auto opened = coordinator.open_context(
        world, scheduler, world.tick(), EconomyId(0U), "treasury",
        "tax_and_transfers", Tick(world.tick().value() + 1U));
    assert(opened.ok());
    return *opened.get_if();
}

void test_submission_idempotency_and_effective_commit() {
    auto world = build_world();
    auto scheduler_result = M11DecisionScheduler::create();
    auto coordinator_result = M11PolicyCoordinator::create(world);
    assert(scheduler_result.ok() && coordinator_result.ok());
    auto scheduler = std::move(*scheduler_result.get_if());
    auto coordinator = std::move(*coordinator_result.get_if());
    M11EventStream events(128U);
    auto context = open_tax_context(coordinator, world, scheduler);
    const auto tax =
        std::find_if(
            context.permitted_actions.begin(),
            context.permitted_actions.end(),
            [](const M11PermittedAction &entry) {
                return entry.lever == "tax_income_rate";
            });
    assert(tax != context.permitted_actions.end());
    assert(tax->allowed);

    auto request = proposal(
        context, "proposal-tax-1", "idem-tax-1",
        {{EconomyId(0U), "tax_income_rate", 0.25}});
    auto accepted = coordinator.submit(
        world, scheduler, world.tick(), request, "player", events);
    assert(accepted.ok());
    assert(accepted.get_if()->status ==
           M11DecisionStatus::accepted_pending);
    assert(accepted.get_if()->effective_at == Tick(30U));
    assert(accepted.get_if()->reserved_administrative_cost > 0.0);
    assert(accepted.get_if()->adjustment_cost > 0.0);
    auto repeated = coordinator.submit(
        world, scheduler, world.tick(), request, "player", events);
    assert(repeated.ok());
    assert(*repeated.get_if() == *accepted.get_if());

    request.actions.front().value = 0.26;
    const auto conflicting = coordinator.submit(
        world, scheduler, world.tick(), request, "player", events);
    assert(!conflicting.ok());
    assert(conflicting.status().code() == ErrorCode::already_exists);

    auto advanced = world.advance(30U);
    assert(advanced.ok());
    auto plan = coordinator.prepare_due(world, world.tick());
    assert(plan.ok());
    assert(plan.get_if()->effective_decision_ids.size() == 1U);
    assert(plan.get_if()->failed_decision_ids.empty());
    assert(!plan.get_if()->effective_changes.empty());
    assert(world.update_policy_batch(plan.get_if()->policy_batch).ok());
    assert(coordinator.commit_due(*plan.get_if(), events).ok());
    const auto *effective =
        coordinator.find_decision(accepted.get_if()->decision_id);
    assert(effective != nullptr);
    assert(effective->status == M11DecisionStatus::effective);
    auto version =
        coordinator.policy_version(EconomyId(0U), "tax_income_rate");
    assert(version.ok());
    assert(*version.get_if() == 1U);
    auto domestic = world.domestic_policy(EconomyId(0U));
    assert(domestic.ok());
    assert(domestic.get_if()->fiscal_monetary.income_tax_rate == 0.25);
}

void test_cancel_and_supersede_refunds() {
    auto world = build_world();
    auto scheduler_result = M11DecisionScheduler::create();
    auto coordinator_result = M11PolicyCoordinator::create(world);
    assert(scheduler_result.ok() && coordinator_result.ok());
    auto scheduler = std::move(*scheduler_result.get_if());
    auto coordinator = std::move(*coordinator_result.get_if());
    M11EventStream events(128U);
    auto context = open_tax_context(coordinator, world, scheduler);
    auto first_request = proposal(
        context, "proposal-tax-first", "idem-tax-first",
        {{EconomyId(0U), "tax_income_rate", 0.25}});
    auto first = coordinator.submit(
        world, scheduler, world.tick(), first_request, "player", events);
    assert(first.ok());
    auto replacement_request = proposal(
        context, "proposal-tax-replacement", "idem-tax-replacement",
        {{EconomyId(0U), "tax_income_rate", 0.30}},
        first_request.proposal_id);
    auto replacement = coordinator.submit(
        world, scheduler, world.tick(), replacement_request, "player",
        events);
    assert(replacement.ok());
    assert(replacement.get_if()->status ==
           M11DecisionStatus::accepted_pending);
    const auto *superseded =
        coordinator.find_decision(first.get_if()->decision_id);
    assert(superseded != nullptr);
    assert(superseded->status == M11DecisionStatus::superseded);

    auto cancelled = coordinator.cancel(
        world.tick(), replacement.get_if()->decision_id,
        "cancel-tax-replacement", "player", events);
    assert(cancelled.ok());
    assert(cancelled.get_if()->status == M11DecisionStatus::cancelled);
    assert(coordinator.budgets().size() == 1U);
    assert(coordinator.budgets().front().reserved == 0.0);
    assert(coordinator.budgets().front().remaining ==
           coordinator.budgets().front().capacity);
}

void test_symmetric_world_conflict_fails_both_peggers() {
    auto world = build_world();
    auto scheduler_result = M11DecisionScheduler::create();
    auto coordinator_result = M11PolicyCoordinator::create(world);
    assert(scheduler_result.ok() && coordinator_result.ok());
    auto scheduler = std::move(*scheduler_result.get_if());
    auto coordinator = std::move(*coordinator_result.get_if());
    M11EventStream events(256U);
    std::vector<std::string> decisions;
    for (std::uint32_t economy = 0U; economy < 2U; ++economy) {
        auto context = coordinator.open_context(
            world, scheduler, world.tick(), EconomyId(economy),
            "central_bank", "fx_operations", Tick(1U));
        assert(context.ok());
        auto request = proposal(
            *context.get_if(),
            "proposal-peg-" + std::to_string(economy),
            "idem-peg-" + std::to_string(economy),
            {
                {EconomyId(economy), "fx_regime", std::string("peg")},
                {EconomyId(economy), "peg_anchor",
                 std::int64_t{economy == 0U ? 1 : 0}},
            });
        auto accepted = coordinator.submit(
            world, scheduler, world.tick(), std::move(request),
            "player", events);
        assert(accepted.ok());
        decisions.push_back(accepted.get_if()->decision_id);
    }
    assert(world.advance(7U).ok());
    auto plan = coordinator.prepare_due(world, world.tick());
    assert(plan.ok());
    assert(plan.get_if()->effective_decision_ids.empty());
    assert(plan.get_if()->failed_decision_ids.size() == 2U);
    assert(coordinator.commit_due(*plan.get_if(), events).ok());
    for (const auto &decision_id : decisions) {
        const auto *decision = coordinator.find_decision(decision_id);
        assert(decision != nullptr);
        assert(decision->status ==
               M11DecisionStatus::failed_at_execution);
    }
    assert(world.external_policies()[0U].fx_regime ==
           FxRegime::floating);
    assert(world.external_policies()[1U].fx_regime ==
           FxRegime::floating);
}

void test_emergency_context_has_cross_group_controls() {
    auto world = build_world();
    auto scheduler_result = M11DecisionScheduler::create();
    auto coordinator_result = M11PolicyCoordinator::create(world);
    assert(scheduler_result.ok() && coordinator_result.ok());
    auto scheduler = std::move(*scheduler_result.get_if());
    auto coordinator = std::move(*coordinator_result.get_if());
    auto context = coordinator.open_context(
        world, scheduler, world.tick(), EconomyId(0U), "treasury",
        "emergency", Tick(1U), true, "exogenous_supply_crisis");
    assert(context.ok());
    assert(context.get_if()->administrative_capacity == 20.0);
    assert(std::any_of(
        context.get_if()->permitted_actions.begin(),
        context.get_if()->permitted_actions.end(),
        [](const M11PermittedAction &entry) {
            return entry.lever == "gov_consumption_share";
        }));
}

} // namespace

int main() {
    test_submission_idempotency_and_effective_commit();
    test_cancel_and_supersede_refunds();
    test_symmetric_world_conflict_fails_both_peggers();
    test_emergency_context_has_cross_group_controls();
    return 0;
}
