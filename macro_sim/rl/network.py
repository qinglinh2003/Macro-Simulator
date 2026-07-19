"""Masked actor-critic network for three-way MultiDiscrete policies.

PyTorch remains an optional dependency of the simulator.  Importing this module
is safe without PyTorch; constructing a network then raises an actionable error.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


try:  # Optional so importing macro_sim does not require a training backend.
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - exercised in a clean base install
    if exc.name is not None and exc.name.split(".", 1)[0] != "torch":
        raise
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def require_torch() -> None:
    """Raise a precise error only when a PyTorch-backed feature is requested."""
    if torch is None:
        raise ModuleNotFoundError(
            "PyTorch is required for RL training; install the project's RL "
            "training extra before constructing ActorCriticNetwork"
        ) from _TORCH_IMPORT_ERROR


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _hidden_sizes(value: Sequence[int]) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("hidden_sizes must be a non-empty sequence of integers")
    sizes = tuple(value)
    if not sizes:
        raise ValueError("hidden_sizes must contain at least one layer")
    for index, size in enumerate(sizes):
        _positive_int(f"hidden_sizes[{index}]", size)
    return sizes


if torch is not None:

    class MaskedMultiCategorical:
        """A vectorized product of categorical distributions.

        Log probabilities and entropies are summed across independent policy
        dimensions, matching the joint probability of a MultiDiscrete action.
        """

        def __init__(
            self,
            logits: torch.Tensor,
            action_masks: torch.Tensor,
            *,
            validate: bool = True,
        ) -> None:
            if logits.ndim < 2 or logits.shape[-1] != 3:
                raise ValueError("logits must have shape [..., action_dims, 3]")
            if action_masks.shape != logits.shape:
                raise ValueError("action_masks must have the same shape as logits")
            if action_masks.dtype is not torch.bool:
                raise TypeError("action_masks must be a boolean tensor")
            if action_masks.device != logits.device:
                raise ValueError("action_masks and logits must be on the same device")
            if validate:
                if not bool(torch.isfinite(logits).all()):
                    raise ValueError("policy logits must be finite")
                if not bool(action_masks.any(dim=-1).all()):
                    raise ValueError(
                        "every action dimension must have at least one legal action"
                    )
            mask_value = torch.finfo(logits.dtype).min
            self.logits = logits.masked_fill(~action_masks, mask_value)
            self.action_masks = action_masks
            self._distribution = torch.distributions.Categorical(logits=self.logits)

        def sample(
            self, *, generator: torch.Generator | None = None,
        ) -> torch.Tensor:
            probabilities = self._distribution.probs
            flattened = probabilities.reshape(-1, 3)
            sampled = torch.multinomial(
                flattened, num_samples=1, replacement=True, generator=generator,
            )
            return sampled.reshape(probabilities.shape[:-1])

        def mode(self) -> torch.Tensor:
            return self.logits.argmax(dim=-1)

        def log_prob(
            self, actions: torch.Tensor, *, validate: bool = True,
        ) -> torch.Tensor:
            expected = self.logits.shape[:-1]
            if actions.shape != expected:
                raise ValueError(f"actions must have shape {expected}")
            if actions.dtype is not torch.long:
                raise TypeError("actions must be a torch.long tensor")
            if actions.device != self.logits.device:
                raise ValueError("actions and logits must be on the same device")
            if validate:
                if bool(((actions < 0) | (actions > 2)).any()):
                    raise ValueError("actions must use direction codes 0, 1, or 2")
                selected = self.action_masks.gather(-1, actions.unsqueeze(-1))
                if not bool(selected.all()):
                    raise ValueError("an action is forbidden by its action mask")
            return self._distribution.log_prob(actions).sum(dim=-1)

        def entropy(self) -> torch.Tensor:
            return self._distribution.entropy().sum(dim=-1)


    def _activation(name: str) -> type[nn.Module]:
        activations: dict[str, type[nn.Module]] = {
            "elu": nn.ELU,
            "gelu": nn.GELU,
            "relu": nn.ReLU,
            "silu": nn.SiLU,
            "tanh": nn.Tanh,
        }
        try:
            return activations[name]
        except KeyError as exc:
            choices = ", ".join(sorted(activations))
            raise ValueError(f"activation must be one of: {choices}") from exc


    def _mlp(
        input_dim: int,
        hidden_sizes: tuple[int, ...],
        activation: type[nn.Module],
    ) -> nn.Sequential:
        layers: list[nn.Module] = []
        previous = input_dim
        for size in hidden_sizes:
            layer = nn.Linear(previous, size)
            nn.init.orthogonal_(layer.weight, gain=2.0 ** 0.5)
            nn.init.zeros_(layer.bias)
            layers.extend((layer, activation()))
            previous = size
        return nn.Sequential(*layers)


    class ActorCriticNetwork(nn.Module):
        """Separate actor/critic MLP trunks with a flattened policy head."""

        def __init__(
            self,
            observation_dim: int,
            action_dims: int,
            *,
            hidden_sizes: Sequence[int] = (128, 128),
            activation: str = "tanh",
        ) -> None:
            super().__init__()
            self.observation_dim = _positive_int("observation_dim", observation_dim)
            self.action_dims = _positive_int("action_dims", action_dims)
            self.hidden_sizes = _hidden_sizes(hidden_sizes)
            if not isinstance(activation, str):
                raise TypeError("activation must be a string")
            activation_type = _activation(activation)
            self.activation_name = activation

            self.actor = _mlp(
                self.observation_dim, self.hidden_sizes, activation_type,
            )
            self.critic = _mlp(
                self.observation_dim, self.hidden_sizes, activation_type,
            )
            final_size = self.hidden_sizes[-1]
            self.policy_head = nn.Linear(final_size, self.action_dims * 3)
            self.value_head = nn.Linear(final_size, 1)
            nn.init.orthogonal_(self.policy_head.weight, gain=0.01)
            nn.init.zeros_(self.policy_head.bias)
            nn.init.orthogonal_(self.value_head.weight, gain=1.0)
            nn.init.zeros_(self.value_head.bias)

        def forward(
            self, observations: torch.Tensor,
        ) -> tuple[torch.Tensor, torch.Tensor]:
            if observations.ndim < 1 or observations.shape[-1] != self.observation_dim:
                raise ValueError(
                    "observations must have final dimension "
                    f"{self.observation_dim}"
                )
            if not observations.is_floating_point():
                raise TypeError("observations must be a floating-point tensor")
            actor_features = self.actor(observations)
            critic_features = self.critic(observations)
            logits = self.policy_head(actor_features).reshape(
                *observations.shape[:-1], self.action_dims, 3,
            )
            values = self.value_head(critic_features).squeeze(-1)
            return logits, values

        def distribution(
            self,
            observations: torch.Tensor,
            action_masks: torch.Tensor,
            *,
            validate: bool = True,
        ) -> tuple[MaskedMultiCategorical, torch.Tensor]:
            logits, values = self(observations)
            return MaskedMultiCategorical(
                logits, action_masks, validate=validate,
            ), values

        def act(
            self,
            observations: torch.Tensor,
            action_masks: torch.Tensor,
            *,
            deterministic: bool = False,
            generator: torch.Generator | None = None,
            validate: bool = True,
        ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            if not isinstance(deterministic, bool):
                raise TypeError("deterministic must be a boolean")
            distribution, values = self.distribution(
                observations, action_masks, validate=validate,
            )
            actions = distribution.mode() if deterministic else distribution.sample(
                generator=generator,
            )
            log_probs = distribution.log_prob(actions, validate=False)
            return actions, log_probs, values

        def evaluate_actions(
            self,
            observations: torch.Tensor,
            action_masks: torch.Tensor,
            actions: torch.Tensor,
            *,
            validate: bool = True,
        ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            distribution, values = self.distribution(
                observations, action_masks, validate=validate,
            )
            return (
                distribution.log_prob(actions, validate=validate),
                distribution.entropy(),
                values,
            )


else:

    class MaskedMultiCategorical:  # pragma: no cover - no-torch fallback
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            require_torch()


    class ActorCriticNetwork:  # pragma: no cover - no-torch fallback
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            require_torch()


__all__ = [
    "ActorCriticNetwork",
    "MaskedMultiCategorical",
    "require_torch",
]
