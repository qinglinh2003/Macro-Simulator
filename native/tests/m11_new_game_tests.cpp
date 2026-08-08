#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
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

void assert_close(double left, double right, double tolerance = 1.0e-10) {
    if (std::abs(left - right) > tolerance) {
        std::cerr << "assert_close failed: left=" << left << " right=" << right
                  << " tolerance=" << tolerance << "\n";
    }
    assert(std::abs(left - right) <= tolerance);
}

[[nodiscard]] std::string new_game_document(std::string_view scenario = "sandbox") {
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
                    "n_banks":3,
                    "necessity_share0":0.75
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
            "labor_social":"null",
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
    assert(game.get_if()->model_id == kM11PlayableModelId);
    assert(game.get_if()->countries.size() == 3U);
    assert(game.get_if()->controller.worker_count == 8U);
    for (const auto &economy : game.get_if()->world.economies) {
        const auto &population = economy.domestic_economy;
        const auto &financial = population.financial_economy;
        const auto &monetary = financial.monetary_economy;
        const auto &real = monetary.real_economy;
        assert(population.rules.fertility);
        assert(population.rules.mortality);
        assert(population.rules.persistent_labor);
        assert(population.rules.frictional_search);
        assert(population.rules.person_efficiency);
        assert_close(population.rules.efficiency_sigma, 0.35);
        assert_close(population.rules.genesis_employment_rate, 0.95);
        assert(population.rules.family_transfers);
        assert(real.stochastic);
        assert(financial.rules.bonds);
        assert(financial.rules.firm_equity);
        assert(financial.rules.bank_equity);
        assert(financial.rules.firm_subscale_exit);
        assert(financial.rules.capital_firm_entry);
        assert(std::abs(monetary.rules.firm_amortization - 1.0 / (365.0 * 2.5)) <
               1.0e-12);
        assert(std::abs(monetary.rules.household_amortization - 1.0 / (365.0 * 5.0)) <
               1.0e-12);
        assert_close(monetary.initial_policy_rate, 1.34e-4);
        assert_close(monetary.policy.inflation_target, 5.4e-5);
        assert_close(monetary.policy.taylor_inflation, 1.20);
        assert_close(monetary.policy.taylor_unemployment, 0.0014);
        assert_close(monetary.policy.rate_inertia, 0.9924);
        assert_close(monetary.policy.neutral_rate, 1.34e-4);
        assert_close(monetary.policy.maximum_policy_rate, 5.0e-4);
        assert_close(monetary.policy.inflation_sensor_lambda, 0.0019);
        assert(monetary.policy.logarithmic_inflation);
        assert_close(monetary.policy.reserve_gap_close, 0.094);
        assert(monetary.policy.reserve_target_indexes_deposits);
        assert_close(monetary.rules.interbank_tightness, 0.0013698630136986301);
        assert_close(monetary.rules.run_fear_persistence, 0.952);
        assert_close(financial.policy.bond_coupon_rate, 1.08e-4);
        assert(financial.policy.bankrupt_persistence == 548U);
        assert(financial.rules.bankrupt_persistence == 548U);
        assert(financial.rules.shell_exit_days == 365U);
        assert_close(financial.rules.entry_hurdle, 1.34e-4);
        assert_close(financial.rules.equity_price_adjustment, 0.13);
        assert_close(financial.rules.equity_trend_lambda, 0.023);
        assert_close(financial.rules.residual_income_lambda, 0.0019);
        assert_close(financial.rules.portfolio_adjustment, 0.048);
        assert_close(financial.rules.bank_equity_lambda, 0.0019);
        assert_close(financial.rules.household_equity_target, 0.30);
        assert_close(real.rules.wage_calvo_probability, 0.011);
        assert_close(real.rules.price_calvo_probability, 0.0037);
        assert_close(real.rules.public_capital_gamma, 0.10);
        assert_close(real.rules.job_guarantee_productivity, 0.50);
        assert(economy.housing_rules.builder_land_fee_credit);
        assert_close(economy.housing_rules.initial_builder_cash_buffer, 25.0);
        assert_close(economy.housing_rules.builder_demand_seed, 0.0);
        assert_close(economy.housing_rules.ask_floor_annual_wage_share, 2.0);
        assert_close(economy.housing_rules.ask_decay, 0.005);
        assert_close(financial.rules.switch_retool_loss, 0.05);
        assert(monetary.rules.interbank);
        assert(monetary.rules.household_credit);
        assert(economy.energy_rules.enabled);
        assert(economy.energy_rules.household_energy);
        assert_close(economy.energy_rules.initial_price, 1.20);
        assert_close(economy.energy_rules.producer_inventory_ratio, 14.0);
        assert_close(economy.energy_rules.household_need, 0.07 / 1.20);
        assert_close(economy.energy_rules.downstream_coverage_days, 14.0);
        assert_close(economy.energy_rules.downstream_gap_close, 0.02);
        assert(economy.housing_rules.enabled);
        assert(economy.housing_rules.resale_market);
        assert(economy.housing_rules.mortgages);
        assert(economy.housing_rules.rentals);
        assert(economy.housing_rules.construction);
        assert_close(real.rules.income_propensity, 0.97);
        assert_close(real.rules.total_factor_productivity, 0.17033823412749668);
        assert_close(real.rules.capital_output_ratio, 912.5);
        assert_close(real.rules.demand_adjustment, 0.0038);
        assert_close(real.rules.initial_consumption_capital, 7300.0);
        assert_close(real.rules.initial_price, 0.80);
        assert(real.rules.capital_rationed_signal);
        assert(!real.rules.consumption_rationed_signal);
        assert_close(monetary.policy.government_consumption_share, 0.20);
        assert_close(monetary.policy.government_deficit_target, 0.03);
        assert_close(monetary.policy.income_tax_rate, 0.25);
        assert(monetary.policy.bank_capital_constraint);
        assert(monetary.policy.unified_bank_rwa);
        assert(monetary.policy.state_resolution_backstop);
        assert(monetary.rules.opening_capital_per_bank > 0.0);
        assert_close(population.policy.pension_replacement, 0.20);
        assert_close(population.rules.marriage_rules.assortativity, 1.0);
    }
    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    for (std::size_t economy_index = 0U;
         economy_index < world.get_if()->economy_count(); ++economy_index) {
        const auto *population =
            world.get_if()->economy_population_runtime(EconomyId(economy_index));
        assert(population != nullptr);
        std::size_t participants = 0U;
        for (const auto person_id : population->persons.alive_ids()) {
            participants += population->persons.get(person_id)->participating ? 1U : 0U;
        }
        assert(population->employment.active_count() ==
               static_cast<std::size_t>(
                   std::llround(population->rules.genesis_employment_rate *
                                static_cast<double>(participants))));
    }
    M9AdvanceOptions baseline_options;
    baseline_options.worker_count = 8U;
    auto baseline = world.get_if()->advance(1825U, baseline_options);
    if (!baseline.ok()) {
        std::cerr << "native default baseline failed: " << baseline.status().message()
                  << "\n";
    }
    assert(baseline.ok());
    assert(baseline.get_if()->advanced_ticks == 1825U);
    assert(baseline.get_if()->metrics.domestic.size() == 3U);
    for (const auto &metrics : baseline.get_if()->metrics.domestic) {
        assert(std::isfinite(metrics.economy.economy.economy.economy.real_output));
        assert(metrics.economy.economy.economy.economy.real_output > 0.0);
        assert(std::isfinite(metrics.economy.unemployment_rate));
        assert(metrics.economy.unemployment_rate >= 0.0);
        // This fast topology fixture contains only 64-120 persons per country.
        // Macroeconomic calibration bounds are evaluated by the maintained
        // 100,000-person product baseline, not by finite-population tails here.
        assert(metrics.economy.unemployment_rate <= 1.0);
        assert(std::abs(metrics.economy.economy.economy.economy.price_index - 0.80) >
               1.0e-3);
    }
    for (std::size_t economy_index = 0U;
         economy_index < world.get_if()->economy_count(); ++economy_index) {
        const auto *root = world.get_if()->economy_root(EconomyId(economy_index));
        assert(root != nullptr);
        root->banks.for_each_alive([root, economy_index](
                                       BankId id, const core::BankComponent &bank) {
            if (!bank.alive) {
                return;
            }
            const auto reserve = root->reserves.balance(bank.settlement_node);
            assert(reserve.ok());
            if (reserve.get_if()->value() < -1.0e-9) {
                std::cerr << "alive bank has negative closing reserves: bank="
                          << id.value() << " economy=" << economy_index
                          << " reserve=" << reserve.get_if()->value() << "\n";
                root->banks.for_each_alive(
                    [root](BankId candidate,
                           const core::BankComponent &candidate_bank) {
                        const auto candidate_reserve =
                            root->reserves.balance(candidate_bank.settlement_node);
                        std::cerr << "  bank=" << candidate.value()
                                  << " alive=" << candidate_bank.alive << " reserve="
                                  << (candidate_reserve.ok()
                                          ? candidate_reserve.get_if()->value()
                                          : std::numeric_limits<double>::quiet_NaN())
                                  << "\n";
                    });
            }
            assert(reserve.get_if()->value() >= -1.0e-9);
        });
    }
    assert(std::isfinite(baseline.get_if()->metrics.world_nfa));
    auto engine = EngineSession::create(std::move(*world.get_if()), 256U);
    assert(engine.ok());
    auto session = M11ControlledSession::create(std::move(*engine.get_if()),
                                                std::move(game.get_if()->controller));
    assert(session.ok());
    assert(session.get_if()->engine().world().economy_count() == 3U);
}

