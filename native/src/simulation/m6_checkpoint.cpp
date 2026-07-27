#include "macro_sim/simulation/m6_checkpoint.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/simulation/m5_checkpoint.hpp"

namespace macro_sim::simulation {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '6', 'C', 'P', '0', '1',
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
    if (position > bytes.size() || bytes.size() - position < 4) {
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
    if (position > bytes.size() || bytes.size() - position < 8) {
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

[[nodiscard]] Json encode_policy(const M6PolicyState &value) {
    return {
        {"bond_finance_fraction", value.bond_finance_fraction},
        {"bond_coupon_rate", value.bond_coupon_rate},
        {"bond_maturity_days", value.bond_maturity_days},
        {"household_bond_target", value.household_bond_target},
        {"bank_bond_appetite", value.bank_bond_appetite},
        {"bank_bond_duration_limit", value.bank_bond_duration_limit},
        {"margin_ltv", value.margin_ltv},
        {"margin_max", value.margin_max},
        {"household_bankruptcy", value.household_bankruptcy},
        {"bank_resolution_fund", value.bank_resolution_fund},
        {"bank_minimum_capital", value.bank_minimum_capital},
        {"bankrupt_persistence", value.bankrupt_persistence},
        {"regulatory_capital_haircut", value.regulatory_capital_haircut},
        {"regulatory_inventory_haircut", value.regulatory_inventory_haircut},
    };
}

[[nodiscard]] M6PolicyState decode_policy(const Json &row) {
    M6PolicyState value;
    value.bond_finance_fraction = row.at("bond_finance_fraction").get<double>();
    value.bond_coupon_rate = row.at("bond_coupon_rate").get<double>();
    value.bond_maturity_days = row.at("bond_maturity_days").get<std::uint64_t>();
    value.household_bond_target = row.at("household_bond_target").get<double>();
    value.bank_bond_appetite = row.at("bank_bond_appetite").get<double>();
    value.bank_bond_duration_limit = row.at("bank_bond_duration_limit").get<double>();
    value.margin_ltv = row.at("margin_ltv").get<double>();
    value.margin_max = row.at("margin_max").get<double>();
    value.household_bankruptcy = row.at("household_bankruptcy").get<bool>();
    value.bank_resolution_fund = row.at("bank_resolution_fund").get<bool>();
    value.bank_minimum_capital = row.at("bank_minimum_capital").get<double>();
    value.bankrupt_persistence =
        row.at("bankrupt_persistence").get<std::uint32_t>();
    value.regulatory_capital_haircut =
        row.at("regulatory_capital_haircut").get<double>();
    value.regulatory_inventory_haircut =
        row.at("regulatory_inventory_haircut").get<double>();
    return value;
}

[[nodiscard]] Json encode_rules(const M6Rules &value) {
    return {
        {"bonds", value.bonds},
        {"bond_maturity_bucket", value.bond_maturity_bucket},
        {"firm_equity", value.firm_equity},
        {"shares_per_firm", value.shares_per_firm},
        {"watchlist_size", value.watchlist_size},
        {"founder_owned_genesis", value.founder_owned_genesis},
        {"genesis_founder_pool", value.genesis_founder_pool},
        {"equity_price_adjustment", value.equity_price_adjustment},
        {"equity_trend_lambda", value.equity_trend_lambda},
        {"residual_income_lambda", value.residual_income_lambda},
        {"q_smoothing", value.q_smoothing},
        {"fundamental_weight", value.fundamental_weight},
        {"chartist_weight", value.chartist_weight},
        {"household_equity_target", value.household_equity_target},
        {"portfolio_adjustment", value.portfolio_adjustment},
        {"portfolio_review_interval_days",
         value.portfolio_review_interval_days},
        {"equity_finance", value.equity_finance},
        {"equity_issue_lambda", value.equity_issue_lambda},
        {"margin_credit", value.margin_credit},
        {"valuation_discount_floor", value.valuation_discount_floor},
        {"valuation_risk_premium", value.valuation_risk_premium},
        {"capital_haircut", value.capital_haircut},
        {"inventory_haircut", value.inventory_haircut},
        {"firm_dynamics", value.firm_dynamics},
        {"bankrupt_persistence", value.bankrupt_persistence},
        {"shell_exit_days", value.shell_exit_days},
        {"entry_hurdle", value.entry_hurdle},
        {"entry_beta", value.entry_beta},
        {"entry_max", value.entry_max},
        {"startup_deposits", value.startup_deposits},
        {"startup_capital", value.startup_capital},
        {"consumption_strata", value.consumption_strata},
        {"sector_switching", value.sector_switching},
        {"switch_return_gap", value.switch_return_gap},
        {"switch_pressure_days", value.switch_pressure_days},
        {"switch_hazard", value.switch_hazard},
        {"switch_retool_loss", value.switch_retool_loss},
        {"bank_equity", value.bank_equity},
        {"bank_equity_trading", value.bank_equity_trading},
        {"bank_shares", value.bank_shares},
        {"bank_equity_lambda", value.bank_equity_lambda},
        {"bank_equity_target", value.bank_equity_target},
        {"bank_dynamics", value.bank_dynamics},
        {"bank_entry_beta", value.bank_entry_beta},
        {"bank_entry_max", value.bank_entry_max},
    };
}

[[nodiscard]] M6Rules decode_rules(const Json &row) {
    M6Rules value;
#define M6_RULE(field, type) value.field = row.at(#field).get<type>()
    M6_RULE(bonds, bool);
    M6_RULE(bond_maturity_bucket, std::uint64_t);
    M6_RULE(firm_equity, bool);
    M6_RULE(shares_per_firm, double);
    M6_RULE(watchlist_size, std::uint32_t);
    M6_RULE(founder_owned_genesis, bool);
    M6_RULE(genesis_founder_pool, double);
    M6_RULE(equity_price_adjustment, double);
    M6_RULE(equity_trend_lambda, double);
    M6_RULE(residual_income_lambda, double);
    M6_RULE(q_smoothing, double);
    M6_RULE(fundamental_weight, double);
    M6_RULE(chartist_weight, double);
    M6_RULE(household_equity_target, double);
    M6_RULE(portfolio_adjustment, double);
    M6_RULE(portfolio_review_interval_days, std::uint32_t);
    M6_RULE(equity_finance, bool);
    M6_RULE(equity_issue_lambda, double);
    M6_RULE(margin_credit, bool);
    M6_RULE(valuation_discount_floor, double);
    M6_RULE(valuation_risk_premium, double);
    M6_RULE(capital_haircut, double);
    M6_RULE(inventory_haircut, double);
    M6_RULE(firm_dynamics, bool);
    M6_RULE(bankrupt_persistence, std::uint32_t);
    M6_RULE(shell_exit_days, std::uint32_t);
    M6_RULE(entry_hurdle, double);
    M6_RULE(entry_beta, double);
    M6_RULE(entry_max, std::uint32_t);
    M6_RULE(startup_deposits, double);
    M6_RULE(startup_capital, double);
    M6_RULE(consumption_strata, bool);
    M6_RULE(sector_switching, bool);
    M6_RULE(switch_return_gap, double);
    M6_RULE(switch_pressure_days, std::uint32_t);
    M6_RULE(switch_hazard, double);
    M6_RULE(switch_retool_loss, double);
    M6_RULE(bank_equity, bool);
    M6_RULE(bank_equity_trading, bool);
    M6_RULE(bank_shares, double);
    M6_RULE(bank_equity_lambda, double);
    M6_RULE(bank_equity_target, double);
    M6_RULE(bank_dynamics, bool);
    M6_RULE(bank_entry_beta, double);
    M6_RULE(bank_entry_max, std::uint32_t);
#undef M6_RULE
    return value;
}

[[nodiscard]] Json encode_metrics(const M6Metrics &value) {
    return Json::array({
        value.bond_outstanding_face,
        value.bond_market_value,
        value.bond_issuance,
        value.bond_redemption,
        value.bond_coupon_paid,
        value.firm_equity_market_cap,
        value.bank_equity_market_cap,
        value.equity_turnover,
        value.primary_equity_raised,
        value.margin_principal,
        value.margin_originated,
        value.margin_repaid,
        value.margin_writeoffs,
        value.total_firm_book_equity,
        value.clearing_residual,
        value.sector_retool_capital,
        value.active_security_lots,
        value.household_bankruptcies,
        value.firm_births,
        value.firm_exits,
        value.firm_defaults,
        value.sector_switches,
        value.bank_births,
        value.bank_equity_resolutions,
    });
}

void decode_metrics(const Json &row, M6Metrics &value) {
    if (!row.is_array() || row.size() != 24) {
        throw std::runtime_error("invalid M6 metrics");
    }
    std::size_t i = 0;
    value.bond_outstanding_face = row[i++].get<double>();
    value.bond_market_value = row[i++].get<double>();
    value.bond_issuance = row[i++].get<double>();
    value.bond_redemption = row[i++].get<double>();
    value.bond_coupon_paid = row[i++].get<double>();
    value.firm_equity_market_cap = row[i++].get<double>();
    value.bank_equity_market_cap = row[i++].get<double>();
    value.equity_turnover = row[i++].get<double>();
    value.primary_equity_raised = row[i++].get<double>();
    value.margin_principal = row[i++].get<double>();
    value.margin_originated = row[i++].get<double>();
    value.margin_repaid = row[i++].get<double>();
    value.margin_writeoffs = row[i++].get<double>();
    value.total_firm_book_equity = row[i++].get<double>();
    value.clearing_residual = row[i++].get<double>();
    value.sector_retool_capital = row[i++].get<double>();
    value.active_security_lots = row[i++].get<std::uint64_t>();
    value.household_bankruptcies = row[i++].get<std::uint64_t>();
    value.firm_births = row[i++].get<std::uint64_t>();
    value.firm_exits = row[i++].get<std::uint64_t>();
    value.firm_defaults = row[i++].get<std::uint64_t>();
    value.sector_switches = row[i++].get<std::uint64_t>();
    value.bank_births = row[i++].get<std::uint64_t>();
    value.bank_equity_resolutions = row[i++].get<std::uint64_t>();
}

[[nodiscard]] Json encode_statement(const FirmStatement &value) {
    return Json::array({
        value.firm.value(),
        value.cash,
        value.debt,
        value.interest_arrears,
        value.capital_units,
        value.capital_unit_price,
        value.capital_value,
        value.output_inventory_units,
        value.output_inventory_unit_price,
        value.output_inventory_value,
        value.work_in_progress_value,
        value.input_inventory_value,
        value.inventory_value,
        value.gross_assets,
        value.book_equity,
        value.eligible_collateral_value,
        value.borrowing_base_proxy,
        value.borrowing_base_headroom,
        value.earnings,
    });
}

[[nodiscard]] FirmStatement decode_statement(const Json &row) {
    if (!row.is_array() || row.size() != 19) {
        throw std::runtime_error("invalid M6 firm statement");
    }
    FirmStatement value;
    std::size_t i = 0;
    value.firm = FirmId(row[i++].get<std::uint64_t>());
    value.cash = row[i++].get<double>();
    value.debt = row[i++].get<double>();
    value.interest_arrears = row[i++].get<double>();
    value.capital_units = row[i++].get<double>();
    value.capital_unit_price = row[i++].get<double>();
    value.capital_value = row[i++].get<double>();
    value.output_inventory_units = row[i++].get<double>();
    value.output_inventory_unit_price = row[i++].get<double>();
    value.output_inventory_value = row[i++].get<double>();
    value.work_in_progress_value = row[i++].get<double>();
    value.input_inventory_value = row[i++].get<double>();
    value.inventory_value = row[i++].get<double>();
    value.gross_assets = row[i++].get<double>();
    value.book_equity = row[i++].get<double>();
    value.eligible_collateral_value = row[i++].get<double>();
    value.borrowing_base_proxy = row[i++].get<double>();
    value.borrowing_base_headroom = row[i++].get<double>();
    value.earnings = row[i++].get<double>();
    return value;
}

[[nodiscard]] Json encode_runtime(const M6Runtime &runtime) {
    Json output;
    output["policy"] = encode_policy(runtime.policy);
    output["rules"] = encode_rules(runtime.rules);
    output["runtime"] = Json::array({
        runtime.replacement_capital_price,
        runtime.lifecycle_rng_counter,
        runtime.security_rng_counter,
        runtime.securities.version(),
    });
    output["metrics"] = encode_metrics(runtime.last_metrics);
    output["bonds"] = Json::array();
    for (const auto &row : runtime.securities.bonds()) {
        output["bonds"].push_back(Json::array({
            row.id.value(),
            static_cast<std::uint8_t>(row.issuer.kind()),
            row.issuer.value(),
            row.issuer_account.value(),
            row.currency.value(),
            row.issued_tick.value(),
            row.maturity_tick.value(),
            row.coupon_rate.value(),
            row.original_face.value(),
            row.outstanding_face.value(),
            row.active,
            row.settled,
        }));
    }
    output["equities"] = Json::array();
    for (const auto &row : runtime.securities.equities()) {
        output["equities"].push_back(Json::array({
            row.id.value(),
            static_cast<std::uint8_t>(row.issuer_kind),
            static_cast<std::uint8_t>(row.issuer.kind()),
            row.issuer.value(),
            row.issuer_account.value(),
            row.currency.value(),
            row.outstanding_shares,
            row.price.value(),
            row.last_price.value(),
            row.peak_price.value(),
            row.fundamental.value(),
            row.trend,
            row.income_signal,
            row.active,
            row.resolved,
        }));
    }
    output["lots"] = Json::array();
    std::uint32_t security_lot_id = 1U;
    for (const auto &row : runtime.securities.lots()) {
        output["lots"].push_back(Json::array({
            security_lot_id++,
            static_cast<std::uint8_t>(row.security.kind()),
            row.security.value(),
            static_cast<std::uint8_t>(row.holder.kind()),
            row.holder.value(),
            row.units,
            row.cost_basis.value(),
            row.active(),
        }));
    }
    output["firms"] = Json::array();
    for (const auto &row : runtime.firms) {
        output["firms"].push_back(Json::array({
            row.firm.value(),
            encode_statement(row.statement),
            static_cast<std::uint8_t>(row.stratum),
            row.insolvent_days,
            row.shell_days,
            row.switch_pressure_days,
            row.residual_income_ema,
            row.tobin_q_ema,
            row.active,
            row.defaulted,
        }));
    }
    output["watchlist_rows"] = Json::array();
    for (const auto &row : runtime.watchlist_rows) {
        output["watchlist_rows"].push_back(Json::array({
            row.household.value(),
            row.offset,
            row.count,
        }));
    }
    output["watchlist_equities"] = Json::array();
    for (const auto equity : runtime.watchlist_equities) {
        output["watchlist_equities"].push_back(equity.value());
    }
    output["margin_loans"] = Json::array();
    for (const auto loan : runtime.margin_loans) {
        output["margin_loans"].push_back(loan.value());
    }
    return output;
}

void decode_runtime(const Json &input, M6Runtime &runtime) {
    runtime.policy = decode_policy(input.at("policy"));
    runtime.rules = decode_rules(input.at("rules"));
    const auto &state = input.at("runtime");
    if (!state.is_array() || state.size() != 4) {
        throw std::runtime_error("invalid M6 runtime");
    }
    runtime.replacement_capital_price = state[0].get<double>();
    runtime.lifecycle_rng_counter = state[1].get<std::uint64_t>();
    runtime.security_rng_counter = state[2].get<std::uint64_t>();
    const auto security_version = state[3].get<std::uint64_t>();
    decode_metrics(input.at("metrics"), runtime.last_metrics);

    std::vector<core::BondContract> bonds;
    for (const auto &row : input.at("bonds")) {
        if (!row.is_array() || row.size() != 12) {
            throw std::runtime_error("invalid M6 bond");
        }
        bonds.push_back({
            BondId(row[0].get<std::uint64_t>()),
            {
                static_cast<core::OwnerKind>(row[1].get<std::uint8_t>()),
                row[2].get<std::uint32_t>(),
            },
            AccountId(row[3].get<std::uint64_t>()),
            CurrencyId(row[4].get<std::uint32_t>()),
            Tick(row[5].get<std::uint64_t>()),
            Tick(row[6].get<std::uint64_t>()),
            Rate(row[7].get<double>()),
            Money(row[8].get<double>()),
            Money(row[9].get<double>()),
            row[10].get<bool>(),
            row[11].get<bool>(),
        });
    }
    std::vector<core::EquityContract> equities;
    for (const auto &row : input.at("equities")) {
        if (!row.is_array() || row.size() != 15) {
            throw std::runtime_error("invalid M6 equity");
        }
        equities.push_back({
            EquityId(row[0].get<std::uint64_t>()),
            static_cast<core::EquityIssuerKind>(row[1].get<std::uint8_t>()),
            {
                static_cast<core::OwnerKind>(row[2].get<std::uint8_t>()),
                row[3].get<std::uint32_t>(),
            },
            AccountId(row[4].get<std::uint64_t>()),
            CurrencyId(row[5].get<std::uint32_t>()),
            row[6].get<double>(),
            Price(row[7].get<double>()),
            Price(row[8].get<double>()),
            Price(row[9].get<double>()),
            Price(row[10].get<double>()),
            row[11].get<double>(),
            row[12].get<double>(),
            row[13].get<bool>(),
            row[14].get<bool>(),
        });
    }
    std::vector<core::SecurityLot> lots;
    for (const auto &row : input.at("lots")) {
        if (!row.is_array() || row.size() != 8) {
            throw std::runtime_error("invalid M6 security lot");
        }
        const auto expected_id =
            static_cast<std::uint64_t>(lots.size()) + 1U;
        if (row[0].get<std::uint64_t>() != expected_id) {
            throw std::runtime_error("invalid M6 security lot identity");
        }
        const double units = row[5].get<double>();
        const double cost_basis = row[6].get<double>();
        const bool active = row[7].get<bool>();
        if (active != (units > 0.0) || (!active && cost_basis != 0.0)) {
            throw std::runtime_error("invalid M6 security lot activity");
        }
        lots.push_back({
            SecurityLotId(expected_id),
            {
                static_cast<core::SecurityKind>(row[1].get<std::uint8_t>()),
                row[2].get<std::uint32_t>(),
            },
            {
                static_cast<core::OwnerKind>(row[3].get<std::uint8_t>()),
                row[4].get<std::uint32_t>(),
            },
            units,
            Money(cost_basis),
            active,
        });
    }
    runtime.securities.replace_records(std::move(bonds), std::move(equities),
                                       std::move(lots), security_version);

    for (const auto &row : input.at("firms")) {
        if (!row.is_array() || row.size() != 10) {
            throw std::runtime_error("invalid M6 firm lifecycle");
        }
        FirmLifecycleRecord value;
        value.firm = FirmId(row[0].get<std::uint64_t>());
        value.statement = decode_statement(row[1]);
        value.stratum = static_cast<ConsumptionStratum>(row[2].get<std::uint8_t>());
        value.insolvent_days = row[3].get<std::uint32_t>();
        value.shell_days = row[4].get<std::uint32_t>();
        value.switch_pressure_days = row[5].get<std::uint32_t>();
        value.residual_income_ema = row[6].get<double>();
        value.tobin_q_ema = row[7].get<double>();
        value.active = row[8].get<bool>();
        value.defaulted = row[9].get<bool>();
        runtime.firms.push_back(value);
    }
    for (const auto &row : input.at("watchlist_rows")) {
        if (!row.is_array() || row.size() != 3) {
            throw std::runtime_error("invalid M6 watchlist row");
        }
        runtime.watchlist_rows.push_back({
            HouseholdId(row[0].get<std::uint64_t>()),
            row[1].get<std::uint32_t>(),
            row[2].get<std::uint32_t>(),
        });
    }
    for (const auto &row : input.at("watchlist_equities")) {
        runtime.watchlist_equities.emplace_back(row.get<std::uint64_t>());
    }
    for (const auto &row : input.at("margin_loans")) {
        runtime.margin_loans.emplace_back(row.get<std::uint64_t>());
    }
}

} // namespace

bool is_m6_checkpoint(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= kMagic.size() &&
           std::equal(kMagic.begin(), kMagic.end(), bytes.begin());
}

Result<std::vector<std::uint8_t>>
save_m6_checkpoint(const core::RootState &root, const M4Runtime &real_economy_runtime,
                   const M5Runtime &monetary_runtime, const M6Runtime &runtime,
                   Tick tick) {
    if (!validate_m6_state(root, real_economy_runtime, monetary_runtime, runtime, tick)
             .ok()) {
        return Status(ErrorCode::invariant_violation,
                      "M6 checkpoint state violates an invariant");
    }
    auto base = save_m5_checkpoint(root, real_economy_runtime, monetary_runtime, tick);
    if (!base.ok()) {
        return base.status();
    }
    const std::string encoded = encode_runtime(runtime).dump();
    std::vector<std::uint8_t> bytes;
    bytes.reserve(kMagic.size() + 4 + 8 + base.get_if()->size() + 8 + encoded.size() +
                  kDigestBytes);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kM6CheckpointSchemaVersion);
    append_u64(bytes, base.get_if()->size());
    bytes.insert(bytes.end(), base.get_if()->begin(), base.get_if()->end());
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    if (bytes.size() > kMaximumCheckpointBytes) {
        return Status(ErrorCode::out_of_range,
                      "M6 checkpoint exceeds the supported size");
    }
    return bytes;
}

Result<M6Checkpoint> load_m6_checkpoint(std::span<const std::uint8_t> bytes) {
    if (bytes.size() > kMaximumCheckpointBytes ||
        bytes.size() < kMagic.size() + 4 + 8 + 8 + kDigestBytes ||
        !is_m6_checkpoint(bytes)) {
        return corrupt("M6 checkpoint identity or size is invalid");
    }
    const auto payload = bytes.first(bytes.size() - kDigestBytes);
    const auto digest = core::sha256_digest(payload);
    if (!std::equal(digest.bytes.begin(), digest.bytes.end(),
                    bytes.end() - static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt("M6 checkpoint checksum does not match");
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0;
    std::uint64_t base_size = 0;
    if (!read_u32(payload, position, version) ||
        version != kM6CheckpointSchemaVersion ||
        !read_u64(payload, position, base_size) ||
        base_size > payload.size() - position) {
        return corrupt("M6 checkpoint header is invalid");
    }
    const auto base = payload.subspan(position, static_cast<std::size_t>(base_size));
    position += static_cast<std::size_t>(base_size);
    std::uint64_t json_size = 0;
    if (!read_u64(payload, position, json_size) ||
        json_size > payload.size() - position ||
        position + json_size != payload.size()) {
        return corrupt("M6 checkpoint payload size is invalid");
    }
    auto loaded = load_m5_checkpoint(base);
    if (!loaded.ok()) {
        return loaded.status();
    }
    try {
        const std::string encoded(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(json_size));
        const auto json = Json::parse(encoded);
        auto value = std::move(*loaded.get_if());
        M6Runtime runtime;
        decode_runtime(json, runtime);
        runtime.last_metrics.economy = value.runtime.last_metrics;
        if (!validate_m6_state(value.root, value.real_economy_runtime, value.runtime,
                               runtime, value.tick)
                 .ok()) {
            return corrupt("M6 checkpoint restored state is invalid");
        }
        return M6Checkpoint{
            std::move(value.root),
            std::move(value.real_economy_runtime),
            std::move(value.runtime),
            std::move(runtime),
            value.tick,
        };
    } catch (...) {
        return corrupt("M6 checkpoint JSON payload is invalid");
    }
}

Result<core::StateDigest> m6_state_digest(const core::RootState &root,
                                          const M4Runtime &real_economy_runtime,
                                          const M5Runtime &monetary_runtime,
                                          const M6Runtime &runtime, Tick tick) {
    auto checkpoint =
        save_m6_checkpoint(root, real_economy_runtime, monetary_runtime, runtime, tick);
    if (!checkpoint.ok()) {
        return checkpoint.status();
    }
    return core::sha256_digest(*checkpoint.get_if());
}

} // namespace macro_sim::simulation
