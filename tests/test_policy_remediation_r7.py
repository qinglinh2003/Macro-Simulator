"""R7 finite-size and rare-event remediation tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.policy_remediation_r7_lib import (
    R7_ACTION_OVERRIDES,
    R7_CANDIDATES,
    R7_CONTROL_OVERRIDES,
    R7_POPULATIONS,
    R7_SEEDS,
    build_r7_acceptance,
    build_r7_manifest,
    _activation_present,
    _rare_event_report,
    validate_r7_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
R6_P2 = ROOT / "docs/policy_remediation_r6_p2_evidence_v39.json"
R6_ACCEPTANCE = ROOT / "docs/policy_remediation_r6_acceptance_v39.json"
R7_EVIDENCE = ROOT / "docs/policy_remediation_r7_scale_evidence_v39.json"
R7_ACCEPTANCE = ROOT / "docs/policy_remediation_r7_acceptance_v39.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_r7_manifest_exactly_covers_pending_scale_queue() -> None:
    manifest = build_r7_manifest(
        r6_p2=_load(R6_P2),
        r6_acceptance=_load(R6_ACCEPTANCE),
    )
    assert manifest["errors"] == []
    assert tuple(row["lever"] for row in manifest["selections"]) == R7_CANDIDATES
    assert tuple(manifest["populations_per_country"]) == R7_POPULATIONS
    assert tuple(manifest["matched_seeds"]) == R7_SEEDS
    assert manifest["native_workers"] == 8


def test_rental_clock_compression_preserves_the_r6_policy_ratio() -> None:
    control = dict(R7_CONTROL_OVERRIDES["rental_eviction_arrears"])[
        "rental_eviction_arrears"
    ]
    treatment = R7_ACTION_OVERRIDES["rental_eviction_arrears"][0]["value"]
    assert treatment / control == 3.0
    assert treatment - control <= 30


def test_soe_scale_gate_uses_the_direct_price_channel() -> None:
    manifest = build_r7_manifest(
        r6_p2=_load(R6_P2),
        r6_acceptance=_load(R6_ACCEPTANCE),
    )
    selection = next(
        row for row in manifest["selections"] if row["lever"] == "soe_efirm"
    )
    assert selection["salient_metrics"] == [
        "metric.source.m8.energy.transaction_price"
    ]
    assert selection["exploratory_metrics"] == [
        "metric.source.m8.energy.production"
    ]


def test_rare_event_activation_accepts_prevention_or_creation() -> None:
    metric = "metric.source.m8.housing.evictions"
    selection = {
        "activation_metrics": [],
        "rare_event_metric": metric,
    }

    def run(control: list[float], treatment: list[float]) -> dict[str, object]:
        return {
            "control": {"metric_series": {metric: {"values": control}}},
            "treatment": {"metric_series": {metric: {"values": treatment}}},
        }

    prevented = run([2.0, 1.0], [0.0, 0.0])
    created = run([0.0, 0.0], [1.0, 2.0])
    assert _activation_present(prevented, selection)
    assert _activation_present(created, selection)
    report = _rare_event_report(selection, [prevented], [created])
    assert report is not None
    assert report["small_event_totals"] == [3.0]
    assert report["large_event_totals"] == [3.0]
    assert report["nonzero_at_both_scales"] is True


def test_r7_acceptance_rejects_incomplete_evidence() -> None:
    acceptance = build_r7_acceptance({
        "status": "failed",
        "errors": [],
        "reports": [],
        "counts": {},
        "protocol": {"legacy_python_simulator_used": False},
        "hashes": {},
    })
    assert acceptance["status"] == "failed"
    assert acceptance["errors"]


def test_r7_acceptance_hash_commits_to_the_evidence_hash() -> None:
    evidence = {
        "status": "failed",
        "errors": [],
        "reports": [],
        "counts": {},
        "protocol": {"legacy_python_simulator_used": False},
        "hashes": {"r7_evidence": "first"},
    }
    first = build_r7_acceptance(evidence)
    evidence["hashes"]["r7_evidence"] = "second"
    second = build_r7_acceptance(evidence)
    assert first["hashes"]["r7_acceptance"] != second["hashes"][
        "r7_acceptance"
    ]


def test_committed_r7_evidence_is_complete_and_native() -> None:
    evidence = _load(R7_EVIDENCE)
    assert evidence["status"] == "accepted"
    assert evidence["counts"]["run_records"] == 56
    assert evidence["counts"]["native_branch_paths"] == 112
    assert evidence["counts"]["cache_hits"] == 0
    assert evidence["counts"]["previously_blocked_paths_completed"] == 4
    assert evidence["protocol"]["legacy_python_simulator_used"] is False
    assert evidence["protocol"]["native_engine_workers"] == 8


def test_committed_r7_acceptance_reproduces_exactly() -> None:
    evidence = _load(R7_EVIDENCE)
    acceptance = _load(R7_ACCEPTANCE)
    assert validate_r7_acceptance(acceptance, evidence) == []