void test_profiles_counts_policy_and_calendar_are_native() {
    auto game = parse_m11_native_new_game(new_game_document());
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
    assert_close(real.rules.necessity_need_per_unit,
                 0.75 * real.rules.initial_wage / real.rules.initial_price);
    assert(real.settlement_banks == 3U);
    assert(real.rules.linear_productivity == 1.2);
    assert(real.rules.capital_productivity == 2.88);
    assert_close(real.rules.initial_firm_money, 200.0 * 7.6 / 18.0);
    assert_close(real.rules.initial_consumption_capital, 7300.0 * 7.6 / 18.0);
    assert_close(real.rules.initial_expected_demand, 6.25 * 7.6 / 18.0);
    assert_close(real.rules.initial_consumption_inventory, 87.5 * 7.6 / 18.0);
    assert_close(real.rules.initial_capital_inventory, 87.5 * 7.6 / 18.0);
    assert(first.energy_rules.producer_productivity == 1.05);
    assert_close(first.energy_rules.initial_producer_cash, 20.0 * 0.95 / 3.0);
    assert_close(first.housing_rules.initial_builder_cash_buffer, 25.0 * 2.375 / 4.0);
    assert(monetary.rules.opening_capital_per_bank > 0.0);
    assert(game.get_if()->initial_policy_actions.size() == 1U);
    assert(game.get_if()->controller.assignments.size() == 6U);

    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    auto batch = project_m11_policy_actions(*world.get_if(),
                                            game.get_if()->initial_policy_actions);
    assert(batch.ok());
    assert(world.get_if()->update_policy_batch(*batch.get_if()).ok());
    auto policy = world.get_if()->domestic_policy(EconomyId(0U));
    assert(policy.ok());
    assert(policy.get_if()->fiscal_monetary.government_deficit_target == 0.02);
}

