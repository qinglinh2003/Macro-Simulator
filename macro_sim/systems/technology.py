"""The single authority for productivity over time (PLAN_v19).

Productivity used to be a set of frozen config literals -- ``A`` (C-sector Cobb-Douglas
TFP), ``a``/``a_K`` (labour productivity), the energy sector's anchored ``A_E`` -- copied
into per-firm fields at genesis and never moved. To make total factor productivity DRIFT
over time we do NOT mutate every firm's ``A`` each tick; instead this object owns a
time-varying MULTIPLIER ``Z`` per sector, applied at the production seam exactly the way
``econ._pubcap_factor`` (the v9.1 public-capital factor) already is. The per-firm ``A``/``a``
stay as the genesis anchors; ``Z`` starts at 1.0 so genesis is bit-for-bit unchanged.

Single writer, single reader:
  * ``factor_for(firm)`` -- the output multiplier for that firm's sector, read at the five
    production call sites (``produce`` / ``labor_demand_notional``).
  * ``step(econ)``       -- advance the index one tick; the ONE place the law of motion lives.

The law is pluggable behind ``tfp_law``: ``"exogenous"`` is a trend (+ optional stochastic
term) that grows ``Z`` at ``g`` per year; ``"learning"`` (the 2.x seam) reads an endogenous
state instead. Both write through the SAME ``step`` interface, so no production call site
ever changes when the law does.

Inert by default: ``tfp_drift_rate=0`` and ``tfp_law="exogenous"`` keep ``Z`` pinned at 1.0,
so every pre-v19 config is bit-identical (``Z * pubcap`` is ``1.0 * pubcap`` exactly).
"""

from __future__ import annotations

import random
from typing import Any, Dict

# firm.sells -> sector key
_SECTOR_OF = {"consumption": "c", "capital": "k", "energy": "e"}
_DAYS_PER_YEAR = 365.0


class Technology:
    """Owns the per-sector TFP index Z(t) and its law of motion."""

    def __init__(
        self,
        *,
        drift_rate: float = 0.0,
        drift_sigma: float = 0.0,
        law: str = "exogenous",
        learning_theta: float = 0.0,
        sector_drift: Dict[str, float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        # Z starts at 1.0 for every sector: genesis is the anchor, drift only moves t>0.
        self.z: Dict[str, float] = {"c": 1.0, "k": 1.0, "e": 1.0}
        self.drift_rate = float(drift_rate)
        self.drift_sigma = float(drift_sigma)
        self.law = law
        self.learning_theta = float(learning_theta)
        # per-sector trend override; falls back to the uniform drift_rate when a sector is absent
        self.sector_drift = dict(sector_drift) if sector_drift else {}
        self._rng = rng
        # learning-by-doing needs a genesis output scale to normalise cumulative output against;
        # captured lazily on the first step (so Z stays exactly 1.0 until real output exists).
        self._learning_base: Dict[str, float] | None = None

    # -- read side ---------------------------------------------------------
    def factor_for(self, firm: Any) -> float:
        """Output multiplier for this firm's sector (1.0 while inert)."""
        return self.z.get(_SECTOR_OF.get(getattr(firm, "sells", "consumption"), "c"), 1.0)

    def factor(self, sector: str) -> float:
        return self.z.get(sector, 1.0)

    # -- write side (the one place the law lives) --------------------------
    def step(self, econ: Any) -> None:
        """Advance Z one tick. Inert (Z unchanged) when drift is off."""
        if self.law == "learning":
            self._step_learning(econ)
        else:
            self._step_exogenous()

    def _step_exogenous(self) -> None:
        if self.drift_rate == 0.0 and not self.sector_drift and self.drift_sigma == 0.0:
            return  # fully inert: Z stays exactly 1.0 (bit-identical guarantee)
        for sector in self.z:
            g = self.sector_drift.get(sector, self.drift_rate)
            daily = g / _DAYS_PER_YEAR
            if self.drift_sigma > 0.0 and self._rng is not None:
                # trend + i.i.d. innovation on the daily growth rate (dedicated substream)
                daily += self._rng.gauss(0.0, self.drift_sigma) / _DAYS_PER_YEAR
            self.z[sector] *= (1.0 + daily)

    def _step_learning(self, econ: Any) -> None:
        """Endogenous law (2.x seam): Z_s = (cumulative_output_s / base_s) ** theta.

        Proves an endogenous law plugs into the SAME interface; the engine itself is 2.x.
        theta=0 keeps Z at 1.0.
        """
        if self.learning_theta == 0.0:
            return
        cum = _cumulative_output_by_sector(econ)
        if self._learning_base is None:
            # first non-trivial output sets the base so Z starts at 1.0
            if all(v <= 0.0 for v in cum.values()):
                return
            self._learning_base = {s: max(v, 1e-9) for s, v in cum.items()}
        for sector in self.z:
            base = self._learning_base.get(sector, 1e-9)
            ratio = max(cum.get(sector, 0.0), 1e-9) / base
            self.z[sector] = ratio ** self.learning_theta


def _cumulative_output_by_sector(econ: Any) -> Dict[str, float]:
    cum = getattr(econ, "_cumulative_output_by_sector", None)
    if cum is None:
        return {"c": 0.0, "k": 0.0, "e": 0.0}
    return cum
