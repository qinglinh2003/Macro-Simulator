#include "macro_sim/simulation/m7.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numeric>
#include <utility>

namespace macro_sim::simulation {
namespace {

constexpr double kDaysPerYear = 365.2425;
constexpr double kDailyYear = 1.0 / kDaysPerYear;
constexpr std::uint64_t kMortalityStream = 0x4d4f5254414c4954ULL;
constexpr std::uint64_t kFertilityStream = 0x46455254494c4954ULL;
constexpr std::uint64_t kSexStream = 0x4249525448534558ULL;
constexpr std::uint64_t kAgeStream = 0x47454e4553495341ULL;
constexpr std::uint64_t kOffsetStream = 0x47454e455349534fULL;
constexpr std::uint64_t kChurnStream = 0x4c41424f52434855ULL;
constexpr double kLaborTolerance = 1.0e-8;

[[nodiscard]] bool finite(double value) noexcept {
    return std::isfinite(value);
}

[[nodiscard]] std::uint64_t splitmix64(std::uint64_t value) noexcept {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

[[nodiscard]] double unit_draw(std::uint64_t seed, std::uint64_t identity,
                               std::int64_t day,
                               std::uint64_t stream) noexcept {
    const auto day_bits = static_cast<std::uint64_t>(day);
    const auto bits =
        splitmix64(seed ^ splitmix64(identity) ^ splitmix64(day_bits) ^ stream);
    return static_cast<double>(bits >> 11U) * 0x1.0p-53;
}

[[nodiscard]] double completed_age(const core::PersonRecord &person,
                                   std::int32_t day) noexcept {
    return std::max(
        0.0,
        static_cast<double>(day - person.birth_day) / kDaysPerYear
    );
}

[[nodiscard]] Status validate_vital_rates(
    const algorithms::VitalRates &rates
) noexcept {
    const auto female = algorithms::female_birth_share(rates);
    if (!female.ok()) {
        return female.status();
    }
    const auto mortality =
        algorithms::survival_probability(rates, 40.0, kDailyYear);
    if (!mortality.ok()) {
        return mortality.status();
    }
    const auto fertility = algorithms::fertility_rate(rates, 28.0);
    return fertility.ok() ? Status::success() : fertility.status();
}

[[nodiscard]] std::vector<double>
stable_age_weights(const algorithms::VitalRates &rates) {
    std::vector<double> weights(
        static_cast<std::size_t>(rates.maximum_age) + 1U,
        0.0
    );
    double survival = 1.0;
    for (std::uint32_t age = 0; age <= rates.maximum_age; ++age) {
        weights[age] = survival;
        if (age == rates.maximum_age) {
            break;
        }
        const auto next =
            algorithms::survival_probability(rates, static_cast<double>(age), 1.0);
        if (!next.ok()) {
            return {};
        }
        survival *= *next.get_if();
    }
    const double total = std::accumulate(weights.begin(), weights.end(), 0.0);
    if (!finite(total) || total <= 0.0) {
        return {};
    }
    for (auto &weight : weights) {
        weight /= total;
    }
    return weights;
}

[[nodiscard]] std::uint32_t sample_age(std::span<const double> weights,
                                       double draw) noexcept {
    double cumulative = 0.0;
    for (std::size_t age = 0; age < weights.size(); ++age) {
        cumulative += weights[age];
        if (draw < cumulative) {
            return static_cast<std::uint32_t>(age);
        }
    }
    return static_cast<std::uint32_t>(weights.size() - 1U);
}

[[nodiscard]] PersonId first_alive_member(
    const core::HouseholdMembershipBook &membership,
    const core::PersonStore &persons,
    HouseholdId household, PersonId excluded
) noexcept {
    PersonId selected{};
    for (const auto candidate : membership.members(household)) {
        if (candidate != excluded && persons.alive(candidate) &&
            (!selected.valid() || candidate < selected)) {
            selected = candidate;
        }
    }
    return selected;
}

[[nodiscard]] PersonId first_alive_person(
    const core::PersonStore &persons, PersonId excluded
) noexcept {
    PersonId selected{};
    for (const auto candidate : persons.alive_ids()) {
        if (candidate != excluded &&
            (!selected.valid() || candidate < selected)) {
            selected = candidate;
        }
    }
    return selected;
}

[[nodiscard]] double beneficial_projection_error(
    const core::BeneficialOwnershipBook &ownership
) {
    std::vector<std::pair<core::BeneficialAssetKey, double>> rows;
    rows.reserve(ownership.records().size());
    for (const auto &lot : ownership.records()) {
        if (lot.active) {
            rows.emplace_back(lot.asset, lot.share);
        }
    }
    std::sort(rows.begin(), rows.end(),
              [](const auto &left, const auto &right) {
                  return left.first < right.first;
              });
    double maximum_error = 0.0;
    std::size_t cursor = 0;
    while (cursor < rows.size()) {
        const auto asset = rows[cursor].first;
        double total = 0.0;
        while (cursor < rows.size() && rows[cursor].first == asset) {
            total += rows[cursor].second;
            ++cursor;
        }
        maximum_error = std::max(maximum_error, std::abs(total - 1.0));
    }
    return maximum_error;
}

void measure_population(const core::RootState &state, const M7Rules &rules,
                        const core::PersonStore &persons,
                        const core::HouseholdMembershipBook &membership,
                        std::int32_t day, M7Metrics &metrics) {
    metrics.population = persons.alive_count();
    std::uint64_t working = 0;
    std::uint64_t dependents = 0;
    for (const auto id : persons.alive_ids()) {
        const auto *person = persons.get(id);
        const double age = completed_age(*person, day);
        if (age >= static_cast<double>(rules.working_age) &&
            age < static_cast<double>(rules.retirement_age)) {
            ++working;
        } else {
            ++dependents;
        }
    }
    std::uint64_t active_households = 0;
    state.households.for_each_alive(
        [&](HouseholdId household, const core::HouseholdComponent &) {
            if (!membership.members(household).empty()) {
                ++active_households;
            }
        }
    );
    metrics.households_with_members = active_households;
    metrics.mean_household_size =
        active_households == 0
            ? 0.0
            : static_cast<double>(metrics.population) /
                  static_cast<double>(active_households);
    metrics.working_age_share =
        metrics.population == 0
            ? 0.0
            : static_cast<double>(working) /
                  static_cast<double>(metrics.population);
    metrics.dependency_ratio =
        working == 0
            ? static_cast<double>(dependents)
            : static_cast<double>(dependents) / static_cast<double>(working);
}

[[nodiscard]] Status settle_death(
    core::PersonStore &persons,
    core::HouseholdMembershipBook &membership,
    core::BeneficialOwnershipBook &ownership,
    core::EmploymentBook &employment,
    core::LaborAccounts &labor_accounts,
    std::vector<EstateRecord> &estates, std::uint64_t &next_event_id,
    PersonId deceased, std::int32_t day,
    const M7PolicyState &policy, M7Metrics &metrics,
    std::vector<BeneficialLotId> &lot_buffer
) {
    auto *record = persons.get(deceased);
    if (record == nullptr || !record->alive) {
        return Status(ErrorCode::contract_violation,
                      "death target is not alive");
    }
    const auto household = record->household;
    auto heir =
        first_alive_member(membership, persons, household, deceased);
    if (!heir.valid()) {
        heir = first_alive_person(persons, deceased);
    }

    lot_buffer.assign(ownership.lots_for_person(deceased).begin(),
                      ownership.lots_for_person(deceased).end());
    EstateRecord estate;
    estate.event = EventId(next_event_id++);
    estate.deceased = deceased;
    estate.household = household;
    estate.opened_day = day;
    estate.settled_day = day;
    estate.settled = true;
    for (const auto lot_id : lot_buffer) {
        const auto *lot = ownership.get(lot_id);
        if (lot == nullptr || !lot->active) {
            return Status(ErrorCode::invariant_violation,
                          "estate references an absent beneficial lot");
        }
        estate.gross_share += lot->share;
        const auto status = heir.valid()
                                ? ownership.transfer(lot_id, heir, lot->share)
                                : ownership.retire(lot_id);
        if (!status.ok()) {
            return status;
        }
        ++estate.transferred_lots;
    }
    estate.tax_share = estate.gross_share * policy.inheritance_tax_rate;

    for (const auto job_id :
         std::array{employment.primary_job(deceased),
                    employment.secondary_job(deceased)}) {
        const auto *job = employment.get(job_id);
        if (job == nullptr || !job->active) {
            continue;
        }
        const auto job_copy = *job;
        const auto job_status = employment.separate(
            job_id, day, core::SeparationKind::death
        );
        if (!job_status.ok()) {
            return job_status;
        }
        if (!job_copy.suspended) {
            labor_accounts.private_fte_outflows_total += job_copy.hours;
        }
        if (!job_copy.secondary) {
            labor_accounts.death_separations_total += 1.0;
        }
    }

    auto status = membership.remove(deceased);
    if (!status.ok()) {
        return status;
    }
    status = persons.mark_dead(deceased, day);
    if (!status.ok()) {
        return status;
    }
    estates.push_back(estate);
    ++metrics.deaths;
    ++metrics.estates_settled;
    metrics.beneficial_lots_transferred += estate.transferred_lots;
    metrics.inheritance_tax_share += estate.tax_share;
    return Status::success();
}

void record_separation(const core::JobRecord &job,
                       core::SeparationKind kind,
                       core::LaborAccounts &accounts) noexcept {
    if (!job.suspended) {
        accounts.private_fte_outflows_total += job.hours;
    }
    if (job.secondary) {
        return;
    }
    switch (kind) {
    case core::SeparationKind::churn:
        accounts.churn_separations_total += 1.0;
        break;
    case core::SeparationKind::demand_layoff:
        accounts.layoff_separations_total += 1.0;
        break;
    case core::SeparationKind::cash_layoff:
        accounts.cash_layoffs_total += 1.0;
        accounts.layoff_separations_total += 1.0;
        break;
    case core::SeparationKind::firm_exit:
        accounts.firm_exit_separations_total += 1.0;
        break;
    case core::SeparationKind::death:
        accounts.death_separations_total += 1.0;
        break;
    case core::SeparationKind::retirement:
        accounts.retirement_separations_total += 1.0;
        break;
    case core::SeparationKind::welfare_quit:
        accounts.welfare_quits_total += 1.0;
        break;
    case core::SeparationKind::job_to_job:
        accounts.job_to_job_moves_total += 1.0;
        break;
    }
}

[[nodiscard]] Status separate_job(
    core::EmploymentBook &employment, JobId job_id,
    std::int32_t day, core::SeparationKind kind,
    core::LaborAccounts &accounts
) {
    const auto *job = employment.get(job_id);
    if (job == nullptr || !job->active) {
        return Status::success();
    }
    const auto copy = *job;
    const auto status = employment.separate(job_id, day, kind);
    if (!status.ok()) {
        return status;
    }
    record_separation(copy, kind, accounts);
    return Status::success();
}

[[nodiscard]] Status separate_person(
    core::EmploymentBook &employment, PersonId person,
    std::int32_t day, core::SeparationKind kind,
    core::LaborAccounts &accounts
) {
    const auto primary = employment.primary_job(person);
    const auto secondary = employment.secondary_job(person);
    auto status = separate_job(
        employment, secondary, day, kind, accounts
    );
    if (!status.ok()) {
        return status;
    }
    return separate_job(employment, primary, day, kind, accounts);
}

void measure_labor(
    const core::RootState &state, const M7Rules &rules,
    const core::PersonStore &persons,
    const core::EmploymentBook &employment,
    const M4TickScratch &real, std::int32_t day,
    core::LaborAccounts &accounts, M7Metrics &metrics
) {
    accounts.employed_fte = 0.0;
    accounts.employed_heads = 0.0;
    accounts.unemployed = 0.0;
    accounts.suspended = 0.0;
    accounts.job_guarantee = 0.0;
    accounts.out_of_labor_force = 0.0;
    accounts.labor_supply = 0.0;
    accounts.vacancies = 0.0;
    accounts.underemployed_heads = 0.0;
    accounts.underemployment_hours = 0.0;
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const double age = completed_age(*person, day);
        if (age < static_cast<double>(rules.working_age) ||
            age >= static_cast<double>(rules.retirement_age) ||
            !person->participating) {
            accounts.out_of_labor_force += 1.0;
            continue;
        }
        accounts.labor_supply += 1.0;
        const auto primary_id = employment.primary_job(person_id);
        const auto *primary = employment.get(primary_id);
        if (primary == nullptr || !primary->active) {
            accounts.unemployed += 1.0;
            continue;
        }
        if (primary->suspended) {
            accounts.suspended += 1.0;
            continue;
        }
        const double hours = employment.active_hours(person_id);
        accounts.employed_heads += 1.0;
        accounts.employed_fte += hours;
        if (hours < 1.0 - kLaborTolerance) {
            accounts.underemployed_heads += 1.0;
            accounts.underemployment_hours += 1.0 - hours;
        }
    }
    for (std::size_t index = 0; index < real.firm_ids_.size(); ++index) {
        accounts.vacancies += std::max(
            0.0,
            real.firm_work_[index].labor_demand_effective -
                employment.active_hours(real.firm_ids_[index])
        );
    }
    const double head_flow_balance =
        accounts.hires_total + accounts.recalls_total -
        accounts.churn_separations_total -
        accounts.layoff_separations_total -
        accounts.firm_exit_separations_total -
        accounts.death_separations_total -
        accounts.retirement_separations_total -
        accounts.suspensions_total -
        accounts.welfare_quits_total;
    const double fte_flow_balance =
        accounts.private_fte_inflows_total -
        accounts.private_fte_outflows_total;
    if (accounts.previous_employed_heads >= 0.0) {
        const double expected =
            accounts.previous_employed_heads +
            head_flow_balance - accounts.previous_head_flow_balance;
        if (std::abs(expected - accounts.employed_heads) >
            kLaborTolerance) {
            accounts.employed_heads =
                std::numeric_limits<double>::quiet_NaN();
        }
    }
    if (accounts.previous_employed_fte >= 0.0) {
        const double expected =
            accounts.previous_employed_fte +
            fte_flow_balance - accounts.previous_fte_flow_balance;
        if (std::abs(expected - accounts.employed_fte) >
            kLaborTolerance) {
            accounts.employed_fte =
                std::numeric_limits<double>::quiet_NaN();
        }
    }
    accounts.previous_employed_heads = accounts.employed_heads;
    accounts.previous_head_flow_balance = head_flow_balance;
    accounts.previous_employed_fte = accounts.employed_fte;
    accounts.previous_fte_flow_balance = fte_flow_balance;

    metrics.employed_fte = accounts.employed_fte;
    metrics.employed_heads = accounts.employed_heads;
    metrics.unemployment = accounts.unemployed;
    metrics.unemployment_rate =
        accounts.labor_supply <= 0.0
            ? 0.0
            : accounts.unemployed / accounts.labor_supply;
    metrics.suspended = accounts.suspended;
    metrics.job_guarantee = accounts.job_guarantee;
    metrics.out_of_labor_force = accounts.out_of_labor_force;
    metrics.labor_supply = accounts.labor_supply;
    metrics.vacancies = accounts.vacancies;
    metrics.underemployed_heads = accounts.underemployed_heads;
    metrics.underemployment_hours = accounts.underemployment_hours;
    static_cast<void>(state);
}

class M7Extension final : public M6TickExtension {
  public:
    M7Extension(M7Runtime &runtime, M7TickScratch &scratch,
                const M7AdvanceOptions &options) noexcept
        : runtime_(runtime), scratch_(scratch), options_(options) {}

