#include "macro_sim/algorithms/market.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <new>
#include <numeric>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include "macro_sim/algorithms/behavior.hpp"

namespace macro_sim::algorithms {
namespace {

struct LiveOffer final {
    std::size_t input_index{0};
    double stock{0.0};
    double sold{0.0};
};

class CountingRng final {
public:
    explicit CountingRng(
        PhiloxKey key,
        PhiloxCounter counter,
        MarketDiagnostics& diagnostics
    ) noexcept
        : rng_(key, counter), diagnostics_(diagnostics) {}

    [[nodiscard]] double uniform() noexcept {
        ++diagnostics_.random_draws;
        return rng_.uniform_closed_open();
    }

    [[nodiscard]] Result<std::size_t> index(std::size_t size) noexcept {
        ++diagnostics_.random_draws;
        return rng_.uniform_index(size);
    }

    [[nodiscard]] std::uint64_t tie_key() noexcept {
        ++diagnostics_.random_draws;
        return rng_.next_u64();
    }

    Status shuffle(std::span<std::size_t> values) noexcept {
        if (values.size() < 2) {
            return Status::success();
        }
        for (
            std::size_t remaining = values.size();
            remaining > 1;
            --remaining
        ) {
            auto draw = index(remaining);
            if (!draw.ok()) {
                return draw.status();
            }
            const auto selected = std::move(draw).take();
            using std::swap;
            swap(values[remaining - 1], values[selected]);
        }
        return Status::success();
    }

    [[nodiscard]] PhiloxCounter counter() const noexcept {
        return rng_.counter();
    }

private:
    PhiloxRng rng_;
    MarketDiagnostics& diagnostics_;
};

class FenwickTree final {
public:
    explicit FenwickTree(std::size_t size)
        : tree_(size + 1, 0.0), weights_(size, 0.0) {}

    void set(std::size_t index, double value) noexcept {
        const double delta = value - weights_[index];
        weights_[index] = value;
        for (
            std::size_t cursor = index + 1;
            cursor < tree_.size();
            cursor += cursor & (~cursor + 1)
        ) {
            tree_[cursor] += delta;
        }
    }

    [[nodiscard]] double weight(std::size_t index) const noexcept {
        return weights_[index];
    }

    [[nodiscard]] double total() const noexcept {
        return prefix(weights_.size());
    }

    [[nodiscard]] std::size_t select(double target) const noexcept {
        std::size_t index = 0;
        double accumulated = 0.0;
        std::size_t bit = 1;
        while (bit < tree_.size()) {
            bit <<= 1U;
        }
        for (bit >>= 1U; bit != 0; bit >>= 1U) {
            const std::size_t next = index + bit;
            if (
                next < tree_.size()
                && accumulated + tree_[next] <= target
            ) {
                index = next;
                accumulated += tree_[next];
            }
        }
        return std::min(index, weights_.size() - 1);
    }

private:
    [[nodiscard]] double prefix(std::size_t count) const noexcept {
        double result = 0.0;
        for (
            std::size_t cursor = count;
            cursor != 0;
            cursor -= cursor & (~cursor + 1)
        ) {
            result += tree_[cursor];
        }
        return result;
    }

