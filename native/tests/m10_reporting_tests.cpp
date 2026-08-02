#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <utility>

#include "macro_sim/reporting/m10.hpp"
#include "macro_sim/reporting/probes.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::simulation;
using namespace macro_sim::reporting;

[[nodiscard]] M9World build_world(std::uint64_t initial_persons = 24U) {
    M8SimulationSpec economy;
    auto &population = economy.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 12;
    real.consumption_firms = 3;
    real.capital_firms = 1;
    real.seed = 707U;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_firm_money = 0.0;
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = initial_persons;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    economy.energy_rules.producer_count = 1;
    economy.housing_rules.enabled = false;

    M9WorldSpec spec;
    spec.economies.push_back(std::move(economy));
    spec.external_policies.resize(1);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] std::size_t metric(std::string_view stable_id) {
    auto result = public_metric_index(stable_id);
    assert(result.ok());
    return *result.get_if();
}

[[nodiscard]] std::size_t maintained_metric(std::string_view stable_id) {
    auto result = metric_index(stable_id);
    assert(result.ok());
    return *result.get_if();
}

void test_descriptors_are_stable_and_complete() {
    const auto public_descriptors = public_metric_descriptors();
    assert(public_descriptors.size() == kM10PublicMetricCount);
    const auto descriptors = metric_descriptors();
    assert(descriptors.size() == kM10MetricCount);
    assert(kM10NativeSourceMetricCount == 229U);
    assert(kM10DashboardMetricCount == 85U);
    assert(kM10NationalAccountMetricCount == 63U);
    assert(kM10MetricCount == 453U);
    for (std::size_t index = 0; index < descriptors.size(); ++index) {
        assert(!descriptors[index].stable_id.empty());
        assert(!descriptors[index].unit.empty());
        assert(!descriptors[index].parity_rule.empty());
        assert(descriptors[index].cadence_ticks >= 1U);
        for (std::size_t previous = 0; previous < index; ++previous) {
            assert(descriptors[previous].stable_id != descriptors[index].stable_id);
        }
    }
}

void test_frame_matches_native_sources() {
    auto world = build_world();
    assert(world.advance(30U).ok());
    auto frame = build_metric_frame(world);
    assert(frame.ok());
    assert(frame.get_if()->tick == world.tick());
    assert(frame.get_if()->economy_count == 1U);
    assert(frame.get_if()->values.size() == kM10MetricCount);
    const auto output = frame.get_if()->value(0U, 14U);
    const auto price = frame.get_if()->value(0U, 13U);
    assert(output.ok());
    assert(price.ok());
    const auto &real = world.last_metrics().domestic[0].economy.economy.economy.economy;
    assert(*output.get_if() == real.real_output);
    assert(*price.get_if() == real.price_index);
    assert(
        frame.get_if()->value(0U, metric("metric.economy.bank_reserves_total")).ok());
    assert(frame.get_if()->value(0U, metric("metric.economy.energy_stock_total")).ok());
    assert(frame.get_if()->value(0U, metric("metric.world.reserves_by_economy")).ok());
    assert(*frame.get_if()
                ->value(0U, maintained_metric("metric.source.m4.real_output"))
                .get_if() == real.real_output);
    assert(*frame.get_if()
                ->value(0U, maintained_metric("metric.source.m8.energy.production"))
                .get_if() == world.last_metrics().domestic[0].energy.production);
    const double nominal_gdp =
        *frame.get_if()
             ->value(0U, maintained_metric("metric.economy.na.nominal_gdp"))
             .get_if();
    assert(nominal_gdp ==
           *frame.get_if()
                ->value(0U, maintained_metric("metric.economy.na.production_nominal"))
                .get_if());
    assert(nominal_gdp ==
           *frame.get_if()
                ->value(0U, maintained_metric(
                                "metric.economy.na.expenditure_reconciled_nominal"))
                .get_if());
    assert(nominal_gdp ==
           *frame.get_if()
                ->value(0U, maintained_metric(
                                "metric.economy.na.income_reconciled_nominal"))
                .get_if());
    assert(*frame.get_if()
                ->value(0U, maintained_metric(
                                "metric.economy.na.production_reconciliation_residual"))
                .get_if() == 0.0);
    const double public_credit_ratio =
        *frame.get_if()->value(0U, metric("metric.economy.credit_to_gdp")).get_if();
    const double national_accounts_credit_ratio =
        *frame.get_if()
             ->value(0U,
                     maintained_metric("metric.economy.na.credit_to_annualized_gdp"))
             .get_if();
    assert(
        world.last_metrics().domestic[0].economy.economy.economy.total_loan_principal >
        0.0);
    assert(public_credit_ratio == national_accounts_credit_ratio);
    for (std::size_t index = 0; index < kM10MetricCount; ++index) {
        assert(frame.get_if()->value(0U, index).ok());
    }
}

