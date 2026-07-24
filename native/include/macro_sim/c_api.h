#ifndef MACRO_SIM_C_API_H
#define MACRO_SIM_C_API_H

#include <stdint.h>

#include "macro_sim/export.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MACRO_SIM_ABI_VERSION 1u

MACRO_SIM_C_API uint32_t macro_sim_abi_version(void);
MACRO_SIM_C_API const char* macro_sim_engine_version(void);

#ifdef __cplusplus
}
#endif

#endif
