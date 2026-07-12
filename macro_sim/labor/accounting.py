"""v16-L0 labor accounting: the state taxonomy, the stocks, and the hard gate.

The labor A5. Five states — E (employed), U (unemployed, searching), S (suspended,
L1b), JG (job-guarantee), OLF (out of the labor force) — must partition the
working-age population every tick, and from L1 on every stock delta must equal its
named flows (hires, churn, demand-gap layoffs, bankruptcy layoffs, deaths, recalls).

Under the SPOT market (labor_matching="spot", the certified default) person states
are not yet real objects: employment is a household-level quantity re-derived every
tick. L0 therefore ships the accounting SHELL with aggregate stocks derived from the
spot quantities (the identity is arithmetic there — its teeth arrive with L1's
rosters), the flow counters (zero under spot), the vacancy stock (unfilled effective
demand — real under spot already), and the per-tick gate wired into phase 5. Every
later stage reports into THIS object; the gauges never move again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TOL = 1e-6


@dataclass
class LaborAccounts:
    # stocks (per tick; derived under spot, true stocks from L1 on)
    employed: float = 0.0
    unemployed: float = 0.0
    suspended: float = 0.0          # L1b state; identically 0 before it
    job_guarantee: float = 0.0
    out_of_labor_force: float = 0.0
    labor_supply: float = 0.0       # Σ person labor supply (working-age mass)
    vacancies: float = 0.0          # unfilled effective labor demand (real under spot)

    # cumulative flow counters (all zero under spot; L1 populates them)
    hires_total: float = 0.0
    churn_seps_total: float = 0.0       # exogenous quits + individual dismissals
    layoff_seps_total: float = 0.0      # demand-gap layoffs
    bankruptcy_seps_total: float = 0.0  # firm-exit mass layoffs
    death_seps_total: float = 0.0
    recalls_total: float = 0.0          # suspension -> employed (L1b)

    def observe_spot(self, econ: Any) -> None:
        """Derive the aggregate stocks from the spot market's household quantities."""
        bridge = getattr(econ, "demographic_bridge", None)
        employed = jg = supply = 0.0
        for h in econ.households:
            employed += float(getattr(h, "labor_sold", 0.0))
            jg += float(getattr(h, "jg_labor", 0.0))
            supply += (bridge.household_labor_supply(h.id) if bridge is not None else 1.0)
        self.employed = employed
        self.job_guarantee = jg
        self.unemployed = max(0.0, supply - employed - jg)
        self.labor_supply = supply
        self.suspended = 0.0
        if bridge is not None:
            state = bridge._demographic_state_ref()
            persons = sum(1 for p in getattr(state, "people", []) if p.alive) if state else 0
            self.out_of_labor_force = max(0.0, float(persons) - supply)
        else:
            self.out_of_labor_force = 0.0
        self.vacancies = sum(
            max(0.0, float(f.labor_demand_eff) - float(f.hired)) for f in econ.firms
        )

    def assert_identity(self) -> None:
        lhs = self.employed + self.unemployed + self.suspended + self.job_guarantee
        if abs(lhs - self.labor_supply) > _TOL * max(1.0, self.labor_supply):
            raise AssertionError(
                f"labor stock identity failed: E+U+S+JG={lhs} != supply={self.labor_supply} "
                f"(E={self.employed} U={self.unemployed} S={self.suspended} JG={self.job_guarantee})"
            )
        for name in ("employed", "unemployed", "suspended", "job_guarantee",
                     "out_of_labor_force", "vacancies"):
            if getattr(self, name) < -_TOL:
                raise AssertionError(f"labor stock {name} went negative: {getattr(self, name)}")

    @property
    def unemployment_rate(self) -> float:
        force = self.employed + self.unemployed + self.suspended + self.job_guarantee
        return self.unemployed / force if force > 0.0 else 0.0

    @property
    def vacancy_rate(self) -> float:
        force = self.employed + self.unemployed + self.suspended + self.job_guarantee
        return self.vacancies / force if force > 0.0 else 0.0
