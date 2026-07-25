#include "macro_sim/engine_session.hpp"

#include <new>
#include <utility>

#include "macro_sim/simulation/m4.hpp"
#include "macro_sim/simulation/m4_checkpoint.hpp"
#include "macro_sim/simulation/m5.hpp"
#include "macro_sim/simulation/m5_checkpoint.hpp"
#include "macro_sim/simulation/m6.hpp"
#include "macro_sim/simulation/m6_checkpoint.hpp"
#include "macro_sim/simulation/m7.hpp"
#include "macro_sim/simulation/m7_checkpoint.hpp"

namespace macro_sim {

EngineSession::EngineSession(EngineSessionOptions options) noexcept
    : id_(options.session_id) {}

EngineSession::EngineSession(std::uint64_t session_id) noexcept
    : EngineSession(EngineSessionOptions{SessionId(session_id)}) {}

EngineSession::~EngineSession() = default;

SessionId EngineSession::id() const noexcept { return id_; }

Tick EngineSession::tick() const noexcept { return tick_; }

SessionState EngineSession::state() const noexcept { return state_; }

bool EngineSession::closed() const noexcept { return state_ == SessionState::closed; }

bool EngineSession::initialized() const noexcept { return root_ != nullptr; }

core::RootState *EngineSession::root() noexcept { return root_.get(); }

const core::RootState *EngineSession::root() const noexcept { return root_.get(); }

const simulation::M4Runtime *EngineSession::simulation_runtime() const noexcept {
    return simulation_runtime_.get();
}

const simulation::M4TickScratch *EngineSession::tick_scratch() const noexcept {
    return tick_scratch_.get();
}

const simulation::M5Runtime *EngineSession::monetary_runtime() const noexcept {
    return monetary_runtime_.get();
}

const simulation::M6Runtime *EngineSession::securities_runtime() const noexcept {
    return securities_runtime_.get();
}

const simulation::M7Runtime *
EngineSession::population_runtime() const noexcept {
    return population_runtime_.get();
}

Status EngineSession::initialize_m7(
    const simulation::M7SimulationSpec &spec
) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(ErrorCode::already_exists,
                      "session already has canonical state");
    }
    try {
        auto initialization = simulation::build_m7_genesis(spec);
        if (!initialization.ok()) {
            return initialization.status();
        }
        auto *value = initialization.get_if();
        auto root =
            std::make_unique<core::RootState>(std::move(value->root));
        auto real = std::make_unique<simulation::M4Runtime>(
            std::move(value->real_economy_runtime)
        );
        auto monetary = std::make_unique<simulation::M5Runtime>(
            std::move(value->monetary_runtime)
        );
        auto financial = std::make_unique<simulation::M6Runtime>(
            std::move(value->financial_runtime)
        );
        auto population = std::make_unique<simulation::M7Runtime>(
            std::move(value->runtime)
        );
        auto real_scratch =
            std::make_unique<simulation::M4TickScratch>();
        auto monetary_scratch =
            std::make_unique<simulation::M5TickScratch>();
        auto financial_scratch =
            std::make_unique<simulation::M6TickScratch>();
        auto population_scratch =
            std::make_unique<simulation::M7TickScratch>();
        real_scratch->reserve(*root);
        monetary_scratch->reserve(*root);
        financial_scratch->reserve(*root, *financial);
        population_scratch->reserve(*population);
        root_ = std::move(root);
        simulation_runtime_ = std::move(real);
        tick_scratch_ = std::move(real_scratch);
        monetary_runtime_ = std::move(monetary);
        monetary_scratch_ = std::move(monetary_scratch);
        securities_runtime_ = std::move(financial);
        securities_scratch_ = std::move(financial_scratch);
        population_runtime_ = std::move(population);
        population_scratch_ = std::move(population_scratch);
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(
            ErrorCode::allocation_failure,
            "M7 simulation genesis allocation failed"
        );
    } catch (...) {
        return Status(ErrorCode::internal_error,
                      "M7 simulation genesis failed");
    }
}

