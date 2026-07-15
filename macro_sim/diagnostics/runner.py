"""Ten-process diagnostic execution, artifacts, paired responses, and reports."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path
from time import perf_counter
from typing import Any

# Ten independent Python processes are the intended parallelism.  Prevent each process
# from opening its own BLAS thread pool before numpy is imported.  ``PYTHONHASHSEED``
# only takes effect at interpreter startup, so remember the orchestrator's inherited
# value and force a deterministic value for every subsequently spawned worker.
_ORCHESTRATOR_HASHSEED_ENV_AT_IMPORT = os.environ.get("PYTHONHASHSEED")
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_thread_env] = "1"
os.environ["PYTHONHASHSEED"] = "0"

import numpy as np

from macro_sim.diagnostics.analysis import detect_run_problems, summarize_run
from macro_sim.diagnostics.models import Finding, RunOutcome, RunSpec, SEVERITY_ORDER
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.diagnostics.scenarios import build_frontier_config, diagnostic_intervention_window
from macro_sim.diagnostics.static_audit import run_static_audit
from macro_sim.diagnostics.world_probes import (
    build_small_world,
    diagnose_world,
    run_small_world_diagnostic,
)
from macro_sim.economy import Economy
from macro_sim.visualization.artifacts import write_series_csv


RESPONSE_KEYS = (
    "policy_rate", "desired_consumption", "effective_consumption",
    "real_gdp", "nominal_gdp", "cpi_fixed_basket",
    "cpi_fixed_basket_inflation_yoy", "real_output",
    "unemployment_rate", "investment_target_units", "investment_units", "new_loans",
    "credit_to_gdp", "credit_to_annual_gdp", "credit_to_annualized_daily_gdp",
    "credit_to_trailing_365d_gdp", "credit_to_best_available_annual_gdp",
    "inflation_yoy", "tobin_q_mean",
    "housing_sales_session",
    "gov_spending", "cash_deficit", "public_investment", "energy_produced",
    "energy_sold", "energy_unfilled",
)
PROBE_RESPONSE_KEYS = (
    "credit_requested_proxy", "firm_interest_due_proxy", "final_demand_proxy",
    "credit_kappa", "government_deficit_target", "energy_shock_active",
    "firm_credit_requested", "firm_credit_leverage_allowed",
    "firm_credit_leverage_shortfall", "firm_credit_leverage_constrained_share",
    "firm_credit_bank_shortfall",
    "priced_firm_balance_sheet_enabled", "firm_eligible_collateral_value",
    "firm_borrowing_base_proxy",
)

FIRST_STAGE_KEYS = {
    "policy_rate": ("policy_rate", 1.0e-8),
    "kappa_multiplier": ("credit_kappa", 1.0e-8),
    "deficit_target": ("government_deficit_target", 1.0e-8),
    "energy_capacity": ("energy_shock_active", 0.5),
}

FIRST_STAGE_DIRECTIONS = {
    "rate_cut": -1.0,
    "rate_hike": 1.0,
    "credit_tightening": -1.0,
    "fiscal_expansion": 1.0,
    "energy_shock": 1.0,
}

DID_NEAR_ZERO_THRESHOLD = 1.0e-10
CREDIT_PROXIMAL_KEYS = (
    "new_loans",
    "firm_credit_leverage_shortfall",
    "firm_credit_leverage_constrained_share",
    "firm_credit_bank_shortfall",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

HARD_RECORD_KEYS = frozenset({
    "t", "genesis_money", "conservation_drift", "reserve_conservation_drift",
    "shares_conservation_drift", "real_output", "price_index", "policy_rate",
    "new_loans", "effective_unemployment",
})
NATIONAL_ACCOUNTS_RECORD_KEYS = frozenset({
    "national_accounts_enabled", "nominal_gdp", "real_gdp", "real_gdp_per_capita",
    "credit_to_best_available_annual_gdp", "total_debt_service_to_nominal_gdp",
    "cpi_fixed_basket", "cpi_fixed_basket_inflation_yoy",
    "cpi_fixed_basket_inflation_yoy_observed",
    "gdp_nominal_production", "gdp_nominal_expenditure_observed",
    "gdp_nominal_energy_cap_product_subsidy",
    "gdp_nominal_export_product_subsidy_signed",
    "gdp_nominal_import_duty_signed",
    "gdp_nominal_vat_observed",
    "gdp_nominal_energy_excise_observed",
    "gdp_nominal_net_product_taxes_observed",
    "gdp_nominal_basic_price_corrected_observed",
    "gdp_nominal_market_price_observed",
    "gdp_jg_public_works_output_observed",
    "gdp_nominal_jg_own_account_capital_at_cost",
    "gdp_real_jg_own_account_capital_units",
    "gdp_nominal_jg_income_floor_transfer",
    "gdp_nominal_expanded_production_candidate",
    "gdp_nominal_expanded_fixed_capital_formation_candidate",
    "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
    "gdp_nominal_expanded_compensation_candidate",
    "gdp_nominal_expenditure_reconciliation_residual",
    "gdp_nominal_expenditure_residual_share",
    "gdp_nominal_expenditure_reconciled", "gdp_nominal_income_observed",
    "gdp_nominal_income_reconciliation_residual",
    "gdp_nominal_income_residual_share", "gdp_nominal_income_reconciled",
    "gdp_nominal_income_output_sales_accrual_c",
    "gdp_nominal_income_output_sales_accrual_k",
    "gdp_nominal_income_output_sales_accrual_e",
    "gdp_nominal_income_output_sales_accrual_housing",
    "gdp_nominal_income_output_sales_accrual_other",
    "gdp_nominal_income_intermediate_scope_adjustment",
    "gdp_nominal_income_accrual_bridge",
    "gdp_nominal_income_accrual_bridge_share",
    "gdp_nominal_accrued_gross_operating_surplus",
    "gdp_nominal_income_accrued_observed",
    "gdp_nominal_income_unexplained_residual",
    "gdp_nominal_income_unexplained_residual_share",
    "gdp_real_production", "gdp_real_expenditure_observed",
    "gdp_real_expenditure_reconciliation_residual",
    "gdp_real_expenditure_residual_share", "gdp_real_expenditure_reconciled",
    "gdp_nominal_exports", "gdp_nominal_imports", "gdp_nominal_net_exports",
    "gdp_real_exports", "gdp_real_imports", "gdp_real_net_exports",
    "gdp_expenditure_includes_observed_net_exports",
    "gdp_nominal_three_approach_raw_spread_share",
})
HARD_PROBE_KEYS = frozenset({
    "t", "nonfinite_official_values", "min_inventory", "min_capital",
    "final_demand_proxy", "reported_nominal_output", "credit_kappa",
    "firm_full_pnl_enabled", "firm_pnl_revenue",
    "firm_pnl_intermediate_inputs", "firm_pnl_compensation",
    "firm_pnl_ebitda", "firm_pnl_depreciation", "firm_pnl_ebit",
    "firm_pnl_cash_interest", "firm_pnl_pre_tax_income",
    "firm_pnl_tax_total", "firm_pnl_net_income",
    "firm_pnl_dividends_paid", "firm_pnl_retained_earnings",
    "firm_pnl_interest_arrears", "firm_pnl_bridge_max_abs_residual",
    "firm_pnl_post_close_revenue_carry",
    "firm_pnl_profit_compatibility_residual",
    "firm_pnl_interest_cash_counter_residual",
    "firm_bank_interest_counterparty_residual",
})


def _json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str) or value is None:
        return value
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True))


def _stable_digest(payload: Any) -> str:
    def canonical(value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return canonical(dataclasses.asdict(value))
        if isinstance(value, dict):
            return {str(key): canonical(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        if isinstance(value, (float, np.floating)):
            number = float(value)
            if math.isnan(number):
                return {"__nonfinite_float__": "nan"}
            if math.isinf(number):
                return {"__nonfinite_float__": "+inf" if number > 0.0 else "-inf"}
            return number
        if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
            return int(value)
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, str) or value is None:
            return value
        return {"__python_repr__": repr(value), "__python_type__": type(value).__qualname__}

    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_run_data(
    records: list[dict[str, Any]], probes: list[dict[str, Any]], spec: RunSpec,
) -> tuple[Finding, ...]:
    """Fail closed when a collector/schema regression could hide an economic defect."""

    evidence: dict[str, Any] = {}
    if len(records) != spec.ticks or len(probes) != spec.ticks or len(records) != len(probes):
        evidence["lengths"] = {
            "expected": spec.ticks, "records": len(records), "probes": len(probes),
        }

    def inspect_rows(
        rows: list[dict[str, Any]], required: frozenset[str], label: str,
    ) -> None:
        missing: dict[str, list[int]] = {}
        nonfinite: dict[str, list[int]] = {}
        ticks: list[Any] = []
        reference_schema = set(rows[0]) if rows else set()
        schema_mismatches: list[int] = []
        for index, row in enumerate(rows):
            ticks.append(row.get("t"))
            if set(row) != reference_schema:
                schema_mismatches.append(index)
            for key in required:
                if key not in row:
                    missing.setdefault(key, []).append(index)
                    continue
                value = row[key]
                if not isinstance(value, (int, float, np.number)) or not math.isfinite(float(value)):
                    nonfinite.setdefault(key, []).append(index)
        if missing:
            evidence[f"{label}_missing_required_fields"] = {
                key: indices[:10] for key, indices in sorted(missing.items())
            }
        if nonfinite:
            evidence[f"{label}_nonfinite_required_fields"] = {
                key: indices[:10] for key, indices in sorted(nonfinite.items())
            }
        expected_ticks = list(range(len(rows)))
        if ticks != expected_ticks:
            evidence[f"{label}_tick_sequence"] = {"expected": expected_ticks[:20], "actual": ticks[:20]}
        if schema_mismatches:
            evidence[f"{label}_schema_mismatch_ticks"] = schema_mismatches[:20]

    record_keys = HARD_RECORD_KEYS
    # All production-frontier configs enable the v23 account; an explicit test or
    # compatibility override may still turn it off and should then validate against
    # the legacy schema rather than fail for intentionally absent optional fields.
    if spec.overrides.get("national_accounts_metrics", True):
        record_keys = record_keys | NATIONAL_ACCOUNTS_RECORD_KEYS
    inspect_rows(records, record_keys, "records")
    inspect_rows(probes, HARD_PROBE_KEYS, "probes")
    if not evidence:
        return ()
    return (Finding(
        issue_id="validity.diagnostic_data_incomplete",
        severity="critical",
        confidence="confirmed",
        category="validity",
        claim="The diagnostic collector produced incomplete, discontinuous, or invalid data.",
        evidence=evidence,
        requested_probes=("collector_schema_diff", "first_invalid_tick"),
        recommendation="Repair the collector/schema regression before interpreting any economic finding from this run.",
        measurement_status="invalid_run",
        detector="diagnostic_schema_gate",
    ),)


def _causal_provenance(
    records: list[dict[str, Any]], probes: list[dict[str, Any]], spec: RunSpec,
) -> dict[str, Any]:
    default_start, _ = diagnostic_intervention_window(spec.ticks)
    start = spec.intervention.start_tick if spec.intervention is not None else default_start
    structural = {
        "seed": spec.seed,
        "ticks": spec.ticks,
        "population": spec.population,
        "n_firms_c": spec.n_firms_c,
        "n_firms_k": spec.n_firms_k,
        "n_banks": spec.n_banks,
        "overrides": spec.overrides,
    }
    return {
        "intervention_start_tick": start,
        "structural_signature": _stable_digest(structural),
        "pre_intervention_digest": _stable_digest({
            "records": records[:start], "probes": probes[:start],
        }),
        "pre_intervention_ticks": start,
    }


def _mean_window(rows: list[dict], key: str, start: int, end: int) -> float:
    values = []
    for row in rows[start:end]:
        value = row.get(key)
        if isinstance(value, (int, float, np.number)) and math.isfinite(float(value)):
            values.append(float(value))
    return float(np.mean(values)) if values else float("nan")


def _response_windows(records: list[dict], probes: list[dict], spec: RunSpec) -> dict[str, Any]:
    default_start, default_end = diagnostic_intervention_window(spec.ticks)
    start = spec.intervention.start_tick if spec.intervention else default_start
    end = spec.intervention.end_tick if spec.intervention and spec.intervention.end_tick else default_end
    width = max(1, end - start)
    pre_start = max(0, start - width)
    post_end = min(spec.ticks, end + width)
    result: dict[str, Any] = {"bounds": {"pre": [pre_start, start], "during": [start, end], "post": [end, post_end]}}
    for key in RESPONSE_KEYS:
        result[key] = {
            "pre": _mean_window(records, key, pre_start, start),
            "during": _mean_window(records, key, start, end),
            "post": _mean_window(records, key, end, post_end),
        }
    for key in PROBE_RESPONSE_KEYS:
        result[key] = {
            "pre": _mean_window(probes, key, pre_start, start),
            "during": _mean_window(probes, key, start, end),
            "post": _mean_window(probes, key, end, post_end),
        }
    return result


def _apply_intervention(econ: Economy, spec: RunSpec, tick: int, original: dict[str, float | None]) -> None:
    intervention = spec.intervention
    if intervention is None or spec.scenario == "energy_shock":
        return
    if tick == intervention.start_tick:
        if intervention.kind == "policy_rate":
            original["policy_rate_override"] = econ.policy.policy_rate_override
            econ.policy.policy_rate_override = intervention.value
        elif intervention.kind == "kappa_multiplier":
            original["kappa"] = econ.policy.kappa
            econ.policy.kappa = econ.policy.kappa * float(intervention.value)
        elif intervention.kind == "deficit_target":
            original["gov_deficit_target"] = econ.policy.gov_deficit_target
            econ.policy.gov_deficit_target = float(intervention.value)
        else:
            raise ValueError(f"unsupported intervention kind {intervention.kind!r}")
    if intervention.end_tick is not None and tick == intervention.end_tick:
        if intervention.kind == "policy_rate":
            econ.policy.policy_rate_override = original.get("policy_rate_override")
        elif intervention.kind == "kappa_multiplier":
            econ.policy.kappa = float(original["kappa"])
        elif intervention.kind == "deficit_target":
            econ.policy.gov_deficit_target = float(original["gov_deficit_target"])


def _run_one(spec: RunSpec, output_root: str) -> RunOutcome:
    """Worker entry point.  Full series are persisted locally, not returned over IPC."""

    started = perf_counter()
    run_dir = Path(output_root) / "runs" / spec.name
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        cfg = build_frontier_config(spec)
        _write_json(run_dir / "config.json", dataclasses.asdict(cfg))
        _write_json(run_dir / "spec.json", spec.to_dict())
        econ = Economy(cfg)
        collector = DeepProbeCollector()
        probes: list[dict[str, float]] = []
        original: dict[str, float | None] = {}
        for tick in range(spec.ticks):
            _apply_intervention(econ, spec, tick, original)
            record = econ.step()
            probes.append(collector.collect(econ, record))
        records = econ.records
        validity_findings = _validate_run_data(records, probes, spec)
        if validity_findings:
            summary = {
                "n_ticks": len(records), "scenario": spec.scenario, "seed": spec.seed,
                "diagnostic_validity": "failed",
            }
            findings = validity_findings
        else:
            summary = summarize_run(records, probes, spec)
            summary["response_windows"] = _response_windows(records, probes, spec)
            summary["causal_provenance"] = _causal_provenance(records, probes, spec)
            summary["diagnostic_validity"] = "passed"
            findings = detect_run_problems(records, probes, spec)
        write_series_csv(records, run_dir / "series.csv")
        write_series_csv(probes, run_dir / "probes.csv")
        _write_json(run_dir / "summary.json", summary)
        _write_json(run_dir / "findings.json", [item.to_dict() for item in findings])
        return RunOutcome(
            spec=spec,
            run_dir=str(run_dir),
            elapsed_seconds=perf_counter() - started,
            summary=summary,
            findings=findings,
        )
    except Exception:
        error = traceback.format_exc()
        (run_dir / "error.txt").write_text(error)
        return RunOutcome(
            spec=spec,
            run_dir=str(run_dir),
            elapsed_seconds=perf_counter() - started,
            summary={},
            findings=(),
            error=error,
        )


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=_REPO_ROOT,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"], text=True, cwd=_REPO_ROOT,
        ).splitlines()
        diff = subprocess.check_output(
            ["git", "diff", "--binary", "HEAD", "--", "macro_sim", "tests", "pyproject.toml", "docs/plans"],
            cwd=_REPO_ROOT,
        )
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "macro_sim", "tests", "pyproject.toml", "docs/plans"],
            text=True, cwd=_REPO_ROOT,
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
        return {"revision": "unknown", "dirty": None, "source_diff_sha256": None, "dirty_paths": []}


def _file_sha256(path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _REPO_ROOT / candidate
    if not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _validate_suite_specs(specs: list[RunSpec]) -> None:
    if not specs:
        raise ValueError("the diagnostic suite needs at least one run")
    names = [spec.name for spec in specs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"diagnostic run names must be unique: {duplicates}")
    unsafe = [name for name in names if not name or Path(name).name != name or name in {".", ".."}]
    if unsafe:
        raise ValueError(f"diagnostic run names must be safe single path components: {unsafe}")
    disguised_arms = [
        spec.name for spec in specs
        if spec.scenario == "baseline" and spec.intervention is not None
    ]
    if disguised_arms:
        raise ValueError(
            "baseline runs cannot carry interventions (they would be aggregated as "
            f"untreated findings): {disguised_arms}"
        )
    ablation_arms = [
        spec.name for spec in specs
        if spec.scenario.startswith("ablation:") and spec.intervention is not None
    ]
    if ablation_arms:
        raise ValueError(f"permanent ablations cannot carry temporary interventions: {ablation_arms}")


def _diagnostic_run_valid(outcome: RunOutcome) -> bool:
    return (
        outcome.error is None
        and outcome.summary.get("diagnostic_validity") == "passed"
    )


def _effect_evidence(values: list[float]) -> dict[str, Any]:
    """Summarize finite paired DIDs without converting their average into a claim."""
    finite = [float(value) for value in values if math.isfinite(float(value))]
    positive = sum(value > DID_NEAR_ZERO_THRESHOLD for value in finite)
    negative = sum(value < -DID_NEAR_ZERO_THRESHOLD for value in finite)
    near_zero = len(finite) - positive - negative
    counts = {"positive": positive, "negative": negative, "near_zero": near_zero}
    dominant = max(counts, key=counts.get) if finite else None
    dominant_count = counts[dominant] if dominant is not None else 0
    if len(finite) < 3:
        status = "insufficient"
        consistent_direction = None
    elif dominant_count == len(finite):
        status = "consistent"
        consistent_direction = dominant
    else:
        status = "mixed"
        consistent_direction = None
    return {
        "n": len(finite),
        "median": float(np.median(finite)) if finite else None,
        "positive_count": positive,
        "negative_count": negative,
        "near_zero_count": near_zero,
        "near_zero_threshold": DID_NEAR_ZERO_THRESHOLD,
        "sign_consistency": dominant_count / len(finite) if finite else None,
        "dominant_direction": dominant,
        "consistent_direction": consistent_direction,
        "effect_evidence_status": status,
    }


def _scenario_effect_evidence(
    responses: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    values: dict[str, dict[str, list[float]]] = {}
    for response in responses:
        if not response.get("causal_validity", {}).get("identified", False):
            continue
        scenario = response["scenario"]
        for metric, raw in response.get("difference_in_differences", {}).items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.setdefault(scenario, {}).setdefault(metric, []).append(value)
    return {
        scenario: {
            metric: _effect_evidence(metric_values)
            for metric, metric_values in metrics.items()
        }
        for scenario, metrics in values.items()
    }


def _paired_responses(outcomes: list[RunOutcome]) -> list[dict[str, Any]]:
    baselines: dict[str | None, list[RunOutcome]] = {}
    for candidate in outcomes:
        if candidate.spec.scenario == "baseline" and candidate.error is None:
            baselines.setdefault(candidate.spec.pair_id, []).append(candidate)
    responses: list[dict[str, Any]] = []
    for outcome in outcomes:
        if (
            outcome.spec.scenario == "baseline"
            or outcome.error is not None
            or outcome.spec.intervention is None
        ):
            continue
        candidates = baselines.get(outcome.spec.pair_id, [])
        baseline = candidates[0] if len(candidates) == 1 else None
        arm_provenance = outcome.summary.get("causal_provenance", {})
        base_provenance = baseline.summary.get("causal_provenance", {}) if baseline else {}
        arm_windows = outcome.summary.get("response_windows", {})
        base_windows = baseline.summary.get("response_windows", {}) if baseline else {}
        causal_checks = {
            "exactly_one_baseline": len(candidates) == 1,
            "same_seed": bool(baseline and baseline.spec.seed == outcome.spec.seed),
            "same_dimensions": bool(baseline and (
                baseline.spec.ticks, baseline.spec.population, baseline.spec.n_firms_c,
                baseline.spec.n_firms_k, baseline.spec.n_banks,
            ) == (
                outcome.spec.ticks, outcome.spec.population, outcome.spec.n_firms_c,
                outcome.spec.n_firms_k, outcome.spec.n_banks,
            )),
            "same_structural_config": bool(
                baseline
                and arm_provenance.get("structural_signature")
                and arm_provenance.get("structural_signature") == base_provenance.get("structural_signature")
            ),
            "same_windows": bool(
                baseline and arm_windows.get("bounds") == base_windows.get("bounds")
            ),
            "pre_intervention_identical": bool(
                baseline
                and arm_provenance.get("pre_intervention_digest")
                and arm_provenance.get("pre_intervention_digest")
                == base_provenance.get("pre_intervention_digest")
            ),
        }
        identified = all(causal_checks.values())
        causal_validity = {
            "identified": identified,
            "checks": causal_checks,
            "arm_pre_digest": arm_provenance.get("pre_intervention_digest"),
            "baseline_pre_digest": base_provenance.get("pre_intervention_digest"),
        }
        if not identified:
            responses.append({
                "scenario": outcome.spec.scenario,
                "run": outcome.spec.name,
                "baseline": baseline.spec.name if baseline else None,
                "pair_id": outcome.spec.pair_id,
                "causal_validity": causal_validity,
                "difference_in_differences": {},
                "post_difference_in_differences": {},
                "during_level_difference": {},
                "first_stage": {"passed": None, "metric": None, "during_level_difference": None},
            })
            continue
        deltas: dict[str, Any] = {}
        post_deltas: dict[str, Any] = {}
        level_differences: dict[str, Any] = {}
        for key in (*RESPONSE_KEYS, *PROBE_RESPONSE_KEYS):
            arm = arm_windows.get(key, {})
            base = base_windows.get(key, {})
            arm_change = arm.get("during", float("nan")) - arm.get("pre", float("nan"))
            base_change = base.get("during", float("nan")) - base.get("pre", float("nan"))
            deltas[key] = arm_change - base_change
            arm_post_change = arm.get("post", float("nan")) - arm.get("pre", float("nan"))
            base_post_change = base.get("post", float("nan")) - base.get("pre", float("nan"))
            post_deltas[key] = arm_post_change - base_post_change
            level_differences[key] = arm.get("during", float("nan")) - base.get("during", float("nan"))
        first_stage = {"passed": None, "metric": None, "during_level_difference": None}
        if outcome.spec.intervention is not None:
            mapping = FIRST_STAGE_KEYS.get(outcome.spec.intervention.kind)
            if mapping is not None:
                metric, threshold = mapping
                observed = level_differences.get(metric, float("nan"))
                direction = FIRST_STAGE_DIRECTIONS.get(outcome.spec.scenario)
                passed = bool(
                    math.isfinite(observed)
                    and (
                        observed * direction >= threshold
                        if direction is not None
                        else abs(observed) >= threshold
                    )
                )
                first_stage = {
                    "passed": passed,
                    "metric": metric,
                    "during_level_difference": observed,
                    "threshold": threshold,
                    "expected_direction": (
                        "increase" if direction == 1.0 else
                        "decrease" if direction == -1.0 else
                        "either"
                    ),
                }
        responses.append({
            "scenario": outcome.spec.scenario,
            "run": outcome.spec.name,
            "baseline": baseline.spec.name,
            "pair_id": outcome.spec.pair_id,
            "causal_validity": causal_validity,
            "difference_in_differences": deltas,
            "post_difference_in_differences": post_deltas,
            "during_level_difference": level_differences,
            "first_stage": first_stage,
        })
    valid_counts: dict[str, int] = {}
    for response in responses:
        if response["causal_validity"]["identified"]:
            valid_counts[response["scenario"]] = valid_counts.get(response["scenario"], 0) + 1
    effect_evidence = _scenario_effect_evidence(responses)
    for response in responses:
        n_pairs = valid_counts.get(response["scenario"], 0)
        if n_pairs >= 3:
            design_status = "design_replicated"
        elif n_pairs == 2:
            design_status = "limited_design_replication"
        elif n_pairs == 1:
            design_status = "exploratory_single_seed"
        else:
            design_status = "no_valid_pairs"
        response["replication"] = {
            "n_valid_pairs_for_scenario": n_pairs,
            "design_replication_status": design_status,
            # Compatibility field retained, but it now names design evidence rather
            # than falsely declaring a replicated treatment effect.
            "evidence_status": design_status,
            "design_replication": {
                "n_valid_pairs": n_pairs,
                "replication_threshold": 3,
                "status": design_status,
            },
            "effect_evidence_by_metric": effect_evidence.get(response["scenario"], {}),
        }
    return responses


def _credit_proximal_did(response: dict[str, Any]) -> float | None:
    """Return the registered proximal response only when every component is finite."""
    did = response.get("difference_in_differences", {})
    values: list[float] = []
    for key in CREDIT_PROXIMAL_KEYS:
        try:
            value = float(did[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        values.append(abs(value))
    return max(values)


def _aggregate_issues(
    outcomes: list[RunOutcome], static_findings: tuple[Finding, ...], responses: list[dict[str, Any]],
    supplemental_findings: tuple[tuple[str, tuple[Finding, ...]], ...] = (),
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for finding in static_findings:
        grouped[finding.issue_id] = {
            **finding.to_dict(), "affected_runs": ["static"], "evidence_samples": [finding.evidence]
        }
    for outcome in outcomes:
        # Structural/economy findings are estimated from untreated baselines only.
        # Intervention arms can support conditional paired claims below, but merging
        # their tail pathologies here would mislabel treatment effects as baseline bugs.
        if outcome.spec.scenario not in {"baseline", "ablation:reference"}:
            continue
        for finding in outcome.findings:
            item = grouped.setdefault(finding.issue_id, {
                **finding.to_dict(), "affected_runs": [], "evidence_samples": []
            })
            item["affected_runs"].append(outcome.spec.name)
            if len(item["evidence_samples"]) < 5:
                item["evidence_samples"].append(finding.evidence)
            if SEVERITY_ORDER[finding.severity] > SEVERITY_ORDER[item["severity"]]:
                item["severity"] = finding.severity
    for source, findings in supplemental_findings:
        for finding in findings:
            item = grouped.setdefault(finding.issue_id, {
                **finding.to_dict(), "affected_runs": [], "evidence_samples": []
            })
            item["affected_runs"].append(source)
            if len(item["evidence_samples"]) < 5:
                item["evidence_samples"].append(finding.evidence)
            if SEVERITY_ORDER[finding.severity] > SEVERITY_ORDER[item["severity"]]:
                item["severity"] = finding.severity

    # First-stage validity is part of the result, not an optional plotting detail.
    credit_pairs: list[dict[str, Any]] = []
    for response in responses:
        causal_validity = response.get("causal_validity", {})
        if not causal_validity.get("identified", False):
            issue_id = f"experiment.{response['scenario']}.invalid_causal_pair"
            grouped[issue_id] = {
                "issue_id": issue_id,
                "severity": "critical",
                "confidence": "confirmed",
                "category": "experiment",
                "claim": "The intervention arm is not an identified causal twin of its baseline.",
                "evidence": causal_validity,
                "suspected_mechanisms": ["seed/config mismatch", "pre-treatment divergence", "ambiguous baseline"],
                "requested_probes": ["tick_by_tick_pre_intervention_state_hash"],
                "recommendation": "Discard the response and rebuild an exact same-seed, same-config twin.",
                "measurement_status": "invalid_experiment",
                "detector": "paired_causal_validity_gate",
                "affected_runs": [response["run"]],
                "evidence_samples": [causal_validity],
            }
            continue
        first_stage = response.get("first_stage", {})
        if first_stage.get("passed") is False:
            observed_first_stage = first_stage.get("during_level_difference")
            blocked_at_zlb = (
                response["scenario"] == "rate_cut"
                and isinstance(observed_first_stage, (int, float, np.number))
                and math.isfinite(float(observed_first_stage))
                and abs(float(observed_first_stage)) < float(first_stage.get("threshold", 0.0))
            )
            issue_id = (
                "monetary.easing_blocked_by_zlb"
                if blocked_at_zlb
                else f"experiment.{response['scenario']}.no_first_stage"
            )
            grouped[issue_id] = {
                "issue_id": issue_id,
                "severity": "high",
                "confidence": "confirmed",
                "category": "experiment",
                "claim": (
                    "The rate-cut arm cannot lower the already-zero policy rate."
                    if blocked_at_zlb
                    else "The intervention did not move its registered treatment variable."
                ),
                "evidence": first_stage,
                "suspected_mechanisms": ["effective lower bound"] if blocked_at_zlb else [],
                "requested_probes": ["alternative_instrument_or_positive_rate_baseline"],
                "recommendation": (
                    "Mark the easing IRF unidentified at the ZLB and test a non-rate instrument or a positive-rate baseline."
                    if blocked_at_zlb
                    else "Repair or redesign the treatment before interpreting outcome differences."
                ),
                "measurement_status": "inconclusive_experiment",
                "detector": "paired_first_stage",
                "affected_runs": [response["run"]],
                "evidence_samples": [first_stage],
            }

        if response["scenario"] == "credit_tightening" and first_stage.get("passed") is True:
            proximal = _credit_proximal_did(response)
            if proximal is not None:
                credit_pairs.append({
                    "run": response["run"],
                    "max_proximal_did": proximal,
                    "supports_nonbinding": proximal <= DID_NEAR_ZERO_THRESHOLD,
                    "first_stage": first_stage,
                    "replication": response.get("replication", {}),
                })

        # A valid paired-rate first stage dynamically complements (but cannot replace)
        # the local static derivative audit.
        if response["scenario"] in {"rate_cut", "rate_hike"} and first_stage.get("passed") is True:
            did = response["difference_in_differences"]
            item = grouped.get("monetary.direct_demand_channels_missing")
            if item is not None:
                item["evidence_samples"].append({
                    "paired_run": response["run"],
                    "policy_rate_did": did.get("policy_rate"),
                    "investment_target_did": did.get("investment_target_units"),
                    "credit_request_did": did.get("credit_requested_proxy"),
                    "interpretation": "total effects; local direct derivative is established by static signature",
                })
                item["affected_runs"].append(response["run"])

    supporting = [pair for pair in credit_pairs if pair["supports_nonbinding"]]
    counterexamples = [pair for pair in credit_pairs if not pair["supports_nonbinding"]]
    if supporting:
        consistently_supported = not counterexamples
        replicated_support = consistently_supported and len(supporting) >= 3
        if replicated_support:
            severity = "high"
            confidence = "high"
            effect_status = "consistent"
            measurement_status = "replicated_consistent_effect"
            claim = (
                "Across at least three valid pairs, halving the leverage cap moves the "
                "policy parameter but consistently has no proximal credit effect."
            )
        elif counterexamples:
            severity = "medium"
            confidence = "low"
            effect_status = "mixed"
            measurement_status = "mixed_effect_evidence"
            claim = (
                "Some paired runs show no proximal response to the tighter leverage cap, "
                "but other valid pairs are counterexamples; the scenario-level effect is mixed."
            )
        else:
            severity = "medium"
            confidence = "medium"
            effect_status = "insufficient"
            measurement_status = (
                "exploratory_single_seed" if len(supporting) == 1
                else "insufficient_effect_replication"
            )
            claim = (
                "The available paired run(s) show no proximal response to the tighter "
                "leverage cap, but fewer than three supporting pairs make this exploratory."
            )
        scenario_replication = supporting[0].get("replication", {})
        evidence = {
            "proximal_threshold": DID_NEAR_ZERO_THRESHOLD,
            "n_evaluable_pairs": len(credit_pairs),
            "supporting_pair_count": len(supporting),
            "counterexample_pair_count": len(counterexamples),
            "supporting_runs": [pair["run"] for pair in supporting],
            "counterexample_runs": [pair["run"] for pair in counterexamples],
            "max_proximal_did_by_run": {
                pair["run"]: pair["max_proximal_did"] for pair in credit_pairs
            },
            "effect_evidence_status": effect_status,
            "claim_replication_status": (
                "replicated_consistent_support"
                if replicated_support else measurement_status
            ),
            "scenario_design_replication": scenario_replication,
        }
        grouped["credit.leverage_cap_nonbinding"] = {
            "issue_id": "credit.leverage_cap_nonbinding",
            "severity": severity,
            "confidence": confidence,
            "category": "credit",
            "claim": claim,
            "evidence": evidence,
            "suspected_mechanisms": [
                "firms do not borrow at the margin", "cash-only borrowing base",
            ],
            "requested_probes": [
                "firm_headroom_distribution", "binding_constraint_share",
            ],
            "recommendation": (
                "Report the share of applicants constrained by each underwriting edge "
                "before using this arm as a credit shock."
            ),
            "measurement_status": measurement_status,
            "detector": "paired_proximal_response",
            # Counterexamples are evidence against the claim, not affected runs that
            # should be mislabeled as supporting it.
            "affected_runs": [pair["run"] for pair in supporting],
            "evidence_samples": [
                {
                    "run": pair["run"],
                    "first_stage": pair["first_stage"],
                    "max_proximal_did": pair["max_proximal_did"],
                }
                for pair in supporting[:5]
            ],
        }

    return sorted(grouped.values(), key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["issue_id"]))


ABLATION_METRICS: dict[str, tuple[str, ...]] = {
    "real_gdp": ("tail", "real_gdp", "mean"),
    "real_output": ("tail", "real_output", "mean"),
    "effective_unemployment": ("tail", "effective_unemployment", "mean"),
    "jg_employment_rate": ("tail", "jg_employment_rate", "mean"),
    "inflation_yoy": ("tail", "inflation_yoy", "median"),
    "credit_to_best_available_annual_gdp": (
        "tail", "credit_to_best_available_annual_gdp", "mean"
    ),
    "public_capital_stock": ("probe_tail", "public_capital_stock", "mean"),
    "public_capital_factor": ("probe_tail", "public_capital_factor", "mean"),
    "job_guarantee_capital_flow": ("probe_tail", "job_guarantee_capital_units", "mean"),
    "government_capital_flow": ("probe_tail", "government_capital_units", "mean"),
    "job_guarantee_workers": ("probe_tail", "job_guarantee_workers", "mean"),
    "final_demand_proxy": ("probe_tail", "final_demand_proxy", "mean"),
}


def _nested_float(payload: dict[str, Any], path: tuple[str, ...]) -> float:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return float("nan")
        current = current[key]
    try:
        value = float(current)
    except (TypeError, ValueError):
        return float("nan")
    return value if math.isfinite(value) else float("nan")


def _ablation_attribution(outcomes: list[RunOutcome]) -> dict[str, Any]:
    ablations = [
        outcome for outcome in outcomes
        if _diagnostic_run_valid(outcome) and outcome.spec.scenario.startswith("ablation:")
    ]
    references = [
        outcome for outcome in ablations if outcome.spec.scenario == "ablation:reference"
    ]
    if len(references) != 1:
        return {}
    reference = references[0]
    reference_values = {
        metric: _nested_float(reference.summary, path)
        for metric, path in ABLATION_METRICS.items()
    }
    comparisons: list[dict[str, Any]] = []
    for outcome in ablations:
        if outcome is reference:
            continue
        values = {
            metric: _nested_float(outcome.summary, path)
            for metric, path in ABLATION_METRICS.items()
        }
        deltas = {
            metric: values[metric] - reference_values[metric]
            if math.isfinite(values[metric]) and math.isfinite(reference_values[metric])
            else float("nan")
            for metric in ABLATION_METRICS
        }
        relative = {
            metric: deltas[metric] / abs(reference_values[metric])
            if math.isfinite(deltas[metric]) and abs(reference_values[metric]) > 1.0e-12
            else float("nan")
            for metric in ABLATION_METRICS
        }
        comparisons.append({
            "run": outcome.spec.name,
            "mechanism_removed": outcome.spec.scenario.removeprefix("ablation:"),
            "overrides": outcome.spec.overrides,
            "values": values,
            "absolute_change_from_reference": deltas,
            "relative_change_from_reference": relative,
        })
    strongest: dict[str, list[dict[str, Any]]] = {}
    for metric in ABLATION_METRICS:
        ranked = [
            {
                "mechanism_removed": item["mechanism_removed"],
                "relative_change": item["relative_change_from_reference"][metric],
                "absolute_change": item["absolute_change_from_reference"][metric],
            }
            for item in comparisons
            if math.isfinite(item["relative_change_from_reference"][metric])
        ]
        strongest[metric] = sorted(
            ranked, key=lambda item: abs(item["relative_change"]), reverse=True,
        )[:5]
    return {
        "method": (
            "same-seed permanent named mechanism-bundle ablations; "
            "descriptive exploratory structural attribution"
        ),
        "design": {
            "seed_count": 1,
            "evidence_status": "exploratory_single_seed",
            "causal_scope": "named_mechanism_bundle_not_atomic_mechanism",
            "replication_required_for_effect_claim": True,
            "caveat": (
                "Several arms intentionally switch a coherent bundle of related "
                "features, so their deltas cannot identify one atomic mechanism."
            ),
        },
        "reference_run": reference.spec.name,
        "reference_values": reference_values,
        "comparisons": comparisons,
        "strongest_effects": strongest,
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# V23 Economic Diagnostic Report",
        "",
        f"- Git revision: `{payload['manifest']['git_revision']}`",
        f"- Jobs: {payload['manifest']['jobs']} ({payload['manifest']['successful']} successful)",
        f"- Workers: {payload['manifest']['workers']}",
        f"- Created: {payload['manifest']['created']}",
        "",
        "## Findings",
        "",
    ]
    for index, issue in enumerate(payload["issues"], 1):
        lines.extend([
            f"### {index}. [{issue['severity'].upper()}] `{issue['issue_id']}`",
            "",
            issue["claim"],
            "",
            f"- Confidence: {issue['confidence']}",
            f"- Category: {issue['category']}",
            f"- Measurement status: {issue['measurement_status']}",
            f"- Affected runs: {', '.join(issue['affected_runs'])}",
        ])
        if issue.get("recommendation"):
            lines.append(f"- Recommendation: {issue['recommendation']}")
        if issue.get("requested_probes"):
            lines.append(f"- Next probes: {', '.join(issue['requested_probes'])}")
        lines.extend(["", "Evidence samples:", "", "```json",
                      json.dumps(_json_safe(issue.get("evidence_samples", [])), indent=2, sort_keys=True),
                      "```", ""])
    lines.extend(["## Paired responses", "", "```json",
                  json.dumps(_json_safe(payload["paired_responses"]), indent=2, sort_keys=True),
                  "```", ""])
    if payload.get("ablation_attribution"):
        lines.extend(["## Structural ablation attribution", "", "```json",
                      json.dumps(_json_safe(payload["ablation_attribution"]), indent=2, sort_keys=True),
                      "```", ""])
    path.write_text("\n".join(lines))


def _run_world_probe_suite() -> tuple[dict[str, Any], tuple[tuple[str, tuple[Finding, ...]], ...]]:
    """Run fast open-economy identities that do not belong in domestic workers."""

    cases: dict[str, Any] = {
        "two_country": run_small_world_diagnostic(n=2, ticks=14, population=30),
        "three_country": run_small_world_diagnostic(n=3, ticks=8, population=30),
        "consumption_strata": run_small_world_diagnostic(
            n=2, ticks=8, population=30, consumption_strata=True,
        ),
    }
    daily_world = build_small_world(n=2, ticks=1, population=12, daily=True)
    cases["daily_clock_contract"] = diagnose_world(daily_world, [])
    payload = {name: result.to_dict() for name, result in cases.items()}
    findings = tuple((f"world:{name}", result.findings) for name, result in cases.items())
    return payload, findings


def run_diagnostic_suite(
    specs: list[RunSpec], *, output_dir: str | Path, workers: int = 10,
    include_world: bool = True,
) -> dict[str, Any]:
    """Run independent economies across at most ten CPU processes and aggregate findings."""

    _validate_suite_specs(specs)
    output_dir = Path(output_dir)
    if output_dir.exists():
        if not output_dir.is_dir():
            raise FileExistsError(f"diagnostic output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise FileExistsError(
                f"diagnostic output directory is not empty: {output_dir}; use a new directory"
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(10, workers, len(specs)))
    started = perf_counter()
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    # Capture provenance before workers import and execute the model.  Re-reading at
    # completion lets the report explicitly invalidate a run whose source changed
    # while a long diagnostic was in flight.
    git = _git_provenance()
    dependency_lock_sha256 = _file_sha256("uv.lock")
    pyproject_sha256 = _file_sha256("pyproject.toml")
    outcomes: list[RunOutcome] = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as executor:
        futures = {executor.submit(_run_one, spec, str(output_dir)): spec for spec in specs}
        for future in as_completed(futures):
            outcome = future.result()
            outcomes.append(outcome)
            status = "FAILED" if outcome.error else "done"
            print(f"[{status:6s}] {outcome.spec.name}: {outcome.elapsed_seconds:.1f}s", flush=True)
    outcomes.sort(key=lambda item: item.spec.name)
    static_findings = run_static_audit()
    responses = _paired_responses(outcomes)
    ablation_attribution = _ablation_attribution(outcomes)
    world_payload: dict[str, Any] = {}
    world_findings: tuple[tuple[str, tuple[Finding, ...]], ...] = ()
    if include_world:
        world_payload, world_findings = _run_world_probe_suite()
        _write_json(output_dir / "world_diagnostics.json", world_payload)
    if ablation_attribution:
        _write_json(output_dir / "ablation_attribution.json", ablation_attribution)
    issues = _aggregate_issues(outcomes, static_findings, responses, world_findings)
    git_at_completion = _git_provenance()
    source_changed_during_run = (
        git.get("revision"), git.get("source_diff_sha256")
    ) != (
        git_at_completion.get("revision"), git_at_completion.get("source_diff_sha256")
    )
    if source_changed_during_run:
        issues.append({
            "issue_id": "validity.source_changed_during_run",
            "severity": "critical",
            "confidence": "confirmed",
            "category": "validity",
            "claim": "The source tree changed while diagnostic workers were executing.",
            "evidence": {"git_at_start": git, "git_at_completion": git_at_completion},
            "suspected_mechanisms": ["concurrent edit or branch update"],
            "requested_probes": [],
            "recommendation": "Discard this run and rerun against an unchanged source snapshot.",
            "measurement_status": "invalid_run",
            "detector": "source_snapshot_gate",
            "affected_runs": [outcome.spec.name for outcome in outcomes],
            "evidence_samples": [{"git_at_start": git, "git_at_completion": git_at_completion}],
        })
        issues.sort(key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["issue_id"]))
    manifest = {
        "schema_version": 1,
        "created": created,
        "git_revision": git["revision"],
        "git": git,
        "git_at_completion": git_at_completion,
        "source_changed_during_run": source_changed_during_run,
        "reproducibility_valid": not source_changed_during_run,
        "runtime": {
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "orchestrator_pythonhashseed_environment_at_import": _ORCHESTRATOR_HASHSEED_ENV_AT_IMPORT,
            "spawned_worker_pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "thread_limits": {
                key: os.environ.get(key)
                for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
            },
        },
        "dependency_lock_sha256": dependency_lock_sha256,
        "pyproject_sha256": pyproject_sha256,
        "jobs": len(specs),
        "executed_without_error": sum(outcome.error is None for outcome in outcomes),
        "successful": sum(_diagnostic_run_valid(outcome) for outcome in outcomes),
        "workers": workers,
        "world_diagnostics": include_world,
        "elapsed_seconds": perf_counter() - started,
        "clock": {"tick": "calendar_day", "ticks_per_year": 365},
        "metric_caveats": [
            "frontier macro diagnosis uses cpi_fixed_basket and nominal_gdp/real_gdp",
            "legacy price_index remains a composition-sensitive C-sector unit value",
            "legacy nominal_output remains a C-sector pseudo-GDP compatibility field",
            "fixed-basket CPI currently excludes separately journaled VAT/excise",
            "Economy-local external trade journals put observed nominal and real X/M/NX into expenditure GDP; the modeled external product perimeter currently covers consumption goods",
            "legacy income residual and raw three-approach spread are cash-to-production bridges; scope diagnosis uses only the income residual left after the sector output-sales accrual bridge",
            "producer energy-cap compensation is an additive product-subsidy correction; household energy rebates remain transfers, and the compatibility nominal_gdp path is unchanged",
            "productive JG public works are reported only in observation-only expanded candidates; zero-productivity JG payments remain income-floor transfers",
            "empirical leverage diagnosis uses trailing-365-day nominal GDP after a full year and an explicitly labelled annualised daily run-rate before then",
            "legacy credit_to_gdp remains a compatibility field with units of model-days",
            "Firm.profit is net income when firm_full_pnl is enabled and the legacy EBITDA-like field otherwise",
        ],
        "specs": [spec.to_dict() for spec in specs],
    }
    payload = {
        "manifest": manifest,
        "issues": issues,
        "paired_responses": responses,
        "ablation_attribution": ablation_attribution,
        "runs": [outcome.to_dict() for outcome in outcomes],
        "world": world_payload,
    }
    _write_json(output_dir / "diagnostics.json", payload)
    _write_json(output_dir / "manifest.json", manifest)
    _write_report(output_dir / "REPORT.md", payload)
    return payload
