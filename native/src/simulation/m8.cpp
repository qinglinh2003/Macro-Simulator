#include "macro_sim/simulation/m8.hpp"

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
#include "macro_sim/core/transaction.hpp"

namespace macro_sim::simulation {
namespace {

constexpr double kTolerance = 1.0e-8;
constexpr double kEconomicEpsilon = 1.0e-12;
constexpr double kDaysPerYear = 365.2425;
constexpr std::size_t kAbsentIndex =
    std::numeric_limits<std::size_t>::max();

[[nodiscard]] bool finite(double value) noexcept {
    return std::isfinite(value);
}

template <std::size_t Size>
[[nodiscard]] bool all_finite(const std::array<double, Size> &values) noexcept {
    return std::all_of(values.begin(), values.end(), finite);
}

[[nodiscard]] std::size_t firm_index(
    const M4TickScratch &scratch, FirmId firm
) noexcept {
    const auto index = static_cast<std::size_t>(firm.value());
    return index < scratch.firm_dense_index_.size()
               ? scratch.firm_dense_index_[index]
               : kAbsentIndex;
}

[[nodiscard]] double projected_balance(
    const M4TickScratch &scratch, AccountId account
) noexcept {
    const auto index = static_cast<std::size_t>(account.value());
    return index < scratch.balances_.size()
               ? scratch.balances_[index]
               : 0.0;
}

[[nodiscard]] bool valid_rationing(EnergyRationing rationing) noexcept {
    return static_cast<std::uint8_t>(rationing) <=
           static_cast<std::uint8_t>(EnergyRationing::industry_first);
}

[[nodiscard]] bool valid_fault_point(M8FaultPoint point) noexcept {
    return static_cast<std::uint8_t>(point) <=
           static_cast<std::uint8_t>(M8FaultPoint::before_commit);
}

[[nodiscard]] Status injected_fault(
    const M8AdvanceOptions &options, M8FaultPoint point
) noexcept {
    if (options.fault_point == point) {
        return Status(ErrorCode::internal_error, "injected M8 energy fault");
    }
    return Status::success();
}

[[nodiscard]] SettlementNodeId genesis_settlement_node(
    const core::RootState &state
) noexcept {
    SettlementNodeId result{};
    state.firms.for_each_alive(
        [&state, &result](FirmId, const core::FirmComponent &firm) {
            if (result.valid()) {
                return;
            }
            const auto *account = state.postings.get(firm.primary_account);
            if (account != nullptr) {
                result = account->key.settlement_node;
            }
        }
    );
    if (!result.valid()) {
        state.banks.for_each_alive(
            [&result](BankId, const core::BankComponent &bank) {
                if (!result.valid()) {
                    result = bank.settlement_node;
                }
            }
        );
    }
    return result;
}

[[nodiscard]] FirmLifecycleRecord lifecycle_for_energy_firm(
    const core::RootState &state, const M6Runtime &runtime, FirmId firm_id
) {
    FirmLifecycleRecord lifecycle;
    lifecycle.firm = firm_id;
    lifecycle.statement.firm = firm_id;
    const auto *firm = state.firms.get(firm_id);
    const auto *account =
        firm == nullptr ? nullptr : state.postings.get(firm->primary_account);
    if (firm == nullptr || account == nullptr) {
        return lifecycle;
    }
    lifecycle.statement.cash = account->balance.value();
    lifecycle.statement.capital_units = firm->physical_capital.value();
    lifecycle.statement.capital_unit_price =
        runtime.replacement_capital_price;
    lifecycle.statement.capital_value =
        lifecycle.statement.capital_units *
        lifecycle.statement.capital_unit_price;
    lifecycle.statement.output_inventory_units =
        firm->goods_inventory.value();
    lifecycle.statement.output_inventory_unit_price =
        firm->posted_price.value();
    lifecycle.statement.output_inventory_value =
        lifecycle.statement.output_inventory_units *
        lifecycle.statement.output_inventory_unit_price;
    lifecycle.statement.inventory_value =
        lifecycle.statement.output_inventory_value;
    lifecycle.statement.gross_assets =
        lifecycle.statement.cash + lifecycle.statement.capital_value +
        lifecycle.statement.inventory_value;
    lifecycle.statement.book_equity = lifecycle.statement.gross_assets;
    lifecycle.statement.eligible_collateral_value =
        (1.0 - runtime.rules.capital_haircut) *
            lifecycle.statement.capital_value +
        (1.0 - runtime.rules.inventory_haircut) *
            lifecycle.statement.inventory_value;
    lifecycle.statement.borrowing_base_proxy =
        lifecycle.statement.cash +
        lifecycle.statement.eligible_collateral_value;
    lifecycle.statement.borrowing_base_headroom =
        lifecycle.statement.borrowing_base_proxy;
    lifecycle.active = true;
    return lifecycle;
}

[[nodiscard]] Status create_energy_firm(
    core::RootState &state, M6Runtime &financial_runtime,
    const EnergyRules &rules, double expected_demand, double capital,
    double inventory, bool state_owned, SettlementNodeId settlement_node,
    EnergyProducerComponent &producer
) {
    core::FirmComponent component;
    component.sector = core::FirmSector::energy;
    component.goods_inventory = Goods(inventory);
    component.physical_capital = Capital(capital);
    component.productivity = rules.producer_productivity;
    component.technology = core::FirmTechnology::cobb_douglas;
    component.total_factor_productivity = 1.0;
    component.capital_share = 0.3;
    component.capital_output_ratio =
        rules.capacity_per_capital > kEconomicEpsilon
            ? 1.0 /
                  (rules.capacity_per_capital *
                   rules.initial_utilization)
            : 0.0;
    component.investment_adjustment = 0.0;
    component.capital_depreciation = 0.0;
    component.demand_adjustment = rules.demand_adjustment;
    component.inventory_ratio = rules.producer_inventory_ratio;
    component.markup_adjustment = rules.markup_adjustment;
    component.markup_minimum = rules.markup_minimum;
    component.markup_maximum = rules.markup_maximum;
    component.shortage_adjustment = 0.0075;
    component.dividend_payout = 0.5;
    component.posted_price = Price(rules.initial_price);
    component.posted_wage = Money(rules.initial_wage);
    component.markup = rules.initial_markup;
    component.demand_expected = expected_demand;
    component.target_inventory_previous =
        rules.producer_inventory_ratio * expected_demand;
    component.sales_previous = expected_demand;

    auto created = state.firms.create(component);
    if (!created.ok()) {
        return created.status();
    }
    const auto firm_id = created.get_if()->id;
    auto account = state.postings.create_account(
        {
            core::AccountKind::deposit,
            state.economy,
            core::OwnerId::firm(firm_id),
            state.currency,
            settlement_node,
        },
        Money(0.0)
    );
    if (!account.ok()) {
        return account.status();
    }
    state.firms.get(firm_id)->primary_account = *account.get_if();
    if (rules.initial_producer_cash > kEconomicEpsilon) {
        core::SettlementTransaction transaction(state);
        auto status = transaction.transfer(
            state.institutions.treasury_account, *account.get_if(),
            Money(rules.initial_producer_cash)
        );
        if (!status.ok()) {
            return status;
        }
        const auto committed = transaction.commit();
        if (!committed.ok()) {
            return committed.status();
        }
    }
    if (financial_runtime.firms.size() <= firm_id.value()) {
        financial_runtime.firms.resize(
            static_cast<std::size_t>(firm_id.value() + 1U)
        );
    }
    financial_runtime.firms[static_cast<std::size_t>(firm_id.value())] =
        lifecycle_for_energy_firm(state, financial_runtime, firm_id);
    producer.firm = firm_id;
    producer.active = true;
    producer.state_owned = state_owned;
    producer.capacity_per_capital = rules.capacity_per_capital;
    producer.inventory = inventory;
    producer.inventory_cost = inventory * rules.initial_price;
    producer.demand_expected = expected_demand;
    return Status::success();
}

void ensure_runtime_indexes(
    const core::RootState &state, M8Runtime &runtime
) {
    const auto firm_slots = static_cast<std::size_t>(
        state.firms.allocator_state().next_id
    );
    const auto household_slots = static_cast<std::size_t>(
        state.households.allocator_state().next_id
    );
    runtime.energy_producers.resize(firm_slots);
    runtime.energy_inputs.resize(firm_slots);
    runtime.household_energy.resize(household_slots);
}

[[nodiscard]] Status validate_energy_projection(
    const core::RootState &state, const M8Runtime &runtime,
    bool allow_pending_lifecycle,
    std::span<const M6FirmExitCommand> exits = {},
    std::span<const M6FirmEntryCommand> entries = {}
) noexcept {
    if (!runtime.energy_rules.enabled) {
        return Status::success();
    }
    const auto exiting = [exits](FirmId firm) {
        return std::any_of(
            exits.begin(), exits.end(),
            [firm](const M6FirmExitCommand &command) {
                return command.firm == firm;
            }
        );
    };
    const auto entering = [entries](FirmId firm) {
        return std::any_of(
            entries.begin(), entries.end(),
            [firm](const M6FirmEntryCommand &command) {
                return command.firm == firm;
            }
        );
    };
    for (std::size_t index = 1;
         index < runtime.energy_producers.size(); ++index) {
        const auto &producer = runtime.energy_producers[index];
        if (!producer.active) {
            continue;
        }
        const auto *firm = state.firms.get(producer.firm);
        const std::array values{
            producer.capacity_per_capital,
            producer.inventory,
            producer.inventory_cost,
            producer.produced,
            producer.sales,
            producer.revenue,
            producer.demand_expected,
        };
        if (producer.firm.value() != index || firm == nullptr ||
            firm->sector != core::FirmSector::energy ||
            !all_finite(values) || producer.capacity_per_capital <= 0.0 ||
            producer.inventory < -kTolerance ||
            producer.inventory_cost < -kTolerance ||
            producer.produced < -kTolerance ||
            producer.sales < -kTolerance ||
            producer.revenue < -kTolerance ||
            producer.demand_expected < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 energy producer projection is invalid"
            );
        }
    }
    for (std::size_t index = 1;
         index < runtime.energy_inputs.size(); ++index) {
        const auto &input = runtime.energy_inputs[index];
        if (!input.active) {
            continue;
        }
        const auto *firm = state.firms.get(input.firm);
        const bool pending_entry =
            allow_pending_lifecycle && entering(input.firm);
        const std::array values{
            input.intensity,
            input.coverage_days,
            input.stock,
            input.stock_cost,
            input.average_cost,
            input.bought,
            input.used,
            input.unmet,
        };
        if (input.firm.value() != index ||
            (firm == nullptr && !pending_entry) ||
            (firm != nullptr &&
             firm->sector != core::FirmSector::consumption &&
             firm->sector != core::FirmSector::capital) ||
            !all_finite(values) || input.intensity < 0.0 ||
            input.coverage_days < 0.0 || input.stock < -kTolerance ||
            input.stock_cost < -kTolerance || input.average_cost < 0.0 ||
            input.bought < -kTolerance || input.used < -kTolerance ||
            input.unmet < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 energy input projection is invalid"
            );
        }
    }
    for (std::size_t index = 1;
         index < runtime.household_energy.size(); ++index) {
        const auto &record = runtime.household_energy[index];
        if (!record.active) {
            continue;
        }
        const auto *household = state.households.get(record.household);
        const std::array values{
            record.need,
            record.bought,
            record.spent,
            record.subsidy,
            record.coverage,
        };
        if (record.household.value() != index || household == nullptr ||
            !all_finite(values) || record.need < -kTolerance ||
            record.bought < -kTolerance || record.spent < -kTolerance ||
            record.subsidy < -kTolerance || record.coverage < -kTolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 household energy projection is invalid"
            );
        }
    }
    Status coverage_status = Status::success();
    state.firms.for_each_alive(
        [&runtime, &exiting, allow_pending_lifecycle,
         &coverage_status](
            FirmId id, const core::FirmComponent &firm
        ) {
            if (!coverage_status.ok()) {
                return;
            }
            const auto index =
                static_cast<std::size_t>(id.value());
            if (firm.sector == core::FirmSector::energy) {
                const bool active =
                    index < runtime.energy_producers.size() &&
                    runtime.energy_producers[index].active;
                if (!active &&
                    !(allow_pending_lifecycle && exiting(id))) {
                    coverage_status = Status(
                        ErrorCode::invariant_violation,
                        "M8 live producer has no energy component"
                    );
                }
            } else if (
                firm.sector == core::FirmSector::consumption ||
                firm.sector == core::FirmSector::capital
            ) {
                const bool active =
                    index < runtime.energy_inputs.size() &&
                    runtime.energy_inputs[index].active;
                if (!active &&
                    !(allow_pending_lifecycle && exiting(id))) {
                    coverage_status = Status(
                        ErrorCode::invariant_violation,
                        "M8 downstream firm has no energy input component"
                    );
                }
            }
        }
    );
    if (!coverage_status.ok()) {
        return coverage_status;
    }
    return Status::success();
}