Status EngineSession::update_m7_policy(
    const simulation::M7PolicyState &policy
) {
    if (closed() || population_runtime_ == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active M7 simulation");
    }
    const auto validated = simulation::validate_m7_policy(policy);
    if (!validated.ok()) {
        return validated;
    }
    population_runtime_->policy = policy;
    return Status::success();
}

Status EngineSession::update_m7_rules(const simulation::M7Rules &rules) {
    if (closed() || population_runtime_ == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active M7 simulation");
    }
    const auto validated = simulation::validate_m7_rules(rules);
    if (!validated.ok()) {
        return validated;
    }
    population_runtime_->rules = rules;
    return Status::success();
}

Result<simulation::M7AdvanceResult>
EngineSession::advance_m7_ticks(
    std::uint64_t count,
    const simulation::M7AdvanceOptions &options
) {
    if (closed() || !initialized() ||
        simulation_runtime_ == nullptr ||
        tick_scratch_ == nullptr ||
        monetary_runtime_ == nullptr ||
        monetary_scratch_ == nullptr ||
        securities_runtime_ == nullptr ||
        securities_scratch_ == nullptr ||
        population_runtime_ == nullptr ||
        population_scratch_ == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active M7 simulation");
    }
    try {
        return simulation::advance_m7_ticks(
            *root_, *simulation_runtime_, *tick_scratch_,
            *monetary_runtime_, *monetary_scratch_,
            *securities_runtime_, *securities_scratch_,
            *population_runtime_, *population_scratch_, tick_,
            count, options
        );
    } catch (const std::bad_alloc &) {
        return Status(
            ErrorCode::allocation_failure,
            "M7 tick execution allocation failed"
        );
    } catch (...) {
        return Status(ErrorCode::internal_error,
                      "M7 tick execution failed");
    }
}

Result<simulation::M7AdvanceResult>
EngineSession::advance_m7_ticks(std::uint64_t count) {
    return advance_m7_ticks(count, simulation::M7AdvanceOptions{});
}

Status EngineSession::initialize(const core::GenesisSpec &spec) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(ErrorCode::already_exists, "session already has canonical state");
    }
    try {
        auto state = core::build_genesis(spec);
        if (!state.ok()) {
            return state.status();
        }
        root_ = std::make_unique<core::RootState>(std::move(*state.get_if()));
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "session genesis allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "session genesis failed");
    }
}

Status EngineSession::initialize_simulation(const simulation::M4SimulationSpec &spec) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(ErrorCode::already_exists, "session already has canonical state");
    }
    try {
        auto initialization = simulation::build_m4_genesis(spec);
        if (!initialization.ok()) {
            return initialization.status();
        }
        auto *value = initialization.get_if();
        auto root = std::make_unique<core::RootState>(std::move(value->root));
        auto runtime =
            std::make_unique<simulation::M4Runtime>(std::move(value->runtime));
        auto scratch = std::make_unique<simulation::M4TickScratch>();
        scratch->reserve(*root);
        root_ = std::move(root);
        simulation_runtime_ = std::move(runtime);
        tick_scratch_ = std::move(scratch);
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "simulation genesis allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "simulation genesis failed");
    }
}

Status EngineSession::initialize_m5(const simulation::M5SimulationSpec &spec) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(ErrorCode::already_exists, "session already has canonical state");
    }
    try {
        auto initialization = simulation::build_m5_genesis(spec);
        if (!initialization.ok()) {
            return initialization.status();
        }
        auto *value = initialization.get_if();
        auto root = std::make_unique<core::RootState>(std::move(value->root));
        auto real_economy = std::make_unique<simulation::M4Runtime>(
            std::move(value->real_economy_runtime));
        auto monetary =
            std::make_unique<simulation::M5Runtime>(std::move(value->runtime));
        auto real_scratch = std::make_unique<simulation::M4TickScratch>();
        auto monetary_scratch = std::make_unique<simulation::M5TickScratch>();
        real_scratch->reserve(*root);
        monetary_scratch->reserve(*root);
        root_ = std::move(root);
        simulation_runtime_ = std::move(real_economy);
        tick_scratch_ = std::move(real_scratch);
        monetary_runtime_ = std::move(monetary);
        monetary_scratch_ = std::move(monetary_scratch);
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M5 simulation genesis allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "M5 simulation genesis failed");
    }
}

