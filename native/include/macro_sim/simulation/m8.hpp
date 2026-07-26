#ifndef MACRO_SIM_SIMULATION_M8_HPP
#define MACRO_SIM_SIMULATION_M8_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/core/housing.hpp"
#include "macro_sim/simulation/m7.hpp"

namespace macro_sim::simulation {

enum class EnergyRationing : std::uint8_t {
    market = 0,
    proportional = 1,
    household_first = 2,
    industry_first = 3,
};

enum class M8FaultPoint : std::uint8_t {
    none = 0,
    after_energy_plan = 1,
    after_energy_clearing = 2,
    before_commit = 3,
};

struct EnergyPolicyState final {
    double excise_rate{0.0};
    double windfall_tax_rate{0.0};
    double household_subsidy_rate{0.0};
    double subsidy_deposit_threshold{0.0};
    double price_cap{0.0};
    bool price_cap_compensation{false};
    double strategic_reserve_target{0.0};
    double strategic_reserve_flow_cap{0.0};
    bool state_owned_price_at_cost{false};
    bool state_owned_first_producer{false};
    EnergyRationing rationing{EnergyRationing::market};

    bool operator==(const EnergyPolicyState &) const = default;
};

struct EnergyRules final {
    bool enabled{true};
    bool household_energy{true};
    bool deprivation{true};
    bool state_owned_first_producer{false};
    std::uint64_t producer_count{2};
    double initial_producer_cash{20.0};
    double initial_price{1.2};
    double initial_wage{1.0};
    double initial_markup{0.2};
    double producer_productivity{1.0};
    double capacity_per_capital{1.0};
    double initial_utilization{0.8};
    double producer_inventory_ratio{0.25};
    double demand_adjustment{0.0076};
    double markup_adjustment{6.7e-4};
    double markup_minimum{0.0};
    double markup_maximum{1.0};
    double household_need{0.2};
    double downstream_intensity{0.08};
    double downstream_coverage_days{2.0};
    double downstream_gap_close{0.10};
    double hoarding_beta{0.0};
    double slow_price_days{30.0};
    std::uint32_t deprivation_burnin_years{2};
    double deprivation_subsistence_share{0.5};
    std::uint32_t deprivation_acute_days{7};
    std::uint32_t deprivation_chronic_days{30};
    double fuel_poverty_threshold{0.60};
    double fuel_poverty_mortality_gamma{0.0};
    double fuel_poverty_mortality_cap{1.3};

    bool operator==(const EnergyRules &) const = default;
};

struct EnergyExogenousInput final {
    double capacity_multiplier{1.0};
    double labor_availability_multiplier{1.0};
    double supply_multiplier{1.0};
    double household_demand_multiplier{1.0};
    double industry_demand_multiplier{1.0};
    double reference_price_multiplier{1.0};

    bool operator==(const EnergyExogenousInput &) const = default;
};

struct EnergyProducerComponent final {
    FirmId firm{};
    bool active{false};
    bool state_owned{false};
    double capacity_per_capital{0.0};
    double inventory{0.0};
    double inventory_cost{0.0};
    double produced{0.0};
    double sales{0.0};
    double revenue{0.0};
    double demand_expected{0.0};

    bool operator==(const EnergyProducerComponent &) const = default;
};

struct EnergyInputComponent final {
    FirmId firm{};
    bool active{false};
    double intensity{0.0};
    double coverage_days{0.0};
    double stock{0.0};
    double stock_cost{0.0};
    double average_cost{0.0};
    double bought{0.0};
    double used{0.0};
    double unmet{0.0};

    bool operator==(const EnergyInputComponent &) const = default;
};

struct HouseholdEnergyComponent final {
    HouseholdId household{};
    bool active{false};
    double need{0.0};
    double bought{0.0};
    double spent{0.0};
    double subsidy{0.0};
    double coverage{0.0};
    std::array<std::uint32_t, 3> deprivation_spells{};

    bool operator==(const HouseholdEnergyComponent &) const = default;
};

struct DeprivationState final {
    std::int32_t current_year{0};
    std::uint32_t years_completed{0};
    double per_unit_sum{0.0};
    double household_days{0.0};
    double price_sum{0.0};
    double price_days{0.0};
    double basket_cost_anchor{0.0};
    double price_anchor{0.0};
    bool active{false};
    bool boundary_breached{false};

