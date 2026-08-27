#include "macro_sim/control/m11_session.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>

namespace macro_sim::control {
namespace {

[[nodiscard]] Status invalid_session(std::string_view message) noexcept {
    return Status(ErrorCode::invalid_argument, message);
}

[[nodiscard]] std::string_view owner_for_group(std::string_view group) noexcept {
    for (const auto &lever : m11_policy_levers()) {
        if (lever.decision_group == group) {
            return lever.owner_role;
        }
    }
    return {};
}

[[nodiscard]] std::vector<std::string_view> split_choices(std::string_view choices) {
    std::vector<std::string_view> result;
    while (!choices.empty()) {
        const auto separator = choices.find('|');
        result.push_back(choices.substr(0U, separator));
        if (separator == std::string_view::npos) {
            break;
        }
        choices.remove_prefix(separator + 1U);
    }
    return result;
}

[[nodiscard]] const M11PermittedAction *permitted(const M11DecisionContext &context,
                                                  std::string_view lever) noexcept {
    const auto found = std::lower_bound(
        context.permitted_actions.begin(), context.permitted_actions.end(), lever,
        [](const M11PermittedAction &entry, std::string_view name) {
            return entry.lever < name;
        });
    return found == context.permitted_actions.end() || found->lever != lever ? nullptr
                                                                             : &*found;
}

[[nodiscard]] const M11ReleasedObservation *released(const M11DecisionContext &context,
                                                     std::string_view series) noexcept {
    const auto found =
        std::lower_bound(context.observation.begin(), context.observation.end(), series,
                         [](const M11ReleasedObservation &entry,
                            std::string_view name) { return entry.series_id < name; });
    return found == context.observation.end() || found->series_id != series ? nullptr
                                                                            : &*found;
}

[[nodiscard]] std::optional<double> released_value(const M11DecisionContext &context,
                                                   std::string_view series) noexcept {
    const auto *entry = released(context, series);
    return entry == nullptr ? std::nullopt : entry->value;
}

[[nodiscard]] const M11PendingDecision *
pending_for(const M11PolicyCoordinator &coordinator, EconomyId economy,
            std::string_view lever) noexcept {
    for (const auto &entry : coordinator.pending()) {
        if (entry.decision.status != M11DecisionStatus::accepted_pending) {
            continue;
        }
        const auto action =
            std::find_if(entry.proposal.actions.begin(), entry.proposal.actions.end(),
                         [&](const NativePolicyAction &value) {
                             return value.economy == economy && value.lever == lever;
                         });
        if (action != entry.proposal.actions.end()) {
            return &entry;
        }
    }
    return nullptr;
}

[[nodiscard]] const NativePolicyAction *
pending_action(const M11PendingDecision &pending_value, EconomyId economy,
               std::string_view lever) noexcept {
    const auto found = std::find_if(
        pending_value.proposal.actions.begin(), pending_value.proposal.actions.end(),
        [&](const NativePolicyAction &action) {
            return action.economy == economy && action.lever == lever;
        });
    return found == pending_value.proposal.actions.end() ? nullptr : &*found;
}

[[nodiscard]] double encode_policy_value(const PolicyLeverDescriptor &lever,
                                         const PolicyValue &value,
                                         std::size_t economy_count) noexcept {
    if (const auto *boolean = std::get_if<bool>(&value); boolean != nullptr) {
        return *boolean ? 1.0 : 0.0;
    }
    double numeric = 0.0;
    bool has_numeric = false;
    if (const auto *integer = std::get_if<std::int64_t>(&value); integer != nullptr) {
        numeric = static_cast<double>(*integer);
        has_numeric = true;
    } else if (const auto *number = std::get_if<double>(&value); number != nullptr) {
        numeric = *number;
        has_numeric = true;
    }
    if (has_numeric) {
        if (lever.minimum.has_value() && lever.maximum.has_value() &&
            *lever.maximum > *lever.minimum) {
            return (numeric - *lever.minimum) / (*lever.maximum - *lever.minimum);
        }
        return numeric;
    }
    if (const auto *choice = std::get_if<std::string>(&value); choice != nullptr) {
        const auto choices = split_choices(lever.choices);
        const auto found = std::find(choices.begin(), choices.end(), *choice);
        return found == choices.end()
                   ? -1.0
                   : static_cast<double>(std::distance(choices.begin(), found));
    }
    if (const auto *targets = std::get_if<PolicyEconomySet>(&value);
        targets != nullptr) {
        double encoded = 0.0;
        for (const auto target : *targets) {
            if (target.value() < economy_count && target.value() < 52U) {
                encoded += std::ldexp(1.0, static_cast<int>(target.value()));
            }
        }
        return encoded;
    }
    return 0.0;
}

[[nodiscard]] Result<PolicyValue> directional_value(const PolicyLeverDescriptor &lever,
                                                    const PolicyValue &current,
                                                    std::uint32_t code, EconomyId owner,
                                                    std::size_t economy_count) {
    if (code == 1U) {
        return current;
    }
    if (code > 2U) {
        return invalid_session("M11 direction code is invalid");
    }
    const auto upward = code == 2U;
    if (lever.kind == PolicyValueKind::boolean) {
        return PolicyValue(upward);
    }
    if (lever.kind == PolicyValueKind::choice) {
        const auto choices = split_choices(lever.choices);
        if (choices.empty()) {
            return current;
        }
        const auto *value = std::get_if<std::string>(&current);
        auto index = value == nullptr
                         ? std::size_t{0U}
                         : static_cast<std::size_t>(std::distance(
                               choices.begin(),
                               std::find(choices.begin(), choices.end(), *value)));
        if (index >= choices.size()) {
            index = 0U;
        }
        index = upward ? std::min(index + 1U, choices.size() - 1U)
                       : (index == 0U ? 0U : index - 1U);
        return PolicyValue(std::string(choices[index]));
    }
    if (lever.kind == PolicyValueKind::economy_id) {
        if (!upward) {
            return PolicyValue(std::monostate{});
        }
        for (std::size_t index = 0U; index < economy_count; ++index) {
            if (index != owner.value()) {
                return PolicyValue(static_cast<std::int64_t>(index));
            }
        }
        return current;
    }
    if (lever.kind == PolicyValueKind::economy_set) {
        PolicyEconomySet targets;
        if (const auto *existing = std::get_if<PolicyEconomySet>(&current);
            existing != nullptr) {
            targets = *existing;
        }
        if (!upward) {
            targets.clear();
        } else {
            for (std::size_t index = 0U; index < economy_count; ++index) {
                if (index != owner.value()) {
                    targets = {EconomyId(index)};
                    break;
                }
            }
        }
        return PolicyValue(std::move(targets));
    }

    const auto step = lever.control_scale.value_or(lever.maximum_step.value_or(0.0));
    if (!(step > 0.0)) {
        return current;
    }
    const auto nullable = lever.kind == PolicyValueKind::nullable_number;
    if (std::holds_alternative<std::monostate>(current)) {
        if (!upward) {
            return current;
        }
        return PolicyValue(lever.minimum.value_or(0.0));
    }
    double base = 0.0;
    if (const auto *number = std::get_if<double>(&current); number != nullptr) {
        base = *number;
    } else if (const auto *integer = std::get_if<std::int64_t>(&current);
               integer != nullptr) {
        base = static_cast<double>(*integer);
    } else {
        return current;
    }
    auto value = base + (upward ? step : -step);
    if (nullable && !upward && lever.minimum.has_value() && value < *lever.minimum) {
        return PolicyValue(std::monostate{});
    }
    if (lever.minimum.has_value()) {
        value = std::max(value, *lever.minimum);
    }
    if (lever.maximum.has_value()) {
        value = std::min(value, *lever.maximum);
    }
    if (lever.kind == PolicyValueKind::integer) {
        return PolicyValue(static_cast<std::int64_t>(std::llround(value)));
    }
    return PolicyValue(value);
}

[[nodiscard]] std::vector<M11ProposalVersion>
proposal_versions(const M11DecisionContext &context) {
    std::vector<M11ProposalVersion> versions;
    versions.reserve(context.policy_versions.size());
    for (const auto &version : context.policy_versions) {
        versions.push_back({version.lever, version.version});
    }
    return versions;
}

[[nodiscard]] std::uint64_t mix64(std::uint64_t value) noexcept {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

[[nodiscard]] std::uint64_t stable_string_hash(std::string_view value) noexcept {
    std::uint64_t result = 1469598103934665603ULL;
    for (const auto character : value) {
        result ^= static_cast<std::uint8_t>(character);
        result *= 1099511628211ULL;
    }
    return result;
}

[[nodiscard]] double unit_random(std::uint64_t value) noexcept {
    return static_cast<double>(value >> 11U) * (1.0 / 9007199254740992.0);
}

[[nodiscard]] std::vector<double>
encode_artifact_context(const NativePolicyArtifact &artifact,
                        const M11PolicyCoordinator &coordinator,
                        const M11DecisionContext &context, std::size_t economy_count) {
    std::vector<double> values;
    values.reserve(artifact.feature_names().size());
    for (const auto &feature : artifact.feature_names()) {
        if (feature == "boundary_tick") {
            values.push_back(static_cast<double>(context.boundary.value()));
            continue;
        }
        if (feature == "elapsed_ticks") {
            values.push_back(static_cast<double>(context.elapsed_ticks));
            continue;
        }
        if (feature.starts_with("release:")) {
            const auto suffix = feature.rfind(':');
            const auto series = feature.substr(8U, suffix - 8U);
            const auto *entry = released(context, series);
            if (feature.ends_with(":missing")) {
                values.push_back(entry == nullptr || !entry->value.has_value() ? 1.0
                                                                               : 0.0);
            } else {
                auto value = entry == nullptr ? std::optional<double>{} : entry->value;
                const auto *field = find_m11_observation_field(series);
                if (value.has_value() && field != nullptr &&
                    field->normalization_scale.has_value() &&
                    *field->normalization_scale != 0.0) {
                    *value /= *field->normalization_scale;
                }
                values.push_back(value.value_or(0.0));
            }
            continue;
        }
        if (feature == "decision:ticks_to_expiry") {
            values.push_back(static_cast<double>(context.expires_at.value() -
                                                 context.boundary.value()));
            continue;
        }
        if (feature == "decision:emergency") {
            values.push_back(context.emergency ? 1.0 : 0.0);
            continue;
        }
        if (feature == "decision:emergency_trigger_present") {
            values.push_back(context.emergency_trigger.empty() ? 0.0 : 1.0);
            continue;
        }
        if (feature == "admin:remaining") {
            values.push_back(context.administrative_remaining);
            continue;
        }
        if (feature == "admin:reserved") {
            values.push_back(context.administrative_reserved);
            continue;
        }
        if (!feature.starts_with("policy:")) {
            values.push_back(0.0);
            continue;
        }
        const auto suffix = feature.rfind(':');
        const auto lever_name = feature.substr(7U, suffix - 7U);
        const auto field_name = feature.substr(suffix + 1U);
        const auto *lever = find_m11_policy_lever(lever_name);
        const auto *item = permitted(context, lever_name);
        const auto *version =
            coordinator.find_policy_version(context.economy, lever_name);
        const auto *pending = pending_for(coordinator, context.economy, lever_name);
        const auto *target =
            pending == nullptr ? nullptr
                               : pending_action(*pending, context.economy, lever_name);
        if (field_name == "value") {
            values.push_back(
                lever == nullptr || item == nullptr
                    ? 0.0
                    : encode_policy_value(*lever, item->current_value, economy_count));
        } else if (field_name == "is_none") {
            values.push_back(item == nullptr || std::holds_alternative<std::monostate>(
                                                    item->current_value)
                                 ? 1.0
                                 : 0.0);
        } else if (field_name == "pending_target") {
            values.push_back(
                lever == nullptr || target == nullptr
                    ? 0.0
                    : encode_policy_value(*lever, target->value, economy_count));
        } else if (field_name == "pending_target_is_none") {
            values.push_back(
                target != nullptr &&
                        std::holds_alternative<std::monostate>(target->value)
                    ? 1.0
                    : 0.0);
        } else if (field_name == "pending_present") {
            values.push_back(pending == nullptr ? 0.0 : 1.0);
        } else if (field_name == "version") {
            values.push_back(
                version == nullptr ? 0.0 : static_cast<double>(version->version));
        } else if (field_name == "last_effective_age") {
            values.push_back(
                version == nullptr || !version->last_effective.has_value()
                    ? 0.0
                    : static_cast<double>(context.boundary.value() -
                                          version->last_effective->value()));
        } else if (field_name == "last_effective_never") {
            values.push_back(
                version == nullptr || !version->last_effective.has_value() ? 1.0 : 0.0);
        } else if (field_name == "next_eligibility_delta") {
            values.push_back(
                item == nullptr || item->earliest_effective <= context.boundary
                    ? 0.0
                    : static_cast<double>(item->earliest_effective.value() -
                                          context.boundary.value()));
        } else if (field_name == "pending_effective_delta") {
            values.push_back(
                pending == nullptr || !pending->decision.effective_at.has_value() ||
                        *pending->decision.effective_at <= context.boundary
                    ? 0.0
                    : static_cast<double>(pending->decision.effective_at->value() -
                                          context.boundary.value()));
        } else {
            values.push_back(0.0);
        }
    }
    return values;
}

[[nodiscard]] CanonicalControllerEnvelope
make_envelope(Tick boundary, std::uint64_t policy_generation,
              const M11ControlledState &state) {
    CanonicalControllerEnvelope envelope;
    envelope.boundary = boundary;
    envelope.policy_generation = policy_generation;
    envelope.event_sequence = state.events.next_sequence();
    envelope.release_cursor = state.releases.next_sequence();
    envelope.decision_versions.reserve(state.coordinator.policy_versions().size());
    envelope.effective_versions.reserve(state.coordinator.policy_versions().size());
    for (const auto &version : state.coordinator.policy_versions()) {
        envelope.decision_versions.push_back(version.version);
        envelope.effective_versions.push_back(version.version);
    }
    std::ostringstream payload;
    payload << "m11|phase=" << static_cast<unsigned>(state.phase)
            << "|boundary_sequence=" << state.boundary_sequence
            << "|events=" << state.events.next_sequence()
            << "|event_head=" << state.events.head_hash().hex()
            << "|releases=" << state.releases.next_sequence()
            << "|contexts=" << state.coordinator.contexts().size()
            << "|pending=" << state.coordinator.pending().size()
            << "|decisions=" << state.coordinator.decisions().size()
            << "|seats=" << state.seats.size()
            << "|seat_archive=" << state.archived_seat_occupants.size()
            << "|seat_operations=" << state.seat_operations.size();
    for (const auto &seat : state.seats) {
        payload << '|' << seat.assignment.economy.value() << ':' << seat.assignment.seat
                << ':' << static_cast<unsigned>(seat.assignment.occupant.kind) << ':'
                << seat.assignment.occupant.occupant_id << ':' << seat.decision_counter
                << ':' << seat.artifact_sha256;
    }
    for (const auto &archived : state.archived_seat_occupants) {
        payload << "|archive:" << archived.archive_id << ':'
                << archived.runtime.assignment.economy.value() << ':'
                << archived.runtime.assignment.seat << ':'
                << static_cast<unsigned>(archived.runtime.assignment.occupant.kind)
                << ':' << archived.runtime.assignment.occupant.occupant_id << ':'
                << archived.runtime.decision_counter << ':'
                << archived.runtime.artifact_sha256;
    }
    for (const auto &operation : state.seat_operations) {
        payload << "|seat_op:" << operation.operation_id << ':'
                << static_cast<unsigned>(operation.kind) << ':'
                << operation.request_hash.hex() << ':'
                << (operation.archived_occupant_id.has_value()
                        ? *operation.archived_occupant_id
                        : "");
    }
    const auto text = payload.str();
    envelope.canonical_payload.assign(text.begin(), text.end());
    return envelope;
}

[[nodiscard]] bool has_unanswered_human(const M11ControlledState &state) noexcept {
    for (const auto &context_id : state.opened_context_ids) {
        const auto *context = state.coordinator.find_context(context_id);
        if (context == nullptr || context->answered_by_proposal.has_value()) {
            continue;
        }
        const auto found = std::find_if(
            state.seats.begin(), state.seats.end(), [&](const M11SeatRuntime &seat) {
                return seat.assignment.economy == context->economy &&
                       seat.assignment.seat == context->seat;
            });
        if (found != state.seats.end() &&
            found->assignment.occupant.kind == M11OccupantKind::human_queue) {
            return true;
        }
    }
    return false;
}

[[nodiscard]] std::uint64_t
previous_context_elapsed(const M11PolicyCoordinator &coordinator, EconomyId economy,
                         std::string_view seat, std::string_view group,
                         Tick boundary) noexcept {
    std::optional<Tick> previous;
    for (const auto &context : coordinator.contexts()) {
        if (context.economy == economy && context.seat == seat &&
            context.decision_group == group && context.boundary < boundary &&
            (!previous.has_value() || context.boundary > *previous)) {
            previous = context.boundary;
        }
    }
    return previous.has_value() ? boundary.value() - previous->value() : 0U;
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_text(std::vector<std::uint8_t> &bytes, std::string_view value) {
    append_u64(bytes, value.size());
    bytes.insert(bytes.end(), value.begin(), value.end());
}

void append_policy_value(std::vector<std::uint8_t> &bytes, const PolicyValue &value) {
    bytes.push_back(static_cast<std::uint8_t>(value.index()));
    std::visit(
        [&](const auto &entry) {
            using Value = std::decay_t<decltype(entry)>;
            if constexpr (std::is_same_v<Value, std::monostate>) {
                return;
            } else if constexpr (std::is_same_v<Value, bool>) {
                bytes.push_back(entry ? 1U : 0U);
            } else if constexpr (std::is_same_v<Value, std::int64_t>) {
                append_u64(bytes, std::bit_cast<std::uint64_t>(entry));
            } else if constexpr (std::is_same_v<Value, double>) {
                append_u64(bytes, std::bit_cast<std::uint64_t>(entry));
            } else if constexpr (std::is_same_v<Value, std::string>) {
                append_text(bytes, entry);
            } else {
                append_u64(bytes, entry.size());
                for (const auto economy : entry) {
                    append_u64(bytes, economy.value());
                }
            }
        },
        value);
}

void append_occupant(std::vector<std::uint8_t> &bytes,
                     const M11OccupantSpec &occupant) {
    bytes.push_back(static_cast<std::uint8_t>(occupant.kind));
    append_text(bytes, occupant.occupant_id);
    append_u64(bytes, occupant.seed);
    append_u64(bytes, std::bit_cast<std::uint64_t>(occupant.random_action_probability));
    append_u64(bytes, occupant.schedule.size());
    for (const auto &scheduled : occupant.schedule) {
        append_u64(bytes, scheduled.boundary.value());
        append_text(bytes, scheduled.decision_group);
        append_u64(bytes, scheduled.actions.size());
        for (const auto &action : scheduled.actions) {
            append_u64(bytes, action.economy.value());
            append_text(bytes, action.lever);
            append_policy_value(bytes, action.value);
        }
    }
    append_text(bytes, occupant.artifact_path.generic_string());
    append_u64(bytes, occupant.action_dimensions.size());
    for (const auto &dimension : occupant.action_dimensions) {
        append_text(bytes, dimension);
    }
}

[[nodiscard]] core::StateDigest
seat_assignment_request_hash(const M11SeatAssignmentRequest &request) {
    std::vector<std::uint8_t> bytes;
    bytes.reserve(128U + request.operation_id.size() + request.actor.size() +
                  request.seat.size());
    bytes.push_back(static_cast<std::uint8_t>(M11SeatOperationKind::assignment));
    append_text(bytes, request.operation_id);
    append_text(bytes, request.actor);
    append_u64(bytes, request.economy.value());
    append_text(bytes, request.seat);
    append_occupant(bytes, request.occupant);
    return core::sha256_digest(bytes);
}

[[nodiscard]] core::StateDigest
seat_restore_request_hash(const M11SeatRestoreRequest &request) {
    std::vector<std::uint8_t> bytes;
    bytes.reserve(128U + request.operation_id.size() + request.actor.size() +
                  request.seat.size() + request.archived_occupant_id.size());
    bytes.push_back(static_cast<std::uint8_t>(M11SeatOperationKind::restoration));
    append_text(bytes, request.operation_id);
    append_text(bytes, request.actor);
    append_u64(bytes, request.economy.value());
    append_text(bytes, request.seat);
    append_text(bytes, request.archived_occupant_id);
    return core::sha256_digest(bytes);
}

[[nodiscard]] std::string seat_archive_id(const core::StateDigest &request_hash) {
    return "occupant:" + request_hash.hex();
}

[[nodiscard]] const M11SeatOperationRecord *
seat_operation(const M11ControlledState &state,
               std::string_view operation_id) noexcept {
    const auto found =
        std::find_if(state.seat_operations.begin(), state.seat_operations.end(),
                     [&](const M11SeatOperationRecord &entry) {
                         return entry.operation_id == operation_id;
                     });
    return found == state.seat_operations.end() ? nullptr : &*found;
}

[[nodiscard]] bool occupant_active_elsewhere(const M11ControlledState &state,
                                             const M11SeatRuntime &candidate,
                                             EconomyId target_economy,
                                             std::string_view target_seat) noexcept {
    if (candidate.assignment.occupant.kind == M11OccupantKind::null_occupant) {
        return false;
    }
    return std::any_of(state.seats.begin(), state.seats.end(),
                       [&](const M11SeatRuntime &entry) {
                           return (entry.assignment.economy != target_economy ||
                                   entry.assignment.seat != target_seat) &&
                                  entry.assignment.occupant.kind ==
                                      candidate.assignment.occupant.kind &&
                                  entry.assignment.occupant.occupant_id ==
                                      candidate.assignment.occupant.occupant_id;
                       });
}

[[nodiscard]] bool valid_occupant_spec(const M11OccupantSpec &spec) noexcept {
    return !spec.occupant_id.empty() && spec.occupant_id.size() <= 128U &&
           std::isfinite(spec.random_action_probability) &&
           spec.random_action_probability >= 0.0 &&
           spec.random_action_probability <= 1.0 &&
           (spec.kind != M11OccupantKind::reinforcement_learning ||
            !spec.artifact_path.empty());
}

[[nodiscard]] bool valid_shock_authority(const M11ShockAuthority &authority,
                                         std::size_t economy_count) noexcept {
    if (authority.principal.empty() || authority.principal.size() > 128U ||
        authority.principal.find('\0') != std::string::npos ||
        authority.maximum_schedule_ahead_ticks == 0U ||
        authority.maximum_duration_ticks == 0U ||
        !std::isfinite(authority.maximum_absolute_magnitude) ||
        authority.maximum_absolute_magnitude < 0.0) {
        return false;
    }
    for (const auto &seat : authority.granted_seats) {
        if (!m11_valid_seat(seat)) {
            return false;
        }
    }
    for (const auto kind : authority.allowed_kinds) {
        if (static_cast<std::uint8_t>(kind) >
            static_cast<std::uint8_t>(simulation::ShockKind::capital_outflow_pressure)) {
            return false;
        }
    }
    for (const auto economy : authority.allowed_economies) {
        if (economy.value() >= economy_count) {
            return false;
        }
    }
    return !authority.allowed_kinds.empty();
}

[[nodiscard]] std::string
shock_input_payload(const M11ControlledShockScheduleRequest &request) {
    const auto &shock = request.shock;
    std::ostringstream payload;
    payload << std::setprecision(17) << "principal=" << request.principal
            << "|actor=" << request.actor
            << "|seat=" << (request.seat.has_value() ? *request.seat : "")
            << "|id=" << shock.id << "|kind=" << static_cast<unsigned>(shock.kind)
            << "|economy=";
    if (shock.economy.has_value()) {
        payload << shock.economy->value();
    } else {
        payload << "global";
    }
    payload << "|start=" << shock.start.value() << "|announcement=";
    if (shock.announcement.has_value()) {
        payload << shock.announcement->value();
    } else {
        payload << "none";
    }
    payload << "|duration=" << shock.duration << "|magnitude=" << shock.magnitude
            << "|shape=" << static_cast<unsigned>(shock.shape)
            << "|ramp_in=" << shock.ramp_in_ticks
            << "|ramp_out=" << shock.ramp_out_ticks << "|sector=";
    if (shock.sector.has_value()) {
        payload << static_cast<unsigned>(*shock.sector);
    } else {
        payload << "none";
    }
    return payload.str();
}

} // namespace

Result<CanonicalControllerEnvelope>
seal_m11_controller_state(Tick boundary, std::uint64_t policy_generation,
                          const M11ControlledState &state) {
    auto envelope = make_envelope(boundary, policy_generation, state);
    auto status = seal_controller_envelope(envelope);
    if (!status.ok()) {
        return status;
    }
    return envelope;
}

std::string_view m11_boundary_phase_name(M11BoundaryPhase phase) noexcept {
    switch (phase) {
    case M11BoundaryPhase::boundary_start:
        return "boundary_start";
    case M11BoundaryPhase::awaiting_human:
        return "awaiting_human";
    case M11BoundaryPhase::ready_to_commit:
        return "ready_to_commit";
    }
    return "unknown";
}

std::string_view m11_occupant_kind_name(M11OccupantKind kind) noexcept {
    switch (kind) {
    case M11OccupantKind::null_occupant:
        return "null";
    case M11OccupantKind::scheduled:
        return "scheduled";
    case M11OccupantKind::heuristic:
        return "heuristic";
    case M11OccupantKind::random_fuzz:
        return "random_fuzz";
    case M11OccupantKind::human_queue:
        return "human_queue";
    case M11OccupantKind::reinforcement_learning:
        return "reinforcement_learning";
    }
    return "unknown";
}

Result<M11ControlledSession>
M11ControlledSession::create(EngineSession engine, M11ControllerRunSpec run_spec) {
    if (run_spec.worker_count == 0U || run_spec.maximum_events == 0U ||
        run_spec.maximum_releases == 0U ||
        run_spec.maximum_events > kM11MaximumControllerEvents ||
        run_spec.maximum_releases > kM11MaximumControllerReleases) {
        return invalid_session("M11 run specification is invalid");
    }
    run_spec.advance_options.worker_count = run_spec.worker_count;
    std::sort(run_spec.shock_authorities.begin(), run_spec.shock_authorities.end(),
              [](const M11ShockAuthority &left, const M11ShockAuthority &right) {
                  return left.principal < right.principal;
              });
    if (std::adjacent_find(
            run_spec.shock_authorities.begin(), run_spec.shock_authorities.end(),
            [](const M11ShockAuthority &left, const M11ShockAuthority &right) {
                return left.principal == right.principal;
            }) != run_spec.shock_authorities.end() ||
        std::any_of(run_spec.shock_authorities.begin(),
                    run_spec.shock_authorities.end(),
                    [&](const M11ShockAuthority &authority) {
                        return !valid_shock_authority(authority,
                                                      engine.world().economy_count());
                    })) {
        return invalid_session("M11 shock authority specification is invalid");
    }
    auto scheduler =
        M11DecisionScheduler::create(run_spec.calendars, run_spec.triggers);
    auto coordinator = M11PolicyCoordinator::create(engine.world(), run_spec.cost_spec);
    if (!scheduler.ok()) {
        return scheduler.status();
    }
    if (!coordinator.ok()) {
        return coordinator.status();
    }
    M11ControlledState state(std::move(*scheduler.get_if()),
                             std::move(*coordinator.get_if()),
                             M11EventStream(run_spec.maximum_events),
                             M11ReleaseStream(run_spec.maximum_releases));

    std::vector<M11SeatAssignment> assignments = run_spec.assignments;
    for (const auto &assignment : assignments) {
        if (assignment.economy.value() >= engine.world().economy_count() ||
            !m11_valid_seat(assignment.seat) ||
            !valid_occupant_spec(assignment.occupant)) {
            return invalid_session("M11 seat assignment is invalid");
        }
    }
    std::sort(assignments.begin(), assignments.end(),
              [](const M11SeatAssignment &left, const M11SeatAssignment &right) {
                  return std::pair{left.economy.value(), left.seat} <
                         std::pair{right.economy.value(), right.seat};
              });
    if (std::adjacent_find(
            assignments.begin(), assignments.end(),
            [](const M11SeatAssignment &left, const M11SeatAssignment &right) {
                return left.economy == right.economy && left.seat == right.seat;
            }) != assignments.end()) {
        return invalid_session("M11 seat assignments contain duplicates");
    }
    if (run_spec.fill_unassigned_with_null) {
        for (std::size_t economy = 0U; economy < engine.world().economy_count();
             ++economy) {
            for (const auto seat : kM11Seats) {
                const auto found =
                    std::find_if(assignments.begin(), assignments.end(),
                                 [&](const M11SeatAssignment &assignment) {
                                     return assignment.economy == EconomyId(economy) &&
                                            assignment.seat == seat;
                                 });
                if (found == assignments.end()) {
                    assignments.push_back({
                        EconomyId(economy),
                        std::string(seat),
                        {},
                    });
                }
            }
        }
        std::sort(assignments.begin(), assignments.end(),
                  [](const M11SeatAssignment &left, const M11SeatAssignment &right) {
                      return std::pair{left.economy.value(), left.seat} <
                             std::pair{right.economy.value(), right.seat};
                  });
    }
    for (auto &assignment : assignments) {
        M11SeatRuntime runtime;
        runtime.assignment = assignment;
        if (assignment.occupant.kind == M11OccupantKind::reinforcement_learning) {
            auto artifact =
                NativePolicyArtifact::load_file(assignment.occupant.artifact_path);
            if (!artifact.ok()) {
                return artifact.status();
            }
            if (runtime.assignment.occupant.action_dimensions.empty()) {
                runtime.assignment.occupant.action_dimensions =
                    artifact.get_if()->info().action_levers;
            }
            if (runtime.assignment.occupant.action_dimensions !=
                    artifact.get_if()->info().action_levers ||
                runtime.assignment.occupant.action_dimensions.size() !=
                    artifact.get_if()->info().action_dimension) {
                return Status(ErrorCode::contract_violation,
                              "M11 artifact action dimensions differ");
            }
            for (const auto &lever_name :
                 runtime.assignment.occupant.action_dimensions) {
                const auto *lever = find_m11_policy_lever(lever_name);
                if (lever == nullptr || lever->owner_role != assignment.seat) {
                    return Status(ErrorCode::contract_violation,
                                  "M11 artifact seat contract differs");
                }
            }
            runtime.artifact_sha256 = artifact.get_if()->info().artifact_sha256;
            runtime.artifact = std::move(*artifact.get_if());
        }
        state.seats.push_back(std::move(runtime));
    }
    run_spec.assignments = assignments;

    auto initial = make_envelope(engine.tick(), engine.policy_generation(), state);
    auto sealed = seal_controller_envelope(initial);
    if (!sealed.ok()) {
        return sealed;
    }
    auto bridge = HybridControlledBridge::create(std::move(engine), std::move(initial));
    if (!bridge.ok()) {
        return bridge.status();
    }
    return M11ControlledSession(std::move(*bridge.get_if()), std::move(run_spec),
                                std::move(state));
}

const M11SeatRuntime *
M11ControlledSession::seat(EconomyId economy,
                           std::string_view seat_name) const noexcept {
    const auto found = std::find_if(state_.seats.begin(), state_.seats.end(),
                                    [&](const M11SeatRuntime &entry) {
                                        return entry.assignment.economy == economy &&
                                               entry.assignment.seat == seat_name;
                                    });
    return found == state_.seats.end() ? nullptr : &*found;
}

Status M11ControlledSession::synchronize_state(std::string operation_id,
                                               M11ControlledState next) {
    auto envelope = make_envelope(bridge_.engine().tick(),
                                  bridge_.engine().policy_generation(), next);
    auto sealed = seal_controller_envelope(envelope);
    if (!sealed.ok()) {
        return sealed;
    }
    ControllerEnvelopeTransition transition{
        std::move(operation_id),
        bridge_.controller_envelope().hash,
        std::move(envelope),
    };
    auto receipt = bridge_.update_controller(transition);
    if (!receipt.ok()) {
        return receipt.status();
    }
    state_ = std::move(next);
    return bridge_.acknowledge_receipt(receipt.get_if()->operation_id);
}

Result<M11PolicyProposal>
M11ControlledSession::automatic_proposal(M11SeatRuntime &seat_runtime,
                                         const M11DecisionContext &context) const {
    const auto counter = seat_runtime.decision_counter++;
    const auto suffix =
        std::to_string(context.boundary.value()) + ":" + std::to_string(counter);
    M11PolicyProposal proposal;
    proposal.proposal_id = "proposal:" + seat_runtime.assignment.occupant.occupant_id +
                           ":" + context.context_id + ":" + suffix;
    proposal.idempotency_key = proposal.proposal_id;
    proposal.context_id = context.context_id;
    proposal.based_on_policy_versions = proposal_versions(context);
    proposal.reason =
        std::string(m11_occupant_kind_name(seat_runtime.assignment.occupant.kind));

    const auto &occupant = seat_runtime.assignment.occupant;
    if (occupant.kind == M11OccupantKind::null_occupant) {
        return proposal;
    }
    if (occupant.kind == M11OccupantKind::human_queue) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 human occupant cannot propose automatically");
    }
    if (occupant.kind == M11OccupantKind::scheduled) {
        const auto scheduled =
            std::find_if(occupant.schedule.begin(), occupant.schedule.end(),
                         [&](const M11ScheduledPolicyActions &entry) {
                             return entry.boundary == context.boundary &&
                                    (entry.decision_group.empty() ||
                                     entry.decision_group == context.decision_group);
                         });
        if (scheduled != occupant.schedule.end()) {
            proposal.actions = scheduled->actions;
        }
        return proposal;
    }
    if (occupant.kind == M11OccupantKind::heuristic) {
        const auto *target = permitted(context, "gov_deficit_target");
        const auto unemployment = released_value(context, "unemployment_rate");
        const auto inflation = released_value(context, "inflation");
        if (target != nullptr && target->allowed && unemployment.has_value() &&
            inflation.has_value()) {
            std::uint32_t direction = 1U;
            if (*unemployment > 0.10 && *inflation < 0.01) {
                direction = 2U;
            } else if (*unemployment < 0.06 || *inflation > 0.02) {
                direction = 0U;
            }
            const auto *lever = find_m11_policy_lever("gov_deficit_target");
            auto value = directional_value(*lever, target->current_value, direction,
                                           context.economy,
                                           bridge_.engine().world().economy_count());
            if (!value.ok()) {
                return value.status();
            }
            if (!m11_policy_values_equal(*value.get_if(), target->current_value)) {
                proposal.actions.push_back({context.economy, "gov_deficit_target",
                                            std::move(*value.get_if())});
            }
        }
        return proposal;
    }
    if (occupant.kind == M11OccupantKind::random_fuzz) {
        auto entropy = mix64(occupant.seed ^ context.boundary.value() ^ mix64(counter) ^
                             stable_string_hash(context.context_id));
        if (unit_random(entropy) > occupant.random_action_probability) {
            return proposal;
        }
        std::vector<const M11PermittedAction *> choices;
        for (const auto &entry : context.permitted_actions) {
            if (entry.allowed) {
                choices.push_back(&entry);
            }
        }
        if (choices.empty()) {
            return proposal;
        }
        entropy = mix64(entropy);
        const auto *entry = choices[entropy % choices.size()];
        const auto direction = (mix64(entropy) & 1U) == 0U ? 0U : 2U;
        const auto *lever = find_m11_policy_lever(entry->lever);
        auto value =
            directional_value(*lever, entry->current_value, direction, context.economy,
                              bridge_.engine().world().economy_count());
        if (!value.ok()) {
            return value.status();
        }
        if (!m11_policy_values_equal(*value.get_if(), entry->current_value)) {
            proposal.actions.push_back(
                {context.economy, entry->lever, std::move(*value.get_if())});
        }
        return proposal;
    }
    if (occupant.kind == M11OccupantKind::reinforcement_learning) {
        if (!seat_runtime.artifact.has_value()) {
            return Status(ErrorCode::invalid_transaction_state,
                          "M11 RL artifact is not loaded");
        }
        const auto &artifact = *seat_runtime.artifact;
        const auto features =
            encode_artifact_context(artifact, state_.coordinator, context,
                                    bridge_.engine().world().economy_count());
        std::vector<std::uint8_t> mask(artifact.info().action_dimension * 3U, 0U);
        for (std::size_t index = 0U; index < occupant.action_dimensions.size();
             ++index) {
            mask[index * 3U + 1U] = 1U;
            const auto *entry = permitted(context, occupant.action_dimensions[index]);
            if (entry == nullptr || !entry->allowed) {
                continue;
            }
            const auto *lever = find_m11_policy_lever(entry->lever);
            for (const auto direction : {0U, 2U}) {
                auto value = directional_value(
                    *lever, entry->current_value, direction, context.economy,
                    bridge_.engine().world().economy_count());
                if (value.ok() &&
                    !m11_policy_values_equal(*value.get_if(), entry->current_value)) {
                    mask[index * 3U + direction] = 1U;
                }
            }
        }
        auto codes = artifact.predict_codes(features, mask);
        if (!codes.ok()) {
            return codes.status();
        }
        for (std::size_t index = 0U; index < codes.get_if()->size(); ++index) {
            const auto direction = (*codes.get_if())[index];
            if (direction == 1U) {
                continue;
            }
            const auto *entry = permitted(context, occupant.action_dimensions[index]);
            if (entry == nullptr || !entry->allowed) {
                continue;
            }
            const auto *lever = find_m11_policy_lever(entry->lever);
            auto value = directional_value(*lever, entry->current_value, direction,
                                           context.economy,
                                           bridge_.engine().world().economy_count());
            if (!value.ok()) {
                return value.status();
            }
            if (!m11_policy_values_equal(*value.get_if(), entry->current_value)) {
                proposal.actions.push_back(
                    {context.economy, entry->lever, std::move(*value.get_if())});
            }
        }
        return proposal;
    }
    return invalid_session("M11 occupant kind is invalid");
}

Result<M11DecisionResult> M11ControlledSession::run_boundary_prelude() {
    if (state_.phase != M11BoundaryPhase::boundary_start) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 boundary prelude is not available");
    }
    auto next = state_;
    next.opened_context_ids.clear();
    const auto boundary = bridge_.engine().tick();
    auto published = release_service_.publish_due(
        bridge_.engine().metrics(), bridge_.engine().world(), boundary,
        next.events.next_sequence(), next.releases);
    if (!published.ok()) {
        return published.status();
    }
    auto boundary_event = next.events.append(
        boundary, "boundary_started",
        "boundary:" + std::to_string(boundary.value()) + ":" +
            std::to_string(next.boundary_sequence),
        "scheduler", "released=" + std::to_string(*published.get_if()),
        M11EventVisibility::institution);
    if (!boundary_event.ok()) {
        return boundary_event.status();
    }

