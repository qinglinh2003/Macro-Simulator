from __future__ import annotations

from scripts.cpp_migration.comparator import validate_statistical_registry


def test_frozen_seed_panels_meet_power_and_holm_contract():
    registry = validate_statistical_registry()
    assert registry["family_wise_alpha"] == 0.05
    assert registry["correction"] == "holm"
    assert all(row["power"] >= 0.8 for row in registry["rows"])
    assert all(len(row["seeds"]) == 16 for row in registry["rows"])
