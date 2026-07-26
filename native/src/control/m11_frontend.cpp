#include "macro_sim/control/m11_frontend.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

#include "macro_sim/reporting/m10.hpp"

namespace macro_sim::control {
namespace {

void append_u64(std::vector<std::uint8_t> &bytes,
                std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(
            static_cast<std::uint8_t>(value >> shift));
    }
}

void append_string(std::vector<std::uint8_t> &bytes,
                   std::string_view value) {
    append_u64(bytes, static_cast<std::uint64_t>(value.size()));
    bytes.insert(bytes.end(), value.begin(), value.end());
}

void append_bool(std::vector<std::uint8_t> &bytes, bool value) {
    bytes.push_back(value ? 1U : 0U);
}

void append_double(std::vector<std::uint8_t> &bytes,
                   double value) {
    append_u64(bytes, std::bit_cast<std::uint64_t>(value));
}

void append_optional_tick(std::vector<std::uint8_t> &bytes,
                          std::optional<Tick> value) {
    append_bool(bytes, value.has_value());
    if (value.has_value()) {
        append_u64(bytes, value->value());
    }
}

void append_optional_string(
    std::vector<std::uint8_t> &bytes,
    const std::optional<std::string> &value) {
    append_bool(bytes, value.has_value());
    if (value.has_value()) {
        append_string(bytes, *value);
    }
}

void append_policy_value(std::vector<std::uint8_t> &bytes,
                         const PolicyValue &value) {
    bytes.push_back(static_cast<std::uint8_t>(value.index()));
    if (const auto *boolean = std::get_if<bool>(&value);
        boolean != nullptr) {
        bytes.push_back(*boolean ? 1U : 0U);
    } else if (const auto *integer =
                   std::get_if<std::int64_t>(&value);
               integer != nullptr) {
        append_u64(bytes, std::bit_cast<std::uint64_t>(*integer));
    } else if (const auto *number =
                   std::get_if<double>(&value);
               number != nullptr) {
        append_double(bytes, *number);
    } else if (const auto *choice =
                   std::get_if<std::string>(&value);
               choice != nullptr) {
        append_string(bytes, *choice);
    } else if (const auto *targets =
                   std::get_if<PolicyEconomySet>(&value);
               targets != nullptr) {
        append_u64(
            bytes,
            static_cast<std::uint64_t>(targets->size()));
        for (const auto target : *targets) {
            append_u64(bytes, target.value());
        }
    }
}

void append_released_observation(
    std::vector<std::uint8_t> &bytes,
    const M11ReleasedObservation &observation) {
    append_string(bytes, observation.series_id);
    append_bool(bytes, observation.value.has_value());
    if (observation.value.has_value()) {
        append_double(bytes, *observation.value);
    }
    append_u64(bytes, observation.observed_at.value());
    append_u64(bytes, observation.released_at.value());
    append_u64(bytes, observation.revision);
}

void append_policy_version(
    std::vector<std::uint8_t> &bytes,
    const M11PolicyVersion &version) {
    append_u64(bytes, version.economy.value());
    append_string(bytes, version.lever);
    append_u64(bytes, version.version);
    append_optional_tick(bytes, version.last_effective);
}

void append_native_policy_action(
    std::vector<std::uint8_t> &bytes,
    const NativePolicyAction &action) {
    append_u64(bytes, action.economy.value());
    append_string(bytes, action.lever);
    append_policy_value(bytes, action.value);
}

void append_decision_context(
    std::vector<std::uint8_t> &bytes,
    const M11DecisionContext &context) {
    append_string(bytes, context.context_id);
    append_string(bytes, context.decision_window_id);
    append_u64(bytes, context.economy.value());
    append_string(bytes, context.seat);
    append_string(bytes, context.decision_group);
    append_u64(bytes, context.boundary.value());
    append_u64(bytes, context.expires_at.value());
    append_u64(bytes, context.administrative_window.value());
    append_u64(
        bytes,
        static_cast<std::uint64_t>(context.observation.size()));
    for (const auto &observation : context.observation) {
        append_released_observation(bytes, observation);
    }
    append_u64(
        bytes,
        static_cast<std::uint64_t>(
            context.permitted_actions.size()));
    for (const auto &action : context.permitted_actions) {
        append_string(bytes, action.lever);
        append_policy_value(bytes, action.current_value);
        append_bool(bytes, action.allowed);
        append_string(bytes, action.reason_code);
        append_u64(bytes, action.policy_version);
        append_u64(bytes, action.earliest_effective.value());
    }
    append_u64(
        bytes,
        static_cast<std::uint64_t>(
            context.policy_versions.size()));
    for (const auto &version : context.policy_versions) {
        append_policy_version(bytes, version);
    }
    append_double(bytes, context.administrative_remaining);
    append_double(bytes, context.administrative_reserved);
    append_double(bytes, context.administrative_capacity);
    append_bool(bytes, context.emergency);
    append_string(bytes, context.emergency_trigger);
    append_u64(bytes, context.elapsed_ticks);
    append_optional_string(bytes, context.answered_by_proposal);
}

void append_policy_proposal(
    std::vector<std::uint8_t> &bytes,
    const M11PolicyProposal &proposal) {
    append_string(bytes, proposal.proposal_id);
    append_string(bytes, proposal.idempotency_key);
    append_string(bytes, proposal.context_id);
    append_u64(
        bytes,
        static_cast<std::uint64_t>(proposal.actions.size()));
    for (const auto &action : proposal.actions) {
        append_native_policy_action(bytes, action);
    }
    append_u64(
        bytes,
        static_cast<std::uint64_t>(
            proposal.based_on_policy_versions.size()));
    for (const auto &version :
         proposal.based_on_policy_versions) {
        append_string(bytes, version.lever);
        append_u64(bytes, version.version);
    }
    append_string(bytes, proposal.reason);
    append_optional_string(
        bytes, proposal.supersedes_proposal_id);
}

void append_policy_decision(
    std::vector<std::uint8_t> &bytes,
    const M11PolicyDecision &decision) {
    append_string(bytes, decision.decision_id);
    append_string(bytes, decision.proposal_id);
    bytes.push_back(
        static_cast<std::uint8_t>(decision.status));
    append_string(bytes, decision.reason_code);
    append_optional_tick(bytes, decision.accepted_at);
    append_optional_tick(bytes, decision.effective_at);
    append_u64(bytes, decision.accepted_sequence);
    append_double(bytes, decision.reserved_administrative_cost);
    append_double(bytes, decision.adjustment_cost);
}

void append_controller_event(
    std::vector<std::uint8_t> &bytes,
    const M11ControllerEvent &event) {
    append_u64(bytes, event.sequence);
    append_u64(bytes, event.boundary.value());
    append_string(bytes, event.event_type);
    append_string(bytes, event.operation_id);
    append_string(bytes, event.actor);
    append_string(bytes, event.canonical_payload);
    bytes.push_back(
        static_cast<std::uint8_t>(event.visibility));
    bytes.insert(bytes.end(), event.prior_hash.bytes.begin(),
                 event.prior_hash.bytes.end());
    bytes.insert(bytes.end(), event.hash.bytes.begin(),
                 event.hash.bytes.end());
}

void append_shock_bulletin(
    std::vector<std::uint8_t> &bytes,
    const reporting::ShockBulletinProbeRow &bulletin) {
    append_u64(bytes, bulletin.shock_id);
    bytes.push_back(static_cast<std::uint8_t>(bulletin.kind));
    append_bool(bytes, bulletin.economy.has_value());
    if (bulletin.economy.has_value()) {
        append_u64(bytes, bulletin.economy->value());
    }
    append_u64(bytes, bulletin.announcement.value());
    append_u64(bytes, bulletin.start.value());
    append_u64(bytes, bulletin.expected_end.value());
    append_u64(bytes, bulletin.duration);
    append_double(bytes, bulletin.magnitude);
    append_double(bytes, bulletin.intensity);
    bytes.push_back(static_cast<std::uint8_t>(bulletin.status));
    append_bool(bytes, bulletin.sector.has_value());
    if (bulletin.sector.has_value()) {
        bytes.push_back(
            static_cast<std::uint8_t>(*bulletin.sector));
    }
}

[[nodiscard]] bool valid_scope(
    const M11ControlledSession &session,
    const M11AccessScope &scope) noexcept {
    return !scope.principal.empty() &&
           scope.principal.size() <= 128U &&
           scope.economy.value() <
               session.engine().world().economy_count() &&
           m11_valid_seat(scope.role);
}

[[nodiscard]] bool frontend_metric(
    const reporting::MetricDescriptor &descriptor) noexcept {
    return descriptor.tier == reporting::MetricTier::causal ||
           descriptor.tier == reporting::MetricTier::release ||
           descriptor.tier == reporting::MetricTier::frontend;
}

[[nodiscard]] bool bulletin_equal(
    const reporting::ShockBulletinProbeRow &left,
    const reporting::ShockBulletinProbeRow &right) noexcept {
    return left.shock_id == right.shock_id &&
           left.kind == right.kind &&
           left.economy == right.economy &&
           left.announcement == right.announcement &&
           left.start == right.start &&
           left.expected_end == right.expected_end &&
           left.duration == right.duration &&
           left.magnitude == right.magnitude &&
           left.intensity == right.intensity &&
           left.status == right.status &&
           left.sector == right.sector;
}

[[nodiscard]] bool bulletins_equal(
    const std::vector<reporting::ShockBulletinProbeRow> &left,
    const std::vector<reporting::ShockBulletinProbeRow> &right) noexcept {
    return left.size() == right.size() &&
           std::equal(left.begin(), left.end(), right.begin(),
                      bulletin_equal);
}

} // namespace

