"""Run and visualize a two-version comparison."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Mapping, Sequence

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.visualization.artifacts import write_run_artifact
from macro_sim.visualization.render import render_run_artifact
from macro_sim.visualization.specs import DEFAULT_CATEGORIES, RunArtifact


DEFAULT_TICKS = 5000
DEFAULT_COMMON_OVERRIDES = {
    "seed": 0,
    "n_households": 5000,
    "n_firms_c": 500,
    "n_firms_k": 250,
    "n_banks": 8,
}
DEFAULT_DEMOGRAPHIC_TICKS = 365
DEFAULT_DEMOGRAPHIC_OVERRIDES = {
    "seed": 0,
    # Compatibility floor for Config validation only. With demographics enabled,
    # Economy derives live economic households from the 10k-person genesis state.
    "n_households": 1000,
    "n_firms_c": 500,
    "n_firms_k": 250,
    "n_banks": 8,
    "demographics_enabled": True,
    "demographics_population": 10000,
    "demographic_lifecycle_consumption": True,
}


@dataclass(frozen=True)
class ComparisonResult:
    output_dir: Path
    artifacts: list[RunArtifact]
    figures_by_label: dict[str, list[Path]]
    figure_paths: list[Path]
    profile_path: Path
    timings: dict[str, float]


@dataclass(frozen=True)
class SingleRunResult:
    output_dir: Path
    artifact: RunArtifact
    figure_paths: list[Path]
    profile_path: Path
    timings: dict[str, float]


def _config_for_version(version: str, *, ticks: int, overrides: Mapping[str, object] | None = None) -> Config:
    factory = getattr(Config, version, None)
    if factory is None or not callable(factory):
        raise ValueError(f"unknown Config version {version!r}")
    params = dict(overrides or {})
    params["n_ticks"] = ticks
    return factory(**params)


def _run_version(version: str, *, label: str, ticks: int, overrides: Mapping[str, object], output_dir: Path) -> RunArtifact:
    cfg = _config_for_version(version, ticks=ticks, overrides=overrides)
    econ = Economy(cfg)
    records = econ.run()
    return write_run_artifact(
        output_dir=output_dir,
        label=label,
        version=version,
        cfg=cfg,
        records=records,
    )


def run_single_version_visualization(
    *,
    version: str = "v123",
    label: str | None = None,
    output_dir: str | Path,
    ticks: int = DEFAULT_DEMOGRAPHIC_TICKS,
    overrides: Mapping[str, object] | None = None,
    category_ids: Sequence[str] | None = None,
    rolling: int = 7,
) -> SingleRunResult:
    """Run one config and persist a per-version CSV, metadata file, figures, and profile."""
    total_start = perf_counter()
    output_dir = Path(output_dir)
    label = label or version
    params = {**DEFAULT_DEMOGRAPHIC_OVERRIDES, **dict(overrides or {})}
    timings: dict[str, float] = {}
    start = perf_counter()
    artifact = _run_version(version, label=label, ticks=ticks, overrides=params, output_dir=output_dir)
    timings[f"{label}_run_and_write_seconds"] = perf_counter() - start
    start = perf_counter()
    figure_paths = render_run_artifact(
        artifact,
        output_dir=artifact.series_path.parent / "figures",
        category_ids=category_ids,
        rolling=rolling,
    )
    timings[f"{label}_render_seconds"] = perf_counter() - start
    timings["total_seconds"] = perf_counter() - total_start
    profile = {
        "preset": "demographic_one_year",
        "version": version,
        "versions": [label],
        "ticks": ticks,
        "category_ids": list(category_ids or DEFAULT_CATEGORIES.keys()),
        "overrides": params,
        "timings": timings,
    }
    profile_path = output_dir / "profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True))
    return SingleRunResult(
        output_dir=output_dir,
        artifact=artifact,
        figure_paths=figure_paths,
        profile_path=profile_path,
        timings=timings,
    )


def run_two_version_comparison(
    *,
    left_version: str = "v123",
    right_version: str = "v124",
    output_dir: str | Path,
    ticks: int = DEFAULT_TICKS,
    common_overrides: Mapping[str, object] | None = None,
    left_overrides: Mapping[str, object] | None = None,
    right_overrides: Mapping[str, object] | None = None,
    category_ids: Sequence[str] | None = None,
    rolling: int = 25,
) -> ComparisonResult:
    """Run two configs and persist one self-contained artifact directory per version."""
    total_start = perf_counter()
    output_dir = Path(output_dir)
    common = dict(common_overrides or {})
    left_params = {**common, **dict(left_overrides or {})}
    right_params = {**common, **dict(right_overrides or {})}
    timings: dict[str, float] = {}
    artifacts: list[RunArtifact] = []
    for version, params in ((left_version, left_params), (right_version, right_params)):
        start = perf_counter()
        artifact = _run_version(version, label=version, ticks=ticks, overrides=params, output_dir=output_dir)
        timings[f"{artifact.label}_run_and_write_seconds"] = perf_counter() - start
        artifacts.append(artifact)
    figures_by_label: dict[str, list[Path]] = {}
    for artifact in artifacts:
        start = perf_counter()
        figures_by_label[artifact.label] = render_run_artifact(
            artifact,
            output_dir=artifact.series_path.parent / "figures",
            category_ids=category_ids,
            rolling=rolling,
        )
        timings[f"{artifact.label}_render_seconds"] = perf_counter() - start
    figure_paths = [path for paths in figures_by_label.values() for path in paths]
    timings["total_seconds"] = perf_counter() - total_start
    profile = {
        "left_version": left_version,
        "right_version": right_version,
        "versions": [artifact.label for artifact in artifacts],
        "ticks": ticks,
        "category_ids": list(category_ids or DEFAULT_CATEGORIES.keys()),
        "common_overrides": common,
        "left_overrides": dict(left_overrides or {}),
        "right_overrides": dict(right_overrides or {}),
        "timings": timings,
    }
    profile_path = output_dir / "profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True))
    return ComparisonResult(
        output_dir=output_dir,
        artifacts=artifacts,
        figures_by_label=figures_by_label,
        figure_paths=figure_paths,
        profile_path=profile_path,
        timings=timings,
    )


def _default_output_dir(left: str, right: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / "visualizations" / f"{stamp}_{left}_vs_{right}"


def _default_single_output_dir(version: str, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / "visualizations" / f"{stamp}_{label or version}"


def main_single(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and visualize one demographic macro-simulator version.")
    parser.add_argument("--version", default="v123", help="Config factory name, e.g. v123")
    parser.add_argument("--label", default="v13_demo", help="Run artifact label")
    parser.add_argument("--ticks", type=int, default=DEFAULT_DEMOGRAPHIC_TICKS, help="Ticks to run")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for CSV, metadata, and figures")
    parser.add_argument("--category", action="append", dest="categories",
                        help=f"Category id to render. Repeatable. Known: {', '.join(DEFAULT_CATEGORIES)}")
    parser.add_argument("--rolling", type=int, default=7, help="Rolling window for plotted lines; 1 disables smoothing")
    parser.add_argument("--seed", type=int, default=DEFAULT_DEMOGRAPHIC_OVERRIDES["seed"], help="Seed")
    parser.add_argument("--population", type=int, default=DEFAULT_DEMOGRAPHIC_OVERRIDES["demographics_population"],
                        help="Genesis person population when demographics are enabled")
    parser.add_argument("--n-firms-c", type=int, default=DEFAULT_DEMOGRAPHIC_OVERRIDES["n_firms_c"])
    parser.add_argument("--n-firms-k", type=int, default=DEFAULT_DEMOGRAPHIC_OVERRIDES["n_firms_k"])
    parser.add_argument("--n-banks", type=int, default=DEFAULT_DEMOGRAPHIC_OVERRIDES["n_banks"])
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_single_output_dir(args.version, args.label)
    result = run_single_version_visualization(
        version=args.version,
        label=args.label,
        output_dir=output_dir,
        ticks=args.ticks,
        overrides={
            "seed": args.seed,
            "n_firms_c": args.n_firms_c,
            "n_firms_k": args.n_firms_k,
            "n_banks": args.n_banks,
            "demographics_population": args.population,
        },
        category_ids=args.categories,
        rolling=args.rolling,
    )
    print(f"single-run output: {result.output_dir}")
    print(f"profile: {result.profile_path}")
    print(f"total_seconds: {result.timings['total_seconds']:.3f}")
    print(f"  {result.artifact.label} run_and_write_seconds: "
          f"{result.timings[f'{result.artifact.label}_run_and_write_seconds']:.3f}")
    print(f"  {result.artifact.label} render_seconds: "
          f"{result.timings[f'{result.artifact.label}_render_seconds']:.3f}")
    print(f"  {result.artifact.label}: {result.artifact.series_path} ; {result.artifact.metadata_path}")
    for path in result.figure_paths:
        print(f"    figure: {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and visualize a two-version macro-simulator comparison.")
    parser.add_argument("--left", default="v123", help="Left Config factory name, e.g. v123")
    parser.add_argument("--right", default="v124", help="Right Config factory name, e.g. v124")
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS, help="Ticks to run for each version")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for CSVs, metadata, and figures")
    parser.add_argument("--category", action="append", dest="categories",
                        help=f"Category id to render. Repeatable. Known: {', '.join(DEFAULT_CATEGORIES)}")
    parser.add_argument("--rolling", type=int, default=25, help="Rolling window for plotted lines; 1 disables smoothing")
    parser.add_argument("--seed", type=int, default=DEFAULT_COMMON_OVERRIDES["seed"], help="Common seed")
    parser.add_argument("--n-households", type=int, default=DEFAULT_COMMON_OVERRIDES["n_households"])
    parser.add_argument("--n-firms-c", type=int, default=DEFAULT_COMMON_OVERRIDES["n_firms_c"])
    parser.add_argument("--n-firms-k", type=int, default=DEFAULT_COMMON_OVERRIDES["n_firms_k"])
    parser.add_argument("--n-banks", type=int, default=DEFAULT_COMMON_OVERRIDES["n_banks"])
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir(args.left, args.right)
    result = run_two_version_comparison(
        left_version=args.left,
        right_version=args.right,
        output_dir=output_dir,
        ticks=args.ticks,
        common_overrides={
            "seed": args.seed,
            "n_households": args.n_households,
            "n_firms_c": args.n_firms_c,
            "n_firms_k": args.n_firms_k,
            "n_banks": args.n_banks,
        },
        category_ids=args.categories,
        rolling=args.rolling,
    )
    print(f"comparison output: {result.output_dir}")
    print(f"profile: {result.profile_path}")
    print(f"total_seconds: {result.timings['total_seconds']:.3f}")
    for artifact in result.artifacts:
        print(f"  {artifact.label} run_and_write_seconds: "
              f"{result.timings[f'{artifact.label}_run_and_write_seconds']:.3f}")
        print(f"  {artifact.label} render_seconds: {result.timings[f'{artifact.label}_render_seconds']:.3f}")
        print(f"  {artifact.label}: {artifact.series_path} ; {artifact.metadata_path}")
        for path in result.figures_by_label[artifact.label]:
            print(f"    figure: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
