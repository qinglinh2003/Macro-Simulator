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

struct TechnologyProjection final {
    std::array<double, 3> indices{1.0, 1.0, 1.0};
    std::array<double, 3> growth{0.0, 0.0, 0.0};
    std::array<double, 3> learning_origin{0.0, 0.0, 0.0};
    std::array<double, 3> learning_base{0.0, 0.0, 0.0};
    std::array<bool, 3> learning_initialized{false, false, false};
    PhiloxCounter rng_counter{};
};

[[nodiscard]] Result<TechnologyProjection>
project_technology(const M4Runtime &runtime) noexcept {
    TechnologyProjection next;
    next.indices = {
        runtime.technology_index,
        runtime.technology_index_capital,
        runtime.technology_index_energy,
    };
    next.learning_origin = runtime.tfp_learning_origin;
    next.learning_base = runtime.tfp_learning_base;
    next.learning_initialized = runtime.tfp_learning_initialized;
    PhiloxRng rng(runtime.technology_rng_key, runtime.technology_rng_counter);

    if (runtime.rules.tfp_law == M4TfpLaw::learning) {
        if (runtime.rules.tfp_learning_theta != 0.0) {
            for (std::size_t sector = 0; sector < next.indices.size(); ++sector) {
                const double previous = next.indices[sector];
                const double cumulative =
                    std::max(0.0, runtime.cumulative_sector_output[sector]);
                if (!next.learning_initialized[sector]) {
                    if (cumulative <= 0.0) {
                        continue;
                    }
                    next.learning_initialized[sector] = true;
                    next.learning_origin[sector] = cumulative;
                    next.learning_base[sector] =
                        std::max(cumulative * kDaysPerYear, 1.0e-9);
                    next.indices[sector] = 1.0;
                } else {
                    const double experience =
                        std::max(0.0, cumulative - next.learning_origin[sector]);
                    const double ratio = 1.0 + experience / next.learning_base[sector];
                    next.indices[sector] =
                        std::pow(ratio, runtime.rules.tfp_learning_theta);
                }
                next.growth[sector] = next.indices[sector] / previous - 1.0;
            }
        }
    } else {
        const std::array overrides{
            runtime.rules.annual_tfp_growth_consumption,
            runtime.rules.annual_tfp_growth_capital,
            runtime.rules.annual_tfp_growth_energy,
        };
        for (std::size_t sector = 0; sector < next.indices.size(); ++sector) {
            const double annual = overrides[sector] == 0.0
                                      ? runtime.rules.annual_tfp_growth
                                      : overrides[sector];
            double daily = annual / kDaysPerYear;
            if (runtime.rules.annual_tfp_volatility > 0.0) {
                daily += runtime.rules.annual_tfp_volatility *
                         rng.standard_normal() / kDaysPerYear;
            }
            const double factor = 1.0 + daily;
            if (!std::isfinite(factor) || factor <= 0.0) {
                return Status(ErrorCode::out_of_range,
                              "M4 TFP innovation produced a non-positive index");
            }
            next.indices[sector] *= factor;
            next.growth[sector] = daily;
        }
    }
    next.rng_counter = rng.counter();
    return next;
}
constexpr std::uint64_t kConsumptionStockoutVisitStream = 0x4353544f434b4f55ULL;
constexpr std::size_t kAbsentFirmIndex = std::numeric_limits<std::size_t>::max();
constexpr std::uint64_t kV1Capabilities =
    capability_bit(M4Capability::physical_capital) |
    capability_bit(M4Capability::government);
constexpr std::uint64_t kUnsupportedCapabilities =
    capability_bit(M4Capability::credit) |
    capability_bit(M4Capability::commercial_banks) |
    capability_bit(M4Capability::central_bank) |
    capability_bit(M4Capability::securities) | capability_bit(M4Capability::equity) |
    capability_bit(M4Capability::demographics) |
    capability_bit(M4Capability::persistent_labor) |
    capability_bit(M4Capability::energy) | capability_bit(M4Capability::housing) |
    capability_bit(M4Capability::open_economy) |
    capability_bit(M4Capability::stateful_shocks) |
    capability_bit(M4Capability::controllers) |
    capability_bit(M4Capability::reinforcement_learning);

[[nodiscard]] bool all_finite(std::span<const double> values) noexcept {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return std::isfinite(value); });
}

[[nodiscard]] std::uint64_t splitmix64(std::uint64_t value) noexcept {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

[[nodiscard]] std::size_t stateless_index(std::uint64_t seed, std::uint64_t identity,
                                          Tick tick, std::uint64_t stream,
                                          std::size_t size) noexcept {
    const auto bits =
        splitmix64(seed ^ splitmix64(identity) ^
                   splitmix64(static_cast<std::uint64_t>(tick.value())) ^ stream);
    return static_cast<std::size_t>(bits % static_cast<std::uint64_t>(size));
}

[[nodiscard]] algorithms::ProductionTechnology
technology_for(core::FirmTechnology technology) noexcept {
    return technology == core::FirmTechnology::linear
               ? algorithms::ProductionTechnology::linear
               : algorithms::ProductionTechnology::cobb_douglas;
}

[[nodiscard]] constexpr bool is_base_firm_sector(core::FirmSector sector) noexcept {
    return sector == core::FirmSector::consumption ||
           sector == core::FirmSector::capital;
}

[[nodiscard]] constexpr bool settles_current_income(core::FirmSector sector) noexcept {
    return is_base_firm_sector(sector) || sector == core::FirmSector::energy;
}

[[nodiscard]] double sum_balances(const M4TickScratch &scratch) noexcept {
    return core::neumaier_sum(scratch.balances_);
}

[[nodiscard]] double fiscal_output_reference(const M4Runtime &runtime,
                                             const M4TickScratch &scratch) noexcept {
    const double genesis_reference = runtime.rules.initial_price *
                                     static_cast<double>(scratch.household_ids_.size());
    if (runtime.previous_nominal_output <= algorithms::kEconomicEpsilon) {
        return genesis_reference;
    }
    // Fiscal demand is specified against potential output, not the already
    // depressed realized flow.  With capital fixed over a day, Cobb-Douglas
    // output scales with labor to the power (1 - alpha), so grossing realized
    // output up by the observed employment rate gives a transparent
    // full-employment estimate.  The 10% floor keeps crisis observations
    // finite without muting ordinary output-gap stabilization.
    const double employment_rate =
        std::clamp(1.0 - runtime.last_metrics.unemployment_rate, 0.10, 1.0);
    const double labor_elasticity =
        std::clamp(1.0 - runtime.rules.capital_share, 0.10, 1.0);
    const double potential =
        runtime.previous_nominal_output / std::pow(employment_rate, labor_elasticity);
    return std::max(genesis_reference, potential);
}

[[nodiscard]] Status transfer(const core::RootState &state, M4TickScratch &scratch,
                              AccountId source, AccountId destination, double amount,
                              std::string_view insufficient_context) noexcept {
    static_cast<void>(state);
    if (!std::isfinite(amount) || amount < -algorithms::kEconomicEpsilon) {
        return Status(ErrorCode::invalid_argument,
                      "M4 transfer amount must be finite and nonnegative");
    }
    if (amount <= algorithms::kEconomicEpsilon || source == destination) {
        return Status::success();
    }
    const auto source_index = static_cast<std::size_t>(source.value());
    const auto destination_index = static_cast<std::size_t>(destination.value());
    if (source_index >= scratch.balances_.size() ||
        destination_index >= scratch.balances_.size() ||
        source_index >= scratch.account_flags_.size() ||
        destination_index >= scratch.account_flags_.size()) {
        return Status(ErrorCode::internal_error, "M4 account projection is stale");
    }
    const auto source_flags = scratch.account_flags_[source_index];
    const auto destination_flags = scratch.account_flags_[destination_index];
    if ((source_flags & M4TickScratch::kAccountOpen) == 0U ||
        (destination_flags & M4TickScratch::kAccountOpen) == 0U) {
        return Status(ErrorCode::not_found, "M4 transfer account is absent");
    }
    if ((source_flags & M4TickScratch::kAccountAllowsNegative) == 0U &&
        scratch.balances_[source_index] + kTolerance < amount) {
        return Status(ErrorCode::insufficient_funds, insufficient_context);
    }
    scratch.balances_[source_index] -= amount;
    scratch.balances_[destination_index] += amount;
    const auto source_node = scratch.account_nodes_[source_index];
    const auto destination_node = scratch.account_nodes_[destination_index];
    if (source_node != destination_node) {
        const auto source_reserve = static_cast<std::size_t>(source_node.value());
        const auto destination_reserve =
            static_cast<std::size_t>(destination_node.value());
        if (source_reserve >= scratch.reserve_balances_.size() ||
            destination_reserve >= scratch.reserve_balances_.size()) {
            return Status(ErrorCode::internal_error, "M4 reserve projection is stale");
        }
        scratch.reserve_balances_[source_reserve] -= amount;
        scratch.reserve_balances_[destination_reserve] += amount;
        scratch.reserve_minimum_[source_reserve] =
            std::min(scratch.reserve_minimum_[source_reserve],
                     scratch.reserve_balances_[source_reserve]);
    }
    ++scratch.transfer_count_;
    return Status::success();
}

[[nodiscard]] Status check_fault(const M4AdvanceOptions &options,
                                 M4Phase phase) noexcept {
    if (options.fault_before_phase.has_value() &&
        *options.fault_before_phase == phase) {
        return Status(ErrorCode::internal_error, "injected M4 phase fault");
    }
    return Status::success();
}

[[nodiscard]] Status
validate_advance_options(const core::RootState &state,
                         const M4AdvanceOptions &options) noexcept {
    if (!all_finite(options.productivity_multipliers) ||
        !all_finite(options.labor_availability_multipliers) ||
        !std::isfinite(options.household_demand_multiplier) ||
        options.household_demand_multiplier < 0.0 ||
        std::any_of(
            options.productivity_multipliers.begin(),
            options.productivity_multipliers.end(),
            [](double value) { return value < 0.0; }) ||
        std::any_of(
            options.labor_availability_multipliers.begin(),
            options.labor_availability_multipliers.end(),
            [](double value) { return value < 0.0; })) {
        return Status(ErrorCode::invalid_argument,
                      "M4 exogenous multipliers must be finite and nonnegative");
    }
    if (!options.external_goods_offer.has_value()) {
        return Status::success();
    }
    const auto &offer = *options.external_goods_offer;
    const auto *seller = state.postings.get(offer.seller);
    if (offer.offer_id == 0U || seller == nullptr || !seller->open ||
        !std::isfinite(offer.stock) || offer.stock < 0.0 ||
        !std::isfinite(offer.price) || offer.price <= 0.0 ||
        state.firms.get(FirmId(offer.offer_id)) != nullptr) {
        return Status(ErrorCode::invalid_argument, "invalid M4 external goods offer");
    }
    return Status::success();
}

[[nodiscard]] std::size_t firm_projection_index(const M4TickScratch &scratch,
                                                std::uint64_t firm) noexcept {
    const auto id = static_cast<std::size_t>(firm);
    return id < scratch.firm_dense_index_.size() ? scratch.firm_dense_index_[id]
                                                 : kAbsentFirmIndex;
}

[[nodiscard]] std::size_t household_projection_index(const M4TickScratch &scratch,
                                                     std::uint64_t household) noexcept {
    const auto id = static_cast<std::size_t>(household);
    return id < scratch.household_dense_index_.size()
               ? scratch.household_dense_index_[id]
               : kAbsentFirmIndex;
}

void record_consumption_purchase(M4TickScratch &scratch, std::size_t household_index,
                                 std::size_t firm_index, double value) noexcept {
    if (household_index >= scratch.household_work_.size() || value <= 0.0) {
        return;
    }
    auto &work = scratch.household_work_[household_index];
    const bool luxury = firm_index < scratch.firm_consumption_strata_.size() &&
                        scratch.firm_consumption_strata_[firm_index] != 0U;
    if (luxury) {
        work.luxury_spent += value;
    } else {
        work.necessity_spent += value;
    }
}

[[nodiscard]] double maximum_consumption_tax_rate(const M4Runtime &runtime) noexcept {
    return std::max({
        0.0,
        runtime.rules.consumption_tax_rate,
        runtime.rules.necessity_consumption_tax_rate.value_or(
            runtime.rules.consumption_tax_rate),
        runtime.rules.luxury_consumption_tax_rate.value_or(
            runtime.rules.consumption_tax_rate),
    });
}

void capture_phase(const core::RootState &state, M4TickScratch &scratch,
                   const M4AdvanceOptions &options, M4Phase phase) {
    if (!options.capture_phase_trace) {
        return;
    }
    double goods = 0.0;
    double capital = 0.0;
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        if (firm == nullptr || !is_base_firm_sector(firm->sector)) {
            continue;
        }
        goods += scratch.firm_work_[index].closing_inventory;
        capital += scratch.firm_work_[index].closing_capital;
    }
    scratch.phase_trace_.push_back({
        phase,
        sum_balances(scratch),
        goods,
        capital,
        scratch.transfer_count_,
        scratch.trade_count_,
    });
}

