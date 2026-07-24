#ifndef MACRO_SIM_SIMULATION_M4_HPP
#define MACRO_SIM_SIMULATION_M4_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/algorithms/market.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/rng.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::simulation {

enum class M4Vertical : std::uint8_t {
    cash_loop = 0,
    capital_fiscal = 1,
};

enum class M4Capability : std::uint64_t {
    physical_capital = 1ULL << 0U,
    government = 1ULL << 1U,
    credit = 1ULL << 2U,
    commercial_banks = 1ULL << 3U,
    central_bank = 1ULL << 4U,
    securities = 1ULL << 5U,
    equity = 1ULL << 6U,
    demographics = 1ULL << 7U,
    persistent_labor = 1ULL << 8U,
    energy = 1ULL << 9U,
    housing = 1ULL << 10U,
    open_economy = 1ULL << 11U,
    stateful_shocks = 1ULL << 12U,
    controllers = 1ULL << 13U,
    reinforcement_learning = 1ULL << 14U,
};

[[nodiscard]] constexpr std::uint64_t capability_bit(
    M4Capability capability
) noexcept {
    return static_cast<std::uint64_t>(capability);
}

struct M4Rules final {
    double linear_productivity{1.0};
    double capital_productivity{2.4};
    double total_factor_productivity{1.0};
    double capital_share{0.3};
    double capital_output_ratio{2.5};
    double demand_adjustment{0.0076};
    double income_adjustment{0.0076};
    double inventory_ratio{14.0};
    double inventory_gap_close{0.05};
    double markup_adjustment{6.7e-4};
    double markup_minimum{0.0};
    double markup_maximum{1.0};
    double wage_shortage_adjustment{0.0075};
    double wage_downward_drift{0.0075};
    double wage_calvo_probability{0.0};
    double price_calvo_probability{0.0};
    double income_propensity{0.8};
    double wealth_propensity{5.5e-5};
    double dividend_payout{0.5};
    double investment_adjustment{0.0019};
    double capital_depreciation{2.28e-4};
    double annual_tfp_growth{0.02};
    double profit_tax_rate{0.25};
    double income_tax_rate{0.20};
    double consumption_tax_rate{0.15};
    double wealth_tax_rate{5.479452054794521e-6};
    double government_consumption_share{0.20};
    double government_investment_share{0.04};
    double unemployment_benefit_replacement{0.40};
    double initial_household_money{100.0};
    double initial_firm_money{200.0};
    double initial_consumption_inventory{10.0};
    double initial_capital_inventory{5.0};
    double initial_consumption_capital{20.0};
    double initial_price{1.2};
    double initial_capital_price{1.2};
    double initial_wage{1.0};
    double initial_markup{0.2};
    double initial_expected_demand{10.0};
    std::uint32_t market_sample_size{1};

    bool operator==(const M4Rules&) const = default;
};

struct M4SimulationSpec final {
    M4Vertical vertical{M4Vertical::cash_loop};
    EconomyId economy{EconomyId(1)};
    CurrencyId currency{CurrencyId(1)};
    std::uint64_t households{1};
    std::uint64_t consumption_firms{1};
    std::uint64_t capital_firms{0};
    std::uint64_t seed{0};
    std::uint64_t requested_capabilities{0};
    bool stochastic{false};
    algorithms::MatchingProtocol market_protocol{
        algorithms::MatchingProtocol::sampled
    };
    M4Rules rules{};
};

struct M4Metrics final {
    Tick tick{};
    double real_output{0.0};
    double nominal_output{0.0};
    double price_index{0.0};
    double unemployment_rate{0.0};
    double total_money{0.0};
    double conservation_drift{0.0};
    double aggregate_capital{0.0};
    double household_consumption{0.0};
    double wages_paid{0.0};
    double firm_profit{0.0};
    double tax_total{0.0};
    double government_spending{0.0};
    double government_deficit{0.0};
    double public_capital{0.0};

    bool operator==(const M4Metrics&) const = default;
};

enum class M4Phase : std::uint8_t {
    open_books = 0,
    open_real_economy = 1,
    plan_and_finance = 2,
    labor = 3,
    production = 4,
    goods_market = 5,
    capital_market = 6,
    settle_domestic = 7,
    validate_and_measure = 8,
    stage_local_commit = 9,
};

struct M4PhaseSummary final {
    M4Phase phase{M4Phase::open_books};
    double money_total{0.0};
    double goods_total{0.0};
    double capital_total{0.0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};

