#ifndef MACRO_SIM_C_API_H
#define MACRO_SIM_C_API_H

#include <stddef.h>
#include <stdint.h>

#include "macro_sim/export.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MACRO_SIM_ABI_VERSION 1u
#define MACRO_SIM_CAPABILITY_M2_ACCOUNTING (UINT64_C(1) << 0)
#define MACRO_SIM_CAPABILITY_M3_ALGORITHMS (UINT64_C(1) << 1)
#define MACRO_SIM_CAPABILITY_M4_TICK (UINT64_C(1) << 2)
#define MACRO_SIM_CAPABILITY_M5_MONETARY (UINT64_C(1) << 3)
#define MACRO_SIM_CAPABILITY_M6_SECURITIES (UINT64_C(1) << 4)
#define MACRO_SIM_CAPABILITY_M7_POPULATION (UINT64_C(1) << 5)
#define MACRO_SIM_CAPABILITY_M8_ENERGY_HOUSING (UINT64_C(1) << 6)
#define MACRO_SIM_CAPABILITY_M9_WORLD (UINT64_C(1) << 7)
#define MACRO_SIM_M4_CAPABILITY_PHYSICAL_CAPITAL (UINT64_C(1) << 0)
#define MACRO_SIM_M4_CAPABILITY_GOVERNMENT (UINT64_C(1) << 1)

typedef enum macro_sim_error_code {
    MACRO_SIM_OK = 0,
    MACRO_SIM_INVALID_ARGUMENT = 1,
    MACRO_SIM_OUT_OF_RANGE = 2,
    MACRO_SIM_ALLOCATION_FAILURE = 3,
    MACRO_SIM_INVALID_HANDLE = 4,
    MACRO_SIM_INCOMPATIBLE_ABI = 5,
    MACRO_SIM_CONTRACT_VIOLATION = 6,
    MACRO_SIM_CORRUPT_INPUT = 7,
    MACRO_SIM_UNSUPPORTED = 8,
    MACRO_SIM_INTERNAL_ERROR = 9
} macro_sim_error_code;

typedef struct macro_sim_status {
    macro_sim_error_code code;
    const char *message;
} macro_sim_status;

typedef struct macro_sim_create_options {
    uint32_t struct_size;
    uint32_t abi_version;
    uint64_t session_id;
} macro_sim_create_options;

typedef struct macro_sim_session macro_sim_session;
typedef struct macro_sim_m9_world macro_sim_m9_world;

typedef enum macro_sim_scalar_kind {
    MACRO_SIM_SCALAR_NULL = 0,
    MACRO_SIM_SCALAR_BOOLEAN = 1,
    MACRO_SIM_SCALAR_INTEGER = 2,
    MACRO_SIM_SCALAR_NUMBER = 3,
    MACRO_SIM_SCALAR_STRING = 4,
    MACRO_SIM_SCALAR_ID_SET = 5
} macro_sim_scalar_kind;

typedef struct macro_sim_scalar {
    macro_sim_scalar_kind kind;
    int64_t integer_value;
    double number_value;
    const char *string_value;
    size_t string_size;
} macro_sim_scalar;

typedef enum macro_sim_m2_vertical {
    MACRO_SIM_M2_M4_V0_CASH_LOOP = 0,
    MACRO_SIM_M2_M4_V1_CAPITAL_FISCAL = 1
} macro_sim_m2_vertical;

typedef struct macro_sim_m2_genesis_options {
    uint32_t struct_size;
    uint32_t vertical;
    uint64_t economy_id;
    uint32_t currency_id;
    uint32_t government;
    uint64_t households;
    uint64_t consumption_firms;
    uint64_t capital_firms;
    uint64_t settlement_banks;
    double aggregate_opening_money;
    double aggregate_opening_capital;
    uint64_t seed;
} macro_sim_m2_genesis_options;

typedef enum macro_sim_m2_owner_kind {
    MACRO_SIM_M2_OWNER_HOUSEHOLD = 0,
    MACRO_SIM_M2_OWNER_FIRM = 1,
    MACRO_SIM_M2_OWNER_BANK = 2,
    MACRO_SIM_M2_OWNER_TREASURY = 3,
    MACRO_SIM_M2_OWNER_CENTRAL_BANK = 4,
    MACRO_SIM_M2_OWNER_DEALER = 5,
    MACRO_SIM_M2_OWNER_ROUNDING_RESIDUAL = 6,
    MACRO_SIM_M2_OWNER_INSTITUTION = 7
} macro_sim_m2_owner_kind;

typedef enum macro_sim_m2_command_kind {
    MACRO_SIM_M2_TRANSFER = 0,
    MACRO_SIM_M2_RESERVE_TRANSFER = 1,
    MACRO_SIM_M2_RESERVE_ISSUE = 2,
    MACRO_SIM_M2_LOAN_ORIGINATION = 3,
    MACRO_SIM_M2_LOAN_REPAYMENT = 4,
    MACRO_SIM_M2_OWNERSHIP_MUTATION = 5,
    MACRO_SIM_M2_COUNTER_INCREMENT = 6
} macro_sim_m2_command_kind;

typedef struct macro_sim_m2_command {
    uint32_t struct_size;
    uint32_t kind;
    uint64_t primary_id;
    uint64_t secondary_id;
    uint64_t tertiary_id;
    uint32_t owner_kind;
    uint32_t reserved;
    double amount;
    double rate;
    uint64_t tick_a;
    uint64_t tick_b;
} macro_sim_m2_command;

typedef struct macro_sim_m2_receipt {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t applied_mutations;
    uint64_t created_loan_count;
    uint8_t before_digest[32];
    uint8_t after_digest[32];
} macro_sim_m2_receipt;

typedef struct macro_sim_owned_buffer {
    uint8_t *data;
    size_t size;
} macro_sim_owned_buffer;

typedef enum macro_sim_m4_vertical {
    MACRO_SIM_M4_CASH_LOOP = 0,
    MACRO_SIM_M4_CAPITAL_FISCAL = 1
} macro_sim_m4_vertical;

