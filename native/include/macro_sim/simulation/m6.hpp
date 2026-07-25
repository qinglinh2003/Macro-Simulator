#ifndef MACRO_SIM_SIMULATION_M6_HPP
#define MACRO_SIM_SIMULATION_M6_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/core/securities.hpp"
#include "macro_sim/simulation/m5.hpp"

namespace macro_sim::simulation {

enum class ConsumptionStratum : std::uint8_t {
    necessity = 0,
    luxury = 1,
};

struct M6PolicyState final {
    double bond_finance_fraction{0.90};
    double bond_coupon_rate{1.0e-4};
    std::uint64_t bond_maturity_days{365};
    double household_bond_target{0.15};
    double bank_bond_appetite{0.03};
    double bank_bond_duration_limit{0.50};
    double margin_ltv{0.50};
    double margin_max{2.0};
    bool household_bankruptcy{true};
    bool bank_resolution_fund{true};
    double bank_minimum_capital{25.0};

    bool operator==(const M6PolicyState &) const = default;
};

struct M6Rules final {
    bool bonds{true};
    std::uint64_t bond_maturity_bucket{30};
    bool firm_equity{true};
    double shares_per_firm{100.0};
    std::uint32_t watchlist_size{15};
    bool founder_owned_genesis{true};
    double genesis_founder_pool{0.10};
    double equity_price_adjustment{0.05};
    double equity_trend_lambda{0.20};
    double residual_income_lambda{0.05};
    double q_smoothing{0.20};
    double fundamental_weight{0.70};
    double chartist_weight{0.30};
    double household_equity_target{0.25};
    double portfolio_adjustment{0.20};
    bool equity_finance{true};
    double equity_issue_lambda{0.20};
    bool margin_credit{true};
    double valuation_discount_floor{1.0e-6};
    double valuation_risk_premium{1.0e-4};
    double capital_haircut{0.20};
    double inventory_haircut{0.50};
    bool firm_dynamics{true};
    std::uint32_t bankrupt_persistence{5};
    std::uint32_t shell_exit_days{60};
    double entry_hurdle{1.0e-4};
    double entry_beta{0.02};
    std::uint32_t entry_max{1};
    double startup_deposits{10.0};
    double startup_capital{2.0};
    bool consumption_strata{true};
    bool sector_switching{true};
    double switch_return_gap{0.10};
    std::uint32_t switch_pressure_days{30};
    double switch_hazard{0.01};
    double switch_retool_loss{0.10};
    bool bank_equity{true};
    bool bank_equity_trading{true};
    double bank_shares{100.0};
    double bank_equity_lambda{0.05};
    double bank_equity_target{0.10};
    bool bank_dynamics{true};
    double bank_entry_beta{0.02};
    std::uint32_t bank_entry_max{1};

    bool operator==(const M6Rules &) const = default;
};

struct FirmStatement final {
    FirmId firm{};
    double cash{0.0};
    double debt{0.0};
    double interest_arrears{0.0};
    double capital_units{0.0};
    double capital_unit_price{0.0};
    double capital_value{0.0};
    double output_inventory_units{0.0};
    double output_inventory_unit_price{0.0};
    double output_inventory_value{0.0};
    double work_in_progress_value{0.0};
    double input_inventory_value{0.0};
    double inventory_value{0.0};
    double gross_assets{0.0};
    double book_equity{0.0};
    double eligible_collateral_value{0.0};
    double borrowing_base_proxy{0.0};
    double borrowing_base_headroom{0.0};
    double earnings{0.0};

    bool operator==(const FirmStatement &) const = default;
};

struct FirmLifecycleRecord final {
    FirmId firm{};
    FirmStatement statement{};
    ConsumptionStratum stratum{ConsumptionStratum::necessity};
    std::uint32_t insolvent_days{0};
    std::uint32_t shell_days{0};
    std::uint32_t switch_pressure_days{0};
    double residual_income_ema{0.0};
    double tobin_q_ema{1.0};
    bool active{false};
    bool defaulted{false};

