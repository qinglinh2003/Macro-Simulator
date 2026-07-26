"""Protocol-v4 desktop projections derived from committed native state.

The projection layer is read-only.  It consumes maintained metric frames and
typed native probes, then preserves the current Godot wire shape while keeping
all categorical values as locale-independent identifiers.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
import math
from statistics import median
from typing import Any

from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.native_backend import NativeSimulationSession


DESKTOP_PROTOCOL_VERSION = 4
SERIES_LIMIT = 160
MAX_COMPATIBILITY_ROWS = 10_000
INVALID_U32 = 2**32 - 1

FIRM_SECTOR_IDS = {
    0: "consumption",
    1: "capital",
    2: "energy",
    3: "construction",
}
OWNER_KIND_IDS = {
    0: "household",
    1: "firm",
    2: "bank",
    3: "treasury",
    4: "central_bank",
    5: "dealer",
    6: "rounding_residual",
    7: "institution",
}
EQUITY_ISSUER_KIND_IDS = {0: "firm", 1: "bank"}
SECURITY_KIND_IDS = {0: "bond", 1: "equity"}
SEX_IDS = {0: "female", 1: "male"}


DIRECT_METRIC_ALIASES = {
    "real_output": "metric.economy.real_output",
    "unemployment_rate": "metric.economy.unemployment_rate",
    "inflation": "metric.economy.inflation",
    "price_index": "metric.economy.price_index",
    "avg_wage": "metric.economy.avg_wage",
    "policy_rate": "metric.economy.policy_rate",
    "population_alive": "metric.economy.population_alive",
    "gov_debt_to_gdp": "metric.economy.gov_debt_to_gdp",
    "gov_deficit_to_gdp": "metric.economy.gov_deficit_to_gdp",
    "poverty_rate": "metric.economy.poverty_rate",
    "income_gini": "metric.economy.income_gini",
    "energy_price": "metric.economy.energy_price",
    "energy_stock_total": "metric.economy.energy_stock_total",
    "energy_unfilled": "metric.economy.energy_unfilled",
    "e": "metric.world.e",
    "nfa": "metric.world.nfa",
    "current_account": "metric.world.current_account",
    "migrant_stock": "metric.world.migrant_stock",
    "remittances": "metric.world.remittances",
    "real_consumption": "metric.source.m4.household_consumption",
    "aggregate_capital": "metric.source.m4.aggregate_capital",
    "investment_spending":
        "metric.source.m4.fixed_capital_formation_nominal",
    "total_money": "metric.source.m4.total_money",
    "tax_total": "metric.source.m4.tax_total",
    "gov_spending": "metric.source.m4.government_spending",
    "gov_deficit": "metric.source.m4.government_deficit",
    "benefit_paid": "metric.source.m4.transfer_payments",
    "gov_consumption": "metric.source.m4.government_consumption",
    "public_investment":
        "metric.source.m4.public_fixed_capital_formation",
    "total_credit": "metric.source.m5.total_loan_principal",
    "bank_capital": "metric.source.m5.total_bank_capital",
    "new_loans_total": "metric.source.m5.new_credit",
    "new_loans": "metric.source.m5.new_credit",
    "bank_realized_credit_losses":
        "metric.source.m5.realized_credit_losses",
    "interbank_rate": "metric.source.m5.interbank_rate",
    "interbank_volume": "metric.source.m5.interbank_volume",
    "banks_alive": "metric.source.m5.alive_banks",
    "n_bank_failures": "metric.source.m5.bank_failures",
    "bank_deaths": "metric.source.m5.bank_failures",
    "equity_turnover": "metric.source.m6.equity_turnover",
    "hh_bankruptcies": "metric.source.m6.household_bankruptcies",
    "bank_births": "metric.source.m6.bank_births",
    "sector_switches": "metric.source.m6.sector_switches",
    "sector_switch_capital": "metric.source.m6.sector_retool_capital",
    "births": "metric.source.m6.firm_births",
    "deaths": "metric.source.m6.firm_exits",
    "labor_E": "metric.source.m7.employed_fte",
    "labor_employed_heads": "metric.source.m7.employed_heads",
    "labor_U": "metric.source.m7.unemployment",
    "labor_JG": "metric.source.m7.job_guarantee",
    "labor_OLF": "metric.source.m7.out_of_labor_force",
    "vacancies_unfilled": "metric.source.m7.vacancies",
    "labor_hires_total": "metric.source.m7.hires",
    "labor_churn_seps_total": "metric.source.m7.separations",
    "avg_household_size": "metric.source.m7.mean_household_size",
    "working_age_share": "metric.source.m7.working_age_share",
    "dependency_ratio": "metric.source.m7.dependency_ratio",
    "births_tick": "metric.source.m7.births",
    "deaths_tick": "metric.source.m7.deaths",
    "marriages_tick": "metric.source.m7.marriages",
    "divorces_tick": "metric.source.m7.divorces",
    "energy_produced": "metric.source.m8.energy.production",
    "energy_used": "metric.source.m8.energy.sold",
    "energy_sold": "metric.source.m8.energy.sold",
    "e_capacity_utilization":
        "metric.source.m8.energy.utilization",
    "spr_stock":
        "metric.source.m8.energy.strategic_reserve_stock",
    "house_price": "metric.source.m8.housing.house_price",
    "rent_level": "metric.source.m8.housing.rent_level",
    "dwellings_total": "metric.source.m8.housing.housing_stock",
    "homeowner_share":
        "metric.source.m8.housing.homeownership_share",
    "housing_listings":
        "metric.source.m8.housing.active_listings",
    "housing_sales_session":
        "metric.source.m8.housing.session_sales",
    "housing_tom":
        "metric.source.m8.housing.mean_time_on_market_days",
    "housing_forced_share":
        "metric.source.m8.housing.forced_listing_share",
    "mortgage_balance_total":
        "metric.source.m8.housing.mortgage_principal_outstanding",
    "mortgage_originated_tick":
        "metric.source.m8.housing.mortgage_principal_originated",
    "foreclosures_total":
        "metric.source.m8.housing.foreclosures",
    "housing_pti_ratio":
        "metric.source.m8.housing.price_to_income_ratio",
    "rent_burden_ratio":
        "metric.source.m8.housing.rent_burden_ratio",
    "property_tax_paid":
        "metric.source.m8.housing.property_tax_paid",
    "transfer_tax_paid":
        "metric.source.m8.housing.transfer_tax_paid",
    "dwellings_built_total":
        "metric.source.m8.housing.dwellings_completed",
    "permits_used_year":
        "metric.source.m8.housing.permits_used",
    "rent_paid_total": "metric.source.m8.housing.rent_paid",
    "evictions_total": "metric.source.m8.housing.evictions",
    "import_value": "metric.source.m9.country.imports_value",
    "export_delivered_volume":
        "metric.source.m9.country.exports_volume",
    "tariff_rev": "metric.source.m9.country.tariff_revenue",
}

NATIONAL_ACCOUNT_ALIASES = {
    "gdp_deflator": "gdp_deflator",
    "gdp_nominal_expenditure_reconciled":
        "expenditure_reconciled_nominal",
    "gdp_real_expenditure_reconciled":
        "expenditure_reconciled_real",
    "gdp_nominal_household_consumption":
        "household_consumption_nominal",
    "gdp_nominal_government_consumption":
        "government_consumption_nominal",
    "gdp_nominal_fixed_capital_formation":
        "fixed_capital_formation_nominal",
    "gdp_nominal_net_exports": "net_exports_nominal",
    "gdp_nominal_gross_output_c":
        "gross_output_consumption_nominal",
    "gdp_nominal_gross_output_k":
        "gross_output_capital_nominal",
    "gdp_nominal_gross_output_e":
        "gross_output_energy_nominal",
    "gdp_nominal_gross_output_housing":
        "gross_output_housing_nominal",
    "gdp_real_household_consumption":
        "household_consumption_goods_nominal",
    "gdp_real_government_consumption":
        "government_consumption_nominal",
    "gdp_real_fixed_capital_formation":
        "fixed_capital_formation_nominal",
    "gdp_real_net_exports": "net_exports_real",
    "gdp_nominal_three_approach_raw_spread_share":
        "three_approach_raw_spread_share",
    "gdp_nominal_income_reconciled":
        "income_reconciled_nominal",
    "gdp_nominal_production": "production_nominal",
    "gdp_nominal_compensation_of_employees":
        "compensation_employees_nominal",
    "gdp_nominal_accrued_gross_operating_surplus":
        "cash_operating_surplus_nominal",
    "gdp_nominal_net_product_taxes_observed":
        "production_reconciliation_residual",
    "gdp_nominal_exports": "exports_nominal",
    "gdp_nominal_imports": "imports_nominal",
    "gdp_nominal_inventory_change":
        "inventory_change_nominal",
    "gdp_nominal_private_fixed_capital_formation":
        "private_fixed_capital_formation_nominal",
    "gdp_nominal_public_fixed_capital_formation":
        "public_fixed_capital_formation_nominal",
    "gdp_nominal_residential_fixed_capital_formation":
        "residential_fixed_capital_formation_nominal",
    "gdp_nominal_machinery_fixed_capital_formation":
        "machinery_fixed_capital_formation_nominal",
    "gdp_real_exports": "exports_real",
    "gdp_real_imports": "imports_real",
    "debt_service_to_nominal_gdp":
        "debt_service_to_nominal_gdp",
    "total_debt_service_to_nominal_gdp":
        "total_debt_service_to_nominal_gdp",
}


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        return default
    result = float(value)
    return result if math.isfinite(result) else default


def _safe_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return None if value < 0 or value >= INVALID_U32 else value


def _gini(values: Iterable[float]) -> float:
    ordered = sorted(max(0.0, _number(value)) for value in values)
    if not ordered:
        return 0.0
    total = sum(ordered)
    if total <= 1.0e-12:
        return 0.0
    count = len(ordered)
    weighted = sum(
        (index + 1) * value for index, value in enumerate(ordered)
    )
    return max(
        0.0,
        min(1.0, 2.0 * weighted / (count * total) - (count + 1) / count),
    )


def _top_share(values: Iterable[float], share: float = 0.1) -> float:
    ordered = sorted(
        (max(0.0, _number(value)) for value in values), reverse=True
    )
    total = sum(ordered)
    if not ordered or total <= 1.0e-12:
        return 0.0
    count = max(1, math.ceil(len(ordered) * share))
    return sum(ordered[:count]) / total


def _distribution(values: Iterable[float]) -> dict[str, list[float]]:
    ordered = sorted(max(0.0, _number(value)) for value in values)
    deciles = [0.0] * 10
    total = sum(ordered)
    if total > 1.0e-12:
        for index, value in enumerate(ordered):
            bucket = min(9, int(index * 10 / len(ordered)))
            deciles[bucket] += value / total
    lorenz = [0.0]
    running = 0.0
    for value in deciles:
        running += value
        lorenz.append(min(1.0, running))
    if total > 1.0e-12:
        lorenz[-1] = 1.0
    return {"deciles": deciles, "lorenz": lorenz}


def _median(values: Iterable[float]) -> float:
    materialized = [_number(value) for value in values]
    return float(median(materialized)) if materialized else 0.0


class NativeDesktopProjection:
    """Build the current desktop snapshot without reading Python engine state."""

    def __init__(
        self,
        session: NativeSimulationSession,
        spec: NewGameSpec,
        player_economy: int,
    ) -> None:
        self.session = session
        self.spec = spec
        self.player_economy = player_economy
        self.panel_history: deque[dict[str, Any]] = deque(
            maxlen=SERIES_LIMIT
        )
        self.world_history: deque[dict[str, Any]] = deque(
            maxlen=SERIES_LIMIT
        )
        self.stock_history: deque[dict[str, Any]] = deque(
            maxlen=SERIES_LIMIT
        )
        self.refresh()

    def _all_rows(self, kind: str) -> tuple[list[dict[str, Any]], bool]:
        rows: list[dict[str, Any]] = []
        after_id = 0
        complete = True
        while len(rows) < MAX_COMPATIBILITY_ROWS:
            page = self.session.probe_page(
                kind,
                economy_id=self.player_economy,
                after_id=after_id,
                maximum_rows=min(
                    1024, MAX_COMPATIBILITY_ROWS - len(rows)
                ),
            )
            if int(page["boundary"]) != self.session.tick:
                raise RuntimeError("native probe boundary changed during snapshot")
            batch = [dict(row) for row in page["rows"]]
            rows.extend(batch)
            if not page["has_more"]:
                break
            next_after_id = int(page["next_after_id"])
            if next_after_id <= after_id or not batch:
                raise RuntimeError("native probe cursor did not advance")
            after_id = next_after_id
        else:
            complete = False
        return rows, complete

    @staticmethod
    def _metric(
        row: Mapping[str, Any], stable_id: str, default: float = 0.0
    ) -> float:
        return _number(row.get(stable_id), default)

    def _panel_point(
        self,
        row: Mapping[str, Any],
        diagnostics: Mapping[str, Any],
        households: list[dict[str, Any]],
        persons: list[dict[str, Any]],
        firms: list[dict[str, Any]],
        banks: list[dict[str, Any]],
        dwellings: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        policy: Mapping[str, Any],
    ) -> dict[str, Any]:
        point: dict[str, Any] = {
            "tick": self.session.tick,
            "boundary": self.session.tick,
            "metric_values": dict(row),
        }
        for alias, stable_id in DIRECT_METRIC_ALIASES.items():
            point[alias] = self._metric(row, stable_id)
        for alias, field in NATIONAL_ACCOUNT_ALIASES.items():
            point[alias] = self._metric(
                row, f"metric.economy.na.{field}"
            )

        nominal_output = self._metric(
            row, "metric.source.m4.nominal_output"
        )
        real_output = point["real_output"]
        price_index = point["price_index"]
        previous = self.panel_history[-1] if self.panel_history else None
        previous_output = (
            _number(previous.get("real_output"))
            if previous is not None
            else real_output
        )
        previous_wage = (
            _number(previous.get("avg_wage"))
            if previous is not None
            else point["avg_wage"]
        )
        total_inventory = sum(
            _number(item.get("goods_inventory")) for item in firms
        )
        total_sales = sum(
            _number(item.get("previous_sales")) for item in firms
        )
        total_equity = (
            self._metric(
                row, "metric.source.m6.firm_equity_market_cap"
            )
            + self._metric(
                row, "metric.source.m6.bank_equity_market_cap"
            )
        )
        household_debt = sum(
            _number(item.get("debt")) for item in households
        )
        firm_debt = sum(_number(item.get("debt")) for item in firms)
        household_wealth = [
            max(0.0, _number(item.get("cash")) - _number(item.get("debt")))
            for item in households
        ]
        person_wealth = [
            max(0.0, _number(item.get("net_worth"))) for item in persons
        ]
        income_values = [
            max(0.0, _number(item.get("income_realized")))
            for item in households
        ]
        consumption_values = [
            max(0.0, _number(item.get("spent"))) for item in households
        ]
        ages = [int(_number(item.get("age_days"))) // 365 for item in persons]
        population = len(persons)
        child_population = sum(age < 18 for age in ages)
        working_population = sum(18 <= age < 65 for age in ages)
        elder_population = sum(age >= 65 for age in ages)
        adult_population = population - child_population
        total_firm_book = sum(
            max(0.0, _number(item.get("book_equity")))
            for item in firms
        )
        q_values = [
            _number(item.get("tobin_q_ema"), 1.0)
            for item in firms if bool(item.get("active", True))
        ]
        active_firms = [
            item for item in firms if bool(item.get("active", True))
        ]
        consumption_firms = [
            item for item in active_firms
            if int(item.get("sector", -1)) == 0
        ]
        household_assets = sum(household_wealth)
        total_debt_service = (
            self._metric(
                row, "metric.source.m5.principal_repaid"
            )
            + self._metric(
                row, "metric.source.m5.loan_interest_paid"
            )
        )
        energy_spending = (
            self._metric(
                row, "metric.source.m8.energy.household_spending"
            )
            + self._metric(
                row, "metric.source.m8.energy.industry_spending"
            )
        )
        energy_used = point["energy_used"]

        point.update({
            "real_output_growth": (
                0.0 if abs(previous_output) <= 1.0e-12
                else real_output / previous_output - 1.0
            ),
            "labor_productivity": (
                real_output / max(
                    1.0,
                    self._metric(
                        row, "metric.source.m7.employed_fte"
                    ),
                )
            ),
            "labor_share": (
                self._metric(row, "metric.source.m4.wages_paid")
                / max(1.0, nominal_output)
            ),
            "inventory_to_sales": total_inventory / max(1.0, total_sales),
            "production_realization_rate": (
                real_output
                / max(
                    1.0,
                    self._metric(
                        row, "metric.source.m4.consumption_output_real"
                    )
                    + self._metric(
                        row, "metric.source.m4.capital_output_real"
                    ),
                )
            ),
            "u_natural": _number(policy.get("u_natural")),
            "underemployed_share": (
                self._metric(
                    row, "metric.source.m7.underemployed_heads"
                )
                / max(1.0, working_population)
            ),
            "wage_inflation": (
                0.0 if abs(previous_wage) <= 1.0e-12
                else point["avg_wage"] / previous_wage - 1.0
            ),
            "avg_markup": (
                sum(_number(item.get("markup")) for item in active_firms)
                / max(1, len(active_firms))
            ),
            "real_wage": point["avg_wage"] / max(1.0e-12, price_index),
            "gov_debt": (
                point["gov_debt_to_gdp"]
                * self._metric(
                    row, "metric.economy.na.annualized_nominal_gdp"
                )
            ),
            "fiscal_revenue_total": point["tax_total"],
            "augmented_gov_spending": point["gov_spending"],
            "bank_deposit_total": _number(
                diagnostics.get("account_balance_total")
            ),
            "writeoffs": (
                point["bank_realized_credit_losses"]
                + self._metric(
                    row, "metric.source.m6.margin_writeoffs"
                )
            ),
            "total_debt_service_ratio": (
                total_debt_service / max(1.0, nominal_output)
            ),
            "firm_debt_total": firm_debt,
            "household_debt_total_observed": household_debt,
            "household_debt_total": household_debt,
            "household_debt_per_capita":
                household_debt / max(1, population),
            "household_debt_gini": _gini(
                _number(item.get("debt")) for item in households
            ),
            "household_debt_top10_share": _top_share(
                _number(item.get("debt")) for item in households
            ),
            "firm_debt_gini": _gini(
                _number(item.get("debt")) for item in firms
            ),
            "firm_debt_top10_share": _top_share(
                _number(item.get("debt")) for item in firms
            ),
            "debt_service_ratio":
                total_debt_service / max(1.0, nominal_output),
            "equity_market_cap": total_equity,
            "tobin_q_mean": (
                sum(q_values) / len(q_values) if q_values else 0.0
            ),
            "tobin_q_dispersion": (
                math.sqrt(
                    sum(
                        (value - sum(q_values) / len(q_values)) ** 2
                        for value in q_values
                    ) / len(q_values)
                ) if q_values else 0.0
            ),
            "n_firms_q_above_1": sum(value > 1.0 for value in q_values),
            "equity_wealth_share":
                total_equity / max(1.0, household_assets + total_equity),
            "equity_ownership_gini": _gini(
                _number(item.get("market_value"))
                for item in positions
                if int(item.get("security_kind", -1)) == 1
                and int(item.get("holder_kind", -1)) == 0
            ),
            "hh_wealth_gini_incl_equity": _gini(person_wealth),
            "hh_wealth_gini": _gini(household_wealth),
            "person_wealth_gini": _gini(person_wealth),
            "person_income_gini": _gini(
                _number(item.get("allocated_income"))
                for item in persons
            ),
            "energy_cost_share": energy_spending / max(1.0, nominal_output),
            "energy_flow_gap": point["energy_produced"] - energy_used,
            "energy_coverage_mean":
                point["energy_stock_total"] / max(1.0, energy_used),
            "poverty_gap": 0.0,
            "bottom10_consumption": (
                _median(sorted(consumption_values)[
                    :max(1, math.ceil(len(consumption_values) * 0.1))
                ]) if consumption_values else 0.0
            ),
            "median_real_household_income":
                _median(income_values) / max(1.0e-12, price_index),
            "savings_rate": (
                1.0 - sum(consumption_values) / max(1.0, sum(income_values))
            ),
            "welfare_log": (
                sum(math.log1p(value) for value in consumption_values)
                / max(1, len(consumption_values))
            ),
            "population_alive": population,
            "child_population": child_population,
            "adult_population": adult_population,
            "working_age_population": working_population,
            "elder_population": elder_population,
            "child_share": child_population / max(1, population),
            "adult_share": adult_population / max(1, population),
            "elder_share": elder_population / max(1, population),
            "child_dependency_ratio":
                child_population / max(1, working_population),
            "elder_dependency_ratio":
                elder_population / max(1, working_population),
            "birth_rate_per_1000_annualized":
                point["births_tick"] * 365_000.0 / max(1, population),
            "death_rate_per_1000_annualized":
                point["deaths_tick"] * 365_000.0 / max(1, population),
            "net_population_growth_rate_annualized": (
                (point["births_tick"] - point["deaths_tick"])
                * 365.0 / max(1, population)
            ),
            "child_median_consumption": _median(
                _number(item.get("allocated_consumption"))
                for item in persons
                if int(_number(item.get("age_days"))) // 365 < 18
            ),
            "adult_median_consumption": _median(
                _number(item.get("allocated_consumption"))
                for item in persons
                if 18 <= int(_number(item.get("age_days"))) // 365 < 65
            ),
            "elder_median_consumption": _median(
                _number(item.get("allocated_consumption"))
                for item in persons
                if int(_number(item.get("age_days"))) // 365 >= 65
            ),
            "firm_count_c": len(consumption_firms),
            "n_firms_producing": sum(
                _number(item.get("previous_sales")) > 0.0
                for item in active_firms
            ),
            "n_firms_selling": sum(
                _number(item.get("previous_sales")) > 0.0
                for item in active_firms
            ),
            "n_firms_borrowing": sum(
                _number(item.get("debt")) > 0.0 for item in active_firms
            ),
            "firm_size_gini_output": _gini(
                _number(item.get("previous_sales"))
                for item in active_firms
            ),
            "firm_size_top_share_output": _top_share(
                _number(item.get("previous_sales"))
                for item in active_firms
            ),
            "total_firm_book_equity": total_firm_book,
            "mortgage_count": sum(
                _safe_id(item.get("collateral_loan_id")) is not None
                for item in dwellings
            ),
            "tenant_share": sum(
                int(item.get("owner_kind", -1)) != 0
                for item in dwellings
                if _safe_id(item.get("occupant_household_id")) is not None
            ) / max(1, len(dwellings)),
            "rental_vacancies": sum(
                _safe_id(item.get("occupant_household_id")) is None
                for item in dwellings
            ),
            "landlord_count": len({
                int(item["owner_id"])
                for item in dwellings
                if int(item.get("owner_kind", -1)) == 0
            }),
        })
        return point

    @staticmethod
    def _jobs_by_person(
        jobs: Iterable[Mapping[str, Any]],
    ) -> dict[int, list[dict[str, Any]]]:
        result: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in jobs:
            person_id = _safe_id(item.get("person_id"))
            if person_id is not None:
                result[person_id].append(dict(item))
        return result

    def _household_snapshot(
        self,
        households: list[dict[str, Any]],
        persons: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        firms: list[dict[str, Any]],
        dwellings: list[dict[str, Any]],
        complete: bool,
    ) -> dict[str, Any]:
        person_by_id = {int(item["id"]): item for item in persons}
        firm_by_id = {int(item["id"]): item for item in firms}
        jobs_by_person = self._jobs_by_person(jobs)
        dwelling_by_household = {
            int(item["occupant_household_id"]): item
            for item in dwellings
            if _safe_id(item.get("occupant_household_id")) is not None
        }
        house_price = (
            _number(self.panel_history[-1].get("house_price"))
            if self.panel_history else 0.0
        )
        items: list[dict[str, Any]] = []
        for household in households:
            household_id = int(household["id"])
            member_rows: list[dict[str, Any]] = []
            for raw_id in household.get("member_ids", []):
                person_id = _safe_id(raw_id)
                person = person_by_id.get(person_id) if person_id else None
                if person is None:
                    continue
                age = int(_number(person.get("age_days"))) // 365
                employers = []
                for job in jobs_by_person.get(person_id, []):
                    firm_id = _safe_id(job.get("firm_id"))
                    firm = firm_by_id.get(firm_id) if firm_id else None
                    employers.append({
                        "firm_id": firm_id,
                        "sector_id": (
                            FIRM_SECTOR_IDS.get(
                                int(firm.get("sector", -1)), "unknown"
                            ) if firm else "unknown"
                        ),
                        "contract_id": (
                            "secondary" if job.get("secondary") else "primary"
                        ),
                        "status_id": (
                            "suspended" if job.get("suspended")
                            else "active" if job.get("active")
                            else "separated"
                        ),
                        "hours": _number(job.get("hours")),
                        "contract_hours": _number(job.get("hours")),
                        "wage": _number(job.get("wage")),
                        "hire_day": int(job.get("hire_day", 0)),
                    })
                active_jobs = [
                    item for item in employers
                    if item["status_id"] == "active"
                ]
                if active_jobs:
                    labor_status = "employed"
                elif age < 18:
                    labor_status = "minor"
                elif age >= 65:
                    labor_status = "retirement_age"
                elif not bool(person.get("participating")):
                    labor_status = "out_of_labor_force"
                else:
                    labor_status = "searching"
                assets = {
                    "cash": _number(person.get("cash")),
                    "firm_equity": _number(person.get("firm_equity")),
                    "bank_equity": _number(person.get("bank_equity")),
                    "bonds": _number(person.get("bonds")),
                    "housing": 0.0,
                    "total": _number(person.get("gross_assets")),
                }
                member_rows.append({
                    "person_id": person_id,
                    "age": age,
                    "age_days": int(person.get("age_days", 0)),
                    "sex_id": SEX_IDS.get(
                        int(person.get("sex", -1)), "unknown"
                    ),
                    "birth_day": int(person.get("birth_day", 0)),
                    "birth_date": date.fromordinal(
                        max(1, int(person.get("birth_day", 1)))
                    ).isoformat(),
                    "relationship_id": "member",
                    "marital_status_id": (
                        "partnered"
                        if _safe_id(person.get("partner_id")) is not None
                        else "unpartnered"
                    ),
                    "partner_id": _safe_id(person.get("partner_id")),
                    "mother_id": _safe_id(person.get("mother_id")),
                    "father_id": _safe_id(person.get("father_id")),
                    "guardian_id": _safe_id(person.get("guardian_id")),
                    "labor_status_id": labor_status,
                    "employer": active_jobs[0] if active_jobs else None,
                    "employers": employers,
                    "assets": assets,
                    "debt": _number(person.get("debt")),
                    "net_worth": _number(person.get("net_worth")),
                    "consumption":
                        _number(person.get("allocated_consumption")),
                    "income": {
                        "labor": _number(person.get("allocated_income")),
                        "capital": 0.0,
                        "transfer": 0.0,
                        "total": _number(person.get("allocated_income")),
                    },
                })
            dwelling = dwelling_by_household.get(household_id)
            housing_value = house_price if dwelling is not None else 0.0
            asset_components = {
                "cash": sum(
                    _number(item["assets"]["cash"]) for item in member_rows
                ),
                "firm_equity": sum(
                    _number(item["assets"]["firm_equity"])
                    for item in member_rows
                ),
                "bank_equity": sum(
                    _number(item["assets"]["bank_equity"])
                    for item in member_rows
                ),
                "bonds": sum(
                    _number(item["assets"]["bonds"]) for item in member_rows
                ),
                "housing": housing_value,
            }
            total_assets = sum(asset_components.values())
            debt = _number(household.get("debt"))
            items.append({
                "household_id": household_id,
                "account_id": int(household["account_id"]),
                "member_count": len(member_rows),
                "assets": {**asset_components, "total": total_assets},
                "debt": debt,
                "net_worth": total_assets - debt,
                "consumption": _number(household.get("spent")),
                "income": _number(household.get("income_realized")),
                "housing_units": 1.0 if dwelling is not None else 0.0,
                "desired_consumption":
                    _number(household.get("consumption_budget")),
                "members": member_rows,
            })
        return {
            "as_of_date": self._date_for_boundary(self.session.tick),
            "complete": complete,
            "summary": {
                "household_count": len(items),
                "population": sum(item["member_count"] for item in items),
                "total_assets": sum(
                    _number(item["assets"]["total"]) for item in items
                ),
                "total_debt": sum(_number(item["debt"]) for item in items),
                "total_net_worth": sum(
                    _number(item["net_worth"]) for item in items
                ),
                "total_consumption": sum(
                    _number(item["consumption"]) for item in items
                ),
            },
            "items": items,
        }

    def _firm_snapshot(
        self,
        firms: list[dict[str, Any]],
        persons: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        complete: bool,
    ) -> dict[str, Any]:
        person_by_id = {int(item["id"]): item for item in persons}
        jobs_by_firm: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for job in jobs:
            firm_id = _safe_id(job.get("firm_id"))
            if firm_id is not None:
                jobs_by_firm[firm_id].append(job)
        positions_by_equity: dict[int, list[dict[str, Any]]] = defaultdict(
            list
        )
        for position in positions:
            if int(position.get("security_kind", -1)) == 1:
                positions_by_equity[int(position["security_id"])].append(
                    position
                )
        items: list[dict[str, Any]] = []
        for firm in firms:
            firm_id = int(firm["id"])
            sector_id = FIRM_SECTOR_IDS.get(
                int(firm.get("sector", -1)), "unknown"
            )
            equity_id = _safe_id(firm.get("equity_id"))
            employees = []
            for job in jobs_by_firm.get(firm_id, []):
                person_id = _safe_id(job.get("person_id"))
                person = person_by_id.get(person_id) if person_id else None
                employees.append({
                    "person_id": person_id,
                    "household_id": (
                        _safe_id(person.get("household_id"))
                        if person else None
                    ),
                    "sex_id": (
                        SEX_IDS.get(int(person.get("sex", -1)), "unknown")
                        if person else "unknown"
                    ),
                    "age": (
                        int(_number(person.get("age_days"))) // 365
                        if person else None
                    ),
                    "contract_id": (
                        "secondary" if job.get("secondary") else "primary"
                    ),
                    "status_id": (
                        "suspended" if job.get("suspended")
                        else "active" if job.get("active")
                        else "separated"
                    ),
                    "hours": _number(job.get("hours")),
                    "contract_hours": _number(job.get("hours")),
                    "locked_wage": _number(job.get("wage")),
                    "paid_wage": _number(job.get("wage")),
                    "efficiency": (
                        _number(person.get("efficiency"), 1.0)
                        if person else 1.0
                    ),
                    "compensation":
                        _number(job.get("wage")) * _number(job.get("hours")),
                    "hire_day": int(job.get("hire_day", 0)),
                })
            shareholders = []
            for position in positions_by_equity.get(equity_id or -1, []):
                if int(position.get("holder_kind", -1)) != 0:
                    continue
                shares = _number(position.get("units"))
                outstanding = _number(firm.get("outstanding_shares"))
                shareholders.append({
                    "holder_kind_id": "household",
                    "holder_id": int(position["holder_id"]),
                    "household_id": int(position["holder_id"]),
                    "shares": shares,
                    "ownership": (
                        shares / outstanding if outstanding > 0.0 else 0.0
                    ),
                    "market_value": _number(position.get("market_value")),
                })
            market_cap = (
                _number(firm.get("outstanding_shares"))
                * _number(firm.get("share_price"))
            )
            book_equity = _number(firm.get("book_equity"))
            cash = _number(firm.get("cash"))
            debt = _number(firm.get("debt"))
            interest_arrears = _number(firm.get("interest_arrears"))
            inventory_units = _number(firm.get("goods_inventory"))
            capital_units = _number(firm.get("physical_capital"))
            price = _number(firm.get("posted_price"))
            wage = _number(firm.get("posted_wage"))
            earnings = _number(firm.get("earnings"))
            sales = _number(firm.get("previous_sales"))
            revenue = sales * price
            gross_assets = max(
                0.0, book_equity + debt + interest_arrears
            )
            condition_id = (
                "defaulted" if firm.get("defaulted")
                else (
                    "insolvent"
                    if int(firm.get("insolvent_days", 0)) > 0
                    else "operating"
                )
            )
            active_employees = [
                item for item in employees
                if item["status_id"] == "active"
            ]
            employment_fte = sum(
                _number(item.get("hours")) for item in active_employees
            )
            equity = {
                "enabled": equity_id is not None,
                "equity_id": equity_id,
                "share_price": _number(firm.get("share_price")),
                "last_share_price":
                    _number(firm.get("last_share_price")),
                "shares_outstanding":
                    _number(firm.get("outstanding_shares")),
                "market_cap": market_cap,
                "tobin_q": market_cap / max(1.0e-12, book_equity),
                "tobin_q_ema": _number(firm.get("tobin_q_ema")),
                "fundamental_per_share":
                    _number(firm.get("fundamental_per_share")),
                "share_trend": _number(firm.get("share_trend")),
                "residual_income_ema":
                    _number(firm.get("residual_income_ema")),
                "attractiveness": None,
                "shareholder_count": len(shareholders),
                "shares_observed": sum(
                    _number(item.get("shares")) for item in shareholders
                ),
                "ownership_coverage": (
                    sum(
                        _number(item.get("shares"))
                        for item in shareholders
                    ) / max(
                        1.0e-12,
                        _number(firm.get("outstanding_shares")),
                    )
                ),
                "shareholders": shareholders,
            }
            items.append({
                "firm_id": firm_id,
                "symbol": f"F{firm_id:04d}",
                "sector_id": sector_id,
                "sector_code": sector_id,
                "sector": sector_id,
                "active": bool(firm.get("active")),
                "condition_id": condition_id,
                "condition": condition_id,
                "state_owned": False,
                "sells": sector_id,
                "technology": "native_current",
                "invests": sector_id in {
                    "consumption", "energy", "construction"
                },
                "bank": {"bank_id": None, "loan_rate": None},
                "cash": cash,
                "debt": debt,
                "book_equity": book_equity,
                "inventory": inventory_units,
                "capital_units": capital_units,
                "price": price,
                "wage": wage,
                "markup": _number(firm.get("markup")),
                "employee_count": len(employees),
                "employment_fte": employment_fte,
                "employees": employees,
                "operations": {
                    "capital_service_pricing_enabled": False,
                    "demand_expected":
                        _number(firm.get("demand_expected")),
                    "target_inventory": None,
                    "production_target": None,
                    "produced": None,
                    "sales": sales,
                    "revenue": revenue,
                    "inventory": inventory_units,
                    "rationed_demand": None,
                    "production_realization": None,
                    "sales_realization": None,
                    "price": price,
                    "wage": wage,
                    "markup": _number(firm.get("markup")),
                    "wagebill": None,
                    "pricing_capital_unit_cost": None,
                    "pricing_capital_service_cost": None,
                    "pricing_capital_service_rate": None,
                    "profit": earnings,
                    "earnings": earnings,
                },
                "labor": {
                    "active_heads": len(active_employees),
                    "contract_count": len(employees),
                    "employment_fte": employment_fte,
                    "efficiency_units": sum(
                        _number(item.get("hours"))
                        * _number(item.get("efficiency"), 1.0)
                        for item in active_employees
                    ),
                    "labor_demand_notional": None,
                    "labor_demand_effective": None,
                    "vacancies": None,
                    "vacancy_age": 0,
                    "employees": employees,
                },
                "capital": {
                    "units": capital_units,
                    "previous_units": None,
                    "investment_target": None,
                    "investment": None,
                    "depreciation_rate": None,
                    "energy_input_stock": None,
                    "energy_input_average_cost": None,
                    "energy_input_stock_cost": None,
                    "energy_bought": None,
                    "energy_used": None,
                    "energy_cost_used": None,
                    "capacity": None,
                },
                "parameters": {
                    "demand_adjustment": None,
                    "inventory_target_ratio": None,
                    "markup_adjustment": None,
                    "markup_min": None,
                    "markup_max": None,
                    "wage_adjustment": None,
                    "labor_productivity":
                        _number(firm.get("productivity")),
                    "tfp":
                        _number(firm.get("total_factor_productivity")),
                    "capital_share": None,
                    "capital_output_target": None,
                    "investment_adjustment": None,
                    "dividend_payout_ratio": None,
                    "coordination_cost_slope": None,
                    "energy_intensity": None,
                    "capacity_kappa": None,
                },
                "signals": {
                    "previous_sales":
                        _number(firm.get("previous_sales")),
                    "previous_hiring":
                        _number(firm.get("previous_hires")),
                    "previous_effective_labor_demand": None,
                    "previous_target_inventory": None,
                    "previous_rationed_demand": None,
                    "sector_switch_pressure":
                        int(firm.get("sector_switch_pressure_days", 0)),
                    "dividend_shortfall": None,
                    "idle_ticks": int(firm.get("shell_days", 0)),
                    "insolvent_ticks":
                        int(firm.get("insolvent_days", 0)),
                    "subscale_ticks": 0,
                },
                "balance_sheet": {
                    "valuation_basis": "replacement_cost",
                    "priced_book_enabled": False,
                    "cash": cash,
                    "capital_units": capital_units,
                    "capital_unit_price": None,
                    "capital_value": None,
                    "output_inventory_units": inventory_units,
                    "output_inventory_unit_price": price,
                    "output_inventory_value":
                        inventory_units * price,
                    "work_in_progress_units": None,
                    "work_in_progress_value": None,
                    "input_inventory_units": None,
                    "input_inventory_value": None,
                    "inventory_value": inventory_units * price,
                    "gross_assets": gross_assets,
                    "debt": debt,
                    "interest_arrears": interest_arrears,
                    "book_equity": book_equity,
                    "eligible_collateral_value":
                        _number(firm.get("eligible_collateral_value")),
                    "borrowing_base_proxy": (
                        _number(firm.get("eligible_collateral_value"))
                    ),
                    "borrowing_base_headroom":
                        _number(firm.get("borrowing_base_headroom")),
                    "capital_haircut": None,
                    "inventory_haircut": None,
                },
                "pnl": {
                    "full_statement": False,
                    "revenue": revenue,
                    "revenue_carry_opening": None,
                    "revenue_carry": None,
                    "intermediate_inputs": None,
                    "compensation": None,
                    "ebitda": earnings,
                    "capital_price": None,
                    "depreciation": None,
                    "ebit": None,
                    "interest_accrued": None,
                    "interest_due": None,
                    "interest_paid": None,
                    "interest_shortfall": None,
                    "interest_arrears_opening": None,
                    "interest_arrears": interest_arrears,
                    "pre_tax_income": earnings,
                    "profit_tax": None,
                    "windfall_tax": None,
                    "net_income": earnings,
                    "dividends": None,
                    "retained_earnings": None,
                },
                "income_statement": {
                    "sales": sales,
                    "earnings": earnings,
                },
                "equity": equity,
            })
        return {
            "as_of_date": self._date_for_boundary(self.session.tick),
            "complete": complete,
            "summary": {
                "firm_count": len(items),
                "active_count": sum(bool(item["active"]) for item in items),
                "employment_fte": sum(
                    _number(item["employment_fte"]) for item in items
                ),
                "total_cash": sum(_number(item["cash"]) for item in items),
                "total_debt": sum(_number(item["debt"]) for item in items),
                "total_book_equity": sum(
                    _number(item["book_equity"]) for item in items
                ),
                "total_revenue": sum(
                    _number(item["operations"]["revenue"])
                    for item in items
                ),
                "total_earnings": sum(
                    _number(item["operations"]["earnings"])
                    for item in items
                ),
                "total_assets": sum(
                    _number(item["balance_sheet"]["gross_assets"])
                    for item in items
                ),
                "total_market_cap": sum(
                    _number(item["equity"]["market_cap"])
                    for item in items
                ),
            },
            "items": items,
        }

    def _stock_snapshot(
        self,
        firm_snapshot: Mapping[str, Any],
        banks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        listings: list[dict[str, Any]] = []
        for firm in firm_snapshot["items"]:
            equity = firm["equity"]
            if not equity["enabled"]:
                continue
            price = _number(equity["share_price"])
            last_price = _number(equity["last_share_price"])
            market_cap = _number(equity["market_cap"])
            listings.append({
                "symbol": firm["symbol"],
                "instrument_type": "company",
                "issuer_kind_id": "firm",
                "issuer_id": firm["firm_id"],
                "sector_id": firm["sector_id"],
                "price": price,
                "last_price": last_price,
                "change": (
                    price / last_price - 1.0
                    if last_price > 1.0e-12 else 0.0
                ),
                "market_cap": market_cap,
                "tobin_q": _number(equity["tobin_q"]),
                "fundamental": _number(
                    equity["fundamental_per_share"]
                ),
                "fundamental_gap": (
                    price / max(
                        1.0e-12,
                        _number(equity["fundamental_per_share"]),
                    ) - 1.0
                ),
                "can_open_firm": True,
            })
        for bank in banks:
            equity_id = _safe_id(bank.get("equity_id"))
            if equity_id is None:
                continue
            price = _number(bank.get("share_price"))
            last_price = _number(bank.get("last_share_price"))
            shares = _number(bank.get("outstanding_shares"))
            book = _number(bank.get("closing_capital"))
            listings.append({
                "symbol": f"B{int(bank['id']):03d}",
                "instrument_type": "bank",
                "issuer_kind_id": "bank",
                "issuer_id": int(bank["id"]),
                "sector_id": "banking",
                "price": price,
                "last_price": last_price,
                "change": (
                    price / last_price - 1.0
                    if last_price > 1.0e-12 else 0.0
                ),
                "market_cap": price * shares,
                "price_to_book": (
                    price * shares / max(1.0e-12, book)
                ),
                "fundamental": _number(
                    bank.get("fundamental_per_share")
                ),
                "fundamental_gap": (
                    price / max(
                        1.0e-12,
                        _number(bank.get("fundamental_per_share")),
                    ) - 1.0
                ),
                "can_open_firm": False,
            })
        market_cap = sum(_number(item["market_cap"]) for item in listings)
        previous_cap = (
            _number(self.stock_history[-1].get("market_cap"))
            if self.stock_history else market_cap
        )
        index_level = (
            1000.0 if not self.stock_history
            else _number(self.stock_history[-1].get("index_level"), 1000.0)
            * market_cap / max(1.0e-12, previous_cap)
        )
        corporate_cap = sum(
            _number(item["market_cap"]) for item in listings
            if item["instrument_type"] == "company"
        )
        bank_cap = market_cap - corporate_cap
        advances = sum(_number(item["change"]) > 1.0e-12 for item in listings)
        declines = sum(_number(item["change"]) < -1.0e-12 for item in listings)
        point = {
            "tick": self.session.tick,
            "index_level": index_level,
            "index_return": (
                0.0 if not self.stock_history
                else index_level
                / max(
                    1.0e-12,
                    _number(
                        self.stock_history[-1].get("index_level"),
                        index_level,
                    ),
                )
                - 1.0
            ),
            "market_cap": market_cap,
            "corporate_market_cap": corporate_cap,
            "bank_market_cap": bank_cap,
            "turnover": (
                _number(self.panel_history[-1].get("equity_turnover"))
                if self.panel_history else 0.0
            ),
            "advances": advances,
            "declines": declines,
            "unchanged": max(0, len(listings) - advances - declines),
            "prices": {
                item["symbol"]: item["price"] for item in listings
            },
            "market_caps": {
                item["symbol"]: item["market_cap"] for item in listings
            },
            "returns": {
                item["symbol"]: item["change"] for item in listings
            },
        }
        self.stock_history.append(point)
        sectors = []
        by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for listing in listings:
            by_sector[str(listing["sector_id"])].append(listing)
        for sector_id, group in sorted(by_sector.items()):
            group_cap = sum(_number(item["market_cap"]) for item in group)
            change = (
                sum(
                    _number(item["change"]) * _number(item["market_cap"])
                    for item in group
                ) / max(1.0e-12, group_cap)
            )
            sectors.append({
                "sector_id": sector_id,
                "change": change,
                "market_cap": group_cap,
                "count": len(group),
            })
        q_values = [
            _number(item.get("tobin_q"))
            for item in listings if item["instrument_type"] == "company"
        ]
        latest_panel = self.panel_history[-1] if self.panel_history else {}
        return {
            "as_of_date": self._date_for_boundary(self.session.tick),
            "index_id": "all_share",
            "summary": {
                "index_level": index_level,
                "index_change": point["index_return"],
                "market_cap": market_cap,
                "corporate_market_cap": corporate_cap,
                "bank_market_cap": bank_cap,
                "listed_count": len(listings),
                "turnover": point["turnover"],
                "advances": advances,
                "declines": declines,
                "unchanged": point["unchanged"],
                "q_mean": sum(q_values) / len(q_values) if q_values else 0.0,
                "ownership_gini": _number(
                    latest_panel.get("equity_ownership_gini")
                ),
                "equity_wealth_share": _number(
                    latest_panel.get("equity_wealth_share")
                ),
            },
            "sectors": sectors,
            "listings": listings,
            "history": list(self.stock_history),
        }

    def _panel_details(
        self,
        persons: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        firms: list[dict[str, Any]],
        households: list[dict[str, Any]],
    ) -> dict[str, Any]:
        active_persons = [
            item for item in persons if bool(item.get("alive", True))
        ]
        active_jobs = [
            item for item in jobs
            if bool(item.get("active")) and not bool(item.get("suspended"))
        ]
        firm_by_id = {int(item["id"]): item for item in firms}
        jobs_by_person = {
            int(item["person_id"]) for item in active_jobs
            if _safe_id(item.get("person_id")) is not None
        }
        pyramid = []
        for label_id, low, high in (
            ("age_0_14", 0, 14),
            ("age_15_24", 15, 24),
            ("age_25_34", 25, 34),
            ("age_35_44", 35, 44),
            ("age_45_54", 45, 54),
            ("age_55_64", 55, 64),
            ("age_65_plus", 65, 200),
        ):
            bucket = [
                item for item in active_persons
                if low <= int(_number(item.get("age_days"))) // 365 <= high
            ]
            pyramid.append({
                "label_id": label_id,
                "male": sum(int(item.get("sex", -1)) == 1 for item in bucket),
                "female": sum(
                    int(item.get("sex", -1)) == 0 for item in bucket
                ),
            })
        participation = []
        for label_id, low, high in (
            ("age_18_24", 18, 24),
            ("age_25_34", 25, 34),
            ("age_35_44", 35, 44),
            ("age_45_54", 45, 54),
            ("age_55_64", 55, 64),
        ):
            group = [
                item for item in active_persons
                if low <= int(_number(item.get("age_days"))) // 365 <= high
            ]
            participating = sum(
                bool(item.get("participating")) for item in group
            )
            employed = sum(int(item["id"]) in jobs_by_person for item in group)
            participation.append({
                "label_id": label_id,
                "population": len(group),
                "participation_rate":
                    participating / max(1, len(group)),
                "employment_rate": employed / max(1, len(group)),
            })
        sector_hours: dict[str, float] = defaultdict(float)
        for job in active_jobs:
            firm = firm_by_id.get(int(job.get("firm_id", -1)))
            sector_id = (
                FIRM_SECTOR_IDS.get(int(firm.get("sector", -1)), "unknown")
                if firm else "unknown"
            )
            sector_hours[sector_id] += _number(job.get("hours"))
        employment_sectors = [
            {"sector_id": key, "value": value}
            for key, value in sorted(sector_hours.items())
        ]
        working = [
            item for item in active_persons
            if 18 <= int(_number(item.get("age_days"))) // 365 < 65
        ]
        employed = sum(int(item["id"]) in jobs_by_person for item in working)
        out = sum(
            not bool(item.get("participating")) for item in working
        )
        searching = max(0, len(working) - employed - out)
        latest = self.panel_history[-1] if self.panel_history else {}
        states = [
            {"state_id": "employed", "value": employed},
            {"state_id": "searching", "value": searching},
            {"state_id": "out_of_labor_force", "value": out},
        ]
        flows = [
            {
                "flow_id": "hires",
                "from_id": "searching",
                "to_id": "employed",
                "value": _number(latest.get("labor_hires_total")),
            },
            {
                "flow_id": "separations",
                "from_id": "employed",
                "to_id": "searching",
                "value": _number(latest.get("labor_churn_seps_total")),
            },
        ]
        sectors = []
        for sector_id in FIRM_SECTOR_IDS.values():
            group = [
                item for item in firms
                if FIRM_SECTOR_IDS.get(
                    int(item.get("sector", -1)), "unknown"
                ) == sector_id
            ]
            sectors.append({
                "sector_id": sector_id,
                "firm_count": len(group),
                "sales": sum(
                    _number(item.get("previous_sales")) for item in group
                ),
                "inventory": sum(
                    _number(item.get("goods_inventory")) for item in group
                ),
                "capital": sum(
                    _number(item.get("physical_capital")) for item in group
                ),
                "employment": _number(sector_hours.get(sector_id)),
            })
        income = [
            _number(item.get("income_realized")) for item in households
        ]
        wealth = [
            max(0.0, _number(item.get("cash")) - _number(item.get("debt")))
            for item in households
        ]
        consumption = [
            _number(item.get("spent")) for item in households
        ]
        firm_bubbles = [{
            "firm_id": int(item["id"]),
            "sector_id": FIRM_SECTOR_IDS.get(
                int(item.get("sector", -1)), "unknown"
            ),
            "q": _number(item.get("tobin_q_ema")),
            "investment": max(0.0, _number(item.get("earnings"))),
            "market_cap": (
                _number(item.get("share_price"))
                * _number(item.get("outstanding_shares"))
            ),
        } for item in firms if _safe_id(item.get("equity_id")) is not None]
        return {
            "population": {"pyramid": pyramid},
            "labor": {
                "participation_by_age": participation,
                "employment_sectors": employment_sectors,
                "states": states,
                "flows": flows,
            },
            "real_economy": {"sectors": sectors},
            "distribution": {
                "income": _distribution(income),
                "wealth": _distribution(wealth),
                "consumption": _distribution(consumption),
            },
            "capital_market": {"firms": firm_bubbles},
        }

    def _world_point(
        self, frame: Mapping[str, Any]
    ) -> dict[str, Any]:
        economies = []
        exchange_rates = []
        nfa = []
        current_account = []
        migrants = []
        remittances = []
        imports = []
        exports = []
        tariff = []
        dealer = []
        pegs = []
        policies = [
            self.session.policy_values(index)
            for index in range(len(frame["economies"]))
        ]
        for economy_id, row in enumerate(frame["economies"]):
            metric = lambda key: self._metric(row, key)
            nominal = metric("metric.source.m4.nominal_output")
            price = metric("metric.economy.price_index")
            economy = {
                "economy_id": economy_id,
                "real_output": metric("metric.economy.real_output"),
                "production_realization_rate": (
                    metric("metric.economy.real_output")
                    / max(
                        1.0,
                        metric(
                            "metric.source.m4.consumption_output_real"
                        )
                        + metric(
                            "metric.source.m4.capital_output_real"
                        ),
                    )
                ),
                "unemployment_rate":
                    metric("metric.economy.unemployment_rate"),
                "underemployed_share": (
                    metric("metric.source.m7.underemployed_heads")
                    / max(1.0, metric("metric.source.m7.population"))
                ),
                "inflation": metric("metric.economy.inflation"),
                "inflation_target": _number(
                    policies[economy_id].get("inflation_target")
                ),
                "price_index": price,
                "avg_wage": metric("metric.economy.avg_wage"),
                "real_wage":
                    metric("metric.economy.avg_wage") / max(1.0e-12, price),
                "policy_rate": metric("metric.economy.policy_rate"),
                "population_alive":
                    metric("metric.economy.population_alive"),
                "gov_debt_to_gdp":
                    metric("metric.economy.gov_debt_to_gdp"),
                "gov_deficit_to_gdp":
                    metric("metric.economy.gov_deficit_to_gdp"),
                "total_credit":
                    metric("metric.source.m5.total_loan_principal"),
                "bank_capital":
                    metric("metric.source.m5.total_bank_capital"),
                "writeoffs":
                    metric("metric.source.m5.realized_credit_losses"),
                "total_debt_service_ratio": (
                    metric("metric.source.m5.principal_repaid")
                    + metric("metric.source.m5.loan_interest_paid")
                ) / max(1.0, nominal),
                "poverty_rate": metric("metric.economy.poverty_rate"),
                "income_gini": metric("metric.economy.income_gini"),
                "energy_price": metric("metric.economy.energy_price"),
                "energy_produced":
                    metric("metric.source.m8.energy.production"),
                "energy_used": metric("metric.source.m8.energy.sold"),
                "energy_stock_total":
                    metric("metric.economy.energy_stock_total"),
                "spr_stock": metric(
                    "metric.source.m8.energy.strategic_reserve_stock"
                ),
            }
            economies.append(economy)
            exchange_rates.append(metric("metric.world.e"))
            nfa.append(metric("metric.world.nfa"))
            current_account.append(metric("metric.world.current_account"))
            migrants.append(metric("metric.world.migrant_stock"))
            remittances.append(metric("metric.world.remittances"))
            imports.append(
                metric("metric.source.m9.country.imports_value")
            )
            exports.append(
                metric("metric.source.m9.country.exports_volume")
            )
            tariff.append(
                metric("metric.source.m9.country.tariff_revenue")
            )
            dealer.append(metric(
                "metric.source.m9.world.dealer_valuation"
            ))
            pegs.append(
                bool(metric("metric.source.m9.world.peg_intact"))
            )
        return {
            "tick": self.session.tick,
            "economies": economies,
            "e": exchange_rates,
            "nfa": nfa,
            "current_account": current_account,
            "migrant_stock": migrants,
            "remittances": remittances,
            "import_value": imports,
            "export_delivered_volume": exports,
            "tariff_rev": tariff,
            "dealer_valuation": dealer[0] if dealer else 0.0,
            "peg_intact": all(pegs) if pegs else True,
        }

    def _date_for_boundary(self, boundary: int) -> str:
        return (
            date.fromisoformat(self.spec.start_date)
            + timedelta(days=boundary)
        ).isoformat()

    def refresh(self) -> None:
        frame = self.session.maintained_metrics()
        diagnostics = self.session.probe_economy_diagnostics(
            self.player_economy
        )
        household_rows, households_complete = self._all_rows("households")
        person_rows, persons_complete = self._all_rows("persons")
        job_rows, jobs_complete = self._all_rows("jobs")
        firm_rows, firms_complete = self._all_rows("firms")
        bank_rows, banks_complete = self._all_rows("banks")
        dwelling_rows, dwellings_complete = self._all_rows("dwellings")
        equity_rows, equities_complete = self._all_rows("equities")
        position_rows, positions_complete = self._all_rows(
            "security_positions"
        )
        del equity_rows
        row = frame["economies"][self.player_economy]
        policy = self.session.policy_values(self.player_economy)
        panel_point = self._panel_point(
            row,
            diagnostics,
            household_rows,
            person_rows,
            firm_rows,
            bank_rows,
            dwelling_rows,
            position_rows,
            policy,
        )
        self.panel_history.append(panel_point)
        world_point = self._world_point(frame)
        world_point["dealer_valuation"] = _number(
            diagnostics.get("dealer_valuation")
        )
        world_point["peg_intact"] = bool(
            diagnostics.get("pegs_intact", True)
        )
        self.world_history.append(world_point)
        complete = all((
            households_complete,
            persons_complete,
            jobs_complete,
            firms_complete,
            banks_complete,
            dwellings_complete,
            equities_complete,
            positions_complete,
        ))
        self.households = self._household_snapshot(
            household_rows,
            person_rows,
            job_rows,
            firm_rows,
            dwelling_rows,
            complete,
        )
        self.firms = self._firm_snapshot(
            firm_rows,
            person_rows,
            job_rows,
            position_rows,
            complete,
        )
        self.stock_market = self._stock_snapshot(
            self.firms, bank_rows
        )
        self.panel_details = self._panel_details(
            person_rows, job_rows, firm_rows, household_rows
        )
        self.current_frame = {
            "boundary": int(frame["tick"]),
            "economies": [dict(item) for item in frame["economies"]],
        }
        self.entity_counts = {
            key: int(diagnostics[key])
            for key in (
                "households",
                "firms",
                "banks",
                "persons_alive",
                "jobs_active",
                "dwellings_active",
            )
        }

    def snapshot_fields(self) -> dict[str, Any]:
        latest_world = (
            self.world_history[-1] if self.world_history else {}
        )
        countries = [{
            "economy_id": index,
            "country_id": country.code.lower(),
            "code": country.code,
            "profile_id": country.profile,
        } for index, country in enumerate(self.spec.countries)]
        configs = self.spec.configs()
        config = configs[self.player_economy]
        capabilities = {
            name: bool(getattr(config, name, False))
            for name in (
                "national_accounts_metrics",
                "demographics_enabled",
                "housing_enabled",
                "housing_market_enabled",
                "mortgage_enabled",
                "housing_rental_enabled",
                "housing_construction_enabled",
                "firm_dynamics",
                "sector_switching",
                "bank_enabled",
                "household_credit",
                "capital_market",
                "energy_enabled",
            )
        }
        latest_panel = (
            dict(self.panel_history[-1]) if self.panel_history else {}
        )
        latest_panel.pop("metric_values", None)
        return {
            "metrics": latest_panel,
            "metric_values": dict(
                self.panel_history[-1]["metric_values"]
            ) if self.panel_history else {},
            "series": [
                {
                    key: value for key, value in point.items()
                    if key != "metric_values"
                }
                for point in self.panel_history
            ],
            "panel_details": self.panel_details,
            "capabilities": capabilities,
            "households": self.households,
            "firms": self.firms,
            "stock_market": self.stock_market,
            "world": {
                "countries": countries,
                "player_economy": self.player_economy,
                "latest": latest_world,
                "history": list(self.world_history),
            },
            "maintained_metrics": self.current_frame,
            "entity_counts": dict(self.entity_counts),
        }
