#include "macro_sim/rng.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <utility>

namespace macro_sim {
namespace {

constexpr std::uint32_t kPhiloxM0 = 0xD2511F53U;
constexpr std::uint32_t kPhiloxM1 = 0xCD9E8D57U;
constexpr std::uint32_t kPhiloxW0 = 0x9E3779B9U;
constexpr std::uint32_t kPhiloxW1 = 0xBB67AE85U;
constexpr double kTwoToNegative53 = 1.0 / 9007199254740992.0;

struct Product final {
    std::uint32_t high;
    std::uint32_t low;
};

[[nodiscard]] constexpr Product multiply_high_low(
    std::uint32_t left,
    std::uint32_t right
) noexcept {
    const auto product =
        static_cast<std::uint64_t>(left) * static_cast<std::uint64_t>(right);
    return {
        static_cast<std::uint32_t>(product >> 32U),
        static_cast<std::uint32_t>(product),
    };
}

[[nodiscard]] constexpr PhiloxBlock philox_round(
    PhiloxCounter counter,
    PhiloxKey key
) noexcept {
    const auto first = multiply_high_low(kPhiloxM0, counter[0]);
    const auto second = multiply_high_low(kPhiloxM1, counter[2]);
    return {
        second.high ^ counter[1] ^ key[0],
        second.low,
        first.high ^ counter[3] ^ key[1],
        first.low,
    };
}

}  // namespace

PhiloxBlock philox4x32_10(PhiloxCounter counter, PhiloxKey key) noexcept {
    for (std::uint32_t round = 0; round < 10; ++round) {
        counter = philox_round(counter, key);
        key[0] += kPhiloxW0;
        key[1] += kPhiloxW1;
    }
    return counter;
}

PhiloxRng::PhiloxRng(PhiloxKey key, PhiloxCounter counter) noexcept
    : key_(key), counter_(counter) {}

std::uint32_t PhiloxRng::next_u32() noexcept {
    if (block_index_ >= block_.size()) {
        refill();
    }
    return block_[block_index_++];
}

std::uint64_t PhiloxRng::next_u64() noexcept {
    const auto low = static_cast<std::uint64_t>(next_u32());
    const auto high = static_cast<std::uint64_t>(next_u32());
    return low | (high << 32U);
}

double PhiloxRng::uniform_closed_open() noexcept {
    const auto bits = next_u64() >> 11U;
    return static_cast<double>(bits) * kTwoToNegative53;
}

double PhiloxRng::uniform_open() noexcept {
    const auto bits = next_u64() >> 11U;
    return (static_cast<double>(bits) + 0.5) * kTwoToNegative53;
}

Result<bool> PhiloxRng::bernoulli(double probability) noexcept {
    if (!std::isfinite(probability) || probability < 0.0 || probability > 1.0) {
        return Status(
            ErrorCode::invalid_argument,
            "Bernoulli probability must be finite and in [0, 1]"
        );
    }
    if (probability == 0.0) {
        return false;
    }
    if (probability == 1.0) {
        return true;
    }
    return uniform_closed_open() < probability;
}

Result<std::uint64_t> PhiloxRng::bounded_u64(std::uint64_t bound) noexcept {
    if (bound == 0) {
        return Status(ErrorCode::invalid_argument, "bounded draw requires bound > 0");
    }
    const auto threshold = static_cast<std::uint64_t>(0U - bound) % bound;
    while (true) {
        const auto value = next_u64();
        if (value >= threshold) {
            return value % bound;
        }
    }
}

Result<std::size_t> PhiloxRng::uniform_index(std::size_t size) noexcept {
    if (size == 0) {
        return Status(ErrorCode::invalid_argument, "index draw requires size > 0");
    }
    auto result = bounded_u64(static_cast<std::uint64_t>(size));
    if (!result.ok()) {
        return result.status();
    }
    const auto value = std::move(result).take();
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        return Status(ErrorCode::out_of_range, "index draw exceeds size_t");
    }
    return static_cast<std::size_t>(value);
}

Result<std::size_t> PhiloxRng::choice_index(std::size_t size) noexcept {
    return uniform_index(size);
}

double PhiloxRng::standard_normal() noexcept {
    double total = 0.0;
    for (std::uint32_t draw = 0; draw < 12; ++draw) {
        total += uniform_closed_open();
    }
    return total - 6.0;
}

Result<std::uint64_t> PhiloxRng::poisson(double lambda) noexcept {
    if (!std::isfinite(lambda) || lambda < 0.0) {
        return Status(
            ErrorCode::invalid_argument,
            "Poisson lambda must be finite and nonnegative"
        );
    }
    if (lambda == 0.0) {
        return std::uint64_t{0};
    }
    std::uint64_t total = 0;
    double remaining = lambda;
    while (remaining > 0.0) {
        const double chunk = std::min(remaining, 16.0);
        const double limit = std::exp(-chunk);
        std::uint64_t count = 0;
        double product = 1.0;
        do {
            ++count;
            product *= uniform_open();
        } while (product > limit);
        if (total > std::numeric_limits<std::uint64_t>::max() - (count - 1)) {
            return Status(ErrorCode::out_of_range, "Poisson result overflow");
        }
        total += count - 1;
        remaining -= chunk;
    }
    return total;
}

Result<std::vector<std::size_t>> PhiloxRng::sample_indices(
    std::size_t population_size,
    std::size_t sample_size
) noexcept {
    if (sample_size > population_size) {
        return Status(
            ErrorCode::invalid_argument,
            "sample size exceeds population size"
        );
    }
    try {
        std::vector<std::size_t> values(population_size);
        std::iota(values.begin(), values.end(), std::size_t{0});
        for (std::size_t offset = 0; offset < sample_size; ++offset) {
            auto draw = uniform_index(population_size - offset);
            if (!draw.ok()) {
                return draw.status();
            }
            const auto selected = offset + std::move(draw).take();
            using std::swap;
            swap(values[offset], values[selected]);
        }
        values.resize(sample_size);
        return values;
    } catch (const std::bad_alloc&) {
        return Status(ErrorCode::allocation_failure, "sample allocation failed");
    } catch (...) {
        return Status(ErrorCode::internal_error, "sample generation failed");
    }
}

PhiloxCounter PhiloxRng::counter() const noexcept {
    return counter_;
}

PhiloxKey PhiloxRng::key() const noexcept {
    return key_;
}

void PhiloxRng::refill() noexcept {
    block_ = philox4x32_10(counter_, key_);
    increment_counter();
    block_index_ = 0;
}

void PhiloxRng::increment_counter() noexcept {
    for (auto& word : counter_) {
        ++word;
        if (word != 0) {
            return;
        }
    }
}

}  // namespace macro_sim
