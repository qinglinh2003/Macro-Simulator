#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "macro_sim/simulation/m7_checkpoint.hpp"
#include "macro_sim/simulation/m8.hpp"

namespace {

using macro_sim::Tick;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec market_spec(bool mortgages, bool rentals) {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &real = population.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 3;
    real.capital_firms = 1;
    real.seed = 8200;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_household_money = 80.0;
    real.rules.initial_firm_money = 20.0;
    real.rules.initial_consumption_inventory = 5.0;
    real.rules.initial_capital_inventory = 5.0;
    real.rules.initial_wage = 2.0;
    auto &monetary = population.financial_economy.monetary_economy;
    monetary.rules.bank_count = 2;
    monetary.rules.household_credit = true;
    monetary.rules.household_amortization = 0.0;
    monetary.rules.opening_capital_per_bank = 1'000.0;
    monetary.policy.household_credit_limit = 1'000.0;
    population.financial_economy.rules.portfolio_review_interval_days = 1U;
    population.population.initial_persons = 20;
    population.population.target_household_size = 2.0;
    population.population.start_calendar_day = 18'000;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.enabled = false;
    value.housing_rules.enabled = true;
    value.housing_rules.resale_market = true;
    value.housing_rules.mortgages = mortgages;
    value.housing_rules.rentals = rentals;
    value.housing_rules.market_interval_days = 1;
    value.housing_rules.house_price_income_years = mortgages ? 0.20 : 0.02;
    value.housing_rules.initial_dwellings_per_household = 1.0;
    value.housing_rules.initial_homeownership_share = 0.5;
    value.housing_rules.initial_rent_yield = 0.05;
    value.housing_rules.voluntary_ask_markup = 0.0;
    value.housing_rules.ask_decay = 0.0;
    value.housing_rules.buyer_liquidity_buffer = 0.0;
    value.housing_rules.distress_deposit_floor = 0.0;
    value.housing_policy.mortgage_ltv_cap = 0.8;
    value.housing_policy.mortgage_underwriting = false;
    value.housing_policy.transfer_tax_rate = 0.01;
    return value;
}

struct Harness final {
    macro_sim::core::RootState root;
    M4Runtime real_runtime;
    M4TickScratch real_scratch;
    M5Runtime monetary_runtime;
    M5TickScratch monetary_scratch;
    M6Runtime financial_runtime;
    M6TickScratch financial_scratch;
    M7Runtime population_runtime;
    M7TickScratch population_scratch;
    M8Runtime runtime;
    M8TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build(M8SimulationSpec value) {
    auto initialized = build_m8_genesis(value);
    if (!initialized.ok()) {
        std::cerr << "housing market genesis failed: " << initialized.status().message()
                  << "\n";
    }
    assert(initialized.ok());
    auto state = std::move(*initialized.get_if());
    Harness result{
        std::move(state.root),
        std::move(state.real_economy_runtime),
        {},
        std::move(state.monetary_runtime),
        {},
        std::move(state.financial_runtime),
        {},
        std::move(state.population_runtime),
        {},
        std::move(state.runtime),
        {},
        Tick{},
    };
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(result.root, result.financial_runtime);
    result.population_scratch.reserve(result.population_runtime);
    result.scratch.reserve(result.root, result.runtime);
    return result;
}

[[nodiscard]] macro_sim::Result<M8AdvanceResult> advance(Harness &harness,
                                                         std::uint64_t count) {
    return advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                            harness.monetary_runtime, harness.monetary_scratch,
                            harness.financial_runtime, harness.financial_scratch,
                            harness.population_runtime, harness.population_scratch,
                            harness.runtime, harness.scratch, harness.tick, count);
}

[[nodiscard]] std::vector<std::uint8_t> base_checkpoint(const Harness &harness) {
    auto bytes = save_m7_checkpoint(harness.root, harness.real_runtime,
                                    harness.monetary_runtime, harness.financial_runtime,
                                    harness.population_runtime, harness.tick);
    assert(bytes.ok());
    return *bytes.get_if();
}

void test_cash_resale_moves_money_title_and_occupancy() {
    auto harness = build(market_spec(false, false));
    const auto events_before = harness.runtime.properties.title_events().size();
    const auto money_before = harness.root.genesis_money;
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "cash housing session failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(result.get_if()->metrics.housing.session_sales > 0.0);
    assert(result.get_if()->metrics.housing.session_volume > 0.0);
    assert(result.get_if()->metrics.housing.transfer_tax_paid > 0.0);
    assert(harness.runtime.properties.title_events().size() > events_before);
    assert(harness.root.genesis_money == money_before);
    assert(harness.runtime.properties.validate().ok());
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_mortgage_origination_is_canonical_and_collateralized() {
    auto spec = market_spec(true, false);
    spec.housing_policy.mortgage_underwriting = true;
    spec.housing_policy.mortgage_dsti_cap = 2.0;
    spec.housing_policy.mortgage_stress_rate_addon = 0.001;
    auto harness = build(spec);
    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "mortgage housing session failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(!harness.runtime.mortgages.empty());
    const auto &mortgage = harness.runtime.mortgages.front();
    assert(mortgage.active);
    assert(mortgage.loan.value() <= harness.root.loans.records().size());
    const auto &loan =
        harness.root.loans
            .records()[static_cast<std::size_t>(mortgage.loan.value() - 1)];
    assert(loan.id == mortgage.loan);
    assert(loan.active);
    assert(loan.borrower == macro_sim::core::OwnerId::household(mortgage.borrower));
    assert(harness.runtime.properties.dwelling_for_collateral(mortgage.loan) ==
           mortgage.collateral);
    assert(result.get_if()->metrics.housing.mortgage_originations > 0.0);
    assert(result.get_if()->metrics.housing.mortgage_principal_originated > 0.0);
    assert(result.get_if()->metrics.housing.mortgage_applications > 0.0);
    assert(result.get_if()->metrics.housing.mortgage_underwriting_applications > 0.0);
    assert(result.get_if()->metrics.housing.mortgage_dsti_rejections <
           result.get_if()->metrics.housing.mortgage_underwriting_applications);
    assert(std::abs(result.get_if()->metrics.housing.mortgage_dsti_cap_applied - 2.0) <
           1.0e-12);
    assert(
        std::abs(result.get_if()->metrics.housing.mortgage_stress_rate_addon_applied -
                 0.001) < 1.0e-12);
    assert(mortgage.underwriting_applied);
    assert(std::abs(mortgage.dsti_cap_at_origination - 2.0) < 1.0e-12);
    assert(std::abs(mortgage.stress_rate_addon_at_origination - 0.001) < 1.0e-12);

    harness.runtime.housing_policy.mortgage_underwriting = false;
    harness.runtime.housing_policy.mortgage_dsti_cap = 0.25;
    harness.runtime.housing_policy.mortgage_stress_rate_addon = 0.004;
    const auto cohort_result = advance(harness, 1);
    assert(cohort_result.ok());
    const auto &legacy = harness.runtime.mortgages.front();
    assert(legacy.underwriting_applied);
    assert(std::abs(legacy.dsti_cap_at_origination - 2.0) < 1.0e-12);
    assert(std::abs(legacy.stress_rate_addon_at_origination - 0.001) < 1.0e-12);
    assert(std::abs(cohort_result.get_if()
                        ->metrics.housing.mortgage_underwritten_principal_share -
                    1.0) < 1.0e-12);
    assert(
        std::abs(
            cohort_result.get_if()->metrics.housing.mortgage_cohort_weighted_dsti_cap -
            2.0) < 1.0e-12);
    assert(std::abs(cohort_result.get_if()
                        ->metrics.housing.mortgage_cohort_weighted_stress_rate_addon -
                    0.001) < 1.0e-12);
}

void test_mortgage_capital_rules_have_dose_and_withdrawal_contract() {
    const auto run_with_capital_rules = [](double risk_weight,
                                           double minimum_capital_ratio) {
        auto spec = market_spec(true, false);
        spec.domestic_economy.financial_economy.monetary_economy.rules
            .opening_capital_per_bank = 10.0;
        spec.housing_policy.mortgage_underwriting = true;
        spec.housing_policy.mortgage_dsti_cap = 2.0;
        spec.housing_policy.mortgage_risk_weight = risk_weight;
        spec.housing_policy.mortgage_minimum_capital_ratio = minimum_capital_ratio;
        auto harness = build(spec);
        const auto result = advance(harness, 1);
        assert(result.ok());
        return result.get_if()->metrics.housing;
    };

    const auto loose = run_with_capital_rules(0.10, 0.01);
    const auto binding = run_with_capital_rules(2.0, 1.0);
    const auto withdrawn = run_with_capital_rules(0.10, 0.01);
    assert(loose.mortgage_underwriting_applications > 0.0);
    assert(binding.mortgage_underwriting_applications > 0.0);
    assert(std::abs(loose.mortgage_risk_weight_applied - 0.10) < 1.0e-12);
    assert(std::abs(loose.mortgage_minimum_capital_ratio_applied - 0.01) <
           1.0e-12);
    assert(std::abs(binding.mortgage_risk_weight_applied - 2.0) < 1.0e-12);
    assert(std::abs(binding.mortgage_minimum_capital_ratio_applied - 1.0) <
           1.0e-12);
    assert(loose.mortgage_rwa_principal_capacity >
           binding.mortgage_rwa_principal_capacity);
    assert(binding.mortgage_rwa_rejections > 0.0);
    assert(loose.mortgage_originations > binding.mortgage_originations);
    assert(std::abs(withdrawn.mortgage_rwa_principal_capacity -
                    loose.mortgage_rwa_principal_capacity) < 1.0e-12);
    assert(withdrawn.mortgage_originations == loose.mortgage_originations);
}

void test_mortgage_follows_heir_when_borrower_household_retires() {
    auto spec = market_spec(true, false);
    spec.domestic_economy.population.target_household_size = 1.0;
    auto harness = build(spec);
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(!harness.runtime.mortgages.empty());
    const auto original = harness.runtime.mortgages.front();
    const auto members =
        harness.population_runtime.membership.members(original.borrower);
    assert(members.size() == 1U);
    const auto deceased = members.front();
    auto *deceased_record = harness.population_runtime.persons.get(deceased);
    macro_sim::PersonId heir{};
    for (const auto candidate :
         std::array{deceased_record->mother, deceased_record->father}) {
        const auto *record = harness.population_runtime.persons.get(candidate);
        if (record != nullptr && record->alive &&
            record->household != original.borrower) {
            heir = candidate;
            break;
        }
    }
    for (const auto candidate : harness.population_runtime.persons.alive_ids()) {
        if (heir.valid()) {
            break;
        }
        const auto *record = harness.population_runtime.persons.get(candidate);
        if (candidate != deceased && record->household != original.borrower) {
            heir = candidate;
            break;
        }
    }
    assert(heir.valid());
    if (deceased_record->mother != heir && deceased_record->father != heir) {
        assert(!deceased_record->mother.valid());
        assert(!deceased_record->father.valid());
        deceased_record->mother = heir;
        assert(harness.population_runtime.relationships
                   .register_birth(harness.population_runtime.persons, deceased)
                   .ok());
    }
    const auto heir_household = harness.population_runtime.persons.get(heir)->household;
    harness.runtime.housing_rules.market_interval_days = 30U;
    M8AdvanceOptions options;
    options.base.force_death = deceased;
    result =
        advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                         harness.monetary_runtime, harness.monetary_scratch,
                         harness.financial_runtime, harness.financial_scratch,
                         harness.population_runtime, harness.population_scratch,
                         harness.runtime, harness.scratch, harness.tick, 1U, options);
    if (!result.ok()) {
        std::cerr << "mortgage estate transfer failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    const auto &inherited = harness.runtime.mortgages.front();
    assert(inherited.active);
    assert(inherited.borrower == heir_household);
    const auto *dwelling = harness.runtime.properties.get(inherited.collateral);
    assert(dwelling != nullptr);
    assert(dwelling->owner == macro_sim::core::OwnerId::household(heir_household));
    const auto &loan =
        harness.root.loans
            .records()[static_cast<std::size_t>(inherited.loan.value() - 1U)];
    assert(loan.active);
    assert(loan.borrower == macro_sim::core::OwnerId::household(heir_household));
    assert(validate_m8_state(harness.root, harness.real_runtime,
                             harness.monetary_runtime, harness.financial_runtime,
                             harness.population_runtime, harness.runtime, harness.tick)
               .ok());
}

void test_mortgaged_resale_discharge_precedes_new_collateral() {
    auto harness = build(market_spec(true, false));
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(!harness.runtime.mortgages.empty());
    const auto original = harness.runtime.mortgages.front();
    const auto *original_dwelling = harness.runtime.properties.get(original.collateral);
    assert(original_dwelling != nullptr);
    assert(original_dwelling->owner ==
           macro_sim::core::OwnerId::household(original.borrower));

    macro_sim::HouseholdId buyer{};
    harness.root.households.for_each_alive(
        [&](macro_sim::HouseholdId candidate,
            const macro_sim::core::HouseholdComponent &) {
            if (!buyer.valid() && candidate != original.borrower) {
                const auto occupied =
                    harness.runtime.properties.dwelling_for_occupant(candidate);
                const auto *record = harness.runtime.properties.get(occupied);
                if (record != nullptr && occupied != original.collateral &&
                    !record->collateral.valid() &&
                    record->owner == macro_sim::core::OwnerId::household(candidate)) {
                    assert(
                        harness.runtime.properties
                            .set_occupant(occupied, candidate, macro_sim::HouseholdId{})
                            .ok());
                    assert(harness.runtime.properties
                               .destroy(occupied,
                                        macro_sim::core::OwnerId::household(candidate),
                                        harness.tick)
                               .ok());
                    buyer = candidate;
                }
            }
        });
    assert(buyer.valid());
    for (auto &listing : harness.runtime.housing_listings) {
        listing.active = false;
    }
    harness.runtime.housing_listings.push_back({
        original.collateral,
        macro_sim::core::OwnerId::household(original.borrower),
        original.purchase_price,
        harness.tick,
        false,
        true,
    });

    result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "mortgaged resale failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    const auto &repaid =
        harness.root.loans
            .records()[static_cast<std::size_t>(original.loan.value() - 1U)];
    assert(!repaid.active);
    assert(repaid.principal.value() == 0.0);
    assert(!harness.runtime.mortgages.front().active);
    const auto *sold = harness.runtime.properties.get(original.collateral);
    assert(sold != nullptr);
    assert(sold->owner == macro_sim::core::OwnerId::household(buyer));
    assert(sold->collateral != original.loan);
    assert(harness.runtime.properties.dwelling_for_collateral(original.loan) ==
           macro_sim::DwellingId{});
    assert(harness.runtime.properties.validate().ok());
}

void test_rent_moves_cash_without_minting_money() {
    auto value = market_spec(false, true);
    value.housing_rules.market_interval_days = 30;
    auto harness = build(value);
    assert(!harness.runtime.tenancies.empty());
    const auto tenancy = harness.runtime.tenancies.front();
    const auto *tenant = harness.root.households.get(tenancy.tenant);
    const auto *landlord = harness.root.households.get(tenancy.landlord);
    assert(tenant != nullptr);
    assert(landlord != nullptr);
    const auto tenant_before =
        harness.root.postings.get(tenant->primary_account)->balance.value();
    const auto landlord_before =
        harness.root.postings.get(landlord->primary_account)->balance.value();
    const auto money_before = harness.root.genesis_money;
    const auto result = advance(harness, 1);
    assert(result.ok());
    const auto tenant_after =
        harness.root.postings.get(tenant->primary_account)->balance.value();
    const auto landlord_after =
        harness.root.postings.get(landlord->primary_account)->balance.value();
    const double paid = result.get_if()->metrics.housing.rent_paid;
    assert(paid > 0.0);
    assert(tenant_after < tenant_before);
    assert(landlord_after > landlord_before);
    assert(harness.root.genesis_money == money_before);
}

void test_housing_enters_the_integrated_net_wealth_tax_base_once() {
    auto excluded_spec = market_spec(false, false);
    excluded_spec.housing_rules.resale_market = false;
    excluded_spec.housing_policy.transfer_tax_rate = 0.0;
    excluded_spec.housing_policy.property_tax_rate = 0.0;
    excluded_spec.housing_policy.include_housing_in_wealth_tax = false;
    auto &excluded_fiscal =
        excluded_spec.domestic_economy.financial_economy.monetary_economy.policy;
    excluded_fiscal.wealth_tax_rate = 0.01;
    excluded_fiscal.wealth_allowance = 0.0;
    auto included_spec = excluded_spec;
    included_spec.housing_policy.include_housing_in_wealth_tax = true;
    auto excluded = build(excluded_spec);
    auto included = build(included_spec);
    const double house_price = included.runtime.house_price;
    std::vector<double> housing_value(included.real_scratch.household_ids_.size(), 0.0);
    for (const auto &dwelling : included.runtime.properties.records()) {
        if (!dwelling.active ||
            dwelling.owner.kind() != macro_sim::core::OwnerKind::household) {
            continue;
        }
        const auto identity = static_cast<std::size_t>(dwelling.owner.value());
        assert(identity < included.real_scratch.household_dense_index_.size());
        const auto index = included.real_scratch.household_dense_index_[identity];
        assert(index < housing_value.size());
        housing_value[index] += house_price;
    }
    const auto excluded_result = advance(excluded, 1);
    const auto included_result = advance(included, 1);
    assert(excluded_result.ok());
    assert(included_result.ok());
    assert(excluded.real_scratch.household_net_wealth_.size() ==
           included.real_scratch.household_net_wealth_.size());
    double total_housing = 0.0;
    for (std::size_t index = 0; index < housing_value.size(); ++index) {
        const double difference = included.real_scratch.household_net_wealth_[index] -
                                  excluded.real_scratch.household_net_wealth_[index];
        assert(std::abs(difference - housing_value[index]) < 1.0e-7);
        total_housing += housing_value[index];
    }
    assert(total_housing > 0.0);
    assert(std::abs(excluded_result.get_if()
                        ->metrics.housing.housing_wealth_tax_base_included) < 1.0e-12);
    assert(
        std::abs(
            included_result.get_if()->metrics.housing.housing_wealth_tax_base_included -
            total_housing) < 1.0e-7);
    assert(included_result.get_if()->metrics.economy.economy.economy.economy.tax_total >
           excluded_result.get_if()->metrics.economy.economy.economy.economy.tax_total);
}

void test_vacant_rental_is_not_forced_into_resale_market() {
    auto value = market_spec(false, true);
    value.housing_rules.market_interval_days = 1;
    auto harness = build(value);
    assert(!harness.runtime.tenancies.empty());
    auto &former_tenancy = harness.runtime.tenancies.front();
    const auto tenant = former_tenancy.tenant;
    const auto dwelling = former_tenancy.dwelling;
    former_tenancy.active = false;
    former_tenancy.ended_tick = harness.tick;
    assert(harness.runtime.properties
               .set_occupant(dwelling, tenant, macro_sim::HouseholdId{})
               .ok());

    const auto result = advance(harness, 1);
    assert(result.ok());
    const auto *record = harness.runtime.properties.get(dwelling);
    assert(record != nullptr);
    assert(record->occupant == tenant);
    assert(std::any_of(harness.runtime.tenancies.begin(),
                       harness.runtime.tenancies.end(),
                       [tenant, dwelling](const TenancyRecord &tenancy) {
                           return tenancy.active && tenancy.tenant == tenant &&
                                  tenancy.dwelling == dwelling;
                       }));
    assert(std::none_of(harness.runtime.housing_listings.begin(),
                        harness.runtime.housing_listings.end(),
                        [dwelling](const HousingListing &listing) {
                            return listing.active && listing.dwelling == dwelling;
                        }));
}

void test_rent_declines_when_rental_vacancy_exceeds_deadband() {
    auto value = market_spec(false, true);
    value.housing_rules.market_interval_days = 1;
    value.housing_rules.initial_dwellings_per_household = 1.5;
    value.housing_rules.rental_vacancy_deadband = 0.0;
    value.housing_rules.rent_adjustment = 0.10;
    auto harness = build(value);
    const double opening_rent = harness.runtime.rent_level;

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(harness.runtime.rent_level < opening_rent);
    for (const auto &tenancy : harness.runtime.tenancies) {
        if (tenancy.active) {
            assert(std::abs(tenancy.daily_rent - harness.runtime.rent_level) < 1.0e-12);
        }
    }
}

void test_failed_bids_do_not_raise_house_price() {
    auto value = market_spec(false, false);
    value.housing_rules.market_interval_days = 1;
    value.housing_rules.house_price_income_years = 100.0;
    value.housing_rules.demand_price_step = 0.10;
    auto harness = build(value);
    const double opening_price = harness.runtime.house_price;

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.housing.session_sales == 0.0);
    assert(std::abs(harness.runtime.house_price - opening_price) < 1.0e-12);
}

void test_forced_sale_does_not_rebase_house_price_index() {
    auto value = market_spec(true, true);
    value.housing_rules.market_interval_days = 1;
    auto harness = build(value);
    const double opening_price = harness.runtime.house_price;

    macro_sim::DwellingId listing_dwelling{};
    macro_sim::HouseholdId seller{};
    for (const auto &candidate : harness.runtime.properties.records()) {
        if (candidate.active &&
            candidate.owner.kind() == macro_sim::core::OwnerKind::household &&
            candidate.occupant == macro_sim::HouseholdId(candidate.owner.value())) {
            listing_dwelling = candidate.id;
            seller = macro_sim::HouseholdId(candidate.owner.value());
            break;
        }
    }
    assert(listing_dwelling.valid());
    assert(harness.runtime.properties
               .set_occupant(listing_dwelling, seller, macro_sim::HouseholdId{})
               .ok());
    harness.runtime.housing_listings.push_back({
        listing_dwelling,
        macro_sim::core::OwnerId::household(seller),
        1.0,
        harness.tick,
        true,
        true,
    });

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.housing.session_sales == 1.0);
    assert(std::abs(harness.runtime.house_price - opening_price) < 1.0e-12);
}

