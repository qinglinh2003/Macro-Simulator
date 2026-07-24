#include "macro_sim/simulation/m4.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numeric>
#include <span>
#include <utility>

#include "macro_sim/algorithms/behavior.hpp"
#include "macro_sim/core/accounting.hpp"

namespace macro_sim::simulation {
namespace {

constexpr double kTolerance = 1.0e-8;
constexpr double kDaysPerYear = 365.0;
constexpr std::uint64_t kV1Capabilities =
    capability_bit(M4Capability::physical_capital)
    | capability_bit(M4Capability::government);
constexpr std::uint64_t kUnsupportedCapabilities =
    capability_bit(M4Capability::credit)
    | capability_bit(M4Capability::commercial_banks)
    | capability_bit(M4Capability::central_bank)
    | capability_bit(M4Capability::securities)
    | capability_bit(M4Capability::equity)
    | capability_bit(M4Capability::demographics)
    | capability_bit(M4Capability::persistent_labor)
    | capability_bit(M4Capability::energy)
    | capability_bit(M4Capability::housing)
    | capability_bit(M4Capability::open_economy)
    | capability_bit(M4Capability::stateful_shocks)
    | capability_bit(M4Capability::controllers)
    | capability_bit(M4Capability::reinforcement_learning);

[[nodiscard]] bool all_finite(std::span<const double> values) noexcept {
    return std::all_of(
        values.begin(),
        values.end(),
        [](double value) { return std::isfinite(value); }
    );
}

[[nodiscard]] algorithms::ProductionTechnology technology_for(
    core::FirmTechnology technology
) noexcept {
    return technology == core::FirmTechnology::linear
        ? algorithms::ProductionTechnology::linear
        : algorithms::ProductionTechnology::cobb_douglas;
}

[[nodiscard]] double sum_balances(
    const M4TickScratch& scratch
) noexcept {
    return core::neumaier_sum(scratch.balances_);
}

[[nodiscard]] Status transfer(
    const core::RootState& state,
    M4TickScratch& scratch,
    AccountId source,
    AccountId destination,
    double amount
) noexcept {
    if (!std::isfinite(amount) || amount < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M4 transfer amount must be finite and nonnegative"
        );
    }
    if (amount <= algorithms::kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto* source_record = state.postings.get(source);
    const auto* destination_record = state.postings.get(destination);
    if (source_record == nullptr || destination_record == nullptr
        || !source_record->open || !destination_record->open) {
        return Status(ErrorCode::not_found, "M4 transfer account is absent");
    }
    const auto source_index = static_cast<std::size_t>(source.value());
    const auto destination_index =
        static_cast<std::size_t>(destination.value());
    if (source_index >= scratch.balances_.size()
        || destination_index >= scratch.balances_.size()) {
        return Status(
            ErrorCode::internal_error,
            "M4 account projection is stale"
        );
    }
    if (!source_record->allow_negative
        && scratch.balances_[source_index] + kTolerance < amount) {
        return Status(
            ErrorCode::insufficient_funds,
            "M4 transfer exceeds available money"
        );
    }
    scratch.balances_[source_index] -= amount;
    scratch.balances_[destination_index] += amount;
    ++scratch.transfer_count_;
    return Status::success();
}

[[nodiscard]] Status check_fault(
    const M4AdvanceOptions& options,
    M4Phase phase
) noexcept {
    if (options.fault_before_phase.has_value()
        && *options.fault_before_phase == phase) {
        return Status(ErrorCode::internal_error, "injected M4 phase fault");
    }
    return Status::success();
}

void capture_phase(
    const core::RootState& state,
    M4TickScratch& scratch,
    const M4AdvanceOptions& options,
    M4Phase phase
) {
    if (!options.capture_phase_trace) {
        return;
    }
    double goods = 0.0;
    double capital = 0.0;
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        goods += scratch.firm_work_[index].closing_inventory;
        capital += scratch.firm_work_[index].closing_capital;
    }
    scratch.phase_trace_.push_back(
        {
            phase,
            sum_balances(scratch),
            goods,
            capital,
            scratch.transfer_count_,
            scratch.trade_count_,
        }
    );
    static_cast<void>(state);
}

[[nodiscard]] Status validate_working_state(
    const core::RootState& state,
    const M4TickScratch& scratch
) noexcept {
    if (!all_finite(scratch.balances_)) {
        return Status(
            ErrorCode::invariant_violation,
            "M4 account balance is nonfinite"
        );
    }
    for (const auto& record : state.postings.records()) {
        const auto index = static_cast<std::size_t>(record.id.value());
        if (index >= scratch.balances_.size()) {
            return Status(
                ErrorCode::invariant_violation,
                "M4 account projection is incomplete"
            );
        }
        if (!record.allow_negative && scratch.balances_[index] < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M4 account balance is negative"
            );
        }
    }
    const double drift =
        sum_balances(scratch) - state.genesis_money.value();
    const double conservation_tolerance = std::max(
        state.accounting_tolerance,
        1.0e-10 * std::max(1.0, std::abs(state.genesis_money.value()))
    );
    if (std::abs(drift) > conservation_tolerance) {
        return Status(
            ErrorCode::invariant_violation,
            "M4 money conservation failed"
        );
    }
    for (const auto& household : scratch.household_work_) {
        const std::array values{
            household.income_expected,
            household.income_realized,
            household.consumption_budget,
            household.spent,
            household.labor_sold,
        };
        if (!all_finite(values) || household.income_expected < 0.0
            || household.income_realized < -kTolerance
            || household.consumption_budget < 0.0
            || household.spent < 0.0
            || household.labor_sold < -kTolerance
            || household.labor_sold > 1.0 + kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M4 household state is invalid"
            );
        }
    }
    for (const auto& firm : scratch.firm_work_) {
        const std::array values{
            firm.target_inventory,
            firm.production_target,
            firm.labor_demand_notional,
            firm.labor_demand_effective,
            firm.hired,
            firm.produced,
            firm.sales,
            firm.revenue,
            firm.wage_bill,
            firm.profit,
            firm.profit_tax,
            firm.dividends,
            firm.retained_earnings,
            firm.investment_target,
            firm.investment,
            firm.rationed_demand,
            firm.closing_inventory,
            firm.closing_capital,
            firm.posted_price,
            firm.posted_wage,
            firm.markup,
            firm.demand_expected,
        };
        if (!all_finite(values) || firm.closing_inventory < -kTolerance
            || firm.closing_capital < -kTolerance
            || firm.posted_price <= 0.0 || firm.posted_wage <= 0.0
            || firm.hired < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M4 firm state is invalid"
            );
        }
    }
    return Status::success();
}

void commit_working_state(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    const M4Metrics& metrics,
    PhiloxCounter rng_counter,
    double technology_index,
    double public_capital
) noexcept {
    for (auto& record : state.postings.records()) {
        record.balance = Money(
            scratch.balances_[static_cast<std::size_t>(record.id.value())]
        );
    }
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        auto* household = state.households.get(scratch.household_ids_[index]);
        const auto& work = scratch.household_work_[index];
        household->income_expected = work.income_expected;
        household->income_realized = work.income_realized;
        household->consumption_budget = work.consumption_budget;
        household->spent = work.spent;
        household->labor_sold = work.labor_sold;
    }
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        auto* firm = state.firms.get(scratch.firm_ids_[index]);
        const auto& work = scratch.firm_work_[index];
        firm->goods_inventory = Goods(std::max(0.0, work.closing_inventory));
        firm->physical_capital =
            Capital(std::max(0.0, work.closing_capital));
        firm->posted_price = Price(work.posted_price);
        firm->posted_wage = Money(work.posted_wage);
        firm->markup = work.markup;
        firm->demand_expected = work.demand_expected;
        firm->target_inventory_previous = work.target_inventory;
        firm->labor_demand_previous = work.labor_demand_effective;
        firm->hired_previous = work.hired;
        firm->sales_previous = work.sales;
        firm->rationed_previous = work.rationed_demand;
    }
    runtime.rng_counter = rng_counter;
    runtime.technology_index = technology_index;
    runtime.public_capital = public_capital;
    runtime.previous_nominal_output = metrics.nominal_output;
    runtime.last_metrics = metrics;
    runtime.last_phase_trace = scratch.phase_trace_;
    tick = Tick(tick.value() + 1);
}

