#include "macro_sim/c_api.h"

#include <algorithm>
#include <cstring>
#include <new>
#include <string_view>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/version.hpp"

struct macro_sim_session {
    explicit macro_sim_session(std::uint64_t session_id)
        : engine(macro_sim::EngineSessionOptions{macro_sim::SessionId(session_id)}) {}

    macro_sim::EngineSession engine;
};

namespace {

macro_sim_status status(macro_sim_error_code code, const char *message) noexcept {
    return {code, message};
}

macro_sim_error_code normalize_error(macro_sim::ErrorCode code) noexcept {
    switch (code) {
    case macro_sim::ErrorCode::ok:
    case macro_sim::ErrorCode::invalid_argument:
    case macro_sim::ErrorCode::out_of_range:
    case macro_sim::ErrorCode::allocation_failure:
    case macro_sim::ErrorCode::invalid_handle:
    case macro_sim::ErrorCode::incompatible_abi:
    case macro_sim::ErrorCode::contract_violation:
    case macro_sim::ErrorCode::corrupt_input:
    case macro_sim::ErrorCode::unsupported:
    case macro_sim::ErrorCode::internal_error:
        return static_cast<macro_sim_error_code>(code);
    case macro_sim::ErrorCode::not_found:
    case macro_sim::ErrorCode::invalid_transaction_state:
    case macro_sim::ErrorCode::stale_handle:
        return MACRO_SIM_INVALID_HANDLE;
    case macro_sim::ErrorCode::already_exists:
    case macro_sim::ErrorCode::insufficient_funds:
    case macro_sim::ErrorCode::unbalanced_transaction:
    case macro_sim::ErrorCode::invariant_violation:
        return MACRO_SIM_CONTRACT_VIOLATION;
    }
    return MACRO_SIM_INTERNAL_ERROR;
}

macro_sim_status status(const macro_sim::Status &source) noexcept {
    return {
        normalize_error(source.code()),
        source.message().empty() ? "" : source.message().data(),
    };
}

void fill_m4_metrics(macro_sim_m4_metrics &output,
                     const macro_sim::simulation::M4Metrics &metrics) noexcept {
    output.reserved = 0;
    output.tick = metrics.tick.value();
    output.real_output = metrics.real_output;
    output.nominal_output = metrics.nominal_output;
    output.price_index = metrics.price_index;
    output.unemployment_rate = metrics.unemployment_rate;
    output.total_money = metrics.total_money;
    output.conservation_drift = metrics.conservation_drift;
    output.aggregate_capital = metrics.aggregate_capital;
    output.household_consumption = metrics.household_consumption;
    output.wages_paid = metrics.wages_paid;
    output.firm_profit = metrics.firm_profit;
    output.tax_total = metrics.tax_total;
    output.government_spending = metrics.government_spending;
    output.government_deficit = metrics.government_deficit;
    output.public_capital = metrics.public_capital;
}

void fill_m5_metrics(macro_sim_m5_metrics &output,
                     const macro_sim::simulation::M5Metrics &metrics) noexcept {
    output.reserved = 0;
    fill_m4_metrics(output.economy, metrics.economy);
    output.policy_rate = metrics.policy_rate;
    output.inflation_sensor = metrics.inflation_sensor;
    output.new_credit = metrics.new_credit;
    output.principal_repaid = metrics.principal_repaid;
    output.loan_interest_paid = metrics.loan_interest_paid;
    output.household_interest_paid = metrics.household_interest_paid;
    output.deposit_interest_paid = metrics.deposit_interest_paid;
    output.total_loan_principal = metrics.total_loan_principal;
    output.total_bank_capital = metrics.total_bank_capital;
    output.total_reserves = metrics.total_reserves;
    output.reserve_stock = metrics.reserve_stock;
    output.omo_flow = metrics.omo_flow;
    output.lolr_advances = metrics.lolr_advances;
    output.interbank_volume = metrics.interbank_volume;
    output.interbank_rate = metrics.interbank_rate;
    output.run_flight_volume = metrics.run_flight_volume;
    output.resolution_cost = metrics.resolution_cost;
    output.realized_credit_losses = metrics.realized_credit_losses;
    output.alive_banks = metrics.alive_banks;
    output.bank_failures = metrics.bank_failures;
}

bool valid_flag(std::uint32_t value) noexcept { return value <= 1; }

} // namespace

uint32_t macro_sim_abi_version(void) { return macro_sim::abi_version(); }

