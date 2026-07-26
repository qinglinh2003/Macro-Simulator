#include <cassert>
#include <cstdint>
#include <string>
#include <utility>

#include "macro_sim/control/m11_policy.hpp"
#include "macro_sim/control/m11_session.hpp"
#include "macro_sim/desktop/m11_new_game.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::desktop;
using namespace macro_sim::simulation;

[[nodiscard]] std::string new_game_document(
    std::string_view scenario = "sandbox") {
    return std::string(R"JSON({
        "schema_version":1,
        "seed":17,
        "start_date":"2024-02-29",
        "scenario":")JSON") +
           std::string(scenario) +
           R"JSON(",
        "duration":365,
        "performance_scale":"fast",
        "world":{
            "trade":true,
            "capital":true,
            "migration":true,
            "fx_lambda":0.05,
            "fx_friction":0.03,
            "fx_trade_cap":0.15,
            "capital_mobility":1.0,
            "capital_adjust":0.2,
            "migration_rate":0.02,
            "migration_max_share":0.25,
            "remittance_share":0.2,
            "wage_smoothing":0.02,
            "peg_reserves0":5000.0
        },
        "countries":[
            {
                "name":"Aurelia",
                "code":"AUR",
                "profile":"advanced",
                "overrides":{
                    "demographics_population":95,
                    "n_firms_c":13,
                    "n_firms_k":5,
                    "n_firms_e":3,
                    "n_builders":4,
                    "n_banks":3
                }
            },
            {
                "name":"Borvia",
                "code":"BOL",
                "profile":"developing",
                "overrides":{}
            }
        ],
        "player_country":0,
        "run_mode":"interactive",
        "seats":{
            "treasury":"human",
            "cb":"heuristic",
            "regulator":"null",
            "external":"fuzz",
            "energy":"scheduled"
        },
        "initial_policy_overrides":{
            "0.treasury.gov_deficit_target":0.02
        }
    })JSON";
}

void test_default_is_complete_latest_world() {
    auto game = default_m11_native_new_game(23U);
    assert(game.ok());
    assert(game.get_if()->model_id ==
           kM11PlayableModelId);
    assert(game.get_if()->countries.size() == 3U);
    assert(game.get_if()->controller.worker_count == 8U);
    for (const auto &economy : game.get_if()->world.economies) {
        const auto &population = economy.domestic_economy;
        const auto &financial = population.financial_economy;
        const auto &monetary = financial.monetary_economy;
        assert(population.rules.fertility);
        assert(population.rules.mortality);
        assert(population.rules.persistent_labor);
        assert(population.rules.frictional_search);
        assert(population.rules.family_transfers);
        assert(financial.rules.bonds);
        assert(financial.rules.firm_equity);
        assert(financial.rules.bank_equity);
        assert(monetary.rules.interbank);
        assert(monetary.rules.household_credit);
        assert(economy.energy_rules.enabled);
        assert(economy.energy_rules.household_energy);
        assert(economy.housing_rules.enabled);
        assert(economy.housing_rules.resale_market);
        assert(economy.housing_rules.mortgages);
        assert(economy.housing_rules.rentals);
        assert(economy.housing_rules.construction);
    }
    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    auto engine = EngineSession::create(
        std::move(*world.get_if()), 256U);
    assert(engine.ok());
    auto session = M11ControlledSession::create(
        std::move(*engine.get_if()),
        std::move(game.get_if()->controller));
    assert(session.ok());
    assert(session.get_if()->engine().world().economy_count() ==
           3U);
}

void test_profiles_counts_policy_and_calendar_are_native() {
    auto game =
        parse_m11_native_new_game(new_game_document());
    assert(game.ok());
    assert(game.get_if()->seed == 17U);
    assert(game.get_if()->start_date == "2024-02-29");
    assert(game.get_if()->player_economy == 0U);
    assert(game.get_if()->world.economies.size() == 2U);
    const auto &first = game.get_if()->world.economies[0U];
    const auto &population = first.domestic_economy;
    const auto &financial = population.financial_economy;
    const auto &monetary = financial.monetary_economy;
    const auto &real = monetary.real_economy;
    assert(population.population.initial_persons == 95U);
    assert(real.households == 38U);
    assert(real.consumption_firms == 13U);
    assert(real.capital_firms == 5U);
    assert(first.energy_rules.producer_count == 3U);
    assert(first.housing_rules.builder_count == 4U);
    assert(monetary.rules.bank_count == 3U);
    assert(real.settlement_banks == 3U);
    assert(real.rules.linear_productivity == 1.2);
    assert(real.rules.capital_productivity == 2.88);
    assert(first.energy_rules.producer_productivity == 1.05);
    assert(game.get_if()->initial_policy_actions.size() == 1U);
    assert(game.get_if()->controller.assignments.size() == 5U);

    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    auto batch = project_m11_policy_actions(
        *world.get_if(),
        game.get_if()->initial_policy_actions);
    assert(batch.ok());
    assert(world.get_if()
               ->update_policy_batch(*batch.get_if())
               .ok());
    auto policy =
        world.get_if()->domestic_policy(EconomyId(0U));
    assert(policy.ok());
    assert(policy.get_if()
               ->fiscal_monetary
               .government_deficit_target == 0.02);
}

void test_native_crisis_scenarios_are_live() {
    for (const auto scenario :
         {"oil", "gfc", "pandemic", "disaster"}) {
        auto game =
            parse_m11_native_new_game(
                new_game_document(scenario));
        assert(game.ok());
        assert(!game.get_if()->world.shocks.empty());
        auto world = M9World::create(game.get_if()->world);
        assert(world.ok());
    }
}

void test_invalid_contract_is_rejected() {
    auto malformed =
        parse_m11_native_new_game("{not-json}");
    assert(malformed.status().code() ==
           ErrorCode::corrupt_input);
    auto extra = new_game_document();
    const auto position = extra.rfind('}');
    assert(position != std::string::npos);
    extra.insert(position, R"JSON(,"unknown":true)JSON");
    assert(!parse_m11_native_new_game(extra).ok());

    auto invalid_date = new_game_document();
    const auto date = invalid_date.find("2024-02-29");
    assert(date != std::string::npos);
    invalid_date.replace(date, 10U, "2023-02-29");
    assert(!parse_m11_native_new_game(invalid_date).ok());
}

} // namespace

int main() {
    test_default_is_complete_latest_world();
    test_profiles_counts_policy_and_calendar_are_native();
    test_native_crisis_scenarios_are_live();
    test_invalid_contract_is_rejected();
    return 0;
}
