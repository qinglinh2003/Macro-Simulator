#ifndef MACRO_SIM_CONTROL_M10_HPP
#define MACRO_SIM_CONTROL_M10_HPP

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/reporting/m10.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::control {

inline constexpr std::size_t kM10MaximumControllerEnvelopeBytes =
    16U * 1024U * 1024U;
inline constexpr std::size_t kM10MaximumOperationIdBytes = 128U;
inline constexpr std::size_t kM10MaximumUnacknowledgedReceipts = 1024U;

struct CanonicalControllerEnvelope final {
    std::uint32_t schema_version{1};
    Tick boundary{};
    std::uint64_t policy_generation{0};
    std::uint64_t event_sequence{0};
    std::uint64_t release_cursor{0};
    std::vector<std::uint64_t> decision_versions;
    std::vector<std::uint64_t> effective_versions;
    std::vector<std::uint8_t> canonical_payload;
    core::StateDigest hash{};

    bool operator==(const CanonicalControllerEnvelope &) const = default;
};

struct ControllerEnvelopeTransition final {
    std::string operation_id;
    core::StateDigest expected_prior_hash{};
    CanonicalControllerEnvelope next{};
};

struct ControllerUpdateReceipt final {
    std::string operation_id;
    core::StateDigest request_hash{};
    core::StateDigest prior_hash{};
    core::StateDigest result_hash{};
    Tick boundary{};
    bool acknowledged{false};

    bool operator==(const ControllerUpdateReceipt &) const = default;
};

struct SealedControlBatch final {
    std::string operation_id;
    core::StateDigest expected_controller_hash{};
    simulation::WorldPolicyBatch policies{};
    std::uint64_t advance_ticks{1};
    simulation::M9AdvanceOptions advance_options{};
};

struct BoundaryPreview final {
    std::string operation_id;
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t policy_generation{0};
    std::uint64_t engine_digest{0};
    reporting::MetricFrame public_metrics{};
};

class HybridControlledBridge;
struct LoadedHybridComposite;

[[nodiscard]] Result<std::vector<std::uint8_t>>
save_hybrid_checkpoint(const HybridControlledBridge &bridge,
                       std::span<const std::uint8_t> objective_envelope = {});
[[nodiscard]] Result<LoadedHybridComposite>
load_hybrid_checkpoint(std::span<const std::uint8_t> checkpoint);

class EngineSession final {
  public:
    EngineSession(const EngineSession &) = default;
    EngineSession &operator=(const EngineSession &) = default;
    EngineSession(EngineSession &&) noexcept = default;
    EngineSession &operator=(EngineSession &&) noexcept = default;
    ~EngineSession() = default;

    [[nodiscard]] static Result<EngineSession>
    create(simulation::M9World world,
           std::size_t history_capacity_frames = 4096U);

    [[nodiscard]] Tick tick() const noexcept { return world_.tick(); }
    [[nodiscard]] std::uint64_t policy_generation() const noexcept {
        return world_.policy_generation();
    }
    [[nodiscard]] const simulation::M9World &world() const noexcept {
        return world_;
    }
    [[nodiscard]] const reporting::MetricPipeline &metrics() const noexcept {
        return metrics_;
    }
    [[nodiscard]] Result<simulation::M9AdvanceResult>
    advance_ticks(std::uint64_t count,
                  const simulation::M9AdvanceOptions &options = {});
    [[nodiscard]] Result<EngineSession> clone() const;

  private:
    friend class HybridControlledBridge;
    friend Result<LoadedHybridComposite>
    load_hybrid_checkpoint(std::span<const std::uint8_t>);
    EngineSession(simulation::M9World world, reporting::MetricPipeline metrics)
        : world_(std::move(world)), metrics_(std::move(metrics)) {}

    simulation::M9World world_;
    reporting::MetricPipeline metrics_;
};

class PreparedBoundaryLease final {
  public:
    PreparedBoundaryLease(const PreparedBoundaryLease &) = delete;
    PreparedBoundaryLease &operator=(const PreparedBoundaryLease &) = delete;
    PreparedBoundaryLease(PreparedBoundaryLease &&) noexcept;
    PreparedBoundaryLease &operator=(PreparedBoundaryLease &&) noexcept;
    ~PreparedBoundaryLease();

    [[nodiscard]] const BoundaryPreview &preview() const noexcept;
    [[nodiscard]] bool active() const noexcept;

  private:
    friend class HybridControlledBridge;
    struct Impl;
    explicit PreparedBoundaryLease(std::unique_ptr<Impl> impl);
    std::unique_ptr<Impl> impl_;
};

class HybridControlledBridge final {
  public:
    HybridControlledBridge(const HybridControlledBridge &) = delete;
    HybridControlledBridge &operator=(const HybridControlledBridge &) = delete;
    HybridControlledBridge(HybridControlledBridge &&) noexcept = default;
    HybridControlledBridge &operator=(HybridControlledBridge &&) noexcept = default;
    ~HybridControlledBridge() = default;

    [[nodiscard]] static Result<HybridControlledBridge>
    create(EngineSession engine, CanonicalControllerEnvelope envelope);

    [[nodiscard]] const CanonicalControllerEnvelope &
    controller_envelope() const noexcept {
        return envelope_;
    }
    [[nodiscard]] const EngineSession &engine() const noexcept { return engine_; }
    [[nodiscard]] Result<ControllerUpdateReceipt>
    update_controller(const ControllerEnvelopeTransition &transition);
    [[nodiscard]] Status acknowledge_receipt(std::string_view operation_id);
    [[nodiscard]] Result<PreparedBoundaryLease>
    prepare_boundary(const SealedControlBatch &batch);
    [[nodiscard]] Result<simulation::M9AdvanceResult>
    commit_boundary(PreparedBoundaryLease &&lease,
                    CanonicalControllerEnvelope next);
    [[nodiscard]] Status abort_boundary(PreparedBoundaryLease &&lease);
    [[nodiscard]] Result<HybridControlledBridge> clone() const;

  private:
    friend class PreparedBoundaryLease;
    friend Result<std::vector<std::uint8_t>>
    save_hybrid_checkpoint(const HybridControlledBridge &,
                           std::span<const std::uint8_t>);
    friend Result<LoadedHybridComposite>
    load_hybrid_checkpoint(std::span<const std::uint8_t>);
    struct BoundaryAuthority;

    HybridControlledBridge(EngineSession engine,
                           CanonicalControllerEnvelope envelope);
    [[nodiscard]] Status require_available() const noexcept;
    [[nodiscard]] Status
    validate_envelope(const CanonicalControllerEnvelope &envelope,
                      Tick expected_boundary,
                      std::uint64_t expected_policy_generation) const noexcept;

    EngineSession engine_;
    CanonicalControllerEnvelope envelope_;
    std::vector<ControllerUpdateReceipt> receipts_;
    std::shared_ptr<BoundaryAuthority> authority_;
};

struct LoadedHybridComposite final {
    HybridControlledBridge bridge;
    std::vector<std::uint8_t> objective_envelope;
};

[[nodiscard]] core::StateDigest
controller_envelope_hash(const CanonicalControllerEnvelope &envelope) noexcept;
[[nodiscard]] Status
seal_controller_envelope(CanonicalControllerEnvelope &envelope) noexcept;

} // namespace macro_sim::control

#endif
