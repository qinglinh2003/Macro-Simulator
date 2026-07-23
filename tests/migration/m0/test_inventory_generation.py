from __future__ import annotations

import json
from pathlib import Path

from scripts.cpp_migration.common import canonical_json_bytes
from scripts.cpp_migration.inventory import (
    INVENTORY_FAMILIES,
    build_all_inventories,
    build_hash_lock,
    validate_cross_references,
)


ROOT = Path(__file__).resolve().parents[3]


def test_checked_inventories_are_current_canonical_outputs():
    inventories = build_all_inventories()
    validate_cross_references(inventories)
    assert tuple(inventories) == INVENTORY_FAMILIES
    for family, value in inventories.items():
        path = ROOT / "schemas/m0/inventory" / f"{family}.json"
        assert path.read_bytes() == canonical_json_bytes(value), family


def test_hash_lock_is_current():
    expected = build_hash_lock()
    actual = json.loads(
        (ROOT / "schemas/m0/hashes.lock.json").read_text(encoding="utf-8")
    )
    assert actual == expected
    assert len(actual["aggregate_sha256"]) == 64
    assert all(len(row["sha256"]) == 64 for row in actual["artifacts"])
