import json
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.config import Config
from macro_sim.visualization.artifacts import load_series_csv, write_run_artifact
from macro_sim.visualization.compare_versions import (
    DEFAULT_COMMON_OVERRIDES,
    DEFAULT_DEMOGRAPHIC_OVERRIDES,
    DEFAULT_DEMOGRAPHIC_TICKS,
    DEFAULT_TICKS,
    run_single_version_visualization,
    run_two_version_comparison,
)
from macro_sim.visualization.render import render_run_artifact
from macro_sim.visualization.specs import DEFAULT_CATEGORIES, RunArtifact


def _records(scale: float = 1.0) -> list[dict]:
    rows = []
    for t in range(6):
        rows.append({
            "t": t,
            "real_output": scale * (10.0 + t),
            "real_consumption": scale * (8.0 + t),
            "real_output_growth": 0.01 * t,
            "real_consumption_growth": 0.008 * t,
            "unemployment_rate": 0.1 - 0.01 * t,
            "inflation": 0.01 + 0.001 * t,
            "price_index": 1.0 + 0.01 * t,
            "cash_deficit_to_gdp": 0.02,
            "augmented_gov_spending_share_of_gdp": 0.18,
            "banks_alive": 2.0,
            "bank_economic_capital_min": scale * 100.0,
            "bond_market_total": scale * 50.0,
            "production_target_total": scale * (12.0 + t),
            "production_realization_rate": 0.8,
            "desired_consumption": scale * 9.0,
            "effective_consumption": scale * 8.0,
            "unsatisfied_demand_ratio": 0.05,
            "investment_units": scale * 2.0,
            "investment_target_units": scale * 3.0,
            "investment_realization_rate": 2.0 / 3.0,
            "aggregate_capital": scale * 100.0,
            "net_private_capital_formation": scale * 1.0,
            "capital_productivity": 0.1,
            "labor_productivity": 1.2,
            "active_producer_share": 0.9,
            "inventory": scale * 7.0,
            "inventory_investment": scale * 0.5,
            "inventory_to_sales": 0.2,
            "population_alive": 100.0,
            "person_population_alive": 100.0,
            "births_tick": 1.0,
            "deaths_tick": 0.0,
            "marriages_tick": 2.0,
            "divorces_tick": 0.0,
            "leaving_home_tick": 1.0,
            "child_share": 0.2,
            "adult_share": 0.65,
            "elder_share": 0.15,
            "working_age_share": 0.65,
            "dependency_ratio": 0.54,
            "child_dependency_ratio": 0.31,
            "elder_dependency_ratio": 0.23,
            "avg_household_size": 2.4,
            "married_share": 0.55,
            "real_output_per_capita": scale * 0.10,
            "real_consumption_per_capita": scale * 0.08,
            "nominal_output_per_capita": scale * 0.11,
            "household_income_per_capita": scale * 0.07,
            "household_saving_per_capita": scale * 0.01,
            "money_per_capita": scale * 10.0,
            "household_net_worth_per_capita": scale * 6.0,
            "gross_household_assets_per_capita": scale * 7.0,
            "household_debt_per_capita": scale * 1.0,
            "real_output_per_adult": scale * 0.16,
            "real_consumption_per_adult": scale * 0.12,
            "employment_per_adult": 0.8,
            "labor_supply_per_adult": 0.85,
        })
    return rows


def test_run_artifact_writes_metadata_and_round_trips_series(tmp_path):
    cfg = Config.v123(n_ticks=6, n_households=20, n_firms_c=3, n_firms_k=2, n_banks=2)
    artifact = write_run_artifact(
        output_dir=tmp_path,
        label="v123",
        version="v123",
        cfg=cfg,
        records=_records(),
    )

    assert artifact.series_path.exists()
    assert artifact.metadata_path.exists()
    metadata = json.loads(artifact.metadata_path.read_text())
    assert metadata["label"] == "v123"
    assert metadata["version"] == "v123"
    assert metadata["config"]["n_ticks"] == 6

    loaded = load_series_csv(artifact.series_path)
    assert loaded[0]["t"] == 0.0
    assert loaded[-1]["real_output"] == 15.0


def test_visualization_cli_defaults_use_full_baseline_scale():
    assert DEFAULT_TICKS == 5000
    assert DEFAULT_COMMON_OVERRIDES == {
        "seed": 0,
        "n_households": 5000,
        "n_firms_c": 500,
        "n_firms_k": 250,
        "n_banks": 8,
    }


def test_pyproject_exposes_single_visualization_entrypoint():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["scripts"]["macro-viz-run"] == "macro_sim.visualization.compare_versions:main_single"


