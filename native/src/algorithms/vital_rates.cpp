#include "macro_sim/algorithms/vital_rates.hpp"

#include <array>
#include <cmath>

namespace macro_sim::algorithms {
namespace {

[[nodiscard]] bool valid_rates(const VitalRates& rates) noexcept {
    const std::array values{
        rates.makeham_a,
        rates.gompertz_b,
        rates.gompertz_theta,
        rates.infant_extra,
        rates.total_fertility_rate,
        rates.fertility_peak_age,
        rates.fertility_width,
        rates.sex_ratio_at_birth,
        rates.interval,
    };
    for (const auto value : values) {
        if (!std::isfinite(value)) {
            return false;
        }
    }
    return rates.makeham_a >= 0.0
        && rates.gompertz_b >= 0.0
        && rates.gompertz_theta > 0.0
        && rates.infant_extra >= 0.0
        && rates.total_fertility_rate >= 0.0
        && rates.fertility_width > 0.0
        && rates.sex_ratio_at_birth > 0.0
        && rates.maximum_age > 0
        && rates.interval > 0.0;
}

[[nodiscard]] Status invalid(std::string_view message) noexcept {
    return Status(ErrorCode::invalid_argument, message);
}

[[nodiscard]] Result<double> fertility_normalization(
    const VitalRates& rates
) noexcept {
    if (!valid_rates(rates)) {
        return invalid("invalid vital rates");
    }
    double total = 0.0;
    for (
        std::uint32_t age = 0;
        age <= rates.maximum_age;
        ++age
    ) {
        const double numeric_age = static_cast<double>(age);
        if (numeric_age < 15.0 || numeric_age > 49.0) {
            continue;
        }
        const double standardized =
            (numeric_age - rates.fertility_peak_age)
            / rates.fertility_width;
        total += std::exp(-0.5 * standardized * standardized);
    }
    total *= rates.interval;
    if (!std::isfinite(total) || total <= 0.0) {
        return invalid("fertility shape has zero area");
    }
    return total;
}

}  // namespace

Result<double> female_birth_share(const VitalRates& rates) noexcept {
    if (!valid_rates(rates)) {
        return invalid("invalid vital rates");
    }
    return 1.0 / (1.0 + rates.sex_ratio_at_birth);
}

Result<double> male_birth_share(const VitalRates& rates) noexcept {
    if (!valid_rates(rates)) {
        return invalid("invalid vital rates");
    }
    return rates.sex_ratio_at_birth / (1.0 + rates.sex_ratio_at_birth);
}

Result<double> mortality_integral(
    const VitalRates& rates,
    double age,
    double interval
) noexcept {
    if (
        !valid_rates(rates)
        || !std::isfinite(age)
        || !std::isfinite(interval)
        || interval < 0.0
    ) {
        return invalid("invalid mortality inputs");
    }
    const double end = age + interval;
    const double gompertz =
        (rates.gompertz_b / rates.gompertz_theta)
        * (
            std::exp(rates.gompertz_theta * end)
            - std::exp(rates.gompertz_theta * age)
        );
    const double infant_overlap = std::max(
        0.0,
        std::min(end, 1.0) - std::max(age, 0.0)
    );
    const double result =
        rates.makeham_a * interval
        + gompertz
        + rates.infant_extra * infant_overlap;
    if (!std::isfinite(result)) {
        return Status(
            ErrorCode::out_of_range,
            "mortality integral overflowed"
        );
    }
    return result;
}

Result<double> survival_probability(
    const VitalRates& rates,
    double age,
    double interval
) noexcept {
    auto integral = mortality_integral(rates, age, interval);
    if (!integral.ok()) {
        return integral.status();
    }
    return std::exp(-std::move(integral).take());
}

Result<double> fertility_shape_rate(
    const VitalRates& rates,
    double age
) noexcept {
    if (!std::isfinite(age)) {
        return invalid("fertility age must be finite");
    }
    if (age < 15.0 || age > 49.0) {
        return 0.0;
    }
    auto normalization = fertility_normalization(rates);
    if (!normalization.ok()) {
        return normalization.status();
    }
    const double standardized =
        (age - rates.fertility_peak_age) / rates.fertility_width;
    return std::exp(-0.5 * standardized * standardized)
        / std::move(normalization).take();
}

Result<double> fertility_rate(
    const VitalRates& rates,
    double age
) noexcept {
    auto shape = fertility_shape_rate(rates, age);
    if (!shape.ok()) {
        return shape.status();
    }
    return rates.total_fertility_rate * std::move(shape).take();
}

Result<double> expected_life_at_birth(
    const VitalRates& rates
) noexcept {
    if (!valid_rates(rates)) {
        return invalid("invalid vital rates");
    }
    double survivorship = 1.0;
    double years = 0.0;
    for (
        std::uint32_t age = 0;
        age <= rates.maximum_age;
        ++age
    ) {
        years += survivorship;
        if (age < rates.maximum_age) {
            auto survival = survival_probability(
                rates,
                static_cast<double>(age),
                rates.interval
            );
            if (!survival.ok()) {
                return survival.status();
            }
            survivorship *= std::move(survival).take();
        }
    }
    return years;
}

}  // namespace macro_sim::algorithms
