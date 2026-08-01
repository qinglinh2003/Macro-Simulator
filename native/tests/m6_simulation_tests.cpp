#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/transaction.hpp"
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

class HouseholdCashDrain final : public macro_sim::simulation::M6TickExtension {
  public:
    macro_sim::Status prepare_tick(
        const macro_sim::core::RootState &, macro_sim::simulation::M4Runtime &,
        macro_sim::simulation::M4TickScratch &, macro_sim::simulation::M5Runtime &,
        macro_sim::simulation::M5TickScratch &, macro_sim::simulation::M6Runtime &,
        macro_sim::simulation::M6TickScratch &, Tick, macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status run_labor(const macro_sim::core::RootState &,
                                macro_sim::simulation::M4Runtime &,
                                macro_sim::simulation::M4TickScratch &,
                                macro_sim::simulation::M5Runtime &,
                                macro_sim::simulation::M5TickScratch &,
                                macro_sim::simulation::M6Runtime &,
                                macro_sim::simulation::M6TickScratch &, Tick,
                                macro_sim::PhiloxRng &, bool &handled) override {
        handled = false;
        return macro_sim::Status::success();
    }

    macro_sim::Status close_day(
        const macro_sim::core::RootState &state, macro_sim::simulation::M4Runtime &,
        macro_sim::simulation::M4TickScratch &real, macro_sim::simulation::M5Runtime &,
        macro_sim::simulation::M5TickScratch &, macro_sim::simulation::M6Runtime &,
        macro_sim::simulation::M6TickScratch &, Tick, macro_sim::PhiloxRng &) override {
        auto result = macro_sim::Status::success();
        state.households.for_each_alive(
            [&](macro_sim::HouseholdId,
                const macro_sim::core::HouseholdComponent &household) {
                if (!result.ok()) {
                    return;
                }
                const auto account =
                    static_cast<std::size_t>(household.primary_account.value());
                const double balance = account < real.balances_.size()
                                           ? std::max(0.0, real.balances_[account])
                                           : 0.0;
                if (balance <= 1.0e-12) {
                    return;
                }
                const auto status = macro_sim::simulation::stage_m4_transfer(
                    state, real, household.primary_account,
                    state.institutions.treasury_account, balance);
                if (!status.ok()) {
                    result = status;
                }
            });
        return result;
    }

    macro_sim::Status validate(const macro_sim::core::RootState &,
                               const macro_sim::simulation::M4Runtime &,
                               const macro_sim::simulation::M4TickScratch &,
                               const macro_sim::simulation::M5Runtime &,
                               const macro_sim::simulation::M5TickScratch &,
                               const macro_sim::simulation::M6Runtime &,
                               const macro_sim::simulation::M6TickScratch &,
                               Tick) const override {
        return macro_sim::Status::success();
    }

    void commit(macro_sim::core::RootState &, macro_sim::simulation::M4Runtime &,
                macro_sim::simulation::M4TickScratch &,
                macro_sim::simulation::M5Runtime &,
                macro_sim::simulation::M5TickScratch &,
                macro_sim::simulation::M6Runtime &,
                macro_sim::simulation::M6TickScratch &, Tick,
                const macro_sim::simulation::M6Metrics &) noexcept override {}
};

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
    const auto validation = macro_sim::simulation::validate_m6_state(
        harness.root, harness.real_runtime, harness.monetary_runtime, harness.runtime,
        harness.tick);
    if (!validation.ok()) {
        std::cerr << "M6 validation failed: " << validation.message() << "\n";
    }
    assert(validation.ok());

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
    assert(result.get_if()->metrics.household_bond_market_value >= 0.0);
    assert(result.get_if()->metrics.bank_bond_market_value >= 0.0);
    assert(result.get_if()->metrics.household_firm_equity_market_value >= 0.0);
    assert(result.get_if()->metrics.household_bank_equity_market_value >= 0.0);
    assert(result.get_if()->metrics.firm_equity_turnover >= 0.0);
    assert(result.get_if()->metrics.bank_equity_turnover >= 0.0);
    assert(result.get_if()->metrics.margin_principal >= 0.0);
    assert(std::abs(result.get_if()->metrics.clearing_residual) < 1.0e-7);
    const auto closing_validation = macro_sim::simulation::validate_m6_state(
        harness.root, harness.real_runtime, harness.monetary_runtime, harness.runtime,
        harness.tick);
    if (!closing_validation.ok()) {
        std::cerr << "M6 closing validation failed: " << closing_validation.message()
                  << "\n";
    }
    assert(closing_validation.ok());
}

