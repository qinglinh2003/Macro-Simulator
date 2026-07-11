"""Phase 3.0 wealth stratification: annual household rank snapshot + vital-event gauges.

OBSERVATION ONLY in 3.0: nothing here feeds a hazard yet. The snapshot machinery is
shared by every later Phase 3 channel (mortality/fertility gradients, marriage
assortativity), which will read the bucket maps built here.

Design constraints (docs/plans/PLAN_v14_phase3.md):
- ranks, never amounts: percentile position is dimensionless (no Phase 2 jurisdiction
  creep) and is the empirical object of the wealth-mortality gradient literature;
- deterministic tie-break (net worth, household_id): zero/negative net worth is common
  in the claims layer and must not break run reproducibility;
- households formed mid-year are absent from the map until the next snapshot => later
  channels default them to neutral;
- the age-wealth confound gauge (age_rank_corr, median rank by age band) decides the
  3.1 rank definition BEFORE any hazard is wired (plain vs within-age-band ranks).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from macro_sim.systems.banking import bank_equity_value

AGE_BANDS = ((0, 17), (18, 39), (40, 64), (65, 200))


@dataclass
class WealthStratification:
    buckets: int = 5
    # v14 Phase 3.1/3.2 rank gradients. 0.0 = channel off (no strata tables built, kernel
    # skips entirely, bit-identical). Individual multiplier m_k = exp(beta*(0.5 - r_k)),
    # EXPOSURE-weighted to mean 1 (mortality: baseline-hazard weights; fertility:
    # married-fertile weights), so expected aggregate deaths/births are invariant at each
    # snapshot -- Phase 3 moves WHO, Phase 2 moves HOW MANY. beta_f is SIGNED: > 0 is the
    # modern negative gradient (poor households more children), < 0 the historical one.
    mortality_gradient: float = 0.0
    fertility_gradient: float = 0.0
    mult_lo: float = 0.5
    mult_hi: float = 2.0

    # snapshot state (rebuilt once per calendar year)
    year: int | None = None
    household_rank: dict[int, float] = field(default_factory=dict)
    household_bucket: dict[int, int] = field(default_factory=dict)
    bucket_wealth_share: list[float] = field(default_factory=list)
    bucket_pop_share: list[float] = field(default_factory=list)
    age_rank_corr: float = 0.0
    median_rank_by_band: list[float] = field(default_factory=list)
    rank_history: list[tuple[int, int, float]] = field(default_factory=list)   # (year, household_id, rank)

    # gradient multiplier tables (household_id -> multiplier; empty = channel off)
    mortality_strata: dict[int, float] = field(default_factory=dict)
    fertility_strata: dict[int, float] = field(default_factory=dict)
    bucket_mortality_mult: list[float] = field(default_factory=list)
    bucket_fertility_mult: list[float] = field(default_factory=list)

    # annual vital-event counters, attributed to the bucket at event time
    bucket_deaths: list[int] = field(default_factory=list)
    bucket_births: list[int] = field(default_factory=list)
    # per-bucket exposure masses from the last snapshot (acceptance-math observability)
    bucket_mort_exposure: list[float] = field(default_factory=list)
    bucket_fert_exposure: list[float] = field(default_factory=list)
    # pre-merge spousal rank pairs (3.3 homophily gauge; whole-run accumulation)
    marriage_rank_pairs: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.bucket_deaths:
            self.bucket_deaths = [0] * self.buckets
        if not self.bucket_births:
            self.bucket_births = [0] * self.buckets
        if not self.bucket_wealth_share:
            self.bucket_wealth_share = [0.0] * self.buckets
        if not self.bucket_pop_share:
            self.bucket_pop_share = [0.0] * self.buckets
        if not self.median_rank_by_band:
            self.median_rank_by_band = [0.5] * len(AGE_BANDS)
        if not self.bucket_mortality_mult:
            self.bucket_mortality_mult = [1.0] * self.buckets
        if not self.bucket_fertility_mult:
            self.bucket_fertility_mult = [1.0] * self.buckets

    # ------------------------------------------------------------------
    # event gauges (called from the bridge's on_death / on_birth hooks)
    # ------------------------------------------------------------------
    def record_death(self, household_id: int | None) -> None:
        bucket = self.household_bucket.get(int(household_id)) if household_id is not None else None
        if bucket is not None:
            self.bucket_deaths[bucket] += 1

    def record_birth(self, household_id: int | None) -> None:
        bucket = self.household_bucket.get(int(household_id)) if household_id is not None else None
        if bucket is not None:
            self.bucket_births[bucket] += 1

    def record_marriage(self, rank_a: float | None, rank_b: float | None) -> None:
        """Pre-merge spousal ranks (v14 Phase 3.3 homophily gauge)."""
        if rank_a is not None and rank_b is not None:
            self.marriage_rank_pairs.append((rank_a, rank_b))

    @property
    def spousal_rank_corr(self) -> float:
        if len(self.marriage_rank_pairs) < 2:
            return 0.0
        return _pearson([a for a, _ in self.marriage_rank_pairs],
                        [b for _, b in self.marriage_rank_pairs])

    # ------------------------------------------------------------------
    # annual snapshot
    # ------------------------------------------------------------------
    def observe_tick(self, econ: Any, bridge: Any, year: int) -> None:
        if self.year is None:
            self.year = int(year)
            self._snapshot(econ, bridge)
            return
        if int(year) != self.year:
            self.year = int(year)
            self.bucket_deaths = [0] * self.buckets
            self.bucket_births = [0] * self.buckets
            self._snapshot(econ, bridge)

    def _snapshot(self, econ: Any, bridge: Any) -> None:
        led = econ.ledger
        price_of = {f.id: getattr(f, "share_price", 0.0) for f in econ.c_firms}
        entries: list[tuple[float, int, float]] = []   # (nw per adult-equivalent, household_id, nw)
        for h in econ.households:
            household_id = bridge.household_id_for_account(h.id)
            profile = bridge.household_profile(h.id)
            need_units = max(float(getattr(profile, "need_units", 0.0)), 1e-9)
            if getattr(profile, "adult_count", 0) + getattr(profile, "child_count", 0) + getattr(profile, "elder_count", 0) <= 0:
                continue                       # empty shells awaiting probate are not strata members
            equity = sum(shares * price_of.get(fid, 0.0) for fid, shares in h.holdings.items())
            net_worth = led.balance(h.id) + equity + bank_equity_value(econ, h.id) - led.debt(h.id)
            entries.append((net_worth / need_units, int(household_id), net_worth))

        self.household_rank.clear()
        self.household_bucket.clear()
        n = len(entries)
        if n == 0:
            return
        entries.sort(key=lambda e: (e[0], e[1]))   # deterministic tie-break on household_id
        bucket_wealth = [0.0] * self.buckets
        bucket_pop = [0] * self.buckets
        total_wealth = sum(max(0.0, e[2]) for e in entries)
        for i, (_, household_id, net_worth) in enumerate(entries):
            rank = (i + 0.5) / n
            bucket = min(self.buckets - 1, int(rank * self.buckets))
            self.household_rank[household_id] = rank
            self.household_bucket[household_id] = bucket
            bucket_wealth[bucket] += max(0.0, net_worth)
            bucket_pop[bucket] += 1
            self.rank_history.append((self.year, household_id, rank))
        self.bucket_wealth_share = [w / total_wealth if total_wealth > 1e-9 else 0.0 for w in bucket_wealth]
        self.bucket_pop_share = [p / n for p in bucket_pop]
        self._age_gauges(bridge)

    def _age_gauges(self, bridge: Any) -> None:
        """One person scan: (a) age-wealth confound gauges (corr(age, rank), median rank
        per band -- the reconnaissance that gates the rank definition); (b) per-bucket
        EXPOSURES for the gradient normalizers (mortality: baseline annual hazard mass;
        fertility: fertile-married mass); (c) the strata multiplier tables."""
        pairs: list[tuple[float, float]] = []
        mort_exposure = [0.0] * self.buckets
        fert_exposure = [0.0] * self.buckets
        state = bridge._demographic_state_ref()
        if state is None:
            return
        econ = getattr(bridge, "econ", None)
        rates = getattr(econ, "demographic_rates", None) if econ is not None else None
        for person in getattr(state, "people", []):
            if not getattr(person, "alive", True) or person.household_id is None:
                continue
            rank = self.household_rank.get(int(person.household_id))
            if rank is None:
                continue
            age = float(person.age)
            pairs.append((age, rank))
            if rates is not None:
                bucket = self.household_bucket[int(person.household_id)]
                mort_exposure[bucket] += rates.mortality_integral(age, 1.0)
                if (
                    getattr(person, "sex", "") == "F"
                    and getattr(person, "partner_id", None) is not None
                    and 15.0 <= age <= 49.0
                ):
                    fert_exposure[bucket] += rates.fertility_shape_rate(age)
        if len(pairs) < 2:
            return
        ages = [a for a, _ in pairs]
        ranks = [r for _, r in pairs]
        self.age_rank_corr = _pearson(ages, ranks)
        self.median_rank_by_band = [
            _median([r for a, r in pairs if lo <= a <= hi]) for lo, hi in AGE_BANDS
        ]
        self.bucket_mort_exposure = list(mort_exposure)   # observability: acceptance math
        self.bucket_fert_exposure = list(fert_exposure)   # needs per-bucket exposure masses
        self._build_strata(self.mortality_gradient, mort_exposure, self.bucket_mortality_mult,
                           self.mortality_strata)
        self._build_strata(self.fertility_gradient, fert_exposure, self.bucket_fertility_mult,
                           self.fertility_strata)

    def _build_strata(self, gradient: float, exposure: list[float],
                      bucket_mult_out: list[float], strata_out: dict[int, float]) -> None:
        """Bucket multipliers exp(gradient*(0.5-r_k)), exposure-weighted to mean EXACTLY 1,
        then clipped. Empty tables when the channel is off (kernel skips entirely)."""
        strata_out.clear()
        bucket_mult_out[:] = [1.0] * self.buckets
        if gradient == 0.0:
            return
        total_exposure = sum(exposure)
        if total_exposure <= 0.0:
            return
        raw = [
            math.exp(gradient * (0.5 - (k + 0.5) / self.buckets))
            for k in range(self.buckets)
        ]
        weighted_mean = sum(w * r for w, r in zip(exposure, raw)) / total_exposure
        if weighted_mean <= 0.0:
            return
        bucket_mult_out[:] = [
            _clip(r / weighted_mean, self.mult_lo, self.mult_hi) for r in raw
        ]
        for household_id, bucket in self.household_bucket.items():
            strata_out[household_id] = bucket_mult_out[bucket]


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = (vx * vy) ** 0.5
    return cov / denom if denom > 1e-12 else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.5
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else 0.5 * (values[mid - 1] + values[mid])
