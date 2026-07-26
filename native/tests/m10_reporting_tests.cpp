#include <cassert>
#include <cstdint>
#include <iostream>
#include <utility>

#include "macro_sim/reporting/m10.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::simulation;
using namespace macro_sim::reporting;

[[nodiscard]] M9World build_world() {
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
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 24;
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

void test_descriptors_are_stable_and_complete() {
    const auto descriptors = public_metric_descriptors();
    assert(descriptors.size() == kM10PublicMetricCount);
    for (std::size_t index = 0; index < descriptors.size(); ++index) {
        assert(!descriptors[index].stable_id.empty());
        assert(!descriptors[index].unit.empty());
        assert(!descriptors[index].parity_rule.empty());
        assert(descriptors[index].cadence_ticks == 1U);
        for (std::size_t previous = 0; previous < index; ++previous) {
            assert(descriptors[previous].stable_id !=
                   descriptors[index].stable_id);
        }
    }
}

void test_frame_matches_native_sources() {
    auto world = build_world();
    assert(world.advance(1U).ok());
    auto frame = build_public_metric_frame(world);
    assert(frame.ok());
    assert(frame.get_if()->tick == world.tick());
    assert(frame.get_if()->economy_count == 1U);
    assert(frame.get_if()->values.size() == kM10PublicMetricCount);
    const auto output = frame.get_if()->value(0U, 14U);
    const auto price = frame.get_if()->value(0U, 13U);
    assert(output.ok());
    assert(price.ok());
    const auto &real =
        world.last_metrics().domestic[0].economy.economy.economy.economy;
    assert(*output.get_if() == real.real_output);
    assert(*price.get_if() == real.price_index);
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

} // namespace

int main() {
    test_descriptors_are_stable_and_complete();
    test_frame_matches_native_sources();
    test_history_is_bounded_and_cursor_checked();
    test_inflation_uses_only_previous_committed_frame();
    std::cout << "M10 reporting tests passed\n";
    return 0;
}