    std::vector<M11TriggerNotice> notices;
    for (std::size_t economy = 0U; economy < bridge_.engine().world().economy_count();
         ++economy) {
        const auto samples = release_service_.trigger_samples(
            next.releases, EconomyId(economy), boundary);
        auto evaluated =
            next.scheduler.evaluate_triggers(boundary, EconomyId(economy), samples);
        if (!evaluated.ok()) {
            return evaluated.status();
        }
        notices.insert(notices.end(), evaluated.get_if()->begin(),
                       evaluated.get_if()->end());
    }

    struct ContextSpec final {
        EconomyId economy{};
        std::string seat;
        std::string group;
        Tick expiry{};
        bool emergency{false};
        std::string trigger;
        double trigger_value{0.0};
    };
    std::vector<ContextSpec> context_specs;
    for (std::size_t economy = 0U; economy < bridge_.engine().world().economy_count();
         ++economy) {
        for (const auto &calendar : next.scheduler.calendars()) {
            if (!next.scheduler.due(calendar.decision_group, boundary,
                                    EconomyId(economy))) {
                continue;
            }
            const auto owner = owner_for_group(calendar.decision_group);
            if (owner.empty() || seat(EconomyId(economy), owner) == nullptr) {
                continue;
            }
            context_specs.push_back({
                EconomyId(economy),
                std::string(owner),
                calendar.decision_group,
                Tick(boundary.value() + calendar.window_ticks - 1U),
                false,
                {},
                0.0,
            });
        }
    }
    for (const auto &notice : notices) {
        for (const auto &seat_name : notice.seats) {
            if (seat(notice.economy, seat_name) == nullptr) {
                continue;
            }
            context_specs.push_back({
                notice.economy,
                seat_name,
                notice.decision_group,
                notice.expires_at,
                true,
                notice.trigger_id,
                notice.value,
            });
        }
    }
    std::sort(context_specs.begin(), context_specs.end(),
              [](const ContextSpec &left, const ContextSpec &right) {
                  return std::tuple{left.economy.value(), left.seat, left.group,
                                    left.emergency, left.trigger} <
                         std::tuple{right.economy.value(), right.seat, right.group,
                                    right.emergency, right.trigger};
              });

