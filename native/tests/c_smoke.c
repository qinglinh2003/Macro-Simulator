#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

int main(void) {
    macro_sim_session* session = NULL;
    macro_sim_create_options options = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        42
    };
    uint64_t value = 0;
    if (macro_sim_abi_version() != MACRO_SIM_ABI_VERSION) {
        return 1;
    }
    if (strcmp(macro_sim_engine_version(), "0.1.0-m1") != 0) {
        return 2;
    }
    if (macro_sim_session_create(&options, &session).code != MACRO_SIM_OK) {
        return 3;
    }
    if (macro_sim_session_id(session, &value).code != MACRO_SIM_OK || value != 42) {
        return 4;
    }
    if (macro_sim_session_tick(session, &value).code != MACRO_SIM_OK || value != 0) {
        return 5;
    }
    if (macro_sim_session_destroy(&session).code != MACRO_SIM_OK || session != NULL) {
        return 6;
    }
    return 0;
}