[[nodiscard]] Status validate_working_state(const core::RootState &state,
                                            const M4TickScratch &scratch,
                                            bool endogenous_money) noexcept {
    if (!all_finite(scratch.balances_)) {
        return Status(ErrorCode::invariant_violation,
                      "M4 account balance is nonfinite");
    }
    if (!all_finite(scratch.reserve_balances_) ||
        !all_finite(scratch.reserve_minimum_)) {
        return Status(ErrorCode::invariant_violation,
                      "M4 reserve projection is not finite");
    }
    for (const auto &record : state.postings.records()) {
        const auto index = static_cast<std::size_t>(record.id.value());
        if (index >= scratch.balances_.size()) {
            return Status(ErrorCode::invariant_violation,
                          "M4 account projection is incomplete");
        }
        if (!record.allow_negative && scratch.balances_[index] < -kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "M4 account balance is negative");
        }
    }
    const double drift = sum_balances(scratch) - state.genesis_money.value();
    const double conservation_tolerance =
        std::max(state.accounting_tolerance,
                 1.0e-10 * std::max(1.0, std::abs(state.genesis_money.value())));
    if (!endogenous_money && std::abs(drift) > conservation_tolerance) {
        return Status(ErrorCode::invariant_violation, "M4 money conservation failed");
    }
    for (const auto &household : scratch.household_work_) {
        const std::array values{
            household.income_expected,    household.income_realized,
            household.consumption_budget, household.spent,
            household.necessity_spent,    household.luxury_spent,
            household.labor_sold,         household.labor_capacity,
        };
        if (!all_finite(values)) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household state contains a nonfinite value");
        }
        if (household.income_expected < 0.0) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household expected income is negative");
        }
        if (household.income_realized < -kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household realized income is negative");
        }
        if (household.consumption_budget < 0.0 || household.spent < 0.0 ||
            household.necessity_spent < 0.0 || household.luxury_spent < 0.0) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household consumption state is negative");
        }
        if (household.necessity_spent + household.luxury_spent >
            household.spent + kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household spending categories exceed spending");
        }
        if (household.labor_sold < -kTolerance ||
            household.labor_capacity < -kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household labor projection is negative");
        }
        if (household.labor_sold > household.labor_capacity + kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household sold labor exceeds capacity");
        }
    }
    for (const auto &firm : scratch.firm_work_) {
        const std::array values{
            firm.target_inventory,
            firm.production_target,
            firm.labor_demand_notional,
            firm.labor_demand_effective,
            firm.hired,
            firm.production_input_factor,
            firm.produced,
            firm.sales,
            firm.revenue,
            firm.wage_bill,
            firm.production_input_cost,
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
        if (!all_finite(values) || firm.closing_inventory < -kTolerance ||
            firm.closing_capital < -kTolerance || firm.posted_price <= 0.0 ||
            firm.posted_wage <= 0.0 || firm.hired < -kTolerance ||
            firm.production_input_factor < -kTolerance ||
            firm.production_input_factor > 1.0 + kTolerance) {
            return Status(ErrorCode::invariant_violation, "M4 firm state is invalid");
        }
    }
    return Status::success();
}

void commit_working_state(core::RootState &state, M4Runtime &runtime,
                          M4TickScratch &scratch, Tick &tick, const M4Metrics &metrics,
                          PhiloxCounter rng_counter,
                          const TechnologyProjection &technology,
                          double public_capital) noexcept {
    for (auto &record : state.postings.records()) {
        record.balance =
            Money(scratch.balances_[static_cast<std::size_t>(record.id.value())]);
    }
    for (auto &record : state.reserves.records()) {
        record.balance = Money(
            scratch.reserve_balances_[static_cast<std::size_t>(record.node.value())]);
    }
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        auto *household = state.households.get(scratch.household_ids_[index]);
        const auto &work = scratch.household_work_[index];
        household->income_expected = work.income_expected;
        household->income_realized = work.income_realized;
        household->consumption_budget = work.consumption_budget;
        household->spent = work.spent;
        household->labor_sold = work.labor_sold;
    }
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        auto *firm = state.firms.get(scratch.firm_ids_[index]);
        const auto &work = scratch.firm_work_[index];
        firm->goods_inventory = Goods(std::max(0.0, work.closing_inventory));
        firm->physical_capital = Capital(std::max(0.0, work.closing_capital));
        firm->posted_price = Price(work.posted_price);
        firm->posted_wage = Money(work.posted_wage);
        firm->markup = work.markup;
        firm->demand_expected = work.demand_expected;
        firm->target_inventory_previous = work.target_inventory;
        firm->labor_demand_previous = work.labor_demand_effective;
        firm->hired_previous = work.hired;
        firm->sales_previous = work.sales;
        firm->rationed_previous = work.rationed_demand;
        firm->attractiveness = work.attractiveness;
    }
    runtime.rng_counter = rng_counter;
    runtime.technology_rng_counter = technology.rng_counter;
    runtime.technology_index = technology.indices[0];
    runtime.technology_index_capital = technology.indices[1];
    runtime.technology_index_energy = technology.indices[2];
    runtime.tfp_learning_origin = technology.learning_origin;
    runtime.tfp_learning_base = technology.learning_base;
    runtime.tfp_learning_initialized = technology.learning_initialized;
    runtime.cumulative_sector_output[0] += metrics.consumption_output_real;
    runtime.cumulative_sector_output[1] += metrics.capital_output_real;
    runtime.public_capital = public_capital;
    runtime.previous_nominal_output = metrics.nominal_output;
    runtime.last_metrics = metrics;
    runtime.last_phase_trace = scratch.phase_trace_;
    tick = Tick(tick.value() + 1);
}

[[nodiscard]] Status prepare_working_state(const core::RootState &state,
                                           const M4Runtime &runtime,
                                           M4TickScratch &scratch) {
    if (scratch.household_ids_.size() != state.households.alive_count() ||
        scratch.firm_ids_.size() != state.firms.alive_count() ||
        scratch.household_dense_index_.size() !=
            state.households.allocator_state().next_id ||
        scratch.firm_dense_index_.size() != state.firms.allocator_state().next_id ||
        scratch.balances_.size() != state.postings.size() + 1 ||
        scratch.account_flags_.size() != state.postings.size() + 1) {
        scratch.reserve(state);
    }
    std::fill(scratch.balances_.begin(), scratch.balances_.end(), 0.0);
    std::fill(scratch.account_nodes_.begin(), scratch.account_nodes_.end(),
              SettlementNodeId{});
    std::fill(scratch.account_flags_.begin(), scratch.account_flags_.end(), 0U);
    for (const auto &account : state.postings.records()) {
        const auto index = static_cast<std::size_t>(account.id.value());
        scratch.balances_[index] = account.balance.value();
        scratch.account_nodes_[index] = account.key.settlement_node;
        scratch.account_flags_[index] =
            (account.open ? M4TickScratch::kAccountOpen : 0U) |
            (account.allow_negative ? M4TickScratch::kAccountAllowsNegative : 0U);
    }
    std::fill(scratch.reserve_balances_.begin(), scratch.reserve_balances_.end(), 0.0);
    for (const auto &reserve : state.reserves.records()) {
        const auto index = static_cast<std::size_t>(reserve.node.value());
        scratch.reserve_balances_[index] = reserve.balance.value();
    }
    scratch.reserve_minimum_ = scratch.reserve_balances_;
    scratch.transfer_count_ = 0;
    scratch.trade_count_ = 0;
    scratch.external_goods_units_ = 0.0;
    scratch.external_goods_value_ = 0.0;
    scratch.supplemental_tax_receipts_ = 0.0;
    scratch.supplemental_nontax_receipts_ = 0.0;
    scratch.supplemental_government_consumption_ = 0.0;
    scratch.supplemental_transfer_payments_ = 0.0;
    scratch.phase_trace_.clear();
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto *household = state.households.get(scratch.household_ids_[index]);
        auto expectation = algorithms::adaptive_expectation(
            household->income_expected, household->income_realized,
            household->income_adjustment);
        if (!expectation.ok()) {
            return expectation.status();
        }
        auto consumption = algorithms::consumption_plan({
            household->income_propensity,
            household->wealth_propensity,
            *expectation.get_if(),
            scratch.balances_[static_cast<std::size_t>(
                household->primary_account.value())],
            0.0,
            1.0,
            std::max(1.0, runtime.rules.initial_household_money),
        });
        if (!consumption.ok()) {
            return consumption.status();
        }
        auto &work = scratch.household_work_[index];
        work = {};
        work.income_expected = *expectation.get_if();
        work.consumption_budget = *consumption.get_if();
    }
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        scratch.firm_consumption_strata_[index] =
            scratch.firm_ids_[index].value() % 2U == 0U ? 1U : 0U;
        auto &work = scratch.firm_work_[index];
        work = {};
        work.closing_inventory = firm->goods_inventory.value();
        work.closing_capital = firm->physical_capital.value();
        work.posted_price = firm->posted_price.value();
        work.posted_wage = firm->posted_wage.value();
        work.markup = firm->markup;
        work.attractiveness = firm->attractiveness;
        auto expectation = algorithms::demand_expectation(
            firm->demand_expected, firm->sales_previous, firm->rationed_previous,
            firm->demand_adjustment *
                runtime.rules.capital_clock_demand_smoothing);
        if (!expectation.ok()) {
            return expectation.status();
        }
        work.demand_expected = *expectation.get_if();
    }
    return Status::success();
}

[[nodiscard]] Status plan_firms(const core::RootState &state, const M4Runtime &runtime,
                                M4TickScratch &scratch, PhiloxRng &rng,
                                const std::array<double, 3> &production_factors,
                                const M4AdvanceOptions &options) {
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        if (!is_base_firm_sector(firm->sector)) {
            continue;
        }
        const auto sector =
            static_cast<std::size_t>(static_cast<std::uint8_t>(firm->sector));
        const double productivity =
            firm->productivity * options.productivity_multipliers[sector];
        const double total_factor_productivity =
            firm->total_factor_productivity * options.productivity_multipliers[sector];
        auto &work = scratch.firm_work_[index];
        if (firm->sector == core::FirmSector::consumption &&
            runtime.rules.gibrat_growth && runtime.rules.gibrat_sigma > 0.0) {
            const double sigma = runtime.rules.gibrat_sigma;
            work.attractiveness = std::max(
                algorithms::kEconomicEpsilon,
                work.attractiveness *
                    std::exp(sigma * rng.standard_normal() - 0.5 * sigma * sigma));
        }
        auto production_plan = algorithms::production_plan({
            work.demand_expected,
            firm->inventory_ratio,
            firm->goods_inventory.value(),
            runtime.rules.inventory_gap_close,
        });
        if (!production_plan.ok()) {
            return production_plan.status();
        }
        work.target_inventory = production_plan.get_if()->target_inventory;
        work.production_target = production_plan.get_if()->production_target;
        auto labor = algorithms::labor_demand({
            technology_for(firm->technology),
            work.production_target,
            firm->productivity,
            firm->total_factor_productivity,
            firm->physical_capital.value(),
            firm->capital_share,
            production_factors[sector],
        });
        if (!labor.ok()) {
            return labor.status();
        }
        work.labor_demand_notional = *labor.get_if();
        const double wage_draw = runtime.stochastic ? rng.uniform_closed_open() : 1.0;
        auto wage = algorithms::wage_plan({
            firm->posted_wage.value(),
            firm->hired_previous,
            firm->labor_demand_previous,
            firm->shortage_adjustment,
            runtime.rules.wage_calvo_probability,
            wage_draw,
            0.0,
            runtime.rules.wage_downward_drift,
            runtime.rules.wage_expected_inflation,
            runtime.rules.wage_indexation,
        });
        if (!wage.ok()) {
            return wage.status();
        }
        work.posted_wage = std::max(runtime.rules.minimum_wage, wage.get_if()->posted);
        auto cost = algorithms::unit_cost({
            technology_for(firm->technology),
            work.posted_wage,
            productivity,
            total_factor_productivity,
            firm->physical_capital.value(),
            firm->capital_share,
            work.production_target,
            work.labor_demand_notional,
            0.0,
            0.0,
            runtime.rules.diseconomy_slope,
            0.0,
            true,
        });
        if (!cost.ok()) {
            return cost.status();
        }
        const double price_draw = runtime.stochastic ? rng.uniform_closed_open() : 1.0;
        auto price = algorithms::price_plan({
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
        });
        if (!price.ok()) {
            return price.status();
        }
        work.posted_price = price.get_if()->posted;
        work.markup = price.get_if()->markup;
        const double balance =
            scratch.balances_[static_cast<std::size_t>(firm->primary_account.value())];
        work.labor_demand_effective = std::max(
            0.0, std::min(work.labor_demand_notional, balance / work.posted_wage));
        auto investment = algorithms::investment_plan({
            runtime.vertical == M4Vertical::capital_fiscal &&
                firm->sector == core::FirmSector::consumption,
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
        });
        if (!investment.ok()) {
            return investment.status();
        }
        work.investment_target = *investment.get_if();
    }
    return Status::success();
}

