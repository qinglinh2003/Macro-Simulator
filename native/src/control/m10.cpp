#include "macro_sim/control/m10.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <string_view>
#include <utility>
#include <vector>

namespace macro_sim::control {
namespace {

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

void append_vector(std::vector<std::uint8_t> &bytes,
                   std::span<const std::uint64_t> values) {
    append_u64(bytes, values.size());
    for (const auto value : values) {
        append_u64(bytes, value);
    }
}

[[nodiscard]] bool valid_operation_id(std::string_view value) noexcept {
    if (value.empty() || value.size() > kM10MaximumOperationIdBytes) {
        return false;
    }
    return std::all_of(value.begin(), value.end(), [](char character) {
        const auto byte = static_cast<unsigned char>(character);
        return byte >= 0x21U && byte <= 0x7eU;
    });
}

[[nodiscard]] core::StateDigest
transition_hash(const ControllerEnvelopeTransition &transition) noexcept {
    std::vector<std::uint8_t> bytes;
    bytes.reserve(64U + transition.operation_id.size());
    bytes.insert(bytes.end(), transition.operation_id.begin(),
                 transition.operation_id.end());
    bytes.insert(bytes.end(), transition.expected_prior_hash.bytes.begin(),
                 transition.expected_prior_hash.bytes.end());
    bytes.insert(bytes.end(), transition.next.hash.bytes.begin(),
                 transition.next.hash.bytes.end());
    return core::sha256_digest(bytes);
}

} // namespace

struct HybridControlledBridge::BoundaryAuthority final {
    bool active{false};
    std::uint64_t generation{0};
};

struct PreparedBoundaryLease::Impl final {
    std::shared_ptr<HybridControlledBridge::BoundaryAuthority> authority;
    std::uint64_t generation{0};
    BoundaryPreview preview;
    simulation::M9World staged_world;
    simulation::M9AdvanceResult advance_result;

    Impl(std::shared_ptr<HybridControlledBridge::BoundaryAuthority> authority_value,
         std::uint64_t generation_value, BoundaryPreview preview_value,
         simulation::M9World world_value,
         simulation::M9AdvanceResult advance_result_value)
        : authority(std::move(authority_value)), generation(generation_value),
          preview(std::move(preview_value)), staged_world(std::move(world_value)),
          advance_result(std::move(advance_result_value)) {}

