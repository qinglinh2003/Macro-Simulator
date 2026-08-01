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
        "mapped_native": 218,
        "missing_native_route": 75,
        "native_fixed": 12,
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


def test_ambiguous_config_names_are_owned_by_their_native_mechanism() -> None:
    rows = {
        row["field_name"]: row
        for row in build_audit_inventory()["rows"]
        if row["declaring_type"] == "Config"
    }
    expected = {
        "alpha1": "consumption_prices_and_expectations",
        "bank_relationship_lock_in": "banking_and_credit",
        "delta": "labor_market",
        "energy_mortality_gamma": "energy",
        "housing_fertility_elasticity": "housing",
        "labor_relationship_wages": "labor_market",
        "lambda_p": "securities_and_capital_markets",
        "monetary_direct_transmission": "banking_and_credit",
        "house_price_income_years": "housing",
        "rho": "firms_and_industrial_dynamics",
        "symmetric_k": "production_and_technology",
        "seed": "scale_and_genesis",
        "ticks_per_year": "numerics_and_observability",
    }
    assert {
        field_name: rows[field_name]["module"]
        for field_name in expected
    } == expected


def test_semantically_incomplete_native_assignment_is_not_counted_as_a_route() -> None:
    rows = {
        row["id"]: row for row in build_audit_inventory()["rows"]
    }
    lifecycle = rows["config.demographic_lifecycle_consumption"]
    assert lifecycle["route_status"] == "missing_native_route"
    assert lifecycle["experiment_role"] == "repair_before_experiment"
    assert "finite-life consumption" in lifecycle["route_note"]
