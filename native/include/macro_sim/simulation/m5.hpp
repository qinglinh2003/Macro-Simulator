#ifndef MACRO_SIM_SIMULATION_M5_HPP
#define MACRO_SIM_SIMULATION_M5_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/core/financial.hpp"
#include "macro_sim/simulation/m4.hpp"

namespace macro_sim::simulation {

enum class MonetaryRegime : std::uint8_t {
    exogenous = 0,
    taylor = 1,
    manual = 2,
};

struct M5PolicyState final {
    double government_consumption_share{0.20};
    double government_deficit_target{0.0};
    double deficit_unemployment_reference{0.0};
    double deficit_unemployment_cap{1.0};
    double government_investment_share{0.04};
    double profit_tax_rate{0.25};
    double income_tax_rate{0.20};
    double income_allowance{0.0};
    double consumption_tax_rate{0.15};
    std::optional<double> necessity_consumption_tax_rate{};
    std::optional<double> luxury_consumption_tax_rate{};
    double wealth_tax_rate{5.479452054794521e-6};
    double wealth_allowance{0.0};
    double unemployment_benefit_replacement{0.40};
    double benefit_income_floor{0.0};
    double minimum_wage{0.0};
    bool job_guarantee{false};
    double job_guarantee_wage_ratio{0.0};
    double job_guarantee_public_works_share{1.0};

    MonetaryRegime monetary_regime{MonetaryRegime::exogenous};
    double inflation_target{0.0};
    double taylor_inflation{1.5};
    double taylor_unemployment{0.5};
    double rate_inertia{0.8};
    std::optional<double> manual_policy_rate{};
    double neutral_rate{0.01};
    double natural_unemployment{0.05};
    double maximum_policy_rate{0.10};
    double inflation_sensor_lambda{0.02};
    bool core_inflation_sensor{false};
    bool fixed_basket_cpi{false};
    bool logarithmic_inflation{false};
    bool fiscal_uses_national_accounts_gdp{false};

    bool open_market_operations{false};
    double reserve_target{0.0};
    double reserve_gap_close{0.10};
    bool reserve_target_indexes_deposits{false};
    bool lender_of_last_resort{false};
    double reserve_floor_fraction{0.0};

    double firm_leverage_limit{3.0};
    double firm_minimum_dscr{1.25};
    double household_credit_limit{2.0};
    bool bank_capital_constraint{false};
    bool unified_bank_rwa{false};
    double bank_leverage_cap{0.0};
    double bank_exposure_limit{0.0};
    double bank_target_capital_ratio{0.0};
    double deposit_rate_floor{0.0};
    bool migrate_relationships_on_failure{true};
    bool state_resolution_backstop{false};

    bool operator==(const M5PolicyState &) const = default;
};

struct M5Rules final {
    bool banking_enabled{true};
    std::uint64_t bank_count{2};
    double opening_capital_per_bank{25.0};
    double bank_leverage_mean{10.0};
    double bank_leverage_dispersion{0.0};
    bool assign_banks_by_size{false};
    bool realized_bank_pnl{true};
    bool full_firm_pnl{true};
    bool household_credit{true};
    bool rate_competition{true};
    bool relationship_lock_in{true};
    double loan_spread_dispersion{0.0};
    std::uint32_t bank_search_count{2};
    bool interbank{true};
    double interbank_rate_base{0.0};
    double interbank_tightness{0.0};
    double deposit_spread_dispersion{0.0};
    std::uint32_t deposit_search_count{2};
    double deposit_rate{0.0};
    bool deposit_interest_arrears{true};
    bool household_interest_arrears{false};
    bool interest_by_deposits{true};
    double firm_amortization{0.10};
    double household_amortization{0.10};
    double household_subsistence{0.0};
    bool direct_monetary_transmission{true};
    double investment_user_cost_elasticity{0.5};
    double investment_user_cost_multiplier_min{0.5};
    double investment_user_cost_multiplier_max{1.5};
    double investment_user_cost_floor{1.0e-9};
    bool bank_runs{false};
    double run_sensitivity{0.0};
    double run_health_reference{0.10};
    double run_market_weight{0.50};
    double run_fear_persistence{0.90};
    double bank_payout_ratio{0.50};

