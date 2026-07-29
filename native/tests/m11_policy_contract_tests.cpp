#include <array>
#include <cassert>
#include <cstdint>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "macro_sim/control/m11_policy.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec domestic_spec(std::uint64_t seed) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 8;
    real.consumption_firms = 2;
    real.capital_firms = 1;
    real.seed = seed;
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
    value.energy_rules.producer_count = 1;
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
    spec.economies.push_back(domestic_spec(1201U));
    spec.economies.push_back(domestic_spec(1202U));
    spec.external_policies.resize(2U);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

void test_catalog_is_complete_and_sorted() {
    const auto levers = m11_policy_levers();
    assert(levers.size() == 102U);
    assert(kM11PolicyContractSha256 ==
           "b871cbf679516a6012658e715ab0b3e099d31076e387fa70bd69b8edaaae23a4");
    std::set<std::string_view> seats;
    std::set<std::string_view> groups;
    for (std::size_t index = 0; index < levers.size(); ++index) {
        const auto &lever = levers[index];
        assert(!lever.name.empty());
        assert(!lever.owner_role.empty());
        assert(!lever.decision_group.empty());
        assert(!lever.cost_class.empty());
        assert(lever.administrative_weight > 0.0);
        if (index > 0U) {
            assert(levers[index - 1U].name < lever.name);
        }
        seats.insert(lever.owner_role);
        groups.insert(lever.decision_group);
        assert(find_m11_policy_lever(lever.name) == &lever);
    }
    assert(seats.size() == 6U);
    assert(groups.size() == 12U);
    const std::array<std::string_view, 7U> labor_social{{
        "benefit_income_floor",
        "benefit_replacement",
        "jg_public_works_share",
        "jg_wage_ratio",
        "job_guarantee",
        "min_wage",
        "pension_replacement",
    }};
    for (const auto name : labor_social) {
        const auto *lever = find_m11_policy_lever(name);
        assert(lever != nullptr);
        assert(lever->owner_role == "labor_social");
        assert(lever->decision_group == "labor_and_welfare");
    }
    assert(find_m11_policy_lever("absent") == nullptr);
}

void test_every_lever_reads_and_noop_projects() {
    auto world = build_world();
    const auto domestic = world.domestic_policy(EconomyId(0U));
    assert(domestic.ok());
    const auto &external = world.external_policies()[0U];
    std::vector<NativePolicyAction> actions;
    for (const auto &lever : m11_policy_levers()) {
        auto value = m11_policy_value(*domestic.get_if(), external, lever.name);
        assert(value.ok());
        assert(validate_m11_policy_value(lever, *value.get_if(), EconomyId(0U),
                                         world.economy_count())
                   .ok());
        actions.push_back({EconomyId(0U), std::string(lever.name), *value.get_if()});
    }
    auto batch = project_m11_policy_actions(world, actions);
    assert(batch.ok());
    assert(batch.get_if()->expected_generation == world.policy_generation());
    for (const auto &action : actions) {
        auto projected = m11_policy_value(batch.get_if()->domestic[0U],
                                          batch.get_if()->external[0U], action.lever);
        assert(projected.ok());
        assert(m11_policy_values_equal(*projected.get_if(), action.value));
    }
}

void test_multi_lever_projection_and_atomic_constraints() {
    auto world = build_world();
    const std::vector<NativePolicyAction> actions{
        {EconomyId(0U), "gov_deficit_target", 0.01},
        {EconomyId(0U), "manual_policy_rate", 0.001},
        {EconomyId(0U), "monetary_regime", std::string("manual")},
        {EconomyId(0U), "bank_resolution_fund", false},
        {EconomyId(0U), "fx_regime", std::string("peg")},
        {EconomyId(0U), "peg_anchor", std::int64_t{1}},
        {EconomyId(1U), "tariff", 0.25},
    };
    auto projected = project_m11_policy_actions(world, actions);
    assert(projected.ok());
    const auto &first = projected.get_if()->domestic[0U];
    assert(first.fiscal_monetary.government_deficit_target == 0.01);
    assert(first.fiscal_monetary.monetary_regime == MonetaryRegime::manual);
    assert(first.fiscal_monetary.manual_policy_rate == 0.001);
    assert(!first.fiscal_monetary.state_resolution_backstop);
    assert(!first.financial.bank_resolution_fund);
    assert(projected.get_if()->external[0U].fx_regime == FxRegime::peg);
    assert(projected.get_if()->external[0U].peg_anchor == EconomyId(1U));
    assert(projected.get_if()->external[1U].tariff == 0.25);

    const std::vector<NativePolicyAction> missing_manual{
        {EconomyId(0U), "monetary_regime", std::string("manual")},
    };
    assert(!project_m11_policy_actions(build_world(), missing_manual).ok());

    const std::vector<NativePolicyAction> competing_pegs{
        {EconomyId(0U), "fx_regime", std::string("peg")},
        {EconomyId(0U), "peg_anchor", std::int64_t{1}},
        {EconomyId(1U), "fx_regime", std::string("peg")},
        {EconomyId(1U), "peg_anchor", std::int64_t{0}},
    };
    assert(!project_m11_policy_actions(build_world(), competing_pegs).ok());
}

void test_type_range_and_duplicate_rejection() {
    auto world = build_world();
    const std::vector<NativePolicyAction> wrong_type{
        {EconomyId(0U), "tariff", true},
    };
    assert(project_m11_policy_actions(world, wrong_type).status().code() ==
           ErrorCode::invalid_argument);
    const std::vector<NativePolicyAction> out_of_range{
        {EconomyId(0U), "tariff", 6.0},
    };
    assert(project_m11_policy_actions(world, out_of_range).status().code() ==
           ErrorCode::out_of_range);
    const std::vector<NativePolicyAction> duplicate{
        {EconomyId(0U), "tariff", 0.1},
        {EconomyId(0U), "tariff", 0.2},
    };
    assert(project_m11_policy_actions(world, duplicate).status().code() ==
           ErrorCode::already_exists);
    const std::vector<NativePolicyAction> invalid_set{
        {EconomyId(0U), "sanctions_imposed_on",
         PolicyEconomySet{EconomyId(1U), EconomyId(1U)}},
    };
    assert(!project_m11_policy_actions(world, invalid_set).ok());
}

} // namespace

int main() {
    test_catalog_is_complete_and_sorted();
    test_every_lever_reads_and_noop_projects();
    test_multi_lever_projection_and_atomic_constraints();
    test_type_range_and_duplicate_rejection();
    return 0;
}
