"""v15.5 housing affordability signal: one pipeline, per-channel multipliers.

The Phase 2 signal discipline, applied to housing: daily accumulation -> annual
ratios -> burn-in DISCARD (the housing market has its own genesis relaxation: the
distress-sale wave and price slide of the first years are initialization artifacts,
never a baseline) -> post-burn-in anchor (ratios start at exactly 1) -> clipped,
neutrality-anchored multipliers per flag-gated channel.

Two annual ratios, both against the anchor:
  - PTI  (price-to-income):   mean house price / nominal annual wage income
  - RENT BURDEN:              mean rent level x 365 / nominal annual wage income

Channels reading them (each its own elasticity, 0.0 = off = exactly 1):
  - leave-home multiplier  L = clip(rent_burden_ratio^-lambda, lo, hi)
    (unaffordable rents delay leaving home => cohabitation emerges, the safety valve)
  - fertility multiplier   F_house = clip(pti_ratio^-eps, lo, hi)   [channel 2.1d]
    (housing cost is the child-rearing cost the original Phase 2 table wanted)
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-12


@dataclass
class HousingAffordabilitySignal:
    burnin_years: int = 4
    leave_elasticity: float = 0.0
    leave_mult_lo: float = 0.5
    leave_mult_hi: float = 1.5
    fertility_elasticity: float = 0.0
    fertility_mult_lo: float = 0.5
    fertility_mult_hi: float = 1.5

    # annual state
    year: int | None = None
    years_completed: int = 0
    pti_baseline: float | None = None
    burden_baseline: float | None = None
    pti_ratio: float = 1.0
    rent_burden_ratio: float = 1.0
    leave_mult: float = 1.0
    fertility_mult: float = 1.0

    # intra-year accumulators
    _price_sum: float = 0.0
    _rent_sum: float = 0.0
    _wage_sum: float = 0.0
    _labor_sum: float = 0.0
    _days: int = 0

    def observe_tick(self, *, year: int, house_price: float, rent_level: float,
                     wages_paid: float, labor: float) -> None:
        if self.year is None:
            self.year = int(year)
        elif int(year) != self.year:
            self._finalize_year()
            self.year = int(year)
        self._price_sum += float(house_price)
        self._rent_sum += float(rent_level)
        self._wage_sum += float(wages_paid)
        self._labor_sum += float(labor)
        self._days += 1

    def _finalize_year(self) -> None:
        days = self._days
        price = self._price_sum / days if days else 0.0
        rent = self._rent_sum / days if days else 0.0
        annual_income = (self._wage_sum / self._labor_sum * 365.0) if self._labor_sum > _EPS else 0.0
        self._price_sum = self._rent_sum = self._wage_sum = self._labor_sum = 0.0
        self._days = 0
        self.years_completed += 1
        if annual_income <= _EPS or price <= _EPS:
            return                                   # hold-last on degenerate years
        if self.years_completed <= self.burnin_years:
            return                                   # genesis transient: DISCARDED
        pti = price / annual_income
        burden = rent * 365.0 / annual_income
        if self.pti_baseline is None:
            self.pti_baseline = pti                  # anchor: ratios start at exactly 1
            self.burden_baseline = burden if burden > _EPS else None
        self.pti_ratio = pti / self.pti_baseline
        if self.burden_baseline is not None and burden > _EPS:
            self.rent_burden_ratio = burden / self.burden_baseline
        if self.leave_elasticity > 0.0:
            self.leave_mult = _clip(
                self.rent_burden_ratio ** (-self.leave_elasticity),
                self.leave_mult_lo, self.leave_mult_hi,
            )
        if self.fertility_elasticity > 0.0:
            self.fertility_mult = _clip(
                self.pti_ratio ** (-self.fertility_elasticity),
                self.fertility_mult_lo, self.fertility_mult_hi,
            )


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
