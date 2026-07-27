#include "macro_sim/desktop/m11_protocol.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <limits>
#include <memory>
#include <optional>
#include <random>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/control/m11_frontend.hpp"
#include "macro_sim/control/m11_policy.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/desktop/m11_new_game.hpp"

namespace macro_sim::desktop {
namespace {

using Json = nlohmann::json;
using control::M11AccessScope;
using control::M11ControlledSession;
using control::M11FrontendDelta;
using control::M11FrontendMetric;
using control::M11FrontendPolicy;
using control::M11FrontendProjection;
using control::M11FrontendSnapshot;

struct ProtocolFault final {
    std::string code;
    std::string message;
    bool full_resync{false};
};

[[nodiscard]] std::string random_hex(std::size_t byte_count) {
    static constexpr std::string_view digits =
        "0123456789abcdef";
    std::random_device source;
    std::string result;
    result.reserve(byte_count * 2U);
    for (std::size_t index = 0U; index < byte_count;
         ++index) {
        const auto value =
            static_cast<std::uint8_t>(source());
        result.push_back(digits[value >> 4U]);
        result.push_back(digits[value & 0x0fU]);
    }
    return result;
}

[[nodiscard]] bool constant_time_equal(
    std::string_view left, std::string_view right) noexcept {
    std::size_t difference = left.size() ^ right.size();
    const auto count = std::max(left.size(), right.size());
    for (std::size_t index = 0U; index < count; ++index) {
        const auto left_value =
            index < left.size()
                ? static_cast<unsigned char>(left[index])
                : 0U;
        const auto right_value =
            index < right.size()
                ? static_cast<unsigned char>(right[index])
                : 0U;
        difference |=
            static_cast<std::size_t>(left_value ^ right_value);
    }
    return difference == 0U;
}

[[nodiscard]] Json policy_value_json(
    const control::PolicyValue &value) {
    if (std::holds_alternative<std::monostate>(value)) {
        return nullptr;
    }
    if (const auto *boolean = std::get_if<bool>(&value);
        boolean != nullptr) {
        return *boolean;
    }
    if (const auto *integer =
            std::get_if<std::int64_t>(&value);
        integer != nullptr) {
        return *integer;
    }
    if (const auto *number = std::get_if<double>(&value);
        number != nullptr) {
        return *number;
    }
    if (const auto *choice =
            std::get_if<std::string>(&value);
        choice != nullptr) {
        return *choice;
    }
    Json result = Json::array();
    for (const auto economy :
         std::get<control::PolicyEconomySet>(value)) {
        result.push_back(economy.value());
    }
    return result;
}

[[nodiscard]] Json metric_json(
    const M11FrontendMetric &metric) {
    return {
        {"stable_id", metric.stable_id},
        {"value",
         metric.value.has_value()
             ? Json(*metric.value)
             : Json(nullptr)},
    };
}

[[nodiscard]] Json policy_json(
    const M11FrontendPolicy &policy) {
    return {
        {"lever", policy.lever},
        {"value", policy_value_json(policy.value)},
        {"version", policy.version},
    };
}

[[nodiscard]] Json observation_json(
    const control::M11ReleasedObservation &observation) {
    return {
        {"series_id", observation.series_id},
        {"value",
         observation.value.has_value()
             ? Json(*observation.value)
             : Json(nullptr)},
        {"observed_at", observation.observed_at.value()},
        {"released_at", observation.released_at.value()},
        {"revision", observation.revision},
    };
}

[[nodiscard]] Json policy_version_json(
    const control::M11PolicyVersion &version) {
    return {
        {"economy_id", version.economy.value()},
        {"lever", version.lever},
        {"version", version.version},
        {"last_effective",
         version.last_effective.has_value()
             ? Json(version.last_effective->value())
             : Json(nullptr)},
    };
}

[[nodiscard]] Json context_json(
    const control::M11DecisionContext &context) {
    Json observations = Json::array();
    for (const auto &observation : context.observation) {
        observations.push_back(
            observation_json(observation));
    }
    Json permitted = Json::array();
    for (const auto &action : context.permitted_actions) {
        permitted.push_back({
            {"lever", action.lever},
            {"current_value",
             policy_value_json(action.current_value)},
            {"allowed", action.allowed},
            {"reason_code", action.reason_code},
            {"policy_version", action.policy_version},
            {"earliest_effective",
             action.earliest_effective.value()},
        });
    }
    Json versions = Json::array();
    for (const auto &version : context.policy_versions) {
        versions.push_back(policy_version_json(version));
    }
    return {
        {"context_id", context.context_id},
        {"decision_window_id", context.decision_window_id},
        {"economy_id", context.economy.value()},
        {"seat", context.seat},
        {"decision_group", context.decision_group},
        {"boundary", context.boundary.value()},
        {"expires_at", context.expires_at.value()},
        {"administrative_window",
         context.administrative_window.value()},
        {"observation", std::move(observations)},
        {"permitted_actions", std::move(permitted)},
        {"policy_versions", std::move(versions)},
        {"administrative_remaining",
         context.administrative_remaining},
        {"administrative_reserved",
         context.administrative_reserved},
        {"administrative_capacity",
         context.administrative_capacity},
        {"emergency", context.emergency},
        {"emergency_trigger", context.emergency_trigger},
        {"elapsed_ticks", context.elapsed_ticks},
        {"answered_by_proposal",
         context.answered_by_proposal.has_value()
             ? Json(*context.answered_by_proposal)
             : Json(nullptr)},
    };
}

[[nodiscard]] Json action_json(
    const control::NativePolicyAction &action) {
    return {
        {"economy_id", action.economy.value()},
        {"lever", action.lever},
        {"value", policy_value_json(action.value)},
    };
}

[[nodiscard]] Json proposal_json(
    const control::M11PolicyProposal &proposal) {
    Json actions = Json::array();
    for (const auto &action : proposal.actions) {
        actions.push_back(action_json(action));
    }
    Json versions = Json::array();
    for (const auto &version :
         proposal.based_on_policy_versions) {
        versions.push_back({
            {"lever", version.lever},
            {"version", version.version},
        });
    }
    return {
        {"proposal_id", proposal.proposal_id},
        {"idempotency_key", proposal.idempotency_key},
        {"context_id", proposal.context_id},
        {"actions", std::move(actions)},
        {"based_on_policy_versions", std::move(versions)},
        {"reason", proposal.reason},
        {"supersedes_proposal_id",
         proposal.supersedes_proposal_id.has_value()
             ? Json(*proposal.supersedes_proposal_id)
             : Json(nullptr)},
    };
}

[[nodiscard]] Json decision_json(
    const control::M11PolicyDecision &decision) {
    return {
        {"decision_id", decision.decision_id},
        {"proposal_id", decision.proposal_id},
        {"status",
         control::m11_decision_status_name(decision.status)},
        {"reason_code", decision.reason_code},
        {"accepted_at",
         decision.accepted_at.has_value()
             ? Json(decision.accepted_at->value())
             : Json(nullptr)},
        {"effective_at",
         decision.effective_at.has_value()
             ? Json(decision.effective_at->value())
             : Json(nullptr)},
        {"accepted_sequence", decision.accepted_sequence},
        {"reserved_administrative_cost",
         decision.reserved_administrative_cost},
        {"adjustment_cost", decision.adjustment_cost},
    };
}

[[nodiscard]] Json pending_json(
    const control::M11PendingDecision &pending) {
    return {
        {"decision", decision_json(pending.decision)},
        {"proposal", proposal_json(pending.proposal)},
        {"context", context_json(pending.context)},
    };
}

[[nodiscard]] Json event_json(
    const control::M11ControllerEvent &event) {
    return {
        {"sequence", event.sequence},
        {"boundary", event.boundary.value()},
        {"event_type", event.event_type},
        {"operation_id", event.operation_id},
        {"actor", event.actor},
        {"canonical_payload", event.canonical_payload},
        {"visibility",
         static_cast<std::uint8_t>(event.visibility)},
        {"prior_hash", event.prior_hash.hex()},
        {"hash", event.hash.hex()},
    };
}

[[nodiscard]] Json shock_bulletin_json(
    const reporting::ShockBulletinProbeRow &bulletin) {
    return {
        {"shock_id", bulletin.shock_id},
        {"kind", static_cast<std::uint8_t>(bulletin.kind)},
        {"economy_id",
         bulletin.economy.has_value()
             ? Json(bulletin.economy->value())
             : Json(nullptr)},
        {"announcement", bulletin.announcement.value()},
        {"start", bulletin.start.value()},
        {"expected_end", bulletin.expected_end.value()},
        {"duration", bulletin.duration},
        {"magnitude", bulletin.magnitude},
        {"intensity", bulletin.intensity},
        {"status",
         static_cast<std::uint8_t>(bulletin.status)},
        {"sector",
         bulletin.sector.has_value()
             ? Json(static_cast<std::uint8_t>(
                   *bulletin.sector))
             : Json(nullptr)},
    };
}

template <typename Value, typename Converter>
[[nodiscard]] Json json_array(
    const std::vector<Value> &values,
    Converter &&converter) {
    Json result = Json::array();
    for (const auto &value : values) {
        result.push_back(converter(value));
    }
    return result;
}

[[nodiscard]] Json snapshot_json(
    const M11FrontendSnapshot &snapshot) {
    return {
        {"schema_version", snapshot.schema_version},
        {"cache_epoch", snapshot.cache_epoch},
        {"snapshot_sequence", snapshot.snapshot_sequence},
        {"snapshot_id", snapshot.snapshot_id.hex()},
        {"scope",
         {
             {"principal", snapshot.scope.principal},
             {"economy_id", snapshot.scope.economy.value()},
             {"role", snapshot.scope.role},
         }},
        {"boundary", snapshot.boundary.value()},
        {"phase",
         control::m11_boundary_phase_name(snapshot.phase)},
        {"awaiting_human", snapshot.awaiting_human},
        {"event_cursor", snapshot.event_cursor},
        {"release_cursor", snapshot.release_cursor},
        {"metrics",
         json_array(snapshot.metrics, metric_json)},
        {"policies",
         json_array(snapshot.policies, policy_json)},
        {"releases",
         json_array(snapshot.releases, observation_json)},
        {"contexts",
         json_array(snapshot.contexts, context_json)},
        {"pending",
         json_array(snapshot.pending, pending_json)},
        {"public_events",
         json_array(snapshot.public_events, event_json)},
        {"shock_bulletins",
         json_array(
             snapshot.shock_bulletins,
             shock_bulletin_json)},
    };
}

[[nodiscard]] Json delta_json(
    const M11FrontendDelta &delta) {
    return {
        {"schema_version", delta.schema_version},
        {"base_snapshot_id", delta.base_snapshot_id.hex()},
        {"result_snapshot_id", delta.result_snapshot_id.hex()},
        {"base_sequence", delta.base_sequence},
        {"result_sequence", delta.result_sequence},
        {"boundary", delta.boundary.value()},
        {"phase",
         control::m11_boundary_phase_name(delta.phase)},
        {"awaiting_human", delta.awaiting_human},
        {"event_cursor", delta.event_cursor},
        {"release_cursor", delta.release_cursor},
        {"changed_metrics",
         json_array(delta.changed_metrics, metric_json)},
        {"changed_policies",
         json_array(delta.changed_policies, policy_json)},
        {"releases",
         json_array(delta.releases, observation_json)},
        {"contexts",
         json_array(delta.contexts, context_json)},
        {"pending",
         json_array(delta.pending, pending_json)},
        {"appended_public_events",
         json_array(
             delta.appended_public_events, event_json)},
        {"shock_bulletins",
         json_array(
             delta.shock_bulletins,
             shock_bulletin_json)},
    };
}

[[nodiscard]] Json decision_result_json(
    const control::M11DecisionResult &result) {
    Json decisions = Json::array();
    for (const auto &decision : result.decisions) {
        decisions.push_back(decision_json(decision));
    }
    return {
        {"phase",
         control::m11_boundary_phase_name(result.phase)},
        {"boundary", result.boundary.value()},
        {"elapsed_ticks", result.elapsed_ticks},
        {"opened_context_ids", result.opened_context_ids},
        {"decisions", std::move(decisions)},
        {"awaiting_human", result.awaiting_human},
        {"limit_reached", result.limit_reached},
        {"advanced_ticks",
         result.advance.has_value()
             ? result.advance->advanced_ticks
             : 0U},
    };
}

[[nodiscard]] std::optional<Json>
parse_strict_json(std::string_view frame) {
    bool invalid = false;
    std::vector<std::set<std::string, std::less<>>> keys;
    const auto callback =
        [&invalid, &keys](
            int depth, Json::parse_event_t event,
            Json &parsed) {
            if (depth > 64) {
                invalid = true;
                return false;
            }
            if (event == Json::parse_event_t::object_start) {
                keys.emplace_back();
            } else if (event == Json::parse_event_t::key) {
                if (keys.empty() ||
                    !keys.back()
                         .emplace(parsed.get<std::string>())
                         .second) {
                    invalid = true;
                    return false;
                }
            } else if (
                event == Json::parse_event_t::object_end &&
                !keys.empty()) {
                keys.pop_back();
            }
            return true;
        };
    try {
        auto result = Json::parse(
            frame.begin(), frame.end(), callback, true, true);
        if (invalid || !result.is_object()) {
            return std::nullopt;
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}

[[nodiscard]] std::optional<std::string>
required_text(const Json &request, std::string_view key,
              std::size_t maximum) {
    if (!request.contains(key) ||
        !request.at(key).is_string()) {
        return std::nullopt;
    }
    auto result = request.at(key).get<std::string>();
    if (result.empty() || result.size() > maximum) {
        return std::nullopt;
    }
    return result;
}

[[nodiscard]] Json error_envelope(
    const Json *request, const ProtocolFault &fault) {
    return {
        {"ok", false},
        {"protocol_version", kM11DesktopProtocolVersion},
        {"request_id",
         request != nullptr && request->contains("request_id")
             ? request->at("request_id")
             : Json(nullptr)},
        {"connection_id",
         request != nullptr &&
                 request->contains("connection_id")
             ? request->at("connection_id")
             : Json(nullptr)},
        {"sequence",
         request != nullptr && request->contains("sequence")
             ? request->at("sequence")
             : Json(nullptr)},
        {"session_id",
         request != nullptr && request->contains("session_id")
             ? request->at("session_id")
             : Json(nullptr)},
        {"error",
         {
             {"code", fault.code},
             {"message", fault.message},
             {"full_resync", fault.full_resync},
         }},
    };
}

[[nodiscard]] ProtocolFault status_fault(
    const Status &status) {
    return {
        std::string(error_code_name(status.code())),
        std::string(status.message()),
        status.code() == ErrorCode::stale_handle,
    };
}

} // namespace

struct M11ProtocolWorker::Impl final {
    struct ConnectionState final {
        std::string connection_id;
        std::uint64_t last_sequence{0U};
    };

    struct Receipt final {
        std::string connection_id;
        std::uint64_t sequence{0U};
        std::string request_id;
        core::StateDigest request_hash{};
        std::string response;
    };

    M11ProtocolOptions options;
    std::vector<ConnectionState> connections;
    std::deque<Receipt> receipts;
    std::unique_ptr<M11ControlledSession> session;
    std::string session_identifier;
    std::string owner_connection;
    std::string cache_epoch;
    std::uint64_t next_snapshot_sequence{1U};
    std::deque<M11FrontendSnapshot> snapshots;
    M11FrontendProjection projection;
    std::optional<M11NativeNewGame> new_game;
    bool shutdown{false};

    [[nodiscard]] ConnectionState *
    connection(std::string_view identifier) {
        const auto found = std::ranges::find(
            connections, identifier,
            &ConnectionState::connection_id);
        if (found != connections.end()) {
            return &*found;
        }
        connections.push_back(
            {std::string(identifier), 0U});
        return &connections.back();
    }

    [[nodiscard]] const Receipt *find_receipt(
        std::string_view connection_id,
        std::uint64_t sequence) const {
        const auto found = std::ranges::find_if(
            receipts,
            [connection_id, sequence](const Receipt &receipt) {
                return receipt.connection_id == connection_id &&
                       receipt.sequence == sequence;
            });
        return found == receipts.end() ? nullptr : &*found;
    }

    void store_receipt(
        std::string connection_id, std::uint64_t sequence,
        std::string request_id,
        const core::StateDigest &request_hash,
        std::string response) {
        receipts.push_back({
            std::move(connection_id), sequence,
            std::move(request_id), request_hash,
            std::move(response),
        });
        while (receipts.size() >
               kM11MaximumProtocolReceipts) {
            receipts.pop_front();
        }
    }

    [[nodiscard]] ProtocolFault require_session(
        const Json &request,
        std::string_view connection_id,
        bool mutable_command) const {
        if (session == nullptr) {
            return {"no_session",
                    "No simulation session is active.", false};
        }
        const auto requested =
            required_text(request, "session_id", 128U);
        if (!requested.has_value() ||
            !constant_time_equal(
                *requested, session_identifier)) {
            return {"invalid_session",
                    "The session identifier is invalid.", false};
        }
        if (owner_connection != connection_id) {
            return {
                mutable_command ? "not_session_owner"
                                : "access_denied",
                mutable_command
                    ? "Only the session owner may mutate the simulation."
                    : "The connection cannot access this session.",
                false,
            };
        }
        return {};
    }

    [[nodiscard]] Result<M11FrontendSnapshot>
    create_snapshot(const Json &request,
                    std::string_view connection_id) {
        const auto role =
            request.value("role", std::string("treasury"));
        const auto economy =
            request.value(
                "economy_id",
                new_game.has_value()
                    ? new_game->player_economy
                    : 0U);
        if (!control::m11_valid_seat(role)) {
            return Status(ErrorCode::invalid_argument,
                          "snapshot role is invalid");
        }
        auto result = projection.snapshot(
            *session,
            M11AccessScope{
                std::string(connection_id),
                EconomyId(economy), role},
            cache_epoch, next_snapshot_sequence);
        if (result.ok()) {
            ++next_snapshot_sequence;
            snapshots.push_back(*result.get_if());
            while (snapshots.size() >
                   kM11MaximumSnapshotCacheEntries) {
                snapshots.pop_front();
            }
        }
        return result;
    }

    [[nodiscard]] Json snapshot_result(
        const Json &request,
        std::string_view connection_id) {
        auto current = create_snapshot(request, connection_id);
        if (!current.ok()) {
            throw status_fault(current.status());
        }
        if (request.contains("base_snapshot_id")) {
            if (!request.at("base_snapshot_id").is_string()) {
                throw ProtocolFault{
                    "invalid_argument",
                    "The snapshot base identifier is invalid.",
                    true};
            }
            const auto base_id =
                request.at("base_snapshot_id")
                    .get<std::string>();
            const auto found = std::ranges::find_if(
                snapshots,
                [&base_id, &current](
                    const M11FrontendSnapshot &snapshot) {
                    return snapshot.snapshot_id.hex() == base_id &&
                           snapshot.snapshot_id !=
                               current.get_if()->snapshot_id;
                });
            if (found != snapshots.end()) {
                auto delta =
                    projection.delta(*found, *current.get_if());
                if (delta.ok()) {
                    return {
                        {"mode", "delta"},
                        {"delta", delta_json(*delta.get_if())},
                    };
                }
            }
            return {
                {"mode", "full_resync"},
                {"reason", "snapshot_base_unavailable"},
                {"snapshot",
                 snapshot_json(*current.get_if())},
            };
        }
        return {
            {"mode", "full"},
            {"snapshot", snapshot_json(*current.get_if())},
        };
    }

    [[nodiscard]] Json new_session_command(
        const Json &request,
        std::string_view connection_id) {
        if (session != nullptr) {
            throw ProtocolFault{
                "session_exists",
                "Close the active session before creating another.",
                false};
        }
        Result<M11NativeNewGame> built =
            request.contains("spec")
                ? parse_m11_native_new_game(
                      request.at("spec").dump())
                : default_m11_native_new_game(
                      request.value("seed", 7U));
        if (!built.ok()) {
            throw status_fault(built.status());
        }
        if (!options.built_in_rl_artifact.empty()) {
            for (auto &assignment :
                 built.get_if()->controller.assignments) {
                if (assignment.occupant.kind ==
                    control::M11OccupantKind::
                        reinforcement_learning) {
                    assignment.occupant.artifact_path =
                        options.built_in_rl_artifact;
                }
            }
        }
        auto world =
            simulation::M9World::create(built.get_if()->world);
        if (!world.ok()) {
            throw status_fault(world.status());
        }
        if (!built.get_if()
                 ->initial_policy_actions.empty()) {
            auto batch = control::project_m11_policy_actions(
                *world.get_if(),
                built.get_if()->initial_policy_actions);
            if (!batch.ok()) {
                throw status_fault(batch.status());
            }
            const auto applied =
                world.get_if()->update_policy_batch(
                    *batch.get_if());
            if (!applied.ok()) {
                throw status_fault(applied);
            }
        }
        auto engine = control::EngineSession::create(
            std::move(*world.get_if()), 4096U);
        if (!engine.ok()) {
            throw status_fault(engine.status());
        }
        auto controlled =
            M11ControlledSession::create(
                std::move(*engine.get_if()),
                std::move(built.get_if()->controller));
        if (!controlled.ok()) {
            throw status_fault(controlled.status());
        }
        session = std::make_unique<M11ControlledSession>(
            std::move(*controlled.get_if()));
        session_identifier = random_hex(16U);
        owner_connection = std::string(connection_id);
        cache_epoch = random_hex(16U);
        next_snapshot_sequence = 1U;
        snapshots.clear();
        new_game = std::move(*built.get_if());
        Json snapshot_request = request;
        snapshot_request["session_id"] =
            session_identifier;
        auto snapshot =
            snapshot_result(snapshot_request, connection_id);
        return {
            {"session_id", session_identifier},
            {"model_id", new_game->model_id},
            {"schema_version", new_game->schema_version},
            {"start_date", new_game->start_date},
            {"duration_ticks",
             new_game->duration_ticks.has_value()
                 ? Json(*new_game->duration_ticks)
                 : Json(nullptr)},
            {"player_economy", new_game->player_economy},
            {"countries",
             [&]() {
                 Json countries = Json::array();
                 for (const auto &country :
                      new_game->countries) {
                     countries.push_back({
                         {"name", country.name},
                         {"code", country.code},
                         {"profile", country.profile},
                     });
                 }
                 return countries;
             }()},
            {"projection", std::move(snapshot)},
        };
    }

    [[nodiscard]] Json dispatch(
        const Json &request,
        std::string_view connection_id) {
        const auto command =
            required_text(request, "command", 64U);
        if (!command.has_value()) {
            throw ProtocolFault{
                "invalid_request",
                "The command is missing or invalid.", false};
        }
        if (*command == "hello") {
            return {
                {"worker", "macro_sim_server"},
                {"protocol_version",
                 kM11DesktopProtocolVersion},
                {"model_id", kM11PlayableModelId},
                {"session_active", session != nullptr},
                {"maximum_frame_bytes",
                 options.maximum_frame_bytes},
                {"maximum_response_bytes",
                 options.maximum_response_bytes},
                {"capabilities",
                 {
                     "controlled_session",
                     "snapshot_delta",
                     "role_scoped_release",
                     "native_checkpoint",
                     "native_policy_inference",
                 }},
            };
        }
        if (*command == "new_session" ||
            *command == "new_game") {
            return new_session_command(
                request, connection_id);
        }
        if (*command == "shutdown") {
            if (session != nullptr) {
                const auto fault = require_session(
                    request, connection_id, true);
                if (!fault.code.empty()) {
                    throw fault;
                }
            }
            shutdown = true;
            return {{"shutdown", true}};
        }
        if (*command == "snapshot") {
            const auto fault = require_session(
                request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            return snapshot_result(request, connection_id);
        }
        if (*command == "advance") {
            const auto fault = require_session(
                request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto ticks =
                request.value("ticks", 1U);
            if (ticks < 1U || ticks > 10000U) {
                throw ProtocolFault{
                    "out_of_range",
                    "Advance ticks must be between 1 and 10000.",
                    false};
            }
            const auto stop =
                request.value(
                    "stop_after_context_boundary", true);
            auto advanced =
                session->advance_until_decision(
                    {ticks, stop});
            if (!advanced.ok()) {
                throw status_fault(advanced.status());
            }
            auto projection_result =
                snapshot_result(request, connection_id);
            return {
                {"advance",
                 decision_result_json(*advanced.get_if())},
                {"projection", std::move(projection_result)},
            };
        }
        if (*command == "close_session") {
            const auto fault = require_session(
                request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            session.reset();
            new_game.reset();
            session_identifier.clear();
            owner_connection.clear();
            cache_epoch.clear();
            snapshots.clear();
            next_snapshot_sequence = 1U;
            return {{"closed", true}};
        }
        throw ProtocolFault{
            "unknown_command",
            "The command is not supported.", false};
    }

    [[nodiscard]] std::string handle(
        std::string_view frame) {
        const auto parsed = parse_strict_json(frame);
        if (!parsed.has_value()) {
            return error_envelope(
                       nullptr,
                       {"malformed_json",
                        "The request is not valid JSON.", false})
                .dump();
        }
        const auto &request = *parsed;
        if (!request.contains("protocol_version") ||
            !request.at("protocol_version")
                 .is_number_unsigned() ||
            request.at("protocol_version")
                    .get<std::uint32_t>() !=
                kM11DesktopProtocolVersion) {
            return error_envelope(
                       &request,
                       {"protocol_mismatch",
                        "The protocol version is incompatible.",
                        false})
                .dump();
        }
        const auto request_id =
            required_text(request, "request_id", 128U);
        const auto connection_id =
            required_text(request, "connection_id", 128U);
        const auto token =
            required_text(request, "token", 64U);
        if (!request_id.has_value() ||
            !connection_id.has_value() ||
            !token.has_value() ||
            !request.contains("sequence") ||
            !request.at("sequence").is_number_unsigned()) {
            return error_envelope(
                       &request,
                       {"invalid_request",
                        "The request envelope is incomplete.",
                        false})
                .dump();
        }
        if (!constant_time_equal(
                *token, options.capability_token)) {
            return error_envelope(
                       &request,
                       {"authentication_failed",
                        "The capability token is invalid.",
                        false})
                .dump();
        }
        const auto sequence =
            request.at("sequence").get<std::uint64_t>();
        const auto bytes = std::span(
            reinterpret_cast<const std::uint8_t *>(
                frame.data()),
            frame.size());
        const auto request_hash =
            core::sha256_digest(bytes);
        if (const auto *receipt =
                find_receipt(*connection_id, sequence);
            receipt != nullptr) {
            if (receipt->request_id == *request_id &&
                receipt->request_hash == request_hash) {
                return receipt->response;
            }
            return error_envelope(
                       &request,
                       {"sequence_conflict",
                        "The sequence was already used by a different request.",
                        false})
                .dump();
        }
        auto *connection_state =
            connection(*connection_id);
        if (sequence !=
            connection_state->last_sequence + 1U) {
            return error_envelope(
                       &request,
                       {"sequence_gap",
                        "The request sequence is not contiguous.",
                        true})
                .dump();
        }
        Json envelope;
        try {
            auto result =
                dispatch(request, *connection_id);
            envelope = {
                {"ok", true},
                {"protocol_version",
                 kM11DesktopProtocolVersion},
                {"request_id", *request_id},
                {"connection_id", *connection_id},
                {"sequence", sequence},
                {"session_id",
                 session != nullptr
                     ? Json(session_identifier)
                     : Json(nullptr)},
                {"result", std::move(result)},
            };
        } catch (const ProtocolFault &fault) {
            envelope = error_envelope(&request, fault);
        } catch (...) {
            envelope = error_envelope(
                &request,
                {"internal_error",
                 "The worker could not complete the request.",
                 false});
        }
        auto response = envelope.dump();
        if (response.size() > options.maximum_response_bytes) {
            response =
                error_envelope(
                    &request,
                    {"response_too_large",
                     "The response exceeds the configured limit.",
                     false})
                    .dump();
        }
        connection_state->last_sequence = sequence;
        store_receipt(
            *connection_id, sequence, *request_id,
            request_hash, response);
        return response;
    }
};

bool valid_m11_capability_token(
    std::string_view token) noexcept {
    return token.size() == 64U &&
           std::ranges::all_of(token, [](char value) {
               return (value >= '0' && value <= '9') ||
                      (value >= 'a' && value <= 'f');
           });
}

M11ProtocolWorker::M11ProtocolWorker(
    Impl *implementation) noexcept
    : implementation_(implementation) {}

M11ProtocolWorker::M11ProtocolWorker(
    M11ProtocolWorker &&other) noexcept
    : implementation_(
          std::exchange(other.implementation_, nullptr)) {}

M11ProtocolWorker &M11ProtocolWorker::operator=(
    M11ProtocolWorker &&other) noexcept {
    if (this != &other) {
        delete implementation_;
        implementation_ =
            std::exchange(other.implementation_, nullptr);
    }
    return *this;
}

M11ProtocolWorker::~M11ProtocolWorker() {
    delete implementation_;
}

Result<M11ProtocolWorker>
M11ProtocolWorker::create(M11ProtocolOptions options) {
    if (!valid_m11_capability_token(
            options.capability_token) ||
        options.maximum_frame_bytes < 1024U ||
        options.maximum_frame_bytes >
            kM11MaximumProtocolFrameBytes ||
        options.maximum_response_bytes < 1024U ||
        options.maximum_response_bytes >
            kM11MaximumProtocolResponseBytes) {
        return Status(ErrorCode::invalid_argument,
                      "M11 protocol options are invalid");
    }
    try {
        auto implementation = std::make_unique<Impl>();
        implementation->options = std::move(options);
        return M11ProtocolWorker(implementation.release());
    } catch (...) {
        return Status(ErrorCode::allocation_failure,
                      "M11 protocol allocation failed");
    }
}

std::string M11ProtocolWorker::handle_frame(
    std::string_view frame) {
    if (implementation_ == nullptr) {
        return error_envelope(
                   nullptr,
                   {"invalid_worker",
                    "The protocol worker is unavailable.", false})
            .dump();
    }
    if (frame.empty() ||
        frame.size() >
            implementation_->options.maximum_frame_bytes) {
        return error_envelope(
                   nullptr,
                   {"frame_too_large",
                    "The request frame size is invalid.", false})
            .dump();
    }
    return implementation_->handle(frame);
}

bool M11ProtocolWorker::shutdown_requested() const noexcept {
    return implementation_ != nullptr &&
           implementation_->shutdown;
}

bool M11ProtocolWorker::has_session() const noexcept {
    return implementation_ != nullptr &&
           implementation_->session != nullptr;
}

std::string_view M11ProtocolWorker::session_id() const noexcept {
    return implementation_ != nullptr
               ? std::string_view(
                     implementation_->session_identifier)
               : std::string_view{};
}

} // namespace macro_sim::desktop
