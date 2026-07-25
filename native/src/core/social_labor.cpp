#include "macro_sim/core/social_labor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace macro_sim::core {
namespace {

[[nodiscard]] bool finite(double value) noexcept {
    return std::isfinite(value);
}

} // namespace

void EmploymentBook::ensure_person(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1U;
    if (primary_by_person_.size() < size) {
        primary_by_person_.resize(size);
        secondary_by_person_.resize(size);
    }
}

void EmploymentBook::ensure_firm(FirmId firm) {
    const auto size = static_cast<std::size_t>(firm.value()) + 1U;
    if (roster_by_firm_.size() < size) {
        roster_by_firm_.resize(size);
    }
}

Result<JobId> EmploymentBook::hire(PersonId person, FirmId firm,
                                   std::int32_t day, double wage,
                                   double hours, bool secondary) {
    if (!person.valid() || person.value() == 0 || !firm.valid() ||
        firm.value() == 0 || !finite(wage) || wage <= 0.0 ||
        !finite(hours) || hours <= 0.0 || hours > 1.0 ||
        next_id_ == std::numeric_limits<std::uint64_t>::max()) {
        return Status(ErrorCode::invalid_argument,
                      "employment contract is invalid");
    }
    ensure_person(person);
    ensure_firm(firm);
    auto &slot = secondary
                     ? secondary_by_person_[
                           static_cast<std::size_t>(person.value())]
                     : primary_by_person_[
                           static_cast<std::size_t>(person.value())];
    if (slot.valid()) {
        return Status(ErrorCode::already_exists,
                      "person already holds this job class");
    }
    const auto other =
        secondary
            ? primary_by_person_[static_cast<std::size_t>(person.value())]
            : secondary_by_person_[static_cast<std::size_t>(person.value())];
    if (other.valid()) {
        const auto *other_record = get(other);
        if (other_record != nullptr && other_record->firm == firm) {
            return Status(ErrorCode::contract_violation,
                          "person cannot hold two jobs at one firm");
        }
        if (active_hours(person) + hours > 1.0 + 1.0e-12) {
            return Status(ErrorCode::contract_violation,
                          "person job hours exceed capacity");
        }
    }
    const auto id = JobId(next_id_++);
    jobs_.push_back({
        id,
        person,
        firm,
        day,
        -1,
        -1,
        wage,
        hours,
        secondary,
        false,
        true,
        SeparationKind::churn,
    });
    slot = id;
    auto &firm_roster =
        roster_by_firm_[static_cast<std::size_t>(firm.value())];
    roster_position_by_job_.push_back(firm_roster.size());
    firm_roster.push_back(id);
    ++active_count_;
    return id;
}

Status EmploymentBook::separate(JobId job, std::int32_t day,
                                SeparationKind kind) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    const auto index = static_cast<std::size_t>(job.value());
    const auto position = roster_position_by_job_[index];
    auto &firm_roster =
        roster_by_firm_[static_cast<std::size_t>(record->firm.value())];
    if (position == kNoRoster || position >= firm_roster.size() ||
        firm_roster[position] != job) {
        return Status(ErrorCode::invariant_violation,
                      "employment roster index is inconsistent");
    }
    const auto moved = firm_roster.back();
    firm_roster[position] = moved;
    firm_roster.pop_back();
    if (moved != job) {
        roster_position_by_job_[
            static_cast<std::size_t>(moved.value())] = position;
    }
    roster_position_by_job_[index] = kNoRoster;
    auto &slot =
        record->secondary
            ? secondary_by_person_[
                  static_cast<std::size_t>(record->person.value())]
            : primary_by_person_[
                  static_cast<std::size_t>(record->person.value())];
    if (slot != job) {
        return Status(ErrorCode::invariant_violation,
                      "employment person index is inconsistent");
    }
    slot = JobId{};
    if (record->suspended) {
        --suspended_count_;
    }
    record->active = false;
    record->suspended = false;
    record->separation_day = day;
    record->separation_kind = kind;
    --active_count_;
    return Status::success();
}

