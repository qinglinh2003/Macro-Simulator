#!/usr/bin/env python3
"""Cross-language acceptance panel for deterministic ``.msrl`` v1 inference."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

import numpy as np


FLOAT32_ATOL = 2.0e-5
FLOAT32_RTOL = 2.0e-5
FLOAT32_PROBABILITY_ATOL = 2.0e-7
FLOAT64_ATOL = 1.0e-12
FLOAT64_RTOL = 1.0e-10


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    return parser.parse_args()


def _assert_close(
    label: str,
    expected: np.ndarray,
    actual: object,
    *,
    atol: float,
    rtol: float,
) -> None:
    received = np.asarray(actual, dtype=np.float64)
    if received.shape != expected.shape:
        raise AssertionError(
            f"{label} shape differs: {received.shape} != {expected.shape}"
        )
    np.testing.assert_allclose(
        received,
        np.asarray(expected, dtype=np.float64),
        atol=atol,
        rtol=rtol,
        err_msg=label,
    )


def _normalization(policy, observation: np.ndarray) -> np.ndarray:
    value = np.asarray(observation, dtype=policy.dtype)
    value = (value - policy.input_mean) / policy.input_scale
    if policy.input_clip is not None:
        value = np.clip(value, -policy.input_clip, policy.input_clip)
    return np.asarray(value, dtype=policy.dtype)


def _write_single_layer_artifact(
    path: Path,
    source_policy,
    *,
    biases: tuple[float, float, float],
    deterministic: bool,
) -> None:
    from macro_sim.rl.artifact import save_artifact
    from macro_sim.rl.model import NumpyMLPPolicy

    dtype = source_policy.dtype
    policy = NumpyMLPPolicy(
        source_policy.context_codec,
        source_policy.action_codec,
        [
            np.zeros(
                (3, source_policy.context_codec.observation_dim),
                dtype=dtype,
            )
        ],
        [np.asarray(biases, dtype=dtype)],
        input_mean=np.zeros(
            source_policy.context_codec.observation_dim, dtype=dtype
        ),
        input_scale=np.ones(
            source_policy.context_codec.observation_dim, dtype=dtype
        ),
        deterministic=deterministic,
        temperature=1.0,
    )
    save_artifact(path, policy, metadata={"fixture": path.stem})


def main() -> int:
    args = _arguments()
    sys.path.insert(0, str(args.native_dir.resolve()))
    sys.path.insert(0, str(args.source_dir.resolve()))

    import _native
    from macro_sim.rl.artifact import load_artifact

    python_policy = load_artifact(args.artifact)
    native_policy = _native.NativePolicyArtifact.load_file(str(args.artifact))
    info = native_policy.info
    if info["inference_capability"] != "msrl_v1_deterministic_inference":
        raise AssertionError("native deterministic inference capability is absent")
    if not info["deterministic"]:
        raise AssertionError("the built-in artifact must be deterministic")
    if info["action_dimension"] != python_policy.action_codec.action_dim:
        raise AssertionError("action dimension differs")
    if info["observation_dimension"] != python_policy.context_codec.observation_dim:
        raise AssertionError("observation dimension differs")

    is_float32 = python_policy.dtype == np.dtype("float32")
    atol = FLOAT32_ATOL if is_float32 else FLOAT64_ATOL
    rtol = FLOAT32_RTOL if is_float32 else FLOAT64_RTOL
    probability_atol = (
        FLOAT32_PROBABILITY_ATOL if is_float32 else FLOAT64_ATOL
    )
    dimension = python_policy.context_codec.observation_dim
    rng = np.random.default_rng(0x4D53524C)
    vectors = (
        np.zeros(dimension, dtype=np.float64),
        np.ones(dimension, dtype=np.float64),
        np.linspace(-2.0, 2.0, dimension, dtype=np.float64),
        np.linspace(-100.0, 100.0, dimension, dtype=np.float64),
        rng.normal(0.0, 3.0, dimension),
    )
    masks = (
        np.ones((python_policy.action_codec.action_dim, 3), dtype=np.bool_),
        np.tile(
            np.asarray([False, True, False], dtype=np.bool_),
            (python_policy.action_codec.action_dim, 1),
        ),
        np.tile(
            np.asarray([True, False, True], dtype=np.bool_),
            (python_policy.action_codec.action_dim, 1),
        ),
    )

    for vector_index, observation in enumerate(vectors):
        normalized = _normalization(python_policy, observation)
        _assert_close(
            f"normalized input vector {vector_index}",
            normalized,
            native_policy.normalized_input(observation.tolist()),
            atol=atol,
            rtol=rtol,
        )
        python_logits = python_policy._forward_vector(observation)
        native_logits = np.asarray(
            native_policy.logits(observation.tolist()), dtype=np.float64
        ).reshape(python_logits.shape)
        _assert_close(
            f"logits vector {vector_index}",
            python_logits,
            native_logits,
            atol=atol,
            rtol=rtol,
        )
        for mask_index, mask in enumerate(masks):
            python_probabilities = python_policy._masked_probabilities(
                python_logits, mask
            )
            native_probabilities = np.asarray(
                native_policy.probabilities(
                    observation.tolist(),
                    mask.astype(np.uint8).reshape(-1).tolist(),
                ),
                dtype=np.float64,
            ).reshape(python_probabilities.shape)
            _assert_close(
                f"probabilities vector {vector_index} mask {mask_index}",
                python_probabilities,
                native_probabilities,
                atol=probability_atol,
                rtol=rtol,
            )
            if not np.array_equal(
                native_probabilities[~mask],
                np.zeros(np.count_nonzero(~mask), dtype=np.float64),
            ):
                raise AssertionError("native inference widened the action mask")
            python_codes = python_policy._sample_probabilities(
                python_probabilities, deterministic=True
            )
            native_codes = np.asarray(
                native_policy.predict_codes(
                    observation.tolist(),
                    mask.astype(np.uint8).reshape(-1).tolist(),
                ),
                dtype=np.int64,
            )
            if not np.array_equal(python_codes, native_codes):
                raise AssertionError(
                    f"action codes differ for vector {vector_index}, "
                    f"mask {mask_index}: {python_codes} != {native_codes}"
                )

    with tempfile.TemporaryDirectory(prefix="macro-sim-m11-artifact-") as temp:
        root = Path(temp)
        tie_path = root / "exact-tie.msrl"
        _write_single_layer_artifact(
            tie_path,
            python_policy,
            biases=(0.0, 0.0, -1.0),
            deterministic=True,
        )
        tie_native = _native.NativePolicyArtifact.load_file(str(tie_path))
        tie_codes = tie_native.predict_codes(
            np.zeros(dimension).tolist(), [1, 1, 1]
        )
        if tie_codes != [0]:
            raise AssertionError("exact deterministic tie did not choose code zero")

        near_tie_path = root / "near-tie.msrl"
        _write_single_layer_artifact(
            near_tie_path,
            python_policy,
            biases=(0.0, FLOAT32_ATOL * 2.0, -1.0),
            deterministic=True,
        )
        near_tie_python = load_artifact(near_tie_path)
        near_tie_native = _native.NativePolicyArtifact.load_file(
            str(near_tie_path)
        )
        observation = np.zeros(dimension)
        expected_codes = near_tie_python.predict(
            observation,
            action_mask=np.ones((1, 3), dtype=np.bool_),
            deterministic=True,
        )
        actual_codes = near_tie_native.predict_codes(
            observation.tolist(), [1, 1, 1]
        )
        if expected_codes.tolist() != actual_codes:
            raise AssertionError("resolved near-tie action differs")

        stochastic_path = root / "stochastic-v1.msrl"
        _write_single_layer_artifact(
            stochastic_path,
            python_policy,
            biases=(0.0, 0.0, -1.0),
            deterministic=False,
        )
        try:
            _native.NativePolicyArtifact.load_file(str(stochastic_path))
        except RuntimeError as exc:
            if not str(exc).startswith("unsupported:"):
                raise AssertionError(
                    "stochastic v1 did not return a typed capability error"
                ) from exc
        else:
            raise AssertionError("native inference accepted stochastic msrl v1")

    print(
        "M11 artifact golden passed: "
        f"{len(vectors)} vectors, {len(masks)} masks, tie fixtures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