    std::vector<double> tree_;
    std::vector<double> weights_;
};

[[nodiscard]] bool valid_worker_count(std::uint32_t count) noexcept {
    return count == 1 || count == 2 || count == 4 || count == 8;
}

[[nodiscard]] Status invalid(std::string_view message) noexcept {
    return Status(ErrorCode::invalid_argument, message);
}

[[nodiscard]] Status validate_inputs(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    const MarketConfig& config
) noexcept {
    if (
        config.sample_size == 0
        || !std::isfinite(config.preferential_beta)
        || config.preferential_beta < 0.0
        || !std::isfinite(config.price_elasticity)
        || config.price_elasticity < 0.0
        || !valid_worker_count(config.worker_count)
    ) {
        return invalid("invalid market configuration");
    }
    try {
        std::unordered_set<std::uint64_t> order_ids;
        std::unordered_set<std::uint64_t> buyer_accounts;
        std::unordered_set<std::uint64_t> offer_ids;
        std::unordered_set<std::uint64_t> seller_accounts;
        order_ids.reserve(orders.size());
        buyer_accounts.reserve(orders.size());
        offer_ids.reserve(offers.size());
        seller_accounts.reserve(offers.size());
        for (const auto& order : orders) {
            const double demand = order.demand.value();
            const double budget = order.budget.value();
            if (
                order.order_id == 0
                || !order.buyer.valid()
                || std::isnan(demand)
                || demand < 0.0
                || (!std::isfinite(demand) && !std::isinf(demand))
                || !std::isfinite(budget)
                || budget < 0.0
            ) {
                return invalid("invalid buy order");
            }
            if (!order_ids.insert(order.order_id).second) {
                return Status(
                    ErrorCode::already_exists,
                    "duplicate buy order ID"
                );
            }
            if (!buyer_accounts.insert(order.buyer.value()).second) {
                return Status(
                    ErrorCode::already_exists,
                    "duplicate buyer account"
                );
            }
        }
        for (const auto& offer : offers) {
            if (
                offer.offer_id == 0
                || !offer.seller.valid()
                || !std::isfinite(offer.stock.value())
                || offer.stock.value() < 0.0
                || !std::isfinite(offer.price.value())
                || offer.price.value() <= 0.0
                || !std::isfinite(offer.attractiveness)
            ) {
                return invalid("invalid sell offer");
            }
            if (!offer_ids.insert(offer.offer_id).second) {
                return Status(
                    ErrorCode::already_exists,
                    "duplicate sell offer ID"
                );
            }
            if (!seller_accounts.insert(offer.seller.value()).second) {
                return Status(
                    ErrorCode::already_exists,
                    "duplicate seller account"
                );
            }
        }
        return Status::success();
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "market validation allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "market validation failed"
        );
    }
}

void append_trade(
    MarketClearing& clearing,
    const BuyOrder& order,
    const SellOffer& offer,
    LiveOffer& live,
    double quantity
) {
    const double value = quantity * offer.price.value();
    live.stock -= quantity;
    live.sold += quantity;
    clearing.trades.push_back(
        Trade{
            static_cast<std::uint64_t>(clearing.trades.size()),
            order.order_id,
            offer.offer_id,
            order.buyer,
            offer.seller,
            Goods(quantity),
            offer.price,
            Money(value),
        }
    );
}

[[nodiscard]] double feasible_quantity(
    double remaining_demand,
    double remaining_budget,
    const SellOffer& offer,
    const LiveOffer& live
) noexcept {
    return std::min(
        {
            remaining_demand,
            remaining_budget / offer.price.value(),
            live.stock,
        }
    );
}

void append_allocation(
    MarketClearing& clearing,
    const BuyOrder& order,
    double allocated_quantity,
    double remaining_demand,
    double remaining_budget
) {
    clearing.allocations.push_back(
        Allocation{
            order.order_id,
            order.buyer,
            Goods(allocated_quantity),
            Money(order.budget.value() - remaining_budget),
            Goods(remaining_demand),
            Money(remaining_budget),
        }
    );
}

[[nodiscard]] Result<std::vector<std::size_t>> sampled_positions(
    std::size_t live_size,
    std::size_t sample_size,
    CountingRng& rng
) noexcept {
    try {
        const std::size_t count = std::min(live_size, sample_size);
        std::vector<std::size_t> selected;
        selected.reserve(count);
        if (count == live_size) {
            selected.resize(live_size);
            std::iota(selected.begin(), selected.end(), std::size_t{0});
            return selected;
        }
        while (selected.size() < count) {
            auto draw = rng.index(live_size);
            if (!draw.ok()) {
                return draw.status();
            }
            const auto candidate = std::move(draw).take();
            if (
                std::find(
                    selected.begin(),
                    selected.end(),
                    candidate
                ) == selected.end()
            ) {
                selected.push_back(candidate);
            }
        }
        return selected;
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "seller sample allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "seller sampling failed"
        );
    }
}

