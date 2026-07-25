#ifndef MACRO_SIM_SIMULATION_M7_HPP
#define MACRO_SIM_SIMULATION_M7_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/algorithms/vital_rates.hpp"
#include "macro_sim/core/population.hpp"
#include "macro_sim/simulation/m6.hpp"

namespace macro_sim::simulation {

struct M7PolicyState final {
    double inheritance_tax_rate{0.0};

    bool operator==(const M7PolicyState &) const = default;
};

struct M7Rules final {
    algorithms::VitalRates vital_rates{};
    std::uint32_t working_age{18};
    std::uint32_t retirement_age{65};
    bool beneficial_ownership{true};
    bool estates{true};
    bool fertility{true};
    bool mortality{true};

    bool operator==(const M7Rules &) const = default;
};

struct M7PopulationSpec final {
    std::uint64_t initial_persons{100};
    std::int32_t start_calendar_day{0};
    double target_household_size{2.5};
};

struct M7SimulationSpec final {
    M6SimulationSpec financial_economy{};
    M7PolicyState policy{};
    M7Rules rules{};
    M7PopulationSpec population{};
};

struct EstateRecord final {
    EventId event{};
    PersonId deceased{};
    HouseholdId household{};
    std::int32_t opened_day{0};
    std::int32_t settled_day{0};
    std::uint64_t transferred_lots{0};
    double gross_share{0.0};
    double tax_share{0.0};
    bool settled{false};

    bool operator==(const EstateRecord &) const = default;
};

struct M7Metrics final {
    M6Metrics economy{};
    std::uint64_t population{0};
    std::uint64_t births{0};
    std::uint64_t deaths{0};
    std::uint64_t households_with_members{0};
    double mean_household_size{0.0};
    double working_age_share{0.0};
    double dependency_ratio{0.0};
    std::uint64_t estates_settled{0};
    std::uint64_t beneficial_lots_transferred{0};
    double inheritance_tax_share{0.0};
    double beneficial_projection_error{0.0};

    bool operator==(const M7Metrics &) const = default;
};

struct M7Runtime final {
    M7PolicyState policy{};
    M7Rules rules{};
    std::int32_t start_calendar_day{0};
    std::int32_t current_calendar_day{0};
    core::PersonStore persons{};
    core::HouseholdMembershipBook membership{};
    core::BeneficialOwnershipBook beneficial_ownership{};
    std::vector<EstateRecord> estates;
    std::uint64_t next_event_id{1};
    std::uint64_t population_rng_counter{0};
    M7Metrics last_metrics{};
};

struct M7AdvanceOptions final {
    M6AdvanceOptions base{};
    std::optional<PersonId> force_death{};
    std::optional<PersonId> force_birth{};
    bool fault_before_population_commit{false};
};

struct M7AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M7Metrics metrics{};
    std::uint64_t scratch_capacity_signature{0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};
};

class M7TickScratch final {
  public:
    void reserve(const M7Runtime &runtime);
    [[nodiscard]] std::uint64_t capacity_signature() const noexcept;

    core::PersonStore persons_;
    core::HouseholdMembershipBook membership_;
    core::BeneficialOwnershipBook beneficial_ownership_;
    std::vector<EstateRecord> estates_;
    std::vector<PersonId> opening_alive_;
    std::vector<BeneficialLotId> deceased_lots_;
    std::uint64_t next_event_id_{1};
    std::uint64_t population_rng_counter_{0};
    M7Metrics working_metrics_{};
};

struct M7Initialization final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime financial_runtime;
    M7Runtime runtime;
};

[[nodiscard]] Status
validate_m7_policy(const M7PolicyState &policy) noexcept;
[[nodiscard]] Status validate_m7_rules(const M7Rules &rules) noexcept;
[[nodiscard]] Status
validate_m7_population_spec(const M7PopulationSpec &population) noexcept;
[[nodiscard]] Status validate_m7_spec(const M7SimulationSpec &spec) noexcept;
[[nodiscard]] Status
validate_m7_state(const core::RootState &state,
                  const M4Runtime &real_economy_runtime,
                  const M5Runtime &monetary_runtime,
                  const M6Runtime &financial_runtime,
                  const M7Runtime &runtime, Tick tick) noexcept;
[[nodiscard]] Result<M7Initialization>
build_m7_genesis(const M7SimulationSpec &spec);
[[nodiscard]] Result<M7AdvanceResult>
advance_m7_ticks(core::RootState &state,
                 M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch,
                 M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch,
                 M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch,
                 M7Runtime &runtime, M7TickScratch &scratch, Tick &tick,
                 std::uint64_t count,
                 const M7AdvanceOptions &options = {});

} // namespace macro_sim::simulation

#endif
