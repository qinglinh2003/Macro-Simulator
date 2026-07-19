"""Unit and synthetic-learning tests for the standalone SMDP PPO components."""
from __future__ import annotations

import copy
from io import BytesIO
import subprocess
import sys

import numpy as np
import pytest

from macro_sim.rl.algorithm import PPOConfig, SMDPPPO, resolve_device
from macro_sim.rl.buffer import RolloutBatch, SMDPRolloutBuffer


try:
    import torch
except ImportError:  # The base simulator intentionally does not require PyTorch.
    torch = None


requires_torch = pytest.mark.skipif(torch is None, reason="PyTorch is not installed")


def _all_legal(num_envs: int, action_dims: int) -> np.ndarray:
    return np.ones((num_envs, action_dims, 3), dtype=np.bool_)


def test_torch_is_an_optional_import_until_a_network_is_constructed():
    script = """
import sys
sys.modules['torch'] = None
from macro_sim.rl.algorithm import PPOConfig
from macro_sim.rl.buffer import SMDPRolloutBuffer
from macro_sim.rl.network import ActorCriticNetwork
assert PPOConfig(2, 1).observation_dim == 2
assert SMDPRolloutBuffer
try:
    ActorCriticNetwork(2, 1)
except ModuleNotFoundError as exc:
    assert 'PyTorch is required for RL training' in str(exc)
else:
    raise AssertionError('network construction unexpectedly succeeded')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"observation_dim": True}, TypeError),
        ({"action_dims": 0}, ValueError),
        ({"hidden_sizes": ()}, ValueError),
        ({"hidden_sizes": (16, 2.5)}, TypeError),
        ({"activation": "softplus"}, ValueError),
        ({"learning_rate": 0.0}, ValueError),
        ({"gamma": 1.01}, ValueError),
        ({"gae_lambda": float("nan")}, ValueError),
        ({"clip_range": 0.0}, ValueError),
        ({"value_clip_range": -0.1}, ValueError),
        ({"entropy_coef": -0.1}, ValueError),
        ({"batch_size": 2.5}, TypeError),
        ({"update_epochs": 0}, ValueError),
        ({"normalize_advantages": 1}, TypeError),
        ({"target_kl": 0.0}, ValueError),
        ({"seed": -1}, ValueError),
        ({"device": "cuda"}, ValueError),
        ({"deterministic_torch": 1}, TypeError),
    ],
)
def test_ppo_config_rejects_ambiguous_or_unsafe_values(overrides, error):
    values = {"observation_dim": 3, "action_dims": 2}
    values.update(overrides)
    with pytest.raises(error):
        PPOConfig(**values)


def test_ppo_config_canonicalizes_sequences_and_serializes():
    config = PPOConfig(3, 2, hidden_sizes=[32, 16], device="CPU")
    assert config.hidden_sizes == (32, 16)
    assert config.device == "cpu"
    assert config.to_dict()["hidden_sizes"] == (32, 16)


def test_smdp_gae_exponentiates_gamma_and_lambda_by_elapsed_ticks():
    buffer = SMDPRolloutBuffer(
        capacity=2,
        num_envs=1,
        observation_dim=2,
        action_dims=1,
        gamma=0.9,
        gae_lambda=0.8,
    )
    common = {
        "observations": np.zeros((1, 2), dtype=np.float32),
        "actions": np.ones((1, 1), dtype=np.int64),
        "action_masks": _all_legal(1, 1),
        "log_probs": np.zeros(1, dtype=np.float32),
        "truncated": np.zeros(1, dtype=np.bool_),
    }
    buffer.add(
        **common,
        rewards=np.array([3.0], dtype=np.float32),
        values=np.array([1.0], dtype=np.float32),
        next_values=np.array([2.0], dtype=np.float32),
        elapsed_ticks=np.array([2], dtype=np.int64),
        terminated=np.zeros(1, dtype=np.bool_),
    )
    buffer.add(
        **common,
        rewards=np.array([4.0], dtype=np.float32),
        values=np.array([2.0], dtype=np.float32),
        next_values=np.array([100.0], dtype=np.float32),
        elapsed_ticks=np.array([1], dtype=np.int64),
        terminated=np.ones(1, dtype=np.bool_),
    )

    buffer.compute_returns_and_advantages()

    final_advantage = 4.0 - 2.0
    first_delta = 3.0 + (0.9**2) * 2.0 - 1.0
    first_advantage = first_delta + (0.9**2) * (0.8**2) * final_advantage
    np.testing.assert_allclose(
        buffer.advantages[:2, 0],
        [first_advantage, final_advantage],
        rtol=1.0e-6,
    )
    np.testing.assert_allclose(
        buffer.returns[:2, 0],
        [first_advantage + 1.0, final_advantage + 2.0],
        rtol=1.0e-6,
    )


def test_terminal_does_not_bootstrap_but_truncation_does_and_both_cut_trace():
    buffer = SMDPRolloutBuffer(
        capacity=1,
        num_envs=2,
        observation_dim=1,
        action_dims=1,
        gamma=0.9,
        gae_lambda=0.8,
    )
    buffer.add(
        observations=np.zeros((2, 1), dtype=np.float32),
        actions=np.ones((2, 1), dtype=np.int64),
        action_masks=_all_legal(2, 1),
        rewards=np.ones(2, dtype=np.float32),
        values=np.zeros(2, dtype=np.float32),
        log_probs=np.zeros(2, dtype=np.float32),
        next_values=np.full(2, 10.0, dtype=np.float32),
        elapsed_ticks=np.full(2, 2, dtype=np.int64),
        terminated=np.array([True, False]),
        truncated=np.array([False, True]),
    )
    buffer.compute_returns_and_advantages()
    np.testing.assert_allclose(buffer.advantages[0], [1.0, 1.0 + 0.9**2 * 10.0])


def test_buffer_rejects_illegal_action_and_non_integer_elapsed_ticks():
    buffer = SMDPRolloutBuffer(
        capacity=1,
        num_envs=1,
        observation_dim=1,
        action_dims=1,
        gamma=0.9,
        gae_lambda=0.8,
    )
    kwargs = {
        "observations": np.zeros((1, 1), dtype=np.float32),
        "actions": np.array([[2]], dtype=np.int64),
        "action_masks": np.array([[[True, True, False]]]),
        "rewards": np.zeros(1, dtype=np.float32),
        "values": np.zeros(1, dtype=np.float32),
        "log_probs": np.zeros(1, dtype=np.float32),
        "next_values": np.zeros(1, dtype=np.float32),
        "elapsed_ticks": np.ones(1, dtype=np.int64),
        "terminated": np.zeros(1, dtype=np.bool_),
        "truncated": np.zeros(1, dtype=np.bool_),
    }
    with pytest.raises(ValueError, match="forbidden"):
        buffer.add(**kwargs)
    kwargs["actions"] = np.ones((1, 1), dtype=np.int64)
    kwargs["elapsed_ticks"] = np.ones(1, dtype=np.float32)
    with pytest.raises(TypeError, match="positive integers"):
        buffer.add(**kwargs)


@requires_torch
def test_masked_joint_distribution_is_vectorized_and_never_samples_illegal_codes():
    from macro_sim.rl.network import MaskedMultiCategorical

    logits = torch.zeros((512, 3, 3), dtype=torch.float32)
    masks = torch.tensor(
        [[[False, True, False], [True, False, True], [True, False, False]]]
    ).expand(512, -1, -1)
    distribution = MaskedMultiCategorical(logits, masks)
    actions = distribution.sample(generator=torch.Generator().manual_seed(7))

    assert actions.shape == (512, 3)
    assert torch.all(actions[:, 0] == 1)
    assert torch.all((actions[:, 1] == 0) | (actions[:, 1] == 2))
    assert torch.all(actions[:, 2] == 0)
    assert distribution.log_prob(actions).shape == (512,)
    assert distribution.entropy().shape == (512,)
    with pytest.raises(ValueError, match="at least one legal"):
        MaskedMultiCategorical(logits[:1], torch.zeros_like(masks[:1]))


@requires_torch
def test_seed_controls_initialization_sampling_and_minibatch_streams():
    config = PPOConfig(
        3, 2, hidden_sizes=(8,), batch_size=4, update_epochs=1, seed=912,
    )
    first = SMDPPPO(config)
    second = SMDPPPO(config)
    for first_parameter, second_parameter in zip(
        first.network.parameters(), second.network.parameters(), strict=True,
    ):
        torch.testing.assert_close(first_parameter, second_parameter)

    observations = np.zeros((16, 3), dtype=np.float32)
    masks = _all_legal(16, 2)
    first_actions, first_log_probs, first_values = first.act(observations, masks)
    second_actions, second_log_probs, second_values = second.act(observations, masks)
    np.testing.assert_array_equal(first_actions, second_actions)
    np.testing.assert_allclose(first_log_probs, second_log_probs)
    np.testing.assert_allclose(first_values, second_values)
    np.testing.assert_array_equal(
        first._minibatch_rng.permutation(20),
        second._minibatch_rng.permutation(20),
    )


@requires_torch
def test_weights_only_resume_restores_optimizer_and_both_rng_streams():
    config = PPOConfig(
        2,
        2,
        hidden_sizes=(8,),
        learning_rate=1.0e-3,
        batch_size=4,
        update_epochs=2,
        seed=44,
    )
    source = SMDPPPO(config)
    observations = np.asarray([
        [1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0],
        [1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0],
    ], dtype=np.float32)
    masks = _all_legal(len(observations), 2)
    actions, log_probs, values = source.act(observations, masks)
    targets = np.asarray([[0, 2], [2, 0]] * 4, dtype=np.int64)
    rewards = ((actions == targets).mean(axis=1) * 2.0 - 1.0).astype(np.float32)
    initial_batch = RolloutBatch(
        observations=observations,
        actions=actions,
        action_masks=masks,
        old_log_probs=log_probs,
        old_values=values,
        returns=rewards,
        advantages=rewards - values,
        elapsed_ticks=np.arange(1, 9, dtype=np.int64),
    )
    source.update(initial_batch)

    checkpoint = source.state_dict()
    stream = BytesIO()
    torch.save(checkpoint, stream)
    stream.seek(0)
    weights_only_state = torch.load(
        stream, map_location="cpu", weights_only=True,
    )
    restored = SMDPPPO(config)
    restored.load_state_dict(weights_only_state)

    for source_parameter, restored_parameter in zip(
        source.network.parameters(), restored.network.parameters(), strict=True,
    ):
        torch.testing.assert_close(source_parameter, restored_parameter, rtol=0, atol=0)
    source_actions, source_log_probs, source_values = source.act(observations, masks)
    restored_actions, restored_log_probs, restored_values = restored.act(
        observations, masks,
    )
    np.testing.assert_array_equal(source_actions, restored_actions)
    np.testing.assert_allclose(source_log_probs, restored_log_probs, rtol=0, atol=0)
    np.testing.assert_allclose(source_values, restored_values, rtol=0, atol=0)

    continuation = RolloutBatch(
        observations=observations,
        actions=source_actions,
        action_masks=masks,
        old_log_probs=source_log_probs,
        old_values=source_values,
        returns=rewards,
        advantages=rewards - source_values,
        elapsed_ticks=np.arange(8, 0, -1, dtype=np.int64),
    )
    source_stats = source.update(continuation)
    restored_stats = restored.update(continuation)
    assert source_stats.to_dict() == restored_stats.to_dict()
    for source_parameter, restored_parameter in zip(
        source.network.parameters(), restored.network.parameters(), strict=True,
    ):
        torch.testing.assert_close(source_parameter, restored_parameter, rtol=0, atol=0)
    np.testing.assert_array_equal(
        source._minibatch_rng.permutation(32),
        restored._minibatch_rng.permutation(32),
    )


@requires_torch
def test_resume_rejects_config_and_shape_drift_without_mutating_network():
    config = PPOConfig(2, 1, hidden_sizes=(8,), seed=21)
    learner = SMDPPPO(config)
    checkpoint = learner.state_dict()
    before = {
        name: tensor.clone() for name, tensor in learner.network.state_dict().items()
    }

    wrong_config = copy.deepcopy(checkpoint)
    wrong_config["config"]["gamma"] = 0.5
    with pytest.raises(ValueError, match="config differs"):
        learner.load_state_dict(wrong_config)

    wrong_shape = copy.deepcopy(checkpoint)
    wrong_shape["network"]["policy_head.weight"] = wrong_shape[
        "network"
    ]["policy_head.weight"][:-1]
    with pytest.raises(ValueError, match="shape must be"):
        learner.load_state_dict(wrong_shape)

    unsafe = copy.deepcopy(checkpoint)
    unsafe["minibatch_rng"]["unsafe"] = object()
    with pytest.raises(TypeError, match="unsupported checkpoint type"):
        learner.load_state_dict(unsafe)

    for name, tensor in learner.network.state_dict().items():
        torch.testing.assert_close(tensor, before[name], rtol=0, atol=0)


@requires_torch
def test_cpu_and_mps_device_selection_is_explicit():
    assert resolve_device("cpu").type == "cpu"
    auto = resolve_device("auto")
    assert auto.type in {"cpu", "mps"}
    if torch.backends.mps.is_available():
        learner = SMDPPPO(
            PPOConfig(2, 1, hidden_sizes=(4,), device="mps", seed=3)
        )
        assert next(learner.network.parameters()).device.type == "mps"
        action = learner.predict(
            np.zeros(2, dtype=np.float32),
            np.ones((1, 3), dtype=np.bool_),
        )
        assert action.shape == (1,)
    else:
        with pytest.raises(RuntimeError, match="unavailable"):
            resolve_device("mps")


@requires_torch
def test_ppo_learns_a_masked_synthetic_policy():
    """The policy should beat uniform exploration on a contextual bandit."""
    sample_count = 256
    config = PPOConfig(
        observation_dim=2,
        action_dims=2,
        hidden_sizes=(32,),
        learning_rate=3.0e-3,
        gamma=0.99,
        gae_lambda=0.95,
        value_clip_range=None,
        entropy_coef=0.005,
        batch_size=128,
        update_epochs=4,
        seed=11,
        device="cpu",
    )
    learner = SMDPPPO(config)
    rng = np.random.default_rng(5)
    mean_rewards: list[float] = []
    last_stats = None

    for _iteration in range(10):
        contexts = rng.integers(0, 2, size=sample_count)
        observations = np.eye(2, dtype=np.float32)[contexts]
        masks = _all_legal(sample_count, 2)
        masks[:, 1, 1] = False
        targets = np.stack((
            np.where(contexts == 0, 0, 2),
            np.where(contexts == 0, 2, 0),
        ), axis=1)
        actions, log_probs, values = learner.act(observations, masks)
        assert np.all(actions[:, 1] != 1)
        rewards = ((actions == targets).mean(axis=1) * 2.0 - 1.0).astype(
            np.float32,
        )
        mean_rewards.append(float(rewards.mean()))

        rollout = SMDPRolloutBuffer(
            capacity=1,
            num_envs=sample_count,
            observation_dim=2,
            action_dims=2,
            gamma=config.gamma,
            gae_lambda=config.gae_lambda,
        )
        rollout.add(
            observations=observations,
            actions=actions,
            action_masks=masks,
            rewards=rewards,
            values=values,
            log_probs=log_probs,
            next_values=np.zeros(sample_count, dtype=np.float32),
            elapsed_ticks=rng.integers(
                1, 5, size=sample_count, dtype=np.int64,
            ),
            terminated=np.ones(sample_count, dtype=np.bool_),
            truncated=np.zeros(sample_count, dtype=np.bool_),
        )
        last_stats = learner.update(rollout)

    evaluation_observations = np.eye(2, dtype=np.float32)
    evaluation_masks = _all_legal(2, 2)
    evaluation_masks[:, 1, 1] = False
    learned_actions = learner.predict(
        evaluation_observations,
        evaluation_masks,
        deterministic=True,
    )
    np.testing.assert_array_equal(learned_actions, [[0, 2], [2, 0]])
    assert np.mean(mean_rewards[-3:]) > np.mean(mean_rewards[:3]) + 0.5
    assert last_stats is not None
    assert last_stats.samples == sample_count
    assert last_stats.minibatches == config.update_epochs * 2
    assert np.isfinite(np.asarray(list(last_stats.to_dict().values()), dtype=float)).all()


def test_flattened_batch_validation_rejects_masked_action():
    batch = RolloutBatch(
        observations=np.zeros((1, 2), dtype=np.float32),
        actions=np.array([[2]], dtype=np.int64),
        action_masks=np.array([[[True, True, False]]]),
        old_log_probs=np.zeros(1, dtype=np.float32),
        old_values=np.zeros(1, dtype=np.float32),
        returns=np.zeros(1, dtype=np.float32),
        advantages=np.zeros(1, dtype=np.float32),
        elapsed_ticks=np.ones(1, dtype=np.int64),
    )
    with pytest.raises(ValueError, match="forbidden"):
        batch.validate(observation_dim=2, action_dims=1)
