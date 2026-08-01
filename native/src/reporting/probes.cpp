#include "macro_sim/reporting/probes.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace macro_sim::reporting {
namespace {

[[nodiscard]] Status validate_request(const simulation::M9World &world,
                                      EconomyId economy,
                                      std::size_t maximum_rows) noexcept {
    if (!economy.valid() ||
        economy.value() >= static_cast<std::uint64_t>(world.economy_count())) {
        return Status(ErrorCode::not_found,
                      "probe economy ID is outside the World");
    }
    if (maximum_rows == 0U || maximum_rows > kMaximumProbePageRows) {
        return Status(ErrorCode::out_of_range,
                      "probe page size is outside the supported range");
    }
    if (world.economy_root(economy) == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "probe economy has no committed native state");
    }
    return Status::success();
}

[[nodiscard]] double account_balance(const core::RootState &root,
                                     AccountId account) noexcept {
    const auto value = root.postings.balance(account);
    return value.ok() ? value.get_if()->value() : 0.0;
}

[[nodiscard]] std::vector<double>
debt_by_owner(const core::RootState &root, core::OwnerKind kind,
              std::size_t count) {
    std::vector<double> output(count + 1U, 0.0);
    for (const auto &loan : root.loans.records()) {
        if (!loan.active || loan.borrower.kind() != kind ||
            loan.borrower.value() >= output.size()) {
            continue;
        }
        output[loan.borrower.value()] += loan.principal.value();
    }
    return output;
}

[[nodiscard]] const simulation::FirmLifecycleRecord *
firm_lifecycle(const simulation::M6Runtime &runtime, FirmId firm) noexcept {
    const auto index = static_cast<std::size_t>(firm.value());
    return index < runtime.firms.size() && runtime.firms[index].firm == firm
               ? &runtime.firms[index]
               : nullptr;
}

[[nodiscard]] const core::EquityContract *
issuer_equity(const core::SecurityBook &securities,
              core::OwnerId issuer) noexcept {
    for (const auto security : securities.securities_for_issuer(issuer)) {
        if (security.kind() != core::SecurityKind::equity) {
            continue;
        }
        const auto *contract =
            securities.get(EquityId(security.value()));
        if (contract != nullptr && contract->active) {
            return contract;
        }
    }
    return nullptr;
}

[[nodiscard]] double security_market_value(
    const core::SecurityBook &securities,
    const core::SecurityLot &lot) noexcept {
    if (lot.security.kind() == core::SecurityKind::equity) {
        const auto *contract =
            securities.get(EquityId(lot.security.value()));
        return contract == nullptr || !contract->active
                   ? 0.0
                   : lot.units * contract->price.value();
    }
    const auto *contract = securities.get(BondId(lot.security.value()));
    return contract == nullptr || !contract->active ? 0.0 : lot.units;
}

void fill_person_assets(PersonProbeRow &row, const core::RootState &root,
                        const simulation::M6Runtime &financial,
                        const simulation::M7Runtime &population) {
    const auto &ownership = population.beneficial_ownership;
    double allocation_share = 0.0;
    for (const auto lot_id : ownership.lots_for_person(row.id)) {
        const auto *beneficial = ownership.get(lot_id);
        if (beneficial == nullptr || !beneficial->is_active()) {
            continue;
        }
        const auto household = beneficial->asset.household;
        const auto *household_component = root.households.get(household);
        if (household_component == nullptr) {
            continue;
        }
        const double share = beneficial->share;
        switch (beneficial->asset.kind) {
        case core::BeneficialAssetKind::household_cash:
            row.cash += share * std::max(
                0.0, account_balance(
                         root, household_component->primary_account));
            allocation_share += share;
            break;
        case core::BeneficialAssetKind::household_debt: {
            const auto *loan =
                root.loans.get(LoanId(beneficial->asset.value));
            if (loan != nullptr && loan->active) {
                row.debt += share * std::max(
                    0.0, loan->principal.value());
            }
            break;
        }
        case core::BeneficialAssetKind::security_position: {
            const auto holder = core::OwnerId::household(household);
            for (const auto position_id :
                 financial.securities.lots_for_holder(holder)) {
                const auto *position =
                    financial.securities.get(position_id);
                if (position == nullptr || !position->active()) {
                    continue;
                }
                const double value =
                    share * security_market_value(
                                financial.securities, *position);
                if (position->security.kind() == core::SecurityKind::bond) {
                    row.bonds += value;
                    continue;
                }
                const auto *contract = financial.securities.get(
                    EquityId(position->security.value()));
                if (contract != nullptr &&
                    contract->issuer_kind ==
                        core::EquityIssuerKind::bank) {
                    row.bank_equity += value;
                } else {
                    row.firm_equity += value;
                }
            }
            break;
        }
        case core::BeneficialAssetKind::generic_position:
            break;
        }
    }
    if (const auto *household = root.households.get(row.household);
        household != nullptr) {
        row.allocated_income =
            allocation_share * household->income_realized;
        row.allocated_consumption =
            allocation_share * household->spent;
    }
    row.gross_assets =
        row.cash + row.firm_equity + row.bank_equity + row.bonds;
    row.net_worth = row.gross_assets - row.debt;
}

