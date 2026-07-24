#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

#include "macro_sim/algorithms/market.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::algorithms;

[[nodiscard]] MarketClearing take(Result<MarketClearing> result) {
    assert(result.ok());
    return std::move(result).take();
}

[[nodiscard]] std::vector<BuyOrder> standard_orders() {
    return {
        {1, AccountId(101), Goods(3.0), Money(30.0)},
        {2, AccountId(102), Goods(5.0), Money(25.0)},
        {
            3,
            AccountId(103),
            Goods(std::numeric_limits<double>::infinity()),
            Money(12.0),
        },
    };
}

[[nodiscard]] std::vector<SellOffer> standard_offers() {
    return {
        {11, AccountId(201), Goods(4.0), Price(3.0), 1.0},
        {12, AccountId(202), Goods(5.0), Price(2.0), 2.0},
        {13, AccountId(203), Goods(6.0), Price(5.0), 4.0},
    };
}

void assert_same(
    const MarketClearing& left,
    const MarketClearing& right
) {
    assert(left.trades.size() == right.trades.size());
    assert(left.allocations.size() == right.allocations.size());
    assert(left.stock_commands.size() == right.stock_commands.size());
    for (std::size_t index = 0; index < left.trades.size(); ++index) {
        const auto& a = left.trades[index];
        const auto& b = right.trades[index];
        assert(a.ordinal == b.ordinal);
        assert(a.order_id == b.order_id);
        assert(a.offer_id == b.offer_id);
        assert(a.buyer == b.buyer);
        assert(a.seller == b.seller);
        assert(a.quantity == b.quantity);
        assert(a.price == b.price);
        assert(a.value == b.value);
    }
    for (std::size_t index = 0; index < left.allocations.size(); ++index) {
        const auto& a = left.allocations[index];
        const auto& b = right.allocations[index];
        assert(a.order_id == b.order_id);
        assert(a.buyer == b.buyer);
        assert(a.allocated == b.allocated);
        assert(a.spent == b.spent);
        assert(a.remaining_demand == b.remaining_demand);
        assert(a.remaining_budget == b.remaining_budget);
    }
    for (
        std::size_t index = 0;
        index < left.stock_commands.size();
        ++index
    ) {
        const auto& a = left.stock_commands[index];
        const auto& b = right.stock_commands[index];
        assert(a.offer_id == b.offer_id);
        assert(a.seller == b.seller);
        assert(a.opening == b.opening);
        assert(a.sold == b.sold);
        assert(a.closing == b.closing);
    }
    assert(left.next_counter == right.next_counter);
}

void test_price_sorted_fixture() {
    const std::vector<BuyOrder> orders{
        {1, AccountId(10), Goods(4.0), Money(20.0)},
    };
    const std::vector<SellOffer> offers{
        {1, AccountId(20), Goods(2.0), Price(4.0), 1.0},
        {2, AccountId(30), Goods(5.0), Price(2.0), 1.0},
    };
    MarketConfig config;
    config.protocol = MatchingProtocol::price_sorted;
    const auto result = take(clear_market(orders, offers, config));
    assert(result.trades.size() == 1);
    assert(result.trades[0].offer_id == 2);
    assert(result.trades[0].quantity == Goods(4.0));
    assert(result.trades[0].value == Money(8.0));
    assert(result.diagnostics.price_sorts == 1);
}

void test_sampled_and_preferential_fixtures() {
    auto orders = standard_orders();
    auto offers = standard_offers();
    MarketConfig sampled;
    sampled.protocol = MatchingProtocol::sampled;
    sampled.sample_size = 3;
    sampled.rng_key = {7U, 9U};
    const auto first = take(clear_market(orders, offers, sampled));
    const auto second = take(clear_market(orders, offers, sampled));
    assert_same(first, second);
    assert(first.diagnostics.price_sorts == 0);
    assert(first.diagnostics.preferential_weight_builds == 0);

    MarketConfig preferential;
    preferential.protocol = MatchingProtocol::preferential;
    preferential.preferential_beta = 1.0;
    preferential.price_elasticity = 0.5;
    preferential.rng_key = {11U, 13U};
    const auto weighted = take(clear_market(orders, offers, preferential));
    assert(weighted.diagnostics.preferential_weight_builds == 1);
    assert(weighted.diagnostics.price_sorts == 0);
    assert(validate_market_clearing(orders, offers, weighted).ok());
}

void test_no_self_trade_and_no_oversell() {
    const std::vector<BuyOrder> orders{
        {1, AccountId(20), Goods(10.0), Money(100.0)},
        {2, AccountId(30), Goods(10.0), Money(100.0)},
    };
    const std::vector<SellOffer> offers{
        {1, AccountId(20), Goods(1.0), Price(1.0), 1.0},
        {2, AccountId(30), Goods(1.0), Price(1.0), 1.0},
    };
    for (const auto protocol : {
            MatchingProtocol::sampled,
            MatchingProtocol::preferential,
            MatchingProtocol::price_sorted,
        }) {
        MarketConfig config;
        config.protocol = protocol;
        config.sample_size = 2;
        config.rng_key = {17U, static_cast<std::uint32_t>(protocol)};
        const auto result = take(clear_market(orders, offers, config));
        double total = 0.0;
        for (const auto& trade : result.trades) {
            assert(trade.buyer != trade.seller);
            total += trade.quantity.value();
        }
        assert(total <= 2.0 + 1.0e-9);
        assert(validate_market_clearing(orders, offers, result).ok());
    }
}