[[nodiscard]] Status prepare_working_state(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch
) {
    if (scratch.household_ids_.size() != state.households.alive_count()
        || scratch.firm_ids_.size() != state.firms.alive_count()
        || scratch.balances_.size() != state.postings.size() + 1) {
        scratch.reserve(state);
    }
    std::fill(scratch.balances_.begin(), scratch.balances_.end(), 0.0);
    for (const auto& account : state.postings.records()) {
        scratch.balances_[static_cast<std::size_t>(account.id.value())] =
            account.balance.value();
    }
    scratch.transfer_count_ = 0;
    scratch.trade_count_ = 0;
    scratch.phase_trace_.clear();
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto* household =
            state.households.get(scratch.household_ids_[index]);
        auto expectation = algorithms::adaptive_expectation(
            household->income_expected,
            household->income_realized,
            household->income_adjustment
        );
        if (!expectation.ok()) {
            return expectation.status();
        }
        auto consumption = algorithms::consumption_plan(
            {
                household->income_propensity,
                household->wealth_propensity,
                *expectation.get_if(),
                scratch.balances_[
                    static_cast<std::size_t>(
                        household->primary_account.value()
                    )
                ],
                0.0,
                1.0,
                std::max(1.0, runtime.rules.initial_household_money),
            }
        );
        if (!consumption.ok()) {
            return consumption.status();
        }
        scratch.household_work_[index] = {
            *expectation.get_if(),
            0.0,
            *consumption.get_if(),
            0.0,
            0.0,
        };
    }
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        auto& work = scratch.firm_work_[index];
        work = {};
        work.closing_inventory = firm->goods_inventory.value();
        work.closing_capital = firm->physical_capital.value();
        work.posted_price = firm->posted_price.value();
        work.posted_wage = firm->posted_wage.value();
        work.markup = firm->markup;
        auto expectation = algorithms::demand_expectation(
            firm->demand_expected,
            firm->sales_previous,
            firm->rationed_previous,
            firm->demand_adjustment
        );
        if (!expectation.ok()) {
            return expectation.status();
        }
        work.demand_expected = *expectation.get_if();
    }
    return Status::success();
}

[[nodiscard]] Status plan_firms(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    PhiloxRng& rng,
    double production_factor
) {
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        auto& work = scratch.firm_work_[index];
        auto production_plan = algorithms::production_plan(
            {
                work.demand_expected,
                firm->inventory_ratio,
                firm->goods_inventory.value(),
                runtime.rules.inventory_gap_close,
            }
        );
        if (!production_plan.ok()) {
            return production_plan.status();
        }
        work.target_inventory =
            production_plan.get_if()->target_inventory;
        work.production_target =
            production_plan.get_if()->production_target;
        auto labor = algorithms::labor_demand(
            {
                technology_for(firm->technology),
                work.production_target,
                firm->productivity,
                firm->total_factor_productivity,
                firm->physical_capital.value(),
                firm->capital_share,
                production_factor,
            }
        );
        if (!labor.ok()) {
            return labor.status();
        }
        work.labor_demand_notional = *labor.get_if();
        const double wage_draw =
            runtime.stochastic ? rng.uniform_closed_open() : 1.0;
        auto wage = algorithms::wage_plan(
            {
                firm->posted_wage.value(),
                firm->hired_previous,
                firm->labor_demand_previous,
                firm->shortage_adjustment,
                runtime.rules.wage_calvo_probability,
                wage_draw,
                0.0,
                runtime.rules.wage_downward_drift,
                0.0,
                0.0,
            }
        );
        if (!wage.ok()) {
            return wage.status();
        }
        work.posted_wage = wage.get_if()->posted;
        auto cost = algorithms::unit_cost(
            {
                technology_for(firm->technology),
                work.posted_wage,
                firm->productivity,
                firm->total_factor_productivity,
                firm->physical_capital.value(),
                firm->capital_share,
                work.production_target,
                work.labor_demand_notional,
                0.0,
                0.0,
                0.0,
                0.0,
                true,
            }
        );
        if (!cost.ok()) {
            return cost.status();
        }
        const double price_draw =
            runtime.stochastic ? rng.uniform_closed_open() : 1.0;
        auto price = algorithms::price_plan(
            {
                firm->posted_price.value(),
                firm->markup,
                firm->markup_minimum,
                firm->markup_maximum,
                firm->markup_adjustment,
                firm->target_inventory_previous,
                firm->goods_inventory.value(),
                *cost.get_if(),
                runtime.rules.price_calvo_probability,
                price_draw,
            }
        );
        if (!price.ok()) {
            return price.status();
        }
        work.posted_price = price.get_if()->posted;
        work.markup = price.get_if()->markup;
        const double balance = scratch.balances_[
            static_cast<std::size_t>(firm->primary_account.value())
        ];
        work.labor_demand_effective = std::max(
            0.0,
            std::min(
                work.labor_demand_notional,
                balance / work.posted_wage
            )
        );
        auto investment = algorithms::investment_plan(
            {
                runtime.vertical == M4Vertical::capital_fiscal
                    && firm->sector == core::FirmSector::consumption,
                firm->capital_output_ratio,
                work.demand_expected,
                firm->investment_adjustment,
                firm->physical_capital.value(),
                firm->capital_depreciation,
                1.0,
                0.0,
                0.5,
                2.0,
                std::nullopt,
            }
        );
        if (!investment.ok()) {
            return investment.status();
        }
        work.investment_target = *investment.get_if();
    }
    return Status::success();
}