    M11DecisionResult result;
    result.boundary = boundary;
    for (const auto &spec : context_specs) {
        auto observation = release_service_.observation(next.releases, spec.economy,
                                                        boundary, spec.seat);
        if (!observation.ok()) {
            return observation.status();
        }
        const auto elapsed = previous_context_elapsed(next.coordinator, spec.economy,
                                                      spec.seat, spec.group, boundary);
        auto opened = next.coordinator.open_context(
            bridge_.engine().world(), next.scheduler, boundary, spec.economy, spec.seat,
            spec.group, spec.expiry, spec.emergency, spec.trigger, elapsed,
            *observation.get_if());
        if (!opened.ok()) {
            return opened.status();
        }
        next.opened_context_ids.push_back(opened.get_if()->context_id);
        result.opened_context_ids.push_back(opened.get_if()->context_id);
        auto event = next.events.append(
            boundary, "decision_context_opened",
            "context-open:" + opened.get_if()->context_id, "scheduler",
            "group=" + spec.group + "|emergency=" + (spec.emergency ? "1" : "0"),
            M11EventVisibility::institution);
        if (!event.ok()) {
            return event.status();
        }
        if (spec.emergency) {
            auto emergency = next.events.append(
                boundary, "emergency_trigger", "trigger:" + opened.get_if()->context_id,
                "scheduler",
                "trigger=" + spec.trigger +
                    "|value=" + std::to_string(spec.trigger_value),
                M11EventVisibility::public_record);
            if (!emergency.ok()) {
                return emergency.status();
            }
        }
    }
    std::sort(next.opened_context_ids.begin(), next.opened_context_ids.end());
    std::sort(result.opened_context_ids.begin(), result.opened_context_ids.end());

