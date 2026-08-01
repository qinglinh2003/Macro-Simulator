"""Static inventory and experiment routing for Config causality audits.

The economic engine owns several different kinds of immutable inputs.  This
module keeps them separate before any dynamic experiment is run:

* gameplay structure and behavioral parameters;
* legacy seeds for live Policy state;
* shock definitions;
* numerical and observability controls; and
* fields that have not yet reached the native engine.

The distinction matters.  A field with no native route is a wiring defect, not
evidence of a small economic elasticity.  Conversely, a numerical tolerance is
expected to have no economic effect and should be tested for invariance.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from macro_sim.desktop.new_game import NewGameSpec
from macro_sim import native_backend


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONFIG_INVENTORY_PATH = REPOSITORY_ROOT / "schemas/m0/inventory/config.json"

POLICY_CLASSIFICATIONS = frozenset(
    {
        "policy_seed_legacy",
        "policyseed_promoted",
        "policy_world",
        "nested_policy_candidate",
        "pending_migration",
    }
)
SHOCK_CLASSIFICATIONS = frozenset({"shock_module"})
INFRA_CLASSIFICATIONS = frozenset({"infra"})
GAMEPLAY_CLASSIFICATIONS = frozenset(
    {"mechanism", "physics", "structure", "nested_physics"}
)


NATIVE_RULE_MAPS: tuple[tuple[str, Mapping[str, str]], ...] = (
    ("m4.real_rules", native_backend.M4_RULE_FIELDS),
    ("m5.monetary_rules", native_backend.M5_RULE_FIELDS),
    ("m6.financial_rules", native_backend.M6_RULE_FIELDS),
    ("m7.population_rules", native_backend.M7_RULE_FIELDS),
    ("m8.energy_rules", native_backend.ENERGY_RULE_FIELDS),
    ("m8.housing_rules", native_backend.HOUSING_RULE_FIELDS),
)

NATIVE_POLICY_MAPS: tuple[tuple[str, Mapping[str, str]], ...] = (
    ("m5.fiscal_monetary_policy", native_backend.M5_POLICY_FIELDS),
    ("m6.financial_policy", native_backend.M6_POLICY_FIELDS),
    ("m7.population_policy", native_backend.M7_POLICY_FIELDS),
    ("m8.energy_policy", native_backend.ENERGY_POLICY_FIELDS),
    ("m8.housing_policy", native_backend.HOUSING_POLICY_FIELDS),
)

# Explicit assignments in native_backend.py that do not go through _assign.
MANUAL_CONFIG_ROUTES: Mapping[str, tuple[str, ...]] = {
    "n_households": ("m4.spec.households",),
    "n_firms_c": ("m4.spec.consumption_firms",),
    "n_firms_k": ("m4.spec.capital_firms",),
    "n_banks": ("m5.rules.bank_count",),
    "seed": ("m4.spec.seed",),
    "bank_assignment": ("m5.rules.assign_banks_by_size",),
    "demographics_tfr": ("m7.rules.vital_rates.total_fertility_rate",),
    "demographics_mortality_scale": (
        "m7.rules.vital_rates.makeham_a",
        "m7.rules.vital_rates.gompertz_b",
    ),
    "marriage_assortativity": ("m7.rules.marriage_rules.assortativity",),
    "demographics_population": ("m7.population.initial_persons",),
    "simulation_start_date": ("m7.population.start_calendar_day",),
    "energy_hh_share": ("m8.energy_rules.household_need",),
    "bank_capital_frac": ("m5.rules.opening_capital_per_bank",),
    "d_bank0": ("m5.rules.opening_capital_per_bank",),
    "bank_enabled": (
        "native_bridge.bank_opening_capital_gate",
    ),
    "bank_bond_appetite": ("m6.policy.bank_bond_appetite",),
    "bond_theta": ("m6.policy.household_bond_target",),
    "capital_market": ("m6.rules.capital_market_cascade",),
    "government": ("m4.spec.requested_capabilities.government",),
}

WORLD_NATIVE_ROUTES: Mapping[str, tuple[str, ...]] = {
    "trade": ("m9.rules.trade",),
    "capital": ("m9.rules.capital",),
    "migration": ("m9.rules.migration",),
    "fx_lambda": ("m9.rules.fx_adjustment",),
    "fx_friction": ("m9.rules.fx_friction",),
    "fx_spread": ("m9.rules.fx_spread",),
    "fx_loss_mutualization": ("m9.rules.fx_loss_mutualization",),
    "fx_trade_cap": ("m9.rules.fx_trade_cap",),
    "capital_mobility": ("m9.rules.capital_mobility",),
    "capital_adjust": ("m9.rules.capital_adjustment",),
    "migration_rate": ("m9.rules.migration_rate",),
    "migration_max_share": ("m9.rules.migration_max_share",),
    "remittance_share": ("m9.rules.remittance_share",),
    "wage_smoothing": ("m9.rules.wage_smoothing",),
    "peg_reserves0": ("m9.rules.initial_peg_reserves",),
}


# Fields retained by the historical inventory whose behavior is deliberately
# unconditional in the latest native engine. They require an invariance or
# removal decision, not a fake elasticity experiment.
NATIVE_FIXED_FIELDS = frozenset(
    {
        "config.capital_annual_clock",
        "config.capital_service_pricing",
        "config.index_startup",
        "config.labor_accounting",
        "config.labor_matching",
        "config.labor_person_efficiency",
        "config.national_accounts_metrics",
        "config.priced_firm_balance_sheet",
        "config.pro_rata_dividends",
        "config.real_entry_signal",
        "config.ticks_per_year",
        "config.world.periods_per_year",
    }
)

SUPERSEDED_FIELDS: Mapping[str, str] = {
    "config.a": (
        "config.case-a in the latest capital-fiscal product; linear productivity "
        "only applies to the retired cash-loop vertical"
    ),
    "config.d_firm0": "config.d_cfirm0",
    "config.float_shares": "config.shares_per_firm",
    "config.gibrat_entry_a0": "config.entry_hurdle and config.entry_beta",
    "config.gibrat_growth": "config.firm_dynamics",
    "config.n_firms": "config.n_firms_c and config.n_firms_k",
    "config.lifecycle-household.annual_leave_rate_late":
        "config.demographic_annual_leave_rate_late",
    "config.lifecycle-household.annual_leave_rate_peak":
        "config.demographic_annual_leave_rate_peak",
    "config.lifecycle-household.leave_home_min_age":
        "config.demographic_leave_home_min_age",
    "config.lifecycle-household.leave_home_peak_end_age":
        "config.demographic_leave_home_peak_end_age",
    "config.social.annual_divorce_rate_base":
        "config.demographic_annual_divorce_rate_base",
    "config.social.annual_marriage_rate_peak":
        "config.demographic_annual_marriage_rate_peak",
    "config.social.divorce_enabled": "config.demographic_divorce_enabled",
    "config.social.marriage_assortativity": "config.marriage_assortativity",
    "config.social.marriage_enabled": "config.demographic_marriage_enabled",
    "config.social.marriage_market_interval_days":
        "config.demographic_marriage_market_interval_days",
}

DERIVED_FIELDS: Mapping[str, str] = {
    "config.world.base_seed": "derived from per-economy Config seeds",
    "config.world.couple": "derived from active open-economy mechanisms",
}

RUN_CONTROL_FIELDS = frozenset({"config.n_ticks"})
PLANNED_REMOVAL_FIELDS: Mapping[str, str] = {
    "config.symmetric_k": "obsolete alternative capital formulation",
}

# These fields reach a native member with a different economic meaning. A
# syntactic assignment is not sufficient evidence of an implemented Config
# route, so they remain repair work until the intended mechanism exists.
INCOMPLETE_NATIVE_ROUTE_FIELDS: Mapping[str, str] = {
    "config.bank_assignment": (
        "Config defines random or borrower-size bank assignment, while the "
        "native false branch currently uses deterministic round-robin genesis "
        "assignment rather than the requested seeded random assignment"
    ),
    "config.bank_enabled": (
        "Config defines the master bank-credit capability, while the native "
        "bridge only disables selected dependent features and still creates "
        "settlement banks and originates ordinary firm credit"
    ),
    "config.consumption_strata": (
        "Config defines a two-stage necessity/luxury goods market, while the "
        "native member only gates sector switching and preserves a firm tag for "
        "differential tax accounting"
    ),
    "config.demographic_lifecycle_consumption": (
        "Config defines a finite-life consumption budget, while the native "
        "member currently controls household moves after marriage, divorce, "
        "and leaving home"
    ),
    "config.government": (
        "Config defines a master fiscal-sector capability, while the current "
        "native capital-fiscal vertical rejects a specification after that "
        "capability bit is removed and therefore cannot execute the requested "
        "government-off economy"
    ),
    "config.monetary_direct_transmission": (
        "Config defines direct investment user-cost, household debt-budget, "
        "and firm debt-service transmission, while the native member currently "
        "only applies the firm debt-service-coverage constraint"
    ),
    "config.necessity_share0": (
        "Config defines a fixed per-need-unit necessity quantity, while the "
        "native member currently controls the fraction of consumption firms "
        "tagged as necessity producers"
    ),
}

# Measurement gates may change published observables but must not receive credit
# for changing the economy they observe.
OBSERVATION_ONLY_FIELDS = frozenset(
    {"config.deprivation_gauges", "config.subsistence_share"}
)


SCALE_FIELDS = frozenset(
    {
        "n_households",
        "n_firms",
        "n_firms_c",
        "n_firms_k",
        "n_firms_e",
        "n_builders",
        "n_banks",
        "demographics_population",
    }
)


# Short mathematical names and cross-module compatibility names cannot be
# assigned reliably with token matching. Keep their economic owner explicit so
# a field is reviewed with the mechanism that actually reads it in C++.
FIELD_MODULE_OVERRIDES: Mapping[str, str] = {
    "bank_bond_appetite": "securities_and_capital_markets",
    "bank_equity": "securities_and_capital_markets",
    "bank_equity_lambda": "securities_and_capital_markets",
    "bank_equity_trading": "securities_and_capital_markets",
    "bank_theta_equity": "securities_and_capital_markets",
    "bank_relationship_lock_in": "banking_and_credit",
    "alpha1": "consumption_prices_and_expectations",
    "alpha2": "consumption_prices_and_expectations",
    "consumption_rationed_signal": "consumption_prices_and_expectations",
    "eta": "consumption_prices_and_expectations",
    "inventory_gap_close": "consumption_prices_and_expectations",
    "lambda_d": "consumption_prices_and_expectations",
    "lambda_y": "consumption_prices_and_expectations",
    "mu_max": "consumption_prices_and_expectations",
    "mu_min": "consumption_prices_and_expectations",
    "phi": "consumption_prices_and_expectations",
    "pref_attach_beta": "consumption_prices_and_expectations",
    "pref_price_elasticity": "consumption_prices_and_expectations",
    "search_m": "consumption_prices_and_expectations",
    "theta_price": "consumption_prices_and_expectations",
    "delta": "labor_market",
    "lambda_fire": "labor_market",
    "labor_relationship_wages": "labor_market",
    "omega": "labor_market",
    "energy_mortality_gamma": "energy",
    "energy_mortality_mult_hi": "energy",
    "housing_fertility_elasticity": "housing",
    "housing_fertility_mult_hi": "housing",
    "housing_fertility_mult_lo": "housing",
    "hh_subsistence": "banking_and_credit",
    "founder_owned_genesis": "securities_and_capital_markets",
    "index_startup": "securities_and_capital_markets",
    "lambda_p": "securities_and_capital_markets",
    "margin_credit": "securities_and_capital_markets",
    "lambda_q": "securities_and_capital_markets",
    "pro_rata_dividends": "securities_and_capital_markets",
    "resid_income_lambda": "securities_and_capital_markets",
    "trend_lambda": "securities_and_capital_markets",
    "watchlist_size": "securities_and_capital_markets",
    "wealth_effect": "securities_and_capital_markets",
    "dis_slope": "firms_and_industrial_dynamics",
    "rho": "firms_and_industrial_dynamics",
    "sector_switching": "firms_and_industrial_dynamics",
    "subsistence_share": "distribution_and_welfare",
    "house_price_income_years": "housing",
    "household_interest_arrears": "banking_and_credit",
    "investment_user_cost_elasticity": "banking_and_credit",
    "investment_user_cost_floor": "banking_and_credit",
    "investment_user_cost_multiplier_max": "banking_and_credit",
    "investment_user_cost_multiplier_min": "banking_and_credit",
    "monetary_direct_transmission": "banking_and_credit",
    "k_replacement_floor": "production_and_technology",
    "symmetric_k": "production_and_technology",
    "n_ticks": "numerics_and_observability",
    "national_accounts_metrics": "numerics_and_observability",
    "ticks_per_year": "numerics_and_observability",
    "seed": "scale_and_genesis",
    "simulation_start_date": "scale_and_genesis",
}


MODULE_CHECKS: Mapping[str, Mapping[str, Any]] = {
    "firm_accounts": {
        "firm_full_pnl": True,
        "priced_firm_balance_sheet": True,
        "capital_service_pricing": True,
    },
    "firm_dynamics": {
        "firm_dynamics": True,
        "firm_subscale_exit": True,
        "capital_firm_entry": True,
    },
    "banking_and_credit": {
        "bank_enabled": True,
        "bank_realized_pnl": True,
        "household_credit": True,
        "bank_relationship_lock_in": True,
    },
    "interbank_and_runs": {
        "interbank": True,
        "bank_runs": True,
    },
    "bonds_and_equity": {
        "bonds": True,
        "capital_market": True,
        "per_firm_equity": True,
        "equity_finance": True,
    },
    "government": {
        "government": True,
        "national_accounts_metrics": True,
    },
    "demography_and_households": {
        "demographics_enabled": True,
        "demographic_lifecycle_consumption": True,
        "family_transfers": True,
    },
    "labor_market": {
        "labor_matching": "persistent",
        "labor_fractional_hours": True,
        "labor_second_job": True,
        "labor_suspension": True,
        "labor_matching_friction": True,
        "labor_relationship_wages": True,
        "labor_job_ladder": True,
        "labor_person_efficiency": True,
        "labor_participation": True,
    },
    "housing": {
        "housing_enabled": True,
        "housing_market_enabled": True,
        "mortgage_enabled": True,
        "mortgage_underwriting": True,
        "housing_rental_enabled": True,
        "housing_construction_enabled": True,
    },
    "energy": {
        "energy_enabled": True,
        "energy_household": True,
        "deprivation_gauges": True,
    },
    "distribution_and_reallocation": {
        "consumption_strata": True,
        "sector_switching": True,
    },
}

WORLD_MODULE_CHECKS: Mapping[str, Any] = {
    "trade": True,
    "capital": True,
    "migration": True,
}


@dataclass(frozen=True, slots=True)
class Route:
    status: str
    targets: tuple[str, ...] = ()
    note: str = ""


def _source_routes(
    source_name: str,
    route_maps: Iterable[tuple[str, Mapping[str, str]]],
) -> tuple[str, ...]:
    output: list[str] = []
    for section, mapping in route_maps:
        output.extend(
            f"{section}.{target}"
            for target, source in mapping.items()
            if source == source_name
        )
    return tuple(sorted(output))


def _route_for(row: Mapping[str, Any]) -> Route:
    classification = str(row["classification"])
    declaring_type = str(row["declaring_type"])
    name = str(row["field_name"])
    field_id = str(row["id"])

    if classification in POLICY_CLASSIFICATIONS:
        targets = _source_routes(name, NATIVE_POLICY_MAPS)
        return Route("excluded_policy", targets)
    if classification in SHOCK_CLASSIFICATIONS:
        return Route("excluded_shock")
    if classification in INFRA_CLASSIFICATIONS:
        targets = _source_routes(name, NATIVE_RULE_MAPS)
        targets += MANUAL_CONFIG_ROUTES.get(name, ())
        return Route("infrastructure_invariance", tuple(sorted(set(targets))))
    if field_id in NATIVE_FIXED_FIELDS:
        return Route("native_fixed")
    if field_id in SUPERSEDED_FIELDS:
        return Route("superseded", note=SUPERSEDED_FIELDS[field_id])
    if field_id in DERIVED_FIELDS:
        return Route("derived", note=DERIVED_FIELDS[field_id])
    if field_id in RUN_CONTROL_FIELDS:
        return Route("run_control")
    if field_id in PLANNED_REMOVAL_FIELDS:
        return Route(
            "planned_removal", note=PLANNED_REMOVAL_FIELDS[field_id]
        )
    if field_id in OBSERVATION_ONLY_FIELDS:
        targets = _source_routes(name, NATIVE_RULE_MAPS)
        targets += MANUAL_CONFIG_ROUTES.get(name, ())
        return Route(
            "infrastructure_invariance",
            tuple(sorted(set(targets))),
            "observation-only measurement gate",
        )
    if field_id in INCOMPLETE_NATIVE_ROUTE_FIELDS:
        targets = _source_routes(name, NATIVE_RULE_MAPS)
        targets += MANUAL_CONFIG_ROUTES.get(name, ())
        return Route(
            "missing_native_route",
            tuple(sorted(set(targets))),
            INCOMPLETE_NATIVE_ROUTE_FIELDS[field_id],
        )
    if declaring_type == "Config":
        targets = _source_routes(name, NATIVE_RULE_MAPS)
        targets += MANUAL_CONFIG_ROUTES.get(name, ())
        if targets:
            return Route("mapped_native", tuple(sorted(set(targets))))
        return Route("missing_native_route")
    if declaring_type == "World":
        targets = WORLD_NATIVE_ROUTES.get(name, ())
        if targets:
            return Route("mapped_native", targets)
        return Route("missing_native_route")
    return Route("missing_native_route")


def _module_for(row: Mapping[str, Any]) -> str:
    declaring_type = str(row["declaring_type"])
    classification = str(row["classification"])
    name = str(row["field_name"])
    lowered = name.lower()

    if classification in POLICY_CLASSIFICATIONS:
        return "policy_seed"
    if classification in SHOCK_CLASSIFICATIONS:
        return "shocks"
    if classification in INFRA_CLASSIFICATIONS:
        return "numerics_and_observability"
    if declaring_type == "World":
        return "open_economy"
    if declaring_type != "Config":
        return "demography_and_households"
    if name in FIELD_MODULE_OVERRIDES:
        return FIELD_MODULE_OVERRIDES[name]
    if name in {
        "necessity_share0",
        "n_firm_share",
        "strat_mult_lo",
        "strat_mult_hi",
        "mpc_dispersion",
        "mpc_wealth_curvature",
    }:
        return "distribution_and_welfare"
    if name in SCALE_FIELDS or lowered.startswith(
        ("initial_", "d_", "p_", "inv_", "startup_", "genesis_")
    ):
        return "scale_and_genesis"
    if any(
        token in lowered
        for token in (
            "demograph",
            "fertility",
            "mortality",
            "marriage",
            "divorce",
            "relationship",
            "leave_home",
            "lifecycle",
            "guardian",
            "custody",
            "parent",
            "spouse",
            "union_",
        )
    ):
        return "demography_and_households"
    if (
        "housing" in lowered
        or "mortgage" in lowered
        or "rent" in lowered
        or "builder" in lowered
        or "land_" in lowered
    ):
        return "housing"
    if any(
        token in lowered
        for token in (
            "labor",
            "wage",
            "job_",
            "ladder",
            "suspension",
            "churn",
            "layoff",
            "efficiency",
            "reservation",
            "welfare_quit",
        )
    ):
        return "labor_market"
    if "energy" in lowered or lowered.startswith(("spr_", "soe_", "a_e", "kappa_e")):
        return "energy"
    if any(
        token in lowered
        for token in (
            "bank",
            "interbank",
            "deposit",
            "credit",
            "loan",
            "amort",
            "reserve",
            "run_",
            "kappa",
        )
    ):
        return "banking_and_credit"
    if any(
        token in lowered
        for token in (
            "bond",
            "equity",
            "share",
            "portfolio",
            "chartist",
            "fundamental",
            "valuation",
            "margin",
            "q_invest",
        )
    ):
        return "securities_and_capital_markets"
    if any(
        token in lowered
        for token in (
            "gov_",
            "government",
            "tax_",
            "benefit",
            "pension",
            "public_capital",
            "job_guarantee",
            "jg_",
        )
    ):
        return "government_and_public_sector"
    if any(
        token in lowered
        for token in ("tfp", "capital_", "delta_k", "lambda_i")
    ) or name in {"A", "a", "a_K", "v", "alpha", "K_firm0"}:
        return "production_and_technology"
    if any(token in lowered for token in ("firm", "entry", "bankrupt", "shell", "gibrat", "subscale", "switch_")):
        return "firms_and_industrial_dynamics"
    if any(
        token in lowered
        for token in (
            "necessity",
            "subsistence",
            "deprivation",
            "family_transfer",
            "n_firm_share",
            "consumption_strata",
        )
    ):
        return "distribution_and_welfare"
    return "consumption_prices_and_expectations"


def _experiment_role(row: Mapping[str, Any], route: Route) -> str:
    name = str(row["field_name"])
    classification = str(row["classification"])
    if route.status in {"excluded_policy", "excluded_shock"}:
        return route.status
    if route.status == "infrastructure_invariance":
        return "invariance_only"
    if route.status == "native_fixed":
        return "invariance_only"
    if route.status in {
        "derived",
        "superseded",
        "run_control",
        "planned_removal",
    }:
        return "excluded_non_treatment"
    if route.status == "missing_native_route":
        return "repair_before_experiment"
    if name in SCALE_FIELDS:
        return "scale_invariance"
    if classification == "structure":
        return "genesis_transient"
    return "causal_treatment"


def _baseline_value(
    row: Mapping[str, Any], config: Any, world: Mapping[str, Any]
) -> Any:
    declaring_type = str(row["declaring_type"])
    name = str(row["field_name"])
    if declaring_type == "Config" and hasattr(config, name):
        return getattr(config, name)
    if declaring_type == "World" and name in world:
        return world[name]
    return row.get("default")


def load_inventory_rows() -> list[dict[str, Any]]:
    payload = json.loads(CONFIG_INVENTORY_PATH.read_text(encoding="utf-8"))
    return list(payload["rows"])


def build_audit_inventory() -> dict[str, Any]:
    spec = NewGameSpec.default()
    config = spec.configs()[0]
    world = dict(spec.world)
    output_rows: list[dict[str, Any]] = []
    for raw in load_inventory_rows():
        route = _route_for(raw)
        output_rows.append(
            {
                "id": raw["id"],
                "declaring_type": raw["declaring_type"],
                "field_name": raw["field_name"],
                "annotation": raw["annotation"],
                "classification": raw["classification"],
                "module": _module_for(raw),
                "declared_default": raw.get("default"),
                "playable_baseline": _baseline_value(raw, config, world),
                "route_status": route.status,
                "native_targets": list(route.targets),
                "route_note": route.note,
                "experiment_role": _experiment_role(raw, route),
                "status": raw["status"],
            }
        )

    route_counts = Counter(row["route_status"] for row in output_rows)
    role_counts = Counter(row["experiment_role"] for row in output_rows)
    module_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in output_rows:
        module_counts[row["module"]][row["experiment_role"]] += 1

    module_state: dict[str, dict[str, Any]] = {}
    for module, expected in MODULE_CHECKS.items():
        actual = {name: getattr(config, name) for name in expected}
        module_state[module] = {
            "enabled": actual == dict(expected),
            "expected": dict(expected),
            "actual": actual,
        }
    module_state["open_economy"] = {
        "enabled": all(world.get(name) == value for name, value in WORLD_MODULE_CHECKS.items()),
        "expected": dict(WORLD_MODULE_CHECKS),
        "actual": {name: world.get(name) for name in WORLD_MODULE_CHECKS},
    }

    return {
        "schema_version": "config-causality-audit-v1",
        "source_inventory": str(CONFIG_INVENTORY_PATH.relative_to(REPOSITORY_ROOT)),
        "field_count": len(output_rows),
        "route_counts": dict(sorted(route_counts.items())),
        "experiment_role_counts": dict(sorted(role_counts.items())),
        "module_counts": {
            module: dict(sorted(counts.items()))
            for module, counts in sorted(module_counts.items())
        },
        "module_state": module_state,
        "all_required_modules_enabled": all(
            value["enabled"] for value in module_state.values()
        ),
        "rows": output_rows,
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Config causality audit inventory",
        "",
        f"Fields: **{payload['field_count']}**.",
        f"All required playable modules enabled: **{str(payload['all_required_modules_enabled']).lower()}**.",
        "",
        "## Route status",
        "",
        "| Status | Fields |",
        "|---|---:|",
    ]
    for name, count in payload["route_counts"].items():
        lines.append(f"| `{name}` | {count} |")
    lines.extend(
        [
            "",
            "## Experiment roles by module",
            "",
            "| Module | Causal | Scale | Genesis | Invariance | Repair |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for module, counts in payload["module_counts"].items():
        lines.append(
            "| {module} | {causal} | {scale} | {genesis} | {invariance} | {repair} |".format(
                module=module,
                causal=counts.get("causal_treatment", 0),
                scale=counts.get("scale_invariance", 0),
                genesis=counts.get("genesis_transient", 0),
                invariance=counts.get("invariance_only", 0),
                repair=counts.get("repair_before_experiment", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Missing native routes",
            "",
            "These fields must be wired, removed, or explicitly fixed before a dynamic elasticity result is meaningful.",
            "",
            "| Module | Field | Classification | Baseline |",
            "|---|---|---|---:|",
        ]
    )
    for row in payload["rows"]:
        if row["route_status"] != "missing_native_route":
            continue
        lines.append(
            f"| {row['module']} | `{row['id']}` | {row['classification']} | `{row['playable_baseline']}` |"
        )
    lines.append("")
    return "\n".join(lines)
