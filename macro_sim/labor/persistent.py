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

# v23: the smallest hour share that constitutes a real private job.
#
# Every fractional allocation site tested hours against EPS (~1e-9) -- a FLOAT-DUST threshold,
# not an economic one. `remaining_target / efficiency` and `remaining_cash / rate` bottom out at
# arithmetic residue, so a "job" of ~1e-9 FTE (a nanosecond of work) could be created; its pay
# `rate * hours` then fell BELOW EPS whenever the wage rate was under 1.0 and tripped the
# downstream "non-positive pay" assertion, killing the whole run (observed: baseline_s1 at 2191
# ticks, pay=9.2e-10). The hours guard and the pay guard were mathematically inconsistent.
#
# A job must be big enough that its pay is a real cash flow. 1e-6 FTE is still economically nil
# -- it can never displace a genuine part-time match -- but sits three orders of magnitude above
# the dust, so `rate * hours` cannot collapse through EPS for any plausible wage.
MIN_JOB_HOURS = 1e-6


@dataclass
class Job:
    person_id: int
    firm_id: str
    hire_date: Any                  # datetime.date (real calendar; leap-safe anniversaries)
    wage: float = 0.0               # L3: locked at hire; anniversary reviews ratchet it
    hours: float = 1.0              # private-job FTE in (0, 1]; fixed at one unless enabled


@dataclass
class Suspension:
    firm_id: str
    since_tick: int
    wage_at: float                  # acceptance threshold base for on-pool search (theta x this)