    for (const auto &context_id : next.opened_context_ids) {
        const auto *context = next.coordinator.find_context(context_id);
        if (context == nullptr) {
            return Status(ErrorCode::internal_error, "M11 opened context is missing");
        }
        auto runtime = std::find_if(
            next.seats.begin(), next.seats.end(), [&](const M11SeatRuntime &entry) {
                return entry.assignment.economy == context->economy &&
                       entry.assignment.seat == context->seat;
            });
        if (runtime == next.seats.end()) {
            return Status(ErrorCode::internal_error, "M11 context seat is unassigned");
        }
        if (runtime->assignment.occupant.kind == M11OccupantKind::human_queue) {
            continue;
        }
        auto proposal = automatic_proposal(*runtime, *context);
        if (!proposal.ok()) {
            return proposal.status();
        }
        auto decision = next.coordinator.submit(
            bridge_.engine().world(), next.scheduler, boundary,
            std::move(*proposal.get_if()), runtime->assignment.occupant.occupant_id,
            next.events);
        if (!decision.ok()) {
            return decision.status();
        }
        result.decisions.push_back(*decision.get_if());
    }
    next.phase = has_unanswered_human(next) ? M11BoundaryPhase::awaiting_human
                                            : M11BoundaryPhase::ready_to_commit;
    result.phase = next.phase;
    result.awaiting_human = next.phase == M11BoundaryPhase::awaiting_human;
    auto operation_id = "m11-prelude:" + std::to_string(boundary.value()) + ":" +
                        std::to_string(next.boundary_sequence);
    auto synchronized = synchronize_state(std::move(operation_id), std::move(next));
    if (!synchronized.ok()) {
        return synchronized;
    }
    return result;
}

Result<M11DecisionResult> M11ControlledSession::commit_ready_boundary(
    std::span<const NativePolicyAction> free_policy_actions) {
    if (state_.phase != M11BoundaryPhase::ready_to_commit) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 boundary is not ready to commit");
    }
    const auto boundary = bridge_.engine().tick();
    auto next = state_;
    auto plan = next.coordinator.prepare_due(bridge_.engine().world(), boundary);
    if (!plan.ok()) {
        return plan.status();
    }
    auto committed_plan = next.coordinator.commit_due(*plan.get_if(), next.events);
    if (!committed_plan.ok()) {
        return committed_plan;
    }
    std::optional<simulation::WorldPolicyBatch> free_policy_batch;
    if (!free_policy_actions.empty()) {
        if (!plan.get_if()->effective_changes.empty()) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "M11 free policy cannot share a boundary with controller policy");
        }
        auto prepared = prepare_m11_free_policy_batch(bridge_.engine().world(),
                                                      free_policy_actions);
        if (!prepared.ok()) {
            return prepared.status();
        }
        free_policy_batch = std::move(*prepared.get_if());
        auto policy_event = next.events.append(
            boundary, "free_policy_effective",
            "free-policy:" + std::to_string(boundary.value()) + ":" +
                std::to_string(next.boundary_sequence),
            "player", "actions=" + std::to_string(free_policy_actions.size()),
            M11EventVisibility::public_record);
        if (!policy_event.ok()) {
            return policy_event.status();
        }
    }
    auto event = next.events.append(
        boundary, "boundary_committing",
        "boundary-commit:" + std::to_string(boundary.value()) + ":" +
            std::to_string(next.boundary_sequence),
        "scheduler",
        "effective=" + std::to_string(plan.get_if()->effective_decision_ids.size()) +
            "|failed=" + std::to_string(plan.get_if()->failed_decision_ids.size()),
        M11EventVisibility::institution);
    if (!event.ok()) {
        return event.status();
    }
    next.phase = M11BoundaryPhase::boundary_start;
    next.opened_context_ids.clear();
    ++next.boundary_sequence;

    SealedControlBatch batch;
    batch.operation_id = "m11-engine-boundary:" + std::to_string(boundary.value()) +
                         ":" + std::to_string(next.boundary_sequence);
    batch.expected_controller_hash = bridge_.controller_envelope().hash;
    batch.policies = free_policy_batch.has_value() ? std::move(*free_policy_batch)
                                                   : plan.get_if()->policy_batch;
    batch.advance_ticks = 1U;
    batch.advance_options = run_spec_.advance_options;
    auto lease = bridge_.prepare_boundary(batch);
    if (!lease.ok()) {
        return lease.status();
    }
    auto envelope = make_envelope(lease.get_if()->preview().next_tick,
                                  lease.get_if()->preview().policy_generation, next);
    auto sealed = seal_controller_envelope(envelope);
    if (!sealed.ok()) {
        (void)bridge_.abort_boundary(std::move(*lease.get_if()));
        return sealed;
    }
    auto advanced =
        bridge_.commit_boundary(std::move(*lease.get_if()), std::move(envelope));
    if (!advanced.ok()) {
        if (lease.get_if()->active()) {
            (void)bridge_.abort_boundary(std::move(*lease.get_if()));
        }
        return advanced.status();
    }
    state_ = std::move(next);
    M11DecisionResult result;
    result.phase = state_.phase;
    result.boundary = bridge_.engine().tick();
    result.elapsed_ticks = 1U;
    result.advance = *advanced.get_if();
    return result;
}