[[nodiscard]] PersonProbeRow make_person_probe_row(
    const core::PersonRecord &person,
    const simulation::M7Runtime &population,
    const core::RootState *root,
    const simulation::M6Runtime *financial) {
    PersonProbeRow row;
    row.id = person.id;
    row.sex = person.sex;
    row.birth_day = person.birth_day;
    row.death_day = person.death_day;
    const auto age_at =
        person.alive ? population.current_calendar_day : person.death_day;
    row.age_days = std::max(0, age_at - person.birth_day);
    row.mother = person.mother;
    row.father = person.father;
    row.partner = person.partner;
    row.guardian = person.guardian;
    row.household = person.household;
    row.primary_job = population.employment.primary_job(person.id);
    row.secondary_job = population.employment.secondary_job(person.id);
    row.efficiency = person.efficiency;
    if (financial != nullptr && root != nullptr) {
        fill_person_assets(row, *root, *financial, population);
    }
    row.participating = person.participating;
    row.searching = person.searching;
    row.alive = person.alive;
    return row;
}

[[nodiscard]] JobProbeRow
make_job_probe_row(const core::JobRecord &job) noexcept {
    return JobProbeRow{
        job.id,
        job.person,
        job.firm,
        job.hire_day,
        job.separation_day,
        job.suspension_day,
        job.wage,
        job.hours,
        job.secondary,
        job.suspended,
        job.active,
    };
}

template <typename Row>
void finish_page(ProbePageInfo &page, std::vector<Row> &rows,
                 std::size_t maximum_rows) {
    if (rows.size() > maximum_rows) {
        page.has_more = true;
        rows.resize(maximum_rows);
    }
    if (!rows.empty()) {
        page.next_after_id = rows.back().id.value();
    }
}

[[nodiscard]] double shock_intensity(
    const simulation::ShockSpec &shock, Tick boundary) noexcept {
    if (boundary.value() < shock.start.value() ||
        boundary.value() >= shock.start.value() + shock.duration) {
        return 0.0;
    }
    if (shock.kind == simulation::ShockKind::capital_destruction) {
        return boundary == shock.start ? 1.0 : 0.0;
    }
    const auto elapsed = boundary.value() - shock.start.value();
    if (shock.ramp_in_ticks > 0U || shock.ramp_out_ticks > 0U) {
        double intensity = 1.0;
        if (shock.ramp_in_ticks > 0U) {
            intensity = std::min(
                intensity, static_cast<double>(elapsed + 1U) /
                               static_cast<double>(shock.ramp_in_ticks));
        }
        if (shock.ramp_out_ticks > 0U) {
            const auto remaining =
                shock.start.value() + shock.duration - boundary.value();
            intensity = std::min(
                intensity, static_cast<double>(remaining) /
                               static_cast<double>(shock.ramp_out_ticks));
        }
        return std::clamp(intensity, 0.0, 1.0);
    }
    if (shock.shape == simulation::ShockShape::step ||
        shock.duration <= 1U) {
        return 1.0;
    }
    if (shock.shape == simulation::ShockShape::linear) {
        return static_cast<double>(elapsed + 1U) /
               static_cast<double>(shock.duration);
    }
    const double position =
        static_cast<double>(elapsed) /
        static_cast<double>(std::max<std::uint64_t>(
            1U, shock.duration - 1U));
    return 1.0 - std::abs(2.0 * position - 1.0);
}

} // namespace

