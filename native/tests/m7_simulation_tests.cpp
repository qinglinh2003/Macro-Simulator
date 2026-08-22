#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/transaction.hpp"
#include "macro_sim/simulation/m7.hpp"

namespace {

using macro_sim::HouseholdId;
using macro_sim::PersonId;
using macro_sim::Tick;
using macro_sim::core::PersonSex;
using macro_sim::simulation::capability_bit;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M7AdvanceOptions;
using macro_sim::simulation::M7SimulationSpec;

[[nodiscard]] M7SimulationSpec base_spec() {
    M7SimulationSpec spec;
    auto &real = spec.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 6;
    real.capital_firms = 2;
    real.seed = 71;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_household_money = 40.0;
    real.rules.initial_firm_money = 8.0;
    real.rules.initial_consumption_inventory = 4.0;
    real.rules.initial_capital_inventory = 3.0;
    real.rules.initial_consumption_capital = 6.0;
    real.rules.initial_expected_demand = 10.0;
    real.rules.initial_wage = 2.0;
    real.rules.initial_price = 1.5;
    real.rules.initial_capital_price = 1.5;
    auto &monetary = spec.financial_economy.monetary_economy;
    monetary.rules.bank_count = 3;
    monetary.rules.opening_capital_per_bank = 30.0;
    monetary.rules.bank_leverage_mean = 8.0;
    monetary.rules.interbank = true;
    monetary.rules.full_firm_pnl = true;
    monetary.rules.realized_bank_pnl = true;
    monetary.rules.household_credit = true;
    monetary.policy.bank_capital_constraint = true;
    monetary.policy.bank_leverage_cap = 8.0;
    monetary.policy.firm_leverage_limit = 4.0;
    monetary.policy.household_credit_limit = 3.0;
    monetary.initial_policy_rate = 0.002;
    spec.financial_economy.policy.bank_minimum_capital = 20.0;
    spec.financial_economy.policy.bond_maturity_days = 30;
    spec.financial_economy.rules.bond_maturity_bucket = 5;
    spec.financial_economy.rules.watchlist_size = 4;
    spec.financial_economy.rules.entry_beta = 0.0;
    spec.financial_economy.rules.bank_entry_beta = 0.0;
    spec.population.initial_persons = 100;
    spec.population.target_household_size = 2.5;
    spec.population.start_calendar_day = 20'000;
    spec.rules.fertility = false;
    spec.rules.mortality = false;
    spec.rules.annual_churn = 0.0;
    return spec;
}

struct Harness final {
    macro_sim::core::RootState root;
    macro_sim::simulation::M4Runtime real_runtime;
    macro_sim::simulation::M4TickScratch real_scratch;
    macro_sim::simulation::M5Runtime monetary_runtime;
    macro_sim::simulation::M5TickScratch monetary_scratch;
    macro_sim::simulation::M6Runtime financial_runtime;
    macro_sim::simulation::M6TickScratch financial_scratch;
    macro_sim::simulation::M7Runtime runtime;
    macro_sim::simulation::M7TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build(M7SimulationSpec spec = base_spec()) {
    auto initialization = macro_sim::simulation::build_m7_genesis(spec);
    if (!initialization.ok()) {
        std::cerr << "M7 genesis failed: " << initialization.status().message() << "\n";
    }
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness harness{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.monetary_runtime),
        {},
        std::move(value.financial_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick(0),
    };
    harness.real_scratch.reserve(harness.root);
    harness.monetary_scratch.reserve(harness.root);
    harness.financial_scratch.reserve(harness.root, harness.financial_runtime);
    harness.scratch.reserve(harness.runtime);
    return harness;
}

[[nodiscard]] macro_sim::Result<macro_sim::simulation::M7AdvanceResult>
advance(Harness &harness, std::uint64_t count, const M7AdvanceOptions &options = {}) {
    return macro_sim::simulation::advance_m7_ticks(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch, harness.financial_runtime,
        harness.financial_scratch, harness.runtime, harness.scratch, harness.tick,
        count, options);
}

void test_genesis_derives_households_from_population() {
    auto harness = build();
    const auto household_count = harness.root.households.alive_count();
    assert(household_count > 0U);
    assert(household_count < 100U);
    assert(household_count != 40U);
    assert(harness.runtime.persons.alive_count() == 100);
    double opening_income = 0.0;
    harness.root.households.for_each_alive(
        [&opening_income](HouseholdId,
                          const macro_sim::core::HouseholdComponent &household) {
            opening_income += household.income_expected;
            assert(household.income_expected == household.income_realized);
        });
    assert(opening_income > 0.0);
    assert(harness.runtime.beneficial_ownership.size() >= 100);
    bool has_security_claim = false;
    bool has_debt_claim = false;
    std::vector<macro_sim::HouseholdId> security_claim_households;
    for (const auto &lot : harness.runtime.beneficial_ownership.records()) {
        if (lot.asset.kind == macro_sim::core::BeneficialAssetKind::security_position) {
            has_security_claim = true;
            assert(lot.asset.value == 0U);
            security_claim_households.push_back(lot.asset.household);
        }
        has_debt_claim =
            has_debt_claim ||
            lot.asset.kind == macro_sim::core::BeneficialAssetKind::household_debt;
    }
    assert(has_security_claim);
    std::sort(security_claim_households.begin(), security_claim_households.end());
    for (auto first = security_claim_households.begin();
         first != security_claim_households.end();) {
        const auto last =
            std::upper_bound(first, security_claim_households.end(), *first);
        const auto members = harness.runtime.membership.members(*first).size();
        assert(static_cast<std::size_t>(last - first) == members);
        first = last;
    }
    const bool has_household_loan = std::any_of(
        harness.root.loans.records().begin(), harness.root.loans.records().end(),
        [](const macro_sim::core::LoanRecord &loan) {
            return loan.active &&
                   loan.borrower.kind() == macro_sim::core::OwnerKind::household;
        });
    assert(!has_household_loan || has_debt_claim);
    assert(harness.runtime.last_metrics.population == 100);
    assert(harness.runtime.last_metrics.households_with_members ==
           household_count);
    std::uint64_t referenced_children = 0;
    std::uint64_t referenced_adults = 0;
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        if (person->mother.valid() || person->father.valid()) {
            ++referenced_children;
            const auto age = static_cast<std::uint32_t>(
                (base_spec().population.start_calendar_day - person->birth_day) /
                365);
            if (age < base_spec().rules.working_age) {
                assert(person->guardian.valid());
                assert(harness.runtime.persons.alive(person->guardian));
                assert(harness.runtime.persons.get(person->guardian)->household ==
                       person->household);
            } else {
                ++referenced_adults;
                assert(!person->guardian.valid());
            }
        }
    }
    assert(referenced_children > 0);
    assert(referenced_adults > 0);
    assert(!harness.runtime.relationships.unions().empty());
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
    harness.root.households.for_each_alive(
        [&](HouseholdId id, const macro_sim::core::HouseholdComponent &) {
            const auto count = harness.runtime.membership.members(id).size();
            assert(count >= 1U);
            assert(count <=
                   base_spec().rules.genesis_maximum_children_per_household +
                       2U);
        });
}

void test_genesis_relationship_rules_have_direct_observable_effects() {
    auto low_union_spec = base_spec();
    low_union_spec.population.initial_persons = 4'096;
    low_union_spec.rules.genesis_union_target_profile.enabled = false;
    low_union_spec.rules.genesis_target_partnered_adult_share = 0.10;
    auto high_union_spec = low_union_spec;
    high_union_spec.rules.genesis_target_partnered_adult_share = 0.80;
    const auto low_union = build(low_union_spec);
    const auto high_union = build(high_union_spec);
    assert(low_union.runtime.last_metrics.partnered_adult_share < 0.20);
    assert(high_union.runtime.last_metrics.partnered_adult_share > 0.60);
    assert(high_union.runtime.last_metrics.partnered_adult_share >
           low_union.runtime.last_metrics.partnered_adult_share + 0.45);

    auto single_parent_spec = base_spec();
    single_parent_spec.population.initial_persons = 4'096;
    single_parent_spec.rules.genesis_two_parent_assignment_share = 0.0;
    auto dual_parent_spec = single_parent_spec;
    dual_parent_spec.rules.genesis_two_parent_assignment_share = 1.0;
    const auto single_parent = build(single_parent_spec);
    const auto dual_parent = build(dual_parent_spec);
    assert(dual_parent.runtime.last_metrics.dual_parent_minor_share >
           single_parent.runtime.last_metrics.dual_parent_minor_share);

    auto narrow_gap_spec = base_spec();
    narrow_gap_spec.population.initial_persons = 4'096;
    narrow_gap_spec.rules.genesis_parent_age_gap_stddev = 0.01;
    auto wide_gap_spec = narrow_gap_spec;
    wide_gap_spec.rules.genesis_parent_age_gap_stddev = 12.0;
    const auto narrow_gap = build(narrow_gap_spec);
    const auto wide_gap = build(wide_gap_spec);
    assert(wide_gap.runtime.last_metrics.mother_age_gap_stddev >
           narrow_gap.runtime.last_metrics.mother_age_gap_stddev);
}

void test_genesis_person_efficiency_is_mean_preserving_and_deterministic() {
    auto spec = base_spec();
    spec.population.initial_persons = 4'096;
    spec.rules.person_efficiency = true;
    spec.rules.efficiency_sigma = 0.35;
    auto first = build(spec);
    auto second = build(spec);

    double total = 0.0;
    bool heterogeneous = false;
    for (const auto person_id : first.runtime.persons.alive_ids()) {
        const double efficiency = first.runtime.persons.get(person_id)->efficiency;
        assert(std::isfinite(efficiency));
        assert(efficiency > 0.0);
        assert(efficiency == second.runtime.persons.get(person_id)->efficiency);
        total += efficiency;
        heterogeneous = heterogeneous || std::abs(efficiency - 1.0) > 1.0e-9;
    }
    const double mean =
        total / static_cast<double>(first.runtime.persons.alive_count());
    assert(mean > 0.97 && mean < 1.03);
    assert(heterogeneous);

    spec.rules.person_efficiency = false;
    auto disabled = build(spec);
    for (const auto person_id : disabled.runtime.persons.alive_ids()) {
        assert(disabled.runtime.persons.get(person_id)->efficiency == 1.0);
    }
}

void test_demography_projects_age_weighted_consumption_needs() {
    auto spec = base_spec();
    auto &real = spec.financial_economy.monetary_economy.real_economy;
    real.rules.consumption_strata = true;
    real.rules.necessity_need_per_unit = 1.0;
    spec.financial_economy.rules.consumption_strata = true;
    auto harness = build(spec);
    const auto result = advance(harness, 1);
    assert(result.ok());

    std::vector<double> expected(harness.real_scratch.household_need_units_.size(),
                                 0.0);
    constexpr double days_per_year = 365.0;
    const auto calendar_day = spec.population.start_calendar_day + 1;
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        assert(person != nullptr);
        const auto household_identity =
            static_cast<std::size_t>(person->household.value());
        assert(household_identity <
               harness.real_scratch.household_dense_index_.size());
        const auto household_index =
            harness.real_scratch.household_dense_index_[household_identity];
        assert(household_index < expected.size());
        const double age = std::max(
            0.0, static_cast<double>(calendar_day - person->birth_day) /
                     days_per_year);
        expected[household_index] +=
            age < 18.0 ? 0.65 : (age >= 65.0 ? 0.90 : 1.0);
    }
    bool differs_from_household_count = false;
    for (std::size_t index = 0; index < expected.size(); ++index) {
        assert(std::abs(harness.real_scratch.household_need_units_[index] -
                        expected[index]) < 1.0e-12);
        differs_from_household_count =
            differs_from_household_count || std::abs(expected[index] - 1.0) > 1.0e-12;
    }
    assert(differs_from_household_count);
}