Result<M11DecisionResult>
M11ControlledSession::advance_until_decision(const M11AdvanceLimit &limit) {
    if (limit.maximum_ticks == 0U) {
        return invalid_session("M11 advance limit must be positive");
    }
    M11DecisionResult aggregate;
    aggregate.phase = state_.phase;
    aggregate.boundary = bridge_.engine().tick();
    if (state_.phase == M11BoundaryPhase::awaiting_human) {
        aggregate.awaiting_human = true;
        aggregate.opened_context_ids = state_.opened_context_ids;
        return aggregate;
    }
    bool boundary_had_context = false;
    while (aggregate.elapsed_ticks < limit.maximum_ticks) {
        if (state_.phase == M11BoundaryPhase::boundary_start) {
            auto prelude = run_boundary_prelude();
            if (!prelude.ok()) {
                return prelude.status();
            }
            boundary_had_context = !prelude.get_if()->opened_context_ids.empty();
            aggregate.opened_context_ids = prelude.get_if()->opened_context_ids;
            aggregate.decisions.insert(aggregate.decisions.end(),
                                       prelude.get_if()->decisions.begin(),
                                       prelude.get_if()->decisions.end());
            if (prelude.get_if()->awaiting_human) {
                aggregate.phase = state_.phase;
                aggregate.boundary = bridge_.engine().tick();
                aggregate.awaiting_human = true;
                return aggregate;
            }
        }
        auto committed = commit_ready_boundary();
        if (!committed.ok()) {
            return committed.status();
        }
        ++aggregate.elapsed_ticks;
        aggregate.advance = committed.get_if()->advance;
        aggregate.phase = state_.phase;
        aggregate.boundary = bridge_.engine().tick();
        if (limit.stop_after_context_boundary && boundary_had_context) {
            return aggregate;
        }
        boundary_had_context = false;
    }
    aggregate.limit_reached = true;
    return aggregate;
}

