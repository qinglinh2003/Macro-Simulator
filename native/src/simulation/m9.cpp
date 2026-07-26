#include "macro_sim/simulation/m9.hpp"

#include "macro_sim/core/transaction.hpp"

#include <algorithm>
#include <atomic>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numeric>
#include <span>
#include <thread>
#include <utility>

namespace macro_sim::simulation {
namespace {

constexpr double kEpsilon = 1.0e-12;
constexpr double kTolerance = 1.0e-8;
constexpr std::uint64_t kFnvOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFnvPrime = 1099511628211ULL;

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

template <typename Value>
[[nodiscard]] std::uint64_t capacity_bytes(const std::vector<Value> &values) noexcept {
    return static_cast<std::uint64_t>(values.capacity()) * sizeof(Value);
}

template <typename Value>
[[nodiscard]] std::uint64_t
nested_capacity_bytes(const std::vector<std::vector<Value>> &values) noexcept {
    std::uint64_t bytes = capacity_bytes(values);
    for (const auto &row : values) {
        bytes += capacity_bytes(row);
    }
    return bytes;
}

[[nodiscard]] bool valid_economy(EconomyId economy, std::size_t count) noexcept {
    return economy.valid() && economy.value() < count;
}

[[nodiscard]] bool valid_fault(M9FaultPoint point) noexcept {
    return static_cast<std::uint8_t>(point) <=
           static_cast<std::uint8_t>(M9FaultPoint::before_world_commit);
}

[[nodiscard]] bool valid_kind(ShockKind kind) noexcept {
    return static_cast<std::uint8_t>(kind) <=
           static_cast<std::uint8_t>(ShockKind::capital_destruction);
}

[[nodiscard]] bool valid_shape(ShockShape shape) noexcept {
    return static_cast<std::uint8_t>(shape) <=
           static_cast<std::uint8_t>(ShockShape::triangular);
}

[[nodiscard]] bool valid_sector(ShockSector sector) noexcept {
    return static_cast<std::uint8_t>(sector) <=
           static_cast<std::uint8_t>(ShockSector::public_sector);
}

[[nodiscard]] bool valid_event_type(ShockEventType type) noexcept {
    return static_cast<std::uint8_t>(type) <=
           static_cast<std::uint8_t>(ShockEventType::realized);
}

[[nodiscard]] double clamp_nonnegative(double value) noexcept {
    return std::max(0.0, value);
}

[[nodiscard]] double shock_progress(const ShockSpec &shock, Tick tick) noexcept {
    if (tick.value() < shock.start.value() ||
        tick.value() >= shock.start.value() + shock.duration) {
        return 0.0;
    }
    const auto elapsed = tick.value() - shock.start.value();
    if (shock.ramp_in_ticks > 0U || shock.ramp_out_ticks > 0U) {
        double intensity = 1.0;
        if (shock.ramp_in_ticks > 0U) {
            intensity =
                std::min(intensity, static_cast<double>(elapsed + 1U) /
                                        static_cast<double>(shock.ramp_in_ticks));
        }
        if (shock.ramp_out_ticks > 0U) {
            const auto remaining = shock.start.value() + shock.duration - tick.value();
            intensity =
                std::min(intensity, static_cast<double>(remaining) /
                                        static_cast<double>(shock.ramp_out_ticks));
        }
        return std::clamp(intensity, 0.0, 1.0);
    }
    if (shock.shape == ShockShape::step || shock.duration <= 1U) {
        return 1.0;
    }
    if (shock.shape == ShockShape::linear) {
        return static_cast<double>(elapsed + 1U) / static_cast<double>(shock.duration);
    }
    const double position =
        static_cast<double>(elapsed) /
        static_cast<double>(std::max<std::uint64_t>(1U, shock.duration - 1U));
    return 1.0 - std::abs(2.0 * position - 1.0);
}

[[nodiscard]] double shock_factor(std::span<const ShockSpec> shocks, ShockKind kind,
                                  std::size_t economy, Tick tick,
                                  std::optional<ShockSector> sector = std::nullopt,
                                  std::uint64_t *active = nullptr) noexcept {
    double result = 1.0;
    for (const auto &shock : shocks) {
        if (shock.kind != kind ||
            (shock.economy.has_value() && shock.economy->value() != economy) ||
            (shock.sector.has_value() && shock.sector != sector)) {
            continue;
        }
        const double progress = shock_progress(shock, tick);
        if (progress <= 0.0) {
            continue;
        }
        result *= std::max(0.0, 1.0 - shock.magnitude * progress);
        if (active != nullptr) {
            ++*active;
        }
    }
    return result;
}

[[nodiscard]] double country_price(const M8Metrics &metrics) noexcept {
    const double price = metrics.economy.economy.economy.economy.price_index;
    return finite(price) && price > kEpsilon ? price : 1.0;
}

[[nodiscard]] double country_output(const M8Metrics &metrics) noexcept {
    return clamp_nonnegative(metrics.economy.economy.economy.economy.real_output);
}

[[nodiscard]] double country_wage(const M8Metrics &metrics) noexcept {
    const double wage = metrics.economy.mean_hourly_wage;
    return finite(wage) && wage > kEpsilon ? wage : 1.0;
}

[[nodiscard]] double policy_rate(const M8Metrics &metrics) noexcept {
    const double rate = metrics.economy.economy.economy.policy_rate;
    return finite(rate) ? rate : 0.0;
}

void hash_mix(std::uint64_t &hash, std::uint64_t value) noexcept {
    hash ^= value;
    hash *= kFnvPrime;
}

void hash_mix(std::uint64_t &hash, double value) noexcept {
    hash_mix(hash, std::bit_cast<std::uint64_t>(value));
}

[[nodiscard]] bool contains_id(std::span<const EconomyId> values,
                               EconomyId needle) noexcept {
    return std::binary_search(values.begin(), values.end(), needle);
}

} // namespace

double RateVector::rate(EconomyId economy) const noexcept {
    if (!valid_economy(economy, log_rates.size())) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return std::exp(log_rates[static_cast<std::size_t>(economy.value())]);
}

double RateVector::bilateral(EconomyId destination, EconomyId source) const noexcept {
    if (!valid_economy(destination, log_rates.size()) ||
        !valid_economy(source, log_rates.size())) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return std::exp(log_rates[static_cast<std::size_t>(destination.value())] -
                    log_rates[static_cast<std::size_t>(source.value())]);
}

double RateVector::to_numeraire(double amount, EconomyId economy) const noexcept {
    const double local_rate = rate(economy);
    return finite(local_rate) && local_rate > kEpsilon ? amount / local_rate : 0.0;
}

void RateVector::normalize() noexcept {
    if (log_rates.empty()) {
        return;
    }
    const double mean = std::accumulate(log_rates.begin(), log_rates.end(), 0.0) /
                        static_cast<double>(log_rates.size());
    for (auto &value : log_rates) {
        value -= mean;
    }
}

M9World::EconomyState::EconomyState(const EconomyState &other)
    : root(other.root), real_economy(other.real_economy), monetary(other.monetary),
      financial(other.financial), population(other.population),
      domestic(other.domestic), tick(other.tick) {
    real_economy_scratch.reserve(root);
    monetary_scratch.reserve(root);
    financial_scratch.reserve(root, financial);
    population_scratch.reserve(population);
    domestic_scratch.reserve(root, domestic);
}

M9World::EconomyState &M9World::EconomyState::operator=(const EconomyState &other) {
    if (this == &other) {
        return *this;
    }
    EconomyState replacement(other);
    *this = std::move(replacement);
    return *this;
}

Status validate_external_policy(const ExternalPolicyState &policy,
                                std::size_t economy_count, EconomyId owner) noexcept {
    if (!finite(policy.tariff) || policy.tariff <= -1.0 ||
        !finite(policy.export_subsidy) || policy.export_subsidy >= 1.0 ||
        !finite(policy.capital_control) || policy.capital_control < 0.0 ||
        policy.capital_control > 1.0 ||
        !finite(policy.external_interest_settlement_fraction) ||
        policy.external_interest_settlement_fraction < 0.0 ||
        policy.external_interest_settlement_fraction > 1.0 ||
        !finite(policy.remittance_tax) || policy.remittance_tax < 0.0 ||
        policy.remittance_tax > 1.0 || !finite(policy.outward_remittance_tax) ||
        policy.outward_remittance_tax < 0.0 || policy.outward_remittance_tax > 1.0 ||
        !finite(policy.guest_worker_return) || policy.guest_worker_return < 0.0 ||
        policy.guest_worker_return > 1.0 || !finite(policy.peg_reserve_scale) ||
        policy.peg_reserve_scale <= 0.0) {
        return Status(ErrorCode::invalid_argument, "invalid external policy scalar");
    }
    const auto valid_optional_share = [](const std::optional<double> &value) {
        return !value.has_value() || (finite(*value) && *value >= 0.0 && *value <= 1.0);
    };
    if (!valid_optional_share(policy.import_quota) ||
        !valid_optional_share(policy.immigration_cap) ||
        !valid_optional_share(policy.emigration_cap)) {
        return Status(ErrorCode::invalid_argument,
                      "invalid external policy optional share");
    }
    if (static_cast<std::uint8_t>(policy.fx_regime) >
        static_cast<std::uint8_t>(FxRegime::peg)) {
        return Status(ErrorCode::invalid_argument, "invalid FX regime");
    }
    EconomyId previous{};
    bool first = true;
    for (const auto target : policy.sanctions_imposed_on) {
        if (!valid_economy(target, economy_count) || target == owner ||
            (!first && !(previous < target))) {
            return Status(ErrorCode::invalid_argument,
                          "sanction targets must be sorted and unique");
        }
        previous = target;
        first = false;
    }
    if (policy.fx_regime == FxRegime::peg) {
        if (!policy.peg_anchor.has_value() ||
            !valid_economy(*policy.peg_anchor, economy_count) ||
            *policy.peg_anchor == owner) {
            return Status(ErrorCode::invalid_argument,
                          "peg requires a distinct valid anchor");
        }
    } else if (policy.peg_anchor.has_value()) {
        return Status(ErrorCode::invalid_argument,
                      "floating regime cannot define a peg anchor");
    }
    return Status::success();
}

Status validate_world_rules(const WorldRules &rules) noexcept {
    if (!finite(rules.fx_adjustment) || rules.fx_adjustment < 0.0 ||
        !finite(rules.fx_friction) || rules.fx_friction < 0.0 ||
        !finite(rules.fx_spread) || rules.fx_spread < 0.0 || rules.fx_spread >= 0.1 ||
        !finite(rules.fx_trade_cap) || rules.fx_trade_cap < 0.0 ||
        rules.fx_trade_cap > 1.0 || !finite(rules.capital_mobility) ||
        rules.capital_mobility < 0.0 || rules.capital_mobility > 1.0 ||
        !finite(rules.capital_adjustment) || rules.capital_adjustment < 0.0 ||
        rules.capital_adjustment > 1.0 || !finite(rules.periods_per_year) ||
        rules.periods_per_year <= 0.0 || !finite(rules.migration_rate) ||
        rules.migration_rate < 0.0 || rules.migration_rate > 1.0 ||
        !finite(rules.migration_max_share) || rules.migration_max_share < 0.0 ||
        rules.migration_max_share > 1.0 || !finite(rules.remittance_share) ||
        rules.remittance_share < 0.0 || rules.remittance_share > 1.0 ||
        !finite(rules.wage_smoothing) || rules.wage_smoothing < 0.0 ||
        rules.wage_smoothing > 1.0 || !finite(rules.initial_peg_reserves) ||
        rules.initial_peg_reserves < 0.0 ||
        rules.dense_edge_threshold != kM9DenseEdgeThreshold) {
        return Status(ErrorCode::invalid_argument, "invalid World rules");
    }
    if ((rules.capital || rules.migration) && !rules.trade) {
        return Status(ErrorCode::invalid_argument,
                      "capital and migration require the World FX layer");
    }
    return Status::success();
}

Status validate_shock_spec(const ShockSpec &shock, std::size_t economy_count) noexcept {
    if (shock.id == 0U || !valid_kind(shock.kind) || !valid_shape(shock.shape) ||
        shock.duration == 0U || !finite(shock.magnitude) || shock.magnitude < -3.0 ||
        shock.magnitude > 0.99 ||
        (shock.economy.has_value() && !valid_economy(*shock.economy, economy_count)) ||
        (shock.sector.has_value() && !valid_sector(*shock.sector))) {
        return Status(ErrorCode::invalid_argument, "invalid shock specification");
    }
    const bool sector_allowed = shock.kind == ShockKind::productivity ||
                                shock.kind == ShockKind::labor_availability ||
                                shock.kind == ShockKind::energy_capacity ||
                                shock.kind == ShockKind::capital_destruction;
    if (shock.sector.has_value() && !sector_allowed) {
        return Status(ErrorCode::invalid_argument,
                      "shock kind does not accept a sector target");
    }
    if (shock.kind == ShockKind::energy_capacity && shock.sector.has_value() &&
        *shock.sector != ShockSector::energy) {
        return Status(ErrorCode::invalid_argument,
                      "energy capacity only accepts the energy sector");
    }
    if (shock.start.value() >
            std::numeric_limits<std::uint64_t>::max() - shock.duration ||
        shock.ramp_in_ticks > shock.duration ||
        shock.ramp_out_ticks > shock.duration - shock.ramp_in_ticks) {
        return Status(ErrorCode::invalid_argument,
                      "shock timing exceeds the supported range");
    }
    if (shock.kind == ShockKind::capital_destruction &&
        (shock.magnitude < 0.0 || shock.duration != 1U ||
         shock.shape != ShockShape::step || shock.ramp_in_ticks != 0U ||
         shock.ramp_out_ticks != 0U)) {
        return Status(ErrorCode::invalid_argument,
                      "capital destruction must be a one-tick adverse step");
    }
    if (shock.announcement.has_value() &&
        shock.announcement->value() > shock.start.value()) {
        return Status(ErrorCode::invalid_argument,
                      "shock announcement cannot follow its start");
    }
    return Status::success();
}

Result<std::vector<ShockSpec>>
make_crisis_scenario(CrisisScenario scenario, const CrisisScenarioOptions &options,
                     std::size_t economy_count) {
    if (economy_count == 0U || options.first_shock_id == 0U ||
        !finite(options.capital_loss) || options.capital_loss < 0.0 ||
        options.capital_loss > 0.99 ||
        static_cast<std::uint8_t>(scenario) >
            static_cast<std::uint8_t>(CrisisScenario::natural_disaster)) {
        return Status(ErrorCode::invalid_argument, "invalid crisis scenario options");
    }
    auto targets = options.economies;
    std::sort(targets.begin(), targets.end());
    if (std::adjacent_find(targets.begin(), targets.end()) != targets.end() ||
        std::any_of(targets.begin(), targets.end(), [economy_count](EconomyId economy) {
            return !valid_economy(economy, economy_count);
        })) {
        return Status(ErrorCode::invalid_argument,
                      "invalid crisis scenario economy targets");
    }
    const auto announcement =
        Tick(options.start.value() > options.announcement_lead_ticks
                 ? options.start.value() - options.announcement_lead_ticks
                 : 0U);
    std::vector<ShockSpec> shocks;
    std::uint64_t next_id = options.first_shock_id;
    auto append = [&](ShockKind kind, double magnitude, std::uint64_t duration,
                      std::uint64_t ramp_out,
                      std::optional<ShockSector> sector =
                          std::nullopt) mutable -> Status {
        auto append_one = [&](std::optional<EconomyId> economy) mutable -> Status {
            if (next_id == std::numeric_limits<std::uint64_t>::max()) {
                return Status(ErrorCode::out_of_range,
                              "crisis scenario shock IDs overflow");
            }
            ShockSpec shock;
            shock.id = next_id++;
            shock.kind = kind;
            shock.economy = economy;
            shock.start = options.start;
            shock.announcement = announcement;
            shock.duration = duration;
            shock.magnitude = magnitude;
            shock.ramp_out_ticks = ramp_out;
            shock.sector = sector;
            auto status = validate_shock_spec(shock, economy_count);
            if (!status.ok()) {
                return status;
            }
            shocks.push_back(std::move(shock));
            return Status::success();
        };
        if (targets.empty()) {
            return append_one(std::nullopt);
        }
        for (const auto economy : targets) {
            auto status = append_one(economy);
            if (!status.ok()) {
                return status;
            }
        }
        return Status::success();
    };

    const auto configured_duration = [duration =
                                          options.duration](std::uint64_t fallback) {
        return duration == 0U ? fallback : duration;
    };
    Status status = Status::success();
    switch (scenario) {
    case CrisisScenario::oil_embargo: {
        const auto duration = configured_duration(180U);
        status =
            append(ShockKind::energy_capacity, 0.45, duration, 0U, ShockSector::energy);
        if (status.ok()) {
            status = append(ShockKind::import_capacity, 0.20, duration, 0U);
        }
        break;
    }
    case CrisisScenario::global_financial_crisis: {
        const auto duration = configured_duration(365U);
        const auto ramp_out = std::min<std::uint64_t>(90U, duration / 3U);
        status = append(ShockKind::credit_supply, 0.70, duration, ramp_out);
        if (status.ok()) {
            status = append(ShockKind::household_demand, 0.18, duration, ramp_out);
        }
        if (status.ok()) {
            status = append(ShockKind::productivity, 0.05, duration, ramp_out);
        }
        break;
    }
    case CrisisScenario::pandemic: {
        const auto duration = configured_duration(540U);
        const auto ramp_out = std::min<std::uint64_t>(180U, duration / 3U);
        for (const auto& [kind, magnitude] :
             {std::pair{ShockKind::labor_availability, 0.25},
              std::pair{ShockKind::productivity, 0.12},
              std::pair{ShockKind::household_demand, 0.16},
              std::pair{ShockKind::credit_supply, 0.12}}) {
            status = append(kind, magnitude, duration, ramp_out);
            if (!status.ok()) {
                break;
            }
        }
        if (status.ok() && options.include_trade) {
            status = append(ShockKind::import_capacity, 0.30, duration, ramp_out);
        }
        if (status.ok() && options.include_trade) {
            status = append(ShockKind::export_capacity, 0.25, duration, ramp_out);
        }
        break;
    }
    case CrisisScenario::natural_disaster: {
        const auto recovery = configured_duration(180U);
        status = append(ShockKind::capital_destruction, options.capital_loss, 1U, 0U);
        if (status.ok()) {
            status = append(ShockKind::productivity, 0.15, recovery,
                            std::min<std::uint64_t>(90U, recovery / 2U));
        }
        const auto labor_duration = std::min<std::uint64_t>(30U, recovery);
        if (status.ok()) {
            status = append(ShockKind::labor_availability, 0.10, labor_duration,
                            std::min<std::uint64_t>(10U, labor_duration / 3U));
        }
        break;
    }
    }
    if (!status.ok()) {
        return status;
    }
    return shocks;
}

Result<M9World> M9World::create(const M9WorldSpec &spec) {
    if (spec.economies.empty() || spec.economies.size() > kM9MaximumEconomies) {
        return Status(ErrorCode::invalid_argument,
                      "M9 World economy count is outside the supported range");
    }
    auto rules_status = validate_world_rules(spec.rules);
    if (!rules_status.ok()) {
        return rules_status;
    }
    if (!spec.external_policies.empty() &&
        spec.external_policies.size() != spec.economies.size()) {
        return Status(ErrorCode::invalid_argument,
                      "external policy count must match economy count");
    }

    M9World world;
    world.rules_ = spec.rules;
    world.rates_.log_rates.assign(spec.economies.size(), 0.0);
    world.dealer_inventory_.assign(spec.economies.size(), 0.0);
    world.external_principal_.assign(spec.economies.size(),
                                     std::vector<double>(spec.economies.size(), 0.0));
    world.interest_arrears_ = world.external_principal_;
    world.smoothed_real_wages_.assign(spec.economies.size(), 1.0);
    world.external_policies_ = spec.external_policies;
    if (world.external_policies_.empty()) {
        world.external_policies_.resize(spec.economies.size());
    }
    auto policy_status = world.validate_policy_vector(world.external_policies_);
    if (!policy_status.ok()) {
        return policy_status;
    }

    world.economies_.reserve(spec.economies.size());
    for (std::size_t index = 0; index < spec.economies.size(); ++index) {
        auto domestic_spec = spec.economies[index];
        auto &m4 = domestic_spec.domestic_economy.financial_economy.monetary_economy
                       .real_economy;
        m4.economy = EconomyId(static_cast<std::uint64_t>(index));
        m4.currency = CurrencyId(static_cast<std::uint32_t>(index));
        auto built = build_m8_genesis(domestic_spec);
        if (!built.ok()) {
            return built.status();
        }
        auto initialization = std::move(built).take();
        EconomyState state;
        state.root = std::move(initialization.root);
        state.real_economy = std::move(initialization.real_economy_runtime);
        state.monetary = std::move(initialization.monetary_runtime);
        state.financial = std::move(initialization.financial_runtime);
        state.population = std::move(initialization.population_runtime);
        state.domestic = std::move(initialization.runtime);
        state.tick = Tick(0);
        state.real_economy_scratch.reserve(state.root);
        state.monetary_scratch.reserve(state.root);
        state.financial_scratch.reserve(state.root, state.financial);
        state.population_scratch.reserve(state.population);
        state.domestic_scratch.reserve(state.root, state.domestic);
        world.economies_.push_back(std::move(state));
    }

    for (std::size_t index = 0; index < world.external_policies_.size(); ++index) {
        const auto &policy = world.external_policies_[index];
        if (policy.fx_regime == FxRegime::peg) {
            world.pegs_.push_back(PegRuntime{
                EconomyId(static_cast<std::uint64_t>(index)),
                *policy.peg_anchor,
                world.rules_.initial_peg_reserves,
                0.0,
                0.0,
                true,
            });
        }
    }
    world.shocks_ = spec.shocks;
    std::sort(world.shocks_.begin(), world.shocks_.end(),
              [](const ShockSpec &left, const ShockSpec &right) {
                  return left.id < right.id;
              });
    for (std::size_t index = 0; index < world.shocks_.size(); ++index) {
        auto shock_status =
            validate_shock_spec(world.shocks_[index], world.economies_.size());
        if (!shock_status.ok()) {
            return shock_status;
        }
        if (index > 0U && world.shocks_[index - 1U].id == world.shocks_[index].id) {
            return Status(ErrorCode::already_exists, "duplicate shock ID");
        }
    }
    world.last_metrics_.domestic.resize(world.economies_.size());
    world.last_metrics_.external.resize(world.economies_.size());
    auto state_status = world.validate();
    if (!state_status.ok()) {
        return state_status;
    }
    return world;
}

const core::RootState *M9World::economy_root(EconomyId economy) const noexcept {
    return valid_economy(economy, economies_.size())
               ? &economies_[static_cast<std::size_t>(economy.value())].root
               : nullptr;
}

const M6Runtime *
M9World::economy_financial_runtime(EconomyId economy) const noexcept {
    return valid_economy(economy, economies_.size())
               ? &economies_[static_cast<std::size_t>(economy.value())].financial
               : nullptr;
}

const M7Runtime *
M9World::economy_population_runtime(EconomyId economy) const noexcept {
    return valid_economy(economy, economies_.size())
               ? &economies_[static_cast<std::size_t>(economy.value())].population
               : nullptr;
}

const M8Runtime *M9World::economy_runtime(EconomyId economy) const noexcept {
    return valid_economy(economy, economies_.size())
               ? &economies_[static_cast<std::size_t>(economy.value())].domestic
               : nullptr;
}

M9MemoryUsage M9World::memory_usage() const noexcept {
    M9MemoryUsage usage;
    for (const auto &economy : economies_) {
        const auto &root = economy.root;
        usage.root_state += root.households.retained_bytes() +
                            root.firms.retained_bytes() + root.banks.retained_bytes() +
                            capacity_bytes(root.postings.records()) +
                            capacity_bytes(root.reserves.records()) +
                            capacity_bytes(root.loans.records()) +
                            capacity_bytes(root.interbank.records()) +
                            capacity_bytes(root.central_bank_operations.records()) +
                            capacity_bytes(root.bank_pnl.records()) +
                            capacity_bytes(root.bank_capital.records()) +
                            capacity_bytes(root.ownership.records()) +
                            capacity_bytes(root.named_counters.records());

        const auto &real = economy.real_economy_scratch;
        usage.real_economy_scratch +=
            capacity_bytes(real.household_ids_) +
            capacity_bytes(real.household_dense_index_) +
            capacity_bytes(real.firm_ids_) + capacity_bytes(real.firm_dense_index_) +
            capacity_bytes(real.consumption_firm_indices_) +
            capacity_bytes(real.capital_firm_indices_) +
            capacity_bytes(real.energy_firm_indices_) +
            capacity_bytes(real.construction_firm_indices_) +
            capacity_bytes(real.household_order_) + capacity_bytes(real.firm_order_) +
            capacity_bytes(real.balances_) + capacity_bytes(real.account_nodes_) +
            capacity_bytes(real.account_flags_) +
            capacity_bytes(real.reserve_balances_) +
            capacity_bytes(real.reserve_minimum_) +
            capacity_bytes(real.household_work_) + capacity_bytes(real.firm_work_) +
            capacity_bytes(real.orders_) + capacity_bytes(real.offers_) +
            capacity_bytes(real.market_buyer_order_) +
            capacity_bytes(real.market_active_offers_) +
            capacity_bytes(real.market_offer_remaining_) +
            capacity_bytes(real.clearing_.trades) +
            capacity_bytes(real.clearing_.allocations) +
            capacity_bytes(real.clearing_.stock_commands) +
            capacity_bytes(real.phase_trace_);

        const auto &monetary = economy.monetary_scratch;
        usage.monetary_scratch += capacity_bytes(monetary.loans_) +
                                  capacity_bytes(monetary.interbank_) +
                                  capacity_bytes(monetary.central_bank_operations_) +
                                  capacity_bytes(monetary.bank_pnl_) +
                                  capacity_bytes(monetary.bank_capital_) +
                                  capacity_bytes(monetary.debt_by_account_) +
                                  capacity_bytes(
                                      monetary.reusable_loan_by_account_) +
                                  capacity_bytes(
                                      monetary.relationship_loan_by_account_) +
                                  capacity_bytes(monetary.exposure_by_bank_) +
                                  capacity_bytes(monetary.deposits_by_bank_) +
                                  capacity_bytes(monetary.bank_capital_live_) +
                                  capacity_bytes(monetary.bank_alive_) +
                                  capacity_bytes(monetary.bank_by_node_) +
                                  capacity_bytes(monetary.firm_index_by_id_) +
                                  capacity_bytes(monetary.household_order_) +
                                  capacity_bytes(monetary.candidate_banks_) +
                                  capacity_bytes(monetary.alive_banks_) +
                                  capacity_bytes(monetary.failed_banks_);

        const auto &financial = economy.financial;
        usage.financial_runtime += financial.securities.memory_usage().total() +
                                   capacity_bytes(financial.firms) +
                                   capacity_bytes(financial.watchlist_rows) +
                                   capacity_bytes(financial.watchlist_equities) +
                                   capacity_bytes(financial.margin_loans);
        const auto &financial_scratch = economy.financial_scratch;
        usage.financial_scratch +=
            financial_scratch.securities_.memory_usage().total() +
            capacity_bytes(financial_scratch.firms_) +
            capacity_bytes(financial_scratch.orders_) +
            capacity_bytes(financial_scratch.ordered_orders_) +
            capacity_bytes(financial_scratch.order_bucket_offsets_) +
            capacity_bytes(financial_scratch.buyers_) +
            capacity_bytes(financial_scratch.sellers_) +
            capacity_bytes(financial_scratch.bank_equities_) +
            capacity_bytes(financial_scratch.bond_demands_) +
            capacity_bytes(financial_scratch.watch_current_) +
            capacity_bytes(financial_scratch.watch_attractiveness_) +
            capacity_bytes(financial_scratch.equity_buy_commitments_) +
            capacity_bytes(financial_scratch.margin_loans_) +
            capacity_bytes(financial_scratch.margin_loan_heads_) +
            capacity_bytes(financial_scratch.margin_loan_tails_) +
            capacity_bytes(financial_scratch.margin_loan_next_) +
            capacity_bytes(financial_scratch.debt_by_account_) +
            capacity_bytes(financial_scratch.margin_by_account_) +
            capacity_bytes(financial_scratch.firm_return_) +
            capacity_bytes(financial_scratch.firm_exits_) +
            capacity_bytes(financial_scratch.firm_entries_) +
            capacity_bytes(financial_scratch.bank_entries_);

        const auto &population = economy.population;
        usage.person_store += population.persons.retained_bytes();
        usage.household_membership += population.membership.retained_bytes();
        const auto beneficial_memory = population.beneficial_ownership.memory_usage();
        usage.beneficial_lots += beneficial_memory.lots;
        usage.beneficial_indexes +=
            beneficial_memory.asset_indexes + beneficial_memory.person_indexes +
            beneficial_memory.query_indexes + beneficial_memory.validation_scratch;
        const auto employment_bytes = population.employment.retained_bytes();
        const auto relationship_bytes = population.relationships.retained_bytes();
        usage.employment += employment_bytes;
        usage.relationships += relationship_bytes;
        usage.social_labor += employment_bytes + relationship_bytes;
        usage.population_scratch +=
            capacity_bytes(economy.population_scratch.opening_alive_) +
            capacity_bytes(economy.population_scratch.guardian_heads_) +
            capacity_bytes(economy.population_scratch.guardian_next_) +
            capacity_bytes(economy.population_scratch.deceased_lots_) +
            capacity_bytes(economy.population_scratch.beneficial_assets_) +
            capacity_bytes(economy.population_scratch.estate_securities_) +
            capacity_bytes(economy.population_scratch.labor_candidates_) +
            capacity_bytes(economy.population_scratch.second_job_candidates_) +
            capacity_bytes(economy.population_scratch.ladder_candidates_) +
            capacity_bytes(economy.population_scratch.ladder_firms_) +
            capacity_bytes(economy.population_scratch.divorce_candidates_) +
            capacity_bytes(economy.population_scratch.fertility_candidates_) +
            capacity_bytes(economy.population_scratch.kin_households_) +
            capacity_bytes(economy.population_scratch.retired_households_) +
            capacity_bytes(economy.population_scratch.household_work_index_) +
            capacity_bytes(economy.population_scratch.roster_buffer_) +
            capacity_bytes(economy.population_scratch.firm_target_ema_) +
            capacity_bytes(economy.population_scratch.estates_) +
            capacity_bytes(economy.population_scratch.leaving_home_) +
            capacity_bytes(economy.population_scratch.pending_leaving_home_) +
            economy.population_scratch.persons_.retained_bytes() +
            economy.population_scratch.membership_.retained_bytes() +
            economy.population_scratch.beneficial_ownership_.memory_usage().total() +
            economy.population_scratch.employment_.retained_bytes() +
            economy.population_scratch.relationships_.retained_bytes();

        const auto &domestic = economy.domestic;
        usage.housing_registry += domestic.properties.retained_bytes();
        usage.domestic_runtime += capacity_bytes(domestic.energy_producers) +
                                  capacity_bytes(domestic.energy_inputs) +
                                  capacity_bytes(domestic.household_energy) +
                                  capacity_bytes(domestic.housing_listings) +
                                  capacity_bytes(domestic.mortgages) +
                                  capacity_bytes(domestic.tenancies) +
                                  capacity_bytes(domestic.builders);
        const auto &domestic_scratch = economy.domestic_scratch;
        usage.domestic_scratch +=
            capacity_bytes(domestic_scratch.energy_producers_) +
            capacity_bytes(domestic_scratch.energy_inputs_) +
            capacity_bytes(domestic_scratch.household_energy_) +
            capacity_bytes(domestic_scratch.orders_) +
            capacity_bytes(domestic_scratch.offers_) +
            capacity_bytes(domestic_scratch.buyer_order_) +
            capacity_bytes(domestic_scratch.seller_order_) +
            capacity_bytes(domestic_scratch.industry_use_need_) +
            capacity_bytes(domestic_scratch.household_consumption_) +
            capacity_bytes(domestic_scratch.opening_balances_) +
            capacity_bytes(domestic_scratch.housing_listings_) +
            capacity_bytes(domestic_scratch.mortgages_) +
            capacity_bytes(domestic_scratch.tenancies_) +
            capacity_bytes(domestic_scratch.builders_);
        if (domestic_scratch.staged_properties_.has_value()) {
            usage.domestic_scratch +=
                domestic_scratch.staged_properties_->retained_bytes();
        }
    }

    usage.world =
        capacity_bytes(economies_) + capacity_bytes(external_policies_) +
        capacity_bytes(rates_.log_rates) + capacity_bytes(dealer_inventory_) +
        nested_capacity_bytes(external_principal_) +
        nested_capacity_bytes(interest_arrears_) + capacity_bytes(pegs_) +
        capacity_bytes(migration_routes_) + capacity_bytes(shocks_) +
        capacity_bytes(announced_shock_ids_) + capacity_bytes(active_shock_ids_) +
        capacity_bytes(realized_shock_ids_) + capacity_bytes(shock_events_) +
        capacity_bytes(trade_reservations_) + capacity_bytes(smoothed_real_wages_) +
        capacity_bytes(last_metrics_.domestic) + capacity_bytes(last_metrics_.external);
    return usage;
}

Status M9World::validate_policy_vector(
    std::span<const ExternalPolicyState> policies) const noexcept {
    if (policies.size() != economies_.size() && !economies_.empty()) {
        return Status(ErrorCode::invalid_argument,
                      "external policy count must match economy count");
    }
    std::size_t peg_count = 0;
    for (std::size_t index = 0; index < policies.size(); ++index) {
        auto status =
            validate_external_policy(policies[index], policies.size(),
                                     EconomyId(static_cast<std::uint64_t>(index)));
        if (!status.ok()) {
            return status;
        }
        if (policies[index].fx_regime == FxRegime::peg) {
            ++peg_count;
            const auto anchor =
                static_cast<std::size_t>(policies[index].peg_anchor->value());
            if (policies[anchor].fx_regime != FxRegime::floating) {
                return Status(ErrorCode::contract_violation, "peg anchor must float");
            }
        }
    }
    if (peg_count > 1U) {
        return Status(ErrorCode::unsupported, "M9 P0 permits at most one pegger");
    }
    return Status::success();
}

Status
M9World::update_external_policies(std::span<const ExternalPolicyState> policies) {
    auto status = validate_policy_vector(policies);
    if (!status.ok()) {
        return status;
    }
    auto next = std::vector<ExternalPolicyState>(policies.begin(), policies.end());
    std::vector<PegRuntime> next_pegs;
    for (std::size_t index = 0; index < next.size(); ++index) {
        if (next[index].fx_regime != FxRegime::peg) {
            continue;
        }
        const auto existing =
            std::find_if(pegs_.begin(), pegs_.end(), [index](const PegRuntime &peg) {
                return peg.pegger.value() == index;
            });
        if (existing != pegs_.end() && existing->anchor == *next[index].peg_anchor) {
            next_pegs.push_back(*existing);
        } else {
            next_pegs.push_back(PegRuntime{
                EconomyId(static_cast<std::uint64_t>(index)),
                *next[index].peg_anchor,
                rules_.initial_peg_reserves,
                0.0,
                rates_.log_rates[index] - rates_.log_rates[static_cast<std::size_t>(
                                              next[index].peg_anchor->value())],
                true,
            });
        }
    }
    external_policies_ = std::move(next);
    pegs_ = std::move(next_pegs);
    return Status::success();
}

Status M9World::schedule_shock(const ShockSpec &shock) {
    auto status = validate_shock_spec(shock, economies_.size());
    if (!status.ok()) {
        return status;
    }
    if (shock.start.value() < tick_.value()) {
        return Status(ErrorCode::invalid_argument,
                      "cannot schedule a shock in the past");
    }
    const Tick announcement = shock.announcement.value_or(shock.start);
    if (announcement.value() < tick_.value()) {
        return Status(ErrorCode::invalid_argument,
                      "cannot backdate a shock announcement");
    }
    const auto position = std::lower_bound(
        shocks_.begin(), shocks_.end(), shock.id,
        [](const ShockSpec &candidate, std::uint64_t id) { return candidate.id < id; });
    if (position != shocks_.end() && position->id == shock.id) {
        return Status(ErrorCode::already_exists, "duplicate shock ID");
    }
    shocks_.insert(position, shock);
    return Status::success();
}

bool M9World::sanctioned(std::size_t first, std::size_t second) const noexcept {
    if (first >= external_policies_.size() || second >= external_policies_.size()) {
        return true;
    }
    const auto first_target = EconomyId(static_cast<std::uint64_t>(second));
    const auto second_target = EconomyId(static_cast<std::uint64_t>(first));
    return contains_id(external_policies_[first].sanctions_imposed_on, first_target) ||
           contains_id(external_policies_[second].sanctions_imposed_on, second_target);
}

Result<M9AdvanceResult> M9World::advance(std::uint64_t count,
                                         const M9AdvanceOptions &options) {
    if (!valid_fault(options.fault_point) || options.worker_count == 0U ||
        (!options.domestic.empty() && options.domestic.size() != economies_.size())) {
        return Status(ErrorCode::invalid_argument, "invalid M9 advance options");
    }
    const Tick first = tick_;
    for (std::uint64_t offset = 0; offset < count; ++offset) {
        auto status = advance_one(options);
        if (!status.ok()) {
            return status;
        }
    }
    return M9AdvanceResult{
        first, tick_, count, last_metrics_, digest(),
    };
}

Status M9World::advance_one(const M9AdvanceOptions &options) {
    if (economies_.size() == 1U && !rules_.trade && shocks_.empty() &&
        options.fault_point == M9FaultPoint::none) {
        auto domestic_options =
            options.domestic.empty() ? M8AdvanceOptions{} : options.domestic.front();
        auto &m4_options = domestic_options.base.base.base.base;
        m4_options.memory_efficient_staging = true;
        if (options.domestic.empty() &&
            !options.require_world_rollback) {
            m4_options.validate_preconditions = false;
            m4_options.audit_extended_state = false;
        }
        auto &economy = economies_.front();
        auto result = advance_m8_ticks(
            economy.root, economy.real_economy, economy.real_economy_scratch,
            economy.monetary, economy.monetary_scratch, economy.financial,
            economy.financial_scratch, economy.population,
            economy.population_scratch, economy.domestic,
            economy.domestic_scratch, economy.tick, 1U, domestic_options);
        if (!result.ok()) {
            return result.status();
        }
        last_metrics_ = {};
        last_metrics_.domestic.push_back(result.get_if()->metrics);
        last_metrics_.external.resize(1U);
        last_metrics_.external.front().exchange_rate =
            rates_.rate(EconomyId(0U));
        tick_ = economy.tick;
        return Status::success();
    }

    const bool move_staging =
        !options.require_world_rollback &&
        options.fault_point == M9FaultPoint::none && options.domestic.empty();
    M9World staged = [this, move_staging]() {
        return move_staging ? M9World(std::move(*this)) : M9World(*this);
    }();
    struct MovedWorldGuard final {
        M9World *target;
        M9World *staged;
        bool armed;

        ~MovedWorldGuard() {
            if (armed) {
                *target = std::move(*staged);
            }
        }
    } guard{this, &staged, move_staging};
    const std::size_t count = staged.economies_.size();
    staged.last_metrics_ = {};
    staged.last_metrics_.domestic.resize(count);
    staged.last_metrics_.external.resize(count);
    staged.trade_reservations_.clear();
    const std::uint64_t opening_event_counter = staged.event_counter_;

    std::vector<std::uint64_t> next_active;
    for (const auto &shock : staged.shocks_) {
        const Tick announcement = shock.announcement.value_or(shock.start);
        if (announcement == staged.tick_ &&
            !std::binary_search(staged.announced_shock_ids_.begin(),
                                staged.announced_shock_ids_.end(), shock.id)) {
            staged.shock_events_.push_back({staged.event_counter_++,
                                            ShockEventType::announced, staged.tick_,
                                            shock.id, 0.0});
            staged.announced_shock_ids_.push_back(shock.id);
        }
        if (shock.kind != ShockKind::capital_destruction &&
            shock_progress(shock, staged.tick_) > 0.0) {
            next_active.push_back(shock.id);
        }
    }
    std::sort(staged.announced_shock_ids_.begin(), staged.announced_shock_ids_.end());
    for (const auto shock_id : staged.active_shock_ids_) {
        if (!std::binary_search(next_active.begin(), next_active.end(), shock_id)) {
            staged.shock_events_.push_back({staged.event_counter_++,
                                            ShockEventType::ended, staged.tick_,
                                            shock_id, 0.0});
        }
    }
    for (const auto shock_id : next_active) {
        if (!std::binary_search(staged.active_shock_ids_.begin(),
                                staged.active_shock_ids_.end(), shock_id)) {
            const auto found = std::lower_bound(
                staged.shocks_.begin(), staged.shocks_.end(), shock_id,
                [](const ShockSpec &shock, std::uint64_t id) { return shock.id < id; });
            const double intensity = found == staged.shocks_.end()
                                         ? 0.0
                                         : shock_progress(*found, staged.tick_);
            staged.shock_events_.push_back({staged.event_counter_++,
                                            ShockEventType::started, staged.tick_,
                                            shock_id, intensity});
        }
    }
    staged.active_shock_ids_ = std::move(next_active);
    for (const auto &shock : staged.shocks_) {
        if (shock.kind == ShockKind::capital_destruction &&
            shock.start == staged.tick_ &&
            !std::binary_search(staged.realized_shock_ids_.begin(),
                                staged.realized_shock_ids_.end(), shock.id)) {
            staged.shock_events_.push_back({staged.event_counter_++,
                                            ShockEventType::realized, staged.tick_,
                                            shock.id, 1.0});
            staged.realized_shock_ids_.push_back(shock.id);
        }
    }
    std::sort(staged.realized_shock_ids_.begin(), staged.realized_shock_ids_.end());

    if (options.fault_point == M9FaultPoint::after_policy_barrier) {
        return Status(ErrorCode::internal_error, "injected M9 policy barrier fault");
    }

    std::vector<double> opening_rates(count, 1.0);
    for (std::size_t index = 0; index < count; ++index) {
        opening_rates[index] =
            staged.rates_.rate(EconomyId(static_cast<std::uint64_t>(index)));
    }
    const auto opening_dealer = staged.dealer_inventory_;

    std::vector<double> import_factor(count, 1.0);
    std::vector<double> export_factor(count, 1.0);
    std::vector<std::uint64_t> active_shocks(count, 0U);
    for (std::size_t index = 0; index < count; ++index) {
        for (const auto &shock : staged.shocks_) {
            if ((!shock.economy.has_value() || shock.economy->value() == index) &&
                shock_progress(shock, staged.tick_) > 0.0) {
                ++active_shocks[index];
            }
        }
        import_factor[index] = shock_factor(staged.shocks_, ShockKind::import_capacity,
                                            index, staged.tick_, std::nullopt);
        export_factor[index] = shock_factor(staged.shocks_, ShockKind::export_capacity,
                                            index, staged.tick_, std::nullopt);
    }

    for (std::size_t index = 0; index < count; ++index) {
        auto &economy = staged.economies_[index];
        economy.root.firms.for_each_alive([&](FirmId, core::FirmComponent &firm) {
            const ShockSector sector =
                firm.sector == core::FirmSector::construction
                    ? ShockSector::housing
                    : static_cast<ShockSector>(static_cast<std::uint8_t>(firm.sector));
            double survival = 1.0;
            for (const auto &shock : staged.shocks_) {
                if (shock.kind != ShockKind::capital_destruction ||
                    shock.start != staged.tick_ ||
                    (shock.economy.has_value() && shock.economy->value() != index) ||
                    (shock.sector.has_value() && *shock.sector != sector)) {
                    continue;
                }
                survival *= 1.0 - shock.magnitude;
            }
            const double opening = firm.physical_capital.value();
            const double closing = std::max(0.0, opening * survival);
            firm.physical_capital = Capital(closing);
            staged.last_metrics_.external[index].capital_destroyed += opening - closing;
        });
        double public_survival = 1.0;
        for (const auto &shock : staged.shocks_) {
            if (shock.kind != ShockKind::capital_destruction ||
                shock.start != staged.tick_ ||
                (shock.economy.has_value() && shock.economy->value() != index) ||
                (shock.sector.has_value() &&
                 *shock.sector != ShockSector::public_sector)) {
                continue;
            }
            public_survival *= 1.0 - shock.magnitude;
        }
        const double opening_public = economy.real_economy.public_capital;
        economy.real_economy.public_capital =
            std::max(0.0, opening_public * public_survival);
        staged.last_metrics_.external[index].capital_destroyed +=
            opening_public - economy.real_economy.public_capital;
    }

    if (staged.rules_.trade && count > 1U) {
        std::vector<double> export_remaining(count, 0.0);
        for (std::size_t source = 0; source < count; ++source) {
            staged.economies_[source].root.firms.for_each_alive(
                [&export_remaining, source](FirmId, const core::FirmComponent &firm) {
                    if (firm.sector == core::FirmSector::consumption) {
                        export_remaining[source] +=
                            clamp_nonnegative(firm.goods_inventory.value());
                    }
                });
            export_remaining[source] *= export_factor[source];
        }

        for (std::size_t importer = 0; importer < count; ++importer) {
            std::size_t best_source = count;
            double best_price = std::numeric_limits<double>::infinity();
            for (std::size_t source = 0; source < count; ++source) {
                if (source == importer || staged.sanctioned(importer, source) ||
                    export_remaining[source] <= kEpsilon) {
                    continue;
                }
                const double quote =
                    country_price(staged.economies_[source].domestic.last_metrics) *
                    staged.rates_.bilateral(
                        EconomyId(static_cast<std::uint64_t>(importer)),
                        EconomyId(static_cast<std::uint64_t>(source))) *
                    (1.0 + staged.rules_.fx_friction) *
                    (1.0 + staged.external_policies_[importer].tariff) *
                    (1.0 - staged.external_policies_[source].export_subsidy);
                if (quote < best_price) {
                    best_price = quote;
                    best_source = source;
                }
            }
            if (best_source == count) {
                continue;
            }
            double capacity =
                staged.rules_.fx_trade_cap *
                std::max(1.0, country_output(
                                  staged.economies_[importer].domestic.last_metrics));
            capacity *= import_factor[importer];
            const auto quota = staged.external_policies_[importer].import_quota;
            if (quota.has_value()) {
                capacity *= *quota;
            }
            const double iceberg = 1.0 + staged.rules_.fx_friction;
            double shipped_need =
                std::min(export_remaining[best_source], capacity * iceberg);
            auto &source_root = staged.economies_[best_source].root;
            std::vector<std::pair<FirmId, core::FirmComponent *>> candidates;
            source_root.firms.for_each_alive(
                [&candidates](FirmId id, core::FirmComponent &firm) {
                    if (firm.sector == core::FirmSector::consumption &&
                        firm.goods_inventory.value() > kEpsilon &&
                        firm.posted_price.value() > kEpsilon) {
                        candidates.emplace_back(id, &firm);
                    }
                });
            std::sort(candidates.begin(), candidates.end(),
                      [](const auto &left, const auto &right) {
                          if (left.second->posted_price != right.second->posted_price) {
                              return left.second->posted_price <
                                     right.second->posted_price;
                          }
                          return left.first < right.first;
                      });
            for (const auto &[firm_id, firm] : candidates) {
                if (shipped_need <= kEpsilon) {
                    break;
                }
                const double shipped =
                    std::min(shipped_need, firm->goods_inventory.value());
                const double delivered = shipped / iceberg;
                const double source_value =
                    shipped * firm->posted_price.value() *
                    (1.0 - staged.external_policies_[best_source].export_subsidy);
                const double importer_basic =
                    source_value *
                    staged.rates_.bilateral(
                        EconomyId(static_cast<std::uint64_t>(importer)),
                        EconomyId(static_cast<std::uint64_t>(best_source))) /
                    (1.0 - staged.rules_.fx_spread);
                const double importer_value =
                    importer_basic * (1.0 + staged.external_policies_[importer].tariff);
                firm->goods_inventory = Goods(firm->goods_inventory.value() - shipped);
                staged.trade_reservations_.push_back(TradeReservation{
                    EconomyId(static_cast<std::uint64_t>(importer)),
                    EconomyId(static_cast<std::uint64_t>(best_source)),
                    firm_id,
                    shipped,
                    delivered,
                    firm->posted_price.value(),
                    importer_value,
                });
                shipped_need -= shipped;
                export_remaining[best_source] -= shipped;
            }
        }
    }

    if (options.fault_point == M9FaultPoint::after_trade_reservation) {
        return Status(ErrorCode::internal_error, "injected M9 trade reservation fault");
    }

    std::vector<double> reserved_import_units(count, 0.0);
    std::vector<double> reserved_import_value(count, 0.0);
    for (const auto &reservation : staged.trade_reservations_) {
        const auto importer = static_cast<std::size_t>(reservation.importer.value());
        reserved_import_units[importer] += reservation.delivered_units;
        reserved_import_value[importer] += reservation.importer_value;
    }
    std::vector<double> realized_import_units(count, 0.0);
    std::vector<double> realized_import_value(count, 0.0);
    std::vector<Status> domestic_status(count);
    const auto advance_domestic = [&](std::size_t index) {
        auto domestic_options =
            options.domestic.empty() ? M8AdvanceOptions{} : options.domestic[index];
        const double energy_capacity =
            shock_factor(staged.shocks_, ShockKind::energy_capacity, index,
                         staged.tick_, ShockSector::energy);
        const double labor_energy =
            shock_factor(staged.shocks_, ShockKind::labor_availability, index,
                         staged.tick_, ShockSector::energy);
        const double productivity_energy =
            shock_factor(staged.shocks_, ShockKind::productivity, index, staged.tick_,
                         ShockSector::energy);
        const double household_demand =
            shock_factor(staged.shocks_, ShockKind::household_demand, index,
                         staged.tick_, std::nullopt);
        const double credit_supply =
            shock_factor(staged.shocks_, ShockKind::credit_supply, index, staged.tick_,
                         std::nullopt);
        auto energy_input = staged.economies_[index].domestic.energy_input;
        energy_input.capacity_multiplier *= energy_capacity;
        energy_input.labor_availability_multiplier *= labor_energy;
        energy_input.supply_multiplier *= productivity_energy;
        domestic_options.energy_input = energy_input;

        auto housing_input = staged.economies_[index].domestic.housing_input;
        housing_input.construction_productivity_multiplier *=
            shock_factor(staged.shocks_, ShockKind::productivity, index, staged.tick_,
                         ShockSector::housing) *
            shock_factor(staged.shocks_, ShockKind::labor_availability, index,
                         staged.tick_, ShockSector::housing);
        domestic_options.housing_input = housing_input;

        auto &m4_options = domestic_options.base.base.base.base;
        m4_options.memory_efficient_staging = true;
        if (options.domestic.empty() &&
            options.fault_point == M9FaultPoint::none &&
            !options.require_world_rollback) {
            m4_options.validate_preconditions = false;
            m4_options.audit_extended_state = false;
        }
        m4_options.household_demand_multiplier *= household_demand;
        if (reserved_import_units[index] > kEpsilon) {
            m4_options.external_goods_offer = M4ExternalGoodsOffer{
                std::numeric_limits<std::uint64_t>::max() -
                    static_cast<std::uint64_t>(index),
                staged.economies_[index].root.institutions.dealer_account,
                reserved_import_units[index],
                reserved_import_value[index] / reserved_import_units[index],
            };
        }
        for (const auto sector : {ShockSector::consumption, ShockSector::capital}) {
            const auto slot =
                static_cast<std::size_t>(static_cast<std::uint8_t>(sector));
            m4_options.productivity_multipliers[slot] *= shock_factor(
                staged.shocks_, ShockKind::productivity, index, staged.tick_, sector);
            m4_options.labor_availability_multipliers[slot] *=
                shock_factor(staged.shocks_, ShockKind::labor_availability, index,
                             staged.tick_, sector);
        }
        domestic_options.base.base.base.credit_supply_multiplier *= credit_supply;
        auto result = advance_m8_ticks(
            staged.economies_[index].root, staged.economies_[index].real_economy,
            staged.economies_[index].real_economy_scratch,
            staged.economies_[index].monetary,
            staged.economies_[index].monetary_scratch,
            staged.economies_[index].financial,
            staged.economies_[index].financial_scratch,
            staged.economies_[index].population,
            staged.economies_[index].population_scratch,
            staged.economies_[index].domestic,
            staged.economies_[index].domestic_scratch, staged.economies_[index].tick,
            1U, domestic_options);
        if (!result.ok()) {
            domestic_status[index] = result.status();
            return;
        }
        staged.last_metrics_.domestic[index] = result.get_if()->metrics;
        realized_import_units[index] =
            staged.economies_[index].real_economy_scratch.external_goods_units_;
        realized_import_value[index] =
            staged.economies_[index].real_economy_scratch.external_goods_value_;
        staged.last_metrics_.external[index].active_shocks = active_shocks[index];
    };
    const auto domestic_worker_count = std::min<std::size_t>(
        static_cast<std::size_t>(options.worker_count),
        count
    );
    if (domestic_worker_count == 1U) {
        for (std::size_t index = 0; index < count; ++index) {
            advance_domestic(index);
        }
    } else {
        std::atomic<std::size_t> next_domestic{0U};
        std::vector<std::thread> workers;
        workers.reserve(domestic_worker_count);
        for (std::size_t worker = 0; worker < domestic_worker_count; ++worker) {
            workers.emplace_back([&]() {
                while (true) {
                    const auto index =
                        next_domestic.fetch_add(1U, std::memory_order_relaxed);
                    if (index >= count) {
                        return;
                    }
                    advance_domestic(index);
                }
            });
        }
        for (auto &worker : workers) {
            worker.join();
        }
    }
    for (const auto &status : domestic_status) {
        if (!status.ok()) {
            return status;
        }
    }

    if (options.fault_point == M9FaultPoint::after_domestic_advance) {
        return Status(ErrorCode::internal_error, "injected M9 domestic advance fault");
    }

    std::vector<double> import_fill(count, 0.0);
    for (std::size_t importer = 0; importer < count; ++importer) {
        if (reserved_import_units[importer] <= kEpsilon) {
            continue;
        }
        if (realized_import_units[importer] >
            reserved_import_units[importer] + kTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "realized imports exceed reserved supply");
        }
        import_fill[importer] = std::clamp(realized_import_units[importer] /
                                               reserved_import_units[importer],
                                           0.0, 1.0);
        const double expected_value =
            reserved_import_value[importer] * import_fill[importer];
        const double value_tolerance = kTolerance * std::max(1.0, expected_value);
        if (std::abs(realized_import_value[importer] - expected_value) >
            value_tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "realized import value does not match market fill");
        }
    }

    std::vector<std::vector<core::TransferCommand>> settlement_commands(count);
    auto append_transfer = [&settlement_commands](std::size_t economy, AccountId source,
                                                  AccountId destination,
                                                  double amount) {
        if (amount > kEpsilon) {
            settlement_commands[economy].push_back(
                core::TransferCommand{source, destination, Money(amount)});
        }
    };

    double declared_spread = 0.0;
    for (const auto &reservation : staged.trade_reservations_) {
        const std::size_t importer =
            static_cast<std::size_t>(reservation.importer.value());
        const std::size_t exporter =
            static_cast<std::size_t>(reservation.exporter.value());
        const double fill = import_fill[importer];
        const double shipped_units = reservation.shipped_units * fill;
        const double delivered_units = reservation.delivered_units * fill;
        const double returned_units = reservation.shipped_units - shipped_units;
        auto *firm = staged.economies_[exporter].root.firms.get(reservation.firm);
        if (firm == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "reserved export firm no longer exists");
        }
        const double closing_inventory =
            firm->goods_inventory.value() + returned_units;
        const double closing_sales = firm->sales_previous + shipped_units;
        if (!finite(closing_inventory) || closing_inventory < -kTolerance ||
            !finite(closing_sales)) {
            return Status(
                ErrorCode::invariant_violation,
                "trade settlement would invalidate the export firm"
            );
        }
        firm->goods_inventory = Goods(std::max(0.0, closing_inventory));
        firm->sales_previous = closing_sales;
        if (shipped_units <= kEpsilon) {
            continue;
        }

        const double tariff_rate = staged.external_policies_[importer].tariff;
        const double importer_value = reservation.importer_value * fill;
        const double importer_basic = importer_value / (1.0 + tariff_rate);
        const double tariff = importer_value - importer_basic;
        const double exporter_basic =
            shipped_units * reservation.source_price *
            (1.0 - staged.external_policies_[exporter].export_subsidy);
        const double subsidy = shipped_units * reservation.source_price *
                               staged.external_policies_[exporter].export_subsidy;

        const auto importer_dealer =
            staged.economies_[importer].root.institutions.dealer_account;
        const auto importer_treasury =
            staged.economies_[importer].root.institutions.treasury_account;
        if (tariff > kEpsilon) {
            append_transfer(importer, importer_dealer, importer_treasury, tariff);
        } else if (tariff < -kEpsilon) {
            append_transfer(importer, importer_treasury, importer_dealer, -tariff);
        }

        const auto exporter_dealer =
            staged.economies_[exporter].root.institutions.dealer_account;
        const auto exporter_treasury =
            staged.economies_[exporter].root.institutions.treasury_account;
        append_transfer(exporter, exporter_dealer, firm->primary_account,
                        exporter_basic);
        if (subsidy > kEpsilon) {
            append_transfer(exporter, exporter_treasury, firm->primary_account,
                            subsidy);
        } else if (subsidy < -kEpsilon) {
            append_transfer(exporter, firm->primary_account, exporter_treasury,
                            -subsidy);
        }

        staged.dealer_inventory_[importer] += importer_basic;
        staged.dealer_inventory_[exporter] -= exporter_basic;
        declared_spread +=
            staged.rates_.to_numeraire(importer_basic, reservation.importer) -
            staged.rates_.to_numeraire(exporter_basic, reservation.exporter);

        auto &import_metrics = staged.last_metrics_.external[importer];
        auto &export_metrics = staged.last_metrics_.external[exporter];
        import_metrics.imports_value += importer_value;
        import_metrics.imports_volume += delivered_units;
        import_metrics.tariff_revenue += tariff;
        export_metrics.exports_value += exporter_basic + subsidy;
        export_metrics.exports_volume += shipped_units;
        export_metrics.iceberg_loss += shipped_units - delivered_units;
        export_metrics.export_subsidy_cost += subsidy;
        ++staged.last_metrics_.trade_routes;
    }
    for (std::size_t economy = 0; economy < count; ++economy) {
        if (settlement_commands[economy].empty()) {
            continue;
        }
        core::SettlementTransaction transaction(staged.economies_[economy].root);
        for (const auto &command : settlement_commands[economy]) {
            auto status = transaction.transfer(command.source, command.destination,
                                               command.amount);
            if (!status.ok()) {
                return status;
            }
        }
        const auto committed = transaction.commit_locally_validated();
        if (!committed.ok()) {
            return committed;
        }
    }
    staged.trade_reservations_.clear();

    if (staged.rules_.capital && count > 1U) {
        const auto opening_principal = staged.external_principal_;
        for (std::size_t debtor = 0; debtor < count; ++debtor) {
            for (std::size_t creditor = 0; creditor < count; ++creditor) {
                if (debtor == creditor || staged.sanctioned(debtor, creditor)) {
                    continue;
                }
                const double annual_rate = std::max(
                    0.0, policy_rate(staged.economies_[debtor].domestic.last_metrics));
                const double due = opening_principal[debtor][creditor] * annual_rate /
                                       staged.rules_.periods_per_year +
                                   staged.interest_arrears_[debtor][creditor];
                const double fraction = staged.external_policies_[debtor]
                                            .external_interest_settlement_fraction;
                const double cash = due * fraction;
                staged.interest_arrears_[debtor][creditor] = due - cash;
                staged.dealer_inventory_[debtor] += cash;
                const double creditor_cash =
                    cash / staged.rates_.bilateral(
                               EconomyId(static_cast<std::uint64_t>(debtor)),
                               EconomyId(static_cast<std::uint64_t>(creditor)));
                staged.dealer_inventory_[creditor] -= creditor_cash;
                staged.last_metrics_.external[debtor].factor_income_accrued -= due;
                staged.last_metrics_.external[creditor].factor_income_accrued +=
                    creditor_cash;
                staged.last_metrics_.external[debtor].factor_income_cash -= cash;
                staged.last_metrics_.external[creditor].factor_income_cash +=
                    creditor_cash;
            }
        }

        for (std::size_t investor = 0; investor < count; ++investor) {
            std::size_t best_debtor = count;
            double best_gap = 0.0;
            const double investor_rate =
                policy_rate(staged.economies_[investor].domestic.last_metrics);
            for (std::size_t debtor = 0; debtor < count; ++debtor) {
                if (debtor == investor || staged.sanctioned(debtor, investor)) {
                    continue;
                }
                const double gap =
                    policy_rate(staged.economies_[debtor].domestic.last_metrics) -
                    investor_rate;
                if (gap > best_gap) {
                    best_gap = gap;
                    best_debtor = debtor;
                }
            }
            if (best_debtor == count) {
                continue;
            }
            const double openness =
                (1.0 - staged.external_policies_[investor].capital_control) *
                (1.0 - staged.external_policies_[best_debtor].capital_control);
            const double flow =
                staged.rules_.capital_mobility * staged.rules_.capital_adjustment *
                openness * best_gap *
                std::max(1.0, country_output(
                                  staged.economies_[investor].domestic.last_metrics));
            staged.external_principal_[best_debtor][investor] += flow;
            staged.dealer_inventory_[investor] += flow;
            const double debtor_cash =
                flow * staged.rates_.bilateral(
                           EconomyId(static_cast<std::uint64_t>(best_debtor)),
                           EconomyId(static_cast<std::uint64_t>(investor)));
            staged.dealer_inventory_[best_debtor] -= debtor_cash;
            staged.last_metrics_.external[best_debtor].capital_flow += debtor_cash;
            staged.last_metrics_.external[investor].capital_flow -= flow;
        }
    }

    if (staged.rules_.migration && count > 1U) {
        std::vector<double> opening_origin_stock(count, 0.0);
        for (const auto &route : staged.migration_routes_) {
            opening_origin_stock[static_cast<std::size_t>(route.origin.value())] +=
                route.stock;
        }
        std::vector<MigrationRoute> next_routes;
        next_routes.reserve(count);
        for (std::size_t origin = 0; origin < count; ++origin) {
            const double origin_real_wage =
                country_wage(staged.economies_[origin].domestic.last_metrics) /
                country_price(staged.economies_[origin].domestic.last_metrics);
            staged.smoothed_real_wages_[origin] =
                (1.0 - staged.rules_.wage_smoothing) *
                    staged.smoothed_real_wages_[origin] +
                staged.rules_.wage_smoothing * origin_real_wage;
        }
        for (std::size_t origin = 0; origin < count; ++origin) {
            std::size_t host = count;
            double best_gap = 0.0;
            for (std::size_t candidate = 0; candidate < count; ++candidate) {
                if (candidate == origin || staged.sanctioned(origin, candidate)) {
                    continue;
                }
                const double gap = staged.smoothed_real_wages_[candidate] -
                                   staged.smoothed_real_wages_[origin];
                if (gap > best_gap) {
                    best_gap = gap;
                    host = candidate;
                }
            }
            if (host == count && opening_origin_stock[origin] <= kEpsilon) {
                continue;
            }
            if (host == count) {
                host = origin == 0U ? 1U : 0U;
            }
            const double population = static_cast<double>(
                staged.economies_[origin].domestic.last_metrics.economy.population);
            double flow = staged.rules_.migration_rate * std::max(0.0, best_gap) *
                          std::max(1.0, population);
            const auto emigration_cap =
                staged.external_policies_[origin].emigration_cap;
            if (emigration_cap.has_value()) {
                flow = std::min(flow, *emigration_cap * population);
            }
            const auto immigration_cap =
                staged.external_policies_[host].immigration_cap;
            if (immigration_cap.has_value()) {
                const double host_population = static_cast<double>(
                    staged.economies_[host].domestic.last_metrics.economy.population);
                flow = std::min(flow, *immigration_cap * host_population);
            }
            const double max_stock =
                staged.rules_.migration_max_share * std::max(1.0, population);
            flow =
                std::min(flow, std::max(0.0, max_stock - opening_origin_stock[origin]));
            const double return_flow =
                std::min(opening_origin_stock[origin],
                         staged.external_policies_[origin].guest_worker_return *
                             opening_origin_stock[origin]);
            const double stock = opening_origin_stock[origin] + flow - return_flow;
            const double host_wage =
                country_wage(staged.economies_[host].domestic.last_metrics);
            const double remittance_gross =
                stock * host_wage * staged.rules_.remittance_share;
            const double outward_tax =
                remittance_gross *
                staged.external_policies_[host].outward_remittance_tax;
            const double after_host_tax = remittance_gross - outward_tax;
            const double inbound_tax =
                after_host_tax * staged.external_policies_[origin].remittance_tax;
            const double remittance_net = after_host_tax - inbound_tax;
            staged.dealer_inventory_[host] += after_host_tax;
            const double origin_payout =
                remittance_net *
                staged.rates_.bilateral(EconomyId(static_cast<std::uint64_t>(origin)),
                                        EconomyId(static_cast<std::uint64_t>(host))) *
                (1.0 - staged.rules_.fx_spread);
            staged.dealer_inventory_[origin] -= origin_payout;
            declared_spread +=
                staged.rates_.to_numeraire(
                    after_host_tax, EconomyId(static_cast<std::uint64_t>(host))) -
                staged.rates_.to_numeraire(
                    origin_payout, EconomyId(static_cast<std::uint64_t>(origin)));
            next_routes.push_back(MigrationRoute{
                EconomyId(static_cast<std::uint64_t>(origin)),
                EconomyId(static_cast<std::uint64_t>(host)),
                stock,
                best_gap,
                flow,
                return_flow,
                remittance_gross,
                remittance_net,
            });
            auto &origin_metrics = staged.last_metrics_.external[origin];
            auto &host_metrics = staged.last_metrics_.external[host];
            origin_metrics.migrant_stock_abroad += stock;
            host_metrics.migrant_stock_hosted += stock;
            origin_metrics.remittances_received += origin_payout;
            host_metrics.remittances_sent += after_host_tax;
            origin_metrics.remittance_tax_revenue += inbound_tax;
            host_metrics.remittance_tax_revenue += outward_tax;
            ++staged.last_metrics_.migration_routes;
        }
        staged.migration_routes_ = std::move(next_routes);
    }

    std::vector<double> grope_signal(count, 0.0);
    double inventory_scale = 1.0;
    for (std::size_t index = 0; index < count; ++index) {
        inventory_scale +=
            std::abs(staged.dealer_inventory_[index]) / opening_rates[index];
    }
    for (std::size_t index = 0; index < count; ++index) {
        grope_signal[index] =
            staged.dealer_inventory_[index] / opening_rates[index] / inventory_scale;
        staged.rates_.log_rates[index] +=
            staged.rules_.fx_adjustment * grope_signal[index];
    }
    staged.rates_.normalize();

    for (auto &peg : staged.pegs_) {
        const std::size_t pegger = static_cast<std::size_t>(peg.pegger.value());
        const std::size_t anchor = static_cast<std::size_t>(peg.anchor.value());
        const double floated_spread =
            staged.rates_.log_rates[pegger] - staged.rates_.log_rates[anchor];
        const double pressure = floated_spread - peg.target_log_spread;
        const double reserve_need =
            std::abs(pressure) * staged.external_policies_[pegger].peg_reserve_scale;
        const double defense = std::min(peg.reserves, reserve_need);
        if (reserve_need > kEpsilon) {
            const double defended_share = defense / reserve_need;
            staged.rates_.log_rates[pegger] -= pressure * defended_share;
            peg.pressure += pressure * (1.0 - defended_share);
            peg.reserves -= defense;
        }
        if (defense + kTolerance < reserve_need) {
            peg.intact = false;
        }
    }
    staged.rates_.normalize();

    double flow = 0.0;
    for (std::size_t index = 0; index < count; ++index) {
        flow += (staged.dealer_inventory_[index] - opening_dealer[index]) /
                opening_rates[index];
    }
    double valuation = 0.0;
    for (std::size_t index = 0; index < count; ++index) {
        const double closing_rate =
            staged.rates_.rate(EconomyId(static_cast<std::uint64_t>(index)));
        valuation += staged.dealer_inventory_[index] *
                     (1.0 / closing_rate - 1.0 / opening_rates[index]);
    }
    staged.dealer_valuation_ += valuation;

    for (std::size_t index = 0; index < count; ++index) {
        auto &metrics = staged.last_metrics_.external[index];
        metrics.exchange_rate =
            staged.rates_.rate(EconomyId(static_cast<std::uint64_t>(index)));
        metrics.current_account = metrics.exports_value - metrics.imports_value +
                                  metrics.factor_income_accrued +
                                  metrics.remittances_received -
                                  metrics.remittances_sent;
        double assets = 0.0;
        double liabilities = 0.0;
        double arrears = 0.0;
        for (std::size_t other = 0; other < count; ++other) {
            assets +=
                staged.external_principal_[other][index] /
                staged.rates_.bilateral(EconomyId(static_cast<std::uint64_t>(index)),
                                        EconomyId(static_cast<std::uint64_t>(other)));
            liabilities += staged.external_principal_[index][other];
            arrears += staged.interest_arrears_[index][other];
        }
        metrics.net_foreign_assets = assets - liabilities;
        metrics.factor_income_arrears = arrears;
    }
    for (const auto &peg : staged.pegs_) {
        staged.last_metrics_.external[static_cast<std::size_t>(peg.pegger.value())]
            .peg_reserves = peg.reserves;
    }
    staged.last_metrics_.dealer_flow = flow;
    staged.last_metrics_.dealer_spread_revenue = declared_spread;
    staged.last_metrics_.dealer_valuation = staged.dealer_valuation_;
    staged.last_metrics_.world_nfa = 0.0;
    for (const auto &metrics : staged.last_metrics_.external) {
        staged.last_metrics_.world_nfa += metrics.net_foreign_assets;
    }
    staged.last_metrics_.shock_events = staged.event_counter_ - opening_event_counter;

    staged.tick_ = Tick(staged.tick_.value() + 1U);

    auto validation = staged.validate_impl(false);
    if (!validation.ok()) {
        return validation;
    }
    if (options.fault_point == M9FaultPoint::before_world_commit) {
        return Status(ErrorCode::internal_error, "injected M9 pre-commit fault");
    }
    *this = std::move(staged);
    guard.armed = false;
    return Status::success();
}

