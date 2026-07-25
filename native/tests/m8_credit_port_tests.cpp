#include <cassert>
#include <cmath>
#include <cstdint>

#include "macro_sim/simulation/m5.hpp"

namespace {

using macro_sim::AccountId;
using macro_sim::LoanId;
using macro_sim::Money;
using macro_sim::Tick;
using macro_sim::simulation::capability_bit;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Runtime;
using macro_sim::simulation::M4TickScratch;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M5Metrics;
using macro_sim::simulation::M5Runtime;
using macro_sim::simulation::M5SimulationSpec;
using macro_sim::simulation::M5TickExtension;
using macro_sim::simulation::M5TickScratch;

[[nodiscard]] M5SimulationSpec spec() {
    M5SimulationSpec value;
    value.real_economy.vertical = M4Vertical::capital_fiscal;
    value.real_economy.households = 8;
    value.real_economy.consumption_firms = 2;
    value.real_economy.capital_firms = 1;
    value.real_economy.seed = 808;
    value.real_economy.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
        capability_bit(M4Capability::government);
    value.real_economy.rules.initial_household_money = 100.0;
    value.real_economy.rules.initial_firm_money = 100.0;
    value.real_economy.rules.initial_consumption_inventory = 10.0;
    value.real_economy.rules.initial_capital_inventory = 10.0;
    value.rules.bank_count = 2;
    value.rules.opening_capital_per_bank = 100.0;
    value.rules.household_credit = false;
    value.rules.realized_bank_pnl = true;
    value.policy.bank_capital_constraint = true;
    value.policy.bank_leverage_cap = 10.0;
    return value;
}

struct Harness final {
    macro_sim::core::RootState root;
    M4Runtime real_runtime;
    M4TickScratch real_scratch;
    M5Runtime runtime;
    M5TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build() {
    auto initialized = macro_sim::simulation::build_m5_genesis(spec());
    assert(initialized.ok());
    auto value = std::move(*initialized.get_if());
    Harness result{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick{},
    };
    result.real_scratch.reserve(result.root);
    result.scratch.reserve(result.root);
    return result;
}

enum class PortAction : std::uint8_t {
    originate = 0,
    writeoff = 1,
    stale_quote = 2,
};

class CreditPort final : public M5TickExtension {
  public:
    CreditPort(PortAction action, AccountId account, LoanId loan = {})
        : action_(action), account_(account), loan_(loan) {}

