#include "macro_sim/control/m11_session.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <set>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace macro_sim::control {
namespace {

using Json = nlohmann::json;

constexpr std::uint32_t kCheckpointSchemaVersion = 1U;

[[nodiscard]] Status corrupt_checkpoint() noexcept {
    return Status(ErrorCode::corrupt_input,
                  "M11 controlled checkpoint is invalid");
}

void require_object(
    const Json &value,
    std::initializer_list<std::string_view> names) {
    if (!value.is_object() || value.size() != names.size()) {
        throw std::runtime_error("object schema differs");
    }
    for (const auto name : names) {
        if (!value.contains(name)) {
            throw std::runtime_error("object field is absent");
        }
    }
}

template <typename Enum>
[[nodiscard]] Enum checked_enum(const Json &value,
                                std::uint8_t maximum) {
    const auto raw = value.get<std::uint8_t>();
    if (raw > maximum) {
        throw std::runtime_error("enum is invalid");
    }
    return static_cast<Enum>(raw);
}

[[nodiscard]] Json optional_tick(std::optional<Tick> value) {
    return value.has_value() ? Json(value->value()) : Json(nullptr);
}

[[nodiscard]] std::optional<Tick>
tick_from_json(const Json &value) {
    return value.is_null()
               ? std::optional<Tick>{}
               : std::optional<Tick>(
                     Tick(value.get<std::uint64_t>()));
}

[[nodiscard]] Json digest_json(const core::StateDigest &digest) {
    return digest.hex();
}

[[nodiscard]] std::uint8_t hex_digit(char value) {
    if (value >= '0' && value <= '9') {
        return static_cast<std::uint8_t>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
        return static_cast<std::uint8_t>(value - 'a' + 10);
    }
    throw std::runtime_error("hex digit is invalid");
}

[[nodiscard]] core::StateDigest
digest_from_json(const Json &value) {
    const auto text = value.get<std::string>();
    if (text.size() != 64U) {
        throw std::runtime_error("digest length differs");
    }
    core::StateDigest digest;
    for (std::size_t index = 0U; index < digest.bytes.size(); ++index) {
        digest.bytes[index] = static_cast<std::uint8_t>(
            (hex_digit(text[index * 2U]) << 4U) |
            hex_digit(text[index * 2U + 1U]));
    }
    return digest;
}

[[nodiscard]] std::string
hex_bytes(std::span<const std::uint8_t> bytes) {
    static constexpr std::array<char, 16> digits{
        '0', '1', '2', '3', '4', '5', '6', '7',
        '8', '9', 'a', 'b', 'c', 'd', 'e', 'f',
    };
    if (bytes.size() >
        std::numeric_limits<std::size_t>::max() / 2U) {
        throw std::runtime_error("byte archive is too large");
    }
    std::string result(bytes.size() * 2U, '0');
    for (std::size_t index = 0U; index < bytes.size(); ++index) {
        result[index * 2U] = digits[bytes[index] >> 4U];
        result[index * 2U + 1U] = digits[bytes[index] & 0x0fU];
    }
    return result;
}

[[nodiscard]] std::vector<std::uint8_t>
bytes_from_hex(const Json &value) {
    const auto text = value.get<std::string>();
    if (text.size() % 2U != 0U ||
        text.size() / 2U > kM11MaximumArtifactBytes) {
        throw std::runtime_error("byte archive length differs");
    }
    std::vector<std::uint8_t> result(text.size() / 2U);
    for (std::size_t index = 0U; index < result.size(); ++index) {
        result[index] = static_cast<std::uint8_t>(
            (hex_digit(text[index * 2U]) << 4U) |
            hex_digit(text[index * 2U + 1U]));
    }
    return result;
}

[[nodiscard]] Json policy_value_json(const PolicyValue &value) {
    if (std::holds_alternative<std::monostate>(value)) {
        return Json{{"kind", "none"}, {"value", nullptr}};
    }
    if (const auto *boolean = std::get_if<bool>(&value);
        boolean != nullptr) {
        return Json{{"kind", "bool"}, {"value", *boolean}};
    }
    if (const auto *integer = std::get_if<std::int64_t>(&value);
        integer != nullptr) {
        return Json{{"kind", "integer"}, {"value", *integer}};
    }
    if (const auto *number = std::get_if<double>(&value);
        number != nullptr) {
        return Json{{"kind", "number"}, {"value", *number}};
    }
    if (const auto *choice = std::get_if<std::string>(&value);
        choice != nullptr) {
        return Json{{"kind", "choice"}, {"value", *choice}};
    }
    std::vector<std::uint64_t> targets;
    for (const auto target : std::get<PolicyEconomySet>(value)) {
        targets.push_back(target.value());
    }
    return Json{{"kind", "economy_set"}, {"value", targets}};
}

[[nodiscard]] PolicyValue policy_value_from_json(const Json &value) {
    require_object(value, {"kind", "value"});
    const auto kind = value.at("kind").get<std::string>();
    if (kind == "none" && value.at("value").is_null()) {
        return std::monostate{};
    }
    if (kind == "bool") {
        return value.at("value").get<bool>();
    }
    if (kind == "integer") {
        return value.at("value").get<std::int64_t>();
    }
    if (kind == "number") {
        const auto result = value.at("value").get<double>();
        if (!std::isfinite(result)) {
            throw std::runtime_error("policy number is not finite");
        }
        return result;
    }
    if (kind == "choice") {
        return value.at("value").get<std::string>();
    }
    if (kind == "economy_set") {
        PolicyEconomySet targets;
        for (const auto raw :
             value.at("value").get<std::vector<std::uint64_t>>()) {
            targets.push_back(EconomyId(raw));
        }
        return targets;
    }
    throw std::runtime_error("policy value kind differs");
}

[[nodiscard]] Json action_json(const NativePolicyAction &value) {
    return Json{
        {"economy", value.economy.value()},
        {"lever", value.lever},
        {"value", policy_value_json(value.value)},
    };
}

[[nodiscard]] NativePolicyAction
action_from_json(const Json &value) {
    require_object(value, {"economy", "lever", "value"});
    return {
        EconomyId(value.at("economy").get<std::uint64_t>()),
        value.at("lever").get<std::string>(),
        policy_value_from_json(value.at("value")),
    };
}

[[nodiscard]] Json policy_version_json(
    const M11PolicyVersion &value) {
    return Json{
        {"economy", value.economy.value()},
        {"last_effective", optional_tick(value.last_effective)},
        {"lever", value.lever},
        {"version", value.version},
    };
}

[[nodiscard]] M11PolicyVersion
policy_version_from_json(const Json &value) {
    require_object(
        value, {"economy", "last_effective", "lever", "version"});
    return {
        EconomyId(value.at("economy").get<std::uint64_t>()),
        value.at("lever").get<std::string>(),
        value.at("version").get<std::uint64_t>(),
        tick_from_json(value.at("last_effective")),
    };
}

[[nodiscard]] Json observation_json(
    const M11ReleasedObservation &value) {
    return Json{
        {"observed_at", value.observed_at.value()},
        {"released_at", value.released_at.value()},
        {"revision", value.revision},
        {"series_id", value.series_id},
        {"value",
         value.value.has_value() ? Json(*value.value) : Json(nullptr)},
    };
}

[[nodiscard]] M11ReleasedObservation
observation_from_json(const Json &value) {
    require_object(
        value,
        {"observed_at", "released_at", "revision", "series_id",
         "value"});
    std::optional<double> number;
    if (!value.at("value").is_null()) {
        number = value.at("value").get<double>();
        if (!std::isfinite(*number)) {
            throw std::runtime_error("observation is not finite");
        }
    }
    return {
        value.at("series_id").get<std::string>(),
        number,
        Tick(value.at("observed_at").get<std::uint64_t>()),
        Tick(value.at("released_at").get<std::uint64_t>()),
        value.at("revision").get<std::uint32_t>(),
    };
}

[[nodiscard]] Json permitted_action_json(
    const M11PermittedAction &value) {
    return Json{
        {"allowed", value.allowed},
        {"current_value", policy_value_json(value.current_value)},
        {"earliest_effective", value.earliest_effective.value()},
        {"lever", value.lever},
        {"policy_version", value.policy_version},
        {"reason_code", value.reason_code},
    };
}

[[nodiscard]] M11PermittedAction
permitted_action_from_json(const Json &value) {
    require_object(
        value,
        {"allowed", "current_value", "earliest_effective", "lever",
         "policy_version", "reason_code"});
    return {
        value.at("lever").get<std::string>(),
        policy_value_from_json(value.at("current_value")),
        value.at("allowed").get<bool>(),
        value.at("reason_code").get<std::string>(),
        value.at("policy_version").get<std::uint64_t>(),
        Tick(value.at("earliest_effective").get<std::uint64_t>()),
    };
}

[[nodiscard]] Json context_json(const M11DecisionContext &value) {
    Json observations = Json::array();
    for (const auto &entry : value.observation) {
        observations.push_back(observation_json(entry));
    }
    Json permitted_actions = Json::array();
    for (const auto &entry : value.permitted_actions) {
        permitted_actions.push_back(permitted_action_json(entry));
    }
    Json policy_versions = Json::array();
    for (const auto &entry : value.policy_versions) {
        policy_versions.push_back(policy_version_json(entry));
    }
    return Json{
        {"administrative_capacity", value.administrative_capacity},
        {"administrative_remaining", value.administrative_remaining},
        {"administrative_reserved", value.administrative_reserved},
        {"administrative_window", value.administrative_window.value()},
        {"answered_by_proposal",
         value.answered_by_proposal.has_value()
             ? Json(*value.answered_by_proposal)
             : Json(nullptr)},
        {"boundary", value.boundary.value()},
        {"context_id", value.context_id},
        {"decision_group", value.decision_group},
        {"decision_window_id", value.decision_window_id},
        {"economy", value.economy.value()},
        {"elapsed_ticks", value.elapsed_ticks},
        {"emergency", value.emergency},
        {"emergency_trigger", value.emergency_trigger},
        {"expires_at", value.expires_at.value()},
        {"observation", std::move(observations)},
        {"permitted_actions", std::move(permitted_actions)},
        {"policy_versions", std::move(policy_versions)},
        {"seat", value.seat},
    };
}

[[nodiscard]] M11DecisionContext
context_from_json(const Json &value) {
    require_object(
        value,
        {"administrative_capacity", "administrative_remaining",
         "administrative_reserved", "administrative_window",
         "answered_by_proposal", "boundary", "context_id",
         "decision_group", "decision_window_id", "economy",
         "elapsed_ticks", "emergency", "emergency_trigger",
         "expires_at", "observation", "permitted_actions",
         "policy_versions", "seat"});
    M11DecisionContext result;
    result.context_id = value.at("context_id").get<std::string>();
    result.decision_window_id =
        value.at("decision_window_id").get<std::string>();
    result.economy =
        EconomyId(value.at("economy").get<std::uint64_t>());
    result.seat = value.at("seat").get<std::string>();
    result.decision_group =
        value.at("decision_group").get<std::string>();
    result.boundary =
        Tick(value.at("boundary").get<std::uint64_t>());
    result.expires_at =
        Tick(value.at("expires_at").get<std::uint64_t>());
    result.administrative_window = Tick(
        value.at("administrative_window").get<std::uint64_t>());
    for (const auto &entry : value.at("observation")) {
        result.observation.push_back(observation_from_json(entry));
    }
    for (const auto &entry : value.at("permitted_actions")) {
        result.permitted_actions.push_back(
            permitted_action_from_json(entry));
    }
    for (const auto &entry : value.at("policy_versions")) {
        result.policy_versions.push_back(
            policy_version_from_json(entry));
    }
    result.administrative_remaining =
        value.at("administrative_remaining").get<double>();
    result.administrative_reserved =
        value.at("administrative_reserved").get<double>();
    result.administrative_capacity =
        value.at("administrative_capacity").get<double>();
    result.emergency = value.at("emergency").get<bool>();
    result.emergency_trigger =
        value.at("emergency_trigger").get<std::string>();
    result.elapsed_ticks =
        value.at("elapsed_ticks").get<std::uint64_t>();
    if (!value.at("answered_by_proposal").is_null()) {
        result.answered_by_proposal =
            value.at("answered_by_proposal").get<std::string>();
    }
    return result;
}

[[nodiscard]] Json proposal_json(const M11PolicyProposal &value) {
    Json actions = Json::array();
    for (const auto &entry : value.actions) {
        actions.push_back(action_json(entry));
    }
    Json versions = Json::array();
    for (const auto &entry : value.based_on_policy_versions) {
        versions.push_back(Json{
            {"lever", entry.lever},
            {"version", entry.version},
        });
    }
    return Json{
        {"actions", std::move(actions)},
        {"based_on_policy_versions", std::move(versions)},
        {"context_id", value.context_id},
        {"idempotency_key", value.idempotency_key},
        {"proposal_id", value.proposal_id},
        {"reason", value.reason},
        {"supersedes_proposal_id",
         value.supersedes_proposal_id.has_value()
             ? Json(*value.supersedes_proposal_id)
             : Json(nullptr)},
    };
}

[[nodiscard]] M11PolicyProposal
proposal_from_json(const Json &value) {
    require_object(
        value,
        {"actions", "based_on_policy_versions", "context_id",
         "idempotency_key", "proposal_id", "reason",
         "supersedes_proposal_id"});
    M11PolicyProposal result;
    result.proposal_id =
        value.at("proposal_id").get<std::string>();
    result.idempotency_key =
        value.at("idempotency_key").get<std::string>();
    result.context_id =
        value.at("context_id").get<std::string>();
    for (const auto &entry : value.at("actions")) {
        result.actions.push_back(action_from_json(entry));
    }
    for (const auto &entry :
         value.at("based_on_policy_versions")) {
        require_object(entry, {"lever", "version"});
        result.based_on_policy_versions.push_back({
            entry.at("lever").get<std::string>(),
            entry.at("version").get<std::uint64_t>(),
        });
    }
    result.reason = value.at("reason").get<std::string>();
    if (!value.at("supersedes_proposal_id").is_null()) {
        result.supersedes_proposal_id =
            value.at("supersedes_proposal_id").get<std::string>();
    }
    return result;
}

[[nodiscard]] Json decision_json(const M11PolicyDecision &value) {
    return Json{
        {"accepted_at", optional_tick(value.accepted_at)},
        {"accepted_sequence", value.accepted_sequence},
        {"adjustment_cost", value.adjustment_cost},
        {"decision_id", value.decision_id},
        {"effective_at", optional_tick(value.effective_at)},
        {"proposal_id", value.proposal_id},
        {"reason_code", value.reason_code},
        {"reserved_administrative_cost",
         value.reserved_administrative_cost},
        {"status", static_cast<std::uint8_t>(value.status)},
    };
}

[[nodiscard]] M11PolicyDecision
decision_from_json(const Json &value) {
    require_object(
        value,
        {"accepted_at", "accepted_sequence", "adjustment_cost",
         "decision_id", "effective_at", "proposal_id", "reason_code",
         "reserved_administrative_cost", "status"});
    return {
        value.at("decision_id").get<std::string>(),
        value.at("proposal_id").get<std::string>(),
        checked_enum<M11DecisionStatus>(
            value.at("status"),
            static_cast<std::uint8_t>(
                M11DecisionStatus::failed_at_execution)),
        value.at("reason_code").get<std::string>(),
        tick_from_json(value.at("accepted_at")),
        tick_from_json(value.at("effective_at")),
        value.at("accepted_sequence").get<std::uint64_t>(),
        value.at("reserved_administrative_cost").get<double>(),
        value.at("adjustment_cost").get<double>(),
    };
}

[[nodiscard]] Json calendar_json(const M11CalendarSpec &value) {
    return Json{
        {"administrative_capacity", value.administrative_capacity},
        {"decision_group", value.decision_group},
        {"offset_ticks", value.offset_ticks},
        {"period_ticks", value.period_ticks},
        {"window_ticks", value.window_ticks},
    };
}

[[nodiscard]] M11CalendarSpec
calendar_from_json(const Json &value) {
    require_object(
        value,
        {"administrative_capacity", "decision_group", "offset_ticks",
         "period_ticks", "window_ticks"});
    return {
        value.at("decision_group").get<std::string>(),
        value.at("period_ticks").get<std::uint32_t>(),
        value.at("offset_ticks").get<std::uint32_t>(),
        value.at("window_ticks").get<std::uint32_t>(),
        value.at("administrative_capacity").get<double>(),
    };
}

[[nodiscard]] Json trigger_json(const M11TriggerSpec &value) {
    return Json{
        {"authorized_seats", value.authorized_seats},
        {"context_expiry_ticks", value.context_expiry_ticks},
        {"cooldown_ticks", value.cooldown_ticks},
        {"decision_group", value.decision_group},
        {"direction", static_cast<std::uint8_t>(value.direction)},
        {"enter_threshold", value.enter_threshold},
        {"exit_threshold", value.exit_threshold},
        {"minimum_persistence_ticks",
         value.minimum_persistence_ticks},
        {"series_id", value.series_id},
        {"trigger_id", value.trigger_id},
    };
}

[[nodiscard]] M11TriggerSpec
trigger_from_json(const Json &value) {
    require_object(
        value,
        {"authorized_seats", "context_expiry_ticks",
         "cooldown_ticks", "decision_group", "direction",
         "enter_threshold", "exit_threshold",
         "minimum_persistence_ticks", "series_id", "trigger_id"});
    return {
        value.at("trigger_id").get<std::string>(),
        value.at("series_id").get<std::string>(),
        value.at("enter_threshold").get<double>(),
        value.at("exit_threshold").get<double>(),
        checked_enum<M11TriggerDirection>(
            value.at("direction"),
            static_cast<std::uint8_t>(
                M11TriggerDirection::below)),
        value.at("minimum_persistence_ticks").get<std::uint32_t>(),
        value.at("cooldown_ticks").get<std::uint32_t>(),
        value.at("context_expiry_ticks").get<std::uint32_t>(),
        value.at("authorized_seats")
            .get<std::vector<std::string>>(),
        value.at("decision_group").get<std::string>(),
    };
}

[[nodiscard]] Json weights_json(const M11CostWeights &value) {
    return Json{
        {"fixed", value.fixed},
        {"linear", value.linear},
        {"quadratic", value.quadratic},
    };
}

[[nodiscard]] M11CostWeights
weights_from_json(const Json &value) {
    require_object(value, {"fixed", "linear", "quadratic"});
    return {
        value.at("fixed").get<double>(),
        value.at("linear").get<double>(),
        value.at("quadratic").get<double>(),
    };
}

[[nodiscard]] Json cost_spec_json(
    const M11AdjustmentCostSpec &value) {
    return Json{
        {"emergency_premium", value.emergency_premium},
        {"major", weights_json(value.major)},
        {"operational", weights_json(value.operational)},
        {"ordinary", weights_json(value.ordinary)},
        {"proposal_administrative_overhead",
         value.proposal_administrative_overhead},
        {"refund_on_cancel", value.refund_on_cancel},
        {"refund_on_failed_execution",
         value.refund_on_failed_execution},
        {"refund_on_supersede", value.refund_on_supersede},
        {"regime_switch", weights_json(value.regime_switch)},
    };
}

[[nodiscard]] M11AdjustmentCostSpec
cost_spec_from_json(const Json &value) {
    require_object(
        value,
        {"emergency_premium", "major", "operational", "ordinary",
         "proposal_administrative_overhead", "refund_on_cancel",
         "refund_on_failed_execution", "refund_on_supersede",
         "regime_switch"});
    M11AdjustmentCostSpec result;
    result.ordinary = weights_from_json(value.at("ordinary"));
    result.major = weights_from_json(value.at("major"));
    result.regime_switch =
        weights_from_json(value.at("regime_switch"));
    result.operational =
        weights_from_json(value.at("operational"));
    result.proposal_administrative_overhead =
        value.at("proposal_administrative_overhead").get<double>();
    result.emergency_premium =
        value.at("emergency_premium").get<double>();
    result.refund_on_cancel =
        value.at("refund_on_cancel").get<double>();
    result.refund_on_supersede =
        value.at("refund_on_supersede").get<double>();
    result.refund_on_failed_execution =
        value.at("refund_on_failed_execution").get<double>();
    return result;
}

[[nodiscard]] Json occupant_json(const M11OccupantSpec &value) {
    Json schedule = Json::array();
    for (const auto &entry : value.schedule) {
        Json actions = Json::array();
        for (const auto &action : entry.actions) {
            actions.push_back(action_json(action));
        }
        schedule.push_back(Json{
            {"actions", std::move(actions)},
            {"boundary", entry.boundary.value()},
            {"decision_group", entry.decision_group},
        });
    }
    return Json{
        {"action_dimensions", value.action_dimensions},
        {"artifact_path", value.artifact_path.generic_string()},
        {"kind", static_cast<std::uint8_t>(value.kind)},
        {"occupant_id", value.occupant_id},
        {"random_action_probability",
         value.random_action_probability},
        {"schedule", std::move(schedule)},
        {"seed", value.seed},
    };
}

[[nodiscard]] M11OccupantSpec
occupant_from_json(const Json &value) {
    require_object(
        value,
        {"action_dimensions", "artifact_path", "kind", "occupant_id",
         "random_action_probability", "schedule", "seed"});
    M11OccupantSpec result;
    result.kind = checked_enum<M11OccupantKind>(
        value.at("kind"),
        static_cast<std::uint8_t>(
            M11OccupantKind::reinforcement_learning));
    result.occupant_id =
        value.at("occupant_id").get<std::string>();
    result.seed = value.at("seed").get<std::uint64_t>();
    result.random_action_probability =
        value.at("random_action_probability").get<double>();
    for (const auto &entry : value.at("schedule")) {
        require_object(
            entry, {"actions", "boundary", "decision_group"});
        M11ScheduledPolicyActions scheduled;
        scheduled.boundary =
            Tick(entry.at("boundary").get<std::uint64_t>());
        scheduled.decision_group =
            entry.at("decision_group").get<std::string>();
        for (const auto &action : entry.at("actions")) {
            scheduled.actions.push_back(action_from_json(action));
        }
        result.schedule.push_back(std::move(scheduled));
    }
    result.artifact_path =
        value.at("artifact_path").get<std::string>();
    result.action_dimensions =
        value.at("action_dimensions")
            .get<std::vector<std::string>>();
    return result;
}

[[nodiscard]] Json seat_json(const M11SeatRuntime &value) {
    const auto artifact_bytes =
        value.artifact.has_value()
            ? value.artifact->source_bytes()
            : std::span<const std::uint8_t>{};
    return Json{
        {"artifact_bytes", hex_bytes(artifact_bytes)},
        {"artifact_sha256", value.artifact_sha256},
        {"decision_counter", value.decision_counter},
        {"economy", value.assignment.economy.value()},
        {"occupant", occupant_json(value.assignment.occupant)},
        {"seat", value.assignment.seat},
    };
}

[[nodiscard]] M11SeatRuntime seat_from_json(const Json &value) {
    require_object(
        value,
        {"artifact_bytes", "artifact_sha256", "decision_counter",
         "economy", "occupant", "seat"});
    M11SeatRuntime result;
    result.assignment.economy =
        EconomyId(value.at("economy").get<std::uint64_t>());
    result.assignment.seat =
        value.at("seat").get<std::string>();
    result.assignment.occupant =
        occupant_from_json(value.at("occupant"));
    result.decision_counter =
        value.at("decision_counter").get<std::uint64_t>();
    result.artifact_sha256 =
        value.at("artifact_sha256").get<std::string>();
    auto bytes = bytes_from_hex(value.at("artifact_bytes"));
    if (result.assignment.occupant.kind ==
        M11OccupantKind::reinforcement_learning) {
        if (bytes.empty()) {
            throw std::runtime_error("RL artifact is absent");
        }
        auto artifact = NativePolicyArtifact::load_bytes(bytes);
        if (!artifact.ok() ||
            artifact.get_if()->info().artifact_sha256 !=
                result.artifact_sha256 ||
            artifact.get_if()->info().action_levers !=
                result.assignment.occupant.action_dimensions) {
            throw std::runtime_error("RL artifact contract differs");
        }
        result.artifact = std::move(*artifact.get_if());
    } else if (!bytes.empty() ||
               !result.artifact_sha256.empty()) {
        throw std::runtime_error(
            "non-RL seat contains an artifact");
    }
    return result;
}

[[nodiscard]] Json event_json(const M11ControllerEvent &value) {
    return Json{
        {"actor", value.actor},
        {"boundary", value.boundary.value()},
        {"canonical_payload", value.canonical_payload},
        {"event_type", value.event_type},
        {"hash", digest_json(value.hash)},
        {"operation_id", value.operation_id},
        {"prior_hash", digest_json(value.prior_hash)},
        {"sequence", value.sequence},
        {"visibility", static_cast<std::uint8_t>(value.visibility)},
    };
}

[[nodiscard]] M11ControllerEvent
event_from_json(const Json &value) {
    require_object(
        value,
        {"actor", "boundary", "canonical_payload", "event_type",
         "hash", "operation_id", "prior_hash", "sequence",
         "visibility"});
    return {
        value.at("sequence").get<std::uint64_t>(),
        Tick(value.at("boundary").get<std::uint64_t>()),
        value.at("event_type").get<std::string>(),
        value.at("operation_id").get<std::string>(),
        value.at("actor").get<std::string>(),
        value.at("canonical_payload").get<std::string>(),
        checked_enum<M11EventVisibility>(
            value.at("visibility"),
            static_cast<std::uint8_t>(
                M11EventVisibility::privileged_audit)),
        digest_from_json(value.at("prior_hash")),
        digest_from_json(value.at("hash")),
    };
}

[[nodiscard]] Json release_json(const M11ReleaseRecord &value) {
    return Json{
        {"economy", value.economy.value()},
        {"observed_at", value.observed_at.value()},
        {"released_at", value.released_at.value()},
        {"revision", value.revision},
        {"sequence", value.sequence},
        {"series_id", value.series_id},
        {"source_event_sequence", value.source_event_sequence},
        {"value",
         value.value.has_value() ? Json(*value.value) : Json(nullptr)},
    };
}

[[nodiscard]] M11ReleaseRecord
release_from_json(const Json &value) {
    require_object(
        value,
        {"economy", "observed_at", "released_at", "revision",
         "sequence", "series_id", "source_event_sequence", "value"});
    std::optional<double> number;
    if (!value.at("value").is_null()) {
        number = value.at("value").get<double>();
    }
    return {
        value.at("sequence").get<std::uint64_t>(),
        EconomyId(value.at("economy").get<std::uint64_t>()),
        value.at("series_id").get<std::string>(),
        Tick(value.at("observed_at").get<std::uint64_t>()),
        Tick(value.at("released_at").get<std::uint64_t>()),
        value.at("revision").get<std::uint32_t>(),
        number,
        value.at("source_event_sequence").get<std::uint64_t>(),
    };
}

[[nodiscard]] Json controller_archive_json(
    const M11ControlledState &state,
    const M11ControllerRunSpec &run_spec) {
    Json calendars = Json::array();
    for (const auto &entry : state.scheduler.calendars()) {
        calendars.push_back(calendar_json(entry));
    }
    Json triggers = Json::array();
    for (const auto &entry : state.scheduler.triggers()) {
        triggers.push_back(trigger_json(entry));
    }
    Json trigger_states = Json::array();
    for (const auto &entry : state.scheduler.trigger_states()) {
        trigger_states.push_back(Json{
            {"active", entry.active},
            {"cooldown_until", entry.cooldown_until.value()},
            {"economy", entry.economy.value()},
            {"persistence_ticks", entry.persistence_ticks},
            {"trigger_id", entry.trigger_id},
        });
    }
    Json policy_versions = Json::array();
    for (const auto &entry : state.coordinator.policy_versions()) {
        policy_versions.push_back(policy_version_json(entry));
    }
    Json contexts = Json::array();
    for (const auto &entry : state.coordinator.contexts()) {
        contexts.push_back(context_json(entry));
    }
    Json pending = Json::array();
    for (const auto &entry : state.coordinator.pending()) {
        pending.push_back(Json{
            {"context", context_json(entry.context)},
            {"decision", decision_json(entry.decision)},
            {"proposal", proposal_json(entry.proposal)},
        });
    }
    Json decisions = Json::array();
    for (const auto &entry : state.coordinator.decisions()) {
        decisions.push_back(decision_json(entry));
    }
    Json budgets = Json::array();
    for (const auto &entry : state.coordinator.budgets()) {
        budgets.push_back(Json{
            {"capacity", entry.capacity},
            {"decision_group", entry.decision_group},
            {"economy", entry.economy.value()},
            {"remaining", entry.remaining},
            {"reserved", entry.reserved},
            {"seat", entry.seat},
            {"window_marker", entry.window_marker.value()},
        });
    }
    Json idempotency = Json::array();
    for (const auto &entry :
         state.coordinator.idempotency_records()) {
        idempotency.push_back(Json{
            {"decision_id", entry.decision_id},
            {"key", entry.key},
            {"request_hash", digest_json(entry.request_hash)},
        });
    }
    Json events = Json::array();
    for (const auto &entry : state.events.events()) {
        events.push_back(event_json(entry));
    }
    Json releases = Json::array();
    for (const auto &entry : state.releases.releases()) {
        releases.push_back(release_json(entry));
    }
    Json seats = Json::array();
    for (const auto &entry : state.seats) {
        seats.push_back(seat_json(entry));
    }
    return Json{
        {"boundary_sequence", state.boundary_sequence},
        {"budgets", std::move(budgets)},
        {"calendars", std::move(calendars)},
        {"contexts", std::move(contexts)},
        {"cost_spec", cost_spec_json(state.coordinator.cost_spec())},
        {"decisions", std::move(decisions)},
        {"events", std::move(events)},
        {"events_head", digest_json(state.events.head_hash())},
        {"events_next_sequence", state.events.next_sequence()},
        {"fill_unassigned_with_null",
         run_spec.fill_unassigned_with_null},
        {"idempotency", std::move(idempotency)},
        {"maximum_events", run_spec.maximum_events},
        {"maximum_releases", run_spec.maximum_releases},
        {"next_decision_sequence",
         state.coordinator.next_decision_sequence()},
        {"opened_context_ids", state.opened_context_ids},
        {"pending", std::move(pending)},
        {"phase", static_cast<std::uint8_t>(state.phase)},
        {"policy_versions", std::move(policy_versions)},
        {"releases", std::move(releases)},
        {"releases_next_sequence", state.releases.next_sequence()},
        {"schema_version", kCheckpointSchemaVersion},
        {"seats", std::move(seats)},
        {"trigger_states", std::move(trigger_states)},
        {"triggers", std::move(triggers)},
        {"worker_count", run_spec.worker_count},
    };
}

[[nodiscard]] bool
checkpointable_advance_options(
    const M11ControllerRunSpec &spec) noexcept {
    return spec.advance_options.domestic.empty() &&
           spec.advance_options.fault_point ==
               simulation::M9FaultPoint::none &&
           !spec.advance_options.require_world_rollback &&
           spec.advance_options.worker_count == spec.worker_count;
}

[[nodiscard]] M11ControlledState
state_from_archive(const Json &root,
                   const simulation::M9World &world,
                   M11ControllerRunSpec &run_spec) {
    require_object(
        root,
        {"boundary_sequence", "budgets", "calendars", "contexts",
         "cost_spec", "decisions", "events", "events_head",
         "events_next_sequence", "fill_unassigned_with_null",
         "idempotency", "maximum_events", "maximum_releases",
         "next_decision_sequence", "opened_context_ids", "pending",
         "phase", "policy_versions", "releases",
         "releases_next_sequence", "schema_version", "seats",
         "trigger_states", "triggers", "worker_count"});
    if (root.at("schema_version").get<std::uint32_t>() !=
        kCheckpointSchemaVersion) {
        throw std::runtime_error("checkpoint schema differs");
    }
    for (const auto &entry : root.at("calendars")) {
        run_spec.calendars.push_back(calendar_from_json(entry));
    }
    for (const auto &entry : root.at("triggers")) {
        run_spec.triggers.push_back(trigger_from_json(entry));
    }
    run_spec.cost_spec =
        cost_spec_from_json(root.at("cost_spec"));
    run_spec.fill_unassigned_with_null =
        root.at("fill_unassigned_with_null").get<bool>();
    run_spec.worker_count =
        root.at("worker_count").get<std::uint32_t>();
    run_spec.advance_options.worker_count = run_spec.worker_count;
    run_spec.maximum_events =
        root.at("maximum_events").get<std::size_t>();
    run_spec.maximum_releases =
        root.at("maximum_releases").get<std::size_t>();
    auto scheduler = M11DecisionScheduler::create(
        run_spec.calendars, run_spec.triggers);
    auto coordinator =
        M11PolicyCoordinator::create(world, run_spec.cost_spec);
    if (!scheduler.ok() || !coordinator.ok() ||
        run_spec.worker_count == 0U ||
        run_spec.maximum_events == 0U ||
        run_spec.maximum_releases == 0U ||
        run_spec.maximum_events >
            kM11MaximumControllerEvents ||
        run_spec.maximum_releases >
            kM11MaximumControllerReleases) {
        throw std::runtime_error("checkpoint run specification differs");
    }
    std::vector<M11TriggerState> trigger_states;
    for (const auto &entry : root.at("trigger_states")) {
        require_object(
            entry,
            {"active", "cooldown_until", "economy",
             "persistence_ticks", "trigger_id"});
        trigger_states.push_back({
            EconomyId(entry.at("economy").get<std::uint64_t>()),
            entry.at("trigger_id").get<std::string>(),
            entry.at("active").get<bool>(),
            entry.at("persistence_ticks").get<std::uint32_t>(),
            Tick(entry.at("cooldown_until").get<std::uint64_t>()),
        });
    }
    if (!scheduler.get_if()
             ->restore_trigger_states(
                 std::move(trigger_states), world.economy_count())
             .ok()) {
        throw std::runtime_error("checkpoint trigger state differs");
    }

    std::vector<M11PolicyVersion> policy_versions;
    for (const auto &entry : root.at("policy_versions")) {
        policy_versions.push_back(
            policy_version_from_json(entry));
    }
    std::vector<M11DecisionContext> contexts;
    for (const auto &entry : root.at("contexts")) {
        contexts.push_back(context_from_json(entry));
    }
    std::vector<M11PendingDecision> pending;
    for (const auto &entry : root.at("pending")) {
        require_object(
            entry, {"context", "decision", "proposal"});
        pending.push_back({
            decision_from_json(entry.at("decision")),
            proposal_from_json(entry.at("proposal")),
            context_from_json(entry.at("context")),
        });
    }
    std::vector<M11PolicyDecision> decisions;
    for (const auto &entry : root.at("decisions")) {
        decisions.push_back(decision_from_json(entry));
    }
    std::vector<M11AdministrativeBudget> budgets;
    for (const auto &entry : root.at("budgets")) {
        require_object(
            entry,
            {"capacity", "decision_group", "economy", "remaining",
             "reserved", "seat", "window_marker"});
        budgets.push_back({
            EconomyId(entry.at("economy").get<std::uint64_t>()),
            entry.at("seat").get<std::string>(),
            entry.at("decision_group").get<std::string>(),
            Tick(entry.at("window_marker").get<std::uint64_t>()),
            entry.at("remaining").get<double>(),
            entry.at("reserved").get<double>(),
            entry.at("capacity").get<double>(),
        });
    }
    std::vector<M11IdempotencyRecord> idempotency;
    for (const auto &entry : root.at("idempotency")) {
        require_object(
            entry, {"decision_id", "key", "request_hash"});
        idempotency.push_back({
            entry.at("key").get<std::string>(),
            digest_from_json(entry.at("request_hash")),
            entry.at("decision_id").get<std::string>(),
        });
    }
    if (!coordinator.get_if()
             ->restore(
                 world, std::move(policy_versions),
                 std::move(contexts), std::move(pending),
                 std::move(decisions), std::move(budgets),
                 std::move(idempotency),
                 root.at("next_decision_sequence")
                     .get<std::uint64_t>())
             .ok()) {
        throw std::runtime_error("checkpoint coordinator differs");
    }

    M11EventStream events(run_spec.maximum_events);
    std::vector<M11ControllerEvent> event_values;
    for (const auto &entry : root.at("events")) {
        event_values.push_back(event_from_json(entry));
    }
    if (!events
             .restore(
                 std::move(event_values),
                 root.at("events_next_sequence")
                     .get<std::uint64_t>(),
                 digest_from_json(root.at("events_head")))
             .ok()) {
        throw std::runtime_error("checkpoint event stream differs");
    }
    M11ReleaseStream releases(run_spec.maximum_releases);
    std::vector<M11ReleaseRecord> release_values;
    for (const auto &entry : root.at("releases")) {
        release_values.push_back(release_from_json(entry));
    }
    if (!releases
             .restore(
                 std::move(release_values),
                 root.at("releases_next_sequence")
                     .get<std::uint64_t>())
             .ok()) {
        throw std::runtime_error("checkpoint release stream differs");
    }

    M11ControlledState state(
        std::move(*scheduler.get_if()),
        std::move(*coordinator.get_if()), std::move(events),
        std::move(releases));
    state.phase = checked_enum<M11BoundaryPhase>(
        root.at("phase"),
        static_cast<std::uint8_t>(
            M11BoundaryPhase::ready_to_commit));
    state.opened_context_ids =
        root.at("opened_context_ids")
            .get<std::vector<std::string>>();
    state.boundary_sequence =
        root.at("boundary_sequence").get<std::uint64_t>();
    for (const auto &entry : root.at("seats")) {
        state.seats.push_back(seat_from_json(entry));
    }
    std::sort(
        state.seats.begin(), state.seats.end(),
        [](const M11SeatRuntime &left,
           const M11SeatRuntime &right) {
            return std::pair{
                       left.assignment.economy.value(),
                       left.assignment.seat} <
                   std::pair{
                       right.assignment.economy.value(),
                       right.assignment.seat};
        });
    if (std::adjacent_find(
            state.seats.begin(), state.seats.end(),
            [](const M11SeatRuntime &left,
               const M11SeatRuntime &right) {
                return left.assignment.economy ==
                           right.assignment.economy &&
                       left.assignment.seat ==
                           right.assignment.seat;
            }) != state.seats.end()) {
        throw std::runtime_error("checkpoint seats are duplicated");
    }
    for (const auto &seat : state.seats) {
        if (seat.assignment.economy.value() >=
                world.economy_count() ||
            !m11_valid_seat(seat.assignment.seat)) {
            throw std::runtime_error("checkpoint seat is invalid");
        }
        run_spec.assignments.push_back(seat.assignment);
    }
    for (const auto &context_id : state.opened_context_ids) {
        if (state.coordinator.find_context(context_id) == nullptr) {
            throw std::runtime_error("checkpoint open context is absent");
        }
    }
    if ((state.phase == M11BoundaryPhase::boundary_start &&
         !state.opened_context_ids.empty()) ||
        (state.phase == M11BoundaryPhase::awaiting_human &&
         state.opened_context_ids.empty())) {
        throw std::runtime_error("checkpoint phase differs");
    }
    return state;
}

} // namespace

