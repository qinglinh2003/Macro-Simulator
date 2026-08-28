"""Packaged scope metadata for player-facing policy evidence.

The economic Registry remains authoritative for execution and validation.  This
catalog only tells clients which remediation experiments have evaluated a lever
and the limits of those results.  It deliberately carries no real-world causal
claim and keeps package-local component roles separate from single-policy
classifications.
"""
from __future__ import annotations

from importlib.resources import files
import json
from typing import Any

from .policy_registry import REGISTRY


POLICY_EVIDENCE_SCHEMA_VERSION = "policy-evidence-v39-v1"
INDIVIDUAL_CLASSIFICATIONS = frozenset({
    "conditional",
    "effective",
    "expert_only",
    "not_reclassified",
    "removed",
    "structural",
})
EVIDENCE_COVERAGE = frozenset({
    "registry_and_route_only",
    "single_policy_calibrated",
})
PACKAGE_ROLES = frozenset({"essential", "harmful", "redundant", "supportive"})


def load_policy_evidence_catalog() -> dict[str, Any]:
    """Load and strictly validate the packaged R9 policy-evidence catalog."""
    resource = files("macro_sim").joinpath(
        "data", "policy_evidence_v39.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        payload: Any = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("policy evidence catalog must be an object")
    if payload.get("schema_version") != POLICY_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("policy evidence catalog schema version differs")
    upstream = payload.get("upstream_acceptance_hashes")
    if not isinstance(upstream, dict) or set(upstream) != {"R6", "R7", "R8"}:
        raise ValueError("policy evidence upstream bindings are incomplete")
    if any(not isinstance(value, str) or len(value) != 64
           for value in upstream.values()):
        raise ValueError("policy evidence upstream bindings are malformed")
    policies = payload.get("policies")
    if not isinstance(policies, dict) or set(policies) != set(REGISTRY):
        raise ValueError("policy evidence catalog must cover the Registry exactly")

    required = {
        "coverage",
        "individual_classification",
        "package_findings",
        "population_per_country",
        "real_world_empirical_claim",
        "scale_disposition",
        "tested_crisis_states",
    }
    for name, raw in policies.items():
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError(f"policy evidence {name!r} has invalid fields")
        if raw["coverage"] not in EVIDENCE_COVERAGE:
            raise ValueError(f"policy evidence {name!r} has invalid coverage")
        if raw["individual_classification"] not in INDIVIDUAL_CLASSIFICATIONS:
            raise ValueError(
                f"policy evidence {name!r} has invalid classification"
            )
        if raw["real_world_empirical_claim"] is not False:
            raise ValueError(
                f"policy evidence {name!r} must not claim real-world causality"
            )
        states = raw["tested_crisis_states"]
        if not isinstance(states, list) or any(
            not isinstance(state, str) or not state for state in states
        ):
            raise ValueError(f"policy evidence {name!r} has invalid states")
        findings = raw["package_findings"]
        if not isinstance(findings, list):
            raise ValueError(f"policy evidence {name!r} has invalid packages")
        for finding in findings:
            if not isinstance(finding, dict) or set(finding) != {
                "package_disposition", "package_id", "role", "scenario_id",
            }:
                raise ValueError(
                    f"policy evidence {name!r} has invalid package finding"
                )
            if finding["role"] not in PACKAGE_ROLES:
                raise ValueError(
                    f"policy evidence {name!r} has invalid package role"
                )
    catalog_hash = payload.get("catalog_sha256")
    if not isinstance(catalog_hash, str) or len(catalog_hash) != 64:
        raise ValueError("policy evidence catalog hash is malformed")
    return dict(payload)


def load_policy_evidence() -> dict[str, dict[str, Any]]:
    """Return just the per-lever evidence rows for schema consumers."""
    catalog = load_policy_evidence_catalog()
    return {
        str(name): dict(raw)
        for name, raw in catalog["policies"].items()
    }


POLICY_EVIDENCE_CATALOG = load_policy_evidence_catalog()
POLICY_EVIDENCE = {
    str(name): dict(raw)
    for name, raw in POLICY_EVIDENCE_CATALOG["policies"].items()
}
POLICY_EVIDENCE_SHA256 = str(POLICY_EVIDENCE_CATALOG["catalog_sha256"])


__all__ = [
    "EVIDENCE_COVERAGE",
    "INDIVIDUAL_CLASSIFICATIONS",
    "PACKAGE_ROLES",
    "POLICY_EVIDENCE",
    "POLICY_EVIDENCE_CATALOG",
    "POLICY_EVIDENCE_SHA256",
    "POLICY_EVIDENCE_SCHEMA_VERSION",
    "load_policy_evidence",
    "load_policy_evidence_catalog",
]
