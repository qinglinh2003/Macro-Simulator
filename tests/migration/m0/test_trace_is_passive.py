from __future__ import annotations

from pathlib import Path

import pytest

from macro_sim.checkpoint import state_digest
from macro_sim.config import Config
from macro_sim.core.phase_trace import (
    JsonLinesTraceSink,
    MemoryTraceSink,
    TraceSpec,
    install_phase_trace,
)
from macro_sim.economy import Economy


def _engine() -> Economy:
    return Economy(
        Config.v124(
            n_firms_c=3,
            n_firms_k=1,
            n_households=12,
            n_ticks=4,
            seed=19,
        )
    )


def _advance(engine: Economy, ticks: int = 4) -> str:
    for _ in range(ticks):
        engine.step()
    return state_digest(engine)


def test_disabled_memory_and_json_trace_have_identical_semantics(tmp_path: Path):
    plain = _engine()
    memory_engine = _engine()
    json_engine = _engine()
    spec = TraceSpec("passive-proof", "refactor-v124")
    memory = MemoryTraceSink(spec)
    path = tmp_path / "trace.jsonl"
    install_phase_trace(memory_engine, memory)
    install_phase_trace(json_engine, JsonLinesTraceSink(spec, path))

    digests = {
        _advance(plain),
        _advance(memory_engine),
        _advance(json_engine),
    }

    assert len(digests) == 1
    assert memory.canonical_bytes() == path.read_bytes()
    assert not [name for name in vars(memory_engine) if name.startswith("_m0")]
    assert not [name for name in vars(json_engine) if name.startswith("_m0")]


def test_trace_does_not_change_next_step_continuation():
    plain = _engine()
    traced = _engine()
    install_phase_trace(
        traced,
        MemoryTraceSink(TraceSpec("continuation-proof", "refactor-v124")),
    )

    assert _advance(plain, 2) == _advance(traced, 2)
    assert _advance(plain, 1) == _advance(traced, 1)


def test_json_lines_sink_refuses_ambiguous_append(tmp_path: Path):
    path = tmp_path / "existing.jsonl"
    path.write_text("existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="existing trace"):
        JsonLinesTraceSink(TraceSpec("run", "scenario"), path)