    Status prepare_tick(const core::RootState &state, M4Runtime &,
                        M4TickScratch &,
                        M5Runtime &, M5TickScratch &, M6Runtime &,
                        M6TickScratch &, Tick tick, PhiloxRng &) override {
        if (options_.force_death.has_value() &&
            !runtime_.persons.alive(*options_.force_death)) {
            return Status(ErrorCode::contract_violation,
                          "forced death target is not alive");
        }
        if (options_.force_birth.has_value() &&
            !runtime_.persons.alive(*options_.force_birth)) {
            return Status(ErrorCode::contract_violation,
                          "forced birth target is not alive");
        }
        scratch_.persons_ = runtime_.persons;
        scratch_.membership_ = runtime_.membership;
        scratch_.beneficial_ownership_ = runtime_.beneficial_ownership;
        scratch_.employment_ = runtime_.employment;
        scratch_.labor_accounts_ = runtime_.labor_accounts;
        scratch_.firm_target_ema_ = runtime_.firm_target_ema;
        scratch_.estates_ = runtime_.estates;
        scratch_.opening_alive_.assign(runtime_.persons.alive_ids().begin(),
                                       runtime_.persons.alive_ids().end());
        scratch_.next_event_id_ = runtime_.next_event_id;
        scratch_.population_rng_counter_ = runtime_.population_rng_counter;
        scratch_.working_metrics_ = M7Metrics{};
        const auto day =
            static_cast<std::int64_t>(runtime_.start_calendar_day) +
            static_cast<std::int64_t>(tick.value()) + 1;
        if (day < std::numeric_limits<std::int32_t>::min() ||
            day > std::numeric_limits<std::int32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "M7 calendar day exceeds storage range");
        }
        const auto calendar_day = static_cast<std::int32_t>(day);
        for (const auto person_id : scratch_.opening_alive_) {
            const auto *person = scratch_.persons_.get(person_id);
            if (person == nullptr || !person->alive) {
                continue;
            }
            bool dies =
                options_.force_death.has_value() &&
                *options_.force_death == person_id;
            const double age = completed_age(*person, calendar_day);
            if (!dies && runtime_.rules.mortality) {
                if (age >=
                    static_cast<double>(
                        runtime_.rules.vital_rates.maximum_age
                    )) {
                    dies = true;
                } else {
                    const auto survival =
                        algorithms::survival_probability(
                            runtime_.rules.vital_rates, age, kDailyYear
                        );
                    if (!survival.ok()) {
                        return survival.status();
                    }
                    dies =
                        unit_draw(
                            state.seed, person_id.value(), calendar_day,
                            kMortalityStream
                        ) > *survival.get_if();
                }
            }
            if (dies) {
                const auto status = settle_death(
                    scratch_.persons_, scratch_.membership_,
                    scratch_.beneficial_ownership_,
                    scratch_.employment_, scratch_.labor_accounts_,
                    scratch_.estates_, scratch_.next_event_id_, person_id,
                    calendar_day, runtime_.policy,
                    scratch_.working_metrics_, scratch_.deceased_lots_
                );
                if (!status.ok()) {
                    return status;
                }
            }
        }
        if (options_.force_death.has_value() &&
            scratch_.persons_.alive(*options_.force_death)) {
            return Status(ErrorCode::contract_violation,
                          "forced death target was not settled");
        }
        return Status::success();
    }

