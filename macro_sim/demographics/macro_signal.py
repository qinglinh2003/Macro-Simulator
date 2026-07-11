"""Phase 2 macro-to-demography signal: annual real-wage level and cycle gap.

The demographic feedback channels (fertility <- development level, mortality <-
development level) read ONE pair of kernel-level scalars produced here:

    x_t  (slow / level)  = EWMA_5y(annual real wage) / baseline
    z_t  (fast / cycle)  = annual real wage / EWMA_{t-1}   (pre-update EWMA, so the
                           cycle component is not contaminated by itself)

The signal is aggregated daily -> annually (the demographic kernel batches vital
events per year of exposure; feeding it daily wages would inject day-frequency
artifacts). Multipliers update once per calendar year and stay constant within
the year. Every multiplier is a population-wide scalar: individual economic
position can never enter a hazard through this module (that is the Phase 3
boundary, enforced structurally).

Neutrality anchors (the Phase 2 acceptance discipline hangs off these):
- elasticity 0.0 (default) => multiplier stays EXACTLY 1.0 (never recomputed),
  so flag-off runs are bit-identical to the pre-feedback baseline;
- during the burn-in years the baseline is still forming => multipliers 1.0;
- a frozen economy makes x_t converge to a constant, so the population must
  relax to the Leslie steady state of the correspondingly scaled vital rates
  (the parameterized oracle: at baseline the scale is exactly 1).
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-12


@dataclass
class DemoMacroSignal:
    """Daily accumulator + annual EWMA state for the macro->demography signal."""

    halflife_years: float = 5.0
    burnin_years: int = 2
    fertility_elasticity: float = 0.0
    fertility_mult_lo: float = 0.5
    fertility_mult_hi: float = 1.5
    mortality_elasticity: float = 0.0
    mortality_mult_lo: float = 0.7
    mortality_mult_hi: float = 1.3

    # annual state (all read-only outside this module)
    year: int | None = None
    years_completed: int = 0
    ewma: float | None = None
    baseline: float | None = None
    signal_x: float = 1.0
    signal_z: float = 1.0
    fertility_mult: float = 1.0
    mortality_mult: float = 1.0
    last_real_wage: float | None = None

    # intra-year accumulators
    _wage_sum: float = 0.0
    _labor_sum: float = 0.0
    _price_sum: float = 0.0
    _days: int = 0

    def observe_tick(self, *, year: int, wages_paid: float, labor: float, price: float) -> None:
        """Accumulate one day of realized wage payments; roll the year on a date change."""
        if self.year is None:
            self.year = int(year)
        elif int(year) != self.year:
            self._finalize_year()
            self.year = int(year)
        self._wage_sum += float(wages_paid)
        self._labor_sum += float(labor)
        self._price_sum += float(price)
        self._days += 1

    def _finalize_year(self) -> None:
        real_wage = self.last_real_wage  # hold-last guard: a zero-activity year keeps the prior level
        if self._labor_sum > _EPS and self._price_sum > _EPS and self._days > 0:
            mean_price = self._price_sum / self._days
            real_wage = (self._wage_sum / self._labor_sum) / mean_price
            self.last_real_wage = real_wage
        self._wage_sum = self._labor_sum = self._price_sum = 0.0
        self._days = 0
        self.years_completed += 1
        if real_wage is None or real_wage <= _EPS:
            return
        if self.years_completed <= self.burnin_years:
            return  # burn-in years are DISCARDED, not smoothed: the genesis transient (real wage
            #         ~3x in the first years of every run, a relaxation from arbitrary initial
            #         prices, not development) must never enter the EWMA -- a baseline anchored
            #         on its slope would drift x for a decade afterwards (replay: x>2 by year 10)
        if self.ewma is None:
            self.ewma = real_wage        # burn-in over: the first clean year is both EWMA seed
            self.baseline = real_wage    # and level anchor, so x starts exactly at 1
            z = 1.0
        else:
            z = real_wage / self.ewma
            alpha = 1.0 - 0.5 ** (1.0 / max(self.halflife_years, _EPS))
            self.ewma += alpha * (real_wage - self.ewma)
        self.signal_z = z
        self.signal_x = self.ewma / self.baseline
        if self.fertility_elasticity > 0.0:
            self.fertility_mult = _clip(
                self.signal_x ** (-self.fertility_elasticity),
                self.fertility_mult_lo,
                self.fertility_mult_hi,
            )
        if self.mortality_elasticity > 0.0:
            self.mortality_mult = _clip(
                self.signal_x ** (-self.mortality_elasticity),
                self.mortality_mult_lo,
                self.mortality_mult_hi,
            )


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
