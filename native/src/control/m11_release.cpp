#include "macro_sim/control/m11_release.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace macro_sim::control {
namespace {

[[nodiscard]] std::vector<std::string_view> split_roles(std::string_view value) {
    std::vector<std::string_view> result;
    while (!value.empty()) {
        const auto separator = value.find('|');
        const auto item = value.substr(0U, separator);
        if (!item.empty()) {
            result.push_back(item);
        }
        if (separator == std::string_view::npos) {
            break;
        }
        value.remove_prefix(separator + 1U);
    }
    return result;
}

[[nodiscard]] std::string metric_stable_id(const M11ObservationFieldDescriptor &field) {
    std::string result = "metric.";
    switch (field.source) {
    case M11ObservationSource::economy:
        result += "economy.";
        break;
    case M11ObservationSource::world:
        result += "world.";
        break;
    case M11ObservationSource::shock:
        result += "shock.";
        break;
    case M11ObservationSource::release:
        return {};
    }
    result += field.source_key;
    return result;
}

[[nodiscard]] bool already_published(const M11ReleaseStream &stream, EconomyId economy,
                                     std::string_view series_id, Tick observed_at,
                                     std::uint32_t revision) noexcept {
    const auto releases = stream.releases();
    return std::any_of(
        releases.begin(), releases.end(), [&](const M11ReleaseRecord &record) {
            return record.economy == economy && record.series_id == series_id &&
                   record.observed_at == observed_at && record.revision == revision;
        });
}

[[nodiscard]] std::optional<double> latest_release(const M11ReleaseStream &stream,
                                                   EconomyId economy,
                                                   std::string_view series_id,
                                                   Tick as_of) noexcept {
    std::optional<double> result;
    std::uint64_t latest_sequence = 0U;
    bool found = false;
    for (const auto &record : stream.releases()) {
        if (record.economy != economy || record.series_id != series_id ||
            record.released_at > as_of ||
            (found && record.sequence <= latest_sequence)) {
            continue;
        }
        found = true;
        latest_sequence = record.sequence;
        result = record.value;
    }
    return result;
}

[[nodiscard]] double
maximum_optional(std::initializer_list<std::optional<double>> values) noexcept {
    double result = 0.0;
    for (const auto &value : values) {
        if (value.has_value() && std::isfinite(*value)) {
            result = std::max(result, *value);
        }
    }
    return result;
}

} // namespace

std::span<const M11ObservationFieldDescriptor> m11_observation_fields() noexcept {
    return kM11ObservationFields;
}

const M11ObservationFieldDescriptor *
find_m11_observation_field(std::string_view series_id) noexcept {
    const auto fields = m11_observation_fields();
    const auto found =
        std::lower_bound(fields.begin(), fields.end(), series_id,
                         [](const M11ObservationFieldDescriptor &field,
                            std::string_view name) { return field.series_id < name; });
    return found == fields.end() || found->series_id != series_id ? nullptr : &*found;
}

bool m11_release_permitted(const M11ObservationFieldDescriptor &field,
                           std::string_view role) noexcept {
    if (field.access == M11ReleaseAccess::public_access) {
        return true;
    }
    if (field.access == M11ReleaseAccess::oracle) {
        return role == "oracle";
    }
    const auto roles = split_roles(field.roles);
    return std::find(roles.begin(), roles.end(), role) != roles.end();
}

Result<std::optional<double>>
M11ReleaseService::aggregate(const reporting::MetricHistoryPage &history,
                             const M11ObservationFieldDescriptor &field,
                             EconomyId economy, Tick endpoint) const {
    if (field.source == M11ObservationSource::release) {
        return Status(ErrorCode::unsupported,
                      "M11 derived release source is not implemented");
    }
    const auto stable_id = metric_stable_id(field);
    auto metric = reporting::metric_index(stable_id);
    if (!metric.ok()) {
        return metric.status();
    }
    if (endpoint.value() + 1U < field.window_ticks && field.require_full_window) {
        return std::optional<double>{};
    }
    const auto first_reference = endpoint.value() + 1U >= field.window_ticks
                                     ? endpoint.value() + 1U - field.window_ticks
                                     : 0U;
    const auto frame_offset = field.source == M11ObservationSource::shock ? 0U : 1U;
    const auto first_tick = first_reference + frame_offset;
    const auto last_tick = endpoint.value() + frame_offset;
    std::vector<double> values;
    values.reserve(field.window_ticks);
    for (const auto &frame : history.frames) {
        if (frame.tick.value() < first_tick || frame.tick.value() > last_tick) {
            continue;
        }
        auto value =
            frame.value(static_cast<std::size_t>(economy.value()), *metric.get_if());
        if (!value.ok() || !std::isfinite(*value.get_if())) {
            continue;
        }
        values.push_back(*value.get_if());
    }
    if (field.require_full_window && values.size() != field.window_ticks) {
        return std::optional<double>{};
    }
    if (values.empty()) {
        return std::optional<double>{};
    }
    if (field.aggregation == M11ReleaseAggregation::last) {
        return std::optional<double>{values.back()};
    }
    double total = 0.0;
    for (const auto value : values) {
        total += value;
    }
    if (!std::isfinite(total)) {
        return Status(ErrorCode::out_of_range, "M11 release aggregation overflowed");
    }
    return std::optional<double>{field.aggregation == M11ReleaseAggregation::mean
                                     ? total / static_cast<double>(values.size())
                                     : total};
}

