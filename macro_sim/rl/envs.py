"""Versioned, reproducible training environments backed by the real engine.

The benchmark in this module is intentionally narrow: a treasury controls only
the deficit target while being scored on released unemployment, inflation and
real output.  Keeping the task small makes it useful as an integration and
learning gate; it is not a claim that one fiscal lever represents a complete
economic mandate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import math
from numbers import Integral, Real
from typing import Any, Mapping

from macro_sim.config import Config
from macro_sim.controllers.gym_adapter import ControllerEnv
from macro_sim.controllers.protocol import canonical_json
from macro_sim.controllers.observation import (
    DEFAULT_OBSERVATION_SPEC,
    ObjectiveEvaluator,
    ObjectiveSpec,
    ObjectiveTerm,
)
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World

from .codec import ContextCodec, DirectionalActionCodec


FISCAL_STABILIZATION_TASK = "fiscal_stabilization_v1"


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _finite(name: str, value: Any, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def fiscal_stabilization_objective() -> ObjectiveSpec:
    """Return the frozen public-information mandate for the v1 benchmark."""
    return ObjectiveSpec(
        terms=(
            ObjectiveTerm(
                "unemployment_rate", "bounds", (0.0, 0.08),
                weight=1.0, normalization_scale=0.10,
            ),
            ObjectiveTerm(
                "inflation", "bounds", (-0.001, 0.001),
                weight=0.10, normalization_scale=0.005,
            ),
            ObjectiveTerm(
                "real_output", "maximize",
                weight=0.20, normalization_scale=100.0,
            ),
        ),
        control_cost_weight=0.01,
        time_normalization="per_tick",
    )


@dataclass(frozen=True, slots=True)
class FiscalStabilizationConfig:
    """Pickle-safe parameters for the real-engine learning benchmark."""

    horizon_ticks: int = 730
    decision_period_ticks: int = 15
    n_households: int = 20
    n_firms_c: int = 15
    n_firms_k: int = 8
    n_banks: int = 2
    initial_deficit_target: float = 0.0
    task_id: str = FISCAL_STABILIZATION_TASK

    def __post_init__(self) -> None:
        for name in (
            "horizon_ticks", "decision_period_ticks", "n_households",
            "n_firms_c", "n_firms_k", "n_banks",
        ):
            object.__setattr__(self, name, _positive_int(name, getattr(self, name)))
        if self.decision_period_ticks > self.horizon_ticks:
            raise ValueError("decision_period_ticks cannot exceed horizon_ticks")
        target = _finite(
            "initial_deficit_target", self.initial_deficit_target, minimum=0.0,
        )
        if target > 0.30:
            raise ValueError("initial_deficit_target must be <= 0.30")
        object.__setattr__(self, "initial_deficit_target", target)
        if self.task_id != FISCAL_STABILIZATION_TASK:
            raise ValueError(f"unsupported task_id {self.task_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FiscalStabilizationConfig":
        if not isinstance(value, Mapping):
            raise TypeError("environment config must be a mapping")
        expected = {field.name for field in fields(cls)}
        actual = set(value)
        if actual != expected:
            raise ValueError(
                "environment config keys differ; "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class FiscalStabilizationEnvFactory:
    """Callable environment factory suitable for local or spawned workers."""

    config: FiscalStabilizationConfig = FiscalStabilizationConfig()

    def __post_init__(self) -> None:
        if not isinstance(self.config, FiscalStabilizationConfig):
            raise TypeError("config must be a FiscalStabilizationConfig")

    @property
    def task_id(self) -> str:
        return self.config.task_id

    @property
    def environment_contract(self) -> dict[str, Any]:
        """Return every experiment assumption not captured by vector codecs."""
        observation_json = canonical_json(DEFAULT_OBSERVATION_SPEC.to_dict())
        return {
            "action_levers": ["gov_deficit_target"],
            "config": self.config.to_dict(),
            "economy_id": 0,
            "episode_decisions": (
                self.config.horizon_ticks - 1
            ) // self.config.decision_period_ticks + 1,
            "horizon_semantics": "finite_terminated",
            "objective": fiscal_stabilization_objective().to_dict(),
            "observation_spec_sha256": hashlib.sha256(
                observation_json.encode("utf-8")
            ).hexdigest(),
            "schema_version": 1,
            "seat": "treasury",
            "task_id": self.task_id,
            "triggers": [],
            "world_preset": "Config.v13",
        }

    @property
    def environment_contract_hash(self) -> str:
        return hashlib.sha256(
            canonical_json(self.environment_contract).encode("utf-8")
        ).hexdigest()

    def __call__(self, seed: int) -> ControllerEnv:
        if isinstance(seed, bool) or not isinstance(seed, Integral):
            raise TypeError("environment seed must be an integer")
        checked_seed = int(seed)
        if not 0 <= checked_seed < 2**63:
            raise ValueError("environment seed must be in [0, 2**63)")

        cfg = self.config
        calendars = {
            name: CalendarSpec(
                period_ticks=cfg.horizon_ticks + 2,
                offset_ticks=cfg.horizon_ticks + 1,
                admin_capacity=100.0,
            )
            for name in DEFAULT_CALENDARS
        }
        calendars["fiscal_stance"] = CalendarSpec(
            period_ticks=cfg.decision_period_ticks,
            admin_capacity=100.0,
        )
        world_config = Config.v13(
            seed=checked_seed,
            n_households=cfg.n_households,
            n_firms_c=cfg.n_firms_c,
            n_firms_k=cfg.n_firms_k,
            n_banks=cfg.n_banks,
            n_ticks=cfg.horizon_ticks,
            government=True,
            gov_deficit_target=cfg.initial_deficit_target,
        )
        session = ControlledSimulationSession(
            World([world_config]),
            scheduler=DecisionScheduler(calendars=calendars, triggers=()),
        )

        fields = tuple(DEFAULT_OBSERVATION_SPEC.fields)
        scales = {
            field.series_id: (
                1.0 if field.normalization_scale is None
                else field.normalization_scale
            )
            for field in fields
        }
        context_codec = ContextCodec.from_parts(
            economy_id=0,
            seat="treasury",
            action_levers=("gov_deficit_target",),
            observation_series=tuple(scales),
            normalization_scales=scales,
            observation_schema_version=DEFAULT_OBSERVATION_SPEC.schema_version,
        )
        action_codec = DirectionalActionCodec.from_context_codec(context_codec)
        return ControllerEnv(
            session,
            economy_id=0,
            seat="treasury",
            objective_evaluator=ObjectiveEvaluator(
                fiscal_stabilization_objective(), DEFAULT_OBSERVATION_SPEC,
            ),
            max_boundary_tick=cfg.horizon_ticks,
            terminate_on_horizon=True,
            action_levers=("gov_deficit_target",),
            context_codec=context_codec,
            action_codec=action_codec,
        )


def make_fiscal_stabilization_env(
    seed: int,
    config: FiscalStabilizationConfig | None = None,
) -> ControllerEnv:
    """Convenience constructor for notebooks, smoke tests and the CLI."""
    return FiscalStabilizationEnvFactory(
        FiscalStabilizationConfig() if config is None else config,
    )(seed)
