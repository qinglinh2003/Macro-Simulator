"""Paired counterfactual experiments against the native C++ engine.

Python owns orchestration and statistical reduction only. Every simulated day
is advanced by :class:`NativeSimulationSession`, whose state owner is C++.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
import math
from statistics import NormalDist, fmean, stdev
import time
from typing import Any, Iterable, Mapping, Sequence

from macro_sim.config import Config
from macro_sim.desktop.new_game import CAPABILITY_DISABLE_CASCADE, NewGameSpec
from macro_sim.native_backend import NativeSimulationSession
from macro_sim import native_backend


DEFAULT_WORKERS = 8
DEFAULT_POPULATION = 100_000
PATHWISE_MATERIAL_RELATIVE_THRESHOLD = 1.0e-3

WORLD_NATIVE_FIELDS: Mapping[str, str] = {
    "trade": "trade",
    "capital": "capital",
    "migration": "migration",
    "fx_lambda": "fx_adjustment",
    "fx_friction": "fx_friction",
    "fx_spread": "fx_spread",
    "fx_loss_mutualization": "fx_loss_mutualization",
    "fx_trade_cap": "fx_trade_cap",
    "capital_mobility": "capital_mobility",
    "capital_adjust": "capital_adjustment",
    "migration_rate": "migration_rate",
    "migration_max_share": "migration_max_share",
    "remittance_share": "remittance_share",
    "wage_smoothing": "wage_smoothing",
    "peg_reserves0": "initial_peg_reserves",
}


# The product parser rescales these per-representative-agent opening values
# after applying country overrides.  A Config treatment is expressed in the
# pre-scaling semantic unit, so the experiment overlay must preserve the
# control contract's density multiplier instead of overwriting the scaled
# native value with an unscaled number.
PROFILE_DENSITY_SCALED_FIELDS = frozenset(
    {
        "d_cfirm0",
        "inv_firm0",
        "inv_kfirm0",
        "K_firm0",
        "demand_e_firm0",
        "d_efirm0",
        "builder_demand_seed",
    }
)


@dataclass(frozen=True, slots=True)
class MetricSummary:
    observations: int
    mean: float
    final: float
    minimum: float
    maximum: float
    volatility: float
    first_window_mean: float
    last_window_mean: float
    cumulative: float
    post_burnin_mean: float
    post_burnin_volatility: float


@dataclass(frozen=True, slots=True)
class EffectSummary:
    pairs: int
    mean_difference: float
    confidence_low: float | None
    confidence_high: float | None
    paired_standard_deviation: float
    mean_relative_difference: float | None
    mean_absolute_difference: float
    mean_absolute_relative_difference: float | None
    pathwise_material_share: float | None


@dataclass(frozen=True, slots=True)
class TimeResponseSummary:
    observations: int
    first_difference_tick: int | None
    peak_tick: int
    peak_effect: float
    terminal_effect: float
    mean_effect: float
    cumulative_effect: float
    half_decay_tick: int | None
    sign_reversals: int


def population_scaled_configs(
    *,
    population: int,
    days: int,
    seed: int,
    countries: int = 1,
) -> tuple[Config, ...]:
    """Return playable profile Configs at stable representative densities."""
    if population < 1:
        raise ValueError("population must be positive")
    if days < 1:
        raise ValueError("days must be positive")
    profiles = NewGameSpec.default(seed=seed).configs()
    if not 1 <= countries <= len(profiles):
        raise ValueError("countries exceeds the built-in profile count")
    output = []
    for economy_id, config in enumerate(profiles[:countries]):
        output.append(
            replace(
                config,
                n_households=population,
                n_firms_c=max(1, round(population * 0.015)),
                n_firms_k=max(1, round(population * 0.005)),
                n_firms_e=max(1, round(population * 0.0025)),
                n_builders=max(1, round(population * 0.00625)),
                n_banks=max(1, round(population * 0.00008)),
                demographics_population=population,
                n_ticks=days,
                seed=seed + economy_id,
            )
        )
    return tuple(output)


def population_scaled_new_game(
    *,
    population: int,
    days: int,
    seed: int,
    countries: int = 1,
) -> NewGameSpec:
    if population < 1:
        raise ValueError("population must be positive")
    raw = NewGameSpec.default(seed=seed).to_dict()
    if not 1 <= countries <= len(raw["countries"]):
        raise ValueError("countries exceeds the built-in profile count")
    raw["duration"] = days
    raw["countries"] = raw["countries"][:countries]
    for country in raw["countries"]:
        overrides = dict(country.get("overrides", {}))
        overrides.update(
            {
                "demographics_population": population,
                "n_households": population,
                "n_firms_c": max(1, round(population * 0.015)),
                "n_firms_k": max(1, round(population * 0.005)),
                "n_firms_e": max(1, round(population * 0.0025)),
                "n_builders": max(1, round(population * 0.00625)),
                "n_banks": max(1, round(population * 0.00008)),
            }
        )
        country["overrides"] = overrides
    return NewGameSpec.from_mapping(raw)


def apply_config_treatment(
    configs: Sequence[Config],
    *,
    field: str,
    value: Any,
    target_economy: int = 0,
) -> tuple[Config, ...]:
    if not 0 <= target_economy < len(configs):
        raise IndexError("target_economy is outside the Config sequence")
    if field not in Config.__dataclass_fields__:
        raise ValueError(f"unknown root Config field {field!r}")
    changes = {field: value}
    changed = True
    while changed:
        changed = False
        for parent, dependants in CAPABILITY_DISABLE_CASCADE.items():
            if changes.get(parent) is not False:
                continue
            for name, dependant_value in dependants.items():
                if changes.get(name, object()) != dependant_value:
                    changes[name] = dependant_value
                    changed = True
    output = list(configs)
    output[target_economy] = replace(output[target_economy], **changes)
    return tuple(output)


def apply_config_treatments(
    configs: Sequence[Config],
    *,
    treatments: Mapping[str, Any],
    target_economy: int = 0,
) -> tuple[Config, ...]:
    """Apply one valid joint Config treatment with capability closure."""
    if not treatments:
        raise ValueError("joint Config treatment must not be empty")
    if not 0 <= target_economy < len(configs):
        raise IndexError("target_economy is outside the Config sequence")
    unknown = sorted(set(treatments) - set(Config.__dataclass_fields__))
    if unknown:
        raise ValueError("unknown root Config fields: " + ", ".join(unknown))
    changes = dict(treatments)
    changed = True
    while changed:
        changed = False
        for parent, dependants in CAPABILITY_DISABLE_CASCADE.items():
            if changes.get(parent) is not False:
                continue
            for name, dependant_value in dependants.items():
                if changes.get(name, object()) != dependant_value:
                    changes[name] = dependant_value
                    changed = True
    output = list(configs)
    output[target_economy] = replace(output[target_economy], **changes)
    return tuple(output)


def _history_rows(
    session: NativeSimulationSession,
    economy_id: int,
) -> list[dict[str, Any]]:
    bounds = session.history_bounds()
    cursor = int(bounds["oldest_sequence"])
    stop = int(bounds["next_sequence"])
    output: list[dict[str, Any]] = []
    while cursor < stop:
        page = session.maintained_history_page(
            cursor, min(512, stop - cursor)
        )
        for frame in page["frames"]:
            if int(frame["tick"]) <= 0:
                continue
            row = derive_analysis_metrics(frame["economies"][economy_id])
            row["_tick"] = int(frame["tick"])
            output.append(row)
        next_cursor = int(page["next_sequence"])
        if next_cursor <= cursor:
            raise RuntimeError("native metric history cursor did not advance")
        cursor = next_cursor
    return output


def derive_analysis_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    """Add transparent ratios derived only from maintained native metrics."""
    output = dict(row)
    spending = output.get(
        "metric.economy.na.household_consumption_goods_nominal"
    )
    units = output.get("metric.economy.sector_consumption_sales")
    if (
        isinstance(spending, (int, float))
        and not isinstance(spending, bool)
        and isinstance(units, (int, float))
        and not isinstance(units, bool)
        and math.isfinite(float(spending))
        and math.isfinite(float(units))
    ):
        if float(units) > 1.0e-12:
            output["metric.analysis.goods_transaction_price_proxy"] = (
                float(spending) / float(units)
            )
    return output


def summarize_metric_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    window_days: int = 30,
    burn_in_days: int = 0,
) -> dict[str, MetricSummary]:
    if not rows:
        raise ValueError("cannot summarize an empty metric history")
    if burn_in_days < 0 or burn_in_days >= len(rows):
        raise ValueError("burn_in_days must leave at least one observation")
    metric_ids = sorted(set.intersection(*(set(row) for row in rows)))
    output: dict[str, MetricSummary] = {}
    for metric_id in metric_ids:
        if metric_id.startswith("_"):
            continue
        values: list[float] = []
        for row in rows:
            value = row[metric_id]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                values = []
                break
            number = float(value)
            if not math.isfinite(number):
                raise RuntimeError(
                    f"non-finite native metric {metric_id}: {value!r}"
                )
            values.append(number)
        if not values:
            continue
        width = min(max(1, window_days), len(values))
        post_burnin = values[burn_in_days:]
        output[metric_id] = MetricSummary(
            observations=len(values),
            mean=fmean(values),
            final=values[-1],
            minimum=min(values),
            maximum=max(values),
            volatility=stdev(values) if len(values) > 1 else 0.0,
            first_window_mean=fmean(values[:width]),
            last_window_mean=fmean(values[-width:]),
            cumulative=sum(values),
            post_burnin_mean=fmean(post_burnin),
            post_burnin_volatility=(
                stdev(post_burnin) if len(post_burnin) > 1 else 0.0
            ),
        )
    return output


def run_native_case(
    configs: Sequence[Config],
    *,
    days: int,
    workers: int = DEFAULT_WORKERS,
    economy_id: int = 0,
    world_overrides: Mapping[str, Any] | None = None,
    burn_in_days: int = 0,
) -> dict[str, Any]:
    if days < 1:
        raise ValueError("days must be positive")
    started = time.perf_counter()
    session = NativeSimulationSession.create_from_configs(
        configs,
        player_country=economy_id,
        worker_count=workers,
        history_capacity_frames=days + 2,
        world_overrides=world_overrides,
    )
    session.advance(days)
    elapsed = time.perf_counter() - started
    rows = _history_rows(session, economy_id)
    return {
        "days": days,
        "elapsed_seconds": elapsed,
        "seconds_per_day": elapsed / days,
        "workers": workers,
        "economy_id": economy_id,
        "metric_summaries": {
            name: asdict(summary)
            for name, summary in summarize_metric_series(
                rows, burn_in_days=burn_in_days
            ).items()
        },
        "memory_bytes": session.memory_usage(),
        "storage_counts": session.storage_counts(),
    }


def _apply_native_root_field(
    native_spec: Any,
    *,
    field: str,
    value: Any,
    economy_id: int,
    baseline_value: Any | None = None,
) -> None:
    """Mutate one native contract field while preserving product defaults."""
    economies = list(native_spec.economies)
    if not 0 <= economy_id < len(economies):
        raise IndexError("economy_id is outside the native experiment spec")
    economy = economies[economy_id]
    population = economy.domestic_economy
    financial = population.financial_economy
    monetary = financial.monetary_economy
    real = monetary.real_economy
    real_rules = real.rules
    monetary_rules = monetary.rules
    monetary_policy = monetary.policy
    financial_policy = financial.policy
    financial_rules = financial.rules
    population_policy = population.policy
    population_rules = population.rules
    energy_policy = economy.energy_policy
    energy_rules = economy.energy_rules
    housing_policy = economy.housing_policy
    housing_rules = economy.housing_rules
    sections = (
        (real_rules, native_backend.M4_RULE_FIELDS),
        (monetary_rules, native_backend.M5_RULE_FIELDS),
        (financial_rules, native_backend.M6_RULE_FIELDS),
        (population_rules, native_backend.M7_RULE_FIELDS),
        (energy_rules, native_backend.ENERGY_RULE_FIELDS),
        (housing_rules, native_backend.HOUSING_RULE_FIELDS),
    )
    policy_sections = (
        (monetary_policy, native_backend.M5_POLICY_FIELDS),
        (financial_policy, native_backend.M6_POLICY_FIELDS),
        (population_policy, native_backend.M7_POLICY_FIELDS),
        (energy_policy, native_backend.ENERGY_POLICY_FIELDS),
        (housing_policy, native_backend.HOUSING_POLICY_FIELDS),
    )
    matched = False
    bridge_computed_fields = {"bank_capital_frac", "d_bank0"}
    for target, mapping in sections:
        for target_name, source_name in mapping.items():
            if source_name == field and field not in bridge_computed_fields:
                resolved_value = value
                if field == "energy_hh_share":
                    resolved_value = (
                        float(value)
                        * float(energy_rules.initial_wage)
                        / max(1.0e-12, float(energy_rules.initial_price))
                    )
                elif field in PROFILE_DENSITY_SCALED_FIELDS:
                    if baseline_value is None:
                        raise ValueError(
                            f"Config field {field!r} requires its baseline value"
                        )
                    if float(baseline_value) != 0.0:
                        resolved_value = (
                            float(getattr(target, target_name))
                            * float(value)
                            / float(baseline_value)
                        )
                    elif field == "builder_demand_seed":
                        population_count = int(
                            population.population.initial_persons
                        )
                        builder_count = max(1, int(housing_rules.builder_count))
                        builder_scale = max(
                            1.0e-6,
                            0.025 * float(population_count) / builder_count,
                        )
                        resolved_value = float(value) * builder_scale
                    else:
                        raise ValueError(
                            f"Config field {field!r} requires a nonzero baseline"
                        )
                setattr(target, target_name, resolved_value)
                matched = True

    # Capability closure can disable policy seeds as a consequence of a
    # structural Config treatment (for example interbank -> OMO/LOLR or
    # mortgages -> underwriting).  Apply those dependent writes to the native
    # policy contract as well; otherwise the experiment would no longer match
    # the validated Config produced by the start-menu cascade.
    for target, mapping in policy_sections:
        for target_name, source_name in mapping.items():
            if source_name == field:
                setattr(target, target_name, value)
                matched = True

    if field == "bond_theta":
        financial_policy.household_bond_target = float(value)
        matched = True
    elif field == "bank_bond_appetite":
        financial_policy.bank_bond_appetite = float(value)
        matched = True
    elif field in bridge_computed_fields:
        if baseline_value is None:
            raise ValueError(
                f"Config field {field!r} requires its baseline value"
            )
        household_count = int(real.households)
        private_opening_money = (
            household_count * float(real_rules.initial_household_money)
            + (int(real.consumption_firms) + int(real.capital_firms))
            * float(real_rules.initial_firm_money)
            + int(energy_rules.producer_count)
            * float(energy_rules.initial_producer_cash)
            + int(housing_rules.builder_count)
            * float(housing_rules.initial_builder_cash_buffer)
        )
        bank_count = max(1, int(monetary_rules.bank_count))
        if field == "bank_capital_frac":
            capital_delta = (
                (float(value) - float(baseline_value))
                * private_opening_money
                / bank_count
            )
        else:
            capital_delta = (
                float(value) - float(baseline_value)
            ) / bank_count
            real_rules.initial_bank_capital = float(value)
        monetary_rules.opening_capital_per_bank += capital_delta
        matched = True
    elif field == "capital_market":
        enabled = bool(value)
        financial_rules.firm_equity = enabled
        financial_rules.bank_equity = enabled
        financial_rules.bank_equity_trading = enabled
        financial_rules.equity_finance = enabled
        financial_rules.margin_credit = enabled
        matched = True
    elif field == "bank_enabled":
        enabled = bool(value)
        monetary_rules.household_credit = enabled
        monetary_rules.interbank = enabled
        monetary_rules.rate_competition = enabled
        monetary_rules.relationship_lock_in = enabled
        financial_rules.bank_equity = enabled
        financial_rules.bank_equity_trading = enabled
        financial_rules.bank_dynamics = enabled
        matched = True
    elif field == "government":
        capability = 1 << 1
        if bool(value):
            real.requested_capabilities |= capability
        else:
            real.requested_capabilities &= ~capability
        matched = True
    elif field == "n_households":
        real.households = int(value)
        matched = True
    elif field == "n_firms_c":
        real.consumption_firms = int(value)
        matched = True
    elif field == "n_firms_k":
        real.capital_firms = int(value)
        matched = True
    elif field == "n_firms_e":
        energy_rules.producer_count = int(value)
        matched = True
    elif field == "n_builders":
        housing_rules.builder_count = int(value)
        matched = True
    elif field == "n_banks":
        monetary_rules.bank_count = int(value)
        real.settlement_banks = int(value)
        matched = True
    elif field == "demographics_population":
        population.population.initial_persons = int(value)
        matched = True
    elif field == "seed":
        real.seed = int(value)
        matched = True
    elif field == "bank_assignment":
        monetary_rules.assign_banks_by_size = value == "by_size"
        matched = True
    elif field == "demographics_tfr":
        vital = population_rules.vital_rates
        vital.total_fertility_rate = float(value)
        population_rules.vital_rates = vital
        matched = True
    elif field == "demographics_mortality_scale":
        if baseline_value is None or float(baseline_value) <= 0.0:
            raise ValueError(
                "demographics_mortality_scale requires a positive baseline"
            )
        ratio = float(value) / float(baseline_value)
        vital = population_rules.vital_rates
        vital.makeham_a *= ratio
        vital.gompertz_b *= ratio
        population_rules.vital_rates = vital
        matched = True
    elif field == "simulation_start_date":
        population.population.start_calendar_day = date.fromisoformat(
            str(value)
        ).toordinal()
        matched = True
    elif field == "marriage_assortativity":
        marriage = population_rules.marriage_rules
        marriage.assortativity = float(value)
        population_rules.marriage_rules = marriage
        matched = True

    if not matched:
        raise ValueError(
            f"Config field {field!r} has no executable native experiment setter"
        )
    real.rules = real_rules
    monetary.rules = monetary_rules
    monetary.policy = monetary_policy
    monetary.real_economy = real
    financial.policy = financial_policy
    financial.rules = financial_rules
    financial.monetary_economy = monetary
    population.rules = population_rules
    population.policy = population_policy
    population.financial_economy = financial
    economy.domestic_economy = population
    economy.energy_policy = energy_policy
    economy.energy_rules = energy_rules
    economy.housing_policy = housing_policy
    economy.housing_rules = housing_rules
    economies[economy_id] = economy
    native_spec.economies = economies


def native_treatment_spec(
    baseline: NewGameSpec,
    *,
    field: str,
    value: Any,
    target_economy: int = 0,
) -> Any:
    """Overlay a Config treatment on the exact product native baseline."""
    baseline_configs = tuple(baseline.configs())
    treated_configs = apply_config_treatment(
        baseline_configs,
        field=field,
        value=value,
        target_economy=target_economy,
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    before = baseline_configs[target_economy]
    after = treated_configs[target_economy]
    for changed_field in Config.__dataclass_fields__:
        before_value = getattr(before, changed_field)
        after_value = getattr(after, changed_field)
        if before_value == after_value:
            continue
        try:
            _apply_native_root_field(
                native_spec,
                field=changed_field,
                value=after_value,
                economy_id=target_economy,
                baseline_value=before_value,
            )
        except ValueError:
            if changed_field != field:
                continue
            raise
    return native_spec


def native_joint_treatment_spec(
    baseline: NewGameSpec,
    *,
    treatments: Mapping[str, Any],
    target_economy: int = 0,
) -> Any:
    """Overlay a capability-valid joint root Config treatment."""
    baseline_configs = tuple(baseline.configs())
    treated_configs = apply_config_treatments(
        baseline_configs,
        treatments=treatments,
        target_economy=target_economy,
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    before = baseline_configs[target_economy]
    after = treated_configs[target_economy]
    for changed_field in Config.__dataclass_fields__:
        before_value = getattr(before, changed_field)
        after_value = getattr(after, changed_field)
        if before_value == after_value:
            continue
        _apply_native_root_field(
            native_spec,
            field=changed_field,
            value=after_value,
            economy_id=target_economy,
            baseline_value=before_value,
        )
    return native_spec


def native_world_treatment_spec(
    baseline: NewGameSpec,
    *,
    field: str,
    value: Any,
) -> Any:
    """Overlay one World Config treatment on the product native baseline."""
    target = WORLD_NATIVE_FIELDS.get(field)
    if target is None:
        raise ValueError(f"unknown World Config field {field!r}")
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.rules
    setattr(rules, target, value)
    if field == "trade" and not bool(value):
        rules.capital = False
        rules.migration = False
    native_spec.rules = rules
    return native_spec


def native_joint_world_treatment_spec(
    baseline: NewGameSpec,
    *,
    treatments: Mapping[str, Any],
) -> Any:
    """Overlay several World Config fields on one product baseline."""
    if not treatments:
        raise ValueError("joint World treatment must not be empty")
    unknown = sorted(set(treatments) - set(WORLD_NATIVE_FIELDS))
    if unknown:
        raise ValueError("unknown World Config fields: " + ", ".join(unknown))
    native_spec = native_backend.build_native_new_game_spec(baseline)
    rules = native_spec.rules
    for field, value in treatments.items():
        setattr(rules, WORLD_NATIVE_FIELDS[field], value)
    if treatments.get("trade") is False:
        rules.capital = False
        rules.migration = False
    native_spec.rules = rules
    return native_spec


def native_world_config_value(native_spec: Any, field: str) -> Any:
    target = WORLD_NATIVE_FIELDS.get(field)
    if target is None:
        raise ValueError(f"unknown World Config field {field!r}")
    return getattr(native_spec.rules, target)


def apply_native_activation_scenario(
    native_spec: Any,
    *,
    scenario: str,
    target_economy: int = 0,
) -> Any:
    """Apply a shared state activation without changing the audited field.

    The same activation is applied to both members of every paired experiment.
    It exists only to put a conditional mechanism on an economically relevant
    branch; it is not itself part of the treatment contrast.
    """
    if scenario in {"neutral_baseline", "neutral_baseline_q_above_one"}:
        return native_spec
    economies = list(native_spec.economies)
    world_scenarios = {
        "world_trade_integration",
        "world_trade_friction",
        "world_capital_rate_gap",
        "world_migration_wage_gap",
        "world_migration_cap_pressure",
        "world_peg_pressure",
        "world_dealer_loss",
        "world_joint_integration",
    }
    if scenario in world_scenarios:
        if len(economies) < 2:
            raise ValueError(f"native activation scenario {scenario!r} needs a World")
        for economy_id, economy in enumerate(economies):
            population = economy.domestic_economy
            financial = population.financial_economy
            monetary = financial.monetary_economy
            real = monetary.real_economy
            rules = real.rules
            if scenario in {
                "world_trade_integration",
                "world_trade_friction",
                "world_peg_pressure",
                "world_dealer_loss",
                "world_joint_integration",
            }:
                if scenario == "world_trade_friction" and economy_id == 0:
                    rules.initial_consumption_inventory *= 4.0
                    rules.initial_price = 0.60
                elif scenario == "world_trade_friction":
                    rules.initial_consumption_inventory = 0.0
                    rules.initial_price = 1.20
                    rules.initial_expected_demand *= 2.0
                elif economy_id == 0:
                    rules.initial_consumption_inventory = 0.0
                    rules.initial_price = 1.20
                    rules.initial_expected_demand *= 2.0
                elif economy_id == 1:
                    rules.initial_consumption_inventory *= 4.0
                    rules.initial_price = 0.60
                else:
                    rules.initial_consumption_inventory *= 2.0
                    rules.initial_price = 0.80
            if scenario in {
                "world_migration_wage_gap",
                "world_migration_cap_pressure",
                "world_joint_integration",
            }:
                rules.initial_wage = 2.0 if economy_id == 0 else 0.70
            if scenario in {
                "world_capital_rate_gap",
                "world_joint_integration",
            }:
                monetary.initial_policy_rate = (0.00030, 0.00005, 0.000134)[
                    min(economy_id, 2)
                ]
            real.rules = rules
            monetary.real_economy = real
            financial.monetary_economy = monetary
            population.financial_economy = financial
            economy.domestic_economy = population
            economies[economy_id] = economy
        native_spec.economies = economies
        world_rules = native_spec.rules
        if scenario == "world_migration_cap_pressure":
            world_rules.migration_rate = 0.05
            world_rules.wage_smoothing = 0.20
        elif scenario in {"world_peg_pressure", "world_dealer_loss"}:
            world_rules.fx_adjustment = 0.25
        native_spec.rules = world_rules
        if scenario == "world_peg_pressure":
            external = list(native_spec.external_policies)
            external[0].fx_regime = native_backend._load_native().FxRegime.PEG
            external[0].peg_anchor = 1
            native_spec.external_policies = external
        return native_spec
    if not 0 <= target_economy < len(economies):
        raise IndexError("target_economy is outside the native experiment spec")
    economy = economies[target_economy]
    population = economy.domestic_economy
    population_rules = population.rules
    financial = population.financial_economy
    financial_policy = financial.policy
    financial_rules = financial.rules
    monetary = financial.monetary_economy
    monetary_policy = monetary.policy
    monetary_rules = monetary.rules
    real = monetary.real_economy
    rules = real.rules
    energy_rules = economy.energy_rules
    housing_rules = economy.housing_rules
    if scenario == "positive_capital_gap":
        rules.initial_consumption_capital *= 0.5
    elif scenario == "opening_consumption_stockout":
        rules.initial_consumption_inventory = 0.0
    elif scenario == "markup_ceiling_pressure":
        rules.initial_consumption_inventory = 0.0
    elif scenario == "markup_floor_pressure":
        rules.initial_consumption_inventory *= 4.0
    elif scenario == "idle_consumption_firms":
        rules.initial_consumption_capital = 1.0e-12
        rules.initial_consumption_inventory = 0.0
        rules.investment_adjustment = 0.0
        financial_rules.firm_subscale_exit = False
    elif scenario == "high_consumption_entry_pressure":
        financial_rules.entry_beta = 5.0
        financial_rules.entry_hurdle = 0.0
    elif scenario == "sector_returns_hazard":
        financial_rules.switch_return_gap = 0.0
        financial_rules.switch_pressure_days = 5
    elif scenario == "sector_returns_pressure":
        financial_rules.switch_return_gap = 0.0
        financial_rules.switch_hazard = 0.05
    elif scenario == "sector_returns_retool":
        financial_rules.switch_return_gap = 0.0
        financial_rules.switch_pressure_days = 5
        financial_rules.switch_hazard = 0.05
    elif scenario == "sector_returns_gap":
        financial_rules.switch_pressure_days = 5
        financial_rules.switch_hazard = 0.05
    elif scenario == "active_job_ladder":
        population_rules.ladder_premium = 0.0
    elif scenario == "binding_labor_reservation":
        population_rules.reservation_markup = 2.5
    elif scenario == "labor_demand_contraction":
        rules.initial_expected_demand *= 4.0
        rules.demand_adjustment = 0.10
    elif scenario == "unpartnered_marriage_market":
        population.population.target_household_size = 1.0
        population_rules.marriage_interval_days = 14
        population_rules.annual_marriage_rate = 1.0
        population_rules.annual_divorce_rate = 0.0
    elif scenario == "eligible_peak_leaving_home":
        population_rules.leave_home_min_age = 18
    elif scenario == "long_horizon_peak_leaving_home":
        population_rules.leave_home_min_age = 18
        population_rules.annual_leave_rate_peak = 0.05
        population_rules.annual_leave_rate_late = 0.01
    elif scenario == "eligible_late_leaving_home":
        population_rules.leave_home_min_age = 18
        population_rules.leave_home_peak_end_age = 18
    elif scenario == "bank_entry_eligible_founders":
        financial_policy.bank_minimum_capital = 0.1
        monetary_rules.opening_capital_per_bank = 250.0
    elif scenario == "bank_entry_cap_pressure":
        financial_policy.bank_minimum_capital = 0.1
        financial_rules.bank_entry_beta = 0.50
        monetary_rules.opening_capital_per_bank = 250.0
    elif scenario == "binding_bank_capital":
        monetary_policy.bank_capital_constraint = True
        monetary_rules.opening_capital_per_bank = 250.0
    elif scenario == "positive_deposit_carry":
        monetary_rules.deposit_rate = 1.0e-4
    elif scenario == "monetary_tightening_pressure":
        monetary.initial_policy_rate = 5.0e-3
        monetary_policy.neutral_rate = 1.34e-4
        rules.initial_consumption_capital *= 0.5
        rules.initial_household_money = 0.20
        monetary_policy.household_credit_limit = 5.0
        monetary_rules.household_subsistence = 2.0
    elif scenario == "monetary_tightening_elasticity":
        monetary.initial_policy_rate = 5.0e-3
        monetary_policy.neutral_rate = 1.34e-4
        monetary_rules.investment_user_cost_multiplier_min = 0.05
        rules.initial_consumption_capital *= 0.5
    elif scenario == "monetary_easing_pressure":
        monetary.initial_policy_rate = 0.0
        monetary_policy.neutral_rate = 3.0e-4
        rules.initial_consumption_capital *= 0.5
    elif scenario == "monetary_zlb_pressure":
        monetary.initial_policy_rate = 0.0
        monetary_policy.neutral_rate = 1.34e-4
        rules.capital_depreciation = 0.0
        rules.initial_consumption_capital *= 0.5
    elif scenario == "bank_run_pressure":
        monetary_policy.bank_capital_constraint = True
        monetary_rules.opening_capital_per_bank = 250.0
        monetary_rules.run_health_reference = 0.22
    elif scenario == "bank_run_fear_pressure":
        monetary_rules.run_health_reference = 100.0
        monetary_rules.run_sensitivity = 0.50
    elif scenario == "bank_run_health_screen":
        monetary_rules.bank_runs = True
        monetary_rules.interbank = True
        monetary_policy.bank_capital_constraint = True
        monetary_rules.opening_capital_per_bank = 250.0
        monetary_rules.bank_leverage_mean = 100.0
    elif scenario == "credit_joint_pressure":
        monetary_policy.bank_capital_constraint = True
        monetary_rules.opening_capital_per_bank = 250.0
        monetary_rules.deposit_spread_dispersion = 1.0e-4
        monetary_rules.run_health_reference = 0.22
    elif scenario == "deposit_arrears_pressure":
        monetary_rules.deposit_rate = 0.005
    elif scenario == "deposit_spread_competition":
        monetary_rules.deposit_spread_dispersion = 1.0e-4
    elif scenario == "active_chartist_demand":
        financial_rules.chartist_weight = 20.0
    elif scenario == "deprivation_measurement_active":
        energy_rules.deprivation_burnin_years = 0
    elif scenario == "energy_inventory_gap":
        rules.initial_consumption_inventory = 0.0
        rules.initial_capital_inventory = 0.0
        rules.demand_adjustment = 0.10
        energy_rules.downstream_coverage_days = 30.0
    elif scenario == "energy_rising_price":
        rules.initial_consumption_inventory = 0.0
        rules.initial_capital_inventory = 0.0
        energy_rules.producer_productivity = 0.50
        energy_rules.household_need = 0.12
        energy_rules.downstream_intensity = 0.10
    elif scenario == "energy_mortality_pressure":
        energy_rules.deprivation_burnin_years = 0
        energy_rules.household_need = 0.15
        energy_rules.downstream_intensity = 0.10
        energy_rules.producer_productivity = 0.50
        energy_rules.fuel_poverty_mortality_cap = 5.0
    elif scenario == "energy_mortality_cap_binding":
        energy_rules.deprivation_burnin_years = 0
        energy_rules.household_need = 0.15
        energy_rules.downstream_intensity = 0.10
        energy_rules.producer_productivity = 0.50
        energy_rules.fuel_poverty_mortality_gamma = 10.0
    elif scenario == "energy_joint_pressure":
        rules.initial_consumption_inventory = 0.0
        rules.initial_capital_inventory = 0.0
        energy_rules.deprivation_burnin_years = 0
        energy_rules.producer_productivity = 0.50
        energy_rules.fuel_poverty_mortality_cap = 5.0
    elif scenario == "housing_shortage":
        housing_rules.initial_dwellings_per_household = 0.80
    elif scenario == "housing_liquid_market":
        housing_rules.initial_dwellings_per_household = 1.20
        housing_rules.initial_homeownership_share = 0.40
        housing_rules.location_count = 8
        housing_rules.distress_deposit_floor = 0.0
        monetary_rules.deposit_rate = 1.5e-4
        rules.initial_household_money = 500.0
    elif scenario == "housing_investor_choice":
        housing_rules.initial_dwellings_per_household = 1.20
        housing_rules.initial_homeownership_share = 0.40
        housing_rules.distress_deposit_floor = 0.0
        monetary_rules.deposit_rate = 8.2e-5
    elif scenario == "housing_search_friction":
        housing_rules.initial_dwellings_per_household = 1.20
        housing_rules.initial_homeownership_share = 0.40
        housing_rules.location_count = 8
        housing_rules.distress_deposit_floor = 0.0
        housing_rules.voluntary_ask_markup = 0.20
        housing_rules.ask_decay = 0.05
        housing_rules.buyer_liquidity_buffer = 0.10
        monetary_rules.deposit_rate = 1.5e-4
        rules.initial_household_money = 260.0
    elif scenario == "housing_distressed_market":
        housing_rules.initial_dwellings_per_household = 1.10
        housing_rules.location_count = 8
        housing_rules.distress_deposit_floor = 2_000.0
        rules.initial_household_money = 1_000.0
    elif scenario == "housing_rental_pressure":
        housing_rules.initial_dwellings_per_household = 0.90
        housing_rules.rental_vacancy_deadband = 0.0
    elif scenario == "housing_affordability_pressure":
        housing_rules.initial_dwellings_per_household = 0.80
        housing_rules.affordability_burnin_years = 0
        housing_rules.demand_price_step = 0.15
    elif scenario == "housing_affordability_relief":
        housing_rules.initial_dwellings_per_household = 1.50
        housing_rules.affordability_burnin_years = 0
        housing_rules.ask_decay = 0.05
        housing_rules.rent_adjustment = 0.25
        housing_rules.rental_vacancy_deadband = 0.0
    elif scenario == "housing_joint_pressure":
        housing_rules.initial_dwellings_per_household = 0.80
        housing_rules.initial_homeownership_share = 0.40
        housing_rules.location_count = 8
        housing_rules.distress_deposit_floor = 0.0
        housing_rules.affordability_burnin_years = 0
        housing_rules.demand_price_step = 0.15
        housing_rules.rental_vacancy_deadband = 0.0
        monetary_rules.deposit_rate = 1.5e-4
        rules.initial_household_money = 500.0
    elif scenario == "firm_joint_dynamism":
        financial_rules.entry_max = 6
        financial_rules.switch_return_gap = 0.0
        financial_rules.switch_pressure_days = 5
        financial_rules.switch_hazard = 0.05
    else:
        raise ValueError(f"unknown native activation scenario {scenario!r}")
    real.rules = rules
    monetary.policy = monetary_policy
    monetary.rules = monetary_rules
    monetary.real_economy = real
    financial.policy = financial_policy
    financial.rules = financial_rules
    financial.monetary_economy = monetary
    population.rules = population_rules
    population.financial_economy = financial
    economy.domestic_economy = population
    economy.energy_rules = energy_rules
    economy.housing_rules = housing_rules
    economies[target_economy] = economy
    native_spec.economies = economies
    return native_spec


def run_native_spec_case(
    native_spec: Any,
    *,
    days: int,
    workers: int = DEFAULT_WORKERS,
    economy_id: int = 0,
    burn_in_days: int = 0,
    series_metric_ids: Iterable[str] = (),
) -> dict[str, Any]:
    started = time.perf_counter()
    session = NativeSimulationSession.create_from_native_spec(
        native_spec,
        player_country=economy_id,
        worker_count=workers,
        history_capacity_frames=days + 2,
    )
    session.advance(days)
    elapsed = time.perf_counter() - started
    requested_series = tuple(dict.fromkeys(series_metric_ids))
    rows_by_economy = {
        str(current_economy): _history_rows(session, current_economy)
        for current_economy in range(len(native_spec.economies))
    }
    summaries_by_economy = {
        str(current_economy): {
            name: asdict(summary)
            for name, summary in summarize_metric_series(
                rows_by_economy[str(current_economy)],
                burn_in_days=burn_in_days,
            ).items()
        }
        for current_economy in range(len(native_spec.economies))
    }
    series_by_economy: dict[str, dict[str, Any]] = {}
    for current_economy, rows in rows_by_economy.items():
        available = summaries_by_economy[current_economy]
        missing = sorted(set(requested_series) - set(available))
        if missing:
            raise RuntimeError(
                "requested native metrics are unavailable: " + ", ".join(missing)
            )
        series_by_economy[current_economy] = {
            metric_id: {
                "ticks": [int(row["_tick"]) for row in rows],
                "values": [float(row[metric_id]) for row in rows],
            }
            for metric_id in requested_series
        }
    return {
        "days": days,
        "elapsed_seconds": elapsed,
        "seconds_per_day": elapsed / days,
        "workers": workers,
        "economy_id": economy_id,
        "burn_in_days": burn_in_days,
        "metric_summaries": summaries_by_economy[str(economy_id)],
        "metric_summaries_by_economy": summaries_by_economy,
        "metric_series": series_by_economy[str(economy_id)],
        "metric_series_by_economy": series_by_economy,
        "memory_bytes": session.memory_usage(),
        "storage_counts": session.storage_counts(),
    }


def paired_effect(
    control: Sequence[float],
    treatment: Sequence[float],
    *,
    confidence: float = 0.95,
) -> EffectSummary:
    if len(control) != len(treatment) or not control:
        raise ValueError("paired samples must have equal, positive length")
    differences = [
        treated - baseline
        for baseline, treated in zip(control, treatment, strict=True)
    ]
    mean_difference = fmean(differences)
    paired_sd = stdev(differences) if len(differences) > 1 else 0.0
    if len(differences) > 1:
        critical = _paired_critical_value(
            pairs=len(differences), confidence=confidence
        )
        half_width = critical * paired_sd / math.sqrt(len(differences))
        confidence_low = mean_difference - half_width
        confidence_high = mean_difference + half_width
    else:
        confidence_low = None
        confidence_high = None
    relative = [
        (treated - baseline) / abs(baseline)
        for baseline, treated in zip(control, treatment, strict=True)
        if abs(baseline) > 1.0e-12
    ]
    absolute_relative = [abs(value) for value in relative]
    return EffectSummary(
        pairs=len(differences),
        mean_difference=mean_difference,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        paired_standard_deviation=paired_sd,
        mean_relative_difference=fmean(relative) if relative else None,
        mean_absolute_difference=fmean(abs(value) for value in differences),
        mean_absolute_relative_difference=(
            fmean(absolute_relative) if absolute_relative else None
        ),
        pathwise_material_share=(
            sum(
                value >= PATHWISE_MATERIAL_RELATIVE_THRESHOLD
                for value in absolute_relative
            )
            / len(absolute_relative)
            if absolute_relative
            else None
        ),
    )


_T_CRITICAL_95 = (
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def _paired_critical_value(*, pairs: int, confidence: float) -> float:
    """Use Student's t for the small paired seed blocks used by the audit."""
    if pairs < 2:
        raise ValueError("at least two pairs are required for an interval")
    if math.isclose(confidence, 0.95) and pairs - 1 <= len(_T_CRITICAL_95):
        return _T_CRITICAL_95[pairs - 2]
    return NormalDist().inv_cdf(0.5 + confidence / 2.0)


