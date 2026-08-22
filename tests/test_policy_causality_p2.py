"""Acceptance tests for the Policy causality audit P2 runner."""

from __future__ import annotations

from macro_sim.core.native_policy_routes import ENGINE_ROUTE_DEFECT, NATIVE_POLICY_ROUTES
from macro_sim.diagnostics.policy_catalog import ACTIVATION_FIXTURES
from macro_sim.diagnostics.policy_contracts import build_contracts
from macro_sim.diagnostics.policy_effects import (
    FINAL_DISPOSITIONS,
    analyze_p2,
    build_experiment_groups,
    select_experiment_arms,
)


def _contract(name: str):
    return next(item for item in build_contracts() if item.lever == name)


def _metric_summary(value: float) -> dict[str, float | int]:
    return {
        "observations": 2,
        "mean": value,
        "final": value,
        "minimum": value,
        "maximum": value,
        "volatility": 0.0,
        "first_window_mean": value,
        "last_window_mean": value,
        "cumulative": value * 2.0,
        "post_burnin_mean": value,
        "post_burnin_volatility": 0.0,
    }


def _phase_runs(contract, *, changed: bool, fixture_active: bool = True):
    metrics = set(contract.materiality_metrics)
    fixture = set(ACTIVATION_FIXTURES[contract.activation_fixture].activation_metrics)
    metrics.update(fixture)
    output = []
    for seed in (1, 2, 3, 4):
        control_values = {
            metric_id: (1.0 if fixture_active or metric_id not in fixture else 0.0)
            for metric_id in metrics
        }
        treatment_values = dict(control_values)
        if changed:
            treatment_values[contract.mechanism_proximal_metrics[0]] = (
                control_values[contract.mechanism_proximal_metrics[0]] + 1.0
            )
        control = {
            "metric_summaries": {
                metric_id: _metric_summary(value)
                for metric_id, value in control_values.items()
            },
            "metric_series": {
                metric_id: {"ticks": [1, 2], "values": [value, value]}
                for metric_id, value in control_values.items()
            },
        }
        treatment = {
            "metric_summaries": {
                metric_id: _metric_summary(value)
                for metric_id, value in treatment_values.items()
            },
            "metric_series": {
                metric_id: {"ticks": [1, 2], "values": [value, value]}
                for metric_id, value in treatment_values.items()
            },
        }
        output.append({
            "seed": seed,
            "control": control,
            "contracts": {
                contract.lever: {
                    "arms": [{
                        "label": "test_arm",
                        "dose_class": "meaningful",
                        "actions": [
                            {"economy_id": 0, "lever": contract.lever, "value": 1}
                        ],
                        "policy_applied": True,
                        "run": treatment,
                        "withdrawal": {"policy_restored": True},
                        "error": None,
                    }]
                }
            },
        })
    return output


def test_groups_cover_every_routed_lever_exactly_once_per_phase() -> None:
    contracts = build_contracts()
    routed = {
        item.lever
        for item in contracts
        if NATIVE_POLICY_ROUTES[item.lever].disposition != ENGINE_ROUTE_DEFECT
    }
    for phase in ("ordinary", "activation"):
        groups = build_experiment_groups(
            contracts,
            phase=phase,
            ordinary_days=7,
            activation_days=30,
            burn_in_days=7,
            withdrawal_days=7,
        )
        names = [contract.lever for group in groups for contract in group.contracts]
        assert len(names) == len(set(names)) == 99
        assert set(names) == routed


def test_numeric_arms_include_local_and_meaningful_activation_doses() -> None:
    contract = _contract("gov_consumption_share")
    activation = select_experiment_arms(contract, phase="activation")
    ordinary = select_experiment_arms(contract, phase="ordinary")
    assert {item.dose_class for item in activation} == {"local", "meaningful"}
    assert [item.dose_class for item in ordinary] == ["meaningful"]


def test_peg_anchor_is_exercised_as_one_valid_atomic_transition() -> None:
    contract = _contract("peg_anchor")
    assert len(contract.treatment_batches) == 1
    assert dict(contract.treatment_batches[0].actions) == {
        "peg_anchor": 2,
        "fx_regime": "peg",
    }


def test_analysis_accepts_live_salient_immediate_mechanism() -> None:
    contract = _contract("gov_consumption_share")
    ordinary = _phase_runs(contract, changed=True)
    activation = _phase_runs(contract, changed=True)
    reports, errors = analyze_p2((contract,), ordinary, activation)
    assert errors == []
    assert reports[0]["disposition"] == "accepted"
    assert reports[0]["disposition"] in FINAL_DISPOSITIONS


def test_analysis_does_not_accept_aggregate_only_new_contract_evidence() -> None:
    contract = _contract("bond_coupon")
    ordinary = _phase_runs(contract, changed=True)
    activation = _phase_runs(contract, changed=True)
    reports, errors = analyze_p2((contract,), ordinary, activation)
    assert errors == []
    assert reports[0]["disposition"] == "observable_defect"


def test_analysis_preserves_known_route_defect_without_running_it() -> None:
    contract = _contract("mortgage_risk_weight")
    reports, errors = analyze_p2((contract,), (), ())
    assert errors == []
    assert reports[0]["disposition"] == "engine_route_defect"
