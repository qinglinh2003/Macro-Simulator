#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m7_checkpoint.hpp"

namespace {

using macro_sim::PhiloxRng;
using macro_sim::Status;
using macro_sim::Tick;
using macro_sim::core::RootState;
using namespace macro_sim::simulation;

[[nodiscard]] M7SimulationSpec spec() {
    M7SimulationSpec value;
    auto &real = value.financial_economy.monetary_economy.real_economy;
    real.vertical = M4Vertical::capital_fiscal;
    real.consumption_firms = 4;
    real.capital_firms = 2;
    real.seed = 808;
    real.requested_capabilities =
        capability_bit(M4Capability::physical_capital) |
        capability_bit(M4Capability::government);
    real.rules.initial_household_money = 30.0;
    real.rules.initial_firm_money = 6.0;
    real.rules.initial_consumption_inventory = 4.0;
    real.rules.initial_capital_inventory = 3.0;
    real.rules.initial_consumption_capital = 5.0;
    real.rules.initial_expected_demand = 8.0;
    real.rules.initial_wage = 1.5;
    real.rules.initial_price = 1.4;
    real.rules.initial_capital_price = 1.6;
    auto &monetary = value.financial_economy.monetary_economy;
    monetary.rules.bank_count = 2;
    monetary.rules.opening_capital_per_bank = 20.0;
    monetary.rules.bank_leverage_mean = 8.0;
    monetary.rules.interbank = true;
    monetary.rules.full_firm_pnl = true;
    monetary.rules.realized_bank_pnl = true;
    monetary.policy.bank_capital_constraint = true;
    monetary.policy.bank_leverage_cap = 8.0;
    value.financial_economy.policy.bank_minimum_capital = 12.0;
    value.financial_economy.rules.entry_beta = 0.0;
    value.financial_economy.rules.bank_entry_beta = 0.0;
    value.population.initial_persons = 80;
    value.population.target_household_size = 2.5;
    value.population.start_calendar_day = 20'000;
    value.rules.fertility = false;
    value.rules.mortality = false;
    value.rules.marriage = false;
    value.rules.divorce = false;
    value.rules.annual_churn = 0.0;
    return value;
}

struct Harness final {
    RootState root;
    M4Runtime real_runtime;
    M4TickScratch real_scratch;
    M5Runtime monetary_runtime;
    M5TickScratch monetary_scratch;
    M6Runtime financial_runtime;
    M6TickScratch financial_scratch;
    M7Runtime runtime;
    M7TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build() {
    auto initialization = build_m7_genesis(spec());
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness result{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.monetary_runtime),
        {},
        std::move(value.financial_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick(0),
    };
    result.real_scratch.reserve(result.root);
    result.monetary_scratch.reserve(result.root);
    result.financial_scratch.reserve(result.root, result.financial_runtime);
    result.scratch.reserve(result.runtime);
    return result;
}

class ProbeExtension final : public M7TickExtension {
  public:
    explicit ProbeExtension(std::optional<std::size_t> fail_at = {})
        : fail_at_(fail_at) {}

    Status prepare_tick(const RootState &, M4Runtime &, M4TickScratch &,
                        M5Runtime &, M5TickScratch &, M6Runtime &,
                        M6TickScratch &, M7Runtime &, M7TickScratch &, Tick,
                        PhiloxRng &) override {
        return visit(0);
    }

    Status after_labor(const RootState &, M4Runtime &, M4TickScratch &,
                       M5Runtime &, M5TickScratch &, M6Runtime &,
                       M6TickScratch &, M7Runtime &, M7TickScratch &, Tick,
                       PhiloxRng &) override {
        return visit(1);
    }

    Status close_day(const RootState &, M4Runtime &, M4TickScratch &,
                     M5Runtime &, M5TickScratch &, M6Runtime &,
                     M6TickScratch &, M7Runtime &, M7TickScratch &, Tick,
                     PhiloxRng &) override {
        return visit(2);
    }

    Status validate(const RootState &, const M4Runtime &,
                    const M4TickScratch &, const M5Runtime &,
                    const M5TickScratch &, const M6Runtime &,
                    const M6TickScratch &, const M7Runtime &,
                    const M7TickScratch &, Tick) const override {
        return const_cast<ProbeExtension *>(this)->visit(3);
    }

    void commit(RootState &, M4Runtime &, M4TickScratch &, M5Runtime &,
                M5TickScratch &, M6Runtime &, M6TickScratch &, M7Runtime &,
                M7TickScratch &, Tick, const M7Metrics &) noexcept override {
        phases.push_back(4);
    }

    std::vector<std::size_t> phases;

  private:
    [[nodiscard]] Status visit(std::size_t phase) {
        phases.push_back(phase);
        if (fail_at_.has_value() && *fail_at_ == phase) {
            return Status(macro_sim::ErrorCode::internal_error,
                          "M7 extension seam fault");
        }
        return Status::success();
    }

    std::optional<std::size_t> fail_at_;
};

[[nodiscard]] std::vector<std::uint8_t> checkpoint(const Harness &harness) {
    auto bytes = save_m7_checkpoint(
        harness.root, harness.real_runtime, harness.monetary_runtime,
        harness.financial_runtime, harness.runtime, harness.tick
    );
    assert(bytes.ok());
    return *bytes.get_if();
}

[[nodiscard]] macro_sim::Result<M7AdvanceResult>
advance_extended(Harness &harness, std::uint64_t count,
                 ProbeExtension &extension) {
    return advance_m7_ticks_extended(
        harness.root, harness.real_runtime, harness.real_scratch,
        harness.monetary_runtime, harness.monetary_scratch,
        harness.financial_runtime, harness.financial_scratch, harness.runtime,
        harness.scratch, harness.tick, count, extension
    );
}

void test_phase_order() {
    auto harness = build();
    ProbeExtension extension;
    const auto result = advance_extended(harness, 1, extension);
    assert(result.ok());
    assert(harness.tick == Tick(1));
    assert(extension.phases ==
           std::vector<std::size_t>({0, 1, 2, 3, 4}));
}

void test_failure_is_atomic_at_every_fallible_boundary() {
    for (std::size_t phase = 0; phase < 4; ++phase) {
        auto harness = build();
        const auto before = checkpoint(harness);
        ProbeExtension extension(phase);
        const auto result = advance_extended(harness, 1, extension);
        assert(!result.ok());
        assert(harness.tick == Tick(0));
        assert(checkpoint(harness) == before);
        assert(extension.phases.size() == phase + 1);
    }
}

void test_noop_extension_preserves_m7() {
    auto direct = build();
    auto extended = build();
    const auto direct_result = advance_m7_ticks(
        direct.root, direct.real_runtime, direct.real_scratch,
        direct.monetary_runtime, direct.monetary_scratch,
        direct.financial_runtime, direct.financial_scratch, direct.runtime,
        direct.scratch, direct.tick, 20
    );
    ProbeExtension extension;
    const auto extended_result = advance_extended(extended, 20, extension);
    assert(direct_result.ok());
    assert(extended_result.ok());
    assert(checkpoint(direct) == checkpoint(extended));
    assert(extension.phases.size() == 20 * 5);
}

} // namespace

int main() {
    test_phase_order();
    test_failure_is_atomic_at_every_fallible_boundary();
    test_noop_extension_preserves_m7();
    return 0;
}