Status EmploymentBook::suspend(JobId job, std::int32_t day) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    if (record->suspended) {
        return Status(ErrorCode::already_exists,
                      "employment contract is already suspended");
    }
    record->suspended = true;
    record->suspension_day = day;
    ++suspended_count_;
    return Status::success();
}

Status EmploymentBook::recall(JobId job) {
    auto *record = get(job);
    if (record == nullptr || !record->active || !record->suspended) {
        return Status(ErrorCode::not_found,
                      "suspended employment contract is absent");
    }
    record->suspended = false;
    record->suspension_day = -1;
    --suspended_count_;
    return Status::success();
}

Status EmploymentBook::set_hours(JobId job, double hours) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    if (!finite(hours) || hours <= 0.0 || hours > 1.0) {
        return Status(ErrorCode::invalid_argument,
                      "employment hours are invalid");
    }
    const double other_hours =
        active_hours(record->person) -
        (record->suspended ? 0.0 : record->hours);
    if (other_hours + hours > 1.0 + 1.0e-12) {
        return Status(ErrorCode::contract_violation,
                      "person job hours exceed capacity");
    }
    record->hours = hours;
    return Status::success();
}

JobRecord *EmploymentBook::get(JobId id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= jobs_.size()) {
        return nullptr;
    }
    return &jobs_[static_cast<std::size_t>(id.value())];
}

const JobRecord *EmploymentBook::get(JobId id) const noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= jobs_.size()) {
        return nullptr;
    }
    return &jobs_[static_cast<std::size_t>(id.value())];
}

JobId EmploymentBook::primary_job(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= primary_by_person_.size()) {
        return JobId{};
    }
    return primary_by_person_[
        static_cast<std::size_t>(person.value())];
}

JobId EmploymentBook::secondary_job(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= secondary_by_person_.size()) {
        return JobId{};
    }
    return secondary_by_person_[
        static_cast<std::size_t>(person.value())];
}

std::span<const JobId>
EmploymentBook::roster(FirmId firm) const noexcept {
    if (!firm.valid() || firm.value() == 0 ||
        firm.value() >= roster_by_firm_.size()) {
        return {};
    }
    return roster_by_firm_[
        static_cast<std::size_t>(firm.value())];
}

const std::vector<JobRecord> &EmploymentBook::records() const noexcept {
    return jobs_;
}

std::uint64_t EmploymentBook::next_id() const noexcept {
    return next_id_;
}

std::size_t EmploymentBook::active_count() const noexcept {
    return active_count_;
}

std::size_t EmploymentBook::suspended_count() const noexcept {
    return suspended_count_;
}

double EmploymentBook::active_hours(PersonId person) const noexcept {
    double result = 0.0;
    for (const auto job :
         std::array{primary_job(person), secondary_job(person)}) {
        const auto *record = get(job);
        if (record != nullptr && record->active && !record->suspended) {
            result += record->hours;
        }
    }
    return result;
}

double EmploymentBook::active_hours(FirmId firm) const noexcept {
    double result = 0.0;
    for (const auto job : roster(firm)) {
        const auto *record = get(job);
        if (record != nullptr && record->active && !record->suspended) {
            result += record->hours;
        }
    }
    return result;
}