def summarize_time_responses(
    control_runs: Sequence[Mapping[str, Any]],
    treatment_runs: Sequence[Mapping[str, Any]],
    *,
    absolute_tolerance: float = 1.0e-12,
) -> dict[str, dict[str, Any]]:
    """Reduce paired daily paths without treating days as independent samples."""
    if len(control_runs) != len(treatment_runs) or not control_runs:
        raise ValueError("control and treatment run counts must match")
    metric_sets = [
        set(run.get("metric_series", {}))
        for run in (*control_runs, *treatment_runs)
    ]
    if not metric_sets or not all(metric_sets):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for metric_id in sorted(set.intersection(*metric_sets)):
        paired_paths: list[list[float]] = []
        ticks: list[int] | None = None
        for control, treatment in zip(
            control_runs, treatment_runs, strict=True
        ):
            control_series = control["metric_series"][metric_id]
            treatment_series = treatment["metric_series"][metric_id]
            control_ticks = [int(value) for value in control_series["ticks"]]
            treatment_ticks = [int(value) for value in treatment_series["ticks"]]
            if control_ticks != treatment_ticks:
                raise ValueError(f"paired ticks differ for {metric_id}")
            if ticks is None:
                ticks = control_ticks
            elif ticks != control_ticks:
                raise ValueError(f"seed paths have different ticks for {metric_id}")
            paired_paths.append(
                [
                    float(treated) - float(baseline)
                    for baseline, treated in zip(
                        control_series["values"],
                        treatment_series["values"],
                        strict=True,
                    )
                ]
            )
        assert ticks is not None
        mean_path = [fmean(values) for values in zip(*paired_paths, strict=True)]
        peak_index = max(range(len(mean_path)), key=lambda index: abs(mean_path[index]))
        peak = mean_path[peak_index]
        first_index = next(
            (
                index
                for index, effect in enumerate(mean_path)
                if abs(effect) > absolute_tolerance
            ),
            None,
        )
        half_decay_tick = None
        if abs(peak) > absolute_tolerance:
            half_level = abs(peak) / 2.0
            for index in range(peak_index + 1, len(mean_path)):
                if abs(mean_path[index]) <= half_level:
                    half_decay_tick = ticks[index]
                    break
        signs = [
            1 if value > absolute_tolerance else -1
            for value in mean_path
            if abs(value) > absolute_tolerance
        ]
        sign_reversals = sum(
            left != right for left, right in zip(signs, signs[1:])
        )
        summary = TimeResponseSummary(
            observations=len(mean_path),
            first_difference_tick=(
                ticks[first_index] if first_index is not None else None
            ),
            peak_tick=ticks[peak_index],
            peak_effect=peak,
            terminal_effect=mean_path[-1],
            mean_effect=fmean(mean_path),
            cumulative_effect=sum(mean_path),
            half_decay_tick=half_decay_tick,
            sign_reversals=sign_reversals,
        )
        output[metric_id] = {
            **asdict(summary),
            "terminal_seed_interval": asdict(
                paired_effect(
                    [0.0] * len(paired_paths),
                    [path[-1] for path in paired_paths],
                )
            ),
        }
    return output


