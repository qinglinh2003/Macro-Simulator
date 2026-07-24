#include "macro_sim/simulation/m5.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numeric>
#include <span>
#include <utility>

#include "macro_sim/algorithms/market.hpp"
#include "macro_sim/algorithms/behavior.hpp"
#include "macro_sim/core/invariants.hpp"

namespace macro_sim::simulation {
namespace {

constexpr double kTolerance = 1.0e-8;
constexpr std::size_t kNoIndex = std::numeric_limits<std::size_t>::max();
constexpr std::uint64_t kM4FiscalCapabilities =
    capability_bit(M4Capability::physical_capital)
    | capability_bit(M4Capability::government);

[[nodiscard]] bool finite(double value) noexcept {
    return std::isfinite(value);
}

template <typename Range>
[[nodiscard]] bool all_finite(const Range& values) noexcept {
    return std::all_of(
        values.begin(),
        values.end(),
        [](double value) { return std::isfinite(value); }
    );
}

[[nodiscard]] std::size_t account_index(AccountId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] std::size_t bank_index(BankId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] std::size_t node_index(SettlementNodeId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] BankId bank_for_node(
    const M5TickScratch& scratch,
    SettlementNodeId node
) noexcept {
    const auto index = node_index(node);
    return index < scratch.bank_by_node_.size()
        ? scratch.bank_by_node_[index]
        : BankId{};
}

[[nodiscard]] core::BankPnlRecord* pnl_for(
    M5TickScratch& scratch,
    BankId bank
) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_pnl_.size()
        ? &scratch.bank_pnl_[index - 1]
        : nullptr;
}

[[nodiscard]] core::BankCapitalRecord* capital_for(
    M5TickScratch& scratch,
    BankId bank
) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_capital_.size()
        ? &scratch.bank_capital_[index - 1]
        : nullptr;
}

[[nodiscard]] const core::BankCapitalRecord* capital_for(
    const M5TickScratch& scratch,
    BankId bank
) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_capital_.size()
        ? &scratch.bank_capital_[index - 1]
        : nullptr;
}

[[nodiscard]] const core::BankComponent* bank_component(
    const core::RootState& state,
    BankId bank
) noexcept {
    return state.banks.get(bank);
}

[[nodiscard]] double projected_balance(
    const M4TickScratch& scratch,
    AccountId account
) noexcept {
    const auto index = account_index(account);
    return index < scratch.balances_.size()
        ? scratch.balances_[index]
        : 0.0;
}

[[nodiscard]] Status move_reserves(
    M4TickScratch& scratch,
    SettlementNodeId source,
    SettlementNodeId destination,
    double amount
) noexcept {
    if (!finite(amount) || amount < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M5 reserve movement must be finite and nonnegative"
        );
    }
    if (amount <= algorithms::kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto source_index = node_index(source);
    const auto destination_index = node_index(destination);
    if (source_index >= scratch.reserve_balances_.size()
        || destination_index >= scratch.reserve_balances_.size()) {
        return Status(
            ErrorCode::not_found,
            "M5 reserve movement references an absent node"
        );
    }
    scratch.reserve_balances_[source_index] -= amount;
    scratch.reserve_balances_[destination_index] += amount;
    scratch.reserve_minimum_[source_index] = std::min(
        scratch.reserve_minimum_[source_index],
        scratch.reserve_balances_[source_index]
    );
    return Status::success();
}

[[nodiscard]] Status transfer(
    const core::RootState& state,
    M4TickScratch& scratch,
    AccountId source,
    AccountId destination,
    double amount
) noexcept {
    if (!finite(amount) || amount < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M5 transfer must be finite and nonnegative"
        );
    }
    if (amount <= algorithms::kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto* source_record = state.postings.get(source);
    const auto* destination_record = state.postings.get(destination);
    if (source_record == nullptr || destination_record == nullptr
        || !source_record->open || !destination_record->open) {
        return Status(ErrorCode::not_found, "M5 transfer account is absent");
    }
    const auto source_index = account_index(source);
    const auto destination_index = account_index(destination);
    if (source_index >= scratch.balances_.size()
        || destination_index >= scratch.balances_.size()) {
        return Status(
            ErrorCode::internal_error,
            "M5 posting projection is stale"
        );
    }
    if (!source_record->allow_negative
        && scratch.balances_[source_index] + kTolerance < amount) {
        return Status(
            ErrorCode::insufficient_funds,
            "M5 transfer exceeds available funds"
        );
    }
    scratch.balances_[source_index] -= amount;
    scratch.balances_[destination_index] += amount;
    const auto reserve_status = move_reserves(
        scratch,
        scratch.account_nodes_[source_index],
        scratch.account_nodes_[destination_index],
        amount
    );
    if (!reserve_status.ok()) {
        scratch.balances_[source_index] += amount;
        scratch.balances_[destination_index] -= amount;
        return reserve_status;
    }
    ++scratch.transfer_count_;
    return Status::success();
}

void refresh_aggregates(
    const core::RootState& state,
    const M4TickScratch& real,
    M5TickScratch& scratch
) {
    std::fill(
        scratch.debt_by_account_.begin(),
        scratch.debt_by_account_.end(),
        0.0
    );
    std::fill(
        scratch.exposure_by_bank_.begin(),
        scratch.exposure_by_bank_.end(),
        0.0
    );
    for (const auto& loan : scratch.loans_) {
        if (!loan.active || loan.principal.value() <= 0.0) {
            continue;
        }
        const auto account = account_index(loan.borrower_account);
        const auto bank = bank_index(loan.lender);
        if (account < scratch.debt_by_account_.size()) {
            scratch.debt_by_account_[account] += loan.principal.value();
        }
        if (bank < scratch.exposure_by_bank_.size()) {
            scratch.exposure_by_bank_[bank] += loan.principal.value();
        }
    }
    std::fill(
        scratch.deposits_by_bank_.begin(),
        scratch.deposits_by_bank_.end(),
        0.0
    );
    state.households.for_each_alive(
        [&real, &scratch](HouseholdId, const core::HouseholdComponent& item) {
            const auto account = account_index(item.primary_account);
            const auto bank = bank_for_node(
                scratch,
                real.account_nodes_[account]
            );
            const auto bank_slot = bank_index(bank);
            if (bank_slot < scratch.deposits_by_bank_.size()) {
                scratch.deposits_by_bank_[bank_slot] +=
                    std::max(0.0, real.balances_[account]);
            }
        }
    );
}

[[nodiscard]] double bank_capacity(
    const core::RootState& state,
    const M5Runtime& runtime,
    const M5TickScratch& scratch,
    BankId bank
) noexcept {
    const auto index = bank_index(bank);
    const auto* component = bank_component(state, bank);
    if (component == nullptr || index >= scratch.bank_alive_.size()
        || scratch.bank_alive_[index] == 0U) {
        return 0.0;
    }
    if (!runtime.policy.bank_capital_constraint
        && !runtime.policy.unified_bank_rwa) {
        return std::numeric_limits<double>::max();
    }
    double leverage = component->leverage_appetite;
    if (runtime.policy.bank_leverage_cap > 0.0) {
        leverage = std::min(leverage, runtime.policy.bank_leverage_cap);
    }
    const double capital = std::max(
        0.0,
        scratch.bank_capital_live_[index]
    );
    return std::max(
        0.0,
        leverage * capital - scratch.exposure_by_bank_[index]
    );
}

[[nodiscard]] BankId relationship_bank(
    const core::RootState& state,
    const M4TickScratch& real,
    const M5TickScratch& scratch,
    AccountId account
) noexcept {
    for (const auto& loan : scratch.loans_) {
        if (loan.active && loan.borrower_account == account
            && loan.principal.value() > algorithms::kEconomicEpsilon) {
            return loan.lender;
        }
    }
    const auto index = account_index(account);
    if (index >= real.account_nodes_.size()) {
        return BankId{};
    }
    const auto bank = bank_for_node(scratch, real.account_nodes_[index]);
    return state.banks.get(bank) != nullptr ? bank : BankId{};
}

[[nodiscard]] Status migrate_account(
    const core::RootState& state,
    M4TickScratch& real,
    M5TickScratch& scratch,
    AccountId account,
    BankId destination,
    bool move_net_deposit
) noexcept {
    const auto* bank = state.banks.get(destination);
    const auto index = account_index(account);
    if (bank == nullptr || index >= real.account_nodes_.size()) {
        return Status(
            ErrorCode::not_found,
            "M5 account migration target is absent"
        );
    }
    const auto old_node = real.account_nodes_[index];
    if (old_node == bank->settlement_node) {
        return Status::success();
    }
    if (move_net_deposit) {
        const double debt = index < scratch.debt_by_account_.size()
            ? scratch.debt_by_account_[index]
            : 0.0;
        const double reserves = std::max(
            0.0,
            real.balances_[index] - debt
        );
        const auto status = move_reserves(
            real,
            old_node,
            bank->settlement_node,
            reserves
        );
        if (!status.ok()) {
            return status;
        }
    }
    real.account_nodes_[index] = bank->settlement_node;
    return Status::success();
}

[[nodiscard]] BankId choose_bank(
    const core::RootState& state,
    const M5Runtime& runtime,
    const M4TickScratch& real,
    M5TickScratch& scratch,
    AccountId account,
    double requested
) {
    const auto incumbent = relationship_bank(state, real, scratch, account);
    if (runtime.rules.relationship_lock_in) {
        for (const auto& loan : scratch.loans_) {
            if (loan.active && loan.borrower_account == account
                && loan.principal.value()
                    > algorithms::kEconomicEpsilon
                && bank_capacity(
                    state,
                    runtime,
                    scratch,
                    incumbent
                ) + kTolerance >= requested) {
                return incumbent;
            }
        }
    }
    if (!runtime.rules.rate_competition
        || state.banks.alive_count() <= 1) {
        return incumbent;
    }
    BankId best = incumbent;
    double best_rate = std::numeric_limits<double>::max();
    const auto* incumbent_component = state.banks.get(incumbent);
    if (incumbent_component != nullptr
        && bank_capacity(state, runtime, scratch, incumbent) + kTolerance
            >= requested) {
        best_rate = std::max(
            0.0,
            runtime.policy_rate + incumbent_component->loan_spread
        );
    }
    scratch.candidate_banks_.clear();
    state.banks.for_each_alive(
        [&scratch](BankId id, const core::BankComponent& bank) {
            if (bank.alive) {
                scratch.candidate_banks_.push_back(
                    static_cast<std::size_t>(id.value())
                );
            }
        }
    );
    if (scratch.candidate_banks_.empty()) {
        return BankId{};
    }
    const auto limit = std::min<std::size_t>(
        scratch.candidate_banks_.size(),
        std::max<std::size_t>(1, runtime.rules.bank_search_count + 1)
    );
    const auto start = account.value() % scratch.candidate_banks_.size();
    for (std::size_t offset = 0; offset < limit; ++offset) {
        const auto raw = scratch.candidate_banks_[
            (start + offset) % scratch.candidate_banks_.size()
        ];
        const BankId candidate(raw);
        if (bank_capacity(state, runtime, scratch, candidate) + kTolerance
            < requested) {
            continue;
        }
        const auto* component = state.banks.get(candidate);
        const double rate = std::max(
            0.0,
            runtime.policy_rate + component->loan_spread
        );
        if (rate < best_rate - algorithms::kEconomicEpsilon
            || (std::abs(rate - best_rate)
                    <= algorithms::kEconomicEpsilon
                && candidate < best)) {
            best = candidate;
            best_rate = rate;
        }
    }
    return best;
}

