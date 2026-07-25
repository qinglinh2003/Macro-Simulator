#ifndef MACRO_SIM_SIMULATION_M9_HPP
#define MACRO_SIM_SIMULATION_M9_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m8.hpp"

namespace macro_sim::simulation {

enum class FxRegime : std::uint8_t {
    floating = 0,
    peg = 1,
};

enum class ShockKind : std::uint8_t {
    productivity = 0,
    labor_availability = 1,
    energy_capacity = 2,
    household_demand = 3,
    import_capacity = 4,
    export_capacity = 5,
    credit_supply = 6,
    capital_destruction = 7,
};

enum class ShockShape : std::uint8_t {
    step = 0,
    linear = 1,
    triangular = 2,
};

enum class M9FaultPoint : std::uint8_t {
    none = 0,
    after_policy_barrier = 1,
    after_trade_reservation = 2,
    after_domestic_advance = 3,
    before_world_commit = 4,
};

struct ExternalPolicyState final {
    double tariff{0.0};
    std::optional<double> import_quota{};
    double export_subsidy{0.0};
    double capital_control{0.0};
    double external_interest_settlement_fraction{1.0};
    std::vector<EconomyId> sanctions_imposed_on;
    std::optional<double> immigration_cap{};
    std::optional<double> emigration_cap{};
    double remittance_tax{0.0};
    double outward_remittance_tax{0.0};
    double guest_worker_return{0.0};
    FxRegime fx_regime{FxRegime::floating};
    std::optional<EconomyId> peg_anchor{};
    double peg_reserve_scale{100000.0};

    bool operator==(const ExternalPolicyState &) const = default;
};

struct WorldRules final {
    bool trade{false};
    bool capital{false};
    bool migration{false};
    double fx_adjustment{0.05};
    double fx_friction{0.03};
    double fx_spread{0.0};
    bool fx_loss_mutualization{false};
    double fx_trade_cap{0.15};
    double capital_mobility{0.0};
    double capital_adjustment{0.1};
    double periods_per_year{12.0};
    double migration_rate{0.02};
    double migration_max_share{0.25};
    double remittance_share{0.2};
    double wage_smoothing{0.02};
    double initial_peg_reserves{5000.0};
    std::size_t dense_edge_threshold{64};

    bool operator==(const WorldRules &) const = default;
};

struct ShockSpec final {
    std::uint64_t id{0};
    ShockKind kind{ShockKind::productivity};
    std::optional<EconomyId> economy{};
    Tick start{};
    std::uint64_t duration{1};
    double magnitude{0.0};
    ShockShape shape{ShockShape::step};
    std::optional<std::uint8_t> sector{};

    bool operator==(const ShockSpec &) const = default;
};

struct M9WorldSpec final {
    std::vector<M8SimulationSpec> economies;
    std::vector<ExternalPolicyState> external_policies;
    WorldRules rules{};
    std::vector<ShockSpec> shocks;
};

struct RateVector final {
    std::vector<double> log_rates;

    [[nodiscard]] std::size_t size() const noexcept { return log_rates.size(); }
    [[nodiscard]] double rate(EconomyId economy) const noexcept;
    [[nodiscard]] double bilateral(EconomyId destination,
                                   EconomyId source) const noexcept;
    [[nodiscard]] double to_numeraire(double amount, EconomyId economy) const noexcept;
    void normalize() noexcept;

    bool operator==(const RateVector &) const = default;
};

struct PegRuntime final {
    EconomyId pegger{};
    EconomyId anchor{};
    double reserves{0.0};
    double pressure{0.0};
    double target_log_spread{0.0};
    bool intact{true};

    bool operator==(const PegRuntime &) const = default;
};

struct MigrationRoute final {
    EconomyId origin{};
    EconomyId host{};
    double stock{0.0};
    double smoothed_real_wage_gap{0.0};
    double flow{0.0};
    double return_flow{0.0};
    double remittance_gross{0.0};
    double remittance_net{0.0};

    bool operator==(const MigrationRoute &) const = default;
};

struct CountryExternalMetrics final {
    double exchange_rate{1.0};
    double imports_value{0.0};
    double imports_volume{0.0};
    double exports_value{0.0};
    double exports_volume{0.0};
    double iceberg_loss{0.0};
    double tariff_revenue{0.0};
    double export_subsidy_cost{0.0};
    double current_account{0.0};
    double capital_flow{0.0};
    double net_foreign_assets{0.0};
    double factor_income_accrued{0.0};
    double factor_income_cash{0.0};
    double factor_income_arrears{0.0};
    double peg_reserves{0.0};
    double migrant_stock_abroad{0.0};
    double migrant_stock_hosted{0.0};
    double remittances_received{0.0};
    double remittances_sent{0.0};
    double remittance_tax_revenue{0.0};
    std::uint64_t active_shocks{0};

    bool operator==(const CountryExternalMetrics &) const = default;
};

struct M9WorldMetrics final {
    std::vector<M8Metrics> domestic;
    std::vector<CountryExternalMetrics> external;
    double dealer_flow{0.0};
    double dealer_spread_revenue{0.0};
    double dealer_valuation{0.0};
    double world_nfa{0.0};
    std::uint64_t trade_routes{0};
    std::uint64_t migration_routes{0};
    std::uint64_t shock_events{0};