uint64_t macro_sim_capabilities(void) {
    return MACRO_SIM_CAPABILITY_M2_ACCOUNTING | MACRO_SIM_CAPABILITY_M3_ALGORITHMS |
           MACRO_SIM_CAPABILITY_M4_TICK | MACRO_SIM_CAPABILITY_M5_MONETARY |
           MACRO_SIM_CAPABILITY_M6_SECURITIES;
}

const char *macro_sim_engine_version(void) { return macro_sim::kEngineVersion.data(); }

const char *macro_sim_error_code_name(macro_sim_error_code code) {
    return macro_sim::error_code_name(static_cast<macro_sim::ErrorCode>(code)).data();
}

macro_sim_status macro_sim_session_create(const macro_sim_create_options *options,
                                          macro_sim_session **output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "output must not be null");
    }
    *output = nullptr;
    std::uint64_t session_id = 1;
    if (options != nullptr) {
        if (options->struct_size != sizeof(macro_sim_create_options)) {
            return status(MACRO_SIM_INVALID_ARGUMENT, "create options size mismatch");
        }
        if (options->abi_version != MACRO_SIM_ABI_VERSION) {
            return status(MACRO_SIM_INCOMPATIBLE_ABI, "ABI version mismatch");
        }
        if (options->session_id == UINT64_MAX) {
            return status(MACRO_SIM_INVALID_ARGUMENT, "session ID is invalid");
        }
        session_id = options->session_id;
    }
    try {
        *output = new macro_sim_session(session_id);
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "session allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "session creation failed");
    }
}

macro_sim_status macro_sim_session_destroy(macro_sim_session **session) {
    if (session == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session pointer must not be null");
    }
    if (*session == nullptr) {
        return status(MACRO_SIM_INVALID_HANDLE, "session is already null");
    }
    delete *session;
    *session = nullptr;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_session_id(const macro_sim_session *session,
                                      uint64_t *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.id().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_session_tick(const macro_sim_session *session,
                                        uint64_t *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.tick().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_validate_scalar(const char *contract_id,
                                           size_t contract_id_size,
                                           const macro_sim_scalar *value,
                                           macro_sim_validation_code *output) {
    if (contract_id == nullptr || value == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "contract ID, scalar, and output are required");
    }
    macro_sim::generated::ScalarValue native_value{};
    switch (value->kind) {
    case MACRO_SIM_SCALAR_NULL:
        native_value.kind = macro_sim::generated::InputKind::null_value;
        break;
    case MACRO_SIM_SCALAR_BOOLEAN:
        native_value.kind = macro_sim::generated::InputKind::boolean;
        native_value.number = value->integer_value == 0 ? 0.0 : 1.0;
        break;
    case MACRO_SIM_SCALAR_INTEGER:
        native_value.kind = macro_sim::generated::InputKind::integer;
        native_value.number = static_cast<double>(value->integer_value);
        break;
    case MACRO_SIM_SCALAR_NUMBER:
        native_value.kind = macro_sim::generated::InputKind::number;
        native_value.number = value->number_value;
        break;
    case MACRO_SIM_SCALAR_STRING:
        if (value->string_value == nullptr && value->string_size != 0) {
            return status(MACRO_SIM_INVALID_ARGUMENT,
                          "nonempty string scalar has a null pointer");
        }
        native_value.kind = macro_sim::generated::InputKind::string;
        native_value.text =
            std::string_view(value->string_value == nullptr ? "" : value->string_value,
                             value->string_size);
        break;
    case MACRO_SIM_SCALAR_ID_SET:
        native_value.kind = macro_sim::generated::InputKind::id_set;
        break;
    default:
        return status(MACRO_SIM_INVALID_ARGUMENT, "unknown scalar kind");
    }
    const auto code = macro_sim::generated::validate_scalar(
        std::string_view(contract_id, contract_id_size), native_value);
    *output = static_cast<macro_sim_validation_code>(code);
    return status(MACRO_SIM_OK, "");
}

const char *macro_sim_validation_code_name(macro_sim_validation_code code) {
    return macro_sim::generated::validation_code_name(
               static_cast<macro_sim::generated::ValidationCode>(code))
        .data();
}

macro_sim_status macro_sim_m2_genesis(macro_sim_session *session,
                                      const macro_sim_m2_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m2_genesis_options) ||
        options->vertical > MACRO_SIM_M2_M4_V1_CAPITAL_FISCAL ||
        options->government > 1) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "genesis options are invalid");
    }
    macro_sim::core::GenesisSpec spec;
    spec.vertical = static_cast<macro_sim::core::GenesisVertical>(options->vertical);
    spec.economy = macro_sim::EconomyId(options->economy_id);
    spec.currency = macro_sim::CurrencyId(options->currency_id);
    spec.households = options->households;
    spec.consumption_firms = options->consumption_firms;
    spec.capital_firms = options->capital_firms;
    spec.settlement_banks = options->settlement_banks;
    spec.government = options->government != 0;
    spec.aggregate_opening_money = macro_sim::Money(options->aggregate_opening_money);
    spec.aggregate_opening_capital =
        macro_sim::Capital(options->aggregate_opening_capital);
    spec.seed = options->seed;
    return status(session->engine.initialize(spec));
}