void test_energy_inventory_enters_expenditure_accounts() {
    auto world = build_world();
    assert(world.advance(1U).ok());
    const auto frame = build_metric_frame(world);
    assert(frame.ok());

    const auto &domestic = world.last_metrics().domestic[0];
    const auto &real = domestic.economy.economy.economy.economy;
    const auto &energy = domestic.energy;
    const double energy_inventory_change =
        energy.production - energy.sold + std::max(0.0, energy.strategic_reserve_flow);
    const double expected_nominal = real.inventory_change_nominal +
                                    energy_inventory_change * energy.transaction_price;
    const double expected_real = real.inventory_change_real + energy_inventory_change;

    const auto nominal = frame.get_if()->value(
        0U, maintained_metric("metric.economy.na.inventory_change_nominal"));
    const auto real_change = frame.get_if()->value(
        0U, maintained_metric("metric.economy.na.inventory_change_real"));
    assert(nominal.ok());
    assert(real_change.ok());
    assert(std::abs(*nominal.get_if() - expected_nominal) < 1.0e-12);
    assert(std::abs(*real_change.get_if() - expected_real) < 1.0e-12);
}

void test_poverty_is_equivalized_and_person_weighted() {
    auto world = build_world(25U);
    auto *root = const_cast<core::RootState *>(world.economy_root(EconomyId(0U)));
    const auto *population = world.economy_population_runtime(EconomyId(0U));
    assert(root != nullptr);
    assert(population != nullptr);

    HouseholdId poor{};
    root->households.for_each_alive(
        [&](HouseholdId household_id, core::HouseholdComponent &household) {
            const auto persons = population->membership.members(household_id).size();
            assert(persons > 0U);
            household.spent = 10.0 * std::sqrt(static_cast<double>(persons));
            if (!poor.valid() && persons == 3U) {
                poor = household_id;
            }
        });
    assert(poor.valid());
    root->households.get(poor)->spent = 0.0;

    const auto frame = build_metric_frame(world);
    assert(frame.ok());
    const auto poverty =
        frame.get_if()->value(0U, metric("metric.economy.poverty_rate"));
    assert(poverty.ok());
    assert(std::abs(*poverty.get_if() - 3.0 / 25.0) < 1.0e-12);
}

void test_distribution_metrics_are_native_and_complete() {
    auto world = build_world(120U);
    assert(world.advance(30U).ok());
    const auto frame = build_metric_frame(world);
    assert(frame.ok());

    for (const auto stable_id : {
             "metric.economy.hh_wealth_gini",
             "metric.economy.wage_p90_p10_ratio",
             "metric.economy.welfare_log",
             "metric.economy.savings_rate",
             "metric.economy.bottom10_consumption",
         }) {
        const auto value = frame.get_if()->value(0U, metric(stable_id));
        assert(value.ok());
        assert(std::isfinite(*value.get_if()));
    }

    for (const auto prefix : {
             "metric.economy.income_decile_",
             "metric.economy.wealth_decile_",
             "metric.economy.consumption_decile_",
         }) {
        double total_share = 0.0;
        for (std::size_t decile = 1U; decile <= 10U; ++decile) {
            const auto stable_id =
                std::string(prefix) + std::to_string(decile) + "_share";
            const auto share = frame.get_if()->value(0U, metric(stable_id));
            assert(share.ok());
            assert(*share.get_if() >= 0.0);
            total_share += *share.get_if();
        }
        assert(std::abs(total_share - 1.0) < 1.0e-9);
    }
}

