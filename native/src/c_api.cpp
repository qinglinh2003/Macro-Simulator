#include "macro_sim/c_api.h"

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

}  // namespace

uint32_t macro_sim_abi_version(void) {
    return macro_sim::abi_version();
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