[[nodiscard]] Status run_labor(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    PhiloxRng& rng
) {
    scratch.firm_order_.resize(scratch.firm_ids_.size());
    std::iota(
        scratch.household_order_.begin(),
        scratch.household_order_.end(),
        std::size_t{0}
    );
    std::iota(
        scratch.firm_order_.begin(),
        scratch.firm_order_.end(),
        std::size_t{0}
    );
    if (runtime.stochastic) {
        auto status = rng.shuffle(std::span(scratch.household_order_));
        if (!status.ok()) {
            return status;
        }
        status = rng.shuffle(std::span(scratch.firm_order_));
        if (!status.ok()) {
            return status;
        }
    }
    std::size_t worker_position = 0;
    double worker_remaining = 1.0;
    for (const auto firm_index : scratch.firm_order_) {
        const auto* firm = state.firms.get(scratch.firm_ids_[firm_index]);
        auto& firm_work = scratch.firm_work_[firm_index];
        double need = firm_work.labor_demand_effective;
        while (need > algorithms::kEconomicEpsilon
            && worker_position < scratch.household_order_.size()) {
            const auto household_index =
                scratch.household_order_[worker_position];
            const auto* household =
                state.households.get(scratch.household_ids_[household_index]);
            const auto firm_account =
                static_cast<std::size_t>(firm->primary_account.value());
            const double affordable =
                scratch.balances_[firm_account] / firm_work.posted_wage;
            if (affordable <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double hired =
                std::min({need, worker_remaining, affordable});
            if (hired <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double pay = hired * firm_work.posted_wage;
            const auto status = transfer(
                state,
                scratch,
                firm->primary_account,
                household->primary_account,
                pay
            );
            if (!status.ok()) {
                return status;
            }
            firm_work.hired += hired;
            firm_work.wage_bill += pay;
            auto& household_work = scratch.household_work_[household_index];
            household_work.income_realized += pay;
            household_work.labor_sold += hired;
            worker_remaining -= hired;
            need -= hired;
            if (worker_remaining <= algorithms::kEconomicEpsilon) {
                ++worker_position;
                worker_remaining = 1.0;
            }
        }
    }
    return Status::success();
}

[[nodiscard]] Status run_production(
    const core::RootState& state,
    M4TickScratch& scratch,
    double production_factor
) {
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        auto& work = scratch.firm_work_[index];
        auto produced = algorithms::production(
            {
                technology_for(firm->technology),
                work.hired,
                firm->productivity,
                firm->total_factor_productivity,
                firm->physical_capital.value(),
                firm->capital_share,
                production_factor,
            }
        );
        if (!produced.ok()) {
            return produced.status();
        }
        work.produced = *produced.get_if();
        work.closing_inventory =
            firm->goods_inventory.value() + work.produced;
    }
    return Status::success();
}

[[nodiscard]] Status apply_sampled_market(
    const core::RootState& state,
    M4TickScratch& scratch,
    PhiloxRng& rng,
    bool capital_market
) {
    scratch.market_buyer_order_.resize(scratch.orders_.size());
    std::iota(
        scratch.market_buyer_order_.begin(),
        scratch.market_buyer_order_.end(),
        std::size_t{0}
    );
    auto status = rng.shuffle(
        std::span<std::size_t>(scratch.market_buyer_order_)
    );
    if (!status.ok()) {
        return status;
    }
    scratch.market_active_offers_.clear();
    scratch.market_offer_remaining_.resize(scratch.offers_.size());
    for (std::size_t index = 0; index < scratch.offers_.size(); ++index) {
        const double stock = scratch.offers_[index].stock.value();
        scratch.market_offer_remaining_[index] = stock;
        if (stock > algorithms::kEconomicEpsilon) {
            scratch.market_active_offers_.push_back(index);
        }
    }
    for (const auto buyer_index : scratch.market_buyer_order_) {
        const auto& order = scratch.orders_[buyer_index];
        double remaining_budget = order.budget.value();
        double remaining_demand = order.demand.value();
        double allocated = 0.0;
        while (remaining_budget > algorithms::kEconomicEpsilon
            && remaining_demand > algorithms::kEconomicEpsilon
            && !scratch.market_active_offers_.empty()) {
            auto selected_result = rng.uniform_index(
                scratch.market_active_offers_.size()
            );
            if (!selected_result.ok()) {
                return selected_result.status();
            }
            auto selected_position = *selected_result.get_if();
            auto offer_index =
                scratch.market_active_offers_[selected_position];
            if (scratch.offers_[offer_index].seller == order.buyer) {
                selected_position =
                    scratch.market_active_offers_.size();
                for (std::size_t position = 0;
                     position < scratch.market_active_offers_.size();
                     ++position) {
                    const auto candidate =
                        scratch.market_active_offers_[position];
                    if (scratch.offers_[candidate].seller != order.buyer) {
                        selected_position = position;
                        offer_index = candidate;
                        break;
                    }
                }
                if (selected_position
                    == scratch.market_active_offers_.size()) {
                    break;
                }
            }
            const auto& offer = scratch.offers_[offer_index];
            const double quantity = std::min(
                {
                    remaining_demand,
                    remaining_budget / offer.price.value(),
                    scratch.market_offer_remaining_[offer_index],
                }
            );
            if (quantity <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double value = quantity * offer.price.value();
            status = transfer(
                state,
                scratch,
                order.buyer,
                offer.seller,
                value
            );
            if (!status.ok()) {
                return status;
            }
            remaining_budget -= value;
            remaining_demand -= quantity;
            allocated += quantity;
            scratch.market_offer_remaining_[offer_index] -= quantity;
            const auto firm_index =
                static_cast<std::size_t>(offer.offer_id - 1);
            auto& firm = scratch.firm_work_[firm_index];
            firm.sales += quantity;
            firm.revenue += value;
            ++scratch.trade_count_;
            if (scratch.market_offer_remaining_[offer_index]
                <= algorithms::kEconomicEpsilon) {
                scratch.market_active_offers_[selected_position] =
                    scratch.market_active_offers_.back();
                scratch.market_active_offers_.pop_back();
            }
        }
        if (capital_market) {
            const auto firm_index =
                static_cast<std::size_t>(order.order_id - 1);
            if (firm_index >= scratch.firm_work_.size()
                || scratch.firm_ids_[firm_index].value()
                    != order.order_id) {
                return Status(
                    ErrorCode::internal_error,
                    "M4 capital buyer projection is stale"
                );
            }
            scratch.firm_work_[firm_index].investment = allocated;
        } else {
            const auto household_index =
                static_cast<std::size_t>(order.order_id - 1);
            if (household_index >= scratch.household_work_.size()
                || scratch.household_ids_[household_index].value()
                    != order.order_id) {
                return Status(
                    ErrorCode::internal_error,
                    "M4 household buyer projection is stale"
                );
            }
            scratch.household_work_[household_index].spent =
                order.budget.value() - remaining_budget;
        }
    }
    for (std::size_t index = 0; index < scratch.offers_.size(); ++index) {
        const auto firm_index = static_cast<std::size_t>(
            scratch.offers_[index].offer_id - 1
        );
        scratch.firm_work_[firm_index].closing_inventory =
            scratch.market_offer_remaining_[index];
    }
    return Status::success();
}

[[nodiscard]] Status apply_market(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    PhiloxRng& rng,
    bool capital_market
) {
    scratch.orders_.clear();
    scratch.offers_.clear();
    if (capital_market) {
        for (const auto index : scratch.consumption_firm_indices_) {
            const auto* firm = state.firms.get(scratch.firm_ids_[index]);
            const auto& work = scratch.firm_work_[index];
            const double budget = scratch.balances_[
                static_cast<std::size_t>(firm->primary_account.value())
            ];
            if (work.investment_target > algorithms::kEconomicEpsilon
                && budget > algorithms::kEconomicEpsilon) {
                scratch.orders_.push_back(
                    {
                        scratch.firm_ids_[index].value(),
                        firm->primary_account,
                        Goods(work.investment_target),
                        Money(budget),
                    }
                );
            }
        }
        for (const auto index : scratch.capital_firm_indices_) {
            const auto* firm = state.firms.get(scratch.firm_ids_[index]);
            const auto& work = scratch.firm_work_[index];
            scratch.offers_.push_back(
                {
                    scratch.firm_ids_[index].value(),
                    firm->primary_account,
                    Goods(std::max(0.0, work.closing_inventory)),
                    Price(work.posted_price),
                    1.0,
                }
            );
        }
    } else {
        for (std::size_t index = 0;
             index < scratch.household_ids_.size();
             ++index) {
            const auto* household =
                state.households.get(scratch.household_ids_[index]);
            const auto& work = scratch.household_work_[index];
            const double cash = scratch.balances_[
                static_cast<std::size_t>(
                    household->primary_account.value()
                )
            ];
            const double budget = std::min(work.consumption_budget, cash);
            if (budget > algorithms::kEconomicEpsilon) {
                scratch.orders_.push_back(
                    {
                        scratch.household_ids_[index].value(),
                        household->primary_account,
                        Goods(std::numeric_limits<double>::infinity()),
                        Money(
                            budget
                            / (
                                1.0
                                + (
                                    runtime.vertical
                                        == M4Vertical::capital_fiscal
                                    ? runtime.rules.consumption_tax_rate
                                    : 0.0
                                )
                            )
                        ),
                    }
                );
            }
        }
        for (const auto index : scratch.consumption_firm_indices_) {
            const auto* firm = state.firms.get(scratch.firm_ids_[index]);
            const auto& work = scratch.firm_work_[index];
            scratch.offers_.push_back(
                {
                    scratch.firm_ids_[index].value(),
                    firm->primary_account,
                    Goods(std::max(0.0, work.closing_inventory)),
                    Price(work.posted_price),
                    1.0,
                }
            );
        }
    }
    if (runtime.market_protocol == algorithms::MatchingProtocol::sampled
        && runtime.rules.market_sample_size == 1) {
        return apply_sampled_market(
            state,
            scratch,
            rng,
            capital_market
        );
    }
    algorithms::MarketConfig config;
    config.protocol = runtime.market_protocol;
    config.sample_size = runtime.rules.market_sample_size;
    config.rng_key = runtime.rng_key;
    config.rng_counter = rng.counter();
    auto clearing = algorithms::clear_market(
        scratch.orders_,
        scratch.offers_,
        config
    );
    if (!clearing.ok()) {
        return clearing.status();
    }
    scratch.clearing_ = std::move(*clearing.get_if());
    rng = PhiloxRng(runtime.rng_key, scratch.clearing_.next_counter);
    for (const auto& trade : scratch.clearing_.trades) {
        const auto status = transfer(
            state,
            scratch,
            trade.buyer,
            trade.seller,
            trade.value.value()
        );
        if (!status.ok()) {
            return status;
        }
        const auto firm_index =
            static_cast<std::size_t>(trade.offer_id - 1);
        if (firm_index >= scratch.firm_work_.size()
            || scratch.firm_ids_[firm_index].value() != trade.offer_id) {
            return Status(
                ErrorCode::internal_error,
                "M4 market offer projection is stale"
            );
        }
        auto& firm = scratch.firm_work_[firm_index];
        firm.sales += trade.quantity.value();
        firm.revenue += trade.value.value();
        ++scratch.trade_count_;
    }
    for (const auto& stock : scratch.clearing_.stock_commands) {
        const auto firm_index =
            static_cast<std::size_t>(stock.offer_id - 1);
        scratch.firm_work_[firm_index].closing_inventory =
            stock.closing.value();
    }
    for (const auto& allocation : scratch.clearing_.allocations) {
        if (capital_market) {
            const auto firm_id = allocation.order_id;
            const auto firm_index = static_cast<std::size_t>(firm_id - 1);
            if (firm_index >= scratch.firm_work_.size()
                || scratch.firm_ids_[firm_index].value() != firm_id) {
                return Status(
                    ErrorCode::internal_error,
                    "M4 capital buyer projection is stale"
                );
            }
            scratch.firm_work_[firm_index].investment =
                allocation.allocated.value();
        } else {
            const auto household_id = allocation.order_id;
            const auto household_index =
                static_cast<std::size_t>(household_id - 1);
            if (household_index >= scratch.household_work_.size()
                || scratch.household_ids_[household_index].value()
                    != household_id) {
                return Status(
                    ErrorCode::internal_error,
                    "M4 household buyer projection is stale"
                );
            }
            scratch.household_work_[household_index].spent =
                allocation.spent.value();
        }
    }
    return Status::success();
}

[[nodiscard]] Status run_consumption_tax(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    double& tax_total
) noexcept {
    if (runtime.vertical != M4Vertical::capital_fiscal
        || runtime.rules.consumption_tax_rate <= 0.0) {
        return Status::success();
    }
    const auto treasury = state.institutions.treasury_account;
    for (std::size_t index = 0;
         index < scratch.household_ids_.size();
         ++index) {
        const auto* household =
            state.households.get(scratch.household_ids_[index]);
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        const double due =
            scratch.household_work_[index].spent
            * runtime.rules.consumption_tax_rate;
        const double paid = std::min(due, scratch.balances_[account]);
        const auto status = transfer(
            state,
            scratch,
            household->primary_account,
            treasury,
            paid
        );
        if (!status.ok()) {
            return status;
        }
        tax_total += paid;
    }
    return Status::success();
}

[[nodiscard]] Status run_government_procurement(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    double& government_spending
) {
    if (runtime.vertical != M4Vertical::capital_fiscal) {
        return Status::success();
    }
    scratch.firm_order_.assign(
        scratch.consumption_firm_indices_.begin(),
        scratch.consumption_firm_indices_.end()
    );
    std::sort(
        scratch.firm_order_.begin(),
        scratch.firm_order_.end(),
        [&scratch](std::size_t left, std::size_t right) {
            const auto& lhs = scratch.firm_work_[left];
            const auto& rhs = scratch.firm_work_[right];
            if (lhs.posted_price != rhs.posted_price) {
                return lhs.posted_price < rhs.posted_price;
            }
            return scratch.firm_ids_[left] < scratch.firm_ids_[right];
        }
    );
    double units =
        runtime.rules.government_consumption_share
        * static_cast<double>(scratch.household_ids_.size())
        * runtime.rules.linear_productivity;
    const auto treasury = state.institutions.treasury_account;
    for (const auto index : scratch.firm_order_) {
        if (units <= algorithms::kEconomicEpsilon) {
            break;
        }
        auto& work = scratch.firm_work_[index];
        const double quantity = std::min(units, work.closing_inventory);
        if (quantity <= algorithms::kEconomicEpsilon) {
            continue;
        }
        const double value = quantity * work.posted_price;
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        const auto status = transfer(
            state,
            scratch,
            treasury,
            firm->primary_account,
            value
        );
        if (!status.ok()) {
            return status;
        }
        work.closing_inventory -= quantity;
        work.sales += quantity;
        work.revenue += value;
        government_spending += value;
        units -= quantity;
    }
    return Status::success();
}

[[nodiscard]] Status run_public_investment(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    double& government_spending,
    double& public_capital_addition
) {
    if (runtime.vertical != M4Vertical::capital_fiscal
        || runtime.rules.government_investment_share <= 0.0) {
        return Status::success();
    }
    scratch.firm_order_.assign(
        scratch.capital_firm_indices_.begin(),
        scratch.capital_firm_indices_.end()
    );
    std::sort(
        scratch.firm_order_.begin(),
        scratch.firm_order_.end(),
        [&scratch](std::size_t left, std::size_t right) {
            const auto& lhs = scratch.firm_work_[left];
            const auto& rhs = scratch.firm_work_[right];
            if (lhs.posted_price != rhs.posted_price) {
                return lhs.posted_price < rhs.posted_price;
            }
            return scratch.firm_ids_[left] < scratch.firm_ids_[right];
        }
    );
    double budget =
        runtime.rules.government_investment_share
        * std::max(
            runtime.previous_nominal_output,
            runtime.rules.initial_price
                * static_cast<double>(scratch.household_ids_.size())
        );
    const auto treasury = state.institutions.treasury_account;
    for (const auto index : scratch.firm_order_) {
        if (budget <= algorithms::kEconomicEpsilon) {
            break;
        }
        auto& work = scratch.firm_work_[index];
        const double quantity = std::min(
            work.closing_inventory,
            budget / work.posted_price
        );
        if (quantity <= algorithms::kEconomicEpsilon) {
            continue;
        }
        const double value = quantity * work.posted_price;
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        const auto status = transfer(
            state,
            scratch,
            treasury,
            firm->primary_account,
            value
        );
        if (!status.ok()) {
            return status;
        }
        work.closing_inventory -= quantity;
        work.sales += quantity;
        work.revenue += value;
        budget -= value;
        government_spending += value;
        public_capital_addition += quantity;
    }
    return Status::success();
}

[[nodiscard]] Status run_settlement(
    const core::RootState& state,
    const M4Runtime& runtime,
    M4TickScratch& scratch,
    double& tax_total,
    double& benefit_spending
) {
    const bool fiscal = runtime.vertical == M4Vertical::capital_fiscal;
    const auto treasury = state.institutions.treasury_account;
    const auto clearing = state.institutions.clearing_account;
    double dividend_total = 0.0;
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        auto& work = scratch.firm_work_[index];
        work.profit = work.revenue - work.wage_bill;
        if (fiscal && work.profit > algorithms::kEconomicEpsilon) {
            const auto account =
                static_cast<std::size_t>(firm->primary_account.value());
            const double due =
                runtime.rules.profit_tax_rate * work.profit;
            work.profit_tax = std::min(due, scratch.balances_[account]);
            const auto status = transfer(
                state,
                scratch,
                firm->primary_account,
                treasury,
                work.profit_tax
            );
            if (!status.ok()) {
                return status;
            }
            tax_total += work.profit_tax;
        }
        const double distributable =
            std::max(0.0, work.profit - work.profit_tax);
        const auto account =
            static_cast<std::size_t>(firm->primary_account.value());
        work.dividends = std::min(
            firm->dividend_payout * distributable,
            scratch.balances_[account]
        );
        if (work.dividends > algorithms::kEconomicEpsilon) {
            const auto status = transfer(
                state,
                scratch,
                firm->primary_account,
                clearing,
                work.dividends
            );
            if (!status.ok()) {
                return status;
            }
            dividend_total += work.dividends;
        }
        work.retained_earnings =
            work.profit - work.profit_tax - work.dividends;
    }
    if (dividend_total > algorithms::kEconomicEpsilon
        && !scratch.household_ids_.empty()) {
        const double share =
            dividend_total
            / static_cast<double>(scratch.household_ids_.size());
        for (std::size_t index = 0;
             index + 1 < scratch.household_ids_.size();
             ++index) {
            const auto* household =
                state.households.get(scratch.household_ids_[index]);
            const auto status = transfer(
                state,
                scratch,
                clearing,
                household->primary_account,
                share
            );
            if (!status.ok()) {
                return status;
            }
            scratch.household_work_[index].income_realized += share;
        }
        const auto last_index = scratch.household_ids_.size() - 1;
        const auto* household =
            state.households.get(scratch.household_ids_[last_index]);
        const auto clearing_index =
            static_cast<std::size_t>(clearing.value());
        const double remainder = scratch.balances_[clearing_index];
        const auto status = transfer(
            state,
            scratch,
            clearing,
            household->primary_account,
            remainder
        );
        if (!status.ok()) {
            return status;
        }
        scratch.household_work_[last_index].income_realized += remainder;
    }
    if (!fiscal) {
        return Status::success();
    }
    for (std::size_t index = 0;
         index < scratch.household_ids_.size();
         ++index) {
        const auto* household =
            state.households.get(scratch.household_ids_[index]);
        auto& work = scratch.household_work_[index];
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        const double due =
            runtime.rules.income_tax_rate
            * std::max(0.0, work.income_realized);
        const double paid = std::min(due, scratch.balances_[account]);
        auto status = transfer(
            state,
            scratch,
            household->primary_account,
            treasury,
            paid
        );
        if (!status.ok()) {
            return status;
        }
        work.income_realized -= paid;
        tax_total += paid;
    }
    double mean_wage = 0.0;
    for (const auto& firm : scratch.firm_work_) {
        mean_wage += firm.posted_wage;
    }
    mean_wage /= static_cast<double>(
        std::max<std::size_t>(1, scratch.firm_work_.size())
    );
    for (std::size_t index = 0;
         index < scratch.household_ids_.size();
         ++index) {
        const auto* household =
            state.households.get(scratch.household_ids_[index]);
        auto& work = scratch.household_work_[index];
        const double benefit =
            runtime.rules.unemployment_benefit_replacement
            * mean_wage * std::max(0.0, 1.0 - work.labor_sold);
        auto status = transfer(
            state,
            scratch,
            treasury,
            household->primary_account,
            benefit
        );
        if (!status.ok()) {
            return status;
        }
        work.income_realized += benefit;
        benefit_spending += benefit;
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        const double wealth_tax = std::min(
            runtime.rules.wealth_tax_rate
                * std::max(0.0, scratch.balances_[account]),
            scratch.balances_[account]
        );
        status = transfer(
            state,
            scratch,
            household->primary_account,
            treasury,
            wealth_tax
        );
        if (!status.ok()) {
            return status;
        }
        tax_total += wealth_tax;
    }
    return Status::success();
}

void commit_capital(
    const core::RootState& state,
    M4TickScratch& scratch
) noexcept {
    for (const auto index : scratch.consumption_firm_indices_) {
        const auto* firm = state.firms.get(scratch.firm_ids_[index]);
        auto& work = scratch.firm_work_[index];
        work.closing_capital =
            (1.0 - firm->capital_depreciation)
                * firm->physical_capital.value()
            + work.investment;
    }
}

[[nodiscard]] M4Metrics measure(
    const core::RootState& state,
    const M4Runtime& runtime,
    const M4TickScratch& scratch,
    Tick tick,
    double tax_total,
    double government_spending,
    double benefit_spending,
    double public_capital
) noexcept {
    M4Metrics metrics;
    metrics.tick = tick;
    double sold_quantity = 0.0;
    double price_value = 0.0;
    for (std::size_t index = 0;
         index < scratch.firm_work_.size();
         ++index) {
        const auto& firm = scratch.firm_work_[index];
        metrics.real_output += firm.produced;
        metrics.nominal_output += firm.revenue;
        const auto* persistent =
            state.firms.get(scratch.firm_ids_[index]);
        if (persistent->sector == core::FirmSector::consumption) {
            sold_quantity += firm.sales;
            price_value += firm.sales * firm.posted_price;
        }
        metrics.wages_paid += firm.wage_bill;
        metrics.firm_profit += firm.profit;
        metrics.aggregate_capital += firm.closing_capital;
    }
    for (const auto& household : scratch.household_work_) {
        metrics.household_consumption += household.spent;
        metrics.unemployment_rate += 1.0 - household.labor_sold;
    }
    const double household_count =
        static_cast<double>(scratch.household_work_.size());
    metrics.unemployment_rate =
        household_count > 0.0
        ? metrics.unemployment_rate / household_count
        : 0.0;
    if (sold_quantity > algorithms::kEconomicEpsilon) {
        metrics.price_index = price_value / sold_quantity;
    } else if (!scratch.firm_work_.empty()) {
        for (const auto& firm : scratch.firm_work_) {
            metrics.price_index += firm.posted_price;
        }
        metrics.price_index /=
            static_cast<double>(scratch.firm_work_.size());
    }
    metrics.total_money = sum_balances(scratch);
    metrics.conservation_drift =
        metrics.total_money - state.genesis_money.value();
    metrics.tax_total = tax_total;
    metrics.government_spending =
        government_spending + benefit_spending;
    metrics.government_deficit =
        metrics.government_spending - tax_total;
    metrics.public_capital = public_capital;
    static_cast<void>(runtime);
    return metrics;
}

[[nodiscard]] Result<M4AdvanceResult> advance_one(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    const M4AdvanceOptions& options
) {
    auto status = check_fault(options, M4Phase::open_books);
    if (!status.ok()) {
        return status;
    }
    status = prepare_working_state(state, runtime, scratch);
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::open_books);

    status = check_fault(options, M4Phase::open_real_economy);
    if (!status.ok()) {
        return status;
    }
    const double daily_growth = std::pow(
        1.0 + runtime.rules.annual_tfp_growth,
        1.0 / kDaysPerYear
    );
    const double technology_index =
        runtime.technology_index * daily_growth;
    const double production_factor = technology_index;
    capture_phase(state, scratch, options, M4Phase::open_real_economy);

    PhiloxRng rng(runtime.rng_key, runtime.rng_counter);
    status = check_fault(options, M4Phase::plan_and_finance);
    if (!status.ok()) {
        return status;
    }
    status = plan_firms(
        state,
        runtime,
        scratch,
        rng,
        production_factor
    );
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::plan_and_finance);

    status = check_fault(options, M4Phase::labor);
    if (!status.ok()) {
        return status;
    }
    status = run_labor(state, runtime, scratch, rng);
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::labor);

    status = check_fault(options, M4Phase::production);
    if (!status.ok()) {
        return status;
    }
    status = run_production(state, scratch, production_factor);
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::production);

    status = check_fault(options, M4Phase::goods_market);
    if (!status.ok()) {
        return status;
    }
    status = apply_market(state, runtime, scratch, rng, false);
    if (!status.ok()) {
        return status;
    }
    double tax_total = 0.0;
    double government_spending = 0.0;
    double public_capital_addition = 0.0;
    status = run_consumption_tax(state, runtime, scratch, tax_total);
    if (!status.ok()) {
        return status;
    }
    status = run_government_procurement(
        state,
        runtime,
        scratch,
        government_spending
    );
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::goods_market);

    if (runtime.vertical == M4Vertical::capital_fiscal) {
        status = check_fault(options, M4Phase::capital_market);
        if (!status.ok()) {
            return status;
        }
        status = apply_market(state, runtime, scratch, rng, true);
        if (!status.ok()) {
            return status;
        }
        status = run_public_investment(
            state,
            runtime,
            scratch,
            government_spending,
            public_capital_addition
        );
        if (!status.ok()) {
            return status;
        }
        capture_phase(state, scratch, options, M4Phase::capital_market);
    }

    status = check_fault(options, M4Phase::settle_domestic);
    if (!status.ok()) {
        return status;
    }
    double benefit_spending = 0.0;
    status = run_settlement(
        state,
        runtime,
        scratch,
        tax_total,
        benefit_spending
    );
    if (!status.ok()) {
        return status;
    }
    commit_capital(state, scratch);
    const double public_capital =
        runtime.public_capital + public_capital_addition;
    capture_phase(state, scratch, options, M4Phase::settle_domestic);

    status = check_fault(options, M4Phase::validate_and_measure);
    if (!status.ok()) {
        return status;
    }
    status = validate_working_state(state, scratch);
    if (!status.ok()) {
        return status;
    }
    const auto metrics = measure(
        state,
        runtime,
        scratch,
        tick,
        tax_total,
        government_spending,
        benefit_spending,
        public_capital
    );
    capture_phase(state, scratch, options, M4Phase::validate_and_measure);

    status = check_fault(options, M4Phase::stage_local_commit);
    if (!status.ok()) {
        return status;
    }
    commit_working_state(
        state,
        runtime,
        scratch,
        tick,
        metrics,
        rng.counter(),
        technology_index,
        public_capital
    );
    if (options.capture_phase_trace) {
        runtime.last_phase_trace.push_back(
            {
                M4Phase::stage_local_commit,
                metrics.total_money,
                0.0,
                metrics.aggregate_capital,
                scratch.transfer_count_,
                scratch.trade_count_,
            }
        );
    }
    return M4AdvanceResult{
        metrics.tick,
        tick,
        1,
        metrics,
        scratch.capacity_signature(),
        scratch.transfer_count_,
        scratch.trade_count_,
    };
}

}  // namespace

