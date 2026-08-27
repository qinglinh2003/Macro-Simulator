#include "macro_sim/desktop/m11_protocol.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
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

inline constexpr std::array<std::uint8_t, 8> kSaveMagic{'M', 'S', 'D', 'T',
                                                        'P', '0', '1', '1'};
inline constexpr std::uint32_t kSaveSchemaVersion = 2U;
inline constexpr std::size_t kMaximumSaveMetadataBytes = std::size_t{1024} * 1024U;
inline constexpr std::uint64_t kMaximumSaveArchiveBytes =
    2ULL * 1024ULL * 1024ULL * 1024ULL;

struct ProtocolFault final {
    std::string code;
    std::string message;
    bool full_resync{false};
};

struct LoadedDesktopSave final {
    M11NativeNewGame metadata;
    std::string authority_principal;
    std::vector<control::NativePolicyAction> free_policy_actions;
    std::vector<std::uint8_t> checkpoint;
};

[[nodiscard]] std::string random_hex(std::size_t byte_count) {
    static constexpr std::string_view digits = "0123456789abcdef";
    std::random_device source;
    std::string result;
    result.reserve(byte_count * 2U);
    for (std::size_t index = 0U; index < byte_count; ++index) {
        const auto value = static_cast<std::uint8_t>(source());
        result.push_back(digits[value >> 4U]);
        result.push_back(digits[value & 0x0fU]);
    }
    return result;
}

[[nodiscard]] bool constant_time_equal(std::string_view left,
                                       std::string_view right) noexcept {
    std::size_t difference = left.size() ^ right.size();
    const auto count = std::max(left.size(), right.size());
    for (std::size_t index = 0U; index < count; ++index) {
        const auto left_value =
            index < left.size() ? static_cast<unsigned char>(left[index]) : 0U;
        const auto right_value =
            index < right.size() ? static_cast<unsigned char>(right[index]) : 0U;
        difference |= static_cast<std::size_t>(left_value ^ right_value);
    }
    return difference == 0U;
}

[[nodiscard]] Json policy_value_json(const control::PolicyValue &value) {
    if (std::holds_alternative<std::monostate>(value)) {
        return nullptr;
    }
    if (const auto *boolean = std::get_if<bool>(&value); boolean != nullptr) {
        return *boolean;
    }
    if (const auto *integer = std::get_if<std::int64_t>(&value); integer != nullptr) {
        return *integer;
    }
    if (const auto *number = std::get_if<double>(&value); number != nullptr) {
        return *number;
    }
    if (const auto *choice = std::get_if<std::string>(&value); choice != nullptr) {
        return *choice;
    }
    Json result = Json::array();
    for (const auto economy : std::get<control::PolicyEconomySet>(value)) {
        result.push_back(economy.value());
    }
    return result;
}

[[nodiscard]] Result<control::PolicyValue>
protocol_policy_value(const control::PolicyLeverDescriptor &lever, const Json &value) {
    using control::PolicyValue;
    switch (lever.kind) {
    case control::PolicyValueKind::number:
        if (value.is_number() && std::isfinite(value.get<double>())) {
            return PolicyValue(value.get<double>());
        }
        break;
    case control::PolicyValueKind::nullable_number:
        if (value.is_null()) {
            return PolicyValue(std::monostate{});
        }
        if (value.is_number() && std::isfinite(value.get<double>())) {
            return PolicyValue(value.get<double>());
        }
        break;
    case control::PolicyValueKind::integer:
        if (value.is_number_integer()) {
            return PolicyValue(value.get<std::int64_t>());
        }
        break;
    case control::PolicyValueKind::boolean:
        if (value.is_boolean()) {
            return PolicyValue(value.get<bool>());
        }
        break;
    case control::PolicyValueKind::choice:
        if (value.is_string()) {
            return PolicyValue(value.get<std::string>());
        }
        break;
    case control::PolicyValueKind::economy_id:
        if (value.is_null()) {
            return PolicyValue(std::monostate{});
        }
        if (value.is_number_integer()) {
            return PolicyValue(value.get<std::int64_t>());
        }
        break;
    case control::PolicyValueKind::economy_set:
        if (value.is_array()) {
            control::PolicyEconomySet economies;
            economies.reserve(value.size());
            for (const auto &entry : value) {
                if (!entry.is_number_unsigned()) {
                    return Status(ErrorCode::invalid_argument,
                                  "policy economy set is invalid");
                }
                economies.emplace_back(entry.get<std::uint64_t>());
            }
            return PolicyValue(std::move(economies));
        }
        break;
    }
    return Status(ErrorCode::invalid_argument, "policy value is invalid");
}

[[nodiscard]] std::string_view
policy_kind_name(control::PolicyValueKind kind) noexcept {
    switch (kind) {
    case control::PolicyValueKind::number:
        return "number";
    case control::PolicyValueKind::nullable_number:
        return "nullable_number";
    case control::PolicyValueKind::integer:
        return "integer";
    case control::PolicyValueKind::boolean:
        return "boolean";
    case control::PolicyValueKind::choice:
        return "choice";
    case control::PolicyValueKind::economy_id:
        return "economy_id";
    case control::PolicyValueKind::economy_set:
        return "economy_set";
    }
    return "unknown";
}

[[nodiscard]] std::string_view policy_scope_name(control::PolicyScope scope) noexcept {
    return scope == control::PolicyScope::external ? "external" : "economy";
}

[[nodiscard]] Json policy_descriptor_json(const control::PolicyLeverDescriptor &lever) {
    Json choices = Json::array();
    std::string_view remaining = lever.choices;
    while (!remaining.empty()) {
        const auto separator = remaining.find('|');
        choices.push_back(std::string(remaining.substr(0U, separator)));
        if (separator == std::string_view::npos) {
            break;
        }
        remaining.remove_prefix(separator + 1U);
    }
    return {
        {"name", lever.name},
        {"scope", policy_scope_name(lever.scope)},
        {"value_kind", policy_kind_name(lever.kind)},
        {"nullable", lever.kind == control::PolicyValueKind::nullable_number ||
                         lever.kind == control::PolicyValueKind::economy_id},
        {"minimum", lever.minimum.has_value() ? Json(*lever.minimum) : Json(nullptr)},
        {"maximum", lever.maximum.has_value() ? Json(*lever.maximum) : Json(nullptr)},
        {"choices", std::move(choices)},
        {"owner_role", lever.owner_role},
        {"decision_group", lever.decision_group},
        {"implementation_lag", lever.implementation_lag},
        {"emergency_implementation_lag", lever.emergency_implementation_lag.has_value()
                                             ? Json(*lever.emergency_implementation_lag)
                                             : Json(nullptr)},
        {"minimum_hold_ticks", lever.minimum_hold_ticks},
        {"emergency", lever.emergency},
        {"control_scale",
         lever.control_scale.has_value() ? Json(*lever.control_scale) : Json(nullptr)},
        {"maximum_step",
         lever.maximum_step.has_value() ? Json(*lever.maximum_step) : Json(nullptr)},
        {"administrative_weight", lever.administrative_weight},
        {"cost_class", lever.cost_class},
        {"semantics", lever.semantics},
        {"enabled_if", lever.enabled_if},
        {"required_capabilities", lever.required_capabilities},
        {"help_key", "policy." + std::string(lever.name)},
    };
}

[[nodiscard]] Json metric_json(const M11FrontendMetric &metric) {
    return {
        {"stable_id", metric.stable_id},
        {"value", metric.value.has_value() ? Json(*metric.value) : Json(nullptr)},
    };
}

[[nodiscard]] Json policy_json(const M11FrontendPolicy &policy) {
    return {
        {"lever", policy.lever},
        {"value", policy_value_json(policy.value)},
        {"version", policy.version},
    };
}

[[nodiscard]] Json economy_json(const control::M11FrontendEconomy &economy) {
    Json metrics = Json::array();
    for (const auto &metric : economy.metrics) {
        metrics.push_back(metric_json(metric));
    }
    return {
        {"economy_id", economy.economy.value()},
        {"metrics", std::move(metrics)},
    };
}

[[nodiscard]] Json
observation_json(const control::M11ReleasedObservation &observation) {
    return {
        {"series_id", observation.series_id},
        {"value",
         observation.value.has_value() ? Json(*observation.value) : Json(nullptr)},
        {"observed_at", observation.observed_at.value()},
        {"released_at", observation.released_at.value()},
        {"revision", observation.revision},
    };
}

[[nodiscard]] Json policy_version_json(const control::M11PolicyVersion &version) {
    return {
        {"economy_id", version.economy.value()},
        {"lever", version.lever},
        {"version", version.version},
        {"last_effective", version.last_effective.has_value()
                               ? Json(version.last_effective->value())
                               : Json(nullptr)},
    };
}

