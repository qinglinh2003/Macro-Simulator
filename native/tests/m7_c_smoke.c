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

static void require_ok(macro_sim_status status) {
    CHECK(status.code == MACRO_SIM_OK);
}

int main(void) {
    CHECK(
        (macro_sim_capabilities() &
         MACRO_SIM_CAPABILITY_M7_POPULATION) != 0
    );
    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        77,
    };
    macro_sim_session *session = NULL;
    require_ok(macro_sim_session_create(&create, &session));

    macro_sim_m7_genesis_options genesis;
    memset(&genesis, 0, sizeof(genesis));
    genesis.struct_size = sizeof(genesis);
    genesis.start_calendar_day = 29;
    genesis.initial_persons = 96;
    genesis.target_household_size = 2.4;
    genesis.financial.struct_size = sizeof(genesis.financial);
    genesis.financial.matching_protocol =
        MACRO_SIM_M4_MATCH_PRICE_SORTED;
    genesis.financial.economy_id = 1;
    genesis.financial.currency_id = 1;
    genesis.financial.bonds = 1;
    genesis.financial.firm_equity = 1;
    genesis.financial.margin_credit = 1;
    genesis.financial.consumption_firms = 6;
    genesis.financial.capital_firms = 2;
    genesis.financial.banks = 3;
    genesis.financial.seed = 77;
    genesis.financial.watchlist_size = 3;
    genesis.financial.opening_capital_per_bank = 30.0;
    genesis.financial.initial_policy_rate = 0.002;
    require_ok(macro_sim_m7_genesis(session, &genesis));

    macro_sim_m7_policy policy;
    require_ok(macro_sim_m7_policy_defaults(&policy));
    policy.inheritance_tax_rate = 0.15;
    require_ok(macro_sim_m7_update_policy(session, &policy));

    macro_sim_m7_rules rules;
    require_ok(macro_sim_m7_rules_defaults(&rules));
    rules.fertility = 0;
    rules.mortality = 0;
    rules.annual_churn = 0.0;
    rules.annual_marriage_rate = 1.0;
    require_ok(macro_sim_m7_update_rules(session, &rules));

    macro_sim_m7_advance_result result;
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    result.metrics.struct_size = sizeof(result.metrics);
    result.metrics.economy.struct_size =
        sizeof(result.metrics.economy);
    result.metrics.economy.economy.struct_size =
        sizeof(result.metrics.economy.economy);
    result.metrics.economy.economy.economy.struct_size =
        sizeof(result.metrics.economy.economy.economy);
    require_ok(macro_sim_m7_advance(session, 12, &result));
    CHECK(result.advanced_ticks == 12);
    CHECK(result.next_tick == 12);
    CHECK(result.metrics.population == 96);
    CHECK(result.metrics.labor_supply > 0.0);
    CHECK(result.metrics.employed_heads > 0.0);

    size_t person_count = 0;
    require_ok(macro_sim_m7_person_count(session, &person_count));
    CHECK(person_count == 96);
    macro_sim_m7_person persons[3];
    size_t written = 0;
    require_ok(macro_sim_m7_persons(
        session, 2, persons, 3, &written
    ));
    CHECK(written == 3);
    CHECK(persons[0].struct_size == sizeof(persons[0]));
    CHECK(persons[0].id == 3);

    size_t membership_count = 0;
    require_ok(
        macro_sim_m7_membership_count(session, &membership_count)
    );
    CHECK(membership_count == person_count);
    macro_sim_m7_membership memberships[2];
    require_ok(macro_sim_m7_memberships(
        session, 0, memberships, 2, &written
    ));
    CHECK(written == 2);
    CHECK(memberships[0].person_id == 1);
    CHECK(memberships[0].household_id != 0);

    size_t job_count = 0;
    require_ok(macro_sim_m7_job_count(session, &job_count));
    CHECK(job_count > 0);
    macro_sim_m7_job jobs[2];
    require_ok(macro_sim_m7_jobs(
        session, 0, jobs, 2, &written
    ));
    CHECK(written == 2);
    CHECK(jobs[0].struct_size == sizeof(jobs[0]));
    CHECK(jobs[0].person_id != 0);
    CHECK(jobs[0].firm_id != 0);

    size_t union_count = 0;
    size_t estate_count = 0;
    require_ok(macro_sim_m7_union_count(session, &union_count));
    require_ok(macro_sim_m7_estate_count(session, &estate_count));
    macro_sim_m7_union union_rows[1];
    macro_sim_m7_estate estate_rows[1];
    require_ok(macro_sim_m7_unions(
        session, union_count, union_rows, 1, &written
    ));
    CHECK(written == 0);
    require_ok(macro_sim_m7_estates(
        session, estate_count, estate_rows, 1, &written
    ));
    CHECK(written == 0);

    uint8_t before[32];
    require_ok(macro_sim_m7_state_digest(
        session, before, sizeof(before)
    ));
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    require_ok(macro_sim_m7_checkpoint_save(session, &checkpoint));
    CHECK(checkpoint.size > 32);

    macro_sim_session *resumed = NULL;
    require_ok(macro_sim_session_create(NULL, &resumed));
    require_ok(macro_sim_m7_checkpoint_load(
        resumed, checkpoint.data, checkpoint.size
    ));
    uint8_t after[32];
    require_ok(macro_sim_m7_state_digest(
        resumed, after, sizeof(after)
    ));
    CHECK(memcmp(before, after, sizeof(before)) == 0);

    require_ok(macro_sim_owned_buffer_release(&checkpoint));
    require_ok(macro_sim_session_destroy(&resumed));
    require_ok(macro_sim_session_destroy(&session));
    return 0;
}
