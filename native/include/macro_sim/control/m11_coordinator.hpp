#ifndef MACRO_SIM_CONTROL_M11_COORDINATOR_HPP
#define MACRO_SIM_CONTROL_M11_COORDINATOR_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/control/m11_kernel.hpp"
#include "macro_sim/control/m11_policy.hpp"
#include "macro_sim/control/m11_release.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::control {

inline constexpr std::size_t kM11MaximumProposalActions = 102U;
inline constexpr std::size_t kM11MaximumPendingDecisions = 4096U;
inline constexpr std::size_t kM11MaximumDecisionContexts = 8192U;
inline constexpr std::size_t kM11MaximumDecisionHistory = 1U << 20U;
inline constexpr std::size_t kM11MaximumIdempotencyRecords = 4096U;

enum class M11DecisionStatus : std::uint8_t {
    rejected = 0,
    accepted_noop = 1,
    accepted_pending = 2,
    effective = 3,
    cancelled = 4,
    superseded = 5,
    failed_at_execution = 6,
};

struct M11PolicyVersion final {
    EconomyId economy{};
    std::string lever;
    std::uint64_t version{0U};
    std::optional<Tick> last_effective{};

    bool operator==(const M11PolicyVersion &) const = default;
};

struct M11PermittedAction final {
    std::string lever;
    PolicyValue current_value{};
    bool allowed{false};
    std::string reason_code;
    std::uint64_t policy_version{0U};
    Tick earliest_effective{};

    bool operator==(const M11PermittedAction &) const = default;
};

struct M11DecisionContext final {
    std::string context_id;
    std::string decision_window_id;
    EconomyId economy{};
    std::string seat;
    std::string decision_group;
    Tick boundary{};
    Tick expires_at{};
    Tick administrative_window{};
    std::vector<M11ReleasedObservation> observation;
    std::vector<M11PermittedAction> permitted_actions;
    std::vector<M11PolicyVersion> policy_versions;
    double administrative_remaining{0.0};
    double administrative_reserved{0.0};
    double administrative_capacity{0.0};
    bool emergency{false};
    std::string emergency_trigger;
    std::uint64_t elapsed_ticks{0U};
    std::optional<std::string> answered_by_proposal{};

    bool operator==(const M11DecisionContext &) const = default;
};

struct M11ProposalVersion final {
    std::string lever;
    std::uint64_t version{0U};

    bool operator==(const M11ProposalVersion &) const = default;
};

struct M11PolicyProposal final {
    std::string proposal_id;
    std::string idempotency_key;
    std::string context_id;
    std::vector<NativePolicyAction> actions;
    std::vector<M11ProposalVersion> based_on_policy_versions;
    std::string reason;
    std::optional<std::string> supersedes_proposal_id{};

    bool operator==(const M11PolicyProposal &) const = default;
};

struct M11PolicyDecision final {
    std::string decision_id;
    std::string proposal_id;
    M11DecisionStatus status{M11DecisionStatus::rejected};
    std::string reason_code;
    std::optional<Tick> accepted_at{};
    std::optional<Tick> effective_at{};
    std::uint64_t accepted_sequence{0U};
    double reserved_administrative_cost{0.0};
    double adjustment_cost{0.0};

    bool operator==(const M11PolicyDecision &) const = default;
};

struct M11PendingDecision final {
    M11PolicyDecision decision;
    M11PolicyProposal proposal;
    M11DecisionContext context;

    bool operator==(const M11PendingDecision &) const = default;
};

struct M11AdministrativeBudget final {
    EconomyId economy{};
    std::string seat;
    std::string decision_group;
    Tick window_marker{};
    double remaining{0.0};
    double reserved{0.0};
    double capacity{0.0};

    bool operator==(const M11AdministrativeBudget &) const = default;
};

struct M11IdempotencyRecord final {
    std::string key;
    core::StateDigest request_hash{};
    std::string decision_id;

    bool operator==(const M11IdempotencyRecord &) const = default;
};

struct M11DuePlan final {
    Tick boundary{};
    simulation::WorldPolicyBatch policy_batch{};
    std::vector<std::string> effective_decision_ids;
    std::vector<std::string> failed_decision_ids;
    std::vector<NativePolicyAction> effective_changes;
    std::string exclusion_reason;

    [[nodiscard]] bool has_due_decisions() const noexcept {
        return !effective_decision_ids.empty() ||
               !failed_decision_ids.empty();
    }
};

[[nodiscard]] std::string_view
m11_decision_status_name(M11DecisionStatus status) noexcept;
[[nodiscard]] bool m11_world_capability(
    const simulation::M9World &world, EconomyId economy,
    std::string_view capability) noexcept;

class M11PolicyCoordinator final {
  public:
    [[nodiscard]] static Result<M11PolicyCoordinator>
    create(const simulation::M9World &world,
           M11AdjustmentCostSpec cost_spec = {});

