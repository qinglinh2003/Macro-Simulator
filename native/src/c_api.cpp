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

macro_sim_status status(
    macro_sim_error_code code,
    const char* message
) noexcept {
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

macro_sim_status status(const macro_sim::Status& source) noexcept {
    return {
        normalize_error(source.code()),
        source.message().empty() ? "" : source.message().data(),
    };
}

}  // namespace

uint32_t macro_sim_abi_version(void) {
    return macro_sim::abi_version();
}

uint64_t macro_sim_capabilities(void) {
    return MACRO_SIM_CAPABILITY_M2_ACCOUNTING
        | MACRO_SIM_CAPABILITY_M3_ALGORITHMS;
}

const char* macro_sim_engine_version(void) {
    return macro_sim::kEngineVersion.data();
}

const char* macro_sim_error_code_name(macro_sim_error_code code) {
    return macro_sim::error_code_name(
        static_cast<macro_sim::ErrorCode>(code)
    ).data();
}

macro_sim_status macro_sim_session_create(
    const macro_sim_create_options* options,
    macro_sim_session** output
) {
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
    } catch (const std::bad_alloc&) {
        return status(MACRO_SIM_ALLOCATION_FAILURE, "session allocation failed");
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "session creation failed");
    }
}

macro_sim_status macro_sim_session_destroy(macro_sim_session** session) {
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

macro_sim_status macro_sim_session_id(
    const macro_sim_session* session,
    uint64_t* output
) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.id().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_session_tick(
    const macro_sim_session* session,
    uint64_t* output
) {
    if (session == nullptr || output == nullptr) {
        return status(MACRO_SIM_INVALID_ARGUMENT, "session and output are required");
    }
    *output = session->engine.tick().value();
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_validate_scalar(
    const char* contract_id,
    size_t contract_id_size,
    const macro_sim_scalar* value,
    macro_sim_validation_code* output
) {
    if (contract_id == nullptr || value == nullptr || output == nullptr) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "contract ID, scalar, and output are required"
        );
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
                return status(
                    MACRO_SIM_INVALID_ARGUMENT,
                    "nonempty string scalar has a null pointer"
                );
            }
            native_value.kind = macro_sim::generated::InputKind::string;
            native_value.text = std::string_view(
                value->string_value == nullptr ? "" : value->string_value,
                value->string_size
            );
            break;
        case MACRO_SIM_SCALAR_ID_SET:
            native_value.kind = macro_sim::generated::InputKind::id_set;
            break;
        default:
            return status(MACRO_SIM_INVALID_ARGUMENT, "unknown scalar kind");
    }
    const auto code = macro_sim::generated::validate_scalar(
        std::string_view(contract_id, contract_id_size),
        native_value
    );
    *output = static_cast<macro_sim_validation_code>(code);
    return status(MACRO_SIM_OK, "");
}

const char* macro_sim_validation_code_name(macro_sim_validation_code code) {
    return macro_sim::generated::validation_code_name(
        static_cast<macro_sim::generated::ValidationCode>(code)
    ).data();
}

macro_sim_status macro_sim_m2_genesis(
    macro_sim_session* session,
    const macro_sim_m2_genesis_options* options
) {
    if (session == nullptr || options == nullptr) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "session and genesis options are required"
        );
    }
    if (options->struct_size != sizeof(macro_sim_m2_genesis_options)
        || options->vertical > MACRO_SIM_M2_M4_V1_CAPITAL_FISCAL
        || options->government > 1) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "genesis options are invalid"
        );
    }
    macro_sim::core::GenesisSpec spec;
    spec.vertical =
        static_cast<macro_sim::core::GenesisVertical>(options->vertical);
    spec.economy = macro_sim::EconomyId(options->economy_id);
    spec.currency = macro_sim::CurrencyId(options->currency_id);
    spec.households = options->households;
    spec.consumption_firms = options->consumption_firms;
    spec.capital_firms = options->capital_firms;
    spec.settlement_banks = options->settlement_banks;
    spec.government = options->government != 0;
    spec.aggregate_opening_money =
        macro_sim::Money(options->aggregate_opening_money);
    spec.aggregate_opening_capital =
        macro_sim::Capital(options->aggregate_opening_capital);
    spec.seed = options->seed;
    return status(session->engine.initialize(spec));
}