void M4TickScratch::reserve(const core::RootState& state) {
    const auto household_count = state.households.alive_count();
    const auto firm_count = state.firms.alive_count();
    household_ids_.clear();
    household_ids_.reserve(household_count);
    state.households.for_each_alive(
        [this](HouseholdId id, const core::HouseholdComponent&) {
            household_ids_.push_back(id);
        }
    );
    firm_ids_.clear();
    consumption_firm_indices_.clear();
    capital_firm_indices_.clear();
    firm_ids_.reserve(firm_count);
    consumption_firm_indices_.reserve(firm_count);
    capital_firm_indices_.reserve(firm_count);
    state.firms.for_each_alive(
        [this](FirmId id, const core::FirmComponent& firm) {
            const auto index = firm_ids_.size();
            firm_ids_.push_back(id);
            if (firm.sector == core::FirmSector::consumption) {
                consumption_firm_indices_.push_back(index);
            } else {
                capital_firm_indices_.push_back(index);
            }
        }
    );
    household_order_.resize(household_count);
    firm_order_.resize(firm_count);
    balances_.resize(state.postings.size() + 1);
    household_work_.resize(household_count);
    firm_work_.resize(firm_count);
    orders_.reserve(std::max(household_count, firm_count));
    offers_.reserve(firm_count);
    market_buyer_order_.reserve(std::max(household_count, firm_count));
    market_active_offers_.reserve(firm_count);
    market_offer_remaining_.reserve(firm_count);
    clearing_.trades.reserve(household_count + firm_count);
    clearing_.allocations.reserve(std::max(household_count, firm_count));
    clearing_.stock_commands.reserve(firm_count);
    phase_trace_.reserve(10);
}