Result<std::vector<std::uint8_t>>
save_m11_checkpoint(const M11ControlledSession &session) {
    if (!checkpointable_advance_options(session.run_spec_)) {
        return Status(
            ErrorCode::unsupported,
            "M11 checkpoint does not persist fault-injection options");
    }
    try {
        const auto archive_text =
            controller_archive_json(
                session.state_, session.run_spec_)
                .dump();
        const auto archive = std::span<const std::uint8_t>(
            reinterpret_cast<const std::uint8_t *>(
                archive_text.data()),
            archive_text.size());
        return save_hybrid_checkpoint(
            session.bridge_, {}, archive);
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M11 checkpoint allocation failed");
    } catch (const std::exception &) {
        return Status(ErrorCode::internal_error,
                      "M11 checkpoint encoding failed");
    }
}

Result<M11ControlledSession>
load_m11_checkpoint(std::span<const std::uint8_t> checkpoint) {
    auto loaded = load_hybrid_checkpoint(checkpoint);
    if (!loaded.ok()) {
        return loaded.status();
    }
    try {
        const std::string archive_text(
            reinterpret_cast<const char *>(
                loaded.get_if()->controller_archive.data()),
            loaded.get_if()->controller_archive.size());
        const auto root = Json::parse(archive_text);
        if (root.dump() != archive_text) {
            return corrupt_checkpoint();
        }
        M11ControllerRunSpec run_spec;
        run_spec.calendars.clear();
        run_spec.triggers.clear();
        auto state = state_from_archive(
            root, loaded.get_if()->bridge.engine().world(),
            run_spec);
        auto expected = seal_m11_controller_state(
            loaded.get_if()->bridge.engine().tick(),
            loaded.get_if()->bridge.engine().policy_generation(),
            state);
        if (!expected.ok() ||
            loaded.get_if()->bridge.controller_envelope() !=
                *expected.get_if()) {
            return corrupt_checkpoint();
        }
        return M11ControlledSession(
            std::move(loaded.get_if()->bridge),
            std::move(run_spec), std::move(state));
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M11 checkpoint allocation failed");
    } catch (const std::exception &) {
        return corrupt_checkpoint();
    }
}

} // namespace macro_sim::control
