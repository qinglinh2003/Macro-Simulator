#include "macro_sim/c_api.h"

#include "macro_sim/version.hpp"

uint32_t macro_sim_abi_version(void) {
    return macro_sim::abi_version();
}

const char* macro_sim_engine_version(void) {
    return macro_sim::kEngineVersion.data();
}
