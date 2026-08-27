"""R5 crisis-library acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.policy_remediation_r5_lib import (
    R5_CRISIS_IDS,
    R5_GATE_NAMES,
    R5_SHOCK_KINDS,
    R5_STATE_IDS,
    build_r5_acceptance,
    validate_r5_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs/policy_remediation_r5_acceptance_v39.json"


def test_r5_accepts_every_state_crisis_and_gate() -> None:
    report = build_r5_acceptance(ROOT)
    assert report["status"] == "accepted"
    assert report["errors"] == []
    assert set(report["state_checks"]) == set(R5_STATE_IDS)
    assert set(report["crisis_checks"]) == set(R5_CRISIS_IDS)
    assert all(row["accepted"] for row in report["state_checks"].values())
    for row in report["crisis_checks"].values():
        assert row["accepted"]
        assert set(row["gates"]) == {
            name.removesuffix("_gate") for name in R5_GATE_NAMES
        }
        assert all(row["gates"].values())
        assert row["replay_evidence_count"] >= 1
        assert row["all_integrity_rows_passed"]


def test_r5_protocol_and_shock_surface_are_native_and_complete() -> None:
    report = build_r5_acceptance(ROOT)
    assert report["protocol"] == {
        "population_per_country": 100_000,
        "matched_seeds": [5_101, 5_113, 5_129, 5_143, 5_159, 5_177, 5_193, 5_209],
        "native_engine_workers": 8,
        "independent_seed_jobs": 8,
        "entry_required_seeds": 6,
        "legacy_python_simulator_used": False,
    }
    assert report["shock_kinds"] == sorted(R5_SHOCK_KINDS)
    assert report["counts"]["cache_hits"] == 0
    assert report["counts"]["executed_native_runs"] == 176
    assert report["excluded_crises"] == []
    assert not report["supersession"]["policy_calibration_performed"]


def test_committed_r5_report_reproduces_exactly() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert validate_r5_acceptance(payload, ROOT) == []
