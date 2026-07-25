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
#include "macro_sim/simulation/m4.hpp"
#include "macro_sim/simulation/m5.hpp"
#include "macro_sim/simulation/m6.hpp"
#include "macro_sim/simulation/m7.hpp"
#include "macro_sim/simulation/m8.hpp"
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
    EngineSession(const EngineSession &) = delete;
    EngineSession &operator=(const EngineSession &) = delete;
    EngineSession(EngineSession &&) = delete;
    EngineSession &operator=(EngineSession &&) = delete;
    ~EngineSession();

    [[nodiscard]] SessionId id() const noexcept;
    [[nodiscard]] Tick tick() const noexcept;
    [[nodiscard]] SessionState state() const noexcept;
    [[nodiscard]] bool closed() const noexcept;
    [[nodiscard]] bool initialized() const noexcept;
    [[nodiscard]] core::RootState *root() noexcept;
    [[nodiscard]] const core::RootState *root() const noexcept;
    [[nodiscard]] const simulation::M4Runtime *simulation_runtime() const noexcept;
    [[nodiscard]] const simulation::M4TickScratch *tick_scratch() const noexcept;
    [[nodiscard]] const simulation::M5Runtime *monetary_runtime() const noexcept;
    [[nodiscard]] const simulation::M6Runtime *securities_runtime() const noexcept;
    [[nodiscard]] const simulation::M7Runtime *population_runtime() const noexcept;
    [[nodiscard]] const simulation::M8Runtime *housing_runtime() const noexcept;
    [[nodiscard]] Status initialize_m8(const simulation::M8SimulationSpec &spec);
    [[nodiscard]] Status
    update_m8_energy_policy(const simulation::EnergyPolicyState &policy);
    [[nodiscard]] Status
    update_m8_housing_policy(const simulation::HousingPolicyState &policy);
    [[nodiscard]] Result<simulation::M8AdvanceResult>
    advance_m8_ticks(std::uint64_t count, const simulation::M8AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M8AdvanceResult>
    advance_m8_ticks(std::uint64_t count);
    [[nodiscard]] Status initialize_m7(const simulation::M7SimulationSpec &spec);
    [[nodiscard]] Status update_m7_policy(const simulation::M7PolicyState &policy);
    [[nodiscard]] Status update_m7_rules(const simulation::M7Rules &rules);
    [[nodiscard]] Result<simulation::M7AdvanceResult>
    advance_m7_ticks(std::uint64_t count, const simulation::M7AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M7AdvanceResult>
    advance_m7_ticks(std::uint64_t count);
    [[nodiscard]] Status initialize_m6(const simulation::M6SimulationSpec &spec);
    [[nodiscard]] Status update_m6_policy(const simulation::M6PolicyState &policy);
    [[nodiscard]] Result<simulation::M6AdvanceResult>
    advance_m6_ticks(std::uint64_t count, const simulation::M6AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M6AdvanceResult>
    advance_m6_ticks(std::uint64_t count);
    [[nodiscard]] Status initialize_m5(const simulation::M5SimulationSpec &spec);
    [[nodiscard]] Status update_m5_policy(const simulation::M5PolicyState &policy);
    [[nodiscard]] Result<simulation::M5AdvanceResult>
    advance_m5_ticks(std::uint64_t count, const simulation::M5AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M5AdvanceResult>
    advance_m5_ticks(std::uint64_t count);
    [[nodiscard]] Status initialize(const core::GenesisSpec &spec);
    [[nodiscard]] Status
    initialize_simulation(const simulation::M4SimulationSpec &spec);
    [[nodiscard]] Result<simulation::M4AdvanceResult>
    advance_ticks(std::uint64_t count, const simulation::M4AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M4AdvanceResult>
    advance_ticks(std::uint64_t count);
    [[nodiscard]] Result<simulation::M4AdvanceResult>
    advance_tick(const simulation::M4AdvanceOptions &options);
    [[nodiscard]] Result<simulation::M4AdvanceResult> advance_tick();
    [[nodiscard]] Result<core::TransactionReceipt>
    apply(const core::SettlementBatch &batch);
    [[nodiscard]] Result<core::StateDigest> digest() const;
    [[nodiscard]] Result<std::vector<std::uint8_t>> checkpoint() const;
    [[nodiscard]] Status restore_checkpoint(std::span<const std::uint8_t> checkpoint);
    [[nodiscard]] Status close() noexcept;

  private:
    SessionId id_;
    Tick tick_{};
    SessionState state_{SessionState::ready};
    std::unique_ptr<core::RootState> root_;
    std::unique_ptr<simulation::M4Runtime> simulation_runtime_;
    std::unique_ptr<simulation::M4TickScratch> tick_scratch_;
    std::unique_ptr<simulation::M5Runtime> monetary_runtime_;
    std::unique_ptr<simulation::M5TickScratch> monetary_scratch_;
    std::unique_ptr<simulation::M6Runtime> securities_runtime_;
    std::unique_ptr<simulation::M6TickScratch> securities_scratch_;
    std::unique_ptr<simulation::M7Runtime> population_runtime_;
    std::unique_ptr<simulation::M7TickScratch> population_scratch_;
    std::unique_ptr<simulation::M8Runtime> housing_runtime_;
    std::unique_ptr<simulation::M8TickScratch> housing_scratch_;
};

} // namespace macro_sim

#endif