    Status run_labor(const core::RootState &state, M4Runtime &,
                     M4TickScratch &real, M5Runtime &, M5TickScratch &,
                     M6Runtime &, M6TickScratch &, Tick tick, PhiloxRng &,
                     bool &handled) override {
        handled = runtime_.rules.persistent_labor;
        if (!handled) {
            return Status::success();
        }
        const auto calendar_day = static_cast<std::int32_t>(
            static_cast<std::int64_t>(runtime_.start_calendar_day) +
            static_cast<std::int64_t>(tick.value()) + 1
        );
        scratch_.household_work_index_.assign(
            static_cast<std::size_t>(
                state.households.allocator_state().next_id
            ),
            std::numeric_limits<std::size_t>::max()
        );
        for (std::size_t index = 0;
             index < real.household_ids_.size(); ++index) {
            scratch_.household_work_index_[
                static_cast<std::size_t>(
                    real.household_ids_[index].value()
                )] = index;
        }
        if (scratch_.firm_target_ema_.size() <
            state.firms.allocator_state().next_id) {
            scratch_.firm_target_ema_.resize(
                static_cast<std::size_t>(
                    state.firms.allocator_state().next_id
                ),
                0.0
            );
        }

        const double churn_probability =
            runtime_.rules.annual_churn >= 1.0
                ? 1.0
                : 1.0 -
                      std::pow(
                          1.0 - runtime_.rules.annual_churn,
                          kDailyYear
                      );
        for (const auto person_id : scratch_.persons_.alive_ids()) {
            auto *person = scratch_.persons_.get(person_id);
            const double age = completed_age(*person, calendar_day);
            const bool working_age =
                age >= static_cast<double>(runtime_.rules.working_age) &&
                age < static_cast<double>(
                          runtime_.rules.retirement_age
                      );
            person->participating = working_age;
            if (!working_age) {
                const auto status = separate_person(
                    scratch_.employment_, person_id, calendar_day,
                    core::SeparationKind::retirement,
                    scratch_.labor_accounts_
                );
                if (!status.ok()) {
                    return status;
                }
                continue;
            }
            const auto primary =
                scratch_.employment_.primary_job(person_id);
            if (scratch_.employment_.get(primary) != nullptr &&
                unit_draw(
                    state.seed, person_id.value(), calendar_day,
                    kChurnStream
                ) < churn_probability) {
                const auto status = separate_person(
                    scratch_.employment_, person_id, calendar_day,
                    core::SeparationKind::churn,
                    scratch_.labor_accounts_
                );
                if (!status.ok()) {
                    return status;
                }
                scratch_.working_metrics_.separations += 1.0;
            }
        }

        for (const auto &job : scratch_.employment_.records()) {
            if (!job.active || !job.suspended ||
                calendar_day - job.suspension_day <
                    static_cast<std::int32_t>(
                        runtime_.rules.suspension_timeout_days
                    )) {
                continue;
            }
            const auto status = scratch_.employment_.separate(
                job.id, calendar_day,
                core::SeparationKind::cash_layoff
            );
            if (!status.ok()) {
                return status;
            }
        }

        for (std::size_t firm_index = 0;
             firm_index < real.firm_ids_.size(); ++firm_index) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            auto &work = real.firm_work_[firm_index];
            const double target =
                std::max(0.0, work.labor_demand_effective);
            auto &target_ema = scratch_.firm_target_ema_[
                static_cast<std::size_t>(firm_id.value())];
            target_ema =
                target_ema <= 0.0
                    ? target
                    : (1.0 - runtime_.rules.target_smoothing) *
                              target_ema +
                          runtime_.rules.target_smoothing * target;
            const double firing_target = std::max(target, target_ema);

            scratch_.roster_buffer_.assign(
                scratch_.employment_.roster(firm_id).begin(),
                scratch_.employment_.roster(firm_id).end()
            );
            std::sort(
                scratch_.roster_buffer_.begin(),
                scratch_.roster_buffer_.end(),
                [&](JobId left, JobId right) {
                    const auto *left_job =
                        scratch_.employment_.get(left);
                    const auto *right_job =
                        scratch_.employment_.get(right);
                    if (left_job->hire_day != right_job->hire_day) {
                        return left_job->hire_day >
                               right_job->hire_day;
                    }
                    return left > right;
                }
            );
            double active_hours =
                scratch_.employment_.active_hours(firm_id);
            const double layoff_threshold =
                firing_target *
                (1.0 + runtime_.rules.layoff_band);
            for (const auto job_id : scratch_.roster_buffer_) {
                if (active_hours <= layoff_threshold +
                                        kLaborTolerance) {
                    break;
                }
                const auto *job =
                    scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active ||
                    job->suspended) {
                    continue;
                }
                const double excess =
                    active_hours - firing_target;
                if (runtime_.rules.fractional_hours &&
                    job->hours - excess > 1.0e-6) {
                    const double old_hours = job->hours;
                    const auto status =
                        scratch_.employment_.set_hours(
                            job_id, old_hours - excess
                        );
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.labor_accounts_
                        .private_fte_outflows_total += excess;
                    active_hours -= excess;
                    break;
                }
                const double hours = job->hours;
                const auto status = separate_job(
                    scratch_.employment_, job_id, calendar_day,
                    core::SeparationKind::demand_layoff,
                    scratch_.labor_accounts_
                );
                if (!status.ok()) {
                    return status;
                }
                active_hours -= hours;
                scratch_.working_metrics_.separations += 1.0;
            }