Status clear_sampled(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    std::span<const std::size_t> buyer_order,
    const MarketConfig& config,
    CountingRng& rng,
    std::vector<LiveOffer>& live,
    MarketClearing& clearing
) {
    std::vector<std::size_t> active;
    active.reserve(live.size());
    for (std::size_t index = 0; index < live.size(); ++index) {
        if (live[index].stock > kEconomicEpsilon) {
            active.push_back(index);
        }
    }
    for (const auto buyer_index : buyer_order) {
        const auto& order = orders[buyer_index];
        double remaining_budget = order.budget.value();
        double remaining_demand = order.demand.value();
        double allocated_quantity = 0.0;
        while (
            remaining_budget > kEconomicEpsilon
            && remaining_demand > kEconomicEpsilon
            && !active.empty()
        ) {
            std::size_t chosen_position =
                std::numeric_limits<std::size_t>::max();
            if (config.sample_size == 1) {
                auto draw = rng.index(active.size());
                if (!draw.ok()) {
                    return draw.status();
                }
                chosen_position = std::move(draw).take();
                if (
                    offers[live[active[chosen_position]].input_index].seller
                    == order.buyer
                ) {
                    chosen_position =
                        std::numeric_limits<std::size_t>::max();
                    for (
                        std::size_t position = 0;
                        position < active.size();
                        ++position
                    ) {
                        ++clearing.diagnostics.seller_candidates;
                        if (
                            offers[
                                live[active[position]].input_index
                            ].seller != order.buyer
                        ) {
                            chosen_position = position;
                            break;
                        }
                    }
                }
            } else {
                auto positions = sampled_positions(
                    active.size(),
                    config.sample_size,
                    rng
                );
                if (!positions.ok()) {
                    return positions.status();
                }
                double best_price =
                    std::numeric_limits<double>::infinity();
                for (const auto position : std::move(positions).take()) {
                    ++clearing.diagnostics.seller_candidates;
                    const auto& offer = offers[
                        live[active[position]].input_index
                    ];
                    if (
                        offer.seller != order.buyer
                        && offer.price.value() < best_price
                    ) {
                        best_price = offer.price.value();
                        chosen_position = position;
                    }
                }
            }
            if (chosen_position == std::numeric_limits<std::size_t>::max()) {
                break;
            }
            const std::size_t live_index = active[chosen_position];
            auto& live_offer = live[live_index];
            const auto& offer = offers[live_offer.input_index];
            const double quantity = feasible_quantity(
                remaining_demand,
                remaining_budget,
                offer,
                live_offer
            );
            if (quantity <= kEconomicEpsilon) {
                break;
            }
            append_trade(clearing, order, offer, live_offer, quantity);
            allocated_quantity += quantity;
            remaining_budget -= quantity * offer.price.value();
            remaining_demand -= quantity;
            if (live_offer.stock <= kEconomicEpsilon) {
                active[chosen_position] = active.back();
                active.pop_back();
                ++clearing.diagnostics.seller_updates;
            }
        }
        append_allocation(
            clearing,
            order,
            allocated_quantity,
            remaining_demand,
            remaining_budget
        );
    }
    return Status::success();
}