void test_tenant_can_buy_and_end_previous_tenancy() {
    auto value = market_spec(true, true);
    value.housing_rules.market_interval_days = 1;
    auto harness = build(value);
    assert(!harness.runtime.tenancies.empty());
    const auto original_tenancies = harness.runtime.tenancies;

    macro_sim::DwellingId listing_dwelling{};
    macro_sim::HouseholdId seller{};
    for (const auto &candidate : harness.runtime.properties.records()) {
        if (candidate.active &&
            candidate.owner.kind() == macro_sim::core::OwnerKind::household &&
            candidate.occupant == macro_sim::HouseholdId(candidate.owner.value())) {
            listing_dwelling = candidate.id;
            seller = macro_sim::HouseholdId(candidate.owner.value());
            break;
        }
    }
    assert(listing_dwelling.valid());
    assert(harness.runtime.properties
               .set_occupant(listing_dwelling, seller, macro_sim::HouseholdId{})
               .ok());
    harness.runtime.housing_listings.push_back({
        listing_dwelling,
        macro_sim::core::OwnerId::household(seller),
        1.0,
        harness.tick,
        false,
        true,
    });

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(result.get_if()->metrics.housing.session_sales == 1.0);
    const auto *sold = harness.runtime.properties.get(listing_dwelling);
    assert(sold != nullptr);
    assert(sold->owner.kind() == macro_sim::core::OwnerKind::household);
    const auto buyer = macro_sim::HouseholdId(sold->owner.value());
    const auto previous =
        std::find_if(original_tenancies.begin(), original_tenancies.end(),
                     [buyer](const TenancyRecord &tenancy) {
                         return tenancy.active && tenancy.tenant == buyer;
                     });
    assert(previous != original_tenancies.end());
    assert(sold->occupant == buyer);
    const auto ended =
        std::find_if(harness.runtime.tenancies.begin(), harness.runtime.tenancies.end(),
                     [previous](const TenancyRecord &tenancy) {
                         return tenancy.id == previous->id;
                     });
    assert(ended != harness.runtime.tenancies.end());
    assert(!ended->active);
    assert(ended->ended_tick == Tick(0));
    const auto *former_home = harness.runtime.properties.get(previous->dwelling);
    assert(former_home != nullptr);
    assert(!former_home->occupant.valid());
}