typedef enum macro_sim_m4_matching_protocol {
    MACRO_SIM_M4_MATCH_SAMPLED = 0,
    MACRO_SIM_M4_MATCH_PREFERENTIAL = 1,
    MACRO_SIM_M4_MATCH_PRICE_SORTED = 2
} macro_sim_m4_matching_protocol;

typedef struct macro_sim_m4_genesis_options {
    uint32_t struct_size;
    uint32_t vertical;
    uint64_t economy_id;
    uint32_t currency_id;
    uint32_t matching_protocol;
    uint32_t stochastic;
    uint32_t reserved;
    uint64_t households;
    uint64_t consumption_firms;
    uint64_t capital_firms;
    uint64_t seed;
    uint64_t requested_capabilities;
} macro_sim_m4_genesis_options;

typedef struct macro_sim_m4_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t tick;
    double real_output;
    double nominal_output;
    double price_index;
    double unemployment_rate;
    double total_money;
    double conservation_drift;
    double aggregate_capital;
    double household_consumption;
    double wages_paid;
    double firm_profit;
    double tax_total;
    double government_spending;
    double government_deficit;
    double public_capital;
    double dividends_paid;
} macro_sim_m4_metrics;

typedef struct macro_sim_m4_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t scratch_capacity_signature;
    uint64_t transfer_count;
    uint64_t trade_count;
    macro_sim_m4_metrics metrics;
} macro_sim_m4_advance_result;

typedef enum macro_sim_m5_monetary_regime {
    MACRO_SIM_M5_EXOGENOUS = 0,
    MACRO_SIM_M5_TAYLOR = 1,
    MACRO_SIM_M5_MANUAL = 2
} macro_sim_m5_monetary_regime;

typedef struct macro_sim_m5_genesis_options {
    uint32_t struct_size;
    uint32_t monetary_regime;
    uint64_t economy_id;
    uint32_t currency_id;
    uint32_t matching_protocol;
    uint32_t stochastic;
    uint32_t reserved;
    uint64_t households;
    uint64_t consumption_firms;
    uint64_t capital_firms;
    uint64_t banks;
    uint64_t seed;
    double opening_capital_per_bank;
    double initial_policy_rate;
    double manual_policy_rate;
    uint32_t has_manual_policy_rate;
    uint32_t interbank;
    uint32_t household_credit;
    uint32_t bank_runs;
} macro_sim_m5_genesis_options;

typedef struct macro_sim_m5_policy {
    uint32_t struct_size;
    uint32_t monetary_regime;
    uint32_t has_manual_policy_rate;
    uint32_t open_market_operations;
    uint32_t reserve_target_indexes_deposits;
    uint32_t lender_of_last_resort;
    uint32_t bank_capital_constraint;
    uint32_t unified_bank_rwa;
    uint32_t migrate_relationships_on_failure;
    uint32_t state_resolution_backstop;
    uint32_t job_guarantee;
    uint32_t reserved;
    double government_consumption_share;
    double government_deficit_target;
    double deficit_unemployment_reference;
    double deficit_unemployment_cap;
    double government_investment_share;
    double profit_tax_rate;
    double income_tax_rate;
    double income_allowance;
    double consumption_tax_rate;
    double wealth_tax_rate;
    double wealth_allowance;
    double unemployment_benefit_replacement;
    double benefit_income_floor;
    double minimum_wage;
    double job_guarantee_wage_ratio;
    double job_guarantee_public_works_share;
    double inflation_target;
    double taylor_inflation;
    double taylor_unemployment;
    double rate_inertia;
    double manual_policy_rate;
    double neutral_rate;
    double natural_unemployment;
    double maximum_policy_rate;
    double inflation_sensor_lambda;
    double reserve_target;
    double reserve_gap_close;
    double reserve_floor_fraction;
    double firm_leverage_limit;
    double firm_minimum_dscr;
    double household_credit_limit;
    double bank_leverage_cap;
    double bank_exposure_limit;
    double bank_target_capital_ratio;
    double deposit_rate_floor;
} macro_sim_m5_policy;

typedef struct macro_sim_m5_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    macro_sim_m4_metrics economy;
    double policy_rate;
    double inflation_sensor;
    double new_credit;
    double firm_investment_target;
    double investment_user_cost_multiplier_mean;
    double household_debt_service_reserved;
    double firm_dscr_credit_shortfall;
    double principal_repaid;
    double loan_interest_paid;
    double household_interest_paid;
    double deposit_interest_paid;
    double deposit_interest_arrears;
    double total_loan_principal;
    double total_bank_capital;
    double total_reserves;
    double reserve_stock;
    double omo_flow;
    double lolr_advances;
    double lolr_outstanding;
    double interbank_volume;
    double interbank_rate;
    double run_flight_volume;
    double resolution_cost;
    double realized_credit_losses;
    double realized_interbank_losses;
    uint64_t alive_banks;
    uint64_t bank_failures;
} macro_sim_m5_metrics;

typedef struct macro_sim_m5_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t scratch_capacity_signature;
    uint64_t transfer_count;
    uint64_t trade_count;
    macro_sim_m5_metrics metrics;
} macro_sim_m5_advance_result;

typedef struct macro_sim_m6_genesis_options {
    uint32_t struct_size;
    uint32_t matching_protocol;
    uint64_t economy_id;
    uint32_t currency_id;
    uint32_t stochastic;
    uint32_t bonds;
    uint32_t firm_equity;
    uint32_t margin_credit;
    uint32_t firm_dynamics;
    uint32_t bank_dynamics;
    uint32_t reserved;
    uint64_t households;
    uint64_t consumption_firms;
    uint64_t capital_firms;
    uint64_t banks;
    uint64_t seed;
    uint32_t watchlist_size;
    uint32_t portfolio_review_interval_days;
    double opening_capital_per_bank;
    double initial_policy_rate;
} macro_sim_m6_genesis_options;