@dataclass
class LaborMarket:
    fractional_hours: bool = False  # optional intensive margin; whole-person path stays default
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
    # L4 person efficiency: the human-capital slot. e_i ~ lognormal, MEAN ONE
    # (mu = -sigma^2/2), drawn ONCE at first hire from a dedicated substream and
    # carried for life (across jobs and unemployment spells). Earnings = wage x e_i
    # through wage_of (the single authority: every cash check prices it); firms
    # produce with EFFICIENCY UNITS (f.hired); labor_sold is heads on the legacy
    # path and FTE hours under the optional intensive margin. Parent->child
    # transmission is Phase 3.4, NOT v16.
    person_efficiency: bool = False
    efficiency_sigma: float = 0.35
    efficiency: dict[int, float] = field(default_factory=dict)  # person_id -> e_i
    # L5 participation margin: the reservation wage. The outside option is what the
    # welfare state actually pays a non-worker (max of the JG wage and the benefit
    # rate); a jobless person SEARCHES iff their expected private earnings
    # (wage_ref x e_i) clear reservation_markup x outside, and an incumbent whose
    # actual pay sits below that line QUITS TO WELFARE at a daily hazard. This is a
    # SEARCH decision, not an accounting rewrite: non-searchers stay in partition-U
    # (jobless on welfare) with a memo stock -- the JG/benefit machinery is untouched.
    participation_enabled: bool = False
    reservation_markup: float = 1.0
    welfare_quit_hazard: float = 0.02   # per-tick quit hazard for below-reservation incumbents
    nonsearch: set[int] = field(default_factory=set)            # this tick's voluntary idle
    vacancy_age: dict[str, int] = field(default_factory=dict)   # consecutive gap ticks per firm

    jobs: dict[int, Job] = field(default_factory=dict)          # person_id -> Job
    rosters: dict[str, list[int]] = field(default_factory=dict) # firm_id -> hire-ordered ids
    suspended: dict[int, Suspension] = field(default_factory=dict)  # person_id -> Suspension

    def roster_of(self, firm_id: str) -> list[int]:
        return self.rosters.setdefault(firm_id, [])

    # -- v23 second contract (the intensive-margin fix) --------------------------------
    #
    # Under `labor_fractional_hours` each firm allocates its labour target GREEDILY down its
    # roster, so only the MARGINAL worker at a firm ends up part-time. With ~75 firms that is
    # ~75 part-timers stranding ~0.3-0.5 FTE each: measured 13-24 FTE of residual hours idle
    # while firms posted 180-235 vacancies, and the residue drained into the job guarantee
    # (JG 11.7% of labour, fill 85.7%). One Job per person made those hours UNSELLABLE.
    #
    # A person may now hold ONE additional contract at a DIFFERENT firm, capped so their total
    # hours never exceed 1.0. Dual job-holding recovers essentially all of the stranded margin
    # (triple-holding is economically rare). Every firm-scoped read resolves the contract AT
    # THAT FIRM via `job_at`; person-scoped reads use `total_hours`. Off (`second_job=False`)
    # the structure is empty and every path is the original single-Job one.
    second_job: bool = False
    second_jobs: dict[int, Job] = field(default_factory=dict)   # person_id -> the extra contract
    # separate() is reached from 16 call sites (churn, layoffs, deaths, exits, poaching), each
    # of which records the FTE of the PRIMARY job it knows about. When the person also held an
    # extra contract, those hours must leave FTE too, so the market keeps a reference to the
    # live labour journal rather than threading `accounts` through every caller.
    accounts_ref: Any = None

    def job_at(self, person_id: int, firm_id: str) -> "Job | None":
        """The person's contract AT THIS FIRM (primary or second)."""
        job = self.jobs.get(person_id)
        if job is not None and job.firm_id == firm_id:
            return job
        extra = self.second_jobs.get(person_id)
        if extra is not None and extra.firm_id == firm_id:
            return extra
        return None

    def total_hours(self, person_id: int) -> float:
        """Hours sold across ALL of this person's private contracts."""
        total = 0.0
        job = self.jobs.get(person_id)
        if job is not None and person_id not in self.suspended:
            total += job.hours
        extra = self.second_jobs.get(person_id)
        if extra is not None:
            total += extra.hours
        return total

    def residual_hours(self, person_id: int) -> float:
        """Unsold capacity: what a second employer could still buy."""
        return max(0.0, 1.0 - self.total_hours(person_id))

    def can_take_second_job(self, person_id: int, firm_id: str) -> bool:
        if not (self.second_job and self.fractional_hours):
            return False
        if person_id in self.suspended or person_id in self.second_jobs:
            return False
        job = self.jobs.get(person_id)
        if job is None or job.firm_id == firm_id:
            return False   # unemployed people take a PRIMARY job; never two at one firm
        return self.residual_hours(person_id) > MIN_JOB_HOURS

    def hire_second(self, person_id: int, firm_id: str, date: Any, wage: float,
                    hours: float) -> None:
        hours = min(hours, self.residual_hours(person_id))
        if hours <= MIN_JOB_HOURS:
            return
        self.second_jobs[person_id] = Job(person_id=person_id, firm_id=firm_id,
                                          hire_date=date, wage=wage, hours=hours)
        self.roster_of(firm_id).append(person_id)

    def separate_second(self, person_id: int) -> float:
        """Drop only the extra contract; returns the hours released."""
        extra = self.second_jobs.pop(person_id, None)
        if extra is None:
            return 0.0
        roster = self.rosters.get(extra.firm_id)
        if roster is not None:
            try:
                roster.remove(person_id)
            except ValueError:
                pass
        return extra.hours

    def hire(
        self, person_id: int, firm_id: str, date: Any, wage: float = 0.0,
        hours: float = 1.0,
    ) -> None:
        if person_id in self.jobs:
            raise AssertionError(f"person {person_id} already has a private Job")
        if not (0.0 < hours <= 1.0):
            raise AssertionError(f"Job hours must be in (0, 1], got {hours}")
        self.jobs[person_id] = Job(person_id=person_id, firm_id=firm_id,
                                   hire_date=date, wage=wage, hours=hours)
        self.roster_of(firm_id).append(person_id)

    def separate(self, person_id: int, accounts: Any | None = None) -> None:
        # The extra contract cannot outlive the person's participation. Its hours leave FTE
        # here (the caller only knows about the primary job's hours), but NOT the head count --
        # the head separation is booked once, by the caller, for the person.
        dropped = self.separate_second(person_id)
        journal = accounts if accounts is not None else self.accounts_ref
        if dropped > 0.0 and journal is not None and self.fractional_hours:
            _record_fte_change(journal, -dropped)
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
        """The wage a member is actually paid: relationship wage under L3, posted else;
        times the person's efficiency under L4 (single authority: cash checks see it).

        v23: a relationship wage belongs to a CONTRACT, not to a person. With a second job the
        old lookup returned the PRIMARY job's locked wage no matter which firm was asking, so a
        second employer budgeted its own posted wage but paid the other firm's relationship wage
        -- the firm's wage bill then overran its live cash and tripped the cash guard.
        """
        if self.relationship_wages:
            # Per-CONTRACT lookup only when a person can hold two of them; otherwise keep the
            # legacy person-scoped lookup exactly, so every existing preset stays bit-identical.
            job = (
                self.job_at(person_id, firm.id) if self.second_job
                else self.jobs.get(person_id)
            )
            if job is not None and job.wage > 0.0:
                base = job.wage
            else:
                base = max(float(firm.wage), 1e-12)
        else:
            base = max(float(firm.wage), 1e-12)
        if self.person_efficiency:
            return base * self.efficiency.get(person_id, 1.0)
        return base

    def e_of(self, person_id: int) -> float:
        return self.efficiency.get(person_id, 1.0)

    def ensure_efficiency(self, person_id: int, rng: Any) -> None:
        """Draw e_i at FIRST hire (never redrawn: it is a person attribute)."""
        if self.person_efficiency and person_id not in self.efficiency:
            mu = -0.5 * self.efficiency_sigma * self.efficiency_sigma
            self.efficiency[person_id] = rng.lognormvariate(mu, self.efficiency_sigma)

    def active_count(self, firm_id: str) -> int:
        return sum(1 for pid in self.rosters.get(firm_id, ()) if pid not in self.suspended)

    def active_hours(self, firm_id: str) -> float:
        """Scheduled private FTE at THIS firm; suspended recall rights contribute zero.
        v23: resolves the contract at this firm, so a second-job holder contributes only the
        hours they sold HERE (never their primary employer's hours)."""
        total = 0.0
        for pid in self.rosters.get(firm_id, ()):
            if pid in self.suspended:
                continue
            job = self.job_at(pid, firm_id)
            if job is not None:
                total += job.hours
        return total

    def active_effective(self, firm_id: str) -> float:
        """Efficiency-weighted hours at THIS firm, in the units of firm labor demand/output."""
        total = 0.0
        for pid in self.rosters.get(firm_id, ()):
            if pid in self.suspended:
                continue
            job = self.job_at(pid, firm_id)
            if job is not None:
                total += job.hours * self.e_of(pid)
        return total

    def on_person_death(self, person_id: int, accounts: Any | None = None) -> None:
        self.efficiency.pop(person_id, None)      # human capital dies with the person
        if person_id in self.jobs:
            was_suspended = person_id in self.suspended
            hours = self.jobs[person_id].hours
            self.separate(person_id)
            if accounts is not None and not was_suspended:
                accounts.death_seps_total += 1    # suspended exits are S-side, not E-flows
                if self.fractional_hours:
                    _record_fte_change(accounts, -hours)

    def on_firm_exit(self, firm_id: str, accounts: Any | None = None) -> None:
        """Bankruptcy / liquidation = the whole roster into the pool at once."""
        for person_id in list(self.rosters.get(firm_id, ())):
            was_suspended = person_id in self.suspended
            job = self.job_at(person_id, firm_id)
            if job is None:
                continue
            hours = job.hours
            # v23: a person whose SECOND contract is at the dying firm keeps their PRIMARY job
            # elsewhere -- only the contract at THIS firm ends, and they stay employed. That is
            # an INTENSIVE-margin loss (hours), not a head separation, so it must not enter the
            # head-flow identity.
            is_second = job is self.second_jobs.get(person_id)
            if is_second:
                self.separate_second(person_id)
                if accounts is not None and self.fractional_hours:
                    _record_fte_change(accounts, -hours)
                continue
            self.separate(person_id)
            if accounts is not None and not was_suspended:
                accounts.bankruptcy_seps_total += 1
                if self.fractional_hours:
                    _record_fte_change(accounts, -hours)
        self.rosters.pop(firm_id, None)


