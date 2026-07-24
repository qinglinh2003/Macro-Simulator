#ifndef MACRO_SIM_ENGINE_SESSION_HPP
#define MACRO_SIM_ENGINE_SESSION_HPP

#include <cstdint>

#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim {

enum class SessionState : std::uint8_t {
    ready = 0,
    closed = 1,
};

struct EngineSessionOptions final {
    SessionId session_id{SessionId(1)};
};

class EngineSession final {
public:
    explicit EngineSession(EngineSessionOptions options = {}) noexcept;
    explicit EngineSession(std::uint64_t session_id) noexcept;
    EngineSession(const EngineSession&) = delete;
    EngineSession& operator=(const EngineSession&) = delete;
    EngineSession(EngineSession&&) = delete;
    EngineSession& operator=(EngineSession&&) = delete;
    ~EngineSession() = default;

    [[nodiscard]] SessionId id() const noexcept;
    [[nodiscard]] Tick tick() const noexcept;
    [[nodiscard]] SessionState state() const noexcept;
    [[nodiscard]] bool closed() const noexcept;
    [[nodiscard]] Status close() noexcept;

private:
    SessionId id_;
    Tick tick_{};
    SessionState state_{SessionState::ready};
};

}  // namespace macro_sim

#endif
