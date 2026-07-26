#include <cassert>
#include <cstdint>
#include <iostream>
#include <utility>

#include "macro_sim/simulation/m9.hpp"

namespace {

using namespace macro_sim;
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
    value.housing_rules.enabled = false;
    return value;
}

[[nodiscard]] M9World build_world() {
    M9WorldSpec spec;
    spec.economies.push_back(domestic_spec(101U));
    spec.economies.push_back(domestic_spec(102U));
    spec.external_policies.resize(2);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] WorldPolicyBatch policy_batch(const M9World &world) {
    WorldPolicyBatch batch;
    batch.expected_tick = world.tick();
    batch.expected_generation = world.policy_generation();
    batch.external = world.external_policies();
    for (std::size_t index = 0; index < world.economy_count(); ++index) {
        auto policy =
            world.domestic_policy(EconomyId(static_cast<std::uint64_t>(index)));
        assert(policy.ok());
        batch.domestic.push_back(*policy.get_if());
    }
    return batch;
}

void test_complete_policy_batch_commits_once() {
    auto world = build_world();
    auto batch = policy_batch(world);
    batch.domestic[0].fiscal_monetary.income_tax_rate = 0.42;
    batch.domestic[0].fiscal_monetary.monetary_regime =
        MonetaryRegime::manual;
    batch.domestic[0].fiscal_monetary.manual_policy_rate = 0.03;
    batch.domestic[0].fiscal_monetary.necessity_consumption_tax_rate = 0.04;
    batch.domestic[0].fiscal_monetary.luxury_consumption_tax_rate = 0.28;
    batch.domestic[0].fiscal_monetary.core_inflation_sensor = true;
    batch.domestic[0].fiscal_monetary.fixed_basket_cpi = true;
    batch.domestic[0].fiscal_monetary.logarithmic_inflation = true;
    batch.domestic[0]
        .fiscal_monetary.fiscal_uses_national_accounts_gdp = true;
    batch.domestic[1].financial.margin_ltv = 0.25;
    batch.domestic[1].financial.bankrupt_persistence = 31;
    batch.domestic[1].financial.regulatory_capital_haircut = 0.41;
    batch.domestic[1].financial.regulatory_inventory_haircut = 0.62;
    batch.domestic[1].population.inheritance_tax_rate = 0.12;
    batch.domestic[1].population.pension_replacement = 0.55;
    batch.domestic[0].energy.excise_rate = 0.15;
    batch.domestic[0].energy.windfall_tax_rate = 0.37;
    batch.domestic[0].energy.state_owned_first_producer = true;
    batch.domestic[1].housing.property_tax_rate = 0.01;
    batch.domestic[1].housing.include_housing_in_wealth_tax = true;
    batch.domestic[1].fiscal_monetary.wealth_tax_rate = 0.02;
    batch.external[0].tariff = 0.2;

    assert(world.update_policy_batch(batch).ok());
    assert(world.policy_generation() == 1U);
    const auto first = world.domestic_policy(EconomyId(0));
    const auto second = world.domestic_policy(EconomyId(1));
    assert(first.ok());
    assert(second.ok());
    assert(first.get_if()->fiscal_monetary.income_tax_rate == 0.42);
    assert(first.get_if()->fiscal_monetary.manual_policy_rate == 0.03);
    assert(first.get_if()
               ->fiscal_monetary.necessity_consumption_tax_rate == 0.04);
    assert(first.get_if()
               ->fiscal_monetary.luxury_consumption_tax_rate == 0.28);
    assert(first.get_if()->fiscal_monetary.core_inflation_sensor);
    assert(first.get_if()->fiscal_monetary.fixed_basket_cpi);
    assert(first.get_if()->fiscal_monetary.logarithmic_inflation);
    assert(first.get_if()
               ->fiscal_monetary.fiscal_uses_national_accounts_gdp);
    assert(second.get_if()->financial.margin_ltv == 0.25);
    assert(second.get_if()->financial.bankrupt_persistence == 31);
    assert(second.get_if()->financial.regulatory_capital_haircut == 0.41);
    assert(second.get_if()->financial.regulatory_inventory_haircut == 0.62);
    assert(second.get_if()->population.inheritance_tax_rate == 0.12);
    assert(second.get_if()->population.pension_replacement == 0.55);
    assert(first.get_if()->energy.excise_rate == 0.15);
    assert(first.get_if()->energy.windfall_tax_rate == 0.37);
    assert(first.get_if()->energy.state_owned_first_producer);
    assert(second.get_if()->housing.property_tax_rate == 0.01);
    assert(second.get_if()->housing.include_housing_in_wealth_tax);
    assert(second.get_if()->housing.wealth_tax_rate == 0.02);
    assert(world.external_policies()[0].tariff == 0.2);
}

void test_no_op_policy_batch_preserves_generation() {
    auto world = build_world();
    auto batch = policy_batch(world);
    assert(world.update_policy_batch(batch).ok());
    assert(world.policy_generation() == 0U);
}

void test_invalid_member_rolls_back_complete_batch() {
    auto world = build_world();
    const auto opening = world.checkpoint();
    assert(opening.ok());
    auto batch = policy_batch(world);
    batch.domestic[0].fiscal_monetary.income_tax_rate = 0.42;
    batch.domestic[1].fiscal_monetary.monetary_regime =
        MonetaryRegime::manual;
    batch.domestic[1].fiscal_monetary.manual_policy_rate.reset();
    batch.external[0].tariff = 0.2;

    const auto status = world.update_policy_batch(batch);
    assert(!status.ok());
    assert(world.policy_generation() == 0U);
    const auto closing = world.checkpoint();
    assert(closing.ok());
    assert(*opening.get_if() == *closing.get_if());
}

void test_stale_tick_and_generation_reject() {
    auto world = build_world();
    auto batch = policy_batch(world);
    batch.domestic[0].fiscal_monetary.income_tax_rate = 0.30;
    assert(world.update_policy_batch(batch).ok());
    assert(world.update_policy_batch(batch).code() == ErrorCode::stale_handle);

    auto tick_stale = policy_batch(world);
    assert(world.advance(1U).ok());
    assert(world.update_policy_batch(tick_stale).code() == ErrorCode::stale_handle);
}

void test_checkpoint_preserves_policy_generation() {
    auto world = build_world();
    auto batch = policy_batch(world);
    batch.domestic[0].fiscal_monetary.consumption_tax_rate = 0.21;
    assert(world.update_policy_batch(batch).ok());
    const auto bytes = world.checkpoint();
    assert(bytes.ok());
    auto restored = M9World::restore(*bytes.get_if());
    assert(restored.ok());
    assert(restored.get_if()->policy_generation() == 1U);
    const auto restored_policy =
        restored.get_if()->domestic_policy(EconomyId(0));
    assert(restored_policy.ok());
    assert(restored_policy.get_if()->fiscal_monetary.consumption_tax_rate ==
           0.21);
    assert(restored.get_if()->digest() == world.digest());
}

} // namespace

int main() {
    test_complete_policy_batch_commits_once();
    test_no_op_policy_batch_preserves_generation();
    test_invalid_member_rolls_back_complete_batch();
    test_stale_tick_and_generation_reject();
    test_checkpoint_preserves_policy_generation();
    std::cout << "M10 policy tests passed\n";
    return 0;
}