typedef struct macro_sim_m6_policy {
    uint32_t struct_size;
    uint32_t household_bankruptcy;
    uint32_t bank_resolution_fund;
    uint32_t reserved;
    uint64_t bond_maturity_days;
    double bond_finance_fraction;
    double bond_coupon_rate;
    double household_bond_target;
    double bank_bond_appetite;
    double bank_bond_duration_limit;
    double margin_ltv;
    double margin_max;
    double bank_minimum_capital;
} macro_sim_m6_policy;

typedef struct macro_sim_m6_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    macro_sim_m5_metrics economy;
    double bond_outstanding_face;
    double bond_market_value;
    double bond_issuance;
    double bond_redemption;
    double bond_coupon_paid;
    double household_bond_market_value;
    double bank_bond_market_value;
    double firm_equity_market_cap;
    double bank_equity_market_cap;
    double household_firm_equity_market_value;
    double household_bank_equity_market_value;
    double equity_turnover;
    double firm_equity_turnover;
    double bank_equity_turnover;
    double firm_equity_fundamental_value;
    double bank_equity_fundamental_value;
    double primary_equity_raised;
    double margin_principal;
    double margin_originated;
    double margin_repaid;
    double margin_writeoffs;
    double total_firm_book_equity;
    double clearing_residual;
    double sector_retool_capital;
    uint64_t active_security_lots;
    uint64_t household_bankruptcies;
    uint64_t firm_births;
    uint64_t firm_exits;
    uint64_t firm_defaults;
    uint64_t sector_switches;
    uint64_t bank_births;
    uint64_t bank_equity_resolutions;
} macro_sim_m6_metrics;

typedef struct macro_sim_m6_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t scratch_capacity_signature;
    uint64_t transfer_count;
    uint64_t trade_count;
    macro_sim_m6_metrics metrics;
} macro_sim_m6_advance_result;

typedef struct macro_sim_m6_bond {
    uint32_t struct_size;
    uint32_t issuer_kind;
    uint64_t id;
    uint64_t issuer_id;
    uint64_t issuer_account;
    uint32_t currency_id;
    uint32_t active;
    uint64_t issued_tick;
    uint64_t maturity_tick;
    double coupon_rate;
    double original_face;
    double outstanding_face;
    uint32_t settled;
    uint32_t reserved;
} macro_sim_m6_bond;

typedef struct macro_sim_m6_equity {
    uint32_t struct_size;
    uint32_t issuer_kind;
    uint64_t id;
    uint32_t owner_kind;
    uint32_t currency_id;
    uint64_t issuer_id;
    uint64_t issuer_account;
    double outstanding_shares;
    double price;
    double last_price;
    double peak_price;
    double fundamental;
    double trend;
    double income_signal;
    uint32_t active;
    uint32_t resolved;
} macro_sim_m6_equity;

typedef struct macro_sim_m6_firm_statement {
    uint32_t struct_size;
    uint32_t active;
    uint64_t firm_id;
    uint32_t stratum;
    uint32_t defaulted;
    double cash;
    double debt;
    double interest_arrears;
    double capital_units;
    double capital_unit_price;
    double capital_value;
    double output_inventory_units;
    double output_inventory_unit_price;
    double output_inventory_value;
    double inventory_value;
    double gross_assets;
    double book_equity;
    double eligible_collateral_value;
    double borrowing_base_proxy;
    double borrowing_base_headroom;
    double earnings;
} macro_sim_m6_firm_statement;

typedef struct macro_sim_m7_genesis_options {
    uint32_t struct_size;
    int32_t start_calendar_day;
    macro_sim_m6_genesis_options financial;
    uint64_t initial_persons;
    double target_household_size;
} macro_sim_m7_genesis_options;

typedef struct macro_sim_m7_policy {
    uint32_t struct_size;
    uint32_t reserved;
    double inheritance_tax_rate;
} macro_sim_m7_policy;

typedef struct macro_sim_m7_rules {
    uint32_t struct_size;
    uint32_t working_age;
    uint32_t retirement_age;
    uint32_t maximum_age;
    uint32_t beneficial_ownership;
    uint32_t estates;
    uint32_t fertility;
    uint32_t mortality;
    uint32_t persistent_labor;
    uint32_t fractional_hours;
    uint32_t second_jobs;
    uint32_t suspensions;
    uint32_t frictional_search;
    uint32_t relationship_wages;
    uint32_t job_ladder;
    uint32_t person_efficiency;
    uint32_t participation_margin;
    uint32_t age_participation;
    uint32_t family_transfers;
    uint32_t relationships;
    uint32_t marriage;
    uint32_t divorce;
    uint32_t household_lifecycle;
    uint32_t lifecycle_consumption;
    uint32_t leaving_home;
    uint32_t forbid_same_household;
    uint32_t forbid_close_kin;
    uint32_t suspension_timeout_days;
    uint32_t marriage_interval_days;
    uint32_t marriage_minimum_age;
    uint32_t marriage_maximum_age;
    uint32_t marriage_maximum_age_gap;
    uint32_t leave_home_min_age;
    uint32_t leave_home_peak_end_age;
    uint32_t demographic_feedback_burnin_years;
    double makeham_a;
    double gompertz_b;
    double gompertz_theta;
    double infant_extra;
    double total_fertility_rate;
    double fertility_peak_age;
    double fertility_width;
    double sex_ratio_at_birth;
    double vital_interval;
    double annual_churn;
    double firing_adjustment;
    double layoff_band;
    double target_smoothing;
    double suspension_quit_discount;
    double search_intensity;
    double ladder_search_intensity;
    double ladder_premium;
    double efficiency_sigma;
    double genesis_employment_rate;
    double young_participation_rate;
    double prime_participation_rate;
    double older_participation_rate;
    double reservation_markup;
    double welfare_quit_hazard;
    double family_transfer_buffer;
    double annual_leave_rate_peak;
    double annual_leave_rate_late;
    double annual_marriage_rate;
    double annual_divorce_rate;
    double marriage_preferred_age_gap;
    double marriage_age_gap_penalty;
    double marriage_assortativity;
    double lifecycle_income_propensity;
    double lifecycle_wealth_draw_propensity;
    double demographic_signal_halflife_years;
    double fertility_income_elasticity;
    double fertility_multiplier_minimum;
    double fertility_multiplier_maximum;
    double mortality_income_elasticity;
    double mortality_multiplier_minimum;
    double mortality_multiplier_maximum;
    uint32_t genesis_union_target_profile_enabled;
    double genesis_union_target_shares[6];
    uint32_t genesis_parent_minimum_age_gap;
    uint32_t genesis_parent_maximum_age_gap;
    double genesis_ideal_parent_age_gap;
    double genesis_parent_age_gap_stddev;
    uint32_t genesis_spouse_maximum_age_gap;
    double genesis_spouse_age_gap_stddev;
    double genesis_target_partnered_adult_share;
    double genesis_two_parent_assignment_share;
    uint32_t genesis_maximum_children_per_parent;
    uint32_t genesis_maximum_children_per_household;
    uint32_t social_union_target_profile_enabled;
    double social_union_target_shares[6];
    double marriage_peak_age;
    double marriage_age_width;
    double marriage_age_gap_stddev;
    double marriage_acceptance_base;
    double marriage_acceptance_age_gap_penalty;
    double remarriage_rate_multiplier;
    double widowed_remarriage_multiplier;
    double divorce_peak_duration_years;
    double divorce_duration_width;
    double divorce_peak_multiplier;
    double divorce_child_multiplier;
    double divorce_age_gap_multiplier_per_10y;
    uint32_t guardian_search_grandparents;
    uint32_t guardian_search_adult_siblings;
    uint32_t guardian_search_same_household_adults;
    uint32_t guardian_maximum_household_size;
} macro_sim_m7_rules;