[[nodiscard]] Status run_labor(const core::RootState &state, const M4Runtime &runtime,
                               M4TickScratch &scratch, PhiloxRng &rng) {
    scratch.firm_order_.resize(scratch.firm_ids_.size());
    std::iota(scratch.household_order_.begin(), scratch.household_order_.end(),
              std::size_t{0});
    std::iota(scratch.firm_order_.begin(), scratch.firm_order_.end(), std::size_t{0});
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
        const auto *firm = state.firms.get(scratch.firm_ids_[firm_index]);
        if (!is_base_firm_sector(firm->sector)) {
            continue;
        }
        auto &firm_work = scratch.firm_work_[firm_index];
        double need = firm_work.labor_demand_effective;
        while (need > algorithms::kEconomicEpsilon &&
               worker_position < scratch.household_order_.size()) {
            const auto household_index = scratch.household_order_[worker_position];
            const auto *household =
                state.households.get(scratch.household_ids_[household_index]);
            const auto firm_account =
                static_cast<std::size_t>(firm->primary_account.value());
            const double affordable =
                scratch.balances_[firm_account] / firm_work.posted_wage;
            if (affordable <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double hired = std::min({need, worker_remaining, affordable});
            if (hired <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double pay = hired * firm_work.posted_wage;
            const auto status = transfer(state, scratch, firm->primary_account,
                                         household->primary_account, pay,
                                         "M4 labor payroll exceeds available money");
            if (!status.ok()) {
                return status;
            }
            firm_work.hired += hired;
            firm_work.wage_bill += pay;
            auto &household_work = scratch.household_work_[household_index];
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

[[nodiscard]] Status run_production(const core::RootState &state,
                                    M4TickScratch &scratch,
                                    const std::array<double, 3> &production_factors,
                                    const M4AdvanceOptions &options) {
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        if (!is_base_firm_sector(firm->sector)) {
            continue;
        }
        const auto sector =
            static_cast<std::size_t>(static_cast<std::uint8_t>(firm->sector));
        auto &work = scratch.firm_work_[index];
        auto produced = algorithms::production({
            technology_for(firm->technology),
            work.hired * options.labor_availability_multipliers[sector],
            firm->productivity * options.productivity_multipliers[sector],
            firm->total_factor_productivity * options.productivity_multipliers[sector],
            firm->physical_capital.value(),
            firm->capital_share,
            production_factors[sector],
        });
        if (!produced.ok()) {
            return produced.status();
        }
        work.produced = *produced.get_if() * work.production_input_factor;
        work.closing_inventory = firm->goods_inventory.value() + work.produced;
    }
    return Status::success();
}

[[nodiscard]] Status apply_sampled_market(const core::RootState &state,
                                          M4TickScratch &scratch, PhiloxRng &rng,
                                          Tick tick, bool capital_market,
                                          bool consumption_rationed_signal,
                                          const M4AdvanceOptions &options) {
    scratch.market_buyer_order_.resize(scratch.orders_.size());
    std::iota(scratch.market_buyer_order_.begin(), scratch.market_buyer_order_.end(),
              std::size_t{0});
    auto status = rng.shuffle(std::span<std::size_t>(scratch.market_buyer_order_));
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
        const auto &order = scratch.orders_[buyer_index];
        const auto household_index =
            capital_market ? kAbsentFirmIndex
                           : household_projection_index(scratch, order.order_id);
        if (!capital_market &&
            (household_index >= scratch.household_work_.size() ||
             scratch.household_ids_[household_index].value() != order.order_id)) {
            return Status(ErrorCode::internal_error,
                          "M4 household buyer projection is stale");
        }
        double remaining_budget = order.budget.value();
        double remaining_demand = order.demand.value();
        double allocated = 0.0;
        while (remaining_budget > algorithms::kEconomicEpsilon &&
               remaining_demand > algorithms::kEconomicEpsilon &&
               !scratch.market_active_offers_.empty()) {
            auto selected_result =
                rng.uniform_index(scratch.market_active_offers_.size());
            if (!selected_result.ok()) {
                return selected_result.status();
            }
            auto selected_position = *selected_result.get_if();
            auto offer_index = scratch.market_active_offers_[selected_position];
            if (scratch.offers_[offer_index].seller == order.buyer) {
                selected_position = scratch.market_active_offers_.size();
                for (std::size_t position = 0;
                     position < scratch.market_active_offers_.size(); ++position) {
                    const auto candidate = scratch.market_active_offers_[position];
                    if (scratch.offers_[candidate].seller != order.buyer) {
                        selected_position = position;
                        offer_index = candidate;
                        break;
                    }
                }
                if (selected_position == scratch.market_active_offers_.size()) {
                    break;
                }
            }
            const auto &offer = scratch.offers_[offer_index];
            const double quantity = std::min({
                remaining_demand,
                remaining_budget / offer.price.value(),
                scratch.market_offer_remaining_[offer_index],
            });
            if (quantity <= algorithms::kEconomicEpsilon) {
                break;
            }
            const double value = quantity * offer.price.value();
            status = transfer(state, scratch, order.buyer, offer.seller, value,
                              "M4 goods purchase exceeds available money");
            if (!status.ok()) {
                return status;
            }
            remaining_budget -= value;
            remaining_demand -= quantity;
            allocated += quantity;
            scratch.market_offer_remaining_[offer_index] -= quantity;
            if (!capital_market && options.external_goods_offer.has_value() &&
                offer.offer_id == options.external_goods_offer->offer_id) {
                scratch.external_goods_units_ += quantity;
                scratch.external_goods_value_ += value;
            } else {
                const auto firm_index = firm_projection_index(scratch, offer.offer_id);
                if (firm_index == kAbsentFirmIndex ||
                    firm_index >= scratch.firm_work_.size()) {
                    return Status(ErrorCode::internal_error,
                                  "M4 market offer projection is stale");
                }
                auto &firm = scratch.firm_work_[firm_index];
                firm.sales += quantity;
                firm.revenue += value;
                if (!capital_market) {
                    record_consumption_purchase(scratch, household_index, firm_index,
                                                value);
                }
            }
            ++scratch.trade_count_;
            if (scratch.market_offer_remaining_[offer_index] <=
                algorithms::kEconomicEpsilon) {
                scratch.market_active_offers_[selected_position] =
                    scratch.market_active_offers_.back();
                scratch.market_active_offers_.pop_back();
            }
        }
        if (!capital_market && consumption_rationed_signal &&
            remaining_budget > algorithms::kEconomicEpsilon &&
            remaining_demand > algorithms::kEconomicEpsilon &&
            scratch.market_active_offers_.empty() && !scratch.offers_.empty()) {
            // Once every shelf is empty, the buyer still makes one observable
            // seller visit.  Attribute only that visit to the sampled domestic
            // firm; the rest of the unspent budget remains aggregate.  This is
            // the native counterpart of the product model's attributable
            // stock-out footfall and avoids fabricating an equal-share signal.
            const auto visited = stateless_index(state.seed, order.order_id, tick,
                                                 kConsumptionStockoutVisitStream,
                                                 scratch.offers_.size());
            const auto &offer = scratch.offers_[visited];
            const auto firm_index = firm_projection_index(scratch, offer.offer_id);
            if (firm_index != kAbsentFirmIndex &&
                firm_index < scratch.firm_work_.size() &&
                offer.price.value() > algorithms::kEconomicEpsilon) {
                scratch.firm_work_[firm_index].rationed_demand +=
                    remaining_budget / offer.price.value();
            }
        }
        if (capital_market) {
            const auto firm_index = firm_projection_index(scratch, order.order_id);
            if (firm_index >= scratch.firm_work_.size() ||
                scratch.firm_ids_[firm_index].value() != order.order_id) {
                return Status(ErrorCode::internal_error,
                              "M4 capital buyer projection is stale");
            }
            scratch.firm_work_[firm_index].investment = allocated;
        } else {
            scratch.household_work_[household_index].spent =
                order.budget.value() - remaining_budget;
        }
    }
    for (std::size_t index = 0; index < scratch.offers_.size(); ++index) {
        if (!capital_market && options.external_goods_offer.has_value() &&
            scratch.offers_[index].offer_id == options.external_goods_offer->offer_id) {
            continue;
        }
        const auto firm_index =
            firm_projection_index(scratch, scratch.offers_[index].offer_id);
        if (firm_index == kAbsentFirmIndex || firm_index >= scratch.firm_work_.size()) {
            return Status(ErrorCode::internal_error,
                          "M4 market offer projection is stale");
        }
        scratch.firm_work_[firm_index].closing_inventory =
            scratch.market_offer_remaining_[index];
    }
    return Status::success();
}

[[nodiscard]] Status apply_market(const core::RootState &state,
                                  const M4Runtime &runtime, M4TickScratch &scratch,
                                  PhiloxRng &rng, Tick tick, bool capital_market,
                                  const M4AdvanceOptions &options) {
    scratch.orders_.clear();
    scratch.offers_.clear();
    if (capital_market) {
        const auto add_investment_orders =
            [&](const std::vector<std::size_t> &indices) {
                for (const auto index : indices) {
                    const auto *firm = state.firms.get(scratch.firm_ids_[index]);
                    const auto &work = scratch.firm_work_[index];
                    const double budget = scratch.balances_[static_cast<std::size_t>(
                        firm->primary_account.value())];
                    if (work.investment_target > algorithms::kEconomicEpsilon &&
                        budget > algorithms::kEconomicEpsilon) {
                        scratch.orders_.push_back({
                            scratch.firm_ids_[index].value(),
                            firm->primary_account,
                            Goods(work.investment_target),
                            Money(budget),
                        });
                    }
                }
            };
        add_investment_orders(scratch.consumption_firm_indices_);
        // Energy capacity is productive capital too.  M8 plans its desired
        // expansion before labor and uses the same capital-goods market as
        // consumption firms, so scarcity and financing remain endogenous.
        add_investment_orders(scratch.energy_firm_indices_);
        for (const auto index : scratch.capital_firm_indices_) {
            const auto *firm = state.firms.get(scratch.firm_ids_[index]);
            const auto &work = scratch.firm_work_[index];
            scratch.offers_.push_back({
                scratch.firm_ids_[index].value(),
                firm->primary_account,
                Goods(std::max(0.0, work.closing_inventory)),
                Price(work.posted_price),
                work.attractiveness,
            });
        }
    } else {
        for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
            const auto *household = state.households.get(scratch.household_ids_[index]);
            const auto &work = scratch.household_work_[index];
            const double cash = scratch.balances_[static_cast<std::size_t>(
                household->primary_account.value())];
            const double budget = std::min(work.consumption_budget, cash);
            if (budget > algorithms::kEconomicEpsilon) {
                scratch.orders_.push_back({
                    scratch.household_ids_[index].value(),
                    household->primary_account,
                    Goods(std::numeric_limits<double>::infinity()),
                    Money(budget /
                          (1.0 + (runtime.vertical == M4Vertical::capital_fiscal
                                      ? maximum_consumption_tax_rate(runtime)
                                      : 0.0))),
                });
            }
        }
        for (const auto index : scratch.consumption_firm_indices_) {
            const auto *firm = state.firms.get(scratch.firm_ids_[index]);
            const auto &work = scratch.firm_work_[index];
            scratch.offers_.push_back({
                scratch.firm_ids_[index].value(),
                firm->primary_account,
                Goods(std::max(0.0, work.closing_inventory)),
                Price(work.posted_price),
                work.attractiveness,
            });
        }
        if (options.external_goods_offer.has_value()) {
            const auto &offer = *options.external_goods_offer;
            scratch.offers_.push_back({
                offer.offer_id,
                offer.seller,
                Goods(offer.stock),
                Price(offer.price),
                1.0,
            });
        }
    }
    if (runtime.market_protocol == algorithms::MatchingProtocol::sampled &&
        runtime.rules.market_sample_size == 1) {
        return apply_sampled_market(state, scratch, rng, tick, capital_market,
                                    runtime.rules.consumption_rationed_signal, options);
    }
    algorithms::MarketConfig config;
    config.protocol = runtime.market_protocol;
    config.sample_size = runtime.rules.market_sample_size;
    config.preferential_beta = runtime.rules.preferential_attachment_beta;
    config.price_elasticity = runtime.rules.preferential_price_elasticity;
    config.rng_key = runtime.rng_key;
    config.rng_counter = rng.counter();
    auto clearing = algorithms::clear_market(scratch.orders_, scratch.offers_, config);
    if (!clearing.ok()) {
        return clearing.status();
    }
    scratch.clearing_ = std::move(*clearing.get_if());
    rng = PhiloxRng(runtime.rng_key, scratch.clearing_.next_counter);
    for (const auto &trade : scratch.clearing_.trades) {
        const auto household_index =
            capital_market ? kAbsentFirmIndex
                           : household_projection_index(scratch, trade.order_id);
        if (!capital_market &&
            (household_index >= scratch.household_work_.size() ||
             scratch.household_ids_[household_index].value() != trade.order_id)) {
            return Status(ErrorCode::internal_error,
                          "M4 household buyer projection is stale");
        }
        const auto status =
            transfer(state, scratch, trade.buyer, trade.seller, trade.value.value(),
                     "M4 cleared goods purchase exceeds available money");
        if (!status.ok()) {
            return status;
        }
        if (!capital_market && options.external_goods_offer.has_value() &&
            trade.offer_id == options.external_goods_offer->offer_id) {
            scratch.external_goods_units_ += trade.quantity.value();
            scratch.external_goods_value_ += trade.value.value();
        } else {
            const auto firm_index = firm_projection_index(scratch, trade.offer_id);
            if (firm_index >= scratch.firm_work_.size() ||
                scratch.firm_ids_[firm_index].value() != trade.offer_id) {
                return Status(ErrorCode::internal_error,
                              "M4 market offer projection is stale");
            }
            auto &firm = scratch.firm_work_[firm_index];
            firm.sales += trade.quantity.value();
            firm.revenue += trade.value.value();
            if (!capital_market) {
                record_consumption_purchase(scratch, household_index, firm_index,
                                            trade.value.value());
            }
        }
        ++scratch.trade_count_;
    }
    for (const auto &stock : scratch.clearing_.stock_commands) {
        if (!capital_market && options.external_goods_offer.has_value() &&
            stock.offer_id == options.external_goods_offer->offer_id) {
            continue;
        }
        const auto firm_index = firm_projection_index(scratch, stock.offer_id);
        if (firm_index == kAbsentFirmIndex || firm_index >= scratch.firm_work_.size()) {
            return Status(ErrorCode::internal_error,
                          "M4 market stock projection is stale");
        }
        scratch.firm_work_[firm_index].closing_inventory = stock.closing.value();
    }
    for (const auto &allocation : scratch.clearing_.allocations) {
        if (capital_market) {
            const auto firm_id = allocation.order_id;
            const auto firm_index = firm_projection_index(scratch, firm_id);
            if (firm_index >= scratch.firm_work_.size() ||
                scratch.firm_ids_[firm_index].value() != firm_id) {
                return Status(ErrorCode::internal_error,
                              "M4 capital buyer projection is stale");
            }
            scratch.firm_work_[firm_index].investment = allocation.allocated.value();
        } else {
            const auto household_id = allocation.order_id;
            const auto household_identity = static_cast<std::size_t>(household_id);
            const auto household_index =
                household_identity < scratch.household_dense_index_.size()
                    ? scratch.household_dense_index_[household_identity]
                    : kAbsentFirmIndex;
            if (household_index >= scratch.household_work_.size() ||
                scratch.household_ids_[household_index].value() != household_id) {
                return Status(ErrorCode::internal_error,
                              "M4 household buyer projection is stale");
            }
            scratch.household_work_[household_index].spent = allocation.spent.value();
        }
    }
    return Status::success();
}

[[nodiscard]] Status run_consumption_tax(const core::RootState &state,
                                         const M4Runtime &runtime,
                                         M4TickScratch &scratch, double &tax_total,
                                         double &consumption_tax) noexcept {
    if (runtime.vertical != M4Vertical::capital_fiscal ||
        (runtime.rules.consumption_tax_rate <= 0.0 &&
         !runtime.rules.necessity_consumption_tax_rate.has_value() &&
         !runtime.rules.luxury_consumption_tax_rate.has_value())) {
        return Status::success();
    }
    const double necessity_rate = runtime.rules.necessity_consumption_tax_rate.value_or(
        runtime.rules.consumption_tax_rate);
    const double luxury_rate = runtime.rules.luxury_consumption_tax_rate.value_or(
        runtime.rules.consumption_tax_rate);
    const auto treasury = state.institutions.treasury_account;
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto *household = state.households.get(scratch.household_ids_[index]);
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        const auto &work = scratch.household_work_[index];
        const double generic_spent =
            std::max(0.0, work.spent - work.necessity_spent - work.luxury_spent);
        const double due = work.necessity_spent * necessity_rate +
                           work.luxury_spent * luxury_rate +
                           generic_spent * runtime.rules.consumption_tax_rate;
        const double paid = std::min(due, scratch.balances_[account]);
        const auto status =
            transfer(state, scratch, household->primary_account, treasury, paid,
                     "M4 consumption tax exceeds available money");
        if (!status.ok()) {
            return status;
        }
        tax_total += paid;
        consumption_tax += paid;
    }
    return Status::success();
}