Status EngineSession::initialize_m6(const simulation::M6SimulationSpec &spec) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (initialized()) {
        return Status(ErrorCode::already_exists, "session already has canonical state");
    }
    try {
        auto initialization = simulation::build_m6_genesis(spec);
        if (!initialization.ok()) {
            return initialization.status();
        }
        auto *value = initialization.get_if();
        auto root = std::make_unique<core::RootState>(std::move(value->root));
        auto real_economy = std::make_unique<simulation::M4Runtime>(
            std::move(value->real_economy_runtime));
        auto monetary =
            std::make_unique<simulation::M5Runtime>(std::move(value->monetary_runtime));
        auto securities =
            std::make_unique<simulation::M6Runtime>(std::move(value->runtime));
        auto real_scratch = std::make_unique<simulation::M4TickScratch>();
        auto monetary_scratch = std::make_unique<simulation::M5TickScratch>();
        auto securities_scratch = std::make_unique<simulation::M6TickScratch>();
        real_scratch->reserve(*root);
        monetary_scratch->reserve(*root);
        securities_scratch->reserve(*root, *securities);
        root_ = std::move(root);
        simulation_runtime_ = std::move(real_economy);
        tick_scratch_ = std::move(real_scratch);
        monetary_runtime_ = std::move(monetary);
        monetary_scratch_ = std::move(monetary_scratch);
        securities_runtime_ = std::move(securities);
        securities_scratch_ = std::move(securities_scratch);
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M6 simulation genesis allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "M6 simulation genesis failed");
    }
}

Status EngineSession::update_m6_policy(const simulation::M6PolicyState &policy) {
    if (closed() || securities_runtime_ == nullptr) {
        return Status(ErrorCode::invalid_handle, "session has no active M6 simulation");
    }
    const auto validated = simulation::validate_m6_policy(policy);
    if (!validated.ok()) {
        return validated;
    }
    securities_runtime_->policy = policy;
    return Status::success();
}

Result<simulation::M6AdvanceResult>
EngineSession::advance_m6_ticks(std::uint64_t count,
                                const simulation::M6AdvanceOptions &options) {
    if (closed() || !initialized() || simulation_runtime_ == nullptr ||
        tick_scratch_ == nullptr || monetary_runtime_ == nullptr ||
        monetary_scratch_ == nullptr || securities_runtime_ == nullptr ||
        securities_scratch_ == nullptr ||
        population_runtime_ != nullptr) {
        return Status(ErrorCode::invalid_handle, "session has no active M6 simulation");
    }
    try {
        return simulation::advance_m6_ticks(
            *root_, *simulation_runtime_, *tick_scratch_, *monetary_runtime_,
            *monetary_scratch_, *securities_runtime_, *securities_scratch_, tick_,
            count, options);
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M6 tick execution allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "M6 tick execution failed");
    }
}

Result<simulation::M6AdvanceResult>
EngineSession::advance_m6_ticks(std::uint64_t count) {
    return advance_m6_ticks(count, simulation::M6AdvanceOptions{});
}

Status EngineSession::update_m5_policy(const simulation::M5PolicyState &policy) {
    if (closed() || monetary_runtime_ == nullptr) {
        return Status(ErrorCode::invalid_handle, "session has no active M5 simulation");
    }
    const auto validated = simulation::validate_m5_policy(policy);
    if (!validated.ok()) {
        return validated;
    }
    monetary_runtime_->policy = policy;
    return Status::success();
}

Result<simulation::M5AdvanceResult>
EngineSession::advance_m5_ticks(std::uint64_t count,
                                const simulation::M5AdvanceOptions &options) {
    if (closed() || !initialized() || simulation_runtime_ == nullptr ||
        tick_scratch_ == nullptr || monetary_runtime_ == nullptr ||
        monetary_scratch_ == nullptr || securities_runtime_ != nullptr) {
        return Status(ErrorCode::invalid_handle, "session has no active M5 simulation");
    }
    try {
        return simulation::advance_m5_ticks(*root_, *simulation_runtime_,
                                            *tick_scratch_, *monetary_runtime_,
                                            *monetary_scratch_, tick_, count, options);
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "M5 tick execution allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "M5 tick execution failed");
    }
}

