#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/algorithms/market.hpp"

namespace {

using Clock = std::chrono::steady_clock;
using namespace macro_sim;
using namespace macro_sim::algorithms;

struct Row final {
    std::string_view protocol;
    std::size_t size;
    std::uint64_t median_ns;
    MarketDiagnostics diagnostics;
};

[[nodiscard]] std::vector<BuyOrder> make_orders(std::size_t size) {
    std::vector<BuyOrder> orders;
    orders.reserve(size);
    for (std::size_t index = 0; index < size; ++index) {
        orders.push_back({
            static_cast<std::uint64_t>(index + 1),
            AccountId(static_cast<std::uint64_t>(100000 + index)),
            Goods(1.0),
            Money(16.0),
        });
    }
    return orders;
}

[[nodiscard]] std::vector<SellOffer> make_offers(std::size_t size) {
    std::vector<SellOffer> offers;
    offers.reserve(size);
    for (std::size_t index = 0; index < size; ++index) {
        offers.push_back({
            static_cast<std::uint64_t>(index + 1),
            AccountId(static_cast<std::uint64_t>(200000 + index)),
            Goods(1.0),
            Price(1.0 + static_cast<double>(index % 17) * 0.01),
            1.0 + static_cast<double>(index % 11),
        });
    }
    return offers;
}

[[nodiscard]] Row measure(
    MatchingProtocol protocol,
    std::string_view name,
    std::size_t size,
    std::size_t repetitions
) {
    const auto orders = make_orders(size);
    const auto offers = make_offers(size);
    MarketConfig config;
    config.protocol = protocol;
    config.sample_size = 4;
    config.preferential_beta = 0.8;
    config.price_elasticity = 0.3;
    config.rng_key = {
        static_cast<std::uint32_t>(size),
        static_cast<std::uint32_t>(protocol) + 0x9E3779B9U,
    };
    std::vector<std::uint64_t> samples;
    samples.reserve(repetitions);
    MarketDiagnostics diagnostics;
    std::size_t trade_sink = 0;
    for (std::size_t repetition = 0; repetition < repetitions; ++repetition) {
        config.rng_counter = {
            static_cast<std::uint32_t>(repetition),
            0U,
            0U,
            0U,
        };
        const auto start = Clock::now();
        auto result = clear_market(orders, offers, config);
        const auto stop = Clock::now();
        assert(result.ok());
        auto clearing = std::move(result).take();
        assert(clearing.trades.size() == size);
        trade_sink += clearing.trades.size();
        diagnostics = clearing.diagnostics;
        samples.push_back(
            static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    stop - start
                ).count()
            )
        );
    }
    if (trade_sink == 0) {
        std::abort();
    }
    std::sort(samples.begin(), samples.end());
    return {
        name,
        size,
        samples[samples.size() / 2],
        diagnostics,
    };
}

}  // namespace

int main(int argc, char** argv) {
    std::size_t repetitions = 9;
    if (argc == 3 && std::string_view(argv[1]) == "--repetitions") {
        repetitions = static_cast<std::size_t>(
            std::strtoull(argv[2], nullptr, 10)
        );
    }
    if (repetitions < 3) {
        std::cerr << "repetitions must be at least 3\n";
        return 2;
    }
    std::vector<Row> rows;
    for (const auto size : {256U, 512U, 1024U, 2048U}) {
        rows.push_back(measure(
            MatchingProtocol::sampled,
            "sampled",
            size,
            repetitions
        ));
        rows.push_back(measure(
            MatchingProtocol::preferential,
            "preferential",
            size,
            repetitions
        ));
        rows.push_back(measure(
            MatchingProtocol::price_sorted,
            "price_sorted",
            size,
            repetitions
        ));
    }
    std::cout << "{\"rows\":[";
    for (std::size_t index = 0; index < rows.size(); ++index) {
        if (index != 0) {
            std::cout << ',';
        }
        const auto& row = rows[index];
        std::cout
            << "{\"median_ns\":" << row.median_ns
            << ",\"preferential_weight_builds\":"
            << row.diagnostics.preferential_weight_builds
            << ",\"price_sorts\":" << row.diagnostics.price_sorts
            << ",\"protocol\":\"" << row.protocol
            << "\",\"seller_candidates\":"
            << row.diagnostics.seller_candidates
            << ",\"seller_updates\":" << row.diagnostics.seller_updates
            << ",\"size\":" << row.size
            << '}';
    }
    std::cout << "],\"schema_version\":\"m3-market-benchmark-v1\"}\n";
    return 0;
}