void test_price_shock_forecloses_into_bank_title() {
    auto harness = build(market_spec(true, false));
    auto result = advance(harness, 1);
    assert(result.ok());
    assert(!harness.runtime.mortgages.empty());
    const auto mortgage = harness.runtime.mortgages.front();
    const auto loss_before =
        harness.monetary_runtime.last_metrics.realized_credit_losses;
    harness.runtime.housing_rules.market_interval_days = 30;
    harness.runtime.housing_input.house_price_reference_multiplier = 0.1;
    result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "mortgage foreclosure failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    const auto &closed = harness.runtime.mortgages.front();
    assert(!closed.active);
    assert(closed.foreclosed);
    const auto *dwelling = harness.runtime.properties.get(mortgage.collateral);
    assert(dwelling != nullptr);
    assert(dwelling->owner == macro_sim::core::OwnerId::bank(mortgage.lender));
    assert(!dwelling->collateral.valid());
    assert(!dwelling->occupant.valid());
    assert(result.get_if()->metrics.housing.foreclosures >= 1.0);
    assert(harness.monetary_runtime.last_metrics.realized_credit_losses > loss_before);
}

void test_mortgage_arrears_floor_has_dose_and_withdrawal_contract() {
    const auto run_with_floor = [](double floor) {
        auto harness = build(market_spec(true, false));
        auto result = advance(harness, 1);
        assert(result.ok());
        assert(!harness.runtime.mortgages.empty());
        harness.runtime.housing_rules.market_interval_days = 30;
        harness.runtime.housing_policy.mortgage_arrears_floor = floor;
        harness.runtime.housing_input.house_price_reference_multiplier = 0.1;
        result = advance(harness, 1);
        assert(result.ok());
        return result.get_if()->metrics.housing;
    };

    const auto protected_households = run_with_floor(0.0);
    const auto binding = run_with_floor(100.0);
    const auto withdrawn = run_with_floor(0.0);
    assert(protected_households.mortgage_arrears_floor_applied == 0.0);
    assert(binding.mortgage_arrears_floor_applied == 100.0);
    assert(protected_households.mortgage_foreclosure_candidates > 0.0);
    assert(binding.mortgage_foreclosure_candidates > 0.0);
    assert(protected_households.mortgage_foreclosures_prevented_by_liquidity >
           binding.mortgage_foreclosures_prevented_by_liquidity);
    assert(binding.foreclosures > protected_households.foreclosures);
    assert(withdrawn.mortgage_foreclosures_prevented_by_liquidity ==
           protected_households.mortgage_foreclosures_prevented_by_liquidity);
    assert(withdrawn.foreclosures == protected_households.foreclosures);
}

