from __future__ import annotations

import math

import pytest

from macro_sim.controllers.costs import AdjustmentCostSpec, CostWeights
from macro_sim.controllers.scheduler import (
    CalendarSpec,
    DecisionScheduler,
    TriggerSpec,
)


@pytest.mark.parametrize("value", [-1.0, math.inf, math.nan, True])
def test_cost_spec_rejects_invalid_operational_numbers(value):
    with pytest.raises((TypeError, ValueError)):
        CostWeights(fixed=value)
    with pytest.raises((TypeError, ValueError)):
        AdjustmentCostSpec(proposal_admin_overhead=value)


def test_cost_spec_requires_complete_classes_and_bounded_refunds():
    with pytest.raises(ValueError, match="cost classes"):
        AdjustmentCostSpec(class_weights={"ordinary": CostWeights()})
    with pytest.raises(ValueError, match="refund_on_cancel"):
        AdjustmentCostSpec(refund_on_cancel=1.01)


def test_scheduler_specs_reject_overlap_bad_hysteresis_and_duplicate_ids():
    with pytest.raises(ValueError, match="overlap"):
        CalendarSpec(5, window_ticks=6)
    with pytest.raises(ValueError, match="enter_threshold"):
        TriggerSpec("bad", "metric", 0.1, 0.2, authorized_seats=("treasury",))
    trigger = TriggerSpec("same", "metric", 0.2, 0.1, authorized_seats=("treasury",))
    with pytest.raises(ValueError, match="unique"):
        DecisionScheduler(triggers=(trigger, trigger))


def test_missing_metric_breaks_trigger_persistence():
    trigger = TriggerSpec(
        "stress", "metric", 1.0, 0.0,
        min_persist_ticks=2, authorized_seats=("regulator",),
    )
    scheduler = DecisionScheduler(triggers=(trigger,))

    assert scheduler.evaluate_triggers(0, 0, {"metric": 2.0}) == []
    assert scheduler.evaluate_triggers(1, 0, {}) == []
    assert scheduler.evaluate_triggers(2, 0, {"metric": 2.0}) == []
    assert len(scheduler.evaluate_triggers(3, 0, {"metric": 2.0})) == 1
