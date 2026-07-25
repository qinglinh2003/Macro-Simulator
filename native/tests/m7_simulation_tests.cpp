#include <algorithm>
#include <cassert>
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
    assert(harness.runtime.beneficial_ownership.size() >= 100);
    bool has_security_claim = false;
    bool has_debt_claim = false;
    for (const auto &lot :
         harness.runtime.beneficial_ownership.records()) {
        has_security_claim =
            has_security_claim ||
            lot.asset.kind ==
                macro_sim::core::BeneficialAssetKind::
                    security_position;
        has_debt_claim =
            has_debt_claim ||
            lot.asset.kind ==
                macro_sim::core::BeneficialAssetKind::
                    household_debt;
    }
    assert(has_security_claim);
    const bool has_household_loan =
        std::any_of(
            harness.root.loans.records().begin(),
            harness.root.loans.records().end(),
            [](const macro_sim::core::LoanRecord &loan) {
                return loan.active &&
                       loan.borrower.kind ==
                           macro_sim::core::OwnerKind::
                               household;
            }
        );
    assert(!has_household_loan || has_debt_claim);
    assert(harness.runtime.last_metrics.population == 100);
    assert(harness.runtime.last_metrics.households_with_members == 40);
    std::uint64_t referenced_children = 0;
    for (const auto person_id :
         harness.runtime.persons.alive_ids()) {
        const auto *person =
            harness.runtime.persons.get(person_id);
        if (person->mother.valid() || person->father.valid()) {
            ++referenced_children;
            assert(person->guardian.valid());
            assert(
                harness.runtime.persons.alive(person->guardian)
            );
            assert(
                harness.runtime.persons.get(person->guardian)
                    ->household == person->household
            );
        }
    }
    assert(referenced_children > 0);
    assert(!harness.runtime.relationships.unions().empty());
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
    if (!result.ok()) {
        std::cerr << "M7 marriage failed: "
                  << result.status().message() << "\n";
    }
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
    if (!result.ok()) {
        std::cerr << "M7 divorce failed: "
                  << result.status().message() << "\n";
    }
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

void test_last_member_estate_moves_canonical_positions() {
    auto spec = base_spec();
    spec.population.initial_persons = 3;
    spec.population.target_household_size = 1.0;
    spec.policy.inheritance_tax_rate = 0.20;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.financial_economy.monetary_economy.rules
        .household_credit = false;
    auto harness = build(spec);
    const auto source_household =
        harness.runtime.persons.get(PersonId(1))->household;
    const auto destination_household =
        harness.runtime.persons.get(PersonId(2))->household;
    assert(source_household != destination_household);
    const auto source_account =
        harness.root.households.get(source_household)
            ->primary_account;
    const auto opening_households =
        harness.root.households.alive_count();
    M7AdvanceOptions options;
    options.force_death = PersonId(1);
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 last-member estate failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(
        harness.root.households.get(source_household) == nullptr
    );
    assert(
        harness.root.households.alive_count() ==
        opening_households - 1U
    );
    assert(!harness.root.postings.get(source_account)->open);
    assert(harness.runtime.estates.size() == 1);
    const auto &estate = harness.runtime.estates.front();
    assert(estate.heir == PersonId(2));
    assert(
        estate.destination_household ==
        destination_household
    );
    assert(estate.tax_paid > 0.0);
    const auto source_owner =
        macro_sim::core::OwnerId::household(source_household);
    for (const auto &security :
         harness.financial_runtime.securities.bonds()) {
        assert(
            harness.financial_runtime.securities.units_held(
                macro_sim::core::SecurityId::bond(security.id),
                source_owner
            ) == 0.0
        );
    }
    for (const auto &security :
         harness.financial_runtime.securities.equities()) {
        assert(
            harness.financial_runtime.securities.units_held(
                macro_sim::core::SecurityId::equity(security.id),
                source_owner
            ) == 0.0
        );
    }
    for (const auto &loan : harness.root.loans.records()) {
        assert(!loan.active || loan.borrower != source_owner);
    }
    for (const auto &lot : harness.root.ownership.records()) {
        assert(!lot.active || lot.owner != source_owner);
    }
    for (const auto &lot :
         harness.runtime.beneficial_ownership.records()) {
        assert(
            !lot.active ||
            lot.asset.household != source_household
        );
    }
    const auto continuation = advance(harness, 1);
    if (!continuation.ok()) {
        std::cerr << "M7 estate continuation failed: "
                  << continuation.status().message() << "\n";
    }
    assert(continuation.ok());
}

