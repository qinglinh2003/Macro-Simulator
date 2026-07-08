"""Leslie matrix and deterministic oracle for the Phase 0 population kernel."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from macro_sim.demographics.rates import Phase0VitalRates


@dataclass(frozen=True)
class LeslieDiagnostics:
    lambda1: float
    growth_rate: float
    damping_ratio: float
    cycle_period: float | None


def build_leslie_matrix(rates: Phase0VitalRates) -> np.ndarray:
    size = rates.omega + 1
    matrix = np.zeros((size, size), dtype=float)
    matrix[0, :] = rates.female_birth_share * rates.fertility_curve() * rates.dt
    survival = rates.survival_curve()
    for age, probability in enumerate(survival):
        matrix[age + 1, age] = probability
    return matrix


def _dominant_eigensystem(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    values, vectors = np.linalg.eig(matrix)
    idx = int(np.argmax(values.real))
    return values, vectors, idx


def stable_age_distribution(matrix: np.ndarray) -> np.ndarray:
    values, vectors, idx = _dominant_eigensystem(matrix)
    vector = vectors[:, idx].real
    if vector.sum() < 0.0:
        vector = -vector
    vector = np.clip(vector, 0.0, None)
    total = float(vector.sum())
    if total <= 0.0:
        raise ValueError("dominant Leslie eigenvector has zero non-negative mass")
    return vector / total


def spectral_diagnostics(matrix: np.ndarray, *, dt: float = 1.0) -> LeslieDiagnostics:
    values, _, idx = _dominant_eigensystem(matrix)
    lambda1 = float(values[idx].real)
    ordered = sorted((value for i, value in enumerate(values) if i != idx), key=lambda value: abs(value), reverse=True)
    lambda2 = ordered[0] if ordered else 0.0
    angle = float(np.angle(lambda2))
    cycle_period = None if abs(angle) < 1e-12 else float(2.0 * np.pi * dt / abs(angle))
    return LeslieDiagnostics(
        lambda1=lambda1,
        growth_rate=float(np.log(lambda1) / dt),
        damping_ratio=float(abs(lambda2) / abs(lambda1)) if lambda1 != 0.0 else 0.0,
        cycle_period=cycle_period,
    )


@dataclass
class LeslieOracle:
    matrix: np.ndarray
    counts: np.ndarray

    def step(self) -> np.ndarray:
        self.counts = self.matrix @ self.counts
        return self.counts.copy()
