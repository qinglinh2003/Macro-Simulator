"""Illustrative historical crisis packages composed only from generic shocks.

These are reduced-form templates, not claims of historical calibration.  Policy
responses are intentionally absent: a Controller or human operator must supply them.
"""

from __future__ import annotations

from typing import Sequence

from .spec import ShockSpec, ShockTape, ShockTarget


def _target(economy_ids: Sequence[int] | None, sectors=()) -> ShockTarget:
    return ShockTarget(None if economy_ids is None else tuple(economy_ids), tuple(sectors))


def oil_embargo_scenario(
    *, start_tick: int, duration_ticks: int = 180,
    economy_ids: Sequence[int] | None = None, announcement_lead_ticks: int = 0,
) -> ShockTape:
    common = dict(
        start_tick=start_tick, duration_ticks=duration_ticks,
        announcement_tick=max(0, start_tick - announcement_lead_ticks),
        source="illustrative_1970s_oil_embargo_template",
        correlation_group="oil_embargo", tags=("historical_template", "supply"),
        calibration_note="Illustrative reduced-form package; not empirically calibrated.",
    )
    return ShockTape((
        ShockSpec("oil_embargo.energy", "energy_capacity", magnitude=0.45,
                  target=_target(economy_ids, ("energy",)), **common),
        ShockSpec("oil_embargo.imports", "import_capacity", magnitude=0.20,
                  target=_target(economy_ids), **common),
    ), name="oil_embargo_template")


def global_financial_crisis_scenario(
    *, start_tick: int, duration_ticks: int = 365,
    economy_ids: Sequence[int] | None = None, announcement_lead_ticks: int = 0,
) -> ShockTape:
    common = dict(
        start_tick=start_tick, duration_ticks=duration_ticks,
        ramp_out_ticks=min(90, duration_ticks // 3),
        announcement_tick=max(0, start_tick - announcement_lead_ticks),
        source="illustrative_2008_gfc_template", correlation_group="gfc",
        tags=("historical_template", "financial"),
        calibration_note="Illustrative reduced-form package; policy response excluded.",
    )
    return ShockTape((
        ShockSpec("gfc.credit", "credit_supply", magnitude=0.70,
                  target=_target(economy_ids), **common),
        ShockSpec("gfc.demand", "household_demand", magnitude=0.18,
                  target=_target(economy_ids), **common),
        ShockSpec("gfc.productivity", "productivity", magnitude=0.05,
                  target=_target(economy_ids), **common),
    ), name="global_financial_crisis_template")


def pandemic_scenario(
    *, start_tick: int, duration_ticks: int = 540,
    economy_ids: Sequence[int] | None = None, announcement_lead_ticks: int = 0,
    include_trade: bool = True,
) -> ShockTape:
    common = dict(
        start_tick=start_tick, duration_ticks=duration_ticks,
        ramp_out_ticks=min(180, duration_ticks // 3),
        announcement_tick=max(0, start_tick - announcement_lead_ticks),
        source="illustrative_covid19_template", correlation_group="pandemic",
        tags=("historical_template", "pandemic"),
        calibration_note="Illustrative reduced-form package; policy response excluded.",
    )
    specs = [
        ShockSpec("pandemic.labor", "labor_availability", magnitude=0.25,
                  target=_target(economy_ids), **common),
        ShockSpec("pandemic.productivity", "productivity", magnitude=0.12,
                  target=_target(economy_ids), **common),
        ShockSpec("pandemic.demand", "household_demand", magnitude=0.16,
                  target=_target(economy_ids), **common),
        ShockSpec("pandemic.credit", "credit_supply", magnitude=0.12,
                  target=_target(economy_ids), **common),
    ]
    if include_trade:
        specs.extend((
            ShockSpec("pandemic.imports", "import_capacity", magnitude=0.30,
                      target=_target(economy_ids), **common),
            ShockSpec("pandemic.exports", "export_capacity", magnitude=0.25,
                      target=_target(economy_ids), **common),
        ))
    return ShockTape(tuple(specs), name="pandemic_template")


def natural_disaster_scenario(
    *, start_tick: int, recovery_ticks: int = 180,
    economy_ids: Sequence[int] | None = None,
    capital_loss: float = 0.20,
) -> ShockTape:
    target = _target(economy_ids)
    note = "Illustrative natural-disaster package; no reconstruction policy included."
    return ShockTape((
        ShockSpec(
            "natural_disaster.capital", "capital_destruction", start_tick,
            capital_loss, target=target, duration_ticks=1, announcement_tick=start_tick,
            source="illustrative_natural_disaster_template",
            calibration_note=note, correlation_group="natural_disaster",
            tags=("historical_template", "disaster"),
        ),
        ShockSpec(
            "natural_disaster.productivity", "productivity", start_tick,
            0.15, target=target, duration_ticks=recovery_ticks,
            ramp_out_ticks=min(90, recovery_ticks // 2), announcement_tick=start_tick,
            source="illustrative_natural_disaster_template",
            calibration_note=note, correlation_group="natural_disaster",
            tags=("historical_template", "disaster"),
        ),
        ShockSpec(
            "natural_disaster.labor", "labor_availability", start_tick,
            0.10, target=target, duration_ticks=min(30, recovery_ticks),
            ramp_out_ticks=min(10, max(0, min(30, recovery_ticks) // 3)),
            announcement_tick=start_tick,
            source="illustrative_natural_disaster_template",
            calibration_note=note, correlation_group="natural_disaster",
            tags=("historical_template", "disaster"),
        ),
    ), name="natural_disaster_template")