core::StateDigest m11_frontend_snapshot_id(
    const M11FrontendSnapshot &snapshot) noexcept {
    try {
        std::vector<std::uint8_t> bytes;
        bytes.reserve(
            256U + snapshot.metrics.size() * 32U +
            snapshot.policies.size() * 40U);
        append_u64(bytes, snapshot.schema_version);
        append_string(bytes, snapshot.cache_epoch);
        append_u64(bytes, snapshot.snapshot_sequence);
        append_string(bytes, snapshot.scope.principal);
        append_u64(bytes, snapshot.scope.economy.value());
        append_string(bytes, snapshot.scope.role);
        append_u64(bytes, snapshot.boundary.value());
        bytes.push_back(
            static_cast<std::uint8_t>(snapshot.phase));
        bytes.push_back(snapshot.awaiting_human ? 1U : 0U);
        append_u64(bytes, snapshot.event_cursor);
        append_u64(bytes, snapshot.release_cursor);
        append_u64(
            bytes,
            static_cast<std::uint64_t>(snapshot.metrics.size()));
        for (const auto &metric : snapshot.metrics) {
            append_string(bytes, metric.stable_id);
            bytes.push_back(metric.value.has_value() ? 1U : 0U);
            if (metric.value.has_value()) {
                append_double(bytes, *metric.value);
            }
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.policies.size()));
        for (const auto &policy : snapshot.policies) {
            append_string(bytes, policy.lever);
            append_policy_value(bytes, policy.value);
            append_u64(bytes, policy.version);
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.releases.size()));
        for (const auto &release : snapshot.releases) {
            append_released_observation(bytes, release);
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.contexts.size()));
        for (const auto &context : snapshot.contexts) {
            append_decision_context(bytes, context);
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.pending.size()));
        for (const auto &pending : snapshot.pending) {
            append_policy_decision(bytes, pending.decision);
            append_policy_proposal(bytes, pending.proposal);
            append_decision_context(bytes, pending.context);
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.public_events.size()));
        for (const auto &event : snapshot.public_events) {
            append_controller_event(bytes, event);
        }
        append_u64(
            bytes,
            static_cast<std::uint64_t>(
                snapshot.shock_bulletins.size()));
        for (const auto &bulletin : snapshot.shock_bulletins) {
            append_shock_bulletin(bytes, bulletin);
        }
        return core::sha256_digest(bytes);
    } catch (...) {
        return {};
    }
}

