#ifndef MACRO_SIM_SIMULATION_M7_HPP
#define MACRO_SIM_SIMULATION_M7_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/algorithms/vital_rates.hpp"
#include "macro_sim/core/population.hpp"
#include "macro_sim/core/social_labor.hpp"
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
    bool persistent_labor{true};
    bool fractional_hours{true};
    bool second_jobs{true};
    bool suspensions{true};
    double annual_churn{0.28};
    double firing_adjustment{0.03};
    double layoff_band{0.05};
    double target_smoothing{0.02};
    std::uint32_t suspension_timeout_days{45};
    bool frictional_search{false};
    double search_intensity{0.15};
    bool relationship_wages{true};
    bool job_ladder{true};
    double ladder_search_intensity{0.03};
    double ladder_premium{0.05};
    bool participation_margin{true};
    double reservation_markup{1.0};
    double welfare_quit_hazard{0.02};
    bool family_transfers{false};
    double family_transfer_buffer{1.5};
    bool relationships{true};
    bool marriage{true};
    bool divorce{true};
    bool household_lifecycle{true};
    bool leaving_home{true};
    std::uint32_t leave_home_min_age{22};
    std::uint32_t leave_home_peak_end_age{30};
    double annual_leave_rate_peak{0.25};
    double annual_leave_rate_late{0.05};
    std::uint32_t marriage_interval_days{30};
    double annual_marriage_rate{0.08};
    double annual_divorce_rate{0.02};
    core::MarriageRules marriage_rules{};

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
    PersonId heir{};
    HouseholdId household{};
    HouseholdId destination_household{};
    std::int32_t opened_day{0};
    std::int32_t settled_day{0};
    std::uint64_t transferred_lots{0};
    double gross_share{0.0};
    double tax_share{0.0};
    double gross_value{0.0};
    double liabilities{0.0};
    double tax_paid{0.0};
    bool public_residual{false};
    bool settled{false};

    bool operator==(const EstateRecord &) const = default;
};

struct LeavingHomeRecord final {
    EventId event{};
    PersonId person{};
    HouseholdId origin{};
    HouseholdId destination{};
    std::int32_t day{0};

    bool operator==(const LeavingHomeRecord &) const = default;
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
    double participation_rate{0.0};
    std::uint64_t estates_settled{0};
    std::uint64_t beneficial_lots_transferred{0};
    double inheritance_tax_share{0.0};
    double inheritance_tax_paid{0.0};
    double beneficial_projection_error{0.0};
    double employed_fte{0.0};
    double employed_heads{0.0};
    double unemployment{0.0};
    double unemployment_rate{0.0};
    double suspended{0.0};
    double job_guarantee{0.0};
    double out_of_labor_force{0.0};
    double labor_supply{0.0};
    double vacancies{0.0};
    double underemployed_heads{0.0};
    double underemployment_hours{0.0};
    double suspended_memo{0.0};
    double second_job_heads{0.0};
    double second_job_hours{0.0};
    double nonsearching{0.0};
    double job_to_job_moves{0.0};
    double mean_hourly_wage{0.0};
    double family_transfer_total{0.0};
    double family_transfer_recipients{0.0};
    double family_exposed_households{0.0};
    double hires{0.0};
    double separations{0.0};
    std::uint64_t marriages{0};
    std::uint64_t divorces{0};
    std::uint64_t widowhoods{0};
    std::uint64_t leaving_home_events{0};

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
    core::EmploymentBook employment{};
    core::RelationshipBook relationships{};
    core::LaborAccounts labor_accounts{};
    std::vector<double> firm_target_ema;
    std::vector<EstateRecord> estates;
    std::vector<LeavingHomeRecord> leaving_home;
    std::uint64_t next_event_id{1};
    std::uint64_t population_rng_counter{0};
    M7Metrics last_metrics{};
};

