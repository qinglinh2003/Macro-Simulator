#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/string_view.h>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/rng.hpp"
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
        item["owner_kind"] = static_cast<std::uint8_t>(account.key.owner.kind);
        item["owner_id"] = account.key.owner.value;
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
        item["borrower_kind"] = static_cast<std::uint8_t>(loan.borrower.kind);
        item["borrower_id"] = loan.borrower.value;
        item["borrower_account"] = loan.borrower_account.value();
        item["principal"] = loan.principal.value();
        item["active"] = loan.active;
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
    output["government_spending"] = metrics.government_spending;
    output["government_deficit"] = metrics.government_deficit;
    output["public_capital"] = metrics.public_capital;
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
    output["total_loan_principal"] = metrics.total_loan_principal;
    output["total_bank_capital"] = metrics.total_bank_capital;
    output["total_reserves"] = metrics.total_reserves;
    output["reserve_stock"] = metrics.reserve_stock;
    output["omo_flow"] = metrics.omo_flow;
    output["lolr_advances"] = metrics.lolr_advances;
    output["interbank_volume"] = metrics.interbank_volume;
    output["interbank_rate"] = metrics.interbank_rate;
    output["run_flight_volume"] = metrics.run_flight_volume;
    output["resolution_cost"] = metrics.resolution_cost;
    output["realized_credit_losses"] = metrics.realized_credit_losses;
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

nb::dict m7_metrics_to_python(
    const macro_sim::simulation::M7Metrics &metrics
) {
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
    MACRO_SIM_M7_METRIC(participation_rate);
    MACRO_SIM_M7_METRIC(estates_settled);
    MACRO_SIM_M7_METRIC(beneficial_lots_transferred);
    MACRO_SIM_M7_METRIC(inheritance_tax_share);
    MACRO_SIM_M7_METRIC(inheritance_tax_paid);
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
    MACRO_SIM_M7_METRIC(marriages);
    MACRO_SIM_M7_METRIC(divorces);
    MACRO_SIM_M7_METRIC(widowhoods);
    MACRO_SIM_M7_METRIC(leaving_home_events);
#undef MACRO_SIM_M7_METRIC
    return output;
}

nb::dict m7_result_to_python(
    const macro_sim::simulation::M7AdvanceResult &result
) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] =
        result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m7_metrics_to_python(result.metrics);
    return output;
}

nb::dict m6_snapshot_to_python(
    const macro_sim::EngineSession &session
);

