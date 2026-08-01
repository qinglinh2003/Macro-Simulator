#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <string>
#include <utility>

#include "macro_sim/control/m11_frontend.hpp"

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
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
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
    spec.economies.push_back(economy_spec(4401U));
    spec.economies.push_back(economy_spec(4402U));
    spec.external_policies.resize(2U);
    auto world = M9World::create(spec);
    assert(world.ok());
    auto result = EngineSession::create(std::move(*world.get_if()), 4096U);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] bool has_release(const M11FrontendSnapshot &snapshot,
                               std::string_view series_id) {
    return std::ranges::any_of(snapshot.releases,
                               [series_id](const M11ReleasedObservation &release) {
                                   return release.series_id == series_id;
                               });
}

[[nodiscard]] const M11FrontendMetric *
find_metric(const M11FrontendSnapshot &snapshot, std::string_view stable_id) {
    const auto iterator = std::ranges::lower_bound(
        snapshot.metrics, stable_id, {}, &M11FrontendMetric::stable_id);
    return iterator == snapshot.metrics.end() ||
            iterator->stable_id != stable_id
        ? nullptr
        : &*iterator;
}

void test_snapshot_is_role_scoped_and_deterministic() {
    auto session = M11ControlledSession::create(engine());
    assert(session.ok());
    assert(session.get_if()->advance_until_decision({2U, false}).ok());
    M11FrontendProjection projection;
    auto treasury = projection.snapshot(
        *session.get_if(), {"player", EconomyId(0U), "treasury"}, "epoch-a", 7U);
    auto central_bank = projection.snapshot(
        *session.get_if(), {"player", EconomyId(0U), "central_bank"}, "epoch-a", 7U);
    assert(treasury.ok());
    assert(central_bank.ok());
    assert(!treasury.get_if()->metrics.empty());
    assert(std::ranges::is_sorted(treasury.get_if()->metrics, {},
                                  &M11FrontendMetric::stable_id));
    assert(std::ranges::is_sorted(treasury.get_if()->policies, {},
                                  &M11FrontendPolicy::lever));
    for (const auto stable_id : {
             "metric.economy.hh_wealth_gini",
             "metric.economy.wage_p90_p10_ratio",
             "metric.economy.welfare_log",
             "metric.economy.savings_rate",
             "metric.economy.income_decile_1_share",
             "metric.economy.wealth_decile_10_share",
             "metric.economy.consumption_decile_10_share",
        }) {
        const auto *metric = find_metric(*treasury.get_if(), stable_id);
        assert(metric != nullptr);
        if (std::string_view(stable_id).find("decile") !=
            std::string_view::npos) {
            assert(metric->value.has_value());
        }
    }
    for (const auto &policy : treasury.get_if()->policies) {
        const auto *lever = find_m11_policy_lever(policy.lever);
        assert(lever != nullptr);
        assert(lever->owner_role == "treasury");
    }
    for (const auto &policy : central_bank.get_if()->policies) {
        const auto *lever = find_m11_policy_lever(policy.lever);
        assert(lever != nullptr);
        assert(lever->owner_role == "central_bank");
    }
    assert(!has_release(*treasury.get_if(), "bank_reserves_total"));
    assert(has_release(*central_bank.get_if(), "bank_reserves_total"));
    assert(treasury.get_if()->snapshot_id ==
           m11_frontend_snapshot_id(*treasury.get_if()));
    assert(central_bank.get_if()->snapshot_id ==
           m11_frontend_snapshot_id(*central_bank.get_if()));
    for (const auto &event : treasury.get_if()->public_events) {
        assert(event.visibility == M11EventVisibility::public_record);
    }
}

void test_delta_requires_exact_base_and_reports_changes() {
    auto session = M11ControlledSession::create(engine());
    assert(session.ok());
    M11FrontendProjection projection;
    const M11AccessScope scope{"player", EconomyId(0U), "treasury"};
    auto base = projection.snapshot(*session.get_if(), scope, "epoch-b", 1U);
    assert(base.ok());
    assert(session.get_if()->advance_until_decision({1U, true}).ok());
    auto result = projection.snapshot(*session.get_if(), scope, "epoch-b", 2U);
    assert(result.ok());
    auto delta = projection.delta(*base.get_if(), *result.get_if());
    assert(delta.ok());
    assert(delta.get_if()->base_snapshot_id == base.get_if()->snapshot_id);
    assert(delta.get_if()->result_snapshot_id == result.get_if()->snapshot_id);
    assert(delta.get_if()->result_sequence == 2U);
    assert(delta.get_if()->boundary == Tick(1U));

    auto wrong_sequence = *result.get_if();
    wrong_sequence.snapshot_sequence = 3U;
    wrong_sequence.snapshot_id = m11_frontend_snapshot_id(wrong_sequence);
    assert(projection.delta(*base.get_if(), wrong_sequence).status().code() ==
           ErrorCode::stale_handle);

    auto wrong_epoch = *result.get_if();
    wrong_epoch.cache_epoch = "epoch-c";
    wrong_epoch.snapshot_id = m11_frontend_snapshot_id(wrong_epoch);
    assert(projection.delta(*base.get_if(), wrong_epoch).status().code() ==
           ErrorCode::stale_handle);

    auto tampered_base = *base.get_if();
    assert(!tampered_base.metrics.empty());
    tampered_base.metrics.front().stable_id = "tampered";
    assert(projection.delta(tampered_base, *result.get_if()).status().code() ==
           ErrorCode::stale_handle);
}