def summarize_paired_runs(
    control_runs: Sequence[Mapping[str, Any]],
    treatment_runs: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    if len(control_runs) != len(treatment_runs) or not control_runs:
        raise ValueError("control and treatment run counts must match")
    metric_sets = [
        set(run["metric_summaries"])
        for run in (*control_runs, *treatment_runs)
    ]
    common_metrics = sorted(set.intersection(*metric_sets))
    statistics = (
        "mean",
        "final",
        "volatility",
        "first_window_mean",
        "last_window_mean",
        "cumulative",
        "post_burnin_mean",
        "post_burnin_volatility",
    )
    output: dict[str, dict[str, dict[str, Any]]] = {}
    for metric_id in common_metrics:
        metric_effects: dict[str, dict[str, Any]] = {}
        for statistic in statistics:
            control = [
                float(run["metric_summaries"][metric_id][statistic])
                for run in control_runs
            ]
            treatment = [
                float(run["metric_summaries"][metric_id][statistic])
                for run in treatment_runs
            ]
            metric_effects[statistic] = asdict(
                paired_effect(control, treatment)
            )
        output[metric_id] = metric_effects
    return output


def changed_metrics(
    effects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    absolute_tolerance: float = 1.0e-12,
    relative_tolerance: float = 1.0e-9,
) -> list[str]:
    output = []
    for metric_id, statistics in effects.items():
        effect = statistics["mean"]
        absolute = abs(float(effect["mean_difference"]))
        relative_value = effect["mean_relative_difference"]
        relative = (
            abs(float(relative_value)) if relative_value is not None else None
        )
        if absolute > absolute_tolerance and (
            relative is None or relative > relative_tolerance
        ):
            output.append(metric_id)
    return output


def effect_scales(
    effects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    control_value: Any,
    treatment_value: Any,
) -> dict[str, dict[str, dict[str, float | None]]]:
    if (
        isinstance(control_value, bool)
        or isinstance(treatment_value, bool)
        or not isinstance(control_value, (int, float))
        or not isinstance(treatment_value, (int, float))
    ):
        return {}
    input_delta = float(treatment_value) - float(control_value)
    if abs(input_delta) <= 1.0e-15:
        return {}
    input_relative = (
        input_delta / abs(float(control_value))
        if abs(float(control_value)) > 1.0e-12
        else None
    )
    output: dict[str, dict[str, dict[str, float | None]]] = {}
    for metric_id, statistics in effects.items():
        scaled: dict[str, dict[str, float | None]] = {}
        for statistic, effect in statistics.items():
            relative = effect["mean_relative_difference"]
            scaled[statistic] = {
                "semi_elasticity": float(effect["mean_difference"]) / input_delta,
                "local_elasticity": (
                    float(relative) / input_relative
                    if relative is not None
                    and input_relative is not None
                    and abs(input_relative) > 1.0e-15
                    else None
                ),
            }
        output[metric_id] = scaled
    return output


def default_burn_in_days(days: int) -> int:
    if days < 2:
        return 0
    return min(90, max(1, days // 4), days - 1)


def run_root_config_experiment(
    *,
    field: str,
    treatment_value: Any,
    control_value: Any | None,
    seeds: Iterable[int],
    population: int = DEFAULT_POPULATION,
    days: int = 365,
    workers: int = DEFAULT_WORKERS,
    countries: int = 1,
    burn_in_days: int | None = None,
    series_metric_ids: Iterable[str] = (),
) -> dict[str, Any]:
    control_runs = []
    treatment_runs = []
    seed_values = tuple(seeds)
    if not seed_values:
        raise ValueError("at least one seed is required")
    resolved_burn_in = (
        default_burn_in_days(days) if burn_in_days is None else burn_in_days
    )
    resolved_control: Any = None
    requested_series = tuple(series_metric_ids)
    for seed in seed_values:
        baseline = population_scaled_new_game(
            population=population,
            days=days,
            seed=seed,
            countries=countries,
        )
        baseline_config = baseline.configs()[0]
        if control_value is None:
            control_spec = native_backend.build_native_new_game_spec(baseline)
            resolved_control = getattr(baseline_config, field)
        else:
            control_spec = native_treatment_spec(
                baseline, field=field, value=control_value
            )
            resolved_control = control_value
        treatment_spec = native_treatment_spec(
            baseline, field=field, value=treatment_value
        )
        control_runs.append(
            run_native_spec_case(
                control_spec,
                days=days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                series_metric_ids=requested_series,
            )
        )
        treatment_runs.append(
            run_native_spec_case(
                treatment_spec,
                days=days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                series_metric_ids=requested_series,
            )
        )
    effects = summarize_paired_runs(control_runs, treatment_runs)
    return {
        "schema_version": "native-config-experiment-v1",
        "field": field,
        "control_value": resolved_control,
        "treatment_value": treatment_value,
        "seeds": list(seed_values),
        "population_per_country": population,
        "days": days,
        "workers": workers,
        "countries": countries,
        "burn_in_days": resolved_burn_in,
        "control_runs": control_runs,
        "treatment_runs": treatment_runs,
        "effects": effects,
        "time_responses": summarize_time_responses(
            control_runs, treatment_runs
        ),
        "effect_scales": effect_scales(
            effects,
            control_value=resolved_control,
            treatment_value=treatment_value,
        ),
        "changed_metric_count": len(changed_metrics(effects)),
        "changed_metrics": changed_metrics(effects),
    }


def run_world_config_experiment(
    *,
    field: str,
    treatment_value: Any,
    control_value: Any | None,
    seeds: Iterable[int],
    population: int = DEFAULT_POPULATION,
    days: int = 365,
    workers: int = DEFAULT_WORKERS,
    countries: int = 3,
    burn_in_days: int | None = None,
    series_metric_ids: Iterable[str] = (),
) -> dict[str, Any]:
    if countries < 2:
        raise ValueError("World Config experiments require at least two countries")
    control_runs = []
    treatment_runs = []
    seed_values = tuple(seeds)
    if not seed_values:
        raise ValueError("at least one seed is required")
    resolved_burn_in = (
        default_burn_in_days(days) if burn_in_days is None else burn_in_days
    )
    resolved_control: Any = None
    requested_series = tuple(series_metric_ids)
    for seed in seed_values:
        baseline = population_scaled_new_game(
            population=population,
            days=days,
            seed=seed,
            countries=countries,
        )
        if control_value is None:
            control_spec = native_backend.build_native_new_game_spec(baseline)
            resolved_control = native_world_config_value(control_spec, field)
        else:
            control_spec = native_world_treatment_spec(
                baseline, field=field, value=control_value
            )
            resolved_control = control_value
        treatment_spec = native_world_treatment_spec(
            baseline, field=field, value=treatment_value
        )
        control_runs.append(
            run_native_spec_case(
                control_spec,
                days=days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                series_metric_ids=requested_series,
            )
        )
        treatment_runs.append(
            run_native_spec_case(
                treatment_spec,
                days=days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                series_metric_ids=requested_series,
            )
        )

    effects_by_economy: dict[str, Any] = {}
    changed_by_economy: dict[str, list[str]] = {}
    for economy_id in range(countries):
        control_economy_runs = [
            {
                **run,
                "metric_summaries": run["metric_summaries_by_economy"][
                    str(economy_id)
                ],
            }
            for run in control_runs
        ]
        treatment_economy_runs = [
            {
                **run,
                "metric_summaries": run["metric_summaries_by_economy"][
                    str(economy_id)
                ],
            }
            for run in treatment_runs
        ]
        economy_effects = summarize_paired_runs(
            control_economy_runs, treatment_economy_runs
        )
        effects_by_economy[str(economy_id)] = economy_effects
        changed_by_economy[str(economy_id)] = changed_metrics(economy_effects)
    changed_union = sorted(
        set().union(*(set(values) for values in changed_by_economy.values()))
    )
    effect_scales_by_economy = {
        economy_id: effect_scales(
            effects,
            control_value=resolved_control,
            treatment_value=treatment_value,
        )
        for economy_id, effects in effects_by_economy.items()
    }
    time_responses_by_economy: dict[str, Any] = {}
    for economy_id in range(countries):
        control_economy_runs = [
            {
                **run,
                "metric_series": run["metric_series_by_economy"][
                    str(economy_id)
                ],
            }
            for run in control_runs
        ]
        treatment_economy_runs = [
            {
                **run,
                "metric_series": run["metric_series_by_economy"][
                    str(economy_id)
                ],
            }
            for run in treatment_runs
        ]
        time_responses_by_economy[str(economy_id)] = summarize_time_responses(
            control_economy_runs, treatment_economy_runs
        )
    return {
        "schema_version": "native-world-config-experiment-v1",
        "field": field,
        "control_value": resolved_control,
        "treatment_value": treatment_value,
        "seeds": list(seed_values),
        "population_per_country": population,
        "days": days,
        "workers": workers,
        "countries": countries,
        "burn_in_days": resolved_burn_in,
        "control_runs": control_runs,
        "treatment_runs": treatment_runs,
        "effects_by_economy": effects_by_economy,
        "effect_scales_by_economy": effect_scales_by_economy,
        "time_responses_by_economy": time_responses_by_economy,
        "changed_metric_count": len(changed_union),
        "changed_metrics": changed_union,
        "changed_metrics_by_economy": changed_by_economy,
    }