[[nodiscard]] double grant_credit(
    const core::RootState& state,
    M4TickScratch& real,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    AccountId account,
    double requested,
    double borrower_limit,
    Tick tick
) {
    if (requested <= algorithms::kEconomicEpsilon
        || borrower_limit <= algorithms::kEconomicEpsilon) {
        return 0.0;
    }
    const auto account_slot = account_index(account);
    const double existing = scratch.debt_by_account_[account_slot];
    const auto lender = choose_bank(
        state,
        runtime,
        real,
        scratch,
        account,
        std::min(requested, borrower_limit)
    );
    if (!lender.valid()) {
        return 0.0;
    }
    double room = bank_capacity(state, runtime, scratch, lender);
    if (runtime.policy.bank_exposure_limit > 0.0) {
        const auto bank_slot = bank_index(lender);
        const double capital = std::max(
            0.0,
            scratch.bank_capital_live_[bank_slot]
        );
        room = std::min(
            room,
            runtime.policy.bank_exposure_limit * capital - existing
        );
    }
    const double granted = std::min(
        {requested, borrower_limit, std::max(0.0, room)}
    );
    if (granted <= algorithms::kEconomicEpsilon) {
        return 0.0;
    }
    if (existing <= algorithms::kEconomicEpsilon) {
        const auto status = migrate_account(
            state,
            real,
            scratch,
            account,
            lender,
            true
        );
        if (!status.ok()) {
            return 0.0;
        }
    }
    real.balances_[account_slot] += granted;
    const auto* account_record = state.postings.get(account);
    const auto* bank = state.banks.get(lender);
    scratch.loans_.push_back(
        {
            LoanId(scratch.loans_.size() + 1),
            lender,
            account_record->key.owner,
            account,
            Money(granted),
            0.0,
            {
                Rate(std::max(
                    0.0,
                    runtime.policy_rate + bank->loan_spread
                )),
                tick,
                Tick(tick.value() + 3650),
            },
            true,
        }
    );
    scratch.debt_by_account_[account_slot] += granted;
    scratch.exposure_by_bank_[bank_index(lender)] += granted;
    scratch.working_metrics_.new_credit += granted;
    return granted;
}

[[nodiscard]] Status set_policy_rate(
    M5Runtime& runtime
) noexcept {
    const auto& policy = runtime.policy;
    if (policy.monetary_regime != MonetaryRegime::exogenous) {
        double inflation = 0.0;
        if (runtime.previous_price_index > algorithms::kEconomicEpsilon
            && runtime.last_metrics.economy.price_index
                > algorithms::kEconomicEpsilon) {
            inflation =
                runtime.last_metrics.economy.price_index
                    / runtime.previous_price_index
                - 1.0;
        }
        runtime.inflation_sensor +=
            policy.inflation_sensor_lambda
            * (inflation - runtime.inflation_sensor);
    }
    switch (policy.monetary_regime) {
        case MonetaryRegime::exogenous:
            runtime.policy_rate = runtime.initial_policy_rate;
            break;
        case MonetaryRegime::manual:
            runtime.policy_rate = std::clamp(
                *policy.manual_policy_rate,
                0.0,
                policy.maximum_policy_rate
            );
            break;
        case MonetaryRegime::taylor: {
            const double target =
                policy.neutral_rate
                + policy.taylor_inflation
                    * (runtime.inflation_sensor
                        - policy.inflation_target)
                - policy.taylor_unemployment
                    * (runtime.previous_unemployment
                        - policy.natural_unemployment);
            runtime.policy_rate = std::clamp(
                policy.rate_inertia * runtime.policy_rate
                    + (1.0 - policy.rate_inertia) * target,
                0.0,
                policy.maximum_policy_rate
            );
            break;
        }
    }
    return Status::success();
}

void apply_fiscal_policy(
    M4Runtime& real,
    const M5Runtime& runtime
) noexcept {
    real.rules.government_consumption_share =
        runtime.policy.government_consumption_share;
    real.rules.government_deficit_target =
        runtime.policy.government_deficit_target;
    real.rules.deficit_unemployment_reference =
        runtime.policy.deficit_unemployment_reference;
    real.rules.deficit_unemployment_cap =
        runtime.policy.deficit_unemployment_cap;
    real.rules.government_investment_share =
        runtime.policy.government_investment_share;
    real.rules.profit_tax_rate = runtime.policy.profit_tax_rate;
    real.rules.income_tax_rate = runtime.policy.income_tax_rate;
    real.rules.income_allowance = runtime.policy.income_allowance;
    real.rules.consumption_tax_rate =
        runtime.policy.consumption_tax_rate;
    real.rules.wealth_tax_rate = runtime.policy.wealth_tax_rate;
    real.rules.wealth_allowance = runtime.policy.wealth_allowance;
    real.rules.unemployment_benefit_replacement =
        runtime.policy.unemployment_benefit_replacement;
    real.rules.benefit_income_floor =
        runtime.policy.benefit_income_floor;
    real.rules.minimum_wage = runtime.policy.minimum_wage;
    real.rules.job_guarantee = runtime.policy.job_guarantee;
    real.rules.job_guarantee_wage_ratio =
        runtime.policy.job_guarantee_wage_ratio;
    real.rules.job_guarantee_public_works_share =
        runtime.policy.job_guarantee_public_works_share;
}

void open_financial_books(
    const core::RootState& state,
    const M4TickScratch& real,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    Tick tick
) {
    scratch.loans_ = state.loans.records();
    scratch.interbank_ = state.interbank.records();
    scratch.central_bank_operations_ =
        state.central_bank_operations.records();
    scratch.bank_pnl_ = state.bank_pnl.records();
    scratch.bank_capital_ = state.bank_capital.records();
    scratch.reserve_stock_ = state.reserves.reserve_stock().value();
    scratch.working_metrics_ = {};
    scratch.working_metrics_.policy_rate = runtime.policy_rate;
    scratch.working_metrics_.inflation_sensor =
        runtime.inflation_sensor;
    std::fill(
        scratch.bank_alive_.begin(),
        scratch.bank_alive_.end(),
        0U
    );
    state.banks.for_each_alive(
        [&real, &scratch, tick](
            BankId id,
            const core::BankComponent& bank
        ) {
            const auto index = bank_index(id);
            scratch.bank_alive_[index] = bank.alive ? 1U : 0U;
            const double cash = projected_balance(real, bank.cash_account);
            scratch.bank_capital_live_[index] = cash;
            auto* pnl = pnl_for(scratch, id);
            *pnl = core::BankPnlRecord{id, tick};
            auto* capital = capital_for(scratch, id);
            capital->opening_capital = cash;
            capital->closing_capital = cash;
            capital->alive = bank.alive;
        }
    );
    refresh_aggregates(state, real, scratch);
}

[[nodiscard]] Status run_deposit_competition(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch
) {
    if (!runtime.rules.interbank
        || runtime.rules.deposit_spread_dispersion <= 0.0
        || state.banks.alive_count() <= 1) {
        return Status::success();
    }
    refresh_aggregates(state, real, scratch);
    double total = std::accumulate(
        scratch.deposits_by_bank_.begin(),
        scratch.deposits_by_bank_.end(),
        0.0
    );
    total = std::max(1.0, total);
    state.households.for_each_alive(
        [&state, &runtime, &real, &scratch, total](
            HouseholdId,
            const core::HouseholdComponent& household
        ) {
            const auto account = account_index(household.primary_account);
            if (scratch.debt_by_account_[account]
                > algorithms::kEconomicEpsilon) {
                return;
            }
            const auto current = bank_for_node(
                scratch,
                real.account_nodes_[account]
            );
            BankId best = current;
            const auto effective = [&state, &runtime, &scratch, total](
                                       BankId bank) {
                const auto* component = state.banks.get(bank);
                const auto index = bank_index(bank);
                const double congestion =
                    runtime.rules.deposit_spread_dispersion
                    * static_cast<double>(state.banks.alive_count())
                    * scratch.deposits_by_bank_[index] / total;
                return component->deposit_spread - congestion;
            };
            double best_rate = effective(current);
            std::size_t visited = 0;
            state.banks.for_each_alive(
                [&best, &best_rate, &visited, &runtime, &effective](
                    BankId candidate,
                    const core::BankComponent& bank
                ) {
                    if (!bank.alive
                        || visited >= runtime.rules.deposit_search_count) {
                        return;
                    }
                    ++visited;
                    const double rate = effective(candidate);
                    if (rate > best_rate + algorithms::kEconomicEpsilon
                        || (std::abs(rate - best_rate)
                                <= algorithms::kEconomicEpsilon
                            && candidate < best)) {
                        best = candidate;
                        best_rate = rate;
                    }
                }
            );
            if (best != current) {
                static_cast<void>(migrate_account(
                    state,
                    real,
                    scratch,
                    household.primary_account,
                    best,
                    true
                ));
            }
        }
    );
    refresh_aggregates(state, real, scratch);
    return Status::success();
}

void add_cb_operation(
    M5TickScratch& scratch,
    core::CentralBankOperationKind kind,
    BankId bank,
    double amount,
    double rate,
    Tick tick
) {
    for (auto& operation : scratch.central_bank_operations_) {
        if (operation.active && operation.kind == kind
            && operation.counterparty == bank) {
            operation.principal = Money(
                operation.principal.value() + amount
            );
            operation.rate = Rate(rate);
            operation.maturity_tick = Tick(tick.value() + 1);
            return;
        }
    }
    scratch.central_bank_operations_.push_back(
        {
            CentralBankOperationId(
                scratch.central_bank_operations_.size() + 1
            ),
            kind,
            bank,
            Money(amount),
            Rate(rate),
            tick,
            Tick(tick.value() + 1),
            true,
        }
    );
}

