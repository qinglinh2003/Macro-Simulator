#include <array>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/string_view.h>
#include <nanobind/stl/vector.h>

#include "macro_sim/control/m10.hpp"
#include "macro_sim/control/m11_artifact.hpp"
#include "macro_sim/control/m11_policy.hpp"
#include "macro_sim/desktop/m11_new_game.hpp"
#include "macro_sim/engine_session.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/rng.hpp"
#include "macro_sim/simulation/m9.hpp"
#include "macro_sim/version.hpp"
#include "python_m3_bindings.hpp"

namespace nb = nanobind;

namespace {

struct PythonScalar final {
    macro_sim::generated::InputKind kind;
    double number;
    std::string text;
};

PythonScalar scalar_from_python(nb::handle value) {
    using macro_sim::generated::InputKind;
    if (value.is_none()) {
        return {InputKind::null_value, 0.0, ""};
    }
    if (nb::isinstance<nb::bool_>(value)) {
        return {
            InputKind::boolean,
            nb::cast<bool>(value) ? 1.0 : 0.0,
            "",
        };
    }
    if (nb::isinstance<nb::int_>(value)) {
        return {
            InputKind::integer,
            static_cast<double>(nb::cast<std::int64_t>(value)),
            "",
        };
    }
    if (nb::isinstance<nb::float_>(value)) {
        return {InputKind::number, nb::cast<double>(value), ""};
    }
    if (nb::isinstance<nb::str>(value)) {
        return {InputKind::string, 0.0, nb::cast<std::string>(value)};
    }
    return {InputKind::id_set, 0.0, ""};
}

void require_status(const macro_sim::Status &status) {
    if (!status.ok()) {
        throw std::runtime_error(
            std::string(macro_sim::error_code_name(status.code())) + ": " +
            std::string(status.message()));
    }
}

macro_sim::core::StateDigest digest_from_hex(std::string_view value) {
    if (value.size() != 64U) {
        throw std::runtime_error("invalid_argument: digest must contain 64 hex digits");
    }
    const auto nibble = [](char character) -> std::uint8_t {
        if (character >= '0' && character <= '9') {
            return static_cast<std::uint8_t>(character - '0');
        }
        if (character >= 'a' && character <= 'f') {
            return static_cast<std::uint8_t>(character - 'a' + 10);
        }
        if (character >= 'A' && character <= 'F') {
            return static_cast<std::uint8_t>(character - 'A' + 10);
        }
        throw std::runtime_error("invalid_argument: digest contains non-hex data");
    };
    macro_sim::core::StateDigest output;
    for (std::size_t index = 0; index < output.bytes.size(); ++index) {
        output.bytes[index] = static_cast<std::uint8_t>(
            (nibble(value[index * 2U]) << 4U) | nibble(value[index * 2U + 1U]));
    }
    return output;
}

nb::dict m10_metric_frame_to_python(
    const macro_sim::reporting::MetricFrame &frame,
    std::span<const macro_sim::reporting::MetricDescriptor> descriptors =
        macro_sim::reporting::public_metric_descriptors()) {
    nb::dict output;
    output["tick"] = frame.tick.value();
    output["economy_count"] = frame.economy_count;
    nb::list economies;
    for (std::size_t economy = 0; economy < frame.economy_count; ++economy) {
        nb::dict values;
        for (std::size_t metric = 0; metric < descriptors.size(); ++metric) {
            const auto value = frame.value(economy, metric);
            const auto key = nb::str(descriptors[metric].stable_id.data(),
                                     descriptors[metric].stable_id.size());
            values[key] = value.ok() ? nb::cast(*value.get_if()) : nb::none();
        }
        economies.append(std::move(values));
    }
    output["economies"] = std::move(economies);
    return output;
}

nb::dict
m10_maintained_metric_frame_to_python(const macro_sim::reporting::MetricFrame &frame) {
    return m10_metric_frame_to_python(frame,
                                      macro_sim::reporting::metric_descriptors());
}

nb::dict probe_page_info_to_python(const macro_sim::reporting::ProbePageInfo &page) {
    nb::dict output;
    output["boundary"] = page.boundary.value();
    output["economy_id"] = page.economy.value();
    output["next_after_id"] = page.next_after_id;
    output["total_rows"] = page.total_rows;
    output["has_more"] = page.has_more;
    return output;
}

nb::dict
household_probe_to_python(const macro_sim::reporting::HouseholdProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["account_id"] = row.account.value();
        item["cash"] = row.cash;
        item["debt"] = row.debt;
        item["income_expected"] = row.income_expected;
        item["income_realized"] = row.income_realized;
        item["consumption_budget"] = row.consumption_budget;
        item["spent"] = row.spent;
        item["labor_sold"] = row.labor_sold;
        nb::list members;
        for (const auto person : row.members) {
            members.append(person.value());
        }
        item["member_ids"] = std::move(members);
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict firm_probe_to_python(const macro_sim::reporting::FirmProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["sector"] = static_cast<std::uint8_t>(row.sector);
        item["account_id"] = row.account.value();
        item["cash"] = row.cash;
        item["debt"] = row.debt;
        item["goods_inventory"] = row.goods_inventory;
        item["physical_capital"] = row.physical_capital;
        item["productivity"] = row.productivity;
        item["total_factor_productivity"] = row.total_factor_productivity;
        item["posted_price"] = row.posted_price;
        item["posted_wage"] = row.posted_wage;
        item["markup"] = row.markup;
        item["demand_expected"] = row.demand_expected;
        item["previous_sales"] = row.previous_sales;
        item["previous_hires"] = row.previous_hires;
        item["book_equity"] = row.book_equity;
        item["earnings"] = row.earnings;
        item["interest_arrears"] = row.interest_arrears;
        item["eligible_collateral_value"] = row.eligible_collateral_value;
        item["borrowing_base_headroom"] = row.borrowing_base_headroom;
        item["residual_income_ema"] = row.residual_income_ema;
        item["tobin_q_ema"] = row.tobin_q_ema;
        item["insolvent_days"] = row.insolvent_days;
        item["shell_days"] = row.shell_days;
        item["sector_switch_pressure_days"] = row.sector_switch_pressure_days;
        item["defaulted"] = row.defaulted;
        item["equity_id"] = row.equity.value();
        item["outstanding_shares"] = row.outstanding_shares;
        item["share_price"] = row.share_price;
        item["last_share_price"] = row.last_share_price;
        item["peak_share_price"] = row.peak_share_price;
        item["fundamental_per_share"] = row.fundamental_per_share;
        item["share_trend"] = row.share_trend;
        item["active"] = row.active;
        nb::list employees;
        for (const auto person : row.employees) {
            employees.append(person.value());
        }
        item["employee_ids"] = std::move(employees);
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict bank_probe_to_python(const macro_sim::reporting::BankProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["cash_account_id"] = row.cash_account.value();
        item["reserve_node_id"] = row.reserve_node.value();
        item["cash"] = row.cash;
        item["reserves"] = row.reserves;
        item["loan_principal"] = row.loan_principal;
        item["opening_capital"] = row.opening_capital;
        item["closing_capital"] = row.closing_capital;
        item["deposit_interest_arrears"] = row.deposit_interest_arrears;
        item["leverage_appetite"] = row.leverage_appetite;
        item["loan_spread"] = row.loan_spread;
        item["deposit_spread"] = row.deposit_spread;
        item["equity_id"] = row.equity.value();
        item["outstanding_shares"] = row.outstanding_shares;
        item["share_price"] = row.share_price;
        item["last_share_price"] = row.last_share_price;
        item["peak_share_price"] = row.peak_share_price;
        item["fundamental_per_share"] = row.fundamental_per_share;
        item["share_trend"] = row.share_trend;
        item["alive"] = row.alive;
        item["resolved"] = row.resolved;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict person_probe_to_python(const macro_sim::reporting::PersonProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["sex"] = static_cast<std::uint8_t>(row.sex);
        item["birth_day"] = row.birth_day;
        item["death_day"] = row.death_day;
        item["age_days"] = row.age_days;
        item["mother_id"] = row.mother.value();
        item["father_id"] = row.father.value();
        item["partner_id"] = row.partner.value();
        item["guardian_id"] = row.guardian.value();
        item["household_id"] = row.household.value();
        item["primary_job_id"] = row.primary_job.value();
        item["secondary_job_id"] = row.secondary_job.value();
        item["efficiency"] = row.efficiency;
        item["cash"] = row.cash;
        item["debt"] = row.debt;
        item["firm_equity"] = row.firm_equity;
        item["bank_equity"] = row.bank_equity;
        item["bonds"] = row.bonds;
        item["gross_assets"] = row.gross_assets;
        item["net_worth"] = row.net_worth;
        item["allocated_income"] = row.allocated_income;
        item["allocated_consumption"] = row.allocated_consumption;
        item["participating"] = row.participating;
        item["searching"] = row.searching;
        item["alive"] = row.alive;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict job_probe_to_python(const macro_sim::reporting::JobProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["person_id"] = row.person.value();
        item["firm_id"] = row.firm.value();
        item["hire_day"] = row.hire_day;
        item["separation_day"] = row.separation_day;
        item["wage"] = row.wage;
        item["hours"] = row.hours;
        item["secondary"] = row.secondary;
        item["suspended"] = row.suspended;
        item["active"] = row.active;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict dwelling_probe_to_python(const macro_sim::reporting::DwellingProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["owner_kind"] = static_cast<std::uint8_t>(row.owner_kind);
        item["owner_id"] = row.owner_id;
        item["occupant_household_id"] = row.occupant_household.value();
        item["collateral_loan_id"] = row.collateral_loan.value();
        item["floor_area"] = row.floor_area;
        item["quality"] = row.quality;
        item["location"] = row.location;
        item["age_days"] = row.age_days;
        item["active"] = row.active;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict equity_probe_to_python(const macro_sim::reporting::EquityProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["issuer_kind"] = static_cast<std::uint8_t>(row.issuer_kind);
        item["issuer_owner_kind"] = static_cast<std::uint8_t>(row.issuer.kind());
        item["issuer_id"] = row.issuer.value();
        item["issuer_account_id"] = row.issuer_account.value();
        item["currency_id"] = row.currency.value();
        item["outstanding_shares"] = row.outstanding_shares;
        item["price"] = row.price;
        item["last_price"] = row.last_price;
        item["peak_price"] = row.peak_price;
        item["fundamental"] = row.fundamental;
        item["trend"] = row.trend;
        item["income_signal"] = row.income_signal;
        item["active"] = row.active;
        item["resolved"] = row.resolved;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict security_position_probe_to_python(
    const macro_sim::reporting::SecurityPositionProbePage &page) {
    auto output = probe_page_info_to_python(page.page);
    nb::list rows;
    for (const auto &row : page.rows) {
        nb::dict item;
        item["id"] = row.id.value();
        item["security_kind"] = static_cast<std::uint8_t>(row.security_kind);
        item["security_id"] = row.security_id;
        item["holder_kind"] = static_cast<std::uint8_t>(row.holder_kind);
        item["holder_id"] = row.holder_id;
        item["units"] = row.units;
        item["cost_basis"] = row.cost_basis;
        item["market_value"] = row.market_value;
        rows.append(std::move(item));
    }
    output["rows"] = std::move(rows);
    return output;
}

nb::dict
diagnostic_probe_to_python(const macro_sim::reporting::EconomyDiagnosticProbe &probe) {
    nb::dict output;
    output["boundary"] = probe.boundary.value();
    output["economy_id"] = probe.economy.value();
    output["digest"] = probe.digest;
    output["households"] = probe.households;
    output["firms"] = probe.firms;
    output["banks"] = probe.banks;
    output["persons_alive"] = probe.persons_alive;
    output["jobs_active"] = probe.jobs_active;
    output["dwellings_active"] = probe.dwellings_active;
    output["account_balance_total"] = probe.account_balance_total;
    output["loan_principal_total"] = probe.loan_principal_total;
    output["reserve_total"] = probe.reserve_total;
    output["goods_inventory_total"] = probe.goods_inventory_total;
    output["physical_capital_total"] = probe.physical_capital_total;
    output["energy_stock_total"] = probe.energy_stock_total;
    output["dealer_valuation"] = probe.dealer_valuation;
    output["peg_count"] = probe.peg_count;
    output["pegs_intact"] = probe.pegs_intact;
    return output;
}

std::string_view shock_kind_id(macro_sim::simulation::ShockKind kind) noexcept {
    using macro_sim::simulation::ShockKind;
    switch (kind) {
    case ShockKind::productivity:
        return "productivity";
    case ShockKind::labor_availability:
        return "labor_availability";
    case ShockKind::energy_capacity:
        return "energy_capacity";
    case ShockKind::household_demand:
        return "household_demand";
    case ShockKind::import_capacity:
        return "import_capacity";
    case ShockKind::export_capacity:
        return "export_capacity";
    case ShockKind::credit_supply:
        return "credit_supply";
    case ShockKind::capital_destruction:
        return "capital_destruction";
    }
    return "unknown";
}

std::string_view
shock_bulletin_status_id(macro_sim::reporting::ShockBulletinStatus status) noexcept {
    using macro_sim::reporting::ShockBulletinStatus;
    switch (status) {
    case ShockBulletinStatus::upcoming:
        return "upcoming";
    case ShockBulletinStatus::active:
        return "active";
    case ShockBulletinStatus::realizing:
        return "realizing";
    }
    return "unknown";
}

nb::list shock_bulletins_to_python(
    const std::vector<macro_sim::reporting::ShockBulletinProbeRow> &rows) {
    nb::list output;
    for (const auto &row : rows) {
        nb::dict item;
        item["announcement_tick"] = row.announcement.value();
        item["duration_ticks"] = row.duration;
        item["expected_end_tick"] = row.expected_end.value();
        item["intensity"] = row.intensity;
        item["kind"] = shock_kind_id(row.kind);
        item["magnitude"] = row.magnitude;
        item["shock_id"] = std::to_string(row.shock_id);
        item["start_tick"] = row.start.value();
        item["status"] = shock_bulletin_status_id(row.status);
        nb::dict target;
        if (row.economy.has_value()) {
            nb::list economies;
            economies.append(row.economy->value());
            target["economy_ids"] = std::move(economies);
        } else {
            target["economy_ids"] = nb::none();
        }
        if (row.sector.has_value()) {
            target["sector"] = static_cast<std::uint8_t>(*row.sector);
        } else {
            target["sector"] = nb::none();
        }
        item["target"] = std::move(target);
        item["visibility"] = "public";
        output.append(std::move(item));
    }
    return output;
}

nb::dict receipt_to_python(const macro_sim::core::TransactionReceipt &receipt) {
    nb::list loans;
    for (const auto loan : receipt.created_loans) {
        loans.append(loan.value());
    }
    nb::dict output;
    output["before"] = receipt.before.hex();
    output["after"] = receipt.after.hex();
    output["applied_mutations"] = receipt.applied_mutations;
    output["created_loans"] = std::move(loans);
    return output;
}

nb::dict snapshot_to_python(const macro_sim::core::RootState &state) {
    nb::list accounts;
    for (const auto &account : state.postings.records()) {
        nb::dict item;
        item["id"] = account.id.value();
        item["kind"] = static_cast<std::uint8_t>(account.key.kind);
        item["owner_kind"] = static_cast<std::uint8_t>(account.key.owner.kind());
        item["owner_id"] = account.key.owner.value();
        item["settlement_node"] = account.key.settlement_node.value();
        item["balance"] = account.balance.value();
        item["open"] = account.open;
        accounts.append(std::move(item));
    }
    nb::list reserves;
    for (const auto &reserve : state.reserves.records()) {
        nb::dict item;
        item["node"] = reserve.node.value();
        item["bank"] = reserve.bank.value();
        item["balance"] = reserve.balance.value();
        reserves.append(std::move(item));
    }
    nb::list loans;
    for (const auto &loan : state.loans.records()) {
        nb::dict item;
        item["id"] = loan.id.value();
        item["lender"] = loan.lender.value();
        item["borrower_kind"] = static_cast<std::uint8_t>(loan.borrower.kind());
        item["borrower_id"] = loan.borrower.value();
        item["borrower_account"] = loan.borrower_account.value();
        item["principal"] = loan.principal.value();
        item["active"] = loan.active;
        item["purpose"] = static_cast<std::uint8_t>(loan.purpose);
        loans.append(std::move(item));
    }
    nb::dict counters;
    for (const auto &[stream, value] : state.named_counters.records()) {
        counters[nb::int_(stream)] = nb::int_(value);
    }
    nb::dict output;
    output["digest"] = macro_sim::core::state_digest(state).hex();
    output["accounts"] = std::move(accounts);
    output["reserves"] = std::move(reserves);
    output["loans"] = std::move(loans);
    output["counters"] = std::move(counters);
    return output;
}

nb::dict m4_metrics_to_python(const macro_sim::simulation::M4Metrics &metrics) {
    nb::dict output;
    output["tick"] = metrics.tick.value();
    output["real_output"] = metrics.real_output;
    output["nominal_output"] = metrics.nominal_output;
    output["price_index"] = metrics.price_index;
    output["unemployment_rate"] = metrics.unemployment_rate;
    output["total_money"] = metrics.total_money;
    output["conservation_drift"] = metrics.conservation_drift;
    output["aggregate_capital"] = metrics.aggregate_capital;
    output["household_consumption"] = metrics.household_consumption;
    output["wages_paid"] = metrics.wages_paid;
    output["firm_profit"] = metrics.firm_profit;
    output["tax_total"] = metrics.tax_total;
    output["tax_profit"] = metrics.tax_profit;
    output["tax_income"] = metrics.tax_income;
    output["tax_consumption"] = metrics.tax_consumption;
    output["government_spending"] = metrics.government_spending;
    output["government_deficit"] = metrics.government_deficit;
    output["public_capital"] = metrics.public_capital;
    output["gross_output_nominal"] = metrics.gross_output_nominal;
    output["consumption_output_nominal"] = metrics.consumption_output_nominal;
    output["capital_output_nominal"] = metrics.capital_output_nominal;
    output["consumption_output_real"] = metrics.consumption_output_real;
    output["capital_output_real"] = metrics.capital_output_real;
    output["inventory_change_nominal"] = metrics.inventory_change_nominal;
    output["inventory_change_real"] = metrics.inventory_change_real;
    output["fixed_capital_formation_nominal"] = metrics.fixed_capital_formation_nominal;
    output["fixed_capital_formation_real"] = metrics.fixed_capital_formation_real;
    output["government_consumption"] = metrics.government_consumption;
    output["public_fixed_capital_formation"] = metrics.public_fixed_capital_formation;
    output["transfer_payments"] = metrics.transfer_payments;
    return output;
}

nb::dict m4_result_to_python(const macro_sim::simulation::M4AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] = result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m4_metrics_to_python(result.metrics);
    return output;
}

nb::dict m5_metrics_to_python(const macro_sim::simulation::M5Metrics &metrics) {
    nb::dict output;
    output["economy"] = m4_metrics_to_python(metrics.economy);
    output["policy_rate"] = metrics.policy_rate;
    output["inflation_sensor"] = metrics.inflation_sensor;
    output["new_credit"] = metrics.new_credit;
    output["principal_repaid"] = metrics.principal_repaid;
    output["loan_interest_paid"] = metrics.loan_interest_paid;
    output["household_interest_paid"] = metrics.household_interest_paid;
    output["deposit_interest_paid"] = metrics.deposit_interest_paid;
    output["deposit_interest_arrears"] = metrics.deposit_interest_arrears;
    output["total_loan_principal"] = metrics.total_loan_principal;
    output["total_bank_capital"] = metrics.total_bank_capital;
    output["total_reserves"] = metrics.total_reserves;
    output["reserve_stock"] = metrics.reserve_stock;
    output["omo_flow"] = metrics.omo_flow;
    output["lolr_advances"] = metrics.lolr_advances;
    output["lolr_outstanding"] = metrics.lolr_outstanding;
    output["interbank_volume"] = metrics.interbank_volume;
    output["interbank_rate"] = metrics.interbank_rate;
    output["run_flight_volume"] = metrics.run_flight_volume;
    output["resolution_cost"] = metrics.resolution_cost;
    output["realized_credit_losses"] = metrics.realized_credit_losses;
    output["realized_interbank_losses"] = metrics.realized_interbank_losses;
    output["alive_banks"] = metrics.alive_banks;
    output["bank_failures"] = metrics.bank_failures;
    return output;
}

nb::dict m5_result_to_python(const macro_sim::simulation::M5AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] = result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m5_metrics_to_python(result.metrics);
    return output;
}

nb::dict m4_snapshot_to_python(const macro_sim::EngineSession &session);

nb::dict m5_snapshot_to_python(const macro_sim::EngineSession &session) {
    if (session.root() == nullptr || session.monetary_runtime() == nullptr) {
        throw std::runtime_error("invalid_handle: session has no active M5 simulation");
    }
    auto output = m4_snapshot_to_python(session);
    const auto &root = *session.root();
    nb::list banks;
    root.banks.for_each_alive(
        [&banks, &root](macro_sim::BankId id,
                        const macro_sim::core::BankComponent &bank) {
            nb::dict item;
            item["id"] = id.value();
            item["cash_account"] = bank.cash_account.value();
            item["reserve_node"] = bank.settlement_node.value();
            item["leverage_appetite"] = bank.leverage_appetite;
            item["loan_spread"] = bank.loan_spread;
            item["deposit_spread"] = bank.deposit_spread;
            item["alive"] = bank.alive;
            if (const auto *capital = root.bank_capital.get(id); capital != nullptr) {
                item["opening_capital"] = capital->opening_capital;
                item["closing_capital"] = capital->closing_capital;
                item["deposit_interest_arrears"] = capital->deposit_interest_arrears;
                item["resolved"] = capital->resolved;
            }
            banks.append(std::move(item));
        });
    nb::list interbank;
    for (const auto &record : root.interbank.records()) {
        nb::dict item;
        item["id"] = record.id.value();
        item["lender"] = record.lender.value();
        item["borrower"] = record.borrower.value();
        item["principal"] = record.principal.value();
        item["rate"] = record.rate.value();
        item["accrued_interest"] = record.accrued_interest.value();
        item["originated_tick"] = record.originated_tick.value();
        item["maturity_tick"] = record.maturity_tick.value();
        item["active"] = record.active;
        interbank.append(std::move(item));
    }
    nb::list central_bank_operations;
    for (const auto &record : root.central_bank_operations.records()) {
        nb::dict item;
        item["id"] = record.id.value();
        item["kind"] = static_cast<std::uint8_t>(record.kind);
        item["bank"] = record.counterparty.value();
        item["principal"] = record.principal.value();
        item["rate"] = record.rate.value();
        item["originated_tick"] = record.opened_tick.value();
        item["maturity_tick"] = record.maturity_tick.value();
        item["active"] = record.active;
        central_bank_operations.append(std::move(item));
    }
    output["banks"] = std::move(banks);
    output["interbank"] = std::move(interbank);
    output["central_bank_operations"] = std::move(central_bank_operations);
    output["policy_rate"] = session.monetary_runtime()->policy_rate;
    output["inflation_sensor"] = session.monetary_runtime()->inflation_sensor;
    output["metrics"] = m5_metrics_to_python(session.monetary_runtime()->last_metrics);
    return output;
}

nb::dict m6_metrics_to_python(const macro_sim::simulation::M6Metrics &metrics) {
    nb::dict output;
    output["economy"] = m5_metrics_to_python(metrics.economy);
#define MACRO_SIM_M6_METRIC(field) output[#field] = metrics.field
    MACRO_SIM_M6_METRIC(bond_outstanding_face);
    MACRO_SIM_M6_METRIC(bond_market_value);
    MACRO_SIM_M6_METRIC(bond_issuance);
    MACRO_SIM_M6_METRIC(bond_redemption);
    MACRO_SIM_M6_METRIC(bond_coupon_paid);
    MACRO_SIM_M6_METRIC(firm_equity_market_cap);
    MACRO_SIM_M6_METRIC(bank_equity_market_cap);
    MACRO_SIM_M6_METRIC(equity_turnover);
    MACRO_SIM_M6_METRIC(primary_equity_raised);
    MACRO_SIM_M6_METRIC(margin_principal);
    MACRO_SIM_M6_METRIC(margin_originated);
    MACRO_SIM_M6_METRIC(margin_repaid);
    MACRO_SIM_M6_METRIC(margin_writeoffs);
    MACRO_SIM_M6_METRIC(total_firm_book_equity);
    MACRO_SIM_M6_METRIC(clearing_residual);
    MACRO_SIM_M6_METRIC(sector_retool_capital);
    MACRO_SIM_M6_METRIC(active_security_lots);
    MACRO_SIM_M6_METRIC(household_bankruptcies);
    MACRO_SIM_M6_METRIC(firm_births);
    MACRO_SIM_M6_METRIC(firm_exits);
    MACRO_SIM_M6_METRIC(firm_defaults);
    MACRO_SIM_M6_METRIC(sector_switches);
    MACRO_SIM_M6_METRIC(bank_births);
    MACRO_SIM_M6_METRIC(bank_equity_resolutions);
#undef MACRO_SIM_M6_METRIC
    return output;
}

nb::dict m6_result_to_python(const macro_sim::simulation::M6AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] = result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m6_metrics_to_python(result.metrics);
    return output;
}

nb::dict m7_metrics_to_python(const macro_sim::simulation::M7Metrics &metrics) {
    nb::dict output;
    output["economy"] = m6_metrics_to_python(metrics.economy);
#define MACRO_SIM_M7_METRIC(field) output[#field] = metrics.field
    MACRO_SIM_M7_METRIC(population);
    MACRO_SIM_M7_METRIC(births);
    MACRO_SIM_M7_METRIC(deaths);
    MACRO_SIM_M7_METRIC(households_with_members);
    MACRO_SIM_M7_METRIC(mean_household_size);
    MACRO_SIM_M7_METRIC(working_age_share);
    MACRO_SIM_M7_METRIC(dependency_ratio);
    MACRO_SIM_M7_METRIC(mean_person_efficiency);
    MACRO_SIM_M7_METRIC(person_efficiency_stddev);
    MACRO_SIM_M7_METRIC(active_unions);
    MACRO_SIM_M7_METRIC(mean_partner_age_gap);
    MACRO_SIM_M7_METRIC(mean_partner_log_efficiency_gap);
    MACRO_SIM_M7_METRIC(participation_rate);
    MACRO_SIM_M7_METRIC(estates_settled);
    MACRO_SIM_M7_METRIC(beneficial_lots_transferred);
    MACRO_SIM_M7_METRIC(inheritance_tax_share);
    MACRO_SIM_M7_METRIC(inheritance_tax_paid);
    MACRO_SIM_M7_METRIC(pension_paid);
    MACRO_SIM_M7_METRIC(beneficial_projection_error);
    MACRO_SIM_M7_METRIC(employed_fte);
    MACRO_SIM_M7_METRIC(employed_heads);
    MACRO_SIM_M7_METRIC(unemployment);
    MACRO_SIM_M7_METRIC(unemployment_rate);
    MACRO_SIM_M7_METRIC(suspended);
    MACRO_SIM_M7_METRIC(job_guarantee);
    MACRO_SIM_M7_METRIC(out_of_labor_force);
    MACRO_SIM_M7_METRIC(labor_supply);
    MACRO_SIM_M7_METRIC(vacancies);
    MACRO_SIM_M7_METRIC(underemployed_heads);
    MACRO_SIM_M7_METRIC(underemployment_hours);
    MACRO_SIM_M7_METRIC(suspended_memo);
    MACRO_SIM_M7_METRIC(second_job_heads);
    MACRO_SIM_M7_METRIC(second_job_hours);
    MACRO_SIM_M7_METRIC(nonsearching);
    MACRO_SIM_M7_METRIC(job_to_job_moves);
    MACRO_SIM_M7_METRIC(mean_hourly_wage);
    MACRO_SIM_M7_METRIC(family_transfer_total);
    MACRO_SIM_M7_METRIC(family_transfer_recipients);
    MACRO_SIM_M7_METRIC(family_exposed_households);
    MACRO_SIM_M7_METRIC(hires);
    MACRO_SIM_M7_METRIC(separations);
    MACRO_SIM_M7_METRIC(churn_separations);
    MACRO_SIM_M7_METRIC(demand_layoff_separations);
    MACRO_SIM_M7_METRIC(cash_layoff_separations);
    MACRO_SIM_M7_METRIC(firm_exit_separations);
    MACRO_SIM_M7_METRIC(death_separations);
    MACRO_SIM_M7_METRIC(retirement_separations);
    MACRO_SIM_M7_METRIC(welfare_quits);
    MACRO_SIM_M7_METRIC(suspensions_flow);
    MACRO_SIM_M7_METRIC(recalls);
    MACRO_SIM_M7_METRIC(marriages);
    MACRO_SIM_M7_METRIC(divorces);
    MACRO_SIM_M7_METRIC(widowhoods);
    MACRO_SIM_M7_METRIC(leaving_home_events);
#undef MACRO_SIM_M7_METRIC
    return output;
}

nb::dict m7_result_to_python(const macro_sim::simulation::M7AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] = result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m7_metrics_to_python(result.metrics);
    return output;
}

nb::dict
m8_energy_metrics_to_python(const macro_sim::simulation::EnergyMetrics &metrics) {
    nb::dict output;
#define MACRO_SIM_M8_ENERGY_METRIC(field) output[#field] = metrics.field
    MACRO_SIM_M8_ENERGY_METRIC(production);
    MACRO_SIM_M8_ENERGY_METRIC(capacity);
    MACRO_SIM_M8_ENERGY_METRIC(utilization);
    MACRO_SIM_M8_ENERGY_METRIC(opening_supply);
    MACRO_SIM_M8_ENERGY_METRIC(requested_total);
    MACRO_SIM_M8_ENERGY_METRIC(requested_households);
    MACRO_SIM_M8_ENERGY_METRIC(requested_industry);
    MACRO_SIM_M8_ENERGY_METRIC(requested_public);
    MACRO_SIM_M8_ENERGY_METRIC(sold);
    MACRO_SIM_M8_ENERGY_METRIC(unfilled);
    MACRO_SIM_M8_ENERGY_METRIC(transaction_price);
    MACRO_SIM_M8_ENERGY_METRIC(household_units);
    MACRO_SIM_M8_ENERGY_METRIC(household_spending);
    MACRO_SIM_M8_ENERGY_METRIC(industry_units);
    MACRO_SIM_M8_ENERGY_METRIC(industry_spending);
    MACRO_SIM_M8_ENERGY_METRIC(excise_paid);
    MACRO_SIM_M8_ENERGY_METRIC(windfall_tax_paid);
    MACRO_SIM_M8_ENERGY_METRIC(subsidy_paid);
    MACRO_SIM_M8_ENERGY_METRIC(cap_compensation);
    MACRO_SIM_M8_ENERGY_METRIC(strategic_reserve_stock);
    MACRO_SIM_M8_ENERGY_METRIC(strategic_reserve_flow);
    MACRO_SIM_M8_ENERGY_METRIC(strategic_reserve_purchase_paid);
    MACRO_SIM_M8_ENERGY_METRIC(strategic_reserve_sale_revenue);
    MACRO_SIM_M8_ENERGY_METRIC(fuel_poverty_share);
    MACRO_SIM_M8_ENERGY_METRIC(fuel_poverty_mortality_multiplier);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_below_100_share);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_below_60_share);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_below_30_share);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_destitute_share);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_acute_stock);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_chronic_stock);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_max_spell_days);
    MACRO_SIM_M8_ENERGY_METRIC(deprivation_boundary);