void test_lifecycle_consumption_replaces_the_standard_budget() {
    auto standard = build();
    auto lifecycle_spec = base_spec();
    lifecycle_spec.rules.lifecycle_consumption = true;
    lifecycle_spec.rules.lifecycle_income_propensity = 0.0;
    lifecycle_spec.rules.lifecycle_wealth_draw_propensity = 0.0;
    auto lifecycle = build(lifecycle_spec);

    const auto standard_result = advance(standard, 1);
    const auto lifecycle_result = advance(lifecycle, 1);
    assert(standard_result.ok());
    assert(lifecycle_result.ok());
    assert(standard_result.get_if()->metrics.economy.economy.economy
               .household_consumption_budget > 0.0);
    assert(lifecycle_result.get_if()->metrics.economy.economy.economy
               .household_consumption_budget == 0.0);

    lifecycle_spec.rules.lifecycle_income_propensity = 1.0;
    auto income_channel = build(lifecycle_spec);
    const auto income_result = advance(income_channel, 1);
    assert(income_result.ok());
    assert(income_result.get_if()->metrics.economy.economy.economy
               .household_consumption_budget > 0.0);
}

void test_real_wage_signal_updates_vital_multipliers_annually() {
    auto spec = base_spec();
    spec.population.start_calendar_day = 737'790; // 2020-12-31
    spec.rules.demographic_feedback_burnin_years = 1U;
    spec.rules.demographic_signal_halflife_years = 1.0;
    spec.rules.fertility_income_elasticity = 1.0;
    spec.rules.mortality_income_elasticity = 1.0;
    auto harness = build(spec);
    harness.runtime.demographic_signal_year = 2020;
    harness.runtime.demographic_signal_years_completed = 1U;
    harness.runtime.demographic_signal_ewma = 100.0;
    harness.runtime.demographic_signal_baseline = 100.0;
    harness.runtime.demographic_signal_last_real_wage = 100.0;
    harness.runtime.demographic_signal_wage_sum = 50.0;
    harness.runtime.demographic_signal_labor_sum = 1.0;
    harness.runtime.demographic_signal_price_sum = 1.0;
    harness.runtime.demographic_signal_days = 1U;

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(std::abs(harness.runtime.demographic_signal_x - 0.75) < 1.0e-12);
    assert(std::abs(harness.runtime.demographic_signal_fertility_multiplier -
                    4.0 / 3.0) < 1.0e-12);
    assert(std::abs(harness.runtime.demographic_signal_mortality_multiplier - 1.3) <
           1.0e-12);
    assert(result.get_if()->metrics.demographic_fertility_multiplier > 1.0);
    assert(result.get_if()->metrics.demographic_mortality_multiplier > 1.0);

    auto neutral_spec = spec;
    neutral_spec.rules.fertility_income_elasticity = 0.0;
    neutral_spec.rules.mortality_income_elasticity = 0.0;
    auto neutral = build(neutral_spec);
    neutral.runtime.demographic_signal_fertility_multiplier = 1.4;
    neutral.runtime.demographic_signal_mortality_multiplier = 1.2;
    const auto neutral_result = advance(neutral, 1);
    assert(neutral_result.ok());
    assert(neutral.runtime.demographic_signal_fertility_multiplier == 1.0);
    assert(neutral.runtime.demographic_signal_mortality_multiplier == 1.0);
}