[[nodiscard]] double household_need_units(
    const M7TickScratch &population, HouseholdId household,
    std::int32_t calendar_day
) noexcept {
    double need = 0.0;
    for (const auto person_id :
         population.membership_.members(household)) {
        const auto *person = population.persons_.get(person_id);
        if (person == nullptr || !person->alive) {
            continue;
        }
        const double age = std::max(
            0.0,
            static_cast<double>(calendar_day - person->birth_day) /
                kDaysPerYear
        );
        need += age < 18.0 ? 0.6 : age >= 65.0 ? 0.8 : 1.0;
    }
    return need;
}

class M8Extension final : public M7TickExtension {
  public:
    M8Extension(M8Runtime &runtime, M8TickScratch &scratch,
                const M8AdvanceOptions &options) noexcept
        : runtime_(runtime), scratch_(scratch), options_(options) {}

    Status prepare_tick(
        const core::RootState &state, M4Runtime &,
        M4TickScratch &real, M5Runtime &, M5TickScratch &,
        M6Runtime &, M6TickScratch &, M7Runtime &,
        M7TickScratch &, Tick, PhiloxRng &
    ) override {
        scratch_.energy_producers_ = runtime_.energy_producers;
        scratch_.energy_inputs_ = runtime_.energy_inputs;
        scratch_.household_energy_ = runtime_.household_energy;
        scratch_.deprivation_ = runtime_.deprivation;
        scratch_.strategic_reserve_stock_ =
            runtime_.strategic_reserve_stock;
        scratch_.strategic_reserve_cost_ =
            runtime_.strategic_reserve_cost;
        scratch_.energy_price_ = runtime_.energy_price;
        scratch_.slow_energy_price_ = runtime_.slow_energy_price;
        scratch_.energy_event_counter_ = runtime_.energy_event_counter;
        scratch_.working_metrics_ = M8Metrics{};
        scratch_.orders_.clear();
        scratch_.offers_.clear();
        scratch_.buyer_order_.clear();
        scratch_.seller_order_.clear();
        if (scratch_.industry_use_need_.size() <
            state.firms.allocator_state().next_id) {
            scratch_.industry_use_need_.resize(
                static_cast<std::size_t>(
                    state.firms.allocator_state().next_id
                )
            );
        }
        std::fill(
            scratch_.industry_use_need_.begin(),
            scratch_.industry_use_need_.end(), 0.0
        );
        if (scratch_.household_consumption_.size() <
            state.households.allocator_state().next_id) {
            scratch_.household_consumption_.resize(
                static_cast<std::size_t>(
                    state.households.allocator_state().next_id
                )
            );
        }
        std::fill(
            scratch_.household_consumption_.begin(),
            scratch_.household_consumption_.end(), 0.0
        );
        scratch_.opening_balances_ = real.balances_;
        for (auto &producer : scratch_.energy_producers_) {
            producer.produced = 0.0;
            producer.sales = 0.0;
            producer.revenue = 0.0;
        }
        for (auto &input : scratch_.energy_inputs_) {
            input.bought = 0.0;
            input.used = 0.0;
            input.unmet = 0.0;
        }
        for (auto &record : scratch_.household_energy_) {
            record.need = 0.0;
            record.bought = 0.0;
            record.spent = 0.0;
            record.subsidy = 0.0;
            record.coverage = 0.0;
        }
        input_ =
            options_.energy_input.value_or(runtime_.energy_input);
        return validate_energy_input(input_);
    }