typedef struct macro_sim_m7_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    macro_sim_m6_metrics economy;
    uint64_t population;
    uint64_t births;
    uint64_t deaths;
    double demographic_real_wage_signal;
    double demographic_fertility_multiplier;
    double demographic_mortality_multiplier;
    uint64_t households_with_members;
    double mean_household_size;
    double working_age_share;
    double dependency_ratio;
    double mean_person_efficiency;
    double person_efficiency_stddev;
    uint64_t active_unions;
    double mean_partner_age_gap;
    double mean_partner_log_efficiency_gap;
    double participation_rate;
    uint64_t estates_settled;
    uint64_t beneficial_lots_transferred;
    double inheritance_tax_share;
    double inheritance_tax_paid;
    double beneficial_projection_error;
    double employed_fte;
    double employed_heads;
    double unemployment;
    double unemployment_rate;
    double suspended;
    double job_guarantee;
    double out_of_labor_force;
    double labor_supply;
    double vacancies;
    double underemployed_heads;
    double underemployment_hours;
    double suspended_memo;
    double second_job_heads;
    double second_job_hours;
    double nonsearching;
    double job_to_job_moves;
    double mean_hourly_wage;
    double family_transfer_total;
    double family_transfer_recipients;
    double family_exposed_households;
    double hires;
    double separations;
    double suspension_poaches;
    uint64_t marriages;
    uint64_t divorces;
    uint64_t widowhoods;
    uint64_t remarriages;
    uint64_t widowed_remarriages;
    uint64_t guardian_same_household_assignments;
    uint64_t guardian_grandparent_assignments;
    uint64_t guardian_adult_sibling_assignments;
    uint64_t guardian_parent_assignments;
    uint64_t guardian_unresolved_assignments;
    double partnered_adult_share;
    double dual_parent_minor_share;
    double guardian_only_minor_share;
    double mean_mother_age_gap;
    double mother_age_gap_stddev;
    double mean_father_age_gap;
    double father_age_gap_stddev;
    uint64_t maximum_household_size;
    uint64_t leaving_home_events;
} macro_sim_m7_metrics;

typedef struct macro_sim_m7_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t scratch_capacity_signature;
    uint64_t transfer_count;
    uint64_t trade_count;
    macro_sim_m7_metrics metrics;
} macro_sim_m7_advance_result;

typedef struct macro_sim_m7_person {
    uint32_t struct_size;
    uint32_t sex;
    uint64_t id;
    int32_t birth_day;
    int32_t death_day;
    uint64_t mother_id;
    uint64_t father_id;
    uint64_t partner_id;
    uint64_t guardian_id;
    uint64_t household_id;
    int32_t marriage_start_day;
    int32_t last_divorce_day;
    int32_t last_widowed_day;
    uint32_t marriage_count;
    double efficiency;
    uint32_t participating;
    uint32_t searching;
    uint32_t alive;
} macro_sim_m7_person;

typedef struct macro_sim_m7_membership {
    uint32_t struct_size;
    uint32_t alive;
    uint64_t person_id;
    uint64_t household_id;
} macro_sim_m7_membership;

typedef struct macro_sim_m7_job {
    uint32_t struct_size;
    uint32_t active;
    uint64_t id;
    uint64_t person_id;
    uint64_t firm_id;
    int32_t hire_day;
    int32_t separation_day;
    int32_t suspension_day;
    uint32_t separation_kind;
    double wage;
    double hours;
    uint32_t secondary;
    uint32_t suspended;
} macro_sim_m7_job;

typedef struct macro_sim_m7_union {
    uint32_t struct_size;
    uint32_t active;
    uint64_t event_id;
    uint64_t first_id;
    uint64_t second_id;
    uint64_t first_origin_household_id;
    uint64_t second_origin_household_id;
    int32_t start_day;
    int32_t end_day;
    uint32_t end_kind;
    uint32_t reserved;
} macro_sim_m7_union;

typedef struct macro_sim_m7_estate {
    uint32_t struct_size;
    uint32_t settled;
    uint64_t event_id;
    uint64_t deceased_id;
    uint64_t heir_id;
    uint64_t household_id;
    uint64_t destination_household_id;
    int32_t opened_day;
    int32_t settled_day;
    uint64_t transferred_lots;
    double gross_share;
    double tax_share;
    double gross_value;
    double liabilities;
    double tax_paid;
    uint32_t public_residual;
    uint32_t reserved;
} macro_sim_m7_estate;

