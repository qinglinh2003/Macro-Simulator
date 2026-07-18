"""v25 B3: the registry is complete, consistent with the inventory, and the
sanctioned set_lever path validates + logs."""
import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.core.policy import Policy
from macro_sim.core.policy_registry import REGISTRY, set_lever, Range
from macro_sim.economy import Economy


def test_registry_covers_every_policy_field_exactly():
    policy_fields = {f.name for f in dataclasses.fields(Policy)}
    assert set(REGISTRY) == policy_fields, (
        f"missing={policy_fields - set(REGISTRY)} stale={set(REGISTRY) - policy_fields}")


def test_registry_capabilities_exist_in_config():
    cfg_fields = {f.name for f in dataclasses.fields(Config)}
    for lv in REGISTRY.values():
        assert lv.requires <= cfg_fields, f"{lv.name}: unknown capability {lv.requires - cfg_fields}"


def test_set_lever_validates_and_logs():
    e = Economy(Config.v13(seed=41, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                           demographics_population=120, n_ticks=20, government=True))
    for _ in range(3):
        e.step()
    before = e.policy.tax_income_rate            # v13 preset seeds a nonzero rate
    set_lever(e, "tax_income_rate", 0.25, actor="test")
    assert e.policy.tax_income_rate == 0.25
    assert e._policy_action_log[-1]["lever"] == "tax_income_rate"
    assert e._policy_action_log[-1]["old"] == pytest.approx(before)
    with pytest.raises(ValueError, match="outside"):
        set_lever(e, "tax_income_rate", 2.0)
    with pytest.raises(ValueError, match="capability"):
        set_lever(e, "tax_energy_rate", 0.1)      # energy_enabled missing
    with pytest.raises(KeyError):
        set_lever(e, "no_such_lever", 1)


def test_max_step_enforced_when_declared():
    e = Economy(Config.v13(seed=42, n_households=20, n_firms_c=15, n_firms_k=8, n_banks=2,
                           demographics_population=120, n_ticks=20, government=True))
    for _ in range(3):
        e.step()
    stepped = dataclasses.replace(REGISTRY["tax_income_rate"],
                                  validation=Range(0.0, 0.8, max_step=0.05))
    REGISTRY["tax_income_rate"] = stepped
    try:
        base = e.policy.tax_income_rate          # preset-seeded (0.2 in v13)
        with pytest.raises(ValueError, match="max_step"):
            set_lever(e, "tax_income_rate", base + 0.3)
        set_lever(e, "tax_income_rate", base + 0.04)   # within the step cap
    finally:
        REGISTRY["tax_income_rate"] = dataclasses.replace(stepped, validation=Range(0.0, 0.8))