def run_persistent_labor_phase(econ: Any) -> None:
    if econ.labor_market.fractional_hours:
        return _run_fractional_hours_labor_phase(econ)
    lm = econ.labor_market
    rng = econ._labor_rng
    eff_rng = getattr(econ, "_eff_rng", None)       # L4 substream (draws only if enabled)
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
            lm.efficiency.pop(person_id, None)
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

    # ---- 2c. (L5) the participation margin: reservation = markup x the welfare
    # state's outside option (max of JG wage and benefit rate). Incumbents PAID below
    # it quit to welfare at a daily hazard (the policy-sensitive quit class); jobless
    # persons whose EXPECTED private earnings (wage_ref x e_i; e defaults to 1 before
    # the first job -- unknown ability, optimistic) fall below it do not search. A
    # search decision, not an accounting rewrite: non-searchers stay in partition-U
    # on welfare, gauged by the memo stock. Suspended workers keep their own recall
    # reservation and are exempt. ----
    if lm.participation_enabled:
        pol = econ.policy
        wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
        outside = 0.0
        if pol.job_guarantee and pol.jg_wage_ratio > 0.0:
            outside = max(pol.jg_wage_ratio * wage_ref, pol.min_wage)
        outside = max(outside, pol.benefit_replacement * wage_ref)
        reservation = lm.reservation_markup * outside
        if reservation > 0.0:
            for person_id, job in list(lm.jobs.items()):
                if person_id in lm.suspended:
                    continue
                firm = firm_by_id.get(job.firm_id)
                if firm is None:
                    continue
                if lm.wage_of(person_id, firm) < reservation \
                        and rng.random() < lm.welfare_quit_hazard:
                    lm.separate(person_id)
                    if accounts is not None:
                        accounts.welfare_quits_total += 1
        lm.nonsearch = {
            pid for pid, s in supply_of.items()
            if s > 0.0 and pid not in lm.jobs
            and wage_ref * lm.e_of(pid) < reservation
        }
    else:
        lm.nonsearch = set()

    # searcher pool: the jobless PLUS the suspended (recall unemployment: they search
    # with a reservation of quit_discount x their suspended wage)
    pool = [
        pid for pid, s in supply_of.items()
        if s > 0.0 and pid in household_account_of and pid not in lm.nonsearch
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
        if s > 0.0 and pid in household_account_of and pid not in lm.nonsearch
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
                _try_hire(lm, accounts, f, candidate, wage, date, eff_rng)
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
            if _try_hire(lm, accounts, f, candidate, wage, date, eff_rng):
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
            # L4: production consumes EFFICIENCY UNITS; heads stay in labor_sold below
            f.hired += lm.e_of(person_id) if lm.person_efficiency else 1.0
            f.wagebill += pay
            agent = bridge._household_agent(account)
            if agent is not None:
                agent.income_realized += pay
                agent.labor_sold += 1.0


def _record_fte_change(accounts: Any, delta: float) -> None:
    """Post one private-hours stock mutation to the fractional-hours FTE gate."""
    if accounts is None or abs(delta) <= EPS:
        return
    if delta > 0.0:
        accounts.private_fte_inflows_total += delta
    else:
        accounts.private_fte_outflows_total -= delta


def _set_active_hours(lm: LaborMarket, accounts: Any, person_id: int, hours: float,
                      firm_id: str | None = None) -> None:
    """Resize an active Job without confusing an intensive change with a hire.

    v23: with a second contract, resize the job AT THIS FIRM and never let the person's TOTAL
    hours exceed 1.0 (the other contract's hours are already sold)."""
    job = lm.jobs[person_id] if firm_id is None else lm.job_at(person_id, firm_id)
    if job is None:
        return
    other = lm.total_hours(person_id) - job.hours   # hours sold at the person's OTHER contract
    hours = min(hours, max(0.0, 1.0 - other))
    if not (EPS < hours <= 1.0 + EPS):
        raise AssertionError(f"active Job hours must be in (0, 1], got {hours}")
    old = job.hours
    job.hours = min(1.0, hours)
    _record_fte_change(accounts, job.hours - old)


def _run_fractional_hours_labor_phase(econ: Any) -> None:
    """Persistent one-job relationships with an explicit within-job hours margin.

    The certified whole-person path above is deliberately not refactored through this
    function: ``labor_fractional_hours=False`` therefore keeps both decisions and RNG
    consumption unchanged.  Here existing relationships are resized first, recalls
    second, and new matches last.  Head events retain the established flow taxonomy;
    every hours mutation additionally posts to the private-FTE flow gate.
    """

    lm = econ.labor_market
    rng = econ._labor_rng
    eff_rng = getattr(econ, "_eff_rng", None)
    bridge = econ.demographic_bridge
    accounts = econ.labor_accounts
    lm.accounts_ref = accounts   # v23: so separate() can retire an extra contract's FTE
    led = econ.ledger
    date = econ.demographic_state.current_date
    churn_daily = lm.churn_annual / 365.0

    person_index: dict[int, Any] = {}
    supply_of: dict[int, float] = {}
    household_account_of: dict[int, str] = {}
    state = bridge._demographic_state_ref()
    from macro_sim.demographics.economic_state import labor_supply_for_person
    for person in state.people:
        if not person.alive or person.household_id is None:
            continue
        person_id = int(person.id)
        person_index[person_id] = person
        supply_of[person_id] = labor_supply_for_person(person)
        account = bridge.household_to_account.get(int(person.household_id))
        if account is not None:
            household_account_of[person_id] = account

    # Deaths/age-outs and suspension timeouts are extensive-margin changes.
    for person_id in list(lm.jobs):
        person = person_index.get(person_id)
        gone = (
            person is None or supply_of.get(person_id, 0.0) <= 0.0
            or person_id not in household_account_of
        )
        if gone:
            was_suspended = person_id in lm.suspended
            hours = lm.jobs[person_id].hours
            lm.separate(person_id)
            lm.efficiency.pop(person_id, None)
            if accounts is not None and not was_suspended:
                accounts.death_seps_total += 1
                _record_fte_change(accounts, -hours)

    if lm.suspension_enabled:
        for person_id, susp in list(lm.suspended.items()):
            if econ.t - susp.since_tick >= lm.suspension_timer:
                lm.separate(person_id)
                if accounts is not None:
                    accounts.suspension_timeouts_total += 1

    # Preserve the established per-active-job churn draw and ordering.
    for person_id in list(lm.jobs):
        if person_id in lm.suspended:
            continue
        if rng.random() < churn_daily:
            hours = lm.jobs[person_id].hours
            lm.separate(person_id)
            if accounts is not None:
                accounts.churn_seps_total += 1
                _record_fte_change(accounts, -hours)

    firms_order = list(econ.firms)
    rng.shuffle(firms_order)
    firm_by_id = {f.id: f for f in econ.firms}

    if lm.relationship_wages:
        for job in lm.jobs.values():
            if job.person_id in lm.suspended:
                continue
            hd = job.hire_date
            month, day = hd.month, hd.day
            if month == 2 and day == 29 and not (
                date.year % 4 == 0 and (date.year % 100 != 0 or date.year % 400 == 0)
            ):
                day = 28
            if (date.month, date.day) == (month, day) and date != hd:
                firm = firm_by_id.get(job.firm_id)
                if firm is not None:
                    job.wage = max(job.wage, float(firm.wage), float(econ.policy.min_wage))

    if lm.participation_enabled:
        pol = econ.policy
        wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
        outside = 0.0
        if pol.job_guarantee and pol.jg_wage_ratio > 0.0:
            outside = max(pol.jg_wage_ratio * wage_ref, pol.min_wage)
        outside = max(outside, pol.benefit_replacement * wage_ref)
        reservation = lm.reservation_markup * outside
        if reservation > 0.0:
            for person_id, job in list(lm.jobs.items()):
                if person_id in lm.suspended:
                    continue
                firm = firm_by_id.get(job.firm_id)
                if firm is None:
                    continue
                # Compare hourly earning capacity with the hourly outside option;
                # JG/benefits cover the residual hours rather than penalizing part time.
                if lm.wage_of(person_id, firm) < reservation \
                        and rng.random() < lm.welfare_quit_hazard:
                    hours = job.hours
                    lm.separate(person_id)
                    if accounts is not None:
                        accounts.welfare_quits_total += 1
                        _record_fte_change(accounts, -hours)
        lm.nonsearch = {
            pid for pid, supply in supply_of.items()
            if supply > 0.0 and pid not in lm.jobs
            and wage_ref * lm.e_of(pid) < reservation
        }
    else:
        lm.nonsearch = set()

    # Keep the historical pre-adjustment shuffle.  It is redundant operationally but
    # makes the enabled mode's stochastic grammar parallel to persistent whole-person.
    pool = [
        pid for pid, supply in supply_of.items()
        if supply > 0.0 and pid in household_account_of and pid not in lm.nonsearch
        and (pid not in lm.jobs or pid in lm.suspended)
    ]
    rng.shuffle(pool)

    def actives_of(firm: Any) -> list[int]:
        # v23: a person on this roster may hold their PRIMARY job elsewhere and a SECOND
        # contract here, so membership is decided by the contract AT THIS FIRM.
        return [
            pid for pid in lm.roster_of(firm.id)
            if pid not in lm.suspended and lm.job_at(pid, firm.id) is not None
        ]

    def hours_at(firm: Any, pid: int) -> float:
        job = lm.job_at(pid, firm.id)
        return job.hours if job is not None else 0.0

    def committed_bill(firm: Any) -> float:
        return sum(
            lm.wage_of(pid, firm) * hours_at(firm, pid)
            for pid in actives_of(firm)
        )

    def gap_of(firm: Any) -> float:
        return max(0.0, float(firm.labor_demand_eff) - lm.active_effective(firm.id))

    # Existing matches get first claim on target hours and live cash. Oldest matches
    # are retained first; the marginal relationship carries the fractional remainder.
    for firm in firms_order:
        target = max(0.0, float(firm.labor_demand_eff))
        ema = lm.target_ema.get(firm.id)
        lm.target_ema[firm.id] = target if ema is None else ema + lm.target_smooth * (target - ema)
        remaining_target = target
        remaining_cash = max(0.0, float(led.balance(firm.id)))
        for person_id in list(actives_of(firm)):
            job = lm.job_at(person_id, firm.id)       # v23: the contract AT THIS FIRM
            if job is None:
                continue
            old_hours = job.hours
            efficiency = lm.e_of(person_id)
            rate = lm.wage_of(person_id, firm)
            # a second-job holder can only sell what their other employer left unsold
            sellable = max(0.0, 1.0 - (lm.total_hours(person_id) - old_hours))
            new_hours = min(
                sellable,
                remaining_target / max(efficiency, EPS),
                remaining_cash / max(rate, EPS),
            )
            if new_hours > MIN_JOB_HOURS:
                _set_active_hours(lm, accounts, person_id, new_hours, firm_id=firm.id)
                remaining_target = max(0.0, remaining_target - efficiency * new_hours)
                remaining_cash = max(0.0, remaining_cash - rate * new_hours)
                continue

            cash_blocked = remaining_target > EPS and remaining_cash / max(rate, EPS) <= EPS
            _record_fte_change(accounts, -old_hours)
            if job is lm.second_jobs.get(person_id):
                # v23: releasing a SECOND contract must not touch the person's primary job, and
                # it is an INTENSIVE-margin event -- the person stays employed, so hours fall
                # but the HEAD count does not move. Booking a head separation here would break
                # the labour head-flow identity. The FTE change was already recorded above.
                lm.separate_second(person_id)
            elif cash_blocked and lm.suspension_enabled:
                lm.suspended[person_id] = Suspension(
                    firm_id=firm.id, since_tick=econ.t, wage_at=max(firm.wage, EPS),
                )
                if accounts is not None:
                    accounts.suspensions_total += 1
            else:
                lm.separate(person_id)
                if accounts is not None:
                    accounts.layoff_seps_total += 1
                    if cash_blocked:
                        accounts.cash_layoffs_memo += 1

        if lm.suspension_enabled:
            own_suspended = sorted(
                (
                    pid for pid in lm.roster_of(firm.id)
                    if pid in lm.suspended and lm.suspended[pid].firm_id == firm.id
                ),
                key=lambda pid: lm.suspended[pid].since_tick,
            )
            for person_id in own_suspended:
                gap = gap_of(firm)
                if gap <= EPS:
                    break
                rate = lm.wage_of(person_id, firm)
                cash = max(0.0, led.balance(firm.id) - committed_bill(firm))
                hours = min(
                    1.0, gap / max(lm.e_of(person_id), EPS), cash / max(rate, EPS),
                )
                if hours <= MIN_JOB_HOURS:
                    continue
                lm.jobs[person_id].hours = hours
                del lm.suspended[person_id]
                if accounts is not None:
                    accounts.recalls_total += 1
                    _record_fte_change(accounts, hours)

    # Workers separated above re-enter this tick; newly suspended workers wait a day.
    pool = [
        pid for pid, supply in supply_of.items()
        if supply > 0.0 and pid in household_account_of and pid not in lm.nonsearch
        and (
            pid not in lm.jobs
            or (pid in lm.suspended and lm.suspended[pid].since_tick < econ.t)
        )
    ]
    rng.shuffle(pool)

    if not lm.friction_enabled:
        pool_idx = 0
        for firm in firms_order:
            while gap_of(firm) > EPS and pool_idx < len(pool):
                candidate = pool[pool_idx]
                pool_idx += 1
                if candidate in lm.jobs and candidate not in lm.suspended:
                    continue
                if eff_rng is not None:
                    lm.ensure_efficiency(candidate, eff_rng)
                rate = max(firm.wage, EPS) * lm.e_of(candidate)
                cash = max(0.0, led.balance(firm.id) - committed_bill(firm))
                hours = min(
                    1.0,
                    gap_of(firm) / max(lm.e_of(candidate), EPS),
                    cash / max(rate, EPS),
                )
                if hours <= MIN_JOB_HOURS:
                    break
                _try_hire(
                    lm, accounts, firm, candidate, max(firm.wage, EPS), date,
                    eff_rng, hours=hours,
                )
    else:
        hiring_list = [
            firm for firm in econ.firms
            if gap_of(firm) > EPS and led.balance(firm.id) - committed_bill(firm) > EPS
        ]
        for candidate in pool:
            if not hiring_list:
                break
            if candidate in lm.jobs and candidate not in lm.suspended:
                continue
            if rng.random() >= lm.search_intensity:
                continue
            idx = rng.randrange(len(hiring_list))
            firm = hiring_list[idx]
            gap = gap_of(firm)
            cash = max(0.0, led.balance(firm.id) - committed_bill(firm))
            if gap <= EPS or cash <= EPS:
                hiring_list[idx] = hiring_list[-1]
                hiring_list.pop()
                continue
            if eff_rng is not None:
                lm.ensure_efficiency(candidate, eff_rng)
            rate = max(firm.wage, EPS) * lm.e_of(candidate)
            hours = min(
                1.0, gap / max(lm.e_of(candidate), EPS), cash / max(rate, EPS),
            )
            if hours <= MIN_JOB_HOURS:
                hiring_list[idx] = hiring_list[-1]
                hiring_list.pop()
                continue
            if _try_hire(
                lm, accounts, firm, candidate, max(firm.wage, EPS), date,
                eff_rng, hours=hours,
            ):
                if gap_of(firm) <= EPS or led.balance(firm.id) - committed_bill(firm) <= EPS:
                    hiring_list[idx] = hiring_list[-1]
                    hiring_list.pop()

        for firm in econ.firms:
            if gap_of(firm) > EPS:
                lm.vacancy_age[firm.id] = lm.vacancy_age.get(firm.id, 0) + 1
            else:
                lm.vacancy_age.pop(firm.id, None)

    # One private Job per person remains binding: a ladder move transfers the whole
    # relationship, with destination hours set by its FTE gap and cash.
    if lm.job_ladder and lm.relationship_wages:
        ladder_hiring = [
            firm for firm in econ.firms
            if gap_of(firm) > EPS and led.balance(firm.id) - committed_bill(firm) > EPS
        ]
        if ladder_hiring:
            for person_id in list(lm.jobs):
                if person_id in lm.suspended or person_id not in lm.jobs:
                    continue
                if rng.random() >= lm.ladder_intensity:
                    continue
                firm = ladder_hiring[rng.randrange(len(ladder_hiring))]
                old_job = lm.jobs[person_id]
                if firm.id == old_job.firm_id:
                    continue
                wage = max(firm.wage, EPS)
                if wage < old_job.wage * (1.0 + lm.ladder_premium):
                    continue
                cash = max(0.0, led.balance(firm.id) - committed_bill(firm))
                hours = min(
                    1.0,
                    gap_of(firm) / max(lm.e_of(person_id), EPS),
                    cash / max(lm.e_of(person_id) * wage, EPS),
                )
                if hours <= MIN_JOB_HOURS:
                    continue
                old_hours = old_job.hours
                lm.separate(person_id)
                _record_fte_change(accounts, -old_hours)
                lm.hire(person_id, firm.id, date, wage=wage, hours=hours)
                _record_fte_change(accounts, hours)
                if accounts is not None:
                    accounts.churn_seps_total += 1
                    accounts.hires_total += 1
                    accounts.ladder_moves_total += 1

    # v23 SECOND-CONTRACT PASS -- the intensive-margin fix.
    #
    # Greedy per-firm allocation leaves exactly one part-time MARGINAL worker at each firm.
    # With one Job per person those residual hours were unsellable: measured 13-24 FTE idle
    # while firms posted 180-235 vacancies, and the residue drained into the job guarantee
    # (fill 85.7%, JG 11.7%, and the resulting production shortfall ratcheted the B3 markup
    # into runaway inflation). A firm that still has a gap may now buy a part-timer's UNSOLD
    # hours as a second contract, capped so nobody sells more than 1.0 FTE in total.
    if lm.second_job:
        part_timers = [
            pid for pid in lm.jobs
            if pid not in lm.suspended
            and pid not in lm.second_jobs
            and pid in household_account_of
            and lm.residual_hours(pid) > MIN_JOB_HOURS
        ]
        rng.shuffle(part_timers)
        for firm in firms_order:
            if gap_of(firm) <= EPS:
                continue
            for candidate in list(part_timers):
                if gap_of(firm) <= EPS:
                    break
                if not lm.can_take_second_job(candidate, firm.id):
                    continue
                rate = max(firm.wage, EPS) * lm.e_of(candidate)
                cash = max(0.0, led.balance(firm.id) - committed_bill(firm))
                hours = min(
                    lm.residual_hours(candidate),
                    gap_of(firm) / max(lm.e_of(candidate), EPS),
                    cash / max(rate, EPS),
                )
                if hours <= MIN_JOB_HOURS:
                    continue
                lm.hire_second(candidate, firm.id, date, max(firm.wage, EPS), hours)
                if candidate in lm.second_jobs:
                    # An extra contract is an INTENSIVE-margin change: the person was already
                    # employed, so FTE rises but the HEAD count does not. Booking it as a hire
                    # would break the labour head-flow identity (heads vs prev + net flows).
                    _record_fte_change(accounts, lm.second_jobs[candidate].hours)
                    part_timers.remove(candidate)

    # Cash was reserved conceptually above; settle exact hours-scaled pay and work.
    for firm in firms_order:
        for person_id in actives_of(firm):
            account = household_account_of.get(person_id)
            if account is None:
                continue
            hours = hours_at(firm, person_id)   # v23: the contract AT THIS FIRM, not the person's primary
            if not (EPS < hours <= 1.0 + EPS):
                raise AssertionError(f"zero/invalid-hour pseudo-job for person {person_id}: {hours}")
            rate = lm.wage_of(person_id, firm)
            pay = rate * hours
            if pay > led.balance(firm.id) + 1e-9:
                raise AssertionError(
                    f"fractional wage plan exceeds live cash for {firm.id}: pay={pay}, "
                    f"cash={led.balance(firm.id)}"
                )
            if pay <= EPS:
                raise AssertionError(f"fractional Job generated non-positive pay: {pay}")
            led.transfer(firm.id, account, pay)
            bridge.post_labor_income(account, pay, worker_person_ids=[person_id])
            firm.hired += lm.e_of(person_id) * hours
            firm.wagebill += pay
            agent = bridge._household_agent(account)
            if agent is not None:
                agent.income_realized += pay
                agent.labor_sold += hours


def _try_hire(
    lm: LaborMarket, accounts: Any, f: Any, candidate: int, wage: float, date: Any,
    eff_rng: Any = None, hours: float = 1.0,
) -> bool:
    """Shared hire attempt: suspended candidates hold out for their reservation."""
    susp = lm.suspended.get(candidate)
    if susp is not None:
        if susp.firm_id == f.id or wage < lm.quit_discount * susp.wage_at:
            return False                            # waiting beats this offer
        lm.separate(candidate)                      # poached: the old link dies (S-side)
        if accounts is not None:
            accounts.suspension_poached_total += 1
    if eff_rng is not None:
        lm.ensure_efficiency(candidate, eff_rng)    # L4: e_i is born at the first hire
    lm.hire(candidate, f.id, date, wage=wage, hours=hours)
    if accounts is not None:
        accounts.hires_total += 1
        if lm.fractional_hours:
            _record_fte_change(accounts, hours)
    return True
