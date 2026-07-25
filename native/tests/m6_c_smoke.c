#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "macro_sim/c_api.h"

#define CHECK(condition)                                                               \
    do {                                                                               \
        if (!(condition)) {                                                            \
            abort();                                                                   \
        }                                                                              \
    } while (0)

static void require_ok(macro_sim_status status) { CHECK(status.code == MACRO_SIM_OK); }

int main(void) {
    CHECK((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M6_SECURITIES) != 0);
    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        66,
    };
    macro_sim_session *session = NULL;
    require_ok(macro_sim_session_create(&create, &session));

    macro_sim_m6_genesis_options genesis;
    memset(&genesis, 0, sizeof(genesis));
    genesis.struct_size = sizeof(genesis);
    genesis.matching_protocol = MACRO_SIM_M4_MATCH_SAMPLED;
    genesis.economy_id = 1;
    genesis.currency_id = 1;
    genesis.bonds = 1;
    genesis.firm_equity = 1;
    genesis.margin_credit = 1;
    genesis.households = 24;
    genesis.consumption_firms = 4;
    genesis.capital_firms = 2;
    genesis.banks = 3;
    genesis.seed = 66;
    genesis.watchlist_size = 3;
    genesis.opening_capital_per_bank = 25.0;
    genesis.initial_policy_rate = 0.002;
    require_ok(macro_sim_m6_genesis(session, &genesis));

    macro_sim_m6_policy policy;
    require_ok(macro_sim_m6_policy_defaults(&policy));
    policy.bond_maturity_days = 15;
    require_ok(macro_sim_m6_update_policy(session, &policy));

    macro_sim_m6_advance_result result;
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    result.metrics.struct_size = sizeof(result.metrics);
    result.metrics.economy.struct_size = sizeof(result.metrics.economy);
    result.metrics.economy.economy.struct_size = sizeof(result.metrics.economy.economy);
    require_ok(macro_sim_m6_advance(session, 8, &result));
    CHECK(result.advanced_ticks == 8);
    CHECK(result.next_tick == 8);
    CHECK(result.metrics.active_security_lots > 0);

    size_t equity_count = 0;
    require_ok(macro_sim_m6_equity_count(session, &equity_count));
    CHECK(equity_count == 7);
    macro_sim_m6_equity equities[3];
    size_t written = 0;
    require_ok(macro_sim_m6_equities(session, 1, equities, 3, &written));
    CHECK(written == 3);
    CHECK(equities[0].struct_size == sizeof(equities[0]));
    CHECK(equities[0].id == 2);

    size_t statement_count = 0;
    require_ok(macro_sim_m6_firm_statement_count(session, &statement_count));
    CHECK(statement_count >= 6);
    macro_sim_m6_firm_statement statements[2];
    require_ok(macro_sim_m6_firm_statements(session, 0, statements, 2, &written));
    CHECK(written == 2);
    CHECK(statements[0].firm_id == 1);

    uint8_t before[32];
    require_ok(macro_sim_m6_state_digest(session, before, sizeof(before)));
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    require_ok(macro_sim_m6_checkpoint_save(session, &checkpoint));
    CHECK(checkpoint.size > 32);

    macro_sim_session *resumed = NULL;
    require_ok(macro_sim_session_create(NULL, &resumed));
    require_ok(macro_sim_m6_checkpoint_load(resumed, checkpoint.data, checkpoint.size));
    uint8_t after[32];
    require_ok(macro_sim_m6_state_digest(resumed, after, sizeof(after)));
    CHECK(memcmp(before, after, sizeof(before)) == 0);

    require_ok(macro_sim_owned_buffer_release(&checkpoint));
    require_ok(macro_sim_session_destroy(&resumed));
    require_ok(macro_sim_session_destroy(&session));
    return 0;
}