Result<M11FrontendSnapshot>
M11FrontendProjection::snapshot(
    const M11ControlledSession &session,
    const M11AccessScope &scope, std::string cache_epoch,
    std::uint64_t snapshot_sequence) const {
    if (!valid_scope(session, scope) || cache_epoch.empty() ||
        cache_epoch.size() > 128U) {
        return Status(ErrorCode::invalid_argument,
                      "M11 frontend snapshot scope is invalid");
    }
    M11FrontendSnapshot result;
    result.cache_epoch = std::move(cache_epoch);
    result.snapshot_sequence = snapshot_sequence;
    result.scope = scope;
    result.boundary = session.tick();
    result.phase = session.phase();
    result.awaiting_human =
        session.phase() == M11BoundaryPhase::awaiting_human;
    result.event_cursor = session.events().next_sequence();
    result.release_cursor = session.releases().next_sequence();

    const auto &frame = session.engine().metrics().current();
    const auto descriptors = reporting::metric_descriptors();
    result.metrics.reserve(descriptors.size());
    for (std::size_t index = 0U; index < descriptors.size();
         ++index) {
        if (!frontend_metric(descriptors[index])) {
            continue;
        }
        auto value = frame.value(
            static_cast<std::size_t>(scope.economy.value()),
            index);
        result.metrics.push_back({
            std::string(descriptors[index].stable_id),
            value.ok() ? std::optional<double>(*value.get_if())
                       : std::optional<double>{},
        });
    }
    std::ranges::sort(
        result.metrics, {},
        &M11FrontendMetric::stable_id);

    auto domestic =
        session.engine().world().domestic_policy(scope.economy);
    if (!domestic.ok()) {
        return domestic.status();
    }
    const auto &external =
        session.engine().world().external_policies()
            [static_cast<std::size_t>(scope.economy.value())];
    for (const auto &lever : m11_policy_levers()) {
        if (lever.owner_role != scope.role) {
            continue;
        }
        auto value = m11_policy_value(
            *domestic.get_if(), external, lever.name);
        const auto *version =
            session.coordinator().find_policy_version(
                scope.economy, lever.name);
        if (!value.ok() || version == nullptr) {
            return Status(
                ErrorCode::internal_error,
                "M11 frontend policy projection is incomplete");
        }
        result.policies.push_back({
            std::string(lever.name), *value.get_if(),
            version->version,
        });
    }
    std::ranges::sort(
        result.policies, {}, &M11FrontendPolicy::lever);
    auto observations = release_service_.observation(
        session.releases(), scope.economy, session.tick(),
        scope.role);
    if (!observations.ok()) {
        return observations.status();
    }
    result.releases = std::move(*observations.get_if());
    std::ranges::sort(
        result.releases,
        [](const M11ReleasedObservation &left,
           const M11ReleasedObservation &right) {
            return std::tie(
                       left.series_id, left.observed_at,
                       left.released_at, left.revision) <
                   std::tie(
                       right.series_id, right.observed_at,
                       right.released_at, right.revision);
        });
    for (const auto &context :
         session.coordinator().contexts()) {
        if (context.economy == scope.economy &&
            context.seat == scope.role &&
            context.boundary <= session.tick() &&
            context.expires_at >= session.tick()) {
            result.contexts.push_back(context);
        }
    }
    std::ranges::sort(
        result.contexts, {}, &M11DecisionContext::context_id);
    for (const auto &pending :
         session.coordinator().pending()) {
        if (pending.context.economy == scope.economy &&
            pending.context.seat == scope.role &&
            pending.decision.status ==
                M11DecisionStatus::accepted_pending) {
            result.pending.push_back(pending);
        }
    }
    std::ranges::sort(
        result.pending,
        [](const M11PendingDecision &left,
           const M11PendingDecision &right) {
            return left.decision.decision_id <
                   right.decision.decision_id;
        });
    const auto first_event =
        result.event_cursor > kM11FrontendEventWindow
            ? result.event_cursor - kM11FrontendEventWindow
            : 0U;
    auto events = session.events().page(
        first_event, kM11FrontendEventWindow,
        M11EventVisibility::public_record);
    if (!events.ok()) {
        return events.status();
    }
    result.public_events = std::move(*events.get_if());
    auto bulletins = session.engine().probe_shock_bulletins(
        scope.economy, session.tick());
    if (!bulletins.ok()) {
        return bulletins.status();
    }
    result.shock_bulletins = std::move(*bulletins.get_if());
    result.snapshot_id = m11_frontend_snapshot_id(result);
    return result;
}

