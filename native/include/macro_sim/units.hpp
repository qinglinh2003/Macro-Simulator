#ifndef MACRO_SIM_UNITS_HPP
#define MACRO_SIM_UNITS_HPP

#include <compare>
#include <cstdint>
#include <type_traits>

namespace macro_sim {

template <typename Tag, typename Rep>
class Quantity final {
    static_assert(std::is_arithmetic_v<Rep>);

public:
    using rep_type = Rep;

    constexpr Quantity() noexcept = default;
    explicit constexpr Quantity(Rep value) noexcept : value_(value) {}

    [[nodiscard]] constexpr Rep value() const noexcept {
        return value_;
    }

    constexpr Quantity& operator+=(Quantity other) noexcept {
        value_ += other.value_;
        return *this;
    }

    constexpr Quantity& operator-=(Quantity other) noexcept {
        value_ -= other.value_;
        return *this;
    }

    [[nodiscard]] friend constexpr Quantity operator+(
        Quantity left,
        Quantity right
    ) noexcept {
        left += right;
        return left;
    }

    [[nodiscard]] friend constexpr Quantity operator-(
        Quantity left,
        Quantity right
    ) noexcept {
        left -= right;
        return left;
    }

    constexpr auto operator<=>(const Quantity&) const noexcept = default;

private:
    Rep value_{};
};

struct CountTag;
struct GoodsTag;
struct CapitalTag;
struct MoneyTag;
struct PriceTag;
struct RateTag;
struct TickTag;

using Count = Quantity<CountTag, std::uint64_t>;
using Goods = Quantity<GoodsTag, double>;
using Capital = Quantity<CapitalTag, double>;
using Money = Quantity<MoneyTag, double>;
using Price = Quantity<PriceTag, double>;
using Rate = Quantity<RateTag, double>;
using Tick = Quantity<TickTag, std::uint64_t>;

static_assert(!std::is_convertible_v<Money, Price>);
static_assert(!std::is_convertible_v<Rate, Money>);
static_assert(!std::is_convertible_v<Tick, Count>);

}  // namespace macro_sim

#endif