macro_sim_status macro_sim_m2_apply_batch(
    macro_sim_session* session,
    const macro_sim_m2_command* commands,
    size_t command_count,
    macro_sim_m2_receipt* output
) {
    if (session == nullptr || output == nullptr
        || (commands == nullptr && command_count != 0)) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "session, commands, and receipt are invalid"
        );
    }
    if (output->struct_size != sizeof(macro_sim_m2_receipt)) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "receipt structure size mismatch"
        );
    }
    if (command_count > 1'000'000) {
        return status(
            MACRO_SIM_OUT_OF_RANGE,
            "command count limit is exceeded"
        );
    }
    macro_sim::core::SettlementBatch batch;
    try {
        for (std::size_t index = 0; index < command_count; ++index) {
            const auto& command = commands[index];
            if (command.struct_size != sizeof(macro_sim_m2_command)
                || command.reserved != 0) {
                return status(
                    MACRO_SIM_INVALID_ARGUMENT,
                    "command structure is invalid"
                );
            }
            if (command.owner_kind > MACRO_SIM_M2_OWNER_INSTITUTION) {
                return status(
                    MACRO_SIM_INVALID_ARGUMENT,
                    "command owner kind is invalid"
                );
            }
            const macro_sim::core::OwnerId owner{
                static_cast<macro_sim::core::OwnerKind>(
                    command.owner_kind
                ),
                command.tertiary_id,
            };
            switch (command.kind) {
                case MACRO_SIM_M2_TRANSFER:
                    batch.transfers.push_back(
                        {
                            macro_sim::AccountId(command.primary_id),
                            macro_sim::AccountId(command.secondary_id),
                            macro_sim::Money(command.amount),
                        }
                    );
                    break;
                case MACRO_SIM_M2_RESERVE_TRANSFER:
                    batch.reserve_transfers.push_back(
                        {
                            macro_sim::SettlementNodeId(command.primary_id),
                            macro_sim::SettlementNodeId(
                                command.secondary_id
                            ),
                            macro_sim::Money(command.amount),
                        }
                    );
                    break;
                case MACRO_SIM_M2_RESERVE_ISSUE:
                    batch.reserve_issues.push_back(
                        {
                            macro_sim::SettlementNodeId(command.primary_id),
                            macro_sim::Money(command.amount),
                        }
                    );
                    break;
                case MACRO_SIM_M2_LOAN_ORIGINATION:
                    batch.originations.push_back(
                        {
                            macro_sim::BankId(command.primary_id),
                            owner,
                            macro_sim::AccountId(command.secondary_id),
                            macro_sim::Money(command.amount),
                            {
                                macro_sim::Rate(command.rate),
                                macro_sim::Tick(command.tick_a),
                                macro_sim::Tick(command.tick_b),
                            },
                        }
                    );
                    break;
                case MACRO_SIM_M2_LOAN_REPAYMENT:
                    batch.repayments.push_back(
                        {
                            macro_sim::LoanId(command.primary_id),
                            macro_sim::AccountId(command.secondary_id),
                            macro_sim::Money(command.amount),
                        }
                    );
                    break;
                case MACRO_SIM_M2_OWNERSHIP_MUTATION:
                    batch.ownership_mutations.push_back(
                        {
                            macro_sim::OwnershipLotId(command.primary_id),
                            owner,
                            command.amount,
                        }
                    );
                    break;
                case MACRO_SIM_M2_COUNTER_INCREMENT:
                    batch.counter_increments.push_back(
                        {command.primary_id, command.secondary_id}
                    );
                    break;
                default:
                    return status(
                        MACRO_SIM_INVALID_ARGUMENT,
                        "command kind is invalid"
                    );
            }
        }
        auto receipt = session->engine.apply(batch);
        if (!receipt.ok()) {
            return status(receipt.status());
        }
        output->reserved = 0;
        output->applied_mutations = receipt.get_if()->applied_mutations;
        output->created_loan_count =
            receipt.get_if()->created_loans.size();
        std::copy(
            receipt.get_if()->before.bytes.begin(),
            receipt.get_if()->before.bytes.end(),
            output->before_digest
        );
        std::copy(
            receipt.get_if()->after.bytes.begin(),
            receipt.get_if()->after.bytes.end(),
            output->after_digest
        );
        return status(MACRO_SIM_OK, "");
    } catch (const std::bad_alloc&) {
        return status(
            MACRO_SIM_ALLOCATION_FAILURE,
            "batch allocation failed"
        );
    } catch (...) {
        return status(MACRO_SIM_INTERNAL_ERROR, "batch conversion failed");
    }
}

macro_sim_status macro_sim_m2_state_digest(
    const macro_sim_session* session,
    uint8_t* output,
    size_t output_size
) {
    if (session == nullptr || output == nullptr || output_size != 32) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "session and 32-byte digest output are required"
        );
    }
    const auto digest = session->engine.digest();
    if (!digest.ok()) {
        return status(digest.status());
    }
    std::copy(
        digest.get_if()->bytes.begin(),
        digest.get_if()->bytes.end(),
        output
    );
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_save(
    const macro_sim_session* session,
    macro_sim_owned_buffer* output
) {
    if (session == nullptr || output == nullptr) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "session and checkpoint output are required"
        );
    }
    output->data = nullptr;
    output->size = 0;
    const auto checkpoint = session->engine.checkpoint();
    if (!checkpoint.ok()) {
        return status(checkpoint.status());
    }
    const auto size = checkpoint.get_if()->size();
    auto* bytes = new (std::nothrow) std::uint8_t[size];
    if (bytes == nullptr && size != 0) {
        return status(
            MACRO_SIM_ALLOCATION_FAILURE,
            "checkpoint output allocation failed"
        );
    }
    std::memcpy(bytes, checkpoint.get_if()->data(), size);
    output->data = bytes;
    output->size = size;
    return status(MACRO_SIM_OK, "");
}

macro_sim_status macro_sim_m2_checkpoint_load(
    macro_sim_session* session,
    const uint8_t* checkpoint,
    size_t checkpoint_size
) {
    if (session == nullptr
        || (checkpoint == nullptr && checkpoint_size != 0)) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "session and checkpoint input are invalid"
        );
    }
    return status(
        session->engine.restore_checkpoint(
            std::span<const std::uint8_t>(checkpoint, checkpoint_size)
        )
    );
}

macro_sim_status macro_sim_owned_buffer_release(
    macro_sim_owned_buffer* buffer
) {
    if (buffer == nullptr) {
        return status(
            MACRO_SIM_INVALID_ARGUMENT,
            "buffer is required"
        );
    }
    delete[] buffer->data;
    buffer->data = nullptr;
    buffer->size = 0;
    return status(MACRO_SIM_OK, "");
}