[[nodiscard]] Status run_government_procurement(const core::RootState &state,
                                                const M4Runtime &runtime,
                                                M4TickScratch &scratch,
                                                double &government_spending) {
    if (runtime.vertical != M4Vertical::capital_fiscal) {
        return Status::success();
    }
    scratch.firm_order_.assign(scratch.consumption_firm_indices_.begin(),
                               scratch.consumption_firm_indices_.end());
    std::sort(scratch.firm_order_.begin(), scratch.firm_order_.end(),
              [&scratch](std::size_t left, std::size_t right) {
                  const auto &lhs = scratch.firm_work_[left];
                  const auto &rhs = scratch.firm_work_[right];
                  if (lhs.posted_price != rhs.posted_price) {
                      return lhs.posted_price < rhs.posted_price;
                  }
                  return scratch.firm_ids_[left] < scratch.firm_ids_[right];
              });
    const double output_reference = fiscal_output_reference(runtime, scratch);
    const double committed_outlays =
        runtime.rules.government_investment_share * output_reference +
        runtime.last_metrics.transfer_payments;
    double budget = 0.0;
    if (runtime.rules.government_deficit_target > 0.0) {
        double target = runtime.rules.government_deficit_target;
        if (runtime.rules.deficit_unemployment_reference > 0.0) {
            target *= std::min(runtime.rules.deficit_unemployment_cap,
                               runtime.last_metrics.unemployment_rate /
                                   runtime.rules.deficit_unemployment_reference);
        }
        // Deficit targeting and quantity targeting are separate fiscal
        // regimes. In deficit mode, discretionary procurement is the residual
        // that makes total spending approach tax receipts plus the target
        // deficit after transfers and public investment.
        budget = std::max(0.0, runtime.last_metrics.tax_total +
                                   target * output_reference - committed_outlays);
    } else {
        budget = runtime.rules.government_consumption_share * output_reference;
    }
    const auto treasury = state.institutions.treasury_account;
    std::size_t last_contractor = kAbsentFirmIndex;
    for (const auto index : scratch.firm_order_) {
        if (budget <= algorithms::kEconomicEpsilon) {
            break;
        }
        auto &work = scratch.firm_work_[index];
        const double quantity =
            std::min(work.closing_inventory, budget / work.posted_price);
        if (quantity <= algorithms::kEconomicEpsilon) {
            continue;
        }
        const double value = quantity * work.posted_price;
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        const auto status =
            transfer(state, scratch, treasury, firm->primary_account, value,
                     "M4 government procurement exceeds available money");
        if (!status.ok()) {
            return status;
        }
        work.closing_inventory -= quantity;
        work.sales += quantity;
        work.revenue += value;
        government_spending += value;
        budget -= value;
        last_contractor = index;
    }
    // The final accepted supplier observes the unfilled remainder of the same
    // tender when it has sold out.  Carry that attributable physical demand
    // into next-period expectations.  Without this link, procurement capped by
    // today's inventory is mistaken for weak demand and the supply-constrained
    // equilibrium becomes self-confirming.
    if (runtime.rules.consumption_rationed_signal &&
        last_contractor != kAbsentFirmIndex && budget > algorithms::kEconomicEpsilon) {
        auto &contractor = scratch.firm_work_[last_contractor];
        if (contractor.closing_inventory <= algorithms::kEconomicEpsilon &&
            contractor.posted_price > algorithms::kEconomicEpsilon) {
            contractor.rationed_demand += budget / contractor.posted_price;
        }
    }
    return Status::success();
}

[[nodiscard]] Status run_public_investment(const core::RootState &state,
                                           const M4Runtime &runtime,
                                           M4TickScratch &scratch,
                                           double &government_spending,
                                           double &public_capital_addition,
                                           double &public_investment_spending) {
    if (runtime.vertical != M4Vertical::capital_fiscal ||
        runtime.rules.government_investment_share <= 0.0) {
        return Status::success();
    }
    scratch.firm_order_.assign(scratch.capital_firm_indices_.begin(),
                               scratch.capital_firm_indices_.end());
    std::sort(scratch.firm_order_.begin(), scratch.firm_order_.end(),
              [&scratch](std::size_t left, std::size_t right) {
                  const auto &lhs = scratch.firm_work_[left];
                  const auto &rhs = scratch.firm_work_[right];
                  if (lhs.posted_price != rhs.posted_price) {
                      return lhs.posted_price < rhs.posted_price;
                  }
                  return scratch.firm_ids_[left] < scratch.firm_ids_[right];
              });
    double budget = runtime.rules.government_investment_share *
                    fiscal_output_reference(runtime, scratch);
    const auto treasury = state.institutions.treasury_account;
    for (const auto index : scratch.firm_order_) {
        if (budget <= algorithms::kEconomicEpsilon) {
            break;
        }
        auto &work = scratch.firm_work_[index];
        const double quantity =
            std::min(work.closing_inventory, budget / work.posted_price);
        if (quantity <= algorithms::kEconomicEpsilon) {
            continue;
        }
        const double value = quantity * work.posted_price;
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        const auto status =
            transfer(state, scratch, treasury, firm->primary_account, value,
                     "M4 public investment exceeds available money");
        if (!status.ok()) {
            return status;
        }
        work.closing_inventory -= quantity;
        work.sales += quantity;
        work.revenue += value;
        budget -= value;
        government_spending += value;
        public_capital_addition += quantity;
        public_investment_spending += value;
    }
    return Status::success();
}

