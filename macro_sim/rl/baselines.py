"""Framework-neutral policy adapters and reproducible evaluation baselines.

The training package deliberately talks to policies through the small
``EvaluationPolicy`` protocol instead of importing a particular RL framework.
This keeps saved-model compatibility at the edge: an SB3-like model, the native
SMDP trainer, deterministic heuristics, and stochastic baselines all enter the
same evaluator without weakening the :class:`~macro_sim.controllers.ControllerEnv`
authority boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import math
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

import numpy as np

from macro_sim.controllers.protocol import immutable_json_mapping


Action = Any


@runtime_checkable
class EvaluationPolicy(Protocol):
    """A resettable policy consumed by the synchronous experiment runner."""

    def reset(self, seed: int) -> None:
        """Start one evaluation episode with policy-local randomness."""

    def act(
        self,
        observation: np.ndarray,
        info: Mapping[str, Any],
        *,
        deterministic: bool,
    ) -> Action:
        """Return one action for the server-issued decision context."""


def _strict_seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("policy seed must be an integer")
    seed = int(seed)
    if seed < 0:
        raise ValueError("policy seed must be non-negative")
    return seed


def _action_mask(info: Mapping[str, Any]) -> np.ndarray:
    if "action_mask" not in info:
        raise ValueError("policy info does not contain action_mask")
    mask = np.asarray(info["action_mask"])
    if mask.ndim != 2 or mask.shape[1] != 3:
        raise ValueError("action_mask must have shape (action_dimensions, 3)")
    if not np.all((mask == 0) | (mask == 1)):
        raise ValueError("action_mask must be binary")
    if np.any(mask.sum(axis=1) == 0):
        raise ValueError("every action dimension must have a legal action")
    return mask.astype(np.bool_, copy=False)


@dataclass
class RandomMaskedPolicy:
    """Uniformly sample legal directional actions with optional sparsity.

    ``change_probability`` is applied per action dimension.  A dimension that is
    not selected holds (code 1); if hold is illegal, it falls back to a uniformly
    sampled legal code.  ``max_changes`` caps optional changes (forced non-hold
    dimensions are always legal) and prevents a high-dimensional policy space
    from turning the random baseline into an unrealistic all-lever shock.

    The baseline remains stochastic even when the experiment asks learned models
    for deterministic predictions.  Its randomness is isolated by ``reset(seed)``.
    """

    change_probability: float = 0.25
    max_changes: int | None = 2
    _rng: np.random.Generator = field(
        init=False, repr=False, default_factory=np.random.default_rng,
    )

    def __post_init__(self) -> None:
        probability = self.change_probability
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) \
                or not math.isfinite(float(probability)):
            raise ValueError("change_probability must be a finite number")
        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError("change_probability must be between zero and one")
        self.change_probability = float(probability)
        if self.max_changes is not None:
            if isinstance(self.max_changes, bool) or not isinstance(self.max_changes, int):
                raise TypeError("max_changes must be an integer or None")
            if self.max_changes < 0:
                raise ValueError("max_changes must be non-negative")

    def reset(self, seed: int) -> None:
        self._rng = np.random.default_rng(_strict_seed(seed))

    def act(
        self,
        observation: np.ndarray,
        info: Mapping[str, Any],
        *,
        deterministic: bool,
    ) -> np.ndarray:
        del observation, deterministic
        mask = _action_mask(info)
        action = np.ones(mask.shape[0], dtype=np.int64)
        forced: list[int] = []
        candidates: list[int] = []
        for index, legal in enumerate(mask):
            if legal[1]:
                if self._rng.random() <= self.change_probability \
                        and (legal[0] or legal[2]):
                    candidates.append(index)
            else:
                forced.append(index)
        if self.max_changes is not None and len(candidates) > self.max_changes:
            selected = self._rng.choice(
                np.asarray(candidates, dtype=np.int64),
                size=self.max_changes,
                replace=False,
            )
            candidates = [int(index) for index in selected]
        for index in (*forced, *candidates):
            legal_codes = np.flatnonzero(mask[index])
            if mask[index, 1] and len(legal_codes) > 1:
                legal_codes = legal_codes[legal_codes != 1]
            action[index] = int(self._rng.choice(legal_codes))
        return action


@dataclass(frozen=True)
class HeuristicPolicy:
    """Named deterministic baselines matching the built-in occupant semantics.

    Supported rules are ``hold``, ``inflation_targeting`` and
    ``fiscal_stabilizer``. Active rules use only released context data and pass
    through the same Coordinator validation path as learned actions.
    """

    rule_name: str = "hold"
    parameters: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rule_name not in {
            "hold", "inflation_targeting", "fiscal_stabilizer",
        }:
            raise ValueError(f"unknown heuristic rule: {self.rule_name!r}")
        normalized: dict[str, float] = {}
        for name, value in self.parameters.items():
            if not isinstance(name, str) or not name:
                raise ValueError("heuristic parameter names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError("heuristic parameters must be finite numbers")
            normalized[name] = float(value)
        object.__setattr__(self, "parameters", immutable_json_mapping(normalized))

    def reset(self, seed: int) -> None:
        _strict_seed(seed)

    @staticmethod
    def _released_value(context: Mapping[str, Any], series_id: str) -> Any:
        observation = context.get("observation", {})
        if not isinstance(observation, Mapping):
            return None
        releases = observation.get("releases", ())
        if not isinstance(releases, (list, tuple)):
            return None
        for release in releases:
            if not isinstance(release, Mapping):
                continue
            if release.get("series_id") == series_id \
                    and release.get("missing_reason") is None:
                return release.get("value")
        return None

    def act(
        self,
        observation: np.ndarray,
        info: Mapping[str, Any],
        *,
        deterministic: bool,
    ) -> Action:
        del observation, deterministic
        if self.rule_name == "hold":
            return {}
        context = info.get("context")
        if not isinstance(context, Mapping):
            raise ValueError("heuristic policy requires a serialized DecisionContext")
        if self.rule_name == "fiscal_stabilizer":
            mask = _action_mask(info)
            dimensions = tuple(info.get("action_dimensions", ()))
            try:
                index = dimensions.index(("gov_deficit_target", None))
            except ValueError:
                return {}
            unemployment = self._released_value(context, "unemployment_rate")
            inflation = self._released_value(context, "inflation")
            if unemployment is None or inflation is None:
                return np.ones(mask.shape[0], dtype=np.int64)
            unemployment_enter = self.parameters.get("unemployment_enter", 0.10)
            unemployment_exit = self.parameters.get("unemployment_exit", 0.06)
            inflation_ceiling = self.parameters.get("inflation_ceiling", 0.01)
            inflation_emergency = self.parameters.get("inflation_emergency", 0.02)
            code = 1
            if float(unemployment) > unemployment_enter \
                    and float(inflation) < inflation_ceiling and mask[index, 2]:
                code = 2
            elif (
                float(unemployment) < unemployment_exit
                or float(inflation) > inflation_emergency
            ) and mask[index, 0]:
                code = 0
            action = np.ones(mask.shape[0], dtype=np.int64)
            action[index] = code
            return action
        inflation = self._released_value(context, "inflation")
        permitted = {
            item.get("lever"): item
            for item in context.get("permitted_actions", ())
            if isinstance(item, Mapping) and isinstance(item.get("lever"), str)
        }
        rate = permitted.get("manual_policy_rate")
        if inflation is None or rate is None or not rate.get("allowed", False) \
                or rate.get("current_value") is None:
            return {}
        target = self.parameters.get("target", 0.0)
        gain = self.parameters.get("gain", 0.0001)
        value = float(rate["current_value"]) + gain * (float(inflation) - target)
        if rate.get("minimum") is not None:
            value = max(float(rate["minimum"]), value)
        if rate.get("maximum") is not None:
            value = min(float(rate["maximum"]), value)
        return {"manual_policy_rate": value}


@dataclass
class CallablePolicy:
    """Adapt a pure callable for tests, research rules, or external runtimes."""

    function: Callable[[np.ndarray, Mapping[str, Any], bool], Action]
    reset_function: Callable[[int], None] | None = None

    def __post_init__(self) -> None:
        if not callable(self.function):
            raise TypeError("policy function must be callable")
        if self.reset_function is not None and not callable(self.reset_function):
            raise TypeError("reset_function must be callable or None")

    def reset(self, seed: int) -> None:
        seed = _strict_seed(seed)
        if self.reset_function is not None:
            self.reset_function(seed)

    def act(
        self,
        observation: np.ndarray,
        info: Mapping[str, Any],
        *,
        deterministic: bool,
    ) -> Action:
        return self.function(observation, info, deterministic)


@dataclass
class PredictModelPolicy:
    """Adapt a saved model exposing a conventional ``predict`` method.

    Native SMDP models can declare ``predict(observation, action_mask=...,
    deterministic=...)``.  SB3-style models without ``action_mask`` are also
    accepted, though formal benchmark runs should use a mask-aware model.  Tuple
    returns such as ``(action, recurrent_state)`` are unwrapped automatically.
    """

    model: Any
    require_action_mask: bool = True
    seed_hook: Callable[[Any, int], None] | None = None
    _accepts_action_mask: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        predict = getattr(self.model, "predict", None)
        if not callable(predict):
            raise TypeError("model must expose a callable predict method")
        try:
            signature = inspect.signature(predict)
        except (TypeError, ValueError):
            accepts_mask = False
        else:
            accepts_mask = "action_mask" in signature.parameters or any(
                item.kind is inspect.Parameter.VAR_KEYWORD
                for item in signature.parameters.values()
            )
        self._accepts_action_mask = accepts_mask
        if self.require_action_mask and not accepts_mask:
            raise TypeError(
                "model.predict must accept action_mask for policy-safe evaluation"
            )

    def reset(self, seed: int) -> None:
        seed = _strict_seed(seed)
        if self.seed_hook is not None:
            self.seed_hook(self.model, seed)
            return
        reset_state = getattr(self.model, "reset_policy_state", None)
        if callable(reset_state):
            reset_state(seed=seed)
            return
        reseed = getattr(self.model, "reseed", None)
        if callable(reseed):
            reseed(seed)

    def act(
        self,
        observation: np.ndarray,
        info: Mapping[str, Any],
        *,
        deterministic: bool,
    ) -> Action:
        context_codec = getattr(self.model, "context_codec", None)
        action_codec = getattr(self.model, "action_codec", None)
        if context_codec is not None and info.get("context_contract_hash") \
                != getattr(context_codec, "contract_hash", None):
            raise ValueError("model/environment context contract hash differs")
        if action_codec is not None and info.get("action_contract_hash") \
                != getattr(action_codec, "contract_hash", None):
            raise ValueError("model/environment action contract hash differs")
        kwargs: dict[str, Any] = {"deterministic": deterministic}
        if self._accepts_action_mask:
            kwargs["action_mask"] = _action_mask(info)
        result = self.model.predict(observation, **kwargs)
        action = result[0] if isinstance(result, tuple) else result
        array = np.asarray(action)
        dimensions = len(info.get("action_dimensions", ()))
        if dimensions and array.shape == (1, dimensions):
            return array[0]
        return action