void test_bank_equity_uses_lagged_closed_income() {
    auto slow_spec = base_spec();
    slow_spec.rules.bank_equity_lambda = 0.001;
    auto fast_spec = slow_spec;
    fast_spec.rules.bank_equity_lambda = 1.0;
    auto slow = build(slow_spec);
    auto fast = build(fast_spec);

    const auto slow_result = advance(slow, 20);
    const auto fast_result = advance(fast, 20);
    assert(slow_result.ok());
    assert(fast_result.ok());
    const double slow_value =
        slow_result.get_if()->metrics.bank_equity_fundamental_value;
    const double fast_value =
        fast_result.get_if()->metrics.bank_equity_fundamental_value;
    assert(slow_value > 0.0);
    assert(fast_value > 0.0);
    assert(std::abs(slow_value - fast_value) > 1.0e-6);
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

void test_unsettled_trade_protects_firm_from_exit() {
    auto harness = build();
    const auto firm_count = harness.root.firms.alive_count();
    M6AdvanceOptions options;
    options.force_firm_exit = FirmId(1);
    options.protected_firm_exits.push_back(FirmId(1));
    const auto result = advance(harness, 1, options);
    assert(result.ok());
    assert(harness.root.firms.alive_count() == firm_count);
    assert(harness.root.firms.get(FirmId(1)) != nullptr);
    assert(result.get_if()->metrics.firm_exits == 0);
}

void test_firm_liquidation_recovers_haircut_collateral() {
    auto spec = base_spec();
    spec.monetary_economy.real_economy.rules.initial_expected_demand = 0.0;
    spec.monetary_economy.real_economy.rules.initial_consumption_inventory = 0.0;
    spec.monetary_economy.policy.firm_leverage_limit = 0.0;
    auto harness = build(spec);

    const auto firm_id = FirmId(1);
    const auto *firm = harness.root.firms.get(firm_id);
    assert(firm != nullptr);
    const auto node = harness.root.postings.settlement_node(firm->primary_account);
    assert(node.ok());
    macro_sim::BankId lender{};
    harness.root.banks.for_each_alive([&](macro_sim::BankId id, const auto &bank) {
        if (bank.settlement_node == *node.get_if()) {
            lender = id;
        }
    });
    assert(lender.valid());

    constexpr double principal = 20.0;
    macro_sim::core::SettlementTransaction origination(harness.root);
    assert(origination
               .originate_loan(
                   lender, macro_sim::core::OwnerId::firm(firm_id),
                   firm->primary_account, macro_sim::Money(principal),
                   macro_sim::core::LoanTerms{macro_sim::Rate(0.0), Tick(0), Tick(365)})
               .ok());
    const auto origination_receipt = origination.commit();
    assert(origination_receipt.ok());
    assert(origination_receipt.get_if()->created_loans.size() == 1U);
    const auto loan_id = origination_receipt.get_if()->created_loans.front();

    const auto balance = harness.root.postings.balance(firm->primary_account);
    assert(balance.ok() && balance.get_if()->value() > 0.0);
    macro_sim::AccountId recipient{};
    harness.root.households.for_each_alive(
        [&](macro_sim::HouseholdId, const auto &household) {
            const auto household_node =
                harness.root.postings.settlement_node(household.primary_account);
            if (!recipient.valid() && household_node.ok() &&
                *household_node.get_if() == *node.get_if()) {
                recipient = household.primary_account;
            }
        });
    assert(recipient.valid());
    macro_sim::core::SettlementTransaction drain(harness.root);
    assert(drain.transfer(firm->primary_account, recipient, *balance.get_if()).ok());
    assert(drain.commit().ok());

    M6AdvanceOptions exit;
    exit.force_firm_exit = firm_id;
    const auto result = advance(harness, 1, exit);
    if (!result.ok()) {
        std::cerr << "M6 collateral recovery failed: " << result.status().message()
                  << "\n";
    }
    assert(result.ok());
    const double loss = result.get_if()->metrics.economy.realized_credit_losses;
    assert(loss > 0.0);
    assert(loss < principal);
    const auto *assumed = harness.root.loans.get(loan_id);
    assert(assumed != nullptr && assumed->active);
    assert(assumed->borrower.kind() == macro_sim::core::OwnerKind::firm);
    assert(assumed->borrower != macro_sim::core::OwnerId::firm(firm_id));
    assert(assumed->principal.value() > 0.0);
    assert(assumed->principal.value() < principal);
}

void test_bank_entry_uses_post_extension_founder_cash() {
    auto harness = build();
    const auto bank_count = harness.root.banks.alive_count();
    HouseholdCashDrain extension;
    M6AdvanceOptions options;
    options.force_bank_entry = true;
    const auto result = macro_sim::simulation::advance_m6_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch, harness.runtime,
        harness.scratch, harness.tick, 1U, extension, options);
    assert(result.ok());
    assert(harness.root.banks.alive_count() == bank_count);
    assert(result.get_if()->metrics.bank_births == 0U);
}

