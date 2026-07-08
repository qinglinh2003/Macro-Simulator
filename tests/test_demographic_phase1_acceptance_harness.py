from __future__ import annotations

import json
import tomllib
from pathlib import Path

from macro_sim.demographics.phase1_acceptance import (
    Phase1AcceptanceConfig,
    run_acceptance_matrix,
    run_phase1_acceptance,
)


def test_phase1_acceptance_tiny_config_reports_core_gates():
    result = run_phase1_acceptance(
        Phase1AcceptanceConfig(
            population=40,
            ticks=3,
            n_firms_c=5,
            n_firms_k=2,
            n_banks=2,
            seed=17,
        )
    )

    assert result.passed is True
    assert result.gates["population_path_invariant"].passed is True
    assert result.gates["stock_flow_identity"].passed is True
    assert result.gates["claim_identity"].passed is True
    assert result.gates["demographic_metrics"].passed is True
    assert result.gates["per_capita_metrics"].passed is True
    assert result.gates["labor_supply_bridge"].passed is True
    assert result.metrics["ticks"] == 3
    assert result.metrics["initial_population"] == 40
    assert result.metrics["final_population"] >= 0


def test_phase1_acceptance_matrix_can_write_json_summary(tmp_path):
    output_path = tmp_path / "phase1-summary.json"

    summary = run_acceptance_matrix(
        presets=[
            Phase1AcceptanceConfig(
                name="mini-a",
                population=30,
                ticks=2,
                n_firms_c=4,
                n_firms_k=2,
                n_banks=2,
                seed=3,
            ),
            Phase1AcceptanceConfig(
                name="mini-b",
                population=30,
                ticks=2,
                n_firms_c=4,
                n_firms_k=2,
                n_banks=2,
                seed=4,
            ),
        ],
        workers=2,
        output_path=output_path,
    )

    assert summary["passed"] is True
    assert summary["workers"] == 2
    assert len(summary["runs"]) == 2
    persisted = json.loads(output_path.read_text())
    assert persisted["passed"] is True
    assert {run["name"] for run in persisted["runs"]} == {"mini-a", "mini-b"}


def test_pyproject_exposes_phase1_acceptance_entrypoint():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert (
        pyproject["project"]["scripts"]["macro-demographics-phase1-acceptance"]
        == "macro_sim.demographics.phase1_acceptance:main"
    )
