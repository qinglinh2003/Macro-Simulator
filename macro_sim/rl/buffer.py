"""NumPy rollout storage with elapsed-time-aware SMDP GAE.

The buffer deliberately has no PyTorch dependency.  Environment processes can
therefore collect rollouts without importing the training backend, and a whole
flattened rollout can be transferred to CPU or MPS once per PPO update.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _strict_positive_int(name: str, value: Any) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    checked = int(value)
    if checked <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return checked


def _strict_discount(name: str, value: Any) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite float in [0, 1]")
    checked = float(value)
    if not np.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise ValueError(f"{name} must be a finite float in [0, 1]")
    return checked


@dataclass(frozen=True, slots=True)
class RolloutBatch:
    """A time/env-flattened PPO training batch.

    All leading dimensions have already been flattened to ``sample_count``.
    Keeping this as a NumPy contract makes it cheap to serialize, inspect, and
    hand to a local or remote PyTorch learner.
    """

    observations: np.ndarray
    actions: np.ndarray
    action_masks: np.ndarray
    old_log_probs: np.ndarray
    old_values: np.ndarray
    returns: np.ndarray
    advantages: np.ndarray
    elapsed_ticks: np.ndarray

    @property
    def sample_count(self) -> int:
        return int(self.observations.shape[0])

    def validate(
        self,
        *,
        observation_dim: int | None = None,
        action_dims: int | None = None,
    ) -> None:
        """Reject malformed batches before they reach an optimizer step."""
        if self.observations.ndim != 2:
            raise ValueError("observations must have shape [samples, observation_dim]")
        samples = self.sample_count
        if samples <= 0:
            raise ValueError("rollout batch must contain at least one sample")
        if observation_dim is not None and self.observations.shape[1] != observation_dim:
            raise ValueError(
                "rollout observation dimension does not match PPO configuration"
            )
        if self.actions.ndim != 2:
            raise ValueError("actions must have shape [samples, action_dims]")
        inferred_action_dims = int(self.actions.shape[1])
        if action_dims is not None and inferred_action_dims != action_dims:
            raise ValueError("rollout action dimensions do not match PPO configuration")
        expected_shapes = {
            "actions": (samples, inferred_action_dims),
            "action_masks": (samples, inferred_action_dims, 3),
            "old_log_probs": (samples,),
            "old_values": (samples,),
            "returns": (samples,),
            "advantages": (samples,),
            "elapsed_ticks": (samples,),
        }
        for name, expected in expected_shapes.items():
            actual = np.asarray(getattr(self, name)).shape
            if actual != expected:
                raise ValueError(f"{name} must have shape {expected}, got {actual}")

        numeric = (
            "observations", "old_log_probs", "old_values", "returns", "advantages",
        )
        for name in numeric:
            if not np.all(np.isfinite(np.asarray(getattr(self, name)))):
                raise ValueError(f"{name} must contain only finite values")
        if self.actions.dtype.kind not in "iu" or np.issubdtype(
            self.actions.dtype, np.bool_,
        ):
            raise TypeError("actions must contain integer direction codes")
        if np.any((self.actions < 0) | (self.actions > 2)):
            raise ValueError("actions must use direction codes 0, 1, or 2")

        masks = np.asarray(self.action_masks)
        if masks.dtype.kind not in "biu" or np.any((masks != 0) & (masks != 1)):
            raise ValueError("action_masks must contain only boolean/0/1 entries")
        boolean_masks = masks.astype(np.bool_, copy=False)
        if np.any(~boolean_masks.any(axis=-1)):
            raise ValueError("every action dimension must have at least one legal action")
        selected_legal = np.take_along_axis(
            boolean_masks, self.actions[..., None], axis=-1,
        ).squeeze(-1)
        if not bool(np.all(selected_legal)):
            raise ValueError("rollout contains an action forbidden by its action mask")

        elapsed = np.asarray(self.elapsed_ticks)
        if elapsed.dtype.kind not in "iu" or np.issubdtype(elapsed.dtype, np.bool_):
            raise TypeError("elapsed_ticks must contain positive integers")
        if np.any(elapsed <= 0):
            raise ValueError("elapsed_ticks must contain positive integers")


class SMDPRolloutBuffer:
    """Fixed-capacity vector rollout storage.

    ``next_values`` is explicit for every transition.  This avoids the common
    time-limit bug: a truncated transition can bootstrap from its terminal
    observation while still cutting the GAE trace before the reset episode.
    """

    def __init__(
        self,
        *,
        capacity: int,
        num_envs: int,
        observation_dim: int,
        action_dims: int,
        gamma: float,
        gae_lambda: float,
    ) -> None:
        self.capacity = _strict_positive_int("capacity", capacity)
        self.num_envs = _strict_positive_int("num_envs", num_envs)
        self.observation_dim = _strict_positive_int(
            "observation_dim", observation_dim,
        )
        self.action_dims = _strict_positive_int("action_dims", action_dims)
        self.gamma = _strict_discount("gamma", gamma)
        self.gae_lambda = _strict_discount("gae_lambda", gae_lambda)

        time_env = (self.capacity, self.num_envs)
        self.observations = np.empty(
            (*time_env, self.observation_dim), dtype=np.float32,
        )
        self.actions = np.empty((*time_env, self.action_dims), dtype=np.int64)
        self.action_masks = np.empty(
            (*time_env, self.action_dims, 3), dtype=np.bool_,
        )
        self.rewards = np.empty(time_env, dtype=np.float32)
        self.values = np.empty(time_env, dtype=np.float32)
        self.next_values = np.empty(time_env, dtype=np.float32)
        self.log_probs = np.empty(time_env, dtype=np.float32)
        self.elapsed_ticks = np.empty(time_env, dtype=np.int64)
        self.terminated = np.empty(time_env, dtype=np.bool_)
        self.truncated = np.empty(time_env, dtype=np.bool_)
        self.advantages = np.empty(time_env, dtype=np.float32)
        self.returns = np.empty(time_env, dtype=np.float32)
        self.reset()

    @property
    def size(self) -> int:
        return self._position

    @property
    def full(self) -> bool:
        return self._position == self.capacity

    @property
    def advantages_ready(self) -> bool:
        return self._advantages_ready

    @property
    def sample_count(self) -> int:
        return self.size * self.num_envs

    def reset(self) -> None:
        self._position = 0
        self._advantages_ready = False

    def add(
        self,
        *,
        observations: Any,
        actions: Any,
        action_masks: Any,
        rewards: Any,
        values: Any,
        log_probs: Any,
        next_values: Any,
        elapsed_ticks: Any,
        terminated: Any,
        truncated: Any,
    ) -> None:
        """Append one vectorized environment step with exact shape checking."""
        if self.full:
            raise RuntimeError("rollout buffer is full; update or reset it first")

        observations_array = self._finite_float_array(
            "observations", observations,
            (self.num_envs, self.observation_dim),
        )
        actions_array = np.asarray(actions)
        expected_actions = (self.num_envs, self.action_dims)
        if actions_array.shape != expected_actions:
            raise ValueError(
                f"actions must have shape {expected_actions}, got {actions_array.shape}"
            )
        if actions_array.dtype.kind not in "iu" or np.issubdtype(
            actions_array.dtype, np.bool_,
        ):
            raise TypeError("actions must contain integer direction codes")
        if np.any((actions_array < 0) | (actions_array > 2)):
            raise ValueError("actions must use direction codes 0, 1, or 2")

        masks_array = np.asarray(action_masks)
        expected_masks = (self.num_envs, self.action_dims, 3)
        if masks_array.shape != expected_masks:
            raise ValueError(
                "action_masks must have shape "
                f"{expected_masks}, got {masks_array.shape}"
            )
        if masks_array.dtype.kind not in "biu" or np.any(
            (masks_array != 0) & (masks_array != 1)
        ):
            raise ValueError("action_masks must contain only boolean/0/1 entries")
        boolean_masks = masks_array.astype(np.bool_, copy=False)
        if np.any(~boolean_masks.any(axis=-1)):
            raise ValueError("every action dimension must have at least one legal action")
        selected_legal = np.take_along_axis(
            boolean_masks, actions_array[..., None], axis=-1,
        ).squeeze(-1)
        if not bool(np.all(selected_legal)):
            raise ValueError("actions contain a direction forbidden by action_masks")

        scalar_shape = (self.num_envs,)
        rewards_array = self._finite_float_array("rewards", rewards, scalar_shape)
        values_array = self._finite_float_array("values", values, scalar_shape)
        log_probs_array = self._finite_float_array(
            "log_probs", log_probs, scalar_shape,
        )
        next_values_array = self._finite_float_array(
            "next_values", next_values, scalar_shape,
        )

        elapsed_array = np.asarray(elapsed_ticks)
        if elapsed_array.shape != scalar_shape:
            raise ValueError(
                f"elapsed_ticks must have shape {scalar_shape}, got {elapsed_array.shape}"
            )
        if elapsed_array.dtype.kind not in "iu" or np.issubdtype(
            elapsed_array.dtype, np.bool_,
        ):
            raise TypeError("elapsed_ticks must contain positive integers")
        if np.any(elapsed_array <= 0):
            raise ValueError("elapsed_ticks must contain positive integers")

        terminated_array = self._bool_array("terminated", terminated, scalar_shape)
        truncated_array = self._bool_array("truncated", truncated, scalar_shape)
        if np.any(terminated_array & truncated_array):
            raise ValueError("a transition cannot be both terminated and truncated")

        index = self._position
        self.observations[index] = observations_array
        self.actions[index] = actions_array
        self.action_masks[index] = boolean_masks
        self.rewards[index] = rewards_array
        self.values[index] = values_array
        self.log_probs[index] = log_probs_array
        self.next_values[index] = next_values_array
        self.elapsed_ticks[index] = elapsed_array
        self.terminated[index] = terminated_array
        self.truncated[index] = truncated_array
        self._position += 1
        self._advantages_ready = False

    @staticmethod
    def _finite_float_array(name: str, value: Any, shape: tuple[int, ...]) -> np.ndarray:
        array = np.asarray(value)
        if array.shape != shape:
            raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
        if array.dtype.kind not in "iuf":
            raise TypeError(f"{name} must contain real numeric values")
        try:
            checked = array.astype(np.float32, copy=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise TypeError(f"{name} must contain real numeric values") from exc
        if not np.all(np.isfinite(checked)):
            raise ValueError(f"{name} must contain only finite values")
        return checked

    @staticmethod
    def _bool_array(name: str, value: Any, shape: tuple[int, ...]) -> np.ndarray:
        array = np.asarray(value)
        if array.shape != shape:
            raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
        if array.dtype.kind != "b":
            raise TypeError(f"{name} must contain booleans")
        return array

    def compute_returns_and_advantages(self) -> None:
        """Compute GAE with ``gamma**dt`` and ``lambda**dt`` per transition."""
        if self.size == 0:
            raise RuntimeError("cannot compute advantages for an empty rollout")

        next_advantage = np.zeros(self.num_envs, dtype=np.float64)
        gamma = self.gamma
        gae_lambda = self.gae_lambda
        for step in range(self.size - 1, -1, -1):
            elapsed = self.elapsed_ticks[step].astype(np.float64, copy=False)
            gamma_discount = np.power(gamma, elapsed)
            lambda_discount = np.power(gae_lambda, elapsed)
            bootstrap = (~self.terminated[step]).astype(np.float64)
            trace_continues = (~(
                self.terminated[step] | self.truncated[step]
            )).astype(np.float64)
            delta = (
                self.rewards[step].astype(np.float64)
                + gamma_discount
                * self.next_values[step].astype(np.float64)
                * bootstrap
                - self.values[step].astype(np.float64)
            )
            next_advantage = (
                delta
                + gamma_discount
                * lambda_discount
                * trace_continues
                * next_advantage
            )
            self.advantages[step] = next_advantage

        self.returns[:self.size] = (
            self.advantages[:self.size] + self.values[:self.size]
        )
        self._advantages_ready = True

    def flatten(self) -> RolloutBatch:
        """Return a contiguous time-major/env-minor view for vectorized PPO."""
        if not self._advantages_ready:
            raise RuntimeError("compute_returns_and_advantages() must run first")
        stop = self.size
        batch = RolloutBatch(
            observations=self.observations[:stop].reshape(
                self.sample_count, self.observation_dim,
            ),
            actions=self.actions[:stop].reshape(self.sample_count, self.action_dims),
            action_masks=self.action_masks[:stop].reshape(
                self.sample_count, self.action_dims, 3,
            ),
            old_log_probs=self.log_probs[:stop].reshape(self.sample_count),
            old_values=self.values[:stop].reshape(self.sample_count),
            returns=self.returns[:stop].reshape(self.sample_count),
            advantages=self.advantages[:stop].reshape(self.sample_count),
            elapsed_ticks=self.elapsed_ticks[:stop].reshape(self.sample_count),
        )
        batch.validate(
            observation_dim=self.observation_dim,
            action_dims=self.action_dims,
        )
        return batch