Status clear_preferential(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    std::span<const std::size_t> buyer_order,
    const MarketConfig& config,
    CountingRng& rng,
    std::vector<LiveOffer>& live,
    MarketClearing& clearing
) {
    FenwickTree weights(live.size());
    std::unordered_map<std::uint64_t, std::size_t> by_account;
    by_account.reserve(live.size());
    for (std::size_t index = 0; index < live.size(); ++index) {
        const auto& offer = offers[live[index].input_index];
        by_account.emplace(offer.seller.value(), index);
        if (live[index].stock <= kEconomicEpsilon) {
            continue;
        }
        const double weight =
            std::pow(
                std::max(kEconomicEpsilon, offer.attractiveness),
                config.preferential_beta
            )
            / std::pow(
                offer.price.value(),
                config.price_elasticity
            );
        if (!std::isfinite(weight) || weight <= 0.0) {
            return Status(
                ErrorCode::contract_violation,
                "preferential weight is invalid"
            );
        }
        weights.set(index, weight);
    }
    clearing.diagnostics.preferential_weight_builds = 1;
    for (const auto buyer_index : buyer_order) {
        const auto& order = orders[buyer_index];
        double remaining_budget = order.budget.value();
        double remaining_demand = order.demand.value();
        double allocated_quantity = 0.0;
        while (
            remaining_budget > kEconomicEpsilon
            && remaining_demand > kEconomicEpsilon
        ) {
            std::optional<std::pair<std::size_t, double>> excluded;
            const auto own = by_account.find(order.buyer.value());
            if (
                own != by_account.end()
                && weights.weight(own->second) > 0.0
            ) {
                excluded = std::pair(
                    own->second,
                    weights.weight(own->second)
                );
                weights.set(own->second, 0.0);
                ++clearing.diagnostics.seller_updates;
            }
            const double total = weights.total();
            if (!std::isfinite(total)) {
                if (excluded.has_value()) {
                    weights.set(excluded->first, excluded->second);
                    ++clearing.diagnostics.seller_updates;
                }
                return Status(
                    ErrorCode::contract_violation,
                    "preferential total weight is invalid"
                );
            }
            if (total <= 0.0) {
                if (excluded.has_value()) {
                    weights.set(excluded->first, excluded->second);
                    ++clearing.diagnostics.seller_updates;
                }
                break;
            }
            const double target = rng.uniform() * total;
            const std::size_t selected = weights.select(target);
            if (excluded.has_value()) {
                weights.set(excluded->first, excluded->second);
                ++clearing.diagnostics.seller_updates;
            }
            ++clearing.diagnostics.seller_candidates;
            auto& live_offer = live[selected];
            const auto& offer = offers[live_offer.input_index];
            const double quantity = feasible_quantity(
                remaining_demand,
                remaining_budget,
                offer,
                live_offer
            );
            if (quantity <= kEconomicEpsilon) {
                break;
            }
            append_trade(clearing, order, offer, live_offer, quantity);
            allocated_quantity += quantity;
            remaining_budget -= quantity * offer.price.value();
            remaining_demand -= quantity;
            if (live_offer.stock <= kEconomicEpsilon) {
                weights.set(selected, 0.0);
                ++clearing.diagnostics.seller_updates;
            }
        }
        append_allocation(
            clearing,
            order,
            allocated_quantity,
            remaining_demand,
            remaining_budget
        );
    }
    return Status::success();
}

