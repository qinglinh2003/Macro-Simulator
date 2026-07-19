"""A compact, vectorized PPO learner for semi-Markov policy control."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from dataclasses import dataclass, asdict
import math
import random
from typing import Any

import numpy as np

from .buffer import RolloutBatch, SMDPRolloutBuffer
from .network import ActorCriticNetwork, require_torch


PPO_STATE_SCHEMA_VERSION = 1


try:  # Keep the engine importable without the RL training extra.
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - exercised in a base install
    if exc.name is not None and exc.name.split(".", 1)[0] != "torch":
        raise
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    checked = int(value)
    if checked <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return checked


def _finite_float(
    name: str,
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    if minimum is not None:
        invalid = checked < minimum if minimum_inclusive else checked <= minimum
        if invalid:
            comparator = ">=" if minimum_inclusive else ">"
            raise ValueError(f"{name} must be {comparator} {minimum}")
    if maximum is not None and checked > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return checked


@dataclass(frozen=True, slots=True)
class PPOConfig:
    """Validated PPO hyperparameters and architecture contract."""

    observation_dim: int
    action_dims: int
    hidden_sizes: tuple[int, ...] = (128, 128)
    activation: str = "tanh"
    learning_rate: float = 3.0e-4
    adam_eps: float = 1.0e-5
    gamma: float = 0.999
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    value_clip_range: float | None = 0.2
    entropy_coef: float = 0.0
    value_coef: float = 0.5
    max_grad_norm: float = 0.5
    batch_size: int = 256
    update_epochs: int = 10
    normalize_advantages: bool = True
    target_kl: float | None = None
    seed: int = 0
    device: str = "cpu"
    deterministic_torch: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_dim", _positive_int(
                "observation_dim", self.observation_dim,
            ),
        )
        object.__setattr__(
            self, "action_dims", _positive_int("action_dims", self.action_dims),
        )
        if isinstance(self.hidden_sizes, (str, bytes)) or not isinstance(
            self.hidden_sizes, Sequence,
        ):
            raise TypeError("hidden_sizes must be a non-empty sequence")
        checked_hidden = tuple(self.hidden_sizes)
        if not checked_hidden:
            raise ValueError("hidden_sizes must contain at least one layer")
        for index, size in enumerate(checked_hidden):
            _positive_int(f"hidden_sizes[{index}]", size)
        object.__setattr__(self, "hidden_sizes", checked_hidden)

        if not isinstance(self.activation, str):
            raise TypeError("activation must be a string")
        if self.activation not in {"elu", "gelu", "relu", "silu", "tanh"}:
            raise ValueError("activation must be one of: elu, gelu, relu, silu, tanh")

        object.__setattr__(
            self, "learning_rate", _finite_float(
                "learning_rate", self.learning_rate,
                minimum=0.0, minimum_inclusive=False,
            ),
        )
        object.__setattr__(
            self, "adam_eps", _finite_float(
                "adam_eps", self.adam_eps,
                minimum=0.0, minimum_inclusive=False,
            ),
        )
        object.__setattr__(
            self, "gamma", _finite_float(
                "gamma", self.gamma, minimum=0.0, maximum=1.0,
            ),
        )
        object.__setattr__(
            self, "gae_lambda", _finite_float(
                "gae_lambda", self.gae_lambda, minimum=0.0, maximum=1.0,
            ),
        )
        object.__setattr__(
            self, "clip_range", _finite_float(
                "clip_range", self.clip_range,
                minimum=0.0, maximum=1.0, minimum_inclusive=False,
            ),
        )
        if self.value_clip_range is not None:
            object.__setattr__(
                self, "value_clip_range", _finite_float(
                    "value_clip_range", self.value_clip_range,
                    minimum=0.0, minimum_inclusive=False,
                ),
            )
        object.__setattr__(
            self, "entropy_coef", _finite_float(
                "entropy_coef", self.entropy_coef, minimum=0.0,
            ),
        )
        object.__setattr__(
            self, "value_coef", _finite_float(
                "value_coef", self.value_coef, minimum=0.0,
            ),
        )
        object.__setattr__(
            self, "max_grad_norm", _finite_float(
                "max_grad_norm", self.max_grad_norm,
                minimum=0.0, minimum_inclusive=False,
            ),
        )
        object.__setattr__(self, "batch_size", _positive_int("batch_size", self.batch_size))
        object.__setattr__(
            self, "update_epochs", _positive_int("update_epochs", self.update_epochs),
        )
        if not isinstance(self.normalize_advantages, bool):
            raise TypeError("normalize_advantages must be a boolean")
        if self.target_kl is not None:
            object.__setattr__(
                self, "target_kl", _finite_float(
                    "target_kl", self.target_kl,
                    minimum=0.0, minimum_inclusive=False,
                ),
            )
        if isinstance(self.seed, (bool, np.bool_)) or not isinstance(
            self.seed, (int, np.integer),
        ):
            raise TypeError("seed must be an integer in [0, 2**63 - 1]")
        checked_seed = int(self.seed)
        if not 0 <= checked_seed < 2**63:
            raise ValueError("seed must be an integer in [0, 2**63 - 1]")
        object.__setattr__(self, "seed", checked_seed)
        if not isinstance(self.device, str):
            raise TypeError("device must be 'cpu', 'mps', or 'auto'")
        checked_device = self.device.lower()
        if checked_device not in {"auto", "cpu", "mps"}:
            raise ValueError("device must be 'cpu', 'mps', or 'auto'")
        object.__setattr__(self, "device", checked_device)
        if not isinstance(self.deterministic_torch, bool):
            raise TypeError("deterministic_torch must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PPOUpdateStats:
    samples: int
    epochs: int
    minibatches: int
    policy_loss: float
    value_loss: float
    entropy: float
    total_loss: float
    approx_kl: float
    clip_fraction: float
    explained_variance: float
    grad_norm: float
    early_stopped: bool

    def to_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


def resolve_device(device: str):
    """Resolve ``cpu``/``mps``/``auto`` and fail fast for unavailable MPS."""
    require_torch()
    assert torch is not None
    if not isinstance(device, str):
        raise TypeError("device must be 'cpu', 'mps', or 'auto'")
    requested = device.lower()
    if requested not in {"auto", "cpu", "mps"}:
        raise ValueError("device must be 'cpu', 'mps', or 'auto'")
    mps_available = bool(
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    )
    if requested == "mps" and not mps_available:
        raise RuntimeError(
            "MPS was requested but is unavailable; use device='cpu' or install "
            "an MPS-enabled PyTorch build"
        )
    selected = "mps" if requested == "auto" and mps_available else requested
    if selected == "auto":
        selected = "cpu"
    return torch.device(selected)


def seed_everything(seed: int, *, deterministic_torch: bool = False) -> None:
    """Seed Python, NumPy, and PyTorch from one validated seed."""
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise TypeError("seed must be an integer in [0, 2**63 - 1]")
    checked = int(seed)
    if not 0 <= checked < 2**63:
        raise ValueError("seed must be an integer in [0, 2**63 - 1]")
    if not isinstance(deterministic_torch, bool):
        raise TypeError("deterministic_torch must be a boolean")
    require_torch()
    assert torch is not None
    random.seed(checked)
    np.random.seed(checked % 2**32)
    torch.manual_seed(checked)
    if deterministic_torch:
        torch.use_deterministic_algorithms(True)


class SMDPPPO:
    """PyTorch PPO with masked joint actions and externally collected SMDP data."""

    def __init__(
        self,
        config: PPOConfig,
        *,
        network: Any | None = None,
    ) -> None:
        require_torch()
        assert torch is not None and nn is not None
        if not isinstance(config, PPOConfig):
            raise TypeError("config must be a PPOConfig")
        self.config = config
        self.device = resolve_device(config.device)
        seed_everything(
            config.seed, deterministic_torch=config.deterministic_torch,
        )
        if network is None:
            network = ActorCriticNetwork(
                config.observation_dim,
                config.action_dims,
                hidden_sizes=config.hidden_sizes,
                activation=config.activation,
            )
        if not isinstance(network, nn.Module):
            raise TypeError("network must be a torch.nn.Module")
        if getattr(network, "observation_dim", None) != config.observation_dim:
            raise ValueError("network observation dimension does not match config")
        if getattr(network, "action_dims", None) != config.action_dims:
            raise ValueError("network action dimensions do not match config")
        self.network = network.to(self.device)
        self.optimizer = torch.optim.Adam(
            self.network.parameters(),
            lr=config.learning_rate,
            eps=config.adam_eps,
        )
        self._minibatch_rng = np.random.default_rng(config.seed)
        try:
            self._action_generator: torch.Generator | None = torch.Generator(
                device=self.device,
            )
            self._action_generator.manual_seed(config.seed)
        except (RuntimeError, TypeError):  # Older MPS builds use the global seed.
            self._action_generator = None

    def reseed(self, seed: int | None = None) -> None:
        """Reset policy sampling and minibatch-order streams without changing weights."""
        checked = self.config.seed if seed is None else seed
        if isinstance(checked, bool) or not isinstance(checked, int):
            raise TypeError("seed must be an integer in [0, 2**63 - 1]")
        if not 0 <= checked < 2**63:
            raise ValueError("seed must be an integer in [0, 2**63 - 1]")
        self._minibatch_rng = np.random.default_rng(checked)
        if self._action_generator is not None:
            self._action_generator.manual_seed(checked)
        else:
            torch.manual_seed(checked)

    def _action_rng_state(self):
        if self._action_generator is not None:
            return self._action_generator.get_state().clone()
        if self.device.type == "mps" and hasattr(torch.mps, "get_rng_state"):
            return torch.mps.get_rng_state().clone()
        return torch.get_rng_state().clone()

    def _set_action_rng_state(self, state) -> None:
        if self._action_generator is not None:
            self._action_generator.set_state(state)
        elif self.device.type == "mps" and hasattr(torch.mps, "set_rng_state"):
            torch.mps.set_rng_state(state)
        else:
            torch.set_rng_state(state)

    @staticmethod
    def _validate_checkpoint_container(value: Any, *, path: str = "state") -> None:
        """Limit resume payloads to weights-only-safe built-in structures."""
        if value is None or type(value) in {bool, int, str}:
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError(f"{path} contains a non-finite float")
            return
        if torch.is_tensor(value):
            return
        if type(value) in {list, tuple}:
            for index, item in enumerate(value):
                SMDPPPO._validate_checkpoint_container(
                    item, path=f"{path}[{index}]",
                )
            return
        if type(value) is dict:
            for key, item in value.items():
                if type(key) not in {int, str}:
                    raise TypeError(
                        f"{path} contains a non-primitive mapping key"
                    )
                SMDPPPO._validate_checkpoint_container(
                    item, path=f"{path}[{key!r}]",
                )
            return
        raise TypeError(
            f"{path} contains unsupported checkpoint type {type(value).__name__}"
        )

    def state_dict(self) -> dict[str, Any]:
        """Return a ``torch.load(weights_only=True)`` compatible resume state."""
        network_state = {
            name: value.detach().clone()
            for name, value in self.network.state_dict().items()
        }
        state = {
            "schema_version": PPO_STATE_SCHEMA_VERSION,
            "config": self.config.to_dict(),
            "network": network_state,
            "optimizer": copy.deepcopy(self.optimizer.state_dict()),
            "minibatch_rng": copy.deepcopy(self._minibatch_rng.bit_generator.state),
            "action_rng": self._action_rng_state(),
            "action_rng_is_local": self._action_generator is not None,
        }
        self._validate_checkpoint_container(state)
        return state

    def _validate_network_state(self, state: Any) -> None:
        if type(state) is not dict:
            raise TypeError("state.network must be a dictionary")
        expected = self.network.state_dict()
        if set(state) != set(expected):
            raise ValueError(
                "state.network keys differ from the configured network; "
                f"missing={sorted(set(expected) - set(state))}, "
                f"extra={sorted(set(state) - set(expected))}"
            )
        for name, expected_tensor in expected.items():
            candidate = state[name]
            if not torch.is_tensor(candidate):
                raise TypeError(f"state.network[{name!r}] must be a tensor")
            if candidate.shape != expected_tensor.shape:
                raise ValueError(
                    f"state.network[{name!r}] shape must be "
                    f"{tuple(expected_tensor.shape)}, got {tuple(candidate.shape)}"
                )
            if candidate.dtype != expected_tensor.dtype:
                raise TypeError(
                    f"state.network[{name!r}] dtype must be "
                    f"{expected_tensor.dtype}, got {candidate.dtype}"
                )
            if candidate.is_floating_point() and not bool(torch.isfinite(candidate).all()):
                raise ValueError(f"state.network[{name!r}] contains NaN or Infinity")

    def _validate_optimizer_state(self, state: Any) -> None:
        if type(state) is not dict or set(state) != {"state", "param_groups"}:
            raise ValueError("state.optimizer must contain state and param_groups")
        raw_states = state["state"]
        raw_groups = state["param_groups"]
        if type(raw_states) is not dict or type(raw_groups) is not list:
            raise TypeError("state.optimizer has invalid container types")
        current_groups = self.optimizer.state_dict()["param_groups"]
        if len(raw_groups) != len(current_groups):
            raise ValueError("state.optimizer param group count differs")

        saved_parameter_ids: list[int] = []
        live_parameters: list[Any] = []
        for index, (saved_group, current_group, live_group) in enumerate(zip(
            raw_groups, current_groups, self.optimizer.param_groups, strict=True,
        )):
            if type(saved_group) is not dict or set(saved_group) != set(current_group):
                raise ValueError(f"state.optimizer param group {index} keys differ")
            saved_ids = saved_group["params"]
            if type(saved_ids) is not list or len(saved_ids) != len(live_group["params"]):
                raise ValueError(
                    f"state.optimizer param group {index} parameter count differs"
                )
            for parameter_id in saved_ids:
                if isinstance(parameter_id, bool) or not isinstance(parameter_id, int):
                    raise TypeError("state.optimizer parameter ids must be integers")
            for name, current_value in current_group.items():
                if name == "params":
                    continue
                if saved_group[name] != current_value:
                    raise ValueError(
                        f"state.optimizer param group {index} field {name!r} "
                        "differs from the configured optimizer"
                    )
            saved_parameter_ids.extend(saved_ids)
            live_parameters.extend(live_group["params"])
        if len(saved_parameter_ids) != len(set(saved_parameter_ids)):
            raise ValueError("state.optimizer contains duplicate parameter ids")
        if not set(raw_states).issubset(saved_parameter_ids):
            raise ValueError("state.optimizer contains an unknown parameter id")

        allowed_fields = {"step", "exp_avg", "exp_avg_sq", "max_exp_avg_sq"}
        for parameter_id, parameter in zip(
            saved_parameter_ids, live_parameters, strict=True,
        ):
            parameter_state = raw_states.get(parameter_id)
            if parameter_state is None:
                continue
            if type(parameter_state) is not dict:
                raise TypeError("state.optimizer parameter state must be a dictionary")
            if not set(parameter_state).issubset(allowed_fields):
                raise ValueError("state.optimizer contains an unknown Adam state field")
            required = {"step", "exp_avg", "exp_avg_sq"}
            if not required.issubset(parameter_state):
                raise ValueError("state.optimizer Adam parameter state is incomplete")
            for name, value in parameter_state.items():
                if not torch.is_tensor(value):
                    raise TypeError(
                        f"state.optimizer parameter field {name!r} must be a tensor"
                    )
                if name == "step":
                    if value.numel() != 1:
                        raise ValueError("state.optimizer Adam step must be scalar")
                else:
                    if value.shape != parameter.shape:
                        raise ValueError(
                            f"state.optimizer {name} shape differs from parameter"
                        )
                    if value.dtype != parameter.dtype:
                        raise TypeError(
                            f"state.optimizer {name} dtype differs from parameter"
                        )
                if value.is_floating_point() and not bool(torch.isfinite(value).all()):
                    raise ValueError(
                        f"state.optimizer parameter field {name!r} is non-finite"
                    )

    def _validate_rng_states(
        self,
        minibatch_state: Any,
        action_state: Any,
        *,
        action_rng_is_local: Any,
    ) -> None:
        if type(minibatch_state) is not dict:
            raise TypeError("state.minibatch_rng must be a dictionary")
        if minibatch_state.get("bit_generator") != type(
            self._minibatch_rng.bit_generator,
        ).__name__:
            raise ValueError("state.minibatch_rng uses a different bit generator")
        try:
            probe = np.random.default_rng()
            probe.bit_generator.state = copy.deepcopy(minibatch_state)
        except (TypeError, ValueError) as exc:
            raise ValueError("state.minibatch_rng is invalid") from exc
        if type(action_rng_is_local) is not bool:
            raise TypeError("state.action_rng_is_local must be a boolean")
        if action_rng_is_local != (self._action_generator is not None):
            raise ValueError("state action RNG backend differs from this PyTorch runtime")
        if not torch.is_tensor(action_state):
            raise TypeError("state.action_rng must be a tensor")
        expected_action_state = self._action_rng_state()
        if action_state.dtype != torch.uint8 or action_state.device.type != "cpu":
            raise TypeError("state.action_rng must be a CPU uint8 tensor")
        if action_state.shape != expected_action_state.shape:
            raise ValueError("state.action_rng shape differs from this PyTorch runtime")

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        """Transactionally restore model, optimizer, and both RNG streams."""
        if type(state) is not dict:
            raise TypeError("PPO state must be a built-in dictionary")
        expected_keys = {
            "schema_version", "config", "network", "optimizer",
            "minibatch_rng", "action_rng", "action_rng_is_local",
        }
        if set(state) != expected_keys:
            raise ValueError(
                "PPO state keys differ; "
                f"missing={sorted(expected_keys - set(state))}, "
                f"extra={sorted(set(state) - expected_keys)}"
            )
        self._validate_checkpoint_container(state)
        if type(state["schema_version"]) is not int \
                or state["schema_version"] != PPO_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported PPO state schema_version")
        if type(state["config"]) is not dict \
                or state["config"] != self.config.to_dict():
            raise ValueError("PPO state config differs from this learner")
        self._validate_network_state(state["network"])
        self._validate_optimizer_state(state["optimizer"])
        self._validate_rng_states(
            state["minibatch_rng"],
            state["action_rng"],
            action_rng_is_local=state["action_rng_is_local"],
        )

        previous_network = {
            name: value.detach().clone()
            for name, value in self.network.state_dict().items()
        }
        previous_optimizer = copy.deepcopy(self.optimizer.state_dict())
        previous_minibatch_rng = copy.deepcopy(
            self._minibatch_rng.bit_generator.state,
        )
        previous_action_rng = self._action_rng_state()
        try:
            self.network.load_state_dict(state["network"], strict=True)
            self.optimizer.load_state_dict(copy.deepcopy(state["optimizer"]))
            self._minibatch_rng.bit_generator.state = copy.deepcopy(
                state["minibatch_rng"],
            )
            self._set_action_rng_state(state["action_rng"])
        except Exception:
            self.network.load_state_dict(previous_network, strict=True)
            self.optimizer.load_state_dict(previous_optimizer)
            self._minibatch_rng.bit_generator.state = previous_minibatch_rng
            self._set_action_rng_state(previous_action_rng)
            raise

    def _inference_inputs(
        self, observation: Any, action_mask: Any,
    ) -> tuple[Any, Any, bool]:
        observations = np.asarray(observation)
        single = observations.ndim == 1
        if single:
            observations = observations[None, :]
        if observations.ndim != 2 or observations.shape[1] != self.config.observation_dim:
            raise ValueError(
                "observation must have shape [observation_dim] or "
                "[batch, observation_dim]"
            )
        if observations.dtype.kind not in "iuf" or not np.all(np.isfinite(observations)):
            raise ValueError("observation must contain finite real values")

        masks = np.asarray(action_mask)
        if single and masks.ndim == 2:
            masks = masks[None, :, :]
        expected_masks = (observations.shape[0], self.config.action_dims, 3)
        if masks.shape != expected_masks:
            raise ValueError(f"action_mask must have shape {expected_masks}")
        if masks.dtype.kind not in "biu" or np.any((masks != 0) & (masks != 1)):
            raise ValueError("action_mask must contain only boolean/0/1 entries")
        masks = masks.astype(np.bool_, copy=False)
        if np.any(~masks.any(axis=-1)):
            raise ValueError("every action dimension must have at least one legal action")

        observation_tensor = torch.as_tensor(
            observations, dtype=torch.float32, device=self.device,
        )
        mask_tensor = torch.as_tensor(masks, dtype=torch.bool, device=self.device)
        return observation_tensor, mask_tensor, single

    def act(
        self,
        observation: Any,
        action_mask: Any,
        *,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, np.ndarray | float, np.ndarray | float]:
        """Return actions, joint log probabilities, and values for rollout storage."""
        if not isinstance(deterministic, bool):
            raise TypeError("deterministic must be a boolean")
        observation_tensor, mask_tensor, single = self._inference_inputs(
            observation, action_mask,
        )
        self.network.eval()
        with torch.inference_mode():
            actions, log_probs, values = self.network.act(
                observation_tensor,
                mask_tensor,
                deterministic=deterministic,
                generator=self._action_generator,
                validate=False,
            )
        action_array = actions.cpu().numpy().astype(np.int64, copy=False)
        log_prob_array = log_probs.cpu().numpy().astype(np.float32, copy=False)
        value_array = values.cpu().numpy().astype(np.float32, copy=False)
        if single:
            return action_array[0], float(log_prob_array[0]), float(value_array[0])
        return action_array, log_prob_array, value_array

    def predict(
        self,
        observation: Any,
        action_mask: Any,
        *,
        deterministic: bool = True,
    ) -> np.ndarray:
        """Inference adapter: a single observation returns one action vector."""
        actions, _log_probs, _values = self.act(
            observation, action_mask, deterministic=deterministic,
        )
        return actions

    def evaluate_value(self, observation: Any) -> np.ndarray | float:
        observations = np.asarray(observation)
        single = observations.ndim == 1
        if single:
            observations = observations[None, :]
        if observations.ndim != 2 or observations.shape[1] != self.config.observation_dim:
            raise ValueError(
                "observation must have shape [observation_dim] or "
                "[batch, observation_dim]"
            )
        if observations.dtype.kind not in "iuf" or not np.all(np.isfinite(observations)):
            raise ValueError("observation must contain finite real values")
        tensor = torch.as_tensor(
            observations, dtype=torch.float32, device=self.device,
        )
        self.network.eval()
        with torch.inference_mode():
            _logits, values = self.network(tensor)
        result = values.cpu().numpy().astype(np.float32, copy=False)
        return float(result[0]) if single else result

    def update(
        self, rollout: RolloutBatch | SMDPRolloutBuffer,
    ) -> PPOUpdateStats:
        """Run vectorized minibatch PPO updates over a flattened rollout."""
        if isinstance(rollout, SMDPRolloutBuffer):
            if not math.isclose(rollout.gamma, self.config.gamma, rel_tol=0.0, abs_tol=1e-15):
                raise ValueError("rollout gamma does not match PPO configuration")
            if not math.isclose(
                rollout.gae_lambda, self.config.gae_lambda,
                rel_tol=0.0, abs_tol=1e-15,
            ):
                raise ValueError("rollout gae_lambda does not match PPO configuration")
            if not rollout.advantages_ready:
                rollout.compute_returns_and_advantages()
            batch = rollout.flatten()
        elif isinstance(rollout, RolloutBatch):
            batch = rollout
        else:
            raise TypeError("rollout must be RolloutBatch or SMDPRolloutBuffer")
        batch.validate(
            observation_dim=self.config.observation_dim,
            action_dims=self.config.action_dims,
        )

        observations = torch.as_tensor(
            batch.observations, dtype=torch.float32, device=self.device,
        )
        actions = torch.as_tensor(
            batch.actions, dtype=torch.long, device=self.device,
        )
        action_masks = torch.as_tensor(
            batch.action_masks, dtype=torch.bool, device=self.device,
        )
        old_log_probs = torch.as_tensor(
            batch.old_log_probs, dtype=torch.float32, device=self.device,
        )
        old_values = torch.as_tensor(
            batch.old_values, dtype=torch.float32, device=self.device,
        )
        returns = torch.as_tensor(
            batch.returns, dtype=torch.float32, device=self.device,
        )
        advantages = torch.as_tensor(
            batch.advantages, dtype=torch.float32, device=self.device,
        )
        if self.config.normalize_advantages and batch.sample_count > 1:
            advantages = (
                advantages - advantages.mean()
            ) / advantages.std(unbiased=False).clamp_min(1.0e-8)

        metric_names = (
            "policy_loss", "value_loss", "entropy", "total_loss",
            "approx_kl", "clip_fraction",
        )
        metrics = {
            name: torch.zeros((), dtype=torch.float32, device=self.device)
            for name in metric_names
        }
        grad_norm_sum = torch.zeros((), dtype=torch.float32, device=self.device)
        weighted_samples = 0
        minibatches = 0
        epochs_completed = 0
        early_stopped = False
        self.network.train()

        for epoch in range(self.config.update_epochs):
            permutation = self._minibatch_rng.permutation(batch.sample_count)
            epoch_kl_sum = torch.zeros((), dtype=torch.float32, device=self.device)
            epoch_samples = 0
            for start in range(0, batch.sample_count, self.config.batch_size):
                numpy_indices = permutation[start:start + self.config.batch_size]
                indices = torch.as_tensor(
                    numpy_indices, dtype=torch.long, device=self.device,
                )
                new_log_probs, entropy, new_values = self.network.evaluate_actions(
                    observations[indices],
                    action_masks[indices],
                    actions[indices],
                    validate=False,
                )
                log_ratio = new_log_probs - old_log_probs[indices]
                ratio = log_ratio.exp()
                minibatch_advantages = advantages[indices]
                unclipped_policy = -minibatch_advantages * ratio
                clipped_policy = -minibatch_advantages * ratio.clamp(
                    1.0 - self.config.clip_range,
                    1.0 + self.config.clip_range,
                )
                policy_loss = torch.maximum(
                    unclipped_policy, clipped_policy,
                ).mean()

                minibatch_returns = returns[indices]
                if self.config.value_clip_range is None:
                    value_loss = 0.5 * (
                        new_values - minibatch_returns
                    ).square().mean()
                else:
                    value_delta = new_values - old_values[indices]
                    clipped_values = old_values[indices] + value_delta.clamp(
                        -self.config.value_clip_range,
                        self.config.value_clip_range,
                    )
                    value_loss = 0.5 * torch.maximum(
                        (new_values - minibatch_returns).square(),
                        (clipped_values - minibatch_returns).square(),
                    ).mean()
                entropy_mean = entropy.mean()
                total_loss = (
                    policy_loss
                    + self.config.value_coef * value_loss
                    - self.config.entropy_coef * entropy_mean
                )

                self.optimizer.zero_grad(set_to_none=True)
                total_loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(
                    self.network.parameters(),
                    self.config.max_grad_norm,
                    error_if_nonfinite=True,
                )
                self.optimizer.step()

                with torch.no_grad():
                    approx_kl = ((ratio - 1.0) - log_ratio).mean()
                    clip_fraction = (
                        (ratio - 1.0).abs() > self.config.clip_range
                    ).float().mean()
                    count = int(indices.numel())
                    values_by_name = {
                        "policy_loss": policy_loss,
                        "value_loss": value_loss,
                        "entropy": entropy_mean,
                        "total_loss": total_loss,
                        "approx_kl": approx_kl,
                        "clip_fraction": clip_fraction,
                    }
                    for name, value in values_by_name.items():
                        metrics[name] += value.detach() * count
                    grad_norm_sum += grad_norm.detach()
                    epoch_kl_sum += approx_kl.detach() * count
                    weighted_samples += count
                    epoch_samples += count
                    minibatches += 1

            epochs_completed = epoch + 1
            if self.config.target_kl is not None and epoch_samples:
                epoch_kl = float((epoch_kl_sum / epoch_samples).cpu())
                if epoch_kl > self.config.target_kl:
                    early_stopped = True
                    break

        if weighted_samples == 0 or minibatches == 0:  # defensive, validate forbids this
            raise RuntimeError("PPO update processed no samples")
        metric_values = {
            name: float((value / weighted_samples).detach().cpu())
            for name, value in metrics.items()
        }
        returns_array = np.asarray(batch.returns, dtype=np.float64)
        old_values_array = np.asarray(batch.old_values, dtype=np.float64)
        return_variance = float(np.var(returns_array))
        explained_variance = (
            float(1.0 - np.var(returns_array - old_values_array) / return_variance)
            if return_variance > 1.0e-12 else 0.0
        )
        return PPOUpdateStats(
            samples=batch.sample_count,
            epochs=epochs_completed,
            minibatches=minibatches,
            policy_loss=metric_values["policy_loss"],
            value_loss=metric_values["value_loss"],
            entropy=metric_values["entropy"],
            total_loss=metric_values["total_loss"],
            approx_kl=metric_values["approx_kl"],
            clip_fraction=metric_values["clip_fraction"],
            explained_variance=explained_variance,
            grad_norm=float((grad_norm_sum / minibatches).detach().cpu()),
            early_stopped=early_stopped,
        )


__all__ = [
    "PPOConfig",
    "PPO_STATE_SCHEMA_VERSION",
    "PPOUpdateStats",
    "SMDPPPO",
    "resolve_device",
    "seed_everything",
]