std::uint64_t M4TickScratch::capacity_signature() const noexcept {
    std::uint64_t signature = 1469598103934665603ULL;
    const std::array capacities{
        household_ids_.capacity(),
        firm_ids_.capacity(),
        consumption_firm_indices_.capacity(),
        capital_firm_indices_.capacity(),
        household_order_.capacity(),
        firm_order_.capacity(),
        balances_.capacity(),
        household_work_.capacity(),
        firm_work_.capacity(),
        orders_.capacity(),
        offers_.capacity(),
        market_buyer_order_.capacity(),
        market_active_offers_.capacity(),
        market_offer_remaining_.capacity(),
        clearing_.trades.capacity(),
        clearing_.allocations.capacity(),
        clearing_.stock_commands.capacity(),
        phase_trace_.capacity(),
    };
    for (const auto capacity : capacities) {
        signature ^= static_cast<std::uint64_t>(capacity);
        signature *= 1099511628211ULL;
    }
    return signature;
}

Status validate_spec(const M4SimulationSpec& spec) noexcept {
    if (!spec.economy.valid() || !spec.currency.valid()
        || spec.households == 0 || spec.consumption_firms == 0) {
        return Status(
            ErrorCode::invalid_argument,
            "M4 genesis requires valid IDs, households, and consumption firms"
        );
    }
    if (spec.households > 10'000'000
        || spec.consumption_firms > 10'000'000
        || spec.capital_firms > 10'000'000) {
        return Status(ErrorCode::out_of_range, "M4 entity limit is exceeded");
    }
    if ((spec.requested_capabilities & kUnsupportedCapabilities) != 0) {
        return Status(
            ErrorCode::unsupported,
            "requested capability is scheduled after M4"
        );
    }
    if (spec.vertical == M4Vertical::cash_loop) {
        if (spec.capital_firms != 0 || spec.requested_capabilities != 0) {
            return Status(
                ErrorCode::unsupported,
                "M4 V0 supports only the basic cash-loop capability set"
            );
        }
    } else if (spec.capital_firms == 0
        || spec.requested_capabilities != kV1Capabilities) {
        return Status(
            ErrorCode::unsupported,
            "M4 V1 requires exactly physical-capital and government capabilities"
        );
    }
    const auto& rules = spec.rules;
    const std::array values{
        rules.linear_productivity,
        rules.capital_productivity,
        rules.total_factor_productivity,
        rules.capital_share,
        rules.capital_output_ratio,
        rules.demand_adjustment,
        rules.income_adjustment,
        rules.inventory_ratio,
        rules.inventory_gap_close,
        rules.markup_adjustment,
        rules.markup_minimum,
        rules.markup_maximum,
        rules.wage_shortage_adjustment,
        rules.wage_downward_drift,
        rules.wage_calvo_probability,
        rules.price_calvo_probability,
        rules.income_propensity,
        rules.wealth_propensity,
        rules.dividend_payout,
        rules.investment_adjustment,
        rules.capital_depreciation,
        rules.annual_tfp_growth,
        rules.profit_tax_rate,
        rules.income_tax_rate,
        rules.consumption_tax_rate,
        rules.wealth_tax_rate,
        rules.government_consumption_share,
        rules.government_investment_share,
        rules.unemployment_benefit_replacement,
        rules.initial_household_money,
        rules.initial_firm_money,
        rules.initial_consumption_inventory,
        rules.initial_capital_inventory,
        rules.initial_consumption_capital,
        rules.initial_price,
        rules.initial_capital_price,
        rules.initial_wage,
        rules.initial_markup,
        rules.initial_expected_demand,
    };
    if (!all_finite(values) || rules.linear_productivity <= 0.0
        || rules.capital_productivity <= 0.0
        || rules.total_factor_productivity <= 0.0
        || rules.capital_share < 0.0 || rules.capital_share >= 1.0
        || rules.capital_output_ratio < 0.0
        || rules.markup_minimum > rules.markup_maximum
        || rules.markup_minimum < 0.0
        || rules.annual_tfp_growth <= -1.0
        || rules.demand_adjustment < 0.0
        || rules.demand_adjustment > 1.0
        || rules.income_adjustment < 0.0
        || rules.income_adjustment > 1.0
        || rules.inventory_ratio < 0.0
        || rules.inventory_gap_close < 0.0
        || rules.inventory_gap_close > 1.0
        || rules.markup_adjustment < 0.0
        || rules.wage_shortage_adjustment < 0.0
        || rules.wage_downward_drift < 0.0
        || rules.income_propensity < 0.0
        || rules.wealth_propensity < 0.0
        || rules.dividend_payout < 0.0
        || rules.dividend_payout > 1.0
        || rules.investment_adjustment < 0.0
        || rules.capital_depreciation < 0.0
        || rules.capital_depreciation > 1.0
        || rules.profit_tax_rate < 0.0
        || rules.profit_tax_rate > 1.0
        || rules.income_tax_rate < 0.0
        || rules.income_tax_rate > 1.0
        || rules.consumption_tax_rate < 0.0
        || rules.consumption_tax_rate > 1.0
        || rules.wealth_tax_rate < 0.0
        || rules.wealth_tax_rate > 1.0
        || rules.government_consumption_share < 0.0
        || rules.government_investment_share < 0.0
        || rules.unemployment_benefit_replacement < 0.0
        || rules.unemployment_benefit_replacement > 1.0
        || rules.government_consumption_share > 1.0
        || rules.government_investment_share > 1.0
        || rules.initial_price <= 0.0 || rules.initial_capital_price <= 0.0
        || rules.initial_wage <= 0.0 || rules.initial_household_money < 0.0
        || rules.initial_firm_money < 0.0
        || rules.initial_consumption_inventory < 0.0
        || rules.initial_capital_inventory < 0.0
        || rules.initial_consumption_capital < 0.0
        || rules.initial_markup < rules.markup_minimum
        || rules.initial_markup > rules.markup_maximum
        || rules.initial_expected_demand < 0.0
        || rules.wage_calvo_probability < 0.0
        || rules.wage_calvo_probability > 1.0
        || rules.price_calvo_probability < 0.0
        || rules.price_calvo_probability > 1.0
        || rules.market_sample_size == 0) {
        return Status(ErrorCode::invalid_argument, "M4 rules are invalid");
    }
    return Status::success();
}