    void release() noexcept {
        if (authority != nullptr && authority->generation == generation) {
            authority->active = false;
        }
        authority.reset();
    }
};

Result<EngineSession>
EngineSession::create(simulation::M9World world,
                      std::size_t history_capacity_frames) {
    if (history_capacity_frames == 0U) {
        return Status(ErrorCode::invalid_argument,
                      "M10 metric history capacity must be positive");
    }
    auto state = world.validate();
    if (!state.ok()) {
        return state;
    }
    reporting::MetricPipeline metrics(world.economy_count(),
                                      history_capacity_frames);
    auto capture = metrics.capture(world);
    if (!capture.ok()) {
        return capture;
    }
    return EngineSession(std::move(world), std::move(metrics));
}

Result<simulation::M9AdvanceResult>
EngineSession::advance_ticks(std::uint64_t count,
                             const simulation::M9AdvanceOptions &options) {
    auto result = world_.advance(count, options);
    if (!result.ok()) {
        return result.status();
    }
    auto status = metrics_.capture(world_);
    if (!status.ok()) {
        return status;
    }
    return std::move(*result.get_if());
}

Result<EngineSession> EngineSession::clone() const { return *this; }

PreparedBoundaryLease::PreparedBoundaryLease(std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}

PreparedBoundaryLease::PreparedBoundaryLease(PreparedBoundaryLease &&) noexcept =
    default;

PreparedBoundaryLease &
PreparedBoundaryLease::operator=(PreparedBoundaryLease &&other) noexcept {
    if (this != &other) {
        if (impl_ != nullptr) {
            impl_->release();
        }
        impl_ = std::move(other.impl_);
    }
    return *this;
}

PreparedBoundaryLease::~PreparedBoundaryLease() {
    if (impl_ != nullptr) {
        impl_->release();
    }
}

const BoundaryPreview &PreparedBoundaryLease::preview() const noexcept {
    static const BoundaryPreview empty{};
    return impl_ == nullptr ? empty : impl_->preview;
}

bool PreparedBoundaryLease::active() const noexcept {
    return impl_ != nullptr && impl_->authority != nullptr &&
           impl_->authority->active &&
           impl_->authority->generation == impl_->generation;
}

HybridControlledBridge::HybridControlledBridge(
    EngineSession engine, CanonicalControllerEnvelope envelope)
    : engine_(std::move(engine)), envelope_(std::move(envelope)),
      authority_(std::make_shared<BoundaryAuthority>()) {}

Result<HybridControlledBridge>
HybridControlledBridge::create(EngineSession engine,
                               CanonicalControllerEnvelope envelope) {
    HybridControlledBridge result(std::move(engine), std::move(envelope));
    auto status = result.validate_envelope(
        result.envelope_, result.engine_.tick(),
        result.engine_.policy_generation());
    if (!status.ok()) {
        return status;
    }
    return std::move(result);
}

Status HybridControlledBridge::require_available() const noexcept {
    return authority_->active
               ? Status(ErrorCode::invalid_transaction_state,
                        "M10 prepared boundary lease is outstanding")
               : Status::success();
}

Status HybridControlledBridge::validate_envelope(
    const CanonicalControllerEnvelope &envelope, Tick expected_boundary,
    std::uint64_t expected_policy_generation) const noexcept {
    if (envelope.schema_version != 1U ||
        envelope.canonical_payload.size() >
            kM10MaximumControllerEnvelopeBytes ||
        envelope.boundary != expected_boundary ||
        envelope.policy_generation != expected_policy_generation ||
        envelope.decision_versions.size() !=
            envelope.effective_versions.size() ||
        controller_envelope_hash(envelope) != envelope.hash) {
        return Status(ErrorCode::contract_violation,
                      "M10 controller envelope is invalid");
    }
    for (std::size_t index = 0; index < envelope.decision_versions.size();
         ++index) {
        if (envelope.effective_versions[index] >
            envelope.decision_versions[index]) {
            return Status(ErrorCode::contract_violation,
                          "effective policy version exceeds decision version");
        }
    }
    return Status::success();
}

Result<ControllerUpdateReceipt>
HybridControlledBridge::update_controller(
    const ControllerEnvelopeTransition &transition) {
    auto available = require_available();
    if (!available.ok()) {
        return available;
    }
    if (!valid_operation_id(transition.operation_id)) {
        return Status(ErrorCode::invalid_argument,
                      "controller operation ID is invalid");
    }
    const auto request_hash = transition_hash(transition);
    const auto existing =
        std::find_if(receipts_.begin(), receipts_.end(),
                     [&](const ControllerUpdateReceipt &receipt) {
                         return receipt.operation_id == transition.operation_id;
                     });
    if (existing != receipts_.end()) {
        if (existing->request_hash != request_hash) {
            return Status(ErrorCode::already_exists,
                          "controller operation ID payload differs");
        }
        return *existing;
    }
    const auto unacknowledged =
        std::count_if(receipts_.begin(), receipts_.end(),
                      [](const ControllerUpdateReceipt &receipt) {
                          return !receipt.acknowledged;
                      });
    if (static_cast<std::size_t>(unacknowledged) >=
        kM10MaximumUnacknowledgedReceipts) {
        return Status(ErrorCode::out_of_range,
                      "controller receipt cache requires acknowledgement");
    }
    if (transition.expected_prior_hash != envelope_.hash) {
        return Status(ErrorCode::stale_handle,
                      "controller envelope prior hash is stale");
    }
    auto status = validate_envelope(
        transition.next, engine_.tick(), engine_.policy_generation());
    if (!status.ok()) {
        return status;
    }
    if (transition.next.event_sequence < envelope_.event_sequence ||
        transition.next.release_cursor < envelope_.release_cursor) {
        return Status(ErrorCode::contract_violation,
                      "controller envelope cursors cannot move backward");
    }
    ControllerUpdateReceipt receipt{
        transition.operation_id,
        request_hash,
        envelope_.hash,
        transition.next.hash,
        engine_.tick(),
        false,
    };
    envelope_ = transition.next;
    receipts_.push_back(receipt);
    return receipt;
}

Status HybridControlledBridge::acknowledge_receipt(
    std::string_view operation_id) {
    auto available = require_available();
    if (!available.ok()) {
        return available;
    }
    const auto found =
        std::find_if(receipts_.begin(), receipts_.end(),
                     [operation_id](const ControllerUpdateReceipt &receipt) {
                         return receipt.operation_id == operation_id;
                     });
    if (found == receipts_.end()) {
        return Status(ErrorCode::not_found, "controller receipt was not found");
    }
    found->acknowledged = true;
    return Status::success();
}

Result<PreparedBoundaryLease>
HybridControlledBridge::prepare_boundary(const SealedControlBatch &batch) {
    auto available = require_available();
    if (!available.ok()) {
        return available;
    }
    if (!valid_operation_id(batch.operation_id) ||
        batch.expected_controller_hash != envelope_.hash ||
        batch.advance_ticks == 0U ||
        batch.policies.expected_tick != engine_.tick() ||
        batch.policies.expected_generation != engine_.policy_generation()) {
        return Status(ErrorCode::stale_handle,
                      "M10 sealed boundary precondition is stale");
    }

    auto staged = engine_.world_;
    auto policy_status = staged.update_policy_batch(batch.policies);
    if (!policy_status.ok()) {
        return policy_status;
    }
    auto advanced = staged.advance(batch.advance_ticks, batch.advance_options);
    if (!advanced.ok()) {
        return advanced.status();
    }
    auto frame = reporting::build_public_metric_frame(
        staged, &engine_.metrics_.current());
    if (!frame.ok()) {
        return frame.status();
    }

    authority_->active = true;
    ++authority_->generation;
    BoundaryPreview preview{
        batch.operation_id,
        engine_.tick(),
        staged.tick(),
        staged.policy_generation(),
        staged.digest(),
        std::move(*frame.get_if()),
    };
    auto impl = std::make_unique<PreparedBoundaryLease::Impl>(
        authority_, authority_->generation, std::move(preview),
        std::move(staged), std::move(*advanced.get_if()));
    return PreparedBoundaryLease(std::move(impl));
}

Result<simulation::M9AdvanceResult>
HybridControlledBridge::commit_boundary(PreparedBoundaryLease &&lease,
                                        CanonicalControllerEnvelope next) {
    if (!lease.active() || lease.impl_->authority.get() != authority_.get()) {
        return Status(ErrorCode::stale_handle,
                      "M10 prepared boundary lease is stale");
    }
    auto status = validate_envelope(
        next, lease.impl_->preview.next_tick,
        lease.impl_->preview.policy_generation);
    if (!status.ok()) {
        return status;
    }
    if (next.event_sequence < envelope_.event_sequence ||
        next.release_cursor < envelope_.release_cursor) {
        return Status(ErrorCode::contract_violation,
                      "committed controller cursors cannot move backward");
    }

    auto history_status =
        engine_.metrics_.commit(lease.impl_->preview.public_metrics);
    if (!history_status.ok()) {
        return history_status;
    }
    engine_.world_ = std::move(lease.impl_->staged_world);
    envelope_ = std::move(next);
    auto result = lease.impl_->advance_result;
    lease.impl_->release();
    lease.impl_.reset();
    return result;
}

Status
HybridControlledBridge::abort_boundary(PreparedBoundaryLease &&lease) {
    if (!lease.active() || lease.impl_->authority.get() != authority_.get()) {
        return Status(ErrorCode::stale_handle,
                      "M10 prepared boundary lease is stale");
    }
    lease.impl_->release();
    lease.impl_.reset();
    return Status::success();
}

Result<HybridControlledBridge> HybridControlledBridge::clone() const {
    auto available = require_available();
    if (!available.ok()) {
        return available;
    }
    HybridControlledBridge result(engine_, envelope_);
    result.receipts_ = receipts_;
    return std::move(result);
}

core::StateDigest
controller_envelope_hash(const CanonicalControllerEnvelope &envelope) noexcept {
    std::vector<std::uint8_t> bytes;
    bytes.reserve(64U + envelope.canonical_payload.size() +
                  (envelope.decision_versions.size() +
                   envelope.effective_versions.size()) *
                      sizeof(std::uint64_t));
    const std::array<std::uint8_t, 8> magic{
        'M', 'S', 'C', 'T', 'R', 'L', '0', '1',
    };
    bytes.insert(bytes.end(), magic.begin(), magic.end());
    append_u32(bytes, envelope.schema_version);
    append_u64(bytes, envelope.boundary.value());
    append_u64(bytes, envelope.policy_generation);
    append_u64(bytes, envelope.event_sequence);
    append_u64(bytes, envelope.release_cursor);
    append_vector(bytes, envelope.decision_versions);
    append_vector(bytes, envelope.effective_versions);
    append_u64(bytes, envelope.canonical_payload.size());
    bytes.insert(bytes.end(), envelope.canonical_payload.begin(),
                 envelope.canonical_payload.end());
    return core::sha256_digest(bytes);
}

Status seal_controller_envelope(CanonicalControllerEnvelope &envelope) noexcept {
    if (envelope.schema_version != 1U ||
        envelope.canonical_payload.size() >
            kM10MaximumControllerEnvelopeBytes ||
        envelope.decision_versions.size() !=
            envelope.effective_versions.size()) {
        return Status(ErrorCode::invalid_argument,
                      "cannot seal invalid controller envelope");
    }
    envelope.hash = controller_envelope_hash(envelope);
    return Status::success();
}

} // namespace macro_sim::control