[[nodiscard]] Status run_settlement(const core::RootState &state, M4Runtime &runtime,
                                    M4TickScratch &scratch, M4TickExtension *extension,
                                    Tick tick, PhiloxRng &rng, double &tax_total,
                                    double &profit_tax, double &income_tax,
                                    double &benefit_spending,
                                    double &public_capital_addition,
                                    double &job_guarantee_spending,
                                    double &job_guarantee_labor,
                                    double &job_guarantee_capital_addition) {
    const bool fiscal = runtime.vertical == M4Vertical::capital_fiscal;
    const auto treasury = state.institutions.treasury_account;
    const auto clearing = state.institutions.clearing_account;
    double dividend_total = 0.0;
    for (std::size_t index = 0; index < scratch.firm_ids_.size(); ++index) {
        const auto *firm = state.firms.get(scratch.firm_ids_[index]);
        if (!settles_current_income(firm->sector)) {
            continue;
        }
        auto &work = scratch.firm_work_[index];
        if (is_base_firm_sector(firm->sector)) {
            work.profit = work.revenue - work.wage_bill - work.production_input_cost;
        }
        if (fiscal && work.profit > algorithms::kEconomicEpsilon) {
            const auto account =
                static_cast<std::size_t>(firm->primary_account.value());
            const double due = runtime.rules.profit_tax_rate * work.profit;
            work.profit_tax = std::min(due, scratch.balances_[account]);
            const auto status =
                transfer(state, scratch, firm->primary_account, treasury,
                         work.profit_tax, "M4 profit tax exceeds available money");
            if (!status.ok()) {
                return status;
            }
            tax_total += work.profit_tax;
            profit_tax += work.profit_tax;
        }
        const double distributable = std::max(0.0, work.profit - work.profit_tax);
        const auto account = static_cast<std::size_t>(firm->primary_account.value());
        work.dividends =
            std::min(firm->dividend_payout * distributable, scratch.balances_[account]);
        if (work.dividends > algorithms::kEconomicEpsilon) {
            const auto status =
                transfer(state, scratch, firm->primary_account, clearing,
                         work.dividends, "M4 dividend exceeds available money");
            if (!status.ok()) {
                return status;
            }
            dividend_total += work.dividends;
        }
        work.retained_earnings = work.profit - work.profit_tax - work.dividends;
    }
    bool dividends_handled = false;
    if (dividend_total > algorithms::kEconomicEpsilon && extension != nullptr) {
        const auto status = extension->distribute_dividends(
            state, runtime, scratch, tick, rng, dividend_total, dividends_handled);
        if (!status.ok()) {
            return status;
        }
    }
    if (dividend_total > algorithms::kEconomicEpsilon && !dividends_handled &&
        !scratch.household_ids_.empty()) {
        const auto clearing_index = static_cast<std::size_t>(clearing.value());
        double remaining =
            std::min(dividend_total, std::max(0.0, scratch.balances_[clearing_index]));
        for (std::size_t index = 0; index + 1 < scratch.household_ids_.size();
             ++index) {
            const auto *household = state.households.get(scratch.household_ids_[index]);
            const auto recipients_left = scratch.household_ids_.size() - index;
            const double share = remaining / static_cast<double>(recipients_left);
            const auto status =
                transfer(state, scratch, clearing, household->primary_account, share,
                         "M4 dividend allocation exceeds clearing balance");
            if (!status.ok()) {
                return status;
            }
            remaining -= share;
            scratch.household_work_[index].income_realized += share;
        }
        const auto last_index = scratch.household_ids_.size() - 1;
        const auto *household =
            state.households.get(scratch.household_ids_[last_index]);
        const double remainder =
            std::min(remaining, std::max(0.0, scratch.balances_[clearing_index]));
        const auto status =
            transfer(state, scratch, clearing, household->primary_account, remainder,
                     "M4 dividend remainder exceeds clearing balance");
        if (!status.ok()) {
            return status;
        }
        scratch.household_work_[last_index].income_realized += remainder;
    }
    if (!fiscal) {
        return Status::success();
    }
    double mean_income = 0.0;
    for (const auto &work : scratch.household_work_) {
        mean_income += work.income_realized;
    }
    mean_income /=
        static_cast<double>(std::max<std::size_t>(1, scratch.household_work_.size()));
    const double income_allowance = runtime.rules.income_allowance * mean_income;
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto *household = state.households.get(scratch.household_ids_[index]);
        auto &work = scratch.household_work_[index];
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        const double due = runtime.rules.income_tax_rate *
                           std::max(0.0, work.income_realized - income_allowance);
        const double paid = std::min(due, scratch.balances_[account]);
        auto status = transfer(state, scratch, household->primary_account, treasury,
                               paid, "M4 income tax exceeds available money");
        if (!status.ok()) {
            return status;
        }
        work.income_realized -= paid;
        tax_total += paid;
        income_tax += paid;
    }
    double mean_wage = 0.0;
    for (const auto &firm : scratch.firm_work_) {
        mean_wage += firm.posted_wage;
    }
    mean_wage /=
        static_cast<double>(std::max<std::size_t>(1, scratch.firm_work_.size()));
    if (runtime.rules.job_guarantee && runtime.rules.job_guarantee_wage_ratio > 0.0) {
        const double guarantee_wage =
            std::max(runtime.rules.minimum_wage,
                     runtime.rules.job_guarantee_wage_ratio * mean_wage);
        for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
            const auto *household = state.households.get(scratch.household_ids_[index]);
            auto &work = scratch.household_work_[index];
            const double residual =
                std::max(0.0, work.labor_capacity - work.labor_sold);
            const double payment = guarantee_wage * residual;
            const auto status =
                transfer(state, scratch, treasury, household->primary_account, payment,
                         "M4 job guarantee exceeds treasury capacity");
            if (!status.ok()) {
                return status;
            }
            work.income_realized += payment;
            benefit_spending += payment;
            job_guarantee_spending += payment;
            job_guarantee_labor += residual;
            const double produced =
                runtime.rules.job_guarantee_productivity *
                runtime.rules.job_guarantee_public_works_share * residual;
            public_capital_addition += produced;
            job_guarantee_capital_addition += produced;
        }
    }
    for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
        const auto *household = state.households.get(scratch.household_ids_[index]);
        auto &work = scratch.household_work_[index];
        const double benefit =
            runtime.rules.unemployment_benefit_replacement * mean_wage *
            (runtime.rules.job_guarantee && runtime.rules.job_guarantee_wage_ratio > 0.0
                 ? 0.0
                 : std::max(0.0, work.labor_capacity - work.labor_sold));
        auto status =
            transfer(state, scratch, treasury, household->primary_account, benefit,
                     "M4 unemployment benefit exceeds treasury capacity");
        if (!status.ok()) {
            return status;
        }
        work.income_realized += benefit;
        benefit_spending += benefit;
        if (runtime.rules.benefit_income_floor > 0.0) {
            const double floor = runtime.rules.benefit_income_floor * mean_wage;
            const double top_up = std::max(0.0, floor - work.income_realized);
            status =
                transfer(state, scratch, treasury, household->primary_account, top_up,
                         "M4 income-floor benefit exceeds treasury capacity");
            if (!status.ok()) {
                return status;
            }
            work.income_realized += top_up;
            benefit_spending += top_up;
        }
    }
    if (runtime.rules.wealth_tax_rate > algorithms::kEconomicEpsilon) {
        scratch.household_net_wealth_.resize(scratch.household_ids_.size());
        for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
            const auto *household = state.households.get(scratch.household_ids_[index]);
            scratch.household_net_wealth_[index] =
                scratch.balances_[static_cast<std::size_t>(
                    household->primary_account.value())];
        }
        if (extension != nullptr) {
            const auto status = extension->prepare_household_net_wealth(
                state, runtime, scratch, tick, rng,
                std::span<double>(scratch.household_net_wealth_));
            if (!status.ok()) {
                return status;
            }
        }
        if (!all_finite(std::span<const double>(scratch.household_net_wealth_))) {
            return Status(ErrorCode::invariant_violation,
                          "M4 household net wealth projection is not finite");
        }
        double mean_wealth = 0.0;
        for (const double wealth : scratch.household_net_wealth_) {
            mean_wealth += std::max(0.0, wealth);
        }
        mean_wealth /= static_cast<double>(
            std::max<std::size_t>(1, scratch.household_ids_.size()));
        const double wealth_allowance = runtime.rules.wealth_allowance * mean_wealth;
        for (std::size_t index = 0; index < scratch.household_ids_.size(); ++index) {
            const auto *household = state.households.get(scratch.household_ids_[index]);
            const auto account =
                static_cast<std::size_t>(household->primary_account.value());
            const double wealth_tax =
                std::min(runtime.rules.wealth_tax_rate *
                             std::max(0.0, scratch.household_net_wealth_[index] -
                                               wealth_allowance),
                         std::max(0.0, scratch.balances_[account]));
            const auto status =
                transfer(state, scratch, household->primary_account, treasury,
                         wealth_tax, "M4 wealth tax exceeds available money");
            if (!status.ok()) {
                return status;
            }
            tax_total += wealth_tax;
        }
    }
    return Status::success();
}

void commit_capital(const core::RootState &state, M4TickScratch &scratch) noexcept {
    const auto commit_sector = [&](const std::vector<std::size_t> &indices) {
        for (const auto index : indices) {
            const auto *firm = state.firms.get(scratch.firm_ids_[index]);
            auto &work = scratch.firm_work_[index];
            work.closing_capital =
                (1.0 - firm->capital_depreciation) * firm->physical_capital.value() +
                work.investment;
        }
    };
    commit_sector(scratch.consumption_firm_indices_);
    commit_sector(scratch.energy_firm_indices_);
}

[[nodiscard]] M4Metrics measure(const core::RootState &state, const M4Runtime &runtime,
                                const M4TickScratch &scratch, Tick tick,
                                double tax_total, double profit_tax, double income_tax,
                                double consumption_tax, double government_spending,
                                double benefit_spending, double public_capital,
                                double public_investment_spending,
                                double job_guarantee_spending,
                                double job_guarantee_labor,
                                double job_guarantee_capital_formation) noexcept {
    M4Metrics metrics;
    metrics.tick = tick;
    double sold_quantity = 0.0;
    double price_value = 0.0;
    for (std::size_t index = 0; index < scratch.firm_work_.size(); ++index) {
        const auto &firm = scratch.firm_work_[index];
        const auto *persistent = state.firms.get(scratch.firm_ids_[index]);
        if (is_base_firm_sector(persistent->sector)) {
            metrics.real_output += firm.produced;
            metrics.nominal_output += firm.revenue;
            const double output_value = firm.produced * firm.posted_price;
            metrics.gross_output_nominal += output_value;
            const double inventory_change =
                firm.closing_inventory - persistent->goods_inventory.value();
            metrics.inventory_change_real += inventory_change;
            metrics.inventory_change_nominal += inventory_change * firm.posted_price;
        }
        if (persistent->sector == core::FirmSector::consumption) {
            sold_quantity += firm.sales;
            price_value += firm.sales * firm.posted_price;
            metrics.consumption_output_real += firm.produced;
            metrics.consumption_output_nominal += firm.produced * firm.posted_price;
        } else if (persistent->sector == core::FirmSector::capital) {
            metrics.capital_output_real += firm.produced;
            metrics.capital_output_nominal += firm.produced * firm.posted_price;
            metrics.fixed_capital_formation_real += firm.sales;
            metrics.fixed_capital_formation_nominal += firm.revenue;
        }
        metrics.wages_paid += firm.wage_bill;
        metrics.firm_profit += firm.profit;
        metrics.dividends_paid += firm.dividends;
        metrics.aggregate_capital += firm.closing_capital;
    }
    const double productive_job_guarantee_spending =
        runtime.rules.job_guarantee_public_works_share * job_guarantee_spending;
    const bool productive_job_guarantee =
        job_guarantee_capital_formation > algorithms::kEconomicEpsilon;
    if (productive_job_guarantee) {
        // Productive JG labor is own-account government construction.  Value
        // current output at its observed wage cost and record the physical
        // public-capital units separately, matching national-account treatment
        // of own-account fixed-capital formation.
        metrics.real_output += job_guarantee_capital_formation;
        metrics.nominal_output += productive_job_guarantee_spending;
        metrics.gross_output_nominal += productive_job_guarantee_spending;
        metrics.fixed_capital_formation_real +=
            job_guarantee_capital_formation;
        metrics.fixed_capital_formation_nominal +=
            productive_job_guarantee_spending;
        metrics.wages_paid += productive_job_guarantee_spending;
    }
    double labor_capacity = 0.0;
    for (const auto &household : scratch.household_work_) {
        metrics.household_consumption += household.spent;
        metrics.unemployment_rate +=
            std::max(0.0, household.labor_capacity - household.labor_sold);
        labor_capacity += household.labor_capacity;
    }
    metrics.unemployment_rate =
        labor_capacity > 0.0 ? metrics.unemployment_rate / labor_capacity : 0.0;
    if (sold_quantity > algorithms::kEconomicEpsilon) {
        metrics.price_index = price_value / sold_quantity;
    } else if (!scratch.consumption_firm_indices_.empty()) {
        for (const auto index : scratch.consumption_firm_indices_) {
            metrics.price_index += scratch.firm_work_[index].posted_price;
        }
        metrics.price_index /=
            static_cast<double>(scratch.consumption_firm_indices_.size());
    }
    metrics.total_money = sum_balances(scratch);
    metrics.conservation_drift = metrics.total_money - state.genesis_money.value();
    metrics.tax_total = tax_total + scratch.supplemental_tax_receipts_;
    metrics.tax_profit = profit_tax;
    metrics.tax_income = income_tax;
    metrics.tax_consumption = consumption_tax;
    metrics.government_spending = government_spending + benefit_spending +
                                  scratch.supplemental_government_consumption_ +
                                  scratch.supplemental_transfer_payments_;
    metrics.government_consumption = government_spending - public_investment_spending +
                                     scratch.supplemental_government_consumption_;
    metrics.public_fixed_capital_formation =
        public_investment_spending +
        (productive_job_guarantee ? productive_job_guarantee_spending : 0.0);
    metrics.transfer_payments =
        benefit_spending -
        (productive_job_guarantee ? productive_job_guarantee_spending : 0.0) +
        scratch.supplemental_transfer_payments_;
    metrics.government_deficit = metrics.government_spending - metrics.tax_total -
                                 scratch.supplemental_nontax_receipts_;
    metrics.public_capital = public_capital;
    metrics.job_guarantee_spending = job_guarantee_spending;
    metrics.job_guarantee_labor = job_guarantee_labor;
    metrics.job_guarantee_public_capital_formation =
        job_guarantee_capital_formation;
    const double public_works_labor =
        runtime.rules.job_guarantee_public_works_share * job_guarantee_labor;
    metrics.job_guarantee_realized_productivity =
        public_works_labor > algorithms::kEconomicEpsilon
            ? job_guarantee_capital_formation / public_works_labor
            : 0.0;
    static_cast<void>(runtime);
    return metrics;
}

