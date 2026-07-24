#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

int main(void) {
    macro_sim_session* source = NULL;
    macro_sim_session* clone = NULL;
    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        401
    };
    macro_sim_m4_genesis_options genesis;
    macro_sim_m4_advance_result advanced;
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    uint8_t source_digest[32];
    uint8_t clone_digest[32];
    memset(&genesis, 0, sizeof(genesis));
    genesis.struct_size = sizeof(genesis);
    genesis.vertical = MACRO_SIM_M4_CAPITAL_FISCAL;
    genesis.economy_id = 1;
    genesis.currency_id = 1;
    genesis.matching_protocol = MACRO_SIM_M4_MATCH_SAMPLED;
    genesis.stochastic = 1;
    genesis.households = 20;
    genesis.consumption_firms = 4;
    genesis.capital_firms = 2;
    genesis.seed = 206;
    genesis.requested_capabilities =
        MACRO_SIM_M4_CAPABILITY_PHYSICAL_CAPITAL
        | MACRO_SIM_M4_CAPABILITY_GOVERNMENT;
    memset(&advanced, 0, sizeof(advanced));
    advanced.struct_size = sizeof(advanced);
    advanced.metrics.struct_size = sizeof(advanced.metrics);

    if ((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M4_TICK) == 0) {
        return 1;
    }
    if (macro_sim_session_create(&create, &source).code != MACRO_SIM_OK) {
        return 2;
    }
    genesis.requested_capabilities |= UINT64_C(1) << 10;
    if (macro_sim_m4_genesis(source, &genesis).code
        != MACRO_SIM_UNSUPPORTED) {
        return 2;
    }
    genesis.requested_capabilities =
        MACRO_SIM_M4_CAPABILITY_PHYSICAL_CAPITAL
        | MACRO_SIM_M4_CAPABILITY_GOVERNMENT;
    if (macro_sim_m4_genesis(source, &genesis).code != MACRO_SIM_OK) {
        return 2;
    }
    if (macro_sim_m4_advance(source, 10, &advanced).code != MACRO_SIM_OK
        || advanced.advanced_ticks != 10 || advanced.next_tick != 10
        || advanced.metrics.total_money != 3200.0) {
        return 3;
    }
    if (macro_sim_m4_state_digest(
            source,
            source_digest,
            sizeof(source_digest)
        ).code != MACRO_SIM_OK
        || macro_sim_m4_checkpoint_save(
            source,
            &checkpoint
        ).code != MACRO_SIM_OK) {
        return 4;
    }
    create.session_id = 402;
    if (macro_sim_session_create(&create, &clone).code != MACRO_SIM_OK
        || macro_sim_m4_checkpoint_load(
            clone,
            checkpoint.data,
            checkpoint.size
        ).code != MACRO_SIM_OK
        || macro_sim_m4_state_digest(
            clone,
            clone_digest,
            sizeof(clone_digest)
        ).code != MACRO_SIM_OK
        || memcmp(source_digest, clone_digest, 32) != 0) {
        return 5;
    }
    if (macro_sim_owned_buffer_release(&checkpoint).code != MACRO_SIM_OK
        || macro_sim_session_destroy(&clone).code != MACRO_SIM_OK
        || macro_sim_session_destroy(&source).code != MACRO_SIM_OK) {
        return 6;
    }
    return 0;
}