void test_firm_entry_uses_post_extension_founder_cash() {
    auto spec = base_spec();
    spec.rules.entry_beta = 1.0;
    spec.rules.entry_max = 1;
    spec.rules.startup_deposits = 5.0;
    auto harness = build(spec);
    harness.runtime.last_metrics.economy.policy_rate = -1.0;
    const auto firm_count = harness.root.firms.alive_count();
    HouseholdCashDrain extension;
    const auto result = macro_sim::simulation::advance_m6_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch, harness.runtime,
        harness.scratch, harness.tick, 1U, extension);
    assert(result.ok());
    assert(harness.root.firms.alive_count() == firm_count);
    assert(result.get_if()->metrics.firm_births == 0U);
}

void test_capital_firms_are_not_idle_consumption_shells() {
    auto spec = base_spec();
    spec.rules.shell_exit_days = 1;
    auto harness = build(spec);
    std::vector<FirmId> capital_firms;
    for (const auto firm_id : harness.real_scratch.firm_ids_) {
        auto *firm = harness.root.firms.get(firm_id);
        assert(firm != nullptr);
        if (firm->sector == macro_sim::core::FirmSector::capital) {
            capital_firms.push_back(firm_id);
            firm->goods_inventory = macro_sim::Goods(0.0);
            firm->demand_expected = 0.0;
            firm->target_inventory_previous = 0.0;
        } else if (firm->sector == macro_sim::core::FirmSector::consumption) {
            firm->investment_adjustment = 0.0;
            firm->capital_depreciation = 0.0;
        }
    }
    assert(capital_firms.size() == 2);

    const auto result = advance(harness, 1);
    assert(result.ok());
    for (const auto firm_id : capital_firms) {
        const auto *firm = harness.root.firms.get(firm_id);
        const auto lifecycle = std::find_if(
            harness.runtime.firms.begin(), harness.runtime.firms.end(),
            [firm_id](const auto &value) { return value.firm == firm_id; });
        assert(firm != nullptr);
        assert(lifecycle != harness.runtime.firms.end());
        assert(lifecycle->active);
        assert(lifecycle->shell_days == 0);
    }
}

void test_genesis_respects_initial_necessity_share() {
    auto spec = base_spec();
    spec.rules.initial_necessity_share = 0.66;
    auto harness = build(spec);
    std::uint64_t necessity = 0U;
    std::uint64_t luxury = 0U;
    harness.root.firms.for_each_alive([&](FirmId id,
                                          const macro_sim::core::FirmComponent &firm) {
        if (firm.sector != macro_sim::core::FirmSector::consumption) {
            return;
        }
        const auto &lifecycle =
            harness.runtime.firms[static_cast<std::size_t>(id.value())];
        if (lifecycle.stratum == macro_sim::simulation::ConsumptionStratum::necessity) {
            ++necessity;
        } else {
            ++luxury;
        }
    });
    assert(necessity == 4U);
    assert(luxury == 2U);

    spec.rules.initial_necessity_share = 1.01;
    assert(!macro_sim::simulation::build_m6_genesis(spec).ok());
}