Status clear_price_sorted(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    std::span<const std::size_t> buyer_order,
    CountingRng& rng,
    std::vector<LiveOffer>& live,
    MarketClearing& clearing
) {
    struct SortedOffer final {
        std::size_t live_index{0};
        std::uint64_t tie_key{0};
    };
    std::vector<SortedOffer> sorted;
    sorted.reserve(live.size());
    for (std::size_t index = 0; index < live.size(); ++index) {
        if (live[index].stock > kEconomicEpsilon) {
            sorted.push_back({index, rng.tie_key()});
        }
    }
    std::stable_sort(
        sorted.begin(),
        sorted.end(),
        [&](const auto& left, const auto& right) {
            const auto& left_offer =
                offers[live[left.live_index].input_index];
            const auto& right_offer =
                offers[live[right.live_index].input_index];
            if (left_offer.price.value() != right_offer.price.value()) {
                return left_offer.price.value()
                    < right_offer.price.value();
            }
            if (left.tie_key != right.tie_key) {
                return left.tie_key < right.tie_key;
            }
            return left_offer.offer_id < right_offer.offer_id;
        }
    );
    clearing.diagnostics.price_sorts = 1;
    std::size_t first_live = 0;
    for (const auto buyer_index : buyer_order) {
        const auto& order = orders[buyer_index];
        double remaining_budget = order.budget.value();
        double remaining_demand = order.demand.value();
        double allocated_quantity = 0.0;
        std::size_t alternate = first_live + 1;
        while (
            remaining_budget > kEconomicEpsilon
            && remaining_demand > kEconomicEpsilon
        ) {
            while (
                first_live < sorted.size()
                && live[sorted[first_live].live_index].stock
                    <= kEconomicEpsilon
            ) {
                ++first_live;
                ++clearing.diagnostics.seller_candidates;
            }
            if (first_live >= sorted.size()) {
                break;
            }
            std::size_t selected = first_live;
            const auto& cheapest = offers[
                live[sorted[first_live].live_index].input_index
            ];
            if (cheapest.seller == order.buyer) {
                alternate = std::max(alternate, first_live + 1);
                while (
                    alternate < sorted.size()
                    && (
                        live[sorted[alternate].live_index].stock
                            <= kEconomicEpsilon
                        || offers[
                            live[sorted[alternate].live_index].input_index
                        ].seller == order.buyer
                    )
                ) {
                    ++alternate;
                    ++clearing.diagnostics.seller_candidates;
                }
                if (alternate >= sorted.size()) {
                    break;
                }
                selected = alternate;
            }
            ++clearing.diagnostics.seller_candidates;
            auto& live_offer = live[sorted[selected].live_index];
            const auto& offer = offers[live_offer.input_index];
            const double quantity = feasible_quantity(
                remaining_demand,
                remaining_budget,
                offer,
                live_offer
            );
            if (quantity <= kEconomicEpsilon) {
                break;
            }
            append_trade(clearing, order, offer, live_offer, quantity);
            allocated_quantity += quantity;
            remaining_budget -= quantity * offer.price.value();
            remaining_demand -= quantity;
            if (live_offer.stock <= kEconomicEpsilon) {
                ++clearing.diagnostics.seller_updates;
                if (selected == first_live) {
                    ++first_live;
                } else {
                    ++alternate;
                }
            }
        }
        append_allocation(
            clearing,
            order,
            allocated_quantity,
            remaining_demand,
            remaining_budget
        );
    }
    return Status::success();
}

}  // namespace

