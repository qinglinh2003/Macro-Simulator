#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m7.hpp"

namespace {

using macro_sim::HouseholdId;
using macro_sim::PersonId;
using macro_sim::Tick;
using macro_sim::core::PersonSex;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M7AdvanceOptions;
using macro_sim::simulation::M7SimulationSpec;
using macro_sim::simulation::capability_bit;

[[nodiscard]] M7SimulationSpec base_spec() {
    M7SimulationSpec spec;
    auto &real =
        spec.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 6;
    real.capital_firms = 2;
    real.seed = 71;
    real.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
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
        std::cerr << "M7 genesis failed: "
                  << initialization.status().message() << "\n";
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
    harness.financial_scratch.reserve(
        harness.root, harness.financial_runtime
    );
    harness.scratch.reserve(harness.runtime);
    return harness;
}

[[nodiscard]] macro_sim::Result<
    macro_sim::simulation::M7AdvanceResult
>
advance(Harness &harness, std::uint64_t count,
        const M7AdvanceOptions &options = {}) {
    return macro_sim::simulation::advance_m7_ticks(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch,
        harness.financial_runtime, harness.financial_scratch,
        harness.runtime, harness.scratch, harness.tick, count, options
    );
}

void test_genesis_derives_households_from_population() {
    auto harness = build();
    assert(harness.root.households.alive_count() == 40);
    assert(harness.runtime.persons.alive_count() == 100);
    assert(harness.runtime.beneficial_ownership.size() == 100);
    assert(harness.runtime.last_metrics.population == 100);
    assert(harness.runtime.last_metrics.households_with_members == 40);
    assert(
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime, harness.monetary_runtime,
            harness.financial_runtime, harness.runtime, harness.tick
        )
            .ok()
    );
    harness.root.households.for_each_alive(
        [&](HouseholdId id, const macro_sim::core::HouseholdComponent &) {
            const auto count = harness.runtime.membership.members(id).size();
            assert(count == 2 || count == 3);
        }
    );
}

void test_death_and_estate_settle_exactly_once() {
    auto harness = build();
    const auto household =
        harness.runtime.persons.get(PersonId(1))->household;
    const auto opening_members =
        harness.runtime.membership.members(household).size();
    const auto opening_lots =
        harness.runtime.beneficial_ownership.lots_for_person(PersonId(1)).size();
    M7AdvanceOptions options;
    options.force_death = PersonId(1);
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 forced death failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.tick == Tick(1));
    assert(!harness.runtime.persons.alive(PersonId(1)));
    assert(harness.runtime.persons.archived_count() == 1);
    assert(
        harness.runtime.membership.members(household).size() ==
        opening_members - 1
    );
    assert(
        harness.runtime.beneficial_ownership
            .lots_for_person(PersonId(1))
            .empty()
    );
    assert(harness.runtime.estates.size() == 1);
    assert(harness.runtime.estates[0].settled);
    assert(
        harness.runtime.estates[0].transferred_lots == opening_lots
    );
    assert(result.get_if()->metrics.deaths == 1);
    assert(result.get_if()->metrics.estates_settled == 1);
    assert(
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime, harness.monetary_runtime,
            harness.financial_runtime, harness.runtime, harness.tick
        )
            .ok()
    );

    const auto before_tick = harness.tick;
    const auto before_estates = harness.runtime.estates;
    const auto repeated = advance(harness, 1, options);
    assert(!repeated.ok());
    assert(harness.tick == before_tick);
    assert(harness.runtime.estates == before_estates);
}

void test_population_fault_is_atomic() {
    auto harness = build();
    const auto root_digest = macro_sim::core::state_digest(harness.root);
    const auto people = harness.runtime.persons.records();
    const auto ownership =
        harness.runtime.beneficial_ownership.records();
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
    assert(
        harness.runtime.beneficial_ownership.records() == ownership
    );
    assert(harness.runtime.estates.empty());
    assert(harness.financial_runtime.securities.lots() == securities);
    assert(harness.financial_runtime.firms == financial_firms);
}

