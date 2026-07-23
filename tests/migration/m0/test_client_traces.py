from __future__ import annotations

from pathlib import Path

from scripts.cpp_migration.client_traces import build_client_contracts
from scripts.cpp_migration.common import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[3]


def test_checked_client_contracts_match_current_runtime_inventories():
    expected = build_client_contracts()
    path = ROOT / "tests/fixtures/m0/clients/contracts.json"
    assert path.read_bytes() == canonical_json_bytes(expected)
    rows = {row["id"]: row for row in expected["rows"]}
    assert set(rows) == {
        "client.controller.shared-transaction",
        "client.desktop.current-flow",
        "client.persistence.python-oracle",
        "client.rl.fiscal-stabilization-v1",
    }
    assert len(rows["client.rl.fiscal-stabilization-v1"]["observation_ids"]) == 101
    assert len(rows["client.desktop.current-flow"]["observation_ids"]) == 42
    assert len(rows["client.controller.shared-transaction"]["occupants"]) == 6
