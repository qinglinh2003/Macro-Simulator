#include "macro_sim/simulation/m5_checkpoint.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m4_checkpoint.hpp"

namespace macro_sim::simulation {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '5', 'C', 'P', '0', '1',
};
constexpr std::size_t kDigestBytes = 32;
constexpr std::size_t kMaximumCheckpointBytes = 256U * 1024U * 1024U;

void append_u32(std::vector<std::uint8_t> &bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

[[nodiscard]] bool read_u32(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint32_t &value) noexcept {
    if (bytes.size() - position < 4) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 4; ++index) {
        value = static_cast<std::uint32_t>((value << 8U) | bytes[position++]);
    }
    return true;
}

[[nodiscard]] bool read_u64(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint64_t &value) noexcept {
    if (bytes.size() - position < 8) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 8; ++index) {
        value = (value << 8U) | bytes[position++];
    }
    return true;
}

[[nodiscard]] Status corrupt(const char *message) noexcept {
    return Status(ErrorCode::corrupt_input, message);
}

[[nodiscard]] Json encode_policy(const M5PolicyState &value) {
    return Json::array({
        value.government_consumption_share,
        value.government_deficit_target,
        value.deficit_unemployment_reference,
        value.deficit_unemployment_cap,
        value.government_investment_share,
        value.profit_tax_rate,
        value.income_tax_rate,
        value.income_allowance,
        value.consumption_tax_rate,
        value.necessity_consumption_tax_rate.has_value()
            ? Json(*value.necessity_consumption_tax_rate)
            : Json(nullptr),
        value.luxury_consumption_tax_rate.has_value()
            ? Json(*value.luxury_consumption_tax_rate)
            : Json(nullptr),
        value.wealth_tax_rate,
        value.wealth_allowance,
        value.unemployment_benefit_replacement,
        value.benefit_income_floor,
        value.minimum_wage,
        value.job_guarantee,
        value.job_guarantee_wage_ratio,
        value.job_guarantee_public_works_share,
        static_cast<std::uint8_t>(value.monetary_regime),
        value.inflation_target,
        value.taylor_inflation,
        value.taylor_unemployment,
        value.rate_inertia,
        value.manual_policy_rate.has_value() ? Json(*value.manual_policy_rate)
                                             : Json(nullptr),
        value.neutral_rate,
        value.natural_unemployment,
        value.maximum_policy_rate,
        value.inflation_sensor_lambda,
        value.core_inflation_sensor,
        value.fixed_basket_cpi,
        value.logarithmic_inflation,
        value.fiscal_uses_national_accounts_gdp,
        value.open_market_operations,
        value.reserve_target,
        value.reserve_gap_close,
        value.reserve_target_indexes_deposits,
        value.lender_of_last_resort,
        value.reserve_floor_fraction,
        value.firm_leverage_limit,
        value.firm_minimum_dscr,
        value.household_credit_limit,
        value.bank_capital_constraint,
        value.unified_bank_rwa,
        value.bank_leverage_cap,
        value.bank_exposure_limit,
        value.bank_target_capital_ratio,
        value.deposit_rate_floor,
        value.migrate_relationships_on_failure,
        value.state_resolution_backstop,
    });
}

