from __future__ import annotations

from pathlib import Path

import pytest

from macro_sim.diagnostics import config_batch
from macro_sim.diagnostics.config_batch import (
    _canonical_hash,
    _direction_result,
    _load_cached,
    run_contract_batch,
)
from macro_sim.diagnostics.config_contracts import (
    activation_contracts,
    invariance_contracts,
    screening_contracts,
)


def test_canonical_hash_ignores_mapping_order() -> None:
    assert _canonical_hash({"a": 1, "b": 2}) == _canonical_hash(
        {"b": 2, "a": 1}
    )


def test_cache_rejects_a_different_signature(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(
        '{"run_signature":"abc","result":{"days":90}}',
        encoding="utf-8",
    )
    assert _load_cached(path, signature="def") is None
    assert _load_cached(path, signature="abc") == {"days": 90}


@pytest.mark.parametrize(
    ("expected", "baseline", "treatment", "difference", "result"),
    [
        ("increase", 1.0, 1.2, 0.1, "pass"),
        ("increase", 1.0, 0.8, -0.1, "pass"),
        ("decrease", 1.0, 1.2, -0.1, "pass"),
        ("nonzero", True, False, 0.1, "pass"),
        ("invariance", 1.0, 1.2, 0.0, "exact_invariance"),
    ],
)
def test_direction_result_respects_low_and_high_arms(
    expected: str,
    baseline: object,
    treatment: object,
    difference: float,
    result: str,
) -> None:
    assert (
        _direction_result(
            expected=expected,
            effect={
                "mean_difference": difference,
                "confidence_low": difference - 0.01,
                "confidence_high": difference + 0.01,
            },
            baseline_value=baseline,
            treatment_value=treatment,
            time_response=None,
        )
        == result
    )


def test_direction_result_marks_a_crossing_interval_inconclusive() -> None:
    assert _direction_result(
        expected="increase",
        effect={
            "mean_difference": 0.01,
            "confidence_low": -0.02,
            "confidence_high": 0.04,
        },
        baseline_value=1.0,
        treatment_value=1.2,
        time_response=None,
    ) == "inconclusive"


def test_washout_requires_observed_half_decay() -> None:
    effect = {
        "mean_difference": 1.0,
        "confidence_low": 0.5,
        "confidence_high": 1.5,
    }
    assert _direction_result(
        expected="washout",
        effect=effect,
        baseline_value=1.0,
        treatment_value=1.2,
        time_response={
            "peak_effect": 10.0,
            "terminal_effect": 8.0,
            "half_decay_tick": None,
        },
    ) == "inconclusive"
    assert _direction_result(
        expected="washout",
        effect=effect,
        baseline_value=1.0,
        treatment_value=1.2,
        time_response={
            "peak_effect": 10.0,
            "terminal_effect": 4.0,
            "half_decay_tick": 120,
        },
    ) == "pass"
    assert _direction_result(
        expected="washout",
        effect=effect,
        baseline_value=1.0,
        treatment_value=1.2,
        time_response={
            "peak_effect": 10.0,
            "terminal_effect": 7.0,
            "half_decay_tick": 120,
        },
    ) == "inconclusive"


def test_only_reviewed_contracts_can_enter_a_neutral_batch() -> None:
    assert all(
        contract.status == "screening_ready"
        for contract in screening_contracts(
            module="production_and_technology"
        )
    )


def test_measurement_invariance_contracts_are_executable_but_separate() -> None:
    contracts = invariance_contracts(module="distribution_and_welfare")
    assert {contract.status for contract in contracts} == {
        "invariance_activation_required"
    }
    assert {contract.route_status for contract in contracts} == {
        "infrastructure_invariance"
    }


def test_contracts_with_the_same_activation_share_one_control(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[tuple[str, str, float, float]] = []

    def fake_run_or_load(**kwargs: object) -> tuple[dict, bool]:
        signature = kwargs["signature_payload"]
        native_spec = kwargs["native_spec"]
        metrics = kwargs["primary_metrics"]
        assert isinstance(signature, dict)
        economy = native_spec.economies[0]
        rules = (
            economy.domestic_economy.financial_economy.monetary_economy
            .real_economy.rules
        )
        observed.append(
            (
                str(signature["activation_scenario"]),
                str(signature["case"]),
                float(rules.initial_consumption_capital),
                float(rules.capital_productivity),
            )
        )
        level = 1.0 if signature["case"] == "treatment" else 0.0
        summary = {
            "mean": level,
            "final": level,
            "volatility": 0.0,
            "first_window_mean": level,
            "last_window_mean": level,
            "cumulative": level,
            "post_burnin_mean": level,
            "post_burnin_volatility": 0.0,
        }
        return (
            {
                "metric_summaries": {
                    metric: dict(summary) for metric in metrics
                },
                "metric_series": {
                    metric: {"ticks": [1], "values": [level]}
                    for metric in metrics
                },
            },
            False,
        )

    monkeypatch.setattr(config_batch, "_run_or_load", fake_run_or_load)
    contracts = activation_contracts(module="production_and_technology")
    payload = run_contract_batch(
        contracts,
        seeds=[101],
        artifact_dir=tmp_path,
        source_revision="test",
        stage="activation",
        population=100_000,
        days_override=2,
    )
    assert payload["executed_runs"] == 4
    controls = [row for row in observed if row[1] == "control"]
    assert [row[0] for row in controls] == ["positive_capital_gap"]
    assert len({row[2:] for row in observed}) == 1