            const auto firm_account_index =
                static_cast<std::size_t>(
                    firm->primary_account.value()
                );
            const double affordable_hours =
                real.balances_[firm_account_index] /
                std::max(work.posted_wage, 1.0e-12);
            for (const auto job_id :
                 scratch_.employment_.roster(firm_id)) {
                auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active ||
                    !job->suspended ||
                    active_hours + job->hours >
                        std::min(target, affordable_hours) +
                            kLaborTolerance) {
                    continue;
                }
                const auto status =
                    scratch_.employment_.recall(job_id);
                if (!status.ok()) {
                    return status;
                }
                active_hours += job->hours;
                scratch_.labor_accounts_.recalls_total += 1.0;
                scratch_.labor_accounts_
                    .private_fte_inflows_total += job->hours;
            }
        }

        scratch_.labor_candidates_.clear();
        for (const auto person_id : scratch_.persons_.alive_ids()) {
            const auto *person = scratch_.persons_.get(person_id);
            if (person->participating &&
                scratch_.employment_
                    .get(
                        scratch_.employment_.primary_job(person_id)
                    ) == nullptr) {
                scratch_.labor_candidates_.push_back(person_id);
            }
        }
        std::sort(
            scratch_.labor_candidates_.begin(),
            scratch_.labor_candidates_.end()
        );
        std::size_t candidate_cursor = 0;
        for (std::size_t firm_index = 0;
             firm_index < real.firm_ids_.size(); ++firm_index) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            auto &work = real.firm_work_[firm_index];
            double active_hours =
                scratch_.employment_.active_hours(firm_id);
            double need =
                std::max(
                    0.0,
                    work.labor_demand_effective - active_hours
                );
            while (need > kLaborTolerance &&
                   candidate_cursor <
                       scratch_.labor_candidates_.size()) {
                const auto person_id =
                    scratch_.labor_candidates_[candidate_cursor++];
                if (runtime_.rules.frictional_search &&
                    unit_draw(
                        state.seed, person_id.value(), calendar_day,
                        firm_id.value()
                    ) >= runtime_.rules.search_intensity) {
                    continue;
                }
                const double hours =
                    runtime_.rules.fractional_hours
                        ? std::min(1.0, need)
                        : 1.0;
                const auto hired = scratch_.employment_.hire(
                    person_id, firm_id, calendar_day,
                    work.posted_wage, hours
                );
                if (!hired.ok()) {
                    return hired.status();
                }
                need = std::max(0.0, need - hours);
                active_hours += hours;
                scratch_.labor_accounts_.hires_total += 1.0;
                scratch_.labor_accounts_
                    .private_fte_inflows_total += hours;
                scratch_.working_metrics_.hires += 1.0;
            }

            const auto firm_account_index =
                static_cast<std::size_t>(
                    firm->primary_account.value()
                );
            double affordable_hours =
                real.balances_[firm_account_index] /
                std::max(work.posted_wage, 1.0e-12);
            if (active_hours > affordable_hours +
                                   kLaborTolerance) {
                scratch_.roster_buffer_.assign(
                    scratch_.employment_.roster(firm_id).begin(),
                    scratch_.employment_.roster(firm_id).end()
                );
                std::sort(
                    scratch_.roster_buffer_.begin(),
                    scratch_.roster_buffer_.end(),
                    [&](JobId left, JobId right) {
                        const auto *left_job =
                            scratch_.employment_.get(left);
                        const auto *right_job =
                            scratch_.employment_.get(right);
                        if (left_job->hire_day !=
                            right_job->hire_day) {
                            return left_job->hire_day >
                                   right_job->hire_day;
                        }
                        return left > right;
                    }
                );
                for (const auto job_id :
                     scratch_.roster_buffer_) {
                    if (active_hours <= affordable_hours +
                                            kLaborTolerance) {
                        break;
                    }
                    const auto *job =
                        scratch_.employment_.get(job_id);
                    if (job == nullptr || !job->active ||
                        job->suspended) {
                        continue;
                    }
                    const double hours = job->hours;
                    Status status;
                    if (runtime_.rules.suspensions &&
                        !job->secondary) {
                        status = scratch_.employment_.suspend(
                            job_id, calendar_day
                        );
                        if (status.ok()) {
                            scratch_.labor_accounts_
                                .suspensions_total += 1.0;
                            scratch_.labor_accounts_
                                .private_fte_outflows_total +=
                                hours;
                        }
                    } else {
                        status = separate_job(
                            scratch_.employment_, job_id,
                            calendar_day,
                            core::SeparationKind::cash_layoff,
                            scratch_.labor_accounts_
                        );
                    }
                    if (!status.ok()) {
                        return status;
                    }
                    active_hours -= hours;
                }
            }

            for (const auto job_id :
                 scratch_.employment_.roster(firm_id)) {
                const auto *job =
                    scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active ||
                    job->suspended) {
                    continue;
                }
                const auto *person =
                    scratch_.persons_.get(job->person);
                const auto *household =
                    state.households.get(person->household);
                if (household == nullptr) {
                    return Status(
                        ErrorCode::invariant_violation,
                        "job references an absent household"
                    );
                }
                const double pay =
                    job->hours * job->wage * person->efficiency;
                const auto transfer_status = stage_m4_transfer(
                    state, real, firm->primary_account,
                    household->primary_account, pay
                );
                if (!transfer_status.ok()) {
                    return transfer_status;
                }
                const auto household_index =
                    scratch_.household_work_index_[
                        static_cast<std::size_t>(
                            person->household.value()
                        )];
                if (household_index >=
                    real.household_work_.size()) {
                    return Status(
                        ErrorCode::invariant_violation,
                        "household labor projection is stale"
                    );
                }
                auto &household_work =
                    real.household_work_[household_index];
                household_work.income_realized += pay;
                const auto member_count =
                    scratch_.membership_
                        .members(person->household)
                        .size();
                household_work.labor_sold +=
                    job->hours /
                    static_cast<double>(
                        std::max<std::size_t>(1, member_count)
                    );
                work.hired += job->hours * person->efficiency;
                work.wage_bill += pay;
            }
        }
        return Status::success();
    }

    Status close_day(const core::RootState &state, M4Runtime &,
                     M4TickScratch &real, M5Runtime &, M5TickScratch &,
                     M6Runtime &, M6TickScratch &financial,
                     Tick tick, PhiloxRng &) override {
        const auto day = static_cast<std::int64_t>(runtime_.start_calendar_day) +
                         static_cast<std::int64_t>(tick.value()) + 1;
        if (day < std::numeric_limits<std::int32_t>::min() ||
            day > std::numeric_limits<std::int32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "M7 calendar day exceeds storage range");
        }
        const auto calendar_day = static_cast<std::int32_t>(day);

        if (runtime_.rules.persistent_labor) {
            for (const auto &exit : financial.firm_exits_) {
                scratch_.roster_buffer_.assign(
                    scratch_.employment_.roster(exit.firm).begin(),
                    scratch_.employment_.roster(exit.firm).end()
                );
                for (const auto job_id :
                     scratch_.roster_buffer_) {
                    const auto status = separate_job(
                        scratch_.employment_, job_id, calendar_day,
                        core::SeparationKind::firm_exit,
                        scratch_.labor_accounts_
                    );
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.working_metrics_.separations += 1.0;
                }
            }
        }

        if (runtime_.rules.fertility ||
            options_.force_birth.has_value()) {
            std::vector<PersonId> mothers;
            mothers.reserve(scratch_.persons_.alive_count() / 4U);
            for (const auto person_id : scratch_.persons_.alive_ids()) {
                const auto *person = scratch_.persons_.get(person_id);
                const double age = completed_age(*person, calendar_day);
                const bool forced =
                    options_.force_birth.has_value() &&
                    *options_.force_birth == person_id;
                if (person->sex != core::PersonSex::female ||
                    age < 15.0 || age > 49.0) {
                    if (forced) {
                        return Status(ErrorCode::invalid_argument,
                                      "forced birth target is ineligible");
                    }
                    continue;
                }
                const auto annual_rate =
                    algorithms::fertility_rate(runtime_.rules.vital_rates, age);
                if (!annual_rate.ok()) {
                    return annual_rate.status();
                }
                const double probability =
                    runtime_.rules.fertility
                        ? 1.0 -
                              std::exp(
                                  -*annual_rate.get_if() * kDailyYear
                              )
                        : 0.0;
                if (forced ||
                    unit_draw(state.seed, person_id.value(), calendar_day,
                              kFertilityStream) < probability) {
                    mothers.push_back(person_id);
                }
            }
            if (options_.force_birth.has_value() &&
                !scratch_.persons_.alive(*options_.force_birth)) {
                return Status(ErrorCode::contract_violation,
                              "forced birth target is not alive");
            }
            const auto female_share =
                algorithms::female_birth_share(runtime_.rules.vital_rates);
            if (!female_share.ok()) {
                return female_share.status();
            }
            for (const auto mother_id : mothers) {
                const auto *mother = scratch_.persons_.get(mother_id);
                core::PersonRecord baby;
                baby.sex =
                    unit_draw(state.seed, mother_id.value(), calendar_day,
                              kSexStream) < *female_share.get_if()
                        ? core::PersonSex::female
                        : core::PersonSex::male;
                baby.birth_day = calendar_day;
                baby.mother = mother_id;
                baby.father =
                    scratch_.persons_.alive(mother->partner)
                        ? mother->partner
                        : PersonId{};
                baby.guardian = mother_id;
                baby.household = mother->household;
                const auto created = scratch_.persons_.create(baby);
                if (!created.ok()) {
                    return created.status();
                }
                const auto status =
                    scratch_.membership_.add(*created.get_if(), baby.household);
                if (!status.ok()) {
                    return status;
                }
                ++scratch_.working_metrics_.births;
            }
        }
        ++scratch_.population_rng_counter_;
        measure_population(state, runtime_.rules, scratch_.persons_,
                           scratch_.membership_, calendar_day,
                           scratch_.working_metrics_);
        if (runtime_.rules.persistent_labor) {
            measure_labor(
                state, runtime_.rules, scratch_.persons_,
                scratch_.employment_, real, calendar_day,
                scratch_.labor_accounts_,
                scratch_.working_metrics_
            );
        }
        scratch_.working_metrics_.beneficial_projection_error =
            beneficial_projection_error(scratch_.beneficial_ownership_);
        return Status::success();
    }

    Status validate(const core::RootState &state, const M4Runtime &,
                    const M4TickScratch &, const M5Runtime &,
                    const M5TickScratch &, const M6Runtime &,
                    const M6TickScratch &, Tick) const override {
        auto status = scratch_.persons_.validate();
        if (status.ok()) {
            status = scratch_.membership_.validate(scratch_.persons_, state);
        }
        if (status.ok() && runtime_.rules.beneficial_ownership) {
            status = scratch_.beneficial_ownership_.validate(
                scratch_.persons_, state.accounting_tolerance
            );
        }
        if (status.ok() && runtime_.rules.persistent_labor) {
            status = scratch_.employment_.validate(
                scratch_.persons_, state, state.accounting_tolerance
            );
        }
        if (status.ok() && runtime_.rules.persistent_labor) {
            status = core::validate_labor_accounts(
                scratch_.labor_accounts_, state.accounting_tolerance
            );
        }
        if (!status.ok()) {
            return status;
        }
        if (options_.fault_before_population_commit) {
            return Status(ErrorCode::internal_error,
                          "injected M7 pre-commit fault");
        }
        return Status::success();
    }

    void commit(core::RootState &, M4Runtime &, M4TickScratch &, M5Runtime &,
                M5TickScratch &, M6Runtime &, M6TickScratch &, Tick tick,
                const M6Metrics &metrics) noexcept override {
        std::swap(runtime_.persons, scratch_.persons_);
        std::swap(runtime_.membership, scratch_.membership_);
        std::swap(runtime_.beneficial_ownership,
                  scratch_.beneficial_ownership_);
        std::swap(runtime_.employment, scratch_.employment_);
        runtime_.labor_accounts = scratch_.labor_accounts_;
        std::swap(runtime_.firm_target_ema,
                  scratch_.firm_target_ema_);
        std::swap(runtime_.estates, scratch_.estates_);
        runtime_.next_event_id = scratch_.next_event_id_;
        runtime_.population_rng_counter = scratch_.population_rng_counter_;
        scratch_.working_metrics_.economy = metrics;
        runtime_.last_metrics = scratch_.working_metrics_;
        runtime_.current_calendar_day =
            runtime_.start_calendar_day +
            static_cast<std::int32_t>(tick.value()) + 1;
    }

  private:
    M7Runtime &runtime_;
    M7TickScratch &scratch_;
    const M7AdvanceOptions &options_;
};

} // namespace

