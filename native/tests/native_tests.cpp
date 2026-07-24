#include <cstdlib>
#include <iostream>

#include "macro_sim/c_api.h"
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
    return EXIT_SUCCESS;
}
