#include <string>
#include <stdexcept>

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/version.hpp"

namespace nb = nanobind;

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version", []() {
        return std::string(macro_sim::engine_version());
    });
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
