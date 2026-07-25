#ifndef MACRO_SIM_ALGORITHMS_VITAL_RATES_HPP
#define MACRO_SIM_ALGORITHMS_VITAL_RATES_HPP

#include <cstdint>

#include "macro_sim/error.hpp"

namespace macro_sim::algorithms {

struct VitalRates final {
    double makeham_a{3.0e-4};
    double gompertz_b{6.0e-5};
    double gompertz_theta{0.0866};
    double infant_extra{0.010};
    double total_fertility_rate{2.5};
    double fertility_peak_age{28.0};
    double fertility_width{6.0};
    double sex_ratio_at_birth{1.05};
    std::uint32_t maximum_age{100};
    double interval{1.0};

    bool operator==(const VitalRates &) const = default;
};

[[nodiscard]] Result<double> female_birth_share(
    const VitalRates& rates
) noexcept;
[[nodiscard]] Result<double> male_birth_share(
    const VitalRates& rates
) noexcept;
[[nodiscard]] Result<double> mortality_integral(
    const VitalRates& rates,
    double age,
    double interval
) noexcept;
[[nodiscard]] Result<double> survival_probability(
    const VitalRates& rates,
    double age,
    double interval
) noexcept;
[[nodiscard]] Result<double> fertility_shape_rate(
    const VitalRates& rates,
    double age
) noexcept;
[[nodiscard]] Result<double> fertility_rate(
    const VitalRates& rates,
    double age
) noexcept;
[[nodiscard]] Result<double> expected_life_at_birth(
    const VitalRates& rates
) noexcept;

}  // namespace macro_sim::algorithms

#endif