    Status before_labor(
        const core::RootState &state, M4Runtime &,
        M4TickScratch &real, M5Runtime &, M5TickScratch &,
        M6Runtime &, M6TickScratch &, M7Runtime &,
        M7TickScratch &, Tick, PhiloxRng &
    ) override {
        if (!runtime_.energy_rules.enabled) {
            return Status::success();
        }
        const auto &rules = runtime_.energy_rules;
        const auto &policy = runtime_.energy_policy;
        const double slow_weight =
            1.0 / std::max(1.0, rules.slow_price_days);
        scratch_.slow_energy_price_ +=
            slow_weight *
            (scratch_.energy_price_ - scratch_.slow_energy_price_);
        double hoarding = 1.0;
        if (rules.hoarding_beta > 0.0 &&
            scratch_.slow_energy_price_ > kEconomicEpsilon) {
            const double trend =
                scratch_.energy_price_ /
                    scratch_.slow_energy_price_ -
                1.0;
            hoarding +=
                rules.hoarding_beta * std::max(0.0, trend);
        }

        double industry_demand = 0.0;
        for (auto &input : scratch_.energy_inputs_) {
            if (!input.active) {
                continue;
            }
            const auto dense = firm_index(real, input.firm);
            const auto *firm = state.firms.get(input.firm);
            if (dense == kAbsentIndex ||
                dense >= real.firm_work_.size() || firm == nullptr) {
                continue;
            }
            auto &work = real.firm_work_[dense];
            const double use_need =
                input.intensity * work.production_target *
                input_.industry_demand_multiplier;
            const double target =
                hoarding * input.coverage_days *
                input.intensity * work.demand_expected;
            const double demand = std::max(
                0.0,
                use_need +
                    rules.downstream_gap_close *
                        (target - input.stock)
            );
            scratch_.industry_use_need_[
                static_cast<std::size_t>(input.firm.value())
            ] = use_need;
            const double balance =
                projected_balance(real, firm->primary_account);
            const double reserved_energy_cash = std::min(
                balance,
                demand * scratch_.energy_price_ *
                    (1.0 + policy.excise_rate)
            );
            if (work.posted_wage > kEconomicEpsilon) {
                work.labor_demand_effective = std::min(
                    work.labor_demand_effective,
                    std::max(
                        0.0,
                        balance - reserved_energy_cash
                    ) /
                        work.posted_wage
                );
            }
            if (demand > kEconomicEpsilon &&
                balance > kEconomicEpsilon) {
                scratch_.orders_.push_back(
                    {
                        EnergyBuyerKind::industry,
                        input.firm.value(),
                        firm->primary_account,
                        demand,
                        balance /
                            (1.0 + policy.excise_rate),
                        0.0,
                        0.0,
                    }
                );
                industry_demand += demand;
            }
        }

        double household_demand = 0.0;
        if (rules.household_energy) {
            for (std::size_t index = 0;
                 index < real.household_ids_.size(); ++index) {
                const auto household_id = real.household_ids_[index];
                const auto *household =
                    state.households.get(household_id);
                const double need =
                    rules.household_need *
                    input_.household_demand_multiplier;
                auto &record = scratch_.household_energy_[
                    static_cast<std::size_t>(household_id.value())
                ];
                record.household = household_id;
                record.active = true;
                record.need = need;
                const double balance = projected_balance(
                    real, household->primary_account
                );
                if (need > kEconomicEpsilon &&
                    balance > kEconomicEpsilon) {
                    scratch_.orders_.push_back(
                        {
                            EnergyBuyerKind::household,
                            household_id.value(),
                            household->primary_account,
                            need,
                            balance /
                                (1.0 + policy.excise_rate),
                            0.0,
                            0.0,
                        }
                    );
                    household_demand += need;
                }
            }
        }

        double public_demand = 0.0;
        if (policy.strategic_reserve_flow_cap >
                kEconomicEpsilon &&
            scratch_.strategic_reserve_stock_ +
                    kEconomicEpsilon <
                policy.strategic_reserve_target) {
            public_demand = std::min(
                policy.strategic_reserve_flow_cap,
                policy.strategic_reserve_target -
                    scratch_.strategic_reserve_stock_
            );
            scratch_.orders_.push_back(
                {
                    EnergyBuyerKind::strategic_reserve,
                    0,
                    state.institutions.treasury_account,
                    public_demand,
                    std::numeric_limits<double>::infinity(),
                    0.0,
                    0.0,
                }
            );
        }

        const double total_demand =
            industry_demand + household_demand + public_demand;
        std::size_t active_producers = 0;
        for (const auto &producer : scratch_.energy_producers_) {
            active_producers += producer.active ? 1U : 0U;
        }
        if (active_producers == 0) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 energy market has no active producer"
            );
        }
        const double per_producer =
            total_demand /
            static_cast<double>(active_producers);
        for (auto &producer : scratch_.energy_producers_) {
            if (!producer.active) {
                continue;
            }
            const auto dense = firm_index(real, producer.firm);
            const auto *firm = state.firms.get(producer.firm);
            if (dense == kAbsentIndex ||
                dense >= real.firm_work_.size() || firm == nullptr) {
                return Status(
                    ErrorCode::invariant_violation,
                    "M8 producer is absent from the firm projection"
                );
            }
            auto &work = real.firm_work_[dense];
            const double target_inventory =
                rules.producer_inventory_ratio *
                producer.demand_expected;
            const double target = std::max(
                0.0,
                per_producer +
                    rules.downstream_gap_close *
                        (target_inventory - producer.inventory)
            );
            const double capacity =
                producer.capacity_per_capital *
                firm->physical_capital.value() *
                input_.capacity_multiplier;
            work.target_inventory = target_inventory;
            work.production_target =
                std::min(target, capacity);
            work.labor_demand_notional =
                work.production_target /
                std::max(
                    kEconomicEpsilon,
                    firm->productivity *
                        input_.labor_availability_multiplier
                );
            work.posted_wage = firm->posted_wage.value();
            work.posted_price =
                policy.state_owned_price_at_cost &&
                        producer.state_owned
                    ? work.posted_wage /
                          std::max(
                              kEconomicEpsilon,
                              firm->productivity
                          )
                    : firm->posted_price.value();
            work.markup =
                policy.state_owned_price_at_cost &&
                        producer.state_owned
                    ? 0.0
                    : firm->markup;
            const double balance =
                projected_balance(real, firm->primary_account);
            work.labor_demand_effective =
                work.posted_wage > kEconomicEpsilon
                    ? std::min(
                          work.labor_demand_notional,
                          balance / work.posted_wage
                      )
                    : 0.0;
            work.closing_inventory = producer.inventory;
            work.closing_capital =
                firm->physical_capital.value();
        }
        scratch_.working_metrics_.energy.requested_total =
            total_demand;
        scratch_.working_metrics_.energy.requested_households =
            household_demand;
        scratch_.working_metrics_.energy.requested_industry =
            industry_demand;
        scratch_.working_metrics_.energy.requested_public =
            public_demand;
        return injected_fault(
            options_, M8FaultPoint::after_energy_plan
        );
    }

    Status after_labor(
        const core::RootState &state, M4Runtime &,
        M4TickScratch &real, M5Runtime &, M5TickScratch &,
        M6Runtime &, M6TickScratch &, M7Runtime &,
        M7TickScratch &, Tick, PhiloxRng &rng
    ) override {
        if (!runtime_.energy_rules.enabled) {
            return Status::success();
        }
        auto status = produce_and_build_offers(state, real);
        if (!status.ok()) {
            return status;
        }
        build_strategic_reserve_offer(state);
        status = clear_energy_market(state, real, rng);
        if (!status.ok()) {
            return status;
        }
        status = settle_energy_results(state, real);
        if (!status.ok()) {
            return status;
        }
        return injected_fault(
            options_, M8FaultPoint::after_energy_clearing
        );
    }

    Status close_day(
        const core::RootState &state, M4Runtime &,
        M4TickScratch &real, M5Runtime &, M5TickScratch &,
        M6Runtime &, M6TickScratch &financial, M7Runtime &population,
        M7TickScratch &population_scratch, Tick tick, PhiloxRng &
    ) override {
        if (!runtime_.energy_rules.enabled) {
            return Status::success();
        }
        for (const auto &exit : financial.firm_exits_) {
            const auto index =
                static_cast<std::size_t>(exit.firm.value());
            if (index < scratch_.energy_producers_.size()) {
                scratch_.energy_producers_[index].active = false;
            }
            if (index < scratch_.energy_inputs_.size()) {
                scratch_.energy_inputs_[index].active = false;
            }
        }
        for (const auto &entry : financial.firm_entries_) {
            const auto index =
                static_cast<std::size_t>(entry.firm.value());
            if (scratch_.energy_inputs_.size() <= index) {
                scratch_.energy_inputs_.resize(index + 1U);
            }
            auto &input = scratch_.energy_inputs_[index];
            input.firm = entry.firm;
            input.active = true;
            input.intensity =
                runtime_.energy_rules.downstream_intensity;
            input.coverage_days =
                runtime_.energy_rules.downstream_coverage_days;
            input.average_cost = scratch_.energy_price_;
        }
        for (const auto household :
             population_scratch.retired_households_) {
            const auto index =
                static_cast<std::size_t>(household.value());
            if (index < scratch_.household_energy_.size()) {
                scratch_.household_energy_[index].active = false;
            }
        }
        for (const auto &event :
             population_scratch.pending_leaving_home_) {
            const auto index = static_cast<std::size_t>(
                event.destination.value()
            );
            if (scratch_.household_energy_.size() <= index) {
                scratch_.household_energy_.resize(index + 1U);
            }
            scratch_.household_energy_[index].household =
                event.destination;
            scratch_.household_energy_[index].active = false;
        }
        update_deprivation(
            state, real, population, population_scratch, tick
        );
        scratch_.working_metrics_.energy.strategic_reserve_stock =
            scratch_.strategic_reserve_stock_;
        scratch_.working_metrics_.energy.deprivation_boundary =
            scratch_.deprivation_.boundary_breached;
        ++scratch_.energy_event_counter_;
        return Status::success();
    }

    Status validate(
        const core::RootState &state, const M4Runtime &,
        const M4TickScratch &real, const M5Runtime &,
        const M5TickScratch &, const M6Runtime &,
        const M6TickScratch &financial, const M7Runtime &,
        const M7TickScratch &, Tick
    ) const override {
        M8Runtime staged = runtime_;
        staged.energy_input = input_;
        staged.energy_producers = scratch_.energy_producers_;
        staged.energy_inputs = scratch_.energy_inputs_;
        staged.household_energy = scratch_.household_energy_;
        staged.deprivation = scratch_.deprivation_;
        staged.strategic_reserve_stock =
            scratch_.strategic_reserve_stock_;
        staged.strategic_reserve_cost =
            scratch_.strategic_reserve_cost_;
        staged.energy_price = scratch_.energy_price_;
        staged.slow_energy_price = scratch_.slow_energy_price_;
        staged.energy_event_counter =
            scratch_.energy_event_counter_;
        staged.last_metrics = scratch_.working_metrics_;
        auto status = validate_energy_projection(
            state, staged, true, financial.firm_exits_,
            financial.firm_entries_
        );
        if (!status.ok()) {
            return status;
        }
        const auto &metrics = scratch_.working_metrics_.energy;
        const double resource_error =
            metrics.opening_supply -
            (metrics.sold +
             std::accumulate(
                 scratch_.offers_.begin(), scratch_.offers_.end(),
                 0.0,
                 [](double total, const EnergyOffer &offer) {
                     return total + offer.stock;
                 }
             ));
        const double tolerance = std::max(
            state.accounting_tolerance,
            1.0e-9 *
                std::max(1.0, metrics.opening_supply)
        );
        if (!finite(resource_error) ||
            std::abs(resource_error) > tolerance) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 energy resource conservation failed"
            );
        }
        if (!all_finite(std::array{
                scratch_.strategic_reserve_stock_,
                scratch_.strategic_reserve_cost_,
                scratch_.energy_price_,
                scratch_.slow_energy_price_,
            }) ||
            scratch_.strategic_reserve_stock_ < -kTolerance ||
            scratch_.strategic_reserve_cost_ < -kTolerance ||
            scratch_.energy_price_ <= 0.0 ||
            scratch_.slow_energy_price_ <= 0.0 ||
            !std::all_of(
                real.balances_.begin(), real.balances_.end(),
                finite
            )) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 energy state is not finite"
            );
        }
        return injected_fault(
            options_, M8FaultPoint::before_commit
        );
    }

    void commit(
        core::RootState &state, M4Runtime &, M4TickScratch &,
        M5Runtime &, M5TickScratch &, M6Runtime &,
        M6TickScratch &, M7Runtime &,
        M7TickScratch &population_scratch, Tick,
        const M7Metrics &metrics
    ) noexcept override {
        runtime_.energy_input = input_;
        std::swap(
            runtime_.energy_producers,
            scratch_.energy_producers_
        );
        std::swap(
            runtime_.energy_inputs,
            scratch_.energy_inputs_
        );
        std::swap(
            runtime_.household_energy,
            scratch_.household_energy_
        );
        for (const auto &event :
             population_scratch.pending_leaving_home_) {
            const auto index = static_cast<std::size_t>(
                event.destination.value()
            );
            if (index >= runtime_.household_energy.size() ||
                state.households.get(event.destination) == nullptr) {
                std::terminate();
            }
            auto &record =
                runtime_.household_energy[index];
            record.household = event.destination;
            record.active = true;
        }
        runtime_.deprivation = scratch_.deprivation_;
        runtime_.strategic_reserve_stock =
            scratch_.strategic_reserve_stock_;
        runtime_.strategic_reserve_cost =
            scratch_.strategic_reserve_cost_;
        runtime_.energy_price = scratch_.energy_price_;
        runtime_.slow_energy_price =
            scratch_.slow_energy_price_;
        runtime_.energy_event_counter =
            scratch_.energy_event_counter_;
        scratch_.working_metrics_.economy = metrics;
        runtime_.last_metrics = scratch_.working_metrics_;
    }

  private:
    [[nodiscard]] Status produce_and_build_offers(
        const core::RootState &state, M4TickScratch &real
    ) {
        const auto &policy = runtime_.energy_policy;
        const auto &rules = runtime_.energy_rules;
        double private_supply = 0.0;
        double production = 0.0;
        double capacity_total = 0.0;
        for (auto &producer : scratch_.energy_producers_) {
            if (!producer.active) {
                continue;
            }
            const auto dense = firm_index(real, producer.firm);
            const auto *firm = state.firms.get(producer.firm);
            if (dense == kAbsentIndex ||
                dense >= real.firm_work_.size() || firm == nullptr) {
                return Status(
                    ErrorCode::invariant_violation,
                    "M8 producer projection became stale"
                );
            }
            auto &work = real.firm_work_[dense];
            const double capacity =
                producer.capacity_per_capital *
                firm->physical_capital.value() *
                input_.capacity_multiplier;
            const double labor_output =
                firm->productivity * work.hired *
                input_.labor_availability_multiplier *
                input_.supply_multiplier;
            const double produced =
                std::min(capacity, std::max(0.0, labor_output));
            producer.produced = produced;
            producer.inventory += produced;
            producer.inventory_cost +=
                produced > kEconomicEpsilon
                    ? work.wage_bill
                    : 0.0;
            work.produced = produced;
            work.closing_inventory = producer.inventory;
            const double posted =
                work.posted_price *
                input_.reference_price_multiplier;
            const double price =
                policy.price_cap > kEconomicEpsilon
                    ? std::min(posted, policy.price_cap)
                    : posted;
            scratch_.offers_.push_back(
                {
                    producer.firm,
                    firm->primary_account,
                    producer.inventory,
                    price,
                    posted,
                    0.0,
                    0.0,
                    false,
                }
            );
            production += produced;
            capacity_total += capacity;
            private_supply += producer.inventory;
        }
        scratch_.working_metrics_.energy.production = production;
        scratch_.working_metrics_.energy.capacity = capacity_total;
        scratch_.working_metrics_.energy.utilization =
            capacity_total > kEconomicEpsilon
                ? production / capacity_total
                : 0.0;
        scratch_.working_metrics_.energy.opening_supply =
            private_supply;
        static_cast<void>(rules);
        return Status::success();
    }

    void build_strategic_reserve_offer(
        const core::RootState &state
    ) {
        const auto &policy = runtime_.energy_policy;
        if (policy.strategic_reserve_flow_cap <=
                kEconomicEpsilon ||
            scratch_.strategic_reserve_stock_ <=
                policy.strategic_reserve_target +
                    kEconomicEpsilon ||
            scratch_.offers_.empty()) {
            return;
        }
        const double amount = std::min(
            policy.strategic_reserve_flow_cap,
            scratch_.strategic_reserve_stock_ -
                policy.strategic_reserve_target
        );
        const double minimum_price = std::min_element(
            scratch_.offers_.begin(), scratch_.offers_.end(),
            [](const EnergyOffer &left,
               const EnergyOffer &right) {
                return left.price < right.price;
            }
        )->price;
        scratch_.offers_.push_back(
            {
                FirmId{},
                state.institutions.treasury_account,
                amount,
                0.999 * minimum_price,
                0.999 * minimum_price,
                0.0,
                0.0,
                true,
            }
        );
        scratch_.working_metrics_.energy.opening_supply += amount;
    }

    [[nodiscard]] Status transfer_trade(
        const core::RootState &state, M4TickScratch &real,
        EnergyOrder &order, EnergyOffer &offer, double quantity
    ) {
        const double value = quantity * offer.price;
        auto status = stage_m4_transfer(
            state, real, order.account, offer.account, value
        );
        if (!status.ok()) {
            return status;
        }
        double excise = 0.0;
        if (order.kind !=
                EnergyBuyerKind::strategic_reserve &&
            runtime_.energy_policy.excise_rate >
                kEconomicEpsilon) {
            excise =
                value *
                runtime_.energy_policy.excise_rate;
            status = stage_m4_transfer(
                state, real, order.account,
                state.institutions.treasury_account, excise
            );
            if (!status.ok()) {
                return status;
            }
        }
        order.allocated += quantity;
        order.spending += value;
        order.budget -= value;
        offer.stock -= quantity;
        offer.sold += quantity;
        offer.revenue += value;
        scratch_.working_metrics_.energy.excise_paid += excise;
        ++scratch_.energy_event_counter_;
        return Status::success();
    }

    [[nodiscard]] Status clear_buyer_sequence(
        const core::RootState &state, M4TickScratch &real,
        std::span<const std::size_t> buyers
    ) {
        for (const auto buyer_index : buyers) {
            auto &order = scratch_.orders_[buyer_index];
            double remaining =
                std::max(0.0, order.demand - order.allocated);
            for (const auto seller_index : scratch_.seller_order_) {
                auto &offer = scratch_.offers_[seller_index];
                if (remaining <= kEconomicEpsilon ||
                    order.budget <= kEconomicEpsilon) {
                    break;
                }
                if (offer.stock <= kEconomicEpsilon ||
                    offer.price <= kEconomicEpsilon) {
                    continue;
                }
                const double available =
                    order.kind ==
                            EnergyBuyerKind::strategic_reserve
                        ? std::numeric_limits<double>::infinity()
                        : projected_balance(real, order.account) /
                              (
                                  1.0 +
                                  runtime_.energy_policy.excise_rate
                              );
                const double quantity = std::min(
                    {
                        remaining,
                        offer.stock,
                        order.budget / offer.price,
                        available / offer.price,
                    }
                );
                if (quantity <= kEconomicEpsilon) {
                    continue;
                }
                const auto status = transfer_trade(
                    state, real, order, offer, quantity
                );
                if (!status.ok()) {
                    return status;
                }
                remaining -= quantity;
            }
        }
        return Status::success();
    }

    [[nodiscard]] Status clear_proportional(
        const core::RootState &state, M4TickScratch &real
    ) {
        double total_demand = 0.0;
        for (const auto &order : scratch_.orders_) {
            total_demand += order.demand;
        }
        if (total_demand <= kEconomicEpsilon) {
            return Status::success();
        }
        for (const auto seller_index : scratch_.seller_order_) {
            auto &offer = scratch_.offers_[seller_index];
            const double base = offer.stock;
            if (base <= kEconomicEpsilon ||
                offer.price <= kEconomicEpsilon) {
                continue;
            }
            for (auto &order : scratch_.orders_) {
                const double share =
                    order.demand / total_demand;
                const double available =
                    order.kind ==
                            EnergyBuyerKind::strategic_reserve
                        ? std::numeric_limits<double>::infinity()
                        : projected_balance(real, order.account) /
                              (
                                  1.0 +
                                  runtime_.energy_policy.excise_rate
                              );
                const double quantity = std::min(
                    {
                        base * share,
                        order.demand - order.allocated,
                        order.budget / offer.price,
                        available / offer.price,
                        offer.stock,
                    }
                );
                if (quantity <= kEconomicEpsilon) {
                    continue;
                }
                const auto status = transfer_trade(
                    state, real, order, offer, quantity
                );
                if (!status.ok()) {
                    return status;
                }
            }
        }
        return Status::success();
    }

    [[nodiscard]] Status clear_energy_market(
        const core::RootState &state, M4TickScratch &real,
        PhiloxRng &rng
    ) {
        scratch_.seller_order_.resize(scratch_.offers_.size());
        std::iota(
            scratch_.seller_order_.begin(),
            scratch_.seller_order_.end(), std::size_t{0}
        );
        std::stable_sort(
            scratch_.seller_order_.begin(),
            scratch_.seller_order_.end(),
            [this](std::size_t left, std::size_t right) {
                const auto &lhs = scratch_.offers_[left];
                const auto &rhs = scratch_.offers_[right];
                if (lhs.price != rhs.price) {
                    return lhs.price < rhs.price;
                }
                if (lhs.strategic_reserve !=
                    rhs.strategic_reserve) {
                    return lhs.strategic_reserve;
                }
                return lhs.firm < rhs.firm;
            }
        );
        scratch_.buyer_order_.resize(scratch_.orders_.size());
        std::iota(
            scratch_.buyer_order_.begin(),
            scratch_.buyer_order_.end(), std::size_t{0}
        );
        const auto rationing = runtime_.energy_policy.rationing;
        if (rationing == EnergyRationing::proportional) {
            return clear_proportional(state, real);
        }
        if (rationing == EnergyRationing::market) {
            const auto status =
                rng.shuffle(std::span(scratch_.buyer_order_));
            if (!status.ok()) {
                return status;
            }
            return clear_buyer_sequence(
                state, real, scratch_.buyer_order_
            );
        }
        std::stable_sort(
            scratch_.buyer_order_.begin(),
            scratch_.buyer_order_.end(),
            [this, rationing](
                std::size_t left, std::size_t right
            ) {
                const auto &lhs = scratch_.orders_[left];
                const auto &rhs = scratch_.orders_[right];
                const bool lhs_household =
                    lhs.kind == EnergyBuyerKind::household;
                const bool rhs_household =
                    rhs.kind == EnergyBuyerKind::household;
                if (lhs_household != rhs_household) {
                    return rationing ==
                                   EnergyRationing::household_first
                               ? lhs_household
                               : !lhs_household;
                }
                if (lhs.kind != rhs.kind) {
                    return lhs.kind < rhs.kind;
                }
                return lhs.owner < rhs.owner;
            }
        );
        return clear_buyer_sequence(
            state, real, scratch_.buyer_order_
        );
    }

    [[nodiscard]] Status settle_energy_results(
        const core::RootState &state, M4TickScratch &real
    ) {
        double weighted_value = 0.0;
        double sold = 0.0;
        double private_sold = 0.0;
        for (const auto &offer : scratch_.offers_) {
            sold += offer.sold;
            weighted_value += offer.revenue;
            private_sold +=
                offer.strategic_reserve ? 0.0 : offer.sold;
        }
        for (auto &offer : scratch_.offers_) {
            if (offer.strategic_reserve) {
                const double average_cost =
                    scratch_.strategic_reserve_stock_ >
                            kEconomicEpsilon
                        ? scratch_.strategic_reserve_cost_ /
                              scratch_.strategic_reserve_stock_
                        : 0.0;
                scratch_.strategic_reserve_stock_ =
                    std::max(
                        0.0,
                        scratch_.strategic_reserve_stock_ -
                            offer.sold
                    );
                scratch_.strategic_reserve_cost_ =
                    std::max(
                        0.0,
                        scratch_.strategic_reserve_cost_ -
                            average_cost * offer.sold
                    );
                scratch_.working_metrics_.energy
                    .strategic_reserve_flow -= offer.sold;
                scratch_.working_metrics_.energy
                    .strategic_reserve_sale_revenue +=
                    offer.revenue;
                continue;
            }
            const auto index =
                static_cast<std::size_t>(offer.firm.value());
            auto &producer =
                scratch_.energy_producers_[index];
            const double average_cost =
                producer.inventory > kEconomicEpsilon
                    ? producer.inventory_cost /
                          producer.inventory
                    : 0.0;
            producer.inventory = std::max(
                0.0, producer.inventory - offer.sold
            );
            producer.inventory_cost = std::max(
                0.0,
                producer.inventory_cost -
                    average_cost * offer.sold
            );
            producer.sales = offer.sold;
            producer.revenue = offer.revenue;
            const auto dense = firm_index(real, offer.firm);
            auto &work = real.firm_work_[dense];
            work.sales = offer.sold;
            work.revenue = offer.revenue;
            work.closing_inventory = producer.inventory;
            work.profit = work.revenue - work.wage_bill;
            const double unfilled =
                std::max(
                    0.0,
                    scratch_.working_metrics_.energy
                            .requested_total -
                        sold
                );
            const double shortage_share =
                private_sold > kEconomicEpsilon
                    ? offer.sold / private_sold
                    : 1.0 /
                          static_cast<double>(
                              std::max<std::size_t>(
                                  1,
                                  real.energy_firm_indices_.size()
                              )
                          );
            producer.demand_expected = std::max(
                0.0,
                producer.demand_expected +
                    runtime_.energy_rules.demand_adjustment *
                        (
                            offer.sold +
                            shortage_share * unfilled -
                            producer.demand_expected
                        )
            );
            work.demand_expected =
                producer.demand_expected;
            const auto *firm =
                state.firms.get(offer.firm);
            const double target_inventory =
                runtime_.energy_rules
                    .producer_inventory_ratio *
                producer.demand_expected;
            const double imbalance =
                target_inventory > kEconomicEpsilon
                    ? (
                          target_inventory -
                          producer.inventory
                      ) /
                          target_inventory
                    : 0.0;
            if (runtime_.energy_policy
                    .state_owned_price_at_cost &&
                producer.state_owned) {
                work.markup = 0.0;
            } else {
                work.markup = std::clamp(
                    work.markup +
                        runtime_.energy_rules
                            .markup_adjustment *
                            imbalance,
                    runtime_.energy_rules.markup_minimum,
                    runtime_.energy_rules.markup_maximum
                );
            }
            const double unit_cost =
                work.posted_wage /
                std::max(
                    kEconomicEpsilon,
                    firm->productivity
                );
            work.posted_price = std::max(
                kEconomicEpsilon,
                (1.0 + work.markup) * unit_cost
            );
            if (runtime_.energy_policy.price_cap >
                    kEconomicEpsilon &&
                offer.posted_price >
                    runtime_.energy_policy.price_cap &&
                runtime_.energy_policy
                    .price_cap_compensation &&
                offer.sold > kEconomicEpsilon) {
                const double compensation =
                    (
                        offer.posted_price - offer.price
                    ) *
                    offer.sold;
                const auto status = stage_m4_transfer(
                    state, real,
                    state.institutions.treasury_account,
                    offer.account, compensation
                );
                if (!status.ok()) {
                    return status;
                }
                scratch_.working_metrics_.energy
                    .cap_compensation += compensation;
            }
        }

        double mean_deposit = 0.0;
        std::size_t household_count = 0;
        for (const auto &record :
             scratch_.household_energy_) {
            if (!record.active) {
                continue;
            }
            const auto *household =
                state.households.get(record.household);
            if (household != nullptr) {
                mean_deposit += projected_balance(
                    real, household->primary_account
                );
                ++household_count;
            }
        }
        mean_deposit /=
            static_cast<double>(
                std::max<std::size_t>(1, household_count)
            );
        for (const auto &order : scratch_.orders_) {
            if (order.kind == EnergyBuyerKind::industry) {
                auto &input = scratch_.energy_inputs_[
                    static_cast<std::size_t>(order.owner)
                ];
                input.bought = order.allocated;
                input.stock += order.allocated;
                input.stock_cost += order.spending;
                if (input.stock > kEconomicEpsilon) {
                    input.average_cost =
                        input.stock_cost / input.stock;
                }
                scratch_.working_metrics_.energy
                    .industry_units += order.allocated;
                scratch_.working_metrics_.energy
                    .industry_spending += order.spending;
            } else if (
                order.kind == EnergyBuyerKind::household
            ) {
                auto &record = scratch_.household_energy_[
                    static_cast<std::size_t>(order.owner)
                ];
                record.bought = order.allocated;
                record.spent = order.spending;
                record.coverage =
                    record.need > kEconomicEpsilon
                        ? order.allocated / record.need
                        : 1.0;
                const auto *household =
                    state.households.get(record.household);
                const bool targeted =
                    runtime_.energy_policy
                            .subsidy_deposit_threshold <=
                        0.0 ||
                    projected_balance(
                        real, household->primary_account
                    ) <
                        runtime_.energy_policy
                                .subsidy_deposit_threshold *
                            mean_deposit;
                if (targeted &&
                    runtime_.energy_policy
                            .household_subsidy_rate >
                        kEconomicEpsilon &&
                    order.spending > kEconomicEpsilon) {
                    record.subsidy =
                        runtime_.energy_policy
                            .household_subsidy_rate *
                        order.spending;
                    const auto status = stage_m4_transfer(
                        state, real,
                        state.institutions.treasury_account,
                        household->primary_account,
                        record.subsidy
                    );
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.working_metrics_.energy
                        .subsidy_paid += record.subsidy;
                }
                scratch_.working_metrics_.energy
                    .household_units += order.allocated;
                scratch_.working_metrics_.energy
                    .household_spending += order.spending;
            } else {
                scratch_.strategic_reserve_stock_ +=
                    order.allocated;
                scratch_.strategic_reserve_cost_ +=
                    order.spending;
                scratch_.working_metrics_.energy
                    .strategic_reserve_flow +=
                    order.allocated;
                scratch_.working_metrics_.energy
                    .strategic_reserve_purchase_paid +=
                    order.spending;
            }
        }

        for (auto &input : scratch_.energy_inputs_) {
            if (!input.active) {
                continue;
            }
            const auto index =
                static_cast<std::size_t>(input.firm.value());
            const double need =
                index < scratch_.industry_use_need_.size()
                    ? scratch_.industry_use_need_[index]
                    : 0.0;
            input.used = std::min(input.stock, need);
            input.unmet = std::max(0.0, need - input.used);
            if (input.stock > kEconomicEpsilon) {
                const double average =
                    input.stock_cost / input.stock;
                input.stock_cost = std::max(
                    0.0,
                    input.stock_cost - average * input.used
                );
            }
            input.stock =
                std::max(0.0, input.stock - input.used);
            if (input.stock > kEconomicEpsilon) {
                input.average_cost =
                    input.stock_cost / input.stock;
            }
            const auto dense = firm_index(real, input.firm);
            if (dense != kAbsentIndex &&
                dense < real.firm_work_.size()) {
                real.firm_work_[dense]
                    .production_input_factor =
                    need > kEconomicEpsilon
                        ? std::clamp(
                              input.used / need, 0.0, 1.0
                          )
                        : 1.0;
            }
        }
        scratch_.working_metrics_.energy.sold = sold;
        scratch_.working_metrics_.energy.unfilled =
            std::max(
                0.0,
                scratch_.working_metrics_.energy
                        .requested_total -
                    sold
            );
        if (sold > kEconomicEpsilon) {
            scratch_.energy_price_ =
                weighted_value / sold;
        }
        scratch_.working_metrics_.energy.transaction_price =
            scratch_.energy_price_;
        return Status::success();
    }

    void update_deprivation(
        const core::RootState &state, const M4TickScratch &real,
        const M7Runtime &population,
        const M7TickScratch &population_scratch, Tick tick
    ) {
        const auto &rules = runtime_.energy_rules;
        const auto day64 =
            static_cast<std::int64_t>(
                population.start_calendar_day
            ) +
            static_cast<std::int64_t>(tick.value()) + 1;
        const auto calendar_day =
            static_cast<std::int32_t>(day64);
        const auto year =
            static_cast<std::int32_t>(
                std::floor(
                    static_cast<double>(calendar_day) /
                    kDaysPerYear
                )
            );
        if (scratch_.deprivation_.current_year == 0) {
            scratch_.deprivation_.current_year = year;
        } else if (
            scratch_.deprivation_.current_year != year
        ) {
            ++scratch_.deprivation_.years_completed;
            scratch_.deprivation_.current_year = year;
        }

        double persons_total = 0.0;
        double fuel_poor = 0.0;
        double below_100 = 0.0;
        double below_60 = 0.0;
        double below_30 = 0.0;
        double destitute = 0.0;
        double acute = 0.0;
        double chronic = 0.0;
        double maximum_spell = 0.0;
        for (std::size_t dense = 0;
             dense < real.household_ids_.size(); ++dense) {
            const auto household_id =
                real.household_ids_[dense];
            const auto id_index =
                static_cast<std::size_t>(
                    household_id.value()
                );
            auto &energy =
                scratch_.household_energy_[id_index];
            const double person_count =
                static_cast<double>(
                    population_scratch.membership_
                        .members(household_id)
                        .size()
                );
            persons_total += person_count;
            if (energy.coverage <
                rules.fuel_poverty_threshold) {
                fuel_poor += person_count;
            }
            const double need_units = household_need_units(
                population_scratch, household_id,
                calendar_day
            );
            const double consumption =
                real.household_work_[dense].spent +
                energy.spent;
            scratch_.household_consumption_[id_index] =
                consumption;
            if (!rules.deprivation ||
                need_units <= kEconomicEpsilon) {
                continue;
            }
            if (!scratch_.deprivation_.active) {
                scratch_.deprivation_.per_unit_sum +=
                    consumption / need_units;
                scratch_.deprivation_.household_days += 1.0;
                if (real_runtime_price(real) >
                    kEconomicEpsilon) {
                    scratch_.deprivation_.price_sum +=
                        real_runtime_price(real);
                    scratch_.deprivation_.price_days += 1.0;
                }
                continue;
            }
            const double price_ratio =
                scratch_.deprivation_.price_anchor >
                        kEconomicEpsilon
                    ? real_runtime_price(real) /
                          scratch_.deprivation_.price_anchor
                    : 1.0;
            const double basket =
                scratch_.deprivation_.basket_cost_anchor *
                need_units * price_ratio;
            if (basket <= kEconomicEpsilon) {
                continue;
            }
            const double coverage =
                consumption / basket;
            const auto *household =
                state.households.get(household_id);
            const double liquid = projected_balance(
                real, household->primary_account
            );
            const bool deposit_poor = liquid < basket;
            auto &spells = energy.deprivation_spells;
            spells[0] =
                coverage < 1.0 ? spells[0] + 1U : 0U;
            spells[1] =
                coverage < 0.6 ? spells[1] + 1U : 0U;
            spells[2] =
                coverage < 0.3 && deposit_poor
                    ? spells[2] + 1U
                    : 0U;
            maximum_spell = std::max(
                maximum_spell,
                static_cast<double>(spells[0])
            );
            below_100 +=
                coverage < 1.0 ? person_count : 0.0;
            below_60 +=
                coverage < 0.6 ? person_count : 0.0;
            below_30 +=
                coverage < 0.3 ? person_count : 0.0;
            destitute +=
                coverage < 0.3 && deposit_poor
                    ? person_count
                    : 0.0;
            if (spells[2] >= rules.deprivation_acute_days) {
                acute += person_count;
                scratch_.deprivation_.boundary_breached = true;
            }
            if (spells[1] >=
                    rules.deprivation_chronic_days &&
                deposit_poor) {
                chronic += person_count;
                scratch_.deprivation_.boundary_breached = true;
            }
        }
        if (!scratch_.deprivation_.active &&
            scratch_.deprivation_.years_completed >=
                rules.deprivation_burnin_years &&
            scratch_.deprivation_.household_days >
                kEconomicEpsilon) {
            const double mean =
                scratch_.deprivation_.per_unit_sum /
                scratch_.deprivation_.household_days;
            if (mean > kEconomicEpsilon) {
                scratch_.deprivation_.basket_cost_anchor =
                    rules.deprivation_subsistence_share *
                    mean;
                scratch_.deprivation_.price_anchor =
                    scratch_.deprivation_.price_days >
                            kEconomicEpsilon
                        ? scratch_.deprivation_.price_sum /
                              scratch_.deprivation_.price_days
                        : 1.0;
                scratch_.deprivation_.active = true;
            }
        }
        const double denominator =
            std::max(1.0, persons_total);
        auto &metrics = scratch_.working_metrics_.energy;
        metrics.fuel_poverty_share =
            fuel_poor / denominator;
        metrics.fuel_poverty_mortality_multiplier =
            scratch_.deprivation_.years_completed >
                        rules.deprivation_burnin_years &&
                    rules.fuel_poverty_mortality_gamma >
                        0.0
                ? std::clamp(
                      1.0 +
                          rules.fuel_poverty_mortality_gamma *
                              metrics.fuel_poverty_share,
                      1.0,
                      rules.fuel_poverty_mortality_cap
                  )
                : 1.0;
        metrics.deprivation_below_100_share =
            below_100 / denominator;
        metrics.deprivation_below_60_share =
            below_60 / denominator;
        metrics.deprivation_below_30_share =
            below_30 / denominator;
        metrics.deprivation_destitute_share =
            destitute / denominator;
        metrics.deprivation_acute_stock = acute;
        metrics.deprivation_chronic_stock = chronic;
        metrics.deprivation_max_spell_days = maximum_spell;
        metrics.deprivation_boundary =
            scratch_.deprivation_.boundary_breached;
    }

    [[nodiscard]] static double real_runtime_price(
        const M4TickScratch &real
    ) noexcept {
        double quantity = 0.0;
        double value = 0.0;
        for (const auto index :
             real.consumption_firm_indices_) {
            const auto &work = real.firm_work_[index];
            quantity += work.sales;
            value += work.sales * work.posted_price;
        }
        return quantity > kEconomicEpsilon
                   ? value / quantity
                   : 1.0;
    }

    M8Runtime &runtime_;
    M8TickScratch &scratch_;
    const M8AdvanceOptions &options_;
    EnergyExogenousInput input_{};
};

} // namespace

