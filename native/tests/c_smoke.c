#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

int main(void) {
    if (macro_sim_abi_version() != MACRO_SIM_ABI_VERSION) {
        return 1;
    }
    if (strcmp(macro_sim_engine_version(), "0.1.0-m1") != 0) {
        return 2;
    }
    return 0;
}