void test_forced_birth_and_split_determinism() {
    auto direct = build();
    PersonId mother{};
    for (const auto id : direct.runtime.persons.alive_ids()) {
        const auto *person = direct.runtime.persons.get(id);
        const double age =
            static_cast<double>(
                direct.runtime.current_calendar_day - person->birth_day
            ) /
            365.2425;
        if (person->sex == PersonSex::female && age >= 15.0 &&
            age <= 49.0) {
            mother = id;
            break;
        }
    }
    assert(mother.valid());
    M7AdvanceOptions birth;
    birth.force_birth = mother;
    const auto born = advance(direct, 1, birth);
    assert(born.ok());
    assert(direct.runtime.persons.alive_count() == 101);
    assert(born.get_if()->metrics.births == 1);
    const auto *baby = direct.runtime.persons.get(PersonId(101));
    assert(baby != nullptr);
    assert(baby->mother == mother);
    assert(
        direct.runtime.membership.household_of(PersonId(101)) ==
        direct.runtime.persons.get(mother)->household
    );

    auto batch = build();
    auto split = build();
    auto result = advance(batch, 12);
    assert(result.ok());
    for (std::uint64_t index = 0; index < 12; ++index) {
        result = advance(split, 1);
        assert(result.ok());
    }
    assert(batch.tick == split.tick);
    assert(batch.runtime.persons.records() ==
           split.runtime.persons.records());
    assert(
        batch.runtime.beneficial_ownership.records() ==
        split.runtime.beneficial_ownership.records()
    );
    assert(batch.runtime.estates == split.runtime.estates);
    assert(batch.runtime.last_metrics == split.runtime.last_metrics);
    assert(
        batch.runtime.employment.records() ==
        split.runtime.employment.records()
    );
    assert(
        batch.runtime.labor_accounts ==
        split.runtime.labor_accounts
    );
}

void test_persistent_labor_and_death_separation() {
    auto harness = build();
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.employed_heads > 0.0);
    assert(result.get_if()->metrics.employed_fte > 0.0);
    assert(result.get_if()->metrics.hires > 0.0);
    assert(
        harness.runtime.employment.validate(
            harness.runtime.persons, harness.root,
            harness.root.accounting_tolerance
        )
            .ok()
    );
    assert(
        macro_sim::core::validate_labor_accounts(
            harness.runtime.labor_accounts,
            harness.root.accounting_tolerance
        )
            .ok()
    );
    PersonId worker{};
    for (const auto person : harness.runtime.persons.alive_ids()) {
        if (harness.runtime.employment
                .primary_job(person)
                .valid()) {
            worker = person;
            break;
        }
    }
    assert(worker.valid());
    const auto death_flow =
        harness.runtime.labor_accounts.death_separations_total;
    M7AdvanceOptions death;
    death.force_death = worker;
    result = advance(harness, 1, death);
    assert(result.ok());
    assert(!harness.runtime.persons.alive(worker));
    assert(
        !harness.runtime.employment.primary_job(worker).valid()
    );
    assert(
        harness.runtime.labor_accounts.death_separations_total ==
        death_flow + 1.0
    );
    assert(
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime, harness.financial_runtime,
            harness.runtime, harness.tick
        )
            .ok()
    );
}

void test_relationship_household_lifecycle() {
    auto spec = base_spec();
    spec.population.start_calendar_day = 29;
    spec.rules.marriage_interval_days = 30;
    spec.rules.annual_marriage_rate = 1.0;
    spec.rules.annual_divorce_rate = 0.0;
    auto harness = build(spec);
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.marriages > 0);
    assert(
        harness.runtime.relationships
            .validate(harness.runtime.persons)
            .ok()
    );
    PersonId partnered{};
    for (const auto person : harness.runtime.persons.alive_ids()) {
        if (harness.runtime.persons.get(person)->partner.valid()) {
            partnered = person;
            break;
        }
    }
    assert(partnered.valid());
    const auto partner =
        harness.runtime.persons.get(partnered)->partner;
    assert(
        harness.runtime.membership.household_of(partnered) ==
        harness.runtime.membership.household_of(partner)
    );

    harness.runtime.rules.annual_divorce_rate = 1.0;
    result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.divorces > 0);
    assert(
        harness.runtime.relationships
            .validate(harness.runtime.persons)
            .ok()
    );

    spec = base_spec();
    spec.population.start_calendar_day = 29;
    spec.rules.marriage_interval_days = 30;
    spec.rules.annual_marriage_rate = 1.0;
    spec.rules.annual_divorce_rate = 0.0;
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
    assert(
        harness.runtime.relationships
            .validate(harness.runtime.persons)
            .ok()
    );
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
}

} // namespace

int main() {
    test_genesis_derives_households_from_population();
    test_death_and_estate_settle_exactly_once();
    test_population_fault_is_atomic();
    test_forced_birth_and_split_determinism();
    test_persistent_labor_and_death_separation();
    test_relationship_household_lifecycle();
    test_validation_rejects_invalid_population();
    return 0;
}
