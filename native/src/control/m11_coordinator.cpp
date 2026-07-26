#include "macro_sim/control/m11_coordinator.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <span>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m4.hpp"

namespace macro_sim::control {
namespace {

constexpr double kBudgetTolerance = 1.0e-12;
constexpr std::size_t kMaximumIdentifierBytes = 128U;
constexpr std::size_t kMaximumReasonBytes = 4096U;
constexpr std::size_t kMaximumConservativeAttempts = 4096U;

[[nodiscard]] bool valid_identifier(std::string_view value) noexcept {
    if (value.empty() || value.size() > kMaximumIdentifierBytes) {
        return false;
    }
    return std::all_of(value.begin(), value.end(), [](char character) {
        const auto byte = static_cast<unsigned char>(character);
        return byte >= 0x21U && byte <= 0x7eU;
    });
}

[[nodiscard]] bool valid_actor(std::string_view value) noexcept {
    return !value.empty() && value.size() <= 256U &&
           value.find('\0') == std::string_view::npos;
}

[[nodiscard]] std::vector<std::string_view>
split_contract_list(std::string_view value) {
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

[[nodiscard]] std::string context_identifier(
    EconomyId economy, std::string_view seat,
    std::string_view decision_group, Tick boundary, bool emergency,
    std::string_view trigger) {
    std::ostringstream stream;
    stream << "ctx:" << economy.value() << ':' << seat << ':'
           << decision_group << ':' << boundary.value() << ':';
    if (emergency) {
        stream << "emergency:" << trigger;
    } else {
        stream << "regular";
    }
    return stream.str();
}

[[nodiscard]] Tick administrative_window_marker(
    const M11CalendarSpec &calendar, Tick boundary) noexcept {
    if (boundary.value() < calendar.offset_ticks) {
        return Tick(calendar.offset_ticks);
    }
    const auto cycle =
        (boundary.value() - calendar.offset_ticks) /
        calendar.period_ticks;
    return Tick(calendar.offset_ticks +
                cycle * calendar.period_ticks);
}

[[nodiscard]] const M11CalendarSpec *calendar_for(
    const M11DecisionScheduler &scheduler,
    std::string_view decision_group) noexcept {
    static const M11CalendarSpec emergency_calendar{
        "emergency", 91U, 0U, 1U, 20.0};
    if (decision_group == "emergency") {
        return &emergency_calendar;
    }
    const auto &calendars = scheduler.calendars();
    const auto found =
        std::lower_bound(calendars.begin(), calendars.end(), decision_group,
                         [](const M11CalendarSpec &calendar,
                            std::string_view name) {
                             return calendar.decision_group < name;
                         });
    return found == calendars.end() ||
                   found->decision_group != decision_group
               ? nullptr
               : &*found;
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_string(std::vector<std::uint8_t> &bytes,
                   std::string_view value) {
    append_u64(bytes, static_cast<std::uint64_t>(value.size()));
    bytes.insert(bytes.end(), value.begin(), value.end());
}

void append_policy_value(std::vector<std::uint8_t> &bytes,
                         const PolicyValue &value) {
    bytes.push_back(static_cast<std::uint8_t>(value.index()));
    if (const auto *boolean = std::get_if<bool>(&value)) {
        bytes.push_back(*boolean ? 1U : 0U);
    } else if (const auto *integer =
                   std::get_if<std::int64_t>(&value)) {
        append_u64(bytes, static_cast<std::uint64_t>(*integer));
    } else if (const auto *number = std::get_if<double>(&value)) {
        const auto text = [&] {
            std::ostringstream stream;
            stream << std::setprecision(17) << *number;
            return stream.str();
        }();
        append_string(bytes, text);
    } else if (const auto *text =
                   std::get_if<std::string>(&value)) {
        append_string(bytes, *text);
    } else if (const auto *economies =
                   std::get_if<PolicyEconomySet>(&value)) {
        append_u64(
            bytes, static_cast<std::uint64_t>(economies->size()));
        for (const auto economy : *economies) {
            append_u64(bytes, economy.value());
        }
    }
}

[[nodiscard]] core::StateDigest
proposal_hash(const M11PolicyProposal &proposal) {
    std::vector<std::uint8_t> bytes;
    append_string(bytes, proposal.proposal_id);
    append_string(bytes, proposal.idempotency_key);
    append_string(bytes, proposal.context_id);
    append_string(bytes, proposal.reason);
    append_string(bytes, proposal.supersedes_proposal_id.value_or(""));
    append_u64(bytes, static_cast<std::uint64_t>(proposal.actions.size()));
    for (const auto &action : proposal.actions) {
        append_u64(bytes, action.economy.value());
        append_string(bytes, action.lever);
        append_policy_value(bytes, action.value);
    }
    append_u64(
        bytes,
        static_cast<std::uint64_t>(
            proposal.based_on_policy_versions.size()));
    for (const auto &version : proposal.based_on_policy_versions) {
        append_string(bytes, version.lever);
        append_u64(bytes, version.version);
    }
    return core::sha256_digest(bytes);
}

[[nodiscard]] const M11ProposalVersion *proposal_version(
    std::span<const M11ProposalVersion> versions,
    std::string_view lever) noexcept {
    const auto found =
        std::lower_bound(versions.begin(), versions.end(), lever,
                         [](const M11ProposalVersion &entry,
                            std::string_view name) {
                             return entry.lever < name;
                         });
    return found == versions.end() || found->lever != lever ? nullptr
                                                            : &*found;
}

[[nodiscard]] const M11PermittedAction *permitted_action(
    std::span<const M11PermittedAction> actions,
    std::string_view lever) noexcept {
    const auto found =
        std::lower_bound(actions.begin(), actions.end(), lever,
                         [](const M11PermittedAction &entry,
                            std::string_view name) {
                             return entry.lever < name;
                         });
    return found == actions.end() || found->lever != lever ? nullptr
                                                           : &*found;
}

[[nodiscard]] const M11PendingDecision *active_pending_for_lever(
    std::span<const M11PendingDecision> pending, EconomyId economy,
    std::string_view lever, std::string_view excluded_decision = {}) noexcept {
    const auto found =
        std::find_if(pending.begin(), pending.end(),
                     [&](const M11PendingDecision &item) {
                         if (item.decision.status !=
                                 M11DecisionStatus::accepted_pending ||
                             item.context.economy != economy ||
                             item.decision.decision_id ==
                                 excluded_decision) {
                             return false;
                         }
                         return std::any_of(
                             item.proposal.actions.begin(),
                             item.proposal.actions.end(),
                             [lever](const NativePolicyAction &action) {
                                 return action.lever == lever;
                             });
                     });
    return found == pending.end() ? nullptr : &*found;
}

[[nodiscard]] const M11PendingDecision *pending_for_proposal(
    std::span<const M11PendingDecision> pending,
    std::string_view proposal_id) noexcept {
    const auto found =
        std::find_if(pending.begin(), pending.end(),
                     [proposal_id](const M11PendingDecision &item) {
                         return item.proposal.proposal_id == proposal_id &&
                                item.decision.status ==
                                    M11DecisionStatus::accepted_pending;
                     });
    return found == pending.end() ? nullptr : &*found;
}

[[nodiscard]] bool policy_truthy(const PolicyValue &value) noexcept {
    if (const auto *boolean = std::get_if<bool>(&value)) {
        return *boolean;
    }
    if (const auto *integer =
            std::get_if<std::int64_t>(&value)) {
        return *integer != 0;
    }
    if (const auto *number = std::get_if<double>(&value)) {
        return *number != 0.0;
    }
    if (const auto *text =
            std::get_if<std::string>(&value)) {
        return !text->empty();
    }
    if (const auto *economies =
            std::get_if<PolicyEconomySet>(&value)) {
        return !economies->empty();
    }
    return false;
}

[[nodiscard]] Result<PolicyValue> world_policy_value(
    const simulation::M9World &world, EconomyId economy,
    std::string_view lever) {
    auto domestic = world.domestic_policy(economy);
    if (!domestic.ok()) {
        return domestic.status();
    }
    const auto index = static_cast<std::size_t>(economy.value());
    if (index >= world.external_policies().size()) {
        return Status(ErrorCode::out_of_range,
                      "M11 policy economy is out of range");
    }
    return m11_policy_value(
        *domestic.get_if(), world.external_policies()[index], lever);
}

[[nodiscard]] Result<PolicyValue> batch_policy_value(
    const simulation::WorldPolicyBatch &batch, EconomyId economy,
    std::string_view lever) {
    const auto index = static_cast<std::size_t>(economy.value());
    if (index >= batch.domestic.size() ||
        index >= batch.external.size()) {
        return Status(ErrorCode::out_of_range,
                      "M11 projected policy economy is out of range");
    }
    return m11_policy_value(
        batch.domestic[index], batch.external[index], lever);
}

[[nodiscard]] Status validate_enabled_prerequisites(
    const simulation::WorldPolicyBatch &batch,
    std::span<const NativePolicyAction> actions) {
    for (const auto &action : actions) {
        const auto *lever = find_m11_policy_lever(action.lever);
        if (lever == nullptr) {
            return Status(ErrorCode::not_found,
                          "M11 proposal policy lever was not found");
        }
        for (const auto prerequisite :
             split_contract_list(lever->enabled_if)) {
            auto value =
                batch_policy_value(batch, action.economy, prerequisite);
            if (!value.ok()) {
                return value.status();
            }
            if (!policy_truthy(*value.get_if())) {
                return Status(ErrorCode::contract_violation,
                              "M11 policy prerequisite is disabled");
            }
        }
    }
    return Status::success();
}

[[nodiscard]] Result<simulation::M9World> project_timeline_before(
    const simulation::M9World &world,
    std::span<const M11PendingDecision> pending, Tick effective_tick,
    std::string_view excluded_decision) {
    auto projected = world;
    std::vector<const M11PendingDecision *> timeline;
    for (const auto &item : pending) {
        if (item.decision.status != M11DecisionStatus::accepted_pending ||
            !item.decision.effective_at.has_value() ||
            *item.decision.effective_at >= effective_tick ||
            item.decision.decision_id == excluded_decision) {
            continue;
        }
        timeline.push_back(&item);
    }
    std::sort(
        timeline.begin(), timeline.end(),
        [](const M11PendingDecision *left,
           const M11PendingDecision *right) {
            return std::tuple{
                       left->decision.effective_at->value(),
                       left->decision.accepted_sequence,
                       left->decision.decision_id} <
                   std::tuple{
                       right->decision.effective_at->value(),
                       right->decision.accepted_sequence,
                       right->decision.decision_id};
        });
    std::size_t cursor = 0U;
    while (cursor < timeline.size()) {
        const auto group_tick =
            timeline[cursor]->decision.effective_at->value();
        std::vector<NativePolicyAction> actions;
        while (cursor < timeline.size() &&
               timeline[cursor]->decision.effective_at->value() ==
                   group_tick) {
            actions.insert(
                actions.end(),
                timeline[cursor]->proposal.actions.begin(),
                timeline[cursor]->proposal.actions.end());
            ++cursor;
        }
        auto batch = project_m11_policy_actions(projected, actions);
        if (!batch.ok()) {
            return batch.status();
        }
        auto prerequisite_status =
            validate_enabled_prerequisites(*batch.get_if(), actions);
        if (!prerequisite_status.ok()) {
            return prerequisite_status;
        }
        auto status = projected.update_policy_batch(*batch.get_if());
        if (!status.ok()) {
            return status;
        }
    }
    return projected;
}

[[nodiscard]] std::vector<NativePolicyAction> flatten_actions(
    std::span<const M11PendingDecision *const> candidates) {
    std::vector<NativePolicyAction> actions;
    for (const auto *candidate : candidates) {
        actions.insert(actions.end(), candidate->proposal.actions.begin(),
                       candidate->proposal.actions.end());
    }
    std::sort(actions.begin(), actions.end(),
              [](const NativePolicyAction &left,
                 const NativePolicyAction &right) {
                  return std::pair{left.economy.value(), left.lever} <
                         std::pair{right.economy.value(), right.lever};
              });
    return actions;
}

[[nodiscard]] Result<simulation::WorldPolicyBatch> validate_candidate_set(
    const simulation::M9World &world,
    std::span<const M11PendingDecision *const> candidates) {
    auto actions = flatten_actions(candidates);
    auto batch = project_m11_policy_actions(world, actions);
    if (!batch.ok()) {
        return batch.status();
    }
    auto status =
        validate_enabled_prerequisites(*batch.get_if(), actions);
    if (!status.ok()) {
        return status;
    }
    return std::move(*batch.get_if());
}

[[nodiscard]] std::vector<NativePolicyAction> changed_actions(
    const simulation::M9World &world,
    const simulation::WorldPolicyBatch &batch) {
    std::vector<NativePolicyAction> result;
    const auto levers = m11_policy_levers();
    for (std::size_t economy = 0U;
         economy < world.economy_count(); ++economy) {
        const auto economy_id =
            EconomyId(static_cast<std::uint32_t>(economy));
        for (const auto &lever : levers) {
            auto before =
                world_policy_value(world, economy_id, lever.name);
            auto after =
                batch_policy_value(batch, economy_id, lever.name);
            if (before.ok() && after.ok() &&
                !m11_policy_values_equal(*before.get_if(),
                                         *after.get_if())) {
                result.push_back(
                    {economy_id, std::string(lever.name),
                     *after.get_if()});
            }
        }
    }
    return result;
}

[[nodiscard]] std::string event_payload(
    std::string_view name, std::string_view identifier,
    std::string_view reason = {}) {
    std::string result = "{\"";
    result += name;
    result += "\":\"";
    result += identifier;
    result += '"';
    if (!reason.empty()) {
        result += ",\"reason\":\"";
        result += reason;
        result += '"';
    }
    result += '}';
    return result;
}

[[nodiscard]] bool same_touched_levers(
    const M11PolicyProposal &left,
    const M11PolicyProposal &right) {
    std::vector<std::string_view> left_names;
    std::vector<std::string_view> right_names;
    for (const auto &action : left.actions) {
        left_names.push_back(action.lever);
    }
    for (const auto &action : right.actions) {
        right_names.push_back(action.lever);
    }
    std::sort(left_names.begin(), left_names.end());
    std::sort(right_names.begin(), right_names.end());
    return left_names == right_names;
}

[[nodiscard]] bool policy_version_less(const M11PolicyVersion &left,
                                       const M11PolicyVersion &right) {
    return std::pair{left.economy.value(), left.lever} <
           std::pair{right.economy.value(), right.lever};
}

[[nodiscard]] bool context_less(const M11DecisionContext &left,
                                const M11DecisionContext &right) {
    return left.context_id < right.context_id;
}

[[nodiscard]] bool pending_less(const M11PendingDecision &left,
                                const M11PendingDecision &right) {
    return left.decision.decision_id < right.decision.decision_id;
}

[[nodiscard]] bool decision_less(const M11PolicyDecision &left,
                                 const M11PolicyDecision &right) {
    return left.decision_id < right.decision_id;
}

[[nodiscard]] bool budget_less(const M11AdministrativeBudget &left,
                               const M11AdministrativeBudget &right) {
    return std::tuple{left.economy.value(), left.seat,
                      left.decision_group} <
           std::tuple{right.economy.value(), right.seat,
                      right.decision_group};
}

} // namespace

std::string_view m11_decision_status_name(
    M11DecisionStatus status) noexcept {
    switch (status) {
        case M11DecisionStatus::rejected:
            return "rejected";
        case M11DecisionStatus::accepted_noop:
            return "accepted_noop";
        case M11DecisionStatus::accepted_pending:
            return "accepted_pending";
        case M11DecisionStatus::effective:
            return "effective";
        case M11DecisionStatus::cancelled:
            return "cancelled";
        case M11DecisionStatus::superseded:
            return "superseded";
        case M11DecisionStatus::failed_at_execution:
            return "failed_at_execution";
    }
    return "unknown";
}

bool m11_world_capability(const simulation::M9World &world,
                          EconomyId economy,
                          std::string_view capability) noexcept {
    const auto *real = world.economy_real_runtime(economy);
    const auto *monetary = world.economy_monetary_runtime(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    const auto *domestic = world.economy_runtime(economy);
    if (real == nullptr || monetary == nullptr || financial == nullptr ||
        domestic == nullptr) {
        return false;
    }
    const auto has = [&](simulation::M4Capability item) {
        return (real->capability_mask &
                simulation::capability_bit(item)) != 0U;
    };
    if (capability == "government") {
        return has(simulation::M4Capability::government);
    }
    if (capability == "bank_enabled") {
        return has(simulation::M4Capability::commercial_banks);
    }
    if (capability == "bank_realized_pnl") {
        return monetary->rules.realized_bank_pnl;
    }
    if (capability == "bonds") {
        return has(simulation::M4Capability::securities);
    }
    if (capability == "consumption_strata") {
        return financial->rules.consumption_strata;
    }
    if (capability == "energy_enabled") {
        return domestic->energy_rules.enabled;
    }
    if (capability == "energy_household") {
        return domestic->energy_rules.enabled &&
               domestic->energy_rules.household_energy;
    }
    if (capability == "household_credit") {
        return monetary->rules.household_credit;
    }
    if (capability == "housing_construction_enabled") {
        return domestic->housing_rules.enabled &&
               domestic->housing_rules.construction;
    }
    if (capability == "housing_enabled") {
        return domestic->housing_rules.enabled;
    }
    if (capability == "housing_market_enabled") {
        return domestic->housing_rules.enabled &&
               domestic->housing_rules.resale_market;
    }
    if (capability == "interbank") {
        return monetary->rules.interbank;
    }
    if (capability == "margin_credit") {
        return financial->rules.margin_credit;
    }
    if (capability == "mortgage_enabled") {
        return domestic->housing_rules.enabled &&
               domestic->housing_rules.mortgages;
    }
    return false;
}

Result<M11PolicyCoordinator> M11PolicyCoordinator::create(
    const simulation::M9World &world,
    M11AdjustmentCostSpec cost_spec) {
    auto cost_status = validate_m11_cost_spec(cost_spec);
    if (!cost_status.ok()) {
        return cost_status;
    }
    if (world.economy_count() == 0U) {
        return Status(ErrorCode::invalid_argument,
                      "M11 coordinator requires an economy");
    }
    M11PolicyCoordinator result(std::move(cost_spec));
    const auto levers = m11_policy_levers();
    result.policy_versions_.reserve(
        world.economy_count() * levers.size());
    for (std::size_t economy = 0U;
         economy < world.economy_count(); ++economy) {
        const auto economy_id =
            EconomyId(static_cast<std::uint32_t>(economy));
        for (const auto &lever : levers) {
            result.policy_versions_.push_back(
                {economy_id, std::string(lever.name), 0U, std::nullopt});
        }
    }
    return result;
}

const M11DecisionContext *M11PolicyCoordinator::find_context(
    std::string_view context_id) const noexcept {
    const auto found =
        std::lower_bound(contexts_.begin(), contexts_.end(), context_id,
                         [](const M11DecisionContext &context,
                            std::string_view id) {
                             return context.context_id < id;
                         });
    return found == contexts_.end() || found->context_id != context_id
               ? nullptr
               : &*found;
}

const M11PolicyDecision *M11PolicyCoordinator::find_decision(
    std::string_view decision_id) const noexcept {
    const auto found =
        std::lower_bound(decisions_.begin(), decisions_.end(), decision_id,
                         [](const M11PolicyDecision &decision,
                            std::string_view id) {
                             return decision.decision_id < id;
                         });
    return found == decisions_.end() || found->decision_id != decision_id
               ? nullptr
               : &*found;
}

const M11PendingDecision *M11PolicyCoordinator::find_pending(
    std::string_view decision_id) const noexcept {
    const auto found =
        std::lower_bound(pending_.begin(), pending_.end(), decision_id,
                         [](const M11PendingDecision &pending,
                            std::string_view id) {
                             return pending.decision.decision_id < id;
                         });
    return found == pending_.end() ||
                   found->decision.decision_id != decision_id
               ? nullptr
               : &*found;
}

Result<std::uint64_t> M11PolicyCoordinator::policy_version(
    EconomyId economy, std::string_view lever) const noexcept {
    const auto *found = find_policy_version(economy, lever);
    return found == nullptr
               ? Result<std::uint64_t>(
                     Status(ErrorCode::not_found,
                            "M11 policy version was not found"))
               : Result<std::uint64_t>(found->version);
}

const M11PolicyVersion *M11PolicyCoordinator::find_policy_version(
    EconomyId economy, std::string_view lever) const noexcept {
    const auto key = std::pair{economy.value(), lever};
    const auto found =
        std::lower_bound(policy_versions_.begin(), policy_versions_.end(),
                         key,
                         [](const M11PolicyVersion &entry,
                            const auto &candidate) {
                             return std::pair{
                                        entry.economy.value(),
                                        std::string_view(entry.lever)} <
                                    candidate;
                         });
    return found == policy_versions_.end() ||
                   found->economy != economy ||
                   found->lever != lever
               ? nullptr
               : &*found;
}

M11PolicyVersion *M11PolicyCoordinator::mutable_policy_version(
    EconomyId economy, std::string_view lever) noexcept {
    const auto key = std::pair{economy.value(), lever};
    const auto found =
        std::lower_bound(policy_versions_.begin(), policy_versions_.end(),
                         key,
                         [](const M11PolicyVersion &entry,
                            const auto &candidate) {
                             return std::pair{
                                        entry.economy.value(),
                                        std::string_view(entry.lever)} <
                                    candidate;
                         });
    return found == policy_versions_.end() ||
                   found->economy != economy ||
                   found->lever != lever
               ? nullptr
               : &*found;
}

M11DecisionContext *M11PolicyCoordinator::mutable_context(
    std::string_view context_id) noexcept {
    return const_cast<M11DecisionContext *>(find_context(context_id));
}

M11PendingDecision *M11PolicyCoordinator::mutable_pending(
    std::string_view decision_id) noexcept {
    return const_cast<M11PendingDecision *>(find_pending(decision_id));
}

M11PolicyDecision *M11PolicyCoordinator::mutable_decision(
    std::string_view decision_id) noexcept {
    return const_cast<M11PolicyDecision *>(find_decision(decision_id));
}

M11AdministrativeBudget *M11PolicyCoordinator::mutable_budget(
    EconomyId economy, std::string_view seat,
    std::string_view decision_group) noexcept {
    const auto key =
        std::tuple{economy.value(), seat, decision_group};
    const auto found =
        std::lower_bound(
            budgets_.begin(), budgets_.end(), key,
            [](const M11AdministrativeBudget &budget,
               const auto &candidate) {
                return std::tuple{
                           budget.economy.value(),
                           std::string_view(budget.seat),
                           std::string_view(budget.decision_group)} <
                       candidate;
            });
    return found == budgets_.end() || found->economy != economy ||
                   found->seat != seat ||
                   found->decision_group != decision_group
               ? nullptr
               : &*found;
}

Result<M11AdministrativeBudget *>
M11PolicyCoordinator::ensure_budget(
    const M11DecisionScheduler &scheduler, EconomyId economy,
    std::string_view seat, std::string_view decision_group,
    Tick boundary) {
    const auto *calendar =
        calendar_for(scheduler, decision_group);
    if (calendar == nullptr) {
        return Status(ErrorCode::not_found,
                      "M11 decision calendar was not found");
    }
    const auto marker =
        administrative_window_marker(*calendar, boundary);
    auto *budget =
        mutable_budget(economy, seat, decision_group);
    if (budget == nullptr) {
        budgets_.push_back({
            economy,
            std::string(seat),
            std::string(decision_group),
            marker,
            calendar->administrative_capacity,
            0.0,
            calendar->administrative_capacity,
        });
        std::sort(budgets_.begin(), budgets_.end(), budget_less);
        budget = mutable_budget(economy, seat, decision_group);
    } else if (budget->window_marker != marker) {
        budget->window_marker = marker;
        budget->remaining = calendar->administrative_capacity;
        budget->reserved = 0.0;
        budget->capacity = calendar->administrative_capacity;
    }
    return budget;
}

Result<M11DecisionContext> M11PolicyCoordinator::open_context(
    const simulation::M9World &world,
    const M11DecisionScheduler &scheduler, Tick boundary,
    EconomyId economy, std::string seat,
    std::string decision_group, Tick expires_at, bool emergency,
    std::string emergency_trigger, std::uint64_t elapsed_ticks) {
    if (boundary != world.tick() ||
        static_cast<std::size_t>(economy.value()) >=
            world.economy_count() ||
        !m11_valid_seat(seat) || expires_at < boundary ||
        (!emergency &&
         !m11_valid_decision_group(decision_group)) ||
        (emergency && (!valid_identifier(emergency_trigger) ||
                       decision_group != "emergency")) ||
        (!emergency && !emergency_trigger.empty())) {
        return Status(ErrorCode::invalid_argument,
                      "M11 decision context request is invalid");
    }
    const auto context_id =
        context_identifier(economy, seat, decision_group, boundary,
                           emergency, emergency_trigger);
    if (const auto *existing = find_context(context_id);
        existing != nullptr) {
        return *existing;
    }
    if (contexts_.size() >= kM11MaximumDecisionContexts) {
        return Status(ErrorCode::out_of_range,
                      "M11 decision context capacity was reached");
    }
    const auto budget_group = std::string_view(decision_group);
    auto budget_result =
        ensure_budget(scheduler, economy, seat, budget_group, boundary);
    if (!budget_result.ok()) {
        return budget_result.status();
    }
    auto *budget = *budget_result.get_if();

    M11DecisionContext context;
    context.context_id = context_id;
    context.decision_window_id = "window:" + context_id;
    context.economy = economy;
    context.seat = std::move(seat);
    context.decision_group = std::move(decision_group);
    context.boundary = boundary;
    context.expires_at = expires_at;
    context.administrative_window = budget->window_marker;
    context.administrative_remaining = budget->remaining;
    context.administrative_reserved = budget->reserved;
    context.administrative_capacity = budget->capacity;
    context.emergency = emergency;
    context.emergency_trigger = std::move(emergency_trigger);
    context.elapsed_ticks = elapsed_ticks;

    for (const auto &lever : m11_policy_levers()) {
        if (lever.owner_role != context.seat ||
            (!emergency &&
             lever.decision_group != context.decision_group) ||
            (emergency && !lever.emergency)) {
            continue;
        }
        auto current =
            world_policy_value(world, economy, lever.name);
        if (!current.ok()) {
            return current.status();
        }
        auto *version =
            mutable_policy_version(economy, lever.name);
        if (version == nullptr) {
            return Status(ErrorCode::internal_error,
                          "M11 policy version table is incomplete");
        }
        const auto lag =
            emergency &&
                    lever.emergency_implementation_lag.has_value()
                ? *lever.emergency_implementation_lag
                : lever.implementation_lag;
        auto earliest = Tick(boundary.value() + lag);
        std::string reason;
        for (const auto capability :
             split_contract_list(lever.required_capabilities)) {
            if (!m11_world_capability(world, economy, capability)) {
                reason = "missing_capability:" +
                         std::string(capability);
                break;
            }
        }
        if (reason.empty() &&
            active_pending_for_lever(
                pending_, economy, lever.name) != nullptr) {
            reason = "pending_conflict";
        }
        if (version->last_effective.has_value()) {
            const auto hold_until =
                Tick(version->last_effective->value() +
                     lever.minimum_hold_ticks);
            if (earliest < hold_until) {
                earliest = hold_until;
                if (reason.empty()) {
                    reason = "minimum_hold";
                }
            }
        }
        for (const auto prerequisite :
             split_contract_list(lever.enabled_if)) {
            auto value =
                world_policy_value(world, economy, prerequisite);
            if (!value.ok()) {
                return value.status();
            }
            if (reason.empty() &&
                !policy_truthy(*value.get_if())) {
                reason = "disabled_prerequisite:" +
                         std::string(prerequisite);
            }
            auto prerequisite_version =
                policy_version(economy, prerequisite);
            if (!prerequisite_version.ok()) {
                return prerequisite_version.status();
            }
            context.policy_versions.push_back(
                {economy, std::string(prerequisite),
                 *prerequisite_version.get_if(), std::nullopt});
        }
        const auto minimum_admin =
            cost_spec_.proposal_administrative_overhead +
            lever.administrative_weight;
        if (reason.empty() &&
            budget->remaining + kBudgetTolerance < minimum_admin) {
            reason = "admin_capacity_exceeded";
        }
        context.permitted_actions.push_back({
            std::string(lever.name),
            *current.get_if(),
            reason.empty(),
            std::move(reason),
            version->version,
            earliest,
        });
        context.policy_versions.push_back(*version);
    }
    std::sort(context.permitted_actions.begin(),
              context.permitted_actions.end(),
              [](const M11PermittedAction &left,
                 const M11PermittedAction &right) {
                  return left.lever < right.lever;
              });
    std::sort(context.policy_versions.begin(),
              context.policy_versions.end(), policy_version_less);
    context.policy_versions.erase(
        std::unique(
            context.policy_versions.begin(),
            context.policy_versions.end(),
            [](const M11PolicyVersion &left,
               const M11PolicyVersion &right) {
                return left.economy == right.economy &&
                       left.lever == right.lever;
            }),
        context.policy_versions.end());
    contexts_.push_back(context);
    std::sort(contexts_.begin(), contexts_.end(), context_less);
    return context;
}

M11PolicyDecision M11PolicyCoordinator::make_decision(
    const M11PolicyProposal &proposal, M11DecisionStatus status,
    std::string reason, std::optional<Tick> accepted_at,
    std::optional<Tick> effective_at, double administrative_cost,
    double adjustment_cost) {
    std::ostringstream identifier;
    identifier << "decision:" << std::setw(12) << std::setfill('0')
               << next_decision_sequence_;
    M11PolicyDecision result{
        identifier.str(),
        proposal.proposal_id,
        status,
        std::move(reason),
        accepted_at,
        effective_at,
        next_decision_sequence_,
        administrative_cost,
        adjustment_cost,
    };
    ++next_decision_sequence_;
    return result;
}

Result<M11PolicyDecision> M11PolicyCoordinator::reject(
    const M11PolicyProposal &proposal, std::string reason,
    core::StateDigest request_hash) {
    if (decisions_.size() >= kM11MaximumDecisionHistory ||
        idempotency_.size() >= kM11MaximumIdempotencyRecords) {
        return Status(ErrorCode::out_of_range,
                      "M11 decision receipt capacity was reached");
    }
    auto decision = make_decision(
        proposal, M11DecisionStatus::rejected, std::move(reason),
        std::nullopt, std::nullopt);
    decisions_.push_back(decision);
    std::sort(decisions_.begin(), decisions_.end(), decision_less);
    idempotency_.push_back(
        {proposal.idempotency_key, request_hash,
         decision.decision_id});
    std::sort(idempotency_.begin(), idempotency_.end(),
              [](const M11IdempotencyRecord &left,
                 const M11IdempotencyRecord &right) {
                  return left.key < right.key;
              });
    return decision;
}

Result<M11PolicyDecision> M11PolicyCoordinator::submit(
    const simulation::M9World &world,
    const M11DecisionScheduler &scheduler, Tick boundary,
    M11PolicyProposal proposal, std::string_view actor,
    M11EventStream &events) {
    if (boundary != world.tick() || !valid_actor(actor) ||
        !valid_identifier(proposal.proposal_id) ||
        !valid_identifier(proposal.idempotency_key) ||
        !valid_identifier(proposal.context_id) ||
        proposal.reason.size() > kMaximumReasonBytes ||
        proposal.reason.find('\0') != std::string::npos ||
        proposal.actions.size() > kM11MaximumProposalActions ||
        proposal.actions.empty() ||
        (proposal.supersedes_proposal_id.has_value() &&
         !valid_identifier(*proposal.supersedes_proposal_id))) {
        return Status(ErrorCode::invalid_argument,
                      "M11 policy proposal is invalid");
    }
    std::sort(
        proposal.actions.begin(), proposal.actions.end(),
        [](const NativePolicyAction &left,
           const NativePolicyAction &right) {
            return std::pair{left.economy.value(), left.lever} <
                   std::pair{right.economy.value(), right.lever};
        });
    if (std::adjacent_find(
            proposal.actions.begin(), proposal.actions.end(),
            [](const NativePolicyAction &left,
               const NativePolicyAction &right) {
                return left.economy == right.economy &&
                       left.lever == right.lever;
            }) != proposal.actions.end()) {
        return Status(ErrorCode::invalid_argument,
                      "M11 proposal actions must be unique");
    }
    std::sort(proposal.based_on_policy_versions.begin(),
              proposal.based_on_policy_versions.end(),
              [](const M11ProposalVersion &left,
                 const M11ProposalVersion &right) {
                  return left.lever < right.lever;
              });
    if (std::adjacent_find(
            proposal.based_on_policy_versions.begin(),
            proposal.based_on_policy_versions.end(),
            [](const M11ProposalVersion &left,
               const M11ProposalVersion &right) {
                return left.lever == right.lever;
            }) != proposal.based_on_policy_versions.end()) {
        return Status(ErrorCode::invalid_argument,
                      "M11 proposal versions must be unique");
    }
    const auto request_hash = proposal_hash(proposal);
    const auto receipt =
        std::lower_bound(
            idempotency_.begin(), idempotency_.end(),
            proposal.idempotency_key,
            [](const M11IdempotencyRecord &entry,
               std::string_view key) { return entry.key < key; });
    if (receipt != idempotency_.end() &&
        receipt->key == proposal.idempotency_key) {
        if (receipt->request_hash != request_hash) {
            return Status(ErrorCode::already_exists,
                          "M11 idempotency key payload differs");
        }
        const auto *decision =
            find_decision(receipt->decision_id);
        return decision == nullptr
                   ? Result<M11PolicyDecision>(
                         Status(ErrorCode::internal_error,
                                "M11 decision receipt is incomplete"))
                   : Result<M11PolicyDecision>(*decision);
    }

    M11PolicyCoordinator staged = *this;
    auto staged_events = events;
    auto event = staged_events.append(
        boundary, "proposal_submitted", proposal.idempotency_key,
        std::string(actor),
        event_payload("proposal_id", proposal.proposal_id),
        M11EventVisibility::privileged_audit);
    if (!event.ok()) {
        return event.status();
    }
    const auto reject_with = [&](std::string reason)
        -> Result<M11PolicyDecision> {
        auto decision =
            staged.reject(proposal, std::move(reason), request_hash);
        if (!decision.ok()) {
            return decision.status();
        }
        auto rejected = staged_events.append(
            boundary, "decision_rejected", proposal.idempotency_key,
            "coordinator",
            event_payload("decision_id",
                          decision.get_if()->decision_id,
                          decision.get_if()->reason_code),
            M11EventVisibility::institution);
        if (!rejected.ok()) {
            return rejected.status();
        }
        *this = std::move(staged);
        events = std::move(staged_events);
        return *decision.get_if();
    };

    auto *context = staged.mutable_context(proposal.context_id);
    if (context == nullptr) {
        return reject_with("unknown_context");
    }
    if (boundary > context->expires_at) {
        return reject_with("context_expired");
    }
    if (std::any_of(
            staged.decisions_.begin(), staged.decisions_.end(),
            [&](const M11PolicyDecision &decision) {
                return decision.proposal_id == proposal.proposal_id;
            })) {
        return reject_with("duplicate_proposal_id");
    }
    M11PendingDecision *superseded = nullptr;
    if (context->answered_by_proposal.has_value()) {
        if (!proposal.supersedes_proposal_id.has_value() ||
            *proposal.supersedes_proposal_id !=
                *context->answered_by_proposal) {
            return reject_with("context_already_answered");
        }
    }
    if (proposal.supersedes_proposal_id.has_value()) {
        const auto *found = pending_for_proposal(
            staged.pending_, *proposal.supersedes_proposal_id);
        if (found == nullptr) {
            return reject_with("proposal_not_supersedable");
        }
        superseded = staged.mutable_pending(
            found->decision.decision_id);
        if (superseded == nullptr ||
            superseded->context.economy != context->economy ||
            superseded->context.seat != context->seat) {
            return reject_with("supersede_scope_mismatch");
        }
        if (!same_touched_levers(proposal,
                                 superseded->proposal)) {
            return reject_with("supersede_lever_mismatch");
        }
    }

    for (const auto &action : proposal.actions) {
        if (action.economy != context->economy) {
            return reject_with("proposal_economy_mismatch");
        }
        const auto *lever = find_m11_policy_lever(action.lever);
        const auto *permitted =
            permitted_action(context->permitted_actions,
                             action.lever);
        if (lever == nullptr || permitted == nullptr ||
            lever->owner_role != context->seat ||
            (!context->emergency &&
             lever->decision_group != context->decision_group) ||
            (context->emergency && !lever->emergency)) {
            return reject_with("unauthorized_lever");
        }
        auto value_status = validate_m11_policy_value(
            *lever, action.value, action.economy,
            world.economy_count());
        if (!value_status.ok()) {
            return reject_with("registry_validation");
        }
        for (const auto capability :
             split_contract_list(lever->required_capabilities)) {
            if (!m11_world_capability(
                    world, context->economy, capability)) {
                return reject_with("missing_capability");
            }
        }
        const auto expected =
            proposal_version(
                proposal.based_on_policy_versions,
                action.lever);
        const auto current =
            staged.policy_version(context->economy,
                                  action.lever);
        if (expected == nullptr || !current.ok() ||
            expected->version != *current.get_if()) {
            return reject_with("stale_policy_version");
        }
        for (const auto prerequisite :
             split_contract_list(lever->enabled_if)) {
            const auto *expected_prerequisite =
                proposal_version(
                    proposal.based_on_policy_versions,
                    prerequisite);
            const auto current_prerequisite =
                staged.policy_version(context->economy,
                                      prerequisite);
            if (expected_prerequisite == nullptr ||
                !current_prerequisite.ok() ||
                expected_prerequisite->version !=
                    *current_prerequisite.get_if()) {
                return reject_with(
                    "stale_prerequisite_version");
            }
        }
        const auto excluded =
            superseded == nullptr
                ? std::string_view{}
                : std::string_view(
                      superseded->decision.decision_id);
        if (active_pending_for_lever(
                staged.pending_, context->economy,
                action.lever, excluded) != nullptr) {
            return reject_with("pending_conflict");
        }
    }

    std::uint32_t maximum_lag = 0U;
    for (const auto &action : proposal.actions) {
        const auto *lever =
            find_m11_policy_lever(action.lever);
        const auto lag =
            context->emergency &&
                    lever->emergency_implementation_lag.has_value()
                ? *lever->emergency_implementation_lag
                : lever->implementation_lag;
        maximum_lag = std::max(maximum_lag, lag);
    }
    const auto effective =
        Tick(boundary.value() + maximum_lag);
    auto projected = project_timeline_before(
        world, staged.pending_, effective,
        superseded == nullptr
            ? std::string_view{}
            : std::string_view(superseded->decision.decision_id));
    if (!projected.ok()) {
        return reject_with("projected_timeline_conflict");
    }
    auto projected_batch = project_m11_policy_actions(
        *projected.get_if(), proposal.actions);
    if (!projected_batch.ok()) {
        return reject_with("registry_validation");
    }
    auto prerequisites = validate_enabled_prerequisites(
        *projected_batch.get_if(), proposal.actions);
    if (!prerequisites.ok()) {
        return reject_with("disabled_prerequisite");
    }
    std::vector<M11PolicyChange> changes;
    changes.reserve(proposal.actions.size());
    for (const auto &action : proposal.actions) {
        const auto *lever =
            find_m11_policy_lever(action.lever);
        auto before = world_policy_value(
            *projected.get_if(), action.economy,
            action.lever);
        auto after = batch_policy_value(
            *projected_batch.get_if(), action.economy,
            action.lever);
        if (!before.ok() || !after.ok()) {
            return reject_with("registry_validation");
        }
        auto distance = m11_policy_numeric_distance(
            *lever, *before.get_if(), *after.get_if());
        if (!distance.ok()) {
            return reject_with("registry_validation");
        }
        if (lever->maximum_step.has_value() &&
            lever->control_scale.has_value() &&
            *distance.get_if() * *lever->control_scale >
                *lever->maximum_step + 1.0e-15) {
            return reject_with("maximum_step");
        }
        auto *version = staged.mutable_policy_version(
            action.economy, action.lever);
        if (version == nullptr) {
            return Status(ErrorCode::internal_error,
                          "M11 policy version table is incomplete");
        }
        if (!m11_policy_values_equal(*before.get_if(),
                                     *after.get_if()) &&
            version->last_effective.has_value() &&
            effective.value() <
                version->last_effective->value() +
                    lever->minimum_hold_ticks) {
            return reject_with("minimum_hold");
        }
        changes.push_back(
            {lever, *before.get_if(), *after.get_if()});
    }
    const auto changed =
        std::any_of(changes.begin(), changes.end(),
                    [](const M11PolicyChange &change) {
                        return !m11_policy_values_equal(
                            change.old_value, change.new_value);
                    });
    if (staged.decisions_.size() >=
            kM11MaximumDecisionHistory ||
        staged.idempotency_.size() >=
            kM11MaximumIdempotencyRecords) {
        return Status(ErrorCode::out_of_range,
                      "M11 decision receipt capacity was reached");
    }
    if (!changed) {
        if (superseded != nullptr) {
            superseded->decision.status =
                M11DecisionStatus::superseded;
            superseded->decision.reason_code = "superseded";
            auto *history = staged.mutable_decision(
                superseded->decision.decision_id);
            if (history != nullptr) {
                *history = superseded->decision;
            }
            staged.refund(
                *superseded,
                staged.cost_spec_.refund_on_supersede);
        }
        auto decision = staged.make_decision(
            proposal, M11DecisionStatus::accepted_noop,
            "no_change", boundary, std::nullopt);
        staged.decisions_.push_back(decision);
        std::sort(staged.decisions_.begin(),
                  staged.decisions_.end(), decision_less);
        staged.idempotency_.push_back(
            {proposal.idempotency_key, request_hash,
             decision.decision_id});
        std::sort(staged.idempotency_.begin(),
                  staged.idempotency_.end(),
                  [](const M11IdempotencyRecord &left,
                     const M11IdempotencyRecord &right) {
                      return left.key < right.key;
                  });
        context = staged.mutable_context(proposal.context_id);
        context->answered_by_proposal = proposal.proposal_id;
        auto accepted = staged_events.append(
            boundary, "decision_accepted_noop",
            proposal.idempotency_key, "coordinator",
            event_payload("decision_id", decision.decision_id),
            M11EventVisibility::institution);
        if (!accepted.ok()) {
            return accepted.status();
        }
        *this = std::move(staged);
        events = std::move(staged_events);
        return decision;
    }

    auto administrative_cost =
        m11_administrative_cost(staged.cost_spec_, changes);
    auto adjustment_cost =
        m11_adjustment_cost(staged.cost_spec_, changes,
                            context->emergency);
    if (!administrative_cost.ok() || !adjustment_cost.ok()) {
        return reject_with("cost_validation");
    }
    const auto budget_group =
        std::string_view(context->decision_group);
    auto budget_result = staged.ensure_budget(
        scheduler, context->economy, context->seat,
        budget_group, boundary);
    if (!budget_result.ok()) {
        return budget_result.status();
    }
    auto *budget = *budget_result.get_if();
    double supersede_refund = 0.0;
    if (superseded != nullptr &&
        superseded->context.administrative_window ==
            budget->window_marker) {
        supersede_refund =
            superseded->decision.reserved_administrative_cost *
            staged.cost_spec_.refund_on_supersede;
    }
    if (*administrative_cost.get_if() >
        budget->remaining + supersede_refund +
            kBudgetTolerance) {
        return reject_with("admin_capacity_exceeded");
    }
    if (superseded != nullptr) {
        superseded->decision.status =
            M11DecisionStatus::superseded;
        superseded->decision.reason_code = "superseded";
        auto *history = staged.mutable_decision(
            superseded->decision.decision_id);
        if (history != nullptr) {
            *history = superseded->decision;
        }
        staged.refund(
            *superseded,
            staged.cost_spec_.refund_on_supersede);
        auto superseded_event = staged_events.append(
            boundary, "decision_superseded",
            proposal.idempotency_key, "coordinator",
            event_payload("decision_id",
                          superseded->decision.decision_id),
            M11EventVisibility::institution);
        if (!superseded_event.ok()) {
            return superseded_event.status();
        }
        budget = staged.mutable_budget(
            context->economy, context->seat, budget_group);
    }
    budget->remaining -= *administrative_cost.get_if();
    budget->reserved += *administrative_cost.get_if();
    if (staged.pending_.size() >=
        kM11MaximumPendingDecisions) {
        return Status(ErrorCode::out_of_range,
                      "M11 pending decision capacity was reached");
    }
    auto decision = staged.make_decision(
        proposal, M11DecisionStatus::accepted_pending,
        "accepted", boundary, effective,
        *administrative_cost.get_if(),
        *adjustment_cost.get_if());
    staged.pending_.push_back(
        {decision, proposal, *context});
    std::sort(staged.pending_.begin(), staged.pending_.end(),
              pending_less);
    staged.decisions_.push_back(decision);
    std::sort(staged.decisions_.begin(), staged.decisions_.end(),
              decision_less);
    staged.idempotency_.push_back(
        {proposal.idempotency_key, request_hash,
         decision.decision_id});
    std::sort(staged.idempotency_.begin(),
              staged.idempotency_.end(),
              [](const M11IdempotencyRecord &left,
                 const M11IdempotencyRecord &right) {
                  return left.key < right.key;
              });
    context = staged.mutable_context(proposal.context_id);
    context->answered_by_proposal = proposal.proposal_id;
    context->administrative_remaining = budget->remaining;
    context->administrative_reserved = budget->reserved;
    auto accepted = staged_events.append(
        boundary, "decision_accepted",
        proposal.idempotency_key, "coordinator",
        event_payload("decision_id", decision.decision_id),
        M11EventVisibility::institution);
    if (!accepted.ok()) {
        return accepted.status();
    }
    *this = std::move(staged);
    events = std::move(staged_events);
    return decision;
}

void M11PolicyCoordinator::refund(
    M11PendingDecision &pending, double fraction) noexcept {
    const auto group =
        std::string_view(pending.context.decision_group);
    auto *budget = mutable_budget(
        pending.context.economy, pending.context.seat, group);
    if (budget == nullptr ||
        budget->window_marker !=
            pending.context.administrative_window) {
        return;
    }
    const auto reserved =
        pending.decision.reserved_administrative_cost;
    budget->remaining += reserved * fraction;
    budget->remaining =
        std::min(budget->remaining, budget->capacity);
    budget->reserved =
        std::max(0.0, budget->reserved - reserved);
}

Result<M11PolicyDecision> M11PolicyCoordinator::cancel(
    Tick boundary, std::string_view decision_id,
    std::string_view operation_id, std::string_view actor,
    M11EventStream &events) {
    if (!valid_identifier(decision_id) ||
        !valid_identifier(operation_id) || !valid_actor(actor)) {
        return Status(ErrorCode::invalid_argument,
                      "M11 cancellation request is invalid");
    }
    const auto *active = find_pending(decision_id);
    if (active == nullptr ||
        active->decision.status !=
            M11DecisionStatus::accepted_pending) {
        return Status(ErrorCode::invalid_transaction_state,
                      "M11 decision is not active pending");
    }
    M11PolicyCoordinator staged = *this;
    auto staged_events = events;
    auto input = staged_events.append(
        boundary, "pending_cancel_requested",
        std::string(operation_id), std::string(actor),
        event_payload("decision_id", decision_id),
        M11EventVisibility::privileged_audit);
    if (!input.ok()) {
        return input.status();
    }
    auto *pending = staged.mutable_pending(decision_id);
    pending->decision.status = M11DecisionStatus::cancelled;
    pending->decision.reason_code = "cancelled";
    auto *history = staged.mutable_decision(decision_id);
    if (history == nullptr) {
        return Status(ErrorCode::internal_error,
                      "M11 decision history is incomplete");
    }
    *history = pending->decision;
    staged.refund(*pending, staged.cost_spec_.refund_on_cancel);
    auto derived = staged_events.append(
        boundary, "decision_cancelled",
        std::string(operation_id), "coordinator",
        event_payload("decision_id", decision_id),
        M11EventVisibility::institution);
    if (!derived.ok()) {
        return derived.status();
    }
    auto result = pending->decision;
    *this = std::move(staged);
    events = std::move(staged_events);
    return result;
}

Result<M11DuePlan> M11PolicyCoordinator::prepare_due(
    const simulation::M9World &world, Tick boundary) const {
    if (boundary != world.tick()) {
        return Status(ErrorCode::stale_handle,
                      "M11 due boundary is stale");
    }
    std::vector<const M11PendingDecision *> due;
    std::vector<std::string> immediately_failed;
    for (const auto &item : pending_) {
        if (item.decision.status !=
                M11DecisionStatus::accepted_pending ||
            !item.decision.effective_at.has_value() ||
            *item.decision.effective_at != boundary) {
            continue;
        }
        bool valid = true;
        for (const auto &action : item.proposal.actions) {
            const auto *lever =
                find_m11_policy_lever(action.lever);
            const auto *expected =
                proposal_version(
                    item.proposal.based_on_policy_versions,
                    action.lever);
            auto current =
                policy_version(action.economy, action.lever);
            const auto *version =
                find_policy_version(action.economy, action.lever);
            if (lever == nullptr || expected == nullptr ||
                !current.ok() ||
                expected->version != *current.get_if() ||
                (version != nullptr &&
                 version->last_effective.has_value() &&
                 boundary.value() <
                     version->last_effective->value() +
                         lever->minimum_hold_ticks)) {
                valid = false;
                break;
            }
            for (const auto prerequisite :
                 split_contract_list(lever->enabled_if)) {
                const auto *expected_prerequisite =
                    proposal_version(
                        item.proposal.based_on_policy_versions,
                        prerequisite);
                auto current_prerequisite =
                    policy_version(action.economy, prerequisite);
                if (expected_prerequisite == nullptr ||
                    !current_prerequisite.ok() ||
                    expected_prerequisite->version !=
                        *current_prerequisite.get_if()) {
                    valid = false;
                    break;
                }
            }
            if (!valid) {
                break;
            }
        }
        if (valid) {
            due.push_back(&item);
        } else {
            immediately_failed.push_back(
                item.decision.decision_id);
        }
    }
    std::sort(
        due.begin(), due.end(),
        [](const M11PendingDecision *left,
           const M11PendingDecision *right) {
            return std::pair{left->decision.accepted_sequence,
                             left->decision.decision_id} <
                   std::pair{right->decision.accepted_sequence,
                             right->decision.decision_id};
        });

    std::vector<const M11PendingDecision *> safe;
    std::string exclusion_reason;
    if (!due.empty()) {
        auto full = validate_candidate_set(world, due);
        if (full.ok()) {
            safe = due;
        } else {
            exclusion_reason = "joint_world_conflict";
            const auto count = due.size();
            std::size_t attempts = 0U;
            for (std::size_t size = count - 1U;
                 size > 0U && safe.empty(); --size) {
                std::vector<std::vector<const M11PendingDecision *>>
                    valid_subsets;
                if (count < 63U) {
                    const auto limit = std::uint64_t{1U} << count;
                    for (std::uint64_t mask = 1U; mask < limit;
                         ++mask) {
                        if (static_cast<std::size_t>(
                                std::popcount(mask)) != size) {
                            continue;
                        }
                        ++attempts;
                        if (attempts >
                            kMaximumConservativeAttempts) {
                            break;
                        }
                        std::vector<const M11PendingDecision *> subset;
                        for (std::size_t index = 0U;
                             index < count; ++index) {
                            if ((mask &
                                 (std::uint64_t{1U} << index)) != 0U) {
                                subset.push_back(due[index]);
                            }
                        }
                        if (validate_candidate_set(world, subset).ok()) {
                            valid_subsets.push_back(std::move(subset));
                        }
                    }
                }
                if (attempts >
                        kMaximumConservativeAttempts ||
                    valid_subsets.empty()) {
                    continue;
                }
                safe = valid_subsets.front();
                for (std::size_t index = 1U;
                     index < valid_subsets.size(); ++index) {
                    safe.erase(
                        std::remove_if(
                            safe.begin(), safe.end(),
                            [&](const M11PendingDecision *candidate) {
                                return std::find(
                                           valid_subsets[index].begin(),
                                           valid_subsets[index].end(),
                                           candidate) ==
                                       valid_subsets[index].end();
                            }),
                        safe.end());
                }
                if (!safe.empty() &&
                    !validate_candidate_set(world, safe).ok()) {
                    safe.clear();
                }
            }
        }
    }
    auto actions = flatten_actions(safe);
    auto batch = project_m11_policy_actions(world, actions);
    if (!batch.ok()) {
        return batch.status();
    }
    M11DuePlan plan;
    plan.boundary = boundary;
    plan.policy_batch = std::move(*batch.get_if());
    plan.failed_decision_ids = std::move(immediately_failed);
    plan.exclusion_reason = std::move(exclusion_reason);
    for (const auto *item : safe) {
        plan.effective_decision_ids.push_back(
            item->decision.decision_id);
    }
    for (const auto *item : due) {
        if (std::find(safe.begin(), safe.end(), item) == safe.end()) {
            plan.failed_decision_ids.push_back(
                item->decision.decision_id);
        }
    }
    std::sort(plan.failed_decision_ids.begin(),
              plan.failed_decision_ids.end());
    plan.effective_changes =
        changed_actions(world, plan.policy_batch);
    return plan;
}

Status M11PolicyCoordinator::commit_due(
    const M11DuePlan &plan, M11EventStream &events) {
    M11PolicyCoordinator staged = *this;
    auto staged_events = events;
    for (const auto &decision_id : plan.failed_decision_ids) {
        auto *pending = staged.mutable_pending(decision_id);
        auto *history = staged.mutable_decision(decision_id);
        if (pending == nullptr || history == nullptr ||
            pending->decision.status !=
                M11DecisionStatus::accepted_pending) {
            return Status(ErrorCode::stale_handle,
                          "M11 due failure decision is stale");
        }
        pending->decision.status =
            M11DecisionStatus::failed_at_execution;
        pending->decision.reason_code =
            plan.exclusion_reason.empty()
                ? "stale_at_execution"
                : plan.exclusion_reason;
        *history = pending->decision;
        staged.refund(
            *pending,
            staged.cost_spec_.refund_on_failed_execution);
        auto event = staged_events.append(
            plan.boundary, "decision_failed_at_execution",
            decision_id, "policy_executor",
            event_payload("decision_id", decision_id,
                          pending->decision.reason_code),
            M11EventVisibility::institution);
        if (!event.ok()) {
            return event.status();
        }
    }
    for (const auto &decision_id :
         plan.effective_decision_ids) {
        auto *pending = staged.mutable_pending(decision_id);
        auto *history = staged.mutable_decision(decision_id);
        if (pending == nullptr || history == nullptr ||
            pending->decision.status !=
                M11DecisionStatus::accepted_pending) {
            return Status(ErrorCode::stale_handle,
                          "M11 due effective decision is stale");
        }
        pending->decision.status = M11DecisionStatus::effective;
        pending->decision.reason_code = "effective";
        *history = pending->decision;
        const auto group =
            std::string_view(pending->context.decision_group);
        auto *budget = staged.mutable_budget(
            pending->context.economy,
            pending->context.seat, group);
        if (budget != nullptr &&
            budget->window_marker ==
                pending->context.administrative_window) {
            budget->reserved = std::max(
                0.0,
                budget->reserved -
                    pending->decision
                        .reserved_administrative_cost);
        }
    }
    for (const auto &change : plan.effective_changes) {
        auto *version = staged.mutable_policy_version(
            change.economy, change.lever);
        if (version == nullptr) {
            return Status(ErrorCode::internal_error,
                          "M11 effective policy version is missing");
        }
        ++version->version;
        version->last_effective = plan.boundary;
    }
    if (!plan.effective_decision_ids.empty()) {
        auto event = staged_events.append(
            plan.boundary, "policy_transaction_effective",
            "boundary-policy-commit", "policy_executor",
            event_payload(
                "decision_count",
                std::to_string(
                    plan.effective_decision_ids.size())),
            M11EventVisibility::public_record);
        if (!event.ok()) {
            return event.status();
        }
    }
    *this = std::move(staged);
    events = std::move(staged_events);
    return Status::success();
}

Status M11PolicyCoordinator::fail_due(
    const M11DuePlan &plan, std::string_view reason,
    M11EventStream &events) {
    if (reason.empty() || reason.size() > kMaximumReasonBytes) {
        return Status(ErrorCode::invalid_argument,
                      "M11 execution failure reason is invalid");
    }
    auto failed = plan;
    failed.failed_decision_ids.insert(
        failed.failed_decision_ids.end(),
        failed.effective_decision_ids.begin(),
        failed.effective_decision_ids.end());
    failed.effective_decision_ids.clear();
    failed.effective_changes.clear();
    failed.exclusion_reason = std::string(reason);
    std::sort(failed.failed_decision_ids.begin(),
              failed.failed_decision_ids.end());
    failed.failed_decision_ids.erase(
        std::unique(failed.failed_decision_ids.begin(),
                    failed.failed_decision_ids.end()),
        failed.failed_decision_ids.end());
    return commit_due(failed, events);
}

Status M11PolicyCoordinator::restore(
    const simulation::M9World &world,
    std::vector<M11PolicyVersion> policy_versions,
    std::vector<M11DecisionContext> contexts,
    std::vector<M11PendingDecision> pending,
    std::vector<M11PolicyDecision> decisions,
    std::vector<M11AdministrativeBudget> budgets,
    std::vector<M11IdempotencyRecord> idempotency,
    std::uint64_t next_decision_sequence) {
    const auto expected_versions =
        world.economy_count() * m11_policy_levers().size();
    if (policy_versions.size() != expected_versions ||
        contexts.size() > kM11MaximumDecisionContexts ||
        pending.size() > kM11MaximumPendingDecisions ||
        decisions.size() > kM11MaximumDecisionHistory ||
        idempotency.size() > kM11MaximumIdempotencyRecords) {
        return Status(ErrorCode::corrupt_input,
                      "M11 coordinator checkpoint size is invalid");
    }
    std::sort(policy_versions.begin(), policy_versions.end(),
              policy_version_less);
    for (std::size_t economy = 0U;
         economy < world.economy_count(); ++economy) {
        for (std::size_t lever = 0U;
             lever < m11_policy_levers().size(); ++lever) {
            const auto index =
                economy * m11_policy_levers().size() + lever;
            if (policy_versions[index].economy.value() != economy ||
                policy_versions[index].lever !=
                    m11_policy_levers()[lever].name) {
                return Status(ErrorCode::corrupt_input,
                              "M11 policy version table is corrupt");
            }
        }
    }
    std::sort(contexts.begin(), contexts.end(), context_less);
    std::sort(pending.begin(), pending.end(), pending_less);
    std::sort(decisions.begin(), decisions.end(), decision_less);
    std::sort(budgets.begin(), budgets.end(), budget_less);
    std::sort(idempotency.begin(), idempotency.end(),
              [](const M11IdempotencyRecord &left,
                 const M11IdempotencyRecord &right) {
                  return left.key < right.key;
              });
    if (std::adjacent_find(
            contexts.begin(), contexts.end(),
            [](const M11DecisionContext &left,
               const M11DecisionContext &right) {
                return left.context_id == right.context_id;
            }) != contexts.end() ||
        std::adjacent_find(
            pending.begin(), pending.end(),
            [](const M11PendingDecision &left,
               const M11PendingDecision &right) {
                return left.decision.decision_id ==
                       right.decision.decision_id;
            }) != pending.end() ||
        std::adjacent_find(
            decisions.begin(), decisions.end(),
            [](const M11PolicyDecision &left,
               const M11PolicyDecision &right) {
                return left.decision_id == right.decision_id;
            }) != decisions.end() ||
        std::adjacent_find(
            budgets.begin(), budgets.end(),
            [](const M11AdministrativeBudget &left,
               const M11AdministrativeBudget &right) {
                return left.economy == right.economy &&
                       left.seat == right.seat &&
                       left.decision_group ==
                           right.decision_group;
            }) != budgets.end() ||
        std::adjacent_find(
            idempotency.begin(), idempotency.end(),
            [](const M11IdempotencyRecord &left,
               const M11IdempotencyRecord &right) {
                return left.key == right.key;
            }) != idempotency.end()) {
        return Status(ErrorCode::corrupt_input,
                      "M11 coordinator keys are not unique");
    }
    for (const auto &budget : budgets) {
        if (!m11_valid_seat(budget.seat) ||
            !std::isfinite(budget.remaining) ||
            !std::isfinite(budget.reserved) ||
            !std::isfinite(budget.capacity) ||
            budget.remaining < 0.0 || budget.reserved < 0.0 ||
            budget.capacity < 0.0 ||
            budget.remaining + budget.reserved >
                budget.capacity + kBudgetTolerance) {
            return Status(ErrorCode::corrupt_input,
                          "M11 administrative budget is corrupt");
        }
    }
    for (const auto &decision : decisions) {
        if (decision.accepted_sequence >= next_decision_sequence) {
            return Status(ErrorCode::corrupt_input,
                          "M11 decision sequence is corrupt");
        }
    }
    policy_versions_ = std::move(policy_versions);
    contexts_ = std::move(contexts);
    pending_ = std::move(pending);
    decisions_ = std::move(decisions);
    budgets_ = std::move(budgets);
    idempotency_ = std::move(idempotency);
    next_decision_sequence_ = next_decision_sequence;
    return Status::success();
}

} // namespace macro_sim::control