macro_sim_status macro_sim_m2_apply_batch(macro_sim_session *session,
                                          const macro_sim_m2_command *commands,
                                          size_t command_count,
                                          macro_sim_m2_receipt *output) {
    if (session == nullptr || output == nullptr ||
        (commands == nullptr && command_count != 0)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session, commands, and receipt are invalid");
    }
    if (output->struct_size != sizeof(macro_sim_m2_receipt)) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "receipt structure size mismatch");
    }
    if (command_count > 1'000'000) {
        return status(MACRO_SIM_OUT_OF_RANGE, "command count limit is exceeded");
    }
    macro_sim::core::SettlementBatch batch;
    try {
        for (std::size_t index = 0; index < command_count; ++index) {
            const auto &command = commands[index];
            if (command.struct_size != sizeof(macro_sim_m2_command) ||
                command.reserved != 0) {
                return status(MACRO_SIM_INVALID_ARGUMENT,
                              "command structure is invalid");
            }
            if (command.owner_kind > MACRO_SIM_M2_OWNER_INSTITUTION) {
                return status(MACRO_SIM_INVALID_ARGUMENT,
                              "command owner kind is invalid");
            }
            const macro_sim::core::OwnerId owner{
                static_cast<macro_sim::core::OwnerKind>(command.owner_kind),
                command.tertiary_id,
            };
            switch (command.kind) {
            case MACRO_SIM_M2_TRANSFER:
                batch.transfers.push_back({
                    macro_sim::AccountId(command.primary_id),
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_RESERVE_TRANSFER:
                batch.reserve_transfers.push_back({
                    macro_sim::SettlementNodeId(command.primary_id),
                    macro_sim::SettlementNodeId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_RESERVE_ISSUE:
                batch.reserve_issues.push_back({
                    macro_sim::SettlementNodeId(command.primary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_LOAN_ORIGINATION:
                batch.originations.push_back({
                    macro_sim::BankId(command.primary_id),
                    owner,
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                    {
                        macro_sim::Rate(command.rate),
                        macro_sim::Tick(command.tick_a),
                        macro_sim::Tick(command.tick_b),
                    },
                });
                break;
            case MACRO_SIM_M2_LOAN_REPAYMENT:
                batch.repayments.push_back({
                    macro_sim::LoanId(command.primary_id),
                    macro_sim::AccountId(command.secondary_id),
                    macro_sim::Money(command.amount),
                });
                break;
            case MACRO_SIM_M2_OWNERSHIP_MUTATION:
                batch.ownership_mutations.push_back({
                    macro_sim::OwnershipLotId(command.primary_id),
                    owner,
                    command.amount,
                });
                break;
            case MACRO_SIM_M2_COUNTER_INCREMENT:
                batch.counter_increments.push_back(
                    {command.primary_id, command.secondary_id});
                break;
            default:
                return status(MACRO_SIM_INVALID_ARGUMENT, "command kind is invalid");
            }
        }
        auto receipt = session->engine.apply(batch);
        if (!receipt.ok()) {
            return status(receipt.status());
        }
        output->reserved = 0;
        output->applied_mutations = receipt.get_if()->applied_mutations;
        output->created_loan_count = receipt.get_if()->created_loans.size();
        std::copy(receipt.get_if()->before.bytes.begin(),
                  receipt.get_if()->before.bytes.end(), output->before_digest);
        std::copy(receipt.get_if()->after.bytes.begin(),
                  receipt.get_if()->after.bytes.end(), output->after_digest);
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc &) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "batch allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "batch conversion failed");
    }
}

macro_sim_status macro_sim_m2_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    if (session == nullptr || output == nullptr || output_size != 32) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and 32-byte digest output are required");
    }
    const auto digest = session->engine.digest();
    if (!digest.ok()) {
        return status(digest.status());
    }
    std::copy(digest.get_if()->bytes.begin(), digest.get_if()->bytes.end(), output);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and checkpoint output are required");
    }
    output->data = nullptr;
    output->size = 0;
    const auto checkpoint = session->engine.checkpoint();
    if (!checkpoint.ok()) {
        return status(checkpoint.status());
    }
    const auto size = checkpoint.get_if()->size();
    auto *bytes = new (std::nothrow) std::uint8_t[size];
    if (bytes == nullptr && size != 0) {
        return status(MACRO_SIM_ALLOCATION_FAILURE,
                      "checkpoint output allocation failed");
    }
    std::memcpy(bytes, checkpoint.get_if()->data(), size);
    output->data = bytes;
    output->size = size;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    if (session == nullptr || (checkpoint == nullptr && checkpoint_size != 0)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and checkpoint input are invalid");
    }
    return status(session->engine.restore_checkpoint(
        std::span<const std::uint8_t>(checkpoint, checkpoint_size)));
}

macro_sim_status macro_sim_m4_genesis(macro_sim_session *session,
                                      const macro_sim_m4_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M4 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m4_genesis_options) ||
        options->vertical > MACRO_SIM_M4_CAPITAL_FISCAL ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        options->stochastic > 1 || options->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M4 genesis options are invalid");
    }
    macro_sim::simulation::M4SimulationSpec spec;
    spec.vertical = static_cast<macro_sim::simulation::M4Vertical>(options->vertical);
    spec.economy = macro_sim::EconomyId(options->economy_id);
    spec.currency = macro_sim::CurrencyId(options->currency_id);
    spec.market_protocol = static_cast<macro_sim::algorithms::MatchingProtocol>(
        options->matching_protocol);
    spec.stochastic = options->stochastic != 0;
    spec.households = options->households;
    spec.consumption_firms = options->consumption_firms;
    spec.capital_firms = options->capital_firms;
    spec.seed = options->seed;
    spec.requested_capabilities = options->requested_capabilities;
    return status(session->engine.initialize_simulation(spec));
}

