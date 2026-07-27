#include "macro_sim/control/m11_kernel.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace macro_sim::control {
namespace {

constexpr std::size_t kMaximumStableIdBytes = 128U;
constexpr std::size_t kMaximumActorBytes = 256U;
constexpr std::size_t kMaximumEventPayloadBytes = std::size_t{4} * 1024U * 1024U;

[[nodiscard]] bool valid_stable_id(std::string_view value) noexcept {
    if (value.empty() || value.size() > kMaximumStableIdBytes) {
        return false;
    }
    return std::all_of(value.begin(), value.end(), [](char character) {
        const auto byte = static_cast<unsigned char>(character);
        return byte >= 0x21U && byte <= 0x7eU;
    });
}

[[nodiscard]] bool valid_actor(std::string_view value) noexcept {
    return !value.empty() && value.size() <= kMaximumActorBytes &&
           value.find('\0') == std::string_view::npos;
}

void append_u32(std::vector<std::uint8_t> &bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_string(std::vector<std::uint8_t> &bytes, std::string_view value) {
    append_u64(bytes, static_cast<std::uint64_t>(value.size()));
    bytes.insert(bytes.end(), value.begin(), value.end());
}

[[nodiscard]] core::StateDigest event_hash(const M11ControllerEvent &event) noexcept {
    std::vector<std::uint8_t> bytes;
    bytes.reserve(128U + event.event_type.size() + event.operation_id.size() +
                  event.actor.size() + event.canonical_payload.size());
    bytes.insert(bytes.end(), event.prior_hash.bytes.begin(),
                 event.prior_hash.bytes.end());
    append_u64(bytes, event.sequence);
    append_u64(bytes, event.boundary.value());
    append_string(bytes, event.event_type);
    append_string(bytes, event.operation_id);
    append_string(bytes, event.actor);
    append_string(bytes, event.canonical_payload);
    append_u32(bytes, static_cast<std::uint32_t>(event.visibility));
    return core::sha256_digest(bytes);
}

[[nodiscard]] const M11CalendarSpec *
find_calendar(std::span<const M11CalendarSpec> calendars,
              std::string_view decision_group) noexcept {
    const auto found =
        std::lower_bound(calendars.begin(), calendars.end(), decision_group,
                         [](const M11CalendarSpec &calendar, std::string_view name) {
                             return calendar.decision_group < name;
                         });
    return found == calendars.end() || found->decision_group != decision_group
               ? nullptr
               : &*found;
}

[[nodiscard]] const M11TriggerSpec *
find_trigger(std::span<const M11TriggerSpec> triggers,
             std::string_view trigger_id) noexcept {
    const auto found =
        std::lower_bound(triggers.begin(), triggers.end(), trigger_id,
                         [](const M11TriggerSpec &trigger, std::string_view name) {
                             return trigger.trigger_id < name;
                         });
    return found == triggers.end() || found->trigger_id != trigger_id ? nullptr
                                                                      : &*found;
}

[[nodiscard]] M11TriggerState *
find_trigger_state(std::vector<M11TriggerState> &states, EconomyId economy,
                   std::string_view trigger_id) noexcept {
    const auto key = std::pair{economy.value(), trigger_id};
    const auto found = std::lower_bound(
        states.begin(), states.end(), key,
        [](const M11TriggerState &state, const auto &candidate) {
            return std::pair{state.economy.value(),
                             std::string_view(state.trigger_id)} < candidate;
        });
    if (found != states.end() && found->economy == economy &&
        found->trigger_id == trigger_id) {
        return &*found;
    }
    const auto offset = static_cast<std::size_t>(std::distance(states.begin(), found));
    states.insert(found, M11TriggerState{economy, std::string(trigger_id)});
    return &states[offset];
}

[[nodiscard]] std::optional<double>
metric_value(std::span<const M11MetricSample> metrics,
             std::string_view series_id) noexcept {
    const auto found = std::find_if(metrics.begin(), metrics.end(),
                                    [series_id](const M11MetricSample &sample) {
                                        return sample.series_id == series_id;
                                    });
    return found == metrics.end() ? std::optional<double>{} : found->value;
}

[[nodiscard]] const M11CostWeights *cost_weights(const M11AdjustmentCostSpec &spec,
                                                 std::string_view cost_class) noexcept {
    if (cost_class == "ordinary") {
        return &spec.ordinary;
    }
    if (cost_class == "major") {
        return &spec.major;
    }
    if (cost_class == "regime_switch") {
        return &spec.regime_switch;
    }
    if (cost_class == "operational") {
        return &spec.operational;
    }
    return nullptr;
}

[[nodiscard]] bool finite_non_negative(double value) noexcept {
    return std::isfinite(value) && value >= 0.0;
}

[[nodiscard]] Status validate_weights(const M11CostWeights &weights) noexcept {
    if (!finite_non_negative(weights.fixed) || !finite_non_negative(weights.linear) ||
        !finite_non_negative(weights.quadratic) ||
        (weights.fixed == 0.0 && weights.linear == 0.0)) {
        return Status(ErrorCode::contract_violation,
                      "M11 adjustment cost weights are invalid");
    }
    return Status::success();
}

[[nodiscard]] bool release_key_less(const M11ReleaseRecord &left,
                                    const M11ReleaseRecord &right) noexcept {
    if (left.sequence != right.sequence) {
        return left.sequence < right.sequence;
    }
    if (left.economy != right.economy) {
        return left.economy < right.economy;
    }
    return left.series_id < right.series_id;
}

} // namespace

bool m11_valid_seat(std::string_view seat) noexcept {
    return std::binary_search(kM11Seats.begin(), kM11Seats.end(), seat);
}

bool m11_valid_decision_group(std::string_view decision_group) noexcept {
    return std::find(kM11DecisionGroups.begin(), kM11DecisionGroups.end(),
                     decision_group) != kM11DecisionGroups.end();
}

std::vector<M11CalendarSpec> m11_default_calendars() {
    return {
        {"monetary_stance", 45U, 0U, 1U, 12.0},
        {"liquidity_operations", 45U, 0U, 1U, 10.0},
        {"fiscal_stance", 91U, 0U, 1U, 18.0},
        {"tax_and_transfers", 365U, 0U, 1U, 25.0},
        {"debt_management", 91U, 0U, 1U, 12.0},
        {"macroprudential", 91U, 0U, 1U, 20.0},
        {"structural_law", 365U, 0U, 1U, 30.0},
        {"trade_and_migration", 91U, 0U, 1U, 18.0},
        {"fx_operations", 45U, 0U, 1U, 12.0},
        {"energy_operations", 91U, 0U, 1U, 16.0},
        {"energy_structure", 365U, 0U, 1U, 20.0},
    };
}

std::vector<M11TriggerSpec> m11_default_triggers() {
    return {
        {"bank_liquidity_stress",
         "reserve_floor_breach_share",
         0.10,
         0.02,
         M11TriggerDirection::above,
         2U,
         30U,
         1U,
         {"central_bank", "regulator"},
         "emergency"},
        {"bank_capital_stress",
         "near_failure_bank_count",
         0.5,
         0.0,
         M11TriggerDirection::above,
         1U,
         30U,
         1U,
         {"central_bank", "regulator"},
         "emergency"},
        {"energy_shortage",
         "energy_unfilled",
         1.0,
         0.1,
         M11TriggerDirection::above,
         2U,
         14U,
         1U,
         {"energy", "treasury"},
         "emergency"},
        {"exogenous_supply_crisis",
         "shock_supply_severity",
         0.20,
         0.05,
         M11TriggerDirection::above,
         1U,
         30U,
         1U,
         {"central_bank", "treasury"},
         "emergency"},
        {"exogenous_energy_crisis",
         "shock_energy_severity",
         0.20,
         0.05,
         M11TriggerDirection::above,
         1U,
         14U,
         1U,
         {"energy", "treasury"},
         "emergency"},
        {"exogenous_financial_crisis",
         "shock_financial_severity",
         0.20,
         0.05,
         M11TriggerDirection::above,
         1U,
         30U,
         1U,
         {"central_bank", "regulator", "treasury"},
         "emergency"},
        {"exogenous_trade_crisis",
         "shock_trade_severity",
         0.20,
         0.05,
         M11TriggerDirection::above,
         1U,
         30U,
         1U,
         {"external_affairs", "treasury"},
         "emergency"},
        {"exogenous_demand_crisis",
         "shock_demand_severity",
         0.20,
         0.05,
         M11TriggerDirection::above,
         1U,
         30U,
         1U,
         {"central_bank", "treasury"},
         "emergency"},
    };
}

Status validate_m11_calendar(const M11CalendarSpec &calendar) noexcept {
    if (!m11_valid_decision_group(calendar.decision_group) ||
        calendar.period_ticks == 0U || calendar.window_ticks == 0U ||
        calendar.window_ticks > calendar.period_ticks ||
        calendar.offset_ticks >= calendar.period_ticks ||
        !finite_non_negative(calendar.administrative_capacity)) {
        return Status(ErrorCode::contract_violation,
                      "M11 decision calendar is invalid");
    }
    return Status::success();
}

Status validate_m11_trigger(const M11TriggerSpec &trigger) noexcept {
    if (!valid_stable_id(trigger.trigger_id) || !valid_stable_id(trigger.series_id) ||
        trigger.minimum_persistence_ticks == 0U || trigger.context_expiry_ticks == 0U ||
        !std::isfinite(trigger.enter_threshold) ||
        !std::isfinite(trigger.exit_threshold) || trigger.authorized_seats.empty() ||
        !valid_stable_id(trigger.decision_group)) {
        return Status(ErrorCode::contract_violation,
                      "M11 emergency trigger is invalid");
    }
    if ((trigger.direction == M11TriggerDirection::above &&
         trigger.enter_threshold <= trigger.exit_threshold) ||
        (trigger.direction == M11TriggerDirection::below &&
         trigger.enter_threshold >= trigger.exit_threshold)) {
        return Status(ErrorCode::contract_violation,
                      "M11 trigger hysteresis thresholds are invalid");
    }
    auto seats = trigger.authorized_seats;
    std::sort(seats.begin(), seats.end());
    if (std::adjacent_find(seats.begin(), seats.end()) != seats.end() ||
        std::any_of(seats.begin(), seats.end(),
                    [](const std::string &seat) { return !m11_valid_seat(seat); })) {
        return Status(ErrorCode::contract_violation,
                      "M11 trigger seat authorization is invalid");
    }
    return Status::success();
}

Result<M11DecisionScheduler>
M11DecisionScheduler::create(std::vector<M11CalendarSpec> calendars,
                             std::vector<M11TriggerSpec> triggers) {
    if (calendars.size() != kM11DecisionGroupCount) {
        return Status(ErrorCode::contract_violation,
                      "M11 scheduler requires eleven decision calendars");
    }
    for (const auto &calendar : calendars) {
        auto status = validate_m11_calendar(calendar);
        if (!status.ok()) {
            return status;
        }
    }
    std::sort(calendars.begin(), calendars.end(),
              [](const M11CalendarSpec &left, const M11CalendarSpec &right) {
                  return left.decision_group < right.decision_group;
              });
    if (std::adjacent_find(
            calendars.begin(), calendars.end(),
            [](const M11CalendarSpec &left, const M11CalendarSpec &right) {
                return left.decision_group == right.decision_group;
            }) != calendars.end()) {
        return Status(ErrorCode::contract_violation,
                      "M11 decision calendars must be unique");
    }
    for (const auto group : kM11DecisionGroups) {
        if (find_calendar(calendars, group) == nullptr) {
            return Status(ErrorCode::contract_violation,
                          "M11 decision calendar is missing");
        }
    }
    for (const auto &trigger : triggers) {
        auto status = validate_m11_trigger(trigger);
        if (!status.ok()) {
            return status;
        }
    }
    std::sort(triggers.begin(), triggers.end(),
              [](const M11TriggerSpec &left, const M11TriggerSpec &right) {
                  return left.trigger_id < right.trigger_id;
              });
    if (std::adjacent_find(triggers.begin(), triggers.end(),
                           [](const M11TriggerSpec &left, const M11TriggerSpec &right) {
                               return left.trigger_id == right.trigger_id;
                           }) != triggers.end()) {
        return Status(ErrorCode::contract_violation, "M11 trigger IDs must be unique");
    }
    return M11DecisionScheduler(std::move(calendars), std::move(triggers));
}

bool M11DecisionScheduler::due(std::string_view decision_group, Tick tick,
                               EconomyId economy) const noexcept {
    (void)economy;
    const auto *calendar = find_calendar(calendars_, decision_group);
    if (calendar == nullptr || tick.value() < calendar->offset_ticks) {
        return false;
    }
    return (tick.value() - calendar->offset_ticks) % calendar->period_ticks == 0U;
}

Result<double> M11DecisionScheduler::administrative_capacity(
    std::string_view decision_group) const noexcept {
    const auto *calendar = find_calendar(calendars_, decision_group);
    return calendar == nullptr
               ? Result<double>(Status(ErrorCode::not_found,
                                       "M11 decision calendar was not found"))
               : Result<double>(calendar->administrative_capacity);
}

Result<std::vector<M11TriggerNotice>>
M11DecisionScheduler::evaluate_triggers(Tick boundary, EconomyId economy,
                                        std::span<const M11MetricSample> metrics) {
    std::vector<M11TriggerNotice> notices;
    for (const auto &spec : triggers_) {
        auto *state = find_trigger_state(trigger_states_, economy, spec.trigger_id);
        const auto sample = metric_value(metrics, spec.series_id);
        if (!sample.has_value() || !std::isfinite(*sample)) {
            if (!state->active) {
                state->persistence_ticks = 0U;
            }
            continue;
        }
        const auto entering = spec.direction == M11TriggerDirection::above
                                  ? *sample >= spec.enter_threshold
                                  : *sample <= spec.enter_threshold;
        const auto exiting = spec.direction == M11TriggerDirection::above
                                 ? *sample <= spec.exit_threshold
                                 : *sample >= spec.exit_threshold;
        if (state->active) {
            if (exiting) {
                state->active = false;
                state->persistence_ticks = 0U;
            }
            continue;
        }
        state->persistence_ticks = entering ? state->persistence_ticks + 1U : 0U;
        if (state->persistence_ticks < spec.minimum_persistence_ticks ||
            boundary < state->cooldown_until) {
            continue;
        }
        state->active = true;
        state->persistence_ticks = 0U;
        state->cooldown_until = Tick(boundary.value() + spec.cooldown_ticks);
        auto seats = spec.authorized_seats;
        std::sort(seats.begin(), seats.end());
        notices.push_back({
            spec.trigger_id,
            economy,
            std::move(seats),
            spec.decision_group,
            Tick(boundary.value() + spec.context_expiry_ticks),
            *sample,
        });
    }
    return notices;
}

Status M11DecisionScheduler::restore_trigger_states(std::vector<M11TriggerState> states,
                                                    std::size_t economy_count) {
    for (const auto &state : states) {
        if (static_cast<std::size_t>(state.economy.value()) >= economy_count ||
            find_trigger(triggers_, state.trigger_id) == nullptr) {
            return Status(ErrorCode::corrupt_input,
                          "M11 trigger state does not match run schema");
        }
    }
    std::sort(states.begin(), states.end(),
              [](const M11TriggerState &left, const M11TriggerState &right) {
                  return std::pair{left.economy.value(), left.trigger_id} <
                         std::pair{right.economy.value(), right.trigger_id};
              });
    if (std::adjacent_find(
            states.begin(), states.end(),
            [](const M11TriggerState &left, const M11TriggerState &right) {
                return left.economy == right.economy &&
                       left.trigger_id == right.trigger_id;
            }) != states.end()) {
        return Status(ErrorCode::corrupt_input,
                      "M11 trigger state keys must be unique");
    }
    trigger_states_ = std::move(states);
    return Status::success();
}

Status validate_m11_cost_spec(const M11AdjustmentCostSpec &spec) noexcept {
    for (const auto *weights :
         {&spec.ordinary, &spec.major, &spec.regime_switch, &spec.operational}) {
        auto status = validate_weights(*weights);
        if (!status.ok()) {
            return status;
        }
    }
    if (!finite_non_negative(spec.proposal_administrative_overhead) ||
        !finite_non_negative(spec.emergency_premium) ||
        !std::isfinite(spec.refund_on_cancel) ||
        !std::isfinite(spec.refund_on_supersede) ||
        !std::isfinite(spec.refund_on_failed_execution) ||
        spec.refund_on_cancel < 0.0 || spec.refund_on_cancel > 1.0 ||
        spec.refund_on_supersede < 0.0 || spec.refund_on_supersede > 1.0 ||
        spec.refund_on_failed_execution < 0.0 ||
        spec.refund_on_failed_execution > 1.0) {
        return Status(ErrorCode::contract_violation,
                      "M11 adjustment cost specification is invalid");
    }
    return Status::success();
}

Result<double> m11_adjustment_cost(const M11AdjustmentCostSpec &spec,
                                   std::span<const M11PolicyChange> changes,
                                   bool emergency) noexcept {
    auto status = validate_m11_cost_spec(spec);
    if (!status.ok()) {
        return status;
    }
    double total = 0.0;
    for (const auto &change : changes) {
        if (change.lever == nullptr) {
            return Status(ErrorCode::invalid_argument,
                          "M11 policy change has no descriptor");
        }
        if (m11_policy_values_equal(change.old_value, change.new_value)) {
            continue;
        }
        const auto *weights = cost_weights(spec, change.lever->cost_class);
        if (weights == nullptr) {
            return Status(ErrorCode::contract_violation,
                          "M11 policy cost class is unknown");
        }
        auto distance = m11_policy_numeric_distance(*change.lever, change.old_value,
                                                    change.new_value);
        if (!distance.ok()) {
            return distance.status();
        }
        const auto value = *distance.get_if();
        total += weights->fixed + weights->linear * value +
                 weights->quadratic * value * value;
    }
    total *= emergency ? spec.emergency_premium : 1.0;
    if (!std::isfinite(total)) {
        return Status(ErrorCode::out_of_range, "M11 adjustment cost overflowed");
    }
    return total;
}

Result<double>
m11_administrative_cost(const M11AdjustmentCostSpec &spec,
                        std::span<const M11PolicyChange> changes) noexcept {
    auto status = validate_m11_cost_spec(spec);
    if (!status.ok()) {
        return status;
    }
    double total = 0.0;
    bool changed = false;
    for (const auto &change : changes) {
        if (change.lever == nullptr) {
            return Status(ErrorCode::invalid_argument,
                          "M11 policy change has no descriptor");
        }
        if (m11_policy_values_equal(change.old_value, change.new_value)) {
            continue;
        }
        changed = true;
        total += change.lever->administrative_weight;
    }
    if (changed) {
        total += spec.proposal_administrative_overhead;
    }
    if (!std::isfinite(total)) {
        return Status(ErrorCode::out_of_range, "M11 administrative cost overflowed");
    }
    return total;
}

Result<M11ControllerEvent> M11EventStream::append(Tick boundary, std::string event_type,
                                                  std::string operation_id,
                                                  std::string actor,
                                                  std::string canonical_payload,
                                                  M11EventVisibility visibility) {
    if (events_.size() >= maximum_events_) {
        return Status(ErrorCode::out_of_range, "M11 event stream capacity was reached");
    }
    if (!valid_stable_id(event_type) ||
        (!operation_id.empty() && !valid_stable_id(operation_id)) ||
        !valid_actor(actor) || canonical_payload.size() > kMaximumEventPayloadBytes ||
        canonical_payload.find('\0') != std::string::npos ||
        static_cast<std::uint8_t>(visibility) >
            static_cast<std::uint8_t>(M11EventVisibility::privileged_audit)) {
        return Status(ErrorCode::invalid_argument, "M11 controller event is invalid");
    }
    M11ControllerEvent event{
        next_sequence_,
        boundary,
        std::move(event_type),
        std::move(operation_id),
        std::move(actor),
        std::move(canonical_payload),
        visibility,
        head_hash_,
        {},
    };
    event.hash = event_hash(event);
    events_.push_back(event);
    head_hash_ = event.hash;
    ++next_sequence_;
    return event;
}

Result<std::vector<M11ControllerEvent>>
M11EventStream::page(std::uint64_t first_sequence, std::size_t maximum_rows,
                     M11EventVisibility maximum_visibility) const {
    if (maximum_rows == 0U ||
        static_cast<std::uint8_t>(maximum_visibility) >
            static_cast<std::uint8_t>(M11EventVisibility::privileged_audit)) {
        return Status(ErrorCode::invalid_argument, "M11 event page request is invalid");
    }
    if (first_sequence > next_sequence_) {
        return Status(ErrorCode::out_of_range, "M11 event page cursor is out of range");
    }
    std::vector<M11ControllerEvent> result;
    result.reserve(std::min(maximum_rows, events_.size()));
    for (const auto &event : events_) {
        if (event.sequence < first_sequence ||
            static_cast<std::uint8_t>(event.visibility) >
                static_cast<std::uint8_t>(maximum_visibility)) {
            continue;
        }
        result.push_back(event);
        if (result.size() == maximum_rows) {
            break;
        }
    }
    return result;
}

Status M11EventStream::restore(std::vector<M11ControllerEvent> events,
                               std::uint64_t next_sequence,
                               core::StateDigest head_hash) {
    if (events.size() > maximum_events_ || next_sequence != events.size()) {
        return Status(ErrorCode::corrupt_input, "M11 event stream cursor is corrupt");
    }
    core::StateDigest prior{};
    for (std::size_t index = 0; index < events.size(); ++index) {
        const auto &event = events[index];
        if (event.sequence != index || event.prior_hash != prior ||
            event.hash != event_hash(event)) {
            return Status(ErrorCode::corrupt_input, "M11 event hash chain is corrupt");
        }
        prior = event.hash;
    }
    if (prior != head_hash) {
        return Status(ErrorCode::corrupt_input, "M11 event stream head is corrupt");
    }
    events_ = std::move(events);
    next_sequence_ = next_sequence;
    head_hash_ = head_hash;
    return Status::success();
}

Result<M11ReleaseRecord> M11ReleaseStream::append(EconomyId economy,
                                                  std::string series_id,
                                                  Tick observed_at, Tick released_at,
                                                  std::uint32_t revision,
                                                  std::optional<double> value,
                                                  std::uint64_t source_event_sequence) {
    if (releases_.size() >= maximum_releases_) {
        return Status(ErrorCode::out_of_range,
                      "M11 release stream capacity was reached");
    }
    if (!economy.valid() || !valid_stable_id(series_id) || released_at < observed_at ||
        (value.has_value() && !std::isfinite(*value))) {
        return Status(ErrorCode::invalid_argument, "M11 release record is invalid");
    }
    const auto duplicate = std::find_if(
        releases_.begin(), releases_.end(), [&](const M11ReleaseRecord &record) {
            return record.economy == economy && record.series_id == series_id &&
                   record.observed_at == observed_at && record.revision == revision;
        });
    if (duplicate != releases_.end()) {
        return Status(ErrorCode::already_exists, "M11 release revision already exists");
    }
    const auto previous = std::find_if(
        releases_.rbegin(), releases_.rend(), [&](const M11ReleaseRecord &record) {
            return record.economy == economy && record.series_id == series_id &&
                   record.observed_at == observed_at;
        });
    if (previous != releases_.rend() && revision != previous->revision + 1U) {
        return Status(ErrorCode::contract_violation,
                      "M11 release revisions must be contiguous");
    }
    if (previous == releases_.rend() && revision != 0U) {
        return Status(ErrorCode::contract_violation,
                      "M11 initial release revision must be zero");
    }
    M11ReleaseRecord record{
        next_sequence_, economy, std::move(series_id),  observed_at, released_at,
        revision,       value,   source_event_sequence,
    };
    releases_.push_back(record);
    ++next_sequence_;
    return record;
}

Result<std::vector<M11ReleaseRecord>>
M11ReleaseStream::page(std::uint64_t first_sequence, std::size_t maximum_rows,
                       Tick released_through) const {
    if (maximum_rows == 0U) {
        return Status(ErrorCode::invalid_argument,
                      "M11 release page size must be positive");
    }
    if (first_sequence > next_sequence_) {
        return Status(ErrorCode::out_of_range,
                      "M11 release page cursor is out of range");
    }
    std::vector<M11ReleaseRecord> result;
    result.reserve(std::min(maximum_rows, releases_.size()));
    for (const auto &record : releases_) {
        if (record.sequence < first_sequence || record.released_at > released_through) {
            continue;
        }
        result.push_back(record);
        if (result.size() == maximum_rows) {
            break;
        }
    }
    return result;
}

Status M11ReleaseStream::restore(std::vector<M11ReleaseRecord> releases,
                                 std::uint64_t next_sequence) {
    if (releases.size() > maximum_releases_ || next_sequence != releases.size() ||
        !std::is_sorted(releases.begin(), releases.end(), release_key_less)) {
        return Status(ErrorCode::corrupt_input, "M11 release stream cursor is corrupt");
    }
    for (std::size_t index = 0; index < releases.size(); ++index) {
        const auto &record = releases[index];
        if (record.sequence != index || !record.economy.valid() ||
            !valid_stable_id(record.series_id) ||
            record.released_at < record.observed_at ||
            (record.value.has_value() && !std::isfinite(*record.value))) {
            return Status(ErrorCode::corrupt_input,
                          "M11 release stream record is corrupt");
        }
        const auto prior = std::find_if(
            releases.rbegin() + static_cast<std::ptrdiff_t>(releases.size() - index),
            releases.rend(), [&](const M11ReleaseRecord &candidate) {
                return candidate.economy == record.economy &&
                       candidate.series_id == record.series_id &&
                       candidate.observed_at == record.observed_at;
            });
        if ((prior == releases.rend() && record.revision != 0U) ||
            (prior != releases.rend() && record.revision != prior->revision + 1U)) {
            return Status(ErrorCode::corrupt_input,
                          "M11 release revision chain is corrupt");
        }
    }
    releases_ = std::move(releases);
    next_sequence_ = next_sequence;
    return Status::success();
}

} // namespace macro_sim::control
