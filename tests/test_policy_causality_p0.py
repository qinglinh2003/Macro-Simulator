"""Acceptance tests for Policy causality audit milestone P0."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_catalog import (
    ACTIVATION_FIXTURES,
    CRISIS_ROLES,
    FAILURE_TAXONOMY,
    GROUP_SPECS,
    LEVER_PROXIMAL_METRICS,
    METRIC_MATERIALITY,
    SCENARIOS,
)
from macro_sim.diagnostics.policy_contracts import (
    build_contracts,
    build_inventory,
    build_p0_payload,
    render_p0_markdown,
    verify_p0,
)


ROOT = Path(__file__).resolve().parents[1]
FROZEN_P0_ROOT_HASH = "6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6"


def _maintained_metric_ids() -> set[str]:
    ids = set(re.findall(
        r'"(metric\.[A-Za-z0-9_.]+)"',
        (ROOT / "native/src/reporting/m10.cpp").read_text(encoding="utf-8"),
    ))
    sources = (
        ROOT / "native/include/macro_sim/reporting/m10_metric_sources.inc"
    ).read_text(encoding="utf-8")
    prefixes = {
        "M4_SOURCE": "metric.source.m4.",
        "M5_SOURCE": "metric.source.m5.",
        "M6_SOURCE": "metric.source.m6.",
        "M7_SOURCE": "metric.source.m7.",
        "M8_ENERGY_SOURCE": "metric.source.m8.energy.",
        "M8_HOUSING_SOURCE": "metric.source.m8.housing.",
        "M9_COUNTRY_SOURCE": "metric.source.m9.country.",
        "M9_WORLD_SOURCE": "metric.source.m9.world.",
    }
    for macro, prefix in prefixes.items():
        ids.update(
            prefix + field
            for field in re.findall(
                rf"MACRO_SIM_{macro}\((\w+),",
                sources,
            )
        )
    ids.update(re.findall(
        r'"(metric\.[A-Za-z0-9_.]+)"',
        (
            ROOT / "native/include/macro_sim/reporting/m10_dashboard_metrics.inc"
        ).read_text(encoding="utf-8"),
    ))
    national_accounts = (
        ROOT / "native/include/macro_sim/reporting/m10_national_accounts.inc"
    ).read_text(encoding="utf-8")
    ids.update(
        "metric.economy.na." + field
        for field in re.findall(
            r"MACRO_SIM_NATIONAL_ACCOUNT\((\w+),",
            national_accounts,
        )
    )
    return ids


def test_p0_has_complete_registry_contract_and_group_coverage():
    assert verify_p0() == []
    assert len(REGISTRY) == 102
    assert len(build_inventory()) == 102
    assert len(build_contracts()) == 102
    assert set(REGISTRY) == set(LEVER_PROXIMAL_METRICS)
    assert len(GROUP_SPECS) == 12
    assert Counter(
        (item.owner_role, item.decision_group) for item in REGISTRY.values()
    ) == Counter({
        ("treasury", "fiscal_stance"): 7,
        ("treasury", "tax_and_transfers"): 18,
        ("treasury", "debt_management"): 3,
        ("central_bank", "monetary_stance"): 13,
        ("central_bank", "liquidity_operations"): 6,
        ("central_bank", "fx_operations"): 5,
        ("regulator", "macroprudential"): 21,
        ("regulator", "structural_law"): 7,
        ("external_affairs", "trade_and_migration"): 9,
        ("energy", "energy_operations"): 5,
        ("energy", "energy_structure"): 1,
        ("labor_social", "labor_and_welfare"): 7,
    })


def test_every_contract_has_treatments_activation_metrics_and_full_crisis_matrix():
    for contract in build_contracts():
        assert contract.treatment_batches
        assert contract.activation_fixture in ACTIVATION_FIXTURES
        assert contract.mechanism_proximal_metrics
        assert set(contract.crisis_roles) == set(SCENARIOS)
        assert set(contract.crisis_roles.values()) <= CRISIS_ROLES
        assert set(contract.crisis_roles.values()) != {"not_applicable"}
        assert contract.operating_horizon_days > 0
        assert contract.tradeoff_metrics
        for batch in contract.treatment_batches:
            assert contract.lever in {name for name, _value in batch.actions}
        for metric_id in contract.materiality_metrics:
            assert metric_id in METRIC_MATERIALITY


def test_linked_regime_treatments_are_atomic_batches():
    contracts = {item.lever: item for item in build_contracts()}
    manual_batches = contracts["manual_policy_rate"].treatment_batches
    assert all(
        dict(batch.actions)["monetary_regime"] == "manual"
        for batch in manual_batches
    )
    regime_batches = contracts["monetary_regime"].treatment_batches
    manual = next(
        batch for batch in regime_batches
        if dict(batch.actions).get("monetary_regime") == "manual"
    )
    assert dict(manual.actions)["manual_policy_rate"] == 1.0e-4
    peg = next(
        batch for batch in contracts["fx_regime"].treatment_batches
        if dict(batch.actions).get("fx_regime") == "peg"
    )
    assert dict(peg.actions)["peg_anchor"] == 1


def test_every_declared_metric_is_maintained_by_native_reporting():
    missing = set(METRIC_MATERIALITY) - _maintained_metric_ids()
    assert not missing, sorted(missing)


def test_scenarios_and_failures_are_closed_and_actionable():
    assert len(SCENARIOS) == 11
    assert {item.readiness for item in SCENARIOS.values()} == {
        "ready_to_calibrate", "conditional", "blocked"
    }
    assert len(FAILURE_TAXONOMY) == 28
    assert all(item.default_disposition for item in FAILURE_TAXONOMY.values())


def test_payload_is_accepted_deterministic_and_frozen():
    first = build_p0_payload()
    second = build_p0_payload()
    assert first == second
    assert first["status"] == "accepted"
    assert first["errors"] == []
    assert first["counts"]["unmapped_levers"] == 0
    assert first["counts"]["validation_errors"] == 0
    assert first["hashes"]["p0_root"] == FROZEN_P0_ROOT_HASH


def test_markdown_contains_all_levers_and_acceptance_identity():
    payload = build_p0_payload()
    markdown = render_p0_markdown(payload)
    assert "Status: **accepted**" in markdown
    assert payload["hashes"]["p0_root"] in markdown
    for name in REGISTRY:
        assert f"`{name}`" in markdown
