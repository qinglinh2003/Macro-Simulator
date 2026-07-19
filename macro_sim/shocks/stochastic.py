"""Seeded generators that materialize randomness into concrete shock tapes."""

from __future__ import annotations

import math
import random
from typing import Sequence

from .spec import ShockSpec, ShockTape, ShockTarget


def generate_poisson_tape(
    *,
    seed: int,
    kind: str,
    start_tick: int,
    end_tick: int,
    annual_rate: float,
    magnitude_range: tuple[float, float],
    duration_range: tuple[int, int],
    economy_ids: Sequence[int] | None = None,
    sectors: Sequence[str] = (),
    announcement_lead_range: tuple[int, int] = (0, 0),
    ticks_per_year: float = 365.0,
    name: str | None = None,
) -> ShockTape:
    """Draw a Poisson arrival process once and return its immutable realization."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if not 0 <= start_tick < end_tick:
        raise ValueError("generator requires 0 <= start_tick < end_tick")
    if not annual_rate >= 0.0 or not ticks_per_year > 0.0:
        raise ValueError("annual_rate must be >= 0 and ticks_per_year must be > 0")
    mag_lo, mag_hi = map(float, magnitude_range)
    dur_lo, dur_hi = duration_range
    lead_lo, lead_hi = announcement_lead_range
    if mag_hi < mag_lo or dur_lo < 1 or dur_hi < dur_lo \
            or lead_lo < 0 or lead_hi < lead_lo:
        raise ValueError("invalid stochastic shock range")
    rng = random.Random(seed)
    daily_rate = float(annual_rate) / float(ticks_per_year)
    tick = int(start_tick)
    specs: list[ShockSpec] = []
    sequence = 0
    while daily_rate > 0.0:
        wait = max(1, math.ceil(rng.expovariate(daily_rate)))
        tick += wait
        if tick >= end_tick:
            break
        magnitude = rng.uniform(mag_lo, mag_hi)
        duration = rng.randint(int(dur_lo), int(dur_hi))
        lead = rng.randint(int(lead_lo), int(lead_hi))
        specs.append(ShockSpec(
            shock_id=f"stochastic.{kind}.{seed}.{sequence:06d}",
            kind=kind,
            start_tick=tick,
            magnitude=magnitude,
            target=ShockTarget(
                None if economy_ids is None else tuple(economy_ids), tuple(sectors),
            ),
            duration_ticks=duration,
            announcement_tick=max(start_tick, tick - lead),
            source="seeded_poisson_generator",
            calibration_note=(
                f"annual_rate={annual_rate}; magnitude={magnitude_range}; "
                f"duration={duration_range}; seed={seed}"
            ),
            correlation_group=f"poisson:{seed}",
            tags=("stochastic",),
        ))
        sequence += 1
    return ShockTape(tuple(specs), name=name or f"poisson_{kind}_{seed}")