void test_real_wage_signal_denominator_includes_unemployed_working_age_people() {
    auto harness = build();
    const auto calendar_day = base_spec().population.start_calendar_day + 1;
    const double opening_price_index = harness.real_runtime.last_metrics.price_index;
    double working_age_population = 0.0;
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        const double age = std::max(
            0.0, static_cast<double>(calendar_day - person->birth_day) / 365.0);
        working_age_population +=
            age >= static_cast<double>(harness.runtime.rules.working_age) &&
                    age < static_cast<double>(harness.runtime.rules.retirement_age)
                ? 1.0
                : 0.0;
    }

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(std::abs(harness.runtime.demographic_signal_labor_sum -
                    working_age_population) < 1.0e-12);
    assert(harness.runtime.demographic_signal_labor_sum >=
           result.get_if()->metrics.employed_fte);
    double contractual_labor_income = 0.0;
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        const double age = std::max(
            0.0, static_cast<double>(calendar_day - person->birth_day) / 365.0);
        if (age < static_cast<double>(harness.runtime.rules.working_age) ||
            age >= static_cast<double>(harness.runtime.rules.retirement_age)) {
            continue;
        }
        for (const auto job_id : std::array{
                 harness.runtime.employment.primary_job(person_id),
                 harness.runtime.employment.secondary_job(person_id)}) {
            const auto *job = harness.runtime.employment.get(job_id);
            if (job != nullptr && job->active && !job->suspended) {
                contractual_labor_income +=
                    job->wage * job->hours * person->efficiency;
            }
        }
    }
    assert(std::abs(harness.runtime.demographic_signal_wage_sum -
                    contractual_labor_income) < 1.0e-12);
    assert(std::abs(harness.runtime.demographic_signal_price_sum -
                    std::max(1.0e-8, opening_price_index)) < 1.0e-12);
}

void test_real_wage_signal_includes_job_guarantee_labor_income() {
    auto spec = base_spec();
    auto &policy = spec.financial_economy.monetary_economy.policy;
    policy.job_guarantee = true;
    policy.job_guarantee_wage_ratio = 0.75;
    auto harness = build(spec);

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.job_guarantee > 0.0);

    double private_contractual_income = 0.0;
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        for (const auto job_id : std::array{
                 harness.runtime.employment.primary_job(person_id),
                 harness.runtime.employment.secondary_job(person_id)}) {
            const auto *job = harness.runtime.employment.get(job_id);
            if (job != nullptr && job->active && !job->suspended) {
                private_contractual_income +=
                    job->wage * job->hours * person->efficiency;
            }
        }
    }
    double mean_posted_wage = 0.0;
    for (const auto &work : harness.real_scratch.firm_work_) {
        mean_posted_wage += work.posted_wage;
    }
    mean_posted_wage /= static_cast<double>(
        std::max<std::size_t>(1U, harness.real_scratch.firm_work_.size()));
    const double guarantee_wage =
        std::max(policy.minimum_wage,
                 policy.job_guarantee_wage_ratio * mean_posted_wage);
    const double expected =
        private_contractual_income +
        result.get_if()->metrics.job_guarantee * guarantee_wage;
    assert(std::abs(harness.runtime.demographic_signal_wage_sum - expected) <
           1.0e-12);
}

void test_wealth_rank_gradients_apply_bounded_vital_risk() {
    auto spec = base_spec();
    spec.population.initial_persons = 2'000;
    spec.rules.mortality_rank_gradient = 0.8;
    spec.rules.fertility_rank_gradient = 0.5;
    auto harness = build(spec);
    harness.runtime.rules.marriage = false;
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.wealth_rank_mortality_multiplier_stddev > 0.0);
    assert(result.get_if()->metrics.wealth_rank_fertility_multiplier_stddev > 0.0);
    const double unbounded_mortality_stddev =
        result.get_if()->metrics.wealth_rank_mortality_multiplier_stddev;
    assert(harness.runtime.household_wealth_quintile.size() ==
           harness.real_scratch.household_dense_index_.size());

    PersonId bottom_member{};
    PersonId top_fertile_woman{};
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        const auto household = static_cast<std::size_t>(person->household.value());
        if (household >= harness.runtime.household_wealth_quintile.size()) {
            continue;
        }
        const auto quintile = harness.runtime.household_wealth_quintile[household];
        if (quintile == 0U && !bottom_member.valid()) {
            bottom_member = person_id;
        }
        const double age = static_cast<double>(harness.runtime.current_calendar_day -
                                               person->birth_day) /
                           365.2425;
        if (quintile == 4U && person->sex == PersonSex::female && age >= 15.0 &&
            age <= 49.0 && !top_fertile_woman.valid()) {
            top_fertile_woman = person_id;
        }
    }
    assert(bottom_member.valid());
    if (!top_fertile_woman.valid()) {
        for (const auto person_id : harness.runtime.persons.alive_ids()) {
            const auto *person = harness.runtime.persons.get(person_id);
            const double age = static_cast<double>(
                                   harness.runtime.current_calendar_day -
                                   person->birth_day) /
                               365.2425;
            if (person->sex != PersonSex::female || age < 15.0 || age > 49.0) {
                continue;
            }
            if (person->household ==
                harness.runtime.persons.get(bottom_member)->household) {
                continue;
            }
            top_fertile_woman = person_id;
            const auto household =
                static_cast<std::size_t>(person->household.value());
            harness.runtime.household_wealth_quintile[household] = 4U;
            break;
        }
    }
    assert(top_fertile_woman.valid());
    M7AdvanceOptions forced_death;
    forced_death.force_death = bottom_member;
    result = advance(harness, 1, forced_death);
    assert(result.ok());
    assert(result.get_if()->metrics.bottom_wealth_quintile_deaths >= 1U);
    M7AdvanceOptions forced_birth;
    forced_birth.force_birth = top_fertile_woman;
    result = advance(harness, 1, forced_birth);
    assert(result.ok());
    assert(result.get_if()->metrics.top_wealth_quintile_births >= 1U);

    auto bounded = spec;
    bounded.rules.stratification_multiplier_minimum = 0.9;
    bounded.rules.stratification_multiplier_maximum = 1.05;
    auto bounded_harness = build(bounded);
    result = advance(bounded_harness, 1);
    assert(result.ok());
    assert(*std::ranges::min_element(
               bounded_harness.runtime.mortality_quintile_multiplier) >= 0.9);
    assert(*std::ranges::max_element(
               bounded_harness.runtime.fertility_quintile_multiplier) <= 1.05);
    assert(result.get_if()->metrics.wealth_rank_mortality_multiplier_stddev <
           unbounded_mortality_stddev);
}

void test_death_and_estate_settle_exactly_once() {
    auto harness = build();
    const auto household = harness.runtime.persons.get(PersonId(1))->household;
    const auto opening_members = harness.runtime.membership.members(household).size();
    const auto opening_lots =
        harness.runtime.beneficial_ownership.lots_for_person(PersonId(1)).size();
    M7AdvanceOptions options;
    options.force_death = PersonId(1);
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 forced death failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.tick == Tick(1));
    assert(!harness.runtime.persons.alive(PersonId(1)));
    assert(harness.runtime.persons.archived_count() == 1);
    assert(harness.runtime.membership.members(household).size() == opening_members - 1);
    assert(harness.runtime.beneficial_ownership.lots_for_person(PersonId(1)).empty());
    assert(harness.runtime.estates.size() == 1);
    assert(harness.runtime.estates[0].settled);
    assert(harness.runtime.estates[0].transferred_lots == opening_lots);
    assert(result.get_if()->metrics.deaths == 1);
    assert(result.get_if()->metrics.estates_settled == 1);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());

    const auto before_tick = harness.tick;
    const auto before_estates = harness.runtime.estates;
    const auto repeated = advance(harness, 1, options);
    assert(!repeated.ok());
    assert(harness.tick == before_tick);
    assert(harness.runtime.estates == before_estates);
}

