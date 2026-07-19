"""End-to-end SMDP PPO training orchestration and portable model export."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Integral, Real
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

import numpy as np

from macro_sim.controllers.protocol import canonical_json, canonical_value

from .algorithm import PPOConfig, SMDPPPO, require_torch
from .artifact import save_artifact
from .buffer import SMDPRolloutBuffer
from .experiment import (
    EnvironmentFactory,
    SynchronousEnvironmentBatch,
    aggregate_interval_reward,
)
from .model import NumpyMLPPolicy, SUPPORTED_ACTIVATIONS
from .vector_env import SubprocessEnvironmentBatch


TRAINING_CHECKPOINT_SCHEMA_VERSION = 2


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _seed(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if not 0 <= result < 2**63:
        raise ValueError(f"{name} must be in [0, 2**63)")
    return result


def _finite(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Runtime-independent orchestration settings for PPO training."""

    updates: int = 50
    rollout_steps: int = 49
    num_envs: int = 4
    seed: int = 42
    environment_seed_start: int = 10_000
    parallel: bool = True
    start_method: str = "spawn"
    worker_timeout_seconds: float = 300.0
    device: str = "cpu"
    observation_clip: float = 10.0
    reward_scale: float = 0.01
    checkpoint_interval: int = 5
    output_dir: str = "runs/fiscal_stabilization_v1"

    def __post_init__(self) -> None:
        for name in ("updates", "rollout_steps", "num_envs", "checkpoint_interval"):
            object.__setattr__(self, name, _positive_int(name, getattr(self, name)))
        object.__setattr__(self, "seed", _seed("seed", self.seed))
        object.__setattr__(
            self,
            "environment_seed_start",
            _seed("environment_seed_start", self.environment_seed_start),
        )
        if not isinstance(self.parallel, bool):
            raise TypeError("parallel must be a boolean")
        if not isinstance(self.start_method, str) or not self.start_method:
            raise ValueError("start_method must be a non-empty string")
        object.__setattr__(
            self,
            "worker_timeout_seconds",
            _finite(
                "worker_timeout_seconds", self.worker_timeout_seconds, positive=True,
            ),
        )
        if self.device not in {"auto", "cpu", "mps"}:
            raise ValueError("device must be 'auto', 'cpu', or 'mps'")
        object.__setattr__(
            self,
            "observation_clip",
            _finite("observation_clip", self.observation_clip, positive=True),
        )
        object.__setattr__(
            self,
            "reward_scale",
            _finite("reward_scale", self.reward_scale, positive=True),
        )
        if not isinstance(self.output_dir, str) or not self.output_dir.strip():
            raise ValueError("output_dir must be a non-empty path")

    @property
    def samples_per_update(self) -> int:
        return self.rollout_steps * self.num_envs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunningObservationNormalizer:
    """Numerically stable Welford statistics with a frozen export contract."""

    def __init__(self, dimension: int, *, epsilon: float = 1.0e-6) -> None:
        self.dimension = _positive_int("dimension", dimension)
        self.epsilon = _finite("epsilon", epsilon, positive=True)
        self.count = 0
        self.mean = np.zeros(self.dimension, dtype=np.float64)
        self.m2 = np.zeros(self.dimension, dtype=np.float64)

    def update(self, observations: Any) -> None:
        array = np.asarray(observations)
        if array.ndim == 1:
            array = array[None, :]
        if array.ndim != 2 or array.shape[1] != self.dimension:
            raise ValueError(
                f"observations must have shape [batch, {self.dimension}]"
            )
        if array.dtype.kind not in "iuf" or not np.all(np.isfinite(array)):
            raise ValueError("observations must contain finite real values")
        batch = array.astype(np.float64, copy=False)
        batch_count = batch.shape[0]
        if batch_count == 0:
            return
        batch_mean = batch.mean(axis=0)
        centered = batch - batch_mean
        batch_m2 = np.sum(centered * centered, axis=0)
        if self.count == 0:
            self.count = batch_count
            self.mean[:] = batch_mean
            self.m2[:] = batch_m2
            return
        total = self.count + batch_count
        delta = batch_mean - self.mean
        self.mean += delta * (batch_count / total)
        self.m2 += batch_m2 + delta * delta * (
            self.count * batch_count / total
        )
        self.count = total

    @property
    def scale(self) -> np.ndarray:
        if self.count < 2:
            return np.ones(self.dimension, dtype=np.float64)
        variance = self.m2 / self.count
        return np.sqrt(np.maximum(variance, self.epsilon))

    def normalize(self, observations: Any, *, clip: float) -> np.ndarray:
        array = np.asarray(observations, dtype=np.float64)
        if array.shape[-1:] != (self.dimension,) or not np.all(np.isfinite(array)):
            raise ValueError("observations do not match normalization contract")
        result = (array - self.mean) / self.scale
        return np.clip(result, -clip, clip).astype(np.float32, copy=False)

    def state_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "dimension": self.dimension,
            "epsilon": self.epsilon,
            "m2": self.m2.tolist(),
            "mean": self.mean.tolist(),
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        expected = {"count", "dimension", "epsilon", "m2", "mean"}
        if not isinstance(state, Mapping) or set(state) != expected:
            raise ValueError("normalizer state has missing or unknown fields")
        if state["dimension"] != self.dimension or state["epsilon"] != self.epsilon:
            raise ValueError("normalizer state contract does not match trainer")
        count = state["count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("normalizer count must be a non-negative integer")
        mean = np.asarray(state["mean"], dtype=np.float64)
        m2 = np.asarray(state["m2"], dtype=np.float64)
        if mean.shape != (self.dimension,) or m2.shape != (self.dimension,) \
                or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(m2)) \
                or np.any(m2 < 0.0):
            raise ValueError("normalizer arrays are invalid")
        self.count = count
        self.mean[:] = mean
        self.m2[:] = m2