macro_sim_status macro_sim_m4_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m4_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m4_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M4 result are required");
    }
    const auto result = session->engine.advance_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m4_metrics(output->metrics, metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m4_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m4_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m4_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m5_genesis(macro_sim_session *session,
                                      const macro_sim_m5_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M5 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m5_genesis_options) ||
        options->monetary_regime > MACRO_SIM_M5_MANUAL ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        !valid_flag(options->stochastic) ||
        !valid_flag(options->has_manual_policy_rate) ||
        !valid_flag(options->interbank) || !valid_flag(options->household_credit) ||
        !valid_flag(options->bank_runs) || options->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 genesis options are invalid");
    }
    macro_sim::simulation::M5SimulationSpec spec;
    spec.real_economy.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    spec.real_economy.economy = macro_sim::EconomyId(options->economy_id);
    spec.real_economy.currency = macro_sim::CurrencyId(options->currency_id);
    spec.real_economy.market_protocol =
        static_cast<macro_sim::algorithms::MatchingProtocol>(
            options->matching_protocol);
    spec.real_economy.stochastic = options->stochastic != 0;
    spec.real_economy.households = options->households;
    spec.real_economy.consumption_firms = options->consumption_firms;
    spec.real_economy.capital_firms = options->capital_firms;
    spec.real_economy.seed = options->seed;
    spec.real_economy.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    spec.rules.bank_count = options->banks;
    spec.rules.opening_capital_per_bank = options->opening_capital_per_bank;
    spec.rules.interbank = options->interbank != 0;
    spec.rules.household_credit = options->household_credit != 0;
    spec.rules.bank_runs = options->bank_runs != 0;
    spec.policy.monetary_regime =
        static_cast<macro_sim::simulation::MonetaryRegime>(options->monetary_regime);
    if (options->has_manual_policy_rate != 0) {
        spec.policy.manual_policy_rate = options->manual_policy_rate;
    }
    spec.initial_policy_rate = options->initial_policy_rate;
    return status(session->engine.initialize_m5(spec));
}