void test_retired_household_closes_tolerance_sized_account_residual() {
    auto spec = base_spec();
    spec.population.initial_persons = 40;
    spec.population.target_household_size = 1.0;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);

    PersonId deceased{};
    HouseholdId household{};
    for (const auto candidate : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(candidate);
        if (person != nullptr &&
            harness.runtime.membership.members(person->household).size() == 1U) {
            deceased = candidate;
            household = person->household;
            break;
        }
    }
    assert(deceased.valid() && household.valid());
    const auto account = harness.root.households.get(household)->primary_account;
    const auto *opening = harness.root.postings.get(account);
    assert(opening != nullptr && opening->balance.value() > 0.0);

    macro_sim::core::SettlementTransaction drain(harness.root);
    assert(drain
               .transfer(account,
                         harness.root.institutions.rounding_residual_account,
                         opening->balance)
               .ok());
    assert(drain.commit_locally_validated().ok());
    macro_sim::core::SettlementTransaction residual(harness.root);
    assert(residual
               .transfer(harness.root.institutions.rounding_residual_account,
                         account,
                         macro_sim::Money(harness.root.accounting_tolerance * 0.5))
               .ok());
    assert(residual.commit_locally_validated().ok());

    M7AdvanceOptions options;
    options.force_death = deceased;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 residual-account retirement failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(!harness.root.postings.contains(account));
    assert(harness.root.households.get(household) == nullptr);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_population_fault_is_atomic() {
    auto harness = build();
    const auto root_digest = macro_sim::core::state_digest(harness.root);
    const auto people = harness.runtime.persons.records();
    const auto ownership = harness.runtime.beneficial_ownership.records();
    const auto securities = harness.financial_runtime.securities.lots();
    const auto financial_firms = harness.financial_runtime.firms;
    M7AdvanceOptions options;
    options.force_death = PersonId(1);
    options.fault_before_population_commit = true;
    const auto failed = advance(harness, 1, options);
    assert(!failed.ok());
    assert(harness.tick == Tick(0));
    assert(root_digest == macro_sim::core::state_digest(harness.root));
    assert(harness.runtime.persons.records() == people);
    assert(harness.runtime.beneficial_ownership.records() == ownership);
    assert(harness.runtime.estates.empty());
    assert(harness.financial_runtime.securities.lots() == securities);
    assert(harness.financial_runtime.firms == financial_firms);
}

void test_forced_birth_and_split_determinism() {
    auto efficiency_spec = base_spec();
    efficiency_spec.rules.person_efficiency = true;
    efficiency_spec.rules.efficiency_sigma = 0.35;
    auto direct = build(efficiency_spec);
    auto repeated_birth = build(efficiency_spec);
    PersonId mother{};
    for (const auto id : direct.runtime.persons.alive_ids()) {
        const auto *person = direct.runtime.persons.get(id);
        const double age = static_cast<double>(direct.runtime.current_calendar_day -
                                               person->birth_day) /
                           365.2425;
        if (person->sex == PersonSex::female && age >= 15.0 && age <= 49.0) {
            mother = id;
            break;
        }
    }
    assert(mother.valid());
    M7AdvanceOptions birth;
    birth.force_birth = mother;
    const auto born = advance(direct, 1, birth);
    assert(born.ok());
    const auto repeated = advance(repeated_birth, 1, birth);
    assert(repeated.ok());
    assert(direct.runtime.persons.alive_count() == 101);
    assert(born.get_if()->metrics.births == 1);
    const auto *baby = direct.runtime.persons.get(PersonId(101));
    assert(baby != nullptr);
    assert(baby->mother == mother);
    assert(std::isfinite(baby->efficiency));
    assert(baby->efficiency > 0.0);
    assert(baby->efficiency ==
           repeated_birth.runtime.persons.get(PersonId(101))->efficiency);
    assert(direct.runtime.membership.household_of(PersonId(101)) ==
           direct.runtime.persons.get(mother)->household);

    auto batch = build();
    auto split = build();
    auto result = advance(batch, 12);
    assert(result.ok());
    for (std::uint64_t index = 0; index < 12; ++index) {
        result = advance(split, 1);
        assert(result.ok());
    }
    assert(batch.tick == split.tick);
    assert(batch.runtime.persons.records() == split.runtime.persons.records());
    assert(batch.runtime.beneficial_ownership.records() ==
           split.runtime.beneficial_ownership.records());
    assert(batch.runtime.estates == split.runtime.estates);
    assert(batch.runtime.last_metrics == split.runtime.last_metrics);
    assert(batch.runtime.employment.records() == split.runtime.employment.records());
    assert(batch.runtime.labor_accounts == split.runtime.labor_accounts);
}

void test_persistent_labor_and_death_separation() {
    auto harness = build();
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.employed_heads > 0.0);
    assert(result.get_if()->metrics.employed_fte > 0.0);
    assert(result.get_if()->metrics.hires > 0.0);
    assert(std::abs(result.get_if()->metrics.unemployment -
                    (harness.runtime.labor_accounts.unemployed +
                     harness.runtime.labor_accounts.suspended)) < 1.0e-12);
    assert(std::abs(result.get_if()->metrics.unemployment_rate -
                    result.get_if()->metrics.unemployment /
                        result.get_if()->metrics.labor_supply) < 1.0e-12);
    assert(
        std::abs(result.get_if()->metrics.unemployment_rate -
                 result.get_if()->metrics.economy.economy.economy.unemployment_rate) <
        1.0e-12);
    assert(harness.runtime.employment
               .validate(harness.runtime.persons, harness.root,
                         harness.root.accounting_tolerance)
               .ok());
    assert(macro_sim::core::validate_labor_accounts(harness.runtime.labor_accounts,
                                                    harness.root.accounting_tolerance)
               .ok());
    PersonId worker{};
    for (const auto person : harness.runtime.persons.alive_ids()) {
        if (harness.runtime.employment.primary_job(person).valid()) {
            worker = person;
            break;
        }
    }
    assert(worker.valid());
    const auto death_flow = harness.runtime.labor_accounts.death_separations_total;
    M7AdvanceOptions death;
    death.force_death = worker;
    result = advance(harness, 1, death);
    assert(result.ok());
    assert(!harness.runtime.persons.alive(worker));
    assert(!harness.runtime.employment.primary_job(worker).valid());
    assert(harness.runtime.labor_accounts.death_separations_total == death_flow + 1.0);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_payroll_budget_uses_worker_efficiency() {
    auto harness = build();
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(harness.runtime.employment.active_count() > 0U);
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        harness.runtime.persons.get(person_id)->efficiency = 1'000.0;
    }
    result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M7 efficiency-weighted payroll failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_labor_matching_fills_effective_units() {
    auto spec = base_spec();
    spec.financial_economy.monetary_economy.real_economy.rules.initial_firm_money =
        1'000'000.0;
    auto harness = build(spec);
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        harness.runtime.persons.get(person_id)->efficiency = 2.0;
    }

    const auto result = advance(harness, 1);
    assert(result.ok());
    bool observed_demand = false;
    for (const auto &work : harness.real_scratch.firm_work_) {
        if (work.labor_demand_effective <= 1.0e-8) {
            continue;
        }
        observed_demand = true;
        assert(work.hired <= work.labor_demand_effective + 1.0e-8);
    }
    assert(observed_demand);
}