[[nodiscard]] M5PolicyState decode_policy(const Json &row) {
    if (!row.is_array() || row.size() != 50) {
        throw std::runtime_error("invalid M5 policy");
    }
    M5PolicyState value;
    std::size_t i = 0;
    value.government_consumption_share = row[i++].get<double>();
    value.government_deficit_target = row[i++].get<double>();
    value.deficit_unemployment_reference = row[i++].get<double>();
    value.deficit_unemployment_cap = row[i++].get<double>();
    value.government_investment_share = row[i++].get<double>();
    value.profit_tax_rate = row[i++].get<double>();
    value.income_tax_rate = row[i++].get<double>();
    value.income_allowance = row[i++].get<double>();
    value.consumption_tax_rate = row[i++].get<double>();
    if (row[i].is_null()) {
        value.necessity_consumption_tax_rate.reset();
    } else {
        value.necessity_consumption_tax_rate = row[i].get<double>();
    }
    ++i;
    if (row[i].is_null()) {
        value.luxury_consumption_tax_rate.reset();
    } else {
        value.luxury_consumption_tax_rate = row[i].get<double>();
    }
    ++i;
    value.wealth_tax_rate = row[i++].get<double>();
    value.wealth_allowance = row[i++].get<double>();
    value.unemployment_benefit_replacement = row[i++].get<double>();
    value.benefit_income_floor = row[i++].get<double>();
    value.minimum_wage = row[i++].get<double>();
    value.job_guarantee = row[i++].get<bool>();
    value.job_guarantee_wage_ratio = row[i++].get<double>();
    value.job_guarantee_public_works_share = row[i++].get<double>();
    value.monetary_regime = static_cast<MonetaryRegime>(row[i++].get<std::uint8_t>());
    value.inflation_target = row[i++].get<double>();
    value.taylor_inflation = row[i++].get<double>();
    value.taylor_unemployment = row[i++].get<double>();
    value.rate_inertia = row[i++].get<double>();
    if (row[i].is_null()) {
        value.manual_policy_rate.reset();
    } else {
        value.manual_policy_rate = row[i].get<double>();
    }
    ++i;
    value.neutral_rate = row[i++].get<double>();
    value.natural_unemployment = row[i++].get<double>();
    value.maximum_policy_rate = row[i++].get<double>();
    value.inflation_sensor_lambda = row[i++].get<double>();
    value.core_inflation_sensor = row[i++].get<bool>();
    value.fixed_basket_cpi = row[i++].get<bool>();
    value.logarithmic_inflation = row[i++].get<bool>();
    value.fiscal_uses_national_accounts_gdp = row[i++].get<bool>();
    value.open_market_operations = row[i++].get<bool>();
    value.reserve_target = row[i++].get<double>();
    value.reserve_gap_close = row[i++].get<double>();
    value.reserve_target_indexes_deposits = row[i++].get<bool>();
    value.lender_of_last_resort = row[i++].get<bool>();
    value.reserve_floor_fraction = row[i++].get<double>();
    value.firm_leverage_limit = row[i++].get<double>();
    value.firm_minimum_dscr = row[i++].get<double>();
    value.household_credit_limit = row[i++].get<double>();
    value.bank_capital_constraint = row[i++].get<bool>();
    value.unified_bank_rwa = row[i++].get<bool>();
    value.bank_leverage_cap = row[i++].get<double>();
    value.bank_exposure_limit = row[i++].get<double>();
    value.bank_target_capital_ratio = row[i++].get<double>();
    value.deposit_rate_floor = row[i++].get<double>();
    value.migrate_relationships_on_failure = row[i++].get<bool>();
    value.state_resolution_backstop = row[i++].get<bool>();
    return value;
}

[[nodiscard]] Json encode_rules(const M5Rules &value) {
    return Json::array({
        value.bank_count,
        value.opening_capital_per_bank,
        value.bank_leverage_mean,
        value.bank_leverage_dispersion,
        value.assign_banks_by_size,
        value.realized_bank_pnl,
        value.full_firm_pnl,
        value.household_credit,
        value.rate_competition,
        value.relationship_lock_in,
        value.loan_spread_dispersion,
        value.bank_search_count,
        value.interbank,
        value.interbank_rate_base,
        value.interbank_tightness,
        value.deposit_spread_dispersion,
        value.deposit_search_count,
        value.deposit_rate,
        value.deposit_interest_arrears,
        value.interest_by_deposits,
        value.firm_amortization,
        value.household_amortization,
        value.household_subsistence,
        value.direct_monetary_transmission,
        value.bank_runs,
        value.run_sensitivity,
        value.run_health_reference,
        value.run_fear_persistence,
        value.bank_payout_ratio,
    });
}

[[nodiscard]] M5Rules decode_rules(const Json &row) {
    if (!row.is_array() || row.size() != 29) {
        throw std::runtime_error("invalid M5 rules");
    }
    M5Rules value;
    std::size_t i = 0;
    value.bank_count = row[i++].get<std::uint64_t>();
    value.opening_capital_per_bank = row[i++].get<double>();
    value.bank_leverage_mean = row[i++].get<double>();
    value.bank_leverage_dispersion = row[i++].get<double>();
    value.assign_banks_by_size = row[i++].get<bool>();
    value.realized_bank_pnl = row[i++].get<bool>();
    value.full_firm_pnl = row[i++].get<bool>();
    value.household_credit = row[i++].get<bool>();
    value.rate_competition = row[i++].get<bool>();
    value.relationship_lock_in = row[i++].get<bool>();
    value.loan_spread_dispersion = row[i++].get<double>();
    value.bank_search_count = row[i++].get<std::uint32_t>();
    value.interbank = row[i++].get<bool>();
    value.interbank_rate_base = row[i++].get<double>();
    value.interbank_tightness = row[i++].get<double>();
    value.deposit_spread_dispersion = row[i++].get<double>();
    value.deposit_search_count = row[i++].get<std::uint32_t>();
    value.deposit_rate = row[i++].get<double>();
    value.deposit_interest_arrears = row[i++].get<bool>();
    value.interest_by_deposits = row[i++].get<bool>();
    value.firm_amortization = row[i++].get<double>();
    value.household_amortization = row[i++].get<double>();
    value.household_subsistence = row[i++].get<double>();
    value.direct_monetary_transmission = row[i++].get<bool>();
    value.bank_runs = row[i++].get<bool>();
    value.run_sensitivity = row[i++].get<double>();
    value.run_health_reference = row[i++].get<double>();
    value.run_fear_persistence = row[i++].get<double>();
    value.bank_payout_ratio = row[i++].get<double>();
    return value;
}

