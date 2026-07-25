#include "macro_sim/simulation/m6.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <numeric>
#include <span>
#include <utility>
#include <vector>

#include "macro_sim/algorithms/market.hpp"
#include "macro_sim/core/invariants.hpp"
#include "macro_sim/core/transaction.hpp"

namespace macro_sim::simulation {
namespace {

constexpr double kTolerance = 1.0e-8;
constexpr double kEconomicEpsilon = 1.0e-12;

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

template <typename Range> [[nodiscard]] bool all_finite(const Range &values) noexcept {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return finite(value); });
}

[[nodiscard]] std::size_t account_index(AccountId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] std::size_t node_index(SettlementNodeId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] std::size_t bank_index(BankId id) noexcept {
    return static_cast<std::size_t>(id.value());
}

[[nodiscard]] double projected_balance(const M4TickScratch &scratch,
                                       AccountId account) noexcept {
    const auto index = account_index(account);
    return index < scratch.balances_.size() ? scratch.balances_[index] : 0.0;
}

[[nodiscard]] Status move_reserves(M4TickScratch &scratch, SettlementNodeId source,
                                   SettlementNodeId destination,
                                   double amount) noexcept {
    if (!finite(amount) || amount < 0.0) {
        return Status(ErrorCode::invalid_argument, "M6 reserve movement is invalid");
    }
    if (amount <= kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto source_index = node_index(source);
    const auto destination_index = node_index(destination);
    if (source_index >= scratch.reserve_balances_.size() ||
        destination_index >= scratch.reserve_balances_.size()) {
        return Status(ErrorCode::not_found,
                      "M6 reserve movement references an absent node");
    }
    scratch.reserve_balances_[source_index] -= amount;
    scratch.reserve_balances_[destination_index] += amount;
    scratch.reserve_minimum_[source_index] =
        std::min(scratch.reserve_minimum_[source_index],
                 scratch.reserve_balances_[source_index]);
    return Status::success();
}

[[nodiscard]] Status transfer(const core::RootState &state, M4TickScratch &scratch,
                              AccountId source, AccountId destination,
                              double amount) noexcept {
    if (!finite(amount) || amount < 0.0) {
        return Status(ErrorCode::invalid_argument, "M6 transfer is invalid");
    }
    if (amount <= kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto *source_record = state.postings.get(source);
    const auto *destination_record = state.postings.get(destination);
    if (source_record == nullptr || destination_record == nullptr ||
        !source_record->open || !destination_record->open) {
        return Status(ErrorCode::not_found, "M6 transfer account is absent");
    }
    const auto source_index = account_index(source);
    const auto destination_index = account_index(destination);
    if (source_index >= scratch.balances_.size() ||
        destination_index >= scratch.balances_.size() ||
        source_index >= scratch.account_nodes_.size() ||
        destination_index >= scratch.account_nodes_.size()) {
        return Status(ErrorCode::internal_error, "M6 posting projection is stale");
    }
    if (!source_record->allow_negative &&
        scratch.balances_[source_index] + kTolerance < amount) {
        return Status(ErrorCode::insufficient_funds,
                      "M6 transfer exceeds available funds");
    }
    scratch.balances_[source_index] -= amount;
    scratch.balances_[destination_index] += amount;
    const auto reserve_status =
        move_reserves(scratch, scratch.account_nodes_[source_index],
                      scratch.account_nodes_[destination_index], amount);
    if (!reserve_status.ok()) {
        scratch.balances_[source_index] += amount;
        scratch.balances_[destination_index] -= amount;
        return reserve_status;
    }
    ++scratch.transfer_count_;
    return Status::success();
}

[[nodiscard]] AccountId owner_account(const core::RootState &state,
                                      core::OwnerId owner) noexcept {
    switch (owner.kind) {
    case core::OwnerKind::household: {
        const auto *household = state.households.get(HouseholdId(owner.value));
        return household != nullptr ? household->primary_account : AccountId{};
    }
    case core::OwnerKind::firm: {
        const auto *firm = state.firms.get(FirmId(owner.value));
        return firm != nullptr ? firm->primary_account : AccountId{};
    }
    case core::OwnerKind::bank: {
        const auto *bank = state.banks.get(BankId(owner.value));
        return bank != nullptr ? bank->cash_account : AccountId{};
    }
    case core::OwnerKind::treasury:
        return state.institutions.treasury_account;
    case core::OwnerKind::central_bank:
        return state.institutions.central_bank_account;
    case core::OwnerKind::dealer:
        return state.institutions.dealer_account;
    case core::OwnerKind::rounding_residual:
        return state.institutions.rounding_residual_account;
    case core::OwnerKind::institution:
        if (owner.value == 2) {
            return state.institutions.clearing_account;
        }
        break;
    }
    return AccountId{};
}

[[nodiscard]] BankId bank_for_node(const core::RootState &state,
                                   SettlementNodeId node) noexcept {
    BankId result{};
    state.banks.for_each_alive(
        [&result, node](BankId id, const core::BankComponent &bank) {
            if (bank.settlement_node == node) {
                result = id;
            }
        });
    return result;
}

[[nodiscard]] core::BankPnlRecord *pnl_for(M5TickScratch &scratch,
                                           BankId bank) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_pnl_.size()
               ? &scratch.bank_pnl_[index - 1]
               : nullptr;
}

[[nodiscard]] core::BankCapitalRecord *capital_for(M5TickScratch &scratch,
                                                   BankId bank) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_capital_.size()
               ? &scratch.bank_capital_[index - 1]
               : nullptr;
}

[[nodiscard]] const core::BankCapitalRecord *capital_for(const M5TickScratch &scratch,
                                                         BankId bank) noexcept {
    const auto index = bank_index(bank);
    return index > 0 && index <= scratch.bank_capital_.size()
               ? &scratch.bank_capital_[index - 1]
               : nullptr;
}

[[nodiscard]] FirmLifecycleRecord *
firm_record(std::vector<FirmLifecycleRecord> &records, FirmId firm) noexcept {
    const auto index = static_cast<std::size_t>(firm.value());
    return index < records.size() && records[index].firm == firm ? &records[index]
                                                                 : nullptr;
}

[[nodiscard]] const FirmLifecycleRecord *
firm_record(const std::vector<FirmLifecycleRecord> &records, FirmId firm) noexcept {
    const auto index = static_cast<std::size_t>(firm.value());
    return index < records.size() && records[index].firm == firm ? &records[index]
                                                                 : nullptr;
}

[[nodiscard]] std::span<const EquityId>
household_watchlist(const M6Runtime &runtime, HouseholdId household) noexcept {
    const auto index = static_cast<std::size_t>(household.value());
    if (index >= runtime.watchlist_rows.size()) {
        return {};
    }
    const auto &row = runtime.watchlist_rows[index];
    if (row.household != household || static_cast<std::size_t>(row.offset) + row.count >
                                          runtime.watchlist_equities.size()) {
        return {};
    }
    return std::span<const EquityId>(runtime.watchlist_equities.data() + row.offset,
                                     row.count);
}

