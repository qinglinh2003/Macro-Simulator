from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INVENTORY_ROOT = ROOT / "schemas/m0/inventory"


def _inventory(name: str) -> dict:
    return json.loads((INVENTORY_ROOT / f"{name}.json").read_text(encoding="utf-8"))


def test_config_and_capability_tripwires():
    config = _inventory("config")
    capabilities = _inventory("capabilities")
    assert config["metadata"]["root_config_field_count"] == 368
    assert config["metadata"]["total_tunable_count"] == 453
    assert capabilities["metadata"] == {
        "config_mechanism_count": 61,
        "dependency_source": "reviewed M0 capability map",
        "world_mechanism_count": 5,
    }
    root_fields = [
        row for row in config["rows"] if row["declaring_type"] == "Config"
    ]
    assert len(root_fields) == 368
    assert len({row["field_name"] for row in root_fields}) == 368
    assert not [
        row for row in config["rows"] if row["classification"] == "pending_ruling"
    ]


def test_policy_tripwires_and_aliases():
    policy = _inventory("policy")
    metadata = policy["metadata"]
    assert metadata["lever_count"] == 102
    assert metadata["domestic_count"] == 88
    assert metadata["external_count"] == 14
    assert metadata["semantic_counts"] == {
        "immediate": 90,
        "new-contracts-only": 7,
        "state-transition": 5,
    }
    assert metadata["seats"] == [
        "central_bank",
        "energy",
        "external_affairs",
        "labor_social",
        "regulator",
        "treasury",
    ]
    assert len(metadata["decision_groups"]) == 12
    assert policy["aliases"] == {
        "firm_capital_haircut": "regulatory_firm_capital_haircut",
        "firm_inventory_haircut": "regulatory_firm_inventory_haircut",
        "land_convexity": "land_fee_stock_elasticity",
        "policy_rate_override": "manual_policy_rate",
    }
    assert all(row["runtime_read_point"] for row in policy["rows"])
    assert all(row["seat"] in metadata["seats"] for row in policy["rows"])


def test_shock_observation_and_rl_tripwires():
    shocks = _inventory("shocks")
    observations = _inventory("observations")
    assert [row["shock_kind"] for row in shocks["rows"]] == [
        "capital_destruction",
        "capital_outflow_pressure",
        "credit_supply",
        "energy_capacity",
        "export_capacity",
        "household_demand",
        "import_capacity",
        "labor_availability",
        "productivity",
        "sovereign_risk_premium",
    ]
    metadata = observations["metadata"]
    assert metadata["release_series_count"] == 44
    assert metadata["fiscal_v1_feature_count"] == 101
    assert metadata["fiscal_v1_action_dimension_count"] == 1
    assert metadata["fiscal_v1_direction_count"] == 3
    features = [
        row for row in observations["rows"] if row["kind"] == "rl_feature"
    ]
    assert len(features) == 101
    assert [row["ordinal"] for row in features] == list(range(101))


def test_every_row_has_existing_evidence_and_no_unresolved_status():
    for path in sorted(INVENTORY_ROOT.glob("*.json")):
        inventory = json.loads(path.read_text(encoding="utf-8"))
        ids = [row["id"] for row in inventory["rows"]]
        assert ids == sorted(ids), path.name
        assert len(ids) == len(set(ids)), path.name
        for row in inventory["rows"]:
            assert (ROOT / row["source_path"]).is_file(), row["id"]
            assert row["source_symbol"], row["id"]
            assert row["owner_milestone"], row["id"]
            assert row["status"] != "unresolved", row["id"]


def test_m4_verticals_reference_known_contracts():
    inventories = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in INVENTORY_ROOT.glob("*.json")
    }
    ids = {
        row["id"]
        for inventory in inventories.values()
        for row in inventory["rows"]
    }
    m4 = inventories["m4_v0_v1"]
    assert [row["id"] for row in m4["rows"]] == ["m4.v0", "m4.v1"]
    for vertical in m4["rows"]:
        for field in ("phases", "metrics", "invariants"):
            assert set(vertical[field]) <= ids