#undef MACRO_SIM_M8_ENERGY_METRIC
    return output;
}

nb::dict
m8_housing_metrics_to_python(const macro_sim::simulation::HousingMetrics &metrics) {
    nb::dict output;
#define MACRO_SIM_M8_HOUSING_METRIC(field) output[#field] = metrics.field
    MACRO_SIM_M8_HOUSING_METRIC(house_price);
    MACRO_SIM_M8_HOUSING_METRIC(rent_level);
    MACRO_SIM_M8_HOUSING_METRIC(housing_stock);
    MACRO_SIM_M8_HOUSING_METRIC(homeownership_share);
    MACRO_SIM_M8_HOUSING_METRIC(vacancy_share);
    MACRO_SIM_M8_HOUSING_METRIC(active_listings);
    MACRO_SIM_M8_HOUSING_METRIC(forced_listing_share);
    MACRO_SIM_M8_HOUSING_METRIC(session_sales);
    MACRO_SIM_M8_HOUSING_METRIC(session_volume);
    MACRO_SIM_M8_HOUSING_METRIC(mean_time_on_market_days);
    MACRO_SIM_M8_HOUSING_METRIC(mortgage_originations);
    MACRO_SIM_M8_HOUSING_METRIC(mortgage_principal_originated);
    MACRO_SIM_M8_HOUSING_METRIC(mortgage_principal_outstanding);
    MACRO_SIM_M8_HOUSING_METRIC(foreclosures);
    MACRO_SIM_M8_HOUSING_METRIC(rent_paid);
    MACRO_SIM_M8_HOUSING_METRIC(rent_unpaid);
    MACRO_SIM_M8_HOUSING_METRIC(evictions);
    MACRO_SIM_M8_HOUSING_METRIC(property_tax_paid);
    MACRO_SIM_M8_HOUSING_METRIC(housing_wealth_tax_paid);
    MACRO_SIM_M8_HOUSING_METRIC(transfer_tax_paid);
    MACRO_SIM_M8_HOUSING_METRIC(land_fee_paid);
    MACRO_SIM_M8_HOUSING_METRIC(construction_output);
    MACRO_SIM_M8_HOUSING_METRIC(dwellings_completed);
    MACRO_SIM_M8_HOUSING_METRIC(permits_used);
    MACRO_SIM_M8_HOUSING_METRIC(price_to_income_ratio);
    MACRO_SIM_M8_HOUSING_METRIC(rent_burden_ratio);
    MACRO_SIM_M8_HOUSING_METRIC(leave_home_multiplier);
    MACRO_SIM_M8_HOUSING_METRIC(fertility_multiplier);
#undef MACRO_SIM_M8_HOUSING_METRIC
    return output;
}

nb::dict m8_metrics_to_python(const macro_sim::simulation::M8Metrics &metrics) {
    nb::dict output;
    output["economy"] = m7_metrics_to_python(metrics.economy);
    output["energy"] = m8_energy_metrics_to_python(metrics.energy);
    output["housing"] = m8_housing_metrics_to_python(metrics.housing);
    return output;
}

nb::dict m8_result_to_python(const macro_sim::simulation::M8AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] = result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m8_metrics_to_python(result.metrics);
    return output;
}

nb::dict m9_country_metrics_to_python(
    const macro_sim::simulation::CountryExternalMetrics &metrics, std::size_t economy) {
    nb::dict output;
    output["economy_id"] = economy;
#define MACRO_SIM_M9_COUNTRY_METRIC(field) output[#field] = metrics.field
    MACRO_SIM_M9_COUNTRY_METRIC(exchange_rate);
    MACRO_SIM_M9_COUNTRY_METRIC(imports_value);
    MACRO_SIM_M9_COUNTRY_METRIC(imports_volume);
    MACRO_SIM_M9_COUNTRY_METRIC(exports_value);
    MACRO_SIM_M9_COUNTRY_METRIC(exports_volume);
    MACRO_SIM_M9_COUNTRY_METRIC(iceberg_loss);
    MACRO_SIM_M9_COUNTRY_METRIC(tariff_revenue);
    MACRO_SIM_M9_COUNTRY_METRIC(export_subsidy_cost);
    MACRO_SIM_M9_COUNTRY_METRIC(current_account);
    MACRO_SIM_M9_COUNTRY_METRIC(capital_flow);
    MACRO_SIM_M9_COUNTRY_METRIC(net_foreign_assets);
    MACRO_SIM_M9_COUNTRY_METRIC(factor_income_accrued);
    MACRO_SIM_M9_COUNTRY_METRIC(factor_income_cash);
    MACRO_SIM_M9_COUNTRY_METRIC(factor_income_arrears);
    MACRO_SIM_M9_COUNTRY_METRIC(peg_reserves);
    MACRO_SIM_M9_COUNTRY_METRIC(migrant_stock_abroad);
    MACRO_SIM_M9_COUNTRY_METRIC(migrant_stock_hosted);
    MACRO_SIM_M9_COUNTRY_METRIC(remittances_received);
    MACRO_SIM_M9_COUNTRY_METRIC(remittances_sent);
    MACRO_SIM_M9_COUNTRY_METRIC(remittance_tax_revenue);
    MACRO_SIM_M9_COUNTRY_METRIC(capital_destroyed);
    MACRO_SIM_M9_COUNTRY_METRIC(active_shocks);
#undef MACRO_SIM_M9_COUNTRY_METRIC
    return output;
}

nb::dict m9_metrics_to_python(const macro_sim::simulation::M9WorldMetrics &metrics) {
    nb::list domestic;
    for (const auto &value : metrics.domestic) {
        domestic.append(m8_metrics_to_python(value));
    }
    nb::list external;
    for (std::size_t index = 0; index < metrics.external.size(); ++index) {
        external.append(m9_country_metrics_to_python(metrics.external[index], index));
    }
    nb::dict output;
    output["domestic"] = std::move(domestic);
    output["external"] = std::move(external);
    output["dealer_flow"] = metrics.dealer_flow;
    output["dealer_spread_revenue"] = metrics.dealer_spread_revenue;
    output["dealer_valuation"] = metrics.dealer_valuation;
    output["world_nfa"] = metrics.world_nfa;
    output["trade_routes"] = metrics.trade_routes;
    output["migration_routes"] = metrics.migration_routes;
    output["shock_events"] = metrics.shock_events;
    return output;
}

nb::dict m9_result_to_python(const macro_sim::simulation::M9AdvanceResult &result) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["digest"] = result.digest;
    output["metrics"] = m9_metrics_to_python(result.metrics);
    return output;
}

nb::dict m9_snapshot_to_python(const macro_sim::simulation::M9World &world) {
    nb::list rates;
    for (std::size_t index = 0; index < world.economy_count(); ++index) {
        rates.append(world.rates().rate(
            macro_sim::EconomyId(static_cast<std::uint64_t>(index))));
    }
    nb::list pegs;
    for (const auto &peg : world.pegs()) {
        nb::dict item;
        item["pegger"] = peg.pegger.value();
        item["anchor"] = peg.anchor.value();
        item["reserves"] = peg.reserves;
        item["pressure"] = peg.pressure;
        item["target_log_spread"] = peg.target_log_spread;
        item["intact"] = peg.intact;
        pegs.append(std::move(item));
    }
    nb::list migration;
    for (const auto &route : world.migration_routes()) {
        nb::dict item;
        item["origin"] = route.origin.value();
        item["host"] = route.host.value();
        item["stock"] = route.stock;
        item["smoothed_real_wage_gap"] = route.smoothed_real_wage_gap;
        item["flow"] = route.flow;
        item["return_flow"] = route.return_flow;
        item["remittance_gross"] = route.remittance_gross;
        item["remittance_net"] = route.remittance_net;
        migration.append(std::move(item));
    }
    nb::dict output;
    output["tick"] = world.tick().value();
    output["economy_count"] = world.economy_count();
    output["digest"] = world.digest();
    output["rates"] = std::move(rates);
    output["pegs"] = std::move(pegs);
    output["migration"] = std::move(migration);
    output["metrics"] = m9_metrics_to_python(world.last_metrics());
    return output;
}