[[nodiscard]] Status run_omo(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    Tick tick
) {
    if (!runtime.policy.open_market_operations
        || !runtime.rules.interbank) {
        return Status::success();
    }
    double target = runtime.policy.reserve_target
        * runtime.reserve_genesis;
    if (runtime.policy.reserve_target_indexes_deposits) {
        double deposits = 0.0;
        for (const auto& account : state.postings.records()) {
            if (account.key.kind == core::AccountKind::deposit) {
                deposits += std::max(
                    0.0,
                    real.balances_[account_index(account.id)]
                );
            }
        }
        target =
            runtime.policy.reserve_target
            * runtime.policy.reserve_floor_fraction
            * deposits;
    }
    double current = 0.0;
    state.banks.for_each_alive(
        [&real, &scratch, &current](
            BankId id,
            const core::BankComponent& bank
        ) {
            if (bank.alive && scratch.bank_alive_[bank_index(id)] != 0U) {
                current += real.reserve_balances_[
                    node_index(bank.settlement_node)
                ];
            }
        }
    );
    const double move =
        runtime.policy.reserve_gap_close * (current - target);
    if (move > algorithms::kEconomicEpsilon) {
        double positive = 0.0;
        state.banks.for_each_alive(
            [&real, &positive](BankId, const core::BankComponent& bank) {
                positive += std::max(
                    0.0,
                    real.reserve_balances_[
                        node_index(bank.settlement_node)
                    ]
                );
            }
        );
        if (positive <= algorithms::kEconomicEpsilon) {
            return Status::success();
        }
        double drained = 0.0;
        state.banks.for_each_alive(
            [&real,
             &scratch,
             &runtime,
             tick,
             move,
             positive,
             &drained](
                BankId id,
                const core::BankComponent& bank
            ) {
                const auto node = node_index(bank.settlement_node);
                const double available =
                    std::max(0.0, real.reserve_balances_[node]);
                const double amount = std::min(
                    available,
                    move * available / positive
                );
                real.reserve_balances_[node] -= amount;
                scratch.reserve_stock_ -= amount;
                add_cb_operation(
                    scratch,
                    core::CentralBankOperationKind::reserve_absorption,
                    id,
                    amount,
                    runtime.policy_rate,
                    tick
                );
                drained += amount;
            }
        );
        scratch.working_metrics_.omo_flow = drained;
    } else if (move < -algorithms::kEconomicEpsilon) {
        double outstanding = 0.0;
        for (const auto& operation : scratch.central_bank_operations_) {
            if (operation.active
                && operation.kind
                    == core::CentralBankOperationKind::reserve_absorption) {
                outstanding += operation.principal.value();
            }
        }
        double remaining = std::min(-move, outstanding);
        for (auto& operation : scratch.central_bank_operations_) {
            if (remaining <= algorithms::kEconomicEpsilon) {
                break;
            }
            if (!operation.active
                || operation.kind
                    != core::CentralBankOperationKind::reserve_absorption) {
                continue;
            }
            const auto* bank = state.banks.get(operation.counterparty);
            if (bank == nullptr
                || scratch.bank_alive_[bank_index(operation.counterparty)]
                    == 0U) {
                continue;
            }
            const double amount = std::min(
                remaining,
                operation.principal.value()
            );
            real.reserve_balances_[
                node_index(bank->settlement_node)
            ] += amount;
            scratch.reserve_stock_ += amount;
            operation.principal = Money(
                operation.principal.value() - amount
            );
            operation.active =
                operation.principal.value()
                    > algorithms::kEconomicEpsilon;
            remaining -= amount;
            scratch.working_metrics_.omo_flow -= amount;
        }
    }
    return Status::success();
}

[[nodiscard]] Status run_credit(
    const core::RootState& state,
    M4Runtime& real_runtime,
    M4TickScratch& real,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    Tick tick
) {
    const double capital_price =
        real_runtime.rules.initial_capital_price;
    for (std::size_t index = 0; index < real.firm_ids_.size(); ++index) {
        const auto* firm = state.firms.get(real.firm_ids_[index]);
        auto& work = real.firm_work_[index];
        const auto account = account_index(firm->primary_account);
        const double debt = scratch.debt_by_account_[account];
        const double cash = real.balances_[account];
        const double request = std::max(
            0.0,
            work.posted_wage * work.labor_demand_notional
                + capital_price * work.investment_target
                - cash
        );
        const double net_worth = std::max(
            0.0,
            cash
                + 0.5 * work.closing_inventory * work.posted_price
                + 0.7 * work.closing_capital * capital_price
                - debt
        );
        double room = std::max(
            0.0,
            runtime.policy.firm_leverage_limit * net_worth - debt
        );
        if (runtime.rules.direct_monetary_transmission
            && runtime.policy.firm_minimum_dscr > 0.0) {
            const double operating_cash = std::max(
                0.0,
                work.posted_price * work.demand_expected
                    - work.posted_wage
                        * work.labor_demand_notional
            );
            const double service_rate =
                runtime.policy_rate
                + runtime.rules.firm_amortization;
            if (service_rate > algorithms::kEconomicEpsilon) {
                room = std::min(
                    room,
                    operating_cash
                        / (
                            runtime.policy.firm_minimum_dscr
                            * service_rate
                        )
                );
            }
        }
        static_cast<void>(grant_credit(
            state,
            real,
            runtime,
            scratch,
            firm->primary_account,
            request,
            room,
            tick
        ));
        work.labor_demand_effective = std::max(
            0.0,
            std::min(
                work.labor_demand_notional,
                real.balances_[account] / work.posted_wage
            )
        );
    }
    if (runtime.rules.household_credit) {
        for (std::size_t index = 0;
             index < real.household_ids_.size();
             ++index) {
            const auto* household =
                state.households.get(real.household_ids_[index]);
            const auto account = account_index(
                household->primary_account
            );
            const double debt = scratch.debt_by_account_[account];
            const double requested = std::max(
                0.0,
                real.household_work_[index].consumption_budget
                    - real.balances_[account]
            );
            const double income = std::max(
                {
                    household->income_expected,
                    real.household_work_[index].income_expected,
                    runtime.rules.household_subsistence,
                }
            );
            const double room = std::max(
                0.0,
                runtime.policy.household_credit_limit * income - debt
            );
            static_cast<void>(grant_credit(
                state,
                real,
                runtime,
                scratch,
                household->primary_account,
                requested,
                room,
                tick
            ));
        }
    }
    refresh_aggregates(state, real, scratch);
    return Status::success();
}

[[nodiscard]] Status service_debt(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    bool full_pnl
) {
    for (auto& loan : scratch.loans_) {
        if (!loan.active
            || loan.principal.value() <= algorithms::kEconomicEpsilon) {
            continue;
        }
        const auto* account_record =
            state.postings.get(loan.borrower_account);
        const auto* lender = state.banks.get(loan.lender);
        if (account_record == nullptr || lender == nullptr) {
            return Status(
                ErrorCode::invariant_violation,
                "M5 debt service references an absent owner"
            );
        }
        const auto account = account_index(loan.borrower_account);
        const double amortization =
            account_record->key.owner.kind == core::OwnerKind::household
            ? runtime.rules.household_amortization
            : runtime.rules.firm_amortization;
        const double interest_due =
            loan.terms.annual_rate.value() * loan.principal.value();
        double interest = 0.0;
        double principal = 0.0;
        if (full_pnl) {
            interest = std::min(
                interest_due,
                std::max(0.0, real.balances_[account])
            );
            principal = std::min(
                amortization * loan.principal.value(),
                std::max(0.0, real.balances_[account] - interest)
            );
        } else {
            principal = std::min(
                amortization * loan.principal.value(),
                std::max(0.0, real.balances_[account])
            );
            interest = std::min(
                interest_due,
                std::max(0.0, real.balances_[account] - principal)
            );
        }
        if (interest > algorithms::kEconomicEpsilon) {
            const auto status = transfer(
                state,
                real,
                loan.borrower_account,
                lender->cash_account,
                interest
            );
            if (!status.ok()) {
                return status;
            }
            pnl_for(scratch, loan.lender)->loan_interest += interest;
            scratch.working_metrics_.loan_interest_paid += interest;
            if (account_record->key.owner.kind
                == core::OwnerKind::household) {
                scratch.working_metrics_.household_interest_paid
                    += interest;
            } else if (full_pnl) {
                const auto firm_id =
                    static_cast<std::size_t>(
                        account_record->key.owner.value
                    );
                if (firm_id < scratch.firm_index_by_id_.size()) {
                    const auto firm_index =
                        scratch.firm_index_by_id_[firm_id];
                    if (firm_index != kNoIndex) {
                        real.firm_work_[firm_index].wage_bill += interest;
                    }
                }
            }
        }
        if (principal > algorithms::kEconomicEpsilon) {
            real.balances_[account] -= principal;
            loan.principal = Money(
                loan.principal.value() - principal
            );
            if (loan.principal.value()
                <= algorithms::kEconomicEpsilon) {
                loan.principal = Money(0.0);
                loan.active = false;
            }
            scratch.working_metrics_.principal_repaid += principal;
        }
    }
    refresh_aggregates(state, real, scratch);
    return Status::success();
}

[[nodiscard]] core::InterbankRecord* find_interbank(
    M5TickScratch& scratch,
    BankId lender,
    BankId borrower
) noexcept {
    for (auto& record : scratch.interbank_) {
        if (record.active && record.lender == lender
            && record.borrower == borrower) {
            return &record;
        }
    }
    return nullptr;
}

void add_interbank(
    M5TickScratch& scratch,
    BankId lender,
    BankId borrower,
    double principal,
    double rate,
    Tick tick
) {
    if (auto* record = find_interbank(scratch, lender, borrower);
        record != nullptr) {
        const double old = record->principal.value();
        const double total = old + principal;
        record->rate = Rate(
            total > 0.0
            ? (old * record->rate.value() + principal * rate) / total
            : 0.0
        );
        record->principal = Money(total);
        record->maturity_tick = Tick(tick.value() + 1);
        return;
    }
    scratch.interbank_.push_back(
        {
            InterbankContractId(scratch.interbank_.size() + 1),
            lender,
            borrower,
            Money(principal),
            Rate(rate),
            Money(0.0),
            tick,
            Tick(tick.value() + 1),
            true,
        }
    );
}

[[nodiscard]] Status default_interbank_borrower(
    const core::RootState& state,
    M4TickScratch& real,
    M5TickScratch& scratch,
    BankId borrower
) {
    const auto* borrower_bank = state.banks.get(borrower);
    for (auto& record : scratch.interbank_) {
        if (!record.active || record.borrower != borrower) {
            continue;
        }
        const auto* lender = state.banks.get(record.lender);
        const double principal = record.principal.value();
        real.balances_[account_index(lender->cash_account)] -= principal;
        real.balances_[account_index(borrower_bank->cash_account)]
            += principal;
        pnl_for(scratch, record.lender)
            ->realized_interbank_losses += principal;
        pnl_for(scratch, borrower)->resolution_flow += principal;
        record.principal = Money(0.0);
        record.accrued_interest = Money(0.0);
        record.active = false;
    }
    return Status::success();
}