[[nodiscard]] std::uint64_t splitmix64(std::uint64_t value) noexcept {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

[[nodiscard]] double unit_draw(std::uint64_t seed, std::uint64_t counter,
                               std::uint64_t stream) noexcept {
    const auto bits = splitmix64(seed ^ (counter * 0x9e3779b97f4a7c15ULL) ^
                                 (stream * 0xd1b54a32d192ed03ULL));
    return static_cast<double>(bits >> 11U) * (1.0 / 9007199254740992.0);
}

[[nodiscard]] std::optional<EquityId> firm_equity(const core::SecurityBook &book,
                                                  FirmId firm) noexcept {
    for (const auto security : book.securities_for_issuer(core::OwnerId::firm(firm))) {
        if (security.kind != core::SecurityKind::equity) {
            continue;
        }
        const auto id = EquityId(security.value);
        const auto *contract = book.get(id);
        if (contract != nullptr && contract->active &&
            contract->issuer_kind == core::EquityIssuerKind::firm) {
            return id;
        }
    }
    return std::nullopt;
}

[[nodiscard]] std::optional<EquityId> bank_equity(const core::SecurityBook &book,
                                                  BankId bank) noexcept {
    for (const auto security : book.securities_for_issuer(core::OwnerId::bank(bank))) {
        if (security.kind != core::SecurityKind::equity) {
            continue;
        }
        const auto id = EquityId(security.value);
        const auto *contract = book.get(id);
        if (contract != nullptr && contract->active &&
            contract->issuer_kind == core::EquityIssuerKind::bank) {
            return id;
        }
    }
    return std::nullopt;
}

[[nodiscard]] double household_security_value(const core::SecurityBook &book,
                                              core::OwnerId holder) noexcept {
    double value = 0.0;
    for (const auto lot_id : book.lots_for_holder(holder)) {
        const auto *lot = book.get(lot_id);
        if (lot == nullptr || !lot->active ||
            lot->security.kind != core::SecurityKind::equity) {
            continue;
        }
        const auto *contract = book.get(EquityId(lot->security.value));
        if (contract != nullptr && contract->active) {
            value += lot->units * contract->price.value();
        }
    }
    return value;
}

[[nodiscard]] double household_bond_value(const core::SecurityBook &book,
                                          core::OwnerId holder, Tick tick,
                                          double rate) noexcept {
    double value = 0.0;
    for (const auto lot_id : book.lots_for_holder(holder)) {
        const auto *lot = book.get(lot_id);
        if (lot == nullptr || !lot->active ||
            lot->security.kind != core::SecurityKind::bond) {
            continue;
        }
        const auto *contract = book.get(BondId(lot->security.value));
        if (contract == nullptr || !contract->active) {
            continue;
        }
        const auto remaining = contract->maturity_tick.value() > tick.value()
                                   ? contract->maturity_tick.value() - tick.value()
                                   : 0;
        value += bond_price(lot->units, remaining, rate, contract->coupon_rate.value());
    }
    return value;
}

[[nodiscard]] double bank_bond_face(const core::SecurityBook &book,
                                    BankId bank) noexcept {
    double value = 0.0;
    const auto holder = core::OwnerId::bank(bank);
    for (const auto &bond : book.bonds()) {
        if (bond.active) {
            value +=
                book.units_held(core::SecurityId::bond(bond.id), holder);
        }
    }
    return value;
}

void open_bank_security_books(const core::RootState &state,
                              const core::SecurityBook &book,
                              M5TickScratch &monetary) noexcept {
    state.banks.for_each_alive([&](BankId bank, const core::BankComponent &) {
        const double securities_value = bank_bond_face(book, bank);
        auto *capital = capital_for(monetary, bank);
        if (capital != nullptr) {
            capital->opening_capital += securities_value;
            capital->closing_capital += securities_value;
        }
        const auto index = bank_index(bank);
        if (index < monetary.bank_capital_live_.size()) {
            monetary.bank_capital_live_[index] += securities_value;
        }
    });
}

void close_bank_security_books(const core::RootState &state, const M4TickScratch &real,
                               const core::SecurityBook &book,
                               M5TickScratch &monetary) noexcept {
    state.banks.for_each_alive([&](BankId bank, const core::BankComponent &component) {
        auto *capital = capital_for(monetary, bank);
        if (capital == nullptr) {
            return;
        }
        capital->closing_capital = projected_balance(real, component.cash_account) +
                                   bank_bond_face(book, bank);
        const auto index = bank_index(bank);
        if (index < monetary.bank_capital_live_.size()) {
            monetary.bank_capital_live_[index] = capital->closing_capital;
        }
    });
}

[[nodiscard]] double outstanding_margin(const M6TickScratch &scratch,
                                        AccountId account) noexcept {
    const auto index = account_index(account);
    return index < scratch.margin_by_account_.size() ? scratch.margin_by_account_[index]
                                                     : 0.0;
}

void rebuild_debt_views(const core::RootState &state, const M5TickScratch &monetary,
                        M6TickScratch &scratch) {
    scratch.debt_by_account_.assign(state.postings.size() + 1, 0.0);
    scratch.margin_by_account_.assign(state.postings.size() + 1, 0.0);
    for (const auto &loan : monetary.loans_) {
        if (!loan.active) {
            continue;
        }
        const auto index = account_index(loan.borrower_account);
        if (index < scratch.debt_by_account_.size()) {
            scratch.debt_by_account_[index] += loan.principal.value();
        }
    }
    for (const auto loan_id : scratch.margin_loans_) {
        if (loan_id.value() == 0 || loan_id.value() > monetary.loans_.size()) {
            continue;
        }
        const auto &loan =
            monetary.loans_[static_cast<std::size_t>(loan_id.value() - 1)];
        if (!loan.active) {
            continue;
        }
        const auto index = account_index(loan.borrower_account);
        if (index < scratch.margin_by_account_.size()) {
            scratch.margin_by_account_[index] += loan.principal.value();
        }
    }
}

[[nodiscard]] Status run_bond_open(const core::RootState &state, M4TickScratch &real,
                                   M5TickScratch &monetary, M6TickScratch &scratch,
                                   Tick tick) {
    scratch.working_metrics_.bond_coupon_paid = 0.0;
    scratch.working_metrics_.bond_redemption = 0.0;
    if (scratch.securities_.bonds().empty()) {
        return Status::success();
    }
    const auto treasury = state.institutions.treasury_account;
    if (!treasury.valid()) {
        return Status(ErrorCode::contract_violation,
                      "M6 bonds require a Treasury account");
    }
    auto status = scratch.securities_.begin_batch();
    if (!status.ok()) {
        return status;
    }
    std::vector<BondId> matured;
    matured.reserve(scratch.securities_.bonds().size());
    for (const auto &bond : scratch.securities_.bonds()) {
        if (!bond.active) {
            continue;
        }
        const auto security = core::SecurityId::bond(bond.id);
        for (const auto lot_id : scratch.securities_.lots_for_security(security)) {
            const auto *lot = scratch.securities_.get(lot_id);
            if (lot == nullptr || !lot->active) {
                continue;
            }
            const auto account = owner_account(state, lot->holder);
            if (!account.valid()) {
                return Status(ErrorCode::contract_violation,
                              "bond holder account is absent");
            }
            const double coupon = lot->units * bond.coupon_rate.value();
            if (coupon > kEconomicEpsilon) {
                status = transfer(state, real, treasury, account, coupon);
                if (!status.ok()) {
                    return status;
                }
                if (lot->holder.kind == core::OwnerKind::bank) {
                    const auto bank = BankId(lot->holder.value);
                    auto *pnl = pnl_for(monetary, bank);
                    if (pnl != nullptr) {
                        pnl->interbank_interest_income += coupon;
                    }
                }
                scratch.working_metrics_.bond_coupon_paid += coupon;
            }
        }
        if (bond.maturity_tick <= tick) {
            matured.push_back(bond.id);
        }
    }
    for (const auto bond_id : matured) {
        const auto *bond = scratch.securities_.get(bond_id);
        if (bond == nullptr || !bond->active) {
            continue;
        }
        const auto security = core::SecurityId::bond(bond_id);
        const auto lot_ids = scratch.securities_.lots_for_security(security);
        std::vector<SecurityLotId> stable_lots(lot_ids.begin(), lot_ids.end());
        for (const auto lot_id : stable_lots) {
            const auto *lot = scratch.securities_.get(lot_id);
            if (lot == nullptr || !lot->active) {
                continue;
            }
            const auto account = owner_account(state, lot->holder);
            status = transfer(state, real, treasury, account, lot->units);
            if (!status.ok()) {
                return status;
            }
            scratch.working_metrics_.bond_redemption += lot->units;
        }
        status = scratch.securities_.settle_bond(bond_id);
        if (!status.ok()) {
            return status;
        }
    }
    return scratch.securities_.finish_batch();
}

void build_firm_statements(const core::RootState &state, M4TickScratch &real,
                           const M5TickScratch &monetary, M6Runtime &runtime,
                           M6TickScratch &scratch) {
    rebuild_debt_views(state, monetary, scratch);
    double capital_price = 0.0;
    std::uint64_t capital_quotes = 0;
    for (const auto index : real.capital_firm_indices_) {
        if (index < real.firm_work_.size()) {
            capital_price += real.firm_work_[index].posted_price;
            ++capital_quotes;
        }
    }
    if (capital_quotes > 0) {
        capital_price /= static_cast<double>(capital_quotes);
    } else {
        capital_price = runtime.replacement_capital_price;
    }
    capital_price = std::max(kEconomicEpsilon, capital_price);
    runtime.replacement_capital_price = capital_price;
    scratch.firm_return_.assign(scratch.firms_.size(), 0.0);
    scratch.working_metrics_.total_firm_book_equity = 0.0;
    for (std::size_t index = 0; index < real.firm_ids_.size(); ++index) {
        const auto id = real.firm_ids_[index];
        const auto *firm = state.firms.get(id);
        auto *lifecycle = firm_record(scratch.firms_, id);
        if (firm == nullptr || lifecycle == nullptr || !lifecycle->active) {
            continue;
        }
        const auto &work = real.firm_work_[index];
        FirmStatement statement;
        statement.firm = id;
        statement.cash = projected_balance(real, firm->primary_account);
        const auto debt_index = account_index(firm->primary_account);
        statement.debt = debt_index < scratch.debt_by_account_.size()
                             ? scratch.debt_by_account_[debt_index]
                             : 0.0;
        statement.capital_units = std::max(0.0, work.closing_capital);
        statement.capital_unit_price = capital_price;
        statement.capital_value =
            statement.capital_units * statement.capital_unit_price;
        statement.output_inventory_units = std::max(0.0, work.closing_inventory);
        const double unit_cost = work.produced > kEconomicEpsilon
                                     ? work.wage_bill / work.produced
                                     : work.posted_price;
        statement.output_inventory_unit_price =
            std::max(0.0, std::min(work.posted_price, std::max(0.0, unit_cost)));
        statement.output_inventory_value =
            statement.output_inventory_units * statement.output_inventory_unit_price;
        statement.inventory_value = statement.output_inventory_value +
                                    statement.work_in_progress_value +
                                    statement.input_inventory_value;
        statement.gross_assets =
            statement.cash + statement.capital_value + statement.inventory_value;
        statement.book_equity =
            statement.gross_assets - statement.debt - statement.interest_arrears;
        statement.eligible_collateral_value =
            (1.0 - runtime.rules.capital_haircut) * statement.capital_value +
            (1.0 - runtime.rules.inventory_haircut) * statement.inventory_value;
        statement.borrowing_base_proxy =
            statement.cash + statement.eligible_collateral_value;
        statement.borrowing_base_headroom =
            std::max(0.0, statement.borrowing_base_proxy - statement.debt);
        statement.earnings = work.profit;
        lifecycle->statement = statement;
        const double denominator = std::max(kEconomicEpsilon, statement.capital_value);
        const auto lifecycle_index = static_cast<std::size_t>(id.value());
        if (lifecycle_index < scratch.firm_return_.size()) {
            scratch.firm_return_[lifecycle_index] = statement.earnings / denominator;
        }
        scratch.working_metrics_.total_firm_book_equity += statement.book_equity;
    }
}

[[nodiscard]] Status update_equity_fundamentals(const core::RootState &state,
                                                const M5Runtime &monetary_runtime,
                                                M5TickScratch &monetary,
                                                M6Runtime &runtime,
                                                M6TickScratch &scratch) {
    const double discount = equity_discount_rate(monetary_runtime, runtime.rules);
    auto status = scratch.securities_.begin_batch();
    if (!status.ok()) {
        return status;
    }
    for (const auto &contract : scratch.securities_.equities()) {
        if (!contract.active) {
            continue;
        }
        double fundamental = 0.0;
        double income_signal = contract.income_signal;
        double peak = contract.peak_price.value();
        if (contract.issuer_kind == core::EquityIssuerKind::firm) {
            const auto id = FirmId(contract.issuer.value);
            auto *lifecycle = firm_record(scratch.firms_, id);
            if (lifecycle == nullptr || !lifecycle->active) {
                continue;
            }
            const double residual = lifecycle->statement.earnings -
                                    discount * lifecycle->statement.book_equity;
            lifecycle->residual_income_ema +=
                runtime.rules.residual_income_lambda *
                (residual - lifecycle->residual_income_ema);
            income_signal = lifecycle->residual_income_ema;
            fundamental = residual_income_fundamental(
                lifecycle->statement.book_equity, lifecycle->residual_income_ema,
                contract.outstanding_shares, discount);
            const double q = lifecycle->statement.book_equity > kEconomicEpsilon
                                 ? contract.price.value() *
                                       contract.outstanding_shares /
                                       lifecycle->statement.book_equity
                                 : 1.0;
            lifecycle->tobin_q_ema +=
                runtime.rules.q_smoothing * (q - lifecycle->tobin_q_ema);
        } else {
            const auto bank = BankId(contract.issuer.value);
            const auto *capital = capital_for(monetary, bank);
            const auto *pnl = pnl_for(monetary, bank);
            if (capital == nullptr || pnl == nullptr || !capital->alive) {
                continue;
            }
            income_signal += runtime.rules.bank_equity_lambda *
                             (std::max(0.0, pnl->net_income) - income_signal);
            fundamental =
                contract.outstanding_shares > kEconomicEpsilon
                    ? std::max(0.0, capital->closing_capital +
                                        std::max(0.0, income_signal) / discount) /
                          contract.outstanding_shares
                    : 0.0;
            peak = std::max(peak * 0.999, contract.price.value());
        }
        status = scratch.securities_.update_equity_valuation(
            contract.id, contract.price, contract.last_price, Price(peak),
            Price(fundamental), contract.trend, income_signal);
        if (!status.ok()) {
            return status;
        }
    }
    static_cast<void>(state);
    return scratch.securities_.finish_batch();
}

[[nodiscard]] double bank_exposure(const M5TickScratch &monetary,
                                   BankId bank) noexcept {
    double result = 0.0;
    for (const auto &loan : monetary.loans_) {
        if (loan.active && loan.lender == bank) {
            result += loan.principal.value();
        }
    }
    return result;
}

[[nodiscard]] double originate_margin(const core::RootState &state, M4TickScratch &real,
                                      M5Runtime &monetary_runtime,
                                      M5TickScratch &monetary, M6TickScratch &scratch,
                                      HouseholdId household_id, double requested,
                                      Tick tick, double credit_supply_multiplier) {
    if (requested <= kEconomicEpsilon) {
        return 0.0;
    }
    const auto *household = state.households.get(household_id);
    if (household == nullptr) {
        return 0.0;
    }
    const auto account = household->primary_account;
    const auto account_position = account_index(account);
    if (account_position >= real.account_nodes_.size()) {
        return 0.0;
    }
    const auto bank = bank_for_node(state, real.account_nodes_[account_position]);
    const auto *capital = capital_for(monetary, bank);
    if (!bank.valid() || capital == nullptr || !capital->alive) {
        return 0.0;
    }
    double headroom = requested;
    if (monetary_runtime.policy.bank_capital_constraint &&
        monetary_runtime.policy.bank_leverage_cap > 0.0) {
        headroom = std::min(
            headroom, std::max(0.0, monetary_runtime.policy.bank_leverage_cap *
                                            std::max(0.0, capital->closing_capital) -
                                        bank_exposure(monetary, bank)));
    }
    const double income = std::max(1.0, household->income_expected);
    const double current_debt = account_position < scratch.debt_by_account_.size()
                                    ? scratch.debt_by_account_[account_position]
                                    : 0.0;
    headroom =
        std::min(headroom,
                 std::max(0.0, monetary_runtime.policy.household_credit_limit * income -
                                   current_debt));
    headroom *= credit_supply_multiplier;
    const double granted = std::max(0.0, headroom);
    if (granted <= kEconomicEpsilon) {
        return 0.0;
    }
    const auto id = LoanId(static_cast<std::uint64_t>(monetary.loans_.size()) + 1);
    monetary.loans_.push_back({
        id,
        bank,
        core::OwnerId::household(household_id),
        account,
        Money(granted),
        0.0,
        core::LoanTerms{
            Rate(monetary_runtime.policy_rate),
            tick,
            Tick(tick.value() + 10 * 365),
        },
        true,
    });
    scratch.margin_loans_.push_back(id);
    real.balances_[account_position] += granted;
    scratch.debt_by_account_[account_position] += granted;
    scratch.margin_by_account_[account_position] += granted;
    scratch.working_metrics_.margin_originated += granted;
    monetary.working_metrics_.new_credit += granted;
    return granted;
}

void generate_firm_equity_orders(const core::RootState &state, M4TickScratch &real,
                                 M5Runtime &monetary_runtime, M5TickScratch &monetary,
                                 const M6Runtime &runtime, M6TickScratch &scratch,
                                 Tick tick, std::uint64_t &ordinal,
                                 double credit_supply_multiplier) {
    state.households.for_each_alive([&](HouseholdId household_id,
                                        const core::HouseholdComponent &household) {
        if ((household_id.value() - 1U + tick.value()) %
                runtime.rules.portfolio_review_interval_days !=
            0U) {
            return;
        }
        const auto watch = household_watchlist(runtime, household_id);
        if (watch.empty()) {
            return;
        }
        const auto holder = core::OwnerId::household(household_id);
        const double deposits = projected_balance(real, household.primary_account);
        double equity_value = 0.0;
        double attractiveness_total = 0.0;
        scratch.watch_current_.assign(watch.size(), 0.0);
        scratch.watch_attractiveness_.assign(watch.size(), 0.0);
        for (std::size_t index = 0; index < watch.size(); ++index) {
            const auto equity_id = watch[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || !equity->active ||
                equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double current = scratch.securities_.units_held(
                core::SecurityId::equity(equity_id), holder);
            scratch.watch_current_[index] = current;
            equity_value += current * equity->price.value();
            const double response =
                runtime.rules.fundamental_weight *
                    (equity->fundamental.value() - equity->price.value()) /
                    equity->price.value() +
                runtime.rules.chartist_weight * equity->trend;
            const double attractiveness = std::max(0.0, 1.0 + response);
            scratch.watch_attractiveness_[index] = attractiveness;
            attractiveness_total += attractiveness;
        }
        if (attractiveness_total <= kEconomicEpsilon) {
            return;
        }
        const double margin = outstanding_margin(scratch, household.primary_account);
        const double net_worth = deposits + equity_value - margin;
        double target_share = runtime.rules.household_equity_target;
        if (runtime.rules.margin_credit) {
            target_share = std::min(runtime.policy.margin_max, target_share);
        }
        const double target_equity = std::max(0.0, target_share * net_worth);
        double buy_cash = 0.0;
        for (std::size_t index = 0; index < watch.size(); ++index) {
            const auto equity_id = watch[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || !equity->active ||
                equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double desired = target_equity *
                                   scratch.watch_attractiveness_[index] /
                                   attractiveness_total / equity->price.value();
            const double current = scratch.watch_current_[index];
            const double delta =
                (desired - current) * runtime.rules.portfolio_adjustment;
            if (delta > 0.0) {
                buy_cash += delta * equity->price.value();
            }
        }
        double budget = deposits;
        if (runtime.rules.margin_credit && equity_value > 0.0) {
            const double secured_room =
                std::max(0.0, runtime.policy.margin_ltv * equity_value - margin);
            const double desired_margin =
                std::max(0.0, std::min(buy_cash, deposits + secured_room) - deposits);
            budget += originate_margin(state, real, monetary_runtime, monetary, scratch,
                                       household_id, desired_margin, tick,
                                       credit_supply_multiplier);
        }
        const double scale =
            buy_cash > kEconomicEpsilon ? std::min(1.0, budget / buy_cash) : 1.0;
        for (std::size_t index = 0; index < watch.size(); ++index) {
            const auto equity_id = watch[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || !equity->active ||
                equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double desired = target_equity *
                                   scratch.watch_attractiveness_[index] /
                                   attractiveness_total / equity->price.value();
            const double current = scratch.watch_current_[index];
            double delta = (desired - current) * runtime.rules.portfolio_adjustment;
            delta = delta > 0.0 ? delta * scale : std::max(delta, -current);
            if (std::abs(delta) > kEconomicEpsilon) {
                scratch.orders_.push_back({equity_id, household_id, delta, ordinal++});
            }
        }
    });
}

void generate_bank_equity_orders(const core::RootState &state, M4TickScratch &real,
                                 const M6Runtime &runtime, M6TickScratch &scratch,
                                 Tick tick, std::uint64_t &ordinal) {
    auto &bank_equities = scratch.bank_equities_;
    bank_equities.clear();
    state.banks.for_each_alive([&](BankId bank, const core::BankComponent &component) {
        if (!component.alive) {
            return;
        }
        const auto equity = bank_equity(scratch.securities_, bank);
        if (equity.has_value()) {
            bank_equities.push_back(*equity);
        }
    });
    if (bank_equities.empty()) {
        return;
    }
    state.households.for_each_alive([&](HouseholdId household_id,
                                        const core::HouseholdComponent &household) {
        if ((household_id.value() - 1U + tick.value()) %
                runtime.rules.portfolio_review_interval_days !=
            0U) {
            return;
        }
        const auto holder = core::OwnerId::household(household_id);
        const double deposits = projected_balance(real, household.primary_account);
        double value = 0.0;
        double attractiveness_total = 0.0;
        scratch.watch_current_.assign(bank_equities.size(), 0.0);
        scratch.watch_attractiveness_.assign(bank_equities.size(), 0.0);
        for (const auto lot_id : scratch.securities_.lots_for_holder(holder)) {
            const auto *lot = scratch.securities_.get(lot_id);
            if (lot == nullptr || !lot->active ||
                lot->security.kind != core::SecurityKind::equity) {
                continue;
            }
            const auto equity_id = EquityId(lot->security.value);
            const auto found =
                std::lower_bound(bank_equities.begin(), bank_equities.end(), equity_id);
            if (found != bank_equities.end() && *found == equity_id) {
                scratch.watch_current_[static_cast<std::size_t>(
                    found - bank_equities.begin())] += lot->units;
            }
        }
        for (std::size_t index = 0; index < bank_equities.size(); ++index) {
            const auto equity_id = bank_equities[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double current = scratch.watch_current_[index];
            scratch.watch_current_[index] = current;
            value += current * equity->price.value();
            const double response =
                runtime.rules.fundamental_weight *
                    (equity->fundamental.value() - equity->price.value()) /
                    equity->price.value() +
                runtime.rules.chartist_weight * equity->trend;
            const double attractiveness = std::max(0.0, 1.0 + response);
            scratch.watch_attractiveness_[index] = attractiveness;
            attractiveness_total += attractiveness;
        }
        if (attractiveness_total <= kEconomicEpsilon) {
            return;
        }
        const double target =
            runtime.rules.bank_equity_target * std::max(0.0, deposits + value);
        double buy_cash = 0.0;
        for (std::size_t index = 0; index < bank_equities.size(); ++index) {
            const auto equity_id = bank_equities[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double weight =
                scratch.watch_attractiveness_[index] / attractiveness_total;
            const double desired = target * weight / equity->price.value();
            const double current = scratch.watch_current_[index];
            const double delta =
                (desired - current) * runtime.rules.portfolio_adjustment;
            if (delta > 0.0) {
                buy_cash += delta * equity->price.value();
            }
        }
        const double scale =
            buy_cash > kEconomicEpsilon ? std::min(1.0, deposits / buy_cash) : 1.0;
        for (std::size_t index = 0; index < bank_equities.size(); ++index) {
            const auto equity_id = bank_equities[index];
            const auto *equity = scratch.securities_.get(equity_id);
            if (equity == nullptr || equity->price.value() <= kEconomicEpsilon) {
                continue;
            }
            const double weight =
                scratch.watch_attractiveness_[index] / attractiveness_total;
            const double desired = target * weight / equity->price.value();
            const double current = scratch.watch_current_[index];
            double delta = (desired - current) * runtime.rules.portfolio_adjustment;
            delta = delta > 0.0 ? delta * scale : std::max(delta, -current);
            if (std::abs(delta) > kEconomicEpsilon) {
                scratch.orders_.push_back({equity_id, household_id, delta, ordinal++});
            }
        }
    });
}

[[nodiscard]] double planned_primary_issue(const core::EquityContract &contract,
                                           const FirmLifecycleRecord *firm,
                                           const core::BankCapitalRecord *bank_capital,
                                           const M6Runtime &runtime) noexcept {
    if (contract.price.value() <= kEconomicEpsilon) {
        return 0.0;
    }
    if (contract.issuer_kind == core::EquityIssuerKind::firm) {
        if (!runtime.rules.equity_finance || firm == nullptr ||
            firm->tobin_q_ema <= 1.0 ||
            firm->statement.book_equity <= kEconomicEpsilon) {
            return 0.0;
        }
        const double issue_cash =
            std::min(runtime.rules.equity_issue_lambda * (firm->tobin_q_ema - 1.0) *
                         firm->statement.book_equity,
                     0.5 * firm->statement.book_equity);
        return std::min(issue_cash / contract.price.value(),
                        0.2 * contract.outstanding_shares);
    }
    if (!runtime.policy.bank_resolution_fund || bank_capital == nullptr ||
        bank_capital->closing_capital >= 0.0) {
        return 0.0;
    }
    const double needed = std::max(0.0, runtime.policy.bank_minimum_capital -
                                            bank_capital->closing_capital);
    return needed / contract.price.value();
}

[[nodiscard]] Status clear_equity_orders(const core::RootState &state,
                                         M4TickScratch &real, M5TickScratch &monetary,
                                         M6Runtime &runtime, M6TickScratch &scratch) {
    const auto equity_count = scratch.securities_.equities().size();
    const bool dense_equity_ids =
        std::all_of(scratch.orders_.begin(), scratch.orders_.end(),
                    [equity_count](const M6EquityOrder &order) {
                        return order.equity.value() <= equity_count;
                    });
    const bool monotonic_ordinals =
        std::is_sorted(scratch.orders_.begin(), scratch.orders_.end(),
                       [](const M6EquityOrder &left, const M6EquityOrder &right) {
                           return left.ordinal < right.ordinal;
                       });
    if (dense_equity_ids && monotonic_ordinals) {
        scratch.order_bucket_offsets_.assign(equity_count + 2U, 0U);
        for (const auto &order : scratch.orders_) {
            ++scratch.order_bucket_offsets_[order.equity.value() + 1U];
        }
        std::partial_sum(scratch.order_bucket_offsets_.begin(),
                         scratch.order_bucket_offsets_.end(),
                         scratch.order_bucket_offsets_.begin());
        scratch.ordered_orders_.resize(scratch.orders_.size());
        for (const auto &order : scratch.orders_) {
            const auto destination =
                scratch.order_bucket_offsets_[order.equity.value()]++;
            scratch.ordered_orders_[destination] = order;
        }
        scratch.orders_.swap(scratch.ordered_orders_);
    } else {
        std::sort(scratch.orders_.begin(), scratch.orders_.end(),
                  [](const M6EquityOrder &left, const M6EquityOrder &right) {
                      if (left.equity != right.equity) {
                          return left.equity < right.equity;
                      }
                      return left.ordinal < right.ordinal;
                  });
    }
    auto status = scratch.securities_.begin_batch();
    if (!status.ok()) {
        return status;
    }
    const auto clearing = state.institutions.clearing_account;
    std::size_t first = 0;
    while (first < scratch.orders_.size()) {
        std::size_t last = first + 1;
        while (last < scratch.orders_.size() &&
               scratch.orders_[last].equity == scratch.orders_[first].equity) {
            ++last;
        }
        const auto equity_id = scratch.orders_[first].equity;
        auto *contract = scratch.securities_.get(equity_id);
        if (contract == nullptr || !contract->active) {
            first = last;
            continue;
        }
        scratch.buyers_.clear();
        scratch.sellers_.clear();
        double buy = 0.0;
        double secondary_sell = 0.0;
        for (std::size_t index = first; index < last; ++index) {
            const auto &order = scratch.orders_[index];
            if (order.quantity > 0.0) {
                buy += order.quantity;
                scratch.buyers_.push_back(order);
            } else {
                secondary_sell -= order.quantity;
                scratch.sellers_.push_back(order);
            }
        }
        FirmLifecycleRecord *firm = nullptr;
        core::BankCapitalRecord *bank_capital = nullptr;
        if (contract->issuer_kind == core::EquityIssuerKind::firm) {
            firm = firm_record(scratch.firms_, FirmId(contract->issuer.value));
        } else {
            bank_capital = capital_for(monetary, BankId(contract->issuer.value));
        }
        const double primary =
            planned_primary_issue(*contract, firm, bank_capital, runtime);
        const double sell_total = secondary_sell + primary;
        const double executed = std::min(buy, sell_total);
        const double buy_scale = buy > kEconomicEpsilon ? executed / buy : 0.0;
        const double sell_scale =
            sell_total > kEconomicEpsilon ? executed / sell_total : 0.0;
        for (auto &buyer : scratch.buyers_) {
            buyer.quantity *= buy_scale;
        }
        for (auto &seller : scratch.sellers_) {
            seller.quantity = -seller.quantity * sell_scale;
        }
        const double primary_executed = primary * sell_scale;
        const double price = contract->price.value();
        for (const auto &buyer : scratch.buyers_) {
            const auto *household = state.households.get(buyer.household);
            if (household == nullptr) {
                return Status(ErrorCode::contract_violation, "equity buyer is absent");
            }
            status = transfer(state, real, household->primary_account, clearing,
                              buyer.quantity * price);
            if (!status.ok()) {
                return status;
            }
        }
        for (const auto &seller : scratch.sellers_) {
            const auto *household = state.households.get(seller.household);
            status = transfer(state, real, clearing, household->primary_account,
                              seller.quantity * price);
            if (!status.ok()) {
                return status;
            }
        }
        if (primary_executed > kEconomicEpsilon) {
            status = transfer(state, real, clearing, contract->issuer_account,
                              primary_executed * price);
            if (!status.ok()) {
                return status;
            }
            scratch.working_metrics_.primary_equity_raised += primary_executed * price;
            if (bank_capital != nullptr) {
                const double raised = primary_executed * price;
                bank_capital->closing_capital += raised;
                auto *pnl = pnl_for(monetary, BankId(contract->issuer.value));
                if (pnl != nullptr) {
                    pnl->resolution_flow += raised;
                }
            }
        }

        std::size_t buyer_index = 0;
        for (const auto &seller : scratch.sellers_) {
            double remaining = seller.quantity;
            while (remaining > kEconomicEpsilon &&
                   buyer_index < scratch.buyers_.size()) {
                auto &buyer = scratch.buyers_[buyer_index];
                const double take = std::min(remaining, buyer.quantity);
                status = scratch.securities_.transfer_units(
                    core::SecurityId::equity(equity_id),
                    core::OwnerId::household(seller.household),
                    core::OwnerId::household(buyer.household), take,
                    Money(take * price));
                if (!status.ok()) {
                    return status;
                }
                remaining -= take;
                buyer.quantity -= take;
                if (buyer.quantity <= kEconomicEpsilon) {
                    ++buyer_index;
                }
            }
        }
        double issue_remaining = primary_executed;
        while (issue_remaining > kEconomicEpsilon &&
               buyer_index < scratch.buyers_.size()) {
            auto &buyer = scratch.buyers_[buyer_index];
            const double take = std::min(issue_remaining, buyer.quantity);
            status = scratch.securities_.issue_equity_units(
                equity_id, core::OwnerId::household(buyer.household), take,
                Money(take * price));
            if (!status.ok()) {
                return status;
            }
            issue_remaining -= take;
            buyer.quantity -= take;
            if (buyer.quantity <= kEconomicEpsilon) {
                ++buyer_index;
            }
        }
        scratch.working_metrics_.equity_turnover += executed;
        const double excess = contract->outstanding_shares > kEconomicEpsilon
                                  ? (buy - sell_total) / contract->outstanding_shares
                                  : 0.0;
        const double bounded = std::clamp(excess, -0.5, 0.5);
        const double next_price =
            std::max(kEconomicEpsilon,
                     price * (1.0 + runtime.rules.equity_price_adjustment * bounded));
        const double price_return =
            price > kEconomicEpsilon ? (next_price - price) / price : 0.0;
        const double next_trend =
            contract->trend +
            runtime.rules.equity_trend_lambda * (price_return - contract->trend);
        const double next_peak = std::max(contract->peak_price.value(), next_price);
        status = scratch.securities_.update_equity_valuation(
            equity_id, Price(next_price), Price(price), Price(next_peak),
            contract->fundamental, next_trend, contract->income_signal);
        if (!status.ok()) {
            return status;
        }
        first = last;
    }
    status = scratch.securities_.finish_batch();
    if (!status.ok()) {
        return status;
    }
    scratch.working_metrics_.clearing_residual = projected_balance(real, clearing);
    return Status::success();
}

[[nodiscard]] Status service_margin(const core::RootState &state, M4TickScratch &real,
                                    M5TickScratch &monetary, M6Runtime &runtime,
                                    M6TickScratch &scratch) {
    rebuild_debt_views(state, monetary, scratch);
    scratch.working_metrics_.margin_repaid = 0.0;
    scratch.working_metrics_.margin_writeoffs = 0.0;
    scratch.working_metrics_.household_bankruptcies = 0;
    state.households.for_each_alive([&](HouseholdId household_id,
                                        const core::HouseholdComponent &household) {
        const auto account = household.primary_account;
        const double margin = outstanding_margin(scratch, account);
        if (margin <= kEconomicEpsilon) {
            return;
        }
        const double equity = household_security_value(
            scratch.securities_, core::OwnerId::household(household_id));
        double call = std::max(0.0, margin - runtime.policy.margin_ltv * equity);
        double available = projected_balance(real, account);
        double repayment = std::min(call, available);
        for (const auto loan_id : scratch.margin_loans_) {
            if (repayment <= kEconomicEpsilon || loan_id.value() == 0 ||
                loan_id.value() > monetary.loans_.size()) {
                continue;
            }
            auto &loan = monetary.loans_[static_cast<std::size_t>(loan_id.value() - 1)];
            if (!loan.active || loan.borrower_account != account) {
                continue;
            }
            const double paid = std::min(repayment, loan.principal.value());
            loan.principal = Money(loan.principal.value() - paid);
            loan.active = loan.principal.value() > kEconomicEpsilon;
            real.balances_[account_index(account)] -= paid;
            repayment -= paid;
            call -= paid;
            available -= paid;
            scratch.working_metrics_.margin_repaid += paid;
            monetary.working_metrics_.principal_repaid += paid;
        }
        rebuild_debt_views(state, monetary, scratch);
        const double remaining_margin = outstanding_margin(scratch, account);
        if (!runtime.policy.household_bankruptcy ||
            remaining_margin <= kEconomicEpsilon ||
            projected_balance(real, account) + equity - remaining_margin > 0.0) {
            return;
        }
        double cash = projected_balance(real, account);
        for (const auto loan_id : scratch.margin_loans_) {
            if (loan_id.value() == 0 || loan_id.value() > monetary.loans_.size()) {
                continue;
            }
            auto &loan = monetary.loans_[static_cast<std::size_t>(loan_id.value() - 1)];
            if (!loan.active || loan.borrower_account != account) {
                continue;
            }
            const double paid = std::min(cash, loan.principal.value());
            if (paid > 0.0) {
                loan.principal = Money(loan.principal.value() - paid);
                real.balances_[account_index(account)] -= paid;
                cash -= paid;
                scratch.working_metrics_.margin_repaid += paid;
                monetary.working_metrics_.principal_repaid += paid;
            }
            const double loss = loan.principal.value();
            if (loss > kEconomicEpsilon) {
                auto *pnl = pnl_for(monetary, loan.lender);
                const auto *bank = state.banks.get(loan.lender);
                if (pnl != nullptr) {
                    pnl->realized_loan_losses += loss;
                }
                if (bank != nullptr) {
                    real.balances_[account_index(bank->cash_account)] -= loss;
                }
                scratch.working_metrics_.margin_writeoffs += loss;
                monetary.working_metrics_.realized_credit_losses += loss;
                loan.principal = Money(0.0);
            }
            loan.active = false;
        }
        ++scratch.working_metrics_.household_bankruptcies;
    });
    rebuild_debt_views(state, monetary, scratch);
    return Status::success();
}

[[nodiscard]] Status resolve_firm_exit(const core::RootState &state,
                                       M4TickScratch &real, M5TickScratch &monetary,
                                       M6TickScratch &scratch, FirmId firm_id,
                                       bool defaulted) {
    const auto *firm = state.firms.get(firm_id);
    auto *lifecycle = firm_record(scratch.firms_, firm_id);
    if (firm == nullptr || lifecycle == nullptr || !lifecycle->active) {
        return Status(ErrorCode::not_found, "firm exit references an absent firm");
    }
    const auto account = firm->primary_account;
    double cash = projected_balance(real, account);
    for (auto &loan : monetary.loans_) {
        if (!loan.active || loan.borrower_account != account) {
            continue;
        }
        const double paid = std::min(cash, loan.principal.value());
        if (paid > 0.0) {
            real.balances_[account_index(account)] -= paid;
            cash -= paid;
            loan.principal = Money(loan.principal.value() - paid);
            monetary.working_metrics_.principal_repaid += paid;
        }
        const double loss = loan.principal.value();
        if (loss > kEconomicEpsilon) {
            auto *pnl = pnl_for(monetary, loan.lender);
            const auto *bank = state.banks.get(loan.lender);
            if (pnl != nullptr) {
                pnl->realized_loan_losses += loss;
            }
            if (bank != nullptr) {
                real.balances_[account_index(bank->cash_account)] -= loss;
            }
            monetary.working_metrics_.realized_credit_losses += loss;
            loan.principal = Money(0.0);
        }
        loan.active = false;
    }
    const auto equity = firm_equity(scratch.securities_, firm_id);
    if (cash > kEconomicEpsilon) {
        if (!defaulted && equity.has_value()) {
            const auto security = core::SecurityId::equity(*equity);
            const double shares = scratch.securities_.total_units(security);
            if (shares > kEconomicEpsilon) {
                const auto lot_ids = scratch.securities_.lots_for_security(security);
                for (const auto lot_id : lot_ids) {
                    const auto *lot = scratch.securities_.get(lot_id);
                    if (lot == nullptr || !lot->active ||
                        lot->holder.kind != core::OwnerKind::household) {
                        continue;
                    }
                    const auto recipient = owner_account(state, lot->holder);
                    const double amount = cash * lot->units / shares;
                    const auto status =
                        transfer(state, real, account, recipient, amount);
                    if (!status.ok()) {
                        return status;
                    }
                }
            }
        }
        cash = projected_balance(real, account);
        if (cash > kEconomicEpsilon) {
            const auto node = real.account_nodes_[account_index(account)];
            const auto bank = bank_for_node(state, node);
            const auto *bank_component = state.banks.get(bank);
            if (bank_component == nullptr) {
                return Status(ErrorCode::contract_violation,
                              "firm resolution bank is absent");
            }
            const auto status =
                transfer(state, real, account, bank_component->cash_account, cash);
            if (!status.ok()) {
                return status;
            }
            auto *pnl = pnl_for(monetary, bank);
            if (pnl != nullptr) {
                pnl->resolution_flow += cash;
            }
        }
    }
    if (equity.has_value()) {
        const auto status = scratch.securities_.resolve_equity(*equity);
        if (!status.ok()) {
            return status;
        }
    }
    lifecycle->active = false;
    lifecycle->defaulted = defaulted;
    scratch.firm_exits_.push_back({firm_id, account});
    ++scratch.working_metrics_.firm_exits;
    if (defaulted) {
        ++scratch.working_metrics_.firm_defaults;
    }
    return Status::success();
}

[[nodiscard]] Status run_firm_exits(const core::RootState &state, M4TickScratch &real,
                                    M5TickScratch &monetary, M6Runtime &runtime,
                                    M6TickScratch &scratch,
                                    const M6AdvanceOptions &options) {
    if (!runtime.rules.firm_dynamics && !options.force_firm_exit.has_value()) {
        return Status::success();
    }
    for (const auto firm_id : real.firm_ids_) {
        const auto *firm = state.firms.get(firm_id);
        auto *lifecycle = firm_record(scratch.firms_, firm_id);
        if (firm == nullptr || lifecycle == nullptr || !lifecycle->active) {
            continue;
        }
        const bool insolvent = lifecycle->statement.book_equity < -kTolerance;
        lifecycle->insolvent_days = insolvent ? lifecycle->insolvent_days + 1 : 0;
        const bool shell =
            lifecycle->statement.capital_units <= kEconomicEpsilon &&
            lifecycle->statement.output_inventory_units <= kEconomicEpsilon;
        lifecycle->shell_days = shell ? lifecycle->shell_days + 1 : 0;
        const bool forced =
            options.force_firm_exit.has_value() && *options.force_firm_exit == firm_id;
        const bool defaulted =
            forced || lifecycle->insolvent_days >= runtime.rules.bankrupt_persistence;
        const bool voluntary = lifecycle->shell_days >= runtime.rules.shell_exit_days;
        if (!(defaulted || voluntary)) {
            continue;
        }
        std::uint64_t active_in_sector = 0;
        state.firms.for_each_alive(
            [&](FirmId candidate, const core::FirmComponent &component) {
                const auto *record = firm_record(scratch.firms_, candidate);
                if (record != nullptr && record->active &&
                    component.sector == firm->sector) {
                    ++active_in_sector;
                }
            });
        if (active_in_sector <= 1) {
            continue;
        }
        const auto status =
            resolve_firm_exit(state, real, monetary, scratch, firm_id, defaulted);
        if (!status.ok()) {
            return status;
        }
    }
    return Status::success();
}

void run_sector_switching(const core::RootState &state, M4TickScratch &real,
                          M6Runtime &runtime, M6TickScratch &scratch,
                          std::uint64_t &lifecycle_counter) {
    if (!runtime.rules.consumption_strata || !runtime.rules.sector_switching) {
        return;
    }
    double necessity_return = 0.0;
    double luxury_return = 0.0;
    std::uint64_t necessity_count = 0;
    std::uint64_t luxury_count = 0;
    for (const auto firm_id : real.firm_ids_) {
        const auto *firm = state.firms.get(firm_id);
        const auto *lifecycle = firm_record(scratch.firms_, firm_id);
        if (firm == nullptr || lifecycle == nullptr || !lifecycle->active ||
            firm->sector != core::FirmSector::consumption) {
            continue;
        }
        const auto index = static_cast<std::size_t>(firm_id.value());
        const double value =
            index < scratch.firm_return_.size() ? scratch.firm_return_[index] : 0.0;
        if (lifecycle->stratum == ConsumptionStratum::necessity) {
            necessity_return += value;
            ++necessity_count;
        } else {
            luxury_return += value;
            ++luxury_count;
        }
    }
    if (necessity_count == 0 || luxury_count == 0) {
        return;
    }
    necessity_return /= static_cast<double>(necessity_count);
    luxury_return /= static_cast<double>(luxury_count);
    for (std::size_t index = 0; index < real.firm_ids_.size(); ++index) {
        const auto firm_id = real.firm_ids_[index];
        const auto *firm = state.firms.get(firm_id);
        auto *lifecycle = firm_record(scratch.firms_, firm_id);
        if (firm == nullptr || lifecycle == nullptr || !lifecycle->active ||
            firm->sector != core::FirmSector::consumption) {
            continue;
        }
        const double own = lifecycle->stratum == ConsumptionStratum::necessity
                               ? necessity_return
                               : luxury_return;
        const double other = lifecycle->stratum == ConsumptionStratum::necessity
                                 ? luxury_return
                                 : necessity_return;
        if (other > own * (1.0 + runtime.rules.switch_return_gap) && other > 0.0) {
            ++lifecycle->switch_pressure_days;
        } else {
            lifecycle->switch_pressure_days = 0;
        }
        if (lifecycle->switch_pressure_days < runtime.rules.switch_pressure_days) {
            continue;
        }
        const double draw =
            unit_draw(state.seed, lifecycle_counter++, 0x535749544348ULL);
        if (draw >= runtime.rules.switch_hazard) {
            continue;
        }
        auto &work = real.firm_work_[index];
        const double loss = work.closing_capital * runtime.rules.switch_retool_loss;
        work.closing_capital = std::max(0.0, work.closing_capital - loss);
        lifecycle->stratum = lifecycle->stratum == ConsumptionStratum::necessity
                                 ? ConsumptionStratum::luxury
                                 : ConsumptionStratum::necessity;
        lifecycle->switch_pressure_days = 0;
        ++scratch.working_metrics_.sector_switches;
        scratch.working_metrics_.sector_retool_capital += loss;
    }
}

[[nodiscard]] std::optional<HouseholdId>
pick_founder(const core::RootState &state, const M4TickScratch &real, double need,
             std::uint64_t seed, std::uint64_t &counter, std::uint64_t stream) {
    const auto count = state.households.alive_count();
    if (count == 0) {
        return std::nullopt;
    }
    for (std::uint64_t attempt = 0; attempt < 16; ++attempt) {
        const auto ordinal = static_cast<std::uint64_t>(
            unit_draw(seed, counter++, stream) * static_cast<double>(count));
        HouseholdId candidate{};
        std::uint64_t position = 0;
        state.households.for_each_alive([&](HouseholdId id,
                                            const core::HouseholdComponent &) {
            if (position == std::min(ordinal, static_cast<std::uint64_t>(count - 1))) {
                candidate = id;
            }
            ++position;
        });
        const auto *household = state.households.get(candidate);
        if (household != nullptr &&
            projected_balance(real, household->primary_account) >= need) {
            return candidate;
        }
    }
    return std::nullopt;
}

[[nodiscard]] Status stage_firm_entries(const core::RootState &state,
                                        M4TickScratch &real, M6Runtime &runtime,
                                        M6TickScratch &scratch,
                                        std::uint64_t &lifecycle_counter) {
    if (!runtime.rules.firm_dynamics || runtime.rules.entry_max == 0) {
        return Status::success();
    }
    std::vector<double> returns;
    for (const auto firm_id : real.firm_ids_) {
        const auto *firm = state.firms.get(firm_id);
        const auto *lifecycle = firm_record(scratch.firms_, firm_id);
        if (firm == nullptr || lifecycle == nullptr || !lifecycle->active ||
            firm->sector != core::FirmSector::consumption) {
            continue;
        }
        const auto index = static_cast<std::size_t>(firm_id.value());
        if (index < scratch.firm_return_.size()) {
            returns.push_back(scratch.firm_return_[index]);
        }
    }
    if (returns.empty()) {
        return Status::success();
    }
    std::sort(returns.begin(), returns.end());
    const double median = returns[returns.size() / 2];
    const double excess = median - (runtime.last_metrics.economy.policy_rate +
                                    runtime.rules.entry_hurdle);
    if (excess <= 0.0) {
        return Status::success();
    }
    const double desired =
        runtime.rules.entry_beta * excess * static_cast<double>(returns.size());
    std::uint32_t entries =
        static_cast<std::uint32_t>(std::floor(std::max(0.0, desired)));
    if (unit_draw(state.seed, lifecycle_counter++, 0x4649524d454e5452ULL) <
        desired - std::floor(desired)) {
        ++entries;
    }
    entries = std::min(entries, runtime.rules.entry_max);
    for (std::uint32_t entry = 0; entry < entries; ++entry) {
        const auto founder =
            pick_founder(state, real, runtime.rules.startup_deposits, state.seed,
                         lifecycle_counter, 0x464f554e444552ULL);
        if (!founder.has_value()) {
            break;
        }
        const auto *founder_component = state.households.get(*founder);
        const auto predicted_firm = FirmId(state.firms.allocator_state().next_id +
                                           scratch.firm_entries_.size());
        const auto predicted_account =
            AccountId(static_cast<std::uint64_t>(state.postings.size()) +
                      scratch.firm_entries_.size() + 1);
        core::FirmComponent component;
        component.sector = core::FirmSector::consumption;
        component.primary_account = predicted_account;
        component.goods_inventory = Goods(0.0);
        component.physical_capital = Capital(runtime.rules.startup_capital);
        component.productivity =
            real.firm_ids_.empty()
                ? 1.0
                : state.firms.get(real.firm_ids_.front())->productivity;
        component.technology = core::FirmTechnology::cobb_douglas;
        component.total_factor_productivity =
            real.firm_ids_.empty()
                ? 1.0
                : state.firms.get(real.firm_ids_.front())->total_factor_productivity;
        component.posted_price = Price(std::max(
            kEconomicEpsilon, runtime.last_metrics.economy.economy.price_index));
        component.posted_wage =
            Money(real.firm_ids_.empty()
                      ? 1.0
                      : state.firms.get(real.firm_ids_.front())->posted_wage.value());
        FirmLifecycleRecord lifecycle;
        lifecycle.firm = predicted_firm;
        lifecycle.statement.firm = predicted_firm;
        lifecycle.statement.cash = runtime.rules.startup_deposits;
        lifecycle.statement.capital_units = runtime.rules.startup_capital;
        lifecycle.statement.capital_unit_price = runtime.replacement_capital_price;
        lifecycle.statement.capital_value =
            lifecycle.statement.capital_units * lifecycle.statement.capital_unit_price;
        lifecycle.statement.gross_assets =
            runtime.rules.startup_deposits + lifecycle.statement.capital_value;
        lifecycle.statement.book_equity = lifecycle.statement.gross_assets;
        lifecycle.statement.eligible_collateral_value =
            (1.0 - runtime.rules.capital_haircut) * lifecycle.statement.capital_value;
        lifecycle.statement.borrowing_base_proxy =
            lifecycle.statement.cash + lifecycle.statement.eligible_collateral_value;
        lifecycle.statement.borrowing_base_headroom =
            lifecycle.statement.borrowing_base_proxy;
        lifecycle.stratum =
            entry % 2 == 0 ? ConsumptionStratum::necessity : ConsumptionStratum::luxury;
        lifecycle.active = true;
        if (scratch.firms_.size() <= predicted_firm.value()) {
            scratch.firms_.resize(static_cast<std::size_t>(predicted_firm.value()) + 1);
        }
        scratch.firms_[static_cast<std::size_t>(predicted_firm.value())] = lifecycle;
        core::EquityContract equity;
        equity.issuer_kind = core::EquityIssuerKind::firm;
        equity.issuer = core::OwnerId::firm(predicted_firm);
        equity.issuer_account = predicted_account;
        equity.currency = state.currency;
        equity.outstanding_shares = runtime.rules.shares_per_firm;
        const double price =
            runtime.rules.startup_deposits / runtime.rules.shares_per_firm;
        equity.price = Price(price);
        equity.last_price = Price(price);
        equity.peak_price = Price(price);
        equity.fundamental = Price(price);
        const std::array holding{core::InitialSecurityHolding{
            core::OwnerId::household(*founder),
            runtime.rules.shares_per_firm,
            Money(runtime.rules.startup_deposits),
        }};
        const auto created = scratch.securities_.create_equity(equity, holding);
        if (!created.ok()) {
            return created.status();
        }
        scratch.firm_entries_.push_back({
            predicted_firm,
            predicted_account,
            *founder,
            founder_component->primary_account,
            real.account_nodes_[account_index(founder_component->primary_account)],
            runtime.rules.startup_deposits,
            component,
            lifecycle,
            *created.get_if(),
        });
        ++scratch.working_metrics_.firm_births;
    }
    return Status::success();
}

[[nodiscard]] Status resolve_dead_bank_equity(const core::RootState &state,
                                              M5TickScratch &monetary,
                                              M6TickScratch &scratch) {
    for (const auto &capital : monetary.bank_capital_) {
        if (capital.alive) {
            continue;
        }
        const auto equity = bank_equity(scratch.securities_, capital.bank);
        if (!equity.has_value()) {
            continue;
        }
        const auto *contract = scratch.securities_.get(*equity);
        if (contract == nullptr || !contract->active) {
            continue;
        }
        const auto status = scratch.securities_.resolve_equity(*equity);
        if (!status.ok()) {
            return status;
        }
        ++scratch.working_metrics_.bank_equity_resolutions;
    }
    static_cast<void>(state);
    return Status::success();
}

[[nodiscard]] Status stage_bank_entries(const core::RootState &state,
                                        M4TickScratch &real,
                                        const M5Runtime &monetary_runtime,
                                        M5TickScratch &monetary, M6Runtime &runtime,
                                        M6TickScratch &scratch,
                                        std::uint64_t &lifecycle_counter, bool force) {
    if (!runtime.rules.bank_dynamics || !runtime.rules.bank_equity ||
        runtime.rules.bank_entry_max == 0) {
        return Status::success();
    }
    double profitable_capital = 0.0;
    double profitable_income = 0.0;
    std::uint64_t alive = 0;
    for (const auto &capital : monetary.bank_capital_) {
        if (!capital.alive) {
            continue;
        }
        ++alive;
        const auto *pnl = pnl_for(monetary, capital.bank);
        if (pnl != nullptr && pnl->net_income > 0.0 && capital.closing_capital > 0.0) {
            profitable_capital += capital.closing_capital;
            profitable_income += pnl->net_income;
        }
    }
    double probability = 0.0;
    if (profitable_capital > kEconomicEpsilon) {
        const double roe = profitable_income / profitable_capital;
        const double rate = std::max(runtime.last_metrics.economy.policy_rate, 1.0e-6);
        probability =
            std::clamp(runtime.rules.bank_entry_beta * (roe / rate - 1.0), 0.0, 1.0);
        probability *=
            std::max(0.0, 1.0 - static_cast<double>(alive) /
                                    (2.0 * static_cast<double>(std::max<std::uint64_t>(
                                               1, state.banks.alive_count()))));
    } else if (alive == 0 && runtime.policy.bank_resolution_fund) {
        probability = std::min(1.0, 5.0 * runtime.rules.bank_entry_beta);
    }
    if (force) {
        probability = 1.0;
    }
    for (std::uint32_t entry = 0; entry < runtime.rules.bank_entry_max; ++entry) {
        if (unit_draw(state.seed, lifecycle_counter++, 0x42414e4b454e5452ULL) >=
            probability) {
            continue;
        }
        const auto founder =
            pick_founder(state, real, runtime.policy.bank_minimum_capital, state.seed,
                         lifecycle_counter, 0x42414e4b464f554eULL);
        if (!founder.has_value()) {
            break;
        }
        const auto *founder_component = state.households.get(*founder);
        const auto predicted_bank = BankId(state.banks.allocator_state().next_id +
                                           scratch.bank_entries_.size());
        const auto predicted_node =
            SettlementNodeId(static_cast<std::uint64_t>(state.reserves.size()) +
                             scratch.bank_entries_.size() + 1);
        const auto predicted_account =
            AccountId(static_cast<std::uint64_t>(state.postings.size()) +
                      scratch.firm_entries_.size() + scratch.bank_entries_.size() + 1);
        core::BankComponent component;
        component.cash_account = predicted_account;
        component.settlement_node = predicted_node;
        component.leverage_appetite = monetary_runtime.rules.bank_leverage_mean;
        component.alive = true;
        core::BankPnlRecord pnl{predicted_bank, Tick(0)};
        core::BankCapitalRecord capital{
            predicted_bank,
            runtime.policy.bank_minimum_capital,
            runtime.policy.bank_minimum_capital,
            0.0,
            Tick(0),
            true,
            false,
        };
        core::EquityContract equity;
        equity.issuer_kind = core::EquityIssuerKind::bank;
        equity.issuer = core::OwnerId::bank(predicted_bank);
        equity.issuer_account = predicted_account;
        equity.currency = state.currency;
        equity.outstanding_shares = runtime.rules.bank_shares;
        const double price =
            runtime.policy.bank_minimum_capital / runtime.rules.bank_shares;
        equity.price = Price(price);
        equity.last_price = Price(price);
        equity.peak_price = Price(price);
        equity.fundamental = Price(price);
        const std::array holding{core::InitialSecurityHolding{
            core::OwnerId::household(*founder),
            runtime.rules.bank_shares,
            Money(runtime.policy.bank_minimum_capital),
        }};
        const auto created = scratch.securities_.create_equity(equity, holding);
        if (!created.ok()) {
            return created.status();
        }
        scratch.bank_entries_.push_back({
            predicted_bank,
            predicted_account,
            predicted_node,
            *founder,
            founder_component->primary_account,
            runtime.policy.bank_minimum_capital,
            component,
            pnl,
            capital,
        });
        ++scratch.working_metrics_.bank_births;
    }
    return Status::success();
}

[[nodiscard]] Status run_bond_issuance(const core::RootState &state,
                                       M4TickScratch &real,
                                       const M5TickScratch &monetary,
                                       M6Runtime &runtime, M6TickScratch &scratch,
                                       Tick tick) {
    if (!runtime.rules.bonds || runtime.policy.bond_finance_fraction <= 0.0) {
        return Status::success();
    }
    const auto treasury = state.institutions.treasury_account;
    const double outstanding = scratch.securities_.total_bond_face().value();
    const double government_debt =
        std::max(0.0, outstanding - projected_balance(real, treasury));
    const double target = runtime.policy.bond_finance_fraction * government_debt;
    const double gap = std::max(0.0, target - outstanding);
    if (gap <= kEconomicEpsilon) {
        return Status::success();
    }
    auto &demands = scratch.bond_demands_;
    demands.clear();
    double total_demand = 0.0;
    state.households.for_each_alive(
        [&](HouseholdId id, const core::HouseholdComponent &household) {
            const auto holder = core::OwnerId::household(id);
            const double deposits = projected_balance(real, household.primary_account);
            const double bonds =
                household_bond_value(scratch.securities_, holder, tick,
                                     runtime.last_metrics.economy.policy_rate);
            const double buffer =
                std::max(household.income_expected, runtime.rules.startup_deposits);
            const double room = std::max(
                0.0, runtime.policy.household_bond_target * (deposits + bonds) - bonds);
            const double demand = std::min(std::max(0.0, deposits - buffer), room);
            if (demand > kEconomicEpsilon) {
                demands.push_back({holder, household.primary_account, demand});
                total_demand += demand;
            }
        });
    state.banks.for_each_alive([&](BankId id, const core::BankComponent &bank) {
        if (!bank.alive || runtime.policy.bank_bond_appetite <= 0.0) {
            return;
        }
        const auto reserve_position = node_index(bank.settlement_node);
        const double reserve = reserve_position < real.reserve_balances_.size()
                                   ? real.reserve_balances_[reserve_position]
                                   : 0.0;
        const auto *capital = capital_for(monetary, id);
        const double current =
            std::accumulate(scratch.securities_.bank_lots(id).begin(),
                            scratch.securities_.bank_lots(id).end(), 0.0,
                            [&](double sum, SecurityLotId lot_id) {
                                const auto *lot = scratch.securities_.get(lot_id);
                                return sum + (lot != nullptr ? lot->units : 0.0);
                            });
        double demand = runtime.policy.bank_bond_appetite * std::max(0.0, reserve);
        if (runtime.policy.bank_bond_duration_limit > 0.0 && capital != nullptr) {
            demand = std::min(
                demand, std::max(0.0, runtime.policy.bank_bond_duration_limit *
                                              std::max(0.0, capital->closing_capital) -
                                          current));
        }
        if (demand > kEconomicEpsilon) {
            demands.push_back({
                core::OwnerId::bank(id),
                bank.cash_account,
                demand,
            });
            total_demand += demand;
        }
    });
    const double issue = std::min(gap, total_demand);
    if (issue <= kEconomicEpsilon) {
        return Status::success();
    }
    std::uint64_t maturity = tick.value() + runtime.policy.bond_maturity_days;
    if (runtime.rules.bond_maturity_bucket > 1) {
        const auto bucket = runtime.rules.bond_maturity_bucket;
        maturity = ((maturity + bucket - 1) / bucket) * bucket;
    }
    core::BondContract contract;
    contract.issuer = core::OwnerId::institutional(core::OwnerKind::treasury);
    contract.issuer_account = treasury;
    contract.currency = state.currency;
    contract.issued_tick = tick;
    contract.maturity_tick = Tick(maturity);
    contract.coupon_rate = Rate(runtime.policy.bond_coupon_rate);
    contract.original_face = Money(issue);
    const auto clearing_owner =
        core::OwnerId::institutional(core::OwnerKind::institution, 2);
    auto status = scratch.securities_.begin_batch();
    if (!status.ok()) {
        return status;
    }
    BondId bond_id{};
    for (const auto &candidate : scratch.securities_.bonds()) {
        if (candidate.active && candidate.issuer == contract.issuer &&
            candidate.issuer_account == contract.issuer_account &&
            candidate.currency == contract.currency &&
            candidate.maturity_tick == contract.maturity_tick &&
            candidate.coupon_rate == contract.coupon_rate) {
            bond_id = candidate.id;
            break;
        }
    }
    if (bond_id.valid()) {
        status = scratch.securities_.issue_bond_units(bond_id, clearing_owner, issue,
                                                      Money(issue));
        if (!status.ok()) {
            return status;
        }
    } else {
        const auto created =
            scratch.securities_.issue_bond(contract, clearing_owner, Money(issue));
        if (!created.ok()) {
            return created.status();
        }
        bond_id = *created.get_if();
    }
    double allocated = 0.0;
    for (std::size_t index = 0; index < demands.size(); ++index) {
        const double remaining_issue = std::max(0.0, issue - allocated);
        const double planned =
            index + 1 == demands.size()
                ? remaining_issue
                : std::min(demands[index].amount,
                           issue * demands[index].amount / total_demand);
        const double available = scratch.securities_.units_held(
            core::SecurityId::bond(bond_id), clearing_owner);
        const double amount = std::min({remaining_issue, planned, available});
        if (amount <= kEconomicEpsilon) {
            continue;
        }
        status = transfer(state, real, demands[index].account, treasury, amount);
        if (!status.ok()) {
            return status;
        }
        status = scratch.securities_.transfer_units(
            core::SecurityId::bond(bond_id), clearing_owner, demands[index].holder,
            amount, Money(amount));
        if (!status.ok()) {
            return status;
        }
        allocated += amount;
        if (allocated >= issue - kTolerance) {
            break;
        }
    }
    status = scratch.securities_.finish_batch();
    if (!status.ok()) {
        return status;
    }
    scratch.working_metrics_.bond_issuance += allocated;
    return Status::success();
}

void measure_m6(const core::RootState &state, const M5TickScratch &monetary,
                M6Runtime &runtime, M6TickScratch &scratch, Tick tick) {
    scratch.working_metrics_.bond_outstanding_face =
        scratch.securities_.total_bond_face().value();
    scratch.working_metrics_.bond_market_value = 0.0;
    scratch.working_metrics_.firm_equity_market_cap = 0.0;
    scratch.working_metrics_.bank_equity_market_cap = 0.0;
    scratch.working_metrics_.active_security_lots = 0;
    for (const auto &lot : scratch.securities_.lots()) {
        if (lot.active) {
            ++scratch.working_metrics_.active_security_lots;
        }
    }
    for (const auto &bond : scratch.securities_.bonds()) {
        if (!bond.active) {
            continue;
        }
        const auto remaining = bond.maturity_tick.value() > tick.value()
                                   ? bond.maturity_tick.value() - tick.value()
                                   : 0;
        scratch.working_metrics_.bond_market_value += bond_price(
            bond.outstanding_face.value(), remaining,
            runtime.last_metrics.economy.policy_rate, bond.coupon_rate.value());
    }
    for (const auto &equity : scratch.securities_.equities()) {
        if (!equity.active) {
            continue;
        }
        const double market_cap = equity.outstanding_shares * equity.price.value();
        if (equity.issuer_kind == core::EquityIssuerKind::firm) {
            scratch.working_metrics_.firm_equity_market_cap += market_cap;
        } else {
            scratch.working_metrics_.bank_equity_market_cap += market_cap;
        }
    }
    scratch.working_metrics_.margin_principal = 0.0;
    for (const auto loan_id : scratch.margin_loans_) {
        if (loan_id.value() > 0 && loan_id.value() <= monetary.loans_.size()) {
            const auto &loan =
                monetary.loans_[static_cast<std::size_t>(loan_id.value() - 1)];
            if (loan.active) {
                scratch.working_metrics_.margin_principal += loan.principal.value();
            }
        }
    }
    const double shares = std::accumulate(
        scratch.securities_.equities().begin(), scratch.securities_.equities().end(),
        0.0, [](double sum, const core::EquityContract &equity) {
            return sum + (equity.active ? equity.outstanding_shares : 0.0);
        });
    scratch.working_metrics_.equity_turnover =
        shares > kEconomicEpsilon ? scratch.working_metrics_.equity_turnover / shares
                                  : 0.0;
    static_cast<void>(state);
}

[[nodiscard]] Status validate_projection(const core::RootState &state,
                                         const M4TickScratch &real,
                                         const M5TickScratch &monetary,
                                         const M6Runtime &runtime,
                                         const M6TickScratch &scratch) {
    const auto security_status =
        scratch.securities_.validate_records(state.accounting_tolerance);
    if (!security_status.ok()) {
        return security_status;
    }
    if (!finite(scratch.working_metrics_.clearing_residual) ||
        std::abs(scratch.working_metrics_.clearing_residual) > 1.0e-6) {
        return Status(ErrorCode::invariant_violation, "invariant.m6.clearing-zero");
    }
    for (const auto &exit : scratch.firm_exits_) {
        if (std::abs(projected_balance(real, exit.account)) > 1.0e-6) {
            return Status(ErrorCode::invariant_violation,
                          "invariant.m6.exited-firm-cash");
        }
        for (const auto &loan : monetary.loans_) {
            if (loan.active && loan.borrower_account == exit.account &&
                loan.principal.value() > kTolerance) {
                return Status(ErrorCode::invariant_violation,
                              "invariant.m6.exited-firm-loan");
            }
        }
    }
    const double private_net_financial_worth =
        core::neumaier_sum(real.balances_) -
        projected_balance(real, state.institutions.treasury_account) -
        std::accumulate(monetary.loans_.begin(), monetary.loans_.end(), 0.0,
                        [](double total, const core::LoanRecord &loan) {
                            return total + (loan.active ? loan.principal.value() : 0.0);
                        }) +
        scratch.securities_.total_bond_face().value();
    const double government_debt =
        scratch.securities_.total_bond_face().value() -
        projected_balance(real, state.institutions.treasury_account);
    const double expected = state.genesis_money.value() + government_debt;
    if (std::abs(private_net_financial_worth - expected) >
        1.0e-6 * std::max(1.0, std::abs(expected))) {
        return Status(ErrorCode::invariant_violation, "invariant.m6.private-nfw");
    }
    static_cast<void>(runtime);
    return Status::success();
}

void append_founder_watchlist(M6Runtime &runtime, HouseholdId founder,
                              EquityId equity) {
    std::vector<M6WatchlistRow> rows(runtime.watchlist_rows.size());
    std::vector<EquityId> values;
    values.reserve(runtime.watchlist_equities.size() + 1);
    for (std::size_t index = 1; index < runtime.watchlist_rows.size(); ++index) {
        const auto &old = runtime.watchlist_rows[index];
        if (!old.household.valid()) {
            continue;
        }
        M6WatchlistRow row;
        row.household = old.household;
        row.offset = static_cast<std::uint32_t>(values.size());
        const auto existing = household_watchlist(runtime, old.household);
        values.insert(values.end(), existing.begin(), existing.end());
        if (old.household == founder &&
            std::find(existing.begin(), existing.end(), equity) == existing.end()) {
            values.push_back(equity);
        }
        row.count = static_cast<std::uint32_t>(values.size() - row.offset);
        rows[index] = row;
    }
    runtime.watchlist_rows = std::move(rows);
    runtime.watchlist_equities = std::move(values);
}

void commit_lifecycle(core::RootState &state, M5Runtime &monetary_runtime,
                      M6Runtime &runtime, M6TickScratch &scratch) noexcept {
    for (const auto &exit : scratch.firm_exits_) {
        const auto *account = state.postings.get(exit.account);
        if (account == nullptr || !account->open ||
            std::abs(account->balance.value()) > state.accounting_tolerance) {
            std::terminate();
        }
        if (account->balance.value() != 0.0) {
            core::SettlementTransaction transaction(state);
            const double residual = account->balance.value();
            const auto transfer_status =
                residual > 0.0
                    ? transaction.transfer(
                          exit.account,
                          state.institutions.rounding_residual_account,
                          Money(residual))
                    : transaction.transfer(
                          state.institutions.rounding_residual_account,
                          exit.account,
                          Money(-residual));
            if (!transfer_status.ok() ||
                !transaction.commit_locally_validated().ok()) {
                std::terminate();
            }
        }
        static_cast<void>(state.ownership.retire_asset(core::AssetKey{
            core::AssetKind::firm_equity,
            state.economy,
            exit.firm.value(),
        }));
        if (!state.postings.close_account(exit.account).ok() ||
            !state.firms.remove(exit.firm).ok()) {
            std::terminate();
        }
    }
    for (const auto &entry : scratch.firm_entries_) {
        auto created = state.firms.create(entry.component);
        if (!created.ok() || created.get_if()->id != entry.firm) {
            std::terminate();
        }
        auto account = state.postings.create_account(
            core::AccountKey{
                core::AccountKind::deposit,
                state.economy,
                core::OwnerId::firm(entry.firm),
                state.currency,
                entry.settlement_node,
            },
            Money(0.0));
        if (!account.ok() || *account.get_if() != entry.account) {
            std::terminate();
        }
        state.firms.get(entry.firm)->primary_account = entry.account;
        core::SettlementTransaction transaction(state);
        const auto transfer = transaction.transfer(
            entry.founder_account, entry.account, Money(entry.startup_cash));
        if (!transfer.ok()) {
            std::terminate();
        }
        const auto committed = transaction.commit();
        if (!committed.ok()) {
            std::terminate();
        }
        append_founder_watchlist(runtime, entry.founder, entry.equity);
    }
    for (const auto &entry : scratch.bank_entries_) {
        auto created = state.banks.create(entry.component);
        if (!created.ok() || created.get_if()->id != entry.bank) {
            std::terminate();
        }
        auto node = state.reserves.create_position(entry.bank, Money(0.0));
        if (!node.ok() || *node.get_if() != entry.settlement_node) {
            std::terminate();
        }
        auto account = state.postings.create_account(
            core::AccountKey{
                core::AccountKind::bank_cash,
                state.economy,
                core::OwnerId::bank(entry.bank),
                state.currency,
                entry.settlement_node,
            },
            Money(0.0), true);
        if (!account.ok() || *account.get_if() != entry.account) {
            std::terminate();
        }
        auto *bank = state.banks.get(entry.bank);
        bank->cash_account = entry.account;
        bank->settlement_node = entry.settlement_node;
        auto pnl = state.bank_pnl.records();
        auto capital = state.bank_capital.records();
        pnl.push_back(entry.pnl);
        capital.push_back(entry.bank_capital);
        state.bank_pnl.replace_records(pnl);
        state.bank_capital.replace_records(capital);
        core::SettlementTransaction transaction(state);
        const auto transfer_status = transaction.transfer(
            entry.founder_account, entry.account, Money(entry.capital));
        if (!transfer_status.ok()) {
            std::terminate();
        }
        const auto committed = transaction.commit();
        if (!committed.ok()) {
            std::terminate();
        }
    }
    monetary_runtime.last_metrics.alive_banks = 0;
    for (const auto &capital : state.bank_capital.records()) {
        if (capital.alive) {
            ++monetary_runtime.last_metrics.alive_banks;
        }
    }
}

class M6Extension final : public M5TickExtension {
  public:
    M6Extension(M6Runtime &runtime, M6TickScratch &scratch,
                const M6AdvanceOptions &options, M6TickExtension *extension) noexcept
        : runtime_(runtime), scratch_(scratch), options_(options),
          extension_(extension) {}

    ~M6Extension() override {
        if (memory_efficient_staging_ && !committed_) {
            runtime_.securities = std::move(scratch_.securities_);
            runtime_.firms = std::move(scratch_.firms_);
            runtime_.margin_loans = std::move(scratch_.margin_loans_);
        }
    }

    Status prepare_tick(const core::RootState &state, M4Runtime &real_runtime,
                        M4TickScratch &real, M5Runtime &monetary_runtime,
                        M5TickScratch &monetary, Tick tick, PhiloxRng &rng) override {
        memory_efficient_staging_ =
            options_.base.base.memory_efficient_staging;
        opening_security_version_ = runtime_.securities.version();
        if (memory_efficient_staging_) {
            scratch_.securities_ = std::move(runtime_.securities);
            scratch_.firms_ = std::move(runtime_.firms);
            scratch_.margin_loans_ = std::move(runtime_.margin_loans);
        } else {
            scratch_.securities_ = runtime_.securities;
            scratch_.firms_ = runtime_.firms;
            scratch_.margin_loans_ = runtime_.margin_loans;
        }
        scratch_.securities_.clear_household_position_changes();
        scratch_.orders_.clear();
        scratch_.firm_exits_.clear();
        scratch_.firm_entries_.clear();
        scratch_.bank_entries_.clear();
        scratch_.working_metrics_ = M6Metrics{};
        lifecycle_counter_ = runtime_.lifecycle_rng_counter;
        security_counter_ = runtime_.security_rng_counter;
        open_bank_security_books(state, scratch_.securities_, monetary);
        auto status = run_bond_open(state, real, monetary, scratch_, tick);
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->prepare_tick(state, real_runtime, real, monetary_runtime,
                                        monetary, runtime_, scratch_, tick, rng);
    }

    Status after_planning(const core::RootState &, M4Runtime &, M4TickScratch &,
                          M5Runtime &, M5TickScratch &, Tick, PhiloxRng &) override {
        return Status::success();
    }

    Status run_labor(const core::RootState &state, M4Runtime &real_runtime,
                     M4TickScratch &real, M5Runtime &monetary_runtime,
                     M5TickScratch &monetary, Tick tick, PhiloxRng &rng,
                     bool &handled) override {
        handled = false;
        if (extension_ == nullptr) {
            return Status::success();
        }
        return extension_->run_labor(state, real_runtime, real, monetary_runtime,
                                     monetary, runtime_, scratch_, tick, rng, handled);
    }

    Status before_settlement(const core::RootState &, M4Runtime &, M4TickScratch &,
                             M5Runtime &, M5TickScratch &, Tick, PhiloxRng &) override {
        return Status::success();
    }

    Status after_settlement(const core::RootState &, M4Runtime &, M4TickScratch &,
                            M5Runtime &, M5TickScratch &, Tick, PhiloxRng &) override {
        return Status::success();
    }

    Status before_bank_resolution(const core::RootState &state, M4Runtime &,
                                  M4TickScratch &real, M5Runtime &monetary_runtime,
                                  M5TickScratch &monetary, Tick tick,
                                  PhiloxRng &) override {
        build_firm_statements(state, real, monetary, runtime_, scratch_);
        auto status = update_equity_fundamentals(state, monetary_runtime, monetary,
                                                 runtime_, scratch_);
        if (!status.ok()) {
            return status;
        }
        scratch_.orders_.clear();
        std::uint64_t ordinal = 0;
        if (runtime_.rules.firm_equity) {
            generate_firm_equity_orders(state, real, monetary_runtime, monetary,
                                        runtime_, scratch_, tick, ordinal,
                                        options_.base.credit_supply_multiplier);
        }
        if (runtime_.rules.bank_equity && runtime_.rules.bank_equity_trading) {
            generate_bank_equity_orders(state, real, runtime_, scratch_, tick,
                                        ordinal);
        }
        status = clear_equity_orders(state, real, monetary, runtime_, scratch_);
        if (!status.ok()) {
            return status;
        }
        status = service_margin(state, real, monetary, runtime_, scratch_);
        if (!status.ok()) {
            return status;
        }
        return run_firm_exits(state, real, monetary, runtime_, scratch_, options_);
    }

    Status close_institutions(const core::RootState &state, M4Runtime &real_runtime,
                              M4TickScratch &real, M5Runtime &monetary_runtime,
                              M5TickScratch &monetary, Tick tick,
                              PhiloxRng &rng) override {
        auto status = resolve_dead_bank_equity(state, monetary, scratch_);
        if (!status.ok()) {
            return status;
        }
        run_sector_switching(state, real, runtime_, scratch_, lifecycle_counter_);
        status =
            stage_firm_entries(state, real, runtime_, scratch_, lifecycle_counter_);
        if (!status.ok()) {
            return status;
        }
        status =
            stage_bank_entries(state, real, monetary_runtime, monetary, runtime_,
                               scratch_, lifecycle_counter_, options_.force_bank_entry);
        if (!status.ok()) {
            return status;
        }
        status = run_bond_issuance(state, real, monetary, runtime_, scratch_, tick);
        if (!status.ok()) {
            return status;
        }
        close_bank_security_books(state, real, scratch_.securities_, monetary);
        status = scratch_.securities_.compact_inactive_lots();
        if (!status.ok()) {
            return status;
        }
        measure_m6(state, monetary, runtime_, scratch_, tick);
        if (extension_ == nullptr) {
            return Status::success();
        }
        return extension_->close_day(state, real_runtime, real, monetary_runtime,
                                     monetary, runtime_, scratch_, tick, rng);
    }

    Status validate(const core::RootState &state, const M4Runtime &real_runtime,
                    const M4TickScratch &real, const M5Runtime &monetary_runtime,
                    const M5TickScratch &monetary, Tick tick) const override {
        const auto status =
            validate_projection(state, real, monetary, runtime_, scratch_);
        if (!status.ok() || extension_ == nullptr) {
            return status;
        }
        return extension_->validate(state, real_runtime, real, monetary_runtime,
                                    monetary, runtime_, scratch_, tick);
    }

    void commit(core::RootState &state, M4Runtime &real_runtime, M4TickScratch &real,
                M5Runtime &monetary_runtime, M5TickScratch &monetary, Tick tick,
                const M5Metrics &metrics) noexcept override {
        const auto next_security_version = scratch_.securities_.version();
        if (next_security_version >= opening_security_version_) {
            security_counter_ += next_security_version - opening_security_version_;
        }
        if (memory_efficient_staging_) {
            runtime_.securities = std::move(scratch_.securities_);
            runtime_.firms = std::move(scratch_.firms_);
            runtime_.margin_loans = std::move(scratch_.margin_loans_);
        } else {
            std::swap(runtime_.securities, scratch_.securities_);
            std::swap(runtime_.firms, scratch_.firms_);
            std::swap(runtime_.margin_loans, scratch_.margin_loans_);
        }
        runtime_.lifecycle_rng_counter = lifecycle_counter_;
        runtime_.security_rng_counter = security_counter_;
        scratch_.working_metrics_.economy = metrics;
        runtime_.last_metrics = scratch_.working_metrics_;
        commit_lifecycle(state, monetary_runtime, runtime_, scratch_);
        if (extension_ != nullptr) {
            extension_->commit(state, real_runtime, real, monetary_runtime, monetary,
                               runtime_, scratch_, tick, runtime_.last_metrics);
        }
        committed_ = true;
    }

  private:
    M6Runtime &runtime_;
    M6TickScratch &scratch_;
    const M6AdvanceOptions &options_;
    M6TickExtension *extension_{nullptr};
    std::uint64_t lifecycle_counter_{0};
    std::uint64_t security_counter_{0};
    std::uint64_t opening_security_version_{0};
    bool memory_efficient_staging_{false};
    bool committed_{false};
};

[[nodiscard]] core::EquityContract
initial_firm_equity(const core::RootState &state, const M6Rules &rules, FirmId firm_id,
                    const core::FirmComponent &firm, double book) {
    const double price = std::max(kEconomicEpsilon, book / rules.shares_per_firm);
    core::EquityContract contract;
    contract.issuer_kind = core::EquityIssuerKind::firm;
    contract.issuer = core::OwnerId::firm(firm_id);
    contract.issuer_account = firm.primary_account;
    contract.currency = state.currency;
    contract.outstanding_shares = rules.shares_per_firm;
    contract.price = Price(price);
    contract.last_price = Price(price);
    contract.peak_price = Price(price);
    contract.fundamental = Price(price);
    return contract;
}

void build_genesis_watchlists(const core::RootState &state,
                              const std::vector<FirmId> &firms, const M6Rules &rules,
                              M6Runtime &runtime) {
    runtime.watchlist_rows.resize(
        static_cast<std::size_t>(state.households.allocator_state().next_id));
    const auto count = std::min<std::size_t>(rules.watchlist_size, firms.size());
    runtime.watchlist_equities.reserve(state.households.alive_count() * count);
    state.households.for_each_alive([&](HouseholdId household,
                                        const core::HouseholdComponent &) {
        std::vector<std::size_t> candidates(firms.size());
        std::iota(candidates.begin(), candidates.end(), 0);
        std::uint64_t random_state =
            splitmix64(state.seed ^ household.value() ^ 0x57415443484c4953ULL);
        for (std::size_t index = 0; index < count; ++index) {
            random_state = splitmix64(random_state);
            const auto selected =
                index +
                static_cast<std::size_t>(random_state % (candidates.size() - index));
            std::swap(candidates[index], candidates[selected]);
        }
        auto &row = runtime.watchlist_rows[static_cast<std::size_t>(household.value())];
        row.household = household;
        row.offset = static_cast<std::uint32_t>(runtime.watchlist_equities.size());
        row.count = static_cast<std::uint32_t>(count);
        for (std::size_t index = 0; index < count; ++index) {
            runtime.watchlist_equities.push_back(EquityId(candidates[index] + 1));
        }
    });
}

} // namespace

double bond_price(double face, std::uint64_t remaining_days, double required_return,
                  double coupon_rate) noexcept {
    if (!finite(face) || !finite(required_return) || !finite(coupon_rate) ||
        face < 0.0 || coupon_rate < 0.0 || required_return <= -1.0 ||
        remaining_days == 0) {
        return std::max(0.0, face);
    }
    if (remaining_days == 1 && coupon_rate <= kEconomicEpsilon) {
        return face;
    }
    const double discount = 1.0 / (1.0 + required_return);
    const double periods = static_cast<double>(remaining_days);
    const double principal = face * std::pow(discount, periods);
    const double coupons = std::abs(required_return) <= 1.0e-12
                               ? coupon_rate * face * periods
                               : coupon_rate * face *
                                     (1.0 - std::pow(discount, periods)) /
                                     required_return;
    const double result = principal + coupons;
    return finite(result) ? std::max(0.0, result) : face;
}

double equity_discount_rate(const M5Runtime &monetary_runtime,
                            const M6Rules &rules) noexcept {
    return std::max(rules.valuation_discount_floor,
                    std::max(0.0, monetary_runtime.policy_rate) +
                        rules.valuation_risk_premium);
}

double residual_income_fundamental(double book_value, double residual_income,
                                   double shares, double discount_rate) noexcept {
    if (!finite(book_value) || !finite(residual_income) || !finite(shares) ||
        !finite(discount_rate) || shares <= kEconomicEpsilon) {
        return 0.0;
    }
    const double discount = std::max(kEconomicEpsilon, discount_rate);
    return std::max(0.0,
                    (book_value + std::max(0.0, residual_income) / discount) / shares);
}

Status validate_m6_policy(const M6PolicyState &policy) noexcept {
    const std::array values{
        policy.bond_finance_fraction,
        policy.bond_coupon_rate,
        policy.household_bond_target,
        policy.bank_bond_appetite,
        policy.bank_bond_duration_limit,
        policy.margin_ltv,
        policy.margin_max,
        policy.bank_minimum_capital,
    };
    if (!all_finite(values) || policy.bond_finance_fraction < 0.0 ||
        policy.bond_finance_fraction > 1.0 || policy.bond_coupon_rate < 0.0 ||
        policy.bond_maturity_days == 0 || policy.household_bond_target < 0.0 ||
        policy.household_bond_target > 1.0 || policy.bank_bond_appetite < 0.0 ||
        policy.bank_bond_appetite > 1.0 || policy.bank_bond_duration_limit < 0.0 ||
        policy.margin_ltv < 0.0 || policy.margin_ltv >= 1.0 ||
        policy.margin_max < 1.0 || policy.bank_minimum_capital < 0.0) {
        return Status(ErrorCode::invalid_argument, "M6 policy is invalid");
    }
    return Status::success();
}

Status validate_m6_rules(const M6Rules &rules) noexcept {
    struct RuleView final {
        const M6Rules &rules;
    };
    const RuleView spec{rules};
    const std::array values{
        spec.rules.shares_per_firm,
        spec.rules.genesis_founder_pool,
        spec.rules.equity_price_adjustment,
        spec.rules.equity_trend_lambda,
        spec.rules.residual_income_lambda,
        spec.rules.q_smoothing,
        spec.rules.fundamental_weight,
        spec.rules.chartist_weight,
        spec.rules.household_equity_target,
        spec.rules.portfolio_adjustment,
        spec.rules.equity_issue_lambda,
        spec.rules.valuation_discount_floor,
        spec.rules.valuation_risk_premium,
        spec.rules.capital_haircut,
        spec.rules.inventory_haircut,
        spec.rules.entry_hurdle,
        spec.rules.entry_beta,
        spec.rules.startup_deposits,
        spec.rules.startup_capital,
        spec.rules.switch_return_gap,
        spec.rules.switch_hazard,
        spec.rules.switch_retool_loss,
        spec.rules.bank_shares,
        spec.rules.bank_equity_lambda,
        spec.rules.bank_equity_target,
        spec.rules.bank_entry_beta,
    };
    if (!all_finite(values) || spec.rules.bond_maturity_bucket == 0 ||
        spec.rules.portfolio_review_interval_days == 0U ||
        spec.rules.shares_per_firm <= 0.0 || spec.rules.watchlist_size > 100'000 ||
        spec.rules.genesis_founder_pool <= 0.0 ||
        spec.rules.genesis_founder_pool > 1.0 ||
        spec.rules.equity_price_adjustment < 0.0 ||
        spec.rules.equity_trend_lambda < 0.0 || spec.rules.equity_trend_lambda > 1.0 ||
        spec.rules.residual_income_lambda < 0.0 ||
        spec.rules.residual_income_lambda > 1.0 || spec.rules.q_smoothing < 0.0 ||
        spec.rules.q_smoothing > 1.0 || spec.rules.fundamental_weight < 0.0 ||
        spec.rules.chartist_weight < 0.0 || spec.rules.household_equity_target < 0.0 ||
        spec.rules.household_equity_target > 1.0 ||
        spec.rules.portfolio_adjustment < 0.0 ||
        spec.rules.portfolio_adjustment > 1.0 || spec.rules.equity_issue_lambda < 0.0 ||
        spec.rules.valuation_discount_floor <= 0.0 ||
        spec.rules.valuation_risk_premium < 0.0 || spec.rules.capital_haircut < 0.0 ||
        spec.rules.capital_haircut > 1.0 || spec.rules.inventory_haircut < 0.0 ||
        spec.rules.inventory_haircut > 1.0 || spec.rules.bankrupt_persistence == 0 ||
        spec.rules.shell_exit_days == 0 || spec.rules.entry_hurdle < 0.0 ||
        spec.rules.entry_beta < 0.0 || spec.rules.startup_deposits < 0.0 ||
        spec.rules.startup_capital < 0.0 || spec.rules.switch_return_gap < 0.0 ||
        spec.rules.switch_pressure_days == 0 || spec.rules.switch_hazard < 0.0 ||
        spec.rules.switch_hazard > 1.0 || spec.rules.switch_retool_loss < 0.0 ||
        spec.rules.switch_retool_loss > 1.0 || spec.rules.bank_shares <= 0.0 ||
        spec.rules.bank_equity_lambda < 0.0 || spec.rules.bank_equity_lambda > 1.0 ||
        spec.rules.bank_equity_target < 0.0 || spec.rules.bank_equity_target > 1.0 ||
        spec.rules.bank_entry_beta < 0.0 ||
        (spec.rules.margin_credit && !spec.rules.firm_equity) ||
        (spec.rules.equity_finance && !spec.rules.firm_equity) ||
        (spec.rules.sector_switching && !spec.rules.consumption_strata)) {
        return Status(ErrorCode::invalid_argument, "M6 rules are invalid");
    }
    return Status::success();
}

Status validate_m6_spec(const M6SimulationSpec &spec) noexcept {
    const auto base = validate_m5_spec(spec.monetary_economy);
    if (!base.ok()) {
        return base;
    }
    const auto policy = validate_m6_policy(spec.policy);
    if (!policy.ok()) {
        return policy;
    }
    return validate_m6_rules(spec.rules);
}

Status validate_m6_state_fast(const core::RootState &state,
                              const M4Runtime &real_economy_runtime,
                              const M5Runtime &monetary_runtime,
                              const M6Runtime &runtime, Tick tick) noexcept {
    if (!validate_m6_policy(runtime.policy).ok() ||
        !validate_m6_rules(runtime.rules).ok() ||
        !runtime.securities.validate_records(state.accounting_tolerance).ok() ||
        !finite(runtime.replacement_capital_price) ||
        runtime.replacement_capital_price <= 0.0) {
        return Status(ErrorCode::invariant_violation, "M6 persistent state is invalid");
    }
    for (const auto &bond : runtime.securities.bonds()) {
        if (!bond.active) {
            continue;
        }
        const auto account = owner_account(state, bond.issuer);
        const auto *posting = state.postings.get(account);
        if (bond.currency != state.currency || account != bond.issuer_account ||
            posting == nullptr || !posting->open) {
            return Status(ErrorCode::invariant_violation,
                          "M6 bond issuer reference is invalid");
        }
    }
    for (const auto &equity : runtime.securities.equities()) {
        if (!equity.active) {
            continue;
        }
        const bool issuer_kind_matches =
            (equity.issuer_kind == core::EquityIssuerKind::firm &&
             equity.issuer.kind == core::OwnerKind::firm) ||
            (equity.issuer_kind == core::EquityIssuerKind::bank &&
             equity.issuer.kind == core::OwnerKind::bank);
        const auto account = owner_account(state, equity.issuer);
        const auto *posting = state.postings.get(account);
        if (!issuer_kind_matches || equity.currency != state.currency ||
            account != equity.issuer_account || posting == nullptr || !posting->open) {
            return Status(ErrorCode::invariant_violation,
                          "M6 equity issuer reference is invalid");
        }
    }
    for (const auto &lot : runtime.securities.lots()) {
        if (!lot.active) {
            continue;
        }
        const auto account = owner_account(state, lot.holder);
        const auto *posting = state.postings.get(account);
        if (!account.valid() || posting == nullptr || !posting->open) {
            return Status(ErrorCode::invariant_violation,
                          "M6 security holder reference is invalid");
        }
    }
    bool firms_valid = true;
    state.firms.for_each_alive([&](FirmId id, const core::FirmComponent &) {
        const auto *record = firm_record(runtime.firms, id);
        firms_valid =
            firms_valid && record != nullptr && record->active && record->firm == id &&
            record->statement.firm == id && finite(record->statement.book_equity) &&
            finite(record->residual_income_ema) && finite(record->tobin_q_ema);
    });
    for (const auto &record : runtime.firms) {
        if (record.active && state.firms.get(record.firm) == nullptr) {
            firms_valid = false;
        }
    }
    if (!firms_valid) {
        return Status(ErrorCode::invariant_violation,
                      "M6 firm lifecycle state is inconsistent");
    }
    for (std::size_t index = 1; index < runtime.watchlist_rows.size(); ++index) {
        const auto &row = runtime.watchlist_rows[index];
        if (!row.household.valid()) {
            continue;
        }
        if (row.household.value() != index ||
            state.households.get(row.household) == nullptr ||
            static_cast<std::size_t>(row.offset) + row.count >
                runtime.watchlist_equities.size()) {
            return Status(ErrorCode::invariant_violation,
                          "M6 watchlist state is inconsistent");
        }
        for (const auto equity : household_watchlist(runtime, row.household)) {
            if (runtime.securities.get(equity) == nullptr) {
                return Status(ErrorCode::invariant_violation,
                              "M6 watchlist references an absent equity");
            }
        }
    }
    for (const auto loan : runtime.margin_loans) {
        if (loan.value() == 0 || loan.value() > state.loans.records().size()) {
            return Status(ErrorCode::invariant_violation,
                          "M6 margin loan reference is invalid");
        }
    }
    return validate_m5_state(state, real_economy_runtime, monetary_runtime, tick);
}

Status validate_m6_state(const core::RootState &state,
                         const M4Runtime &real_economy_runtime,
                         const M5Runtime &monetary_runtime, const M6Runtime &runtime,
                         Tick tick) noexcept {
    const auto records = validate_m6_state_fast(state, real_economy_runtime,
                                                monetary_runtime, runtime, tick);
    return records.ok() ? runtime.securities.validate_indexes() : records;
}

Result<M6Initialization> build_m6_genesis(const M6SimulationSpec &spec) {
    const auto validation = validate_m6_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    auto base = build_m5_genesis(spec.monetary_economy);
    if (!base.ok()) {
        return base.status();
    }
    auto value = std::move(*base.get_if());
    M6Runtime runtime;
    runtime.policy = spec.policy;
    runtime.rules = spec.rules;
    runtime.replacement_capital_price =
        spec.monetary_economy.real_economy.rules.initial_capital_price;
    runtime.firms.resize(
        static_cast<std::size_t>(value.root.firms.allocator_state().next_id));
    std::vector<FirmId> equity_firms;
    value.root.firms.for_each_alive([&](FirmId id, const core::FirmComponent &firm) {
        FirmLifecycleRecord lifecycle;
        lifecycle.firm = id;
        lifecycle.statement.firm = id;
        lifecycle.statement.cash =
            value.root.postings.get(firm.primary_account)->balance.value();
        lifecycle.statement.capital_units = firm.physical_capital.value();
        lifecycle.statement.capital_unit_price = runtime.replacement_capital_price;
        lifecycle.statement.capital_value =
            lifecycle.statement.capital_units * lifecycle.statement.capital_unit_price;
        lifecycle.statement.output_inventory_units = firm.goods_inventory.value();
        lifecycle.statement.output_inventory_unit_price = firm.posted_price.value();
        lifecycle.statement.output_inventory_value =
            lifecycle.statement.output_inventory_units *
            lifecycle.statement.output_inventory_unit_price;
        lifecycle.statement.inventory_value =
            lifecycle.statement.output_inventory_value;
        lifecycle.statement.gross_assets = lifecycle.statement.cash +
                                           lifecycle.statement.capital_value +
                                           lifecycle.statement.inventory_value;
        lifecycle.statement.book_equity = lifecycle.statement.gross_assets;
        lifecycle.statement.eligible_collateral_value =
            (1.0 - runtime.rules.capital_haircut) * lifecycle.statement.capital_value +
            (1.0 - runtime.rules.inventory_haircut) *
                lifecycle.statement.inventory_value;
        lifecycle.statement.borrowing_base_proxy =
            lifecycle.statement.cash + lifecycle.statement.eligible_collateral_value;
        lifecycle.statement.borrowing_base_headroom =
            lifecycle.statement.borrowing_base_proxy;
        lifecycle.stratum = id.value() % 2 == 0 ? ConsumptionStratum::luxury
                                                : ConsumptionStratum::necessity;
        lifecycle.active = true;
        runtime.firms[static_cast<std::size_t>(id.value())] = lifecycle;
        if (firm.sector == core::FirmSector::consumption && runtime.rules.firm_equity) {
            equity_firms.push_back(id);
        }
    });
    build_genesis_watchlists(value.root, equity_firms, runtime.rules, runtime);
    std::vector<std::vector<HouseholdId>> watchers(equity_firms.size());
    for (std::size_t household_index = 1;
         household_index < runtime.watchlist_rows.size(); ++household_index) {
        const auto &row = runtime.watchlist_rows[household_index];
        if (!row.household.valid()) {
            continue;
        }
        for (const auto equity : household_watchlist(runtime, row.household)) {
            if (equity.value() > 0 && equity.value() <= watchers.size()) {
                watchers[static_cast<std::size_t>(equity.value() - 1)].push_back(
                    row.household);
            }
        }
    }
    auto securities_batch = runtime.securities.begin_batch();
    if (!securities_batch.ok()) {
        return securities_batch;
    }
    for (std::size_t index = 0; index < equity_firms.size(); ++index) {
        const auto firm_id = equity_firms[index];
        const auto *firm = value.root.firms.get(firm_id);
        const auto *lifecycle = firm_record(runtime.firms, firm_id);
        auto contract = initial_firm_equity(value.root, runtime.rules, firm_id, *firm,
                                            lifecycle->statement.book_equity);
        std::vector<core::InitialSecurityHolding> holdings;
        if (runtime.rules.founder_owned_genesis) {
            const auto founder_count = std::max<std::uint64_t>(
                1, static_cast<std::uint64_t>(
                       runtime.rules.genesis_founder_pool *
                       static_cast<double>(value.root.households.alive_count())));
            const auto founder = HouseholdId(1 + (index % founder_count));
            holdings.push_back({
                core::OwnerId::household(founder),
                runtime.rules.shares_per_firm,
                Money(lifecycle->statement.book_equity),
            });
        } else {
            auto owners = watchers[index];
            if (owners.empty()) {
                owners.push_back(HouseholdId(1));
            }
            const double shares =
                runtime.rules.shares_per_firm / static_cast<double>(owners.size());
            double assigned = 0.0;
            for (std::size_t owner = 0; owner < owners.size(); ++owner) {
                const double units = owner + 1 == owners.size()
                                         ? runtime.rules.shares_per_firm - assigned
                                         : shares;
                assigned += units;
                holdings.push_back({
                    core::OwnerId::household(owners[owner]),
                    units,
                    Money(lifecycle->statement.book_equity * units /
                          runtime.rules.shares_per_firm),
                });
            }
        }
        const auto created = runtime.securities.create_equity(contract, holdings);
        if (!created.ok()) {
            return created.status();
        }
    }
    Status bank_equity_status = Status::success();
    if (runtime.rules.bank_equity) {
        value.root.banks.for_each_alive([&](BankId bank_id,
                                            const core::BankComponent &bank) {
            if (!bank_equity_status.ok()) {
                return;
            }
            const auto *capital = value.root.bank_capital.get(bank_id);
            const double book =
                capital != nullptr ? std::max(0.0, capital->closing_capital) : 0.0;
            core::EquityContract contract;
            contract.issuer_kind = core::EquityIssuerKind::bank;
            contract.issuer = core::OwnerId::bank(bank_id);
            contract.issuer_account = bank.cash_account;
            contract.currency = value.root.currency;
            contract.outstanding_shares = runtime.rules.bank_shares;
            const double price =
                std::max(kEconomicEpsilon, book / runtime.rules.bank_shares);
            contract.price = Price(price);
            contract.last_price = Price(price);
            contract.peak_price = Price(price);
            contract.fundamental = Price(price);
            const auto founder = HouseholdId(
                1 + ((bank_id.value() - 1) % value.root.households.alive_count()));
            const std::array holding{core::InitialSecurityHolding{
                core::OwnerId::household(founder),
                runtime.rules.bank_shares,
                Money(book),
            }};
            const auto created = runtime.securities.create_equity(contract, holding);
            if (!created.ok()) {
                bank_equity_status = created.status();
            }
        });
    }
    if (!bank_equity_status.ok()) {
        return bank_equity_status;
    }
    securities_batch = runtime.securities.finish_batch();
    if (!securities_batch.ok()) {
        return securities_batch;
    }
    runtime.last_metrics.economy = value.runtime.last_metrics;
    runtime.last_metrics.bond_outstanding_face = 0.0;
    const auto state_validation = validate_m6_state(
        value.root, value.real_economy_runtime, value.runtime, runtime, Tick(0));
    if (!state_validation.ok()) {
        return state_validation;
    }
    runtime.securities.clear_household_position_changes();
    return M6Initialization{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        std::move(value.runtime),
        std::move(runtime),
    };
}

void M6TickScratch::reserve(const core::RootState &state, const M6Runtime &runtime) {
    firms_.reserve(runtime.firms.size() + 16);
    orders_.reserve(state.households.alive_count() *
                    static_cast<std::size_t>(runtime.rules.watchlist_size +
                                             state.banks.alive_count()));
    order_bucket_offsets_.reserve(runtime.securities.equities().size() + 2U);
    buyers_.reserve(state.households.alive_count());
    sellers_.reserve(state.households.alive_count());
    bank_equities_.reserve(state.banks.alive_count());
    bond_demands_.reserve(state.households.alive_count() + state.banks.alive_count());
    const auto observation_width =
        std::max<std::size_t>(runtime.rules.watchlist_size, state.banks.alive_count());
    watch_current_.reserve(observation_width);
    watch_attractiveness_.reserve(observation_width);
    margin_loans_.reserve(runtime.margin_loans.size() + state.households.alive_count());
    debt_by_account_.resize(state.postings.size() + 1);
    margin_by_account_.resize(state.postings.size() + 1);
    firm_return_.resize(
        static_cast<std::size_t>(state.firms.allocator_state().next_id));
    firm_exits_.reserve(state.firms.alive_count());
    firm_entries_.reserve(runtime.rules.entry_max);
    bank_entries_.reserve(runtime.rules.bank_entry_max);
}

std::uint64_t M6TickScratch::capacity_signature() const noexcept {
    std::uint64_t signature = 1469598103934665603ULL;
    const std::array capacities{
        firms_.capacity(),
        orders_.capacity(),
        ordered_orders_.capacity(),
        order_bucket_offsets_.capacity(),
        buyers_.capacity(),
        sellers_.capacity(),
        bank_equities_.capacity(),
        bond_demands_.capacity(),
        watch_current_.capacity(),
        watch_attractiveness_.capacity(),
        margin_loans_.capacity(),
        debt_by_account_.capacity(),
        margin_by_account_.capacity(),
        firm_return_.capacity(),
        firm_exits_.capacity(),
        firm_entries_.capacity(),
        bank_entries_.capacity(),
    };
    for (const auto capacity : capacities) {
        signature ^= static_cast<std::uint64_t>(capacity);
        signature *= 1099511628211ULL;
    }
    return signature;
}

Result<M6AdvanceResult>
advance_m6_ticks_impl(core::RootState &state, M4Runtime &real_economy_runtime,
                      M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                      M5TickScratch &monetary_scratch, M6Runtime &runtime,
                      M6TickScratch &scratch, Tick &tick, std::uint64_t count,
                      M6TickExtension *tick_extension,
                      const M6AdvanceOptions &options) {
    if (count == 0) {
        return M6AdvanceResult{
            tick, tick, 0, runtime.last_metrics, scratch.capacity_signature(), 0, 0,
        };
    }
    if (!validate_m6_state_fast(state, real_economy_runtime, monetary_runtime, runtime,
                                tick)
             .ok()) {
        return Status(ErrorCode::invariant_violation,
                      "M6 cannot advance an invalid state");
    }
    M6Extension extension(runtime, scratch, options, tick_extension);
    auto result = advance_m5_ticks_extended(
        state, real_economy_runtime, real_economy_scratch, monetary_runtime,
        monetary_scratch, tick, count, extension, options.base);
    if (!result.ok()) {
        return result.status();
    }
    const auto &base = *result.get_if();
    return M6AdvanceResult{
        base.first_tick,
        base.next_tick,
        base.advanced_ticks,
        runtime.last_metrics,
        scratch.capacity_signature(),
        base.transfer_count,
        base.trade_count,
    };
}

Result<M6AdvanceResult>
advance_m6_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &runtime,
                 M6TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M6AdvanceOptions &options) {
    return advance_m6_ticks_impl(state, real_economy_runtime, real_economy_scratch,
                                 monetary_runtime, monetary_scratch, runtime, scratch,
                                 tick, count, nullptr, options);
}

Result<M6AdvanceResult>
advance_m6_ticks_extended(core::RootState &state, M4Runtime &real_economy_runtime,
                          M4TickScratch &real_economy_scratch,
                          M5Runtime &monetary_runtime, M5TickScratch &monetary_scratch,
                          M6Runtime &runtime, M6TickScratch &scratch, Tick &tick,
                          std::uint64_t count, M6TickExtension &extension,
                          const M6AdvanceOptions &options) {
    return advance_m6_ticks_impl(state, real_economy_runtime, real_economy_scratch,
                                 monetary_runtime, monetary_scratch, runtime, scratch,
                                 tick, count, &extension, options);
}

} // namespace macro_sim::simulation
