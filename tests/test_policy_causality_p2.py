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


def test_nullable_caps_use_binding_threshold_crossing_doses() -> None:
    import_quota = select_experiment_arms(
        _contract("import_quota"), phase="activation"
    )
    immigration_cap = select_experiment_arms(
        _contract("immigration_cap"), phase="activation"
    )
    assert [item.actions for item in import_quota] == [
        (("import_quota", 0.25),),
        (("import_quota", 0.0),),
    ]
    assert [item.actions for item in immigration_cap] == [
        (("immigration_cap", 0.01),),
        (("immigration_cap", 0.0),),
    ]

    permits = select_experiment_arms(
        _contract("housing_permits"), phase="activation"
    )
    mortgage_ltv = select_experiment_arms(
        _contract("mortgage_ltv_cap"), phase="activation"
    )
    arrears_floor = select_experiment_arms(
        _contract("mortgage_arrears_floor"), phase="activation"
    )
    assert [item.actions for item in permits] == [
        (("housing_permits", 25),),
        (("housing_permits", 0),),
    ]
    assert [item.actions for item in mortgage_ltv] == [
        (("mortgage_ltv_cap", 0.50),),
        (("mortgage_ltv_cap", 0.0),),
    ]
    assert [item.actions for item in arrears_floor] == [
        (("mortgage_arrears_floor", 10.0),),
        (("mortgage_arrears_floor", 100.0),),
    ]


def test_activation_groups_freeze_target_fixture_and_horizon_overrides() -> None:
    groups = build_experiment_groups(
        build_contracts(),
        phase="activation",
        ordinary_days=7,
        activation_days=30,
        burn_in_days=7,
        withdrawal_days=7,
    )
    by_lever = {
        contract.lever: group
        for group in groups
        for contract in group.contracts
    }

    remittance = by_lever["remittance_tax"]
    assert remittance.target_economy == 1
    assert remittance.native_scenario == "world_migration_wage_gap"

    taylor = by_lever["taylor_phi_pi"]
    assert dict(taylor.setup_actions)["monetary_regime"] == "taylor"
    assert dict(taylor.setup_actions)["r_max"] == 0.02

    foreclosure = by_lever["mortgage_foreclosure_ltv"]
    assert foreclosure.days == 365
    assert foreclosure.native_scenario == "housing_distressed_market"


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


def test_analysis_never_labels_an_exact_zero_effect_as_salient() -> None:
    contract = _contract("gov_consumption_share")
    ordinary = _phase_runs(contract, changed=False)
    activation = _phase_runs(contract, changed=False)
    reports, errors = analyze_p2((contract,), ordinary, activation)
    assert errors == []
    assert reports[0]["disposition"] == "mechanism_defect"
    for arm in reports[0]["activation"]["arms"]:
        assert arm["salient_proximal_metrics"] == []


def test_analysis_distinguishes_an_inactive_direct_gate_from_a_dead_mechanism() -> None:
    contract = _contract("housing_permits")
    ordinary = _phase_runs(contract, changed=False)
    activation = _phase_runs(contract, changed=False)
    direct = contract.mechanism_proximal_metrics[0]
    for run in activation:
        run["control"]["metric_summaries"][direct] = _metric_summary(0.0)
        run["control"]["metric_series"][direct] = {
            "ticks": [1, 2],
            "values": [0.0, 0.0],
        }
        for arm in run["contracts"][contract.lever]["arms"]:
            arm["run"]["metric_summaries"][direct] = _metric_summary(0.0)
            arm["run"]["metric_series"][direct] = {
                "ticks": [1, 2],
                "values": [0.0, 0.0],
            }
    reports, errors = analyze_p2((contract,), ordinary, activation)
    assert errors == []
    assert reports[0]["disposition"] == "unsupported_by_current_engine"
    assert reports[0]["activation"]["fixture_evidence"]["passed"] is True
    assert (
        reports[0]["activation"]["mechanism_opportunity_evidence"]["passed"]
        is False
    )


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
