"""R1 Registry/controller/generated-contract parity acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_validation_parity import (
    R1_DOMAINS,
    build_r1_acceptance,
    validate_r1_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "policy_remediation_r1_acceptance_v39.json"


def test_r1_domains_accept_boundaries_and_reject_near_boundaries() -> None:
    for lever, expected in R1_DOMAINS.items():
        validation = REGISTRY[lever].validation
        assert validation.check(None, expected["minimum"]) is None
        assert validation.check(None, expected["maximum"]) is None
        assert validation.check(None, expected["minimum"] - 1.0e-9) is not None
        assert validation.check(None, expected["maximum"] + 1.0e-9) is not None
        if expected["nullable"]:
            assert validation.check(None, None) is None
        else:
            assert validation.check(None, None) is not None


def test_r1_all_contract_layers_reproduce_the_canonical_domains() -> None:
    report = build_r1_acceptance(ROOT)
    assert report["status"] == "accepted"
    assert report["errors"] == []
    assert set(report["domains"]) == set(R1_DOMAINS)


def test_committed_r1_report_reproduces_exactly() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert validate_r1_acceptance(payload, ROOT) == []