    bool operator==(const FirmLifecycleRecord &) const = default;
};

struct M6WatchlistRow final {
    HouseholdId household{};
    std::uint32_t offset{0};
    std::uint32_t count{0};

    bool operator==(const M6WatchlistRow &) const = default;
};

struct M6Metrics final {
    M5Metrics economy{};
    double bond_outstanding_face{0.0};
    double bond_market_value{0.0};
    double bond_issuance{0.0};
    double bond_redemption{0.0};
    double bond_coupon_paid{0.0};
    double firm_equity_market_cap{0.0};
    double bank_equity_market_cap{0.0};
    double equity_turnover{0.0};
    double primary_equity_raised{0.0};
    double margin_principal{0.0};
    double margin_originated{0.0};
    double margin_repaid{0.0};
    double margin_writeoffs{0.0};
    double total_firm_book_equity{0.0};
    double clearing_residual{0.0};
    double sector_retool_capital{0.0};
    std::uint64_t active_security_lots{0};
    std::uint64_t household_bankruptcies{0};
    std::uint64_t firm_births{0};
    std::uint64_t firm_exits{0};
    std::uint64_t firm_defaults{0};
    std::uint64_t sector_switches{0};
    std::uint64_t bank_births{0};
    std::uint64_t bank_equity_resolutions{0};

    bool operator==(const M6Metrics &) const = default;
};

struct M6SimulationSpec final {
    M5SimulationSpec monetary_economy{};
    M6PolicyState policy{};
    M6Rules rules{};
};

struct M6AdvanceOptions final {
    M5AdvanceOptions base{};
    std::optional<FirmId> force_firm_exit{};
    bool force_bank_entry{false};
};

struct M6AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M6Metrics metrics{};
    std::uint64_t scratch_capacity_signature{0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};
};

struct M6Runtime final {
    M6PolicyState policy{};
    M6Rules rules{};
    core::SecurityBook securities{};
    std::vector<FirmLifecycleRecord> firms;
    std::vector<M6WatchlistRow> watchlist_rows;
    std::vector<EquityId> watchlist_equities;
    std::vector<LoanId> margin_loans;
    double replacement_capital_price{1.0};
    std::uint64_t lifecycle_rng_counter{0};
    std::uint64_t security_rng_counter{0};
    M6Metrics last_metrics{};
};

struct M6FirmExitCommand final {
    FirmId firm{};
    AccountId account{};
};

struct M6FirmEntryCommand final {
    FirmId firm{};
    AccountId account{};
    HouseholdId founder{};
    AccountId founder_account{};
    SettlementNodeId settlement_node{};
    double startup_cash{0.0};
    core::FirmComponent component{};
    FirmLifecycleRecord lifecycle{};
    EquityId equity{};
};

struct M6BankEntryCommand final {
    BankId bank{};
    AccountId account{};
    SettlementNodeId settlement_node{};
    HouseholdId founder{};
    AccountId founder_account{};
    double capital{0.0};
    core::BankComponent component{};
    core::BankPnlRecord pnl{};
    core::BankCapitalRecord bank_capital{};
};

struct M6EquityOrder final {
    EquityId equity{};
    HouseholdId household{};
    double quantity{0.0};
    std::uint64_t ordinal{0};
};

struct M6BondDemand final {
    core::OwnerId holder{};
    AccountId account{};
    double amount{0.0};
};

class M6TickScratch final {
  public:
    void reserve(const core::RootState &state, const M6Runtime &runtime);
    [[nodiscard]] std::uint64_t capacity_signature() const noexcept;

