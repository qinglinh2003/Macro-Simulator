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
    wage: float = 0.0               # L3: locked at hire; anniversary reviews ratchet it


@dataclass
class Suspension:
    firm_id: str
    since_tick: int
    wage_at: float                  # acceptance threshold base for on-pool search (theta x this)


@dataclass
class LaborMarket:
    churn_annual: float = 0.28      # exogenous quits + individual dismissals (monthly ~2.4%)
    lambda_fire: float = 0.03       # per-tick closure rate of the layoff gap
    layoff_band: float = 0.05       # hysteresis: no action within +/- band x target
    target_smooth: float = 0.02     # daily EMA on the FIRING target: hire fast, fire slow
                                    # (the anti-churn damper the L1 portrait demanded --
                                    # firing against raw daily targets cycled 2-8x the
                                    # workforce per year against a ~15%/yr real anchor)
    target_ema: dict[str, float] = field(default_factory=dict)
    # L1b suspension (the employment LOLR): liquidity != insolvency at the match level.
    # A suspended worker keeps the Job link (the recall right) but is NOT employed:
    # no pay, no work, no output -- and NO DEBT (zero new liability class). Under the
    # uncapped JG they are absorbed by the safety net automatically, so S is a MEMO
    # stock (recall rights), never a partition state.
    suspension_enabled: bool = False
    suspension_timer: int = 45      # ticks before an unrecalled suspension converts to layoff
    quit_discount: float = 0.9      # accept an outside offer iff wage >= this x suspended wage
    # L2 matching friction: hiring happens through CONTACTS, not a Walrasian sweep.
    # Each searcher contacts one random hiring firm per tick with prob search_intensity;
    # contacting a firm whose gap just filled wastes the contact (congestion). u* is the
    # balance of churn inflow against contact-success outflow (~2 months mean duration
    # at the defaults). JG workers hold no Job link, so they are searchers by
    # construction -- the buffer stock drains back to private employment.
    friction_enabled: bool = False
    search_intensity: float = 0.15
    # L3 relationship wages: the entry wage is LOCKED at hire; incumbents reprice only
    # at their hire anniversary, upward-only (per-person DNWR). The free-hire drift
    # delta keeps applying to the POSTED wage alone -- the v14 pass-through blocker's
    # cure: productivity gains reach incumbents through sticky wages + falling prices.
    relationship_wages: bool = False
    # L3b on-the-job ladder: incumbent wage discipline. Employed workers sample one
    # hiring firm at ladder_intensity; they switch iff posted >= wage x (1 + premium).
    job_ladder: bool = False
    ladder_intensity: float = 0.03
    ladder_premium: float = 0.05
    vacancy_age: dict[str, int] = field(default_factory=dict)   # consecutive gap ticks per firm

    jobs: dict[int, Job] = field(default_factory=dict)          # person_id -> Job
    rosters: dict[str, list[int]] = field(default_factory=dict) # firm_id -> hire-ordered ids
    suspended: dict[int, Suspension] = field(default_factory=dict)  # person_id -> Suspension

    def roster_of(self, firm_id: str) -> list[int]:
        return self.rosters.setdefault(firm_id, [])

    def hire(self, person_id: int, firm_id: str, date: Any, wage: float = 0.0) -> None:
        self.jobs[person_id] = Job(person_id=person_id, firm_id=firm_id,
                                   hire_date=date, wage=wage)
        self.roster_of(firm_id).append(person_id)

    def separate(self, person_id: int) -> None:
        job = self.jobs.pop(person_id, None)
        self.suspended.pop(person_id, None)
        if job is not None:
            roster = self.rosters.get(job.firm_id)
            if roster is not None:
                try:
                    roster.remove(person_id)
                except ValueError:
                    pass

    def wage_of(self, person_id: int, firm) -> float:
        """The wage a member is actually paid: relationship wage under L3, posted else."""
        if self.relationship_wages:
            job = self.jobs.get(person_id)
            if job is not None and job.wage > 0.0:
                return job.wage
        return max(float(firm.wage), 1e-12)

    def active_count(self, firm_id: str) -> int:
        return sum(1 for pid in self.rosters.get(firm_id, ()) if pid not in self.suspended)

    def on_person_death(self, person_id: int, accounts: Any | None = None) -> None:
        if person_id in self.jobs:
            was_suspended = person_id in self.suspended
            self.separate(person_id)
            if accounts is not None and not was_suspended:
                accounts.death_seps_total += 1    # suspended exits are S-side, not E-flows

    def on_firm_exit(self, firm_id: str, accounts: Any | None = None) -> None:
        """Bankruptcy / liquidation = the whole roster into the pool at once."""
        for person_id in list(self.rosters.get(firm_id, ())):
            was_suspended = person_id in self.suspended
            self.separate(person_id)
            if accounts is not None and not was_suspended:
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
        gone = person is None or supply_of.get(person_id, 0.0) <= 0.0 \
            or person_id not in household_account_of
        if gone:
            was_suspended = person_id in lm.suspended
            lm.separate(person_id)          # deaths AND age-outs: the exit class
            if accounts is not None and not was_suspended:
                accounts.death_seps_total += 1

    # ---- 1b. suspension lifecycle: timeouts convert to layoff (S-side, no E-flow) ----
    if lm.suspension_enabled:
        for person_id, susp in list(lm.suspended.items()):
            if econ.t - susp.since_tick >= lm.suspension_timer:
                lm.separate(person_id)
                if accounts is not None:
                    accounts.suspension_timeouts_total += 1

    # ---- 2. churn: one daily hazard for quits + individual dismissals (ACTIVE only:
    # a suspended worker has nothing to quit from -- their exit path is the pool) ----
    for person_id in list(lm.jobs.keys()):
        if person_id in lm.suspended:
            continue
        if rng.random() < churn_daily:
            lm.separate(person_id)
            if accounts is not None:
                accounts.churn_seps_total += 1

    # ---- 3. + 4. firm-side separations, then 5. hiring, then 6. wages ----
    firms_order = list(econ.firms)
    rng.shuffle(firms_order)

    # ---- 2b. (L3) anniversary reviews: incumbents reprice on their hire date,
    # UPWARD ONLY (per-person DNWR) toward the current posted wage. Feb-29 hires
    # review on Feb-28 in common years (real-calendar, leap-safe). ----
    firm_by_id = {f.id: f for f in econ.firms}
    if lm.relationship_wages:
        for job in lm.jobs.values():
            if job.person_id in lm.suspended:
                continue
            hd = job.hire_date
            month, day = hd.month, hd.day
            if month == 2 and day == 29 and not (date.year % 4 == 0 and (date.year % 100 != 0 or date.year % 400 == 0)):
                day = 28
            if (date.month, date.day) == (month, day) and date != hd:
                firm = firm_by_id.get(job.firm_id)
                if firm is not None:
                    job.wage = max(job.wage, float(firm.wage), float(econ.policy.min_wage))

    # searcher pool: the jobless PLUS the suspended (recall unemployment: they search
    # with a reservation of quit_discount x their suspended wage)
    pool = [
        pid for pid, s in supply_of.items()
        if s > 0.0 and pid in household_account_of
        and (pid not in lm.jobs or pid in lm.suspended)
    ]
    rng.shuffle(pool)

    def actives_of(f) -> list[int]:
        return [pid for pid in lm.roster_of(f.id) if pid not in lm.suspended]

    # ---- PASS A: firm-side separations, suspensions, recalls ----
    for f in firms_order:
        target = max(0.0, float(f.labor_demand_eff))
        wage = max(f.wage, EPS)
        affordable = int(led.balance(f.id) / wage)

        # 3. demand-gap layoffs with hysteresis + partial adjustment (LIFO over actives).
        # The firing decision reads a SMOOTHED target (daily EMA) while hiring reads the
        # live one: firms grab workers fast but shed them only on persistent gaps --
        # labor hoarding as an asymmetric adjustment rule.
        ema = lm.target_ema.get(f.id)
        ema = target if ema is None else ema + lm.target_smooth * (target - ema)
        lm.target_ema[f.id] = ema
        active = actives_of(f)
        excess = len(active) - ema
        # the band floors at ONE WHOLE WORKER: at ~2-worker firms a relative band is
        # invisible against integer granularity and the market cycles itself to death
        band = max(1.0, lm.layoff_band * ema)
        if excess > band:
            fire_flow = lm.lambda_fire * (excess - band)
            n_fire = int(fire_flow)
            if rng.random() < fire_flow - n_fire:
                n_fire += 1
            for victim in list(reversed(active))[:n_fire]:
                lm.separate(victim)
                if accounts is not None:
                    accounts.layoff_seps_total += 1

        # 4. cash-crunch ladder: suspend (L1b, the employment LOLR) or fire (L1).
        # Under L3 wages are heterogeneous: the test is the actual wagebill vs cash.
        active = actives_of(f)
        while active and sum(lm.wage_of(pid, f) for pid in active) > led.balance(f.id):
            victim = active.pop()                   # LIFO
            if lm.suspension_enabled:
                lm.suspended[victim] = Suspension(firm_id=f.id, since_tick=econ.t, wage_at=wage)
                if accounts is not None:
                    accounts.suspensions_total += 1
            else:
                lm.separate(victim)
                if accounts is not None:
                    accounts.layoff_seps_total += 1
                    accounts.cash_layoffs_memo += 1

        # 4b. recall: cash recovered and demand wants them -> suspended return in place
        # (FIFO by suspension time), BEFORE any new hiring -- no re-matching friction
        if lm.suspension_enabled:
            own_suspended = sorted(
                (pid for pid in lm.roster_of(f.id) if lm.suspended.get(pid) is not None
                 and lm.suspended[pid].firm_id == f.id),
                key=lambda pid: lm.suspended[pid].since_tick,
            )
            for pid in own_suspended:
                current = actives_of(f)
                bill = sum(lm.wage_of(q, f) for q in current)
                if len(current) + 1 > target + 0.5 or bill + lm.wage_of(pid, f) > led.balance(f.id):
                    break
                del lm.suspended[pid]
                if accounts is not None:
                    accounts.recalls_total += 1

    # freshly separated workers rejoin the pool for THIS tick's hiring; the JUST-
    # suspended do not search until tomorrow (else instant-fill mode vacuums a
    # firm's suspended roster the same tick and the recall option never exists)
    pool = [
        pid for pid, s in supply_of.items()
        if s > 0.0 and pid in household_account_of
        and (pid not in lm.jobs
             or (pid in lm.suspended and lm.suspended[pid].since_tick < econ.t))
    ]
    rng.shuffle(pool)

    # ---- PASS B: hiring (instant fill in L1; friction contacts in L2) ----
    if not lm.friction_enabled:
        pool_idx = 0
        for f in firms_order:
            target = max(0.0, float(f.labor_demand_eff))
            wage = max(f.wage, EPS)
            affordable = int(led.balance(f.id) / wage)
            while len(actives_of(f)) + 1 <= target + 0.5 and pool_idx < len(pool):
                bill = sum(lm.wage_of(q, f) for q in actives_of(f))
                if bill + wage > led.balance(f.id):
                    break                           # cash cap binds (heterogeneous bill)
                candidate = pool[pool_idx]
                pool_idx += 1
                if candidate in lm.jobs and candidate not in lm.suspended:
                    continue                        # already employed elsewhere this tick
                _try_hire(lm, accounts, f, candidate, wage, date)
    else:
        # the contact process: each searcher contacts ONE random hiring firm with prob
        # search_intensity; landing on a just-filled or cash-capped firm WASTES the
        # contact (congestion). u* = churn inflow vs contact-success outflow.
        hiring_list = [
            f for f in econ.firms
            if float(f.labor_demand_eff) - lm.active_count(f.id) > 0.5
            and led.balance(f.id) > max(f.wage, EPS)
        ]
        for candidate in pool:
            if not hiring_list:
                break
            if candidate in lm.jobs and candidate not in lm.suspended:
                continue                            # employed (non-suspended): not searching
            if rng.random() >= lm.search_intensity:
                continue                            # no contact today
            idx = rng.randrange(len(hiring_list))
            f = hiring_list[idx]
            wage = max(f.wage, EPS)
            gap = float(f.labor_demand_eff) - lm.active_count(f.id)
            bill = sum(lm.wage_of(q, f) for q in lm.rosters.get(f.id, ()) if q not in lm.suspended)
            if gap < 0.5 or bill + wage > led.balance(f.id):
                hiring_list[idx] = hiring_list[-1]  # stale vacancy: drop it, contact wasted
                hiring_list.pop()
                continue
            if _try_hire(lm, accounts, f, candidate, wage, date):
                if float(f.labor_demand_eff) - lm.active_count(f.id) < 0.5:
                    hiring_list[idx] = hiring_list[-1]
                    hiring_list.pop()

        # vacancy-age gauge: consecutive ticks each firm has carried an unfilled gap
        for f in econ.firms:
            if float(f.labor_demand_eff) - lm.active_count(f.id) > 0.5:
                lm.vacancy_age[f.id] = lm.vacancy_age.get(f.id, 0) + 1
            else:
                lm.vacancy_age.pop(f.id, None)

    # ---- PASS B2 (L3b): the on-the-job ladder -- incumbent wage discipline. Employed
    # workers sample ONE hiring firm at ladder_intensity and switch iff the posted
    # wage clears their own wage x (1 + premium). An E->E move: counted as churn+hire
    # (net zero for the reconciliation gate) plus the ladder memo. ----
    if lm.job_ladder and lm.relationship_wages:
        ladder_hiring = [
            f for f in econ.firms
            if float(f.labor_demand_eff) - lm.active_count(f.id) > 0.5
            and led.balance(f.id) > max(f.wage, EPS)
        ]
        if ladder_hiring:
            for person_id in list(lm.jobs.keys()):
                if person_id in lm.suspended:
                    continue
                if rng.random() >= lm.ladder_intensity:
                    continue
                f = ladder_hiring[rng.randrange(len(ladder_hiring))]
                job = lm.jobs[person_id]
                if f.id == job.firm_id:
                    continue
                wage = max(f.wage, EPS)
                gap = float(f.labor_demand_eff) - lm.active_count(f.id)
                bill = sum(lm.wage_of(q, f) for q in lm.rosters.get(f.id, ()) if q not in lm.suspended)
                if gap < 0.5 or bill + wage > led.balance(f.id):
                    continue                        # stale posting: contact wasted
                if wage < job.wage * (1.0 + lm.ladder_premium):
                    continue                        # the raise is not worth the jump
                lm.separate(person_id)
                lm.hire(person_id, f.id, date, wage=wage)
                if accounts is not None:
                    accounts.churn_seps_total += 1
                    accounts.hires_total += 1
                    accounts.ladder_moves_total += 1

    # ---- PASS C: wages -- every ACTIVE member (including this tick's hires) paid at
    # the posted wage into their CURRENT household; suspended members: no pay, no work
    # (the benefit/JG machinery catches them through labor_sold = 0) ----
    for f in firms_order:
        for person_id in actives_of(f):
            account = household_account_of.get(person_id)
            if account is None:
                continue
            pay = min(lm.wage_of(person_id, f), led.balance(f.id))
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


def _try_hire(lm: LaborMarket, accounts: Any, f: Any, candidate: int, wage: float, date: Any) -> bool:
    """Shared hire attempt: suspended candidates hold out for their reservation."""
    susp = lm.suspended.get(candidate)
    if susp is not None:
        if susp.firm_id == f.id or wage < lm.quit_discount * susp.wage_at:
            return False                            # waiting beats this offer
        lm.separate(candidate)                      # poached: the old link dies (S-side)
        if accounts is not None:
            accounts.suspension_poached_total += 1
    lm.hire(candidate, f.id, date, wage=wage)
    if accounts is not None:
        accounts.hires_total += 1
    return True
