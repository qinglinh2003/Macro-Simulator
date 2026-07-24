#include <string>

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "macro_sim/version.hpp"

namespace nb = nanobind;

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version", []() {
        return std::string(macro_sim::engine_version());
    });
}