void test_history_is_bounded_and_cursor_checked() {
    auto world = build_world();
    MetricPipeline pipeline(1U, 3U);
    for (std::uint64_t index = 0; index < 5U; ++index) {
        assert(world.advance(1U).ok());
        assert(pipeline.capture(world).ok());
    }
    assert(pipeline.history().size() == 3U);
    assert(pipeline.history().oldest_sequence() == 2U);
    assert(pipeline.history().next_sequence() == 5U);
    assert(!pipeline.history().page(1U, 1U).ok());
    auto page = pipeline.history().page(2U, 8U);
    assert(page.ok());
    assert(page.get_if()->frames.size() == 3U);
    assert(page.get_if()->frames[0].tick == Tick(3U));
    assert(page.get_if()->frames[2].tick == Tick(5U));
    assert(page.get_if()->next_sequence == 5U);
}

void test_inflation_uses_only_previous_committed_frame() {
    auto world = build_world();
    MetricPipeline pipeline(1U, 4U);
    assert(world.advance(1U).ok());
    assert(pipeline.capture(world).ok());
    const auto initial = pipeline.current().value(0U, 8U);
    assert(initial.ok());
    assert(*initial.get_if() == 0.0);
    const double opening_price = *pipeline.current().value(0U, 13U).get_if();
    assert(world.advance(1U).ok());
    assert(pipeline.capture(world).ok());
    const double closing_price = *pipeline.current().value(0U, 13U).get_if();
    const double inflation = *pipeline.current().value(0U, 8U).get_if();
    assert(inflation == closing_price / opening_price - 1.0);
}

void test_shock_metrics_respect_announcement_boundary() {
    auto world = build_world();
    ShockSpec shock;
    shock.id = 801U;
    shock.kind = ShockKind::productivity;
    shock.economy = EconomyId(0U);
    shock.start = Tick(5U);
    shock.announcement = Tick(0U);
    shock.duration = 10U;
    shock.magnitude = 0.2;
    assert(world.schedule_shock(shock).ok());

    auto opening = build_metric_frame(world);
    assert(opening.ok());
    assert(
        *opening.get_if()->value(0U, metric("metric.shock.announced_count")).get_if() ==
        1.0);
    assert(*opening.get_if()->value(0U, metric("metric.shock.active_count")).get_if() ==
           0.0);
    assert(*opening.get_if()->value(0U, metric("metric.shock.time_to_next")).get_if() ==
           5.0);
    assert(*opening.get_if()
                ->value(0U, metric("metric.shock.severity.productivity"))
                .get_if() == 0.2);
    auto opening_bulletins = probe_shock_bulletins(world, EconomyId(0U), Tick(0U));
    assert(opening_bulletins.ok());
    assert(opening_bulletins.get_if()->size() == 1U);
    assert(opening_bulletins.get_if()->front().shock_id == 801U);
    assert(opening_bulletins.get_if()->front().status == ShockBulletinStatus::upcoming);
    assert(opening_bulletins.get_if()->front().intensity == 0.0);

    assert(world.advance(5U).ok());
    auto active = build_metric_frame(world, opening.get_if());
    assert(active.ok());
    assert(*active.get_if()->value(0U, metric("metric.shock.active_count")).get_if() ==
           1.0);
    assert(*active.get_if()->value(0U, metric("metric.shock.max_severity")).get_if() ==
           0.2);
    auto active_bulletins = probe_shock_bulletins(world, EconomyId(0U), Tick(5U));
    assert(active_bulletins.ok());
    assert(active_bulletins.get_if()->front().status == ShockBulletinStatus::active);
    assert(active_bulletins.get_if()->front().intensity == 1.0);
    assert(!probe_shock_bulletins(world, EconomyId(0U), Tick(6U)).ok());
}