[[nodiscard]] Json encode_metrics(const M5Metrics &value) {
    return Json::array({
        value.policy_rate,
        value.inflation_sensor,
        value.new_credit,
        value.principal_repaid,
        value.loan_interest_paid,
        value.household_interest_paid,
        value.deposit_interest_paid,
        value.total_loan_principal,
        value.total_bank_capital,
        value.total_reserves,
        value.reserve_stock,
        value.omo_flow,
        value.lolr_advances,
        value.lolr_outstanding,
        value.interbank_volume,
        value.interbank_rate,
        value.run_flight_volume,
        value.resolution_cost,
        value.realized_credit_losses,
        value.realized_interbank_losses,
        value.alive_banks,
        value.bank_failures,
    });
}

void decode_metrics(const Json &row, M5Metrics &value) {
    if (!row.is_array() || row.size() != 22) {
        throw std::runtime_error("invalid M5 metrics");
    }
    std::size_t i = 0;
    value.policy_rate = row[i++].get<double>();
    value.inflation_sensor = row[i++].get<double>();
    value.new_credit = row[i++].get<double>();
    value.principal_repaid = row[i++].get<double>();
    value.loan_interest_paid = row[i++].get<double>();
    value.household_interest_paid = row[i++].get<double>();
    value.deposit_interest_paid = row[i++].get<double>();
    value.total_loan_principal = row[i++].get<double>();
    value.total_bank_capital = row[i++].get<double>();
    value.total_reserves = row[i++].get<double>();
    value.reserve_stock = row[i++].get<double>();
    value.omo_flow = row[i++].get<double>();
    value.lolr_advances = row[i++].get<double>();
    value.lolr_outstanding = row[i++].get<double>();
    value.interbank_volume = row[i++].get<double>();
    value.interbank_rate = row[i++].get<double>();
    value.run_flight_volume = row[i++].get<double>();
    value.resolution_cost = row[i++].get<double>();
    value.realized_credit_losses = row[i++].get<double>();
    value.realized_interbank_losses = row[i++].get<double>();
    value.alive_banks = row[i++].get<std::uint64_t>();
    value.bank_failures = row[i++].get<std::uint64_t>();
}

[[nodiscard]] Json encode_state(const core::RootState &root, const M5Runtime &runtime) {
    Json output;
    output["policy"] = encode_policy(runtime.policy);
    output["rules"] = encode_rules(runtime.rules);
    output["runtime"] = Json::array({
        runtime.initial_policy_rate,
        runtime.policy_rate,
        runtime.inflation_sensor,
        runtime.previous_price_index,
        runtime.headline_price_index,
        runtime.previous_headline_price_index,
        runtime.previous_unemployment,
        runtime.reserve_genesis,
        runtime.bank_fear,
    });
    output["metrics"] = encode_metrics(runtime.last_metrics);
    output["banks"] = Json::array();
    root.banks.for_each_alive([&output](BankId id, const core::BankComponent &bank) {
        output["banks"].push_back(Json::array({
            id.value(),
            bank.leverage_appetite,
            bank.loan_spread,
            bank.deposit_spread,
            bank.alive,
        }));
    });
    output["interbank"] = Json::array();
    for (const auto &row : root.interbank.records()) {
        output["interbank"].push_back(Json::array({
            row.id.value(),
            row.lender.value(),
            row.borrower.value(),
            row.principal.value(),
            row.rate.value(),
            row.accrued_interest.value(),
            row.originated_tick.value(),
            row.maturity_tick.value(),
            row.active,
        }));
    }
    output["central_bank_operations"] = Json::array();
    for (const auto &row : root.central_bank_operations.records()) {
        output["central_bank_operations"].push_back(Json::array({
            row.id.value(),
            static_cast<std::uint8_t>(row.kind),
            row.counterparty.value(),
            row.principal.value(),
            row.rate.value(),
            row.opened_tick.value(),
            row.maturity_tick.value(),
            row.active,
        }));
    }
    output["bank_pnl"] = Json::array();
    for (const auto &row : root.bank_pnl.records()) {
        output["bank_pnl"].push_back(Json::array({
            row.bank.value(),
            row.tick.value(),
            row.loan_interest,
            row.interbank_interest_income,
            row.interbank_interest_expense,
            row.deposit_funding_cost,
            row.realized_loan_losses,
            row.realized_interbank_losses,
            row.resolution_flow,
            row.distributions,
            row.net_income,
        }));
    }
    output["bank_capital"] = Json::array();
    for (const auto &row : root.bank_capital.records()) {
        output["bank_capital"].push_back(Json::array({
            row.bank.value(),
            row.opening_capital,
            row.closing_capital,
            row.deposit_interest_arrears,
            row.last_closed_tick.value(),
            row.alive,
            row.resolved,
        }));
    }
    return output;
}

