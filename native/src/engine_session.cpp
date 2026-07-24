#include "macro_sim/engine_session.hpp"

#include <new>
#include <utility>

namespace macro_sim {

EngineSession::EngineSession(EngineSessionOptions options) noexcept
    : id_(options.session_id) {}

EngineSession::EngineSession(std::uint64_t session_id) noexcept
    : EngineSession(EngineSessionOptions{SessionId(session_id)}) {}

EngineSession::~EngineSession() = default;

SessionId EngineSession::id() const noexcept {
    return id_;
}

Tick EngineSession::tick() const noexcept {
    return tick_;
}

SessionState EngineSession::state() const noexcept {
    return state_;
}

bool EngineSession::closed() const noexcept {
    return state_ == SessionState::closed;
}

bool EngineSession::initialized() const noexcept {
    return root_ != nullptr;
}

core::RootState* EngineSession::root() noexcept {
    return root_.get();
}

const core::RootState* EngineSession::root() const noexcept {
    return root_.get();
}

Status EngineSession::initialize(const core::GenesisSpec& spec) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(
            ErrorCode::already_exists,
            "session already has canonical state"
        );
    }
    try {
        auto state = core::build_genesis(spec);
        if (!state.ok()) {
            return state.status();
        }
        root_ = std::make_unique<core::RootState>(
            std::move(*state.get_if())
        );
        return Status::success();
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "session genesis allocation failed"
        );
    } catch (...) {
        return Status(ErrorCode::internal_error, "session genesis failed");
    }
}

Result<core::TransactionReceipt> EngineSession::apply(
    const core::SettlementBatch& batch
) {
    if (closed() || !initialized()) {
        return Status(
            ErrorCode::invalid_handle,
            "session has no active canonical state"
        );
    }
    try {
        core::SettlementTransaction transaction(*root_);
        const auto appended = transaction.append(batch);
        if (!appended.ok()) {
            return appended;
        }
        return transaction.commit();
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "batch allocation failed"
        );
    } catch (...) {
        return Status(ErrorCode::internal_error, "batch execution failed");
    }
}

Result<core::StateDigest> EngineSession::digest() const {
    if (closed() || !initialized()) {
        return Status(
            ErrorCode::invalid_handle,
            "session has no active canonical state"
        );
    }
    return core::state_digest(*root_);
}

Result<std::vector<std::uint8_t>> EngineSession::checkpoint() const {
    if (closed() || !initialized()) {
        return Status(
            ErrorCode::invalid_handle,
            "session has no active canonical state"
        );
    }
    return core::save_checkpoint(*root_);
}

Status EngineSession::restore_checkpoint(
    std::span<const std::uint8_t> checkpoint
) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    auto state = core::load_checkpoint(checkpoint);
    if (!state.ok()) {
        return state.status();
    }
    try {
        auto replacement = std::make_unique<core::RootState>(
            std::move(*state.get_if())
        );
        root_ = std::move(replacement);
        return Status::success();
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "checkpoint restore allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "checkpoint restore failed"
        );
    }
}

Status EngineSession::close() noexcept {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is already closed");
    }
    root_.reset();
    state_ = SessionState::closed;
    return Status::success();
}

}  // namespace macro_sim