[[nodiscard]] Result<M4AdvanceResult>
advance_one(core::RootState &state, M4Runtime &runtime, M4TickScratch &scratch,
            Tick &tick, const M4AdvanceOptions &options, M4TickExtension *extension) {
    struct RuleRestore final {
        M4Runtime &runtime;
        M4Rules rules;
        ~RuleRestore() { runtime.rules = rules; }
    } restore{runtime, runtime.rules};
    auto status = check_fault(options, M4Phase::open_books);
    if (!status.ok()) {
        return status;
    }
    status = prepare_working_state(state, runtime, scratch);
    if (!status.ok()) {
        return status;
    }
    for (auto &household : scratch.household_work_) {
        household.consumption_budget *= options.household_demand_multiplier;
    }
    PhiloxRng rng(runtime.rng_key, runtime.rng_counter);
    if (extension != nullptr) {
        status = extension->prepare_tick(state, runtime, scratch, tick, rng);
        if (!status.ok()) {
            return status;
        }
    }
    capture_phase(state, scratch, options, M4Phase::open_books);

    status = check_fault(options, M4Phase::open_real_economy);
    if (!status.ok()) {
        return status;
    }
    auto technology_result = project_technology(runtime);
    if (!technology_result.ok()) {
        return technology_result.status();
    }
    const auto technology = *technology_result.get_if();
    const double public_capital_factor =
        runtime.rules.public_capital_gamma > 0.0
            ? std::pow(1.0 + runtime.public_capital / runtime.public_capital_reference,
                       runtime.rules.public_capital_gamma)
            : 1.0;
    for (std::size_t sector = 0; sector < scratch.production_factors_.size(); ++sector) {
        scratch.production_factors_[sector] =
            technology.indices[sector] * public_capital_factor;
    }
    capture_phase(state, scratch, options, M4Phase::open_real_economy);

    status = check_fault(options, M4Phase::plan_and_finance);
    if (!status.ok()) {
        return status;
    }
    status = plan_firms(state, runtime, scratch, rng, scratch.production_factors_,
                        options);
    if (!status.ok()) {
        return status;
    }
    if (extension != nullptr) {
        status = extension->after_planning(state, runtime, scratch, tick, rng);
        if (!status.ok()) {
            return status;
        }
    }
    capture_phase(state, scratch, options, M4Phase::plan_and_finance);

    status = check_fault(options, M4Phase::labor);
    if (!status.ok()) {
        return status;
    }
    bool labor_handled = false;
    if (extension != nullptr) {
        status =
            extension->run_labor(state, runtime, scratch, tick, rng, labor_handled);
        if (!status.ok()) {
            return status;
        }
    }
    if (!labor_handled) {
        status = run_labor(state, runtime, scratch, rng);
        if (!status.ok()) {
            return status;
        }
    }
    capture_phase(state, scratch, options, M4Phase::labor);

    status = check_fault(options, M4Phase::production);
    if (!status.ok()) {
        return status;
    }
    status = run_production(state, scratch, scratch.production_factors_, options);
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::production);

    status = check_fault(options, M4Phase::goods_market);
    if (!status.ok()) {
        return status;
    }
    status = apply_market(state, runtime, scratch, rng, tick, false, options);
    if (!status.ok()) {
        return status;
    }
    double tax_total = 0.0;
    double profit_tax = 0.0;
    double income_tax = 0.0;
    double consumption_tax = 0.0;
    double government_spending = 0.0;
    double public_capital_addition = 0.0;
    double public_investment_spending = 0.0;
    status = run_consumption_tax(state, runtime, scratch, tax_total, consumption_tax);
    if (!status.ok()) {
        return status;
    }
    status = run_government_procurement(state, runtime, scratch, government_spending);
    if (!status.ok()) {
        return status;
    }
    capture_phase(state, scratch, options, M4Phase::goods_market);

    if (runtime.vertical == M4Vertical::capital_fiscal) {
        status = check_fault(options, M4Phase::capital_market);
        if (!status.ok()) {
            return status;
        }
        status = apply_market(state, runtime, scratch, rng, tick, true, options);
        if (!status.ok()) {
            return status;
        }
        if (runtime.rules.capital_rationed_signal &&
            !scratch.capital_firm_indices_.empty()) {
            double unmet = 0.0;
            const auto accumulate_unmet = [&scratch, &unmet](
                                              const std::vector<std::size_t> &indices) {
                for (const auto index : indices) {
                    const auto &work = scratch.firm_work_[index];
                    unmet += std::max(0.0, work.investment_target - work.investment);
                }
            };
            accumulate_unmet(scratch.consumption_firm_indices_);
            accumulate_unmet(scratch.energy_firm_indices_);
            const double share =
                unmet / static_cast<double>(scratch.capital_firm_indices_.size());
            for (const auto index : scratch.capital_firm_indices_) {
                scratch.firm_work_[index].rationed_demand += share;
            }
        }
        status =
            run_public_investment(state, runtime, scratch, government_spending,
                                  public_capital_addition, public_investment_spending);
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
    double job_guarantee_spending = 0.0;
    double job_guarantee_labor = 0.0;
    double job_guarantee_capital_addition = 0.0;
    if (extension != nullptr) {
        status = extension->before_settlement(state, runtime, scratch, tick, rng);
        if (!status.ok()) {
            return status;
        }
    }
    status = run_settlement(state, runtime, scratch, extension, tick, rng, tax_total,
                            profit_tax, income_tax, benefit_spending,
                            public_capital_addition, job_guarantee_spending,
                            job_guarantee_labor,
                            job_guarantee_capital_addition);
    if (!status.ok()) {
        return status;
    }
    commit_capital(state, scratch);
    if (extension != nullptr) {
        status = extension->after_settlement(state, runtime, scratch, tick, rng);
        if (!status.ok()) {
            return status;
        }
        status = extension->close_institutions(state, runtime, scratch, tick, rng);
        if (!status.ok()) {
            return status;
        }
    }
    const double public_capital =
        (1.0 - runtime.rules.public_capital_depreciation) * runtime.public_capital +
        public_capital_addition;
    capture_phase(state, scratch, options, M4Phase::settle_domestic);

    status = check_fault(options, M4Phase::validate_and_measure);
    if (!status.ok()) {
        return status;
    }
    status = validate_working_state(state, scratch, extension != nullptr);
    if (!status.ok()) {
        return status;
    }
    if (extension != nullptr && options.audit_extended_state) {
        status = extension->validate(state, runtime, scratch, tick);
        if (!status.ok()) {
            return status;
        }
    }
    auto metrics =
        measure(state, runtime, scratch, tick, tax_total, profit_tax, income_tax,
                consumption_tax, government_spending, benefit_spending, public_capital,
                public_investment_spending, job_guarantee_spending,
                job_guarantee_labor,
                job_guarantee_capital_addition);
    metrics.tfp_index_consumption = technology.indices[0];
    metrics.tfp_index_capital = technology.indices[1];
    metrics.tfp_index_energy = technology.indices[2];
    metrics.tfp_growth_consumption = technology.growth[0];
    metrics.tfp_growth_capital = technology.growth[1];
    metrics.tfp_growth_energy = technology.growth[2];
    metrics.cumulative_output_consumption =
        runtime.cumulative_sector_output[0] + metrics.consumption_output_real;
    metrics.cumulative_output_capital =
        runtime.cumulative_sector_output[1] + metrics.capital_output_real;
    metrics.cumulative_output_energy = runtime.cumulative_sector_output[2];
    capture_phase(state, scratch, options, M4Phase::validate_and_measure);

    status = check_fault(options, M4Phase::stage_local_commit);
    if (!status.ok()) {
        return status;
    }
    commit_working_state(state, runtime, scratch, tick, metrics, rng.counter(),
                         technology, public_capital);
    if (extension != nullptr) {
        extension->commit(state, runtime, scratch, metrics.tick, metrics);
    }
    if (options.capture_phase_trace) {
        runtime.last_phase_trace.push_back({
            M4Phase::stage_local_commit,
            metrics.total_money,
            0.0,
            metrics.aggregate_capital,
            scratch.transfer_count_,
            scratch.trade_count_,
        });
    }
    return M4AdvanceResult{
        metrics.tick,
        tick,
        1,
        metrics,
        scratch.capacity_signature(),
        scratch.transfer_count_,
        scratch.trade_count_,
        scratch.external_goods_units_,
        scratch.external_goods_value_,
    };
}

} // namespace

void M4TickScratch::reserve(const core::RootState &state) {
    const auto household_count = state.households.alive_count();
    const auto firm_count = state.firms.alive_count();
    household_ids_.clear();
    household_dense_index_.assign(
        static_cast<std::size_t>(state.households.allocator_state().next_id),
        kAbsentFirmIndex);
    household_ids_.reserve(household_count);
    state.households.for_each_alive(
        [this](HouseholdId id, const core::HouseholdComponent &) {
            household_dense_index_[static_cast<std::size_t>(id.value())] =
                household_ids_.size();
            household_ids_.push_back(id);
        });
    firm_ids_.clear();
    firm_dense_index_.assign(
        static_cast<std::size_t>(state.firms.allocator_state().next_id),
        kAbsentFirmIndex);
    consumption_firm_indices_.clear();
    capital_firm_indices_.clear();
    energy_firm_indices_.clear();
    construction_firm_indices_.clear();
    firm_consumption_strata_.clear();
    firm_ids_.reserve(firm_count);
    consumption_firm_indices_.reserve(firm_count);
    capital_firm_indices_.reserve(firm_count);
    energy_firm_indices_.reserve(firm_count);
    construction_firm_indices_.reserve(firm_count);
    firm_consumption_strata_.resize(firm_count);
    state.firms.for_each_alive([this](FirmId id, const core::FirmComponent &firm) {
        const auto index = firm_ids_.size();
        firm_ids_.push_back(id);
        firm_dense_index_[static_cast<std::size_t>(id.value())] = index;
        if (firm.sector == core::FirmSector::consumption) {
            consumption_firm_indices_.push_back(index);
        } else if (firm.sector == core::FirmSector::capital) {
            capital_firm_indices_.push_back(index);
        } else if (firm.sector == core::FirmSector::energy) {
            energy_firm_indices_.push_back(index);
        } else {
            construction_firm_indices_.push_back(index);
        }
    });
    household_order_.resize(household_count);
    firm_order_.resize(firm_count);
    std::iota(household_order_.begin(), household_order_.end(), std::size_t{0});
    std::iota(firm_order_.begin(), firm_order_.end(), std::size_t{0});
    balances_.resize(state.postings.size() + 1);
    account_nodes_.resize(state.postings.size() + 1);
    account_flags_.resize(state.postings.size() + 1);
    reserve_balances_.resize(state.reserves.size() + 1);
    reserve_minimum_.resize(state.reserves.size() + 1);
    household_net_wealth_.resize(household_count);
    household_work_.resize(household_count);
    firm_work_.resize(firm_count);
    orders_.reserve(std::max(household_count, firm_count));
    offers_.reserve(firm_count);
    market_buyer_order_.reserve(std::max(household_count, firm_count));
    market_active_offers_.reserve(firm_count);
    market_offer_remaining_.reserve(firm_count);
    phase_trace_.reserve(10);
}

