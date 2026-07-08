import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.config import Config
from macro_sim.visualization.artifacts import load_series_csv, write_run_artifact
from macro_sim.visualization.compare_versions import DEFAULT_COMMON_OVERRIDES, DEFAULT_TICKS, run_two_version_comparison
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
        category_ids=["overview", "real_macro"],
        rolling=2,
    )

    assert [p.name for p in paths] == ["overview.png", "real_macro.png"]
    assert all(p.parent == tmp_path / "v123" / "figures" for p in paths)
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
    assert "overview" in DEFAULT_CATEGORIES
    assert "real_macro" in DEFAULT_CATEGORIES


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