    bool operator==(const M5Rules &) const = default;
};

struct M5SimulationSpec final {
    M4SimulationSpec real_economy{};
    M5PolicyState policy{};
    M5Rules rules{};
    double initial_policy_rate{0.01};
};

struct M5Metrics final {
    M4Metrics economy{};
    double policy_rate{0.0};
    double inflation_sensor{0.0};
    double new_credit{0.0};
    double firm_investment_target{0.0};
    double investment_user_cost_multiplier_mean{1.0};
    double household_debt_service_reserved{0.0};
    double firm_dscr_credit_shortfall{0.0};
    double firm_credit_applications{0.0};
    double firm_credit_requested{0.0};
    double firm_credit_existing_principal{0.0};
    double firm_credit_min_dscr_applied{0.0};
    double firm_credit_originated{0.0};
    double bank_capital_constraint_applied{0.0};
    double bank_gross_capital_headroom{0.0};
    double bank_gross_capital_credit_shortfall{0.0};
    double principal_repaid{0.0};
    double loan_interest_paid{0.0};
    double household_interest_paid{0.0};
    double household_interest_arrears_opening{0.0};
    double household_interest_accrued{0.0};
    double household_interest_arrears_cash_paid{0.0};
    double household_interest_arrears_closing{0.0};
    double household_interest_arrears_extinguished{0.0};
    double household_contractual_debt_service_due{0.0};
    double household_interest_arrears_in_goods_reservation{0.0};
    double household_interest_arrears_stock_flow_residual{0.0};
    double deposit_interest_paid{0.0};
    double deposit_interest_arrears{0.0};
    double total_loan_principal{0.0};
    double total_bank_capital{0.0};
    double total_reserves{0.0};
    double reserve_stock{0.0};
    double omo_flow{0.0};
    double lolr_liquidity_shortfall{0.0};
    double lolr_advances{0.0};
    double lolr_outstanding{0.0};
    double interbank_volume{0.0};
    double interbank_rate{0.0};
    double run_flight_volume{0.0};
    double resolution_funding_need{0.0};
    double resolution_cost{0.0};
    double resolution_mutualized_cost{0.0};
    double failed_account_migration_candidates{0.0};
    double failed_accounts_migrated{0.0};
    double failed_loan_migration_candidates{0.0};
    double failed_loans_migrated{0.0};
    double unified_bank_rwa_applied{0.0};
    double bank_rwa_headroom{0.0};
    double bank_rwa_credit_shortfall{0.0};
    double realized_credit_losses{0.0};
    double realized_interbank_losses{0.0};
    std::uint64_t alive_banks{0};
    std::uint64_t bank_failures{0};

    bool operator==(const M5Metrics &) const = default;
};

struct M5AdvanceOptions final {
    M4AdvanceOptions base{};
    std::optional<AccountId> force_default_account{};
    std::optional<BankId> force_run_bank{};
    double credit_supply_multiplier{1.0};
};

struct M5AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M5Metrics metrics{};
    std::uint64_t scratch_capacity_signature{0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};
};

struct M5Runtime final {
    M5PolicyState policy{};
    M5Rules rules{};
    double initial_policy_rate{0.01};
    double policy_rate{0.01};
    double inflation_sensor{0.0};
    double previous_price_index{0.0};
    double headline_price_index{0.0};
    double previous_headline_price_index{0.0};
    double previous_unemployment{0.0};
    double reserve_genesis{0.0};
    double bank_fear{0.0};
    // M8 synchronizes these live regulatory terms before M5 credit allocation.
    // Pure M5 simulations use the canonical whole-bank RWA defaults.
    double unified_rwa_mortgage_risk_weight{0.35};
    double unified_rwa_minimum_capital_ratio{0.08};
    // Dense by BankId. Index zero is the invalid-identity sentinel. M6 updates
    // this projection from the previous close's listed-bank price/peak ratio.
    // Pure M5 simulations retain the neutral value of one.
    std::vector<double> bank_market_health{};
    M5Metrics last_metrics{};