macro_sim_status macro_sim_m5_update_policy(macro_sim_session *session,
                                            const macro_sim_m5_policy *policy) {
    if (session == nullptr || policy == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and M5 policy are required");
    }
    if (policy->struct_size != sizeof(macro_sim_m5_policy) ||
        policy->monetary_regime > MACRO_SIM_M5_MANUAL ||
        !valid_flag(policy->has_manual_policy_rate) ||
        !valid_flag(policy->open_market_operations) ||
        !valid_flag(policy->reserve_target_indexes_deposits) ||
        !valid_flag(policy->lender_of_last_resort) ||
        !valid_flag(policy->bank_capital_constraint) ||
        !valid_flag(policy->unified_bank_rwa) ||
        !valid_flag(policy->migrate_relationships_on_failure) ||
        !valid_flag(policy->state_resolution_backstop) ||
        !valid_flag(policy->job_guarantee) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 policy structure is invalid");
    }
    macro_sim::simulation::M5PolicyState value;
    value.government_consumption_share = policy->government_consumption_share;
    value.government_deficit_target = policy->government_deficit_target;
    value.deficit_unemployment_reference = policy->deficit_unemployment_reference;
    value.deficit_unemployment_cap = policy->deficit_unemployment_cap;
    value.government_investment_share = policy->government_investment_share;
    value.profit_tax_rate = policy->profit_tax_rate;
    value.income_tax_rate = policy->income_tax_rate;
    value.income_allowance = policy->income_allowance;
    value.consumption_tax_rate = policy->consumption_tax_rate;
    value.wealth_tax_rate = policy->wealth_tax_rate;
    value.wealth_allowance = policy->wealth_allowance;
    value.unemployment_benefit_replacement = policy->unemployment_benefit_replacement;
    value.benefit_income_floor = policy->benefit_income_floor;
    value.minimum_wage = policy->minimum_wage;
    value.job_guarantee = policy->job_guarantee != 0;
    value.job_guarantee_wage_ratio = policy->job_guarantee_wage_ratio;
    value.job_guarantee_public_works_share = policy->job_guarantee_public_works_share;
    value.monetary_regime =
        static_cast<macro_sim::simulation::MonetaryRegime>(policy->monetary_regime);
    value.inflation_target = policy->inflation_target;
    value.taylor_inflation = policy->taylor_inflation;
    value.taylor_unemployment = policy->taylor_unemployment;
    value.rate_inertia = policy->rate_inertia;
    if (policy->has_manual_policy_rate != 0) {
        value.manual_policy_rate = policy->manual_policy_rate;
    }
    value.neutral_rate = policy->neutral_rate;
    value.natural_unemployment = policy->natural_unemployment;
    value.maximum_policy_rate = policy->maximum_policy_rate;
    value.inflation_sensor_lambda = policy->inflation_sensor_lambda;
    value.open_market_operations = policy->open_market_operations != 0;
    value.reserve_target = policy->reserve_target;
    value.reserve_gap_close = policy->reserve_gap_close;
    value.reserve_target_indexes_deposits =
        policy->reserve_target_indexes_deposits != 0;
    value.lender_of_last_resort = policy->lender_of_last_resort != 0;
    value.reserve_floor_fraction = policy->reserve_floor_fraction;
    value.firm_leverage_limit = policy->firm_leverage_limit;
    value.firm_minimum_dscr = policy->firm_minimum_dscr;
    value.household_credit_limit = policy->household_credit_limit;
    value.bank_capital_constraint = policy->bank_capital_constraint != 0;
    value.unified_bank_rwa = policy->unified_bank_rwa != 0;
    value.bank_leverage_cap = policy->bank_leverage_cap;
    value.bank_exposure_limit = policy->bank_exposure_limit;
    value.bank_target_capital_ratio = policy->bank_target_capital_ratio;
    value.deposit_rate_floor = policy->deposit_rate_floor;
    value.migrate_relationships_on_failure =
        policy->migrate_relationships_on_failure != 0;
    value.state_resolution_backstop = policy->state_resolution_backstop != 0;
    return status(session->engine.update_m5_policy(value));
}

