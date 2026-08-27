#include "macro_sim/reporting/m10.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <limits>
#include <numeric>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace macro_sim::reporting {
namespace {

using simulation::M8Metrics;

constexpr std::array<MetricDescriptor, kM10MetricCount> kDescriptors{{
    {"metric.economy.avg_wage", "currency_per_tick", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.mean_hourly_wage"},
    {"metric.economy.credit_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "m5.total_loan_principal / m4.nominal_output"},
    {"metric.economy.employment", "fte", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.employed_fte"},
    {"metric.economy.energy_price", "currency_per_unit", 1U, MetricTier::causal,
     MetricAggregation::mean, "m8.energy.transaction_price_hold_last"},
    {"metric.economy.energy_subsidy_paid", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m8.energy.subsidy_paid"},
    {"metric.economy.gov_debt_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "government_debt / annualized_daily_nominal_output"},
    {"metric.economy.gov_deficit_to_gdp", "share", 1U, MetricTier::analytic,
     MetricAggregation::last, "m4.government_deficit / m4.nominal_output"},
    {"metric.economy.income_gini", "index", 1U, MetricTier::analytic,
     MetricAggregation::last, "gini(live_household_income_realized)"},
    {"metric.economy.inflation", "per_tick", 1U, MetricTier::analytic,
     MetricAggregation::mean, "price_index / previous_price_index - 1"},
    {"metric.economy.n_bank_failures", "count", 1U, MetricTier::causal,
     MetricAggregation::sum, "m5.bank_failures"},
    {"metric.economy.policy_rate", "rate_per_tick", 1U, MetricTier::causal,
     MetricAggregation::last, "m5.policy_rate"},
    {"metric.economy.population_alive", "persons", 1U, MetricTier::causal,
     MetricAggregation::last, "m7.population"},
    {"metric.economy.poverty_rate", "share", 1U, MetricTier::analytic,
     MetricAggregation::last,
     "person_share_below_half_person_weighted_median_equivalized_consumption"},
    {"metric.economy.price_index", "index", 1U, MetricTier::causal,
     MetricAggregation::mean, "m4.price_index"},
    {"metric.economy.real_output", "goods_units", 1U, MetricTier::causal,
     MetricAggregation::sum, "m4.real_output"},
    {"metric.economy.unemployment_rate", "share", 1U, MetricTier::causal,
     MetricAggregation::mean, "m7.unemployment_rate"},
    {"metric.world.current_account", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.current_account"},
    {"metric.world.e", "local_currency_per_numeraire", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.exchange_rate"},
    {"metric.world.export_shipped_volume", "goods_units", 1U,
     MetricTier::causal, MetricAggregation::sum, "m9.external.exports_volume"},
    {"metric.world.import_volume", "goods_units", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.imports_volume"},
    {"metric.world.migrant_stock", "persons", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.migrant_stock_abroad"},
    {"metric.world.nfa", "currency", 1U, MetricTier::causal,
     MetricAggregation::last, "m9.external.net_foreign_assets"},
    {"metric.world.remittances", "currency", 1U, MetricTier::causal,
     MetricAggregation::sum, "m9.external.remittances_received"},
    {"metric.economy.bank_reserves_total", "currency", 1U,
     MetricTier::causal, MetricAggregation::last,
     "m5.total_reserves"},
    {"metric.economy.reserve_floor_breach_share", "share", 1U,
     MetricTier::release, MetricAggregation::last,
     "share(alive_bank_reserves < reserve_floor_fraction * deposits)"},
    {"metric.economy.near_failure_bank_count", "banks", 1U,
     MetricTier::release, MetricAggregation::last,
     "count(0 <= closing_bank_capital < m6.bank_minimum_capital)"},
    {"metric.economy.energy_stock_total", "energy_units", 1U,
     MetricTier::causal, MetricAggregation::last,
     "m8.producer_inventory + m8.downstream_stock + m8.strategic_reserve"},
    {"metric.economy.energy_unfilled", "energy_units", 1U,
     MetricTier::causal, MetricAggregation::sum,
     "m8.energy.unfilled"},
    {"metric.world.reserves_by_economy", "anchor_currency", 1U,
     MetricTier::causal, MetricAggregation::last,
     "m9.peg.reserves for pegger; zero for floating economy"},
    {"metric.shock.announced_count", "events", 1U, MetricTier::release,
     MetricAggregation::last, "count(disclosed shocks relevant to economy)"},
    {"metric.shock.active_count", "events", 1U, MetricTier::release,
     MetricAggregation::last, "count(disclosed shocks active at boundary)"},
    {"metric.shock.max_severity", "fraction", 1U, MetricTier::release,
     MetricAggregation::last, "max(disclosed active magnitude * intensity)"},
    {"metric.shock.time_to_next", "ticks", 1U, MetricTier::release,
     MetricAggregation::last, "min(max(0, start - boundary)) over disclosed shocks"},
    {"metric.shock.severity.productivity", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed productivity shock severity"},
    {"metric.shock.severity.labor_availability", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed labor-availability shock severity"},
    {"metric.shock.severity.energy_capacity", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed energy-capacity shock severity"},
    {"metric.shock.severity.household_demand", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed household-demand shock severity"},
    {"metric.shock.severity.import_capacity", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed import-capacity shock severity"},
    {"metric.shock.severity.export_capacity", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed export-capacity shock severity"},
    {"metric.shock.severity.credit_supply", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed credit-supply shock severity"},
    {"metric.shock.severity.capital_destruction", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed capital-destruction shock severity"},
    {"metric.economy.hh_wealth_gini", "index", 30U, MetricTier::analytic,
     MetricAggregation::last,
     "gini(nonnegative household deposits + securities + housing - debt)"},
    {"metric.economy.wage_p90_p10_ratio", "ratio", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "weighted_p90(active hourly wage) / weighted_p10(active hourly wage)"},
    {"metric.economy.welfare_log", "log_real_consumption", 30U,
     MetricTier::analytic, MetricAggregation::mean,
     "person-weighted mean log equivalized real household consumption"},
    {"metric.economy.savings_rate", "share", 30U, MetricTier::analytic,
     MetricAggregation::last,
     "(live household realized income - consumption) / realized income"},
    {"metric.economy.bottom10_consumption", "real_currency", 30U,
     MetricTier::analytic, MetricAggregation::mean,
     "mean equivalized real consumption of the bottom population decile"},
    {"metric.economy.income_decile_1_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "bottom household income decile share"},
    {"metric.economy.income_decile_2_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "second household income decile share"},
    {"metric.economy.income_decile_3_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "third household income decile share"},
    {"metric.economy.income_decile_4_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "fourth household income decile share"},
    {"metric.economy.income_decile_5_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "fifth household income decile share"},
    {"metric.economy.income_decile_6_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "sixth household income decile share"},
    {"metric.economy.income_decile_7_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "seventh household income decile share"},
    {"metric.economy.income_decile_8_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "eighth household income decile share"},
    {"metric.economy.income_decile_9_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "ninth household income decile share"},
    {"metric.economy.income_decile_10_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "top household income decile share"},
    {"metric.economy.wealth_decile_1_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "bottom household net-wealth decile share"},
    {"metric.economy.wealth_decile_2_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "second household net-wealth decile share"},
    {"metric.economy.wealth_decile_3_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "third household net-wealth decile share"},
    {"metric.economy.wealth_decile_4_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "fourth household net-wealth decile share"},
    {"metric.economy.wealth_decile_5_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "fifth household net-wealth decile share"},
    {"metric.economy.wealth_decile_6_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "sixth household net-wealth decile share"},
    {"metric.economy.wealth_decile_7_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "seventh household net-wealth decile share"},
    {"metric.economy.wealth_decile_8_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "eighth household net-wealth decile share"},
    {"metric.economy.wealth_decile_9_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "ninth household net-wealth decile share"},
    {"metric.economy.wealth_decile_10_share", "share", 30U, MetricTier::analytic,
     MetricAggregation::last, "top household net-wealth decile share"},
    {"metric.economy.consumption_decile_1_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "bottom population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_2_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "second population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_3_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "third population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_4_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "fourth population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_5_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "fifth population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_6_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "sixth population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_7_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "seventh population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_8_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "eighth population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_9_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "ninth population equivalized-consumption decile share"},
    {"metric.economy.consumption_decile_10_share", "share", 30U,
     MetricTier::analytic, MetricAggregation::last,
     "top population equivalized-consumption decile share"},
    {"metric.shock.severity.sovereign_risk_premium", "fraction", 1U,
     MetricTier::release, MetricAggregation::last,
     "max disclosed sovereign-risk-premium shock severity"},
#define MACRO_SIM_DASHBOARD_METRIC(symbol, stable_id, unit, parity_rule)   \
    {stable_id, unit, 30U, MetricTier::analytic,                          \
     MetricAggregation::last, parity_rule},
#include "macro_sim/reporting/m10_dashboard_metrics.inc"
#undef MACRO_SIM_DASHBOARD_METRIC
#define MACRO_SIM_M4_SOURCE(field, unit)                                  \
    {"metric.source.m4." #field, unit, 1U, MetricTier::analytic,          \
     MetricAggregation::last, "simulation::M4Metrics::" #field},
#define MACRO_SIM_M5_SOURCE(field, unit)                                  \
    {"metric.source.m5." #field, unit, 1U, MetricTier::analytic,          \
     MetricAggregation::last, "simulation::M5Metrics::" #field},
#define MACRO_SIM_M6_SOURCE(field, unit)                                  \
    {"metric.source.m6." #field, unit, 1U, MetricTier::analytic,          \
     MetricAggregation::last, "simulation::M6Metrics::" #field},
#define MACRO_SIM_M7_SOURCE(field, unit)                                  \
    {"metric.source.m7." #field, unit, 1U, MetricTier::analytic,          \
     MetricAggregation::last, "simulation::M7Metrics::" #field},
#define MACRO_SIM_M8_ENERGY_SOURCE(field, unit)                           \
    {"metric.source.m8.energy." #field, unit, 1U, MetricTier::analytic,   \
     MetricAggregation::last, "simulation::EnergyMetrics::" #field},
#define MACRO_SIM_M8_HOUSING_SOURCE(field, unit)                          \
    {"metric.source.m8.housing." #field, unit, 1U, MetricTier::analytic,  \
     MetricAggregation::last, "simulation::HousingMetrics::" #field},
#define MACRO_SIM_M9_COUNTRY_SOURCE(field, unit)                          \
    {"metric.source.m9.country." #field, unit, 1U, MetricTier::analytic,  \
     MetricAggregation::last,                                            \
     "simulation::CountryExternalMetrics::" #field},
#define MACRO_SIM_M9_WORLD_SOURCE(field, unit)                            \
    {"metric.source.m9.world." #field, unit, 1U, MetricTier::analytic,    \
     MetricAggregation::last, "simulation::M9WorldMetrics::" #field},
#include "macro_sim/reporting/m10_metric_sources.inc"
#undef MACRO_SIM_M4_SOURCE
#undef MACRO_SIM_M5_SOURCE
#undef MACRO_SIM_M6_SOURCE
#undef MACRO_SIM_M7_SOURCE
#undef MACRO_SIM_M8_ENERGY_SOURCE
#undef MACRO_SIM_M8_HOUSING_SOURCE
#undef MACRO_SIM_M9_COUNTRY_SOURCE
#undef MACRO_SIM_M9_WORLD_SOURCE
#define MACRO_SIM_NATIONAL_ACCOUNT(field, unit)                           \
    {"metric.economy.na." #field, unit, 1U, MetricTier::analytic,         \
     MetricAggregation::last, "native_national_accounts::" #field},
#include "macro_sim/reporting/m10_national_accounts.inc"
#undef MACRO_SIM_NATIONAL_ACCOUNT
}};

enum class DashboardMetric : std::size_t {
#define MACRO_SIM_DASHBOARD_METRIC(symbol, stable_id, unit, parity_rule) symbol,
#include "macro_sim/reporting/m10_dashboard_metrics.inc"
#undef MACRO_SIM_DASHBOARD_METRIC
    count,
};

static_assert(
    static_cast<std::size_t>(DashboardMetric::count) ==
    kM10DashboardMetricCount);

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

[[nodiscard]] double gini(std::vector<double> values) {
    if (values.empty()) {
        return 0.0;
    }
    for (auto &value : values) {
        value = std::max(0.0, value);
    }
    std::sort(values.begin(), values.end());
    const double total = std::accumulate(values.begin(), values.end(), 0.0);
    if (total <= 1.0e-12) {
        return 0.0;
    }
    double weighted = 0.0;
    for (std::size_t index = 0; index < values.size(); ++index) {
        weighted += static_cast<double>(index + 1U) * values[index];
    }
    const double count = static_cast<double>(values.size());
    return std::clamp(2.0 * weighted / (count * total) -
                          (count + 1.0) / count,
                      0.0, 1.0);
}

[[nodiscard]] double top_decile_share(std::vector<double> values) {
    if (values.empty()) {
        return 0.0;
    }
    for (auto &value : values) {
        value = std::max(0.0, value);
    }
    std::sort(values.begin(), values.end(), std::greater<double>{});
    const double total = std::accumulate(values.begin(), values.end(), 0.0);
    if (total <= 1.0e-12) {
        return 0.0;
    }
    const std::size_t count = std::max<std::size_t>(
        1U, (values.size() + 9U) / 10U);
    return std::accumulate(
               values.begin(),
               values.begin() +
                   static_cast<std::vector<double>::difference_type>(
                       count),
               0.0) /
           total;
}

[[nodiscard]] double pareto_slope(std::vector<double> values) {
    values.erase(
        std::remove_if(
            values.begin(), values.end(),
            [](double value) {
                return !finite(value) || value <= 1.0e-12;
            }),
        values.end());
    if (values.size() < 3U) {
        return 0.0;
    }
    std::sort(values.begin(), values.end(), std::greater<double>{});
    values.resize(std::max<std::size_t>(
        3U, (values.size() + 9U) / 10U));
    double mean_log_rank = 0.0;
    double mean_log_size = 0.0;
    for (std::size_t index = 0U; index < values.size(); ++index) {
        mean_log_rank += std::log(static_cast<double>(index + 1U));
        mean_log_size += std::log(values[index]);
    }
    mean_log_rank /= static_cast<double>(values.size());
    mean_log_size /= static_cast<double>(values.size());
    double covariance = 0.0;
    double rank_variance = 0.0;
    for (std::size_t index = 0U; index < values.size(); ++index) {
        const double rank =
            std::log(static_cast<double>(index + 1U)) -
            mean_log_rank;
        covariance += rank * (std::log(values[index]) - mean_log_size);
        rank_variance += rank * rank;
    }
    const double rank_size_slope =
        rank_variance > 1.0e-12
            ? covariance / rank_variance
            : 0.0;
    return rank_size_slope < -1.0e-12
               ? -1.0 / rank_size_slope
               : 0.0;
}

struct EquivalizedConsumption final {
    double value{0.0};
    std::size_t persons{0U};
};

struct WeightedObservation final {
    double value{0.0};
    double weight{0.0};
};

struct DecileDistribution final {
    std::array<double, 10U> shares{};
    double bottom_mean{0.0};
};

[[nodiscard]] double relative_consumption_poverty(
    std::vector<EquivalizedConsumption> households
) {
    households.erase(
        std::remove_if(
            households.begin(), households.end(),
            [](const EquivalizedConsumption &household) {
                return household.persons == 0U;
            }),
        households.end());
    if (households.empty()) {
        return 0.0;
    }
    std::sort(
        households.begin(), households.end(),
        [](const EquivalizedConsumption &left,
           const EquivalizedConsumption &right) {
            return left.value < right.value;
        });
    const std::size_t persons = std::accumulate(
        households.begin(), households.end(), std::size_t{0U},
        [](std::size_t total, const EquivalizedConsumption &household) {
            return total + household.persons;
        });
    if (persons == 0U) {
        return 0.0;
    }
    const std::size_t median_rank = (persons + 1U) / 2U;
    std::size_t cumulative = 0U;
    double person_weighted_median = households.back().value;
    for (const auto &household : households) {
        cumulative += household.persons;
        if (cumulative >= median_rank) {
            person_weighted_median = household.value;
            break;
        }
    }
    const double poverty_line = 0.5 * person_weighted_median;
    if (poverty_line <= 1.0e-12) {
        return 0.0;
    }
    const std::size_t persons_below = std::accumulate(
        households.begin(), households.end(), std::size_t{0U},
        [poverty_line](
            std::size_t total,
            const EquivalizedConsumption &household
        ) {
            return total +
                (household.value < poverty_line ? household.persons : 0U);
        });
    return static_cast<double>(persons_below) /
        static_cast<double>(persons);
}

[[nodiscard]] DecileDistribution decile_distribution(
    std::vector<WeightedObservation> observations
) {
    observations.erase(
        std::remove_if(
            observations.begin(), observations.end(),
            [](const WeightedObservation &observation) {
                return !finite(observation.value) ||
                    !finite(observation.weight) ||
                    observation.weight <= 0.0;
            }),
        observations.end());
    DecileDistribution result;
    if (observations.empty()) {
        return result;
    }
    for (auto &observation : observations) {
        observation.value = std::max(0.0, observation.value);
    }
    std::sort(
        observations.begin(), observations.end(),
        [](const WeightedObservation &left,
           const WeightedObservation &right) {
            return left.value < right.value;
        });
    const double total_weight = std::accumulate(
        observations.begin(), observations.end(), 0.0,
        [](double total, const WeightedObservation &observation) {
            return total + observation.weight;
        });
    const double total_resource = std::accumulate(
        observations.begin(), observations.end(), 0.0,
        [](double total, const WeightedObservation &observation) {
            return total + observation.value * observation.weight;
        });
    if (total_weight <= 1.0e-12) {
        return result;
    }

    const double decile_weight = total_weight / 10.0;
    std::size_t decile = 0U;
    double used_in_decile = 0.0;
    std::array<double, 10U> resource{};
    for (const auto &observation : observations) {
        double remaining = observation.weight;
        while (remaining > 1.0e-12 && decile < resource.size()) {
            const double room = decile_weight - used_in_decile;
            const double allocated = std::min(remaining, room);
            resource[decile] += allocated * observation.value;
            remaining -= allocated;
            used_in_decile += allocated;
            if (used_in_decile + 1.0e-12 >= decile_weight) {
                ++decile;
                used_in_decile = 0.0;
            }
        }
    }
    if (total_resource > 1.0e-12) {
        for (std::size_t index = 0U; index < result.shares.size(); ++index) {
            result.shares[index] = resource[index] / total_resource;
        }
    }
    result.bottom_mean =
        decile_weight > 1.0e-12 ? resource[0U] / decile_weight : 0.0;
    return result;
}

[[nodiscard]] double weighted_quantile(
    std::vector<WeightedObservation> observations, double probability
) {
    observations.erase(
        std::remove_if(
            observations.begin(), observations.end(),
            [](const WeightedObservation &observation) {
                return !finite(observation.value) ||
                    !finite(observation.weight) ||
                    observation.weight <= 0.0;
            }),
        observations.end());
    if (observations.empty()) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    std::sort(
        observations.begin(), observations.end(),
        [](const WeightedObservation &left,
           const WeightedObservation &right) {
            return left.value < right.value;
        });
    const double total_weight = std::accumulate(
        observations.begin(), observations.end(), 0.0,
        [](double total, const WeightedObservation &observation) {
            return total + observation.weight;
        });
    const double target = std::clamp(probability, 0.0, 1.0) * total_weight;
    double cumulative = 0.0;
    for (const auto &observation : observations) {
        cumulative += observation.weight;
        if (cumulative + 1.0e-12 >= target) {
            return observation.value;
        }
    }
    return observations.back().value;
}

[[nodiscard]] std::size_t age_bucket(std::uint32_t age) noexcept {
    if (age < 15U) {
        return 0U;
    }
    if (age < 25U) {
        return 1U;
    }
    if (age < 35U) {
        return 2U;
    }
    if (age < 45U) {
        return 3U;
    }
    if (age < 55U) {
        return 4U;
    }
    if (age < 65U) {
        return 5U;
    }
    return 6U;
}

[[nodiscard]] double security_market_value(
    const core::SecurityBook &securities,
    const core::SecurityLot &lot
) noexcept {
    if (lot.security.kind() == core::SecurityKind::equity) {
        const auto *contract =
            securities.get(EquityId(lot.security.value()));
        return contract == nullptr || !contract->active
            ? 0.0
            : lot.units * contract->price.value();
    }
    const auto *contract = securities.get(BondId(lot.security.value()));
    return contract == nullptr || !contract->active
        ? 0.0
        : lot.units;
}

[[nodiscard]] double shock_progress(const simulation::ShockSpec &shock,
                                    Tick boundary) noexcept {
    if (boundary.value() < shock.start.value() ||
        boundary.value() >= shock.start.value() + shock.duration) {
        return 0.0;
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
    if (shock.shape == simulation::ShockShape::step || shock.duration <= 1U) {
        return 1.0;
    }
    if (shock.shape == simulation::ShockShape::linear) {
        return static_cast<double>(elapsed + 1U) /
               static_cast<double>(shock.duration);
    }
    const double position =
        static_cast<double>(elapsed) /
        static_cast<double>(std::max<std::uint64_t>(1U, shock.duration - 1U));
    return 1.0 - std::abs(2.0 * position - 1.0);
}

[[nodiscard]] bool shock_relevant(const simulation::ShockSpec &shock,
                                  std::size_t economy) noexcept {
    return !shock.economy.has_value() ||
           shock.economy->value() == economy;
}

[[nodiscard]] bool shock_disclosed(const simulation::ShockSpec &shock,
                                   Tick boundary) noexcept {
    return shock.announcement.value_or(shock.start).value() <=
           boundary.value();
}

[[nodiscard]] double shock_severity(const simulation::ShockSpec &shock,
                                    Tick boundary,
                                    bool include_announced_future) noexcept {
    const double magnitude = std::max(0.0, shock.magnitude);
    if (magnitude == 0.0) {
        return 0.0;
    }
    if (boundary.value() < shock.start.value()) {
        return include_announced_future ? magnitude : 0.0;
    }
    if (shock.kind == simulation::ShockKind::capital_destruction) {
        return magnitude;
    }
    return magnitude * shock_progress(shock, boundary);
}

void set(MetricFrame &frame, std::size_t economy, std::size_t metric,
         double value) {
    const std::size_t offset = economy * kM10MetricCount + metric;
    frame.values[offset] = value;
    frame.valid[offset] = finite(value) ? 1U : 0U;
}

void set_dashboard(MetricFrame &frame, std::size_t economy,
                   DashboardMetric metric, double value) {
    set(frame, economy,
        kM10BasePublicMetricCount + static_cast<std::size_t>(metric), value);
}

[[nodiscard]] const simulation::M4Metrics &m4(const M8Metrics &metrics) noexcept {
    return metrics.economy.economy.economy.economy;
}

[[nodiscard]] const simulation::M5Metrics &m5(const M8Metrics &metrics) noexcept {
    return metrics.economy.economy.economy;
}

[[nodiscard]] const simulation::M6Metrics &m6(const M8Metrics &metrics) noexcept {
    return metrics.economy.economy;
}

[[nodiscard]] const simulation::M7Metrics &m7(const M8Metrics &metrics) noexcept {
    return metrics.economy;
}

struct NativeNationalAccounts final {
#define MACRO_SIM_NATIONAL_ACCOUNT(field, unit) double field{0.0};
#include "macro_sim/reporting/m10_national_accounts.inc"
#undef MACRO_SIM_NATIONAL_ACCOUNT
};

[[nodiscard]] double safe_ratio(double numerator, double denominator) noexcept {
    return std::abs(denominator) > 1.0e-12
               ? numerator / denominator
               : 0.0;
}

[[nodiscard]] NativeNationalAccounts build_national_accounts(
    const simulation::M8Metrics &domestic,
    const simulation::CountryExternalMetrics &external,
    double government_debt) noexcept {
    const auto &real = m4(domestic);
    const auto &monetary = m5(domestic);
    const auto &population = m7(domestic);
    const auto &energy = domestic.energy;
    const auto &housing = domestic.housing;
    NativeNationalAccounts accounts;
    accounts.enabled = 1.0;

    const double energy_output_nominal =
        energy.production * energy.transaction_price;
    const double housing_output_nominal =
        housing.construction_output * housing.house_price;
    accounts.gross_output_consumption_nominal =
        real.consumption_output_nominal;
    accounts.gross_output_capital_nominal =
        real.capital_output_nominal;
    accounts.gross_output_energy_nominal = energy_output_nominal;
    accounts.gross_output_housing_nominal = housing_output_nominal;
    accounts.gross_output_nominal =
        real.gross_output_nominal + energy_output_nominal +
        housing_output_nominal;
    accounts.gross_output_real =
        real.consumption_output_real + real.capital_output_real +
        energy.production + housing.construction_output;
    accounts.intermediate_energy_nominal = energy.industry_spending;
    accounts.intermediate_energy_real = energy.industry_units;
    accounts.production_nominal =
        accounts.gross_output_nominal -
        accounts.intermediate_energy_nominal;
    accounts.production_real =
        accounts.gross_output_real - accounts.intermediate_energy_real;
    accounts.nominal_gdp = accounts.production_nominal;
    accounts.real_gdp = accounts.production_real;
    accounts.nominal_gdp_per_capita = safe_ratio(
        accounts.nominal_gdp, static_cast<double>(population.population));
    accounts.real_gdp_per_capita = safe_ratio(
        accounts.real_gdp, static_cast<double>(population.population));
    accounts.gdp_deflator =
        safe_ratio(accounts.nominal_gdp, accounts.real_gdp);

    accounts.household_consumption_goods_nominal =
        real.household_consumption;
    accounts.household_consumption_energy_nominal =
        energy.household_spending;
    accounts.household_consumption_nominal =
        accounts.household_consumption_goods_nominal +
        accounts.household_consumption_energy_nominal;
    accounts.government_consumption_nominal =
        real.government_consumption;
    accounts.machinery_fixed_capital_formation_nominal =
        real.fixed_capital_formation_nominal;
    accounts.residential_fixed_capital_formation_nominal =
        housing_output_nominal;
    accounts.fixed_capital_formation_nominal =
        accounts.machinery_fixed_capital_formation_nominal +
        accounts.residential_fixed_capital_formation_nominal;
    accounts.public_fixed_capital_formation_nominal =
        real.public_fixed_capital_formation;
    accounts.private_fixed_capital_formation_nominal =
        accounts.fixed_capital_formation_nominal -
        accounts.public_fixed_capital_formation_nominal;
    // Energy production that is not consumed remains either in producer
    // inventories or in the strategic reserve.  `energy.sold` includes sales
    // out of the reserve, while a positive reserve flow is a purchase from a
    // private producer.  This expression therefore measures the change in the
    // complete energy stock without double-counting reserve transactions.
    const double energy_inventory_change =
        energy.production - energy.sold +
        std::max(0.0, energy.strategic_reserve_flow);
    accounts.inventory_change_nominal =
        real.inventory_change_nominal +
        energy_inventory_change * energy.transaction_price;
    accounts.inventory_change_real =
        real.inventory_change_real + energy_inventory_change;
    accounts.exports_nominal = external.exports_value;
    accounts.imports_nominal = external.imports_value;
    accounts.net_exports_nominal =
        accounts.exports_nominal - accounts.imports_nominal;
    accounts.exports_real = external.exports_volume;
    accounts.imports_real = external.imports_volume;
    accounts.net_exports_real =
        accounts.exports_real - accounts.imports_real;

    accounts.expenditure_observed_nominal =
        accounts.household_consumption_nominal +
        accounts.government_consumption_nominal +
        accounts.fixed_capital_formation_nominal +
        accounts.inventory_change_nominal +
        accounts.net_exports_nominal;
    accounts.expenditure_residual_nominal =
        accounts.nominal_gdp - accounts.expenditure_observed_nominal;
    accounts.expenditure_residual_share = safe_ratio(
        std::abs(accounts.expenditure_residual_nominal),
        std::abs(accounts.nominal_gdp));
    accounts.expenditure_reconciled_nominal =
        accounts.expenditure_observed_nominal +
        accounts.expenditure_residual_nominal;

    const double household_consumption_real =
        safe_ratio(
            accounts.household_consumption_goods_nominal,
            real.price_index) +
        energy.household_units;
    const double government_consumption_real =
        safe_ratio(accounts.government_consumption_nominal,
                   real.price_index);
    const double fixed_capital_formation_real =
        real.fixed_capital_formation_real +
        housing.construction_output;
    accounts.household_consumption_real = household_consumption_real;
    accounts.government_consumption_real = government_consumption_real;
    accounts.fixed_capital_formation_real =
        fixed_capital_formation_real;
    accounts.expenditure_observed_real =
        household_consumption_real + government_consumption_real +
        fixed_capital_formation_real + accounts.inventory_change_real +
        accounts.net_exports_real;
    accounts.expenditure_residual_real =
        accounts.real_gdp - accounts.expenditure_observed_real;
    accounts.expenditure_reconciled_real =
        accounts.expenditure_observed_real +
        accounts.expenditure_residual_real;

    accounts.compensation_employees_nominal = real.wages_paid;
    accounts.cash_operating_surplus_nominal = real.firm_profit;
    // Native production accounts are measured at basic prices.  Product
    // taxes are therefore an observed zero rather than an unavailable value.
    accounts.net_product_taxes_observed = 0.0;
    accounts.income_observed_nominal =
        accounts.compensation_employees_nominal +
        accounts.cash_operating_surplus_nominal;
    accounts.income_residual_nominal =
        accounts.nominal_gdp - accounts.income_observed_nominal;
    accounts.income_residual_share = safe_ratio(
        std::abs(accounts.income_residual_nominal),
        std::abs(accounts.nominal_gdp));
    accounts.income_reconciled_nominal =
        accounts.income_observed_nominal +
        accounts.income_residual_nominal;
    accounts.production_reconciliation_residual = 0.0;
    const double approach_max = std::max(
        {accounts.nominal_gdp, accounts.expenditure_observed_nominal,
         accounts.income_observed_nominal});
    const double approach_min = std::min(
        {accounts.nominal_gdp, accounts.expenditure_observed_nominal,
         accounts.income_observed_nominal});
    accounts.three_approach_raw_spread = approach_max - approach_min;
    accounts.three_approach_raw_spread_share = safe_ratio(
        accounts.three_approach_raw_spread,
        std::abs(accounts.nominal_gdp));
    accounts.transfers_excluded = real.transfer_payments;
    accounts.price_basis_basic = 1.0;
    accounts.scope_excludes_imputed_housing = 1.0;
    accounts.scope_excludes_unpriced_financial = 1.0;
    accounts.annualized_nominal_gdp = 365.0 * accounts.nominal_gdp;
    accounts.credit_to_annualized_gdp = safe_ratio(
        monetary.total_loan_principal, accounts.annualized_nominal_gdp);
    accounts.gov_deficit_to_nominal_gdp = safe_ratio(
        real.government_deficit, accounts.nominal_gdp);
    accounts.gov_debt_to_annualized_gdp = safe_ratio(
        government_debt, accounts.annualized_nominal_gdp);
    accounts.debt_service_to_nominal_gdp = safe_ratio(
        monetary.household_interest_paid + monetary.principal_repaid,
        accounts.nominal_gdp);
    accounts.total_debt_service_to_nominal_gdp = safe_ratio(
        monetary.loan_interest_paid + monetary.principal_repaid,
        accounts.nominal_gdp);
    return accounts;
}

} // namespace

Result<double> MetricFrame::value(std::size_t economy,
                                  std::size_t metric) const noexcept {
    if (economy >= economy_count || metric >= kM10MetricCount) {
        return Status(ErrorCode::out_of_range, "metric frame index is out of range");
    }
    const std::size_t offset = economy * kM10MetricCount + metric;
    if (offset >= valid.size() || offset >= values.size() || valid[offset] == 0U) {
        return Status(ErrorCode::not_found, "metric frame value is unavailable");
    }
    return values[offset];
}

MetricHistory::MetricHistory(std::size_t economy_count, std::size_t metric_count,
                             std::size_t capacity_frames)
    : economy_count_(economy_count), metric_count_(metric_count),
      capacity_frames_(capacity_frames), ticks_(capacity_frames),
      values_(capacity_frames * economy_count * metric_count),
      valid_(capacity_frames * economy_count * metric_count) {}

Result<MetricHistory>
MetricHistory::restore(std::size_t economy_count, std::size_t metric_count,
                       std::size_t capacity_frames,
                       std::uint64_t first_sequence,
                       std::span<const MetricFrame> frames) {
    if (economy_count == 0U || metric_count == 0U ||
        capacity_frames == 0U || frames.empty() ||
        frames.size() > capacity_frames ||
        first_sequence >
            std::numeric_limits<std::uint64_t>::max() - frames.size()) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history restore shape is invalid");
    }
    MetricHistory result(economy_count, metric_count, capacity_frames);
    result.next_sequence_ = first_sequence;
    for (const auto &frame : frames) {
        auto status = result.append(frame);
        if (!status.ok()) {
            return status;
        }
    }
    return result;
}

Status MetricHistory::append(const MetricFrame &frame) {
    if (capacity_frames_ == 0U || frame.economy_count != economy_count_ ||
        frame.values.size() != frame_width() ||
        frame.valid.size() != frame_width()) {
        return Status(ErrorCode::contract_violation,
                      "metric history frame shape does not match");
    }
    const std::size_t slot =
        static_cast<std::size_t>(next_sequence_ % capacity_frames_);
    const std::size_t offset = slot * frame_width();
    ticks_[slot] = frame.tick;
    std::copy(frame.values.begin(), frame.values.end(), values_.begin() +
                                                        static_cast<std::ptrdiff_t>(
                                                            offset));
    std::copy(frame.valid.begin(), frame.valid.end(), valid_.begin() +
                                                      static_cast<std::ptrdiff_t>(
                                                          offset));
    ++next_sequence_;
    size_ = std::min(capacity_frames_, size_ + 1U);
    return Status::success();
}

Result<MetricHistoryPage>
MetricHistory::page(std::uint64_t first_sequence,
                    std::size_t maximum_frames) const {
    if (first_sequence < oldest_sequence() || first_sequence > next_sequence_) {
        return Status(ErrorCode::out_of_range,
                      "metric history cursor is outside the retained window");
    }
    MetricHistoryPage result;
    result.first_sequence = first_sequence;
    const std::uint64_t available = next_sequence_ - first_sequence;
    const std::size_t count = static_cast<std::size_t>(
        std::min<std::uint64_t>(available, maximum_frames));
    result.frames.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint64_t sequence = first_sequence + index;
        const std::size_t slot =
            static_cast<std::size_t>(sequence % capacity_frames_);
        const std::size_t offset = slot * frame_width();
        MetricFrame frame;
        frame.tick = ticks_[slot];
        frame.economy_count = economy_count_;
        frame.values.assign(
            values_.begin() + static_cast<std::ptrdiff_t>(offset),
            values_.begin() + static_cast<std::ptrdiff_t>(offset + frame_width()));
        frame.valid.assign(
            valid_.begin() + static_cast<std::ptrdiff_t>(offset),
            valid_.begin() + static_cast<std::ptrdiff_t>(offset + frame_width()));
        result.frames.push_back(std::move(frame));
    }
    result.next_sequence = first_sequence + count;
    return result;
}

std::uint64_t MetricHistory::retained_bytes() const noexcept {
    return static_cast<std::uint64_t>(ticks_.capacity()) * sizeof(Tick) +
           static_cast<std::uint64_t>(values_.capacity()) * sizeof(double) +
           static_cast<std::uint64_t>(valid_.capacity()) * sizeof(std::uint8_t);
}

MetricPipeline::MetricPipeline(std::size_t economy_count,
                               std::size_t history_capacity_frames)
    : history_(economy_count, kM10MetricCount, history_capacity_frames) {}

Status MetricPipeline::capture(const simulation::M9World &world) {
    const MetricFrame *previous = captured_ ? &current_ : nullptr;
    auto built = build_metric_frame(world, previous);
    if (!built.ok()) {
        return built.status();
    }
    return commit(std::move(*built.get_if()));
}

Status MetricPipeline::commit(MetricFrame frame) {
    auto status = history_.append(frame);
    if (!status.ok()) {
        return status;
    }
    current_ = std::move(frame);
    captured_ = true;
    return Status::success();
}

Result<MetricPipeline> MetricPipeline::restore(MetricHistory history) {
    if (history.size() == 0U) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history cannot restore empty");
    }
    auto last = history.page(history.next_sequence() - 1U, 1U);
    if (!last.ok() || last.get_if()->frames.size() != 1U) {
        return Status(ErrorCode::corrupt_input,
                      "M10 metric history last frame is unavailable");
    }
    MetricPipeline result;
    result.current_ = std::move(last.get_if()->frames.front());
    result.history_ = std::move(history);
    result.captured_ = true;
    return result;
}

std::span<const MetricDescriptor> public_metric_descriptors() noexcept {
    return {kDescriptors.data(), kM10PublicMetricCount};
}

std::span<const MetricDescriptor> metric_descriptors() noexcept {
    return kDescriptors;
}

Result<std::size_t>
public_metric_index(std::string_view stable_id) noexcept {
    const auto descriptors = public_metric_descriptors();
    const auto found = std::find_if(
        descriptors.begin(), descriptors.end(),
        [stable_id](const MetricDescriptor &descriptor) {
            return descriptor.stable_id == stable_id;
        });
    if (found == descriptors.end()) {
        return Status(ErrorCode::not_found,
                      "public metric stable ID is unknown");
    }
    return static_cast<std::size_t>(
        std::distance(descriptors.begin(), found));
}

Result<std::size_t> metric_index(std::string_view stable_id) noexcept {
    const auto descriptors = metric_descriptors();
    const auto found = std::find_if(
        descriptors.begin(), descriptors.end(),
        [stable_id](const MetricDescriptor &descriptor) {
            return descriptor.stable_id == stable_id;
        });
    if (found == descriptors.end()) {
        return Status(ErrorCode::not_found,
                      "metric stable ID is unknown");
    }
    return static_cast<std::size_t>(
        std::distance(descriptors.begin(), found));
}

Result<MetricFrame>
build_metric_frame(const simulation::M9World &world,
                   const MetricFrame *previous) {
    const auto &metrics = world.last_metrics();
    if (metrics.domestic.size() != world.economy_count() ||
        metrics.external.size() != world.economy_count()) {
        return Status(ErrorCode::invariant_violation,
                      "M10 metric source dimensions disagree");
    }
    if (previous != nullptr && previous->economy_count != world.economy_count()) {
        return Status(ErrorCode::contract_violation,
                      "M10 previous metric frame shape disagrees");
    }

    MetricFrame frame;
    frame.tick = world.tick();
    frame.economy_count = world.economy_count();
    // Availability is represented exclusively by `valid`. Keeping the backing
    // value finite makes metric frames deterministic and safely serializable
    // even when a statistic (for example a wage quantile before the first
    // hire) is not yet available.
    frame.values.assign(frame.economy_count * kM10MetricCount, 0.0);
    frame.valid.assign(frame.values.size(), 0U);

    for (std::size_t economy = 0; economy < frame.economy_count; ++economy) {
        const auto &domestic = metrics.domestic[economy];
        const auto &external = metrics.external[economy];
        const auto &real = m4(domestic);
        const auto &monetary = m5(domestic);
        const auto &securities = m6(domestic);
        const auto &population = m7(domestic);
        const auto *root = world.economy_root(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *real_runtime = world.economy_real_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *financial = world.economy_financial_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *population_runtime = world.economy_population_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto *runtime = world.economy_runtime(
            EconomyId(static_cast<std::uint64_t>(economy)));
        const auto domestic_policy = world.domestic_policy(
            EconomyId(static_cast<std::uint64_t>(economy)));
        if (root == nullptr || real_runtime == nullptr || financial == nullptr ||
            population_runtime == nullptr || runtime == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "M10 metric source economy is unavailable");
        }
        if (!domestic_policy.ok()) {
            return domestic_policy.status();
        }

        double energy_stock = runtime->strategic_reserve_stock;
        for (const auto &producer : runtime->energy_producers) {
            if (producer.active) {
                energy_stock += std::max(0.0, producer.inventory);
            }
        }
        for (const auto &input : runtime->energy_inputs) {
            if (input.active) {
                energy_stock += std::max(0.0, input.stock);
            }
        }

        const bool refresh_distribution =
            previous == nullptr ||
            frame.tick.value() % 30U == 0U ||
            !previous->value(economy, 41U).ok() ||
            (!previous->value(economy, 42U).ok() &&
             population_runtime->employment.active_count() > 0U);
        if (refresh_distribution) {
            const std::size_t household_slots =
                root->households.slot_count() + 1U;
            std::vector<double> debt(household_slots, 0.0);
            std::vector<double> securities_value(household_slots, 0.0);
            std::vector<double> housing_value(household_slots, 0.0);
            for (const auto &loan : root->loans.records()) {
                if (!loan.active ||
                    loan.borrower.kind() != core::OwnerKind::household ||
                    loan.borrower.value() >= debt.size()) {
                    continue;
                }
                debt[loan.borrower.value()] +=
                    std::max(0.0, loan.principal.value());
            }
            for (const auto &lot : financial->securities.lots()) {
                if (!lot.active() ||
                    lot.holder.kind() != core::OwnerKind::household ||
                    lot.holder.value() >= securities_value.size()) {
                    continue;
                }
                securities_value[lot.holder.value()] +=
                    std::max(
                        0.0,
                        security_market_value(financial->securities, lot));
            }
            for (const auto &dwelling : runtime->properties.records()) {
                if (!dwelling.active ||
                    dwelling.owner.kind() != core::OwnerKind::household ||
                    dwelling.owner.value() >= housing_value.size()) {
                    continue;
                }
                housing_value[dwelling.owner.value()] +=
                    std::max(0.0, runtime->house_price);
            }

            std::vector<double> incomes;
            std::vector<double> wealth;
            std::vector<EquivalizedConsumption> consumption;
            std::vector<WeightedObservation> income_observations;
            std::vector<WeightedObservation> wealth_observations;
            std::vector<WeightedObservation> consumption_observations;
            const std::size_t household_count =
                root->households.alive_count();
            incomes.reserve(household_count);
            wealth.reserve(household_count);
            consumption.reserve(household_count);
            income_observations.reserve(household_count);
            wealth_observations.reserve(household_count);
            consumption_observations.reserve(household_count);
            double total_income = 0.0;
            double total_consumption = 0.0;
            double welfare_weighted_sum = 0.0;
            double welfare_weight = 0.0;
            const double price_index =
                std::max(1.0e-9, real.price_index);
            root->households.for_each_alive(
                [&](HouseholdId household_id,
                    const core::HouseholdComponent &household) {
                    const std::size_t household_index =
                        static_cast<std::size_t>(household_id.value());
                    const std::size_t persons =
                        population_runtime->membership.members(
                            household_id).size();
                    if (persons == 0U) {
                        return;
                    }
                    const double person_weight =
                        static_cast<double>(persons);
                    const double scale = std::sqrt(person_weight);
                    const double energy_spent =
                        household_index < runtime->household_energy.size() &&
                            runtime->household_energy[household_index].active
                        ? runtime->household_energy[household_index].spent
                        : 0.0;
                    const double household_consumption =
                        std::max(0.0, household.spent + energy_spent);
                    const double equivalized_consumption =
                        household_consumption / scale;
                    const double equivalized_real_consumption =
                        equivalized_consumption / price_index;
                    const auto balance =
                        root->postings.balance(household.primary_account);
                    const double cash =
                        balance.ok()
                        ? std::max(0.0, balance.get_if()->value())
                        : 0.0;
                    const double net_wealth = std::max(
                        0.0,
                        cash + securities_value[household_index] +
                            housing_value[household_index] -
                            debt[household_index]);

                    incomes.push_back(household.income_realized);
                    wealth.push_back(net_wealth);
                    consumption.push_back({
                        equivalized_consumption,
                        persons,
                    });
                    income_observations.push_back({
                        std::max(0.0, household.income_realized / scale),
                        person_weight,
                    });
                    wealth_observations.push_back({
                        net_wealth / scale,
                        person_weight,
                    });
                    consumption_observations.push_back({
                        equivalized_real_consumption,
                        person_weight,
                    });
                    total_income += household.income_realized;
                    total_consumption += household_consumption;
                    welfare_weighted_sum +=
                        person_weight *
                        std::log(std::max(
                            1.0e-9, equivalized_real_consumption));
                    welfare_weight += person_weight;
                });

            const auto income_distribution =
                decile_distribution(std::move(income_observations));
            const auto wealth_distribution =
                decile_distribution(std::move(wealth_observations));
            const auto consumption_distribution =
                decile_distribution(std::move(consumption_observations));
            set(frame, economy, 7U, gini(std::move(incomes)));
            set(
                frame, economy, 12U,
                relative_consumption_poverty(std::move(consumption)));
            if (!wealth.empty()) {
                set(frame, economy, 41U, gini(std::move(wealth)));
            }

            std::vector<WeightedObservation> wages;
            wages.reserve(population_runtime->employment.active_count());
            for (const auto &job :
                 population_runtime->employment.records()) {
                if (!job.active || job.suspended ||
                    job.wage <= 0.0 || job.hours <= 0.0) {
                    continue;
                }
                wages.push_back({job.wage, job.hours});
            }
            if (!wages.empty()) {
                const double p10 = weighted_quantile(wages, 0.10);
                const double p90 =
                    weighted_quantile(std::move(wages), 0.90);
                if (finite(p10) && finite(p90) && p10 > 1.0e-12) {
                    set(frame, economy, 42U, p90 / p10);
                }
            }
            if (welfare_weight > 1.0e-12) {
                set(
                    frame, economy, 43U,
                    welfare_weighted_sum / welfare_weight);
            }
            if (std::abs(total_income) > 1.0e-12) {
                set(
                    frame, economy, 44U,
                    (total_income - total_consumption) / total_income);
            }
            set(
                frame, economy, 45U,
                consumption_distribution.bottom_mean);
            for (std::size_t decile = 0U; decile < 10U; ++decile) {
                set(
                    frame, economy, 46U + decile,
                    income_distribution.shares[decile]);
                set(
                    frame, economy, 56U + decile,
                    wealth_distribution.shares[decile]);
                set(
                    frame, economy, 66U + decile,
                    consumption_distribution.shares[decile]);
            }
        } else {
            for (const std::size_t metric : {
                     7U, 12U, 41U, 42U, 43U, 44U, 45U, 46U, 47U, 48U,
                     49U, 50U, 51U, 52U, 53U, 54U, 55U, 56U, 57U, 58U,
                     59U, 60U, 61U, 62U, 63U, 64U, 65U, 66U, 67U, 68U,
                     69U, 70U, 71U, 72U, 73U, 74U, 75U,
                 }) {
                const auto carried = previous->value(economy, metric);
                if (carried.ok()) {
                    set(frame, economy, metric, *carried.get_if());
                }
            }
            for (std::size_t metric = kM10BasePublicMetricCount;
                 metric < kM10PublicMetricCount; ++metric) {
                const auto carried = previous->value(economy, metric);
                if (carried.ok()) {
                    set(frame, economy, metric, *carried.get_if());
                }
            }
        }
        const double nominal_output = real.nominal_output;
        const auto treasury_balance =
            root->postings.balance(root->institutions.treasury_account);
        if (!treasury_balance.ok()) {
            return treasury_balance.status();
        }
        const bool has_government =
            (real_runtime->capability_mask &
             simulation::capability_bit(simulation::M4Capability::government)) != 0U;
        const double government_debt =
            has_government
                ? financial->securities.total_bond_face().value() -
                      treasury_balance.get_if()->value()
                : 0.0;
        const auto national_accounts =
            build_national_accounts(domestic, external, government_debt);

        set(frame, economy, 0U, population.mean_hourly_wage);
        set(frame, economy, 1U,
            national_accounts.credit_to_annualized_gdp);
        set(frame, economy, 2U, population.employed_fte);
        set(frame, economy, 3U,
            domestic.energy.transaction_price > 1.0e-12
                ? domestic.energy.transaction_price
                : runtime->energy_price);
        set(frame, economy, 4U, domestic.energy.subsidy_paid);
        set(frame, economy, 5U,
            nominal_output > 1.0e-12
                ? government_debt / (365.0 * nominal_output)
                : 0.0);
        set(frame, economy, 6U,
            nominal_output > 1.0e-12
                ? real.government_deficit / nominal_output
                : 0.0);
        double inflation = 0.0;
        if (previous != nullptr) {
            const auto previous_price = previous->value(economy, 13U);
            if (previous_price.ok() && *previous_price.get_if() > 1.0e-12) {
                inflation = real.price_index / *previous_price.get_if() - 1.0;
            }
        }
        set(frame, economy, 8U, inflation);
        set(frame, economy, 9U, static_cast<double>(monetary.bank_failures));
        set(frame, economy, 10U, monetary.policy_rate);
        set(frame, economy, 11U, static_cast<double>(population.population));
        set(frame, economy, 13U, real.price_index);
        set(frame, economy, 14U, real.real_output);
        set(frame, economy, 15U, population.unemployment_rate);
        set(frame, economy, 16U, external.current_account);
        set(frame, economy, 17U, external.exchange_rate);
        set(frame, economy, 18U, external.exports_volume);
        set(frame, economy, 19U, external.imports_volume);
        set(frame, economy, 20U, external.migrant_stock_abroad);
        set(frame, economy, 21U, external.net_foreign_assets);
        set(frame, economy, 22U, external.remittances_received);

        set(frame, economy, 23U, monetary.total_reserves);

        std::unordered_map<std::uint64_t, double> deposits_by_node;
        for (const auto &account : root->postings.records()) {
            if (!account.open ||
                account.key.kind != core::AccountKind::deposit) {
                continue;
            }
            deposits_by_node[account.key.settlement_node.value()] +=
                std::max(0.0, account.balance.value());
        }
        if (refresh_distribution) {
            std::unordered_map<std::uint64_t, double> household_debt;
            std::unordered_map<std::uint64_t, double> firm_debt;
            for (const auto &loan : root->loans.records()) {
                if (!loan.active || loan.principal.value() <= 0.0) {
                    continue;
                }
                if (loan.borrower.kind() == core::OwnerKind::household) {
                    household_debt[loan.borrower.value()] +=
                        loan.principal.value();
                } else if (loan.borrower.kind() ==
                           core::OwnerKind::firm) {
                    firm_debt[loan.borrower.value()] +=
                        loan.principal.value();
                }
            }

            std::unordered_map<std::uint64_t, bool> active_firm;
            std::vector<double> tobin_q;
            tobin_q.reserve(financial->firms.size());
            for (const auto &record : financial->firms) {
                active_firm[record.firm.value()] = record.active;
                if (record.active && finite(record.tobin_q_ema)) {
                    tobin_q.push_back(record.tobin_q_ema);
                }
            }

            std::array<double, 4U> sector_firms{};
            std::array<double, 4U> sector_sales{};
            std::array<double, 4U> sector_employment{};
            std::vector<double> firm_debt_observations;
            std::vector<double> firm_output_observations;
            firm_debt_observations.reserve(root->firms.alive_count());
            firm_output_observations.reserve(root->firms.alive_count());
            double inventory_total = 0.0;
            double sales_total = 0.0;
            double markup_total = 0.0;
            double markup_count = 0.0;
            double producing_firms = 0.0;
            double selling_firms = 0.0;
            double borrowing_firms = 0.0;
            root->firms.for_each_alive(
                [&](FirmId firm_id, const core::FirmComponent &firm) {
                    const auto active = active_firm.find(
                        firm_id.value());
                    if (active != active_firm.end() && !active->second) {
                        return;
                    }
                    const auto sector = static_cast<std::size_t>(
                        firm.sector);
                    if (sector < sector_firms.size()) {
                        sector_firms[sector] += 1.0;
                        sector_sales[sector] +=
                            std::max(0.0, firm.sales_previous);
                    }
                    const double sales =
                        std::max(0.0, firm.sales_previous);
                    const double output_value =
                        sales * std::max(0.0, firm.posted_price.value());
                    const double debt =
                        firm_debt[firm_id.value()];
                    firm_debt_observations.push_back(debt);
                    firm_output_observations.push_back(output_value);
                    inventory_total += std::max(
                        0.0, firm.goods_inventory.value());
                    sales_total += sales;
                    markup_total += std::max(0.0, firm.markup);
                    markup_count += 1.0;
                    producing_firms +=
                        (firm.hired_previous > 1.0e-12 ||
                         sales > 1.0e-12)
                        ? 1.0
                        : 0.0;
                    selling_firms += sales > 1.0e-12 ? 1.0 : 0.0;
                    borrowing_firms += debt > 1.0e-12 ? 1.0 : 0.0;
                });

            for (const auto &job :
                 population_runtime->employment.records()) {
                if (!job.active || job.suspended ||
                    job.hours <= 0.0) {
                    continue;
                }
                const auto *firm = root->firms.get(job.firm);
                if (firm == nullptr) {
                    continue;
                }
                const auto sector = static_cast<std::size_t>(
                    firm->sector);
                if (sector < sector_employment.size()) {
                    sector_employment[sector] += job.hours;
                }
            }

            std::unordered_map<std::uint64_t, double> household_equity;
            std::unordered_map<std::uint64_t, double> household_securities;
            for (const auto &lot : financial->securities.lots()) {
                if (!lot.active() ||
                    lot.holder.kind() != core::OwnerKind::household) {
                    continue;
                }
                const double value = std::max(
                    0.0, security_market_value(
                             financial->securities, lot));
                household_securities[lot.holder.value()] += value;
                if (lot.security.kind() ==
                    core::SecurityKind::equity) {
                    household_equity[lot.holder.value()] += value;
                }
            }

            std::vector<double> household_debt_observations;
            std::vector<double> household_equity_observations;
            household_debt_observations.reserve(
                root->households.alive_count());
            household_equity_observations.reserve(
                root->households.alive_count());
            double household_cash = 0.0;
            double household_security_value = 0.0;
            root->households.for_each_alive(
                [&](HouseholdId household_id,
                    const core::HouseholdComponent &household) {
                    household_debt_observations.push_back(
                        household_debt[household_id.value()]);
                    household_equity_observations.push_back(
                        household_equity[household_id.value()]);
                    const auto balance = root->postings.balance(
                        household.primary_account);
                    if (balance.ok()) {
                        household_cash += std::max(
                            0.0, balance.get_if()->value());
                    }
                    household_security_value +=
                        household_securities[household_id.value()];
                });

            std::array<double, 7U> male_by_age{};
            std::array<double, 7U> female_by_age{};
            std::array<double, 6U> population_by_labor_age{};
            std::array<double, 6U> participating_by_age{};
            std::array<double, 6U> employed_by_age{};
            double child_population = 0.0;
            double working_age_population = 0.0;
            double elder_population = 0.0;
            for (const auto person_id :
                 population_runtime->persons.alive_ids()) {
                const auto *person =
                    population_runtime->persons.get(person_id);
                if (person == nullptr) {
                    continue;
                }
                const auto age_days = std::max<std::int64_t>(
                    0, static_cast<std::int64_t>(
                           population_runtime->current_calendar_day) -
                           static_cast<std::int64_t>(
                               person->birth_day));
                const auto age = static_cast<std::uint32_t>(
                    age_days / 365);
                const auto bucket = age_bucket(age);
                if (person->sex == core::PersonSex::male) {
                    male_by_age[bucket] += 1.0;
                } else {
                    female_by_age[bucket] += 1.0;
                }
                if (bucket > 0U) {
                    const auto labor_bucket = bucket - 1U;
                    population_by_labor_age[labor_bucket] += 1.0;
                    participating_by_age[labor_bucket] +=
                        person->participating ? 1.0 : 0.0;
                    employed_by_age[labor_bucket] +=
                        population_runtime->employment.active_hours(
                            person_id) > 1.0e-12
                        ? 1.0
                        : 0.0;
                }
                if (age < population_runtime->rules.working_age) {
                    child_population += 1.0;
                } else if (age <
                           population_runtime->rules.retirement_age) {
                    working_age_population += 1.0;
                } else {
                    elder_population += 1.0;
                }
            }

            std::array<std::vector<WeightedObservation>, 3U>
                consumption_by_generation;
            const double consumption_price =
                std::max(1.0e-9, real.price_index);
            root->households.for_each_alive(
                [&](HouseholdId household_id,
                    const core::HouseholdComponent &household) {
                    const auto members =
                        population_runtime->membership.members(
                            household_id);
                    if (members.empty()) {
                        return;
                    }
                    std::array<double, 3U> group_members{};
                    for (const auto person_id : members) {
                        const auto *person =
                            population_runtime->persons.get(person_id);
                        if (person == nullptr || !person->alive) {
                            continue;
                        }
                        const auto age_days = std::max<std::int64_t>(
                            0, static_cast<std::int64_t>(
                                   population_runtime
                                       ->current_calendar_day) -
                                   static_cast<std::int64_t>(
                                       person->birth_day));
                        const auto age = static_cast<std::uint32_t>(
                            age_days / 365);
                        const std::size_t group =
                            age <
                                    population_runtime->rules
                                        .working_age
                            ? 0U
                            : (age <
                                       population_runtime->rules
                                           .retirement_age
                                   ? 1U
                                   : 2U);
                        group_members[group] += 1.0;
                    }
                    const auto index = static_cast<std::size_t>(
                        household_id.value());
                    const double energy_spent =
                        index < runtime->household_energy.size() &&
                            runtime->household_energy[index].active
                        ? runtime->household_energy[index].spent
                        : 0.0;
                    const double equivalized =
                        std::max(
                            0.0, household.spent + energy_spent) /
                        std::sqrt(
                            static_cast<double>(members.size())) /
                        consumption_price;
                    for (std::size_t group = 0U;
                         group < group_members.size(); ++group) {
                        if (group_members[group] > 0.0) {
                            consumption_by_generation[group].push_back({
                                equivalized,
                                group_members[group],
                            });
                        }
                    }
                });

            std::unordered_set<std::uint64_t> tenant_households;
            std::unordered_set<std::uint64_t> landlord_households;
            for (const auto &tenancy : runtime->tenancies) {
                if (!tenancy.active) {
                    continue;
                }
                tenant_households.insert(tenancy.tenant.value());
                landlord_households.insert(tenancy.landlord.value());
            }
            double rental_vacancies = 0.0;
            for (const auto &dwelling : runtime->properties.records()) {
                if (!dwelling.active ||
                    dwelling.owner.kind() !=
                        core::OwnerKind::household) {
                    continue;
                }
                if (!dwelling.occupant.valid()) {
                    rental_vacancies += 1.0;
                } else if (dwelling.occupant.value() !=
                           dwelling.owner.value()) {
                    landlord_households.insert(
                        dwelling.owner.value());
                    tenant_households.insert(
                        dwelling.occupant.value());
                }
            }

            double builder_work_in_progress = 0.0;
            double builder_inventory = 0.0;
            for (const auto &builder : runtime->builders) {
                if (!builder.active) {
                    continue;
                }
                builder_work_in_progress +=
                    std::max(0.0, builder.work_in_progress);
                builder_inventory +=
                    std::max(0.0, builder.finished_inventory);
            }
            const auto mortgage_count = static_cast<double>(
                std::count_if(
                    runtime->mortgages.begin(),
                    runtime->mortgages.end(),
                    [](const simulation::MortgageRecord &mortgage) {
                        return mortgage.active;
                    }));

            const double population_total =
                static_cast<double>(population.population);
            const double household_debt_total =
                std::accumulate(
                    household_debt_observations.begin(),
                    household_debt_observations.end(), 0.0);
            const double firm_debt_total =
                std::accumulate(
                    firm_debt_observations.begin(),
                    firm_debt_observations.end(), 0.0);
            const double deposit_total = std::accumulate(
                deposits_by_node.begin(), deposits_by_node.end(), 0.0,
                [](double total, const auto &entry) {
                    return total + entry.second;
                });
            const double q_mean =
                tobin_q.empty()
                ? 0.0
                : std::accumulate(
                      tobin_q.begin(), tobin_q.end(), 0.0) /
                      static_cast<double>(tobin_q.size());
            const double q_variance =
                tobin_q.empty()
                ? 0.0
                : std::accumulate(
                      tobin_q.begin(), tobin_q.end(), 0.0,
                      [q_mean](double total, double value) {
                          const double difference = value - q_mean;
                          return total + difference * difference;
                      }) /
                      static_cast<double>(tobin_q.size());
            const double household_equity_total =
                std::accumulate(
                    household_equity_observations.begin(),
                    household_equity_observations.end(), 0.0);
            double previous_wage = 0.0;
            if (previous != nullptr) {
                const auto value = previous->value(economy, 0U);
                if (value.ok()) {
                    previous_wage = *value.get_if();
                }
            }

            set_dashboard(
                frame, economy, DashboardMetric::inventory_to_sales,
                safe_ratio(inventory_total, sales_total));
            set_dashboard(
                frame, economy,
                DashboardMetric::production_realization_rate,
                safe_ratio(
                    real.real_output,
                    national_accounts.gross_output_real));
            set_dashboard(
                frame, economy, DashboardMetric::underemployed_share,
                safe_ratio(
                    population.underemployed_heads,
                    population.employed_heads +
                        population.unemployment));
            set_dashboard(
                frame, economy, DashboardMetric::wage_inflation,
                previous_wage > 1.0e-12
                ? population.mean_hourly_wage / previous_wage - 1.0
                : 0.0);
            set_dashboard(
                frame, economy, DashboardMetric::avg_markup,
                safe_ratio(markup_total, markup_count));
            set_dashboard(
                frame, economy, DashboardMetric::gov_debt,
                government_debt);
            set_dashboard(
                frame, economy, DashboardMetric::bank_deposit_total,
                deposit_total);
            set_dashboard(
                frame, economy, DashboardMetric::household_debt_total,
                household_debt_total);
            set_dashboard(
                frame, economy,
                DashboardMetric::household_debt_total_observed,
                household_debt_total);
            set_dashboard(
                frame, economy, DashboardMetric::firm_debt_total,
                firm_debt_total);
            set_dashboard(
                frame, economy, DashboardMetric::household_debt_gini,
                gini(household_debt_observations));
            set_dashboard(
                frame, economy,
                DashboardMetric::household_debt_top10_share,
                top_decile_share(household_debt_observations));
            set_dashboard(
                frame, economy, DashboardMetric::firm_debt_gini,
                gini(firm_debt_observations));
            set_dashboard(
                frame, economy,
                DashboardMetric::firm_debt_top10_share,
                top_decile_share(firm_debt_observations));
            set_dashboard(
                frame, economy, DashboardMetric::equity_market_cap,
                securities.firm_equity_market_cap +
                    securities.bank_equity_market_cap);
            set_dashboard(
                frame, economy, DashboardMetric::tobin_q_mean,
                q_mean);
            set_dashboard(
                frame, economy, DashboardMetric::tobin_q_dispersion,
                std::sqrt(std::max(0.0, q_variance)));
            set_dashboard(
                frame, economy, DashboardMetric::equity_wealth_share,
                safe_ratio(
                    household_equity_total,
                    household_cash + household_security_value));
            set_dashboard(
                frame, economy, DashboardMetric::equity_ownership_gini,
                gini(household_equity_observations));
            const auto wealth_gini = frame.value(economy, 41U);
            set_dashboard(
                frame, economy,
                DashboardMetric::hh_wealth_gini_incl_equity,
                wealth_gini.ok() ? *wealth_gini.get_if() : 0.0);
            set_dashboard(
                frame, economy, DashboardMetric::mortgage_count,
                mortgage_count);
            set_dashboard(
                frame, economy, DashboardMetric::tenant_share,
                safe_ratio(
                    static_cast<double>(tenant_households.size()),
                    static_cast<double>(
                        population.households_with_members)));
            set_dashboard(
                frame, economy, DashboardMetric::rental_vacancies,
                rental_vacancies);
            set_dashboard(
                frame, economy, DashboardMetric::landlord_count,
                static_cast<double>(landlord_households.size()));
            set_dashboard(
                frame, economy, DashboardMetric::builder_wip_units,
                builder_work_in_progress);
            set_dashboard(
                frame, economy,
                DashboardMetric::builder_inventory_units,
                builder_inventory);
            set_dashboard(
                frame, economy, DashboardMetric::builder_employment,
                sector_employment[
                    static_cast<std::size_t>(
                        core::FirmSector::construction)]);
            set_dashboard(
                frame, economy, DashboardMetric::energy_cost_share,
                safe_ratio(
                    domestic.energy.household_spending,
                    national_accounts.household_consumption_nominal));
            set_dashboard(
                frame, economy, DashboardMetric::energy_coverage_mean,
                safe_ratio(energy_stock, domestic.energy.sold));
            set_dashboard(
                frame, economy,
                DashboardMetric::net_population_growth_rate_annualized,
                safe_ratio(
                    365.0 *
                        (static_cast<double>(population.births) -
                         static_cast<double>(population.deaths)),
                    population_total));
            set_dashboard(
                frame, economy,
                DashboardMetric::birth_rate_per_1000_annualized,
                safe_ratio(
                    365000.0 *
                        static_cast<double>(population.births),
                    population_total));
            set_dashboard(
                frame, economy,
                DashboardMetric::death_rate_per_1000_annualized,
                safe_ratio(
                    365000.0 *
                        static_cast<double>(population.deaths),
                    population_total));
            set_dashboard(
                frame, economy, DashboardMetric::firm_count_c,
                sector_firms[
                    static_cast<std::size_t>(
                        core::FirmSector::consumption)]);
            set_dashboard(
                frame, economy, DashboardMetric::firm_count_k,
                sector_firms[
                    static_cast<std::size_t>(
                        core::FirmSector::capital)]);
            set_dashboard(
                frame, economy, DashboardMetric::firm_count_e,
                sector_firms[
                    static_cast<std::size_t>(
                        core::FirmSector::energy)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::firm_count_construction,
                sector_firms[
                    static_cast<std::size_t>(
                        core::FirmSector::construction)]);
            set_dashboard(
                frame, economy, DashboardMetric::n_firms_producing,
                producing_firms);
            set_dashboard(
                frame, economy, DashboardMetric::n_firms_selling,
                selling_firms);
            set_dashboard(
                frame, economy, DashboardMetric::n_firms_borrowing,
                borrowing_firms);
            set_dashboard(
                frame, economy,
                DashboardMetric::firm_size_gini_output,
                gini(firm_output_observations));
            set_dashboard(
                frame, economy,
                DashboardMetric::firm_size_top_share_output,
                top_decile_share(firm_output_observations));
            set_dashboard(
                frame, economy,
                DashboardMetric::firm_size_pareto_slope,
                pareto_slope(firm_output_observations));
            set_dashboard(
                frame, economy,
                DashboardMetric::working_age_population,
                working_age_population);
            set_dashboard(
                frame, economy, DashboardMetric::child_population,
                child_population);
            set_dashboard(
                frame, economy, DashboardMetric::child_share,
                safe_ratio(child_population, population_total));
            set_dashboard(
                frame, economy, DashboardMetric::adult_share,
                safe_ratio(working_age_population, population_total));
            set_dashboard(
                frame, economy, DashboardMetric::elder_population,
                elder_population);
            set_dashboard(
                frame, economy, DashboardMetric::elder_share,
                safe_ratio(elder_population, population_total));
            set_dashboard(
                frame, economy,
                DashboardMetric::child_median_consumption,
                consumption_by_generation[0U].empty()
                ? 0.0
                : weighted_quantile(
                      consumption_by_generation[0U], 0.5));
            set_dashboard(
                frame, economy,
                DashboardMetric::adult_median_consumption,
                consumption_by_generation[1U].empty()
                ? 0.0
                : weighted_quantile(
                      consumption_by_generation[1U], 0.5));
            set_dashboard(
                frame, economy,
                DashboardMetric::elder_median_consumption,
                consumption_by_generation[2U].empty()
                ? 0.0
                : weighted_quantile(
                      consumption_by_generation[2U], 0.5));
            set_dashboard(
                frame, economy,
                DashboardMetric::labor_sector_consumption_fte,
                sector_employment[
                    static_cast<std::size_t>(
                        core::FirmSector::consumption)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::labor_sector_capital_fte,
                sector_employment[
                    static_cast<std::size_t>(
                        core::FirmSector::capital)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::labor_sector_energy_fte,
                sector_employment[
                    static_cast<std::size_t>(
                        core::FirmSector::energy)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::labor_sector_construction_fte,
                sector_employment[
                    static_cast<std::size_t>(
                        core::FirmSector::construction)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::sector_consumption_sales,
                sector_sales[
                    static_cast<std::size_t>(
                        core::FirmSector::consumption)]);
            set_dashboard(
                frame, economy, DashboardMetric::sector_capital_sales,
                sector_sales[
                    static_cast<std::size_t>(
                        core::FirmSector::capital)]);
            set_dashboard(
                frame, economy, DashboardMetric::sector_energy_sales,
                sector_sales[
                    static_cast<std::size_t>(
                        core::FirmSector::energy)]);
            set_dashboard(
                frame, economy,
                DashboardMetric::sector_construction_sales,
                sector_sales[
                    static_cast<std::size_t>(
                        core::FirmSector::construction)]);
            for (std::size_t age = 0U; age < 6U; ++age) {
                set_dashboard(
                    frame, economy,
                    static_cast<DashboardMetric>(
                        static_cast<std::size_t>(
                            DashboardMetric::
                                age_15_24_participation) +
                        age),
                    safe_ratio(
                        participating_by_age[age],
                        population_by_labor_age[age]));
                set_dashboard(
                    frame, economy,
                    static_cast<DashboardMetric>(
                        static_cast<std::size_t>(
                            DashboardMetric::age_15_24_employment) +
                        age),
                    safe_ratio(
                        employed_by_age[age],
                        population_by_labor_age[age]));
            }
            for (std::size_t age = 0U; age < 7U; ++age) {
                set_dashboard(
                    frame, economy,
                    static_cast<DashboardMetric>(
                        static_cast<std::size_t>(
                            DashboardMetric::pyramid_male_0_14) +
                        age * 2U),
                    male_by_age[age]);
                set_dashboard(
                    frame, economy,
                    static_cast<DashboardMetric>(
                        static_cast<std::size_t>(
                            DashboardMetric::pyramid_female_0_14) +
                        age * 2U),
                    female_by_age[age]);
            }
        }
        std::size_t bank_count = 0U;
        std::size_t reserve_floor_breaches = 0U;
        for (const auto &reserve : root->reserves.records()) {
            const auto *bank = root->banks.get(reserve.bank);
            if (bank == nullptr || !bank->alive) {
                continue;
            }
            ++bank_count;
            const double floor =
                domestic_policy.get_if()
                    ->fiscal_monetary.reserve_floor_fraction *
                deposits_by_node[bank->settlement_node.value()];
            if (reserve.balance.value() + 1.0e-9 < floor) {
                ++reserve_floor_breaches;
            }
        }
        set(frame, economy, 24U,
            bank_count == 0U
                ? 0.0
                : static_cast<double>(reserve_floor_breaches) /
                      static_cast<double>(bank_count));

        std::size_t near_failure_banks = 0U;
        for (const auto &capital : root->bank_capital.records()) {
            if (capital.alive && capital.closing_capital >= 0.0 &&
                capital.closing_capital <
                    financial->policy.bank_minimum_capital) {
                ++near_failure_banks;
            }
        }
        set(frame, economy, 25U,
            static_cast<double>(near_failure_banks));

        set(frame, economy, 26U, energy_stock);
        set(frame, economy, 27U, domestic.energy.unfilled);

        double fx_reserves = 0.0;
        for (const auto &peg : world.pegs()) {
            if (peg.pegger.value() == economy) {
                fx_reserves = peg.reserves;
                break;
            }
        }
        set(frame, economy, 28U, fx_reserves);

        std::size_t disclosed_count = 0U;
        std::size_t active_count = 0U;
        double maximum_severity = 0.0;
        std::uint64_t time_to_next = std::numeric_limits<std::uint64_t>::max();
        std::array<double, 9U> kind_severity{};
        for (const auto &shock : world.shocks()) {
            if (!shock_relevant(shock, economy) ||
                !shock_disclosed(shock, world.tick())) {
                continue;
            }
            ++disclosed_count;
            time_to_next = std::min(
                time_to_next,
                shock.start.value() > world.tick().value()
                    ? shock.start.value() - world.tick().value()
                    : 0U);
            const double disclosed_severity =
                shock_severity(shock, world.tick(), true);
            const auto kind =
                static_cast<std::size_t>(shock.kind);
            kind_severity[kind] =
                std::max(kind_severity[kind], disclosed_severity);
            const double active_severity =
                shock_severity(shock, world.tick(), false);
            const bool active =
                shock.kind == simulation::ShockKind::capital_destruction
                    ? world.tick() == shock.start
                    : active_severity > 0.0;
            if (active) {
                ++active_count;
                maximum_severity =
                    std::max(maximum_severity, active_severity);
            }
        }
        set(frame, economy, 29U, static_cast<double>(disclosed_count));
        set(frame, economy, 30U, static_cast<double>(active_count));
        set(frame, economy, 31U, maximum_severity);
        set(frame, economy, 32U,
            time_to_next == std::numeric_limits<std::uint64_t>::max()
                ? 0.0
                : static_cast<double>(time_to_next));
        for (std::size_t kind = 0U; kind < 8U; ++kind) {
            set(frame, economy, 33U + kind, kind_severity[kind]);
        }
        set(frame, economy, 76U, kind_severity[8U]);

        std::size_t source_metric = kM10PublicMetricCount;
#define MACRO_SIM_M4_SOURCE(field, unit)                                  \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(real.field));
#define MACRO_SIM_M5_SOURCE(field, unit)                                  \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(monetary.field));
#define MACRO_SIM_M6_SOURCE(field, unit)                                  \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(securities.field));
#define MACRO_SIM_M7_SOURCE(field, unit)                                  \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(population.field));
#define MACRO_SIM_M8_ENERGY_SOURCE(field, unit)                           \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(domestic.energy.field));
#define MACRO_SIM_M8_HOUSING_SOURCE(field, unit)                          \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(domestic.housing.field));
#define MACRO_SIM_M9_COUNTRY_SOURCE(field, unit)                          \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(external.field));
#define MACRO_SIM_M9_WORLD_SOURCE(field, unit)                            \
        set(frame, economy, source_metric++,                              \
            static_cast<double>(metrics.field));
#include "macro_sim/reporting/m10_metric_sources.inc"
#undef MACRO_SIM_M4_SOURCE
#undef MACRO_SIM_M5_SOURCE
#undef MACRO_SIM_M6_SOURCE
#undef MACRO_SIM_M7_SOURCE
#undef MACRO_SIM_M8_ENERGY_SOURCE
#undef MACRO_SIM_M8_HOUSING_SOURCE
#undef MACRO_SIM_M9_COUNTRY_SOURCE
#undef MACRO_SIM_M9_WORLD_SOURCE
        if (source_metric !=
            kM10PublicMetricCount + kM10NativeSourceMetricCount) {
            return Status(ErrorCode::invariant_violation,
                          "M10 native metric catalog width disagrees");
        }
#define MACRO_SIM_NATIONAL_ACCOUNT(field, unit)                           \
        set(frame, economy, source_metric++, national_accounts.field);
#include "macro_sim/reporting/m10_national_accounts.inc"
#undef MACRO_SIM_NATIONAL_ACCOUNT
        if (source_metric != kM10MetricCount) {
            return Status(ErrorCode::invariant_violation,
                          "M10 national-account catalog width disagrees");
        }
    }
    return frame;
}

} // namespace macro_sim::reporting