nb::dict m9_memory_usage_to_python(const macro_sim::simulation::M9MemoryUsage &usage) {
    nb::dict output;
#define MACRO_SIM_M9_MEMORY(field) output[#field] = usage.field
    MACRO_SIM_M9_MEMORY(root_state);
    MACRO_SIM_M9_MEMORY(root_households);
    MACRO_SIM_M9_MEMORY(root_firms);
    MACRO_SIM_M9_MEMORY(root_banks);
    MACRO_SIM_M9_MEMORY(root_postings);
    MACRO_SIM_M9_MEMORY(root_reserves);
    MACRO_SIM_M9_MEMORY(root_loans);
    MACRO_SIM_M9_MEMORY(root_interbank);
    MACRO_SIM_M9_MEMORY(root_central_bank_operations);
    MACRO_SIM_M9_MEMORY(root_bank_pnl);
    MACRO_SIM_M9_MEMORY(root_bank_capital);
    MACRO_SIM_M9_MEMORY(root_ownership);
    MACRO_SIM_M9_MEMORY(root_named_counters);
    MACRO_SIM_M9_MEMORY(real_economy_scratch);
    MACRO_SIM_M9_MEMORY(monetary_scratch);
    MACRO_SIM_M9_MEMORY(financial_runtime);
    MACRO_SIM_M9_MEMORY(financial_scratch);
    MACRO_SIM_M9_MEMORY(person_store);
    MACRO_SIM_M9_MEMORY(household_membership);
    MACRO_SIM_M9_MEMORY(beneficial_lots);
    MACRO_SIM_M9_MEMORY(beneficial_indexes);
    MACRO_SIM_M9_MEMORY(social_labor);
    MACRO_SIM_M9_MEMORY(employment);
    MACRO_SIM_M9_MEMORY(relationships);
    MACRO_SIM_M9_MEMORY(population_scratch);
    MACRO_SIM_M9_MEMORY(housing_registry);
    MACRO_SIM_M9_MEMORY(domestic_runtime);
    MACRO_SIM_M9_MEMORY(domestic_scratch);
    MACRO_SIM_M9_MEMORY(world);
#undef MACRO_SIM_M9_MEMORY
    output["total_known"] = usage.total_known();
    return output;
}

nb::dict m9_storage_counts_to_python(const macro_sim::simulation::M9World &world) {
    std::uint64_t accounts = 0;
    std::uint64_t reserves = 0;
    std::uint64_t loans = 0;
    std::uint64_t interbank = 0;
    std::uint64_t central_bank_operations = 0;
    std::uint64_t bank_pnl = 0;
    std::uint64_t bank_capital = 0;
    std::uint64_t ownership = 0;
    std::uint64_t persons = 0;
    std::uint64_t jobs = 0;
    std::uint64_t unions = 0;
    for (std::size_t index = 0; index < world.economy_count(); ++index) {
        const auto economy = macro_sim::EconomyId(index);
        const auto *root = world.economy_root(economy);
        const auto *population = world.economy_population_runtime(economy);
        if (root != nullptr) {
            accounts += root->postings.records().size();
            reserves += root->reserves.records().size();
            loans += root->loans.records().size();
            interbank += root->interbank.records().size();
            central_bank_operations += root->central_bank_operations.records().size();
            bank_pnl += root->bank_pnl.records().size();
            bank_capital += root->bank_capital.records().size();
            ownership += root->ownership.records().size();
        }
        if (population != nullptr) {
            persons += population->persons.total_count();
            jobs += population->employment.records().size();
            unions += population->relationships.unions().size();
        }
    }
    nb::dict output;
    output["accounts"] = accounts;
    output["reserves"] = reserves;
    output["loans"] = loans;
    output["interbank"] = interbank;
    output["central_bank_operations"] = central_bank_operations;
    output["bank_pnl"] = bank_pnl;
    output["bank_capital"] = bank_capital;
    output["ownership"] = ownership;
    output["persons"] = persons;
    output["jobs"] = jobs;
    output["unions"] = unions;
    return output;
}

nb::dict m6_snapshot_to_python(const macro_sim::EngineSession &session);

nb::dict m7_snapshot_to_python(const macro_sim::EngineSession &session) {
    const auto *runtime = session.population_runtime();
    if (runtime == nullptr) {
        throw std::runtime_error("invalid_handle: session has no active M7 simulation");
    }
    auto output = m6_snapshot_to_python(session);
    nb::list persons;
    for (std::size_t index = 1; index < runtime->persons.records().size(); ++index) {
        const auto &row = runtime->persons.records()[index];
        nb::dict item;
        item["id"] = row.id.value();
        item["sex"] = static_cast<std::uint8_t>(row.sex);
        item["birth_day"] = row.birth_day;
        item["death_day"] = row.death_day;
        item["mother_id"] = row.mother.value();
        item["father_id"] = row.father.value();
        item["partner_id"] = row.partner.value();
        item["guardian_id"] = row.guardian.value();
        item["household_id"] = row.household.value();
        item["efficiency"] = row.efficiency;
        item["participating"] = row.participating;
        item["searching"] = row.searching;
        item["alive"] = row.alive;
        persons.append(std::move(item));
    }
    nb::list jobs;
    for (std::size_t index = 1; index < runtime->employment.records().size(); ++index) {
        const auto &row = runtime->employment.records()[index];
        nb::dict item;
        item["id"] = row.id.value();
        item["person_id"] = row.person.value();
        item["firm_id"] = row.firm.value();
        item["hire_day"] = row.hire_day;
        item["separation_day"] = row.separation_day;
        item["wage"] = row.wage;
        item["hours"] = row.hours;
        item["secondary"] = row.secondary;
        item["suspended"] = row.suspended;
        item["active"] = row.active;
        jobs.append(std::move(item));
    }
    nb::list unions;
    for (const auto &row : runtime->relationships.unions()) {
        nb::dict item;
        item["event_id"] = row.event.value();
        item["first_id"] = row.first.value();
        item["second_id"] = row.second.value();
        item["start_day"] = row.start_day;
        item["end_day"] = row.end_day;
        item["end_kind"] = static_cast<std::uint8_t>(row.end_kind);
        item["active"] = row.active;
        unions.append(std::move(item));
    }
    nb::list estates;
    for (const auto &row : runtime->estates) {
        nb::dict item;
        item["event_id"] = row.event.value();
        item["deceased_id"] = row.deceased.value();
        item["heir_id"] = row.heir.value();
        item["household_id"] = row.household.value();
        item["destination_household_id"] = row.destination_household.value();
        item["opened_day"] = row.opened_day;
        item["settled_day"] = row.settled_day;
        item["transferred_lots"] = row.transferred_lots;
        item["gross_share"] = row.gross_share;
        item["tax_share"] = row.tax_share;
        item["gross_value"] = row.gross_value;
        item["liabilities"] = row.liabilities;
        item["tax_paid"] = row.tax_paid;
        item["public_residual"] = row.public_residual;
        item["settled"] = row.settled;
        estates.append(std::move(item));
    }
    nb::list leaving_home;
    for (const auto &row : runtime->leaving_home) {
        nb::dict item;
        item["event_id"] = row.event.value();
        item["person_id"] = row.person.value();
        item["origin_household_id"] = row.origin.value();
        item["destination_household_id"] = row.destination.value();
        item["day"] = row.day;
        leaving_home.append(std::move(item));
    }
    output["persons"] = std::move(persons);
    output["jobs"] = std::move(jobs);
    output["unions"] = std::move(unions);
    output["estates"] = std::move(estates);
    output["leaving_home"] = std::move(leaving_home);
    output["calendar_day"] = runtime->current_calendar_day;
    output["metrics"] = m7_metrics_to_python(runtime->last_metrics);
    return output;
}

nb::dict m8_snapshot_to_python(const macro_sim::EngineSession &session) {
    const auto *runtime = session.housing_runtime();
    if (runtime == nullptr) {
        throw std::runtime_error("invalid_handle: session has no active M8 simulation");
    }
    auto output = m7_snapshot_to_python(session);
    nb::list energy_producers;
    for (const auto &row : runtime->energy_producers) {
        nb::dict item;
        item["firm_id"] = row.firm.value();
        item["active"] = row.active;
        item["state_owned"] = row.state_owned;
        item["capacity_per_capital"] = row.capacity_per_capital;
        item["inventory"] = row.inventory;
        item["inventory_cost"] = row.inventory_cost;
        item["produced"] = row.produced;
        item["sales"] = row.sales;
        item["revenue"] = row.revenue;
        item["demand_expected"] = row.demand_expected;
        energy_producers.append(std::move(item));
    }
    nb::list energy_inputs;
    for (const auto &row : runtime->energy_inputs) {
        nb::dict item;
        item["firm_id"] = row.firm.value();
        item["active"] = row.active;
        item["intensity"] = row.intensity;
        item["coverage_days"] = row.coverage_days;
        item["stock"] = row.stock;
        item["stock_cost"] = row.stock_cost;
        item["average_cost"] = row.average_cost;
        item["bought"] = row.bought;
        item["used"] = row.used;
        item["unmet"] = row.unmet;
        energy_inputs.append(std::move(item));
    }
    nb::list household_energy;
    for (const auto &row : runtime->household_energy) {
        nb::dict item;
        item["household_id"] = row.household.value();
        item["active"] = row.active;
        item["need"] = row.need;
        item["bought"] = row.bought;
        item["spent"] = row.spent;
        item["subsidy"] = row.subsidy;
        item["coverage"] = row.coverage;
        item["deprivation_spells"] =
            nb::make_tuple(row.deprivation_spells[0], row.deprivation_spells[1],
                           row.deprivation_spells[2]);
        household_energy.append(std::move(item));
    }
    nb::list dwellings;
    for (const auto &row : runtime->properties.records()) {
        nb::dict item;
        item["id"] = row.id.value();
        item["owner_kind"] = static_cast<std::uint8_t>(row.owner.kind());
        item["owner_id"] = row.owner.value();
        item["occupant_household_id"] = row.occupant.value();
        item["collateral_loan_id"] = row.collateral.value();
        item["minted_tick"] = row.minted_tick.value();
        item["last_title_tick"] = row.last_title_tick.value();
        item["floor_area"] = row.floor_area;
        item["quality"] = row.quality;
        item["location"] = row.location;
        item["age_days"] = row.age_days;
        item["active"] = row.active;
        dwellings.append(std::move(item));
    }
    nb::list title_events;
    for (const auto &row : runtime->properties.title_events()) {
        nb::dict item;
        item["id"] = row.id.value();
        item["dwelling_id"] = row.dwelling.value();
        item["kind"] = static_cast<std::uint8_t>(row.kind);
        item["previous_owner_kind"] =
            static_cast<std::uint8_t>(row.previous_owner.kind());
        item["previous_owner_id"] = row.previous_owner.value();
        item["next_owner_kind"] = static_cast<std::uint8_t>(row.next_owner.kind());
        item["next_owner_id"] = row.next_owner.value();
        item["tick"] = row.tick.value();
        title_events.append(std::move(item));
    }
    nb::list listings;
    for (const auto &row : runtime->housing_listings) {
        nb::dict item;
        item["dwelling_id"] = row.dwelling.value();
        item["seller_kind"] = static_cast<std::uint8_t>(row.seller.kind());
        item["seller_id"] = row.seller.value();
        item["asking_price"] = row.asking_price;
        item["listed_tick"] = row.listed_tick.value();
        item["forced"] = row.forced;
        item["active"] = row.active;
        listings.append(std::move(item));
    }
    nb::list mortgages;
    for (const auto &row : runtime->mortgages) {
        nb::dict item;
        item["loan_id"] = row.loan.value();
        item["borrower_household_id"] = row.borrower.value();
        item["lender_bank_id"] = row.lender.value();
        item["collateral_dwelling_id"] = row.collateral.value();
        item["original_principal"] = row.original_principal;
        item["purchase_price"] = row.purchase_price;
        item["qualifying_income"] = row.qualifying_income;
        item["stressed_payment"] = row.stressed_payment;
        item["originated_tick"] = row.originated_tick.value();
        item["active"] = row.active;
        item["foreclosed"] = row.foreclosed;
        mortgages.append(std::move(item));
    }
    nb::list tenancies;
    for (const auto &row : runtime->tenancies) {
        nb::dict item;
        item["id"] = row.id.value();
        item["dwelling_id"] = row.dwelling.value();
        item["landlord_household_id"] = row.landlord.value();
        item["tenant_household_id"] = row.tenant.value();
        item["daily_rent"] = row.daily_rent;
        item["missed_days"] = row.missed_days;
        item["started_tick"] = row.started_tick.value();
        item["ended_tick"] = row.ended_tick.value();
        item["active"] = row.active;
        tenancies.append(std::move(item));
    }
    nb::list builders;
    for (const auto &row : runtime->builders) {
        nb::dict item;
        item["firm_id"] = row.firm.value();
        item["active"] = row.active;
        item["work_in_progress"] = row.work_in_progress;
        item["finished_inventory"] = row.finished_inventory;
        item["demand_expected"] = row.demand_expected;
        item["produced_today"] = row.produced_today;
        item["dwellings_minted"] = row.dwellings_minted;
        builders.append(std::move(item));
    }
    output["energy_producers"] = std::move(energy_producers);
    output["energy_inputs"] = std::move(energy_inputs);
    output["household_energy"] = std::move(household_energy);
    output["dwellings"] = std::move(dwellings);
    output["title_events"] = std::move(title_events);
    output["housing_listings"] = std::move(listings);
    output["mortgages"] = std::move(mortgages);
    output["tenancies"] = std::move(tenancies);
    output["builders"] = std::move(builders);
    output["strategic_reserve_stock"] = runtime->strategic_reserve_stock;
    output["strategic_reserve_cost"] = runtime->strategic_reserve_cost;
    output["energy_price"] = runtime->energy_price;
    output["slow_energy_price"] = runtime->slow_energy_price;
    output["house_price"] = runtime->house_price;
    output["rent_level"] = runtime->rent_level;
    output["permits_used"] = runtime->permits_used;
    output["metrics"] = m8_metrics_to_python(runtime->last_metrics);
    return output;
}

nb::dict m6_snapshot_to_python(const macro_sim::EngineSession &session) {
    const auto *runtime = session.securities_runtime();
    if (runtime == nullptr) {
        throw std::runtime_error("invalid_handle: session has no active M6 simulation");
    }
    auto output = m5_snapshot_to_python(session);
    nb::list bonds;
    for (const auto &row : runtime->securities.bonds()) {
        nb::dict item;
        item["id"] = row.id.value();
        item["issuer_kind"] = static_cast<std::uint8_t>(row.issuer.kind());
        item["issuer_id"] = row.issuer.value();
        item["issuer_account"] = row.issuer_account.value();
        item["currency_id"] = row.currency.value();
        item["issued_tick"] = row.issued_tick.value();
        item["maturity_tick"] = row.maturity_tick.value();
        item["coupon_rate"] = row.coupon_rate.value();
        item["original_face"] = row.original_face.value();
        item["outstanding_face"] = row.outstanding_face.value();
        item["active"] = row.active;
        item["settled"] = row.settled;
        bonds.append(std::move(item));
    }
    nb::list equities;
    for (const auto &row : runtime->securities.equities()) {
        nb::dict item;
        item["id"] = row.id.value();
        item["issuer_kind"] = static_cast<std::uint8_t>(row.issuer_kind);
        item["owner_kind"] = static_cast<std::uint8_t>(row.issuer.kind());
        item["issuer_id"] = row.issuer.value();
        item["issuer_account"] = row.issuer_account.value();
        item["currency_id"] = row.currency.value();
        item["outstanding_shares"] = row.outstanding_shares;
        item["price"] = row.price.value();
        item["last_price"] = row.last_price.value();
        item["peak_price"] = row.peak_price.value();
        item["fundamental"] = row.fundamental.value();
        item["trend"] = row.trend;
        item["income_signal"] = row.income_signal;
        item["active"] = row.active;
        item["resolved"] = row.resolved;
        equities.append(std::move(item));
    }
    nb::list lots;
    std::uint32_t security_lot_id = 1U;
    for (const auto &row : runtime->securities.lots()) {
        nb::dict item;
        item["id"] = security_lot_id++;
        item["security_kind"] = static_cast<std::uint8_t>(row.security.kind());
        item["security_id"] = row.security.value();
        item["holder_kind"] = static_cast<std::uint8_t>(row.holder.kind());
        item["holder_id"] = row.holder.value();
        item["units"] = row.units;
        item["cost_basis"] = row.cost_basis.value();
        item["active"] = row.active();
        lots.append(std::move(item));
    }
    nb::list firms;
    for (const auto &row : runtime->firms) {
        if (!row.firm.valid()) {
            continue;
        }
        nb::dict item;
        item["firm_id"] = row.firm.value();
        item["stratum"] = static_cast<std::uint8_t>(row.stratum);
        item["insolvent_days"] = row.insolvent_days;
        item["shell_days"] = row.shell_days;
        item["subscale_days"] = row.subscale_days;
        item["switch_pressure_days"] = row.switch_pressure_days;
        item["residual_income_ema"] = row.residual_income_ema;
        item["tobin_q_ema"] = row.tobin_q_ema;
        item["active"] = row.active;
        item["defaulted"] = row.defaulted;
        item["cash"] = row.statement.cash;
        item["debt"] = row.statement.debt;
        item["interest_arrears"] = row.statement.interest_arrears;
        item["capital_units"] = row.statement.capital_units;
        item["capital_unit_price"] = row.statement.capital_unit_price;
        item["capital_value"] = row.statement.capital_value;
        item["output_inventory_units"] = row.statement.output_inventory_units;
        item["output_inventory_unit_price"] = row.statement.output_inventory_unit_price;
        item["output_inventory_value"] = row.statement.output_inventory_value;
        item["inventory_value"] = row.statement.inventory_value;
        item["gross_assets"] = row.statement.gross_assets;
        item["book_equity"] = row.statement.book_equity;
        item["eligible_collateral_value"] = row.statement.eligible_collateral_value;
        item["borrowing_base_proxy"] = row.statement.borrowing_base_proxy;
        item["borrowing_base_headroom"] = row.statement.borrowing_base_headroom;
        item["earnings"] = row.statement.earnings;
        firms.append(std::move(item));
    }
    output["bonds"] = std::move(bonds);
    output["equities"] = std::move(equities);
    output["security_lots"] = std::move(lots);
    output["firm_statements"] = std::move(firms);
    output["metrics"] = m6_metrics_to_python(runtime->last_metrics);
    return output;
}