Status validate_m4_state(
    const core::RootState& root,
    const M4Runtime& runtime,
    Tick tick
) noexcept {
    const auto* clearing = root.postings.get(
        root.institutions.clearing_account
    );
    if (clearing == nullptr
        || !clearing->open
        || clearing->key.kind != core::AccountKind::clearing
        || clearing->key.owner
            != core::OwnerId::institutional(core::OwnerKind::institution)) {
        return Status(
            ErrorCode::invariant_violation,
            "M4 session identity is invalid"
        );
    }
    bool components_valid = true;
    root.households.for_each_alive(
        [&components_valid](
            HouseholdId,
            const core::HouseholdComponent& household
        ) {
            const std::array values{
                household.income_propensity,
                household.wealth_propensity,
                household.income_adjustment,
                household.income_expected,
                household.income_realized,
                household.consumption_budget,
                household.spent,
                household.labor_sold,
            };
            components_valid =
                components_valid && all_finite(values)
                && household.income_propensity >= 0.0
                && household.wealth_propensity >= 0.0
                && household.income_adjustment >= 0.0
                && household.income_adjustment <= 1.0
                && household.income_expected >= 0.0
                && household.consumption_budget >= 0.0
                && household.spent >= 0.0
                && household.labor_sold >= 0.0
                && household.labor_sold <= 1.0 + kTolerance;
        }
    );
    std::uint64_t consumption_firms = 0;
    std::uint64_t capital_firms = 0;
    root.firms.for_each_alive(
        [&components_valid, &consumption_firms, &capital_firms](
            FirmId,
            const core::FirmComponent& firm
        ) {
            if (firm.sector == core::FirmSector::consumption) {
                ++consumption_firms;
            } else {
                ++capital_firms;
            }
            const std::array values{
                firm.total_factor_productivity,
                firm.capital_share,
                firm.capital_output_ratio,
                firm.investment_adjustment,
                firm.capital_depreciation,
                firm.demand_adjustment,
                firm.inventory_ratio,
                firm.markup_adjustment,
                firm.markup_minimum,
                firm.markup_maximum,
                firm.shortage_adjustment,
                firm.dividend_payout,
                firm.posted_price.value(),
                firm.posted_wage.value(),
                firm.markup,
                firm.demand_expected,
                firm.target_inventory_previous,
                firm.labor_demand_previous,
                firm.hired_previous,
                firm.sales_previous,
                firm.rationed_previous,
            };
            components_valid =
                components_valid && all_finite(values)
                && firm.total_factor_productivity > 0.0
                && firm.capital_share >= 0.0
                && firm.capital_share < 1.0
                && firm.capital_output_ratio >= 0.0
                && firm.investment_adjustment >= 0.0
                && firm.capital_depreciation >= 0.0
                && firm.capital_depreciation <= 1.0
                && firm.posted_price.value() > 0.0
                && firm.posted_wage.value() > 0.0
                && firm.demand_expected >= 0.0
                && firm.hired_previous >= 0.0
                && firm.sales_previous >= 0.0
                && firm.rationed_previous >= 0.0;
        }
    );
    const std::array runtime_values{
        runtime.technology_index,
        runtime.public_capital,
        runtime.previous_nominal_output,
        runtime.last_metrics.real_output,
        runtime.last_metrics.nominal_output,
        runtime.last_metrics.price_index,
        runtime.last_metrics.unemployment_rate,
        runtime.last_metrics.total_money,
        runtime.last_metrics.conservation_drift,
        runtime.last_metrics.aggregate_capital,
        runtime.last_metrics.household_consumption,
        runtime.last_metrics.wages_paid,
        runtime.last_metrics.firm_profit,
        runtime.last_metrics.tax_total,
        runtime.last_metrics.government_spending,
        runtime.last_metrics.government_deficit,
        runtime.last_metrics.public_capital,
    };
    if (!components_valid || !all_finite(runtime_values)
        || runtime.technology_index <= 0.0
        || runtime.public_capital < 0.0) {
        return Status(
            ErrorCode::invariant_violation,
            "M4 persistent columns are invalid"
        );
    }
    for (const auto& phase : runtime.last_phase_trace) {
        const std::array values{
            phase.money_total,
            phase.goods_total,
            phase.capital_total,
        };
        if (!all_finite(values)
            || static_cast<std::uint8_t>(phase.phase)
                > static_cast<std::uint8_t>(
                    M4Phase::stage_local_commit
                )) {
            return Status(
                ErrorCode::invariant_violation,
                "M4 phase trace is invalid"
            );
        }
    }
    M4SimulationSpec spec;
    spec.vertical = runtime.vertical;
    spec.economy = root.economy;
    spec.currency = root.currency;
    spec.households = root.households.alive_count();
    spec.consumption_firms = consumption_firms;
    spec.capital_firms = capital_firms;
    spec.seed = root.seed;
    spec.requested_capabilities = runtime.capability_mask;
    spec.stochastic = runtime.stochastic;
    spec.market_protocol = runtime.market_protocol;
    spec.rules = runtime.rules;
    static_cast<void>(tick);
    return validate_spec(spec);
}

