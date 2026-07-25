#include "macro_sim/simulation/m9.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/simulation/m8_checkpoint.hpp"

namespace macro_sim::simulation {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '9', 'C', 'P', '0', '1',
};
constexpr std::uint32_t kSchemaVersion = 1U;
constexpr std::size_t kDigestBytes = 32U;
constexpr std::size_t kMaximumCheckpointBytes = 2U * 1024U * 1024U * 1024U;

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
    if (position > bytes.size() || bytes.size() - position < 4U) {
        return false;
    }
    value = 0U;
    for (int index = 0; index < 4; ++index) {
        value = static_cast<std::uint32_t>((value << 8U) | bytes[position++]);
    }
    return true;
}

[[nodiscard]] bool read_u64(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint64_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 8U) {
        return false;
    }
    value = 0U;
    for (int index = 0; index < 8; ++index) {
        value = (value << 8U) | bytes[position++];
    }
    return true;
}

[[nodiscard]] Status corrupt() noexcept {
    return Status(ErrorCode::corrupt_input, "M9 checkpoint is invalid");
}

[[nodiscard]] Json encode_rules(const WorldRules &value) {
    return Json::array({
        value.trade,
        value.capital,
        value.migration,
        value.fx_adjustment,
        value.fx_friction,
        value.fx_spread,
        value.fx_loss_mutualization,
        value.fx_trade_cap,
        value.capital_mobility,
        value.capital_adjustment,
        value.periods_per_year,
        value.migration_rate,
        value.migration_max_share,
        value.remittance_share,
        value.wage_smoothing,
        value.initial_peg_reserves,
        value.dense_edge_threshold,
    });
}

[[nodiscard]] WorldRules decode_rules(const Json &input) {
    if (!input.is_array() || input.size() != 17U) {
        throw std::runtime_error("invalid World rules");
    }
    WorldRules value;
    value.trade = input[0].get<bool>();
    value.capital = input[1].get<bool>();
    value.migration = input[2].get<bool>();
    value.fx_adjustment = input[3].get<double>();
    value.fx_friction = input[4].get<double>();
    value.fx_spread = input[5].get<double>();
    value.fx_loss_mutualization = input[6].get<bool>();
    value.fx_trade_cap = input[7].get<double>();
    value.capital_mobility = input[8].get<double>();
    value.capital_adjustment = input[9].get<double>();
    value.periods_per_year = input[10].get<double>();
    value.migration_rate = input[11].get<double>();
    value.migration_max_share = input[12].get<double>();
    value.remittance_share = input[13].get<double>();
    value.wage_smoothing = input[14].get<double>();
    value.initial_peg_reserves = input[15].get<double>();
    value.dense_edge_threshold = input[16].get<std::size_t>();
    return value;
}

[[nodiscard]] Json optional_value(const std::optional<double> &value) {
    return value.has_value() ? Json(*value) : Json(nullptr);
}

[[nodiscard]] std::optional<double> decode_optional(const Json &value) {
    return value.is_null() ? std::nullopt : std::optional<double>(value.get<double>());
}

[[nodiscard]] Json encode_policy(const ExternalPolicyState &value) {
    Json sanctions = Json::array();
    for (const auto target : value.sanctions_imposed_on) {
        sanctions.push_back(target.value());
    }
    return Json::array({
        value.tariff,
        optional_value(value.import_quota),
        value.export_subsidy,
        value.capital_control,
        value.external_interest_settlement_fraction,
        std::move(sanctions),
        optional_value(value.immigration_cap),
        optional_value(value.emigration_cap),
        value.remittance_tax,
        value.outward_remittance_tax,
        value.guest_worker_return,
        static_cast<std::uint8_t>(value.fx_regime),
        value.peg_anchor.has_value() ? Json(value.peg_anchor->value()) : Json(nullptr),
        value.peg_reserve_scale,
    });
}

