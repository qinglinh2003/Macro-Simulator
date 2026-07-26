#ifndef MACRO_SIM_REPORTING_M10_HPP
#define MACRO_SIM_REPORTING_M10_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::reporting {

// Forty-one native source series back the forty-two institutional observation
// series.  ``oracle_daily_output`` deliberately aliases the same committed
// ``real_output`` source; access control belongs to the release layer rather
// than to a duplicate economic measurement.
inline constexpr std::size_t kM10PublicMetricCount = 41U;

enum class MetricTier : std::uint8_t {
    causal = 0,
    release = 1,
    frontend = 2,
    analytic = 3,
    probe = 4,
};

enum class MetricAggregation : std::uint8_t {
    last = 0,
    mean = 1,
    sum = 2,
};

struct MetricDescriptor final {
    std::string_view stable_id;
    std::string_view unit;
    std::uint32_t cadence_ticks{1};
    MetricTier tier{MetricTier::causal};
    MetricAggregation aggregation{MetricAggregation::last};
    std::string_view parity_rule;
};

struct MetricFrame final {
    Tick tick{};
    std::size_t economy_count{0};
    std::vector<double> values;
    std::vector<std::uint8_t> valid;

    [[nodiscard]] Result<double> value(std::size_t economy,
                                       std::size_t metric) const noexcept;
};

struct MetricHistoryPage final {
    std::uint64_t first_sequence{0};
    std::uint64_t next_sequence{0};
    std::vector<MetricFrame> frames;
};

class MetricHistory final {
  public:
    MetricHistory() = default;
    MetricHistory(std::size_t economy_count, std::size_t metric_count,
                  std::size_t capacity_frames);

    [[nodiscard]] static Result<MetricHistory>
    restore(std::size_t economy_count, std::size_t metric_count,
            std::size_t capacity_frames, std::uint64_t first_sequence,
            std::span<const MetricFrame> frames);
    [[nodiscard]] Status append(const MetricFrame &frame);
    [[nodiscard]] Result<MetricHistoryPage>
    page(std::uint64_t first_sequence, std::size_t maximum_frames) const;

    [[nodiscard]] std::size_t economy_count() const noexcept {
        return economy_count_;
    }
    [[nodiscard]] std::size_t metric_count() const noexcept {
        return metric_count_;
    }
    [[nodiscard]] std::size_t capacity() const noexcept {
        return capacity_frames_;
    }
    [[nodiscard]] std::size_t size() const noexcept { return size_; }
    [[nodiscard]] std::uint64_t oldest_sequence() const noexcept {
        return next_sequence_ - size_;
    }
    [[nodiscard]] std::uint64_t next_sequence() const noexcept {
        return next_sequence_;
    }
    [[nodiscard]] std::uint64_t retained_bytes() const noexcept;

  private:
    [[nodiscard]] std::size_t frame_width() const noexcept {
        return economy_count_ * metric_count_;
    }

    std::size_t economy_count_{0};
    std::size_t metric_count_{0};
    std::size_t capacity_frames_{0};
    std::size_t size_{0};
    std::uint64_t next_sequence_{0};
    std::vector<Tick> ticks_;
    std::vector<double> values_;
    std::vector<std::uint8_t> valid_;
};

class MetricPipeline final {
  public:
    MetricPipeline() = default;
    MetricPipeline(std::size_t economy_count,
                   std::size_t history_capacity_frames);

    [[nodiscard]] Status capture(const simulation::M9World &world);
    [[nodiscard]] Status commit(MetricFrame frame);
    [[nodiscard]] static Result<MetricPipeline>
    restore(MetricHistory history);
    [[nodiscard]] const MetricFrame &current() const noexcept { return current_; }
    [[nodiscard]] const MetricHistory &history() const noexcept {
        return history_;
    }
    [[nodiscard]] MetricHistory &history() noexcept { return history_; }

  private:
    MetricFrame current_{};
    MetricHistory history_{};
    bool captured_{false};
};

[[nodiscard]] std::span<const MetricDescriptor> public_metric_descriptors() noexcept;
[[nodiscard]] Result<std::size_t>
public_metric_index(std::string_view stable_id) noexcept;
[[nodiscard]] Result<MetricFrame>
build_public_metric_frame(const simulation::M9World &world,
                          const MetricFrame *previous = nullptr);

} // namespace macro_sim::reporting

#endif
