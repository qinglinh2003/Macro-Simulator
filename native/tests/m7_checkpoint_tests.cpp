#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

#include "macro_sim/simulation/m7_checkpoint.hpp"

namespace {

using macro_sim::Tick;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M7SimulationSpec;
using macro_sim::simulation::capability_bit;

[[nodiscard]] M7SimulationSpec spec() {
    M7SimulationSpec value;
    auto &real =
        value.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 5;
    real.capital_firms = 2;
    real.seed = 79;
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
    auto &monetary = value.financial_economy.monetary_economy;
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
    value.financial_economy.policy.bank_minimum_capital = 20.0;
    value.financial_economy.policy.bond_maturity_days = 30;
    value.financial_economy.rules.bond_maturity_bucket = 5;
    value.financial_economy.rules.watchlist_size = 4;
    value.financial_economy.rules.entry_beta = 0.0;
    value.financial_economy.rules.bank_entry_beta = 0.0;
    value.population.initial_persons = 96;
    value.population.target_household_size = 2.4;
    value.population.start_calendar_day = 29;
    value.rules.annual_churn = 0.0;
    value.rules.fertility = false;
    value.rules.mortality = false;
    value.rules.marriage_interval_days = 30;
    value.rules.annual_marriage_rate = 1.0;
    value.rules.annual_divorce_rate = 0.0;
    return value;
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

[[nodiscard]] Harness build() {
    auto initialization =
        macro_sim::simulation::build_m7_genesis(spec());
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness result{
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
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(
        result.root, result.financial_runtime
    );
    result.scratch.reserve(result.runtime);
    return result;
}

[[nodiscard]] Harness restore(
    std::span<const std::uint8_t> bytes
) {
    auto checkpoint =
        macro_sim::simulation::load_m7_checkpoint(bytes);
    if (!checkpoint.ok()) {
        std::cerr << "M7 restore failed: "
                  << checkpoint.status().message() << "\n";
    }
    assert(checkpoint.ok());
    auto value = std::move(*checkpoint.get_if());
    Harness result{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.monetary_runtime),
        {},
        std::move(value.financial_runtime),
        {},
        std::move(value.runtime),
        {},
        value.tick,
    };
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(
        result.root, result.financial_runtime
    );
    result.scratch.reserve(result.runtime);
    return result;
}

void advance(Harness &value, std::uint64_t count) {
    const auto result = macro_sim::simulation::advance_m7_ticks(
        value.root, value.real_runtime, value.real_scratch,
        value.monetary_runtime, value.monetary_scratch,
        value.financial_runtime, value.financial_scratch,
        value.runtime, value.scratch, value.tick, count
    );
    if (!result.ok()) {
        std::cerr << "M7 advance failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
}

[[nodiscard]] std::vector<std::uint8_t>
save(const Harness &value) {
    const auto checkpoint =
        macro_sim::simulation::save_m7_checkpoint(
            value.root, value.real_runtime,
            value.monetary_runtime, value.financial_runtime,
            value.runtime, value.tick
        );
    assert(checkpoint.ok());
    return *checkpoint.get_if();
}

void test_round_trip_and_continuation() {
    auto direct = build();
    advance(direct, 12);
    const auto bytes = save(direct);
    assert(macro_sim::simulation::is_m7_checkpoint(bytes));
    auto resumed = restore(bytes);
    assert(save(resumed) == bytes);
    advance(direct, 15);
    advance(resumed, 15);
    const auto direct_bytes = save(direct);
    const auto resumed_bytes = save(resumed);
    assert(direct_bytes == resumed_bytes);
    const auto direct_digest =
        macro_sim::simulation::m7_state_digest(
            direct.root, direct.real_runtime,
            direct.monetary_runtime, direct.financial_runtime,
            direct.runtime, direct.tick
        );
    const auto resumed_digest =
        macro_sim::simulation::m7_state_digest(
            resumed.root, resumed.real_runtime,
            resumed.monetary_runtime, resumed.financial_runtime,
            resumed.runtime, resumed.tick
        );
    assert(direct_digest.ok());
    assert(resumed_digest.ok());
    assert(*direct_digest.get_if() == *resumed_digest.get_if());
}

void test_corruption_and_size_rejections() {
    auto value = build();
    advance(value, 2);
    auto bytes = save(value);
    auto corrupt = bytes;
    corrupt[corrupt.size() / 2U] ^= 0x5aU;
    assert(
        !macro_sim::simulation::load_m7_checkpoint(corrupt).ok()
    );
    auto truncated = bytes;
    truncated.pop_back();
    assert(
        !macro_sim::simulation::load_m7_checkpoint(truncated).ok()
    );
    bytes.push_back(0);
    assert(
        !macro_sim::simulation::load_m7_checkpoint(bytes).ok()
    );
}

} // namespace

int main() {
    test_round_trip_and_continuation();
    test_corruption_and_size_rejections();
    return 0;
}