[[nodiscard]] ExternalPolicyState decode_policy(const Json &input) {
    if (!input.is_array() || input.size() != 14U) {
        throw std::runtime_error("invalid external policy");
    }
    ExternalPolicyState value;
    value.tariff = input[0].get<double>();
    value.import_quota = decode_optional(input[1]);
    value.export_subsidy = input[2].get<double>();
    value.capital_control = input[3].get<double>();
    value.external_interest_settlement_fraction = input[4].get<double>();
    for (const auto &target : input[5]) {
        value.sanctions_imposed_on.emplace_back(target.get<std::uint64_t>());
    }
    value.immigration_cap = decode_optional(input[6]);
    value.emigration_cap = decode_optional(input[7]);
    value.remittance_tax = input[8].get<double>();
    value.outward_remittance_tax = input[9].get<double>();
    value.guest_worker_return = input[10].get<double>();
    value.fx_regime = static_cast<FxRegime>(input[11].get<std::uint8_t>());
    if (!input[12].is_null()) {
        value.peg_anchor = EconomyId(input[12].get<std::uint64_t>());
    }
    value.peg_reserve_scale = input[13].get<double>();
    return value;
}

[[nodiscard]] Json encode_shock(const ShockSpec &value) {
    return Json::array({
        value.id,
        static_cast<std::uint8_t>(value.kind),
        value.economy.has_value() ? Json(value.economy->value()) : Json(nullptr),
        value.start.value(),
        value.announcement.has_value() ? Json(value.announcement->value())
                                       : Json(nullptr),
        value.duration,
        value.magnitude,
        static_cast<std::uint8_t>(value.shape),
        value.ramp_in_ticks,
        value.ramp_out_ticks,
        value.sector.has_value() ? Json(static_cast<std::uint8_t>(*value.sector))
                                 : Json(nullptr),
    });
}

[[nodiscard]] ShockSpec decode_shock(const Json &input) {
    if (!input.is_array() || input.size() != 11U) {
        throw std::runtime_error("invalid shock");
    }
    ShockSpec value;
    value.id = input[0].get<std::uint64_t>();
    value.kind = static_cast<ShockKind>(input[1].get<std::uint8_t>());
    if (!input[2].is_null()) {
        value.economy = EconomyId(input[2].get<std::uint64_t>());
    }
    value.start = Tick(input[3].get<std::uint64_t>());
    if (!input[4].is_null()) {
        value.announcement = Tick(input[4].get<std::uint64_t>());
    }
    value.duration = input[5].get<std::uint64_t>();
    value.magnitude = input[6].get<double>();
    value.shape = static_cast<ShockShape>(input[7].get<std::uint8_t>());
    value.ramp_in_ticks = input[8].get<std::uint64_t>();
    value.ramp_out_ticks = input[9].get<std::uint64_t>();
    if (!input[10].is_null()) {
        value.sector = static_cast<ShockSector>(input[10].get<std::uint8_t>());
    }
    return value;
}

[[nodiscard]] Json encode_country_metrics(const CountryExternalMetrics &value) {
    return Json::array({
        value.exchange_rate,        value.imports_value,
        value.imports_volume,       value.exports_value,
        value.exports_volume,       value.iceberg_loss,
        value.tariff_revenue,       value.export_subsidy_cost,
        value.current_account,      value.capital_flow,
        value.net_foreign_assets,   value.factor_income_accrued,
        value.factor_income_cash,   value.factor_income_arrears,
        value.peg_reserves,         value.migrant_stock_abroad,
        value.migrant_stock_hosted, value.remittances_received,
        value.remittances_sent,     value.remittance_tax_revenue,
        value.capital_destroyed,    value.active_shocks,
    });
}

