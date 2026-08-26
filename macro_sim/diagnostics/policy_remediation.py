"""Deterministic P0-P8 remediation ledger for Policy repair R0.

R0 is a planning and provenance milestone.  It consumes frozen audit reports,
classifies every canonical Policy lever, and emits the ordered repair and
revalidation queues.  It intentionally does not execute either simulator or
change an economic mechanism.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


R0_SCHEMA_VERSION = "policy-remediation-r0-v1"
R0_ACCEPTED_STATUS = "accepted"

P2_DEFECT_DISPOSITIONS = frozenset({
    "engine_route_defect",
    "mechanism_defect",
    "observable_defect",
    "unsupported_by_current_engine",
})

BEHAVIOR_REVIEW_LEVERS = frozenset({
    # Fiscal, labor, and distribution.
    "gov_consumption_share",
    "gov_investment_share",
    "gov_deficit_target",
    "deficit_u_ref",
    "benefit_income_floor",
    "benefit_replacement",
    "pension_replacement",
    "min_wage",
    "job_guarantee",
    "jg_wage_ratio",
    "jg_public_works_share",
    "tax_income_rate",
    # Monetary stance and liquidity.
    "manual_policy_rate",
    "inflation_target",
    "monetary_regime",
    "r_neutral",
    "taylor_phi_pi",
    "taylor_phi_u",
    "rate_inertia",
    "u_natural",
    "r_max",
    "infl_ema_lambda",
    "cb_core_inflation",
    "cb_uses_fixed_basket_cpi",
    "cb_log_inflation",
    "omo",
    # Financial and housing.
    "bank_min_capital",
    "mortgage_ltv_cap",
    "bankrupt_persist",
    "mortgage_foreclosure_ltv",
    "rental_eviction_arrears",
    # Energy, external, and structural.
    "energy_price_cap",
    "energy_rationing",
    "tariff",
    "fx_regime",
    "soe_efirm",
})

SCALE_REVALIDATION_LEVERS = frozenset({
    "gov_investment_share",
    "bankrupt_persist",
    "soe_efirm",
    "tariff",
    "fx_regime",
    "mortgage_foreclosure_ltv",
    "rental_eviction_arrears",
})

EMPIRICAL_COMPARISON_LEVERS: Mapping[str, tuple[str, ...]] = {
    "fiscal_spending_multiplier": (
        "gov_consumption_share", "gov_investment_share",
    ),
    "income_tax_output_response": ("tax_income_rate",),
    "benefit_consumption_and_poverty": (
        "benefit_income_floor", "benefit_replacement",
    ),
    "minimum_wage_employment": ("min_wage",),
    "manual_rate_recession_response": ("manual_policy_rate",),
    "open_market_operations_yield_channel": ("omo",),
    "bank_capital_credit": ("bank_min_capital",),
    "mortgage_ltv_credit": ("mortgage_ltv_cap",),
    "tariff_import_response": ("tariff",),
}

PHASE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "phase_id": "R0",
        "title": "Remediation ledger and evidence invalidation map",
        "purpose": "Freeze scope, ordering, acceptance gates, and provenance before mechanism edits.",
        "prerequisites": ["P8 accepted with explicit limitations"],
        "exit_criteria": [
            "All 102 Registry levers appear exactly once in the primary ledger.",
            "The 27/36/39 classification and source hashes reproduce deterministically.",
            "Every repair queue has explicit gates and an evidence invalidation rule.",
        ],
        "invalidates_audit_stages": [],
    },
    {
        "phase_id": "R1",
        "title": "Registry and native validation parity",
        "purpose": "Make the player-facing domain equal the native acceptance domain.",
        "prerequisites": ["R0"],
        "exit_criteria": [
            "Boundary and near-boundary values agree across Registry, controller, checkpoint, and native validators.",
            "Invalid values fail before dispatch with one canonical reason.",
        ],
        "invalidates_audit_stages": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R2",
        "title": "Contract-level observability",
        "purpose": "Expose enough native observables to prove cohort terms, gates, flows, and long-yield transmission.",
        "prerequisites": ["R1"],
        "exit_criteria": [
            "Every repaired lever has a declared proximal observable that changes at the correct read point.",
            "Stock-versus-new-contract semantics are distinguishable without proxy inference.",
            "OMO has a comparable sovereign-duration or long-yield outcome.",
        ],
        "invalidates_audit_stages": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R3",
        "title": "Direct route and mechanism repair",
        "purpose": "Connect stored Policy state to the intended native decision and settlement paths.",
        "prerequisites": ["R2"],
        "exit_criteria": [
            "Each repaired route is read by the intended native mechanism.",
            "Local and meaningful doses move the declared proximal metric in matched-seed tests.",
            "Withdrawal or restoration returns the mechanism to its reference behavior where applicable.",
        ],
        "invalidates_audit_stages": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R4",
        "title": "Opportunity and state-machine repair",
        "purpose": "Create deterministic binding fixtures for rare legal, liquidity, housing, and failure transitions.",
        "prerequisites": ["R3"],
        "exit_criteria": [
            "The intended opportunity occurs in every preregistered seed.",
            "The treatment changes the event decision or state transition, not merely a downstream proxy.",
            "Activation, non-activation, and withdrawal paths are all covered.",
        ],
        "invalidates_audit_stages": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R5",
        "title": "Crisis and structural-state library repair",
        "purpose": "Accept the ten crisis scenarios that P3 withheld before policy-efficacy retesting.",
        "prerequisites": ["R4"],
        "exit_criteria": [
            "Each scenario passes activation, severity, persistence, contamination, and accounting gates.",
            "Crisis calibration remains separate from policy calibration.",
        ],
        "invalidates_audit_stages": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R6",
        "title": "Single-policy calibration and reclassification",
        "purpose": "Retest the 36 behavior candidates across relevant states, doses, and horizons.",
        "prerequisites": ["R5"],
        "exit_criteria": [
            "Each candidate is classified as effective, conditional, expert-only, structural, or removed from the player surface.",
            "Direction, magnitude, timing, guardrails, and empirical scope are reported separately.",
            "No lever is retained solely because a statistically detectable but gameplay-silent effect exists.",
        ],
        "invalidates_audit_stages": ["P2", "P4", "P5", "P6", "P7", "P8"],
    },
    {
        "phase_id": "R7",
        "title": "Scale and rare-event confirmation",
        "purpose": "Close finite-size dependencies and previously blocked million-person paths.",
        "prerequisites": ["R6"],
        "exit_criteria": [
            "100k and 1M matched-seed signs agree or the scale dependency is explicitly modeled.",
            "All previously blocked paths finish within the preregistered wall-clock and memory budgets.",
        ],
        "invalidates_audit_stages": ["P6", "P7", "P8"],
    },
    {
        "phase_id": "R8",
        "title": "Policy packages and interaction robustness",
        "purpose": "Rebuild crisis packages only from accepted single-policy and scenario evidence.",
        "prerequisites": ["R7"],
        "exit_criteria": [
            "Every package passes primary, guardrail, withdrawal, severity, and alternative-state gates.",
            "Factorial and ablation evidence identifies essential, redundant, and harmful components.",
        ],
        "invalidates_audit_stages": ["P5", "P7", "P8"],
    },
    {
        "phase_id": "R9",
        "title": "Controller, UI, and final acceptance",
        "purpose": "Refresh delivery timing, human ingress, heuristic, random, and RL transfer evidence after engine repair.",
        "prerequisites": ["R8"],
        "exit_criteria": [
            "The UI domain and definitions match the accepted Registry and evidence scope.",
            "Free-immediate and institutional delivery paths share identical economic execution after their documented lags.",
            "The full native acceptance suite passes with eight test workers.",
        ],
        "invalidates_audit_stages": ["P8"],
    },
)


def canonical_json(value: Any) -> str:
    """Serialize finite JSON for stable content hashes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _load(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _by_lever(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["lever"]): dict(item) for item in report.get("reports", ())}


