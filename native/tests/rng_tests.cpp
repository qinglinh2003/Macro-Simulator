#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <span>
#include <utility>
#include <vector>

#include "macro_sim/generated/rng_vectors.hpp"
#include "macro_sim/rng.hpp"

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
    for (const auto& vector : macro_sim::generated::kPhiloxBlockVectors) {
        if (require(
                macro_sim::philox4x32_10(vector.counter, vector.key) == vector.output,
                "Philox block vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }

    macro_sim::PhiloxRng stream(
        {0x12345678U, 0x9ABCDEF0U},
        {7U, 6U, 5U, 4U}
    );
    for (const auto expected : macro_sim::generated::kStreamU32) {
        if (require(stream.next_u32() == expected, "stream u32 mismatch") != 0) {
            return EXIT_FAILURE;
        }
    }

    macro_sim::PhiloxRng uniform({11U, 29U});
    for (const auto expected : macro_sim::generated::kUniformBits) {
        if (require(
                std::bit_cast<std::uint64_t>(uniform.uniform_closed_open()) == expected,
                "uniform bit vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }
    for (const auto expected : macro_sim::generated::kOpenUniformBits) {
        if (require(
                std::bit_cast<std::uint64_t>(uniform.uniform_open()) == expected,
                "open uniform bit vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }

    macro_sim::PhiloxRng bounded({31U, 37U});
    for (const auto& vector : macro_sim::generated::kBoundedVectors) {
        auto result = bounded.bounded_u64(vector.bound);
        if (require(
                result.ok() && *result.get_if() == vector.value,
                "bounded vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }
    if (require(!bounded.bounded_u64(0).ok(), "zero bound was accepted") != 0) {
        return EXIT_FAILURE;
    }

    macro_sim::PhiloxRng bernoulli({41U, 43U});
    for (const auto& vector : macro_sim::generated::kBernoulliVectors) {
        auto result = bernoulli.bernoulli(vector.probability);
        if (require(
                result.ok() && *result.get_if() == vector.value,
                "Bernoulli vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }
    if (require(
            !bernoulli.bernoulli(std::numeric_limits<double>::quiet_NaN()).ok(),
            "NaN Bernoulli probability was accepted"
        ) != 0) {
        return EXIT_FAILURE;
    }

    macro_sim::PhiloxRng permutations({47U, 53U});
    std::vector<std::size_t> shuffled(12);
    for (std::size_t index = 0; index < shuffled.size(); ++index) {
        shuffled[index] = index;
    }
    if (require(
            permutations.shuffle<std::size_t>(std::span<std::size_t>(shuffled)).ok(),
            "shuffle failed"
        ) != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            std::equal(
                shuffled.begin(),
                shuffled.end(),
                macro_sim::generated::kShuffleVector.begin()
            ),
            "shuffle vector mismatch"
        ) != 0) {
        return EXIT_FAILURE;
    }
    auto sample = permutations.sample_indices(20, 7);
    if (require(sample.ok(), "sample failed") != 0) {
        return EXIT_FAILURE;
    }
    if (require(
            std::equal(
                sample.get_if()->begin(),
                sample.get_if()->end(),
                macro_sim::generated::kSampleVector.begin()
            ),
            "sample vector mismatch"
        ) != 0) {
        return EXIT_FAILURE;
    }

    macro_sim::PhiloxRng normal({59U, 61U});
    for (const auto expected : macro_sim::generated::kNormalBits) {
        const auto actual =
            std::bit_cast<std::uint64_t>(normal.standard_normal());
        if (actual != expected) {
            std::cerr << "normal bit vector mismatch: actual=" << actual
                      << " expected=" << expected << '\n';
            return EXIT_FAILURE;
        }
    }

    macro_sim::PhiloxRng poisson({67U, 71U});
    for (const auto& vector : macro_sim::generated::kPoissonVectors) {
        auto result = poisson.poisson(vector.lambda);
        if (require(
                result.ok() && *result.get_if() == vector.value,
                "Poisson vector mismatch"
            ) != 0) {
            return EXIT_FAILURE;
        }
    }
    if (require(
            !poisson.poisson(-1.0).ok(),
            "negative Poisson lambda was accepted"
        ) != 0) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