nb::dict m4_snapshot_to_python(const macro_sim::EngineSession &session) {
    if (session.root() == nullptr || session.simulation_runtime() == nullptr) {
        throw std::runtime_error("invalid_handle: session has no active simulation");
    }
    nb::list households;
    session.root()->households.for_each_alive(
        [&households](macro_sim::HouseholdId id,
                      const macro_sim::core::HouseholdComponent &household) {
            nb::dict item;
            item["id"] = id.value();
            item["account"] = household.primary_account.value();
            item["income_expected"] = household.income_expected;
            item["income_realized"] = household.income_realized;
            item["consumption_budget"] = household.consumption_budget;
            item["spent"] = household.spent;
            item["labor_sold"] = household.labor_sold;
            households.append(std::move(item));
        });
    nb::list firms;
    session.root()->firms.for_each_alive(
        [&firms](macro_sim::FirmId id, const macro_sim::core::FirmComponent &firm) {
            nb::dict item;
            item["id"] = id.value();
            item["sector"] = static_cast<std::uint8_t>(firm.sector);
            item["account"] = firm.primary_account.value();
            item["inventory"] = firm.goods_inventory.value();
            item["capital"] = firm.physical_capital.value();
            item["price"] = firm.posted_price.value();
            item["wage"] = firm.posted_wage.value();
            item["expected_demand"] = firm.demand_expected;
            item["previous_sales"] = firm.sales_previous;
            firms.append(std::move(item));
        });
    nb::list balances;
    for (const auto &account : session.root()->postings.records()) {
        balances.append(account.balance.value());
    }
    nb::dict output;
    const auto digest = session.digest();
    require_status(digest.status());
    output["digest"] = digest.get_if()->hex();
    output["tick"] = session.tick().value();
    output["households"] = std::move(households);
    output["firms"] = std::move(firms);
    output["balances"] = std::move(balances);
    output["technology_index"] = session.simulation_runtime()->technology_index;
    output["public_capital"] = session.simulation_runtime()->public_capital;
    nb::list rng_counter;
    for (const auto value : session.simulation_runtime()->rng_counter) {
        rng_counter.append(value);
    }
    output["rng_counter"] = std::move(rng_counter);
    nb::list phase_trace;
    for (const auto &phase : session.simulation_runtime()->last_phase_trace) {
        nb::dict item;
        item["phase"] = static_cast<std::uint8_t>(phase.phase);
        item["money_total"] = phase.money_total;
        item["goods_total"] = phase.goods_total;
        item["capital_total"] = phase.capital_total;
        item["transfer_count"] = phase.transfer_count;
        item["trade_count"] = phase.trade_count;
        phase_trace.append(std::move(item));
    }
    output["phase_trace"] = std::move(phase_trace);
    output["metrics"] =
        m4_metrics_to_python(session.simulation_runtime()->last_metrics);
    return output;
}

} // namespace

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version",
               []() { return std::string(macro_sim::engine_version()); });
    macro_sim::python_m3::bind(module);
    module.def(
        "validate_scalar",
        [](std::string_view contract_id, nb::object value) {
            const auto scalar = scalar_from_python(value);
            const auto code =
                macro_sim::generated::validate_scalar(contract_id, {
                                                                       scalar.kind,
                                                                       scalar.number,
                                                                       scalar.text,
                                                                   });
            return std::pair(
                code == macro_sim::generated::ValidationCode::ok,
                std::string(macro_sim::generated::validation_code_name(code)));
        },
        nb::arg("contract_id"), nb::arg("value").none());
    module.def(
        "philox_block",
        [](macro_sim::PhiloxCounter counter, macro_sim::PhiloxKey key) {
            const auto block = macro_sim::philox4x32_10(counter, key);
            return nb::make_tuple(block[0], block[1], block[2], block[3]);
        },
        nb::arg("counter"), nb::arg("key"));
    module.def("m6_bond_price", &macro_sim::simulation::bond_price, nb::arg("face"),
               nb::arg("remaining_days"), nb::arg("required_return"),
               nb::arg("coupon_rate"));
    nb::enum_<macro_sim::SessionState>(module, "SessionState")
        .value("READY", macro_sim::SessionState::ready)
        .value("CLOSED", macro_sim::SessionState::closed);
    nb::enum_<macro_sim::core::GenesisVertical>(module, "GenesisVertical")
        .value("M4_V0_CASH_LOOP", macro_sim::core::GenesisVertical::m4_v0_cash_loop)
        .value("M4_V1_CAPITAL_FISCAL",
               macro_sim::core::GenesisVertical::m4_v1_capital_fiscal);
    nb::enum_<macro_sim::simulation::M4Vertical>(module, "M4Vertical")
        .value("CASH_LOOP", macro_sim::simulation::M4Vertical::cash_loop)
        .value("CAPITAL_FISCAL", macro_sim::simulation::M4Vertical::capital_fiscal);
    nb::enum_<macro_sim::algorithms::MatchingProtocol>(module, "MatchingProtocol")
        .value("SAMPLED", macro_sim::algorithms::MatchingProtocol::sampled)
        .value("PREFERENTIAL", macro_sim::algorithms::MatchingProtocol::preferential)
        .value("PRICE_SORTED", macro_sim::algorithms::MatchingProtocol::price_sorted);
    auto m4_rules =
        nb::class_<macro_sim::simulation::M4Rules>(module, "M4Rules").def(nb::init<>());