macro_sim_status macro_sim_m5_policy_defaults(macro_sim_m5_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M5 policy output is required");
    }
    const macro_sim::simulation::M5PolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->monetary_regime = static_cast<std::uint32_t>(value.monetary_regime);
    output->open_market_operations = value.open_market_operations ? 1U : 0U;
    output->reserve_target_indexes_deposits =
        value.reserve_target_indexes_deposits ? 1U : 0U;
    output->lender_of_last_resort = value.lender_of_last_resort ? 1U : 0U;
    output->bank_capital_constraint = value.bank_capital_constraint ? 1U : 0U;
    output->unified_bank_rwa = value.unified_bank_rwa ? 1U : 0U;
    output->migrate_relationships_on_failure =
        value.migrate_relationships_on_failure ? 1U : 0U;
    output->state_resolution_backstop = value.state_resolution_backstop ? 1U : 0U;
    output->job_guarantee = value.job_guarantee ? 1U : 0U;
    output->government_consumption_share = value.government_consumption_share;
    output->government_deficit_target = value.government_deficit_target;
    output->deficit_unemployment_reference = value.deficit_unemployment_reference;
    output->deficit_unemployment_cap = value.deficit_unemployment_cap;
    output->government_investment_share = value.government_investment_share;
    output->profit_tax_rate = value.profit_tax_rate;
    output->income_tax_rate = value.income_tax_rate;
    output->income_allowance = value.income_allowance;
    output->consumption_tax_rate = value.consumption_tax_rate;
    output->wealth_tax_rate = value.wealth_tax_rate;
    output->wealth_allowance = value.wealth_allowance;
    output->unemployment_benefit_replacement = value.unemployment_benefit_replacement;
    output->benefit_income_floor = value.benefit_income_floor;
    output->minimum_wage = value.minimum_wage;
    output->job_guarantee_wage_ratio = value.job_guarantee_wage_ratio;
    output->job_guarantee_public_works_share = value.job_guarantee_public_works_share;
    output->inflation_target = value.inflation_target;
    output->taylor_inflation = value.taylor_inflation;
    output->taylor_unemployment = value.taylor_unemployment;
    output->rate_inertia = value.rate_inertia;
    output->neutral_rate = value.neutral_rate;
    output->natural_unemployment = value.natural_unemployment;
    output->maximum_policy_rate = value.maximum_policy_rate;
    output->inflation_sensor_lambda = value.inflation_sensor_lambda;
    output->reserve_target = value.reserve_target;
    output->reserve_gap_close = value.reserve_gap_close;
    output->reserve_floor_fraction = value.reserve_floor_fraction;
    output->firm_leverage_limit = value.firm_leverage_limit;
    output->firm_minimum_dscr = value.firm_minimum_dscr;
    output->household_credit_limit = value.household_credit_limit;
    output->bank_leverage_cap = value.bank_leverage_cap;
    output->bank_exposure_limit = value.bank_exposure_limit;
    output->bank_target_capital_ratio = value.bank_target_capital_ratio;
    output->deposit_rate_floor = value.deposit_rate_floor;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m5_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m5_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m5_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m5_metrics) ||
        output->metrics.economy.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M5 result are required");
    }
    const auto result = session->engine.advance_m5_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    fill_m5_metrics(output->metrics, metrics);
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m5_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m5_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m5_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m6_genesis(macro_sim_session *session,
                                      const macro_sim_m6_genesis_options *options) {
    if (session == nullptr || options == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and M6 genesis options are required");
    }
    if (options->struct_size != sizeof(macro_sim_m6_genesis_options) ||
        options->matching_protocol > MACRO_SIM_M4_MATCH_PRICE_SORTED ||
        !valid_flag(options->stochastic) || !valid_flag(options->bonds) ||
        !valid_flag(options->firm_equity) || !valid_flag(options->margin_credit) ||
        !valid_flag(options->firm_dynamics) || !valid_flag(options->bank_dynamics) ||
        options->reserved != 0 || options->reserved_2 != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M6 genesis options are invalid");
    }
    macro_sim::simulation::M6SimulationSpec spec;
    auto &monetary = spec.monetary_economy;
    auto &real = monetary.real_economy;
    real.vertical = macro_sim::simulation::M4Vertical::capital_fiscal;
    real.economy = macro_sim::EconomyId(options->economy_id);
    real.currency = macro_sim::CurrencyId(options->currency_id);
    real.market_protocol = static_cast<macro_sim::algorithms::MatchingProtocol>(
        options->matching_protocol);
    real.stochastic = options->stochastic != 0;
    real.households = options->households;
    real.consumption_firms = options->consumption_firms;
    real.capital_firms = options->capital_firms;
    real.seed = options->seed;
    real.requested_capabilities =
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::physical_capital) |
        macro_sim::simulation::capability_bit(
            macro_sim::simulation::M4Capability::government);
    monetary.rules.bank_count = options->banks;
    monetary.rules.opening_capital_per_bank = options->opening_capital_per_bank;
    monetary.initial_policy_rate = options->initial_policy_rate;
    spec.rules.bonds = options->bonds != 0;
    spec.rules.firm_equity = options->firm_equity != 0;
    spec.rules.margin_credit = options->margin_credit != 0;
    spec.rules.firm_dynamics = options->firm_dynamics != 0;
    spec.rules.bank_dynamics = options->bank_dynamics != 0;
    spec.rules.watchlist_size = options->watchlist_size;
    return status(session->engine.initialize_m6(spec));
}

