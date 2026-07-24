#ifndef MACRO_SIM_ENGINE_SESSION_HPP
#define MACRO_SIM_ENGINE_SESSION_HPP

#include <cstdint>
#include <memory>
#include <span>
#include <vector>

#include "macro_sim/core/checkpoint.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/core/transaction.hpp"
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
    ~EngineSession();

    [[nodiscard]] SessionId id() const noexcept;
    [[nodiscard]] Tick tick() const noexcept;
    [[nodiscard]] SessionState state() const noexcept;
    [[nodiscard]] bool closed() const noexcept;
    [[nodiscard]] bool initialized() const noexcept;
    [[nodiscard]] core::RootState* root() noexcept;
    [[nodiscard]] const core::RootState* root() const noexcept;
    [[nodiscard]] Status initialize(const core::GenesisSpec& spec);
    [[nodiscard]] Result<core::TransactionReceipt> apply(
        const core::SettlementBatch& batch
    );
    [[nodiscard]] Result<core::StateDigest> digest() const;
    [[nodiscard]] Result<std::vector<std::uint8_t>> checkpoint() const;
    [[nodiscard]] Status restore_checkpoint(
        std::span<const std::uint8_t> checkpoint
    );
    [[nodiscard]] Status close() noexcept;

private:
    SessionId id_;
    Tick tick_{};
    SessionState state_{SessionState::ready};
    std::unique_ptr<core::RootState> root_;
};

}  // namespace macro_sim

#endif
