"""Static category renderers for per-version visualization artifacts."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from macro_sim.visualization.specs import CategorySpec, DEFAULT_CATEGORIES, PanelSpec, RunArtifact


_RUN_COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")
_METRIC_STYLES = ("-", "--", ":", "-.")
_GRID = dict(alpha=0.23, lw=0.6)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text).strip("_")


def _series(records: list[dict], key: str) -> np.ndarray:
    return np.asarray([float(row.get(key, float("nan"))) for row in records], dtype=float)


def _ticks(records: list[dict]) -> np.ndarray:
    if records and "t" in records[0]:
        return _series(records, "t")
    return np.arange(len(records), dtype=float)


def _rolling(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or values.size == 0:
        return values
    out = np.empty_like(values, dtype=float)
    for idx in range(values.size):
        start = max(0, idx - window + 1)
        chunk = values[start:idx + 1]
        out[idx] = np.nanmean(chunk) if np.isfinite(chunk).any() else np.nan
    return out


def _has_data(values: np.ndarray) -> bool:
    return bool(np.isfinite(values).any())


def _plot_panel(ax, panel: PanelSpec, artifacts: Sequence[RunArtifact], rolling: int) -> None:
    missing: list[str] = []
    plotted = False
    single_run = len(artifacts) == 1
    for metric_idx, metric in enumerate(panel.metrics):
        style = _METRIC_STYLES[metric_idx % len(_METRIC_STYLES)]
        for run_idx, artifact in enumerate(artifacts):
            values = _series(artifact.records, metric)
            if not _has_data(values):
                if run_idx == 0:
                    missing.append(metric)
                continue
            t = _ticks(artifact.records)
            color_idx = metric_idx if single_run else run_idx
            color = _RUN_COLORS[color_idx % len(_RUN_COLORS)]
            label = (
                metric
                if single_run
                else artifact.label if len(panel.metrics) == 1 else f"{artifact.label} / {metric}"
            )
            if rolling > 1:
                ax.plot(t, values, color=color, ls=style, lw=0.65, alpha=0.22)
                ax.plot(t, _rolling(values, rolling), color=color, ls=style, lw=1.35, label=label)
            else:
                ax.plot(t, values, color=color, ls=style, lw=1.15, label=label)
            plotted = True
    if panel.zero:
        ax.axhline(0.0, color="black", lw=0.7, ls="--", alpha=0.45)
    if panel.one:
        ax.axhline(1.0, color="black", lw=0.7, ls="--", alpha=0.45)
    ax.set_title(panel.title, fontsize=9)
    ax.grid(**_GRID)
    ax.tick_params(labelsize=7)
    if plotted:
        ax.legend(fontsize=5.8, loc="best", framealpha=0.62)
    else:
        ax.text(0.5, 0.54, "No data", transform=ax.transAxes, ha="center", va="center", fontsize=9)
    if missing:
        ax.text(
            0.01,
            0.01,
            "missing: " + ", ".join(missing[:4]) + ("..." if len(missing) > 4 else ""),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=5.8,
            color="#666666",
        )
    ax.set_xlabel("tick", fontsize=7)


def _plot_category(
    artifacts: Sequence[RunArtifact],
    category: CategorySpec,
    path: str | Path,
    *,
    rolling: int,
) -> Path:
    if not artifacts:
        raise ValueError("at least one run artifact is required")
    n = len(category.panels)
    ncols = 2 if n > 1 else 1
    nrows = int(math.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, max(4.2, 3.2 * nrows)), squeeze=False)
    for ax, panel in zip(axes.ravel(), category.panels):
        _plot_panel(ax, panel, artifacts, rolling)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    run_label = " vs ".join(a.label for a in artifacts)
    fig.suptitle(f"{category.title}: {run_label}", fontsize=14, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.982))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=135)
    plt.close(fig)
    return path


def plot_category_run(
    artifact: RunArtifact,
    category: CategorySpec,
    path: str | Path,
    *,
    rolling: int = 1,
) -> Path:
    """Render one category for a single version artifact."""
    return _plot_category([artifact], category, path, rolling=rolling)


def render_run_artifact(
    artifact: RunArtifact,
    *,
    output_dir: str | Path,
    category_ids: Sequence[str] | None = None,
    rolling: int = 1,
) -> list[Path]:
    """Render the default category PNG group for one version artifact."""
    output_dir = Path(output_dir)
    category_ids = tuple(category_ids or DEFAULT_CATEGORIES.keys())
    paths: list[Path] = []
    for category_id in category_ids:
        category = DEFAULT_CATEGORIES[category_id]
        path = output_dir / f"{_slug(category.id)}.png"
        paths.append(plot_category_run(artifact, category, path, rolling=rolling))
    return paths
