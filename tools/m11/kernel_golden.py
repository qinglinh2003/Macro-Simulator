#!/usr/bin/env python3
"""Compare the native M11 institutional kernel with the Python oracle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_sim.controllers.costs import AdjustmentCostSpec
from macro_sim.controllers.scheduler import DecisionScheduler
from macro_sim.core.policy_registry import REGISTRY


def expected() -> dict[str, object]:
    scheduler = DecisionScheduler()
    first = scheduler.evaluate_triggers(
        10, 0, {"reserve_floor_breach_share": 0.15}
    )
    second = scheduler.evaluate_triggers(
        11, 0, {"reserve_floor_breach_share": 0.15}
    )
    assert not first and len(second) == 1

    entries = (
        SimpleNamespace(
            lever=REGISTRY["tax_income_rate"],
            old=0.20,
            new=0.25,
        ),
    )
    cost_spec = AdjustmentCostSpec()
    return {
        "calendar_count": len(scheduler.calendars),
        "trigger_count": len(scheduler.triggers),
        "groups": [
            {
                "admin": spec.admin_capacity,
                "id": name,
                "period": spec.period_ticks,
            }
            for name, spec in sorted(scheduler.calendars.items())
        ],
        "adjustment": cost_spec.estimate(entries),
        "administrative": cost_spec.admin_cost(entries),
        "notice_count": len(second),
        "notice_expiry": second[0].expires_at_tick,
        "notice_id": second[0].trigger_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-exe", required=True, type=Path)
    args = parser.parse_args()
    completed = subprocess.run(
        [str(args.native_exe), "--golden"],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = json.loads(completed.stdout)
    oracle = expected()
    if actual.keys() != oracle.keys():
        raise AssertionError((actual.keys(), oracle.keys()))
    for key in ("adjustment", "administrative"):
        if abs(float(actual[key]) - float(oracle[key])) > 1.0e-12:
            raise AssertionError((key, actual[key], oracle[key]))
    actual.pop("adjustment")
    actual.pop("administrative")
    oracle.pop("adjustment")
    oracle.pop("administrative")
    if actual != oracle:
        raise AssertionError((actual, oracle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
