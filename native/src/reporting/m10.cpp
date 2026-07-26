#include "macro_sim/reporting/m10.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numeric>
#include <utility>

namespace macro_sim::reporting {
namespace {

using simulation::M8Metrics;

constexpr std::array<MetricDescriptor, kM10PublicMetricCount> kDescriptors{{
    {"metric.economy.avg_wage", "currency_per_tick", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.mean_hourly_wage"},
    {"metric.economy.credit_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "m5.total_loan_principal / m4.nominal_output"},
    {"metric.economy.employment", "fte", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.employed_fte"},
    {"metric.economy.energy_price", "currency_per_unit", 1U, MetricTier::causal,
     MetricAggregation::mean, "m8.energy.transaction_price_hold_last"},
    {"metric.economy.energy_subsidy_paid", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m8.energy.subsidy_paid"},
    {"metric.economy.gov_debt_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "government_debt / annualized_daily_nominal_output"},
    {"metric.economy.gov_deficit_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "m4.government_deficit / m4.nominal_output"},
    {"metric.economy.income_gini", "index", 1U, MetricTier::analytic,
     MetricAggregation::last, "gini(live_household_income_realized)"},
    {"metric.economy.inflation", "per_tick", 1U, MetricTier::analytic,
     MetricAggregation::mean, "price_index / previous_price_index - 1"},
    {"metric.economy.n_bank_failures", "count", 1U, MetricTier::causal,
     MetricAggregation::sum, "m5.bank_failures"},
    {"metric.economy.policy_rate", "rate_per_tick", 1U, MetricTier::causal,
     MetricAggregation::last, "m5.policy_rate"},
    {"metric.economy.population_alive", "persons", 1U, MetricTier::causal,
     MetricAggregation::last, "m7.population"},
    {"metric.economy.poverty_rate", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "share_below_half_median_household_consumption"},
    {"metric.economy.price_index", "index", 1U, MetricTier::causal,
     MetricAggregation::mean, "m4.price_index"},
    {"metric.economy.real_output", "goods_units", 1U, MetricTier::causal,
     MetricAggregation::sum, "m4.real_output"},
    {"metric.economy.unemployment_rate", "share", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.unemployment_rate"},
    {"metric.world.current_account", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.current_account"},
    {"metric.world.e", "local_currency_per_numeraire", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.exchange_rate"},
    {"metric.world.export_shipped_volume", "goods_units", 1U,
     MetricTier::causal, MetricAggregation::sum, "m9.external.exports_volume"},
    {"metric.world.import_volume", "goods_units", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.imports_volume"},
    {"metric.world.migrant_stock", "persons", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.migrant_stock_abroad"},
    {"metric.world.nfa", "currency", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.net_foreign_assets"},
    {"metric.world.remittances", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.remittances_received"},
}};

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

[[nodiscard]] double gini(std::vector<double> values) {
    if (values.empty()) {
        return 0.0;
    }
    for (auto &value : values) {
        value = std::max(0.0, value);
    }
    std::sort(values.begin(), values.end());
    const double total = std::accumulate(values.begin(), values.end(), 0.0);
    if (total <= 1.0e-12) {
        return 0.0;
    }
    double weighted = 0.0;
    for (std::size_t index = 0; index < values.size(); ++index) {
        weighted += static_cast<double>(index + 1U) * values[index];
    }
    const double count = static_cast<double>(values.size());
    return std::clamp(2.0 * weighted / (count * total) -
                          (count + 1.0) / count,
                      0.0, 1.0);
}

[[nodiscard]] double median(std::vector<double> values) {
    if (values.empty()) {
        return 0.0;
    }
    const std::size_t middle = values.size() / 2U;
    std::nth_element(values.begin(),
                     values.begin() + static_cast<std::ptrdiff_t>(middle),
                     values.end());
    const double upper = values[middle];
    if (values.size() % 2U != 0U) {
        return upper;
    }
    const auto lower = std::max_element(
        values.begin(), values.begin() + static_cast<std::ptrdiff_t>(middle));
    return 0.5 * (*lower + upper);
}

void set(MetricFrame &frame, std::size_t economy, std::size_t metric,
         double value) {
    const std::size_t offset = economy * kM10PublicMetricCount + metric;
    frame.values[offset] = value;
    frame.valid[offset] = finite(value) ? 1U : 0U;
}

[[nodiscard]] const simulation::M4Metrics &m4(const M8Metrics &metrics) noexcept {
    return metrics.economy.economy.economy.economy;
}

[[nodiscard]] const simulation::M5Metrics &m5(const M8Metrics &metrics) noexcept {
    return metrics.economy.economy.economy;
}

[[nodiscard]] const simulation::M7Metrics &m7(const M8Metrics &metrics) noexcept {
    return metrics.economy;
}

} // namespace

Result<double> MetricFrame::value(std::size_t economy,
                                  std::size_t metric) const noexcept {
    if (economy >= economy_count || metric >= kM10PublicMetricCount) {
        return Status(ErrorCode::out_of_range, "metric frame index is out of range");
    }
    const std::size_t offset = economy * kM10PublicMetricCount + metric;
    if (offset >= valid.size() || offset >= values.size() || valid[offset] == 0U) {
        return Status(ErrorCode::not_found, "metric frame value is unavailable");
    }
    return values[offset];
}

MetricHistory::MetricHistory(std::size_t economy_count, std::size_t metric_count,
                             std::size_t capacity_frames)
    : economy_count_(economy_count), metric_count_(metric_count),
      capacity_frames_(capacity_frames), ticks_(capacity_frames),
      values_(capacity_frames * economy_count * metric_count),
      valid_(capacity_frames * economy_count * metric_count) {}

Result<MetricHistory>
MetricHistory::restore(std::size_t economy_count, std::size_t metric_count,
                       std::size_t capacity_frames,
                       std::uint64_t first_sequence,
                       std::span<const MetricFrame> frames) {
    if (economy_count == 0U || metric_count == 0U ||
        capacity_frames == 0U || frames.empty() ||
        frames.size() > capacity_frames ||
        first_sequence >
            std::numeric_limits<std::uint64_t>::max() - frames.size()) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history restore shape is invalid");
    }
    MetricHistory result(economy_count, metric_count, capacity_frames);
    result.next_sequence_ = first_sequence;
    for (const auto &frame : frames) {
        auto status = result.append(frame);
        if (!status.ok()) {
            return status;
        }
    }
    return result;
}

Status MetricHistory::append(const MetricFrame &frame) {
    if (capacity_frames_ == 0U || frame.economy_count != economy_count_ ||
        frame.values.size() != frame_width() ||
        frame.valid.size() != frame_width()) {
        return Status(ErrorCode::contract_violation,
                      "metric history frame shape does not match");
    }
    const std::size_t slot =
        static_cast<std::size_t>(next_sequence_ % capacity_frames_);
    const std::size_t offset = slot * frame_width();
    ticks_[slot] = frame.tick;
    std::copy(frame.values.begin(), frame.values.end(), values_.begin() +
                                                        static_cast<std::ptrdiff_t>(
                                                            offset));
    std::copy(frame.valid.begin(), frame.valid.end(), valid_.begin() +
                                                      static_cast<std::ptrdiff_t>(
                                                          offset));
    ++next_sequence_;
    size_ = std::min(capacity_frames_, size_ + 1U);
    return Status::success();
}

Result<MetricHistoryPage>
MetricHistory::page(std::uint64_t first_sequence,
                    std::size_t maximum_frames) const {
    if (first_sequence < oldest_sequence() || first_sequence > next_sequence_) {
        return Status(ErrorCode::out_of_range,
                      "metric history cursor is outside the retained window");
    }
    MetricHistoryPage result;
    result.first_sequence = first_sequence;
    const std::uint64_t available = next_sequence_ - first_sequence;
    const std::size_t count = static_cast<std::size_t>(
        std::min<std::uint64_t>(available, maximum_frames));
    result.frames.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint64_t sequence = first_sequence + index;
        const std::size_t slot =
            static_cast<std::size_t>(sequence % capacity_frames_);
        const std::size_t offset = slot * frame_width();
        MetricFrame frame;
        frame.tick = ticks_[slot];
        frame.economy_count = economy_count_;
        frame.values.assign(
            values_.begin() + static_cast<std::ptrdiff_t>(offset),
            values_.begin() + static_cast<std::ptrdiff_t>(offset + frame_width()));
        frame.valid.assign(
            valid_.begin() + static_cast<std::ptrdiff_t>(offset),
            valid_.begin() + static_cast<std::ptrdiff_t>(offset + frame_width()));
        result.frames.push_back(std::move(frame));
    }
    result.next_sequence = first_sequence + count;
    return result;
}

std::uint64_t MetricHistory::retained_bytes() const noexcept {
    return static_cast<std::uint64_t>(ticks_.capacity()) * sizeof(Tick) +
           static_cast<std::uint64_t>(values_.capacity()) * sizeof(double) +
           static_cast<std::uint64_t>(valid_.capacity()) * sizeof(std::uint8_t);
}

MetricPipeline::MetricPipeline(std::size_t economy_count,
                               std::size_t history_capacity_frames)
    : history_(economy_count, kM10PublicMetricCount, history_capacity_frames) {}

Status MetricPipeline::capture(const simulation::M9World &world) {
    const MetricFrame *previous = captured_ ? &current_ : nullptr;
    auto built = build_public_metric_frame(world, previous);
    if (!built.ok()) {
        return built.status();
    }
    return commit(std::move(*built.get_if()));
}

Status MetricPipeline::commit(MetricFrame frame) {
    auto status = history_.append(frame);
    if (!status.ok()) {
        return status;
    }
    current_ = std::move(frame);
    captured_ = true;
    return Status::success();
}

Result<MetricPipeline> MetricPipeline::restore(MetricHistory history) {
    if (history.size() == 0U) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history cannot restore empty");
    }
    auto last = history.page(history.next_sequence() - 1U, 1U);
    if (!last.ok() || last.get_if()->frames.size() != 1U) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history last frame is unavailable");
    }
    MetricPipeline result;
    result.current_ = std::move(last.get_if()->frames.front());
    result.history_ = std::move(history);
    result.captured_ = true;
    return result;
}

std::span<const MetricDescriptor> public_metric_descriptors() noexcept {
    return kDescriptors;
}

Result<MetricFrame>
build_public_metric_frame(const simulation::M9World &world,
                          const MetricFrame *previous) {
    const auto &metrics = world.last_metrics();
    if (metrics.domestic.size() != world.economy_count() ||
        metrics.external.size() != world.economy_count()) {
        return Status(ErrorCode::invariant_violation,
                      "M10 metric source dimensions disagree");
    }
    if (previous != nullptr && previous->economy_count != world.economy_count()) {
        return Status(ErrorCode::contract_violation,
                      "M10 previous metric frame shape disagrees");
    }

    MetricFrame frame;
    frame.tick = world.tick();
    frame.economy_count = world.economy_count();
    frame.values.assign(frame.economy_count * kM10PublicMetricCount,
                        std::numeric_limits<double>::quiet_NaN());
    frame.valid.assign(frame.values.size(), 0U);

    for (std::size_t economy = 0; economy < frame.economy_count; ++economy) {
        const auto &domestic = metrics.domestic[economy];
        const auto &external = metrics.external[economy];
        const auto &real = m4(domestic);
        const auto &monetary = m5(domestic);
        const auto &population = m7(domestic);
        const auto *root = world.economy_root(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *financial = world.economy_financial_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *runtime = world.economy_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        if (root == nullptr || financial == nullptr || runtime == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "M10 metric source economy is unavailable");
        }

        std::vector<double> incomes;
        std::vector<double> consumption;
        incomes.reserve(root->households.alive_count());
        consumption.reserve(root->households.alive_count());
        root->households.for_each_alive(
            [&](HouseholdId, const core::HouseholdComponent &household) {
                incomes.push_back(household.income_realized);
                consumption.push_back(household.spent);
            });
        const double consumption_median = median(consumption);
        const double poverty_line = 0.5 * consumption_median;
        const double poverty =
            poverty_line > 1.0e-12 && !consumption.empty()
                ? static_cast<double>(std::count_if(
                      consumption.begin(), consumption.end(),
                      [poverty_line](double value) { return value < poverty_line; })) /
                      static_cast<double>(consumption.size())
                : 0.0;
        const double nominal_output = real.nominal_output;
        const auto treasury_balance =
            root->postings.balance(root->institutions.treasury_account);
        if (!treasury_balance.ok()) {
            return treasury_balance.status();
        }
        const double government_debt =
            financial->securities.total_bond_face().value() -
            treasury_balance.get_if()->value();

        set(frame, economy, 0U, population.mean_hourly_wage);
        set(frame, economy, 1U,
            nominal_output > 1.0e-12
                ? monetary.total_loan_principal / nominal_output
                : 0.0);
        set(frame, economy, 2U, population.employed_fte);
        set(frame, economy, 3U,
            domestic.energy.transaction_price > 1.0e-12
                ? domestic.energy.transaction_price
                : runtime->energy_price);
        set(frame, economy, 4U, domestic.energy.subsidy_paid);
        set(frame, economy, 5U,
            nominal_output > 1.0e-12
                ? government_debt / (365.0 * nominal_output)
                : 0.0);
        set(frame, economy, 6U,
            nominal_output > 1.0e-12
                ? real.government_deficit / nominal_output
                : 0.0);
        set(frame, economy, 7U, gini(std::move(incomes)));
        double inflation = 0.0;
        if (previous != nullptr) {
            const auto previous_price = previous->value(economy, 13U);
            if (previous_price.ok() && *previous_price.get_if() > 1.0e-12) {
                inflation = real.price_index / *previous_price.get_if() - 1.0;
            }
        }
        set(frame, economy, 8U, inflation);
        set(frame, economy, 9U, static_cast<double>(monetary.bank_failures));
        set(frame, economy, 10U, monetary.policy_rate);
        set(frame, economy, 11U, static_cast<double>(population.population));
        set(frame, economy, 12U, poverty);
        set(frame, economy, 13U, real.price_index);
        set(frame, economy, 14U, real.real_output);
        set(frame, economy, 15U, population.unemployment_rate);
        set(frame, economy, 16U, external.current_account);
        set(frame, economy, 17U, external.exchange_rate);
        set(frame, economy, 18U, external.exports_volume);
        set(frame, economy, 19U, external.imports_volume);
        set(frame, economy, 20U, external.migrant_stock_abroad);
        set(frame, economy, 21U, external.net_foreign_assets);
        set(frame, economy, 22U, external.remittances_received);
    }
    return frame;
}

} // namespace macro_sim::reporting