void test_relationship_household_lifecycle() {
    auto spec = base_spec();
    spec.population.start_calendar_day = 29;
    spec.rules.marriage_interval_days = 30;
    spec.rules.annual_marriage_rate = 1.0;
    spec.rules.annual_divorce_rate = 0.0;
    spec.rules.genesis_union_target_profile.enabled = false;
    spec.rules.genesis_target_partnered_adult_share = 0.0;
    auto harness = build(spec);
    auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M7 marriage failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(result.get_if()->metrics.marriages > 0);
    assert(result.get_if()->metrics.active_unions > 0);
    assert(result.get_if()->metrics.mean_partner_age_gap >= 0.0);
    assert(result.get_if()->metrics.mean_partner_log_efficiency_gap >= 0.0);
    assert(harness.runtime.relationships.validate(harness.runtime.persons).ok());
    PersonId partnered{};
    for (const auto person : harness.runtime.persons.alive_ids()) {
        if (harness.runtime.persons.get(person)->partner.valid()) {
            partnered = person;
            break;
        }
    }
    assert(partnered.valid());
    const auto partner = harness.runtime.persons.get(partnered)->partner;
    assert(harness.runtime.membership.household_of(partnered) ==
           harness.runtime.membership.household_of(partner));

    harness.runtime.rules.annual_divorce_rate = 1.0;
    result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M7 divorce failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(result.get_if()->metrics.divorces > 0);
    assert(harness.runtime.relationships.validate(harness.runtime.persons).ok());

    spec = base_spec();
    spec.population.start_calendar_day = 29;
    spec.rules.marriage_interval_days = 30;
    spec.rules.annual_marriage_rate = 1.0;
    spec.rules.annual_divorce_rate = 0.0;
    spec.rules.genesis_union_target_profile.enabled = false;
    spec.rules.genesis_target_partnered_adult_share = 0.0;
    harness = build(spec);
    result = advance(harness, 1);
    assert(result.ok());
    partnered = PersonId{};
    for (const auto person : harness.runtime.persons.alive_ids()) {
        if (harness.runtime.persons.get(person)->partner.valid()) {
            partnered = person;
            break;
        }
    }
    assert(partnered.valid());
    M7AdvanceOptions death;
    death.force_death = partnered;
    result = advance(harness, 1, death);
    assert(result.ok());
    assert(result.get_if()->metrics.widowhoods == 1);
    assert(harness.runtime.relationships.validate(harness.runtime.persons).ok());
}

void test_divorce_does_not_reenter_household_retired_by_same_day_death() {
    auto spec = base_spec();
    spec.population.start_calendar_day = 29;
    spec.population.target_household_size = 2.0;
    spec.rules.marriage_interval_days = 30;
    spec.rules.annual_marriage_rate = 1.0;
    spec.rules.annual_divorce_rate = 0.0;
    spec.rules.genesis_union_target_profile.enabled = false;
    spec.rules.genesis_target_partnered_adult_share = 0.0;
    auto harness = build(spec);
    auto result = advance(harness, 1);
    assert(result.ok());

    PersonId spouse{};
    PersonId last_origin_member{};
    HouseholdId origin{};
    macro_sim::EventId union_event{};
    for (const auto &union_record : harness.runtime.relationships.unions()) {
        if (union_record.active) {
            spouse = union_record.second;
            union_event = union_record.event;
            break;
        }
    }
    assert(spouse.valid() && union_event.valid());
    harness.root.households.for_each_alive(
        [&](HouseholdId household,
            const macro_sim::core::HouseholdComponent &) {
            if (origin.valid() ||
                household == harness.runtime.persons.get(spouse)->household) {
                return;
            }
            const auto members = harness.runtime.membership.members(household);
            if (members.size() == 1U) {
                origin = household;
                last_origin_member = members.front();
            }
        });
    assert(last_origin_member.valid() && origin.valid());
    auto unions = harness.runtime.relationships.unions();
    auto rewritten = std::vector<macro_sim::core::UnionRecord>(
        unions.begin(), unions.end());
    const auto selected = std::find_if(
        rewritten.begin(), rewritten.end(),
        [union_event](const macro_sim::core::UnionRecord &record) {
            return record.event == union_event;
        });
    assert(selected != rewritten.end());
    selected->second_origin_household = origin;
    assert(harness.runtime.relationships
               .replace_unions(harness.runtime.persons, std::move(rewritten))
               .ok());

    harness.runtime.rules.annual_divorce_rate = 1.0;
    M7AdvanceOptions death;
    death.force_death = last_origin_member;
    result = advance(harness, 1, death);
    if (!result.ok()) {
        std::cerr << "same-day estate/divorce failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    const auto *survivor = harness.runtime.persons.get(spouse);
    assert(survivor != nullptr && survivor->alive);
    assert(!survivor->partner.valid());
    assert(survivor->household != origin);
    assert(harness.root.households.get(origin) == nullptr);
    assert(harness.root.households.get(survivor->household) != nullptr);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_last_member_estate_moves_canonical_positions() {
    auto spec = base_spec();
    spec.population.initial_persons = 100;
    spec.population.target_household_size = 1.0;
    spec.policy.inheritance_tax_rate = 0.20;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.rules.genesis_union_target_profile.enabled = false;
    spec.rules.genesis_target_partnered_adult_share = 0.0;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);
    PersonId deceased{};
    PersonId heir{};
    for (const auto candidate : harness.runtime.persons.alive_ids()) {
        const auto *record = harness.runtime.persons.get(candidate);
        if (harness.runtime.membership.members(record->household).size() != 1U) {
            continue;
        }
        for (const auto parent : std::array{record->mother, record->father}) {
            const auto *parent_record = harness.runtime.persons.get(parent);
            if (parent_record != nullptr && parent_record->alive &&
                parent_record->household != record->household) {
                deceased = candidate;
                heir = parent;
                break;
            }
        }
        if (deceased.valid()) {
            break;
        }
    }
    if (!deceased.valid()) {
        for (const auto candidate : harness.runtime.persons.alive_ids()) {
            const auto *record = harness.runtime.persons.get(candidate);
            if (harness.runtime.membership.members(record->household).size() == 1U &&
                !record->mother.valid() && !record->father.valid()) {
                deceased = candidate;
                break;
            }
        }
        assert(deceased.valid());
        for (const auto candidate : harness.runtime.persons.alive_ids()) {
            if (candidate != deceased &&
                harness.runtime.persons.get(candidate)->household !=
                    harness.runtime.persons.get(deceased)->household) {
                heir = candidate;
                break;
            }
        }
        assert(heir.valid());
        harness.runtime.persons.get(deceased)->mother = heir;
        assert(harness.runtime.relationships
                   .register_birth(harness.runtime.persons, deceased)
                   .ok());
    }
    auto *deceased_record = harness.runtime.persons.get(deceased);
    const auto source_household = deceased_record->household;
    const auto destination_household =
        harness.runtime.persons.get(heir)->household;
    assert(source_household != destination_household);
    const auto source_account =
        harness.root.households.get(source_household)->primary_account;
    const auto source_owner = macro_sim::core::OwnerId::household(source_household);
    constexpr double dust_units = 5.0e-9;
    bool dust_position_created = false;
    for (const auto &equity : harness.financial_runtime.securities.equities()) {
        const auto security = macro_sim::core::SecurityId::equity(equity.id);
        if (harness.financial_runtime.securities.units_held(security, source_owner) !=
            0.0) {
            continue;
        }
        assert(harness.financial_runtime.securities
                   .issue_equity_units(equity.id, source_owner, dust_units,
                                       macro_sim::Money(dust_units))
                   .ok());
        dust_position_created = true;
        break;
    }
    assert(dust_position_created);
    const auto opening_households = harness.root.households.alive_count();
    M7AdvanceOptions options;
    options.force_death = deceased;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 last-member estate failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(harness.root.households.get(source_household) == nullptr);
    assert(harness.root.households.alive_count() == opening_households - 1U);
    assert(!harness.root.postings.get(source_account)->open);
    assert(harness.runtime.estates.size() == 1);
    const auto &estate = harness.runtime.estates.front();
    assert(estate.heir == heir);
    assert(estate.destination_household == destination_household);
    assert(estate.tax_paid > 0.0);
    for (const auto &security : harness.financial_runtime.securities.bonds()) {
        assert(harness.financial_runtime.securities.units_held(
                   macro_sim::core::SecurityId::bond(security.id), source_owner) ==
               0.0);
    }
    for (const auto &security : harness.financial_runtime.securities.equities()) {
        assert(harness.financial_runtime.securities.units_held(
                   macro_sim::core::SecurityId::equity(security.id), source_owner) ==
               0.0);
    }
    for (const auto &loan : harness.root.loans.records()) {
        assert(!loan.active || loan.borrower != source_owner);
    }
    for (const auto &lot : harness.root.ownership.records()) {
        assert(!lot.active || lot.owner != source_owner);
    }
    for (const auto &lot : harness.runtime.beneficial_ownership.records()) {
        assert(!lot.is_active() || lot.asset.household != source_household);
    }
    const auto continuation = advance(harness, 1);
    if (!continuation.ok()) {
        std::cerr << "M7 estate continuation failed: "
                  << continuation.status().message() << "\n";
    }
    assert(continuation.ok());
}

void test_public_residual_estate_has_no_unrelated_heir() {
    auto spec = base_spec();
    spec.population.initial_persons = 1;
    spec.population.target_household_size = 1.0;
    spec.policy.inheritance_tax_rate = 0.20;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.rules.relationships = false;
    spec.rules.household_lifecycle = false;
    spec.rules.family_transfers = false;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);
    harness.runtime.rules.relationships = true;
    harness.runtime.rules.household_lifecycle = true;
    const auto treasury = harness.root.institutions.treasury_account;
    const double opening_treasury =
        harness.root.postings.balance(treasury).get_if()->value();
    M7AdvanceOptions options;
    options.force_death = PersonId(1);
    const auto result = advance(harness, 1, options);
    assert(result.ok());
    assert(harness.runtime.estates.size() == 1U);
    const auto &estate = harness.runtime.estates.front();
    assert(!estate.heir.valid());
    assert(!estate.destination_household.valid());
    assert(estate.public_residual);
    assert(harness.root.postings.balance(treasury).get_if()->value() >
           opening_treasury);
    assert(harness.root.households.alive_count() == 0U);
}

