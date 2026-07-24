#!/usr/bin/env python3
"""Generate and validate the M3 exact equation fixture corpus."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

from macro_sim.behavior import planning


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "schemas/m3/fixtures/equations.json"


def load_vital_rates_module():
    """Load the pure oracle without importing optional visualization modules."""

    path = ROOT / "macro_sim/demographics/rates.py"
    specification = importlib.util.spec_from_file_location(
        "macro_sim_m3_vital_rates_oracle",
        path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load vital-rate oracle")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


VITAL_RATES = load_vital_rates_module()
Phase0VitalRates = VITAL_RATES.Phase0VitalRates
expected_life_at_birth = VITAL_RATES.expected_life_at_birth


def floor_safe_price_return(old_price: float, new_price: float) -> float:
    if old_price <= planning.EPS:
        return 0.0
    return (new_price - old_price) / old_price


def residual_income_fundamental(
    *,
    book_value: float,
    residual_income: float,
    shares_outstanding: float,
    discount_rate: float,
) -> float:
    if shares_outstanding <= planning.EPS:
        return 0.0
    premium = max(0.0, residual_income) / max(planning.EPS, discount_rate)
    return max(0.0, (book_value + premium) / shares_outstanding)


def bond_price(face: float, periods: int, rate: float, coupon: float) -> float:
    if periods <= 0 or rate <= -1.0 + planning.EPS:
        return face
    discount = 1.0 / (1.0 + rate)
    principal = face * discount ** periods
    if coupon <= 0.0:
        coupons = 0.0
    elif abs(rate) < 1e-12:
        coupons = coupon * face * periods
    else:
        coupons = coupon * face * (1.0 - discount ** periods) / rate
    return coupons + principal


class Draw:
    """One deterministic random draw compatible with planning functions."""

    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


def cases() -> list[dict[str, Any]]:
    return [
        {"kind": "adaptive_expectation", "values": [10.0, 14.0, 0.25]},
        {"kind": "demand_expectation", "values": [10.0, 8.0, 4.0, 0.5]},
        {"kind": "production", "values": [0, 4.0, 2.5, 1.0, 0.0, 0.3, 1.2]},
        {"kind": "production", "values": [1, 9.0, 1.0, 2.0, 16.0, 0.5, 1.0]},
        {"kind": "labor_demand", "values": [1, 24.0, 1.0, 2.0, 16.0, 0.5, 1.0]},
        {"kind": "capital_service_cost", "values": [3.0, 0.02, 100.0, 0.08]},
        {
            "kind": "capital_service_unit_cost",
            "values": [3.0, 0.02, 100.0, 0.08, 12.0, 15.0],
        },
        {
            "kind": "unit_cost",
            "values": [0, 6.0, 3.0, 1.0, 0.0, 0.3, 20.0, 8.0, 0.2, 5.0, 0.01, 0.5, 1],
        },
        {"kind": "production_plan", "values": [10.0, 2.0, 7.0, 0.25]},
        {
            "kind": "wage_plan",
            "values": [10.0, 4.0, 5.0, 0.1, 0.5, 0.2, 11.5, 0.0, 0.0, 0.0],
        },
        {
            "kind": "price_plan",
            "values": [8.0, 0.2, 0.1, 0.4, 0.05, 5.0, 3.0, 10.0, 0.8, 0.1],
        },
        {
            "kind": "investment_user_cost",
            "values": [0.06, 0.02, 0.04, 0.02, 0.01, 1.0, 0.5, 1.5, 1e-9],
        },
        {
            "kind": "investment_plan",
            "values": [
                1, 2.0, 10.0, 0.5, 12.0, 0.1, 1.5, 0.5, 0.5, 2.0,
                1, 0.06, 0.02, 0.04, 0.02, 0.1, 1.0, 0.5, 1.5, 1e-9,
            ],
        },
        {"kind": "firm_credit_request", "values": [4.0, 5.0, 3.0, 2.0, 8.0]},
        {
            "kind": "firm_debt_service_headroom",
            "values": [12.0, 10.0, 0.05, 0.05, 1.2],
        },
        {
            "kind": "credit_grant",
            "values": [40.0, 100.0, 20.0, 1.0, 0, 0.0, 1, 45.0, 1, 12.0, 10.0, 0.05, 0.05, 1.2],
        },
        {"kind": "debt_service", "values": [100.0, 15.0, 0.05, 0.1]},
        {"kind": "consumption_plan", "values": [0.8, 0.1, 10.0, 16.0, 0.0, 0.5, 4.0]},
        {
            "kind": "household_contractual_debt_service",
            "values": [100.0, 20.0, 0.02, 0.1, 3.0],
        },
        {
            "kind": "household_debt_service_reservation",
            "values": [40.0, 45.0, 100.0, 20.0, 0.02, 0.1, 3.0],
        },
        {"kind": "equity_demand", "values": [10.0, 12.0, 0.0, 100.0, 5.0, 0.5, 0.0, 0.4]},
        {"kind": "household_credit_request", "values": [8.0, 12.0, 2.0, 4.0]},
        {"kind": "floor_safe_price_return", "values": [10.0, 12.0]},
        {"kind": "valuation_discount_rate", "values": [0.01, -0.02, 0.03]},
        {"kind": "residual_income_fundamental", "values": [100.0, 10.0, 20.0, 0.1]},
        {"kind": "bond_price", "values": [100.0, 2, 0.1, 0.05]},
        {"kind": "female_birth_share", "values": []},
        {"kind": "male_birth_share", "values": []},
        {"kind": "mortality_integral", "values": [0.0, 1.0]},
        {"kind": "survival_probability", "values": [0.0, 1.0]},
        {"kind": "fertility_shape_rate", "values": [28.0]},
        {"kind": "fertility_rate", "values": [28.0]},
        {"kind": "expected_life_at_birth", "values": []},
    ]


def expected(case: dict[str, Any]) -> list[float]:
    kind = case["kind"]
    v = case["values"]
    if kind == "adaptive_expectation":
        hh = SimpleNamespace(y_expected=v[0], income_realized=v[1], lambda_y=v[2])
        planning.update_income_expectation(hh)
        return [hh.y_expected]
    if kind == "demand_expectation":
        firm = SimpleNamespace(
            demand_expected=v[0], sales_prev=v[1], rationed_prev=v[2], lambda_d=v[3],
        )
        planning.update_demand_expectation(firm)
        return [firm.demand_expected]
    if kind in {"production", "labor_demand"}:
        firm = SimpleNamespace(
            tech="linear" if v[0] == 0 else "cobb_douglas",
            a=v[2], A=v[3], capital=v[4], alpha=v[5],
        )
        value = (
            planning.produce(firm, v[1], v[6])
            if kind == "production"
            else planning.labor_demand_notional(firm, v[1], v[6])
        )
        return [value]
    if kind == "capital_service_cost":
        firm = SimpleNamespace(capital=v[2], delta_K=v[3])
        return [planning.capital_service_cost(
            firm, replacement_price=v[0], opportunity_rate=v[1],
        )]
    if kind == "capital_service_unit_cost":
        firm = SimpleNamespace(capital=v[2], delta_K=v[3], production_target=v[4])
        return [planning.capital_service_unit_cost(
            firm, replacement_price=v[0], opportunity_rate=v[1], min_output=v[5],
        )]
    if kind == "unit_cost":
        firm = SimpleNamespace(
            tech="linear" if v[0] == 0 else "cobb_douglas",
            wage=v[1], a=v[2], A=v[3], capital=v[4], alpha=v[5],
            production_target=v[6], labor_demand_notional=v[7],
            energy_intensity=v[8], energy_avg_cost=v[9], dis_slope=v[10],
        )
        return [planning.unit_cost(
            firm, v[11], productivity_adjusted=bool(v[12]),
        )]
    if kind == "production_plan":
        firm = SimpleNamespace(
            demand_expected=v[0], phi=v[1], inventory=v[2],
            target_inventory=0.0, production_target=0.0,
        )
        planning.plan_production(firm, v[3])
        return [firm.target_inventory, firm.production_target]
    if kind == "wage_plan":
        firm = SimpleNamespace(
            wage=v[0], hired_prev=v[1], labor_demand_eff_prev=v[2], omega=v[3],
        )
        planning.plan_wage(
            firm, Draw(v[5]), v[4], v[6], v[7], v[8], v[9],
        )
        drift = v[9] * v[8]
        rationed = v[1] < v[2] - planning.EPS
        target = v[0] * (1.0 + drift + v[3]) if rationed else v[0] * (1.0 + drift)
        return [target, firm.wage, float(rationed), float(v[5] < v[4]), float(firm.wage == v[6])]
    if kind == "price_plan":
        firm = SimpleNamespace(
            a=1.0, price=v[0], markup=v[1], mu_min=v[2], mu_max=v[3], eta=v[4],
            target_inventory_prev=v[5], inventory=v[6], tech="linear", wage=v[7],
            production_target=0.0, labor_demand_notional=0.0, energy_intensity=0.0,
            energy_avg_cost=0.0, dis_slope=0.0,
        )
        planning.plan_price(firm, Draw(v[9]), v[8])
        target = (1.0 + firm.markup) * v[7]
        return [firm.markup, target, firm.price, float(v[9] < v[8])]
    if kind == "investment_user_cost":
        return [planning.investment_user_cost_multiplier(
            nominal_loan_rate=v[0], expected_inflation=v[1],
            neutral_nominal_rate=v[2], inflation_target=v[3],
            depreciation=v[4], elasticity=v[5], multiplier_min=v[6],
            multiplier_max=v[7], user_cost_floor=v[8],
        )]
    if kind == "investment_plan":
        firm = SimpleNamespace(
            invests=bool(v[0]), v=v[1], demand_expected=v[2], lambda_I=v[3],
            capital=v[4], delta_K=v[5], tobin_q_ema=v[6], investment_target=0.0,
        )
        kwargs = {}
        if v[10]:
            kwargs = dict(
                nominal_loan_rate=v[11], expected_inflation=v[12],
                neutral_nominal_rate=v[13], inflation_target=v[14],
                user_cost_elasticity=v[16], user_cost_multiplier_min=v[17],
                user_cost_multiplier_max=v[18], user_cost_floor=v[19],
            )
        planning.plan_investment(firm, v[7], v[8], v[9], **kwargs)
        return [firm.investment_target]
    if kind == "firm_credit_request":
        firm = SimpleNamespace(
            wage=v[0], labor_demand_notional=v[1], investment_target=v[2],
        )
        return [planning.credit_request(firm, v[4], v[3])]
    if kind == "firm_debt_service_headroom":
        return [planning.firm_debt_service_headroom(
            expected_operating_cash_flow=v[0], debt=v[1], loan_rate=v[2],
            amort=v[3], min_dscr=v[4],
        )]
    if kind == "credit_grant":
        kwargs = {}
        if v[4]:
            kwargs["book_equity"] = v[5]
        if v[6]:
            kwargs["borrowing_base_proxy"] = v[7]
        if v[8]:
            kwargs.update(
                expected_operating_cash_flow=v[9], loan_rate=v[11],
                amort=v[12], min_dscr=v[13],
            )
        return [planning.credit_grant(v[0], v[1], v[2], v[3], **kwargs)]
    if kind == "debt_service":
        return list(planning.debt_service_amounts(v[0], v[1], v[2], v[3]))
    if kind == "consumption_plan":
        hh = SimpleNamespace(
            alpha1=v[0], alpha2=v[1], y_expected=v[2], consumption_budget=0.0,
        )
        planning.plan_consumption(hh, v[3], v[4], v[5], v[6])
        return [hh.consumption_budget]
    if kind == "household_contractual_debt_service":
        return [planning.household_contractual_debt_service(
            debt=v[0], margin_debt=v[1], loan_rate=v[2], amort=v[3], interest_arrears=v[4],
        )]
    if kind == "household_debt_service_reservation":
        return [planning.reserve_household_debt_service(
            v[0], deposits=v[1], debt=v[2], margin_debt=v[3],
            loan_rate=v[4], amort=v[5], interest_arrears=v[6],
        )]
    if kind == "equity_demand":
        hh = SimpleNamespace(shares=v[4])
        market = SimpleNamespace(price=v[0], fundamental=v[1], trend=v[2])
        cfg = SimpleNamespace(
            w_fundamental=v[5], w_chartist=v[6], theta_equity=v[7],
        )
        return [planning.plan_equity_demand(hh, market, v[3], cfg)]
    if kind == "household_credit_request":
        hh = SimpleNamespace(consumption_budget=v[0], y_expected=v[3])
        return list(planning.household_credit_request(hh, v[2], v[1]))
    if kind == "floor_safe_price_return":
        return [floor_safe_price_return(v[0], v[1])]
    if kind == "valuation_discount_rate":
        return [max(v[0], max(0.0, v[1]) + v[2])]
    if kind == "residual_income_fundamental":
        return [residual_income_fundamental(
            book_value=v[0], residual_income=v[1],
            shares_outstanding=v[2], discount_rate=v[3],
        )]
    if kind == "bond_price":
        return [bond_price(v[0], int(v[1]), v[2], v[3])]
    rates = Phase0VitalRates()
    if kind == "female_birth_share":
        return [rates.female_birth_share]
    if kind == "male_birth_share":
        return [rates.male_birth_share]
    if kind == "mortality_integral":
        return [rates.mortality_integral(v[0], v[1])]
    if kind == "survival_probability":
        return [rates.survival_probability(v[0], v[1])]
    if kind == "fertility_shape_rate":
        return [rates.fertility_shape_rate(v[0])]
    if kind == "fertility_rate":
        return [rates.fertility_rate(v[0])]
    if kind == "expected_life_at_birth":
        return [expected_life_at_birth(rates)]
    raise ValueError(f"unknown equation kind {kind}")


def document() -> dict[str, Any]:
    rows = []
    for case in cases():
        rows.append({**case, "expected": expected(case)})
    return {"schema_version": "m3-equation-fixtures-v1", "cases": rows}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    rendered = canonical(document())
    if arguments.write:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(rendered, encoding="utf-8")
        return 0
    if not FIXTURE.is_file() or FIXTURE.read_text(encoding="utf-8") != rendered:
        raise SystemExit("M3 equation fixture is absent or stale")
    print("M3 equation fixture: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
