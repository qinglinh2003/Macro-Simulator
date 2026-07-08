import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.validation import (
    main,
    partner_integrity,
    run_phase0_validation,
    total_variation,
)


def test_total_variation_normalizes_vectors_before_comparing_shapes():
    assert total_variation(np.array([10.0, 0.0]), np.array([5.0, 5.0])) == 0.5
    assert total_variation(np.array([0.0, 0.0]), np.array([0.0, 0.0])) == 0.0


def test_partner_integrity_reports_broken_and_dead_partner_links():
    rates = Phase0VitalRates(tfr=0.0)
    state = create_genesis_population(rates, n=600, seed=17)
    people = {person.id: person for person in state.people}
    couple = next(
        (person, people[person.partner_id])
        for person in state.people
        if person.partner_id is not None and person.id < person.partner_id
    )
    a, b = couple
    b.partner_id = None

    report = partner_integrity(state)

    assert report["bad_partner_links"] == 1
    assert report["asymmetric_partner_links"] == 1

    b.partner_id = a.id
    b.alive = False
    report = partner_integrity(state)

    assert report["bad_partner_links"] == 1
    assert report["dead_partner_refs"] == 1


def test_run_phase0_validation_writes_layered_artifacts(tmp_path):
    summary = run_phase0_validation(output_dir=tmp_path, n=800, years=2, seeds=[11, 12])

    assert summary["passed"] is True
    assert set(summary["configs"]) == {
        "config_a_mortality_only",
        "config_b_ungated_fertility",
        "config_c_multistate_oracle",
        "config_c_two_sided_matching",
    }
    assert summary["configs"]["config_a_mortality_only"]["headcount_identity_failures"] == 0
    assert summary["configs"]["config_a_mortality_only"]["max_daily_survival_error"] < 1e-10
    assert summary["configs"]["config_a_mortality_only"]["cohort_survival_max_abs_error"] < 0.08
    assert "ensemble_cells_over_2se" in summary["configs"]["config_a_mortality_only"]
    assert summary["configs"]["config_a_mortality_only"]["event_count_bh_rejections"] == 0
    assert summary["configs"]["config_a_mortality_only"]["aggregated_event_bh_rejections"] == 0
    assert summary["configs"]["config_b_ungated_fertility"]["max_tv_distance"] < 0.35
    assert summary["configs"]["config_b_ungated_fertility"]["annual_leslie_max_tv_distance"] >= summary["configs"]["config_b_ungated_fertility"]["max_tv_distance"]
    assert summary["configs"]["config_b_ungated_fertility"]["genesis_tv_mean"] <= summary["configs"]["config_b_ungated_fertility"]["genesis_tv_null_upper_3sd"]
    assert summary["configs"]["config_b_ungated_fertility"]["r_empirical_z_abs"] < 2.5
    assert summary["configs"]["config_b_ungated_fertility"]["ensemble_active_cells"] >= summary["configs"]["config_b_ungated_fertility"]["ensemble_cells_over_2se"]
    assert summary["configs"]["config_b_ungated_fertility"]["event_count_bh_rejections"] == 0
    assert summary["configs"]["config_b_ungated_fertility"]["aggregated_event_bh_rejections"] == 0
    assert summary["configs"]["config_b_ungated_fertility"]["relaxation_decay_relative_error"] < 0.35
    assert summary["configs"]["config_b_ungated_fertility"]["birth_hook_count"] == summary["configs"]["config_b_ungated_fertility"]["birth_events"]
    assert summary["configs"]["config_b_ungated_fertility"]["death_hook_count"] == summary["configs"]["config_b_ungated_fertility"]["death_events"]
    assert summary["configs"]["config_b_ungated_fertility"]["noop_economic_state_identical"] == 1
    assert summary["configs"]["config_b_ungated_fertility"]["dead_retained_count"] == summary["configs"]["config_b_ungated_fertility"]["death_events"]
    assert summary["configs"]["config_b_ungated_fertility"]["newborns_with_parent_id"] == summary["configs"]["config_b_ungated_fertility"]["birth_events"]
    assert summary["configs"]["config_c_two_sided_matching"]["bad_partner_links"] == 0
    assert summary["configs"]["config_c_two_sided_matching"]["minor_household_missing"] == 0
    assert summary["configs"]["config_c_multistate_oracle"]["married_profile_max_abs_error"] < 0.12
    assert summary["configs"]["config_c_two_sided_matching"]["married_share_oracle_gap_abs"] < 0.20

    summary_path = tmp_path / "summary.json"
    constants_path = tmp_path / "spectral_constants.csv"
    mortality_ensemble_path = tmp_path / "config_a_ensemble_deviation.csv"
    mortality_event_path = tmp_path / "config_a_event_count_tests.csv"
    alignment_path = tmp_path / "config_b_oracle_alignment.csv"
    ensemble_path = tmp_path / "config_b_ensemble_deviation.csv"
    event_path = tmp_path / "config_b_event_count_tests.csv"
    partner_path = tmp_path / "partner_integrity.csv"
    assert summary_path.exists()
    assert constants_path.exists()
    assert mortality_ensemble_path.exists()
    assert mortality_event_path.exists()
    assert alignment_path.exists()
    assert ensemble_path.exists()
    assert event_path.exists()
    assert partner_path.exists()

    written = json.loads(summary_path.read_text())
    assert written["passed"] is True
    with constants_path.open() as f:
        constants = list(csv.DictReader(f))
    assert {"one_dimensional", "multistate"} <= {row["oracle"] for row in constants}
    for row in constants:
        assert "nrr" in row
        assert "generation_length" in row
        assert row["sign_consistency"] == "1"


def test_phase0_validation_cli_runs_tiny_harness(tmp_path):
    code = main([
        "--output-dir",
        str(tmp_path),
        "--n",
        "500",
        "--years",
        "1",
        "--seeds",
        "1",
    ])

    assert code == 0
    assert (tmp_path / "summary.json").exists()


def test_phase0_validation_accepts_parallel_workers(tmp_path):
    summary = run_phase0_validation(output_dir=tmp_path, n=400, years=1, seeds=[21, 22], workers=2)

    assert summary["passed"] is True
    assert summary["workers"] == 2
    assert len(summary["seeds"]) == 2

    cli_dir = tmp_path / "cli"
    code = main([
        "--output-dir",
        str(cli_dir),
        "--n",
        "400",
        "--years",
        "1",
        "--seeds",
        "2",
        "--workers",
        "2",
    ])

    assert code == 0
    assert (cli_dir / "summary.json").exists()
