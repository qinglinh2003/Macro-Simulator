"""Compare the Python Config inventory with the actual native product contract."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Mapping

from macro_sim import native_backend
from macro_sim.diagnostics.config_causality import build_audit_inventory
from macro_sim.diagnostics.config_experiment import (
    PROFILE_DENSITY_SCALED_FIELDS,
    WORLD_NATIVE_FIELDS,
    population_scaled_new_game,
)


def _native_root_values(native_spec: Any, economy_id: int = 0) -> dict[str, Any]:
    economy = native_spec.economies[economy_id]
    population = economy.domestic_economy
    financial = population.financial_economy
    monetary = financial.monetary_economy
    real = monetary.real_economy
    sections = (
        ("m4.real_rules", real.rules, native_backend.M4_RULE_FIELDS),
        ("m5.monetary_rules", monetary.rules, native_backend.M5_RULE_FIELDS),
        ("m6.financial_rules", financial.rules, native_backend.M6_RULE_FIELDS),
        ("m7.population_rules", population.rules, native_backend.M7_RULE_FIELDS),
        ("m8.energy_rules", economy.energy_rules, native_backend.ENERGY_RULE_FIELDS),
        ("m8.housing_rules", economy.housing_rules, native_backend.HOUSING_RULE_FIELDS),
    )
    values: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section, target, mapping in sections:
        for target_name, source_name in mapping.items():
            values[source_name].append(
                {
                    "target": f"{section}.{target_name}",
                    "value": getattr(target, target_name),
                }
            )

    manual = {
        "n_households": real.households,
        "n_firms_c": real.consumption_firms,
        "n_firms_k": real.capital_firms,
        "n_firms_e": economy.energy_rules.producer_count,
        "n_builders": economy.housing_rules.builder_count,
        "n_banks": monetary.rules.bank_count,
        "seed": real.seed,
        "bank_assignment": (
            "by_size" if monetary.rules.assign_banks_by_size else "random"
        ),
        "demographics_tfr": population.rules.vital_rates.total_fertility_rate,
        "demographics_population": population.population.initial_persons,
        "simulation_start_date": population.population.start_calendar_day,
        "marriage_assortativity": population.rules.marriage_rules.assortativity,
        "bank_bond_appetite": financial.policy.bank_bond_appetite,
        "bond_theta": financial.policy.household_bond_target,
        "bank_capital_frac": monetary.rules.opening_capital_per_bank,
        "demographics_mortality_scale": (
            population.rules.vital_rates.makeham_a
            + population.rules.vital_rates.gompertz_b
        ),
        "capital_market": all(
            (
                financial.rules.firm_equity,
                financial.rules.bank_equity,
                financial.rules.bank_equity_trading,
                financial.rules.equity_finance,
                financial.rules.margin_credit,
            )
        ),
        "bank_enabled": all(
            (
                monetary.rules.household_credit,
                monetary.rules.interbank,
                monetary.rules.rate_competition,
                monetary.rules.relationship_lock_in,
                financial.rules.bank_equity,
                financial.rules.bank_equity_trading,
                financial.rules.bank_dynamics,
            )
        ),
        "government": bool(real.requested_capabilities & (1 << 1)),
    }
    for source_name, value in manual.items():
        values[source_name].append(
            {"target": "manual_native_projection", "value": value}
        )
    return dict(values)


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1.0e-12, abs_tol=1.0e-12)
    return left == right


def build_native_baseline_audit(
    *, population: int = 100_000, seed: int = 101, countries: int = 3
) -> dict[str, Any]:
    baseline = population_scaled_new_game(
        population=population, days=365, seed=seed, countries=countries
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    root_values = _native_root_values(native_spec)
    inventory = build_audit_inventory()
    rows = []
    for row in inventory["rows"]:
        if row["route_status"] != "mapped_native":
            continue
        field = str(row["field_name"])
        if row["declaring_type"] == "World":
            target = WORLD_NATIVE_FIELDS[field]
            targets = [
                {
                    "target": f"m9.rules.{target}",
                    "value": getattr(native_spec.rules, target),
                }
            ]
        else:
            targets = list(root_values.get(field, []))
        baseline_value = row["playable_baseline"]
        if not targets:
            status = "projection_missing"
        elif field in {
            "n_households",
            "n_firms_c",
            "n_firms_k",
            "n_firms_e",
            "n_builders",
            "n_banks",
            "demographics_population",
        }:
            status = "experiment_scale_override"
        elif field == "seed":
            status = "experiment_seed_override"
        elif field in PROFILE_DENSITY_SCALED_FIELDS:
            status = "density_scaled"
        elif field in {
            "bank_capital_frac",
            "d_bank0",
            "demographics_mortality_scale",
            "energy_hh_share",
            "simulation_start_date",
        }:
            status = "computed_or_encoded"
        elif all(_same_value(baseline_value, item["value"]) for item in targets):
            status = "exact"
        elif len({repr(item["value"]) for item in targets}) > 1:
            status = "multi_target_divergence"
        else:
            status = "product_baseline_divergence"
        rows.append(
            {
                "field_id": row["id"],
                "field_name": field,
                "module": row["module"],
                "experiment_role": row["experiment_role"],
                "inventory_baseline": baseline_value,
                "native_targets": targets,
                "status": status,
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": "config-native-baseline-audit-v1",
        "population_per_country": population,
        "seed": seed,
        "countries": countries,
        "field_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
