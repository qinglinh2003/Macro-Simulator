"""The country-character interface (PLAN_v20 §0.6): `CountryProfile`.

A named Config overlay applied at genesis.  Profiles now use the demographic,
technology and energy systems that landed after v20 instead of retaining placeholder
descriptions for already-implemented axes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from macro_sim.config import Config


@dataclass(frozen=True)
class CountryProfile:
    """A genesis character overlay. Multipliers are relative to the base config."""

    name: str
    productivity: float = 1.0            # × base labor productivity `a` (TFP level) — LIVE
    scale: float = 1.0                   # × base n_households (economy size) — LIVE
    necessity_tilt: float | None = None  # necessity_share0 override (consumption structure) — LIVE
    tfp_growth: float | None = None       # annual Hicks-neutral drift
    tfr: float | None = None              # genesis and live total fertility rate
    mortality_scale: float | None = None # >1 means shorter baseline lives
    energy_productivity: float = 1.0      # × a_E and kappa_E

    def apply(self, base: Config) -> Config:
        overrides = {
            "a": base.a * self.productivity,
            "a_K": base.a_K * self.productivity,
            "a_E": base.a_E * self.energy_productivity,
            "kappa_E": base.kappa_E * self.energy_productivity,
        }
        if self.scale != 1.0:
            overrides["n_households"] = max(1, int(round(base.n_households * self.scale)))
        if self.necessity_tilt is not None:
            overrides["necessity_share0"] = self.necessity_tilt
        if self.tfp_growth is not None:
            overrides["tfp_drift_rate"] = self.tfp_growth
        if self.tfr is not None:
            overrides["demographics_tfr"] = self.tfr
        if self.mortality_scale is not None:
            overrides["demographics_mortality_scale"] = self.mortality_scale
        return replace(base, **overrides)


# -- Archetype presets (§0.6). Extreme on a LIVE crown-jewel axis; muted features noted. --

SYMMETRIC = CountryProfile("symmetric")

ADVANCED = CountryProfile(
    "advanced", productivity=1.20, scale=1.0, tfp_growth=0.012,
    tfr=1.6, mortality_scale=0.85, energy_productivity=1.05,
)
DEVELOPING = CountryProfile(
    "developing", productivity=0.75, scale=1.5, necessity_tilt=0.65,
    tfp_growth=0.030, tfr=2.4, mortality_scale=1.20,
)
LAND_SCARCE_ENTREPOT = CountryProfile(
    "entrepot", productivity=1.15, scale=0.4, tfp_growth=0.018,
    tfr=1.3, mortality_scale=0.80, energy_productivity=0.85,
)
PETROSTATE = CountryProfile(
    "petrostate", productivity=0.85, scale=0.8, tfp_growth=0.010,
    tfr=2.2, mortality_scale=0.90, energy_productivity=1.40,
)
