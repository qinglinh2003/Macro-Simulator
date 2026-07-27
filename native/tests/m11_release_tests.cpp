#include <algorithm>
#include <cassert>
#include <cstdint>
#include <string_view>
#include <utility>

#include "macro_sim/control/m10.hpp"
#include "macro_sim/control/m11_release.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::simulation;

[[nodiscard]] M9World build_world() {
    M8SimulationSpec economy;
    auto &population = economy.domestic_economy;
    auto &monetary = population.financial_economy.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 8U;
    real.consumption_firms = 2U;
    real.capital_firms = 1U;
    real.seed = 4201U;
    real.requested_capabilities = capability_bit(M4Capability::physical_capital) |
                                  capability_bit(M4Capability::government);
    monetary.rules.bank_count = 2U;
    monetary.rules.opening_capital_per_bank = 100.0;
    population.financial_economy.rules.entry_beta = 0.0;
    population.financial_economy.rules.bank_entry_beta = 0.0;
    population.population.initial_persons = 16U;
    population.rules.fertility = false;
    population.rules.mortality = false;
    population.rules.marriage = false;
    population.rules.divorce = false;
    economy.energy_rules.producer_count = 1U;
    economy.housing_rules.enabled = false;
    M9WorldSpec spec;
    spec.economies.push_back(std::move(economy));
    spec.external_policies.resize(1U);
    auto result = M9World::create(spec);
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] bool has_series(const std::vector<M11ReleasedObservation> &values,
                              std::string_view series) {
    return std::any_of(values.begin(), values.end(),
                       [series](const M11ReleasedObservation &value) {
                           return value.series_id == series;
                       });
}

void test_contract_and_access() {
    const auto fields = m11_observation_fields();
    assert(fields.size() == 42U);
    assert(kM11ObservationContractSha256 ==
           "324327db4fa0fa2e6dcdd4eb2f4c4dbc345dd7f51d0a8b65588d04928c7d4447");
    for (std::size_t index = 0U; index < fields.size(); ++index) {
        assert(find_m11_observation_field(fields[index].series_id) == &fields[index]);
        if (index > 0U) {
            assert(fields[index - 1U].series_id < fields[index].series_id);
        }
    }
    const auto *reserves = find_m11_observation_field("bank_reserves_total");
    assert(reserves != nullptr);
    assert(!m11_release_permitted(*reserves, "treasury"));
    assert(m11_release_permitted(*reserves, "central_bank"));
    assert(m11_release_permitted(*reserves, "regulator"));
    const auto *oracle = find_m11_observation_field("oracle_daily_output");
    assert(oracle != nullptr);
    assert(!m11_release_permitted(*oracle, "treasury"));
    assert(m11_release_permitted(*oracle, "oracle"));
}

void test_cadence_lag_aggregation_and_role_filter() {
    auto engine_result = EngineSession::create(build_world(), 64U);
    assert(engine_result.ok());
    auto engine = std::move(*engine_result.get_if());
    M11ReleaseService service;
    M11ReleaseStream stream(1024U);
    auto initial = service.publish_due(engine.metrics(), engine.world(), engine.tick(),
                                       0U, stream);
    assert(initial.ok());
    assert(*initial.get_if() > 0U);
    const auto count = stream.releases().size();
    auto duplicate = service.publish_due(engine.metrics(), engine.world(),
                                         engine.tick(), 0U, stream);
    assert(duplicate.ok());
    assert(*duplicate.get_if() == 0U);
    assert(stream.releases().size() == count);

    auto advanced = engine.advance_ticks(1U);
    assert(advanced.ok());
    auto first_day = service.publish_due(engine.metrics(), engine.world(),
                                         engine.tick(), 1U, stream);
    assert(first_day.ok());
    auto public_values =
        service.observation(stream, EconomyId(0U), Tick(1U), "treasury");
    auto central_bank_values =
        service.observation(stream, EconomyId(0U), Tick(1U), "central_bank");
    auto oracle_values = service.observation(stream, EconomyId(0U), Tick(1U), "oracle");
    assert(public_values.ok() && central_bank_values.ok() && oracle_values.ok());
    assert(!has_series(*public_values.get_if(), "bank_reserves_total"));
    assert(has_series(*central_bank_values.get_if(), "bank_reserves_total"));
    assert(!has_series(*public_values.get_if(), "oracle_daily_output"));
    assert(has_series(*oracle_values.get_if(), "oracle_daily_output"));

    for (std::uint64_t day = 2U; day <= 9U; ++day) {
        auto next = engine.advance_ticks(1U);
        assert(next.ok());
        auto published = service.publish_due(engine.metrics(), engine.world(),
                                             engine.tick(), day, stream);
        assert(published.ok());
    }
    auto released = service.observation(stream, EconomyId(0U), Tick(9U), "treasury");
    assert(released.ok());
    assert(has_series(*released.get_if(), "price_index"));
    assert(has_series(*released.get_if(), "inflation"));
    assert(has_series(*released.get_if(), "unemployment_rate"));
    assert(!has_series(*released.get_if(), "real_output"));
    const auto price =
        std::find_if(released.get_if()->begin(), released.get_if()->end(),
                     [](const M11ReleasedObservation &value) {
                         return value.series_id == "price_index";
                     });
    assert(price != released.get_if()->end());
    assert(price->observed_at == Tick(6U));
    assert(price->released_at == Tick(9U));

    const auto samples = service.trigger_samples(stream, EconomyId(0U), Tick(9U));
    assert(samples.size() == 8U);
    assert(
        std::any_of(samples.begin(), samples.end(), [](const M11MetricSample &sample) {
            return sample.series_id == "shock_supply_severity" &&
                   sample.value.has_value();
        }));
}

} // namespace

int main() {
    test_contract_and_access();
    test_cadence_lag_aggregation_and_role_filter();
    return 0;
}