nb::dict m7_snapshot_to_python(
    const macro_sim::EngineSession &session
) {
    const auto *runtime = session.population_runtime();
    if (runtime == nullptr) {
        throw std::runtime_error(
            "invalid_handle: session has no active M7 simulation"
        );
    }
    auto output = m6_snapshot_to_python(session);
    nb::list persons;
    for (std::size_t index = 1;
         index < runtime->persons.records().size(); ++index) {
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
    for (std::size_t index = 1;
         index < runtime->employment.records().size(); ++index) {
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
        item["end_kind"] =
            static_cast<std::uint8_t>(row.end_kind);
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
        item["destination_household_id"] =
            row.destination_household.value();
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
        item["destination_household_id"] =
            row.destination.value();
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
        item["issuer_kind"] = static_cast<std::uint8_t>(row.issuer.kind);
        item["issuer_id"] = row.issuer.value;
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
        item["owner_kind"] = static_cast<std::uint8_t>(row.issuer.kind);
        item["issuer_id"] = row.issuer.value;
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
    for (const auto &row : runtime->securities.lots()) {
        nb::dict item;
        item["id"] = row.id.value();
        item["security_kind"] = static_cast<std::uint8_t>(row.security.kind);
        item["security_id"] = row.security.value;
        item["holder_kind"] = static_cast<std::uint8_t>(row.holder.kind);
        item["holder_id"] = row.holder.value;
        item["units"] = row.units;
        item["cost_basis"] = row.cost_basis.value();
        item["active"] = row.active;
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
                &macro_sim::simulation::M4SimulationSpec::market_protocol);
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
    m5_policy.def_prop_rw(
        "manual_policy_rate",
        [](const macro_sim::simulation::M5PolicyState &policy) {
            if (!policy.manual_policy_rate.has_value()) {
                return nb::object(nb::none());
            }
            return nb::object(nb::float_(*policy.manual_policy_rate));
        },
        [](macro_sim::simulation::M5PolicyState &policy, const nb::object &value) {
            if (value.is_none()) {
                policy.manual_policy_rate.reset();
            } else {
                policy.manual_policy_rate = nb::cast<double>(value);
            }
        });
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
    MACRO_SIM_BIND_M6_RULE(consumption_strata);
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
    auto vital = nb::class_<macro_sim::algorithms::VitalRates>(
        module, "VitalRates"
    ).def(nb::init<>());
#define MACRO_SIM_BIND_VITAL(field) \
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
        nb::class_<macro_sim::core::MarriageRules>(
            module, "MarriageRules"
        )
            .def(nb::init<>());
#define MACRO_SIM_BIND_MARRIAGE(field) \
    marriage_rules.def_rw( \
        #field, &macro_sim::core::MarriageRules::field \
    )
    MACRO_SIM_BIND_MARRIAGE(minimum_age);
    MACRO_SIM_BIND_MARRIAGE(maximum_age);
    MACRO_SIM_BIND_MARRIAGE(maximum_age_gap);
    MACRO_SIM_BIND_MARRIAGE(preferred_age_gap);
    MACRO_SIM_BIND_MARRIAGE(age_gap_penalty);
    MACRO_SIM_BIND_MARRIAGE(assortativity);
    MACRO_SIM_BIND_MARRIAGE(forbid_same_household);
    MACRO_SIM_BIND_MARRIAGE(forbid_close_kin);
#undef MACRO_SIM_BIND_MARRIAGE
    nb::class_<macro_sim::simulation::M7PolicyState>(
        module, "M7Policy"
    )
        .def(nb::init<>())
        .def_rw(
            "inheritance_tax_rate",
            &macro_sim::simulation::M7PolicyState::
                inheritance_tax_rate
        );
    auto m7_rules = nb::class_<macro_sim::simulation::M7Rules>(
        module, "M7Rules"
    ).def(nb::init<>());
#define MACRO_SIM_BIND_M7_RULE(field) \
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
    nb::class_<macro_sim::simulation::M7PopulationSpec>(
        module, "M7PopulationSpec"
    )
        .def(nb::init<>())
        .def_rw(
            "initial_persons",
            &macro_sim::simulation::M7PopulationSpec::initial_persons
        )
        .def_rw(
            "start_calendar_day",
            &macro_sim::simulation::M7PopulationSpec::
                start_calendar_day
        )
        .def_rw(
            "target_household_size",
            &macro_sim::simulation::M7PopulationSpec::
                target_household_size
        );
    nb::class_<macro_sim::simulation::M7SimulationSpec>(
        module, "M7SimulationSpec"
    )
        .def(nb::init<>())
        .def_rw(
            "financial_economy",
            &macro_sim::simulation::M7SimulationSpec::
                financial_economy
        )
        .def_rw(
            "policy",
            &macro_sim::simulation::M7SimulationSpec::policy
        )
        .def_rw(
            "rules",
            &macro_sim::simulation::M7SimulationSpec::rules
        )
        .def_rw(
            "population",
            &macro_sim::simulation::M7SimulationSpec::population
        );
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
                    {borrower_kind, borrower},
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
                    {owner_kind, owner},
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
            [](macro_sim::EngineSession &session,
               std::uint64_t count) {
                auto result = [&session, count]() {
                    nb::gil_scoped_release release;
                    return session.advance_m7_ticks(count);
                }();
                require_status(result.status());
                return m7_result_to_python(*result.get_if());
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
}
