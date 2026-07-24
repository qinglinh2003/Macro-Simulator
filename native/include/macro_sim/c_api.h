#ifndef MACRO_SIM_C_API_H
#define MACRO_SIM_C_API_H

#include <stdint.h>

#include "macro_sim/export.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MACRO_SIM_ABI_VERSION 1u

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

MACRO_SIM_C_API uint32_t macro_sim_abi_version(void);
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

#ifdef __cplusplus
}
#endif

#endif