void test_unclaimed_external_share_returns_to_asset_household() {
    auto spec = base_spec();
    spec.population.initial_persons = 3;
    spec.population.target_household_size = 1.0;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.rules.relationships = false;
    spec.rules.household_lifecycle = false;
    spec.rules.family_transfers = false;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);
    harness.runtime.rules.relationships = true;
    harness.runtime.rules.household_lifecycle = true;

    const auto deceased = PersonId(1);
    const auto surviving_owner = PersonId(2);
    const auto surviving_household =
        harness.runtime.persons.get(surviving_owner)->household;
    const auto occupied_household = harness.runtime.persons.get(PersonId(3))->household;
    const macro_sim::core::BeneficialAssetKey cash{
        macro_sim::core::BeneficialAssetKind::household_cash,
        surviving_household,
        surviving_household.value(),
    };
    const auto cash_lots = harness.runtime.beneficial_ownership.lots_for_asset(cash);
    assert(cash_lots.size() == 1U);
    const auto lot_id = cash_lots.front();
    const auto *lot = harness.runtime.beneficial_ownership.get(lot_id);
    assert(lot != nullptr && lot->owner == surviving_owner);
    assert(harness.runtime.beneficial_ownership
               .transfer(lot_id, deceased, lot->share * 0.5)
               .ok());
    assert(harness.runtime.membership.move(surviving_owner, occupied_household).ok());
    harness.runtime.persons.get(surviving_owner)->household = occupied_household;
    assert(harness.runtime.membership.members(surviving_household).empty());

    auto *deceased_record = harness.runtime.persons.get(deceased);
    deceased_record->mother = PersonId{};
    deceased_record->father = PersonId{};
    deceased_record->guardian = PersonId{};
    deceased_record->partner = PersonId{};
    M7AdvanceOptions options;
    options.force_death = deceased;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 unclaimed external share return failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());

    const auto inherited_lots =
        harness.runtime.beneficial_ownership.lots_for_asset(cash);
    double inherited_share = 0.0;
    for (const auto inherited_lot : inherited_lots) {
        const auto *inherited = harness.runtime.beneficial_ownership.get(inherited_lot);
        assert(inherited != nullptr && inherited->is_active());
        assert(inherited->owner == surviving_owner);
        inherited_share += inherited->share;
    }
    assert(std::abs(inherited_share - 1.0) < 1.0e-12);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_unclaimed_empty_household_escheats_canonical_positions() {
    auto spec = base_spec();
    spec.population.initial_persons = 3;
    spec.population.target_household_size = 1.0;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.rules.relationships = false;
    spec.rules.household_lifecycle = false;
    spec.rules.family_transfers = false;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);
    harness.runtime.rules.relationships = true;
    harness.runtime.rules.household_lifecycle = true;

    const auto first = PersonId(1);
    const auto deceased = PersonId(2);
    const auto occupied = PersonId(3);
    const auto first_household = harness.runtime.persons.get(first)->household;
    const auto orphan_household = harness.runtime.persons.get(deceased)->household;
    const auto occupied_household = harness.runtime.persons.get(occupied)->household;
    assert(harness.runtime.membership.move(first, occupied_household).ok());
    harness.runtime.persons.get(first)->household = occupied_household;
    assert(harness.runtime.membership.move(deceased, first_household).ok());
    harness.runtime.persons.get(deceased)->household = first_household;
    assert(harness.runtime.membership.members(orphan_household).empty());
    macro_sim::simulation::EstateRecord stale_estate;
    stale_estate.event = macro_sim::EventId(harness.runtime.next_event_id++);
    stale_estate.household = orphan_household;
    stale_estate.destination_household = orphan_household;
    stale_estate.opened_day = harness.runtime.current_calendar_day - 1;
    stale_estate.settled_day = harness.runtime.current_calendar_day - 1;
    stale_estate.settled = true;
    harness.runtime.estates.push_back(stale_estate);

    auto *deceased_record = harness.runtime.persons.get(deceased);
    deceased_record->mother = PersonId{};
    deceased_record->father = PersonId{};
    deceased_record->guardian = PersonId{};
    deceased_record->partner = PersonId{};
    M7AdvanceOptions options;
    options.force_death = deceased;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 empty-household escheat failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());

    assert(harness.root.households.get(orphan_household) == nullptr);
    for (const auto &lot : harness.runtime.beneficial_ownership.records()) {
        assert(!lot.is_active() || lot.asset.household != orphan_household);
    }
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_forced_leaving_home_creates_canonical_household() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    auto harness = build(spec);
    PersonId child{};
    PersonId parent{};
    for (const auto candidate : harness.runtime.persons.alive_ids()) {
        const auto *record = harness.runtime.persons.get(candidate);
        if (record->partner.valid()) {
            continue;
        }
        for (const auto candidate_parent :
             std::array{record->mother, record->father}) {
            const auto *parent_record =
                harness.runtime.persons.get(candidate_parent);
            if (parent_record != nullptr && parent_record->alive &&
                parent_record->household == record->household) {
                child = candidate;
                parent = candidate_parent;
                break;
            }
        }
        if (child.valid()) {
            break;
        }
    }
    assert(child.valid());
    assert(parent.valid());
    auto *child_record = harness.runtime.persons.get(child);
    child_record->birth_day = harness.runtime.current_calendar_day - 25 * 365;
    const auto origin = child_record->household;
    const macro_sim::core::BeneficialAssetKey origin_cash{
        macro_sim::core::BeneficialAssetKind::household_cash,
        origin,
        origin.value(),
    };
    std::vector<macro_sim::BeneficialLotId> child_cash_lots;
    for (const auto lot_id :
         harness.runtime.beneficial_ownership.lots_for_person(child)) {
        const auto *lot = harness.runtime.beneficial_ownership.get(lot_id);
        if (lot != nullptr && lot->is_active() && lot->asset == origin_cash) {
            child_cash_lots.push_back(lot_id);
        }
    }
    assert(!child_cash_lots.empty());
    for (const auto lot_id : child_cash_lots) {
        const auto *lot = harness.runtime.beneficial_ownership.get(lot_id);
        assert(harness.runtime.beneficial_ownership.transfer(lot_id, parent, lot->share)
                   .ok());
    }
    const auto opening_households = harness.root.households.alive_count();
    auto compact_watchlists = decltype(harness.financial_runtime.watchlist_equities)(
        harness.financial_runtime.watchlist_equities.begin(),
        harness.financial_runtime.watchlist_equities.end());
    harness.financial_runtime.watchlist_equities.swap(compact_watchlists);
    M7AdvanceOptions options;
    options.force_leave_home = child;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 leaving-home failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    const auto destination = harness.runtime.persons.get(child)->household;
    assert(destination != origin);
    assert(harness.root.households.alive_count() == opening_households + 1U);
    assert(harness.root.households.get(destination) != nullptr);
    assert(harness.runtime.membership.household_of(child) == destination);
    assert(harness.runtime.leaving_home.size() == 1U);
    assert(harness.runtime.beneficial_ownership.contains_asset({
        macro_sim::core::BeneficialAssetKind::household_cash,
        destination,
        destination.value(),
    }));
    const auto validation = macro_sim::simulation::validate_m7_state(
        harness.root, harness.real_runtime, harness.monetary_runtime,
        harness.financial_runtime, harness.runtime, harness.tick);
    if (!validation.ok()) {
        std::cerr << "M7 leaving-home validation failed: "
                  << validation.message() << "\n";
    }
    assert(validation.ok());
}

