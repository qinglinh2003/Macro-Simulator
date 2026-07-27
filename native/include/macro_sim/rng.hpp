#ifndef MACRO_SIM_RNG_HPP
#define MACRO_SIM_RNG_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/error.hpp"

namespace macro_sim {

using PhiloxCounter = std::array<std::uint32_t, 4>;
using PhiloxKey = std::array<std::uint32_t, 2>;
using PhiloxBlock = std::array<std::uint32_t, 4>;

[[nodiscard]] PhiloxBlock philox4x32_10(
    PhiloxCounter counter,
    PhiloxKey key
) noexcept;

class PhiloxRng final {
public:
    explicit PhiloxRng(
        PhiloxKey key,
        PhiloxCounter counter = {}
    ) noexcept;

    [[nodiscard]] std::uint32_t next_u32() noexcept;
    [[nodiscard]] std::uint64_t next_u64() noexcept;
    [[nodiscard]] double uniform_closed_open() noexcept;
    [[nodiscard]] double uniform_open() noexcept;
    [[nodiscard]] Result<bool> bernoulli(double probability) noexcept;
    [[nodiscard]] Result<std::uint64_t> bounded_u64(
        std::uint64_t bound
    ) noexcept;
    [[nodiscard]] Result<std::size_t> uniform_index(
        std::size_t size
    ) noexcept;
    [[nodiscard]] Result<std::size_t> choice_index(
        std::size_t size
    ) noexcept;
    [[nodiscard]] double standard_normal() noexcept;
    [[nodiscard]] Result<std::uint64_t> poisson(double lambda) noexcept;
    [[nodiscard]] Result<std::vector<std::size_t>> sample_indices(
        std::size_t population_size,
        std::size_t sample_size
    ) noexcept;

    template <typename T>
    Status shuffle(std::span<T> values) noexcept {
        if (values.size() < 2) {
            return Status::success();
        }
        for (std::size_t remaining = values.size(); remaining > 1; --remaining) {
            auto draw = uniform_index(remaining);
            if (!draw.ok()) {
                return draw.status();
            }
            // ``take()`` is rvalue-qualified, so the move is required to compile.
            // NOLINTNEXTLINE(performance-move-const-arg)
            const auto index = std::move(draw).take();
            using std::swap;
            swap(values[remaining - 1], values[index]);
        }
        return Status::success();
    }

    [[nodiscard]] PhiloxCounter counter() const noexcept;
    [[nodiscard]] PhiloxKey key() const noexcept;

private:
    void refill() noexcept;
    void increment_counter() noexcept;

    PhiloxKey key_{};
    PhiloxCounter counter_{};
    PhiloxBlock block_{};
    std::size_t block_index_{4};
};

}  // namespace macro_sim

#endif