#define MACRO_SIM_BIND_M4_RULE(field)                                                  \
    m4_rules.def_rw(#field, &macro_sim::simulation::M4Rules::field)
    MACRO_SIM_BIND_M4_RULE(linear_productivity);
    MACRO_SIM_BIND_M4_RULE(capital_productivity);
    MACRO_SIM_BIND_M4_RULE(total_factor_productivity);
    MACRO_SIM_BIND_M4_RULE(capital_share);
    MACRO_SIM_BIND_M4_RULE(capital_output_ratio);
    MACRO_SIM_BIND_M4_RULE(demand_adjustment);
    MACRO_SIM_BIND_M4_RULE(income_adjustment);
    MACRO_SIM_BIND_M4_RULE(inventory_ratio);
    MACRO_SIM_BIND_M4_RULE(inventory_gap_close);
    MACRO_SIM_BIND_M4_RULE(markup_adjustment);
    MACRO_SIM_BIND_M4_RULE(markup_minimum);
    MACRO_SIM_BIND_M4_RULE(markup_maximum);
    MACRO_SIM_BIND_M4_RULE(wage_shortage_adjustment);
    MACRO_SIM_BIND_M4_RULE(wage_downward_drift);
    MACRO_SIM_BIND_M4_RULE(wage_calvo_probability);
    MACRO_SIM_BIND_M4_RULE(price_calvo_probability);
    MACRO_SIM_BIND_M4_RULE(income_propensity);
    MACRO_SIM_BIND_M4_RULE(wealth_propensity);
    MACRO_SIM_BIND_M4_RULE(dividend_payout);
    MACRO_SIM_BIND_M4_RULE(investment_adjustment);
    MACRO_SIM_BIND_M4_RULE(capital_depreciation);
    MACRO_SIM_BIND_M4_RULE(annual_tfp_growth);
    MACRO_SIM_BIND_M4_RULE(profit_tax_rate);
    MACRO_SIM_BIND_M4_RULE(income_tax_rate);
    MACRO_SIM_BIND_M4_RULE(consumption_tax_rate);
    MACRO_SIM_BIND_M4_RULE(necessity_consumption_tax_rate);
    MACRO_SIM_BIND_M4_RULE(luxury_consumption_tax_rate);
    MACRO_SIM_BIND_M4_RULE(wealth_tax_rate);
    MACRO_SIM_BIND_M4_RULE(government_consumption_share);
    MACRO_SIM_BIND_M4_RULE(government_deficit_target);
    MACRO_SIM_BIND_M4_RULE(deficit_unemployment_reference);
    MACRO_SIM_BIND_M4_RULE(deficit_unemployment_cap);
    MACRO_SIM_BIND_M4_RULE(government_investment_share);
    MACRO_SIM_BIND_M4_RULE(public_capital_gamma);
    MACRO_SIM_BIND_M4_RULE(public_capital_depreciation);
    MACRO_SIM_BIND_M4_RULE(unemployment_benefit_replacement);
    MACRO_SIM_BIND_M4_RULE(income_allowance);
    MACRO_SIM_BIND_M4_RULE(wealth_allowance);
    MACRO_SIM_BIND_M4_RULE(benefit_income_floor);
    MACRO_SIM_BIND_M4_RULE(minimum_wage);
    MACRO_SIM_BIND_M4_RULE(job_guarantee);
    MACRO_SIM_BIND_M4_RULE(job_guarantee_wage_ratio);
    MACRO_SIM_BIND_M4_RULE(job_guarantee_public_works_share);
    MACRO_SIM_BIND_M4_RULE(initial_household_money);
    MACRO_SIM_BIND_M4_RULE(initial_firm_money);
    MACRO_SIM_BIND_M4_RULE(initial_bank_capital);
    MACRO_SIM_BIND_M4_RULE(initial_consumption_inventory);
    MACRO_SIM_BIND_M4_RULE(initial_capital_inventory);
    MACRO_SIM_BIND_M4_RULE(initial_consumption_capital);
    MACRO_SIM_BIND_M4_RULE(initial_price);
    MACRO_SIM_BIND_M4_RULE(initial_capital_price);
    MACRO_SIM_BIND_M4_RULE(initial_wage);
    MACRO_SIM_BIND_M4_RULE(initial_markup);
    MACRO_SIM_BIND_M4_RULE(initial_expected_demand);
    MACRO_SIM_BIND_M4_RULE(capital_rationed_signal);
    MACRO_SIM_BIND_M4_RULE(consumption_rationed_signal);
    MACRO_SIM_BIND_M4_RULE(market_sample_size);
#undef MACRO_SIM_BIND_M4_RULE
    nb::class_<macro_sim::simulation::M4SimulationSpec>(module, "M4SimulationSpec")
        .def(nb::init<>())
        .def_rw("vertical", &macro_sim::simulation::M4SimulationSpec::vertical)
        .def_prop_rw(
            "economy_id",
            [](const macro_sim::simulation::M4SimulationSpec &spec) {
                return spec.economy.value();
            },
            [](macro_sim::simulation::M4SimulationSpec &spec, std::uint64_t value) {
                spec.economy = macro_sim::EconomyId(value);
            })
        .def_prop_rw(
            "currency_id",
            [](const macro_sim::simulation::M4SimulationSpec &spec) {
                return spec.currency.value();
            },
            [](macro_sim::simulation::M4SimulationSpec &spec, std::uint32_t value) {
                spec.currency = macro_sim::CurrencyId(value);
            })
        .def_rw("households", &macro_sim::simulation::M4SimulationSpec::households)
        .def_rw("consumption_firms",
                &macro_sim::simulation::M4SimulationSpec::consumption_firms)
        .def_rw("capital_firms",
                &macro_sim::simulation::M4SimulationSpec::capital_firms)
        .def_rw("settlement_banks",
                &macro_sim::simulation::M4SimulationSpec::settlement_banks)
        .def_rw("seed", &macro_sim::simulation::M4SimulationSpec::seed)
        .def_rw("requested_capabilities",
                &macro_sim::simulation::M4SimulationSpec::requested_capabilities)
        .def_rw("stochastic", &macro_sim::simulation::M4SimulationSpec::stochastic)
        .def_rw("market_protocol",
                &macro_sim::simulation::M4SimulationSpec::market_protocol)
        .def_rw("rules", &macro_sim::simulation::M4SimulationSpec::rules);
    nb::enum_<macro_sim::simulation::MonetaryRegime>(module, "MonetaryRegime")
        .value("EXOGENOUS", macro_sim::simulation::MonetaryRegime::exogenous)
        .value("TAYLOR", macro_sim::simulation::MonetaryRegime::taylor)
        .value("MANUAL", macro_sim::simulation::MonetaryRegime::manual);
    auto m5_policy =
        nb::class_<macro_sim::simulation::M5PolicyState>(module, "M5Policy")
            .def(nb::init<>());
#define MACRO_SIM_BIND_M5_POLICY(field)                                                \
    m5_policy.def_rw(#field, &macro_sim::simulation::M5PolicyState::field)
    MACRO_SIM_BIND_M5_POLICY(government_consumption_share);
    MACRO_SIM_BIND_M5_POLICY(government_deficit_target);
    MACRO_SIM_BIND_M5_POLICY(deficit_unemployment_reference);
    MACRO_SIM_BIND_M5_POLICY(deficit_unemployment_cap);
    MACRO_SIM_BIND_M5_POLICY(government_investment_share);
    MACRO_SIM_BIND_M5_POLICY(profit_tax_rate);
    MACRO_SIM_BIND_M5_POLICY(income_tax_rate);
    MACRO_SIM_BIND_M5_POLICY(income_allowance);
    MACRO_SIM_BIND_M5_POLICY(consumption_tax_rate);
    MACRO_SIM_BIND_M5_POLICY(wealth_tax_rate);
    MACRO_SIM_BIND_M5_POLICY(wealth_allowance);
    MACRO_SIM_BIND_M5_POLICY(unemployment_benefit_replacement);
    MACRO_SIM_BIND_M5_POLICY(benefit_income_floor);
    MACRO_SIM_BIND_M5_POLICY(minimum_wage);
    MACRO_SIM_BIND_M5_POLICY(job_guarantee);
    MACRO_SIM_BIND_M5_POLICY(job_guarantee_wage_ratio);
    MACRO_SIM_BIND_M5_POLICY(job_guarantee_public_works_share);
    MACRO_SIM_BIND_M5_POLICY(monetary_regime);
    MACRO_SIM_BIND_M5_POLICY(inflation_target);
    MACRO_SIM_BIND_M5_POLICY(taylor_inflation);
    MACRO_SIM_BIND_M5_POLICY(taylor_unemployment);
    MACRO_SIM_BIND_M5_POLICY(rate_inertia);
    MACRO_SIM_BIND_M5_POLICY(neutral_rate);
    MACRO_SIM_BIND_M5_POLICY(natural_unemployment);
    MACRO_SIM_BIND_M5_POLICY(maximum_policy_rate);
    MACRO_SIM_BIND_M5_POLICY(inflation_sensor_lambda);
    MACRO_SIM_BIND_M5_POLICY(core_inflation_sensor);
    MACRO_SIM_BIND_M5_POLICY(fixed_basket_cpi);
    MACRO_SIM_BIND_M5_POLICY(logarithmic_inflation);
    MACRO_SIM_BIND_M5_POLICY(fiscal_uses_national_accounts_gdp);
    MACRO_SIM_BIND_M5_POLICY(open_market_operations);
    MACRO_SIM_BIND_M5_POLICY(reserve_target);
    MACRO_SIM_BIND_M5_POLICY(reserve_gap_close);
    MACRO_SIM_BIND_M5_POLICY(reserve_target_indexes_deposits);
    MACRO_SIM_BIND_M5_POLICY(lender_of_last_resort);
    MACRO_SIM_BIND_M5_POLICY(reserve_floor_fraction);
    MACRO_SIM_BIND_M5_POLICY(firm_leverage_limit);
    MACRO_SIM_BIND_M5_POLICY(firm_minimum_dscr);
    MACRO_SIM_BIND_M5_POLICY(household_credit_limit);
    MACRO_SIM_BIND_M5_POLICY(bank_capital_constraint);
    MACRO_SIM_BIND_M5_POLICY(unified_bank_rwa);
    MACRO_SIM_BIND_M5_POLICY(bank_leverage_cap);
    MACRO_SIM_BIND_M5_POLICY(bank_exposure_limit);
    MACRO_SIM_BIND_M5_POLICY(bank_target_capital_ratio);
    MACRO_SIM_BIND_M5_POLICY(deposit_rate_floor);
    MACRO_SIM_BIND_M5_POLICY(migrate_relationships_on_failure);
    MACRO_SIM_BIND_M5_POLICY(state_resolution_backstop);
#undef MACRO_SIM_BIND_M5_POLICY
    module.def(
        "_validate_m5_policy",
        [](const macro_sim::simulation::M5PolicyState &policy) {
            require_status(macro_sim::simulation::validate_m5_policy(policy));
        },
        nb::arg("policy"));
    m5_policy.def_prop_rw(
        "manual_policy_rate",
        [](const macro_sim::simulation::M5PolicyState &policy) {
            if (!policy.manual_policy_rate.has_value()) {
                return nb::object(nb::none());
            }
            return nb::object(nb::float_(*policy.manual_policy_rate));
        },
        [](macro_sim::simulation::M5PolicyState &policy, nb::handle value) {
            if (value.is_none()) {
                policy.manual_policy_rate.reset();
            } else {
                policy.manual_policy_rate = nb::cast<double>(value);
            }
        },
        nb::for_setter(nb::arg("value").none()));
    const auto bind_optional_rate =
        [&m5_policy](
            const char *name,
            std::optional<double> macro_sim::simulation::M5PolicyState::*field) {
            m5_policy.def_prop_rw(
                name,
                [field](
                    const macro_sim::simulation::M5PolicyState &policy) -> nb::object {
                    const auto &value = policy.*field;
                    return value.has_value() ? nb::object(nb::float_(*value))
                                             : nb::object(nb::none());
                },
                [field](macro_sim::simulation::M5PolicyState &policy,
                        nb::handle value) {
                    if (value.is_none()) {
                        (policy.*field).reset();
                    } else {
                        policy.*field = nb::cast<double>(value);
                    }
                },
                nb::for_setter(nb::arg("value").none()));
        };
    bind_optional_rate(
        "necessity_consumption_tax_rate",
        &macro_sim::simulation::M5PolicyState::necessity_consumption_tax_rate);
    bind_optional_rate(
        "luxury_consumption_tax_rate",
        &macro_sim::simulation::M5PolicyState::luxury_consumption_tax_rate);
    auto m5_rules =
        nb::class_<macro_sim::simulation::M5Rules>(module, "M5Rules").def(nb::init<>());
#define MACRO_SIM_BIND_M5_RULE(field)                                                  \
    m5_rules.def_rw(#field, &macro_sim::simulation::M5Rules::field)
    MACRO_SIM_BIND_M5_RULE(bank_count);
    MACRO_SIM_BIND_M5_RULE(opening_capital_per_bank);
    MACRO_SIM_BIND_M5_RULE(bank_leverage_mean);
    MACRO_SIM_BIND_M5_RULE(bank_leverage_dispersion);
    MACRO_SIM_BIND_M5_RULE(assign_banks_by_size);
    MACRO_SIM_BIND_M5_RULE(realized_bank_pnl);
    MACRO_SIM_BIND_M5_RULE(full_firm_pnl);
    MACRO_SIM_BIND_M5_RULE(household_credit);
    MACRO_SIM_BIND_M5_RULE(rate_competition);
    MACRO_SIM_BIND_M5_RULE(relationship_lock_in);
    MACRO_SIM_BIND_M5_RULE(loan_spread_dispersion);
    MACRO_SIM_BIND_M5_RULE(bank_search_count);
    MACRO_SIM_BIND_M5_RULE(interbank);
    MACRO_SIM_BIND_M5_RULE(interbank_rate_base);
    MACRO_SIM_BIND_M5_RULE(interbank_tightness);
    MACRO_SIM_BIND_M5_RULE(deposit_spread_dispersion);
    MACRO_SIM_BIND_M5_RULE(deposit_search_count);
    MACRO_SIM_BIND_M5_RULE(deposit_rate);
    MACRO_SIM_BIND_M5_RULE(deposit_interest_arrears);
    MACRO_SIM_BIND_M5_RULE(interest_by_deposits);
    MACRO_SIM_BIND_M5_RULE(firm_amortization);
    MACRO_SIM_BIND_M5_RULE(household_amortization);
    MACRO_SIM_BIND_M5_RULE(household_subsistence);
    MACRO_SIM_BIND_M5_RULE(direct_monetary_transmission);
    MACRO_SIM_BIND_M5_RULE(bank_runs);
    MACRO_SIM_BIND_M5_RULE(run_sensitivity);
    MACRO_SIM_BIND_M5_RULE(run_health_reference);
    MACRO_SIM_BIND_M5_RULE(run_fear_persistence);
    MACRO_SIM_BIND_M5_RULE(bank_payout_ratio);
#undef MACRO_SIM_BIND_M5_RULE
    nb::class_<macro_sim::simulation::M5SimulationSpec>(module, "M5SimulationSpec")
        .def(nb::init<>())
        .def_rw("real_economy", &macro_sim::simulation::M5SimulationSpec::real_economy)
        .def_rw("policy", &macro_sim::simulation::M5SimulationSpec::policy)
        .def_rw("rules", &macro_sim::simulation::M5SimulationSpec::rules)
        .def_rw("initial_policy_rate",
                &macro_sim::simulation::M5SimulationSpec::initial_policy_rate);
    nb::enum_<macro_sim::simulation::ConsumptionStratum>(module, "ConsumptionStratum")
        .value("NECESSITY", macro_sim::simulation::ConsumptionStratum::necessity)
        .value("LUXURY", macro_sim::simulation::ConsumptionStratum::luxury);
    auto m6_policy =
        nb::class_<macro_sim::simulation::M6PolicyState>(module, "M6Policy")
            .def(nb::init<>());
#define MACRO_SIM_BIND_M6_POLICY(field)                                                \
    m6_policy.def_rw(#field, &macro_sim::simulation::M6PolicyState::field)
    MACRO_SIM_BIND_M6_POLICY(bond_finance_fraction);
    MACRO_SIM_BIND_M6_POLICY(bond_coupon_rate);
    MACRO_SIM_BIND_M6_POLICY(bond_maturity_days);
    MACRO_SIM_BIND_M6_POLICY(household_bond_target);
    MACRO_SIM_BIND_M6_POLICY(bank_bond_appetite);
    MACRO_SIM_BIND_M6_POLICY(bank_bond_duration_limit);
    MACRO_SIM_BIND_M6_POLICY(margin_ltv);
    MACRO_SIM_BIND_M6_POLICY(margin_max);
    MACRO_SIM_BIND_M6_POLICY(household_bankruptcy);
    MACRO_SIM_BIND_M6_POLICY(bank_resolution_fund);
    MACRO_SIM_BIND_M6_POLICY(bank_minimum_capital);
    MACRO_SIM_BIND_M6_POLICY(bankrupt_persistence);
    MACRO_SIM_BIND_M6_POLICY(regulatory_capital_haircut);
    MACRO_SIM_BIND_M6_POLICY(regulatory_inventory_haircut);
#undef MACRO_SIM_BIND_M6_POLICY
    auto m6_rules =
        nb::class_<macro_sim::simulation::M6Rules>(module, "M6Rules").def(nb::init<>());
#define MACRO_SIM_BIND_M6_RULE(field)                                                  \
    m6_rules.def_rw(#field, &macro_sim::simulation::M6Rules::field)
    MACRO_SIM_BIND_M6_RULE(bonds);
    MACRO_SIM_BIND_M6_RULE(bond_maturity_bucket);
    MACRO_SIM_BIND_M6_RULE(firm_equity);
    MACRO_SIM_BIND_M6_RULE(shares_per_firm);
    MACRO_SIM_BIND_M6_RULE(watchlist_size);
    MACRO_SIM_BIND_M6_RULE(founder_owned_genesis);
    MACRO_SIM_BIND_M6_RULE(genesis_founder_pool);
    MACRO_SIM_BIND_M6_RULE(equity_price_adjustment);
    MACRO_SIM_BIND_M6_RULE(equity_trend_lambda);
    MACRO_SIM_BIND_M6_RULE(residual_income_lambda);
    MACRO_SIM_BIND_M6_RULE(q_smoothing);
    MACRO_SIM_BIND_M6_RULE(fundamental_weight);
    MACRO_SIM_BIND_M6_RULE(chartist_weight);
    MACRO_SIM_BIND_M6_RULE(household_equity_target);
    MACRO_SIM_BIND_M6_RULE(portfolio_adjustment);
    MACRO_SIM_BIND_M6_RULE(portfolio_review_interval_days);
    MACRO_SIM_BIND_M6_RULE(equity_finance);
    MACRO_SIM_BIND_M6_RULE(equity_issue_lambda);
    MACRO_SIM_BIND_M6_RULE(margin_credit);
    MACRO_SIM_BIND_M6_RULE(valuation_discount_floor);
    MACRO_SIM_BIND_M6_RULE(valuation_risk_premium);
    MACRO_SIM_BIND_M6_RULE(capital_haircut);
    MACRO_SIM_BIND_M6_RULE(inventory_haircut);
    MACRO_SIM_BIND_M6_RULE(firm_dynamics);
    MACRO_SIM_BIND_M6_RULE(bankrupt_persistence);
    MACRO_SIM_BIND_M6_RULE(shell_exit_days);
    MACRO_SIM_BIND_M6_RULE(entry_hurdle);
    MACRO_SIM_BIND_M6_RULE(entry_beta);
    MACRO_SIM_BIND_M6_RULE(entry_max);
    MACRO_SIM_BIND_M6_RULE(startup_deposits);
    MACRO_SIM_BIND_M6_RULE(startup_capital);
    MACRO_SIM_BIND_M6_RULE(firm_subscale_exit);
    MACRO_SIM_BIND_M6_RULE(capital_firm_entry);
    MACRO_SIM_BIND_M6_RULE(subscale_viability_workers);
    MACRO_SIM_BIND_M6_RULE(subscale_grace_days);
    MACRO_SIM_BIND_M6_RULE(subscale_exit_hazard);
    MACRO_SIM_BIND_M6_RULE(k_entry_demand);
    MACRO_SIM_BIND_M6_RULE(k_entry_hazard);
    MACRO_SIM_BIND_M6_RULE(consumption_strata);
    MACRO_SIM_BIND_M6_RULE(initial_necessity_share);
    MACRO_SIM_BIND_M6_RULE(sector_switching);
    MACRO_SIM_BIND_M6_RULE(switch_return_gap);
    MACRO_SIM_BIND_M6_RULE(switch_pressure_days);
    MACRO_SIM_BIND_M6_RULE(switch_hazard);
    MACRO_SIM_BIND_M6_RULE(switch_retool_loss);
    MACRO_SIM_BIND_M6_RULE(bank_equity);
    MACRO_SIM_BIND_M6_RULE(bank_equity_trading);
    MACRO_SIM_BIND_M6_RULE(bank_shares);
    MACRO_SIM_BIND_M6_RULE(bank_equity_lambda);
    MACRO_SIM_BIND_M6_RULE(bank_equity_target);
    MACRO_SIM_BIND_M6_RULE(bank_dynamics);
    MACRO_SIM_BIND_M6_RULE(bank_entry_beta);
    MACRO_SIM_BIND_M6_RULE(bank_entry_max);
#undef MACRO_SIM_BIND_M6_RULE
    nb::class_<macro_sim::simulation::M6SimulationSpec>(module, "M6SimulationSpec")
        .def(nb::init<>())
        .def_rw("monetary_economy",
                &macro_sim::simulation::M6SimulationSpec::monetary_economy)
        .def_rw("policy", &macro_sim::simulation::M6SimulationSpec::policy)
        .def_rw("rules", &macro_sim::simulation::M6SimulationSpec::rules);
    auto vital = nb::class_<macro_sim::algorithms::VitalRates>(module, "VitalRates")
                     .def(nb::init<>());
#define MACRO_SIM_BIND_VITAL(field)                                                    \
    vital.def_rw(#field, &macro_sim::algorithms::VitalRates::field)
    MACRO_SIM_BIND_VITAL(makeham_a);
    MACRO_SIM_BIND_VITAL(gompertz_b);
    MACRO_SIM_BIND_VITAL(gompertz_theta);
    MACRO_SIM_BIND_VITAL(infant_extra);
    MACRO_SIM_BIND_VITAL(total_fertility_rate);
    MACRO_SIM_BIND_VITAL(fertility_peak_age);
    MACRO_SIM_BIND_VITAL(fertility_width);
    MACRO_SIM_BIND_VITAL(sex_ratio_at_birth);
    MACRO_SIM_BIND_VITAL(maximum_age);
    MACRO_SIM_BIND_VITAL(interval);
#undef MACRO_SIM_BIND_VITAL
    auto marriage_rules =
        nb::class_<macro_sim::core::MarriageRules>(module, "MarriageRules")
            .def(nb::init<>());
#define MACRO_SIM_BIND_MARRIAGE(field)                                                 \
    marriage_rules.def_rw(#field, &macro_sim::core::MarriageRules::field)
    MACRO_SIM_BIND_MARRIAGE(minimum_age);
    MACRO_SIM_BIND_MARRIAGE(maximum_age);
    MACRO_SIM_BIND_MARRIAGE(maximum_age_gap);
    MACRO_SIM_BIND_MARRIAGE(preferred_age_gap);
    MACRO_SIM_BIND_MARRIAGE(age_gap_penalty);
    MACRO_SIM_BIND_MARRIAGE(assortativity);
    MACRO_SIM_BIND_MARRIAGE(forbid_same_household);
    MACRO_SIM_BIND_MARRIAGE(forbid_close_kin);
#undef MACRO_SIM_BIND_MARRIAGE
    nb::class_<macro_sim::simulation::M7PolicyState>(module, "M7Policy")
        .def(nb::init<>())
        .def_rw("inheritance_tax_rate",
                &macro_sim::simulation::M7PolicyState::inheritance_tax_rate)
        .def_rw("pension_replacement",
                &macro_sim::simulation::M7PolicyState::pension_replacement);
    auto m7_rules =
        nb::class_<macro_sim::simulation::M7Rules>(module, "M7Rules").def(nb::init<>());
#define MACRO_SIM_BIND_M7_RULE(field)                                                  \
    m7_rules.def_rw(#field, &macro_sim::simulation::M7Rules::field)
    MACRO_SIM_BIND_M7_RULE(vital_rates);
    MACRO_SIM_BIND_M7_RULE(working_age);
    MACRO_SIM_BIND_M7_RULE(retirement_age);
    MACRO_SIM_BIND_M7_RULE(beneficial_ownership);
    MACRO_SIM_BIND_M7_RULE(estates);
    MACRO_SIM_BIND_M7_RULE(fertility);
    MACRO_SIM_BIND_M7_RULE(mortality);
    MACRO_SIM_BIND_M7_RULE(persistent_labor);
    MACRO_SIM_BIND_M7_RULE(fractional_hours);
    MACRO_SIM_BIND_M7_RULE(second_jobs);
    MACRO_SIM_BIND_M7_RULE(suspensions);
    MACRO_SIM_BIND_M7_RULE(efficiency_sigma);
    MACRO_SIM_BIND_M7_RULE(annual_churn);
    MACRO_SIM_BIND_M7_RULE(firing_adjustment);
    MACRO_SIM_BIND_M7_RULE(layoff_band);
    MACRO_SIM_BIND_M7_RULE(target_smoothing);
    MACRO_SIM_BIND_M7_RULE(suspension_timeout_days);
    MACRO_SIM_BIND_M7_RULE(frictional_search);
    MACRO_SIM_BIND_M7_RULE(search_intensity);
    MACRO_SIM_BIND_M7_RULE(relationship_wages);
    MACRO_SIM_BIND_M7_RULE(job_ladder);
    MACRO_SIM_BIND_M7_RULE(ladder_search_intensity);
    MACRO_SIM_BIND_M7_RULE(ladder_premium);
    MACRO_SIM_BIND_M7_RULE(participation_margin);
    MACRO_SIM_BIND_M7_RULE(age_participation);
    MACRO_SIM_BIND_M7_RULE(young_participation_rate);
    MACRO_SIM_BIND_M7_RULE(prime_participation_rate);
    MACRO_SIM_BIND_M7_RULE(older_participation_rate);
    MACRO_SIM_BIND_M7_RULE(reservation_markup);
    MACRO_SIM_BIND_M7_RULE(welfare_quit_hazard);
    MACRO_SIM_BIND_M7_RULE(family_transfers);
    MACRO_SIM_BIND_M7_RULE(family_transfer_buffer);
    MACRO_SIM_BIND_M7_RULE(relationships);
    MACRO_SIM_BIND_M7_RULE(marriage);
    MACRO_SIM_BIND_M7_RULE(divorce);
    MACRO_SIM_BIND_M7_RULE(household_lifecycle);
    MACRO_SIM_BIND_M7_RULE(leaving_home);
    MACRO_SIM_BIND_M7_RULE(leave_home_min_age);
    MACRO_SIM_BIND_M7_RULE(leave_home_peak_end_age);
    MACRO_SIM_BIND_M7_RULE(annual_leave_rate_peak);
    MACRO_SIM_BIND_M7_RULE(annual_leave_rate_late);
    MACRO_SIM_BIND_M7_RULE(marriage_interval_days);
    MACRO_SIM_BIND_M7_RULE(annual_marriage_rate);
    MACRO_SIM_BIND_M7_RULE(annual_divorce_rate);
    MACRO_SIM_BIND_M7_RULE(marriage_rules);
#undef MACRO_SIM_BIND_M7_RULE
    nb::class_<macro_sim::simulation::M7PopulationSpec>(module, "M7PopulationSpec")
        .def(nb::init<>())
        .def_rw("initial_persons",
                &macro_sim::simulation::M7PopulationSpec::initial_persons)
        .def_rw("start_calendar_day",
                &macro_sim::simulation::M7PopulationSpec::start_calendar_day)
        .def_rw("target_household_size",
                &macro_sim::simulation::M7PopulationSpec::target_household_size)
        .def_rw("fixed_genesis_vital_rates",
                &macro_sim::simulation::M7PopulationSpec::fixed_genesis_vital_rates)
        .def_rw("genesis_vital_rates",
                &macro_sim::simulation::M7PopulationSpec::genesis_vital_rates);
    nb::class_<macro_sim::simulation::M7SimulationSpec>(module, "M7SimulationSpec")
        .def(nb::init<>())
        .def_rw("financial_economy",
                &macro_sim::simulation::M7SimulationSpec::financial_economy)
        .def_rw("policy", &macro_sim::simulation::M7SimulationSpec::policy)
        .def_rw("rules", &macro_sim::simulation::M7SimulationSpec::rules)
        .def_rw("population", &macro_sim::simulation::M7SimulationSpec::population);
    nb::enum_<macro_sim::simulation::EnergyRationing>(module, "EnergyRationing")
        .value("MARKET", macro_sim::simulation::EnergyRationing::market)
        .value("PROPORTIONAL", macro_sim::simulation::EnergyRationing::proportional)
        .value("HOUSEHOLD_FIRST",
               macro_sim::simulation::EnergyRationing::household_first)
        .value("INDUSTRY_FIRST",
               macro_sim::simulation::EnergyRationing::industry_first);
    auto energy_policy =
        nb::class_<macro_sim::simulation::EnergyPolicyState>(module, "EnergyPolicy")
            .def(nb::init<>());
#define MACRO_SIM_BIND_ENERGY_POLICY(field)                                            \
    energy_policy.def_rw(#field, &macro_sim::simulation::EnergyPolicyState::field)
    MACRO_SIM_BIND_ENERGY_POLICY(excise_rate);
    MACRO_SIM_BIND_ENERGY_POLICY(windfall_tax_rate);
    MACRO_SIM_BIND_ENERGY_POLICY(household_subsidy_rate);
    MACRO_SIM_BIND_ENERGY_POLICY(subsidy_deposit_threshold);
    MACRO_SIM_BIND_ENERGY_POLICY(price_cap);
    MACRO_SIM_BIND_ENERGY_POLICY(price_cap_compensation);
    MACRO_SIM_BIND_ENERGY_POLICY(strategic_reserve_target);
    MACRO_SIM_BIND_ENERGY_POLICY(strategic_reserve_flow_cap);
    MACRO_SIM_BIND_ENERGY_POLICY(state_owned_price_at_cost);
    MACRO_SIM_BIND_ENERGY_POLICY(state_owned_first_producer);
    MACRO_SIM_BIND_ENERGY_POLICY(rationing);
#undef MACRO_SIM_BIND_ENERGY_POLICY
    auto energy_rules =
        nb::class_<macro_sim::simulation::EnergyRules>(module, "EnergyRules")
            .def(nb::init<>());
#define MACRO_SIM_BIND_ENERGY_RULE(field)                                              \
    energy_rules.def_rw(#field, &macro_sim::simulation::EnergyRules::field)
    MACRO_SIM_BIND_ENERGY_RULE(enabled);
    MACRO_SIM_BIND_ENERGY_RULE(household_energy);
    MACRO_SIM_BIND_ENERGY_RULE(deprivation);
    MACRO_SIM_BIND_ENERGY_RULE(state_owned_first_producer);
    MACRO_SIM_BIND_ENERGY_RULE(producer_count);
    MACRO_SIM_BIND_ENERGY_RULE(initial_producer_cash);
    MACRO_SIM_BIND_ENERGY_RULE(initial_price);
    MACRO_SIM_BIND_ENERGY_RULE(initial_wage);
    MACRO_SIM_BIND_ENERGY_RULE(initial_markup);
    MACRO_SIM_BIND_ENERGY_RULE(producer_productivity);
    MACRO_SIM_BIND_ENERGY_RULE(capacity_per_capital);
    MACRO_SIM_BIND_ENERGY_RULE(initial_utilization);
    MACRO_SIM_BIND_ENERGY_RULE(producer_inventory_ratio);
    MACRO_SIM_BIND_ENERGY_RULE(demand_adjustment);
    MACRO_SIM_BIND_ENERGY_RULE(markup_adjustment);
    MACRO_SIM_BIND_ENERGY_RULE(markup_minimum);
    MACRO_SIM_BIND_ENERGY_RULE(markup_maximum);
    MACRO_SIM_BIND_ENERGY_RULE(household_need);
    MACRO_SIM_BIND_ENERGY_RULE(downstream_intensity);
    MACRO_SIM_BIND_ENERGY_RULE(downstream_coverage_days);
    MACRO_SIM_BIND_ENERGY_RULE(downstream_gap_close);
    MACRO_SIM_BIND_ENERGY_RULE(hoarding_beta);
    MACRO_SIM_BIND_ENERGY_RULE(slow_price_days);
    MACRO_SIM_BIND_ENERGY_RULE(deprivation_burnin_years);
    MACRO_SIM_BIND_ENERGY_RULE(deprivation_subsistence_share);
    MACRO_SIM_BIND_ENERGY_RULE(deprivation_acute_days);
    MACRO_SIM_BIND_ENERGY_RULE(deprivation_chronic_days);
    MACRO_SIM_BIND_ENERGY_RULE(fuel_poverty_threshold);
    MACRO_SIM_BIND_ENERGY_RULE(fuel_poverty_mortality_gamma);
    MACRO_SIM_BIND_ENERGY_RULE(fuel_poverty_mortality_cap);
#undef MACRO_SIM_BIND_ENERGY_RULE
    auto energy_input =
        nb::class_<macro_sim::simulation::EnergyExogenousInput>(module, "EnergyInput")
            .def(nb::init<>());
#define MACRO_SIM_BIND_ENERGY_INPUT(field)                                             \
    energy_input.def_rw(#field, &macro_sim::simulation::EnergyExogenousInput::field)
    MACRO_SIM_BIND_ENERGY_INPUT(capacity_multiplier);
    MACRO_SIM_BIND_ENERGY_INPUT(labor_availability_multiplier);
    MACRO_SIM_BIND_ENERGY_INPUT(supply_multiplier);
    MACRO_SIM_BIND_ENERGY_INPUT(household_demand_multiplier);
    MACRO_SIM_BIND_ENERGY_INPUT(industry_demand_multiplier);
    MACRO_SIM_BIND_ENERGY_INPUT(reference_price_multiplier);
#undef MACRO_SIM_BIND_ENERGY_INPUT
    auto housing_policy =
        nb::class_<macro_sim::simulation::HousingPolicyState>(module, "HousingPolicy")
            .def(nb::init<>());
#define MACRO_SIM_BIND_HOUSING_POLICY(field)                                           \
    housing_policy.def_rw(#field, &macro_sim::simulation::HousingPolicyState::field)
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_ltv_cap);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_underwriting);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_dsti_cap);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_stress_rate_addon);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_risk_weight);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_minimum_capital_ratio);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_foreclosure_ltv);
    MACRO_SIM_BIND_HOUSING_POLICY(mortgage_arrears_floor);
    MACRO_SIM_BIND_HOUSING_POLICY(rental_eviction_arrears);
    MACRO_SIM_BIND_HOUSING_POLICY(annual_housing_permits);
    MACRO_SIM_BIND_HOUSING_POLICY(land_fee_share);
    MACRO_SIM_BIND_HOUSING_POLICY(land_fee_stock_elasticity);
    MACRO_SIM_BIND_HOUSING_POLICY(transfer_tax_rate);
    MACRO_SIM_BIND_HOUSING_POLICY(property_tax_rate);
    MACRO_SIM_BIND_HOUSING_POLICY(include_housing_in_wealth_tax);
    MACRO_SIM_BIND_HOUSING_POLICY(wealth_tax_rate);
#undef MACRO_SIM_BIND_HOUSING_POLICY
    auto housing_rules =
        nb::class_<macro_sim::simulation::HousingRules>(module, "HousingRules")
            .def(nb::init<>());
#define MACRO_SIM_BIND_HOUSING_RULE(field)                                             \
    housing_rules.def_rw(#field, &macro_sim::simulation::HousingRules::field)
    MACRO_SIM_BIND_HOUSING_RULE(enabled);
    MACRO_SIM_BIND_HOUSING_RULE(resale_market);
    MACRO_SIM_BIND_HOUSING_RULE(mortgages);
    MACRO_SIM_BIND_HOUSING_RULE(rentals);
    MACRO_SIM_BIND_HOUSING_RULE(construction);
    MACRO_SIM_BIND_HOUSING_RULE(house_price_income_years);
    MACRO_SIM_BIND_HOUSING_RULE(initial_dwellings_per_household);
    MACRO_SIM_BIND_HOUSING_RULE(initial_homeownership_share);
    MACRO_SIM_BIND_HOUSING_RULE(initial_floor_area);
    MACRO_SIM_BIND_HOUSING_RULE(initial_quality);
    MACRO_SIM_BIND_HOUSING_RULE(location_count);
    MACRO_SIM_BIND_HOUSING_RULE(market_interval_days);
    MACRO_SIM_BIND_HOUSING_RULE(voluntary_ask_markup);
    MACRO_SIM_BIND_HOUSING_RULE(forced_sale_discount);
    MACRO_SIM_BIND_HOUSING_RULE(ask_decay);
    MACRO_SIM_BIND_HOUSING_RULE(demand_price_step);
    MACRO_SIM_BIND_HOUSING_RULE(ask_floor_annual_wage_share);
    MACRO_SIM_BIND_HOUSING_RULE(buyer_search_count);
    MACRO_SIM_BIND_HOUSING_RULE(buyer_liquidity_buffer);
    MACRO_SIM_BIND_HOUSING_RULE(distress_deposit_floor);
    MACRO_SIM_BIND_HOUSING_RULE(initial_rent_yield);
    MACRO_SIM_BIND_HOUSING_RULE(rent_adjustment);
    MACRO_SIM_BIND_HOUSING_RULE(rent_burden_cap);
    MACRO_SIM_BIND_HOUSING_RULE(rental_investor_premium);
    MACRO_SIM_BIND_HOUSING_RULE(rental_vacancy_deadband);
    MACRO_SIM_BIND_HOUSING_RULE(rent_floor_wage_share);
    MACRO_SIM_BIND_HOUSING_RULE(builder_count);
    MACRO_SIM_BIND_HOUSING_RULE(initial_builder_cash_buffer);
    MACRO_SIM_BIND_HOUSING_RULE(builder_productivity);
    MACRO_SIM_BIND_HOUSING_RULE(builder_demand_seed);
    MACRO_SIM_BIND_HOUSING_RULE(builder_demand_price_gain);
    MACRO_SIM_BIND_HOUSING_RULE(builder_finished_inventory_buffer);
    MACRO_SIM_BIND_HOUSING_RULE(builder_land_fee_credit);
    MACRO_SIM_BIND_HOUSING_RULE(affordability_burnin_years);
    MACRO_SIM_BIND_HOUSING_RULE(leave_home_elasticity);
    MACRO_SIM_BIND_HOUSING_RULE(leave_home_multiplier_minimum);
    MACRO_SIM_BIND_HOUSING_RULE(leave_home_multiplier_maximum);
    MACRO_SIM_BIND_HOUSING_RULE(fertility_elasticity);
    MACRO_SIM_BIND_HOUSING_RULE(fertility_multiplier_minimum);
    MACRO_SIM_BIND_HOUSING_RULE(fertility_multiplier_maximum);
#undef MACRO_SIM_BIND_HOUSING_RULE
    auto housing_input =
        nb::class_<macro_sim::simulation::HousingExogenousInput>(module, "HousingInput")
            .def(nb::init<>());
#define MACRO_SIM_BIND_HOUSING_INPUT(field)                                            \
    housing_input.def_rw(#field, &macro_sim::simulation::HousingExogenousInput::field)
    MACRO_SIM_BIND_HOUSING_INPUT(house_price_reference_multiplier);
    MACRO_SIM_BIND_HOUSING_INPUT(buyer_demand_multiplier);
    MACRO_SIM_BIND_HOUSING_INPUT(rental_demand_multiplier);
    MACRO_SIM_BIND_HOUSING_INPUT(construction_productivity_multiplier);
    MACRO_SIM_BIND_HOUSING_INPUT(land_cost_multiplier);
#undef MACRO_SIM_BIND_HOUSING_INPUT
    nb::class_<macro_sim::simulation::M8SimulationSpec>(module, "M8SimulationSpec")
        .def(nb::init<>())
        .def_rw("domestic_economy",
                &macro_sim::simulation::M8SimulationSpec::domestic_economy)
        .def_rw("energy_policy",
                &macro_sim::simulation::M8SimulationSpec::energy_policy)
        .def_rw("energy_rules", &macro_sim::simulation::M8SimulationSpec::energy_rules)
        .def_rw("energy_input", &macro_sim::simulation::M8SimulationSpec::energy_input)
        .def_rw("housing_policy",
                &macro_sim::simulation::M8SimulationSpec::housing_policy)
        .def_rw("housing_rules",
                &macro_sim::simulation::M8SimulationSpec::housing_rules)
        .def_rw("housing_input",
                &macro_sim::simulation::M8SimulationSpec::housing_input);
    nb::enum_<macro_sim::simulation::FxRegime>(module, "FxRegime")
        .value("FLOAT", macro_sim::simulation::FxRegime::floating)
        .value("PEG", macro_sim::simulation::FxRegime::peg);
    nb::enum_<macro_sim::simulation::ShockKind>(module, "ShockKind")
        .value("PRODUCTIVITY", macro_sim::simulation::ShockKind::productivity)
        .value("LABOR_AVAILABILITY",
               macro_sim::simulation::ShockKind::labor_availability)
        .value("ENERGY_CAPACITY", macro_sim::simulation::ShockKind::energy_capacity)
        .value("HOUSEHOLD_DEMAND", macro_sim::simulation::ShockKind::household_demand)
        .value("IMPORT_CAPACITY", macro_sim::simulation::ShockKind::import_capacity)
        .value("EXPORT_CAPACITY", macro_sim::simulation::ShockKind::export_capacity)
        .value("CREDIT_SUPPLY", macro_sim::simulation::ShockKind::credit_supply)
        .value("CAPITAL_DESTRUCTION",
               macro_sim::simulation::ShockKind::capital_destruction);
    nb::enum_<macro_sim::simulation::ShockShape>(module, "ShockShape")
        .value("STEP", macro_sim::simulation::ShockShape::step)
        .value("LINEAR", macro_sim::simulation::ShockShape::linear)
        .value("TRIANGULAR", macro_sim::simulation::ShockShape::triangular);
    nb::enum_<macro_sim::simulation::ShockSector>(module, "ShockSector")
        .value("CONSUMPTION", macro_sim::simulation::ShockSector::consumption)
        .value("CAPITAL", macro_sim::simulation::ShockSector::capital)
        .value("ENERGY", macro_sim::simulation::ShockSector::energy)
        .value("HOUSING", macro_sim::simulation::ShockSector::housing)
        .value("PUBLIC", macro_sim::simulation::ShockSector::public_sector);
    nb::enum_<macro_sim::simulation::ShockEventType>(module, "ShockEventType")
        .value("ANNOUNCED", macro_sim::simulation::ShockEventType::announced)
        .value("STARTED", macro_sim::simulation::ShockEventType::started)
        .value("ENDED", macro_sim::simulation::ShockEventType::ended)
        .value("REALIZED", macro_sim::simulation::ShockEventType::realized);
    nb::enum_<macro_sim::simulation::CrisisScenario>(module, "CrisisScenario")
        .value("OIL_EMBARGO", macro_sim::simulation::CrisisScenario::oil_embargo)
        .value("GLOBAL_FINANCIAL_CRISIS",
               macro_sim::simulation::CrisisScenario::global_financial_crisis)
        .value("PANDEMIC", macro_sim::simulation::CrisisScenario::pandemic)
        .value("NATURAL_DISASTER",
               macro_sim::simulation::CrisisScenario::natural_disaster);
    auto world_rules =
        nb::class_<macro_sim::simulation::WorldRules>(module, "WorldRules")
            .def(nb::init<>());
#define MACRO_SIM_BIND_WORLD_RULE(field)                                               \
    world_rules.def_rw(#field, &macro_sim::simulation::WorldRules::field)
    MACRO_SIM_BIND_WORLD_RULE(trade);
    MACRO_SIM_BIND_WORLD_RULE(capital);
    MACRO_SIM_BIND_WORLD_RULE(migration);
    MACRO_SIM_BIND_WORLD_RULE(fx_adjustment);
    MACRO_SIM_BIND_WORLD_RULE(fx_friction);
    MACRO_SIM_BIND_WORLD_RULE(fx_spread);
    MACRO_SIM_BIND_WORLD_RULE(fx_loss_mutualization);
    MACRO_SIM_BIND_WORLD_RULE(fx_trade_cap);
    MACRO_SIM_BIND_WORLD_RULE(capital_mobility);
    MACRO_SIM_BIND_WORLD_RULE(capital_adjustment);
    MACRO_SIM_BIND_WORLD_RULE(periods_per_year);
    MACRO_SIM_BIND_WORLD_RULE(migration_rate);
    MACRO_SIM_BIND_WORLD_RULE(migration_max_share);
    MACRO_SIM_BIND_WORLD_RULE(remittance_share);
    MACRO_SIM_BIND_WORLD_RULE(wage_smoothing);
    MACRO_SIM_BIND_WORLD_RULE(initial_peg_reserves);
    MACRO_SIM_BIND_WORLD_RULE(dense_edge_threshold);
#undef MACRO_SIM_BIND_WORLD_RULE
    auto external_policy =
        nb::class_<macro_sim::simulation::ExternalPolicyState>(module, "ExternalPolicy")
            .def(nb::init<>());
#define MACRO_SIM_BIND_EXTERNAL_POLICY(field)                                          \
    external_policy.def_rw(#field, &macro_sim::simulation::ExternalPolicyState::field)
    MACRO_SIM_BIND_EXTERNAL_POLICY(tariff);
    MACRO_SIM_BIND_EXTERNAL_POLICY(import_quota);
    MACRO_SIM_BIND_EXTERNAL_POLICY(export_subsidy);
    MACRO_SIM_BIND_EXTERNAL_POLICY(capital_control);
    MACRO_SIM_BIND_EXTERNAL_POLICY(external_interest_settlement_fraction);
    MACRO_SIM_BIND_EXTERNAL_POLICY(immigration_cap);
    MACRO_SIM_BIND_EXTERNAL_POLICY(emigration_cap);
    MACRO_SIM_BIND_EXTERNAL_POLICY(remittance_tax);
    MACRO_SIM_BIND_EXTERNAL_POLICY(outward_remittance_tax);
    MACRO_SIM_BIND_EXTERNAL_POLICY(guest_worker_return);
    MACRO_SIM_BIND_EXTERNAL_POLICY(fx_regime);
    MACRO_SIM_BIND_EXTERNAL_POLICY(peg_reserve_scale);
#undef MACRO_SIM_BIND_EXTERNAL_POLICY
    external_policy
        .def_prop_rw(
            "sanctions_imposed_on",
            [](const macro_sim::simulation::ExternalPolicyState &value) {
                std::vector<std::uint64_t> output;
                output.reserve(value.sanctions_imposed_on.size());
                for (const auto target : value.sanctions_imposed_on) {
                    output.push_back(target.value());
                }
                return output;
            },
            [](macro_sim::simulation::ExternalPolicyState &value,
               const std::vector<std::uint64_t> &targets) {
                value.sanctions_imposed_on.clear();
                value.sanctions_imposed_on.reserve(targets.size());
                for (const auto target : targets) {
                    value.sanctions_imposed_on.emplace_back(target);
                }
            })
        .def_prop_rw(
            "peg_anchor",
            [](const macro_sim::simulation::ExternalPolicyState &value) -> nb::object {
                if (!value.peg_anchor.has_value()) {
                    return nb::none();
                }
                return nb::int_(value.peg_anchor->value());
            },
            [](macro_sim::simulation::ExternalPolicyState &value, nb::handle anchor) {
                value.peg_anchor =
                    anchor.is_none()
                        ? std::nullopt
                        : std::optional<macro_sim::EconomyId>(
                              macro_sim::EconomyId(nb::cast<std::uint64_t>(anchor)));
            },
            nb::for_setter(nb::arg("value").none()));
    auto shock_spec =
        nb::class_<macro_sim::simulation::ShockSpec>(module, "ShockSpec")
            .def(nb::init<>())
            .def_rw("id", &macro_sim::simulation::ShockSpec::id)
            .def_rw("kind", &macro_sim::simulation::ShockSpec::kind)
            .def_prop_rw(
                "economy_id",
                [](const macro_sim::simulation::ShockSpec &value) -> nb::object {
                    if (!value.economy.has_value()) {
                        return nb::none();
                    }
                    return nb::int_(value.economy->value());
                },
                [](macro_sim::simulation::ShockSpec &value, nb::handle economy) {
                    value.economy =
                        economy.is_none()
                            ? std::nullopt
                            : std::optional<macro_sim::EconomyId>(macro_sim::EconomyId(
                                  nb::cast<std::uint64_t>(economy)));
                },
                nb::for_setter(nb::arg("value").none()))
            .def_prop_rw(
                "start_tick",
                [](const macro_sim::simulation::ShockSpec &value) {
                    return value.start.value();
                },
                [](macro_sim::simulation::ShockSpec &value, std::uint64_t tick) {
                    value.start = macro_sim::Tick(tick);
                })
            .def_prop_rw(
                "announcement_tick",
                [](const macro_sim::simulation::ShockSpec &value) -> nb::object {
                    if (!value.announcement.has_value()) {
                        return nb::none();
                    }
                    return nb::int_(value.announcement->value());
                },
                [](macro_sim::simulation::ShockSpec &value, nb::handle tick) {
                    value.announcement =
                        tick.is_none() ? std::nullopt
                                       : std::optional<macro_sim::Tick>(macro_sim::Tick(
                                             nb::cast<std::uint64_t>(tick)));
                },
                nb::for_setter(nb::arg("value").none()))
            .def_rw("duration", &macro_sim::simulation::ShockSpec::duration)
            .def_rw("magnitude", &macro_sim::simulation::ShockSpec::magnitude)
            .def_rw("shape", &macro_sim::simulation::ShockSpec::shape)
            .def_rw("ramp_in_ticks", &macro_sim::simulation::ShockSpec::ramp_in_ticks)
            .def_rw("ramp_out_ticks", &macro_sim::simulation::ShockSpec::ramp_out_ticks)
            .def_prop_rw(
                "sector",
                [](const macro_sim::simulation::ShockSpec &value) -> nb::object {
                    if (!value.sector.has_value()) {
                        return nb::none();
                    }
                    return nb::cast(*value.sector);
                },
                [](macro_sim::simulation::ShockSpec &value, nb::handle sector) {
                    value.sector =
                        sector.is_none()
                            ? std::nullopt
                            : std::optional<macro_sim::simulation::ShockSector>(
                                  nb::cast<macro_sim::simulation::ShockSector>(sector));
                },
                nb::for_setter(nb::arg("value").none()));
    static_cast<void>(shock_spec);
    nb::class_<macro_sim::simulation::CrisisScenarioOptions>(module,
                                                             "CrisisScenarioOptions")
        .def(nb::init<>())
        .def_prop_rw(
            "start_tick",
            [](const macro_sim::simulation::CrisisScenarioOptions &value) {
                return value.start.value();
            },
            [](macro_sim::simulation::CrisisScenarioOptions &value,
               std::uint64_t tick) { value.start = macro_sim::Tick(tick); })
        .def_rw("duration", &macro_sim::simulation::CrisisScenarioOptions::duration)
        .def_rw("announcement_lead_ticks",
                &macro_sim::simulation::CrisisScenarioOptions::announcement_lead_ticks)
        .def_rw("first_shock_id",
                &macro_sim::simulation::CrisisScenarioOptions::first_shock_id)
        .def_prop_rw(
            "economies",
            [](const macro_sim::simulation::CrisisScenarioOptions &value) {
                std::vector<std::uint64_t> output;
                output.reserve(value.economies.size());
                for (const auto economy : value.economies) {
                    output.push_back(economy.value());
                }
                return output;
            },
            [](macro_sim::simulation::CrisisScenarioOptions &value,
               const std::vector<std::uint64_t> &economies) {
                value.economies.clear();
                value.economies.reserve(economies.size());
                for (const auto economy : economies) {
                    value.economies.emplace_back(economy);
                }
            })
        .def_rw("include_trade",
                &macro_sim::simulation::CrisisScenarioOptions::include_trade)
        .def_rw("capital_loss",
                &macro_sim::simulation::CrisisScenarioOptions::capital_loss);
    module.def("make_crisis_scenario",
               [](macro_sim::simulation::CrisisScenario scenario,
                  const macro_sim::simulation::CrisisScenarioOptions &options,
                  std::size_t economy_count) {
                   auto result = macro_sim::simulation::make_crisis_scenario(
                       scenario, options, economy_count);
                   require_status(result.status());
                   return std::move(*result.get_if());
               });
    nb::class_<macro_sim::simulation::M9WorldSpec>(module, "M9WorldSpec")
        .def(nb::init<>())
        .def_rw("economies", &macro_sim::simulation::M9WorldSpec::economies)
        .def_rw("external_policies",
                &macro_sim::simulation::M9WorldSpec::external_policies)
        .def_rw("rules", &macro_sim::simulation::M9WorldSpec::rules)
        .def_rw("shocks", &macro_sim::simulation::M9WorldSpec::shocks);
    nb::class_<macro_sim::simulation::DomesticPolicyState>(module, "DomesticPolicy")
        .def(nb::init<>())
        .def_rw("fiscal_monetary",
                &macro_sim::simulation::DomesticPolicyState::fiscal_monetary)
        .def_rw("financial", &macro_sim::simulation::DomesticPolicyState::financial)
        .def_rw("population", &macro_sim::simulation::DomesticPolicyState::population)
        .def_rw("energy", &macro_sim::simulation::DomesticPolicyState::energy)
        .def_rw("housing", &macro_sim::simulation::DomesticPolicyState::housing);
    nb::class_<macro_sim::simulation::WorldPolicyBatch>(module, "WorldPolicyBatch")
        .def(nb::init<>())
        .def_prop_rw(
            "expected_tick",
            [](const macro_sim::simulation::WorldPolicyBatch &value) {
                return value.expected_tick.value();
            },
            [](macro_sim::simulation::WorldPolicyBatch &value, std::uint64_t tick) {
                value.expected_tick = macro_sim::Tick(tick);
            })
        .def_rw("expected_generation",
                &macro_sim::simulation::WorldPolicyBatch::expected_generation)
        .def_rw("domestic", &macro_sim::simulation::WorldPolicyBatch::domestic)
        .def_rw("external", &macro_sim::simulation::WorldPolicyBatch::external);
    nb::class_<macro_sim::simulation::M9World>(module, "WorldSession")
        .def_static(
            "create",
            [](const macro_sim::simulation::M9WorldSpec &spec) {
                auto result = macro_sim::simulation::M9World::create(spec);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("spec"))
        .def_prop_ro("tick",
                     [](const macro_sim::simulation::M9World &world) {
                         return world.tick().value();
                     })
        .def_prop_ro("economy_count", &macro_sim::simulation::M9World::economy_count)
        .def_prop_ro("policy_generation",
                     &macro_sim::simulation::M9World::policy_generation)
        .def(
            "domestic_policy",
            [](const macro_sim::simulation::M9World &world, std::uint64_t economy) {
                auto result = world.domestic_policy(macro_sim::EconomyId(economy));
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("economy_id"))
        .def("external_policies",
             [](const macro_sim::simulation::M9World &world) {
                 return world.external_policies();
             })
        .def(
            "update_policy_batch",
            [](macro_sim::simulation::M9World &world,
               const macro_sim::simulation::WorldPolicyBatch &batch) {
                require_status(world.update_policy_batch(batch));
            },
            nb::arg("batch"))
        .def(
            "update_external_policies",
            [](macro_sim::simulation::M9World &world,
               const std::vector<macro_sim::simulation::ExternalPolicyState>
                   &policies) {
                require_status(world.update_external_policies(policies));
            },
            nb::arg("policies"))
        .def(
            "schedule_shock",
            [](macro_sim::simulation::M9World &world,
               const macro_sim::simulation::ShockSpec &shock) {
                require_status(world.schedule_shock(shock));
            },
            nb::arg("shock"))
        .def(
            "advance",
            [](macro_sim::simulation::M9World &world, std::uint64_t count,
               std::uint32_t worker_count) {
                macro_sim::simulation::M9AdvanceOptions options;
                options.worker_count = worker_count;
                auto result = [&world, count, &options]() {
                    nb::gil_scoped_release release;
                    return world.advance(count, options);
                }();
                require_status(result.status());
                return m9_result_to_python(*result.get_if());
            },
            nb::arg("count"), nb::arg("worker_count") = 1U)
        .def("snapshot",
             [](const macro_sim::simulation::M9World &world) {
                 return m9_snapshot_to_python(world);
             })
        .def("memory_usage",
             [](const macro_sim::simulation::M9World &world) {
                 return m9_memory_usage_to_python(world.memory_usage());
             })
        .def("storage_counts", &m9_storage_counts_to_python)
        .def("shock_events",
             [](const macro_sim::simulation::M9World &world) {
                 nb::list output;
                 for (const auto &event : world.shock_events()) {
                     nb::dict row;
                     row["sequence"] = event.sequence;
                     row["type"] = event.type;
                     row["tick"] = event.tick.value();
                     row["shock_id"] = event.shock_id;
                     row["intensity"] = event.intensity;
                     output.append(std::move(row));
                 }
                 return output;
             })
        .def("digest", &macro_sim::simulation::M9World::digest)
        .def("checkpoint",
             [](const macro_sim::simulation::M9World &world) {
                 const auto result = world.checkpoint();
                 require_status(result.status());
                 const auto &bytes = *result.get_if();
                 return nb::bytes(bytes.data(), bytes.size());
             })
        .def(
            "economy_checkpoint",
            [](const macro_sim::simulation::M9World &world, std::uint64_t economy) {
                const auto result =
                    world.economy_checkpoint(macro_sim::EconomyId(economy));
                require_status(result.status());
                const auto &bytes = *result.get_if();
                return nb::bytes(bytes.data(), bytes.size());
            },
            nb::arg("economy_id"))
        .def(
            "restore_checkpoint",
            [](macro_sim::simulation::M9World &world, const nb::bytes &encoded) {
                auto result = macro_sim::simulation::M9World::restore(
                    std::span<const std::uint8_t>(
                        static_cast<const std::uint8_t *>(encoded.data()),
                        encoded.size()));
                require_status(result.status());
                world = std::move(*result.get_if());
            },
            nb::arg("checkpoint"));
    module.def(
        "native_spec_from_new_game",
        [](std::string_view document) {
            auto game = macro_sim::desktop::parse_m11_native_new_game(document);
            require_status(game.status());
            return std::move(game.get_if()->world);
        },
        nb::arg("document"));
    module.def(
        "native_world_from_new_game",
        [](std::string_view document) {
            auto game = macro_sim::desktop::parse_m11_native_new_game(document);
            require_status(game.status());
            auto world = macro_sim::simulation::M9World::create(game.get_if()->world);
            require_status(world.status());
            if (!game.get_if()->initial_policy_actions.empty()) {
                auto batch = macro_sim::control::project_m11_policy_actions(
                    *world.get_if(), game.get_if()->initial_policy_actions);
                require_status(batch.status());
                require_status(world.get_if()->update_policy_batch(*batch.get_if()));
            }
            return std::move(*world.get_if());
        },
        nb::arg("document"));

    nb::class_<macro_sim::control::CanonicalControllerEnvelope>(
        module, "CanonicalControllerEnvelope")
        .def(nb::init<>())
        .def_rw("schema_version",
                &macro_sim::control::CanonicalControllerEnvelope::schema_version)
        .def_prop_rw(
            "boundary",
            [](const macro_sim::control::CanonicalControllerEnvelope &value) {
                return value.boundary.value();
            },
            [](macro_sim::control::CanonicalControllerEnvelope &value,
               std::uint64_t boundary) { value.boundary = macro_sim::Tick(boundary); })
        .def_rw("policy_generation",
                &macro_sim::control::CanonicalControllerEnvelope::policy_generation)
        .def_rw("event_sequence",
                &macro_sim::control::CanonicalControllerEnvelope::event_sequence)
        .def_rw("release_cursor",
                &macro_sim::control::CanonicalControllerEnvelope::release_cursor)
        .def_rw("decision_versions",
                &macro_sim::control::CanonicalControllerEnvelope::decision_versions)
        .def_rw("effective_versions",
                &macro_sim::control::CanonicalControllerEnvelope::effective_versions)
        .def_prop_rw(
            "canonical_payload",
            [](const macro_sim::control::CanonicalControllerEnvelope &value) {
                return nb::bytes(value.canonical_payload.data(),
                                 value.canonical_payload.size());
            },
            [](macro_sim::control::CanonicalControllerEnvelope &value,
               const nb::bytes &payload) {
                const auto *begin = static_cast<const std::uint8_t *>(payload.data());
                value.canonical_payload.assign(begin, begin + payload.size());
            })
        .def_prop_ro("hash",
                     [](const macro_sim::control::CanonicalControllerEnvelope &value) {
                         return value.hash.hex();
                     })
        .def("seal", [](macro_sim::control::CanonicalControllerEnvelope &value) {
            require_status(macro_sim::control::seal_controller_envelope(value));
            return value.hash.hex();
        });
    nb::class_<macro_sim::control::ControllerEnvelopeTransition>(
        module, "ControllerEnvelopeTransition")
        .def(nb::init<>())
        .def_rw("operation_id",
                &macro_sim::control::ControllerEnvelopeTransition::operation_id)
        .def_prop_rw(
            "expected_prior_hash",
            [](const macro_sim::control::ControllerEnvelopeTransition &value) {
                return value.expected_prior_hash.hex();
            },
            [](macro_sim::control::ControllerEnvelopeTransition &value,
               std::string_view digest) {
                value.expected_prior_hash = digest_from_hex(digest);
            })
        .def_rw("next", &macro_sim::control::ControllerEnvelopeTransition::next);
    nb::enum_<macro_sim::control::M10FaultPoint>(module, "M10FaultPoint")
        .value("NONE", macro_sim::control::M10FaultPoint::none)
        .value("PREPARE_AFTER_POLICY",
               macro_sim::control::M10FaultPoint::prepare_after_policy)
        .value("PREPARE_AFTER_ADVANCE",
               macro_sim::control::M10FaultPoint::prepare_after_advance)
        .value("PREPARE_AFTER_METRICS",
               macro_sim::control::M10FaultPoint::prepare_after_metrics)
        .value("COMMIT_BEFORE_SWAP",
               macro_sim::control::M10FaultPoint::commit_before_swap);
    nb::class_<macro_sim::control::SealedControlBatch>(module, "SealedControlBatch")
        .def(nb::init<>())
        .def_rw("operation_id", &macro_sim::control::SealedControlBatch::operation_id)
        .def_prop_rw(
            "expected_controller_hash",
            [](const macro_sim::control::SealedControlBatch &value) {
                return value.expected_controller_hash.hex();
            },
            [](macro_sim::control::SealedControlBatch &value, std::string_view digest) {
                value.expected_controller_hash = digest_from_hex(digest);
            })
        .def_rw("policies", &macro_sim::control::SealedControlBatch::policies)
        .def_rw("advance_ticks", &macro_sim::control::SealedControlBatch::advance_ticks)
        .def_rw("fault_point", &macro_sim::control::SealedControlBatch::fault_point)
        .def_prop_rw(
            "worker_count",
            [](const macro_sim::control::SealedControlBatch &value) {
                return value.advance_options.worker_count;
            },
            [](macro_sim::control::SealedControlBatch &value, std::uint32_t workers) {
                value.advance_options.worker_count = workers;
            });
    nb::class_<macro_sim::control::NativePolicyArtifact>(module, "NativePolicyArtifact")
        .def_static(
            "load_file",
            [](const std::string &path) {
                auto result = macro_sim::control::NativePolicyArtifact::load_file(path);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("path"))
        .def_prop_ro("info",
                     [](const macro_sim::control::NativePolicyArtifact &artifact) {
                         const auto &info = artifact.info();
                         nb::dict output;
                         output["inference_capability"] = info.inference_capability;
                         output["artifact_sha256"] = info.artifact_sha256;
                         output["context_contract_hash"] = info.context_contract_hash;
                         output["action_contract_hash"] = info.action_contract_hash;
                         output["model_contract_hash"] = info.model_contract_hash;
                         output["metadata_json"] = info.metadata_json;
                         output["observation_dimension"] = info.observation_dimension;
                         output["action_dimension"] = info.action_dimension;
                         output["layer_count"] = info.layer_count;
                         output["float32"] = info.float32;
                         output["deterministic"] = info.deterministic;
                         output["temperature"] = info.temperature;
                         return output;
                     })
        .def_prop_ro("feature_names",
                     [](const macro_sim::control::NativePolicyArtifact &artifact) {
                         return artifact.feature_names();
                     })
        .def(
            "logits",
            [](const macro_sim::control::NativePolicyArtifact &artifact,
               const std::vector<double> &observation) {
                auto result = artifact.logits(observation);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("observation"))
        .def(
            "normalized_input",
            [](const macro_sim::control::NativePolicyArtifact &artifact,
               const std::vector<double> &observation) {
                auto result = artifact.normalized_input(observation);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("observation"))
        .def(
            "probabilities",
            [](const macro_sim::control::NativePolicyArtifact &artifact,
               const std::vector<double> &observation,
               const std::vector<std::uint8_t> &action_mask) {
                auto result = artifact.probabilities(observation, action_mask);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("observation"), nb::arg("action_mask"))
        .def(
            "predict_codes",
            [](const macro_sim::control::NativePolicyArtifact &artifact,
               const std::vector<double> &observation,
               const std::vector<std::uint8_t> &action_mask) {
                auto result = artifact.predict_codes(observation, action_mask);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("observation"), nb::arg("action_mask"));

    nb::class_<macro_sim::control::EngineSession>(module, "NativeWorldEngineSession")
        .def_static(
            "create",
            [](macro_sim::simulation::M9World world,
               std::size_t history_capacity_frames) {
                auto result = macro_sim::control::EngineSession::create(
                    std::move(world), history_capacity_frames);
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("world"), nb::arg("history_capacity_frames") = 4096U)
        .def_prop_ro("tick",
                     [](const macro_sim::control::EngineSession &value) {
                         return value.tick().value();
                     })
        .def_prop_ro("policy_generation",
                     &macro_sim::control::EngineSession::policy_generation)
        .def(
            "advance_ticks",
            [](macro_sim::control::EngineSession &value, std::uint64_t count,
               std::uint32_t worker_count) {
                macro_sim::simulation::M9AdvanceOptions options;
                options.worker_count = worker_count;
                auto result = [&]() {
                    nb::gil_scoped_release release;
                    return value.advance_ticks(count, options);
                }();
                require_status(result.status());
                return m9_result_to_python(*result.get_if());
            },
            nb::arg("count"), nb::arg("worker_count") = 1U)
        .def("public_metrics",
             [](const macro_sim::control::EngineSession &value) {
                 return m10_metric_frame_to_python(value.metrics().current());
             })
        .def("maintained_metrics",
             [](const macro_sim::control::EngineSession &value) {
                 return m10_maintained_metric_frame_to_python(
                     value.metrics().current());
             })
        .def(
            "history_page",
            [](const macro_sim::control::EngineSession &value,
               std::uint64_t first_sequence, std::size_t maximum_frames) {
                auto result =
                    value.metrics().history().page(first_sequence, maximum_frames);
                require_status(result.status());
                nb::dict output;
                output["first_sequence"] = result.get_if()->first_sequence;
                output["next_sequence"] = result.get_if()->next_sequence;
                nb::list frames;
                for (const auto &frame : result.get_if()->frames) {
                    frames.append(m10_metric_frame_to_python(frame));
                }
                output["frames"] = std::move(frames);
                return output;
            },
            nb::arg("first_sequence"), nb::arg("maximum_frames") = 256U)
        .def(
            "maintained_history_page",
            [](const macro_sim::control::EngineSession &value,
               std::uint64_t first_sequence, std::size_t maximum_frames) {
                auto result =
                    value.metrics().history().page(first_sequence, maximum_frames);
                require_status(result.status());
                nb::dict output;
                output["first_sequence"] = result.get_if()->first_sequence;
                output["next_sequence"] = result.get_if()->next_sequence;
                nb::list frames;
                for (const auto &frame : result.get_if()->frames) {
                    frames.append(m10_maintained_metric_frame_to_python(frame));
                }
                output["frames"] = std::move(frames);
                return output;
            },
            nb::arg("first_sequence"), nb::arg("maximum_frames") = 256U)
        .def("history_bounds",
             [](const macro_sim::control::EngineSession &value) {
                 nb::dict output;
                 const auto &history = value.metrics().history();
                 output["oldest_sequence"] = history.oldest_sequence();
                 output["next_sequence"] = history.next_sequence();
                 output["capacity"] = history.capacity();
                 output["size"] = history.size();
                 output["retained_bytes"] = history.retained_bytes();
                 return output;
             })
        .def("memory_usage",
             [](const macro_sim::control::EngineSession &value) {
                 return m9_memory_usage_to_python(value.world().memory_usage());
             })
        .def("storage_counts",
             [](const macro_sim::control::EngineSession &value) {
                 return m9_storage_counts_to_python(value.world());
             })
        .def("clone",
             [](const macro_sim::control::EngineSession &value) {
                 auto result = value.clone();
                 require_status(result.status());
                 return std::move(*result.get_if());
             })
        .def(
            "probe_households",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_households(macro_sim::EconomyId(economy),
                                                     after_id, maximum_rows);
                require_status(result.status());
                return household_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_firms",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_firms(macro_sim::EconomyId(economy), after_id,
                                                maximum_rows);
                require_status(result.status());
                return firm_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_banks",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_banks(macro_sim::EconomyId(economy), after_id,
                                                maximum_rows);
                require_status(result.status());
                return bank_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_persons",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_persons(macro_sim::EconomyId(economy),
                                                  after_id, maximum_rows);
                require_status(result.status());
                return person_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_jobs",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_jobs(macro_sim::EconomyId(economy), after_id,
                                               maximum_rows);
                require_status(result.status());
                return job_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_dwellings",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_dwellings(macro_sim::EconomyId(economy),
                                                    after_id, maximum_rows);
                require_status(result.status());
                return dwelling_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_equities",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_equities(macro_sim::EconomyId(economy),
                                                   after_id, maximum_rows);
                require_status(result.status());
                return equity_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_security_positions",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t after_id, std::size_t maximum_rows) {
                auto result = value.probe_security_positions(
                    macro_sim::EconomyId(economy), after_id, maximum_rows);
                require_status(result.status());
                return security_position_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_economy_diagnostics",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy) {
                auto result =
                    value.probe_economy_diagnostics(macro_sim::EconomyId(economy));
                require_status(result.status());
                return diagnostic_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"))
        .def(
            "probe_shock_bulletins",
            [](const macro_sim::control::EngineSession &value, std::uint64_t economy,
               std::uint64_t as_of_boundary) {
                auto result = value.probe_shock_bulletins(
                    macro_sim::EconomyId(economy), macro_sim::Tick(as_of_boundary));
                require_status(result.status());
                return shock_bulletins_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("as_of_boundary"));
    nb::class_<macro_sim::control::PreparedBoundaryLease>(module,
                                                          "PreparedBoundaryLease")
        .def_prop_ro("active", &macro_sim::control::PreparedBoundaryLease::active)
        .def_prop_ro("preview",
                     [](const macro_sim::control::PreparedBoundaryLease &value) {
                         const auto &preview = value.preview();
                         nb::dict output;
                         output["operation_id"] = preview.operation_id;
                         output["first_tick"] = preview.first_tick.value();
                         output["next_tick"] = preview.next_tick.value();
                         output["policy_generation"] = preview.policy_generation;
                         output["engine_digest"] = preview.engine_digest;
                         output["public_metrics"] =
                             m10_metric_frame_to_python(preview.public_metrics);
                         return output;
                     });
    nb::class_<macro_sim::control::HybridControlledBridge>(module,
                                                           "HybridControlledBridge")
        .def_static(
            "create",
            [](macro_sim::control::EngineSession engine,
               macro_sim::control::CanonicalControllerEnvelope envelope) {
                auto result = macro_sim::control::HybridControlledBridge::create(
                    std::move(engine), std::move(envelope));
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("engine"), nb::arg("envelope"))
        .def_prop_ro("tick",
                     [](const macro_sim::control::HybridControlledBridge &value) {
                         require_status(value.query_status());
                         return value.engine().tick().value();
                     })
        .def_prop_ro("policy_generation",
                     [](const macro_sim::control::HybridControlledBridge &value) {
                         require_status(value.query_status());
                         return value.engine().policy_generation();
                     })
        .def_prop_ro("economy_count",
                     [](const macro_sim::control::HybridControlledBridge &value) {
                         require_status(value.query_status());
                         return value.engine().world().economy_count();
                     })
        .def(
            "domestic_policy",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy) {
                require_status(value.query_status());
                auto result = value.engine().world().domestic_policy(
                    macro_sim::EconomyId(economy));
                require_status(result.status());
                return *result.get_if();
            },
            nb::arg("economy_id"))
        .def("external_policies",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return value.engine().world().external_policies();
             })
        .def("native_snapshot",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return m9_snapshot_to_python(value.engine().world());
             })
        .def_prop_ro("controller_envelope",
                     [](const macro_sim::control::HybridControlledBridge &value) {
                         require_status(value.query_status());
                         return value.controller_envelope();
                     })
        .def(
            "update_controller",
            [](macro_sim::control::HybridControlledBridge &value,
               const macro_sim::control::ControllerEnvelopeTransition &transition) {
                auto result = value.update_controller(transition);
                require_status(result.status());
                nb::dict output;
                output["operation_id"] = result.get_if()->operation_id;
                output["request_hash"] = result.get_if()->request_hash.hex();
                output["prior_hash"] = result.get_if()->prior_hash.hex();
                output["result_hash"] = result.get_if()->result_hash.hex();
                output["boundary"] = result.get_if()->boundary.value();
                output["acknowledged"] = result.get_if()->acknowledged;
                return output;
            },
            nb::arg("transition"))
        .def(
            "acknowledge_receipt",
            [](macro_sim::control::HybridControlledBridge &value,
               const std::string &operation_id) {
                require_status(value.acknowledge_receipt(operation_id));
            },
            nb::arg("operation_id"))
        .def(
            "validate_policy_batch",
            [](const macro_sim::control::HybridControlledBridge &value,
               const macro_sim::simulation::WorldPolicyBatch &batch) {
                require_status(value.validate_policy_batch(batch));
            },
            nb::arg("batch"))
        .def(
            "prepare_boundary",
            [](macro_sim::control::HybridControlledBridge &value,
               const macro_sim::control::SealedControlBatch &batch) {
                auto result = [&]() {
                    nb::gil_scoped_release release;
                    return value.prepare_boundary(batch);
                }();
                require_status(result.status());
                return std::move(*result.get_if());
            },
            nb::arg("batch"))
        .def(
            "commit_boundary",
            [](macro_sim::control::HybridControlledBridge &value,
               macro_sim::control::PreparedBoundaryLease &lease,
               macro_sim::control::CanonicalControllerEnvelope next) {
                auto result = value.commit_boundary(std::move(lease), std::move(next));
                require_status(result.status());
                return m9_result_to_python(*result.get_if());
            },
            nb::arg("lease"), nb::arg("next"))
        .def(
            "abort_boundary",
            [](macro_sim::control::HybridControlledBridge &value,
               macro_sim::control::PreparedBoundaryLease &lease) {
                require_status(value.abort_boundary(std::move(lease)));
            },
            nb::arg("lease"))
        .def("public_metrics",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return m10_metric_frame_to_python(value.engine().metrics().current());
             })
        .def("maintained_metrics",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return m10_maintained_metric_frame_to_python(
                     value.engine().metrics().current());
             })
        .def(
            "history_page",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t first_sequence, std::size_t maximum_frames) {
                require_status(value.query_status());
                auto result = value.engine().metrics().history().page(first_sequence,
                                                                      maximum_frames);
                require_status(result.status());
                nb::dict output;
                output["first_sequence"] = result.get_if()->first_sequence;
                output["next_sequence"] = result.get_if()->next_sequence;
                nb::list frames;
                for (const auto &frame : result.get_if()->frames) {
                    frames.append(m10_metric_frame_to_python(frame));
                }
                output["frames"] = std::move(frames);
                return output;
            },
            nb::arg("first_sequence"), nb::arg("maximum_frames") = 256U)
        .def(
            "maintained_history_page",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t first_sequence, std::size_t maximum_frames) {
                require_status(value.query_status());
                auto result = value.engine().metrics().history().page(first_sequence,
                                                                      maximum_frames);
                require_status(result.status());
                nb::dict output;
                output["first_sequence"] = result.get_if()->first_sequence;
                output["next_sequence"] = result.get_if()->next_sequence;
                nb::list frames;
                for (const auto &frame : result.get_if()->frames) {
                    frames.append(m10_maintained_metric_frame_to_python(frame));
                }
                output["frames"] = std::move(frames);
                return output;
            },
            nb::arg("first_sequence"), nb::arg("maximum_frames") = 256U)
        .def("history_bounds",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 nb::dict output;
                 const auto &history = value.engine().metrics().history();
                 output["oldest_sequence"] = history.oldest_sequence();
                 output["next_sequence"] = history.next_sequence();
                 output["capacity"] = history.capacity();
                 output["size"] = history.size();
                 output["retained_bytes"] = history.retained_bytes();
                 return output;
             })
        .def("memory_usage",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return m9_memory_usage_to_python(
                     value.engine().world().memory_usage());
             })
        .def("storage_counts",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 require_status(value.query_status());
                 return m9_storage_counts_to_python(value.engine().world());
             })
        .def("clone",
             [](const macro_sim::control::HybridControlledBridge &value) {
                 auto result = value.clone();
                 require_status(result.status());
                 return std::move(*result.get_if());
             })
        .def(
            "probe_households",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_households(macro_sim::EconomyId(economy),
                                                     after_id, maximum_rows);
                require_status(result.status());
                return household_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_firms",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_firms(macro_sim::EconomyId(economy), after_id,
                                                maximum_rows);
                require_status(result.status());
                return firm_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_banks",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_banks(macro_sim::EconomyId(economy), after_id,
                                                maximum_rows);
                require_status(result.status());
                return bank_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_persons",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_persons(macro_sim::EconomyId(economy),
                                                  after_id, maximum_rows);
                require_status(result.status());
                return person_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_jobs",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_jobs(macro_sim::EconomyId(economy), after_id,
                                               maximum_rows);
                require_status(result.status());
                return job_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_dwellings",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_dwellings(macro_sim::EconomyId(economy),
                                                    after_id, maximum_rows);
                require_status(result.status());
                return dwelling_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_equities",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_equities(macro_sim::EconomyId(economy),
                                                   after_id, maximum_rows);
                require_status(result.status());
                return equity_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_security_positions",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t after_id,
               std::size_t maximum_rows) {
                auto result = value.probe_security_positions(
                    macro_sim::EconomyId(economy), after_id, maximum_rows);
                require_status(result.status());
                return security_position_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("after_id") = 0U,
            nb::arg("maximum_rows") = 256U)
        .def(
            "probe_economy_diagnostics",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy) {
                auto result =
                    value.probe_economy_diagnostics(macro_sim::EconomyId(economy));
                require_status(result.status());
                return diagnostic_probe_to_python(*result.get_if());
            },
            nb::arg("economy_id"))
        .def(
            "probe_shock_bulletins",
            [](const macro_sim::control::HybridControlledBridge &value,
               std::uint64_t economy, std::uint64_t as_of_boundary) {
                auto result = value.probe_shock_bulletins(
                    macro_sim::EconomyId(economy), macro_sim::Tick(as_of_boundary));
                require_status(result.status());
                return shock_bulletins_to_python(*result.get_if());
            },
            nb::arg("economy_id"), nb::arg("as_of_boundary"))
        .def(
            "checkpoint",
            [](const macro_sim::control::HybridControlledBridge &value,
               const nb::bytes &objective) {
                const auto *data = static_cast<const std::uint8_t *>(objective.data());
                auto result = macro_sim::control::save_hybrid_checkpoint(
                    value, std::span<const std::uint8_t>(data, objective.size()));
                require_status(result.status());
                return nb::bytes(result.get_if()->data(), result.get_if()->size());
            },
            nb::arg("objective_envelope"))
        .def(
            "checkpoint",
            [](const macro_sim::control::HybridControlledBridge &value,
               const nb::bytes &objective, const nb::bytes &controller_archive) {
                const auto *data = static_cast<const std::uint8_t *>(objective.data());
                const auto *archive_data =
                    static_cast<const std::uint8_t *>(controller_archive.data());
                auto result = macro_sim::control::save_hybrid_checkpoint(
                    value, std::span<const std::uint8_t>(data, objective.size()),
                    std::span<const std::uint8_t>(archive_data,
                                                  controller_archive.size()));
                require_status(result.status());
                return nb::bytes(result.get_if()->data(), result.get_if()->size());
            },
            nb::arg("objective_envelope"), nb::arg("controller_archive"))
        .def_static(
            "restore_checkpoint",
            [](const nb::bytes &checkpoint) {
                const auto *data = static_cast<const std::uint8_t *>(checkpoint.data());
                auto result = macro_sim::control::load_hybrid_checkpoint(
                    std::span<const std::uint8_t>(data, checkpoint.size()));
                require_status(result.status());
                nb::dict output;
                output["bridge"] = nb::cast(std::move(result.get_if()->bridge));
                output["objective_envelope"] =
                    nb::bytes(result.get_if()->objective_envelope.data(),
                              result.get_if()->objective_envelope.size());
                output["controller_archive"] =
                    nb::bytes(result.get_if()->controller_archive.data(),
                              result.get_if()->controller_archive.size());
                return output;
            },
            nb::arg("checkpoint"));
    nb::enum_<macro_sim::core::OwnerKind>(module, "OwnerKind")
        .value("HOUSEHOLD", macro_sim::core::OwnerKind::household)
        .value("FIRM", macro_sim::core::OwnerKind::firm)
        .value("BANK", macro_sim::core::OwnerKind::bank)
        .value("TREASURY", macro_sim::core::OwnerKind::treasury)
        .value("CENTRAL_BANK", macro_sim::core::OwnerKind::central_bank)
        .value("DEALER", macro_sim::core::OwnerKind::dealer)
        .value("ROUNDING_RESIDUAL", macro_sim::core::OwnerKind::rounding_residual)
        .value("INSTITUTION", macro_sim::core::OwnerKind::institution);
    nb::class_<macro_sim::core::GenesisSpec>(module, "GenesisSpec")
        .def(nb::init<>())
        .def_prop_rw(
            "vertical",
            [](const macro_sim::core::GenesisSpec &spec) { return spec.vertical; },
            [](macro_sim::core::GenesisSpec &spec,
               macro_sim::core::GenesisVertical value) { spec.vertical = value; })
        .def_prop_rw(
            "economy_id",
            [](const macro_sim::core::GenesisSpec &spec) {
                return spec.economy.value();
            },
            [](macro_sim::core::GenesisSpec &spec, std::uint64_t value) {
                spec.economy = macro_sim::EconomyId(value);
            })
        .def_prop_rw(
            "currency_id",
            [](const macro_sim::core::GenesisSpec &spec) {
                return spec.currency.value();
            },
            [](macro_sim::core::GenesisSpec &spec, std::uint32_t value) {
                spec.currency = macro_sim::CurrencyId(value);
            })
        .def_rw("households", &macro_sim::core::GenesisSpec::households)
        .def_rw("consumption_firms", &macro_sim::core::GenesisSpec::consumption_firms)
        .def_rw("capital_firms", &macro_sim::core::GenesisSpec::capital_firms)
        .def_rw("settlement_banks", &macro_sim::core::GenesisSpec::settlement_banks)
        .def_rw("government", &macro_sim::core::GenesisSpec::government)
        .def_prop_rw(
            "opening_money",
            [](const macro_sim::core::GenesisSpec &spec) {
                return spec.aggregate_opening_money.value();
            },
            [](macro_sim::core::GenesisSpec &spec, double value) {
                spec.aggregate_opening_money = macro_sim::Money(value);
            })
        .def_prop_rw(
            "opening_capital",
            [](const macro_sim::core::GenesisSpec &spec) {
                return spec.aggregate_opening_capital.value();
            },
            [](macro_sim::core::GenesisSpec &spec, double value) {
                spec.aggregate_opening_capital = macro_sim::Capital(value);
            })
        .def_rw("seed", &macro_sim::core::GenesisSpec::seed)
        .def(
            "add_counter_stream",
            [](macro_sim::core::GenesisSpec &spec, std::uint64_t stream) {
                spec.named_counter_streams.push_back(stream);
            },
            nb::arg("stream_id"));
    nb::class_<macro_sim::core::SettlementBatch>(module, "SettlementBatch")
        .def(nb::init<>())
        .def(
            "transfer",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t source,
               std::uint64_t destination, double amount) {
                batch.transfers.push_back({
                    macro_sim::AccountId(source),
                    macro_sim::AccountId(destination),
                    macro_sim::Money(amount),
                });
            },
            nb::arg("source_account"), nb::arg("destination_account"),
            nb::arg("amount"))
        .def(
            "move_reserves",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t source,
               std::uint64_t destination, double amount) {
                batch.reserve_transfers.push_back({
                    macro_sim::SettlementNodeId(source),
                    macro_sim::SettlementNodeId(destination),
                    macro_sim::Money(amount),
                });
            },
            nb::arg("source_node"), nb::arg("destination_node"), nb::arg("amount"))
        .def(
            "issue_reserves",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t destination,
               double amount) {
                batch.reserve_issues.push_back({
                    macro_sim::SettlementNodeId(destination),
                    macro_sim::Money(amount),
                });
            },
            nb::arg("destination_node"), nb::arg("amount"))
        .def(
            "originate_loan",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t lender,
               macro_sim::core::OwnerKind borrower_kind, std::uint64_t borrower,
               std::uint64_t borrower_account, double amount, double annual_rate,
               std::uint64_t originated_tick, std::uint64_t maturity_tick) {
                batch.originations.push_back({
                    macro_sim::BankId(lender),
                    macro_sim::core::OwnerId::institutional(borrower_kind, borrower),
                    macro_sim::AccountId(borrower_account),
                    macro_sim::Money(amount),
                    {
                        macro_sim::Rate(annual_rate),
                        macro_sim::Tick(originated_tick),
                        macro_sim::Tick(maturity_tick),
                    },
                });
            },
            nb::arg("lender_bank"), nb::arg("borrower_kind"), nb::arg("borrower_id"),
            nb::arg("borrower_account"), nb::arg("amount"), nb::arg("annual_rate"),
            nb::arg("originated_tick"), nb::arg("maturity_tick"))
        .def(
            "repay_loan",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t loan,
               std::uint64_t payer_account, double amount) {
                batch.repayments.push_back({
                    macro_sim::LoanId(loan),
                    macro_sim::AccountId(payer_account),
                    macro_sim::Money(amount),
                });
            },
            nb::arg("loan_id"), nb::arg("payer_account"), nb::arg("amount"))
        .def(
            "mutate_ownership",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t lot,
               macro_sim::core::OwnerKind owner_kind, std::uint64_t owner,
               double share) {
                batch.ownership_mutations.push_back({
                    macro_sim::OwnershipLotId(lot),
                    macro_sim::core::OwnerId::institutional(owner_kind, owner),
                    share,
                });
            },
            nb::arg("lot_id"), nb::arg("owner_kind"), nb::arg("owner_id"),
            nb::arg("share"))
        .def(
            "increment_counter",
            [](macro_sim::core::SettlementBatch &batch, std::uint64_t stream,
               std::uint64_t amount) {
                batch.counter_increments.push_back({stream, amount});
            },
            nb::arg("stream_id"), nb::arg("amount") = 1);
    nb::class_<macro_sim::EngineSession>(module, "EngineSession")
        .def(nb::init<std::uint64_t>(), nb::arg("session_id") = 1)
        .def_prop_ro("session_id",
                     [](const macro_sim::EngineSession &session) {
                         return session.id().value();
                     })
        .def_prop_ro("tick",
                     [](const macro_sim::EngineSession &session) {
                         return session.tick().value();
                     })
        .def_prop_ro("state", &macro_sim::EngineSession::state)
        .def_prop_ro("closed", &macro_sim::EngineSession::closed)
        .def_prop_ro("initialized", &macro_sim::EngineSession::initialized)
        .def(
            "initialize_m2",
            [](macro_sim::EngineSession &session,
               const macro_sim::core::GenesisSpec &spec) {
                require_status(session.initialize(spec));
            },
            nb::arg("spec"))
        .def(
            "initialize_simulation",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M4SimulationSpec &spec) {
                require_status(session.initialize_simulation(spec));
            },
            nb::arg("spec"))
        .def(
            "initialize_m5",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M5SimulationSpec &spec) {
                require_status(session.initialize_m5(spec));
            },
            nb::arg("spec"))
        .def(
            "initialize_m6",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M6SimulationSpec &spec) {
                require_status(session.initialize_m6(spec));
            },
            nb::arg("spec"))
        .def(
            "initialize_m7",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M7SimulationSpec &spec) {
                nb::gil_scoped_release release;
                require_status(session.initialize_m7(spec));
            },
            nb::arg("spec"))
        .def(
            "initialize_m8",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M8SimulationSpec &spec) {
                nb::gil_scoped_release release;
                require_status(session.initialize_m8(spec));
            },
            nb::arg("spec"))
        .def(
            "update_m5_policy",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M5PolicyState &policy) {
                require_status(session.update_m5_policy(policy));
            },
            nb::arg("policy"))
        .def(
            "update_m6_policy",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M6PolicyState &policy) {
                require_status(session.update_m6_policy(policy));
            },
            nb::arg("policy"))
        .def(
            "update_m7_policy",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M7PolicyState &policy) {
                require_status(session.update_m7_policy(policy));
            },
            nb::arg("policy"))
        .def(
            "update_m7_rules",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::M7Rules &rules) {
                require_status(session.update_m7_rules(rules));
            },
            nb::arg("rules"))
        .def(
            "update_m8_energy_policy",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::EnergyPolicyState &policy) {
                require_status(session.update_m8_energy_policy(policy));
            },
            nb::arg("policy"))
        .def(
            "update_m8_housing_policy",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::HousingPolicyState &policy) {
                require_status(session.update_m8_housing_policy(policy));
            },
            nb::arg("policy"))
        .def(
            "update_m8_energy_input",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::EnergyExogenousInput &input) {
                require_status(session.update_m8_energy_input(input));
            },
            nb::arg("input"))
        .def(
            "update_m8_housing_input",
            [](macro_sim::EngineSession &session,
               const macro_sim::simulation::HousingExogenousInput &input) {
                require_status(session.update_m8_housing_input(input));
            },
            nb::arg("input"))
        .def(
            "advance_ticks",
            [](macro_sim::EngineSession &session, std::uint64_t count,
               bool capture_phase_trace) {
                macro_sim::simulation::M4AdvanceOptions options;
                options.capture_phase_trace = capture_phase_trace;
                const auto result = session.advance_ticks(count, options);
                require_status(result.status());
                return m4_result_to_python(*result.get_if());
            },
            nb::arg("count"), nb::arg("capture_phase_trace") = false)
        .def(
            "advance_m5_ticks",
            [](macro_sim::EngineSession &session, std::uint64_t count) {
                const auto result = session.advance_m5_ticks(count);
                require_status(result.status());
                return m5_result_to_python(*result.get_if());
            },
            nb::arg("count"))
        .def(
            "advance_m6_ticks",
            [](macro_sim::EngineSession &session, std::uint64_t count) {
                auto result = [&session, count]() {
                    nb::gil_scoped_release release;
                    return session.advance_m6_ticks(count);
                }();
                require_status(result.status());
                return m6_result_to_python(*result.get_if());
            },
            nb::arg("count"))
        .def(
            "advance_m7_ticks",
            [](macro_sim::EngineSession &session, std::uint64_t count) {
                auto result = [&session, count]() {
                    nb::gil_scoped_release release;
                    return session.advance_m7_ticks(count);
                }();
                require_status(result.status());
                return m7_result_to_python(*result.get_if());
            },
            nb::arg("count"))
        .def(
            "advance_m8_ticks",
            [](macro_sim::EngineSession &session, std::uint64_t count) {
                auto result = [&session, count]() {
                    nb::gil_scoped_release release;
                    return session.advance_m8_ticks(count);
                }();
                require_status(result.status());
                return m8_result_to_python(*result.get_if());
            },
            nb::arg("count"))
        .def("simulation_snapshot",
             [](const macro_sim::EngineSession &session) {
                 return m4_snapshot_to_python(session);
             })
        .def("m5_snapshot",
             [](const macro_sim::EngineSession &session) {
                 return m5_snapshot_to_python(session);
             })
        .def("m6_snapshot",
             [](const macro_sim::EngineSession &session) {
                 return m6_snapshot_to_python(session);
             })
        .def("m7_snapshot",
             [](const macro_sim::EngineSession &session) {
                 return m7_snapshot_to_python(session);
             })
        .def("m8_snapshot",
             [](const macro_sim::EngineSession &session) {
                 return m8_snapshot_to_python(session);
             })
        .def(
            "apply_batch",
            [](macro_sim::EngineSession &session,
               const macro_sim::core::SettlementBatch &batch) {
                const auto result = session.apply(batch);
                require_status(result.status());
                return receipt_to_python(*result.get_if());
            },
            nb::arg("batch"))
        .def("digest",
             [](const macro_sim::EngineSession &session) {
                 const auto result = session.digest();
                 require_status(result.status());
                 return result.get_if()->hex();
             })
        .def("accounting_snapshot",
             [](const macro_sim::EngineSession &session) {
                 if (session.root() == nullptr || session.closed()) {
                     throw std::runtime_error(
                         "invalid_handle: session has no active canonical state");
                 }
                 return snapshot_to_python(*session.root());
             })
        .def("checkpoint",
             [](const macro_sim::EngineSession &session) {
                 const auto result = session.checkpoint();
                 require_status(result.status());
                 const auto &bytes = *result.get_if();
                 return nb::bytes(bytes.data(), bytes.size());
             })
        .def(
            "restore_checkpoint",
            [](macro_sim::EngineSession &session, const nb::bytes &encoded) {
                require_status(session.restore_checkpoint(std::span<const std::uint8_t>(
                    static_cast<const std::uint8_t *>(encoded.data()),
                    encoded.size())));
            },
            nb::arg("checkpoint"))
        .def("close", [](macro_sim::EngineSession &session) {
            const auto result = session.close();
            if (!result.ok()) {
                throw std::runtime_error(std::string(result.message()));
            }
        });
    module.attr("M6Session") = module.attr("EngineSession");
    module.attr("M7Session") = module.attr("EngineSession");
    module.attr("M8Session") = module.attr("EngineSession");
}
