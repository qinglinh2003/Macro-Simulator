#ifndef MACRO_SIM_CORE_SOCIAL_LABOR_HPP
#define MACRO_SIM_CORE_SOCIAL_LABOR_HPP

#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <vector>

#include "macro_sim/core/population.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"

namespace macro_sim::core {

enum class UnionEndKind : std::uint8_t {
    active = 0,
    divorce = 1,
    widowhood = 2,
};

struct UnionRecord final {
    EventId event{};
    PersonId first{};
    PersonId second{};
    HouseholdId first_origin_household{};
    HouseholdId second_origin_household{};
    std::int32_t start_day{0};
    std::int32_t end_day{-1};
    UnionEndKind end_kind{UnionEndKind::active};
    bool active{true};

    bool operator==(const UnionRecord &) const = default;
};

struct MarriageRules final {
    std::uint32_t minimum_age{18};
    std::uint32_t maximum_age{80};
    std::uint32_t maximum_age_gap{20};
    double preferred_age_gap{0.0};
    double age_gap_penalty{1.0};
    double assortativity{0.25};
    bool forbid_same_household{true};
    bool forbid_close_kin{true};

    bool operator==(const MarriageRules &) const = default;
};

struct MarriageMatch final {
    PersonId first{};
    PersonId second{};
    double score{0.0};

    bool operator==(const MarriageMatch &) const = default;
};

class RelationshipBook final {
  public:
    [[nodiscard]] Status marry(PersonStore &persons, EventId event,
                               PersonId first, PersonId second,
                               std::int32_t day);
    [[nodiscard]] Status divorce(PersonStore &persons, PersonId person,
                                 std::int32_t day);
    [[nodiscard]] Status widow(PersonStore &persons, PersonId deceased,
                               std::int32_t day);
    [[nodiscard]] Status register_birth(const PersonStore &persons,
                                        PersonId child);

    [[nodiscard]] EventId active_union(PersonId person) const noexcept;
    [[nodiscard]] std::span<const PersonId>
    children(PersonId parent) const;
    [[nodiscard]] const std::vector<UnionRecord> &unions() const noexcept;
    [[nodiscard]] std::uint64_t retained_bytes() const noexcept;
    [[nodiscard]] Status
    replace_unions(const PersonStore &persons,
                   std::vector<UnionRecord> unions);
    [[nodiscard]] Status validate(const PersonStore &persons) const;

  private:
    struct ChildLink final {
        PersonId child{};
        std::uint32_t previous{0U};
    };

    void ensure_person(PersonId person);
    [[nodiscard]] Status append_child(PersonId parent, PersonId child);
    [[nodiscard]] UnionRecord *get(EventId event) noexcept;
    [[nodiscard]] const UnionRecord *get(EventId event) const noexcept;

    std::vector<UnionRecord> unions_;
    std::vector<EventId> active_union_by_person_{EventId{}};
    std::vector<std::uint32_t> child_head_by_parent_{0U};
    std::vector<ChildLink> child_links_;
    mutable std::vector<PersonId> child_query_;
};

[[nodiscard]] Result<std::vector<MarriageMatch>>
exact_marriage_matches(const PersonStore &persons,
                       const HouseholdMembershipBook &membership,
                       const MarriageRules &rules,
                       std::int32_t day);

enum class SeparationKind : std::uint8_t {
    churn = 0,
    demand_layoff = 1,
    cash_layoff = 2,
    firm_exit = 3,
    death = 4,
    retirement = 5,
    welfare_quit = 6,
    job_to_job = 7,
};

struct JobRecord final {
    JobId id{};
    PersonId person{};
    FirmId firm{};
    std::int32_t hire_day{0};
    std::int32_t separation_day{-1};
    std::int32_t suspension_day{-1};
    double wage{0.0};
    double hours{1.0};
    bool secondary{false};
    bool suspended{false};
    bool active{true};
    SeparationKind separation_kind{SeparationKind::churn};