def test_demographic_visualization_preset_defaults_to_10000_people_and_one_year():
    assert DEFAULT_DEMOGRAPHIC_TICKS == 365
    assert DEFAULT_DEMOGRAPHIC_OVERRIDES["demographics_enabled"] is True
    assert DEFAULT_DEMOGRAPHIC_OVERRIDES["demographics_population"] == 10000
    assert DEFAULT_DEMOGRAPHIC_OVERRIDES["demographic_lifecycle_consumption"] is True
    assert DEFAULT_DEMOGRAPHIC_OVERRIDES["n_households"] != DEFAULT_DEMOGRAPHIC_OVERRIDES["demographics_population"]


def test_render_run_artifact_writes_category_pngs_under_run_directory(tmp_path):
    artifact = RunArtifact(
        label="v123",
        version="v123",
        records=_records(1.0),
        series_path=tmp_path / "v123" / "series.csv",
        metadata_path=tmp_path / "v123" / "metadata.json",
    )

    paths = render_run_artifact(
        artifact,
        output_dir=tmp_path / "v123" / "figures",
        category_ids=["overview", "real_macro", "demographics", "per_capita_macro"],
        rolling=2,
    )

    assert [p.name for p in paths] == [
        "overview.png",
        "real_macro.png",
        "demographics.png",
        "per_capita_macro.png",
    ]
    assert all(p.parent == tmp_path / "v123" / "figures" for p in paths)
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
    assert "overview" in DEFAULT_CATEGORIES
    assert "real_macro" in DEFAULT_CATEGORIES
    assert "demographics" in DEFAULT_CATEGORIES
    assert "per_capita_macro" in DEFAULT_CATEGORIES


def test_run_single_version_visualization_generates_demographic_artifact(tmp_path):
    result = run_single_version_visualization(
        version="v123",
        label="v13_demo",
        output_dir=tmp_path,
        ticks=2,
        overrides={
            "seed": 12,
            "n_households": 40,
            "n_firms_c": 5,
            "n_firms_k": 2,
            "n_banks": 2,
            "demographics_population": 40,
        },
        category_ids=["demographics", "per_capita_macro"],
        rolling=1,
    )

    assert result.artifact.label == "v13_demo"
    assert result.artifact.series_path == tmp_path / "v13_demo" / "series.csv"
    assert result.artifact.metadata_path == tmp_path / "v13_demo" / "metadata.json"
    assert result.profile_path == tmp_path / "profile.json"
    assert [p.name for p in result.figure_paths] == ["demographics.png", "per_capita_macro.png"]
    assert all(p.exists() and p.stat().st_size > 0 for p in result.figure_paths)
    metadata = json.loads(result.artifact.metadata_path.read_text())
    assert metadata["config"]["demographics_enabled"] is True
    assert metadata["config"]["demographics_population"] == 40
    profile = json.loads(result.profile_path.read_text())
    assert profile["versions"] == ["v13_demo"]
    assert profile["ticks"] == 2
    assert profile["preset"] == "demographic_one_year"



def test_run_two_version_comparison_smoke_generates_csv_metadata_and_figures(tmp_path):
    result = run_two_version_comparison(
        left_version="v123",
        right_version="v124",
        output_dir=tmp_path,
        ticks=2,
        common_overrides={
            "n_households": 30,
            "n_firms_c": 4,
            "n_firms_k": 2,
            "n_banks": 2,
            "seed": 5,
        },
        category_ids=["overview"],
        rolling=1,
    )

    assert [a.label for a in result.artifacts] == ["v123", "v124"]
    assert result.artifacts[0].series_path == tmp_path / "v123" / "series.csv"
    assert result.artifacts[1].series_path == tmp_path / "v124" / "series.csv"
    assert all(a.series_path.exists() for a in result.artifacts)
    assert all(a.metadata_path.exists() for a in result.artifacts)
    assert sorted(result.figures_by_label) == ["v123", "v124"]
    assert result.figures_by_label["v123"] == [tmp_path / "v123" / "figures" / "overview.png"]
    assert result.figures_by_label["v124"] == [tmp_path / "v124" / "figures" / "overview.png"]
    assert [p.name for p in result.figure_paths] == ["overview.png", "overview.png"]
    assert all(p.stat().st_size > 0 for p in result.figure_paths)
    assert result.profile_path == tmp_path / "profile.json"
    assert result.profile_path.exists()
    profile = json.loads(result.profile_path.read_text())
    assert profile["versions"] == ["v123", "v124"]
    assert profile["ticks"] == 2
    assert profile["timings"]["total_seconds"] >= 0.0
    assert profile["timings"]["v123_run_and_write_seconds"] >= 0.0
    assert profile["timings"]["v124_render_seconds"] >= 0.0
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "figures").exists()