    core::SecurityBook securities_;
    std::vector<FirmLifecycleRecord> firms_;
    std::vector<M6EquityOrder> orders_;
    std::vector<M6EquityOrder> buyers_;
    std::vector<M6EquityOrder> sellers_;
    std::vector<EquityId> bank_equities_;
    std::vector<M6BondDemand> bond_demands_;
    std::vector<double> watch_current_;
    std::vector<double> watch_attractiveness_;
    std::vector<LoanId> margin_loans_;
    std::vector<double> debt_by_account_;
    std::vector<double> margin_by_account_;
    std::vector<double> firm_return_;
    std::vector<M6FirmExitCommand> firm_exits_;
    std::vector<M6FirmEntryCommand> firm_entries_;
    std::vector<M6BankEntryCommand> bank_entries_;
    M6Metrics working_metrics_{};
};

class M6TickExtension {
  public:
    M6TickExtension() = default;
    M6TickExtension(const M6TickExtension &) = delete;
    M6TickExtension &operator=(const M6TickExtension &) = delete;
    virtual ~M6TickExtension() = default;

    [[nodiscard]] virtual Status
    prepare_tick(const core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &runtime,
                 M6TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    run_labor(const core::RootState &state,
              M4Runtime &real_economy_runtime,
              M4TickScratch &real_economy_scratch,
              M5Runtime &monetary_runtime,
              M5TickScratch &monetary_scratch, M6Runtime &runtime,
              M6TickScratch &scratch, Tick tick, PhiloxRng &rng,
              bool &handled) = 0;
    [[nodiscard]] virtual Status
    close_day(const core::RootState &state, M4Runtime &real_economy_runtime,
              M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
              M5TickScratch &monetary_scratch, M6Runtime &runtime,
              M6TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    validate(const core::RootState &state, const M4Runtime &real_economy_runtime,
             const M4TickScratch &real_economy_scratch,
             const M5Runtime &monetary_runtime, const M5TickScratch &monetary_scratch,
             const M6Runtime &runtime, const M6TickScratch &scratch,
             Tick tick) const = 0;
    virtual void commit(core::RootState &state, M4Runtime &real_economy_runtime,
                        M4TickScratch &real_economy_scratch,
                        M5Runtime &monetary_runtime, M5TickScratch &monetary_scratch,
                        M6Runtime &runtime, M6TickScratch &scratch, Tick tick,
                        const M6Metrics &metrics) noexcept = 0;
};

struct M6Initialization final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime runtime;
};

[[nodiscard]] double bond_price(double face, std::uint64_t remaining_days,
                                double required_return, double coupon_rate) noexcept;
[[nodiscard]] double equity_discount_rate(const M5Runtime &monetary_runtime,
                                          const M6Rules &rules) noexcept;
[[nodiscard]] double residual_income_fundamental(double book_value,
                                                 double residual_income, double shares,
                                                 double discount_rate) noexcept;
[[nodiscard]] Status validate_m6_policy(const M6PolicyState &policy) noexcept;
[[nodiscard]] Status validate_m6_rules(const M6Rules &rules) noexcept;
[[nodiscard]] Status validate_m6_spec(const M6SimulationSpec &spec) noexcept;
[[nodiscard]] Status validate_m6_state(const core::RootState &state,
                                       const M4Runtime &real_economy_runtime,
                                       const M5Runtime &monetary_runtime,
                                       const M6Runtime &runtime, Tick tick) noexcept;
[[nodiscard]] Result<M6Initialization> build_m6_genesis(const M6SimulationSpec &spec);
[[nodiscard]] Result<M6AdvanceResult>
advance_m6_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &runtime,
                 M6TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M6AdvanceOptions &options = {});
[[nodiscard]] Result<M6AdvanceResult>
advance_m6_ticks_extended(core::RootState &state, M4Runtime &real_economy_runtime,
                          M4TickScratch &real_economy_scratch,
                          M5Runtime &monetary_runtime, M5TickScratch &monetary_scratch,
                          M6Runtime &runtime, M6TickScratch &scratch, Tick &tick,
                          std::uint64_t count, M6TickExtension &extension,
                          const M6AdvanceOptions &options = {});

} // namespace macro_sim::simulation

#endif
