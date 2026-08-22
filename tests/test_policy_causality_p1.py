"""Acceptance tests for Policy causality audit milestone P1."""

from __future__ import annotations

from pathlib import Path

from macro_sim.core.native_policy_routes import (
    ENGINE_ROUTE_DEFECT,
    NATIVE_POLICY_ROUTES,
    NATIVE_ROUTE_DEFECTS,
    ROUTED,
)
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_contracts import build_inventory
from macro_sim.diagnostics.policy_routing import (
    build_full_route_batch,
    build_p1_payload,
    build_route_ledger,
    verify_p1_static,
)


ROOT = Path(__file__).resolve().parents[1]
FROZEN_ROUTE_LEDGER_HASH = "e1eb003349328505e77eee6b556824bba67959bf8e806231b4cb9bc9ce52948a"
FROZEN_P1_ROOT_HASH = "385d738195f2260a57694c12293c1a267bf0fd3cc4221ffb47b489d5d5932906"


def test_route_catalog_covers_registry_and_generated_contract() -> None:
    assert verify_p1_static() == []
    assert len(REGISTRY) == 102
    assert len(NATIVE_POLICY_ROUTES) == 102
    assert len(build_route_ledger()) == 102
    assert set(NATIVE_POLICY_ROUTES) == set(REGISTRY)


def test_every_routed_read_point_has_a_live_cpp_source_anchor() -> None:
    for name, route in NATIVE_POLICY_ROUTES.items():
        assert REGISTRY[name].read_point == route.read_point
        assert ".py" not in REGISTRY[name].read_point
        if route.disposition != ROUTED:
            continue
        source = ROOT / route.source_path
        assert source.is_file()
        assert route.source_anchor in source.read_text(encoding="utf-8")
        assert route.read_phase


def test_route_defects_are_explicit_and_exact() -> None:
    assert NATIVE_ROUTE_DEFECTS == {
        "fiscal_uses_national_accounts_gdp",
        "mortgage_min_capital_ratio",
        "mortgage_risk_weight",
    }
    for name in NATIVE_ROUTE_DEFECTS:
        route = NATIVE_POLICY_ROUTES[name]
        assert route.disposition == ENGINE_ROUTE_DEFECT
        assert route.defect_reason
        assert not route.source_path
        assert not route.source_anchor
        assert not route.read_phase


def test_full_route_batch_changes_every_lever_and_closes_linked_state() -> None:
    baseline = {
        row["lever"]: row["reference_baseline"]
        for row in build_inventory()
    }
    actions = build_full_route_batch(baseline)
    assert len(actions) == 102
    assert {item["lever"] for item in actions} == set(REGISTRY)
    assert all(item["economy_id"] == 0 for item in actions)
    action_values = {item["lever"]: item["value"] for item in actions}
    assert action_values["monetary_regime"] == "manual"
    assert action_values["manual_policy_rate"] is not None
    assert action_values["manual_policy_rate"] <= action_values["r_max"]
    assert action_values["fx_regime"] == "peg"
    assert action_values["peg_anchor"] == 1


def test_static_payload_is_deterministic_and_frozen() -> None:
    first = build_p1_payload()
    second = build_p1_payload()
    assert first == second
    assert first["status"] == "incomplete"
    assert first["native_smoke"] is None
    assert first["counts"] == {
        "levers": 102,
        "generated_native_routes": 102,
        "native_read_points": 99,
        "explicit_route_defects": 3,
        "static_errors": 0,
        "dynamic_errors": 0,
    }
    assert first["hashes"]["route_ledger"] == FROZEN_ROUTE_LEDGER_HASH
    assert first["hashes"]["p1_root"] == FROZEN_P1_ROOT_HASH
    assert first["hashes"]["native_smoke_evidence"] is None
    assert first["hashes"]["p1_acceptance"] is None
