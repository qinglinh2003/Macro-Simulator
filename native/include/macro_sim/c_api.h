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
    double principal_repaid;
    double loan_interest_paid;
    double household_interest_paid;
    double deposit_interest_paid;
    double total_loan_principal;
    double total_bank_capital;
    double total_reserves;
    double reserve_stock;
    double omo_flow;
    double lolr_advances;
    double interbank_volume;
    double interbank_rate;
    double run_flight_volume;
    double resolution_cost;
    double realized_credit_losses;
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
    uint32_t reserved_2;
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
    double firm_equity_market_cap;
    double bank_equity_market_cap;
    double equity_turnover;
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
MACRO_SIM_C_API macro_sim_status
macro_sim_owned_buffer_release(macro_sim_owned_buffer *buffer);

#ifdef __cplusplus
}
#endif

#endif
