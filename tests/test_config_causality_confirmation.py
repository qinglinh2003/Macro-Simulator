from __future__ import annotations

import pytest

from macro_sim.diagnostics.config_confirmation import compare_batch_reports


def _effect(difference: float, low: float, high: float) -> dict:
    return {
        "mean_difference": difference,
        "confidence_low": low,
        "confidence_high": high,
    }


def _batch(*, population: int, days: int = 365, difference: float = 2.0) -> dict:
    contract = {
        "scope": "root",
        "field_name": "v",
        "activation_scenario": "neutral_baseline",
        "baseline_value": 1.0,
        "treatment_values": [2.0],
        "primary_metrics": ["metric.test"],
        "direction_statistics": {"metric.test": "post_burnin_mean"},
    }
    return {
        "population_per_country": population,
        "seeds": [101, 211],
        "reports": [
            {
                "contract": contract,
                "days": days,
                "burn_in_days": 90,
                "arms": [
                    {
                        "treatment_value": 2.0,
                        "effects": {
                            "metric.test": {
                                "post_burnin_mean": _effect(
                                    difference,
                                    difference - 0.5,
                                    difference + 0.5,
                                )
                            }
                        },
                    }
                ],
            }
        ],
    }


def test_matched_finite_size_comparison_reports_sign_and_ratio() -> None:
    payload = compare_batch_reports(
        _batch(population=100_000, difference=2.0),
        _batch(population=1_000_000, difference=3.0),
        field_name="v",
    )
    metric = payload["fields"][0]["arms"][0]["metrics"][0]
    assert metric["sign_preserved"] is True
    assert metric["raw_confirmation_to_reference_ratio"] == pytest.approx(1.5)
    assert metric["per_person_confirmation_to_reference_ratio"] == pytest.approx(0.15)
    assert metric["confirmation_interval_excludes_zero"] is True


def test_finite_size_comparison_rejects_horizon_or_seed_mismatch() -> None:
    with pytest.raises(ValueError, match="horizons"):
        compare_batch_reports(
            _batch(population=100_000, days=90),
            _batch(population=1_000_000, days=365),
        )
    large = _batch(population=1_000_000)
    large["seeds"] = [101]
    with pytest.raises(ValueError, match="paired seeds"):
        compare_batch_reports(_batch(population=100_000), large)