Result<M11DecisionResult>
M11ControlledSession::advance_free_policy(std::span<const NativePolicyAction> actions,
                                          const M11AdvanceLimit &limit) {
    if (limit.maximum_ticks == 0U) {
        return invalid_session("M11 advance limit must be positive");
    }
    if (state_.phase != M11BoundaryPhase::boundary_start) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 free policy requires a clean boundary");
    }
    auto prepared = prepare_m11_free_policy_batch(bridge_.engine().world(), actions);
    if (!prepared.ok()) {
        return prepared.status();
    }

    M11DecisionResult aggregate;
    aggregate.phase = state_.phase;
    aggregate.boundary = bridge_.engine().tick();
    bool first_boundary = true;
    while (aggregate.elapsed_ticks < limit.maximum_ticks) {
        if (state_.phase == M11BoundaryPhase::boundary_start) {
            auto prelude = run_boundary_prelude();
            if (!prelude.ok()) {
                return prelude.status();
            }
            aggregate.opened_context_ids = prelude.get_if()->opened_context_ids;
            aggregate.decisions.insert(aggregate.decisions.end(),
                                       prelude.get_if()->decisions.begin(),
                                       prelude.get_if()->decisions.end());
            if (prelude.get_if()->awaiting_human) {
                aggregate.phase = state_.phase;
                aggregate.boundary = bridge_.engine().tick();
                aggregate.awaiting_human = true;
                return aggregate;
            }
        }
        auto committed = commit_ready_boundary(
            first_boundary ? actions : std::span<const NativePolicyAction>{});
        if (!committed.ok()) {
            return committed.status();
        }
        first_boundary = false;
        ++aggregate.elapsed_ticks;
        aggregate.advance = committed.get_if()->advance;
        aggregate.phase = state_.phase;
        aggregate.boundary = bridge_.engine().tick();
    }
    aggregate.limit_reached = true;
    return aggregate;
}