    bool operator==(const M5Runtime &) const = default;
};

class M5TickScratch final {
  public:
    void reserve(const core::RootState &state);
    void synchronize_topology(const core::RootState &state,
                              const M4TickScratch &real_economy_scratch);
    [[nodiscard]] std::uint64_t capacity_signature() const noexcept;

    std::vector<core::LoanRecord> loans_;
    std::vector<core::InterbankRecord> interbank_;
    std::vector<core::CentralBankOperationRecord> central_bank_operations_;
    std::vector<core::BankPnlRecord> bank_pnl_;
    std::vector<core::BankCapitalRecord> bank_capital_;
    std::vector<double> debt_by_account_;
    std::vector<LoanId> reusable_loan_by_account_;
    std::vector<LoanId> relationship_loan_by_account_;
    std::vector<double> exposure_by_bank_;
    std::vector<double> deposits_by_bank_;
    std::vector<double> scheduled_service_by_account_;
    std::vector<double> bank_capital_live_;
    std::vector<std::uint8_t> bank_alive_;
    std::vector<BankId> bank_by_node_;
    std::vector<std::size_t> firm_index_by_id_;
    std::vector<std::size_t> household_order_;
    std::vector<std::size_t> candidate_banks_;
    std::vector<BankId> alive_banks_;
    std::vector<BankId> failed_banks_;
    double reserve_stock_{0.0};
    M5Metrics working_metrics_{};
};

struct M5CreditQuote final {
    AccountId borrower_account{};
    core::OwnerId borrower{};
    BankId lender{};
    Money principal{};
    Rate annual_rate{};
    SettlementNodeId expected_settlement_node{};
    double expected_existing_debt{0.0};
    std::size_t expected_loan_count{0};

    bool operator==(const M5CreditQuote &) const = default;
};

[[nodiscard]] Result<M5CreditQuote>
quote_m5_credit(const core::RootState &state, const M4TickScratch &real_economy,
                const M5Runtime &runtime, M5TickScratch &scratch,
                AccountId borrower_account, Money requested, Money borrower_limit,
                double credit_supply_multiplier = 1.0);
[[nodiscard]] double m5_bank_rwa_principal_capacity(const M5TickScratch &scratch,
                                                    BankId bank,
                                                    double mortgage_risk_weight,
                                                    double minimum_capital_ratio,
                                                    double new_loan_risk_weight,
                                                    bool unified_bank_rwa) noexcept;
[[nodiscard]] double m5_bank_risk_weighted_assets(const M5TickScratch &scratch,
                                                  BankId bank,
                                                  double mortgage_risk_weight,
                                                  bool unified_bank_rwa) noexcept;
[[nodiscard]] Result<LoanId>
stage_m5_credit(const core::RootState &state, M4TickScratch &real_economy,
                const M5Runtime &runtime, M5TickScratch &scratch,
                const M5CreditQuote &quote, Tick tick,
                core::LoanPurpose purpose = core::LoanPurpose::general);
[[nodiscard]] double stage_m5_firm_plan_credit(
    const core::RootState &state, const M4Runtime &real_economy_runtime,
    M4TickScratch &real_economy, M5Runtime &runtime, M5TickScratch &scratch,
    std::size_t firm_index, Tick tick, double credit_supply_multiplier = 1.0,
    double additional_cash_need = 0.0);
[[nodiscard]] Status stage_m5_loan_repayment(const core::RootState &state,
                                             M4TickScratch &real_economy,
                                             M5TickScratch &scratch, LoanId loan,
                                             AccountId payer, Money amount) noexcept;
[[nodiscard]] Status stage_m5_loan_writeoff(const core::RootState &state,
                                            M4TickScratch &real_economy,
                                            M5TickScratch &scratch, LoanId loan,
                                            Tick tick) noexcept;
// Re-closes bank reserves after payments posted outside the domestic tick, such
// as world trade and remittance settlement.
[[nodiscard]] Status close_m5_external_liquidity(core::RootState &state,
                                                 M5Runtime &runtime, Tick closed_tick);