void M7TickScratch::reserve(const M7Runtime &runtime) {
    opening_alive_.reserve(runtime.persons.alive_count());
    deceased_lots_.reserve(8);
    estates_.reserve(runtime.estates.size() + 8U);
    labor_candidates_.reserve(runtime.persons.alive_count());
    roster_buffer_.reserve(runtime.employment.active_count());
    firm_target_ema_.reserve(runtime.firm_target_ema.size());
}

std::uint64_t M7TickScratch::capacity_signature() const noexcept {
    return static_cast<std::uint64_t>(opening_alive_.capacity()) ^
           (static_cast<std::uint64_t>(deceased_lots_.capacity()) << 16U) ^
           (static_cast<std::uint64_t>(estates_.capacity()) << 32U) ^
           (static_cast<std::uint64_t>(labor_candidates_.capacity())
            << 8U) ^
           (static_cast<std::uint64_t>(roster_buffer_.capacity()) << 24U);
}

Status validate_m7_policy(const M7PolicyState &policy) noexcept {
    if (!finite(policy.inheritance_tax_rate) ||
        policy.inheritance_tax_rate < 0.0 ||
        policy.inheritance_tax_rate > 1.0) {
        return Status(ErrorCode::invalid_argument, "M7 policy is invalid");
    }
    return Status::success();
}