Result<M4Initialization> build_m4_genesis(
    const M4SimulationSpec& spec
) {
    const auto validation = validate_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    const auto firm_count =
        spec.consumption_firms + spec.capital_firms;
    const double opening_money =
        static_cast<double>(spec.households)
            * spec.rules.initial_household_money
        + static_cast<double>(firm_count)
            * spec.rules.initial_firm_money;
    const double opening_capital =
        spec.vertical == M4Vertical::capital_fiscal
        ? static_cast<double>(spec.consumption_firms)
            * spec.rules.initial_consumption_capital
        : 0.0;
    core::GenesisSpec genesis;
    genesis.vertical =
        spec.vertical == M4Vertical::cash_loop
        ? core::GenesisVertical::m4_v0_cash_loop
        : core::GenesisVertical::m4_v1_capital_fiscal;
    genesis.economy = spec.economy;
    genesis.currency = spec.currency;
    genesis.households = spec.households;
    genesis.consumption_firms = spec.consumption_firms;
    genesis.capital_firms = spec.capital_firms;
    genesis.settlement_banks = 1;
    genesis.government =
        spec.vertical == M4Vertical::capital_fiscal;
    genesis.aggregate_opening_money = Money(opening_money);
    genesis.aggregate_opening_capital = Capital(opening_capital);
    genesis.seed = spec.seed;
    genesis.use_per_agent_endowments = true;
    genesis.household_opening_money =
        Money(spec.rules.initial_household_money);
    genesis.firm_opening_money = Money(spec.rules.initial_firm_money);
    genesis.opening_capital_to_consumption_firms = true;
    auto state = core::build_genesis(genesis);
    if (!state.ok()) {
        return state.status();
    }
    auto root = std::move(*state.get_if());
    root.households.for_each_alive(
        [&spec](HouseholdId, core::HouseholdComponent& household) {
            household.income_propensity = spec.rules.income_propensity;
            household.wealth_propensity = spec.rules.wealth_propensity;
            household.income_adjustment = spec.rules.income_adjustment;
        }
    );
    root.firms.for_each_alive(
        [&spec](FirmId, core::FirmComponent& firm) {
            const bool consumption =
                firm.sector == core::FirmSector::consumption;
            firm.goods_inventory = Goods(
                consumption
                    ? spec.rules.initial_consumption_inventory
                    : spec.rules.initial_capital_inventory
            );
            firm.productivity =
                consumption
                    ? spec.rules.linear_productivity
                    : spec.rules.capital_productivity;
            firm.technology =
                consumption
                    && spec.vertical == M4Vertical::capital_fiscal
                ? core::FirmTechnology::cobb_douglas
                : core::FirmTechnology::linear;
            firm.total_factor_productivity =
                spec.rules.total_factor_productivity;
            firm.capital_share = spec.rules.capital_share;
            firm.capital_output_ratio = spec.rules.capital_output_ratio;
            firm.investment_adjustment =
                spec.rules.investment_adjustment;
            firm.capital_depreciation =
                spec.rules.capital_depreciation;
            firm.demand_adjustment = spec.rules.demand_adjustment;
            firm.inventory_ratio = spec.rules.inventory_ratio;
            firm.markup_adjustment = spec.rules.markup_adjustment;
            firm.markup_minimum = spec.rules.markup_minimum;
            firm.markup_maximum = spec.rules.markup_maximum;
            firm.shortage_adjustment =
                spec.rules.wage_shortage_adjustment;
            firm.dividend_payout = spec.rules.dividend_payout;
            firm.posted_price = Price(
                consumption
                    ? spec.rules.initial_price
                    : spec.rules.initial_capital_price
            );
            firm.posted_wage = Money(spec.rules.initial_wage);
            firm.markup = spec.rules.initial_markup;
            firm.demand_expected = spec.rules.initial_expected_demand;
        }
    );
    M4Runtime runtime;
    runtime.vertical = spec.vertical;
    runtime.capability_mask = spec.requested_capabilities;
    runtime.rules = spec.rules;
    runtime.market_protocol = spec.market_protocol;
    runtime.stochastic = spec.stochastic;
    runtime.rng_key = {
        static_cast<std::uint32_t>(spec.seed),
        static_cast<std::uint32_t>(spec.seed >> 32U) ^ 0x9e3779b9U,
    };
    runtime.last_phase_trace.reserve(10);
    runtime.last_metrics.total_money = opening_money;
    return M4Initialization{std::move(root), std::move(runtime)};
}