Result<simulation::M5AdvanceResult>
EngineSession::advance_m5_ticks(std::uint64_t count) {
    return advance_m5_ticks(count, simulation::M5AdvanceOptions{});
}

Result<simulation::M4AdvanceResult>
EngineSession::advance_ticks(std::uint64_t count,
                             const simulation::M4AdvanceOptions &options) {
    if (closed() || !initialized() || simulation_runtime_ == nullptr ||
        tick_scratch_ == nullptr || monetary_runtime_ != nullptr ||
        securities_runtime_ != nullptr) {
        return Status(ErrorCode::invalid_handle, "session has no active simulation");
    }
    try {
        return simulation::advance_ticks(*root_, *simulation_runtime_, *tick_scratch_,
                                         tick_, count, options);
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "tick execution allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "tick execution failed");
    }
}

Result<simulation::M4AdvanceResult> EngineSession::advance_ticks(std::uint64_t count) {
    return advance_ticks(count, simulation::M4AdvanceOptions{});
}

Result<simulation::M4AdvanceResult>
EngineSession::advance_tick(const simulation::M4AdvanceOptions &options) {
    return advance_ticks(1, options);
}

Result<simulation::M4AdvanceResult> EngineSession::advance_tick() {
    return advance_ticks(1);
}

Result<core::TransactionReceipt>
EngineSession::apply(const core::SettlementBatch &batch) {
    if (closed() || !initialized()) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active canonical state");
    }
    if (simulation_runtime_ != nullptr) {
        return Status(
            ErrorCode::unsupported,
            "direct accounting batches are outside the M4 simulation boundary");
    }
    try {
        core::SettlementTransaction transaction(*root_);
        const auto appended = transaction.append(batch);
        if (!appended.ok()) {
            return appended;
        }
        return transaction.commit();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure, "batch allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "batch execution failed");
    }
}

Result<core::StateDigest> EngineSession::digest() const {
    if (closed() || !initialized()) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active canonical state");
    }
    if (securities_runtime_ != nullptr) {
        if (population_runtime_ != nullptr) {
            return simulation::m7_state_digest(
                *root_, *simulation_runtime_, *monetary_runtime_,
                *securities_runtime_, *population_runtime_, tick_
            );
        }
        return simulation::m6_state_digest(*root_, *simulation_runtime_,
                                           *monetary_runtime_, *securities_runtime_,
                                           tick_);
    }
    if (monetary_runtime_ != nullptr) {
        auto encoded = simulation::save_m5_checkpoint(*root_, *simulation_runtime_,
                                                      *monetary_runtime_, tick_);
        if (!encoded.ok()) {
            return encoded.status();
        }
        return core::sha256_digest(*encoded.get_if());
    }
    if (simulation_runtime_ != nullptr) {
        auto encoded =
            simulation::save_m4_checkpoint(*root_, *simulation_runtime_, tick_);
        if (!encoded.ok()) {
            return encoded.status();
        }
        return core::sha256_digest(*encoded.get_if());
    }
    return core::state_digest(*root_);
}

Result<std::vector<std::uint8_t>> EngineSession::checkpoint() const {
    if (closed() || !initialized()) {
        return Status(ErrorCode::invalid_handle,
                      "session has no active canonical state");
    }
    if (securities_runtime_ != nullptr) {
        if (population_runtime_ != nullptr) {
            return simulation::save_m7_checkpoint(
                *root_, *simulation_runtime_, *monetary_runtime_,
                *securities_runtime_, *population_runtime_, tick_
            );
        }
        return simulation::save_m6_checkpoint(*root_, *simulation_runtime_,
                                              *monetary_runtime_, *securities_runtime_,
                                              tick_);
    }
    if (monetary_runtime_ != nullptr) {
        return simulation::save_m5_checkpoint(*root_, *simulation_runtime_,
                                              *monetary_runtime_, tick_);
    }
    if (simulation_runtime_ != nullptr) {
        return simulation::save_m4_checkpoint(*root_, *simulation_runtime_, tick_);
    }
    return core::save_checkpoint(*root_);
}