    bool operator==(const DeprivationState &) const = default;
};

struct EnergyMetrics final {
    double production{0.0};
    double capacity{0.0};
    double utilization{0.0};
    double opening_supply{0.0};
    double requested_total{0.0};
    double requested_households{0.0};
    double requested_industry{0.0};
    double requested_public{0.0};
    double sold{0.0};
    double unfilled{0.0};
    double transaction_price{0.0};
    double household_units{0.0};
    double household_spending{0.0};
    double industry_units{0.0};
    double industry_spending{0.0};
    double excise_paid{0.0};
    double windfall_tax_paid{0.0};
    double subsidy_paid{0.0};
    double cap_compensation{0.0};
    double strategic_reserve_stock{0.0};
    double strategic_reserve_flow{0.0};
    double strategic_reserve_purchase_paid{0.0};
    double strategic_reserve_sale_revenue{0.0};
    double fuel_poverty_share{0.0};
    double fuel_poverty_mortality_multiplier{1.0};
    double deprivation_below_100_share{0.0};
    double deprivation_below_60_share{0.0};
    double deprivation_below_30_share{0.0};
    double deprivation_destitute_share{0.0};
    double deprivation_acute_stock{0.0};
    double deprivation_chronic_stock{0.0};
    double deprivation_max_spell_days{0.0};
    bool deprivation_boundary{false};

    bool operator==(const EnergyMetrics &) const = default;
};

struct HousingPolicyState final {
    double mortgage_ltv_cap{0.8};
    bool mortgage_underwriting{false};
    double mortgage_dsti_cap{0.45};
    double mortgage_stress_rate_addon{0.02 / 365.0};
    double mortgage_risk_weight{0.35};
    double mortgage_minimum_capital_ratio{0.08};
    double mortgage_foreclosure_ltv{1.1};
    double mortgage_arrears_floor{2.0};
    std::uint32_t rental_eviction_arrears{30};
    std::uint64_t annual_housing_permits{50};
    double land_fee_share{0.2};
    double land_fee_stock_elasticity{1.0};
    double transfer_tax_rate{0.0};
    double property_tax_rate{0.0};
    bool include_housing_in_wealth_tax{false};
    double wealth_tax_rate{0.0};

    bool operator==(const HousingPolicyState &) const = default;
};

struct HousingRules final {
    bool enabled{false};
    bool resale_market{false};
    bool mortgages{false};
    bool rentals{false};
    bool construction{false};
    double house_price_income_years{3.5};
    double initial_dwellings_per_household{1.0};
    double initial_homeownership_share{1.0};
    double initial_floor_area{80.0};
    double initial_quality{1.0};
    std::uint32_t location_count{1};
    std::uint32_t market_interval_days{30};
    double voluntary_ask_markup{0.05};
    double forced_sale_discount{0.10};
    double ask_decay{0.03};
    double demand_price_step{0.0};
    double ask_floor_annual_wage_share{0.0};
    std::uint32_t buyer_search_count{5};
    double buyer_liquidity_buffer{0.25};
    double distress_deposit_floor{5.0};
    double initial_rent_yield{0.05};
    double rent_adjustment{0.02};
    double rent_burden_cap{0.40};
    double rental_investor_premium{0.02};
    double rental_vacancy_deadband{0.0};
    double rent_floor_wage_share{0.0};
    std::uint64_t builder_count{5};
    double initial_builder_cash_buffer{5.0};
    double builder_productivity{0.002};
    double builder_demand_seed{0.005};
    double builder_demand_price_gain{0.0};
    double builder_finished_inventory_buffer{0.0};
    bool builder_land_fee_credit{false};
    std::uint32_t affordability_burnin_years{4};
    double leave_home_elasticity{0.0};
    double leave_home_multiplier_minimum{0.5};
    double leave_home_multiplier_maximum{1.5};
    double fertility_elasticity{0.0};
    double fertility_multiplier_minimum{0.5};
    double fertility_multiplier_maximum{1.5};

    bool operator==(const HousingRules &) const = default;
};

struct HousingExogenousInput final {
    double house_price_reference_multiplier{1.0};
    double buyer_demand_multiplier{1.0};
    double rental_demand_multiplier{1.0};
    double construction_productivity_multiplier{1.0};
    double land_cost_multiplier{1.0};

    bool operator==(const HousingExogenousInput &) const = default;
};

struct HousingListing final {
    DwellingId dwelling{};
    core::OwnerId seller{};
    double asking_price{0.0};
    Tick listed_tick{};
    bool forced{false};
    bool active{true};

