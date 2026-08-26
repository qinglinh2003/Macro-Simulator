"""R4 opportunity and state-machine acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from macro_sim.core.native_policy_routes import NATIVE_ROUTE_DEFECTS
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_catalog import LEVER_PROXIMAL_METRICS
from macro_sim.diagnostics.policy_state_machines import (
    R4_CONTRACTS,
    build_r4_acceptance,
    validate_r4_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "policy_remediation_r4_acceptance_v39.json"


def test_r4_routes_and_proximal_contracts_match_the_ruling() -> None:
    assert NATIVE_ROUTE_DEFECTS == frozenset()
    for lever, expected in R4_CONTRACTS.items():
        registry = REGISTRY[lever]
        assert registry.read_point == expected["read_point"]
        assert registry.semantics == expected["semantics"]
        assert registry.handler_id == expected["handler_id"]
        assert tuple(LEVER_PROXIMAL_METRICS[lever]) == expected["metrics"]


def test_r4_report_covers_routes_metrics_tests_and_invalidation() -> None:
    report = build_r4_acceptance(ROOT)
    assert report["status"] == "accepted"
    assert report["errors"] == []
    assert set(report["contracts"]) == set(R4_CONTRACTS)
    assert all(row["all_metrics_maintained"] for row in report["contract_checks"].values())
    assert report["native_route_defects"] == []
    assert report["checkpoint_schema_versions"] == {"m5": 5, "m6": 4, "m8": 5}
    assert report["invalidation"]["historical_evidence_invalidated"]


def test_committed_r4_report_reproduces_exactly() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert validate_r4_acceptance(payload, ROOT) == []
