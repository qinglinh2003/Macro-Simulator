"""Treatment contracts for the immutable Config causality audit.

The registry deliberately covers the entire immutable surface.  A generated
suggestion is not an approved experiment: only ``screening_ready`` contracts
may enter the expensive native batch.  This prevents a generic percentage
change from being mistaken for an economically reviewed intervention.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Mapping

from macro_sim.diagnostics.config_causality import build_audit_inventory


DIRECTION_VALUES = frozenset(
    {
        "increase",
        "decrease",
        "nonzero",
        "ambiguous",
        "invariance",
        "washout",
    }
)


MODULE_PRIMARY_METRICS: Mapping[str, tuple[str, ...]] = {
    "production_and_technology": (
        "metric.economy.na.real_gdp_per_capita",
        "metric.economy.real_output",
        "metric.source.m4.aggregate_capital",
        "metric.source.m4.fixed_capital_formation_real",
        "metric.source.m4.capital_output_real",
        "metric.economy.labor_sector_capital_fte",
        "metric.economy.avg_wage",
        "metric.economy.price_index",
        "metric.economy.unemployment_rate",
        "metric.source.m6.primary_equity_raised",
    ),
    "firms_and_industrial_dynamics": (
        "metric.economy.firm_count_c",
        "metric.economy.firm_count_k",
        "metric.source.m6.firm_births",
        "metric.source.m6.firm_exits",
        "metric.source.m6.firm_defaults",
        "metric.source.m6.sector_switches",
        "metric.source.m6.sector_retool_capital",
        "metric.source.m4.firm_profit",
        "metric.economy.avg_markup",
        "metric.economy.firm_size_gini_output",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
    ),
    "consumption_prices_and_expectations": (
        "metric.economy.na.household_consumption_real",
        "metric.analysis.goods_transaction_price_proxy",
        "metric.economy.inventory_to_sales",
        "metric.economy.avg_markup",
        "metric.economy.price_index",
        "metric.economy.inflation",
        "metric.economy.real_output",
        "metric.economy.unemployment_rate",
        "metric.economy.poverty_rate",
    ),
    "labor_market": (
        "metric.source.m7.participation_rate",
        "metric.source.m7.employed_fte",
        "metric.source.m7.hires",
        "metric.source.m7.separations",
        "metric.source.m7.vacancies",
        "metric.economy.unemployment_rate",
        "metric.economy.underemployed_share",
        "metric.economy.avg_wage",
        "metric.economy.real_output",
    ),
    "distribution_and_welfare": (
        "metric.economy.poverty_rate",
        "metric.economy.income_gini",
        "metric.economy.hh_wealth_gini_incl_equity",
        "metric.economy.wage_p90_p10_ratio",
        "metric.economy.savings_rate",
        "metric.economy.welfare_log",
        "metric.economy.na.household_consumption_real",
    ),
    "open_economy": (
        "metric.source.m9.country.exports_volume",
        "metric.source.m9.country.imports_volume",
        "metric.source.m9.country.current_account",
        "metric.source.m9.country.exchange_rate",
        "metric.source.m9.country.net_foreign_assets",
        "metric.source.m9.country.capital_flow",
        "metric.source.m9.country.migrant_stock_hosted",
        "metric.economy.real_output",
    ),
}


@dataclass(frozen=True, slots=True)
class TreatmentContract:
    field_id: str
    field_name: str
    scope: str
    module: str
    experiment_role: str
    route_status: str
    baseline_value: Any
    status: str
    treatment_kind: str
    treatment_values: tuple[Any, ...]
    primary_metrics: tuple[str, ...]
    expected_directions: Mapping[str, str]
    direction_statistics: Mapping[str, str]
    horizon_days: int
    countries: int
    activation_scenario: str
    rationale: str


def _suggested_numeric_levels(value: int | float) -> tuple[int | float, ...]:
    """Return non-authoritative, type-preserving review suggestions."""
    if isinstance(value, int):
        if value <= 0:
            return (1,)
        low = max(0, round(value * 0.75))
        high = max(low + 1, round(value * 1.25))
        return tuple(candidate for candidate in (low, high) if candidate != value)
    number = float(value)
    if number > 0.0:
        return (number * 0.75, number * 1.25)
    if number < 0.0:
        return (number * 1.25, number * 0.75)
    return (-0.01, 0.01)


def _draft_treatment(row: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    baseline = row["playable_baseline"]
    annotation = str(row["annotation"])
    if annotation == "bool" and isinstance(baseline, bool):
        return "boolean_toggle", (not baseline,)
    if annotation in {"float", "int"} and isinstance(baseline, (int, float)):
        return "numeric_levels", _suggested_numeric_levels(baseline)
    if row["field_name"] == "bank_assignment":
        return "categorical_alternative", (
            "size" if baseline == "random" else "random",
        )
    if row["field_name"] == "simulation_start_date":
        start = date.fromisoformat(str(baseline))
        return "calendar_shift", (start.replace(year=start.year + 10).isoformat(),)
    return "manual_review", ()


def _default_status(row: Mapping[str, Any]) -> str:
    role = str(row["experiment_role"])
    if role == "repair_before_experiment":
        return "blocked_native_route"
    if role in {"excluded_policy", "excluded_shock", "excluded_non_treatment"}:
        return role
    if role == "invariance_only":
        return "invariance_review_required"
    if role == "scale_invariance":
        return "scale_contract_required"
    if role == "genesis_transient":
        return "washout_contract_required"
    return "economic_review_required"


def _production_contracts() -> Mapping[str, Mapping[str, Any]]:
    output = "metric.economy.na.real_gdp_per_capita"
    capital = "metric.source.m4.aggregate_capital"
    investment = "metric.source.m4.fixed_capital_formation_real"
    return {
        "config.a": {
            "status": "excluded_non_treatment",
            "values": (),
            "directions": {},
            "rationale": "The product uses Cobb-Douglas consumption firms, where Hicks-neutral A replaces the linear-productivity compatibility input.",
        },
        "config.alpha": {
            "status": "screening_ready",
            "values": (0.25, 0.35),
            "directions": {capital: "nonzero", output: "ambiguous"},
            "rationale": "Capital income share changes factor substitution and distribution; the equilibrium output sign is not imposed.",
        },
        "config.capital_firm_entry": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.source.m6.firm_births": "decrease",
                "metric.economy.firm_count_k": "decrease",
            },
            "rationale": "A capability ablation should remove endogenous capital-firm births without disabling incumbent production.",
        },
        "config.capital_market": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.economy.equity_market_cap": "decrease",
                "metric.source.m6.primary_equity_raised": "decrease",
            },
            "rationale": "Capability ablation identifies the equity-finance channel and its real-economy spillovers.",
        },
        "config.capital_rationed_signal": {
            "status": "activation_scenario_required",
            "values": (False,),
            "directions": {investment: "nonzero"},
            "statistics": {investment: "cumulative"},
            "activation": "positive_capital_gap",
            "rationale": "Halving opening consumption-firm capital creates positive investment orders and unmet capital demand, allowing the expectations signal to affect subsequent capital-goods production.",
        },
        "config.case-a": {
            "status": "screening_ready",
            "values": (0.1362705873, 0.2044058809),
            "directions": {
                output: "increase",
                "metric.economy.price_index": "decrease",
            },
            "rationale": "Hicks-neutral consumption-sector productivity should raise real capacity and lower marginal cost, holding other structural inputs fixed.",
        },
        "config.case-a_k": {
            "status": "screening_ready",
            "values": (2.304, 3.456),
            "directions": {
                "metric.source.m4.capital_output_real": "increase",
                investment: "increase",
            },
            "rationale": "Capital-goods labor productivity should expand machinery supply and relax investment bottlenecks.",
        },
        "config.case-delta_k": {
            "status": "screening_ready",
            "values": (0.0001824, 0.0002736),
            "directions": {capital: "decrease", investment: "increase"},
            "rationale": "Faster depreciation destroys the installed stock while raising replacement demand; both legs must be visible.",
        },
        "config.case-k_firm0": {
            "status": "screening_ready",
            "values": (5840.0, 8760.0),
            "directions": {capital: "washout"},
            "rationale": "Opening capital is a genesis condition: the initial stock must move proportionally and its normalized effect should decay.",
        },
        "config.case-lambda_i": {
            "status": "activation_scenario_required",
            "values": (0.00152, 0.00228),
            "directions": {investment: "nonzero"},
            "statistics": {investment: "cumulative"},
            "activation": "positive_capital_gap",
            "rationale": "Investment adjustment speed only binds when desired capital exceeds the installed stock; the baseline initially sits on its replacement-only branch.",
        },
        "config.lambda_issue": {
            "status": "screening_ready",
            "values": (0.1, 0.3),
            "directions": {
                "metric.source.m6.primary_equity_raised": "increase"
            },
            "statistics": {
                "metric.source.m6.primary_equity_raised": "first_window_mean"
            },
            "activation": "neutral_baseline_q_above_one",
            "rationale": "The audited product baseline has Tobin's q above one and positive daily issuance, so the issuance-intensity channel is identified without a synthetic stress scenario.",
        },
        "config.tfp_drift_rate": {
            "status": "screening_ready",
            "values": (0.006, 0.024),
            "directions": {output: "increase"},
            "horizon_days": 1825,
            "rationale": "A higher annual TFP trend must steepen medium-run real output growth rather than create a one-day level jump.",
        },
        "config.v": {
            "status": "screening_ready",
            "values": (730.0, 1095.0),
            "directions": {capital: "increase", investment: "increase"},
            "rationale": "The desired capital-output ratio raises desired installed capital and the investment needed to approach it.",
        },
    }


def _firm_contracts() -> Mapping[str, Mapping[str, Any]]:
    births = "metric.source.m6.firm_births"
    exits = "metric.source.m6.firm_exits"
    capital_firms = "metric.economy.firm_count_k"
    switches = "metric.source.m6.sector_switches"
    retool = "metric.source.m6.sector_retool_capital"
    return {
        "config.demand_e_firm0": {
            "status": "screening_ready",
            "values": (5.0, 7.5),
            "directions": {
                "metric.source.m8.energy.production": "washout",
            },
            "horizon_days": 1825,
            "rationale": "Opening expected energy demand is a genesis seed; it must move early production and then lose influence.",
        },
        "config.entry_beta": {
            "status": "screening_ready",
            "values": (0.2, 0.6),
            "directions": {births: "increase"},
            "statistics": {births: "cumulative"},
            "rationale": "Entry sensitivity scales the number of consumption-firm entrants generated by a positive median excess return.",
        },
        "config.entry_hurdle": {
            "status": "screening_ready",
            "values": (0.0, 0.000268),
            "directions": {births: "decrease"},
            "statistics": {births: "cumulative"},
            "rationale": "A higher required return should suppress consumption-firm entry, holding profitability and the policy rate fixed.",
        },
        "config.entry_max": {
            "status": "activation_scenario_required",
            "values": (1, 6),
            "directions": {births: "increase"},
            "statistics": {births: "cumulative"},
            "activation": "high_consumption_entry_pressure",
            "rationale": "The per-day cap is exactly silent in the neutral one-year screen; a shared high entry sensitivity and zero hurdle force desired entry above the cap while preserving the audited limit.",
        },
        "config.firm_dynamics": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {births: "decrease", exits: "decrease"},
            "statistics": {births: "cumulative", exits: "cumulative"},
            "rationale": "The master capability ablation must remove endogenous firm births and exits; Config validity also closes the dependent founder-equity capability, so broad spillovers are interpreted as a package rather than a pure dynamics effect.",
        },
        "config.firm_full_pnl": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {
                "metric.source.m5.loan_interest_paid": "nonzero",
                "metric.source.m4.firm_profit": "nonzero",
            },
            "statistics": {
                "metric.source.m5.loan_interest_paid": "cumulative",
                "metric.source.m4.firm_profit": "cumulative",
            },
            "rationale": "The full cash-basis income statement services debt before settlement; disabling it tests whether that phase ordering changes realized interest and firm profit flows.",
        },
        "config.firm_subscale_exit": {
            "status": "screening_ready",
            "values": (False,),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "rationale": "Disabling viability exits should reduce total firm exits after the grace period.",
        },
        "config.k_entry_demand": {
            "status": "screening_ready",
            "values": (1.0, 5.0),
            "directions": {capital_firms: "decrease"},
            "rationale": "A higher sector-wide labor-demand threshold should make capital-firm spin-offs less frequent.",
        },
        "config.k_entry_hazard": {
            "status": "screening_ready",
            "values": (1.0 / 120.0, 1.0 / 30.0),
            "directions": {capital_firms: "increase"},
            "rationale": "Conditional on sector capacity pressure, a higher daily spin-off hazard should raise the capital-firm stock.",
        },
        "config.mu_firm0": {
            "status": "screening_ready",
            "values": (0.15, 0.25),
            "directions": {"metric.economy.avg_markup": "washout"},
            "horizon_days": 1825,
            "rationale": "Opening markup is a quote seed; it should affect early prices and margins but converge under endogenous price adjustment.",
        },
        "config.shell_exit_ticks": {
            "status": "activation_scenario_required",
            "values": (180, 548),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "activation": "idle_consumption_firms",
            "horizon_days": 730,
            "rationale": "A shared zero-capital, zero-inventory, no-investment setup creates idle shells while disabling the competing subscale-exit rule.",
        },
        "config.subscale_exit_hazard": {
            "status": "screening_ready",
            "values": (1.0 / 180.0, 1.0 / 45.0),
            "directions": {exits: "increase"},
            "statistics": {exits: "cumulative"},
            "rationale": "After the viability grace period, a higher daily hazard should increase subscale exits.",
        },
        "config.subscale_grace_days": {
            "status": "screening_ready",
            "values": (90, 365),
            "directions": {exits: "decrease"},
            "statistics": {exits: "cumulative"},
            "rationale": "A longer continuous-below-viability grace period should delay and reduce exits over a fixed horizon.",
        },
        "config.subscale_viability_workers": {
            "status": "screening_ready",
            "values": (0.05, 2.0),
            "directions": {exits: "increase"},
            "statistics": {exits: "cumulative"},
            "rationale": "A higher minimum viable labor demand classifies more firms as subscale and should increase exits.",
        },
        "config.switch_hazard": {
            "status": "activation_scenario_required",
            "values": (0.005, 0.02),
            "directions": {switches: "increase"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_hazard",
            "rationale": "A shared low return gap and short pressure window create eligible firms while preserving the audited switch hazard.",
        },
        "config.switch_pressure_days": {
            "status": "activation_scenario_required",
            "values": (2, 10),
            "directions": {switches: "decrease"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_pressure",
            "rationale": "A shared low return gap and higher hazard preserve the audited pressure duration; 2 and 10 days identify the mechanism after 30 and 120 days proved silent because return leadership resets too often.",
        },
        "config.switch_retool_loss": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.15),
            "directions": {retool: "increase"},
            "statistics": {retool: "cumulative"},
            "activation": "sector_returns_retool",
            "rationale": "A common switching regime identifies the physical capital destroyed per retool event.",
        },
        "config.switch_return_gap": {
            "status": "activation_scenario_required",
            "values": (0.0, 0.10),
            "directions": {switches: "decrease"},
            "statistics": {switches: "cumulative"},
            "activation": "sector_returns_gap",
            "rationale": "A short pressure window and higher hazard expose how the required relative-return gap governs eligibility.",
        },
        "config.w_firm0": {
            "status": "screening_ready",
            "values": (0.8, 1.2),
            "directions": {"metric.economy.avg_wage": "washout"},
            "horizon_days": 1825,
            "rationale": "Opening posted wage should move initial labor-market quotes and then converge under endogenous wage adjustment.",
        },
    }


def _consumption_contracts() -> Mapping[str, Mapping[str, Any]]:
    consumption = "metric.economy.na.household_consumption_real"
    inventory = "metric.economy.inventory_to_sales"
    markup = "metric.economy.avg_markup"
    inflation = "metric.economy.inflation"
    return {
        "config.alpha1": {
            "status": "screening_ready",
            "values": (0.90, 0.99),
            "directions": {consumption: "increase"},
            "rationale": "A higher marginal propensity out of expected income should raise household consumption demand, holding income, wealth, taxes, and credit rules fixed.",
        },
        "config.alpha2": {
            "status": "screening_ready",
            "values": (1.0e-6, 5.0e-4),
            "directions": {consumption: "increase"},
            "rationale": "A higher propensity out of liquid wealth should raise consumption for a given expected income and opening balance sheet.",
        },
        "config.consumption_rationed_signal": {
            "status": "activation_scenario_required",
            "values": (True,),
            "directions": {inventory: "increase"},
            "activation": "opening_consumption_stockout",
            "rationale": "A shared opening stockout exposes whether unfilled consumer and government orders enter seller demand expectations and raise the subsequent inventory response; output, employment, prices, and realized consumption remain unconstrained trade-offs.",
        },
        "config.eta": {
            "status": "screening_ready",
            "values": (3.35e-4, 1.34e-3),
            "directions": {markup: "nonzero"},
            "rationale": "Markup adjustment speed must change the response of price-cost margins to inventory imbalance; the equilibrium sign depends on whether shortages or excess stocks dominate.",
        },
        "config.inventory_gap_close": {
            "status": "screening_ready",
            "values": (0.025, 0.10),
            "directions": {inventory: "nonzero"},
            "rationale": "The fraction of the target inventory gap closed each day should alter realized inventory coverage and production volatility without changing the long-run inventory target itself.",
        },
        "config.lambda_d": {
            "status": "screening_ready",
            "values": (0.0019, 0.0076),
            "directions": {inventory: "nonzero"},
            "rationale": "Faster seller demand learning should change the inventory and sales path after daily demand surprises; its long-run level sign is not imposed.",
        },
        "config.lambda_y": {
            "status": "screening_ready",
            "values": (0.0038, 0.0152),
            "directions": {consumption: "nonzero"},
            "rationale": "Faster permanent-income updating should change consumption when realized labor and transfer income differs from prior expectations.",
        },
        "config.mu_max": {
            "status": "activation_scenario_required",
            "values": (0.20, 0.22),
            "directions": {markup: "increase"},
            "activation": "markup_ceiling_pressure",
            "rationale": "A higher markup ceiling should permit higher price-cost margins when shortage pressure would otherwise bind the cap.",
        },
        "config.mu_min": {
            "status": "activation_scenario_required",
            "values": (0.18, 0.20),
            "directions": {markup: "increase"},
            "activation": "markup_floor_pressure",
            "rationale": "A higher markup floor should prevent competitive or excess-inventory pressure from compressing margins below the configured bound.",
        },
        "config.phi": {
            "status": "screening_ready",
            "values": (10.5, 17.5),
            "directions": {inventory: "increase"},
            "rationale": "A higher target number of inventory days should raise inventory coverage and create a larger working-stock buffer against demand surprises.",
        },
        "config.search_m": {
            "status": "screening_ready",
            "values": (2, 8),
            "directions": {
                "metric.analysis.goods_transaction_price_proxy": "nonzero"
            },
            "rationale": "Comparing more sampled sellers increases consumer price transparency. The partial-equilibrium selection effect favors cheaper offers, but inventory depletion, seller learning, and the current mixed household/sector price proxy leave the long-run equilibrium sign unconstrained. The ordinary range stops at eight because larger samples add little measured benefit while increasing matching cost materially.",
        },
        "config.theta_price": {
            "status": "screening_ready",
            "values": (0.00185, 0.00740),
            "directions": {inflation: "nonzero"},
            "statistics": {inflation: "post_burnin_volatility"},
            "rationale": "The daily Calvo repricing probability should alter inflation dynamics and the speed at which desired markups pass into posted prices; the volatility sign is an empirical model result.",
        },
    }


CURATED_CONTRACTS = {
    **_production_contracts(),
    **_firm_contracts(),
    **_consumption_contracts(),
}


def build_contract_registry() -> dict[str, Any]:
    inventory = build_audit_inventory()
    contracts: list[TreatmentContract] = []
    for row in inventory["rows"]:
        treatment_kind, suggested_values = _draft_treatment(row)
        override = CURATED_CONTRACTS.get(str(row["id"]), {})
        directions = dict(override.get("directions", {}))
        invalid = set(directions.values()) - DIRECTION_VALUES
        if invalid:
            raise ValueError(f"invalid expected directions for {row['id']}: {invalid}")
        module_metrics = tuple(
            override.get(
                "metrics", MODULE_PRIMARY_METRICS.get(str(row["module"]), ())
            )
        )
        primary_metrics = tuple(
            dict.fromkeys((*module_metrics, *directions.keys()))
        )
        contract = TreatmentContract(
            field_id=str(row["id"]),
            field_name=str(row["field_name"]),
            scope=("world" if row["declaring_type"] == "World" else "root"),
            module=str(row["module"]),
            experiment_role=str(row["experiment_role"]),
            route_status=str(row["route_status"]),
            baseline_value=row["playable_baseline"],
            status=str(override.get("status", _default_status(row))),
            treatment_kind=treatment_kind,
            treatment_values=tuple(override.get("values", suggested_values)),
            primary_metrics=primary_metrics,
            expected_directions=directions,
            direction_statistics=dict(override.get("statistics", {})),
            horizon_days=int(override.get("horizon_days", 365)),
            countries=(3 if row["declaring_type"] == "World" else 1),
            activation_scenario=str(override.get("activation", "neutral_baseline")),
            rationale=str(
                override.get(
                    "rationale",
                    "Automatically generated treatment suggestion; economic review is required before execution.",
                )
            ),
        )
        if contract.status in {
            "screening_ready",
            "activation_scenario_required",
        }:
            if contract.route_status != "mapped_native":
                raise ValueError(f"ready contract lacks a native route: {contract.field_id}")
            if not contract.treatment_values or not contract.primary_metrics:
                raise ValueError(f"ready contract is incomplete: {contract.field_id}")
            if set(contract.direction_statistics) - set(contract.expected_directions):
                raise ValueError(
                    f"direction statistic lacks an expectation: {contract.field_id}"
                )
        contracts.append(contract)

    status_counts: dict[str, int] = {}
    for contract in contracts:
        status_counts[contract.status] = status_counts.get(contract.status, 0) + 1
    return {
        "schema_version": "config-treatment-contracts-v1",
        "field_count": len(contracts),
        "status_counts": dict(sorted(status_counts.items())),
        "contracts": [asdict(contract) for contract in contracts],
    }


def screening_contracts(*, module: str | None = None) -> tuple[TreatmentContract, ...]:
    payload = build_contract_registry()
    output = []
    for raw in payload["contracts"]:
        if raw["status"] != "screening_ready":
            continue
        if module is not None and raw["module"] != module:
            continue
        output.append(TreatmentContract(**raw))
    return tuple(output)


def activation_contracts(*, module: str | None = None) -> tuple[TreatmentContract, ...]:
    """Return reviewed contracts that require a shared activation scenario."""
    payload = build_contract_registry()
    output = []
    for raw in payload["contracts"]:
        if raw["status"] != "activation_scenario_required":
            continue
        if module is not None and raw["module"] != module:
            continue
        output.append(TreatmentContract(**raw))
    return tuple(output)