Result<std::size_t>
M11ReleaseService::publish_due(const reporting::MetricPipeline &metrics,
                               const simulation::M9World &world, Tick boundary,
                               std::uint64_t source_event_sequence,
                               M11ReleaseStream &stream) const {
    if (boundary != world.tick() || boundary != metrics.current().tick) {
        return Status(ErrorCode::stale_handle, "M11 release boundary is stale");
    }
    const auto &history_store = metrics.history();
    auto history =
        history_store.page(history_store.oldest_sequence(), history_store.size());
    if (!history.ok()) {
        return history.status();
    }
    auto staged = stream;
    std::size_t published = 0U;
    for (const auto &field : m11_observation_fields()) {
        std::uint64_t endpoint_value = 0U;
        if (field.source == M11ObservationSource::shock) {
            if (boundary.value() <
                field.phase_offset_ticks + field.publication_lag_ticks) {
                continue;
            }
            const auto release_index = boundary.value() - field.publication_lag_ticks;
            if (release_index < field.phase_offset_ticks ||
                (release_index - field.phase_offset_ticks) % field.frequency_ticks !=
                    0U) {
                continue;
            }
            endpoint_value = boundary.value();
        } else {
            const auto first_release =
                static_cast<std::uint64_t>(field.phase_offset_ticks) +
                field.frequency_ticks + field.publication_lag_ticks;
            if (boundary.value() < first_release) {
                continue;
            }
            const auto completed_through =
                boundary.value() - field.publication_lag_ticks;
            if ((completed_through - field.phase_offset_ticks) %
                    field.frequency_ticks !=
                0U) {
                continue;
            }
            endpoint_value = completed_through - 1U;
        }
        const auto endpoint = Tick(endpoint_value);
        for (std::size_t economy = 0U; economy < world.economy_count(); ++economy) {
            const auto economy_id = EconomyId(static_cast<std::uint32_t>(economy));
            if (already_published(staged, economy_id, field.series_id, endpoint, 0U)) {
                continue;
            }
            auto value = aggregate(*history.get_if(), field, economy_id, endpoint);
            if (!value.ok()) {
                return value.status();
            }
            auto appended =
                staged.append(economy_id, std::string(field.series_id), endpoint,
                              boundary, 0U, *value.get_if(), source_event_sequence);
            if (!appended.ok()) {
                return appended.status();
            }
            ++published;
        }
    }
    stream = std::move(staged);
    return published;
}

Result<std::vector<M11ReleasedObservation>>
M11ReleaseService::observation(const M11ReleaseStream &stream, EconomyId economy,
                               Tick as_of, std::string_view role) const {
    if (!economy.valid() || role.empty()) {
        return Status(ErrorCode::invalid_argument, "M11 observation scope is invalid");
    }
    std::vector<M11ReleasedObservation> result;
    for (const auto &field : m11_observation_fields()) {
        if (!m11_release_permitted(field, role)) {
            continue;
        }
        const M11ReleaseRecord *latest = nullptr;
        for (const auto &record : stream.releases()) {
            if (record.economy != economy || record.series_id != field.series_id ||
                record.released_at > as_of ||
                (latest != nullptr && record.sequence <= latest->sequence)) {
                continue;
            }
            latest = &record;
        }
        if (latest != nullptr) {
            result.push_back({
                latest->series_id,
                latest->value,
                latest->observed_at,
                latest->released_at,
                latest->revision,
            });
        }
    }
    std::sort(
        result.begin(), result.end(),
        [](const M11ReleasedObservation &left, const M11ReleasedObservation &right) {
            return left.series_id < right.series_id;
        });
    return result;
}

std::vector<M11MetricSample>
M11ReleaseService::trigger_samples(const M11ReleaseStream &stream, EconomyId economy,
                                   Tick as_of) const {
    const auto reserve =
        latest_release(stream, economy, "reserve_floor_breach_share", as_of);
    const auto failures =
        latest_release(stream, economy, "near_failure_bank_count", as_of);
    const auto energy = latest_release(stream, economy, "energy_unfilled", as_of);
    const auto productivity =
        latest_release(stream, economy, "shock_productivity", as_of);
    const auto labor =
        latest_release(stream, economy, "shock_labor_availability", as_of);
    const auto capital =
        latest_release(stream, economy, "shock_capital_destruction", as_of);
    const auto energy_shock =
        latest_release(stream, economy, "shock_energy_capacity", as_of);
    const auto credit = latest_release(stream, economy, "shock_credit_supply", as_of);
    const auto import_shock =
        latest_release(stream, economy, "shock_import_capacity", as_of);
    const auto export_shock =
        latest_release(stream, economy, "shock_export_capacity", as_of);
    const auto demand =
        latest_release(stream, economy, "shock_household_demand", as_of);
    return {
        {"reserve_floor_breach_share", reserve},
        {"near_failure_bank_count", failures},
        {"energy_unfilled", energy},
        {"shock_supply_severity", maximum_optional({productivity, labor, capital})},
        {"shock_energy_severity", maximum_optional({energy_shock})},
        {"shock_financial_severity", maximum_optional({credit})},
        {"shock_trade_severity", maximum_optional({import_shock, export_shock})},
        {"shock_demand_severity", maximum_optional({demand})},
    };
}

} // namespace macro_sim::control
