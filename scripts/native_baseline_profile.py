"""Run a large native no-shock baseline and summarize its macro trajectory."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any

sys.meta_path = [
    finder
    for finder in sys.meta_path
    if finder.__class__.__name__ != "ScikitBuildRedirectingFinder"
]

from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.native_backend import NativeSimulationSession


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"non-finite diagnostic value: {value!r}")
    return number


def _series(rows: list[dict[str, Any]], metric_id: str) -> list[float]:
    return [_finite(row[metric_id]) for row in rows]


def _window_mean(values: list[float], start: int, stop: int) -> float:
    return _mean(values[max(0, start) : min(len(values), stop)])


def _relative_change(first: float, last: float) -> float:
    return last / first - 1.0 if abs(first) > 1.0e-12 else 0.0


def _build_spec(
    population: int,
    days: int,
    seed: int,
    countries: int = 1,
) -> NewGameSpec:
    raw = NewGameSpec.default().to_dict()
    raw["duration"] = days
    raw["seed"] = seed
    if not 1 <= countries <= len(raw["countries"]):
        raise ValueError("countries exceeds the built-in profile count")
    raw["countries"] = raw["countries"][:countries]
    for country in raw["countries"]:
        country["overrides"] = dict(country.get("overrides", {}))
        country["overrides"].update(
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
    return NewGameSpec.from_mapping(raw)


def _parse_config_override(expression: str) -> tuple[str, Any]:
    key, separator, raw_value = expression.partition("=")
    key = key.strip()
    if not separator or not key:
        raise argparse.ArgumentTypeError(
            "config overrides must use FIELD=JSON_VALUE"
        )
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            f"invalid JSON value in config override: {error.msg}"
        ) from error
    return key, value


def _history_rows(
    session: NativeSimulationSession,
    economy_id: int = 0,
) -> list[dict[str, Any]]:
    bounds = session.history_bounds()
    cursor = int(bounds["oldest_sequence"])
    stop = int(bounds["next_sequence"])
    rows: list[dict[str, Any]] = []
    while cursor < stop:
        page = session.maintained_history_page(
            cursor, min(512, stop - cursor)
        )
        frames = list(page["frames"])
        for frame in frames:
            if int(frame["tick"]) <= 0:
                continue
            row = dict(frame["economies"][economy_id])
            row["_tick"] = int(frame["tick"])
            rows.append(row)
        cursor = int(page["next_sequence"])
    return rows


def _all_probe_rows(
    session: NativeSimulationSession,
    kind: str,
    economy_id: int = 0,
) -> list[dict[str, Any]]:
    after_id = 0
    rows: list[dict[str, Any]] = []
    while True:
        page = session.probe_page(
            kind,
            economy_id=economy_id,
            after_id=after_id,
            maximum_rows=512,
        )
        batch = [dict(row) for row in page["rows"]]
        rows.extend(batch)
        if not page["has_more"]:
            return rows
        next_after_id = int(page["next_after_id"])
        if next_after_id <= after_id:
            raise RuntimeError(f"{kind} probe cursor did not advance")
        after_id = next_after_id


def _firm_sector_summary(
    session: NativeSimulationSession,
    economy_id: int = 0,
) -> dict[str, dict[str, float | int]]:
    names = {0: "consumption", 1: "capital", 2: "energy", 3: "construction"}
    output: dict[str, dict[str, float | int]] = {}
    for row in _all_probe_rows(session, "firms", economy_id):
        if not row["active"]:
            continue
        sector = names[int(row["sector"])]
        aggregate = output.setdefault(
            sector,
            {
                "firms": 0,
                "cash": 0.0,
                "debt": 0.0,
                "inventory": 0.0,
                "physical_capital": 0.0,
                "posted_price_mean": 0.0,
                "posted_wage_mean": 0.0,
                "markup_mean": 0.0,
                "markup_max": 0.0,
                "expected_demand": 0.0,
                "previous_sales": 0.0,
                "previous_hires": 0.0,
                "employees": 0,
                "zero_sales_firms": 0,
                "zero_hire_firms": 0,
            },
        )
        aggregate["firms"] += 1
        aggregate["cash"] += _finite(row["cash"])
        aggregate["debt"] += _finite(row["debt"])
        aggregate["inventory"] += _finite(row["goods_inventory"])
        aggregate["physical_capital"] += _finite(row["physical_capital"])
        aggregate["posted_price_mean"] += _finite(row["posted_price"])
        aggregate["posted_wage_mean"] += _finite(row["posted_wage"])
        aggregate["markup_mean"] += _finite(row["markup"])
        aggregate["markup_max"] = max(
            float(aggregate["markup_max"]), _finite(row["markup"])
        )
        aggregate["expected_demand"] += _finite(row["demand_expected"])
        aggregate["previous_sales"] += _finite(row["previous_sales"])
        aggregate["previous_hires"] += _finite(row["previous_hires"])
        aggregate["employees"] += len(row["employee_ids"])
        aggregate["zero_sales_firms"] += (
            _finite(row["previous_sales"]) <= 1.0e-12
        )
        aggregate["zero_hire_firms"] += (
            _finite(row["previous_hires"]) <= 1.0e-12
        )
    for aggregate in output.values():
        count = max(1, int(aggregate["firms"]))
        aggregate["posted_price_mean"] /= count
        aggregate["posted_wage_mean"] /= count
        aggregate["markup_mean"] /= count
    return output


def _bank_summary(
    session: NativeSimulationSession,
    economy_id: int = 0,
) -> dict[str, Any]:
    rows = _all_probe_rows(session, "banks", economy_id)
    alive = [row for row in rows if row["alive"]]
    inactive = [row for row in rows if not row["alive"]]
    resolved = [row for row in rows if row["resolved"]]
    stored_records = len(rows)
    alive_capital = [_finite(row["closing_capital"]) for row in alive]
    alive_loans = [_finite(row["loan_principal"]) for row in alive]
    alive_reserves = [_finite(row["reserves"]) for row in alive]
    inactive_reserves = [_finite(row["reserves"]) for row in inactive]
    negative_reserve_banks = [
        {
            "id": int(row["id"]),
            "cash": _finite(row["cash"]),
            "reserves": _finite(row["reserves"]),
            "loan_principal": _finite(row["loan_principal"]),
            "opening_capital": _finite(row["opening_capital"]),
            "closing_capital": _finite(row["closing_capital"]),
            "deposit_interest_arrears": _finite(
                row["deposit_interest_arrears"]
            ),
        }
        for row in alive
        if _finite(row["reserves"]) < -1.0e-9
    ]
    return {
        "stored_records": stored_records,
        "alive": len(alive),
        "alive_ids": [int(row["id"]) for row in alive],
        "inactive_inferred": max(0, stored_records - len(alive)),
        "resolved": len(resolved),
        "resolved_ids": [int(row["id"]) for row in resolved],
        "alive_capital_total": sum(alive_capital),
        "alive_capital_min": min(alive_capital, default=0.0),
        "alive_capital_median": (
            statistics.median(alive_capital) if alive_capital else 0.0
        ),
        "alive_loan_principal_total": sum(alive_loans),
        "alive_loan_principal_max": max(alive_loans, default=0.0),
        "alive_without_loans": sum(
            principal <= 1.0e-12 for principal in alive_loans
        ),
        "alive_reserve_total": sum(alive_reserves),
        "alive_reserve_min": min(alive_reserves, default=0.0),
        "negative_reserve_banks": negative_reserve_banks,
        "inactive_reserve_total": sum(inactive_reserves),
        "inactive_reserve_max_abs": max(
            (abs(value) for value in inactive_reserves),
            default=0.0,
        ),
        "resolved_capital_total": sum(
            _finite(row["closing_capital"]) for row in resolved
        ),
    }


def _job_summary(
    session: NativeSimulationSession,
    economy_id: int = 0,
) -> dict[str, Any]:
    sector_names = {
        0: "consumption",
        1: "capital",
        2: "energy",
        3: "construction",
    }
    firm_sectors = {
        int(row["id"]): sector_names[int(row["sector"])]
        for row in _all_probe_rows(session, "firms", economy_id)
        if row["active"]
    }
    summary: dict[str, Any] = {
        "active_contracts": 0,
        "suspended_contracts": 0,
        "secondary_contracts": 0,
        "active_hours": 0.0,
        "suspended_hours": 0.0,
        "by_sector": {},
    }
    for row in _all_probe_rows(session, "jobs", economy_id):
        if not row["active"]:
            continue
        suspended = bool(row["suspended"])
        hours = _finite(row["hours"])
        sector = firm_sectors.get(int(row["firm_id"]), "inactive_firm")
        sector_summary = summary["by_sector"].setdefault(
            sector,
            {
                "active_contracts": 0,
                "suspended_contracts": 0,
                "active_hours": 0.0,
                "suspended_hours": 0.0,
            },
        )
        summary["active_contracts"] += 1
        summary["secondary_contracts"] += bool(row["secondary"])
        sector_summary["active_contracts"] += 1
        if suspended:
            summary["suspended_contracts"] += 1
            summary["suspended_hours"] += hours
            sector_summary["suspended_contracts"] += 1
            sector_summary["suspended_hours"] += hours
        else:
            summary["active_hours"] += hours
            sector_summary["active_hours"] += hours
    return summary


def _summarize(
    rows: list[dict[str, Any]],
    *,
    elapsed_seconds: float,
    population: int,
    seed: int,
    session: NativeSimulationSession,
    economy_id: int = 0,
) -> dict[str, Any]:
    if not rows:
        raise RuntimeError("native baseline produced no retained metric frames")

    real_output = _series(rows, "metric.source.m4.real_output")
    population_series = _series(rows, "metric.source.m7.population")
    real_output_pc = [
        output / max(1.0, persons)
        for output, persons in zip(real_output, population_series, strict=True)
    ]
    unemployment = _series(rows, "metric.source.m7.unemployment_rate")
    m4_unemployment = _series(
        rows, "metric.source.m4.unemployment_rate"
    )
    participation = _series(rows, "metric.source.m7.participation_rate")
    vacancies = _series(rows, "metric.source.m7.vacancies")
    labor_supply = _series(rows, "metric.source.m7.labor_supply")
    suspended = _series(rows, "metric.source.m7.suspended")
    employed_fte = _series(rows, "metric.source.m7.employed_fte")
    employed_heads = _series(rows, "metric.source.m7.employed_heads")
    unemployed = _series(rows, "metric.source.m7.unemployment")
    underemployed_heads = _series(
        rows, "metric.source.m7.underemployed_heads"
    )
    underemployment_hours = _series(
        rows, "metric.source.m7.underemployment_hours"
    )
    nonsearching = _series(rows, "metric.source.m7.nonsearching")
    hires = _series(rows, "metric.source.m7.hires")
    separations = _series(rows, "metric.source.m7.separations")
    churn_separations = _series(
        rows, "metric.source.m7.churn_separations"
    )
    demand_layoff_separations = _series(
        rows, "metric.source.m7.demand_layoff_separations"
    )
    cash_layoff_separations = _series(
        rows, "metric.source.m7.cash_layoff_separations"
    )
    firm_exit_separations = _series(
        rows, "metric.source.m7.firm_exit_separations"
    )
    death_separations = _series(
        rows, "metric.source.m7.death_separations"
    )
    retirement_separations = _series(
        rows, "metric.source.m7.retirement_separations"
    )
    welfare_quits = _series(rows, "metric.source.m7.welfare_quits")
    suspensions_flow = _series(
        rows, "metric.source.m7.suspensions_flow"
    )
    recalls = _series(rows, "metric.source.m7.recalls")
    job_to_job_moves = _series(
        rows, "metric.source.m7.job_to_job_moves"
    )
    mean_wage = _series(rows, "metric.source.m7.mean_hourly_wage")
    capital = _series(rows, "metric.source.m4.aggregate_capital")
    investment = _series(
        rows, "metric.source.m4.fixed_capital_formation_real"
    )
    price = _series(rows, "metric.source.m4.price_index")
    energy_requested = _series(
        rows, "metric.source.m8.energy.requested_total"
    )
    energy_opening = _series(
        rows, "metric.source.m8.energy.opening_supply"
    )
    energy_unfilled = _series(rows, "metric.source.m8.energy.unfilled")
    energy_price = _series(
        rows, "metric.source.m8.energy.transaction_price"
    )
    fuel_poverty = _series(
        rows, "metric.source.m8.energy.fuel_poverty_share"
    )
    population_births = _series(rows, "metric.source.m7.births")
    population_deaths = _series(rows, "metric.source.m7.deaths")
    housing_stock = _series(
        rows, "metric.source.m8.housing.housing_stock"
    )
    housing_completions = _series(
        rows, "metric.source.m8.housing.dwellings_completed"
    )
    housing_sales = _series(
        rows, "metric.source.m8.housing.session_sales"
    )
    mortgage_originations = _series(
        rows, "metric.source.m8.housing.mortgage_originations"
    )
    rent_paid = _series(rows, "metric.source.m8.housing.rent_paid")
    rent_unpaid = _series(rows, "metric.source.m8.housing.rent_unpaid")
    evictions = _series(rows, "metric.source.m8.housing.evictions")
    active_listings = _series(
        rows, "metric.source.m8.housing.active_listings"
    )
    housing_construction = _series(
        rows, "metric.source.m8.housing.construction_output"
    )
    house_price = _series(
        rows, "metric.source.m8.housing.house_price"
    )
    rent_level = _series(rows, "metric.source.m8.housing.rent_level")
    homeownership = _series(
        rows, "metric.source.m8.housing.homeownership_share"
    )
    housing_vacancy = _series(
        rows, "metric.source.m8.housing.vacancy_share"
    )
    sale_indexes = [
        index for index, sales in enumerate(housing_sales) if sales > 0.0
    ]
    house_price_changes = [
        (house_price[index] / house_price[index - 1] - 1.0)
        for index in range(1, len(house_price))
        if abs(house_price[index - 1]) > 1.0e-12
        and abs(house_price[index] - house_price[index - 1]) > 1.0e-12
    ]
    bank_failures = _series(rows, "metric.source.m5.bank_failures")
    run_flight_volume = _series(
        rows, "metric.source.m5.run_flight_volume"
    )
    lolr_advances = _series(rows, "metric.source.m5.lolr_advances")
    lolr_outstanding = _series(
        rows, "metric.source.m5.lolr_outstanding"
    )
    resolution_cost = _series(rows, "metric.source.m5.resolution_cost")
    realized_credit_losses = _series(
        rows, "metric.source.m5.realized_credit_losses"
    )
    realized_interbank_losses = _series(
        rows, "metric.source.m5.realized_interbank_losses"
    )
    government_debt_to_gdp = _series(
        rows, "metric.economy.gov_debt_to_gdp"
    )
    credit_to_gdp = _series(rows, "metric.economy.credit_to_gdp")
    poverty = _series(rows, "metric.economy.poverty_rate")
    expenditure_residual = _series(
        rows, "metric.economy.na.expenditure_residual_share"
    )
    income_residual = _series(
        rows, "metric.economy.na.income_residual_share"
    )
    conservation = _series(rows, "metric.source.m4.conservation_drift")
    government_spending = _series(
        rows, "metric.source.m4.government_spending"
    )
    government_deficit = _series(
        rows, "metric.source.m4.government_deficit"
    )
    government_consumption = _series(
        rows, "metric.source.m4.government_consumption"
    )
    transfer_payments = _series(
        rows, "metric.source.m4.transfer_payments"
    )
    household_consumption = _series(
        rows, "metric.source.m4.household_consumption"
    )
    taxes = _series(rows, "metric.source.m4.tax_total")
    firm_profit = _series(rows, "metric.source.m4.firm_profit")
    inventory_change = _series(
        rows, "metric.source.m4.inventory_change_real"
    )
    firm_births = _series(rows, "metric.source.m6.firm_births")
    firm_exits = _series(rows, "metric.source.m6.firm_exits")
    firm_defaults = _series(rows, "metric.source.m6.firm_defaults")
    bank_births = _series(rows, "metric.source.m6.bank_births")
    new_credit = _series(rows, "metric.source.m5.new_credit")
    loan_principal = _series(
        rows, "metric.source.m5.total_loan_principal"
    )
    nominal_output = _series(rows, "metric.source.m4.nominal_output")
    exchange_rate = _series(
        rows, "metric.source.m9.country.exchange_rate"
    )
    imports_value = _series(
        rows, "metric.source.m9.country.imports_value"
    )
    exports_value = _series(
        rows, "metric.source.m9.country.exports_value"
    )
    current_account = _series(
        rows, "metric.source.m9.country.current_account"
    )
    capital_flow = _series(
        rows, "metric.source.m9.country.capital_flow"
    )
    net_foreign_assets = _series(
        rows, "metric.source.m9.country.net_foreign_assets"
    )
    migrant_stock_abroad = _series(
        rows, "metric.source.m9.country.migrant_stock_abroad"
    )
    migrant_stock_hosted = _series(
        rows, "metric.source.m9.country.migrant_stock_hosted"
    )
    remittances_received = _series(
        rows, "metric.source.m9.country.remittances_received"
    )
    remittances_sent = _series(
        rows, "metric.source.m9.country.remittances_sent"
    )
    world_nfa = _series(rows, "metric.source.m9.world.world_nfa")
    physical_shortage = [
        max(requested - opening, 0.0)
        for requested, opening in zip(
            energy_requested, energy_opening, strict=True
        )
    ]

    split = min(365, len(rows))
    second_start = split if len(rows) > split else 0
    first_window_start = max(0, split - min(30, split))
    second_window_start = max(second_start, len(rows) - min(30, len(rows)))
    first_gdp_pc = _window_mean(real_output_pc, first_window_start, split)
    second_gdp_pc = _window_mean(
        real_output_pc, second_window_start, len(rows)
    )
    first_price = _window_mean(price, first_window_start, split)
    second_price = _window_mean(price, second_window_start, len(rows))
    first_capital = _window_mean(capital, first_window_start, split)
    second_capital = _window_mean(capital, second_window_start, len(rows))
    transition_windows: dict[str, dict[str, float]] = {}
    for start in range(0, min(len(rows), 730), 30):
        stop = min(start + 30, len(rows))
        nominal = sum(nominal_output[start:stop])
        requested_energy = sum(energy_requested[start:stop])
        transition_windows[f"{start + 1}-{stop}"] = {
            "unemployment_mean": _mean(unemployment[start:stop]),
            "unemployment_end": unemployment[stop - 1],
            "suspended_share_mean": (
                sum(suspended[start:stop])
                / max(1.0e-12, sum(labor_supply[start:stop]))
            ),
            "vacancies_mean": _mean(vacancies[start:stop]),
            "hires_mean": _mean(hires[start:stop]),
            "separations_mean": _mean(separations[start:stop]),
            "real_output_per_capita_mean": _mean(
                real_output_pc[start:stop]
            ),
            "price_index_end": price[stop - 1],
            "capital_end": capital[stop - 1],
            "household_consumption_share": (
                sum(household_consumption[start:stop])
                / max(1.0e-12, nominal)
            ),
            "government_spending_share": (
                sum(government_spending[start:stop])
                / max(1.0e-12, nominal)
            ),
            "fixed_investment_share": (
                sum(investment[start:stop]) / max(1.0e-12, nominal)
            ),
            "firm_profit_share": (
                sum(firm_profit[start:stop]) / max(1.0e-12, nominal)
            ),
            "inventory_change_mean": _mean(inventory_change[start:stop]),
            "energy_unfilled_share": (
                sum(energy_unfilled[start:stop])
                / max(1.0e-12, requested_energy)
            ),
            "new_credit_mean": _mean(new_credit[start:stop]),
            "firm_defaults": sum(firm_defaults[start:stop]),
            "bank_failures": sum(bank_failures[start:stop]),
        }

    return {
        "population_requested": population,
        "seed": seed,
        "days": len(rows),
        "elapsed_seconds": elapsed_seconds,
        "seconds_per_day": elapsed_seconds / len(rows),
        "memory_bytes": session.memory_usage(),
        "storage_counts": session.storage_counts(),
        "native_module": str(sys.modules["_native"].__file__),
        "economy_id": economy_id,
        "end_probe": session.probe_economy_diagnostics(economy_id),
        "end_firm_sectors": _firm_sector_summary(session, economy_id),
        "end_banks": _bank_summary(session, economy_id),
        "end_jobs": _job_summary(session, economy_id),
        "transition_windows": transition_windows,
        "annual": {
            str(year + 1): {
                "unemployment_mean": _mean(
                    unemployment[year * 365 : min((year + 1) * 365, len(rows))]
                ),
                "unemployment_end": unemployment[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "m4_unemployment_mean": _mean(
                    m4_unemployment[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "real_output_per_capita_mean": _mean(
                    real_output_pc[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "price_index_end": price[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "house_price_end": house_price[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "rent_level_end": rent_level[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "homeownership_end": homeownership[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "housing_vacancy_end": housing_vacancy[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "housing_sales": sum(
                    housing_sales[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "housing_completions": sum(
                    housing_completions[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "government_deficit_share": (
                    sum(
                        government_deficit[
                            year * 365 : min((year + 1) * 365, len(rows))
                        ]
                    )
                    / max(
                        1.0e-12,
                        sum(
                            nominal_output[
                                year * 365 : min((year + 1) * 365, len(rows))
                            ]
                        ),
                    )
                ),
                "government_debt_to_gdp_end": government_debt_to_gdp[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "credit_to_gdp_end": credit_to_gdp[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "capital_end": capital[
                    min((year + 1) * 365, len(rows)) - 1
                ],
                "poverty_mean": _mean(
                    poverty[year * 365 : min((year + 1) * 365, len(rows))]
                ),
                "bank_failures": sum(
                    bank_failures[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "bank_births": sum(
                    bank_births[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "firm_defaults": sum(
                    firm_defaults[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "realized_credit_losses": sum(
                    realized_credit_losses[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "realized_interbank_losses": sum(
                    realized_interbank_losses[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "resolution_cost": sum(
                    resolution_cost[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "new_credit": sum(
                    new_credit[
                        year * 365 : min((year + 1) * 365, len(rows))
                    ]
                ),
                "loan_principal_end": loan_principal[
                    min((year + 1) * 365, len(rows)) - 1
                ],
            }
            for year in range((len(rows) + 364) // 365)
        },
        "macro": {
            "population_end": population_series[-1],
            "population_change": _relative_change(
                population_series[0], population_series[-1]
            ),
            "births_total": sum(population_births),
            "deaths_total": sum(population_deaths),
            "unemployment_mean_second_year": _mean(
                unemployment[second_start:]
            ),
            "unemployment_end": unemployment[-1],
            "unemployment_min_second_year": min(
                unemployment[second_start:]
            ),
            "unemployment_max_second_year": max(
                unemployment[second_start:]
            ),
            "m4_unemployment_mean_second_year": _mean(
                m4_unemployment[second_start:]
            ),
            "m4_unemployment_end": m4_unemployment[-1],
            "suspended_share_mean_second_year": (
                sum(suspended[second_start:])
                / max(1.0e-12, sum(labor_supply[second_start:]))
            ),
            "suspended_share_end": (
                suspended[-1] / max(1.0e-12, labor_supply[-1])
            ),
            "participation_mean_second_year": _mean(
                participation[second_start:]
            ),
            "participation_end": participation[-1],
            "vacancies_mean_second_year": _mean(vacancies[second_start:]),
            "vacancies_end": vacancies[-1],
            "labor_supply_end": labor_supply[-1],
            "employed_fte_end": employed_fte[-1],
            "employed_heads_end": employed_heads[-1],
            "unemployed_end": unemployed[-1],
            "open_unemployment_share_end": (
                max(0.0, unemployed[-1] - suspended[-1])
                / max(1.0e-12, labor_supply[-1])
            ),
            "underemployed_head_share_end": (
                underemployed_heads[-1]
                / max(1.0e-12, labor_supply[-1])
            ),
            "underemployment_hours_share_end": (
                underemployment_hours[-1]
                / max(1.0e-12, labor_supply[-1])
            ),
            "nonsearching_end": nonsearching[-1],
            "hires_mean_second_year": _mean(hires[second_start:]),
            "separations_mean_second_year": _mean(
                separations[second_start:]
            ),
            "churn_separations_mean_second_year": _mean(
                churn_separations[second_start:]
            ),
            "demand_layoff_separations_mean_second_year": _mean(
                demand_layoff_separations[second_start:]
            ),
            "cash_layoff_separations_mean_second_year": _mean(
                cash_layoff_separations[second_start:]
            ),
            "firm_exit_separations_mean_second_year": _mean(
                firm_exit_separations[second_start:]
            ),
            "death_separations_mean_second_year": _mean(
                death_separations[second_start:]
            ),
            "retirement_separations_mean_second_year": _mean(
                retirement_separations[second_start:]
            ),
            "welfare_quits_mean_second_year": _mean(
                welfare_quits[second_start:]
            ),
            "suspensions_flow_mean_second_year": _mean(
                suspensions_flow[second_start:]
            ),
            "recalls_mean_second_year": _mean(
                recalls[second_start:]
            ),
            "job_to_job_moves_mean_second_year": _mean(
                job_to_job_moves[second_start:]
            ),
            "mean_wage_window_change": _relative_change(
                _window_mean(mean_wage, first_window_start, split),
                _window_mean(mean_wage, second_window_start, len(rows)),
            ),
            "real_output_pc_window_change": _relative_change(
                first_gdp_pc, second_gdp_pc
            ),
            "price_window_change": _relative_change(
                first_price, second_price
            ),
            "capital_window_change": _relative_change(
                first_capital, second_capital
            ),
            "fixed_investment_mean_second_year": _mean(
                investment[second_start:]
            ),
            "energy_unfilled_request_share_second_year": (
                sum(energy_unfilled[second_start:])
                / max(1.0e-12, sum(energy_requested[second_start:]))
            ),
            "energy_physical_shortage_share_second_year": (
                sum(physical_shortage[second_start:])
                / max(1.0e-12, sum(energy_requested[second_start:]))
            ),
            "energy_price_end": energy_price[-1],
            "fuel_poverty_mean_second_year": _mean(
                fuel_poverty[second_start:]
            ),
            "housing_stock_end": housing_stock[-1],
            "housing_stock_change": housing_stock[-1] - housing_stock[0],
            "housing_completions_total": sum(housing_completions),
            "housing_sales_total": sum(housing_sales),
            "housing_first_sale_tick": (
                int(rows[sale_indexes[0]]["_tick"]) if sale_indexes else None
            ),
            "housing_last_sale_tick": (
                int(rows[sale_indexes[-1]]["_tick"]) if sale_indexes else None
            ),
            "housing_sale_sessions": len(sale_indexes),
            "house_price_session_change_min": min(
                house_price_changes, default=0.0
            ),
            "house_price_session_change_max": max(
                house_price_changes, default=0.0
            ),
            "mortgage_originations_total": sum(mortgage_originations),
            "rent_paid_total": sum(rent_paid),
            "rent_unpaid_total": sum(rent_unpaid),
            "evictions_total": sum(evictions),
            "active_listings_end": active_listings[-1],
            "housing_construction_mean_second_year": _mean(
                housing_construction[second_start:]
            ),
            "house_price_window_change": _relative_change(
                _window_mean(house_price, first_window_start, split),
                _window_mean(house_price, second_window_start, len(rows)),
            ),
            "rent_window_change": _relative_change(
                _window_mean(rent_level, first_window_start, split),
                _window_mean(rent_level, second_window_start, len(rows)),
            ),
            "homeownership_end": homeownership[-1],
            "housing_vacancy_end": housing_vacancy[-1],
            "bank_failures_total": sum(bank_failures),
            "run_flight_volume_total": sum(run_flight_volume),
            "lolr_advances_total": sum(lolr_advances),
            "lolr_outstanding_end": lolr_outstanding[-1],
            "lolr_outstanding_max": max(lolr_outstanding),
            "resolution_cost_total": sum(resolution_cost),
            "realized_credit_losses_total": sum(
                realized_credit_losses
            ),
            "realized_interbank_losses_total": sum(
                realized_interbank_losses
            ),
            "poverty_mean_second_year": _mean(poverty[second_start:]),
            "expenditure_residual_abs_mean_second_year": _mean(
                [abs(value) for value in expenditure_residual[second_start:]]
            ),
            "income_residual_abs_mean_second_year": _mean(
                [abs(value) for value in income_residual[second_start:]]
            ),
            "conservation_drift_max_abs": max(
                abs(value) for value in conservation
            ),
            "government_spending_share_mean_second_year": (
                sum(government_spending[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "government_deficit_share_mean_second_year": (
                sum(government_deficit[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "government_consumption_share_mean_second_year": (
                sum(government_consumption[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "transfer_share_mean_second_year": (
                sum(transfer_payments[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "household_consumption_share_mean_second_year": (
                sum(household_consumption[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "tax_share_mean_second_year": (
                sum(taxes[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "firm_profit_share_mean_second_year": (
                sum(firm_profit[second_start:])
                / max(1.0e-12, sum(nominal_output[second_start:]))
            ),
            "inventory_change_mean_second_year": _mean(
                inventory_change[second_start:]
            ),
            "firm_births_total": sum(firm_births),
            "firm_exits_total": sum(firm_exits),
            "firm_defaults_total": sum(firm_defaults),
            "new_credit_mean_second_year": _mean(
                new_credit[second_start:]
            ),
            "loan_principal_end": loan_principal[-1],
            "exchange_rate_end": exchange_rate[-1],
            "exchange_rate_min": min(exchange_rate),
            "exchange_rate_max": max(exchange_rate),
            "imports_value_total": sum(imports_value),
            "exports_value_total": sum(exports_value),
            "current_account_total": sum(current_account),
            "capital_flow_total": sum(capital_flow),
            "net_foreign_assets_end": net_foreign_assets[-1],
            "migrant_stock_abroad_end": migrant_stock_abroad[-1],
            "migrant_stock_hosted_end": migrant_stock_hosted[-1],
            "remittances_received_total": sum(remittances_received),
            "remittances_sent_total": sum(remittances_sent),
            "world_nfa_max_abs": max(abs(value) for value in world_nfa),
        },
        "checkpoints": {
            str(int(rows[index]["_tick"])): {
                "unemployment": unemployment[index],
                "participation": participation[index],
                "vacancies": vacancies[index],
                "real_output_per_capita": real_output_pc[index],
                "price_index": price[index],
                "aggregate_capital": capital[index],
            }
            for index in sorted(
                {
                    min(len(rows) - 1, day - 1)
                    for day in (1, 7, 30, 90, 180, 365, 545, 730)
                }
            )
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--countries", type=int, default=1)
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--checkpoint-after", type=int, default=0)
    parser.add_argument(
        "--capital-rationed-signal",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--consumption-rationed-signal",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--config-override",
        action="append",
        default=[],
        metavar="FIELD=JSON_VALUE",
        type=_parse_config_override,
        help="override a Config field after constructing the playable baseline",
    )
    args = parser.parse_args()

    spec = _build_spec(
        args.population,
        args.days,
        args.seed,
        args.countries,
    )
    if args.countries > 1 and (
        args.capital_rationed_signal is not None
        or args.consumption_rationed_signal is not None
        or args.config_override
    ):
        parser.error(
            "direct Config overrides are only supported for one-country runs"
        )
    config = spec.configs()[0]
    uses_direct_config = (
        args.capital_rationed_signal is not None
        or args.consumption_rationed_signal is not None
        or bool(args.config_override)
    )
    if args.capital_rationed_signal is not None:
        config = replace(
            config,
            capital_rationed_signal=args.capital_rationed_signal,
        )
    if args.consumption_rationed_signal is not None:
        config = replace(
            config,
            consumption_rationed_signal=args.consumption_rationed_signal,
        )
    for field, value in args.config_override:
        if not hasattr(config, field):
            parser.error(f"Config has no field named {field!r}")
        config = replace(config, **{field: value})
    if uses_direct_config:
        session = NativeSimulationSession.create_from_configs(
            [config],
            worker_count=args.workers,
            history_capacity_frames=args.days + 8,
        )
    else:
        session = NativeSimulationSession.create(
            spec,
            worker_count=args.workers,
            history_capacity_frames=args.days + 8,
        )
    started = time.perf_counter()
    while session.tick < args.days:
        step = min(args.chunk_days, args.days - session.tick)
        session.advance(step)
        print(
            f"advanced={session.tick}/{args.days} "
            f"elapsed={time.perf_counter() - started:.2f}s",
            flush=True,
        )
        if (
            args.checkpoint is not None
            and session.tick >= args.checkpoint_after
        ):
            args.checkpoint.write_bytes(session.checkpoint())
    elapsed = time.perf_counter() - started
    summaries = [
        _summarize(
            _history_rows(session, economy_id),
            elapsed_seconds=elapsed,
            population=args.population,
            seed=args.seed,
            session=session,
            economy_id=economy_id,
        )
        for economy_id in range(args.countries)
    ]
    summary: dict[str, Any]
    if args.countries == 1:
        summary = summaries[0]
    else:
        summary = {
            "countries": args.countries,
            "population_per_country": args.population,
            "seed": args.seed,
            "days": args.days,
            "elapsed_seconds": elapsed,
            "seconds_per_world_day": elapsed / args.days,
            "memory_bytes": session.memory_usage(),
            "storage_counts": session.storage_counts(),
            "economies": summaries,
        }
    payload = json.dumps(summary, indent=2, sort_keys=True)
    print(payload, flush=True)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