Result<MarketClearing> clear_market(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    const MarketConfig& config
) noexcept {
    const auto inputs = validate_inputs(orders, offers, config);
    if (!inputs.ok()) {
        return inputs;
    }
    try {
        MarketClearing clearing;
        clearing.diagnostics.worker_count = config.worker_count;
        clearing.trades.reserve(orders.size() + offers.size());
        clearing.allocations.reserve(orders.size());
        clearing.stock_commands.reserve(offers.size());

        std::vector<LiveOffer> live;
        live.reserve(offers.size());
        for (std::size_t index = 0; index < offers.size(); ++index) {
            live.push_back({index, offers[index].stock.value(), 0.0});
        }

        std::vector<std::size_t> buyer_order(orders.size());
        std::iota(
            buyer_order.begin(),
            buyer_order.end(),
            std::size_t{0}
        );
        CountingRng rng(
            config.rng_key,
            config.rng_counter,
            clearing.diagnostics
        );
        const auto shuffle_status = rng.shuffle(buyer_order);
        if (!shuffle_status.ok()) {
            return shuffle_status;
        }

        Status status;
        switch (config.protocol) {
            case MatchingProtocol::sampled:
                status = clear_sampled(
                    orders,
                    offers,
                    buyer_order,
                    config,
                    rng,
                    live,
                    clearing
                );
                break;
            case MatchingProtocol::preferential:
                status = clear_preferential(
                    orders,
                    offers,
                    buyer_order,
                    config,
                    rng,
                    live,
                    clearing
                );
                break;
            case MatchingProtocol::price_sorted:
                status = clear_price_sorted(
                    orders,
                    offers,
                    buyer_order,
                    rng,
                    live,
                    clearing
                );
                break;
            default:
                return Status(
                    ErrorCode::unsupported,
                    "unknown matching protocol"
                );
        }
        if (!status.ok()) {
            return status;
        }
        for (const auto& live_offer : live) {
            const auto& offer = offers[live_offer.input_index];
            clearing.stock_commands.push_back(
                PhysicalStockCommand{
                    offer.offer_id,
                    offer.seller,
                    offer.stock,
                    Goods(live_offer.sold),
                    Goods(live_offer.stock),
                }
            );
        }
        clearing.next_counter = rng.counter();
        const auto validation =
            validate_market_clearing(orders, offers, clearing);
        if (!validation.ok()) {
            return validation;
        }
        return clearing;
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "market clearing allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "market clearing failed"
        );
    }
}