void test_firm_dividends_follow_equity_ownership() {
    auto spec = base_spec();
    auto &fiscal = spec.monetary_economy.policy;
    fiscal.government_consumption_share = 0.0;
    fiscal.government_investment_share = 0.0;
    fiscal.profit_tax_rate = 0.0;
    fiscal.income_tax_rate = 0.0;
    fiscal.consumption_tax_rate = 0.0;
    fiscal.wealth_tax_rate = 0.0;
    fiscal.unemployment_benefit_replacement = 0.0;
    spec.rules.bonds = false;
    spec.rules.founder_owned_genesis = true;
    spec.rules.household_equity_target = 0.0;
    spec.rules.portfolio_adjustment = 0.0;
    spec.rules.equity_finance = false;
    spec.rules.margin_credit = false;
    spec.rules.bank_equity = false;
    spec.rules.bank_dynamics = false;
    spec.rules.firm_dynamics = false;
    auto harness = build(spec);
    harness.root.firms.for_each_alive(
        [&](macro_sim::FirmId id, const macro_sim::core::FirmComponent &firm) {
            auto *mutable_firm = harness.root.firms.get(id);
            mutable_firm->dividend_payout =
                firm.sector == macro_sim::core::FirmSector::consumption ? 1.0 : 0.0;
        });
    const auto result = advance(harness, 1);
    assert(result.ok());
    std::vector<double> expected(harness.real_scratch.household_work_.size(), 0.0);
    double dividend_total = 0.0;
    for (const auto &equity : harness.runtime.securities.equities()) {
        if (!equity.active ||
            equity.issuer_kind != macro_sim::core::EquityIssuerKind::firm) {
            continue;
        }
        const auto firm = macro_sim::FirmId(equity.issuer.value());
        const auto identity = static_cast<std::size_t>(firm.value());
        assert(identity < harness.real_scratch.firm_dense_index_.size());
        const auto firm_index = harness.real_scratch.firm_dense_index_[identity];
        assert(firm_index < harness.real_scratch.firm_work_.size());
        const double dividend = harness.real_scratch.firm_work_[firm_index].dividends;
        dividend_total += dividend;
        const auto security = macro_sim::core::SecurityId::equity(equity.id);
        const double units = harness.runtime.securities.total_units(security);
        assert(units > 0.0);
        for (const auto lot_id :
             harness.runtime.securities.lots_for_security(security)) {
            const auto *lot = harness.runtime.securities.get(lot_id);
            if (lot == nullptr || !lot->active() ||
                lot->holder.kind() != macro_sim::core::OwnerKind::household) {
                continue;
            }
            const auto holder = static_cast<std::size_t>(lot->holder.value());
            assert(holder < harness.real_scratch.household_dense_index_.size());
            const auto household_index =
                harness.real_scratch.household_dense_index_[holder];
            assert(household_index < expected.size());
            expected[household_index] += dividend * lot->units / units;
        }
    }
    assert(dividend_total > 0.0);
    for (std::size_t index = 0; index < harness.real_scratch.household_work_.size();
         ++index) {
        const auto &work = harness.real_scratch.household_work_[index];
        const double wage_income =
            work.labor_sold * spec.monetary_economy.real_economy.rules.initial_wage;
        assert(std::abs((work.income_realized - wage_income) - expected[index]) <
               1.0e-7);
    }
}

