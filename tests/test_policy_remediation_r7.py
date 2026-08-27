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
