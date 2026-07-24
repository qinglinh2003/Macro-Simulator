#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <type_traits>

#include "macro_sim/arena.hpp"
#include "macro_sim/buffer.hpp"
#include "macro_sim/c_api.h"
#include "macro_sim/engine_session.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/generated/invalid_cases.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"
#include "macro_sim/version.hpp"

namespace {

int require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}

}  // namespace

int main() {
    static_assert(!std::is_convertible_v<macro_sim::HouseholdId, macro_sim::FirmId>);
    static_assert(!std::is_convertible_v<macro_sim::Money, macro_sim::Price>);
    if (require(macro_sim::abi_version() == 1, "C++ ABI version mismatch") != 0) {
        return EXIT_FAILURE;
    }
    if (require(macro_sim_abi_version() == 1, "C ABI version mismatch") != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            macro_sim::engine_version() == macro_sim_engine_version(),
            "engine version mismatch"
        ) != 0) {
        return EXIT_FAILURE;
    }
    const auto money = macro_sim::Money(2.0) + macro_sim::Money(3.0);
    if (require(money.value() == 5.0, "typed quantity arithmetic failed") != 0) {
        return EXIT_FAILURE;
    }

    auto buffer_result = macro_sim::OwnedBuffer::allocate(64);
    if (require(buffer_result.ok(), "owned buffer allocation failed") != 0) {
        return EXIT_FAILURE;
    }
    auto buffer = std::move(buffer_result).take();
    if (require(buffer.size() == 64, "owned buffer size mismatch") != 0) {
        return EXIT_FAILURE;
    }

    auto arena_result = macro_sim::MonotonicArena::create(128);
    if (require(arena_result.ok(), "arena allocation failed") != 0) {
        return EXIT_FAILURE;
    }
    auto arena = std::move(arena_result).take();
    auto first = arena.allocate(16, 16);
    auto second = arena.allocate(32, 32);
    if (require(first.ok() && second.ok(), "aligned arena allocation failed") != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            reinterpret_cast<std::uintptr_t>(first.get_if()->data) % 16 == 0,
            "first arena allocation is misaligned"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            reinterpret_cast<std::uintptr_t>(second.get_if()->data) % 32 == 0,
            "second arena allocation is misaligned"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            !arena.allocate(1, 3).ok(),
            "non-power-of-two alignment was accepted"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            !arena.allocate(129).ok(),
            "arena overflow was accepted"
        ) != 0) {
        return EXIT_FAILURE;
    }
    arena.reset();
    if (require(arena.used() == 0, "arena reset failed") != 0) {
        return EXIT_FAILURE;
    }

    macro_sim::EngineSession session(
        macro_sim::EngineSessionOptions{macro_sim::SessionId(77)}
    );
    if (require(session.id().value() == 77, "session ID mismatch") != 0) {
        return EXIT_FAILURE;
    }
    if (require(session.tick().value() == 0, "empty session tick changed") != 0) {
        return EXIT_FAILURE;
    }
    if (require(session.close().ok(), "session close failed") != 0) {
        return EXIT_FAILURE;
    }
    if (require(!session.close().ok(), "double close was accepted") != 0) {
        return EXIT_FAILURE;
    }

    macro_sim_session* c_session = nullptr;
    macro_sim_create_options options{
        sizeof(macro_sim_create_options),
        MACRO_SIM_ABI_VERSION,
        91
    };
    auto c_status = macro_sim_session_create(&options, &c_session);
    if (require(c_status.code == MACRO_SIM_OK, "C session creation failed") != 0) {
        return EXIT_FAILURE;
    }
    std::uint64_t output = 0;
    if (require(
            macro_sim_session_id(c_session, &output).code == MACRO_SIM_OK &&
                output == 91,
            "C session ID mismatch"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            macro_sim_session_destroy(&c_session).code == MACRO_SIM_OK &&
                c_session == nullptr,
            "C session destruction failed"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            macro_sim_session_destroy(&c_session).code == MACRO_SIM_INVALID_HANDLE,
            "C double destroy was accepted"
        ) != 0) {
        return EXIT_FAILURE;
    }

    for (const auto& item : macro_sim::generated::kInvalidContractCases) {
        macro_sim::generated::ScalarValue value{};
        switch (item.input_kind) {
            case macro_sim::generated::InvalidInputKind::null_value:
                value.kind = macro_sim::generated::InputKind::null_value;
                break;
            case macro_sim::generated::InvalidInputKind::boolean:
                value.kind = macro_sim::generated::InputKind::boolean;
                value.number = item.number;
                break;
            case macro_sim::generated::InvalidInputKind::integer:
                value.kind = macro_sim::generated::InputKind::integer;
                value.number = item.number;
                break;
            case macro_sim::generated::InvalidInputKind::number:
                value.kind = macro_sim::generated::InputKind::number;
                value.number = item.number;
                break;
            case macro_sim::generated::InvalidInputKind::string:
                value.kind = macro_sim::generated::InputKind::string;
                value.text = item.text;
                break;
            case macro_sim::generated::InvalidInputKind::nonfinite:
                value.kind = macro_sim::generated::InputKind::number;
                value.number = std::numeric_limits<double>::quiet_NaN();
                break;
        }
        const auto code =
            macro_sim::generated::validate_scalar(item.contract_id, value);
        if (require(code == item.expected, item.id.data()) != 0) {
            return EXIT_FAILURE;
        }
    }
    return EXIT_SUCCESS;
}