class M5TickExtension {
  public:
    M5TickExtension() = default;
    M5TickExtension(const M5TickExtension &) = delete;
    M5TickExtension &operator=(const M5TickExtension &) = delete;
    virtual ~M5TickExtension() = default;

    [[nodiscard]] virtual Status
    prepare_tick(const core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                 M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    // The real-economy plan is complete at this point, but credit has not yet
    // been sized.  Financial-market extensions use this seam for valuation
    // channels (for example Tobin's q) that must alter both the physical
    // investment target and the financing request built from that target.
    [[nodiscard]] virtual Status before_credit(const core::RootState &, M4Runtime &,
                                               M4TickScratch &, M5Runtime &,
                                               M5TickScratch &, Tick, PhiloxRng &) {
        return Status::success();
    }
    [[nodiscard]] virtual Status
    after_planning(const core::RootState &state, M4Runtime &real_economy_runtime,
                   M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                   M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    run_labor(const core::RootState &state, M4Runtime &real_economy_runtime,
              M4TickScratch &real_economy_scratch, M5Runtime &runtime,
              M5TickScratch &scratch, Tick tick, PhiloxRng &rng, bool &handled) = 0;
    [[nodiscard]] virtual Status
    before_settlement(const core::RootState &state, M4Runtime &real_economy_runtime,
                      M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                      M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status distribute_dividends(const core::RootState &,
                                                      M4Runtime &, M4TickScratch &,
                                                      M5Runtime &, M5TickScratch &,
                                                      Tick, PhiloxRng &, double,
                                                      bool &handled) {
        handled = false;
        return Status::success();
    }
    [[nodiscard]] virtual Status
    prepare_household_net_wealth(const core::RootState &, M4Runtime &, M4TickScratch &,
                                 M5Runtime &, M5TickScratch &, Tick, PhiloxRng &,
                                 std::span<double>) {
        return Status::success();
    }
    [[nodiscard]] virtual Status
    after_settlement(const core::RootState &state, M4Runtime &real_economy_runtime,
                     M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                     M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    before_bank_resolution(const core::RootState &state,
                           M4Runtime &real_economy_runtime,
                           M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                           M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    close_institutions(const core::RootState &state, M4Runtime &real_economy_runtime,
                       M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                       M5TickScratch &scratch, Tick tick, PhiloxRng &rng) = 0;
    [[nodiscard]] virtual Status
    validate(const core::RootState &state, const M4Runtime &real_economy_runtime,
             const M4TickScratch &real_economy_scratch, const M5Runtime &runtime,
             const M5TickScratch &scratch, Tick tick) const = 0;
    virtual void commit(core::RootState &state, M4Runtime &real_economy_runtime,
                        M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                        M5TickScratch &scratch, Tick closed_tick,
                        const M5Metrics &metrics) noexcept = 0;
};

struct M5Initialization final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime runtime;
};

[[nodiscard]] Status validate_m5_policy(const M5PolicyState &policy) noexcept;
[[nodiscard]] Status validate_m5_spec(const M5SimulationSpec &spec) noexcept;
[[nodiscard]] Status validate_m5_state(const core::RootState &state,
                                       const M4Runtime &real_economy_runtime,
                                       const M5Runtime &runtime, Tick tick) noexcept;
[[nodiscard]] Result<M5Initialization> build_m5_genesis(const M5SimulationSpec &spec);
[[nodiscard]] Result<M5AdvanceResult>
advance_m5_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                 M5TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M5AdvanceOptions &options = {});
[[nodiscard]] Result<M5AdvanceResult>
advance_m5_ticks_extended(core::RootState &state, M4Runtime &real_economy_runtime,
                          M4TickScratch &real_economy_scratch, M5Runtime &runtime,
                          M5TickScratch &scratch, Tick &tick, std::uint64_t count,
                          M5TickExtension &extension,
                          const M5AdvanceOptions &options = {});

} // namespace macro_sim::simulation

#endif