void decode_state(const Json &input, core::RootState &root, M5Runtime &runtime) {
    runtime.policy = decode_policy(input.at("policy"));
    runtime.rules = decode_rules(input.at("rules"));
    const auto &state = input.at("runtime");
    if (!state.is_array() || state.size() != 9) {
        throw std::runtime_error("invalid M5 runtime");
    }
    runtime.initial_policy_rate = state[0].get<double>();
    runtime.policy_rate = state[1].get<double>();
    runtime.inflation_sensor = state[2].get<double>();
    runtime.previous_price_index = state[3].get<double>();
    runtime.headline_price_index = state[4].get<double>();
    runtime.previous_headline_price_index = state[5].get<double>();
    runtime.previous_unemployment = state[6].get<double>();
    runtime.reserve_genesis = state[7].get<double>();
    runtime.bank_fear = state[8].get<double>();
    decode_metrics(input.at("metrics"), runtime.last_metrics);

    for (const auto &row : input.at("banks")) {
        if (!row.is_array() || row.size() != 5) {
            throw std::runtime_error("invalid M5 bank");
        }
        const BankId id(row[0].get<std::uint64_t>());
        auto *bank = root.banks.get(id);
        if (bank == nullptr) {
            throw std::runtime_error("unknown M5 bank");
        }
        bank->leverage_appetite = row[1].get<double>();
        bank->loan_spread = row[2].get<double>();
        bank->deposit_spread = row[3].get<double>();
        bank->alive = row[4].get<bool>();
    }
    std::vector<core::InterbankRecord> interbank;
    for (const auto &row : input.at("interbank")) {
        if (!row.is_array() || row.size() != 9) {
            throw std::runtime_error("invalid M5 interbank record");
        }
        interbank.push_back({
            InterbankContractId(row[0].get<std::uint64_t>()),
            BankId(row[1].get<std::uint64_t>()),
            BankId(row[2].get<std::uint64_t>()),
            Money(row[3].get<double>()),
            Rate(row[4].get<double>()),
            Money(row[5].get<double>()),
            Tick(row[6].get<std::uint64_t>()),
            Tick(row[7].get<std::uint64_t>()),
            row[8].get<bool>(),
        });
    }
    root.interbank.replace_records(interbank);
    std::vector<core::CentralBankOperationRecord> operations;
    for (const auto &row : input.at("central_bank_operations")) {
        if (!row.is_array() || row.size() != 8) {
            throw std::runtime_error("invalid M5 central-bank operation");
        }
        operations.push_back({
            CentralBankOperationId(row[0].get<std::uint64_t>()),
            static_cast<core::CentralBankOperationKind>(row[1].get<std::uint8_t>()),
            BankId(row[2].get<std::uint64_t>()),
            Money(row[3].get<double>()),
            Rate(row[4].get<double>()),
            Tick(row[5].get<std::uint64_t>()),
            Tick(row[6].get<std::uint64_t>()),
            row[7].get<bool>(),
        });
    }
    root.central_bank_operations.replace_records(operations);
    std::vector<core::BankPnlRecord> pnl;
    for (const auto &row : input.at("bank_pnl")) {
        if (!row.is_array() || row.size() != 11) {
            throw std::runtime_error("invalid M5 P&L record");
        }
        pnl.push_back({
            BankId(row[0].get<std::uint64_t>()),
            Tick(row[1].get<std::uint64_t>()),
            row[2].get<double>(),
            row[3].get<double>(),
            row[4].get<double>(),
            row[5].get<double>(),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<double>(),
            row[9].get<double>(),
            row[10].get<double>(),
        });
    }
    root.bank_pnl.replace_records(pnl);
    std::vector<core::BankCapitalRecord> capital;
    for (const auto &row : input.at("bank_capital")) {
        if (!row.is_array() || row.size() != 7) {
            throw std::runtime_error("invalid M5 capital record");
        }
        capital.push_back({
            BankId(row[0].get<std::uint64_t>()),
            row[1].get<double>(),
            row[2].get<double>(),
            row[3].get<double>(),
            Tick(row[4].get<std::uint64_t>()),
            row[5].get<bool>(),
            row[6].get<bool>(),
        });
    }
    root.bank_capital.replace_records(capital);
}

} // namespace

