#ifndef MACRO_SIM_CONTROL_M11_SESSION_HPP
#define MACRO_SIM_CONTROL_M11_SESSION_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/control/m10.hpp"
#include "macro_sim/control/m11_artifact.hpp"
#include "macro_sim/control/m11_coordinator.hpp"
#include "macro_sim/control/m11_release.hpp"
#include "macro_sim/error.hpp"

namespace macro_sim::control {

enum class M11BoundaryPhase : std::uint8_t {
    boundary_start = 0,
    awaiting_human = 1,
    ready_to_commit = 2,
};

enum class M11OccupantKind : std::uint8_t {
    null_occupant = 0,
    scheduled = 1,
    heuristic = 2,
    random_fuzz = 3,
    human_queue = 4,
    reinforcement_learning = 5,
};

struct M11ScheduledPolicyActions final {
    Tick boundary{};
    std::string decision_group;
    std::vector<NativePolicyAction> actions;

    bool operator==(const M11ScheduledPolicyActions &) const = default;
};

struct M11OccupantSpec final {
    M11OccupantKind kind{M11OccupantKind::null_occupant};
    std::string occupant_id{"null"};
    std::uint64_t seed{0U};
    double random_action_probability{0.35};
    std::vector<M11ScheduledPolicyActions> schedule;
    std::filesystem::path artifact_path;
    std::vector<std::string> action_dimensions;

    bool operator==(const M11OccupantSpec &) const = default;
};

struct M11SeatAssignment final {
    EconomyId economy{};
    std::string seat;
    M11OccupantSpec occupant{};

    bool operator==(const M11SeatAssignment &) const = default;
};

struct M11ShockAuthority final {
    std::string principal;
    std::vector<std::string> granted_seats;
    std::vector<simulation::ShockKind> allowed_kinds;
    std::vector<EconomyId> allowed_economies;
    bool allow_all_economies{false};
    bool allow_global{false};
    std::uint64_t minimum_announcement_lead_ticks{0U};
    std::uint64_t maximum_schedule_ahead_ticks{36500U};
    std::uint64_t maximum_duration_ticks{36500U};
    double maximum_absolute_magnitude{1.0};

    bool operator==(const M11ShockAuthority &) const = default;
};

struct M11ControlledShockScheduleRequest final {
    std::string operation_id;
    std::string principal;
    std::string actor;
    std::optional<std::string> seat{};
    simulation::ShockSpec shock{};
};

struct M11ShockScheduleResult final {
    std::uint64_t shock_id{0U};
    Tick accepted_at{};
    std::uint64_t event_sequence{0U};
    bool repeated{false};

    bool operator==(const M11ShockScheduleResult &) const = default;
};

struct M11SeatRuntime final {
    M11SeatAssignment assignment;
    std::uint64_t decision_counter{0U};
    std::string artifact_sha256;
    std::optional<NativePolicyArtifact> artifact{};
};

struct M11ArchivedSeatOccupant final {
    std::string archive_id;
    M11SeatRuntime runtime;
};

enum class M11SeatOperationKind : std::uint8_t {
    assignment = 0,
    restoration = 1,
};

struct M11SeatOperationRecord final {
    std::string operation_id;
    M11SeatOperationKind kind{M11SeatOperationKind::assignment};
    core::StateDigest request_hash{};
    std::optional<std::string> archived_occupant_id{};

    bool operator==(const M11SeatOperationRecord &) const = default;
};

struct M11SeatChangeResult final {
    std::optional<std::string> archived_occupant_id{};
    bool repeated{false};

    bool operator==(const M11SeatChangeResult &) const = default;
};

struct M11ControllerRunSpec final {
    std::vector<M11CalendarSpec> calendars{m11_default_calendars()};
    std::vector<M11TriggerSpec> triggers{m11_default_triggers()};
    M11AdjustmentCostSpec cost_spec{};
    std::vector<M11SeatAssignment> assignments;
    std::vector<M11ShockAuthority> shock_authorities;
    bool fill_unassigned_with_null{true};
    std::uint32_t worker_count{1U};
    simulation::M9AdvanceOptions advance_options{};
    std::size_t maximum_events{kM11MaximumControllerEvents};
    std::size_t maximum_releases{kM11MaximumControllerReleases};

};

struct M11AdvanceLimit final {
    std::uint64_t maximum_ticks{1U};
    bool stop_after_context_boundary{true};
};

struct M11DecisionResult final {
    M11BoundaryPhase phase{M11BoundaryPhase::boundary_start};
    Tick boundary{};
    std::uint64_t elapsed_ticks{0U};
    std::vector<std::string> opened_context_ids;
    std::vector<M11PolicyDecision> decisions;
    std::optional<simulation::M9AdvanceResult> advance{};
    bool awaiting_human{false};
    bool limit_reached{false};
};

struct M11SeatAssignmentRequest final {
    std::string operation_id;
    std::string actor;
    EconomyId economy{};
    std::string seat;
    M11OccupantSpec occupant{};
};

struct M11SeatRestoreRequest final {
    std::string operation_id;
    std::string actor;
    EconomyId economy{};
    std::string seat;
    std::string archived_occupant_id;
};

struct M11ControlledState final {
    M11BoundaryPhase phase{M11BoundaryPhase::boundary_start};
    M11DecisionScheduler scheduler;
    M11PolicyCoordinator coordinator;
    M11EventStream events;
    M11ReleaseStream releases;
    std::vector<M11SeatRuntime> seats;
    std::vector<M11ArchivedSeatOccupant> archived_seat_occupants;
    std::vector<M11SeatOperationRecord> seat_operations;
    std::vector<std::string> opened_context_ids;
    std::uint64_t boundary_sequence{0U};

