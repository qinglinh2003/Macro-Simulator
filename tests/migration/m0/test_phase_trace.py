from __future__ import annotations

from macro_sim.config import Config
from macro_sim.core.phase_trace import (
    MemoryTraceSink,
    TraceSpec,
    install_phase_trace,
)
from macro_sim.economy import Economy
from macro_sim.world import World
from scripts.cpp_migration.trace_compare import first_trace_divergence


ECONOMY_PATH = [
    "B0",
    "E0",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "E8",
    "E9",
    "W.CommitBoundary",
    "W.Publish",
]


def _config(seed: int = 7) -> Config:
    return Config.v124(
        n_firms_c=3,
        n_firms_k=1,
        n_households=12,
        n_ticks=2,
        seed=seed,
    )


def test_bare_economy_emits_one_complete_registered_path():
    economy = Economy(_config())
    sink = MemoryTraceSink(TraceSpec("economy-path", "refactor-v124"))
    install_phase_trace(economy, sink)

    economy.step()

    assert [record["phase_code"] for record in sink.records] == ECONOMY_PATH
    assert all(record["terminal_status"] == "ok" for record in sink.records)
    assert all(len(record["posting_digest"]) == 64 for record in sink.records)
    validation = next(
        record for record in sink.records if record["phase_code"] == "E8"
    )
    assert validation["invariant_results"]
    assert {item["status"] for item in validation["invariant_results"]} == {
        "passed"
    }


def test_coupled_world_emits_barrier_and_both_economy_paths():
    world = World([_config(10), _config(11)], base_seed=10, couple=True)
    sink = MemoryTraceSink(TraceSpec("world-path", "world-n2"))
    install_phase_trace(world, sink)

    world.step()

    codes = [record["phase_code"] for record in sink.records]
    assert codes == [
        "B0",
        "E0",
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "E0",
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "W0",
        "W.DealerSettlement",
        "W.ValidateGlobal",
        "E6",
        "E7",
        "E8",
        "E9",
        "E6",
        "E7",
        "E8",
        "E9",
        "W.CommitBoundary",
        "W.Publish",
    ]
    global_validation = next(
        record
        for record in sink.records
        if record["phase_code"] == "W.ValidateGlobal"
    )
    assert global_validation["invariant_results"] == [
        {
            "id": "invariant.world.dealer-flow-passthrough",
            "status": "passed",
        }
    ]


def test_first_divergence_reports_phase_field_and_rule():
    expected = [{"phase_id": "phase.economy.open-books", "selected_state": {"x": 1}}]
    actual = [{"phase_id": "phase.economy.open-books", "selected_state": {"x": 2}}]

    difference = first_trace_divergence(expected, actual)

    assert difference is not None
    assert difference.record_index == 0
    assert difference.phase_id == "phase.economy.open-books"
    assert difference.field_path == "$.selected_state.x"
    assert difference.comparison_rule == "exact_semantic"
