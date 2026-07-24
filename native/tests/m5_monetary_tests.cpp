#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m5.hpp"
#include "macro_sim/simulation/m5_checkpoint.hpp"

namespace {

using macro_sim::AccountId;
using macro_sim::BankId;
using macro_sim::Tick;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M4Phase;
using macro_sim::simulation::M5AdvanceOptions;
using macro_sim::simulation::M5PolicyState;
using macro_sim::simulation::M5Runtime;
using macro_sim::simulation::M5SimulationSpec;
using macro_sim::simulation::M5TickScratch;
using macro_sim::simulation::MonetaryRegime;
using macro_sim::simulation::capability_bit;

[[nodiscard]] M5SimulationSpec base_spec() {
    M5SimulationSpec spec;
    spec.real_economy.vertical = M4Vertical::capital_fiscal;
    spec.real_economy.households = 24;
    spec.real_economy.consumption_firms = 4;
    spec.real_economy.capital_firms = 2;
    spec.real_economy.seed = 51;
    spec.real_economy.requested_capabilities =
        capability_bit(M4Capability::physical_capital)
        | capability_bit(M4Capability::government);
    spec.real_economy.rules.initial_household_money = 20.0;
    spec.real_economy.rules.initial_firm_money = 2.0;
    spec.real_economy.rules.initial_consumption_inventory = 2.0;
    spec.real_economy.rules.initial_capital_inventory = 2.0;
    spec.real_economy.rules.initial_consumption_capital = 4.0;
    spec.real_economy.rules.initial_expected_demand = 8.0;
    spec.real_economy.rules.initial_wage = 2.0;
    spec.real_economy.rules.initial_price = 1.5;
    spec.real_economy.rules.initial_capital_price = 1.5;
    spec.rules.bank_count = 3;
    spec.rules.opening_capital_per_bank = 30.0;
    spec.rules.bank_leverage_mean = 8.0;
    spec.rules.rate_competition = true;
    spec.rules.loan_spread_dispersion = 0.001;
    spec.rules.interbank = true;
    spec.rules.full_firm_pnl = true;
    spec.rules.realized_bank_pnl = true;
    spec.rules.household_credit = true;
    spec.rules.deposit_rate = 0.0001;
    spec.rules.deposit_interest_arrears = true;
    spec.policy.bank_capital_constraint = true;
    spec.policy.bank_leverage_cap = 8.0;
    spec.policy.firm_leverage_limit = 4.0;
    spec.policy.household_credit_limit = 3.0;
    spec.initial_policy_rate = 0.002;
    return spec;
}

struct Harness final {
    macro_sim::core::RootState root;
    macro_sim::simulation::M4Runtime real_runtime;
    macro_sim::simulation::M4TickScratch real_scratch;
    M5Runtime runtime;
    M5TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build(M5SimulationSpec spec = base_spec()) {
    auto initialization =
        macro_sim::simulation::build_m5_genesis(spec);
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness harness{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick(0),
    };
    harness.real_scratch.reserve(harness.root);
    harness.scratch.reserve(harness.root);
    return harness;
}

void test_policy_validation() {
    M5PolicyState policy;
    policy.monetary_regime = MonetaryRegime::manual;
    assert(!macro_sim::simulation::validate_m5_policy(policy).ok());
    policy.manual_policy_rate = 0.03;
    assert(macro_sim::simulation::validate_m5_policy(policy).ok());
    policy.monetary_regime = MonetaryRegime::taylor;
    assert(!macro_sim::simulation::validate_m5_policy(policy).ok());
    policy.manual_policy_rate.reset();
    assert(macro_sim::simulation::validate_m5_policy(policy).ok());
    policy.taylor_inflation = -1.0;
    assert(!macro_sim::simulation::validate_m5_policy(policy).ok());

    auto spec = base_spec();
    spec.rules.run_fear_persistence = 1.1;
    assert(!macro_sim::simulation::validate_m5_spec(spec).ok());
}

void test_size_based_bank_assignment() {
    auto round_robin_spec = base_spec();
    round_robin_spec.real_economy.households = 5;
    round_robin_spec.rules.assign_banks_by_size = false;
    auto round_robin = build(round_robin_spec);
    const auto* first_firm =
        round_robin.root.firms.get(macro_sim::FirmId(1));
    assert(first_firm != nullptr);
    const auto round_robin_node = round_robin.root.postings
        .get(first_firm->primary_account)
        ->key.settlement_node;

    auto by_size_spec = round_robin_spec;
    by_size_spec.rules.assign_banks_by_size = true;
    auto by_size = build(by_size_spec);
    first_firm = by_size.root.firms.get(macro_sim::FirmId(1));
    assert(first_firm != nullptr);
    const auto by_size_node = by_size.root.postings
        .get(first_firm->primary_account)
        ->key.settlement_node;

    assert(round_robin_node != by_size_node);
}

void test_credit_and_monetary_tick() {
    auto harness = build();
    auto result = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        8
    );
    if (!result.ok()) {
        std::cerr << "credit tick failed: "
                  << result.status().message() << "\n";
    }
    assert(result.ok());
    assert(harness.tick == Tick(8));
    assert(result.get_if()->metrics.new_credit >= 0.0);
    assert(result.get_if()->metrics.total_loan_principal >= 0.0);
    assert(result.get_if()->metrics.alive_banks == 3);
    assert(std::abs(
        result.get_if()->metrics.total_reserves
        - result.get_if()->metrics.reserve_stock
    ) < 1.0e-7);
    assert(macro_sim::simulation::validate_m5_state(
        harness.root,
        harness.real_runtime,
        harness.runtime,
        harness.tick
    ).ok());