void test_family_transfer_uses_kin_and_conserves_cash() {
    auto spec = base_spec();
    spec.rules.family_transfers = true;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.financial_economy.monetary_economy.rules.household_credit = false;
    auto harness = build(spec);
    const auto donor_person = PersonId(1);
    PersonId recipient_person{};
    for (const auto candidate : harness.runtime.persons.alive_ids()) {
        const auto *record = harness.runtime.persons.get(candidate);
        if (record->household != harness.runtime.persons.get(donor_person)->household &&
            !record->mother.valid() && !record->father.valid()) {
            recipient_person = candidate;
            break;
        }
    }
    assert(recipient_person.valid());
    auto *recipient_record = harness.runtime.persons.get(recipient_person);
    recipient_record->mother = donor_person;
    assert(harness.runtime.relationships
               .register_birth(harness.runtime.persons, recipient_person)
               .ok());
    const auto donor_household = harness.runtime.persons.get(donor_person)->household;
    const auto recipient_household = recipient_record->household;
    auto *donor = harness.root.households.get(donor_household);
    auto *recipient = harness.root.households.get(recipient_household);
    recipient->income_expected = 20.0;
    recipient->income_realized = 20.0;
    donor->income_expected = 0.0;
    donor->income_realized = 0.0;
    const auto recipient_balance =
        harness.root.postings.balance(recipient->primary_account).get_if()->value();
    if (recipient_balance > 0.0) {
        macro_sim::core::SettlementTransaction transaction(harness.root);
        assert(transaction
                   .transfer(recipient->primary_account, donor->primary_account,
                             macro_sim::Money(recipient_balance))
                   .ok());
        assert(transaction.commit().ok());
    }
    assert(harness.runtime.rules.family_transfers);
    assert(std::abs(harness.root.postings.balance(recipient->primary_account)
                        .get_if()
                        ->value()) < 1.0e-8);
    const auto preflight = macro_sim::simulation::validate_m7_state(
        harness.root, harness.real_runtime, harness.monetary_runtime,
        harness.financial_runtime, harness.runtime, harness.tick);
    if (!preflight.ok()) {
        std::cerr << "M7 family transfer preflight failed: " << preflight.message()
                  << "\n";
    }
    assert(preflight.ok());
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M7 family transfer failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    if (result.get_if()->metrics.family_transfer_total <= 0.0) {
        std::cerr << "family transfer recipients="
                  << result.get_if()->metrics.family_transfer_recipients
                  << " exposed=" << result.get_if()->metrics.family_exposed_households
                  << "\n";
    }
    assert(result.get_if()->metrics.family_transfer_total > 0.0);
    assert(result.get_if()->metrics.family_transfer_recipients > 0.0);
}

void test_pensions_are_consolidated_into_fiscal_metrics() {
    auto spec = base_spec();
    spec.policy.pension_replacement = 0.4;
    auto harness = build(spec);
    const auto result = advance(harness, 2);
    assert(result.ok());
    const auto &metrics = result.get_if()->metrics;
    const auto &fiscal = metrics.economy.economy.economy;
    assert(metrics.pension_paid > 0.0);
    assert(fiscal.transfer_payments + 1.0e-8 >= metrics.pension_paid);
    assert(fiscal.government_spending + 1.0e-8 >= metrics.pension_paid);
}

void test_job_ladder_survives_firm_lifecycle() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.second_jobs = false;
    spec.rules.frictional_search = true;
    spec.rules.search_intensity = 0.03;
    spec.rules.job_ladder = true;
    spec.rules.ladder_search_intensity = 1.0;
    spec.rules.ladder_premium = 0.0;
    auto harness = build(spec);
    const auto result = advance(harness, 365);
    if (!result.ok()) {
        std::cerr << "M7 job ladder panel failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(harness.runtime.labor_accounts.job_to_job_moves_total > 0.0);
    assert(macro_sim::simulation::validate_m7_state(
               harness.root, harness.real_runtime, harness.monetary_runtime,
               harness.financial_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_second_jobs_and_participation_margin() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.second_jobs = true;
    spec.rules.job_ladder = false;
    spec.population.initial_persons = 128;
    spec.financial_economy.monetary_economy.real_economy.consumption_firms = 64;
    spec.financial_economy.monetary_economy.real_economy.capital_firms = 16;
    auto harness = build(spec);
    auto result = advance(harness, 5);
    assert(result.ok());
    assert(result.get_if()->metrics.second_job_heads > 0.0);
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto primary_id = harness.runtime.employment.primary_job(person_id);
        const auto secondary_id = harness.runtime.employment.secondary_job(person_id);
        const auto *secondary = harness.runtime.employment.get(secondary_id);
        if (secondary == nullptr || !secondary->active) {
            continue;
        }
        const auto *primary = harness.runtime.employment.get(primary_id);
        assert(primary != nullptr && primary->active);
        assert(primary->firm != secondary->firm);
        assert(harness.runtime.employment.active_hours(person_id) <= 1.0 + 1.0e-12);
    }

    auto participation = build();
    result = advance(participation, 1);
    assert(result.ok());
    participation.runtime.rules.reservation_markup = 100.0;
    participation.runtime.rules.welfare_quit_hazard = 1.0;
    result = advance(participation, 1);
    assert(result.ok());
    assert(participation.runtime.labor_accounts.welfare_quits_total > 0.0);
    assert(result.get_if()->metrics.nonsearching > 0.0);
}

void test_participation_exit_closes_suspended_recall_option() {
    auto harness = build();
    auto result = advance(harness, 1);
    assert(result.ok());

    PersonId worker{};
    macro_sim::JobId suspended_job{};
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto job_id = harness.runtime.employment.primary_job(person_id);
        const auto *job = harness.runtime.employment.get(job_id);
        if (job != nullptr && job->active && !job->suspended) {
            worker = person_id;
            suspended_job = job_id;
            break;
        }
    }
    assert(worker.valid());
    const double before_hours = harness.runtime.employment.active_hours(worker);
    assert(harness.runtime.employment
               .suspend(suspended_job, harness.runtime.current_calendar_day)
               .ok());
    const double after_hours = harness.runtime.employment.active_hours(worker);
    harness.runtime.labor_accounts.private_fte_outflows_total +=
        before_hours - after_hours;
    harness.runtime.labor_accounts.suspensions_total += 1.0;
    harness.runtime.rules.reservation_markup = 100.0;
    harness.runtime.rules.welfare_quit_hazard = 1.0;

    result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "suspended participation exit failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(!harness.runtime.persons.get(worker)->participating);
    const auto *closed = harness.runtime.employment.get(suspended_job);
    assert(closed != nullptr);
    assert(!closed->active);
    assert(!harness.runtime.employment.primary_job(worker).valid());
}

