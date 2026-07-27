#ifndef MACRO_SIM_CONTROL_M11_KERNEL_HPP
#define MACRO_SIM_CONTROL_M11_KERNEL_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/control/m11_policy.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::control {

inline constexpr std::size_t kM11SeatCount = 5U;
inline constexpr std::size_t kM11DecisionGroupCount = 11U;
inline constexpr std::size_t kM11DefaultTriggerCount = 8U;
inline constexpr std::size_t kM11MaximumControllerEvents = 1U << 20U;
inline constexpr std::size_t kM11MaximumControllerReleases = 1U << 20U;

inline constexpr std::array<std::string_view, kM11SeatCount> kM11Seats{{
    "central_bank",
    "energy",
    "external_affairs",
    "regulator",
    "treasury",
}};

inline constexpr std::array<std::string_view, kM11DecisionGroupCount>
    kM11DecisionGroups{{
        "monetary_stance",
        "liquidity_operations",
        "fiscal_stance",
        "tax_and_transfers",
        "debt_management",
        "macroprudential",
        "structural_law",
        "trade_and_migration",
        "fx_operations",
        "energy_operations",
        "energy_structure",
    }};

[[nodiscard]] bool m11_valid_seat(std::string_view seat) noexcept;
[[nodiscard]] bool m11_valid_decision_group(std::string_view decision_group) noexcept;

struct M11CalendarSpec final {
    std::string decision_group;
    std::uint32_t period_ticks{91U};
    std::uint32_t offset_ticks{0U};
    std::uint32_t window_ticks{1U};
    double administrative_capacity{20.0};

    bool operator==(const M11CalendarSpec &) const = default;
};

enum class M11TriggerDirection : std::uint8_t {
    above = 0,
    below = 1,
};

struct M11TriggerSpec final {
    std::string trigger_id;
    std::string series_id;
    double enter_threshold{0.0};
    double exit_threshold{0.0};
    M11TriggerDirection direction{M11TriggerDirection::above};
    std::uint32_t minimum_persistence_ticks{1U};
    std::uint32_t cooldown_ticks{30U};
    std::uint32_t context_expiry_ticks{1U};
    std::vector<std::string> authorized_seats;
    std::string decision_group{"emergency"};

    bool operator==(const M11TriggerSpec &) const = default;
};

struct M11TriggerState final {
    EconomyId economy{};
    std::string trigger_id;
    bool active{false};
    std::uint32_t persistence_ticks{0U};
    Tick cooldown_until{};

    bool operator==(const M11TriggerState &) const = default;
};

struct M11TriggerNotice final {
    std::string trigger_id;
    EconomyId economy{};
    std::vector<std::string> seats;
    std::string decision_group;
    Tick expires_at{};
    double value{0.0};

    bool operator==(const M11TriggerNotice &) const = default;
};

struct M11MetricSample final {
    std::string series_id;
    std::optional<double> value{};

    bool operator==(const M11MetricSample &) const = default;
};

[[nodiscard]] std::vector<M11CalendarSpec> m11_default_calendars();
[[nodiscard]] std::vector<M11TriggerSpec> m11_default_triggers();
[[nodiscard]] Status validate_m11_calendar(const M11CalendarSpec &calendar) noexcept;
[[nodiscard]] Status validate_m11_trigger(const M11TriggerSpec &trigger) noexcept;

class M11DecisionScheduler final {
  public:
    [[nodiscard]] static Result<M11DecisionScheduler>
    create(std::vector<M11CalendarSpec> calendars = m11_default_calendars(),
           std::vector<M11TriggerSpec> triggers = m11_default_triggers());

    [[nodiscard]] const std::vector<M11CalendarSpec> &calendars() const noexcept {
        return calendars_;
    }
    [[nodiscard]] const std::vector<M11TriggerSpec> &triggers() const noexcept {
        return triggers_;
    }
    [[nodiscard]] const std::vector<M11TriggerState> &trigger_states() const noexcept {
        return trigger_states_;
    }
    [[nodiscard]] bool due(std::string_view decision_group, Tick tick,
                           EconomyId economy = EconomyId{}) const noexcept;
    [[nodiscard]] Result<double>
    administrative_capacity(std::string_view decision_group) const noexcept;
    [[nodiscard]] Result<std::vector<M11TriggerNotice>>
    evaluate_triggers(Tick boundary, EconomyId economy,
                      std::span<const M11MetricSample> metrics);
    [[nodiscard]] Status restore_trigger_states(std::vector<M11TriggerState> states,
                                                std::size_t economy_count);

  private:
    M11DecisionScheduler(std::vector<M11CalendarSpec> calendars,
                         std::vector<M11TriggerSpec> triggers)
        : calendars_(std::move(calendars)), triggers_(std::move(triggers)) {}

    std::vector<M11CalendarSpec> calendars_;
    std::vector<M11TriggerSpec> triggers_;
    std::vector<M11TriggerState> trigger_states_;
};

