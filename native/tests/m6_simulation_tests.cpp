#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m6.hpp"
#include "macro_sim/simulation/m6_checkpoint.hpp"

namespace {

using macro_sim::FirmId;
using macro_sim::Tick;
using macro_sim::simulation::capability_bit;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Phase;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M6AdvanceOptions;
using macro_sim::simulation::M6SimulationSpec;

[[nodiscard]] M6SimulationSpec base_spec() {
    M6SimulationSpec spec;
    auto &real = spec.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.households = 40;
    real.consumption_firms = 6;
    real.capital_firms = 2;
    real.seed = 61;
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
    spec.monetary_economy.rules.bank_count = 3;
    spec.monetary_economy.rules.opening_capital_per_bank = 30.0;
    spec.monetary_economy.rules.bank_leverage_mean = 8.0;
    spec.monetary_economy.rules.interbank = true;
    spec.monetary_economy.rules.full_firm_pnl = true;
    spec.monetary_economy.rules.realized_bank_pnl = true;
    spec.monetary_economy.rules.household_credit = true;
    spec.monetary_economy.policy.bank_capital_constraint = true;
    spec.monetary_economy.policy.bank_leverage_cap = 8.0;
    spec.monetary_economy.policy.firm_leverage_limit = 4.0;
    spec.monetary_economy.policy.household_credit_limit = 3.0;
    spec.monetary_economy.initial_policy_rate = 0.002;
    spec.policy.bank_minimum_capital = 20.0;
    spec.policy.bond_maturity_days = 30;
    spec.rules.bond_maturity_bucket = 5;
    spec.rules.watchlist_size = 4;
    spec.rules.entry_beta = 0.0;
    spec.rules.bank_entry_beta = 0.0;
    return spec;
}

struct Harness final {
    macro_sim::core::RootState root;
    macro_sim::simulation::M4Runtime real_runtime;
    macro_sim::simulation::M4TickScratch real_scratch;
    macro_sim::simulation::M5Runtime monetary_runtime;
    macro_sim::simulation::M5TickScratch monetary_scratch;
    macro_sim::simulation::M6Runtime runtime;
    macro_sim::simulation::M6TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build(M6SimulationSpec spec = base_spec()) {
    auto initialization = macro_sim::simulation::build_m6_genesis(spec);
    if (!initialization.ok()) {
        std::cerr << "M6 genesis failed: " << initialization.status().message() << "\n";
    }
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness harness{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.monetary_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick(0),
    };
    harness.real_scratch.reserve(harness.root);
    harness.monetary_scratch.reserve(harness.root);
    harness.scratch.reserve(harness.root, harness.runtime);
    return harness;
}

[[nodiscard]] macro_sim::Result<macro_sim::simulation::M6AdvanceResult>
advance(Harness &harness, std::uint64_t count, const M6AdvanceOptions &options = {}) {
    return macro_sim::simulation::advance_m6_ticks(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch, harness.runtime,
        harness.scratch, harness.tick, count, options);
}

void test_validation_and_prices() {
    auto spec = base_spec();
    spec.policy.margin_ltv = 1.0;
    assert(!macro_sim::simulation::validate_m6_spec(spec).ok());
    spec = base_spec();
    spec.rules.shares_per_firm = 0.0;
    assert(!macro_sim::simulation::validate_m6_spec(spec).ok());

    assert(std::abs(macro_sim::simulation::bond_price(100.0, 1, 0.0, 0.0) - 100.0) <
           1.0e-12);
    assert(std::abs(macro_sim::simulation::residual_income_fundamental(100.0, 2.0, 10.0,
                                                                       0.10) -
                    12.0) < 1.0e-12);
}

void test_genesis_and_multiday_advance() {
    auto harness = build();
    assert(harness.runtime.securities.equities().size() == 9);
    assert(harness.runtime.securities.validate(1.0e-8).ok());
    assert(macro_sim::simulation::validate_m6_state(harness.root, harness.real_runtime,
                                                    harness.monetary_runtime,
                                                    harness.runtime, harness.tick)
               .ok());

    auto result = advance(harness, 1);
    while (result.ok() && harness.tick < Tick(40)) {
        result = advance(harness, 1);
    }
    if (!result.ok()) {
        std::cerr << "M6 advance failed: " << result.status().message() << " at tick "
                  << harness.tick.value() << "\n";
        for (const auto &pnl : harness.monetary_scratch.bank_pnl_) {
            const auto capital =
                std::find_if(harness.monetary_scratch.bank_capital_.begin(),
                             harness.monetary_scratch.bank_capital_.end(),
                             [&](const auto &value) { return value.bank == pnl.bank; });
            if (capital != harness.monetary_scratch.bank_capital_.end()) {
                const double expected = capital->opening_capital + pnl.net_income +
                                        pnl.resolution_flow - pnl.distributions;
                std::cerr << "bank=" << pnl.bank.value()
                          << " opening=" << capital->opening_capital
                          << " income=" << pnl.net_income
                          << " resolution=" << pnl.resolution_flow
                          << " distributions=" << pnl.distributions
                          << " closing=" << capital->closing_capital
                          << " expected=" << expected << "\n";
            }
        }
    }
    assert(result.ok());
    assert(harness.tick == Tick(40));
    assert(result.get_if()->metrics.active_security_lots > 0);
    assert(result.get_if()->metrics.firm_equity_market_cap >= 0.0);
    assert(result.get_if()->metrics.bank_equity_market_cap >= 0.0);
    assert(result.get_if()->metrics.margin_principal >= 0.0);
    assert(std::abs(result.get_if()->metrics.clearing_residual) < 1.0e-7);
    assert(macro_sim::simulation::validate_m6_state(harness.root, harness.real_runtime,
                                                    harness.monetary_runtime,
                                                    harness.runtime, harness.tick)
               .ok());
}

void test_fault_is_atomic() {
    auto harness = build();
    const auto before = macro_sim::core::state_digest(harness.root);
    const auto equities = harness.runtime.securities.equities();
    const auto lots = harness.runtime.securities.lots();
    const auto firms = harness.runtime.firms;
    const auto watchlist = harness.runtime.watchlist_equities;
    const auto lifecycle_counter = harness.runtime.lifecycle_rng_counter;
    M6AdvanceOptions options;
    options.base.base.fault_before_phase = M4Phase::production;
    const auto failed = advance(harness, 1, options);
    assert(!failed.ok());
    assert(harness.tick == Tick(0));
    assert(before == macro_sim::core::state_digest(harness.root));
    assert(harness.runtime.securities.equities() == equities);
    assert(harness.runtime.securities.lots() == lots);
    assert(harness.runtime.firms == firms);
    assert(harness.runtime.watchlist_equities == watchlist);
    assert(harness.runtime.lifecycle_rng_counter == lifecycle_counter);
}

void test_forced_firm_exit_and_bank_entry() {
    auto harness = build();
    const auto firm_count = harness.root.firms.alive_count();
    M6AdvanceOptions exit;
    exit.force_firm_exit = FirmId(1);
    auto result = advance(harness, 1, exit);
    if (!result.ok()) {
        std::cerr << "M6 forced exit failed: " << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.root.firms.alive_count() == firm_count - 1);
    assert(harness.root.firms.get(FirmId(1)) == nullptr);
    assert(result.get_if()->metrics.firm_exits == 1);
    for (const auto &lot : harness.root.ownership.records()) {
        assert(!lot.active ||
               lot.asset.kind != macro_sim::core::AssetKind::firm_equity ||
               lot.asset.value != 1);
    }

    const auto bank_count = harness.root.banks.alive_count();
    M6AdvanceOptions entry;
    entry.force_bank_entry = true;
    result = advance(harness, 1, entry);
    if (!result.ok()) {
        std::cerr << "M6 forced bank entry failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    assert(harness.root.banks.alive_count() == bank_count + 1);
    assert(result.get_if()->metrics.bank_births == 1);
    assert(macro_sim::simulation::validate_m6_state(harness.root, harness.real_runtime,
                                                    harness.monetary_runtime,
                                                    harness.runtime, harness.tick)
               .ok());
}

void test_checkpoint_and_split_determinism() {
    auto direct = build();
    auto split = build();
    auto result = advance(direct, 20);
    assert(result.ok());
    for (std::uint64_t step = 0; step < 20; ++step) {
        result = advance(split, 1);
        assert(result.ok());
    }
    auto direct_checkpoint = macro_sim::simulation::save_m6_checkpoint(
        direct.root, direct.real_runtime, direct.monetary_runtime, direct.runtime,
        direct.tick);
    auto split_checkpoint = macro_sim::simulation::save_m6_checkpoint(
        split.root, split.real_runtime, split.monetary_runtime, split.runtime,
        split.tick);
    assert(direct_checkpoint.ok());
    assert(split_checkpoint.ok());
    assert(*direct_checkpoint.get_if() == *split_checkpoint.get_if());

    auto loaded =
        macro_sim::simulation::load_m6_checkpoint(*direct_checkpoint.get_if());
    assert(loaded.ok());
    auto value = std::move(*loaded.get_if());
    Harness resumed{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.monetary_runtime),
        {},
        std::move(value.runtime),
        {},
        value.tick,
    };
    resumed.real_scratch.reserve(resumed.root);
    resumed.monetary_scratch.reserve(resumed.root);
    resumed.scratch.reserve(resumed.root, resumed.runtime);
    result = advance(direct, 15);
    assert(result.ok());
    result = advance(resumed, 15);
    assert(result.ok());
    direct_checkpoint = macro_sim::simulation::save_m6_checkpoint(
        direct.root, direct.real_runtime, direct.monetary_runtime, direct.runtime,
        direct.tick);
    auto resumed_checkpoint = macro_sim::simulation::save_m6_checkpoint(
        resumed.root, resumed.real_runtime, resumed.monetary_runtime, resumed.runtime,
        resumed.tick);
    assert(direct_checkpoint.ok());
    assert(resumed_checkpoint.ok());
    assert(*direct_checkpoint.get_if() == *resumed_checkpoint.get_if());
    auto direct_digest = macro_sim::simulation::m6_state_digest(
        direct.root, direct.real_runtime, direct.monetary_runtime, direct.runtime,
        direct.tick);
    auto resumed_digest = macro_sim::simulation::m6_state_digest(
        resumed.root, resumed.real_runtime, resumed.monetary_runtime, resumed.runtime,
        resumed.tick);
    assert(direct_digest.ok());
    assert(resumed_digest.ok());
    assert(*direct_digest.get_if() == *resumed_digest.get_if());

    auto corrupt = *resumed_checkpoint.get_if();
    corrupt[corrupt.size() / 2] ^= 0x80U;
    assert(!macro_sim::simulation::load_m6_checkpoint(corrupt).ok());
    corrupt.push_back(0U);
    assert(!macro_sim::simulation::load_m6_checkpoint(corrupt).ok());
}

} // namespace

int main() {
    test_validation_and_prices();
    test_genesis_and_multiday_advance();
    test_fault_is_atomic();
    test_forced_firm_exit_and_bank_entry();
    test_checkpoint_and_split_determinism();
    std::cout << "m6 simulation tests passed\n";
    return 0;
}
