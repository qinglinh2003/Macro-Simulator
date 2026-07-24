#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "macro_sim/c_api.h"

int main(void) {
    macro_sim_session* session = NULL;
    macro_sim_session* clone = NULL;
    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        121
    };
    macro_sim_m2_genesis_options genesis = {
        sizeof(macro_sim_m2_genesis_options),
        MACRO_SIM_M2_M4_V0_CASH_LOOP,
        1,
        1,
        0,
        4,
        2,
        0,
        2,
        400.0,
        0.0,
        77
    };
    macro_sim_m2_command commands[2];
    macro_sim_m2_receipt receipt;
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    uint8_t digest[32];
    uint8_t clone_digest[32];

    memset(commands, 0, sizeof(commands));
    commands[0].struct_size = sizeof(macro_sim_m2_command);
    commands[0].kind = MACRO_SIM_M2_TRANSFER;
    commands[0].primary_id = 6;
    commands[0].secondary_id = 7;
    commands[0].amount = 12.5;
    commands[1].struct_size = sizeof(macro_sim_m2_command);
    commands[1].kind = MACRO_SIM_M2_LOAN_ORIGINATION;
    commands[1].primary_id = 1;
    commands[1].secondary_id = 6;
    commands[1].tertiary_id = 1;
    commands[1].owner_kind = MACRO_SIM_M2_OWNER_HOUSEHOLD;
    commands[1].amount = 20.0;
    commands[1].rate = 0.04;
    commands[1].tick_b = 365;
    memset(&receipt, 0, sizeof(receipt));
    receipt.struct_size = sizeof(macro_sim_m2_receipt);

    if (macro_sim_session_create(&create, &session).code != MACRO_SIM_OK) {
        return 1;
    }
    if (macro_sim_m2_genesis(session, &genesis).code != MACRO_SIM_OK) {
        return 2;
    }
    if (macro_sim_m2_apply_batch(
            session,
            commands,
            2,
            &receipt
        ).code != MACRO_SIM_OK) {
        return 3;
    }
    if (receipt.created_loan_count != 1 || receipt.applied_mutations < 3) {
        return 4;
    }
    if (macro_sim_m2_state_digest(
            session,
            digest,
            sizeof(digest)
        ).code != MACRO_SIM_OK) {
        return 5;
    }
    if (macro_sim_m2_checkpoint_save(
            session,
            &checkpoint
        ).code != MACRO_SIM_OK || checkpoint.data == NULL
        || checkpoint.size == 0) {
        return 6;
    }

    create.session_id = 122;
    if (macro_sim_session_create(&create, &clone).code != MACRO_SIM_OK) {
        return 7;
    }
    if (macro_sim_m2_checkpoint_load(
            clone,
            checkpoint.data,
            checkpoint.size
        ).code != MACRO_SIM_OK) {
        return 8;
    }
    if (macro_sim_m2_state_digest(
            clone,
            clone_digest,
            sizeof(clone_digest)
        ).code != MACRO_SIM_OK
        || memcmp(digest, clone_digest, sizeof(digest)) != 0) {
        return 9;
    }
    if (macro_sim_owned_buffer_release(&checkpoint).code != MACRO_SIM_OK
        || checkpoint.data != NULL || checkpoint.size != 0) {
        return 10;
    }
    if (macro_sim_session_destroy(&clone).code != MACRO_SIM_OK
        || macro_sim_session_destroy(&session).code != MACRO_SIM_OK) {
        return 11;
    }
    return 0;
}