typedef enum macro_sim_m8_energy_rationing {
    MACRO_SIM_M8_ENERGY_RATION_MARKET = 0,
    MACRO_SIM_M8_ENERGY_RATION_PROPORTIONAL = 1,
    MACRO_SIM_M8_ENERGY_RATION_HOUSEHOLD_FIRST = 2,
    MACRO_SIM_M8_ENERGY_RATION_INDUSTRY_FIRST = 3
} macro_sim_m8_energy_rationing;

typedef struct macro_sim_m8_energy_policy {
    uint32_t struct_size;
    uint32_t price_cap_compensation;
    uint32_t state_owned_price_at_cost;
    uint32_t rationing;
    double excise_rate;
    double household_subsidy_rate;
    double subsidy_deposit_threshold;
    double price_cap;
    double strategic_reserve_target;
    double strategic_reserve_flow_cap;
} macro_sim_m8_energy_policy;

typedef struct macro_sim_m8_energy_rules {
    uint32_t struct_size;
    uint32_t enabled;
    uint32_t household_energy;
    uint32_t deprivation;
    uint32_t state_owned_first_producer;
    uint32_t deprivation_burnin_years;
    uint32_t deprivation_acute_days;
    uint32_t deprivation_chronic_days;
    uint32_t reserved;
    uint64_t producer_count;
    double initial_producer_cash;
    double initial_price;
    double initial_wage;
    double initial_markup;
    double producer_productivity;
    double capacity_per_capital;
    double initial_utilization;
    double producer_inventory_ratio;
    double demand_adjustment;
    double markup_adjustment;
    double markup_minimum;
    double markup_maximum;
    double household_need;
    double downstream_intensity;
    double downstream_coverage_days;
    double downstream_gap_close;
    double hoarding_beta;
    double slow_price_days;
    double deprivation_subsistence_share;
    double fuel_poverty_threshold;
    double fuel_poverty_mortality_gamma;
    double fuel_poverty_mortality_cap;
} macro_sim_m8_energy_rules;

typedef struct macro_sim_m8_energy_input {
    uint32_t struct_size;
    uint32_t reserved;
    double capacity_multiplier;
    double labor_availability_multiplier;
    double supply_multiplier;
    double household_demand_multiplier;
    double industry_demand_multiplier;
    double reference_price_multiplier;
} macro_sim_m8_energy_input;

typedef struct macro_sim_m8_housing_policy {
    uint32_t struct_size;
    uint32_t mortgage_underwriting;
    uint32_t rental_eviction_arrears;
    uint32_t reserved;
    uint64_t annual_housing_permits;
    double mortgage_ltv_cap;
    double mortgage_dsti_cap;
    double mortgage_stress_rate_addon;
    double mortgage_risk_weight;
    double mortgage_minimum_capital_ratio;
    double mortgage_foreclosure_ltv;
    double mortgage_arrears_floor;
    double land_fee_share;
    double land_fee_stock_elasticity;
    double transfer_tax_rate;
    double property_tax_rate;
} macro_sim_m8_housing_policy;

typedef struct macro_sim_m8_housing_rules {
    uint32_t struct_size;
    uint32_t enabled;
    uint32_t resale_market;
    uint32_t mortgages;
    uint32_t rentals;
    uint32_t construction;
    uint32_t location_count;
    uint32_t market_interval_days;
    uint32_t buyer_search_count;
    uint32_t builder_land_fee_credit;
    uint32_t affordability_burnin_years;
    uint32_t reserved;
    uint64_t builder_count;
    double house_price_income_years;
    double initial_dwellings_per_household;
    double initial_homeownership_share;
    double initial_floor_area;
    double initial_quality;
    double voluntary_ask_markup;
    double forced_sale_discount;
    double ask_decay;
    double demand_price_step;
    double ask_floor_annual_wage_share;
    double buyer_liquidity_buffer;
    double distress_deposit_floor;
    double initial_rent_yield;
    double rent_adjustment;
    double rent_burden_cap;
    double rental_investor_premium;
    double rental_vacancy_deadband;
    double rent_floor_wage_share;
    double initial_builder_cash_buffer;
    double builder_productivity;
    double builder_demand_seed;
    double builder_demand_price_gain;
    double builder_finished_inventory_buffer;
    double leave_home_elasticity;
    double leave_home_multiplier_minimum;
    double leave_home_multiplier_maximum;
    double fertility_elasticity;
    double fertility_multiplier_minimum;
    double fertility_multiplier_maximum;
} macro_sim_m8_housing_rules;

typedef struct macro_sim_m8_housing_input {
    uint32_t struct_size;
    uint32_t reserved;
    double house_price_reference_multiplier;
    double buyer_demand_multiplier;
    double rental_demand_multiplier;
    double construction_productivity_multiplier;
    double land_cost_multiplier;
} macro_sim_m8_housing_input;

typedef struct macro_sim_m8_genesis_options {
    uint32_t struct_size;
    uint32_t reserved;
    macro_sim_m7_genesis_options domestic_economy;
    macro_sim_m8_energy_policy energy_policy;
    macro_sim_m8_energy_rules energy_rules;
    macro_sim_m8_energy_input energy_input;
    macro_sim_m8_housing_policy housing_policy;
    macro_sim_m8_housing_rules housing_rules;
    macro_sim_m8_housing_input housing_input;
} macro_sim_m8_genesis_options;

typedef struct macro_sim_m8_energy_metrics {
    uint32_t struct_size;
    uint32_t deprivation_boundary;
    double production;
    double capacity;
    double utilization;
    double opening_supply;
    double requested_total;
    double requested_households;
    double requested_industry;
    double requested_public;
    double sold;
    double unfilled;
    double transaction_price;
    double household_units;
    double household_spending;
    double industry_units;
    double industry_spending;
    double excise_paid;
    double subsidy_paid;
    double cap_compensation;
    double strategic_reserve_stock;
    double strategic_reserve_flow;
    double strategic_reserve_purchase_paid;
    double strategic_reserve_sale_revenue;
    double fuel_poverty_share;
    double fuel_poverty_mortality_multiplier;
    double deprivation_below_100_share;
    double deprivation_below_60_share;
    double deprivation_below_30_share;
    double deprivation_destitute_share;
    double deprivation_acute_stock;
    double deprivation_chronic_stock;
    double deprivation_max_spell_days;
    double producer_capital;
} macro_sim_m8_energy_metrics;

