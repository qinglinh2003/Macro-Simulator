#include <stddef.h>
#include <stdint.h>

#include "macro_sim/c_api.h"

#define CHECK(expression)                                                              \
    do {                                                                               \
        if (!(expression)) {                                                           \
            return __LINE__;                                                           \
        }                                                                              \
    } while (0)

int main(void) {
    CHECK((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M9_WORLD) != 0U);

    macro_sim_m8_genesis_options economies[2];
    CHECK(macro_sim_m8_defaults(&economies[0]).code == MACRO_SIM_OK);
    CHECK(macro_sim_m8_defaults(&economies[1]).code == MACRO_SIM_OK);
    economies[0].domestic_economy.financial.seed = 901U;
    economies[1].domestic_economy.financial.seed = 902U;
    economies[0].domestic_economy.financial.consumption_firms = 4U;
    economies[1].domestic_economy.financial.consumption_firms = 4U;

    macro_sim_m9_world_rules rules;
    CHECK(macro_sim_m9_world_rules_defaults(&rules).code == MACRO_SIM_OK);
    rules.trade = 1U;
    rules.fx_trade_cap = 0.5;

    macro_sim_m9_external_policy policies[2];
    CHECK(macro_sim_m9_external_policy_defaults(&policies[0]).code == MACRO_SIM_OK);
    CHECK(macro_sim_m9_external_policy_defaults(&policies[1]).code == MACRO_SIM_OK);
    policies[0].tariff = 0.1;

    macro_sim_m9_genesis_options genesis = {0};
    genesis.struct_size = sizeof(genesis);
    genesis.economies = economies;
    genesis.economy_count = 2U;
    genesis.external_policies = policies;
    genesis.external_policy_count = 2U;
    genesis.rules = rules;

    macro_sim_m9_world *world = NULL;
    CHECK(macro_sim_m9_world_create(&genesis, &world).code == MACRO_SIM_OK);
    CHECK(world != NULL);

    uint64_t tick = UINT64_MAX;
    CHECK(macro_sim_m9_world_tick(world, &tick).code == MACRO_SIM_OK);
    CHECK(tick == 0U);

    macro_sim_m9_advance_result advanced = {0};
    advanced.struct_size = sizeof(advanced);
    CHECK(macro_sim_m9_world_advance(world, 1U, &advanced).code == MACRO_SIM_OK);
    CHECK(advanced.first_tick == 0U);
    CHECK(advanced.next_tick == 1U);
    CHECK(advanced.advanced_ticks == 1U);
    CHECK(macro_sim_m9_world_advance(world, 1U, &advanced).code == MACRO_SIM_OK);
    CHECK(advanced.first_tick == 1U);
    CHECK(advanced.next_tick == 2U);

    double rates[2] = {0.0, 0.0};
    size_t written = 0U;
    CHECK(macro_sim_m9_world_rates(world, 0U, rates, 2U, &written).code ==
          MACRO_SIM_OK);
    CHECK(written == 2U);
    CHECK(rates[0] > 0.0);
    CHECK(rates[1] > 0.0);

    macro_sim_m9_country_metrics metrics[2] = {{0}};
    CHECK(macro_sim_m9_world_country_metrics(world, 0U, metrics, 2U, &written).code ==
          MACRO_SIM_OK);
    CHECK(written == 2U);
    CHECK(metrics[0].struct_size == sizeof(metrics[0]));
    CHECK(metrics[0].economy_id == 0U);
    CHECK(metrics[1].economy_id == 1U);

    macro_sim_m9_shock shock = {0};
    shock.struct_size = sizeof(shock);
    shock.kind = MACRO_SIM_M9_SHOCK_HOUSEHOLD_DEMAND;
    shock.shape = MACRO_SIM_M9_SHOCK_STEP;
    shock.has_economy = 1U;
    shock.id = 71U;
    shock.economy_id = 0U;
    shock.start_tick = 2U;
    shock.duration = 1U;
    shock.magnitude = 0.25;
    CHECK(macro_sim_m9_world_schedule_shock(world, &shock).code == MACRO_SIM_OK);
    CHECK(macro_sim_m9_world_advance(world, 1U, &advanced).code == MACRO_SIM_OK);
    size_t event_count = 0U;
    CHECK(macro_sim_m9_world_shock_event_count(world, &event_count).code ==
          MACRO_SIM_OK);
    CHECK(event_count == 2U);
    macro_sim_m9_shock_event events[2] = {{0}};
    CHECK(macro_sim_m9_world_shock_events(world, 0U, events, 2U, &written).code ==
          MACRO_SIM_OK);
    CHECK(written == 2U);
    CHECK(events[0].type == MACRO_SIM_M9_SHOCK_ANNOUNCED);
    CHECK(events[1].type == MACRO_SIM_M9_SHOCK_STARTED);

    macro_sim_owned_buffer checkpoint = {0};
    CHECK(macro_sim_m9_world_checkpoint_save(world, &checkpoint).code == MACRO_SIM_OK);
    CHECK(checkpoint.data != NULL);
    CHECK(checkpoint.size > 0U);
    CHECK(macro_sim_m9_world_advance(world, 1U, &advanced).code == MACRO_SIM_OK);
    CHECK(macro_sim_m9_world_checkpoint_load(world, checkpoint.data, checkpoint.size)
              .code == MACRO_SIM_OK);
    CHECK(macro_sim_m9_world_tick(world, &tick).code == MACRO_SIM_OK);
    CHECK(tick == 3U);
    CHECK(macro_sim_owned_buffer_release(&checkpoint).code == MACRO_SIM_OK);

    CHECK(macro_sim_m9_world_destroy(&world).code == MACRO_SIM_OK);
    CHECK(world == NULL);
    CHECK(macro_sim_m9_world_destroy(&world).code == MACRO_SIM_OK);
    return 0;
}