Status validate_market_clearing(
    std::span<const BuyOrder> orders,
    std::span<const SellOffer> offers,
    const MarketClearing& clearing
) noexcept {
    try {
        std::unordered_map<std::uint64_t, const BuyOrder*> orders_by_id;
        std::unordered_map<std::uint64_t, const SellOffer*> offers_by_id;
        std::unordered_map<std::uint64_t, double> allocated;
        std::unordered_map<std::uint64_t, double> spent;
        std::unordered_map<std::uint64_t, double> sold;
        std::unordered_map<std::uint64_t, std::size_t> sale_counts;
        std::unordered_set<std::uint64_t> allocation_ids;
        std::unordered_set<std::uint64_t> stock_command_ids;
        orders_by_id.reserve(orders.size());
        offers_by_id.reserve(offers.size());
        allocated.reserve(orders.size());
        spent.reserve(orders.size());
        sold.reserve(offers.size());
        sale_counts.reserve(offers.size());
        allocation_ids.reserve(orders.size());
        stock_command_ids.reserve(offers.size());
        for (const auto& order : orders) {
            orders_by_id.emplace(order.order_id, &order);
        }
        for (const auto& offer : offers) {
            offers_by_id.emplace(offer.offer_id, &offer);
        }
        for (std::size_t index = 0; index < clearing.trades.size(); ++index) {
            const auto& trade = clearing.trades[index];
            const auto order = orders_by_id.find(trade.order_id);
            const auto offer = offers_by_id.find(trade.offer_id);
            if (
                trade.ordinal != index
                || order == orders_by_id.end()
                || offer == offers_by_id.end()
                || trade.buyer != order->second->buyer
                || trade.seller != offer->second->seller
                || trade.buyer == trade.seller
                || !std::isfinite(trade.quantity.value())
                || trade.quantity.value() <= kEconomicEpsilon
                || !std::isfinite(trade.value.value())
                || trade.value.value() < 0.0
                || trade.price != offer->second->price
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "invalid trade record"
                );
            }
            const double expected_value =
                trade.quantity.value() * trade.price.value();
            const double tolerance =
                16.0 * std::numeric_limits<double>::epsilon()
                * std::max(1.0, std::abs(expected_value));
            if (std::abs(expected_value - trade.value.value()) > tolerance) {
                return Status(
                    ErrorCode::invariant_violation,
                    "trade value identity failed"
                );
            }
            allocated[trade.order_id] += trade.quantity.value();
            spent[trade.order_id] += trade.value.value();
            sold[trade.offer_id] += trade.quantity.value();
            ++sale_counts[trade.offer_id];
        }
        for (const auto& order : orders) {
            const double order_allocated = allocated[order.order_id];
            const double order_spent = spent[order.order_id];
            if (
                (
                    std::isfinite(order.demand.value())
                    && order_allocated
                        > order.demand.value() + kEconomicEpsilon
                )
                || order_spent
                    > order.budget.value() + kEconomicEpsilon
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "buyer feasibility failed"
                );
            }
        }
        for (const auto& offer : offers) {
            if (
                sold[offer.offer_id]
                > offer.stock.value() + kEconomicEpsilon
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "seller oversold stock"
                );
            }
        }
        if (
            clearing.allocations.size() != orders.size()
            || clearing.stock_commands.size() != offers.size()
        ) {
            return Status(
                ErrorCode::invariant_violation,
                "market summary cardinality failed"
            );
        }
        for (const auto& allocation : clearing.allocations) {
            const auto order = orders_by_id.find(allocation.order_id);
            if (
                order == orders_by_id.end()
                || !allocation_ids.insert(allocation.order_id).second
                || allocation.buyer != order->second->buyer
                || !std::isfinite(allocation.allocated.value())
                || allocation.allocated.value() < 0.0
                || !std::isfinite(allocation.spent.value())
                || allocation.spent.value() < 0.0
                || !std::isfinite(allocation.remaining_budget.value())
                || allocation.remaining_budget.value() < -kEconomicEpsilon
                || std::abs(
                    allocation.allocated.value()
                    - allocated[allocation.order_id]
                ) > kEconomicEpsilon
                || std::abs(
                    allocation.spent.value()
                    - spent[allocation.order_id]
                ) > kEconomicEpsilon
                || std::abs(
                    allocation.spent.value()
                    + allocation.remaining_budget.value()
                    - order->second->budget.value()
                ) > kEconomicEpsilon
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "buyer allocation summary failed"
                );
            }
            if (
                std::isfinite(order->second->demand.value())
                && (
                    !std::isfinite(allocation.remaining_demand.value())
                    || allocation.remaining_demand.value()
                        < -kEconomicEpsilon
                    || std::abs(
                        allocation.allocated.value()
                        + allocation.remaining_demand.value()
                        - order->second->demand.value()
                    ) > kEconomicEpsilon
                )
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "buyer demand summary failed"
                );
            }
        }
        for (const auto& command : clearing.stock_commands) {
            const auto offer = offers_by_id.find(command.offer_id);
            const double expected_sold = sold[command.offer_id];
            const double stock_scale = std::max({
                1.0,
                std::abs(command.opening.value()),
                std::abs(command.sold.value()),
                std::abs(command.closing.value()),
                std::abs(expected_sold),
            });
            // A large market accumulates sold quantities in a different order
            // from the live-offer decrement. Both paths conserve the same stock,
            // but their floating-point round-off grows with the stock scale.
            const double stock_tolerance = std::max(
                kEconomicEpsilon,
                32.0 * std::numeric_limits<double>::epsilon()
                    * static_cast<double>(std::max<std::size_t>(
                        1, sale_counts[command.offer_id]))
                    * stock_scale
            );
            if (
                offer == offers_by_id.end()
                || !stock_command_ids.insert(command.offer_id).second
                || command.seller != offer->second->seller
                || command.opening != offer->second->stock
                || std::abs(command.sold.value() - expected_sold)
                    > stock_tolerance
                || std::abs(
                    command.opening.value()
                    - command.sold.value()
                    - command.closing.value()
                ) > stock_tolerance
                || command.closing.value() < -kEconomicEpsilon
            ) {
                return Status(
                    ErrorCode::invariant_violation,
                    "physical stock conservation failed"
                );
            }
        }
        return Status::success();
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "market validation allocation failed"
        );
    } catch (...) {
        return Status(
            ErrorCode::internal_error,
            "market result validation failed"
        );
    }
}

}  // namespace macro_sim::algorithms
