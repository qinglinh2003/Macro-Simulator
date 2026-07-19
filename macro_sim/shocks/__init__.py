"""Public shock-engine API."""

from .engine import ShockEngine, ShockEventStream, get_shock_engine, legacy_energy_spec
from .registry import DEFAULT_SHOCK_REGISTRY, ShockDefinition, ShockRegistry
from .scenarios import (
    global_financial_crisis_scenario,
    natural_disaster_scenario,
    oil_embargo_scenario,
    pandemic_scenario,
)
from .spec import SHOCK_SCHEMA_VERSION, ShockSpec, ShockTape, ShockTarget
from .stochastic import generate_poisson_tape

__all__ = [
    "DEFAULT_SHOCK_REGISTRY",
    "SHOCK_SCHEMA_VERSION",
    "ShockDefinition",
    "ShockEngine",
    "ShockEventStream",
    "ShockRegistry",
    "ShockSpec",
    "ShockTape",
    "ShockTarget",
    "generate_poisson_tape",
    "get_shock_engine",
    "global_financial_crisis_scenario",
    "legacy_energy_spec",
    "natural_disaster_scenario",
    "oil_embargo_scenario",
    "pandemic_scenario",
]
