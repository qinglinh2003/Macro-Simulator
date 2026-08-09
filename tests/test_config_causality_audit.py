from __future__ import annotations

from dataclasses import fields

from macro_sim.config import Config
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
    assert payload["field_count"] == 453
    assert payload["route_counts"] == {
        "derived": 2,
        "excluded_policy": 108,
        "excluded_shock": 4,
        "infrastructure_invariance": 18,
        "mapped_native": 294,
        "native_fixed": 12,
        "run_control": 1,
        "superseded": 14,
    }
    assert sum(payload["route_counts"].values()) == payload["field_count"]
    assert sum(payload["experiment_role_counts"].values()) == payload["field_count"]
    assert all(row["module"] for row in payload["rows"])
    assert all(row["experiment_role"] for row in payload["rows"])


def test_failed_v25_capital_recursion_is_not_a_silent_config_surface() -> None:
    names = {field.name for field in fields(Config)}
    assert "symmetric_k" not in names
    assert "k_replacement_floor" not in names
    assert not hasattr(Config, "v25")
    inventory_ids = {row["id"] for row in build_audit_inventory()["rows"]}
    assert "config.symmetric_k" not in inventory_ids
    assert "config.k_replacement_floor" not in inventory_ids


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
        "bank_bond_appetite": "securities_and_capital_markets",
        "bank_equity": "securities_and_capital_markets",
        "bank_equity_lambda": "securities_and_capital_markets",
        "bank_equity_trading": "securities_and_capital_markets",
        "bank_theta_equity": "securities_and_capital_markets",
        "alpha1": "consumption_prices_and_expectations",
        "bank_relationship_lock_in": "banking_and_credit",
        "delta": "labor_market",
        "energy_mortality_gamma": "energy",
        "housing_fertility_elasticity": "housing",
        "hh_subsistence": "banking_and_credit",
        "labor_relationship_wages": "labor_market",
        "lambda_p": "securities_and_capital_markets",
        "margin_credit": "securities_and_capital_markets",
        "monetary_direct_transmission": "banking_and_credit",
        "house_price_income_years": "housing",
        "rho": "firms_and_industrial_dynamics",
        "subsistence_share": "distribution_and_welfare",
        "seed": "scale_and_genesis",
        "ticks_per_year": "numerics_and_observability",
    }
    assert {
        field_name: rows[field_name]["module"]
        for field_name in expected
    } == expected


def test_lifecycle_consumption_is_routed_to_its_native_mechanism() -> None:
    rows = {
        row["id"]: row for row in build_audit_inventory()["rows"]
    }
    lifecycle = rows["config.demographic_lifecycle_consumption"]
    assert lifecycle["route_status"] == "mapped_native"
    assert lifecycle["experiment_role"] == "causal_treatment"
    assert lifecycle["native_targets"] == [
        "m7.population_rules.lifecycle_consumption"
    ]
    strata = rows["config.consumption_strata"]
    assert strata["route_status"] == "mapped_native"
    assert strata["native_targets"] == [
        "m4.real_rules.consumption_strata",
        "m6.financial_rules.consumption_strata",
    ]
    q_sensitivity = rows["config.lambda_q"]
    assert q_sensitivity["route_status"] == "mapped_native"
    assert q_sensitivity["native_targets"] == [
        "m6.financial_rules.q_investment_sensitivity"
    ]


def test_persistent_securities_structure_is_not_mislabeled_as_transient() -> None:
    rows = {row["id"]: row for row in build_audit_inventory()["rows"]}
    assert rows["config.founder_owned_genesis"]["experiment_role"] == (
        "causal_treatment"
    )
    assert rows["config.watchlist_size"]["experiment_role"] == (
        "causal_treatment"
    )
    assert rows["config.shares_per_firm"]["experiment_role"] == (
        "invariance_only"
    )
    necessity = rows["config.necessity_share0"]
    assert necessity["route_status"] == "mapped_native"
    for field_name in (
        "fertility_rank_gradient",
        "mortality_rank_gradient",
        "strat_mult_hi",
        "strat_mult_lo",
    ):
        assert rows[f"config.{field_name}"]["route_status"] == "mapped_native"
    bank_assignment = rows["config.bank_assignment"]
    assert bank_assignment["route_status"] == "mapped_native"
    assert bank_assignment["native_targets"] == [
        "m5.rules.assign_banks_by_size"
    ]
    bank_enabled = rows["config.bank_enabled"]
    assert bank_enabled["route_status"] == "mapped_native"
    assert bank_enabled["native_targets"] == [
        "m5.monetary_rules.banking_enabled",
        "m5.rules.banking_enabled",
    ]
    household_arrears = rows["config.household_interest_arrears"]
    assert household_arrears["route_status"] == "mapped_native"
    assert household_arrears["native_targets"] == [
        "m5.monetary_rules.household_interest_arrears"
    ]
    run_market_weight = rows["config.run_market_weight"]
    assert run_market_weight["route_status"] == "mapped_native"
    assert run_market_weight["native_targets"] == [
        "m5.monetary_rules.run_market_weight"
    ]
    direct = rows["config.monetary_direct_transmission"]
    assert direct["route_status"] == "mapped_native"
    assert direct["native_targets"] == [
        "m5.monetary_rules.direct_monetary_transmission"
    ]
    government = rows["config.government"]
    assert government["route_status"] == "mapped_native"
    assert government["native_targets"] == [
        "m4.spec.requested_capabilities.government"
    ]


def test_observation_gate_is_not_credited_with_economic_causality() -> None:
    rows = {row["id"]: row for row in build_audit_inventory()["rows"]}
    deprivation = rows["config.deprivation_gauges"]
    assert deprivation["route_status"] == "infrastructure_invariance"
    assert deprivation["experiment_role"] == "invariance_only"
    standard = rows["config.subsistence_share"]
    assert standard["route_status"] == "infrastructure_invariance"
    assert standard["experiment_role"] == "invariance_only"