typedef struct macro_sim_m8_housing_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    double house_price;
    double rent_level;
    double housing_stock;
    double homeownership_share;
    double vacancy_share;
    double active_listings;
    double forced_listing_share;
    double session_sales;
    double session_volume;
    double mean_time_on_market_days;
    double mortgage_originations;
    double mortgage_principal_originated;
    double mortgage_principal_outstanding;
    double foreclosures;
    double rent_paid;
    double rent_unpaid;
    double evictions;
    double property_tax_paid;
    double transfer_tax_paid;
    double land_fee_paid;
    double construction_output;
    double dwellings_completed;
    double permits_used;
    double price_to_income_ratio;
    double rent_burden_ratio;
    double leave_home_multiplier;
    double fertility_multiplier;
} macro_sim_m8_housing_metrics;

typedef struct macro_sim_m8_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    macro_sim_m7_metrics economy;
    macro_sim_m8_energy_metrics energy;
    macro_sim_m8_housing_metrics housing;
} macro_sim_m8_metrics;

typedef struct macro_sim_m8_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t scratch_capacity_signature;
    uint64_t transfer_count;
    uint64_t trade_count;
    macro_sim_m8_metrics metrics;
} macro_sim_m8_advance_result;

typedef struct macro_sim_m8_dwelling {
    uint32_t struct_size;
    uint32_t active;
    uint64_t id;
    uint32_t owner_kind;
    uint32_t location;
    uint64_t owner_id;
    uint64_t occupant_household_id;
    uint64_t collateral_loan_id;
    uint64_t minted_tick;
    uint64_t last_title_tick;
    uint32_t age_days;
    uint32_t reserved;
    double floor_area;
    double quality;
} macro_sim_m8_dwelling;

typedef struct macro_sim_m8_listing {
    uint32_t struct_size;
    uint32_t active;
    uint64_t dwelling_id;
    uint32_t seller_kind;
    uint32_t forced;
    uint64_t seller_id;
    uint64_t listed_tick;
    double asking_price;
} macro_sim_m8_listing;

typedef struct macro_sim_m8_mortgage {
    uint32_t struct_size;
    uint32_t active;
    uint64_t loan_id;
    uint64_t borrower_household_id;
    uint64_t lender_bank_id;
    uint64_t collateral_dwelling_id;
    uint64_t originated_tick;
    uint32_t foreclosed;
    uint32_t reserved;
    double original_principal;
    double purchase_price;
    double qualifying_income;
    double stressed_payment;
} macro_sim_m8_mortgage;

typedef struct macro_sim_m8_tenancy {
    uint32_t struct_size;
    uint32_t active;
    uint64_t id;
    uint64_t dwelling_id;
    uint64_t landlord_household_id;
    uint64_t tenant_household_id;
    uint64_t started_tick;
    uint64_t ended_tick;
    uint32_t missed_days;
    uint32_t reserved;
    double daily_rent;
} macro_sim_m8_tenancy;

typedef struct macro_sim_m8_builder {
    uint32_t struct_size;
    uint32_t active;
    uint64_t firm_id;
    uint64_t dwellings_minted;
    double work_in_progress;
    double finished_inventory;
    double demand_expected;
    double produced_today;
} macro_sim_m8_builder;

typedef struct macro_sim_m8_energy_producer {
    uint32_t struct_size;
    uint32_t active;
    uint32_t state_owned;
    uint32_t reserved;
    uint64_t firm_id;
    double capacity_per_capital;
    double inventory;
    double inventory_cost;
    double produced;
    double sales;
    double revenue;
    double demand_expected;
} macro_sim_m8_energy_producer;

typedef enum macro_sim_m9_fx_regime {
    MACRO_SIM_M9_FX_FLOAT = 0,
    MACRO_SIM_M9_FX_PEG = 1
} macro_sim_m9_fx_regime;

typedef enum macro_sim_m9_shock_kind {
    MACRO_SIM_M9_SHOCK_PRODUCTIVITY = 0,
    MACRO_SIM_M9_SHOCK_LABOR_AVAILABILITY = 1,
    MACRO_SIM_M9_SHOCK_ENERGY_CAPACITY = 2,
    MACRO_SIM_M9_SHOCK_HOUSEHOLD_DEMAND = 3,
    MACRO_SIM_M9_SHOCK_IMPORT_CAPACITY = 4,
    MACRO_SIM_M9_SHOCK_EXPORT_CAPACITY = 5,
    MACRO_SIM_M9_SHOCK_CREDIT_SUPPLY = 6,
    MACRO_SIM_M9_SHOCK_CAPITAL_DESTRUCTION = 7,
    MACRO_SIM_M9_SHOCK_SOVEREIGN_RISK_PREMIUM = 8,
    MACRO_SIM_M9_SHOCK_CAPITAL_OUTFLOW_PRESSURE = 9
} macro_sim_m9_shock_kind;

typedef enum macro_sim_m9_shock_shape {
    MACRO_SIM_M9_SHOCK_STEP = 0,
    MACRO_SIM_M9_SHOCK_LINEAR = 1,
    MACRO_SIM_M9_SHOCK_TRIANGULAR = 2
} macro_sim_m9_shock_shape;

typedef enum macro_sim_m9_shock_sector {
    MACRO_SIM_M9_SHOCK_SECTOR_CONSUMPTION = 0,
    MACRO_SIM_M9_SHOCK_SECTOR_CAPITAL = 1,
    MACRO_SIM_M9_SHOCK_SECTOR_ENERGY = 2,
    MACRO_SIM_M9_SHOCK_SECTOR_HOUSING = 3,
    MACRO_SIM_M9_SHOCK_SECTOR_PUBLIC = 4
} macro_sim_m9_shock_sector;