    macro_sim::Status prepare_tick(const macro_sim::core::RootState &, M4Runtime &,
                                   M4TickScratch &, M5Runtime &, M5TickScratch &, Tick,
                                   macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status after_planning(const macro_sim::core::RootState &, M4Runtime &,
                                     M4TickScratch &, M5Runtime &, M5TickScratch &,
                                     Tick, macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status run_labor(const macro_sim::core::RootState &, M4Runtime &,
                                M4TickScratch &, M5Runtime &, M5TickScratch &, Tick,
                                macro_sim::PhiloxRng &, bool &handled) override {
        handled = false;
        return macro_sim::Status::success();
    }

    macro_sim::Status before_settlement(const macro_sim::core::RootState &, M4Runtime &,
                                        M4TickScratch &, M5Runtime &, M5TickScratch &,
                                        Tick, macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status after_settlement(const macro_sim::core::RootState &, M4Runtime &,
                                       M4TickScratch &, M5Runtime &, M5TickScratch &,
                                       Tick, macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status before_bank_resolution(const macro_sim::core::RootState &,
                                             M4Runtime &, M4TickScratch &, M5Runtime &,
                                             M5TickScratch &, Tick,
                                             macro_sim::PhiloxRng &) override {
        return macro_sim::Status::success();
    }

    macro_sim::Status close_institutions(const macro_sim::core::RootState &state,
                                         M4Runtime &, M4TickScratch &real,
                                         M5Runtime &runtime, M5TickScratch &scratch,
                                         Tick tick, macro_sim::PhiloxRng &) override {
        if (action_ == PortAction::originate) {
            const auto quote = macro_sim::simulation::quote_m5_credit(
                state, real, runtime, scratch, account_, Money(7.5), Money(7.5));
            if (!quote.ok()) {
                return quote.status();
            }
            if (std::abs(quote.get_if()->principal.value() - 7.5) > 1.0e-12) {
                return macro_sim::Status(macro_sim::ErrorCode::contract_violation,
                                         "mortgage quote was partially funded");
            }
            const auto account_slot = static_cast<std::size_t>(account_.value());
            const double before = real.balances_[account_slot];
            const auto staged = macro_sim::simulation::stage_m5_credit(
                state, real, runtime, scratch, *quote.get_if(), tick);
            if (!staged.ok()) {
                return staged.status();
            }
            funded_delta_ = real.balances_[account_slot] - before;
            loan_ = *staged.get_if();
            return macro_sim::Status::success();
        }
        if (action_ == PortAction::stale_quote) {
            const auto quote = macro_sim::simulation::quote_m5_credit(
                state, real, runtime, scratch, account_, Money(3.0), Money(3.0));
            if (!quote.ok()) {
                return quote.status();
            }
            const auto account_slot = static_cast<std::size_t>(account_.value());
            const double balance = real.balances_[account_slot];
            scratch.loans_.push_back({});
            const auto staged = macro_sim::simulation::stage_m5_credit(
                state, real, runtime, scratch, *quote.get_if(), tick);
            scratch.loans_.pop_back();
            stale_rejected_ =
                !staged.ok() &&
                staged.status().code() == macro_sim::ErrorCode::stale_handle &&
                real.balances_[account_slot] == balance;
            return stale_rejected_
                       ? macro_sim::Status::success()
                       : macro_sim::Status(
                             macro_sim::ErrorCode::contract_violation,
                             "stale mortgage quote changed projected state");
        }
        if (!loan_.valid() || loan_.value() > scratch.loans_.size()) {
            return macro_sim::Status(macro_sim::ErrorCode::not_found,
                                     "mortgage loan is absent");
        }
        loss_ = scratch.loans_[static_cast<std::size_t>(loan_.value() - 1)]
                    .principal.value();
        return macro_sim::simulation::stage_m5_loan_writeoff(state, real, scratch,
                                                             loan_, tick);
    }

    macro_sim::Status validate(const macro_sim::core::RootState &, const M4Runtime &,
                               const M4TickScratch &, const M5Runtime &,
                               const M5TickScratch &, Tick) const override {
        return macro_sim::Status::success();
    }

    void commit(macro_sim::core::RootState &, M4Runtime &, M4TickScratch &, M5Runtime &,
                M5TickScratch &, Tick, const M5Metrics &) noexcept override {}

    [[nodiscard]] LoanId loan() const noexcept { return loan_; }
    [[nodiscard]] double loss() const noexcept { return loss_; }
    [[nodiscard]] double funded_delta() const noexcept { return funded_delta_; }
    [[nodiscard]] bool stale_rejected() const noexcept { return stale_rejected_; }

  private:
    PortAction action_;
    AccountId account_{};
    LoanId loan_{};
    double loss_{0.0};
    double funded_delta_{0.0};
    bool stale_rejected_{false};
};

void test_quote_staging_and_writeoff() {
    auto harness = build();
    const auto household = harness.root.households.get(macro_sim::HouseholdId(1));
    assert(household != nullptr);
    const auto account = household->primary_account;
    CreditPort originator(PortAction::originate, account);
    auto advanced = macro_sim::simulation::advance_m5_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch, harness.runtime,
        harness.scratch, harness.tick, 1, originator);
    assert(advanced.ok());
    assert(originator.loan().valid());
    const auto *loan = harness.root.loans.get(originator.loan());
    assert(loan != nullptr && loan->active);
    assert(std::abs(loan->principal.value() - 7.5) < 1.0e-12);
    assert(std::abs(originator.funded_delta() - 7.5) < 1.0e-12);

    const auto lender = loan->lender;
    CreditPort foreclosure(PortAction::writeoff, account, originator.loan());
    advanced = macro_sim::simulation::advance_m5_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch, harness.runtime,
        harness.scratch, harness.tick, 1, foreclosure);
    assert(advanced.ok());
    loan = harness.root.loans.get(originator.loan());
    assert(loan != nullptr && !loan->active);
    assert(loan->principal.value() == 0.0);
    assert(foreclosure.loss() > 0.0);
    assert(harness.root.bank_pnl.get(lender)->realized_loan_losses + 1.0e-9 >=
           foreclosure.loss());
    assert(macro_sim::simulation::validate_m5_state(harness.root, harness.real_runtime,
                                                    harness.runtime, harness.tick)
               .ok());
}

void test_stale_quote_rejected_without_mutation() {
    auto harness = build();
    const auto household = harness.root.households.get(macro_sim::HouseholdId(1));
    assert(household != nullptr);
    CreditPort stale(PortAction::stale_quote, household->primary_account);
    const auto advanced = macro_sim::simulation::advance_m5_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch, harness.runtime,
        harness.scratch, harness.tick, 1, stale);
    assert(advanced.ok());
    assert(stale.stale_rejected());
}

} // namespace

int main() {
    test_quote_staging_and_writeoff();
    test_stale_quote_rejected_without_mutation();
    return 0;
}
