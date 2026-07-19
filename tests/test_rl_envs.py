from __future__ import annotations

import pickle

import numpy as np
import pytest

from macro_sim.rl.envs import (
    FISCAL_STABILIZATION_TASK,
    FiscalStabilizationConfig,
    FiscalStabilizationEnvFactory,
)


def _small_config() -> FiscalStabilizationConfig:
    return FiscalStabilizationConfig(
        horizon_ticks=30,
        decision_period_ticks=15,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
    )


def test_fiscal_environment_config_is_strict_and_round_trips():
    config = _small_config()
    assert FiscalStabilizationConfig.from_dict(config.to_dict()) == config
    assert config.task_id == FISCAL_STABILIZATION_TASK
    with pytest.raises(ValueError, match="keys differ"):
        FiscalStabilizationConfig.from_dict({"horizon_ticks": 30})
    with pytest.raises(ValueError, match="cannot exceed"):
        FiscalStabilizationConfig(horizon_ticks=10, decision_period_ticks=11)
    with pytest.raises(ValueError, match="<= 0.30"):
        FiscalStabilizationConfig(initial_deficit_target=0.31)


def test_environment_factory_is_pickle_safe_and_uses_deployable_contract():
    factory = pickle.loads(pickle.dumps(FiscalStabilizationEnvFactory(_small_config())))
    env = factory(501)
    observation, info = env.reset(seed=501)

    assert env.action_levers == ("gov_deficit_target",)
    assert env.action_dimensions == (("gov_deficit_target", None),)
    assert observation.shape == (env.context_codec.observation_dim,)
    assert observation.shape == env.observation_space.shape
    assert info["action_mask"].shape == (1, 3)
    assert np.all(info["action_mask"][:, 1])
    with pytest.raises(ValueError, match="outside.*action_levers"):
        env.action_to_proposal({"benefit_replacement": 0.5})

    next_observation, reward, terminated, truncated, next_info = env.step(
        np.asarray((2,), dtype=np.int64),
    )
    assert next_observation.shape == observation.shape
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert next_info["elapsed_ticks"] == 15
    _terminal_observation, _reward, terminated, truncated, terminal_info = env.step(
        np.asarray((2,), dtype=np.int64),
    )
    assert terminated
    assert not truncated
    assert terminal_info["terminal_observation"] is True
    assert terminal_info["reward_time_normalization"] == "per_tick"


def test_real_environment_is_reproducible_for_seed_and_actions():
    factory = FiscalStabilizationEnvFactory(_small_config())
    traces = []
    for _ in range(2):
        env = factory(502)
        observation, _ = env.reset(seed=999)
        episode = [observation.copy()]
        done = False
        while not done:
            observation, reward, terminated, truncated, _ = env.step(
                np.asarray((2,), dtype=np.int64),
            )
            episode.append((observation.copy(), reward))
            done = terminated or truncated
        traces.append(episode)

    assert len(traces[0]) == len(traces[1])
    for left, right in zip(traces[0], traces[1], strict=True):
        if isinstance(left, np.ndarray):
            np.testing.assert_array_equal(left, right)
        else:
            np.testing.assert_array_equal(left[0], right[0])
            assert left[1] == right[1]