void test_forced_leaving_home_creates_canonical_household() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    auto harness = build(spec);
    PersonId child{};
    PersonId parent{};
    for (const auto household_id :
         std::vector<HouseholdId>{
             harness.runtime.persons.get(PersonId(1))->household
         }) {
        const auto members =
            harness.runtime.membership.members(household_id);
        for (const auto candidate : members) {
            const auto *record =
                harness.runtime.persons.get(candidate);
            const double age =
                static_cast<double>(
                    harness.runtime.current_calendar_day -
                    record->birth_day
                ) /
                365.2425;
            if (age >= 22.0) {
                child = candidate;
                break;
            }
        }
        for (const auto candidate : members) {
            if (candidate != child) {
                parent = candidate;
                break;
            }
        }
    }
    if (!child.valid() || !parent.valid()) {
        for (const auto household_id :
             std::vector<HouseholdId>{
                 harness.runtime.persons.get(PersonId(4))->household,
                 harness.runtime.persons.get(PersonId(7))->household,
             }) {
            const auto members =
                harness.runtime.membership.members(household_id);
            if (members.size() < 2U) {
                continue;
            }
            child = members.front();
            parent = members.back();
            auto *record = harness.runtime.persons.get(child);
            record->birth_day =
                harness.runtime.current_calendar_day -
                25 * 365;
            break;
        }
    }
    assert(child.valid());
    assert(parent.valid());
    auto *child_record = harness.runtime.persons.get(child);
    child_record->mother = parent;
    assert(
        harness.runtime.relationships.register_birth(
            harness.runtime.persons, child
        )
            .ok()
    );
    const auto origin = child_record->household;
    const auto opening_households =
        harness.root.households.alive_count();
    M7AdvanceOptions options;
    options.force_leave_home = child;
    const auto result = advance(harness, 1, options);
    if (!result.ok()) {
        std::cerr << "M7 leaving-home failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    const auto destination =
        harness.runtime.persons.get(child)->household;
    assert(destination != origin);
    assert(
        harness.root.households.alive_count() ==
        opening_households + 1U
    );
    assert(harness.root.households.get(destination) != nullptr);
    assert(
        harness.runtime.membership.household_of(child) ==
        destination
    );
    assert(harness.runtime.leaving_home.size() == 1U);
    assert(
        harness.runtime.beneficial_ownership.contains_asset(
            {
                macro_sim::core::BeneficialAssetKind::
                    household_cash,
                destination,
                destination.value(),
            }
        )
    );
    assert(
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime,
            harness.financial_runtime, harness.runtime,
            harness.tick
        )
            .ok()
    );
}

