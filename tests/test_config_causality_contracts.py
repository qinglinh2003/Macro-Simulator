from __future__ import annotations

from macro_sim.diagnostics.config_contracts import (
    activation_contracts,
    build_contract_registry,
    screening_contracts,
)


def test_contract_registry_covers_every_inventory_field() -> None:
    payload = build_contract_registry()
    assert payload["field_count"] == 455
    assert len(payload["contracts"]) == 455
    assert len({item["field_id"] for item in payload["contracts"]}) == 455
    assert payload["status_counts"]["blocked_native_route"] == 75


def test_production_screening_contracts_are_curated_and_routed() -> None:
    contracts = screening_contracts(module="production_and_technology")
    assert len(contracts) == 10
    assert {contract.field_name for contract in contracts} == {
        "alpha",
        "capital_firm_entry",
        "capital_market",
        "lambda_issue",
        "A",
        "a_K",
        "delta_K",
        "K_firm0",
        "tfp_drift_rate",
        "v",
    }
    assert all(contract.route_status == "mapped_native" for contract in contracts)
    assert all(contract.treatment_values for contract in contracts)
    assert all(contract.primary_metrics for contract in contracts)
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in contracts
    )


def test_activation_only_contracts_do_not_enter_neutral_screen() -> None:
    payload = build_contract_registry()
    contracts = {item["field_name"]: item for item in payload["contracts"]}
    assert contracts["capital_rationed_signal"]["status"] == (
        "activation_scenario_required"
    )
    assert contracts["capital_rationed_signal"]["activation_scenario"] == (
        "positive_capital_gap"
    )
    assert contracts["lambda_issue"]["activation_scenario"] == (
        "neutral_baseline_q_above_one"
    )
    assert contracts["lambda_issue"]["direction_statistics"] == {
        "metric.source.m6.primary_equity_raised": "first_window_mean"
    }
    assert contracts["lambda_I"]["activation_scenario"] == (
        "positive_capital_gap"
    )
    assert contracts["lambda_I"]["direction_statistics"] == {
        "metric.source.m4.fixed_capital_formation_real": "cumulative"
    }
    assert contracts["capital_rationed_signal"]["direction_statistics"] == {
        "metric.source.m4.fixed_capital_formation_real": "cumulative"
    }
    assert contracts["a"]["status"] == "excluded_non_treatment"


def test_activation_contracts_are_reviewed_and_separate() -> None:
    contracts = activation_contracts(module="production_and_technology")
    assert {contract.field_name for contract in contracts} == {
        "capital_rationed_signal",
        "lambda_I",
    }
    assert all(
        contract.status == "activation_scenario_required"
        for contract in contracts
    )


def test_firm_contracts_cover_every_mapped_causal_or_genesis_field() -> None:
    neutral = screening_contracts(module="firms_and_industrial_dynamics")
    activated = activation_contracts(module="firms_and_industrial_dynamics")
    assert len(neutral) == 13
    assert len(activated) == 6
    assert len({contract.field_name for contract in (*neutral, *activated)}) == 19
    assert all(
        set(contract.expected_directions) <= set(contract.primary_metrics)
        for contract in (*neutral, *activated)
    )