Result<M11PolicyDecision>
M11ControlledSession::submit_policy_proposal(M11PolicyProposal proposal,
                                             std::string_view actor) {
    if (state_.phase != M11BoundaryPhase::awaiting_human &&
        state_.phase != M11BoundaryPhase::ready_to_commit) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 proposal ingress is not open");
    }
    auto next = state_;
    auto decision = next.coordinator.submit(bridge_.engine().world(), next.scheduler,
                                            bridge_.engine().tick(),
                                            std::move(proposal), actor, next.events);
    if (!decision.ok()) {
        return decision.status();
    }
    next.phase = has_unanswered_human(next) ? M11BoundaryPhase::awaiting_human
                                            : M11BoundaryPhase::ready_to_commit;
    auto status = synchronize_state("m11-proposal:" + decision.get_if()->decision_id,
                                    std::move(next));
    if (!status.ok()) {
        return status;
    }
    return *decision.get_if();
}

Result<M11PolicyDecision>
M11ControlledSession::submit_human_proposal(M11PolicyProposal proposal,
                                            std::string_view actor) {
    const auto *context = state_.coordinator.find_context(proposal.context_id);
    if (state_.phase != M11BoundaryPhase::awaiting_human || context == nullptr) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 human proposal is not currently expected");
    }
    const auto *runtime = seat(context->economy, context->seat);
    if (runtime == nullptr ||
        runtime->assignment.occupant.kind != M11OccupantKind::human_queue) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 context is not assigned to a human queue");
    }
    return submit_policy_proposal(std::move(proposal), actor);
}

Result<M11PolicyDecision>
M11ControlledSession::timeout_context(std::string_view context_id,
                                      std::string_view operation_id,
                                      std::string_view actor) {
    const auto *context = state_.coordinator.find_context(context_id);
    if (context == nullptr) {
        return Status(ErrorCode::not_found, "M11 context was not found");
    }
    M11PolicyProposal proposal;
    proposal.proposal_id = "timeout:" + std::string(operation_id);
    proposal.idempotency_key = std::string(operation_id);
    proposal.context_id = std::string(context_id);
    proposal.based_on_policy_versions = proposal_versions(*context);
    proposal.reason = "timeout";
    return submit_policy_proposal(std::move(proposal), actor);
}

Result<M11PolicyDecision>
M11ControlledSession::cancel_pending(std::string_view decision_id,
                                     std::string_view operation_id,
                                     std::string_view actor) {
    auto next = state_;
    auto decision = next.coordinator.cancel(bridge_.engine().tick(), decision_id,
                                            operation_id, actor, next.events);
    if (!decision.ok()) {
        return decision.status();
    }
    auto status =
        synchronize_state("m11-cancel:" + std::string(operation_id), std::move(next));
    if (!status.ok()) {
        return status;
    }
    return *decision.get_if();
}

Result<M11SeatChangeResult>
M11ControlledSession::assign_seat(const M11SeatAssignmentRequest &request) {
    if (request.operation_id.empty() ||
        request.operation_id.size() > kM10MaximumOperationIdBytes ||
        request.operation_id.find('\0') != std::string::npos || request.actor.empty() ||
        request.economy.value() >= bridge_.engine().world().economy_count() ||
        !m11_valid_seat(request.seat) || !valid_occupant_spec(request.occupant)) {
        return invalid_session("M11 seat assignment request is invalid");
    }
    const auto request_hash = seat_assignment_request_hash(request);
    if (const auto *existing = seat_operation(state_, request.operation_id);
        existing != nullptr) {
        if (existing->kind != M11SeatOperationKind::assignment ||
            existing->request_hash != request_hash) {
            return Status(ErrorCode::already_exists,
                          "M11 seat operation ID payload differs");
        }
        return M11SeatChangeResult{existing->archived_occupant_id, true};
    }
    if (state_.phase != M11BoundaryPhase::boundary_start) {
        return invalid_session("M11 seat assignment requires a boundary start");
    }
    auto next = state_;
    auto runtime = std::find_if(
        next.seats.begin(), next.seats.end(), [&](const M11SeatRuntime &entry) {
            return entry.assignment.economy == request.economy &&
                   entry.assignment.seat == request.seat;
        });
    M11SeatRuntime replacement;
    replacement.assignment = {request.economy, request.seat, request.occupant};
    if (request.occupant.kind == M11OccupantKind::reinforcement_learning) {
        auto artifact = NativePolicyArtifact::load_file(request.occupant.artifact_path);
        if (!artifact.ok()) {
            return artifact.status();
        }
        if (replacement.assignment.occupant.action_dimensions.empty()) {
            replacement.assignment.occupant.action_dimensions =
                artifact.get_if()->info().action_levers;
        }
        if (replacement.assignment.occupant.action_dimensions !=
            artifact.get_if()->info().action_levers) {
            return Status(ErrorCode::contract_violation,
                          "M11 artifact action dimensions differ");
        }
        replacement.artifact_sha256 = artifact.get_if()->info().artifact_sha256;
        replacement.artifact = std::move(*artifact.get_if());
    }
    if (occupant_active_elsewhere(next, replacement, request.economy, request.seat)) {
        return Status(ErrorCode::already_exists,
                      "M11 occupant is already assigned to another seat");
    }
    std::optional<std::string> archived_occupant_id;
    if (runtime == next.seats.end()) {
        next.seats.push_back(std::move(replacement));
    } else {
        archived_occupant_id = seat_archive_id(request_hash);
        next.archived_seat_occupants.push_back({
            *archived_occupant_id,
            std::move(*runtime),
        });
        *runtime = std::move(replacement);
    }
    std::sort(
        next.seats.begin(), next.seats.end(),
        [](const M11SeatRuntime &left, const M11SeatRuntime &right) {
            return std::pair{left.assignment.economy.value(), left.assignment.seat} <
                   std::pair{right.assignment.economy.value(), right.assignment.seat};
        });
    std::sort(
        next.archived_seat_occupants.begin(), next.archived_seat_occupants.end(),
        [](const M11ArchivedSeatOccupant &left, const M11ArchivedSeatOccupant &right) {
            return left.archive_id < right.archive_id;
        });
    next.seat_operations.push_back({
        request.operation_id,
        M11SeatOperationKind::assignment,
        request_hash,
        archived_occupant_id,
    });
    auto event = next.events.append(
        bridge_.engine().tick(), "seat_assigned", request.operation_id, request.actor,
        "economy=" + std::to_string(request.economy.value()) + "|seat=" + request.seat +
            "|occupant=" + std::string(m11_occupant_kind_name(request.occupant.kind)) +
            "|archived=" +
            (archived_occupant_id.has_value() ? *archived_occupant_id : ""),
        M11EventVisibility::privileged_audit);
    if (!event.ok()) {
        return event.status();
    }
    const auto status =
        synchronize_state("m11-seat:" + request_hash.hex(), std::move(next));
    if (!status.ok()) {
        return status;
    }
    return M11SeatChangeResult{std::move(archived_occupant_id), false};
}

