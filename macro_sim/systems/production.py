"""Production phase, split out of the labor phase (v16/v17 trunk refactor).

Production used to happen inline at hire time inside ``run_labor_phase``. Both
parallel arcs need it separate: v16 wants the labor phase to be pure matching, and
v17 inserts the energy market BETWEEN hiring and production (output becomes
``min(a·L, energy/e_coeff)``). Per-firm production is a pure function of the firm's
own hires, so extracting it is order-independent and bit-identical.
"""

from __future__ import annotations

from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.markets.matching import EPS


def run_production_phase(econ: Any) -> None:
    """Hired labor yields output added to inventory (§6.3). Sector-aware (B.produce):
    linear a*N, or Cobb-Douglas A K^alpha N^(1-alpha).

    v17.0 energy (PLAN_v17), guarded no-ops when energy is off:
      - capacity edge (E-firms): produced capped at kappa*K (the planning-side cap
        already limits labor demand; the pubcap factor could push a*N past it);
      - Leontief input (c/k firms): produced capped by the energy stock; energy used
        is drawn down at AVERAGE COST (feeds profit and the B3 unit cost).
    """
    energy_on = getattr(econ.cfg, "energy_enabled", False)
    for f in econ.firms:
        if energy_on and f.capacity_kappa > 0.0:
            continue                     # E-firms already produced (pre-market, energy.py)
        f.produced = B.produce(f, f.hired, econ._output_factor(f))
        if energy_on:
            if f.energy_intensity > 0.0:
                f.energy_used = f.energy_cost_used = 0.0
                if f.produced > 0.0:
                    f.produced = min(f.produced, f.energy_stock / f.energy_intensity)
                    use = f.energy_intensity * f.produced
                    if use > EPS:
                        avg = f.energy_stock_cost / f.energy_stock if f.energy_stock > EPS else 0.0
                        f.energy_used = use
                        f.energy_cost_used = use * avg
                        f.energy_stock = max(0.0, f.energy_stock - use)
                        f.energy_stock_cost = max(0.0, f.energy_stock_cost - f.energy_cost_used)
                        if avg > 0.0:
                            f.energy_avg_cost = avg    # hold-last (B3 reads it at next planning)
        f.inventory += f.produced
