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

static void require_ok(macro_sim_status value) { CHECK(value.code == MACRO_SIM_OK); }

static void initialize_result(macro_sim_m8_advance_result *result) {
    memset(result, 0, sizeof(*result));
    result->struct_size = sizeof(*result);
    result->metrics.struct_size = sizeof(result->metrics);
    result->metrics.economy.struct_size = sizeof(result->metrics.economy);
    result->metrics.economy.economy.struct_size =
        sizeof(result->metrics.economy.economy);
    result->metrics.economy.economy.economy.struct_size =
        sizeof(result->metrics.economy.economy.economy);
    result->metrics.economy.economy.economy.economy.struct_size =
        sizeof(result->metrics.economy.economy.economy.economy);
    result->metrics.energy.struct_size = sizeof(result->metrics.energy);
    result->metrics.housing.struct_size = sizeof(result->metrics.housing);
}

int main(void) {
    CHECK((macro_sim_capabilities() & MACRO_SIM_CAPABILITY_M8_ENERGY_HOUSING) != 0);
    macro_sim_m8_genesis_options genesis;
    require_ok(macro_sim_m8_defaults(&genesis));
    genesis.domestic_economy.initial_persons = 64;
    genesis.domestic_economy.target_household_size = 2.0;
    genesis.domestic_economy.financial.consumption_firms = 4;
    genesis.domestic_economy.financial.capital_firms = 2;
    genesis.domestic_economy.financial.banks = 2;
    genesis.domestic_economy.financial.seed = 808;
    genesis.energy_rules.producer_count = 2;
    genesis.housing_rules.enabled = 1;
    genesis.housing_rules.resale_market = 1;
    genesis.housing_rules.rentals = 1;
    genesis.housing_rules.initial_homeownership_share = 0.75;
    genesis.housing_rules.market_interval_days = 1;

    macro_sim_create_options create = {
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        808,
    };
    macro_sim_session *session = NULL;
    require_ok(macro_sim_session_create(&create, &session));
    require_ok(macro_sim_m8_genesis(session, &genesis));

    genesis.energy_policy.excise_rate = 0.05;
    require_ok(macro_sim_m8_update_energy_policy(session, &genesis.energy_policy));
    genesis.housing_policy.property_tax_rate = 0.001;
    require_ok(macro_sim_m8_update_housing_policy(session, &genesis.housing_policy));
    genesis.energy_input.supply_multiplier = 0.9;
    require_ok(macro_sim_m8_update_energy_input(session, &genesis.energy_input));
    genesis.housing_input.buyer_demand_multiplier = 1.1;
    require_ok(macro_sim_m8_update_housing_input(session, &genesis.housing_input));

    macro_sim_m8_advance_result result;
    initialize_result(&result);
    require_ok(macro_sim_m8_advance(session, 3, &result));
    CHECK(result.advanced_ticks == 3);
    CHECK(result.next_tick == 3);
    CHECK(result.metrics.economy.population == 64);
    CHECK(result.metrics.energy.capacity > 0.0);
    CHECK(result.metrics.housing.housing_stock > 0.0);

    size_t dwelling_count = 0;
    size_t producer_count = 0;
    size_t written = 0;
    require_ok(macro_sim_m8_dwelling_count(session, &dwelling_count));
    require_ok(macro_sim_m8_energy_producer_count(session, &producer_count));
    CHECK(dwelling_count > 0);
    CHECK(producer_count >= 2);
    macro_sim_m8_dwelling dwellings[2];
    macro_sim_m8_energy_producer producers[2];
    require_ok(macro_sim_m8_dwellings(session, 0, dwellings, 2, &written));
    CHECK(written == 2);
    CHECK(dwellings[0].id == 1);
    require_ok(macro_sim_m8_energy_producers(session, 0, producers, 2, &written));
    CHECK(written == 2);
    CHECK(producers[0].firm_id != 0);

    size_t listing_count = 0;
    size_t mortgage_count = 0;
    size_t tenancy_count = 0;
    size_t builder_count = 0;
    require_ok(macro_sim_m8_listing_count(session, &listing_count));
    require_ok(macro_sim_m8_mortgage_count(session, &mortgage_count));
    require_ok(macro_sim_m8_tenancy_count(session, &tenancy_count));
    require_ok(macro_sim_m8_builder_count(session, &builder_count));
    macro_sim_m8_listing listings[1];
    macro_sim_m8_mortgage mortgages[1];
    macro_sim_m8_tenancy tenancies[1];
    macro_sim_m8_builder builders[1];
    require_ok(macro_sim_m8_listings(session, listing_count, listings, 1, &written));
    CHECK(written == 0);
    require_ok(macro_sim_m8_mortgages(session, mortgage_count, mortgages, 1, &written));
    CHECK(written == 0);
    require_ok(macro_sim_m8_tenancies(session, tenancy_count, tenancies, 1, &written));
    CHECK(written == 0);
    require_ok(macro_sim_m8_builders(session, builder_count, builders, 1, &written));
    CHECK(written == 0);

    uint8_t before[32];
    require_ok(macro_sim_m8_state_digest(session, before, sizeof(before)));
    macro_sim_owned_buffer checkpoint = {NULL, 0};
    require_ok(macro_sim_m8_checkpoint_save(session, &checkpoint));
    CHECK(checkpoint.size > 32);
    macro_sim_session *resumed = NULL;
    require_ok(macro_sim_session_create(NULL, &resumed));
    require_ok(macro_sim_m8_checkpoint_load(resumed, checkpoint.data, checkpoint.size));
    uint8_t after[32];
    require_ok(macro_sim_m8_state_digest(resumed, after, sizeof(after)));
    CHECK(memcmp(before, after, sizeof(before)) == 0);

    require_ok(macro_sim_owned_buffer_release(&checkpoint));
    require_ok(macro_sim_session_destroy(&resumed));
    require_ok(macro_sim_session_destroy(&session));
    return 0;
}
