#include "macro_sim/engine_session.hpp"

namespace macro_sim {

EngineSession::EngineSession(EngineSessionOptions options) noexcept
    : id_(options.session_id) {}

EngineSession::EngineSession(std::uint64_t session_id) noexcept
    : EngineSession(EngineSessionOptions{SessionId(session_id)}) {}

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

Status EngineSession::close() noexcept {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is already closed");
    }
    state_ = SessionState::closed;
    return Status::success();
}

}  // namespace macro_sim
