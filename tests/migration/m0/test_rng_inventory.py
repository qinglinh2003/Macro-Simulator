from __future__ import annotations

import json
from pathlib import Path

from macro_sim.config import Config
from macro_sim.core.phase_trace import (
    MemoryTraceSink,
    TraceSpec,
    install_phase_trace,
)
from macro_sim.economy import Economy
from scripts.cpp_migration.common import canonical_json_bytes
from scripts.cpp_migration.inventory import build_rng_inventory


ROOT = Path(__file__).resolve().parents[3]


def test_static_rng_inventory_accounts_for_all_current_scan_results():
    expected = build_rng_inventory()
    checked = json.loads(
        (ROOT / "schemas/m0/inventory/rng.json").read_text(encoding="utf-8")
    )
    assert canonical_json_bytes(expected) == canonical_json_bytes(checked)
    assert expected["metadata"]["stream_count"] > 0
    assert expected["metadata"]["draw_site_count"] > 0
    assert all(row["source_path"].startswith("macro_sim/") for row in expected["rows"])


def test_trace_rng_metadata_uses_named_streams_and_state_digests():
    economy = Economy(
        Config.v124(
            n_firms_c=2,
            n_firms_k=1,
            n_households=8,
            n_ticks=1,
            seed=23,
        )
    )
    sink = MemoryTraceSink(TraceSpec("rng-proof", "refactor-v124"))
    install_phase_trace(economy, sink)

    economy.step()

    metadata = sink.records[0]["rng_metadata"]
    assert metadata["root_seeds"] == [23]
    assert metadata["streams"]
    assert all(stream["attribute"] for stream in metadata["streams"])
    assert all(len(stream["state_digest"]) == 64 for stream in metadata["streams"])