Status EmploymentBook::validate(const PersonStore &persons,
                                const RootState &state,
                                double tolerance) const {
    if (jobs_.empty() || roster_position_by_job_.size() != jobs_.size() ||
        next_id_ != jobs_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "employment store dimensions are inconsistent");
    }
    std::vector<std::uint8_t> roster_seen(jobs_.size(), 0U);
    std::size_t active = 0;
    std::size_t suspended = 0;
    for (std::size_t firm_index = 1;
         firm_index < roster_by_firm_.size(); ++firm_index) {
        const auto firm = FirmId(firm_index);
        if (!roster_by_firm_[firm_index].empty() &&
            state.firms.get(firm) == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "employment roster references an absent firm");
        }
        for (std::size_t position = 0;
             position < roster_by_firm_[firm_index].size(); ++position) {
            const auto job_id = roster_by_firm_[firm_index][position];
            const auto *job = get(job_id);
            if (job == nullptr || !job->active || job->firm != firm ||
                roster_position_by_job_[
                    static_cast<std::size_t>(job_id.value())] != position ||
                roster_seen[
                    static_cast<std::size_t>(job_id.value())] != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "employment roster is inconsistent");
            }
            roster_seen[
                static_cast<std::size_t>(job_id.value())] = 1U;
        }
    }
    for (std::size_t index = 1; index < jobs_.size(); ++index) {
        const auto &job = jobs_[index];
        if (job.id.value() != index || !finite(job.wage) ||
            job.wage <= 0.0 || !finite(job.hours) ||
            job.hours <= 0.0 || job.hours > 1.0 + tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "employment contract is invalid");
        }
        if (!job.active) {
            if (job.separation_day < job.hire_day ||
                roster_seen[index] != 0U ||
                roster_position_by_job_[index] != kNoRoster) {
                return Status(ErrorCode::invariant_violation,
                              "separated employment contract is inconsistent");
            }
            continue;
        }
        ++active;
        suspended += job.suspended ? 1U : 0U;
        const auto expected =
            job.secondary ? secondary_job(job.person)
                          : primary_job(job.person);
        if (!persons.alive(job.person) || expected != job.id ||
            state.firms.get(job.firm) == nullptr ||
            roster_seen[index] != 1U ||
            (job.suspended && job.suspension_day < job.hire_day)) {
            return Status(ErrorCode::invariant_violation,
                          "active employment contract is inconsistent");
        }
    }
    if (active != active_count_ || suspended != suspended_count_) {
        return Status(ErrorCode::invariant_violation,
                      "employment aggregate counters are inconsistent");
    }
    for (const auto person : persons.alive_ids()) {
        const double hours = active_hours(person);
        if (!finite(hours) || hours > 1.0 + tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "person employment hours exceed capacity");
        }
    }
    return Status::success();
}

Status validate_labor_accounts(const LaborAccounts &accounts,
                               double tolerance) noexcept {
    const std::array values{
        accounts.employed_fte,
        accounts.employed_heads,
        accounts.unemployed,
        accounts.suspended,
        accounts.job_guarantee,
        accounts.out_of_labor_force,
        accounts.labor_supply,
        accounts.vacancies,
        accounts.underemployed_heads,
        accounts.underemployment_hours,
        accounts.hires_total,
        accounts.churn_separations_total,
        accounts.layoff_separations_total,
        accounts.cash_layoffs_total,
        accounts.firm_exit_separations_total,
        accounts.death_separations_total,
        accounts.retirement_separations_total,
        accounts.recalls_total,
        accounts.suspensions_total,
        accounts.welfare_quits_total,
        accounts.job_to_job_moves_total,
        accounts.private_fte_inflows_total,
        accounts.private_fte_outflows_total,
        accounts.previous_employed_fte,
        accounts.previous_fte_flow_balance,
        accounts.previous_employed_heads,
        accounts.previous_head_flow_balance,
    };
    if (!std::all_of(values.begin(), values.end(), finite)) {
        return Status(ErrorCode::invariant_violation,
                      "labor accounts contain a non-finite value");
    }
    const auto nonnegative = std::array{
        accounts.employed_fte,
        accounts.employed_heads,
        accounts.unemployed,
        accounts.suspended,
        accounts.job_guarantee,
        accounts.out_of_labor_force,
        accounts.labor_supply,
        accounts.vacancies,
        accounts.underemployed_heads,
        accounts.underemployment_hours,
    };
    if (std::any_of(nonnegative.begin(), nonnegative.end(),
                    [tolerance](double value) {
                        return value < -tolerance;
                    }) ||
        accounts.employed_fte >
            accounts.employed_heads + tolerance) {
        return Status(ErrorCode::invariant_violation,
                      "labor stock is inconsistent");
    }
    const double partition =
        accounts.employed_heads + accounts.unemployed +
        accounts.suspended + accounts.job_guarantee;
    if (std::abs(partition - accounts.labor_supply) >
        tolerance * std::max(1.0, accounts.labor_supply)) {
        return Status(ErrorCode::invariant_violation,
                      "labor force partition is inconsistent");
    }
    return Status::success();
}

} // namespace macro_sim::core