Status validate_m7_rules(const M7Rules &rules) noexcept {
    const std::array labor_values{
        rules.annual_churn,
        rules.firing_adjustment,
        rules.layoff_band,
        rules.target_smoothing,
        rules.search_intensity,
    };
    if (rules.working_age < 1U ||
        rules.retirement_age <= rules.working_age ||
        rules.retirement_age > rules.vital_rates.maximum_age ||
        (rules.estates && !rules.beneficial_ownership) ||
        !std::all_of(
            labor_values.begin(), labor_values.end(),
            [](double value) { return finite(value); }
        ) ||
        rules.annual_churn < 0.0 || rules.annual_churn > 1.0 ||
        rules.firing_adjustment < 0.0 ||
        rules.firing_adjustment > 1.0 ||
        rules.layoff_band < 0.0 ||
        rules.target_smoothing < 0.0 ||
        rules.target_smoothing > 1.0 ||
        rules.suspension_timeout_days == 0 ||
        rules.search_intensity < 0.0 ||
        rules.search_intensity > 1.0 ||
        (rules.second_jobs && !rules.fractional_hours)) {
        return Status(ErrorCode::invalid_argument, "M7 rules are invalid");
    }
    return validate_vital_rates(rules.vital_rates);
}

Status
validate_m7_population_spec(const M7PopulationSpec &population) noexcept {
    if (population.initial_persons == 0 ||
        !finite(population.target_household_size) ||
        population.target_household_size < 1.0 ||
        population.target_household_size >
            static_cast<double>(population.initial_persons)) {
        return Status(ErrorCode::invalid_argument,
                      "M7 population specification is invalid");
    }
    return Status::success();
}