def _acceptance_hash(report: Mapping[str, Any], stage: str) -> str:
    value = report.get("hashes", {}).get(f"{stage}_acceptance")
    return str(value or "")


def _require_equal(
    errors: list[str], label: str, actual: Any, expected: Any,
) -> None:
    if actual != expected:
        errors.append(f"{label}: {actual!r} != {expected!r}")


def build_source_freeze(
    p1_source: str | Path | Mapping[str, Any],
    p2_source: str | Path | Mapping[str, Any],
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
    p6_source: str | Path | Mapping[str, Any],
    p7_source: str | Path | Mapping[str, Any],
    p8_source: str | Path | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    """Pin the frozen audit identity and verify exposed cross-stage bindings."""
    reports = {
        "p1": _load(p1_source),
        "p2": _load(p2_source),
        "p3": _load(p3_source),
        "p4": _load(p4_source),
        "p5": _load(p5_source),
        "p6": _load(p6_source),
        "p7": _load(p7_source),
        "p8": _load(p8_source),
    }
    errors: list[str] = []
    expected_statuses = {
        "p1": "accepted_with_explicit_defects",
        "p2": "accepted_with_explicit_defects",
        "p3": "accepted_with_explicit_defects",
        "p4": "accepted_with_explicit_defects",
        "p5": "accepted_with_explicit_defects",
        "p6": "accepted_with_explicit_defects",
        "p7": "accepted_with_explicit_defects",
        "p8": "accepted_with_explicit_limitations",
    }
    for stage, expected in expected_statuses.items():
        _require_equal(errors, f"{stage} status", reports[stage].get("status"), expected)

    p0_roots = {
        "p1": reports["p1"].get("hashes", {}).get("p0_root"),
        "p2": reports["p2"].get("p0_root_hash"),
        "p3": reports["p3"].get("p0_root_hash"),
        "p4": reports["p4"].get("manifest", {}).get("p0_root_hash"),
        "p5": reports["p5"].get("manifest", {}).get("p0_root_hash"),
        "p6": reports["p6"].get("manifest", {}).get("p0_root_hash"),
        "p7": reports["p7"].get("manifest", {}).get("p0_root_hash"),
    }
    roots = {str(value) for value in p0_roots.values() if value}
    if len(roots) != 1 or any(not value for value in p0_roots.values()):
        errors.append(f"P0 root identity is not common across P1-P7: {p0_roots}")
    p0_root = next(iter(roots), "")

    hashes = {stage: _acceptance_hash(report, stage) for stage, report in reports.items()}
    if any(not value for value in hashes.values()):
        errors.append("one or more P1-P8 acceptance hashes are missing")

    p4_manifest = reports["p4"].get("manifest", {})
    _require_equal(errors, "P4 binds P2", p4_manifest.get("p2_acceptance_hash"), hashes["p2"])
    _require_equal(errors, "P4 binds P3", p4_manifest.get("p3_acceptance_hash"), hashes["p3"])
    p5_manifest = reports["p5"].get("manifest", {})
    for stage in ("p2", "p3", "p4"):
        _require_equal(
            errors,
            f"P5 binds {stage.upper()}",
            p5_manifest.get(f"{stage}_acceptance_hash"),
            hashes[stage],
        )
    p6_manifest = reports["p6"].get("manifest", {})
    _require_equal(errors, "P6 binds P2", p6_manifest.get("p2_acceptance_hash"), hashes["p2"])
    _require_equal(errors, "P6 binds P5", p6_manifest.get("p5_acceptance_hash"), hashes["p5"])
    p7_upstream = reports["p7"].get("manifest", {}).get("upstream_acceptance_hashes", {})
    for stage in ("p2", "p3", "p4", "p5", "p6"):
        _require_equal(
            errors,
            f"P7 binds {stage.upper()}",
            p7_upstream.get(f"{stage}_acceptance"),
            hashes[stage],
        )
    p8_upstream = reports["p8"].get("manifest", {}).get("upstream_acceptance_hashes", {})
    for stage in ("p3", "p4", "p7"):
        _require_equal(
            errors,
            f"P8 binds {stage.upper()}",
            p8_upstream.get(f"{stage}_acceptance"),
            hashes[stage],
        )

    _require_equal(errors, "P2 lever count", reports["p2"].get("counts", {}).get("levers"), 102)
    _require_equal(errors, "P4 matrix count", reports["p4"].get("counts", {}).get("matrix_cells"), 102)
    _require_equal(errors, "P7 lever count", reports["p7"].get("counts", {}).get("levers"), 102)
    _require_equal(errors, "P7 accepted crisis count", reports["p7"].get("counts", {}).get("accepted_crises"), 1)

    freeze = {
        "p0_root_hash": p0_root,
        "acceptance_hashes": hashes,
        "source_revisions": {
            stage: report.get("source_revision") for stage, report in reports.items()
        },
        "statuses": {stage: report.get("status") for stage, report in reports.items()},
        "accepted_crises": list(
            reports["p7"].get("freeze", {}).get("scenario_manifests", {}).get(
                "accepted_scenarios", ()
            )
        ),
        "provenance_notes": [
            "P0 identity is the common root exposed by P1-P7, not a copied standalone ignored artifact.",
            "P2 does not expose a P1 acceptance binding; R0 pins P1 and P2 independently on the same P0 root.",
            "R0 verifies exposed cross-stage identities but does not rerun upstream native experiments.",
        ],
    }
    return freeze, reports, errors


def _package_membership(p5: Mapping[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for package in p5.get("manifest", {}).get("packages", ()):
        package_id = str(package["package_id"])
        for lever in package.get("required_levers", ()):
            result.setdefault(str(lever), []).append(package_id)
    return result


def _comparison_membership(p7: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    comparisons = {
        item["comparison_id"]: item for item in p7.get("empirical_comparisons", ())
    }
    for comparison_id, levers in EMPIRICAL_COMPARISON_LEVERS.items():
        item = comparisons.get(comparison_id)
        if item is None:
            continue
        finding = {
            "stage": "P7",
            "code": str(item["comparison_status"]),
            "reason": str(item["assessment"]),
            "comparison_id": comparison_id,
        }
        for lever in levers:
            result.setdefault(lever, []).append(finding)
    return result


def _mandatory_phases(p2_report: Mapping[str, Any]) -> list[str]:
    phases: list[str] = []
    if p2_report.get("validation_contract_defect"):
        phases.append("R1")
    disposition = p2_report.get("disposition")
    if disposition == "observable_defect":
        phases.append("R2")
    elif disposition in {"engine_route_defect", "mechanism_defect"}:
        phases.append("R3")
    elif disposition == "unsupported_by_current_engine":
        phases.append("R4")
    return phases


def _repair_contract(
    remediation_class: str,
    p2_report: Mapping[str, Any],
    phase_ids: Iterable[str],
) -> dict[str, Any]:
    phases = set(phase_ids)
    if remediation_class == "no_change_evidence":
        return {
            "intent": "preserve_current_behavior",
            "acceptance_gates": [
                "Remain covered by the final 102-lever Registry and native regression suite.",
                "Any later semantic change must move this lever back into a repair or calibration queue.",
            ],
        }
    gates: list[str] = []
    if "R1" in phases:
        gates.append("Registry, controller, checkpoint, and native boundary values must agree.")
    if "R2" in phases:
        gates.append("A direct proximal observable must distinguish the intended contract, flow, or cohort effect.")
    if "R3" in phases:
        gates.append("Matched-seed local and meaningful doses must move the intended native read path.")
    if "R4" in phases:
        gates.append("The binding event must occur in every preregistered activation seed and change the intended transition.")
    if "R6" in phases:
        gates.extend([
            "Relevant normal, structural, and crisis states must be tested with preregistered local and meaningful doses.",
            "Direction, magnitude, timing, guardrails, and empirical comparability must be reported separately.",
        ])
    if "R7" in phases:
        gates.append("The accepted sign and materiality must survive the 100k-to-1M scale check or be explicitly scale-conditional.")
    if p2_report.get("disposition") in P2_DEFECT_DISPOSITIONS:
        intent = f"repair_{p2_report['disposition']}"
    else:
        intent = "recalibrate_or_reclassify"
    return {"intent": intent, "acceptance_gates": gates}


def build_remediation_ledger(
    p1_source: str | Path | Mapping[str, Any],
    p2_source: str | Path | Mapping[str, Any],
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
    p6_source: str | Path | Mapping[str, Any],
    p7_source: str | Path | Mapping[str, Any],
    p8_source: str | Path | Mapping[str, Any],
    *,
    baseline_revision: str,
    expected_levers: Iterable[str] | None = None,
) -> dict[str, Any]:
    freeze, reports, errors = build_source_freeze(
        p1_source, p2_source, p3_source, p4_source, p5_source,
        p6_source, p7_source, p8_source,
    )
    p1_routes = set(reports["p1"].get("route_defects", ()))
    p2_by = _by_lever(reports["p2"])
    p4_by = _by_lever(reports["p4"])
    p6_by = _by_lever(reports["p6"])
    p7_by = {
        str(item["lever"]): dict(item)
        for item in reports["p7"].get("lever_ledger", ())
    }
    package_membership = _package_membership(reports["p5"])
    comparisons = _comparison_membership(reports["p7"])

    lever_order = list(p7_by)
    if len(lever_order) != 102 or len(set(lever_order)) != 102:
        errors.append("P7 lever ledger is not a unique 102-lever inventory")
    if set(p2_by) != set(lever_order):
        errors.append("P2 and P7 lever inventories differ")
    if set(p4_by) != set(lever_order):
        errors.append("P4 and P7 lever inventories differ")
    if expected_levers is not None and set(expected_levers) != set(lever_order):
        errors.append("current Registry and frozen P7 lever inventories differ")
    p2_route_defects = {
        lever for lever, item in p2_by.items()
        if item.get("disposition") == "engine_route_defect"
    }
    if p1_routes != p2_route_defects:
        errors.append("P1 and P2 route-defect inventories differ")

    mandatory = {
        lever for lever, item in p2_by.items()
        if item.get("disposition") in P2_DEFECT_DISPOSITIONS
        or item.get("validation_contract_defect")
    }
    if mandatory & BEHAVIOR_REVIEW_LEVERS:
        errors.append("mandatory repair and behavior-review classes overlap")
    unknown_candidates = BEHAVIOR_REVIEW_LEVERS - set(lever_order)
    if unknown_candidates:
        errors.append(f"behavior-review levers are absent from P7: {sorted(unknown_candidates)}")

    policies: list[dict[str, Any]] = []
    for lever in lever_order:
        p2_item = p2_by[lever]
        p4_item = p4_by[lever]
        p6_item = p6_by.get(lever)
        p7_item = p7_by[lever]
        if lever in mandatory:
            remediation_class = "mandatory_repair"
        elif lever in BEHAVIOR_REVIEW_LEVERS:
            remediation_class = "behavior_review"
        else:
            remediation_class = "no_change_evidence"

        phase_ids = _mandatory_phases(p2_item)
        if lever == "omo" and "R2" not in phase_ids:
            phase_ids.append("R2")
        if remediation_class == "behavior_review":
            phase_ids.append("R6")
        if lever in SCALE_REVALIDATION_LEVERS:
            phase_ids.append("R7")

        findings: list[dict[str, Any]] = []
        if lever in p1_routes:
            findings.append({
                "stage": "P1",
                "code": "engine_route_defect",
                "reason": "P1 lists the lever as an explicit native route defect.",
            })
        if p2_item.get("disposition") in P2_DEFECT_DISPOSITIONS:
            findings.append({
                "stage": "P2",
                "code": str(p2_item["disposition"]),
                "reason": str(p2_item["reason"]),
            })
        if p2_item.get("validation_contract_defect"):
            findings.append({
                "stage": "P2",
                "code": "validation_contract_defect",
                "reason": str(p2_item["validation_contract_defect"]),
            })
        if remediation_class == "behavior_review":
            findings.append({
                "stage": "P4",
                "code": str(p4_item["disposition"]),
                "reason": str(p4_item["reason"]),
            })
        if p6_item and (
            remediation_class == "behavior_review"
            or p6_item.get("disposition") != "finite_size_confirmed"
        ):
            findings.append({
                "stage": "P6",
                "code": str(p6_item["disposition"]),
                "reason": (
                    "Scale result retained from the frozen P6 representative ledger."
                    if not p6_item.get("reason") else str(p6_item["reason"])
                ),
            })
        findings.extend(comparisons.get(lever, ()))
        if lever == "benefit_income_floor":
            findings.append({
                "stage": "P8",
                "code": "institutional_delivery_scope_limited",
                "reason": "Delivery ingress and timing were validated, but no human performance claim was accepted.",
            })

        policies.append({
            "lever": lever,
            "owner_role": p7_item["owner_role"],
            "decision_group": p7_item["decision_group"],
            "remediation_class": remediation_class,
            "phase_ids": phase_ids,
            "package_ids_for_later_validation": package_membership.get(lever, []),
            "audit_snapshot": {
                "p2_disposition": p2_item["disposition"],
                "p4_disposition": p4_item["disposition"],
                "p6_disposition": p6_item["disposition"] if p6_item else None,
                "p7_claim_scope": p7_item["claim_scope"],
                "p7_preset_status": p7_item["recommended_ui_preset_status"],
            },
            "findings": findings,
            "repair_contract": _repair_contract(
                remediation_class, p2_item, phase_ids,
            ),
        })

    class_counts = {
        name: sum(item["remediation_class"] == name for item in policies)
        for name in ("mandatory_repair", "behavior_review", "no_change_evidence")
    }
    expected_counts = {
        "mandatory_repair": 27,
        "behavior_review": 36,
        "no_change_evidence": 39,
    }
    if class_counts != expected_counts:
        errors.append(f"primary class counts changed: {class_counts} != {expected_counts}")

    phases = []
    for definition in PHASE_DEFINITIONS:
        phase_id = definition["phase_id"]
        if phase_id == "R0":
            phase_levers = lever_order
        elif phase_id in {"R5", "R8", "R9"}:
            phase_levers = []
        else:
            phase_levers = [
                item["lever"] for item in policies if phase_id in item["phase_ids"]
            ]
        phases.append({**definition, "policy_levers": phase_levers})

    invalidation_graph = [
        {
            "repair_phase": item["phase_id"],
            "invalidates_audit_stages": item["invalidates_audit_stages"],
            "rule": (
                "Planning-only; no frozen empirical evidence is invalidated."
                if not item["invalidates_audit_stages"] else
                "Any material implementation change in this phase requires the listed audit stages to be regenerated before claims are restored."
            ),
        }
        for item in phases
    ]
    evidence = {
        "source_freeze": freeze,
        "policies": policies,
        "phases": phases,
        "invalidation_graph": invalidation_graph,
    }
    payload = {
        "schema_version": R0_SCHEMA_VERSION,
        "status": R0_ACCEPTED_STATUS if not errors else "failed",
        "baseline_revision": baseline_revision,
        "errors": errors,
        "counts": {
            "levers": len(policies),
            **class_counts,
            "mandatory_phase_occurrences": sum(
                item["remediation_class"] == "mandatory_repair"
                for item in policies
                for _phase in item["phase_ids"]
            ),
            "phases": len(phases),
        },
        "source_freeze": freeze,
        "policies": policies,
        "phases": phases,
        "invalidation_graph": invalidation_graph,
        "limitations": [
            "R0 changes no Registry domain, native route, economic equation, scenario, or controller behavior.",
            "The 36 behavior candidates are hypotheses for retesting, not a declaration that all 36 mechanisms are broken.",
            "The 39 no-change entries have no current modification evidence; they remain subject to final regression and future evidence.",
            "P8 human paths are transport fixtures rather than participant performance data, and its RL run is only a transfer probe.",
        ],
        "protocol": {
            "legacy_python_simulator_used": False,
            "native_simulation_executed": False,
            "network_fetch_during_acceptance": False,
            "planning_only": True,
            "test_workers": 8,
        },
        "hashes": {
            "r0_evidence": canonical_hash(evidence),
        },
    }
    payload["hashes"]["r0_acceptance"] = canonical_hash({
        "schema_version": payload["schema_version"],
        "status": payload["status"],
        "baseline_revision": baseline_revision,
        "errors": errors,
        "counts": payload["counts"],
        "evidence": payload["hashes"]["r0_evidence"],
        "limitations": payload["limitations"],
        "protocol": payload["protocol"],
    })
    return payload


def validate_remediation_ledger(payload: Mapping[str, Any]) -> list[str]:
    """Validate a serialized R0 ledger without access to ignored audit files."""
    errors: list[str] = []
    policies = list(payload.get("policies", ()))
    levers = [item.get("lever") for item in policies]
    if len(levers) != 102 or len(set(levers)) != 102:
        errors.append("ledger must contain 102 unique levers")
    counts = {
        name: sum(item.get("remediation_class") == name for item in policies)
        for name in ("mandatory_repair", "behavior_review", "no_change_evidence")
    }
    expected = {"mandatory_repair": 27, "behavior_review": 36, "no_change_evidence": 39}
    if counts != expected:
        errors.append(f"serialized class counts changed: {counts}")
    if len(payload.get("phases", ())) != 10:
        errors.append("ledger must define phases R0-R9")
    if [item.get("phase_id") for item in payload.get("phases", ())] != [f"R{i}" for i in range(10)]:
        errors.append("phase ordering must be R0 through R9")
    for item in policies:
        contract = item.get("repair_contract", {})
        if not contract.get("intent") or not contract.get("acceptance_gates"):
            errors.append(f"{item.get('lever')}: repair contract is incomplete")
    evidence = {
        "source_freeze": payload.get("source_freeze"),
        "policies": policies,
        "phases": payload.get("phases"),
        "invalidation_graph": payload.get("invalidation_graph"),
    }
    if canonical_hash(evidence) != payload.get("hashes", {}).get("r0_evidence"):
        errors.append("R0 evidence hash does not reproduce")
    acceptance = canonical_hash({
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "baseline_revision": payload.get("baseline_revision"),
        "errors": payload.get("errors"),
        "counts": payload.get("counts"),
        "evidence": payload.get("hashes", {}).get("r0_evidence"),
        "limitations": payload.get("limitations"),
        "protocol": payload.get("protocol"),
    })
    if acceptance != payload.get("hashes", {}).get("r0_acceptance"):
        errors.append("R0 acceptance hash does not reproduce")
    return errors


def render_remediation_markdown(payload: Mapping[str, Any]) -> str:
    """Render the committed, human-reviewable R0 plan."""
    counts = payload["counts"]
    policies = list(payload["policies"])
    lines = [
        "# Policy Remediation Plan v39",
        "",
        "## R0 acceptance",
        "",
        f"- Status: `{payload['status']}`",
        f"- Baseline revision: `{payload['baseline_revision']}`",
        f"- R0 acceptance hash: `{payload['hashes']['r0_acceptance']}`",
        f"- Frozen P0 root: `{payload['source_freeze']['p0_root_hash']}`",
        "- Scope: deterministic planning and provenance only; no simulator or policy behavior changed.",
        "",
        "## Executive decision",
        "",
        f"The frozen P0-P8 evidence covers **{counts['levers']}** canonical Policy levers. "
        f"R0 classifies **{counts['mandatory_repair']}** as mandatory repairs, "
        f"**{counts['behavior_review']}** as behavior-review candidates, and "
        f"**{counts['no_change_evidence']}** as no-change entries under current evidence.",
        "",
        "A behavior-review label does not mean that a mechanism is broken. It means its "
        "accepted effect, dose, state dependence, empirical direction, safety, or scale "
        "scope must be retested after upstream repairs. A no-change label is also not a "
        "permanent exemption; those levers remain under the final regression gate.",
        "",
        "## Evidence boundary",
        "",
    ]
    for note in payload["source_freeze"]["provenance_notes"]:
        lines.append(f"- {note}")
    lines.extend(["", "### Frozen acceptance identities", "", "| Stage | Status | Acceptance hash | Source revision |", "|---|---|---|---|"])
    for stage in (f"p{i}" for i in range(1, 9)):
        source_revision = payload["source_freeze"]["source_revisions"].get(stage)
        lines.append(
            f"| {stage.upper()} | `{payload['source_freeze']['statuses'][stage]}` | "
            f"`{payload['source_freeze']['acceptance_hashes'][stage]}` | "
            f"`{source_revision or 'not exposed'}` |"
        )
    lines.extend([
        "",
        "Only `CR_DEMAND_RECESSION` is currently accepted for player-facing policy-efficacy claims. "
        "R5 must repair the other ten crisis scenarios before they can be used to judge a policy.",
        "",
        "## Ordered milestones",
        "",
        "| Phase | Purpose | Policy queue | Invalidates |",
        "|---|---|---:|---|",
    ])
    for phase in payload["phases"]:
        invalidates = ", ".join(phase["invalidates_audit_stages"]) or "none"
        lines.append(
            f"| {phase['phase_id']} | {phase['title']} | {len(phase['policy_levers'])} | {invalidates} |"
        )
    for phase in payload["phases"]:
        lines.extend([
            "",
            f"### {phase['phase_id']}: {phase['title']}",
            "",
            phase["purpose"],
            "",
            "Exit criteria:",
            "",
        ])
        lines.extend(f"- {item}" for item in phase["exit_criteria"])
        if phase["policy_levers"] and phase["phase_id"] != "R0":
            lines.extend(["", "Queue:", "", ", ".join(f"`{lever}`" for lever in phase["policy_levers"])])
    lines.extend([
        "",
        "## Evidence invalidation rule",
        "",
        "Frozen audit results remain historical evidence, but a material repair removes their authority "
        "for current product claims. The affected stages below must be regenerated before a repaired "
        "lever, crisis, package, UI statement, or controller comparison is accepted again.",
        "",
        "| Repair phase | Audit stages to regenerate |",
        "|---|---|",
    ])
    for edge in payload["invalidation_graph"]:
        stages = ", ".join(edge["invalidates_audit_stages"]) or "none"
        lines.append(f"| {edge['repair_phase']} | {stages} |")

    for classification, title in (
        ("mandatory_repair", "Mandatory repair ledger"),
        ("behavior_review", "Behavior-review ledger"),
        ("no_change_evidence", "No-change ledger under current evidence"),
    ):
        lines.extend([
            "",
            f"## {title}",
            "",
            "| Lever | Owner / group | Phases | Frozen dispositions | Repair intent |",
            "|---|---|---|---|---|",
        ])
        for item in policies:
            if item["remediation_class"] != classification:
                continue
            snapshot = item["audit_snapshot"]
            dispositions = "/".join(
                str(value) for value in (
                    snapshot["p2_disposition"], snapshot["p4_disposition"], snapshot["p6_disposition"],
                ) if value is not None
            )
            lines.append(
                f"| `{item['lever']}` | `{item['owner_role']}` / `{item['decision_group']}` | "
                f"{', '.join(item['phase_ids']) or 'regression only'} | `{dispositions}` | "
                f"`{item['repair_contract']['intent']}` |"
            )

    lines.extend(["", "## R0 non-goals and stop rule", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.extend([
        "- R0 stops after this ledger, its machine-readable twin, focused tests, and an eight-worker acceptance run are committed.",
        "- R1 must start on a new milestone decision; R0 does not silently include validation or engine repairs.",
        "",
    ])
    return "\n".join(lines)


def write_remediation_artifacts(
    payload: Mapping[str, Any], json_path: str | Path, markdown_path: str | Path,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_temporary = json_target.with_suffix(json_target.suffix + ".tmp")
    markdown_temporary = markdown_target.with_suffix(
        markdown_target.suffix + ".tmp"
    )
    json_temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_temporary.write_text(
        render_remediation_markdown(payload), encoding="utf-8",
    )
    json_temporary.replace(json_target)
    markdown_temporary.replace(markdown_target)
