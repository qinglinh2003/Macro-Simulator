"""v18.5 product-line switching — supply reallocates its STUCK capital.

The emergent investment+entry channel (18.5a) already drifts capital toward the growing
sector, but existing capital is stuck: it leaves a shrinking sector only through slow
depreciation + differential new investment, never repurposing. Measured on a 10y growth
run, necessity ends OVER-capitalized by ~13pp vs its shrunk demand. Switching closes that
lag: a firm whose sector has been out-returned by the other for a SUSTAINED window retools
to the other sector, paying a RETOOL LOSS (a fraction of its capital) at a low hazard.

The retool loss + the sustained-gap requirement + the low hazard are the FRICTION (the
v16 search-friction analog on the supply side): they keep structural transformation a
slow, non-oscillating process rather than a per-tick reshuffle. The retooled capital is a
REAL stock (like `f.inventory` / depreciation) — destroying a slice of it touches no money
conservation. Off (sector_switching=False) ⇒ no-op ⇒ bit-identical.
"""

from __future__ import annotations

from typing import Any

from macro_sim.systems.firm_accounting import firm_earnings

EPS = 1e-9


def _sector_rate(econ: Any, firms, price_level: float) -> float:
    rates = [firm_earnings(econ, f) / (f.capital * price_level) for f in firms if f.capital > EPS]
    return sum(rates) / len(rates) if rates else 0.0


def run_sector_switching_phase(econ: Any) -> None:
    cfg = econ.cfg
    if not getattr(cfg, "sector_switching", False):
        return                               # off ⇒ no state touched ⇒ bit-identical
    econ._sector_switches = 0.0
    econ._sector_switch_capital = 0.0
    if not (econ.n_firms and econ.l_firms):
        return
    price = max(EPS, float(getattr(econ, "_price_level", 1.0)))
    r_N = _sector_rate(econ, econ.n_firms, price)
    r_L = _sector_rate(econ, econ.l_firms, price)
    rng = econ._switch_rng
    gap = cfg.switch_return_gap

    for f in list(econ.c_firms):
        if f.capital <= EPS:                 # entrants / shells: no capital to retool
            f.switch_pressure = 0
            continue
        if f.consumption_sector == "necessity":
            own_r, other_r = r_N, r_L
        else:
            own_r, other_r = r_L, r_N
        # accumulate switching pressure while the OTHER sector out-returns this one
        if other_r > own_r * (1.0 + gap) and other_r > 0.0:
            f.switch_pressure += 1
        else:
            f.switch_pressure = 0
        if f.switch_pressure >= cfg.switch_pressure_days and rng.random() < cfg.switch_hazard:
            loss = f.capital * cfg.switch_retool_loss
            f.capital -= loss                # retooling destroys a slice of real capital
            f.capital_prev = f.capital
            old = f.consumption_sector
            new = "luxury" if old == "necessity" else "necessity"
            f.consumption_sector = new
            (econ.n_firms if old == "necessity" else econ.l_firms).remove(f)
            (econ.n_firms if new == "necessity" else econ.l_firms).append(f)
            f.switch_pressure = 0
            econ._sector_switches += 1.0
            econ._sector_switch_capital += loss