Status validate_m7_spec(const M7SimulationSpec &spec) noexcept {
    auto status = validate_m7_policy(spec.policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_rules(spec.rules);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_population_spec(spec.population);
    if (!status.ok()) {
        return status;
    }
    auto financial = spec.financial_economy;
    const auto derived_households = static_cast<std::uint64_t>(std::ceil(
        static_cast<double>(spec.population.initial_persons) /
        spec.population.target_household_size
    ));
    financial.monetary_economy.real_economy.households =
        derived_households;
    return validate_m6_spec(financial);
}

Status validate_m7_state(const core::RootState &state,
                         const M4Runtime &real_economy_runtime,
                         const M5Runtime &monetary_runtime,
                         const M6Runtime &financial_runtime,
                         const M7Runtime &runtime, Tick tick) noexcept {
    auto status = validate_m7_policy(runtime.policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_rules(runtime.rules);
    if (!status.ok()) {
        return status;
    }
    status = validate_m6_state(state, real_economy_runtime, monetary_runtime,
                               financial_runtime, tick);
    if (!status.ok()) {
        return status;
    }
    status = runtime.persons.validate();
    if (!status.ok()) {
        return status;
    }
    status = runtime.membership.validate(runtime.persons, state);
    if (!status.ok()) {
        return status;
    }
    if (runtime.rules.beneficial_ownership) {
        status = runtime.beneficial_ownership.validate(
            runtime.persons, state.accounting_tolerance
        );
        if (!status.ok()) {
            return status;
        }
    }
    if (runtime.rules.persistent_labor) {
        status = runtime.employment.validate(
            runtime.persons, state, state.accounting_tolerance
        );
        if (!status.ok()) {
            return status;
        }
        status = core::validate_labor_accounts(
            runtime.labor_accounts, state.accounting_tolerance
        );
        if (!status.ok()) {
            return status;
        }
    }
    const auto expected_day =
        static_cast<std::int64_t>(runtime.start_calendar_day) +
        static_cast<std::int64_t>(tick.value());
    if (expected_day != runtime.current_calendar_day) {
        return Status(ErrorCode::invariant_violation,
                      "M7 calendar and tick are inconsistent");
    }
    return Status::success();
}

Result<M7Initialization>
build_m7_genesis(const M7SimulationSpec &spec) {
    const auto status = validate_m7_spec(spec);
    if (!status.ok()) {
        return status;
    }
    auto financial_spec = spec.financial_economy;
    auto &real = financial_spec.monetary_economy.real_economy;
    real.households = static_cast<std::uint64_t>(std::ceil(
        static_cast<double>(spec.population.initial_persons) /
        spec.population.target_household_size
    ));
    const auto genesis = build_m6_genesis(financial_spec);
    if (!genesis.ok()) {
        return genesis.status();
    }
    auto financial = std::move(*genesis.get_if());

    M7Runtime runtime;
    runtime.policy = spec.policy;
    runtime.rules = spec.rules;
    runtime.start_calendar_day = spec.population.start_calendar_day;
    runtime.current_calendar_day = spec.population.start_calendar_day;
    runtime.firm_target_ema.resize(
        static_cast<std::size_t>(
            financial.root.firms.allocator_state().next_id
        ),
        0.0
    );
    const auto age_weights = stable_age_weights(spec.rules.vital_rates);
    if (age_weights.empty()) {
        return Status(ErrorCode::invalid_argument,
                      "M7 stable age distribution is invalid");
    }
    const auto female_share =
        algorithms::female_birth_share(spec.rules.vital_rates);
    if (!female_share.ok()) {
        return female_share.status();
    }

    std::vector<HouseholdId> households;
    households.reserve(financial.root.households.alive_count());
    financial.root.households.for_each_alive(
        [&](HouseholdId id, const core::HouseholdComponent &) {
            households.push_back(id);
        }
    );
    std::sort(households.begin(), households.end());
    for (std::uint64_t index = 0;
         index < spec.population.initial_persons; ++index) {
        const auto identity = index + 1U;
        const auto age = sample_age(
            age_weights,
            unit_draw(financial.root.seed, identity,
                      spec.population.start_calendar_day, kAgeStream)
        );
        const auto offset = static_cast<std::int32_t>(
            unit_draw(financial.root.seed, identity,
                      spec.population.start_calendar_day, kOffsetStream) *
            kDaysPerYear
        );
        core::PersonRecord person;
        person.sex =
            unit_draw(financial.root.seed, identity,
                      spec.population.start_calendar_day, kSexStream) <
                    *female_share.get_if()
                ? core::PersonSex::female
                : core::PersonSex::male;
        person.birth_day =
            spec.population.start_calendar_day -
            static_cast<std::int32_t>(age * 365U) - offset;
        person.household =
            households[static_cast<std::size_t>(index % households.size())];
        const auto created = runtime.persons.create(person);
        if (!created.ok()) {
            return created.status();
        }
        const auto membership =
            runtime.membership.add(*created.get_if(), person.household);
        if (!membership.ok()) {
            return membership;
        }
    }

    if (runtime.rules.beneficial_ownership) {
        for (const auto household : households) {
            const auto members = runtime.membership.members(household);
            if (members.empty()) {
                return Status(ErrorCode::invariant_violation,
                              "M7 genesis created an empty household");
            }
            const double share = 1.0 / static_cast<double>(members.size());
            const core::BeneficialAssetKey cash{
                core::BeneficialAssetKind::household_cash,
                household,
                household.value(),
            };
            for (const auto person : members) {
                const auto lot =
                    runtime.beneficial_ownership.create_lot(cash, person, share);
                if (!lot.ok()) {
                    return lot.status();
                }
            }
        }
    }
    measure_population(financial.root, runtime.rules, runtime.persons,
                       runtime.membership, runtime.current_calendar_day,
                       runtime.last_metrics);
    runtime.last_metrics.beneficial_projection_error =
        beneficial_projection_error(runtime.beneficial_ownership);
    const auto state_status = validate_m7_state(
        financial.root, financial.real_economy_runtime,
        financial.monetary_runtime, financial.runtime, runtime, Tick(0)
    );
    if (!state_status.ok()) {
        return state_status;
    }
    return M7Initialization{
        std::move(financial.root),
        std::move(financial.real_economy_runtime),
        std::move(financial.monetary_runtime),
        std::move(financial.runtime),
        std::move(runtime),
    };
}

Result<M7AdvanceResult>
advance_m7_ticks(core::RootState &state,
                 M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch,
                 M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch,
                 M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch,
                 M7Runtime &runtime, M7TickScratch &scratch, Tick &tick,
                 std::uint64_t count,
                 const M7AdvanceOptions &options) {
    const auto status =
        validate_m7_state(state, real_economy_runtime, monetary_runtime,
                          financial_runtime, runtime, tick);
    if (!status.ok()) {
        return Status(ErrorCode::invariant_violation,
                      "M7 cannot advance an invalid state");
    }
    M7Extension extension(runtime, scratch, options);
    auto result = advance_m6_ticks_extended(
        state, real_economy_runtime, real_economy_scratch, monetary_runtime,
        monetary_scratch, financial_runtime, financial_scratch, tick, count,
        extension, options.base
    );
    if (!result.ok()) {
        return result.status();
    }
    const auto &base = *result.get_if();
    return M7AdvanceResult{
        base.first_tick,
        base.next_tick,
        base.advanced_ticks,
        runtime.last_metrics,
        scratch.capacity_signature(),
        base.transfer_count,
        base.trade_count,
    };
}

} // namespace macro_sim::simulation