typedef enum macro_sim_m9_shock_event_type {
    MACRO_SIM_M9_SHOCK_ANNOUNCED = 0,
    MACRO_SIM_M9_SHOCK_STARTED = 1,
    MACRO_SIM_M9_SHOCK_ENDED = 2,
    MACRO_SIM_M9_SHOCK_REALIZED = 3
} macro_sim_m9_shock_event_type;

typedef struct macro_sim_m9_shock {
    uint32_t struct_size;
    uint32_t kind;
    uint32_t shape;
    uint32_t has_economy;
    uint32_t has_announcement;
    uint32_t has_sector;
    uint32_t sector;
    uint32_t reserved;
    uint64_t id;
    uint64_t economy_id;
    uint64_t start_tick;
    uint64_t announcement_tick;
    uint64_t duration;
    double magnitude;
    uint64_t ramp_in_ticks;
    uint64_t ramp_out_ticks;
} macro_sim_m9_shock;

typedef struct macro_sim_m9_shock_event {
    uint32_t struct_size;
    uint32_t type;
    uint64_t sequence;
    uint64_t tick;
    uint64_t shock_id;
    double intensity;
} macro_sim_m9_shock_event;

typedef struct macro_sim_m9_world_rules {
    uint32_t struct_size;
    uint32_t trade;
    uint32_t capital;
    uint32_t migration;
    uint32_t fx_loss_mutualization;
    uint32_t reserved;
    uint64_t dense_edge_threshold;
    double fx_adjustment;
    double fx_friction;
    double fx_spread;
    double fx_trade_cap;
    double capital_mobility;
    double capital_adjustment;
    double periods_per_year;
    double migration_rate;
    double migration_max_share;
    double remittance_share;
    double wage_smoothing;
    double initial_peg_reserves;
} macro_sim_m9_world_rules;

typedef struct macro_sim_m9_external_policy {
    uint32_t struct_size;
    uint32_t has_import_quota;
    uint32_t has_immigration_cap;
    uint32_t has_emigration_cap;
    uint32_t fx_regime;
    uint32_t has_peg_anchor;
    uint32_t reserved;
    uint32_t reserved_2;
    uint64_t peg_anchor;
    const uint64_t *sanctions;
    size_t sanction_count;
    double tariff;
    double import_quota;
    double export_subsidy;
    double capital_control;
    double external_interest_settlement_fraction;
    double immigration_cap;
    double emigration_cap;
    double remittance_tax;
    double outward_remittance_tax;
    double guest_worker_return;
    double peg_reserve_scale;
} macro_sim_m9_external_policy;

typedef struct macro_sim_m9_genesis_options {
    uint32_t struct_size;
    uint32_t reserved;
    const macro_sim_m8_genesis_options *economies;
    size_t economy_count;
    const macro_sim_m9_external_policy *external_policies;
    size_t external_policy_count;
    const macro_sim_m9_shock *shocks;
    size_t shock_count;
    macro_sim_m9_world_rules rules;
} macro_sim_m9_genesis_options;

typedef struct macro_sim_m9_country_metrics {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t economy_id;
    uint64_t active_shocks;
    double exchange_rate;
    double imports_value;
    double imports_volume;
    double exports_value;
    double exports_volume;
    double iceberg_loss;
    double tariff_revenue;
    double export_subsidy_cost;
    double current_account;
    double capital_flow;
    double net_foreign_assets;
    double factor_income_accrued;
    double factor_income_cash;
    double factor_income_arrears;
    double peg_reserves;
    double migrant_stock_abroad;
    double migrant_stock_hosted;
    double remittances_received;
    double remittances_sent;
    double remittance_tax_revenue;
    double capital_destroyed;
    double fx_mutualization_paid;
} macro_sim_m9_country_metrics;

typedef struct macro_sim_m9_advance_result {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t first_tick;
    uint64_t next_tick;
    uint64_t advanced_ticks;
    uint64_t digest;
    uint64_t trade_routes;
    uint64_t migration_routes;
    uint64_t shock_events;
    double dealer_flow;
    double dealer_spread_revenue;
    double dealer_valuation;
    double world_nfa;
} macro_sim_m9_advance_result;

typedef enum macro_sim_validation_code {
    MACRO_SIM_VALIDATION_OK = 0,
    MACRO_SIM_VALIDATION_UNKNOWN_CONTRACT = 1,
    MACRO_SIM_VALIDATION_TYPE_MISMATCH = 2,
    MACRO_SIM_VALIDATION_NONFINITE = 3,
    MACRO_SIM_VALIDATION_BELOW_MINIMUM = 4,
    MACRO_SIM_VALIDATION_ABOVE_MAXIMUM = 5,
    MACRO_SIM_VALIDATION_INVALID_CHOICE = 6
} macro_sim_validation_code;

MACRO_SIM_C_API uint32_t macro_sim_abi_version(void);
MACRO_SIM_C_API uint64_t macro_sim_capabilities(void);
MACRO_SIM_C_API const char *macro_sim_engine_version(void);
MACRO_SIM_C_API const char *macro_sim_error_code_name(macro_sim_error_code code);
MACRO_SIM_C_API macro_sim_status macro_sim_session_create(
    const macro_sim_create_options *options, macro_sim_session **output);