void test_typed_probes_are_stable_and_paged() {
    auto world = build_world();
    auto first = probe_households(world, EconomyId(0U), 0U, 5U);
    assert(first.ok());
    assert(first.get_if()->page.boundary == Tick(0U));
    assert(first.get_if()->page.total_rows > 5U);
    assert(first.get_if()->rows.size() == 5U);
    assert(first.get_if()->page.has_more);
    assert(first.get_if()->page.next_after_id == 5U);
    assert(first.get_if()->rows.front().id == HouseholdId(1U));
    assert(first.get_if()->rows.front().cash >= 0.0);

    auto second =
        probe_households(world, EconomyId(0U), first.get_if()->page.next_after_id,
                         kMaximumProbePageRows);
    assert(second.ok());
    assert(second.get_if()->rows.size() ==
           first.get_if()->page.total_rows - first.get_if()->rows.size());
    assert(!second.get_if()->page.has_more);
    assert(second.get_if()->rows.front().id == HouseholdId(6U));

    auto persons = probe_persons(world, EconomyId(0U), 0U, 4U);
    assert(persons.ok());
    assert(persons.get_if()->page.total_rows == 24U);
    assert(persons.get_if()->rows.front().household.valid());

    auto firms = probe_firms(world, EconomyId(0U), 0U, 8U);
    auto banks = probe_banks(world, EconomyId(0U), 0U, 8U);
    auto equities = probe_equities(world, EconomyId(0U), 0U, 8U);
    auto positions = probe_security_positions(world, EconomyId(0U), 0U, 8U);
    auto diagnostic = probe_economy_diagnostics(world, EconomyId(0U));
    assert(firms.ok());
    assert(banks.ok());
    assert(equities.ok());
    assert(positions.ok());
    assert(diagnostic.ok());
    assert(firms.get_if()->page.total_rows >= 4U);
    assert(banks.get_if()->page.total_rows == 2U);
    assert(equities.get_if()->page.total_rows > 0U);
    assert(equities.get_if()->rows.front().price >= 0.0);
    assert(positions.get_if()->page.total_rows > 0U);
    assert(positions.get_if()->rows.front().market_value >= 0.0);
    assert(persons.get_if()->rows.front().gross_assets >= 0.0);
    assert(persons.get_if()->rows.front().net_worth ==
           persons.get_if()->rows.front().gross_assets -
               persons.get_if()->rows.front().debt);
    assert(diagnostic.get_if()->households == first.get_if()->page.total_rows);
    assert(diagnostic.get_if()->persons_alive == 24U);
    assert(diagnostic.get_if()->account_balance_total > 0.0);
    assert(diagnostic.get_if()->peg_count == 0U);
    assert(diagnostic.get_if()->pegs_intact);
    assert(!probe_households(world, EconomyId(1U), 0U, 1U).ok());
    assert(!probe_households(world, EconomyId(0U), 0U, 0U).ok());
}