[[nodiscard]] Status run_interbank(
    const core::RootState& state,
    M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    Tick tick
) {
    scratch.working_metrics_.interbank_rate = runtime.policy_rate;
    if (!runtime.rules.interbank || state.banks.alive_count() <= 1) {
        return Status::success();
    }
    for (auto& record : scratch.interbank_) {
        if (!record.active || record.maturity_tick > tick) {
            continue;
        }
        if (scratch.bank_alive_[bank_index(record.borrower)] == 0U) {
            continue;
        }
        const auto* lender = state.banks.get(record.lender);
        const auto* borrower = state.banks.get(record.borrower);
        const auto borrower_node = node_index(borrower->settlement_node);
        const double due =
            record.accrued_interest.value()
            + record.principal.value() * record.rate.value();
        const double interest = std::min(
            {
                due,
                std::max(
                    0.0,
                    real.balances_[
                        account_index(borrower->cash_account)
                    ]
                ),
                std::max(0.0, real.reserve_balances_[borrower_node]),
            }
        );
        if (interest > algorithms::kEconomicEpsilon) {
            const auto status = transfer(
                state,
                real,
                borrower->cash_account,
                lender->cash_account,
                interest
            );
            if (!status.ok()) {
                return status;
            }
            pnl_for(scratch, record.borrower)
                ->interbank_interest_expense += interest;
            pnl_for(scratch, record.lender)
                ->interbank_interest_income += interest;
        }
        const double principal = std::min(
            record.principal.value(),
            std::max(0.0, real.reserve_balances_[borrower_node])
        );
        if (principal > algorithms::kEconomicEpsilon) {
            const auto status = move_reserves(
                real,
                borrower->settlement_node,
                lender->settlement_node,
                principal
            );
            if (!status.ok()) {
                return status;
            }
        }
        record.principal = Money(
            record.principal.value() - principal
        );
        record.accrued_interest = Money(
            std::max(0.0, due - interest)
        );
        record.active =
            record.principal.value() > algorithms::kEconomicEpsilon
            || record.accrued_interest.value()
                > algorithms::kEconomicEpsilon;
        record.maturity_tick = Tick(tick.value() + 1);
    }
    double deficit = 0.0;
    double surplus = 0.0;
    state.banks.for_each_alive(
        [&real, &scratch, &deficit, &surplus](
            BankId id,
            const core::BankComponent& bank
        ) {
            if (!bank.alive || scratch.bank_alive_[bank_index(id)] == 0U) {
                return;
            }
            const double reserve = real.reserve_balances_[
                node_index(bank.settlement_node)
            ];
            deficit += std::max(0.0, -reserve);
            surplus += std::max(0.0, reserve);
        }
    );
    if (deficit <= algorithms::kEconomicEpsilon
        || surplus <= algorithms::kEconomicEpsilon) {
        return Status::success();
    }
    const double tightness = std::min(1.0, deficit / surplus);
    const double rate = std::max(
        0.0,
        runtime.policy_rate
            + runtime.rules.interbank_rate_base
            + runtime.rules.interbank_tightness * tightness
    );
    scratch.working_metrics_.interbank_rate = rate;
    double remaining_supply = surplus;
    state.banks.for_each_alive(
        [&state,
         &real,
         &scratch,
         tick,
         rate,
         deficit,
         surplus,
         &remaining_supply](
            BankId borrower_id,
            const core::BankComponent& borrower
        ) {
            const auto borrower_node =
                node_index(borrower.settlement_node);
            const double need = std::max(
                0.0,
                -real.reserve_balances_[borrower_node]
            );
            double funding = std::min(
                need,
                std::min(deficit, surplus) * need / deficit
            );
            state.banks.for_each_alive(
                [&real,
                 &scratch,
                 tick,
                 rate,
                 borrower_id,
                 &borrower,
                 &funding,
                 &remaining_supply](
                    BankId lender_id,
                    const core::BankComponent& lender
                ) {
                    if (funding <= algorithms::kEconomicEpsilon
                        || remaining_supply
                            <= algorithms::kEconomicEpsilon
                        || lender_id == borrower_id) {
                        return;
                    }
                    const auto lender_node =
                        node_index(lender.settlement_node);
                    const double available = std::max(
                        0.0,
                        real.reserve_balances_[lender_node]
                    );
                    const double amount = std::min(funding, available);
                    if (amount <= algorithms::kEconomicEpsilon) {
                        return;
                    }
                    static_cast<void>(move_reserves(
                        real,
                        lender.settlement_node,
                        borrower.settlement_node,
                        amount
                    ));
                    add_interbank(
                        scratch,
                        lender_id,
                        borrower_id,
                        amount,
                        rate,
                        tick
                    );
                    scratch.working_metrics_.interbank_volume += amount;
                    funding -= amount;
                    remaining_supply -= amount;
                }
            );
        }
    );
    return Status::success();
}

[[nodiscard]] double bank_health(
    const core::RootState& state,
    const M5Runtime& runtime,
    const M5TickScratch& scratch,
    BankId bank
) noexcept {
    const auto index = bank_index(bank);
    const double exposure = scratch.exposure_by_bank_[index];
    if (exposure <= algorithms::kEconomicEpsilon) {
        return 1.0;
    }
    const auto* component = state.banks.get(bank);
    const double capital = std::max(
        0.0,
        scratch.bank_capital_live_[index]
    );
    static_cast<void>(component);
    return std::min(
        1.0,
        (capital / exposure)
            / std::max(
                algorithms::kEconomicEpsilon,
                runtime.rules.run_health_reference
            )
    );
}

void add_lolr(
    M5Runtime& runtime,
    M5TickScratch& scratch,
    M4TickScratch& real,
    const core::BankComponent& bank,
    BankId bank_id,
    double amount,
    Tick tick
) {
    real.reserve_balances_[node_index(bank.settlement_node)] += amount;
    scratch.reserve_stock_ += amount;
    add_cb_operation(
        scratch,
        core::CentralBankOperationKind::lender_of_last_resort,
        bank_id,
        amount,
        runtime.policy_rate,
        tick
    );
    scratch.working_metrics_.lolr_advances += amount;
}

[[nodiscard]] Status resolve_bank(
    const core::RootState& state,
    M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    BankId failed
) {
    const auto failed_index = bank_index(failed);
    if (scratch.bank_alive_[failed_index] == 0U) {
        return Status::success();
    }
    scratch.bank_alive_[failed_index] = 0U;
    ++scratch.working_metrics_.bank_failures;
    auto* failed_capital = capital_for(scratch, failed);
    failed_capital->alive = false;
    failed_capital->resolved = true;
    auto status = default_interbank_borrower(
        state,
        real,
        scratch,
        failed
    );
    if (!status.ok()) {
        return status;
    }
    scratch.alive_banks_.clear();
    state.banks.for_each_alive(
        [&scratch](BankId id, const core::BankComponent&) {
            if (scratch.bank_alive_[bank_index(id)] != 0U) {
                scratch.alive_banks_.push_back(id);
            }
        }
    );
    for (auto& record : scratch.interbank_) {
        if (!record.active || record.lender != failed) {
            continue;
        }
        if (scratch.alive_banks_.empty()) {
            record.active = false;
            record.principal = Money(0.0);
            record.accrued_interest = Money(0.0);
            continue;
        }
        const auto receiver_it = std::find_if(
            scratch.alive_banks_.begin(),
            scratch.alive_banks_.end(),
            [&record](BankId candidate) {
                return candidate != record.borrower;
            }
        );
        const auto receiver = receiver_it != scratch.alive_banks_.end()
            ? *receiver_it
            : scratch.alive_banks_.front();
        if (receiver == record.borrower) {
            record.active = false;
            record.principal = Money(0.0);
            record.accrued_interest = Money(0.0);
            continue;
        }
        const auto* failed_bank = state.banks.get(failed);
        const auto* receiver_bank = state.banks.get(receiver);
        const double principal = record.principal.value();
        real.balances_[account_index(failed_bank->cash_account)]
            -= principal;
        real.balances_[account_index(receiver_bank->cash_account)]
            += principal;
        pnl_for(scratch, failed)->resolution_flow -= principal;
        pnl_for(scratch, receiver)->resolution_flow += principal;
        record.lender = receiver;
    }
    if (runtime.policy.migrate_relationships_on_failure
        && !scratch.alive_banks_.empty()) {
        std::size_t next = 0;
        for (auto& account : state.postings.records()) {
            const auto index = account_index(account.id);
            if (account.id
                    == state.banks.get(failed)->cash_account
                || real.account_nodes_[index]
                    != state.banks.get(failed)->settlement_node) {
                continue;
            }
            const auto target = scratch.alive_banks_[
                next++ % scratch.alive_banks_.size()
            ];
            status = migrate_account(
                state,
                real,
                scratch,
                account.id,
                target,
                true
            );
            if (!status.ok()) {
                return status;
            }
        }
        next = 0;
        for (auto& loan : scratch.loans_) {
            if (loan.active && loan.lender == failed) {
                loan.lender = scratch.alive_banks_[
                    next++ % scratch.alive_banks_.size()
                ];
            }
        }
    }
    const auto* failed_bank = state.banks.get(failed);
    const auto failed_account = account_index(failed_bank->cash_account);
    if (real.balances_[failed_account]
            > algorithms::kEconomicEpsilon) {
        AccountId receiver_account =
            state.institutions.treasury_account;
        BankId receiver_bank{};
        if (!scratch.alive_banks_.empty()) {
            receiver_bank = scratch.alive_banks_.front();
            receiver_account =
                state.banks.get(receiver_bank)->cash_account;
        }
        const double amount = real.balances_[failed_account];
        status = transfer(
            state,
            real,
            failed_bank->cash_account,
            receiver_account,
            amount
        );
        if (!status.ok()) {
            return status;
        }
        pnl_for(scratch, failed)->resolution_flow -= amount;
        if (receiver_bank.valid()) {
            pnl_for(scratch, receiver_bank)->resolution_flow += amount;
        }
    }
    double hole = std::max(0.0, -real.balances_[failed_account]);
    if (hole > algorithms::kEconomicEpsilon
        && runtime.policy.state_resolution_backstop
        && state.institutions.treasury_account.valid()) {
        status = transfer(
            state,
            real,
            state.institutions.treasury_account,
            failed_bank->cash_account,
            hole
        );
        if (!status.ok()) {
            return status;
        }
        pnl_for(scratch, failed)->resolution_flow += hole;
        scratch.working_metrics_.resolution_cost += hole;
    } else if (hole > algorithms::kEconomicEpsilon
        && !scratch.alive_banks_.empty()) {
        double available = 0.0;
        for (const auto bank : scratch.alive_banks_) {
            const auto* component = state.banks.get(bank);
            available += std::max(
                0.0,
                real.reserve_balances_[
                    node_index(component->settlement_node)
                ]
            );
        }
        for (const auto bank : scratch.alive_banks_) {
            if (hole <= algorithms::kEconomicEpsilon
                || available <= algorithms::kEconomicEpsilon) {
                break;
            }
            const auto* component = state.banks.get(bank);
            const double reserve = std::max(
                0.0,
                real.reserve_balances_[
                    node_index(component->settlement_node)
                ]
            );
            const double amount = std::min(
                hole,
                hole * reserve / available
            );
            status = transfer(
                state,
                real,
                component->cash_account,
                failed_bank->cash_account,
                amount
            );
            if (!status.ok()) {
                return status;
            }
            pnl_for(scratch, bank)->resolution_flow -= amount;
            pnl_for(scratch, failed)->resolution_flow += amount;
            hole -= amount;
        }
    }
    refresh_aggregates(state, real, scratch);
    return Status::success();
}