void test_distribution_projection_is_populated_after_warmup() {
    auto session = M11ControlledSession::create(engine());
    assert(session.ok());
    assert(session.get_if()->advance_until_decision({90U, false}).ok());
    M11FrontendProjection projection;
    const auto snapshot = projection.snapshot(
        *session.get_if(), {"player", EconomyId(0U), "treasury"},
        "distribution-warmup", 1U);
    assert(snapshot.ok());
    for (const auto stable_id : {
             "metric.economy.hh_wealth_gini",
             "metric.economy.wage_p90_p10_ratio",
             "metric.economy.welfare_log",
             "metric.economy.savings_rate",
             "metric.economy.bottom10_consumption",
         }) {
        const auto *metric = find_metric(*snapshot.get_if(), stable_id);
        assert(metric != nullptr);
        assert(metric->value.has_value());
        assert(std::isfinite(*metric->value));
    }
    for (const auto prefix : {
             "metric.economy.income_decile_",
             "metric.economy.wealth_decile_",
             "metric.economy.consumption_decile_",
         }) {
        double total = 0.0;
        for (std::size_t decile = 1U; decile <= 10U; ++decile) {
            const auto stable_id =
                std::string(prefix) + std::to_string(decile) + "_share";
            const auto *metric =
                find_metric(*snapshot.get_if(), stable_id);
            assert(metric != nullptr);
            assert(metric->value.has_value());
            total += *metric->value;
        }
        assert(std::abs(total - 1.0) < 1.0e-9);
    }
}

void test_context_projection_is_private_and_fully_hashed() {
    M11ControllerRunSpec run_spec;
    M11OccupantSpec human;
    human.kind = M11OccupantKind::human_queue;
    human.occupant_id = "human";
    run_spec.assignments.push_back({EconomyId(0U), "treasury", std::move(human)});
    auto session = M11ControlledSession::create(engine(), std::move(run_spec));
    assert(session.ok());
    auto paused = session.get_if()->advance_until_decision({1U, true});
    assert(paused.ok() && paused.get_if()->awaiting_human);

    M11FrontendProjection projection;
    auto treasury = projection.snapshot(
        *session.get_if(), {"player", EconomyId(0U), "treasury"}, "epoch-d", 1U);
    auto regulator = projection.snapshot(
        *session.get_if(), {"player", EconomyId(0U), "regulator"}, "epoch-d", 1U);
    assert(treasury.ok());
    assert(regulator.ok());
    assert(!treasury.get_if()->contexts.empty());
    for (const auto &context : treasury.get_if()->contexts) {
        assert(context.economy == EconomyId(0U));
        assert(context.seat == "treasury");
    }
    for (const auto &context : regulator.get_if()->contexts) {
        assert(context.economy == EconomyId(0U));
        assert(context.seat == "regulator");
    }

    auto changed = *treasury.get_if();
    changed.contexts.front().administrative_capacity += 1.0;
    assert(m11_frontend_snapshot_id(changed) != treasury.get_if()->snapshot_id);
    if (!changed.contexts.front().permitted_actions.empty()) {
        changed = *treasury.get_if();
        changed.contexts.front().permitted_actions.front().reason_code = "tampered";
        assert(m11_frontend_snapshot_id(changed) != treasury.get_if()->snapshot_id);
    }
}

void test_invalid_scope_is_rejected() {
    auto session = M11ControlledSession::create(engine());
    assert(session.ok());
    M11FrontendProjection projection;
    assert(!projection
                .snapshot(*session.get_if(), {"", EconomyId(0U), "treasury"}, "epoch-e",
                          1U)
                .ok());
    assert(!projection
                .snapshot(*session.get_if(), {"player", EconomyId(9U), "treasury"},
                          "epoch-e", 1U)
                .ok());
    assert(!projection
                .snapshot(*session.get_if(), {"player", EconomyId(0U), "invalid-seat"},
                          "epoch-e", 1U)
                .ok());
}

} // namespace

int main() {
    test_snapshot_is_role_scoped_and_deterministic();
    test_delta_requires_exact_base_and_reports_changes();
    test_distribution_projection_is_populated_after_warmup();
    test_context_projection_is_private_and_fully_hashed();
    test_invalid_scope_is_rejected();
    return 0;
}