MACRO_SIM_C_API macro_sim_status macro_sim_session_destroy(macro_sim_session **session);
MACRO_SIM_C_API macro_sim_status macro_sim_session_id(const macro_sim_session *session,
                                                      uint64_t *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_session_tick(const macro_sim_session *session, uint64_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_validate_scalar(
    const char *contract_id, size_t contract_id_size, const macro_sim_scalar *value,
    macro_sim_validation_code *output);
MACRO_SIM_C_API const char *
macro_sim_validation_code_name(macro_sim_validation_code code);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_genesis(
    macro_sim_session *session, const macro_sim_m2_genesis_options *options);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_apply_batch(
    macro_sim_session *session, const macro_sim_m2_command *commands,
    size_t command_count, macro_sim_m2_receipt *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_genesis(
    macro_sim_session *session, const macro_sim_m4_genesis_options *options);
MACRO_SIM_C_API macro_sim_status
macro_sim_m4_advance(macro_sim_session *session, uint64_t tick_count,
                     macro_sim_m4_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m5_genesis(
    macro_sim_session *session, const macro_sim_m5_genesis_options *options);
MACRO_SIM_C_API macro_sim_status macro_sim_m5_update_policy(
    macro_sim_session *session, const macro_sim_m5_policy *policy);
MACRO_SIM_C_API macro_sim_status
macro_sim_m5_policy_defaults(macro_sim_m5_policy *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m5_advance(macro_sim_session *session, uint64_t tick_count,
                     macro_sim_m5_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m5_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m5_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m5_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_genesis(
    macro_sim_session *session, const macro_sim_m6_genesis_options *options);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_update_policy(
    macro_sim_session *session, const macro_sim_m6_policy *policy);
MACRO_SIM_C_API macro_sim_status
macro_sim_m6_policy_defaults(macro_sim_m6_policy *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m6_advance(macro_sim_session *session, uint64_t tick_count,
                     macro_sim_m6_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status
macro_sim_m6_bond_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_bonds(const macro_sim_session *session,
                                                    size_t offset,
                                                    macro_sim_m6_bond *output,
                                                    size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m6_equity_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_equities(const macro_sim_session *session,
                                                       size_t offset,
                                                       macro_sim_m6_equity *output,
                                                       size_t capacity,
                                                       size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m6_firm_statement_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m6_firm_statements(
    const macro_sim_session *session, size_t offset,
    macro_sim_m6_firm_statement *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_genesis(
    macro_sim_session *session, const macro_sim_m7_genesis_options *options);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_update_policy(
    macro_sim_session *session, const macro_sim_m7_policy *policy);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_policy_defaults(macro_sim_m7_policy *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_update_rules(macro_sim_session *session, const macro_sim_m7_rules *rules);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_rules_defaults(macro_sim_m7_rules *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_advance(macro_sim_session *session, uint64_t tick_count,
                     macro_sim_m7_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_person_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_persons(const macro_sim_session *session,
                                                      size_t offset,
                                                      macro_sim_m7_person *output,
                                                      size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_membership_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_memberships(
    const macro_sim_session *session, size_t offset, macro_sim_m7_membership *output,
    size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_job_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_jobs(const macro_sim_session *session,
                                                   size_t offset,
                                                   macro_sim_m7_job *output,
                                                   size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_union_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_unions(const macro_sim_session *session,
                                                     size_t offset,
                                                     macro_sim_m7_union *output,
                                                     size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m7_estate_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m7_estates(const macro_sim_session *session,
                                                      size_t offset,
                                                      macro_sim_m7_estate *output,
                                                      size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_defaults(macro_sim_m8_genesis_options *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_genesis(
    macro_sim_session *session, const macro_sim_m8_genesis_options *options);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_update_energy_policy(
    macro_sim_session *session, const macro_sim_m8_energy_policy *policy);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_update_housing_policy(
    macro_sim_session *session, const macro_sim_m8_housing_policy *policy);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_update_energy_input(
    macro_sim_session *session, const macro_sim_m8_energy_input *input);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_update_housing_input(
    macro_sim_session *session, const macro_sim_m8_housing_input *input);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_advance(macro_sim_session *session, uint64_t tick_count,
                     macro_sim_m8_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_state_digest(
    const macro_sim_session *session, uint8_t *output, size_t output_size);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_checkpoint_save(
    const macro_sim_session *session, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_checkpoint_load(
    macro_sim_session *session, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_dwelling_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_dwellings(const macro_sim_session *session, size_t offset,
                       macro_sim_m8_dwelling *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_listing_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_listings(const macro_sim_session *session,
                                                       size_t offset,
                                                       macro_sim_m8_listing *output,
                                                       size_t capacity,
                                                       size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_mortgage_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_mortgages(const macro_sim_session *session, size_t offset,
                       macro_sim_m8_mortgage *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_tenancy_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_tenancies(const macro_sim_session *session, size_t offset,
                       macro_sim_m8_tenancy *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_builder_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_builders(const macro_sim_session *session,
                                                       size_t offset,
                                                       macro_sim_m8_builder *output,
                                                       size_t capacity,
                                                       size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m8_energy_producer_count(const macro_sim_session *session, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m8_energy_producers(
    const macro_sim_session *session, size_t offset,
    macro_sim_m8_energy_producer *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_world_rules_defaults(macro_sim_m9_world_rules *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_external_policy_defaults(macro_sim_m9_external_policy *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_create(
    const macro_sim_m9_genesis_options *options, macro_sim_m9_world **output);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_destroy(macro_sim_m9_world **world);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_world_tick(const macro_sim_m9_world *world, uint64_t *output);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_world_advance(macro_sim_m9_world *world, uint64_t tick_count,
                           macro_sim_m9_advance_result *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_update_external_policies(
    macro_sim_m9_world *world, const macro_sim_m9_external_policy *policies,
    size_t policy_count);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_schedule_shock(
    macro_sim_m9_world *world, const macro_sim_m9_shock *shock);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_world_shock_event_count(const macro_sim_m9_world *world, size_t *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_shock_events(
    const macro_sim_m9_world *world, size_t offset, macro_sim_m9_shock_event *output,
    size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status
macro_sim_m9_world_rates(const macro_sim_m9_world *world, size_t offset, double *output,
                         size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_country_metrics(
    const macro_sim_m9_world *world, size_t offset,
    macro_sim_m9_country_metrics *output, size_t capacity, size_t *written);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_checkpoint_save(
    const macro_sim_m9_world *world, macro_sim_owned_buffer *output);
MACRO_SIM_C_API macro_sim_status macro_sim_m9_world_checkpoint_load(
    macro_sim_m9_world *world, const uint8_t *checkpoint, size_t checkpoint_size);
MACRO_SIM_C_API macro_sim_status
macro_sim_owned_buffer_release(macro_sim_owned_buffer *buffer);

#ifdef __cplusplus
}
#endif

#endif