    M11ControlledState(M11DecisionScheduler scheduler_value,
                       M11PolicyCoordinator coordinator_value,
                       M11EventStream events_value,
                       M11ReleaseStream releases_value)
        : scheduler(std::move(scheduler_value)),
          coordinator(std::move(coordinator_value)),
          events(std::move(events_value)),
          releases(std::move(releases_value)) {}
};

class M11ControlledSession;
[[nodiscard]] Result<CanonicalControllerEnvelope>
seal_m11_controller_state(Tick boundary,
                          std::uint64_t policy_generation,
                          const M11ControlledState &state);
[[nodiscard]] Result<std::vector<std::uint8_t>>
save_m11_checkpoint(const M11ControlledSession &session);
[[nodiscard]] Result<M11ControlledSession>
load_m11_checkpoint(std::span<const std::uint8_t> checkpoint);

class M11ControlledSession final {
  public:
    M11ControlledSession(const M11ControlledSession &) = delete;
    M11ControlledSession &
    operator=(const M11ControlledSession &) = delete;
    M11ControlledSession(M11ControlledSession &&) noexcept = default;
    M11ControlledSession &
    operator=(M11ControlledSession &&) noexcept = default;
    ~M11ControlledSession() = default;

    [[nodiscard]] static Result<M11ControlledSession>
    create(EngineSession engine, M11ControllerRunSpec run_spec = {});

    [[nodiscard]] Tick tick() const noexcept {
        return bridge_.engine().tick();
    }
    [[nodiscard]] M11BoundaryPhase phase() const noexcept {
        return state_.phase;
    }
    [[nodiscard]] const EngineSession &engine() const noexcept {
        return bridge_.engine();
    }
    [[nodiscard]] const M11ControllerRunSpec &
    run_spec() const noexcept {
        return run_spec_;
    }
    [[nodiscard]] const M11ControlledState &state() const noexcept {
        return state_;
    }
    [[nodiscard]] const M11PolicyCoordinator &
    coordinator() const noexcept {
        return state_.coordinator;
    }
    [[nodiscard]] const M11EventStream &events() const noexcept {
        return state_.events;
    }
    [[nodiscard]] const M11ReleaseStream &releases() const noexcept {
        return state_.releases;
    }
    [[nodiscard]] const M11SeatRuntime *
    seat(EconomyId economy, std::string_view seat) const noexcept;

    [[nodiscard]] Result<M11DecisionResult>
    advance_until_decision(const M11AdvanceLimit &limit = {});
    [[nodiscard]] Result<M11PolicyDecision>
    submit_policy_proposal(M11PolicyProposal proposal,
                           std::string_view actor);
    [[nodiscard]] Result<M11PolicyDecision>
    submit_human_proposal(M11PolicyProposal proposal,
                          std::string_view actor);
    [[nodiscard]] Result<M11PolicyDecision>
    timeout_context(std::string_view context_id,
                    std::string_view operation_id,
                    std::string_view actor);
    [[nodiscard]] Result<M11PolicyDecision>
    cancel_pending(std::string_view decision_id,
                   std::string_view operation_id,
                   std::string_view actor);
    [[nodiscard]] Result<M11SeatChangeResult>
    assign_seat(const M11SeatAssignmentRequest &request);
    [[nodiscard]] Result<M11SeatChangeResult>
    restore_seat(const M11SeatRestoreRequest &request);
    [[nodiscard]] Result<M11ShockScheduleResult>
    schedule_shock(
        const M11ControlledShockScheduleRequest &request);
    [[nodiscard]] Result<M11ControlledSession> clone() const;

  private:
    friend Result<std::vector<std::uint8_t>>
    save_m11_checkpoint(const M11ControlledSession &);
    friend Result<M11ControlledSession>
    load_m11_checkpoint(std::span<const std::uint8_t>);

    M11ControlledSession(HybridControlledBridge bridge,
                         M11ControllerRunSpec run_spec,
                         M11ControlledState state)
        : bridge_(std::move(bridge)), run_spec_(std::move(run_spec)),
          state_(std::move(state)) {}

    [[nodiscard]] Status synchronize_state(
        std::string operation_id, M11ControlledState next);
    [[nodiscard]] Result<M11DecisionResult>
    run_boundary_prelude();
    [[nodiscard]] Result<M11DecisionResult>
    commit_ready_boundary();
    [[nodiscard]] Result<M11PolicyProposal>
    automatic_proposal(M11SeatRuntime &seat,
                       const M11DecisionContext &context) const;
    [[nodiscard]] bool
    has_unanswered_human_context() const noexcept;

    HybridControlledBridge bridge_;
    M11ControllerRunSpec run_spec_;
    M11ControlledState state_;
    M11ReleaseService release_service_{};
};

[[nodiscard]] std::string_view
m11_boundary_phase_name(M11BoundaryPhase phase) noexcept;
[[nodiscard]] std::string_view
m11_occupant_kind_name(M11OccupantKind kind) noexcept;

} // namespace macro_sim::control

#endif
