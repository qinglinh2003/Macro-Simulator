"""R2 native contract-observability acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_catalog import LEVER_PROXIMAL_METRICS
from macro_sim.diagnostics.policy_observability import (
    R2_CONTRACTS,
    build_r2_acceptance,
    validate_r2_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "policy_remediation_r2_acceptance_v39.json"


def test_r2_registry_and_proximal_contracts_match_the_ruling() -> None:
    for lever, expected in R2_CONTRACTS.items():
        registry = REGISTRY[lever]
        assert registry.read_point == expected["read_point"]
        assert registry.semantics == expected["semantics"]
        assert registry.handler_id == expected["handler_id"]
        assert tuple(LEVER_PROXIMAL_METRICS[lever]) == expected["metrics"]


def test_r2_report_covers_maintained_metrics_and_invalidates_old_evidence() -> None:
    report = build_r2_acceptance(ROOT)
    assert report["status"] == "accepted"
    assert report["errors"] == []
    assert set(report["contracts"]) == set(R2_CONTRACTS)
    assert all(
        row["all_metrics_maintained"]
        for row in report["contract_checks"].values()
    )
    assert report["invalidation"]["historical_evidence_invalidated"]
    assert report["checkpoint_schema_versions"] == {"m5": 3, "m6": 3, "m8": 3}


def test_committed_r2_report_reproduces_exactly() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert validate_r2_acceptance(payload, ROOT) == []