void M8TickScratch::reserve(
    const core::RootState &state, const M8Runtime &runtime
) {
    energy_producers_.reserve(
        std::max(
            runtime.energy_producers.size(),
            static_cast<std::size_t>(
                state.firms.allocator_state().next_id
            )
        )
    );
    energy_inputs_.reserve(
        std::max(
            runtime.energy_inputs.size(),
            static_cast<std::size_t>(
                state.firms.allocator_state().next_id
            )
        )
    );
    household_energy_.reserve(
        std::max(
            runtime.household_energy.size(),
            static_cast<std::size_t>(
                state.households.allocator_state().next_id
            )
        )
    );
    orders_.reserve(
        state.households.alive_count() +
        state.firms.alive_count() + 1U
    );
    offers_.reserve(
        state.firms.alive_count() + 1U
    );
    buyer_order_.reserve(orders_.capacity());
    seller_order_.reserve(offers_.capacity());
    industry_use_need_.resize(
        static_cast<std::size_t>(
            state.firms.allocator_state().next_id
        )
    );
    household_consumption_.resize(
        static_cast<std::size_t>(
            state.households.allocator_state().next_id
        )
    );
    opening_balances_.reserve(state.postings.size() + 1U);
}

std::uint64_t M8TickScratch::capacity_signature() const noexcept {
    std::uint64_t signature = 1469598103934665603ULL;
    const std::array capacities{
        energy_producers_.capacity(),
        energy_inputs_.capacity(),
        household_energy_.capacity(),
        orders_.capacity(),
        offers_.capacity(),
        buyer_order_.capacity(),
        seller_order_.capacity(),
        industry_use_need_.capacity(),
        household_consumption_.capacity(),
        opening_balances_.capacity(),
    };
    for (const auto capacity : capacities) {
        signature ^= static_cast<std::uint64_t>(capacity);
        signature *= 1099511628211ULL;
    }
    return signature;
}

