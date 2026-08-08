#include "macro_sim/desktop/m11_new_game.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/control/m11_policy.hpp"

namespace macro_sim::desktop {
namespace {

using Json = nlohmann::json;

inline constexpr std::uint64_t kMaximumSeed = 2147483647U;
inline constexpr std::uint64_t kMaximumAgents = 50000000U;
inline constexpr std::uint64_t kMaximumDuration = 3652058U;

struct Profile final {
    double productivity{1.0};
    double scale{1.0};
    double tfp_growth{0.02};
    double fertility{2.0};
    double mortality_scale{1.0};
    double energy_productivity{1.0};
    double necessity_share{0.50};
};

[[nodiscard]] const Profile *profile(std::string_view name) noexcept {
    static constexpr Profile symmetric{};
    static constexpr Profile advanced{1.20, 1.0, 0.012, 1.6, 0.85, 1.05, 0.50};
    static constexpr Profile developing{0.75, 1.5, 0.030, 2.4, 1.20, 1.0, 0.60};
    static constexpr Profile entrepot{1.15, 0.4, 0.018, 1.3, 0.80, 0.85, 0.50};
    static constexpr Profile petrostate{0.85, 0.8, 0.010, 2.2, 0.90, 1.40, 0.50};
    if (name == "symmetric" || name == "custom") {
        return &symmetric;
    }
    if (name == "advanced") {
        return &advanced;
    }
    if (name == "developing") {
        return &developing;
    }
    if (name == "entrepot") {
        return &entrepot;
    }
    if (name == "petrostate") {
        return &petrostate;
    }
    return nullptr;
}

[[nodiscard]] bool exact_keys(const Json &value,
                              std::initializer_list<std::string_view> required,
                              std::initializer_list<std::string_view> optional = {}) {
    if (!value.is_object()) {
        return false;
    }
    std::set<std::string, std::less<>> allowed;
    for (const auto key : required) {
        allowed.emplace(key);
        if (!value.contains(key)) {
            return false;
        }
    }
    for (const auto key : optional) {
        allowed.emplace(key);
    }
    return std::ranges::all_of(value.items(), [&allowed](const auto &item) {
        return allowed.contains(item.key());
    });
}

[[nodiscard]] bool finite_number(const Json &value) {
    return value.is_number() && std::isfinite(value.get<double>());
}

[[nodiscard]] bool unsigned_integer(const Json &value, std::uint64_t minimum,
                                    std::uint64_t maximum) {
    if (!value.is_number_integer() && !value.is_number_unsigned()) {
        return false;
    }
    if (value.is_number_integer() && value.get<std::int64_t>() < 0) {
        return false;
    }
    const auto checked = value.get<std::uint64_t>();
    return checked >= minimum && checked <= maximum;
}

[[nodiscard]] std::optional<std::int32_t> calendar_ordinal(std::string_view value) {
    if (value.size() != 10U || value[4] != '-' || value[7] != '-') {
        return std::nullopt;
    }
    const auto digit = [](char input) { return input >= '0' && input <= '9'; };
    if (!std::ranges::all_of(std::array{value[0], value[1], value[2], value[3],
                                        value[5], value[6], value[8], value[9]},
                             digit)) {
        return std::nullopt;
    }
    const auto number = [value](std::size_t offset, std::size_t count) {
        std::uint32_t result = 0U;
        for (std::size_t index = 0U; index < count; ++index) {
            result =
                result * 10U + static_cast<std::uint32_t>(value[offset + index] - '0');
        }
        return result;
    };
    const auto year = static_cast<int>(number(0U, 4U));
    const auto month = static_cast<unsigned>(number(5U, 2U));
    const auto day = static_cast<unsigned>(number(8U, 2U));
    const std::chrono::year_month_day parsed{
        std::chrono::year(year), std::chrono::month(month), std::chrono::day(day)};
    if (!parsed.ok()) {
        return std::nullopt;
    }
    const auto unix_days = std::chrono::sys_days(parsed).time_since_epoch().count();
    constexpr std::int64_t python_unix_ordinal = 719163;
    const auto ordinal = static_cast<std::int64_t>(unix_days) + python_unix_ordinal;
    if (ordinal < 1 || ordinal > std::numeric_limits<std::int32_t>::max()) {
        return std::nullopt;
    }
    return static_cast<std::int32_t>(ordinal);
}

[[nodiscard]] control::M11OccupantKind occupant_kind(std::string_view value) {
    if (value == "human") {
        return control::M11OccupantKind::human_queue;
    }
    if (value == "heuristic") {
        return control::M11OccupantKind::heuristic;
    }
    if (value == "rl") {
        return control::M11OccupantKind::reinforcement_learning;
    }
    if (value == "scheduled") {
        return control::M11OccupantKind::scheduled;
    }
    if (value == "fuzz") {
        return control::M11OccupantKind::random_fuzz;
    }
    return control::M11OccupantKind::null_occupant;
}

[[nodiscard]] bool valid_occupant(std::string_view value) {
    return value == "human" || value == "null" || value == "heuristic" ||
           value == "rl" || value == "scheduled" || value == "fuzz";
}

[[nodiscard]] std::optional<std::string_view> canonical_seat(std::string_view value) {
    if (value == "cb") {
        return "central_bank";
    }
    if (value == "external") {
        return "external_affairs";
    }
    if (value == "treasury" || value == "labor_social" || value == "regulator" ||
        value == "energy") {
        return value;
    }
    return std::nullopt;
}

[[nodiscard]] Result<control::PolicyValue>
policy_value_from_json(const control::PolicyLeverDescriptor &lever, const Json &value) {
    using control::PolicyValue;
    switch (lever.kind) {
    case control::PolicyValueKind::number:
        if (finite_number(value)) {
            return PolicyValue(value.get<double>());
        }
        break;
    case control::PolicyValueKind::nullable_number:
        if (value.is_null()) {
            return PolicyValue(std::monostate{});
        }
        if (finite_number(value)) {
            return PolicyValue(value.get<double>());
        }
        break;
    case control::PolicyValueKind::integer:
    case control::PolicyValueKind::economy_id:
        if (value.is_number_integer()) {
            return PolicyValue(value.get<std::int64_t>());
        }
        if (lever.kind == control::PolicyValueKind::economy_id && value.is_null()) {
            return PolicyValue(std::monostate{});
        }
        break;
    case control::PolicyValueKind::boolean:
        if (value.is_boolean()) {
            return PolicyValue(value.get<bool>());
        }
        break;
    case control::PolicyValueKind::choice:
        if (value.is_string()) {
            return PolicyValue(value.get<std::string>());
        }
        break;
    case control::PolicyValueKind::economy_set:
        if (value.is_array()) {
            control::PolicyEconomySet result;
            result.reserve(value.size());
            for (const auto &entry : value) {
                if (!unsigned_integer(entry, 0U,
                                      simulation::kM9MaximumEconomies - 1U)) {
                    return Status(ErrorCode::invalid_argument,
                                  "new-game policy value is invalid");
                }
                result.emplace_back(entry.get<std::uint64_t>());
            }
            return PolicyValue(std::move(result));
        }
        break;
    }
    return Status(ErrorCode::invalid_argument, "new-game policy value is invalid");
}

void enable_complete_playable_modules(simulation::M8SimulationSpec &spec) {
    auto &population = spec.domestic_economy;
    auto &financial = population.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = simulation::M4Vertical::capital_fiscal;
    real.requested_capabilities =
        simulation::capability_bit(simulation::M4Capability::physical_capital) |
        simulation::capability_bit(simulation::M4Capability::government);
    // The start-menu factory selects the exogenous TFP law, but omitted default
    // values are intentionally absent from the country override object.  The
    // native new-game path must therefore seed the corresponding stochastic
    // regime here.  Leaving it false pins every Calvo draw to one, so no wage
    // or price with a probability below one can ever adjust.
    real.stochastic = true;
    // Consumption is based on smoothed permanent income.  The daily baseline
    // needs a high propensity to avoid a mechanical demand leakage that would
    // otherwise sustain double-digit unemployment without an external shock.
    real.rules.income_propensity = 0.97;
    real.rules.mpc_dispersion = 0.40;
    real.rules.mpc_wealth_curvature = 1.0;
    real.rules.consumption_strata = true;
    // The daily clock reads an annual capital-output ratio.  The opening stock
    // and TFP normalization are a joint calibration that preserves genesis
    // output while making replacement capital economically meaningful.
    real.rules.total_factor_productivity = 0.17033823412749668;
    real.rules.capital_output_ratio = 912.5;
    real.rules.demand_adjustment = 0.0038;
    real.rules.capital_clock_demand_smoothing = 0.5;
    real.rules.gibrat_growth = true;
    real.rules.gibrat_sigma = 0.0052;
    real.rules.preferential_price_elasticity = 1.0;
    real.rules.wage_calvo_probability = 0.011;
    real.rules.price_calvo_probability = 0.0037;
    real.rules.public_capital_gamma = 0.10;
    real.rules.job_guarantee_productivity = 0.50;
    real.rules.initial_consumption_capital = 7300.0;
    real.rules.initial_price = 0.80;
    real.rules.necessity_need_per_unit =
        0.50 * real.rules.initial_wage / real.rules.initial_price;
    // Open near the sustainable flow rate and carry the same fourteen days of
    // inventory targeted by the production rule.  The historical one-day
    // stock created a mechanical inventory boom and a first-year labor crash.
    real.rules.initial_expected_demand = 6.25;
    real.rules.initial_consumption_inventory = 87.5;
    real.rules.initial_capital_inventory = 87.5;
    real.rules.capital_rationed_signal = true;
    // Transient stockouts during genesis should not become a persistent
    // consumer-demand shock in the stable no-shock baseline.  The mechanism
    // remains configurable for experiments.
    real.rules.consumption_rationed_signal = false;
    real.rules.initial_capital_price = 0.80;
    // Keep the native desktop path on the same daily monetary clock as the
    // Config-backed native bridge.  The historical C++ defaults were period
    // rates: using them here meant a 1% policy rate and 10% principal
    // amortization every day.
    monetary.initial_policy_rate = 1.34e-4;
    monetary.policy.government_consumption_share = 0.20;
    monetary.policy.government_deficit_target = 0.03;
    monetary.policy.deficit_unemployment_reference = 0.05;
    monetary.policy.deficit_unemployment_cap = 4.0;
    monetary.policy.income_tax_rate = 0.25;
    monetary.policy.income_allowance = 0.50;
    monetary.policy.wealth_allowance = 1.0;
    monetary.policy.inflation_target = 5.4e-5;
    monetary.policy.taylor_inflation = 1.20;
    monetary.policy.taylor_unemployment = 0.0014;
    monetary.policy.rate_inertia = 0.9924;
    monetary.policy.neutral_rate = 1.34e-4;
    monetary.policy.maximum_policy_rate = 5.0e-4;
    monetary.policy.inflation_sensor_lambda = 0.0019;
    monetary.policy.logarithmic_inflation = true;
    monetary.policy.bank_capital_constraint = true;
    monetary.policy.unified_bank_rwa = true;
    monetary.policy.bank_leverage_cap = 0.0;
    monetary.policy.bank_exposure_limit = 0.15;
    monetary.policy.bank_target_capital_ratio = 0.18;
    monetary.policy.state_resolution_backstop = true;
    monetary.policy.open_market_operations = true;
    monetary.policy.reserve_target = 1.0;
    monetary.policy.reserve_gap_close = 0.094;
    monetary.policy.reserve_target_indexes_deposits = true;
    monetary.policy.lender_of_last_resort = true;
    monetary.policy.reserve_floor_fraction = 0.25;
    monetary.rules.bank_leverage_dispersion = 0.60;
    monetary.rules.loan_spread_dispersion = 4.466666666666667e-5;
    monetary.rules.interbank_tightness = 0.0013698630136986301;
    monetary.rules.household_subsistence = 0.50;
    monetary.rules.bank_runs = true;
    monetary.rules.run_sensitivity = 8.0;
    monetary.rules.run_fear_persistence = 0.952;
    population.policy.pension_replacement = 0.20;
    population.policy.inheritance_tax_rate = 5.479452054794521e-6;
    monetary.policy.fixed_basket_cpi = true;
    monetary.policy.fiscal_uses_national_accounts_gdp = true;
    monetary.rules.realized_bank_pnl = true;
    monetary.rules.full_firm_pnl = true;
    monetary.rules.household_credit = true;
    monetary.rules.relationship_lock_in = true;
    monetary.rules.interbank = true;
    monetary.rules.deposit_interest_arrears = false;
    monetary.rules.direct_monetary_transmission = true;
    monetary.rules.investment_user_cost_elasticity = 0.5;
    monetary.rules.investment_user_cost_multiplier_min = 0.5;
    monetary.rules.investment_user_cost_multiplier_max = 1.5;
    monetary.rules.investment_user_cost_floor = 1.0e-9;
    // Loan rates already use the daily clock.  Principal amortization must use
    // the same clock: these values imply approximately 2.5-year business loans
    // and 5-year unsecured household loans rather than ten-day maturities.
    monetary.rules.firm_amortization = 1.0 / (365.0 * 2.5);
    monetary.rules.household_amortization = 1.0 / (365.0 * 5.0);
    financial.policy.bond_coupon_rate = 1.08e-4;
    financial.policy.bond_maturity_days = 365U;
    financial.policy.bank_minimum_capital = 400.0;
    financial.policy.bankrupt_persistence = 548U;
    financial.policy.regulatory_capital_haircut = 0.30;
    financial.rules.bonds = true;
    financial.rules.bond_maturity_bucket = 30U;
    financial.rules.firm_equity = true;
    financial.rules.founder_owned_genesis = true;
    financial.rules.equity_finance = true;
    financial.rules.margin_credit = true;
    financial.rules.equity_price_adjustment = 0.13;
    financial.rules.equity_trend_lambda = 0.023;
    financial.rules.residual_income_lambda = 0.0019;
    financial.rules.q_smoothing = 1.0;
    financial.rules.q_investment_sensitivity = 0.0076;
    financial.rules.q_investment_floor = 0.50;
    financial.rules.q_investment_cap = 2.0;
    financial.rules.household_equity_wealth_smoothing = 0.0076;
    financial.rules.household_equity_wealth_effect = 0.0;
    financial.rules.fundamental_weight = 1.0;
    financial.rules.chartist_weight = 0.20;
    financial.rules.portfolio_adjustment = 0.048;
    financial.rules.valuation_discount_floor = 1.0e-9;
    financial.rules.valuation_risk_premium = 1.34e-4;
    financial.rules.capital_haircut = 0.30;
    financial.rules.firm_dynamics = true;
    financial.rules.bankrupt_persistence = 548U;
    financial.rules.shell_exit_days = 365U;
    financial.rules.entry_hurdle = 1.34e-4;
    financial.rules.entry_beta = 0.40;
    financial.rules.entry_max = 3U;
    financial.rules.startup_deposits = 15.0;
    financial.rules.startup_capital = 10.0;
    financial.rules.firm_subscale_exit = true;
    financial.rules.capital_firm_entry = true;
    financial.rules.k_entry_hazard = 1.0 / 60.0;
    financial.rules.consumption_strata = true;
    financial.rules.sector_switching = true;
    financial.rules.switch_return_gap = 0.50;
    financial.rules.switch_pressure_days = 60U;
    financial.rules.switch_retool_loss = 0.05;
    financial.rules.bank_equity = true;
    financial.rules.bank_equity_trading = true;
    financial.rules.bank_equity_lambda = 0.0019;
    financial.rules.bank_dynamics = true;
    financial.rules.household_equity_target = 0.30;
    population.rules.fertility = true;
    population.rules.mortality = true;
    population.rules.persistent_labor = true;
    population.rules.fractional_hours = true;
    population.rules.second_jobs = true;
    population.rules.suspensions = true;
    population.rules.frictional_search = true;
    population.rules.relationship_wages = true;
    population.rules.job_ladder = true;
    population.rules.person_efficiency = true;
    population.rules.genesis_employment_rate = 0.95;
    population.rules.participation_margin = true;
    population.rules.age_participation = true;
    population.rules.family_transfers = true;
    population.rules.relationships = true;
    population.rules.marriage = true;
    population.rules.divorce = true;
    population.rules.household_lifecycle = true;
    population.rules.leaving_home = true;
    population.rules.annual_marriage_rate = 0.30;
    population.rules.annual_divorce_rate = 0.012;
    population.rules.mortality_rank_gradient = 0.8;
    population.rules.fertility_rank_gradient = 0.5;
    population.rules.stratification_multiplier_minimum = 0.5;
    population.rules.stratification_multiplier_maximum = 2.0;
    population.rules.marriage_rules.assortativity = 1.0;
    spec.energy_rules.enabled = true;
    spec.energy_rules.household_energy = true;
    spec.energy_rules.deprivation = true;
    spec.energy_rules.hoarding_beta = 1.0;
    spec.energy_rules.fuel_poverty_mortality_gamma = 2.0;
    spec.energy_rules.initial_price = 1.20;
    spec.energy_rules.initial_utilization = 0.85;
    spec.energy_rules.producer_inventory_ratio = 14.0;
    spec.energy_rules.demand_adjustment = 0.0038;
    spec.energy_rules.household_need = 0.07 / spec.energy_rules.initial_price;
    spec.energy_rules.downstream_intensity = 0.05;
    spec.energy_rules.downstream_coverage_days = 14.0;
    spec.energy_rules.downstream_gap_close = 0.02;
    spec.housing_rules.enabled = true;
    spec.housing_rules.resale_market = true;
    spec.housing_rules.mortgages = true;
    spec.housing_rules.rentals = true;
    spec.housing_rules.construction = true;
    spec.housing_rules.builder_land_fee_credit = true;
    // A balanced genesis has no uncovered housing need.  A positive cold-start
    // seed otherwise finances a fractional project at every developer, leaving
    // the whole construction sector with debt but no buyer.
    spec.housing_rules.builder_demand_seed = 0.0;
    // Anchor the lower tail of stale asking prices to two years of current
    // wages.  This still permits a material housing correction without allowing
    // repeated listing markdowns to collapse the price index toward zero.
    spec.housing_rules.ask_floor_annual_wage_share = 2.0;
    spec.housing_rules.ask_decay = 0.005;
    spec.housing_rules.rental_vacancy_deadband = 0.15;
    spec.housing_rules.rent_floor_wage_share = 0.02;
    spec.housing_policy.rental_eviction_arrears = 90;
    spec.housing_rules.demand_price_step = 0.03;
    spec.housing_rules.leave_home_elasticity = 1.0;
    spec.housing_rules.fertility_elasticity = 0.5;
    spec.housing_rules.wealth_effect = 0.1;
    spec.housing_policy.mortgage_underwriting = true;
}

void scale_representative_entities(simulation::M8SimulationSpec &spec,
                                   std::uint64_t population_count) {
    auto &population = spec.domestic_economy;
    auto &real = population.financial_economy.monetary_economy.real_economy;
    const auto entity_scale = [population_count](std::uint64_t count,
                                                 double reference_density) {
        return std::max(1.0e-6,
                        reference_density * static_cast<double>(population_count) /
                            static_cast<double>(std::max<std::uint64_t>(1U, count)));
    };
    constexpr double kReferencePersonsPerHousehold = 2.5;
    const double firm_scale = entity_scale(real.consumption_firms + real.capital_firms,
                                           0.20 / kReferencePersonsPerHousehold);
    real.rules.initial_firm_money *= firm_scale;
    real.rules.initial_consumption_inventory *= firm_scale;
    real.rules.initial_capital_inventory *= firm_scale;
    real.rules.initial_consumption_capital *= firm_scale;
    real.rules.initial_expected_demand *= firm_scale;

    spec.energy_rules.initial_producer_cash *= entity_scale(
        spec.energy_rules.producer_count, 0.025 / kReferencePersonsPerHousehold);
    const double builder_scale = entity_scale(spec.housing_rules.builder_count,
                                              0.0625 / kReferencePersonsPerHousehold);
    spec.housing_rules.initial_builder_cash_buffer *= builder_scale;
    spec.housing_rules.builder_demand_seed *= builder_scale;
}

void calibrate_opening_bank_capital(simulation::M8SimulationSpec &spec) {
    auto &population = spec.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    const double private_opening_money =
        static_cast<double>(real.households) * real.rules.initial_household_money +
        static_cast<double>(real.consumption_firms + real.capital_firms) *
            real.rules.initial_firm_money +
        static_cast<double>(spec.energy_rules.producer_count) *
            spec.energy_rules.initial_producer_cash +
        static_cast<double>(spec.housing_rules.builder_count) *
            spec.housing_rules.initial_builder_cash_buffer;
    constexpr double kOpeningBankCapitalShare = 0.05;
    monetary.rules.opening_capital_per_bank =
        kOpeningBankCapitalShare * private_opening_money /
        static_cast<double>(std::max<std::uint64_t>(1U, monetary.rules.bank_count));
}

[[nodiscard]] Status apply_country_overrides(const Json &overrides,
                                             simulation::M8SimulationSpec &spec,
                                             std::uint64_t &population_count) {
    static constexpr std::array<std::string_view, 47> allowed{{
        "n_households",
        "n_firms_c",
        "n_firms_k",
        "n_firms_e",
        "n_builders",
        "n_banks",
        "demographics_population",
        "a",
        "alpha",
        "tfp_law",
        "bank_enabled",
        "interbank",
        "bonds",
        "capital_market",
        "per_firm_equity",
        "household_credit",
        "housing_enabled",
        "housing_market_enabled",
        "mortgage_enabled",
        "housing_rental_enabled",
        "housing_construction_enabled",
        "demographics_enabled",
        "consumption_strata",
        "necessity_share0",
        "n_firm_share",
        "mpc_dispersion",
        "mpc_wealth_curvature",
        "mortality_rank_gradient",
        "fertility_rank_gradient",
        "strat_mult_lo",
        "strat_mult_hi",
        "energy_enabled",
        "government",
        "national_accounts_metrics",
        "a_K",
        "tfp_drift_rate",
        "tfp_drift_sigma",
        "tfp_learning_theta",
        "tfp_drift_c",
        "tfp_drift_k",
        "tfp_drift_e",
        "lambda_q",
        "q_invest_floor",
        "q_invest_cap",
        "q_invest_smooth",
        "equity_ema_lambda",
        "wealth_effect",
    }};
    if (!overrides.is_object() ||
        !std::ranges::all_of(overrides.items(), [](const auto &item) {
            return std::ranges::find(allowed, item.key()) != allowed.end();
        })) {
        return Status(ErrorCode::invalid_argument,
                      "new-game country overrides are invalid");
    }
    auto &population = spec.domestic_economy;
    auto &financial = population.financial_economy;
    auto &monetary = financial.monetary_economy;
    auto &real = monetary.real_economy;
    const auto assign_count = [&overrides](std::string_view key,
                                           std::uint64_t &target) -> bool {
        if (!overrides.contains(key)) {
            return true;
        }
        const auto &value = overrides.at(key);
        if (!unsigned_integer(value, 1U, kMaximumAgents)) {
            return false;
        }
        target = value.get<std::uint64_t>();
        return true;
    };
    if (!assign_count("n_households", real.households) ||
        !assign_count("n_firms_c", real.consumption_firms) ||
        !assign_count("n_firms_k", real.capital_firms) ||
        !assign_count("n_firms_e", spec.energy_rules.producer_count) ||
        !assign_count("n_builders", spec.housing_rules.builder_count) ||
        !assign_count("n_banks", monetary.rules.bank_count)) {
        return Status(ErrorCode::out_of_range,
                      "new-game country count is out of range");
    }
    if (overrides.contains("demographics_population")) {
        if (!unsigned_integer(overrides.at("demographics_population"), 1U,
                              kMaximumAgents)) {
            return Status(ErrorCode::out_of_range,
                          "new-game population is out of range");
        }
        population_count = overrides.at("demographics_population").get<std::uint64_t>();
        real.households = std::max<std::uint64_t>(
            1U, static_cast<std::uint64_t>(
                    std::llround(static_cast<double>(population_count) /
                                 population.population.target_household_size)));
    } else {
        population_count = real.households;
    }
    const auto assign_number = [&overrides](std::string_view key,
                                            double &target) -> bool {
        if (!overrides.contains(key)) {
            return true;
        }
        if (!finite_number(overrides.at(key))) {
            return false;
        }
        target = overrides.at(key).get<double>();
        return true;
    };
    double necessity_share =
        real.rules.necessity_need_per_unit * real.rules.initial_price /
        real.rules.initial_wage;
    if (!assign_number("a", real.rules.linear_productivity) ||
        !assign_number("a_K", real.rules.capital_productivity) ||
        !assign_number("alpha", real.rules.capital_share) ||
        !assign_number("necessity_share0", necessity_share) ||
        !assign_number("n_firm_share", financial.rules.necessity_firm_share) ||
        !assign_number("mpc_dispersion", real.rules.mpc_dispersion) ||
        !assign_number("mpc_wealth_curvature",
                       real.rules.mpc_wealth_curvature) ||
        !assign_number("mortality_rank_gradient",
                       population.rules.mortality_rank_gradient) ||
        !assign_number("fertility_rank_gradient",
                       population.rules.fertility_rank_gradient) ||
        !assign_number("strat_mult_lo",
                       population.rules.stratification_multiplier_minimum) ||
        !assign_number("strat_mult_hi",
                       population.rules.stratification_multiplier_maximum) ||
        !assign_number("tfp_drift_rate", real.rules.annual_tfp_growth) ||
        !assign_number("tfp_drift_sigma", real.rules.annual_tfp_volatility) ||
        !assign_number("tfp_learning_theta", real.rules.tfp_learning_theta) ||
        !assign_number("tfp_drift_c", real.rules.annual_tfp_growth_consumption) ||
        !assign_number("tfp_drift_k", real.rules.annual_tfp_growth_capital) ||
        !assign_number("tfp_drift_e", real.rules.annual_tfp_growth_energy) ||
        !assign_number("lambda_q", financial.rules.q_investment_sensitivity) ||
        !assign_number("q_invest_floor", financial.rules.q_investment_floor) ||
        !assign_number("q_invest_cap", financial.rules.q_investment_cap) ||
        !assign_number("q_invest_smooth", financial.rules.q_smoothing) ||
        !assign_number("equity_ema_lambda",
                       financial.rules.household_equity_wealth_smoothing) ||
        !assign_number("wealth_effect",
                       financial.rules.household_equity_wealth_effect)) {
        return Status(ErrorCode::invalid_argument,
                      "new-game country number is invalid");
    }
    real.rules.necessity_need_per_unit =
        necessity_share * real.rules.initial_wage / real.rules.initial_price;
    const auto boolean = [&overrides](std::string_view key, bool &target) -> bool {
        if (!overrides.contains(key)) {
            return true;
        }
        if (!overrides.at(key).is_boolean()) {
            return false;
        }
        target = overrides.at(key).get<bool>();
        return true;
    };
    if (!boolean("interbank", monetary.rules.interbank) ||
        !boolean("bonds", financial.rules.bonds) ||
        !boolean("per_firm_equity", financial.rules.firm_equity) ||
        !boolean("household_credit", monetary.rules.household_credit) ||
        !boolean("housing_enabled", spec.housing_rules.enabled) ||
        !boolean("housing_market_enabled", spec.housing_rules.resale_market) ||
        !boolean("mortgage_enabled", spec.housing_rules.mortgages) ||
        !boolean("housing_rental_enabled", spec.housing_rules.rentals) ||
        !boolean("housing_construction_enabled", spec.housing_rules.construction) ||
        !boolean("demographics_enabled", population.rules.fertility) ||
        !boolean("consumption_strata", financial.rules.consumption_strata) ||
        !boolean("consumption_strata", real.rules.consumption_strata) ||
        !boolean("energy_enabled", spec.energy_rules.enabled) ||
        !boolean("national_accounts_metrics", monetary.policy.fixed_basket_cpi)) {
        return Status(ErrorCode::invalid_argument,
                      "new-game country capability is invalid");
    }
    if (overrides.contains("demographics_enabled")) {
        population.rules.mortality = population.rules.fertility;
    }
    if (overrides.contains("consumption_strata") &&
        !real.rules.consumption_strata) {
        financial.rules.sector_switching = false;
        population.rules.family_transfers = false;
    }
    if (overrides.contains("capital_market")) {
        if (!overrides.at("capital_market").is_boolean()) {
            return Status(ErrorCode::invalid_argument,
                          "new-game capital-market switch is invalid");
        }
        const bool enabled = overrides.at("capital_market").get<bool>();
        financial.rules.firm_equity = enabled;
        financial.rules.bank_equity = enabled;
        financial.rules.bank_equity_trading = enabled;
        financial.rules.equity_finance = enabled;
        financial.rules.margin_credit = enabled;
    }
    if (overrides.contains("bank_enabled")) {
        if (!overrides.at("bank_enabled").is_boolean()) {
            return Status(ErrorCode::invalid_argument,
                          "new-game bank switch is invalid");
        }
        if (!overrides.at("bank_enabled").get<bool>()) {
            monetary.rules.household_credit = false;
            monetary.rules.interbank = false;
            monetary.rules.rate_competition = false;
            monetary.rules.relationship_lock_in = false;
            financial.rules.bank_equity = false;
            financial.rules.bank_equity_trading = false;
            financial.rules.bank_dynamics = false;
        }
    }
    if (overrides.contains("government")) {
        if (!overrides.at("government").is_boolean()) {
            return Status(ErrorCode::invalid_argument,
                          "new-game government switch is invalid");
        }
        if (!overrides.at("government").get<bool>()) {
            real.requested_capabilities &=
                ~simulation::capability_bit(simulation::M4Capability::government);
            financial.rules.bonds = false;
            spec.housing_rules.construction = false;
        }
    }
    if (!spec.housing_rules.enabled) {
        spec.housing_rules.resale_market = false;
        spec.housing_rules.mortgages = false;
        spec.housing_rules.rentals = false;
        spec.housing_rules.construction = false;
    }
    if (!spec.housing_rules.resale_market) {
        spec.housing_rules.mortgages = false;
        spec.housing_rules.rentals = false;
        spec.housing_rules.construction = false;
    }
    if (!spec.energy_rules.enabled) {
        spec.energy_rules.household_energy = false;
        spec.energy_rules.deprivation = false;
    }
    if (overrides.contains("tfp_law")) {
        if (!overrides.at("tfp_law").is_string()) {
            return Status(ErrorCode::invalid_argument, "new-game TFP law is invalid");
        }
        const auto law = overrides.at("tfp_law").get<std::string>();
        if (law != "exogenous" && law != "learning") {
            return Status(ErrorCode::invalid_argument, "new-game TFP law is invalid");
        }
        real.rules.tfp_law = law == "learning"
                                 ? simulation::M4TfpLaw::learning
                                 : simulation::M4TfpLaw::exogenous;
        real.stochastic = law == "exogenous";
    }
    return Status::success();
}

[[nodiscard]] Result<M11NativeNewGame> parse_document(const Json &document) {
    if (!exact_keys(document,
                    {"schema_version", "seed", "scenario", "duration", "world",
                     "countries", "player_country", "run_mode", "seats",
                     "initial_policy_overrides"},
                    {"model_id", "start_date", "performance_scale"})) {
        return Status(ErrorCode::invalid_argument, "new-game fields are invalid");
    }
    if (!unsigned_integer(document.at("schema_version"), kM11NewGameSchemaVersion,
                          kM11NewGameSchemaVersion) ||
        !unsigned_integer(document.at("seed"), 0U, kMaximumSeed)) {
        return Status(ErrorCode::invalid_argument,
                      "new-game version or seed is invalid");
    }
    M11NativeNewGame result;
    result.seed = document.at("seed").get<std::uint64_t>();
    if (document.contains("start_date")) {
        if (!document.at("start_date").is_string()) {
            return Status(ErrorCode::invalid_argument,
                          "new-game start date is invalid");
        }
        result.start_date = document.at("start_date").get<std::string>();
    }
    const auto ordinal = calendar_ordinal(result.start_date);
    if (!ordinal.has_value()) {
        return Status(ErrorCode::invalid_argument, "new-game start date is invalid");
    }
    if (document.at("duration").is_null()) {
        result.duration_ticks = std::nullopt;
    } else if (unsigned_integer(document.at("duration"), 1U, kMaximumDuration)) {
        result.duration_ticks = document.at("duration").get<std::uint64_t>();
    } else {
        return Status(ErrorCode::out_of_range, "new-game duration is invalid");
    }
    if (!document.at("scenario").is_string()) {
        return Status(ErrorCode::invalid_argument, "new-game scenario is invalid");
    }
    const auto scenario = document.at("scenario").get<std::string>();
    if (scenario != "sandbox" && scenario != "oil" && scenario != "gfc" &&
        scenario != "pandemic" && scenario != "disaster") {
        return Status(ErrorCode::invalid_argument, "new-game scenario is invalid");
    }
    const auto scale = document.value("performance_scale", std::string("fast"));
    if (scale != "fast" && scale != "standard") {
        return Status(ErrorCode::invalid_argument,
                      "new-game performance scale is invalid");
    }
    const auto base_households = scale == "fast" ? 80U : 200U;
    const auto base_consumption_firms = scale == "fast" ? 12U : 30U;
    const auto base_capital_firms = scale == "fast" ? 4U : 10U;
    const auto base_energy_firms = scale == "fast" ? 2U : 4U;
    const auto base_banks = scale == "fast" ? 2U : 4U;

    const auto &world = document.at("world");
    if (!exact_keys(world, {"trade", "capital", "migration", "fx_lambda", "fx_friction",
                            "fx_trade_cap", "capital_mobility", "capital_adjust",
                            "migration_rate", "migration_max_share", "remittance_share",
                            "wage_smoothing", "peg_reserves0"})) {
        return Status(ErrorCode::invalid_argument, "new-game world fields are invalid");
    }
    if (!world.at("trade").is_boolean() || !world.at("capital").is_boolean() ||
        !world.at("migration").is_boolean()) {
        return Status(ErrorCode::invalid_argument,
                      "new-game world switches are invalid");
    }
    const std::array<std::string_view, 10> world_numbers{{
        "fx_lambda",
        "fx_friction",
        "fx_trade_cap",
        "capital_mobility",
        "capital_adjust",
        "migration_rate",
        "migration_max_share",
        "remittance_share",
        "wage_smoothing",
        "peg_reserves0",
    }};
    if (!std::ranges::all_of(world_numbers, [&world](std::string_view key) {
            return finite_number(world.at(key));
        })) {
        return Status(ErrorCode::invalid_argument, "new-game world number is invalid");
    }
    result.world.rules.trade = world.at("trade").get<bool>();
    result.world.rules.capital = world.at("capital").get<bool>();
    result.world.rules.migration = world.at("migration").get<bool>();
    result.world.rules.fx_adjustment = world.at("fx_lambda").get<double>();
    result.world.rules.fx_friction = world.at("fx_friction").get<double>();
    result.world.rules.fx_trade_cap = world.at("fx_trade_cap").get<double>();
    result.world.rules.capital_mobility = world.at("capital_mobility").get<double>();
    result.world.rules.capital_adjustment = world.at("capital_adjust").get<double>();
    result.world.rules.migration_rate = world.at("migration_rate").get<double>();
    result.world.rules.migration_max_share =
        world.at("migration_max_share").get<double>();
    result.world.rules.remittance_share = world.at("remittance_share").get<double>();
    result.world.rules.wage_smoothing = world.at("wage_smoothing").get<double>();
    result.world.rules.initial_peg_reserves = world.at("peg_reserves0").get<double>();
    result.world.rules.periods_per_year = 365.0;

    const auto &countries = document.at("countries");
    if (!countries.is_array() || countries.empty() ||
        countries.size() > kM11MaximumNewGameCountries) {
        return Status(ErrorCode::out_of_range, "new-game country count is invalid");
    }
    if (!unsigned_integer(document.at("player_country"), 0U, countries.size() - 1U)) {
        return Status(ErrorCode::out_of_range, "new-game player country is invalid");
    }
    result.player_economy = document.at("player_country").get<std::uint64_t>();
    std::set<std::string, std::less<>> country_codes;
    for (std::size_t index = 0U; index < countries.size(); ++index) {
        const auto &country = countries[index];
        if (!exact_keys(country, {"name", "code", "profile", "overrides"}, {"color"}) ||
            !country.at("name").is_string() || !country.at("code").is_string() ||
            !country.at("profile").is_string()) {
            return Status(ErrorCode::invalid_argument, "new-game country is invalid");
        }
        M11CountryMetadata metadata{
            country.at("name").get<std::string>(),
            country.at("code").get<std::string>(),
            country.at("profile").get<std::string>(),
        };
        if (metadata.name.empty() || metadata.name.size() > 40U ||
            metadata.code.size() < 2U || metadata.code.size() > 5U ||
            !country_codes.emplace(metadata.code).second) {
            return Status(ErrorCode::invalid_argument,
                          "new-game country identity is invalid");
        }
        const auto *selected_profile = profile(metadata.profile);
        if (selected_profile == nullptr) {
            return Status(ErrorCode::invalid_argument,
                          "new-game country profile is invalid");
        }
        simulation::M8SimulationSpec economy;
        enable_complete_playable_modules(economy);
        auto &population = economy.domestic_economy;
        auto &financial = population.financial_economy;
        auto &monetary = financial.monetary_economy;
        auto &real = monetary.real_economy;
        real.economy = EconomyId(static_cast<std::uint64_t>(index));
        real.currency = CurrencyId(static_cast<std::uint64_t>(index));
        real.seed = result.seed;
        real.households = std::max<std::uint64_t>(
            1U, static_cast<std::uint64_t>(std::llround(
                    static_cast<double>(base_households) * selected_profile->scale)));
        real.consumption_firms = base_consumption_firms;
        real.capital_firms = base_capital_firms;
        real.settlement_banks = base_banks;
        real.rules.linear_productivity *= selected_profile->productivity;
        real.rules.capital_productivity *= selected_profile->productivity;
        real.rules.annual_tfp_growth = selected_profile->tfp_growth;
        real.rules.necessity_need_per_unit =
            selected_profile->necessity_share * real.rules.initial_wage /
            real.rules.initial_price;
        monetary.rules.bank_count = base_banks;
        population.population.initial_persons = real.households;
        population.population.start_calendar_day = *ordinal;
        population.population.target_household_size = 2.5;
        auto vital = population.rules.vital_rates;
        vital.total_fertility_rate = selected_profile->fertility;
        vital.makeham_a *= selected_profile->mortality_scale;
        vital.gompertz_b *= selected_profile->mortality_scale;
        population.rules.vital_rates = vital;
        economy.energy_rules.producer_count = base_energy_firms;
        economy.energy_rules.producer_productivity *=
            selected_profile->energy_productivity;
        economy.energy_rules.capacity_per_capital *=
            selected_profile->energy_productivity;
        economy.housing_rules.builder_count = 5U;
        auto population_count = population.population.initial_persons;
        const auto override_status =
            apply_country_overrides(country.at("overrides"), economy, population_count);
        if (!override_status.ok()) {
            return override_status;
        }
        population.population.fixed_genesis_vital_rates = true;
        population.population.genesis_vital_rates = population.rules.vital_rates;
        population.population.initial_persons = population_count;
        if (country.at("overrides").contains("demographics_population")) {
            scale_representative_entities(economy, population_count);
        }
        calibrate_opening_bank_capital(economy);
        real.settlement_banks = monetary.rules.bank_count;
        result.countries.push_back(std::move(metadata));
        result.world.economies.push_back(economy);
        result.world.external_policies.emplace_back();
    }

    if (!document.at("run_mode").is_string()) {
        return Status(ErrorCode::invalid_argument, "new-game run mode is invalid");
    }
    result.run_mode = document.at("run_mode").get<std::string>();
    if (result.run_mode != "interactive" && result.run_mode != "realtime" &&
        result.run_mode != "batch") {
        return Status(ErrorCode::invalid_argument, "new-game run mode is invalid");
    }
    const auto &seats = document.at("seats");
    if (!exact_keys(seats, {"treasury", "cb", "labor_social", "regulator", "external",
                            "energy"})) {
        return Status(ErrorCode::invalid_argument, "new-game seats are invalid");
    }
    for (const auto &entry : seats.items()) {
        if (!entry.value().is_string()) {
            return Status(ErrorCode::invalid_argument, "new-game occupant is invalid");
        }
        const auto occupant = entry.value().get<std::string>();
        const auto seat = canonical_seat(entry.key());
        if (!seat.has_value() || !valid_occupant(occupant) ||
            (occupant == "rl" && *seat != "treasury") ||
            (result.run_mode == "batch" && occupant == "human")) {
            return Status(ErrorCode::invalid_argument, "new-game occupant is invalid");
        }
        control::M11OccupantSpec occupant_spec;
        occupant_spec.kind = occupant_kind(occupant);
        occupant_spec.occupant_id = "player-" + std::string(*seat);
        result.controller.assignments.push_back({
            EconomyId(result.player_economy),
            std::string(*seat),
            std::move(occupant_spec),
        });
    }
    result.controller.worker_count = 8U;
    const auto &policy_overrides = document.at("initial_policy_overrides");
    if (!policy_overrides.is_object()) {
        return Status(ErrorCode::invalid_argument,
                      "new-game initial policy is invalid");
    }
    for (const auto &entry : policy_overrides.items()) {
        const auto &key = entry.key();
        const auto first = key.find('.');
        const auto second =
            first == std::string::npos ? std::string::npos : key.find('.', first + 1U);
        if (first == std::string::npos || second == std::string::npos ||
            second + 1U >= key.size()) {
            return Status(ErrorCode::invalid_argument,
                          "new-game policy key is invalid");
        }
        const auto economy_text = key.substr(0U, first);
        std::uint64_t economy = 0U;
        try {
            std::size_t parsed = 0U;
            economy = std::stoull(economy_text, &parsed);
            if (parsed != economy_text.size()) {
                return Status(ErrorCode::invalid_argument,
                              "new-game policy key is invalid");
            }
        } catch (...) {
            return Status(ErrorCode::invalid_argument,
                          "new-game policy key is invalid");
        }
        if (economy >= result.world.economies.size()) {
            return Status(ErrorCode::out_of_range,
                          "new-game policy economy is invalid");
        }
        const auto seat = canonical_seat(
            std::string_view(key).substr(first + 1U, second - first - 1U));
        const auto lever_name = std::string_view(key).substr(second + 1U);
        const auto *lever = control::find_m11_policy_lever(lever_name);
        if (!seat.has_value() || lever == nullptr || lever->owner_role != *seat) {
            return Status(ErrorCode::invalid_argument,
                          "new-game policy ownership is invalid");
        }
        auto policy_value = policy_value_from_json(*lever, entry.value());
        if (!policy_value.ok()) {
            return policy_value.status();
        }
        result.initial_policy_actions.push_back({
            EconomyId(economy),
            std::string(lever_name),
            std::move(*policy_value.get_if()),
        });
    }
    if (scenario != "sandbox") {
        simulation::CrisisScenarioOptions options;
        const auto horizon = result.duration_ticks.value_or(100000U);
        options.start = Tick(
            std::min<std::uint64_t>(365U, std::max<std::uint64_t>(30U, horizon / 4U)));
        options.duration = scenario == "pandemic" ? 365U : 180U;
        options.announcement_lead_ticks = 30U;
        options.first_shock_id = 1U;
        options.include_trade = result.world.rules.trade;
        for (std::size_t index = 0U; index < result.world.economies.size(); ++index) {
            options.economies.emplace_back(static_cast<std::uint64_t>(index));
        }
        const auto crisis =
            scenario == "oil"   ? simulation::CrisisScenario::oil_embargo
            : scenario == "gfc" ? simulation::CrisisScenario::global_financial_crisis
            : scenario == "pandemic" ? simulation::CrisisScenario::pandemic
                                     : simulation::CrisisScenario::natural_disaster;
        auto shocks = simulation::make_crisis_scenario(crisis, options,
                                                       result.world.economies.size());
        if (!shocks.ok()) {
            return shocks.status();
        }
        result.world.shocks = std::move(*shocks.get_if());
    }
    return result;
}

} // namespace

Result<M11NativeNewGame> parse_m11_native_new_game(std::string_view json_document) {
    if (json_document.empty() || json_document.size() > std::size_t{1024} * 1024U) {
        return Status(ErrorCode::out_of_range, "new-game document size is invalid");
    }
    try {
        return parse_document(Json::parse(json_document));
    } catch (...) {
        return Status(ErrorCode::corrupt_input, "new-game document is malformed");
    }
}

Result<M11NativeNewGame> default_m11_native_new_game(std::uint64_t seed) {
    if (seed > kMaximumSeed) {
        return Status(ErrorCode::out_of_range, "new-game seed is invalid");
    }
    Json document = {
        {"schema_version", kM11NewGameSchemaVersion},
        {"seed", seed},
        {"start_date", "2000-01-01"},
        {"scenario", "sandbox"},
        {"duration", 1827U},
        {"performance_scale", "fast"},
        {"world",
         {
             {"trade", true},
             {"capital", true},
             {"migration", true},
             {"fx_lambda", 0.05},
             {"fx_friction", 0.03},
             {"fx_trade_cap", 0.15},
             {"capital_mobility", 1.0},
             {"capital_adjust", 0.2},
             {"migration_rate", 0.0005},
             {"migration_max_share", 0.25},
             {"remittance_share", 0.2},
             {"wage_smoothing", 0.02},
             {"peg_reserves0", 5000.0},
         }},
        {"countries", Json::array({
                          {
                              {"name", "Aurelia"},
                              {"code", "AUR"},
                              {"profile", "advanced"},
                              {"overrides", Json::object()},
                          },
                          {
                              {"name", "Borvia"},
                              {"code", "BOL"},
                              {"profile", "developing"},
                              {"overrides", Json::object()},
                          },
                          {
                              {"name", "Petronia"},
                              {"code", "PET"},
                              {"profile", "petrostate"},
                              {"overrides", Json::object()},
                          },
                      })},
        {"player_country", 0U},
        {"run_mode", "interactive"},
        {"seats",
         {
             {"treasury", "human"},
             {"cb", "human"},
             {"labor_social", "human"},
             {"regulator", "human"},
             {"external", "human"},
             {"energy", "human"},
         }},
        {"initial_policy_overrides", Json::object()},
    };
    return parse_document(document);
}

} // namespace macro_sim::desktop