Result<M4AdvanceResult> advance_ticks(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    std::uint64_t count,
    const M4AdvanceOptions& options
) {
    if (state.transaction_active) {
        return Status(
            ErrorCode::invalid_transaction_state,
            "M4 cannot advance during an accounting transaction"
        );
    }
    const Tick first = tick;
    if (count == 0) {
        return M4AdvanceResult{
            first,
            tick,
            0,
            runtime.last_metrics,
            scratch.capacity_signature(),
            0,
            0,
        };
    }
    M4AdvanceResult result;
    std::uint64_t transfers = 0;
    std::uint64_t trades = 0;
    for (std::uint64_t index = 0; index < count; ++index) {
        auto current = advance_one(
            state,
            runtime,
            scratch,
            tick,
            options
        );
        if (!current.ok()) {
            return current.status();
        }
        result = std::move(*current.get_if());
        transfers += result.transfer_count;
        trades += result.trade_count;
    }
    result.first_tick = first;
    result.next_tick = tick;
    result.advanced_ticks = count;
    result.transfer_count = transfers;
    result.trade_count = trades;
    return result;
}

Result<M4AdvanceResult> advance_tick(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    const M4AdvanceOptions& options
) {
    return advance_ticks(
        state,
        runtime,
        scratch,
        tick,
        1,
        options
    );
}

}  // namespace macro_sim::simulation