void test_consumption_strata_override_closes_dependent_capabilities() {
    auto document = new_game_document();
    const auto position = document.find(R"JSON("necessity_share0":0.75)JSON");
    assert(position != std::string::npos);
    document.insert(position, R"JSON("consumption_strata":false,)JSON");
    auto game = parse_m11_native_new_game(document);
    assert(game.ok());
    const auto &population = game.get_if()->world.economies[0].domestic_economy;
    const auto &financial = population.financial_economy;
    const auto &real = financial.monetary_economy.real_economy;
    assert(!real.rules.consumption_strata);
    assert(!financial.rules.consumption_strata);
    assert(!financial.rules.sector_switching);
    assert(!population.rules.family_transfers);
    assert(M9World::create(game.get_if()->world).ok());
}

void test_large_population_dividend_distribution_is_stable() {
    auto document = new_game_document();
    const std::string small_counts = R"JSON("demographics_population":95,
                    "n_firms_c":13,
                    "n_firms_k":5,
                    "n_firms_e":3,
                    "n_builders":4,
                    "n_banks":3)JSON";
    const std::string large_counts = R"JSON("demographics_population":100000,
                    "n_firms_c":1500,
                    "n_firms_k":500,
                    "n_firms_e":250,
                    "n_builders":625,
                    "n_banks":8)JSON";
    const auto position = document.find(small_counts);
    assert(position != std::string::npos);
    document.replace(position, small_counts.size(), large_counts);

    auto game = parse_m11_native_new_game(document);
    assert(game.ok());
    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    M9AdvanceOptions options;
    options.worker_count = 8U;
    const auto result = world.get_if()->advance(30U, options);
    if (!result.ok()) {
        std::cerr << "large-population baseline failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(result.get_if()->advanced_ticks == 30U);
}

