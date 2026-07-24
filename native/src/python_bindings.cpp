#include <array>
#include <cstdint>
#include <string>
#include <stdexcept>

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/string_view.h>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/rng.hpp"
#include "macro_sim/version.hpp"

namespace nb = nanobind;

namespace {

struct PythonScalar final {
    macro_sim::generated::InputKind kind;
    double number;
    std::string text;
};

PythonScalar scalar_from_python(nb::handle value) {
    using macro_sim::generated::InputKind;
    if (value.is_none()) {
        return {InputKind::null_value, 0.0, ""};
    }
    if (nb::isinstance<nb::bool_>(value)) {
        return {
            InputKind::boolean,
            nb::cast<bool>(value) ? 1.0 : 0.0,
            "",
        };
    }
    if (nb::isinstance<nb::int_>(value)) {
        return {
            InputKind::integer,
            static_cast<double>(nb::cast<std::int64_t>(value)),
            "",
        };
    }
    if (nb::isinstance<nb::float_>(value)) {
        return {InputKind::number, nb::cast<double>(value), ""};
    }
    if (nb::isinstance<nb::str>(value)) {
        return {InputKind::string, 0.0, nb::cast<std::string>(value)};
    }
    return {InputKind::id_set, 0.0, ""};
}

}  // namespace

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version", []() {
        return std::string(macro_sim::engine_version());
    });
    module.def(
        "validate_scalar",
        [](std::string_view contract_id, nb::object value) {
            const auto scalar = scalar_from_python(value);
            const auto code = macro_sim::generated::validate_scalar(
                contract_id,
                {
                    scalar.kind,
                    scalar.number,
                    scalar.text,
                }
            );
            return std::pair(
                code == macro_sim::generated::ValidationCode::ok,
                std::string(macro_sim::generated::validation_code_name(code))
            );
        },
        nb::arg("contract_id"),
        nb::arg("value").none()
    );
    module.def(
        "philox_block",
        [](macro_sim::PhiloxCounter counter, macro_sim::PhiloxKey key) {
            const auto block = macro_sim::philox4x32_10(counter, key);
            return nb::make_tuple(block[0], block[1], block[2], block[3]);
        },
        nb::arg("counter"),
        nb::arg("key")
    );
    nb::enum_<macro_sim::SessionState>(module, "SessionState")
        .value("READY", macro_sim::SessionState::ready)
        .value("CLOSED", macro_sim::SessionState::closed);
    nb::class_<macro_sim::EngineSession>(module, "EngineSession")
        .def(
            nb::init<std::uint64_t>(),
            nb::arg("session_id") = 1
        )
        .def_prop_ro("session_id", [](const macro_sim::EngineSession& session) {
            return session.id().value();
        })
        .def_prop_ro("tick", [](const macro_sim::EngineSession& session) {
            return session.tick().value();
        })
        .def_prop_ro("state", &macro_sim::EngineSession::state)
        .def_prop_ro("closed", &macro_sim::EngineSession::closed)
        .def("close", [](macro_sim::EngineSession& session) {
            const auto result = session.close();
            if (!result.ok()) {
                throw std::runtime_error(std::string(result.message()));
            }
        });
}
