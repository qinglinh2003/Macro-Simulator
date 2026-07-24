#include <chrono>
#include <cstdint>
#include <iostream>

#include "macro_sim/version.hpp"

int main() {
    constexpr std::uint64_t iterations = 1'000'000;
    const auto started = std::chrono::steady_clock::now();
    std::uint64_t accumulator = 0;
    for (std::uint64_t index = 0; index < iterations; ++index) {
        accumulator += macro_sim::abi_version();
    }
    const auto elapsed = std::chrono::steady_clock::now() - started;
    const auto nanoseconds =
        std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count();
    std::cout << "{\"benchmark\":\"foundation.version\",\"iterations\":"
              << iterations << ",\"elapsed_ns\":" << nanoseconds
              << ",\"guard\":" << accumulator << "}\n";
    return 0;
}
