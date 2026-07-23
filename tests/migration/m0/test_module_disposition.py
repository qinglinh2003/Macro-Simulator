from __future__ import annotations

import json
from pathlib import Path

from scripts.cpp_migration.inventory import _module_paths


ROOT = Path(__file__).resolve().parents[3]


def test_every_maintained_runtime_or_client_file_has_a_disposition():
    inventory = json.loads(
        (ROOT / "schemas/m0/inventory/modules.json").read_text(encoding="utf-8")
    )
    actual = {row["source_path"] for row in inventory["rows"]}
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in _module_paths()
    }
    assert actual == expected
    assert inventory["metadata"]["unresolved_count"] == 0
    assert all(
        row["action"]
        in {
            "adapter",
            "keep",
            "keep_client",
            "oracle_only",
            "port",
            "port_or_adapter",
            "wrap_native_worker",
        }
        for row in inventory["rows"]
    )