[[nodiscard]] Status force_default(
    const core::RootState& state,
    M4TickScratch& real,
    M5TickScratch& scratch,
    AccountId account
) {
    for (auto& loan : scratch.loans_) {
        if (!loan.active || loan.borrower_account != account) {
            continue;
        }
        const auto* bank = state.banks.get(loan.lender);
        const double loss = loan.principal.value();
        real.balances_[account_index(bank->cash_account)] -= loss;
        pnl_for(scratch, loan.lender)->realized_loan_losses += loss;
        scratch.working_metrics_.realized_credit_losses += loss;
        loan.principal = Money(0.0);
        loan.active = false;
    }
    refresh_aggregates(state, real, scratch);
    return Status::success();
}

[[nodiscard]] Status run_bank_runs(
    const core::RootState& state,
    M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    Tick tick,
    PhiloxRng& rng,
    std::optional<BankId> forced
) {
    if ((!runtime.rules.bank_runs && !forced.has_value())
        || !runtime.rules.interbank
        || state.banks.alive_count() <= 1) {
        return Status::success();
    }
    runtime.bank_fear *= runtime.rules.run_fear_persistence;
    BankId safe{};
    double safest = -1.0;
    state.banks.for_each_alive(
        [&state, &runtime, &scratch, &safe, &safest](
            BankId id,
            const core::BankComponent& bank
        ) {
            if (!bank.alive || scratch.bank_alive_[bank_index(id)] == 0U) {
                return;
            }
            const double health = bank_health(
                state,
                runtime,
                scratch,
                id
            );
            if (health > safest
                || (std::abs(health - safest)
                        <= algorithms::kEconomicEpsilon
                    && id < safe)) {
                safe = id;
                safest = health;
            }
        }
    );
    if (!safe.valid()) {
        return Status::success();
    }
    scratch.failed_banks_.clear();
    state.banks.for_each_alive(
        [&state,
         &runtime,
         &real,
         &scratch,
         tick,
         &rng,
         forced,
         safe](
            BankId id,
            const core::BankComponent& bank
        ) {
            if (id == safe || !bank.alive
                || scratch.bank_alive_[bank_index(id)] == 0U) {
                return;
            }
            const double health = bank_health(
                state,
                runtime,
                scratch,
                id
            );
            const double pressure = std::max(0.0, 0.5 - health);
            const double intensity = forced == id
                ? 1.0
                : std::min(
                    1.0,
                    runtime.rules.run_sensitivity * pressure
                        + runtime.bank_fear
                );
            if (intensity <= algorithms::kEconomicEpsilon) {
                return;
            }
            scratch.household_order_.clear();
            for (std::size_t index = 0;
                 index < real.household_ids_.size();
                 ++index) {
                const auto* household =
                    state.households.get(real.household_ids_[index]);
                const auto account =
                    account_index(household->primary_account);
                if (real.account_nodes_[account]
                        == bank.settlement_node
                    && scratch.debt_by_account_[account]
                        <= algorithms::kEconomicEpsilon
                    && rng.uniform_closed_open() < intensity) {
                    scratch.household_order_.push_back(index);
                }
            }
            static_cast<void>(rng.shuffle(
                std::span(scratch.household_order_)
            ));
            bool suspended = false;
            for (const auto index : scratch.household_order_) {
                const auto* household =
                    state.households.get(real.household_ids_[index]);
                const auto account =
                    account_index(household->primary_account);
                const double withdrawal =
                    std::max(0.0, real.balances_[account]);
                auto& reserves = real.reserve_balances_[
                    node_index(bank.settlement_node)
                ];
                if (reserves + kTolerance < withdrawal
                    && runtime.policy.lender_of_last_resort
                    && scratch.bank_capital_live_[bank_index(id)] > 0.0) {
                    add_lolr(
                        runtime,
                        scratch,
                        real,
                        bank,
                        id,
                        withdrawal - reserves,
                        tick
                    );
                }
                if (reserves + kTolerance >= withdrawal) {
                    static_cast<void>(migrate_account(
                        state,
                        real,
                        scratch,
                        household->primary_account,
                        safe,
                        true
                    ));
                    scratch.working_metrics_.run_flight_volume
                        += withdrawal;
                } else {
                    suspended = true;
                    break;
                }
            }
            if (suspended) {
                scratch.failed_banks_.push_back(id);
                runtime.bank_fear = std::min(
                    1.0,
                    runtime.bank_fear + 0.25
                );
            } else if (!scratch.household_order_.empty()) {
                runtime.bank_fear = std::min(
                    1.0,
                    runtime.bank_fear
                        + 0.02
                            * static_cast<double>(
                                scratch.household_order_.size()
                            )
                            / static_cast<double>(
                                std::max<std::size_t>(
                                    1,
                                    real.household_ids_.size()
                                )
                            )
                );
            }
        }
    );
    for (const auto bank : scratch.failed_banks_) {
        const auto status = resolve_bank(
            state,
            runtime,
            real,
            scratch,
            bank
        );
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

[[nodiscard]] Status resolve_insolvent_banks(
    const core::RootState& state,
    M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch
) {
    bool changed = true;
    while (changed) {
        changed = false;
        scratch.failed_banks_.clear();
        state.banks.for_each_alive(
            [&real, &scratch](
                BankId id,
                const core::BankComponent& bank
            ) {
                if (scratch.bank_alive_[bank_index(id)] != 0U
                    && real.balances_[
                        account_index(bank.cash_account)
                    ] < -kTolerance) {
                    scratch.failed_banks_.push_back(id);
                }
            }
        );
        for (const auto bank : scratch.failed_banks_) {
            const auto status = resolve_bank(
                state,
                runtime,
                real,
                scratch,
                bank
            );
            if (!status.ok()) {
                return status;
            }
            changed = true;
        }
    }
    return Status::success();
}

[[nodiscard]] Status distribute_bank_payout(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    core::BankPnlRecord& pnl,
    double payable
) {
    if (payable <= algorithms::kEconomicEpsilon) {
        return Status::success();
    }
    const auto* bank = state.banks.get(pnl.bank);
    double denominator = 0.0;
    for (const auto household_id : real.household_ids_) {
        const auto* household = state.households.get(household_id);
        const auto account = account_index(household->primary_account);
        if (!runtime.rules.interest_by_deposits
            || bank_for_node(
                scratch,
                real.account_nodes_[account]
            ) == pnl.bank) {
            denominator += runtime.rules.interest_by_deposits
                ? std::max(0.0, real.balances_[account])
                : 1.0;
        }
    }
    if (denominator <= algorithms::kEconomicEpsilon) {
        return Status::success();
    }
    for (const auto household_id : real.household_ids_) {
        const auto* household = state.households.get(household_id);
        const auto account = account_index(household->primary_account);
        if (runtime.rules.interest_by_deposits
            && bank_for_node(
                scratch,
                real.account_nodes_[account]
            ) != pnl.bank) {
            continue;
        }
        const double weight = runtime.rules.interest_by_deposits
            ? std::max(0.0, real.balances_[account])
            : 1.0;
        const double amount = payable * weight / denominator;
        const auto status = transfer(
            state,
            real,
            bank->cash_account,
            household->primary_account,
            amount
        );
        if (!status.ok()) {
            return status;
        }
        pnl.distributions += amount;
    }
    return Status::success();
}

[[nodiscard]] Status close_legacy_bank_payout(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch
) {
    if (runtime.rules.realized_bank_pnl) {
        return Status::success();
    }
    for (auto& pnl : scratch.bank_pnl_) {
        const auto* bank = state.banks.get(pnl.bank);
        const auto cash = account_index(bank->cash_account);
        if (scratch.bank_alive_[bank_index(pnl.bank)] == 0U
            || real.balances_[cash] <= algorithms::kEconomicEpsilon) {
            continue;
        }
        double payable = std::min(
            runtime.rules.bank_payout_ratio
                * std::max(0.0, pnl.loan_interest),
            real.balances_[cash]
        );
        if (runtime.policy.bank_target_capital_ratio > 0.0) {
            const double target =
                runtime.policy.bank_target_capital_ratio
                * scratch.exposure_by_bank_[bank_index(pnl.bank)];
            payable = std::max(0.0, real.balances_[cash] - target);
        }
        const auto status = distribute_bank_payout(
            state,
            runtime,
            real,
            scratch,
            pnl,
            payable
        );
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

[[nodiscard]] Status pay_deposit_cost_and_close_pnl(
    const core::RootState& state,
    const M5Runtime& runtime,
    M4TickScratch& real,
    M5TickScratch& scratch,
    Tick tick
) {
    const double rate = runtime.rules.realized_bank_pnl
        ? std::max(
            runtime.rules.deposit_rate,
            runtime.policy.deposit_rate_floor
        )
        : 0.0;
    if (runtime.rules.realized_bank_pnl
        && (rate > 0.0 || runtime.rules.deposit_interest_arrears)) {
        for (std::size_t index = 0;
             index < real.household_ids_.size();
             ++index) {
            const auto* household =
                state.households.get(real.household_ids_[index]);
            const auto account =
                account_index(household->primary_account);
            const auto bank = bank_for_node(
                scratch,
                real.account_nodes_[account]
            );
            if (!bank.valid()
                || scratch.bank_alive_[bank_index(bank)] == 0U) {
                continue;
            }
            const auto* bank_component_value = state.banks.get(bank);
            const auto cash = account_index(
                bank_component_value->cash_account
            );
            const double due =
                rate * std::max(0.0, real.balances_[account]);
            const double paid = std::min(
                due,
                std::max(0.0, real.balances_[cash])
            );
            if (paid > algorithms::kEconomicEpsilon) {
                const auto status = transfer(
                    state,
                    real,
                    bank_component_value->cash_account,
                    household->primary_account,
                    paid
                );
                if (!status.ok()) {
                    return status;
                }
                pnl_for(scratch, bank)->deposit_funding_cost += paid;
                scratch.working_metrics_.deposit_interest_paid += paid;
            }
            if (runtime.rules.deposit_interest_arrears) {
                capital_for(scratch, bank)->deposit_interest_arrears
                    += std::max(0.0, due - paid);
            }
        }
        if (runtime.rules.deposit_interest_arrears) {
            for (auto& capital : scratch.bank_capital_) {
                if (!capital.alive
                    || capital.deposit_interest_arrears
                        <= algorithms::kEconomicEpsilon) {
                    continue;
                }
                const auto* bank = state.banks.get(capital.bank);
                const auto cash = account_index(bank->cash_account);
                const double budget = std::min(
                    capital.deposit_interest_arrears,
                    std::max(0.0, real.balances_[cash])
                );
                if (budget <= algorithms::kEconomicEpsilon) {
                    continue;
                }
                double deposits = 0.0;
                for (const auto household_id : real.household_ids_) {
                    const auto* household =
                        state.households.get(household_id);
                    const auto account =
                        account_index(household->primary_account);
                    if (bank_for_node(
                            scratch,
                            real.account_nodes_[account]
                        ) == capital.bank) {
                        deposits += std::max(
                            0.0,
                            real.balances_[account]
                        );
                    }
                }
                if (deposits <= algorithms::kEconomicEpsilon) {
                    continue;
                }
                double paid_total = 0.0;
                for (const auto household_id : real.household_ids_) {
                    const auto* household =
                        state.households.get(household_id);
                    const auto account =
                        account_index(household->primary_account);
                    if (bank_for_node(
                            scratch,
                            real.account_nodes_[account]
                        ) != capital.bank) {
                        continue;
                    }
                    const double amount =
                        budget
                        * std::max(0.0, real.balances_[account])
                        / deposits;
                    const auto status = transfer(
                        state,
                        real,
                        bank->cash_account,
                        household->primary_account,
                        amount
                    );
                    if (!status.ok()) {
                        return status;
                    }
                    pnl_for(scratch, capital.bank)
                        ->deposit_funding_cost += amount;
                    scratch.working_metrics_.deposit_interest_paid
                        += amount;
                    paid_total += amount;
                }
                capital.deposit_interest_arrears = std::max(
                    0.0,
                    capital.deposit_interest_arrears - paid_total
                );
            }
        }
    }
    for (auto& pnl : scratch.bank_pnl_) {
        pnl.net_income =
            pnl.loan_interest
            + pnl.interbank_interest_income
            - pnl.interbank_interest_expense
            - pnl.deposit_funding_cost
            - pnl.realized_loan_losses
            - pnl.realized_interbank_losses;
        const auto* bank = state.banks.get(pnl.bank);
        const auto cash = account_index(bank->cash_account);
        if (runtime.rules.realized_bank_pnl
            && scratch.bank_alive_[bank_index(pnl.bank)] != 0U
            && pnl.net_income > algorithms::kEconomicEpsilon
            && real.balances_[cash] > algorithms::kEconomicEpsilon) {
            double payable = std::min(
                runtime.rules.bank_payout_ratio * pnl.net_income,
                real.balances_[cash]
            );
            if (runtime.policy.bank_target_capital_ratio > 0.0) {
                const double target =
                    runtime.policy.bank_target_capital_ratio
                    * scratch.exposure_by_bank_[bank_index(pnl.bank)];
                payable = std::min(
                    pnl.net_income,
                    std::max(0.0, real.balances_[cash] - target)
                );
            }
            const auto status = distribute_bank_payout(
                state,
                runtime,
                real,
                scratch,
                pnl,
                payable
            );
            if (!status.ok()) {
                return status;
            }
        }
        auto* capital = capital_for(scratch, pnl.bank);
        capital->closing_capital = real.balances_[
            account_index(bank->cash_account)
        ];
        capital->last_closed_tick = tick;
        capital->alive =
            scratch.bank_alive_[bank_index(pnl.bank)] != 0U;
        scratch.bank_capital_live_[bank_index(pnl.bank)] =
            capital->closing_capital;
    }
    return Status::success();
}

[[nodiscard]] Status validate_projection(
    const core::RootState& state,
    const M4TickScratch& real,
    const M5TickScratch& scratch
) noexcept {
    if (!all_finite(real.balances_)
        || !all_finite(real.reserve_balances_)
        || !finite(scratch.reserve_stock_)
        || scratch.reserve_stock_ < -kTolerance) {
        return Status(
            ErrorCode::invariant_violation,
            "M5 financial projection is not finite"
        );
    }
    double deposits = 0.0;
    for (const auto& account : state.postings.records()) {
        const double balance =
            real.balances_[account_index(account.id)];
        if (!account.allow_negative && balance < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.ledger.nonnegative-balances"
            );
        }
        deposits += balance;
    }
    double principal = 0.0;
    for (std::size_t index = 0; index < scratch.loans_.size(); ++index) {
        const auto& loan = scratch.loans_[index];
        if (loan.id.value() != index + 1
            || !finite(loan.principal.value())
            || loan.principal.value() < -kTolerance
            || state.banks.get(loan.lender) == nullptr
            || state.postings.get(loan.borrower_account) == nullptr) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.loan-ownership"
            );
        }
        if (loan.active) {
            principal += loan.principal.value();
        }
    }
    const double a5 = deposits - principal;
    const double scale = std::max(
        {1.0, std::abs(deposits), std::abs(state.genesis_money.value())}
    );
    if (std::abs(a5 - state.genesis_money.value())
        > 1.0e-9 * scale) {
        return Status(
            ErrorCode::invariant_violation,
            "invariant.m5.net-financial-worth"
        );
    }
    const double reserves = std::accumulate(
        real.reserve_balances_.begin(),
        real.reserve_balances_.end(),
        0.0
    );
    if (std::abs(reserves - scratch.reserve_stock_)
        > 1.0e-9 * std::max({1.0, std::abs(reserves), std::abs(scratch.reserve_stock_)})) {
        return Status(
            ErrorCode::invariant_violation,
            "invariant.ledger.reserve-conservation"
        );
    }
    for (std::size_t index = 0; index < scratch.interbank_.size(); ++index) {
        const auto& record = scratch.interbank_[index];
        if (record.id.value() != index + 1
            || record.lender == record.borrower
            || state.banks.get(record.lender) == nullptr
            || state.banks.get(record.borrower) == nullptr
            || !finite(record.principal.value())
            || record.principal.value() < -kTolerance
            || !finite(record.accrued_interest.value())
            || record.accrued_interest.value() < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.interbank"
            );
        }
    }
    for (const auto& operation : scratch.central_bank_operations_) {
        if (state.banks.get(operation.counterparty) == nullptr
            || !finite(operation.principal.value())
            || operation.principal.value() < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.central-bank-operations"
            );
        }
    }
    for (const auto& pnl : scratch.bank_pnl_) {
        const double expected =
            pnl.loan_interest
            + pnl.interbank_interest_income
            - pnl.interbank_interest_expense
            - pnl.deposit_funding_cost
            - pnl.realized_loan_losses
            - pnl.realized_interbank_losses;
        if (!finite(pnl.net_income)
            || std::abs(pnl.net_income - expected)
                > 1.0e-10
                    * std::max({1.0, std::abs(expected), std::abs(pnl.net_income)})) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.bank-pnl"
            );
        }
        const auto* capital = capital_for(scratch, pnl.bank);
        if (capital == nullptr) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.bank-capital-owner"
            );
        }
        const double roll_forward =
            capital->opening_capital
            + pnl.net_income
            + pnl.resolution_flow
            - pnl.distributions;
        if (std::abs(capital->closing_capital - roll_forward)
            > 1.0e-8
                * std::max(
                    {1.0, std::abs(roll_forward), std::abs(capital->closing_capital)}
                )) {
            return Status(
                ErrorCode::invariant_violation,
                "invariant.m5.bank-capital-roll-forward"
            );
        }
    }
    return Status::success();
}