struct M7AdvanceOptions final {
    M6AdvanceOptions base{};
    std::optional<PersonId> force_death{};
    std::optional<PersonId> force_birth{};
    std::optional<PersonId> force_leave_home{};
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
    core::EmploymentBook employment_;
    core::RelationshipBook relationships_;
    core::LaborAccounts labor_accounts_{};
    std::vector<double> firm_target_ema_;
    std::vector<EstateRecord> estates_;
    std::vector<LeavingHomeRecord> leaving_home_;
    std::vector<LeavingHomeRecord> pending_leaving_home_;
    std::vector<PersonId> opening_alive_;
    std::vector<std::uint32_t> guardian_heads_;
    std::vector<std::uint32_t> guardian_next_;
    std::vector<BeneficialLotId> deceased_lots_;
    std::vector<core::BeneficialAssetKey> beneficial_assets_;
    std::vector<core::SecurityId> estate_securities_;
    std::vector<PersonId> labor_candidates_;
    std::vector<PersonId> second_job_candidates_;
    std::vector<PersonId> ladder_candidates_;
    std::vector<FirmId> ladder_firms_;
    std::vector<PersonId> divorce_candidates_;
    std::vector<PersonId> fertility_candidates_;
    std::vector<HouseholdId> kin_households_;
    std::vector<HouseholdId> retired_households_;
    std::vector<std::size_t> household_work_index_;
    std::vector<JobId> roster_buffer_;
    double external_leave_home_multiplier_{1.0};
    double external_fertility_multiplier_{1.0};
    std::uint64_t next_event_id_{1};
    std::uint64_t population_rng_counter_{0};
    M7Metrics working_metrics_{};
};

class M7TickExtension {
  public:
    M7TickExtension() = default;
    M7TickExtension(const M7TickExtension &) = delete;
    M7TickExtension &operator=(const M7TickExtension &) = delete;
    virtual ~M7TickExtension() = default;

    [[nodiscard]] virtual Status
    prepare_tick(const core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch, M7Runtime &runtime,
                 M7TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    before_labor(const core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch, M7Runtime &runtime,
                 M7TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    after_labor(const core::RootState &state, M4Runtime &real_economy_runtime,
                M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                M6TickScratch &financial_scratch, M7Runtime &runtime,
                M7TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    close_day(const core::RootState &state, M4Runtime &real_economy_runtime,
              M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
              M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
              M6TickScratch &financial_scratch, M7Runtime &runtime,
              M7TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    validate(const core::RootState &state, const M4Runtime &real_economy_runtime,
             const M4TickScratch &real_economy_scratch,
             const M5Runtime &monetary_runtime, const M5TickScratch &monetary_scratch,
             const M6Runtime &financial_runtime, const M6TickScratch &financial_scratch,
             const M7Runtime &runtime, const M7TickScratch &scratch,
             Tick tick) const = 0;
    virtual void commit(core::RootState &state, M4Runtime &real_economy_runtime,
                        M4TickScratch &real_economy_scratch,
                        M5Runtime &monetary_runtime, M5TickScratch &monetary_scratch,
                        M6Runtime &financial_runtime, M6TickScratch &financial_scratch,
                        M7Runtime &runtime, M7TickScratch &scratch, Tick tick,
                        const M7Metrics &metrics) noexcept = 0;
};

struct M7Initialization final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime financial_runtime;
    M7Runtime runtime;
};

[[nodiscard]] Status validate_m7_policy(const M7PolicyState &policy) noexcept;
[[nodiscard]] Status validate_m7_rules(const M7Rules &rules) noexcept;
[[nodiscard]] Status
validate_m7_population_spec(const M7PopulationSpec &population) noexcept;
[[nodiscard]] Status validate_m7_spec(const M7SimulationSpec &spec) noexcept;
[[nodiscard]] Status validate_m7_state(const core::RootState &state,
                                       const M4Runtime &real_economy_runtime,
                                       const M5Runtime &monetary_runtime,
                                       const M6Runtime &financial_runtime,
                                       const M7Runtime &runtime, Tick tick) noexcept;
[[nodiscard]] Result<M7Initialization> build_m7_genesis(const M7SimulationSpec &spec);
[[nodiscard]] Result<M7AdvanceResult>
advance_m7_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch, M7Runtime &runtime,
                 M7TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M7AdvanceOptions &options = {});
[[nodiscard]] Result<M7AdvanceResult> advance_m7_ticks_extended(
    core::RootState &state, M4Runtime &real_economy_runtime,
    M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
    M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
    M6TickScratch &financial_scratch, M7Runtime &runtime, M7TickScratch &scratch,
    Tick &tick, std::uint64_t count, M7TickExtension &extension,
    const M7AdvanceOptions &options = {});

} // namespace macro_sim::simulation

#endif
