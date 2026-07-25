#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

#include "macro_sim/simulation/m5.hpp"
#include "macro_sim/simulation/m5_checkpoint.hpp"

namespace {

using macro_sim::PhiloxRng;
using macro_sim::Status;
using macro_sim::Tick;
using macro_sim::core::RootState;
using macro_sim::simulation::M4Capability;
using macro_sim::simulation::M4Runtime;
using macro_sim::simulation::M4TickScratch;
using macro_sim::simulation::M4Vertical;
using macro_sim::simulation::M5Metrics;
using macro_sim::simulation::M5Runtime;
using macro_sim::simulation::M5SimulationSpec;
using macro_sim::simulation::M5TickExtension;
using macro_sim::simulation::M5TickScratch;
using macro_sim::simulation::capability_bit;

[[nodiscard]] M5SimulationSpec spec() {
    M5SimulationSpec value;
    value.real_economy.vertical = M4Vertical::capital_fiscal;
    value.real_economy.households = 16;
    value.real_economy.consumption_firms = 3;
    value.real_economy.capital_firms = 1;
    value.real_economy.seed = 606;
    value.real_economy.requested_capabilities =
        capability_bit(M4Capability::physical_capital)
        | capability_bit(M4Capability::government);
    value.real_economy.rules.initial_household_money = 20.0;
    value.real_economy.rules.initial_firm_money = 4.0;
    value.real_economy.rules.initial_consumption_inventory = 3.0;
    value.real_economy.rules.initial_capital_inventory = 3.0;
    value.real_economy.rules.initial_consumption_capital = 5.0;
    value.real_economy.rules.initial_expected_demand = 8.0;
    value.real_economy.rules.initial_wage = 1.5;
    value.real_economy.rules.initial_price = 1.4;
    value.real_economy.rules.initial_capital_price = 1.6;
    value.rules.bank_count = 2;
    value.rules.opening_capital_per_bank = 20.0;
    value.policy.bank_capital_constraint = true;
    value.policy.bank_leverage_cap = 10.0;
    return value;
}

struct Harness final {
    RootState root;
    M4Runtime real_runtime;
    M4TickScratch real_scratch;
    M5Runtime runtime;
    M5TickScratch scratch;
    Tick tick{};
};

[[nodiscard]] Harness build() {
    auto initialization = macro_sim::simulation::build_m5_genesis(spec());
    assert(initialization.ok());
    auto value = std::move(*initialization.get_if());
    Harness result{
        std::move(value.root),
        std::move(value.real_economy_runtime),
        {},
        std::move(value.runtime),
        {},
        Tick(0),
    };
    result.real_scratch.reserve(result.root);
    result.scratch.reserve(result.root);
    return result;
}

class ProbeExtension final : public M5TickExtension {
public:
    explicit ProbeExtension(std::optional<std::size_t> fail_at = {})
        : fail_at_(fail_at) {}

    Status prepare_tick(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(0);
    }

    Status after_planning(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(1);
    }

    Status run_labor(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&,
        bool& handled
    ) override {
        handled = false;
        return Status::success();
    }

    Status before_settlement(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(2);
    }

    Status after_settlement(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(3);
    }

    Status before_bank_resolution(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(4);
    }

    Status close_institutions(
        const RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        PhiloxRng&
    ) override {
        return visit(5);
    }

    Status validate(
        const RootState&,
        const M4Runtime&,
        const M4TickScratch&,
        const M5Runtime&,
        const M5TickScratch&,
        Tick
    ) const override {
        return const_cast<ProbeExtension*>(this)->visit(6);
    }

    void commit(
        RootState&,
        M4Runtime&,
        M4TickScratch&,
        M5Runtime&,
        M5TickScratch&,
        Tick,
        const M5Metrics&
    ) noexcept override {
        phases.push_back(7);
    }

    std::vector<std::size_t> phases;

private:
    [[nodiscard]] Status visit(std::size_t phase) {
        phases.push_back(phase);
        if (fail_at_.has_value() && *fail_at_ == phase) {
            return Status(
                macro_sim::ErrorCode::internal_error,
                "extension seam fault"
            );
        }
        return Status::success();
    }

    std::optional<std::size_t> fail_at_;
};

[[nodiscard]] std::vector<std::uint8_t> checkpoint(const Harness& harness) {
    auto bytes = macro_sim::simulation::save_m5_checkpoint(
        harness.root,
        harness.real_runtime,
        harness.runtime,
        harness.tick
    );
    assert(bytes.ok());
    return *bytes.get_if();
}

void test_phase_order() {
    auto harness = build();
    ProbeExtension extension;
    const auto result = macro_sim::simulation::advance_m5_ticks_extended(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1,
        extension
    );
    assert(result.ok());
    assert(harness.tick == Tick(1));
    assert(
        extension.phases
        == std::vector<std::size_t>({0, 1, 2, 3, 4, 5, 6, 7})
    );
}

void test_failure_is_atomic() {
    auto harness = build();
    const auto before = checkpoint(harness);
    ProbeExtension extension(4);
    const auto result = macro_sim::simulation::advance_m5_ticks_extended(
        harness.root,
        harness.real_runtime,
        harness.real_scratch,
        harness.runtime,
        harness.scratch,
        harness.tick,
        1,
        extension
    );
    assert(!result.ok());
    assert(harness.tick == Tick(0));
    assert(checkpoint(harness) == before);
    assert(
        extension.phases
        == std::vector<std::size_t>({0, 1, 2, 3, 4})
    );
}

void test_noop_extension_preserves_m5() {
    auto direct = build();
    auto extended = build();
    const auto direct_result = macro_sim::simulation::advance_m5_ticks(
        direct.root,
        direct.real_runtime,
        direct.real_scratch,
        direct.runtime,
        direct.scratch,
        direct.tick,
        20
    );
    ProbeExtension extension;
    const auto extended_result =
        macro_sim::simulation::advance_m5_ticks_extended(
            extended.root,
            extended.real_runtime,
            extended.real_scratch,
            extended.runtime,
            extended.scratch,
            extended.tick,
            20,
            extension
        );
    assert(direct_result.ok());
    assert(extended_result.ok());
    assert(checkpoint(direct) == checkpoint(extended));
    assert(extension.phases.size() == 20 * 8);
}

}  // namespace

int main() {
    test_phase_order();
    test_failure_is_atomic();
    test_noop_extension_preserves_m5();
    return 0;
}