std::uint64_t M4TickScratch::capacity_signature() const noexcept {
    std::uint64_t signature = 1469598103934665603ULL;
    const std::array capacities{
        household_ids_.capacity(),
        household_dense_index_.capacity(),
        firm_ids_.capacity(),
        firm_dense_index_.capacity(),
        consumption_firm_indices_.capacity(),
        capital_firm_indices_.capacity(),
        energy_firm_indices_.capacity(),
        construction_firm_indices_.capacity(),
        firm_consumption_strata_.capacity(),
        household_order_.capacity(),
        firm_order_.capacity(),
        balances_.capacity(),
        account_nodes_.capacity(),
        account_flags_.capacity(),
        reserve_balances_.capacity(),
        reserve_minimum_.capacity(),
        household_net_wealth_.capacity(),
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

Status validate_spec(const M4SimulationSpec &spec) noexcept {
    if (!spec.economy.valid() || !spec.currency.valid() || spec.households == 0 ||
        spec.consumption_firms == 0 || spec.settlement_banks == 0) {
        return Status(
            ErrorCode::invalid_argument,
            "M4 genesis requires valid IDs, households, and consumption firms");
    }
    if (spec.households > 10'000'000 || spec.consumption_firms > 10'000'000 ||
        spec.capital_firms > 10'000'000 || spec.settlement_banks > 1'000'000) {
        return Status(ErrorCode::out_of_range, "M4 entity limit is exceeded");
    }
    if ((spec.requested_capabilities & kUnsupportedCapabilities) != 0) {
        return Status(ErrorCode::unsupported,
                      "requested capability is scheduled after M4");
    }
    if (spec.vertical == M4Vertical::cash_loop) {
        if (spec.capital_firms != 0 || spec.requested_capabilities != 0) {
            return Status(ErrorCode::unsupported,
                          "M4 V0 supports only the basic cash-loop capability set");
        }
    } else if (spec.capital_firms == 0 ||
               spec.requested_capabilities != kV1Capabilities) {
        return Status(
            ErrorCode::unsupported,
            "M4 V1 requires exactly physical-capital and government capabilities");
    }
    const auto &rules = spec.rules;
    const std::array values{
        rules.linear_productivity,
        rules.capital_productivity,
        rules.total_factor_productivity,
        rules.capital_share,
        rules.capital_output_ratio,
        rules.demand_adjustment,
        rules.capital_clock_demand_smoothing,
        rules.income_adjustment,
        rules.inventory_ratio,
        rules.inventory_gap_close,
        rules.markup_adjustment,
        rules.markup_minimum,
        rules.markup_maximum,
        rules.diseconomy_slope,
        rules.gibrat_sigma,
        rules.preferential_attachment_beta,
        rules.preferential_price_elasticity,
        rules.wage_shortage_adjustment,
        rules.wage_downward_drift,
        rules.wage_calvo_probability,
        rules.wage_indexation,
        rules.wage_expected_inflation,
        rules.price_calvo_probability,
        rules.income_propensity,
        rules.wealth_propensity,
        rules.dividend_payout,
        rules.investment_adjustment,
        rules.capital_depreciation,
        rules.annual_tfp_growth,
        rules.annual_tfp_growth_consumption,
        rules.annual_tfp_growth_capital,
        rules.annual_tfp_growth_energy,
        rules.annual_tfp_volatility,
        rules.tfp_learning_theta,
        rules.profit_tax_rate,
        rules.income_tax_rate,
        rules.consumption_tax_rate,
        rules.wealth_tax_rate,
        rules.government_consumption_share,
        rules.government_deficit_target,
        rules.deficit_unemployment_reference,
        rules.deficit_unemployment_cap,
        rules.government_investment_share,
        rules.public_capital_gamma,
        rules.public_capital_depreciation,
        rules.unemployment_benefit_replacement,
        rules.income_allowance,
        rules.wealth_allowance,
        rules.benefit_income_floor,
        rules.minimum_wage,
        rules.job_guarantee_wage_ratio,
        rules.job_guarantee_public_works_share,
        rules.job_guarantee_productivity,
        rules.initial_household_money,
        rules.initial_firm_money,
        rules.initial_capital_firm_money,
        rules.initial_bank_capital,
        rules.initial_consumption_inventory,
        rules.initial_capital_inventory,
        rules.initial_consumption_capital,
        rules.initial_price,
        rules.initial_capital_price,
        rules.initial_wage,
        rules.initial_markup,
        rules.initial_expected_demand,
    };
    if (!all_finite(values) || rules.linear_productivity <= 0.0 ||
        rules.capital_productivity <= 0.0 || rules.total_factor_productivity <= 0.0 ||
        rules.capital_share < 0.0 || rules.capital_share >= 1.0 ||
        rules.capital_output_ratio < 0.0 ||
        rules.markup_minimum > rules.markup_maximum || rules.markup_minimum < 0.0 ||
        rules.annual_tfp_growth <= -1.0 ||
        rules.annual_tfp_growth_consumption <= -1.0 ||
        rules.annual_tfp_growth_capital <= -1.0 ||
        rules.annual_tfp_growth_energy <= -1.0 ||
        rules.annual_tfp_volatility < 0.0 || rules.tfp_learning_theta < 0.0 ||
        static_cast<std::uint8_t>(rules.tfp_law) >
            static_cast<std::uint8_t>(M4TfpLaw::learning) ||
        rules.demand_adjustment < 0.0 ||
        rules.demand_adjustment > 1.0 || rules.income_adjustment < 0.0 ||
        rules.capital_clock_demand_smoothing <= 0.0 ||
        rules.capital_clock_demand_smoothing > 1.0 ||
        rules.income_adjustment > 1.0 || rules.inventory_ratio < 0.0 ||
        rules.inventory_gap_close < 0.0 || rules.inventory_gap_close > 1.0 ||
        rules.markup_adjustment < 0.0 || rules.diseconomy_slope < 0.0 ||
        rules.gibrat_sigma < 0.0 || rules.preferential_attachment_beta < 0.0 ||
        rules.preferential_price_elasticity < 0.0 ||
        rules.wage_shortage_adjustment < 0.0 ||
        rules.wage_downward_drift < 0.0 || rules.income_propensity < 0.0 ||
        rules.wealth_propensity < 0.0 || rules.dividend_payout < 0.0 ||
        rules.dividend_payout > 1.0 || rules.investment_adjustment < 0.0 ||
        rules.capital_depreciation < 0.0 || rules.capital_depreciation > 1.0 ||
        rules.profit_tax_rate < 0.0 || rules.profit_tax_rate > 1.0 ||
        rules.income_tax_rate < 0.0 || rules.income_tax_rate > 1.0 ||
        rules.consumption_tax_rate < 0.0 || rules.consumption_tax_rate > 1.0 ||
        (rules.necessity_consumption_tax_rate.has_value() &&
         (!std::isfinite(*rules.necessity_consumption_tax_rate) ||
          *rules.necessity_consumption_tax_rate < 0.0 ||
          *rules.necessity_consumption_tax_rate > 0.6)) ||
        (rules.luxury_consumption_tax_rate.has_value() &&
         (!std::isfinite(*rules.luxury_consumption_tax_rate) ||
          *rules.luxury_consumption_tax_rate < 0.0 ||
          *rules.luxury_consumption_tax_rate > 0.8)) ||
        rules.wealth_tax_rate < 0.0 || rules.wealth_tax_rate > 1.0 ||
        rules.government_consumption_share < 0.0 ||
        rules.government_deficit_target < 0.0 ||
        rules.deficit_unemployment_reference < 0.0 ||
        rules.deficit_unemployment_cap < 0.0 ||
        rules.government_investment_share < 0.0 || rules.public_capital_gamma < 0.0 ||
        rules.public_capital_depreciation < 0.0 ||
        rules.public_capital_depreciation >= 1.0 ||
        rules.unemployment_benefit_replacement < 0.0 ||
        rules.unemployment_benefit_replacement > 1.0 ||
        rules.government_consumption_share > 1.0 || rules.income_allowance < 0.0 ||
        rules.wealth_allowance < 0.0 || rules.benefit_income_floor < 0.0 ||
        rules.minimum_wage < 0.0 || rules.job_guarantee_wage_ratio < 0.0 ||
        rules.job_guarantee_public_works_share < 0.0 ||
        rules.job_guarantee_public_works_share > 1.0 ||
        rules.job_guarantee_productivity < 0.0 ||
        rules.government_investment_share > 1.0 || rules.initial_price <= 0.0 ||
        rules.initial_capital_price <= 0.0 || rules.initial_wage <= 0.0 ||
        rules.initial_household_money < 0.0 || rules.initial_firm_money < 0.0 ||
        rules.initial_capital_firm_money < 0.0 ||
        rules.initial_bank_capital < 0.0 || rules.initial_consumption_inventory < 0.0 ||
        rules.initial_capital_inventory < 0.0 ||
        rules.initial_consumption_capital < 0.0 ||
        rules.initial_markup < rules.markup_minimum ||
        rules.initial_markup > rules.markup_maximum ||
        rules.initial_expected_demand < 0.0 || rules.wage_calvo_probability < 0.0 ||
        rules.wage_calvo_probability > 1.0 || rules.price_calvo_probability < 0.0 ||
        rules.price_calvo_probability > 1.0 || rules.wage_indexation < 0.0 ||
        rules.wage_indexation > 1.0 || rules.wage_expected_inflation <= -1.0 ||
        rules.market_sample_size == 0) {
        return Status(ErrorCode::invalid_argument, "M4 rules are invalid");
    }
    return Status::success();
}

Status stage_m4_transfer(const core::RootState &state, M4TickScratch &scratch,
                         AccountId source, AccountId destination,
                         double amount) noexcept {
    if (!std::isfinite(amount) || amount < 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "M4 staged transfer amount is invalid");
    }
    return transfer(state, scratch, source, destination, amount,
                    "M4 staged transfer exceeds available money");
}

Status validate_m4_state(const core::RootState &root, const M4Runtime &runtime,
                         Tick tick) noexcept {
    const auto *clearing = root.postings.get(root.institutions.clearing_account);
    if (clearing == nullptr || !clearing->open ||
        clearing->key.kind != core::AccountKind::clearing ||
        clearing->key.owner !=
            core::OwnerId::institutional(core::OwnerKind::institution)) {
        return Status(ErrorCode::invariant_violation, "M4 session identity is invalid");
    }
    bool components_valid = true;
    root.households.for_each_alive(
        [&components_valid](HouseholdId, const core::HouseholdComponent &household) {
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
            components_valid = components_valid && all_finite(values) &&
                               household.income_propensity >= 0.0 &&
                               household.wealth_propensity >= 0.0 &&
                               household.income_adjustment >= 0.0 &&
                               household.income_adjustment <= 1.0 &&
                               household.income_expected >= 0.0 &&
                               household.consumption_budget >= 0.0 &&
                               household.spent >= 0.0 && household.labor_sold >= 0.0;
        });
    std::uint64_t consumption_firms = 0;
    std::uint64_t capital_firms = 0;
    root.firms.for_each_alive([&components_valid, &consumption_firms, &capital_firms](
                                  FirmId, const core::FirmComponent &firm) {
        if (firm.sector == core::FirmSector::consumption) {
            ++consumption_firms;
        } else if (firm.sector == core::FirmSector::capital) {
            ++capital_firms;
        } else if (firm.sector != core::FirmSector::energy &&
                   firm.sector != core::FirmSector::construction) {
            components_valid = false;
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
            firm.attractiveness,
        };
        components_valid =
            components_valid && all_finite(values) &&
            firm.total_factor_productivity > 0.0 && firm.capital_share >= 0.0 &&
            firm.capital_share < 1.0 && firm.capital_output_ratio >= 0.0 &&
            firm.investment_adjustment >= 0.0 && firm.capital_depreciation >= 0.0 &&
            firm.capital_depreciation <= 1.0 && firm.posted_price.value() > 0.0 &&
            firm.posted_wage.value() > 0.0 && firm.demand_expected >= 0.0 &&
            firm.hired_previous >= 0.0 && firm.sales_previous >= 0.0 &&
            firm.rationed_previous >= 0.0;
        components_valid = components_valid &&
                           firm.attractiveness > 0.0;
    });
    const std::array runtime_values{
        runtime.technology_index,
        runtime.technology_index_capital,
        runtime.technology_index_energy,
        runtime.cumulative_sector_output[0],
        runtime.cumulative_sector_output[1],
        runtime.cumulative_sector_output[2],
        runtime.tfp_learning_origin[0],
        runtime.tfp_learning_origin[1],
        runtime.tfp_learning_origin[2],
        runtime.tfp_learning_base[0],
        runtime.tfp_learning_base[1],
        runtime.tfp_learning_base[2],
        runtime.public_capital,
        runtime.public_capital_reference,
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
        runtime.last_metrics.dividends_paid,
        runtime.last_metrics.tax_total,
        runtime.last_metrics.government_spending,
        runtime.last_metrics.government_deficit,
        runtime.last_metrics.public_capital,
        runtime.last_metrics.gross_output_nominal,
        runtime.last_metrics.consumption_output_nominal,
        runtime.last_metrics.capital_output_nominal,
        runtime.last_metrics.consumption_output_real,
        runtime.last_metrics.capital_output_real,
        runtime.last_metrics.inventory_change_nominal,
        runtime.last_metrics.inventory_change_real,
        runtime.last_metrics.fixed_capital_formation_nominal,
        runtime.last_metrics.fixed_capital_formation_real,
        runtime.last_metrics.government_consumption,
        runtime.last_metrics.public_fixed_capital_formation,
        runtime.last_metrics.transfer_payments,
        runtime.last_metrics.tfp_index_consumption,
        runtime.last_metrics.tfp_index_capital,
        runtime.last_metrics.tfp_index_energy,
        runtime.last_metrics.tfp_growth_consumption,
        runtime.last_metrics.tfp_growth_capital,
        runtime.last_metrics.tfp_growth_energy,
        runtime.last_metrics.cumulative_output_consumption,
        runtime.last_metrics.cumulative_output_capital,
        runtime.last_metrics.cumulative_output_energy,
    };
    if (!components_valid || !all_finite(runtime_values) ||
        runtime.technology_index <= 0.0 || runtime.technology_index_capital <= 0.0 ||
        runtime.technology_index_energy <= 0.0 ||
        std::any_of(runtime.cumulative_sector_output.begin(),
                    runtime.cumulative_sector_output.end(),
                    [](double value) { return value < 0.0; }) ||
        std::any_of(runtime.tfp_learning_origin.begin(),
                    runtime.tfp_learning_origin.end(),
                    [](double value) { return value < 0.0; }) ||
        std::any_of(runtime.tfp_learning_base.begin(),
                    runtime.tfp_learning_base.end(),
                    [](double value) { return value < 0.0; }) ||
        runtime.public_capital < 0.0 ||
        runtime.public_capital_reference <= 0.0) {
        return Status(ErrorCode::invariant_violation,
                      "M4 persistent columns are invalid");
    }
    for (const auto &phase : runtime.last_phase_trace) {
        const std::array values{
            phase.money_total,
            phase.goods_total,
            phase.capital_total,
        };
        if (!all_finite(values) ||
            static_cast<std::uint8_t>(phase.phase) >
                static_cast<std::uint8_t>(M4Phase::stage_local_commit)) {
            return Status(ErrorCode::invariant_violation, "M4 phase trace is invalid");
        }
    }
    M4SimulationSpec spec;
    spec.vertical = runtime.vertical;
    spec.economy = root.economy;
    spec.currency = root.currency;
    spec.households = root.households.alive_count();
    spec.consumption_firms = consumption_firms;
    spec.capital_firms = capital_firms;
    spec.settlement_banks = root.banks.alive_count();
    spec.seed = root.seed;
    spec.requested_capabilities = runtime.capability_mask;
    spec.stochastic = runtime.stochastic;
    spec.market_protocol = runtime.market_protocol;
    spec.rules = runtime.rules;
    static_cast<void>(tick);
    return validate_spec(spec);
}

Result<M4Initialization> build_m4_genesis(const M4SimulationSpec &spec) {
    const auto validation = validate_spec(spec);
    if (!validation.ok()) {
        return validation;
    }
    const double opening_money =
        static_cast<double>(spec.households) * spec.rules.initial_household_money +
        static_cast<double>(spec.consumption_firms) *
            spec.rules.initial_firm_money +
        static_cast<double>(spec.capital_firms) *
            spec.rules.initial_capital_firm_money +
        static_cast<double>(spec.settlement_banks) * spec.rules.initial_bank_capital;
    const double opening_capital = spec.vertical == M4Vertical::capital_fiscal
                                       ? static_cast<double>(spec.consumption_firms) *
                                             spec.rules.initial_consumption_capital
                                       : 0.0;
    core::GenesisSpec genesis;
    genesis.vertical = spec.vertical == M4Vertical::cash_loop
                           ? core::GenesisVertical::m4_v0_cash_loop
                           : core::GenesisVertical::m4_v1_capital_fiscal;
    genesis.economy = spec.economy;
    genesis.currency = spec.currency;
    genesis.households = spec.households;
    genesis.consumption_firms = spec.consumption_firms;
    genesis.capital_firms = spec.capital_firms;
    genesis.settlement_banks = spec.settlement_banks;
    genesis.government = spec.vertical == M4Vertical::capital_fiscal;
    genesis.aggregate_opening_money = Money(opening_money);
    genesis.aggregate_opening_capital = Capital(opening_capital);
    genesis.seed = spec.seed;
    genesis.use_per_agent_endowments = true;
    genesis.household_opening_money = Money(spec.rules.initial_household_money);
    genesis.firm_opening_money = Money(spec.rules.initial_firm_money);
    genesis.capital_firm_opening_money =
        Money(spec.rules.initial_capital_firm_money);
    genesis.bank_opening_money = Money(spec.rules.initial_bank_capital);
    genesis.opening_capital_to_consumption_firms = true;
    auto state = core::build_genesis(genesis);
    if (!state.ok()) {
        return state.status();
    }
    auto root = std::move(*state.get_if());
    root.households.for_each_alive(
        [&spec](HouseholdId, core::HouseholdComponent &household) {
            household.income_propensity = spec.rules.income_propensity;
            household.wealth_propensity = spec.rules.wealth_propensity;
            household.income_adjustment = spec.rules.income_adjustment;
            household.income_expected = spec.rules.initial_wage;
            household.income_realized = spec.rules.initial_wage;
        });
    root.firms.for_each_alive([&spec](FirmId, core::FirmComponent &firm) {
        const bool consumption = firm.sector == core::FirmSector::consumption;
        firm.goods_inventory =
            Goods(consumption ? spec.rules.initial_consumption_inventory
                              : spec.rules.initial_capital_inventory);
        firm.productivity = consumption ? spec.rules.linear_productivity
                                        : spec.rules.capital_productivity;
        firm.technology = consumption && spec.vertical == M4Vertical::capital_fiscal
                              ? core::FirmTechnology::cobb_douglas
                              : core::FirmTechnology::linear;
        firm.total_factor_productivity = spec.rules.total_factor_productivity;
        firm.capital_share = spec.rules.capital_share;
        firm.capital_output_ratio = spec.rules.capital_output_ratio;
        firm.investment_adjustment = spec.rules.investment_adjustment;
        firm.capital_depreciation = spec.rules.capital_depreciation;
        firm.demand_adjustment = spec.rules.demand_adjustment;
        firm.inventory_ratio = spec.rules.inventory_ratio;
        firm.markup_adjustment = spec.rules.markup_adjustment;
        firm.markup_minimum = spec.rules.markup_minimum;
        firm.markup_maximum = spec.rules.markup_maximum;
        firm.shortage_adjustment = spec.rules.wage_shortage_adjustment;
        firm.dividend_payout = spec.rules.dividend_payout;
        firm.posted_price = Price(consumption ? spec.rules.initial_price
                                              : spec.rules.initial_capital_price);
        firm.posted_wage = Money(spec.rules.initial_wage);
        firm.markup = spec.rules.initial_markup;
        firm.demand_expected = spec.rules.initial_expected_demand;
        firm.attractiveness = 1.0;
    });
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
    const auto technology_seed = splitmix64(spec.seed + 19'000U);
    runtime.technology_rng_key = {
        static_cast<std::uint32_t>(technology_seed),
        static_cast<std::uint32_t>(technology_seed >> 32U) ^ 0x9e3779b9U,
    };
    runtime.public_capital_reference = std::max(1.0, opening_capital);
    runtime.last_phase_trace.reserve(10);
    runtime.last_metrics.total_money = opening_money;
    return M4Initialization{std::move(root), std::move(runtime)};
}

Result<M4AdvanceResult> advance_ticks(core::RootState &state, M4Runtime &runtime,
                                      M4TickScratch &scratch, Tick &tick,
                                      std::uint64_t count,
                                      const M4AdvanceOptions &options) {
    if (state.transaction_active) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M4 cannot advance during an accounting transaction");
    }
    auto options_status = validate_advance_options(state, options);
    if (!options_status.ok()) {
        return options_status;
    }
    const Tick first = tick;
    if (count == 0) {
        return M4AdvanceResult{
            first, tick, 0, runtime.last_metrics, scratch.capacity_signature(), 0, 0,
        };
    }
    M4AdvanceResult result;
    std::uint64_t transfers = 0;
    std::uint64_t trades = 0;
    double external_units = 0.0;
    double external_value = 0.0;
    for (std::uint64_t index = 0; index < count; ++index) {
        auto current = advance_one(state, runtime, scratch, tick, options, nullptr);
        if (!current.ok()) {
            return current.status();
        }
        result = std::move(*current.get_if());
        transfers += result.transfer_count;
        trades += result.trade_count;
        external_units += result.external_goods_units;
        external_value += result.external_goods_value;
    }
    result.first_tick = first;
    result.next_tick = tick;
    result.advanced_ticks = count;
    result.transfer_count = transfers;
    result.trade_count = trades;
    result.external_goods_units = external_units;
    result.external_goods_value = external_value;
    return result;
}

Result<M4AdvanceResult>
advance_ticks_extended(core::RootState &state, M4Runtime &runtime,
                       M4TickScratch &scratch, Tick &tick, std::uint64_t count,
                       M4TickExtension &extension, const M4AdvanceOptions &options) {
    if (state.transaction_active) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M4 cannot advance during an accounting transaction");
    }
    auto options_status = validate_advance_options(state, options);
    if (!options_status.ok()) {
        return options_status;
    }
    const Tick first = tick;
    if (count == 0) {
        return M4AdvanceResult{
            first, tick, 0, runtime.last_metrics, scratch.capacity_signature(), 0, 0,
        };
    }
    M4AdvanceResult result;
    std::uint64_t transfers = 0;
    std::uint64_t trades = 0;
    double external_units = 0.0;
    double external_value = 0.0;
    for (std::uint64_t index = 0; index < count; ++index) {
        auto current = advance_one(state, runtime, scratch, tick, options, &extension);
        if (!current.ok()) {
            return current.status();
        }
        result = std::move(*current.get_if());
        transfers += result.transfer_count;
        trades += result.trade_count;
        external_units += result.external_goods_units;
        external_value += result.external_goods_value;
    }
    result.first_tick = first;
    result.next_tick = tick;
    result.advanced_ticks = count;
    result.transfer_count = transfers;
    result.trade_count = trades;
    result.external_goods_units = external_units;
    result.external_goods_value = external_value;
    return result;
}

Result<M4AdvanceResult> advance_tick(core::RootState &state, M4Runtime &runtime,
                                     M4TickScratch &scratch, Tick &tick,
                                     const M4AdvanceOptions &options) {
    return advance_ticks(state, runtime, scratch, tick, 1, options);
}

} // namespace macro_sim::simulation