[[nodiscard]] CountryExternalMetrics decode_country_metrics(const Json &input) {
    if (!input.is_array() || input.size() != 22U) {
        throw std::runtime_error("invalid country metrics");
    }
    CountryExternalMetrics value;
    value.exchange_rate = input[0].get<double>();
    value.imports_value = input[1].get<double>();
    value.imports_volume = input[2].get<double>();
    value.exports_value = input[3].get<double>();
    value.exports_volume = input[4].get<double>();
    value.iceberg_loss = input[5].get<double>();
    value.tariff_revenue = input[6].get<double>();
    value.export_subsidy_cost = input[7].get<double>();
    value.current_account = input[8].get<double>();
    value.capital_flow = input[9].get<double>();
    value.net_foreign_assets = input[10].get<double>();
    value.factor_income_accrued = input[11].get<double>();
    value.factor_income_cash = input[12].get<double>();
    value.factor_income_arrears = input[13].get<double>();
    value.peg_reserves = input[14].get<double>();
    value.migrant_stock_abroad = input[15].get<double>();
    value.migrant_stock_hosted = input[16].get<double>();
    value.remittances_received = input[17].get<double>();
    value.remittances_sent = input[18].get<double>();
    value.remittance_tax_revenue = input[19].get<double>();
    value.capital_destroyed = input[20].get<double>();
    value.active_shocks = input[21].get<std::uint64_t>();
    return value;
}

} // namespace

Result<std::vector<std::uint8_t>> M9World::checkpoint() const {
    const auto state_status = validate();
    if (!state_status.ok()) {
        return Status(ErrorCode::invariant_violation, "cannot save invalid M9 World");
    }
    Json metadata;
    metadata["tick"] = tick_.value();
    metadata["rules"] = encode_rules(rules_);
    metadata["rates"] = rates_.log_rates;
    metadata["dealer"] = dealer_inventory_;
    metadata["principal"] = external_principal_;
    metadata["arrears"] = interest_arrears_;
    metadata["smoothed_wages"] = smoothed_real_wages_;
    metadata["dealer_valuation"] = dealer_valuation_;
    metadata["event_counter"] = event_counter_;
    metadata["announced_shocks"] = announced_shock_ids_;
    metadata["active_shocks"] = active_shock_ids_;
    metadata["realized_shocks"] = realized_shock_ids_;
    metadata["shock_events"] = Json::array();
    for (const auto &event : shock_events_) {
        metadata["shock_events"].push_back(Json::array({
            event.sequence,
            static_cast<std::uint8_t>(event.type),
            event.tick.value(),
            event.shock_id,
            event.intensity,
        }));
    }
    metadata["policies"] = Json::array();
    for (const auto &policy : external_policies_) {
        metadata["policies"].push_back(encode_policy(policy));
    }
    metadata["pegs"] = Json::array();
    for (const auto &peg : pegs_) {
        metadata["pegs"].push_back(Json::array({
            peg.pegger.value(),
            peg.anchor.value(),
            peg.reserves,
            peg.pressure,
            peg.target_log_spread,
            peg.intact,
        }));
    }
    metadata["migration"] = Json::array();
    for (const auto &route : migration_routes_) {
        metadata["migration"].push_back(Json::array({
            route.origin.value(),
            route.host.value(),
            route.stock,
            route.smoothed_real_wage_gap,
            route.flow,
            route.return_flow,
            route.remittance_gross,
            route.remittance_net,
        }));
    }
    metadata["shocks"] = Json::array();
    for (const auto &shock : shocks_) {
        metadata["shocks"].push_back(encode_shock(shock));
    }
    metadata["external_metrics"] = Json::array();
    for (const auto &metrics : last_metrics_.external) {
        metadata["external_metrics"].push_back(encode_country_metrics(metrics));
    }
    metadata["world_metrics"] = Json::array({
        last_metrics_.dealer_flow,
        last_metrics_.dealer_spread_revenue,
        last_metrics_.dealer_valuation,
        last_metrics_.world_nfa,
        last_metrics_.trade_routes,
        last_metrics_.migration_routes,
        last_metrics_.shock_events,
    });

    const auto encoded = metadata.dump();
    std::vector<std::vector<std::uint8_t>> domestic;
    domestic.reserve(economies_.size());
    std::size_t reserve_size =
        kMagic.size() + 4U + 8U + encoded.size() + 8U + kDigestBytes;
    for (const auto &economy : economies_) {
        auto value = save_m8_checkpoint(
            economy.root, economy.real_economy, economy.monetary, economy.financial,
            economy.population, economy.domestic, economy.tick);
        if (!value.ok()) {
            return value.status();
        }
        reserve_size += 8U + value.get_if()->size();
        domestic.push_back(std::move(*value.get_if()));
    }
    if (reserve_size > kMaximumCheckpointBytes) {
        return Status(ErrorCode::out_of_range,
                      "M9 checkpoint exceeds the supported size");
    }
    std::vector<std::uint8_t> bytes;
    bytes.reserve(reserve_size);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kSchemaVersion);
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    append_u64(bytes, domestic.size());
    for (const auto &value : domestic) {
        append_u64(bytes, value.size());
        bytes.insert(bytes.end(), value.begin(), value.end());
    }
    const auto digest_value = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest_value.bytes.begin(), digest_value.bytes.end());
    return bytes;
}