void test_family_transfer_uses_kin_and_conserves_cash() {
    auto spec = base_spec();
    spec.rules.family_transfers = true;
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.leaving_home = false;
    spec.financial_economy.monetary_economy.rules
        .household_credit = false;
    auto harness = build(spec);
    const auto donor_person = PersonId(1);
    PersonId recipient_person{};
    for (const auto candidate :
         harness.runtime.persons.alive_ids()) {
        const auto *record =
            harness.runtime.persons.get(candidate);
        if (record->household !=
                harness.runtime.persons.get(donor_person)->household &&
            !record->mother.valid() &&
            !record->father.valid()) {
            recipient_person = candidate;
            break;
        }
    }
    assert(recipient_person.valid());
    auto *recipient_record =
        harness.runtime.persons.get(recipient_person);
    recipient_record->mother = donor_person;
    assert(
        harness.runtime.relationships.register_birth(
            harness.runtime.persons, recipient_person
        )
            .ok()
    );
    const auto donor_household =
        harness.runtime.persons.get(donor_person)->household;
    const auto recipient_household =
        recipient_record->household;
    auto *donor =
        harness.root.households.get(donor_household);
    auto *recipient =
        harness.root.households.get(recipient_household);
    recipient->income_expected = 20.0;
    recipient->income_realized = 20.0;
    donor->income_expected = 0.0;
    donor->income_realized = 0.0;
    const auto recipient_balance =
        harness.root.postings
            .balance(recipient->primary_account)
            .get_if()
            ->value();
    if (recipient_balance > 0.0) {
        macro_sim::core::SettlementTransaction transaction(
            harness.root
        );
        assert(
            transaction
                .transfer(
                    recipient->primary_account,
                    donor->primary_account,
                    macro_sim::Money(recipient_balance)
                )
                .ok()
        );
        assert(transaction.commit().ok());
    }
    assert(harness.runtime.rules.family_transfers);
    assert(
        std::abs(
            harness.root.postings
                .balance(recipient->primary_account)
                .get_if()
                ->value()
        ) < 1.0e-8
    );
    const auto preflight =
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime,
            harness.financial_runtime, harness.runtime,
            harness.tick
        );
    if (!preflight.ok()) {
        std::cerr << "M7 family transfer preflight failed: "
                  << preflight.message() << "\n";
    }
    assert(preflight.ok());
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "M7 family transfer failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    if (result.get_if()->metrics.family_transfer_total <= 0.0) {
        std::cerr << "family transfer recipients="
                  << result.get_if()
                         ->metrics.family_transfer_recipients
                  << " exposed="
                  << result.get_if()
                         ->metrics.family_exposed_households
                  << "\n";
    }
    assert(result.get_if()->metrics.family_transfer_total > 0.0);
    assert(
        result.get_if()->metrics.family_transfer_recipients >
        0.0
    );
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
        std::cerr << "M7 job ladder panel failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(
        result.get_if()->metrics.job_to_job_moves > 0.0
    );
    assert(
        macro_sim::simulation::validate_m7_state(
            harness.root, harness.real_runtime,
            harness.monetary_runtime,
            harness.financial_runtime, harness.runtime,
            harness.tick
        )
            .ok()
    );
}

void test_second_jobs_and_participation_margin() {
    auto spec = base_spec();
    spec.rules.marriage = false;
    spec.rules.divorce = false;
    spec.rules.second_jobs = true;
    spec.rules.job_ladder = false;
    spec.population.initial_persons = 128;
    spec.financial_economy.monetary_economy.real_economy
        .consumption_firms = 8;
    spec.financial_economy.monetary_economy.real_economy
        .capital_firms = 3;
    auto harness = build(spec);
    auto result = advance(harness, 5);
    assert(result.ok());
    assert(result.get_if()->metrics.second_job_heads > 0.0);
    for (const auto person_id :
         harness.runtime.persons.alive_ids()) {
        const auto primary_id =
            harness.runtime.employment.primary_job(person_id);
        const auto secondary_id =
            harness.runtime.employment.secondary_job(person_id);
        const auto *secondary =
            harness.runtime.employment.get(secondary_id);
        if (secondary == nullptr || !secondary->active) {
            continue;
        }
        const auto *primary =
            harness.runtime.employment.get(primary_id);
        assert(primary != nullptr && primary->active);
        assert(primary->firm != secondary->firm);
        assert(
            harness.runtime.employment.active_hours(person_id) <=
            1.0 + 1.0e-12
        );
    }

    harness.runtime.rules.reservation_markup = 100.0;
    harness.runtime.rules.welfare_quit_hazard = 1.0;
    result = advance(harness, 1);
    assert(result.ok());
    assert(
        harness.runtime.labor_accounts.welfare_quits_total >
        0.0
    );
    assert(result.get_if()->metrics.nonsearching > 0.0);
}

void test_guardianship_repairs_after_death() {
    auto harness = build();
    PersonId child{};
    PersonId guardian{};
    for (const auto person_id :
         harness.runtime.persons.alive_ids()) {
        const auto *person =
            harness.runtime.persons.get(person_id);
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
    const auto *dependent =
        harness.runtime.persons.get(child);
    assert(dependent != nullptr && dependent->alive);
    assert(dependent->guardian != guardian);
    assert(
        !dependent->guardian.valid() ||
        harness.runtime.persons.alive(dependent->guardian)
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
    test_last_member_estate_moves_canonical_positions();
    test_forced_leaving_home_creates_canonical_household();
    test_family_transfer_uses_kin_and_conserves_cash();
    test_job_ladder_survives_firm_lifecycle();
    test_second_jobs_and_participation_margin();
    test_guardianship_repairs_after_death();
    test_validation_rejects_invalid_population();
    return 0;
}