void test_wealth_tax_base_includes_securities_and_subtracts_debt() {
    auto spec = base_spec();
    auto &fiscal = spec.monetary_economy.policy;
    fiscal.government_consumption_share = 0.0;
    fiscal.government_investment_share = 0.0;
    fiscal.profit_tax_rate = 0.0;
    fiscal.income_tax_rate = 0.0;
    fiscal.consumption_tax_rate = 0.0;
    fiscal.wealth_tax_rate = 0.001;
    fiscal.wealth_allowance = 0.0;
    fiscal.unemployment_benefit_replacement = 0.0;
    auto &banking = spec.monetary_economy.rules;
    banking.interest_by_deposits = false;
    banking.deposit_interest_arrears = false;
    banking.bank_payout_ratio = 0.0;
    spec.rules.bonds = false;
    spec.rules.founder_owned_genesis = true;
    spec.rules.household_equity_target = 0.0;
    spec.rules.portfolio_adjustment = 0.0;
    spec.rules.equity_finance = false;
    spec.rules.margin_credit = false;
    spec.rules.bank_equity = false;
    spec.rules.bank_dynamics = false;
    spec.rules.firm_dynamics = false;
    auto harness = build(spec);
    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(harness.real_scratch.household_net_wealth_.size() ==
           harness.real_scratch.household_ids_.size());
    double security_total = 0.0;
    for (std::size_t index = 0; index < harness.real_scratch.household_ids_.size();
         ++index) {
        const auto household_id = harness.real_scratch.household_ids_[index];
        const auto *household = harness.root.households.get(household_id);
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        double security_value = 0.0;
        for (const auto lot_id : harness.runtime.securities.lots_for_holder(
                 macro_sim::core::OwnerId::household(household_id))) {
            const auto *lot = harness.runtime.securities.get(lot_id);
            if (lot == nullptr || !lot->active()) {
                continue;
            }
            if (lot->security.kind() == macro_sim::core::SecurityKind::equity) {
                const auto *equity = harness.runtime.securities.get(
                    macro_sim::EquityId(lot->security.value()));
                if (equity != nullptr && equity->active) {
                    security_value += lot->units * equity->price.value();
                }
            } else {
                security_value += lot->units;
            }
        }
        security_total += security_value;
        const double debt = account < harness.monetary_scratch.debt_by_account_.size()
                                ? harness.monetary_scratch.debt_by_account_[account]
                                : 0.0;
        const double net_wealth = harness.real_scratch.household_net_wealth_[index];
        const double wealth_tax = 0.001 * std::max(0.0, net_wealth);
        const double cash_before_tax =
            harness.real_scratch.balances_[account] + wealth_tax;
        assert(std::abs(net_wealth - (cash_before_tax + security_value - debt)) <
               1.0e-7);
    }
    assert(security_total > 0.0);
}

void test_capital_firm_entry_responds_to_sector_capacity_pressure() {
    auto spec = base_spec();
    spec.monetary_economy.real_economy.rules.initial_firm_money = 100.0;
    spec.rules.capital_firm_entry = true;
    spec.rules.subscale_viability_workers = 0.001;
    spec.rules.k_entry_demand = 1.0;
    spec.rules.k_entry_hazard = 1.0;
    spec.rules.startup_deposits = 5.0;
    auto harness = build(spec);
    const auto count_capital_firms = [&]() {
        std::size_t count = 0;
        harness.root.firms.for_each_alive([&](FirmId, const auto &firm) {
            count += firm.sector == macro_sim::core::FirmSector::capital;
        });
        return count;
    };
    const auto before = count_capital_firms();

    const auto result = advance(harness, 1);
    assert(result.ok());
    assert(count_capital_firms() == before + 1);
    assert(result.get_if()->metrics.firm_births == 1);
    assert(macro_sim::simulation::validate_m6_state(harness.root, harness.real_runtime,
                                                    harness.monetary_runtime,
                                                    harness.runtime, harness.tick)
               .ok());
}

void test_subscale_exit_consolidates_without_extinguishing_a_sector() {
    auto spec = base_spec();
    spec.rules.firm_subscale_exit = true;
    spec.rules.subscale_viability_workers = 1.0e6;
    spec.rules.subscale_grace_days = 1;
    spec.rules.subscale_exit_hazard = 1.0;
    auto harness = build(spec);

    const auto result = advance(harness, 1);
    assert(result.ok());
    std::array<std::size_t, 2> active{};
    harness.root.firms.for_each_alive([&](FirmId, const auto &firm) {
        if (firm.sector == macro_sim::core::FirmSector::consumption) {
            ++active[0];
        } else if (firm.sector == macro_sim::core::FirmSector::capital) {
            ++active[1];
        }
    });
    assert(active[0] == 1);
    assert(active[1] == 1);
    assert(result.get_if()->metrics.firm_exits == 6);
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
    test_bank_equity_uses_lagged_closed_income();
    test_fault_is_atomic();
    test_forced_firm_exit_and_bank_entry();
    test_unsettled_trade_protects_firm_from_exit();
    test_firm_liquidation_recovers_haircut_collateral();
    test_bank_entry_uses_post_extension_founder_cash();
    test_firm_entry_uses_post_extension_founder_cash();
    test_capital_firms_are_not_idle_consumption_shells();
    test_genesis_respects_initial_necessity_share();
    test_firm_dividends_follow_equity_ownership();
    test_wealth_tax_base_includes_securities_and_subtracts_debt();
    test_capital_firm_entry_responds_to_sector_capacity_pressure();
    test_subscale_exit_consolidates_without_extinguishing_a_sector();
    test_checkpoint_and_split_determinism();
    std::cout << "m6 simulation tests passed\n";
    return 0;
}