Result<std::vector<std::uint8_t>> M9World::economy_checkpoint(EconomyId economy) const {
    if (!economy.valid() || economy.value() >= economies_.size()) {
        return Status(ErrorCode::out_of_range,
                      "M9 economy checkpoint index is out of range");
    }
    const auto &state = economies_[static_cast<std::size_t>(economy.value())];
    return save_m8_checkpoint(state.root, state.real_economy, state.monetary,
                              state.financial, state.population, state.domestic,
                              state.tick);
}

Result<M9World> M9World::restore(std::span<const std::uint8_t> checkpoint) {
    if (checkpoint.size() > kMaximumCheckpointBytes ||
        checkpoint.size() < kMagic.size() + 4U + 8U + 8U + kDigestBytes ||
        !std::equal(kMagic.begin(), kMagic.end(), checkpoint.begin())) {
        return corrupt();
    }
    const auto payload = checkpoint.first(checkpoint.size() - kDigestBytes);
    const auto digest_value = core::sha256_digest(payload);
    if (!std::equal(digest_value.bytes.begin(), digest_value.bytes.end(),
                    checkpoint.end() - static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt();
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0U;
    std::uint64_t json_size = 0U;
    if (!read_u32(payload, position, version) || version != kSchemaVersion ||
        !read_u64(payload, position, json_size) ||
        json_size > payload.size() - position) {
        return corrupt();
    }
    try {
        const std::string encoded(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(json_size));
        position += static_cast<std::size_t>(json_size);
        const auto metadata = Json::parse(encoded);
        std::uint64_t economy_count = 0U;
        if (!read_u64(payload, position, economy_count) || economy_count == 0U ||
            economy_count >
                static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
            return corrupt();
        }

        M9World world;
        world.tick_ = Tick(metadata.at("tick").get<std::uint64_t>());
        world.rules_ = decode_rules(metadata.at("rules"));
        world.rates_.log_rates = metadata.at("rates").get<std::vector<double>>();
        world.dealer_inventory_ = metadata.at("dealer").get<std::vector<double>>();
        world.external_principal_ =
            metadata.at("principal").get<std::vector<std::vector<double>>>();
        world.interest_arrears_ =
            metadata.at("arrears").get<std::vector<std::vector<double>>>();
        world.smoothed_real_wages_ =
            metadata.at("smoothed_wages").get<std::vector<double>>();
        world.dealer_valuation_ = metadata.at("dealer_valuation").get<double>();
        world.event_counter_ = metadata.at("event_counter").get<std::uint64_t>();
        world.announced_shock_ids_ =
            metadata.at("announced_shocks").get<std::vector<std::uint64_t>>();
        world.active_shock_ids_ =
            metadata.at("active_shocks").get<std::vector<std::uint64_t>>();
        world.realized_shock_ids_ =
            metadata.at("realized_shocks").get<std::vector<std::uint64_t>>();
        for (const auto &item : metadata.at("shock_events")) {
            if (!item.is_array() || item.size() != 5U) {
                return corrupt();
            }
            world.shock_events_.push_back(ShockEvent{
                item[0].get<std::uint64_t>(),
                static_cast<ShockEventType>(item[1].get<std::uint8_t>()),
                Tick(item[2].get<std::uint64_t>()),
                item[3].get<std::uint64_t>(),
                item[4].get<double>(),
            });
        }
        for (const auto &item : metadata.at("policies")) {
            world.external_policies_.push_back(decode_policy(item));
        }
        for (const auto &item : metadata.at("pegs")) {
            if (!item.is_array() || item.size() != 6U) {
                return corrupt();
            }
            world.pegs_.push_back(PegRuntime{
                EconomyId(item[0].get<std::uint64_t>()),
                EconomyId(item[1].get<std::uint64_t>()),
                item[2].get<double>(),
                item[3].get<double>(),
                item[4].get<double>(),
                item[5].get<bool>(),
            });
        }
        for (const auto &item : metadata.at("migration")) {
            if (!item.is_array() || item.size() != 8U) {
                return corrupt();
            }
            world.migration_routes_.push_back(MigrationRoute{
                EconomyId(item[0].get<std::uint64_t>()),
                EconomyId(item[1].get<std::uint64_t>()),
                item[2].get<double>(),
                item[3].get<double>(),
                item[4].get<double>(),
                item[5].get<double>(),
                item[6].get<double>(),
                item[7].get<double>(),
            });
        }
        for (const auto &item : metadata.at("shocks")) {
            world.shocks_.push_back(decode_shock(item));
        }
        for (const auto &item : metadata.at("external_metrics")) {
            world.last_metrics_.external.push_back(decode_country_metrics(item));
        }
        const auto &world_metrics = metadata.at("world_metrics");
        if (!world_metrics.is_array() || world_metrics.size() != 7U) {
            return corrupt();
        }
        world.last_metrics_.dealer_flow = world_metrics[0].get<double>();
        world.last_metrics_.dealer_spread_revenue = world_metrics[1].get<double>();
        world.last_metrics_.dealer_valuation = world_metrics[2].get<double>();
        world.last_metrics_.world_nfa = world_metrics[3].get<double>();
        world.last_metrics_.trade_routes = world_metrics[4].get<std::uint64_t>();
        world.last_metrics_.migration_routes = world_metrics[5].get<std::uint64_t>();
        world.last_metrics_.shock_events = world_metrics[6].get<std::uint64_t>();

        world.economies_.reserve(static_cast<std::size_t>(economy_count));
        world.last_metrics_.domestic.reserve(static_cast<std::size_t>(economy_count));
        for (std::uint64_t index = 0U; index < economy_count; ++index) {
            std::uint64_t size = 0U;
            if (!read_u64(payload, position, size) ||
                size > payload.size() - position) {
                return corrupt();
            }
            auto loaded = load_m8_checkpoint(
                payload.subspan(position, static_cast<std::size_t>(size)));
            if (!loaded.ok()) {
                return loaded.status();
            }
            position += static_cast<std::size_t>(size);
            auto value = std::move(*loaded.get_if());
            if (value.tick != world.tick_) {
                return corrupt();
            }
            EconomyState state;
            state.root = std::move(value.root);
            state.real_economy = std::move(value.real_economy_runtime);
            state.monetary = std::move(value.monetary_runtime);
            state.financial = std::move(value.financial_runtime);
            state.population = std::move(value.population_runtime);
            state.domestic = std::move(value.runtime);
            state.tick = value.tick;
            state.real_economy_scratch.reserve(state.root);
            state.monetary_scratch.reserve(state.root);
            state.financial_scratch.reserve(state.root, state.financial);
            state.population_scratch.reserve(state.population);
            state.domestic_scratch.reserve(state.root, state.domestic);
            world.last_metrics_.domestic.push_back(state.domestic.last_metrics);
            world.economies_.push_back(std::move(state));
        }
        if (position != payload.size() ||
            world.last_metrics_.external.size() != world.economies_.size()) {
            return corrupt();
        }
        const auto status = world.validate();
        if (!status.ok()) {
            return corrupt();
        }
        return world;
    } catch (...) {
        return corrupt();
    }
}

} // namespace macro_sim::simulation