Status M9World::validate() const noexcept {
    return validate_impl(true);
}

Status M9World::validate_impl(bool validate_domestic) const noexcept {
    if (economies_.empty() || external_policies_.size() != economies_.size() ||
        rates_.size() != economies_.size() ||
        dealer_inventory_.size() != economies_.size() ||
        external_principal_.size() != economies_.size() ||
        interest_arrears_.size() != economies_.size() ||
        smoothed_real_wages_.size() != economies_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "M9 World vector dimensions disagree");
    }
    auto rules_status = validate_world_rules(rules_);
    if (!rules_status.ok()) {
        return rules_status;
    }
    auto policy_status = validate_policy_vector(external_policies_);
    if (!policy_status.ok()) {
        return policy_status;
    }
    for (std::size_t index = 0; index < shocks_.size(); ++index) {
        const auto status = validate_shock_spec(shocks_[index], economies_.size());
        if (!status.ok() ||
            (index > 0U && shocks_[index - 1U].id >= shocks_[index].id)) {
            return Status(ErrorCode::invariant_violation, "invalid M9 shock tape");
        }
    }
    const auto known_shock = [&](std::uint64_t id) {
        const auto found =
            std::lower_bound(shocks_.begin(), shocks_.end(), id,
                             [](const ShockSpec &shock, std::uint64_t candidate) {
                                 return shock.id < candidate;
                             });
        return found != shocks_.end() && found->id == id;
    };
    const auto valid_lifecycle_ids = [&](const std::vector<std::uint64_t> &ids) {
        if (!std::is_sorted(ids.begin(), ids.end()) ||
            std::adjacent_find(ids.begin(), ids.end()) != ids.end()) {
            return false;
        }
        return std::all_of(ids.begin(), ids.end(), known_shock);
    };
    if (!valid_lifecycle_ids(announced_shock_ids_) ||
        !valid_lifecycle_ids(active_shock_ids_) ||
        !valid_lifecycle_ids(realized_shock_ids_) ||
        event_counter_ != shock_events_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "invalid M9 shock lifecycle state");
    }
    for (std::size_t index = 0; index < shock_events_.size(); ++index) {
        const auto &event = shock_events_[index];
        if (event.sequence != index || !valid_event_type(event.type) ||
            !finite(event.intensity) || event.intensity < 0.0 ||
            !known_shock(event.shock_id)) {
            return Status(ErrorCode::invariant_violation,
                          "invalid M9 shock event stream");
        }
    }
    double mean_log_rate = 0.0;
    for (std::size_t index = 0; index < economies_.size(); ++index) {
        if (!finite(rates_.log_rates[index]) || !finite(dealer_inventory_[index]) ||
            !finite(smoothed_real_wages_[index]) || smoothed_real_wages_[index] < 0.0 ||
            external_principal_[index].size() != economies_.size() ||
            interest_arrears_[index].size() != economies_.size() ||
            economies_[index].tick != tick_) {
            return Status(ErrorCode::invariant_violation, "invalid M9 country state");
        }
        mean_log_rate += rates_.log_rates[index];
        for (std::size_t other = 0; other < economies_.size(); ++other) {
            if (!finite(external_principal_[index][other]) ||
                external_principal_[index][other] < -kTolerance ||
                !finite(interest_arrears_[index][other]) ||
                interest_arrears_[index][other] < -kTolerance ||
                (index == other &&
                 (std::abs(external_principal_[index][other]) > kTolerance ||
                  std::abs(interest_arrears_[index][other]) > kTolerance))) {
                return Status(ErrorCode::invariant_violation,
                              "invalid external contract matrix");
            }
        }
        if (validate_domestic) {
            auto domestic_status = validate_m8_state(
                economies_[index].root, economies_[index].real_economy,
                economies_[index].monetary, economies_[index].financial,
                economies_[index].population, economies_[index].domestic,
                economies_[index].tick);
            if (!domestic_status.ok()) {
                return domestic_status;
            }
        }
    }
    mean_log_rate /= static_cast<double>(economies_.size());
    if (std::abs(mean_log_rate) > kTolerance) {
        return Status(ErrorCode::invariant_violation,
                      "exchange-rate vector is not normalized");
    }
    for (const auto &peg : pegs_) {
        if (!valid_economy(peg.pegger, economies_.size()) ||
            !valid_economy(peg.anchor, economies_.size()) || peg.pegger == peg.anchor ||
            !finite(peg.reserves) || peg.reserves < -kTolerance ||
            !finite(peg.pressure) || !finite(peg.target_log_spread)) {
            return Status(ErrorCode::invariant_violation, "invalid peg runtime");
        }
    }
    for (const auto &route : migration_routes_) {
        if (!valid_economy(route.origin, economies_.size()) ||
            !valid_economy(route.host, economies_.size()) ||
            route.origin == route.host || !finite(route.stock) ||
            route.stock < -kTolerance || !finite(route.flow) ||
            route.flow < -kTolerance || !finite(route.return_flow) ||
            route.return_flow < -kTolerance || !finite(route.remittance_gross) ||
            route.remittance_gross < -kTolerance || !finite(route.remittance_net) ||
            route.remittance_net < -kTolerance) {
            return Status(ErrorCode::invariant_violation, "invalid migration route");
        }
    }
    return Status::success();
}

