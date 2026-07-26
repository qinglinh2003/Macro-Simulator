"""Native-engine controller environments for deployment and evaluation gates."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Integral, Real
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import numpy as np

from macro_sim.config import Config
from macro_sim.controllers.costs import AdjustmentCostSpec
from macro_sim.controllers.native_observation import NativeObservationSource
from macro_sim.controllers.observation import (
    DEFAULT_OBSERVATION_SPEC,
    ObjectiveEvaluator,
    ReleaseService,
)
from macro_sim.controllers.protocol import DecisionContext, PermittedAction
from macro_sim.controllers.protocol import canonical_json
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.native_backend import NativeSimulationSession

from .codec import ContextCodec, DirectionalActionCodec
from .envs import (
    FISCAL_STABILIZATION_TASK,
    FiscalStabilizationConfig,
    fiscal_stabilization_objective,
)


def _finite_reward(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _fiscal_codecs() -> tuple[ContextCodec, DirectionalActionCodec]:
    fields = tuple(DEFAULT_OBSERVATION_SPEC.fields)
    scales = {
        field.series_id: (
            1.0 if field.normalization_scale is None
            else field.normalization_scale
        )
        for field in fields
    }
    context = ContextCodec.from_parts(
        economy_id=0,
        seat="treasury",
        action_levers=("gov_deficit_target",),
        observation_series=tuple(scales),
        normalization_scales=scales,
        observation_schema_version=DEFAULT_OBSERVATION_SPEC.schema_version,
    )
    return context, DirectionalActionCodec.from_context_codec(context)


@dataclass(frozen=True, slots=True)
class _PendingFiscalAction:
    value: float
    accepted_tick: int
    effective_tick: int
    adjustment_cost: float


class NativeFiscalStabilizationEnv:
    """Fiscal SMDP task whose only economic state owner is the C++ World.

    M10 deliberately keeps the reviewed release calendar and reward evaluator in
    Python.  Every economic day, policy mutation, checkpoint, and reset is
    executed by the native session.  M11 moves the remaining controller state
    machine behind the standalone native worker.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        seed: int,
        config: FiscalStabilizationConfig | None = None,
        *,
        worker_count: int = 8,
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, Integral):
            raise TypeError("environment seed must be an integer")
        checked_seed = int(seed)
        if not 0 <= checked_seed < 2**63:
            raise ValueError("environment seed must be in [0, 2**63)")
        self.config = (
            FiscalStabilizationConfig() if config is None else config
        )
        if not isinstance(self.config, FiscalStabilizationConfig):
            raise TypeError("config must be a FiscalStabilizationConfig")
        if isinstance(worker_count, bool) or not isinstance(worker_count, int) \
                or worker_count < 1:
            raise ValueError("worker_count must be a positive integer")
        self.seed = checked_seed
        self.worker_count = worker_count
        self.economy_id = 0
        self.seat = "treasury"
        self.action_levers = ("gov_deficit_target",)
        self.action_dimensions = (("gov_deficit_target", None),)
        self._economy_targets: tuple[int, ...] = ()
        self.context_codec, self.action_codec = _fiscal_codecs()
        self.observation_features = self.context_codec.feature_names
        self.objective_spec = fiscal_stabilization_objective()
        self.cost_spec = AdjustmentCostSpec()
        self._source_config = self._make_config()
        self._session = NativeSimulationSession.create_from_configs(
            (self._source_config,),
            worker_count=worker_count,
            history_capacity_frames=self.config.horizon_ticks + 2,
        )
        self._genesis_checkpoint = self._session.checkpoint(
            self._objective_envelope()
        )
        self._ready = False
        self.context: DecisionContext | None = None
        self._pending: _PendingFiscalAction | None = None
        self._policy_version = 0
        self._last_effective_tick: int | None = None
        self._previous_decision_tick: int | None = None
        self._reset_publication_state()

    def _make_config(self) -> Config:
        cfg = self.config
        return Config.v13(
            seed=self.seed,
            n_households=cfg.n_households,
            n_firms_c=cfg.n_firms_c,
            n_firms_k=cfg.n_firms_k,
            n_banks=cfg.n_banks,
            n_ticks=cfg.horizon_ticks,
            government=True,
            gov_deficit_target=cfg.initial_deficit_target,
        )

    def _objective_envelope(self) -> bytes:
        return json.dumps(
            {
                "environment": FISCAL_STABILIZATION_TASK,
                "horizon_ticks": self.config.horizon_ticks,
                "schema_version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _reset_publication_state(self) -> None:
        self.source = NativeObservationSource(self._session)
        self.release_service = ReleaseService(DEFAULT_OBSERVATION_SPEC)
        self.objective_evaluator = ObjectiveEvaluator(
            self.objective_spec, DEFAULT_OBSERVATION_SPEC,
        )

    @property
    def boundary_tick(self) -> int:
        return self._session.tick

    @property
    def native_session(self) -> NativeSimulationSession:
        return self._session

    def _current_target(self) -> float:
        return float(
            self._session.bridge.domestic_policy(
                self.economy_id
            ).fiscal_monetary.government_deficit_target
        )

    def _next_eligibility_tick(self, boundary: int) -> int:
        lever = REGISTRY["gov_deficit_target"]
        implementation = boundary + lever.implementation_lag
        if self._last_effective_tick is None:
            return implementation
        return max(
            implementation,
            self._last_effective_tick + lever.min_hold_ticks,
        )

    def _context(
        self, boundary: int, *, elapsed_ticks: int, terminal: bool = False,
    ) -> DecisionContext:
        lever = REGISTRY["gov_deficit_target"]
        current = self._current_target()
        earliest = boundary + lever.implementation_lag
        hold_until = (
            earliest if self._last_effective_tick is None
            else self._last_effective_tick + lever.min_hold_ticks
        )
        allowed = (
            not terminal
            and self._pending is None
            and earliest >= hold_until
        )
        reason = None
        if terminal:
            reason = "episode_horizon"
        elif self._pending is not None:
            reason = "pending_change"
        elif not allowed:
            reason = "minimum_hold"
        validation = lever.validation
        observation = self.release_service.observe(
            self.source,
            boundary,
            economy_id=self.economy_id,
            role=self.seat,
            elapsed_ticks=elapsed_ticks,
        )
        pending_policy: dict[str, float] = {}
        pending_ticks: dict[str, int] = {}
        if self._pending is not None:
            pending_policy[lever.name] = self._pending.value
            pending_ticks[lever.name] = self._pending.effective_tick
        next_eligibility = self._next_eligibility_tick(boundary)
        permitted = PermittedAction(
            lever=lever.name,
            current_value=current,
            allowed=allowed,
            reason_code=reason,
            value_kind="number",
            minimum=getattr(validation, "lo", None),
            maximum=getattr(validation, "hi", None),
            control_scale=lever.control_scale,
            max_step=getattr(validation, "max_step", None),
            earliest_effective_tick=earliest,
        )
        return DecisionContext(
            context_id=(
                f"native:terminal:{boundary}" if terminal
                else f"native:ctx:0:treasury:fiscal_stance:{boundary}"
            ),
            decision_window_id=(
                f"native:terminal:{boundary}"
                if terminal else f"native:fiscal_stance:{boundary}"
            ),
            economy_id=self.economy_id,
            seat=self.seat,
            decision_group="fiscal_stance",
            boundary_tick=boundary,
            expires_at_tick=boundary,
            policy_versions={lever.name: self._policy_version},
            observation=observation,
            permitted_actions=(permitted,),
            pending_policy=pending_policy,
            current_policy={lever.name: current},
            pending_effective_ticks=pending_ticks,
            elapsed_ticks=elapsed_ticks,
            last_effective_ticks={
                lever.name: self._last_effective_tick,
            },
            next_eligibility_ticks={
                lever.name: next_eligibility,
            },
            admin_remaining=100.0,
            admin_reserved=0.0,
            admin_capacity=100.0,
            visible_cost_estimates={
                lever.name: {
                    "cost_class": lever.cost_class,
                    "down": self._direction_cost(current, -1),
                    "up": self._direction_cost(current, 1),
                }
            },
            observation_schema_version=DEFAULT_OBSERVATION_SPEC.schema_version,
        )

    def _direction_cost(self, current: float, direction: int) -> float:
        lever = REGISTRY["gov_deficit_target"]
        scale = float(lever.control_scale or 0.0)
        validation = lever.validation
        desired = current + direction * scale
        desired = min(
            float(getattr(validation, "hi", desired)),
            max(float(getattr(validation, "lo", desired)), desired),
        )
        if desired == current:
            return 0.0
        return float(self.cost_spec.estimate((
            SimpleNamespace(lever=lever, old=current, new=desired),
        )))

    def _release_history(self, boundary: int) -> dict[str, Any]:
        return {
            term.series_id: self.release_service.history(
                self.economy_id, term.series_id, as_of_tick=boundary,
                limit=term.evaluation_window,
            )
            for term in self.objective_spec.terms
        }

    def _evaluate_boundary(self, boundary: int):
        observation = self.release_service.observe(
            self.source,
            boundary,
            economy_id=self.economy_id,
            role=self.seat,
            elapsed_ticks=1,
        )
        return self.objective_evaluator.evaluate(
            observation,
            adjustment_cost=0.0,
            elapsed_ticks=1,
            release_history=self._release_history(boundary),
        )

    def _vector(self, context: DecisionContext) -> np.ndarray:
        output = np.asarray(
            self.context_codec.encode(context), dtype=np.float64,
        )
        if output.shape != (len(self.observation_features),):
            raise RuntimeError("native fiscal observation shape drifted")
        return output

    def _action_mask(self, context: DecisionContext) -> np.ndarray:
        return np.asarray(
            self.action_codec.action_mask(
                context, context_codec=self.context_codec,
            ),
            dtype=np.bool_,
        )

    def _info(
        self,
        context: DecisionContext,
        *,
        elapsed_ticks: int,
        decisions: Sequence[Mapping[str, Any]] = (),
        objective: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        mask = self._action_mask(context)
        current = self._current_target()
        info: dict[str, Any] = {
            "action_contract_hash": self.action_codec.contract_hash,
            "action_costs": np.asarray([[
                self._direction_cost(current, -1),
                self._direction_cost(current, 1),
            ]], dtype=np.float64),
            "action_dimensions": self.action_dimensions,
            "action_levers": self.action_levers,
            "action_mask": mask,
            "context": context.to_dict(),
            "context_json": context.to_json(),
            "context_contract_hash": self.context_codec.contract_hash,
            "decisions": [dict(item) for item in decisions],
            "elapsed_ticks": elapsed_ticks,
            "objective_profile": "human_comparable",
            "observation_features": self.observation_features,
            "reward_time_normalization": "per_tick",
        }
        if objective is not None:
            info["objective"] = dict(objective)
        return info

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, Mapping[str, Any]]:
        del options
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, Integral):
                raise TypeError("environment seed must be an integer")
            if int(seed) != self.seed:
                raise ValueError(
                    "reseed by constructing the seed-specific native environment"
                )
        self._session, objective = NativeSimulationSession.restore(
            self._session.spec,
            self._genesis_checkpoint,
            worker_count=self.worker_count,
        )
        if objective != self._objective_envelope():
            raise RuntimeError("native fiscal objective checkpoint drifted")
        self._pending = None
        self._policy_version = 0
        self._last_effective_tick = None
        self._previous_decision_tick = 0
        self._reset_publication_state()
        self.context = self._context(0, elapsed_ticks=0)
        self.objective_evaluator.evaluate(
            self.context.observation,
            adjustment_cost=0.0,
            elapsed_ticks=1,
            release_history=self._release_history(0),
        )
        self._ready = True
        return self._vector(self.context), self._info(
            self.context, elapsed_ticks=0,
        )

    def _decode_action(self, action: Any, context: DecisionContext) -> float | None:
        if isinstance(action, Mapping):
            unknown = set(action) - {"gov_deficit_target"}
            if unknown:
                raise ValueError(
                    f"native fiscal action contains unknown levers {sorted(unknown)}"
                )
            if "gov_deficit_target" not in action:
                return None
            raw = action["gov_deficit_target"]
            if isinstance(raw, bool) or not isinstance(raw, Real):
                raise TypeError("gov_deficit_target action must be numeric")
            desired = _finite_reward("gov_deficit_target action", raw)
        else:
            actions = self.action_codec.decode(
                np.asarray(action),
                context,
                context_codec=self.context_codec,
                strict=False,
            )
            if not actions:
                return None
            desired = float(actions[0].value)
        current = self._current_target()
        error = REGISTRY["gov_deficit_target"].validation.check(
            current, desired,
        )
        if error is not None:
            raise ValueError(f"gov_deficit_target: {error}")
        return None if desired == current else desired

    def step(
        self, action: Any,
    ) -> tuple[np.ndarray, float, bool, bool, Mapping[str, Any]]:
        if not self._ready or self.context is None:
            raise RuntimeError("reset() must be called before step()")
        previous = self.context
        desired = self._decode_action(action, previous)
        permitted = previous.permitted_actions[0]
        decision: dict[str, Any]
        interval_cost = 0.0
        if desired is None:
            decision = {
                "adjustment_cost": 0.0,
                "effective_tick": None,
                "reason_code": "no_change",
                "status": "accepted_noop",
            }
        elif not permitted.allowed:
            decision = {
                "adjustment_cost": 0.0,
                "effective_tick": None,
                "reason_code": permitted.reason_code or "not_permitted",
                "status": "rejected",
            }
        else:
            lever = REGISTRY["gov_deficit_target"]
            cost = float(self.cost_spec.estimate((
                SimpleNamespace(
                    lever=lever,
                    old=self._current_target(),
                    new=desired,
                ),
            )))
            self._pending = _PendingFiscalAction(
                value=desired,
                accepted_tick=previous.boundary_tick,
                effective_tick=(
                    previous.boundary_tick + lever.implementation_lag
                ),
                adjustment_cost=cost,
            )
            decision = {
                "adjustment_cost": cost,
                "effective_tick": self._pending.effective_tick,
                "reason_code": "accepted",
                "status": "pending",
            }

        target = min(
            previous.boundary_tick + self.config.decision_period_ticks,
            self.config.horizon_ticks,
        )
        evaluations = []
        while self._session.tick < target:
            actions: tuple[dict[str, Any], ...] = ()
            pending = self._pending
            if pending is not None and pending.effective_tick == self._session.tick:
                actions = ({
                    "economy_id": self.economy_id,
                    "lever": "gov_deficit_target",
                    "value": pending.value,
                },)
            self._session.advance(actions=actions)
            self.source.refresh()
            if actions:
                assert pending is not None
                interval_cost += pending.adjustment_cost
                self._last_effective_tick = pending.effective_tick
                self._policy_version += 1
                decision["reason_code"] = "effective"
                decision["status"] = "effective"
                self._pending = None
            evaluations.append(self._evaluate_boundary(self._session.tick))

        elapsed = target - previous.boundary_tick
        if elapsed <= 0:
            raise RuntimeError("native fiscal environment did not advance")
        macro_reward = sum(item.macro_reward for item in evaluations) / elapsed
        control_penalty = (
            self.objective_spec.control_cost_weight * interval_cost / elapsed
        )
        reward = _finite_reward(
            "native fiscal reward", macro_reward - control_penalty,
        )
        component_names = sorted({
            name for item in evaluations for name in item.components
        })
        objective = {
            "components": {
                name: sum(
                    item.components.get(name, 0.0) for item in evaluations
                ) / elapsed
                for name in component_names
            },
            "control_cost_penalty": control_penalty,
            "elapsed_ticks": elapsed,
            "macro_reward": macro_reward,
            "missing": (
                dict(evaluations[-1].missing) if evaluations else {}
            ),
            "profile": "human_comparable",
            "total_reward": reward,
        }
        terminated = target >= self.config.horizon_ticks
        self.context = self._context(
            target, elapsed_ticks=elapsed, terminal=terminated,
        )
        info = self._info(
            self.context,
            elapsed_ticks=elapsed,
            decisions=(decision,),
            objective=objective,
        )
        if terminated:
            info["terminal_observation"] = True
            self._ready = False
        return self._vector(self.context), reward, terminated, False, info

    def checkpoint(self) -> bytes:
        """Return the complete native economic checkpoint for this boundary."""
        if self._pending is not None:
            raise RuntimeError(
                "checkpoint at a decision boundary before submitting an action"
            )
        return self._session.checkpoint(self._objective_envelope())

    def clone(self) -> "NativeFiscalStabilizationEnv":
        """Clone the current boundary through the native composite clone API."""
        if self._pending is not None:
            raise RuntimeError("cannot clone with an in-flight policy action")
        clone = type(self)(
            self.seed, self.config, worker_count=self.worker_count,
        )
        clone._session = self._session.clone()
        clone._policy_version = self._policy_version
        clone._last_effective_tick = self._last_effective_tick
        clone._previous_decision_tick = self._previous_decision_tick
        clone._reset_publication_state()
        # Publication and objective ledgers are deterministic functions of the
        # retained native source frames, so replay them to the current boundary.
        opening = clone.release_service.observe(
            clone.source, 0, economy_id=0, role="treasury", elapsed_ticks=0,
        )
        clone.objective_evaluator.evaluate(
            opening,
            adjustment_cost=0.0,
            elapsed_ticks=1,
            release_history=clone._release_history(0),
        )
        for boundary in range(1, self._session.tick + 1):
            clone._evaluate_boundary(boundary)
        clone.context = clone._context(
            self._session.tick,
            elapsed_ticks=(
                0 if self.context is None else self.context.elapsed_ticks
            ),
            terminal=self._session.tick >= self.config.horizon_ticks,
        )
        clone._ready = self._ready
        return clone

    def close(self) -> None:
        self._ready = False
        self.context = None


@dataclass(frozen=True, slots=True)
class NativeFiscalStabilizationEnvFactory:
    """Seeded factory consumed by evaluation and vector-environment runners."""

    config: FiscalStabilizationConfig = FiscalStabilizationConfig()
    worker_count: int = 8

    @property
    def task_id(self) -> str:
        return self.config.task_id

    @property
    def environment_contract(self) -> dict[str, Any]:
        """Declare the native dynamics instead of impersonating the old task."""
        observation_json = canonical_json(
            DEFAULT_OBSERVATION_SPEC.to_dict()
        )
        return {
            "action_levers": ["gov_deficit_target"],
            "config": self.config.to_dict(),
            "economy_id": 0,
            "engine_backend": "native_m10_world",
            "episode_decisions": (
                self.config.horizon_ticks - 1
            ) // self.config.decision_period_ticks + 1,
            "horizon_semantics": "finite_terminated",
            "objective": fiscal_stabilization_objective().to_dict(),
            "observation_spec_sha256": hashlib.sha256(
                observation_json.encode("utf-8")
            ).hexdigest(),
            "schema_version": 2,
            "seat": "treasury",
            "task_id": self.task_id,
            "triggers": [],
            "world_preset": "Config.v13_to_native_m9",
        }

    @property
    def environment_contract_hash(self) -> str:
        return hashlib.sha256(
            canonical_json(self.environment_contract).encode("utf-8")
        ).hexdigest()

    def __call__(self, seed: int) -> NativeFiscalStabilizationEnv:
        return NativeFiscalStabilizationEnv(
            seed, self.config, worker_count=self.worker_count,
        )


def make_native_fiscal_stabilization_env(
    seed: int,
    config: FiscalStabilizationConfig | None = None,
    *,
    worker_count: int = 8,
) -> NativeFiscalStabilizationEnv:
    return NativeFiscalStabilizationEnv(
        seed, config, worker_count=worker_count,
    )