    harness.runtime.policy.monetary_regime =
        MonetaryRegime::manual;
    harness.runtime.policy.manual_policy_rate = 0.04;
    result = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1
    );
    assert(result.ok());
    assert(std::abs(result.get_if()->metrics.policy_rate - 0.04)
        < 1.0e-12);

    harness.runtime.policy.monetary_regime =
        MonetaryRegime::exogenous;
    harness.runtime.policy.manual_policy_rate.reset();
    result = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1
    );
    assert(result.ok());
    assert(std::abs(
        result.get_if()->metrics.policy_rate
        - harness.runtime.initial_policy_rate
    ) < 1.0e-12);
}

void test_interbank_clearing() {
    auto harness = build();
    auto& reserves = harness.root.reserves.records();
    assert(reserves.size() == 3);
    reserves[0].balance = macro_sim::Money(-25.0);
    reserves[1].balance = macro_sim::Money(50.0);
    const double stock =
        reserves[0].balance.value()
        + reserves[1].balance.value()
        + reserves[2].balance.value();
    harness.root.reserves.commit_projected_stock(
        macro_sim::Money(stock)
    );
    auto result = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1
    );
    assert(result.ok());
    assert(result.get_if()->metrics.interbank_volume > 0.0);
    assert(harness.root.interbank.total_principal().value() > 0.0);
}

void test_realized_and_legacy_bank_pnl_paths() {
    auto realized_spec = base_spec();
    realized_spec.rules.realized_bank_pnl = true;
    realized_spec.rules.deposit_rate = 0.01;
    auto realized = build(realized_spec);
    const auto realized_result =
        macro_sim::simulation::advance_m5_ticks(
            realized.root,
            realized.real_runtime,
            realized.real_scratch,
            realized.runtime,
            realized.scratch,
            realized.tick,
            1
        );
    assert(realized_result.ok());
    assert(
        realized_result.get_if()->metrics.deposit_interest_paid > 0.0
    );

    auto legacy_spec = realized_spec;
    legacy_spec.rules.realized_bank_pnl = false;
    auto legacy = build(legacy_spec);
    const auto legacy_result =
        macro_sim::simulation::advance_m5_ticks(
            legacy.root,
            legacy.real_runtime,
            legacy.real_scratch,
            legacy.runtime,
            legacy.scratch,
            legacy.tick,
            1
        );
    assert(legacy_result.ok());
    assert(
        legacy_result.get_if()->metrics.deposit_interest_paid == 0.0
    );
    double legacy_distributions = 0.0;
    for (const auto& pnl : legacy.root.bank_pnl.records()) {
        legacy_distributions += pnl.distributions;
    }
    assert(legacy_distributions > 0.0);
}

void test_phase_fault_is_atomic() {
    auto harness = build();
    const auto before = macro_sim::core::state_digest(harness.root);
    const auto runtime_before = harness.runtime;
    const auto loan_count = harness.root.loans.size();
    M5AdvanceOptions options;
    options.base.fault_before_phase = M4Phase::production;
    auto failed = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1,
        options
    );
    assert(!failed.ok());
    assert(harness.tick == Tick(0));
    const auto after = macro_sim::core::state_digest(harness.root);
    assert(before == after);
    assert(harness.root.loans.size() == loan_count);
    assert(harness.runtime == runtime_before);
}

void test_default_resolution() {
    auto spec = base_spec();
    spec.rules.opening_capital_per_bank = 1.0;
    spec.policy.bank_leverage_cap = 50.0;
    spec.rules.bank_leverage_mean = 50.0;
    spec.policy.state_resolution_backstop = true;
    spec.rules.direct_monetary_transmission = false;
    spec.real_economy.rules.initial_firm_money = 0.0;
    spec.real_economy.rules.initial_consumption_inventory = 0.0;
    spec.real_economy.rules.initial_capital_inventory = 0.0;
    spec.real_economy.rules.initial_expected_demand = 30.0;
    auto harness = build(spec);
    auto first = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1
    );
    assert(first.ok());
    AccountId borrower{};
    for (const auto& loan : harness.root.loans.records()) {
        if (loan.active && loan.principal.value() > 1.0) {
            borrower = loan.borrower_account;
            break;
        }
    }
    if (!borrower.valid()) {
        for (const auto& loan : harness.root.loans.records()) {
            if (loan.active) {
                borrower = loan.borrower_account;
                break;
            }
        }
    }
    assert(borrower.valid());
    M5AdvanceOptions options;
    options.force_default_account = borrower;
    auto crisis = macro_sim::simulation::advance_m5_ticks(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1,
        options
    );
    assert(crisis.ok());
    assert(crisis.get_if()->metrics.realized_credit_losses > 0.0);
    assert(crisis.get_if()->metrics.bank_failures >= 1);
    assert(crisis.get_if()->metrics.resolution_cost >= 0.0);
}

