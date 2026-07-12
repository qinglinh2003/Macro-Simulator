"""v16-L1 persistent labor market: person-level rosters and the four separations.

Employment attaches to PERSONS (the settled architecture decision): a Job is a
(person, firm) link with a real hire date. The tick processes FLOWS, never the stock:

  1. sweep exits      -- deaths and age-outs leave rosters (the taxonomy's exit class)
  2. churn            -- exogenous quits + individual dismissals, one daily hazard
  3. demand-gap fires -- lambda_fire x (roster - target - band), LIFO: labor HOARDING
                         and Okun's law live here (this is the old labor_adjust thread)
  4. cash-crunch fires-- roster forced down to what live deposits can pay (A4 first
                         line is the credit phase; suspension arrives in L1b)
  5. hiring           -- fill toward target from the searcher pool (instant in L1;
                         the matching function arrives in L2)
  6. wages            -- every roster member is paid firm.wage into their CURRENT
                         household account, attributed to the PERSON in the claims
                         layer (the Phase 3 gauges upgrade)

All randomness on a dedicated substream (econ._labor_rng); the main stream's
consumption order is untouched, so spot-mode runs stay bit-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.markets.matching import EPS


@dataclass
class Job:
    person_id: int
    firm_id: str
    hire_date: Any                  # datetime.date (real calendar; leap-safe anniversaries)


@dataclass
class LaborMarket:
    churn_annual: float = 0.28      # exogenous quits + individual dismissals (monthly ~2.4%)
    lambda_fire: float = 0.10       # per-tick closure rate of the layoff gap
    layoff_band: float = 0.05       # hysteresis: no action within +/- band x target

    jobs: dict[int, Job] = field(default_factory=dict)          # person_id -> Job
    rosters: dict[str, list[int]] = field(default_factory=dict) # firm_id -> hire-ordered ids

    def roster_of(self, firm_id: str) -> list[int]:
        return self.rosters.setdefault(firm_id, [])

    def hire(self, person_id: int, firm_id: str, date: Any) -> None:
        self.jobs[person_id] = Job(person_id=person_id, firm_id=firm_id, hire_date=date)
        self.roster_of(firm_id).append(person_id)

    def separate(self, person_id: int) -> None:
        job = self.jobs.pop(person_id, None)
        if job is not None:
            roster = self.rosters.get(job.firm_id)
            if roster is not None:
                try:
                    roster.remove(person_id)
                except ValueError:
                    pass

    def on_person_death(self, person_id: int, accounts: Any | None = None) -> None:
        if person_id in self.jobs:
            self.separate(person_id)
            if accounts is not None:
                accounts.death_seps_total += 1

    def on_firm_exit(self, firm_id: str, accounts: Any | None = None) -> None:
        """Bankruptcy / liquidation = the whole roster into the pool at once."""
        for person_id in list(self.rosters.get(firm_id, ())):
            self.separate(person_id)
            if accounts is not None:
                accounts.bankruptcy_seps_total += 1
        self.rosters.pop(firm_id, None)


def run_persistent_labor_phase(econ: Any) -> None:
    lm = econ.labor_market
    rng = econ._labor_rng
    bridge = econ.demographic_bridge
    accounts = econ.labor_accounts
    led = econ.ledger
    date = econ.demographic_state.current_date
    churn_daily = lm.churn_annual / 365.0

    person_index = {}
    supply_of = {}
    household_account_of = {}
    state = bridge._demographic_state_ref()
    from macro_sim.demographics.economic_state import labor_supply_for_person
    for person in state.people:
        if not person.alive or person.household_id is None:
            continue
        person_index[int(person.id)] = person
        supply_of[int(person.id)] = labor_supply_for_person(person)
        account = bridge.household_to_account.get(int(person.household_id))
        if account is not None:
            household_account_of[int(person.id)] = account

    # ---- 1. exit sweep: dead or aged-out members leave rosters (sweep, not hooks:
    # guardianship moves and every future emptying path are covered by construction) ----
    for person_id in list(lm.jobs.keys()):
        person = person_index.get(person_id)
        if person is None:
            lm.separate(person_id)
            if accounts is not None:
                accounts.death_seps_total += 1
        elif supply_of.get(person_id, 0.0) <= 0.0 or person_id not in household_account_of:
            lm.separate(person_id)          # age-out (retirement): an exit, kept in the
            if accounts is not None:        # death/exit class of the fixed taxonomy
                accounts.death_seps_total += 1

    # ---- 2. churn: one daily hazard for quits + individual dismissals ----
    for person_id in list(lm.jobs.keys()):
        if rng.random() < churn_daily:
            lm.separate(person_id)
            if accounts is not None:
                accounts.churn_seps_total += 1

    # ---- 3. + 4. firm-side separations, then 5. hiring, then 6. wages ----
    firms_order = list(econ.firms)
    rng.shuffle(firms_order)

    # searcher pool: working-age, alive, jobless (shuffled once; consumed by pointer)
    pool = [
        pid for pid, s in supply_of.items()
        if s > 0.0 and pid not in lm.jobs and pid in household_account_of
    ]
    rng.shuffle(pool)
    pool_ptr = 0

    for f in firms_order:
        roster = lm.roster_of(f.id)
        target = max(0.0, float(f.labor_demand_eff))

        # 3. demand-gap layoffs with hysteresis + partial adjustment (LIFO)
        excess = len(roster) - target
        band = lm.layoff_band * max(1.0, target)
        if excess > band:
            fire_flow = lm.lambda_fire * (excess - band)
            n_fire = int(fire_flow)
            if rng.random() < fire_flow - n_fire:
                n_fire += 1
            for _ in range(min(n_fire, len(roster))):
                victim = roster[-1]                 # LIFO: the most recent hire
                lm.separate(victim)
                if accounts is not None:
                    accounts.layoff_seps_total += 1

        # 4. cash-crunch: the roster must be payable from live deposits (A4)
        wage = max(f.wage, EPS)
        affordable = int(led.balance(f.id) / wage)
        while len(roster) > affordable:
            victim = roster[-1]
            lm.separate(victim)
            if accounts is not None:
                accounts.layoff_seps_total += 1

        # 5. hiring: fill toward the target (instant in L1; matching friction = L2)
        while len(roster) + 1 <= target + 0.5 and pool_ptr < len(pool):
            if len(roster) + 1 > affordable:
                break                               # cash cap binds
            lm.hire(pool[pool_ptr], f.id, date)
            if accounts is not None:
                accounts.hires_total += 1
            pool_ptr += 1

        # 6. wages: every member paid at the posted wage into their CURRENT household
        for person_id in roster:
            account = household_account_of.get(person_id)
            if account is None:
                continue
            pay = min(wage, led.balance(f.id))
            if pay <= EPS:
                break
            led.transfer(f.id, account, pay)
            # per-PERSON attribution through the existing targeted-recipients API --
            # individual labor histories become real objects (Phase 3 gauges upgrade)
            bridge.post_labor_income(account, pay, worker_person_ids=[person_id])
            f.hired += 1.0
            f.wagebill += pay
            agent = bridge._household_agent(account)
            if agent is not None:
                agent.income_realized += pay
                agent.labor_sold += 1.0
