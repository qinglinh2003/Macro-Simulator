#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/simulation/m8_checkpoint.hpp"

namespace {

using macro_sim::Tick;
using namespace macro_sim::simulation;

[[nodiscard]] M8SimulationSpec spec() {
    M8SimulationSpec value;
    auto &population = value.domestic_economy;
    auto &real = population.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 4;
    real.capital_firms = 2;
    real.seed = 8808;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    real.rules.initial_household_money = 80.0;
    real.rules.initial_firm_money = 30.0;
    real.rules.initial_consumption_inventory = 5.0;
    real.rules.initial_capital_inventory = 4.0;
    real.rules.initial_wage = 2.0;
    auto &monetary = population.financial_economy.monetary_economy;
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 1'000.0;
    monetary.rules.household_credit = true;
    monetary.rules.household_amortization = 0.0;
    monetary.policy.household_credit_limit = 1'000.0;
    population.population.initial_persons = 40;
    population.population.target_household_size = 2.0;
    population.population.start_calendar_day = 18'000;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    population.rules.annual_churn = 0.0;
    value.energy_rules.enabled = true;
    value.energy_rules.producer_count = 1;
    value.energy_rules.initial_producer_cash = 100.0;
    value.housing_rules.enabled = true;
    value.housing_rules.resale_market = true;
    value.housing_rules.mortgages = true;
    value.housing_rules.construction = true;
    value.housing_rules.house_price_income_years = 0.2;
    value.housing_rules.initial_homeownership_share = 0.5;
    value.housing_rules.market_interval_days = 1;
    value.housing_rules.voluntary_ask_markup = 0.0;
    value.housing_rules.ask_decay = 0.0;
    value.housing_rules.buyer_liquidity_buffer = 0.0;
    value.housing_rules.builder_count = 1;
    value.housing_rules.builder_productivity = 1.0;
    value.housing_rules.builder_demand_seed = 2.0;
    value.housing_rules.initial_builder_cash_buffer = 1'000.0;
    value.housing_policy.land_fee_share = 0.0;
    value.housing_policy.annual_housing_permits = 3;
    value.housing_policy.mortgage_ltv_cap = 0.8;
    value.housing_policy.mortgage_underwriting = false;
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

void reserve(Harness &value) {
    value.real_scratch.reserve(value.root);
    value.monetary_scratch.reserve(value.root);
    value.financial_scratch.reserve(value.root, value.financial_runtime);
    value.population_scratch.reserve(value.population_runtime);
    value.scratch.reserve(value.root, value.runtime);
}

[[nodiscard]] Harness build() {
    auto initialized = build_m8_genesis(spec());
    if (!initialized.ok()) {
        std::cerr << "M8 checkpoint genesis failed: " << initialized.status().message()
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
    reserve(result);
    return result;
}

[[nodiscard]] Harness restore(M8Checkpoint state) {
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
        state.tick,
    };
    reserve(result);
    return result;
}

[[nodiscard]] macro_sim::Result<M8AdvanceResult> advance(Harness &value,
                                                         std::uint64_t count) {
    return advance_m8_ticks(value.root, value.real_runtime, value.real_scratch,
                            value.monetary_runtime, value.monetary_scratch,
                            value.financial_runtime, value.financial_scratch,
                            value.population_runtime, value.population_scratch,
                            value.runtime, value.scratch, value.tick, count);
}

[[nodiscard]] macro_sim::core::StateDigest digest(const Harness &value) {
    auto result = m8_state_digest(value.root, value.real_runtime,
                                  value.monetary_runtime, value.financial_runtime,
                                  value.population_runtime, value.runtime, value.tick);
    assert(result.ok());
    return *result.get_if();
}

void test_round_trip_and_continuation_are_exact() {
    auto original = build();
    assert(advance(original, 20).ok());
    auto bytes = save_m8_checkpoint(
        original.root, original.real_runtime, original.monetary_runtime,
        original.financial_runtime, original.population_runtime, original.runtime,
        original.tick);
    assert(bytes.ok());
    assert(is_m8_checkpoint(*bytes.get_if()));
    const auto before = digest(original);
    auto loaded = load_m8_checkpoint(*bytes.get_if());
    if (!loaded.ok()) {
        std::cerr << "M8 checkpoint load failed: " << loaded.status().message() << "\n";
    }
    assert(loaded.ok());
    auto restored = restore(std::move(*loaded.get_if()));
    assert(restored.tick == original.tick);
    if (!(restored.runtime == original.runtime)) {
        const auto &left =
            restored.runtime.last_metrics.economy.economy.economy.economy;
        const auto &right =
            original.runtime.last_metrics.economy.economy.economy.economy;
        std::cerr
            << "M8 runtime mismatch:"
            << " producers="
            << (restored.runtime.energy_producers ==
                original.runtime.energy_producers)
            << " inputs="
            << (restored.runtime.energy_inputs == original.runtime.energy_inputs)
            << " household_energy="
            << (restored.runtime.household_energy ==
                original.runtime.household_energy)
            << " deprivation="
            << (restored.runtime.deprivation == original.runtime.deprivation)
            << " energy_metrics="
            << (restored.runtime.last_metrics.energy ==
                original.runtime.last_metrics.energy)
            << " housing_metrics="
            << (restored.runtime.last_metrics.housing ==
                original.runtime.last_metrics.housing)
            << " economy_metrics="
            << (restored.runtime.last_metrics.economy ==
                original.runtime.last_metrics.economy)
            << " m6_metrics="
            << (restored.runtime.last_metrics.economy.economy ==
                original.runtime.last_metrics.economy.economy)
            << " m5_metrics="
            << (restored.runtime.last_metrics.economy.economy.economy ==
                original.runtime.last_metrics.economy.economy.economy)
            << " m4_metrics="
            << (restored.runtime.last_metrics.economy.economy.economy.economy ==
                original.runtime.last_metrics.economy.economy.economy.economy)
            << " energy_policy="
            << (restored.runtime.energy_policy ==
                original.runtime.energy_policy)
            << " energy_rules="
            << (restored.runtime.energy_rules ==
                original.runtime.energy_rules)
            << " energy_input="
            << (restored.runtime.energy_input ==
                original.runtime.energy_input)
            << " housing_policy="
            << (restored.runtime.housing_policy ==
                original.runtime.housing_policy)
            << " housing_rules="
            << (restored.runtime.housing_rules ==
                original.runtime.housing_rules)
            << " housing_input="
            << (restored.runtime.housing_input ==
                original.runtime.housing_input)
            << " properties="
            << (restored.runtime.properties == original.runtime.properties)
            << " listings="
            << (restored.runtime.housing_listings ==
                original.runtime.housing_listings)
            << " mortgages="
            << (restored.runtime.mortgages == original.runtime.mortgages)
            << " tenancies="
            << (restored.runtime.tenancies == original.runtime.tenancies)
            << " builders="
            << (restored.runtime.builders == original.runtime.builders)
            << " affordability="
            << (restored.runtime.housing_affordability ==
                original.runtime.housing_affordability)
            << " scalars="
            << (restored.runtime.strategic_reserve_stock ==
                    original.runtime.strategic_reserve_stock &&
                restored.runtime.strategic_reserve_cost ==
                    original.runtime.strategic_reserve_cost &&
                restored.runtime.energy_price == original.runtime.energy_price &&
                restored.runtime.slow_energy_price ==
                    original.runtime.slow_energy_price &&
                restored.runtime.energy_event_counter ==
                    original.runtime.energy_event_counter &&
                restored.runtime.house_price == original.runtime.house_price &&
                restored.runtime.rent_level == original.runtime.rent_level &&
                restored.runtime.genesis_dwelling_count ==
                    original.runtime.genesis_dwelling_count &&
                restored.runtime.permit_year == original.runtime.permit_year &&
                restored.runtime.permits_used == original.runtime.permits_used &&
                restored.runtime.housing_event_counter ==
                    original.runtime.housing_event_counter)
            << "\n";
#define REPORT_M4_FIELD(name)                                                   \
    if (left.name != right.name) {                                              \
        std::cerr << "M4 metric mismatch " #name ": restored=" << left.name      \
                  << " original=" << right.name << "\n";                        \
    }
        REPORT_M4_FIELD(real_output)
        REPORT_M4_FIELD(nominal_output)
        REPORT_M4_FIELD(price_index)
        REPORT_M4_FIELD(unemployment_rate)
        REPORT_M4_FIELD(total_money)
        REPORT_M4_FIELD(conservation_drift)
        REPORT_M4_FIELD(aggregate_capital)
        REPORT_M4_FIELD(household_consumption)
        REPORT_M4_FIELD(wages_paid)
        REPORT_M4_FIELD(firm_profit)
        REPORT_M4_FIELD(dividends_paid)
        REPORT_M4_FIELD(tax_total)
        REPORT_M4_FIELD(government_spending)
        REPORT_M4_FIELD(government_deficit)
        REPORT_M4_FIELD(public_capital)
        REPORT_M4_FIELD(gross_output_nominal)
        REPORT_M4_FIELD(consumption_output_nominal)
        REPORT_M4_FIELD(capital_output_nominal)
        REPORT_M4_FIELD(consumption_output_real)
        REPORT_M4_FIELD(capital_output_real)
        REPORT_M4_FIELD(inventory_change_nominal)
        REPORT_M4_FIELD(inventory_change_real)
        REPORT_M4_FIELD(fixed_capital_formation_nominal)
        REPORT_M4_FIELD(fixed_capital_formation_real)
        REPORT_M4_FIELD(government_consumption)
        REPORT_M4_FIELD(public_fixed_capital_formation)
        REPORT_M4_FIELD(transfer_payments)
        REPORT_M4_FIELD(job_guarantee_spending)
        REPORT_M4_FIELD(job_guarantee_labor)
        REPORT_M4_FIELD(job_guarantee_public_capital_formation)
        REPORT_M4_FIELD(job_guarantee_realized_productivity)
#undef REPORT_M4_FIELD
    }
    assert(restored.runtime == original.runtime);
    assert(digest(restored) == before);
    assert(advance(original, 20).ok());
    assert(advance(restored, 20).ok());
    assert(digest(restored) == digest(original));
}

void test_checksum_and_payload_corruption_are_rejected() {
    auto value = build();
    assert(advance(value, 2).ok());
    auto bytes = save_m8_checkpoint(
        value.root, value.real_runtime, value.monetary_runtime, value.financial_runtime,
        value.population_runtime, value.runtime, value.tick);
    assert(bytes.ok());
    auto corrupted = *bytes.get_if();
    corrupted[corrupted.size() / 2U] ^= 0x5aU;
    assert(!load_m8_checkpoint(corrupted).ok());
    corrupted = *bytes.get_if();
    corrupted.resize(corrupted.size() - 1U);
    assert(!load_m8_checkpoint(corrupted).ok());
}

void test_serialization_is_deterministic() {
    auto value = build();
    assert(advance(value, 3).ok());
    const auto first = save_m8_checkpoint(
        value.root, value.real_runtime, value.monetary_runtime, value.financial_runtime,
        value.population_runtime, value.runtime, value.tick);
    const auto second = save_m8_checkpoint(
        value.root, value.real_runtime, value.monetary_runtime, value.financial_runtime,
        value.population_runtime, value.runtime, value.tick);
    assert(first.ok());
    assert(second.ok());
    assert(*first.get_if() == *second.get_if());
}

void test_engine_session_restores_and_continues_m8() {
    macro_sim::EngineSession first(8808);
    assert(first.initialize_m8(spec()).ok());
    assert(first.advance_m8_ticks(5).ok());
    auto bytes = first.checkpoint();
    auto before = first.digest();
    assert(bytes.ok());
    assert(before.ok());

    macro_sim::EngineSession second(8809);
    assert(second.restore_checkpoint(*bytes.get_if()).ok());
    assert(second.housing_runtime() != nullptr);
    auto restored = second.digest();
    assert(restored.ok());
    assert(*restored.get_if() == *before.get_if());
    assert(!second.advance_m7_ticks(1).ok());

    auto energy_policy = second.housing_runtime()->energy_policy;
    energy_policy.strategic_reserve_target += 1.0;
    assert(second.update_m8_energy_policy(energy_policy).ok());
    assert(first.update_m8_energy_policy(energy_policy).ok());
    assert(first.advance_m8_ticks(7).ok());
    assert(second.advance_m8_ticks(7).ok());
    auto first_digest = first.digest();
    auto second_digest = second.digest();
    assert(first_digest.ok());
    assert(second_digest.ok());
    assert(*first_digest.get_if() == *second_digest.get_if());
    assert(second.close().ok());
    assert(second.housing_runtime() == nullptr);
}

} // namespace

int main() {
    test_round_trip_and_continuation_are_exact();
    test_checksum_and_payload_corruption_are_rejected();
    test_serialization_is_deterministic();
    test_engine_session_restores_and_continues_m8();
    return 0;
}