void test_run_and_lolr() {
    auto spec = base_spec();
    spec.rules.bank_runs = true;
    spec.policy.open_market_operations = true;
    spec.policy.reserve_target = 0.0;
    spec.policy.reserve_gap_close = 1.0;
    spec.policy.lender_of_last_resort = false;
    auto without_lolr = build(spec);
    auto drain = macro_sim::simulation::advance_m5_ticks(
        without_lolr.root,
        without_lolr.real_runtime,
        without_lolr.real_scratch,
        without_lolr.runtime,
        without_lolr.scratch,
        without_lolr.tick,
        1
    );
    assert(drain.ok());
    M5AdvanceOptions run;
    run.force_run_bank = BankId(2);
    auto failed = macro_sim::simulation::advance_m5_ticks(
        without_lolr.root,
        without_lolr.real_runtime,
        without_lolr.real_scratch,
        without_lolr.runtime,
        without_lolr.scratch,
        without_lolr.tick,
        1,
        run
    );
    assert(failed.ok());
    assert(failed.get_if()->metrics.bank_failures >= 1);

    spec.policy.lender_of_last_resort = true;
    auto with_lolr = build(spec);
    drain = macro_sim::simulation::advance_m5_ticks(
        with_lolr.root,
        with_lolr.real_runtime,
        with_lolr.real_scratch,
        with_lolr.runtime,
        with_lolr.scratch,
        with_lolr.tick,
        1
    );
    assert(drain.ok());
    auto rescued = macro_sim::simulation::advance_m5_ticks(
        with_lolr.root,
        with_lolr.real_runtime,
        with_lolr.real_scratch,
        with_lolr.runtime,
        with_lolr.scratch,
        with_lolr.tick,
        1,
        run
    );
    assert(rescued.ok());
    assert(rescued.get_if()->metrics.lolr_advances > 0.0);
    assert(rescued.get_if()->metrics.bank_failures == 0);
}

void test_checkpoint_continuation() {
    auto direct = build();
    auto prefix = macro_sim::simulation::advance_m5_ticks(
        direct.root,
        direct.real_runtime,
        direct.real_scratch,
        direct.runtime,
        direct.scratch,
        direct.tick,
        4
    );
    assert(prefix.ok());
    auto saved = macro_sim::simulation::save_m5_checkpoint(
        direct.root,
        direct.real_runtime,
        direct.runtime,
        direct.tick
    );
    assert(saved.ok());
    auto loaded = macro_sim::simulation::load_m5_checkpoint(
        *saved.get_if()
    );
    assert(loaded.ok());
    auto loaded_value = std::move(*loaded.get_if());
    Harness resumed{
        std::move(loaded_value.root),
        std::move(loaded_value.real_economy_runtime),
        {},
        std::move(loaded_value.runtime),
        {},
        loaded_value.tick,
    };
    resumed.real_scratch.reserve(resumed.root);
    resumed.scratch.reserve(resumed.root);
    auto direct_tail = macro_sim::simulation::advance_m5_ticks(
        direct.root,
        direct.real_runtime,
        direct.real_scratch,
        direct.runtime,
        direct.scratch,
        direct.tick,
        5
    );
    auto resumed_tail = macro_sim::simulation::advance_m5_ticks(
        resumed.root,
        resumed.real_runtime,
        resumed.real_scratch,
        resumed.runtime,
        resumed.scratch,
        resumed.tick,
        5
    );
    assert(direct_tail.ok());
    assert(resumed_tail.ok());
    auto direct_checkpoint =
        macro_sim::simulation::save_m5_checkpoint(
            direct.root,
            direct.real_runtime,
            direct.runtime,
            direct.tick
        );
    auto resumed_checkpoint =
        macro_sim::simulation::save_m5_checkpoint(
            resumed.root,
            resumed.real_runtime,
            resumed.runtime,
            resumed.tick
        );
    assert(direct_checkpoint.ok());
    assert(resumed_checkpoint.ok());
    assert(*direct_checkpoint.get_if() == *resumed_checkpoint.get_if());

    auto corrupt = *saved.get_if();
    corrupt[corrupt.size() / 2] ^= 0x80U;
    assert(!macro_sim::simulation::load_m5_checkpoint(corrupt).ok());
}

}  // namespace

int main() {
    test_policy_validation();
    test_size_based_bank_assignment();
    test_credit_and_monetary_tick();
    test_interbank_clearing();
    test_realized_and_legacy_bank_pnl_paths();
    test_phase_fault_is_atomic();
    test_default_resolution();
    test_run_and_lolr();
    test_checkpoint_continuation();
    std::cout << "m5 monetary tests passed\n";
    return 0;
}
