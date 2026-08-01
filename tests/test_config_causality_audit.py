from __future__ import annotations

from macro_sim.diagnostics.config_causality import build_audit_inventory


def test_playable_baseline_enables_every_required_module() -> None:
    payload = build_audit_inventory()
    assert payload["all_required_modules_enabled"] is True
    assert {
        name: state["actual"]
        for name, state in payload["module_state"].items()
        if not state["enabled"]
    } == {}


def test_every_config_inventory_row_receives_an_audit_disposition() -> None:
    payload = build_audit_inventory()
    assert payload["field_count"] == 455
    assert payload["route_counts"] == {
        "derived": 2,
        "excluded_policy": 108,
        "excluded_shock": 4,
        "infrastructure_invariance": 18,
        "mapped_native": 219,
        "missing_native_route": 75,
        "native_fixed": 11,
        "planned_removal": 1,
        "run_control": 1,
        "superseded": 16,
    }
    assert sum(payload["route_counts"].values()) == payload["field_count"]
    assert sum(payload["experiment_role_counts"].values()) == payload["field_count"]
    assert all(row["module"] for row in payload["rows"])
    assert all(row["experiment_role"] for row in payload["rows"])


def test_missing_routes_cannot_be_misreported_as_causal_treatments() -> None:
    payload = build_audit_inventory()
    for row in payload["rows"]:
        if row["route_status"] == "missing_native_route":
            assert row["experiment_role"] == "repair_before_experiment"
