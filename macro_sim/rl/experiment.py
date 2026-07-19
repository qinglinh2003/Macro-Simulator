"""Reproducible, paired policy evaluation over semi-Markov controller envs.

The environment builder is intentionally injected.  Choosing a country config,
observation release table, mandate, horizon, and controlled seat is part of an
experiment definition rather than a safe library default.  A factory receives an
environment seed and must construct a fresh ``ControllerEnv``-compatible object;
the evaluator then reuses that expensive genesis across policies via ``reset``.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

from macro_sim.controllers.protocol import immutable_json_mapping

from .baselines import EvaluationPolicy
from .metrics import (
    BenchmarkVerdict,
    MetricSummary,
    SuperiorityRule,
    judge_against_baselines,
    summarize_metric,
)


@runtime_checkable
class EvaluationEnvironment(Protocol):
    """The subset of Gymnasium used by evaluation and the sync batch."""

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, Mapping[str, Any]]: ...

    def step(
        self, action: Any,
    ) -> tuple[np.ndarray, float, bool, bool, Mapping[str, Any]]: ...


@runtime_checkable
class EnvironmentFactory(Protocol):
    """Construct a fresh, seed-specific environment genesis."""

    def __call__(self, seed: int) -> EvaluationEnvironment: ...


@dataclass(frozen=True)
class CallableEnvironmentFactory:
    """Give a named callable an explicit environment-factory role."""

    builder: Callable[[int], EvaluationEnvironment]

    def __post_init__(self) -> None:
        if not callable(self.builder):
            raise TypeError("environment builder must be callable")

    def __call__(self, seed: int) -> EvaluationEnvironment:
        return self.builder(_strict_seed("environment seed", seed))


def _strict_seed(name: str, seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    seed = int(seed)
    if seed < 0:
        raise ValueError(f"{name} must be non-negative")
    return seed


def _seed_tuple(name: str, seeds: Sequence[int], *, allow_empty: bool) -> tuple[int, ...]:
    result = tuple(_strict_seed(name, seed) for seed in seeds)
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


@dataclass(frozen=True)
class ExperimentSeeds:
    """Disjoint simulator seeds for fitting and honest out-of-sample evaluation."""

    training: tuple[int, ...]
    evaluation: tuple[int, ...]
    policy_seed_salt: int = 0

    def __post_init__(self) -> None:
        training = _seed_tuple("training seeds", self.training, allow_empty=True)
        evaluation = _seed_tuple("evaluation seeds", self.evaluation, allow_empty=False)
        if set(training) & set(evaluation):
            raise ValueError("training and evaluation seeds must be disjoint")
        object.__setattr__(self, "training", training)
        object.__setattr__(self, "evaluation", evaluation)
        object.__setattr__(
            self,
            "policy_seed_salt",
            _strict_seed("policy_seed_salt", self.policy_seed_salt),
        )

    @classmethod
    def generate(
        cls,
        root_seed: int,
        *,
        training_count: int,
        evaluation_count: int,
        policy_seed_salt: int | None = None,
    ) -> "ExperimentSeeds":
        root_seed = _strict_seed("root seed", root_seed)
        for name, count in (
            ("training_count", training_count),
            ("evaluation_count", evaluation_count),
        ):
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError(f"{name} must be an integer")
            if count < (1 if name == "evaluation_count" else 0):
                raise ValueError(
                    f"{name} must be >= {1 if name == 'evaluation_count' else 0}"
                )
        total = training_count + evaluation_count
        children = np.random.SeedSequence(root_seed).spawn(total)
        generated: list[int] = []
        used: set[int] = set()
        for child in children:
            # Configs throughout the engine accept ordinary non-negative Python
            # integers.  Probe on the vanishingly unlikely uint32 collision so the
            # disjointness invariant remains deterministic rather than probabilistic.
            value = int(child.generate_state(1, dtype=np.uint32)[0])
            while value in used:
                value = (value + 1) % (2 ** 32)
            used.add(value)
            generated.append(value)
        salt = root_seed if policy_seed_salt is None else policy_seed_salt
        return cls(
            training=tuple(generated[:training_count]),
            evaluation=tuple(generated[training_count:]),
            policy_seed_salt=salt,
        )

    def policy_seed(self, environment_seed: int, policy_name: str) -> int:
        """Derive policy-local randomness without consuming simulator RNG."""
        environment_seed = _strict_seed("environment seed", environment_seed)
        if not isinstance(policy_name, str) or not policy_name:
            raise ValueError("policy_name must be a non-empty string")
        digest = hashlib.blake2b(
            (
                f"macro-sim-policy-seed-v1:{self.policy_seed_salt}:"
                f"{environment_seed}:{policy_name}"
            ).encode("utf-8"),
            digest_size=8,
        ).digest()
        return int.from_bytes(digest, "big") & ((1 << 63) - 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation": list(self.evaluation),
            "policy_seed_salt": self.policy_seed_salt,
            "training": list(self.training),
        }


@dataclass(frozen=True)
class EvaluationPlan:
    seeds: ExperimentSeeds
    gamma_per_tick: float = 1.0
    deterministic_models: bool = True
    max_decisions: int = 10_000
    confidence_level: float = 0.95
    bootstrap_resamples: int = 10_000
    bootstrap_seed: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.seeds, ExperimentSeeds):
            raise TypeError("seeds must be an ExperimentSeeds instance")
        gamma = self.gamma_per_tick
        if isinstance(gamma, bool) or not isinstance(gamma, (int, float)) \
                or not math.isfinite(float(gamma)) or not 0.0 < float(gamma) <= 1.0:
            raise ValueError("gamma_per_tick must be finite and in (0, 1]")
        object.__setattr__(self, "gamma_per_tick", float(gamma))
        if isinstance(self.deterministic_models, np.bool_):
            object.__setattr__(
                self, "deterministic_models", bool(self.deterministic_models),
            )
        elif not isinstance(self.deterministic_models, bool):
            raise TypeError("deterministic_models must be boolean")
        if isinstance(self.max_decisions, bool) or not isinstance(self.max_decisions, int):
            raise TypeError("max_decisions must be an integer")
        if self.max_decisions < 1:
            raise ValueError("max_decisions must be positive")
        if isinstance(self.confidence_level, bool) or not isinstance(
            self.confidence_level, (int, float),
        ) or not math.isfinite(float(self.confidence_level)) \
                or not 0.0 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")
        if isinstance(self.bootstrap_resamples, bool) \
                or not isinstance(self.bootstrap_resamples, int):
            raise TypeError("bootstrap_resamples must be an integer")
        if self.bootstrap_resamples < 100:
            raise ValueError("bootstrap_resamples must be at least 100")
        object.__setattr__(
            self,
            "bootstrap_seed",
            _strict_seed("bootstrap_seed", self.bootstrap_seed),
        )


@dataclass(frozen=True)
class EpisodeResult:
    policy_name: str
    environment_seed: int
    policy_seed: int
    total_reward: float
    discounted_return: float
    reward_per_tick: float
    decision_steps: int
    elapsed_ticks: int
    terminated: bool
    truncated: bool
    decision_status_counts: Mapping[str, int] = field(default_factory=dict)
    objective_profile: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_name, str) or not self.policy_name:
            raise ValueError("policy_name must be a non-empty string")
        object.__setattr__(
            self,
            "environment_seed",
            _strict_seed("environment_seed", self.environment_seed),
        )
        object.__setattr__(
            self, "policy_seed", _strict_seed("policy_seed", self.policy_seed),
        )
        for name in ("total_reward", "discounted_return", "reward_per_tick"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        for name in ("decision_steps", "elapsed_ticks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("terminated", "truncated"):
            value = getattr(self, name)
            if isinstance(value, np.bool_):
                object.__setattr__(self, name, bool(value))
            elif not isinstance(value, bool):
                raise TypeError(f"{name} must be boolean")
        if not self.terminated and not self.truncated:
            raise ValueError("a published episode result must be complete")
        if self.objective_profile is not None and (
            not isinstance(self.objective_profile, str) or not self.objective_profile
        ):
            raise ValueError("objective_profile must be a non-empty string or None")
        normalized: dict[str, int] = {}
        for status, count in self.decision_status_counts.items():
            if not isinstance(status, str) or not status:
                raise ValueError("decision status names must be non-empty strings")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("decision status counts must be non-negative integers")
            normalized[status] = count
        object.__setattr__(
            self,
            "decision_status_counts",
            immutable_json_mapping(dict(sorted(normalized.items()))),
        )

    def metric(self, name: str) -> float:
        if name not in {"total_reward", "discounted_return", "reward_per_tick"}:
            raise ValueError(f"unknown episode metric: {name!r}")
        return float(getattr(self, name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_status_counts": dict(self.decision_status_counts),
            "decision_steps": self.decision_steps,
            "discounted_return": self.discounted_return,
            "elapsed_ticks": self.elapsed_ticks,
            "environment_seed": self.environment_seed,
            "objective_profile": self.objective_profile,
            "policy_name": self.policy_name,
            "policy_seed": self.policy_seed,
            "reward_per_tick": self.reward_per_tick,
            "terminated": self.terminated,
            "total_reward": self.total_reward,
            "truncated": self.truncated,
        }


class EpisodeLimitExceeded(RuntimeError):
    """Raised instead of publishing a silently censored benchmark episode."""


def aggregate_interval_reward(
    reward: float,
    elapsed_ticks: int,
    info: Mapping[str, Any],
) -> float:
    """Convert an environment scalar into one SMDP interval reward.

    A ``per_tick`` objective reports the interval mean so humans can compare
    unequal decision intervals. PPO/evaluation instead need the interval sum;
    multiplying by duration makes an undiscounted trajectory invariant to how
    often decision boundaries happened to open. ``sum`` and legacy environments
    already report an interval aggregate.
    """
    normalization = info.get("reward_time_normalization", "sum")
    if normalization not in {"per_tick", "sum"}:
        raise ValueError("unknown reward_time_normalization in environment info")
    return float(reward) * elapsed_ticks if normalization == "per_tick" else float(reward)


def run_episode(
    environment: EvaluationEnvironment,
    policy: EvaluationPolicy,
    *,
    policy_name: str,
    environment_seed: int,
    policy_seed: int,
    gamma_per_tick: float = 1.0,
    deterministic: bool = True,
    max_decisions: int = 10_000,
) -> EpisodeResult:
    """Run one complete SMDP episode and use ``gamma ** elapsed_ticks``."""

    if not isinstance(policy_name, str) or not policy_name:
        raise ValueError("policy_name must be a non-empty string")
    environment_seed = _strict_seed("environment_seed", environment_seed)
    policy_seed = _strict_seed("policy_seed", policy_seed)
    if isinstance(gamma_per_tick, bool) or not isinstance(gamma_per_tick, (int, float)) \
            or not math.isfinite(float(gamma_per_tick)) \
            or not 0.0 < float(gamma_per_tick) <= 1.0:
        raise ValueError("gamma_per_tick must be in (0, 1]")
    if isinstance(max_decisions, bool) or not isinstance(max_decisions, int) \
            or max_decisions < 1:
        raise ValueError("max_decisions must be a positive integer")

    observation, info = environment.reset(seed=environment_seed)
    policy.reset(policy_seed)
    rewards: list[float] = []
    discounted_rewards: list[float] = []
    weighted_rewards: list[float] = []
    elapsed_total = 0
    discount = 1.0
    statuses: Counter[str] = Counter()
    objective_profile = info.get("objective_profile")
    for decision_step in range(1, max_decisions + 1):
        action = policy.act(
            np.asarray(observation), info, deterministic=deterministic,
        )
        observation, reward, terminated, truncated, info = environment.step(action)
        if isinstance(reward, bool) or not isinstance(reward, (int, float, np.number)) \
                or not math.isfinite(float(reward)):
            raise ValueError("environment reward must be finite")
        elapsed = info.get("elapsed_ticks")
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, np.integer)) \
                or int(elapsed) < 1:
            raise ValueError("environment info.elapsed_ticks must be a positive integer")
        elapsed = int(elapsed)
        reward = float(reward)
        interval_reward = aggregate_interval_reward(reward, elapsed, info)
        rewards.append(interval_reward)
        discounted_rewards.append(discount * interval_reward)
        weighted_rewards.append(
            interval_reward
            if "reward_time_normalization" in info
            else reward * elapsed
        )
        elapsed_total += elapsed
        discount *= float(gamma_per_tick) ** elapsed
        current_profile = info.get("objective_profile", objective_profile)
        if objective_profile is None:
            objective_profile = current_profile
        elif current_profile is not None and current_profile != objective_profile:
            raise ValueError("objective_profile changed during an episode")
        decisions = info.get("decisions", ())
        if isinstance(decisions, (list, tuple)):
            for decision in decisions:
                if isinstance(decision, Mapping) and isinstance(decision.get("status"), str):
                    statuses[decision["status"]] += 1
        if bool(terminated) or bool(truncated):
            return EpisodeResult(
                policy_name=policy_name,
                environment_seed=environment_seed,
                policy_seed=policy_seed,
                total_reward=math.fsum(rewards),
                discounted_return=math.fsum(discounted_rewards),
                reward_per_tick=math.fsum(weighted_rewards) / elapsed_total,
                decision_steps=decision_step,
                elapsed_ticks=elapsed_total,
                terminated=bool(terminated),
                truncated=bool(truncated),
                decision_status_counts=dict(statuses),
                objective_profile=objective_profile,
            )
    raise EpisodeLimitExceeded(
        f"policy {policy_name!r}, environment seed {environment_seed} did not "
        f"finish within {max_decisions} decisions"
    )


def _derived_stat_seed(base_seed: int, label: str) -> int:
    digest = hashlib.blake2b(
        f"macro-sim-stat-seed-v1:{base_seed}:{label}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


@dataclass(frozen=True)
class ExperimentResult:
    plan: EvaluationPlan
    policy_names: tuple[str, ...]
    episodes: tuple[EpisodeResult, ...]

    def __post_init__(self) -> None:
        names = tuple(self.policy_names)
        if not names or len(names) != len(set(names)):
            raise ValueError("policy_names must be non-empty and unique")
        expected = {
            (name, seed)
            for name in names
            for seed in self.plan.seeds.evaluation
        }
        actual = {(item.policy_name, item.environment_seed) for item in self.episodes}
        if actual != expected or len(actual) != len(self.episodes):
            raise ValueError("episodes do not form a complete policy/evaluation-seed matrix")
        for item in self.episodes:
            expected_policy_seed = self.plan.seeds.policy_seed(
                item.environment_seed, item.policy_name,
            )
            if item.policy_seed != expected_policy_seed:
                raise ValueError("episode policy seed does not match the experiment seed plan")
        for environment_seed in self.plan.seeds.evaluation:
            profiles = {
                item.objective_profile
                for item in self.episodes
                if item.environment_seed == environment_seed
            }
            if len(profiles) != 1:
                raise ValueError(
                    "paired policies must use the same objective profile per seed"
                )
        object.__setattr__(self, "policy_names", names)
        object.__setattr__(self, "episodes", tuple(self.episodes))

    def episodes_for(self, policy_name: str) -> tuple[EpisodeResult, ...]:
        if policy_name not in self.policy_names:
            raise KeyError(policy_name)
        by_seed = {
            item.environment_seed: item
            for item in self.episodes
            if item.policy_name == policy_name
        }
        return tuple(by_seed[seed] for seed in self.plan.seeds.evaluation)

    def scores(self, policy_name: str, metric: str) -> dict[int, float]:
        return {
            item.environment_seed: item.metric(metric)
            for item in self.episodes_for(policy_name)
        }

    def summary(self, policy_name: str, metric: str) -> MetricSummary:
        return summarize_metric(
            tuple(self.scores(policy_name, metric).values()),
            confidence_level=self.plan.confidence_level,
            resamples=self.plan.bootstrap_resamples,
            seed=_derived_stat_seed(
                self.plan.bootstrap_seed, f"summary:{policy_name}:{metric}",
            ),
        )

    def judge(
        self,
        candidate: str,
        baselines: Sequence[str],
        *,
        metric: str = "discounted_return",
        rule: SuperiorityRule | None = None,
    ) -> BenchmarkVerdict:
        if candidate not in self.policy_names:
            raise KeyError(candidate)
        baseline_names = tuple(baselines)
        if not baseline_names or len(baseline_names) != len(set(baseline_names)):
            raise ValueError("baselines must be non-empty and unique")
        if candidate in baseline_names:
            raise ValueError("candidate cannot also be a baseline")
        for baseline in baseline_names:
            if baseline not in self.policy_names:
                raise KeyError(baseline)
        rule = rule or SuperiorityRule()
        return judge_against_baselines(
            self.scores(candidate, metric),
            {name: self.scores(name, metric) for name in baseline_names},
            candidate_name=candidate,
            metric=metric,
            rule=rule,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "episodes": [item.to_dict() for item in self.episodes],
            "plan": {
                "bootstrap_resamples": self.plan.bootstrap_resamples,
                "bootstrap_seed": self.plan.bootstrap_seed,
                "confidence_level": self.plan.confidence_level,
                "deterministic_models": self.plan.deterministic_models,
                "gamma_per_tick": self.plan.gamma_per_tick,
                "max_decisions": self.plan.max_decisions,
                "seeds": self.plan.seeds.to_dict(),
            },
            "policy_names": list(self.policy_names),
        }


def evaluate_policies(
    environment_factory: EnvironmentFactory,
    policies: Mapping[str, EvaluationPolicy],
    plan: EvaluationPlan,
) -> ExperimentResult:
    """Evaluate a complete paired matrix with one expensive genesis per seed.

    The loop is ordered by environment seed, then policy.  ``ControllerEnv.reset``
    restores its serialized genesis between policies, so random, heuristic, and
    model policies see common simulator randomness without reconstructing the
    world for every comparison.  Policy randomness is independently derived and
    never touches the simulator RNG stream.
    """

    if not callable(environment_factory):
        raise TypeError("environment_factory must be callable")
    if not isinstance(plan, EvaluationPlan):
        raise TypeError("plan must be an EvaluationPlan")
    normalized: dict[str, EvaluationPolicy] = {}
    for name, policy in policies.items():
        if not isinstance(name, str) or not name:
            raise ValueError("policy names must be non-empty strings")
        if not isinstance(policy, EvaluationPolicy):
            raise TypeError(f"policy {name!r} does not implement EvaluationPolicy")
        normalized[name] = policy
    if not normalized:
        raise ValueError("at least one policy is required")
    names = tuple(sorted(normalized))
    episodes: list[EpisodeResult] = []
    for environment_seed in plan.seeds.evaluation:
        environment = environment_factory(environment_seed)
        if not isinstance(environment, EvaluationEnvironment):
            close = getattr(environment, "close", None)
            if callable(close):
                close()
            raise TypeError("environment factory returned an incompatible object")
        try:
            for name in names:
                policy_seed = plan.seeds.policy_seed(environment_seed, name)
                episodes.append(run_episode(
                    environment,
                    normalized[name],
                    policy_name=name,
                    environment_seed=environment_seed,
                    policy_seed=policy_seed,
                    gamma_per_tick=plan.gamma_per_tick,
                    deterministic=plan.deterministic_models,
                    max_decisions=plan.max_decisions,
                ))
        finally:
            close = getattr(environment, "close", None)
            if callable(close):
                close()
    return ExperimentResult(plan, names, tuple(episodes))


@dataclass(frozen=True)
class BatchReset:
    observations: np.ndarray
    action_masks: np.ndarray
    infos: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class BatchStep:
    observations: np.ndarray
    action_masks: np.ndarray
    rewards: np.ndarray
    elapsed_ticks: np.ndarray
    terminated: np.ndarray
    truncated: np.ndarray
    infos: tuple[Mapping[str, Any], ...]


class SynchronousEnvironmentBatch:
    """Small, allocation-conscious synchronous interface for a trainer thread.

    Environments are constructed once, arrays are stacked on the leading batch
    dimension, and no worker IPC or implicit auto-reset is performed.  A trainer
    can therefore choose its own rollout and seed-rotation policy.  Once any slot
    ends, call ``reset`` before the next synchronized step.
    """

    def __init__(self, factory: EnvironmentFactory, seeds: Sequence[int]):
        if not callable(factory):
            raise TypeError("environment factory must be callable")
        self.seeds = _seed_tuple("batch seeds", seeds, allow_empty=False)
        built: list[EvaluationEnvironment] = []
        try:
            for seed in self.seeds:
                built.append(factory(seed))
        except Exception:
            for environment in built:
                close = getattr(environment, "close", None)
                if callable(close):
                    close()
            raise
        self._environments = tuple(built)
        if not all(isinstance(env, EvaluationEnvironment) for env in self._environments):
            self.close()
            raise TypeError("environment factory returned an incompatible object")
        self._ready = False
        self._ended = False
        self._closed = False

    @property
    def num_envs(self) -> int:
        return len(self._environments)

    @staticmethod
    def _stack(observations: Sequence[Any]) -> np.ndarray:
        try:
            return np.stack(
                [np.asarray(item) for item in observations], axis=0,
            )
        except ValueError as exc:
            raise ValueError(
                "synchronous environments must expose homogeneous observations"
            ) from exc

    @staticmethod
    def _stack_action_masks(infos: Sequence[Mapping[str, Any]]) -> np.ndarray:
        masks: list[np.ndarray] = []
        for info in infos:
            if "action_mask" not in info:
                raise ValueError("environment info does not contain action_mask")
            mask = np.asarray(info["action_mask"])
            if mask.ndim != 2 or mask.shape[1] != 3 \
                    or mask.dtype.kind not in "biu" \
                    or np.any((mask != 0) & (mask != 1)) \
                    or np.any(~mask.astype(np.bool_).any(axis=1)):
                raise ValueError(
                    "environment action_mask must be legal binary [dimensions, 3]"
                )
            masks.append(mask.astype(np.bool_, copy=False))
        try:
            return np.stack(masks, axis=0)
        except ValueError as exc:
            raise ValueError(
                "synchronous environments must expose homogeneous action masks"
            ) from exc

    def reset(self) -> BatchReset:
        if self._closed:
            raise RuntimeError("synchronous environment batch is closed")
        self._ready = False
        observations: list[Any] = []
        infos: list[Mapping[str, Any]] = []
        try:
            for environment, seed in zip(self._environments, self.seeds, strict=True):
                observation, info = environment.reset(seed=seed)
                observations.append(observation)
                infos.append(info)
            stacked = self._stack(observations)
            masks = self._stack_action_masks(infos)
        except Exception:
            self._ended = True
            raise
        self._ready = True
        self._ended = False
        return BatchReset(stacked, masks, tuple(infos))

    def step(self, actions: Sequence[Any]) -> BatchStep:
        if not self._ready:
            raise RuntimeError("reset() must be called before step()")
        if self._ended:
            raise RuntimeError("a batch slot ended; reset() before the next step")
        if len(actions) != self.num_envs:
            raise ValueError("actions length must equal num_envs")
        observations: list[Any] = []
        rewards = np.empty(self.num_envs, dtype=np.float64)
        elapsed_ticks = np.empty(self.num_envs, dtype=np.int64)
        terminated = np.empty(self.num_envs, dtype=np.bool_)
        truncated = np.empty(self.num_envs, dtype=np.bool_)
        infos: list[Mapping[str, Any]] = []
        try:
            for index, (environment, action) in enumerate(
                zip(self._environments, actions, strict=True)
            ):
                observation, reward, term, trunc, info = environment.step(action)
                if isinstance(reward, bool) or not isinstance(
                    reward, (int, float, np.number),
                ) or not math.isfinite(float(reward)):
                    raise ValueError("environment reward must be finite")
                observations.append(observation)
                rewards[index] = float(reward)
                elapsed = info.get("elapsed_ticks")
                if isinstance(elapsed, bool) or not isinstance(
                    elapsed, (int, np.integer),
                ) or int(elapsed) < 1:
                    raise ValueError(
                        "environment info.elapsed_ticks must be a positive integer"
                    )
                elapsed_ticks[index] = int(elapsed)
                terminated[index] = bool(term)
                truncated[index] = bool(trunc)
                infos.append(info)
            stacked = self._stack(observations)
            masks = self._stack_action_masks(infos)
        except Exception:
            # A synchronous step cannot roll back already-advanced slots.  Force
            # an explicit all-slot reset instead of letting a trainer continue
            # with a partially advanced batch.
            self._ready = False
            self._ended = True
            raise
        self._ended = bool(np.any(terminated | truncated))
        return BatchStep(
            stacked,
            masks,
            rewards,
            elapsed_ticks,
            terminated,
            truncated,
            tuple(infos),
        )

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        for environment in getattr(self, "_environments", ()):
            close = getattr(environment, "close", None)
            if callable(close):
                close()
        self._ready = False
        self._closed = True

    def __enter__(self) -> "SynchronousEnvironmentBatch":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