macro_sim_status macro_sim_m6_update_policy(macro_sim_session *session,
                                            const macro_sim_m6_policy *policy) {
    if (session == nullptr || policy == nullptr ||
        policy->struct_size != sizeof(macro_sim_m6_policy) ||
        !valid_flag(policy->household_bankruptcy) ||
        !valid_flag(policy->bank_resolution_fund) || policy->reserved != 0) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and valid M6 policy are required");
    }
    macro_sim::simulation::M6PolicyState value;
    value.bond_finance_fraction = policy->bond_finance_fraction;
    value.bond_coupon_rate = policy->bond_coupon_rate;
    value.bond_maturity_days = policy->bond_maturity_days;
    value.household_bond_target = policy->household_bond_target;
    value.bank_bond_appetite = policy->bank_bond_appetite;
    value.bank_bond_duration_limit = policy->bank_bond_duration_limit;
    value.margin_ltv = policy->margin_ltv;
    value.margin_max = policy->margin_max;
    value.household_bankruptcy = policy->household_bankruptcy != 0;
    value.bank_resolution_fund = policy->bank_resolution_fund != 0;
    value.bank_minimum_capital = policy->bank_minimum_capital;
    return status(session->engine.update_m6_policy(value));
}

macro_sim_status macro_sim_m6_policy_defaults(macro_sim_m6_policy *output) {
    if (output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "M6 policy output is required");
    }
    const macro_sim::simulation::M6PolicyState value;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->household_bankruptcy = value.household_bankruptcy ? 1U : 0U;
    output->bank_resolution_fund = value.bank_resolution_fund ? 1U : 0U;
    output->bond_maturity_days = value.bond_maturity_days;
    output->bond_finance_fraction = value.bond_finance_fraction;
    output->bond_coupon_rate = value.bond_coupon_rate;
    output->household_bond_target = value.household_bond_target;
    output->bank_bond_appetite = value.bank_bond_appetite;
    output->bank_bond_duration_limit = value.bank_bond_duration_limit;
    output->margin_ltv = value.margin_ltv;
    output->margin_max = value.margin_max;
    output->bank_minimum_capital = value.bank_minimum_capital;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_advance(macro_sim_session *session, uint64_t tick_count,
                                      macro_sim_m6_advance_result *output) {
    if (session == nullptr || output == nullptr ||
        output->struct_size != sizeof(macro_sim_m6_advance_result) ||
        output->metrics.struct_size != sizeof(macro_sim_m6_metrics) ||
        output->metrics.economy.struct_size != sizeof(macro_sim_m5_metrics) ||
        output->metrics.economy.economy.struct_size != sizeof(macro_sim_m4_metrics)) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "session and initialized M6 result are required");
    }
    const auto result = session->engine.advance_m6_ticks(tick_count);
    if (!result.ok()) {
        return status(result.status());
    }
    const auto &value = *result.get_if();
    const auto &metrics = value.metrics;
    output->reserved = 0;
    output->first_tick = value.first_tick.value();
    output->next_tick = value.next_tick.value();
    output->advanced_ticks = value.advanced_ticks;
    output->scratch_capacity_signature = value.scratch_capacity_signature;
    output->transfer_count = value.transfer_count;
    output->trade_count = value.trade_count;
    output->metrics.reserved = 0;
    fill_m5_metrics(output->metrics.economy, metrics.economy);
#define M6_METRIC(field) output->metrics.field = metrics.field
    M6_METRIC(bond_outstanding_face);
    M6_METRIC(bond_market_value);
    M6_METRIC(bond_issuance);
    M6_METRIC(bond_redemption);
    M6_METRIC(bond_coupon_paid);
    M6_METRIC(firm_equity_market_cap);
    M6_METRIC(bank_equity_market_cap);
    M6_METRIC(equity_turnover);
    M6_METRIC(primary_equity_raised);
    M6_METRIC(margin_principal);
    M6_METRIC(margin_originated);
    M6_METRIC(margin_repaid);
    M6_METRIC(margin_writeoffs);
    M6_METRIC(total_firm_book_equity);
    M6_METRIC(clearing_residual);
    M6_METRIC(sector_retool_capital);
    M6_METRIC(active_security_lots);
    M6_METRIC(household_bankruptcies);
    M6_METRIC(firm_births);
    M6_METRIC(firm_exits);
    M6_METRIC(firm_defaults);
    M6_METRIC(sector_switches);
    M6_METRIC(bank_births);
    M6_METRIC(bank_equity_resolutions);
#undef M6_METRIC
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_state_digest(const macro_sim_session *session,
                                           uint8_t *output, size_t output_size) {
    return macro_sim_m2_state_digest(session, output, output_size);
}

macro_sim_status macro_sim_m6_checkpoint_save(const macro_sim_session *session,
                                              macro_sim_owned_buffer *output) {
    return macro_sim_m2_checkpoint_save(session, output);
}

macro_sim_status macro_sim_m6_checkpoint_load(macro_sim_session *session,
                                              const uint8_t *checkpoint,
                                              size_t checkpoint_size) {
    return macro_sim_m2_checkpoint_load(session, checkpoint, checkpoint_size);
}

