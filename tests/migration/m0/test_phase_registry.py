from __future__ import annotations

from pathlib import Path

import yaml

from macro_sim.core.phases import PHASES


ROOT = Path(__file__).resolve().parents[3]


def test_runtime_phase_registry_matches_reviewed_manifest():
    raw = yaml.safe_load(
        (ROOT / "schemas/m0/manifests/phases.yaml").read_text(encoding="utf-8")
    )
    manifest = {
        row["id"]: (
            row["phase_code"],
            row["order"],
            row["scope"],
            row["snapshot_after"],
        )
        for row in raw["rows"]
    }
    runtime = {
        phase.id: (
            phase.code,
            phase.ordinal,
            phase.scope,
            phase.snapshot_epoch,
        )
        for phase in PHASES
    }
    assert runtime == manifest


def test_phase_ids_codes_and_ordinals_are_unique_and_ordered():
    assert len({phase.id for phase in PHASES}) == len(PHASES)
    assert len({phase.code for phase in PHASES}) == len(PHASES)
    assert [phase.ordinal for phase in PHASES] == sorted(
        phase.ordinal for phase in PHASES
    )
