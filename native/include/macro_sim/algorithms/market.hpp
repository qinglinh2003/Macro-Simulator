#ifndef MACRO_SIM_ALGORITHMS_MARKET_HPP
#define MACRO_SIM_ALGORITHMS_MARKET_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/rng.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::algorithms {

enum class MatchingProtocol : std::uint8_t {
    sampled = 0,
    preferential = 1,
    price_sorted = 2,
};

struct BuyOrder final {
    std::uint64_t order_id{0};
    AccountId buyer{};
    Goods demand{};
    Money budget{};
};

struct SellOffer final {
    std::uint64_t offer_id{0};
    AccountId seller{};
    Goods stock{};
    Price price{};
    double attractiveness{1.0};
};

struct MarketConfig final {
    MatchingProtocol protocol{MatchingProtocol::sampled};
    std::uint32_t sample_size{1};
    double preferential_beta{1.0};
    double price_elasticity{0.0};
    PhiloxKey rng_key{};
    PhiloxCounter rng_counter{};
    std::uint32_t worker_count{1};
};

struct Trade final {
    std::uint64_t ordinal{0};
    std::uint64_t order_id{0};
    std::uint64_t offer_id{0};
    AccountId buyer{};
    AccountId seller{};
    Goods quantity{};
    Price price{};
    Money value{};
};

struct Allocation final {
    std::uint64_t order_id{0};
    AccountId buyer{};
    Goods allocated{};
    Money spent{};
    Goods remaining_demand{};
    Money remaining_budget{};
};

struct PhysicalStockCommand final {
    std::uint64_t offer_id{0};
    AccountId seller{};
    Goods opening{};
    Goods sold{};
    Goods closing{};
};

struct MarketDiagnostics final {
    std::uint64_t random_draws{0};
    std::uint64_t seller_candidates{0};
    std::uint64_t seller_updates{0};
    std::uint64_t preferential_weight_builds{0};
    std::uint64_t price_sorts{0};
    std::uint32_t worker_count{1};
};

struct MarketClearing final {
    std::vector<Trade> trades{};
    std::vector<Allocation> allocations{};
    std::vector<PhysicalStockCommand> stock_commands{};
    MarketDiagnostics diagnostics{};
    PhiloxCounter next_counter{};
};

[[nodiscard]] Result<MarketClearing> clear_market(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    const MarketConfig& config
) noexcept;

[[nodiscard]] Status validate_market_clearing(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    const MarketClearing& clearing
) noexcept;

}  // namespace macro_sim::algorithms

#endif