Result<HouseholdProbePage>
probe_households(const simulation::M9World &world, EconomyId economy,
                 std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto &root = *world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    const auto debt = debt_by_owner(
        root, core::OwnerKind::household, root.households.slot_count());
    HouseholdProbePage output;
    output.page = {world.tick(), economy, after_id,
                   static_cast<std::uint64_t>(root.households.alive_count()),
                   false};
    output.rows.reserve(maximum_rows + 1U);
    root.households.for_each_alive(
        [&](HouseholdId id, const core::HouseholdComponent &household) {
            if (id.value() <= after_id ||
                output.rows.size() > maximum_rows) {
                return;
            }
            HouseholdProbeRow row;
            row.id = id;
            row.account = household.primary_account;
            row.cash = account_balance(root, row.account);
            if (id.value() < debt.size()) {
                row.debt = debt[id.value()];
            }
            row.income_expected = household.income_expected;
            row.income_realized = household.income_realized;
            row.consumption_budget = household.consumption_budget;
            row.spent = household.spent;
            row.labor_sold = household.labor_sold;
            if (population != nullptr) {
                const auto members = population->membership.members(id);
                row.members.assign(members.begin(), members.end());
            }
            output.rows.push_back(std::move(row));
        });
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<FirmProbePage>
probe_firms(const simulation::M9World &world, EconomyId economy,
            std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto &root = *world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    const auto debt =
        debt_by_owner(root, core::OwnerKind::firm, root.firms.slot_count());
    std::vector<std::uint8_t> active(root.firms.slot_count() + 1U, 1U);
    if (financial != nullptr) {
        for (const auto &lifecycle : financial->firms) {
            if (lifecycle.firm.value() < active.size()) {
                active[lifecycle.firm.value()] =
                    static_cast<std::uint8_t>(lifecycle.active);
            }
        }
    }
    FirmProbePage output;
    output.page = {world.tick(), economy, after_id,
                   static_cast<std::uint64_t>(root.firms.alive_count()), false};
    output.rows.reserve(maximum_rows + 1U);
    root.firms.for_each_alive(
        [&](FirmId id, const core::FirmComponent &firm) {
            if (id.value() <= after_id ||
                output.rows.size() > maximum_rows) {
                return;
            }
            FirmProbeRow row;
            row.id = id;
            row.sector = firm.sector;
            row.account = firm.primary_account;
            row.cash = account_balance(root, row.account);
            if (id.value() < debt.size()) {
                row.debt = debt[id.value()];
            }
            row.goods_inventory = firm.goods_inventory.value();
            row.physical_capital = firm.physical_capital.value();
            row.productivity = firm.productivity;
            row.total_factor_productivity = firm.total_factor_productivity;
            row.posted_price = firm.posted_price.value();
            row.posted_wage = firm.posted_wage.value();
            row.markup = firm.markup;
            row.demand_expected = firm.demand_expected;
            row.previous_sales = firm.sales_previous;
            row.previous_hires = firm.hired_previous;
            if (financial != nullptr) {
                if (const auto *lifecycle =
                        firm_lifecycle(*financial, id);
                    lifecycle != nullptr) {
                    row.book_equity = lifecycle->statement.book_equity;
                    row.earnings = lifecycle->statement.earnings;
                    row.interest_arrears =
                        lifecycle->statement.interest_arrears;
                    row.eligible_collateral_value =
                        lifecycle->statement.eligible_collateral_value;
                    row.borrowing_base_headroom =
                        lifecycle->statement.borrowing_base_headroom;
                    row.residual_income_ema =
                        lifecycle->residual_income_ema;
                    row.tobin_q_ema = lifecycle->tobin_q_ema;
                    row.insolvent_days = lifecycle->insolvent_days;
                    row.shell_days = lifecycle->shell_days;
                    row.sector_switch_pressure_days =
                        lifecycle->switch_pressure_days;
                    row.defaulted = lifecycle->defaulted;
                }
                if (const auto *equity = issuer_equity(
                        financial->securities,
                        core::OwnerId::firm(id));
                    equity != nullptr) {
                    row.equity = equity->id;
                    row.outstanding_shares =
                        equity->outstanding_shares;
                    row.share_price = equity->price.value();
                    row.last_share_price =
                        equity->last_price.value();
                    row.peak_share_price =
                        equity->peak_price.value();
                    row.fundamental_per_share =
                        equity->fundamental.value();
                    row.share_trend = equity->trend;
                }
            }
            row.active =
                id.value() >= active.size() || active[id.value()] != 0U;
            if (population != nullptr) {
                const auto jobs = population->employment.roster(id);
                row.employees.reserve(jobs.size());
                for (const auto job_id : jobs) {
                    const auto *job = population->employment.get(job_id);
                    if (job != nullptr && job->active) {
                        row.employees.push_back(job->person);
                    }
                }
            }
            output.rows.push_back(std::move(row));
        });
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<BankProbePage>
probe_banks(const simulation::M9World &world, EconomyId economy,
            std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto &root = *world.economy_root(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    std::vector<double> principal(root.banks.slot_count() + 1U, 0.0);
    for (const auto &loan : root.loans.records()) {
        if (loan.active && loan.lender.value() < principal.size()) {
            principal[loan.lender.value()] += loan.principal.value();
        }
    }
    BankProbePage output;
    output.page = {world.tick(), economy, after_id,
                   static_cast<std::uint64_t>(root.banks.alive_count()), false};
    output.rows.reserve(maximum_rows + 1U);
    root.banks.for_each_alive(
        [&](BankId id, const core::BankComponent &bank) {
            if (id.value() <= after_id ||
                output.rows.size() > maximum_rows) {
                return;
            }
            BankProbeRow row;
            row.id = id;
            row.cash_account = bank.cash_account;
            row.reserve_node = bank.settlement_node;
            row.cash = account_balance(root, bank.cash_account);
            const auto reserve = root.reserves.balance(bank.settlement_node);
            row.reserves =
                reserve.ok() ? reserve.get_if()->value() : 0.0;
            if (id.value() < principal.size()) {
                row.loan_principal = principal[id.value()];
            }
            if (const auto *capital = root.bank_capital.get(id);
                capital != nullptr) {
                row.opening_capital = capital->opening_capital;
                row.closing_capital = capital->closing_capital;
                row.deposit_interest_arrears =
                    capital->deposit_interest_arrears;
                row.resolved = capital->resolved;
            }
            row.leverage_appetite = bank.leverage_appetite;
            row.loan_spread = bank.loan_spread;
            row.deposit_spread = bank.deposit_spread;
            if (financial != nullptr) {
                if (const auto *equity = issuer_equity(
                        financial->securities,
                        core::OwnerId::bank(id));
                    equity != nullptr) {
                    row.equity = equity->id;
                    row.outstanding_shares =
                        equity->outstanding_shares;
                    row.share_price = equity->price.value();
                    row.last_share_price =
                        equity->last_price.value();
                    row.peak_share_price =
                        equity->peak_price.value();
                    row.fundamental_per_share =
                        equity->fundamental.value();
                    row.share_trend = equity->trend;
                }
            }
            row.alive = bank.alive;
            output.rows.push_back(std::move(row));
        });
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<PersonProbePage>
probe_persons(const simulation::M9World &world, EconomyId economy,
              std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *population = world.economy_population_runtime(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    const auto *root = world.economy_root(economy);
    if (population == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "person probe requires the native population module");
    }
    PersonProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(population->persons.total_count()), false};
    output.rows.reserve(maximum_rows + 1U);
    for (std::size_t index = 1U;
         index < population->persons.records().size(); ++index) {
        const auto &person = population->persons.records()[index];
        if (person.id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(
            make_person_probe_row(person, *population, root, financial));
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<JobProbePage>
probe_jobs(const simulation::M9World &world, EconomyId economy,
           std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *population = world.economy_population_runtime(economy);
    if (population == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "job probe requires the native population module");
    }
    JobProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(
            population->employment.records().size() - 1U),
        false};
    output.rows.reserve(maximum_rows + 1U);
    for (std::size_t index = 1U;
         index < population->employment.records().size(); ++index) {
        const auto &job = population->employment.records()[index];
        if (job.id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(make_job_probe_row(job));
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<JobProbePage>
probe_jobs_for_household(const simulation::M9World &world, EconomyId economy,
                         HouseholdId household, std::uint64_t after_id,
                         std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *root = world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    if (root == nullptr || !household.valid() ||
        root->households.get(household) == nullptr) {
        return Status(ErrorCode::not_found,
                      "household job probe requires an existing household");
    }
    if (population == nullptr) {
        return Status(
            ErrorCode::invalid_handle,
            "household job probe requires the native population module");
    }

    std::vector<JobId> jobs;
    const auto members = population->membership.members(household);
    jobs.reserve(members.size() * 2U);
    for (const auto person : members) {
        for (const auto job : {
                 population->employment.primary_job(person),
                 population->employment.secondary_job(person)}) {
            if (job.valid()) {
                jobs.push_back(job);
            }
        }
    }
    std::sort(jobs.begin(), jobs.end(),
              [](JobId left, JobId right) {
                  return left.value() < right.value();
              });
    jobs.erase(std::unique(jobs.begin(), jobs.end()), jobs.end());

    JobProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(jobs.size()), false};
    output.rows.reserve(std::min(jobs.size(), maximum_rows + 1U));
    for (const auto job_id : jobs) {
        if (job_id.value() <= after_id) {
            continue;
        }
        const auto *job = population->employment.get(job_id);
        if (job == nullptr) {
            continue;
        }
        output.rows.push_back(make_job_probe_row(*job));
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<JobProbePage>
probe_jobs_for_firm(const simulation::M9World &world, EconomyId economy,
                    FirmId firm, std::uint64_t after_id,
                    std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *root = world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    if (root == nullptr || !firm.valid() || root->firms.get(firm) == nullptr) {
        return Status(ErrorCode::not_found,
                      "firm job probe requires an existing firm");
    }
    if (population == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "firm job probe requires the native population module");
    }
    const auto roster = population->employment.roster(firm);
    JobProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(roster.size()), false};
    output.rows.reserve(std::min(roster.size(), maximum_rows + 1U));
    for (const auto job_id : roster) {
        const auto *job = population->employment.get(job_id);
        if (job == nullptr || !job->active || job->id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(make_job_probe_row(*job));
    }
    std::sort(output.rows.begin(), output.rows.end(),
              [](const JobProbeRow &left, const JobProbeRow &right) {
                  return left.id.value() < right.id.value();
              });
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<PersonProbePage>
probe_persons_for_household(const simulation::M9World &world,
                            EconomyId economy, HouseholdId household,
                            std::uint64_t after_id,
                            std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *root = world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    if (root == nullptr || !household.valid() ||
        root->households.get(household) == nullptr) {
        return Status(
            ErrorCode::not_found,
            "household person probe requires an existing household");
    }
    if (population == nullptr) {
        return Status(
            ErrorCode::invalid_handle,
            "household person probe requires the native population module");
    }

    const auto members = population->membership.members(household);
    PersonProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(members.size()), false};
    output.rows.reserve(std::min(members.size(), maximum_rows + 1U));
    for (const auto person_id : members) {
        if (person_id.value() <= after_id) {
            continue;
        }
        const auto *person = population->persons.get(person_id);
        if (person == nullptr) {
            continue;
        }
        output.rows.push_back(
            make_person_probe_row(*person, *population, root, financial));
    }
    std::sort(output.rows.begin(), output.rows.end(),
              [](const PersonProbeRow &left, const PersonProbeRow &right) {
                  return left.id.value() < right.id.value();
              });
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<PersonProbePage>
probe_persons_for_firm(const simulation::M9World &world, EconomyId economy,
                       FirmId firm, std::uint64_t after_id,
                       std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *root = world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    const auto *financial = world.economy_financial_runtime(economy);
    if (root == nullptr || !firm.valid() || root->firms.get(firm) == nullptr) {
        return Status(ErrorCode::not_found,
                      "firm person probe requires an existing firm");
    }
    if (population == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "firm person probe requires the native population module");
    }
    std::vector<PersonId> people;
    const auto roster = population->employment.roster(firm);
    people.reserve(roster.size());
    for (const auto job_id : roster) {
        const auto *job = population->employment.get(job_id);
        if (job != nullptr && job->active) {
            people.push_back(job->person);
        }
    }
    std::sort(people.begin(), people.end(),
              [](PersonId left, PersonId right) {
                  return left.value() < right.value();
              });
    people.erase(
        std::unique(people.begin(), people.end(),
                    [](PersonId left, PersonId right) {
                        return left.value() == right.value();
                    }),
        people.end());

    PersonProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(people.size()), false};
    output.rows.reserve(std::min(people.size(), maximum_rows + 1U));
    for (const auto person_id : people) {
        if (person_id.value() <= after_id) {
            continue;
        }
        const auto *person = population->persons.get(person_id);
        if (person == nullptr) {
            continue;
        }
        output.rows.push_back(
            make_person_probe_row(*person, *population, root, financial));
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<DwellingProbePage>
probe_dwellings(const simulation::M9World &world, EconomyId economy,
                std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *domestic = world.economy_runtime(economy);
    if (domestic == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "dwelling probe requires the native housing module");
    }
    DwellingProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(domestic->properties.active_count()), false};
    output.rows.reserve(maximum_rows + 1U);
    for (const auto &dwelling : domestic->properties.records()) {
        if (!dwelling.active || dwelling.id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(DwellingProbeRow{
            dwelling.id,
            dwelling.owner.kind(),
            dwelling.owner.value(),
            dwelling.occupant,
            dwelling.collateral,
            dwelling.floor_area,
            dwelling.quality,
            static_cast<double>(dwelling.location),
            static_cast<std::int32_t>(dwelling.age_days),
            dwelling.active,
        });
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<EquityProbePage>
probe_equities(const simulation::M9World &world, EconomyId economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *financial = world.economy_financial_runtime(economy);
    if (financial == nullptr) {
        return Status(ErrorCode::invalid_handle,
                      "equity probe requires the native financial module");
    }
    EquityProbePage output;
    std::uint64_t active_count = 0U;
    for (const auto &equity : financial->securities.equities()) {
        if (equity.active) {
            ++active_count;
        }
    }
    output.page = {
        world.tick(), economy, after_id, active_count, false};
    output.rows.reserve(maximum_rows + 1U);
    for (const auto &equity : financial->securities.equities()) {
        if (!equity.active || equity.id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(EquityProbeRow{
            equity.id,
            equity.issuer_kind,
            equity.issuer,
            equity.issuer_account,
            equity.currency,
            equity.outstanding_shares,
            equity.price.value(),
            equity.last_price.value(),
            equity.peak_price.value(),
            equity.fundamental.value(),
            equity.trend,
            equity.income_signal,
            equity.active,
            equity.resolved,
        });
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<SecurityPositionProbePage>
probe_security_positions(const simulation::M9World &world,
                         EconomyId economy, std::uint64_t after_id,
                         std::size_t maximum_rows) {
    auto status = validate_request(world, economy, maximum_rows);
    if (!status.ok()) {
        return status;
    }
    const auto *financial = world.economy_financial_runtime(economy);
    if (financial == nullptr) {
        return Status(
            ErrorCode::invalid_handle,
            "security-position probe requires the native financial module");
    }
    SecurityPositionProbePage output;
    output.page = {
        world.tick(), economy, after_id,
        static_cast<std::uint64_t>(
            financial->securities.active_lot_count()),
        false};
    output.rows.reserve(maximum_rows + 1U);
    const auto &positions = financial->securities.lots();
    for (std::size_t index = 0U; index < positions.size(); ++index) {
        const auto id = SecurityLotId(
            static_cast<std::uint32_t>(index + 1U));
        const auto &position = positions[index];
        if (!position.active() || id.value() <= after_id) {
            continue;
        }
        output.rows.push_back(SecurityPositionProbeRow{
            id,
            position.security.kind(),
            position.security.value(),
            position.holder.kind(),
            position.holder.value(),
            position.units,
            position.cost_basis.value(),
            security_market_value(financial->securities, position),
        });
        if (output.rows.size() > maximum_rows) {
            break;
        }
    }
    finish_page(output.page, output.rows, maximum_rows);
    return output;
}

Result<EconomyDiagnosticProbe>
probe_economy_diagnostics(const simulation::M9World &world,
                          EconomyId economy) {
    auto status = validate_request(world, economy, 1U);
    if (!status.ok()) {
        return status;
    }
    const auto &root = *world.economy_root(economy);
    const auto *population = world.economy_population_runtime(economy);
    const auto *domestic = world.economy_runtime(economy);
    EconomyDiagnosticProbe output;
    output.boundary = world.tick();
    output.economy = economy;
    output.digest = world.digest();
    output.dealer_valuation = world.last_metrics().dealer_valuation;
    output.peg_count = world.pegs().size();
    output.pegs_intact = std::all_of(
        world.pegs().begin(), world.pegs().end(),
        [](const simulation::PegRuntime &peg) { return peg.intact; });
    output.households = root.households.alive_count();
    output.firms = root.firms.alive_count();
    root.banks.for_each_alive(
        [&output](BankId, const core::BankComponent &bank) {
            output.banks += bank.alive ? 1U : 0U;
        });
    output.account_balance_total = root.postings.total_deposits().value();
    output.loan_principal_total = root.loans.total_principal().value();
    output.reserve_total = root.reserves.total_reserves().value();
    root.firms.for_each_alive(
        [&](FirmId, const core::FirmComponent &firm) {
            output.goods_inventory_total += firm.goods_inventory.value();
            output.physical_capital_total += firm.physical_capital.value();
        });
    if (population != nullptr) {
        output.persons_alive = population->persons.alive_count();
        output.jobs_active = population->employment.active_count();
    }
    if (domestic != nullptr) {
        output.dwellings_active = domestic->properties.active_count();
        output.energy_stock_total = domestic->strategic_reserve_stock;
        for (const auto &producer : domestic->energy_producers) {
            if (producer.active) {
                output.energy_stock_total += producer.inventory;
            }
        }
        for (const auto &input : domestic->energy_inputs) {
            if (input.active) {
                output.energy_stock_total += input.stock;
            }
        }
    }
    return output;
}

Result<std::vector<ShockBulletinProbeRow>>
probe_shock_bulletins(const simulation::M9World &world, EconomyId economy,
                      Tick as_of_boundary) {
    auto status = validate_request(world, economy, 1U);
    if (!status.ok()) {
        return status;
    }
    if (as_of_boundary > world.tick()) {
        return Status(ErrorCode::out_of_range,
                      "shock bulletin boundary is in the future");
    }
    std::vector<ShockBulletinProbeRow> output;
    for (const auto &shock : world.shocks()) {
        if ((shock.economy.has_value() && *shock.economy != economy) ||
            shock.announcement.value_or(shock.start) > as_of_boundary) {
            continue;
        }
        const auto expected_end =
            Tick(shock.start.value() + shock.duration);
        const bool one_shot =
            shock.kind == simulation::ShockKind::capital_destruction;
        if ((one_shot && shock.start < as_of_boundary) ||
            (!one_shot && expected_end <= as_of_boundary)) {
            continue;
        }
        const double intensity = shock_intensity(shock, as_of_boundary);
        ShockBulletinStatus bulletin_status =
            ShockBulletinStatus::upcoming;
        if (as_of_boundary >= shock.start) {
            bulletin_status =
                one_shot ? ShockBulletinStatus::realizing
                         : ShockBulletinStatus::active;
        }
        output.push_back(ShockBulletinProbeRow{
            shock.id,
            shock.kind,
            shock.economy,
            shock.announcement.value_or(shock.start),
            shock.start,
            expected_end,
            shock.duration,
            shock.magnitude,
            intensity,
            bulletin_status,
            shock.sector,
        });
    }
    std::sort(
        output.begin(), output.end(),
        [](const ShockBulletinProbeRow &left,
           const ShockBulletinProbeRow &right) {
            return left.start == right.start
                       ? left.shock_id < right.shock_id
                       : left.start < right.start;
        });
    return output;
}

} // namespace macro_sim::reporting
