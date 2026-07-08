"""CSV and metadata artifacts for visualization runs."""

from __future__ import annotations

import csv
import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from macro_sim.config import Config
from macro_sim.reporting.metrics import field_order
from macro_sim.visualization.specs import RunArtifact


def _parse_value(value: str):
    if value == "":
        return float("nan")
    try:
        return float(value)
    except ValueError:
        return value


def load_series_csv(path: str | Path) -> list[dict]:
    """Load a metrics CSV, parsing numeric cells back to floats."""
    path = Path(path)
    with path.open(newline="") as fh:
        return [{k: _parse_value(v) for k, v in row.items()} for row in csv.DictReader(fh)]


def write_series_csv(records: Iterable[dict], path: str | Path) -> Path:
    records = list(records)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = field_order(records)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in records:
            writer.writerow(row)
    return path


def write_run_artifact(
    *,
    output_dir: str | Path,
    label: str,
    version: str,
    cfg: Config,
    records: list[dict],
) -> RunArtifact:
    """Persist one run as `series.csv` plus metadata, returning a loaded artifact."""
    run_dir = Path(output_dir) / label
    run_dir.mkdir(parents=True, exist_ok=True)
    series_path = write_series_csv(records, run_dir / "series.csv")
    metadata = {
        "label": label,
        "version": version,
        "created": datetime.now().isoformat(timespec="seconds"),
        "n_records": len(records),
        "config": dataclasses.asdict(cfg),
    }
    metadata_path = run_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))
    return RunArtifact(
        label=label,
        version=version,
        records=records,
        series_path=series_path,
        metadata_path=metadata_path,
    )