void test_homeless_owner_does_not_buy_own_listing() {
    auto spec = market_spec(false, false);
    spec.housing_rules.ask_floor_annual_wage_share = 0.0;
    spec.housing_rules.buyer_search_count = 1U;
    auto harness = build(spec);

    macro_sim::HouseholdId owner{};
    macro_sim::DwellingId dwelling{};
    for (const auto &candidate : harness.runtime.properties.records()) {
        if (candidate.active &&
            candidate.owner.kind() == macro_sim::core::OwnerKind::household &&
            candidate.occupant == macro_sim::HouseholdId(candidate.owner.value())) {
            owner = macro_sim::HouseholdId(candidate.owner.value());
            dwelling = candidate.id;
            break;
        }
    }
    assert(owner.valid());
    assert(dwelling.valid());
    assert(harness.runtime.properties
               .set_occupant(dwelling, owner, macro_sim::HouseholdId{})
               .ok());
    harness.root.households.for_each_alive(
        [&](macro_sim::HouseholdId household,
            const macro_sim::core::HouseholdComponent &) {
            if (household == owner ||
                harness.runtime.properties.dwelling_for_occupant(household).valid()) {
                return;
            }
            for (const auto &candidate : harness.runtime.properties.records()) {
                if (!candidate.active || candidate.id == dwelling ||
                    candidate.occupant.valid()) {
                    continue;
                }
                assert(
                    harness.runtime.properties
                        .set_occupant(candidate.id, macro_sim::HouseholdId{}, household)
                        .ok());
                assert(
                    harness.runtime.properties
                        .transfer_title(candidate.id, candidate.owner,
                                        macro_sim::core::OwnerId::household(household),
                                        harness.tick)
                        .ok());
                return;
            }
            assert(false);
        });
    for (auto &listing : harness.runtime.housing_listings) {
        listing.active = false;
    }
    harness.runtime.housing_listings.push_back({
        dwelling,
        macro_sim::core::OwnerId::household(owner),
        1.0e-6,
        harness.tick,
        false,
        true,
    });

    const auto result = advance(harness, 1);
    if (!result.ok()) {
        std::cerr << "self-owned listing exclusion failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    const auto *record = harness.runtime.properties.get(dwelling);
    assert(record != nullptr);
    assert(record->owner == macro_sim::core::OwnerId::household(owner));
    assert(harness.runtime.properties.validate().ok());
}

void test_broader_housing_search_changes_the_observed_opportunity_set() {
    auto narrow_spec = market_spec(true, false);
    narrow_spec.housing_rules.initial_dwellings_per_household = 2.0;
    narrow_spec.housing_rules.initial_homeownership_share = 0.2;
    narrow_spec.housing_rules.buyer_search_count = 1U;
    auto broad_spec = narrow_spec;
    broad_spec.housing_rules.buyer_search_count = 8U;
    auto narrow = build(narrow_spec);
    auto broad = build(broad_spec);

    const auto seed_heterogeneous_listings = [](Harness &harness) {
        harness.runtime.housing_listings.clear();
        for (const auto &dwelling : harness.runtime.properties.records()) {
            if (!dwelling.active || dwelling.occupant.valid()) {
                continue;
            }
            const double relative_ask =
                0.75 + 0.05 * static_cast<double>(dwelling.id.value() % 7U);
            harness.runtime.housing_listings.push_back({
                dwelling.id,
                dwelling.owner,
                harness.runtime.house_price * relative_ask,
                harness.tick,
                false,
                true,
            });
        }
        assert(harness.runtime.housing_listings.size() > 8U);
    };
    seed_heterogeneous_listings(narrow);
    seed_heterogeneous_listings(broad);

    const auto narrow_result = advance(narrow, 1);
    const auto broad_result = advance(broad, 1);
    assert(narrow_result.ok());
    assert(broad_result.ok());
    assert(narrow_result.get_if()->metrics.housing.session_sales > 0.0);
    assert(broad_result.get_if()->metrics.housing.session_sales > 0.0);
    assert(std::abs(narrow_result.get_if()->metrics.housing.session_volume -
                    broad_result.get_if()->metrics.housing.session_volume) > 1.0e-9);
}

void test_housing_wealth_effect_adds_owner_consumption_budget() {
    auto neutral_spec = market_spec(false, false);
    neutral_spec.housing_rules.resale_market = false;
    neutral_spec.housing_rules.wealth_effect = 0.0;
    auto treatment_spec = neutral_spec;
    treatment_spec.housing_rules.wealth_effect = 0.10;
    auto neutral = build(neutral_spec);
    auto treatment = build(treatment_spec);

    const auto neutral_result = advance(neutral, 1);
    const auto treatment_result = advance(treatment, 1);
    assert(neutral_result.ok());
    assert(treatment_result.ok());
    const auto total_budget = [](const Harness &harness) {
        double total = 0.0;
        for (const auto &household : harness.real_scratch.household_work_) {
            total += household.consumption_budget;
        }
        return total;
    };
    assert(total_budget(treatment) > total_budget(neutral));
    assert(treatment_result.get_if()
               ->metrics.economy.economy.economy.economy.household_consumption >
           neutral_result.get_if()
               ->metrics.economy.economy.economy.economy.household_consumption);
}

void test_failed_market_tick_is_atomic() {
    auto harness = build(market_spec(false, false));
    const auto root = base_checkpoint(harness);
    const auto housing = harness.runtime;
    const auto tick = harness.tick;
    M8AdvanceOptions options;
    options.fault_point = M8FaultPoint::before_commit;
    const auto result =
        advance_m8_ticks(harness.root, harness.real_runtime, harness.real_scratch,
                         harness.monetary_runtime, harness.monetary_scratch,
                         harness.financial_runtime, harness.financial_scratch,
                         harness.population_runtime, harness.population_scratch,
                         harness.runtime, harness.scratch, harness.tick, 1, options);
    assert(!result.ok());
    assert(base_checkpoint(harness) == root);
    assert(harness.runtime == housing);
    assert(harness.tick == tick);
}

} // namespace

int main() {
    test_cash_resale_moves_money_title_and_occupancy();
    test_mortgage_origination_is_canonical_and_collateralized();
    test_mortgage_capital_rules_have_dose_and_withdrawal_contract();
    test_mortgage_follows_heir_when_borrower_household_retires();
    test_mortgaged_resale_discharge_precedes_new_collateral();
    test_rent_moves_cash_without_minting_money();
    test_housing_enters_the_integrated_net_wealth_tax_base_once();
    test_vacant_rental_is_not_forced_into_resale_market();
    test_rent_declines_when_rental_vacancy_exceeds_deadband();
    test_failed_bids_do_not_raise_house_price();
    test_forced_sale_does_not_rebase_house_price_index();
    test_tenant_can_buy_and_end_previous_tenancy();
    test_price_shock_forecloses_into_bank_title();
    test_mortgage_arrears_floor_has_dose_and_withdrawal_contract();
    test_homeless_owner_does_not_buy_own_listing();
    test_broader_housing_search_changes_the_observed_opportunity_set();
    test_housing_wealth_effect_adds_owner_consumption_budget();
    test_failed_market_tick_is_atomic();
    return 0;
}
