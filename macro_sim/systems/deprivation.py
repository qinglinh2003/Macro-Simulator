"""v18.0 subsistence basket & deprivation gauges — OBSERVATION ONLY.

The measurement object the whole consumption-stratification arc reads. A subsistence
basket is an EXTERNAL standard, not a decision input: needs-weighted real consumption
against a floor whose per-need-unit cost is fitted once at genesis to a fraction of
mean per-unit consumption (the poverty-line idiom), then FROZEN.

Two facts about the substrate shape the design:

1. Consumption is attributed at the HOUSEHOLD unit — `post_household_consumption`
   charges dependents' needs to supporting adults, so a child's OWN allocation is ~0.
   Deprivation is therefore measured per household (coverage = C_hh / (basket_cost0 *
   need_units_hh * price_ratio)) and inherited by every member; incidence gauges count
   the PERSONS in deprived households (a poor household's children are deprived).

2. `PersonClaimSheet.consumption_allocated_tick` is CUMULATIVE over a person's life
   (never reset — metrics reads it as a lifetime-consumption stock). The per-tick flow
   this gauge needs is recovered by DIFFERENCING each person's cumulative against the
   prior tick (monotonic within a life, so no household-composition jump artifacts). A
   person seen for the first time contributes zero flow that tick (its prior is seeded,
   not dumped as one spike).

The DOMAIN BOUNDARY (PLAN_v18, the research ruling): acute deprivation is NOT modeled
as death — there is no 21st-century precedent for large-scale acute mortality from
purely economic causes, and reality's clearing valves (migration, aid, remittances)
are all outside a closed economy, so a simulated death would be an artifact of a
missing mechanism. A sustained acute spell sets a STICKY health flag marking that the
run has left the model's validity domain; post-breach demographic/long-run paths are
out of domain while distributional readouts stay valid.

Genesis idiom (mirrors HousingAffordabilitySignal / EnergyPovertySignal): discard the
first `burnin_years` as a genesis relaxation transient, then anchor the basket to the
mean per-unit consumption FLOW over the burn-in window and freeze it. Off
(deprivation_gauges=False) ⇒ the signal is never constructed ⇒ bit-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

_EPS = 1e-12

# Reporting is a table contract: activation after the calibration window changes
# values, never columns.  Keeping the inactive schema explicit also lets long-run
# diagnostics distinguish an intentional burn-in zero from missing data.
_INACTIVE_GAUGES = {
    "deprivation_active": 0.0,
    "deprivation_basket_per_unit": 0.0,
    "deprivation_below100_share": 0.0,
    "deprivation_below60_share": 0.0,
    "deprivation_below30_share": 0.0,
    "deprivation_destitute_share": 0.0,
    "deprivation_acute_stock": 0.0,
    "deprivation_chronic_stock": 0.0,
    "deprivation_acute_persondays": 0.0,
    "deprivation_chronic_persondays": 0.0,
    "deprivation_max_spell_days": 0.0,
    "deprivation_coverage_child": 0.0,
    "deprivation_coverage_adult": 0.0,
    "deprivation_coverage_elder": 0.0,
    "deprivation_below100_share_bottomq": 0.0,
    "deprivation_below100_share_topq": 0.0,
    "deprivation_boundary": 0.0,
}

# One alive person per tick: (person_id, household_id, need_weight, cumulative_consumption,
# age, net_worth, liquid_deposits). The signal differences the cumulative into a per-tick
# flow itself. liquid_deposits (the person-claim cash balance) gates the DOMAIN BOUNDARY:
# genuine subsistence destitution means consumption below the line AND no liquid savings
# to self-fund it -- this excludes a wealthy household whose consumption flow briefly hits
# zero because a bank suspension froze its (still-owned) deposits, a liquidity artifact the
# flow-only gauge misreads as deprivation (its wealth gradient inverts: top quintile, not
# bottom, reads "deprived" -- the diagnostic signature of a freeze, not a famine).
PersonObs = Tuple[int, int, float, float, int, float, float]


@dataclass
class DeprivationSignal:
    subsistence_share: float = 0.5
    burnin_years: int = 2
    acute_days: int = 7            # sub-30% spell length that trips the domain flag
    chronic_days: int = 30        # sub-60% spell length that trips the domain flag

    # anchor state (frozen after burn-in)
    basket_cost0: float | None = None      # subsistence cost per unit-of-need at genesis prices
    price_ref: float | None = None         # price index at the anchor tick
    year: int | None = None
    years_completed: int = 0

    # burn-in accumulators (mean consumption-per-need-unit FLOW over the window)
    _per_unit_sum: float = 0.0
    _hh_days: float = 0.0
    _price_sum: float = 0.0
    _price_days: float = 0.0

    # differencing state: person_id -> last-seen cumulative consumption
    _prev_cum: Dict[int, float] = field(default_factory=dict)
    # per-household spell counters: household_id -> [days<100%, days<60%, days<30%]
    _spells: Dict[int, List[int]] = field(default_factory=dict)
    boundary_breached: bool = False        # sticky: any acute/chronic spell ever reached

    def preview(self, *, year: int, price_index: float, persons: Sequence[PersonObs]) -> dict:
        """Return this tick's gauges without advancing any differencing state.

        Reporting may be queried more than once between economic ticks (interactive
        dashboards and diagnostic probes both do this).  ``preview`` therefore runs the
        exact same deterministic transition as :meth:`observe`, but leaves the signal
        untouched.  ``Economy`` calls ``observe`` once, explicitly, after accepting the
        metric snapshot.
        """
        return self._observe(year=year, price_index=price_index, persons=persons, commit=False)

    def observe(self, *, year: int, price_index: float, persons: Sequence[PersonObs]) -> dict:
        """One tick. `persons` = iterable of PersonObs for every alive person with a
        claim sheet. Returns gauges to merge into the record; empty (active=0) during
        burn-in before the anchor is set."""
        return self._observe(year=year, price_index=price_index, persons=persons, commit=True)

    def _observe(
        self,
        *,
        year: int,
        price_index: float,
        persons: Sequence[PersonObs],
        commit: bool,
    ) -> dict:
        """Compute the observation transition, optionally committing its next state."""
        next_year = self.year
        next_years_completed = self.years_completed
        if next_year is None:
            next_year = int(year)
        elif int(year) != next_year:
            next_years_completed += 1
            next_year = int(year)

        # difference cumulative -> per-tick flow, aggregate to households
        next_prev_cum = dict(self._prev_cum)
        hh_flow: Dict[int, float] = {}
        hh_need: Dict[int, float] = {}
        hh_n: Dict[int, int] = {}
        hh_wealth: Dict[int, float] = {}
        hh_liquid: Dict[int, float] = {}
        hh_ages: Dict[int, List[int]] = {}
        for pid, hid, weight, cum, age, wealth, liquid in persons:
            prev = next_prev_cum.get(pid)
            next_prev_cum[pid] = cum
            flow = 0.0 if prev is None else max(0.0, cum - prev)   # first sight ⇒ 0 (no spike)
            hh_flow[hid] = hh_flow.get(hid, 0.0) + flow
            hh_need[hid] = hh_need.get(hid, 0.0) + max(0.0, float(weight))
            hh_n[hid] = hh_n.get(hid, 0) + 1
            hh_wealth[hid] = hh_wealth.get(hid, 0.0) + float(wealth)
            hh_liquid[hid] = hh_liquid.get(hid, 0.0) + max(0.0, float(liquid))
            hh_ages.setdefault(hid, []).append(int(age))

        if self.basket_cost0 is None:
            next_per_unit_sum = self._per_unit_sum
            next_hh_days = self._hh_days
            next_price_sum = self._price_sum
            next_price_days = self._price_days
            for hid, need in hh_need.items():
                if need > _EPS:
                    next_per_unit_sum += hh_flow.get(hid, 0.0) / need
                    next_hh_days += 1.0
            if price_index > _EPS:
                next_price_sum += float(price_index)
                next_price_days += 1.0
            next_basket_cost0 = self.basket_cost0
            next_price_ref = self.price_ref
            if next_years_completed >= self.burnin_years and next_hh_days > _EPS:
                mean_per_unit = next_per_unit_sum / next_hh_days
                if mean_per_unit > _EPS:      # never freeze a degenerate zero basket
                    next_basket_cost0 = self.subsistence_share * mean_per_unit
                    next_price_ref = (next_price_sum / next_price_days) if next_price_days > _EPS else 1.0
            if commit:
                self.year = next_year
                self.years_completed = next_years_completed
                self._prev_cum = next_prev_cum
                self._per_unit_sum = next_per_unit_sum
                self._hh_days = next_hh_days
                self._price_sum = next_price_sum
                self._price_days = next_price_days
                self.basket_cost0 = next_basket_cost0
                self.price_ref = next_price_ref
            return dict(_INACTIVE_GAUGES)

        gauges, next_spells, next_boundary = self._score(
            price_index,
            hh_flow,
            hh_need,
            hh_n,
            hh_wealth,
            hh_liquid,
            hh_ages,
            spells=self._spells,
            boundary_breached=self.boundary_breached,
        )
        if commit:
            self.year = next_year
            self.years_completed = next_years_completed
            self._prev_cum = next_prev_cum
            self._spells = next_spells
            self.boundary_breached = next_boundary
        return gauges

    def _score(
        self,
        price_index,
        hh_flow,
        hh_need,
        hh_n,
        hh_wealth,
        hh_liquid,
        hh_ages,
        *,
        spells: Dict[int, List[int]],
        boundary_breached: bool,
    ) -> tuple[dict, Dict[int, List[int]], bool]:
        price_ratio = (price_index / self.price_ref) if (self.price_ref and self.price_ref > _EPS) else 1.0
        persons = 0
        p_below100 = p_below60 = p_below30 = 0     # PERSONS in deprived households (flow only)
        p_destitute = 0                            # flow-below-30% AND liquid < basket (resource-gated)
        acute_persons = chronic_persons = 0
        acute_persondays = chronic_persondays = 0
        max_spell = 0
        cov_by_hh: Dict[int, float] = {}
        new_spells: Dict[int, List[int]] = {}
        for hid, need in hh_need.items():
            n = hh_n.get(hid, 0)
            persons += n
            if need <= _EPS:
                continue
            basket = self.basket_cost0 * need * price_ratio
            if basket <= _EPS:
                continue
            coverage = hh_flow.get(hid, 0.0) / basket
            cov_by_hh[hid] = coverage
            # resource gate: a household that could self-fund subsistence from liquid
            # savings is not destitute even if its consumption FLOW is momentarily low
            # (a bank-freeze artifact). "Deposit-poor" = liquid < one period's basket.
            deposit_poor = hh_liquid.get(hid, 0.0) < basket
            prior = spells.get(hid, [0, 0, 0])
            s100 = prior[0] + 1 if coverage < 1.0 else 0
            s60 = prior[1] + 1 if coverage < 0.6 else 0
            # the acute (sub-30%) spell only counts while the household is ALSO deposit-poor
            s30 = prior[2] + 1 if (coverage < 0.3 and deposit_poor) else 0
            new_spells[hid] = [s100, s60, s30]
            if coverage < 1.0:
                p_below100 += n
            if coverage < 0.6:
                p_below60 += n
            if coverage < 0.3:
                p_below30 += n
            if coverage < 0.3 and deposit_poor:
                p_destitute += n
            max_spell = max(max_spell, s100)
            if s30 >= self.acute_days:
                acute_persons += n
                acute_persondays += s30 * n
                boundary_breached = True
            if s60 >= self.chronic_days and deposit_poor:
                chronic_persons += n
                chronic_persondays += s60 * n
                boundary_breached = True
        denom = float(max(1, persons))

        # age-band mean coverage (each member inherits its household coverage) + a
        # wealth-rank incidence gradient (bottom vs top wealth quintile share below 100%).
        child_c: List[float] = []
        adult_c: List[float] = []
        elder_c: List[float] = []
        for hid, ages in hh_ages.items():
            cov = cov_by_hh.get(hid)
            if cov is None:
                continue
            for a in ages:
                (child_c if a < 18 else elder_c if a >= 65 else adult_c).append(cov)
        paired = sorted((hh_wealth.get(hid, 0.0), cov) for hid, cov in cov_by_hh.items())
        bottomq = topq = 0.0
        if len(paired) >= 5:
            q = max(1, len(paired) // 5)
            bot = [c for _w, c in paired[:q]]
            top = [c for _w, c in paired[-q:]]
            bottomq = sum(1 for c in bot if c < 1.0) / len(bot)
            topq = sum(1 for c in top if c < 1.0) / len(top)

        gauges = {
            **_INACTIVE_GAUGES,
            "deprivation_active": 1.0,
            "deprivation_basket_per_unit": self.basket_cost0 * price_ratio,
            "deprivation_below100_share": p_below100 / denom,
            "deprivation_below60_share": p_below60 / denom,
            "deprivation_below30_share": p_below30 / denom,
            "deprivation_destitute_share": p_destitute / denom,     # resource-gated (the honest acute)
            "deprivation_acute_stock": float(acute_persons),        # persons, sub-30% > acute_days
            "deprivation_chronic_stock": float(chronic_persons),    # persons, sub-60% > chronic_days
            "deprivation_acute_persondays": float(acute_persondays),
            "deprivation_chronic_persondays": float(chronic_persondays),
            "deprivation_max_spell_days": float(max_spell),
            "deprivation_coverage_child": _mean(child_c),
            "deprivation_coverage_adult": _mean(adult_c),
            "deprivation_coverage_elder": _mean(elder_c),
            "deprivation_below100_share_bottomq": bottomq,
            "deprivation_below100_share_topq": topq,
            "deprivation_boundary": 1.0 if boundary_breached else 0.0,
        }
        return gauges, new_spells, boundary_breached


def _mean(xs: List[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0
