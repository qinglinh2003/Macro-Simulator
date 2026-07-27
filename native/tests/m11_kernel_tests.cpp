#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/control/m11_kernel.hpp"

namespace {

using macro_sim::EconomyId;
using macro_sim::ErrorCode;
using macro_sim::Tick;
using macro_sim::control::M11AdjustmentCostSpec;
using macro_sim::control::M11ControllerEvent;
using macro_sim::control::M11EventStream;
using macro_sim::control::M11EventVisibility;
using macro_sim::control::M11MetricSample;
using macro_sim::control::M11PolicyChange;
using macro_sim::control::M11ReleaseRecord;
using macro_sim::control::M11ReleaseStream;

void test_default_contract() {
    auto scheduler = macro_sim::control::M11DecisionScheduler::create();
    assert(scheduler.ok());
    const auto &value = *scheduler.get_if();
    assert(value.calendars().size() == macro_sim::control::kM11DecisionGroupCount);
    assert(value.triggers().size() == macro_sim::control::kM11DefaultTriggerCount);
    assert(value.due("monetary_stance", Tick(0U)));
    assert(value.due("monetary_stance", Tick(45U)));
    assert(!value.due("monetary_stance", Tick(44U)));
    auto capacity = value.administrative_capacity("tax_and_transfers");
    assert(capacity.ok());
    assert(*capacity.get_if() == 25.0);

    const auto calendars = macro_sim::control::m11_default_calendars();
    assert(calendars.size() == 11U);
    for (const auto &calendar : calendars) {
        assert(macro_sim::control::validate_m11_calendar(calendar).ok());
    }
    const auto triggers = macro_sim::control::m11_default_triggers();
    assert(triggers.size() == 8U);
    for (const auto &trigger : triggers) {
        assert(macro_sim::control::validate_m11_trigger(trigger).ok());
    }
}

void test_trigger_hysteresis() {
    auto built = macro_sim::control::M11DecisionScheduler::create();
    assert(built.ok());
    auto scheduler = std::move(*built.get_if());
    const std::vector<M11MetricSample> high{{
        "reserve_floor_breach_share",
        0.15,
    }};
    auto first = scheduler.evaluate_triggers(Tick(10U), EconomyId(0U), high);
    assert(first.ok());
    assert(first.get_if()->empty());
    auto second = scheduler.evaluate_triggers(Tick(11U), EconomyId(0U), high);
    assert(second.ok());
    assert(second.get_if()->size() == 1U);
    assert(second.get_if()->front().trigger_id == "bank_liquidity_stress");
    assert(second.get_if()->front().expires_at == Tick(12U));

    auto held = scheduler.evaluate_triggers(Tick(12U), EconomyId(0U), high);
    assert(held.ok());
    assert(held.get_if()->empty());
    const std::vector<M11MetricSample> low{{
        "reserve_floor_breach_share",
        0.01,
    }};
    auto exited = scheduler.evaluate_triggers(Tick(13U), EconomyId(0U), low);
    assert(exited.ok());
    assert(exited.get_if()->empty());
    auto cooling_one = scheduler.evaluate_triggers(Tick(14U), EconomyId(0U), high);
    auto cooling_two = scheduler.evaluate_triggers(Tick(15U), EconomyId(0U), high);
    assert(cooling_one.ok() && cooling_two.ok());
    assert(cooling_two.get_if()->empty());
    auto after_cooldown = scheduler.evaluate_triggers(Tick(41U), EconomyId(0U), high);
    assert(after_cooldown.ok());
    assert(after_cooldown.get_if()->size() == 1U);

    auto states = scheduler.trigger_states();
    auto restored = macro_sim::control::M11DecisionScheduler::create();
    assert(restored.ok());
    assert(restored.get_if()->restore_trigger_states(states, 1U).ok());
    assert(restored.get_if()->trigger_states() == states);
}

void test_costs() {
    M11AdjustmentCostSpec spec;
    assert(macro_sim::control::validate_m11_cost_spec(spec).ok());
    const auto *lever = macro_sim::control::find_m11_policy_lever("tax_income_rate");
    assert(lever != nullptr);
    const std::vector<M11PolicyChange> changes{{
        lever,
        macro_sim::control::PolicyValue(0.20),
        macro_sim::control::PolicyValue(0.25),
    }};
    auto cost = macro_sim::control::m11_adjustment_cost(spec, changes, false);
    assert(cost.ok());
    assert(lever->control_scale.has_value());
    const auto distance = 0.05 / *lever->control_scale;
    const auto expected = spec.major.fixed + spec.major.linear * distance +
                          spec.major.quadratic * distance * distance;
    assert(std::abs(*cost.get_if() - expected) < 1.0e-12);
    auto emergency = macro_sim::control::m11_adjustment_cost(spec, changes, true);
    assert(emergency.ok());
    assert(std::abs(*emergency.get_if() - expected * spec.emergency_premium) < 1.0e-12);
    auto administrative = macro_sim::control::m11_administrative_cost(spec, changes);
    assert(administrative.ok());
    assert(std::abs(*administrative.get_if() - (0.25 + lever->administrative_weight)) <
           1.0e-12);

    const std::vector<M11PolicyChange> no_change{{
        lever,
        macro_sim::control::PolicyValue(0.20),
        macro_sim::control::PolicyValue(0.20),
    }};
    auto zero = macro_sim::control::m11_administrative_cost(spec, no_change);
    assert(zero.ok());
    assert(*zero.get_if() == 0.0);
}

void test_event_stream() {
    M11EventStream stream(8U);
    auto first = stream.append(Tick(0U), "boundary_started", "op-1", "system", "{}",
                               M11EventVisibility::public_record);
    assert(first.ok());
    auto second = stream.append(Tick(0U), "proposal_received", "op-2", "player",
                                "{\"lever\":\"income_tax\"}",
                                M11EventVisibility::privileged_audit);
    assert(second.ok());
    assert(second.get_if()->sequence == 1U);
    assert(second.get_if()->prior_hash == first.get_if()->hash);

    auto public_page = stream.page(0U, 8U, M11EventVisibility::public_record);
    assert(public_page.ok());
    assert(public_page.get_if()->size() == 1U);
    auto audit_page = stream.page(0U, 8U, M11EventVisibility::privileged_audit);
    assert(audit_page.ok());
    assert(audit_page.get_if()->size() == 2U);

    std::vector<M11ControllerEvent> restored_events(stream.events().begin(),
                                                    stream.events().end());
    M11EventStream restored(8U);
    assert(restored.restore(restored_events, stream.next_sequence(), stream.head_hash())
               .ok());
    restored_events.back().canonical_payload = "{}";
    M11EventStream corrupt(8U);
    const auto corrupt_status =
        corrupt.restore(restored_events, stream.next_sequence(), stream.head_hash());
    assert(!corrupt_status.ok());
    assert(corrupt_status.code() == ErrorCode::corrupt_input);
}

void test_release_stream() {
    M11ReleaseStream stream(8U);
    auto first =
        stream.append(EconomyId(0U), "real_output", Tick(1U), Tick(3U), 0U, 10.0, 4U);
    assert(first.ok());
    auto revision =
        stream.append(EconomyId(0U), "real_output", Tick(1U), Tick(5U), 1U, 10.5, 7U);
    assert(revision.ok());
    auto other = stream.append(EconomyId(0U), "price_index", Tick(2U), Tick(2U), 0U,
                               std::nullopt, 8U);
    assert(other.ok());

    auto early = stream.page(0U, 8U, Tick(2U));
    assert(early.ok());
    assert(early.get_if()->size() == 1U);
    assert(early.get_if()->front().series_id == "price_index");
    auto all = stream.page(0U, 8U, Tick(5U));
    assert(all.ok());
    assert(all.get_if()->size() == 3U);

    std::vector<M11ReleaseRecord> records(stream.releases().begin(),
                                          stream.releases().end());
    M11ReleaseStream restored(8U);
    assert(restored.restore(records, stream.next_sequence()).ok());
    records[1].revision = 3U;
    M11ReleaseStream corrupt(8U);
    assert(!corrupt.restore(records, stream.next_sequence()).ok());
}

void emit_golden() {
    auto built = macro_sim::control::M11DecisionScheduler::create();
    assert(built.ok());
    auto scheduler = std::move(*built.get_if());
    const std::vector<M11MetricSample> high{{
        "reserve_floor_breach_share",
        0.15,
    }};
    auto first = scheduler.evaluate_triggers(Tick(10U), EconomyId(0U), high);
    auto second = scheduler.evaluate_triggers(Tick(11U), EconomyId(0U), high);
    assert(first.ok() && second.ok());
    const auto *lever = macro_sim::control::find_m11_policy_lever("tax_income_rate");
    assert(lever != nullptr);
    const std::vector<M11PolicyChange> changes{{
        lever,
        macro_sim::control::PolicyValue(0.20),
        macro_sim::control::PolicyValue(0.25),
    }};
    M11AdjustmentCostSpec spec;
    auto adjustment = macro_sim::control::m11_adjustment_cost(spec, changes, false);
    auto administrative = macro_sim::control::m11_administrative_cost(spec, changes);
    assert(adjustment.ok() && administrative.ok());

    std::cout << "{\"calendar_count\":" << scheduler.calendars().size()
              << ",\"trigger_count\":" << scheduler.triggers().size()
              << ",\"groups\":[";
    for (std::size_t index = 0; index < scheduler.calendars().size(); ++index) {
        if (index != 0U) {
            std::cout << ',';
        }
        const auto &calendar = scheduler.calendars()[index];
        std::cout << "{\"admin\":" << std::setprecision(17)
                  << calendar.administrative_capacity << ",\"id\":\""
                  << calendar.decision_group
                  << "\",\"period\":" << calendar.period_ticks << '}';
    }
    std::cout << "],\"adjustment\":" << std::setprecision(17) << *adjustment.get_if()
              << ",\"administrative\":" << *administrative.get_if()
              << ",\"notice_count\":" << second.get_if()->size()
              << ",\"notice_expiry\":" << second.get_if()->front().expires_at.value()
              << ",\"notice_id\":\"" << second.get_if()->front().trigger_id << "\"}\n";
}

} // namespace

int main(int argc, char **argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--golden") {
        emit_golden();
        return 0;
    }
    test_default_contract();
    test_trigger_hysteresis();
    test_costs();
    test_event_stream();
    test_release_stream();
    return 0;
}
