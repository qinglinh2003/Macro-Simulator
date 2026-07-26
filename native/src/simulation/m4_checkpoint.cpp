#include "macro_sim/simulation/m4_checkpoint.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <utility>
#include <vector>

#include "macro_sim/core/checkpoint.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/invariants.hpp"

namespace macro_sim::simulation {
namespace {

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '4', 'C', 'P', '0', '1',
};
constexpr std::size_t kDigestBytes = 32;
constexpr std::size_t kMaximumCheckpointBytes = 128U * 1024U * 1024U;

class Writer final {
public:
    void u8(std::uint8_t value) {
        bytes_.push_back(value);
    }

    void boolean(bool value) {
        u8(value ? 1U : 0U);
    }

    void u32(std::uint32_t value) {
        for (int shift = 24; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void u64(std::uint64_t value) {
        for (int shift = 56; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void f64(double value) {
        u64(std::bit_cast<std::uint64_t>(value));
    }

    void raw(std::span<const std::uint8_t> bytes) {
        bytes_.insert(bytes_.end(), bytes.begin(), bytes.end());
    }

    [[nodiscard]] std::vector<std::uint8_t>& bytes() noexcept {
        return bytes_;
    }

    [[nodiscard]] std::vector<std::uint8_t> take() && {
        return std::move(bytes_);
    }

private:
    std::vector<std::uint8_t> bytes_;
};

class Reader final {
public:
    explicit Reader(std::span<const std::uint8_t> bytes) noexcept
        : bytes_(bytes) {}

    [[nodiscard]] bool u8(std::uint8_t& value) noexcept {
        if (remaining() < 1) {
            return false;
        }
        value = bytes_[position_++];
        return true;
    }

    [[nodiscard]] bool boolean(bool& value) noexcept {
        std::uint8_t encoded = 0;
        if (!u8(encoded) || encoded > 1U) {
            return false;
        }
        value = encoded != 0;
        return true;
    }

    [[nodiscard]] bool u32(std::uint32_t& value) noexcept {
        if (remaining() < 4) {
            return false;
        }
        value = 0;
        for (int index = 0; index < 4; ++index) {
            value = static_cast<std::uint32_t>(
                (value << 8U) | bytes_[position_++]
            );
        }
        return true;
    }

    [[nodiscard]] bool u64(std::uint64_t& value) noexcept {
        if (remaining() < 8) {
            return false;
        }
        value = 0;
        for (int index = 0; index < 8; ++index) {
            value = (value << 8U) | bytes_[position_++];
        }
        return true;
    }

    [[nodiscard]] bool f64(double& value) noexcept {
        std::uint64_t bits = 0;
        if (!u64(bits)) {
            return false;
        }
        value = std::bit_cast<double>(bits);
        return std::isfinite(value);
    }

    [[nodiscard]] bool raw(
        std::size_t size,
        std::span<const std::uint8_t>& value
    ) noexcept {
        if (remaining() < size) {
            return false;
        }
        value = bytes_.subspan(position_, size);
        position_ += size;
        return true;
    }

    [[nodiscard]] std::size_t remaining() const noexcept {
        return bytes_.size() - position_;
    }

private:
    std::span<const std::uint8_t> bytes_;
    std::size_t position_{0};
};

void write_rules(Writer& writer, const M4Rules& rules) {
    writer.f64(rules.linear_productivity);
    writer.f64(rules.capital_productivity);
    writer.f64(rules.total_factor_productivity);
    writer.f64(rules.capital_share);
    writer.f64(rules.capital_output_ratio);
    writer.f64(rules.demand_adjustment);
    writer.f64(rules.income_adjustment);
    writer.f64(rules.inventory_ratio);
    writer.f64(rules.inventory_gap_close);
    writer.f64(rules.markup_adjustment);
    writer.f64(rules.markup_minimum);
    writer.f64(rules.markup_maximum);
    writer.f64(rules.wage_shortage_adjustment);
    writer.f64(rules.wage_downward_drift);
    writer.f64(rules.wage_calvo_probability);
    writer.f64(rules.price_calvo_probability);
    writer.f64(rules.income_propensity);
    writer.f64(rules.wealth_propensity);
    writer.f64(rules.dividend_payout);
    writer.f64(rules.investment_adjustment);
    writer.f64(rules.capital_depreciation);
    writer.f64(rules.annual_tfp_growth);
    writer.f64(rules.profit_tax_rate);
    writer.f64(rules.income_tax_rate);
    writer.f64(rules.consumption_tax_rate);
    writer.u8(rules.necessity_consumption_tax_rate.has_value() ? 1U : 0U);
    writer.f64(rules.necessity_consumption_tax_rate.value_or(0.0));
    writer.u8(rules.luxury_consumption_tax_rate.has_value() ? 1U : 0U);
    writer.f64(rules.luxury_consumption_tax_rate.value_or(0.0));
    writer.f64(rules.wealth_tax_rate);
    writer.f64(rules.government_consumption_share);
    writer.f64(rules.government_deficit_target);
    writer.f64(rules.deficit_unemployment_reference);
    writer.f64(rules.deficit_unemployment_cap);
    writer.f64(rules.government_investment_share);
    writer.f64(rules.unemployment_benefit_replacement);
    writer.f64(rules.income_allowance);
    writer.f64(rules.wealth_allowance);
    writer.f64(rules.benefit_income_floor);
    writer.f64(rules.minimum_wage);
    writer.u8(rules.job_guarantee ? 1U : 0U);
    writer.f64(rules.job_guarantee_wage_ratio);
    writer.f64(rules.job_guarantee_public_works_share);
    writer.f64(rules.initial_household_money);
    writer.f64(rules.initial_firm_money);
    writer.f64(rules.initial_bank_capital);
    writer.f64(rules.initial_consumption_inventory);
    writer.f64(rules.initial_capital_inventory);
    writer.f64(rules.initial_consumption_capital);
    writer.f64(rules.initial_price);
    writer.f64(rules.initial_capital_price);
    writer.f64(rules.initial_wage);
    writer.f64(rules.initial_markup);
    writer.f64(rules.initial_expected_demand);
    writer.u32(rules.market_sample_size);
}

[[nodiscard]] bool read_rules(Reader& reader, M4Rules& rules) noexcept {
    std::uint8_t job_guarantee = 0;
    std::uint8_t necessity_tax_present = 0;
    std::uint8_t luxury_tax_present = 0;
    double necessity_tax = 0.0;
    double luxury_tax = 0.0;
    const auto success = reader.f64(rules.linear_productivity)
        && reader.f64(rules.capital_productivity)
        && reader.f64(rules.total_factor_productivity)
        && reader.f64(rules.capital_share)
        && reader.f64(rules.capital_output_ratio)
        && reader.f64(rules.demand_adjustment)
        && reader.f64(rules.income_adjustment)
        && reader.f64(rules.inventory_ratio)
        && reader.f64(rules.inventory_gap_close)
        && reader.f64(rules.markup_adjustment)
        && reader.f64(rules.markup_minimum)
        && reader.f64(rules.markup_maximum)
        && reader.f64(rules.wage_shortage_adjustment)
        && reader.f64(rules.wage_downward_drift)
        && reader.f64(rules.wage_calvo_probability)
        && reader.f64(rules.price_calvo_probability)
        && reader.f64(rules.income_propensity)
        && reader.f64(rules.wealth_propensity)
        && reader.f64(rules.dividend_payout)
        && reader.f64(rules.investment_adjustment)
        && reader.f64(rules.capital_depreciation)
        && reader.f64(rules.annual_tfp_growth)
        && reader.f64(rules.profit_tax_rate)
        && reader.f64(rules.income_tax_rate)
        && reader.f64(rules.consumption_tax_rate)
        && reader.u8(necessity_tax_present)
        && reader.f64(necessity_tax)
        && reader.u8(luxury_tax_present)
        && reader.f64(luxury_tax)
        && reader.f64(rules.wealth_tax_rate)
        && reader.f64(rules.government_consumption_share)
        && reader.f64(rules.government_deficit_target)
        && reader.f64(rules.deficit_unemployment_reference)
        && reader.f64(rules.deficit_unemployment_cap)
        && reader.f64(rules.government_investment_share)
        && reader.f64(rules.unemployment_benefit_replacement)
        && reader.f64(rules.income_allowance)
        && reader.f64(rules.wealth_allowance)
        && reader.f64(rules.benefit_income_floor)
        && reader.f64(rules.minimum_wage)
        && reader.u8(job_guarantee)
        && reader.f64(rules.job_guarantee_wage_ratio)
        && reader.f64(rules.job_guarantee_public_works_share)
        && reader.f64(rules.initial_household_money)
        && reader.f64(rules.initial_firm_money)
        && reader.f64(rules.initial_bank_capital)
        && reader.f64(rules.initial_consumption_inventory)
        && reader.f64(rules.initial_capital_inventory)
        && reader.f64(rules.initial_consumption_capital)
        && reader.f64(rules.initial_price)
        && reader.f64(rules.initial_capital_price)
        && reader.f64(rules.initial_wage)
        && reader.f64(rules.initial_markup)
        && reader.f64(rules.initial_expected_demand)
        && reader.u32(rules.market_sample_size);
    rules.job_guarantee = job_guarantee != 0;
    rules.necessity_consumption_tax_rate =
        necessity_tax_present != 0U ? std::optional<double>(necessity_tax)
                                    : std::nullopt;
    rules.luxury_consumption_tax_rate =
        luxury_tax_present != 0U ? std::optional<double>(luxury_tax)
                                 : std::nullopt;
    return success && job_guarantee <= 1U;
}

void write_metrics(Writer& writer, const M4Metrics& metrics) {
    writer.u64(metrics.tick.value());
    writer.f64(metrics.real_output);
    writer.f64(metrics.nominal_output);
    writer.f64(metrics.price_index);
    writer.f64(metrics.unemployment_rate);
    writer.f64(metrics.total_money);
    writer.f64(metrics.conservation_drift);
    writer.f64(metrics.aggregate_capital);
    writer.f64(metrics.household_consumption);
    writer.f64(metrics.wages_paid);
    writer.f64(metrics.firm_profit);
    writer.f64(metrics.tax_total);
    writer.f64(metrics.government_spending);
    writer.f64(metrics.government_deficit);
    writer.f64(metrics.public_capital);
    writer.f64(metrics.gross_output_nominal);
    writer.f64(metrics.consumption_output_nominal);
    writer.f64(metrics.capital_output_nominal);
    writer.f64(metrics.consumption_output_real);
    writer.f64(metrics.capital_output_real);
    writer.f64(metrics.inventory_change_nominal);
    writer.f64(metrics.inventory_change_real);
    writer.f64(metrics.fixed_capital_formation_nominal);
    writer.f64(metrics.fixed_capital_formation_real);
    writer.f64(metrics.government_consumption);
    writer.f64(metrics.public_fixed_capital_formation);
    writer.f64(metrics.transfer_payments);
}

[[nodiscard]] bool read_metrics(
    Reader& reader,
    M4Metrics& metrics
) noexcept {
    std::uint64_t tick = 0;
    if (!reader.u64(tick)) {
        return false;
    }
    metrics.tick = Tick(tick);
    return reader.f64(metrics.real_output)
        && reader.f64(metrics.nominal_output)
        && reader.f64(metrics.price_index)
        && reader.f64(metrics.unemployment_rate)
        && reader.f64(metrics.total_money)
        && reader.f64(metrics.conservation_drift)
        && reader.f64(metrics.aggregate_capital)
        && reader.f64(metrics.household_consumption)
        && reader.f64(metrics.wages_paid)
        && reader.f64(metrics.firm_profit)
        && reader.f64(metrics.tax_total)
        && reader.f64(metrics.government_spending)
        && reader.f64(metrics.government_deficit)
        && reader.f64(metrics.public_capital)
        && reader.f64(metrics.gross_output_nominal)
        && reader.f64(metrics.consumption_output_nominal)
        && reader.f64(metrics.capital_output_nominal)
        && reader.f64(metrics.consumption_output_real)
        && reader.f64(metrics.capital_output_real)
        && reader.f64(metrics.inventory_change_nominal)
        && reader.f64(metrics.inventory_change_real)
        && reader.f64(metrics.fixed_capital_formation_nominal)
        && reader.f64(metrics.fixed_capital_formation_real)
        && reader.f64(metrics.government_consumption)
        && reader.f64(metrics.public_fixed_capital_formation)
        && reader.f64(metrics.transfer_payments);
}

void write_household(
    Writer& writer,
    HouseholdId id,
    const core::HouseholdComponent& household
) {
    writer.u64(id.value());
    writer.f64(household.income_propensity);
    writer.f64(household.wealth_propensity);
    writer.f64(household.income_adjustment);
    writer.f64(household.income_expected);
    writer.f64(household.income_realized);
    writer.f64(household.consumption_budget);
    writer.f64(household.spent);
    writer.f64(household.labor_sold);
}

[[nodiscard]] bool read_household(
    Reader& reader,
    core::RootState& root
) noexcept {
    std::uint64_t id = 0;
    if (!reader.u64(id)) {
        return false;
    }
    auto* household = root.households.get(HouseholdId(id));
    return household != nullptr
        && reader.f64(household->income_propensity)
        && reader.f64(household->wealth_propensity)
        && reader.f64(household->income_adjustment)
        && reader.f64(household->income_expected)
        && reader.f64(household->income_realized)
        && reader.f64(household->consumption_budget)
        && reader.f64(household->spent)
        && reader.f64(household->labor_sold);
}

void write_firm(
    Writer& writer,
    FirmId id,
    const core::FirmComponent& firm
) {
    writer.u64(id.value());
    writer.u8(static_cast<std::uint8_t>(firm.technology));
    writer.f64(firm.total_factor_productivity);
    writer.f64(firm.capital_share);
    writer.f64(firm.capital_output_ratio);
    writer.f64(firm.investment_adjustment);
    writer.f64(firm.capital_depreciation);
    writer.f64(firm.demand_adjustment);
    writer.f64(firm.inventory_ratio);
    writer.f64(firm.markup_adjustment);
    writer.f64(firm.markup_minimum);
    writer.f64(firm.markup_maximum);
    writer.f64(firm.shortage_adjustment);
    writer.f64(firm.dividend_payout);
    writer.f64(firm.posted_price.value());
    writer.f64(firm.posted_wage.value());
    writer.f64(firm.markup);
    writer.f64(firm.demand_expected);
    writer.f64(firm.target_inventory_previous);
    writer.f64(firm.labor_demand_previous);
    writer.f64(firm.hired_previous);
    writer.f64(firm.sales_previous);
    writer.f64(firm.rationed_previous);
}

[[nodiscard]] bool read_firm(
    Reader& reader,
    core::RootState& root
) noexcept {
    std::uint64_t id = 0;
    std::uint8_t technology = 0;
    if (!reader.u64(id) || !reader.u8(technology)
        || technology
            > static_cast<std::uint8_t>(
                core::FirmTechnology::cobb_douglas
            )) {
        return false;
    }
    auto* firm = root.firms.get(FirmId(id));
    double price = 0.0;
    double wage = 0.0;
    if (firm == nullptr
        || !reader.f64(firm->total_factor_productivity)
        || !reader.f64(firm->capital_share)
        || !reader.f64(firm->capital_output_ratio)
        || !reader.f64(firm->investment_adjustment)
        || !reader.f64(firm->capital_depreciation)
        || !reader.f64(firm->demand_adjustment)
        || !reader.f64(firm->inventory_ratio)
        || !reader.f64(firm->markup_adjustment)
        || !reader.f64(firm->markup_minimum)
        || !reader.f64(firm->markup_maximum)
        || !reader.f64(firm->shortage_adjustment)
        || !reader.f64(firm->dividend_payout)
        || !reader.f64(price)
        || !reader.f64(wage)
        || !reader.f64(firm->markup)
        || !reader.f64(firm->demand_expected)
        || !reader.f64(firm->target_inventory_previous)
        || !reader.f64(firm->labor_demand_previous)
        || !reader.f64(firm->hired_previous)
        || !reader.f64(firm->sales_previous)
        || !reader.f64(firm->rationed_previous)) {
        return false;
    }
    firm->technology = static_cast<core::FirmTechnology>(technology);
    firm->posted_price = Price(price);
    firm->posted_wage = Money(wage);
    return true;
}

[[nodiscard]] Status corrupt(const char* message) noexcept {
    return Status(ErrorCode::corrupt_input, message);
}

}  // namespace

bool is_m4_checkpoint(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= kMagic.size()
        && std::equal(kMagic.begin(), kMagic.end(), bytes.begin());
}

Result<std::vector<std::uint8_t>> save_m4_checkpoint(
    const core::RootState& root,
    const M4Runtime& runtime,
    Tick tick
) {
    if (!core::run_invariants(root).ok()
        || !validate_m4_state(root, runtime, tick).ok()) {
        return Status(
            ErrorCode::invariant_violation,
            "M4 checkpoint root violates an invariant"
        );
    }
    auto base = core::save_checkpoint(root);
    if (!base.ok()) {
        return base.status();
    }
    Writer writer;
    writer.raw(kMagic);
    writer.u32(kM4CheckpointSchemaVersion);
    writer.u64(tick.value());
    writer.u64(root.institutions.clearing_account.value());
    writer.u8(static_cast<std::uint8_t>(runtime.vertical));
    writer.u64(runtime.capability_mask);
    writer.u8(static_cast<std::uint8_t>(runtime.market_protocol));
    writer.boolean(runtime.stochastic);
    for (const auto value : runtime.rng_key) {
        writer.u32(value);
    }
    for (const auto value : runtime.rng_counter) {
        writer.u32(value);
    }
    writer.f64(runtime.technology_index);
    writer.f64(runtime.public_capital);
    writer.f64(runtime.previous_nominal_output);
    write_rules(writer, runtime.rules);
    write_metrics(writer, runtime.last_metrics);
    writer.u64(runtime.last_phase_trace.size());
    for (const auto& phase : runtime.last_phase_trace) {
        writer.u8(static_cast<std::uint8_t>(phase.phase));
        writer.f64(phase.money_total);
        writer.f64(phase.goods_total);
        writer.f64(phase.capital_total);
        writer.u64(phase.transfer_count);
        writer.u64(phase.trade_count);
    }
    writer.u64(root.households.alive_count());
    root.households.for_each_alive(
        [&writer](HouseholdId id, const core::HouseholdComponent& value) {
            write_household(writer, id, value);
        }
    );
    writer.u64(root.firms.alive_count());
    root.firms.for_each_alive(
        [&writer](FirmId id, const core::FirmComponent& value) {
            write_firm(writer, id, value);
        }
    );
    writer.u64(base.get_if()->size());
    writer.raw(*base.get_if());
    auto& payload = writer.bytes();
    const auto digest = core::sha256_digest(payload);
    writer.raw(digest.bytes);
    auto output = std::move(writer).take();
    if (output.size() > kMaximumCheckpointBytes) {
        return Status(
            ErrorCode::out_of_range,
            "M4 checkpoint exceeds the supported size"
        );
    }
    return output;
}

Result<M4Checkpoint> load_m4_checkpoint(
    std::span<const std::uint8_t> bytes
) {
    if (bytes.size() > kMaximumCheckpointBytes
        || bytes.size() < kMagic.size() + 4 + kDigestBytes
        || !is_m4_checkpoint(bytes)) {
        return corrupt("M4 checkpoint identity or size is invalid");
    }
    const auto payload = bytes.first(bytes.size() - kDigestBytes);
    const auto expected = core::sha256_digest(payload);
    if (!std::equal(
            expected.bytes.begin(),
            expected.bytes.end(),
            bytes.end() - static_cast<std::ptrdiff_t>(kDigestBytes)
        )) {
        return corrupt("M4 checkpoint checksum does not match");
    }
    Reader reader(payload.subspan(kMagic.size()));
    std::uint32_t version = 0;
    std::uint64_t tick = 0;
    std::uint64_t clearing_account = 0;
    std::uint8_t vertical = 0;
    std::uint8_t protocol = 0;
    bool stochastic = false;
    M4Runtime runtime;
    if (!reader.u32(version) || version != kM4CheckpointSchemaVersion
        || !reader.u64(tick)
        || !reader.u64(clearing_account)
        || !reader.u8(vertical)
        || vertical > static_cast<std::uint8_t>(M4Vertical::capital_fiscal)
        || !reader.u64(runtime.capability_mask)
        || !reader.u8(protocol)
        || protocol
            > static_cast<std::uint8_t>(
                algorithms::MatchingProtocol::price_sorted
            )
        || !reader.boolean(stochastic)) {
        return corrupt("M4 checkpoint header is invalid");
    }
    runtime.vertical = static_cast<M4Vertical>(vertical);
    runtime.market_protocol =
        static_cast<algorithms::MatchingProtocol>(protocol);
    runtime.stochastic = stochastic;
    for (auto& value : runtime.rng_key) {
        if (!reader.u32(value)) {
            return corrupt("M4 checkpoint RNG key is truncated");
        }
    }
    for (auto& value : runtime.rng_counter) {
        if (!reader.u32(value)) {
            return corrupt("M4 checkpoint RNG counter is truncated");
        }
    }
    if (!reader.f64(runtime.technology_index)
        || !reader.f64(runtime.public_capital)
        || !reader.f64(runtime.previous_nominal_output)
        || !read_rules(reader, runtime.rules)
        || !read_metrics(reader, runtime.last_metrics)) {
        return corrupt("M4 checkpoint runtime is invalid");
    }
    std::uint64_t phase_count = 0;
    if (!reader.u64(phase_count) || phase_count > 32) {
        return corrupt("M4 checkpoint phase trace is invalid");
    }
    runtime.last_phase_trace.reserve(static_cast<std::size_t>(phase_count));
    for (std::uint64_t index = 0; index < phase_count; ++index) {
        std::uint8_t phase = 0;
        M4PhaseSummary summary;
        if (!reader.u8(phase)
            || phase
                > static_cast<std::uint8_t>(M4Phase::stage_local_commit)
            || !reader.f64(summary.money_total)
            || !reader.f64(summary.goods_total)
            || !reader.f64(summary.capital_total)
            || !reader.u64(summary.transfer_count)
            || !reader.u64(summary.trade_count)) {
            return corrupt("M4 checkpoint phase trace is truncated");
        }
        summary.phase = static_cast<M4Phase>(phase);
        runtime.last_phase_trace.push_back(summary);
    }
    std::uint64_t household_count = 0;
    if (!reader.u64(household_count) || household_count > 10'000'000) {
        return corrupt("M4 checkpoint household count is invalid");
    }
    const auto household_bytes = static_cast<std::size_t>(household_count)
        * (8U + 8U * 8U);
    std::span<const std::uint8_t> encoded_households;
    if (!reader.raw(household_bytes, encoded_households)) {
        return corrupt("M4 checkpoint households are truncated");
    }
    std::uint64_t firm_count = 0;
    if (!reader.u64(firm_count) || firm_count > 10'000'000) {
        return corrupt("M4 checkpoint firm count is invalid");
    }
    const auto firm_record_bytes = 8U + 1U + 21U * 8U;
    const auto firm_bytes =
        static_cast<std::size_t>(firm_count) * firm_record_bytes;
    std::span<const std::uint8_t> encoded_firms;
    if (!reader.raw(firm_bytes, encoded_firms)) {
        return corrupt("M4 checkpoint firms are truncated");
    }
    std::uint64_t base_size = 0;
    std::span<const std::uint8_t> base;
    if (!reader.u64(base_size)
        || base_size > kMaximumCheckpointBytes
        || !reader.raw(static_cast<std::size_t>(base_size), base)
        || reader.remaining() != 0) {
        return corrupt("M4 checkpoint base state is invalid");
    }
    auto loaded = core::load_checkpoint(base);
    if (!loaded.ok()) {
        return loaded.status();
    }
    auto root = std::move(*loaded.get_if());
    if (root.households.alive_count() != household_count
        || root.firms.alive_count() != firm_count) {
        return corrupt("M4 checkpoint projections do not match base state");
    }
    root.institutions.clearing_account = AccountId(clearing_account);
    Reader household_reader(encoded_households);
    for (std::uint64_t index = 0; index < household_count; ++index) {
        if (!read_household(household_reader, root)) {
            return corrupt("M4 checkpoint household state is invalid");
        }
    }
    Reader firm_reader(encoded_firms);
    for (std::uint64_t index = 0; index < firm_count; ++index) {
        if (!read_firm(firm_reader, root)) {
            return corrupt("M4 checkpoint firm state is invalid");
        }
    }
    std::uint64_t consumption_firms = 0;
    std::uint64_t capital_firms = 0;
    root.firms.for_each_alive(
        [&consumption_firms, &capital_firms](
            FirmId,
            const core::FirmComponent& firm
        ) {
            if (firm.sector == core::FirmSector::consumption) {
                ++consumption_firms;
            } else if (firm.sector == core::FirmSector::capital) {
                ++capital_firms;
            }
        }
    );
    M4SimulationSpec spec;
    spec.vertical = runtime.vertical;
    spec.economy = root.economy;
    spec.currency = root.currency;
    spec.households = household_count;
    spec.consumption_firms = consumption_firms;
    spec.capital_firms = capital_firms;
    spec.settlement_banks = root.banks.alive_count();
    spec.seed = root.seed;
    spec.requested_capabilities = runtime.capability_mask;
    spec.stochastic = runtime.stochastic;
    spec.market_protocol = runtime.market_protocol;
    spec.rules = runtime.rules;
    if (!validate_spec(spec).ok() || !core::run_invariants(root).ok()
        || !validate_m4_state(root, runtime, Tick(tick)).ok()) {
        return corrupt("M4 checkpoint restored state is invalid");
    }
    return M4Checkpoint{
        std::move(root),
        std::move(runtime),
        Tick(tick),
    };
}

}  // namespace macro_sim::simulation
