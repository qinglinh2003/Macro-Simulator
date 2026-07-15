"""CLI for comparing simulator runs with provenance-complete observed data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from macro_sim.diagnostics.empirical import (
    CalendarCadenceError,
    SimulationTimeline,
    aggregate_daily_series,
    align_observed_simulated,
    classify_empirical_symptoms,
    diagnose_empirical_fit,
    prepare_simulation_timeline,
    select_observed_series,
    simulation_daily_values,
    transform_simulated_aggregates,
    validate_aligned_cadence,
)
from macro_sim.diagnostics.observed import ObservedDataset, ObservedRecord, load_observed_csv
from macro_sim.diagnostics.registry import ComparisonMode, DEFAULT_REGISTRY, Frequency


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _read_simulation_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("simulation CSV is missing a header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("simulation CSV contains duplicate header fields")
        if any(not field.strip() for field in reader.fieldnames):
            raise ValueError("simulation CSV contains a blank header field")
        rows = list(reader)
    if not rows:
        raise ValueError("simulation CSV contains no records")
    return rows


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_provenance() -> dict[str, Any]:
    """Fingerprint the executable source, including untracked diagnostic files."""

    scoped_paths = ("macro_sim", "tests", "pyproject.toml", "uv.lock")
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=_REPO_ROOT,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short", "--", *scoped_paths],
            text=True,
            cwd=_REPO_ROOT,
        ).splitlines()
        diff = subprocess.check_output(
            ["git", "diff", "--binary", "HEAD", "--", *scoped_paths],
            cwd=_REPO_ROOT,
        )
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "--", *scoped_paths],
            text=True,
            cwd=_REPO_ROOT,
        ).splitlines()
        digest = hashlib.sha256()
        digest.update(diff)
        for name in sorted(untracked):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update((_REPO_ROOT / name).read_bytes())
        return {
            "revision": revision,
            "dirty": bool(status),
            "source_diff_sha256": digest.hexdigest(),
            "dirty_paths": status,
        }
    except (OSError, subprocess.CalledProcessError):
        return {
            "revision": "unknown",
            "dirty": None,
            "source_diff_sha256": None,
            "dirty_paths": [],
        }


def _metric_registry_sha256() -> str:
    canonical = json.dumps(
        _json_safe(DEFAULT_REGISTRY.to_dict()),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _software_provenance() -> dict[str, Any]:
    return {
        "git": _git_provenance(),
        "runtime": {
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
        },
        "metric_registry_sha256": _metric_registry_sha256(),
    }


def _software_fingerprint(provenance: dict[str, Any]) -> tuple[Any, ...]:
    git = provenance["git"]
    return (
        git.get("revision"),
        git.get("source_diff_sha256"),
        provenance.get("metric_registry_sha256"),
    )


def _provenance_key(row: ObservedRecord) -> tuple[str, str, str, str, str, str, str]:
    return (
        row.metric_id,
        row.geography.casefold(),
        row.source.casefold(),
        row.series_id.casefold(),
        row.frequency.value,
        row.unit,
        row.seasonal_adjustment,
    )


def _series_key(row: ObservedRecord) -> str:
    return (
        f"{row.metric_id}@{row.geography}:{row.source}/{row.series_id}"
        f"[{row.frequency.value},{row.unit},{row.seasonal_adjustment}]"
    )


def _matches_filters(
    row: ObservedRecord,
    *,
    geography: str,
    metric_ids: set[str],
    source: str | None,
    series_id: str | None,
    seasonal_adjustment: str | None,
) -> bool:
    return (
        row.geography.casefold() == geography.casefold()
        and (not metric_ids or row.metric_id in metric_ids)
        and (source is None or row.source.casefold() == source.casefold())
        and (series_id is None or row.series_id.casefold() == series_id.casefold())
        and (
            seasonal_adjustment is None
            or row.seasonal_adjustment == seasonal_adjustment
        )
    )


def _failure_reason(stage: str, exc: Exception, *, code: str) -> dict[str, str]:
    return {
        "code": code,
        "stage": stage,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def _series_shell(
    row: ObservedRecord,
    *,
    selected_vintage: str,
) -> dict[str, Any]:
    crosswalk = DEFAULT_REGISTRY.resolve_crosswalk(
        row.metric_id,
        source=row.source,
        series_id=row.series_id,
        frequency=row.frequency,
        unit=row.unit,
        geography=row.geography,
        seasonal_adjustment=row.seasonal_adjustment,
    )
    return {
        "series_key": _series_key(row),
        "status": "pending",
        "metric_id": row.metric_id,
        "observed_series": {
            "source": row.source,
            "series_id": row.series_id,
            "geography": row.geography,
            "frequency": row.frequency,
            "unit": row.unit,
            "seasonal_adjustment": row.seasonal_adjustment,
            "selected_vintage": selected_vintage,
            "crosswalk": asdict(crosswalk),
        },
        "diagnostic": None,
        "classification": None,
        "findings": [],
        "aligned": [],
        "failure_reason": None,
    }


def _process_series(
    dataset: ObservedDataset,
    representative: ObservedRecord,
    simulation_timeline: SimulationTimeline,
    *,
    vintage: str | date,
    vintage_label: str,
    comparison_mode: ComparisonMode | None,
    allow_partial_periods: bool,
    strict: bool,
) -> dict[str, Any]:
    result = _series_shell(representative, selected_vintage=vintage_label)
    stage = "observed_selection"
    try:
        observed = select_observed_series(
            dataset,
            representative.metric_id,
            geography=representative.geography,
            source=representative.source,
            series_id=representative.series_id,
            frequency=representative.frequency,
            unit=representative.unit,
            seasonal_adjustment=representative.seasonal_adjustment,
            vintage=vintage,
        )
        result["observed_series"]["n_selected_observations"] = len(observed)
        result["observed_series"]["selected_vintage_dates"] = sorted({
            row.vintage.isoformat() for row in observed
        })

        crosswalk = DEFAULT_REGISTRY.resolve_crosswalk(
            representative.metric_id,
            source=representative.source,
            series_id=representative.series_id,
            frequency=representative.frequency,
            unit=representative.unit,
            geography=representative.geography,
            seasonal_adjustment=representative.seasonal_adjustment,
        )
        simulation_metric_id = (
            crosswalk.simulation_source_metric_id or representative.metric_id
        )
        result["observed_series"]["crosswalk"][
            "effective_simulation_metric_id"
        ] = simulation_metric_id
        stage = "simulation_series"
        daily = simulation_daily_values(
            simulation_timeline,
            simulation_metric_id,
        )
        stage = "calendar_aggregation"
        aggregated = aggregate_daily_series(
            daily,
            DEFAULT_REGISTRY.get(simulation_metric_id),
            representative.frequency,
            require_complete=False,
            crosswalk=(
                crosswalk
                if simulation_metric_id == representative.metric_id
                else None
            ),
        )
        simulated = transform_simulated_aggregates(
            aggregated,
            target_metric_id=representative.metric_id,
            crosswalk=crosswalk,
        )
        stage = "alignment"
        aligned = align_observed_simulated(
            simulated,
            observed,
            require_complete_simulation_periods=not allow_partial_periods,
        )
        result["aligned"] = [asdict(point) for point in aligned]
        if len(aligned) < 2:
            exc = ValueError(
                f"at least two aligned periods are required; found {len(aligned)}"
            )
            if strict:
                raise exc
            result["status"] = "skipped"
            result["failure_reason"] = _failure_reason(
                "alignment", exc, code="insufficient_aligned_periods",
            )
            return result

        stage = "calendar_cadence"
        validate_aligned_cadence(aligned)
        stage = "distance_diagnostic"
        diagnostic = diagnose_empirical_fit(
            aligned,
            representative.metric_id,
            comparison_mode=comparison_mode,
        )
        stage = "symptom_classification"
        classification = classify_empirical_symptoms(
            aligned,
            diagnostic,
            registered_comparison_mode=crosswalk.comparison_mode,
        )
        result.update(
            status="success",
            diagnostic=asdict(diagnostic),
            classification=asdict(classification),
            findings=[asdict(item) for item in classification.findings],
        )
        return result
    except Exception as exc:
        if strict:
            raise
        result["status"] = (
            "skipped" if stage == "observed_selection" else "failed"
        )
        if isinstance(exc, CalendarCadenceError):
            failure_code = "non_contiguous_aligned_periods"
        elif stage == "observed_selection":
            failure_code = "observations_unavailable_at_vintage"
        else:
            failure_code = "series_processing_failed"
        result["failure_reason"] = _failure_reason(
            stage,
            exc,
            code=failure_code,
        )
        return result


def _missing_requested_series(
    metric_id: str,
    *,
    geography: str,
    source: str | None,
    series_id: str | None,
    seasonal_adjustment: str | None,
) -> dict[str, Any]:
    filters = {
        "geography": geography,
        "source": source,
        "series_id": series_id,
        "seasonal_adjustment": seasonal_adjustment,
    }
    return {
        "series_key": f"{metric_id}@{geography}:unresolved",
        "status": "skipped",
        "metric_id": metric_id,
        "observed_series": {"requested_filters": filters},
        "diagnostic": None,
        "classification": None,
        "findings": [],
        "aligned": [],
        "failure_reason": {
            "code": "no_matching_observed_series",
            "stage": "series_discovery",
            "error_type": "ValueError",
            "message": (
                f"no observed provenance group matches metric {metric_id!r} and "
                f"the requested filters"
            ),
        },
    }


def _legacy_payload(
    payload: dict[str, Any], series: dict[str, Any],
) -> dict[str, Any]:
    """Preserve the schema-v1 single-series artifact as a compatibility alias."""

    observed = dict(series["observed_series"])
    observed.update(
        path=payload["inputs"]["observed"]["path"],
        sha256=payload["inputs"]["observed"]["sha256_before"],
    )
    return {
        "schema_version": 1,
        "created": payload["created"],
        "metric_id": series["metric_id"],
        "simulation": {
            "path": payload["inputs"]["simulation"]["path"],
            "sha256": payload["inputs"]["simulation"]["sha256_before"],
            "start_date": payload["request"]["simulation_start_date"],
            "start_date_semantics": payload["request"][
                "simulation_start_date_semantics"
            ],
            "tick_field": payload["request"]["tick_field"],
            "timeline": payload["inputs"]["simulation"]["timeline"],
        },
        "observed_series": observed,
        "diagnostic": series["diagnostic"],
        "aligned": series["aligned"],
    }


def _markdown_scalar(value: Any) -> str:
    safe = _json_safe(value)
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, sort_keys=True, ensure_ascii=False)
    return str(safe)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# Empirical Economic Diagnostics",
        "",
        "This report screens descriptive model/data mismatches. It does not identify "
        "causes or authorize calibration from abstract model levels.",
        "",
        "## Run summary",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Geography: `{payload['request']['geography']}`",
        f"- Series discovered: {summary['series_total']}",
        f"- Successful: {summary['series_successful']}",
        f"- Failed: {summary['series_failed']}",
        f"- Skipped: {summary['series_skipped']}",
        f"- Symptom findings: {summary['finding_count']}",
        f"- Simulation SHA-256: `{payload['inputs']['simulation']['sha256_before']}`",
        f"- Observed SHA-256: `{payload['inputs']['observed']['sha256_before']}`",
        f"- Input integrity verified after processing: `{payload['input_integrity']['verified']}`",
        "",
    ]
    for series in payload["series"]:
        lines.extend([
            f"## `{series['series_key']}`",
            "",
            f"- Status: `{series['status']}`",
            f"- Metric: `{series['metric_id']}`",
        ])
        provenance = series["observed_series"]
        if "source" in provenance:
            lines.extend([
                f"- Observed series: `{provenance['source']}/{provenance['series_id']}`",
                f"- Frequency: `{_markdown_scalar(provenance['frequency'])}`",
                f"- Unit: `{provenance['unit']}`",
            ])
        if series["failure_reason"] is not None:
            reason = series["failure_reason"]
            lines.extend([
                f"- Reason code: `{reason['code']}`",
                f"- Stage: `{reason['stage']}`",
                f"- Reason: {reason['message']}",
                "",
            ])
        diagnostic = series["diagnostic"]
        if diagnostic is not None:
            classification = series["classification"]
            lines.extend([
                f"- Comparison: `{_markdown_scalar(diagnostic['comparison_mode'])}`",
                f"- Aligned periods: {diagnostic['n_aligned']}",
                f"- Measurement status: `{classification['measurement_status']}`",
                f"- Classification status: `{classification['status']}`",
                f"- Level calibration allowed: `{classification['level_calibration_allowed']}`",
                f"- NRMSE: {_markdown_scalar(diagnostic['normalized_rmse'])}",
                f"- Correlation: {_markdown_scalar(diagnostic['correlation'])}",
                "",
                "### Findings",
                "",
            ])
            if not series["findings"]:
                lines.append("- No symptom crossed the declared screening thresholds.")
            for finding in series["findings"]:
                lines.extend([
                    f"- **{finding['issue_id']}** (`{finding['severity']}`): {finding['claim']}",
                    f"  Evidence: `{_markdown_scalar(finding['evidence'])}`",
                    f"  Thresholds: `{_markdown_scalar(finding['thresholds'])}`",
                    f"  Next probes: `{', '.join(finding['probe_ids']) or 'none registered'}`",
                    f"  Root-cause candidates to test: "
                    f"`{', '.join(finding['root_cause_ids']) or 'none registered'}`",
                    f"  Ablations: `{', '.join(finding['ablation_ids']) or 'none registered'}`",
                ])
            lines.extend(["", "### Caveats", ""])
            lines.extend(f"- {item}" for item in classification["caveats"])
            lines.append("")
        if series["aligned"]:
            lines.extend([
                "### Aligned data",
                "",
                "| Period | Simulated | Observed | Vintage | Complete |",
                "|---|---:|---:|---|---|",
            ])
            for point in series["aligned"]:
                lines.append(
                    f"| {point['period']} | {_markdown_scalar(point['simulated'])} | "
                    f"{_markdown_scalar(point['observed'])} | "
                    f"{_markdown_scalar(point['observed_vintage'])} | "
                    f"{point['simulated_complete']} |"
                )
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _ensure_empty_output_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise FileExistsError(f"output path is not a directory: {path}")
        if any(path.iterdir()):
            raise FileExistsError(f"output directory is not empty: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare daily simulator series with versioned real-world observations. "
            "Repeat --metric-id for a batch, or omit it to process every provenance "
            "series for the selected geography."
        ),
    )
    parser.add_argument("--simulation-csv", type=Path, required=True)
    parser.add_argument("--observed-csv", type=Path, required=True)
    parser.add_argument("--metric-id", action="append")
    parser.add_argument(
        "--simulation-start-date",
        type=date.fromisoformat,
        required=True,
        help="calendar date assigned to the first retained post-burn tick",
    )
    parser.add_argument("--geography", required=True)
    parser.add_argument("--source")
    parser.add_argument("--series-id")
    parser.add_argument("--seasonal-adjustment")
    parser.add_argument("--vintage", default="latest")
    parser.add_argument("--tick-field", default="t")
    parser.add_argument("--tick-origin", type=int, default=0)
    parser.add_argument("--burn-in-ticks", type=int, default=0)
    parser.add_argument("--comparison-mode", choices=tuple(mode.value for mode in ComparisonMode))
    parser.add_argument("--allow-partial-periods", action="store_true")
    parser.add_argument(
        "--allow-missing-requested",
        action="store_true",
        help="allow explicitly requested metrics to be skipped without a nonzero exit",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    _ensure_empty_output_dir(args.output_dir)
    software_at_start = _software_provenance()
    simulation_sha_before = _file_sha256(args.simulation_csv)
    observed_sha_before = _file_sha256(args.observed_csv)

    vintage: str | date = args.vintage
    if vintage != "latest":
        vintage = date.fromisoformat(vintage)
    comparison_mode = (
        ComparisonMode(args.comparison_mode) if args.comparison_mode else None
    )
    dataset = load_observed_csv(args.observed_csv)
    simulation_rows = _read_simulation_csv(args.simulation_csv)
    simulation_timeline = prepare_simulation_timeline(
        simulation_rows,
        start_date=args.simulation_start_date,
        tick_field=args.tick_field,
        tick_origin=args.tick_origin,
        burn_in_ticks=args.burn_in_ticks,
    )
    requested_metric_list = list(args.metric_id or ())
    requested_metric_ids = set(requested_metric_list)
    single_compatibility_mode = len(requested_metric_list) == 1

    series_results: list[dict[str, Any]] = []
    if single_compatibility_mode:
        # This intentionally retains the old strict ambiguity behavior.  Batch mode
        # below is the explicit way to diagnose each provenance independently.
        observed = select_observed_series(
            dataset,
            requested_metric_list[0],
            geography=args.geography,
            source=args.source,
            series_id=args.series_id,
            seasonal_adjustment=args.seasonal_adjustment,
            vintage=vintage,
        )
        series_results.append(_process_series(
            dataset,
            observed[0],
            simulation_timeline,
            vintage=vintage,
            vintage_label=args.vintage,
            comparison_mode=comparison_mode,
            allow_partial_periods=args.allow_partial_periods,
            strict=True,
        ))
    else:
        candidates = [
            row for row in dataset.records
            if _matches_filters(
                row,
                geography=args.geography,
                metric_ids=requested_metric_ids,
                source=args.source,
                series_id=args.series_id,
                seasonal_adjustment=args.seasonal_adjustment,
            )
        ]
        if not candidates and not requested_metric_ids:
            raise ValueError(
                f"no observed provenance series match geography {args.geography!r} "
                "and the requested filters"
            )
        representatives: dict[
            tuple[str, str, str, str, str, str, str], ObservedRecord
        ] = {}
        for row in sorted(
            candidates,
            key=lambda item: (
                _provenance_key(item), item.period, item.vintage,
                item.geography, item.source, item.series_id,
            ),
        ):
            representatives.setdefault(_provenance_key(row), row)
        for key in sorted(representatives):
            series_results.append(_process_series(
                dataset,
                representatives[key],
                simulation_timeline,
                vintage=vintage,
                vintage_label=args.vintage,
                comparison_mode=comparison_mode,
                allow_partial_periods=args.allow_partial_periods,
                strict=False,
            ))
        discovered_metrics = {row.metric_id for row in candidates}
        for metric_id in sorted(requested_metric_ids - discovered_metrics):
            series_results.append(_missing_requested_series(
                metric_id,
                geography=args.geography,
                source=args.source,
                series_id=args.series_id,
                seasonal_adjustment=args.seasonal_adjustment,
            ))

    series_results.sort(key=lambda item: item["series_key"].casefold())
    findings = sorted(
        (
            {"series_key": series["series_key"], **finding}
            for series in series_results
            for finding in series["findings"]
        ),
        key=lambda item: (item["series_key"].casefold(), item["issue_id"]),
    )
    simulation_sha_after = _file_sha256(args.simulation_csv)
    observed_sha_after = _file_sha256(args.observed_csv)
    verified = (
        simulation_sha_after == simulation_sha_before
        and observed_sha_after == observed_sha_before
    )
    if not verified:
        raise RuntimeError("an input CSV changed while the empirical diagnostic was running")
    software_at_completion = _software_provenance()
    if _software_fingerprint(software_at_completion) != _software_fingerprint(
        software_at_start
    ):
        raise RuntimeError(
            "the executable source or metric registry changed while the empirical "
            "diagnostic was running"
        )

    successful = sum(item["status"] == "success" for item in series_results)
    failed = sum(item["status"] == "failed" for item in series_results)
    skipped = sum(item["status"] == "skipped" for item in series_results)
    explicitly_requested_skips = sorted({
        item["metric_id"]
        for item in series_results
        if item["status"] == "skipped" and item["metric_id"] in requested_metric_ids
    })
    payload = _json_safe({
        "schema_version": 2,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inference_scope": "descriptive_non_causal",
        "software": {
            "at_start": software_at_start,
            "at_completion": software_at_completion,
            "unchanged_during_run": True,
        },
        "inputs": {
            "simulation": {
                "path": str(args.simulation_csv),
                "sha256_before": simulation_sha_before,
                "sha256_after": simulation_sha_after,
                "timeline": simulation_timeline.metadata(),
            },
            "observed": {
                "path": str(args.observed_csv),
                "sha256_before": observed_sha_before,
                "sha256_after": observed_sha_after,
            },
        },
        "input_integrity": {
            "algorithm": "sha256",
            "verified": verified,
            "checked_before_read": True,
            "checked_after_processing": True,
        },
        "request": {
            "metric_ids": sorted(requested_metric_ids) or None,
            "auto_discover_all_metrics": not requested_metric_list,
            "single_metric_compatibility_mode": single_compatibility_mode,
            "simulation_start_date": args.simulation_start_date,
            "simulation_start_date_semantics": "first_retained_post_burn_tick",
            "geography": args.geography,
            "source": args.source,
            "series_id": args.series_id,
            "seasonal_adjustment": args.seasonal_adjustment,
            "vintage": args.vintage,
            "tick_field": args.tick_field,
            "tick_origin": args.tick_origin,
            "burn_in_ticks": args.burn_in_ticks,
            "allow_missing_requested": args.allow_missing_requested,
            "comparison_mode_override": comparison_mode,
            "allow_partial_periods": args.allow_partial_periods,
        },
        "summary": {
            "series_total": len(series_results),
            "series_successful": successful,
            "series_failed": failed,
            "series_skipped": skipped,
            "finding_count": len(findings),
        },
        "request_completeness": {
            "complete": not explicitly_requested_skips and failed == 0,
            "explicitly_requested_skipped_metrics": explicitly_requested_skips,
            "missing_requested_allowed": args.allow_missing_requested,
        },
        "findings": findings,
        "series": series_results,
    })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plural_path = args.output_dir / "empirical_diagnostics.json"
    plural_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if single_compatibility_mode:
        legacy = _json_safe(_legacy_payload(payload, series_results[0]))
        (args.output_dir / "empirical_diagnostic.json").write_text(
            json.dumps(legacy, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    _write_markdown(args.output_dir / "REPORT.md", payload)

    # Close the small race between payload construction and artifact writes.  A
    # changed input invalidates the run even if the output files were already made.
    if (
        _file_sha256(args.simulation_csv) != simulation_sha_after
        or _file_sha256(args.observed_csv) != observed_sha_after
    ):
        raise RuntimeError("an input CSV changed while empirical artifacts were written")
    if _software_fingerprint(_software_provenance()) != _software_fingerprint(
        software_at_completion
    ):
        raise RuntimeError(
            "the executable source or metric registry changed while empirical "
            "artifacts were written"
        )
    print(f"report: {args.output_dir / 'REPORT.md'}")
    print(
        f"series: {successful} successful, {failed} failed, {skipped} skipped; "
        f"findings: {len(findings)}"
    )
    requested_skip_failure = (
        bool(explicitly_requested_skips) and not args.allow_missing_requested
    )
    return 1 if failed or successful == 0 or requested_skip_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