Result<M11SeatChangeResult>
M11ControlledSession::restore_seat(const M11SeatRestoreRequest &request) {
    if (request.operation_id.empty() ||
        request.operation_id.size() > kM10MaximumOperationIdBytes ||
        request.operation_id.find('\0') != std::string::npos || request.actor.empty() ||
        request.economy.value() >= bridge_.engine().world().economy_count() ||
        !m11_valid_seat(request.seat) || request.archived_occupant_id.empty() ||
        request.archived_occupant_id.size() > 256U ||
        request.archived_occupant_id.find('\0') != std::string::npos) {
        return invalid_session("M11 seat restoration request is invalid");
    }
    const auto request_hash = seat_restore_request_hash(request);
    if (const auto *existing = seat_operation(state_, request.operation_id);
        existing != nullptr) {
        if (existing->kind != M11SeatOperationKind::restoration ||
            existing->request_hash != request_hash) {
            return Status(ErrorCode::already_exists,
                          "M11 seat operation ID payload differs");
        }
        return M11SeatChangeResult{existing->archived_occupant_id, true};
    }
    if (state_.phase != M11BoundaryPhase::boundary_start) {
        return invalid_session("M11 seat restoration requires a boundary start");
    }

    auto next = state_;
    const auto archived = std::find_if(
        next.archived_seat_occupants.begin(), next.archived_seat_occupants.end(),
        [&](const M11ArchivedSeatOccupant &entry) {
            return entry.archive_id == request.archived_occupant_id;
        });
    if (archived == next.archived_seat_occupants.end()) {
        return Status(ErrorCode::not_found, "M11 archived seat occupant was not found");
    }
    if (archived->runtime.assignment.economy != request.economy ||
        archived->runtime.assignment.seat != request.seat) {
        return Status(ErrorCode::contract_violation,
                      "M11 archived occupant belongs to another seat");
    }
    if (occupant_active_elsewhere(next, archived->runtime, request.economy,
                                  request.seat)) {
        return Status(ErrorCode::already_exists,
                      "M11 archived occupant is already active");
    }

    auto runtime = std::find_if(
        next.seats.begin(), next.seats.end(), [&](const M11SeatRuntime &entry) {
            return entry.assignment.economy == request.economy &&
                   entry.assignment.seat == request.seat;
        });
    auto restored = std::move(archived->runtime);
    next.archived_seat_occupants.erase(archived);
    std::optional<std::string> outgoing_archive_id;
    if (runtime == next.seats.end()) {
        next.seats.push_back(std::move(restored));
    } else {
        outgoing_archive_id = seat_archive_id(request_hash);
        next.archived_seat_occupants.push_back({
            *outgoing_archive_id,
            std::move(*runtime),
        });
        *runtime = std::move(restored);
    }
    std::sort(
        next.seats.begin(), next.seats.end(),
        [](const M11SeatRuntime &left, const M11SeatRuntime &right) {
            return std::pair{left.assignment.economy.value(), left.assignment.seat} <
                   std::pair{right.assignment.economy.value(), right.assignment.seat};
        });
    std::sort(
        next.archived_seat_occupants.begin(), next.archived_seat_occupants.end(),
        [](const M11ArchivedSeatOccupant &left, const M11ArchivedSeatOccupant &right) {
            return left.archive_id < right.archive_id;
        });
    next.seat_operations.push_back({
        request.operation_id,
        M11SeatOperationKind::restoration,
        request_hash,
        outgoing_archive_id,
    });
    auto event = next.events.append(
        bridge_.engine().tick(), "seat_restored", request.operation_id, request.actor,
        "economy=" + std::to_string(request.economy.value()) + "|seat=" + request.seat +
            "|restored=" + request.archived_occupant_id + "|archived=" +
            (outgoing_archive_id.has_value() ? *outgoing_archive_id : ""),
        M11EventVisibility::privileged_audit);
    if (!event.ok()) {
        return event.status();
    }
    const auto status =
        synchronize_state("m11-restore:" + request_hash.hex(), std::move(next));
    if (!status.ok()) {
        return status;
    }
    return M11SeatChangeResult{std::move(outgoing_archive_id), false};
}

Result<M11ShockScheduleResult>
M11ControlledSession::schedule_shock(const M11ControlledShockScheduleRequest &request) {
    if (request.operation_id.empty() ||
        request.operation_id.size() > kM10MaximumOperationIdBytes ||
        request.operation_id.find('\0') != std::string::npos ||
        request.principal.empty() || request.actor.empty() ||
        (request.seat.has_value() && !m11_valid_seat(*request.seat))) {
        return invalid_session("M11 controlled shock request is invalid");
    }
    const auto payload = shock_input_payload(request);
    for (const auto &event : state_.events.events()) {
        if (event.operation_id != request.operation_id) {
            continue;
        }
        if (event.event_type != "shock_scheduled_input" ||
            event.actor != request.actor || event.canonical_payload != payload) {
            return Status(ErrorCode::already_exists,
                          "M11 shock operation ID payload differs");
        }
        return M11ShockScheduleResult{request.shock.id, event.boundary, event.sequence,
                                      true};
    }
    const auto authority = std::lower_bound(
        run_spec_.shock_authorities.begin(), run_spec_.shock_authorities.end(),
        request.principal,
        [](const M11ShockAuthority &entry, std::string_view principal) {
            return entry.principal < principal;
        });
    if (authority == run_spec_.shock_authorities.end() ||
        authority->principal != request.principal) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 shock authority was not granted");
    }
    if (request.seat.has_value() &&
        std::find(authority->granted_seats.begin(), authority->granted_seats.end(),
                  *request.seat) == authority->granted_seats.end()) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 shock seat authority was not granted");
    }
    if (std::find(authority->allowed_kinds.begin(), authority->allowed_kinds.end(),
                  request.shock.kind) == authority->allowed_kinds.end()) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 shock kind authority was not granted");
    }
    if (request.shock.economy.has_value()) {
        if (!authority->allow_all_economies &&
            std::find(authority->allowed_economies.begin(),
                      authority->allowed_economies.end(),
                      *request.shock.economy) == authority->allowed_economies.end()) {
            return Status(ErrorCode::invalid_transaction_state,
                          "M11 shock economy authority was not granted");
        }
    } else if (!authority->allow_global) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 global shock authority was not granted");
    }
    const auto boundary = bridge_.engine().tick();
    const auto earliest = state_.phase == M11BoundaryPhase::boundary_start
                              ? boundary
                              : Tick(boundary.value() + 1U);
    const auto announcement = request.shock.announcement.value_or(request.shock.start);
    if (request.shock.start < earliest || announcement < earliest ||
        request.shock.start < announcement ||
        request.shock.start.value() - announcement.value() <
            authority->minimum_announcement_lead_ticks ||
        request.shock.start.value() - boundary.value() >
            authority->maximum_schedule_ahead_ticks ||
        request.shock.duration > authority->maximum_duration_ticks ||
        !std::isfinite(request.shock.magnitude) ||
        std::abs(request.shock.magnitude) > authority->maximum_absolute_magnitude) {
        return invalid_session("M11 shock timing or magnitude exceeds its authority");
    }

    auto next = state_;
    auto event = next.events.append(boundary, "shock_scheduled_input",
                                    request.operation_id, request.actor, payload,
                                    M11EventVisibility::privileged_audit);
    if (!event.ok()) {
        return event.status();
    }
    auto envelope = seal_m11_controller_state(
        bridge_.engine().tick(), bridge_.engine().policy_generation(), next);
    if (!envelope.ok()) {
        return envelope.status();
    }
    ControllerEnvelopeTransition transition{
        request.operation_id,
        bridge_.controller_envelope().hash,
        std::move(*envelope.get_if()),
    };
    auto receipt = bridge_.schedule_shock(request.shock, transition);
    if (!receipt.ok()) {
        return receipt.status();
    }
    state_ = std::move(next);
    auto acknowledged = bridge_.acknowledge_receipt(receipt.get_if()->operation_id);
    if (!acknowledged.ok()) {
        return acknowledged;
    }
    return M11ShockScheduleResult{request.shock.id, boundary, event.get_if()->sequence,
                                  false};
}

bool M11ControlledSession::has_unanswered_human_context() const noexcept {
    return has_unanswered_human(state_);
}

Result<M11ControlledSession> M11ControlledSession::clone() const {
    auto bridge = bridge_.clone();
    if (!bridge.ok()) {
        return bridge.status();
    }
    return M11ControlledSession(std::move(*bridge.get_if()), run_spec_, state_);
}

} // namespace macro_sim::control