void test_supported_worker_counts_are_invariant() {
    const auto orders = standard_orders();
    const auto offers = standard_offers();
    for (const auto protocol : {
            MatchingProtocol::sampled,
            MatchingProtocol::preferential,
            MatchingProtocol::price_sorted,
        }) {
        MarketConfig config;
        config.protocol = protocol;
        config.sample_size = 2;
        config.rng_key = {19U, 23U};
        config.worker_count = 1;
        const auto reference = take(clear_market(orders, offers, config));
        for (const auto workers : {2U, 4U, 8U}) {
            config.worker_count = workers;
            const auto candidate = take(clear_market(orders, offers, config));
            assert_same(reference, candidate);
            assert(candidate.diagnostics.worker_count == workers);
        }
    }
}

void test_randomized_properties() {
    for (std::uint32_t seed = 1; seed <= 100; ++seed) {
        std::vector<BuyOrder> orders;
        std::vector<SellOffer> offers;
        for (std::uint64_t index = 0; index < 20; ++index) {
            orders.push_back(
                {
                    index + 1,
                    AccountId(1000 + index),
                    Goods(1.0 + static_cast<double>((seed + index) % 11)),
                    Money(2.0 + static_cast<double>((seed * 3 + index) % 29)),
                }
            );
        }
        for (std::uint64_t index = 0; index < 15; ++index) {
            offers.push_back(
                {
                    100 + index,
                    AccountId(2000 + index),
                    Goods(1.0 + static_cast<double>((seed + index) % 7)),
                    Price(0.5 + static_cast<double>((seed + index) % 9)),
                    0.25 + static_cast<double>((seed * 5 + index) % 13),
                }
            );
        }
        for (const auto protocol : {
                MatchingProtocol::sampled,
                MatchingProtocol::preferential,
                MatchingProtocol::price_sorted,
            }) {
            MarketConfig config;
            config.protocol = protocol;
            config.sample_size = 4;
            config.preferential_beta = 0.8;
            config.price_elasticity = 0.4;
            config.rng_key = {seed, seed * 7919U};
            const auto result = take(clear_market(orders, offers, config));
            assert(validate_market_clearing(orders, offers, result).ok());
            if (protocol == MatchingProtocol::preferential) {
                assert(
                    result.diagnostics.preferential_weight_builds == 1
                );
            }
            if (protocol == MatchingProtocol::price_sorted) {
                assert(result.diagnostics.price_sorts == 1);
            }
        }
    }
}

void test_stochastic_selection_distributions() {
    const std::vector<BuyOrder> orders{
        {1, AccountId(100), Goods(1.0), Money(10.0)},
    };
    const std::vector<SellOffer> uniform_offers{
        {1, AccountId(201), Goods(1.0), Price(1.0), 1.0},
        {2, AccountId(202), Goods(1.0), Price(1.0), 1.0},
        {3, AccountId(203), Goods(1.0), Price(1.0), 1.0},
        {4, AccountId(204), Goods(1.0), Price(1.0), 1.0},
    };
    std::array<std::uint64_t, 4> sampled_counts{};
    std::array<std::uint64_t, 4> preferential_counts{};
    std::array<std::uint64_t, 4> tie_counts{};
    const std::vector<SellOffer> weighted_offers{
        {1, AccountId(201), Goods(1.0), Price(1.0), 1.0},
        {2, AccountId(202), Goods(1.0), Price(1.0), 2.0},
        {3, AccountId(203), Goods(1.0), Price(1.0), 3.0},
        {4, AccountId(204), Goods(1.0), Price(1.0), 4.0},
    };
    constexpr std::uint32_t samples = 20000;
    for (std::uint32_t seed = 0; seed < samples; ++seed) {
        MarketConfig config;
        config.protocol = MatchingProtocol::sampled;
        config.sample_size = 1;
        config.rng_key = {seed, seed ^ 0x9E3779B9U};
        auto sampled = take(clear_market(orders, uniform_offers, config));
        ++sampled_counts[sampled.trades[0].offer_id - 1];

        config.protocol = MatchingProtocol::preferential;
        auto weighted = take(clear_market(orders, weighted_offers, config));
        ++preferential_counts[weighted.trades[0].offer_id - 1];

        config.protocol = MatchingProtocol::price_sorted;
        auto tied = take(clear_market(orders, uniform_offers, config));
        ++tie_counts[tied.trades[0].offer_id - 1];
    }
    for (std::size_t index = 0; index < 4; ++index) {
        assert(std::abs(
            static_cast<double>(sampled_counts[index]) / samples - 0.25
        ) < 0.02);
        assert(std::abs(
            static_cast<double>(tie_counts[index]) / samples - 0.25
        ) < 0.02);
        const double expected =
            static_cast<double>(index + 1) / 10.0;
        assert(std::abs(
            static_cast<double>(preferential_counts[index]) / samples
                - expected
        ) < 0.02);
    }
}

void test_invalid_inputs() {
    auto orders = standard_orders();
    auto offers = standard_offers();
    MarketConfig config;
    config.worker_count = 3;
    assert(!clear_market(orders, offers, config).ok());
    config.worker_count = 1;
    offers[0].price = Price(0.0);
    assert(!clear_market(orders, offers, config).ok());
    offers = standard_offers();
    offers[1].seller = offers[0].seller;
    assert(!clear_market(orders, offers, config).ok());
}

}  // namespace

int main() {
    test_price_sorted_fixture();
    test_sampled_and_preferential_fixtures();
    test_no_self_trade_and_no_oversell();
    test_supported_worker_counts_are_invariant();
    test_randomized_properties();
    test_stochastic_selection_distributions();
    test_invalid_inputs();
    return 0;
}