    bool operator==(const HousingListing &) const = default;
};

struct MortgageRecord final {
    LoanId loan{};
    HouseholdId borrower{};
    BankId lender{};
    DwellingId collateral{};
    double original_principal{0.0};
    double purchase_price{0.0};
    double qualifying_income{0.0};
    double stressed_payment{0.0};
    Tick originated_tick{};
    bool active{true};
    bool foreclosed{false};

    bool operator==(const MortgageRecord &) const = default;
};

struct TenancyRecord final {
    TenancyId id{};
    DwellingId dwelling{};
    HouseholdId landlord{};
    HouseholdId tenant{};
    double daily_rent{0.0};
    std::uint32_t missed_days{0};
    Tick started_tick{};
    Tick ended_tick{};
    bool active{true};

    bool operator==(const TenancyRecord &) const = default;
};

struct BuilderComponent final {
    FirmId firm{};
    bool active{false};
    double work_in_progress{0.0};
    double finished_inventory{0.0};
    double demand_expected{0.0};
    double produced_today{0.0};
    std::uint64_t dwellings_minted{0};

    bool operator==(const BuilderComponent &) const = default;
};

struct HousingAffordabilityState final {
    std::int32_t current_year{0};
    std::uint32_t years_completed{0};
    double price_sum{0.0};
    double rent_sum{0.0};
    double wage_sum{0.0};
    double labor_sum{0.0};
    std::uint32_t observed_days{0};
    double price_to_income_baseline{0.0};
    double rent_burden_baseline{0.0};
    double price_to_income_ratio{1.0};
    double rent_burden_ratio{1.0};
    double leave_home_multiplier{1.0};
    double fertility_multiplier{1.0};

    bool operator==(const HousingAffordabilityState &) const = default;
};

struct HousingMetrics final {
    double house_price{0.0};
    double rent_level{0.0};
    double housing_stock{0.0};
    double homeownership_share{0.0};
    double vacancy_share{0.0};
    double active_listings{0.0};
    double forced_listing_share{0.0};
    double session_sales{0.0};
    double session_volume{0.0};
    double mean_time_on_market_days{0.0};
    double mortgage_originations{0.0};
    double mortgage_principal_originated{0.0};
    double mortgage_principal_outstanding{0.0};
    double foreclosures{0.0};
    double rent_paid{0.0};
    double rent_unpaid{0.0};
    double evictions{0.0};
    double property_tax_paid{0.0};
    double housing_wealth_tax_paid{0.0};
    double transfer_tax_paid{0.0};
    double land_fee_paid{0.0};
    double construction_output{0.0};
    double dwellings_completed{0.0};
    double permits_used{0.0};
    double price_to_income_ratio{1.0};
    double rent_burden_ratio{1.0};
    double leave_home_multiplier{1.0};
    double fertility_multiplier{1.0};

    bool operator==(const HousingMetrics &) const = default;
};

struct M8Metrics final {
    M7Metrics economy{};
    EnergyMetrics energy{};
    HousingMetrics housing{};

    bool operator==(const M8Metrics &) const = default;
};

struct M8SimulationSpec final {
    M7SimulationSpec domestic_economy{};
    EnergyPolicyState energy_policy{};
    EnergyRules energy_rules{};
    EnergyExogenousInput energy_input{};
    HousingPolicyState housing_policy{};
    HousingRules housing_rules{};
    HousingExogenousInput housing_input{};
};

struct M8Runtime final {
    EnergyPolicyState energy_policy{};
    EnergyRules energy_rules{};
    EnergyExogenousInput energy_input{};
    std::vector<EnergyProducerComponent> energy_producers;
    std::vector<EnergyInputComponent> energy_inputs;
    std::vector<HouseholdEnergyComponent> household_energy;
    DeprivationState deprivation{};
    double strategic_reserve_stock{0.0};
    double strategic_reserve_cost{0.0};
    double energy_price{1.0};
    double slow_energy_price{1.0};
    std::uint64_t energy_event_counter{0};
    HousingPolicyState housing_policy{};
    HousingRules housing_rules{};
    HousingExogenousInput housing_input{};
    core::PropertyRegistry properties{};
    std::vector<HousingListing> housing_listings;
    std::vector<MortgageRecord> mortgages;
    std::vector<TenancyRecord> tenancies;
    std::vector<BuilderComponent> builders;
    HousingAffordabilityState housing_affordability{};
    double house_price{0.0};
    double rent_level{0.0};
    std::uint64_t genesis_dwelling_count{0};
    std::int32_t permit_year{0};
    std::uint64_t permits_used{0};
    std::uint64_t housing_event_counter{0};
    M8Metrics last_metrics{};