    bool operator==(const M4PhaseSummary&) const = default;
};

struct M4AdvanceOptions final {
    bool capture_phase_trace{false};
    std::optional<M4Phase> fault_before_phase{};
};

struct M4AdvanceResult final {
    Tick first_tick{};
    Tick next_tick{};
    std::uint64_t advanced_ticks{0};
    M4Metrics metrics{};
    std::uint64_t scratch_capacity_signature{0};
    std::uint64_t transfer_count{0};
    std::uint64_t trade_count{0};
};

struct M4Runtime final {
    M4Vertical vertical{M4Vertical::cash_loop};
    std::uint64_t capability_mask{0};
    M4Rules rules{};
    algorithms::MatchingProtocol market_protocol{
        algorithms::MatchingProtocol::sampled
    };
    bool stochastic{false};
    PhiloxKey rng_key{};
    PhiloxCounter rng_counter{};
    double technology_index{1.0};
    double public_capital{0.0};
    double previous_nominal_output{0.0};
    M4Metrics last_metrics{};
    std::vector<M4PhaseSummary> last_phase_trace;
};

class M4TickScratch final {
public:
    M4TickScratch() = default;
    M4TickScratch(const M4TickScratch&) = delete;
    M4TickScratch& operator=(const M4TickScratch&) = delete;
    M4TickScratch(M4TickScratch&&) noexcept = default;
    M4TickScratch& operator=(M4TickScratch&&) noexcept = default;
    ~M4TickScratch() = default;

    void reserve(const core::RootState& state);
    [[nodiscard]] std::uint64_t capacity_signature() const noexcept;

    // Reusable implementation storage. This is intentionally exposed to the
    // translation-unit executor but is not part of the stable C ABI.
    struct HouseholdWork final {
        double income_expected{0.0};
        double income_realized{0.0};
        double consumption_budget{0.0};
        double spent{0.0};
        double labor_sold{0.0};
    };

    struct FirmWork final {
        double target_inventory{0.0};
        double production_target{0.0};
        double labor_demand_notional{0.0};
        double labor_demand_effective{0.0};
        double hired{0.0};
        double produced{0.0};
        double sales{0.0};
        double revenue{0.0};
        double wage_bill{0.0};
        double profit{0.0};
        double profit_tax{0.0};
        double dividends{0.0};
        double retained_earnings{0.0};
        double investment_target{0.0};
        double investment{0.0};
        double rationed_demand{0.0};
        double closing_inventory{0.0};
        double closing_capital{0.0};
        double posted_price{0.0};
        double posted_wage{0.0};
        double markup{0.0};
        double demand_expected{0.0};
    };

    std::vector<HouseholdId> household_ids_;
    std::vector<FirmId> firm_ids_;
    std::vector<std::size_t> consumption_firm_indices_;
    std::vector<std::size_t> capital_firm_indices_;
    std::vector<std::size_t> household_order_;
    std::vector<std::size_t> firm_order_;
    std::vector<double> balances_;
    std::vector<HouseholdWork> household_work_;
    std::vector<FirmWork> firm_work_;
    std::vector<algorithms::BuyOrder> orders_;
    std::vector<algorithms::SellOffer> offers_;
    std::vector<std::size_t> market_buyer_order_;
    std::vector<std::size_t> market_active_offers_;
    std::vector<double> market_offer_remaining_;
    algorithms::MarketClearing clearing_;
    std::vector<M4PhaseSummary> phase_trace_;
    std::uint64_t transfer_count_{0};
    std::uint64_t trade_count_{0};
};

struct M4Initialization final {
    core::RootState root;
    M4Runtime runtime;
};

[[nodiscard]] Status validate_spec(const M4SimulationSpec& spec) noexcept;
[[nodiscard]] Status validate_m4_state(
    const core::RootState& root,
    const M4Runtime& runtime,
    Tick tick
) noexcept;
[[nodiscard]] Result<M4Initialization> build_m4_genesis(
    const M4SimulationSpec& spec
);
[[nodiscard]] Result<M4AdvanceResult> advance_ticks(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    std::uint64_t count,
    const M4AdvanceOptions& options = {}
);
[[nodiscard]] Result<M4AdvanceResult> advance_tick(
    core::RootState& state,
    M4Runtime& runtime,
    M4TickScratch& scratch,
    Tick& tick,
    const M4AdvanceOptions& options = {}
);

}  // namespace macro_sim::simulation

#endif