class M5Extension final : public M4TickExtension {
public:
    M5Extension(
        M5Runtime& runtime,
        M5TickScratch& scratch,
        const M5AdvanceOptions& options,
        M5TickExtension* extension
    ) noexcept
        : runtime_(runtime),
          scratch_(scratch),
          options_(options),
          extension_(extension) {}

    ~M5Extension() override {
        if (tick_active_) {
            runtime_ = tick_open_runtime_;
        }
    }

    Status prepare_tick(
        const core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick tick,
        PhiloxRng& rng
    ) override {
        tick_open_runtime_ = runtime_;
        tick_active_ = true;
        const auto rate_status = set_policy_rate(runtime_);
        if (!rate_status.ok()) {
            return rate_status;
        }
        apply_fiscal_policy(real_runtime, runtime_);
        open_financial_books(
            state,
            real,
            runtime_,
            scratch_,
            tick
        );
        auto status = run_deposit_competition(
            state,
            runtime_,
            real,
            scratch_
        );
        if (!status.ok()) {
            return status;
        }
        status = run_omo(
            state,
            runtime_,
            real,
            scratch_,
            tick
        );
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->prepare_tick(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick,
            rng
        );
    }

    Status after_planning(
        const core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick tick,
        PhiloxRng& rng
    ) override {
        auto status = run_credit(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick
        );
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->after_planning(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick,
            rng
        );
    }

    Status before_settlement(
        const core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick tick,
        PhiloxRng& rng
    ) override {
        auto status = Status::success();
        if (runtime_.rules.full_firm_pnl) {
            status = service_debt(
                state,
                runtime_,
                real,
                scratch_,
                true
            );
            if (status.ok()) {
                status = close_legacy_bank_payout(
                    state,
                    runtime_,
                    real,
                    scratch_
                );
            }
        }
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->before_settlement(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick,
            rng
        );
    }

    Status after_settlement(
        const core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick tick,
        PhiloxRng& rng
    ) override {
        auto status = Status::success();
        if (!runtime_.rules.full_firm_pnl) {
            status = service_debt(
                state,
                runtime_,
                real,
                scratch_,
                false
            );
            if (status.ok()) {
                status = close_legacy_bank_payout(
                    state,
                    runtime_,
                    real,
                    scratch_
                );
            }
        }
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->after_settlement(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick,
            rng
        );
    }