    bool operator==(const M8Runtime &) const = default;
};

struct M8AdvanceOptions final {
    M7AdvanceOptions base{};
    std::optional<EnergyExogenousInput> energy_input{};
    std::optional<HousingExogenousInput> housing_input{};
    M8FaultPoint fault_point{M8FaultPoint::none};
};

struct M8AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M8Metrics metrics{};
    std::uint64_t scratch_capacity_signature{0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};
};

enum class EnergyBuyerKind : std::uint8_t {
    household = 0,
    industry = 1,
    strategic_reserve = 2,
};

struct EnergyOrder final {
    EnergyBuyerKind kind{EnergyBuyerKind::household};
    std::uint64_t owner{0};
    AccountId account{};
    double demand{0.0};
    double budget{0.0};
    double allocated{0.0};
    double spending{0.0};
};

struct EnergyOffer final {
    FirmId firm{};
    AccountId account{};
    double stock{0.0};
    double price{0.0};
    double posted_price{0.0};
    double sold{0.0};
    double revenue{0.0};
    bool strategic_reserve{false};
};

class M8TickScratch final {
  public:
    void reserve(const core::RootState &state, const M8Runtime &runtime);
    [[nodiscard]] std::uint64_t capacity_signature() const noexcept;

    std::vector<EnergyProducerComponent> energy_producers_;
    std::vector<EnergyInputComponent> energy_inputs_;
    std::vector<HouseholdEnergyComponent> household_energy_;
    DeprivationState deprivation_{};
    std::vector<EnergyOrder> orders_;
    std::vector<EnergyOffer> offers_;
    std::vector<std::size_t> buyer_order_;
    std::vector<std::size_t> seller_order_;
    std::vector<double> industry_use_need_;
    std::vector<double> household_consumption_;
    std::vector<double> opening_balances_;
    std::vector<HousingListing> housing_listings_;
    std::vector<MortgageRecord> mortgages_;
    std::vector<TenancyRecord> tenancies_;
    std::vector<BuilderComponent> builders_;
    std::optional<core::PropertyRegistry> staged_properties_;
    HousingAffordabilityState housing_affordability_{};
    HousingExogenousInput housing_input_{};
    double house_price_{0.0};
    double rent_level_{0.0};
    std::int32_t permit_year_{0};
    std::uint64_t permits_used_{0};
    std::uint64_t housing_event_counter_{0};
    double strategic_reserve_stock_{0.0};
    double strategic_reserve_cost_{0.0};
    double energy_price_{1.0};
    double slow_energy_price_{1.0};
    std::uint64_t energy_event_counter_{0};
    M8Metrics working_metrics_{};
};

struct M8Initialization final {
    core::RootState root;
    M4Runtime real_economy_runtime;
    M5Runtime monetary_runtime;
    M6Runtime financial_runtime;
    M7Runtime population_runtime;
    M8Runtime runtime;
};

[[nodiscard]] Status validate_energy_policy(const EnergyPolicyState &policy) noexcept;
[[nodiscard]] Status validate_energy_rules(const EnergyRules &rules) noexcept;
[[nodiscard]] Status validate_energy_input(const EnergyExogenousInput &input) noexcept;
[[nodiscard]] Status validate_housing_policy(const HousingPolicyState &policy) noexcept;
[[nodiscard]] Status validate_housing_rules(const HousingRules &rules) noexcept;
[[nodiscard]] Status
validate_housing_input(const HousingExogenousInput &input) noexcept;
[[nodiscard]] Status validate_m8_spec(const M8SimulationSpec &spec) noexcept;
[[nodiscard]] Status validate_m8_state(const core::RootState &state,
                                       const M4Runtime &real_economy_runtime,
                                       const M5Runtime &monetary_runtime,
                                       const M6Runtime &financial_runtime,
                                       const M7Runtime &population_runtime,
                                       const M8Runtime &runtime, Tick tick) noexcept;
[[nodiscard]] Result<M8Initialization> build_m8_genesis(const M8SimulationSpec &spec);
[[nodiscard]] Result<M8AdvanceResult>
advance_m8_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch, M7Runtime &population_runtime,
                 M7TickScratch &population_scratch, M8Runtime &runtime,
                 M8TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M8AdvanceOptions &options = {});

} // namespace macro_sim::simulation

#endif
