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

# One alive person per tick: (person_id, household_id, need_weight, cumulative_consumption,
# age, net_worth). The signal differences the cumulative into a per-tick flow itself.
PersonObs = Tuple[int, int, float, float, int, float]


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

    def observe(self, *, year: int, price_index: float, persons: Sequence[PersonObs]) -> dict:
        """One tick. `persons` = iterable of PersonObs for every alive person with a
        claim sheet. Returns gauges to merge into the record; empty (active=0) during
        burn-in before the anchor is set."""
        if self.year is None:
            self.year = int(year)
        elif int(year) != self.year:
            self.years_completed += 1
            self.year = int(year)

        # difference cumulative -> per-tick flow, aggregate to households
        hh_flow: Dict[int, float] = {}
        hh_need: Dict[int, float] = {}
        hh_n: Dict[int, int] = {}
        hh_wealth: Dict[int, float] = {}
        hh_ages: Dict[int, List[int]] = {}
        for pid, hid, weight, cum, age, wealth in persons:
            prev = self._prev_cum.get(pid)
            self._prev_cum[pid] = cum
            flow = 0.0 if prev is None else max(0.0, cum - prev)   # first sight ⇒ 0 (no spike)
            hh_flow[hid] = hh_flow.get(hid, 0.0) + flow
            hh_need[hid] = hh_need.get(hid, 0.0) + max(0.0, float(weight))
            hh_n[hid] = hh_n.get(hid, 0) + 1
            hh_wealth[hid] = hh_wealth.get(hid, 0.0) + float(wealth)
            hh_ages.setdefault(hid, []).append(int(age))

        if self.basket_cost0 is None:
            for hid, need in hh_need.items():
                if need > _EPS:
                    self._per_unit_sum += hh_flow.get(hid, 0.0) / need
                    self._hh_days += 1.0
            if price_index > _EPS:
                self._price_sum += float(price_index)
                self._price_days += 1.0
            if self.years_completed >= self.burnin_years and self._hh_days > _EPS:
                mean_per_unit = self._per_unit_sum / self._hh_days
                if mean_per_unit > _EPS:      # never freeze a degenerate zero basket
                    self.basket_cost0 = self.subsistence_share * mean_per_unit
                    self.price_ref = (self._price_sum / self._price_days) if self._price_days > _EPS else 1.0
            return {"deprivation_active": 0.0}

        return self._score(price_index, hh_flow, hh_need, hh_n, hh_wealth, hh_ages)

    def _score(self, price_index, hh_flow, hh_need, hh_n, hh_wealth, hh_ages) -> dict:
        price_ratio = (price_index / self.price_ref) if (self.price_ref and self.price_ref > _EPS) else 1.0
        persons = 0
        p_below100 = p_below60 = p_below30 = 0     # PERSONS in deprived households
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
            prior = self._spells.get(hid, [0, 0, 0])
            s100 = prior[0] + 1 if coverage < 1.0 else 0
            s60 = prior[1] + 1 if coverage < 0.6 else 0
            s30 = prior[2] + 1 if coverage < 0.3 else 0
            new_spells[hid] = [s100, s60, s30]
            if coverage < 1.0:
                p_below100 += n
            if coverage < 0.6:
                p_below60 += n
            if coverage < 0.3:
                p_below30 += n
            max_spell = max(max_spell, s100)
            if s30 >= self.acute_days:
                acute_persons += n
                acute_persondays += s30 * n
                self.boundary_breached = True
            if s60 >= self.chronic_days:
                chronic_persons += n
                chronic_persondays += s60 * n
                self.boundary_breached = True
        self._spells = new_spells
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

        return {
            "deprivation_active": 1.0,
            "deprivation_basket_per_unit": self.basket_cost0 * price_ratio,
            "deprivation_below100_share": p_below100 / denom,
            "deprivation_below60_share": p_below60 / denom,
            "deprivation_below30_share": p_below30 / denom,
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
            "deprivation_boundary": 1.0 if self.boundary_breached else 0.0,
        }


def _mean(xs: List[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0