std::uint64_t M9World::digest() const noexcept {
    std::uint64_t hash = kFnvOffset;
    hash_mix(hash, tick_.value());
    hash_mix(hash, static_cast<std::uint64_t>(economies_.size()));
    for (std::size_t index = 0; index < economies_.size(); ++index) {
        hash_mix(hash, rates_.log_rates[index]);
        hash_mix(hash, dealer_inventory_[index]);
        hash_mix(hash, smoothed_real_wages_[index]);
        hash_mix(hash, external_policies_[index].tariff);
        hash_mix(hash, external_policies_[index].capital_control);
        hash_mix(hash, economies_[index].root.seed);
        hash_mix(hash, economies_[index].domestic.energy_event_counter);
        hash_mix(hash, economies_[index].domestic.housing_event_counter);
        for (std::size_t other = 0; other < economies_.size(); ++other) {
            hash_mix(hash, external_principal_[index][other]);
            hash_mix(hash, interest_arrears_[index][other]);
        }
    }
    for (const auto &peg : pegs_) {
        hash_mix(hash, static_cast<std::uint64_t>(peg.pegger.value()));
        hash_mix(hash, static_cast<std::uint64_t>(peg.anchor.value()));
        hash_mix(hash, peg.reserves);
        hash_mix(hash, peg.pressure);
        hash_mix(hash, static_cast<std::uint64_t>(peg.intact ? 1U : 0U));
    }
    for (const auto &route : migration_routes_) {
        hash_mix(hash, static_cast<std::uint64_t>(route.origin.value()));
        hash_mix(hash, static_cast<std::uint64_t>(route.host.value()));
        hash_mix(hash, route.stock);
        hash_mix(hash, route.remittance_net);
    }
    hash_mix(hash, dealer_valuation_);
    hash_mix(hash, event_counter_);
    return hash;
}

} // namespace macro_sim::simulation
