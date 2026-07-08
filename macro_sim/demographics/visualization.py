"""Rendering helpers for Phase 0 demographic diagnostics."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from macro_sim.demographics.rates import Phase0VitalRates


def plot_stable_pyramid(distribution: np.ndarray, rates: Phase0VitalRates, path: Path) -> Path:
    ages = np.arange(rates.omega + 1)
    female = distribution * rates.female_birth_share
    male = distribution * rates.male_birth_share
    fig, ax = plt.subplots(figsize=(8.5, 8.0))
    ax.barh(ages, -male, height=0.9, color="#2F80B7", alpha=0.72, label="male")
    ax.barh(ages, female, height=0.9, color="#D07A36", alpha=0.72, label="female")
    ax.axvline(0.0, color="black", lw=0.8)
    ax.set_title("Phase 0 stable population pyramid from vital rates")
    ax.set_xlabel("share of population; male plotted negative")
    ax.set_ylabel("age")
    ax.grid(axis="x", alpha=0.22)
    ax.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