    bool operator==(const JobRecord &) const = default;
};

class EmploymentBook final {
  public:
    [[nodiscard]] Result<JobId> hire(PersonId person, FirmId firm,
                                     std::int32_t day, double wage,
                                     double hours, bool secondary = false);
    [[nodiscard]] Status separate(JobId job, std::int32_t day,
                                  SeparationKind kind);
    [[nodiscard]] Status suspend(JobId job, std::int32_t day);
    [[nodiscard]] Status recall(JobId job);
    [[nodiscard]] Status set_hours(JobId job, double hours);
    [[nodiscard]] Status set_wage(JobId job, double wage);
    [[nodiscard]] Status promote_secondary(PersonId person);

    [[nodiscard]] JobRecord *get(JobId id) noexcept;
    [[nodiscard]] const JobRecord *get(JobId id) const noexcept;
    [[nodiscard]] JobId primary_job(PersonId person) const noexcept;
    [[nodiscard]] JobId secondary_job(PersonId person) const noexcept;
    [[nodiscard]] std::span<const JobId>
    roster(FirmId firm) const noexcept;
    [[nodiscard]] const std::vector<std::vector<JobId>> &
    firm_rosters() const noexcept;
    [[nodiscard]] const std::vector<JobRecord> &records() const noexcept;
    [[nodiscard]] Status
    replace_records(std::vector<JobRecord> records);
    [[nodiscard]] Status
    restore_firm_rosters(std::vector<std::vector<JobId>> rosters);
    [[nodiscard]] std::uint64_t next_id() const noexcept;
    [[nodiscard]] std::size_t active_count() const noexcept;
    [[nodiscard]] std::size_t suspended_count() const noexcept;
    [[nodiscard]] Status compact_inactive();
    [[nodiscard]] std::uint64_t retained_bytes() const noexcept;
    [[nodiscard]] double active_hours(PersonId person) const noexcept;
    [[nodiscard]] double active_hours(FirmId firm) const noexcept;
    [[nodiscard]] Status validate(const PersonStore &persons,
                                  const RootState &state,
                                  double tolerance) const;

  private:
    static constexpr std::uint32_t kNoRoster =
        std::numeric_limits<std::uint32_t>::max();

    void ensure_person(PersonId person);
    void ensure_firm(FirmId firm);

    std::vector<JobRecord> jobs_{JobRecord{}};
    std::vector<JobId> primary_by_person_{JobId{}};
    std::vector<JobId> secondary_by_person_{JobId{}};
    std::vector<std::vector<JobId>> roster_by_firm_{
        std::vector<JobId>{}};
    std::vector<std::uint32_t> roster_position_by_job_{kNoRoster};
    std::uint64_t next_id_{1};
    std::size_t active_count_{0};
    std::size_t suspended_count_{0};
};

struct LaborAccounts final {
    double employed_fte{0.0};
    double employed_heads{0.0};
    double unemployed{0.0};
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
    double hires_total{0.0};
    double churn_separations_total{0.0};
    double layoff_separations_total{0.0};
    double cash_layoffs_total{0.0};
    double firm_exit_separations_total{0.0};
    double death_separations_total{0.0};
    double retirement_separations_total{0.0};
    double recalls_total{0.0};
    double suspensions_total{0.0};
    double welfare_quits_total{0.0};
    double job_to_job_moves_total{0.0};
    double private_fte_inflows_total{0.0};
    double private_fte_outflows_total{0.0};
    double previous_employed_fte{-1.0};
    double previous_fte_flow_balance{0.0};
    double previous_employed_heads{-1.0};
    double previous_head_flow_balance{0.0};

    bool operator==(const LaborAccounts &) const = default;
};

[[nodiscard]] Status validate_labor_accounts(
    const LaborAccounts &accounts,
    double tolerance
) noexcept;

} // namespace macro_sim::core

#endif
