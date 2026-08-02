"""Fractional-factorial interaction screens for immutable Config packages.

The simulated observations are owned by the native C++ engine.  This module
only constructs balanced treatment designs, resumes cached native runs, and
reduces each independent seed to main-effect and two-factor contrasts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.diagnostics.config_experiment import (
    DEFAULT_POPULATION,
    DEFAULT_WORKERS,
    apply_native_activation_scenario,
    native_joint_treatment_spec,
    native_joint_world_treatment_spec,
    paired_effect,
    population_scaled_new_game,
    run_native_spec_case,
)


@dataclass(frozen=True, slots=True)
class FactorSpec:
    field: str
    low: Any
    high: Any


@dataclass(frozen=True, slots=True)
class OutcomeSpec:
    metric_id: str
    statistic: str
    reducer: str = "player"


@dataclass(frozen=True, slots=True)
class CombinationPackage:
    package_id: str
    title: str
    scope: str
    activation_scenario: str
    days: int
    countries: int
    factors: tuple[FactorSpec, ...]
    outcomes: tuple[OutcomeSpec, ...]


@dataclass(frozen=True, slots=True)
class DesignArm:
    arm_id: str
    signs: tuple[int, ...]
    treatments: Mapping[str, Any]


# Four independent columns and three length-three generators produce a regular
# resolution-IV 2^(7-3) design. Main effects are orthogonal to every two-factor
# interaction; two-factor interactions are reported with their alias groups.
_COLUMN_MASKS = (0b0001, 0b0010, 0b0100, 0b1000, 0b0111, 0b1011, 0b1101)


def fractional_factorial_design(
    factors: Sequence[FactorSpec],
) -> tuple[DesignArm, ...]:
    """Return a balanced full or regular resolution-IV two-level design."""
    if not 1 <= len(factors) <= len(_COLUMN_MASKS):
        raise ValueError("combination packages require 1..7 factors")
    if len({factor.field for factor in factors}) != len(factors):
        raise ValueError("combination package factor names must be unique")
    base_width = min(4, len(factors))
    arms: list[DesignArm] = []
    for base_signs in itertools.product((-1, 1), repeat=base_width):
        signs: list[int] = []
        for mask in _COLUMN_MASKS[: len(factors)]:
            sign = 1
            for index in range(base_width):
                if mask & (1 << index):
                    sign *= base_signs[index]
            signs.append(sign)
        treatments = {
            factor.field: factor.high if sign > 0 else factor.low
            for factor, sign in zip(factors, signs, strict=True)
        }
        bits = "".join("h" if sign > 0 else "l" for sign in signs)
        arms.append(DesignArm(f"arm-{bits}", tuple(signs), treatments))
    return tuple(arms)


def interaction_alias_groups(
    factors: Sequence[FactorSpec],
) -> dict[str, tuple[str, ...]]:
    """Return the two-factor aliases induced by the regular design."""
    if len(factors) > len(_COLUMN_MASKS):
        raise ValueError("too many factors")
    grouped: dict[int, list[str]] = {}
    for left, right in itertools.combinations(range(len(factors)), 2):
        mask = _COLUMN_MASKS[left] ^ _COLUMN_MASKS[right]
        grouped.setdefault(mask, []).append(
            f"{factors[left].field}:{factors[right].field}"
        )
    return {
        name: tuple(grouped[_COLUMN_MASKS[left] ^ _COLUMN_MASKS[right]])
        for left, right in itertools.combinations(range(len(factors)), 2)
        for name in (f"{factors[left].field}:{factors[right].field}",)
    }


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=True, allow_nan=False, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _run_or_load(
    *,
    path: Path,
    signature_payload: Mapping[str, Any],
    native_spec: Any,
    days: int,
    workers: int,
    burn_in_days: int,
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature = _canonical_hash(signature_payload)
    if resume and path.is_file():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True
    result = run_native_spec_case(
        native_spec,
        days=days,
        workers=workers,
        burn_in_days=burn_in_days,
    )
    _atomic_json(path, {"run_signature": signature, "result": result})
    return result, False


def _outcome_value(result: Mapping[str, Any], outcome: OutcomeSpec) -> float:
    by_economy = result["metric_summaries_by_economy"]
    values = [
        float(by_economy[str(index)][outcome.metric_id][outcome.statistic])
        for index in range(len(by_economy))
    ]
    if outcome.reducer == "player":
        return values[int(result["economy_id"])]
    if outcome.reducer == "world_sum":
        return sum(values)
    if outcome.reducer == "world_mean":
        return fmean(values)
    raise ValueError(f"unknown outcome reducer {outcome.reducer!r}")


def _effect_summary(values: Sequence[float]) -> dict[str, Any]:
    return asdict(paired_effect([0.0] * len(values), values))


def _reduce_design(
    package: CombinationPackage,
    arms: Sequence[DesignArm],
    arm_results: Mapping[int, Sequence[Mapping[str, Any]]],
    reference_results: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    aliases = interaction_alias_groups(package.factors)
    main: dict[str, dict[str, Any]] = {}
    interactions: dict[str, dict[str, Any]] = {}
    reference_deviation: dict[str, dict[str, Any]] = {}
    for outcome in package.outcomes:
        outcome_id = (
            f"{outcome.metric_id}|{outcome.statistic}|{outcome.reducer}"
        )
        per_seed: dict[int, list[float]] = {
            seed: [_outcome_value(result, outcome) for result in results]
            for seed, results in arm_results.items()
        }
        grand_means = {
            seed: fmean(values) for seed, values in per_seed.items()
        }
        reference_deltas = [
            grand_means[seed] - _outcome_value(reference_results[seed], outcome)
            for seed in sorted(per_seed)
        ]
        reference_deviation[outcome_id] = _effect_summary(reference_deltas)
        for factor_index, factor in enumerate(package.factors):
            estimates = [
                2.0
                * fmean(
                    arm.signs[factor_index] * value
                    for arm, value in zip(arms, per_seed[seed], strict=True)
                )
                for seed in sorted(per_seed)
            ]
            relative = [
                estimate / abs(grand_means[seed])
                for seed, estimate in zip(sorted(per_seed), estimates, strict=True)
                if abs(grand_means[seed]) > 1.0e-12
            ]
            main.setdefault(factor.field, {})[outcome_id] = {
                **_effect_summary(estimates),
                "mean_relative_to_design_grand_mean": (
                    fmean(relative) if relative else None
                ),
            }
        for left, right in itertools.combinations(range(len(package.factors)), 2):
            interaction_id = (
                f"{package.factors[left].field}:"
                f"{package.factors[right].field}"
            )
            estimates = [
                4.0
                * fmean(
                    arm.signs[left] * arm.signs[right] * value
                    for arm, value in zip(arms, per_seed[seed], strict=True)
                )
                for seed in sorted(per_seed)
            ]
            relative = [
                estimate / abs(grand_means[seed])
                for seed, estimate in zip(sorted(per_seed), estimates, strict=True)
                if abs(grand_means[seed]) > 1.0e-12
            ]
            interactions.setdefault(interaction_id, {})[outcome_id] = {
                **_effect_summary(estimates),
                "mean_relative_to_design_grand_mean": (
                    fmean(relative) if relative else None
                ),
                "alias_group": aliases[interaction_id],
            }
    return {
        "main_effects": main,
        "two_factor_interactions": interactions,
        "design_center_minus_product_reference": reference_deviation,
    }


def run_combination_package(
    package: CombinationPackage,
    *,
    seeds: Iterable[int],
    artifact_dir: Path,
    source_revision: str,
    population: int = DEFAULT_POPULATION,
    workers: int = DEFAULT_WORKERS,
    burn_in_days: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Run and reduce one resumable native fractional-factorial package."""
    if package.scope not in {"root", "world"}:
        raise ValueError("combination package scope must be root or world")
    if population < 100_000:
        raise ValueError("Config combination screens require 100,000+ persons")
    seed_values = tuple(seeds)
    if len(seed_values) < 2 or len(set(seed_values)) != len(seed_values):
        raise ValueError("combination screens require distinct paired seeds")
    arms = fractional_factorial_design(package.factors)
    resolved_burn_in = (
        min(90, max(1, package.days // 4), package.days - 1)
        if burn_in_days is None
        else burn_in_days
    )
    arm_results: dict[int, list[dict[str, Any]]] = {}
    reference_results: dict[int, dict[str, Any]] = {}
    cache_hits = 0
    executed_runs = 0
    signature_base = {
        "schema_version": "config-combination-run-v1",
        "package": asdict(package),
        "source_revision": source_revision,
        "population_per_country": population,
        "workers": workers,
        "burn_in_days": resolved_burn_in,
    }
    for seed in seed_values:
        baseline = population_scaled_new_game(
            population=population,
            days=package.days,
            seed=seed,
            countries=package.countries,
        )
        reference_spec = native_backend.build_native_new_game_spec(baseline)
        apply_native_activation_scenario(
            reference_spec, scenario=package.activation_scenario
        )
        reference, cached = _run_or_load(
            path=artifact_dir / "runs" / str(seed) / "reference.json",
            signature_payload={**signature_base, "seed": seed, "arm": "reference"},
            native_spec=reference_spec,
            days=package.days,
            workers=workers,
            burn_in_days=resolved_burn_in,
            resume=resume,
        )
        reference_results[seed] = reference
        cache_hits += int(cached)
        executed_runs += int(not cached)
        seed_results: list[dict[str, Any]] = []
        for arm in arms:
            native_spec = (
                native_joint_world_treatment_spec(
                    baseline, treatments=arm.treatments
                )
                if package.scope == "world"
                else native_joint_treatment_spec(
                    baseline, treatments=arm.treatments
                )
            )
            apply_native_activation_scenario(
                native_spec, scenario=package.activation_scenario
            )
            result, cached = _run_or_load(
                path=artifact_dir / "runs" / str(seed) / f"{arm.arm_id}.json",
                signature_payload={
                    **signature_base,
                    "seed": seed,
                    "arm": arm.arm_id,
                    "treatments": dict(arm.treatments),
                },
                native_spec=native_spec,
                days=package.days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                resume=resume,
            )
            seed_results.append(result)
            cache_hits += int(cached)
            executed_runs += int(not cached)
        arm_results[seed] = seed_results
    payload = {
        "schema_version": "config-combination-report-v1",
        "source_revision": source_revision,
        "package": asdict(package),
        "population_per_country": population,
        "workers": workers,
        "seeds": list(seed_values),
        "burn_in_days": resolved_burn_in,
        "design": [asdict(arm) for arm in arms],
        "design_resolution": "IV" if len(package.factors) > 4 else "full",
        "cache_hits": cache_hits,
        "executed_runs": executed_runs,
        **_reduce_design(package, arms, arm_results, reference_results),
    }
    _atomic_json(artifact_dir / "combination_report.json", payload)
    return payload


def _outcome(metric_id: str, statistic: str, reducer: str = "player") -> OutcomeSpec:
    return OutcomeSpec(metric_id, statistic, reducer)


COMBINATION_PACKAGES: Mapping[str, CombinationPackage] = {
    "productive_capacity": CombinationPackage(
        "productive_capacity", "Productive capacity", "root",
        "positive_capital_gap", 365, 1,
        (
            FactorSpec("A", 0.1362705873, 0.2044058809),
            FactorSpec("alpha", 0.25, 0.35),
            FactorSpec("delta_K", 0.0001824, 0.0002736),
            FactorSpec("lambda_I", 0.00152, 0.00228),
            FactorSpec("tfp_drift_rate", 0.006, 0.024),
            FactorSpec("v", 730.0, 1095.0),
        ),
        (
            _outcome("metric.economy.na.real_gdp_per_capita", "post_burnin_mean"),
            _outcome("metric.source.m4.fixed_capital_formation_real", "cumulative"),
            _outcome("metric.source.m4.aggregate_capital", "last_window_mean"),
            _outcome("metric.economy.unemployment_rate", "post_burnin_mean"),
            _outcome("metric.economy.price_index", "post_burnin_mean"),
        ),
    ),
    "labor_institutions": CombinationPackage(
        "labor_institutions", "Labor institutions", "root",
        "neutral_baseline", 365, 1,
        (
            FactorSpec("labor_matching_friction", False, True),
            FactorSpec("job_search_intensity", 0.075, 0.30),
            FactorSpec("reservation_markup", 0.5, 2.5),
            FactorSpec("theta_wage", 0.0055, 0.022),
            FactorSpec("lambda_fire", 0.015, 0.060),
            FactorSpec("ladder_premium", 0.0, 0.10),
            FactorSpec("suspension_timer", 1, 90),
        ),
        (
            _outcome("metric.source.m7.participation_rate", "post_burnin_mean"),
            _outcome("metric.source.m7.employed_fte", "post_burnin_mean"),
            _outcome("metric.source.m7.vacancies", "post_burnin_mean"),
            _outcome("metric.source.m7.hires", "cumulative"),
            _outcome("metric.source.m7.separations", "cumulative"),
            _outcome("metric.source.m7.mean_hourly_wage", "post_burnin_mean"),
            _outcome("metric.economy.unemployment_rate", "post_burnin_mean"),
        ),
    ),
    "credit_architecture": CombinationPackage(
        "credit_architecture", "Credit architecture", "root",
        "credit_joint_pressure", 365, 1,
        (
            FactorSpec("bank_rate_competition", False, True),
            FactorSpec("bank_leverage_disp", 0.0, 1.0),
            FactorSpec("bank_relationship_lock_in", False, True),
            FactorSpec("amort", 0.000547945205479452, 0.002191780821917808),
            FactorSpec("interbank", False, True),
            FactorSpec("household_credit", False, True),
            FactorSpec("run_sensitivity", 0.5, 16.0),
        ),
        (
            _outcome("metric.source.m5.new_credit", "cumulative"),
            _outcome("metric.source.m5.total_loan_principal", "last_window_mean"),
            _outcome("metric.source.m5.total_bank_capital", "last_window_mean"),
            _outcome("metric.source.m5.interbank_volume", "cumulative"),
            _outcome("metric.source.m5.run_flight_volume", "cumulative"),
            _outcome("metric.source.m5.bank_failures", "cumulative"),
            _outcome("metric.economy.real_output", "post_burnin_mean"),
        ),
    ),
    "housing_family": CombinationPackage(
        "housing_family", "Housing and family formation", "root",
        "housing_joint_pressure", 730, 1,
        (
            FactorSpec("builder_productivity", 0.001, 0.008),
            FactorSpec("builder_demand_price_gain", 0.5, 2.0),
            FactorSpec("housing_ask_decay", 0.001, 0.05),
            FactorSpec("mortgage_enabled", False, True),
            FactorSpec("rent_adjust", 0.0, 0.20),
            FactorSpec("housing_leave_elasticity", 0.0, 3.0),
            FactorSpec("housing_fertility_elasticity", 0.0, 2.0),
        ),
        (
            _outcome("metric.source.m8.housing.construction_output", "cumulative"),
            _outcome("metric.source.m8.housing.housing_stock", "last_window_mean"),
            _outcome("metric.source.m8.housing.house_price", "post_burnin_mean"),
            _outcome("metric.source.m8.housing.mortgage_originations", "cumulative"),
            _outcome("metric.source.m8.housing.rent_paid", "cumulative"),
            _outcome("metric.source.m8.housing.leave_home_multiplier", "last_window_mean"),
            _outcome("metric.source.m8.housing.fertility_multiplier", "last_window_mean"),
        ),
    ),
    "energy_dependence": CombinationPackage(
        "energy_dependence", "Energy dependence", "root",
        "energy_joint_pressure", 730, 1,
        (
            FactorSpec("energy_util0", 0.55, 1.0),
            FactorSpec("energy_hh_share", 0.03, 0.14),
            FactorSpec("energy_intensity", 0.01, 0.12),
            FactorSpec("energy_coverage_ticks", 3.0, 30.0),
            FactorSpec("energy_hoarding_beta", 0.0, 5.0),
            FactorSpec("energy_mortality_gamma", 0.0, 4.0),
        ),
        (
            _outcome("metric.source.m8.energy.production", "cumulative"),
            _outcome("metric.source.m8.energy.unfilled", "cumulative"),
            _outcome("metric.source.m8.energy.requested_households", "cumulative"),
            _outcome("metric.source.m8.energy.requested_industry", "cumulative"),
            _outcome("metric.source.m8.energy.transaction_price", "post_burnin_mean"),
            _outcome("metric.source.m8.energy.fuel_poverty_share", "post_burnin_mean"),
            _outcome("metric.source.m7.deaths", "cumulative"),
        ),
    ),
    "firm_dynamism": CombinationPackage(
        "firm_dynamism", "Firm dynamism", "root",
        "firm_joint_dynamism", 365, 1,
        (
            FactorSpec("entry_hurdle", 0.0, 0.000268),
            FactorSpec("entry_beta", 0.2, 0.6),
            FactorSpec("subscale_exit_hazard", 0.005555555555555556, 0.022222222222222223),
            FactorSpec("subscale_grace_days", 90, 365),
            FactorSpec("sector_switching", False, True),
            FactorSpec("switch_retool_loss", 0.0, 0.15),
        ),
        (
            _outcome("metric.source.m6.firm_births", "cumulative"),
            _outcome("metric.source.m6.firm_exits", "cumulative"),
            _outcome("metric.source.m6.sector_switches", "cumulative"),
            _outcome("metric.source.m6.sector_retool_capital", "cumulative"),
            _outcome("metric.source.m4.firm_profit", "cumulative"),
            _outcome("metric.economy.real_output", "post_burnin_mean"),
            _outcome("metric.economy.unemployment_rate", "post_burnin_mean"),
        ),
    ),
    "open_economy": CombinationPackage(
        "open_economy", "Open economy", "world",
        "world_joint_integration", 365, 3,
        (
            FactorSpec("fx_trade_cap", 0.03, 0.30),
            FactorSpec("fx_lambda", 0.01, 0.20),
            FactorSpec("fx_friction", 0.0, 0.15),
            FactorSpec("capital_mobility", 0.20, 0.80),
            FactorSpec("migration_rate", 0.0001, 0.005),
            FactorSpec("remittance_share", 0.05, 0.50),
            FactorSpec("wage_smoothing", 0.005, 0.20),
        ),
        (
            _outcome("metric.source.m9.country.imports_volume", "cumulative", "world_sum"),
            _outcome("metric.source.m9.country.iceberg_loss", "cumulative", "world_sum"),
            _outcome("metric.source.m9.country.capital_flow", "cumulative"),
            _outcome("metric.source.m9.country.migrant_stock_hosted", "last_window_mean", "world_sum"),
            _outcome("metric.source.m9.country.remittances_sent", "cumulative", "world_sum"),
            _outcome("metric.source.m9.country.exchange_rate", "post_burnin_volatility"),
            _outcome("metric.economy.real_output", "post_burnin_mean", "world_mean"),
        ),
    ),
}