bool is_m5_checkpoint(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= kMagic.size() &&
           std::equal(kMagic.begin(), kMagic.end(), bytes.begin());
}

Result<std::vector<std::uint8_t>>
save_m5_checkpoint(const core::RootState &root, const M4Runtime &real_economy_runtime,
                   const M5Runtime &runtime, Tick tick) {
    if (!validate_m5_state(root, real_economy_runtime, runtime, tick).ok()) {
        return Status(ErrorCode::invariant_violation,
                      "M5 checkpoint state violates an invariant");
    }
    auto base = save_m4_checkpoint(root, real_economy_runtime, tick);
    if (!base.ok()) {
        return base.status();
    }
    const std::string encoded = encode_state(root, runtime).dump();
    std::vector<std::uint8_t> bytes;
    bytes.reserve(kMagic.size() + 4 + 8 + base.get_if()->size() + 8 + encoded.size() +
                  kDigestBytes);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kM5CheckpointSchemaVersion);
    append_u64(bytes, base.get_if()->size());
    bytes.insert(bytes.end(), base.get_if()->begin(), base.get_if()->end());
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    if (bytes.size() > kMaximumCheckpointBytes) {
        return Status(ErrorCode::out_of_range,
                      "M5 checkpoint exceeds the supported size");
    }
    return bytes;
}

Result<M5Checkpoint> load_m5_checkpoint(std::span<const std::uint8_t> bytes) {
    if (bytes.size() > kMaximumCheckpointBytes ||
        bytes.size() < kMagic.size() + 4 + 8 + 8 + kDigestBytes ||
        !is_m5_checkpoint(bytes)) {
        return corrupt("M5 checkpoint identity or size is invalid");
    }
    const auto payload = bytes.first(bytes.size() - kDigestBytes);
    const auto digest = core::sha256_digest(payload);
    if (!std::equal(digest.bytes.begin(), digest.bytes.end(),
                    bytes.end() - static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt("M5 checkpoint checksum does not match");
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0;
    std::uint64_t base_size = 0;
    if (!read_u32(payload, position, version) ||
        version != kM5CheckpointSchemaVersion ||
        !read_u64(payload, position, base_size) ||
        base_size > payload.size() - position) {
        return corrupt("M5 checkpoint header is invalid");
    }
    const auto base = payload.subspan(position, static_cast<std::size_t>(base_size));
    position += static_cast<std::size_t>(base_size);
    std::uint64_t json_size = 0;
    if (!read_u64(payload, position, json_size) ||
        json_size > payload.size() - position ||
        position + json_size != payload.size()) {
        return corrupt("M5 checkpoint payload size is invalid");
    }
    auto loaded = load_m4_checkpoint(base);
    if (!loaded.ok()) {
        return loaded.status();
    }
    try {
        const std::string encoded(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(json_size));
        const auto json = Json::parse(encoded);
        auto value = std::move(*loaded.get_if());
        M5Runtime runtime;
        decode_state(json, value.root, runtime);
        runtime.last_metrics.economy = value.runtime.last_metrics;
        runtime.last_metrics.economy.conservation_drift =
            runtime.last_metrics.economy.total_money -
            runtime.last_metrics.total_loan_principal -
            value.root.genesis_money.value();
        if (!validate_m5_state(value.root, value.runtime, runtime, value.tick).ok()) {
            return corrupt("M5 checkpoint restored state is invalid");
        }
        return M5Checkpoint{
            std::move(value.root),
            std::move(value.runtime),
            std::move(runtime),
            value.tick,
        };
    } catch (...) {
        return corrupt("M5 checkpoint JSON payload is invalid");
    }
}

} // namespace macro_sim::simulation
