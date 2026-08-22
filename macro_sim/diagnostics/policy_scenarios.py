"""Native scenario validation for Policy causality audit milestone P3.

P3 freezes policy-independent ordinary, structural, and crisis environments.
The crisis controls are built from a common native pre-crisis checkpoint, then
branched into mild, moderate, and severe immutable shock tapes.  No Policy
treatment is applied here and the legacy Python simulator is never executed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    derive_analysis_metrics,
    native_joint_treatment_spec,
    population_scaled_new_game,
)
from macro_sim.diagnostics.policy_catalog import (
    ORDINARY_SCENARIOS,
    SCENARIOS,
    STRUCTURAL_SCENARIOS,
)
from macro_sim.diagnostics.policy_contracts import build_p0_payload
from macro_sim.native_backend import NativeSimulationSession


P3_SCHEMA_VERSION = "policy-causality-p3-v1"
DEFAULT_P3_SEEDS = (5_101, 5_113, 5_129, 5_143, 5_159, 5_177, 5_193, 5_209)
SEVERITIES = ("mild", "moderate", "severe")
SEVERITY_SCALE: Mapping[str, float] = {
    "mild": 0.50,
    "moderate": 1.00,
    "severe": 1.50,
}


@dataclass(frozen=True, slots=True)
class StateCriterion:
    metric_id: str
    minimum: float | None = None
    maximum: float | None = None
    absolute: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StateManifest:
    scenario_id: str
    description: str
    scenario_class: str
    countries: int
    horizon_days: int
    activation_scenario: str
    criteria: tuple[StateCriterion, ...]
    config_treatments: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ShockLeg:
    kind: str
    magnitude: float
    duration_days: int
    ramp_out_days: int = 0
    sector: str | None = None
    economy_id: int | None = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdverseRule:
    metric_id: str
    direction: str
    absolute_floor: float
    relative_floor: float = 0.0
    statistic: str = "mean"
    persistence_days: int = 3

    def __post_init__(self) -> None:
        if self.direction not in {"increase", "decrease"}:
            raise ValueError(f"invalid adverse direction {self.direction!r}")
        if self.statistic not in {"mean", "peak", "cumulative"}:
            raise ValueError(f"invalid adverse statistic {self.statistic!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CrisisManifest:
    scenario_id: str
    description: str
    readiness: str
    countries: int
    burn_in_days: int
    recovery_days: int
    activation_scenario: str
    shock_legs: tuple[ShockLeg, ...]
    entry_rules: tuple[AdverseRule, ...]
    propagation_rules: tuple[AdverseRule, ...]
    primary_damage: AdverseRule
    recovery_mode: str
    caveat: str = ""

    def __post_init__(self) -> None:
        if self.recovery_mode not in {"recover", "recover_or_new_regime", "new_regime"}:
            raise ValueError(
                f"{self.scenario_id}: invalid recovery mode {self.recovery_mode!r}"
            )

    @property
    def maximum_shock_days(self) -> int:
        return max(
            (leg.duration_days + leg.ramp_out_days for leg in self.shock_legs),
            default=0,
        )

    @property
    def horizon_days(self) -> int:
        return self.maximum_shock_days + self.recovery_days

    @property
    def metric_ids(self) -> tuple[str, ...]:
        output = {
            self.primary_damage.metric_id,
            "metric.shock.active_count",
            "metric.source.m4.conservation_drift",
            "metric.source.m6.clearing_residual",
            "metric.economy.na.production_reconciliation_residual",
        }
        output.update(rule.metric_id for rule in self.entry_rules)
        output.update(rule.metric_id for rule in self.propagation_rules)
        output.update(
            f"metric.shock.severity.{leg.kind}" for leg in self.shock_legs
        )
        return tuple(sorted(output))

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["horizon_days"] = self.horizon_days
        return output


def _state(
    scenario_id: str,
    description: str,
    scenario_class: str,
    activation: str,
    criteria: tuple[StateCriterion, ...],
    *,
    countries: int = 1,
    horizon_days: int = 90,
    config_treatments: tuple[tuple[str, Any], ...] = (),
) -> StateManifest:
    return StateManifest(
        scenario_id,
        description,
        scenario_class,
        countries,
        horizon_days,
        activation,
        criteria,
        config_treatments,
    )


STATE_MANIFESTS: Mapping[str, StateManifest] = {
    item.scenario_id: item
    for item in (
        _state(
            "BASE_NORMAL",
            "The current playable baseline without a shock or policy response.",
            "ordinary",
            "neutral_baseline",
            (
                StateCriterion("metric.economy.unemployment_rate", 0.0, 0.15),
                StateCriterion("metric.economy.real_output", 1.0, None),
            ),
        ),
        _state(
            "BASE_SLACK",
            "A reproducible ordinary state with idle labor and weak demand.",
            "ordinary",
            "labor_demand_contraction",
            (StateCriterion("metric.economy.unemployment_rate", 0.08, None),),
        ),
        _state(
            "BASE_TIGHT",
            "A reproducible ordinary state with a tight labor market.",
            "ordinary",
            "opening_consumption_stockout",
            (StateCriterion("metric.economy.unemployment_rate", 0.0, 0.05),),
        ),
        _state(
            "STRUCT_HIGH_POVERTY",
            "Persistent material deprivation without an acute external shock.",
            "structural",
            "energy_mortality_pressure",
            (StateCriterion("metric.economy.poverty_rate", 0.15, None),),
            horizon_days=180,
            config_treatments=(("d_household0", 0.25),),
        ),
        _state(
            "STRUCT_HIGH_INEQUALITY",
            "A high-dispersion income and wealth distribution.",
            "structural",
            "wealth_dispersion",
            (
                StateCriterion("metric.economy.income_gini", 0.35, None),
                StateCriterion("metric.economy.hh_wealth_gini", 0.50, None),
            ),
        ),
        _state(
            "STRUCT_LOW_PARTICIPATION",
            "Reservation and welfare-exit margins reduce labor participation.",
            "structural",
            "binding_labor_reservation",
            (StateCriterion("metric.source.m7.participation_rate", 0.0, 0.72),),
            config_treatments=(
                ("labor_participation", True),
                ("reservation_markup", 2.5),
                ("welfare_quit_hazard", 0.50),
            ),
        ),
        _state(
            "STRUCT_HOUSING_SHORTAGE",
            "The dwelling stock is insufficient relative to households.",
            "structural",
            "housing_shortage",
            (StateCriterion("metric.source.m8.housing.vacancy_share", 0.0, 0.02),),
        ),
        _state(
            "STRUCT_LOW_PRODUCTIVITY",
            "Low labor productivity depresses output per living person.",
            "structural",
            "neutral_baseline",
            (StateCriterion("metric.analysis.real_output_per_person", 0.0, 0.60),),
            config_treatments=(("a", 0.60), ("a_K", 1.44), ("a_E", 0.60)),
        ),
        _state(
            "STRUCT_ENERGY_DEPENDENCE",
            "Low energy productivity and high needs expose the economy to energy costs.",
            "structural",
            "energy_joint_pressure",
            (StateCriterion("metric.economy.energy_cost_share", 0.03, None),),
            config_treatments=(("energy_hh_share", 0.15), ("a_E", 0.50)),
        ),
        _state(
            "STRUCT_POPULATION_AGING",
            "A high dependency burden creates a long-run demographic state.",
            "structural",
            "neutral_baseline",
            (StateCriterion("metric.source.m7.dependency_ratio", 0.65, None),),
            config_treatments=(
                ("TFR", 1.20),
                ("demographics_mortality_scale", 0.75),
            ),
        ),
        _state(
            "STRUCT_EXTERNAL_IMBALANCE",
            "Persistent price and inventory differences create an external imbalance.",
            "structural",
            "world_trade_friction",
            (StateCriterion("metric.world.current_account", 0.01, None, True),),
            countries=3,
        ),
    )
}


def _rule(
    metric_id: str,
    direction: str,
    absolute_floor: float,
    relative_floor: float = 0.0,
    statistic: str = "peak",
    persistence_days: int = 3,
) -> AdverseRule:
    return AdverseRule(
        metric_id,
        direction,
        absolute_floor,
        relative_floor,
        statistic,
        persistence_days,
    )


def _crisis(
    scenario_id: str,
    *,
    countries: int = 1,
    burn_in: int = 30,
    recovery: int = 60,
    activation: str = "neutral_baseline",
    legs: tuple[ShockLeg, ...],
    entry: tuple[AdverseRule, ...],
    propagation: tuple[AdverseRule, ...],
    primary: AdverseRule,
    recovery_mode: str = "recover",
) -> CrisisManifest:
    catalog = SCENARIOS[scenario_id]
    return CrisisManifest(
        scenario_id,
        catalog.description,
        catalog.readiness,
        countries,
        burn_in,
        recovery,
        activation,
        legs,
        entry,
        propagation,
        primary,
        recovery_mode,
        catalog.caveat,
    )


CRISIS_MANIFESTS: Mapping[str, CrisisManifest] = {
    item.scenario_id: item
    for item in (
        _crisis(
            "CR_DEMAND_RECESSION",
            legs=(ShockLeg("household_demand", 0.24, 60, 30),),
            entry=(
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
            ),
            propagation=(
                _rule("metric.source.m4.household_consumption", "decrease", 1.0, 0.01),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
                _rule("metric.economy.poverty_rate", "increase", 0.002),
            ),
            primary=_rule("metric.economy.real_output", "decrease", 1.0, 0.01),
        ),
        _crisis(
            "CR_SUPPLY_STAGFLATION",
            legs=(
                ShockLeg("productivity", 0.15, 60, 30),
                ShockLeg("energy_capacity", 0.30, 60, 30, "energy"),
            ),
            entry=(
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
                _rule("metric.economy.inflation", "increase", 1.0e-5),
            ),
            propagation=(
                _rule("metric.source.m8.energy.unfilled", "increase", 1.0),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
                _rule("metric.economy.inflation", "increase", 1.0e-5),
            ),
            primary=_rule("metric.economy.real_output", "decrease", 1.0, 0.01),
        ),
        _crisis(
            "CR_ENERGY_EMBARGO",
            countries=3,
            legs=(
                ShockLeg("energy_capacity", 0.45, 90, 30, "energy"),
                ShockLeg("import_capacity", 0.25, 90, 30),
            ),
            entry=(
                _rule("metric.source.m8.energy.unfilled", "increase", 1.0),
                _rule("metric.source.m8.energy.transaction_price", "increase", 1.0e-4, 0.01),
            ),
            propagation=(
                _rule("metric.source.m8.energy.fuel_poverty_share", "increase", 0.002),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
                _rule("metric.economy.inflation", "increase", 1.0e-5),
            ),
            primary=_rule("metric.source.m8.energy.unfilled", "increase", 1.0),
            activation="energy_inventory_gap",
        ),
        _crisis(
            "CR_CREDIT_CRUNCH",
            activation="credit_joint_pressure",
            legs=(
                ShockLeg("credit_supply", 0.70, 90, 30),
                ShockLeg("household_demand", 0.18, 90, 30),
                ShockLeg("productivity", 0.05, 90, 30),
            ),
            entry=(
                _rule("metric.source.m5.new_credit", "decrease", 1.0e-9, 0.05, "cumulative"),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
            ),
            propagation=(
                _rule("metric.source.m5.firm_investment_target", "decrease", 1.0e-9, 0.01),
                _rule("metric.source.m6.firm_defaults", "increase", 1.0, 0.0, "cumulative"),
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
            ),
            primary=_rule("metric.economy.real_output", "decrease", 1.0, 0.01),
            recovery_mode="recover_or_new_regime",
        ),
        _crisis(
            "CR_PANDEMIC",
            countries=3,
            recovery=90,
            legs=(
                ShockLeg("labor_availability", 0.25, 90, 60),
                ShockLeg("productivity", 0.12, 90, 60),
                ShockLeg("household_demand", 0.16, 90, 60),
                ShockLeg("credit_supply", 0.12, 90, 60),
                ShockLeg("import_capacity", 0.30, 90, 60),
                ShockLeg("export_capacity", 0.25, 90, 60),
            ),
            entry=(
                _rule("metric.economy.employment", "decrease", 1.0, 0.01),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
            ),
            propagation=(
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
                _rule("metric.economy.poverty_rate", "increase", 0.002),
                _rule("metric.source.m9.country.imports_volume", "decrease", 1.0e-6, 0.05),
            ),
            primary=_rule("metric.economy.real_output", "decrease", 1.0, 0.01),
            recovery_mode="recover_or_new_regime",
        ),
        _crisis(
            "CR_NATURAL_DISASTER",
            legs=(
                ShockLeg("capital_destruction", 0.10, 1),
                ShockLeg("productivity", 0.15, 90, 45),
                ShockLeg("labor_availability", 0.10, 30, 10),
            ),
            entry=(
                _rule("metric.source.m9.country.capital_destroyed", "increase", 1.0, 0.0, "cumulative", 1),
                _rule("metric.source.m4.aggregate_capital", "decrease", 1.0, 0.01),
            ),
            propagation=(
                _rule("metric.economy.real_output", "decrease", 1.0, 0.01),
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
            ),
            primary=_rule("metric.source.m4.aggregate_capital", "decrease", 1.0, 0.01),
            recovery_mode="new_regime",
        ),
        _crisis(
            "CR_TRADE_INTERRUPTION",
            countries=3,
            activation="world_trade_integration",
            legs=(
                ShockLeg("import_capacity", 0.50, 60, 30),
                ShockLeg("export_capacity", 0.50, 60, 30),
            ),
            entry=(
                _rule("metric.source.m9.country.imports_volume", "decrease", 1.0e-6, 0.05),
                _rule("metric.source.m9.country.exports_volume", "decrease", 1.0e-6, 0.05),
            ),
            propagation=(
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
                _rule("metric.world.current_account", "increase", 1.0e-4, 0.01),
                _rule("metric.economy.price_index", "increase", 1.0e-4, 0.005),
            ),
            primary=_rule("metric.source.m9.country.imports_volume", "decrease", 1.0e-6, 0.05),
        ),
        _crisis(
            "CR_PEG_PRESSURE",
            countries=3,
            activation="world_peg_pressure",
            legs=(
                ShockLeg("import_capacity", 0.50, 90, 30),
                ShockLeg("export_capacity", 0.20, 90, 30),
            ),
            entry=(
                _rule("metric.source.m9.country.peg_reserves", "decrease", 1.0, 0.01),
                _rule("metric.source.m9.country.exchange_rate", "increase", 1.0e-4, 0.001),
            ),
            propagation=(
                _rule("metric.world.current_account", "increase", 1.0e-4, 0.01),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
            ),
            primary=_rule("metric.source.m9.country.peg_reserves", "decrease", 1.0, 0.01),
            recovery_mode="recover_or_new_regime",
        ),
        _crisis(
            "CR_BANK_RUN",
            activation="bank_run_market_signal",
            legs=(
                ShockLeg("productivity", 0.10, 30, 15),
                ShockLeg("household_demand", 0.12, 30, 15),
            ),
            entry=(
                _rule("metric.source.m5.run_flight_volume", "increase", 1.0, 0.0, "cumulative"),
                _rule("metric.source.m5.lolr_advances", "increase", 1.0, 0.0, "cumulative"),
            ),
            propagation=(
                _rule("metric.source.m5.bank_failures", "increase", 1.0, 0.0, "cumulative"),
                _rule("metric.source.m5.new_credit", "decrease", 1.0e-9, 0.05, "cumulative"),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
            ),
            primary=_rule("metric.source.m5.run_flight_volume", "increase", 1.0, 0.0, "cumulative"),
            recovery_mode="recover_or_new_regime",
        ),
        _crisis(
            "CR_HOUSING_BUST",
            activation="housing_distressed_market",
            burn_in=90,
            recovery=90,
            legs=(
                ShockLeg("household_demand", 0.20, 90, 30),
                ShockLeg("credit_supply", 0.40, 90, 30),
                ShockLeg("productivity", 0.08, 90, 30),
            ),
            entry=(
                _rule("metric.source.m8.housing.house_price", "decrease", 1.0e-4, 0.01),
                _rule("metric.source.m8.housing.foreclosures", "increase", 1.0, 0.0, "cumulative"),
            ),
            propagation=(
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
                _rule("metric.economy.unemployment_rate", "increase", 0.005),
            ),
            primary=_rule("metric.source.m8.housing.house_price", "decrease", 1.0e-4, 0.01),
            recovery_mode="recover_or_new_regime",
        ),
        _crisis(
            "CR_SOVEREIGN_STRESS",
            legs=(),
            entry=(
                _rule("metric.source.m6.bond_issuance", "increase", 1.0),
                _rule("metric.economy.gov_debt_to_gdp", "increase", 0.01),
            ),
            propagation=(
                _rule("metric.source.m6.bond_market_value", "decrease", 1.0, 0.01),
                _rule("metric.source.m5.total_bank_capital", "decrease", 1.0, 0.01),
                _rule("metric.economy.real_output", "decrease", 1.0, 0.005),
            ),
            primary=_rule("metric.source.m6.bond_market_value", "decrease", 1.0, 0.01),
            recovery_mode="new_regime",
        ),
    )
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(_jsonable(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _history_rows_after(
    session: NativeSimulationSession,
    *,
    economy_id: int,
    first_tick_exclusive: int,
    last_tick_inclusive: int,
) -> list[dict[str, Any]]:
    bounds = session.history_bounds()
    cursor = int(bounds["oldest_sequence"])
    stop = int(bounds["next_sequence"])
    rows: list[dict[str, Any]] = []
    while cursor < stop:
        page = session.maintained_history_page(cursor, min(512, stop - cursor))
        for frame in page["frames"]:
            tick = int(frame["tick"])
            if first_tick_exclusive < tick <= last_tick_inclusive:
                row = derive_analysis_metrics(frame["economies"][economy_id])
                population = float(row.get("metric.economy.population_alive", 0.0))
                output = float(row.get("metric.economy.real_output", 0.0))
                row["metric.analysis.real_output_per_person"] = (
                    output / population if population > 0.0 else 0.0
                )
                row["_tick"] = tick
                rows.append(row)
        next_cursor = int(page["next_sequence"])
        if next_cursor <= cursor:
            raise RuntimeError("native metric history cursor did not advance")
        cursor = next_cursor
    return rows


def _series(
    rows: Sequence[Mapping[str, Any]], metric_ids: Iterable[str]
) -> dict[str, list[float]]:
    output: dict[str, list[float]] = {}
    for metric_id in metric_ids:
        values = []
        for row in rows:
            value = row.get(metric_id)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                values = []
                break
            number = float(value)
            if not math.isfinite(number):
                raise RuntimeError(f"non-finite native metric {metric_id}: {value!r}")
            values.append(number)
        if values:
            output[metric_id] = values
    return output


def _state_native_spec(manifest: StateManifest, *, population: int, seed: int) -> Any:
    baseline = population_scaled_new_game(
        population=population,
        days=manifest.horizon_days + 2,
        seed=seed,
        countries=manifest.countries,
    )
    if manifest.config_treatments:
        native_spec = native_joint_treatment_spec(
            baseline,
            treatments=dict(manifest.config_treatments),
        )
    else:
        native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(
        native_spec,
        scenario=manifest.activation_scenario,
    )
    return native_spec


def _criterion_result(values: Sequence[float], criterion: StateCriterion) -> dict[str, Any]:
    terminal_window = values[-min(14, len(values)) :]
    observed = fmean(abs(value) for value in terminal_window) if criterion.absolute else fmean(terminal_window)
    passed = (
        (criterion.minimum is None or observed >= criterion.minimum)
        and (criterion.maximum is None or observed <= criterion.maximum)
    )
    return {
        **criterion.to_dict(),
        "observed": observed,
        "passed": passed,
    }


def _integrity(series: Mapping[str, Sequence[float]]) -> dict[str, Any]:
    missing = [
        metric_id
        for metric_id in (
            "metric.source.m4.conservation_drift",
            "metric.source.m6.clearing_residual",
            "metric.economy.na.production_reconciliation_residual",
        )
        if metric_id not in series
    ]
    finite = all(math.isfinite(value) for values in series.values() for value in values)
    limits = {
        "metric.source.m4.conservation_drift": 1.0e-4,
        "metric.source.m6.clearing_residual": 1.0e-5,
        "metric.economy.na.production_reconciliation_residual": 1.0e-6,
    }
    maxima = {
        metric_id: max((abs(value) for value in series.get(metric_id, ())), default=math.inf)
        for metric_id in limits
    }
    accounting = not missing and all(maxima[name] <= limit for name, limit in limits.items())
    return {
        "finite": finite,
        "missing_accounting_metrics": missing,
        "maximum_absolute_residuals": maxima,
        "accounting_passed": accounting,
        "passed": finite and accounting,
    }


def _run_state_seed(
    manifest: StateManifest,
    *,
    seed: int,
    population: int,
    workers: int,
    source_revision: str,
    cache_path: Path,
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature_payload = {
        "schema_version": P3_SCHEMA_VERSION,
        "source_revision": source_revision,
        "manifest": manifest.to_dict(),
        "population": population,
        "workers": workers,
        "seed": seed,
    }
    signature = _canonical_hash(signature_payload)
    if resume and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True
    started = time.perf_counter()
    session = NativeSimulationSession.create_from_native_spec(
        _state_native_spec(manifest, population=population, seed=seed),
        worker_count=workers,
        history_capacity_frames=manifest.horizon_days + 4,
    )
    session.advance(manifest.horizon_days)
    rows = _history_rows_after(
        session,
        economy_id=0,
        first_tick_exclusive=0,
        last_tick_inclusive=manifest.horizon_days,
    )
    metric_ids = {
        criterion.metric_id for criterion in manifest.criteria
    } | {
        "metric.source.m4.conservation_drift",
        "metric.source.m6.clearing_residual",
        "metric.economy.na.production_reconciliation_residual",
    }
    captured = _series(rows, metric_ids)
    missing = sorted(metric_ids - set(captured))
    criteria = [
        _criterion_result(captured[item.metric_id], item)
        for item in manifest.criteria
        if item.metric_id in captured
    ]
    integrity = _integrity(captured)
    result = {
        "scenario_id": manifest.scenario_id,
        "seed": seed,
        "criteria": criteria,
        "missing_metrics": missing,
        "integrity": integrity,
        "checkpoint_sha256": hashlib.sha256(session.checkpoint()).hexdigest(),
        "elapsed_seconds": time.perf_counter() - started,
        "memory_bytes": session.memory_usage(),
    }
    _atomic_json(cache_path, {
        "schema_version": "policy-p3-state-run-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result, False


def _native_shock(
    manifest: CrisisManifest,
    leg: ShockLeg,
    *,
    severity: str,
    start_tick: int,
    ordinal: int,
) -> Any:
    native = native_backend._load_native()
    kinds = {
        "productivity": native.ShockKind.PRODUCTIVITY,
        "labor_availability": native.ShockKind.LABOR_AVAILABILITY,
        "energy_capacity": native.ShockKind.ENERGY_CAPACITY,
        "household_demand": native.ShockKind.HOUSEHOLD_DEMAND,
        "import_capacity": native.ShockKind.IMPORT_CAPACITY,
        "export_capacity": native.ShockKind.EXPORT_CAPACITY,
        "credit_supply": native.ShockKind.CREDIT_SUPPLY,
        "capital_destruction": native.ShockKind.CAPITAL_DESTRUCTION,
    }
    sectors = {
        "consumption": native.ShockSector.CONSUMPTION,
        "capital": native.ShockSector.CAPITAL,
        "energy": native.ShockSector.ENERGY,
        "housing": native.ShockSector.HOUSING,
        "public": native.ShockSector.PUBLIC,
    }
    shock = native.ShockSpec()
    identity = f"{manifest.scenario_id}:{severity}:{ordinal}"
    shock.id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big") or 1
    shock.kind = kinds[leg.kind]
    shock.economy_id = leg.economy_id
    shock.start_tick = start_tick
    shock.announcement_tick = start_tick
    shock.duration = leg.duration_days
    shock.magnitude = min(0.95, leg.magnitude * SEVERITY_SCALE[severity])
    shock.shape = native.ShockShape.STEP
    shock.ramp_out_ticks = leg.ramp_out_days
    if leg.kind == "capital_destruction":
        shock.duration = 1
        shock.ramp_out_ticks = 0
    if leg.sector is not None:
        shock.sector = sectors[leg.sector]
    return shock


def _tape_payload(manifest: CrisisManifest, severity: str, start_tick: int) -> dict[str, Any]:
    return {
        "scenario_id": manifest.scenario_id,
        "severity": severity,
        "start_tick": start_tick,
        "legs": [
            {
                **leg.to_dict(),
                "magnitude": min(0.95, leg.magnitude * SEVERITY_SCALE[severity]),
            }
            for leg in manifest.shock_legs
        ],
    }


def _schedule_tape(
    branch: NativeSimulationSession,
    manifest: CrisisManifest,
    *,
    severity: str,
    start_tick: int,
) -> str:
    tape = _tape_payload(manifest, severity, start_tick)
    tape_hash = _canonical_hash(tape)
    for ordinal, leg in enumerate(manifest.shock_legs):
        branch.schedule_shock(
            _native_shock(
                manifest,
                leg,
                severity=severity,
                start_tick=start_tick,
                ordinal=ordinal,
            ),
            operation_id=f"p3:{manifest.scenario_id}:{severity}:{ordinal}",
            payload=_canonical_bytes({
                "schema_version": 1,
                "tape_hash": tape_hash,
                "leg": ordinal,
            }),
        )
    return tape_hash


def _crisis_native_spec(
    manifest: CrisisManifest, *, population: int, seed: int
) -> Any:
    maximum_days = manifest.burn_in_days + manifest.horizon_days + 4
    baseline = population_scaled_new_game(
        population=population,
        days=maximum_days,
        seed=seed,
        countries=manifest.countries,
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(
        native_spec,
        scenario=manifest.activation_scenario,
    )
    return native_spec


def _run_crisis_seed(
    manifest: CrisisManifest,
    *,
    seed: int,
    population: int,
    workers: int,
    source_revision: str,
    verify_replay: bool,
    cache_path: Path,
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature_payload = {
        "schema_version": P3_SCHEMA_VERSION,
        "source_revision": source_revision,
        "manifest": manifest.to_dict(),
        "population": population,
        "workers": workers,
        "seed": seed,
        "verify_replay": verify_replay,
    }
    signature = _canonical_hash(signature_payload)
    if resume and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True
    started = time.perf_counter()
    session = NativeSimulationSession.create_from_native_spec(
        _crisis_native_spec(manifest, population=population, seed=seed),
        worker_count=workers,
        history_capacity_frames=manifest.burn_in_days + manifest.horizon_days + 8,
    )
    session.advance(manifest.burn_in_days)
    t0 = session.tick
    common_checkpoint = session.checkpoint()
    common_checkpoint_hash = hashlib.sha256(common_checkpoint).hexdigest()

    control = session.clone()
    control.advance(manifest.horizon_days)
    control_rows = _history_rows_after(
        control,
        economy_id=0,
        first_tick_exclusive=t0,
        last_tick_inclusive=t0 + manifest.horizon_days,
    )
    control_series = _series(control_rows, manifest.metric_ids)
    severity_runs: dict[str, Any] = {}
    for severity in SEVERITIES:
        branch = session.clone()
        start_tick = t0 + 1
        tape_hash = _schedule_tape(
            branch,
            manifest,
            severity=severity,
            start_tick=start_tick,
        )
        scheduled_checkpoint = branch.checkpoint()
        scheduled_checkpoint_hash = hashlib.sha256(scheduled_checkpoint).hexdigest()
        branch.advance(manifest.horizon_days)
        rows = _history_rows_after(
            branch,
            economy_id=0,
            first_tick_exclusive=t0,
            last_tick_inclusive=t0 + manifest.horizon_days,
        )
        captured = _series(rows, manifest.metric_ids)
        replay = None
        if verify_replay and severity == "moderate":
            restored, _objective = NativeSimulationSession.restore(
                branch.spec,
                scheduled_checkpoint,
                worker_count=workers,
            )
            restored.advance(manifest.horizon_days)
            replay = {
                "final_checkpoint_sha256": hashlib.sha256(restored.checkpoint()).hexdigest(),
                "expected_final_checkpoint_sha256": hashlib.sha256(branch.checkpoint()).hexdigest(),
            }
            replay["passed"] = (
                replay["final_checkpoint_sha256"]
                == replay["expected_final_checkpoint_sha256"]
            )
        severity_runs[severity] = {
            "tape_hash": tape_hash,
            "scheduled_checkpoint_sha256": scheduled_checkpoint_hash,
            "series": captured,
            "integrity": _integrity(captured),
            "terminal_active_shocks": captured.get("metric.shock.active_count", [math.inf])[-1],
            "replay": replay,
        }

    result = {
        "scenario_id": manifest.scenario_id,
        "seed": seed,
        "t0": t0,
        "common_checkpoint_sha256": common_checkpoint_hash,
        "control": {
            "series": control_series,
            "integrity": _integrity(control_series),
        },
        "severities": severity_runs,
        "elapsed_seconds": time.perf_counter() - started,
        "memory_bytes": session.memory_usage(),
    }
    _atomic_json(cache_path, {
        "schema_version": "policy-p3-crisis-run-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result, False


def _adverse_path(
    control: Sequence[float], treatment: Sequence[float], rule: AdverseRule
) -> list[float]:
    if len(control) != len(treatment):
        raise ValueError("paired crisis series have different lengths")
    if rule.direction == "increase":
        return [right - left for left, right in zip(control, treatment, strict=True)]
    return [left - right for left, right in zip(control, treatment, strict=True)]


def _rule_evidence(
    control: Sequence[float], treatment: Sequence[float], rule: AdverseRule
) -> dict[str, Any]:
    adverse = _adverse_path(control, treatment, rule)
    baseline_scale = max(fmean(abs(value) for value in control), 1.0e-12)
    threshold = max(rule.absolute_floor, rule.relative_floor * baseline_scale)
    if rule.statistic == "cumulative":
        observed = sum(adverse)
    elif rule.statistic == "peak":
        observed = max(adverse, default=-math.inf)
    else:
        observed = fmean(adverse)
    persistent_days = sum(value >= threshold for value in adverse)
    passed = observed >= threshold and persistent_days >= min(
        rule.persistence_days, len(adverse)
    )
    return {
        **rule.to_dict(),
        "baseline_scale": baseline_scale,
        "threshold": threshold,
        "observed": observed,
        "persistent_days": persistent_days,
        "passed": passed,
    }


def _seed_gate(
    run: Mapping[str, Any], manifest: CrisisManifest, rules: Sequence[AdverseRule]
) -> dict[str, Any]:
    control = run["control"]["series"]
    treatment = run["severities"]["moderate"]["series"]
    evidence = []
    for rule in rules:
        if rule.metric_id not in control or rule.metric_id not in treatment:
            evidence.append({**rule.to_dict(), "missing": True, "passed": False})
        else:
            evidence.append(_rule_evidence(
                control[rule.metric_id], treatment[rule.metric_id], rule
            ))
    return {
        "seed": run["seed"],
        "rules": evidence,
        "passed": bool(evidence) and all(item["passed"] for item in evidence),
    }


def _primary_loss(
    run: Mapping[str, Any], manifest: CrisisManifest, severity: str
) -> float | None:
    metric_id = manifest.primary_damage.metric_id
    control = run["control"]["series"].get(metric_id)
    treatment = run["severities"][severity]["series"].get(metric_id)
    if control is None or treatment is None:
        return None
    adverse = _adverse_path(control, treatment, manifest.primary_damage)
    if manifest.primary_damage.statistic == "cumulative":
        return sum(adverse)
    if manifest.primary_damage.statistic == "peak":
        return max(adverse, default=None)
    return fmean(adverse)


def _severity_gate(
    runs: Sequence[Mapping[str, Any]], manifest: CrisisManifest
) -> dict[str, Any]:
    by_seed = []
    for run in runs:
        losses = {severity: _primary_loss(run, manifest, severity) for severity in SEVERITIES}
        ordered = (
            all(value is not None for value in losses.values())
            and float(losses["mild"]) < float(losses["moderate"])
            and float(losses["moderate"]) < float(losses["severe"])
        )
        by_seed.append({"seed": run["seed"], "losses": losses, "ordered": ordered})
    means = {
        severity: fmean(
            float(item["losses"][severity])
            for item in by_seed
            if item["losses"][severity] is not None
        )
        if any(item["losses"][severity] is not None for item in by_seed)
        else None
        for severity in SEVERITIES
    }
    aggregate_ordered = (
        all(value is not None for value in means.values())
        and float(means["mild"]) < float(means["moderate"])
        and float(means["moderate"]) < float(means["severe"])
    )
    ordered_seed_count = sum(bool(item["ordered"]) for item in by_seed)
    return {
        "primary_metric": manifest.primary_damage.metric_id,
        "mean_losses": means,
        "by_seed": by_seed,
        "ordered_seed_count": ordered_seed_count,
        "aggregate_ordered": aggregate_ordered,
        "passed": aggregate_ordered and ordered_seed_count >= 6,
    }


def _recovery_seed(run: Mapping[str, Any], manifest: CrisisManifest) -> dict[str, Any]:
    metric_id = manifest.primary_damage.metric_id
    control = run["control"]["series"].get(metric_id)
    treatment = run["severities"]["moderate"]["series"].get(metric_id)
    if control is None or treatment is None:
        return {"seed": run["seed"], "missing": True, "passed": False}
    adverse = _adverse_path(control, treatment, manifest.primary_damage)
    peak = max(adverse, default=0.0)
    terminal = fmean(max(0.0, value) for value in adverse[-min(14, len(adverse)) :])
    persistent_days = sum(value >= max(peak * 0.10, manifest.primary_damage.absolute_floor) for value in adverse)
    inactive = (
        float(run["severities"]["moderate"]["terminal_active_shocks"]) == 0.0
    )
    if manifest.recovery_mode == "recover":
        path_passed = peak > 0.0 and terminal <= peak * 0.75
    elif manifest.recovery_mode == "new_regime":
        path_passed = peak > 0.0 and terminal <= peak * 2.0
    else:
        path_passed = peak > 0.0 and (
            terminal <= peak * 0.75 or terminal <= peak * 1.25
        )
    passed = path_passed and inactive and persistent_days >= 3
    return {
        "seed": run["seed"],
        "peak_adverse_effect": peak,
        "terminal_adverse_effect": terminal,
        "persistent_days": persistent_days,
        "terminal_shock_inactive": inactive,
        "mode": manifest.recovery_mode,
        "passed": passed,
    }


def analyze_crisis(
    manifest: CrisisManifest, runs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if manifest.readiness == "blocked":
        return {
            "scenario_id": manifest.scenario_id,
            "declared_readiness": manifest.readiness,
            "disposition": "blocked_engine_gap",
            "accepted": False,
            "reason": manifest.caveat,
            "entry_gate": None,
            "propagation_gate": None,
            "severity_gate": None,
            "recovery_gate": None,
            "integrity_gate": None,
        }
    entry_by_seed = [_seed_gate(run, manifest, manifest.entry_rules) for run in runs]
    propagation_by_seed = [
        _seed_gate(run, manifest, manifest.propagation_rules) for run in runs
    ]
    entry_count = sum(item["passed"] for item in entry_by_seed)
    propagation_count = sum(item["passed"] for item in propagation_by_seed)
    entry_gate = {
        "passed_seed_count": entry_count,
        "required_seed_count": 6,
        "by_seed": entry_by_seed,
        "passed": len(runs) == 8 and entry_count >= 6,
    }
    propagation_gate = {
        "passed_seed_count": propagation_count,
        "required_seed_count": 6,
        "by_seed": propagation_by_seed,
        "passed": len(runs) == 8 and propagation_count >= 6,
    }
    severity_gate = _severity_gate(runs, manifest)
    recovery_by_seed = [_recovery_seed(run, manifest) for run in runs]
    recovery_count = sum(item["passed"] for item in recovery_by_seed)
    recovery_gate = {
        "passed_seed_count": recovery_count,
        "required_seed_count": 6,
        "by_seed": recovery_by_seed,
        "passed": len(runs) == 8 and recovery_count >= 6,
    }
    integrity_runs = []
    for run in runs:
        passed = bool(run["control"]["integrity"]["passed"])
        passed = passed and all(
            item["integrity"]["passed"]
            and float(item["terminal_active_shocks"]) == 0.0
            for item in run["severities"].values()
        )
        replay = run["severities"]["moderate"].get("replay")
        if replay is not None:
            passed = passed and bool(replay["passed"])
        integrity_runs.append({"seed": run["seed"], "passed": passed, "replay": replay})
    integrity_gate = {
        "by_seed": integrity_runs,
        "replay_evidence_count": sum(item["replay"] is not None for item in integrity_runs),
        "passed": len(runs) == 8 and all(item["passed"] for item in integrity_runs),
    }
    gates = {
        "entry": entry_gate["passed"],
        "propagation": propagation_gate["passed"],
        "severity": severity_gate["passed"],
        "recovery": recovery_gate["passed"],
        "integrity": integrity_gate["passed"],
    }
    accepted = all(gates.values())
    if accepted:
        disposition = "accepted"
        reason = "All five no-response scenario gates passed."
    else:
        first_failed = next(name for name, passed in gates.items() if not passed)
        disposition = (
            "conditional_unaccepted"
            if manifest.readiness == "conditional"
            else f"crisis_{first_failed}_failure"
        )
        reason = f"The no-response {first_failed} gate did not pass."
    return {
        "scenario_id": manifest.scenario_id,
        "declared_readiness": manifest.readiness,
        "disposition": disposition,
        "accepted": accepted,
        "reason": reason,
        "entry_gate": entry_gate,
        "propagation_gate": propagation_gate,
        "severity_gate": severity_gate,
        "recovery_gate": recovery_gate,
        "integrity_gate": integrity_gate,
        "frozen_tape_hashes": {
            severity: sorted({run["severities"][severity]["tape_hash"] for run in runs})
            for severity in SEVERITIES
        },
        "frozen_common_checkpoint_hashes": [
            {"seed": run["seed"], "sha256": run["common_checkpoint_sha256"]}
            for run in runs
        ],
    }


def analyze_state(
    manifest: StateManifest, runs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    passed_by_seed = []
    for run in runs:
        passed = (
            not run["missing_metrics"]
            and run["integrity"]["passed"]
            and len(run["criteria"]) == len(manifest.criteria)
            and all(item["passed"] for item in run["criteria"])
        )
        passed_by_seed.append({"seed": run["seed"], "passed": passed, "criteria": run["criteria"]})
    count = sum(item["passed"] for item in passed_by_seed)
    accepted = len(runs) == 8 and count >= 6
    return {
        "scenario_id": manifest.scenario_id,
        "scenario_class": manifest.scenario_class,
        "accepted": accepted,
        "disposition": "accepted" if accepted else "state_unaccepted",
        "passed_seed_count": count,
        "required_seed_count": 6,
        "by_seed": passed_by_seed,
        "frozen_checkpoint_hashes": [
            {"seed": run["seed"], "sha256": run["checkpoint_sha256"]}
            for run in runs
        ],
    }


def _run_parallel(
    function: Any,
    manifest: Any,
    *,
    seeds: Sequence[int],
    jobs: int,
    path_for_seed: Any,
    kwargs: Mapping[str, Any],
    replay_seed: int | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    results = []
    cache_hits = 0
    executed = 0
    with ThreadPoolExecutor(max_workers=min(jobs, len(seeds))) as executor:
        futures = {}
        for seed in seeds:
            call_kwargs = dict(kwargs)
            call_kwargs["cache_path"] = path_for_seed(seed)
            if replay_seed is not None:
                call_kwargs["verify_replay"] = seed == replay_seed
            future = executor.submit(function, manifest, seed=seed, **call_kwargs)
            futures[future] = seed
        for future in as_completed(futures):
            result, cached = future.result()
            results.append(result)
            cache_hits += int(cached)
            executed += int(not cached)
    return sorted(results, key=lambda item: int(item["seed"])), cache_hits, executed


def validate_manifest_catalogs() -> list[str]:
    errors = []
    if set(STATE_MANIFESTS) != set(ORDINARY_SCENARIOS) | set(STRUCTURAL_SCENARIOS):
        errors.append("P3 state manifests do not exactly cover the P0 state catalog")
    if set(CRISIS_MANIFESTS) != set(SCENARIOS):
        errors.append("P3 crisis manifests do not exactly cover the P0 crisis catalog")
    for scenario_id, manifest in CRISIS_MANIFESTS.items():
        catalog = SCENARIOS[scenario_id]
        if manifest.readiness != catalog.readiness:
            errors.append(f"{scenario_id}: readiness drifted from P0")
        if manifest.readiness != "blocked" and not manifest.shock_legs:
            errors.append(f"{scenario_id}: runnable scenario has no immutable shock tape")
        declared = set(catalog.entry_metrics + catalog.damage_metrics)
        measured = {
            rule.metric_id
            for rule in (
                *manifest.entry_rules,
                *manifest.propagation_rules,
                manifest.primary_damage,
            )
        }
        if not set(catalog.entry_metrics).issubset(measured):
            errors.append(f"{scenario_id}: a P0 entry metric is not measured")
        if not declared.intersection(measured):
            errors.append(f"{scenario_id}: P0 and P3 observables are disconnected")
    return errors


def run_p3(
    *,
    artifact_dir: Path,
    source_revision: str,
    seeds: Sequence[int] = DEFAULT_P3_SEEDS,
    population: int = 100_000,
    workers: int = 8,
    jobs: int = 4,
    resume: bool = True,
    progress: Any = None,
) -> dict[str, Any]:
    if len(seeds) != 8 or len(set(seeds)) != 8:
        raise ValueError("P3 requires exactly eight unique matched seeds")
    if population < 100_000:
        raise ValueError("P3 crisis validation requires at least 100,000 persons per country")
    if workers != 8:
        raise ValueError("P3 acceptance uses exactly eight native engine workers")
    if jobs < 1:
        raise ValueError("jobs must be positive")
    p0 = build_p0_payload()
    errors = validate_manifest_catalogs()
    state_runs: dict[str, list[dict[str, Any]]] = {}
    crisis_runs: dict[str, list[dict[str, Any]]] = {}
    cache_hits = 0
    executed = 0
    manifests = [STATE_MANIFESTS[name] for name in (*ORDINARY_SCENARIOS, *STRUCTURAL_SCENARIOS)]
    for index, manifest in enumerate(manifests, start=1):
        if progress is not None:
            progress("state", index, len(manifests), manifest)
        runs, hits, fresh = _run_parallel(
            _run_state_seed,
            manifest,
            seeds=seeds,
            jobs=jobs,
            path_for_seed=lambda seed, name=manifest.scenario_id: artifact_dir / "runs" / "states" / name / f"{seed}.json",
            kwargs={
                "population": population,
                "workers": workers,
                "source_revision": source_revision,
                "resume": resume,
            },
        )
        state_runs[manifest.scenario_id] = runs
        cache_hits += hits
        executed += fresh

    runnable = [
        manifest
        for manifest in CRISIS_MANIFESTS.values()
        if manifest.readiness != "blocked"
    ]
    for index, manifest in enumerate(runnable, start=1):
        if progress is not None:
            progress("crisis", index, len(runnable), manifest)
        runs, hits, fresh = _run_parallel(
            _run_crisis_seed,
            manifest,
            seeds=seeds,
            jobs=jobs,
            replay_seed=min(seeds),
            path_for_seed=lambda seed, name=manifest.scenario_id: artifact_dir / "runs" / "crises" / name / f"{seed}.json",
            kwargs={
                "population": population,
                "workers": workers,
                "source_revision": source_revision,
                "resume": resume,
            },
        )
        crisis_runs[manifest.scenario_id] = runs
        cache_hits += hits
        executed += fresh

    state_reports = [
        analyze_state(STATE_MANIFESTS[name], state_runs[name])
        for name in (*ORDINARY_SCENARIOS, *STRUCTURAL_SCENARIOS)
    ]
    crisis_reports = [
        analyze_crisis(CRISIS_MANIFESTS[name], crisis_runs.get(name, ()))
        for name in SCENARIOS
    ]
    accepted_crises = sorted(
        item["scenario_id"] for item in crisis_reports if item["accepted"]
    )
    unaccepted_crises = sorted(
        item["scenario_id"] for item in crisis_reports if not item["accepted"]
    )
    manifest_payload = {
        "states": [manifest.to_dict() for manifest in manifests],
        "crises": [CRISIS_MANIFESTS[name].to_dict() for name in SCENARIOS],
    }
    evidence = {
        "states": state_reports,
        "crises": crisis_reports,
    }
    status = "accepted_with_explicit_defects" if not errors else "failed"
    payload = {
        "schema_version": P3_SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "source_revision": source_revision,
        "p0_root_hash": p0["hashes"]["p0_root"],
        "protocol": {
            "population_per_country": population,
            "matched_seeds": list(seeds),
            "native_engine_workers": workers,
            "independent_seed_jobs": min(jobs, len(seeds)),
            "entry_required_seeds": 6,
            "legacy_python_simulator_used": False,
        },
        "counts": {
            "ordinary_states": len(ORDINARY_SCENARIOS),
            "structural_states": len(STRUCTURAL_SCENARIOS),
            "crises": len(SCENARIOS),
            "accepted_states": sum(item["accepted"] for item in state_reports),
            "accepted_crises": len(accepted_crises),
            "unaccepted_crises": len(unaccepted_crises),
            "native_run_records": sum(len(items) for items in state_runs.values())
            + sum(len(items) for items in crisis_runs.values()),
            "executed_native_runs": executed,
            "cache_hits": cache_hits,
        },
        "accepted_crises_for_p4": accepted_crises,
        "excluded_crises_for_p4": unaccepted_crises,
        "manifest": manifest_payload,
        "reports": evidence,
        "hashes": {
            "p3_manifest": _canonical_hash(manifest_payload),
            "p3_evidence": _canonical_hash(evidence),
        },
    }
    payload["hashes"]["p3_acceptance"] = _canonical_hash({
        "status": status,
        "errors": errors,
        "p0_root": p0["hashes"]["p0_root"],
        "protocol": payload["protocol"],
        "manifest": payload["hashes"]["p3_manifest"],
        "evidence": payload["hashes"]["p3_evidence"],
        "accepted_crises_for_p4": accepted_crises,
    })
    _atomic_json(artifact_dir / "p3_report.json", payload)
    return payload


def render_p3_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy causality audit P3",
        "",
        f"- Status: `{payload['status']}`",
        f"- Population per country: {payload['protocol']['population_per_country']:,}",
        f"- Matched seeds: `{payload['protocol']['matched_seeds']}`",
        f"- Native workers per session: {payload['protocol']['native_engine_workers']}",
        f"- Manifest hash: `{payload['hashes']['p3_manifest']}`",
        f"- Evidence hash: `{payload['hashes']['p3_evidence']}`",
        f"- Acceptance hash: `{payload['hashes']['p3_acceptance']}`",
        "",
        "## State environments",
        "",
        "| Scenario | Class | Passed seeds | Disposition |",
        "|---|---|---:|---|",
    ]
    for report in payload["reports"]["states"]:
        lines.append(
            f"| `{report['scenario_id']}` | `{report['scenario_class']}` | "
            f"{report['passed_seed_count']}/8 | `{report['disposition']}` |"
        )
    lines.extend([
        "",
        "## Crisis environments",
        "",
        "| Scenario | P0 readiness | Entry | Propagation | Severity | Recovery | Integrity | Disposition |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ])
    for report in payload["reports"]["crises"]:
        gates = []
        for name in ("entry", "propagation", "severity", "recovery", "integrity"):
            gate = report.get(f"{name}_gate")
            gates.append("-" if gate is None else ("pass" if gate["passed"] else "fail"))
        lines.append(
            f"| `{report['scenario_id']}` | `{report['declared_readiness']}` | "
            + " | ".join(gates)
            + f" | `{report['disposition']}` |"
        )
    lines.extend([
        "",
        "## P4 eligibility freeze",
        "",
        "Accepted: " + ", ".join(f"`{item}`" for item in payload["accepted_crises_for_p4"]),
        "",
        "Excluded: " + ", ".join(f"`{item}`" for item in payload["excluded_crises_for_p4"]),
        "",
        "An excluded crisis must not support a policy-efficacy claim until a later P3 rerun accepts all five gates.",
        "",
    ])
    return "\n".join(lines)


__all__ = [
    "CRISIS_MANIFESTS",
    "DEFAULT_P3_SEEDS",
    "P3_SCHEMA_VERSION",
    "SEVERITIES",
    "STATE_MANIFESTS",
    "AdverseRule",
    "CrisisManifest",
    "ShockLeg",
    "StateCriterion",
    "StateManifest",
    "analyze_crisis",
    "analyze_state",
    "render_p3_markdown",
    "run_p3",
    "validate_manifest_catalogs",
]