    Status close_institutions(
        const core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick tick,
        PhiloxRng& rng
    ) override {
        auto status = run_interbank(
            state,
            runtime_,
            real,
            scratch_,
            tick
        );
        if (!status.ok()) {
            return status;
        }
        status = run_bank_runs(
            state,
            runtime_,
            real,
            scratch_,
            tick,
            rng,
            options_.force_run_bank
        );
        if (!status.ok()) {
            return status;
        }
        if (options_.force_default_account.has_value()) {
            status = force_default(
                state,
                real,
                scratch_,
                *options_.force_default_account
            );
            if (!status.ok()) {
                return status;
            }
        }
        if (extension_ != nullptr) {
            status = extension_->before_bank_resolution(
                state,
                real_runtime,
                real,
                runtime_,
                scratch_,
                tick,
                rng
            );
            if (!status.ok()) {
                return status;
            }
        }
        status = resolve_insolvent_banks(
            state,
            runtime_,
            real,
            scratch_
        );
        if (!status.ok()) {
            return status;
        }
        status = pay_deposit_cost_and_close_pnl(
            state,
            runtime_,
            real,
            scratch_,
            tick
        );
        if (!status.ok()) {
            return status;
        }
        if (extension_ != nullptr) {
            status = extension_->close_institutions(
                state,
                real_runtime,
                real,
                runtime_,
                scratch_,
                tick,
                rng
            );
            if (!status.ok()) {
                return status;
            }
        }
        scratch_.working_metrics_.total_loan_principal =
            std::accumulate(
                scratch_.loans_.begin(),
                scratch_.loans_.end(),
                0.0,
                [](double total, const core::LoanRecord& loan) {
                    return total
                        + (loan.active ? loan.principal.value() : 0.0);
                }
            );
        scratch_.working_metrics_.total_reserves = std::accumulate(
            real.reserve_balances_.begin(),
            real.reserve_balances_.end(),
            0.0
        );
        scratch_.working_metrics_.reserve_stock =
            scratch_.reserve_stock_;
        for (const auto& capital : scratch_.bank_capital_) {
            scratch_.working_metrics_.total_bank_capital
                += capital.closing_capital;
            if (capital.alive) {
                ++scratch_.working_metrics_.alive_banks;
            }
        }
        return Status::success();
    }

    Status validate(
        const core::RootState& state,
        const M4Runtime& real_runtime,
        const M4TickScratch& real,
        Tick tick
    ) const override {
        const auto status = validate_projection(state, real, scratch_);
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->validate(
            state,
            real_runtime,
            real,
            runtime_,
            scratch_,
            tick
        );
    }

    void commit(
        core::RootState& state,
        M4Runtime& real_runtime,
        M4TickScratch& real,
        Tick closed_tick,
        const M4Metrics& metrics
    ) noexcept override {
        for (auto& account : state.postings.records()) {
            account.key.settlement_node =
                real.account_nodes_[account_index(account.id)];
        }
        state.loans.replace_records(scratch_.loans_);
        state.interbank.replace_records(scratch_.interbank_);
        state.central_bank_operations.replace_records(
            scratch_.central_bank_operations_
        );
        state.bank_pnl.replace_records(scratch_.bank_pnl_);
        state.bank_capital.replace_records(scratch_.bank_capital_);
        state.reserves.commit_projected_stock(
            Money(scratch_.reserve_stock_)
        );
        state.banks.for_each_alive(
            [this](BankId id, core::BankComponent& bank) {
                bank.alive =
                    scratch_.bank_alive_[bank_index(id)] != 0U;
            }
        );
        scratch_.working_metrics_.economy = metrics;
        scratch_.working_metrics_.policy_rate = runtime_.policy_rate;
        scratch_.working_metrics_.inflation_sensor =
            runtime_.inflation_sensor;
        runtime_.previous_price_index =
            runtime_.last_metrics.economy.price_index;
        if (runtime_.previous_price_index
            <= algorithms::kEconomicEpsilon) {
            runtime_.previous_price_index = metrics.price_index;
        }
        runtime_.previous_unemployment = metrics.unemployment_rate;
        runtime_.last_metrics = scratch_.working_metrics_;
        if (extension_ != nullptr) {
            extension_->commit(
                state,
                real_runtime,
                real,
                runtime_,
                scratch_,
                closed_tick,
                runtime_.last_metrics
            );
        }
        tick_active_ = false;
    }

private:
    M5Runtime& runtime_;
    M5TickScratch& scratch_;
    const M5AdvanceOptions& options_;
    M5TickExtension* extension_{nullptr};
    M5Runtime tick_open_runtime_{};
    bool tick_active_{false};
};

}  // namespace

void M5TickScratch::reserve(const core::RootState& state) {
    loans_.reserve(state.loans.size() + state.households.alive_count()
        + state.firms.alive_count());
    interbank_.reserve(
        state.interbank.size()
        + state.banks.alive_count() * state.banks.alive_count()
    );
    central_bank_operations_.reserve(
        state.central_bank_operations.size()
        + 2 * state.banks.alive_count()
    );
    bank_pnl_.reserve(state.banks.alive_count());
    bank_capital_.reserve(state.banks.alive_count());
    debt_by_account_.resize(state.postings.size() + 1);
    const auto next_bank_id =
        static_cast<std::size_t>(state.banks.allocator_state().next_id);
    exposure_by_bank_.resize(next_bank_id);
    deposits_by_bank_.resize(next_bank_id);
    bank_capital_live_.resize(next_bank_id);
    bank_alive_.resize(next_bank_id);
    bank_by_node_.resize(state.reserves.size() + 1);
    for (const auto& reserve : state.reserves.records()) {
        bank_by_node_[node_index(reserve.node)] = reserve.bank;
    }
    firm_index_by_id_.assign(
        static_cast<std::size_t>(
            state.firms.allocator_state().next_id
        ),
        kNoIndex
    );
    std::size_t dense = 0;
    state.firms.for_each_alive(
        [this, &dense](FirmId id, const core::FirmComponent&) {
            if (id.value() < firm_index_by_id_.size()) {
                firm_index_by_id_[id.value()] = dense;
            }
            ++dense;
        }
    );
    household_order_.reserve(state.households.alive_count());
    candidate_banks_.reserve(state.banks.alive_count());
    alive_banks_.reserve(state.banks.alive_count());
    failed_banks_.reserve(state.banks.alive_count());
}

std::uint64_t M5TickScratch::capacity_signature() const noexcept {
    std::uint64_t signature = 1469598103934665603ULL;
    const std::array capacities{
        loans_.capacity(),
        interbank_.capacity(),
        central_bank_operations_.capacity(),
        bank_pnl_.capacity(),
        bank_capital_.capacity(),
        debt_by_account_.capacity(),
        exposure_by_bank_.capacity(),
        deposits_by_bank_.capacity(),
        bank_capital_live_.capacity(),
        bank_alive_.capacity(),
        bank_by_node_.capacity(),
        firm_index_by_id_.capacity(),
        household_order_.capacity(),
        candidate_banks_.capacity(),
        alive_banks_.capacity(),
        failed_banks_.capacity(),
    };
    for (const auto capacity : capacities) {
        signature ^= static_cast<std::uint64_t>(capacity);
        signature *= 1099511628211ULL;
    }
    return signature;
}

Status validate_m5_policy(const M5PolicyState& policy) noexcept {
    const std::array values{
        policy.government_consumption_share,
        policy.government_deficit_target,
        policy.deficit_unemployment_reference,
        policy.deficit_unemployment_cap,
        policy.government_investment_share,
        policy.profit_tax_rate,
        policy.income_tax_rate,
        policy.income_allowance,
        policy.consumption_tax_rate,
        policy.wealth_tax_rate,
        policy.wealth_allowance,
        policy.unemployment_benefit_replacement,
        policy.benefit_income_floor,
        policy.minimum_wage,
        policy.job_guarantee_wage_ratio,
        policy.job_guarantee_public_works_share,
        policy.inflation_target,
        policy.taylor_inflation,
        policy.taylor_unemployment,
        policy.rate_inertia,
        policy.neutral_rate,
        policy.natural_unemployment,
        policy.maximum_policy_rate,
        policy.inflation_sensor_lambda,
        policy.reserve_target,
        policy.reserve_gap_close,
        policy.reserve_floor_fraction,
        policy.firm_leverage_limit,
        policy.firm_minimum_dscr,
        policy.household_credit_limit,
        policy.bank_leverage_cap,
        policy.bank_exposure_limit,
        policy.bank_target_capital_ratio,
        policy.deposit_rate_floor,
    };
    if (!all_finite(values)
        || static_cast<std::uint8_t>(policy.monetary_regime) > 2U
        || policy.rate_inertia < 0.0 || policy.rate_inertia > 1.0
        || policy.inflation_target < 0.0
        || policy.taylor_inflation < 0.0
        || policy.taylor_unemployment < 0.0
        || policy.neutral_rate < 0.0
        || policy.natural_unemployment < 0.0
        || policy.natural_unemployment > 1.0
        || policy.inflation_sensor_lambda < 0.0
        || policy.inflation_sensor_lambda > 1.0
        || policy.maximum_policy_rate <= 0.0
        || policy.reserve_gap_close < 0.0
        || policy.reserve_gap_close > 1.0
        || policy.reserve_target < 0.0
        || policy.reserve_floor_fraction < 0.0
        || policy.government_consumption_share < 0.0
        || policy.government_consumption_share > 1.0
        || policy.government_deficit_target < 0.0
        || policy.deficit_unemployment_reference < 0.0
        || policy.deficit_unemployment_reference > 1.0
        || policy.deficit_unemployment_cap < 0.0
        || policy.deficit_unemployment_cap > 1.0
        || policy.government_investment_share < 0.0
        || policy.government_investment_share > 1.0
        || policy.profit_tax_rate < 0.0
        || policy.profit_tax_rate > 1.0
        || policy.income_tax_rate < 0.0
        || policy.income_tax_rate > 1.0
        || policy.income_allowance < 0.0
        || policy.consumption_tax_rate < 0.0
        || policy.consumption_tax_rate > 1.0
        || policy.wealth_tax_rate < 0.0
        || policy.wealth_tax_rate > 1.0
        || policy.wealth_allowance < 0.0
        || policy.unemployment_benefit_replacement < 0.0
        || policy.unemployment_benefit_replacement > 1.0
        || policy.benefit_income_floor < 0.0
        || policy.minimum_wage < 0.0
        || policy.job_guarantee_wage_ratio < 0.0
        || policy.job_guarantee_public_works_share < 0.0
        || policy.job_guarantee_public_works_share > 1.0
        || policy.firm_leverage_limit < 0.0
        || policy.firm_minimum_dscr < 0.0
        || policy.household_credit_limit < 0.0
        || policy.bank_leverage_cap < 0.0
        || policy.bank_exposure_limit < 0.0
        || policy.bank_exposure_limit > 1.0
        || policy.bank_target_capital_ratio < 0.0
        || policy.deposit_rate_floor < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M5 policy contains an invalid value"
        );
    }
    const bool manual =
        policy.monetary_regime == MonetaryRegime::manual;
    if (manual != policy.manual_policy_rate.has_value()
        || (manual
            && (!finite(*policy.manual_policy_rate)
                || *policy.manual_policy_rate < 0.0))) {
        return Status(
            ErrorCode::invalid_argument,
            "manual monetary regime requires exactly one manual rate"
        );
    }
    return Status::success();
}