[[nodiscard]] Json context_json(const control::M11DecisionContext &context) {
    Json observations = Json::array();
    for (const auto &observation : context.observation) {
        observations.push_back(observation_json(observation));
    }
    Json permitted = Json::array();
    for (const auto &action : context.permitted_actions) {
        permitted.push_back({
            {"lever", action.lever},
            {"current_value", policy_value_json(action.current_value)},
            {"allowed", action.allowed},
            {"reason_code", action.reason_code},
            {"policy_version", action.policy_version},
            {"earliest_effective", action.earliest_effective.value()},
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
        {"administrative_window", context.administrative_window.value()},
        {"observation", std::move(observations)},
        {"permitted_actions", std::move(permitted)},
        {"policy_versions", std::move(versions)},
        {"administrative_remaining", context.administrative_remaining},
        {"administrative_reserved", context.administrative_reserved},
        {"administrative_capacity", context.administrative_capacity},
        {"emergency", context.emergency},
        {"emergency_trigger", context.emergency_trigger},
        {"elapsed_ticks", context.elapsed_ticks},
        {"answered_by_proposal", context.answered_by_proposal.has_value()
                                     ? Json(*context.answered_by_proposal)
                                     : Json(nullptr)},
    };
}

[[nodiscard]] Json action_json(const control::NativePolicyAction &action) {
    return {
        {"economy_id", action.economy.value()},
        {"lever", action.lever},
        {"value", policy_value_json(action.value)},
    };
}

[[nodiscard]] Json proposal_json(const control::M11PolicyProposal &proposal) {
    Json actions = Json::array();
    for (const auto &action : proposal.actions) {
        actions.push_back(action_json(action));
    }
    Json versions = Json::array();
    for (const auto &version : proposal.based_on_policy_versions) {
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
        {"supersedes_proposal_id", proposal.supersedes_proposal_id.has_value()
                                       ? Json(*proposal.supersedes_proposal_id)
                                       : Json(nullptr)},
    };
}

[[nodiscard]] Json decision_json(const control::M11PolicyDecision &decision) {
    return {
        {"decision_id", decision.decision_id},
        {"proposal_id", decision.proposal_id},
        {"status", control::m11_decision_status_name(decision.status)},
        {"reason_code", decision.reason_code},
        {"accepted_at", decision.accepted_at.has_value()
                            ? Json(decision.accepted_at->value())
                            : Json(nullptr)},
        {"effective_at", decision.effective_at.has_value()
                             ? Json(decision.effective_at->value())
                             : Json(nullptr)},
        {"accepted_sequence", decision.accepted_sequence},
        {"reserved_administrative_cost", decision.reserved_administrative_cost},
        {"adjustment_cost", decision.adjustment_cost},
    };
}

[[nodiscard]] Json pending_json(const control::M11PendingDecision &pending) {
    return {
        {"decision", decision_json(pending.decision)},
        {"proposal", proposal_json(pending.proposal)},
        {"context", context_json(pending.context)},
    };
}

[[nodiscard]] Json event_json(const control::M11ControllerEvent &event) {
    return {
        {"sequence", event.sequence},
        {"boundary", event.boundary.value()},
        {"event_type", event.event_type},
        {"operation_id", event.operation_id},
        {"actor", event.actor},
        {"canonical_payload", event.canonical_payload},
        {"visibility", static_cast<std::uint8_t>(event.visibility)},
        {"prior_hash", event.prior_hash.hex()},
        {"hash", event.hash.hex()},
    };
}

[[nodiscard]] Json
shock_bulletin_json(const reporting::ShockBulletinProbeRow &bulletin) {
    return {
        {"shock_id", bulletin.shock_id},
        {"kind", static_cast<std::uint8_t>(bulletin.kind)},
        {"economy_id", bulletin.economy.has_value() ? Json(bulletin.economy->value())
                                                    : Json(nullptr)},
        {"announcement", bulletin.announcement.value()},
        {"start", bulletin.start.value()},
        {"expected_end", bulletin.expected_end.value()},
        {"duration", bulletin.duration},
        {"magnitude", bulletin.magnitude},
        {"intensity", bulletin.intensity},
        {"status", static_cast<std::uint8_t>(bulletin.status)},
        {"sector", bulletin.sector.has_value()
                       ? Json(static_cast<std::uint8_t>(*bulletin.sector))
                       : Json(nullptr)},
    };
}

[[nodiscard]] std::string_view firm_sector_name(core::FirmSector sector) noexcept {
    switch (sector) {
    case core::FirmSector::consumption:
        return "consumption";
    case core::FirmSector::capital:
        return "capital";
    case core::FirmSector::energy:
        return "energy";
    case core::FirmSector::construction:
        return "construction";
    }
    return "unknown";
}

[[nodiscard]] std::string_view person_sex_name(core::PersonSex sex) noexcept {
    switch (sex) {
    case core::PersonSex::female:
        return "female";
    case core::PersonSex::male:
        return "male";
    }
    return "unknown";
}

[[nodiscard]] std::string_view owner_kind_name(core::OwnerKind kind) noexcept {
    switch (kind) {
    case core::OwnerKind::household:
        return "household";
    case core::OwnerKind::firm:
        return "firm";
    case core::OwnerKind::bank:
        return "bank";
    case core::OwnerKind::treasury:
        return "treasury";
    case core::OwnerKind::central_bank:
        return "central_bank";
    case core::OwnerKind::dealer:
        return "dealer";
    case core::OwnerKind::rounding_residual:
        return "rounding_residual";
    case core::OwnerKind::institution:
        return "institution";
    }
    return "unknown";
}

[[nodiscard]] std::string_view
equity_issuer_name(core::EquityIssuerKind kind) noexcept {
    return kind == core::EquityIssuerKind::bank ? "bank" : "firm";
}

[[nodiscard]] std::string_view security_kind_name(core::SecurityKind kind) noexcept {
    return kind == core::SecurityKind::equity ? "equity" : "bond";
}

template <typename Id>
[[nodiscard]] Json limited_id_array(const std::vector<Id> &ids, bool include,
                                    std::size_t maximum = 256U) {
    Json result = Json::array();
    if (!include) {
        return result;
    }
    const auto count = std::min(ids.size(), maximum);
    for (std::size_t index = 0U; index < count; ++index) {
        result.push_back(ids[index].value());
    }
    return result;
}

template <typename Id> [[nodiscard]] Json nullable_id(Id id) {
    return id.valid() ? Json(id.value()) : Json(nullptr);
}

[[nodiscard]] Json entity_row_json(const reporting::HouseholdProbeRow &row,
                                   bool include_relations) {
    return {
        {"id", row.id.value()},
        {"account_id", row.account.value()},
        {"cash", row.cash},
        {"debt", row.debt},
        {"income_expected", row.income_expected},
        {"income_realized", row.income_realized},
        {"consumption_budget", row.consumption_budget},
        {"spent", row.spent},
        {"labor_sold", row.labor_sold},
        {"member_count", row.members.size()},
        {"member_ids", limited_id_array(row.members, include_relations)},
        {"member_ids_truncated", include_relations && row.members.size() > 256U},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::FirmProbeRow &row,
                                   bool include_relations) {
    return {
        {"id", row.id.value()},
        {"sector", firm_sector_name(row.sector)},
        {"account_id", row.account.value()},
        {"cash", row.cash},
        {"debt", row.debt},
        {"goods_inventory", row.goods_inventory},
        {"physical_capital", row.physical_capital},
        {"productivity", row.productivity},
        {"total_factor_productivity", row.total_factor_productivity},
        {"posted_price", row.posted_price},
        {"posted_wage", row.posted_wage},
        {"markup", row.markup},
        {"demand_expected", row.demand_expected},
        {"previous_sales", row.previous_sales},
        {"previous_hires", row.previous_hires},
        {"book_equity", row.book_equity},
        {"earnings", row.earnings},
        {"interest_arrears", row.interest_arrears},
        {"eligible_collateral_value", row.eligible_collateral_value},
        {"borrowing_base_headroom", row.borrowing_base_headroom},
        {"residual_income_ema", row.residual_income_ema},
        {"tobin_q_ema", row.tobin_q_ema},
        {"insolvent_days", row.insolvent_days},
        {"shell_days", row.shell_days},
        {"sector_switch_pressure_days", row.sector_switch_pressure_days},
        {"defaulted", row.defaulted},
        {"equity_id", nullable_id(row.equity)},
        {"outstanding_shares", row.outstanding_shares},
        {"share_price", row.share_price},
        {"last_share_price", row.last_share_price},
        {"peak_share_price", row.peak_share_price},
        {"fundamental_per_share", row.fundamental_per_share},
        {"share_trend", row.share_trend},
        {"active", row.active},
        {"employee_count", row.employees.size()},
        {"employee_ids", limited_id_array(row.employees, include_relations)},
        {"employee_ids_truncated", include_relations && row.employees.size() > 256U},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::BankProbeRow &row, bool) {
    return {
        {"id", row.id.value()},
        {"cash_account_id", row.cash_account.value()},
        {"reserve_node_id", row.reserve_node.value()},
        {"cash", row.cash},
        {"reserves", row.reserves},
        {"loan_principal", row.loan_principal},
        {"opening_capital", row.opening_capital},
        {"closing_capital", row.closing_capital},
        {"deposit_interest_arrears", row.deposit_interest_arrears},
        {"leverage_appetite", row.leverage_appetite},
        {"loan_spread", row.loan_spread},
        {"deposit_spread", row.deposit_spread},
        {"equity_id", nullable_id(row.equity)},
        {"outstanding_shares", row.outstanding_shares},
        {"share_price", row.share_price},
        {"last_share_price", row.last_share_price},
        {"peak_share_price", row.peak_share_price},
        {"fundamental_per_share", row.fundamental_per_share},
        {"share_trend", row.share_trend},
        {"alive", row.alive},
        {"resolved", row.resolved},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::PersonProbeRow &row, bool) {
    return {
        {"id", row.id.value()},
        {"sex", person_sex_name(row.sex)},
        {"birth_day", row.birth_day},
        {"death_day", row.death_day},
        {"age_days", row.age_days},
        {"mother_id", nullable_id(row.mother)},
        {"father_id", nullable_id(row.father)},
        {"partner_id", nullable_id(row.partner)},
        {"guardian_id", nullable_id(row.guardian)},
        {"household_id", nullable_id(row.household)},
        {"primary_job_id", nullable_id(row.primary_job)},
        {"secondary_job_id", nullable_id(row.secondary_job)},
        {"efficiency", row.efficiency},
        {"cash", row.cash},
        {"debt", row.debt},
        {"firm_equity", row.firm_equity},
        {"bank_equity", row.bank_equity},
        {"bonds", row.bonds},
        {"gross_assets", row.gross_assets},
        {"net_worth", row.net_worth},
        {"allocated_income", row.allocated_income},
        {"allocated_consumption", row.allocated_consumption},
        {"participating", row.participating},
        {"searching", row.searching},
        {"alive", row.alive},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::JobProbeRow &row, bool) {
    return {
        {"id", row.id.value()},
        {"person_id", row.person.value()},
        {"firm_id", row.firm.value()},
        {"hire_day", row.hire_day},
        {"separation_day", row.separation_day},
        {"suspension_day", row.suspension_day},
        {"wage", row.wage},
        {"hours", row.hours},
        {"secondary", row.secondary},
        {"suspended", row.suspended},
        {"active", row.active},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::DwellingProbeRow &row, bool) {
    return {
        {"id", row.id.value()},
        {"owner_kind", owner_kind_name(row.owner_kind)},
        {"owner_id", row.owner_id},
        {"occupant_household_id", nullable_id(row.occupant_household)},
        {"collateral_loan_id", nullable_id(row.collateral_loan)},
        {"floor_area", row.floor_area},
        {"quality", row.quality},
        {"location", row.location},
        {"age_days", row.age_days},
        {"active", row.active},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::EquityProbeRow &row, bool) {
    return {
        {"id", row.id.value()},
        {"issuer_kind", equity_issuer_name(row.issuer_kind)},
        {"issuer_owner_kind", owner_kind_name(row.issuer.kind())},
        {"issuer_owner_id", row.issuer.value()},
        {"issuer_account_id", row.issuer_account.value()},
        {"currency_id", row.currency.value()},
        {"outstanding_shares", row.outstanding_shares},
        {"price", row.price},
        {"last_price", row.last_price},
        {"peak_price", row.peak_price},
        {"fundamental", row.fundamental},
        {"trend", row.trend},
        {"income_signal", row.income_signal},
        {"active", row.active},
        {"resolved", row.resolved},
    };
}

[[nodiscard]] Json entity_row_json(const reporting::SecurityPositionProbeRow &row,
                                   bool) {
    return {
        {"id", row.id.value()},
        {"security_kind", security_kind_name(row.security_kind)},
        {"security_id", row.security_id},
        {"holder_kind", owner_kind_name(row.holder_kind)},
        {"holder_id", row.holder_id},
        {"units", row.units},
        {"cost_basis", row.cost_basis},
        {"market_value", row.market_value},
    };
}

template <typename Page>
[[nodiscard]] Json entity_page_json(std::string_view kind, const Page &page,
                                    bool include_relations = false) {
    Json rows = Json::array();
    for (const auto &row : page.rows) {
        rows.push_back(entity_row_json(row, include_relations));
    }
    return {
        {"kind", kind},
        {"page",
         {
             {"boundary", page.page.boundary.value()},
             {"economy_id", page.page.economy.value()},
             {"next_after_id", page.page.next_after_id},
             {"total_rows", page.page.total_rows},
             {"has_more", page.page.has_more},
         }},
        {"rows", std::move(rows)},
    };
}

template <typename Value, typename Converter>
[[nodiscard]] Json json_array(const std::vector<Value> &values, Converter &&converter) {
    Json result = Json::array();
    for (const auto &value : values) {
        result.push_back(converter(value));
    }
    return result;
}

[[nodiscard]] Json snapshot_json(const M11FrontendSnapshot &snapshot) {
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
        {"phase", control::m11_boundary_phase_name(snapshot.phase)},
        {"awaiting_human", snapshot.awaiting_human},
        {"event_cursor", snapshot.event_cursor},
        {"release_cursor", snapshot.release_cursor},
        {"metrics", json_array(snapshot.metrics, metric_json)},
        {"economies", json_array(snapshot.economies, economy_json)},
        {"policies", json_array(snapshot.policies, policy_json)},
        {"releases", json_array(snapshot.releases, observation_json)},
        {"contexts", json_array(snapshot.contexts, context_json)},
        {"pending", json_array(snapshot.pending, pending_json)},
        {"public_events", json_array(snapshot.public_events, event_json)},
        {"shock_bulletins", json_array(snapshot.shock_bulletins, shock_bulletin_json)},
    };
}

[[nodiscard]] Json delta_json(const M11FrontendDelta &delta) {
    return {
        {"schema_version", delta.schema_version},
        {"base_snapshot_id", delta.base_snapshot_id.hex()},
        {"result_snapshot_id", delta.result_snapshot_id.hex()},
        {"base_sequence", delta.base_sequence},
        {"result_sequence", delta.result_sequence},
        {"boundary", delta.boundary.value()},
        {"phase", control::m11_boundary_phase_name(delta.phase)},
        {"awaiting_human", delta.awaiting_human},
        {"event_cursor", delta.event_cursor},
        {"release_cursor", delta.release_cursor},
        {"changed_metrics", json_array(delta.changed_metrics, metric_json)},
        {"changed_economies", json_array(delta.changed_economies, economy_json)},
        {"changed_policies", json_array(delta.changed_policies, policy_json)},
        {"releases", json_array(delta.releases, observation_json)},
        {"contexts", json_array(delta.contexts, context_json)},
        {"pending", json_array(delta.pending, pending_json)},
        {"appended_public_events",
         json_array(delta.appended_public_events, event_json)},
        {"shock_bulletins", json_array(delta.shock_bulletins, shock_bulletin_json)},
    };
}

[[nodiscard]] Json decision_result_json(const control::M11DecisionResult &result) {
    Json decisions = Json::array();
    for (const auto &decision : result.decisions) {
        decisions.push_back(decision_json(decision));
    }
    return {
        {"phase", control::m11_boundary_phase_name(result.phase)},
        {"boundary", result.boundary.value()},
        {"elapsed_ticks", result.elapsed_ticks},
        {"opened_context_ids", result.opened_context_ids},
        {"decisions", std::move(decisions)},
        {"awaiting_human", result.awaiting_human},
        {"limit_reached", result.limit_reached},
        {"advanced_ticks",
         result.advance.has_value() ? result.advance->advanced_ticks : 0U},
    };
}

[[nodiscard]] std::optional<Json> parse_strict_json(std::string_view frame) {
    bool invalid = false;
    std::vector<std::set<std::string, std::less<>>> keys;
    const auto callback = [&invalid, &keys](int depth, Json::parse_event_t event,
                                            Json &parsed) {
        if (depth > 64) {
            invalid = true;
            return false;
        }
        if (event == Json::parse_event_t::object_start) {
            keys.emplace_back();
        } else if (event == Json::parse_event_t::key) {
            if (keys.empty() ||
                !keys.back().emplace(parsed.get<std::string>()).second) {
                invalid = true;
                return false;
            }
        } else if (event == Json::parse_event_t::object_end && !keys.empty()) {
            keys.pop_back();
        }
        return true;
    };
    try {
        auto result = Json::parse(frame.begin(), frame.end(), callback, true, true);
        if (invalid || !result.is_object()) {
            return std::nullopt;
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}

[[nodiscard]] std::optional<std::string>
required_text(const Json &request, std::string_view key, std::size_t maximum) {
    if (!request.contains(key) || !request.at(key).is_string()) {
        return std::nullopt;
    }
    auto result = request.at(key).get<std::string>();
    if (result.empty() || result.size() > maximum) {
        return std::nullopt;
    }
    return result;
}

[[nodiscard]] std::optional<std::uint64_t>
required_u64(const Json &request, std::string_view key,
             std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
    if (!request.contains(key) || !request.at(key).is_number_unsigned()) {
        return std::nullopt;
    }
    const auto value = request.at(key).get<std::uint64_t>();
    return value <= maximum ? std::optional<std::uint64_t>(value) : std::nullopt;
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

[[nodiscard]] std::uint32_t read_u32(std::span<const std::uint8_t> bytes,
                                     std::size_t &cursor) {
    if (cursor > bytes.size() || bytes.size() - cursor < 4U) {
        throw ProtocolFault{"corrupt_input", "The desktop save is truncated.", false};
    }
    std::uint32_t value = 0U;
    for (std::size_t index = 0U; index < 4U; ++index) {
        value = (value << 8U) | bytes[cursor++];
    }
    return value;
}

[[nodiscard]] std::uint64_t read_u64(std::span<const std::uint8_t> bytes,
                                     std::size_t &cursor) {
    if (cursor > bytes.size() || bytes.size() - cursor < 8U) {
        throw ProtocolFault{"corrupt_input", "The desktop save is truncated.", false};
    }
    std::uint64_t value = 0U;
    for (std::size_t index = 0U; index < 8U; ++index) {
        value = (value << 8U) | bytes[cursor++];
    }
    return value;
}

[[nodiscard]] Json
save_metadata_json(const M11NativeNewGame &game, std::string_view authority_principal,
                   std::span<const control::NativePolicyAction> free_policy_actions) {
    Json countries = Json::array();
    for (const auto &country : game.countries) {
        countries.push_back({
            {"name", country.name},
            {"code", country.code},
            {"profile", country.profile},
        });
    }
    Json staged = Json::array();
    for (const auto &action : free_policy_actions) {
        staged.push_back(action_json(action));
    }
    return {
        {"authority_principal", authority_principal},
        {"countries", std::move(countries)},
        {"duration_ticks",
         game.duration_ticks.has_value() ? Json(*game.duration_ticks) : Json(nullptr)},
        {"free_policy_actions", std::move(staged)},
        {"model_id", game.model_id},
        {"player_economy", game.player_economy},
        {"run_mode", game.run_mode},
        {"schema_version", game.schema_version},
        {"seed", game.seed},
        {"start_date", game.start_date},
    };
}

[[nodiscard]] std::vector<std::uint8_t>
make_desktop_save(const M11NativeNewGame &game, std::string_view authority_principal,
                  std::span<const control::NativePolicyAction> free_policy_actions,
                  std::span<const std::uint8_t> checkpoint) {
    const auto metadata =
        save_metadata_json(game, authority_principal, free_policy_actions).dump();
    if (metadata.size() > kMaximumSaveMetadataBytes ||
        checkpoint.size() > kMaximumSaveArchiveBytes) {
        throw ProtocolFault{"out_of_range", "The desktop save exceeds its size limit.",
                            false};
    }
    std::vector<std::uint8_t> bytes;
    const auto expected =
        kSaveMagic.size() + 4U + 8U + 8U + metadata.size() + checkpoint.size() + 32U;
    if (expected > kMaximumSaveArchiveBytes) {
        throw ProtocolFault{"out_of_range", "The desktop save exceeds its size limit.",
                            false};
    }
    bytes.reserve(expected);
    bytes.insert(bytes.end(), kSaveMagic.begin(), kSaveMagic.end());
    append_u32(bytes, kSaveSchemaVersion);
    append_u64(bytes, static_cast<std::uint64_t>(metadata.size()));
    append_u64(bytes, static_cast<std::uint64_t>(checkpoint.size()));
    bytes.insert(bytes.end(), metadata.begin(), metadata.end());
    bytes.insert(bytes.end(), checkpoint.begin(), checkpoint.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    return bytes;
}

[[nodiscard]] LoadedDesktopSave load_desktop_save(std::span<const std::uint8_t> bytes) {
    constexpr std::size_t header_size = kSaveMagic.size() + 4U + 8U + 8U;
    if (bytes.size() < header_size + 32U || bytes.size() > kMaximumSaveArchiveBytes ||
        !std::equal(kSaveMagic.begin(), kSaveMagic.end(), bytes.begin())) {
        throw ProtocolFault{"corrupt_input", "The desktop save header is invalid.",
                            false};
    }
    const auto content = bytes.first(bytes.size() - 32U);
    const auto expected_digest = core::sha256_digest(content);
    if (!std::equal(expected_digest.bytes.begin(), expected_digest.bytes.end(),
                    bytes.end() - 32)) {
        throw ProtocolFault{"corrupt_input", "The desktop save digest is invalid.",
                            false};
    }
    std::size_t cursor = kSaveMagic.size();
    if (read_u32(bytes, cursor) != kSaveSchemaVersion) {
        throw ProtocolFault{"corrupt_input",
                            "The desktop save version is incompatible.", false};
    }
    const auto metadata_size = read_u64(bytes, cursor);
    const auto checkpoint_size = read_u64(bytes, cursor);
    if (metadata_size > kMaximumSaveMetadataBytes ||
        checkpoint_size > kMaximumSaveArchiveBytes ||
        metadata_size > static_cast<std::uint64_t>(bytes.size() - cursor - 32U) ||
        checkpoint_size !=
            static_cast<std::uint64_t>(bytes.size() - cursor - 32U) - metadata_size) {
        throw ProtocolFault{"corrupt_input", "The desktop save lengths are invalid.",
                            false};
    }
    const auto metadata_count = static_cast<std::size_t>(metadata_size);
    const auto checkpoint_count = static_cast<std::size_t>(checkpoint_size);
    Json metadata;
    try {
        metadata = Json::parse(
            bytes.begin() + static_cast<std::ptrdiff_t>(cursor),
            bytes.begin() + static_cast<std::ptrdiff_t>(cursor + metadata_count));
    } catch (...) {
        throw ProtocolFault{"corrupt_input", "The desktop save metadata is invalid.",
                            false};
    }
    static constexpr std::array<std::string_view, 10> metadata_fields{{
        "authority_principal",
        "countries",
        "duration_ticks",
        "free_policy_actions",
        "model_id",
        "player_economy",
        "run_mode",
        "schema_version",
        "seed",
        "start_date",
    }};
    if (!metadata.is_object() || metadata.size() != metadata_fields.size() ||
        !std::ranges::all_of(
            metadata_fields,
            [&metadata](std::string_view key) { return metadata.contains(key); }) ||
        !metadata.at("authority_principal").is_string() ||
        !metadata.at("countries").is_array() || !metadata.at("model_id").is_string() ||
        !metadata.at("free_policy_actions").is_array() ||
        !metadata.at("run_mode").is_string() ||
        !metadata.at("start_date").is_string() ||
        !metadata.at("schema_version").is_number_unsigned() ||
        !metadata.at("seed").is_number_unsigned() ||
        !metadata.at("player_economy").is_number_unsigned()) {
        throw ProtocolFault{"corrupt_input",
                            "The desktop save metadata schema is invalid.", false};
    }
    LoadedDesktopSave result;
    result.authority_principal = metadata.at("authority_principal").get<std::string>();
    result.metadata.schema_version = metadata.at("schema_version").get<std::uint32_t>();
    result.metadata.model_id = metadata.at("model_id").get<std::string>();
    result.metadata.seed = metadata.at("seed").get<std::uint64_t>();
    result.metadata.start_date = metadata.at("start_date").get<std::string>();
    result.metadata.player_economy = metadata.at("player_economy").get<std::uint64_t>();
    result.metadata.run_mode = metadata.at("run_mode").get<std::string>();
    if (metadata.at("duration_ticks").is_null()) {
        result.metadata.duration_ticks = std::nullopt;
    } else if (metadata.at("duration_ticks").is_number_unsigned()) {
        result.metadata.duration_ticks =
            metadata.at("duration_ticks").get<std::uint64_t>();
    } else {
        throw ProtocolFault{"corrupt_input", "The desktop save duration is invalid.",
                            false};
    }
    for (const auto &country : metadata.at("countries")) {
        if (!country.is_object() || country.size() != 3U || !country.contains("name") ||
            !country.contains("code") || !country.contains("profile") ||
            !country.at("name").is_string() || !country.at("code").is_string() ||
            !country.at("profile").is_string()) {
            throw ProtocolFault{"corrupt_input", "The desktop save country is invalid.",
                                false};
        }
        result.metadata.countries.push_back({
            country.at("name").get<std::string>(),
            country.at("code").get<std::string>(),
            country.at("profile").get<std::string>(),
        });
    }
    std::set<std::pair<std::uint64_t, std::string>> touched;
    for (const auto &entry : metadata.at("free_policy_actions")) {
        if (!entry.is_object() || entry.size() != 3U || !entry.contains("economy_id") ||
            !entry.contains("lever") || !entry.contains("value") ||
            !entry.at("economy_id").is_number_unsigned() ||
            !entry.at("lever").is_string()) {
            throw ProtocolFault{"corrupt_input",
                                "The desktop save free-policy action is invalid.",
                                false};
        }
        const auto economy = entry.at("economy_id").get<std::uint64_t>();
        const auto lever_name = entry.at("lever").get<std::string>();
        const auto *lever = control::find_m11_policy_lever(lever_name);
        if (economy >= result.metadata.countries.size() || lever == nullptr ||
            !touched.emplace(economy, lever_name).second) {
            throw ProtocolFault{"corrupt_input",
                                "The desktop save free-policy action is invalid.",
                                false};
        }
        auto value = protocol_policy_value(*lever, entry.at("value"));
        if (!value.ok()) {
            throw ProtocolFault{"corrupt_input",
                                "The desktop save free-policy value is invalid.",
                                false};
        }
        if (!control::validate_m11_policy_value(*lever, *value.get_if(),
                                                EconomyId(economy),
                                                result.metadata.countries.size())
                 .ok()) {
            throw ProtocolFault{"corrupt_input",
                                "The desktop save free-policy value is invalid.",
                                false};
        }
        result.free_policy_actions.push_back(
            {EconomyId(economy), lever_name, std::move(*value.get_if())});
    }
    cursor += metadata_count;
    result.checkpoint.assign(
        bytes.begin() + static_cast<std::ptrdiff_t>(cursor),
        bytes.begin() + static_cast<std::ptrdiff_t>(cursor + checkpoint_count));
    return result;
}

[[nodiscard]] bool valid_slot_id(std::string_view slot) noexcept {
    return !slot.empty() && slot.size() <= 64U &&
           std::ranges::all_of(slot, [](char value) {
               return (value >= 'a' && value <= 'z') ||
                      (value >= 'A' && value <= 'Z') ||
                      (value >= '0' && value <= '9') || value == '_' || value == '-';
           });
}

void write_file(const std::filesystem::path &path,
                std::span<const std::uint8_t> bytes) {
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    if (!stream) {
        throw ProtocolFault{"io_error", "The save file could not be opened.", false};
    }
    constexpr std::size_t maximum_chunk = std::size_t{16} * 1024U * 1024U;
    std::size_t offset = 0U;
    while (offset < bytes.size()) {
        const auto count = std::min(maximum_chunk, bytes.size() - offset);
        stream.write(reinterpret_cast<const char *>(bytes.data() + offset),
                     static_cast<std::streamsize>(count));
        if (!stream) {
            throw ProtocolFault{"io_error", "The save file could not be written.",
                                false};
        }
        offset += count;
    }
    stream.flush();
    if (!stream) {
        throw ProtocolFault{"io_error", "The save file could not be flushed.", false};
    }
}

[[nodiscard]] std::vector<std::uint8_t> read_file(const std::filesystem::path &path) {
    std::error_code error;
    const auto size = std::filesystem::file_size(path, error);
    if (error || size > kMaximumSaveArchiveBytes) {
        throw ProtocolFault{"io_error", "The save file size is invalid.", false};
    }
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw ProtocolFault{"not_found", "The save slot does not exist.", false};
    }
    constexpr std::size_t maximum_chunk = std::size_t{16} * 1024U * 1024U;
    std::size_t offset = 0U;
    while (offset < bytes.size()) {
        const auto count = std::min(maximum_chunk, bytes.size() - offset);
        stream.read(reinterpret_cast<char *>(bytes.data() + offset),
                    static_cast<std::streamsize>(count));
        if (!stream) {
            throw ProtocolFault{"io_error", "The save file could not be read.", false};
        }
        offset += count;
    }
    return bytes;
}

[[nodiscard]] Json error_envelope(const Json *request, const ProtocolFault &fault) {
    return {
        {"ok", false},
        {"protocol_version", kM11DesktopProtocolVersion},
        {"request_id", request != nullptr && request->contains("request_id")
                           ? request->at("request_id")
                           : Json(nullptr)},
        {"connection_id", request != nullptr && request->contains("connection_id")
                              ? request->at("connection_id")
                              : Json(nullptr)},
        {"sequence", request != nullptr && request->contains("sequence")
                         ? request->at("sequence")
                         : Json(nullptr)},
        {"session_id", request != nullptr && request->contains("session_id")
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

[[nodiscard]] ProtocolFault status_fault(const Status &status) {
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
    std::vector<control::NativePolicyAction> free_policy_actions;
    std::uint64_t next_free_policy_sequence{0U};
    bool shutdown{false};

    [[nodiscard]] ConnectionState *connection(std::string_view identifier) {
        const auto found =
            std::ranges::find(connections, identifier, &ConnectionState::connection_id);
        if (found != connections.end()) {
            return &*found;
        }
        connections.push_back({std::string(identifier), 0U});
        return &connections.back();
    }

    [[nodiscard]] const Receipt *find_receipt(std::string_view connection_id,
                                              std::uint64_t sequence) const {
        const auto found = std::ranges::find_if(
            receipts, [connection_id, sequence](const Receipt &receipt) {
                return receipt.connection_id == connection_id &&
                       receipt.sequence == sequence;
            });
        return found == receipts.end() ? nullptr : &*found;
    }

    void store_receipt(std::string connection_id, std::uint64_t sequence,
                       std::string request_id, const core::StateDigest &request_hash,
                       std::string response) {
        receipts.push_back({
            std::move(connection_id),
            sequence,
            std::move(request_id),
            request_hash,
            std::move(response),
        });
        while (receipts.size() > kM11MaximumProtocolReceipts) {
            receipts.pop_front();
        }
    }

    [[nodiscard]] ProtocolFault require_session(const Json &request,
                                                std::string_view connection_id,
                                                bool mutable_command) const {
        if (session == nullptr) {
            return {"no_session", "No simulation session is active.", false};
        }
        const auto requested = required_text(request, "session_id", 128U);
        if (!requested.has_value() ||
            !constant_time_equal(*requested, session_identifier)) {
            return {"invalid_session", "The session identifier is invalid.", false};
        }
        if (owner_connection != connection_id) {
            return {
                mutable_command ? "not_session_owner" : "access_denied",
                mutable_command ? "Only the session owner may mutate the simulation."
                                : "The connection cannot access this session.",
                false,
            };
        }
        return {};
    }

    [[nodiscard]] Result<M11FrontendSnapshot>
    create_snapshot(const Json &request, std::string_view connection_id) {
        std::string role = "player";
        if (request.contains("role")) {
            const auto checked = required_text(request, "role", 64U);
            if (!checked.has_value()) {
                return Status(ErrorCode::invalid_argument, "snapshot role is invalid");
            }
            role = *checked;
        }
        std::uint64_t economy = new_game.has_value() ? new_game->player_economy : 0U;
        if (request.contains("economy_id")) {
            const auto checked = required_u64(request, "economy_id");
            if (!checked.has_value()) {
                return Status(ErrorCode::invalid_argument,
                              "snapshot economy is invalid");
            }
            economy = *checked;
        }
        if (role != "player" && !control::m11_valid_seat(role)) {
            return Status(ErrorCode::invalid_argument, "snapshot role is invalid");
        }
        auto result = projection.snapshot(
            *session,
            M11AccessScope{std::string(connection_id), EconomyId(economy), role},
            cache_epoch, next_snapshot_sequence);
        if (result.ok()) {
            ++next_snapshot_sequence;
            snapshots.push_back(*result.get_if());
            while (snapshots.size() > kM11MaximumSnapshotCacheEntries) {
                snapshots.pop_front();
            }
        }
        return result;
    }

    [[nodiscard]] Json free_policy_json() const {
        Json actions = Json::array();
        for (const auto &action : free_policy_actions) {
            actions.push_back(action_json(action));
        }
        return {
            {"enabled", true},
            {"effective_tick", session != nullptr && !free_policy_actions.empty()
                                   ? Json(session->tick().value() + 1U)
                                   : Json(nullptr)},
            {"actions", std::move(actions)},
        };
    }

    void decorate_free_policy(Json &result) const {
        const auto mode = result.at("mode").get<std::string>();
        auto &payload = mode == "delta" ? result.at("delta") : result.at("snapshot");
        payload["control_mode"] = "free_policy";
        payload["free_policy"] = free_policy_json();
    }

    [[nodiscard]] Json free_policy_decision(std::string_view status,
                                            std::optional<Tick> effective) {
        const auto identifier =
            "free-policy:" + std::to_string(session->tick().value()) + ":" +
            std::to_string(next_free_policy_sequence++);
        return {
            {"decision_id", identifier},
            {"proposal_id", identifier},
            {"status", status},
            {"reason_code", ""},
            {"accepted_at", session->tick().value()},
            {"effective_at",
             effective.has_value() ? Json(effective->value()) : Json(nullptr)},
            {"effective_tick",
             effective.has_value() ? Json(effective->value()) : Json(nullptr)},
            {"accepted_sequence", next_free_policy_sequence - 1U},
            {"reserved_administrative_cost", 0.0},
            {"reserved_admin_cost", 0.0},
            {"adjustment_cost", 0.0},
        };
    }

    [[nodiscard]] std::vector<control::NativePolicyAction>
    free_policy_actions_from_request(const Json &request) const {
        if (!request.contains("actions") || !request.at("actions").is_array() ||
            request.at("actions").size() > control::kM11MaximumProposalActions) {
            throw ProtocolFault{"invalid_argument", "The free-policy batch is invalid.",
                                false};
        }
        const auto owner = new_game.has_value() ? new_game->player_economy : 0U;
        std::set<std::pair<std::uint64_t, std::string>> touched;
        std::vector<control::NativePolicyAction> actions;
        actions.reserve(request.at("actions").size());
        for (const auto &entry : request.at("actions")) {
            if (!entry.is_object() || !entry.contains("lever") ||
                !entry.contains("value") || !entry.at("lever").is_string()) {
                throw ProtocolFault{"invalid_argument",
                                    "A free-policy action is invalid.", false};
            }
            auto economy = owner;
            if (entry.contains("economy_id")) {
                if (!entry.at("economy_id").is_number_unsigned()) {
                    throw ProtocolFault{"invalid_argument",
                                        "A free-policy economy is invalid.", false};
                }
                economy = entry.at("economy_id").get<std::uint64_t>();
            }
            if (economy != owner) {
                throw ProtocolFault{"access_denied",
                                    "Free policy cannot target a non-player economy.",
                                    false};
            }
            const auto lever_name = entry.at("lever").get<std::string>();
            const auto *lever = control::find_m11_policy_lever(lever_name);
            if (lever == nullptr || !touched.emplace(economy, lever_name).second) {
                throw ProtocolFault{"invalid_argument",
                                    "A free-policy lever is unknown or duplicated.",
                                    false};
            }
            auto value = protocol_policy_value(*lever, entry.at("value"));
            if (!value.ok()) {
                throw status_fault(value.status());
            }
            auto validated = control::validate_m11_policy_value(
                *lever, *value.get_if(), EconomyId(economy),
                session->engine().world().economy_count());
            if (!validated.ok()) {
                throw status_fault(validated);
            }
            actions.push_back(
                {EconomyId(economy), lever_name, std::move(*value.get_if())});
        }
        std::sort(actions.begin(), actions.end(),
                  [](const control::NativePolicyAction &left,
                     const control::NativePolicyAction &right) {
                      return std::pair{left.economy.value(), left.lever} <
                             std::pair{right.economy.value(), right.lever};
                  });
        return actions;
    }

    [[nodiscard]] Json snapshot_result(const Json &request,
                                       std::string_view connection_id) {
        auto current = create_snapshot(request, connection_id);
        if (!current.ok()) {
            throw status_fault(current.status());
        }
        if (request.contains("base_snapshot_id")) {
            if (!request.at("base_snapshot_id").is_string()) {
                throw ProtocolFault{"invalid_argument",
                                    "The snapshot base identifier is invalid.", true};
            }
            const auto base_id = request.at("base_snapshot_id").get<std::string>();
            const auto found = std::ranges::find_if(
                snapshots, [&base_id, &current](const M11FrontendSnapshot &snapshot) {
                    return snapshot.snapshot_id.hex() == base_id &&
                           snapshot.snapshot_id != current.get_if()->snapshot_id;
                });
            if (found != snapshots.end()) {
                auto delta = projection.delta(*found, *current.get_if());
                if (delta.ok()) {
                    Json result{
                        {"mode", "delta"},
                        {"delta", delta_json(*delta.get_if())},
                    };
                    decorate_free_policy(result);
                    return result;
                }
            }
            Json result{
                {"mode", "full_resync"},
                {"reason", "snapshot_base_unavailable"},
                {"snapshot", snapshot_json(*current.get_if())},
            };
            decorate_free_policy(result);
            return result;
        }
        Json result{
            {"mode", "full"},
            {"snapshot", snapshot_json(*current.get_if())},
        };
        decorate_free_policy(result);
        return result;
    }

    [[nodiscard]] Json new_session_command(const Json &request,
                                           std::string_view connection_id) {
        if (session != nullptr) {
            throw ProtocolFault{"session_exists",
                                "Close the active session before creating another.",
                                false};
        }
        Result<M11NativeNewGame> built =
            request.contains("spec")
                ? parse_m11_native_new_game(request.at("spec").dump())
                : [&]() {
                      std::uint64_t seed = 7U;
                      if (request.contains("seed")) {
                          const auto checked =
                              required_u64(request, "seed", 2147483647U);
                          if (!checked.has_value()) {
                              return Result<M11NativeNewGame>(
                                  Status(ErrorCode::invalid_argument,
                                         "new-game seed is invalid"));
                          }
                          seed = *checked;
                      }
                      return default_m11_native_new_game(seed);
                  }();
        if (!built.ok()) {
            throw status_fault(built.status());
        }
        // The desktop product is an unrestricted policy sandbox. Controller
        // occupants remain available to non-desktop M11 consumers, but desktop
        // sessions never turn policy calendars into player permissions.
        built.get_if()->controller.assignments.clear();
        built.get_if()->controller.fill_unassigned_with_null = true;
        if (!options.built_in_rl_artifact.empty()) {
            for (auto &assignment : built.get_if()->controller.assignments) {
                if (assignment.occupant.kind ==
                    control::M11OccupantKind::reinforcement_learning) {
                    assignment.occupant.artifact_path = options.built_in_rl_artifact;
                }
            }
        }
        control::M11ShockAuthority authority;
        authority.principal = std::string(connection_id);
        authority.granted_seats = {
            "treasury",  "central_bank",     "labor_social",
            "regulator", "external_affairs", "energy",
        };
        authority.allowed_kinds = {
            simulation::ShockKind::productivity,
            simulation::ShockKind::labor_availability,
            simulation::ShockKind::energy_capacity,
            simulation::ShockKind::household_demand,
            simulation::ShockKind::import_capacity,
            simulation::ShockKind::export_capacity,
            simulation::ShockKind::credit_supply,
            simulation::ShockKind::capital_destruction,
            simulation::ShockKind::sovereign_risk_premium,
        };
        authority.allow_all_economies = true;
        authority.allow_global = true;
        authority.maximum_absolute_magnitude = 1.0;
        built.get_if()->controller.shock_authorities.push_back(std::move(authority));
        auto world = simulation::M9World::create(built.get_if()->world);
        if (!world.ok()) {
            throw status_fault(world.status());
        }
        if (!built.get_if()->initial_policy_actions.empty()) {
            auto batch = control::project_m11_policy_actions(
                *world.get_if(), built.get_if()->initial_policy_actions);
            if (!batch.ok()) {
                throw status_fault(batch.status());
            }
            const auto applied = world.get_if()->update_policy_batch(*batch.get_if());
            if (!applied.ok()) {
                throw status_fault(applied);
            }
        }
        auto engine = control::EngineSession::create(std::move(*world.get_if()), 4096U);
        if (!engine.ok()) {
            throw status_fault(engine.status());
        }
        auto controlled = M11ControlledSession::create(
            std::move(*engine.get_if()), std::move(built.get_if()->controller));
        if (!controlled.ok()) {
            throw status_fault(controlled.status());
        }
        session =
            std::make_unique<M11ControlledSession>(std::move(*controlled.get_if()));
        session_identifier = random_hex(16U);
        owner_connection = std::string(connection_id);
        cache_epoch = random_hex(16U);
        next_snapshot_sequence = 1U;
        snapshots.clear();
        free_policy_actions.clear();
        next_free_policy_sequence = 0U;
        new_game = std::move(*built.get_if());
        Json snapshot_request = request;
        snapshot_request["session_id"] = session_identifier;
        auto snapshot = snapshot_result(snapshot_request, connection_id);
        return {
            {"session_id", session_identifier},
            {"model_id", new_game->model_id},
            {"schema_version", new_game->schema_version},
            {"start_date", new_game->start_date},
            {"duration_ticks", new_game->duration_ticks.has_value()
                                   ? Json(*new_game->duration_ticks)
                                   : Json(nullptr)},
            {"player_economy", new_game->player_economy},
            {"control_mode", "free_policy"},
            {"countries",
             [&]() {
                 Json countries = Json::array();
                 for (const auto &country : new_game->countries) {
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

    [[nodiscard]] control::M11PolicyProposal
    proposal_from_request(const Json &request) const {
        const auto context_id = required_text(request, "context_id", 256U);
        const auto operation_id = required_text(request, "operation_id", 128U);
        if (!context_id.has_value() || !operation_id.has_value() ||
            !request.contains("actions") || !request.at("actions").is_array() ||
            request.at("actions").size() > control::kM11MaximumProposalActions) {
            throw ProtocolFault{"invalid_argument", "The policy proposal is invalid.",
                                false};
        }
        const auto *context = session->coordinator().find_context(*context_id);
        if (context == nullptr) {
            throw ProtocolFault{"not_found", "The decision context does not exist.",
                                false};
        }
        control::M11PolicyProposal proposal;
        proposal.proposal_id = std::string(*operation_id);
        proposal.idempotency_key = *operation_id;
        proposal.context_id = *context_id;
        proposal.reason = "player decision";
        if (request.contains("proposal_id")) {
            const auto checked = required_text(request, "proposal_id", 128U);
            if (!checked.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The proposal identifier is invalid.", false};
            }
            proposal.proposal_id = *checked;
        }
        if (request.contains("reason")) {
            if (!request.at("reason").is_string()) {
                throw ProtocolFault{"invalid_argument",
                                    "The proposal reason is invalid.", false};
            }
            proposal.reason = request.at("reason").get<std::string>();
        }
        if (proposal.proposal_id.empty() || proposal.proposal_id.size() > 128U ||
            proposal.reason.size() > 1024U) {
            throw ProtocolFault{"invalid_argument",
                                "The policy proposal metadata is invalid.", false};
        }
        if (request.contains("supersedes_proposal_id")) {
            const auto supersedes =
                required_text(request, "supersedes_proposal_id", 128U);
            if (!supersedes.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The superseded proposal identifier is invalid.",
                                    false};
            }
            proposal.supersedes_proposal_id = *supersedes;
        }
        std::set<std::string, std::less<>> levers;
        for (const auto &entry : request.at("actions")) {
            if (!entry.is_object() || !entry.contains("lever") ||
                !entry.contains("value") || !entry.at("lever").is_string()) {
                throw ProtocolFault{"invalid_argument", "A policy action is invalid.",
                                    false};
            }
            const auto lever_name = entry.at("lever").get<std::string>();
            const auto *lever = control::find_m11_policy_lever(lever_name);
            if (lever == nullptr || !levers.emplace(lever_name).second) {
                throw ProtocolFault{"invalid_argument",
                                    "A policy lever is unknown or duplicated.", false};
            }
            auto economy = static_cast<std::uint64_t>(context->economy.value());
            if (entry.contains("economy_id")) {
                if (!entry.at("economy_id").is_number_unsigned()) {
                    throw ProtocolFault{"invalid_argument",
                                        "A policy economy is invalid.", false};
                }
                economy = entry.at("economy_id").get<std::uint64_t>();
            }
            if (economy != context->economy.value()) {
                throw ProtocolFault{"access_denied",
                                    "A proposal cannot target another economy.", false};
            }
            auto value = protocol_policy_value(*lever, entry.at("value"));
            if (!value.ok()) {
                throw status_fault(value.status());
            }
            proposal.actions.push_back({
                EconomyId(economy),
                lever_name,
                std::move(*value.get_if()),
            });
        }
        for (const auto &version : context->policy_versions) {
            proposal.based_on_policy_versions.push_back(
                {version.lever, version.version});
        }
        return proposal;
    }

    [[nodiscard]] Json policy_schema_command(const Json &request) const {
        std::string role = "player";
        if (request.contains("role")) {
            const auto checked = required_text(request, "role", 64U);
            if (!checked.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The policy schema role is invalid.", false};
            }
            role = *checked;
        }
        std::uint64_t economy = new_game.has_value() ? new_game->player_economy : 0U;
        if (request.contains("economy_id")) {
            const auto checked = required_u64(request, "economy_id");
            if (!checked.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The policy schema economy is invalid.", false};
            }
            economy = *checked;
        }
        if ((role != "player" && !control::m11_valid_seat(role)) ||
            economy >= session->engine().world().economy_count()) {
            throw ProtocolFault{"invalid_argument",
                                "The policy schema scope is invalid.", false};
        }
        auto domestic = session->engine().world().domestic_policy(EconomyId(economy));
        if (!domestic.ok()) {
            throw status_fault(domestic.status());
        }
        const auto &external =
            session->engine()
                .world()
                .external_policies()[static_cast<std::size_t>(economy)];
        const auto capabilities_available =
            [&](const control::PolicyLeverDescriptor &candidate) {
                std::string_view capabilities = candidate.required_capabilities;
                while (!capabilities.empty()) {
                    const auto separator = capabilities.find('|');
                    const auto capability = capabilities.substr(0U, separator);
                    if (!capability.empty() &&
                        !control::m11_world_capability(
                            session->engine().world(), EconomyId(economy),
                            capability)) {
                        return false;
                    }
                    if (separator == std::string_view::npos) {
                        break;
                    }
                    capabilities.remove_prefix(separator + 1U);
                }
                return true;
            };
        Json levers = Json::array();
        for (const auto &lever : control::m11_policy_levers()) {
            if (role != "player" && lever.owner_role != role) {
                continue;
            }
            bool available = capabilities_available(lever);
            std::string_view prerequisites = lever.enabled_if;
            while (available && !prerequisites.empty()) {
                const auto separator = prerequisites.find('|');
                const auto prerequisite_name =
                    prerequisites.substr(0U, separator);
                const auto *prerequisite =
                    control::find_m11_policy_lever(prerequisite_name);
                available = prerequisite != nullptr &&
                            capabilities_available(*prerequisite);
                if (separator == std::string_view::npos) {
                    break;
                }
                prerequisites.remove_prefix(separator + 1U);
            }
            if (role == "player" && !available) {
                continue;
            }
            auto descriptor = policy_descriptor_json(lever);
            if (lever.kind == control::PolicyValueKind::economy_id) {
                Json valid_economies = Json::array();
                for (std::size_t candidate = 0U;
                     candidate < session->engine().world().economy_count();
                     ++candidate) {
                    if (candidate == economy) {
                        continue;
                    }
                    if (lever.name == "peg_anchor" &&
                        session->engine().world().external_policies()[candidate]
                                .fx_regime != simulation::FxRegime::floating) {
                        continue;
                    }
                    valid_economies.push_back(candidate);
                }
                descriptor["choices"] = std::move(valid_economies);
            }
            auto value =
                control::m11_policy_value(*domestic.get_if(), external, lever.name);
            const auto *version = session->coordinator().find_policy_version(
                EconomyId(economy), lever.name);
            if (!value.ok() || version == nullptr) {
                throw ProtocolFault{"internal_error",
                                    "The policy schema projection is incomplete.",
                                    false};
            }
            descriptor["current_value"] = policy_value_json(*value.get_if());
            descriptor["version"] = version->version;
            levers.push_back(std::move(descriptor));
        }
        return {
            {"schema_version", 1U},
            {"economy_id", economy},
            {"role", role},
            {"control_mode", "free_policy"},
            {"levers", std::move(levers)},
        };
    }

    [[nodiscard]] control::M11OccupantSpec
    occupant_from_request(const Json &request) const {
        if (!request.contains("occupant") || !request.at("occupant").is_object()) {
            throw ProtocolFault{"invalid_argument", "The seat occupant is invalid.",
                                false};
        }
        const auto &source = request.at("occupant");
        const auto kind = required_text(source, "kind", 32U);
        if (!kind.has_value()) {
            throw ProtocolFault{"invalid_argument",
                                "The seat occupant kind is invalid.", false};
        }
        control::M11OccupantSpec occupant;
        if (*kind == "null") {
            occupant.kind = control::M11OccupantKind::null_occupant;
        } else if (*kind == "human") {
            occupant.kind = control::M11OccupantKind::human_queue;
        } else if (*kind == "heuristic") {
            occupant.kind = control::M11OccupantKind::heuristic;
        } else if (*kind == "fuzz") {
            occupant.kind = control::M11OccupantKind::random_fuzz;
        } else if (*kind == "scheduled") {
            occupant.kind = control::M11OccupantKind::scheduled;
        } else if (*kind == "rl") {
            occupant.kind = control::M11OccupantKind::reinforcement_learning;
            occupant.artifact_path = options.built_in_rl_artifact;
        } else {
            throw ProtocolFault{"invalid_argument",
                                "The seat occupant kind is invalid.", false};
        }
        occupant.occupant_id = "runtime-" + std::string(*kind);
        if (source.contains("occupant_id")) {
            const auto checked = required_text(source, "occupant_id", 128U);
            if (!checked.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The seat occupant identifier is invalid.", false};
            }
            occupant.occupant_id = *checked;
        }
        if (occupant.occupant_id.empty() || occupant.occupant_id.size() > 128U) {
            throw ProtocolFault{"invalid_argument",
                                "The seat occupant identifier is invalid.", false};
        }
        if (source.contains("seed")) {
            if (!source.at("seed").is_number_unsigned()) {
                throw ProtocolFault{"invalid_argument",
                                    "The seat occupant seed is invalid.", false};
            }
            occupant.seed = source.at("seed").get<std::uint64_t>();
        }
        if (source.contains("random_action_probability")) {
            if (!source.at("random_action_probability").is_number()) {
                throw ProtocolFault{"invalid_argument",
                                    "The random action probability is invalid.", false};
            }
            occupant.random_action_probability =
                source.at("random_action_probability").get<double>();
            if (!std::isfinite(occupant.random_action_probability)) {
                throw ProtocolFault{"invalid_argument",
                                    "The random action probability is invalid.", false};
            }
        }
        return occupant;
    }

    [[nodiscard]] static simulation::ShockKind shock_kind(std::string_view value) {
        if (value == "productivity") {
            return simulation::ShockKind::productivity;
        }
        if (value == "labor_availability") {
            return simulation::ShockKind::labor_availability;
        }
        if (value == "energy_capacity") {
            return simulation::ShockKind::energy_capacity;
        }
        if (value == "household_demand") {
            return simulation::ShockKind::household_demand;
        }
        if (value == "import_capacity") {
            return simulation::ShockKind::import_capacity;
        }
        if (value == "export_capacity") {
            return simulation::ShockKind::export_capacity;
        }
        if (value == "credit_supply") {
            return simulation::ShockKind::credit_supply;
        }
        if (value == "capital_destruction") {
            return simulation::ShockKind::capital_destruction;
        }
        if (value == "sovereign_risk_premium") {
            return simulation::ShockKind::sovereign_risk_premium;
        }
        throw ProtocolFault{"invalid_argument", "The shock kind is invalid.", false};
    }

    [[nodiscard]] static simulation::ShockShape shock_shape(std::string_view value) {
        if (value == "step") {
            return simulation::ShockShape::step;
        }
        if (value == "linear") {
            return simulation::ShockShape::linear;
        }
        if (value == "triangular") {
            return simulation::ShockShape::triangular;
        }
        throw ProtocolFault{"invalid_argument", "The shock shape is invalid.", false};
    }

    [[nodiscard]] static std::optional<simulation::ShockSector>
    shock_sector(std::string_view value) {
        if (value == "consumption") {
            return simulation::ShockSector::consumption;
        }
        if (value == "capital") {
            return simulation::ShockSector::capital;
        }
        if (value == "energy") {
            return simulation::ShockSector::energy;
        }
        if (value == "housing") {
            return simulation::ShockSector::housing;
        }
        if (value == "public") {
            return simulation::ShockSector::public_sector;
        }
        throw ProtocolFault{"invalid_argument", "The shock sector is invalid.", false};
    }

    [[nodiscard]] Json entity_page_command(const Json &request, bool detail) const {
        const auto kind_value = required_text(request, "kind", 64U);
        if (!kind_value.has_value()) {
            throw ProtocolFault{"invalid_argument", "The entity kind is invalid.",
                                false};
        }
        auto kind = *kind_value;
        if (kind == "household") {
            kind = "households";
        } else if (kind == "firm") {
            kind = "firms";
        } else if (kind == "bank") {
            kind = "banks";
        } else if (kind == "person") {
            kind = "persons";
        } else if (kind == "job") {
            kind = "jobs";
        } else if (kind == "dwelling") {
            kind = "dwellings";
        } else if (kind == "equity") {
            kind = "equities";
        } else if (kind == "security_position") {
            kind = "security_positions";
        }
        const bool firm_scoped =
            kind == "firm_jobs" || kind == "firm_persons";
        const bool household_scoped =
            kind == "household_jobs" || kind == "household_persons";
        if (detail && (firm_scoped || household_scoped)) {
            throw ProtocolFault{
                "invalid_argument",
                "Scoped entity queries are page queries.", false};
        }
        std::uint64_t economy = new_game.has_value() ? new_game->player_economy : 0U;
        if (request.contains("economy_id")) {
            const auto checked = required_u64(
                request, "economy_id", session->engine().world().economy_count() - 1U);
            if (!checked.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The entity economy is invalid.", false};
            }
            economy = *checked;
        }
        std::uint64_t after_id = 0U;
        std::uint64_t maximum_rows = 256U;
        std::optional<std::uint64_t> requested_id;
        if (detail) {
            requested_id = required_u64(request, "entity_id");
            if (!requested_id.has_value() || *requested_id == 0U) {
                throw ProtocolFault{"invalid_argument",
                                    "The entity identifier is invalid.", false};
            }
            after_id = *requested_id - 1U;
            maximum_rows = 1U;
        } else {
            if (request.contains("after_id")) {
                const auto checked = required_u64(request, "after_id");
                if (!checked.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The entity cursor is invalid.", false};
                }
                after_id = *checked;
            }
            if (request.contains("maximum_rows")) {
                const auto checked = required_u64(request, "maximum_rows",
                                                  reporting::kMaximumProbePageRows);
                if (!checked.has_value() || *checked == 0U) {
                    throw ProtocolFault{"invalid_argument",
                                        "The entity page size is invalid.", false};
                }
                maximum_rows = *checked;
            }
        }
        Json result;
        const auto economy_id = EconomyId(economy);
        const auto rows = static_cast<std::size_t>(maximum_rows);
        std::optional<std::uint64_t> firm_scope;
        std::optional<std::uint64_t> household_scope;
        if (firm_scoped) {
            firm_scope = required_u64(request, "firm_id");
            if (!firm_scope.has_value() || *firm_scope == 0U) {
                throw ProtocolFault{"invalid_argument",
                                    "The firm scope is invalid.", false};
            }
        }
        if (household_scoped) {
            household_scope = required_u64(request, "household_id");
            if (!household_scope.has_value() || *household_scope == 0U) {
                throw ProtocolFault{
                    "invalid_argument",
                    "The household scope is invalid.", false};
            }
        }
        if (kind == "households") {
            auto page = session->engine().probe_households(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if(), detail);
        } else if (kind == "firms") {
            auto page = session->engine().probe_firms(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if(), detail);
        } else if (kind == "banks") {
            auto page = session->engine().probe_banks(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "persons") {
            auto page = session->engine().probe_persons(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "jobs") {
            auto page = session->engine().probe_jobs(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "household_jobs") {
            auto page = reporting::probe_jobs_for_household(
                session->engine().world(), economy_id,
                HouseholdId(*household_scope), after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "firm_jobs") {
            auto page = reporting::probe_jobs_for_firm(
                session->engine().world(), economy_id, FirmId(*firm_scope),
                after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "firm_persons") {
            auto page = reporting::probe_persons_for_firm(
                session->engine().world(), economy_id, FirmId(*firm_scope),
                after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "household_persons") {
            auto page = reporting::probe_persons_for_household(
                session->engine().world(), economy_id,
                HouseholdId(*household_scope), after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "dwellings") {
            auto page = session->engine().probe_dwellings(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "equities") {
            auto page = session->engine().probe_equities(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else if (kind == "security_positions") {
            auto page =
                session->engine().probe_security_positions(economy_id, after_id, rows);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            result = entity_page_json(kind, *page.get_if());
        } else {
            throw ProtocolFault{"invalid_argument", "The entity kind is not supported.",
                                false};
        }
        if (firm_scope.has_value()) {
            result["firm_id"] = *firm_scope;
        }
        if (household_scope.has_value()) {
            result["household_id"] = *household_scope;
        }
        if (!detail) {
            return result;
        }
        const auto &page_rows = result.at("rows");
        if (page_rows.empty() ||
            page_rows.front().at("id").get<std::uint64_t>() != *requested_id) {
            throw ProtocolFault{"not_found", "The requested entity does not exist.",
                                false};
        }
        return {
            {"kind", kind},
            {"boundary", result.at("page").at("boundary")},
            {"economy_id", economy},
            {"entity", page_rows.front()},
        };
    }

    [[nodiscard]] std::filesystem::path save_slot_path(std::string_view slot) const {
        if (options.save_root.empty()) {
            throw ProtocolFault{"unsupported", "Save storage is not configured.",
                                false};
        }
        if (!valid_slot_id(slot)) {
            throw ProtocolFault{"invalid_argument",
                                "The logical save-slot identifier is invalid.", false};
        }
        return options.save_root / (std::string(slot) + ".msim");
    }

    [[nodiscard]] Json save_slot_command(const Json &request) const {
        const auto slot = required_text(request, "slot_id", 64U);
        if (!slot.has_value()) {
            throw ProtocolFault{"invalid_argument",
                                "The logical save-slot identifier is invalid.", false};
        }
        const auto path = save_slot_path(*slot);
        std::error_code error;
        std::filesystem::create_directories(options.save_root, error);
        if (error) {
            throw ProtocolFault{"io_error", "The save directory could not be created.",
                                false};
        }
        const auto root_status =
            std::filesystem::symlink_status(options.save_root, error);
        if (error || std::filesystem::is_symlink(root_status)) {
            throw ProtocolFault{"io_error", "The save directory is not trusted.",
                                false};
        }
        const auto existing = std::filesystem::symlink_status(path, error);
        if (!error && std::filesystem::is_symlink(existing)) {
            throw ProtocolFault{"io_error", "The save slot is not a regular file.",
                                false};
        }
        error.clear();
        auto checkpoint = control::save_m11_checkpoint(*session);
        if (!checkpoint.ok()) {
            throw status_fault(checkpoint.status());
        }
        if (!new_game.has_value()) {
            throw ProtocolFault{"no_session", "No simulation session is active.",
                                false};
        }
        auto archive = make_desktop_save(*new_game, owner_connection,
                                         free_policy_actions, *checkpoint.get_if());
        const auto temporary =
            options.save_root / (std::string(*slot) + ".tmp-" + random_hex(8U));
        try {
            write_file(temporary, archive);
            std::filesystem::permissions(temporary,
                                         std::filesystem::perms::owner_read |
                                             std::filesystem::perms::owner_write,
                                         std::filesystem::perm_options::replace, error);
            if (error) {
                throw ProtocolFault{
                    "io_error", "The save-file permissions could not be set.", false};
            }
            std::filesystem::rename(temporary, path, error);
            if (error) {
                throw ProtocolFault{"io_error",
                                    "The save slot could not be replaced atomically.",
                                    false};
            }
        } catch (...) {
            std::error_code cleanup_error;
            std::filesystem::remove(temporary, cleanup_error);
            throw;
        }
        return {
            {"slot_id", *slot},
            {"bytes", archive.size()},
            {"digest", core::sha256_digest(archive).hex()},
            {"boundary", session->tick().value()},
        };
    }

    [[nodiscard]] Json load_slot_command(const Json &request,
                                         std::string_view connection_id) {
        if (session != nullptr) {
            throw ProtocolFault{"session_exists",
                                "Close the active session before loading a save.",
                                false};
        }
        const auto slot = required_text(request, "slot_id", 64U);
        if (!slot.has_value()) {
            throw ProtocolFault{"invalid_argument",
                                "The logical save-slot identifier is invalid.", false};
        }
        const auto path = save_slot_path(*slot);
        std::error_code error;
        const auto file_status = std::filesystem::symlink_status(path, error);
        if (error || std::filesystem::is_symlink(file_status) ||
            !std::filesystem::is_regular_file(file_status)) {
            throw ProtocolFault{"not_found", "The save slot does not exist.", false};
        }
        auto archive = read_file(path);
        auto loaded = load_desktop_save(archive);
        if (!constant_time_equal(loaded.authority_principal, connection_id)) {
            throw ProtocolFault{"access_denied",
                                "The save belongs to another launcher identity.",
                                false};
        }
        auto restored = control::load_m11_checkpoint(loaded.checkpoint);
        if (!restored.ok()) {
            throw status_fault(restored.status());
        }
        if (loaded.metadata.schema_version != kM11NewGameSchemaVersion ||
            loaded.metadata.model_id != kM11PlayableModelId ||
            loaded.metadata.countries.size() !=
                restored.get_if()->engine().world().economy_count() ||
            loaded.metadata.player_economy >= loaded.metadata.countries.size()) {
            throw ProtocolFault{"corrupt_input",
                                "The save metadata does not match the engine state.",
                                false};
        }
        session = std::make_unique<M11ControlledSession>(std::move(*restored.get_if()));
        new_game = std::move(loaded.metadata);
        free_policy_actions = std::move(loaded.free_policy_actions);
        next_free_policy_sequence = 0U;
        owner_connection = std::string(connection_id);
        session_identifier = random_hex(16U);
        cache_epoch = random_hex(16U);
        next_snapshot_sequence = 1U;
        snapshots.clear();
        Json snapshot_request = request;
        snapshot_request["session_id"] = session_identifier;
        return {
            {"slot_id", *slot},
            {"session_id", session_identifier},
            {"model_id", new_game->model_id},
            {"start_date", new_game->start_date},
            {"duration_ticks", new_game->duration_ticks.has_value()
                                   ? Json(*new_game->duration_ticks)
                                   : Json(nullptr)},
            {"player_economy", new_game->player_economy},
            {"control_mode", "free_policy"},
            {"projection", snapshot_result(snapshot_request, connection_id)},
        };
    }

    [[nodiscard]] Json dispatch(const Json &request, std::string_view connection_id) {
        const auto command = required_text(request, "command", 64U);
        if (!command.has_value()) {
            throw ProtocolFault{"invalid_request", "The command is missing or invalid.",
                                false};
        }
        if (*command == "hello") {
            return {
                {"worker", "macro_sim_server"},
                {"protocol_version", kM11DesktopProtocolVersion},
                {"model_id", kM11PlayableModelId},
                {"session_active", session != nullptr},
                {"maximum_frame_bytes", options.maximum_frame_bytes},
                {"maximum_response_bytes", options.maximum_response_bytes},
                {"capabilities",
                 {
                     "controlled_session",
                     "free_policy",
                     "snapshot_delta",
                     "role_scoped_release",
                     "native_checkpoint",
                     "native_policy_inference",
                 }},
            };
        }
        if (*command == "new_session" || *command == "new_game") {
            return new_session_command(request, connection_id);
        }
        if (*command == "shutdown") {
            if (session != nullptr) {
                const auto fault = require_session(request, connection_id, true);
                if (!fault.code.empty()) {
                    throw fault;
                }
            }
            shutdown = true;
            return {{"shutdown", true}};
        }
        if (*command == "snapshot") {
            const auto fault = require_session(request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            return snapshot_result(request, connection_id);
        }
        if (*command == "policy_schema" || *command == "get_schema") {
            const auto fault = require_session(request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            return policy_schema_command(request);
        }
        if (*command == "decision_context" || *command == "pending_decisions" ||
            *command == "shock_bulletins") {
            const auto fault = require_session(request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            auto current = create_snapshot(request, connection_id);
            if (!current.ok()) {
                throw status_fault(current.status());
            }
            if (*command == "decision_context") {
                return {
                    {"contexts", json_array(current.get_if()->contexts, context_json)},
                    {"boundary", current.get_if()->boundary.value()},
                };
            }
            if (*command == "pending_decisions") {
                return {
                    {"pending", json_array(current.get_if()->pending, pending_json)},
                    {"boundary", current.get_if()->boundary.value()},
                };
            }
            return {
                {"shock_bulletins",
                 json_array(current.get_if()->shock_bulletins, shock_bulletin_json)},
                {"boundary", current.get_if()->boundary.value()},
            };
        }
        if (*command == "entity_page" || *command == "entity_detail") {
            const auto fault = require_session(request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            return entity_page_command(request, *command == "entity_detail");
        }
        if (*command == "stage_policy") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            if (session->phase() != control::M11BoundaryPhase::boundary_start) {
                throw ProtocolFault{
                    "invalid_transaction_state",
                    "Free policy may only be staged at a clean day boundary.", false};
            }
            free_policy_actions = free_policy_actions_from_request(request);
            return {
                {"control_mode", "free_policy"},
                {"free_policy", free_policy_json()},
                {"decision",
                 free_policy_decision(
                     free_policy_actions.empty() ? "cleared" : "staged",
                     free_policy_actions.empty()
                         ? std::optional<Tick>{}
                         : std::optional<Tick>{Tick(session->tick().value() + 1U)})},
            };
        }
        if (*command == "submit_policy" || *command == "submit_human_policy") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            auto proposal = proposal_from_request(request);
            auto decision =
                *command == "submit_human_policy"
                    ? session->submit_human_proposal(std::move(proposal), connection_id)
                    : session->submit_policy_proposal(std::move(proposal),
                                                      connection_id);
            if (!decision.ok()) {
                throw status_fault(decision.status());
            }
            return {
                {"decision", decision_json(*decision.get_if())},
                {"projection", snapshot_result(request, connection_id)},
            };
        }
        if (*command == "timeout_context") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto context_id = required_text(request, "context_id", 256U);
            const auto operation_id = required_text(request, "operation_id", 128U);
            if (!context_id.has_value() || !operation_id.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The timeout request is invalid.", false};
            }
            auto decision =
                session->timeout_context(*context_id, *operation_id, connection_id);
            if (!decision.ok()) {
                throw status_fault(decision.status());
            }
            return {
                {"decision", decision_json(*decision.get_if())},
                {"projection", snapshot_result(request, connection_id)},
            };
        }
        if (*command == "cancel_policy") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto decision_id = required_text(request, "decision_id", 256U);
            const auto operation_id = required_text(request, "operation_id", 128U);
            if (!decision_id.has_value() || !operation_id.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The cancellation request is invalid.", false};
            }
            auto decision =
                session->cancel_pending(*decision_id, *operation_id, connection_id);
            if (!decision.ok()) {
                throw status_fault(decision.status());
            }
            return {
                {"decision", decision_json(*decision.get_if())},
                {"projection", snapshot_result(request, connection_id)},
            };
        }
        if (*command == "assign_seat") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto economy = required_u64(
                request, "economy_id", session->engine().world().economy_count() - 1U);
            const auto seat = required_text(request, "seat", 64U);
            const auto operation_id = required_text(request, "operation_id", 128U);
            if (!economy.has_value() || !seat.has_value() ||
                !control::m11_valid_seat(*seat) || !operation_id.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The seat assignment is invalid.", false};
            }
            auto occupant = occupant_from_request(request);
            const auto assigned = session->assign_seat({
                *operation_id,
                std::string(connection_id),
                EconomyId(*economy),
                *seat,
                std::move(occupant),
            });
            if (!assigned.ok()) {
                throw status_fault(assigned.status());
            }
            const auto &archived = assigned.get_if()->archived_occupant_id;
            return {
                {"assigned", true},
                {"economy_id", *economy},
                {"seat", *seat},
                {"archived_occupant_id",
                 archived.has_value() ? Json(*archived) : Json(nullptr)},
                {"repeated", assigned.get_if()->repeated},
            };
        }
        if (*command == "restore_seat") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto economy = required_u64(
                request, "economy_id", session->engine().world().economy_count() - 1U);
            const auto seat = required_text(request, "seat", 64U);
            const auto operation_id = required_text(request, "operation_id", 128U);
            const auto archived_occupant_id =
                required_text(request, "archived_occupant_id", 256U);
            if (!economy.has_value() || !seat.has_value() ||
                !control::m11_valid_seat(*seat) || !operation_id.has_value() ||
                !archived_occupant_id.has_value()) {
                throw ProtocolFault{"invalid_argument",
                                    "The seat restoration is invalid.", false};
            }
            auto restored = session->restore_seat({
                *operation_id,
                std::string(connection_id),
                EconomyId(*economy),
                *seat,
                *archived_occupant_id,
            });
            if (!restored.ok()) {
                throw status_fault(restored.status());
            }
            const auto &archived = restored.get_if()->archived_occupant_id;
            return {
                {"restored", true},
                {"economy_id", *economy},
                {"seat", *seat},
                {"archived_occupant_id",
                 archived.has_value() ? Json(*archived) : Json(nullptr)},
                {"repeated", restored.get_if()->repeated},
            };
        }
        if (*command == "event_page") {
            const auto fault = require_session(request, connection_id, false);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto first_sequence = required_u64(request, "first_sequence");
            const auto maximum_rows = required_u64(request, "maximum_rows", 256U);
            if (!first_sequence.has_value() || !maximum_rows.has_value() ||
                *maximum_rows == 0U) {
                throw ProtocolFault{"invalid_argument",
                                    "The event page request is invalid.", false};
            }
            auto visibility = control::M11EventVisibility::public_record;
            if (request.contains("visibility")) {
                const auto requested = required_text(request, "visibility", 32U);
                if (!requested.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The event visibility is invalid.", false};
                }
                if (*requested == "institution") {
                    visibility = control::M11EventVisibility::institution;
                } else if (*requested == "privileged_audit") {
                    visibility = control::M11EventVisibility::privileged_audit;
                } else if (*requested != "public_record") {
                    throw ProtocolFault{"invalid_argument",
                                        "The event visibility is invalid.", false};
                }
            }
            auto page = session->events().page(
                *first_sequence, static_cast<std::size_t>(*maximum_rows), visibility);
            if (!page.ok()) {
                throw status_fault(page.status());
            }
            const auto next_sequence = page.get_if()->empty()
                                           ? session->events().next_sequence()
                                           : page.get_if()->back().sequence + 1U;
            return {
                {"events", json_array(*page.get_if(), event_json)},
                {"first_sequence", *first_sequence},
                {"next_sequence", next_sequence},
                {"event_cursor", session->events().next_sequence()},
                {"head_hash", session->events().head_hash().hex()},
            };
        }
        if (*command == "schedule_shock" || *command == "trigger_shock") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            const auto operation_id = required_text(request, "operation_id", 128U);
            if (!operation_id.has_value() || !request.contains("shock") ||
                !request.at("shock").is_object()) {
                throw ProtocolFault{"invalid_argument", "The shock request is invalid.",
                                    false};
            }
            const auto &source = request.at("shock");
            const auto shock_id = required_u64(source, "shock_id");
            const auto kind = required_text(source, "kind", 64U);
            const auto start = required_u64(source, "start");
            const auto duration = required_u64(source, "duration", 36500U);
            if (!shock_id.has_value() || !kind.has_value() || !start.has_value() ||
                !duration.has_value() || *duration == 0U ||
                !source.contains("magnitude") || !source.at("magnitude").is_number()) {
                throw ProtocolFault{"invalid_argument",
                                    "The shock specification is invalid.", false};
            }
            simulation::ShockSpec shock;
            shock.id = *shock_id;
            shock.kind = shock_kind(*kind);
            shock.start = Tick(*start);
            shock.duration = *duration;
            shock.magnitude = source.at("magnitude").get<double>();
            if (!std::isfinite(shock.magnitude)) {
                throw ProtocolFault{"invalid_argument",
                                    "The shock magnitude is invalid.", false};
            }
            std::string shape = "step";
            if (source.contains("shape")) {
                const auto checked = required_text(source, "shape", 32U);
                if (!checked.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock shape is invalid.", false};
                }
                shape = *checked;
            }
            shock.shape = shock_shape(shape);
            if (source.contains("ramp_in_ticks")) {
                const auto checked = required_u64(source, "ramp_in_ticks", 36500U);
                if (!checked.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock ramp-in is invalid.", false};
                }
                shock.ramp_in_ticks = *checked;
            }
            if (source.contains("ramp_out_ticks")) {
                const auto checked = required_u64(source, "ramp_out_ticks", 36500U);
                if (!checked.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock ramp-out is invalid.", false};
                }
                shock.ramp_out_ticks = *checked;
            }
            if (source.contains("announcement")) {
                const auto announcement = required_u64(source, "announcement");
                if (!announcement.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock announcement is invalid.", false};
                }
                shock.announcement = Tick(*announcement);
            }
            if (source.contains("economy_id") && !source.at("economy_id").is_null()) {
                const auto economy =
                    required_u64(source, "economy_id",
                                 session->engine().world().economy_count() - 1U);
                if (!economy.has_value()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock economy is invalid.", false};
                }
                shock.economy = EconomyId(*economy);
            }
            if (source.contains("sector") && !source.at("sector").is_null()) {
                if (!source.at("sector").is_string()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock sector is invalid.", false};
                }
                shock.sector = shock_sector(source.at("sector").get<std::string>());
            }
            std::optional<std::string> seat;
            if (request.contains("seat")) {
                const auto checked = required_text(request, "seat", 64U);
                if (!checked.has_value() || !control::m11_valid_seat(*checked)) {
                    throw ProtocolFault{"invalid_argument",
                                        "The shock seat is invalid.", false};
                }
                seat = *checked;
            }
            auto scheduled = session->schedule_shock({
                *operation_id,
                std::string(connection_id),
                std::string(connection_id),
                std::move(seat),
                shock,
            });
            if (!scheduled.ok()) {
                throw status_fault(scheduled.status());
            }
            return {
                {"shock_id", scheduled.get_if()->shock_id},
                {"accepted_at", scheduled.get_if()->accepted_at.value()},
                {"event_sequence", scheduled.get_if()->event_sequence},
                {"repeated", scheduled.get_if()->repeated},
                {"projection", snapshot_result(request, connection_id)},
            };
        }
        if (*command == "advance") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            std::uint64_t ticks = 1U;
            if (request.contains("ticks")) {
                const auto checked = required_u64(request, "ticks", 10000U);
                if (!checked.has_value()) {
                    throw ProtocolFault{"out_of_range",
                                        "Advance ticks must be between 1 and 10000.",
                                        false};
                }
                ticks = *checked;
            }
            if (ticks < 1U) {
                throw ProtocolFault{"out_of_range",
                                    "Advance ticks must be between 1 and 10000.",
                                    false};
            }
            if (request.contains("stop_after_context_boundary")) {
                if (!request.at("stop_after_context_boundary").is_boolean()) {
                    throw ProtocolFault{"invalid_argument",
                                        "The advance stop mode is invalid.", false};
                }
            }
            const bool had_staged_policy = !free_policy_actions.empty();
            const auto effective_tick = Tick(session->tick().value() + 1U);
            auto advanced =
                session->advance_free_policy(free_policy_actions, {ticks, false});
            if (!advanced.ok()) {
                throw status_fault(advanced.status());
            }
            if (advanced.get_if()->elapsed_ticks > 0U) {
                free_policy_actions.clear();
            }
            auto projection_result = snapshot_result(request, connection_id);
            Json result{
                {"advance", decision_result_json(*advanced.get_if())},
                {"projection", std::move(projection_result)},
            };
            if (had_staged_policy && advanced.get_if()->elapsed_ticks > 0U) {
                result["decision"] = free_policy_decision("effective", effective_tick);
            }
            return result;
        }
        if (*command == "save_slot") {
            const auto fault = require_session(request, connection_id, true);
            if (!fault.code.empty()) {
                throw fault;
            }
            return save_slot_command(request);
        }
        if (*command == "load_slot") {
            return load_slot_command(request, connection_id);
        }
        if (*command == "close_session") {
            const auto fault = require_session(request, connection_id, true);
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
            free_policy_actions.clear();
            next_free_policy_sequence = 0U;
            return {{"closed", true}};
        }
        throw ProtocolFault{"unknown_command", "The command is not supported.", false};
    }

    [[nodiscard]] std::string handle(std::string_view frame) {
        const auto parsed = parse_strict_json(frame);
        if (!parsed.has_value()) {
            return error_envelope(nullptr, {"malformed_json",
                                            "The request is not valid JSON.", false})
                .dump();
        }
        const auto &request = *parsed;
        if (!request.contains("protocol_version") ||
            !request.at("protocol_version").is_number_unsigned() ||
            request.at("protocol_version").get<std::uint32_t>() !=
                kM11DesktopProtocolVersion) {
            return error_envelope(&request,
                                  {"protocol_mismatch",
                                   "The protocol version is incompatible.", false})
                .dump();
        }
        const auto request_id = required_text(request, "request_id", 128U);
        const auto connection_id = required_text(request, "connection_id", 128U);
        const auto token = required_text(request, "token", 64U);
        if (!request_id.has_value() || !connection_id.has_value() ||
            !token.has_value() || !request.contains("sequence") ||
            !request.at("sequence").is_number_unsigned()) {
            return error_envelope(&request,
                                  {"invalid_request",
                                   "The request envelope is incomplete.", false})
                .dump();
        }
        if (!constant_time_equal(*token, options.capability_token)) {
            return error_envelope(&request, {"authentication_failed",
                                             "The capability token is invalid.", false})
                .dump();
        }
        const auto sequence = request.at("sequence").get<std::uint64_t>();
        const auto bytes = std::span(
            reinterpret_cast<const std::uint8_t *>(frame.data()), frame.size());
        const auto request_hash = core::sha256_digest(bytes);
        if (const auto *receipt = find_receipt(*connection_id, sequence);
            receipt != nullptr) {
            if (receipt->request_id == *request_id &&
                receipt->request_hash == request_hash) {
                return receipt->response;
            }
            return error_envelope(
                       &request,
                       {"sequence_conflict",
                        "The sequence was already used by a different request.", false})
                .dump();
        }
        auto *connection_state = connection(*connection_id);
        if (sequence != connection_state->last_sequence + 1U) {
            return error_envelope(&request,
                                  {"sequence_gap",
                                   "The request sequence is not contiguous.", true})
                .dump();
        }
        Json envelope;
        try {
            auto result = dispatch(request, *connection_id);
            envelope = {
                {"ok", true},
                {"protocol_version", kM11DesktopProtocolVersion},
                {"request_id", *request_id},
                {"connection_id", *connection_id},
                {"sequence", sequence},
                {"session_id",
                 session != nullptr ? Json(session_identifier) : Json(nullptr)},
                {"result", std::move(result)},
            };
        } catch (const ProtocolFault &fault) {
            envelope = error_envelope(&request, fault);
        } catch (...) {
            envelope = error_envelope(
                &request, {"internal_error",
                           "The worker could not complete the request.", false});
        }
        auto response = envelope.dump();
        if (response.size() > options.maximum_response_bytes) {
            response =
                error_envelope(&request,
                               {"response_too_large",
                                "The response exceeds the configured limit.", false})
                    .dump();
        }
        connection_state->last_sequence = sequence;
        store_receipt(*connection_id, sequence, *request_id, request_hash, response);
        return response;
    }
};

bool valid_m11_capability_token(std::string_view token) noexcept {
    return token.size() == 64U && std::ranges::all_of(token, [](char value) {
               return (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f');
           });
}

M11ProtocolWorker::M11ProtocolWorker(Impl *implementation) noexcept
    : implementation_(implementation) {}

M11ProtocolWorker::M11ProtocolWorker(M11ProtocolWorker &&other) noexcept
    : implementation_(std::exchange(other.implementation_, nullptr)) {}

M11ProtocolWorker &M11ProtocolWorker::operator=(M11ProtocolWorker &&other) noexcept {
    if (this != &other) {
        delete implementation_;
        implementation_ = std::exchange(other.implementation_, nullptr);
    }
    return *this;
}

M11ProtocolWorker::~M11ProtocolWorker() { delete implementation_; }

Result<M11ProtocolWorker> M11ProtocolWorker::create(M11ProtocolOptions options) {
    if (!valid_m11_capability_token(options.capability_token) ||
        options.maximum_frame_bytes < 1024U ||
        options.maximum_frame_bytes > kM11MaximumProtocolFrameBytes ||
        options.maximum_response_bytes < 1024U ||
        options.maximum_response_bytes > kM11MaximumProtocolResponseBytes ||
        (!options.save_root.empty() && !options.save_root.is_absolute()) ||
        (!options.built_in_rl_artifact.empty() &&
         !options.built_in_rl_artifact.is_absolute())) {
        return Status(ErrorCode::invalid_argument, "M11 protocol options are invalid");
    }
    try {
        auto implementation = std::make_unique<Impl>();
        implementation->options = std::move(options);
        return M11ProtocolWorker(implementation.release());
    } catch (...) {
        return Status(ErrorCode::allocation_failure, "M11 protocol allocation failed");
    }
}

std::string M11ProtocolWorker::handle_frame(std::string_view frame) {
    if (implementation_ == nullptr) {
        return error_envelope(nullptr, {"invalid_worker",
                                        "The protocol worker is unavailable.", false})
            .dump();
    }
    if (frame.empty() || frame.size() > implementation_->options.maximum_frame_bytes) {
        return error_envelope(nullptr, {"frame_too_large",
                                        "The request frame size is invalid.", false})
            .dump();
    }
    return implementation_->handle(frame);
}

bool M11ProtocolWorker::shutdown_requested() const noexcept {
    return implementation_ != nullptr && implementation_->shutdown;
}

bool M11ProtocolWorker::has_session() const noexcept {
    return implementation_ != nullptr && implementation_->session != nullptr;
}

std::string_view M11ProtocolWorker::session_id() const noexcept {
    return implementation_ != nullptr
               ? std::string_view(implementation_->session_identifier)
               : std::string_view{};
}

} // namespace macro_sim::desktop