Status validate_energy_policy(
    const EnergyPolicyState &policy
) noexcept {
    const std::array values{
        policy.excise_rate,
        policy.household_subsidy_rate,
        policy.subsidy_deposit_threshold,
        policy.price_cap,
        policy.strategic_reserve_target,
        policy.strategic_reserve_flow_cap,
    };
    if (!all_finite(values) || policy.excise_rate < 0.0 ||
        policy.household_subsidy_rate < 0.0 ||
        policy.household_subsidy_rate > 1.0 ||
        policy.subsidy_deposit_threshold < 0.0 ||
        policy.price_cap < 0.0 ||
        policy.strategic_reserve_target < 0.0 ||
        policy.strategic_reserve_flow_cap < 0.0 ||
        !valid_rationing(policy.rationing)) {
        return Status(
            ErrorCode::invalid_argument,
            "M8 energy policy is invalid"
        );
    }
    return Status::success();
}

Status validate_energy_rules(const EnergyRules &rules) noexcept {
    const std::array values{
        rules.initial_producer_cash,
        rules.initial_price,
        rules.initial_wage,
        rules.initial_markup,
        rules.producer_productivity,
        rules.capacity_per_capital,
        rules.initial_utilization,
        rules.producer_inventory_ratio,
        rules.demand_adjustment,
        rules.markup_adjustment,
        rules.markup_minimum,
        rules.markup_maximum,
        rules.household_need,
        rules.downstream_intensity,
        rules.downstream_coverage_days,
        rules.downstream_gap_close,
        rules.hoarding_beta,
        rules.slow_price_days,
        rules.deprivation_subsistence_share,
        rules.fuel_poverty_threshold,
        rules.fuel_poverty_mortality_gamma,
        rules.fuel_poverty_mortality_cap,
    };
    if (!all_finite(values) ||
        (rules.enabled && rules.producer_count == 0) ||
        rules.producer_count > 10'000'000 ||
        rules.initial_producer_cash < 0.0 ||
        rules.initial_price <= 0.0 ||
        rules.initial_wage <= 0.0 ||
        rules.initial_markup < 0.0 ||
        rules.producer_productivity <= 0.0 ||
        rules.capacity_per_capital <= 0.0 ||
        rules.initial_utilization <= 0.0 ||
        rules.initial_utilization > 1.0 ||
        rules.producer_inventory_ratio < 0.0 ||
        rules.demand_adjustment < 0.0 ||
        rules.demand_adjustment > 1.0 ||
        rules.markup_adjustment < 0.0 ||
        rules.markup_minimum < 0.0 ||
        rules.markup_maximum < rules.markup_minimum ||
        rules.household_need < 0.0 ||
        rules.downstream_intensity < 0.0 ||
        rules.downstream_coverage_days < 0.0 ||
        rules.downstream_gap_close < 0.0 ||
        rules.downstream_gap_close > 1.0 ||
        rules.hoarding_beta < 0.0 ||
        rules.slow_price_days <= 0.0 ||
        rules.deprivation_subsistence_share <= 0.0 ||
        rules.deprivation_subsistence_share > 1.0 ||
        rules.deprivation_acute_days == 0 ||
        rules.deprivation_chronic_days == 0 ||
        rules.fuel_poverty_threshold < 0.0 ||
        rules.fuel_poverty_threshold > 1.0 ||
        rules.fuel_poverty_mortality_gamma < 0.0 ||
        rules.fuel_poverty_mortality_cap < 1.0) {
        return Status(
            ErrorCode::invalid_argument,
            "M8 energy rules are invalid"
        );
    }
    return Status::success();
}

