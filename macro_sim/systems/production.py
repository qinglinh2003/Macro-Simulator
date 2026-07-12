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


def run_production_phase(econ: Any) -> None:
    """Hired labor yields output added to inventory (§6.3). Sector-aware (B.produce):
    linear a*N, or Cobb-Douglas A K^alpha N^(1-alpha)."""
    for f in econ.firms:
        f.produced = B.produce(f, f.hired, econ._pubcap_factor)
        f.inventory += f.produced
