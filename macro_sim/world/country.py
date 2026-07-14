"""The country-character interface (PLAN_v20 §0.6): `CountryProfile`.

A named Config overlay applied at genesis that makes structurally-identical economies look
like different countries by tuning a few interpretable economic axes. Archetypes are preset
points. Only the axes whose defining feature sits on the model's crown-jewel components are
expressible now; several (oil export, SWF, peg, aging demographics) activate as later
components land — the interface is forward-compatible.

v20 LIVE axes: productivity/TFP (labor productivity `a`), scale (n_households), sector tilt
(necessity share). DEFERRED: resource endowment / oil export (S2 energy-tradable), openness
per-economy (world-level for now), policy regime / peg (v21), institutions & savings (thin
params), aging vs young demographics (demographic-arc knobs).
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

    def apply(self, base: Config) -> Config:
        overrides = {"a": base.a * self.productivity}
        if self.scale != 1.0:
            overrides["n_households"] = max(1, int(round(base.n_households * self.scale)))
        if self.necessity_tilt is not None:
            overrides["necessity_share0"] = self.necessity_tilt
        return replace(base, **overrides)


# -- Archetype presets (§0.6). Extreme on a LIVE crown-jewel axis; muted features noted. --

SYMMETRIC = CountryProfile("symmetric")

# The v20.3 first-divergence pair. The plan's headline is aging-rich vs young-developing
# (demographic axis); that needs demographic-arc knobs, so v20's LIVE realization uses the
# productivity/scale axes as the proxy: a small high-TFP advanced economy vs a larger
# low-TFP developing one (§10 "minimal-first"). Demographic aging/young is DEFERRED.
ADVANCED = CountryProfile("advanced", productivity=1.20, scale=1.0)
DEVELOPING = CountryProfile("developing", productivity=0.75, scale=1.5, necessity_tilt=0.65)

# Muted-at-v20 archetypes (kept for the forward-compatible interface):
LAND_SCARCE_ENTREPOT = CountryProfile("entrepot", productivity=1.15, scale=0.4)  # + land/openness (deferred)
PETROSTATE = CountryProfile("petrostate", productivity=0.85, scale=0.8)          # + oil export (S2, deferred)