Result<M11FrontendDelta>
M11FrontendProjection::delta(
    const M11FrontendSnapshot &base,
    const M11FrontendSnapshot &result) const {
    if (base.schema_version !=
            kM11FrontendSnapshotSchemaVersion ||
        result.schema_version !=
            kM11FrontendSnapshotSchemaVersion ||
        base.snapshot_id != m11_frontend_snapshot_id(base) ||
        result.snapshot_id != m11_frontend_snapshot_id(result) ||
        base.scope != result.scope ||
        base.cache_epoch != result.cache_epoch ||
        result.snapshot_sequence != base.snapshot_sequence + 1U ||
        result.boundary < base.boundary ||
        result.event_cursor < base.event_cursor ||
        result.release_cursor < base.release_cursor) {
        return Status(
            ErrorCode::stale_handle,
            "M11 frontend delta base requires a full resync");
    }
    M11FrontendDelta delta;
    delta.base_snapshot_id = base.snapshot_id;
    delta.result_snapshot_id = result.snapshot_id;
    delta.base_sequence = base.snapshot_sequence;
    delta.result_sequence = result.snapshot_sequence;
    delta.boundary = result.boundary;
    delta.phase = result.phase;
    delta.awaiting_human = result.awaiting_human;
    delta.event_cursor = result.event_cursor;
    delta.release_cursor = result.release_cursor;
    for (const auto &metric : result.metrics) {
        const auto previous = std::lower_bound(
            base.metrics.begin(), base.metrics.end(),
            metric.stable_id,
            [](const M11FrontendMetric &entry,
               std::string_view stable_id) {
                return entry.stable_id < stable_id;
            });
        if (previous == base.metrics.end() ||
            previous->stable_id != metric.stable_id ||
            *previous != metric) {
            delta.changed_metrics.push_back(metric);
        }
    }
    for (const auto &policy : result.policies) {
        const auto previous = std::lower_bound(
            base.policies.begin(), base.policies.end(),
            policy.lever,
            [](const M11FrontendPolicy &entry,
               std::string_view lever) {
                return entry.lever < lever;
            });
        if (previous == base.policies.end() ||
            previous->lever != policy.lever ||
            *previous != policy) {
            delta.changed_policies.push_back(policy);
        }
    }
    delta.releases = result.releases;
    delta.contexts = result.contexts;
    delta.pending = result.pending;
    for (const auto &event : result.public_events) {
        if (event.sequence >= base.event_cursor) {
            delta.appended_public_events.push_back(event);
        }
    }
    if (!bulletins_equal(
            base.shock_bulletins, result.shock_bulletins)) {
        delta.shock_bulletins = result.shock_bulletins;
    }
    return delta;
}

} // namespace macro_sim::control