Status validate_energy_input(
    const EnergyExogenousInput &input
) noexcept {
    const std::array values{
        input.capacity_multiplier,
        input.labor_availability_multiplier,
        input.supply_multiplier,
        input.household_demand_multiplier,
        input.industry_demand_multiplier,
        input.reference_price_multiplier,
    };
    if (!all_finite(values) ||
        std::any_of(
            values.begin(), values.end(),
            [](double value) { return value < 0.0; }
        )) {
        return Status(
            ErrorCode::invalid_argument,
            "M8 energy exogenous input is invalid"
        );
    }
    return Status::success();
}

Status validate_m8_spec(const M8SimulationSpec &spec) noexcept {
    auto status = validate_m7_spec(spec.domestic_economy);
    if (!status.ok()) {
        return status;
    }
    status = validate_energy_policy(spec.energy_policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_energy_rules(spec.energy_rules);
    if (!status.ok()) {
        return status;
    }
    status = validate_energy_input(spec.energy_input);
    if (!status.ok()) {
        return status;
    }
    if (spec.energy_rules.enabled &&
        !spec.domestic_economy.rules.persistent_labor) {
        return Status(
            ErrorCode::unsupported,
            "M8 energy requires persistent native labor"
        );
    }
    return Status::success();
}

Status validate_m8_state(
    const core::RootState &state,
    const M4Runtime &real_economy_runtime,
    const M5Runtime &monetary_runtime,
    const M6Runtime &financial_runtime,
    const M7Runtime &population_runtime,
    const M8Runtime &runtime, Tick tick
) noexcept {
    auto status = validate_energy_policy(runtime.energy_policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_energy_rules(runtime.energy_rules);
    if (!status.ok()) {
        return status;
    }
    status = validate_energy_input(runtime.energy_input);
    if (!status.ok()) {
        return status;
    }
    const std::array values{
        runtime.strategic_reserve_stock,
        runtime.strategic_reserve_cost,
        runtime.energy_price,
        runtime.slow_energy_price,
    };
    if (!all_finite(values) ||
        runtime.strategic_reserve_stock < 0.0 ||
        runtime.strategic_reserve_cost < 0.0 ||
        runtime.energy_price <= 0.0 ||
        runtime.slow_energy_price <= 0.0) {
        return Status(
            ErrorCode::invariant_violation,
            "M8 persistent energy state is invalid"
        );
    }
    status = validate_energy_projection(state, runtime, false);
    if (!status.ok()) {
        return status;
    }
    return validate_m7_state(
        state, real_economy_runtime, monetary_runtime,
        financial_runtime, population_runtime, tick
    );
}

Result<M8Initialization>
build_m8_genesis(const M8SimulationSpec &spec) {
    const auto validation = validate_m8_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    auto genesis = build_m7_genesis(spec.domestic_economy);
    if (!genesis.ok()) {
        return genesis.status();
    }
    auto base = std::move(*genesis.get_if());
    M8Runtime runtime;
    runtime.energy_policy = spec.energy_policy;
    runtime.energy_rules = spec.energy_rules;
    runtime.energy_input = spec.energy_input;
    runtime.energy_price = spec.energy_rules.initial_price;
    runtime.slow_energy_price =
        spec.energy_rules.initial_price;
    ensure_runtime_indexes(base.root, runtime);
    if (spec.energy_rules.enabled) {
        const auto settlement_node =
            genesis_settlement_node(base.root);
        if (!settlement_node.valid()) {
            return Status(
                ErrorCode::invariant_violation,
                "M8 genesis has no settlement node"
            );
        }
        double downstream_demand = 0.0;
        base.root.firms.for_each_alive(
            [&downstream_demand, &spec](
                FirmId, const core::FirmComponent &firm
            ) {
                if (firm.sector ==
                        core::FirmSector::consumption ||
                    firm.sector ==
                        core::FirmSector::capital) {
                    downstream_demand +=
                        spec.energy_rules
                            .downstream_intensity *
                        firm.demand_expected;
                }
            }
        );
        const double household_demand =
            spec.energy_rules.household_energy
                ? spec.energy_rules.household_need *
                      static_cast<double>(
                          base.root.households.alive_count()
                      )
                : 0.0;
        const double total_demand =
            downstream_demand + household_demand;
        const double per_producer =
            total_demand /
            static_cast<double>(
                spec.energy_rules.producer_count
            );
        const double capital =
            per_producer /
            (
                spec.energy_rules.capacity_per_capital *
                spec.energy_rules.initial_utilization
            );
        const double inventory =
            spec.energy_rules.producer_inventory_ratio *
            per_producer;
        for (std::uint64_t index = 0;
             index < spec.energy_rules.producer_count;
             ++index) {
            EnergyProducerComponent producer;
            const auto status = create_energy_firm(
                base.root, base.financial_runtime,
                spec.energy_rules, per_producer, capital,
                inventory,
                spec.energy_rules
                        .state_owned_first_producer &&
                    index == 0,
                settlement_node, producer
            );
            if (!status.ok()) {
                return status;
            }
            if (runtime.energy_producers.size() <=
                producer.firm.value()) {
                runtime.energy_producers.resize(
                    static_cast<std::size_t>(
                        producer.firm.value() + 1U
                    )
                );
                runtime.energy_inputs.resize(
                    runtime.energy_producers.size()
                );
            }
            runtime.energy_producers[
                static_cast<std::size_t>(
                    producer.firm.value()
                )
            ] = producer;
        }
        base.root.firms.for_each_alive(
            [&runtime, &spec](
                FirmId id, const core::FirmComponent &firm
            ) {
                if (firm.sector !=
                        core::FirmSector::consumption &&
                    firm.sector !=
                        core::FirmSector::capital) {
                    return;
                }
                const auto index =
                    static_cast<std::size_t>(id.value());
                auto &input = runtime.energy_inputs[index];
                input.firm = id;
                input.active = true;
                input.intensity =
                    spec.energy_rules.downstream_intensity;
                input.coverage_days =
                    spec.energy_rules
                        .downstream_coverage_days;
                input.stock =
                    input.coverage_days * input.intensity *
                    firm.demand_expected;
                input.stock_cost =
                    input.stock *
                    spec.energy_rules.initial_price;
                input.average_cost =
                    spec.energy_rules.initial_price;
            }
        );
        ensure_runtime_indexes(base.root, runtime);
        base.root.households.for_each_alive(
            [&runtime](HouseholdId id,
                       const core::HouseholdComponent &) {
                auto &record =
                    runtime.household_energy[
                        static_cast<std::size_t>(
                            id.value()
                        )
                    ];
                record.household = id;
                record.active = true;
            }
        );
        if (base.runtime.firm_target_ema.size() <
            base.root.firms.allocator_state().next_id) {
            base.runtime.firm_target_ema.resize(
                static_cast<std::size_t>(
                    base.root.firms.allocator_state().next_id
                ),
                0.0
            );
        }
    }
    runtime.last_metrics.energy.transaction_price =
        runtime.energy_price;
    runtime.last_metrics.energy
        .fuel_poverty_mortality_multiplier = 1.0;
    const auto state_status = validate_m8_state(
        base.root, base.real_economy_runtime,
        base.monetary_runtime, base.financial_runtime,
        base.runtime, runtime, Tick(0)
    );
    if (!state_status.ok()) {
        return state_status;
    }
    return M8Initialization{
        std::move(base.root),
        std::move(base.real_economy_runtime),
        std::move(base.monetary_runtime),
        std::move(base.financial_runtime),
        std::move(base.runtime),
        std::move(runtime),
    };
}

Result<M8AdvanceResult>
advance_m8_ticks(
    core::RootState &state,
    M4Runtime &real_economy_runtime,
    M4TickScratch &real_economy_scratch,
    M5Runtime &monetary_runtime,
    M5TickScratch &monetary_scratch,
    M6Runtime &financial_runtime,
    M6TickScratch &financial_scratch,
    M7Runtime &population_runtime,
    M7TickScratch &population_scratch,
    M8Runtime &runtime, M8TickScratch &scratch, Tick &tick,
    std::uint64_t count, const M8AdvanceOptions &options
) {
    if (!valid_fault_point(options.fault_point)) {
        return Status(
            ErrorCode::invalid_argument,
            "M8 fault point is invalid"
        );
    }
    if (count == 0) {
        return M8AdvanceResult{
            tick,
            tick,
            0,
            runtime.last_metrics,
            scratch.capacity_signature(),
            0,
            0,
        };
    }
    const auto state_status = validate_m8_state(
        state, real_economy_runtime, monetary_runtime,
        financial_runtime, population_runtime, runtime, tick
    );
    if (!state_status.ok()) {
        return Status(
            ErrorCode::invariant_violation,
            "M8 cannot advance an invalid state"
        );
    }
    M8Extension extension(runtime, scratch, options);
    auto result = advance_m7_ticks_extended(
        state, real_economy_runtime, real_economy_scratch,
        monetary_runtime, monetary_scratch, financial_runtime,
        financial_scratch, population_runtime,
        population_scratch, tick, count, extension,
        options.base
    );
    if (!result.ok()) {
        return result.status();
    }
    const auto &base = *result.get_if();
    return M8AdvanceResult{
        base.first_tick,
        base.next_tick,
        base.advanced_ticks,
        runtime.last_metrics,
        scratch.capacity_signature(),
        base.transfer_count,
        base.trade_count,
    };
}

} // namespace macro_sim::simulation