    [[nodiscard]] const M11AdjustmentCostSpec &cost_spec() const noexcept {
        return cost_spec_;
    }
    [[nodiscard]] std::span<const M11PolicyVersion>
    policy_versions() const noexcept {
        return policy_versions_;
    }
    [[nodiscard]] std::span<const M11DecisionContext>
    contexts() const noexcept {
        return contexts_;
    }
    [[nodiscard]] std::span<const M11PendingDecision>
    pending() const noexcept {
        return pending_;
    }
    [[nodiscard]] std::span<const M11PolicyDecision>
    decisions() const noexcept {
        return decisions_;
    }
    [[nodiscard]] std::span<const M11AdministrativeBudget>
    budgets() const noexcept {
        return budgets_;
    }
    [[nodiscard]] std::span<const M11IdempotencyRecord>
    idempotency_records() const noexcept {
        return idempotency_;
    }
    [[nodiscard]] std::uint64_t next_decision_sequence() const noexcept {
        return next_decision_sequence_;
    }

    [[nodiscard]] const M11DecisionContext *
    find_context(std::string_view context_id) const noexcept;
    [[nodiscard]] const M11PolicyDecision *
    find_decision(std::string_view decision_id) const noexcept;
    [[nodiscard]] const M11PendingDecision *
    find_pending(std::string_view decision_id) const noexcept;
    [[nodiscard]] Result<std::uint64_t>
    policy_version(EconomyId economy, std::string_view lever) const noexcept;
    [[nodiscard]] const M11PolicyVersion *
    find_policy_version(EconomyId economy,
                        std::string_view lever) const noexcept;

    [[nodiscard]] Result<M11DecisionContext>
    open_context(const simulation::M9World &world,
                 const M11DecisionScheduler &scheduler, Tick boundary,
                 EconomyId economy, std::string seat,
                 std::string decision_group, Tick expires_at,
                 bool emergency = false,
                 std::string emergency_trigger = {},
                 std::uint64_t elapsed_ticks = 0U,
                 std::span<const M11ReleasedObservation> observation = {});
    [[nodiscard]] Result<M11PolicyDecision>
    submit(const simulation::M9World &world,
           const M11DecisionScheduler &scheduler, Tick boundary,
           M11PolicyProposal proposal, std::string_view actor,
           M11EventStream &events);
    [[nodiscard]] Result<M11PolicyDecision>
    cancel(Tick boundary, std::string_view decision_id,
           std::string_view operation_id, std::string_view actor,
           M11EventStream &events);
    [[nodiscard]] Result<M11DuePlan>
    prepare_due(const simulation::M9World &world, Tick boundary) const;
    [[nodiscard]] Status
    commit_due(const M11DuePlan &plan, M11EventStream &events);
    [[nodiscard]] Status
    fail_due(const M11DuePlan &plan, std::string_view reason,
             M11EventStream &events);

    [[nodiscard]] Status restore(
        const simulation::M9World &world,
        std::vector<M11PolicyVersion> policy_versions,
        std::vector<M11DecisionContext> contexts,
        std::vector<M11PendingDecision> pending,
        std::vector<M11PolicyDecision> decisions,
        std::vector<M11AdministrativeBudget> budgets,
        std::vector<M11IdempotencyRecord> idempotency,
        std::uint64_t next_decision_sequence);

  private:
    explicit M11PolicyCoordinator(M11AdjustmentCostSpec cost_spec)
        : cost_spec_(std::move(cost_spec)) {}

    [[nodiscard]] M11PolicyVersion *
    mutable_policy_version(EconomyId economy,
                           std::string_view lever) noexcept;
    [[nodiscard]] M11DecisionContext *
    mutable_context(std::string_view context_id) noexcept;
    [[nodiscard]] M11PendingDecision *
    mutable_pending(std::string_view decision_id) noexcept;
    [[nodiscard]] M11PolicyDecision *
    mutable_decision(std::string_view decision_id) noexcept;
    [[nodiscard]] M11AdministrativeBudget *
    mutable_budget(EconomyId economy, std::string_view seat,
                   std::string_view decision_group) noexcept;
    [[nodiscard]] Result<M11AdministrativeBudget *>
    ensure_budget(const M11DecisionScheduler &scheduler,
                  EconomyId economy, std::string_view seat,
                  std::string_view decision_group, Tick boundary);
    [[nodiscard]] M11PolicyDecision
    make_decision(const M11PolicyProposal &proposal,
                  M11DecisionStatus status, std::string reason,
                  std::optional<Tick> accepted_at,
                  std::optional<Tick> effective_at,
                  double administrative_cost = 0.0,
                  double adjustment_cost = 0.0);
    [[nodiscard]] Result<M11PolicyDecision>
    reject(const M11PolicyProposal &proposal, std::string reason,
           core::StateDigest request_hash);
    void refund(M11PendingDecision &pending, double fraction) noexcept;

    M11AdjustmentCostSpec cost_spec_{};
    std::vector<M11PolicyVersion> policy_versions_;
    std::vector<M11DecisionContext> contexts_;
    std::vector<M11PendingDecision> pending_;
    std::vector<M11PolicyDecision> decisions_;
    std::vector<M11AdministrativeBudget> budgets_;
    std::vector<M11IdempotencyRecord> idempotency_;
    std::uint64_t next_decision_sequence_{0U};
};

} // namespace macro_sim::control

#endif
