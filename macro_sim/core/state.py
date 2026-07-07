"""Shared simulation state carrier used by extracted systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any


@dataclass
class SimulationState:
    cfg: Any
    policy: Any
    rng: Random
    ledger: Any
    households: list
    firms: list
    c_firms: list
    k_firms: list
    banks: list
    records: list = field(default_factory=list)
