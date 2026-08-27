"""Closed registry of semantic shock channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .spec import SECTORS, ShockSpec


@dataclass(frozen=True)
class ShockDefinition:
    kind: str
    channel: str
    description: str
    magnitude_min: float = -3.0
    magnitude_max: float = 0.99
    one_shot: bool = False
    allowed_sectors: frozenset[str] = frozenset()
    required_capability: str | None = None
    emergency_seats: tuple[str, ...] = ()


class ShockRegistry:
    def __init__(self, definitions: tuple[ShockDefinition, ...]):
        ids = [item.kind for item in definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate ShockDefinition kind")
        self._definitions: Mapping[str, ShockDefinition] = {
            item.kind: item for item in definitions
        }

    def __contains__(self, kind: str) -> bool:
        return kind in self._definitions

    def __getitem__(self, kind: str) -> ShockDefinition:
        try:
            return self._definitions[kind]
        except KeyError as exc:
            raise ValueError(f"unknown shock kind {kind!r}") from exc

    def items(self):
        return self._definitions.items()

    def validate_spec(self, spec: ShockSpec) -> None:
        definition = self[spec.kind]
        if not definition.magnitude_min <= spec.magnitude <= definition.magnitude_max:
            raise ValueError(
                f"{spec.kind} magnitude must be in "
                f"[{definition.magnitude_min}, {definition.magnitude_max}]"
            )
        if definition.one_shot:
            if spec.duration_ticks not in {None, 1}:
                raise ValueError(f"one-shot {spec.kind} cannot have a multi-tick duration")
            if spec.ramp_in_ticks or spec.ramp_out_ticks:
                raise ValueError(f"one-shot {spec.kind} cannot have ramps")
        sectors = set(spec.target.sectors)
        if sectors and not definition.allowed_sectors:
            raise ValueError(f"{spec.kind} does not accept sector targets")
        unknown = sectors - set(definition.allowed_sectors)
        if unknown:
            raise ValueError(f"{spec.kind} does not support sectors {sorted(unknown)}")


_FIRM_SECTORS = frozenset({"consumption", "necessity", "luxury", "capital", "energy", "housing"})

DEFAULT_SHOCK_REGISTRY = ShockRegistry((
    ShockDefinition(
        "productivity", "productivity", "Sector output-factor disturbance.",
        allowed_sectors=_FIRM_SECTORS,
        emergency_seats=("central_bank", "treasury"),
    ),
    ShockDefinition(
        "labor_availability", "labor_availability",
        "Effective attendance/available-labor disturbance.",
        allowed_sectors=_FIRM_SECTORS,
        emergency_seats=("treasury",),
    ),
    ShockDefinition(
        "energy_capacity", "energy_capacity", "Physical energy capacity disturbance.",
        allowed_sectors=frozenset({"energy"}), required_capability="energy_enabled",
        emergency_seats=("energy", "treasury"),
    ),
    ShockDefinition(
        "household_demand", "household_demand", "Household desired-spending disturbance.",
        emergency_seats=("central_bank", "treasury"),
    ),
    ShockDefinition(
        "import_capacity", "import_capacity", "Importer-side physical trade capacity.",
        required_capability="world_trade",
        emergency_seats=("external_affairs", "treasury"),
    ),
    ShockDefinition(
        "export_capacity", "export_capacity", "Exporter-side physical shipping capacity.",
        required_capability="world_trade",
        emergency_seats=("external_affairs", "treasury"),
    ),
    ShockDefinition(
        "credit_supply", "credit_supply", "Bank loan-origination supply disturbance.",
        allowed_sectors=frozenset({"housing"}),
        required_capability="bank_enabled",
        emergency_seats=("central_bank", "regulator", "treasury"),
    ),
    ShockDefinition(
        "capital_destruction", "capital_destruction",
        "One-shot destruction of private/public physical capital.",
        magnitude_min=0.0, magnitude_max=0.99, one_shot=True,
        allowed_sectors=frozenset(SECTORS),
        emergency_seats=("treasury",),
    ),
    ShockDefinition(
        "sovereign_risk_premium", "sovereign_risk_premium",
        "Additive required-return spread on sovereign debt.",
        magnitude_min=0.0, magnitude_max=0.99,
        required_capability="bonds",
        emergency_seats=("central_bank", "regulator", "treasury"),
    ),
))