    bool operator==(const M9WorldMetrics &) const = default;
};

struct M9AdvanceOptions final {
    std::vector<M8AdvanceOptions> domestic;
    M9FaultPoint fault_point{M9FaultPoint::none};
    std::uint32_t worker_count{1};
};

struct M9AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M9WorldMetrics metrics{};
    std::uint64_t digest{0};
};

class M9World final {
  public:
    M9World(const M9World &) = default;
    M9World &operator=(const M9World &) = default;
    M9World(M9World &&) noexcept = default;
    M9World &operator=(M9World &&) noexcept = default;
    ~M9World() = default;

    [[nodiscard]] static Result<M9World> create(const M9WorldSpec &spec);

    [[nodiscard]] Tick tick() const noexcept { return tick_; }
    [[nodiscard]] std::size_t economy_count() const noexcept {
        return economies_.size();
    }
    [[nodiscard]] const RateVector &rates() const noexcept { return rates_; }
    [[nodiscard]] const std::vector<double> &dealer_inventory() const noexcept {
        return dealer_inventory_;
    }
    [[nodiscard]] const std::vector<ExternalPolicyState> &external_policies() const
        noexcept {
        return external_policies_;
    }
    [[nodiscard]] const std::vector<PegRuntime> &pegs() const noexcept {
        return pegs_;
    }
    [[nodiscard]] const std::vector<MigrationRoute> &migration_routes() const
        noexcept {
        return migration_routes_;
    }
    [[nodiscard]] const M9WorldMetrics &last_metrics() const noexcept {
        return last_metrics_;
    }
    [[nodiscard]] const core::RootState *economy_root(EconomyId economy) const
        noexcept;
    [[nodiscard]] const M8Runtime *economy_runtime(EconomyId economy) const noexcept;

    [[nodiscard]] Status
    update_external_policies(std::span<const ExternalPolicyState> policies);
    [[nodiscard]] Status schedule_shock(const ShockSpec &shock);
    [[nodiscard]] Result<M9AdvanceResult>
    advance(std::uint64_t count, const M9AdvanceOptions &options = {});
    [[nodiscard]] Result<std::vector<std::uint8_t>> checkpoint() const;
    [[nodiscard]] static Result<M9World>
    restore(std::span<const std::uint8_t> checkpoint);
    [[nodiscard]] Status validate() const noexcept;
    [[nodiscard]] std::uint64_t digest() const noexcept;

  private:
    struct EconomyState final {
        EconomyState() = default;
        EconomyState(const EconomyState &other);
        EconomyState &operator=(const EconomyState &other);
        EconomyState(EconomyState &&) noexcept = default;
        EconomyState &operator=(EconomyState &&) noexcept = default;
        ~EconomyState() = default;

        core::RootState root;
        M4Runtime real_economy;
        M4TickScratch real_economy_scratch;
        M5Runtime monetary;
        M5TickScratch monetary_scratch;
        M6Runtime financial;
        M6TickScratch financial_scratch;
        M7Runtime population;
        M7TickScratch population_scratch;
        M8Runtime domestic;
        M8TickScratch domestic_scratch;
        Tick tick{};
    };

    struct TradeReservation final {
        EconomyId importer{};
        EconomyId exporter{};
        FirmId firm{};
        double shipped_units{0.0};
        double delivered_units{0.0};
        double source_price{0.0};
        double importer_value{0.0};
    };

    M9World() = default;

    [[nodiscard]] Status advance_one(const M9AdvanceOptions &options);
    [[nodiscard]] Status validate_policy_vector(
        std::span<const ExternalPolicyState> policies) const noexcept;
    [[nodiscard]] bool sanctioned(std::size_t first, std::size_t second) const
        noexcept;

    Tick tick_{};
    WorldRules rules_{};
    std::vector<EconomyState> economies_;
    std::vector<ExternalPolicyState> external_policies_;
    RateVector rates_{};
    std::vector<double> dealer_inventory_;
    std::vector<std::vector<double>> external_principal_;
    std::vector<std::vector<double>> interest_arrears_;
    std::vector<PegRuntime> pegs_;
    std::vector<MigrationRoute> migration_routes_;
    std::vector<ShockSpec> shocks_;
    std::vector<TradeReservation> trade_reservations_;
    std::vector<double> smoothed_real_wages_;
    double dealer_valuation_{0.0};
    std::uint64_t event_counter_{0};
    M9WorldMetrics last_metrics_{};
};

[[nodiscard]] Status validate_external_policy(
    const ExternalPolicyState &policy, std::size_t economy_count,
    EconomyId owner) noexcept;
[[nodiscard]] Status validate_world_rules(const WorldRules &rules) noexcept;
[[nodiscard]] Status validate_shock_spec(const ShockSpec &shock,
                                         std::size_t economy_count) noexcept;

} // namespace macro_sim::simulation

#endif