@dataclass(frozen=True, slots=True)
class TrainingResult:
    artifact_path: Path
    checkpoint_path: Path
    metrics_path: Path
    updates: int
    samples: int
    simulation_ticks: int
    wall_time_seconds: float
    device: str


class RLTrainer:
    """Collect rollouts, optimize PPO, checkpoint, and export engine policy."""

    def __init__(
        self,
        environment_factory: EnvironmentFactory,
        config: TrainingConfig,
        *,
        ppo_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        require_torch()
        if not callable(environment_factory):
            raise TypeError("environment_factory must be callable")
        if not isinstance(config, TrainingConfig):
            raise TypeError("config must be a TrainingConfig")
        overrides = {} if ppo_overrides is None else dict(ppo_overrides)
        forbidden = {"observation_dim", "action_dims", "seed", "device"} & set(overrides)
        if forbidden:
            raise ValueError(
                f"PPO dimensions/seed/device are trainer-owned: {sorted(forbidden)}"
            )
        self.environment_factory = environment_factory
        self.config = config
        raw_contract = getattr(environment_factory, "environment_contract", None)
        if callable(raw_contract):
            raw_contract = raw_contract()
        if not isinstance(raw_contract, Mapping):
            raise ValueError(
                "training environment factories must expose a versioned "
                "environment_contract mapping"
            )
        normalized_contract = canonical_value(dict(raw_contract))
        if not isinstance(normalized_contract, dict) \
                or not isinstance(normalized_contract.get("schema_version"), int) \
                or not isinstance(normalized_contract.get("task_id"), str):
            raise ValueError(
                "environment_contract requires integer schema_version and string task_id"
            )
        self.environment_contract = normalized_contract
        self.environment_contract_hash = hashlib.sha256(
            canonical_json(normalized_contract).encode("utf-8")
        ).hexdigest()
        episode_decisions = normalized_contract.get("episode_decisions")
        if isinstance(episode_decisions, bool) or not isinstance(episode_decisions, int) \
                or episode_decisions <= 0:
            raise ValueError(
                "environment_contract must declare positive episode_decisions"
            )
        self.episode_decisions = episode_decisions
        if config.rollout_steps % episode_decisions != 0:
            raise ValueError(
                "rollout_steps must contain whole fixed-horizon episodes so "
                "checkpoints never discard an in-flight environment"
            )

        probe = environment_factory(config.environment_seed_start)
        try:
            observation, info = probe.reset(seed=config.environment_seed_start)
            observation_array = np.asarray(observation)
            mask = np.asarray(info.get("action_mask"))
            self.context_codec = getattr(probe, "context_codec", None)
            self.action_codec = getattr(probe, "action_codec", None)
            if self.context_codec is None or self.action_codec is None:
                raise ValueError(
                    "training environments require deployable context/action codecs"
                )
            if observation_array.shape != (self.context_codec.observation_dim,):
                raise ValueError("probe observation does not match context codec")
            if mask.shape != (self.action_codec.action_dim, 3):
                raise ValueError("probe action mask does not match action codec")
        finally:
            close = getattr(probe, "close", None)
            if callable(close):
                close()

        defaults: dict[str, Any] = {
            "observation_dim": self.context_codec.observation_dim,
            "action_dims": self.action_codec.action_dim,
            "batch_size": min(256, config.samples_per_update),
            "seed": config.seed,
            "device": config.device,
        }
        defaults.update(overrides)
        self.ppo_config = PPOConfig(**defaults)
        if self.ppo_config.activation not in SUPPORTED_ACTIVATIONS:
            raise ValueError(
                f"PPO activation {self.ppo_config.activation!r} cannot be exported; "
                f"choose one of {sorted(SUPPORTED_ACTIVATIONS)}"
            )
        self.learner = SMDPPPO(self.ppo_config)
        self.normalizer = RunningObservationNormalizer(
            self.context_codec.observation_dim,
        )
        self.completed_updates = 0
        self.total_samples = 0
        self.total_simulation_ticks = 0
        self.next_environment_seed = config.environment_seed_start

    def _take_environment_seeds(self) -> tuple[int, ...]:
        stop = self.next_environment_seed + self.config.num_envs
        if stop >= 2**63:
            raise OverflowError("training environment seed range was exhausted")
        seeds = tuple(range(self.next_environment_seed, stop))
        self.next_environment_seed = stop
        return seeds

    def _new_batch(self):
        seeds = self._take_environment_seeds()
        if self.config.parallel and self.config.num_envs > 1:
            return SubprocessEnvironmentBatch(
                self.environment_factory,
                seeds,
                start_method=self.config.start_method,
                timeout_seconds=self.config.worker_timeout_seconds,
                compact_infos=True,
            )
        return SynchronousEnvironmentBatch(self.environment_factory, seeds)

    @property
    def output_dir(self) -> Path:
        return Path(self.config.output_dir).expanduser().resolve()

    @property
    def checkpoint_path(self) -> Path:
        return self.output_dir / "checkpoint.pt"

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "metrics.jsonl"

    @property
    def artifact_path(self) -> Path:
        return self.output_dir / "policy.msrl"

    def _prepare_output(self, *, resuming: bool) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not resuming:
            conflicts = [
                path for path in (
                    self.checkpoint_path, self.metrics_path, self.artifact_path,
                )
                if path.exists()
            ]
            if conflicts:
                raise FileExistsError(
                    "refusing to overwrite an existing training run: "
                    + ", ".join(str(path) for path in conflicts)
                )

    def _reconcile_metrics_for_resume(self) -> None:
        """Atomically remove log rows newer than the loaded checkpoint."""
        if not self.metrics_path.exists():
            if self.completed_updates > 0:
                raise ValueError(
                    "resume output is missing metrics.jsonl for the loaded checkpoint"
                )
            return
        raw_lines = self.metrics_path.read_text(encoding="utf-8").splitlines()
        records: list[tuple[int, str]] = []
        for index, line in enumerate(raw_lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"metrics line {index} is invalid JSON") from exc
            update = record.get("update") if isinstance(record, Mapping) else None
            if isinstance(update, bool) or not isinstance(update, int) or update <= 0:
                raise ValueError(f"metrics line {index} has an invalid update")
            if update != len(records) + 1:
                raise ValueError("metrics updates must be unique and contiguous")
            records.append((update, line))
        if len(records) < self.completed_updates:
            raise ValueError("metrics log ends before the loaded checkpoint")
        kept = [line for update, line in records if update <= self.completed_updates]
        if len(kept) == len(raw_lines):
            return
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                prefix=f".{self.metrics_path.name}.",
                suffix=".tmp",
                dir=self.output_dir,
                encoding="utf-8",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                if kept:
                    handle.write("\n".join(kept) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.metrics_path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def _checkpoint_payload(self) -> dict[str, Any]:
        state_method = getattr(self.learner, "state_dict", None)
        if not callable(state_method):
            raise RuntimeError("SMDPPPO does not expose checkpoint state_dict()")
        return {
            "action_contract_hash": self.action_codec.contract_hash,
            "completed_updates": self.completed_updates,
            "context_contract_hash": self.context_codec.contract_hash,
            "continuation_config": self._continuation_config(),
            "environment_contract": self.environment_contract,
            "environment_contract_hash": self.environment_contract_hash,
            "learner": state_method(),
            "next_environment_seed": self.next_environment_seed,
            "normalizer": self.normalizer.state_dict(),
            "ppo_config": self.ppo_config.to_dict(),
            "schema_version": TRAINING_CHECKPOINT_SCHEMA_VERSION,
            "total_samples": self.total_samples,
            "total_simulation_ticks": self.total_simulation_ticks,
        }

    def _continuation_config(self) -> dict[str, Any]:
        """Settings that must not drift across one optimizer trajectory."""
        return {
            "environment_seed_start": self.config.environment_seed_start,
            "num_envs": self.config.num_envs,
            "observation_clip": self.config.observation_clip,
            "reward_scale": self.config.reward_scale,
            "rollout_steps": self.config.rollout_steps,
            "seed": self.config.seed,
        }

    def save_checkpoint(self) -> Path:
        import torch

        payload = self._checkpoint_payload()
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=f".{self.checkpoint_path.name}.",
                suffix=".tmp",
                dir=self.output_dir,
                delete=False,
            ) as handle:
                temporary_name = handle.name
                torch.save(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.checkpoint_path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
        return self.checkpoint_path

    def load_checkpoint(self, path: str | os.PathLike[str]) -> None:
        import torch

        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"training checkpoint does not exist: {source}")
        payload = torch.load(
            source,
            # Keep RNG byte tensors on CPU; network/Adam loaders copy numeric
            # state to the configured CPU/MPS parameters transactionally.
            map_location="cpu",
            weights_only=True,
        )
        expected = {
            "action_contract_hash", "completed_updates", "context_contract_hash",
            "continuation_config", "environment_contract",
            "environment_contract_hash", "learner", "next_environment_seed",
            "normalizer", "ppo_config", "schema_version", "total_samples",
            "total_simulation_ticks",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("checkpoint has missing or unknown fields")
        if payload["schema_version"] != TRAINING_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("unsupported training checkpoint schema")
        if payload["context_contract_hash"] != self.context_codec.contract_hash \
                or payload["action_contract_hash"] != self.action_codec.contract_hash:
            raise ValueError("checkpoint vector contract does not match trainer")
        if payload["environment_contract"] != self.environment_contract \
                or payload["environment_contract_hash"] != self.environment_contract_hash:
            raise ValueError("checkpoint environment/task contract does not match trainer")
        actual_environment_hash = hashlib.sha256(
            canonical_json(payload["environment_contract"]).encode("utf-8")
        ).hexdigest()
        if actual_environment_hash != payload["environment_contract_hash"]:
            raise ValueError("checkpoint environment contract hash is invalid")
        if payload["continuation_config"] != self._continuation_config():
            raise ValueError("checkpoint training continuation config does not match trainer")
        if payload["ppo_config"] != self.ppo_config.to_dict():
            raise ValueError("checkpoint PPO configuration does not match trainer")

        counters: dict[str, int] = {}
        for name in (
            "completed_updates", "total_samples", "total_simulation_ticks",
            "next_environment_seed",
        ):
            value = payload[name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"checkpoint {name} is invalid")
            counters[name] = value
        if counters["completed_updates"] > self.config.updates:
            raise ValueError("checkpoint is beyond the requested update count")
        if counters["total_samples"] != (
            counters["completed_updates"] * self.config.samples_per_update
        ):
            raise ValueError("checkpoint sample count is inconsistent with updates")
        if counters["total_simulation_ticks"] < counters["total_samples"]:
            raise ValueError("checkpoint simulation tick count is inconsistent")
        episodes_per_update = self.config.rollout_steps // self.episode_decisions
        expected_next_seed = self.config.environment_seed_start + (
            counters["completed_updates"]
            * episodes_per_update
            * self.config.num_envs
        )
        if expected_next_seed >= 2**63 \
                or counters["next_environment_seed"] != expected_next_seed:
            raise ValueError("checkpoint next_environment_seed is inconsistent")

        # Validate the entire outer payload before changing live trainer state.
        normalizer_probe = RunningObservationNormalizer(
            self.normalizer.dimension, epsilon=self.normalizer.epsilon,
        )
        normalizer_probe.load_state_dict(payload["normalizer"])
        previous_learner = self.learner.state_dict()
        previous_normalizer = self.normalizer.state_dict()
        previous_counters = {
            name: getattr(self, name) for name in counters
        }
        try:
            self.learner.load_state_dict(payload["learner"])
            self.normalizer.load_state_dict(payload["normalizer"])
            for name, value in counters.items():
                setattr(self, name, value)
        except Exception:
            self.learner.load_state_dict(previous_learner)
            self.normalizer.load_state_dict(previous_normalizer)
            for name, value in previous_counters.items():
                setattr(self, name, value)
            raise

    def export_policy(self) -> Path:
        policy = NumpyMLPPolicy.from_actor_critic(
            self.context_codec,
            self.action_codec,
            self.learner.network,
            input_mean=self.normalizer.mean.astype(np.float32),
            input_scale=self.normalizer.scale.astype(np.float32),
            input_clip=self.config.observation_clip,
            deterministic=True,
            seed=self.config.seed,
        )
        metadata: dict[str, Any] = {
            "completed_updates": self.completed_updates,
            "environment_contract": self.environment_contract,
            "environment_contract_hash": self.environment_contract_hash,
            "ppo_config": self.ppo_config.to_dict(),
            "total_samples": self.total_samples,
            "total_simulation_ticks": self.total_simulation_ticks,
            "training_environment_seed_range": {
                "start": self.config.environment_seed_start,
                "stop_exclusive": self.next_environment_seed,
            },
            "training_config": self.config.to_dict(),
        }
        environment_config = getattr(self.environment_factory, "config", None)
        to_dict = getattr(environment_config, "to_dict", None)
        if callable(to_dict):
            metadata["environment_config"] = to_dict()
        return save_artifact(self.artifact_path, policy, metadata=metadata)

    def train(
        self,
        *,
        resume_from: str | os.PathLike[str] | None = None,
    ) -> TrainingResult:
        resuming = resume_from is not None
        self._prepare_output(resuming=resuming)
        if resume_from is not None:
            self.load_checkpoint(resume_from)
            self._reconcile_metrics_for_resume()

        start = time.perf_counter()
        batch = None
        batch_needs_reseed = False
        raw_observations: np.ndarray | None = None
        normalized_observations: np.ndarray | None = None
        action_masks: np.ndarray | None = None
        episode_returns = np.zeros(self.config.num_envs, dtype=np.float64)
        episode_ticks = np.zeros(self.config.num_envs, dtype=np.int64)
        try:
            with self.metrics_path.open("a", encoding="utf-8") as metrics_file:
                while self.completed_updates < self.config.updates:
                    rollout = SMDPRolloutBuffer(
                        capacity=self.config.rollout_steps,
                        num_envs=self.config.num_envs,
                        observation_dim=self.context_codec.observation_dim,
                        action_dims=self.action_codec.action_dim,
                        gamma=self.ppo_config.gamma,
                        gae_lambda=self.ppo_config.gae_lambda,
                    )
                    completed_returns: list[float] = []
                    completed_tick_counts: list[int] = []
                    rollout_started = time.perf_counter()
                    while not rollout.full:
                        if batch is None:
                            batch = self._new_batch()
                            reset = batch.reset()
                        elif batch_needs_reseed:
                            if not isinstance(batch, SubprocessEnvironmentBatch):
                                raise RuntimeError("only process batches support in-place reseed")
                            reset = batch.reseed(self._take_environment_seeds())
                            batch_needs_reseed = False
                        else:
                            reset = None
                        if reset is not None:
                            raw_observations = reset.observations
                            action_masks = reset.action_masks
                            self.normalizer.update(raw_observations)
                            normalized_observations = self.normalizer.normalize(
                                raw_observations, clip=self.config.observation_clip,
                            )
                        assert normalized_observations is not None
                        assert action_masks is not None
                        actions, log_probs, values = self.learner.act(
                            normalized_observations,
                            action_masks,
                            deterministic=False,
                        )
                        transition = batch.step(actions)
                        next_raw = transition.observations
                        self.normalizer.update(next_raw)
                        next_normalized = self.normalizer.normalize(
                            next_raw, clip=self.config.observation_clip,
                        )
                        next_values = self.learner.evaluate_value(next_normalized)
                        interval_rewards = np.asarray([
                            aggregate_interval_reward(
                                reward, int(elapsed), info,
                            )
                            for reward, elapsed, info in zip(
                                transition.rewards,
                                transition.elapsed_ticks,
                                transition.infos,
                                strict=True,
                            )
                        ], dtype=np.float64)
                        rollout.add(
                            observations=normalized_observations,
                            actions=actions,
                            action_masks=action_masks,
                            rewards=interval_rewards * self.config.reward_scale,
                            values=values,
                            log_probs=log_probs,
                            next_values=next_values,
                            elapsed_ticks=transition.elapsed_ticks,
                            terminated=transition.terminated,
                            truncated=transition.truncated,
                        )
                        self.total_simulation_ticks += int(
                            np.sum(transition.elapsed_ticks)
                        )
                        episode_returns += interval_rewards
                        episode_ticks += transition.elapsed_ticks
                        done = transition.terminated | transition.truncated
                        if np.any(done):
                            if not np.all(done):
                                raise RuntimeError(
                                    "vector environments ended asynchronously; use "
                                    "homogeneous fixed-horizon training tasks"
                                )
                            completed_returns.extend(episode_returns.tolist())
                            completed_tick_counts.extend(episode_ticks.tolist())
                            episode_returns.fill(0.0)
                            episode_ticks.fill(0)
                            if isinstance(batch, SubprocessEnvironmentBatch):
                                batch_needs_reseed = True
                            else:
                                batch.close()
                                batch = None
                            raw_observations = None
                            normalized_observations = None
                            action_masks = None
                        else:
                            raw_observations = next_raw
                            normalized_observations = next_normalized
                            action_masks = transition.action_masks

                    rollout.compute_returns_and_advantages()
                    update_stats = self.learner.update(rollout)
                    self.completed_updates += 1
                    self.total_samples += rollout.sample_count
                    elapsed_wall = time.perf_counter() - rollout_started
                    record: dict[str, Any] = {
                        "completed_episode_return_mean": (
                            float(np.mean(completed_returns))
                            if completed_returns else None
                        ),
                        "completed_episode_tick_mean": (
                            float(np.mean(completed_tick_counts))
                            if completed_tick_counts else None
                        ),
                        "environment_steps_per_second": (
                            rollout.sample_count / max(elapsed_wall, 1.0e-12)
                        ),
                        "samples_total": self.total_samples,
                        "simulation_ticks_total": self.total_simulation_ticks,
                        "update": self.completed_updates,
                        "update_stats": update_stats.to_dict(),
                        "wall_seconds": elapsed_wall,
                    }
                    metrics_file.write(
                        json.dumps(record, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                    metrics_file.flush()
                    if self.completed_updates % self.config.checkpoint_interval == 0:
                        self.save_checkpoint()
            self.save_checkpoint()
            self.export_policy()
        finally:
            if batch is not None:
                batch.close()

        wall_time = time.perf_counter() - start
        return TrainingResult(
            artifact_path=self.artifact_path,
            checkpoint_path=self.checkpoint_path,
            metrics_path=self.metrics_path,
            updates=self.completed_updates,
            samples=self.total_samples,
            simulation_ticks=self.total_simulation_ticks,
            wall_time_seconds=wall_time,
            device=str(self.learner.device),
        )
