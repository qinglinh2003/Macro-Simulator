#ifndef MACRO_SIM_C_API_H
#define MACRO_SIM_C_API_H

#include <stdint.h>
#include <stddef.h>

#include "macro_sim/export.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MACRO_SIM_ABI_VERSION 1u
#define MACRO_SIM_CAPABILITY_M2_ACCOUNTING (UINT64_C(1) << 0)
#define MACRO_SIM_CAPABILITY_M3_ALGORITHMS (UINT64_C(1) << 1)
#define MACRO_SIM_CAPABILITY_M4_TICK (UINT64_C(1) << 2)
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
    const char* message;
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
    const char* string_value;
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
    uint8_t* data;
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
MACRO_SIM_C_API const char* macro_sim_engine_version(void);
MACRO_SIM_C_API const char* macro_sim_error_code_name(macro_sim_error_code code);
MACRO_SIM_C_API macro_sim_status macro_sim_session_create(
    const macro_sim_create_options* options,
    macro_sim_session** output
);
MACRO_SIM_C_API macro_sim_status macro_sim_session_destroy(
    macro_sim_session** session
);
MACRO_SIM_C_API macro_sim_status macro_sim_session_id(
    const macro_sim_session* session,
    uint64_t* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_session_tick(
    const macro_sim_session* session,
    uint64_t* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_validate_scalar(
    const char* contract_id,
    size_t contract_id_size,
    const macro_sim_scalar* value,
    macro_sim_validation_code* output
);
MACRO_SIM_C_API const char* macro_sim_validation_code_name(
    macro_sim_validation_code code
);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_genesis(
    macro_sim_session* session,
    const macro_sim_m2_genesis_options* options
);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_apply_batch(
    macro_sim_session* session,
    const macro_sim_m2_command* commands,
    size_t command_count,
    macro_sim_m2_receipt* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_state_digest(
    const macro_sim_session* session,
    uint8_t* output,
    size_t output_size
);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_checkpoint_save(
    const macro_sim_session* session,
    macro_sim_owned_buffer* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_m2_checkpoint_load(
    macro_sim_session* session,
    const uint8_t* checkpoint,
    size_t checkpoint_size
);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_genesis(
    macro_sim_session* session,
    const macro_sim_m4_genesis_options* options
);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_advance(
    macro_sim_session* session,
    uint64_t tick_count,
    macro_sim_m4_advance_result* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_state_digest(
    const macro_sim_session* session,
    uint8_t* output,
    size_t output_size
);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_checkpoint_save(
    const macro_sim_session* session,
    macro_sim_owned_buffer* output
);
MACRO_SIM_C_API macro_sim_status macro_sim_m4_checkpoint_load(
    macro_sim_session* session,
    const uint8_t* checkpoint,
    size_t checkpoint_size
);
MACRO_SIM_C_API macro_sim_status macro_sim_owned_buffer_release(
    macro_sim_owned_buffer* buffer
);

#ifdef __cplusplus
}
#endif

#endif