Status validate_m5_spec(const M5SimulationSpec& spec) noexcept {
    const auto policy = validate_m5_policy(spec.policy);
    if (!policy.ok()) {
        return policy;
    }
    const std::array rule_values{
        spec.rules.opening_capital_per_bank,
        spec.rules.bank_leverage_mean,
        spec.rules.bank_leverage_dispersion,
        spec.rules.loan_spread_dispersion,
        spec.rules.interbank_rate_base,
        spec.rules.interbank_tightness,
        spec.rules.deposit_spread_dispersion,
        spec.rules.deposit_rate,
        spec.rules.firm_amortization,
        spec.rules.household_amortization,
        spec.rules.household_subsistence,
        spec.rules.run_sensitivity,
        spec.rules.run_health_reference,
        spec.rules.run_fear_persistence,
        spec.rules.bank_payout_ratio,
        spec.initial_policy_rate,
    };
    if (spec.real_economy.vertical != M4Vertical::capital_fiscal
        || spec.real_economy.requested_capabilities
            != kM4FiscalCapabilities
        || spec.rules.bank_count == 0
        || spec.rules.bank_count > 100'000
        || !all_finite(rule_values)
        || spec.rules.opening_capital_per_bank < 0.0
        || spec.rules.bank_leverage_mean < 1.0
        || spec.rules.bank_leverage_dispersion < 0.0
        || spec.rules.loan_spread_dispersion < 0.0
        || spec.rules.interbank_rate_base < 0.0
        || spec.rules.interbank_tightness < 0.0
        || spec.rules.deposit_spread_dispersion < 0.0
        || spec.rules.deposit_rate < 0.0
        || spec.rules.firm_amortization < 0.0
        || spec.rules.firm_amortization > 1.0
        || spec.rules.household_amortization < 0.0
        || spec.rules.household_amortization > 1.0
        || spec.rules.household_subsistence < 0.0
        || spec.rules.run_sensitivity < 0.0
        || spec.rules.run_health_reference <= 0.0
        || spec.rules.run_fear_persistence < 0.0
        || spec.rules.run_fear_persistence > 1.0
        || spec.rules.bank_payout_ratio < 0.0
        || spec.rules.bank_payout_ratio > 1.0
        || spec.initial_policy_rate < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M5 simulation specification is invalid"
        );
    }
    auto base = spec.real_economy;
    base.settlement_banks = spec.rules.bank_count;
    base.rules.initial_bank_capital =
        spec.rules.opening_capital_per_bank;
    return validate_spec(base);
}

Status validate_m5_state(
    const core::RootState& state,
    const M4Runtime& real_economy_runtime,
    const M5Runtime& runtime,
    Tick tick
) noexcept {
    if (!validate_m5_policy(runtime.policy).ok()
        || !finite(runtime.initial_policy_rate)
        || !finite(runtime.policy_rate)
        || !finite(runtime.inflation_sensor)
        || !finite(runtime.previous_price_index)
        || !finite(runtime.previous_unemployment)
        || !finite(runtime.reserve_genesis)
        || !finite(runtime.bank_fear)
        || !state.interbank.validate_finite().ok()
        || !state.central_bank_operations.validate_finite().ok()
        || !state.bank_pnl.validate_finite().ok()
        || !state.bank_capital.validate_finite().ok()
        || state.bank_pnl.size() != state.banks.alive_count()
        || state.bank_capital.size() != state.banks.alive_count()) {
        return Status(
            ErrorCode::invariant_violation,
            "M5 persistent state is invalid"
        );
    }
    auto base_runtime = real_economy_runtime;
    base_runtime.rules.initial_bank_capital =
        runtime.rules.opening_capital_per_bank;
    return validate_m4_state(state, base_runtime, tick);
}

Result<M5Initialization> build_m5_genesis(
    const M5SimulationSpec& spec
) {
    const auto validation = validate_m5_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    auto base = spec.real_economy;
    base.settlement_banks = spec.rules.bank_count;
    base.rules.initial_bank_capital =
        spec.rules.opening_capital_per_bank;
    auto initialization = build_m4_genesis(base);
    if (!initialization.ok()) {
        return initialization.status();
    }
    auto value = std::move(*initialization.get_if());
    std::vector<core::BankPnlRecord> pnl;
    std::vector<core::BankCapitalRecord> capital;
    std::vector<BankId> bank_ids;
    pnl.reserve(value.root.banks.alive_count());
    capital.reserve(value.root.banks.alive_count());
    bank_ids.reserve(value.root.banks.alive_count());
    const double denominator = static_cast<double>(
        std::max<std::uint64_t>(1, spec.rules.bank_count - 1)
    );
    value.root.banks.for_each_alive(
        [&spec, &value, &pnl, &capital, &bank_ids, denominator](
            BankId id,
            core::BankComponent& bank
        ) {
            bank_ids.push_back(id);
            const double centered =
                spec.rules.bank_count <= 1
                ? 0.0
                : 2.0
                        * static_cast<double>(id.value() - 1)
                        / denominator
                    - 1.0;
            bank.leverage_appetite = std::max(
                1.0,
                spec.rules.bank_leverage_mean
                    * (1.0
                        + spec.rules.bank_leverage_dispersion
                            * centered)
            );
            bank.loan_spread =
                spec.rules.loan_spread_dispersion * centered;
            bank.deposit_spread =
                spec.rules.deposit_spread_dispersion * centered;
            bank.alive = true;
            const double opening = value.root.postings
                .get(bank.cash_account)
                ->balance.value();
            pnl.push_back(core::BankPnlRecord{id, Tick(0)});
            capital.push_back(
                {
                    id,
                    opening,
                    opening,
                    0.0,
                    Tick(0),
                    true,
                    false,
                }
            );
        }
    );
    if (spec.rules.assign_banks_by_size) {
        std::vector<AccountId> borrowers;
        borrowers.reserve(
            value.root.firms.alive_count()
                + value.root.households.alive_count()
        );
        value.root.firms.for_each_alive(
            [&borrowers](FirmId, const core::FirmComponent& firm) {
                borrowers.push_back(firm.primary_account);
            }
        );
        value.root.households.for_each_alive(
            [&borrowers](
                HouseholdId,
                const core::HouseholdComponent& household
            ) {
                borrowers.push_back(household.primary_account);
            }
        );
        std::stable_sort(
            borrowers.begin(),
            borrowers.end(),
            [&value](AccountId left, AccountId right) {
                return value.root.postings.get(left)->balance.value()
                    > value.root.postings.get(right)->balance.value();
            }
        );
        for (std::size_t index = 0; index < borrowers.size(); ++index) {
            auto* account = value.root.postings.get(borrowers[index]);
            const auto* bank = value.root.banks.get(
                bank_ids[index % bank_ids.size()]
            );
            account->key.settlement_node = bank->settlement_node;
        }
    }
    value.root.bank_pnl.replace_records(pnl);
    value.root.bank_capital.replace_records(capital);
    M5Runtime runtime;
    runtime.policy = spec.policy;
    runtime.rules = spec.rules;
    runtime.initial_policy_rate = spec.initial_policy_rate;
    runtime.policy_rate = spec.initial_policy_rate;
    runtime.reserve_genesis =
        value.root.reserves.reserve_stock().value();
    runtime.last_metrics.policy_rate = spec.initial_policy_rate;
    runtime.last_metrics.total_reserves =
        value.root.reserves.total_reserves().value();
    runtime.last_metrics.reserve_stock =
        value.root.reserves.reserve_stock().value();
    runtime.last_metrics.total_bank_capital =
        spec.rules.opening_capital_per_bank
        * static_cast<double>(spec.rules.bank_count);
    runtime.last_metrics.alive_banks = spec.rules.bank_count;
    const auto state_validation = validate_m5_state(
        value.root,
        value.runtime,
        runtime,
        Tick(0)
    );
    if (!state_validation.ok()) {
        return state_validation;
    }
    return M5Initialization{
        std::move(value.root),
        std::move(value.runtime),
        std::move(runtime),
    };
}

namespace {

Result<M5AdvanceResult> advance_m5_ticks_impl(
    core::RootState& state,
    M4Runtime& real_economy_runtime,
    M4TickScratch& real_economy_scratch,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    Tick& tick,
    std::uint64_t count,
    M5TickExtension* tick_extension,
    const M5AdvanceOptions& options
) {
    if (count == 0) {
        return M5AdvanceResult{
            tick,
            tick,
            0,
            runtime.last_metrics,
            scratch.capacity_signature(),
            0,
            0,
        };
    }
    if (!validate_m5_state(
            state,
            real_economy_runtime,
            runtime,
            tick
        ).ok()) {
        return Status(
            ErrorCode::invariant_violation,
            "M5 cannot advance an invalid state"
        );
    }
    M5Extension extension(
        runtime,
        scratch,
        options,
        tick_extension
    );
    auto result = advance_ticks_extended(
        state,
        real_economy_runtime,
        real_economy_scratch,
        tick,
        count,
        extension,
        options.base
    );
    if (!result.ok()) {
        return result.status();
    }
    const auto& base = *result.get_if();
    return M5AdvanceResult{
        base.first_tick,
        base.next_tick,
        base.advanced_ticks,
        runtime.last_metrics,
        scratch.capacity_signature(),
        base.transfer_count,
        base.trade_count,
    };
}

}  // namespace

Result<M5AdvanceResult> advance_m5_ticks(
    core::RootState& state,
    M4Runtime& real_economy_runtime,
    M4TickScratch& real_economy_scratch,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    Tick& tick,
    std::uint64_t count,
    const M5AdvanceOptions& options
) {
    return advance_m5_ticks_impl(
        state,
        real_economy_runtime,
        real_economy_scratch,
        runtime,
        scratch,
        tick,
        count,
        nullptr,
        options
    );
}

Result<M5AdvanceResult> advance_m5_ticks_extended(
    core::RootState& state,
    M4Runtime& real_economy_runtime,
    M4TickScratch& real_economy_scratch,
    M5Runtime& runtime,
    M5TickScratch& scratch,
    Tick& tick,
    std::uint64_t count,
    M5TickExtension& extension,
    const M5AdvanceOptions& options
) {
    return advance_m5_ticks_impl(
        state,
        real_economy_runtime,
        real_economy_scratch,
        runtime,
        scratch,
        tick,
        count,
        &extension,
        options
    );
}

}  // namespace macro_sim::simulation