struct M11CostWeights final {
    double fixed{0.0};
    double linear{1.0};
    double quadratic{0.0};

    bool operator==(const M11CostWeights &) const = default;
};

struct M11AdjustmentCostSpec final {
    M11CostWeights ordinary{0.05, 0.2, 0.02};
    M11CostWeights major{0.5, 0.4, 0.05};
    M11CostWeights regime_switch{2.0, 0.5, 0.0};
    M11CostWeights operational{0.02, 0.05, 0.0};
    double proposal_administrative_overhead{0.25};
    double emergency_premium{1.5};
    double refund_on_cancel{1.0};
    double refund_on_supersede{1.0};
    double refund_on_failed_execution{1.0};

    bool operator==(const M11AdjustmentCostSpec &) const = default;
};

struct M11PolicyChange final {
    const PolicyLeverDescriptor *lever{nullptr};
    PolicyValue old_value{};
    PolicyValue new_value{};
};

[[nodiscard]] Status validate_m11_cost_spec(const M11AdjustmentCostSpec &spec) noexcept;
[[nodiscard]] Result<double>
m11_adjustment_cost(const M11AdjustmentCostSpec &spec,
                    std::span<const M11PolicyChange> changes, bool emergency) noexcept;
[[nodiscard]] Result<double>
m11_administrative_cost(const M11AdjustmentCostSpec &spec,
                        std::span<const M11PolicyChange> changes) noexcept;

enum class M11EventVisibility : std::uint8_t {
    public_record = 0,
    institution = 1,
    privileged_audit = 2,
};

struct M11ControllerEvent final {
    std::uint64_t sequence{0U};
    Tick boundary{};
    std::string event_type;
    std::string operation_id;
    std::string actor;
    std::string canonical_payload;
    M11EventVisibility visibility{M11EventVisibility::institution};
    core::StateDigest prior_hash{};
    core::StateDigest hash{};

    bool operator==(const M11ControllerEvent &) const = default;
};

class M11EventStream final {
  public:
    explicit M11EventStream(std::size_t maximum_events = kM11MaximumControllerEvents)
        : maximum_events_(maximum_events) {}

    [[nodiscard]] std::uint64_t next_sequence() const noexcept {
        return next_sequence_;
    }
    [[nodiscard]] const core::StateDigest &head_hash() const noexcept {
        return head_hash_;
    }
    [[nodiscard]] std::span<const M11ControllerEvent> events() const noexcept {
        return events_;
    }
    [[nodiscard]] Result<M11ControllerEvent>
    append(Tick boundary, std::string event_type, std::string operation_id,
           std::string actor, std::string canonical_payload,
           M11EventVisibility visibility);
    [[nodiscard]] Result<std::vector<M11ControllerEvent>>
    page(std::uint64_t first_sequence, std::size_t maximum_rows,
         M11EventVisibility maximum_visibility) const;
    [[nodiscard]] Status restore(std::vector<M11ControllerEvent> events,
                                 std::uint64_t next_sequence,
                                 core::StateDigest head_hash);

  private:
    std::size_t maximum_events_{kM11MaximumControllerEvents};
    std::uint64_t next_sequence_{0U};
    core::StateDigest head_hash_{};
    std::vector<M11ControllerEvent> events_;
};

struct M11ReleaseRecord final {
    std::uint64_t sequence{0U};
    EconomyId economy{};
    std::string series_id;
    Tick observed_at{};
    Tick released_at{};
    std::uint32_t revision{0U};
    std::optional<double> value{};
    std::uint64_t source_event_sequence{0U};

    bool operator==(const M11ReleaseRecord &) const = default;
};

class M11ReleaseStream final {
  public:
    explicit M11ReleaseStream(
        std::size_t maximum_releases = kM11MaximumControllerReleases)
        : maximum_releases_(maximum_releases) {}

    [[nodiscard]] std::uint64_t next_sequence() const noexcept {
        return next_sequence_;
    }
    [[nodiscard]] std::span<const M11ReleaseRecord> releases() const noexcept {
        return releases_;
    }
    [[nodiscard]] Result<M11ReleaseRecord>
    append(EconomyId economy, std::string series_id, Tick observed_at, Tick released_at,
           std::uint32_t revision, std::optional<double> value,
           std::uint64_t source_event_sequence);
    [[nodiscard]] Result<std::vector<M11ReleaseRecord>>
    page(std::uint64_t first_sequence, std::size_t maximum_rows,
         Tick released_through) const;
    [[nodiscard]] Status restore(std::vector<M11ReleaseRecord> releases,
                                 std::uint64_t next_sequence);

  private:
    std::size_t maximum_releases_{kM11MaximumControllerReleases};
    std::uint64_t next_sequence_{0U};
    std::vector<M11ReleaseRecord> releases_;
};

} // namespace macro_sim::control

#endif
