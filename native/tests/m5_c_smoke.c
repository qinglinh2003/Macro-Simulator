#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

#undef assert
#define assert(expression) \
    do { \
        if (!(expression)) { \
            return __LINE__; \
        } \
    } while (0)

int main(void) {
    assert(
        (macro_sim_capabilities()
         & MACRO_SIM_CAPABILITY_M5_MONETARY) != 0
    );

    macro_sim_session* session = NULL;
    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        505,
    };
    assert(macro_sim_session_create(&create, &session).code == MACRO_SIM_OK);

    macro_sim_m5_genesis_options genesis;
    memset(&genesis, 0, sizeof(genesis));
    genesis.struct_size = sizeof(genesis);
    genesis.monetary_regime = MACRO_SIM_M5_EXOGENOUS;
    genesis.economy_id = 1;
    genesis.currency_id = 1;
    genesis.matching_protocol = MACRO_SIM_M4_MATCH_SAMPLED;
    genesis.households = 12;
    genesis.consumption_firms = 3;
    genesis.capital_firms = 1;
    genesis.banks = 2;
    genesis.seed = 505;
    genesis.opening_capital_per_bank = 25.0;
    genesis.initial_policy_rate = 0.01;
    genesis.interbank = 1;
    genesis.household_credit = 1;
    assert(macro_sim_m5_genesis(session, &genesis).code == MACRO_SIM_OK);

    macro_sim_m5_advance_result result;
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    result.metrics.struct_size = sizeof(result.metrics);
    result.metrics.economy.struct_size = sizeof(result.metrics.economy);
    assert(macro_sim_m5_advance(session, 3, &result).code == MACRO_SIM_OK);
    assert(result.advanced_ticks == 3);
    assert(result.next_tick == 3);
    assert(result.metrics.alive_banks == 2);
    macro_sim_m5_policy policy;
    assert(macro_sim_m5_policy_defaults(&policy).code == MACRO_SIM_OK);
    policy.monetary_regime = MACRO_SIM_M5_MANUAL;
    policy.has_manual_policy_rate = 1;
    policy.manual_policy_rate = 0.03;
    assert(
        macro_sim_m5_update_policy(session, &policy).code
        == MACRO_SIM_OK
    );
    assert(macro_sim_m5_advance(session, 1, &result).code == MACRO_SIM_OK);
    assert(result.metrics.policy_rate == 0.03);

    uint8_t digest[32] = {0};
    assert(
        macro_sim_m5_state_digest(session, digest, sizeof(digest)).code
        == MACRO_SIM_OK
    );
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    assert(
        macro_sim_m5_checkpoint_save(session, &checkpoint).code
        == MACRO_SIM_OK
    );
    assert(checkpoint.data != NULL);
    assert(checkpoint.size > 0);

    macro_sim_session* resumed = NULL;
    assert(macro_sim_session_create(&create, &resumed).code == MACRO_SIM_OK);
    assert(
        macro_sim_m5_checkpoint_load(
            resumed,
            checkpoint.data,
            checkpoint.size
        ).code == MACRO_SIM_OK
    );
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    result.metrics.struct_size = sizeof(result.metrics);
    result.metrics.economy.struct_size = sizeof(result.metrics.economy);
    assert(macro_sim_m5_advance(resumed, 1, &result).code == MACRO_SIM_OK);
    assert(result.next_tick == 5);

    assert(macro_sim_owned_buffer_release(&checkpoint).code == MACRO_SIM_OK);
    assert(macro_sim_session_destroy(&resumed).code == MACRO_SIM_OK);
    assert(macro_sim_session_destroy(&session).code == MACRO_SIM_OK);
    return 0;
}
