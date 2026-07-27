#ifndef MACRO_SIM_CONTROL_M11_FRONTEND_HPP
#define MACRO_SIM_CONTROL_M11_FRONTEND_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/control/m11_session.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/reporting/probes.hpp"

namespace macro_sim::control {

inline constexpr std::uint32_t kM11FrontendSnapshotSchemaVersion = 2U;
inline constexpr std::size_t kM11FrontendEventWindow = 1024U;

struct M11AccessScope final {
    std::string principal;
    EconomyId economy{};
    std::string role;

    bool operator==(const M11AccessScope &) const = default;
};

struct M11FrontendMetric final {
    std::string stable_id;
    std::optional<double> value{};

    bool operator==(const M11FrontendMetric &) const = default;
};

struct M11FrontendPolicy final {
    std::string lever;
    PolicyValue value{};
    std::uint64_t version{0U};

    bool operator==(const M11FrontendPolicy &) const = default;
};

struct M11FrontendEconomy final {
    EconomyId economy{};
    std::vector<M11FrontendMetric> metrics;

    bool operator==(const M11FrontendEconomy &) const = default;
};

struct M11FrontendSnapshot final {
    std::uint32_t schema_version{kM11FrontendSnapshotSchemaVersion};
    std::string cache_epoch;
    std::uint64_t snapshot_sequence{0U};
    core::StateDigest snapshot_id{};
    M11AccessScope scope;
    Tick boundary{};
    M11BoundaryPhase phase{M11BoundaryPhase::boundary_start};
    bool awaiting_human{false};
    std::uint64_t event_cursor{0U};
    std::uint64_t release_cursor{0U};
    std::vector<M11FrontendMetric> metrics;
    std::vector<M11FrontendEconomy> economies;
    std::vector<M11FrontendPolicy> policies;
    std::vector<M11ReleasedObservation> releases;
    std::vector<M11DecisionContext> contexts;
    std::vector<M11PendingDecision> pending;
    std::vector<M11ControllerEvent> public_events;
    std::vector<reporting::ShockBulletinProbeRow> shock_bulletins;
};

struct M11FrontendDelta final {
    std::uint32_t schema_version{kM11FrontendSnapshotSchemaVersion};
    core::StateDigest base_snapshot_id{};
    core::StateDigest result_snapshot_id{};
    std::uint64_t base_sequence{0U};
    std::uint64_t result_sequence{0U};
    Tick boundary{};
    M11BoundaryPhase phase{M11BoundaryPhase::boundary_start};
    bool awaiting_human{false};
    std::uint64_t event_cursor{0U};
    std::uint64_t release_cursor{0U};
    std::vector<M11FrontendMetric> changed_metrics;
    std::vector<M11FrontendEconomy> changed_economies;
    std::vector<M11FrontendPolicy> changed_policies;
    std::vector<M11ReleasedObservation> releases;
    std::vector<M11DecisionContext> contexts;
    std::vector<M11PendingDecision> pending;
    std::vector<M11ControllerEvent> appended_public_events;
    std::vector<reporting::ShockBulletinProbeRow> shock_bulletins;
};

class M11FrontendProjection final {
  public:
    [[nodiscard]] Result<M11FrontendSnapshot>
    snapshot(const M11ControlledSession &session, const M11AccessScope &scope,
             std::string cache_epoch, std::uint64_t snapshot_sequence) const;
    [[nodiscard]] Result<M11FrontendDelta>
    delta(const M11FrontendSnapshot &base, const M11FrontendSnapshot &result) const;

  private:
    M11ReleaseService release_service_{};
};

[[nodiscard]] core::StateDigest
m11_frontend_snapshot_id(const M11FrontendSnapshot &snapshot) noexcept;

} // namespace macro_sim::control

#endif
