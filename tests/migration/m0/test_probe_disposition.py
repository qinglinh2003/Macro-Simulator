from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_probe_dispositions_are_typed_and_complete():
    inventory = json.loads(
        (ROOT / "schemas/m0/inventory/probes.json").read_text(encoding="utf-8")
    )
    allowed = {
        "typed_public",
        "typed_privileged",
        "derived_from_snapshot",
        "python_oracle_only",
        "retire",
    }
    assert inventory["metadata"]["unresolved_count"] == 0
    assert inventory["rows"]
    assert all(row["disposition"] in allowed for row in inventory["rows"])
    assert all(row["snapshot_epoch"] for row in inventory["rows"])