void test_age_participation_creates_a_stable_labor_force_margin() {
    auto spec = base_spec();
    spec.rules.age_participation = true;
    spec.rules.young_participation_rate = 0.5;
    spec.rules.prime_participation_rate = 0.5;
    spec.rules.older_participation_rate = 0.5;
    spec.population.initial_persons = 1'000;
    auto first = build(spec);
    auto second = build(spec);
    const auto first_result = advance(first, 1);
    const auto second_result = advance(second, 1);
    assert(first_result.ok());
    assert(second_result.ok());
    const auto &metrics = first_result.get_if()->metrics;
    assert(metrics.participation_rate > 0.4);
    assert(metrics.participation_rate < 0.6);
    assert(metrics.labor_supply > 0.0);
    assert(metrics.out_of_labor_force > 0.0);
    assert(first.runtime.persons.records() == second.runtime.persons.records());
    assert(first_result.get_if()->metrics == second_result.get_if()->metrics);
}

void test_second_jobs_respect_search_friction() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.second_jobs = true;
    spec.rules.job_ladder = false;
    spec.rules.frictional_search = true;
    spec.rules.search_intensity = 0.0;
    spec.population.initial_persons = 128;
    spec.financial_economy.monetary_economy.real_economy.consumption_firms = 64;
    spec.financial_economy.monetary_economy.real_economy.capital_firms = 16;
    auto harness = build(spec);
    const auto result = advance(harness, 5);
    assert(result.ok());
    assert(result.get_if()->metrics.second_job_heads == 0.0);
    assert(result.get_if()->metrics.second_job_hours == 0.0);
}

void test_recovered_demand_restores_incumbent_hours() {
    auto spec = base_spec();
    spec.financial_economy.monetary_economy.real_economy.rules.initial_firm_money =
        10'000.0;
    auto harness = build(spec);
    auto result = advance(harness, 1);
    assert(result.ok());

    macro_sim::JobId incumbent{};
    double original_hours = 0.0;
    for (const auto &job : harness.runtime.employment.records()) {
        if (job.id.valid() && job.active && !job.secondary && job.hours > 1.0e-6 &&
            !harness.runtime.employment.secondary_job(job.person).valid()) {
            incumbent = job.id;
            original_hours = job.hours;
            break;
        }
    }
    assert(incumbent.valid());
    const double reduced_hours = original_hours * 0.5;
    assert(harness.runtime.employment.set_hours(incumbent, reduced_hours).ok());
    harness.runtime.labor_accounts.private_fte_outflows_total +=
        original_hours - reduced_hours;
    const auto *incumbent_record = harness.runtime.employment.get(incumbent);
    assert(incumbent_record != nullptr);
    auto *employer = harness.root.firms.get(incumbent_record->firm);
    assert(employer != nullptr);
    employer->demand_expected = 1'000.0;
    employer->goods_inventory = macro_sim::Goods(0.0);

    result = advance(harness, 1);
    assert(result.ok());
    const auto *restored = harness.runtime.employment.get(incumbent);
    assert(restored != nullptr);
    assert(restored->active);
    assert(restored->hours > reduced_hours);
}

void test_firing_adjustment_controls_layoff_speed() {
    auto spec = base_spec();
    spec.financial_economy.monetary_economy.real_economy.rules.initial_firm_money =
        10'000.0;
    spec.rules.target_smoothing = 1.0;
    spec.rules.layoff_band = 0.0;
    spec.rules.firing_adjustment = 0.10;
    auto gradual = build(spec);
    spec.rules.firing_adjustment = 1.0;
    auto immediate = build(spec);

    assert(advance(gradual, 1).ok());
    assert(advance(immediate, 1).ok());
    const auto collapse_demand = [](Harness &harness) {
        harness.root.firms.for_each_alive(
            [](macro_sim::FirmId, macro_sim::core::FirmComponent &firm) {
                firm.demand_expected = 0.0;
                firm.sales_previous = 0.0;
                firm.rationed_previous = 0.0;
                firm.goods_inventory = macro_sim::Goods(1'000'000.0);
            });
    };
    collapse_demand(gradual);
    collapse_demand(immediate);

    const auto gradual_result = advance(gradual, 1);
    const auto immediate_result = advance(immediate, 1);
    assert(gradual_result.ok());
    assert(immediate_result.ok());
    assert(gradual_result.get_if()->metrics.employed_fte >
           immediate_result.get_if()->metrics.employed_fte);
    assert(gradual.runtime.labor_accounts.private_fte_outflows_total <
           immediate.runtime.labor_accounts.private_fte_outflows_total);
}

void test_guardianship_repairs_after_death() {
    auto harness = build();
    PersonId child{};
    PersonId guardian{};
    for (const auto person_id : harness.runtime.persons.alive_ids()) {
        const auto *person = harness.runtime.persons.get(person_id);
        if (person->guardian.valid()) {
            child = person_id;
            guardian = person->guardian;
            break;
        }
    }
    assert(child.valid() && guardian.valid());
    M7AdvanceOptions options;
    options.force_death = guardian;
    const auto result = advance(harness, 1, options);
    assert(result.ok());
    const auto *dependent = harness.runtime.persons.get(child);
    assert(dependent != nullptr && dependent->alive);
    assert(dependent->guardian != guardian);
    assert(!dependent->guardian.valid() ||
           harness.runtime.persons.alive(dependent->guardian));
}

void test_validation_rejects_invalid_population() {
    auto spec = base_spec();
    spec.population.initial_persons = 0;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.policy.inheritance_tax_rate = 1.1;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.beneficial_ownership = false;
    spec.rules.estates = true;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.efficiency_sigma = -0.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.genesis_employment_rate = -0.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.genesis_employment_rate = 1.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.suspension_quit_discount = 0.0;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.suspension_quit_discount = 1.51;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.stratification_multiplier_minimum = 1.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.stratification_multiplier_maximum = 0.99;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.lifecycle_income_propensity = -0.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.demographic_feedback_burnin_years = 0U;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
    spec = base_spec();
    spec.rules.fertility_multiplier_minimum = 1.01;
    assert(!macro_sim::simulation::validate_m7_spec(spec).ok());
}

} // namespace

int main() {
    test_genesis_derives_households_from_population();
    test_genesis_relationship_rules_have_direct_observable_effects();
    test_genesis_person_efficiency_is_mean_preserving_and_deterministic();
    test_demography_projects_age_weighted_consumption_needs();
    test_lifecycle_consumption_replaces_the_standard_budget();
    test_real_wage_signal_updates_vital_multipliers_annually();
    test_real_wage_signal_denominator_includes_unemployed_working_age_people();
    test_real_wage_signal_includes_job_guarantee_labor_income();
    test_wealth_rank_gradients_apply_bounded_vital_risk();
    test_death_and_estate_settle_exactly_once();
    test_retired_household_closes_tolerance_sized_account_residual();
    test_population_fault_is_atomic();
    test_forced_birth_and_split_determinism();
    test_persistent_labor_and_death_separation();
    test_payroll_budget_uses_worker_efficiency();
    test_labor_matching_fills_effective_units();
    test_relationship_household_lifecycle();
    test_divorce_does_not_reenter_household_retired_by_same_day_death();
    test_last_member_estate_moves_canonical_positions();
    test_public_residual_estate_has_no_unrelated_heir();
    test_unclaimed_external_share_returns_to_asset_household();
    test_unclaimed_empty_household_escheats_canonical_positions();
    test_forced_leaving_home_creates_canonical_household();
    test_family_transfer_uses_kin_and_conserves_cash();
    test_pensions_are_consolidated_into_fiscal_metrics();
    test_job_ladder_survives_firm_lifecycle();
    test_second_jobs_and_participation_margin();
    test_participation_exit_closes_suspended_recall_option();
    test_age_participation_creates_a_stable_labor_force_margin();
    test_second_jobs_respect_search_friction();
    test_recovered_demand_restores_incumbent_hours();
    test_firing_adjustment_controls_layoff_speed();
    test_guardianship_repairs_after_death();
    test_validation_rejects_invalid_population();
    return 0;
}
