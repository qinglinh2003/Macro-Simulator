"""Vital-rate primitives for the Phase 0 frozen demographic kernel."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Phase0VitalRates:
    """Biological vital-rate parameters used to derive the Phase 0 pyramid."""

    makeham_a: float = 3e-4
    gompertz_b: float = 6e-5
    gompertz_theta: float = 0.0866
    infant_extra: float = 0.010
    tfr: float = 2.5
    fertility_peak_age: float = 28.0
    fertility_width: float = 6.0
    sex_ratio_at_birth: float = 1.05
    omega: int = 100
    dt: float = 1.0

    @property
    def female_birth_share(self) -> float:
        return 1.0 / (1.0 + self.sex_ratio_at_birth)

    @property
    def male_birth_share(self) -> float:
        return self.sex_ratio_at_birth / (1.0 + self.sex_ratio_at_birth)

    def mortality_integral(self, age: float, dt: float | None = None) -> float:
        """Integral of Gompertz-Makeham mortality hazard over [age, age + dt]."""

        dt = self.dt if dt is None else dt
        if dt < 0.0:
            raise ValueError("dt must be non-negative")
        end = age + dt
        gompertz = (self.gompertz_b / self.gompertz_theta) * (
            np.exp(self.gompertz_theta * end) - np.exp(self.gompertz_theta * age)
        )
        infant_overlap = max(0.0, min(end, 1.0) - max(age, 0.0))
        return float(self.makeham_a * dt + gompertz + self.infant_extra * infant_overlap)

    def survival_probability(self, age: float, dt: float | None = None) -> float:
        return float(np.exp(-self.mortality_integral(age, dt)))

    def survival_curve(self) -> np.ndarray:
        return np.asarray([self.survival_probability(age) for age in range(self.omega)], dtype=float)

    def fertility_shape_curve(self) -> np.ndarray:
        ages = np.arange(self.omega + 1, dtype=float)
        shape = np.zeros_like(ages)
        fertile = (ages >= 15.0) & (ages <= 49.0)
        shape[fertile] = np.exp(
            -0.5 * ((ages[fertile] - self.fertility_peak_age) / self.fertility_width) ** 2
        )
        area = float(shape.sum() * self.dt)
        if area <= 0.0:
            raise ValueError("fertility shape has zero area")
        return shape / area

    def fertility_shape_rate(self, age: float) -> float:
        if age < 15.0 or age > 49.0:
            return 0.0
        annual_ages = np.arange(self.omega + 1, dtype=float)
        annual_shape = np.zeros_like(annual_ages)
        fertile = (annual_ages >= 15.0) & (annual_ages <= 49.0)
        annual_shape[fertile] = np.exp(
            -0.5 * ((annual_ages[fertile] - self.fertility_peak_age) / self.fertility_width) ** 2
        )
        area = float(annual_shape.sum() * self.dt)
        if area <= 0.0:
            raise ValueError("fertility shape has zero area")
        shape = np.exp(-0.5 * ((age - self.fertility_peak_age) / self.fertility_width) ** 2)
        return float(shape / area)

    def fertility_rate(self, age: float) -> float:
        return float(self.tfr * self.fertility_shape_rate(age))

    def fertility_curve(self) -> np.ndarray:
        return self.tfr * self.fertility_shape_curve()


def expected_life_at_birth(rates: Phase0VitalRates) -> float:
    """Approximate e0 from the one-year survival schedule."""

    survivorship = 1.0
    years = 0.0
    for age in range(rates.omega + 1):
        years += survivorship
        if age < rates.omega:
            survivorship *= rates.survival_probability(age)
    return float(years)