void test_firm_scoped_employment_probes_return_exact_contracts() {
    auto world = build_world();
    auto *population =
        const_cast<M7Runtime *>(world.economy_population_runtime(EconomyId(0U)));
    assert(population != nullptr);
    const auto first =
        population->employment.hire(PersonId(1U), FirmId(1U), 7, 4.25, 0.75);
    const auto second =
        population->employment.hire(PersonId(2U), FirmId(2U), 8, 5.0, 1.0);
    assert(first.ok());
    assert(second.ok());
    assert(population->employment.suspend(*first.get_if(), 9).ok());

    const auto contracts =
        probe_jobs_for_firm(world, EconomyId(0U), FirmId(1U), 0U, 8U);
    assert(contracts.ok());
    assert(contracts.get_if()->page.total_rows == 1U);
    assert(contracts.get_if()->rows.size() == 1U);
    const auto &contract = contracts.get_if()->rows.front();
    assert(contract.id == *first.get_if());
    assert(contract.person == PersonId(1U));
    assert(contract.firm == FirmId(1U));
    assert(contract.hire_day == 7);
    assert(contract.suspension_day == 9);
    assert(contract.wage == 4.25);
    assert(contract.hours == 0.75);
    assert(contract.suspended);
    assert(contract.active);

    const auto people =
        probe_persons_for_firm(world, EconomyId(0U), FirmId(1U), 0U, 8U);
    assert(people.ok());
    assert(people.get_if()->page.total_rows == 1U);
    assert(people.get_if()->rows.size() == 1U);
    assert(people.get_if()->rows.front().id == PersonId(1U));
    assert(people.get_if()->rows.front().primary_job == *first.get_if());

    const auto empty = probe_jobs_for_firm(world, EconomyId(0U), FirmId(3U), 0U, 8U);
    assert(empty.ok());
    assert(empty.get_if()->rows.empty());
    assert(!probe_jobs_for_firm(world, EconomyId(0U), FirmId(999U), 0U, 8U).ok());
}

void test_household_scoped_probes_return_every_member() {
    auto world = build_world(24U);
    auto *population =
        const_cast<M7Runtime *>(world.economy_population_runtime(EconomyId(0U)));
    assert(population != nullptr);
    const auto household = HouseholdId(1U);
    const auto expected_members = population->membership.members(household);
    assert(expected_members.size() > 1U);

    const auto hired = population->employment.hire(expected_members.front(), FirmId(1U),
                                                   7, 4.25, 0.75);
    assert(hired.ok());

    const auto people =
        probe_persons_for_household(world, EconomyId(0U), household, 0U, 8U);
    assert(people.ok());
    assert(people.get_if()->page.total_rows == expected_members.size());
    assert(people.get_if()->rows.size() == expected_members.size());
    for (const auto &person : people.get_if()->rows) {
        assert(person.household == household);
    }

    const auto contracts =
        probe_jobs_for_household(world, EconomyId(0U), household, 0U, 8U);
    assert(contracts.ok());
    assert(contracts.get_if()->page.total_rows == 1U);
    assert(contracts.get_if()->rows.size() == 1U);
    assert(contracts.get_if()->rows.front().id == *hired.get_if());
    assert(contracts.get_if()->rows.front().person == expected_members.front());

    assert(!probe_persons_for_household(world, EconomyId(0U), HouseholdId(999U), 0U, 8U)
                .ok());
    assert(!probe_jobs_for_household(world, EconomyId(0U), HouseholdId(999U), 0U, 8U)
                .ok());
}

void test_diagnostic_counts_operating_banks() {
    auto world = build_world();
    auto *root =
        const_cast<macro_sim::core::RootState *>(world.economy_root(EconomyId(0U)));
    assert(root != nullptr);
    auto *failed = root->banks.get(macro_sim::BankId(1U));
    assert(failed != nullptr);
    failed->alive = false;

    const auto diagnostic = probe_economy_diagnostics(world, EconomyId(0U));
    assert(diagnostic.ok());
    assert(root->banks.alive_count() == 2U);
    assert(diagnostic.get_if()->banks == 1U);
}

} // namespace

int main() {
    test_descriptors_are_stable_and_complete();
    test_frame_matches_native_sources();
    test_energy_inventory_enters_expenditure_accounts();
    test_poverty_is_equivalized_and_person_weighted();
    test_distribution_metrics_are_native_and_complete();
    test_history_is_bounded_and_cursor_checked();
    test_inflation_uses_only_previous_committed_frame();
    test_shock_metrics_respect_announcement_boundary();
    test_typed_probes_are_stable_and_paged();
    test_firm_scoped_employment_probes_return_exact_contracts();
    test_household_scoped_probes_return_every_member();
    test_diagnostic_counts_operating_banks();
    std::cout << "M10 reporting tests passed\n";
    return 0;
}