macro_sim_status macro_sim_m6_bond_count(const macro_sim_session *session,
                                         size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    *output = session->engine.securities_runtime()->securities.bonds().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_bonds(const macro_sim_session *session, size_t offset,
                                    macro_sim_m6_bond *output, size_t capacity,
                                    size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and bond output are required");
    }
    const auto &rows = session->engine.securities_runtime()->securities.bonds();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.issuer_kind = static_cast<std::uint32_t>(source.issuer.kind);
        target.id = source.id.value();
        target.issuer_id = source.issuer.value;
        target.issuer_account = source.issuer_account.value();
        target.currency_id = source.currency.value();
        target.active = source.active ? 1U : 0U;
        target.issued_tick = source.issued_tick.value();
        target.maturity_tick = source.maturity_tick.value();
        target.coupon_rate = source.coupon_rate.value();
        target.original_face = source.original_face.value();
        target.outstanding_face = source.outstanding_face.value();
        target.settled = source.settled ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_equity_count(const macro_sim_session *session,
                                           size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    *output = session->engine.securities_runtime()->securities.equities().size();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_equities(const macro_sim_session *session, size_t offset,
                                       macro_sim_m6_equity *output, size_t capacity,
                                       size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and equity output are required");
    }
    const auto &rows = session->engine.securities_runtime()->securities.equities();
    *written = 0;
    if (offset >= rows.size()) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, rows.size() - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index];
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.issuer_kind = static_cast<std::uint32_t>(source.issuer_kind);
        target.id = source.id.value();
        target.owner_kind = static_cast<std::uint32_t>(source.issuer.kind);
        target.currency_id = source.currency.value();
        target.issuer_id = source.issuer.value;
        target.issuer_account = source.issuer_account.value();
        target.outstanding_shares = source.outstanding_shares;
        target.price = source.price.value();
        target.last_price = source.last_price.value();
        target.peak_price = source.peak_price.value();
        target.fundamental = source.fundamental.value();
        target.trend = source.trend;
        target.income_signal = source.income_signal;
        target.active = source.active ? 1U : 0U;
        target.resolved = source.resolved ? 1U : 0U;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_firm_statement_count(const macro_sim_session *session,
                                                   size_t *output) {
    if (session == nullptr || output == nullptr ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and output are required");
    }
    const auto &rows = session->engine.securities_runtime()->firms;
    *output = rows.empty() ? 0 : rows.size() - 1;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m6_firm_statements(const macro_sim_session *session,
                                              size_t offset,
                                              macro_sim_m6_firm_statement *output,
                                              size_t capacity, size_t *written) {
    if (session == nullptr || written == nullptr ||
        (capacity != 0 && output == nullptr) ||
        session->engine.securities_runtime() == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT,
                      "active M6 session and statement output are required");
    }
    const auto &rows = session->engine.securities_runtime()->firms;
    *written = 0;
    const auto logical_size = rows.empty() ? 0 : rows.size() - 1;
    if (offset >= logical_size) {
        return status(MACRO_SIM_OK, "");
    }
    const auto count = std::min(capacity, logical_size - offset);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &source = rows[offset + index + 1];
        const auto &statement = source.statement;
        auto &target = output[index];
        std::memset(&target, 0, sizeof(target));
        target.struct_size = sizeof(target);
        target.active = source.active ? 1U : 0U;
        target.firm_id = source.firm.value();
        target.stratum = static_cast<std::uint32_t>(source.stratum);
        target.defaulted = source.defaulted ? 1U : 0U;
        target.cash = statement.cash;
        target.debt = statement.debt;
        target.interest_arrears = statement.interest_arrears;
        target.capital_units = statement.capital_units;
        target.capital_unit_price = statement.capital_unit_price;
        target.capital_value = statement.capital_value;
        target.output_inventory_units = statement.output_inventory_units;
        target.output_inventory_unit_price = statement.output_inventory_unit_price;
        target.output_inventory_value = statement.output_inventory_value;
        target.inventory_value = statement.inventory_value;
        target.gross_assets = statement.gross_assets;
        target.book_equity = statement.book_equity;
        target.eligible_collateral_value = statement.eligible_collateral_value;
        target.borrowing_base_proxy = statement.borrowing_base_proxy;
        target.borrowing_base_headroom = statement.borrowing_base_headroom;
        target.earnings = statement.earnings;
    }
    *written = count;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_owned_buffer_release(macro_sim_owned_buffer *buffer) {
    if (buffer == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "buffer is required");
    }
    delete[] buffer->data;
    buffer->data = nullptr;
    buffer->size = 0;
    return status(MACRO_SIM_OK, "");
}
