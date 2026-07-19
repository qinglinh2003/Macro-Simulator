"""Portable NumPy inference policy for trained controller models.

Training is free to use PyTorch or another framework.  Deployment intentionally
uses a small, fixed MLP interpreter whose parameters are plain numeric arrays;
loading a model never imports or executes training-framework code.
"""
from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Any, Mapping, Sequence

import numpy as np

from macro_sim.controllers.protocol import DecisionContext, PolicyAction

from .codec import ContextCodec, DirectionalActionCodec


MODEL_SCHEMA_VERSION = 1
MODEL_ARCHITECTURE = "numpy_mlp_categorical_v1"
SUPPORTED_ACTIVATIONS = frozenset({"tanh", "relu"})
SUPPORTED_DTYPES = frozenset({"float32", "float64"})


def _finite(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def _seed(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError("seed must be an integer")
    result = int(value)
    if not 0 <= result < 2 ** 64:
        raise ValueError("seed must be in [0, 2**64)")
    return result


def _numeric_array(
    name: str,
    value: Any,
    *,
    ndim: int,
    dtype: np.dtype | None = None,
) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions, got {raw.ndim}")
    if raw.dtype.name not in SUPPORTED_DTYPES:
        raise TypeError(f"{name} dtype must be float32 or float64")
    if dtype is not None and raw.dtype != dtype:
        raise TypeError(f"{name} dtype must be {dtype.name}, got {raw.dtype.name}")
    if not np.all(np.isfinite(raw)):
        raise ValueError(f"{name} contains NaN or Infinity")
    result = np.array(raw, dtype=raw.dtype, order="C", copy=True)
    result.setflags(write=False)
    return result


class NumpyMLPPolicy:
    """A safe inference-only multi-categorical policy.

    Weight matrices use the PyTorch-compatible ``(out_features, in_features)``
    layout.  The final layer has ``3 * action_dim`` outputs ordered as
    ``[down, hold, up]`` for each action dimension.

    The object is directly callable with a ``DecisionContext`` and therefore can
    be assigned to ``RLOccupant.policy``.  NumPy's ``Generator`` is pickleable;
    checkpointing a stochastic occupant preserves its exact next sample.
    """

    def __init__(
        self,
        context_codec: ContextCodec,
        action_codec: DirectionalActionCodec,
        weights: Sequence[np.ndarray],
        biases: Sequence[np.ndarray],
        *,
        input_mean: np.ndarray | None = None,
        input_scale: np.ndarray | None = None,
        activation: str = "tanh",
        input_clip: float | None = 20.0,
        deterministic: bool = True,
        seed: int = 0,
        temperature: float = 1.0,
    ) -> None:
        if not isinstance(context_codec, ContextCodec):
            raise TypeError("context_codec must be a ContextCodec")
        if not isinstance(action_codec, DirectionalActionCodec):
            raise TypeError("action_codec must be a DirectionalActionCodec")
        action_codec.verify_context_codec(context_codec)
        context_codec.verify_runtime_registry()
        if activation not in SUPPORTED_ACTIVATIONS:
            raise ValueError(f"unsupported activation {activation!r}")
        if not isinstance(deterministic, bool):
            raise TypeError("deterministic must be a bool")
        checked_seed = _seed(seed)
        checked_temperature = _finite("temperature", temperature, positive=True)
        if input_clip is not None:
            input_clip = _finite("input_clip", input_clip, positive=True)

        raw_weights = tuple(weights)
        raw_biases = tuple(biases)
        if not raw_weights:
            raise ValueError("model must contain at least one dense layer")
        if len(raw_weights) != len(raw_biases):
            raise ValueError("weights and biases must have the same layer count")
        first_raw = np.asarray(raw_weights[0])
        if first_raw.dtype.name not in SUPPORTED_DTYPES:
            raise TypeError("model dtype must be float32 or float64")
        dtype = first_raw.dtype
        checked_weights: list[np.ndarray] = []
        checked_biases: list[np.ndarray] = []
        previous = context_codec.observation_dim
        for index, (weight, bias) in enumerate(zip(
            raw_weights, raw_biases, strict=True,
        )):
            checked_weight = _numeric_array(
                f"layer {index} weight", weight, ndim=2, dtype=dtype,
            )
            checked_bias = _numeric_array(
                f"layer {index} bias", bias, ndim=1, dtype=dtype,
            )
            if checked_weight.shape[1] != previous:
                raise ValueError(
                    f"layer {index} expects {checked_weight.shape[1]} inputs, "
                    f"contract requires {previous}"
                )
            if checked_weight.shape[0] != checked_bias.shape[0]:
                raise ValueError(
                    f"layer {index} weight/bias output dimensions differ"
                )
            if checked_weight.shape[0] == 0:
                raise ValueError(f"layer {index} has zero outputs")
            previous = checked_weight.shape[0]
            checked_weights.append(checked_weight)
            checked_biases.append(checked_bias)
        expected_output = action_codec.action_dim * 3
        if previous != expected_output:
            raise ValueError(
                f"model output dimension must be {expected_output}, got {previous}"
            )

        if input_mean is None:
            input_mean = np.zeros(context_codec.observation_dim, dtype=dtype)
        if input_scale is None:
            input_scale = np.ones(context_codec.observation_dim, dtype=dtype)
        checked_mean = _numeric_array(
            "input_mean", input_mean, ndim=1, dtype=dtype,
        )
        checked_scale = _numeric_array(
            "input_scale", input_scale, ndim=1, dtype=dtype,
        )
        expected_input_shape = (context_codec.observation_dim,)
        if checked_mean.shape != expected_input_shape:
            raise ValueError(
                f"input_mean shape must be {expected_input_shape}, "
                f"got {checked_mean.shape}"
            )
        if checked_scale.shape != expected_input_shape:
            raise ValueError(
                f"input_scale shape must be {expected_input_shape}, "
                f"got {checked_scale.shape}"
            )
        if np.any(checked_scale <= 0.0):
            raise ValueError("input_scale entries must all be > 0")

        self.context_codec = context_codec
        self.action_codec = action_codec
        self.weights = tuple(checked_weights)
        self.biases = tuple(checked_biases)
        self.input_mean = checked_mean
        self.input_scale = checked_scale
        self.activation = activation
        self.input_clip = input_clip
        self.deterministic = deterministic
        self.seed = checked_seed
        self.temperature = checked_temperature
        self._rng = np.random.default_rng(checked_seed)

    @property
    def dtype(self) -> np.dtype:
        return self.weights[0].dtype

    @property
    def layer_shapes(self) -> tuple[tuple[int, int], ...]:
        return tuple(tuple(int(value) for value in item.shape) for item in self.weights)

    def reseed(self, seed: int | None = None) -> None:
        """Reset stochastic inference without touching weights or simulator RNG."""
        checked = self.seed if seed is None else _seed(seed)
        self.seed = checked
        self._rng = np.random.default_rng(checked)

    def __call__(self, context: DecisionContext) -> tuple[PolicyAction, ...]:
        codes = self.predict_codes(context)
        # The model samples through its conservative pure-context mask.  Keep
        # decode tolerant because global joint constraints remain Coordinator
        # authority and can change between context creation and submission.
        return self.action_codec.decode(
            codes, context, context_codec=self.context_codec, strict=False,
        )

    def logits(self, context: DecisionContext) -> np.ndarray:
        return self._forward_vector(self.context_codec.encode(context))

    def _forward_vector(self, observation: Any) -> np.ndarray:
        try:
            raw = np.asarray(observation)
        except (TypeError, ValueError) as exc:
            raise ValueError("observation must be a flat numeric vector") from exc
        if raw.shape != (self.context_codec.observation_dim,):
            raise ValueError(
                "observation shape must be "
                f"{(self.context_codec.observation_dim,)}, got {raw.shape}"
            )
        if raw.dtype.kind not in {"i", "u", "f"} or raw.dtype.kind == "b":
            raise TypeError("observation must contain real numeric values")
        try:
            value = np.asarray(raw, dtype=self.dtype)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("observation cannot be represented by model dtype") from exc
        if not np.all(np.isfinite(value)):
            raise ValueError("observation contains NaN or Infinity")
        value = (value - self.input_mean) / self.input_scale
        if self.input_clip is not None:
            value = np.clip(value, -self.input_clip, self.input_clip)
        for index, (weight, bias) in enumerate(zip(
            self.weights, self.biases, strict=True,
        )):
            value = weight @ value + bias
            if index != len(self.weights) - 1:
                if self.activation == "tanh":
                    value = np.tanh(value)
                elif self.activation == "relu":
                    value = np.maximum(value, 0.0)
                else:  # constructor validation makes this unreachable
                    raise RuntimeError("model activation changed after validation")
        result = np.asarray(value, dtype=self.dtype).reshape(
            self.action_codec.action_dim, 3,
        )
        if not np.all(np.isfinite(result)):
            raise RuntimeError("model inference produced NaN or Infinity")
        result = np.array(result, copy=True, order="C")
        result.setflags(write=False)
        return result

    def predict(
        self,
        observation: Any,
        *,
        action_mask: Any,
        deterministic: bool = True,
    ) -> np.ndarray:
        """Evaluation/training-vector interface shared with benchmark policies."""
        if not isinstance(deterministic, bool):
            raise TypeError("deterministic must be a bool")
        logits = self._forward_vector(observation)
        mask = self._validate_action_mask(action_mask)
        probabilities = self._masked_probabilities(logits, mask)
        return self._sample_probabilities(probabilities, deterministic=deterministic)

    def action_probabilities(self, context: DecisionContext) -> np.ndarray:
        logits = self.logits(context)
        mask = self.action_codec.action_mask(
            context, context_codec=self.context_codec,
        )
        return self._masked_probabilities(logits, mask)

    def _validate_action_mask(self, action_mask: Any) -> np.ndarray:
        try:
            raw = np.asarray(action_mask)
        except (TypeError, ValueError) as exc:
            raise ValueError("action_mask must be a rectangular array") from exc
        expected = (self.action_codec.action_dim, 3)
        if raw.shape != expected:
            raise ValueError(f"action_mask shape must be {expected}, got {raw.shape}")
        if raw.dtype.kind == "b":
            result = np.asarray(raw, dtype=np.bool_)
        elif raw.dtype.kind in {"i", "u"} and np.all((raw == 0) | (raw == 1)):
            result = raw.astype(np.bool_, copy=False)
        else:
            raise TypeError("action_mask must contain boolean or integer 0/1 values")
        if not np.all(result.any(axis=1)):
            raise ValueError("every action dimension must permit at least one code")
        return result

    def _masked_probabilities(
        self, logits: np.ndarray, mask: np.ndarray,
    ) -> np.ndarray:
        logits = np.asarray(logits, dtype=np.float64)
        scaled = logits / self.temperature
        scaled = np.where(mask, scaled, -np.inf)
        maximum = np.max(scaled, axis=1, keepdims=True)
        exponentials = np.where(mask, np.exp(scaled - maximum), 0.0)
        totals = exponentials.sum(axis=1, keepdims=True)
        if np.any(~np.isfinite(totals)) or np.any(totals <= 0.0):
            raise RuntimeError("model produced an invalid categorical distribution")
        result = exponentials / totals
        if not np.all(np.isfinite(result)):
            raise RuntimeError("model produced non-finite action probabilities")
        result.setflags(write=False)
        return result

    def _sample_probabilities(
        self, probabilities: np.ndarray, *, deterministic: bool,
    ) -> np.ndarray:
        if deterministic:
            result = np.argmax(probabilities, axis=1).astype(np.int64, copy=False)
        else:
            result = np.asarray([
                self._rng.choice(3, p=row) for row in probabilities
            ], dtype=np.int64)
        result.setflags(write=False)
        return result

    def predict_codes(
        self,
        context: DecisionContext,
        *,
        deterministic: bool | None = None,
    ) -> np.ndarray:
        use_deterministic = self.deterministic if deterministic is None else deterministic
        if not isinstance(use_deterministic, bool):
            raise TypeError("deterministic override must be a bool or None")
        probabilities = self.action_probabilities(context)
        return self._sample_probabilities(
            probabilities, deterministic=use_deterministic,
        )

    @classmethod
    def from_actor_critic(
        cls,
        context_codec: ContextCodec,
        action_codec: DirectionalActionCodec,
        network: Any,
        *,
        input_mean: Any | None = None,
        input_scale: Any | None = None,
        input_clip: float | None = 20.0,
        deterministic: bool = True,
        seed: int = 0,
        temperature: float = 1.0,
    ) -> "NumpyMLPPolicy":
        """Export the repository's trusted PyTorch actor to portable NumPy.

        This helper is used at training/export time only.  Artifact loading never
        imports PyTorch and never deserializes a Python state dictionary.
        """
        if getattr(network, "observation_dim", None) != context_codec.observation_dim:
            raise ValueError("actor observation dimension differs from context codec")
        if getattr(network, "action_dims", None) != action_codec.action_dim:
            raise ValueError("actor action dimension differs from action codec")
        activation = getattr(network, "activation_name", None)
        if activation not in SUPPORTED_ACTIVATIONS:
            raise ValueError(
                f"actor activation {activation!r} is not portable; "
                f"choose one of {sorted(SUPPORTED_ACTIVATIONS)}"
            )

        def numpy_parameter(value: Any, name: str) -> np.ndarray:
            try:
                detached = value.detach().cpu().numpy()
            except AttributeError as exc:
                raise TypeError(f"{name} is not a tensor-like parameter") from exc
            return np.array(detached, copy=True, order="C")

        weights: list[np.ndarray] = []
        biases: list[np.ndarray] = []
        try:
            actor_modules = tuple(network.actor)
        except (AttributeError, TypeError) as exc:
            raise TypeError("network does not expose an iterable actor trunk") from exc
        for module in actor_modules:
            if not hasattr(module, "weight"):
                continue
            if not hasattr(module, "bias") or module.bias is None:
                raise ValueError("portable actor dense layers require a bias")
            weights.append(numpy_parameter(module.weight, "actor weight"))
            biases.append(numpy_parameter(module.bias, "actor bias"))
        try:
            policy_head = network.policy_head
            weights.append(numpy_parameter(policy_head.weight, "policy head weight"))
            biases.append(numpy_parameter(policy_head.bias, "policy head bias"))
        except AttributeError as exc:
            raise TypeError("network does not expose a policy_head") from exc

        dtype = weights[0].dtype if weights else np.dtype("float32")

        def optional_array(value: Any | None) -> np.ndarray | None:
            if value is None:
                return None
            if hasattr(value, "detach"):
                value = value.detach().cpu().numpy()
            return np.asarray(value, dtype=dtype)

        return cls(
            context_codec,
            action_codec,
            weights,
            biases,
            input_mean=optional_array(input_mean),
            input_scale=optional_array(input_scale),
            activation=activation,
            input_clip=input_clip,
            deterministic=deterministic,
            seed=seed,
            temperature=temperature,
        )

    def parameter_arrays(self) -> dict[str, np.ndarray]:
        """Return detached arrays for the safe artifact writer."""
        result = {
            "input_mean": np.array(self.input_mean, copy=True),
            "input_scale": np.array(self.input_scale, copy=True),
        }
        for index, (weight, bias) in enumerate(zip(
            self.weights, self.biases, strict=True,
        )):
            result[f"layer_{index}_weight"] = np.array(weight, copy=True)
            result[f"layer_{index}_bias"] = np.array(bias, copy=True)
        return result

    def model_spec(self) -> dict[str, Any]:
        arrays = self.parameter_arrays()
        return {
            "action_contract_hash": self.action_codec.contract_hash,
            "activation": self.activation,
            "architecture": MODEL_ARCHITECTURE,
            "context_contract_hash": self.context_codec.contract_hash,
            "deterministic": self.deterministic,
            "dtype": self.dtype.name,
            "input_clip": self.input_clip,
            "layer_count": len(self.weights),
            "parameter_specs": {
                name: {
                    "dtype": value.dtype.name,
                    "shape": list(value.shape),
                }
                for name, value in sorted(arrays.items())
            },
            "schema_version": MODEL_SCHEMA_VERSION,
            "seed": self.seed,
            "temperature": self.temperature,
        }

    @classmethod
    def from_spec_and_arrays(
        cls,
        context_codec: ContextCodec,
        action_codec: DirectionalActionCodec,
        spec: Mapping[str, Any],
        arrays: Mapping[str, np.ndarray],
        *,
        deterministic: bool | None = None,
        seed: int | None = None,
    ) -> "NumpyMLPPolicy":
        """Validated reconstruction hook used by :mod:`macro_sim.rl.artifact`."""
        expected_keys = {
            "action_contract_hash", "activation", "architecture",
            "context_contract_hash", "deterministic", "dtype", "input_clip",
            "layer_count", "parameter_specs", "schema_version", "seed",
            "temperature",
        }
        if not isinstance(spec, Mapping) or set(spec) != expected_keys:
            raise ValueError("model spec has missing or unknown fields")
        if spec["schema_version"] != MODEL_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported model schema_version {spec['schema_version']!r}"
            )
        if spec["architecture"] != MODEL_ARCHITECTURE:
            raise ValueError(f"unsupported model architecture {spec['architecture']!r}")
        if spec["context_contract_hash"] != context_codec.contract_hash:
            raise ValueError("model context contract hash mismatch")
        if spec["action_contract_hash"] != action_codec.contract_hash:
            raise ValueError("model action contract hash mismatch")
        layer_count = spec["layer_count"]
        if isinstance(layer_count, bool) or not isinstance(layer_count, Integral) \
                or layer_count < 1:
            raise ValueError("model layer_count must be a positive integer")
        parameter_specs = spec["parameter_specs"]
        if not isinstance(parameter_specs, Mapping):
            raise TypeError("model parameter_specs must be a mapping")
        expected_names = {"input_mean", "input_scale"}
        for index in range(int(layer_count)):
            expected_names.update({f"layer_{index}_weight", f"layer_{index}_bias"})
        if set(parameter_specs) != expected_names or set(arrays) != expected_names:
            raise ValueError("model parameter names do not match layer_count")
        dtype_name = spec["dtype"]
        if dtype_name not in SUPPORTED_DTYPES:
            raise ValueError(f"unsupported model dtype {dtype_name!r}")
        for name in sorted(expected_names):
            parameter_spec = parameter_specs[name]
            if not isinstance(parameter_spec, Mapping) or set(parameter_spec) != {
                "dtype", "shape",
            }:
                raise ValueError(f"parameter spec for {name!r} is malformed")
            shape = parameter_spec["shape"]
            if not isinstance(shape, list) or any(
                isinstance(value, bool) or not isinstance(value, Integral) or value < 0
                for value in shape
            ):
                raise ValueError(f"parameter shape for {name!r} is malformed")
            array = arrays[name]
            if array.dtype.name != parameter_spec["dtype"] \
                    or array.dtype.name != dtype_name:
                raise ValueError(f"parameter dtype mismatch for {name!r}")
            if list(array.shape) != [int(value) for value in shape]:
                raise ValueError(f"parameter shape mismatch for {name!r}")
        return cls(
            context_codec,
            action_codec,
            tuple(arrays[f"layer_{index}_weight"] for index in range(int(layer_count))),
            tuple(arrays[f"layer_{index}_bias"] for index in range(int(layer_count))),
            input_mean=arrays["input_mean"],
            input_scale=arrays["input_scale"],
            activation=spec["activation"],
            input_clip=spec["input_clip"],
            deterministic=spec["deterministic"] if deterministic is None else deterministic,
            seed=spec["seed"] if seed is None else seed,
            temperature=spec["temperature"],
        )
