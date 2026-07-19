"""Administrative capacity and transparent policy-adjustment costs."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable


@dataclass(frozen=True)
class CostWeights:
    fixed: float = 0.0
    l1: float = 1.0
    l2: float = 0.0

    def __post_init__(self) -> None:
        values = (self.fixed, self.l1, self.l2)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(float(value)) for value in values):
            raise ValueError("cost weights must be finite numbers")
        if min(values) < 0:
            raise ValueError("cost weights must be non-negative")
        if self.fixed == 0 and self.l1 == 0:
            raise ValueError("fixed or L1 cost is required; L2 alone encourages splitting")


@dataclass(frozen=True)
class AdjustmentCostSpec:
    class_weights: dict[str, CostWeights] = field(default_factory=lambda: {
        "ordinary": CostWeights(fixed=0.05, l1=0.2, l2=0.02),
        "major": CostWeights(fixed=0.5, l1=0.4, l2=0.05),
        "regime_switch": CostWeights(fixed=2.0, l1=0.5, l2=0.0),
        "operational": CostWeights(fixed=0.02, l1=0.05, l2=0.0),
    })
    proposal_admin_overhead: float = 0.25
    emergency_premium: float = 1.5
    refund_on_cancel: float = 1.0
    refund_on_supersede: float = 1.0
    refund_on_failed_execution: float = 1.0

    def __post_init__(self) -> None:
        required = {"ordinary", "major", "regime_switch", "operational"}
        if set(self.class_weights) != required:
            missing = sorted(required - set(self.class_weights))
            extra = sorted(set(self.class_weights) - required)
            raise ValueError(
                f"cost classes must exactly match the controller classes; "
                f"missing={missing}, extra={extra}"
            )
        if not all(isinstance(value, CostWeights) for value in self.class_weights.values()):
            raise TypeError("class_weights values must be CostWeights")
        numeric = {
            "proposal_admin_overhead": self.proposal_admin_overhead,
            "emergency_premium": self.emergency_premium,
            "refund_on_cancel": self.refund_on_cancel,
            "refund_on_supersede": self.refund_on_supersede,
            "refund_on_failed_execution": self.refund_on_failed_execution,
        }
        for name, value in numeric.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if self.proposal_admin_overhead < 0.0:
            raise ValueError("proposal_admin_overhead must be non-negative")
        if self.emergency_premium < 0.0:
            raise ValueError("emergency_premium must be non-negative")
        for name in (
            "refund_on_cancel", "refund_on_supersede", "refund_on_failed_execution",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    def estimate(self, entries, *, emergency: bool = False) -> float:
        total = 0.0
        for entry in entries:
            if entry.old == entry.new:
                continue
            lever = entry.lever
            weights = self.class_weights[lever.cost_class]
            if lever.control_scale is None or isinstance(entry.new, (bool, str)) or entry.new is None \
                    or entry.old is None:
                distance = 1.0
            else:
                distance = abs(float(entry.new) - float(entry.old)) / lever.control_scale
            total += weights.fixed + weights.l1 * distance + weights.l2 * distance * distance
        return total * (self.emergency_premium if emergency else 1.0)

    def admin_cost(self, entries) -> float:
        changed = [entry for entry in entries if entry.old != entry.new]
        if not changed:
            return 0.0
        return self.proposal_admin_overhead + sum(entry.lever.admin_weight for entry in changed)