void test_large_population_dividend_fallback_is_stable_without_equity() {
    auto document = new_game_document();
    const std::string small_counts = R"JSON("demographics_population":95,
                    "n_firms_c":13,
                    "n_firms_k":5,
                    "n_firms_e":3,
                    "n_builders":4,
                    "n_banks":3)JSON";
    const std::string large_counts = R"JSON("demographics_population":100000,
                    "n_firms_c":1500,
                    "n_firms_k":500,
                    "n_firms_e":250,
                    "n_builders":625,
                    "n_banks":8)JSON";
    const auto counts_position = document.find(small_counts);
    assert(counts_position != std::string::npos);
    document.replace(counts_position, small_counts.size(), large_counts);
    const auto seed_position = document.find(R"JSON("seed":17)JSON");
    assert(seed_position != std::string::npos);
    document.replace(seed_position, 9U, R"JSON("seed":211)JSON");

    auto game = parse_m11_native_new_game(document);
    assert(game.ok());
    auto &rules =
        game.get_if()->world.economies[0U].domestic_economy.financial_economy.rules;
    rules.firm_equity = false;
    rules.bank_equity = false;
    rules.bank_equity_trading = false;
    rules.equity_finance = false;
    rules.margin_credit = false;
    auto world = M9World::create(game.get_if()->world);
    assert(world.ok());
    M9AdvanceOptions options;
    options.worker_count = 8U;
    const auto result = world.get_if()->advance(30U, options);
    if (!result.ok()) {
        std::cerr << "large-population dividend fallback failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(result.get_if()->advanced_ticks == 30U);
}

void test_native_crisis_scenarios_are_live() {
    for (const auto scenario : {"oil", "gfc", "pandemic", "disaster"}) {
        auto game = parse_m11_native_new_game(new_game_document(scenario));
        assert(game.ok());
        assert(!game.get_if()->world.shocks.empty());
        auto world = M9World::create(game.get_if()->world);
        assert(world.ok());
    }
}

void test_invalid_contract_is_rejected() {
    auto malformed = parse_m11_native_new_game("{not-json}");
    assert(malformed.status().code() == ErrorCode::corrupt_input);
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
    test_consumption_strata_override_closes_dependent_capabilities();
    test_large_population_dividend_distribution_is_stable();
    test_large_population_dividend_fallback_is_stable_without_equity();
    test_native_crisis_scenarios_are_live();
    test_invalid_contract_is_rejected();
    return 0;
}
