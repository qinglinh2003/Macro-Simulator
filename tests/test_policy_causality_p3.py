"""Acceptance tests for the P3 native scenario-library runner."""

from __future__ import annotations

from macro_sim.diagnostics.policy_catalog import (
    ORDINARY_SCENARIOS,
    SCENARIOS,
    STRUCTURAL_SCENARIOS,
)
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    SEVERITIES,
    STATE_MANIFESTS,
    analyze_crisis,
    validate_manifest_catalogs,
)


def _series(value: float, days: int = 12) -> list[float]:
    return [value] * days


def _synthetic_run(manifest, seed: int, losses: dict[str, float]):
    metrics = set(manifest.metric_ids)
    control = {metric_id: _series(10.0) for metric_id in metrics}
    control["metric.shock.active_count"] = _series(0.0)
    severities = {}
    for severity in SEVERITIES:
        treatment = {metric_id: list(values) for metric_id, values in control.items()}
        for rule in (*manifest.entry_rules, *manifest.propagation_rules):
            delta = max(rule.absolute_floor * 2.0, 2.0)
            treatment[rule.metric_id] = _series(
                10.0 + delta if rule.direction == "increase" else 10.0 - delta
            )
        primary = manifest.primary_damage
        delta = losses[severity]
        damage_path = [delta] * 6 + [delta * factor for factor in (0.60, 0.40, 0.20, 0.10, 0.0, 0.0)]
        treatment[primary.metric_id] = [
            10.0 + value if primary.direction == "increase" else 10.0 - value
            for value in damage_path
        ]
        treatment["metric.shock.active_count"] = [1.0] * 6 + [0.0] * 6
        severities[severity] = {
            "series": treatment,
            "integrity": {"passed": True},
            "terminal_active_shocks": 0.0,
            "tape_hash": f"{manifest.scenario_id}-{severity}",
            "replay": {"passed": True} if severity == "moderate" and seed == 1 else None,
        }
    return {
        "scenario_id": manifest.scenario_id,
        "seed": seed,
        "common_checkpoint_sha256": f"checkpoint-{seed}",
        "control": {"series": control, "integrity": {"passed": True}},
        "severities": severities,
    }


def test_p3_manifests_exactly_cover_the_frozen_p0_catalogs() -> None:
    assert set(STATE_MANIFESTS) == set(ORDINARY_SCENARIOS) | set(STRUCTURAL_SCENARIOS)
    assert set(CRISIS_MANIFESTS) == set(SCENARIOS)
    assert validate_manifest_catalogs() == []


def test_every_runnable_crisis_freezes_three_ordered_tapes() -> None:
    for manifest in CRISIS_MANIFESTS.values():
        if manifest.readiness == "blocked":
            assert manifest.shock_legs == ()
            continue
        assert manifest.shock_legs
        assert manifest.horizon_days > manifest.maximum_shock_days
        for leg in manifest.shock_legs:
            assert 0.0 < leg.magnitude <= 0.95
            assert leg.duration_days >= 1
            assert f"metric.shock.severity.{leg.kind}" in manifest.metric_ids


def test_analysis_requires_six_of_eight_matched_seeds_and_ordered_severity() -> None:
    manifest = CRISIS_MANIFESTS["CR_DEMAND_RECESSION"]
    assert manifest.primary_damage.statistic == "peak"
    runs = [
        _synthetic_run(manifest, seed, {"mild": 2.0, "moderate": 3.0, "severe": 4.0})
        for seed in range(1, 9)
    ]
    report = analyze_crisis(manifest, runs)
    assert report["accepted"] is True
    assert report["entry_gate"]["passed_seed_count"] == 8
    assert report["severity_gate"]["ordered_seed_count"] == 8
    assert report["integrity_gate"]["replay_evidence_count"] == 1


def test_analysis_rejects_a_non_ordered_or_treatment_only_label() -> None:
    manifest = CRISIS_MANIFESTS["CR_DEMAND_RECESSION"]
    runs = [
        _synthetic_run(manifest, seed, {"mild": 3.0, "moderate": 2.0, "severe": 4.0})
        for seed in range(1, 9)
    ]
    report = analyze_crisis(manifest, runs)
    assert report["accepted"] is False
    assert report["severity_gate"]["passed"] is False
    assert report["disposition"] == "crisis_severity_failure"


def test_blocked_sovereign_scenario_never_runs_or_enters_p4() -> None:
    manifest = CRISIS_MANIFESTS["CR_SOVEREIGN_STRESS"]
    report = analyze_crisis(manifest, ())
    assert report["accepted"] is False
    assert report["disposition"] == "blocked_engine_gap"
    assert "risk-premium" in report["reason"]