Status EngineSession::restore_checkpoint(std::span<const std::uint8_t> checkpoint) {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is closed");
    }
    if (simulation::is_m7_checkpoint(checkpoint)) {
        auto loaded = simulation::load_m7_checkpoint(checkpoint);
        if (!loaded.ok()) {
            return loaded.status();
        }
        try {
            auto *value = loaded.get_if();
            auto replacement =
                std::make_unique<core::RootState>(
                    std::move(value->root)
                );
            auto real = std::make_unique<simulation::M4Runtime>(
                std::move(value->real_economy_runtime)
            );
            auto monetary = std::make_unique<simulation::M5Runtime>(
                std::move(value->monetary_runtime)
            );
            auto financial = std::make_unique<simulation::M6Runtime>(
                std::move(value->financial_runtime)
            );
            auto population = std::make_unique<simulation::M7Runtime>(
                std::move(value->runtime)
            );
            auto real_scratch =
                std::make_unique<simulation::M4TickScratch>();
            auto monetary_scratch =
                std::make_unique<simulation::M5TickScratch>();
            auto financial_scratch =
                std::make_unique<simulation::M6TickScratch>();
            auto population_scratch =
                std::make_unique<simulation::M7TickScratch>();
            real_scratch->reserve(*replacement);
            monetary_scratch->reserve(*replacement);
            financial_scratch->reserve(*replacement, *financial);
            population_scratch->reserve(*population);
            root_ = std::move(replacement);
            simulation_runtime_ = std::move(real);
            tick_scratch_ = std::move(real_scratch);
            monetary_runtime_ = std::move(monetary);
            monetary_scratch_ = std::move(monetary_scratch);
            securities_runtime_ = std::move(financial);
            securities_scratch_ = std::move(financial_scratch);
            population_runtime_ = std::move(population);
            population_scratch_ = std::move(population_scratch);
            tick_ = value->tick;
            return Status::success();
        } catch (const std::bad_alloc &) {
            return Status(
                ErrorCode::allocation_failure,
                "M7 checkpoint restore allocation failed"
            );
        } catch (...) {
            return Status(ErrorCode::internal_error,
                          "M7 checkpoint restore failed");
        }
    }
    if (simulation::is_m6_checkpoint(checkpoint)) {
        auto loaded = simulation::load_m6_checkpoint(checkpoint);
        if (!loaded.ok()) {
            return loaded.status();
        }
        try {
            auto *value = loaded.get_if();
            auto replacement =
                std::make_unique<core::RootState>(std::move(value->root));
            auto real_economy = std::make_unique<simulation::M4Runtime>(
                std::move(value->real_economy_runtime));
            auto monetary = std::make_unique<simulation::M5Runtime>(
                std::move(value->monetary_runtime));
            auto securities =
                std::make_unique<simulation::M6Runtime>(std::move(value->runtime));
            auto real_scratch = std::make_unique<simulation::M4TickScratch>();
            auto monetary_scratch = std::make_unique<simulation::M5TickScratch>();
            auto securities_scratch = std::make_unique<simulation::M6TickScratch>();
            real_scratch->reserve(*replacement);
            monetary_scratch->reserve(*replacement);
            securities_scratch->reserve(*replacement, *securities);
            root_ = std::move(replacement);
            simulation_runtime_ = std::move(real_economy);
            tick_scratch_ = std::move(real_scratch);
            monetary_runtime_ = std::move(monetary);
            monetary_scratch_ = std::move(monetary_scratch);
            securities_runtime_ = std::move(securities);
            securities_scratch_ = std::move(securities_scratch);
            population_runtime_.reset();
            population_scratch_.reset();
            tick_ = value->tick;
            return Status::success();
        } catch (const std::bad_alloc &) {
            return Status(ErrorCode::allocation_failure,
                          "M6 checkpoint restore allocation failed");
        } catch (...) {
            return Status(ErrorCode::internal_error, "M6 checkpoint restore failed");
        }
    }
    if (simulation::is_m5_checkpoint(checkpoint)) {
        auto loaded = simulation::load_m5_checkpoint(checkpoint);
        if (!loaded.ok()) {
            return loaded.status();
        }
        try {
            auto *value = loaded.get_if();
            auto replacement =
                std::make_unique<core::RootState>(std::move(value->root));
            auto real_economy = std::make_unique<simulation::M4Runtime>(
                std::move(value->real_economy_runtime));
            auto monetary =
                std::make_unique<simulation::M5Runtime>(std::move(value->runtime));
            auto real_scratch = std::make_unique<simulation::M4TickScratch>();
            auto monetary_scratch = std::make_unique<simulation::M5TickScratch>();
            real_scratch->reserve(*replacement);
            monetary_scratch->reserve(*replacement);
            root_ = std::move(replacement);
            simulation_runtime_ = std::move(real_economy);
            tick_scratch_ = std::move(real_scratch);
            monetary_runtime_ = std::move(monetary);
            monetary_scratch_ = std::move(monetary_scratch);
            securities_runtime_.reset();
            securities_scratch_.reset();
            population_runtime_.reset();
            population_scratch_.reset();
            tick_ = value->tick;
            return Status::success();
        } catch (const std::bad_alloc &) {
            return Status(ErrorCode::allocation_failure,
                          "M5 checkpoint restore allocation failed");
        } catch (...) {
            return Status(ErrorCode::internal_error, "M5 checkpoint restore failed");
        }
    }
    if (simulation::is_m4_checkpoint(checkpoint)) {
        auto loaded = simulation::load_m4_checkpoint(checkpoint);
        if (!loaded.ok()) {
            return loaded.status();
        }
        try {
            auto *value = loaded.get_if();
            auto replacement =
                std::make_unique<core::RootState>(std::move(value->root));
            auto runtime =
                std::make_unique<simulation::M4Runtime>(std::move(value->runtime));
            auto scratch = std::make_unique<simulation::M4TickScratch>();
            scratch->reserve(*replacement);
            root_ = std::move(replacement);
            simulation_runtime_ = std::move(runtime);
            tick_scratch_ = std::move(scratch);
            monetary_runtime_.reset();
            monetary_scratch_.reset();
            securities_runtime_.reset();
            securities_scratch_.reset();
            population_runtime_.reset();
            population_scratch_.reset();
            tick_ = value->tick;
            return Status::success();
        } catch (const std::bad_alloc &) {
            return Status(ErrorCode::allocation_failure,
                          "M4 checkpoint restore allocation failed");
        } catch (...) {
            return Status(ErrorCode::internal_error, "M4 checkpoint restore failed");
        }
    }
    auto state = core::load_checkpoint(checkpoint);
    if (!state.ok()) {
        return state.status();
    }
    try {
        auto replacement =
            std::make_unique<core::RootState>(std::move(*state.get_if()));
        root_ = std::move(replacement);
        simulation_runtime_.reset();
        tick_scratch_.reset();
        monetary_runtime_.reset();
        monetary_scratch_.reset();
        securities_runtime_.reset();
        securities_scratch_.reset();
        population_runtime_.reset();
        population_scratch_.reset();
        tick_ = Tick(0);
        return Status::success();
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure,
                      "checkpoint restore allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "checkpoint restore failed");
    }
}

Status EngineSession::close() noexcept {
    if (closed()) {
        return Status(ErrorCode::invalid_handle, "session is already closed");
    }
    root_.reset();
    simulation_runtime_.reset();
    tick_scratch_.reset();
    monetary_runtime_.reset();
    monetary_scratch_.reset();
    securities_runtime_.reset();
    securities_scratch_.reset();
    population_runtime_.reset();
    population_scratch_.reset();
    state_ = SessionState::closed;
    return Status::success();
}

} // namespace macro_sim
