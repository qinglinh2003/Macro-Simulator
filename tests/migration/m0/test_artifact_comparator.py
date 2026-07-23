from __future__ import annotations

from pathlib import Path

from scripts.cpp_migration.comparator import (
    first_artifact_difference,
    load_tolerance_registry,
    run_comparator_self_test,
)


ROOT = Path(__file__).resolve().parents[3]


def test_checked_invalid_and_valid_comparator_corpus():
    run_comparator_self_test(
        ROOT / "schemas/m0/manifests/comparator_cases.yaml"
    )


def test_corruption_reports_typed_path_rule_and_reason():
    registry = load_tolerance_registry()
    failure = first_artifact_difference(
        {"selected_state": {"policy_rate": 0.01}},
        {"selected_state": {"policy_rate": 0.02}},
        registry,
    )
    assert failure is not None
    assert failure.path == "$.selected_state.policy_rate"
    assert failure.rule_id == "tolerance.trace.rates"
    assert failure.reason == "numeric_mismatch"


def test_unknown_numeric_field_never_uses_a_fallback_epsilon():
    failure = first_artifact_difference(
        {"unknown": 1.0},
        {"unknown": 1.0},
        load_tolerance_registry(),
    )
    assert failure is not None
    assert failure.reason == "unknown_tolerance"
