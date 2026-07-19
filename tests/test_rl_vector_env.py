from __future__ import annotations

import os
import time

import numpy as np
import pytest

from macro_sim.rl.envs import (
    FiscalStabilizationConfig,
    FiscalStabilizationEnvFactory,
)
from macro_sim.rl.experiment import SynchronousEnvironmentBatch
from macro_sim.rl.vector_env import (
    RemoteEnvironmentError,
    SubprocessEnvironmentBatch,
)


class _SlowStepEnvironment:
    def reset(self, *, seed=None):
        return self._observation()

    def step(self, action):
        time.sleep(0.25)
        observation, info = self._observation()
        return observation, 0.0, False, False, info

    @staticmethod
    def _observation():
        return np.zeros(1, dtype=np.float64), {
            "action_mask": np.ones((1, 3), dtype=np.bool_),
            "elapsed_ticks": 1,
        }

    def close(self):
        return None


class _CrashOnStepEnvironment(_SlowStepEnvironment):
    def step(self, action):
        os._exit(23)


def _slow_factory(seed):
    return _SlowStepEnvironment()


def _crash_factory(seed):
    return _CrashOnStepEnvironment()


def _factory() -> FiscalStabilizationEnvFactory:
    return FiscalStabilizationEnvFactory(FiscalStabilizationConfig(
        horizon_ticks=30,
        decision_period_ticks=15,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
    ))


def test_subprocess_batch_matches_synchronous_real_engine_trace():
    seeds = (601, 602)
    with SynchronousEnvironmentBatch(_factory(), seeds) as synchronous, \
            SubprocessEnvironmentBatch(_factory(), seeds) as subprocess:
        left = synchronous.reset()
        right = subprocess.reset()
        np.testing.assert_array_equal(left.observations, right.observations)
        np.testing.assert_array_equal(left.action_masks, right.action_masks)

        actions = np.full((2, 1), 2, dtype=np.int64)
        left_step = synchronous.step(actions)
        right_step = subprocess.step(actions)
        np.testing.assert_array_equal(left_step.observations, right_step.observations)
        np.testing.assert_array_equal(left_step.action_masks, right_step.action_masks)
        np.testing.assert_array_equal(left_step.rewards, right_step.rewards)
        np.testing.assert_array_equal(left_step.elapsed_ticks, right_step.elapsed_ticks)
        np.testing.assert_array_equal(left_step.terminated, right_step.terminated)
        np.testing.assert_array_equal(left_step.truncated, right_step.truncated)

        # Finish the fixed horizon, then reuse the same worker processes for a
        # fresh seed set and compare with newly built synchronous environments.
        synchronous.step(actions)
        subprocess.step(actions)
        new_seeds = (611, 612)
        with SynchronousEnvironmentBatch(_factory(), new_seeds) as fresh:
            expected = fresh.reset()
            rebuilt = subprocess.reseed(new_seeds)
            np.testing.assert_array_equal(
                rebuilt.observations, expected.observations,
            )
            np.testing.assert_array_equal(
                rebuilt.action_masks, expected.action_masks,
            )


def test_subprocess_batch_requires_reset_and_exact_action_count():
    batch = SubprocessEnvironmentBatch(_factory(), (603,))
    try:
        with pytest.raises(RuntimeError, match=r"reset\(\)"):
            batch.step((np.asarray((1,)),))
        batch.reset()
        with pytest.raises(ValueError, match="actions length"):
            batch.step(())
    finally:
        batch.close()
        batch.close()


def test_subprocess_training_mode_prunes_large_debug_infos():
    with SubprocessEnvironmentBatch(
        _factory(), (604,), compact_infos=True,
    ) as batch:
        reset = batch.reset()
        assert set(reset.infos[0]) == {
            "action_mask", "elapsed_ticks", "reward_time_normalization",
        }
        transition = batch.step((np.asarray((1,)),))
        assert set(transition.infos[0]) == {
            "action_mask", "elapsed_ticks", "reward_time_normalization",
        }


def test_subprocess_timeout_is_reported_and_close_reaps_worker():
    batch = SubprocessEnvironmentBatch(
        _slow_factory, (605,), timeout_seconds=5.0,
    )
    processes = batch._processes
    connections = batch._connections
    try:
        batch.reset()
        # Keep process startup out of this deliberately short response timeout.
        batch.timeout_seconds = 0.05
        with pytest.raises(RemoteEnvironmentError, match="timed out"):
            batch.step((np.asarray((1,)),))
    finally:
        batch.close()

    assert all(not process.is_alive() for process in processes)
    assert all(connection.closed for connection in connections)
    batch.close()


def test_subprocess_worker_eof_is_reported_and_close_reaps_worker():
    batch = SubprocessEnvironmentBatch(
        _crash_factory, (606,), timeout_seconds=5.0,
    )
    processes = batch._processes
    connections = batch._connections
    try:
        batch.reset()
        with pytest.raises(
            RemoteEnvironmentError, match="exited without a response",
        ):
            batch.step((np.asarray((1,)),))
    finally:
        batch.close()

    assert [process.exitcode for process in processes] == [23]
    assert all(not process.is_alive() for process in processes)
    assert all(connection.closed for connection in connections)
