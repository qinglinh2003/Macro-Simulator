"""Stable observable phase identifiers for the Python migration oracle."""

from __future__ import annotations

from dataclasses import dataclass


BOUNDARY_CONTROL = "phase.boundary.control"
ECONOMY_OPEN_BOOKS = "phase.economy.open-books"
ECONOMY_OPEN_FINANCIAL_SYSTEM = "phase.economy.open-financial-system"
ECONOMY_OPEN_REAL_ECONOMY = "phase.economy.open-real-economy"
ECONOMY_POPULATION_BOUNDARY = "phase.economy.population-boundary"
ECONOMY_PLAN_AND_FINANCE = "phase.economy.plan-and-finance"
ECONOMY_PRODUCE_AND_TRADE_DOMESTIC = (
    "phase.economy.produce-and-trade-domestic"
)
WORLD_EXTERNAL_SETTLEMENT_SEAM = "phase.world.external-settlement-seam"
WORLD_DEALER_SETTLEMENT = "phase.world.dealer-settlement"
ECONOMY_SETTLE_DOMESTIC = "phase.economy.settle-domestic"
ECONOMY_CLOSE_INSTITUTIONS = "phase.economy.close-institutions"
ECONOMY_VALIDATE_AND_MEASURE = "phase.economy.validate-and-measure"
WORLD_VALIDATE_GLOBAL = "phase.world.validate-global"
ECONOMY_STAGE_LOCAL_COMMIT = "phase.economy.stage-local-commit"
WORLD_COMMIT_BOUNDARY = "phase.world.commit-boundary"
WORLD_PUBLISH = "phase.world.publish"


@dataclass(frozen=True, slots=True)
class PhaseDescriptor:
    id: str
    code: str
    ordinal: int
    snapshot_epoch: str
    scope: str


PHASES = (
    PhaseDescriptor(BOUNDARY_CONTROL, "B0", 0, "tick_open", "session"),
    PhaseDescriptor(ECONOMY_OPEN_BOOKS, "E0", 10, "books_open", "economy"),
    PhaseDescriptor(
        ECONOMY_OPEN_FINANCIAL_SYSTEM,
        "E1",
        20,
        "financial_open",
        "economy",
    ),
    PhaseDescriptor(
        ECONOMY_OPEN_REAL_ECONOMY,
        "E2",
        30,
        "real_open",
        "economy",
    ),
    PhaseDescriptor(
        ECONOMY_POPULATION_BOUNDARY,
        "E3",
        40,
        "post_population_pre_plan",
        "economy",
    ),
    PhaseDescriptor(ECONOMY_PLAN_AND_FINANCE, "E4", 50, "planned", "economy"),
    PhaseDescriptor(
        ECONOMY_PRODUCE_AND_TRADE_DOMESTIC,
        "E5",
        60,
        "pre_dealer",
        "economy",
    ),
    PhaseDescriptor(
        WORLD_EXTERNAL_SETTLEMENT_SEAM,
        "W0",
        70,
        "external_reserved",
        "world",
    ),
    PhaseDescriptor(
        WORLD_DEALER_SETTLEMENT,
        "W.DealerSettlement",
        80,
        "post_dealer",
        "world",
    ),
    PhaseDescriptor(
        WORLD_VALIDATE_GLOBAL,
        "W.ValidateGlobal",
        85,
        "globally_validated",
        "world",
    ),
    PhaseDescriptor(
        ECONOMY_SETTLE_DOMESTIC,
        "E6",
        90,
        "domestic_settled",
        "economy",
    ),
    PhaseDescriptor(
        ECONOMY_CLOSE_INSTITUTIONS,
        "E7",
        100,
        "institutions_closed",
        "economy",
    ),
    PhaseDescriptor(
        ECONOMY_VALIDATE_AND_MEASURE,
        "E8",
        110,
        "provisional_measured",
        "economy",
    ),
    PhaseDescriptor(
        ECONOMY_STAGE_LOCAL_COMMIT,
        "E9",
        130,
        "local_staged",
        "economy",
    ),
    PhaseDescriptor(
        WORLD_COMMIT_BOUNDARY,
        "W.CommitBoundary",
        140,
        "committed",
        "world",
    ),
    PhaseDescriptor(WORLD_PUBLISH, "W.Publish", 150, "published", "session"),
)

PHASE_BY_ID = {phase.id: phase for phase in PHASES}

if len(PHASE_BY_ID) != len(PHASES):
    raise RuntimeError("duplicate phase identifier")
