#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

int main(void) {
    macro_sim_session* session = NULL;
    macro_sim_create_options options = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        314159
    };
    uint64_t value = 0;
    macro_sim_validation_code validation = MACRO_SIM_VALIDATION_OK;
    macro_sim_scalar invalid_scalar = {
        MACRO_SIM_SCALAR_STRING,
        0,
        0.0,
        "bad",
        3
    };
    if (macro_sim_session_create(&options, &session).code != MACRO_SIM_OK) {
        return 1;
    }
    if (macro_sim_session_id(session, &value).code != MACRO_SIM_OK) {
        return 2;
    }
    if (value != 314159 || macro_sim_session_tick(session, &value).code != MACRO_SIM_OK) {
        return 3;
    }
    if (value != 0 || macro_sim_session_destroy(&session).code != MACRO_SIM_OK) {
        return 4;
    }
    if (session != NULL || strcmp(macro_sim_engine_version(), "0.4.0-m4") != 0) {
        return 5;
    }
    if ((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M3_ALGORITHMS) == 0) {
        return 8;
    }
    if ((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M4_TICK) == 0) {
        return 9;
    }
    if (macro_sim_validate_scalar(
            "config.a",
            8,
            &invalid_scalar,
            &validation
        ).code != MACRO_SIM_OK) {
        return 6;
    }
    if (validation != MACRO_SIM_VALIDATION_TYPE_MISMATCH) {
        return 7;
    }
    return 0;
}
